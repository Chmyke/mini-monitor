# SPDX-License-Identifier: GPL-3.0-or-later
"""Demo frames with made-up values, for the README and the website.

Uses the real renderer and the real animation code (ring fill, lerp, breathing),
driven by a scripted clock, so the pictures show exactly what the screen does.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from . import theme
from .app import Gauge, pulse, smooth
from .i18n import Texts
from .pc import Snapshot
from .render import Ring, View, render, scene_for
from .usage import Window

FPS = 25
SECONDS = 6.0
NOW = datetime(2026, 10, 17, 14, 0, tzinfo=timezone.utc)
SESSION = Window(43, NOW + timedelta(hours=1, minutes=29))
WEEK = Window(15, NOW + timedelta(days=3, hours=22, minutes=10))
SESSION_LATER = Window(47, SESSION.resets_at)  # a new reading, to show the glow
SESSION_UPDATE_AT = 3.5
MB = 1_000_000

# One PC sample per second, as the app reads them.
SAMPLES = [
    Snapshot(52, 31, 14, 40.6, 63.7, 40, 1.9 * MB, 140_000),
    Snapshot(53, 37, 18, 40.8, 63.7, 40, 2.4 * MB, 180_000),
    Snapshot(54, 58, 27, 41.2, 63.7, 40, 3.1 * MB, 220_000),
    Snapshot(55, 44, 22, 41.0, 63.7, 40, 2.2 * MB, 160_000),
    Snapshot(54, 35, 16, 40.9, 63.7, 40, 1.6 * MB, 120_000),
    Snapshot(54, 37, 18, 41.0, 63.7, 40, 2.4 * MB, 180_000),
]


def frames(texts: Texts, gpu_label: str = "GPU 4080 S", size: tuple[int, int] = (480, 320)) -> list[Image.Image]:
    scene = scene_for(size)
    session, week = Gauge(), Gauge()
    shown_pc = None
    out = []
    dt = 1 / FPS
    for i in range(round(SECONDS * FPS)):
        t = i * dt
        session_window = SESSION_LATER if t >= SESSION_UPDATE_AT else SESSION
        session.set(session_window.percent, t)
        week.set(WEEK.percent, t)
        shown_pc = smooth(shown_pc, SAMPLES[min(int(t), len(SAMPLES) - 1)], dt)
        out.append(render(View(
            now=NOW + timedelta(seconds=t), pulse=pulse(t), live=True,
            session=Ring(session_window, session.shown(t), session.glow(t), theme.BLUE, texts.session),
            week=Ring(WEEK, week.shown(t), week.glow(t), theme.GREEN, texts.week),
            pc=shown_pc, texts=texts, gpu_label=gpu_label,
        ), scene))
    return out


def write_demo(directory: str, texts: Texts, lang: str, scale: int = 1,
               size: tuple[int, int] = (480, 320)) -> list[Path]:
    """Writes screen-<lang>.png (a settled frame) and screen-<lang>.webp (the animation).

    Another size than 480x320 adds it to the names: screen-<lang>-320x480.png.

    scale > 1 enlarges every pixel into a square block, so the pictures stay sharp on a web page.
    """
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    images = frames(texts, size=size)
    suffix = "" if size == (480, 320) else f"-{size[0]}x{size[1]}"
    if scale > 1:
        images = [im.resize((im.width * scale, im.height * scale), Image.NEAREST) for im in images]
    still = out_dir / f"screen-{lang}{suffix}.png"
    images[round(3.2 * FPS)].save(still, optimize=True)  # rings full, before the glow
    animation = out_dir / f"screen-{lang}{suffix}.webp"
    images[0].save(animation, save_all=True, append_images=images[1:], duration=round(1000 / FPS),
                   loop=0, lossless=True, method=6)
    return [still, animation]
