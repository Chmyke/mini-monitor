# SPDX-License-Identifier: GPL-3.0-or-later
import sys

import pytest

from minimonitor import fmt, procs, theme
from minimonitor.app import apps_view
from minimonitor.i18n import FR
from minimonitor.pc import Snapshot
from minimonitor.procs import Raw, Usage, app_name, compare

GB = 1024 ** 3


def test_application_names_are_readable_and_grouped():
    assert app_name("claude.exe") == "Claude"
    assert app_name("Photoshop.exe") == "Photoshop"
    assert app_name("darkomen_client.exe") == "Darkomen client"
    assert app_name("rustc.exe") == app_name("cargo") == "Rust"
    assert app_name("") == "?"
    assert app_name("csrss.exe") == app_name("System") == app_name("svchost.exe") == "Windows"


def test_shares_are_summed_per_application_over_the_window():
    before = {1: Raw("claude.exe", 10, 0, GB), 2: Raw("claude.exe", 5, 0, GB), 3: Raw("blender.exe", 0, 0, GB),
              0: Raw("Idle", 0, 0, 0)}
    after = {1: Raw("claude.exe", 11, 0, GB), 2: Raw("claude.exe", 6, 0, 2 * GB),
             3: Raw("blender.exe", 4, 30_000_000, GB), 0: Raw("Idle", 99, 0, 0)}
    found = compare(before, after, seconds=2, cpus=4, gpu={3: 48.0, 1: 2.0})
    # Blender: 4 s of CPU in 2 s on 4 cores = 50 % of the machine; Claude: 2 s -> 25 %.
    assert found.cpu == (("Blender", 50.0), ("Claude", 25.0))
    assert found.gpu == (("Blender", 48.0), ("Claude", 2.0))
    assert found.memory[0] == ("Claude", 3 * GB)
    assert found.disk == ("Blender", 15_000_000)
    assert all(name != "Idle" for name, _ in found.cpu)


def test_a_reused_pid_is_not_counted_as_the_old_program():
    found = compare({7: Raw("old.exe", 100, 10**9, 0)}, {7: Raw("new.exe", 1, 0, GB)}, 1, 1, None)
    assert found.cpu == () and found.disk is None and found.gpu is None


def test_only_the_three_biggest_are_named():
    after = {i: Raw(f"app{i}.exe", 0, 0, (i + 1) * GB) for i in range(6)}
    assert [n for n, _ in compare({}, after, 1, 1, None).memory] == ["App5", "App4", "App3"]


def test_the_watcher_needs_two_readings_and_survives_without_gpu():
    readings = iter([{1: Raw("a.exe", 0, 0, GB)}, {1: Raw("a.exe", 1, 0, GB)}])
    watcher = procs.Watcher(gpu_loads=lambda s: None, reader=lambda: next(readings), start=False)
    watcher.step()
    assert watcher.latest() is None
    watcher.step()
    assert watcher.latest().cpu and watcher.latest().gpu is None


@pytest.mark.skipif(sys.platform != "win32", reason="the native call exists on Windows only")
def test_the_native_windows_reading_sees_this_very_process():
    import os
    found = procs._windows_reader()()
    assert os.getpid() in found and found[os.getpid()].name.lower().startswith("python")
    assert found[os.getpid()].memory > 0 and found[os.getpid()].cpu_seconds > 0


def test_split_is_a_fraction_of_the_bar_and_never_overflows():
    assert fmt.split(80, (("A", 40), ("B", 20))) == (("A", 0.5), ("B", 0.25))
    assert fmt.split(50, (("A", 40), ("B", 40))) == (("A", 0.5), ("B", 0.5))  # counters exceed the total
    assert fmt.split(0, (("A", 1),)) == () and fmt.split(None, (("A", 1),)) == ()


def test_an_application_keeps_its_colour_while_it_stays_on_screen():
    palette = ("blue", "yellow", "green")
    first = fmt.assign_colors({}, ["Rust", "Blender"], palette)
    assert first == {"Rust": "blue", "Blender": "yellow"}
    second = fmt.assign_colors(first, ["Blender", "Claude", "Rust"], palette)
    assert second == {"Blender": "yellow", "Rust": "blue", "Claude": "green"}
    third = fmt.assign_colors(second, ["Chrome", "Java", "Claude", "Zed"], palette)
    assert third["Claude"] == "green" and len(set(third.values())) == 3 and "Zed" not in third


def test_apps_view_names_who_fills_each_bar():
    pc = Snapshot(60, 74, 82, 41.0, 64.0, 79, 0, 0)
    found = Usage(cpu=(("Rust", 41.0), ("Blender", 17.0), ("Claude", 6.0)), gpu=(("Blender", 48.0),),
                  memory=(("Claude", 9.1 * GB),), disk=("Rust", 480e6))
    apps, colors = apps_view(found, pc, {}, FR)
    assert colors["Rust"] == theme.APP_COLORS[0] and colors["Blender"] == theme.APP_COLORS[1]
    assert [n for n, _ in apps.cpu.legend] == ["Rust", "Blender"]
    assert apps.gpu.parts == ((48 / 74, colors["Blender"]),)
    assert apps.disk == ("Rust", colors["Rust"], "480 Mo/s")
    quiet = Usage(cpu=(), gpu=None, memory=(), disk=("Chrome", 20_000))
    assert apps_view(quiet, pc, colors, FR)[0].disk is None  # a trickle names nobody
    assert apps_view(None, pc, colors, FR) == (None, colors)
