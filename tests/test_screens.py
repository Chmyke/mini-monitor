# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
from math import ceil
from types import SimpleNamespace

import pytest
from PIL import Image

from minimonitor import screens
from minimonitor.screens import encode, rev_b, rev_c
from minimonitor.screens.base import Orientation
from minimonitor.screens.rev_a import Command, RevA, pack_command, pack_orientation
from minimonitor.screens.rev_b import RevB
from minimonitor.screens.rev_c import RevC, rom_version
from minimonitor.screens.rev_d import RevD
from minimonitor.screens.weact import WeAct


class FakeLink:
    def __init__(self, answers=()):
        self.answers, self.out, self.closed = list(answers), bytearray(), False

    def write(self, data):
        self.out += data

    def read(self, size):
        return self.answers.pop(0) if self.answers else b""

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True


def pattern(w, h, seed=0):
    n = w * h * 3
    base = bytes((i + seed) % 251 for i in range(251))
    return Image.frombytes("RGB", (w, h), (base * ceil(n / 251))[:n])


# --- Byte for byte against the reference library -------------------------------------
# Hashes of everything the drivers of turing-smart-screen-python (commit 2b33ab4) write
# for: handshake, orientation, screen on, brightness 60, a full frame, a 37x11 patch at
# (100, 50), a 1x1 patch at (5, 7). Produced once by running that library against a fake
# port. Revision A deliberately keeps the native size in its orientation packet (see rev_a).

A35, A5 = bytes([1] * 6), bytes([2] * 6)
B_DIM, B_ONOFF = b"\xcaHELLO\x0a\x12\x00\xca", b"\xcaHELLO\x0a\x01\x00\xca"
C87, C90 = b"chs_5inch.dev1_rom1.87\x00", b"chs_5inch.dev1_rom1.90\x00"
C88 = b"chs_88inch.dev1_rom1.87"
DRIVERS = {"A": RevA, "B": RevB, "C": RevC, "D": RevD, "W": WeAct}

REFERENCE = [
    ("A", None, "LANDSCAPE", [A35], "c6873b35768e1aaa", 308068),
    ("A", None, "PORTRAIT", [A35], "dc4c3a80b4b907d4", 308068),
    ("A", None, "REVERSE_LANDSCAPE", [A35], "8a2794b75a8b117c", 308068),
    ("A", None, "LANDSCAPE", [A5], "b39f5e87be1bc30e", 768868),  # UsbMonitor 5"
    ("A", None, "LANDSCAPE", [], "c6873b35768e1aaa", 308068),  # Turing 3.5": no answer
    ("B", None, "LANDSCAPE", [B_DIM], "b103d79da9117691", 308076),
    ("B", None, "PORTRAIT", [B_DIM], "736f12f31a421a9b", 308076),
    ("B", None, "REVERSE_LANDSCAPE", [B_DIM], "8dd64d68191846ff", 308076),
    ("B", None, "LANDSCAPE", [B_ONOFF], "a059c920aa150945", 308076),
    ("C", (480, 800), "LANDSCAPE", [C87], "7ebcf74f5f50c5a1", 1547250),
    ("C", (480, 800), "PORTRAIT", [C87], "18eb5319baa132b8", 1547250),
    ("C", (480, 800), "REVERSE_LANDSCAPE", [C87], "f5f2a9212bed26bd", 1547250),
    ("C", (480, 800), "REVERSE_PORTRAIT", [C87], "20734b528ef86d80", 1547250),
    ("C", (480, 800), "LANDSCAPE", [C90], "794639b42b62e037", 1547500),
    ("C", (480, 800), "PORTRAIT", [C90], "8b0b9a1edef5f240", 1547750),
    ("C", (480, 1920), "LANDSCAPE", [C88], "790a411b43aa8892", 3706250),
    ("C", (480, 1920), "PORTRAIT", [C88], "3c89121fbcbce28f", 3706250),
    ("C", (480, 1920), "REVERSE_LANDSCAPE", [C88], "5e81a844d7e60a22", 3706250),
    ("C", (480, 1920), "REVERSE_PORTRAIT", [C88], "6e03106dc5b5585c", 3706250),
    ("C", (480, 480), "LANDSCAPE", [C87], "76759c91ca907efa", 930500),
    ("C", (480, 480), "REVERSE_PORTRAIT", [C87], "4761be3bfd85ea2b", 930500),
    ("D", None, "LANDSCAPE", [], "578eb12edebb3332", 312973),
    ("D", None, "PORTRAIT", [], "39f43c73e7538608", 312973),
    ("D", None, "REVERSE_LANDSCAPE", [], "66bc6cbe60e0dab3", 312973),
    ("W", None, "LANDSCAPE", [bytes(19)], "ba978045bfe39dbd", 308056),
    ("W", None, "PORTRAIT", [bytes(19)], "08262de641fa2bd0", 308056),
]


