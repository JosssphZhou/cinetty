"""The event driver: boards whose motion comes from a list of timed events.

A board scene (``driver: events`` in scene.yaml) has fixed boxes and wires; the
project's ``events`` say when a packet runs along a wire, when a box lights up,
when a log line is typed and when a status value changes. ``render_frame(t)`` is
a pure function of the scene, the events and ``t``.

Events, one format for every board template::

  {t: 3.4, type: pulse, wire: a_d, dur: 1.0}               # seconds from the start
  {t: 3.0, type: light, box: A, until: 7.0}
  {t: 3.2, type: log, color: power, tag: Power, text: "SW1 closed"}
  {t: 6.2, type: status, key: 3v3, value: 3.3 V}

Events may also be read from a ``.jsonl`` file (``events: run.jsonl`` in the
project). Times must not go backwards; events at the same time apply in file order.
"""
from __future__ import annotations

import colorsys
import json
from pathlib import Path

from .canvas import BASE_COLORS, BG, Canvas, mix, tw
from .template import TemplateError, has_bad_char, problem

EVENT_KEYS = {
    "pulse": ({"wire"}, {"dur", "dir", "label"}),
    "light": ({"box"}, {"until"}),
    "log": ({"text"}, {"tag", "color"}),
    "status": ({"key", "value"}, set()),
    "highlight": ({"box", "text"}, {"color"}),
}


# ------------------------------------------------------------------ events
def read_events(value, base):
    """Events from a project: an inline list, or a path to a .jsonl file (relative to the project)."""
    if value is None:
        return []
    if isinstance(value, str):
        path = Path(base) / value
        if not path.is_file():
            raise TemplateError(f"events file not found: {value} (paths are relative to the project file)")
        out = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    raise TemplateError(f"{value}, line {n}: not valid JSON") from None
        return out
    if not isinstance(value, list):
        raise TemplateError("events must be a list or the path of a .jsonl file")
    return value


def bad_strings(value, path):
    """Paths of the texts inside an event (at any depth) that hold line breaks or control characters."""
    if isinstance(value, str):
        return [path] if has_bad_char(value) else []
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in bad_strings(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in bad_strings(v, f"{path}[{i}]")]
    return []


def after_end(path, t, total, why=""):
    return problem("after_end", path, f"the animation is {total:g} s long, so this never shows{why}; "
                   f"move it before {total:g} s", actual=round(float(t), 2), limit=total)


def check_events(events, kinds, names, total=None):
    """Problems in an event list. ``kinds`` maps type -> (required keys, optional keys);
    ``names`` maps a key (box, wire, key, color) to the names it may take; ``total`` is the
    animation's length in seconds (an event at or after it never shows)."""
    out = []
    last = 0.0
    for i, e in enumerate(events):
        path = f"events[{i}]"
        if not isinstance(e, dict):
            out.append(problem("wrong_type", path, "each event is a mapping such as {t: 1.5, type: log, text: ...}"))
            continue
        for bad in bad_strings({k: v for k, v in e.items() if k not in ("t", "type")}, path):
            out.append(problem("bad_char", bad, "remove line breaks, tabs and control characters; "
                                                "write the text on one line"))
        t = e.get("t")
        if not isinstance(t, (int, float)) or isinstance(t, bool) or t < 0:
            out.append(problem("bad_time", f"{path}.t", "give the time in seconds from the start (a number >= 0)",
                               actual=t))
        elif t < last:
            out.append(problem("time_goes_back", f"{path}.t",
                               f"events must be in time order; this one is at {t}s after one at {last}s",
                               actual=t, limit=last))
        else:
            last = float(t)
            if total is not None and t >= total:
                out.append(after_end(f"{path}.t", t, total))
        kind = e.get("type")
        if kind not in kinds:
            out.append(problem("unknown_event", f"{path}.type", "use one of: " + ", ".join(kinds), actual=kind))
            continue
        need, opt = kinds[kind]
        for k in sorted(need - set(e)):
            out.append(problem("missing", f"{path}.{k}", f"a {kind} event needs '{k}'"))
        for k in sorted(set(e) - need - opt - {"t", "type"}):
            out.append(problem("unknown_field", f"{path}.{k}",
                               f"a {kind} event takes: t, type, " + ", ".join(sorted(need | opt))))
        for k, allowed in names.items():
            if k in e and k in (need | opt) and e[k] not in allowed:
                out.append(problem("unknown_ref", f"{path}.{k}", f"use one of: {', '.join(map(str, allowed))}",
                                   actual=e[k]))
        for k in ("text", "tag", "value"):
            if k in e and k in (need | opt) and not isinstance(e[k], str):
                out.append(problem("wrong_type", f"{path}.{k}", "write this as text (quote it)", actual=e[k]))
    return out


