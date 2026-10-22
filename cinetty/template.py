"""Templates: a fixed layout (``scene.yaml``) with named fields (``template.yaml``).

A project file (``project.yaml``) names its template and fills the fields.
``load`` returns the scene with the project's values in place, ready for the
engine. ``check_project`` checks the values against the field rules, and
``check_render`` plays the whole timeline and reports text that does not fit.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path

import yaml

from .canvas import tw
from .expr import Lit

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

REF = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")


class TemplateError(Exception):
    pass


def read_yaml(path):
    with open(path, encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise TemplateError(f"{path}: not valid YAML: {e}") from None


def template_dir(name):
    d = TEMPLATES / name
    if not (d / "template.yaml").exists():
        known = ", ".join(sorted(p.name for p in TEMPLATES.iterdir() if (p / "template.yaml").exists()))
        raise TemplateError(f"no template named {name!r} (templates: {known})")
    return d


def list_templates():
    out = []
    for d in sorted(TEMPLATES.iterdir()):
        if (d / "template.yaml").exists():
            out.append((d.name, read_yaml(d / "template.yaml")))
    return out


def lookup(data, path):
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise TemplateError(f"the project has no field {path!r}")
    return cur


def literal(v):
    """Mark every string of a user value as literal text."""
    if isinstance(v, str):
        return Lit(v)
    if isinstance(v, list):
        return [literal(x) for x in v]
    if isinstance(v, dict):
        return {k: literal(x) for k, x in v.items()}
    return v


def fill(node, fields):
    """Put project values into the template's scene where it says ``{{field.path}}``.

    A whole-string reference passes the value through with its type. A reference
    inside a longer string inserts the text with braces escaped, so user text is
    never evaluated.
    """
    if isinstance(node, dict):
        return {k: fill(v, fields) for k, v in node.items()}
    if isinstance(node, list):
        return [fill(v, fields) for v in node]
    if isinstance(node, str):
        m = REF.fullmatch(node)
        if m:
            return literal(copy.deepcopy(lookup(fields, m.group(1))))
        if REF.search(node):
            return REF.sub(lambda mm: str(lookup(fields, mm.group(1))).replace("{", "{{").replace("}", "}}"), node)
    return node


def read_project(project=None, template=None):
    """-> (template name, project dict, path). Without a project file, the template's own example."""
    if project:
        p = Path(project)
        if not p.exists():
            raise TemplateError(f"project file not found: {project}")
        data = read_yaml(p) or {}
        name = data.get("template") or template
        if not name:
            raise TemplateError(f"{project}: add 'template: <name>' (list them with: make templates)")
        return name, data, p
    # A template id alone plays its own example: "id" (English) or "id:zh".
    name, _, lang = template.partition(":")
    meta = read_yaml(template_dir(name) / "template.yaml")
    ex = meta["example"]
    if isinstance(ex, dict):
        if lang and lang not in ex:
            raise TemplateError(f"template {name!r} has examples for: {', '.join(ex)}")
        ex = ex[lang] if lang else ex.get("en", next(iter(ex.values())))
    ex = ROOT / ex
    return name, read_yaml(ex), ex


def load(project=None, template=None):
    name, data, path = read_project(project, template)
    d = template_dir(name)
    scene = read_yaml(d / "scene.yaml")
    scene = fill(scene, data.get("fields") or {})
    if scene.get("driver") == "events":
        from .board import read_events
        scene["_events"] = read_events(data.get("events"), Path(path).parent)
    # The small "made with cinetty" credit: on unless the project or the scene says credit: false.
    scene["credit"] = bool(data.get("credit", scene.get("credit", True)))
    scene["_meta"] = {"template": name, "project": str(path), "dir": str(d),
                      "name": data.get("name") or Path(path).stem.replace("project.", "").replace("project", name)}
    return scene


# ------------------------------------------------------------------ field checks
GROUP = re.compile(r"(^|\.)(legend|status|versions\[\d+\])$|^(fields|status)$")


def problem(code, path, hint, **kw):
    """One problem for the report. Length problems always end with the change that fixes them."""
    if code in ("too_long", "too_long_on_screen"):
        actual, limit = kw.get("actual"), kw.get("limit")
        if isinstance(actual, int) and isinstance(limit, int) and actual > limit:
            kw.setdefault("over", actual - limit)
            if "shorten by" not in hint and "fix:" not in hint:
                if GROUP.search(path):
                    hint += (f"; fix: shorten the texts under {path} by {kw['over']} cells in total, "
                             f"so the line is at most {limit} cells")
                else:
                    hint += f"; fix: shorten by {kw['over']} cells, to at most {limit} cells"
    d = {"code": code, "path": path, "hint": hint}
    d.update(kw)
    return d


