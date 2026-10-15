#!/usr/bin/env bash
# Deploy the inactive API/frontend slot and switch nginx only after smoke checks.
# Run from the repository root on the production VM: scripts/deploy-blue-green.sh <image-tag>
set -Eeuo pipefail

IMAGE_TAG=${1:?Usage: scripts/deploy-blue-green.sh <image-tag|--rollback>}
if [ "$IMAGE_TAG" != --rollback ]; then
  export IMAGE_TAG
fi
cd "$(dirname "$0")/.."

active_dir=nginx/active
sudo install -d -o "$(id -u)" -g "$(id -g)" "$active_dir"

write_slot() {
  local slot=$1 api=api frontend=frontend
  local previous_frontend=frontend
  if [ "$slot" = green ]; then
    api=api_green
    frontend=frontend_green
    previous_frontend=frontend
  elif [ -f "$active_dir/confirmed-slot" ] && [ "$(cat "$active_dir/confirmed-slot")" = green ]; then
    previous_frontend=frontend_green
  fi
  local tmp
  tmp=$(mktemp "$active_dir/.slot.XXXXXX")
  # nginx variables are literal here.
  # shellcheck disable=SC2016
  printf 'set $api_upstream "http://%s:8000";\nset $frontend_upstream "http://%s:3000";\nset $previous_frontend_upstream "http://%s:3000";\nset $leap_slot "%s";\n' \
    "$api" "$frontend" "$previous_frontend" "$slot" > "$tmp"
  mv -f "$tmp" "$active_dir/slot.conf"
}

write_state() {
  local name=$1 value=$2 tmp
  tmp=$(mktemp "$active_dir/.state.XXXXXX")
  printf '%s\n' "$value" > "$tmp"
  mv -f "$tmp" "$active_dir/$name"
}

if [ ! -f "$active_dir/slot.conf" ]; then
  write_slot blue
fi
# nginx variable is literal.
# shellcheck disable=SC2016
if grep -Fq 'set $leap_slot "green";' "$active_dir/slot.conf"; then
  current=green
  target=blue
  grep -Fq 'http://api_green:8000' "$active_dir/slot.conf"
  grep -Fq 'http://frontend_green:3000' "$active_dir/slot.conf"
else
  # nginx variable is literal.
  # shellcheck disable=SC2016
  grep -Fq 'set $leap_slot "blue";' "$active_dir/slot.conf" || {
    echo "Unknown active API slot; refusing to deploy" >&2
    exit 1
  }
  current=blue
  target=green
  grep -Fq 'http://api:8000' "$active_dir/slot.conf"
  grep -Fq 'http://frontend:3000' "$active_dir/slot.conf"
fi
if [ ! -f "$active_dir/confirmed-slot" ]; then
  write_state confirmed-slot "$current"
fi
confirmed=$(cat "$active_dir/confirmed-slot")
case "$confirmed" in blue|green) ;; *) echo "Invalid confirmed slot" >&2; exit 1 ;; esac
if [ "$current" != "$confirmed" ]; then
  echo "Interrupted switch detected; restoring confirmed slot $confirmed" >&2
  write_slot "$confirmed"
  write_state rollback-slot none
  if docker exec leap_nginx test -d /etc/nginx/leap-active 2>/dev/null; then
    docker exec leap_nginx nginx -t && docker exec leap_nginx nginx -s reload
  fi
  exit 1
fi
if [ "$IMAGE_TAG" = --rollback ]; then
  rollback_slot=$(cat "$active_dir/rollback-slot" 2>/dev/null || true)
  if [ "$rollback_slot" != "$target" ]; then
    echo "No confirmed rollback slot $target; refusing to switch traffic" >&2
    exit 1
  fi
else
  # This slot is about to be overwritten; it is no longer a safe rollback
  # target until it passes the nginx smoke checks again.
  write_state rollback-slot none
fi
if [ "$target" = green ]; then
  target_api=api_green
  target_frontend=frontend_green
  target_container=leap_api_green
else
  target_api=api
  target_frontend=frontend
  target_container=leap_api
fi
echo "Deploying $IMAGE_TAG into $target; active slot is $current"

if [ "$IMAGE_TAG" != --rollback ]; then
  yc container registry configure-docker
  if [ -x /opt/leap/refresh-env.sh ]; then
    /opt/leap/refresh-env.sh
  fi
  docker compose pull "$target_api" "$target_frontend" celery_worker celery_cpu_worker celery_maintenance_worker celery_preview_worker celery_beat flower

  # Migrations must remain compatible with the active API until the switch and
  # with both API versions during the rollback window. Never let Compose
  # recreate the production database while starting this one-shot container.
  docker exec leap_postgres pg_isready -U postgres -d leap_platform
  docker compose run --rm --no-deps migrate
  docker compose up --wait --wait-timeout 300 --no-deps celery_preview_worker celery_cpu_worker celery_maintenance_worker celery_worker
  docker compose up --wait --wait-timeout 120 --no-deps celery_beat
  docker compose up -d --no-deps flower
  docker compose up --wait --wait-timeout 180 --no-deps "$target_api" "$target_frontend"
