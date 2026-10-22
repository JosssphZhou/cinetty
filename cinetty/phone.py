"""The screen-flow board: an agent works a phone through a screen mirror and a hardware mouse.

A main box on top hands each screen to a decision model in the middle, with on-device text
recognition (OCR) on its left and a pixel-only vision fallback on its right. Two device cards
below do the work (one captures the screen, one taps), a confirm box collects the result, and
a two-line execution log and a status bar sit at the bottom.

Layout is fixed on a 94 x 37 grid. Texts come from the project's fields, motion from its
events (see ``EVENT_KEYS``). Events are applied one per frame and each waits until the packet
of the previous one has arrived, so the state is replayed frame by frame from the start; a
frame depends only on the project and the time.

The right half of the finished video is a phone screen recording (``fields.phone.clip``)
that the recorder places next to the board; this module draws only the board.
"""
from __future__ import annotations

import colorsys
import math
import unicodedata
from collections import deque

from .board import after_end, check_events
from .canvas import BASE_COLORS, BG, Canvas, mix
from .template import problem

W, H = 94, 37
PACKET = 1.0          # seconds a packet takes along a connecting line
OPEN = 1.0            # seconds the main box is lit at the start
SPIN = "◐◓◑◒"

EVENT_KEYS = {
    "dispatch": ({"to", "text"}, set()),
    "done": ({"text"}, {"final"}),
    "ocr": ({"boxes", "ms"}, set()),
    "decision": ({"question", "answer", "confidence", "outcome"}, {"candidates"}),
}
MAX_CANDIDATES = 3


# ------------------------------------------------------------------ text measure
def cw(ch):
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def tw(s):
    return sum(cw(ch) for ch in str(s))


def single_line(value):
    """The first line, with control characters turned into spaces."""
    lines = str(value if value is not None else "").splitlines()
    text = unicodedata.normalize("NFC", lines[0] if lines else "")
    return "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in text)


def fit(value, width):
    s = single_line(value)
    if tw(s) <= width:
        return s
    if width <= 0:
        return ""
    out = ""
    for ch in s:
        if tw(out) + cw(ch) > width - 1:
            break
        out += ch
    return out + "…"


def ring_cells(rect):
    x0, y0, x1, y1 = rect
    return ([(x, y0) for x in range(x0, x1 + 1)] + [(x1, y) for y in range(y0 + 1, y1 + 1)]
            + [(x, y1) for x in range(x1 - 1, x0 - 1, -1)] + [(x0, y) for y in range(y1 - 1, y0, -1)])


