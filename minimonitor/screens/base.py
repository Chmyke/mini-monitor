# SPDX-License-Identifier: GPL-3.0-or-later
"""What every serial screen driver shares: the link, the orientation, the logical size."""

from __future__ import annotations

from enum import IntEnum
from typing import Protocol

from PIL import Image


class Orientation(IntEnum):
    # Values used by the screens themselves (revision A adds 100 to them).
    PORTRAIT = 0
    REVERSE_PORTRAIT = 1
    LANDSCAPE = 2
    REVERSE_LANDSCAPE = 3

    @property
    def landscape(self) -> bool:
        return self in (Orientation.LANDSCAPE, Orientation.REVERSE_LANDSCAPE)

    @property
    def reverse(self) -> bool:
        return self in (Orientation.REVERSE_PORTRAIT, Orientation.REVERSE_LANDSCAPE)


def orientation(landscape: bool = True, flip: bool = False) -> Orientation:
    if landscape:
        return Orientation.REVERSE_LANDSCAPE if flip else Orientation.LANDSCAPE
    return Orientation.REVERSE_PORTRAIT if flip else Orientation.PORTRAIT


class Link(Protocol):
    """The part of serial.Serial the drivers use; tests pass a fake."""
    def write(self, data: bytes) -> int | None: ...
    def read(self, size: int) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    def close(self) -> None: ...


def open_serial(port: str) -> Link:
    import serial
    # write_timeout: a screen gone mid-write raises instead of blocking forever.
    return serial.Serial(port, 115200, timeout=1, write_timeout=5, rtscts=True)


class SerialScreen:
    """A screen behind a serial link. Coordinates are logical: after orientation."""

    NATIVE = (320, 480)  # width, height in portrait, the panel's own way up
    ROUND = False  # a round panel: the dashboard must fit inside the circle
    description = "serial screen"  # for the log, set by whoever opened it

    def __init__(self, link: Link, orientation: Orientation = Orientation.LANDSCAPE,
                 native: tuple[int, int] | None = None):
        self._link = link
        self.orientation = orientation
        self.native_known = native is not None  # else the driver may ask the screen
        self.native = native or self.NATIVE
        try:
            self._start()
        except Exception:
            link.close()
            raise

    @property
    def round(self) -> bool:
        return self.ROUND

    @property
    def size(self) -> tuple[int, int]:
        w, h = self.native
        return (h, w) if self.orientation.landscape else (w, h)

    def _start(self) -> None:
        """Handshake, orientation, screen on: what the screen needs before the first image."""

    def brightness(self, percent: int) -> None:
        raise NotImplementedError

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        raise NotImplementedError

    def refresh(self) -> None:
        """Called once per frame, after the blits. Serial screens have nothing to do."""

    def close(self) -> None:
        self._link.close()


def clamp_percent(percent: int) -> int:
    return max(0, min(100, int(percent)))