# ------------------------------------------------------------------ geometry
def expand(pts):
    out = [tuple(pts[0])]
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if ya == yb:
            step = 1 if xb > xa else -1
            out += [(x, ya) for x in range(xa + step, xb + step, step)]
        else:
            step = 1 if yb > ya else -1
            out += [(xa, y) for y in range(ya + step, yb + step, step)]
    return out


TRAIL = (("●", 1.0), ("•", 0.8), ("•", 0.62), ("∙", 0.48), ("∙", 0.36), ("·", 0.26), ("·", 0.18), ("·", 0.12))
GLYPH = {1: "┆", 4: "┆", 5: "┆", 2: "┄", 8: "┄", 10: "┄", 6: "╭", 12: "╮", 3: "╰", 9: "╯", 7: "├", 13: "┤",
         14: "┬", 11: "┴", 15: "┼"}


class Board:
    """A circuit-style board: lettered boxes, wires with net labels, a typed log, prompt and status bar."""

    def __init__(self, spec):
        self.spec = spec
        cv = spec["canvas"]
        self.cols, self.rows, self.fps = int(cv["cols"]), int(cv["rows"]), int(cv.get("fps", 30))
        self.total = float(spec["duration"])
        self.photos = None
        self.palette = dict(BASE_COLORS)
        for k, v in (spec.get("palette") or {}).items():
            self.palette[k] = tuple(v)
        self.events = spec.get("_events") or []
        self.boxes = {b["id"]: b for b in spec["boxes"]}
        self.rect = {k: tuple(b["rect"]) for k, b in self.boxes.items()}
        self._wires(spec.get("wires") or [])
        self._timeline()

    # ---------------------------------------------------------- setup
    def color(self, name):
        return self.palette[name] if isinstance(name, str) else tuple(name)

    def _wires(self, wires):
        self.wires = {}
        for w in wires:
            labels = []
            for lb in w.get("labels") or []:
                text = str(lb["text"])
                if tw(text) == 0:
                    continue   # an empty label leaves the wire whole instead of a gap
                if "right_at" in lb:
                    x, y = lb["right_at"]
                    x -= tw(text)
                else:
                    x, y = lb["at"]
                labels.append((x, y, text, lb.get("tag")))
            cells = expand(w["pts"])[int(w.get("trim_start", 0)):]
            self.wires[w["id"]] = dict(pts=w["pts"], cells=cells, col=self.color(w["color"]), labels=labels,
                                       arrows=[tuple(a) for a in w.get("arrows") or []])
        masks, owners = {}, {}
        for name, w in self.wires.items():
            full = expand(w["pts"])
            for (xa, ya), (xb, yb) in zip(full, full[1:]):
                if xb > xa:
                    d0, d1 = 2, 8
                elif xb < xa:
                    d0, d1 = 8, 2
                elif yb > ya:
                    d0, d1 = 4, 1
                else:
                    d0, d1 = 1, 4
                masks[(xa, ya)] = masks.get((xa, ya), 0) | d0
                masks[(xb, yb)] = masks.get((xb, yb), 0) | d1
                for p in ((xa, ya), (xb, yb)):
                    owners.setdefault(p, [])
                    if name not in owners[p]:
                        owners[p].append(name)
        self.masks, self.owners = masks, owners
        self.border = set()
        for (x0, y0, x1, y1) in self.rect.values():
            for x in range(x0, x1 + 1):
                self.border |= {(x, y0), (x, y1)}
            for y in range(y0, y1 + 1):
                self.border |= {(x0, y), (x1, y)}
        self.label_cells = {}
        for name, w in self.wires.items():
            cells = set()
            for (lx, ly, text, _tag) in w["labels"]:
                cells |= {(lx - 1 + i, ly) for i in range(tw(text) + 2)}
            self.label_cells[name] = cells
        self.all_labels = set().union(*self.label_cells.values()) if self.label_cells else set()
        self.arrow_cells = {(a[0], a[1]) for w in self.wires.values() for a in w["arrows"]}

    def _timeline(self):
        """Sort the events by kind. Events the check rejects (a bad time, an unknown box or wire)
        are left out here, so building the board never fails before the check can report them."""
        self.pulses, self.logs, self.status_ev, self.highlights = [], [], [], []
        self.windows = {k: [] for k in self.boxes}
        for e in self.events:
            if not isinstance(e, dict) or not isinstance(e.get("t"), (int, float)) or isinstance(e.get("t"), bool):
                continue
            if ("box" in e and e["box"] not in self.boxes) or ("wire" in e and e["wire"] not in self.wires):
                continue
            t, kind = float(e["t"]), e.get("type")
            try:
                float(e.get("dur", 1.0)), float(e.get("until", 1e9)), int(e.get("dir", 1))
            except (TypeError, ValueError):
                continue
            if kind == "pulse":
                self.pulses.append((e["wire"], t, float(e.get("dur", 1.0)), int(e.get("dir", 1)), e.get("label")))
            elif kind == "light":
                self.windows[e["box"]].append((t, float(e.get("until", 1e9))))
            elif kind == "log":
                self.logs.append((t, e))
            elif kind == "status":
                self.status_ev.append((t, e["key"], e["value"]))
            elif kind == "highlight":
                self.highlights.append((t, e))

    # ---------------------------------------------------------- state
    def duration(self):
        return self.total

    def box_state(self, k, t):
        """0 idle, 1 working, 2 done. The most recently started window decides."""
        st = 0
        for (a, b) in self.windows[k]:
            if t >= a:
                st = 1 if t < b else 2
        return st

    def wire_lit(self, name, t, tag=None):
        v = 0.0
        for (w, ts, d, _dir, ptag) in self.pulses:
            if w == name and t >= ts and (tag is None or ptag == tag):
                end = ts + d
                if t <= end:
                    v = max(v, 1.0)
                else:
                    v = max(v, max(0.0, 1.0 - (t - end) / 6.0) * 0.55 + 0.25)
        return v

    def clock(self, ts):
        """Log time stamp: the project's start clock plus the event time (never the system clock)."""
        h, m, s = (int(x) for x in str(self.spec["log"].get("clock_start", "12:00:00")).split(":"))
        sec = (h * 3600 + m * 60 + s + int(ts)) % 86400
        return f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}"

    # ---------------------------------------------------------- drawing
    def render_frame(self, t):
        P = self.palette
        dim, gray, white, bright, line = P["dim"], P["gray"], P["white"], P["bright"], P["line"]
        c = Canvas(self.cols, self.rows, white)
        cells = c.cells
        # wires
        lit = {n: self.wire_lit(n, t) for n in self.wires}
        for (x, y), m in self.masks.items():
            if (x, y) in self.border or (x, y) in self.arrow_cells:
                continue
            if (x, y) in self.all_labels and any((x, y) in self.label_cells[n] for n in self.owners[(x, y)]):
                continue
            n = max(self.owners[(x, y)], key=lambda o: lit[o])
            col = mix(line, self.wires[n]["col"], 0.2 + 0.8 * lit[n]) if lit[n] > 0 else line
            if 0 <= y < self.rows and 0 <= x < self.cols:
                cells[y][x] = [GLYPH.get(m, "┄"), col, False]
        for name, w in self.wires.items():
            v = lit[name]
            col = mix(line, w["col"], 0.25 + 0.75 * v) if v > 0 else line
            for (ax, ay, ch) in w["arrows"]:
                cells[ay][ax] = [ch, mix(col, bright, 0.3 * v) if v > 0 else mix(line, gray, 0.45), v > 0]
            for (lx, ly, text, ltag) in w["labels"]:
                for i in range(tw(text) + 2):
                    if 0 <= lx - 1 + i < self.cols:
                        cells[ly][lx - 1 + i] = [" ", white, False]
                lv = self.wire_lit(name, t, ltag) if ltag else v
                c.put(lx, ly, text, mix(dim, mix(w["col"], white, 0.55), lv) if lv > 0 else mix(BG, dim, 0.6))
        # boxes
        for k, (x0, y0, x1, y1) in self.rect.items():
            self.draw_box(c, k, t)
        # packets
        for (w, ts, d, direction, _tag) in self.pulses:
            if ts <= t <= ts + d + 0.05:
                pts = self.wires[w]["cells"]
                if direction < 0:
                    pts = pts[::-1]
                prog = min(1.0, max(0.0, (t - ts) / d))
                prog = 1 - (1 - prog) ** 2
                head = int(prog * (len(pts) - 1))
                col = self.wires[w]["col"]
                for j, (ch, inten) in enumerate(TRAIL):
                    idx = head - j
                    if idx >= 0:
                        x, y = pts[idx]
                        if (x, y) in self.border:
                            continue
                        cells[y][x] = [ch, bright if j == 0 else mix(BG, col, inten), True]
        self.draw_title(c, t)
        lg = self.spec.get("legend")
        if lg:
            lx, ly = lg["at"]
            for i, item in enumerate(lg["items"]):
                c.put(lx, ly + i, "■", self.color(item["color"]))
                c.put(lx + 2, ly + i, str(item["text"]), gray)
        self.draw_log(c, t)
        self.draw_prompt(c, t)
        self.draw_status(c, t)
        return c.normalize()

    def draw_box(self, c, k, t):
        P = self.palette
        cells = c.cells
        b = self.boxes[k]
        x0, y0, x1, y1 = self.rect[k]
        st = self.box_state(k, t)
        base = self.color(b["color"])
        col = mix(BG, base, 0.35) if st == 0 else base if st == 1 else mix(BG, base, 0.8)
        for x in range(x0 + 1, x1):
            cells[y0][x] = ["─", col, False]
            cells[y1][x] = ["─", col, False]
        for y in range(y0 + 1, y1):
            cells[y][x0] = ["│", col, False]
            cells[y][x1] = ["│", col, False]
            for x in range(x0 + 1, x1):
                cells[y][x] = [" ", P["white"], False]
        cells[y0][x0], cells[y0][x1] = ["┌", col, False], ["┐", col, False]
        cells[y1][x0], cells[y1][x1] = ["└", col, False], ["┘", col, False]
        c.put(x0 + 2, y0, f" {b.get('tag', k)} ", col, st > 0)
        lines = [str(b["name"]), str(b["role"])] + [str(d) for d in b.get("details") or []]
        yy = y0 + (y1 - y0 + 1 - len(lines)) // 2
        marks = [(ht, e) for ht, e in self.highlights if e["box"] == k and t >= ht]
        for i, text in enumerate(lines):
            if i == 0:
                fg, bold = (mix(BG, base, 0.6), False) if st == 0 else (base, True)
            elif i == 1:
                fg, bold = (mix(BG, P["gray"], 0.55), False) if st == 0 else (P["white"] if st == 1 else P["gray"], False)
            else:
                fg, bold = (mix(BG, P["dim"], 0.7), False) if st == 0 else (P["dim"], False)
            x = x0 + (x1 - x0 + 1 - tw(text)) // 2
            c.put(x, yy + i, text, fg, bold)
            if i >= 2:
                for _ht, e in marks:
                    at = text.find(str(e["text"]))
                    if at >= 0:
                        c.put(x + tw(text[:at]), yy + i, str(e["text"]), self.color(e.get("color", b["color"])), True)
        if st == 1:      # a working box: a light runs around its border
            ring = ([(x, y0) for x in range(x0, x1 + 1)] + [(x1, y) for y in range(y0 + 1, y1 + 1)]
                    + [(x, y1) for x in range(x1 - 1, x0 - 1, -1)] + [(x0, y) for y in range(y1 - 1, y0, -1)])
            f = int(t * self.fps)
            for j in range(12):
                x, y = ring[(f * 2 - j) % len(ring)]
                ch = cells[y][x]
                if ch[0] not in (" ", ""):
                    ch[1] = mix(base, P["bright"], 0.55 * (1 - j / 12))

    def title_text(self):
        return "   ".join(" ".join(wd) for wd in str(self.spec["title"]["text"]).split())

    def draw_title(self, c, t):
        T = self.spec.get("title")
        if not T:
            return
        title = self.title_text()
        x = (self.cols - tw(title)) // 2
        n = len(title)
        sweep = (t * 0.55) % 1.6 - 0.3
        for k, ch in enumerate(title):
            hue = (k / n * 0.85 - t * 0.45) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.72, 1.0)
            hit = max(0.0, 1 - abs(k / n - sweep) * 9)
            x = c.put(x, int(T.get("row", 1)), ch,
                      mix((int(r * 255), int(g * 255), int(b * 255)), self.palette["bright"], 0.75 * hit), True)

    def draw_log(self, c, t):
        L = self.spec.get("log")
        if not L:
            return
        P = self.palette
        cells = c.cells
        lx0, ly0, lx1, ly1 = L["rect"]
        lcol = mix(BG, P["gray"], 0.55)
        for x in range(lx0 + 1, lx1):
            cells[ly0][x] = ["─", lcol, False]
            cells[ly1][x] = ["─", lcol, False]
        for y in range(ly0 + 1, ly1):
            cells[y][lx0] = ["│", lcol, False]
            cells[y][lx1] = ["│", lcol, False]
        cells[ly0][lx0], cells[ly0][lx1] = ["┌", lcol, False], ["┐", lcol, False]
        cells[ly1][lx0], cells[ly1][lx1] = ["└", lcol, False], ["┘", lcol, False]
        c.put(lx0 + 2, ly0 + 1, str(L["title"]), P["gray"])
        shown = sorted(((ts, i) for i, (ts, _e) in enumerate(self.logs) if ts <= t), key=lambda p: -p[0])
        for row, (ts, i) in enumerate(shown[:int(L.get("lines", 2))]):
            e = self.logs[i][1]
            text = str(e["text"])
            if row == 0:
                text = text[:max(0, int((t - ts) * float(L.get("cps", 40))))]
            yy = ly0 + 2 + row
            x = c.put(lx0 + 2, yy, self.clock(ts), P["dim"]) + 2
            x = c.put(x, yy, str(e.get("tag", "")), self.color(e.get("color", "white")), True) + 2
            c.put(x, yy, text, P["white"] if row == 0 else P["gray"])

    def draw_prompt(self, c, t):
        Q = self.spec.get("prompt")
        if not Q:
            return
        P = self.palette
        px, py = Q["at"]
        prefix = str(Q["prefix"])
        cmd = prefix + " " + str(Q["command"])
        delay, cps = float(Q.get("delay", 0.4)), float(Q.get("cps", 16))
        typed = cmd[:max(0, int((t - delay) * cps))] if t >= delay else ""
        if typed:
            c.put(px, py, typed[:len(prefix)], P["gray"])
            c.put(px + tw(prefix), py, typed[len(prefix):], P["white"], True)
        if int(t * 2) % 2 == 0 or typed != cmd:
            c.put(px + tw(typed), py, "█", P["gray"])

    def draw_status(self, c, t):
        S = self.spec.get("status")
        if not S:
            return
        P = self.palette
        initial = {str(k["key"]): str(k["initial"]) for k in S["keys"]}
        state = dict(initial)
        for (ts, key, val) in sorted(self.status_ev, key=lambda e: (e[0], e[1], e[2])):
            if t >= ts:
                state[key] = str(val)
        x, y = S["at"]
        for k in S["keys"]:
            key = str(k["key"])
            x = c.put(x, y, key + " [", P["dim"])
            live = state[key] != initial[key]
            x = c.put(x, y, state[key], self.color(S.get("live_color", "green")) if live else P["gray"], live)
            x = c.put(x, y, "]", P["dim"]) + 2

    # ---------------------------------------------------------- checks
    def check(self):
        """Problems that the field rules cannot see: text that collides on this fixed layout."""
        out = []
        S = self.spec
        kinds = {k: EVENT_KEYS[k] for k in S.get("event_types", list(EVENT_KEYS))}
        keys = [str(k["key"]) for k in (S.get("status") or {}).get("keys", [])]
        tags = sorted({lb[3] for w in self.wires.values() for lb in w["labels"] if lb[3]})
        names = {"wire": list(self.wires), "box": list(self.boxes), "key": keys, "label": tags,
                 "color": [k for k in self.palette if k in S.get("event_colors", self.palette)]}
        out += check_events(self.events, kinds, names, self.total)
        for i, e in enumerate(self.events):
            for k in ("dur", "until", "dir"):
                if isinstance(e, dict) and k in e and (not isinstance(e[k], (int, float)) or isinstance(e[k], bool)):
                    out.append(problem("wrong_type", f"events[{i}].{k}", "write a number", actual=e[k]))
        title = self.title_text()
        if tw(title) > self.cols - 2:
            out.append(problem("too_long_on_screen", S["title"].get("field", "fields.title"),
                               f"the spaced-out title is {tw(title)} cells; the screen holds {self.cols - 2}",
                               actual=tw(title), limit=self.cols - 2, over=tw(title) - self.cols + 2))
        for k, b in self.boxes.items():
            x0, y0, x1, y1 = self.rect[k]
            inner = x1 - x0 - 1
            lines = [("name", b["name"]), ("role", b["role"])] + \
                [(f"details[{i}]", d) for i, d in enumerate(b.get("details") or [])]
            if len(lines) > y1 - y0 - 1:
                out.append(problem("too_many", f"{b.get('field', 'box ' + k)}.details",
                                   f"box {k} holds {y1 - y0 - 1} lines in all", actual=len(lines), limit=y1 - y0 - 1))
            for sub, text in lines:
                if tw(str(text)) > inner:
                    out.append(problem("too_long_on_screen", f"{b.get('field', 'box ' + k)}.{sub}",
                                       f"box {k} is {inner} cells wide inside", actual=tw(str(text)), limit=inner,
                                       over=tw(str(text)) - inner, text=str(text)))
        # wire labels must not touch boxes, arrows, other wires or other labels
        taken = {}
        for name, w in self.wires.items():
            other_wires = {p for n2, w2 in self.wires.items() if n2 != name for p in expand(w2["pts"])}
            for i, (lx, ly, text, _tag) in enumerate(w["labels"]):
                span = {(lx - 1 + j, ly) for j in range(tw(text) + 2)}
                field = (next((lb for lb in S["wires"] if lb["id"] == name), {}).get("labels") or [{}])[i].get("field", f"wire {name}")
                hit = (span & self.border) or (span & self.arrow_cells) or (span & other_wires) \
                    or any(span & s for s in taken.values())
                if hit or lx < 1 or lx + tw(text) >= self.cols:
                    out.append(problem("too_long_on_screen", field,
                                       "this net label runs into a box, an arrow or another label; shorten it",
                                       actual=tw(text), text=text))
                taken[(name, i)] = span
        L = S.get("log")
        if L:
            room = L["rect"][2] - (L["rect"][0] + 2)
            for i, e in enumerate(self.events):
                if isinstance(e, dict) and e.get("type") == "log":
                    n = 8 + 2 + tw(str(e.get("tag", ""))) + 2 + tw(str(e.get("text", "")))
                    if n > room:
                        out.append(problem("too_long_on_screen", f"events[{i}].text",
                                           f"a log line holds {room} cells including the time and tag",
                                           actual=n, limit=room, over=n - room, text=str(e.get("text", ""))))
        St = S.get("status")
        if St:
            widest = {str(k["key"]): tw(str(k["initial"])) for k in St["keys"]}
            source = {str(k["key"]): f"fields.status[{i}].initial" for i, k in enumerate(St["keys"])}
            for i, e in enumerate(self.events):
                if isinstance(e, dict) and e.get("type") == "status" and str(e.get("key")) in widest:
                    if tw(str(e.get("value", ""))) > widest[str(e["key"])]:
                        widest[str(e["key"])] = tw(str(e.get("value", "")))
                        source[str(e["key"])] = f"events[{i}].value"
            n = St["at"][0] + sum(tw(k) + 2 + v + 1 + 2 for k, v in widest.items()) - 2
            room = self.cols - St["at"][0]   # the same margin on the right as on the left
            if n > room:
                keys = [f"fields.status[{i}].key" for i in range(len(St["keys"]))]
                parts = ", ".join(keys + [source[k] for k, _ in sorted(widest.items(), key=lambda kv: -kv[1])])
                out.append(problem("too_long_on_screen", "fields.status",
                                   f"the status line needs {n} cells with its longest values; it holds {room}; "
                                   f"fix: shorten these keys and values by {n - room} cells in total: {parts}",
                                   actual=n, limit=room, over=n - room))
        Q = S.get("prompt")
        if Q:
            n = Q["at"][0] + tw(str(Q["prefix"]) + " " + str(Q["command"])) + 1
            if n > self.cols:
                out.append(problem("too_long_on_screen", Q.get("field", "fields.command"),
                                   f"the command line is {n} cells; the screen has {self.cols}",
                                   actual=n, limit=self.cols, over=n - self.cols))
        return out
