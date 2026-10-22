"""Regression checks for fills that passed the check but broke the picture (visual pass, fill stress).

Each test writes a changed copy of an example and expects make check to fail with a field path
and a hint that names the exact change.
"""
import unittest

import yaml

from helpers import ROOT, check, codes, variant

WORKFLOW = ROOT / "examples/agent-workflow/project.en.yaml"


def problems_for(src, change):
    p = variant(src, change)
    try:
        code, out = check(p)
    finally:
        p.unlink()
    return code, out


class HintsNameTheFix(unittest.TestCase):
    """A length problem used to say only the limit; it now says how many cells to cut."""

    def test_field_too_long_says_how_many_cells_to_cut(self):
        def change(d):
            d["fields"]["main"]["title"] = "x" * 60
        code, out = problems_for(WORKFLOW, change)
        self.assertNotEqual(code, 0)
        p = next(p for p in out["problems"] if p["path"] == "fields.main.title")
        self.assertIn(f"shorten by {p['over']} cells", p["hint"])

    def test_group_line_too_long_says_how_many_cells_to_cut(self):
        def change(d):
            d["fields"]["legend"].update(main="m" * 20, workers="w" * 22, router="r" * 20, advisor="a" * 28)
        code, out = problems_for(WORKFLOW, change)
        p = next(p for p in out["problems"] if p["path"] == "fields.legend")
        self.assertIn(f"by {p['over']} cells", p["hint"])


class WorkflowMargins(unittest.TestCase):
    """A legend that filled the screen edge to edge used to pass; the line now keeps 2 cells each side."""

    def test_legend_keeps_side_margins(self):
        def change(d):
            d["fields"]["legend"]["advisor"] += "x" * 6   # 80 + 9 = 89 cells on a 90-cell screen
            d["fields"]["legend"]["workers"] += "x" * 3
        code, out = problems_for(WORKFLOW, change)
        self.assertNotEqual(code, 0)
        self.assertIn(("too_long_on_screen", "fields.legend"), codes(out))



PHOTO = ROOT / "examples/harness-photo/project.en.yaml"
PORTRAIT = ROOT / "examples/harness-portrait/project.en.yaml"


class PhotoLimits(unittest.TestCase):
    """Fills of photo-loop that passed but touched a border or ran into another text."""

    def assert_reported(self, change, path, code="too_long"):
        code_, out = problems_for(PHOTO, change)
        self.assertNotEqual(code_, 0)
        self.assertIn((code, path), codes(out))

    def test_learning_title_stays_clear_of_its_rainbow_label(self):
        # 60 cells used to run into the centered EVOLUTION label on the same row.
        self.assert_reported(lambda d: d["fields"]["sections"].update(learning="x" * 40), "fields.sections.learning")

    def test_store_lessons_keep_a_cell_before_the_border(self):
        self.assert_reported(lambda d: d["fields"]["store"]["entries"][0].update(cue="x" * 20), "fields.store.entries[0].cue")

    def test_fallback_line_keeps_a_cell_on_each_side(self):
        self.assert_reported(lambda d: d["fields"]["output"].update(fallback_line="x" * 15), "fields.output.fallback_line")

    def test_status_line_that_runs_off_screen_is_reported(self):
        # Ten-cell keys make a 75-cell line on a 66-cell screen; it used to be cut off without a word.
        def change(d):
            d["fields"]["status"] = {k: "x" * 10 for k in d["fields"]["status"]}
        self.assert_reported(change, "fields.status", "too_long_on_screen")

    def test_slot_chips_keep_their_spacing(self):
        # Seven-cell ids used to pass and run the three chips into each other.
        def change(d):
            d["fields"]["slots"] = [{"id": "aaaaaaa"}, {"id": "bbbbbbb"}, {"id": "ccccccc"}]
            for r in d["fields"]["rounds"]:
                if r.get("learned_slot"):
                    r["learned_slot"] = "aaaaaaa"
        code_, out = problems_for(PHOTO, change)
        self.assertNotEqual(code_, 0)
        self.assertTrue(any(p["code"] == "too_long_on_screen" and p["path"].startswith("fields.slots[") for p in out["problems"]),
                        out["problems"])


