#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/api"
exec poetry run uvicorn app.main:app --host 0.0.0.0 --port 58000 --no-access-log