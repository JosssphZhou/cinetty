"""Every number on screen comes from the project file, in all seven templates.

For each template the numbers of an example are replaced by odd values (0.137, 0.862 and so on),
the animation is rendered, and every number on a settled frame has to be one of those values, a
count of things the screen shows (for example the lessons kept), or a time of day computed from the
project's clock. A number the engine made up itself (a hash, a random draw, a constant) is not on
that list, so the test fails when one comes back. Numbers that roll up to their value during a
phase are not read until the phase is over; the live loop of photo-loop and loop-portrait is
read on every frame.

Run with: make test
"""
import itertools
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cinetty import photos  # noqa: E402
from cinetty import template as T  # noqa: E402
from cinetty.engine import build  # noqa: E402
from helpers import check, codes, variant  # noqa: E402

NUMBER = re.compile(r"(?<![A-Za-z#_.\d])\d+(?:[.,]\d+)*")
CLOCK = re.compile(r"\d\d:\d\d:\d\d")


def odd_floats(node, gen):
    """Replace every float of a project by an odd value that has not been used yet."""
    if isinstance(node, dict):
        for k, v in list(node.items()):
            node[k] = gen() if isinstance(v, float) and k not in ("t", "until") else odd_floats(v, gen)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            node[i] = gen() if isinstance(v, float) else odd_floats(v, gen)
    return node


def odd_gen():
    """0.137, 0.186, 0.235 and so on: three decimals, no two equal, none close to a round number."""
    for n in itertools.count(1):
        yield round(0.101 + (n * 0.0371) % 0.85, 3)


def forms(x):
    """Every way a number can be written on the screen."""
    out = {str(x), str(int(x))}
    if isinstance(x, float):
        out |= {f"{x:.1f}", f"{x:.2f}", str(round(x * 100))}
    else:
        out.add(f"{x:,}")
    return out


def numbers_of(node):
    """Every number the project gives: its numeric values and the digits of its texts."""
    out = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in ("t", "until"):     # event times are not shown as numbers
                out |= numbers_of(v)
    elif isinstance(node, list):
        for v in node:
            out |= numbers_of(v)
    elif isinstance(node, bool) or node is None:
        pass
    elif isinstance(node, (int, float)):
        out |= forms(node)
    elif isinstance(node, str):
        out |= set(re.findall(r"\d+(?:[.,]\d+)*", node)) | set(re.findall(r"\d+", node))
    return out


def stray_numbers(text, allowed):
    """Numbers on a frame that are neither allowed nor a time of day."""
    text = CLOCK.sub("", text)
    return [m.group(0) for m in NUMBER.finditer(text) if m.group(0) not in allowed]


# ---------------------------------------------------------------- sampling
def settled_times(S):
    """Moments at which nothing is still counting up: the end of each round, the hold, the freeze."""
    if hasattr(S, "tl"):
        tl = S.tl
        ends = [max(v[1] for v in ph.values()) - 0.05 for ph in tl.PH]
        return ends + [tl.HOLD_S + 0.1, tl.FADE_S - 0.2]
    total = S.duration()
    events = S.events if hasattr(S, "events") else []
    times = {total - 0.2}
    for e in events:
        if isinstance(e, dict) and isinstance(e.get("t"), (int, float)):
            times.add(e["t"] + 2.0)
            if isinstance(e.get("until"), (int, float)):
                times.add(e["until"] - 0.1)
    return sorted(t for t in times if 0 < t < total)


def render(S, times):
    return [S.render_frame(t).text() for t in times]


def load(src, change):
    p = variant(ROOT / src, change)
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        return d, build(T.load(str(p)))
    finally:
        p.unlink()


