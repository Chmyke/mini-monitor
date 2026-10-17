# SPDX-License-Identifier: GPL-3.0-or-later
"""Revision C: Turing Smart Screen 2.1" (round), 5" and 8.8".

Protocol ported from turing-smart-screen-python (library/lcd/lcd_comm_rev_c.py),
Copyright (C) 2021 Matthieu Houdebine, (C) 2023 Alex W. Baule, (C) 2023 Arthur Ferrai,
GPL-3.0-or-later. Every message is padded to a multiple of 250 bytes. The panel is
landscape at heart: other orientations are rotated here, in software. Not tested on
real hardware.

The screen's own ID is not reliable (the 2.1" answers "chs_5inch"), so the model,
hence the size, comes from the USB serial number seen before wake-up, or from --screen.
"""

from __future__ import annotations

import string
import time
from math import ceil

from PIL import Image

from .base import Orientation, SerialScreen, clamp_percent
from .encode import bgr, bgra, chunked

HELLO = bytes((0x01, 0xEF, 0x69, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0xC5, 0xD3))
OPTIONS = bytes((0x7D, 0xEF, 0x69, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x2D))
SET_BRIGHTNESS = bytes((0x7B, 0xEF, 0x69, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00))
STOP_VIDEO = bytes((0x79, 0xEF, 0x69, 0x00, 0x00, 0x00, 0x01))
STOP_MEDIA = bytes((0x96, 0xEF, 0x69, 0x00, 0x00, 0x00, 0x01))
QUERY_STATUS = bytes((0xCF, 0xEF, 0x69, 0x00, 0x00, 0x00, 0x01))
START_DISPLAY_BITMAP = bytes((0x2C,))
PRE_UPDATE_BITMAP = bytes((0x86, 0xEF, 0x69, 0x00, 0x00, 0x00, 0x01))
UPDATE_BITMAP = bytes((0xCC, 0xEF, 0x69, 0x00))
DISPLAY_BITMAP = {  # by panel size in portrait
    (480, 480): bytes((0xC8, 0xEF, 0x69, 0x00, 0x0E, 0x10)),
    (480, 800): bytes((0xC8, 0xEF, 0x69, 0x00, 0x17, 0x70)),
    (480, 1920): bytes((0xC8, 0xEF, 0x69, 0x00, 0x38, 0x40)),
}
# Start mode default, padding, no flip, no sleep.
OPTIONS_PAYLOAD = bytes((0x00, 0x00, 0x00, 0x00))
STATUS_SIZE = 1024
HELLO_ATTEMPTS = 5
DEFAULT_ROM = 87


def pad(message: bytes, fill: bytes = b"\0") -> bytes:
    if len(message) % 250:
        message += fill * (250 * ceil(len(message) / 250) - len(message))
    return message


def rom_version(screen_id: str) -> int:
    """'chs_5inch.dev1_rom1.87' -> 87; out of the known range, the usual 87."""
    try:
        version = int(screen_id.split(".")[2])
    except (IndexError, ValueError):
        return DEFAULT_ROM
    return version if 80 <= version <= 100 else DEFAULT_ROM


