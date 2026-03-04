#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DUMP_FILE="${1:?usage: restore_db.sh path/to/file.dump}"

set -a
if [ -f "$ROOT/.env" ]; then . "$ROOT/.env"; fi
if [ -f "$ROOT/.env.local" ]; then . "$ROOT/.env.local"; fi
set +a

PGHOST="${POSTGRES_HOST:-127.0.0.1}"
PGPORT="${POSTGRES_PORT:-55432}"
PGUSER="${POSTGRES_USER:?POSTGRES_USER missing}"
PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD missing}"
PGDATABASE="${POSTGRES_DB:?POSTGRES_DB missing}"

export PGPASSWORD
pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" --clean --if-exists "$DUMP_FILE"