# Database Design - LEAP Platform

**Версия БД:** 10 миграций
**Последнее обновление:** Февраль 2026
**Статус:** Production-Ready

---

## 📋 Содержание

1. [Обзор](#обзор)
2. [Архитектура](#архитектура)
3. [Таблицы](#таблицы)
4. [JSONB Structures](#jsonb-structures)
5. [Индексы и производительность](#индексы-и-производительность)
6. [Миграции](#миграции)

---

## Обзор

### Статистика

**15 таблиц:**
- Authentication & Users (5 таблиц)
- Subscription & Quotas (4 таблицы)
- Processing (4 таблицы)
- Templates & Configuration (4 таблицы)
- Automation (2 таблицы)

**10 миграций** (автоматическая инициализация)

**PostgreSQL версия:** 12+

### Multi-Tenancy

**Isolation Strategy:** Shared Database + Row-Level Filtering

Все таблицы с `user_id` имеют:
- Type: `VARCHAR(26)` (ULID strings)
- Foreign Key: `REFERENCES users(id) ON DELETE CASCADE`
- Index: `idx_{table}_user_id ON {table}(user_id)`
- Автоматическая фильтрация в Repository Layer

---

## Архитектура

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    AUTHENTICATION                        │
└─────────────────────────────────────────────────────────┘
                          users
                   (id: ULID, user_slug: INT)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
  refresh_tokens    user_credentials    user_configs

┌─────────────────────────────────────────────────────────┐
│                    SUBSCRIPTIONS                         │
└─────────────────────────────────────────────────────────┘
       subscription_plans
                │
        user_subscriptions (user ← plan)
                │
        ┌───────┴────────┐
   quota_usage   quota_change_history

┌─────────────────────────────────────────────────────────┐
│                      PROCESSING                          │
└─────────────────────────────────────────────────────────┘
   recording_templates ─┐
                        │
   input_sources ───────┼─┐
                        │ │
   output_presets ──────┼─┼─┐
                        │ │ │
                recordings ←┘ │
                │   │         │
     source_metadata  │       │
                │     │       │
          output_targets ←────┘
                │
        processing_stages

┌─────────────────────────────────────────────────────────┐
│                     AUTOMATION                           │
└─────────────────────────────────────────────────────────┘
   automation_jobs (schedule + template + sources)
        │
   celery_beat_schedule_entry (Celery Beat integration)
```

---

## Таблицы

### 🔐 Authentication & Users

#### 1. `users`

**Назначение:** Пользователи системы с RBAC permissions

```sql
CREATE TABLE users (
    -- Identity (ULID-based)
    id VARCHAR(26) PRIMARY KEY,  -- ULID string: "01HQ123456789ABCDEFGHJKMNP"
    user_slug INTEGER UNIQUE NOT NULL,  -- Sequential for storage paths: 1, 2, 3...

    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),

    -- Status
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    role VARCHAR(50) DEFAULT 'user' NOT NULL,  -- 'user', 'admin'

    -- RBAC Permissions
    can_transcribe BOOLEAN DEFAULT TRUE NOT NULL,
    can_process_video BOOLEAN DEFAULT TRUE NOT NULL,
    can_upload BOOLEAN DEFAULT TRUE NOT NULL,
    can_create_templates BOOLEAN DEFAULT TRUE NOT NULL,
    can_delete_recordings BOOLEAN DEFAULT TRUE NOT NULL,
    can_update_uploaded_videos BOOLEAN DEFAULT TRUE NOT NULL,
    can_manage_credentials BOOLEAN DEFAULT TRUE NOT NULL,
    can_export_data BOOLEAN DEFAULT TRUE NOT NULL,

    -- Settings
    timezone VARCHAR(50) DEFAULT 'UTC' NOT NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    last_login_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_user_slug ON users(user_slug);
CREATE INDEX idx_users_active ON users(is_active, role);
CREATE SEQUENCE user_slug_seq;
```

**Key Points:**
- `id`: ULID (26 chars) - used in API and database relations
- `user_slug`: Sequential integer - used for storage paths (`storage/users/user_000001/`)
- 8 granular permissions for RBAC

**Связи:**
- 1:N → user_credentials, recordings, templates, input_sources, output_presets
- 1:1 → user_configs
- 1:1 → user_subscriptions

---

#### 2. `refresh_tokens`

**Назначение:** JWT refresh tokens для безопасной аутентификации

```sql
CREATE TABLE refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(500) NOT NULL UNIQUE,

    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked BOOLEAN DEFAULT FALSE,

    -- Security metadata
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token) WHERE NOT revoked;
CREATE INDEX idx_refresh_tokens_expiry ON refresh_tokens(expires_at) WHERE NOT revoked;
```

**Features:**
- Token rotation (auto-revoke old tokens)
- Logout all devices (revoke all tokens)
- Automatic cleanup (expired tokens)

---

#### 3. `user_credentials`

**Назначение:** Зашифрованные credentials для внешних сервисов

```sql
CREATE TABLE user_credentials (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Platform identification
    platform VARCHAR(50) NOT NULL,  -- zoom, youtube, vk, fireworks, deepseek
    account_name VARCHAR(255),      -- For multiple accounts

    -- Encrypted data (Fernet)
    encrypted_data TEXT NOT NULL,

    -- Metadata
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_user_platform_account UNIQUE (user_id, platform, account_name)
);

CREATE INDEX idx_user_credentials_user ON user_credentials(user_id, platform);
CREATE INDEX idx_user_credentials_active ON user_credentials(is_active);
```

**Supported Platforms:**
- `zoom` - Zoom OAuth/Server-to-Server
- `youtube` - YouTube OAuth 2.0
- `vk` - VK Implicit Flow (2026 policy)
- `fireworks` - Fireworks API key
- `deepseek` - DeepSeek API key

**Encryption:** Fernet (symmetric, AES-128)

---

#### 4. `user_configs`

**Назначение:** Unified user-specific default configurations (1:1)

```sql
CREATE TABLE user_configs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,

    -- Default configurations (deep merged with template configs)
    processing_config JSONB DEFAULT '{}',
    transcription_config JSONB DEFAULT '{}',
    metadata_config JSONB DEFAULT '{}',
    upload_config JSONB DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_configs_user ON user_configs(user_id);
```

**См:** [JSONB Structures](#jsonb-structures) для формата конфигураций

---

#### 5. `base_configs`

**Назначение:** Global or user-specific base configurations

```sql
CREATE TABLE base_configs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) REFERENCES users(id) ON DELETE CASCADE,  -- NULL = global

    name VARCHAR(255) NOT NULL,
    description TEXT,
    config_type VARCHAR(50),  -- 'processing', 'metadata', etc.
    config_data JSONB NOT NULL,

    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_base_configs_user ON base_configs(user_id, config_type);
CREATE INDEX idx_base_configs_type ON base_configs(config_type, is_active);
```

---

### 💰 Subscription & Quotas

#### 6. `subscription_plans`

**Назначение:** Тарифные планы (Free/Plus/Pro/Enterprise)

```sql
CREATE TABLE subscription_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,  -- Free, Plus, Pro, Enterprise
    display_name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Quotas
    included_recordings_per_month INTEGER,
    included_storage_gb INTEGER,
    max_concurrent_tasks INTEGER,
    max_automation_jobs INTEGER,
    min_automation_interval_hours INTEGER,

    -- Pricing
    price_monthly DECIMAL(10, 2) DEFAULT 0 NOT NULL,
    price_yearly DECIMAL(10, 2) DEFAULT 0 NOT NULL,
    overage_price_per_unit DECIMAL(10, 4),
    overage_unit_type VARCHAR(50),

    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    sort_order INTEGER DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_subscription_plans_active ON subscription_plans(is_active, sort_order);
```

---

#### 7. `user_subscriptions`

**Назначение:** Подписки пользователей с custom overrides

```sql
CREATE TABLE user_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER NOT NULL REFERENCES subscription_plans(id) ON DELETE RESTRICT,

    -- Custom quota overrides (NULL = use plan default)
    custom_max_recordings_per_month INTEGER,
    custom_max_storage_gb INTEGER,
    custom_max_concurrent_tasks INTEGER,
    custom_max_automation_jobs INTEGER,
    custom_min_automation_interval_hours INTEGER,

    -- Pay-as-you-go
    pay_as_you_go_enabled BOOLEAN DEFAULT FALSE NOT NULL,
    pay_as_you_go_monthly_limit DECIMAL(10, 2),

    -- Period
    starts_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Audit
    created_by VARCHAR(26) REFERENCES users(id) ON DELETE SET NULL,
    modified_by VARCHAR(26) REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_subscriptions_user ON user_subscriptions(user_id);
CREATE INDEX idx_user_subscriptions_plan ON user_subscriptions(plan_id);
CREATE INDEX idx_user_subscriptions_expires ON user_subscriptions(expires_at);
```

---

#### 8. `quota_usage`

**Назначение:** Отслеживание использования по периодам

```sql
CREATE TABLE quota_usage (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period VARCHAR(6) NOT NULL,  -- YYYYMM format

    -- Usage counters
    recordings_count INTEGER DEFAULT 0,
    storage_used_gb DECIMAL(10, 2) DEFAULT 0,
    tasks_run_count INTEGER DEFAULT 0,
    automation_runs_count INTEGER DEFAULT 0,

    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_user_period UNIQUE (user_id, period)
);

CREATE INDEX idx_quota_usage_user_period ON quota_usage(user_id, period DESC);
```

---

#### 9. `quota_change_history`

**Назначение:** Audit trail для изменений квот

```sql
CREATE TABLE quota_change_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    admin_user_id VARCHAR(26) REFERENCES users(id) ON DELETE SET NULL,

    change_type VARCHAR(50) NOT NULL,  -- plan_upgrade, custom_quota_override
    old_value JSONB,
    new_value JSONB,
    reason TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_quota_history_user ON quota_change_history(user_id, created_at DESC);
```

---

### 🎬 Processing

#### 10. `recordings`

**Назначение:** Основная таблица записей

```sql
CREATE TABLE recordings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) REFERENCES users(id) ON DELETE CASCADE,

    -- Template & Source mapping
    input_source_id INTEGER REFERENCES input_sources(id) ON DELETE SET NULL,
    template_id INTEGER REFERENCES recording_templates(id) ON DELETE SET NULL,
    is_mapped BOOLEAN DEFAULT FALSE,

    -- Basic info
    display_name VARCHAR(500) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    duration INTEGER NOT NULL,  -- seconds

    -- Processing status (FSM)
    status VARCHAR(50) NOT NULL DEFAULT 'INITIALIZED',

    -- Flags
    blank_record BOOLEAN DEFAULT FALSE,

    -- File paths (ID-based structure)
    local_video_path VARCHAR(1000),
    processed_video_path VARCHAR(1000),
    processed_audio_path VARCHAR(1000),
    transcription_dir VARCHAR(1000),

    -- Transcription results
    transcription_info JSONB,
    topic_timestamps JSONB,
    main_topics JSONB,

    -- Template overrides
    processing_preferences JSONB,

    -- Deletion (soft + hard delete)
    deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    delete_state VARCHAR(20) DEFAULT 'active',  -- active, soft_deleted, hard_deleted
    deletion_reason VARCHAR(20),
    soft_deleted_at TIMESTAMP WITH TIME ZONE,
    hard_delete_at TIMESTAMP WITH TIME ZONE,

    -- Expiration
    expire_at TIMESTAMP WITH TIME ZONE,

    -- Failure tracking (FSM)
    failed BOOLEAN DEFAULT FALSE,
    failed_at TIMESTAMP WITH TIME ZONE,
    failed_reason VARCHAR(1000),
    failed_at_stage VARCHAR(50),
    retry_count INTEGER DEFAULT 0,

    -- Timestamps
    downloaded_at TIMESTAMP WITH TIME ZONE,
    video_file_size BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_recordings_user ON recordings(user_id, created_at DESC);
CREATE INDEX idx_recordings_status ON recordings(status, user_id);
CREATE INDEX idx_recordings_template ON recordings(template_id, status);
CREATE INDEX idx_recordings_source ON recordings(input_source_id);
CREATE INDEX idx_recordings_mapped ON recordings(is_mapped, user_id);
CREATE INDEX idx_recordings_blank ON recordings(blank_record, user_id);
CREATE INDEX idx_recordings_deleted ON recordings(deleted, user_id);
CREATE INDEX idx_recordings_delete_state ON recordings(delete_state);
CREATE INDEX idx_recordings_failed ON recordings(failed, user_id) WHERE failed = TRUE;
```

**Processing Status (FSM):**
- `PENDING_SOURCE` - Awaiting source processing
- `INITIALIZED` - Ready for download
- `DOWNLOADING` → `DOWNLOADED`
- `PROCESSING` → `PROCESSED`
- `UPLOADING` → `READY`
- `FAILED` - Failed at stage
- `SKIPPED` - Skipped processing

**Key Fields:**
- `blank_record`: duration < 20min OR size < 25MB (auto-skip)
- `delete_state`: Soft delete → hard delete workflow
- `processing_preferences`: Per-recording config overrides

---

#### 11. `source_metadata`

**Назначение:** Метаданные источника (1:1 с recordings)

```sql
CREATE TABLE source_metadata (
    id SERIAL PRIMARY KEY,
    recording_id INTEGER NOT NULL UNIQUE REFERENCES recordings(id) ON DELETE CASCADE,
    user_id VARCHAR(26) REFERENCES users(id) ON DELETE CASCADE,
    input_source_id INTEGER REFERENCES input_sources(id) ON DELETE SET NULL,

    source_type VARCHAR(50) NOT NULL,  -- ZOOM, LOCAL_FILE
    source_key VARCHAR(1000) NOT NULL,  -- Unique ID in source
    meta JSONB,  -- Raw metadata from source ("metadata" column in DB)

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_source_per_recording UNIQUE (source_type, source_key, recording_id)
);

CREATE INDEX idx_source_metadata_recording ON source_metadata(recording_id);
CREATE INDEX idx_source_metadata_source ON source_metadata(source_type, source_key);
CREATE INDEX idx_source_metadata_user ON source_metadata(user_id);
CREATE INDEX idx_source_metadata_input_source ON source_metadata(input_source_id);
```

---

#### 12. `output_targets`

**Назначение:** Отслеживание загрузок по платформам (1:N)

```sql
CREATE TABLE output_targets (
    id SERIAL PRIMARY KEY,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    user_id VARCHAR(26) REFERENCES users(id) ON DELETE CASCADE,
    preset_id INTEGER REFERENCES output_presets(id) ON DELETE SET NULL,

    target_type VARCHAR(50) NOT NULL,  -- YOUTUBE, VK
    status VARCHAR(50) NOT NULL DEFAULT 'NOT_UPLOADED',  -- FSM

    target_meta JSONB,  -- Platform-specific: video_id, url, etc.

    uploaded_at TIMESTAMP WITH TIME ZONE,

    -- Failure tracking (FSM)
    failed BOOLEAN DEFAULT FALSE,
    failed_at TIMESTAMP WITH TIME ZONE,
    failed_reason VARCHAR(1000),
    retry_count INTEGER DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_target_per_recording UNIQUE (recording_id, target_type)
);

CREATE INDEX idx_output_targets_recording ON output_targets(recording_id);
CREATE INDEX idx_output_targets_user ON output_targets(user_id);
CREATE INDEX idx_output_targets_preset ON output_targets(preset_id);
CREATE INDEX idx_output_targets_status ON output_targets(target_type, status);
CREATE INDEX idx_output_targets_failed ON output_targets(status) WHERE status = 'FAILED';
```

**Target Status (FSM):**
- `NOT_UPLOADED` → `UPLOADING` → `UPLOADED`
- `NOT_UPLOADED` → `FAILED`
- `UPLOADING` → `FAILED`
- `FAILED` → `UPLOADING` (retry)

---

#### 13. `processing_stages`

**Назначение:** Детальное отслеживание этапов обработки (FSM)

```sql
CREATE TABLE processing_stages (
    id SERIAL PRIMARY KEY,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    user_id VARCHAR(26) REFERENCES users(id) ON DELETE CASCADE,

    stage_type VARCHAR(50) NOT NULL,  -- TRANSCRIBE, EXTRACT_TOPICS, GENERATE_SUBTITLES, TRIM
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',  -- PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED

    -- Timing
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Failure tracking
    failed BOOLEAN DEFAULT FALSE,
    failed_at TIMESTAMP WITH TIME ZONE,
    failed_reason VARCHAR(1000),
    skip_reason VARCHAR(500),
    retry_count INTEGER DEFAULT 0,

    -- Metadata
    stage_meta JSONB,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_stage_per_recording UNIQUE (recording_id, stage_type)
);

CREATE INDEX idx_processing_stages_recording ON processing_stages(recording_id);
CREATE INDEX idx_processing_stages_user ON processing_stages(user_id);
CREATE INDEX idx_processing_stages_status ON processing_stages(status, stage_type);
```

**Stage Types:**
- `TRANSCRIBE` - Audio transcription (Fireworks Whisper)
- `EXTRACT_TOPICS` - Topic extraction (DeepSeek)
- `GENERATE_SUBTITLES` - SRT/VTT generation
- `TRIM` - Silence removal (FFmpeg)

**Status Flow:**
- `PENDING` → `IN_PROGRESS` → `COMPLETED`
- `PENDING` → `SKIPPED` (not enabled)
- `IN_PROGRESS` → `FAILED`

---

### 📋 Templates & Configuration

#### 14. `recording_templates`

**Назначение:** Шаблоны для автоматической обработки

```sql
CREATE TABLE recording_templates (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Matching rules
    matching_rules JSONB,

    -- Configuration (deep merge with user defaults)
    processing_config JSONB,
    metadata_config JSONB,
    output_config JSONB,

    -- Flags
    is_draft BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_user_template_name UNIQUE (user_id, name)
);

CREATE INDEX idx_recording_templates_user ON recording_templates(user_id, is_active);
CREATE INDEX idx_recording_templates_active ON recording_templates(is_active, created_at);
```

**См:** [JSONB Structures](#jsonb-structures) для формата конфигураций

---

#### 15. `input_sources`

**Назначение:** Источники данных для синхронизации

```sql
CREATE TABLE input_sources (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name VARCHAR(255) NOT NULL,
    description TEXT,
    source_type VARCHAR(50) NOT NULL,  -- ZOOM
    credential_id INTEGER REFERENCES user_credentials(id) ON DELETE SET NULL,

    config JSONB,  -- Source-specific configuration

    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_input_sources_user_name_type_credential
        UNIQUE (user_id, name, source_type, credential_id)
);

CREATE INDEX idx_input_sources_user ON input_sources(user_id, is_active);
CREATE INDEX idx_input_sources_credential ON input_sources(credential_id);
CREATE INDEX idx_input_sources_type ON input_sources(source_type);
```

---

#### 16. `output_presets`

**Назначение:** Пресеты для загрузки на платформы

```sql
CREATE TABLE output_presets (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name VARCHAR(255) NOT NULL,
    description TEXT,
    platform VARCHAR(50) NOT NULL,  -- YOUTUBE, VK
    credential_id INTEGER NOT NULL REFERENCES user_credentials(id) ON DELETE CASCADE,

    preset_metadata JSONB,  -- Platform-specific settings

    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_user_preset_name UNIQUE (user_id, name)
);

CREATE INDEX idx_output_presets_user ON output_presets(user_id, is_active);
CREATE INDEX idx_output_presets_platform ON output_presets(platform, is_active);
CREATE INDEX idx_output_presets_credential ON output_presets(credential_id);
```

---

### ⏰ Automation

#### 17. `automation_jobs`

**Назначение:** Scheduled jobs для автоматизации (Celery Beat)

```sql
CREATE TABLE automation_jobs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_id INTEGER REFERENCES recording_templates(id) ON DELETE CASCADE,

    name VARCHAR(255) NOT NULL,
    description TEXT,
    job_type VARCHAR(50) NOT NULL,  -- sync_and_process, process_recordings

    -- Schedule (crontab or interval)
    schedule_type VARCHAR(20) NOT NULL,  -- crontab, interval
    crontab_minute VARCHAR(100),
    crontab_hour VARCHAR(100),
    crontab_day_of_week VARCHAR(100),
    crontab_day_of_month VARCHAR(100),
    crontab_month_of_year VARCHAR(100),
    interval_every INTEGER,
    interval_period VARCHAR(20),  -- seconds, minutes, hours, days

    -- Sources to process
    source_ids JSONB,  -- [1, 2, 3] or [] for all

    enabled BOOLEAN DEFAULT TRUE,
    last_run_at TIMESTAMP WITH TIME ZONE,
    last_run_status VARCHAR(50),
    last_run_error TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_user_job_name UNIQUE (user_id, name)
);

CREATE INDEX idx_automation_jobs_user ON automation_jobs(user_id, enabled);
CREATE INDEX idx_automation_jobs_template ON automation_jobs(template_id);
CREATE INDEX idx_automation_jobs_enabled ON automation_jobs(enabled);
```

**Job Types:**
- `sync_and_process` - Sync from sources + auto-process with template
- `process_recordings` - Process existing recordings with template

---

#### 18. `celery_beat_schedule_entry`

**Назначение:** Celery Beat scheduler storage (celery-sqlalchemy-scheduler)

```sql
CREATE TABLE celery_beat_schedule_entry (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    task VARCHAR(255) NOT NULL,

    -- Schedule types
    crontab_id INTEGER,
    interval_id INTEGER,

    args JSONB DEFAULT '[]',
    kwargs JSONB DEFAULT '{}',

    queue VARCHAR(255),
    exchange VARCHAR(255),
    routing_key VARCHAR(255),

    expires TIMESTAMP WITH TIME ZONE,
    enabled BOOLEAN DEFAULT TRUE,

    last_run_at TIMESTAMP WITH TIME ZONE,
    total_run_count INTEGER DEFAULT 0,

    date_changed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    description TEXT
);

-- Supporting tables for celery-sqlalchemy-scheduler
CREATE TABLE celery_crontab_schedule (...);
CREATE TABLE celery_interval_schedule (...);
```

---

## JSONB Structures

### Template matching_rules

```json
{
  "exact_matches": ["Lecture: Machine Learning", "AI Course"],
  "keywords": ["ML", "AI", "neural networks"],
  "patterns": ["Лекция \\d+:.*ML", "\\[МО\\].*"],
  "source_ids": [1, 3],
  "match_mode": "any"  // "any" or "all"
}
```

### Template processing_config

```json
{
  "transcription": {
    "enable_transcription": true,
    "language": "ru",
    "prompt": "Technical lecture on machine learning...",
    "enable_topics": true,
    "topics_granularity": "long",
    "enable_subtitles": true
  },
  "video": {
    "remove_silence": true,
    "silence_threshold": -40.0,
    "min_silence_duration": 2.0
  }
}
```

### Template metadata_config

```json
{
  "title_template": "{themes} | {record_time:DD.MM.YYYY}",
  "description_template": "{topics}\\n\\nДлительность: {duration}",
  "topics_display": {
    "format": "numbered_list",  // numbered_list, bullet_list, dash_list, comma_separated
    "max_count": 999,
    "min_length": 0,
    "show_timestamps": true
  },
  "thumbnail_name": "ml_extra.png"  // From storage/users/user_XXXXXX/thumbnails/
}
```

### Template output_config

```json
{
  "preset_ids": [1, 2],  // Output presets to use
  "auto_upload": true
}
```

### Preset metadata (YouTube)

```json
{
  "privacy": "unlisted",
  "playlist_id": "PLmA-1xX7Iuz...",
  "category_id": "27",
  "default_language": "ru",
  "made_for_kids": false,
  "embeddable": true,
  "tags": ["lecture", "ML", "AI"]
}
```

### Preset metadata (VK)

```json
{
  "group_id": 227011779,
  "album_id": "63",
  "privacy_view": 0,  // 0=all, 1=friends, 2=private
  "privacy_comment": 0,
  "disable_comments": false,
  "repeat": false,
  "wallpost": false
}
```

### Input source config (Zoom)

```json
{
  "user_id": "zoom_user_id",
  "sync_from_date": "2024-01-01T00:00:00Z",
  "min_duration_minutes": 20,
  "max_duration_minutes": 300,
  "skip_blank_recordings": true
}
```

---

## Индексы и производительность

### Стратегия индексирования

**1. Multi-tenancy:** Все таблицы с `user_id VARCHAR(26)` имеют `(user_id, ...)` composite indexes

**2. Status filtering:** Composite indexes на `(status, user_id)` для быстрой фильтрации

**3. JSONB:** GIN indexes на JSONB полях для быстрого поиска

**4. Foreign Keys:** Все FK автоматически имеют индексы для быстрых JOIN'ов

**5. Partial indexes:** WHERE условия для часто используемых фильтров (failed, deleted)

### Примеры

```sql
-- Multi-tenancy
CREATE INDEX idx_recordings_user ON recordings(user_id, created_at DESC);

-- Status filtering
CREATE INDEX idx_recordings_status ON recordings(status, user_id);

-- Failed/deleted records (partial index)
CREATE INDEX idx_recordings_failed ON recordings(failed, user_id) WHERE failed = TRUE;
CREATE INDEX idx_recordings_deleted ON recordings(deleted, user_id) WHERE deleted = TRUE;

-- JSONB (if needed)
CREATE INDEX idx_recordings_prefs ON recordings USING GIN (processing_preferences);

-- Unique constraints
CREATE UNIQUE INDEX unique_source_per_recording
    ON source_metadata(source_type, source_key, recording_id);
```

### Performance Optimizations (Jan 2026)

- `func.count()` вместо загрузки всех записей
- Bulk operations через `get_by_ids()`, `find_by_ids()`
- Eager loading для вложенных связей (`lazy="selectin"`)
- Composite indexes для частых queries
- NullPool для Celery workers (asyncio safety)

---

## Миграции

### Список миграций (10)

| # | Filename | Описание |
|---|----------|----------|
| 001 | create_schema_with_ulid | Initial schema with ULID users |
| 002 | remove_priority_from_templates | Simplified template structure |
| 003 | add_pending_source_status | Added PENDING_SOURCE status |
| 004 | update_processing_stage_types | Updated stage types enum |
| 005 | add_missing_processing_statuses | Added missing FSM statuses |
| 006 | refactor_automation_jobs | Automation jobs refactoring |
| 007 | add_trim_stage_and_skipped | Added TRIM stage + SKIPPED status |
| 008 | create_celery_beat_tables | Celery Beat integration |
| 009 | remove_is_superuser_column | Removed deprecated column |
| 010 | convert_datetime_columns_to_timezone_aware | All datetime → timezone-aware |

### Команды

```bash
# Auto-init (при первом запуске FastAPI)
# Автоматически создает БД и применяет миграции

# Вручную
make init-db         # Создать БД + миграции
make migrate         # Применить миграции
make migrate-down    # Откатить миграцию
make db-version      # Текущая версия
make db-history      # История миграций
make recreate-db     # Пересоздать БД (⚠️ УДАЛИТ ДАННЫЕ)
```

### Создание новой миграции

```bash
# Auto-generate from models
alembic revision --autogenerate -m "description"

# Manual migration
alembic revision -m "description"

# Apply
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## См. также

- [TECHNICAL.md](TECHNICAL.md) - Полная техническая документация
- [ADR_OVERVIEW.md](ADR_OVERVIEW.md) - Архитектурные решения
- [OAUTH.md](OAUTH.md) - OAuth credentials & formats
- [TEMPLATES.md](TEMPLATES.md) - Templates & configuration guide
- [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md) - File storage structure

---

**Документ обновлен:** Февраль 2026
**Версия БД:** 10 миграций
**Статус:** ✅ Production-Ready
