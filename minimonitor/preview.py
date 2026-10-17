# SPDX-License-Identifier: GPL-3.0-or-later
"""One frame with live data, written to a PNG: checks the layout without the screen."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from . import fmt, theme, usage
from .i18n import FR, Texts
from .app import fresh
from .pc import PcSampler, disk_label
from .render import Ring, View, render, scene_for


def write_preview(path: str, texts: Texts = FR, size: tuple[int, int] = (480, 320),
                  disk_path: str | None = None) -> None:
    sampler = PcSampler(disk_path)
    time.sleep(1)  # CPU and network rates need a measurement interval
    now = datetime.now(timezone.utc)
    latest = usage.fetch()
    s = fresh(latest.session, now) if latest else None
    w = fresh(latest.week, now) if latest else None
    view = View(
        now=now, pulse=1.0, live=s is not None or w is not None,
        session=Ring(s, s.percent if s else 0, 0, theme.BLUE, texts.session),
        week=Ring(w, w.percent if w else 0, 0, theme.GREEN, texts.week),
        pc=sampler.sample(),
        texts=texts,
        gpu_label=fmt.short_gpu_name(sampler.gpu_name),
        disk_label=disk_label(sampler.disk_path),
    )
    render(view, scene_for(size)).save(path)
