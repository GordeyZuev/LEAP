# 🎯 Production-Ready Multi-tenant платформа

**Период:** 2-14 января 2026
**Версия:** v0.9.6.3
**Статус:** Production Ready

---

## 🔄 Two-Level Recording Deletion System (19 января 2026)

**Проблема:** Hard deleted recordings возвращались при Zoom sync, нет гибкого управления retention

**Решение - Two-Level Deletion:**

**Архитектура:**
- **Level 1 (Soft Delete):** `delete_state="soft"` - файлы на месте, можно restore
- **Level 2 (Files Cleanup):** `delete_state="hard"` - видео/аудио удалены, master.json/topics сохранены
- **Level 3 (Hard Delete):** запись полностью удалена из БД

**Timeline:**
```
Day 0:  User DELETE → deleted=true, delete_state="soft"
        hard_delete_at = now + (soft_delete_days + hard_delete_days)

Day 3:  Maintenance → Files cleanup (Level 2)
        Удалены: video, audio | Сохранены: master.json, extracted.json, метаданные БД
        delete_state="hard", soft_deleted_at=now

Day 33: Maintenance → Hard delete (Level 3)
        Удалена запись из БД полностью
```

**Миграция:** `021_add_two_level_deletion.py`

**Новые поля в RecordingModel:**
- `delete_state` - явное состояние: "active", "soft", "hard"
- `deletion_reason` - "manual" (user), "expired" (auto), "admin"
- `soft_deleted_at` - когда удалили файлы (Level 2)
- `hard_delete_at` - когда удалить из БД (Level 3)

**Per-user настройки (в user config):**
- `retention.soft_delete_days` (default: 3) - через сколько удалить файлы
- `retention.hard_delete_days` (default: 30) - через сколько удалить из БД от deleted_at
- `retention.auto_expire_days` (default: 90) - автоистечение активных записей

**Repository методы:**
- `soft_delete(recording, user_config)` - ручное удаление
- `auto_expire(recording, user_config)` - автоистечение
- `cleanup_recording_files(recording)` - удаление файлов (Level 2)
- `delete(recording)` - hard delete (Level 3)
- `restore(recording, user_config)` - восстановление (только для delete_state="soft")

**API эндпоинты:**
- `DELETE /recordings/{id}` - soft delete с user config
- `POST /recordings/bulk/delete` - bulk soft delete
- `POST /recordings/{id}/restore` - restore (валидация delete_state)
- `POST /recordings/{id}/reset` - только для active recordings
- Response включает: delete_state, deletion_reason, soft_deleted_at, hard_delete_at

**Maintenance Tasks:**
- `auto_expire_recordings_task` (3:30 UTC) - expire активных записей при expire_at
- `cleanup_recording_files_task` (4:00 UTC) - удаление файлов (Level 2)
- `hard_delete_recordings_task` (5:00 UTC) - удаление из БД (Level 3)

**Решена проблема re-sync:** Deleted recordings остаются в БД → sync находит их → пропускает (проверка `if existing.deleted`)

**Конфигурация:**
- Глобальные defaults: `config/settings.py` (RetentionSettings)
- Per-user overrides: `UserConfigModel.config_data['retention']`
- API: `PATCH /api/v1/users/me/config`

**Critical fixes (post-implementation code review):**
1. **Race condition**: User может сделать restore во время maintenance task → файлы удаляются для активной записи
   - Fix: Проверка `delete_state != "soft"` в начале `cleanup_recording_files()`
   - Fix: Re-check state после refetch в `cleanup_recording_files_task()`
2. **Null pointer**: `deleted_at` может быть None → TypeError при `deleted_at + timedelta(...)`
   - Fix: Проверка `if not recording.deleted_at: continue`
3. **Timestamp consistency**: `updated_at` не обновлялся при cleanup
   - Fix: Явная установка `recording.updated_at = datetime.utcnow()`
4. **Idempotency**: Повторный вызов мог изменять timestamps
   - Fix: State check предотвращает повторное выполнение
