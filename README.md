# 🎥 LEAP

> **AI-powered platform for intelligent educational video content processing**

<!-- Backend -->
![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)
![Redis](https://img.shields.io/badge/Redis-7+-blue.svg)
![Celery](https://img.shields.io/badge/Celery-5+-blue.svg)
![ty](https://img.shields.io/badge/ty-0.14+-orange.svg)
<!-- Frontend -->
![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)
![React](https://img.shields.io/badge/React-19-61DAFB.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6.svg)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4.svg)
![TanStack Query](https://img.shields.io/badge/TanStack_Query-5-FF4154.svg)
<!-- Meta -->
![License](https://img.shields.io/badge/license-BSL%201.1-orange.svg)

**LEAP** — это `multi-tenant` платформа с полным `REST API` и веб-интерфейсом для автоматизации `end-to-end` обработки образовательного видеоконтента — от загрузки до публикации с `AI-транскрибацией`, интеллектуальным структурированием и профессиональным оформлением.

**Версия:** `v0.10.4.1` (June 2026) · **Статус:** In Active Development • Beta
**Backend:** `Python 3.14` • `FastAPI` • `Pydantic V2` • `PostgreSQL` • `Redis` • `Celery` • `AI` (AssemblyAI, DeepSeek) • `yt-dlp` • `ruff & ty`
**Frontend:** `Next.js 16` • `React 19` • `TypeScript 5` • `Tailwind CSS 4` • `TanStack Query v5` • `shadcn/ui`

**Структура репозитория:** API — [`backend/`](backend/) (`uv`, `make`, тесты, Celery); веб-клиент — [`frontend/`](frontend/) (`npm`, Next.js). В **корне** — [`docker-compose.yml`](docker-compose.yml) и [`Makefile`](Makefile) для Docker.

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
- Яндекс Диск (публичная ссылка) — `POST /api/v1/sources` (`YANDEX_DISK` + `public_url`) и sync
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

### Backend

**Core Framework**
```
Python 3.14+ • FastAPI (async) • SQLAlchemy 2.0 (async ORM)
PostgreSQL 15+ • Redis 7+ • Celery 5+ Beat • Alembic
```

**AI & Media**
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

**Security**
```
JWT Authentication • OAuth 2.0 • Fernet Encryption
PBKDF2 Hashing • RBAC • CSRF Protection
```

**DevOps & Tooling**
```
Docker & Docker Compose • uv (package manager)
Ruff (linter) • ty (type checker) • Flower (Celery monitoring) • Make
```

### Frontend

**Core**
```
Next.js 16 (App Router) • React 19 • TypeScript 5
```

**Styling & UI**
```
Tailwind CSS 4 • shadcn/ui (class-variance-authority, clsx, tailwind-merge)
Lucide React (иконки)
```

**Data Fetching**
```
TanStack Query v5 (React Query) — кеширование, фоновый рефетч, polling
Axios — HTTP-клиент с JWT-интерцептором
```

**Tooling**
```
ESLint (eslint-config-next) • npm
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

**Backend (`backend/`):**
```
api/                    ← FastAPI endpoints, JWT auth, validation
api/routers/            ← REST routers (recordings, templates, presets, automations, references, …)
api/services/           ← Business logic layer
api/repositories/       ← Data access layer (Repository pattern)
api/tasks/              ← Celery background tasks (download, process, upload, maintenance)
database/               ← SQLAlchemy models, Alembic migrations
file_storage/           ← Storage abstraction (paths, backends: LOCAL/S3)
video_download_module/  ← BaseDownloader + factory (Zoom, yt-dlp, Yandex Disk)
video_processing_module/← FFmpeg (silence removal, trim, audio extraction)
transcription_module/   ← AI transcription coordination (Fireworks Whisper)
video_upload_module/    ← Multi-platform upload (YouTube, VK, Yandex Disk)
yandex_disk_module/     ← Yandex Disk REST API client
storage/                ← User media files (ID-based tenant isolation)
```

**Frontend (`frontend/`):**
```
src/app/(app)/          ← App Router pages (recordings, templates, presets, automations, settings, …)
src/components/         ← Shared UI components (platform-fields, recordings, ui/)
src/hooks/              ← React Query hooks (useReferences, useRecordings, …)
src/lib/                ← API client (Axios + JWT), constants, utils
```

**Design Patterns:**
- **Repository** — data access isolation
- **Factory** — service creation with credentials
- **Service Context** — unified execution context
- **Config-Driven** — template-based automation

📖 Детали: [TECHNICAL.md](backend/docs/TECHNICAL.md) • [ADR_OVERVIEW.md](backend/docs/ADR_OVERVIEW.md)

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

**📋 Навигация:** [INDEX.md](backend/docs/INDEX.md) - полный список документов

### Основные руководства

| Документ | Описание |
|----------|----------|
| 📖 [TECHNICAL.md](backend/docs/TECHNICAL.md) | Complete technical reference (API, modules, security) |
| 🚀 [DEPLOYMENT.md](backend/docs/guides/DEPLOYMENT.md) | Production deployment guide |
| 🗄️ [DATABASE_DESIGN.md](backend/docs/DATABASE_DESIGN.md) | Database schema & migrations |
| 🗺️ [tests/ROADMAP.md](backend/tests/ROADMAP.md) | Testing roadmap & plans |
| 📋 [PLAN.md](backend/docs/archive/PLAN.md) | Thesis plan & milestones |
| 📜 [CHANGELOG.md](backend/docs/CHANGELOG.md) | Complete version history |
| 🎬 [YT_DLP_GUIDE.md](backend/docs/guides/YT_DLP_GUIDE.md) | yt-dlp video ingestion guide |
| 💿 [YANDEX_DISK_GUIDE.md](backend/docs/guides/YANDEX_DISK_GUIDE.md) | Yandex Disk integration guide |

---

## 🆕 Последние релизы

Ниже — что изменилось для пользователей и операторов. Полная история — **[CHANGELOG.md](backend/docs/CHANGELOG.md)**.

**Новое в `v0.10.4.1`** — AssemblyAI вместо Fireworks:
- **Транскрипция** — AssemblyAI Universal-2/3-Pro; сегменты через `/sentences` (точнее, чем эвристика по словам).
- **Keyterms** — термины из шаблона и название записи улучшают распознавание (поле `prompt` в ASR убрано).
- **Деплой** — нужен `config/assemblyai_creds.json` (`api_key`); `fireworks_creds.json` и batch Fireworks API удалены.
- **Темы** — только DeepSeek; fallback через Fireworks DeepSeek убран.

**Новое в `v0.10.4`** — стабильнее пайплайн и публикация:
- **Надёжная обработка** — запись больше не «зависает» в активном пайплайне после сбоя воркера: новый флаг `on_air`, автоматический сброс застрявших записей, защита от двойного запуска.
- **Пауза и возобновление** — пауза сразу откатывает статус и останавливает фоновые задачи; после возобновления не пропускаются оставшиеся этапы (транскрипция, темы, субтитры).
- **Стабильная загрузка** — исправлен путь «только upload»: флаг активности сбрасывается после отправки на платформы; сброс записи корректно отзывает цепочку Celery.
- **Темы и вопросы в описании** — настройки в UI, preview и итоговое описание при публикации теперь совпадают; API отдаёт единые defaults для редакторов.

**Новое в `v0.10.3`** — больше настроек публикации прямо в интерфейсе:
- **Пресеты публикации** — все параметры YouTube, VK и Яндекс.Диска теперь настраиваются в UI: отложенная публикация, лицензия, встраивание на другие сайты, отключение комментариев и лайков, уведомление подписчиков; для VK — зацикливание и сжатие; для Я.Диска — шаблоны названия и описания, а также автоматическая загрузка субтитров, транскрипции и текстового описания рядом с видео.
- **Шаблоны обработки** — настройки отображения тем и вопросов в описании, загрузка субтитров на платформы. Раньше часть полей можно было задать, но они не применялись при публикации — теперь применяются.
- **Страница записи** — обрезка видео из меню перезапуска этапов; редактирование индивидуальных настроек без создания нового шаблона; привязка к существующему шаблону; видео открывается сразу при входе на страницу.
- **Список записей** — массовый запуск обрезки; при ручном запуске обработки доступны те же настройки описания, что и в шаблонах.
- **Удобнее формы** — выпадающие списки стали единообразными и не обрезаются в модальных окнах; редкие опции спрятаны в блок «Дополнительно».
- **VK** — исправлено: отключение комментариев и сжатие видео теперь реально передаются при загрузке.

**Новое в `v0.10.2`** — удобнее работать в интерфейсе и надёжнее эксплуатация:
- **Единые фильтры и поиск** — во всех разделах (записи, шаблоны, пресеты, источники, учётные данные, автоматизации) одинаковый тулбар: фильтры применяются сразу, активные условия видны чипами. В источниках появился поиск.
- **Настройки аккаунта** — профиль с ключевыми цифрами использования, управление активными сессиями в одном месте, загрузка файлов перетаскиванием. Визуально выровнены все разделы приложения.
- **Мониторинг для команды** — дашборд «LEAP Overview» в Grafana: активные пользователи, записи, загрузки, успешность, выручка. Логи хранятся в облаке 90 дней; при ошибках проще найти конкретную запись и пользователя.
- **Надёжность инфраструктуры** — проверки готовности сервиса перед приёмом трафика; ежедневные резервные копии Redis; данные не удаляются при обычном перезапуске контейнеров.
- **Защита данных на сервере** — видео и базы переживают пересоздание виртуальной машины; случайное удаление инфраструктуры заблокировано на уровне Terraform.
- **Для администраторов** — при обновлении нужна одноразовая настройка Grafana и создание постоянных томов Docker. Подробности — [DEPLOYMENT.md](backend/docs/guides/DEPLOYMENT.md).

**Новое в `v0.10.1`** — контроль входа и безопасность сессий:
- **Мгновенный выход со всех устройств** — кнопка «Выйти везде» срабатывает сразу, без ожидания до 30 минут.
- **Активные сессии** — в настройках видно, с каких устройств выполнен вход (браузер, ОС, время активности); можно отключить отдельное устройство или все, кроме текущего.
- **Смена пароля** — автоматически завершает все остальные сессии.
- **Для администраторов** — после обновления все пользователи один раз перелогинятся. Подробности — [SESSIONS.md](backend/docs/guides/SESSIONS.md).

**Новое в `v0.10.0`** — появился веб-интерфейс и production-запуск:
- **Веб-интерфейс** — полноценный UI для работы с записями, шаблонами, пресетами, автоматизациями, источниками и настройками. Управление платформой через браузер, без необходимости работать только через API.
- **Production в облаке** — развёртывание на Yandex Cloud: файлы в облачном хранилище, HTTPS, мониторинг, автоматический деплой обновлений.
- **Просмотр видео** — воспроизведение напрямую из облака, без нагрузки на сервер приложения.

**Ранее (`v0.9.x`)** — ключевые возможности до появления UI:
- **Много источников и площадок** — Zoom, YouTube/VK/Rutube по ссылке, Яндекс.Диск на входе; публикация на YouTube, VK и Я.Диск.
- **Шаблоны и автоматизация** — гибкие описания на Jinja2, preview перед сохранением, расписания и batch-обработка.
- **Удобство для оператора** — копирование шаблонов, пресетов и автоматизаций одной кнопкой; экспорт записей в Excel/CSV; вопросы для самопроверки в описании лекции.
- **Надёжность пайплайна** — поддержка WebM/MKV и других форматов, устойчивее обрезка и загрузка с разных источников.

---

## 📄 **Лицензия**

**Business Source License 1.1**

Проект распространяется под лицензией Business Source License 1.1. См. файл [LICENSE](LICENSE) для полной информации.

---

## 📞 **Сотрудничетсво**

**Телеграм:** [Gordey Zuev](https://t.me/WhiteShape)
**Почта** [gordey.zuev@gmail.com](mailto:gordey.zuev@gmail.com)

---

**Status:** In Active Development • Beta
