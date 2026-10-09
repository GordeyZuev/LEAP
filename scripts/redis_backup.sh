#!/usr/bin/env bash
# Daily Redis RDB backup → Yandex Object Storage backups bucket.
#
# Invoked from cron on the VM (cloud-init installs the schedule); also available
# on demand via `make deploy-backup-redis`.
#
# Requires:
#   - docker container `leap_redis` running
#   - `yc` CLI configured (uses VM service account automatically)
#   - leap-backups bucket exists (Terraform creates it)

set -euo pipefail

BUCKET=${BUCKET:-leap-backups}
TS=$(date +%Y%m%d_%H%M%S)
TMP=/tmp/leap_redis_${TS}.rdb.gz

echo "[redis_backup] $(date -Iseconds) starting snapshot"

# Read LASTSAVE before BGSAVE: a small dataset finishes before the next redis-cli call.
prev=$(docker exec leap_redis redis-cli LASTSAVE | tr -d '[:space:]')
docker exec leap_redis redis-cli BGSAVE >/dev/null

cur=$prev
for _ in $(seq 1 60); do
  cur=$(docker exec leap_redis redis-cli LASTSAVE | tr -d '[:space:]')
  if [ "$cur" != "$prev" ]; then
    break
  fi
  sleep 1
done

if [ "$cur" = "$prev" ]; then
  echo "[redis_backup] ERROR: BGSAVE did not complete in 60s"
  exit 1
fi

docker exec leap_redis cat /data/dump.rdb | gzip > "$TMP"
SIZE=$(stat -c%s "$TMP" 2>/dev/null || stat -f%z "$TMP")

trap 'rm -f "$TMP"' EXIT

if [ "$SIZE" -lt 64 ]; then
  echo "[redis_backup] ERROR: dump too small ($SIZE bytes) — Redis unreachable?"
  exit 1
fi

yc storage s3 cp "$TMP" "s3://${BUCKET}/redis/leap_redis_${TS}.rdb.gz"
echo "[redis_backup] $(date -Iseconds) uploaded s3://${BUCKET}/redis/leap_redis_${TS}.rdb.gz (${SIZE} bytes)"