class PhotoPicture(unittest.TestCase):
    """What the example itself draws."""

    def frame(self, t):
        from cinetty.scene import Scene
        from cinetty.template import load
        return Scene(load(PHOTO)).render_frame(t)

    def test_rainbow_label_has_no_border_piece_between_letters(self):
        # A wire crossing the label row used to leave a dash between E and V: "E─V O L U T I O N".
        row = "".join(c[0] for c in self.frame(5.0).cells[30])
        self.assertIn(" E V O L U T I O N ", row)

    def test_output_box_has_no_spaced_dot(self):
        for t in (2.0, 5.0, 9.0, 14.0):
            row = "".join(c[0] for c in self.frame(t).cells[23][46:63])
            self.assertNotIn("·", row, f"t={t}: {row!r}")


class HintsForBuiltText(unittest.TestCase):
    """Text built from other names used to point at the reference, which cannot be shortened."""

    def test_patch_text_points_at_the_part_name(self):
        def change(d):
            d["fields"]["rounds"][0]["patches"][0] = ["Prompt Template", "Tool Guidance"]
        code_, out = problems_for(PORTRAIT, change)
        self.assertNotEqual(code_, 0)
        p = next(p for p in out["problems"] if p["code"] == "too_long_on_screen")
        self.assertTrue(p["path"].startswith("fields.parts["), p)
        self.assertIn("wherever it is referenced", p["hint"])

    def test_status_line_reports_the_status_field(self):
        def change(d):
            d["fields"]["status"].update(confidence="x" * 16, fallbacks="y" * 14, store="z" * 10)
        code_, out = problems_for(PORTRAIT, change)
        self.assertIn(("too_long_on_screen", "fields.status"), codes(out))


LANDSCAPE = ROOT / "examples/harness-landscape/project.en.yaml"
CIRCUIT = ROOT / "examples/circuit-flow/project.en.yaml"


def set_path(d, path, value):
    """Set fields.a.b[0].c in a project dict."""
    import re
    keys = [int(i) if i else k for k, i in re.findall(r"\.?([^.\[\]]+)|\[(\d+)\]", path)]
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = value


class TextKeepsOffBorders(unittest.TestCase):
    """Texts one or two cells shorter than the old limits used to touch or cover a box border."""

    CASES = [
        # (example, field, width that used to pass)
        (WORKFLOW, "fields.advisor.name", 21),
        (WORKFLOW, "fields.advisor.moments[0]", 18),
        (WORKFLOW, "fields.main.title", 26),
        (WORKFLOW, "fields.workers[0].task", 18),
        (WORKFLOW, "fields.delegate.effort_short", 4),
        (WORKFLOW, "fields.worker_states.done", 16),
        (WORKFLOW, "fields.review.subtitle", 32),
        (WORKFLOW, "fields.router.sharp_route", 22),
        (PORTRAIT, "fields.live.execute_line_1", 14),
        (PORTRAIT, "fields.store.version_change", 18),
        (PORTRAIT, "fields.learning.kept", 28),
        (LANDSCAPE, "fields.executor.subtitle", 64),
        (LANDSCAPE, "fields.rounds[0].task", 32),
    ]

    def test_each_field_reports_the_old_width(self):
        for src, path, width in self.CASES:
            with self.subTest(path=path):
                code_, out = problems_for(src, lambda d: set_path(d, path, "x" * width))
                self.assertNotEqual(code_, 0)
                self.assertTrue(any(p["path"] == path for p in out["problems"]), out["problems"])


class CircuitStatusMargin(unittest.TestCase):
    """A status line that reached the last column used to pass."""

    def test_status_line_keeps_the_right_margin(self):
        from cinetty.canvas import tw

        def change(d):
            keys = d["fields"]["status"]
            for e in d["events"]:          # every status value as wide as its key's first value
                if e.get("type") == "status":
                    e["value"] = next(str(k["initial"]) for k in keys if k["key"] == e["key"])
            n = 1 + sum(tw(str(k["key"])) + 2 + tw(str(k["initial"])) + 1 + 2 for k in keys) - 2
            grow = 120 - n                 # makes the line end exactly at the last column
            for k in keys:
                add = min(grow, 12 - tw(str(k["initial"])))
                k["initial"] = str(k["initial"]) + "x" * add
                grow -= add
            self.assertEqual(grow, 0)
            for e in d["events"]:
                if e.get("type") == "status":
                    e["value"] = next(str(k["initial"]) for k in keys if k["key"] == e["key"])
        code_, out = problems_for(CIRCUIT, change)
        self.assertIn(("too_long_on_screen", "fields.status"), codes(out))


