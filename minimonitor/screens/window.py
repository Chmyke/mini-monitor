# SPDX-License-Identifier: GPL-3.0-or-later
"""A window on the desktop that stands in for the USB screen (--screen window).

Uses Tk, shipped with Python on Windows (python3-tk on Debian and Ubuntu). The window
is driven from the main loop: it handles its events once per frame, in refresh().
Closing it ends the program; close() only forgets the link, the window stays.
"""

from __future__ import annotations

from PIL import Image

from .. import theme


class WindowScreen:
    round = False

    def __init__(self, size: tuple[int, int] = (480, 320)):
        import tkinter as tk
        from PIL import ImageTk

        self.size = size
        self.description = f"window, {size[0]}x{size[1]}"
        self._frame = Image.new("RGB", size, theme.BG)
        self._root = tk.Tk()
        self._root.title("Mini Monitor")
        self._root.resizable(False, False)
        self._root.configure(background=theme.BG)
        self._photo = ImageTk.PhotoImage(self._frame)
        tk.Label(self._root, image=self._photo, borderwidth=0, highlightthickness=0).pack()
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._closed = self._dirty = False
        self._tk_error = tk.TclError

    def _on_close(self) -> None:
        self._closed = True

    def brightness(self, percent: int) -> None:
        """A window has no backlight."""

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        self._frame.paste(image, (x, y))
        self._dirty = True

    def refresh(self) -> None:
        if self._closed:
            self._root.destroy()
            raise SystemExit(0)
        try:
            if self._dirty:
                self._photo.paste(self._frame)
                self._dirty = False
            self._root.update()
        except self._tk_error:  # the window was destroyed from outside
            raise SystemExit(0) from None

    def close(self) -> None:
        """Called when the link is dropped (after sleep): the same window is used again."""
