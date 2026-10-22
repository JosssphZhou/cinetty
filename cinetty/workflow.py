"""The pipeline board: a main session hands work to a router, the router dispatches it
to one, two or three workers, an advisor column comments at three moments, and every handover runs as
a packet along the connecting lines.

Layout is fixed on a 90 x 46 grid. Texts come from the project's fields; motion from its
events (see ``EVENT_KEYS``). State is replayed frame by frame from the start, so a frame
depends only on the project and the time. Every number on the board comes from the project: the
router's counter and the advisor's token count change only where an event gives a new value, and the
advisor's call count is the number of advise events that have started.
"""
from __future__ import annotations

import colorsys
import math
import random

from .board import after_end, check_events
from .canvas import BASE_COLORS, BG, Canvas, cw, mix, tw
from .template import problem

W, H = 90, 46
CX = 57                    # centre column of the main flow
BR = [36, 57, 78]          # centre columns of the three worker card slots
SLOTS = {1: [CX], 2: [BR[0], BR[2]], 3: BR}   # slots used for 1, 2 or 3 workers; unused ones stay empty
AX0, AX1 = 2, 24           # advisor column borders
TXT_MAX = AX1 - 1
MOMENT_ROWS = {0: 6, 1: 26, 2: 34}
MOMENT_LINES = {0: (6, AX1 + 1, 42), 1: (26, AX1 + 1, 25), 2: (34, AX1 + 1, 39)}   # moment 1 ends at the first card
SPIN = "◐◓◑◒"
COUNTER_LABEL_X, COUNTER_END = 61, 76   # the router's counter label starts here; its number ends here

EVENT_KEYS = {
    "advise": ({"until", "moment", "lines", "who", "log"}, {"log_end", "hold_card", "tokens"}),
    "log": ({"who", "text"}, {"route", "card", "result", "forks"}),
    "decision": ({"who", "text", "row", "p"}, {"route", "card", "forks"}),
    "review": ({"until"}, set()),
}
ROUTES = ("plan", "escalate", "dispatch", "handback")


def hline(y, x0, x1):
    step = 1 if x1 >= x0 else -1
    return [(x, y) for x in range(x0, x1 + step, step)]


def route_cells(kind, x=CX):
    """Cells a packet runs through (``x`` is the worker card's centre column); only between
    boxes, never over a box border."""
    if kind == "plan":          # main session -> router
        return [(CX, 9), (CX, 10)]
    if kind == "escalate":      # router -> main session (not sure enough)
        return [(CX, 10), (CX, 9)]
    if kind == "dispatch":      # router -> worker i
        return [(CX, 18), (CX, 19), (CX, 20)] + hline(21, CX, x) + [(x, 22)]
    if kind == "handback":      # worker i -> review
        return [(x, 30)] + hline(31, x, CX) + [(CX, 32)]
    raise ValueError(kind)


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def valid(e):
    """An event the replay can use: a mapping with numeric times (the check reports the rest)."""
    return isinstance(e, dict) and number(e.get("t")) and (e.get("type") not in ("advise", "review") or number(e.get("until")))


