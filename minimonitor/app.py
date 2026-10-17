# SPDX-License-Identifier: GPL-3.0-or-later
"""Main loop: samples the data, animates, and sends only what changed to the screen.

A full frame takes about 1.2 s over USB; a 120x40 patch about 40 ms (measured
2026-10-17). So the frame is redrawn in memory at every tick, compared region by
region with what the screen shows, and only the changed rectangles are sent.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, fields
from datetime import datetime, timezone

from PIL import Image, ImageChops

from . import fmt, theme, usage
from .i18n import FR, Texts
from .pc import PcSampler, Snapshot
from .render import REGIONS, Ring, View, render

TICK = 0.1  # seconds between frames
PC_PERIOD = 1.0
USAGE_PERIOD = 300.0
RING_FILL_SECONDS = 1.2
GLOW_SECONDS = 1.5
BREATH_SECONDS = 2.4
SMOOTH_SECONDS = 0.2  # time constant of the PC values' lerp: ~95 % of the way in 0.6 s
SNAP = 0.05


def changed_boxes(previous: Image.Image | None, current: Image.Image,
                  regions: dict[str, tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Smallest rectangles (x0, y0, x1, y1 exclusive) to resend, one per changed region."""
    if previous is None:
        return [(0, 0, *current.size)]
    boxes = []
    for x0, y0, x1, y1 in regions.values():
        box = (x0, y0, x1 + 1, y1 + 1)
        diff = ImageChops.difference(previous.crop(box), current.crop(box)).getbbox()
        if diff:
            boxes.append((x0 + diff[0], y0 + diff[1], x0 + diff[2], y0 + diff[3]))
    return boxes


def ease_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


@dataclass
class Gauge:
    """Animated value of one Claude ring: fills from its old value to its new one."""
    start: float = 0.0
    target: float = 0.0
    changed_at: float = -1e9
    has_value: bool = False

    def set(self, value: float | None, now: float) -> None:
        if value is None:
            self.has_value = False
            return
        if not self.has_value or value != self.target:
            self.start = self.shown(now) if self.has_value else 0.0
            self.target = value
            self.changed_at = now
            self.has_value = True

    def shown(self, now: float) -> float:
        return self.start + (self.target - self.start) * ease_out((now - self.changed_at) / RING_FILL_SECONDS)

    def glow(self, now: float) -> float:
        age = now - self.changed_at
        return max(0.0, 1 - age / GLOW_SECONDS) if self.has_value else 0.0


def approach(current: float | None, target: float | None, dt: float, tau: float = SMOOTH_SECONDS) -> float | None:
    """Exponential lerp toward target; snaps once close so the frame stops changing."""
    if current is None or target is None:
        return target
    value = target + (current - target) * math.exp(-max(dt, 0.0) / tau)
    return target if abs(value - target) < SNAP else value


def smooth(shown: Snapshot | None, target: Snapshot | None, dt: float) -> Snapshot | None:
    """PC values glide to each new sample instead of jumping."""
    if shown is None or target is None:
        return target
    return Snapshot(**{f.name: approach(getattr(shown, f.name), getattr(target, f.name), dt)
                       for f in fields(Snapshot)})


def fresh(window: usage.Window | None, now: datetime) -> usage.Window | None:
    """A window whose reset time has passed holds a stale percentage: treat it as unknown."""
    if window is None or (window.resets_at is not None and window.resets_at <= now):
        return None
    return window


class UsagePoller:
    """Fetches Claude usage in the background so a slow network never freezes the screen."""

    def __init__(self, period: float = USAGE_PERIOD):
        self._period = period
        self._lock = threading.Lock()
        self._usage: usage.Usage | None = None
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            result = usage.fetch()
            with self._lock:
                self._usage = result
            self._wake.wait(self._period)
            self._wake.clear()

    def latest(self) -> usage.Usage | None:
        with self._lock:
            return self._usage

    def refresh_now(self) -> None:
        self._wake.set()


def run(screen, brightness: int = 60, texts: Texts = FR) -> None:
    screen.brightness(brightness)
    sampler = PcSampler()
    gpu_label = fmt.short_gpu_name(sampler.gpu_name)
    poller = UsagePoller()
    session, week = Gauge(), Gauge()
    shown: Image.Image | None = None
    snapshot, displayed, next_pc = None, None, 0.0
    t0 = previous_tick = time.monotonic()
    while True:
        tick = time.monotonic()
        if tick >= next_pc:
            snapshot, next_pc = sampler.sample(), tick + PC_PERIOD
        displayed = smooth(displayed, snapshot, tick - previous_tick)
        previous_tick = tick

        now = datetime.now(timezone.utc)
        latest = poller.latest()
        s = fresh(latest.session, now) if latest else None
        w = fresh(latest.week, now) if latest else None
        if latest and (latest.session and s is None or latest.week and w is None):
            poller.refresh_now()
        session.set(s.percent if s else None, tick)
        week.set(w.percent if w else None, tick)

        view = View(
            now=now,
            pulse=0.5 - 0.5 * math.cos(2 * math.pi * (tick - t0) / BREATH_SECONDS),
            live=s is not None or w is not None,
            session=Ring(s, session.shown(tick), session.glow(tick), theme.BLUE, texts.session),
            week=Ring(w, week.shown(tick), week.glow(tick), theme.GREEN, texts.week),
            pc=displayed,
            texts=texts,
            gpu_label=gpu_label,
        )
        frame = render(view)
        for x0, y0, x1, y1 in changed_boxes(shown, frame, REGIONS):
            screen.blit(frame.crop((x0, y0, x1, y1)), x0, y0)
        shown = frame
        time.sleep(max(0.0, TICK - (time.monotonic() - tick)))
