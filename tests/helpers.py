"""Shared helpers for the tests: run the command line, make changed copies of example projects."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(*args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "cinetty", *map(str, args)], cwd=cwd, capture_output=True, text=True)


def check(project):
    """(exit code, parsed JSON) of ``check --format json``; fails the test if stdout is not JSON."""
    r = run("check", project, "--format", "json")
    return r.returncode, json.loads(r.stdout)


def variant(src, change):
    """A copy of an example project, changed, written next to the original so relative paths still work.
    The copy has its own name, so it never finds photos prepared for the example."""
    data = yaml.safe_load(Path(src).read_text(encoding="utf-8"))
    change(data)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=Path(src).parent, delete=False, encoding="utf-8")
    # A name of its own, so no photo cache that `make play` prepared under the example's name is used.
    data.setdefault("name", Path(src).stem)
    data["name"] = f"{data['name']}-test-{Path(tmp.name).stem}"
    yaml.safe_dump(data, tmp, allow_unicode=True)
    tmp.close()
    return Path(tmp.name)


def codes(out):
    return {(p["code"], p["path"]) for p in out["problems"]}
