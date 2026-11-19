# SPDX-License-Identifier: GPL-3.0-or-later
"""Layout "Claude en vedette": draws a full frame from a View, at any screen size.

Two layouts are designed in pixels: landscape (480x320, Claude left, PC right) and
portrait (320x480, Claude on top). A Scene fits the right one to the actual screen:
scaled to fill it, centred, and shrunk to fit inside the circle of a round screen.
Everything is drawn at the final size, so text stays sharp at any scale.

The renderer only draws; it computes nothing. Regions name the rectangles that may
change between frames, so the app can send only those over USB.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw

from . import fmt, theme
from .i18n import Texts
from .pc import Snapshot
from .usage import Window

Box = tuple[int, int, int, int]  # x0, y0, x1, y1, inclusive

RING_DIAMETER = 128
RING_STROKE = 11
# Width of the ring's hole at the height of the note's last line, minus a margin.
NOTE_WIDTH = 86
BAR_HEIGHT = 6
DOT = (18, 20, 26, 28)
# PC rows, as offsets from the top of the PC column: baselines, bars, and the
# rectangle each row may change in (top, bottom).
# PC rows, as baselines from the top of the PC column, `pc_step` apart: the bar sits BAR_DY
# below its row and the legend (who fills the bar) LEGEND_DY below; each row may change within
# ROW_REGION of it. The network line (down and up, no label: arrows and units say it) closes it.
ROWS = ("gpu", "cpu", "mem", "disk")
FIRST_ROW_Y = 24
BAR_DY, LEGEND_DY = 8, 26
ROW_REGION = (-18, 32)
NET_DY = 58  # from the last row
NET_REGION = (-16, 6)


@dataclass(frozen=True)
class Layout:
    size: tuple[int, int]
    claude_card: Box
    pc_card: Box
    rings: tuple[tuple[int, int], tuple[int, int]]  # session and week centres
    pc_x: tuple[int, int]  # left and right edges of the PC rows
    pc_top: int
    pc_step: int  # between two PC rows: wider where the column is taller

    @property
    def rows_y(self) -> dict[str, int]:
        return {name: FIRST_ROW_Y + i * self.pc_step for i, name in enumerate(ROWS)}

    @property
    def net_y(self) -> int:
        return self.rows_y[ROWS[-1]] + NET_DY

    @property
    def regions(self) -> dict[str, Box]:
        x0, y0, x1, y1 = DOT
        regions = {"dot": (x0 - 4, y0 - 4, x1 + 4, y1 + 4)}
        r = RING_DIAMETER // 2 + 2
        for name, (cx, cy) in zip(("session", "week"), self.rings):
            regions[name] = (cx - r, cy - r, cx + r, cy + r)
        left, right = self.pc_x[0] - 4, self.pc_x[1] + 4
        lines = [*((name, y, ROW_REGION) for name, y in self.rows_y.items()), ("net", self.net_y, NET_REGION)]
        for name, y, (top, bottom) in lines:
            regions[name] = (left, self.pc_top + y + top, right, self.pc_top + y + bottom)
        return regions


LANDSCAPE = Layout(
    size=(480, 320), claude_card=(8, 8, 227, 311), pc_card=(236, 8, 471, 311),
    rings=((118, 110), (118, 246)), pc_x=(248, 460), pc_top=8, pc_step=64,
)
PORTRAIT = Layout(
    size=(320, 480), claude_card=(8, 8, 311, 183), pc_card=(8, 192, 311, 471),
    rings=((84, 108), (236, 108)), pc_x=(20, 299), pc_top=199, pc_step=56,
)


@dataclass(frozen=True)
class Scene:
    """A layout fitted to a screen: design pixels -> screen pixels."""
    layout: Layout
    size: tuple[int, int]
    scale: float
    offset: tuple[float, float]
    regions: dict[str, Box] = field(compare=False)

    def x(self, v: float) -> int:
        return round(self.offset[0] + v * self.scale)

    def y(self, v: float) -> int:
        return round(self.offset[1] + v * self.scale)

    def box(self, b: Box) -> Box:
        return self.x(b[0]), self.y(b[1]), self.x(b[2]), self.y(b[3])

    def px(self, v: float) -> int:
        """A length (font size, stroke, radius), never below one pixel."""
        return max(1, round(v * self.scale))


@lru_cache(maxsize=16)
def scene_for(size: tuple[int, int], round_screen: bool = False) -> Scene:
    width, height = size
    layout = LANDSCAPE if width >= height else PORTRAIT
    lw, lh = layout.size
    if round_screen:  # the whole rectangle, corners included, inside the circle
        scale = min(width, height) / math.hypot(lw, lh)
    else:
        scale = min(width / lw, height / lh)
    ox, oy = (width - lw * scale) / 2, (height - lh * scale) / 2
    regions = {}
    for name, (x0, y0, x1, y1) in layout.regions.items():
        # One more pixel around each region: antialiasing may spill over after scaling.
        regions[name] = (max(0, math.floor(ox + x0 * scale) - 1), max(0, math.floor(oy + y0 * scale) - 1),
                         min(width - 1, math.ceil(ox + x1 * scale) + 1),
                         min(height - 1, math.ceil(oy + y1 * scale) + 1))
    return Scene(layout, size, scale, (ox, oy), regions)


DEFAULT_SIZE = LANDSCAPE.size


@dataclass(frozen=True)
class Ring:
    window: Window | None  # None: unknown, shown as a grey '?'
    shown: float  # percent currently drawn (animated toward window.percent)
    glow: float  # 0..1, brief highlight after a value change
    accent: str
    title: str
    note: str | None = None  # replaces the time left, e.g. the command that signs in again


@dataclass(frozen=True)
class Split:
    """Who fills one bar: computed by the app, only drawn here."""
    parts: tuple[tuple[float, str], ...] = ()  # (fraction of the bar's value, colour), left to right
    legend: tuple[tuple[str, str], ...] = ()  # (application, colour), the biggest first


@dataclass(frozen=True)
class Apps:
    gpu: Split = Split()
    cpu: Split = Split()
    memory: Split = Split()
    disk: tuple[str, str, str] | None = None  # who moves the most bytes: application, colour, rate


@dataclass(frozen=True)
class View:
    now: datetime
    pulse: float  # 0..1, breathing dot opacity
    live: bool  # Claude numbers are fresh
    session: Ring  # first ring: the session limit, or the model limit on plans without one
    week: Ring
    pc: Snapshot | None
    texts: Texts
    gpu_label: str  # e.g. 'GPU 4080 S'
    disk_label: str = "C:"
    apps: Apps | None = None  # None: whole bars, no names


def mix(a: str, b: str, t: float) -> tuple[int, int, int]:
    ca, cb = _rgb(a), _rgb(b)
    return tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=256)
def _ring_image(percent_tenths: int, color: str, diameter: int, stroke: int) -> Image.Image:
    """Anti-aliased ring, drawn 4x larger then reduced."""
    scale = 4
    size = diameter * scale
    stroke *= scale
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
    return img.resize((diameter, diameter), Image.LANCZOS)


def _ring(img: Image.Image, d: ImageDraw.ImageDraw, s: Scene, ring: Ring, center: tuple[int, int],
          now: datetime, texts: Texts) -> None:
    known = ring.window is not None
    color = fmt.severity_color(ring.window.percent, ring.accent) if known else theme.LABEL
    shown = ring.shown if known else 0
    diameter = s.px(RING_DIAMETER)
    cx, cy = center
    img.paste(_ring_image(round(shown * 10), color, diameter, s.px(RING_STROKE)),
              (s.x(cx) - diameter // 2, s.y(cy) - diameter // 2))
    if ring.note:  # no number to show: the title and what to do fill the ring's hole
        d.text((s.x(cx), s.y(cy - 20)), ring.title, font=theme.sans(s.px(11)), fill=theme.LABEL, anchor="mm")
        lines = ring.note.rsplit(" ", 1) if " " in ring.note else [ring.note]
        for i, line in enumerate(lines):
            d.text((s.x(cx), s.y(cy + 2 + 18 * i)), line, fill=theme.TEXT, anchor="mm",
                   font=_fitted_mono(d, line, s.px(15), s.px(NOTE_WIDTH)))
        return
    number = fmt.percent(shown) if known else "?"  # counts along with the ring fill
    number_color = mix(theme.TEXT, color, ring.glow) if known else theme.LABEL
    d.text((s.x(cx), s.y(cy - 10)), number, font=theme.mono(s.px(30)), fill=number_color, anchor="mm")
    d.text((s.x(cx), s.y(cy + 14)), ring.title, font=theme.sans(s.px(11)), fill=theme.LABEL, anchor="mm")
    left = fmt.remaining(ring.window.resets_at, now, texts) if known else "?"
    d.text((s.x(cx), s.y(cy + 29)), left, font=theme.mono(s.px(13)),
           fill=theme.TEXT if known else theme.LABEL, anchor="mm")


def _fitted_mono(d: ImageDraw.ImageDraw, text: str, size: int, width: int):
    """The largest monospace font, up to `size`, that keeps `text` inside the ring's hole."""
    while size > 6 and d.textlength(text, font=theme.mono(size)) > width:
        size -= 1
    return theme.mono(size)


