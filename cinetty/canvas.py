"""Character grid, color helpers and the escape-code encoder.

A frame is a grid of cells ``[char, fg, bold]``. Wide (CJK) characters take two
cells; the second one holds ``""`` so the encoder skips it.
"""
from __future__ import annotations

import random
import unicodedata

BG = (0, 0, 0)

# Default palette shared by every template. Scenes may override or extend it.
BASE_COLORS = {
    "bg": (0, 0, 0),
    "dim": (92, 98, 110),
    "gray": (150, 156, 166),
    "soft": (200, 204, 212),
    "white": (232, 234, 238),
    "bright": (255, 255, 255),
    "line": (58, 64, 76),
    "red": (255, 72, 72),
    "track": (34, 38, 46),
    "gold": (255, 196, 87),
}


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def cw(ch):
    """Display width of one character in terminal cells."""
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def tw(s):
    """Display width of a string in terminal cells (CJK counts as 2)."""
    return sum(cw(c) for c in s)


def ease_out(x):
    return 1 - (1 - x) ** 3


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def clamp01(x):
    return max(0.0, min(1.0, x))


def typed(text, t0, cps, t):
    """The part of ``text`` typed so far when typing starts at ``t0``."""
    return text[:int(max(0.0, t - t0) * cps)]


def rolling(final, t_end, t, seed=0, after_dot=None, swap=None):
    """Digits roll randomly until ``t_end``, then show ``final``.

    Only digits after the decimal point roll; if ``final`` has no point, all
    digits roll (``after_dot`` forces either behaviour).
    """
    if t >= t_end:
        return final
    r = random.Random(int(t * 30) * 977 + seed)
    out = []
    dot = ("." not in final) if after_dot is None else (not after_dot)
    for ch in final:
        if ch == ".":
            dot = True
        out.append(str(r.randint(0, 9)) if (ch.isdigit() and dot) else ch)
    s = "".join(out)
    return swap(s) if swap else s


class Canvas:
    def __init__(self, cols, rows, fg=(200, 204, 212)):
        self.cols, self.rows = cols, rows
        self.cells = [[[" ", fg, False] for _ in range(cols)] for _ in range(rows)]
        self.bg = {}           # row -> set of columns drawn on a black background
        self.paint = {}        # row -> {column: (r, g, b)} cells with a coloured background
        self.img = None        # photo shown in this frame (used by the Kitty layer)
        self.warnings = []

    def shade(self, x, y, n):
        self.bg.setdefault(y, set()).update(range(x, x + n))

    def set_bg(self, x, y, color):
        if 0 <= x < self.cols and 0 <= y < self.rows:
            self.paint.setdefault(y, {})[x] = tuple(color)

    def put(self, x, y, text, fg=(200, 204, 212), bold=False):
        for ch in text:
            if 0 <= x < self.cols and 0 <= y < self.rows:
                self.cells[y][x] = [ch, fg, bold]
                if cw(ch) == 2 and x + 1 < self.cols:
                    self.cells[y][x + 1] = ["", fg, bold]
            x += cw(ch)
        return x

    def fit(self, text, width, where):
        """Record a warning when ``text`` is wider than ``width`` cells."""
        if tw(text) > width:
            self.warnings.append((where, text, tw(text), width))
        return text

    def text(self):
        return "\n".join("".join(c[0] for c in row) for row in self.cells)

    def normalize(self):
        """Make every row exactly ``cols`` cells wide in a terminal. A wide character needs its
        second cell; when something narrow was drawn over that cell, a space gives way to the wide
        character and anything else wins over it. A second cell left without its wide character
        becomes a space. Without this a row can come out one cell longer and wrap onto the next."""
        for row in self.cells:
            x = 0
            while x < self.cols:
                ch, fg, bold = row[x]
                if ch == "":
                    row[x] = [" ", fg, bold]
                elif cw(ch[0]) == 2:
                    if x + 1 >= self.cols:
                        row[x] = [" ", fg, bold]
                    elif row[x + 1][0] == "":
                        x += 1
                    elif row[x + 1][0] == " ":
                        row[x + 1] = ["", fg, bold]
                        x += 1
                    else:
                        row[x] = [" ", fg, bold]
                x += 1
        return self


def encode(c, prev=None, left=0, top=0):
    """Escape codes that turn the terminal from ``prev`` into ``c`` (row diff), drawn ``left``
    columns and ``top`` rows away from the top-left corner."""
    out = []
    for y, row in enumerate(c.cells):
        if prev is not None and prev.cells[y] == row and prev.bg.get(y) == c.bg.get(y) \
                and prev.paint.get(y) == c.paint.get(y):
            continue
        out.append(f"\x1b[{y + 1 + top};{1 + left}H")
        last = None
        shaded = c.bg.get(y, ())
        painted = c.paint.get(y, {})
        for x, (ch, fg, bold) in enumerate(row):
            if ch == "":
                continue
            bgc = painted.get(x) or ((0, 0, 0) if x in shaded else None)
            key = (fg, bold, bgc)
            if key != last:
                bgs = f"48;2;{bgc[0]};{bgc[1]};{bgc[2]};" if bgc else ""
                out.append(f"\x1b[0;{'1;' if bold else ''}{bgs}38;2;{fg[0]};{fg[1]};{fg[2]}m")
                last = key
            out.append(ch)
        out.append("\x1b[0m")
    return "".join(out)


def stable_hash(s):
    """Deterministic string hash (Python's ``hash`` changes per process)."""
    import zlib
    return zlib.crc32(s.encode("utf-8"))


# ------------------------------------------------------------------ credit
CREDIT = "made with cinetty"


def _blank(c, x0, x1, y):
    return all(c.cells[y][x][0] == " " and x not in c.paint.get(y, {}) for x in range(max(0, x0), min(c.cols, x1)))


def credit_spot(c):
    """Where the credit goes: right-aligned on the bottom status row, or the row just below or
    above it, whichever has room. ``c`` is a typical frame. -> (x, y) or None."""
    n = tw(CREDIT)
    x = c.cols - n - 1
    used = [y for y in range(c.rows) if any(cell[0] not in (" ", "") for cell in c.cells[y])]
    if not used or x < 2:
        return None
    for y in (used[-1], used[-1] + 1, used[-1] - 1):
        if 0 <= y < c.rows and _blank(c, x - 2, c.cols, y):
            return x, y
    return None


def merged(frames):
    """One canvas whose cells are taken wherever any of ``frames`` draws something."""
    first = frames[0]
    m = Canvas(first.cols, first.rows)
    for f in frames:
        for y, row in enumerate(f.cells):
            for x, cell in enumerate(row):
                if cell[0] not in (" ", ""):
                    m.cells[y][x] = list(cell)
        for y, cols in f.paint.items():
            m.paint.setdefault(y, {}).update(cols)
    return m


def steady_credit_spot(render, duration, samples=24):
    """A credit spot that stays free for the whole animation, so the credit never blinks out."""
    return credit_spot(merged([render(duration * (i + 0.5) / samples) for i in range(samples)]))


def stamp_credit(c, spot, fg=BASE_COLORS["dim"]):
    """Draw the credit at ``spot`` when those cells are free in this frame (the check never sees it)."""
    if spot and _blank(c, spot[0] - 2, c.cols, spot[1]):
        c.put(spot[0], spot[1], CREDIT, fg)
