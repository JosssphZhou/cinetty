"""Round-driven scenes: layout, timeline, wires and packets, and ``render_frame``.

A scene is plain data (already resolved from a template and a content file).
``Scene(spec).render_frame(t)`` returns a ``Canvas`` for time ``t`` seconds.
"""
from __future__ import annotations

import colorsys
import math
import random

from . import expr
from .canvas import (BASE_COLORS, BG, Canvas, clamp01, cw, ease_out, mix, smooth, stable_hash, tw)

GLYPH = {1: "┆", 4: "┆", 5: "┆", 2: "┄", 8: "┄", 10: "┄", 6: "╭", 12: "╮", 3: "╰", 9: "╯", 7: "├", 13: "┤",
         14: "┬", 11: "┴", 15: "┼"}
TRAIL = (("●", 1.0), ("•", 0.85), ("•", 0.68), ("∙", 0.52), ("∙", 0.4), ("·", 0.3), ("·", 0.22), ("·", 0.15))


# ------------------------------------------------------------------ timeline
class Timeline:
    """Intro, N rounds of phases, all-lit hold, freeze, outro back to the opening frame."""

    def __init__(self, spec, n_rounds):
        self.intro = float(spec.get("intro", 1.6))
        self.phases = [(p["name"], p.get("kind", "work"), float(p["dur"]), bool(p.get("skip_last", False)))
                       for p in spec["phases"]]
        # duration_scale per round: {kind: factor}; 0.7 means the phase takes 70% of its listed duration.
        speeds = spec.get("duration_scale") or [{}] * n_rounds
        self.PH = []
        t = self.intro
        for ri in range(n_rounds):
            sp = speeds[ri] if ri < len(speeds) else speeds[-1]
            d = {}
            for name, kind, dur, skip_last in self.phases:
                if skip_last and ri == n_rounds - 1:
                    continue
                dd = dur * float(sp.get(kind, 1.0))
                d[name] = (t, t + dd)
                t += dd
            self.PH.append(d)
        self.speeds = speeds
        self.HOT_S = t
        self.HOLD_S = self.HOT_S + float(spec.get("hold", 1.6))
        self.FADE_S = self.HOLD_S + float(spec.get("freeze", 2.4))
        self.TOTAL = self.FADE_S + float(spec.get("outro", 1.5))
        snap = spec.get("snapshot") or {"round": min(2, n_rounds), "phase": self.phases[0][0], "at": 0.5}
        s, e = self.PH[int(snap["round"]) - 1][snap["phase"]]
        self.TS = s + float(snap.get("at", 0.5)) * (e - s)

    def round_at(self, t):
        for ri, d in enumerate(self.PH):
            if min(v[0] for v in d.values()) - 1e-6 <= t < max(v[1] for v in d.values()) + 1e-6:
                return ri
        return 0 if t < self.intro else len(self.PH) - 1

    def span(self, ri, name):
        return self.PH[ri].get(name)

    def in_phase(self, ri, name, t):
        sp = self.PH[ri].get(name)
        return sp is not None and sp[0] <= t < sp[1]

    def pg(self, ri, name, t):
        sp = self.PH[ri].get(name)
        if sp is None:
            return 1.0
        s, e = sp
        return clamp01((t - s) / max(1e-6, e - s))

    def alpha_content(self, t):
        if t < self.intro:
            return 0.0
        if t >= self.FADE_S:
            return 1.0 - smooth((t - self.FADE_S) / 0.7)
        return 1.0

    def alpha_snap(self, t):
        if t < self.intro - 0.3:
            return 1.0
        if t < self.intro:
            return 1.0 - smooth((t - (self.intro - 0.3)) / 0.3)
        if t >= self.FADE_S + 0.7:
            return smooth((t - (self.FADE_S + 0.7)) / 0.8)
        return 0.0

    def allon(self, t):
        if t < self.HOT_S:
            return 0.0
        if t < self.FADE_S:
            return smooth((t - self.HOT_S) / 0.35)
        return 1.0 - smooth((t - self.FADE_S) / 1.1)

    def named(self, key):
        """Absolute time of a named moment: intro, hot, hold, fade, total."""
        return {"intro": self.intro, "hot": self.HOT_S, "hold": self.HOLD_S, "fade": self.FADE_S,
                "total": self.TOTAL, "start": 0.0}[key]


