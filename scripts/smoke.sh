#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:58000}"

live=$(curl -s "$BASE/health/live" || true)
ready=$(curl -s "$BASE/health/ready" || true)

echo "$live"
echo "$ready"

echo "$live" | grep -q '"status":"alive"'
echo "$ready" | grep -q '"status":"ready"'

echo "smoke ok"
