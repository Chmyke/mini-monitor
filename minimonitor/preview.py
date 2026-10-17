"""One frame with live data, written to a PNG: checks the layout without the screen."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from . import theme, usage
from .app import fresh
from .pc import PcSampler
from .render import Ring, View, render


def write_preview(path: str) -> None:
    sampler = PcSampler()
    time.sleep(1)  # CPU and network rates need a measurement interval
    now = datetime.now(timezone.utc)
    latest = usage.fetch()
    s = fresh(latest.session, now) if latest else None
    w = fresh(latest.week, now) if latest else None
    view = View(
        now=now, pulse=1.0, live=s is not None or w is not None,
        session=Ring(s, s.percent if s else 0, 0, theme.BLUE, "SESSION 5 H"),
        week=Ring(w, w.percent if w else 0, 0, theme.GREEN, "SEMAINE"),
        pc=sampler.sample(),
    )
    render(view).save(path)
