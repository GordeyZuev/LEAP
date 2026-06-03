#!/usr/bin/env bash
# LEAP VM bootstrap — invoked by `make deploy-vm-init` over SSH on a fresh
# (or partially-provisioned) Yandex Cloud VM.
#
# All inputs come from the environment so the same script works from cloud-init
# and from Makefile-driven re-runs. Required env vars:
#
#   FOLDER_ID            YC folder ID (yc config get folder-id)
#   DOMAIN               production domain, e.g. leap-platform.ru
#   CERT_EMAIL           Let's Encrypt expiry notice address
#   LOCKBOX_SECRET_ID    Lockbox secret holding all credentials
#   REGISTRY_ID          Container Registry ID (cr.yandex/<id>/...)
#   S3_BUCKET            main Object Storage bucket name
#   GITHUB_OWNER         e.g. GordeyZuev
#   GITHUB_REPO          e.g. ZoomUploader
#   GITHUB_BRANCH        e.g. main
#
# Idempotent: re-running on an already-bootstrapped VM only patches drift.

set -euo pipefail

LOG=/var/log/leap-bootstrap.log
exec > >(tee -a "$LOG") 2>&1
echo "[vm-init] $(date -Iseconds) starting"

REPO_DIR=/opt/leap
REPO_URL="https://github.com/${GITHUB_OWNER:?}/${GITHUB_REPO:?}.git"
BRANCH="${GITHUB_BRANCH:-main}"

# --- 1. Packages ----------------------------------------------------------
# Ubuntu's docker.io lacks the compose plugin; get.docker.com ships docker-ce
# + compose plugin together. Purge docker.io first if present (systemd unit
# conflict with docker-ce).
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git jq curl ca-certificates gnupg apache2-utils

if dpkg -l docker.io 2>/dev/null | grep -q '^ii'; then
  apt-get remove -y --purge docker.io containerd 2>&1 | tail -3
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable --now docker
usermod -aG docker ubuntu || true

# --- 1a. Mount persistent data disk at /var/lib/docker/volumes ------------
# Terraform attaches a secondary disk (yandex_compute_disk.data) with
# auto_delete=false. It survives VM recreation, so docker named volumes
# (postgres, redis, loki, prometheus, grafana) survive too. Detection
# excludes the boot disk (vda/sda). Idempotent — safe to re-run.
#
# Safety net: if /var/lib/docker/volumes already has data (we're running on
# an existing VM with volumes on the boot disk), refuse to auto-mount —
# mounting an empty new disk over a non-empty directory would shadow the
# existing data. Operator must rsync first; see DEPLOYMENT.md → VM durability.
DATA_DEVICE=$(lsblk -ndo NAME,TYPE | awk '$2=="disk" && $1!~/^(vda|sda)$/ {print "/dev/"$1; exit}')
mkdir -p /var/lib/docker/volumes
EXISTING_VOLUME_ENTRIES=$(find /var/lib/docker/volumes -mindepth 1 -maxdepth 1 2>/dev/null | head -1)

if [ -n "$DATA_DEVICE" ] && ! mountpoint -q /var/lib/docker/volumes; then
  if [ -n "$EXISTING_VOLUME_ENTRIES" ]; then
    echo "[vm-init] WARN: $DATA_DEVICE present but /var/lib/docker/volumes has data —"
    echo "[vm-init]       refusing to auto-mount (would hide existing volumes)."
    echo "[vm-init]       Migrate manually: see DEPLOYMENT.md → VM durability."
  else
    echo "[vm-init] preparing $DATA_DEVICE for /var/lib/docker/volumes"
    if ! blkid "$DATA_DEVICE" >/dev/null 2>&1; then
      mkfs.ext4 -F -L leap-data "$DATA_DEVICE"
    fi
    systemctl stop docker || true
    if ! grep -q "/var/lib/docker/volumes" /etc/fstab; then
      echo "UUID=$(blkid -s UUID -o value "$DATA_DEVICE") /var/lib/docker/volumes ext4 defaults,nofail 0 2" >> /etc/fstab
    fi
    mount /var/lib/docker/volumes
    systemctl start docker
  fi
fi

# --- 2. yc CLI (auths via VM SA metadata; configured for both root + ubuntu
#       so GH Actions deploys as ubuntu can use docker-credential-yc) -----
if ! command -v yc >/dev/null 2>&1; then
  curl -sSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh \
    | bash -s -- -i /usr/local -n
  ln -sf /usr/local/bin/yc /usr/bin/yc
fi
yc config set folder-id "${FOLDER_ID:?}" || true
yc container registry configure-docker

sudo -u ubuntu mkdir -p /home/ubuntu/.config/yandex-cloud
sudo -u ubuntu yc config profile create default >/dev/null 2>&1 || true
sudo -u ubuntu yc config set folder-id "${FOLDER_ID}" || true
sudo -u ubuntu yc container registry configure-docker

