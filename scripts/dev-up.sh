#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Starting infra (postgres/redis/minio)"
docker compose -f "$ROOT/infra/docker/compose.yml" up -d

echo "==> Migrating DB"
cd "$ROOT/apps/api"
poetry run alembic upgrade head

echo
echo "==> Start API in one terminal:"
echo "cd $ROOT/apps/api && poetry run uvicorn app.main:app --reload --host 127.0.0.1 --port 58000"
echo
echo "==> Start Worker in another terminal:"
echo "cd $ROOT/apps/api && poetry run python -m app.worker"
echo
echo "==> Start Web in another terminal:"
echo "cd $ROOT/apps/web && npm run dev"