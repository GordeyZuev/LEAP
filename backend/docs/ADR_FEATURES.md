# Architecture Decision Records - Features

**Проект:** LEAP Platform
**Версия:** 2.1 (Актуализировано: апрель 2026)
**Статус:** Production Features

Дополняет **[ADR_OVERVIEW.md](ADR_OVERVIEW.md)**: там foundational ADR-001–009 (кратко), здесь — прикладные решения **ADR-010+** (автоматизация, очереди Celery, квоты, FSM, аудит и т.д.).

---

## 📋 Содержание

1. [ADR-010: Automation System](#adr-010-automation-system)
2. [ADR-011: Async Processing (Celery)](#adr-011-async-processing-celery)
3. [ADR-012: Quotas & Subscriptions](#adr-012-quotas--subscriptions)
4. [ADR-013: Audit Logging](#adr-013-audit-logging)
5. [ADR-014: Notifications](#adr-014-notifications)
6. [ADR-015: FSM для надежной обработки](#adr-015-fsm-для-надежной-обработки)
7. [ADR-016: Database Performance Optimization](#adr-016-database-performance-optimization)

---

## ADR-010: Automation System

**Статус:** ✅ Полностью реализовано
**Дата:** Январь 2026

### Решение

Template-driven automation с scheduled jobs через Celery Beat.

### Архитектура

```
┌─────────────────────────────────────────┐
│        Automation Architecture          │
└─────────────────────────────────────────┘

automation_jobs (schedule config)
    ↓
Celery Beat (scheduler)
    ↓
Celery Worker (execution)
    ↓
1. Sync sources → find new recordings
2. Match to templates → auto-assign
3. Process matched recordings
4. Upload to platforms
```

### Ключевые компоненты

**1. Automation Jobs (database):**
```python
class AutomationJob:
    name: str
    schedule_config: dict  # Cron-like config
    template_id: int       # Template to apply
    enabled: bool
    last_run_at: datetime
    next_run_at: datetime
```

**2. Schedule Types:**
```python
{
  "type": "daily",       # Daily at specific time
  "time": "06:00",
  "timezone": "UTC"
}

{
  "type": "hours",       # Every N hours
  "hours": 6
}

{
  "type": "weekdays",    # Specific days + time
  "days": [1, 3, 5],     # Mon, Wed, Fri
  "time": "08:00"
}

{
  "type": "cron",        # Custom cron
  "expression": "0 */6 * * *"
}
```

**3. Execution Flow:**
```python
async def execute_automation_job(job_id: int):
    """
    1. Sync sources linked to template
    2. Find recordings with template_id
    3. Filter by status (INITIALIZED, etc.)
    4. Trigger full pipeline
    5. Track progress in processing_stages
    """
    job = await get_job(job_id)
    template = await get_template(job.template_id)

    # Sync
    new_recordings = await sync_sources(template.source_ids)

    # Filter + Process
    to_process = await filter_recordings(
        template_id=template.id,
        status="INITIALIZED",
        exclude_blank=True
    )

    # Batch process
    await bulk_process_recordings(to_process)
```

### Quota Management

**Limits:**
- `max_automation_jobs` - макс. количество jobs (по плану)
- `min_job_interval` - мин. интервал между запусками (anti-spam)

**Checks:**
```python
# Before creating job
if user.jobs_count >= plan.max_automation_jobs:
    raise QuotaExceededError("Max automation jobs reached")

# Before running
if job.last_run_at + min_interval > now():
    skip_run("Too frequent")
```

### Реализация

**Файлы:**
- `database/automation_models.py` - AutomationJob, ProcessingStage
- `api/routers/automation.py` - CRUD endpoints
- `api/tasks/automation.py` - Celery tasks
- `api/services/automation_service.py` - logic

**Endpoints:**
- `GET /automation/jobs` - list jobs
- `POST /automation/jobs` - create job
- `PATCH /automation/jobs/{id}` - update job
- `DELETE /automation/jobs/{id}` - delete job
- `POST /automation/jobs/{id}/run` - manual trigger
- `POST /automation/jobs/{id}/dry-run` - preview

**Статус:** ✅ Реализовано

**См. также:** [TECHNICAL.md](TECHNICAL.md) - Automation system implementation

---

## ADR-011: Async Processing (Celery)

**Статус:** ✅ Полностью реализовано
**Дата:** Январь 2026

### Решение

Celery + Redis для асинхронной обработки длительных задач.

### Архитектура

FastAPI ставит задачи в **Redis** (broker); воркеры забирают задачи по **именованным очередям**. Результаты задач — в Redis (`CELERY_RESULT_BACKEND`). Статус задачи клиент может запрашивать через API (см. OpenAPI).

### Queues

Маршрутизация задаётся в **`api/celery_app.py`** (`task_routes`):

| Queue | Назначение |
|-------|------------|
| `downloads` | Сетевые загрузки (Zoom, yt-dlp и т.д.) |
| `uploads` | Выгрузка на YouTube / VK / Яндекс Диск |
| `async_operations` | Транскрибация, темы, субтитры, оркестрация `run_recording`, sync, automation tasks |
| `processing_cpu` | Только CPU-heavy **trim** (FFmpeg) |
| `maintenance` | Периодические задачи обслуживания |

**Продакшен / локально:** один процесс воркера может слушать несколько очередей (как в корневом `docker-compose.yml`: `downloads,uploads,async_operations,processing_cpu,maintenance`) или разнести по процессам — см. цели `celery-downloads`, `celery-uploads`, `celery-async`, `celery-cpu`, `celery-maintenance` в **`backend/Makefile`** и [CELERY_WORKERS_GUIDE.md](guides/CELERY_WORKERS_GUIDE.md).

### Task Types

**Processing Tasks:**
- `download_recording_task` - download from source
- `process_video_task` - FFmpeg processing
- `transcribe_recording_task` - AI transcription
- `extract_topics_task` - AI topic extraction
- `generate_subtitles_task` - SRT/VTT generation

**Upload Tasks:**
- `upload_to_platform_task` - upload to YouTube/VK
- `retry_failed_uploads_task` - retry failed

**Batch Tasks:**
- `bulk_process_recordings_task` - batch processing
- `bulk_sync_sources_task` - batch sync

**Automation Tasks:**
- `execute_automation_job_task` - run scheduled job

### Progress Tracking

**Task Status:**
```python
{
  "task_id": "abc-123",
  "status": "PROCESSING",  # PENDING, PROCESSING, SUCCESS, FAILURE
  "progress": 45,          # 0-100%
  "current_step": "Transcribing audio...",
  "result": None,          # Result when complete
  "error": None            # Error message if failed
}
```

**API:**
```
GET /tasks/{task_id} - Get task status
DELETE /tasks/{task_id} - Cancel task
GET /tasks - List user's tasks
```

### Celery Chains для параллелизма (январь 2026)

**Проблема:** Монолитный `process_recording_task` блокировал worker на 5+ минут.

**Решение:** Orchestrator pattern с Celery chains:

```python
# Orchestrator (~0.08s)
process_recording_task(recording_id, user_id)
  └─ chain.apply_async() → освобождает worker
       └─ download → trim → transcribe → topics → subs → launch_uploads
          (каждый шаг на любом свободном worker)
```

**Benefits:**
- Worker освобождается за 0.08s (не блокирован на 5+ минут)
- Параллельная обработка разных recordings
- Динамическое распределение шагов между workers
- Worker reuse - один worker может делать download для rec A, потом trim для rec B

**Graceful Error Handling (январь 2026):**
- Credential/Token/Resource errors обрабатываются gracefully
- Output target помечается как FAILED в БД
- Задача возвращает `status='failed'` вместо raise
- ERROR логируется без traceback spam
- Celery видит задачу как успешно завершённую

### Реализация

**Файлы:**
- `api/celery_app.py` — конфигурация и маршрутизация очередей
- `api/tasks/` — определения задач
- `api/routers/tasks.py` — HTTP-статус задач (`GET /api/v1/tasks/{task_id}`)
- корневой `docker-compose.yml` — Redis, воркеры (при деплое через compose)

**Monitoring:**
- Flower UI: `http://localhost:5555`
- Prometheus metrics (опционально)

**Статус:** ✅ Реализовано

---

## ADR-012: Quotas & Subscriptions

**Статус:** ✅ Полностью реализовано
**Дата:** Февраль 2026

### Решение

Code-based defaults + optional plan subscriptions с usage tracking и user statistics.

### Архитектура

```
┌─────────────────────────────────────────┐
│        Quota & Stats System             │
└─────────────────────────────────────────┘

DEFAULT_QUOTAS (config/settings.py, all None = unlimited)
    ↓
subscription_plans (optional, for custom limits)
    ↓
user_subscriptions (user ← plan + custom overrides)
    ↓
quota_usage (tracking по периодам YYYYMM)

StatsService → recordings, transcription seconds, storage bytes
```

### Default Behavior

По умолчанию все пользователи получают `DEFAULT_QUOTAS` из `config/settings.py`:
```python
DEFAULT_QUOTAS: dict[str, int | None] = {
    "max_recordings_per_month": None,   # None = unlimited
    "max_storage_gb": None,
    "max_concurrent_tasks": None,
    "max_automation_jobs": None,
    "min_automation_interval_hours": None,
}
```

- Подписка НЕ создаётся автоматически при регистрации
- Подписка назначается только вручную (кастомный план)
- При отсутствии подписки → fallback на `DEFAULT_QUOTAS`

### Quota Types

**Resource Quotas:**
```python
{
  "max_recordings_per_month": 50,      # Monthly limit (None = unlimited)
  "max_storage_gb": 25,                # Total storage
  "max_concurrent_tasks": 2,           # Parallel processing
  "max_automation_jobs": 3,            # Scheduled jobs
  "min_automation_interval_hours": 1   # Min automation interval
}
```

**Custom Overrides (per user):**
```python
# Override via user_subscriptions.custom_max_*
{
  "custom_max_recordings_per_month": 100,  # Override plan: 50 → 100
  "custom_max_storage_gb": 50              # Override plan: 25 → 50
}
```

### Usage Tracking

**Period-based tracking (quota_usage):**
```python
{
  "user_id": "01HQ...",
  "period": "202602",  # YYYYMM
  "recordings_count": 15,
  "storage_bytes": 3435973837,
  "concurrent_tasks_count": 2
}
```

**Quota Checks (middleware):**
```python
# QuotaService.get_effective_quotas:
# 1. Get user subscription (if exists)
# 2. Get plan limits + custom overrides
# 3. If no subscription → return DEFAULT_QUOTAS
# 4. None = unlimited, skip check

# Before creating recording:
await check_recordings_quota(user_id)
await check_storage_quota(user_id, user_slug)
```

### User Stats

**StatsService** предоставляет статистику:
- `recordings_total` — количество записей (фильтруется по датам)
- `recordings_by_status` — разбивка по статусам
- `recordings_by_template` — обработанные записи по шаблонам
- `transcription_total_seconds` — сумма `final_duration`
- `storage_bytes` / `storage_gb` — размер папки пользователя

### Endpoints

```
GET /users/me/quota - Current quota status
GET /users/me/stats - User statistics (recordings, transcription, storage)
GET /admin/stats/overview - Platform stats
GET /admin/stats/users - User stats
GET /admin/stats/quotas - Quota usage
POST /admin/users/{id}/quota - Override quota
```

### Реализация

**Файлы:**
- `config/settings.py` - `DEFAULT_QUOTAS` constant
- `database/auth_models.py` - subscription & quota models (3 tables)
- `api/services/quota_service.py` - quota logic (fallback → DEFAULT_QUOTAS)
- `api/services/stats_service.py` - user statistics
- `api/middleware/quota.py` - enforcement checks
- `api/routers/admin.py` - admin endpoints
- `api/routers/users.py` - /me/quota, /me/stats

**Статус:** ✅ Реализовано


---

## ADR-013: Audit Logging

**Статус:** 🚧 Частично реализовано (базовый logging)
**Приоритет:** Medium (для compliance)

### Решение

Structured logging + audit trail для критичных операций.

### Что логируется

**Critical Operations:**
- Authentication (login, logout, token refresh)
- Credential management (create, update, delete)
- Recording operations (create, delete, reset)
- Template changes (create, update, delete, rematch)
- Quota overrides (admin actions)
- Automation job runs (start, end, errors)

**Audit Log Format:**
```python
{
  "timestamp": "2026-01-14T10:30:00Z",
  "user_id": 123,
  "action": "recording.delete",
  "resource_type": "recording",
  "resource_id": 456,
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "details": {
    "recording_name": "Lecture 1",
    "status": "UPLOADED"
  },
  "result": "success"  # success, failure, partial
}
```

### Реализация (текущая)

**Structured Logging:**
- Python `logging` module
- JSON format для production
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Rotation: daily, 30 days retention

**Будущее (полный audit):**
```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id INT REFERENCES users(id),
    action VARCHAR(100),
    resource_type VARCHAR(50),
    resource_id INT,
    ip_address INET,
    user_agent TEXT,
    details JSONB,
    result VARCHAR(20)
);

CREATE INDEX idx_audit_user ON audit_logs(user_id, timestamp DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, timestamp DESC);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
```

**Endpoints (будущее):**
```
GET /admin/audit - Admin audit log
GET /users/me/activity - User activity log
```

**Статус:** 🚧 Базовый logging реализован, полный audit - TODO

---

## ADR-014: Notifications

**Статус:** 🚧 Частично реализовано (error logging)
**Приоритет:** Low (nice to have)

### Решение

Multi-channel notifications для критичных событий.

### Notification Types

**Error Notifications:**
- Processing failure after retries
- Transcription failure (quota, API error)
- Upload failure (auth, quota, network)
- Automation job failure

**Success Notifications (опционально):**
- Recording uploaded successfully
- Automation job completed
- Daily/weekly summary

**Quota Notifications:**
- 80% quota reached
- 100% quota reached
- Overage usage

### Channels

**Email (primary):**
- SMTP integration
- Template-based messages
- HTML + plain text fallback

**Webhook (future):**
- POST to user-defined URL
- JSON payload with event data
- Retry logic with exponential backoff

**In-app (future):**
- Notification center в UI
- Real-time via WebSocket
- Persistent storage в БД

### Реализация (текущая)

**Error Logging:**
- Все ошибки логируются
- Email уведомления - TODO

**Будущее:**
```python
# Notification Service
class NotificationService:
    async def send_error_notification(
        user_id: int,
        error_type: str,
        details: dict
    ):
        # Send via configured channels
        pass

    async def send_quota_warning(
        user_id: int,
        quota_type: str,
        usage_percent: float
    ):
        pass
```

**Статус:** 🚧 Базовый logging, notifications - TODO

---

## ADR-015: FSM для надежной обработки

**Статус:** ✅ Полностью реализовано
**Дата:** Январь 2026

### Решение

Finite State Machine для гарантированных state transitions.

### FSM Diagram

```
┌─────────────────────────────────────────┐
│        Processing State Machine         │
└─────────────────────────────────────────┘

INITIALIZED
    ↓
DOWNLOADING → DOWNLOADED
    ↓
PROCESSING → PROCESSED
    ↓
TRANSCRIBING → TRANSCRIBED
    ↓
UPLOADING → UPLOADED

Any state → FAILED (with failed_at_stage)
FAILED → retry → continue from failed stage
```

### State Definitions

**Processing States:**
- `INITIALIZED` - Запись создана, готова к обработке
- `DOWNLOADING` - Скачивается из источника
- `DOWNLOADED` - Скачана, готова к processing
- `PROCESSING` - FFmpeg обработка (trim silence)
- `PROCESSED` - Обработана, готова к transcription
- `TRANSCRIBING` - AI транскрибация
- `TRANSCRIBED` - Транскрибирована, готова к upload
- `UPLOADING` - Загрузка на платформы
- `UPLOADED` - Успешно загружена везде
- `FAILED` - Ошибка (с указанием стадии)
- `SKIPPED` - Пропущена (blank record, user skip)

### Transition Rules

**Allowed Transitions:**
```python
ALLOWED_TRANSITIONS = {
    "PENDING_SOURCE": ["INITIALIZED", "SKIPPED"],  # After source processing completes
    "INITIALIZED": ["DOWNLOADING", "FAILED", "SKIPPED"],
    "DOWNLOADING": ["DOWNLOADED", "FAILED"],
    "DOWNLOADED": ["PROCESSING", "FAILED"],
    "PROCESSING": ["PROCESSED", "FAILED"],
    "PROCESSED": ["TRANSCRIBING", "FAILED"],
    "TRANSCRIBING": ["TRANSCRIBED", "FAILED"],
    "TRANSCRIBED": ["UPLOADING", "FAILED"],
    "UPLOADING": ["UPLOADED", "FAILED"],
    "UPLOADED": [],  # Terminal state
    "FAILED": ["DOWNLOADING", "PROCESSING", "TRANSCRIBING", "UPLOADING"],  # Retry
    "SKIPPED": []  # Terminal state
}
```

**Validation:**
```python
def validate_transition(from_status: str, to_status: str) -> bool:
    """Check if transition is allowed"""
    return to_status in ALLOWED_TRANSITIONS[from_status]

# Usage
if not validate_transition(recording.status, new_status):
    raise InvalidTransitionError(f"{recording.status} → {new_status}")
```

### Output Target FSM

**Separate FSM для каждой платформы:**
```python
class OutputTarget:
    target_type: str  # youtube, vk
    status: TargetStatus  # Enum

    # Transitions
    NOT_UPLOADED → UPLOADING → UPLOADED
    NOT_UPLOADED → FAILED
    UPLOADING → FAILED
    FAILED → UPLOADING  # Retry
```

**Преимущества:**
- ✅ Независимые статусы для каждой платформы
- ✅ Partial success (YouTube ok, VK failed)
- ✅ Retry только failed platforms

### Failed Handling

**Failed Flag:**
```python
class Recording:
    status: ProcessingStatus  # Current stage
    failed: bool              # Is in failed state?
    failed_at_stage: str      # Stage where failed
    retry_count: int          # Number of retries
    error_message: str        # Last error
```

**Retry Logic:**
```python
async def retry_recording(recording_id: int):
    """
    1. Check failed=True
    2. Get failed_at_stage
    3. Reset failed=False
    4. Continue from failed_at_stage
    5. Increment retry_count
    """
    recording = await get_recording(recording_id)

    if not recording.failed:
        raise ValueError("Recording not failed")

    # Continue from failed stage
    stage = recording.failed_at_stage
    recording.failed = False
    recording.retry_count += 1

    if stage == "DOWNLOADING":
        await download_task(recording_id)
    elif stage == "PROCESSING":
        await process_task(recording_id)
    # etc.
```

### Processing Stages Tracking

**Table: processing_stages**
```python
class ProcessingStage:
    recording_id: int
    stage_name: str  # download, process, transcribe, upload
    status: str      # pending, running, completed, failed
    started_at: datetime
    completed_at: datetime
    error_message: str
    metadata: dict   # Stage-specific data
```

**Usage:**
- Детальное отслеживание progress
- Debugging failed recordings
- Analytics (avg time per stage)

### Реализация

**Файлы:**
- `models/recording.py` - ProcessingStatus enum
- `database/models.py` - RecordingModel with FSM fields
- `database/automation_models.py` - ProcessingStage model
- Service layer - FSM validation

**Endpoints:**
```
POST /recordings/{id}/retry - Retry failed recording
POST /recordings/{id}/reset - Reset to INITIALIZED
GET /recordings/{id}/stages - Get processing stages
```

**Статус:** ✅ Реализовано

---

## ADR-016: Database Performance Optimization

**Статус:** ✅ Полностью реализовано
**Дата:** Январь 2026

### Решение

Оптимизация производительности БД через устранение N+1 queries, bulk operations и eager loading.

### Проблемы

**До оптимизации:**
- N+1 queries: загрузка пресетов в циклах (1 запрос + N запросов)
- Загрузка всех записей в память для подсчета
- Отсутствие eager loading для вложенных связей
- Множественные запросы в batch операциях
- Импорты внутри функций (anti-pattern)

### Решение

**1. Bulk Operations:**
```python
# До: N запросов
for recording_id in recording_ids:
    recording = await repo.find_by_id(user_id, recording_id)

# После: 1 запрос
recordings = await repo.get_by_ids(user_id, recording_ids)
```

**2. Efficient Counting:**
```python
# До: загрузка всех записей
jobs = await session.execute(select(AutomationJob).where(...))
count = len(jobs.scalars().all())

# После: database count
count = await session.scalar(
    select(func.count()).select_from(AutomationJob).where(...)
)
```

**3. Eager Loading:**
```python
# До: N+1 queries
recording = await session.get(Recording, id)
source = recording.source  # +1 query
preset = recording.outputs[0].preset  # +N queries

# После: 1 query with joins
stmt = (
    select(Recording)
    .options(
        selectinload(Recording.source).selectinload(SourceMetadata.input_source),
        selectinload(Recording.outputs).selectinload(OutputTarget.preset)
    )
    .where(Recording.id == id)
)
```

### Оптимизированные области

**Repositories:**
- `recording_repos.py` - добавлен `get_by_ids()`, eager loading
- `template_repos.py` - добавлен `find_by_ids()` для пресетов
- `automation_repos.py` - оптимизирован `count_user_jobs()`

**Tasks:**
- `upload.py` - устранена N+1 при поиске пресетов
- `processing.py` - устранена N+1 при загрузке пресетов

**Routers:**
- `recordings.py` - устранено 8 N+1 проблем в batch операциях
- `users.py` - удален дублирующий запрос

**Code Quality:**
- Все импорты перенесены в начало файлов (PEP8)
- Удалены неиспользуемые импорты и вызовы

### Метрики

**До:**
- Batch операция (10 recordings): ~50 queries
- Count операция: загрузка всех записей в память
- Nested relations: N+1 queries

**После:**
- Batch операция (10 recordings): ~5 queries (-90%)
- Count операция: 1 database query
- Nested relations: eager loading (1 query)

### Реализация

**Файлы:**
- `api/repositories/recording_repos.py`
- `api/repositories/template_repos.py`
- `api/repositories/automation_repos.py`
- `api/tasks/upload.py`
- `api/tasks/processing.py`
- `api/routers/recordings.py`
- `api/routers/users.py`

**Статус:** ✅ Реализовано (январь 2026)

---

## Итоговая таблица статусов

| ADR | Feature | Status | Priority | Notes |
|-----|---------|--------|----------|-------|
| ADR-010 | Automation | ✅ Done | High | Celery Beat |
| ADR-011 | Async Processing | ✅ Done | High | Celery Chains |
| ADR-012 | Quotas & Subscriptions | ✅ Done | High | 4 plans |
| ADR-013 | Audit Logging | 🚧 Partial | Medium | Basic logging |
| ADR-014 | Notifications | 🚧 Partial | Low | Logging only |
| ADR-015 | FSM | ✅ Done | High | Production-ready |
| ADR-016 | DB Optimization | ✅ Done | High | N+1 eliminated |

---

## См. также

### Детальная документация
- [TECHNICAL.md](TECHNICAL.md) - Automation system implementation
- [TECHNICAL.md](TECHNICAL.md) - Admin & Quota API
- [TECHNICAL.md](TECHNICAL.md) - Техническая документация

### Архитектура
- [ADR_OVERVIEW.md](ADR_OVERVIEW.md) - Основные ADR решения
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Схемы БД

---

**Документ обновлен:** Январь 2026
**Статус фич:** 4/6 fully done, 2/6 partial
