# Technical Documentation

**Complete technical reference for LEAP Platform**

**Version:** v0.9.6 (February 2026)
**Status:** ✅ Production Ready

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [System Modules](#system-modules)
5. [Database Design](#database-design)
6. [Processing Pipeline](#processing-pipeline)
7. [REST API](#rest-api)
8. [Security](#security)
9. [Development Guide](#development-guide)

---

## System Overview

### What is LEAP

**LEAP** (Learning Educational Automation Platform) - это multi-tenant платформа для автоматизации end-to-end обработки образовательного видеоконтента.

**Ключевые возможности:**
- ✅ Синхронизация видео из Zoom, локальных файлов
- ✅ Загрузка видео по ссылке (YouTube, VK, Rutube, 1000+ сайтов через yt-dlp)
- ✅ Интеграция с Яндекс Диском (загрузка и выгрузка через REST API)
- ✅ FFmpeg обработка (удаление тишины, обрезка)
- ✅ AI транскрибация (Fireworks Whisper)
- ✅ AI извлечение тем (DeepSeek)
- ✅ Генерация субтитров (SRT, VTT)
- ✅ Multi-platform upload (YouTube, VK, Яндекс Диск)
- ✅ Template-driven automation
- ✅ Scheduled jobs (Celery Beat)

### Technology Stack

**Backend:**
```
Python 3.14+ • FastAPI • SQLAlchemy 2.0 (async)
PostgreSQL 12+ • Redis • Celery + Beat
```

**AI & Media:**
```
Fireworks AI (Whisper-v3-turbo) • DeepSeek API
FFmpeg • Pydantic V2
```

**External APIs:**
```
Zoom API • YouTube Data API v3 • VK API
yt-dlp (1000+ sites) • Yandex Disk REST API
```

**Security:**
```
JWT • OAuth 2.0 • Fernet Encryption • PBKDF2
```

### Project Structure

```
ZoomUploader/
├── api/                      # FastAPI application
│   ├── routers/              # API endpoints
│   ├── services/             # Business logic layer
│   ├── repositories/         # Data access layer
│   ├── schemas/              # Pydantic models
│   ├── core/                 # Core utilities (context, security)
│   ├── helpers/              # Helper classes
│   └── tasks/                # Celery tasks
├── database/                 # Database models & config
│   ├── models.py             # Core models (Recording, etc.)
│   ├── auth_models.py        # User, Credentials, Subscriptions
│   ├── template_models.py    # Templates, Sources, Presets
│   ├── automation_models.py  # Automation jobs
│   └── config.py             # Database configuration
├── file_storage/             # Storage abstraction layer (NEW v2.0)
│   ├── path_builder.py       # StoragePathBuilder (single source of truth)
│   ├── factory.py            # Backend factory (LOCAL/S3)
│   └── backends/             # Storage backends
│       ├── base.py           # StorageBackend interface
│       └── local.py          # LocalStorageBackend
├── *_module/                 # Processing modules
│   ├── video_download_module/
│   │   ├── core/base.py      # BaseDownloader ABC
│   │   ├── factory.py        # Downloader factory (by SourceType)
│   │   ├── downloader.py     # ZoomDownloader
│   │   └── platforms/        # yt-dlp, Yandex Disk downloaders
│   ├── video_processing_module/
│   ├── transcription_module/
│   ├── deepseek_module/
│   ├── subtitle_module/
│   ├── video_upload_module/
│   └── yandex_disk_module/   # Yandex Disk REST API client
├── storage/                  # User media files (ID-based, NEW v2.0)
│   ├── shared/thumbnails/    # Global thumbnails
│   ├── temp/                 # Temporary processing files
│   └── users/user_XXXXXX/    # User-isolated storage
├── alembic/                  # Database migrations
├── config/                   # Configuration files
├── utils/                    # Utilities
└── docs/                     # Documentation
```

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│                  REST API + JWT Auth                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Service Layer                           │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│   │ Recording    │  │ Template     │  │ Automation   │    │
│   │ Service      │  │ Service      │  │ Service      │    │
│   └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                              │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│   │ Credential   │  │ User         │  │ Upload       │    │
│   │ Service      │  │ Service      │  │ Service      │    │
│   └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Repository Layer                          │
│   (Database Access via SQLAlchemy async ORM)                │
│                                                              │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│   │ Recording    │  │ Template     │  │ User         │    │
│   │ Repository   │  │ Repository   │  │ Repository   │    │
│   └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│                      PostgreSQL                              │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Processing Modules                         │
│                                                              │
│   Video Download → Video Processing → Transcription →       │
│   Topic Extraction → Subtitle Generation → Upload           │
└─────────────────────────────────────────────────────────────┘
```

### Design Patterns

#### 1. Repository Pattern
**Purpose:** Изоляция доступа к данным от бизнес-логики

```python
class RecordingRepository:
    """Data access layer for recordings"""

    async def find_by_id(self, user_id: str, recording_id: int) -> Recording:
        """Get recording with multi-tenant isolation"""

    async def find_all(self, user_id: str, filters: dict) -> list[Recording]:
        """List recordings with filters"""
```

**Benefits:**
- ✅ Automatic multi-tenant filtering
- ✅ Reusable queries
- ✅ Easy to test and mock
- ✅ Separation of concerns

#### 2. Factory Pattern
**Purpose:** Создание сервисов с правильными credentials

```python
# FireworksTranscriptionService (uses config file)
from fireworks_module import FireworksConfig
fireworks_config = FireworksConfig.from_file("config/fireworks_creds.json")
service = FireworksTranscriptionService(fireworks_config)

# UploaderFactory
uploader = await UploaderFactory.create_uploader(
    session, user_id, platform="youtube"
)
```

**Benefits:**
- ✅ Централизованная логика создания
- ✅ Автоматическая загрузка credentials
- ✅ Fallback на default config
- ✅ Type-safe

#### 3. Service Context Pattern
**Purpose:** Передача контекста выполнения (user_id, session)

```python
@dataclass
class ServiceContext:
    session: AsyncSession
    user_id: str

    @property
    def config_helper(self) -> ConfigService:
        """Lazy-loaded config service"""
```

**Benefits:**
- ✅ Избегает передачи множества параметров
- ✅ Lazy-loading dependencies
- ✅ Единая точка входа

#### 4. Config-Driven Pattern
**Purpose:** Template-based automation

```python
# Config hierarchy (deep merge):
final_config = user_config ← template_config ← recording_override
```

**Benefits:**
- ✅ Консистентность обработки
- ✅ Гибкость через overrides
- ✅ Масштабируемость

### Architecture Principles

**KISS (Keep It Simple):**
- ServiceContext вместо передачи множества параметров
- ConfigService вместо прямого доступа к credentials
- Factories для упрощения создания объектов

**DRY (Don't Repeat Yourself):**
- Все credential-запросы через `CredentialService`
- Все config-запросы через `ConfigService`
- Repository pattern для избежания дублирования SQL

**Separation of Concerns:**
- Router → Service → Repository → Model
- Каждый слой имеет четкую ответственность
- Dependencies injection через FastAPI

---

## Core Components

### 1. ServiceContext

**File:** `api/core/context.py`

**Purpose:** Централизованное хранение контекста выполнения операции

```python
from api.core.dependencies import get_service_context

@router.post("/recordings/{id}/process")
async def process_recording(
    id: int,
    ctx: ServiceContext = Depends(get_service_context)
):
    # ctx содержит: session, user_id, config_helper (ConfigService)
    # Используйте ctx.config_helper для get_youtube_credentials, get_vk_credentials и др.
    # ...
```

**Key Features:**
- Автоматическая инициализация в `get_service_context` dependency
- Lazy-loading `ConfigService` (создается только при обращении)
- Единая точка входа для всех сервисов

### 2. ConfigService

**File:** `api/services/config_service.py`

**Purpose:** Получение конфигураций и credentials для пользователя

```python
config_service = ConfigService(session, user_id)

# Platform credentials (YouTube, VK)
youtube_creds = await config_service.get_youtube_credentials()
vk_creds = await config_service.get_vk_credentials()

# Zoom: используйте cred_service.get_credentials_by_id() и create_zoom_credentials()
# AI (Fireworks/DeepSeek): используйте *Config.from_file() из config/
```

**Key Features:**
- Абстракция деталей хранения credentials
- Единый интерфейс для всех платформ
- Автоматическая валидация и дешифрование
- Fallback на default credentials

### 3. FireworksTranscriptionService

**File:** `fireworks_module/service.py`

**Purpose:** Транскрибация аудио через Fireworks AI API

```python
from fireworks_module.service import FireworksTranscriptionService
from fireworks_module import FireworksConfig

# Получение конфигурации из файла
fireworks_config = FireworksConfig.from_file("config/fireworks_creds.json")

# Создание сервиса транскрибации
service = FireworksTranscriptionService(fireworks_config)

# Транскрибация
result = await service.transcribe_audio(
    audio_path="path/to/audio.mp3",
    language="ru",
    prompt="Optional context prompt"
)
```

**Поддерживаемые провайдеры:**
- `fireworks` - Fireworks AI (Whisper-v3-turbo)

### 4. UploaderFactory

**File:** `video_upload_module/uploader_factory.py`

**Purpose:** Создание uploaders с user credentials

```python
from video_upload_module.factory import UploaderFactory

# По платформе (автоматический выбор credentials)
uploader = await UploaderFactory.create_uploader(session, user_id, platform="youtube")

# По credential_id (явный выбор)
uploader = await UploaderFactory.create_youtube_uploader(
    session, user_id, credential_id=5
)

# По output preset (из template)
uploader = await UploaderFactory.create_uploader_by_preset_id(
    session, user_id, preset_id=1
)
```

**Поддерживаемые платформы:**
- `youtube` - YouTube Data API v3
- `vk_video` - VK Video API
- `yandex_disk` - Yandex Disk REST API

### 5. CredentialService

**File:** `api/services/credential_service.py`

**Purpose:** Низкоуровневая работа с credentials (encryption, validation)

```python
from api.services.credential_service import CredentialService

cred_service = CredentialService(session)

# Получение credentials
creds = await cred_service.get_decrypted_credentials(
    user_id="01HQ123456789ABCDEFGHJKMNP",  # ULID string
    platform="zoom",
    account_name="myaccount"
)

# Platform-specific методы
youtube_creds = await cred_service.get_youtube_credentials(user_id)
vk_creds = await cred_service.get_vk_credentials(user_id)

# По credential_id
creds = await cred_service.get_credentials_by_id(credential_id)
```

**Key Features:**
- Автоматическое дешифрование (Fernet)
- Валидация структуры credentials
- Multi-tenant изоляция

---

## System Modules

### 📡 API Module (`api/`)

**Purpose:** REST API endpoints, аутентификация, валидация

**Key Components:**
- `routers/` - API endpoints
- `services/` - Business logic
- `repositories/` - Data access
- `schemas/` - Pydantic models
- `core/` - Auth, security, context

**Features:**
- JWT authentication + refresh tokens
- OAuth 2.0 integration (YouTube, VK, Zoom)
- Role-based access control (RBAC)
- Quota management
- OpenAPI documentation (Swagger, ReDoc)

---

### ⬇️ Video Download Module (`video_download_module/`)

**Purpose:** Загрузка видео из внешних источников

**Architecture:**
```
video_download_module/
├── core/base.py              # BaseDownloader ABC (httpx streaming, resume, validation)
├── factory.py                # create_downloader(source_type) → BaseDownloader
├── downloader.py             # ZoomDownloader (Zoom API)
└── platforms/
    ├── ytdlp/
    │   ├── downloader.py     # YtDlpDownloader (YouTube, VK, Rutube, 1000+ sites)
    │   └── metadata.py       # Platform detection, playlist extraction
    └── yadisk/
        └── downloader.py     # YandexDiskDownloader (public links + OAuth API)
```

**Supported Sources:**
- **Zoom API** — OAuth 2.0 / Server-to-Server, token refresh
- **yt-dlp** — YouTube, VK, Rutube и 1000+ сайтов (видео + плейлисты + аудио/mp3)
- **Yandex Disk** — публичные ссылки и OAuth API для приватных файлов
- **Local files** — загрузка через API endpoint

**Key Features:**
- `BaseDownloader` — общий ABC с httpx streaming, resume, file validation
- `create_downloader()` — factory dispatch по `SourceType`
- Source-agnostic pipeline: download → process → upload работает одинаково для всех типов

**Direct Add-by-URL Endpoints:**
```
POST /api/v1/recordings/add-url       — добавить видео по ссылке
POST /api/v1/recordings/add-playlist  — добавить плейлист/канал
POST /api/v1/recordings/add-yadisk    — добавить с Яндекс Диска
```

**Output:** `storage/users/user_XXXXXX/recordings/{id}/source.mp4` (или `.mp3` для audio)

---

### ✂️ Video Processing Module (`video_processing_module/`)

**Purpose:** FFmpeg обработка видео

**Key Features:**
- Детекция тишины (silence detection)
- Обрезка "тихих" частей
- Удаление пустого начала и конца
- Audio extraction для транскрибации
- Codec: copy (без перекодирования)

**Files:**
- `video_processor.py` - Main processor
- `audio_detector.py` - Silence detection
- `segments.py` - Segment management

**Output:**
- Processed video: `storage/users/user_XXXXXX/recordings/{id}/video.mp4`
- Extracted audio: `storage/users/user_XXXXXX/recordings/{id}/audio.mp3`

---

### 🎤 Transcription Module (`transcription_module/`)

**Purpose:** Координация транскрибации через AI сервисы

**Architecture:**
```
TranscriptionManager (transcription_module/manager.py)
    ↓ (file operations: save/load master.json, extracted.json)

ConfigService (api/services/config_service.py)
    ↓ (get credentials)

FireworksTranscriptionService (fireworks_module/service.py)
    ↓ (actual AI transcription via Fireworks API)
```

**Key Features:**
- Транскрибация через Fireworks AI (Whisper-v3-turbo)
- Параллельная обработка с ограничением (max 2 concurrent)
- Retry механизм (3 попытки с exponential backoff)
- Валидация конфигурации через Pydantic

**Output:** `storage/users/user_XXXXXX/recordings/{id}/transcriptions/`
- `master.json` - Метаданные транскрипции с words и segments
- `extracted.json` - Извлечённые темы + summary (опционально)

**Documentation:** [Fireworks Audio API](https://fireworks.ai/docs/api-reference/audio-transcriptions)

---

### 🧠 DeepSeek Module (`deepseek_module/`)

**Purpose:** Извлечение тем и структурирование контента

**Key Features:**
- Определение основных тем (main topics)
- Генерация детализированных тем с таймкодами
- Автоматическое определение перерывов (паузы ≥8 минут)
- Динамический расчёт количества тем по длительности
- Поддержка двух провайдеров: DeepSeek, Fireworks DeepSeek

**Output:** `extracted.json` с версионированием (v1, v2, ...)

**Example:**
```json
{
  "recording_id": 21,
  "active_version": "v1",
  "versions": [
    {
      "id": "v1",
      "model": "deepseek-chat",
      "main_topics": ["ML", "Neural Networks", "Backpropagation"],
      "detailed_topics": [
        {"time": "00:05:30", "title": "Introduction to ML"},
        {"time": "00:15:45", "title": "Neural Network Basics"}
      ],
      "breaks": [{"time": "01:30:00", "duration_minutes": 10}]
    }
  ]
}
```

---

### 📝 Subtitle Module (`subtitle_module/`)

**Purpose:** Генерация субтитров из транскрипций

**Key Features:**
- Форматы: SRT, VTT
- Автоматическое разбиение на строки
- Таймкоды из words.txt
- Поддержка multiple языков

**Output:**
- `subtitles.srt`
- `subtitles.vtt`

**Usage:**
```bash
python main.py subtitles --format srt,vtt
```

**Upload:**
- YouTube: автоматическая загрузка субтитров
- VK: субтитры не поддерживаются

---

### 🚀 Upload Module (`video_upload_module/`)

**Purpose:** Загрузка видео на платформы

**Architecture:**
```
video_upload_module/
├── factory.py                # UploaderFactory
├── uploader_factory.py       # DB-based factory (create_uploader_from_db)
├── credentials_provider.py   # Credential providers
├── config_factory.py         # Config factory
└── platforms/
    ├── youtube/
    │   ├── uploader.py       # YouTubeUploader
    │   └── config.py         # YouTubeUploadConfig
    ├── vk/
    │   ├── uploader.py       # VKUploader
    │   └── config.py         # VKUploadConfig
    └── yadisk/
        └── uploader.py       # YandexDiskUploader (folder templates, overwrite)
```

**Supported Platforms:**

#### YouTube (YouTube Data API v3)
- Video upload с metadata
- Playlist management
- Subtitle upload (SRT, VTT)
- Thumbnail upload
- Privacy settings
- OAuth 2.0 authentication
- Automatic token refresh через `@requires_valid_token` decorator

#### VK (VK Video API)
- Video upload
- Album management
- Thumbnail upload
- Privacy settings
- Implicit Flow authentication (2026 policy)
- Automatic token refresh через `@requires_valid_vk_token` decorator

#### Yandex Disk (REST API)
- Upload через OAuth API
- Template-driven folder paths (e.g. `/Video/{course_name}/{date}`)
- Custom filename templates
- Overwrite mode
- Automatic folder creation

**Key Features:**
- Automatic token refresh с декораторами (Jan 2026)
- Graceful credential error handling
- Retry механизм
- Progress tracking
- Multi-account support
- Credential provider pattern

**Documentation:**
- [OAUTH.md](OAUTH.md) - OAuth setup
- [VK_INTEGRATION.md](VK_INTEGRATION.md) - VK details

---

### 🗄️ Database Module (`database/`)

**Purpose:** Database models и migrations

**Key Files:**
- `models.py` - Core models (Recording, SourceMetadata, OutputTarget)
- `auth_models.py` - User, Credentials, Subscriptions
- `template_models.py` - Templates, Sources, Presets
- `automation_models.py` - Automation jobs
- `config.py` - Database configuration
- `manager.py` - Database lifecycle manager (create, migrate, close)

**ORM:** SQLAlchemy 2.0 (async)

**Migrations:** Alembic (auto-init)

**Performance Optimizations (Jan 2026):**
- `func.count()` вместо загрузки всех записей
- Bulk operations через `get_by_ids()` и `find_by_ids()`
- Eager loading для вложенных связей (N+1 устранены)
- Composite indexes для часто используемых queries

**Documentation:** [DATABASE_DESIGN.md](DATABASE_DESIGN.md)

---

## Database Design

**Database:** PostgreSQL 12+ with SQLAlchemy 2.0 (async)

**Key Features:**
- Multi-tenant isolation via `user_id` filtering
- Encrypted credentials (Fernet)
- Automatic migrations
- Composite indexes for performance

**Table Categories:**
- Authentication & Users
- Subscriptions & Quotas
- Processing
- Automation

**Full Details:** [DATABASE_DESIGN.md](DATABASE_DESIGN.md)

---

## Processing Pipeline

### Pipeline Stages

```
1. INGEST       → Fetch from Zoom / yt-dlp / Yandex Disk / add-by-URL
2. DOWNLOAD     → Source-agnostic download via BaseDownloader factory
3. PROCESS      → FFmpeg trim silence, extract audio
4. TRANSCRIBE   → Fireworks AI (Whisper-v3-turbo)
5. TOPICS       → DeepSeek extraction with timestamps
6. SUBTITLES    → Generate SRT/VTT (optional)
7. UPLOAD       → YouTube + VK + Yandex Disk with metadata
```

**Celery Chains Architecture (Jan 2026):**

Orchestrator создает chain задач вместо монолитной обработки:

```python
# Orchestrator (~0.08s)
process_recording_task(recording_id, user_id)
  ↓
# Chain (каждый шаг на любом свободном worker)
download_task.s()
  | trim_task.s()
  | transcribe_task.s()
  | topics_task.s()
  | subtitles_task.s()
  | launch_uploads_task.s()
```

**Benefits:**
- Worker освобождается за 0.08s (не блокирован на 5+ минут)
- Параллельная обработка разных recordings
- Динамическое распределение шагов между workers
- Естественные boundaries для retry и мониторинга

### Processing Status Flow

```
INITIALIZED → DOWNLOADING → DOWNLOADED →
PROCESSING → PROCESSED → UPLOADING → READY
```

**Status Details:**
- `PROCESSING` — any processing stage (transcribe, extract topics, generate subtitles) is IN_PROGRESS
- `PROCESSED` — all processing stages completed or skipped, ready for upload
- `UPLOADING` — at least one platform upload is in progress
- `READY` — all platform uploads completed successfully

**Processing Stages:**
- `TRANSCRIBE` — audio transcription via Fireworks AI (Whisper)
- `EXTRACT_TOPICS` — topic extraction via DeepSeek
- `GENERATE_SUBTITLES` — subtitle generation (SRT/VTT)

Each stage has status: `PENDING` → `IN_PROGRESS` → `COMPLETED` (or `FAILED`/`SKIPPED`)

**Special statuses:**
- `SKIPPED` - Пропущено (не matched к template или user choice)
- `FAILED` - Ошибка на одном из этапов (graceful handling, Jan 2026)
- `EXPIRED` - Устарело (TTL exceeded)

**Error Handling (Jan 2026):**
- Credential/Token/Resource errors обрабатываются gracefully
- Output target помечается как FAILED в БД
- Задача возвращает `status='failed'` вместо raise
- ERROR логируется без traceback spam
- Celery видит задачу как успешно завершённую

### Template-Driven Processing

**Config Hierarchy (Deep Merge):**
```
User Default Config ← Template Config ← Recording Override Config
```

**Example:**
```python
# User default
user_config = {"transcription": {"language": "ru"}}

# Template config
template_config = {
    "transcription": {"enable_topics": True, "language": "en"},
    "video": {"remove_silence": True}
}

# Recording override
override_config = {"transcription": {"language": "ru"}}

# Final (deep merge)
final = {
    "transcription": {
        "language": "ru",           # override wins
        "enable_topics": True       # from template
    },
    "video": {"remove_silence": True}  # from template
}
```

**Documentation:** [TEMPLATES.md](TEMPLATES.md)

---

## REST API

### API Endpoints

| Category | Description |
|----------|-------------|
| 🔐 **Authentication** | Register, Login, Refresh, Logout, Profile |
| 👤 **User Management** | Profile, Config, Password, Account |
| 👔 **Admin** | Stats, Users, Quotas |
| 🎥 **Recordings** | CRUD, Pipeline, Batch, Add-by-URL |
| 📋 **Templates** | CRUD, Matching, Re-match |
| 🔑 **Credentials** | CRUD, Platform management |
| 🔌 **OAuth** | YouTube, VK, Zoom flows |
| 🤖 **Automation** | Jobs, Scheduling, Celery Beat |
| 📊 **Tasks** | Async task monitoring |
| 📥 **Input Sources** | Zoom/yt-dlp/Yandex Disk sources, Sync |
| 📤 **Output Presets** | Upload presets |
| 🖼️ **Thumbnails** | Upload, Management |
| 💚 **Health** | System status |
| 🔧 **User Config** | User-specific settings |

### Pydantic Schemas

**Complete type safety:**

- Request/Response models для всех endpoints
- Nested typing (templates, presets, configs)
- 6 Enums (`ProcessingStatus`, `YouTubePrivacy`, `VKPrivacyLevel`, etc.)
- 100% OpenAPI documentation coverage

### Key Endpoint Groups

#### Recordings Pipeline

```bash
# Add video from external sources (no InputSource required)
POST /api/v1/recordings/add-url        # Single video by URL (yt-dlp)
POST /api/v1/recordings/add-playlist   # Playlist/channel by URL (yt-dlp)
POST /api/v1/recordings/add-yadisk     # Yandex Disk public link

# Full pipeline
POST /api/v1/recordings/{id}/full-pipeline

# Individual stages
POST /api/v1/recordings/{id}/download
POST /api/v1/recordings/{id}/process
POST /api/v1/recordings/{id}/transcribe
POST /api/v1/recordings/{id}/upload/{platform}

# Batch operations
POST /api/v1/recordings/batch-process
POST /api/v1/recordings/batch-upload
```

#### Template Management

```bash
# CRUD
GET /api/v1/templates
POST /api/v1/templates
GET /api/v1/templates/{id}
PATCH /api/v1/templates/{id}
DELETE /api/v1/templates/{id}

# Matching
POST /api/v1/templates/{id}/preview-match
POST /api/v1/templates/{id}/rematch
POST /api/v1/templates/{id}/preview-rematch
```

#### OAuth Flows

```bash
# YouTube
GET /api/v1/oauth/youtube/authorize
GET /api/v1/oauth/youtube/callback

# VK
GET /api/v1/oauth/vk/authorize
POST /api/v1/oauth/vk/token/submit  # Implicit Flow

# Zoom
GET /api/v1/oauth/zoom/authorize
GET /api/v1/oauth/zoom/callback
```

#### Thumbnails

```bash
# List user thumbnails
GET /api/v1/thumbnails
# Response: {"thumbnails": [...]}

# Upload new thumbnail
POST /api/v1/thumbnails
# Body: multipart/form-data (file + optional custom_filename)
# Returns: 201 Created or 409 Conflict

# Update/create thumbnail
PUT /api/v1/thumbnails/{filename}
# Body: multipart/form-data (file)
# Idempotent operation

# Get thumbnail file
GET /api/v1/thumbnails/{filename}
# Returns: image file (png/jpg/jpeg)

# Delete thumbnail
DELETE /api/v1/thumbnails/{filename}
# Returns: 204 No Content
```

**Note:**
- Each user gets copies of all shared templates (22 files) at registration
- Users can upload, modify, or delete any thumbnails in their directory
- In templates/presets, use filename only: `"thumbnail_name": "ml_extra.png"`
- API automatically resolves to: `storage/users/user_XXXXXX/thumbnails/ml_extra.png`
- Security: API returns URLs (`/api/v1/thumbnails/file.jpg`), not filesystem paths

### API Documentation

**Interactive documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## Security

### Multi-Tenant Isolation

**3-Layer Security:**

**1. Database Level:**
- Все таблицы имеют `user_id` с индексами
- Foreign Key constraints: `ON DELETE CASCADE`
- Row-level filtering в queries

**2. Repository Level:**
- Автоматическая фильтрация по `user_id` во всех запросах
- Validation в `find_by_id`, `find_all`, `update`, `delete`

**3. Service Level:**
- `ServiceContext` передает правильный `user_id`
- Validation на существование ресурса и ownership

**4. API Level:**
- JWT token validation через `get_current_user` dependency
- Автоматическая инъекция `user_id` в `ServiceContext`

### Authentication & Authorization

**JWT (JSON Web Tokens):**
- Access token: 15 минут
- Refresh token: 30 дней
- Stored in database (`refresh_tokens` table)
- Automatic rotation

**OAuth 2.0:**
- YouTube: Authorization Code Flow
- VK: Implicit Flow (2026 policy)
- Zoom: OAuth 2.0 / Server-to-Server
- CSRF protection через Redis state tokens

**RBAC (Role-Based Access Control):**
```python
class UserModel:
    id: str  # ULID (26 chars): "01HQ123456789ABCDEFGHJKMNP"
    user_slug: int  # Sequential integer for storage paths (user_000001)
    role: str  # "user", "admin"

    # Permissions
    can_transcribe: bool
    can_process_video: bool
    can_upload: bool
    can_create_templates: bool
    can_delete_recordings: bool
    can_update_uploaded_videos: bool
    can_manage_credentials: bool
    can_export_data: bool
```

**Documentation:** [OAUTH.md](OAUTH.md)

### Credentials Encryption

**Fernet (Symmetric Encryption):**

```python
from cryptography.fernet import Fernet

# Encrypt
encrypted_data = fernet.encrypt(json.dumps(credentials).encode())

# Store in DB
user_credentials.encrypted_data = encrypted_data.decode()

# Decrypt
decrypted = json.loads(fernet.decrypt(encrypted_data.encode()))
```

**Key Management:**
- Encryption key stored in environment variable: `ENCRYPTION_KEY`
- Key rotation support через `encryption_key_version`
- Never log or expose credentials

**Encrypted Platforms:**
- Zoom (OAuth tokens, Server-to-Server credentials)
- YouTube (OAuth tokens)
- VK (access tokens)
- Yandex Disk (OAuth tokens)
- Fireworks API keys
- DeepSeek API keys

### Rate Limiting

**API Rate Limits:**
- Per minute: 60 requests
- Per hour: 1000 requests
- 429 Too Many Requests response

**Quota System:**
- Monthly recordings limit (by plan)
- Storage limit (by plan)
- Concurrent tasks limit
- Automation jobs limit

### Security Best Practices

**Environment Variables:**
```bash
# Never commit these
API_JWT_SECRET_KEY=your-secret-key-change-in-production
ENCRYPTION_KEY=your-fernet-key-here
DATABASE_PASSWORD=secure-password
```

**CORS Configuration:**
```python
# Production: strict origins
ALLOWED_ORIGINS = ["https://yourdomain.com"]

# Development: localhost only
ALLOWED_ORIGINS = ["http://localhost:3000"]
```

**HTTPS Only:**
- All OAuth redirects must use HTTPS in production
- Secure cookies (`SameSite=Lax`, `Secure=True`)

---

## Development Guide

### Setup

**Requirements:**
- Python 3.14+
- PostgreSQL 12+
- Redis
- FFmpeg

**Installation:**
```bash
# 1. Clone repository
git clone <repo-url>
cd ZoomUploader

# 2. Install dependencies (UV recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# 3. Setup environment
cp .env.example .env
# Edit .env with your credentials

# 4. Start infrastructure
make docker-up

# 5. Initialize database
make init-db

# 6. Run API
make api
```

### Project Commands

**Development:**
```bash
make api          # Start FastAPI server
make worker       # Start Celery worker
make beat         # Start Celery beat (scheduling)
make flower       # Start Flower (monitoring)
```

**Database:**
```bash
make init-db      # Initialize database + migrations
make migrate      # Apply migrations
make migrate-down # Rollback migration
make db-version   # Show current version
make db-history   # Show migration history
make recreate-db  # Drop + recreate (⚠️ data loss)
```

**Code Quality:**
```bash
make lint         # Run ruff linter
make format       # Format code with ruff
make type-check   # Run type checking (planned)
```

### Running Tests

**Unit Tests:**
```bash
pytest tests/unit/
```

**Integration Tests:**
```bash
pytest tests/integration/
```

**E2E Tests:**
```bash
pytest tests/e2e/
```

### Adding New Features

**1. Create migration:**
```bash
alembic revision -m "add_new_feature"
# Edit migration file
alembic upgrade head
```

**2. Add models:**
```python
# database/models.py
class NewModel(Base):
    __tablename__ = "new_table"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"))  # Multi-tenant (ULID)
```

**3. Add repository:**
```python
# api/repositories/new_repository.py
class NewRepository:
    async def find_all(self, user_id: str) -> list[NewModel]:
        # Auto-filter by user_id (ULID string)
        pass
```

**4. Add service:**
```python
# api/services/new_service.py
class NewService:
    def __init__(self, repo: NewRepository):
        self.repo = repo
```

**5. Add schemas:**
```python
# api/schemas/new/schemas.py
class NewCreate(BaseModel):
    name: str = Field(..., min_length=1)

class NewResponse(BaseModel):
    id: int
    name: str
```

**6. Add router:**
```python
# api/routers/new.py
@router.get("/new")
async def list_new(ctx: ServiceContext = Depends(get_service_context)):
    service = NewService(NewRepository(ctx.session))
    return await service.list(ctx.user_id)
```

### Environment Variables

**Required:**
```bash
# Database
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=zoom_manager
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=postgres

# API
API_JWT_SECRET_KEY=your-secret-key
ENCRYPTION_KEY=your-fernet-key

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

**Optional:**
```bash
# AI Services
FIREWORKS_API_KEY=your-key
DEEPSEEK_API_KEY=your-key

# OAuth
# See config/oauth_*.json files
```

### Debugging

**Enable debug logging:**
```python
# logger.py
LOG_LEVEL = "DEBUG"
```

**View logs:**
```bash
# Docker
docker-compose logs -f api
docker-compose logs -f worker

# Local
tail -f logs/api.log
tail -f logs/worker.log
```

**Redis inspection:**
```bash
redis-cli
> KEYS *
> GET oauth:state:abc-123
```

**Database inspection:**
```bash
psql -U postgres -d zoom_manager
> \dt  # List tables
> SELECT * FROM recordings WHERE user_id=1;
```

---

## Performance

### Optimization Strategies

**1. Lazy Loading:**
- `ConfigService` создается только при первом обращении
- SQLAlchemy relationships с `lazy="selectin"`

**2. Async Operations:**
- Все I/O операции асинхронные (FastAPI, SQLAlchemy)
- Concurrent transcription/upload (с ограничением)

**3. Database Optimization (Jan 2026):**
- `func.count()` вместо загрузки всех записей в память
- Bulk operations: `get_by_ids()`, `find_by_ids()` (один запрос вместо N)
- Eager loading для вложенных связей (N+1 queries устранены)
- Composite indexes для часто используемых queries
- Импорты вынесены в начало файлов (PEP8)

**4. Celery Chains (Jan 2026):**
- Orchestrator освобождает worker за ~0.08s
- Параллельная обработка recordings
- Динамическое распределение шагов

**5. Caching:**
- Redis для OAuth state tokens
- Token caching в memory (planned)

**6. Connection Pooling:**
- SQLAlchemy async connection pool
- Redis connection pool

### Monitoring

**Metrics:**
- API response time (via middleware)
- Database query performance (slow query log)
- Celery task duration (via Flower)
- Quota usage tracking

**Tools:**
- Flower: http://localhost:5555 (Celery monitoring)
- PostgreSQL slow query log
- Redis monitoring via redis-cli

---

## Related Documentation

**Core Guides:**
- [INDEX.md](INDEX.md) - Documentation index
- [README.md](../README.md) - Project overview
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
- [CHANGELOG.md](CHANGELOG.md) - Version history

**Features:**
- [TEMPLATES.md](TEMPLATES.md) - Template-driven automation
- [OAUTH.md](OAUTH.md) - OAuth integration
- [VK_INTEGRATION.md](VK_INTEGRATION.md) - VK Implicit Flow
- [YT_DLP_GUIDE.md](YT_DLP_GUIDE.md) - yt-dlp video ingestion
- [YANDEX_DISK_GUIDE.md](YANDEX_DISK_GUIDE.md) - Yandex Disk integration

**Architecture:**
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Database schema
- [ADR_OVERVIEW.md](ADR_OVERVIEW.md) - Architecture decisions
- [ADR_FEATURES.md](ADR_FEATURES.md) - Feature ADRs

---

## Quick Reference

**Technology Stack:**
Python 3.14+ • FastAPI • SQLAlchemy 2.0 • PostgreSQL 12+ • Redis • Celery • FFmpeg

**Features:**
- Production-ready REST API
- Multi-tenant database with auto-migrations
- Complete type safety with Pydantic
- Multi-source ingestion (Zoom, yt-dlp, Yandex Disk, local files)
- Processing modules (video, transcription, upload)
- Multi-platform upload (YouTube, VK, Yandex Disk)
- OAuth platforms (YouTube, VK, Zoom)
- AI models (Whisper, DeepSeek)

**Documentation:** Comprehensive guides available in `/docs`

---

**Version:** v0.9.6 (February 2026)
**Status:** Development
**License:** Business Source License 1.1
