# SPDX-License-Identifier: GPL-3.0-or-later
"""Keeps the screen connected and in sync with the frames drawn in memory.

The screen can vanish at any time: unplugged, USB reset, PC asleep. Any serial
error drops the connection; it is then reopened every few seconds, and the first
frame after a (re)connection is sent whole, since the screen may have reset.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Protocol

import serial
from PIL import Image, ImageChops

from .render import REGIONS

RETRY_SECONDS = 3.0
# RuntimeError: the screen is not plugged in (lcd.Screen cannot find its port).
SCREEN_ERRORS = (serial.SerialException, OSError, RuntimeError)

log = logging.getLogger(__name__)


class Display(Protocol):
    def brightness(self, percent: int) -> None: ...
    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None: ...
    def close(self) -> None: ...


def changed_boxes(previous: Image.Image | None, current: Image.Image,
                  regions: dict[str, tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Smallest rectangles (x0, y0, x1, y1 exclusive) to resend, one per changed region."""
    if previous is None:
        return [(0, 0, *current.size)]
    boxes = []
    for x0, y0, x1, y1 in regions.values():
        box = (x0, y0, x1 + 1, y1 + 1)
        diff = ImageChops.difference(previous.crop(box), current.crop(box)).getbbox()
        if diff:
            boxes.append((x0 + diff[0], y0 + diff[1], x0 + diff[2], y0 + diff[3]))
    return boxes


class ScreenLink:
    def __init__(self, open_display: Callable[[], Display], brightness: int,
                 retry_seconds: float = RETRY_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._open = open_display
        self._brightness = brightness
        self._retry = retry_seconds
        self._clock = clock
        self._display: Display | None = None
        self._shown: Image.Image | None = None  # what the screen shows; None: unknown
        self._next_try = 0.0
        self._reported_down = False  # log a lasting outage once, not every retry

    @property
    def connected(self) -> bool:
        return self._display is not None

    def show(self, frame: Image.Image) -> None:
        if self._display is None and not self._connect():
            return
        try:
            for x0, y0, x1, y1 in changed_boxes(self._shown, frame, REGIONS):
                self._display.blit(frame.crop((x0, y0, x1, y1)), x0, y0)
            self._shown = frame
        except SCREEN_ERRORS as e:
            log.warning("screen lost: %s", type(e).__name__)
            self.drop()

    def drop(self) -> None:
        """Forget the connection; the next frame reconnects and is sent whole."""
        if self._display is not None:
            try:
                self._display.close()
            except SCREEN_ERRORS:
                pass
        self._display, self._shown = None, None
        self._next_try = self._clock() + self._retry

    def _connect(self) -> bool:
        if self._clock() < self._next_try:
            return False
        display = None
        try:
            display = self._open()
            display.brightness(self._brightness)
        except SCREEN_ERRORS as e:
            if display is not None:  # opened but already failing: free the port for the next try
                try:
                    display.close()
                except SCREEN_ERRORS:
                    pass
            if not self._reported_down:
                log.warning("screen unavailable (%s), retrying every %.0f s", type(e).__name__, self._retry)
                self._reported_down = True
            self._next_try = self._clock() + self._retry
            return False
        log.info("screen connected")
        self._display, self._shown, self._reported_down = display, None, False
        return True
