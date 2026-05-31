# LEAP — production deployment

End-to-end deployment to Yandex Cloud in **one Make target**:

```bash
make deploy
```

That runs `terraform apply` which creates everything: VM, Object Storage,
Container Registry, Lockbox, DNS zone, IAM. The VM bootstraps itself via
cloud-init: docker stack, certbot, Grafana, the works.

Most operational commands are Make targets — see `make help`.

---

## 1. One-time prerequisites (you, manually)

These are unavoidable because they involve external accounts.

| Account / service | What you need | Time |
|---|---|---|
| **Yandex Cloud** | Working account with billing enabled | ~10 min |
| **`yc` CLI** | Installed and `yc init` complete | 2 min |
| **`terraform` ≥ 1.5** | `brew install terraform` (or apt) | 1 min |
| **`gh` CLI** | `brew install gh && gh auth login` (for `make gh-secrets`) | 2 min |
| **SSH keypair** | `ssh-keygen -t ed25519 -C "leap-prod" -f ~/.ssh/id_ed25519` if you don't have one | 1 min |
| **Domain** | Owned at reg.ru (in our case `leap-platform.ru`) | already done |
| **Zoom OAuth app** | Marketplace → Server-to-Server OAuth → client_id + secret | ~10 min |
| **Google OAuth client** | Cloud Console → OAuth client (Web) → download `client_secrets.json` | ~10 min |
| **VK app** | vk.com/apps → Standalone app → app_id + secure key | ~5 min |
| **Yandex OAuth client** | oauth.yandex.com/client/new → client_id + secret | ~5 min |
| **Fireworks** | fireworks.ai/account/api-keys | ~3 min |
| **DeepSeek** | platform.deepseek.com/api_keys | ~3 min |

Save the OAuth credentials into `backend/config/oauth_*.json` and AI keys
into `backend/config/{fireworks,deepseek}_creds.json` — those files are
gitignored and consumed verbatim by Terraform. Templates are in
`backend/config/examples/`.

**Callback URI for every OAuth provider:**
`https://<your-domain>/api/v1/oauth/<provider>/callback`

Register that URI in each provider's dashboard (otherwise OAuth returns
`redirect_uri_mismatch`).

---

## 2. One-time Terraform setup

### Provider mirror

Yandex Cloud's mirror at `terraform-mirror.yandexcloud.net` carries the YC
provider plus all `hashicorp/*` providers. Configure once:

```bash
cat > ~/.terraformrc <<'EOF'
provider_installation {
  network_mirror {
    url     = "https://terraform-mirror.yandexcloud.net/"
    include = ["registry.terraform.io/*/*"]
  }
  direct {
    exclude = ["registry.terraform.io/*/*"]
  }
}
EOF
```

The wildcard `*/*` is required — without it `terraform init` will try to
reach the (unreachable from Russia) `registry.terraform.io` for the
auxiliary `hashicorp/random` and `hashicorp/external` providers.

### Fill `terraform/terraform.tfvars`

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars
```

Required values:

```hcl
yc_cloud_id      = "..."   # yc config get cloud-id
yc_folder_id     = "..."   # yc config get folder-id

domain           = "leap-platform.ru"
cert_email       = "you@example.com"
ssh_public_key   = "ssh-ed25519 AAAA..."  # cat ~/.ssh/id_ed25519.pub
ssh_allowed_cidr = ["1.2.3.4/32"]         # curl -4 ifconfig.me  + /32

github_owner = "GordeyZuev"
github_repo  = "ZoomUploader"

# OAuth + AI — read from existing files in backend/config/
oauth_zoom_json    = file("../backend/config/oauth_zoom.json")
oauth_youtube_json = file("../backend/config/oauth_google.json")
oauth_vk_json      = file("../backend/config/oauth_vk.json")
oauth_yadisk_json  = file("../backend/config/oauth_yandex_disk.json")

