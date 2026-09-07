# Quota & Admin API Documentation

**Дата:** 16 февраля 2026
**Версия:** v3.0

---

## Обзор изменений

### Что было сделано

1. **Quota & Stats endpoints** в `/api/v1/users/me/`
2. **Упрощен `/api/v1/users/me`** - убрана информация о квотах
3. **Admin роутер** (`/api/v1/admin/stats`) для просмотра статистики
4. **Admin dependency** - проверка роли `admin`
5. **DEFAULT_QUOTAS** — дефолтные лимиты в коде (`config/settings.py`), не в БД
6. **AnalyticsService** — activity time series for Usage / Admin charts (see [USAGE_AND_ANALYTICS.md](USAGE_AND_ANALYTICS.md))

---

## User Endpoints

### GET /api/v1/users/me/quota

Получить полный статус квот текущего пользователя.

**Требует:** JWT токен

**Response (shape):**
```json
{
  "subscription": null,
  "current_usage": {
    "period": 202609,
    "recordings_count": 3,
    "storage_gb": 1.25,
    "concurrent_tasks_count": 0,
    "transcriptions_count": 2,
    "processing_count": 1,
    "uploads_count": 4,
    "overage_recordings_count": 0,
    "overage_cost": "0.00"
  },
  "recordings": { "used": 3, "limit": null, "available": null },
  "storage": { "used_gb": 1.25, "limit_gb": null, "available_gb": null },
  "concurrent_tasks": { "used": 0, "limit": 5, "available": 5 },
  "automation_jobs": { "used": 2, "limit": 10, "available": 8 },
  "transcriptions": { "used": 2, "limit": null, "available": null },
  "processing": { "used": 1, "limit": null, "available": null },
  "templates": { "used": 4, "limit": 20, "available": 16 },
  "credentials": { "used": 1, "limit": null, "available": null },
  "is_overage_enabled": false,
  "overage_cost_this_month": "0.00",
  "overage_limit": null
}
```

**Ключевые поля:**
- `subscription` — данные подписки (если есть кастомный план, иначе `null`)
- Блоки `recordings`, `storage`, `concurrent_tasks`, `automation_jobs`, `transcriptions`, `processing`, `templates`, `credentials` — каждый `{ used, limit, available }`; `limit: null` = безлимит
- `automation_jobs.used`, `templates.used`, `credentials.used` — live-подсчёт строк (не месячный счётчик); templates — named templates без default
- `current_usage` — месячные счётчики за период `YYYYMM`
- Activity-графики в UI — `GET /users/me/analytics` (см. [USAGE_AND_ANALYTICS.md](USAGE_AND_ANALYTICS.md))

**Поведение без подписки:**
- По умолчанию все пользователи получают `DEFAULT_QUOTAS` (все `null` = безлимит)
- Подписка создаётся только при назначении кастомного плана

---

### GET /api/v1/users/me/analytics

Activity charts and period totals for Settings → Usage. See [USAGE_AND_ANALYTICS.md](USAGE_AND_ANALYTICS.md).

**Требует:** JWT токен

**Query Parameters:** `from`, `to` (inclusive `YYYY-MM-DD`; max 366 days)

---

## Updated User Endpoint

### GET /api/v1/users/me

Получить базовую информацию о текущем пользователе (без квот).

**Требует:** JWT токен

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "timezone": "Europe/Moscow",
  "role": "user",
  "is_active": true,
  "is_verified": false,
  "created_at": "2026-01-09T10:00:00Z",
  "last_login_at": "2026-01-09T12:00:00Z"
}
```

**Изменения:**
- ❌ Убрано поле `quota_status`
- ✅ Для квот используйте `GET /api/v1/users/me/quota`

---

## Admin Endpoints

### GET /api/v1/admin/stats/overview

Получить общую статистику платформы.

**Требует:** JWT токен + роль `admin`

**Response:**
```json
{
  "total_users": 150,
  "active_users": 142,
  "total_recordings": 1250,
  "total_storage_gb": 320.50,
  "total_plans": 4,
  "users_by_plan": {
    "free": 120,
    "plus": 20,
    "pro": 8,
    "enterprise": 2
  }
}
```

---

### GET /api/v1/admin/stats/users

Получить детальную статистику по пользователям.

**Требует:** JWT токен + роль `admin`

**Query Parameters:**
- `page` (int, default=1) - номер страницы
- `page_size` (int, default=50, max=100) - размер страницы
- `exceeded_only` (bool, default=false) - только пользователи с превышением квот
- `plan_name` (str, optional) - фильтр по плану (free, plus, pro, enterprise)

**Examples:**
```bash
# Все пользователи (первая страница)
GET /api/v1/admin/stats/users

