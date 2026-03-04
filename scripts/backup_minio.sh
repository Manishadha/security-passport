#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$ROOT/backups/minio}"
mkdir -p "$OUT_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

set -a
if [ -f "$ROOT/.env" ]; then . "$ROOT/.env"; fi
if [ -f "$ROOT/.env.local" ]; then . "$ROOT/.env.local"; fi
set +a

ENDPOINT="${S3_ENDPOINT:-http://127.0.0.1:59000}"
ACCESS="${S3_ACCESS_KEY:?S3_ACCESS_KEY missing}"
SECRET="${S3_SECRET_KEY:?S3_SECRET_KEY missing}"
BUCKET="${S3_BUCKET:?S3_BUCKET missing}"

TMP="$OUT_DIR/minio_${TS}"
mkdir -p "$TMP"

python3 - <<PY
import os, sys
import boto3
from botocore.config import Config

endpoint=os.environ["ENDPOINT"]
access=os.environ["ACCESS"]
secret=os.environ["SECRET"]
bucket=os.environ["BUCKET"]
out=os.environ["OUT"]

s3=boto3.client(
  "s3",
  endpoint_url=endpoint,
  aws_access_key_id=access,
  aws_secret_access_key=secret,
  config=Config(signature_version="s3v4"),
  region_name=os.environ.get("S3_REGION","us-east-1"),
)

paginator=s3.get_paginator("list_objects_v2")
count=0
for page in paginator.paginate(Bucket=bucket):
  for obj in page.get("Contents",[]):
    key=obj["Key"]
    path=os.path.join(out, key.replace("/", "__"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    s3.download_file(bucket, key, path)
    count += 1
print(count)
PY
ENDPOINT="$ENDPOINT" ACCESS="$ACCESS" SECRET="$SECRET" BUCKET="$BUCKET" OUT="$TMP"

tar -C "$OUT_DIR" -czf "$OUT_DIR/minio_${TS}.tar.gz" "minio_${TS}"
rm -rf "$TMP"
echo "$OUT_DIR/minio_${TS}.tar.gz"