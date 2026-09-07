# LEAP documentation

Canonical hub for operators and contributors. Product age rating: **12+**.

In-app guide (plain language, search, FAQ): web client → **Documentation**.

---

## Start here

| If you… | Read |
|---------|------|
| Need a short product answer | [FAQ.md](FAQ.md) |
| Are deploying or running locally | [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) |
| Are connecting platforms | [guides/OAUTH.md](guides/OAUTH.md), [guides/MTS_LINK_GUIDE.md](guides/MTS_LINK_GUIDE.md) |
| Need the HTTP surface | [TECHNICAL.md](TECHNICAL.md), [guides/USAGE_AND_ANALYTICS.md](guides/USAGE_AND_ANALYTICS.md) |
| Want what shipped | [CHANGELOG.md](CHANGELOG.md) |

Root product overview: repository [`README.md`](../../README.md).

---

## Layout

| Path | Contents |
|------|----------|
| **[FAQ.md](FAQ.md)** | Product FAQ (templates, pipeline, share, 12+) |
| **[guides/](guides/)** | How-tos: deploy, OAuth, Celery, integrations, templates, quotas |
| **This folder** | API/tech (`TECHNICAL.md`), ADRs, schema, changelog |
| **[archive/](archive/)** | Historical / thesis material – not runbooks |
| **[dev_notes/](dev_notes/)** | Drafts; ignore when they conflict with `guides/` |

---

## Using the product

- [FAQ.md](FAQ.md)
- [guides/USAGE_AND_ANALYTICS.md](guides/USAGE_AND_ANALYTICS.md) – Settings → Usage, quotas, activity charts, admin analytics, share stats (v0.10.8.3)
- [guides/PLAYLISTS.md](guides/PLAYLISTS.md) – course playlists, public `/share/p/{uuid}`, Enable / Disable / Rotate
- [guides/TEMPLATES.md](guides/TEMPLATES.md)
- [guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md](guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md)
- [guides/JINJA_METADATA_TEMPLATES.md](guides/JINJA_METADATA_TEMPLATES.md) – Jinja variables, Timestamps vs `topics_display`, preview API
- [guides/VIDEO_DELIVERY.md](guides/VIDEO_DELIVERY.md) – browser playback, presigned URLs, MP4 faststart
- [guides/FRONTEND_UI.md](guides/FRONTEND_UI.md) – motion, `.pressable`, reduced-motion

---

## Deploy, auth, workers

- [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md)
- [guides/OAUTH.md](guides/OAUTH.md)
- [guides/CREDENTIAL_SECURITY.md](guides/CREDENTIAL_SECURITY.md)
- [guides/SESSIONS.md](guides/SESSIONS.md)
- [guides/QUOTAS.md](guides/QUOTAS.md)
- [guides/QUOTA_AND_ADMIN_API.md](guides/QUOTA_AND_ADMIN_API.md)
- [guides/AUTOMATION_CELERY_BEAT.md](guides/AUTOMATION_CELERY_BEAT.md)
- [guides/CELERY_WORKERS_GUIDE.md](guides/CELERY_WORKERS_GUIDE.md)
- [guides/CELERY_ASYNCIO_TECHNICAL.md](guides/CELERY_ASYNCIO_TECHNICAL.md)
- [guides/MONITORING.md](guides/MONITORING.md)

---

## Integrations

- [guides/ZOOM_CREDS_GUIDE.md](guides/ZOOM_CREDS_GUIDE.md)
- [guides/MTS_LINK_GUIDE.md](guides/MTS_LINK_GUIDE.md) – org API key, lecturers by email, MP4 on Run, blank by duration, session chat/files
- [guides/YT_DLP_GUIDE.md](guides/YT_DLP_GUIDE.md)
- [guides/YANDEX_DISK_GUIDE.md](guides/YANDEX_DISK_GUIDE.md)

---

## Storage and processing

- [guides/STORAGE_STRUCTURE.md](guides/STORAGE_STRUCTURE.md)
- [guides/MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](guides/MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md) – short/broken files vs under-trim (trailing digital silence)
- [guides/TASK_PROGRESS_WEBSOCKET.md](guides/TASK_PROGRESS_WEBSOCKET.md)

ASR in production is **AssemblyAI**. Notes about Fireworks Batch API are historical: [guides/FIREWORKS_BATCH_API.md](guides/FIREWORKS_BATCH_API.md).

---

## Architecture and API

- [TECHNICAL.md](TECHNICAL.md)
- [ARCHITECTURE_SCHEMAS.md](ARCHITECTURE_SCHEMAS.md)
- [ADR_OVERVIEW.md](ADR_OVERVIEW.md)
- [ADR_FEATURES.md](ADR_FEATURES.md)
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md)

---

## By task

| Goal | Doc |
|------|-----|
| FAQ / onboarding | [FAQ.md](FAQ.md), in-app **Documentation** |
| OAuth | [guides/OAUTH.md](guides/OAUTH.md), [guides/CREDENTIAL_SECURITY.md](guides/CREDENTIAL_SECURITY.md) |
| Deploy | [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) |
| Templates | [guides/TEMPLATES.md](guides/TEMPLATES.md) |
| Playlists / course share | [guides/PLAYLISTS.md](guides/PLAYLISTS.md) |
| MTS Link | [guides/MTS_LINK_GUIDE.md](guides/MTS_LINK_GUIDE.md) |
| Playback | [guides/VIDEO_DELIVERY.md](guides/VIDEO_DELIVERY.md) |
| Observability | [guides/MONITORING.md](guides/MONITORING.md) |
| API | [TECHNICAL.md](TECHNICAL.md) |

---

## History and archive

- [CHANGELOG.md](CHANGELOG.md) – what shipped (canonical)
- [archive/PLAN.md](archive/PLAN.md) – thesis plan (not a runbook)

---

## Developer conventions

- From `backend/`: **`make lint`**, **`make typecheck`**, **`make test`** (or **`make tests-mock`**); **`uv run …`** for one-off commands.
- In **`CHANGELOG.md`**, paths in **Files** blocks are relative to **`backend/`**.

---

**Index last updated:** September 2026
