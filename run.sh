#!/usr/bin/env bash
#
# One-shot launcher for AI-Wrapped.
#
#   ./run.sh              # set up (if needed) and start the web server
#   ./run.sh web          # same as above
#   ./run.sh cli [args]   # run the CLI pipeline, e.g. ./run.sh cli --user me --period last:90
#   ./run.sh test         # run the test suite
#   ./run.sh setup        # only create the venv and install dependencies
#
# Env overrides for the web server: HOST (default 127.0.0.1), PORT (default 8000).
set -euo pipefail

cd "$(dirname "$0")"

VENV="venv"
PY="$VENV/bin/python"
REQ_STAMP="$VENV/.requirements-installed"

# ── 1. virtualenv ────────────────────────────────────────────────────────────
if [[ ! -x "$PY" ]]; then
  echo "→ creating virtualenv ($VENV)…"
  python3 -m venv "$VENV"
fi

# ── 2. dependencies (only reinstall when requirements.txt changes) ───────────
if [[ ! -f "$REQ_STAMP" || requirements.txt -nt "$REQ_STAMP" ]]; then
  echo "→ installing dependencies…"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r requirements.txt
  touch "$REQ_STAMP"
fi

# ── 3. .env ──────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  echo "→ no .env found — creating one from .env.example."
  cp .env.example .env
  echo "  Edit .env and fill in LASTFM_API_KEY, MUSICBRAINZ_CONTACT and an LLM key,"
  echo "  then re-run ./run.sh"
  exit 1
fi

# ── 4. dispatch ──────────────────────────────────────────────────────────────
cmd="${1:-web}"
case "$cmd" in
  web|"")
    HOST="${HOST:-127.0.0.1}"
    PORT="${PORT:-8000}"
    echo "→ starting web server on http://$HOST:$PORT  (Ctrl-C to stop)"
    HOST="$HOST" PORT="$PORT" exec "$PY" frontend/server.py
    ;;
  cli)
    shift
    exec "$PY" wrapped.py "$@"
    ;;
  test)
    exec "$PY" -m pytest -q
    ;;
  setup)
    echo "→ setup complete."
    ;;
  *)
    echo "usage: ./run.sh [web|cli [args]|test|setup]" >&2
    exit 2
    ;;
esac
