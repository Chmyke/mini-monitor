# SPDX-License-Identifier: GPL-3.0-or-later
"""The supported screens, how to recognise them on USB, and how to open one.

Recognition only reads what the OS reports about each serial port (USB vendor and
product IDs, serial number): nothing is sent to a port before it is identified.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from .base import Link, Orientation, SerialScreen, open_serial, orientation
from .rev_a import RevA
from .rev_b import RevB
from .rev_c import RevC
from .rev_d import RevD
from .weact import WeAct

__all__ = ["MODELS", "Model", "Orientation", "identify", "list_ports", "open_screen", "orientation"]


@dataclass(frozen=True)
class Model:
    name: str
    label: str
    driver: type[SerialScreen]
    native: tuple[int, int] | None = None  # portrait size; None: the driver's own, or asked to the screen
    tested: bool = False


MODELS = {m.name: m for m in (
    Model("turing-3.5", 'Turing Smart Screen 3.5", UsbMonitor 3.5" / 5" / 7" (revision A)', RevA, tested=True),
    Model("xuanfang-3.5", 'XuanFang 3.5", including flagship (revision B)', RevB),
    Model("turing-2.1", 'Turing Smart Screen 2.1" round (revision C)', RevC, (480, 480)),
    Model("turing-5", 'Turing Smart Screen 5" (revision C)', RevC, (480, 800)),
    Model("turing-8.8", 'Turing Smart Screen 8.8" (revision C)', RevC, (480, 1920)),
    Model("kipye-3.5", 'Kipye Qiye Smart Display 3.5" (revision D)', RevD),
    Model("weact-3.5", 'WeAct Studio Display FS V1 3.5"', WeAct),
)}


class PortInfo(Protocol):
    device: str
    vid: int | None
    pid: int | None
    serial_number: str | None


# Revision C screens show up under one identity while asleep, another once awake.
REV_C_ASLEEP = {"USB7INCH": "turing-5", "CT21INCH": "turing-2.1", "CT88INCH": "turing-8.8"}
REV_C_ASLEEP_IDS = {(0x1A86, 0xCA21)}
REV_C_AWAKE_SERIALS = {"20080411"}
REV_C_AWAKE_IDS = {(0x0525, 0xA4A7), (0x1D6B, 0x0121), (0x1D6B, 0x0106)}
WAKE_SECONDS = 15


@dataclass(frozen=True)
class Found:
    model: Model
    device: str
    asleep: bool = False
    native: tuple[int, int] | None = None  # size told by the USB identity, if any


# Serial numbers that tell the size of a revision A screen.
REV_A_SIZES = {"USB35INCHIPSV2": (320, 480)}


def identify(port: PortInfo) -> Found | None:
    """The screen model behind a serial port, from its USB identity alone."""
    sn, ids = port.serial_number or "", (port.vid, port.pid)
    name, asleep = None, False
    if sn == "2017-2-25":  # same USB IDs as revision A: the serial number tells them apart
        name = "xuanfang-3.5"
    elif sn == "USB35INCHIPSV2" or ids == (0x1A86, 0x5722):
        name = "turing-3.5"
    elif ids == (0x454D, 0x4E41):
        name = "kipye-3.5"
    elif ids == (0x1A86, 0xFE0C):
        name = "weact-3.5"
    elif sn in REV_C_ASLEEP:
        name, asleep = REV_C_ASLEEP[sn], True
    elif ids in REV_C_ASLEEP_IDS:
        name, asleep = "turing-5", True
    elif sn in REV_C_AWAKE_SERIALS or ids in REV_C_AWAKE_IDS:
        name = "turing-5"  # the size cannot be told: --screen turing-2.1 / turing-8.8 for the others
    return Found(MODELS[name], port.device, asleep, REV_A_SIZES.get(sn)) if name else None


def list_ports() -> list[PortInfo]:
    from serial.tools.list_ports import comports
    return list(comports())


def find(ports: Iterable[PortInfo], wanted: Model | None = None) -> Found | None:
    """The first recognised screen; with `wanted`, the first one using the same driver."""
    for port in ports:
        found = identify(port)
        if found and (wanted is None or found.model.driver is wanted.driver):
            return found
    return None


def _awake_rev_c(ports: Iterable[PortInfo]) -> str | None:
    for port in ports:
        found = identify(port)
        if found and found.model.driver is RevC and not found.asleep:
            return port.device
    return None


def wake(device: str, ports: Callable[[], list[PortInfo]] = list_ports) -> str | None:
    """A sleeping revision C screen wakes up when its port is opened; its new port, or None."""
    for _ in range(WAKE_SECONDS):
        try:
            open_serial(device).close()
        except Exception:  # the port vanishes while the screen restarts
            pass
        awake = _awake_rev_c(ports())
        if awake:
            time.sleep(1)  # let it finish starting
            return awake
        time.sleep(1)
    return None


def open_screen(name: str = "auto", port: str | None = None,
                orient: Orientation = Orientation.LANDSCAPE,
                ports: Callable[[], list[PortInfo]] = list_ports,
                connect: Callable[[str], Link] = open_serial) -> SerialScreen:
    """Finds, opens and starts the screen. RuntimeError if there is none (retried by the caller)."""
    wanted = None if name == "auto" else MODELS[name]
    if port:
        found = next((identify(p) for p in ports() if p.device == port), None)
        # An unrecognised port given by hand: the wanted model, else revision A (the historic default).
        model = wanted or (found.model if found else MODELS["turing-3.5"])
        found = Found(model, port, bool(found and found.asleep), found.native if found else None)
    else:
        found = find(ports(), wanted)
        if found is None:
            raise RuntimeError("no supported screen found" if wanted is None else f"{name} not found")
        if wanted is not None:
            found = Found(wanted, found.device, found.asleep, found.native)
    device = found.device
    if found.asleep:
        device = wake(device, ports)
        if device is None:
            raise RuntimeError(f"{found.model.name} did not wake up")
    screen = found.model.driver(connect(device), orient, found.model.native or found.native)
    screen.description = f"{found.model.name} on {device}, {screen.size[0]}x{screen.size[1]}"
    return screen
