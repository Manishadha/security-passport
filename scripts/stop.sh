#!/usr/bin/env bash
set -euo pipefail

pkill -f "uvicorn app.main:app" || true
pkill -f "python -m app.worker" || true

docker compose -f infra/docker/compose.yml down
echo "stopped"
