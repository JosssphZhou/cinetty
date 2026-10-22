"""Every field in every template.yaml has a type the checker knows and only known keys.

An unquoted comma in a flow mapping once split a desc into a stray key and left the
field without a type, so the checker skipped its width limit.
"""
import unittest

import yaml

from helpers import ROOT

TYPES = {"text", "number", "integer", "enum", "ref", "list", "record", "file", "any"}
KEYS = {"type", "desc", "required", "max_cells", "measure", "allow_empty", "allowed_chars", "placeholders", "split_at",
        "range", "unit", "values", "to", "of", "items", "min_items", "max_items", "fields", "formats",
        "count_of", "count_below", "needs"}


def walk(schema, path, out):
    if not isinstance(schema, dict):
        out.append(f"{path}: not a mapping")
        return
    if schema.get("type") not in TYPES:
        out.append(f"{path}: type {schema.get('type')!r}")
    stray = set(schema) - KEYS
    if stray:
        out.append(f"{path}: unknown keys {sorted(map(str, stray))}")
    for name, sub in (schema.get("fields") or {}).items():
        walk(sub, f"{path}.{name}", out)
    if isinstance(schema.get("of"), dict):
        walk(schema["of"], f"{path}[]", out)


class TemplateSchema(unittest.TestCase):
    def test_every_field_has_a_known_type(self):
        out = []
        for p in sorted((ROOT / "templates").glob("*/template.yaml")):
            meta = yaml.safe_load(p.read_text(encoding="utf-8"))
            walk({"type": "record", "fields": meta["fields"]}, p.parent.name, out)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
