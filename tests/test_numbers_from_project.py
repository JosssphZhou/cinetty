"""The live loop of photo-loop shows only numbers that the project gives.

Every confidence on the status line and in the JEV box, the fallback count and what it
is counted out of, and the threshold are filled with odd values here; any number the
engine made up itself (a hash, a constant) would not be one of them.

Run with: make test
"""
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cinetty import template as T  # noqa: E402
from cinetty.engine import build  # noqa: E402
from helpers import variant  # noqa: E402

GATE = 0.613
STEPS = [[0.137, 0.862, 0.705, 0.413, 0.958], [0.291, 0.884], [0.777, 0.512, 0.649]]
INITIAL = 3


def odd_values(d):
    f = d["fields"]
    f["core"]["gate"] = GATE
    f["store"]["initial"] = INITIAL
    for r, conf in zip(f["rounds"], STEPS):
        r["confidences"] = conf
        r["fallbacks"] = sum(x < GATE for x in conf)


class LiveLoopNumbers(unittest.TestCase):
    def test_status_line_and_jev_box_read_the_project(self):
        p = variant(ROOT / "examples/harness-photo/project.en.yaml", odd_values)
        try:
            S = build(T.load(str(p)))
            frames = [S.render_frame(k / 10).text() for k in range(int(S.tl.TOTAL * 10))]
            before_adopting = S.render_frame(S.tl.PH[0]["store"][0] - 0.05).text()
        finally:
            p.unlink()
        allowed = {f"{x:.2f}" for r in STEPS for x in r}
        by_text = {f"{x:.2f}": x for r in STEPS for x in r}
        counts = {f"{sum(x < GATE for x in r)}/{len(r)}" for r in STEPS}
        seen = set()
        for text in frames:
            for m in re.finditer(r"conf\D{0,30}?(\d\.\d\d)", text):
                self.assertIn(m.group(1), allowed)
                seen.add(m.group(1))
            for m in re.finditer(r"fallback \[(\d+/\d+)\]", text):
                self.assertIn(m.group(1), counts)
            for m in re.finditer(r"conf\D{0,30}?(\d\.\d\d)\s+([✓↻]) [≥<] (\d\.\d+)", text):
                self.assertEqual(m.group(3), f"{GATE:.2f}")
                self.assertEqual(m.group(2) == "✓", float(by_text[m.group(1)]) >= GATE, m.group(0))
        self.assertGreater(len(seen), 3, "the live loop should show several of the project's confidences")
        self.assertEqual(len(re.findall(r"│→ ", before_adopting)), INITIAL, "the store starts with the project's lessons")
        self.assertNotIn("bbox", "".join(frames), "no box is shown before the photos are prepared")
        self.assertNotIn("0,0,0,0", "".join(frames))


class PhotosReady(unittest.TestCase):
    """With prepared photos the box of the main object is shown; the other tests run without them."""

    def test_status_shows_the_box_of_the_prepared_photo(self):
        import json
        p = variant(ROOT / "examples/harness-photo/project.en.yaml", odd_values)
        key = "test-ready-" + p.stem
        out = ROOT / "build" / "photos"
        pointer = out / (yaml.safe_load(p.read_text(encoding="utf-8"))["name"] + ".json")
        try:
            ids = [ph["id"] for ph in yaml.safe_load(p.read_text(encoding="utf-8"))["fields"]["photos"]] + ["compare"]
            (out / key).mkdir(parents=True)
            (out / key / "photos.json").write_text(json.dumps(
                {"photos": {i: {"name": "car", "box": [401, 17, 799, 233], "objects": 1} for i in ids}, "fx": {}}))
            pointer.write_text(json.dumps({"dir": key}))
            S = build(T.load(str(p)))
            text = S.render_frame(S.tl.PH[0]["store"][0] - 0.05).text()
        finally:
            p.unlink()
            pointer.unlink(missing_ok=True)
            import shutil
            shutil.rmtree(out / key, ignore_errors=True)
        self.assertIn("[401,17,799,233]", text)


def full_scores(d):
    """odd_values plus a round where a candidate and the baseline both score 100%."""
    odd_values(d)
    r = d["fields"]["rounds"][2]
    r["baseline"] = 1.0
    r["candidate_scores"] = [1.0, 0.88, 0.93]
    r.pop("winner", None), r.pop("learned_slot", None), r.pop("learned", None)
    r["version"] = [r["version"][0], r["version"][0]]


class FullScoresFitTheComposeBox(unittest.TestCase):
    """A real run scored 100%; the Compose lines became 14 and 15 cells in a 13-cell box and
    make check reported too_long_on_screen."""

    def test_check_passes_and_shows_the_scores(self):
        from helpers import check
        p = variant(ROOT / "examples/harness-photo/project.en.yaml", full_scores)
        try:
            code, out = check(p)
            S = build(T.load(str(p)))
            text = "\n".join(S.render_frame(k / 10).text() for k in range(int(S.tl.TOTAL * 10)))
        finally:
            p.unlink()
        self.assertEqual(code, 0, out["problems"])
        self.assertIn("H1 100≤v", text)
        self.assertRegex(text, r"H3 93≤v\d+ 100")


if __name__ == "__main__":
    unittest.main()