# --- 3. Clone (or update) the repo into /opt/leap ------------------------
mkdir -p "$REPO_DIR"
chown ubuntu:ubuntu "$REPO_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
  # Clone into ubuntu-writable /tmp, then merge over /opt/leap.
  tmpclone=$(sudo -u ubuntu mktemp -d /tmp/leap-clone.XXXXXX)
  sudo -u ubuntu git clone --branch "$BRANCH" "$REPO_URL" "$tmpclone"
  sudo -u ubuntu cp -rT "$tmpclone/." "$REPO_DIR/"
  rm -rf "$tmpclone"
else
  sudo -u ubuntu git -C "$REPO_DIR" fetch --depth=1 origin "$BRANCH"
  sudo -u ubuntu git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
fi

# --- 4. .env.static (values that never change between deploys) -----------
cat > "$REPO_DIR/.env.static" <<EOF
# ---------------------------- Database
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_DATABASE=leap_platform
DATABASE_USERNAME=postgres
# ---------------------------- Redis / Celery
REDIS_HOST=redis
REDIS_PORT=6379
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
# ---------------------------- Storage (Object Storage)
STORAGE_TYPE=S3
STORAGE_S3_BUCKET=${S3_BUCKET:?}
STORAGE_S3_PREFIX=storage
STORAGE_S3_REGION=ru-central1
STORAGE_S3_ENDPOINT_URL=https://storage.yandexcloud.net
STORAGE_S3_PRESIGN_EXPIRES=3600
# ---------------------------- Container Registry
YC_REGISTRY_ID=${REGISTRY_ID:?}
IMAGE_TAG=latest
# ---------------------------- OAuth callback URLs
OAUTH_BASE_URL=https://${DOMAIN:?}/api
OAUTH_REDIRECT_BASE_URL=https://${DOMAIN}
OAUTH_FRONTEND_REDIRECT_URL=https://${DOMAIN}
# ---------------------------- CORS (JSON for pydantic-settings list[str])
SERVER_CORS_ORIGINS=["https://${DOMAIN}"]
# ---------------------------- Session cookies (browser auth flow)
# HTTPS-terminated by nginx; frontend + API share \${DOMAIN}, so host-only
# Lax cookies are sufficient. Switch SAMESITE=none + set a domain if you
# split frontend and API across different sites.
SECURITY_COOKIE_SECURE=true
SECURITY_COOKIE_SAMESITE=lax
# ---------------------------- Bootstrap (needed by refresh-env.sh on deploys)
LOCKBOX_SECRET_ID=${LOCKBOX_SECRET_ID:?}
# ---------------------------- Logging
LOGGING_LEVEL=INFO
LOG_FILE=logs/app.log
ERROR_LOG_FILE=logs/errors.log
JSON_LOG_FILE=logs/structured.json
EOF
chown ubuntu:ubuntu "$REPO_DIR/.env.static"

# --- 5. /opt/leap/refresh-env.sh (Lockbox → .env + backend/config/*.json) -
cat > "$REPO_DIR/refresh-env.sh" <<'EOF'
#!/usr/bin/env bash
# Re-materialize Lockbox entries on disk:
#   regular keys                  -> /opt/leap/.env
#   keys prefixed FILE__<name>.X  -> /opt/leap/backend/config/<name>.X
set -euo pipefail

STATIC=/opt/leap/.env.static
ENV_OUT=/opt/leap/.env
CONFIG_DIR=/opt/leap/backend/config

# Pick up LOCKBOX_SECRET_ID from .env.static so cron/deploy can call us
# without setting any env vars.
if [ -z "${LOCKBOX_SECRET_ID:-}" ] && [ -f "$STATIC" ]; then
  # shellcheck disable=SC1090
  LOCKBOX_SECRET_ID=$(grep '^LOCKBOX_SECRET_ID=' "$STATIC" | cut -d= -f2-)
fi
LOCKBOX_ID="${1:-${LOCKBOX_SECRET_ID:?LOCKBOX_SECRET_ID not set and not in $STATIC}}"

mkdir -p "$CONFIG_DIR"
payload=$(yc lockbox payload get --id "$LOCKBOX_ID" --format json)

env_tmp=$(mktemp)
echo "$payload" \
  | jq -r '.entries[]
           | select(.key | startswith("FILE__") | not)
           | select(.text_value != null and .text_value != "")
           | "\(.key)=\(.text_value)"' \
  > "$env_tmp"
cat "$STATIC" "$env_tmp" > "$ENV_OUT"
chmod 600 "$ENV_OUT"
chown ubuntu:ubuntu "$ENV_OUT"
rm -f "$env_tmp"

