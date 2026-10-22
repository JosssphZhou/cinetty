"""make play without a terminal (an agent's shell, a pipe) used to wait for a window size forever."""
import subprocess
import unittest

from helpers import ROOT


class PlayWithoutTerminal(unittest.TestCase):
    def test_play_stops_with_a_message(self):
        r = subprocess.run(["make", "play", "INPUT=examples/circuit-flow/project.en.yaml"], cwd=ROOT,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("make once", r.stderr)


if __name__ == "__main__":
    unittest.main()


class PhotoCaptionsInEveryScript(unittest.TestCase):
    """The comparison slide drew its captions and headline in Menlo, which has no Chinese glyphs, so
    a Chinese caption came out as a row of empty boxes on the photo."""

    def test_chinese_caption_has_glyphs(self):
        from cinetty.photos import bold, has_glyphs
        for text in ("初版：转人工复核", "改进版：输出判定", "商品照片质检"):
            self.assertTrue(has_glyphs(bold(46, text), text), text)

    def test_latin_caption_stays_monospace(self):
        from cinetty.photos import bold
        self.assertNotIn("Hiragino", bold(46, "v1 0.47 review").getname()[0])


class RowsFitTheTerminal(unittest.TestCase):
    """A Chinese title or rainbow label was laid out one cell per letter, so each wide letter made
    its row one cell longer than the screen; in Ghostty the row wrapped and wiped the start of the
    next row (the blind test's section title lost its first characters)."""

    def rows(self, src, change, step=0.25):
        from cinetty import template
        from cinetty.canvas import tw
        from cinetty.engine import build
        from helpers import variant
        p = variant(ROOT / src, change)
        try:
            sc = build(template.load(p))
        finally:
            p.unlink()
        bad = set()
        for k in range(int(sc.duration() / step)):
            f = sc.render_frame(k * step)
            bad |= {y for y, row in enumerate(f.cells) if tw("".join(c[0] for c in row)) != f.cols}
        return bad

    def test_chinese_title_and_rainbow_labels(self):
        def change(d):
            d["fields"]["title"] = "商品视觉质检"
            d["fields"]["sections"]["live_tag"] = "实 时 质 检"
            d["fields"]["sections"]["learning_tag"] = "持 续 改 进"
        self.assertEqual(self.rows("examples/harness-photo/project.zh.yaml", change), set())

    def test_chinese_title_landscape(self):
        def change(d):
            d["fields"]["title"] = "代码审查自进化"
        self.assertEqual(self.rows("examples/harness-landscape/project.zh.yaml", change), set())

    def test_narrow_mark_over_half_a_wide_letter(self):
        from cinetty.canvas import Canvas, tw
        c = Canvas(10, 1)
        c.put(2, 0, "水泵")
        c.put(3, 0, "●")    # a packet on a wire passes over the second half of 水
        c.put(5, 0, " ")    # a space drawn over the second half of 泵 gives way to it
        c.normalize()
        row = "".join(x[0] for x in c.cells[0])
        self.assertEqual(tw(row), 10)
        self.assertIn("●", row)
        self.assertIn("泵", row)
