# SPDX-License-Identifier: GPL-3.0-or-later
from datetime import datetime, timedelta, timezone

import pytest

from minimonitor import fmt, theme
from minimonitor.i18n import EN

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("delta, text", [
    (timedelta(minutes=42, seconds=30), "42 min"),
    (timedelta(hours=1, minutes=29), "1h29"),
    (timedelta(hours=5), "5h00"),
    (timedelta(days=3, hours=22, minutes=10), "3j 22h"),
    (timedelta(seconds=-1), "?"),
])
def test_remaining(delta, text):
    assert fmt.remaining(NOW + delta, NOW) == text


def test_remaining_unknown():
    assert fmt.remaining(None, NOW) == "?"


@pytest.mark.parametrize("bps, text", [
    (180_000, "180 Ko/s"),
    (2_400_000, "2,4 Mo/s"),
    (250_000_000, "250 Mo/s"),
])
def test_rate(bps, text):
    assert fmt.rate(bps) == text


@pytest.mark.parametrize("pct, color", [
    (74.9, theme.BLUE), (75, theme.YELLOW), (89.9, theme.YELLOW), (90, theme.RED), (None, theme.LABEL),
])
def test_severity(pct, color):
    assert fmt.severity_color(pct, theme.BLUE) == color


@pytest.mark.parametrize("temp, color", [(60, theme.GREEN), (75, theme.YELLOW), (85, theme.RED), (None, theme.LABEL)])
def test_gpu_temp_color(temp, color):
    assert fmt.gpu_temp_color(temp) == color


def test_percent():
    assert fmt.percent(57.6) == "58%"
    assert fmt.percent(None) == "?"


def test_english_units():
    assert fmt.remaining(NOW + timedelta(days=3, hours=22), NOW, EN) == "3d 22h"
    assert fmt.rate(2_400_000, EN) == "2.4 MB/s"
    assert fmt.rate(180_000, EN) == "180 kB/s"


@pytest.mark.parametrize("name, label", [
    ("NVIDIA GeForce RTX 4080 SUPER", "GPU 4080 S"),
    ("NVIDIA GeForce RTX 3060 Ti", "GPU 3060 Ti"),
    ("NVIDIA GeForce GTX 1080", "GPU 1080"),
    (None, "GPU"),
])
def test_short_gpu_name(name, label):
    assert fmt.short_gpu_name(name) == label
