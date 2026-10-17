# SPDX-License-Identifier: GPL-3.0-or-later
"""Pixel formats the screens expect, computed by Pillow in C (no per-pixel Python loop)."""

from __future__ import annotations

from PIL import Image, ImageChops


def rgb565(image: Image.Image, big_endian: bool = False) -> bytes:
    """RGB565: 5 bits of red, 6 of green, 5 of blue, two bytes per pixel."""
    r, g, b = image.convert("RGB").split()
    # The two bytes of a pixel, each the sum of two channels whose bits never overlap.
    high = ImageChops.add(r.point(lambda v: v & 0xF8), g.point(lambda v: v >> 5))
    low = ImageChops.add(g.point(lambda v: (v & 0x1C) << 3), b.point(lambda v: v >> 3))
    return Image.merge("LA", (high, low) if big_endian else (low, high)).tobytes()


def bgr(image: Image.Image) -> bytes:
    return image.convert("RGB").tobytes("raw", "BGR")


def bgra(image: Image.Image) -> bytes:
    return image.convert("RGBA").tobytes("raw", "BGRA")


def chunked(data: bytes, size: int) -> list[bytes]:
    return [data[i:i + size] for i in range(0, len(data), size)]