# Только пользователи с превышением квот
GET /api/v1/admin/stats/users?exceeded_only=true

# Только пользователи на Free плане
GET /api/v1/admin/stats/users?plan_name=free

# Вторая страница, 20 пользователей
GET /api/v1/admin/stats/users?page=2&page_size=20
```

**Response:**
```json
{
  "total_count": 150,
  "users": [
    {
      "user_id": 1,
      "email": "user1@example.com",
      "plan_name": "free",
      "recordings_used": 8,
      "recordings_limit": 10,
      "storage_used_gb": 3.25,
      "storage_limit_gb": 5,
      "is_exceeding": false,
      "overage_enabled": false,
      "overage_cost": 0.00
    },
    {
      "user_id": 5,
      "email": "user5@example.com",
      "plan_name": "plus",
      "recordings_used": 55,
      "recordings_limit": 50,
      "storage_used_gb": 28.50,
      "storage_limit_gb": 25,
      "is_exceeding": true,
      "overage_enabled": true,
      "overage_cost": 2.50
    }
  ],
  "page": 1,
  "page_size": 50
}
```

**Ключевые поля:**
- `is_exceeding` - превышены ли квоты (recordings или storage)
- `overage_enabled` - включен ли Pay-as-you-go
- `overage_cost` - стоимость превышения за текущий месяц

---

### GET /api/v1/admin/stats/quotas

Получить статистику использования квот по планам.

**Требует:** JWT токен + роль `admin`

**Query Parameters:**
- `period` (int, optional) - период (YYYYMM), по умолчанию текущий

**Examples:**
```bash
# Текущий месяц
GET /api/v1/admin/stats/quotas

# Январь 2026
GET /api/v1/admin/stats/quotas?period=202601
```

**Response:**
```json
{
  "period": 202601,
  "total_recordings": 1250,
  "total_storage_gb": 320.50,
  "total_overage_cost": 125.50,
  "plans": [
    {
      "plan_name": "free",
      "total_users": 120,
      "total_recordings": 850,
      "total_storage_gb": 180.25,
      "avg_recordings_per_user": 7.08,
      "avg_storage_per_user_gb": 1.50
    },
    {
      "plan_name": "plus",
      "total_users": 20,
      "total_recordings": 280,
      "total_storage_gb": 95.50,
      "avg_recordings_per_user": 14.00,
      "avg_storage_per_user_gb": 4.78
    },
    {
      "plan_name": "pro",
      "total_users": 8,
      "total_recordings": 100,
      "total_storage_gb": 38.75,
      "avg_recordings_per_user": 12.50,
      "avg_storage_per_user_gb": 4.84
    },
    {
      "plan_name": "enterprise",
      "total_users": 2,
      "total_recordings": 20,
      "total_storage_gb": 6.00,
      "avg_recordings_per_user": 10.00,
      "avg_storage_per_user_gb": 3.00
    }
  ]
}
```

---

## Admin: управление пользователями, подписками и планами

Добавлено в v0.10.5.0. Все эндпоинты требуют `role=admin` (`get_current_admin`).

### Пользователи

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/v1/admin/users` | Список с пагинацией; фильтры `search` (по email), `role`, `page`, `page_size` |
| `GET` | `/api/v1/admin/users/{user_id}` | Полный профиль (роль, `is_active`, 5 feature-флагов) |
| `PATCH` | `/api/v1/admin/users/{user_id}` | Обновить `role`, `is_active` и любой из feature-флагов (`can_transcribe`, `can_process_video`, `can_upload`, `can_update_uploaded_videos`, `can_export_data`). Лимиты на темплейты/credentials — через подписку (`custom_max_templates`, `custom_max_credentials`) |
| `GET` | `/api/v1/admin/users/{user_id}/events` | История из `usage_events`; фильтры `event_type`, `limit`, `offset` |

