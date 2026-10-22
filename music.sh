#!/bin/bash
# Run from the workbench root:  bash moonstar-music/music.sh [cli args]
set -e

# Workbench root = parent of this repo (moonstar-music/)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HARNESS="$ROOT/moonstar-rs/scripts/harness.sh"

echo ""
echo "=== MOONSTAR MUSIC START ==="
echo ""

if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -f "$ROOT/moonstar-rs/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/moonstar-rs/.env"
    set +a
fi
if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "ERROR: OPENROUTER_API_KEY is not set. Export it or put it in $ROOT/moonstar-rs/.env"
    exit 1
fi

echo "[1/2] Starting moonstar-rs gateway + worker (db, migrations, build)..."
bash "$HARNESS" serve

cleanup() {
    echo ""
    bash "$HARNESS" stop || true
    exit 0
}
trap cleanup INT TERM

echo ""
echo "[2/2] Starting music generation loop..."
echo "      Press Ctrl+C to stop all processes."
echo ""

cd "$ROOT/moonstar-music"
python -m moonstar_music.cli "$@"
