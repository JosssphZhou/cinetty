#!/usr/bin/env bash
# Check a project, prepare its photos if it has any, and play it in this terminal: play.sh INPUT [--loop]
source "$(dirname "$0")/lib.sh"
INPUT=$1; shift
require_venv
check_project "$INPUT"
# The photo template needs its photos cropped, outlined and turned into box effects (cached).
HF_HUB_OFFLINE=1 "$PY" -m cinetty.photos "$INPUT" >/dev/null || die "could not prepare the photos"
exec "$PY" -m cinetty play "$INPUT" "$@"
