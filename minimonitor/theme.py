# SPDX-License-Identifier: GPL-3.0-or-later
"""Palette (GitHub-like dark surfaces, Shotoshot accents) and fonts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

BG = "#0d1117"
CARD = "#161b22"
TRACK = "#1c232c"
BORDER = "#283039"
TEXT = "#e6edf3"
LABEL = "#8b98a5"

GREEN = "#40C780"
RED = "#ED4F5C"
BLUE = "#5099F4"
YELLOW = "#FAC042"

FONT_DIR = Path(r"C:\Windows\Fonts")
MONO = "consolab.ttf"  # every number uses a fixed-width font
SANS = "seguisb.ttf"


@lru_cache(maxsize=None)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def mono(size: int) -> ImageFont.FreeTypeFont:
    return font(MONO, size)


def sans(size: int) -> ImageFont.FreeTypeFont:
    return font(SANS, size)
