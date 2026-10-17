# SPDX-License-Identifier: GPL-3.0-or-later
"""Palette (GitHub-like dark surfaces, Shotoshot accents) and fonts.

Fonts are looked up by file name in the usual font folders of Windows, Linux and
macOS, in order of preference; Pillow's own font is the last resort.
"""

from __future__ import annotations

import os
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

# Every number uses a fixed-width font, so values do not dance as they change.
MONO = ("consolab.ttf", "DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf", "NotoSansMono-Bold.ttf",
        "UbuntuMono-B.ttf", "Menlo.ttc")
SANS = ("seguisb.ttf", "NotoSans-SemiBold.ttf", "Ubuntu-M.ttf", "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf", "Arial Bold.ttf", "HelveticaNeue.ttc")

FONT_DIRS = [
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".local" / "share" / "fonts",
    Path.home() / ".fonts",
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
]


@lru_cache(maxsize=None)
def _installed() -> dict[str, Path]:
    """Every font file in the font folders, by lower-case file name (first one wins)."""
    found: dict[str, Path] = {}
    for directory in FONT_DIRS:
        try:
            for path in directory.rglob("*"):
                if path.suffix.lower() in (".ttf", ".ttc", ".otf"):
                    found.setdefault(path.name.lower(), path)
        except OSError:
            continue
    return found


@lru_cache(maxsize=None)
def find(names: tuple[str, ...]) -> Path | None:
    for name in names:
        # Straight in a font folder (Windows, macOS): no need to walk the subfolders.
        direct = next((d / name for d in FONT_DIRS if (d / name).is_file()), None)
        if direct:
            return direct
        installed = _installed()  # Linux keeps fonts in subfolders: walk them, once
        if name.lower() in installed:
            return installed[name.lower()]
    return None


@lru_cache(maxsize=None)
def font(names: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    path = find(names)
    if path is None:
        return ImageFont.load_default(size)
    return ImageFont.truetype(str(path), size)


def mono(size: int) -> ImageFont.FreeTypeFont:
    return font(MONO, size)


def sans(size: int) -> ImageFont.FreeTypeFont:
    return font(SANS, size)