@pytest.mark.parametrize("driver, native, orient, answers, digest, length", REFERENCE)
def test_driver_writes_exactly_what_the_reference_library_writes(
        monkeypatch, driver, native, orient, answers, digest, length):
    monkeypatch.setattr(rev_b.time, "sleep", lambda s: None)
    link = FakeLink(answers)
    screen = DRIVERS[driver](link, Orientation[orient], native)
    screen.brightness(60)
    screen.blit(pattern(*screen.size))
    screen.blit(pattern(37, 11, 3), 100, 50)
    screen.blit(pattern(1, 1, 5), 5, 7)
    assert (hashlib.sha256(bytes(link.out)).hexdigest()[:16], len(link.out)) == (digest, length)


# --- Revision A details, checked on the real screen ------------------------------------

def test_pack_command_matches_reference_encoding():
    # Values from the reference library's bit packing for a 480x320 landscape bitmap.
    assert pack_command(Command.DISPLAY_BITMAP, 0, 0, 479, 319) == bytes([0, 0, 7, 125, 63, 197])
    assert pack_command(Command.DISPLAY_BITMAP, 340, 270, 459, 309) == bytes([85, 16, 231, 45, 53, 197])


def test_brightness_and_screen_commands_carry_no_rectangle():
    assert pack_command(Command.SCREEN_ON) == bytes([0, 0, 0, 0, 0, 109])


def test_orientation_payload():
    buf = pack_orientation(Orientation.LANDSCAPE, 320, 480)
    assert len(buf) == 16
    assert buf[5] == Command.SET_ORIENTATION
    assert buf[6] == 102
    assert buf[7:11] == bytes([1, 64, 1, 224])  # 320 x 480, native portrait


def test_rev_a_with_a_known_size_skips_hello():
    link = FakeLink([A5])
    screen = RevA(link, Orientation.LANDSCAPE, (320, 480))
    assert screen.size == (480, 320) and link.answers == [A5]  # nothing was asked
    assert bytes([Command.HELLO] * 6) not in link.out


def test_rev_a_size_comes_from_the_hello_answer():
    assert RevA(FakeLink([A35])).size == (480, 320)
    assert RevA(FakeLink([A5])).size == (800, 480)
    assert RevA(FakeLink([bytes([3] * 6)]), Orientation.PORTRAIT).size == (600, 1024)


# --- Encoders ------------------------------------------------------------------------

def slow_rgb565(image, big=False):
    out, raw = bytearray(), image.tobytes()
    for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3]):
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        out += v.to_bytes(2, "big" if big else "little")
    return bytes(out)


def test_rgb565_little_endian():
    img = Image.new("RGB", (3, 1))
    img.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    assert encode.rgb565(img) == bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00])


def test_rgb565_matches_the_per_pixel_formula_both_ways():
    img = pattern(61, 17, 9)
    assert encode.rgb565(img) == slow_rgb565(img)
    assert encode.rgb565(img, big_endian=True) == slow_rgb565(img, big=True)


def test_rev_c_rom_version():
    assert rom_version("chs_5inch.dev1_rom1.87") == 87
    assert rom_version("chs_5inch.dev1_rom1.92") == 92
    assert rom_version("chs_5inch") == 87
    assert rom_version("chs_5inch.dev1_rom1.12") == 87