5. **Timestamps logic improvement**: Обе даты (`soft_deleted_at`, `hard_delete_at`) теперь устанавливаются сразу при DELETE (в будущем)
   - `soft_delete()`: устанавливает `soft_deleted_at = now + soft_days`, `hard_delete_at = now + soft_days + hard_days`
   - Maintenance task: просто проверяет `soft_deleted_at < now` вместо расчета threshold
   - `cleanup_recording_files()`: только меняет `delete_state`, даты не трогает

---


---

## ⚙️ Unified Configuration System (18 января 2026)

**Проблема:** Настройки разбросаны по 3 файлам, Celery retry hardcoded, OAuth в JSON файлах

**Решение:**
- Создан `config/settings.py` (599 строк) с Pydantic BaseSettings
- 12 секций: APP, SERVER, DATABASE, REDIS, CELERY, SECURITY, STORAGE, LOGGING, MONITORING, OAUTH, FEATURES, PROCESSING
- Все Celery retry параметры через env (6 типов задач)
- Production validators (JWT min 32 chars)
- Singleton `get_settings()`
- `.env.example` с 200+ переменными

**Удалено legacy (~1200 строк):**
- `api/config.py` (200 строк)
- `config/unified_config.py` (459 строк)
- `config/accounts.py` (28 строк, hardcoded Zoom)
- `utils/title_mapper.py` (214 строк)
- `video_upload_module/config_factory.py` (старая версия, 219 строк)

**Обновлено:**
- 8 файлов Celery tasks (15 задач) - используют settings для retry
- `api/celery_app.py`, `api/main.py`, `api/routers/auth.py`
- `api/auth/security.py`, `api/dependencies.py`, `api/middleware/rate_limit.py`

**Архитектурная очистка:**

1. **video_processing_module/config.py**: 164 строки → 21 строка (minimal dataclass, -88%)
2. **RateLimitMiddleware**: 113 → 72 строки, без параметров в __init__, читает из settings (-36%)
3. **ZoomConfig** вынесен: config/settings.py → models/ (Separation of Concerns)

**Результат:** config/settings.py: 599 строк, zero legacy, DRY/KISS/YAGNI

---

## 🔐 Zoom Authentication - Pydantic Models (18 января 2026)

**Проблема:** Два типа аутентификации (Server-to-Server + OAuth 2.0) в одном @dataclass без различия

**Решение:** `models/zoom_auth.py` (91 строка) с Pydantic дискриминатором

**Модели:**
1. **ZoomServerToServerCredentials**
   - auth_type: "server_to_server", account, account_id, client_id, client_secret
   - Frozen, validated (min_length=1)

2. **ZoomOAuthCredentials**
   - auth_type: "oauth", access_token, refresh_token, token_type, scope, expiry
   - @computed_field is_expired property
   - Frozen, validated

3. **create_zoom_credentials()** - auto-detect helper

**Обновлено 4 файла:**
- `api/helpers/config_helper.py` - использует create_zoom_credentials()
- `api/zoom_api.py` - isinstance() проверки
- `api/token_manager.py` - только ZoomServerToServerCredentials
- `api/routers/input_sources.py` - 19 строк → 2 строки (-89%)

**Преимущества:**
- ✅ Type safety 100% (было 50%)
- ✅ Pydantic validation + JSON serialization
- ✅ Discriminator auto-detection
- ✅ Immutable (frozen=True)
- ✅ Computed properties (is_expired)

**Удалено:** `models/zoom_config.py` (21 строка simple @dataclass)

---

## 🚀 Production Configuration Updates (18 января 2026)

### Scaling for 10+ users (5-10 recordings each)

**Changes:**
- ✅ Increased Celery worker concurrency: 4 → 8 workers
- ✅ Enabled API service in docker-compose.yml (4 FastAPI workers)
- ✅ Added Celery Beat scheduler service for automation jobs
- ✅ Updated Makefile dev commands to use concurrency=8

**Files modified:**
- `docker-compose.yml` - API uncommented, concurrency increased, celery_beat added
- `Makefile` - Updated celery and celery-dev targets

**Performance:** Supports 8 parallel tasks (up from 4), sufficient for 10 users with 5-10 recordings each

---

## 🔒 Bug Fixes: OAuth & YouTube Upload (18 января 2026)

### Bug Fixes: OAuth & YouTube Upload