# ---------------------------------------------------------------- per template
class SettledFrames(unittest.TestCase):
    """The numbers of every template, read on settled frames."""

    def check(self, src, change, extra=lambda d: set()):
        d, S = load(src, change)
        allowed = numbers_of(d) | extra(d)
        stray = {}
        for t, text in zip(settled_times(S), render(S, settled_times(S))):
            for tok in stray_numbers(text, allowed):
                stray.setdefault(tok, round(t, 1))
        self.assertEqual(stray, {}, f"{src}: numbers on screen that the project does not give (token: time)")
        return d, S

    def test_harness_landscape(self):
        def change(d):
            gen = odd_gen()
            odd_floats(d["fields"], lambda: next(gen))
            for i, r in enumerate(d["fields"]["rounds"]):
                r["speed"] = [1.3, 1.7, 2.9][i] + 0.07 * i
            d["fields"]["keep_at"] = KEEP_AT

        def extra(d):
            out = set()
            for r in d["fields"]["rounds"]:
                kept = sum(k["score"] >= KEEP_AT for k in r["kept"])
                out |= {str(kept), str(len(r["kept"]) - kept)}
            out |= {str(i) for i in range(1, len(d["fields"]["rounds"]) + 1)}
            return out

        for lang in ("en", "zh"):
            self.check(f"examples/harness-landscape/project.{lang}.yaml", change, extra)

    def test_harness_portrait(self):
        for lang in ("en", "zh"):
            self.check(f"examples/harness-portrait/project.{lang}.yaml", portrait_values, live_extra)

    def test_harness_photo(self):
        for lang in ("en", "zh"):
            self.check(f"examples/harness-photo/project.{lang}.yaml", photo_values, live_extra)

    def test_agent_workflow(self):
        def change(d):
            gen = odd_gen()
            f = d["fields"]
            odd_floats(f, lambda: next(gen))
            odd_floats(d["events"], lambda: next(gen))
            f["router"]["counter_start"] = 4271
            f["advisor"]["tokens_start"] = 733
            n = itertools.count(4283, 7)
            tk = itertools.count(811, 13)
            for e in d["events"]:
                if "forks" in e:
                    e["forks"] = next(n)
                if "tokens" in e:
                    e["tokens"] = next(tk)

        def extra(d):
            calls = sum(e["type"] == "advise" for e in d["events"])
            return {str(i) for i in range(calls + 1)}

        self.check("examples/agent-workflow/project.en.yaml", change, extra)

    def test_phone_use(self):
        def change(d):
            gen = odd_gen()
            odd_floats(d["fields"], lambda: next(gen))
            odd_floats(d["events"], lambda: next(gen))

        for lang in ("en", "zh"):
            self.check(f"examples/phone-use/project.{lang}.yaml", change)

    def test_circuit_flow(self):
        def change(d):
            gen = odd_gen()
            odd_floats(d["fields"], lambda: next(gen))
            if isinstance(d.get("events"), list):
                odd_floats(d["events"], lambda: next(gen))

        for lang in ("en", "zh"):
            self.check(f"examples/circuit-flow/project.{lang}.yaml", change)


KEEP_AT = 0.857


# loop-portrait and photo-loop ---------------------------------------
GATE = 0.613
STEPS = [[0.137, 0.862, 0.705, 0.413, 0.958], [0.291, 0.884], [0.777, 0.512, 0.649, 0.587]]
INITIAL = 3
BELOW = [sum(x < GATE for x in r) for r in STEPS]


def live_values(f, where):
    """Odd confidences for every live step, a gate nobody would pick, and three lessons to start from."""
    where["gate"] = GATE
    for r, conf in zip(f["rounds"], STEPS):
        r["confidences"] = conf
        r["fallbacks"] = sum(x < GATE for x in conf)
    f["store"]["initial"] = INITIAL


def portrait_values(d):
    gen = odd_gen()
    f = d["fields"]
    odd_floats(f, lambda: next(gen))
    live_values(f, f["live"])


def photo_values(d):
    gen = odd_gen()
    f = d["fields"]
    odd_floats(f, lambda: next(gen))
    live_values(f, f["core"])


def live_extra(d):
    return {str(n) for n in BELOW} | {str(len(r)) for r in STEPS} | {str(INITIAL)} | {"1", "2", "3"}


