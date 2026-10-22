"""Bindings inside scene text: ``{round.task}``, ``{max(round.conf):.2f}``.

A binding is a small Python expression evaluated with a fixed set of names
(``round``, ``rounds``, ``tick``, ``counter``, ``version``, ``photo``) and a few
safe builtins. No other builtins are available.
"""
from __future__ import annotations

from .canvas import tw

SAFE = {"tw": tw, "max": max, "min": min, "len": len, "round": round, "int": int, "float": float, "str": str,
        "abs": abs, "sum": sum, "sorted": sorted, "enumerate": enumerate, "range": range, "any": any, "all": all,
        "zip": zip, "format": format, "list": list, "set": set, "dict": dict}


class Lit(str):
    """User text: shown literally, braces are never read as bindings."""


class Obj(dict):
    """A dict whose keys can also be read as attributes (``round.task``)."""

    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError:
            raise AttributeError(k) from None
        return wrap(v)


def wrap(v):
    if isinstance(v, dict) and not isinstance(v, Obj):
        return Obj(v)
    if isinstance(v, list):
        return [wrap(x) for x in v]
    return v


_cache = {}


def _split(field):
    """Split ``expr:spec`` at the last top-level colon."""
    depth = 0
    for i in range(len(field) - 1, -1, -1):
        ch = field[i]
        if ch in ")]}":
            depth += 1
        elif ch in "([{":
            depth -= 1
        elif ch == ":" and depth == 0:
            return field[:i], field[i + 1:]
    return field, ""


def parse(text):
    """Pieces of a template string: plain strings and ``(code, spec)`` tuples."""
    if text in _cache:
        return _cache[text]
    pieces, i, n = [], 0, len(text)
    buf = []
    while i < n:
        ch = text[i]
        if ch == "{" and i + 1 < n and text[i + 1] == "{":
            buf.append("{"); i += 2; continue
        if ch == "}" and i + 1 < n and text[i + 1] == "}":
            buf.append("}"); i += 2; continue
        if ch == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            if buf:
                pieces.append("".join(buf)); buf = []
            expr, spec = _split(text[i + 1:j - 1])
            pieces.append((compile(expr.strip(), "<binding>", "eval"), spec))
            i = j
            continue
        buf.append(ch)
        i += 1
    if buf:
        pieces.append("".join(buf))
    _cache[text] = pieces
    return pieces


def has_binding(text):
    """True when ``text`` needs rendering: it has bindings or escaped braces (``{{`` ``}}``)."""
    if not isinstance(text, str) or isinstance(text, Lit):
        return False
    return "{" in text or "}" in text


def evaluate(code, ctx):
    # Everything goes into globals so comprehensions can see the names too.
    return eval(code, {"__builtins__": {}, **SAFE, **ctx})


def render(text, ctx):
    """Fill the bindings of ``text``."""
    if not isinstance(text, str) or isinstance(text, Lit):
        return text
    pieces = parse(text)
    if len(pieces) == 1 and isinstance(pieces[0], str):
        return pieces[0]
    out = []
    for p in pieces:
        if isinstance(p, str):
            out.append(p)
        else:
            code, spec = p
            out.append(format(evaluate(code, ctx), spec))
    return "".join(out)


def value(text, ctx):
    """Like ``render`` but a lone ``{expr}`` returns the raw value (number, list)."""
    if not isinstance(text, str) or isinstance(text, Lit):
        return text
    pieces = parse(text)
    if len(pieces) == 1 and not isinstance(pieces[0], str) and not pieces[0][1]:
        return evaluate(pieces[0][0], ctx)
    return render(text, ctx)