**Проблемы:**
- OAuth callback падал с UniqueViolationError при повторной авторизации
- YouTube upload падал с TypeError при форматировании topics
- MediaFileUpload использовал устаревший chunksize=-1

**Исправления:**
- ✅ OAuth upsert pattern: автоопределение account_name (email для YouTube/Zoom, user_id для VK)
- ✅ Добавлены scopes `openid` и `email` для получения user info из Google API
- ✅ Template renderer: обработка None значений в min_length/max_length
- ✅ YouTube uploader: chunksize=10MB вместо deprecated -1
- ✅ Проверка category_id на None перед передачей в upload

**Результат:** Поддержка множественных OAuth аккаунтов + стабильная загрузка на YouTube

---

## 🔒 Обновления (15 января 2026)

### Завершена полная изоляция данных пользователей

**Изменения:**
- Все Celery задачи переведены на `BaseTask` с методами `update_progress()` и `build_result()`
- `user_id` автоматически встраивается во все метаданные и результаты задач
- Добавлен `AutomationTask` базовый класс для задач автоматизации
- `TaskAccessService` теперь корректно проверяет владение задачами по `user_id` из метаданных

**Затронутые модули:**
- `api/tasks/base.py` - добавлен `AutomationTask`
- `api/tasks/automation.py` - 2 задачи переведены на `AutomationTask`
- `api/tasks/processing.py` - 6 задач обновлены (download, trim, transcribe, batch_transcribe, extract_topics, generate_subtitles, process_recording)
- `api/tasks/sync_tasks.py` - 2 задачи обновлены (sync_single_source, bulk_sync_sources)
- `api/tasks/template.py` - 1 задача обновлена (rematch_recordings)
- `api/tasks/upload.py` - 2 задачи обновлены (upload_recording_to_platform, batch_upload_recordings)

**Результат:** 100% изоляция данных пользователей на уровне API и Celery задач

---

## 📖 Что это

Трансформация CLI-приложения в полноценный **Multi-tenant SaaS** с REST API:
- Multi-user с изоляцией данных
- Асинхронная обработка (Celery + Redis)
- Template-driven automation
- OAuth 2.0 для YouTube, VK, Zoom
- Subscription plans с квотами
- Admin API для мониторинга

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────┐
│       REST API (FastAPI)                │
│       84 endpoints                      │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│    OAuth 2.0 (JWT + Refresh)            │
│    YouTube ✅ VK ✅ Zoom ✅              │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│  Multi-tenant (user_id isolation)       │
│  ├── credentials (encrypted)            │
│  ├── recordings + templates             │
│  ├── subscriptions + quotas             │
│  └── media/user_{id}/                   │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│  Async Processing (Celery + Redis)      │
│  ├── download → process → transcribe    │
│  ├── topics → subtitles → upload        │
│  └── automation (scheduled jobs)        │
└─────────────────────────────────────────┘
```

---

## 📊 База данных (12 таблиц)

### Authentication & Users
- `users` - пользователи (role, permissions, timezone)
- `refresh_tokens` - JWT refresh tokens
- `user_credentials` - зашифрованные credentials (Fernet)
- `user_configs` - unified config (1:1 с users)

### Subscription & Quotas
- `subscription_plans` - кастомные тарифные планы
- `user_subscriptions` - подписки пользователей (с custom overrides)
- `quota_usage` - использование по периодам (YYYYMM)
- Дефолтные лимиты: `DEFAULT_QUOTAS` в `config/settings.py` (все `None` = безлимит)

### Processing
- `recordings` - записи (status, template_id, processing_preferences)
- `recording_templates` - шаблоны (matching_rules, processing_config, output_config)
- `input_sources` - источники (Zoom, local)
- `output_presets` - пресеты для загрузки (YouTube, VK с metadata)

### Automation
- `automation_jobs` - scheduled jobs
- `processing_stages` - отслеживание этапов обработки
- `output_targets` - отслеживание загрузок по платформам

**Миграции:** 19 (автоматическая инициализация при первом запуске)

---

## 🎨 API Endpoints (84)

### Core Categories

**Authentication** (5): register, login, refresh, logout, logout-all
**Users** (6): me, config, quota, stats, password, delete
**Admin** (3): stats/overview, stats/users, stats/quotas

**Recordings** (18):
- CRUD + details, process, transcribe, topics, subtitles, upload
- run (smart), pause, bulk-run, bulk-pause, bulk-transcribe, sync
- config management (get, update, save-as-template, reset)
- unmapped recordings list

**Templates** (8):
- CRUD + from-recording
- stats, preview-match, rematch, preview-rematch

**Credentials** (6): CRUD + status, VK token API
**Input Sources** (6): CRUD + sync, bulk-sync
**Output Presets** (5): CRUD

**OAuth** (6): YouTube, VK, Zoom (authorize + callback)
**Automation** (6): jobs CRUD + run, dry-run
**Tasks** (2): status + progress, cancel
**Health** (1)

**Swagger UI:** http://localhost:8000/docs

---

## ✨ Ключевые фичи

### 1. Template-driven Recording Pipeline

**Архитектура:**
```
Sync → Auto-match template → Recording + template_id
     → Config resolution (user < template < manual)
     → Full pipeline → Output tracking
