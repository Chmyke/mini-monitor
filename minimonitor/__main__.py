# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: `python -m minimonitor` drives the screen; `--preview FILE` writes one frame as PNG.

Started at logon by pythonw (no console): everything worth knowing goes to the log
file in %LOCALAPPDATA%\\MiniMonitor, and a second instance exits at once, since
only one program can talk to the screen.
"""

from __future__ import annotations

import argparse
import logging
import msvcrt
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .i18n import LANGUAGES

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MiniMonitor"

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


def single_instance(wait_seconds: float = 15):
    """Holds an OS lock for the life of the process; None if another instance keeps it.

    Waits a little first: on a restart, the previous instance takes a few seconds to exit.
    """
    lock = open(DATA_DIR / "minimonitor.lock", "a+")
    lock.seek(0)  # every instance locks the same byte
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            return lock
        except OSError:
            if time.monotonic() >= deadline:
                lock.close()
                return None
            time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(prog="minimonitor")
    parser.add_argument("--preview", metavar="PNG", help="render one frame with live data to a PNG and exit")
    parser.add_argument("--demo", metavar="DIR", help="write demo pictures (made-up values) to DIR and exit")
    parser.add_argument("--port", help="serial port (default: auto-detect)")
    parser.add_argument("--brightness", type=int, default=60)
    parser.add_argument("--lang", choices=sorted(LANGUAGES), default="fr", help="screen language")
    args = parser.parse_args()
    texts = LANGUAGES[args.lang]

    if args.demo:
        from .demo import write_demo
        for path in write_demo(args.demo, texts, args.lang):
            print(path)
        return

    if args.preview:
        from .preview import write_preview
        write_preview(args.preview, texts)
        return

    setup_logging()
    lock = single_instance()
    if lock is None:
        log.info("another instance is already running: exiting")
        return

    from .app import run
    from .lcd import Screen
    log.info("started (lang=%s, brightness=%d)", args.lang, args.brightness)
    try:
        run(lambda: Screen(args.port), args.brightness, texts)
    except KeyboardInterrupt:
        log.info("stopped")
    except Exception:
        log.exception("crashed")  # the scheduled task restarts it
        raise


if __name__ == "__main__":
    main()