fireworks_api_key    = jsondecode(file("../backend/config/fireworks_creds.json")).api_key
fireworks_account_id = jsondecode(file("../backend/config/fireworks_creds.json")).account_id
deepseek_api_key     = jsondecode(file("../backend/config/deepseek_creds.json")).api_key
```

Defaults for everything else (VM size, region, DNS zone) are sensible.

---

## 3. Deploy

```bash
make init       # ~30 sec  — downloads providers from YC mirror
make plan       # preview (should show "Plan: ~22 to add, 0 to change")
make deploy     # ~5 min   — creates all YC resources

make gh-secrets # push Terraform outputs to GitHub Actions secrets
```

`make deploy` writes a summary at the end:

```
vm_public_ip = "1.2.3.4"
domain_url   = "https://leap-platform.ru"
ns_servers   = ["ns1.yandexcloud.net", "ns2.yandexcloud.net"]
next_steps   = "..."
```

---

## 4. Delegate DNS at reg.ru

In the reg.ru control panel for your domain → DNS → switch NS records to
the two values from `make status` (or `terraform output -json ns_servers`).
Propagation: 1–24 hours. Check progress with
`dig +short NS leap-platform.ru`.

---

## 5. Watch the VM bootstrap

```bash
make logs        # tail /var/log/leap-bootstrap.log on the VM
```

You should see, in order:

1. yc CLI installed, registry configured
2. `[refresh-env] .env + config/ files updated from Lockbox`
3. `docker compose pull` — pulls images from cr.yandex
4. `docker compose up -d postgres redis api …`
5. wait for HTTP health → certbot → cert obtained
6. nginx reloaded with HTTPS config + htpasswd generated
7. `[bootstrap] LEAP stack up at https://leap-platform.ru`

Then:

```bash
make smoke-test  # curl /api/v1/health
make grafana-pw  # admin password for /grafana/
```

---

## 6. Continuous deployment

After `make gh-secrets`, every push to `main` triggers
`.github/workflows/deploy.yml`:

1. Build `backend/` and `frontend/` images
2. Push to `cr.yandex/<registry-id>/leap-{backend,frontend}:<sha>` and `:latest`
3. SSH to the VM:  `git pull` → `refresh-env.sh` → `docker compose pull && up -d`
4. ~3 min from push to live.

PRs run `.github/workflows/ci.yml`: `ruff` + `ty` + backend `pytest tests/unit` + frontend `pnpm lint && pnpm build`.

---

## Where do environment variables come from?

Three layers, merged into `/opt/leap/.env` on the VM:

| Layer | Source | Examples | When to update |
|---|---|---|---|
| **Static** | `terraform/cloud-init.yaml.tftpl` `.env.static` block | `DATABASE_HOST=postgres`, `STORAGE_S3_REGION=ru-central1`, `OAUTH_BASE_URL=https://…/api`, `IMAGE_TAG=latest` | Edit the template + `terraform apply` |
| **Lockbox secrets** | `yandex_lockbox_secret_version` in `terraform/modules/secrets/main.tf` | `DB_PASSWORD`, `SECURITY_JWT_SECRET_KEY`, `SECURITY_ENCRYPTION_KEY`, `STORAGE_S3_ACCESS_KEY_ID`, `OAUTH_*_CLIENT_ID/SECRET`, `GRAFANA_PASSWORD` | Edit Terraform vars + `terraform apply`, OR rotate via `yc lockbox secret add-version` |
| **Config files** | `FILE__<name>.json` entries in Lockbox → materialized to `backend/config/` on the VM by `refresh-env.sh` | `backend/config/oauth_zoom.json`, `fireworks_creds.json`, `deepseek_creds.json`, etc. | Edit local file → `terraform apply` (re-uploads to Lockbox) |

To inspect / change without re-running Terraform:

```bash
yc lockbox payload get --id $(terraform -chdir=terraform output -raw lockbox_secret_id) --format json | jq

# After updating: bump version on VM (no compose restart needed if value is read fresh)
make refresh-env
```

Full env var reference: [backend/.env.example](../../.env.example).

---

## Operational commands (cheat sheet)

