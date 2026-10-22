"""The small "made with cinetty" credit at the bottom of every template."""
import unittest

from helpers import ROOT, check, run, variant

CREDIT = "made with cinetty"
# Template id: the folder of its example project.
EXAMPLES = {"pipeline": "agent-workflow", "circuit-flow": "circuit-flow", "loop-landscape": "harness-landscape",
            "photo-loop": "harness-photo", "loop-portrait": "harness-portrait", "screen-flow": "phone-use"}
VIDEO_TEMPLATES = list(EXAMPLES)


class Credit(unittest.TestCase):
    def test_every_video_example_shows_the_credit(self):
        for t in VIDEO_TEMPLATES:
            with self.subTest(template=t):
                r = run("once", ROOT / f"examples/{EXAMPLES[t]}/project.en.yaml", "--at", "12", "--text")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(CREDIT, r.stdout)

    def test_credit_stays_for_the_whole_animation(self):
        # The circuit status line grows as values change; the credit used to vanish from 30 s on.
        for t in VIDEO_TEMPLATES:
            for lang in ("en", "zh"):
                src = ROOT / f"examples/{EXAMPLES[t]}/project.{lang}.yaml"
                if not src.exists():
                    continue
                dur = {"circuit-flow": 44, "pipeline": 15, "screen-flow": 26}.get(t, 30)
                for at in range(1, dur, 4):
                    with self.subTest(template=t, lang=lang, at=at):
                        r = run("once", src, "--at", str(at), "--text")
                        self.assertIn(CREDIT, r.stdout)

    def test_credit_false_turns_it_off_and_still_passes_check(self):
        p = variant(ROOT / "examples/circuit-flow/project.en.yaml", lambda d: d.__setitem__("credit", False))
        try:
            code, out = check(p)
            r = run("once", p, "--at", "12", "--text")
        finally:
            p.unlink()
        self.assertEqual(code, 0, out["problems"])
        self.assertNotIn(CREDIT, r.stdout)


if __name__ == "__main__":
    unittest.main()