class Cv(Canvas):
    """Canvas with box bookkeeping; text is clipped at the right edge, never wrapped."""

    def __init__(self, cols, rows, fg):
        super().__init__(cols, rows, fg)
        self.boxes = []

    def put(self, x, y, value, fg=(232, 234, 238), bold=False):
        if not 0 <= y < self.rows:
            return x
        prev = None
        for ch in single_line(value):
            w = cw(ch)
            if w == 0:
                if prev is not None:
                    self.cells[y][prev][0] += ch
                continue
            if 0 <= x and x + w <= self.cols:
                self.cells[y][x] = [ch, fg, bold]
                prev = x
                if w == 2:
                    self.cells[y][x + 1] = ["", fg, bold]
            x += w
        return x

    def box(self, x0, y0, x1, y1, fg):
        self.boxes.append((x0, y0, x1, y1))
        self.put(x0, y0, "┌" + "─" * (x1 - x0 - 1) + "┐", fg)
        for y in range(y0 + 1, y1):
            self.put(x0, y, "│", fg)
            self.put(x1, y, "│", fg)
        self.put(x0, y1, "└" + "─" * (x1 - x0 - 1) + "┘", fg)

    def center(self, cx, y, value, fg, bold=False):
        left, right = 0, self.cols
        for x0, y0, x1, y1 in self.boxes:
            if x0 < cx < x1 and y0 < y < y1:
                left, right = max(left, x0 + 1), min(right, x1)
        value = fit(value, max(0, 2 * min(cx - left, right - cx)))
        return self.put(cx - tw(value) // 2, y, value, fg, bold)

    def inside(self, x0, x1, x, y, value, fg, bold=False):
        x = max(0, x0 + 1, x)
        self.put(x, y, fit(value, max(0, min(self.cols, x1) - x)), fg, bold)

    def border_errors(self):
        bad = []
        for x0, y0, x1, y1 in self.boxes:
            for x, y, ch in ((x0, y0, "┌"), (x1, y0, "┐"), (x0, y1, "└"), (x1, y1, "┘")):
                if self.cells[y][x][0] != ch:
                    bad.append((x, y))
            for y in range(y0 + 1, y1):
                bad += [(x, y) for x in (x0, x1) if self.cells[y][x][0] != "│"]
            for x in range(x0 + 1, x1):
                bad += [(x, y) for y in (y0, y1) if self.cells[y][x][0] != "─"]
        return bad


def layout():
    """Every rectangle and connector row, in cells (the grid is fixed at 94 x 37)."""
    L, R, gap, side = 1, W - 2, 2, 19
    axis = (L + R + 1) // 2
    top = 3
    mgr = (axis - 15, top, axis + 14, top + 3)
    my0, my1 = top + 5, top + 14
    adv = (L, my0, L + side - 1, my1)
    vf = (R - side + 1, my0, R, my1)
    jev = (L + side + gap, my0, R - side - gap, my1)
    cy0 = my1 + 2
    half = (R - L + 1 - gap) // 2
    cards = [(L, cy0, L + half - 1, cy0 + 5), (R - half + 1, cy0, R, cy0 + 5)]
    ry0 = cy0 + 7
    return {
        "w": W, "cx": W // 2, "title_y": 0, "sub_y": 1, "footer_y": H - 1,
        "mgr": mgr, "adv": adv, "jev": jev, "vf": vf, "cards": cards,
        "ret": (mgr[0], ry0, mgr[2], ry0 + 2), "log": (L, ry0 + 4, R, H - 3),
        "mcx": axis, "jcx": axis, "rcx": axis, "mgr_row": top + 4, "jev_row": my1 + 1, "split_row": my1 + 1,
        "card_row": cy0 + 6, "join_row": cy0 + 6, "card_cx": [(x0 + x1) // 2 for x0, _, x1, _ in cards],
        "vcx": (vf[0] + vf[2]) // 2, "arrow_y": (my0 + my1) // 2,
    }


LAYOUT = layout()


def valid(e):
    """An event the replay can use: a mapping with a numeric time (the check reports the rest)."""
    return isinstance(e, dict) and isinstance(e.get("t"), (int, float)) and not isinstance(e.get("t"), bool)


class PhoneBoard:
    def __init__(self, spec):
        self.spec = spec
        cv = spec["canvas"]
        self.cols, self.rows, self.fps = int(cv["cols"]), int(cv["rows"]), int(cv.get("fps", 30))
        self.total = float(spec["duration"])
        self.retention = float(spec.get("retention", 600))
        self.ocr_seconds = float(spec.get("ocr_seconds", 1.6))
        self.photos = None
        P = self.palette = dict(BASE_COLORS)
        for k, v in (spec.get("palette") or {}).items():
            P[k] = tuple(v)
        self.F = spec["texts"]
        self.devices = [str(d["id"]) for d in self.F["devices"]]
        # Every event as written, so problems point at the right index; the replay uses the valid ones.
        self.events = [dict(e) if isinstance(e, dict) else e for e in spec.get("_events") or []]
        h, m, s = str(self.F.get("clock_start", "12:00:00")).split(":")
        self.clock_ms = (int(h) * 3600 + int(m) * 60) * 1000 + round(float(s) * 1000)
        self.reset()

    # ---------------------------------------------------------- state
    def reset(self):
        self.pending = deque(sorted(((max(0.0, float(e["t"])), k) for k, e in enumerate(self.events) if valid(e)),
                                    key=lambda d: d[0]))
        self.pending = deque((due, self.events[k]) for due, k in self.pending)
        self.decisions = deque(maxlen=8)
        self.workers = {}
        self.recent = deque(maxlen=12)
        self.ocr_until = -1.0
        self.packet = None
        self.packet_started = self.packet_ends = 0.0
        self.packet_target = None
        self.arrival_kind = self.arrival_target = None
        self.arrived_until = -1.0
        self.sweep_started = self.sweep_until = -1.0
        self.next_ready = 0.0
        self.frame = 0
        self.ocr = None
        self.born = {}
        self.packet_label = ""
        self.final_at = None

    def duration(self):
        return self.total

    def clock(self, t):
        sec = (self.clock_ms + round(float(t) * 1000)) // 1000 % 86400
        return f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}"

    def _visible_targets(self):
        return {slot[0] for slot in self._slots() if slot is not None}

    def _apply(self, e, now):
        kind = e["type"]
        target = str(e.get("text") or "") if kind in ("dispatch", "done") else ""
        if kind == "dispatch":
            # One card per device: a new task replaces the device's previous one.
            for tg, wk in list(self.workers.items()):
                if wk["event"].get("to") == e.get("to"):
                    del self.workers[tg]
        if kind == "ocr":
            self.ocr = e
        # The vision fallback found the spot: it is done and the second device takes over.
        handoff = None
        if kind == "dispatch" and e.get("to") == self.devices[-1]:
            for tg, wk in self.workers.items():
                if wk["event"].get("to") == "vision" and wk["status"] == "run":
                    wk["status"], wk["expires"] = "done", now + self.retention
                    handoff = tg
        if kind == "decision":
            self.decisions.appendleft(e)
            self.sweep_started, self.sweep_until = now, now + 0.5
        elif kind == "dispatch":
            self.workers.pop(target, None)
            self.workers[target] = {"event": e, "status": "run", "expires": None}
            self.packet, self.packet_target = "jev_sub", target
        elif kind == "done":
            if target in self.workers:
                if target not in self._visible_targets():
                    self.workers[target] = self.workers.pop(target)
                self.workers[target]["status"] = "done"
                self.workers[target]["expires"] = now + self.retention
            self.packet, self.packet_target = "sub_ret", target
        elif kind == "ocr":
            self.ocr_until = now + self.ocr_seconds
            self.packet = None
        self.packet_started = now
        self.packet_ends = now + (0.5 if self.packet else 0.35)
        self.arrived_until = -1.0
        self.next_ready = self.packet_ends
        self.recent.appendleft(e)
        self.born[id(e)] = now
        if kind == "decision":
            self.packet = "main_jev"
        if kind == "dispatch" and e.get("to") == "vision":
            self.packet = "jev_vf"
        elif handoff is not None:
            self.packet = "vf_dev"
        if self.packet:
            self.packet_ends = now + PACKET
            self.next_ready = self.packet_ends
            self.packet_label = single_line(e.get("answer") or e.get("text") or "")
            if kind == "done":
                self.packet_label = "✓ " + self.packet_label
        if e.get("final"):
            self.final_at = self.packet_ends

    def step(self, now):
        for tg, wk in list(self.workers.items()):
            if wk["expires"] is not None and now >= wk["expires"]:
                del self.workers[tg]
        if self.pending and now >= self.next_ready and now >= self.pending[0][0]:
            self._apply(self.pending.popleft()[1], now)
        if self.packet and now >= self.packet_ends:
            self.arrival_kind, self.arrival_target = self.packet, self.packet_target
            self.arrived_until = now + 0.3
            self.packet = None
        self.frame += 1

    def advance(self, f):
        """Step the state through frame ``f`` (time f / fps)."""
        if self.frame > f + 1:
            self.reset()
        while self.frame <= f:
            self.step(self.frame / self.fps)

    def applied_times(self, until=None):
        """When each event actually starts (it may wait for the packet before it)."""
        self.reset()
        out = {}
        end = int((until or self.total) * self.fps)
        while self.frame <= end:
            self.step(self.frame / self.fps)
        for k, e in enumerate(self.events):
            if id(e) in self.born:
                out[k] = self.born[id(e)]
        self.reset()
        return out

    def render_frame(self, t):
        f = int(round(t * self.fps))
        self.advance(f)
        c = Cv(self.cols, self.rows, self.palette["white"])
        self.draw(c, f / self.fps)
        return c.normalize()

    # ---------------------------------------------------------- helpers
    def _slots(self):
        """(target, worker) per device card; the vision fallback has its own box."""
        workers = [(tg, wk) for tg, wk in self.workers.items() if wk["event"].get("to") != "vision"]
        slots, spill = [None] * len(self.devices), []
        for tg, wk in reversed(workers):
            to = wk["event"].get("to")
            index = self.devices.index(to) if to in self.devices else None
            if index is None or slots[index] is not None:
                spill.append((tg, wk))
            else:
                slots[index] = (tg, wk)
        free = [i for i, s in enumerate(slots) if s is None]
        rest = list(reversed(spill))[-len(free):] if free else []
        for i, item in zip(free, rest):
            slots[i] = item
        return slots

    def _vision(self):
        return next((wk for wk in self.workers.values() if wk["event"].get("to") == "vision"), None)

    def _target_x(self, target):
        for slot, x in zip(self._slots(), LAYOUT["card_cx"]):
            if slot is not None and slot[0] == target:
                return x
        return LAYOUT["card_cx"][len(LAYOUT["card_cx"]) // 2]

    @staticmethod
    def _run(y, a, b):
        step = 1 if b >= a else -1
        return [(x, y) for x in range(a, b + step, step)]

    def _path(self, kind, target):
        L = LAYOUT
        if kind == "main_jev":
            return self._run(L["mgr_row"], L["mcx"], L["jcx"])
        if kind == "jev_vf":
            return self._run(L["arrow_y"], L["jev"][2] + 1, L["vf"][0] - 1)
        if kind == "vf_dev":
            return [(L["vcx"], L["jev_row"])] + self._run(L["split_row"], L["vcx"], self._target_x(target))
        x = self._target_x(target)
        if kind == "jev_sub":
            return [(L["jcx"], L["jev_row"])] + self._run(L["split_row"], L["jcx"], x)
        return [(x, L["card_row"])] + self._run(L["join_row"], x, L["rcx"])

    def _decision_row(self, e):
        P, D = self.palette, self.F["decision"]
        try:
            value = max(0.0, min(1.0, float(e.get("confidence") or 0)))
        except (TypeError, ValueError):
            value = 0.0
        handoff = e.get("outcome") == "handoff"
        return (single_line(e.get("answer")), value, str(D["handoff"] if handoff else D["act"]),
                P["vision"] if handoff else P["action"])

    def _record(self, e):
        P, F = self.palette, self.F
        tags = F["log_tags"]
        kind = e["type"]
        if kind == "decision":
            answer, value, dest, _ = self._decision_row(e)
            return str(tags["decision"]), f"{single_line(e.get('question'))} → {answer}  {value:.2f}  {dest}", P["decision"]
        if kind == "dispatch" and e.get("to") == "vision":
            return str(tags["vision"]), single_line(e.get("text")), P["vision"]
        if kind == "dispatch":
            who = self._device(e.get("to")).get("log_name", "")
            return str(tags["action"]), f"{single_line(e.get('text'))} → {single_line(who)}", P["action"]
        if kind == "done":
            return str(tags["done"]), single_line(e.get("text")), P["running"]
        return str(tags["ocr"]), self._ocr_line(e), P["ocr"]

    def _ocr_line(self, e):
        return f"{e.get('boxes')} {self.F['ocr']['unit']}  {e.get('ms')} ms"

    def _device(self, key):
        for d in self.F["devices"]:
            if str(d["id"]) == str(key):
                return d
        return {}

    def _typed(self, e, text, now, cps=38):
        born = self.born.get(id(e))
        if born is None:
            return text, False
        n = int((now - born) * cps)
        return text[:n], n < len(text)

    def _stack(self, c, rect, lines):
        """Lines centred in a box, each by its own width; a typing line passes its full text
        as a fourth item so it does not move while it grows."""
        x0, y0, x1, y1 = rect
        top = y0 + 1 + (y1 - y0 - 1 - len(lines)) // 2
        for i, line in enumerate(lines):
            if line is None:
                continue
            text, fg, bold = line[:3]
            w = tw(line[3] if len(line) > 3 else text)
            c.put(x0 + 1 + (x1 - x0 - 1 - w) // 2, top + i, text, fg, bold)

    def _ring(self, c, rect, color, speed=2, length=10):
        ring = ring_cells(rect)
        bright = self.palette["bright"]
        for k in range(length):
            x, y = ring[(self.frame * speed - k) % len(ring)]
            c.cells[y][x][1] = mix(color, mix(color, bright, 0.3), 1 - k / length)

    # ---------------------------------------------------------- drawing
    def draw(self, c, now):
        P, F, L = self.palette, self.F, LAYOUT
        self._title(c, now)
        mgr = L["mgr"]
        main_lit = self.packet in ("main_jev", "sub_ret") or now < OPEN
        c.box(*mgr, mix(P["main"], P["bright"], 0.5 if main_lit else 0))
        self._stack(c, mgr, [(str(F["main"]["name"]), P["main"], True), (str(F["main"]["detail"]), P["white"], False)])
        self._connectors(c)
        self._draw_ocr(c, now)
        self._draw_jev(c, now)
        self._draw_vf(c, now)
        slots = self._slots()
        for i, rect in enumerate(L["cards"]):
            if slots[i] is not None:
                self._draw_card(c, rect, i, slots[i][1], slots[i][0])
            else:
                self._draw_card(c, rect, i, None, "")
        ret = L["ret"]
        lit = 0.0 if self.final_at is None else min(1.0, max(0.0, (now - self.final_at) / 0.4))
        edge = 0.5 if self.packet == "sub_ret" else 0.0
        if lit > 0:
            edge = lit * (0.3 + 0.25 * (0.5 + 0.5 * math.sin((now - self.final_at) * 2 * math.pi * 0.8)))
        CON = P["confirm"]
        c.box(*ret, mix(CON, P["bright"], edge))
        self._stack(c, ret, [(str(F["confirm"]), mix(mix(CON, P["white"], 0.25), mix(CON, P["bright"], 0.65), lit), lit > 0)])
        if self.packet:
            self._draw_packet(c, self._path(self.packet, self.packet_target), now)
        self._draw_log(c, now)
        self._draw_status(c)
        self._flow_borders(c, now)
        self._light_arrival(c, now)

    def _title(self, c, now):
        P, F, L = self.palette, self.F, LAYOUT
        words = str(F["title"]).split()
        title = "  ".join(" ".join(w) for w in words)
        if tw(title) > c.cols - 4:
            title = " ".join(words)
        x = L["cx"] - tw(title) // 2
        n = max(1, len(title))
        sweep = (now * 0.55) % 1.6 - 0.3
        for k, ch in enumerate(title):
            r, g, b = colorsys.hsv_to_rgb((k / n * 0.85 - now * 0.45) % 1.0, 0.72, 1.0)
            hit = max(0.0, 1 - abs(k / n - sweep) * 9)
            x = c.put(x, L["title_y"], ch, mix((int(r * 255), int(g * 255), int(b * 255)), P["bright"], 0.75 * hit), True)
        Lg = F["legend"]
        items = [(str(Lg[k]), P[k]) for k in ("main", "ocr", "decision", "action")]
        total = sum(tw(t) + 2 for t, _ in items) + 4 * (len(items) - 1)
        x = L["cx"] - total // 2
        for text, col in items:
            c.put(x, L["sub_y"], "■", col)
            x = c.put(x + 2, L["sub_y"], text, P["gray"]) + 4

    def _connectors(self, c):
        L, P = LAYOUT, self.palette
        LINE = P["line"]
        mcx, jcx, rcx = L["mcx"], L["jcx"], L["rcx"]
        c.put(mcx, L["mgr_row"], "┆", LINE)
        mgr, adv = L["mgr"], L["adv"]
        acx, my = (adv[0] + adv[2]) // 2, (mgr[1] + mgr[3]) // 2
        c.put(acx, my, "╭" + "┄" * (mgr[0] - acx - 1), LINE)
        for yy in range(my + 1, adv[1]):
            c.put(acx, yy, "┆", LINE)
        xs = L["card_cx"]
        c.put(jcx, L["jev_row"], "┆", LINE)
        y = L["split_row"]
        c.put(xs[0], y, "╭" + "┄" * (xs[-1] - xs[0] - 1) + "╮", LINE)
        c.put(jcx, y, "┴", LINE)
        for x in xs:
            c.put(x, L["card_row"], "┆", LINE)
        y = L["join_row"]
        c.put(xs[0], y, "╰" + "┄" * (xs[-1] - xs[0] - 1) + "╯", LINE)
        c.put(rcx, y, "┬", LINE)
        # Decision model -> vision fallback, and vision fallback -> the second device.
        lit = self.packet == "jev_vf"
        V = P["vision"]
        ay, ax0, ax1 = L["arrow_y"], L["jev"][2] + 1, L["vf"][0] - 1
        c.put(ax0, ay, "┄" * (ax1 - ax0), mix(V, P["bright"], 0.2) if lit else LINE)
        c.put(ax1, ay, "▶", V if lit else mix(LINE, P["gray"], 0.45))
        vcx, xd = L["vcx"], xs[-1]
        c.put(vcx, L["jev_row"], "┆", LINE)
        c.put(xd, L["split_row"], "┬", LINE)
        c.put(xd + 1, L["split_row"], "┄" * (vcx - xd - 1) + "╯", LINE)

    def _draw_ocr(self, c, now):
        P, O = self.palette, self.F["ocr"]
        adv = LAYOUT["adv"]
        on = now < self.ocr_until
        c.box(*adv, P["ocr"] if on else mix(BG, P["ocr"], 0.35))
        lines = [(str(O["name"]), P["ocr"] if on else P["white"], True), (str(O["detail"]), P["gray"], False),
                 (str(O["busy"] if on else O["idle"]), P["ocr"] if on else P["dim"], False)]
        if self.ocr is not None:
            lines += [None, (f"{self.ocr['boxes']} {O['unit']}", P["ocr"], True),
                      (f"{O.get('time_label') or ''} {self.ocr['ms']} ms".strip(), P["gray"], False)]
        self._stack(c, adv, lines)
        if on:
            ring = ring_cells(adv)
            for k in range(8):
                x, y = ring[(self.frame * 2 - k) % len(ring)]
                c.cells[y][x][1] = mix(P["ocr"], mix(P["ocr"], P["bright"], 0.3), 1 - k / 8)

    def _sweep(self, c, x0, y0, x1, now):
        if not self.sweep_started <= now <= self.sweep_until:
            return
        J = self.palette["decision"]
        center = x0 + round(min(1.0, (now - self.sweep_started) / 0.5) * (x1 - x0))
        for x in range(max(x0 + 1, center - 3), min(x1, center + 4)):
            c.cells[y0][x][1] = mix(J, self.palette["bright"], 1.0 - abs(x - center) / 4)

    def _columns(self, parts):
        """Columns of the decision rows: destination, confidence, bar (shared by check())."""
        D = self.F["decision"]
        x0, _, x1, _ = LAYOUT["jev"]
        dest_w = max([tw(p[2]) for p in parts] + [tw(str(D["picked"])), tw(str(D["no_text"]))])
        dest_x = x1 - 1 - dest_w
        conf_x = dest_x - 5
        longest = max([tw(single_line(e.get("answer"))) for e in self.events if valid(e) and e.get("type") == "decision"] + [4])
        bar_w = max(4, min(14, conf_x - 1 - (x0 + 2) - longest - 2))
        return dest_x, conf_x, conf_x - 1 - bar_w, bar_w

    def _draw_jev(self, c, now):
        P, D = self.palette, self.F["decision"]
        J = P["decision"]
        x0, y0, x1, y1 = LAYOUT["jev"]
        lit = self.packet in ("main_jev", "jev_vf")
        c.box(x0, y0, x1, y1, mix(J, P["bright"], 0.45 if lit else 0))
        self._sweep(c, x0, y0, x1, now)
        c.put(x0 + 2, y0 + 1, str(D["title"]), J, True)
        rows = max(0, (y1 - y0 - 2) // 2)
        shown = list(self.decisions)[:rows]
        if not shown:
            c.center((x0 + x1 + 1) // 2, (y0 + y1) // 2 + 1, str(D["waiting"]), P["dim"])
            return
        parts = [self._decision_row(e) for e in shown]
        dest_x, conf_x, bar_x, bar_w = self._columns(parts)
        grow_all = min(1.0, max(0.0, (now - self.sweep_started) / 0.8)) if self.sweep_started >= 0 else 1.0
        y = y0 + 2
        for i, (e, (answer, value, dest, color)) in enumerate(zip(shown, parts)):
            if y + 1 >= y1:
                break
            if i == 1:
                if y + 2 >= y1:
                    break
                c.put(x0 + 2, y, "┄" * (x1 - x0 - 3), P["line"])
                y += 1
            c.inside(x0, x1 - 9, x0 + 2, y, single_line(e.get("question")), P["dim"])
            c.put(x1 - 9, y, self.clock(e["t"]), P["dim"])
            text, typing = self._typed(e, answer, now)
            ax = c.put(x0 + 2, y + 1, text, P["bright"] if typing else P["white"], True)
            if typing:
                c.put(ax, y + 1, "▌", color)
            grow = grow_all if i == 0 else 1.0
            n = round(value * bar_w * grow)
            c.put(bar_x, y + 1, "━" * n, color)
            c.put(bar_x + n, y + 1, "━" * (bar_w - n), P["track"])
            c.put(conf_x, y + 1, f"{value * grow:.2f}", P["gray"])
            c.put(dest_x, y + 1, dest, color)
            y += 2
            if i == 0 and e.get("candidates"):
                y = self._draw_candidates(c, e, x0, y + 1, bar_x, bar_w, conf_x, dest_x, color, now) + 1

    def _draw_candidates(self, c, e, x0, y, bar_x, bar_w, conf_x, dest_x, color, now):
        P, D = self.palette, self.F["decision"]
        born = self.born.get(id(e), -99.0)
        y1 = LAYOUT["jev"][3]
        if y >= y1:
            return y
        c.put(x0 + 4, y, str(D["candidates_title"]), P["dim"])
        y += 1
        for k, cand in enumerate(e["candidates"]):
            if y >= y1:
                break
            t0 = born + 0.35 + k * 0.14
            if now < t0:
                break
            g = min(1.0, (now - t0) / 0.4)
            pick = cand.get("pick")
            col = color if pick else P["gray"]
            c.put(x0 + 4, y, ("▸ " if pick else "  ") + str(cand["text"]), P["decision"] if pick else P["gray"], bool(pick))
            if cand.get("confidence") is not None:
                n = round(cand["confidence"] * bar_w * g)
                c.put(bar_x, y, "━" * n, mix(BG, col, 0.9 if pick else 0.55))
                c.put(bar_x + n, y, "━" * (bar_w - n), P["track"])
                c.put(conf_x, y, f"{cand['confidence'] * g:.2f}", P["gray"])
            if pick:
                c.put(dest_x, y, str(D["no_text"] if cand.get("confidence") is None else D["picked"]), color, True)
            y += 1
        return y

    def _draw_vf(self, c, now):
        P, V, S = self.palette, self.F["vision"], self.F["device_states"]
        HAND = P["vision"]
        rect = LAYOUT["vf"]
        wk = self._vision()
        busy = wk is not None and wk["status"] == "run"
        done = wk is not None and not busy
        c.box(*rect, HAND if busy else mix(BG, HAND, 0.75 if done else 0.35))
        status = (str(V["busy"]), HAND) if busy else ("✓ " + str(S["done"]), P["action"]) if done else (str(V["idle"]), P["dim"])
        lines = [(str(V["name"]), HAND if busy else P["white"], True), (str(V["detail"]), P["gray"], False),
                 (status[0], status[1], busy or done)]
        if wk is not None:
            # The spot it found is typed out once the packet has arrived.
            target = single_line(wk["event"].get("text"))
            born = self.born.get(id(wk["event"]))
            start = (born if born is not None else -99.0) + PACKET + 0.2
            shown = target[:max(0, int((now - start) * 38))]
            lines += [None, (shown, P["bright"] if len(shown) < len(target) else HAND, True, target)]
        self._stack(c, rect, lines)
        if busy:
            self._ring(c, rect, HAND, speed=3, length=14)

    def _draw_card(self, c, rect, i, wk, target):
        P, S = self.palette, self.F["device_states"]
        d = self.F["devices"][i]
        x0, y0, x1, y1 = rect
        inner = x1 - x0 - 3
        if wk is None:
            c.box(x0, y0, x1, y1, P["empty"])
            self._stack(c, rect, [(fit(d["name"], inner), P["dim"], False), (fit(d["detail"], inner), P["empty_text"], False),
                                  ("○ " + str(S["idle"]), P["empty_text"], False)])
            return
        run = wk["status"] == "run"
        col = P["running"] if run else P["action"]
        c.box(x0, y0, x1, y1, mix(BG, col, 0.75))
        mark = SPIN[(self.frame // 4) % 4] + " " if run else "✓ "
        self._stack(c, rect, [(fit(d["name"], inner), P["white"], True), (fit(d["detail"], inner), P["gray"], False),
                              (fit(target, inner), P["white"], False),
                              (mark + str(S["running"] if run else S["done"]), col, True)])
        if run:
            self._ring(c, rect, col, speed=3, length=14)

    def _draw_packet(self, c, points, now):
        if not points:
            return
        P = self.palette
        progress = min(1.0, max(0.0, (now - self.packet_started) / PACKET))
        progress = 1 - (1 - progress) ** 2
        head = int(progress * (len(points) - 1))
        col = (P["action"] if self.packet in ("jev_sub", "vf_dev") else P["running"] if self.packet == "sub_ret"
               else P["vision"] if self.packet == "jev_vf" else P["decision"])
        trail = (("●", 1.0), ("•", 0.8), ("•", 0.62), ("∙", 0.48), ("∙", 0.36), ("·", 0.26), ("·", 0.18), ("·", 0.12))
        for k, (ch, inten) in enumerate(trail):
            j = head - k
            if j >= 0:
                x, y = points[j]
                if c.cells[y][x][0] not in "┌┐└┘│":
                    c.put(x, y, ch, P["bright"] if k == 0 else mix(BG, col, inten), True)
        # The task's words ride behind the trail.
        label = "" if self.packet == "jev_vf" else self.packet_label
        hx, hy = points[head]
        if label and head > 0:
            rightward = points[-1][0] >= points[0][0]
            gap = len(trail) + 1
            x = hx - gap - tw(label) if rightward else hx + gap
            fade = min(1.0, (now - self.packet_started) / 0.15)
            c.put(x, hy, label, mix(BG, mix(col, P["bright"], 0.35), fade), True)

    def _draw_log(self, c, now):
        P, F = self.palette, self.F
        log = LAYOUT["log"]
        c.box(*log, P["line"])
        c.put(log[0] + 2, log[1] + 1, str(F["log_title"]), P["gray"])
        rows = max(0, log[3] - log[1] - 2)
        pad = max(tw(str(v)) for v in F["log_tags"].values())
        for i, e in enumerate(list(self.recent)[:rows]):
            y = log[1] + 2 + i
            label, desc, color = self._record(e)
            x = c.put(log[0] + 2, y, self.clock(e["t"]), P["dim"])
            x = c.put(x + 2, y, label + " " * (pad - tw(label)), color, True)
            text, typing = self._typed(e, desc, now, cps=110)
            tx = c.put(x + 2, y, text, P["bright"] if typing else P["white"])
            if typing:
                c.put(tx, y, "▌", color)
                if i == 0:
                    for x in range(log[0] + 1, log[2]):
                        c.set_bg(x, y, mix(c.paint.get(y, {}).get(x, BG), color, 0.18))

    def _draw_status(self, c):
        P = self.palette
        x, y = 1, LAYOUT["footer_y"]
        for part in self.F["status"]:
            x = c.put(x, y, str(part["key"]) + " ", P["dim"])
            x = c.put(x, y, "[", P["dim"])
            x = c.put(x, y, str(part["value"]), P["action"], True)
            x = c.put(x, y, "]", P["dim"]) + 3

    def _active_box(self, now):
        L = LAYOUT
        if now < OPEN:
            return L["mgr"]
        if self.packet == "main_jev":
            return L["jev"]
        if self.packet == "sub_ret":
            return L["ret"]
        if self.packet == "jev_vf":
            return L["vf"]
        if self.packet in ("jev_sub", "vf_dev"):
            for slot, rect in zip(self._slots(), L["cards"]):
                if slot is not None and slot[0] == self.packet_target:
                    return rect
        if now < self.ocr_until:
            return L["adv"]
        if self.final_at is not None and now >= self.final_at:
            return L["ret"]
        return None

    def _flow_borders(self, c, now):
        """A short light runs around every border; faster and brighter on the current step's box."""
        active = self._active_box(now)
        bright = self.palette["bright"]
        for n, rect in enumerate(c.boxes):
            x0, y0, _, _ = rect
            ring = ring_cells(rect)
            base = c.cells[y0][x0][1]
            top = max(base) or 1
            glow = mix(tuple(min(255, int(v * 255 / top)) for v in base), bright, 0.15)
            hot = rect == active
            speed, length, strength = (3.2, 18, 1.0) if hot else (1.3, 12, 0.75)
            head = int(now * 30 * speed + n * len(ring) / 3.7)
            for k in range(length):
                x, y = ring[(head - k) % len(ring)]
                cell = c.cells[y][x]
                cell[1] = mix(cell[1], glow, strength * (1 - k / length))

    def _arrival_box(self):
        L = LAYOUT
        kind = self.arrival_kind
        if kind == "main_jev":
            return L["jev"]
        if kind == "sub_ret":
            return L["ret"]
        if kind == "jev_vf":
            return L["vf"]
        if kind in ("jev_sub", "vf_dev"):
            for slot, rect in zip(self._slots(), L["cards"]):
                if slot is not None and slot[0] == self.arrival_target:
                    return rect
        return None

    def _light_arrival(self, c, now):
        if now >= self.arrived_until:
            return
        box = self._arrival_box()
        if box not in c.boxes:
            return
        for x, y in ring_cells(box):
            c.cells[y][x][1] = mix(c.cells[y][x][1], self.palette["bright"], 0.85)

    # ---------------------------------------------------------- checks
    def check(self):
        F, out = self.F, []
        V = F["vision"]
        out += check_events(self.events, EVENT_KEYS, {"to": self.devices + ["vision"], "outcome": ["act", "handoff"]},
                            self.total)
        log_room = (LAYOUT["log"][2] - 1) - (LAYOUT["log"][0] + 2 + 8 + 2 + max(tw(str(v)) for v in F["log_tags"].values()) + 2)
        sent = set()
        parts = [self._decision_row(e) for e in self.events if valid(e) and e.get("type") == "decision"]
        dest_x, conf_x, bar_x, bar_w = self._columns(parts)
        x0 = LAYOUT["jev"][0]
        answer_room = conf_x - 1 - (x0 + 2) - 2 - 4      # keep the bar at least 4 cells long
        for i, e in enumerate(self.events):
            p = f"events[{i}]"
            if not valid(e):
                continue
            kind = e.get("type")
            if kind not in EVENT_KEYS:
                continue

            def wide(key, limit, why, text=None):
                s = single_line(e.get(key) if text is None else text)
                if tw(s) > limit:
                    out.append(problem("too_long_on_screen", f"{p}.{key}", f"{why} holds {limit} cells",
                                       actual=tw(s), limit=limit, over=tw(s) - limit, text=s, time=e.get("t")))
            for key in ("text", "question", "answer"):
                if key in e and not isinstance(e[key], str):
                    out.append(problem("wrong_type", f"{p}.{key}", "write this as text (quote it)", actual=e[key]))
            if kind == "dispatch":
                sent.add(str(e.get("text")))
                if e.get("to") == "vision":
                    wide("text", 15, "the vision box")
                else:
                    wide("text", LAYOUT["cards"][0][2] - LAYOUT["cards"][0][0] - 3, "a device card")
            if kind == "done":
                if str(e.get("text")) not in sent:
                    out.append(problem("unknown_ref", f"{p}.text", "a done event repeats the text of an earlier dispatch",
                                       actual=e.get("text")))
                if "final" in e and not isinstance(e["final"], bool):
                    out.append(problem("wrong_type", f"{p}.final", "write true or false", actual=e["final"]))
            if kind == "ocr":
                if not isinstance(e.get("boxes"), int) or isinstance(e.get("boxes"), bool) or e["boxes"] < 0:
                    out.append(problem("wrong_type", f"{p}.boxes", "the number of text boxes found (a whole number)",
                                       actual=e.get("boxes")))
                if not isinstance(e.get("ms"), (int, float, str)) or isinstance(e.get("ms"), bool):
                    out.append(problem("wrong_type", f"{p}.ms", "milliseconds, for example 270.1", actual=e.get("ms")))
                O = F["ocr"]
                wide("boxes", 15, "the OCR box", f"{e.get('boxes')} {O['unit']}")
                wide("ms", 15, "the OCR box", f"{O.get('time_label') or ''} {e.get('ms')} ms".strip())
            if kind == "decision":
                v = e.get("confidence")
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 1:
                    out.append(problem("out_of_range", f"{p}.confidence", "a confidence from 0 to 1", actual=v))
                wide("question", LAYOUT["jev"][2] - 9 - (x0 + 2) - 1, "the question row of the decision box")
                wide("answer", answer_room, "the answer row of the decision box (with the widest outcome word)")
                cands = e.get("candidates")
                if cands is not None:
                    if not isinstance(cands, list):
                        out.append(problem("wrong_type", f"{p}.candidates", "a list of {text, confidence, pick}"))
                        cands = []
                    if len(cands) > MAX_CANDIDATES:
                        out.append(problem("too_many", f"{p}.candidates", f"the decision box shows {MAX_CANDIDATES} candidates",
                                           actual=len(cands), limit=MAX_CANDIDATES, over=len(cands) - MAX_CANDIDATES))
                    for j, cd in enumerate(cands):
                        q = f"{p}.candidates[{j}]"
                        if not isinstance(cd, dict) or not isinstance(cd.get("text"), str):
                            out.append(problem("wrong_type", q, "write {text: ..., confidence: 0.5, pick: true}"))
                            continue
                        for k in sorted(set(cd) - {"text", "confidence", "pick"}):
                            out.append(problem("unknown_field", f"{q}.{k}", "a candidate takes: text, confidence, pick"))
                        cv = cd.get("confidence")
                        if cv is not None and (not isinstance(cv, (int, float)) or isinstance(cv, bool) or not 0 <= cv <= 1):
                            out.append(problem("out_of_range", f"{q}.confidence", "a confidence from 0 to 1, or null", actual=cv))
                        room = (bar_x - 1 if cv is not None else dest_x - 1) - (x0 + 6)
                        s = cd["text"]
                        if tw(s) > room:
                            out.append(problem("too_long_on_screen", f"{q}.text", f"a candidate row holds {room} cells here",
                                               actual=tw(s), limit=room, over=tw(s) - room, text=s, time=e.get("t")))
            label, desc, _ = self._record(e)
            if tw(desc) > log_room:
                out.append(problem("too_long_on_screen", p, f"its log line is {tw(desc)} cells; the log holds {log_room}",
                                   actual=tw(desc), limit=log_room, over=tw(desc) - log_room, text=desc, time=e.get("t")))
        if self.devices and len(set(self.devices)) != len(self.devices) or "vision" in self.devices:
            out.append(problem("duplicate", "fields.devices", "give each device its own id (and not 'vision')"))
        words = str(F["title"]).split()
        title = "  ".join(" ".join(w) for w in words)
        if tw(title) > W - 4 and tw(" ".join(words)) > W - 4:
            out.append(problem("too_long_on_screen", "fields.title", f"the title holds {W - 4} cells",
                               actual=tw(" ".join(words)), limit=W - 4))
        n = sum(tw(str(F["legend"][k])) + 2 for k in ("main", "ocr", "decision", "action")) + 12
        if n > W - 4:
            out.append(problem("too_long_on_screen", "fields.legend", f"the legend line is {n} cells; it holds {W - 4}",
                               actual=n, limit=W - 4, over=n - W + 4))
        n = sum(tw(str(s["key"])) + tw(str(s["value"])) + 3 + 3 for s in F["status"]) - 3
        if 1 + n > W - 1:
            out.append(problem("too_long_on_screen", "fields.status", f"the status line needs {n} cells; it holds {W - 2}",
                               actual=n, limit=W - 2, over=n - W + 2))
        if tw("✓ " + str(F["device_states"]["done"])) > 15:
            out.append(problem("too_long_on_screen", "fields.device_states.done", "the vision box shows it after '✓ ' in 15 cells",
                               actual=tw(str(F["device_states"]["done"])), limit=13))
        if not out:
            out += self._check_timing()
        if not out:
            out += self._check_frames()
        return out

    def _check_timing(self):
        """Each event waits for the packet of the one before, so it can start later than its t.
        Every event must start, and a final one must arrive, before the animation ends."""
        out = []
        started = self.applied_times(self.total)
        for k, e in enumerate(self.events):
            p = f"events[{k}].t"
            if not valid(e):
                continue
            if k not in started or started[k] >= self.total:
                out.append(after_end(p, e["t"], self.total, " (it waits for the steps before it, about 1 s each)"))
            elif e.get("final") and started[k] + PACKET > self.total:
                out.append(after_end(p, started[k] + PACKET, self.total,
                                     " (a final step needs about 1 s after it starts to reach the result)"))
        return out

    def _check_frames(self):
        """Play every frame and report a box border that text ran over."""
        out = []
        for f in range(int(self.total * self.fps)):
            c = self.render_frame(f / self.fps)
            bad = c.border_errors()
            if bad:
                x, y = bad[0]
                out.append(problem("too_long_on_screen", "fields", f"text runs over a box border at column {x}, row {y}",
                                   time=round(f / self.fps, 2)))
                break
        self.reset()
        return out