class OnScreenPathsComeFromTheSlot(unittest.TestCase):
    """A status text that happened to contain a part name used to be blamed on the part list."""

    def test_status_with_a_part_name_reports_the_status(self):
        def change(d):
            d["fields"]["status"].update(round="prompt rnd", confidence="prompt cnf", fallbacks="prompt fbk", store="prompt sto")
        code_, out = problems_for(PHOTO, change)
        self.assertIn(("too_long_on_screen", "fields.status"), codes(out))
        self.assertFalse(any(p["path"].startswith("fields.patch_kinds") for p in out["problems"]), out["problems"])


def two_rounds_one_lesson(d):
    """A real run with two rounds and one adopted lesson, as a project gives it."""
    f = d["fields"]
    f["rounds"] = f["rounds"][:2]
    f["store"]["entries"] = f["store"]["entries"][:1]
    f["store"]["initial"] = 0
    f["rounds"][0]["lessons"] = 0
    f["rounds"][1]["lessons"] = 1


class TwoRoundsOneLesson(unittest.TestCase):
    """photo-loop used to demand exactly three rounds and two lessons, so a real run with two
    rounds and one lesson had to make up a third round and a second lesson."""

    def test_check_passes(self):
        code_, out = problems_for(PHOTO, two_rounds_one_lesson)
        self.assertEqual(code_, 0, out["problems"])

    def test_board_counts_two_rounds_and_shows_one_lesson(self):
        from cinetty import template
        from cinetty.engine import build
        p = variant(PHOTO, two_rounds_one_lesson)
        try:
            sc = build(template.load(p))
        finally:
            p.unlink()
        def text(t, rows=slice(None), cols=slice(None)):
            return "\n".join("".join(c[0] for c in row[cols]) for row in sc.render_frame(t).cells[rows])
        self.assertIn("round [1/2]", text(5.0))
        self.assertLess(sc.duration(), 30)
        # After round 2 adopts its lesson the store lists that one lesson and nothing else.
        lessons = [e["cue"] for e in yaml.safe_load(PHOTO.read_text())["fields"]["store"]["entries"]]
        self.assertIn("round [2/2]", text(25.0))
        store = text(25.0, slice(31, 45), slice(40, 64))   # the Experience Store box
        self.assertEqual([c for c in lessons if c in store], lessons[:1])


class FieldsThatMustAgree(unittest.TestCase):
    """Fills that used to crash the check with a traceback instead of naming a field."""

    def test_lessons_cannot_exceed_the_store(self):
        def change(d):
            d["fields"]["store"]["entries"] = d["fields"]["store"]["entries"][:2]
        code_, out = problems_for(PHOTO, change)
        self.assertNotEqual(code_, 0)
        p = next(p for p in out["problems"] if p["path"].endswith(".lessons"))
        self.assertEqual(p["code"], "out_of_range")
        self.assertIn("fix: use at most 2 here", p["hint"])

    def test_store_needs_one_lesson(self):
        def change(d):
            d["fields"]["store"]["entries"] = []
            d["fields"]["store"]["initial"] = 0
            for r in d["fields"]["rounds"]:
                r["lessons"] = 0
        code_, out = problems_for(PHOTO, change)
        self.assertNotEqual(code_, 0)
        self.assertIn(("too_few", "fields.store.entries"), codes(out))

    def test_store_cannot_start_with_more_lessons_than_it_has(self):
        def change(d):
            d["fields"]["store"]["entries"] = d["fields"]["store"]["entries"][:3]
            d["fields"]["store"]["initial"] = 4
            for r in d["fields"]["rounds"]:
                r["lessons"] = min(r["lessons"], 3)
        code_, out = problems_for(PHOTO, change)
        self.assertNotEqual(code_, 0)
        p = next(p for p in out["problems"] if p["path"] == "fields.store.initial")
        self.assertEqual(p["code"], "out_of_range")

    def test_winner_needs_its_slot(self):
        holder = {}

        def change(d):
            i = next(i for i, r in enumerate(d["fields"]["rounds"]) if r.get("winner"))
            holder["i"] = i
            d["fields"]["rounds"][i].pop("learned_slot")
        code_, out = problems_for(PHOTO, change)
        self.assertNotEqual(code_, 0)
        self.assertIn(("missing", f"fields.rounds[{holder['i']}].learned_slot"), codes(out))


class WorkflowLogLines(unittest.TestCase):
    """A log line that reached the log box border used to pass."""

    def test_log_text_keeps_a_cell_before_the_border(self):
        holder = {}

        def change(d):
            i = next(i for i, e in enumerate(d["events"]) if e.get("type") == "log" and "text" in e)
            holder["i"] = i
            d["events"][i]["text"] = "x" * 61
        code_, out = problems_for(WORKFLOW, change)
        self.assertIn(("too_long_on_screen", f"events[{holder['i']}].text"), codes(out))