```

**Config Hierarchy:**
1. User config (defaults)
2. Template config (if template_id set) - читается live
3. recording.processing_preferences (manual override - highest)

**Ключевые endpoints:**
- `GET/PUT /recordings/{id}/config` - manual config management
- `DELETE /recordings/{id}/config` - reset to template
- `POST /recordings/{id}/config/save-as-template` - create template from config
- `POST /recordings/{id}/run` - unified smart run (start, continue, retry)
- `POST /recordings/{id}/pause` - soft pause (graceful stop)
- `POST /recordings/{id}/reset` - reset to INITIALIZED state
- `POST /recordings/bulk/run` - smart bulk run
- `POST /recordings/bulk/pause` - bulk pause
- `POST /templates/{id}/rematch` - re-match recordings to templates

**Matching Rules:**
- `exact_matches` - точные совпадения
- `keywords` - ключевые слова (case-insensitive)
- `patterns` - regex паттерны
- `source_ids` - фильтр по источникам

Strategy: **first_match** (по `created_at ASC`)

### 2. OAuth 2.0 Integration

**YouTube:**
- Full OAuth 2.0 flow
- Automatic token refresh
- Multi-user support

**VK:**
- VK ID OAuth 2.1 с PKCE (для legacy apps)
- Implicit Flow API (для новых проектов, доступен всем)
- Service Token support
- Automatic token validation

**Zoom:**
- OAuth 2.0 (user-level scopes)
- Dual-mode: OAuth + Server-to-Server
- Auto-detection credentials type

### 3. Quota & Stats System

- **DEFAULT_QUOTAS** в `config/settings.py` — дефолтные лимиты (все `None` = безлимит)
- Подписка назначается только вручную (кастомный план)
- `GET /me/quota` — текущий статус квот
- `GET /me/stats` — статистика (записи, транскрипции, хранилище) с фильтрацией по датам
- Usage tracking по периодам (YYYYMM)
- Custom overrides per-user через `user_subscriptions`

### 4. Automation System

**Declarative Schedules:**
- `time_of_day` - daily at 6am
- `hours` - every N hours
- `weekdays` - specific days + time
- `cron` - custom expressions

**Features:**
- Auto-sync + template matching
- Batch processing
- Dry-run mode (preview без changes)
- Quota management (max jobs, min interval)

### 5. Preset Metadata System

**Template Rendering:**
- Variables: `{display_name}`, `{duration}`, `{record_time}`, `{publish_time}`, `{themes}`, `{topics}`
- Inline time formatting: `{record_time:DD.MM.YYYY}`, `{publish_time:date}`, `{record_time:DD-MM-YY hh:mm}`
- Format tokens: DD, MM, YY, YYYY, hh, mm, ss, date, time, datetime
- Topics display: 5 форматов (numbered_list, bullet_list, dash_list, comma_separated, inline)
- Timestamps in topics: `00:02:36 — Название темы`
- Фильтрация: min_length, max_length, max_count (null = безлимит)
- Architecture: preset (platform defaults) ← template (content-specific + overrides) ← manual override

**YouTube:**
- publishAt (scheduled publishing)
- tags, category_id, playlist_id
- made_for_kids, embeddable, license
- thumbnail support

**VK:**
- group_id, album_id
- privacy_view, privacy_comment
- wallpost, no_comments, repeat
- thumbnail support

### 6. Transcription

**Fireworks API:**
- Sync API (real-time)
- Batch API (экономия ~50%, polling)

**Pipeline:**
1. Transcribe → master.json (words, segments)
2. Extract topics → extracted.json (versioning support)
3. Generate subtitles → .srt, .vtt

**Admin-only credentials** (security)

---

## 🔄 Changelog (хронология ключевых изменений)

### 14 января 2026 - Pydantic V2 Best Practices & Clean Architecture

#### Рефакторинг схем (v2)
- ✅ Чистые валидаторы: оставлены только специфичные (validate_regex_pattern, clean_and_deduplicate_strings)
- ✅ Удалены валидаторы дублирующие Pydantic Field (validate_name, validate_positive_int)
- ✅ Миграция на `model_config` (BASE_MODEL_CONFIG, ORM_MODEL_CONFIG)
- ✅ Field Constraints вместо custom валидаторов: `Field(gt=0, min_length=3, max_length=255)`
- ✅ Обновлены все template/* схемы (13 файлов)
- ✅ Порядок полей в Swagger = порядок определения в классе
- ✅ 0 lint errors, API работает успешно

#### Полная типизация API (v1)
- ✅ 71/95 routes типизированы, 118 моделей в OpenAPI
- ✅ Базовые схемы: common/responses.py, task/status.py
- ✅ Полная типизация Templates/Presets/Sources
- ✅ Вложенные модели: MatchingRules, TranscriptionProcessingConfig, TemplateMetadataConfig
- ✅ 15+ типизированных моделей, 6 Enum'ов
- ✅ +1282/-476 строк, KISS/DRY/YAGNI соблюдены

#### Bulk Operations & Template Lifecycle
- ✅ Переименованы endpoints: `/batch/*` → `/bulk/*`
- ✅ Unified request schema `BulkOperationRequest` (recording_ids OR filters)
- ✅ Новые bulk endpoints: download, trim, topics, subtitles, upload
- ✅ Переименованы operations: `process` (FFmpeg trim) → `trim`, `full-pipeline` → `process`
- ✅ Dry-run support для single и bulk процессов
- ✅ RecordingFilters расширены: template_id, source_id, is_mapped, exclude_blank, failed
- ✅ Auto-unmap при удалении template
- 🐛 FIX: metadata_config терялся при создании template
- 🐛 FIX: /bulk/sync возвращал 422 (исправлен порядок роутов)
- 🐛 FIX: Фильтр status: ["FAILED"] вызывал database error

### 12 января 2026 - CLI Legacy Removal & Architecture Cleanup

#### CLI Removal
- ❌ Удалены legacy файлы: main.py (1,360 lines), cli_helpers.py, setup_vk.py, setup_youtube.py
- ❌ Очищен pipeline_manager.py (удалены 7 CLI-specific методов)
- ❌ Очищен Makefile (удалены CLI команды)
- ✅ Migration path: REST API вместо CLI
- ✅ Benefits: -2,000+ строк legacy кода, чище архитектура

#### Template Config Live Update
- ✅ Template config читается live (не кэшируется)
- ✅ processing_preferences хранит только user overrides
- ✅ Добавлен `DELETE /recordings/{id}/config` для reset to template
- ✅ Template updates автоматически применяются ко всем recordings

#### Audio Path Fix
- ✅ Migration 019: `processed_audio_dir` → `processed_audio_path`
- ✅ Каждая запись хранит specific file path
- ✅ Исключена cross-contamination между recordings
- ✅ Smart matching (score-based) в миграции

### 11 января 2026 - Upload Metadata & Filtering

#### Topics Timestamps + Playlist Fix
- ✅ Временные метки в топиках: `HH:MM:SS — Название темы`
- ✅ show_timestamps: true в topics_display конфигурации
- ✅ Автоформатирование секунд в HH:MM:SS
- 🐛 FIX: Playlist не добавлялся → исправлен поиск playlist_id
- 🐛 FIX: Thumbnail не добавлялся → добавлена поддержка thumbnail_path
- 🐛 FIX: Response endpoint показывал upload: false

#### Error Handling & Reset
- 🐛 FIX: ResponseValidationError падал с 500 + logger KeyError
- 🐛 FIX: Logger использовал f-string с exception
- ✅ Endpoint `POST /recordings/{id}/reset` для сброса в INITIALIZED
- ✅ Reset удаляет файлы, output_targets, processing_stages

#### Upload Metadata Fixes
- 🐛 FIX: VK preset validation error (privacy_view был строкой вместо int)
- ✅ Добавлены default metadata templates в output presets
- ✅ Fallback description использует TemplateRenderer
- ✅ VK thumbnail & album fix: проверка nested 'vk' объекта

#### Blank Records Filtering
- ✅ Флаг blank_record для коротких записей (< 20 мин ИЛИ < 25 МБ)
- ✅ Автоопределение при sync, автоматический skip в pipeline
- ✅ Фильтры по датам: from_date / to_date
- ✅ Migration 018 с автоматическим backfill
- 🐛 FIX: auto_upload читался из неправильного места
- 🐛 FIX: Убран .get() в full_pipeline_task (Celery anti-pattern)

#### Template Variables Refactoring
- ✅ Убрали {summary} (не существует в БД)
- ✅ Переименовали: {main_topics} → {themes}, {topics_list} → {topics}
- ✅ Добавили {record_time} и {publish_time} с форматированием
- ✅ Inline форматирование времени: {publish_time:DD-MM-YY hh:mm}
- ✅ Regex парсинг параметров в placeholders

#### Output Preset Refactoring
- ✅ Separation of concerns: preset (platform defaults) vs template (content-specific)
- ✅ Deep merge metadata hierarchy: preset → template → manual override
- ✅ ConfigResolver.resolve_upload_metadata() method

#### Template-driven Pipeline Complete
- ✅ Template matching в sync (auto-assign template_id)
- ✅ Config resolution hierarchy
- ✅ Template re-match feature (auto + manual + preview)
- ✅ Recording config management endpoints
- ✅ Batch processing (mapped/unmapped)
- ✅ Upload retry mechanism
- ✅ Output targets FSM tracking

#### Celery PYTHONPATH Fix
- 🐛 FIX: Celery не видел обновления кода
- ✅ Добавлен PYTHONPATH в команду запуска
- ✅ Timestamps, playlist, thumbnail работают корректно

### 10 января 2026 - OAuth Complete + Fireworks Batch
- ✅ Zoom OAuth 2.0 (user-level scopes)
- ✅ VK Token API (Implicit Flow)
- ✅ Async sync через Celery
- ✅ Fireworks Batch API (экономия ~50%)

### 9 января 2026 - Subscription System Refactoring
- ✅ Subscription plans architecture (Free/Plus/Pro/Enterprise)
- ✅ Quota system (DEFAULT_QUOTAS, enforcement middleware, usage tracking)
- ✅ User stats API (recordings, transcription, storage)
- ✅ Admin Stats API (3 endpoints)
- ✅ API consistency fixes (100% RESTful)

### 8 января 2026 - Preset Metadata + VK OAuth 2.1
- ✅ Template rendering system (10+ variables)
- ✅ Topics display (5 форматов)
- ✅ YouTube: publishAt + все параметры
- ✅ VK: все параметры публикации
- ✅ VK ID OAuth 2.1 с PKCE (production ready)
- ✅ Credentials validation

### 7 января 2026 - Security Hardening
- ✅ Token validation через БД
- ✅ Logout all devices
- ✅ Automatic expired tokens cleanup
- ✅ User timezone support

### 6 января 2026 - OAuth + Automation
- ✅ YouTube OAuth 2.0 (web-based)
- ✅ VK OAuth 2.1 (web-based)
- ✅ Automation system (Celery Beat + declarative schedules)

### 5 января 2026 - Core Infrastructure
- ✅ Celery integration (async tasks)
- ✅ Unified config system
- ✅ User Management API
- ✅ Thumbnails multi-tenancy
- ✅ Transcription pipeline refactoring

### 2-4 января 2026 - Foundation
- ✅ Multi-tenant architecture
- ✅ JWT authentication
- ✅ Repository pattern
- ✅ Recordings API
- ✅ Template system basics


**Статус:** 🎉 **Production-Ready!**
