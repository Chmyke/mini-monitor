from datetime import datetime, timedelta, timezone

from PIL import Image, ImageChops, ImageDraw

from minimonitor import theme
from minimonitor.pc import Snapshot
from minimonitor.render import HEIGHT, REGIONS, WIDTH, Ring, View, render
from minimonitor.usage import Window

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def view(pct: float | None, pc: Snapshot | None, pulse: float, glow: float) -> View:
    w = Window(pct, NOW + timedelta(hours=1, minutes=29)) if pct is not None else None
    return View(
        now=NOW, pulse=pulse, live=w is not None,
        session=Ring(w, pct or 0, glow, theme.BLUE, "SESSION 5 H"),
        week=Ring(w, pct or 0, glow, theme.GREEN, "SEMAINE"),
        pc=pc,
    )


BUSY = Snapshot(91, 100, 100, 62.9, 63.9, 99, 250e6, 250e6)
IDLE = Snapshot(30, 0, 0, 1, 63.9, 0, 0, 0)


def test_frame_size():
    assert render(view(43, IDLE, 0, 0)).size == (WIDTH, HEIGHT)


def test_everything_that_changes_stays_inside_regions():
    """Partial updates are only correct if no pixel outside REGIONS ever changes."""
    frames = [
        render(view(100, BUSY, 1, 1)),
        render(view(0, IDLE, 0, 0)),
        render(view(None, None, 0.5, 0)),
        render(view(77.7, BUSY, 0.2, 0.5)),
    ]
    mask = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(mask)
    for box in REGIONS.values():
        draw.rectangle(box, fill=0)
    black = Image.new("RGB", (WIDTH, HEIGHT))
    base = Image.composite(frames[0], black, mask)
    for frame in frames[1:]:
        assert ImageChops.difference(base, Image.composite(frame, black, mask)).getbbox() is None


def test_regions_inside_the_screen():
    for x0, y0, x1, y1 in REGIONS.values():
        assert 0 <= x0 < x1 < WIDTH and 0 <= y0 < y1 < HEIGHT
