# SPDX-License-Identifier: GPL-3.0-or-later
"""Revision D: Kipye Qiye Smart Display 3.5".

Protocol ported from turing-smart-screen-python (library/lcd/lcd_comm_rev_d.py),
Copyright (C) 2021 Matthieu Houdebine, GPL-3.0-or-later. The screen only knows
portrait and its reverse: landscape is rotated here, in software. Pixels are RGB565
big-endian, sent 63 bytes at a time. Not tested on real hardware.
"""

from __future__ import annotations

from PIL import Image

from .base import SerialScreen, clamp_percent
from .encode import chunked, rgb565

SET_ORIGINAL = bytes((67, 72, 0, 0))  # portrait
SET_180 = bytes((67, 71, 0, 0))  # reverse portrait
SET_BRIGHTNESS = bytes((67, 67))
BLOCK_WRITE = bytes((67, 65))
PICTURE_MODE_IN = bytes((68, 0, 0, 0))
PICTURE_MODE_OUT = bytes((65, 0, 0, 0))
PIXELS = b"\x50"


class RevD(SerialScreen):
    NATIVE = (320, 480)

    def _write(self, message: bytes) -> None:
        self._link.write(message)
        # The screen acknowledges every message; nothing here needs the answers.
        self._link.reset_input_buffer()

    def _start(self) -> None:
        self._write(SET_180 if self.orientation.reverse else SET_ORIGINAL)

    def brightness(self, percent: int) -> None:
        level = (clamp_percent(percent) * 5).to_bytes(2, "big")  # 0..500
        # Sent twice: once is sometimes ignored (reference library).
        self._write(SET_BRIGHTNESS + level)
        self._write(SET_BRIGHTNESS + level)

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        w, h = image.size
        if self.orientation.landscape:
            image = image.rotate(270, expand=True)
            x0, y0, x1, y1 = self.native[0] - y - h, x, self.native[0] - y - 1, x + w - 1
        else:
            x0, y0, x1, y1 = x, y, x + w - 1, y + h - 1
        self._write(BLOCK_WRITE + b"".join(v.to_bytes(2, "big") for v in (x0, x1, y0, y1)))
        self._write(PICTURE_MODE_IN)
        for chunk in chunked(rgb565(image, big_endian=True), 63):
            self._write(PIXELS + chunk)
        self._write(PICTURE_MODE_OUT)