### Подписки и квоты

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/v1/admin/users/{user_id}/subscription` | Текущая подписка + `effective_quotas` + полный `quota_status` (использование) |
| `POST` | `/api/v1/admin/users/{user_id}/subscription` | Назначить/заменить план (`plan_id` + опциональные `custom_*` оверайды) |
| `PATCH` | `/api/v1/admin/users/{user_id}/subscription` | Обновить `custom_*` оверайды квот |
| `DELETE` | `/api/v1/admin/users/{user_id}/subscription` | Снять подписку (204; 404 если её нет) — откат на `DEFAULT_QUOTAS` |

### Планы

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/v1/admin/plans` | Список планов (`active_only`) |
| `POST` | `/api/v1/admin/plans` | Создать план |
| `PATCH` | `/api/v1/admin/plans/{plan_id}` | Обновить план |

### Новые лимиты и счётчики

- `subscription_plans.max_transcriptions_per_month`, `max_processing_per_month` — hard limits (NULL = безлимит).
- `quota_usage.transcriptions_count`, `processing_count`, `uploads_count` — месячные счётчики (ключ `period` = `YYYYMM`).
- Лимит одновременных задач (`max_concurrent_tasks`) проверяется по числу записей с `on_air=true` (drift-free), а не по хранимому счётчику.
- `GET /me/quota` отдаёт `current_usage` (месячные счётчики) и восемь блоков `{ used, limit, available }` (включая live `automation_jobs`, `templates`, `credentials`).
- Product analytics UI и API: [USAGE_AND_ANALYTICS.md](USAGE_AND_ANALYTICS.md).

---

## Архитектура

### Компоненты

```
api/
├── routers/
│   ├── users.py           # /me/quota, /me/analytics endpoints
│   ├── admin.py           # Admin stats endpoints
├── auth/
│   └── admin.py           # Admin dependency (role check)
├── schemas/
│   ├── admin/
│   │   └── stats.py       # Admin stats schemas
│   ├── auth/
│   │   └── subscription.py  # QuotaStatusResponse (subscription: ... | None)
│   └── user/
│       └── stats.py       # StatsPeriod, TemplateStats (shared with analytics)
├── services/
│   ├── quota_service.py   # QuotaService (fallback → DEFAULT_QUOTAS)
│   └── analytics_service.py  # Product analytics time series
└── middleware/
    └── quota.py           # check_user_quotas, increment_recordings_quota
config/
└── settings.py            # DEFAULT_QUOTAS constant (all None = unlimited)
```

### Dependency: get_current_admin

```python
from api.auth.admin import get_current_admin

@router.get("/admin/stats/overview")
async def get_overview_stats(
    _admin: UserInDB = Depends(get_current_admin),
):
    # Only users with role="admin" can access
    ...
```

**Логика:**
1. Проверяет JWT токен (через `get_current_user`)
2. Проверяет `current_user.role == "admin"`
3. Возвращает `403 Forbidden` если не админ

---

## Примеры использования

### User: Проверка квот и статистики

```bash
# 1. Получить JWT токен
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'

# Response: {"access_token": "...", "refresh_token": "..."}

# 2. Проверить квоты
curl http://localhost:8000/api/v1/users/me/quota \
  -H "Authorization: Bearer ACCESS_TOKEN"

# 3. Activity analytics (Usage tab)
curl "http://localhost:8000/api/v1/users/me/analytics?from=2026-01-01&to=2026-01-31" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

### Admin: Статистика платформы

```bash
# 1. Войти как админ
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}'

# 2. Общая статистика
curl http://localhost:8000/api/v1/admin/stats/overview \
  -H "Authorization: Bearer ADMIN_TOKEN"

