# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import sys
import time

import pytest

from minimonitor import __main__ as entry


def test_second_instance_waits_then_gives_up():
    first = entry.single_instance(wait_seconds=0)
    assert first is not None
    start = time.monotonic()
    assert entry.single_instance(wait_seconds=0.6) is None
    assert time.monotonic() - start >= 0.5  # it waited for the first one to exit


def test_lock_is_free_again_once_the_first_instance_exits():
    first = entry.single_instance(wait_seconds=0)
    first.close()  # what the OS does when the process ends
    second = entry.single_instance(wait_seconds=0)
    assert second is not None
    second.close()


def test_size_option():
    assert entry.size("800x480") == (800, 480)
    assert entry.size("320X480") == (320, 480)
    for bad in ("800", "axb", "10x10", "9000x480"):
        with pytest.raises(argparse.ArgumentTypeError):
            entry.size(bad)


def test_every_model_is_a_screen_choice():
    from minimonitor.screens import MODELS
    args = entry.parser().parse_args(["--screen", "turing-8.8", "--portrait", "--flip"])
    assert args.screen == "turing-8.8" and args.portrait and args.flip
    assert set(MODELS) <= set(entry.parser()._option_string_actions["--screen"].choices)


def test_data_dir_per_platform(monkeypatch, tmp_path):
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert entry.data_dir() == tmp_path / "MiniMonitor"
    else:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        assert entry.data_dir() == tmp_path / "minimonitor"


def test_list_screens_names_what_it_recognises(monkeypatch):
    from types import SimpleNamespace
    from minimonitor import screens
    ports = [SimpleNamespace(device="COM3", vid=0x1A86, pid=0x5722, serial_number="USB35INCHIPSV2"),
             SimpleNamespace(device="COM1", vid=None, pid=None, serial_number=None)]
    monkeypatch.setattr(screens, "list_ports", lambda: ports)
    lines = entry.list_screens()
    assert "turing-3.5" in lines[0] and "1A86:5722" in lines[0]
    assert lines[1].rstrip().endswith("-")