```bash
make status        # everything Terraform knows about the deploy
make ssh           # ssh ubuntu@<vm-ip>
make logs          # tail bootstrap log
make app-logs      # tail docker compose logs api celery_worker frontend
make refresh-env   # pull latest secrets from Lockbox + compose up -d
make smoke-test    # GET /api/v1/health
make grafana-pw    # print Grafana admin password
```

Postgres backup (run as cron on the VM):

```bash
docker exec leap_postgres pg_dump -U postgres leap_platform | gzip > backup.sql.gz
yc storage cp backup.sql.gz s3://leap-backups/postgres/$(date +%Y%m%d).sql.gz
```

---

## Local development (no Yandex Cloud)

```bash
make docker-up                                                # postgres + redis only
docker compose -f docker-compose.dev.yml up -d minio          # optional S3 via MinIO

cd backend
cp .env.example .env
$EDITOR .env       # set STORAGE_TYPE=LOCAL, or S3 with MinIO endpoint
uv sync
uv run alembic upgrade head
make api           # uvicorn on :8000

cd ../frontend
pnpm install && pnpm dev   # :3000
```

For MinIO-backed S3 in dev, set in `.env`:

```env
STORAGE_TYPE=S3
STORAGE_S3_BUCKET=leap-dev
STORAGE_S3_ENDPOINT_URL=http://localhost:9000
STORAGE_S3_ACCESS_KEY_ID=minioadmin
STORAGE_S3_SECRET_ACCESS_KEY=minioadmin
```

MinIO console: http://localhost:9001 (minioadmin / minioadmin).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `terraform init` → "Invalid provider registry host" | `~/.terraformrc` missing wildcard or absent | Re-check the mirror block in §2 |
| certbot HTTP-01 challenge fails | NS delegation hasn't propagated yet | `dig +short NS <domain>` — wait until it returns yandexcloud.net, then SSH in and re-run `sudo bash /opt/leap/bootstrap.sh` |
| OAuth callback returns `redirect_uri_mismatch` | Production URI not whitelisted in provider's console | Add `https://<domain>/api/v1/oauth/<provider>/callback` to each provider's allowed callback list |
| `docker compose pull` fails on VM | YC service account missing `images.puller` role | Re-run `terraform apply` — the IAM module enforces it |
| Grafana login fails | Forgot the auto-generated password | `make grafana-pw` |
| Want to rotate a secret without Terraform | — | `yc lockbox secret add-version --id <id> --payload-from-file=...` then `make refresh-env` |

---

## Architecture (high level)

```
                              users.example.com
                                     │
                                     ▼
              ┌───────────────── nginx :443 ──────────────────────┐
              │     /api/ → api  /flower/ /grafana/    / → frontend │
              └──────────────────────────┬──────────────────────────┘
                                         ▼
                                ┌─────────────────┐
                                │  api (uvicorn)  │
                                └────────┬────────┘
                                         ▼
                          ┌──────────────┴──────────────┐
                          ▼                              ▼
                ┌──────────────────┐              ┌───────────────┐
                │ postgres + redis │              │ celery_worker │
                │   (Docker on VM) │              │   + beat      │
                └──────────────────┘              └───────┬───────┘
                                                          ▼
                                       ┌──────────────────────────────┐
                                       │   Yandex Object Storage      │
                                       │   storage.yandexcloud.net    │
                                       └──────────────────────────────┘
                                                  ▲
                                                  │ presigned GET (Range)
                                       <video src="..." /> ← browser
```

| Where | What |
|---|---|
| Object Storage bucket `leap-platform-storage` | Source/processed videos, audio, transcriptions, subtitles, thumbnails |
| Object Storage bucket `leap-backups` | `pg_dump` archives (30-day lifecycle) |
| Postgres on the VM | All metadata, recordings, OAuth tokens (encrypted), Celery Beat schedule |
| Lockbox `leap-prod-secrets` | All production credentials, fetched at boot |
| VM disk `backend/storage/temp/` | Ephemeral FFmpeg/ASR scratch — Beat-cleaned hourly |
| VM disk `backend/logs/` | Application logs → Promtail → Loki → Grafana |