# 3. Пользователи с превышением квот
curl "http://localhost:8000/api/v1/admin/stats/users?exceeded_only=true" \
  -H "Authorization: Bearer ADMIN_TOKEN"

# 4. Статистика по квотам за декабрь 2025
curl "http://localhost:8000/api/v1/admin/stats/quotas?period=202512" \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

---

## Безопасность

### Роли

- **user** - обычный пользователь (доступ к `/api/v1/quota`)
- **admin** - администратор (доступ к `/api/v1/admin/*`)

### Проверка прав

```python
# User endpoints - требуют только JWT токен
@router.get("/users/me/quota")
async def get_my_quota(current_user: UserInDB = Depends(get_current_user)):
    ...

# Admin endpoints - требуют JWT + role=admin
@router.get("/admin/stats/overview")
async def get_overview(_admin: UserInDB = Depends(get_current_admin)):
    ...
```

---

## Миграция с предыдущей версии

### Что изменилось

**Было:**
```bash
GET /api/v1/users/me
# → Возвращал user + quota_status
```

**Стало:**
```bash
GET /api/v1/users/me
# → Возвращает только user (без quota_status)

GET /api/v1/users/me/quota
# → Возвращает полный quota_status
```

### Обновление клиентского кода

**Старый код:**
```typescript
const response = await fetch('/api/v1/users/me');
const { user, quota_status } = await response.json();
```

**Новый код:**
```typescript
// Базовая информация о пользователе
const userResponse = await fetch('/api/v1/users/me');
const user = await userResponse.json();

// Квоты (отдельный запрос)
const quotaResponse = await fetch('/api/v1/users/me/quota');
const quota_status = await quotaResponse.json();
```

---

## Готовность к Production

| Компонент | Статус | Комментарий |
|-----------|--------|-------------|
| Quota + analytics endpoints | ✅ Готов | `/me/quota`, `/me/analytics` |
| Admin stats endpoints | ✅ Готов | 3 endpoints (`/overview`, `/users`, `/quotas`) |
| Admin management endpoints | ✅ Готов | 10 endpoints (users, subscriptions, plans) — v0.10.5.0 |
| Admin dependency | ✅ Готов | Role check |
| Updated /users/me | ✅ Готов | Simplified response |
| Linter errors | ✅ 0 | Clean code |
| Import checks | ✅ Passed | All imports successful |

---

## Итоги

### Добавлено

- ✅ User endpoints `/api/v1/users/me/quota`, `/api/v1/users/me/analytics`
- ✅ 3 admin stats endpoints (`/overview`, `/users`, `/quotas`)
- ✅ 10 admin management endpoints (users / subscriptions / plans) — v0.10.5.0
- ✅ Admin dependency с проверкой роли
- ✅ Упрощен `/api/v1/users/me` (убрана quota_status)
- ✅ `DEFAULT_QUOTAS` в `config/settings.py` (дефолты в коде, не в БД)
- ✅ `AnalyticsService` для activity-графиков (см. USAGE_AND_ANALYTICS.md)

### Файлы созданы

- `api/routers/admin.py` - Admin stats router
- `api/auth/admin.py` - Admin dependency
- `api/schemas/admin/__init__.py` - Admin schemas export
- `api/schemas/admin/stats.py` - Admin stats schemas
- `docs/guides/QUOTA_AND_ADMIN_API.md` - Документация

### Файлы изменены

- `api/routers/users.py` - `/me/quota`, `/me/analytics` endpoints
- `api/services/analytics_service.py` - AnalyticsService
- `api/schemas/user/stats.py` - StatsPeriod, TemplateStats
- `api/auth/dependencies.py` - Обновлен `check_user_quotas`
- `api/schemas/auth/response.py` - Добавлен `UserMeResponse`
- `api/schemas/auth/__init__.py` - Обновлены экспорты
- `api/main.py` - Добавлен admin роутер
- `database/auth_models.py` - Исправлен relationship для subscription

**Всего endpoints:** 67 (было 65)
**Linter errors:** 0 ✅
