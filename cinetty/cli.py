"""Command line: list templates, check a project, draw one frame, play in a terminal.

  python -m cinetty templates
  python -m cinetty check INPUT [--format json]
  python -m cinetty once INPUT [--at SECONDS]
  python -m cinetty play INPUT [--loop]
  python -m cinetty info INPUT          (name, size and times as JSON)

INPUT is a project file (project.yaml) or a template id (plays its example).

``play`` takes two optional environment variables for a script that records the screen:
CINETTY_START_FILE (stay blank until this file exists, so the first bright frame is t = 0) and
CINETTY_TERM_FILE (write the terminal's size there as JSON once it is ready).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import struct
import sys
import termios
import time
from pathlib import Path

from . import template as T
from . import terminal
from .canvas import encode, stamp_credit, steady_credit_spot


def _scene(inp):
    from .engine import build
    spec = T.load(**_project_args(inp))
    return build(spec), spec


def _project_args(inp):
    if inp.endswith((".yaml", ".yml")) or os.path.sep in inp:
        return {"project": inp}
    return {"template": inp}


def cmd_templates(a):
    rows = []
    for name, meta in T.list_templates():
        prev = meta.get("preview") or {}
        rows.append({"id": name, "kind": meta.get("kind", "video"), "purpose": meta.get("purpose", ""),
                     "terminal": meta.get("terminal", ""), "duration": meta.get("duration", ""),
                     "preview": f"templates/{name}/{prev.get('clip') or prev.get('still') or ''}",
                     "example": meta.get("example")})
    if a.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    for r in rows:
        print(f"{r['id']:<22} {r['kind']:<6} {r['purpose']}")
        print(f"{'':<29} terminal: {r['terminal']}" + (f", {r['duration']}" if r["duration"] else ""))
        print(f"{'':<29} preview: {r['preview']}")
    return 0


def cmd_check(a):
    try:
        args = _project_args(a.input)
        name, problems = T.check_project(**args)
        if not problems:
            problems = T.check_render(**args)
    except T.TemplateError as e:
        problems = [T.problem("bad_input", "", str(e))]
        name = None
    if a.format == "json":
        print(json.dumps({"template": name, "ok": not problems, "problems": problems}, ensure_ascii=False, indent=1))
    else:
        if not problems:
            print(f"ok: {a.input} fits template {name}")
        for p in problems:
            extra = ""
            if "actual" in p and "limit" in p:
                extra = f" ({p['actual']} > {p['limit']})" if p.get("over") else f" (got {p['actual']}, allowed {p['limit']})"
            where = ""
            if p.get("time") is not None:
                where = f" [round {p['round']}, t={p['time']}s]" if "round" in p else f" [t={p['time']}s]"
            print(f"{p['code']}: {p['path']}{extra}{where}: {p['hint']}")
    return 1 if problems else 0


def cmd_once(a):
    S, spec = _scene(a.input)
    c = S.render_frame(a.at)
    if spec["credit"]:
        stamp_credit(c, steady_credit_spot(S.render_frame, S.duration()))
    if a.text:
        print(c.text())
    else:
        sys.stdout.write("\x1b[?25l\x1b[2J" + encode(c) + "\x1b[0m\n")
    return 0


def cmd_info(a):
    S, spec = _scene(a.input)
    if spec.get("driver") == "events":
        print(json.dumps({"name": spec["_meta"]["name"], "template": spec["_meta"]["template"], "kind": "video",
                          "cols": S.cols, "rows": S.rows, "fps": S.fps, "duration": S.duration()},
                         ensure_ascii=False))
        return 0
    tl = S.tl
    out = {"name": spec["_meta"]["name"], "template": spec["_meta"]["template"], "kind": "video", "cols": S.cols, "rows": S.rows,
           "fps": S.fps, "duration": tl.TOTAL,
           "times": {"intro": tl.intro, "hot": tl.HOT_S, "hold": tl.HOLD_S, "fade": tl.FADE_S, "total": tl.TOTAL,
                     "phases": tl.PH}}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def term_size():
    """(cols, rows, width px, height px) of the controlling terminal."""
    buf = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
    rows, cols, xp, yp = struct.unpack("HHHH", buf)
    return cols, rows, xp, yp


def cmd_play(a):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        # Without a terminal the player would wait for a window size forever.
        print("cinetty: make play needs an interactive terminal, and this command runs without one. "
              "Run it in a terminal window, or look at one moment as text with: "
              f"make once INPUT={a.input} AT=12", file=sys.stderr)
        return 2
    S, spec = _scene(a.input)
    total = S.duration()
    spot = steady_credit_spot(S.render_frame, total) if spec["credit"] else None
    if S.photos is not None and S.photos.meta is None:
        print("cinetty: the photos are not prepared yet; run: make play INPUT=" + a.input, file=sys.stderr)
        return 2
    report = os.environ.get("CINETTY_TERM_FILE")
    sys.stdout.write("\x1b[?25l")
    try:
        left, top = terminal.fit(S.cols, S.rows, exact=bool(report))
    except KeyboardInterrupt:
        sys.stdout.write("\x1b[0m\x1b[?25h\n")
        return 130
    if report:
        cols, rows, xp, yp = term_size()
        Path(report).write_text(json.dumps({"cols": cols, "rows": rows, "width": xp, "height": yp}))
    sys.stdout.write("\x1b[2J")
    if S.photos is not None:
        S.photos.offset = (left, top)
        sys.stdout.write(S.photos.upload())
    shown = None
    redraw = [False]
    signal.signal(signal.SIGWINCH, lambda *_: redraw.__setitem__(0, True))
    start_file = os.environ.get("CINETTY_START_FILE")
    if start_file:
        # Stay blank until the recorder starts: the first bright frame marks t = 0 in the recording.
        sys.stdout.flush()
        while not os.path.exists(start_file):
            time.sleep(0.01)
    start = time.time()
    n, prev = 0, None
    try:
        while True:
            t = time.time() - start
            if a.loop:
                t %= total
            frame = S.render_frame(min(t, total - 1e-3))
            stamp_credit(frame, spot)
            if redraw[0]:
                # The window changed size: centre again (and wait if it became too small).
                redraw[0] = False
                left, top = terminal.fit(S.cols, S.rows, exact=bool(report))
                if S.photos is not None:
                    S.photos.offset = (left, top)
                sys.stdout.write("\x1b[2J")
                prev = None
                shown = None
            sys.stdout.write(encode(frame, prev, left, top))
            if S.photos is not None:
                esc, shown = S.photos.update(min(t, total - 1e-3), shown)
                sys.stdout.write(esc)
            sys.stdout.flush()
            prev = frame
            n += 1
            time.sleep(max(0.0, start + n / S.fps - time.time()))
            if not a.loop and t > total + a.tail:
                break
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(f"\x1b[0m\x1b[?25h\x1b[{top + S.rows + 1};1H\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cinetty")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("templates")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(fn=cmd_templates)
    p = sub.add_parser("check")
    p.add_argument("input")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("once")
    p.add_argument("input")
    p.add_argument("--at", type=float, default=0.0)
    p.add_argument("--text", action="store_true", help="print characters only, no colors")
    p.set_defaults(fn=cmd_once)
    p = sub.add_parser("play")
    p.add_argument("input")
    p.add_argument("--loop", action="store_true")
    p.add_argument("--tail", type=float, default=6.0, help="seconds to keep the last frame on screen")
    p.set_defaults(fn=cmd_play)
    p = sub.add_parser("info")
    p.add_argument("input")
    p.set_defaults(fn=cmd_info)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except T.TemplateError as e:
        print(f"cinetty: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
