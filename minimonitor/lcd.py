# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal driver for the Turing Smart Screen 3.5" (revision A, UsbMonitor firmware).

Protocol reference: github.com/mathoudebine/turing-smart-screen-python
(library/lcd/lcd_comm_rev_a.py). Every command is 6 bytes packing a rectangle
(x, y, ex, ey on 10 bits each) and a command code; a bitmap follows as raw
RGB565 little-endian pixels.
"""

from __future__ import annotations

import time
from enum import IntEnum

import serial
from PIL import Image
from serial.tools.list_ports import comports

VID, PID = 0x1A86, 0x5722
SERIAL_NUMBER = "USB35INCHIPSV2"

# Native panel size, in portrait.
NATIVE_WIDTH, NATIVE_HEIGHT = 320, 480


class Command(IntEnum):
    RESET = 101
    CLEAR = 102
    SCREEN_OFF = 108
    SCREEN_ON = 109
    SET_BRIGHTNESS = 110
    SET_ORIENTATION = 121
    DISPLAY_BITMAP = 197
    HELLO = 69


class Orientation(IntEnum):
    PORTRAIT = 0
    REVERSE_PORTRAIT = 1
    LANDSCAPE = 2
    REVERSE_LANDSCAPE = 3


def pack_command(cmd: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> bytes:
    return bytes([
        x >> 2,
        ((x & 3) << 6) + (y >> 4),
        ((y & 15) << 4) + (ex >> 6),
        ((ex & 63) << 2) + (ey >> 8),
        ey & 255,
        cmd,
    ])


def pack_orientation(orientation: Orientation) -> bytes:
    buf = bytearray(16)
    buf[0:6] = pack_command(Command.SET_ORIENTATION)
    buf[6] = orientation + 100
    buf[7], buf[8] = NATIVE_WIDTH >> 8, NATIVE_WIDTH & 255
    buf[9], buf[10] = NATIVE_HEIGHT >> 8, NATIVE_HEIGHT & 255
    return bytes(buf)


def to_rgb565le(image: Image.Image) -> bytes:
    """Convert an RGB image to the panel's pixel format (RGB565, little-endian)."""
    raw = image.convert("RGB").tobytes()
    out = bytearray(len(raw) // 3 * 2)
    j = 0
    for i in range(0, len(raw), 3):
        v = ((raw[i] >> 3) << 11) | ((raw[i + 1] >> 2) << 5) | (raw[i + 2] >> 3)
        out[j] = v & 255
        out[j + 1] = v >> 8
        j += 2
    return bytes(out)


def find_port() -> str | None:
    for p in comports():
        if p.serial_number == SERIAL_NUMBER or (p.vid == VID and p.pid == PID):
            return p.device
    return None


class Screen:
    def __init__(self, port: str | None = None, orientation: Orientation = Orientation.LANDSCAPE):
        port = port or find_port()
        if port is None:
            raise RuntimeError("screen not found (USB 1A86:5722)")
        self._serial = serial.Serial(port, 115200, timeout=1, rtscts=True)
        self.orientation = orientation
        self._serial.write(pack_orientation(orientation))

    @property
    def size(self) -> tuple[int, int]:
        if self.orientation in (Orientation.LANDSCAPE, Orientation.REVERSE_LANDSCAPE):
            return NATIVE_HEIGHT, NATIVE_WIDTH
        return NATIVE_WIDTH, NATIVE_HEIGHT

    def hello(self) -> bytes:
        self._serial.write(bytes([Command.HELLO] * 6))
        answer = self._serial.read(6)
        self._serial.reset_input_buffer()
        return answer

    def brightness(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        # The panel counts backwards: 0 is the brightest, 255 the darkest.
        self._serial.write(pack_command(Command.SET_BRIGHTNESS, int(255 - percent * 2.55)))

    def screen_on(self) -> None:
        self._serial.write(pack_command(Command.SCREEN_ON))

    def screen_off(self) -> None:
        self._serial.write(pack_command(Command.SCREEN_OFF))

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        """Draw an image at (x, y); only that rectangle travels over USB."""
        w, h = image.size
        self._serial.write(pack_command(Command.DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1))
        data = to_rgb565le(image)
        step = self.size[0] * 8
        for i in range(0, len(data), step):
            self._serial.write(data[i:i + step])

    def close(self) -> None:
        self._serial.close()
