#!/bin/bash
# Run from the workbench root:  bash moonstar-music/music.sh
set -e

# Workbench root = parent of this repo (moonstar-music/)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo ""
echo "=== MOONSTAR MUSIC START ==="
echo ""

echo "[1/3] Starting Moonstar gateway..."
cd "$ROOT/moonstar"
bash start.sh > /tmp/moonstar-gateway.log 2>&1 &
GATEWAY_PID=$!
echo "      PID $GATEWAY_PID - logs: /tmp/moonstar-gateway.log"

echo "      Waiting for gateway on http://localhost:8000 ..."
for i in $(seq 1 30); do
    if curl -s --max-time 2 http://localhost:8000/docs > /dev/null 2>&1; then
        echo "      Gateway UP"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Gateway did not start after 60s. Check /tmp/moonstar-gateway.log"
        exit 1
    fi
    sleep 2
done

echo ""
echo "[2/3] Starting Moonstar worker..."
(
    cd "$ROOT/moonstar/packages/moonstar-gateway"
    set -a
    source .env 2>/dev/null || true
    set +a
    NO_COLOR=1 PYTHONUNBUFFERED=1 python -m moonstar_gateway.cli worker
) > /tmp/moonstar-worker.log 2>&1 &
WORKER_PID=$!
echo "      PID $WORKER_PID - logs: /tmp/moonstar-worker.log"
sleep 3

echo ""
echo "[3/3] Starting music generation loop..."
echo "      Press Ctrl+C to stop all processes."
echo ""

cleanup() {
    echo ""
    echo "Stopping worker (PID $WORKER_PID) and gateway (PID $GATEWAY_PID)..."
    kill "$WORKER_PID" 2>/dev/null || true
    kill "$GATEWAY_PID" 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

cd "$ROOT/moonstar-music"
python -m moonstar_music.cli "$@"
