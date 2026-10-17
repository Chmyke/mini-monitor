# SPDX-License-Identifier: GPL-3.0-or-later
"""WeAct Studio Display FS V1 3.5".

Protocol ported from turing-smart-screen-python (library/lcd/lcd_comm_weact_a.py),
Copyright (C) 2021 Matthieu Houdebine and contributors, GPL-3.0-or-later. Commands
end with 0x0A; coordinates are little-endian; pixels are RGB565 little-endian. Not
tested on real hardware.
"""

from __future__ import annotations

from PIL import Image

from .base import SerialScreen, clamp_percent
from .encode import chunked, rgb565

SET_ORIENTATION = 0x02
SET_BRIGHTNESS = 0x03
SET_BITMAP = 0x05
SYSTEM_VERSION = 0x42
READ = 0x80
END = 0x0A
FADE_MS = 1000  # brightness changes fade over this time


class WeAct(SerialScreen):
    NATIVE = (320, 480)

    def _start(self) -> None:
        # Asks for the firmware version: a handshake whose answer is not needed.
        self._link.write(bytes((SYSTEM_VERSION | READ, END)))
        self._link.read(19)
        self._link.reset_input_buffer()
        self._link.write(bytes((SET_ORIENTATION, self.orientation, END)))

    def brightness(self, percent: int) -> None:
        level = int(clamp_percent(percent) / 100 * 255)
        self._link.write(bytes((SET_BRIGHTNESS, level, FADE_MS & 0xFF, FADE_MS >> 8, END)))

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        w, h = image.size
        coords = b"".join(v.to_bytes(2, "little") for v in (x, y, x + w - 1, y + h - 1))
        self._link.write(bytes((SET_BITMAP,)) + coords + bytes((END,)))
        for chunk in chunked(rgb565(image), self.size[0] * 4):
            self._link.write(chunk)
