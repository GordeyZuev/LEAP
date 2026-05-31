# Nginx reverse proxy

This directory contains the nginx config used in production by the `nginx`
service in `docker-compose.yml`.

## Files

| File | When it's used |
|---|---|
| `nginx.conf` | **Runtime artifact — gitignored, not committed.** Docker compose mounts it. Owned by `scripts/vm-init.sh`: initially a copy of `nginx.bootstrap.conf` (HTTP only), after certbot succeeds it's replaced with `nginx.https.conf`. Kept out of git so deploys (`git reset --hard`) don't overwrite the HTTPS version with the HTTP-only bootstrap one. |
| `nginx.bootstrap.conf` | HTTP-only config; serves the ACME `/.well-known/` challenge so certbot can issue the first cert. |
| `nginx.https.conf` | Final production config (HTTPS with HSTS, basic auth for `/flower` and `/grafana`). |
| `htpasswd` | **Not in repo** — generated on the VM by `scripts/vm-init.sh` using the Grafana admin password from Lockbox. |

## How `make deploy-vm-init` sets this up

`scripts/vm-init.sh` (invoked over SSH by `make deploy-vm-init`, and also by
`terraform/cloud-init.yaml.tftpl` on first boot via `systemd-run`) does the
swap automatically:

1. First boot: `nginx.conf` ← `nginx.bootstrap.conf` (HTTP)
2. Stack starts; `/api/v1/health` becomes reachable.
3. `certbot certonly --webroot` requests the cert.
4. `nginx.conf` ← `nginx.https.conf`, then `docker compose up -d --no-deps --force-recreate nginx`.
5. Cron job (also installed by the script) renews the cert nightly.

If something goes wrong, re-run `make deploy-vm-init` — it's idempotent and
re-applies the HTTPS swap whenever a Let's Encrypt cert is already present.