# ------------------------------------------------------------------ ticker
class Ticker:
    """A fast inner loop of steps (one live decision every ``period`` seconds).

    ``confidences`` holds, per round, the confidence of every live step in order, from the
    project: step ``k`` of a round shows confidence ``k`` of that round, cycling through
    the list, and goes ahead when it reaches ``threshold``. Every number the loop shows
    comes from the project; the engine derives none. With ``wrap_end`` the outro replays
    round 1 timed against the opening, so the last frame flows into the first.
    """

    def __init__(self, spec, timeline):
        self.tl = timeline
        self.period = [float(x) for x in spec["period"]]
        self.steps = [[float(x) for x in r] for r in spec["confidences"]]
        self.threshold = float(spec["threshold"])
        self.actions = spec.get("actions", ["tap", "type", "scroll"])
        self.wrap_end = bool(spec.get("wrap_end", True))
        self.pulses = spec.get("pulses", [])

    def time(self, t):
        if self.wrap_end and t >= self.tl.FADE_S:
            return 0, t - self.tl.TOTAL
        return (self.tl.round_at(t) if t >= self.tl.intro else 0), t

    def conf_at(self, ri, k):
        """Confidence of step ``k`` in round ``ri``."""
        seq = self.steps[ri]
        return seq[k % len(seq)]

    def step(self, t):
        ri, tt = self.time(t)
        P = self.period[ri]
        k = int(math.floor(tt / P))
        u = (tt - k * P) / P
        conf = self.conf_at(ri, k)
        btn = k % len(self.actions)
        return dict(k=k, u=u, P=P, conf=conf, gate=self.threshold, btn=btn, act=self.actions[btn], go=conf >= self.threshold, ri=ri)

    def step_pulses(self, t):
        out = []
        st = self.step(t)
        ri, tf = self.time(t)
        shift = t - tf
        for dk in (-1, 0, 1):
            k = st["k"] + dk
            if k < 0 and not self.wrap_end:
                continue
            P = self.period[ri]
            t0 = k * P + shift
            go = self.conf_at(ri, k) >= self.threshold
            for p in self.pulses:
                when = p.get("when", "always")
                if when == "go" and not go or when == "fallback" and go:
                    continue
                out.append((p["wire"], t0 + float(p.get("from", 0)) * P, t0 + float(p.get("to", 1)) * P))
        return out


# ------------------------------------------------------------------ layout
class Box:
    def __init__(self, spec, scene):
        self.key = spec["id"]
        self.x0, self.y0, self.x1, self.y1 = spec["rect"]
        self.color = scene.color(spec.get("color", "gray"))
        self.title = spec.get("title", "")
        self.style = spec.get("style", "normal")          # normal | frame | core
        self.layer = spec.get("layer", "round")           # round | live
        self.spec = spec
        from .components import build
        self.content = [build(c, scene) for c in spec.get("content", [])]

    rect = property(lambda s: (s.x0, s.y0, s.x1, s.y1))
    w = property(lambda s: s.x1 - s.x0 + 1)
    h = property(lambda s: s.y1 - s.y0 + 1)


def expand(pts):
    out = [tuple(pts[0])]
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if ya == yb:
            s = 1 if xb > xa else -1
            out += [(x, ya) for x in range(xa + s, xb + s, s)]
        elif xa == xb:
            s = 1 if yb > ya else -1
            out += [(xa, y) for y in range(ya + s, yb + s, s)]
    return out


def ring_cells(rect):
    x0, y0, x1, y1 = rect
    return ([(x, y0) for x in range(x0, x1 + 1)] + [(x1, y) for y in range(y0 + 1, y1 + 1)]
            + [(x, y1) for x in range(x1 - 1, x0 - 1, -1)] + [(x0, y) for y in range(y1 - 1, y0, -1)])


