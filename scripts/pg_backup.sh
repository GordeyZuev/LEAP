#!/usr/bin/env bash
# Daily Postgres backup → Yandex Object Storage backups bucket.
#
# Invoked from cron on the VM (cloud-init installs the schedule); also available
# on demand via `make deploy-backup-pg`.
#
# Requires:
#   - docker container `leap_postgres` running
#   - `yc` CLI configured (uses VM service account automatically)
#   - leap-backups bucket exists (Terraform creates it)

set -euo pipefail

BUCKET=${BUCKET:-leap-backups}
TS=$(date +%Y%m%d_%H%M%S)
TMP=/tmp/leap_${TS}.sql.gz

echo "[pg_backup] $(date -Iseconds) starting dump"

docker exec leap_postgres pg_dump -U postgres leap_platform | gzip > "$TMP"
SIZE=$(stat -c%s "$TMP" 2>/dev/null || stat -f%z "$TMP")

if [ "$SIZE" -lt 1024 ]; then
  echo "[pg_backup] ERROR: dump too small ($SIZE bytes) — Postgres unreachable?"
  rm -f "$TMP"
  exit 1
fi

yc storage cp --quiet "$TMP" "s3://${BUCKET}/postgres/leap_${TS}.sql.gz"
rm -f "$TMP"

echo "[pg_backup] $(date -Iseconds) uploaded s3://${BUCKET}/postgres/leap_${TS}.sql.gz (${SIZE} bytes)"
