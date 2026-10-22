"""The terminal the animation plays in: wait until it is large enough, then centre the picture."""
from __future__ import annotations

import os
import sys
import time


def size():
    try:
        s = os.get_terminal_size(sys.stdout.fileno())
        return s.columns, s.lines
    except OSError:
        return 0, 0


def fit(cols, rows, exact=False):
    """Wait until the terminal has at least ``cols`` x ``rows`` cells. -> (left, top) offsets that centre it.

    While the terminal is too small, a one-line note says what is needed; making the window
    larger or the font smaller continues. With ``exact`` (a recording script that sizes the
    window itself) it waits up to 10 s for exactly that size instead.
    """
    if exact:
        end = time.time() + 10
        while time.time() < end and size() != (cols, rows):
            time.sleep(0.05)
        return 0, 0
    shown = None
    while True:
        c, r = size()
        if c >= cols and r >= rows:
            if shown is not None:
                sys.stdout.write("\x1b[2J")
            return (c - cols) // 2, (r - rows) // 2
        if (c, r) != shown:
            shown = (c, r)
            note = (f"cinetty: this template needs {cols} x {rows} cells; the terminal has {c} x {r}. "
                    "Make the window larger or the font smaller (Ctrl-C stops).")
            sys.stdout.write("\x1b[2J\x1b[H" + note)
            sys.stdout.flush()
        time.sleep(0.2)
