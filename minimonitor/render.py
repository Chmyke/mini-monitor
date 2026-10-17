"""Layout A, "Claude en vedette": draws a full 480x320 frame from a View.

The renderer only draws; it computes nothing. Regions name the rectangles that
may change between frames, so the app can send only those over USB.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw

from . import fmt, theme
from .pc import Snapshot
from .usage import Window

WIDTH, HEIGHT = 480, 320

LEFT_CARD = (8, 8, 227, 311)
RIGHT_CARD = (236, 8, 471, 311)
RING_DIAMETER = 128
RING_STROKE = 11
RING_CENTER_X = 118
RING_CENTERS_Y = (110, 246)

# Rectangles that may change after the first frame (x0, y0, x1, y1), inclusive.
REGIONS = {
    "dot": (14, 16, 30, 32),
    "session": (40, 44, 196, 176),
    "week": (40, 180, 196, 310),
    "gpu": (244, 14, 464, 78),
    "cpu": (244, 86, 464, 126),
    "mem": (244, 134, 464, 174),
    "disk": (244, 182, 464, 222),
    "net": (244, 232, 464, 300),
}

ROW_X0, ROW_X1 = 248, 460
BAR_HEIGHT = 6


@dataclass(frozen=True)
class Ring:
    window: Window | None  # None: unknown, shown as a grey '?'
    shown: float  # percent currently drawn (animated toward window.percent)
    glow: float  # 0..1, brief highlight after a value change
    accent: str
    title: str


@dataclass(frozen=True)
class View:
    now: datetime
    pulse: float  # 0..1, breathing dot opacity
    live: bool  # Claude numbers are fresh
    session: Ring
    week: Ring
    pc: Snapshot | None


def mix(a: str, b: str, t: float) -> tuple[int, int, int]:
    ca, cb = _rgb(a), _rgb(b)
    return tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=256)
def _ring_image(percent_tenths: int, color: str) -> Image.Image:
    """Anti-aliased ring, drawn 4x larger then reduced."""
    scale = 4
    size = RING_DIAMETER * scale
    stroke = RING_STROKE * scale
    img = Image.new("RGB", (size, size), theme.CARD)
    d = ImageDraw.Draw(img)
    # PIL draws a wide outline inward from the box edge.
    box = (0, 0, size - 1, size - 1)
    d.ellipse(box, outline=theme.TRACK, width=stroke)
    sweep = 360 * min(max(percent_tenths / 1000, 0), 1)
    if sweep > 0:
        start, end = -90, -90 + sweep
        d.arc(box, start, end, fill=color, width=stroke)
        # Round caps.
        r = (size - stroke) / 2
        c = size / 2
        for angle in (start, end):
            a = math.radians(angle)
            x, y = c + r * math.cos(a), c + r * math.sin(a)
            d.ellipse((x - stroke / 2, y - stroke / 2, x + stroke / 2, y + stroke / 2), fill=color)
    return img.resize((RING_DIAMETER, RING_DIAMETER), Image.LANCZOS)


def _ring(img: Image.Image, d: ImageDraw.ImageDraw, ring: Ring, cy: int, now: datetime) -> None:
    known = ring.window is not None
    color = fmt.severity_color(ring.window.percent, ring.accent) if known else theme.LABEL
    shown = ring.shown if known else 0
    img.paste(_ring_image(round(shown * 10), color),
              (RING_CENTER_X - RING_DIAMETER // 2, cy - RING_DIAMETER // 2))
    number = fmt.percent(ring.window.percent) if known else "?"
    number_color = mix(theme.TEXT, color, ring.glow) if known else theme.LABEL
    d.text((RING_CENTER_X, cy - 10), number, font=theme.mono(30), fill=number_color, anchor="mm")
    d.text((RING_CENTER_X, cy + 14), ring.title, font=theme.sans(11), fill=theme.LABEL, anchor="mm")
    left = fmt.remaining(ring.window.resets_at, now) if known else "?"
    d.text((RING_CENTER_X, cy + 29), left, font=theme.mono(13), fill=theme.TEXT if known else theme.LABEL,
           anchor="mm")


def _bar(d: ImageDraw.ImageDraw, y: int, percent: float | None, color: str) -> None:
    d.rounded_rectangle((ROW_X0, y, ROW_X1, y + BAR_HEIGHT - 1), radius=3, fill=theme.TRACK)
    if percent is None or percent <= 0:
        return
    x1 = ROW_X0 + max(BAR_HEIGHT, round((ROW_X1 - ROW_X0) * min(percent, 100) / 100))
    d.rounded_rectangle((ROW_X0, y, x1, y + BAR_HEIGHT - 1), radius=3, fill=color)


def _row(d: ImageDraw.ImageDraw, y: int, label: str, value: str, color: str = theme.TEXT,
         size: int = 16) -> None:
    d.text((ROW_X0, y), label.upper(), font=theme.sans(12), fill=theme.LABEL, anchor="ls")
    d.text((ROW_X1, y), value, font=theme.mono(size), fill=color, anchor="rs")


def _pc(d: ImageDraw.ImageDraw, pc: Snapshot | None) -> None:
    unknown = "?"
    if pc is None:
        for y in (40, 108, 156, 204, 256):
            _row(d, y, "…", unknown, theme.LABEL)
        return
    temp = unknown if pc.gpu_temp is None else f"{pc.gpu_temp:.0f}°"
    _row(d, 40, "GPU 4080 S", temp, fmt.gpu_temp_color(pc.gpu_temp), size=26)
    _row(d, 62, "utilisation", fmt.percent(pc.gpu_util))
    _bar(d, 68, pc.gpu_util, fmt.severity_color(pc.gpu_util, theme.BLUE))

    _row(d, 108, "CPU", fmt.percent(pc.cpu))
    _bar(d, 116, pc.cpu, fmt.severity_color(pc.cpu, theme.BLUE))

    mem_pct = 100 * pc.mem_used_gb / pc.mem_total_gb if pc.mem_total_gb else None
    _row(d, 156, "Mémoire", f"{pc.mem_used_gb:.0f}/{pc.mem_total_gb:.0f} Go")
    _bar(d, 164, mem_pct, fmt.severity_color(mem_pct, theme.BLUE))

    _row(d, 204, "Disque C:", fmt.percent(pc.disk))
    _bar(d, 212, pc.disk, fmt.severity_color(pc.disk, theme.BLUE))

    _row(d, 256, "Réseau", "↓" + fmt.rate(pc.net_down))
    _row(d, 280, "", "↑" + fmt.rate(pc.net_up), theme.LABEL)


def render(view: View) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), theme.BG)
    d = ImageDraw.Draw(img)
    for card in (LEFT_CARD, RIGHT_CARD):
        d.rounded_rectangle(card, radius=8, fill=theme.CARD, outline=theme.BORDER)

    dot = mix(theme.CARD, theme.GREEN, 0.35 + 0.65 * view.pulse) if view.live else _rgb(theme.LABEL)
    d.ellipse((18, 20, 26, 28), fill=dot)
    d.text((36, 30), "CLAUDE", font=theme.sans(13), fill=theme.LABEL, anchor="ls")

    _ring(img, d, view.session, RING_CENTERS_Y[0], view.now)
    _ring(img, d, view.week, RING_CENTERS_Y[1], view.now)
    _pc(d, view.pc)
    return img
