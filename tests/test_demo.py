# SPDX-License-Identifier: GPL-3.0-or-later
from PIL import Image

from minimonitor import demo
from minimonitor.i18n import EN


def test_demo_animation_is_deterministic_and_settles(tmp_path):
    first, again = demo.frames(EN), demo.frames(EN)
    assert len(first) == round(demo.SECONDS * demo.FPS)
    assert all(a.tobytes() == b.tobytes() for a, b in zip(first[::30], again[::30]))
    assert first[0].tobytes() != first[-1].tobytes()  # it moves


def test_demo_files(tmp_path):
    still, animation = demo.write_demo(str(tmp_path), EN, "en")
    assert Image.open(still).size == (480, 320)
    with Image.open(animation) as im:
        assert im.n_frames == round(demo.SECONDS * demo.FPS)


def test_demo_scale_keeps_pixels_square(tmp_path):
    still, _ = demo.write_demo(str(tmp_path), EN, "en", scale=2)
    big = Image.open(still)
    assert big.size == (960, 640)
    assert big.getpixel((40, 40)) == big.getpixel((41, 41))  # one screen pixel = a 2x2 block