class _Pc:
    """The PC column: rows of label, value, bar and legend, positioned by the layout."""

    def __init__(self, img: Image.Image, d: ImageDraw.ImageDraw, s: Scene):
        self.img, self.d, self.s = img, d, s
        self.x0, self.x1 = s.x(s.layout.pc_x[0]), s.x(s.layout.pc_x[1])

    def y(self, offset: int) -> int:
        return self.s.y(self.s.layout.pc_top + offset)

    def bar(self, offset: int, percent: float | None, color: str, split: Split = Split()) -> None:
        """The track, then the value: whole in `color`, or cut into each application's part."""
        y, h, radius = self.y(offset), self.s.px(BAR_HEIGHT), self.s.px(3)
        self.d.rounded_rectangle((self.x0, y, self.x1, y + h - 1), radius=radius, fill=theme.TRACK)
        if percent is None or percent <= 0:
            return
        width = max(h, round((self.x1 - self.x0) * min(percent, 100) / 100))
        if not split.parts:
            self.d.rounded_rectangle((self.x0, y, self.x0 + width, y + h - 1), radius=radius, fill=color)
            return
        strip = Image.new("RGB", (width + 1, h), theme.OTHERS)  # what no named application covers
        draw, left = ImageDraw.Draw(strip), 0.0
        for fraction, part_color in split.parts:
            right = left + width * fraction
            if round(right) > round(left):
                draw.rectangle((round(left), 0, round(right) - 1, h - 1), fill=part_color)
            left = right
        mask = Image.new("L", strip.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, h - 1), radius=radius, fill=255)
        self.img.paste(strip, (self.x0, y), mask)

    def row(self, offset: int, label: str, value: str, color: str = theme.TEXT, size: int = 16) -> None:
        y = self.y(offset)
        self.d.text((self.x0, y), label.upper(), font=theme.sans(self.s.px(12)), fill=theme.LABEL, anchor="ls")
        self.d.text((self.x1, y), value, font=theme.mono(self.s.px(size)), fill=color, anchor="rs")

    def legend(self, offset: int, entries: tuple[tuple[str, str], ...], value: str | None = None) -> None:
        """Up to two applications, each with its colour dot, side by side; or one, and its value
        kept whole at the right edge (the disk's rate)."""
        y, font = self.y(offset), theme.sans(self.s.px(11))
        dot, gap = self.s.px(6), self.s.px(4)
        width = (self.x1 - self.x0) // 2
        if value is not None:
            value_font = theme.mono(self.s.px(12))
            self.d.text((self.x1, y), value, font=value_font, fill=theme.TEXT, anchor="rs")
            width = self.x1 - self.x0 - round(value_font.getlength(value))
        for i, (name, color) in enumerate(entries[:1 if value is not None else 2]):
            x = self.x0 + i * width
            self.d.ellipse((x, y - dot - self.s.px(1), x + dot, y - self.s.px(1)), fill=color)
            text = _fit(self.d, name, font, width - dot - gap - self.s.px(6))
            self.d.text((x + dot + gap, y), text, font=font, fill=theme.TEXT, anchor="ls")

    def net(self, down: str, up: str) -> None:
        font, y = theme.mono(self.s.px(16)), self.y(self.s.layout.net_y)
        self.d.text((self.x0, y), down, font=font, fill=theme.TEXT, anchor="ls")
        self.d.text((self.x1, y), up, font=font, fill=theme.LABEL, anchor="rs")


