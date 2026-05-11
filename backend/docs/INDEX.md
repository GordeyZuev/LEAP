# Documentation Index

**Production-Ready Multi-tenant SaaS for Video Processing**

---

## Layout

| Path | Contents |
|------|----------|
| **[guides/](guides/)** | How-to guides: deployment, OAuth, templates, Celery, integrations (Zoom, VK, yt-dlp, …) |
| **[archive/](archive/)** | Thesis plan and other historical material (not runbooks) |
| **[dev_notes/](dev_notes/)** | Drafts, TODOs, internal notes |
| **This folder** | Core reference: API/tech (`TECHNICAL.md`), ADRs, DB design, architecture schemas, changelog |

---

## Quick start

1. [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) — setup (dev → production)
2. [guides/OAUTH.md](guides/OAUTH.md) — YouTube, VK, Zoom credentials
3. [TECHNICAL.md](TECHNICAL.md) — REST API and modules

---

## Architecture & design

- [ARCHITECTURE_SCHEMAS.md](ARCHITECTURE_SCHEMAS.md) — statuses, run/pause, credentials, configs (diagrams)
- [ADR_OVERVIEW.md](ADR_OVERVIEW.md) — Architecture Decision Records
- [ADR_FEATURES.md](ADR_FEATURES.md) — feature-specific ADRs
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) — schema & migrations
- [TECHNICAL.md](TECHNICAL.md) — full technical reference

### Academic / talks (archive)

- [archive/PLAN.md](archive/PLAN.md) — thesis plan

---

## Guides ([guides/](guides/))

**Templates & automation**

- [guides/TEMPLATES.md](guides/TEMPLATES.md)
- [guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md](guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md)
- [guides/JINJA_METADATA_TEMPLATES.md](guides/JINJA_METADATA_TEMPLATES.md) — Jinja2 variables, precomputed date strings (owner TZ), preview API, migrations 018–019
- [guides/AUTOMATION_CELERY_BEAT.md](guides/AUTOMATION_CELERY_BEAT.md)

**Quotas & admin**

- [guides/QUOTA_AND_ADMIN_API.md](guides/QUOTA_AND_ADMIN_API.md)

**Credentials & platforms**

- [guides/OAUTH.md](guides/OAUTH.md)
- [guides/CREDENTIAL_SECURITY.md](guides/CREDENTIAL_SECURITY.md)
- [guides/VK_INTEGRATION.md](guides/VK_INTEGRATION.md)
- [guides/VK_POLICY_UPDATE_2026.md](guides/VK_POLICY_UPDATE_2026.md)
- [guides/ZOOM_CREDS_GUIDE.md](guides/ZOOM_CREDS_GUIDE.md)

**Processing & workers**

- [guides/FIREWORKS_BATCH_API.md](guides/FIREWORKS_BATCH_API.md)
- [guides/BATCH_TESTING.md](guides/BATCH_TESTING.md)
- [guides/CELERY_WORKERS_GUIDE.md](guides/CELERY_WORKERS_GUIDE.md)
- [guides/CELERY_ASYNCIO_TECHNICAL.md](guides/CELERY_ASYNCIO_TECHNICAL.md)
- [hidden/ASR_MODELS_DEEP_DIVE.md](hidden/ASR_MODELS_DEEP_DIVE.md) — подробный разбор моделей ASR (черновик / внутренняя заметка)

**Storage & ingestion**

- [guides/STORAGE_STRUCTURE.md](guides/STORAGE_STRUCTURE.md)
- [guides/MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](guides/MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md) — short/broken video: `supported_video_formats` whitelist (sniff + suffix), trim vs corrupt source, VP9-in-MP4, diagnostics
- [guides/YT_DLP_GUIDE.md](guides/YT_DLP_GUIDE.md)
- [guides/YANDEX_DISK_GUIDE.md](guides/YANDEX_DISK_GUIDE.md)

**Frontend & future**

- [guides/FRONTEND_DEVELOPMENT_PLAN.md](guides/FRONTEND_DEVELOPMENT_PLAN.md)
- [guides/TASK_PROGRESS_WEBSOCKET.md](guides/TASK_PROGRESS_WEBSOCKET.md)

---

## By task

| Goal | Doc |
|------|-----|
| OAuth setup | [guides/OAUTH.md](guides/OAUTH.md), [guides/CREDENTIAL_SECURITY.md](guides/CREDENTIAL_SECURITY.md) |
| Deploy | [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) |
| Templates | [guides/TEMPLATES.md](guides/TEMPLATES.md) |
| Architecture | [ARCHITECTURE_SCHEMAS.md](ARCHITECTURE_SCHEMAS.md), [ADR_OVERVIEW.md](ADR_OVERVIEW.md) |
| API | [TECHNICAL.md](TECHNICAL.md) |
| VK | [guides/VK_INTEGRATION.md](guides/VK_INTEGRATION.md) |

---

## History

- [CHANGELOG.md](CHANGELOG.md) — version history (canonical release facts)

---

## Developer conventions

- From `backend/`: run **`make lint`**, **`make typecheck`**, **`make test`** (or **`make tests-mock`** for a fast pass); use **`uv run …`** for one-off commands.
- Code layout and modules: see **Repository layout** in the root `README.md` and this index (`guides/`, `TECHNICAL.md`, `CHANGELOG.md`).
- In **`CHANGELOG.md`**, paths in **`### Файлы` / `### Files`** blocks are relative to **`backend/`** (same as `api/…`, `alembic/…`): `docs/…` means `backend/docs/…` from the repository root.

---

## Search tips

Run from the repository root (paths under `backend/docs/`):

```bash
grep -r "OAuth" backend/docs/*.md backend/docs/guides/*.md
grep -r "POST /api" backend/docs/TECHNICAL.md
```

---

**Index last updated:** April 2026
