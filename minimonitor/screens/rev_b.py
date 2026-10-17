# SPDX-License-Identifier: GPL-3.0-or-later
"""Revision B: XuanFang 3.5" (including the "flagship" model with an RGB backplate).

Protocol ported from turing-smart-screen-python (library/lcd/lcd_comm_rev_b.py),
Copyright (C) 2021 Matthieu Houdebine, (C) 2022 Charles Ferguson, GPL-3.0-or-later.
Commands are 10 bytes: the code, 8 bytes of payload, the code again. Pixels are
RGB565 big-endian. Not tested on real hardware.
"""

from __future__ import annotations

import time
from enum import IntEnum

from PIL import Image

from .base import Orientation, SerialScreen, clamp_percent
from .encode import chunked, rgb565


class Command(IntEnum):
    HELLO = 0xCA
    SET_ORIENTATION = 0xCB
    DISPLAY_BITMAP = 0xCC
    SET_LIGHTING = 0xCD
    SET_BRIGHTNESS = 0xCE


HELLO = b"HELLO"
# Sub-revisions whose brightness goes from 0 to 255; the others only know on and off.
DIMMABLE = (0x11, 0x12)
# Without it, a bitmap sent right after another one is often corrupted (reference library).
COOLDOWN_SECONDS = 0.05


def pack(cmd: int, payload: bytes = b"") -> bytes:
    payload = bytes(payload[:8]).ljust(8, b"\0")
    return bytes([cmd]) + payload + bytes([cmd])


class RevB(SerialScreen):
    NATIVE = (320, 480)

    def _start(self) -> None:
        self._dimmable = False
        self._link.write(pack(Command.HELLO, HELLO))
        answer = self._link.read(10)
        self._link.reset_input_buffer()
        if not answer:
            raise OSError("no answer to HELLO from a revision B screen")
        # Like the reference library, an odd answer is tolerated: only the sub-revision is read.
        self._dimmable = len(answer) >= 8 and answer[6] == 0xA and answer[7] in DIMMABLE
        # The screen turns portrait or landscape; the reverse ones are done here, in software.
        self._link.write(pack(Command.SET_ORIENTATION, bytes([1 if self.orientation.landscape else 0])))

    def brightness(self, percent: int) -> None:
        percent = clamp_percent(percent)
        if self._dimmable:
            level = int(percent / 100 * 255)
        else:
            level = 1 if percent == 0 else 0  # 1 is off, 0 full brightness
        self._link.write(pack(Command.SET_BRIGHTNESS, bytes([level])))

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        w, h = image.size
        width, height = self.size
        if self.orientation.reverse:
            image = image.rotate(180)
            x0, y0, x1, y1 = width - x - w, height - y - h, width - x - 1, height - y - 1
        else:
            x0, y0, x1, y1 = x, y, x + w - 1, y + h - 1
        self._link.write(pack(Command.DISPLAY_BITMAP, b"".join(v.to_bytes(2, "big") for v in (x0, y0, x1, y1))))
        for chunk in chunked(rgb565(image, big_endian=True), width * 8):
            self._link.write(chunk)
        time.sleep(COOLDOWN_SECONDS)