else
  docker exec "leap_${target_frontend}" node -e \
    "require('http').get('http://127.0.0.1:3000/login', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"
fi

# The API container healthcheck is liveness. Gate the switch on dependencies too.
docker exec "$target_container" python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=10)"

# The first blue/green deployment changes the nginx mount and recreates nginx
# once. Later deploys reload it in place, keeping existing connections alive.
nginx_backup=$(mktemp)
sudo cp nginx/nginx.conf "$nginx_backup"
if ! sudo test -f /etc/letsencrypt/live/leap/fullchain.pem; then
  domain_cert=$(sudo find /etc/letsencrypt/live -mindepth 2 -maxdepth 2 -name fullchain.pem -print -quit || true)
  if [ -n "$domain_cert" ]; then
    sudo ln -sfn "$(dirname "$domain_cert")" /etc/letsencrypt/live/leap
  fi
fi
if sudo test -f /etc/letsencrypt/live/leap/fullchain.pem; then
  sudo cp nginx/nginx.https.conf nginx/nginx.conf
  domain_url=$(sed -n 's/^OAUTH_FRONTEND_REDIRECT_URL=//p' .env.static | head -n 1)
  test -n "$domain_url"
  smoke_url=$domain_url
  smoke_resolve="${domain_url#https://}:443:127.0.0.1"
else
  sudo cp nginx/nginx.bootstrap.conf nginx/nginx.conf
  smoke_url=http://127.0.0.1
  smoke_resolve=
fi
if docker exec leap_nginx test -d /etc/nginx/leap-active 2>/dev/null; then
  if ! docker exec leap_nginx nginx -t; then
    sudo cp "$nginx_backup" nginx/nginx.conf
    rm -f "$nginx_backup"
    exit 1
  fi
  if ! docker exec leap_nginx nginx -s reload; then
    sudo cp "$nginx_backup" nginx/nginx.conf
    docker exec leap_nginx nginx -t && docker exec leap_nginx nginx -s reload
    rm -f "$nginx_backup"
    exit 1
  fi
else
  if ! docker compose up -d --no-deps --force-recreate nginx; then
    sudo cp "$nginx_backup" nginx/nginx.conf
    docker compose up -d --no-deps --force-recreate nginx
    rm -f "$nginx_backup"
    exit 1
  fi
fi
rm -f "$nginx_backup"

# Apply monitoring changes while the old slot still serves traffic. A failure
# here marks the job red without publishing the new application version.
if [ "$IMAGE_TAG" != --rollback ]; then
  # Monitoring must not recreate Redis (or any other application dependency)
  # between the readiness gate and the nginx smoke check.
  docker compose up -d --no-deps loki
  docker compose up -d --no-deps --force-recreate prometheus celery_exporter promtail grafana
fi

switch_started=0
committed=0
restore_slot() {
  if [ "$switch_started" -eq 1 ] && [ "$committed" -eq 0 ]; then
    echo "Smoke check failed; restoring $current" >&2
    write_slot "$current"
    docker exec leap_nginx nginx -t && docker exec leap_nginx nginx -s reload
  fi
}
trap restore_slot EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP

switch_started=1
write_slot "$target"
docker exec leap_nginx nginx -t
docker exec leap_nginx nginx -s reload
smoke_slot() {
  local path=$1 headers status slot
  local -a curl_args=(--noproxy '*' -sS --max-time 15 -D - -o /dev/null)
  if [ -n "$smoke_resolve" ]; then
    curl_args+=(--resolve "$smoke_resolve")
  fi
  if ! headers=$(curl "${curl_args[@]}" "$smoke_url$path"); then
    echo "Smoke $path: curl failed" >&2
    return 1
  fi
  status=$(awk '/^HTTP\// { value=$2; gsub(/\r/, "", value) } END { print value }' <<< "$headers")
  slot=$(awk 'tolower($1) == "x-leap-slot:" { gsub(/\r/, "", $2); value=$2 } END { print value }' <<< "$headers")
  if [ "$status" != 200 ] || [ "$slot" != "$target" ]; then
    echo "Smoke $path: HTTP ${status:-none}, X-Leap-Slot ${slot:-none}; expected 200/$target" >&2
    return 1
  fi
}
smoke_attempts=${LEAP_SMOKE_ATTEMPTS:-20}
for attempt in $(seq 1 "$smoke_attempts"); do
  if smoke_slot /api/v1/health/ready && smoke_slot /login; then
    break
  fi
  if [ "$attempt" -eq "$smoke_attempts" ]; then
    echo "New slot did not pass nginx smoke checks" >&2
    exit 1
  fi
  sleep 1
done
write_state rollback-slot "$current"
write_state confirmed-slot "$target"
committed=1
echo "Active slot: $target ($IMAGE_TAG); $current is available for rollback"
docker compose ps || true
