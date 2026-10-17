# SPDX-License-Identifier: GPL-3.0-or-later
import serial
from PIL import Image

from minimonitor.link import ScreenLink

FRAME = Image.new("RGB", (480, 320), "#0d1117")


def changed(frame, xy=(20, 22)):
    other = frame.copy()
    other.putpixel(xy, (255, 255, 255))
    return other


class FakeDisplay:
    def __init__(self, fail_after=None):
        self.blits, self.closed, self.levels = [], False, []
        self.fail_after = fail_after

    def brightness(self, percent):
        self.levels.append(percent)

    def blit(self, image, x=0, y=0):
        if self.fail_after is not None and len(self.blits) >= self.fail_after:
            raise serial.SerialException("device gone")
        self.blits.append((x, y, *image.size))

    def close(self):
        self.closed = True


class Opener:
    """Hands out the given displays in turn; an exception in the list is raised instead."""
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def __call__(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_connects_sets_brightness_and_sends_whole_then_partial():
    d = FakeDisplay()
    link = ScreenLink(Opener(d), 60, clock=Clock())
    link.show(FRAME)
    link.show(changed(FRAME))
    link.show(changed(FRAME))
    assert d.levels == [60]
    assert d.blits == [(0, 0, 480, 320), (20, 22, 1, 1)]


def test_unplugged_screen_is_retried_after_delay_without_crashing():
    clock = Clock()
    d = FakeDisplay()
    opener = Opener(RuntimeError("screen not found"), d)
    link = ScreenLink(opener, 60, retry_seconds=3, clock=clock)
    link.show(FRAME)
    clock.t = 1
    link.show(FRAME)
    assert opener.calls == 1 and not link.connected  # waits before retrying
    clock.t = 3
    link.show(FRAME)
    assert link.connected and d.blits == [(0, 0, 480, 320)]


def test_lost_mid_frame_reconnects_and_redraws_whole():
    clock = Clock()
    first, second = FakeDisplay(fail_after=1), FakeDisplay()
    link = ScreenLink(Opener(first, second), 60, retry_seconds=3, clock=clock)
    link.show(FRAME)
    link.show(changed(FRAME))  # second blit fails: unplugged
    assert first.closed and not link.connected
    clock.t = 3
    link.show(changed(FRAME))
    assert second.blits == [(0, 0, 480, 320)]  # the screen may have reset: everything again


def test_drop_forces_full_redraw_after_sleep():
    clock = Clock()
    first, second = FakeDisplay(), FakeDisplay()
    link = ScreenLink(Opener(first, second), 60, retry_seconds=0, clock=clock)
    link.show(FRAME)
    link.drop()
    link.show(FRAME)
    assert first.closed and second.blits == [(0, 0, 480, 320)]


def test_display_failing_right_after_open_is_closed():
    class BadBrightness(FakeDisplay):
        def brightness(self, percent):
            raise serial.SerialTimeoutException("write timeout")
    bad = BadBrightness()
    link = ScreenLink(Opener(bad), 60, clock=Clock())
    link.show(FRAME)
    assert bad.closed and not link.connected  # port freed for the next attempt
