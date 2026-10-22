"""Text we ship on screen does not use a spaced middle dot or bullet as a separator."""
import unittest

from helpers import ROOT, check, variant

SEPARATORS = (" · ", " • ")


class SpacedDots(unittest.TestCase):
    def test_examples_templates_and_engine_have_no_spaced_dots(self):
        hits = []
        for pattern in ("examples/**/*.yaml", "templates/**/*.yaml", "cinetty/*.py"):
            for p in sorted(ROOT.glob(pattern)):
                for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if any(s in line for s in SEPARATORS):
                        hits.append(f"{p.relative_to(ROOT)}:{n}")
        self.assertEqual(hits, [])

    def test_check_rejects_a_spaced_dot_in_a_field(self):
        p = variant(ROOT / "examples/circuit-flow/project.zh.yaml",
                    lambda d: d["fields"].update(title="\u5de5\u5355\u5206\u6d3e \u00b7 \u6d41\u7a0b\u793a\u610f"))
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertNotEqual(code, 0)
        hit = [q for q in out["problems"] if q["path"] == "fields.title"]
        self.assertEqual([q["code"] for q in hit], ["spaced_dot"])
        self.assertIn("colon", hit[0]["hint"])


class SymbolsWithAnUnsureWidth(unittest.TestCase):
    """Ghostty draws a trigram such as \u2630 two cells wide while the layout counted one, so a
    blind-test project with \u2630 as a box icon pushed the rest of that row one cell to the right."""

    def test_check_rejects_a_trigram_icon(self):
        p = variant(ROOT / "examples/harness-photo/project.zh.yaml",
                    lambda d: d["fields"]["patch_kinds"][0].update(icon="\u2630"))
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertNotEqual(code, 0)
        hit = [q for q in out["problems"] if q["code"] == "unsure_width"]
        self.assertEqual([q["path"] for q in hit], ["fields.patch_kinds[0].icon"])
        self.assertIn("\u2630", hit[0]["hint"])

    def test_examples_use_none(self):
        from cinetty.template import unsure_width
        bad = [str(f.relative_to(ROOT)) for f in ROOT.glob("examples/*/*.yaml") if unsure_width(f.read_text())]
        self.assertEqual(bad, [])


class HeadlineAroundTheDivider(unittest.TestCase):
    """The comparison slide's divider runs down the middle of the headline. The example's
    "v1 → v3" puts the arrow there; a blind-test headline without an arrow had the divider
    cut through its middle characters."""

    def test_check_asks_for_an_arrow(self):
        p = variant(ROOT / "examples/harness-photo/project.zh.yaml",
                    lambda d: d["fields"]["compare"].update(headline="质检流程改进示意"))
        try:
            code, out = check(p)
        finally:
            p.unlink()
        self.assertNotEqual(code, 0)
        hit = [q for q in out["problems"] if q["code"] == "no_split"]
        self.assertEqual([q["path"] for q in hit], ["fields.compare.headline"])
        self.assertIn("→", hit[0]["hint"])

    def test_arrow_sits_on_the_divider_when_the_sides_differ(self):
        from cinetty.photos import bold, headline_x
        W = 1824
        for text in ("v1 → v3", "初版 → 改进版", "v1 → v12-final"):
            font = bold(104, text)
            before = text.partition(" → ")[0]
            mid = headline_x(font, text, W) + font.getlength(before + " ") + font.getlength("→") / 2
            self.assertLessEqual(abs(mid - W / 2), 1, text)

    def test_even_sides_keep_the_original_position(self):
        from cinetty.photos import bold, headline_x
        font = bold(104, "v1 → v3")
        self.assertEqual(headline_x(font, "v1 → v3", 1824), (1824 - int(font.getlength("v1 → v3"))) // 2)


if __name__ == "__main__":
    unittest.main()
