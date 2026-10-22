#!/usr/bin/env bash
# Non-interactive setup: creates .venv and installs the light pinned Python packages.
# --photo adds photo packages and downloads two models. Safe to run again.
# Everything it downloads stays inside the repository: uv's cache and any Python that uv
# installs go to .setup-cache/, models to models/. UV_* and PIP_* variables of the calling
# shell are ignored.
set -e
source "$(dirname "$0")/lib.sh"
cd "$ROOT"
REQUIREMENTS=requirements.txt
case "${1:-}" in
  "") ;;
  --photo) REQUIREMENTS=requirements-photo.txt ;;
  *) die "usage: bash scripts/setup.sh [--photo]" ;;
esac

for v in $(env | sed -n 's/^\(UV_[A-Za-z0-9_]*\)=.*/\1/p; s/^\(PIP_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$v"; done
export UV_CACHE_DIR="$ROOT/.setup-cache/uv-cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/.setup-cache/python"
export UV_PYTHON_BIN_DIR="$ROOT/.setup-cache/bin"
export UV_NO_CONFIG=1
export PIP_CACHE_DIR="$ROOT/.setup-cache/pip"
PYTHON_VERSION=${PYTHON_VERSION:-$MIN_PYTHON}

version_ok() {   # version_ok PYTHON: is it at least MIN_PYTHON?
  "$1" -c 'import sys; want = tuple(int(x) for x in sys.argv[1].split(".")); sys.exit(0 if sys.version_info[:2] >= want else 1)' "$MIN_PYTHON"
}

if [ -x "$PY" ] && ! version_ok "$PY"; then
  die ".venv uses Python $("$PY" -c 'import platform; print(platform.python_version())'); $MIN_PYTHON or newer is required. Remove .venv and run make setup again."
fi
if [ ! -x "$PY" ]; then
  if command -v uv >/dev/null; then
    echo "[setup] creating .venv with uv (Python $PYTHON_VERSION)"
    uv venv --quiet --python "$PYTHON_VERSION" .venv
  else
    SYS_PY=${PYTHON:-python3}
    command -v "$SYS_PY" >/dev/null || die "Python $MIN_PYTHON or newer is required (or install uv: https://docs.astral.sh/uv/)."
    version_ok "$SYS_PY" || die "Python $MIN_PYTHON or newer is required; $SYS_PY is $("$SYS_PY" -c 'import platform; print(platform.python_version())'). Install uv (https://docs.astral.sh/uv/) or set PYTHON=python$MIN_PYTHON."
    echo "[setup] creating .venv with $SYS_PY"
    "$SYS_PY" -m venv .venv
  fi
  version_ok "$PY" || die "the new .venv is older than Python $MIN_PYTHON; remove .venv and set PYTHON_VERSION=$MIN_PYTHON"
fi
echo "[setup] Python $("$PY" -c 'import platform; print(platform.python_version())')"

echo "[setup] installing Python packages"
if command -v uv >/dev/null; then
  VIRTUAL_ENV="$ROOT/.venv" uv pip install --quiet -r "$REQUIREMENTS"
else
  "$PY" -m pip install --quiet --disable-pip-version-check -r "$REQUIREMENTS"
fi

if [ "$REQUIREMENTS" = requirements-photo.txt ]; then
  "$PY" scripts/download_models.py
fi
echo "[setup] done. Next: make templates, then make play INPUT=examples/circuit-flow/project.en.yaml"
