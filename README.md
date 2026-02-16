# 🎥 LEAP

> **AI-powered platform for intelligent educational video content processing**

![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-12+-blue.svg)
![Redis](https://img.shields.io/badge/Redis-7+-blue.svg)
![Celery](https://img.shields.io/badge/Celery-5+-blue.svg)
![ty](https://img.shields.io/badge/ty-0.14+-orange.svg)
![License](https://img.shields.io/badge/license-BSL%201.1-orange.svg)

**LEAP** — это `multi-tenant` платформа с полным `REST API` для автоматизации `end-to-end` обработки образовательного видеоконтента — от загрузки до публикации с `AI-транскрибацией`, интеллектуальным структурированием и профессиональным оформлением.

**Версия:** `v0.9.6` (February 2026)
**Tech:** `Python 3.14` • `FastAPI` • `Pydantic V2` • `PostgreSQL` • `Redis` • `Celery` • `AI` (Whisper, DeepSeek) • `yt-dlp` • `ruff & ty`

---

## 🎯 Use Cases

**🏫 Университеты и образовательные платформы**
- Автоматическая публикация тысяч лекций с минимальными усилиями
- AI-структурирование контента для удобной навигации
- Multi-tenant изоляция для разных факультетов/кафедр

**🎓 Онлайн-школы и EdTech**
- Быстрый `time-to-market` для образовательного контента
- Профессиональное оформление с таймкодами и субтитрами
- Scheduled automation для регулярных публикаций

**🎬 Контент-команды**
- Batch processing для массовой обработки архивов
- Template-based автоматизация для разных типов контента
- API-first подход для интеграции в существующие системы

**👨‍💼 Enterprise**
- `Multi-tenancy` для изоляции клиентов/проектов
- `RBAC` и квоты для контроля доступа
- `Audit logs` и `usage tracking`

---

## 🔄 Как это работает

Платформа автоматизирует полный цикл обработки видео от загрузки до публикации:

```
📥 Видео-контент → ✂️ FFmpeg → 🤖 AI (Whisper+DeepSeek) → 📝 Метаданные → 📤 Публикация
                   Обработка    Транскрипция+Темы        Таймкоды         На платформы
                      ↓              ↓                        ↓                 ↓
                  Тишина       Структура контента      Описание+Субтитры   Multi-platform
                  удалена      с таймкодами           Template-based       Auto-retry
```

### Этап 1: 📥 Получение контента

**Источники данных:**
- Синхронизация с `Zoom API` через `OAuth 2.0`
- **yt-dlp** — загрузка по ссылке с YouTube, VK, Rutube и 1000+ сайтов (видео, плейлисты, аудио)
- **Яндекс Диск** — загрузка по публичной ссылке или через OAuth API
- Загрузка локальных файлов
- 🚧 **В разработке:** Google Drive

**Добавление видео:**
- `POST /add-url` — одно видео по ссылке (yt-dlp, auto-detect платформы)
- `POST /add-playlist` — плейлист/канал целиком
- `POST /add-yadisk` — файлы с Яндекс Диска по публичной ссылке
- `InputSource` sync — для периодической синхронизации (Zoom, Yandex Disk OAuth)

**Что происходит:**
- Система забирает записи из различных источников
- Создает записи в БД с метаданными
- Скачивает видео в `user-isolated storage`
- Поддержка `multi-source` для одного пользователя
- Source-agnostic pipeline: download → process → upload работает одинаково для всех типов

### Этап 2: ✂️ Обработка видео

**`FFmpeg Processing`:**
- Детекция и удаление тишины
- Обрезка пустого начала и конца
- Извлечение аудиодорожки для транскрибации

**`Celery Chains` для параллелизма:**
- Orchestrator запускает chain задач (`download` → `trim` → `transcribe` → `topics` → `subs` → `upload`)
- Каждый шаг выполняется на свободном worker (~0.08s `overhead`)
- Динамическое распределение между recordings

**Результат:**
- Чистое видео без технических пауз
- Оптимизированная длительность
- Готовый аудио-файл

### Этап 3: 🤖 AI-обработка

**Транскрибация (`Fireworks AI`):**
- `whisper-v3-turbo` для точной транскрибации
- Поддержка больших файлов (Аудио до гб)
- `Automatic chunking` и `retry`

**Извлечение структуры (`DeepSeek`):**
- Определение основных и детализированных тем
- Автоматическая генерация таймкодов (`HH:MM:SS`)
- Обнаружение перерывов и пауз

**Субтитры:**
- Генерация `SRT` и `VTT` файлов
- Поддержка `multiple` языков

### Этап 4: 📝 Формирование метаданных

**Автоматическая генерация:**
- Структурированное описание с таймкодами
- Заголовок на основе шаблона
- Подбор миниатюр (`thumbnails`)
- Применение `user config` и `templates`

**Template-Based:**
- `Matching rules` для автоматического применения
- Пресеты для разных типов контента
- Настройка через `API` или `config` файлы

### Этап 5: 📤 Публикация

**YouTube:**
- Загрузка видео через `YouTube Data API v3`
- Автоматическая загрузка субтитров
- Добавление в плейлисты
- Настройка privacy и категории

**VK:**
- Загрузка в сообщества
- Добавление в альбомы
- Настройка видимости

**Яндекс Диск:**
- Загрузка через OAuth API
- Template-driven folder paths (e.g. `/Video/{course_name}/{date}`)
- Автоматическое создание папок
- Overwrite mode

🚧 **В разработке:**
- **Rutube** — российская видеоплатформа
- **Local Export** — полный пакет (видео + субтитры + метаданные)

**Multi-Platform:**
- Параллельная загрузка на несколько платформ
- Tracking статусов для каждой платформы
- `Template-driven` настройка для каждой платформы

---

## 🚀 Чем хорош проект

### **Enterprise-Ready Features**

**⚡ Comprehensive REST API**
- Полноценный `CRUD` для всех сущностей
- `JWT` аутентификация + `RBAC`
- `OpenAPI` документация (`Swagger`, `ReDoc`)
- Асинхронная архитектура на `FastAPI`

**👥 Multi-Tenancy из коробки**
- Полная изоляция данных пользователей
- Шифрование credentials (`Fernet`)
- User-isolated file storage
- Квоты, rate limiting и user statistics

**🔐 Production Security**
- `OAuth 2.0` интеграция (YouTube, VK, Zoom, Yandex Disk)
- Automatic token refresh с декораторами
- `CSRF` protection через `Redis`
- Encrypted credentials в БД
- Graceful error handling для credential/token errors

**🤖 Smart Automation**
- `Celery Beat` scheduling
- Declarative job configuration
- Automatic sync + process + upload
- Dry-run mode для preview

**📊 AI-Powered Processing**
- `Fireworks AI` (`whisper-v3-turbo`) для транскрибации
- `DeepSeek` для извлечения тем
- Автоматическая генерация таймкодов
- Генерация субтитров (`SRT`, `VTT`)

---

## 💎 Ключевые преимущества

### ⚡ Производительность

**90%+ экономия времени**
- Полная автоматизация: от синхронизации до публикации
- `Batch processing` для массовой обработки
- `Concurrent execution` с оптимизацией ресурсов
- `Scheduled automation` — публикация в фоне

**Масштабируемость**
- `Multi-tenant` архитектура для тысяч пользователей
- `Horizontal scaling` через `Celery workers` с `chains`
- `Async-first` для высокой пропускной способности
- `DB optimization` (`eager loading`, `bulk operations`)

### 🤖 **AI-Powered Intelligence**

**Smart Content Processing**
- `Fireworks AI` (`whisper-v3-turbo`) — точная транскрибация
- `DeepSeek` — интеллектуальное извлечение тем
- Автоматические таймкоды для навигации
- Генерация субтитров (`SRT`, `VTT`)

**Video Enhancement**
- `FFmpeg` — удаление тишины и пауз
- `Automatic trimming` начала/конца
- `Audio extraction` для `AI processing`
- `Quality optimization`

### 🏢 **Enterprise-Grade**

**Security & Compliance**
- `OAuth 2.0` + `JWT` authentication
- `Fernet` encryption для credentials
- `RBAC` для управления доступом
- Audit logs и usage tracking

---

## 🛠️ **Технологический стек**

### Modern Python Stack

**Core Framework**
```
Python 3.11+ • FastAPI (async) • SQLAlchemy 2.0 (async ORM)
PostgreSQL 12+ • Redis • Celery + Beat • Alembic
```

**AI & ML**
```
Fireworks AI (whisper-v3-turbo) • DeepSeek API
FFmpeg • Pydantic V2
```

**External Integrations**
```
Zoom API (OAuth 2.0) • YouTube Data API v3 • VK API
yt-dlp (1000+ sites) • Yandex Disk REST API
🚧 Google Drive API
```

**Security Stack**
```
JWT Authentication • OAuth 2.0 • Fernet Encryption
PBKDF2 Hashing • RBAC • CSRF Protection
```

**DevOps & Tools**
```
Docker & Docker Compose • UV (package manager)
Ruff (linter) • ty (type checker) • Flower (monitoring) • Make
```

### Архитектурные паттерны

- **Repository Pattern** — изоляция доступа к данным
- **Factory Pattern** — создание сервисов с credentials
- **Service Context** — централизованный контекст выполнения
- **Config-Driven** — template-based автоматизация
- **Async-First** — полностью асинхронная архитектура

---

## 🏗️ **Enterprise Architecture**

### Multi-Tenancy

**3-Level Data Isolation**
```
Database:    user_id filtering + indexes
Service:     ServiceContext + ConfigHelper
File System: storage/users/user_{slug}/ isolation (ID-based naming)
```

### Security

**Authentication & Authorization**
- `JWT` (access + refresh) • `OAuth 2.0` • `RBAC`
- `Fernet` encryption • `PBKDF2` hashing
- `CSRF` protection via `Redis`

**Resource Management**
- Rate limiting (60/min, 1000/hr)
- Storage & processing quotas
- Concurrent task limits
- Usage tracking & audit logs

### Модульная структура

```
api/                    ← FastAPI endpoints, JWT auth, validation
database/               ← SQLAlchemy models, Alembic migrations
file_storage/           ← Storage abstraction (paths, backends: LOCAL/S3)
video_download_module/  ← BaseDownloader + factory (Zoom, yt-dlp, Yandex Disk)
video_processing_module/← FFmpeg (silence removal, audio extraction)
transcription_module/   ← AI transcription coordination
video_upload_module/    ← Multi-platform upload (YouTube, VK, Yandex Disk)
yandex_disk_module/     ← Yandex Disk REST API client
api/services/           ← Business logic layer
api/repositories/       ← Data access layer (Repository pattern)
api/tasks/              ← Celery background tasks
storage/                ← User media files (ID-based structure)
```

**Design Patterns:**
- **Repository** — data access isolation
- **Factory** — service creation with credentials
- **Service Context** — unified execution context
- **Config-Driven** — template-based automation

📖 Детали: [TECHNICAL.md](docs/TECHNICAL.md) • [ADR.md](docs/ADR.md)

---

## 📊 Processing Pipeline

**Status Flow:**
```
INITIALIZED → DOWNLOADING → DOWNLOADED →
PROCESSING → PROCESSED → UPLOADING → READY
```

**Status Details:**
- `PROCESSING` — любая стадия обработки (transcribe, topics, subtitles) в процессе
- `PROCESSED` — все стадии завершены, готово к загрузке
- `UPLOADING` — загрузка на платформы (YouTube/VK/Yandex Disk) в процессе
- `READY` — все загрузки завершены

**Special Statuses:**
- `SKIPPED` — пропущено (config-driven)
- `EXPIRED` — устарело (TTL exceeded)

---

## 📚 Документация

**📋 Навигация:** [INDEX.md](docs/INDEX.md) - полный список документов

### Основные руководства

| Документ | Описание |
|----------|----------|
| 📖 [TECHNICAL.md](docs/TECHNICAL.md) | Complete technical reference (API, modules, security) |
| 🚀 [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment guide |
| 🗄️ [DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) | Database schema & migrations |
| 🗺️ [ROADMAP.md](docs/ROADMAP.md) | Project roadmap & future plans |
| 📋 [PLAN.md](docs/PLAN.md) | Thesis plan & milestones |
| 🆕 [UPDATES.md](docs/UPDATES.md) | Latest updates & progress |
| 📜 [CHANGELOG.md](docs/CHANGELOG.md) | Complete version history |
| 🎬 [YT_DLP_GUIDE.md](docs/YT_DLP_GUIDE.md) | yt-dlp video ingestion guide |
| 💿 [YANDEX_DISK_GUIDE.md](docs/YANDEX_DISK_GUIDE.md) | Yandex Disk integration guide |

---

## 🆕 Version v0.9.6 (February 2026)

**Status:** In Active Development • Beta

**Новое в v0.9.6:**

**📝 Templates & Transcription**
- **transcription_vocabulary** — доп. термины для распознавания (Fireworks/Whisper)
- **granularity** — short/medium/long для извлечения тем (DeepSeek)
- **{summary}** — переменная в шаблонах описания
- Промпты транскрайбера в `fireworks_module/prompts.py`, единый русский язык
- **topics.json → extracted.json** — топики и summary в одном файле

**🔒 Uniqueness & Logging**
- Entity uniqueness constraints (templates, presets, automations, credentials)
- Structured logging: loguru contextualize, SUCCESS уровень, JSON sink
- Pipeline timing: `stage_timings` table, pipeline_started_at/completed_at

**📥 Multi-Source Video Ingestion (v0.9.5)**
- **yt-dlp** — добавление видео по ссылке с YouTube, VK, Rutube и 1000+ сайтов
- **Плейлисты** — импорт целых плейлистов/каналов одной командой
- **Яндекс Диск** — загрузка по публичной ссылке и через OAuth API
- **Аудио (MP3)** — скачивание аудио-дорожки для транскрибации
- **Direct API** — `POST /add-url`, `/add-playlist`, `/add-yadisk` без создания InputSource
- *Зачем:* Загрузка из любых источников, data transfer между платформами

**📤 Yandex Disk Upload**
- Выгрузка обработанных видео на Яндекс Диск через OAuth API
- Template-driven folder paths (e.g. `/Video/{course_name}/{date}`)
- Автоматическое создание папок, кастомные имена файлов
- *Зачем:* Data transfer из Zoom/YouTube на Яндекс Диск

**🏗️ Source-Agnostic Architecture**
- `BaseDownloader` ABC — единый интерфейс для всех источников
- `create_downloader()` factory — dispatch по `SourceType`
- Pipeline download → process → upload работает одинаково для всех типов
- Удалена hardcoded Zoom-логика из generic endpoints
- *Зачем:* Clean architecture, легко добавлять новые источники

**Ключевые возможности (ранее):**

**🔐 Multi-tenancy & Data Isolation**
- Полная изоляция данных между пользователями на всех уровнях
- *Зачем:* Безопасность данных, соответствие GDPR

**🤖 Template-driven Автоматизация**
- `Celery Beat` scheduling + declarative configuration
- Автоматический цикл: sync → process → upload
- *Зачем:* Экономия времени, масштабирование без увеличения команды

**⚡ Параллельное Выполнение Задач**
- `Celery Chains` — параллелизм задач с минимальным overhead (0.08s)
- Обрезка видео ускорена в **6x раз** (audio-first подход)
- *Зачем:* Быстрая обработка = довольные пользователи

**☁️ S3 Storage Support**
- `S3-ready storage abstraction layer` — `LOCAL` / `S3` переключение одной строкой
- `ID-based naming` — никакой кириллицы в путях
- *Зачем:* Неограниченное хранилище, легкое масштабирование

---

## 📄 **Лицензия**

**Business Source License 1.1**

Проект распространяется под лицензией Business Source License 1.1. См. файл [LICENSE](LICENSE) для полной информации.

---

## 📞 **Сотрудничетсво**

**Телеграм:** [Gordey Zuev](https://t.me/WhiteShape)
**Почта** [gordey.zuev@gmail.com](mailto:gordey.zuev@gmail.com)

---

**Version:** `v0.9.6` (February 2026) • **Status:** In Active Development • Beta
