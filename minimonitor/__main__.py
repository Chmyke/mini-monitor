# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: `python -m minimonitor` drives the screen; `--preview FILE` writes one frame as PNG.

Started at logon without a console (pythonw on Windows, a systemd user service on
Linux): everything worth knowing goes to the log file, and a second instance exits
at once, since only one program can talk to the screen.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .i18n import LANGUAGES


def data_dir() -> Path:
    """%LOCALAPPDATA%\\MiniMonitor on Windows, $XDG_STATE_HOME/minimonitor elsewhere."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MiniMonitor"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "minimonitor"


DATA_DIR = data_dir()

log = logging.getLogger("minimonitor")


def setup_logging() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "minimonitor.log"
    handler = RotatingFileHandler(path, maxBytes=500_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if sys.stderr is not None:  # console run: also show the log
        root.addHandler(logging.StreamHandler())
    root.setLevel(logging.INFO)
    return path


def _try_lock(lock) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def single_instance(wait_seconds: float = 15):
    """Holds an OS lock for the life of the process; None if another instance keeps it.

    Waits a little first: on a restart, the previous instance takes a few seconds to exit.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(DATA_DIR / "minimonitor.lock", "a+")
    lock.seek(0)  # every instance locks the same byte
    deadline = time.monotonic() + wait_seconds
    while not _try_lock(lock):
        if time.monotonic() >= deadline:
            lock.close()
            return None
        time.sleep(0.5)
    return lock


def size(text: str) -> tuple[int, int]:
    """'800x480' -> (800, 480)."""
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 800x480") from None
    if not (16 <= w <= 4096 and 16 <= h <= 4096):
        raise argparse.ArgumentTypeError("each side between 16 and 4096 pixels")
    return w, h


def parser() -> argparse.ArgumentParser:
    from .screens import MODELS
    p = argparse.ArgumentParser(prog="minimonitor")
    p.add_argument("--screen", choices=["auto", "window", *MODELS], default="auto",
                   help="screen model (default: detected); 'window' shows the dashboard in a desktop window")
    p.add_argument("--list-screens", action="store_true", help="list the serial ports and the screens recognised")
    p.add_argument("--port", help="serial port, e.g. COM3 or /dev/ttyACM0 (default: detected)")
    p.add_argument("--portrait", action="store_true", help="screen standing upright (default: landscape)")
    p.add_argument("--flip", action="store_true", help="turn the picture upside down")
    p.add_argument("--size", type=size, help="window, preview or demo size, e.g. 800x480 (default 480x320)")
    p.add_argument("--brightness", type=int, default=60, help="backlight, 0-100")
    p.add_argument("--lang", choices=sorted(LANGUAGES), default="fr", help="screen language")
    p.add_argument("--disk", help=r"disk to show (default: C:\ on Windows, / elsewhere)")
    p.add_argument("--preview", metavar="PNG", help="render one frame with live data to a PNG and exit")
    p.add_argument("--demo", metavar="DIR", help="write demo pictures (made-up values) to DIR and exit")
    p.add_argument("--scale", type=int, default=1, help="with --demo: enlarge pixels (2 = 960x640)")
    return p


def list_screens() -> list[str]:
    from .screens import identify, list_ports
    lines = []
    for port in list_ports():
        found = identify(port)
        ids = f"{port.vid:04X}:{port.pid:04X}" if port.vid is not None else "----:----"
        what = f"{found.model.name}{' (asleep)' if found.asleep else ''}" if found else "-"
        lines.append(f"{port.device:<16} {ids}  {port.serial_number or '':<16} {what}")
    return lines or ["no serial port found"]


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    texts = LANGUAGES[args.lang]
    default_size = (320, 480) if args.portrait else (480, 320)

    if args.list_screens:
        print("\n".join(list_screens()))
        return

    if args.demo:
        from .demo import write_demo
        for path in write_demo(args.demo, texts, args.lang, args.scale, args.size or default_size):
            print(path)
        return

    if args.preview:
        from .preview import write_preview
        write_preview(args.preview, texts, args.size or default_size, args.disk)
        return

    setup_logging()
    if args.screen == "window":
        from .screens.window import WindowScreen
        window = WindowScreen(args.size or default_size)
        open_display = lambda: window  # noqa: E731 - one window for the whole run
    else:
        lock = single_instance()  # noqa: F841 - held until the process exits
        if lock is None:
            log.info("another instance is already running: exiting")
            return
        from .screens import open_screen, orientation
        orient = orientation(landscape=not args.portrait, flip=args.flip)
        open_display = lambda: open_screen(args.screen, args.port, orient)  # noqa: E731

    from .app import run
    log.info("started (screen=%s, lang=%s, brightness=%d)", args.screen, args.lang, args.brightness)
    try:
        run(open_display, args.brightness, texts, args.disk)
    except KeyboardInterrupt:
        log.info("stopped")
    except Exception:
        log.exception("crashed")  # the scheduled task or service restarts it
        raise


if __name__ == "__main__":
    main()