def test_rev_c_gives_up_on_a_screen_that_never_says_hello(monkeypatch):
    monkeypatch.setattr(rev_c.time, "sleep", lambda s: None)
    link = FakeLink([b"garbage"] * 10)
    with pytest.raises(OSError):
        RevC(link, Orientation.LANDSCAPE, (480, 800))
    assert link.closed  # the port is freed for the next attempt


def test_round_screen_is_known():
    assert RevC(FakeLink([C87]), Orientation.LANDSCAPE, (480, 480)).round
    assert not RevC(FakeLink([C87]), Orientation.LANDSCAPE, (480, 800)).round


# --- Recognition -----------------------------------------------------------------------

def port(device, vid=None, pid=None, sn=None):
    return SimpleNamespace(device=device, vid=vid, pid=pid, serial_number=sn)


@pytest.mark.parametrize("info, model", [
    (port("COM3", 0x1A86, 0x5722, "USB35INCHIPSV2"), "turing-3.5"),
    (port("COM3", 0x1A86, 0x5722, None), "turing-3.5"),
    (port("COM4", 0x1A86, 0x5722, "2017-2-25"), "xuanfang-3.5"),
    (port("/dev/ttyACM0", 0x454D, 0x4E41), "kipye-3.5"),
    (port("/dev/ttyACM0", 0x1A86, 0xFE0C), "weact-3.5"),
    (port("COM7", 0x1D6B, 0x0121, "20080411"), "turing-5"),
    (port("COM7", 0x1A86, 0xCA21, "CT21INCH"), "turing-2.1"),
    (port("COM7", 0x1A86, 0xCA21, "CT88INCH"), "turing-8.8"),
])
def test_identify(info, model):
    assert screens.identify(info).model.name == model


def test_unrelated_serial_devices_are_ignored():
    assert screens.identify(port("COM1")) is None
    assert screens.identify(port("COM5", 0x1A86, 0x7523, "CH340")) is None  # a plain USB-serial adapter
    assert screens.find([port("COM1"), port("COM5", 0x2341, 0x0043)]) is None


def test_open_screen_auto_detects_and_describes(monkeypatch):
    ports = [port("COM1"), port("COM3", 0x1A86, 0x5722, "USB35INCHIPSV2")]
    links = {}
    screen = screens.open_screen(ports=lambda: ports, connect=lambda d: links.setdefault(d, FakeLink([A35])))
    assert list(links) == ["COM3"]
    assert isinstance(screen, RevA) and screen.description == "turing-3.5 on COM3, 480x320"
    assert links["COM3"].answers == [A35]  # its serial number gave the size: no HELLO


def test_open_screen_with_a_model_uses_its_size(monkeypatch):
    ports = [port("COM7", 0x1D6B, 0x0121, "20080411")]
    screen = screens.open_screen("turing-8.8", ports=lambda: ports, connect=lambda d: FakeLink([C88]))
    assert screen.size == (1920, 480)


def test_open_screen_without_a_screen_is_retried_later():
    with pytest.raises(RuntimeError):
        screens.open_screen(ports=lambda: [port("COM1")], connect=lambda d: FakeLink())


def test_hand_given_port_defaults_to_revision_a():
    screen = screens.open_screen(port="COM9", ports=lambda: [], connect=lambda d: FakeLink([A35]))
    assert isinstance(screen, RevA)


def test_sleeping_rev_c_is_woken_then_opened_on_its_new_port(monkeypatch):
    asleep = [port("COM7", 0x1A86, 0xCA21, "CT88INCH")]
    awake = [port("COM8", 0x1D6B, 0x0121, "20080411")]
    calls = []
    monkeypatch.setattr(screens, "open_serial", lambda d: calls.append(d) or FakeLink())
    monkeypatch.setattr(screens.time, "sleep", lambda s: None)
    states = iter([asleep, awake, awake])
    screen = screens.open_screen(ports=lambda: next(states), connect=lambda d: FakeLink([C88]))
    assert calls == ["COM7"] and screen.size == (1920, 480)  # the 8.8" seen asleep keeps its size
