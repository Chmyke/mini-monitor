# SPDX-License-Identifier: GPL-3.0-or-later
"""Who uses the PC: CPU, GPU, memory and disk traffic per application.

Processes are grouped by application (52 claude.exe are one "Claude"). On Windows one
NtQuerySystemInformation call returns every process with its times, memory and I/O
(about 30 ms for 700 processes, measured 2026-11-19); psutil took 5 s for the same, so it
is only the fallback elsewhere, where it is fast. The GPU share comes from the NVIDIA driver
(about 2 ms); without it the GPU bar stays whole. Read every few seconds off the frame loop.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Callable

import psutil

log = logging.getLogger(__name__)

PERIOD = 3.0  # seconds between two readings: the shares are averaged over this window
TOP = 3  # applications named per resource; the rest is "others"
IDLE_NAMES = {"Idle", "System Idle Process"}
# Process names that are one tool for the person reading the screen.
ALIASES = {"rustc": "Rust", "cargo": "Rust", "rust-analyzer": "Rust"}
# Windows' own processes: their names say nothing, what matters is "it is not one of my programs".
WINDOWS = {"system", "registry", "csrss", "dwm", "svchost", "memcompression", "lsass", "services",
           "wininit", "winlogon", "smss", "fontdrvhost", "searchindexer", "msmpeng", "audiodg", "wmiprvse"}


@dataclass(frozen=True)
class Raw:
    """One process at one instant: cumulated counters, as the OS gives them."""
    name: str
    cpu_seconds: float
    io_bytes: int
    memory: int  # bytes in RAM (working set / RSS)


@dataclass(frozen=True)
class Usage:
    """Biggest applications per resource, largest first, as (name, value)."""
    cpu: tuple[tuple[str, float], ...]  # percent of the whole machine
    gpu: tuple[tuple[str, float], ...] | None  # percent of the GPU; None: not readable here
    memory: tuple[tuple[str, float], ...]  # bytes
    disk: tuple[str, float] | None  # the application moving the most bytes on disk, bytes/s


def app_name(process: str) -> str:
    """'claude.exe' -> 'Claude', 'darkomen_client.exe' -> 'Darkomen client', 'rustc' -> 'Rust'."""
    stem = process[:-4] if process.lower().endswith(".exe") else process
    if stem.lower() in WINDOWS:
        return "Windows"
    stem = ALIASES.get(stem.lower(), stem).replace("_", " ").strip()
    return stem[:1].upper() + stem[1:] if stem else "?"


def top(values: Counter, n: int = TOP) -> tuple[tuple[str, float], ...]:
    return tuple((name, value) for name, value in values.most_common(n) if value > 0)


def compare(before: dict[int, Raw], after: dict[int, Raw], seconds: float, cpus: int,
            gpu: dict[int, float] | None) -> Usage:
    """Shares over the window between two readings. A pid reused by another program is skipped."""
    cpu, io, memory, gpu_apps = Counter(), Counter(), Counter(), Counter()
    seconds = max(seconds, 1e-3)
    for pid, now in after.items():
        if now.name in IDLE_NAMES:
            continue
        name = app_name(now.name)
        memory[name] += now.memory
        then = before.get(pid)
        if then is not None and then.name == now.name:
            cpu[name] += max(now.cpu_seconds - then.cpu_seconds, 0) / seconds / cpus * 100
            io[name] += max(now.io_bytes - then.io_bytes, 0) / seconds
        if gpu and pid in gpu:
            gpu_apps[name] += gpu[pid]
    disk = io.most_common(1)
    return Usage(top(cpu), top(gpu_apps) if gpu is not None else None, top(memory),
                 disk[0] if disk and disk[0][1] > 0 else None)


# ---------- readers ----------

def _windows_reader() -> Callable[[], dict[int, Raw]]:
    """Every process in one NtQuerySystemInformation(SystemProcessInformation) call."""
    import ctypes

    class UnicodeString(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("maximum", ctypes.c_ushort), ("buffer", ctypes.c_void_p)]

    ulong, ulonglong, longlong, size = ctypes.c_ulong, ctypes.c_ulonglong, ctypes.c_longlong, ctypes.c_size_t

    class ProcessInformation(ctypes.Structure):  # SYSTEM_PROCESS_INFORMATION, documented layout
        _fields_ = [
            ("next", ulong), ("threads", ulong), ("private_working_set", longlong), ("hard_faults", ulong),
            ("threads_high", ulong), ("cycles", ulonglong), ("create", longlong), ("user", longlong),
            ("kernel", longlong), ("name", UnicodeString), ("priority", ctypes.c_long),
            ("pid", ctypes.c_void_p), ("parent", ctypes.c_void_p), ("handles", ulong), ("session", ulong),
            ("key", ctypes.c_void_p), ("peak_virtual", size), ("virtual", size), ("page_faults", ulong),
            ("peak_working_set", size), ("working_set", size), ("quota_1", size), ("quota_2", size),
            ("quota_3", size), ("quota_4", size), ("pagefile", size), ("peak_pagefile", size),
            ("private_pages", size), ("read_ops", ulonglong), ("write_ops", ulonglong),
            ("other_ops", ulonglong), ("read_bytes", ulonglong), ("write_bytes", ulonglong),
            ("other_bytes", ulonglong),
        ]

    query = ctypes.WinDLL("ntdll").NtQuerySystemInformation
    state = {"buffer": ctypes.create_string_buffer(4 << 20)}
    too_small = 0xC0000004  # STATUS_INFO_LENGTH_MISMATCH

    def read() -> dict[int, Raw]:
        needed = ulong()
        while True:
            buffer = state["buffer"]
            status = query(5, buffer, len(buffer), ctypes.byref(needed)) & 0xFFFFFFFF
            if status != too_small:
                break
            state["buffer"] = ctypes.create_string_buffer(max(needed.value * 2, len(buffer) * 2))
        if status:
            raise OSError(f"NtQuerySystemInformation 0x{status:08x}")
        found, base, offset = {}, ctypes.addressof(buffer), 0
        while True:
            p = ProcessInformation.from_address(base + offset)
            name = ctypes.wstring_at(p.name.buffer, p.name.length // 2) if p.name.buffer else "Idle"
            found[p.pid or 0] = Raw(name, (p.user + p.kernel) / 1e7, p.read_bytes + p.write_bytes,
                                    p.working_set)
            if not p.next:
                return found
            offset += p.next

    return read


def _psutil_read() -> dict[int, Raw]:
    found = {}
    for p in psutil.process_iter(["name", "cpu_times", "memory_info", "io_counters"]):
        info = p.info
        times, mem, io = info.get("cpu_times"), info.get("memory_info"), info.get("io_counters")
        if times is None or mem is None:  # not ours to read
            continue
        io_bytes = (io.read_bytes + io.write_bytes) if io is not None else 0
        found[p.pid] = Raw(info.get("name") or "?", times.user + times.system, io_bytes, mem.rss)
    return found


def default_reader() -> Callable[[], dict[int, Raw]]:
    if sys.platform == "win32":
        try:
            return _windows_reader()
        except (OSError, AttributeError) as e:
            log.warning("process list: native call unavailable (%s), using psutil", type(e).__name__)
    return _psutil_read


class Watcher:
    """Reads the processes every PERIOD seconds in the background; `latest()` never blocks."""

    def __init__(self, gpu_loads: Callable[[float], dict[int, float] | None] | None = None,
                 reader: Callable[[], dict[int, Raw]] | None = None, period: float = PERIOD,
                 start: bool = True):
        self._read = reader or default_reader()
        self._gpu = gpu_loads
        self._period = period
        self._cpus = os.cpu_count() or 1
        self._lock = threading.Lock()
        self._usage: Usage | None = None
        self._before: tuple[float, dict[int, Raw]] | None = None
        if start:
            threading.Thread(target=self._run, daemon=True).start()

    def step(self) -> None:
        """One reading; from the second on, the shares since the previous one."""
        at, now = time.monotonic(), self._read()
        if self._before is not None:
            then, before = self._before
            gpu = self._gpu(at - then) if self._gpu else None
            usage = compare(before, now, at - then, self._cpus, gpu)
            with self._lock:
                self._usage = usage
        self._before = (at, now)

    def _run(self) -> None:
        failing = False
        while True:
            try:
                self.step()
                failing = False
            except Exception as e:  # a broken reading leaves the bars whole, never the screen
                if not failing:
                    log.warning("process list: %s", type(e).__name__)
                failing = True
                with self._lock:
                    self._usage = None
            time.sleep(self._period)

    def latest(self) -> Usage | None:
        with self._lock:
            return self._usage

