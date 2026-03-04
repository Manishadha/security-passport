# SecurityPassport Runbook

## Start API (prod)
./scripts/run_api_prod.sh

## Start Worker (prod)
./scripts/run_worker_prod.sh

## Health
curl -s http://127.0.0.1:58000/health
curl -s http://127.0.0.1:58000/health/ready -H "Authorization: Bearer $TOKEN"
curl -s http://127.0.0.1:58000/health/version

## Ops
curl -s http://127.0.0.1:58000/ops/config -H "Authorization: Bearer $TOKEN"
curl -s http://127.0.0.1:58000/ops/queues -H "Authorization: Bearer $TOKEN"
curl -s http://127.0.0.1:58000/ops/jobs/recent -H "Authorization: Bearer $TOKEN"
curl -s http://127.0.0.1:58000/ops/whoami -H "Authorization: Bearer $TOKEN"

## Backups
./scripts/backup_db.sh
./scripts/backup_minio.sh

## Restore DB
./scripts/restore_db.sh backups/db_<name>_<ts>.dump

## Sentry test
curl -i http://127.0.0.1:58000/ops/sentry_test -H "Authorization: Bearer $TOKEN"

## Incident quick steps
1. Check /health/ready
2. Check /ops/queues and /ops/jobs/recent
3. If Redis is down: restart redis container/service, confirm /ops/queues returns 200
4. If jobs stuck queued: restart worker, confirm worker sees queue
5. If export failures: inspect job_runs last_error and audit events