def _fit(d: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    """`text`, cut with an ellipsis if it is wider than `width` pixels."""
    if d.textlength(text, font=font) <= width:
        return text
    while len(text) > 1 and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _pc(img: Image.Image, d: ImageDraw.ImageDraw, s: Scene, view: View) -> None:
    pc, t, col = view.pc, view.texts, _Pc(img, d, s)
    if pc is None:
        for offset in (*s.layout.rows_y.values(), s.layout.net_y):
            col.row(offset, "…", "?", theme.LABEL)
        return
    apps, rows = view.apps or Apps(), s.layout.rows_y

    y = rows["gpu"]
    col.row(y, view.gpu_label, fmt.percent(pc.gpu_util), fmt.severity_color(pc.gpu_util, theme.TEXT))
    temp = "?" if pc.gpu_temp is None else f"{pc.gpu_temp:.0f}°"
    value_font = theme.mono(s.px(16))
    d.text((col.x1 - value_font.getlength(fmt.percent(pc.gpu_util)) - s.px(12), col.y(y)), temp,
           font=value_font, fill=fmt.gpu_temp_color(pc.gpu_temp), anchor="rs")
    col.bar(y + BAR_DY, pc.gpu_util, fmt.severity_color(pc.gpu_util, theme.BLUE), apps.gpu)
    col.legend(y + LEGEND_DY, apps.gpu.legend)

    y = rows["cpu"]
    col.row(y, "CPU", fmt.percent(pc.cpu), fmt.severity_color(pc.cpu, theme.TEXT))
    col.bar(y + BAR_DY, pc.cpu, fmt.severity_color(pc.cpu, theme.BLUE), apps.cpu)
    col.legend(y + LEGEND_DY, apps.cpu.legend)

    mem_pct = 100 * pc.mem_used_gb / pc.mem_total_gb if pc.mem_total_gb else None
    y = rows["mem"]
    col.row(y, t.memory, f"{pc.mem_used_gb:.0f}/{pc.mem_total_gb:.0f} {t.gigabytes}",
            fmt.severity_color(mem_pct, theme.TEXT))
    col.bar(y + BAR_DY, mem_pct, fmt.severity_color(mem_pct, theme.BLUE), apps.memory)
    col.legend(y + LEGEND_DY, apps.memory.legend)

    y = rows["disk"]
    col.row(y, f"{t.disk} {view.disk_label}", fmt.percent(pc.disk), fmt.severity_color(pc.disk, theme.TEXT))
    col.bar(y + BAR_DY, pc.disk, fmt.severity_color(pc.disk, theme.BLUE))
    if apps.disk:  # the disk bar is its filling; the legend says who reads or writes the most
        name, color, rate = apps.disk
        col.legend(y + LEGEND_DY, ((name, color),), rate)

    col.net("↓" + fmt.rate(pc.net_down, t), "↑" + fmt.rate(pc.net_up, t))


def render(view: View, scene: Scene | None = None) -> Image.Image:
    s = scene or scene_for(DEFAULT_SIZE)
    img = Image.new("RGB", s.size, theme.BG)
    d = ImageDraw.Draw(img)
    for card in (s.layout.claude_card, s.layout.pc_card):
        d.rounded_rectangle(s.box(card), radius=s.px(8), fill=theme.CARD, outline=theme.BORDER, width=s.px(1))

    dot = mix(theme.CARD, theme.GREEN, 0.35 + 0.65 * view.pulse) if view.live else _rgb(theme.LABEL)
    d.ellipse(s.box(DOT), fill=dot)
    d.text((s.x(36), s.y(30)), "CLAUDE", font=theme.sans(s.px(13)), fill=theme.LABEL, anchor="ls")

    _ring(img, d, s, view.session, s.layout.rings[0], view.now, view.texts)
    _ring(img, d, s, view.week, s.layout.rings[1], view.now, view.texts)
    _pc(img, d, s, view)
    return img
