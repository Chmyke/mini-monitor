# SPDX-License-Identifier: GPL-3.0-or-later
"""PC metrics: psutil for CPU, memory, disk and network; the GPU from NVML (NVIDIA,
Windows and Linux) or, on Linux, from the amdgpu driver's files in /sys."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psutil

try:
    import pynvml
except ImportError:  # pragma: no cover - the GPU row then shows '?'
    pynvml = None


@dataclass(frozen=True)
class Snapshot:
    gpu_temp: float | None
    gpu_util: float | None
    cpu: float
    mem_used_gb: float
    mem_total_gb: float
    disk: float | None
    net_down: float  # bytes per second
    net_up: float


class Gpu(Protocol):
    name: str | None

    def read(self) -> tuple[float | None, float | None]:
        """(temperature in °C, load in %), None for what cannot be read."""


class NvidiaGpu:
    def __init__(self):
        pynvml.nvmlInit()
        self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(self._handle)
        self.name = name.decode() if isinstance(name, bytes) else name

    def read(self) -> tuple[float | None, float | None]:
        try:
            temp = pynvml.nvmlDeviceGetTemperature(self._handle, pynvml.NVML_TEMPERATURE_GPU)
            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle).gpu
            return float(temp), float(util)
        except pynvml.NVMLError:
            return None, None


AMD_VENDOR = "0x1002"


class AmdSysfsGpu:
    """AMD card on Linux: load and temperature as the amdgpu driver publishes them."""

    def __init__(self, device: Path):
        self._busy = device / "gpu_busy_percent"
        temps = sorted(device.glob("hwmon/hwmon*/temp1_input"))  # temp1: the 'edge' sensor
        self._temp = temps[0] if temps else None
        self.name = "AMD Radeon"

    @staticmethod
    def find(drm: Path = Path("/sys/class/drm")) -> AmdSysfsGpu | None:
        for card in sorted(drm.glob("card[0-9]*")):
            device = card / "device"
            try:
                if (device / "vendor").read_text().strip() == AMD_VENDOR and (device / "gpu_busy_percent").exists():
                    return AmdSysfsGpu(device)
            except OSError:
                continue
        return None

    def read(self) -> tuple[float | None, float | None]:
        return (_read_number(self._temp, 1000) if self._temp else None), _read_number(self._busy)


def _read_number(path: Path, divisor: float = 1) -> float | None:
    try:
        return float(path.read_text().strip()) / divisor
    except (OSError, ValueError):
        return None


def open_gpu() -> Gpu | None:
    if pynvml is not None:
        try:
            return NvidiaGpu()
        except pynvml.NVMLError:
            pass
    if sys.platform.startswith("linux"):
        return AmdSysfsGpu.find()
    return None


def default_disk() -> str:
    """The system drive on Windows (usually C:\\), the root elsewhere."""
    if sys.platform == "win32":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


def disk_label(path: str) -> str:
    """'C:\\' -> 'C:'; mount points stay as they are ('/', '/home')."""
    drive = os.path.splitdrive(path)[0] if sys.platform == "win32" else ""
    return drive or path.rstrip("/") or "/"


class PcSampler:
    def __init__(self, disk_path: str | None = None, gpu: Gpu | None = None):
        self.disk_path = disk_path or default_disk()
        self._gpu = gpu if gpu is not None else open_gpu()
        self.gpu_name: str | None = self._gpu.name if self._gpu else None
        psutil.cpu_percent(None)  # first call primes the counter
        self._net = psutil.net_io_counters()
        self._net_time = time.monotonic()

    def sample(self) -> Snapshot:
        gpu_temp, gpu_util = self._gpu.read() if self._gpu else (None, None)
        mem = psutil.virtual_memory()
        net, now = psutil.net_io_counters(), time.monotonic()
        dt = max(now - self._net_time, 1e-3)
        down = max(net.bytes_recv - self._net.bytes_recv, 0) / dt
        up = max(net.bytes_sent - self._net.bytes_sent, 0) / dt
        self._net, self._net_time = net, now
        gib = 1024 ** 3
        try:
            disk = psutil.disk_usage(self.disk_path).percent
        except OSError:  # a removed drive or a mistyped --disk: the row shows '?'
            disk = None
        return Snapshot(
            gpu_temp=gpu_temp,
            gpu_util=gpu_util,
            cpu=psutil.cpu_percent(None),
            mem_used_gb=(mem.total - mem.available) / gib,
            mem_total_gb=mem.total / gib,
            disk=disk,
            net_down=down,
            net_up=up,
        )
