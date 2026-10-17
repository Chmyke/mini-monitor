from datetime import datetime, timedelta, timezone

from PIL import Image

from minimonitor.app import RING_FILL_SECONDS, SMOOTH_SECONDS, Gauge, approach, changed_boxes, fresh, smooth
from minimonitor.pc import Snapshot
from minimonitor.usage import Window

REGIONS = {"a": (10, 10, 49, 49), "b": (100, 0, 199, 99)}


def test_first_frame_is_sent_whole():
    img = Image.new("RGB", (480, 320))
    assert changed_boxes(None, img, REGIONS) == [(0, 0, 480, 320)]


def test_only_changed_pixels_are_sent():
    before = Image.new("RGB", (480, 320))
    after = before.copy()
    after.putpixel((20, 30), (255, 255, 255))
    after.putpixel((22, 31), (255, 255, 255))
    assert changed_boxes(before, after, REGIONS) == [(20, 30, 23, 32)]
    assert changed_boxes(after, after, REGIONS) == []


def test_gauge_fills_from_zero_then_moves_to_new_value():
    g = Gauge()
    g.set(40, now=0)
    assert g.shown(0) == 0
    assert 0 < g.shown(RING_FILL_SECONDS / 2) < 40
    assert g.shown(RING_FILL_SECONDS) == 40
    g.set(60, now=10)
    assert g.shown(10) == 40 and g.shown(10 + RING_FILL_SECONDS) == 60
    assert g.glow(10) == 1 and g.glow(100) == 0


def test_gauge_same_value_does_not_restart():
    g = Gauge()
    g.set(40, now=0)
    g.set(40, now=5)
    assert g.changed_at == 0


def test_reset_time_passed_means_unknown():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    assert fresh(Window(50, now - timedelta(seconds=1)), now) is None
    assert fresh(Window(50, now + timedelta(seconds=1)), now) is not None
    assert fresh(Window(50, None), now) is not None
    assert fresh(None, now) is None


def test_approach_glides_then_snaps():
    assert approach(None, 50, 0.1) == 50  # first value: no lerp from nothing
    assert approach(10, None, 0.1) is None  # unknown stays unknown, never stale
    mid = approach(0, 100, SMOOTH_SECONDS)
    assert 60 < mid < 65  # 1 - 1/e of the way after one time constant
    assert approach(0, 100, 10 * SMOOTH_SECONDS) == 100  # snapped, frame stops changing


def test_smooth_snapshot_field_by_field():
    a = Snapshot(40, 0, 0, 10, 64, 50, 0, 0)
    b = Snapshot(None, 100, 100, 10, 64, 50, 1e6, 0)
    s = smooth(a, b, 0.1)
    assert s.gpu_temp is None and 0 < s.cpu < 100 and s.mem_used_gb == 10
    assert smooth(None, b, 0.1) == b
