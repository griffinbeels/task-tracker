#!/bin/bash
# Double-click for first setup or repair; the generated app is the daily launcher.
set -u
cd -- "$(dirname -- "$0")" || exit 1

fail() {
  printf '\nERROR: %s\n' "$1" >&2
  printf 'Press Return to close this setup window.\n'
  if [ -t 0 ]; then read -r _; fi
  exit 1
}

UV="$(command -v uv || true)"
if [ -z "$UV" ]; then
  for candidate in "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then UV="$candidate"; break; fi
  done
fi
[ -n "$UV" ] || fail 'uv was not found. Install it from https://docs.astral.sh/uv/ and double-click run.command again.'
export TASK_TRACKER_UV="$UV"

if ! .venv/bin/python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' 2>/dev/null; then
  for argument in "$@"; do
    [ "$argument" != --check-only ] || fail 'Python 3.12 is not ready. Run run.command without --check-only to set up.'
  done
  "$UV" venv --python 3.12 --clear .venv || fail 'Could not create Python 3.12. Reconnect and run.command again.'
fi
.venv/bin/python tools/bootstrap.py --mac-app "$@" || fail 'Setup failed. The details above explain what needs repair.'
