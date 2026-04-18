# Architecture Decision Records - Overview

**Проект:** LEAP Platform
**Версия:** 2.1 (Актуализировано: апрель 2026)
**Статус:** Production-Ready Multi-tenant SaaS

---

## 📋 Содержание

1. [Обзор](#обзор)
2. [Контекст и эволюция](#контекст-и-эволюция)
3. [Ключевые архитектурные решения](#ключевые-архитектурные-решения)
4. [Текущее состояние системы](#текущее-состояние-системы)
5. [См. также](#см-также)

---

## Обзор

### Цель документа

Данный документ описывает ключевые архитектурные решения для LEAP Platform - production-ready multi-tenant SaaS платформы для автоматизации обработки образовательного видеоконтента.

### Ключевые достижения

**✅ Реализовано (Production-Ready):**
- Multi-tenancy с полной изоляцией данных
- REST API с полной типизацией
- JWT Authentication + OAuth 2.0 (YouTube, VK, Zoom)
- Асинхронная обработка (Celery + Redis)
- Template-driven automation
- Subscription plans с квотами
- FSM для надежной обработки
- Admin API для мониторинга

**🔧 Технологии:**
- FastAPI (async)
- PostgreSQL
- Redis + Celery
- Pydantic V2
- SQLAlchemy (async)
- Alembic

---

## Контекст и эволюция

### Исходное состояние (v0.1 - CLI)

**Что было:**
- CLI-приложение для обработки Zoom записей
- Единая БД без изоляции
- Конфигурации в JSON файлах
- Нет API и аутентификации
- Single-user система

**Проблемы:**
- Невозможность масштабирования
- Отсутствие изоляции данных
- Ручная работа для каждой записи
- Нет автоматизации

### Трансформация (v0.5 - v0.9)

**Этапы развития:**
1. **v0.5** - Добавление PostgreSQL, базовая БД
2. **v0.6** - Модульная архитектура (separation of concerns)
3. **v0.7** - Multi-tenancy (shared database + user_id)
4. **v0.8** - REST API + JWT authentication
5. **v0.9** - Celery, OAuth 2.0, Templates, Subscriptions

### Текущее состояние

**Production-Ready SaaS платформа:**
- REST API endpoints
- Multi-tenant database
- OAuth integrations (YouTube, VK, Zoom)
- Subscription plans
- Template-driven automation
- Full async processing

---

## Ключевые архитектурные решения

### ADR-001: Multi-Tenancy Model

**Решение:** Shared Database с изоляцией через `user_id`

**Архитектура:**
```
┌──────────────────────────────────────────┐
│        Multi-Tenant Isolation            │
└──────────────────────────────────────────┘

User A (user_id=1)          User B (user_id=2)
    │                              │
    ├─ recordings (user_id=1)     ├─ recordings (user_id=2)
    ├─ templates (user_id=1)      ├─ templates (user_id=2)
    ├─ credentials (user_id=1)    ├─ credentials (user_id=2)
    └─ media/user_1/              └─ media/user_2/

    ┌─────────────────────────────────────┐
    │   PostgreSQL (shared database)      │
    │   + Row-level filtering by user_id  │
    └─────────────────────────────────────┘
```

**Обоснование:**

**Альтернативы:**
1. **Shared Database + Tenant ID** ← **выбрано**
2. Separate Databases per tenant
3. Separate Schemas (PostgreSQL)

**Преимущества выбранного решения:**
- ✅ Простота управления (единые миграции)
- ✅ Эффективное использование ресурсов
- ✅ Легко масштабировать горизонтально
- ✅ Проще бэкапы и восстановление
- ✅ Подходит для 10-1000 пользователей

**Риски и митигация:**
- **Риск утечки данных:** Repository pattern с автоматической фильтрацией по user_id
- **Производительность:** Индексы на (user_id, ...) во всех таблицах
- **Сложность запросов:** ServiceContext + Dependency Injection

**Реализация:**
- `api/core/context.py` - ServiceContext с user_id
- `api/repositories/` - автоматическая фильтрация
- `api/middleware/` - извлечение user_id из JWT

**Статус:** ✅ Полностью реализовано

---

### ADR-002: Authentication & Authorization

**Решение:** JWT Tokens (access + refresh) + OAuth 2.0

**Архитектура:**
```
┌──────────────────────────────────────────┐
│        Authentication Flow               │
└──────────────────────────────────────────┘

1. Registration → User created
2. Login → JWT (access + refresh)
3. Request → Bearer token validation
4. Token expired → Refresh token
5. OAuth → YouTube/VK/Zoom authorization
```

**Обоснование:**

**Альтернативы:**
1. **JWT Tokens** ← **выбрано**
2. API Keys
3. Session-based auth

**Преимущества:**
- ✅ Stateless архитектура
- ✅ Масштабируемость
- ✅ Стандарт для REST API
- ✅ Поддержка refresh tokens
- ✅ Совместимость с OAuth 2.0

**Реализация:**

**JWT Tokens (дефолты в `config/settings.py`, переопределяются через env):**
- Access Token: по умолчанию 30 минут
- Refresh Token: по умолчанию 7 дней (хранится в БД)
- Алгоритм: HS256
- Payload: user_id, role, permissions

**Roles:**
- `admin` - полный доступ, управление пользователями
- `user` - доступ к своим ресурсам

**OAuth 2.0 интеграции:**
- **YouTube** - OAuth 2.0, auto-refresh tokens
- **VK** - VK ID OAuth 2.1 (PKCE) + Implicit Flow API
- **Zoom** - OAuth 2.0 + Server-to-Server dual mode

**Файлы:**
- `api/auth/security.py` — JWT создание и валидация
- `api/routers/auth.py` - endpoints (register, login, refresh)
- `api/routers/oauth/` - OAuth flows для всех платформ
- `database/auth_models.py` - User, RefreshToken models

**Статус:** ✅ Полностью реализовано

---

### ADR-003: Configuration Hierarchy

**Решение:** Трехуровневая иерархия (User Config → Template → Recording Override)

**Архитектура:**
```
┌──────────────────────────────────────────────────────┐
│           Configuration Resolution                    │
└──────────────────────────────────────────────────────┘

Level 1: User Config (defaults)
    ↓
Level 2: Template Config (if template_id set)
    ↓
Level 3: Recording Override (processing_preferences)
    ↓
Final Config → Used for processing
```

**Обоснование:**

**Требования:**
- Глобальные defaults для пользователя
- Template-specific настройки
- Per-recording overrides (высший приоритет)
- Live updates при изменении template

**Преимущества:**
- ✅ DRY - настройки переиспользуются
- ✅ Гибкость - можно переопределить на любом уровне
- ✅ Live updates - изменения template применяются автоматически
- ✅ Explicit overrides - ясно видны ручные изменения

**Реализация:**

**Структура:**
```python
# User Config (stored in user_configs table)
{
  "transcription": {"language": "ru", "enable_topics": true},
  "upload": {"auto_upload": false}
}

# Template Config (stored in recording_templates table)
{
  "processing_config": {...},
  "metadata_config": {...},
  "output_config": {"preset_ids": [1, 2], "auto_upload": true}
}

# Recording Override (stored in recordings.processing_preferences)
{
  "transcription": {"language": "en"}  # Only overrides
}

# Final merged config
{
  "transcription": {"language": "en", "enable_topics": true},  # en from override
  "upload": {"auto_upload": true}  # true from template
}
```

**ConfigResolver:**
- `api/services/config_resolver.py` - единая точка resolution
- Deep merge с приоритетами
- Endpoints для управления:
  - `GET /recordings/{id}/config` - resolved config
  - `PUT /recordings/{id}/config` - set override
  - `DELETE /recordings/{id}/config` - reset to template

**Статус:** ✅ Полностью реализовано

---

### ADR-004: Data Storage & Encryption

**Решение:** PostgreSQL + JSONB + Fernet Encryption

**Архитектура:**
```
┌──────────────────────────────────────────┐
│           Data Storage                    │
└──────────────────────────────────────────┘

PostgreSQL:
├─ Structured data (users, recordings, templates)
├─ JSONB для гибких конфигураций
├─ GIN индексы на JSONB полях
└─ Full-text search (когда нужно)

Encryption:
├─ user_credentials.encrypted_data (Fernet)
├─ Encryption key в environment
└─ Automatic encryption/decryption в CredentialService
```

**Обоснование:**

**JSONB vs отдельные таблицы:**
- ✅ Гибкость - легко добавлять новые поля
- ✅ Производительность - GIN индексы быстрые
- ✅ Простота - меньше таблиц и JOIN'ов
- ✅ Подходит для metadata, конфигураций

**Fernet Encryption:**
- Symmetric encryption (AES-128)
- Простой API (encrypt/decrypt)
- Стандарт Python (cryptography library)
- Ключ в environment variable

**Реализация:**
- `api/auth/encryption.py` — Fernet-обёртка для credentials
- `api/services/credential_service.py` — шифрование/дешифрование при сохранении и чтении
- Environment: **`SECURITY_ENCRYPTION_KEY`** (см. [CREDENTIAL_SECURITY.md](guides/CREDENTIAL_SECURITY.md))

**Статус:** ✅ Полностью реализовано

---

### ADR-005: Template Matching System

**Решение:** First-match strategy с priority ordering

**Архитектура:**
```
┌──────────────────────────────────────────┐
│        Template Matching Flow            │
└──────────────────────────────────────────┘

1. Recording synced from source
    ↓
2. Match against all templates:
   - exact_matches (display_name)
   - keywords (case-insensitive)
   - regex patterns
   - source_ids filter
    ↓
3. Select first match (by template.created_at ASC)
    ↓
4. Set recording.template_id
    ↓
5. Auto-apply template config
```

**Matching Rules:**
```json
{
  "exact_matches": ["Lecture: Machine Learning", "AI Course"],
  "keywords": ["ML", "AI", "neural networks"],
  "patterns": ["Лекция \\d+:.*ML", "\\[МО\\].*"],
  "source_ids": [1, 3],
  "match_mode": "any"  // "any" or "all"
}
```

**Обоснование:**

**Альтернативы:**
1. **First-match** ← **выбрано** (simple, predictable)
2. Best-match (score-based)
3. Multiple templates (array)

**Преимущества:**
- ✅ KISS - простая и понятная логика
- ✅ Предсказуемость - всегда ясно какой template
- ✅ Производительность - O(n) по templates
- ✅ Достаточно для 95% use cases

**Lifecycle:**
- Auto-match при sync
- Re-match при создании нового template
- Preview re-match перед применением
- Unmap при удалении template

**Реализация:**
- `api/services/template_matcher.py` - matching logic
- `api/repositories/template_repository.py` - DB queries
- Endpoints:
  - `POST /templates/{id}/preview-match` - preview
  - `POST /templates/{id}/rematch` - apply
  - `GET /recordings?is_mapped=false` - unmapped list

**Статус:** ✅ Полностью реализовано

**См. также:** [TEMPLATES.md](guides/TEMPLATES.md) - Template matching & re-match

---

### ADR-006: Async Processing Pipeline

**Решение:** Celery + Redis; маршрутизация по очередям (`downloads`, `uploads`, `async_operations`, `processing_cpu`, `maintenance`), orchestration через chains.

Подробности очередей, задач и параллелизма — **[ADR-011: Async Processing (Celery)](ADR_FEATURES.md#adr-011-async-processing-celery)**. Конфигурация: `api/celery_app.py`, цели в `backend/Makefile`.

**Статус:** ✅ Полностью реализовано

---

### ADR-007: Subscription & Quota System

**Решение:** `DEFAULT_QUOTAS` в коде + опциональные планы подписки и учёт использования.

Детали моделей, лимитов и API — **[ADR-012: Quotas & Subscriptions](ADR_FEATURES.md#adr-012-quotas--subscriptions)**.

**Статус:** ✅ Полностью реализовано

---

### ADR-008: FSM для Processing Status

**Решение:** Явные статусы записи и целей выгрузки, валидация переходов в сервисном слое.

Детали и диаграммы — **[ADR-015: FSM](ADR_FEATURES.md#adr-015-fsm-для-надежной-обработки)** и [ARCHITECTURE_SCHEMAS.md](ARCHITECTURE_SCHEMAS.md).

**Статус:** ✅ Полностью реализовано

---

### ADR-009: API Design Principles

**Решение:** RESTful API с консистентными конвенциями

**Принципы:**

**1. URL Structure:**
```
/api/v1/{resource}
/api/v1/{resource}/{id}
/api/v1/{resource}/{id}/{action}
/api/v1/{resource}/bulk/{action}
```

**2. HTTP Methods:**
- `GET` - чтение (idempotent)
- `POST` - создание + actions
- `PATCH` - частичное обновление
- `DELETE` - удаление
- **NO PUT** - используем PATCH для consistency

**3. Response Format:**
```json
// Success
{
  "id": 1,
  "field": "value"
}

// Error
{
  "detail": "Error message",
  "error_code": "RESOURCE_NOT_FOUND"
}

// Bulk operation
{
  "message": "Operation completed",
  "succeeded": 10,
  "failed": 2,
  "details": [...]
}
```

**4. Naming Conventions:**
- snake_case для полей JSON
- kebab-case для URL paths
- SCREAMING_SNAKE_CASE для enums

**5. Типизация:**
- Pydantic V2 для всех request/response
- 100% type coverage
- OpenAPI автогенерация

**Реализация:**
- REST endpoints с полной типизацией
- Pydantic моделей
- Swagger UI: `/docs`
- OpenAPI: `/openapi.json`

**Статус:** ✅ Полностью реализовано

---

## Текущее состояние системы

### Production Readiness

| Компонент | Статус | Комментарий |
|-----------|--------|-------------|
| Multi-tenancy | ✅ | Полная изоляция |
| Authentication | ✅ | JWT + OAuth 2.0 |
| API | ✅ | REST endpoints |
| Database | ✅ | Auto-init migrations |
| Async Processing | ✅ | Celery + Redis |
| Subscriptions | ✅ | Plans + custom quotas |
| Templates | ✅ | Auto-matching + config hierarchy |
| OAuth | ✅ | YouTube, VK, Zoom |
| Admin API | ✅ | Stats & monitoring |
| Encryption | ✅ | Fernet для credentials |
| Security | ✅ | CSRF, token refresh |
| Documentation | ✅ | Complete |

**Готово к production:** ✅

**Рекомендуется добавить:**
- Load testing
- Monitoring (Prometheus/Grafana)
- WebSocket для real-time (опционально)

---

## См. также

### Архитектура
- [ADR_FEATURES.md](ADR_FEATURES.md) — автоматизация, Celery/очереди, квоты, FSM и др. (детальные ADR-010+)
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Схемы БД, JSONB структуры
- [TECHNICAL.md](TECHNICAL.md) — модули и справка (эндпоинты — OpenAPI)

### API & Integration
- [TECHNICAL.md](TECHNICAL.md) — обзор API; детальный контракт — OpenAPI `/docs`
- [OAUTH.md](guides/OAUTH.md) - OAuth setup & integration

### Features
- [TEMPLATES.md](guides/TEMPLATES.md) - Templates, matching, metadata & configuration

### Deployment
- [DEPLOYMENT.md](guides/DEPLOYMENT.md) - Production deployment & infrastructure

---

**Документ обновлен:** Апрель 2026
**Следующий review:** По мере добавления новых ADR
