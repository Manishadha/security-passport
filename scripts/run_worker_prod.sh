#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/api"
exec poetry run rq worker -u "${REDIS_URL:-redis://127.0.0.1:56379/0}" default