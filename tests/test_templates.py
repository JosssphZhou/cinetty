"""End-to-end checks of the template path and the safety of user text.

Run with: make test
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cinetty import template as T  # noqa: E402
from cinetty.engine import build  # noqa: E402


def check(project):
    r = subprocess.run([sys.executable, "-m", "cinetty", "check", str(project), "--format", "json"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


def variant(src, change):
    """A copy of an example project, changed, written next to the original so relative paths still work."""
    data = yaml.safe_load(Path(src).read_text(encoding="utf-8"))
    change(data)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=Path(src).parent, delete=False, encoding="utf-8")
    yaml.safe_dump(data, tmp, allow_unicode=True)
    tmp.close()
    return Path(tmp.name)


class Examples(unittest.TestCase):
    def test_every_example_passes_check(self):
        for p in sorted(ROOT.glob("examples/*/project*.yaml")):
            with self.subTest(project=p.name, template=p.parent.name):
                code, out = check(p)
                self.assertEqual(code, 0, out["problems"][:3])

    def test_every_template_has_an_example_and_lists(self):
        r = subprocess.run([sys.executable, "-m", "cinetty", "templates", "--format", "json"], cwd=ROOT,
                           capture_output=True, text=True, check=True)
        listed = json.loads(r.stdout)
        self.assertEqual(len(listed), 6)
        for t in listed:
            for path in t["example"].values():
                self.assertTrue((ROOT / path).is_file(), path)


class Problems(unittest.TestCase):
    def test_too_long_text_is_reported_with_its_path(self):
        src = ROOT / "examples/circuit-flow/project.en.yaml"
        p = variant(src, lambda d: d["fields"]["modules"]["B"].__setitem__("name", "X" * 40))
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertNotEqual(code, 0)
        hit = [x for x in out["problems"] if x["path"] == "fields.modules.B.name"]
        self.assertTrue(hit, out["problems"])
        self.assertEqual(hit[0]["code"], "too_long")
        self.assertEqual(hit[0]["over"], 6)

    def test_cjk_counts_two_cells(self):
        src = ROOT / "examples/circuit-flow/project.zh.yaml"
        p = variant(src, lambda d: d["fields"]["modules"]["A"].__setitem__("name", "充" * 13))   # 26 cells > 24
        try:
            code, out = check(p)
        finally:
            p.unlink()
        hit = [x for x in out["problems"] if x["path"] == "fields.modules.A.name"]
        self.assertTrue(hit and hit[0]["actual"] == 26, out["problems"])

    def test_events_out_of_order_and_unknown_names(self):
        src = ROOT / "examples/phone-use/project.en.yaml"

        def change(d):
            d["events"][2]["t"] = 0.5
            d["events"][0]["to"] = "tablet"
        p = variant(src, change)
        try:
            code, out = check(p)
        finally:
            p.unlink()
        codes = {(x["code"], x["path"]) for x in out["problems"]}
        self.assertIn(("time_goes_back", "events[2].t"), codes)
        self.assertIn(("unknown_ref", "events[0].to"), codes)

    def test_unknown_field_is_an_error(self):
        src = ROOT / "examples/agent-workflow/project.en.yaml"
        p = variant(src, lambda d: d["fields"].__setitem__("subtitle", "extra"))
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertIn("unknown_field", {x["code"] for x in out["problems"]})


class Safety(unittest.TestCase):
    def test_user_text_is_never_evaluated(self):
        src = ROOT / "examples/harness-landscape/project.en.yaml"
        payload = "{__import__('os').getpid()}"
        p = variant(src, lambda d: d["fields"].__setitem__("frame_title", payload))
        try:
            spec = T.load(str(p))
            S = build(spec)
            text = "\n".join(S.render_frame(t).text() for t in (2.0, 10.0))
        finally:
            p.unlink()
        self.assertIn("__import__", text)


if __name__ == "__main__":
    unittest.main()