def has_bad_char(s):
    """Tabs, line breaks (including U+0085, U+2028, U+2029) and other control characters.
    A terminal cell cannot show them, and a line break would hide the rest of the text."""
    return any(unicodedata.category(ch) in ("Cc", "Zl", "Zp") for ch in s)


# The series never separates words with a spaced middle dot or bullet.
SPACED_DOTS = (" \u00b7 ", " \u2022 ")

# Characters whose width Ghostty 1.3 and the width table here disagree on (measured by printing
# each one and asking Ghostty for the cursor position): it draws the trigrams, digrams, the long
# dashes and the flag letters two cells wide and the Hangul vowel and final-consonant jamo zero
# cells wide. Each one shifts the rest of its line on screen.
UNSURE_WIDTH = ((0x115F, 0x11FF), (0x2630, 0x2637), (0x268A, 0x268F), (0x2E3A, 0x2E3B), (0xFFA0, 0xFFA0),
                (0x1F1E6, 0x1F1FF))


def unsure_width(s):
    return sorted({ch for ch in s if any(a <= ord(ch) <= b for a, b in UNSURE_WIDTH)})


def check_text(s, schema, path, out, root=None):
    if not isinstance(s, str):
        out.append(problem("wrong_type", path, "write this as text (quote it if it looks like a number)",
                           actual=type(s).__name__))
        return
    if has_bad_char(s):
        out.append(problem("bad_char", path, "remove tabs, line breaks and control characters; write the text on one line"))
    if any(sep in s for sep in SPACED_DOTS):
        out.append(problem("spaced_dot", path, "fix: write a colon or a comma instead of the spaced dot, "
                           "or move the second part into another field", text=s))
    sep = schema.get("split_at")
    if sep and len([x for x in s.split(f" {sep} ") if x.strip()]) != 2:
        out.append(problem("no_split", path, f"fix: write it as '<before> {sep} <after>', for example 'v1 {sep} v3'; "
                           f"the divider of the comparison runs through the {sep}", text=s))
    unsure = unsure_width(s)
    if unsure:
        out.append(problem("unsure_width", path, "fix: replace " + " ".join(unsure) + " with another symbol; terminals "
                           "disagree on how many cells it takes, which shifts the rest of the line", actual="".join(unsure)))
    allowed = schema.get("allowed_chars")
    if allowed:
        extra = sorted({ch for ch in s if ch not in allowed})
        if extra:
            out.append(problem("bad_char", path, "use only these characters: " + " ".join(allowed),
                               actual="".join(extra)))
    shown = s
    ph = schema.get("placeholders")
    if ph:
        # Measure the text as it appears on screen, with the widest values filled in.
        measure = schema.get("measure") or {}
        try:
            shown = s.format(**{k: measure.get(k, 0) for k in ph})
        except (KeyError, IndexError, ValueError):
            out.append(problem("bad_placeholder", path,
                               "only these placeholders are allowed: " + ", ".join("{" + k + "}" for k in ph)
                               + "; write a literal brace as {{ or }}"))
            return
    mx = schema.get("max_cells")
    if mx is not None and tw(shown) > int(mx):
        hint = f"shorten by {tw(shown) - int(mx)} cells, to at most {mx} cells (a CJK character counts as 2)"
        if shown != s:
            hint += f"; measured as shown: {shown!r}"
        out.append(problem("too_long", path, hint, actual=tw(shown), limit=int(mx), over=tw(shown) - int(mx), text=s))
    if tw(s) == 0 and schema.get("required", True) and not schema.get("allow_empty"):
        out.append(problem("empty", path, "fill this field"))


def check_count_below(rule, record, key, path, out, root):
    """``record[key]`` must be how many numbers of the sibling list ``rule['list']`` lie below the
    project's ``rule['gate']`` (for example fallbacks out of confidences)."""
    values, count = record.get(rule["list"]), record[key]
    try:
        gate = float(lookup(root or {}, rule["gate"]))
    except (TemplateError, TypeError, ValueError):
        return
    if not isinstance(values, list) or isinstance(count, bool) or not isinstance(count, int):
        return
    numbers = [x for x in values if isinstance(x, (int, float)) and not isinstance(x, bool)]
    n = sum(x < gate for x in numbers)
    if count != n:
        out.append(problem("count_mismatch", f"{path}.{key}",
                           f"{count} here, but {n} of the {len(numbers)} numbers in {rule['list']} are below "
                           f"fields.{rule['gate']} ({gate:g}); fix: write {n} here, or change the numbers or the gate",
                           actual=count, limit=n))