keys=$(echo "$payload" | jq -r '.entries[] | select(.key | startswith("FILE__")) | .key')
while IFS= read -r key; do
  [ -z "$key" ] && continue
  filename=${key#FILE__}
  value=$(echo "$payload" | jq -r --arg k "$key" '.entries[] | select(.key == $k) | .text_value')
  if [ -n "$value" ] && [ "$value" != "null" ]; then
    target="$CONFIG_DIR/$filename"
    printf '%s\n' "$value" > "$target"
    chmod 600 "$target"
    chown ubuntu:ubuntu "$target"
    echo "[refresh-env] wrote $target"
  fi
done <<< "$keys"

echo "[refresh-env] .env + config/ updated from Lockbox $LOCKBOX_ID"
EOF
chmod 0750 "$REPO_DIR/refresh-env.sh"
chown ubuntu:ubuntu "$REPO_DIR/refresh-env.sh"

# --- 6. Materialize secrets ----------------------------------------------
LOCKBOX_SECRET_ID="${LOCKBOX_SECRET_ID:?}" bash "$REPO_DIR/refresh-env.sh"

# --- 7. nginx: HTTP-only until certbot succeeds --------------------------
cd "$REPO_DIR"
if [ ! -L /etc/letsencrypt/live/leap ]; then
  cp nginx/nginx.bootstrap.conf nginx/nginx.conf
else
  cp nginx/nginx.https.conf nginx/nginx.conf
fi

# --- 7a. External named volumes (protected from `docker compose down -v`) -
for vol in leap_postgres_data leap_redis_data leap_loki_data \
           leap_prometheus_data leap_grafana_data; do
  if ! docker volume inspect "$vol" >/dev/null 2>&1; then
    docker volume create "$vol"
    echo "[vm-init] created external volume $vol"
  fi
done

# --- 7b. Host-level logrotate safety net ---------------------------------
cat > /etc/logrotate.d/leap <<'EOF'
/opt/leap/backend/logs/*.log {
    weekly
    rotate 4
    maxsize 200M
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}

/opt/leap/backend/logs/*.json {
    weekly
    rotate 4
    maxsize 500M
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF

# --- 8. Pull images + start the stack ------------------------------------
sudo -u ubuntu docker compose pull
sudo -u ubuntu docker compose up -d \
  postgres redis api celery_worker celery_beat flower frontend \
  loki promtail grafana
sudo -u ubuntu docker compose up -d nginx

# --- 9. Let's Encrypt (needs DNS pointing at us) -------------------------
if [ ! -L /etc/letsencrypt/live/leap ]; then
  echo "[vm-init] waiting up to 5 min for http://$DOMAIN/api/v1/health/live ..."
  health_ok=0
  for _ in $(seq 1 60); do
    if curl -m5 -fsS "http://$DOMAIN/api/v1/health/live" >/dev/null 2>&1; then
      health_ok=1
      break
    fi
    sleep 5
  done

  if [ "$health_ok" != "1" ]; then
    echo "[vm-init] HTTP not ready — skipping certbot."
    echo "[vm-init] After 'dig +short $DOMAIN' returns this VM, re-run: make deploy-vm-init"
  else
    mkdir -p "$REPO_DIR/certbot"
    docker run --rm \
      -v /etc/letsencrypt:/etc/letsencrypt \
      -v "$REPO_DIR/certbot:/var/www/certbot" \
      certbot/certbot certonly --webroot -w /var/www/certbot \
        -d "$DOMAIN" --agree-tos -m "${CERT_EMAIL:?}" --non-interactive

    ln -sfn "/etc/letsencrypt/live/$DOMAIN" /etc/letsencrypt/live/leap

    # htpasswd: rm first — compose may have left an empty dir at this path.
    GRAFANA_PASSWORD=$(grep '^GRAFANA_PASSWORD=' "$REPO_DIR/.env" | cut -d= -f2-)
    rm -rf "$REPO_DIR/nginx/htpasswd"
    htpasswd -nbB admin "$GRAFANA_PASSWORD" > "$REPO_DIR/nginx/htpasswd"
    chmod 600 "$REPO_DIR/nginx/htpasswd"

    cp nginx/nginx.https.conf nginx/nginx.conf
    # --force-recreate is critical: nginx.conf is a bind-mount, and compose
    # doesn't detect file-content drift — without --force-recreate, the
    # already-running nginx keeps the old (bootstrap, HTTP-only) config in
    # memory and TLS handshake on :443 fails.
    sudo -u ubuntu docker compose up -d --no-deps --force-recreate nginx
  fi
fi

# --- 10. Cron: certbot renew + nightly pg_backup + redis_backup ----------
if ! crontab -l 2>/dev/null | grep -q certbot; then
  (crontab -l 2>/dev/null; echo "0 3 * * * docker run --rm -v /etc/letsencrypt:/etc/letsencrypt -v /opt/leap/certbot:/var/www/certbot certbot/certbot renew --quiet && docker exec leap_nginx nginx -s reload") | crontab -
fi
if ! crontab -l 2>/dev/null | grep -q pg_backup; then
  (crontab -l 2>/dev/null; echo "0 2 * * * bash /opt/leap/scripts/pg_backup.sh >> /var/log/leap-pg-backup.log 2>&1") | crontab -
fi
if ! crontab -l 2>/dev/null | grep -q redis_backup; then
  (crontab -l 2>/dev/null; echo "15 4 * * * bash /opt/leap/scripts/redis_backup.sh >> /var/log/leap-redis-backup.log 2>&1") | crontab -
fi

echo "[vm-init] $(date -Iseconds) done — https://$DOMAIN"
