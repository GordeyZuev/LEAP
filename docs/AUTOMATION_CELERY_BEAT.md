# Automation Jobs & Celery Beat Integration

> **Status**: ✅ Fully Implemented
> **Migration**: 008_create_celery_beat_tables
> **Updated**: 2026-01-31

## Overview

Automation jobs provide scheduled sync and processing of Zoom recordings. The system uses **celery-sqlalchemy-scheduler** for reliable, database-backed scheduling with Celery Beat.

**Key Features:**
- 4 schedule types (daily, hours, weekdays, cron)
- Database-backed scheduling (survives restarts)
- Template-based matching and processing
- Flexible filtering and configuration override
- Dry-run preview mode

---

## Architecture

### Components

```
┌─────────────────┐
│ Automation Jobs │  User creates automation jobs via API
│   (PostgreSQL)  │  with schedule, templates, filters
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  beat_sync.py   │  Syncs jobs to Celery Beat tables
│                 │  (celery_periodic_task + crontab_schedule)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Celery Beat    │  Reads database, triggers tasks at schedule
│   (Scheduler)   │  Uses DatabaseScheduler from celery-sqlalchemy-scheduler
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Celery Worker   │  Executes automation.run_job task
│  (async pool)   │  Syncs sources → matches templates → processes
└─────────────────┘
```

### Database Tables

**Automation Tables** (our app):
- `automation_jobs` - user-defined automation configurations

**Celery Beat Tables** (celery-sqlalchemy-scheduler):
- `celery_periodic_task` - scheduled task definitions
- `celery_crontab_schedule` - cron expressions
- `celery_interval_schedule` - interval schedules
- `celery_solar_schedule` - solar event schedules
- `celery_periodic_task_changed` - change tracking for Beat

---

## Schedule Types

### 1. Time of Day (Daily)

Run every day at specific time.

```json
{
  "type": "time_of_day",
  "time": "06:00",
  "timezone": "Europe/Moscow"
}
```

**Cron equivalent**: `00 06 * * *`

**Use cases:**
- Daily morning sync before work
- Nightly processing during off-hours

---

### 2. Hours (Interval)

Run every N hours.

```json
{
  "type": "hours",
  "hours": 6,
  "timezone": "UTC"
}
```

**Cron equivalent**: `0 */6 * * *`

**Use cases:**
- Frequent sync (every 2-4 hours)
- Regular polling of new recordings

---

### 3. Weekdays (Weekly)

Run on specific days at specific time.

```json
{
  "type": "weekdays",
  "days": [0, 2, 4],
  "time": "09:30",
  "timezone": "Europe/Moscow"
}
```

**Days**: `0=Monday, 1=Tuesday, ..., 6=Sunday`
**Cron equivalent**: `30 09 * * 1,3,5`

**Use cases:**
- Workday-only sync (Mon-Fri)
- Weekend processing
- Specific meeting days

---

### 4. Cron (Custom)

Custom cron expression for advanced scheduling.

```json
{
  "type": "cron",
  "expression": "*/15 * * * *",
  "timezone": "UTC"
}
```

**Use cases:**
- Complex schedules (e.g., "every 15 min during business hours")
- Fine-grained control

---

## Automation Job Configuration

### Full Example

```json
{
  "name": "Daily Morning Sync",
  "description": "Sync and process recordings every day at 6 AM",
  "template_ids": [1, 2, 3],
  "schedule": {
    "type": "time_of_day",
    "time": "06:00",
    "timezone": "Europe/Moscow"
  },
  "sync_config": {
    "sync_days": 2
  },
  "filters": {
    "status": ["INITIALIZED"],
    "exclude_blank": true
  },
  "processing_config": {
    "auto_process": true,
    "auto_upload": true,
    "skip_transcription": false
  }
}
```

### Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Job name (required) |
| `description` | string | Optional description |
| `template_ids` | int[] | Templates to use for matching (required) |
| `schedule` | object | Schedule configuration (see above) |
| `sync_config.sync_days` | int | Sync last N days (1-30, default: 2) |
| `filters.status` | string[] | Recording statuses to process (default: `["INITIALIZED"]`) |
| `filters.exclude_blank` | bool | Skip blank recordings (default: `true`) |
| `processing_config` | object | Override config (highest priority) |

---

## API Endpoints

### Create Automation Job

```http
POST /api/v1/automation/jobs
Content-Type: application/json
Authorization: Bearer <token>

{
  "name": "Daily Sync",
  "template_ids": [1],
  "schedule": {
    "type": "time_of_day",
    "time": "06:00",
    "timezone": "Europe/Moscow"
  },
  "sync_config": {
    "sync_days": 2
  }
}
```

**Response**: `201 Created`

The job is automatically synced to Celery Beat tables.

---

### List Jobs

```http
GET /api/v1/automation/jobs?active_only=true
```

**Response**: Array of automation jobs with stats (`last_run_at`, `next_run_at`, `run_count`).

---

### Update Job

```http
PATCH /api/v1/automation/jobs/{job_id}

{
  "is_active": false
}
```

