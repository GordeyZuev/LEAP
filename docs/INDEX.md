# Documentation Index

**Production-Ready Multi-tenant SaaS for Video Processing**

---

## Layout

| Path | Contents |
|------|----------|
| **[guides/](guides/)** | How-to guides: deployment, OAuth, templates, Celery, integrations (Zoom, VK, yt-dlp, …) |
| **[archive/](archive/)** | Thesis plan, seminar materials, incident write-ups, legacy changelogs |
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
- [archive/SEMINAR_PRESENTATION.md](archive/SEMINAR_PRESENTATION.md) — seminar talk outline

---

## Guides ([guides/](guides/))

**Templates & automation**

- [guides/TEMPLATES.md](guides/TEMPLATES.md)
- [guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md](guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md)
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
- [guides/ASR_MODELS_DEEP_DIVE.md](guides/ASR_MODELS_DEEP_DIVE.md)

**Storage & ingestion**

- [guides/STORAGE_STRUCTURE.md](guides/STORAGE_STRUCTURE.md)
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

- [CHANGELOG.md](CHANGELOG.md) — version history
- [archive/UPDATES.md](archive/UPDATES.md) — digest (superseded by changelog for facts)
- [archive/WHAT_WAS_DONE.md](archive/WHAT_WAS_DONE.md) — long-form milestone notes

---

## Developer conventions

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — code style & docs workflow

---

## Search tips

```bash
grep -r "OAuth" docs/*.md docs/guides/*.md
grep -r "POST /api" docs/TECHNICAL.md
```

---

**Index last updated:** March 2026