class LiveLoop(unittest.TestCase):
    """The decision box and the status line change with every step, so they are read on every frame."""

    def frames(self, src, change):
        p = variant(ROOT / src, change)
        try:
            S = build(T.load(str(p)))
            return S, [S.render_frame(k / 10).text() for k in range(int(S.tl.TOTAL * 10))]
        finally:
            p.unlink()

    def test_portrait_decides_by_the_confidences_and_the_gate_of_the_project(self):
        S, frames = self.frames("examples/harness-portrait/project.en.yaml", portrait_values)
        by_text = {f"{x:.2f}": x for r in STEPS for x in r}
        counts = {f"{n}/{len(r)}" for n, r in zip(BELOW, STEPS)}
        seen = set()
        for text in frames:
            for m in re.finditer(r"Confidence\D{0,30}?(\d\.\d\d)[^\n]*\n[^\n]*?(Above|Below)", text):
                self.assertIn(m.group(1), by_text)
                self.assertEqual(m.group(2) == "Above", by_text[m.group(1)] >= GATE, m.group(0))
                seen.add(m.group(1))
            for m in re.finditer(r"Fallbacks (\d+/\d+)", text):
                self.assertIn(m.group(1), counts)
        self.assertGreater(len(seen), 3, "the live loop should show several of the project's confidences")

    def test_portrait_starts_with_the_lessons_the_project_gives(self):
        _, S = load("examples/harness-portrait/project.en.yaml", portrait_values)
        text = S.render_frame(S.tl.PH[0]["store"][0] - 0.05).text()
        self.assertEqual(len(re.findall(r"▸ ", text)), INITIAL)


class KeepThreshold(unittest.TestCase):
    """Compose keeps the changes at or above the project's keep_at, and says how many."""

    def values(self, d):
        d["fields"]["keep_at"] = KEEP_AT

    def test_summary_counts_follow_keep_at(self):
        d, S = load("examples/harness-landscape/project.en.yaml", self.values)
        for ri, r in enumerate(d["fields"]["rounds"]):
            kept = sum(k["score"] >= KEEP_AT for k in r["kept"])
            text = S.render_frame(max(v[1] for v in S.tl.PH[ri].values()) - 0.05).text()
            self.assertIn(f"Keep {kept}, drop {len(r['kept']) - kept}", text)
        self.assertNotEqual(sum(k["score"] >= KEEP_AT for r in d["fields"]["rounds"] for k in r["kept"]),
                            sum(k["score"] >= 0.7 for r in d["fields"]["rounds"] for k in r["kept"]))

    def test_check_asks_for_keep_at(self):
        p = variant(ROOT / "examples/harness-landscape/project.en.yaml", lambda d: d["fields"].pop("keep_at"))
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertNotEqual(code, 0)
        self.assertIn(("missing", "fields.keep_at"), codes(out))
        self.assertIn("threshold your system uses", next(x["hint"] for x in out["problems"] if x["path"] == "fields.keep_at"))


class CountsAgreeWithTheirNumbers(unittest.TestCase):
    """fallbacks is how many confidences lie below the gate; a count out of step with them is reported."""

    def test_check_reports_a_wrong_fallback_count_and_says_the_right_one(self):
        for src, where in (("examples/harness-photo/project.en.yaml", "core"),
                           ("examples/harness-portrait/project.en.yaml", "live")):
            def change(d):
                d["fields"][where]["gate"] = 0.7
                d["fields"]["rounds"][0].update(confidences=[0.5, 0.9, 0.8], fallbacks=14)
            p = variant(ROOT / src, change)
            try:
                code, out = check(p)
            finally:
                p.unlink()
            self.assertNotEqual(code, 0)
            self.assertIn(("count_mismatch", "fields.rounds[0].fallbacks"), codes(out))
            hint = next(x["hint"] for x in out["problems"] if x["code"] == "count_mismatch")
            self.assertIn("write 1 here", hint)


class WhatTheProjectLeavesOut(unittest.TestCase):
    """A number the project does not give is not shown, and nothing stands in for it."""

    def test_a_box_without_confidences_has_no_number_in_its_label(self):
        self.assertEqual(photos.low_boxes({}, 5), (None, photos.LOW_BOXES))
        self.assertEqual(photos.low_boxes({"low_confidences": [0.2, 0.3]}, 5), ([0.2, 0.3], 2))
        self.assertEqual(photos.label_text("car", None), "car")
        self.assertEqual(photos.label_text("car", 0.137), "car 0.14")

    def test_a_round_without_speed_shows_dashes(self):
        def change(d):
            for r in d["fields"]["rounds"]:
                r.pop("speed", None)
        _, S = load("examples/harness-landscape/project.en.yaml", change)
        self.assertIn("speed [--]", S.render_frame(S.tl.HOLD_S + 0.1).text())


if __name__ == "__main__":
    unittest.main()
