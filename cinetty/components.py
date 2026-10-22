"""Box contents and overlays.

Every component is built from a dict (``type`` plus fields) and draws itself
with ``draw(canvas, box, t, scene)``. Round-layer components receive the content
time (real time, or the snapshot time while the opening and closing frames
fade); live components always receive real time.

Many numeric defaults below (stagger fractions, growth spans, column offsets)
reproduce the original JEV × Harness² animations cell for cell. They are fields
so a template can change them, not magic numbers to tune per frame.
"""
from __future__ import annotations

import math

from .canvas import BG, clamp01, cw, ease_out, mix, rolling, tw, typed

REGISTRY = {}


def component(name):
    def deco(cls):
        REGISTRY[name] = cls
        cls.type_name = name
        return cls
    return deco


def build(spec, scene):
    kind = spec.get("type")
    if kind not in REGISTRY:
        raise ValueError(f"unknown component type {kind!r} (known: {', '.join(sorted(REGISTRY))})")
    return REGISTRY[kind](spec, scene)


class Component:
    z = "over"

    def __init__(self, spec, scene):
        self.spec = spec
        self.S = scene
        self.z = spec.get("z", "over")

    def get(self, key, default=None):
        return self.spec.get(key, default)

    def col(self, key, default):
        v = self.spec.get(key)
        return self.S.color(v if v is not None else default)

    def visible(self, t, S):
        """``show: {phase, at}`` hides the component until that point of the current round."""
        sh = self.spec.get("show")
        if not sh:
            return True
        ri = S.tl.round_at(t)
        sp = S.tl.PH[ri].get(sh["phase"])
        if sp is None:
            return False
        s, e = sp
        return t >= s + float(sh.get("at", 0.0)) * (e - s)


def inner_y(b, i):
    return b.y0 + 1 + i