class Put(Canvas):
    """Canvas helpers in the original's terms (put, center, segs, box)."""

    def center(self, cx, y, text, fg, bold=False):
        return self.put(cx - tw(text) // 2, y, text, fg, bold)

    def segs(self, x, y, parts):
        for p in parts:
            x = self.put(x, y, p[0], p[1], p[2] if len(p) > 2 else False)
        return x

    def box(self, x0, y0, x1, y1, fg):
        self.put(x0, y0, "┌" + "─" * (x1 - x0 - 1) + "┐", fg)
        for y in range(y0 + 1, y1):
            self.put(x0, y, "│", fg)
            self.put(x1, y, "│", fg)
        self.put(x0, y1, "└" + "─" * (x1 - x0 - 1) + "┘", fg)


class State:
    def __init__(self, B):
        self.B = B
        self.frame = 0
        self.start()
        self.log = []
        self.rows = [float(v) for v in B.F["router"]["start_values"]]
        self.advice = ["", ""]
        self.adv_full = ["", ""]
        self.adv_started = -1
        self.done = set()
        self.status = ["idle"] * B.n
        self.packets = []
        self.flash = {}
        self.last_cycle = -1

    def start(self):
        """Counters at the start of a cycle: the project's starting values."""
        self.forks = self.forks_goal = int(self.B.F["router"]["counter_start"])
        self.peak = self.forks
        self.calls = 0
        self.tokens = int(self.B.F["advisor"]["tokens_start"])

    def set_forks(self, n):
        """The router's counter is ``n`` from now on; it counts up to it over a few frames."""
        self.forks_goal = n
        self.peak = max(self.peak, n)
        if n < self.forks:
            self.forks = n

    def t(self):
        return self.frame / self.B.fps

    def say(self, who, text, p=None, route_label=None):
        self.log.append((self.B.clock(self.t()), who, text, p, route_label))
        self.log = self.log[-4:]

    def launch(self, kind, i):
        pts = route_cells(kind, self.B.slots[i] if kind in ("dispatch", "handback") else CX)
        frames = max(int(self.B.fps * 0.35), int(len(pts) / 40 * self.B.fps))
        self.packets.append([pts, self.frame, frames, self.B.route_color[kind], (kind, i)])

    def arrive(self, kind, i):
        if kind == "dispatch" and self.status[i] in ("idle", "wait", "done", "pass"):
            self.status[i] = "run"
        elif kind == "handback":
            self.flash["return"] = self.frame
        elif kind == "escalate":
            self.flash["main"] = self.frame
        elif kind == "plan":
            self.flash["router"] = self.frame

    def step(self):
        B = self.B
        self.frame += 1
        t = self.t()
        ct = t % B.cycle
        cycle = int(t // B.cycle)
        if cycle != self.last_cycle:
            self.last_cycle = cycle
            self.done = set()
            self.status = ["idle"] * B.n
            self.start()
        if self.forks < self.forks_goal:
            self.forks += max(1, (self.forks_goal - self.forks) // 6)
        a = B.advisor_now(ct)
        if a:
            k, e = a
            if (k, "start") not in self.done:
                self.done.add((k, "start"))
                self.calls += 1
                if "tokens" in e:
                    self.tokens = int(e["tokens"])
                self.adv_full = [str(x) for x in e["lines"]] + [""] * (2 - len(e["lines"]))
                self.adv_started = self.frame
                self.say(e["who"], e["log"])
                if "hold_card" in e:
                    self.status[int(e["hold_card"])] = "wait"
            if ct > float(e["until"]) - 0.35 and (k, "end") not in self.done:
                self.done.add((k, "end"))
                if e.get("log_end"):
                    self.say(e["who"], e["log_end"])
            n = (self.frame - self.adv_started) // 2
            self.advice = [self.adv_full[0][:n], self.adv_full[1][:max(0, n - len(self.adv_full[0]))]]
        for k, e in B.flow:
            if ct >= float(e["t"]) and ("ev", k) not in self.done:
                self.done.add(("ev", k))
                if e["type"] == "decision":
                    p = float(e["p"])
                    self.rows[int(e["row"])] = p
                    R = B.F["router"]
                    self.say(e["who"], e["text"], p, R["sharp_route"] if p >= 0.7 else R["split_route"])
                else:
                    self.say(e["who"], e["text"])
                if "forks" in e:
                    self.set_forks(int(e["forks"]))
                if e.get("route"):
                    i = int(e.get("card", 0))
                    self.launch(e["route"], i)
                    if e["route"] == "handback":
                        self.status[i] = "pass" if e.get("result") == "passed" else "done"
        alive = []
        for pkt in self.packets:
            pts, f0, frames, col, (kind, i) = pkt
            if self.frame - f0 >= frames:
                self.arrive(kind, i)
            else:
                alive.append(pkt)
        self.packets = alive


class WorkflowBoard:
    def __init__(self, spec):
        self.spec = spec
        cv = spec["canvas"]
        self.cols, self.rows, self.fps = int(cv["cols"]), int(cv["rows"]), int(cv.get("fps", 30))
        self.total = float(spec["duration"])
        self.cycle = float(spec.get("cycle", self.total))
        self.photos = None
        self.palette = dict(BASE_COLORS)
        for k, v in (spec.get("palette") or {}).items():
            self.palette[k] = tuple(v)
        P = self.palette
        self.route_color = {"plan": P["main"], "escalate": P["main"], "dispatch": P["router"], "handback": P["workers"]}
        self.F = spec["texts"]
        self.n = len(self.F["workers"])
        self.slots = SLOTS.get(self.n, BR)
        self.events = spec.get("_events") or []
        self.advises = [(k, e) for k, e in enumerate(self.events) if valid(e) and e.get("type") == "advise"]
        self.flow = [(k, e) for k, e in enumerate(self.events) if valid(e) and e.get("type") in ("log", "decision")]
        self.reviews = [e for e in self.events if valid(e) and e.get("type") == "review"]
        self.who_color = {str(p["name"]): P[p["role"]] for p in self.F["participants"]}
        self._state = None

    def duration(self):
        return self.total

    def clock(self, ts):
        h, m, s = (int(x) for x in str(self.F.get("clock_start", "12:00:00")).split(":"))
        sec = (h * 3600 + m * 60 + s + int(ts)) % 86400
        return f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}"

    def advisor_now(self, ct):
        for k, e in self.advises:
            if float(e["t"]) <= ct < float(e["until"]):
                return k, e
        return None

    def state_at(self, f):
        s = self._state
        if s is None or s.frame > f:
            s = State(self)
        while s.frame < f:
            s.step()
        self._state = s
        return s

    def counter_max(self):
        """The largest value the router's counter reaches, from a full replay."""
        s = State(self)
        while s.frame < int(round(self.total * self.fps)):
            s.step()
        return s.peak

    def render_frame(self, t):
        s = self.state_at(int(round(t * self.fps)))
        c = Put(self.cols, self.rows, self.palette["white"])
        self.draw(c, s)
        return c.normalize()

    # ---------------------------------------------------------- drawing
    def draw(self, c, s):
        P, F = self.palette, self.F
        DIM, GRAY, WHITE, BRIGHT = P["dim"], P["gray"], P["white"], P["bright"]
        ORANGE, BLUE, GREEN, PURPLE, HL = P["main"], P["workers"], P["router"], P["advisor"], P["highlight"]
        f = s.frame
        ct = s.t() % self.cycle
        a = self.advisor_now(ct)
        trig = int(a[1]["moment"]) if a else None
        adv_p = (ct - float(a[1]["t"])) / (float(a[1]["until"]) - float(a[1]["t"])) if a else 0

        # title and legend
        title = "   ".join(" ".join(w) for w in str(F["title"]).split())
        x = (W - tw(title)) // 2
        for k, ch in enumerate(title):
            r, g, b = colorsys.hsv_to_rgb((k * 0.04 - f * 0.012) % 1.0, 0.55, 1.0)
            x = c.put(x, 0, ch, (int(r * 255), int(g * 255), int(b * 255)), True)
        c.put(2, 1, "─" * (W - 4), DIM)
        L = F["legend"]
        legend = [("■", ORANGE), (" " + L["main"], GRAY), ("    ", DIM), ("■", BLUE), (" " + L["workers"], GRAY),
                  ("    ", DIM), ("■", GREEN), (" " + L["router"], GRAY), ("    ", DIM), ("■", PURPLE),
                  (" " + L["advisor"], GRAY)]
        c.segs((W - sum(tw(p[0]) for p in legend)) // 2, 2, legend)

        # advisor column
        A = F["advisor"]

        def text(x, y, t_, fg, bold=False):
            room = TXT_MAX - x + 1
            out, used = "", 0
            for ch in t_:
                if used + cw(ch) > room:
                    break
                out += ch
                used += cw(ch)
            c.put(x, y, out, fg, bold)

        adv_on = trig is not None
        base = mix(mix(BG, PURPLE, 0.55), PURPLE, 0.5 + 0.5 * math.sin(f * 0.08)) if not adv_on else PURPLE
        c.box(AX0, 3, AX1, 36, base)
        if adv_on:
            ring = ([(x, 3) for x in range(AX0, AX1 + 1)] + [(AX1, y) for y in range(4, 36)]
                    + [(x, 36) for x in range(AX1, AX0 - 1, -1)] + [(AX0, y) for y in range(35, 3, -1)])
            head = (f * 2) % len(ring)
            for k in range(10):
                x, y = ring[(head - k) % len(ring)]
                cell = c.cells[y][x]
                cell[1] = mix(PURPLE, BRIGHT, 1 - k / 10)
                cell[2] = True
        name = str(A["name"])
        text(AX0 + 1 + (AX1 - AX0 - 1 - tw(name)) // 2, 4, name, mix(PURPLE, BRIGHT, 0.35 if adv_on else 0), True)
        state = str(A["state_active"] if adv_on else A["state_idle"])
        text(AX0 + 1 + (AX1 - AX0 - 1 - tw(state)) // 2, 5, state,
             mix(PURPLE, BRIGHT, 0.5 + 0.5 * math.sin(f * 0.5)) if adv_on else PURPLE, adv_on)
        for y in range(7, 34):
            if y not in MOMENT_ROWS.values():
                c.put(4, y, "┆", mix(BG, PURPLE, 0.8 if adv_on else 0.45))
        for i, y in MOMENT_ROWS.items():
            if trig == i:
                sweep = AX0 + 1 + (f * 1.5) % (AX1 - AX0 + 6)
                for x in range(AX0 + 1, AX1):
                    c.set_bg(x, y, mix(HL, (150, 120, 230), max(0.0, 1 - abs(x - sweep) / 5) * 0.8))
                text(4, y, "◆ " + str(A["moments"][i]), BRIGHT, True)
            else:
                text(4, y, "◇ " + str(A["moments"][i]), WHITE)
        for k, line in enumerate(A["about"]):
            text(6, 8 + k, str(line), mix(GRAY, WHITE, 0.4) if trig == 0 else GRAY)
        text(6, 14, str(A["advice_label"]), GRAY)
        for k in range(2):
            t_ = s.advice[k] if adv_on else s.adv_full[k]
            if t_ or (adv_on and k == 0):
                text(6, 15 + k, "» " + t_, PURPLE, True)
                if adv_on and t_ and len(t_) < len(s.adv_full[k]):
                    text(8 + tw(t_), 15 + k, "▌", BRIGHT)
        text(6, 18, str(A["calls_label"]), GRAY)
        text(TXT_MAX - len(str(s.calls)), 18, str(s.calls), WHITE, True)
        text(6, 19, str(A["tokens_label"]), GRAY)
        text(8, 20, f"{s.tokens}k", WHITE, True)
        for k, line in enumerate(A["quiet"]):
            text(6, 22 + k, str(line), GRAY)
        for k, line in enumerate(A["rule"]):
            text(6, 29 + k, str(line), GRAY)
        if adv_on:
            rnd = random.Random(f // 3)
            for _ in range(6):
                x, y = rnd.randint(AX0 + 2, AX1 - 2), rnd.randint(7, 35)
                if all(c.cells[y][xx][0] == " " for xx in (x - 1, x, x + 1)):
                    c.put(x, y, rnd.choice(["✦", "·", "⋆", "·"]), mix(BG, PURPLE, rnd.uniform(0.4, 1.0)))
        for i, (y, x0, x1) in MOMENT_LINES.items():
            if i == 1:
                x1 = self.slots[0] - 11          # just left of the first worker card
            on = trig == i
            col = PURPLE if on else mix(BG, PURPLE, 0.4)
            for x in range(x0, x1):
                c.put(x, y, "╌" if on else "-", col)
            c.put(x1, y, "▸", mix(PURPLE, BRIGHT, 0.5) if on else col, on)
            if on and x1 > x0:
                px = x0 + int(min(1.0, adv_p * 1.6) * (x1 - x0))
                for k, ch in enumerate(["●", "•", "∙", "·"]):
                    if px - k >= x0:
                        c.put(px - k, y, ch, BRIGHT if k == 0 else mix(PURPLE, BRIGHT, 0.6 - k * 0.15), True)

        def flash(name, secs=0.8):
            f0 = s.flash.get(name)
            if f0 is None:
                return 0.0
            return max(0.0, 1 - (f - f0) / (self.fps * secs))

        # main session
        M = F["main"]
        mf = max(flash("main"), 1.0 if trig == 0 else 0.0)
        c.box(43, 3, 70, 8, mix(ORANGE, BRIGHT, mf * 0.5))
        c.center(CX, 4, str(M["title"]), mix(ORANGE, BRIGHT, mf * 0.4), True)
        c.center(CX, 5, str(M["subtitle"]), WHITE, True)
        c.segs(48, 6, [(str(M["effort_label"]) + " ", GRAY), ("▮▮▮▮", ORANGE), (" " + str(M["effort"]), ORANGE, True)])
        c.center(CX, 7, str(M["note"]), GRAY)
        for y in (9, 10):
            c.put(CX, y, "┆", DIM)

        # router
        R = F["router"]
        jf = flash("router")
        c.box(36, 11, 78, 17, mix(GREEN, BRIGHT, jf * 0.5))
        c.segs(38, 12, [(str(R["title"]), GREEN, True)])
        c.put(COUNTER_LABEL_X, 12, str(R["counter_label"]), GRAY)
        fk = f"{s.forks:,}"
        c.put(COUNTER_END - len(fk), 12, fk, WHITE, True)
        any_split = False
        for i, v in enumerate(s.rows):
            y = 13 + i
            sharp = v >= 0.7
            any_split |= not sharp
            col = GREEN if sharp else ORANGE
            c.put(38, y, str(R["questions"][i]), WHITE, True)
            n = int(round(v * 10))
            c.put(52, y, "▆" * n, col)
            c.put(52 + n, y, "▆" * (10 - n), mix(BG, col, 0.28))
            c.put(63, y, f"{v:.2f}", col, True)
            c.put(68, y, str(R["sharp_word"] if sharp else R["split_word"]), col, True)
        c.segs(38, 16, [(str(R["sharp_footer"]), GREEN if not any_split else GRAY, not any_split)])
        c.segs(62, 16, [(str(R["split_footer"]), ORANGE if any_split else GRAY, any_split)])

        # hand-off to the workers
        D = F["delegate"]
        c.put(CX, 18, "┆", DIM)
        c.segs(42, 19, [(str(D["label"]), WHITE, True), ("   ", DIM), (str(D["effort"]), BLUE, True)])
        c.put(CX, 20, "│", DIM)
        sl = self.slots
        if len(sl) > 1:
            c.put(sl[0], 21, "┌" + "─" * (sl[-1] - sl[0] - 1) + "┐", DIM)
            c.put(CX, 21, "┴", DIM)
        else:
            c.put(CX, 21, "│", DIM)
        for x in sl:
            c.put(x, 22, "▼", mix(BG, BLUE, 0.6))

        # worker cards
        Wk, St = F["workers"], F["worker_states"]
        for i, wk in enumerate(Wk):
            x0 = sl[i] - 10
            st = s.status[i]
            border = {"idle": mix(BG, BLUE, 0.4), "run": mix(BLUE, BRIGHT, 0.15 + 0.15 * math.sin(f * 0.3 + i)),
                      "wait": PURPLE, "done": GREEN, "pass": GREEN}[st]
            c.box(x0, 23, x0 + 19, 29, border)
            cx = x0 + 10
            lit = st != "idle"
            c.center(cx, 24, str(wk["name"]), WHITE if lit else GRAY, True)
            c.center(cx, 25, str(wk["model"]), BLUE if lit else mix(BG, BLUE, 0.6))
            c.segs(x0 + 3, 26, [(str(D["effort_label"]) + " ", GRAY), ("▮▮", BLUE), ("▯▯", DIM),
                                (" " + str(D["effort_short"]), BLUE)])
            c.center(cx, 27, str(wk["task"]), WHITE if lit else GRAY, lit)
            if st == "run":
                c.center(cx, 28, f"{SPIN[(f // 5 + i) % 4]} {St['running']}", BLUE)
            elif st == "wait":
                c.center(cx, 28, f"◌ {St['waiting']}", PURPLE, True)
            elif st == "pass":
                c.center(cx, 28, f"✓ {St['passed']}", GREEN, True)
            elif st == "done":
                c.center(cx, 28, f"✓ {St['done']}", GREEN, True)
            else:
                c.center(cx, 28, f"○ {St['idle']}", DIM)

        # back to the main session
        Rt = F["review"]
        for x in sl:
            c.put(x, 30, "│", DIM)
        if len(sl) > 1:
            c.put(sl[0], 31, "└" + "─" * (sl[-1] - sl[0] - 1) + "┘", DIM)
            c.put(CX, 31, "┬", DIM)
        else:
            c.put(CX, 31, "│", DIM)
        c.put(CX, 32, "▼", mix(BG, ORANGE, 0.6))
        lit_review = any(float(e["t"]) <= ct < float(e["until"]) for e in self.reviews)
        rf = max(flash("return", 1.0), 1.0 if (trig == 2 or lit_review) else 0.0)
        c.box(40, 33, 73, 36, mix(ORANGE, BRIGHT, rf * 0.45))
        c.segs(46, 34, [(str(Rt["title"]), ORANGE, True), ("   ", DIM), (str(Rt["effort"]), ORANGE, True)])
        c.center(CX, 35, str(Rt["subtitle"]), WHITE, True)

        # packets: the line they pass lights up for a moment
        for pts, f0, frames, col, _ in s.packets:
            prog = min(1.0, (f - f0) / frames)
            head = int(prog * (len(pts) - 1))
            for k in range(head + 1):
                x, y = pts[k]
                cell = c.cells[y][x]
                if cell[0] not in "┌┐└┘│":
                    cell[1] = mix(DIM, col, 0.35 + 0.65 * (1 - (head - k) / max(1, head + 1)))
            for k, ch in enumerate(["●", "•", "∙"]):
                j = head - k
                if j >= 0:
                    x, y = pts[j]
                    if c.cells[y][x][0] not in "┌┐└┘│":
                        c.put(x, y, ch, BRIGHT if k == 0 else mix(col, BRIGHT, 0.4 - k * 0.1), True)

        # session log
        lt = str(F["log_title"])
        c.put(2, 38, "┌─┤ ", DIM)
        c.put(6, 38, lt, GRAY)
        x = 6 + tw(lt)
        c.put(x, 38, " ├" + "─" * (W - 3 - x - 2) + "┐", DIM)
        for y in range(39, 43):
            c.put(2, y, "│", DIM)
            c.put(W - 3, y, "│", DIM)
        c.put(2, 43, "└" + "─" * (W - 6) + "┘", DIM)
        for i, (tm, who, text_, p, rl) in enumerate(s.log):
            y = 39 + i
            c.put(4, y, tm, DIM)
            c.put(13, y, str(who), self.who_color.get(str(who), WHITE), True)
            c.put(25, y, str(text_), WHITE)
            if p is not None:
                c.put(56, y, f"p={p:.2f}", GRAY)
                c.put(65, y, str(rl), GRAY)

        # command line and status bar
        Q, S = F["prompt"], F["status"]
        cur = "█" if (f // 15) % 2 == 0 else " "
        c.segs(2, 44, [(str(Q["path"]) + " ", WHITE, True), (str(Q["command"]) + " ", WHITE, True), (cur, GREEN)])
        c.segs(2, 45, [(str(S["effort_key"]) + " ", GRAY), ("[", DIM), (str(S["effort_value"]), WHITE, True), ("]", DIM),
                       ("  " + str(S["workers_key"]) + " ", GRAY), ("[", DIM), (str(S["workers_value"]), WHITE, True),
                       ("]", DIM), ("  " + str(S["advisor_key"]) + " ", GRAY), ("[", DIM),
                       (str(S["advisor_active"] if a else S["advisor_idle"]), PURPLE, True), ("]", DIM),
                       ("  " + str(S["router_key"]) + " ", GRAY), ("[ ", DIM),
                       (f"{s.forks:,} {S['counter_unit']}", GREEN, True), (" ]", DIM)])

    # ---------------------------------------------------------- checks
    def check(self):
        F = self.F
        out = []
        names = [str(p["name"]) for p in F["participants"]]
        out += check_events(self.events, EVENT_KEYS,
                            {"who": names, "route": list(ROUTES), "card": list(range(self.n)), "moment": [0, 1, 2],
                             "row": [0, 1, 2], "result": ["passed", "done"], "hold_card": list(range(self.n))},
                            self.total)
        for i, e in enumerate(self.events):
            if not isinstance(e, dict):
                continue
            if e.get("type") in ("advise", "review") and isinstance(e.get("until"), (int, float)) \
                    and e["until"] > self.total:
                out.append(after_end(f"events[{i}].until", e["until"], self.total, " to its end"))
            if e.get("type") in ("advise", "review"):
                if not number(e.get("until")):
                    out.append(problem("bad_time", f"events[{i}].until", "give the end time in seconds (a number)",
                                       actual=e.get("until")))
                elif number(e.get("t")) and e["until"] <= e["t"]:
                    out.append(problem("bad_time", f"events[{i}].until", "until must be later than t"))
            if e.get("type") == "advise":
                lines = e.get("lines")
                if not isinstance(lines, list) or not 1 <= len(lines) <= 2:
                    out.append(problem("wrong_type", f"events[{i}].lines", "give one or two lines of advice"))
                else:
                    for j, ln in enumerate(lines):
                        # drawn as "» line" from column 6, keeping one cell free before the column's border
                        lim = TXT_MAX - 8
                        if tw(str(ln)) > lim:
                            out.append(problem("too_long_on_screen", f"events[{i}].lines[{j}]",
                                               f"an advice line holds {lim} cells", actual=tw(str(ln)),
                                               limit=lim, over=tw(str(ln)) - lim, text=str(ln)))
            if e.get("type") in ("log", "decision", "advise"):
                for key in ("text", "log", "log_end"):
                    if key in e and 25 + tw(str(e[key])) > (56 if e.get("type") == "decision" else W - 5):
                        lim = (56 if e.get("type") == "decision" else W - 5) - 25
                        out.append(problem("too_long_on_screen", f"events[{i}].{key}",
                                           f"a log line holds {lim} cells here", actual=tw(str(e[key])), limit=lim,
                                           over=tw(str(e[key])) - lim, text=str(e[key])))
            for key in ("forks", "tokens"):
                if key in e and (not isinstance(e[key], int) or isinstance(e[key], bool) or e[key] < 0):
                    out.append(problem("wrong_type", f"events[{i}].{key}", "write a whole number from 0 up", actual=e[key]))
            if e.get("type") == "decision" and isinstance(e.get("p"), (int, float)) and not 0 <= e["p"] <= 1:
                out.append(problem("out_of_range", f"events[{i}].p", "p is a probability from 0 to 1", actual=e["p"]))
        title = "   ".join(" ".join(w) for w in str(F["title"]).split())
        if tw(title) > W - 4:
            out.append(problem("too_long_on_screen", "fields.title",
                               f"the spaced-out title is {tw(title)} cells; it holds {W - 4} (2 cells of margin on each side)",
                               actual=tw(title), limit=W - 4, over=tw(title) - (W - 4)))
        L = F["legend"]
        n = sum(1 + 1 + tw(str(L[k])) for k in ("main", "workers", "router", "advisor")) + 12
        if n > W - 4:
            out.append(problem("too_long_on_screen", "fields.legend",
                               f"the legend line is {n} cells; it holds {W - 4} (2 cells of margin on each side)",
                               actual=n, limit=W - 4, over=n - (W - 4)))
        S = F["status"]
        R = F["router"]
        top = self.counter_max() if not out else int(R["counter_start"]) + 2000
        digits = len(f"{top:,}")
        gap = (COUNTER_END - digits) - (COUNTER_LABEL_X + tw(str(R["counter_label"])))
        if gap < 1:
            out.append(problem("too_long_on_screen", "fields.router.counter_label",
                               f"the counter reaches {top:,} ({digits} cells) and ends at column {COUNTER_END}; "
                               f"with one space before it, the label holds {COUNTER_END - digits - 1 - COUNTER_LABEL_X} "
                               "cells (shorten the label or start the counter lower)",
                               actual=tw(str(R["counter_label"])), limit=COUNTER_END - digits - 1 - COUNTER_LABEL_X,
                               over=1 - gap, text=str(R["counter_label"])))
        n = (2 + tw(str(S["effort_key"])) + 2 + tw(str(S["effort_value"])) + 1
             + 2 + tw(str(S["workers_key"])) + 2 + tw(str(S["workers_value"])) + 1
             + 2 + tw(str(S["advisor_key"])) + 2 + max(tw(str(S["advisor_active"])), tw(str(S["advisor_idle"]))) + 1
             + 2 + tw(str(S["router_key"])) + 3 + digits + 1 + tw(str(S["counter_unit"])) + 2)
        if n > W - 2:
            out.append(problem("too_long_on_screen", "fields.status",
                               f"the status line needs {n} cells; it holds {W - 2} (2 cells of margin on the right)",
                               actual=n, limit=W - 2, over=n - (W - 2)))
        return out
