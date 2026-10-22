"""SKILL.md and AGENTS.md are one text: the skill for Claude Code and Codex, the same body for other agents.

When you change SKILL.md, copy everything after its frontmatter into AGENTS.md.
"""
import re
import unittest

import yaml

from helpers import ROOT


def split(text):
    m = re.match(r"---\n(.*?)\n---\n\n?(.*)", text, re.S)
    return yaml.safe_load(m.group(1)), m.group(2)


class Skill(unittest.TestCase):
    def setUp(self):
        self.meta, self.body = split((ROOT / "SKILL.md").read_text(encoding="utf-8"))

    def test_agents_md_is_the_skill_body(self):
        self.assertEqual((ROOT / "AGENTS.md").read_text(encoding="utf-8"), self.body,
                         "AGENTS.md must equal SKILL.md without its frontmatter")

    def test_frontmatter(self):
        self.assertEqual(self.meta["name"], "cinetty")
        self.assertLessEqual(len(self.meta["description"]), 1024)
        self.assertEqual(set(self.meta), {"name", "description"})

    def test_body_is_short_and_says_where_to_run(self):
        self.assertLessEqual(len(self.body.splitlines()), 200)
        first = self.body.split("\n\n")[1]
        self.assertIn("from the directory that holds this file", first)

    def test_every_make_target_it_names_exists(self):
        targets = set(re.findall(r"^([a-z-]+):", (ROOT / "Makefile").read_text(), re.M))
        for t in set(re.findall(r"\bmake ([a-z-]+)", self.body)):
            self.assertIn(t, targets, f"make {t}")
