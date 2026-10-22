"""Regression check for review F3: the workflow board took exactly three workers.

With one or two workers the check must pass, and no frame may show an empty card slot,
an arrow into it or a line running to it.
"""
import unittest

from helpers import ROOT, check, variant

from cinetty import template as T
from cinetty.engine import build

SRC = ROOT / "examples/agent-workflow/project.en.yaml"


def with_workers(n):
    def change(d):
        d["fields"]["workers"] = d["fields"]["workers"][:n]
        keep = {1: {0: 0, 1: 0, 2: 0}, 2: {0: 0, 1: 1, 2: 1}, 3: {0: 0, 1: 1, 2: 2}}[n]
        for e in d["events"]:
            for k in ("card", "hold_card"):
                if k in e:
                    e[k] = keep[e[k]]
    return change


class Workers(unittest.TestCase):
    def test_one_and_two_workers_pass_and_leave_no_empty_slots(self):
        for n in (1, 2):
            with self.subTest(workers=n):
                p = variant(SRC, with_workers(n))
                try:
                    code, out = check(p)
                    self.assertEqual(code, 0, out["problems"][:3])
                    S = build(T.load(str(p)))
                    for t in (0.5, 3.0, 6.0, 9.0, 12.0, 14.5):
                        rows = S.render_frame(t).text().splitlines()
                        self.assertEqual(rows[23].count("┌"), n, f"t={t}: {rows[23]}")      # card tops
                        self.assertEqual(rows[22].count("▼"), n, f"t={t}: {rows[22]}")      # arrows into cards
                        bus_in, bus_out = rows[21], rows[31]
                        if n == 1:
                            self.assertNotIn("┌", bus_in)
                            self.assertNotIn("└", bus_out)
                        else:
                            self.assertEqual(bus_in.count("┌") + bus_in.count("┐"), 2, bus_in)
                finally:
                    p.unlink()

    def test_a_card_number_beyond_the_workers_is_an_error(self):
        def change(d):
            with_workers(2)(d)
            e = next(e for e in d["events"] if "card" in e)
            e["card"] = 2
        p = variant(SRC, change)
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertIn("unknown_ref", {x["code"] for x in out["problems"]})


if __name__ == "__main__":
    unittest.main()