# ------------------------------------------------------------------ scene
class Scene:
    def __init__(self, spec):
        self.spec = spec
        self.cols, self.rows = spec["canvas"]["cols"], spec["canvas"]["rows"]
        self.fps = int(spec["canvas"].get("fps", 60))
        self.palette = dict(BASE_COLORS)
        for k, v in (spec.get("palette") or {}).items():
            self.palette[k] = tuple(v)
        self.style = spec.get("style") or {}
        self.rounds = [dict(r) for r in spec.get("rounds") or [{}]]
        self.data = spec.get("data") or {}
        # Per-round values the components read under fixed names, computed from the project's fields.
        for key, code in (spec.get("derive") or {}).items():
            for ri, r in enumerate(self.rounds):
                r[key] = self.static(code, ri)
        self.tl = Timeline(spec["timeline"], len(self.rounds))
        if spec.get("ticker"):
            tk = {k: self.static(v) for k, v in spec["ticker"].items()}
            self.ticker = Ticker(tk, self.tl)
        else:
            self.ticker = None
        self.boxes = [Box(b, self) for b in spec["boxes"]]
        self.B = {b.key: b for b in self.boxes}
        self._build_wires(spec.get("wires") or [])
        from .components import build
        self.overlays = [build(o, self) for o in spec.get("overlay") or []]
        self.title = spec.get("title") or {}
        self._title_setup()
        self.counters = spec.get("counters") or {}
        self.version_spec = spec.get("version")
        self.photos = None
        if spec.get("photo_layer"):
            from .photolayer import PhotoLayer
            self.photos = PhotoLayer(spec["photo_layer"], self)
        self.static_pulses = self._build_pulses(spec.get("wires") or [])
        self.ripple_wires = set((self.style.get("core_pulse") or {}).get("wires", []))
        self.ripples = [s for (w, s, e) in self.static_pulses if w in self.ripple_wires]
        self.extra = {}                      # per-scene state for components

    # ---------------------------------------------------------- helpers
    def static(self, v, ri=0):
        """Evaluate a binding that does not depend on time (rounds and data only)."""
        if not (isinstance(v, str) and expr.has_binding(v)):
            return v
        r = dict(self.rounds[ri])
        r["n"] = ri + 1
        return expr.value(v, {"round": expr.Obj(r), "ri": ri, "rounds": len(self.rounds),
                              "all_rounds": expr.wrap(self.rounds), "data": expr.wrap(self.data)})

    def color(self, c):
        if c is None:
            return None
        if isinstance(c, str):
            return self.palette[c]
        if isinstance(c, (list, tuple)) and c and c[0] == "mix":
            return mix(self.color(c[1]), self.color(c[2]), float(c[3]))
        return tuple(c)

    def swap(self, s):
        """Numbers are shown as the project gives them; nothing on screen is rewritten."""
        return s

    def ctx(self, t, ri=None):
        """Names available to bindings at time ``t``."""
        if ri is None:
            ri = self.tl.round_at(t)
        r = dict(self.rounds[ri])
        r["n"] = ri + 1
        d = {"round": expr.Obj(r), "rounds": len(self.rounds), "ri": ri, "t": t,
             "all_rounds": expr.wrap(self.rounds), "data": expr.wrap(self.data),
             "speed": expr.Obj(self.tl.speeds[ri] if ri < len(self.tl.speeds) else {})}
        if self.ticker:
            d["tick"] = expr.Obj(self.ticker.step(t))
        d["counter"] = expr.Obj({k: self.counter(k, t) for k in self.counters})
        if self.version_spec:
            d["version"] = self.version(t)
        if self.photos:
            tg = self.photos.target(t)
            d["photo"] = expr.Obj({"ready": tg is not None, "name": tg["name"] if tg else "",
                                   "bbox": "[%d,%d,%d,%d]" % tuple(tg["box"]) if tg else "",
                                   "confident": self.photos.confident(t)})
        return d

    def text(self, s, t, ri=None):
        if expr.has_binding(s):
            return expr.render(s, self.ctx(t, ri))
        return s

    def value(self, s, t, ri=None):
        if isinstance(s, str) and expr.has_binding(s):
            return expr.value(s, self.ctx(t, ri))
        return s

    def counter(self, name, t):
        """A number that rolls from a to b during a phase (per-round pair ``[a, b]``)."""
        sp = self.counters[name]
        tl = self.tl
        if t >= tl.HOT_S:
            return self.rounds[-1][sp["key"]][1]
        ri = tl.round_at(t)
        a, b = self.rounds[ri][sp["key"]]
        s, e = tl.PH[ri][sp["phase"]]
        if t < s:
            return a
        p = clamp01((t - s) / max(1e-6, (e - s) * float(sp.get("span", 0.9))))
        return int(round(a + (b - a) * p))

    def counter_pair(self, name, t):
        sp = self.counters[name]
        ri = self.tl.round_at(t)
        a, _ = self.rounds[ri][sp["key"]]
        return a, self.counter(name, t)

    def version(self, t):
        """Adopted version number: switches during the given phase when the round has a winner."""
        sp = self.version_spec
        tl = self.tl
        ri = tl.round_at(t)
        a, b = self.rounds[ri][sp.get("key", "v")]
        if t >= tl.HOT_S:
            return self.rounds[-1][sp.get("key", "v")][1]
        s, e = tl.PH[ri][sp["phase"]]
        return b if t >= s + float(sp.get("at", 0.4)) * (e - s) else a

    # ---------------------------------------------------------- wires
    def _build_wires(self, wires):
        self.W = {}
        for w in wires:
            cells = expand(w["path"])
            arrow = w.get("arrow")
            self.W[w["id"]] = dict(cells=cells, color=self.color(w["color"]), arrow=tuple(arrow) if arrow else None,
                                   target=w.get("to"), decay=float(w.get("decay", 4.0)), spec=w)
        self.WCELLS = set()
        for w in self.W.values():
            self.WCELLS |= set(w["cells"])
        self.BORDER = set()
        self.INTERIOR = {}
        for b in self.boxes:
            for x in range(b.x0, b.x1 + 1):
                self.BORDER |= {(x, b.y0), (x, b.y1)}
            for y in range(b.y0, b.y1 + 1):
                self.BORDER |= {(b.x0, y), (b.x1, y)}
            if b.style in ("frame", "core") or b.layer != "round":
                continue
            self.INTERIOR[b.key] = [(x, y) for y in range(b.y0 + 1, b.y1) for x in range(b.x0 + 1, b.x1)]
        self.MASKS, self.OWNERS = {}, {}
        for name, w in self.W.items():
            full = w["cells"]
            for (xa, ya), (xb, yb) in zip(full, full[1:]):
                d0, d1 = ((2, 8) if xb > xa else (8, 2)) if xb != xa else ((4, 1) if yb > ya else (1, 4))
                for p, d in (((xa, ya), d0), ((xb, yb), d1)):
                    self.MASKS[p] = self.MASKS.get(p, 0) | d
                    self.OWNERS.setdefault(p, [])
                    if name not in self.OWNERS[p]:
                        self.OWNERS[p].append(name)
        self.ARROWS = {(w["arrow"][0], w["arrow"][1]): (w["arrow"][2], n) for n, w in self.W.items() if w["arrow"]}
        self.RINGS = {b.key: ring_cells(b.rect) for b in self.boxes}
        # Wire labels sit on a wire; packets do not draw over them.
        self.labels = []
        self.LABEL = set()
        for name, w in self.W.items():
            lab = w["spec"].get("label")
            if lab:
                if expr.has_binding(lab["text"]):
                    lab = dict(lab, text=expr.render(lab["text"], {}))
                self.labels.append((name, lab))
                txt = lab["text"]
                x0 = lab["x"] - tw(txt) // 2 if lab.get("anchor") == "center" else lab["x"]
                if lab.get("blocks_packets", True):
                    self.LABEL |= {(x, lab["y"]) for x in range(x0, x0 + tw(txt))}

    def _build_pulses(self, wires):
        tl = self.tl
        phase_idx = {p[0]: i for i, p in enumerate(tl.phases)}
        timed, absolute, periodic = [], [], []
        for order, w in enumerate(wires):
            for sp in w.get("pulses") or []:
                if "phase" in sp:
                    for ri, d in enumerate(tl.PH):
                        if sp["phase"] not in d:
                            continue
                        cond = sp.get("if")
                        if cond and not expr.value("{" + cond + "}", self.ctx(d[sp["phase"]][0], ri)):
                            continue
                        s, e = d[sp["phase"]]
                        fs = float(sp.get("from_step", sp.get("step", 0)))
                        ts = float(sp.get("to_step", sp.get("step", 0)))
                        for k in range(int(sp.get("repeat", 1))):
                            ps = s + (e - s) * (float(sp.get("from", 0)) + k * fs) + float(sp.get("plus_from", 0))
                            pe = s + (e - s) * (float(sp.get("to", 1)) + k * ts) + float(sp.get("plus_to", 0))
                            timed.append(((ri, phase_idx[sp["phase"]], order), (w["id"], ps, pe)))
                elif "every" in sp:
                    t0 = tl.named(sp.get("start", "intro"))
                    t1 = tl.named(sp.get("until", "hot"))
                    k = 0
                    while t0 + float(sp["every"]) * k < t1:
                        s0 = t0 + float(sp["every"]) * k
                        periodic.append((w["id"], s0, s0 + float(sp["dur"])))
                        k += 1
                else:
                    s0 = float(sp["at"])
                    absolute.append((w["id"], s0, s0 + float(sp["dur"])))
        timed.sort(key=lambda x: x[0])
        out = [p for _, p in timed]
        if self.style.get("periodic_first"):
            out = periodic + out
            periodic = []
        out += absolute + periodic
        fin = self.style.get("finale_pulses", {"count": 4, "every": 0.38, "dur": 0.55})
        if fin:
            for name in self.W:
                for k in range(int(fin["count"])):
                    s0 = tl.HOT_S + float(fin["every"]) * k + (stable_hash(name) % 7) * 0.03
                    out.append((name, s0, s0 + float(fin["dur"])))
        return out

    def pulses(self, t):
        return self.static_pulses + (self.ticker.step_pulses(t) if self.ticker and self.ticker.pulses else [])

    def wire_energy(self, name, t, pulses):
        v = 0.0
        decay = self.W[name]["decay"]
        for (w, s, e) in pulses:
            if w == name and t >= s:
                v = max(v, 1.0 if t <= e else (0.5 * (1 - min(1.0, (t - e) / decay)) + 0.15))
        return max(v, self.tl.allon(t))

    def flash_of(self, key, t, pulses):
        win = float(self.style.get("flash", 0.25))
        f = 0.0
        for (w, s, e) in pulses:
            if self.W[w]["target"] == key and 0 <= t - e < win:
                f = max(f, 1 - (t - e) / win)
        return f

    # ---------------------------------------------------------- levels
    def levels(self, t):
        tl = self.tl
        ri = tl.round_at(t)
        sa = tl.alpha_snap(t)
        a = tl.allon(t)
        st = self.ticker.step(t) if self.ticker else None
        act = {}
        for b in self.boxes:
            lit = b.spec.get("lit") or []
            v = 0.0
            for item in lit:
                ph, lv = (item, 1.0) if isinstance(item, str) else (item["phase"], float(item.get("level", 1.0)))
                if tl.in_phase(ri, ph, t):
                    v = max(v, lv)
            for t0, t1 in b.spec.get("lit_windows") or []:
                if t0 <= t < t1:
                    v = 1.0
            tk = b.spec.get("lit_tick")
            if tk and st is not None:
                want = tk.get("when", "go") == "go"
                lo, hi = tk.get("window", [0.4, 0.95])
                v = max(v, 1.0 if (st["go"] == want and lo < st["u"] < hi) else float(tk.get("else", 0.0)))
            if "snapshot" in b.spec:
                v = max(v, float(b.spec["snapshot"]) * sa)
            v = max(v, a, float(b.spec.get("idle", 0.0)))
            if "level" in b.spec:
                v = float(b.spec["level"])
            act[b.key] = v
        return act

    # ---------------------------------------------------------- title
    def _title_setup(self):
        T = self.title
        if not T:
            return
        words = T["text"].split(" ")
        self._title = "     ".join("  ".join(w) for w in words)
        rng = random.Random(int(T.get("seed", 20261019)))
        spread = int(T.get("scatter", 30))
        if T.get("scatter_dy", False):
            self._scatter = [(rng.randint(-spread, spread), 0, rng.random() * 0.5) for _ in self._title]
        else:
            self._scatter = [(rng.randint(-spread, spread), 0, rng.random() * 0.5) for _ in self._title]

    def hue_speed(self):
        T = self.title
        if T.get("hue_loop"):
            return round(self.tl.TOTAL * 0.45) / self.tl.TOTAL
        return float(T.get("hue_speed", 0.45))

    def draw_title(self, c, t):
        T = self.title
        if not T:
            return
        tl = self.tl
        bright = self.palette["bright"]
        title = self._title
        # Letters sit at cell positions, so a wide (CJK) letter takes two cells of its gap.
        cells, n = [], 0
        for ch in title:
            cells.append(n)
            n += cw(ch)
        x0 = (self.cols - n) // 2
        c.fit(title, self.cols - 2, "title")
        row = int(T.get("row", 1))
        conv = 1.0 - smooth((t - tl.FADE_S) / 1.2) if t >= tl.FADE_S else None
        sweep = (t - 1.2) / 0.5
        sweep2 = (t - (tl.HOLD_S - 0.2)) / 0.6
        hv = self.hue_speed()
        for k, ch in enumerate(title):
            if ch == " ":
                continue
            dx, _, delay = self._scatter[k]
            p = conv if conv is not None else smooth((t - delay * 0.8) / 1.0)
            x = int(round(x0 + cells[k] + dx * (1 - p)))
            hue = (k / len(title) * 0.85 - t * hv) % 1.0
            r, g, bl = colorsys.hsv_to_rgb(hue, 0.72, 1.0)
            col = (int(r * 255), int(g * 255), int(bl * 255))
            hit = max(0.0, 1 - abs(k / len(title) - sweep) * 9) + max(0.0, 1 - abs(k / len(title) - sweep2) * 9)
            col = mix(col, bright, min(1.0, 0.8 * hit))
            col = mix(BG, col, 0.65 + 0.35 * p)
            if 0 <= x < self.cols:
                c.put(x, row, ch, col, True)
        sub = T.get("subtitle")
        if sub:
            text = sub["text"]
            c.fit(text, self.cols - 2, "title.subtitle")
            fade = 0.75 * smooth(t / 1.0) * (1.0 if t < tl.FADE_S else 1.0 - smooth((t - tl.FADE_S) / 1.2))
            c.put((self.cols - tw(text)) // 2, int(sub.get("row", row + 1)), text, mix(BG, self.palette["gray"], fade))

    # ---------------------------------------------------------- boxes and wires
    def box_title(self, b):
        return b.title

    def draw_box(self, c, b, t, lvl, fl):
        col = b.color
        bright = self.palette["bright"]
        base = mix(BG, col, 0.45 + 0.47 * lvl)
        if fl > 0:
            base = mix(base, bright, 0.85 * fl)
        x0, y0, x1, y1 = b.rect
        cells = c.cells
        soft = self.palette["soft"]
        for x in range(x0 + 1, x1):
            cells[y0][x] = ["─", base, False]
            cells[y1][x] = ["─", base, False]
        for y in range(y0 + 1, y1):
            cells[y][x0] = ["│", base, False]
            cells[y][x1] = ["│", base, False]
            if b.style != "frame":
                for x in range(x0 + 1, x1):
                    cells[y][x] = [" ", soft, False]
        cells[y0][x0], cells[y0][x1] = ["┌", base, False], ["┐", base, False]
        cells[y1][x0], cells[y1][x1] = ["└", base, False], ["┘", base, False]
        title = self.box_title(b)
        if title:
            c.fit(title, b.w - int(self.style.get("title_margin", 5)), f"{b.key}.title")
            c.put(x0 + 2, y0, f" {title} ", mix(col, bright, 0.15 + 0.5 * fl) if lvl > 0.5 else col, lvl > 0.5)
        speed = 39.0 + 57.0 * lvl
        length = int(12 + 6 * lvl)
        power = 0.75 + 0.25 * lvl
        ring = self.RINGS[b.key]
        off = (stable_hash(b.key) % 997) / 997.0 * len(ring)
        head = int(t * speed + off) % len(ring)
        glow = mix(col, bright, 0.15)
        for k in range(length):
            x, y = ring[(head - k) % len(ring)]
            ch = cells[y][x]
            if ch[0] not in (" ", ""):
                ch[1] = mix(base, glow, (1 - k / length) * power)
                ch[2] = k < 3 and lvl > 0.5

    def core_pulse(self, t):
        cp = self.style.get("core_pulse") or {}
        if cp.get("source") == "tick" and self.ticker:
            st = self.ticker.step(t)
            return math.exp(-(st["u"] * st["P"]) / float(cp.get("decay", 0.12)))
        return max([math.exp(-(t - r) / float(cp.get("decay", 0.22))) for r in self.ripples if 0 <= t - r < 1.2] or [0.0])

    def draw_core(self, c, b, t):
        cs = b.spec.get("core") or {}
        bright = self.palette["bright"]
        col = b.color
        p = self.core_pulse(t)
        base = mix(mix(BG, col, 0.95), bright, float(cs.get("glow", 0.8)) * p)
        x0, y0, x1, y1 = b.rect
        cells = c.cells
        soft = self.palette["soft"]
        for x in range(x0 + 1, x1):
            cells[y0][x] = ["═", base, True]
            cells[y1][x] = ["═", base, True]
        for y in range(y0 + 1, y1):
            cells[y][x0] = ["║", base, True]
            cells[y][x1] = ["║", base, True]
            for x in range(x0 + 1, x1):
                cells[y][x] = [" ", soft, False]
        cells[y0][x0], cells[y0][x1], cells[y1][x0], cells[y1][x1] = ["╔", base, True], ["╗", base, True], ["╚", base, True], ["╝", base, True]
        title = " " + b.title + " "
        c.fit(title, b.w - 4, f"{b.key}.title")
        c.put(x0 + 2, y0, title, mix(bright, col, 0.2 * (1 - p)), True)
        rx0, ry0, rx1, ry1 = x0 - 1, y0 - 1, x1 + 1, y1 + 1
        ring = ([(x, ry0, "⠉") for x in range(rx0 + 1, rx1)] + [(rx1, y, "⢸") for y in range(ry0 + 1, ry1)]
                + [(x, ry1, "⣀") for x in range(rx1 - 1, rx0, -1)] + [(rx0, y, "⡇") for y in range(ry1 - 1, ry0, -1)])
        L = len(ring)
        for (x, y, g) in ring:
            if (x, y) in self.WCELLS:
                continue
            cells[y][x] = [g, mix(mix(BG, col, 0.3), mix(col, bright, 0.5), p), False]
        trail = int(cs.get("trail", 22))
        for ph in (0.0, 0.5):
            head = int(t * 34 + ph * L) % L
            for k in range(trail):
                x, y, g = ring[(head - k) % L]
                if (x, y) in self.WCELLS:
                    continue
                cells[y][x] = [g, mix(mix(BG, col, 0.3), mix(col, bright, 0.55), (1 - k / trail) ** 1.3), k < 4]

    def draw_wires(self, c, t, pulses):
        cells = c.cells
        line = self.palette["line"]
        gray = self.palette["gray"]
        bright = self.palette["bright"]
        energy = {n: self.wire_energy(n, t, pulses) for n in self.W}
        for p, m in self.MASKS.items():
            if p in self.BORDER or p in self.ARROWS:
                continue
            x, y = p
            n = max(self.OWNERS[p], key=lambda o: energy[o])
            col = self.W[n]["color"]
            e = energy[n]
            cells[y][x] = [GLYPH.get(m, "┄"), mix(line, col, 0.2 + 0.8 * e) if e > 0 else line, False]
        for name, lab in self.labels:
            e = max(energy[w] for w in lab.get("energy_of", [name]))
            col = self.color(lab.get("color")) or self.W[name]["color"]
            txt = lab["text"]
            x0 = lab["x"] - tw(txt) // 2 if lab.get("anchor") == "center" else lab["x"]
            c.put(x0, lab["y"], txt, mix(mix(BG, col, 0.4), mix(col, bright, 0.4), e))
        for p, (ch, n) in self.ARROWS.items():
            x, y = p
            col = self.W[n]["color"]
            e = energy[n]
            base = mix(line, gray, 0.45)
            cells[y][x] = [ch, mix(base, mix(col, bright, 0.3), e) if e > 0 else base, e > 0.6]

    def draw_packets(self, c, t, pulses):
        bright = self.palette["bright"]
        for (w, s, e) in pulses:
            if s <= t <= e + 0.02:
                pts = self.W[w]["cells"]
                if len(pts) < 2:
                    pts = pts * 2
                p = ease_out(min(1.0, max(0.0, (t - s) / max(1e-6, e - s))))
                head = int(p * (len(pts) - 1))
                col = self.W[w]["color"]
                for j, (ch, inten) in enumerate(TRAIL):
                    idx = head - j
                    if idx >= 0:
                        x, y = pts[idx]
                        if (x, y) in self.BORDER or (x, y) in self.LABEL:
                            continue
                        c.cells[y][x] = [ch, mix(BG, bright if j == 0 else col, inten), True]

    # ---------------------------------------------------------- frame
    def draw_layer(self, c, tc, a):
        for b in self.boxes:
            if b.layer != "round":
                continue
            for comp in b.content:
                comp.draw(c, b, tc, self)
        if a < 1:
            for cells in self.INTERIOR.values():
                for (x, y) in cells:
                    ch = c.cells[y][x]
                    if ch[0] not in (" ", ""):
                        ch[1] = mix(BG, ch[1], a)

    def render_frame(self, t):
        c = Canvas(self.cols, self.rows, self.palette["soft"])
        tl = self.tl
        pulses = self.pulses(t)
        lv = self.levels(t)
        self.draw_wires(c, t, pulses)
        for b in self.boxes:
            if b.style != "core":
                self.draw_box(c, b, t, lv[b.key], self.flash_of(b.key, t, pulses))
        for b in self.boxes:
            if b.style == "core":
                self.draw_core(c, b, t)
        for b in self.boxes:
            if b.layer == "live":
                for comp in b.content:
                    comp.draw(c, b, t, self)
        for o in self.overlays:
            if getattr(o, "z", "over") == "under":
                o.draw(c, None, t, self)
        a, sa = tl.alpha_content(t), tl.alpha_snap(t)
        if a > 0:
            self.draw_layer(c, t, a)
        if sa > 0:
            self.draw_layer(c, tl.TS, sa)
        self.draw_packets(c, t, pulses)
        for o in self.overlays:
            if getattr(o, "z", "over") == "over":
                o.draw(c, None, t, self)
        self.draw_title(c, t)
        for o in self.overlays:
            if getattr(o, "z", "over") == "top":
                o.draw(c, None, t, self)
        return c.normalize()

    def size(self):
        return self.cols, self.rows

    def duration(self):
        return self.tl.TOTAL