Updates are automatically synced to Beat (enables/disables task).

---

### Delete Job

```http
DELETE /api/v1/automation/jobs/{job_id}
```

Removes job from database AND Celery Beat tables.

---

### Manual Trigger

```http
POST /api/v1/automation/jobs/{job_id}/run

# Preview mode (no changes)
POST /api/v1/automation/jobs/{job_id}/run?dry_run=true
```

**Dry run** returns estimated counts without executing.

---

## Execution Flow

### What Happens When Job Runs

1. **Load templates** from `template_ids`
2. **Collect source_ids** from template matching rules
3. **Sync recordings** from all required sources (last N days)
4. **Filter recordings** by status and exclude_blank
5. **Match templates** using `matching_rules` (name patterns, source_ids)
6. **Process matched recordings** with `processing_config` override
7. **Update job stats** (`last_run_at`, `next_run_at`, `run_count`)

### Task Execution

```python
# Celery task
@celery_app.task(name="automation.run_job")
def run_automation_job_task(job_id: int, user_id: str):
    # Load job and templates
    # Sync recordings from sources
    # Filter and match recordings
    # Start processing pipelines
    # Update stats
```

---

## Celery Beat Setup

### Start Beat Scheduler

```bash
# Development (foreground)
make celery-beat

# Production (background)
make celery-all
```

**Configuration** (`api/celery_app.py`):
```python
celery_app.conf.update(
    beat_dburi=database_url,  # Database for scheduler
)
```

**Scheduler**:
```python
--scheduler celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler
```

### Startup Sync

On API startup, all active jobs are synced to Beat:

```python
# main.py or startup script
from api.helpers.beat_sync import sync_all_jobs_to_beat

async def startup():
    async with db_session() as session:
        await sync_all_jobs_to_beat(session)
```

---

## Implementation Details

### beat_sync.py

**Functions:**
- `sync_job_to_beat(session, job)` - create/update periodic task
- `remove_job_from_beat(session, job_id)` - delete periodic task
- `sync_all_jobs_to_beat(session)` - bulk sync on startup

**How it works:**
1. Converts schedule to cron expression
2. Inserts/updates `celery_crontab_schedule`
3. Upserts `celery_periodic_task` with task name `automation_job_{id}`

### schedule_converter.py

**Functions:**
- `schedule_to_cron(schedule)` - convert schedule dict to cron
- `get_next_run_time(cron, timezone)` - calculate next run
- `validate_min_interval(cron, min_hours)` - enforce minimum interval

---

## Quotas & Limits

Users have quotas for automation:

```sql
-- user_quotas table
max_automation_jobs: int = 5  -- max jobs per user
min_automation_interval_hours: int = 1  -- minimum interval
```

**Validation** in `AutomationService`:
- Check job count against `max_automation_jobs`
- Validate cron interval >= `min_automation_interval_hours`

---

## Monitoring

### Check Beat Status

```sql
-- Active periodic tasks
SELECT name, task, enabled, last_run_at, total_run_count
FROM celery_periodic_task
WHERE name LIKE 'automation_job_%'
ORDER BY last_run_at DESC;

-- Next runs
SELECT
  aj.name,
  aj.next_run_at,
  pt.enabled
FROM automation_jobs aj
JOIN celery_periodic_task pt ON pt.name = 'automation_job_' || aj.id
WHERE aj.is_active = true
ORDER BY aj.next_run_at;
```

### Logs

```bash
# Beat scheduler logs
tail -f logs/celery-beat.log

# Worker logs (automation tasks)
tail -f logs/celery-async.log
```

---

## Migration 008

**File**: `alembic/versions/008_create_celery_beat_tables.py`

**Creates tables:**
- `celery_interval_schedule`
- `celery_crontab_schedule`
- `celery_solar_schedule`
- `celery_periodic_task`
- `celery_periodic_task_changed`

**Removes**:
- Old incorrect `celery_schedule` table (from migration 001)

**Apply**:
```bash
uv run alembic upgrade head
```

---

## Troubleshooting

### Beat not picking up jobs

1. Check if Beat is running: `ps aux | grep celery.*beat`
2. Verify database connection in Beat logs
3. Check `celery_periodic_task_changed` has recent `last_update`

### Jobs not executing

1. Verify `enabled=true` in `celery_periodic_task`
2. Check worker is running: `ps aux | grep celery.*worker`
3. Verify queue routing (automation tasks → `async_operations` queue)
4. Check task logs for errors

### Schedule not matching expected time

1. Verify `timezone` in schedule configuration
2. Check cron expression: `SELECT * FROM celery_crontab_schedule`
3. Use `croniter` to test: `croniter('0 6 * * *').get_next()`

---

## See Also

- [CELERY_WORKERS_GUIDE.md](CELERY_WORKERS_GUIDE.md) - Worker pools and queues
- [TEMPLATES.md](TEMPLATES.md) - Template matching rules
- [TECHNICAL.md](TECHNICAL.md) - Full API documentation
