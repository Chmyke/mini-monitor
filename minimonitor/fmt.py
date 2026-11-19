# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure formatting and threshold rules (no I/O, fully unit-tested)."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import theme
from .i18n import FR, Texts

# Usage percentages at which the accent turns more aggressive.
AMBER_FROM = 75
RED_FROM = 90
# GPU temperature thresholds, in degrees Celsius.
GPU_AMBER_FROM = 75
GPU_RED_FROM = 85


def severity_color(percent: float | None, normal: str) -> str:
    if percent is None:
        return theme.LABEL
    if percent >= RED_FROM:
        return theme.RED
    if percent >= AMBER_FROM:
        return theme.YELLOW
    return normal


def gpu_temp_color(celsius: float | None) -> str:
    if celsius is None:
        return theme.LABEL
    if celsius >= GPU_RED_FROM:
        return theme.RED
    if celsius >= GPU_AMBER_FROM:
        return theme.YELLOW
    return theme.GREEN


def remaining(resets_at: datetime | None, now: datetime, texts: Texts = FR) -> str:
    """Time left before a reset: '42 min', '1h29', '3j 22h' ('3d 22h' in English)."""
    if resets_at is None:
        return "?"
    left = resets_at - now
    if left <= timedelta(0):
        return "?"
    minutes = int(left.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}"
    days, hours = divmod(hours, 24)
    return f"{days}{texts.day} {hours}h"


def rate(bytes_per_second: float, texts: Texts = FR) -> str:
    """Network rate: '180 Ko/s', '2,4 Mo/s' in French, '2.4 MB/s' in English."""
    kb = bytes_per_second / 1000
    if kb < 1000:
        return f"{kb:.0f} {texts.kilobytes_per_s}"
    mb = kb / 1000
    if mb < 100:
        return f"{mb:.1f}".replace(".", texts.decimal) + f" {texts.megabytes_per_s}"
    return f"{mb:.0f} {texts.megabytes_per_s}"


def percent(value: float | None) -> str:
    return "?" if value is None else f"{round(value)}%"


def short_gpu_name(name: str | None) -> str:
    """'NVIDIA GeForce RTX 4080 SUPER' -> 'GPU 4080 S': fits the row label."""
    if not name:
        return "GPU"
    words = [w for w in name.replace("NVIDIA", "").replace("GeForce", "").split()
             if w.upper() not in ("RTX", "GTX", "AMD", "RADEON", "INTEL", "ARC")]
    words = ["S" if w.upper() == "SUPER" else w for w in words]
    return " ".join(["GPU", *words])[:14]


def split(total: float | None, shares: tuple[tuple[str, float], ...]) -> tuple[tuple[str, float], ...]:
    """Each application's part of a bar, as fractions of its value (sum at most 1).

    The per-process counters and the machine total are read differently and do not add up
    exactly: when the named applications exceed the total they share the whole bar.
    """
    if not total or total <= 0 or not shares:
        return ()
    fractions = [(name, max(value, 0) / total) for name, value in shares]
    covered = sum(f for _, f in fractions)
    if covered > 1:
        fractions = [(name, f / covered) for name, f in fractions]
    return tuple((name, f) for name, f in fractions if f > 0)


def assign_colors(previous: dict[str, str], names: list[str], palette: tuple[str, ...]) -> dict[str, str]:
    """A colour per application that stays the same while it stays on screen.

    Names keep their previous colour; new ones take the first free colour; past the palette
    they get none (drawn with the rest of the bar).
    """
    kept = {name: previous[name] for name in names if name in previous}
    free = [color for color in palette if color not in kept.values()]
    for name in names:
        if name not in kept and free:
            kept[name] = free.pop(0)
    return kept

