# SPDX-License-Identifier: GPL-3.0-or-later
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image, ImageChops, ImageDraw

from minimonitor import theme
from minimonitor.i18n import EN, FR
from minimonitor.pc import Snapshot
from minimonitor.render import LANDSCAPE, PORTRAIT, Ring, View, render, scene_for
from minimonitor.usage import Window

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
# Every screen the drivers know, both ways up, plus odd window sizes.
SIZES = [(480, 320), (320, 480), (800, 480), (480, 800), (1024, 600), (600, 1024), (1920, 480),
         (480, 1920), (640, 640), (300, 200), (1280, 720)]


def view(pct: float | None, pc: Snapshot | None, pulse: float, glow: float, texts=FR, disk="C:") -> View:
    w = Window(pct, NOW + timedelta(hours=1, minutes=29)) if pct is not None else None
    return View(
        now=NOW, pulse=pulse, live=w is not None,
        session=Ring(w, pct or 0, glow, theme.BLUE, "SESSION 5 H"),
        week=Ring(w, pct or 0, glow, theme.GREEN, "SEMAINE"),
        pc=pc,
        texts=texts,
        gpu_label="GPU 4080 S",
        disk_label=disk,
    )


BUSY = Snapshot(91, 100, 100, 62.9, 63.9, 99, 250e6, 250e6)
IDLE = Snapshot(30, 0, 0, 1, 63.9, 0, 0, 0)
NO_DISK = Snapshot(None, None, 3, 1, 63.9, None, 1e3, 1e3)


def assert_changes_stay_inside_regions(scene):
    """Partial updates are only correct if no pixel outside the regions ever changes."""
    frames = [
        render(view(100, BUSY, 1, 1), scene),
        render(view(0, IDLE, 0, 0), scene),
        render(view(None, None, 0.5, 0), scene),
        render(view(77.7, BUSY, 0.2, 0.5), scene),
        render(view(12, IDLE, 0.7, 0, EN), scene),
        render(view(5, NO_DISK, 0.9, 0.1, EN), scene),
    ]
    mask = Image.new("L", scene.size, 255)
    draw = ImageDraw.Draw(mask)
    for box in scene.regions.values():
        draw.rectangle(box, fill=0)
    black = Image.new("RGB", scene.size)
    base = Image.composite(frames[0], black, mask)
    for frame in frames[1:]:
        assert frame.size == scene.size
        assert ImageChops.difference(base, Image.composite(frame, black, mask)).getbbox() is None


@pytest.mark.parametrize("size", SIZES)
def test_everything_that_changes_stays_inside_regions(size):
    assert_changes_stay_inside_regions(scene_for(size))


def test_round_screen_regions_hold_too():
    assert_changes_stay_inside_regions(scene_for((480, 480), round_screen=True))


@pytest.fixture
def no_installed_fonts(monkeypatch):
    """What a Linux box without any of the preferred fonts gets: Pillow's own font."""
    theme.font.cache_clear()
    monkeypatch.setattr(theme, "find", lambda names: None)
    yield
    theme.font.cache_clear()


@pytest.mark.parametrize("size", [(480, 320), (320, 480)])
def test_regions_hold_with_the_fallback_font(no_installed_fonts, size):
    assert_changes_stay_inside_regions(scene_for(size))


@pytest.mark.parametrize("size", SIZES)
def test_regions_inside_the_screen(size):
    w, h = size
    for x0, y0, x1, y1 in scene_for(size).regions.values():
        assert 0 <= x0 < x1 < w and 0 <= y0 < y1 < h


def test_the_layout_follows_the_screen_shape():
    assert scene_for((800, 480)).layout is LANDSCAPE
    assert scene_for((480, 800)).layout is PORTRAIT


def test_scaled_layout_fills_and_is_centred():
    s = scene_for((800, 480))
    assert s.scale == 1.5 and s.offset == (40, 0)
    assert scene_for((480, 320)).scale == 1 and scene_for((480, 320)).offset == (0, 0)


def test_round_screen_keeps_every_corner_inside_the_circle():
    s = scene_for((480, 480), round_screen=True)
    for x, y in ((0, 0), (480, 0), (0, 320), (480, 320)):  # layout corners
        px, py = s.offset[0] + x * s.scale, s.offset[1] + y * s.scale
        assert (px - 240) ** 2 + (py - 240) ** 2 <= 240 ** 2 + 1


def test_default_frame_is_the_historic_480x320():
    assert render(view(43, IDLE, 0, 0)).size == (480, 320)


def test_disk_label_is_drawn():
    a = render(view(43, IDLE, 0, 0, disk="C:"))
    b = render(view(43, IDLE, 0, 0, disk="/"))
    assert ImageChops.difference(a, b).getbbox() is not None


def test_fonts_are_found_in_subfolders_too(monkeypatch, tmp_path):
    """Linux keeps fonts in subfolders (/usr/share/fonts/truetype/dejavu/...)."""
    nested = tmp_path / "truetype" / "dejavu"
    nested.mkdir(parents=True)
    (nested / "DejaVuSansMono-Bold.ttf").write_bytes(b"")
    monkeypatch.setattr(theme, "FONT_DIRS", [tmp_path])
    theme.find.cache_clear()
    theme._installed.cache_clear()
    try:
        assert theme.find(("consolab.ttf", "DejaVuSansMono-Bold.ttf")) == nested / "DejaVuSansMono-Bold.ttf"
        assert theme.find(("nothing.ttf",)) is None
    finally:
        theme.find.cache_clear()
        theme._installed.cache_clear()
