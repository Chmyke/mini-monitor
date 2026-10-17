"""Entry point: `python -m minimonitor` drives the screen; `--preview FILE` writes one frame as PNG."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="minimonitor")
    parser.add_argument("--preview", metavar="PNG", help="render one frame with live data to a PNG and exit")
    parser.add_argument("--port", help="serial port (default: auto-detect)")
    parser.add_argument("--brightness", type=int, default=60)
    args = parser.parse_args()

    if args.preview:
        from .preview import write_preview
        write_preview(args.preview)
        return

    from .app import run
    from .lcd import Screen
    screen = Screen(args.port)
    try:
        run(screen, args.brightness)
    finally:
        screen.close()


if __name__ == "__main__":
    main()
