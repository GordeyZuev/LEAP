# Automation Jobs & Celery Beat Integration

> **Status**: Implemented (DB-backed Beat for user jobs; maintenance tasks in code)
> **Migration**: `008_create_celery_beat_tables`
> **Updated**: 2026-10-04

## Overview

Automation jobs schedule **sync + template matching + processing** for the sources named by the job's templates (Zoom, MTS Link, a private or public Yandex Disk folder, VIDEO_URL). User-defined schedules are stored in PostgreSQL and executed by **Celery Beat** with **`celery-sqlalchemy-scheduler`** (`DatabaseScheduler`).

**Capabilities:**

- Schedule types: `time_of_day`, `hours`, `weekdays`, `cron` (see `api/schemas/automation/schedule.py`)
- Rows in `celery_periodic_task` survive Beat restarts
- Per-job template lists, filters, `processing_config` override
- Manual run and async dry-run (`automation.dry_run`) via Celery — dry-run lists matches and does **not** refresh sources unless `sync=true`; it does not enqueue pipelines

---

## Architecture

### High-level flow

```
┌──────────────────┐
│ automation_jobs  │  CRUD via API (user-owned)
└────────┬─────────┘
         │ create / update / (delete removes Beat row)
         ▼
┌──────────────────┐
│   beat_sync.py   │  Cron string → celery_crontab_schedule;
│                  │  upsert celery_periodic_task (name, task, args, enabled)
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Celery Beat     │  DatabaseScheduler: installs beat_schedule, then reads
│  (one process)   │  enabled rows from celery_periodic_task
└────────┬─────────┘
         │ enqueue
         ▼
┌──────────────────┐
│  Redis broker    │
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Celery worker    │  Queue: `async_operations` (see `task_routes` in
│ (async pool)     │  `api/celery_app.py`)
└──────────────────┘
```

### Two sources of periodic work

1. **`celery_app.conf.beat_schedule`** (`api/celery_app.py`) — maintenance tasks (UTC crontabs): `maintenance.cleanup_expired_tokens`, `maintenance.auto_expire_recordings`, `maintenance.cleanup_recording_files`, `maintenance.hard_delete_recordings`. Routed to queue **`maintenance`**.

2. **User automation** — rows written only by **`sync_job_to_beat`**: task **`automation.run_job`**, queue **`async_operations`**.

`DatabaseScheduler` (from **`celery-sqlalchemy-scheduler`**) subclasses Celery’s `Scheduler`. On startup, **`setup_schedule`** applies `beat_schedule` into the database via **`update_from_dict`**, then the active schedule is built from **`celery_periodic_task`** (see `DatabaseScheduler.all_as_schedule` in the library). So maintenance and automation **share** `celery_periodic_task` after Beat has started; they differ by **how** rows appear (code install vs API).

```mermaid
flowchart LR
  subgraph code["beat_schedule in api/celery_app.py"]
    M1["maintenance.*"]
  end
  subgraph api["Automation API"]
    AJ["sync_job_to_beat"]
  end
  subgraph db["PostgreSQL"]
    PT["celery_periodic_task"]
    CT["celery_crontab_schedule"]
  end
  B["Celery Beat\nDatabaseScheduler"]
  code --> B
  AJ --> PT
  CT --> PT
  PT --> B
  B --> R["Redis"]
  R --> W["Workers"]
```

### Database tables

**App tables**

- `automation_jobs` — job definition, stats (`last_run_at`, `next_run_at`, `run_count`), unique `(user_id, name)` (migration `015`)

**`celery-sqlalchemy-scheduler` tables** (migration `008`)

- `celery_periodic_task` — name, task, `crontab_id`, `args`, `enabled`, …
- `celery_crontab_schedule` — minute/hour/day/month/day_of_week + `timezone`
- `celery_interval_schedule`, `celery_solar_schedule` — unused by current `beat_sync` (crontab only)
- `celery_periodic_task_changed` — scheduler change notifications

---

## Schedule types

Schemas live in `api/schemas/automation/schedule.py`. Default timezone is **`Europe/Moscow`** where not specified.

### 1. `time_of_day` — daily at local time

```json
{
  "type": "time_of_day",
  "time": "06:00",
  "timezone": "Europe/Moscow"
}
```

Cron: `MM HH * * *` (minute first in DB).

### 2. `hours` — every N hours

```json
{
  "type": "hours",
  "hours": 6,
  "timezone": "UTC"
}
```

Cron: `0 */N * * *` with `1 <= N <= 24`.

### 3. `weekdays` — selected weekdays + time

```json
{
  "type": "weekdays",
  "days": [0, 2, 4],
  "time": "09:30",
  "timezone": "Europe/Moscow"
}
```

**Days:** `0 = Monday` … `6 = Sunday`. Implementation maps to cron’s `day_of_week` (Sunday=0 in cron) via `(day + 1) % 7`.

