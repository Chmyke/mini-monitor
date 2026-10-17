# SPDX-License-Identifier: GPL-3.0-or-later
import sys

import pytest

from minimonitor import pc
from minimonitor.pc import AmdSysfsGpu, PcSampler


def fake_card(drm, name, vendor, busy=None, temp=None):
    device = drm / name / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text(vendor + "\n")
    if busy is not None:
        (device / "gpu_busy_percent").write_text(f"{busy}\n")
    if temp is not None:
        hwmon = device / "hwmon" / "hwmon3"
        hwmon.mkdir(parents=True)
        (hwmon / "temp1_input").write_text(f"{temp}\n")
    return device


def test_amd_card_is_read_from_sysfs(tmp_path):
    fake_card(tmp_path, "card0", "0x8086")  # Intel iGPU: no load published, skipped
    fake_card(tmp_path, "card1", "0x1002", busy=37, temp=54000)
    gpu = AmdSysfsGpu.find(tmp_path)
    assert gpu is not None and gpu.read() == (54.0, 37.0)


def test_amd_card_without_sensor_shows_unknown_temperature(tmp_path):
    fake_card(tmp_path, "card0", "0x1002", busy=5)
    assert AmdSysfsGpu.find(tmp_path).read() == (None, 5.0)


def test_unreadable_amd_values_are_unknown_not_errors(tmp_path):
    device = fake_card(tmp_path, "card0", "0x1002", busy=5, temp=40000)
    gpu = AmdSysfsGpu.find(tmp_path)
    (device / "gpu_busy_percent").write_text("garbage")
    (device / "hwmon" / "hwmon3" / "temp1_input").unlink()
    assert gpu.read() == (None, None)


def test_no_amd_card(tmp_path):
    fake_card(tmp_path, "card0", "0x10de", busy=1)  # NVIDIA goes through NVML
    assert AmdSysfsGpu.find(tmp_path) is None
    assert AmdSysfsGpu.find(tmp_path / "missing") is None


class FixedGpu:
    name = "NVIDIA GeForce RTX 4080 SUPER"

    def read(self):
        return 50.0, 10.0


def test_sampler_uses_the_given_gpu_and_survives_a_missing_disk(tmp_path):
    sampler = PcSampler(disk_path=str(tmp_path / "gone"), gpu=FixedGpu())
    snap = sampler.sample()
    assert sampler.gpu_name.startswith("NVIDIA")
    assert (snap.gpu_temp, snap.gpu_util) == (50.0, 10.0)
    assert snap.disk is None  # shown as '?', the loop keeps running


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive letters")
def test_windows_disk_label(monkeypatch):
    monkeypatch.setenv("SystemDrive", "D:")
    assert pc.default_disk() == "D:\\"
    assert pc.disk_label("D:\\") == "D:"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mount points")
def test_posix_disk_label():
    assert pc.default_disk() == "/"
    assert pc.disk_label("/") == "/"
    assert pc.disk_label("/home/") == "/home"
