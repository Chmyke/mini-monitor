# SPDX-License-Identifier: GPL-3.0-or-later
"""Revision A: Turing Smart Screen 3.5" and UsbMonitor 3.5" / 5" / 7".

Protocol ported from turing-smart-screen-python (library/lcd/lcd_comm_rev_a.py),
Copyright (C) 2021 Matthieu Houdebine, GPL-3.0-or-later. Every command is 6 bytes
packing a rectangle (x, y, ex, ey on 10 bits each) and a command code; a bitmap
follows as raw RGB565 little-endian pixels.

Tested on the UsbMonitor 3.5" (serial USB35INCHIPSV2), 2026-10-17. It answered HELLO
with 01 x6 once, and not at all later: its serial number gives its size instead, and
HELLO (one second of waiting when unanswered) is only sent to other revision A screens.
"""

from __future__ import annotations

from enum import IntEnum

from PIL import Image

from .base import Orientation, SerialScreen, clamp_percent
from .encode import chunked, rgb565


class Command(IntEnum):
    RESET = 101
    CLEAR = 102
    SCREEN_OFF = 108
    SCREEN_ON = 109
    SET_BRIGHTNESS = 110
    SET_ORIENTATION = 121
    DISPLAY_BITMAP = 197
    HELLO = 69


# Answer to HELLO -> panel size in portrait. The original Turing 3.5" does not answer.
SIZES = {
    bytes([1] * 6): (320, 480),
    bytes([2] * 6): (480, 800),
    bytes([3] * 6): (600, 1024),
}


def pack_command(cmd: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> bytes:
    return bytes([
        x >> 2,
        ((x & 3) << 6) + (y >> 4),
        ((y & 15) << 4) + (ex >> 6),
        ((ex & 63) << 2) + (ey >> 8),
        ey & 255,
        cmd,
    ])


def pack_orientation(orientation: Orientation, width: int, height: int) -> bytes:
    """width, height: the native size, in portrait.

    The reference library sends the size after orientation instead; the native size is
    what was verified on the UsbMonitor 3.5" in landscape (2026-10-17), so it is kept.
    """
    buf = bytearray(16)
    buf[0:6] = pack_command(Command.SET_ORIENTATION)
    buf[6] = orientation + 100
    buf[7], buf[8] = width >> 8, width & 255
    buf[9], buf[10] = height >> 8, height & 255
    return bytes(buf)


class RevA(SerialScreen):
    NATIVE = (320, 480)

    def _start(self) -> None:
        if not self.native_known:
            self.native = SIZES.get(self.hello(), self.native)
        self._link.write(pack_orientation(self.orientation, *self.native))
        self._link.write(pack_command(Command.SCREEN_ON))

    def hello(self) -> bytes:
        self._link.write(bytes([Command.HELLO] * 6))
        answer = self._link.read(6)
        self._link.reset_input_buffer()
        return answer

    def brightness(self, percent: int) -> None:
        # The panel counts backwards: 0 is the brightest, 255 the darkest.
        level = int(255 - clamp_percent(percent) / 100 * 255)
        self._link.write(pack_command(Command.SET_BRIGHTNESS, level))

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        """Draw an image at (x, y); only that rectangle travels over USB."""
        w, h = image.size
        self._link.write(pack_command(Command.DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1))
        for chunk in chunked(rgb565(image), self.size[0] * 8):
            self._link.write(chunk)
