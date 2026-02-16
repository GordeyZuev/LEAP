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
6. **StatsService** — статистика по записям, транскрипциям, хранилищу

---

## User Endpoints

### GET /api/v1/users/me/quota

Получить полный статус квот текущего пользователя.

**Требует:** JWT токен

**Response:**
```json
{
  "subscription": null,
  "current_usage": {
    "period": 202602,
    "recordings_count": 3,
    "storage_bytes": 1342177280,
    "concurrent_tasks_count": 0,
    "overage_recordings_count": 0,
    "overage_cost": 0.00
  },
  "effective_quotas": {
    "max_recordings_per_month": null,
    "max_storage_gb": null,
    "max_concurrent_tasks": null,
    "max_automation_jobs": null,
    "min_automation_interval_hours": null
  }
}
```

**Ключевые поля:**
- `subscription` — данные подписки (если есть кастомный план, иначе `null`)
- `effective_quotas` — эффективные лимиты (`null` = безлимит). Источник: `DEFAULT_QUOTAS` из `config/settings.py`, переопределяется планом подписки и custom overrides
- `current_usage` — использование за текущий период (YYYYMM)

**Поведение без подписки:**
- По умолчанию все пользователи получают `DEFAULT_QUOTAS` (все `null` = безлимит)
- Подписка создаётся только при назначении кастомного плана

---

### GET /api/v1/users/me/stats

Получить статистику использования.

**Требует:** JWT токен

**Query Parameters:**
- `from_date` (date, optional) — начало периода (YYYY-MM-DD)
- `to_date` (date, optional) — конец периода (YYYY-MM-DD)

**Examples:**
```bash
# Статистика за всё время
GET /api/v1/users/me/stats

# За конкретный период
GET /api/v1/users/me/stats?from_date=2026-01-01&to_date=2026-01-31
```

**Response:**
```json
{
  "recordings_total": 42,
  "recordings_by_status": {
    "READY": 30,
    "PROCESSING": 2,
    "DOWNLOADED": 5,
    "INITIALIZED": 5
  },
  "recordings_by_template": [
    {"template_id": 1, "template_name": "ML Lectures", "count": 20},
    {"template_id": 3, "template_name": "Seminars", "count": 10}
  ],
  "transcription_total_seconds": 86400.55,
  "storage_bytes": 5368709120,
  "storage_gb": 5.0,
  "period": {
    "from_date": "2026-01-01",
    "to_date": "2026-01-31"
  }
}
```

**Ключевые поля:**
- `recordings_total` — общее количество записей
- `recordings_by_status` — разбивка по статусам
- `recordings_by_template` — количество обработанных записей по шаблонам (только READY)
- `transcription_total_seconds` — сумма `final_duration` всех транскрибированных записей (в секундах)
- `storage_bytes` / `storage_gb` — размер пользовательской папки на диске
- `period` — период фильтрации (если передан, иначе `null` = за всё время)

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

## Архитектура

### Компоненты

```
api/
├── routers/
│   ├── users.py           # /me/quota, /me/stats endpoints
│   ├── admin.py           # Admin stats endpoints
├── auth/
│   └── admin.py           # Admin dependency (role check)
├── schemas/
│   ├── admin/
│   │   └── stats.py       # Admin stats schemas
│   ├── auth/
│   │   └── subscription.py  # QuotaStatusResponse (subscription: ... | None)
│   └── user/
│       └── stats.py       # UserStatsResponse
├── services/
│   ├── quota_service.py   # QuotaService (fallback → DEFAULT_QUOTAS)
│   └── stats_service.py   # StatsService (recordings, transcription, storage)
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

# 3. Посмотреть статистику
curl http://localhost:8000/api/v1/users/me/stats \
  -H "Authorization: Bearer ACCESS_TOKEN"

# 4. Статистика за январь 2026
curl "http://localhost:8000/api/v1/users/me/stats?from_date=2026-01-01&to_date=2026-01-31" \
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
| Quota + Stats endpoints | ✅ Готов | 2 endpoints (/me/quota, /me/stats) |
| Admin endpoints | ✅ Готов | 3 endpoints |
| Admin dependency | ✅ Готов | Role check |
| Updated /users/me | ✅ Готов | Simplified response |
| Linter errors | ✅ 0 | Clean code |
| Import checks | ✅ Passed | All imports successful |

---

## Итоги

### Добавлено

- ✅ 2 user endpoints (`/api/v1/users/me/quota`, `/api/v1/users/me/stats`)
- ✅ 3 admin stats endpoints (`/overview`, `/users`, `/quotas`)
- ✅ Admin dependency с проверкой роли
- ✅ Упрощен `/api/v1/users/me` (убрана quota_status)
- ✅ `DEFAULT_QUOTAS` в `config/settings.py` (дефолты в коде, не в БД)
- ✅ `StatsService` для статистики пользователей

### Файлы созданы

- `api/routers/admin.py` - Admin stats router
- `api/auth/admin.py` - Admin dependency
- `api/schemas/admin/__init__.py` - Admin schemas export
- `api/schemas/admin/stats.py` - Admin stats schemas
- `docs/QUOTA_AND_ADMIN_API.md` - Документация

### Файлы изменены

- `api/routers/users.py` - `/me/quota`, `/me/stats` endpoints
- `api/services/stats_service.py` - StatsService
- `api/schemas/user/stats.py` - UserStatsResponse
- `api/auth/dependencies.py` - Обновлен `check_user_quotas`
- `api/schemas/auth/response.py` - Добавлен `UserMeResponse`
- `api/schemas/auth/__init__.py` - Обновлены экспорты
- `api/main.py` - Добавлен admin роутер
- `database/auth_models.py` - Исправлен relationship для subscription

**Всего endpoints:** 67 (было 65)
**Linter errors:** 0 ✅