def walk_field(schema, value, path, out, root=None, base=None):
    kind = schema.get("type", "text")
    if value is None:
        if schema.get("required", True):
            out.append(problem("missing", path, f"add this field: {schema.get('desc', kind)}"))
        return
    if kind == "text":
        check_text(value, schema, path, out, root)
    elif kind in ("number", "integer"):
        ok = isinstance(value, int) if kind == "integer" else isinstance(value, (int, float))
        if not ok or isinstance(value, bool):
            out.append(problem("wrong_type", path, f"write a {kind}", actual=repr(value)))
            return
        lo, hi = schema.get("range", [None, None])
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            out.append(problem("out_of_range", path, f"use a value from {lo} to {hi}"
                               + (f" ({schema['unit']})" if schema.get("unit") else ""), actual=value, limit=[lo, hi]))
        elif schema.get("count_of"):
            # A count of items in another list, for example lessons adopted out of store.entries.
            try:
                n = len(lookup(root or {}, schema["count_of"]))
            except (TemplateError, TypeError):
                n = None
            if n is not None and value > n:
                out.append(problem("out_of_range", path, f"fields.{schema['count_of']} has {n} items; "
                                   f"fix: use at most {n} here, or add {value - n} more items there",
                                   actual=value, limit=n))
    elif kind == "enum":
        if value not in schema["values"]:
            out.append(problem("not_allowed", path, "use one of: " + ", ".join(map(str, schema["values"])),
                               actual=value))
    elif kind == "ref":
        target = schema["to"]
        list_path, _, key = target.partition("[].")   # "parts" or "photos[].id"
        try:
            names = lookup(root or {}, list_path)
            if key:
                names = [d.get(key) for d in names if isinstance(d, dict)]
        except TemplateError:
            names = []
        if value not in names:
            out.append(problem("unknown_ref", path, f"use one of the names in fields.{target.replace('[].', '[].')}: "
                               + ", ".join(map(str, names)), actual=value))
    elif kind == "list":
        if not isinstance(value, list):
            out.append(problem("wrong_type", path, "write a list"))
            return
        n = schema.get("items")
        lo = schema.get("min_items", n)
        hi = schema.get("max_items", n)
        if lo is not None and len(value) < int(lo):
            out.append(problem("too_few", path, f"needs {'exactly ' + str(n) if n else 'at least ' + str(lo)} items",
                               actual=len(value), limit=int(lo)))
        if hi is not None and len(value) > int(hi):
            out.append(problem("too_many", path, f"needs {'exactly ' + str(n) if n else 'at most ' + str(hi)} items",
                               actual=len(value), limit=int(hi), over=len(value) - int(hi)))
        item = schema.get("of", {"type": "text"})
        for i, v in enumerate(value):
            walk_field(item, v, f"{path}[{i}]", out, root, base)
    elif kind == "record":
        if not isinstance(value, dict):
            out.append(problem("wrong_type", path, "write a mapping of fields"))
            return
        for k, sub in schema["fields"].items():
            walk_field(sub, value.get(k), f"{path}.{k}" if path else k, out, root, base)
            # Optional fields that only make sense together: winner needs learned_slot and learned.
            if value.get(k) is not None:
                for other in sub.get("needs") or []:
                    if value.get(other) is None:
                        out.append(problem("missing", f"{path}.{other}" if path else other,
                                           f"add this field; it is needed when {k} is set (or remove {k})"))
        for k, sub in schema["fields"].items():
            if sub.get("count_below") and value.get(k) is not None:
                check_count_below(sub["count_below"], value, k, path, out, root)
        for k in sorted(set(value) - set(schema["fields"])):
            out.append(problem("unknown_field", f"{path}.{k}" if path else k,
                               "remove it; allowed fields: " + ", ".join(schema["fields"])))
    elif kind == "file":
        if not isinstance(value, str):
            out.append(problem("wrong_type", path, "write a file path relative to the project file"))
            return
        f = (Path(base or ".") / value)
        if not f.is_file():
            out.append(problem("missing_file", path, f"no file at {value} (paths are relative to the project file)"))
        elif schema.get("formats") and f.suffix.lower().lstrip(".") not in schema["formats"]:
            out.append(problem("bad_format", path, "use one of: " + ", ".join(schema["formats"])))
    elif kind == "any":
        pass


