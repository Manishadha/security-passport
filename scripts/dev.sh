#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"

echo "[1/3] Starting infra (postgres/redis/minio)..."
docker compose -f "$ROOT_DIR/infra/docker/compose.yml" up -d

echo "[2/3] Starting API (uvicorn)..."
cd "$API_DIR"
poetry run uvicorn app.main:app --reload --port 58000 &
API_PID=$!

echo "[3/3] Starting worker (RQ)..."
poetry run python -m app.worker &
WORKER_PID=$!

echo ""
echo "API PID=$API_PID  WORKER PID=$WORKER_PID"
echo "Health:"
sleep 1
curl -s http://127.0.0.1:58000/health/ready || true
echo ""
echo ""
echo "Press Ctrl+C to stop."

trap 'echo ""; echo "Stopping..."; kill $API_PID $WORKER_PID 2>/dev/null || true' INT TERM
wait
