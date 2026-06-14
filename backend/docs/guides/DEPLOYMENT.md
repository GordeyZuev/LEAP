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
| **AssemblyAI** | assemblyai.com/app/account | ~3 min |
| **DeepSeek** | platform.deepseek.com/api_keys | ~3 min |

Save the OAuth credentials into `backend/config/oauth_*.json` and AI keys
into `backend/config/{assemblyai,deepseek}_creds.json` — those files are
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

assemblyai_api_key = jsondecode(file("../backend/config/assemblyai_creds.json")).api_key
deepseek_api_key   = jsondecode(file("../backend/config/deepseek_creds.json")).api_key
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
| **Config files** | `FILE__<name>.json` entries in Lockbox → materialized to `backend/config/` on the VM by `refresh-env.sh` | `backend/config/oauth_zoom.json`, `assemblyai_creds.json`, `deepseek_creds.json`, etc. | Edit local file → `terraform apply` (re-uploads to Lockbox) |

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
make deploy-status        # everything Terraform knows about the deploy
make deploy-ssh           # ssh ubuntu@<vm-ip>
make deploy-logs          # tail bootstrap log
make deploy-app-logs      # tail docker compose logs api celery_worker frontend
make deploy-refresh-env   # pull latest secrets from Lockbox + compose up -d
make deploy-smoke-test    # GET /api/v1/health/ready
make deploy-grafana-pw    # print Grafana admin password

# Backups
make deploy-backup-pg     # ad-hoc pg_dump → s3://leap-backups/postgres/
make deploy-backup-redis  # ad-hoc Redis RDB → s3://leap-backups/redis/
make deploy-safe-down     # stop services WITHOUT wiping volumes (no -v)
```

## Volume safety & recovery

Critical data lives in named volumes flagged `external: true`. The `down -v`
flag of `docker compose` only removes compose-owned volumes, so external
volumes survive deliberate or accidental teardowns. Survivors:

| Volume                 | Holds                          | Survives `down` | Survives `down -v` | Survives host reboot |
| ---------------------- | ------------------------------ | --------------- | ------------------ | -------------------- |
| `leap_postgres_data`   | PostgreSQL data dir            | ✓               | ✓                  | ✓                    |
| `leap_redis_data`      | Redis AOF                      | ✓               | ✓                  | ✓                    |
| `leap_loki_data`       | Loki TSDB cache (rebuildable)  | ✓               | ✓                  | ✓ (cache rebuilt from S3) |
| `leap_prometheus_data` | Prometheus TSDB (30d)          | ✓               | ✓                  | ✓                    |
| `leap_grafana_data`    | Dashboards / users / prefs     | ✓               | ✓                  | ✓                    |
| `./backend/logs`       | Bind mount, host filesystem    | ✓               | ✓                  | ✓                    |

**Fresh host bootstrap:** `scripts/vm-init.sh` creates the volumes
idempotently. For an out-of-band first run:

```bash
docker volume create leap_postgres_data leap_redis_data \
                     leap_loki_data leap_prometheus_data leap_grafana_data
```

**To deliberately wipe a volume:**

```bash
docker compose stop postgres        # stop the service holding it
docker volume rm leap_postgres_data
docker volume create leap_postgres_data
docker compose start postgres
```

## VM durability

The VM itself is replaceable, but stateful data must not be. Three layers:

| Layer | Resource | What it protects against |
|---|---|---|
| **Static reserved IP** | `yandex_vpc_address.main` in compute module | VM recreate → DNS stays valid (same IP) |
| **Persistent secondary disk** | `yandex_compute_disk.data` with `auto_delete = false` + `lifecycle.prevent_destroy` | VM recreate → docker volumes stay (postgres, redis, loki, prometheus, grafana live there) |
| **Instance lifecycle** | `yandex_compute_instance.vm` with `prevent_destroy = true` + `ignore_changes = [metadata, image_id]` | Accidental destroy/replace blocked; Ubuntu / cloud-init changes do not force recreation |

### What survives a VM recreate

| Asset | Where | Survives? |
| --- | --- | --- |
| Postgres data | `leap_postgres_data` on secondary disk | ✓ |
| Redis AOF + result backend | `leap_redis_data` on secondary disk | ✓ |
| Loki TSDB cache (chunks already in S3) | `leap_loki_data` on secondary disk | ✓ |
| Prometheus TSDB | `leap_prometheus_data` on secondary disk | ✓ |
| Grafana dashboards/prefs | `leap_grafana_data` on secondary disk | ✓ |
| Recordings media | `s3://leap-platform-storage/` | ✓ (external) |
| pg + redis backups | `s3://leap-backups/` | ✓ (external) |
| Loki chunks + index | `s3://leap-logs/` | ✓ (external) |

