# Shared helpers for the shell scripts. Source it, don't run it.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY="$ROOT/.venv/bin/python"
BUILD="$ROOT/build"
MIN_PYTHON=$(cat "$ROOT/.python-version")

die() { echo "cinetty: $*" >&2; exit 1; }

require_venv() {
  [ -x "$PY" ] || die "no virtualenv yet. Run: make setup"
}

# Check a project; stop with the problems if it does not fit its template.
check_project() {
  "$PY" -m cinetty check "$1" || die "fix the problems above, then run the command again"
}
