"""Pure formatting and threshold rules (no I/O, fully unit-tested)."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import theme

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


def remaining(resets_at: datetime | None, now: datetime) -> str:
    """Time left before a reset: '42 min', '1h29', '3j 22h'."""
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
    return f"{days}j {hours}h"


def rate(bytes_per_second: float) -> str:
    """Network rate in French units with a decimal comma: '180 Ko/s', '2,4 Mo/s'."""
    kb = bytes_per_second / 1000
    if kb < 1000:
        return f"{kb:.0f} Ko/s"
    mb = kb / 1000
    if mb < 100:
        return f"{mb:.1f} Mo/s".replace(".", ",")
    return f"{mb:.0f} Mo/s"


def percent(value: float | None) -> str:
    return "?" if value is None else f"{round(value)}%"