def centered(c, b, row, text, fg, bold=False, full=None, where=None):
    width = tw(full if full is not None else text)
    c.fit(full if full is not None else text, b.w - 2, where or f"{b.key}.row{row}")
    c.put(b.x0 + 1 + (b.w - 2 - width) // 2, inner_y(b, row), text, fg, bold)


def bar(c, S, x, y, w, val, col, tick=None, dim=False, head=True, tick_mix=0.7):
    """Gradient bar: ``█`` cells, a partial-block head, ``·`` track, optional tick mark."""
    dimc, gray, bright = S.palette["dim"], S.palette["gray"], S.palette["bright"]
    filled = max(0.0, min(1.0, val)) * w
    full = int(filled)
    frac = filled - full
    tk = int(tick * w) if tick is not None else -1
    for k in range(w):
        ch, cc = "·", mix(BG, dimc, 0.5)
        if k < full:
            ch = "█"
            cc = mix(mix(BG, col, 0.45), col, k / max(1, w - 1) + 0.2)
            if head and val < 0.999 and k >= full - 2:
                cc = mix(cc, bright, 0.5 if k == full - 1 else 0.25)
        elif k == full and frac > 0:
            ch = "▏▎▍▌▋▊▉"[min(6, int(frac * 7))]
            cc = mix(col, bright, 0.6) if head else col
        if k == tk:
            if ch == "·":
                ch, cc = "│", mix(BG, gray, tick_mix)
            else:
                cc = mix(cc, bright, 0.5)
        if dim:
            cc = mix(BG, cc, 0.4)
        c.put(x + k, y, ch, cc)


def phase_span(S, t, phase):
    ri = S.tl.round_at(t)
    return ri, S.tl.PH[ri].get(phase)


# ------------------------------------------------------------------ text
@component("text")
class Text(Component):
    """One line. ``align``: left (at ``x`` from the box's left border), center or right.

    ``typed: {phase, at, cps}`` types the text from that point of the round;
    ``active: {tick: go|fallback, window}`` switches to ``active_color`` and bold.
    """

    def draw(self, c, b, t, S):
        if not self.visible(t, S):
            return
        text = S.text(self.spec["text"], t)
        fg = self.col("color", "soft")
        bold = bool(self.get("bold", False))
        sw = self.get("tick_switch")
        if sw and S.ticker:
            key = "go" if S.ticker.step(t)["go"] else "fallback"
            text = S.text(sw[key]["text"], t)
            fg = S.color(sw[key]["color"])
        full = S.text(self.spec["full"], t) if "full" in self.spec else text
        act = self.get("active")
        if act and S.ticker:
            st = S.ticker.step(t)
            want = act.get("tick", "go") == "go"
            lo, hi = act.get("window", [0.4, 0.95])
            on = st["go"] == want and lo < st["u"] < hi
            if on:
                fg = self.col("active_color", "bright")
                bold = True
            if "inactive_text" in self.spec and not on:
                text = S.text(self.spec["inactive_text"], t)
        ty = self.get("typed")
        if ty:
            ri, sp = phase_span(S, t, ty["phase"])
            if sp is None:
                return
            s, e = sp
            t0 = s + float(ty.get("at", 0.0)) * (e - s)
            if t < t0:
                return
            if not (ty.get("finish_at_end") and t >= e):
                text = typed(text, t0, float(ty.get("cps", 110)), t)
        if b is None:
            x, y = int(self.spec["x"]), int(self.spec["y"])
            c.put(x, y, text, fg, bold)
            return
        row = int(self.get("row", 0))
        align = self.get("align", "left")
        if align == "center":
            width = tw(full)
            c.fit(full, b.w - 2, f"{b.key}.row{row}")
            x = b.x0 + 1 + (b.w - 2 - width) // 2 + int(S.value(self.get("shift", 0), t))
        elif align == "right":
            x = b.x1 - int(self.get("x", 2)) - tw(full) + 1
        else:
            x = b.x0 + int(self.get("x", 1))
            if self.get("fit", True):
                c.fit(full, b.x1 - x, f"{b.key}.row{row}")
        y = inner_y(b, row) if self.get("on_border") is None else (b.y0 if self.get("on_border") == "top" else b.y1)
        c.put(x, y, text, fg, bold)


@component("lines")
class Lines(Component):
    """Lines typed in one after another during a phase.

    ``items``: a list (or a binding returning a list) of strings or
    ``{text, dim}``. Item ``i`` starts at ``phase start + i * step * phase length``.
    """

    def draw(self, c, b, t, S):
        ri, sp = phase_span(S, t, self.spec["phase"])
        if sp is None:
            return
        s, e = sp
        if t < s:
            return
        items = S.value(self.spec["items"], t)
        step = float(self.get("step", 0.2))
        cps = float(self.get("cps", 110))
        x = b.x0 + int(self.get("x", 2))
        row0 = int(self.get("row", 0))
        color = self.col("color", "soft")
        dim_color = self.col("dim_color", ["mix", "soft", "dim", 0.55])
        flash_s = float(self.get("flash", 0.15))
        flash_color = self.S.color(self.get("flash_color")) if self.get("flash_color") else None
        prefix = self.get("prefix", "")
        for i, item in enumerate(items):
            a0 = s + (e - s) * step * i
            if t < a0:
                continue
            text, dim = (item, False) if isinstance(item, str) else (item["text"], bool(item.get("dim")))
            if self.get("dim_negative") and isinstance(item, str):
                dim = text.split()[-1].startswith("-") if text.split() else False
            text = prefix.format(n=i + 1) + text
            c.fit(text, b.x1 - x, f"{b.key}.item{i}")
            flash = (t - a0) < flash_s
            fg = dim_color if dim else color
            if flash and flash_color is not None:
                fg = flash_color
            c.put(x, inner_y(b, row0 + i * int(self.get("row_step", 1))), typed(text, a0, cps, t), fg, flash)


# ------------------------------------------------------------------ bars
@component("bars")
class Bars(Component):
    """Rows of label + gradient bar + percent.

    ``mode: rank`` lights rows whose value reaches ``lit_at`` once the phase ends
    (``★`` for labels in ``seeds``, ``▸`` for lit ones). ``mode: keep`` marks rows
    with ``✓``/``✕`` against ``threshold`` as each bar settles; ``mark: left`` or
    ``right`` places that mark.
    """

    def draw(self, c, b, t, S):
        ri, sp = phase_span(S, t, self.spec["phase"])
        if sp is None:
            return
        s, e = sp
        if t < s:
            return
        items = S.value(self.spec["items"], t)        # list of [label, value]
        mode = self.get("mode", "keep")
        inner = b.w - 2
        n = len(items)
        lw = int(S.value(self.get("label_w"), t)) if self.get("label_w") is not None else max(tw(lab) for lab, _ in items)
        stagger = float(self.get("stagger", 0.5)) / max(1, int(self.get("stagger_n", n)))
        grow = float(self.get("grow", 0.4))
        row0 = int(self.get("row", 0))
        bright, gold, dimc = S.palette["bright"], S.color(self.get("lit_color", "gold")), S.palette["dim"]
        col0 = self.col("color", "soft")
        faded = mix(BG, dimc, 0.8)
        if mode == "rank":
            seeds = set(S.value(self.spec.get("seeds", "{[]}"), t) or [])
            done = t >= e
            bw = inner - 2 - lw - 1 - 1 - 4
            for i, (lab, val) in enumerate(items):
                y = inner_y(b, row0 + i)
                a0 = s + (e - s) * stagger * i
                a1 = a0 + (e - s) * grow
                p = ease_out(clamp01((t - a0) / (a1 - a0))) if t >= a0 else 0.0
                v = val * p
                lit = done and val >= float(self.get("lit_at", 0.6))
                dim = done and not lit
                col = col0 if not lit else gold
                if t >= a0:
                    c.put(b.x0 + 1, y, "★" if i in seeds else ("▸" if lit else " "), gold if (i in seeds or lit) else col0, True)
                    c.put(b.x0 + 3, y, lab, mix(BG, col, 0.45) if dim else (bright if lit else col), lit)
                    bar(c, S, b.x0 + 3 + lw + 1, y, bw, v, col, dim=dim, tick_mix=float(self.get("tick_mix", 0.6)))
                    c.put(b.x0 + 3 + lw + 1 + bw + 1, y, f"{int(round(v * 100)):>3d}%", mix(BG, col, 0.45) if dim else col, lit)
            return
        th = float(self.spec["threshold"])
        mark = self.get("mark", "left")
        for i, (lab, val) in enumerate(items):
            y = inner_y(b, row0 + i * int(self.get("row_step", 1)))
            a0 = s + (e - s) * stagger * i
            p = ease_out(clamp01((t - a0) / ((e - s) * grow))) if t >= a0 else 0.0
            keep = val >= th
            settled = t >= a0 + (e - s) * grow
            if t < a0:
                continue
            if mark == "left":
                bw = inner - 2 - lw - 1 - 1 - 4 - 2
                col = col0 if keep else faded
                c.put(b.x0 + 1, y, "✓" if (keep and settled) else ("✕" if settled else " "), gold if keep else dimc, True)
                c.put(b.x0 + 3, y, lab, col if not keep else bright, keep and settled)
                bar(c, S, b.x0 + 3 + lw + 1, y, bw, val * p, col if keep or not settled else faded, tick=th,
                    dim=(settled and not keep), tick_mix=float(self.get("tick_mix", 0.6)))
                c.put(b.x0 + 3 + lw + 1 + bw + 1, y, f"{int(round(val * p * 100)):>3d}%", col, keep and settled)
            else:
                fade = settled and not keep
                col = col0 if keep or not settled else faded
                bx = b.x0 + 3 + lw
                bw = inner - 3 - lw - 1 - 4 - 3
                c.put(b.x0 + 2, y, lab, gold if (keep and settled) else (col if not fade else dimc), keep and settled)
                bar(c, S, bx, y, bw, val * p, col, tick=th, dim=fade, tick_mix=float(self.get("tick_mix", 0.6)))
                c.put(bx + bw + 1, y, f"{int(round(val * p * 100)):>3d}%", col if not fade else dimc, keep and settled)
                c.put(bx + bw + 6, y, "✓" if (keep and settled) else ("✕" if fade else " "), gold if keep else dimc, True)
        summ = self.get("summary")
        if summ and t >= e:
            kept = sum(1 for _, v in items if v >= th)
            txt = summ["text"].format(k=kept, d=n - kept)
            full = summ.get("prefix", "") + txt
            c.fit(full, inner, f"{b.key}.summary")
            shown = typed(full, e, float(summ.get("cps", 28.8)), t)
            c.put(b.x0 + 1 + (inner - tw(full)) // 2, inner_y(b, int(summ.get("row", 6))), shown,
                  mix(col0, bright, 0.5), True)
            flash_box(c, b, S, t - e, 0.55)


def flash_box(c, b, S, ft, strength, span=0.35):
    """White flash over a box right after a result lands."""
    if not (0 <= ft < span):
        return
    f = 1 - ft / span
    bright = S.palette["bright"]
    for y in range(b.y0 + 1, b.y1):
        for x in range(b.x0 + 1, b.x1):
            ch = c.cells[y][x]
            if ch[0] == " ":
                c.cells[y][x] = ["░", mix(BG, bright, strength * f), False]
            else:
                ch[1] = mix(ch[1], bright, 0.85 * f)


# ------------------------------------------------------------------ race
@component("race")
class Race(Component):
    """Candidates race to their scores; digits roll until each bar lands.

    ``layout: two_line`` puts the name above the bar, top ``winners`` get ★ and
    ``fail`` (index) stops at 45% with a red ✕. ``layout: inline`` puts
    ``H1 bar 84% ★`` on one row and compares against ``base`` (a tick on the bar);
    only ``win`` (index) gets the star.
    """

    def draw(self, c, b, t, S):
        ri, sp = phase_span(S, t, self.spec["phase"])
        if sp is None:
            return
        s, e = sp
        if t < s:
            return
        bright, gold, dimc, red = S.palette["bright"], S.palette["gold"], S.palette["dim"], S.palette["red"]
        col0 = self.col("color", "soft")
        faded = mix(BG, dimc, 0.8)
        inner = b.w - 2
        sc = S.value(self.spec["scores"], t)
        n = len(sc)
        mn, mx = min(sc), max(sc)
        if self.get("layout", "inline") == "two_line":
            names = S.value(self.spec["names"], t)
            fail = S.value(self.spec.get("fail", "{None}"), t)
            winners = int(self.get("winners", 2))
            bw = inner - 2 - 4 - 4 - 2
            order = sorted(range(n), key=lambda i: -sc[i])
            for i in range(n):
                y = inner_y(b, i * 2)
                name = names[i]
                c.fit(name, inner - 1, f"{b.key}.name{i}")
                frac = (sc[i] - mn) / (mx - mn + 1e-6)
                dur = (e - s) * (0.5 + 0.38 * frac)
                failing = i == fail
                p = ease_out(clamp01((t - s) / dur))
                if failing:
                    p = min(p, 0.45)
                    fail_t = s + dur * 0.42
                    failed = t >= fail_t
                    flash = max(0.0, 1 - (t - fail_t) / 0.3) if failed else 0.0
                else:
                    failed, flash = False, 0.0
                finished = (t >= s + dur) and not failing
                win = finished and i in order[:winners] and t >= e - 0.05
                lose = failed or (t >= e and i not in order[:winners])
                col = col0 if not (lose and not failed) else faded
                if failed:
                    col = mix(col0, red, min(1.0, flash * 1.3)) if flash > 0 else faded
                c.put(b.x0 + 1, y, name, mix(BG, col, 0.5) if (lose and flash == 0) else (bright if win else col), win)
                bx = b.x0 + 1
                bar(c, S, bx, y + 1, bw, sc[i] * p / max(sc[i], 1e-6) * sc[i] if not failing else sc[i] * p / 0.9, col,
                    dim=(lose and flash == 0), head=not failed, tick_mix=float(self.get("tick_mix", 0.6)))
                final = f"{sc[i]:.2f}"
                if failed:
                    txt, fg = "✕", red if flash > 0 else dimc
                else:
                    txt = rolling(final, s + dur + 0.25, t if t >= s else s, i)
                    fg = bright if win else (col if not lose else dimc)
                c.put(bx + bw + 1, y + 1, txt, fg, win or flash > 0)
                c.put(bx + bw + 6, y + 1, "★" if win else " ", gold, True)
            return
        base = float(S.value(self.spec["base"], t))
        win_i = S.value(self.spec.get("win", "{None}"), t)
        label_w = int(self.get("label_w", 3))
        gap = int(self.get("gap", 3))
        star_off = int(self.get("star_offset", 5))
        bw = inner - label_w - 2 - 4 - gap
        best = max(range(n), key=lambda i: sc[i])
        row_step = int(self.get("row_step", 1))
        for i in range(n):
            y = inner_y(b, i * row_step)
            frac = (sc[i] - mn) / (mx - mn + 1e-6)
            dur = (e - s) * (0.55 + 0.35 * frac)
            p = ease_out(clamp01((t - s) / dur))
            done = t >= s + dur
            beats = sc[i] > base
            win = done and beats and i == best and win_i == i
            lose = done and not win
            col = col0 if not lose else faded
            c.put(b.x0 + 1, y, f"H{i + 1}", bright if win else col, win)
            bx = b.x0 + 1 + label_w
            bar(c, S, bx, y, bw, sc[i] * p, col, tick=base, dim=lose)
            txt = rolling(f"{int(round(sc[i] * 100))}%", s + dur + 0.25, t, i, swap=S.swap)
            c.put(bx + bw + 1, y, txt, bright if win else (col if not lose else dimc), win)
            c.put(bx + bw + star_off, y, "★" if win else ("✕" if lose and t >= e else " "), gold if win else dimc, True)
            if lose and not beats and 0 <= t - (s + dur) < 0.25:
                c.put(bx + bw + star_off, y, "✕", red, True)


# ------------------------------------------------------------------ stages
@component("stages")
class Stages(Component):
    """A status line that changes with the phase, followed by a progress bar.

    ``stages``: ``[{from: phaseA, until: phaseB, text, cps}, {from: phaseB, text, done}]``;
    the bar shows the progress of the ``from`` phase.
    """

    def draw(self, c, b, t, S):
        tl = S.tl
        ri = tl.round_at(t)
        d = tl.PH[ri]
        x0 = b.x0 + int(self.get("x", 3))
        lab_w = int(self.get("label_w", 26))
        bw = b.w - 2 - int(self.get("x", 3)) - lab_w - 3
        y = inner_y(b, int(self.get("row", 1)))
        col = self.col("color", "soft")
        bright = S.palette["bright"]
        for st in self.spec["stages"]:
            s = d[st["from"]][0]
            until = d[st["until"]][0] if st.get("until") else math.inf
            if not (s <= t < until):
                continue
            e = d[st["from"]][1]
            text = S.text(st["text"], t)
            if "done" in st:
                done = t >= e
                txt = S.text(st["done"], t) if done else text
                c.fit(txt, lab_w - 1, f"{b.key}.stage")
                c.put(x0, y, txt if done else typed(txt, s, float(st.get("cps", 36)), t),
                      col if not done else mix(col, bright, .25), True)
            else:
                c.put(x0, y, typed(text, s, float(st.get("cps", 110)), t), col, True)
                c.fit(text, lab_w - 1, f"{b.key}.stage")
            bar(c, S, x0 + lab_w, y, bw, tl.pg(ri, st["from"], t), col, tick_mix=0.6)
            break


# ------------------------------------------------------------------ verdict
@component("verdict")
class Verdict(Component):
    """Each candidate's score against the baseline, then the typed conclusion and a flash."""

    def draw(self, c, b, t, S):
        ri, sp = phase_span(S, t, self.spec["phase"])
        if sp is None:
            return
        s, e = sp
        if t < s:
            return
        R = S.rounds[ri]
        inner = b.w - 2
        bright, gold, gray, dimc = S.palette["bright"], S.palette["gold"], S.palette["gray"], S.palette["dim"]
        col0 = self.col("color", "soft")
        cands, base, win, v = R[self.get("scores", "cands")], R[self.get("base", "base")], R.get("win"), R[self.get("version", "v")]
        x = b.x0 + int(self.get("x", 2))
        fmt = self.get("line", "{lab} {val} {rel} {cur}")
        room = inner - (x - b.x0 - 1)

        def lines(pct):
            return [fmt.format(lab=f"H{i + 1}", val=f"{int(round(sc * 100))}{pct}", rel=">" if sc > base else "≤",
                               cur=f"v{v[0]} {int(round(base * 100))}{pct}") for i, sc in enumerate(cands)]
        # A score of 100 makes a line one or two cells longer; the round then drops the percent
        # signs from all its lines, so the numbers stay as the project gives them and line up.
        texts = lines("%")
        if max(tw(t_) for t_ in texts) > room:
            texts = lines("")
        for i, sc in enumerate(cands):
            beats = sc > base
            line = texts[i]
            c.fit(line, room, f"{b.key}.line{i}")
            col = bright if win == i else (col0 if beats else mix(BG, dimc, 0.8))
            if t >= s + (e - s) * 0.12 * (i + 1):
                c.put(x, inner_y(b, i), line, col, win == i)
        rule = self.get("rule")
        if rule and t >= s + 0.5 * (e - s) * 0.6:
            centered(c, b, int(rule.get("row", 3)), S.text(rule["text"], t), mix(BG, gold, 0.7))
        if t >= s + 0.6 * (e - s):
            # ``format: false`` when the texts are built from bindings instead of a {v} placeholder.
            fmt_v = (lambda s_, x: s_.format(v=x)) if self.get("format", True) else (lambda s_, x: s_)
            if win is not None:
                txt = fmt_v(S.text(self.spec["win_text"], t), f"v{v[1]}")
                col = gold
            else:
                txt = fmt_v(S.text(self.spec["keep_text"], t), f"v{v[0]}")
                col = gray
            c.fit(txt, b.x1 - x, f"{b.key}.verdict")
            c.put(x, inner_y(b, int(self.get("verdict_row", 4))), typed(txt, s + 0.6 * (e - s), float(self.get("cps", 28.8)), t), col, True)
            if win is not None:
                flash_box(c, b, S, t - (s + 0.6 * (e - s)), 0.5)


# ------------------------------------------------------------------ chips
@component("chips")
class Chips(Component):
    """``[tag]`` chips, two per row, lit for every lesson learned so far, plus a counter line."""

    def draw(self, c, b, t, S):
        tl = S.tl
        ri = tl.round_at(t)
        labels = S.value(self.spec["labels"], t)
        sets = [set(r[self.get("key", "learned")]) for r in S.rounds]
        # Learned items may be given by label or by index.
        sets = [{labels.index(x) if isinstance(x, str) else x for x in st} for st in sets]
        lit = set()
        for k in range(ri):
            lit |= sets[k]
        s, e = tl.PH[ri][self.spec["phase"]]
        if t >= s + (e - s) * 0.4:
            lit |= sets[ri]
        inner = b.w - 2
        gold, dimc, bright = S.palette["gold"], S.palette["dim"], S.palette["bright"]
        per = int(self.get("per_row", 2))
        for r_ in range((len(labels) + per - 1) // per):
            x = b.x0 + 2
            for k in range(r_ * per, min(len(labels), r_ * per + per)):
                on = k in lit
                x = c.put(x, inner_y(b, 1 + r_), f"[{labels[k]}]", mix(gold, bright, 0.25) if on else mix(BG, dimc, 0.8), on) + 1
            c.fit("x" * (x - b.x0 - 2), inner - 1, f"{b.key}.row{r_}")
        cn = self.get("counter")
        if cn:
            name = cn["name"]
            a, v = S.counter_pair(name, t)
            fmt_roll, fmt_one = cn.get("rolling", "{label} {a} → {v}"), cn.get("single", "{label} {a}")
            label = S.text(cn.get("label", "lessons"), t)
            if t >= s or ri > 0 or t >= tl.FADE_S:
                if t >= tl.HOT_S:
                    txt = fmt_one.format(label=label, a=S.counter(name, t))
                else:
                    txt = fmt_roll.format(label=label, a=a, v=v) if a != v else fmt_one.format(label=label, a=a)
                c.put(b.x0 + 2, inner_y(b, int(cn.get("row", 5))), txt, gold, True)
                c.fit(txt, int((self.get("next") or {}).get("x", 22)) - 1, f"{b.key}.counter")
        nx = self.get("next")
        if nx and tl.in_phase(ri, nx["phase"], t):
            x = b.x0 + 2 + int(nx.get("x", 22))
            txt = "→ " + S.text(nx["text"], t)
            c.put(x, inner_y(b, int(nx.get("row", 5))), txt, mix(gold, bright, .2))
            c.fit(txt, b.x1 - 1 - x, f"{b.key}.next")


# ------------------------------------------------------------------ sequence
@component("sequence")
class Sequence(Component):
    """A row of outcome symbols (✓ ✗ ⇄) revealed across a phase, optional typed legend."""

    def draw(self, c, b, t, S):
        ri, sp = phase_span(S, t, self.spec["phase"])
        if sp is None:
            return
        s, e = sp
        if t < s:
            return
        go, red, fb, dimc = S.color(self.get("ok_color", "go")), S.palette["red"], S.color(self.get("alt_color", "fb")), S.palette["dim"]
        seq = S.value(self.spec["items"], t)
        if self.get("max"):
            seq = seq[:int(self.spec["max"])]
        p = min(1.0, (t - s) / max(1e-6, e - s))
        x = b.x0 + int(self.get("x", 2))
        sp_ = int(self.get("spacing", 2))
        cross = self.get("cross", "✗")
        for i, ch in enumerate(seq):
            shown = i < int(p * len(seq) + 0.999)
            col = {"✓": mix(BG, go, 0.7), "✗": red, "⇄": fb}[ch]
            if not shown:
                col = mix(BG, dimc, 0.4)
                ch = "·"
            c.put(x + i * sp_, inner_y(b, 0), cross if ch == "✗" else ch, col, ch in "✗⇄")
        leg = self.get("legend")
        if leg:
            txt = S.text(leg, t)
            c.fit(txt, b.w - 4, f"{b.key}.legend")
            x = b.x0 + 2
            rose = S.color(self.get("legend_color", "rose"))
            for ch in typed(txt, s, float(self.get("cps", 110)), t):
                col = red if ch == "✗" else (fb if ch == "⇄" else mix(rose, S.palette["bright"], 0.2))
                x = c.put(x, inner_y(b, 1), ch, col, True)


# ------------------------------------------------------------------ store
@component("store")
class Store(Component):
    """Versioned store: version badge, ``vA → vB`` while a win lands, growing entry list.

    ``layout: badge`` draws a small ``╭─────╮`` badge with the version and a
    subtitle above the entries; ``layout: compact`` writes ``vN`` on the first
    row and two lines per entry (``icon cue`` / ``→ lesson``) with ``+N`` for the rest.
    """

    def draw(self, c, b, t, S):
        tl = S.tl
        ri = tl.round_at(t)
        R = S.rounds[ri]
        phase = self.spec["phase"]
        s, e = tl.PH[ri][phase]
        v = S.version(t)
        win = R.get("win") is not None
        jump = 0.0
        if win and s <= t < e:
            jump = max(0.0, 1 - (t - (s + 0.4 * (e - s))) / 0.4) if t >= s + 0.4 * (e - s) else 0.0
        gold, bright, soft = S.palette["gold"], S.palette["bright"], S.palette["soft"]
        col = mix(gold, bright, 0.6 * jump)
        nkey = self.get("count_key", "n_ent")
        prev_n = S.rounds[ri - 1][nkey] if ri > 0 else int(S.value(self.spec["initial"], t))
        n_adopted = R[nkey] if (t >= s + 0.4 * (e - s) and win) or t >= tl.HOT_S else prev_n
        if t >= tl.HOT_S:
            n_adopted = int(self.get("final", S.rounds[-1][nkey]))
        entries = S.value(self.spec["entries"], t)
        if self.get("layout", "badge") == "badge":
            for i, row in enumerate(["╭─────╮", "│     │", "╰─────╯"]):
                c.put(b.x0 + 2, inner_y(b, i), row, mix(gold, BG, 0.15 if jump > 0 else 0.35))
            c.put(b.x0 + 5, inner_y(b, 1), f"v{v}", col, True)
            ver = S.text(self.spec["jump_text"], t).format(a=R["v"][0], b=R["v"][1]) if jump > 0 else S.text(self.get("version_text", ""), t).format(v=v)
            c.fit(ver, b.w - 12, f"{b.key}.version")
            c.put(b.x0 + 11, inner_y(b, 1), ver, mix(gold, bright, 0.7 if jump > 0 else 0.2), True)
            sub = S.text(self.get("subtitle", ""), t)
            c.fit(sub, b.w - 4, f"{b.key}.subtitle")
            c.put(b.x0 + 2, inner_y(b, 3), sub, mix(gold, BG, 0.4))
            for i in range(len(entries)):
                y = inner_y(b, 4 + i)
                if y >= b.y1:
                    break
                if i < n_adopted:
                    c.fit(entries[i], b.w - 4, f"{b.key}.entry{i}")
                    new = i >= prev_n and jump > 0
                    txt = "▸ " + entries[i] if tw("▸ " + entries[i]) <= b.w - 3 else entries[i]
                    c.put(b.x0 + 2, y, txt, mix(gold, bright, 0.5) if new else mix(gold, soft, 0.35), new)
            return
        c.put(b.x0 + 1, inner_y(b, 0), f"v{v}", col, True)
        if jump > 0:
            c.put(b.x0 + 5, inner_y(b, 0), "v%d → v%d" % (R["v"][0], R["v"][1]), mix(gold, bright, 0.7), True)
        shown_max = int(self.get("show", 4))
        for i in range(min(shown_max, n_adopted, len(entries))):
            sym, cue, les = entries[i]
            new = i >= prev_n and jump > 0
            c1 = mix(gold, bright, 0.5) if new else mix(gold, soft, 0.35)
            l1, l2 = f"{sym} {cue}", f"→ {les}"
            c.fit(l2, b.w - 2, f"{b.key}.entry{i}")
            c.put(b.x0 + 1, inner_y(b, 1 + i * 2), l1, c1, new)
            c.put(b.x0 + 1, inner_y(b, 2 + i * 2), l2, mix(gold, soft, 0.2), new)
        if n_adopted > shown_max:
            c.put(b.x0 + 1, inner_y(b, 1 + shown_max * 2), f"+{n_adopted - shown_max}", mix(gold, bright, 0.4), True)


# ------------------------------------------------------------------ core readouts
@component("kv")
class KV(Component):
    """Pieces of text on one row: ``parts: [{text, color, bold, x, show}]`` (``x`` relative to the box).

    A part whose ``show`` binding is false is left out, so a value the project does not give leaves no label behind.
    """

    def draw(self, c, b, t, S):
        y = inner_y(b, int(self.get("row", 0)))
        x = b.x0 + int(self.get("x", 2))
        for part in self.spec["parts"]:
            if not S.value(part.get("show", True), t):
                continue
            if "x" in part:
                x = b.x0 + int(part["x"])
            text = S.text(part["text"], t)
            x = c.put(x, y, text, S.color(part.get("color", "soft")), bool(part.get("bold", False)))
            x += int(part.get("gap", 0))
        if x > b.x1:
            c.fit("x" * (x - b.x0 - 1), b.w - 2, f"{b.key}.row{self.get('row', 0)}")


@component("meter")
class Meter(Component):
    """A bar bound to a live value (``value: "{tick.conf}"``) with threshold tick and readout.

    Colors switch between ``ok_color`` and ``low_color`` at ``threshold``.
    """

    def draw(self, c, b, t, S):
        val = float(S.value(self.spec["value"], t))
        th = float(S.value(self.spec["threshold"], t))
        ok = val >= th
        col = S.color(self.get("ok_color", "go") if ok else self.get("low_color", "fb"))
        y = inner_y(b, int(self.get("row", 0)))
        x = b.x0 + int(self.get("x", 2))
        gray = S.palette["gray"]
        label = S.text(self.get("label", ""), t)
        if label:
            c.put(x, y, label, S.color(self.get("label_color", "gray")))
            x += tw(label) + int(self.get("label_gap", 1))
        bw = int(self.get("width")) if self.get("width") else b.w - 2 - (x - b.x0 - 2) - 2 - int(self.get("reserve", 6))
        min_bar = int(self.get("min_bar", 6))
        if bw < min_bar:
            # The label leaves too little room for the bar.
            c.fit(label + " " * (min_bar + 1), len(label) + 1 + bw if label else bw, f"{b.key}.meter")
        bar(c, S, x, y, bw, val, col, tick=th, head=False)
        c.put(x + bw + 1, y, S.swap(f"{val:.2f}"), col, True)
        chk = self.get("check")
        if chk:
            c.put(x + bw + int(chk.get("x", 7)), y, S.text(chk["ok"] if ok else chk["low"], t), col, True)
        del gray


@component("ports")
class Ports(Component):
    """A ripple tagline, a rule, and ``◆ name value`` items that light while their phase runs.

    Outside the rounds (opening and closing) the values come from the snapshot time.
    """

    def draw(self, c, b, t, S):
        tl = S.tl
        tc = tl.TS if (t < tl.intro or t >= tl.FADE_S) else t
        ri = tl.round_at(tc)
        col = b.color
        bright = S.palette["bright"]
        inner = b.w - 2
        cx = (b.x0 + b.x1) // 2
        ages = [t - s_ for s_ in S.ripples if 0 <= t - s_ < 0.7]

        def ripple(x, base):
            amount = 0.0
            for a in ages:
                amount = max(amount, math.exp(-((abs(x - cx) - a * 70) / 6.0) ** 2))
            return mix(base, bright, amount)

        tag = S.text(self.spec["tagline"], t)
        c.fit(tag, inner, f"{b.key}.tagline")
        x = cx - tw(tag) // 2
        for ch in tag:
            c.put(x, inner_y(b, 0), ch, ripple(x, mix(col, bright, 0.25)), True)
            x += cw(ch)
        for xx in range(b.x0 + 1, b.x1):
            c.cells[inner_y(b, 1)][xx] = ["┈", ripple(xx, mix(BG, col, 0.55)), False]
        d = tl.PH[ri]
        for k, it in enumerate(self.spec["items"]):
            px, row = b.x0 + int(it["x"]), int(it["row"])
            s, e = d[it["phase"]]
            live = s <= t < e + 0.4 or (t < tl.intro and 0.16 * k <= t < 0.16 * k + 0.9)
            val = float(S.value(it["value"], tc, ri))
            name = S.text(it["name"], t)
            txt = f"{name} {val:.2f}" if tc >= s else name
            c.put(px, inner_y(b, row), "◆", bright if live else col, True)
            c.put(px + 2, inner_y(b, row), txt, bright if live else mix(col, BG, 0.2), live)
            c.fit(txt, int(self.get("item_w", 16)), f"{b.key}.port{k}")


@component("slots")
class Slots(Component):
    """``[name vN]`` chips that flash when a round wins, the learned line, and a beam from below."""

    def draw(self, c, b, t, S):
        tl = S.tl
        names = S.value(self.spec["names"], t)
        vers = [1] * len(names)
        hit, flash, learn, beam, lt = None, 0.0, "", None, 0.0
        sp = self.spec
        for ri, R in enumerate(S.rounds):
            if R.get("win") is None:
                continue
            s_, e_ = tl.PH[ri][sp["phase"]]
            ht = s_ + 0.4 * (e_ - s_) + 0.5
            if t >= ht:
                vers[R["slot"]] = 2
                learn, lt = R["learn"], ht
                if t - ht < 1.0:
                    hit, flash = R["slot"], 1 - (t - ht) / 1.0
            elif t >= ht - 0.3:
                beam = (R["slot"], (t - (ht - 0.3)) / 0.3)
        if t >= tl.FADE_S:
            vers, hit, learn, beam = [1] * len(names), None, "", None
        col, bright, gold, soft = b.color, S.palette["bright"], S.palette["gold"], S.palette["soft"]
        x0 = b.x0 + 2
        xs = [x0 + int(o) for o in sp.get("offsets", [0, 13, 25])]
        row = int(sp.get("row", 3))
        for i, nm in enumerate(names):
            # At rest each chip keeps two cells before the next one and one before the border.
            room = (xs[i + 1] - xs[i] - 2) if i + 1 < len(xs) else (b.x1 - 1 - xs[i])
            c.fit(f"[{nm} v{max(vers)}]", room, "slots")
            f = flash if hit == i else 0.0
            colr = mix(mix(col, BG, 0.2), bright, 0.9 * f) if f > 0 else mix(col, soft, 0.35)
            vtxt = f"v{vers[i]}" if f <= 0 else f"v{vers[i] - 1}→{vers[i]}"
            c.put(xs[i], inner_y(b, row), f"[{nm} {vtxt}]", colr, f > 0.2 or i == hit)
        if learn:
            c.put(b.x1 - 2 - tw(learn), inner_y(b, row + 1), typed(learn, lt, 60, t), mix(gold, bright, 0.6 * flash), hit is not None)
        if beam is not None:
            slot, u = beam
            cx = xs[slot] + 6
            by = b.y1
            src = int(sp.get("beam_from", 41))
            glow_ = mix(gold, bright, 0.7)
            if u < 0.6:
                xa = int(src - (src - cx) * (u / 0.6))
                for x in range(xa, src + 1):
                    c.cells[by][x] = ["━", glow_, True]
            else:
                for x in range(cx, src + 1):
                    c.cells[by][x] = ["━", glow_, True]
                c.cells[inner_y(b, row + 1)][cx] = ["┃", glow_, True]


@component("buttons")
class Buttons(Component):
    """``[ label ]`` buttons; the current tick's button is highlighted."""

    def draw(self, c, b, t, S):
        st = S.ticker.step(t)
        labels = S.value(self.spec["labels"], t)
        col, bright = b.color, S.palette["bright"]
        acc = S.color(self.get("accent", "jev"))
        dimc = S.palette["dim"]
        if self.get("bar"):
            c.put(b.x0 + 2, inner_y(b, 0), self.spec["bar"], mix(BG, dimc, 0.7))
        for i, lab in enumerate(labels):
            y = inner_y(b, int(self.get("row", 1)) + i)
            hit = i == st["btn"]
            text = f"[ {lab} ]"
            c.fit(text, b.w - 2, f"{b.key}.button{i}")
            x = b.x0 + 1 + (b.w - 2 - tw(text)) // 2
            flash = max(0.0, 1 - st["u"] * 1.6)
            c.put(x, y, text, mix(col, bright, 0.6 + 0.4 * flash) if hit else mix(BG, col, 0.55), hit)
            if hit:
                c.put(x, y, "[", mix(acc, bright, flash), True)
                c.put(x + tw(text) - 1, y, "]", mix(acc, bright, flash), True)


# ------------------------------------------------------------------ overlays
@component("status")
class Status(Component):
    """Centered status line. ``style: brackets`` draws ``key [value]``; ``plain`` draws ``key value``.

    Values come from bindings; ``after: {phase, at}`` shows ``--`` before that point.
    """

    def draw(self, c, b, t, S):
        tl = S.tl
        a, sa = tl.alpha_content(t), tl.alpha_snap(t)
        alpha = max(a, sa)
        if alpha <= 0:
            return
        tc = t if a >= sa else tl.TS
        ri = tl.round_at(tc)
        items = []
        for it in self.spec["items"]:
            # ``live: true`` reads the value at real time even while the snapshot shows.
            v = S.text(it.get("value", ""), t if it.get("live") else tc)
            if it.get("swap"):
                v = S.swap(v)
            af = it.get("after")
            if af:
                s, e = tl.PH[ri][af["phase"]]
                if tc < s + float(af.get("at", 0)) * (e - s):
                    v = "--"
            key = S.text(it["key"], tc)
            if it.get("fill"):
                # Placeholders in a user's key text, such as "Iter {n}".
                key = key.format(**{k: S.text(x, tc) for k, x in it["fill"].items()})
            items.append((key, v, it))
        dimc, gold, soft, gray = S.palette["dim"], S.palette["gold"], S.palette["soft"], S.palette["gray"]
        y = int(self.spec["row"])
        gap = int(self.get("gap", 3))
        if self.get("style", "brackets") == "brackets":
            measure = tw if self.get("cjk_width") else len
            total = sum(measure(k) + 3 + measure(v) + 1 for k, v, _ in items) + gap * (len(items) - 1)
            c.fit((" " * gap).join(f"{k} [{v}]" for k, v, _ in items), S.cols - 4, "status")
            x = (S.cols - total) // 2
            for k, v, it in items:
                x = c.put(x, y, k + " [", mix(BG, dimc, alpha))
                vc = S.color(it["color"]) if it.get("color") else (gold if it.get("accent") else (soft if v != "--" else gray))
                x = c.put(x, y, v, mix(BG, vc, alpha), v != "--" or not self.get("dash_dim", True))
                x = c.put(x, y, "]", mix(BG, dimc, alpha)) + gap
            return
        total = sum(tw(k) + (1 + len(v) if v else 0) for k, v, _ in items) + gap * (len(items) - 1)
        c.fit((" " * gap).join(k + (" " + v if v else "") for k, v, _ in items), S.cols - 4, "status")
        x = (S.cols - total) // 2
        for k, v, it in items:
            x = c.put(x, y, k, mix(BG, dimc, alpha))
            if v:
                x = c.put(x + 1, y, v, mix(BG, gold if it.get("accent") else soft, alpha), True)
            x += gap


@component("divider")
class Divider(Component):
    """Section divider. ``style: rule`` is a dotted gold rule with a pulsing label;
    ``style: rainbow`` writes spaced labels in flowing rainbow colors."""

    def draw(self, c, b, t, S):
        import colorsys
        if self.get("style", "rule") == "rule":
            y = int(self.spec["row"])
            txt = " " + S.text(self.spec["text"], t) + " "
            x0 = (S.cols - tw(txt)) // 2
            pulse = 0.5 + 0.5 * math.sin(t * 2.0)
            col = S.color(self.get("color", "gold"))
            m = int(self.get("margin", 2))
            c.fit(txt, S.cols - 2 * m, "divider")
            for x in range(m, S.cols - m):
                if (x, y) in S.WCELLS:
                    continue
                c.cells[y][x] = ["┈", mix(BG, col, 0.35), False]
            c.put(x0, y, txt, mix(col, S.palette["bright"], 0.25 + 0.2 * pulse), True)
            return
        hv = S.hue_speed()
        cxm = int(self.get("center", S.cols // 2))
        for item in self.spec["labels"]:
            txt, yy = S.text(item["text"], t), int(item["row"])
            n = tw(txt)
            x0 = cxm - n // 2
            # The label sits in front of wires that cross its row, so no border piece shows between letters.
            for k in range(-1, n + 1):
                c.cells[yy][x0 + k] = [" ", S.palette["soft"], False]
            x = x0
            for k, ch in enumerate(txt):
                if ch != " ":
                    hue = (k / len(txt) * 0.85 - t * hv) % 1.0
                    r, g, bl = colorsys.hsv_to_rgb(hue, 0.72, 1.0)
                    c.put(x, yy, ch, (int(r * 255), int(g * 255), int(bl * 255)), True)
                x += cw(ch)


@component("label")
class Label(Component):
    """Free text at a cell: ``{x, y, text, color}``."""

    def draw(self, c, b, t, S):
        text = S.text(self.spec["text"], t)
        if self.get("max"):
            c.fit(text, int(self.spec["max"]), "label")
        c.put(int(self.spec["x"]), int(self.spec["y"]), text, S.color(self.get("color", "soft")), bool(self.get("bold", False)))


# ------------------------------------------------------------------ photo frame
@component("viewfinder")
class Viewfinder(Component):
    """Corner marks around the photo and a strip under it: recording dot, timecode,
    image quality (from the photo layer) and frame rate. Also tells the frame which
    photo to show (``c.img``)."""

    def draw(self, c, b, t, S):
        ph = S.photos
        if ph is not None:
            c.img = ph.current(t)
        ok = ph.confident(t) if ph is not None else True
        red, soft = S.palette["red"], S.palette["soft"]
        x0, x1 = b.x0 + 1, b.x1 - 1
        bot = inner_y(b, int(self.get("strip_row", 13)))
        on = int(t * 2) % 2 == 0
        good = S.text(self.get("good", "◑ lifted"), t)
        poor = S.text(self.get("poor", "◐ dark_scene"), t)
        qual = (good, S.color(self.get("good_color", "go"))) if ok else (poor, S.color(self.get("poor_color", "fb")))
        c.put(x0 + 1, bot, "●", red if on else mix(BG, red, 0.35), True)
        c.put(x0 + 3, bot, "REC", mix(BG, soft, 0.8))
        if ph is None or not ph.comparing(t):
            c.put(x0 + 22, bot, qual[0], mix(BG, qual[1], 0.9), True)
            c.fit(qual[0], b.w - 2 - 22 - 8, f"{b.key}.quality")
        ya, yb = inner_y(b, 0), inner_y(b, int(self.get("strip_row", 13)) - 1)
        for (x, y, ch) in ((x0, ya, "┌"), (x1, ya, "┐"), (x0, yb, "└"), (x1, yb, "┘")):
            c.put(x, y, ch, mix(BG, soft, 0.85), True)