class RevC(SerialScreen):
    NATIVE = (480, 800)

    def _start(self) -> None:
        if self.native not in DISPLAY_BITMAP:
            raise ValueError(f"unsupported revision C size {self.native}")
        self._count = 0
        self.rom = rom_version(self._hello())
        self._send(OPTIONS + OPTIONS_PAYLOAD)  # orientation is software: always the same options
        self._send(STOP_VIDEO)  # screen on: leave the vendor's video or media mode
        self._send(STOP_MEDIA, read=STATUS_SIZE)

    @property
    def round(self) -> bool:
        return self.native == (480, 480)

    @property
    def _eight_inch(self) -> bool:
        return self.native == (480, 1920)

    def _send(self, message: bytes, fill: bytes = b"\0", read: int = 0) -> None:
        self._link.write(pad(message, fill))
        if read:
            self._link.read(read)

    def _hello(self) -> str:
        for attempt in range(HELLO_ATTEMPTS):
            if attempt:
                time.sleep(1)
            self._link.reset_input_buffer()
            self._send(HELLO)
            answer = self._link.read(23).decode(errors="ignore")
            self._link.reset_input_buffer()
            screen_id = "".join(c for c in answer if c in string.printable)
            if screen_id.startswith("chs_"):
                return screen_id
        raise OSError("no valid ID from a revision C screen")

    def brightness(self, percent: int) -> None:
        self._send(SET_BRIGHTNESS + bytes([int(clamp_percent(percent) / 100 * 255)]))

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        if (x, y) == (0, 0) and image.size == self.size:
            self._send(PRE_UPDATE_BITMAP)
            self._send(START_DISPLAY_BITMAP, fill=START_DISPLAY_BITMAP)
            # Same length field as the reference library, whatever it means.
            self._send(DISPLAY_BITMAP[self.native] + (self.native[0] ** 2 // 64).to_bytes(2, "big"))
            self._send(self._full_image(image), read=STATUS_SIZE)
        else:
            data, header = self._update_image(image, x, y)
            self._send(header)
            self._send(data)
            self._count += 1
        self._send(QUERY_STATUS, read=STATUS_SIZE)

    def _full_image(self, image: Image.Image) -> bytes:
        o = self.orientation
        if self._eight_inch:
            angle = {Orientation.LANDSCAPE: 270, Orientation.REVERSE_LANDSCAPE: 90,
                     Orientation.PORTRAIT: 180, Orientation.REVERSE_PORTRAIT: 0}[o]
        else:
            angle = {Orientation.PORTRAIT: 90, Orientation.REVERSE_PORTRAIT: 270,
                     Orientation.REVERSE_LANDSCAPE: 180, Orientation.LANDSCAPE: 0}[o]
        if angle:
            image = image.rotate(angle, expand=True)
        return b"\0".join(chunked(bgra(image), 249))

    def _update_image(self, image: Image.Image, x: int, y: int) -> tuple[bytes, bytes]:
        """(pixel rows, header) of a partial update, in the panel's own coordinates."""
        o = self.orientation
        width, height = self.size
        x0, y0 = x, y
        if self._eight_inch:
            if o == Orientation.LANDSCAPE:
                image = image.rotate(270, expand=True)
                y0 = height - y - image.width
            elif o == Orientation.REVERSE_LANDSCAPE:
                image = image.rotate(90, expand=True)
                x0 = width - x - image.height
            elif o == Orientation.PORTRAIT:
                image = image.rotate(180, expand=True)
                x0 = height - y - image.height
                y0 = height - x - image.width
            else:
                x0, y0 = y, x
        else:
            if o == Orientation.PORTRAIT:
                image = image.rotate(90, expand=True)
                x0 = width - x - image.height
            elif o == Orientation.REVERSE_PORTRAIT:
                image = image.rotate(270, expand=True)
                y0 = height - y - image.width
            elif o == Orientation.REVERSE_LANDSCAPE:
                image = image.rotate(180)
                y0 = width - x - image.width
                x0 = height - y - image.height
            else:
                x0, y0 = y, x

        if self.native != (480, 480) and self.rom > 88:
            pixels, pixel_size = bgra(image), 4
        else:
            pixels, pixel_size = bgr(image), 3
        stride = self.native[0] if self._eight_inch else self.native[1]
        rows = bytearray()
        for h, line in enumerate(chunked(pixels, image.width * pixel_size)):
            rows += ((x0 + h) * stride + y0).to_bytes(3, "big")
            rows += image.width.to_bytes(2, "big")
            rows += line

        header = UPDATE_BITMAP + (len(rows) + 2).to_bytes(3, "big") + b"\0" * 3 + self._count.to_bytes(4, "big")
        if len(rows) > 250:
            rows = bytearray(b"\0".join(chunked(bytes(rows), 249)))
        return bytes(rows) + b"\xef\x69", header