### 4. `cron` — raw expression

```json
{
  "type": "cron",
  "expression": "*/15 * * * *",
  "timezone": "UTC"
}
```

---

## Job payload (summary)

| Field | Notes |
|--------|--------|
| `name` | Required; unique per user |
| `template_ids` | Non-empty; templates validated (active, not draft) |
| `schedule` | Discriminated union above |
| `sync_config.sync_days` | 1–30 inclusive local calendar days in the job timezone (today counts). `null` = match every catalog row. Zoom and MTS queries use this window (last 30 days when it is null). Disk and VIDEO_URL list the whole folder or link; matching still keeps rows whose `start_time` is inside the window |
| `sync_config.max_recordings` | Optional cap on full pipelines per run; MTS wait pings are not capped. `null` = unlimited |
| `sync_config.sync_on_run` | Default `true`. Scheduled and manual runs refresh sources before matching. Preview does not, unless `sync=true` |
| `filters` | Optional; `AutomationFilters` defaults: MTS-aware statuses (`INITIALIZED`, `PENDING_CONVERSION`, `PENDING_SOURCE`), `exclude_blank=true` |
| `processing_config` | Optional dict override for pipeline |

Full Pydantic models: `api/schemas/automation/job.py`.

---

## API (`api/routers/automation.py`)

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/api/v1/automation/jobs` | Creates job → `sync_job_to_beat` |
| `GET` | `/api/v1/automation/jobs` | **Paginated** list (`page`, `per_page`, `sort_by`, `sort_order`, `active_only`) |
| `GET` | `/api/v1/automation/jobs/{job_id}` | Full job |
| `PATCH` | `/api/v1/automation/jobs/{job_id}` | Updates → `sync_job_to_beat` |
| `DELETE` | `/api/v1/automation/jobs/{job_id}` | `remove_job_from_beat` then delete row |
| `GET` | `/api/v1/automation/jobs/{job_id}/runs` | History; `RUNNING` until finished; `affected_recordings` null before **047** |
| `POST` | `/api/v1/automation/jobs/{job_id}/run` | `dry_run=true` → `automation.dry_run` (default **no** source sync); `sync=true\|false` optional. Execute **409** if inactive or already `RUNNING` |

**Manual / preview:** response is `TriggerJobResponse` (`task_id`, `mode`, `message`). Poll **`GET /api/v1/tasks/{task_id}`** — preview `result` is `would_process` plus counts. HTTP does not return the preview body.

---

## Execution (`api/tasks/automation.py`)

Scheduled and manual runs use **`automation.run_job`** (`run_automation_job_task`):

1. Load active, non-draft templates in **`job.template_ids` order** (first match wins).
2. If sync is on, refresh the sources below. A failure on one source is logged and the run continues with the rest.
3. Load recordings in the **job-timezone calendar window** (`start_time` inclusive), apply `filters`, match templates (`_find_matching_template`). Unmatched rows are left unchanged.
4. Enqueue `run_recording_task` (wait statuses always; `max_recordings` caps other pipelines, newest first).
5. Update job stats and persist a history row (`RUNNING` → `SUCCESS`/`FAILED`/`SKIPPED`). Migration **054**.

### Which sources a run refreshes

Sources come from `matching_rules.source_ids` on the job's templates.

- Every template lists `source_ids`: only those sources, and only when they are active and belong to the job's user.
- Any template has no `matching_rules`, or `source_ids` is missing or empty: every active source of that user. The listed ids on the other templates are not a limit.

A source is refreshed when it has a credential, or when it does not need one:

| Source | Credential | What the refresh reads |
|--------|------------|------------------------|
| Zoom, MTS Link | Required | Recordings in the job date window |
| Yandex Disk private folder | Required | Every video in `config.folder_path`. `start_time` is the file modification time |
| Yandex Disk public link | Not used. `config.public_url` is enough | Every video on that link. `start_time` is the file modification time |
| VIDEO_URL | Not used | The whole URL or playlist. A new row's `start_time` is the sync time |
| LOCAL | Not refreshed | Nothing to pull |
| Inactive, or a private Disk folder with no credential | Skipped | — |

One job can refresh an MTS Link source and a public Disk link together. The Disk link is not dropped for lack of a credential.

Zoom and MTS receive the same inclusive `from`/`to` dates as the match window (last 30 days when `sync_days` is null). A Disk folder, a public Disk link, and VIDEO_URL ignore those dates and still only **match** rows inside the window. A Disk file older than `sync_days` is saved or updated and is not started. A title matches only with `exact_matches`, `keywords`, or `patterns`; `source_ids` only narrows the source. A row that matches no template is stored as `SKIPPED`, and the default filter does not pick `SKIPPED` up. MTS rows waiting for an MP4 stay `PENDING_SOURCE` and are polled again. `exclude_blank` defaults to true.

Shared helper `_sync_and_match` does sync (optional) + match. Preview (`automation.dry_run`) uses the same helper, **commits** only so catalog rows from a requested sync survive, and does not bind, enqueue, or write history.

---

## When Beat rows are written

| Event | Behavior |
|--------|----------|
| `POST` / `PATCH` job | `sync_job_to_beat` upserts `celery_periodic_task` named `automation_job_{id}`, task `automation.run_job`, `args` JSON `[job_id, user_id]` |
| `DELETE` job | `remove_job_from_beat` deletes that periodic task row |
| API startup | **No** call to `sync_all_jobs_to_beat` in `api/main.py` today |

`sync_all_jobs_to_beat` in `api/helpers/beat_sync.py` is intended for **reconciliation** (e.g. after DB restore or drift). Call it from an admin script or a future lifespan hook if you need full resync.

---

## Celery configuration

### Beat process

```bash
# Foreground (Makefile)
make celery-beat
```

Equivalent:

```bash
PYTHONPATH=$PWD:$PYTHONPATH uv run celery -A api.celery_app beat \
  --loglevel=info \
  --scheduler celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler
```

### Workers

Automation tasks match **`automation.*` → `async_operations`**. You need a worker consuming that queue (e.g. `make celery-async`). Production-style multi-worker start: **`make celery-start`** (writes logs under `logs/`, including `celery-beat.log`).

**Note:** `make celery-dev` runs a worker with **embedded** `beat` and **does not** pass `DatabaseScheduler`. For end-to-end testing of **DB-backed** automation schedules, run **`make celery-beat`** (or `celery-start`) alongside workers.

### Beat DB URI

`beat_dburi` is set to the **sync** SQLAlchemy URL from settings (`api/celery_app.py`), same database as the app.

---

## Implementation reference

| Module | Role |
|--------|------|
| `api/helpers/beat_sync.py` | `sync_job_to_beat`, `remove_job_from_beat`, `sync_all_jobs_to_beat` |
| `api/helpers/schedule_converter.py` | `schedule_to_cron(schedule) -> (cron_expr, human_readable)`; `get_next_run_time(cron_expression, timezone_str)`; `validate_min_interval(cron_expression, min_hours)` |
| `api/services/automation_service.py` | Quotas, duplicate name check, schedule interval validation |

Periodic task row:

- **name:** `automation_job_{id}`
- **task:** `automation.run_job`
- **args:** `[job_id, user_id]` (JSON in DB)

---

## Quotas

Limits come from **subscription / plan** via `QuotaService` (`max_automation_jobs`, `min_automation_interval_hours`), not from a single hardcoded number. `NULL` means unlimited / no minimum. See [QUOTA_AND_ADMIN_API.md](QUOTA_AND_ADMIN_API.md).

---

## Monitoring

### Periodic tasks (automation)

```sql
SELECT name, task, enabled, last_run_at, total_run_count
FROM celery_periodic_task
WHERE name LIKE 'automation_job_%'
ORDER BY id;
```

Join with app jobs (PostgreSQL):

```sql
SELECT aj.id, aj.name, aj.next_run_at, pt.enabled
FROM automation_jobs aj
JOIN celery_periodic_task pt ON pt.name = 'automation_job_' || aj.id::text
WHERE aj.is_active = true
ORDER BY aj.next_run_at NULLS LAST;
```

### Logs

`make celery-start` uses `logs/celery-beat.log` and `logs/celery-async.log` (paths from Makefile).

---

## Migration `008`

File: `alembic/versions/008_create_celery_beat_tables.py`

**Creates tables** listed above; **drops** legacy `celery_schedule` if present.

```bash
uv run alembic upgrade head
```

---

## Troubleshooting

| Symptom | Checks |
|--------|--------|
| Beat not enqueueing user jobs | Process running with `DatabaseScheduler`; `celery_periodic_task.enabled`; `beat_dburi` correct |
| Schedule change not applied quickly | Library reloads when `celery_periodic_task_changed` advances; **restart Beat** after manual SQL edits; if API updates ever seem stale, check that table vs `DatabaseScheduler.schedule_changed` in `celery-sqlalchemy-scheduler` |
| Task never runs | Worker listening on `async_operations`; Redis broker URL; `automation.run_job` registered (`api.tasks.automation` in `include`) |
| Maintenance runs, automation does not | DB rows only created on job create/update — see “When Beat rows are written” |
| Wrong local time | `timezone` in schedule + row in `celery_crontab_schedule`; Celery `timezone`/`enable_utc` in `api/celery_app.py` |

---

## See also

- [CELERY_WORKERS_GUIDE.md](CELERY_WORKERS_GUIDE.md) — queues, pools, processes
- [TEMPLATES.md](TEMPLATES.md) — templates and matching
- [QUOTA_AND_ADMIN_API.md](QUOTA_AND_ADMIN_API.md) — automation quotas
- [TECHNICAL.md](../TECHNICAL.md) — broader API reference