def check_project(project=None, template=None):
    """Check a project file against its template's field rules. -> (template name, problems)."""
    name, data, path = read_project(project, template)
    meta = read_yaml(template_dir(name) / "template.yaml")
    out = []
    for k in sorted(set(data) - {"template", "template_version", "name", "credit", "fields", "events", "photos"}):
        out.append(problem("unknown_field", k, "top-level keys are: template, template_version, name, credit, fields, events"))
    if "credit" in data and not isinstance(data["credit"], bool):
        out.append(problem("wrong_type", "credit", "write true or false", actual=data["credit"]))
    want = meta.get("version")
    got = data.get("template_version")
    if want is not None and got is not None and str(got) != str(want):
        out.append(problem("template_version", "template_version",
                           f"this project was written for version {got}; the template is version {want}"))
    fields = data.get("fields") or {}
    walk_field({"type": "record", "fields": meta["fields"]}, fields, "fields", out, fields, Path(path).parent)
    return name, out


def find_field(fields, text, path="fields"):
    """Field paths whose text appears in ``text`` (longest first)."""
    hits = []

    def walk(v, p):
        if isinstance(v, str) and v and v in text:
            hits.append((len(v), p))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{p}[{i}]")
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{p}.{k}")
    walk(fields, path)
    return [p for _, p in sorted(hits, reverse=True)]


def lookup_path(fields, path):
    """Value at a reported path such as ``fields.rounds[0].task``."""
    cur = {"fields": fields}
    for name, idx in re.findall(r"\.?([^.\[\]]+)|\[(\d+)\]", path):
        cur = cur[int(idx)] if idx else cur[name]
    return cur


def guess_field(fields, text, hints, ri):
    """The project field most likely responsible for ``text`` on screen.

    Prefers fields named by the component (``field:`` in scene.yaml), then the
    current round, then fields outside the rounds. Several matching fields in
    the same place are reported by their common parent (``rounds[0].candidates[1]``).
    """
    hits = find_field(fields, text)
    scopes = [[p for p in hits if any(p.startswith("fields." + h) for h in hints)],
              [p for p in hits if p.startswith(f"fields.rounds[{ri}]")],
              [p for p in hits if not p.startswith("fields.rounds[")],
              hits]
    for sc in scopes:
        if not sc:
            continue
        if len(sc) == 1:
            return sc
        # Several hits: the parent whose children cover the most of the text wins.
        groups = {}
        for p in sc:
            parent = re.sub(r"(\.[^.\[]+|\[\d+\])$", "", p)
            groups.setdefault(parent, []).append(p)
        best = max(groups.values(), key=lambda g: sum(len(str(lookup_path(fields, x))) for x in g))
        return best if len(best) == 1 else [re.sub(r"(\.[^.\[]+|\[\d+\])$", "", best[0])]
    return []


def cells_at(fields, path):
    """Width of the text at ``path`` (the widest item for a list); 0 when there is none."""
    try:
        v = lookup_path(fields, path)
    except (KeyError, IndexError, TypeError):
        return 0
    return max((tw(str(x)) for x in v), default=0) if isinstance(v, list) else tw(str(v))


