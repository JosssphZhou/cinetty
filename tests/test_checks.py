"""Regression checks for problems the check used to let through (review of 228efec, F1, F2, F5).

Each test writes a changed copy of an example and expects make check to fail with a field path.
"""
import unittest

from helpers import ROOT, check, codes, variant

EVENT_EXAMPLES = {
    "pipeline": ROOT / "examples/agent-workflow/project.en.yaml",
    "screen-flow": ROOT / "examples/phone-use/project.en.yaml",
    "circuit-flow": ROOT / "examples/circuit-flow/project.en.yaml",
}
# A text-bearing event in each example, and the key that holds its text.
TEXT_EVENT = {"pipeline": "text", "screen-flow": "text", "circuit-flow": "text"}
DURATION = {"pipeline": 15, "screen-flow": 26, "circuit-flow": 44}


def first_with(events, key):
    return next(i for i, e in enumerate(events) if isinstance(e, dict) and key in e)


class CounterOverlap(unittest.TestCase):
    """F1: a long counter label used to be overwritten by a large counter, and the check passed."""

    def test_counter_label_and_number_must_not_overlap(self):
        def change(d):
            d["fields"]["router"]["counter_label"] = "COUNTERX"
            d["fields"]["router"]["counter_start"] = 9999999
        p = variant(EVENT_EXAMPLES["pipeline"], change)
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertNotEqual(code, 0)
        self.assertIn(("too_long_on_screen", "fields.router.counter_label"), codes(out))


class LineBreaksInEvents(unittest.TestCase):
    """F1: a line break in an event text used to hide the second line silently."""

    def test_line_break_in_event_text_is_reported(self):
        for t, src in EVENT_EXAMPLES.items():
            with self.subTest(template=t):
                key = TEXT_EVENT[t]
                holder = {}

                def change(d):
                    i = first_with(d["events"], key)
                    holder["i"] = i
                    d["events"][i][key] = "visible\nhidden"
                p = variant(src, change)
                try:
                    code, out = check(p)
                finally:
                    p.unlink()
                self.assertNotEqual(code, 0)
                self.assertIn(("bad_char", f"events[{holder['i']}].{key}"), codes(out))

    def test_unicode_line_separator_in_a_field_is_reported(self):
        p = variant(EVENT_EXAMPLES["circuit-flow"], lambda d: d["fields"].__setitem__("title", "A B"))
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertIn(("bad_char", "fields.title"), codes(out))


class EventsAfterTheEnd(unittest.TestCase):
    """F2: an event later than the template's fixed length used to pass and never show."""

    def test_event_after_the_end_is_reported(self):
        for t, src in EVENT_EXAMPLES.items():
            with self.subTest(template=t):
                holder = {}

                def change(d):
                    last = dict(d["events"][-1])
                    last["t"] = DURATION[t] + 4
                    d["events"].append(last)
                    holder["i"] = len(d["events"]) - 1
                p = variant(src, change)
                try:
                    code, out = check(p)
                finally:
                    p.unlink()
                self.assertNotEqual(code, 0)
                hit = [x for x in out["problems"] if x["code"] == "after_end"]
                self.assertTrue(hit, out["problems"])
                self.assertEqual(hit[0]["path"], f"events[{holder['i']}].t")
                self.assertEqual(hit[0]["limit"], DURATION[t])

    def test_final_phone_step_must_arrive_before_the_end(self):
        def change(d):
            done = next(e for e in reversed(d["events"]) if e.get("type") == "done")
            d["events"] = [e for e in d["events"] if e is not done] + [dict(done, t=25.5, final=True)]
        p = variant(EVENT_EXAMPLES["screen-flow"], change)
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertIn("after_end", {x["code"] for x in out["problems"]}, out["problems"])


class UnknownBox(unittest.TestCase):
    """F5: a circuit event naming a box that does not exist used to crash with a KeyError."""

    def test_unknown_box_is_reported_as_json(self):
        p = variant(EVENT_EXAMPLES["circuit-flow"],
                    lambda d: d["events"].insert(0, {"t": 1, "type": "light", "box": "MISSING", "until": 5}))
        try:
            code, out = check(p)        # fails here if stdout is not JSON
        finally:
            p.unlink()
        self.assertNotEqual(code, 0)
        hit = [x for x in out["problems"] if x["path"] == "events[0].box"]
        self.assertTrue(hit and hit[0]["code"] == "unknown_ref", out["problems"])
        self.assertTrue(hit[0]["hint"])


if __name__ == "__main__":
    unittest.main()