if __name__ == "__main__":
    unittest.main()


class PortraitActionsAreFields(unittest.TestCase):
    """The portrait's action names (tap, type, scroll) and the target value were fixed in
    scene.yaml, so a system that does not tap a screen could not say what it does (blind test)."""

    def test_actions_and_target_come_from_the_project(self):
        from cinetty import template
        from cinetty.engine import build

        def change(d):
            d["fields"]["live"].update(action_label="处置动作类型标签", actions=["放行放", "复核", "拦截拦"],
                                       target_label="风险评分标签标签", target="0.9分")
        p = variant(ROOT / "examples/harness-portrait/project.zh.yaml", change)
        try:
            code, out = check(p)
            self.assertEqual(code, 0, out)
            sc = build(template.load(str(p)))
            shown = "\n".join("".join(c[0] for c in row) for t in (8.0, 8.5, 9.0, 9.5) for row in sc.render_frame(t).cells)
        finally:
            p.unlink()
        self.assertIn("0.9分", shown)
        self.assertTrue(any(a in shown for a in ("放行放", "复核", "拦截拦")))
        self.assertNotIn("112×40", shown)


class CircuitUnusedWires(unittest.TestCase):
    """A system with fewer connections than the board's sixteen wires had to write a label on every
    wire (a skill test wrote "unused" in Chinese). An empty label is now allowed and leaves the wire whole."""

    def test_empty_net_label_passes_and_leaves_no_gap(self):
        from cinetty import template
        from cinetty.engine import build

        p = variant(ROOT / "examples/circuit-flow/project.zh.yaml", lambda d: d["fields"]["nets"].update(d_e=""))
        try:
            code, out = check(p)
            self.assertEqual(code, 0, out)
            row = "".join(c[0] for c in build(template.load(str(p))).render_frame(30).cells[5])
        finally:
            p.unlink()
        arrow = row.index("▶", row.index("▶") + 1)      # the D to E arrow
        wire = row[row.rindex("│", 0, arrow) + 1:arrow]  # from D's right border to the arrow
        self.assertEqual(set(wire), {"┄"})


class AdviceLinesKeepOffTheBorder(unittest.TestCase):
    """A blind run wrote an advice line of 16 cells (8 CJK characters); the check let it touch the
    advisor column's right border. The original's longest line is 15 cells."""

    def test_sixteen_cell_advice_line_is_too_long(self):
        def change(d):
            e = next(e for e in d["events"] if e["type"] == "advise")
            e["lines"] = ["优先识别紧急诉求"]
        code, out = problems_for(WORKFLOW, change)
        self.assertNotEqual(code, 0)
        p = next(p for p in out["problems"] if p["path"].endswith(".lines[0]"))
        self.assertEqual((p["limit"], p["over"]), (15, 1))
        self.assertIn("shorten by 1 cells", p["hint"])


class RowHintsNameTheirFields(unittest.TestCase):
    """A row drawn from a label and a value (the portrait's target row) used to get the hint
    'shorten the fields shown there', with the slot name as its path."""

    def test_overflowing_row_names_both_fields(self):
        from cinetty import template

        def change(d):
            d["fields"]["live"].update(target_label="L" * 17, target="T" * 7)
        p = variant(ROOT / "examples/harness-portrait/project.en.yaml", change)
        try:
            found = [q for q in template.check_render(str(p)) if q.get("where") == "core.row2"]
        finally:
            p.unlink()
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["path"].startswith("fields.live."))
        self.assertIn("fields.live.target_label, fields.live.target", found[0]["hint"])
        self.assertIn("by 1 cells in total", found[0]["hint"])


class NoMadeUpNumbersUnderThePhoto(unittest.TestCase):
    """Every number on screen comes from the project file (release standard, section 8). The
    photo strip used to show a timecode made from the clock and a fixed '24 fps'."""

    def test_photo_strip_has_no_timecode_or_frame_rate(self):
        import re
        from cinetty import template
        from cinetty.engine import build
        sc = build(template.load(str(ROOT / "examples/harness-photo/project.en.yaml")))
        for t in (2.0, 9.5, 20.0):
            screen = "\n".join("".join(c[0] for c in row) for row in sc.render_frame(t).cells)
            self.assertNotIn("fps", screen)
            self.assertIsNone(re.search(r"\d\d:\d\d:\d\d", screen), t)