def check_render(project=None, template=None, step=None):
    """Play the whole timeline and report text wider than its slot, once per slot and text."""
    from .scene import Scene
    scene = load(project, template)
    if scene.get("driver") == "events":
        from .engine import build
        return build(scene).check()
    _, data, _ = read_project(project, template)
    fields = data.get("fields") or {}
    S = Scene(scene)
    step = step or 1.0 / 15
    seen = {}
    t = 0.0
    while t < S.duration():
        try:
            c = S.render_frame(t)
        except (IndexError, KeyError, AttributeError, ValueError) as err:   # fields that disagree; report, no traceback
            ri = S.tl.round_at(t)
            return [problem("cannot_draw", f"fields.rounds[{ri}]" if "rounds" in fields else "fields",
                            f"the animation cannot be drawn at {t:.2f} s ({type(err).__name__}: {err}); "
                            "fix: make the fields of this round agree with the lists they count or name",
                            time=round(t, 2), round=ri + 1)]
        for where, text, width, limit in c.warnings:
            key = (where, text)
            if key not in seen:
                seen[key] = (t, width, limit)
        t += step
    hints = {}
    for b in scene.get("boxes") or []:
        for comp in b.get("content") or []:
            if comp.get("field"):
                hints.setdefault(b["id"], []).append(comp["field"])
    name = scene["_meta"]["template"]
    meta = read_yaml(template_dir(name) / "template.yaml")
    # Slots whose text comes from one known field: box titles, and slots named after a field (status, slots).
    known, row_refs = {}, {}
    for bx in read_yaml(template_dir(name) / "scene.yaml").get("boxes") or []:
        refs = re.findall(r"\{\{\s*([\w.\[\]]+)\s*\}\}", str(bx.get("title") or ""))
        if len(refs) == 1:
            known[f"{bx['id']}.title"] = "fields." + refs[0]
        # A row built from several fields (a label and a value): name them all in the hint.
        for comp in bx.get("content") or []:
            if isinstance(comp, dict) and "row" in comp:
                refs = re.findall(r"\{\{\s*([\w.\[\]]+)\s*\}\}", str(comp))
                if refs:
                    row_refs.setdefault(f"{bx['id']}.row{comp['row']}", []).extend("fields." + r for r in refs)
    worst = {}
    for (where, text), (t, width, limit) in seen.items():
        ri = S.tl.round_at(t)
        last = where.rsplit(".", 1)[-1]
        base = known.get(where) or ("fields." + last if last in meta["fields"] else None)
        if base:
            inside = [p for p in find_field(fields, text) if p == base or p.startswith((base + ".", base + "["))]
            path = inside[0] if len(inside) == 1 else base
            named = None
        else:
            paths = guess_field(fields, text, [h.replace("[]", f"[{ri}]") for h in hints.get(where.split(".")[0], [])], ri)
            if not paths and row_refs.get(where):
                # Point at the longest field of the row; the hint names the others.
                group = list(dict.fromkeys(row_refs[where]))
                path = max(group, key=lambda p: cells_at(fields, p))
                named = None
            else:
                group = None
                path = paths[0] if paths else where
                named = ref_names(meta["fields"], fields, path) if paths else None
        over = width - limit
        head = f"the text in '{where}' is {width} cells and the slot holds {limit}"
        if not base and group and len(group) > 1:
            hint = f"{head}; it is built from {', '.join(group)}; fix: shorten them by {over} cells in total"
        elif named:
            # The text is built from names defined elsewhere: point at the longest of them.
            path, nm = max(named, key=lambda n: tw(n[1]))
            hint = (f"{head}; it is built from names in {path.rsplit('[', 1)[0]}; fix: shorten {path} ({nm!r}) "
                    f"by {over} cells, to at most {max(1, tw(nm) - over)} cells, and use the new name wherever it is referenced")
        else:
            try:
                value = lookup_path(fields, path)
            except (KeyError, IndexError, TypeError):
                value = None
            if isinstance(value, str):
                hint = f"{head}; fix: shorten {path} by {over} cells, to at most {max(1, tw(value) - over)} cells"
            elif value is not None:
                hint = f"{head}; fix: shorten the texts under {path} by {over} cells in total"
            else:
                hint = f"{head}; fix: shorten the fields shown there by {over} cells in total"
        key = (path, where)
        if key not in worst or over > worst[key]["over"]:
            worst[key] = problem("too_long_on_screen", path, hint, actual=width, limit=limit, over=over,
                                 text=text, where=where, time=round(t, 2), round=ri + 1)
    return list(worst.values())


def schema_at(meta_fields, path):
    """The field rule for a reported path such as ``fields.rounds[0].patches[1]`` (None if unknown)."""
    sc = {"type": "record", "fields": meta_fields}
    for name, idx in re.findall(r"\.?([^.\[\]]+)|\[(\d+)\]", path)[1:]:
        if idx:
            sc = sc.get("of") if sc.get("type") == "list" else None
        else:
            sc = (sc.get("fields") or {}).get(name) if sc.get("type") == "record" else None
        if sc is None:
            return None
    return sc


def ref_names(meta_fields, fields, path):
    """[(path of the definition, name)] when ``path`` holds references to names defined in another list."""
    sc = schema_at(meta_fields, path)
    while sc is not None and sc.get("type") == "list":
        sc = sc.get("of")
    if not sc or sc.get("type") != "ref":
        return None
    try:
        value = lookup_path(fields, path)
    except (KeyError, IndexError, TypeError):
        return None
    flat = []

    def walk(v):
        if isinstance(v, list):
            for x in v:
                walk(x)
        elif v is not None:
            flat.append(v)
    walk(value)
    list_path, _, key = sc["to"].partition("[].")
    try:
        items = lookup_path(fields, "fields." + list_path)
    except (KeyError, IndexError, TypeError):
        return None
    out = []
    for i, it in enumerate(items):
        name = it.get(key) if key and isinstance(it, dict) else it
        if name in flat:
            out.append((f"fields.{list_path}[{i}]" + (f".{key}" if key else ""), str(name)))
    return out or None