### Operational consequences of `prevent_destroy`

Once the `lifecycle` block is enabled on `yandex_compute_instance.vm`:

| Action | Behaviour |
| --- | --- |
| Change `var.vm_cores` / `vm_memory_gb` | in-place update, no recreate |
| Change `var.vm_image_family` (Ubuntu) | Terraform ignores (`ignore_changes = boot_disk[0]…`). Upgrade Ubuntu via `apt-get` on the live VM instead. |
| Change `cloud_init` template | Terraform ignores (`ignore_changes = metadata`). To apply: `make deploy-vm-init` re-runs the script on the live VM. |
| Change `var.vm_disk_gb` (boot disk size) | Forces replacement → blocked by `prevent_destroy`. |
| `make deploy-destroy` | Blocked. To intentionally destroy: comment out `prevent_destroy`, apply, then restore the block. |

This is **intentional friction** on destructive operations. Cost: 30 seconds of manual editing when you actually mean to destroy. Benefit: no more silent VM recreates.

### Replacing the VM intentionally (rare)

1. SSH in, `pg_backup.sh` + `redis_backup.sh` ad-hoc.
2. Locally: comment out `lifecycle { prevent_destroy = true }` in `terraform/modules/compute/main.tf`, `terraform apply` — VM is destroyed, new VM comes up with the **same IP** and **same data disk** (both `prevent_destroy`).
3. Cloud-init runs `vm-init.sh`, which mounts the existing `/var/lib/docker/volumes` from the data disk, then `docker compose up -d` finds all volumes populated and starts everything as before.
4. Restore `prevent_destroy` block, commit.

## Backups

| What       | Schedule          | Script                       | Destination                  |
| ---------- | ----------------- | ---------------------------- | ---------------------------- |
| Postgres   | 02:00 UTC daily   | `scripts/pg_backup.sh`       | `s3://leap-backups/postgres/`|
| Redis      | 04:15 UTC daily   | `scripts/redis_backup.sh`    | `s3://leap-backups/redis/`   |
| Loki logs  | continuous        | Loki S3 backend (TSDB chunks)| `s3://${LOKI_S3_BUCKET}/`    |

Cron entries are installed by `scripts/vm-init.sh`. Re-run
`make deploy-vm-init` after editing the script to refresh the crontab.

**Restoring Postgres** (point-in-time-recovery is out of scope; this is a
full dump restore):

```bash
yc storage s3 cp s3://leap-backups/postgres/leap_<TS>.sql.gz - | gunzip \
  | docker exec -i leap_postgres psql -U postgres leap_platform
```

**Restoring Redis:**

```bash
docker compose stop redis
yc storage s3 cp s3://leap-backups/redis/leap_redis_<TS>.rdb.gz - | gunzip \
  | docker exec -i leap_redis tee /data/dump.rdb >/dev/null
docker compose start redis
```

## Loki recovery on a new host

Because Loki chunks + index live in Object Storage (`LOKI_S3_BUCKET`), a new
VM can read the full history with zero migration:

```bash
# On the new host, after vm-init.sh + docker compose up -d.
# Grafana → Explore → Loki: query for "last 30d" — historical logs appear
# as Loki rebuilds the local TSDB cache from the S3 chunks.
```

The `leap_loki_data` named volume only holds the local TSDB shipper buffer
and compactor working dir (≤ 100 MB, rebuildable). Losing it is a no-op.

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
| certbot HTTP-01 challenge fails | NS delegation hasn't propagated yet | `dig +short NS <domain>` — wait until it returns yandexcloud.net, then re-run `make deploy-vm-init` (idempotent; will only redo the cert step) |
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
