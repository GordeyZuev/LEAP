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

# --------------------------------------------------------------------------
# 1. Packages
# --------------------------------------------------------------------------
# Ubuntu stock repo ships `docker.io` but NOT `docker-compose-plugin` — the
# plugin lives in Docker's official apt repo paired with docker-ce. Use the
# get.docker.com convenience script: it adds the right repo and installs
# docker-ce + the compose plugin in one shot. Idempotent: it re-installs the
# latest each time but doesn't break a working setup.
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git jq curl ca-certificates gnupg apache2-utils

# A prior run may have installed Ubuntu's `docker.io` (no compose plugin).
# It conflicts with `docker-ce` (Docker official) on systemd units. Purge
# before get.docker.com so the official package owns the docker.service unit.
if dpkg -l docker.io 2>/dev/null | grep -q '^ii'; then
  apt-get remove -y --purge docker.io containerd 2>&1 | tail -3
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable --now docker
usermod -aG docker ubuntu || true

# --------------------------------------------------------------------------
# 2. yc CLI (the VM service account is attached, so it authenticates
#    automatically via the instance metadata service)
# --------------------------------------------------------------------------
if ! command -v yc >/dev/null 2>&1; then
  curl -sSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh \
    | bash -s -- -i /usr/local -n
  ln -sf /usr/local/bin/yc /usr/bin/yc
fi
yc config set folder-id "${FOLDER_ID:?}" || true
yc container registry configure-docker

# Make `docker pull cr.yandex/...` work for the ubuntu user too.
mkdir -p /home/ubuntu/.docker
cp -f /root/.docker/config.json /home/ubuntu/.docker/config.json 2>/dev/null || true
chown -R ubuntu:ubuntu /home/ubuntu/.docker

# --------------------------------------------------------------------------
# 3. Clone (or update) the repo into /opt/leap
# --------------------------------------------------------------------------
mkdir -p "$REPO_DIR"
chown ubuntu:ubuntu "$REPO_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
  # /opt/leap may contain stray files from a prior partial cloud-init —
  # clone into /tmp (ubuntu-writable) and merge over the existing dir.
  tmpclone=$(sudo -u ubuntu mktemp -d /tmp/leap-clone.XXXXXX)
  sudo -u ubuntu git clone --branch "$BRANCH" "$REPO_URL" "$tmpclone"
  sudo -u ubuntu cp -rT "$tmpclone/." "$REPO_DIR/"
  rm -rf "$tmpclone"
else
  sudo -u ubuntu git -C "$REPO_DIR" fetch --depth=1 origin "$BRANCH"
  sudo -u ubuntu git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
fi

# --------------------------------------------------------------------------
# 4. Write .env.static (values that never change between deploys)
# --------------------------------------------------------------------------
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
OAUTH_FRONTEND_REDIRECT_URL=https://${DOMAIN}/auth/callback
# ---------------------------- Logging
LOGGING_LEVEL=INFO
LOG_FILE=logs/app.log
ERROR_LOG_FILE=logs/errors.log
JSON_LOG_FILE=logs/structured.json
EOF
chown ubuntu:ubuntu "$REPO_DIR/.env.static"

# --------------------------------------------------------------------------
# 5. Install /opt/leap/refresh-env.sh (Lockbox -> .env + backend/config/*.json)
# --------------------------------------------------------------------------
cat > "$REPO_DIR/refresh-env.sh" <<'EOF'
#!/usr/bin/env bash
# Re-materialize all Lockbox entries on disk:
#   - regular keys                      -> /opt/leap/.env
#   - keys prefixed FILE__<name>.json   -> /opt/leap/backend/config/<name>.json
set -euo pipefail

LOCKBOX_ID="${1:-$LOCKBOX_SECRET_ID}"
ENV_OUT=/opt/leap/.env
STATIC=/opt/leap/.env.static
CONFIG_DIR=/opt/leap/backend/config

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

# --------------------------------------------------------------------------
# 6. Materialize secrets
# --------------------------------------------------------------------------
LOCKBOX_SECRET_ID="${LOCKBOX_SECRET_ID:?}" bash "$REPO_DIR/refresh-env.sh"

# --------------------------------------------------------------------------
# 7. nginx: HTTP-only mode if we don't have a cert yet
# --------------------------------------------------------------------------
cd "$REPO_DIR"
if [ ! -L /etc/letsencrypt/live/leap ]; then
  cp nginx/nginx.bootstrap.conf nginx/nginx.conf
else
  cp nginx/nginx.https.conf nginx/nginx.conf
fi

# --------------------------------------------------------------------------
# 8. Pull images + start the stack
# --------------------------------------------------------------------------
sudo -u ubuntu docker compose pull
sudo -u ubuntu docker compose up -d \
  postgres redis api celery_worker celery_beat flower frontend \
  loki promtail grafana
sudo -u ubuntu docker compose up -d nginx

# --------------------------------------------------------------------------
# 9. Let's Encrypt (only if no cert yet; needs DNS already pointing at us)
# --------------------------------------------------------------------------
if [ ! -L /etc/letsencrypt/live/leap ]; then
  echo "[vm-init] waiting up to 5 min for http://$DOMAIN/api/v1/health ..."
  health_ok=0
  for _ in $(seq 1 60); do
    if curl -m5 -fsS "http://$DOMAIN/api/v1/health" >/dev/null 2>&1; then
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

    # htpasswd for /flower and /grafana basic auth
    GRAFANA_PASSWORD=$(grep '^GRAFANA_PASSWORD=' "$REPO_DIR/.env" | cut -d= -f2-)
    htpasswd -nbB admin "$GRAFANA_PASSWORD" > "$REPO_DIR/nginx/htpasswd"
    chmod 600 "$REPO_DIR/nginx/htpasswd"

    cp nginx/nginx.https.conf nginx/nginx.conf
    sudo -u ubuntu docker compose up -d --no-deps nginx
  fi
fi

# --------------------------------------------------------------------------
# 10. Cron: certbot renew + nightly pg_backup
# --------------------------------------------------------------------------
if ! crontab -l 2>/dev/null | grep -q certbot; then
  (crontab -l 2>/dev/null; echo "0 3 * * * docker run --rm -v /etc/letsencrypt:/etc/letsencrypt -v /opt/leap/certbot:/var/www/certbot certbot/certbot renew --quiet && docker exec leap_nginx nginx -s reload") | crontab -
fi
if ! crontab -l 2>/dev/null | grep -q pg_backup; then
  (crontab -l 2>/dev/null; echo "0 2 * * * bash /opt/leap/scripts/pg_backup.sh >> /var/log/leap-pg-backup.log 2>&1") | crontab -
fi

echo "[vm-init] $(date -Iseconds) done — https://$DOMAIN"
