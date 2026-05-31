# Nginx reverse proxy

This directory contains the nginx config used in production by the `nginx`
service in `docker-compose.yml`.

## Files

| File | When it's used |
|---|---|
| `nginx.conf` | What docker-compose mounts. Initially a copy of `nginx.bootstrap.conf` (HTTP only). After certbot succeeds, cloud-init replaces it with `nginx.https.conf`. |
| `nginx.bootstrap.conf` | HTTP-only config; serves the ACME `/.well-known/` challenge so certbot can issue the first cert. |
| `nginx.https.conf` | Final production config (HTTPS with HSTS, basic auth for `/flower` and `/grafana`). |
| `htpasswd` | **Not in repo** — generated on the VM by the cloud-init script using the Grafana admin password from Lockbox. |

## How `terraform apply` sets this up

Cloud-init (see `terraform/cloud-init.yaml.tftpl`) does the swap automatically:

1. First boot: `nginx.conf` ← `nginx.bootstrap.conf` (HTTP)
2. Stack starts; `/api/v1/health` becomes reachable.
3. `certbot certonly --webroot` requests the cert.
4. `nginx.conf` ← `nginx.https.conf`, then `docker compose up -d --no-deps nginx`.
5. Cron job (also installed by bootstrap) renews the cert nightly.

If something goes wrong, manual steps are documented in `backend/docs/guides/DEPLOYMENT.md`.
