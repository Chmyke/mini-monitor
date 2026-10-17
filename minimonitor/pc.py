# SPDX-License-Identifier: GPL-3.0-or-later
"""PC metrics: psutil for CPU, memory, disk and network; NVML for the GPU."""

from __future__ import annotations

import time
from dataclasses import dataclass

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
    disk: float
    net_down: float  # bytes per second
    net_up: float


class PcSampler:
    def __init__(self, disk_path: str = "C:\\"):
        self._disk_path = disk_path
        self._gpu = None
        self.gpu_name: str | None = None
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                self._gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
                name = pynvml.nvmlDeviceGetName(self._gpu)
                self.gpu_name = name.decode() if isinstance(name, bytes) else name
            except pynvml.NVMLError:
                self._gpu = None
        psutil.cpu_percent(None)  # first call primes the counter
        self._net = psutil.net_io_counters()
        self._net_time = time.monotonic()

    def _gpu_values(self) -> tuple[float | None, float | None]:
        if self._gpu is None:
            return None, None
        try:
            temp = pynvml.nvmlDeviceGetTemperature(self._gpu, pynvml.NVML_TEMPERATURE_GPU)
            util = pynvml.nvmlDeviceGetUtilizationRates(self._gpu).gpu
            return float(temp), float(util)
        except pynvml.NVMLError:
            return None, None

    def sample(self) -> Snapshot:
        gpu_temp, gpu_util = self._gpu_values()
        mem = psutil.virtual_memory()
        net, now = psutil.net_io_counters(), time.monotonic()
        dt = max(now - self._net_time, 1e-3)
        down = max(net.bytes_recv - self._net.bytes_recv, 0) / dt
        up = max(net.bytes_sent - self._net.bytes_sent, 0) / dt
        self._net, self._net_time = net, now
        gib = 1024 ** 3
        return Snapshot(
            gpu_temp=gpu_temp,
            gpu_util=gpu_util,
            cpu=psutil.cpu_percent(None),
            mem_used_gb=(mem.total - mem.available) / gib,
            mem_total_gb=mem.total / gib,
            disk=psutil.disk_usage(self._disk_path).percent,
            net_down=down,
            net_up=up,
        )
