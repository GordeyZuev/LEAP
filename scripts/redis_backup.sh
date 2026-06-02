#!/usr/bin/env bash
# Daily Redis RDB backup → Yandex Object Storage backups bucket.
#
# Redis holds the Celery broker, result backend and beat schedule cache.
# Losing /data wipes all in-flight tasks; AOF on the named volume is fine for
# container restarts but doesn't survive VM destruction. Nightly RDB snapshot
# to S3 plugs that gap.
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

# BGSAVE forks Redis to write /data/dump.rdb without blocking; we then copy it
# out of the container. SAVE would block the whole event loop.
docker exec leap_redis redis-cli BGSAVE >/dev/null

# Wait for the BGSAVE to finish (max 60s). LASTSAVE returns the unix timestamp
# of the last successful background save.
prev=$(docker exec leap_redis redis-cli LASTSAVE)
for _ in $(seq 1 60); do
  cur=$(docker exec leap_redis redis-cli LASTSAVE)
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
