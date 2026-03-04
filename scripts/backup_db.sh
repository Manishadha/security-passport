#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$ROOT/backups}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"

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
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -F c -Z 6 -f "$OUT_DIR/db_${PGDATABASE}_${TS}.dump"
echo "$OUT_DIR/db_${PGDATABASE}_${TS}.dump"