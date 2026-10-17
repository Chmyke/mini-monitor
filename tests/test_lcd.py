# SPDX-License-Identifier: GPL-3.0-or-later
from PIL import Image

from minimonitor.lcd import Command, Orientation, pack_command, pack_orientation, to_rgb565le


def test_pack_command_matches_reference_encoding():
    # Values from the reference library's bit packing for a 480x320 landscape bitmap.
    assert pack_command(Command.DISPLAY_BITMAP, 0, 0, 479, 319) == bytes([0, 0, 7, 125, 63, 197])
    assert pack_command(Command.DISPLAY_BITMAP, 340, 270, 459, 309) == bytes([85, 16, 231, 45, 53, 197])


def test_brightness_and_screen_commands_carry_no_rectangle():
    assert pack_command(Command.SCREEN_ON) == bytes([0, 0, 0, 0, 0, 109])


def test_orientation_payload():
    buf = pack_orientation(Orientation.LANDSCAPE)
    assert len(buf) == 16
    assert buf[5] == Command.SET_ORIENTATION
    assert buf[6] == 102
    assert buf[7:11] == bytes([1, 64, 1, 224])  # 320 x 480, native portrait


def test_rgb565_little_endian():
    img = Image.new("RGB", (3, 1))
    img.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    assert to_rgb565le(img) == bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00])
