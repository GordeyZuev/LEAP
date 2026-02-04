# OAuth Multiple Accounts Support

**Статус:** ✅ Implemented (Январь 2026)

---

## Проблема

Раньше при OAuth авторизации все креденшлы сохранялись с `account_name="oauth_auto"`. Это приводило к:

- ❌ Перезаписи существующих кредов при повторной авторизации
- ❌ Невозможности иметь несколько аккаунтов на одной платформе
- ❌ UniqueViolationError при попытке добавить второй аккаунт

## Решение

Система автоматически извлекает **уникальный идентификатор аккаунта** из OAuth provider:

### YouTube (Google OAuth)
- **Идентификатор:** Email пользователя
- **Источник:** Google UserInfo API (`https://www.googleapis.com/oauth2/v2/userinfo`)
- **Пример:** `user@gmail.com`

### VK
- **Идентификатор:** User ID в формате `vk_{user_id}`
- **Источник:** VK API (`users.get`)
- **Пример:** `vk_123456789`

### Zoom
- **Идентификатор:** Email пользователя
- **Источник:** Zoom API (`/v2/users/me`)
- **Пример:** `user@company.com`

---

## Как работает

### 1. OAuth Flow

```
User → /oauth/youtube/authorize
    ↓
Получение authorization code
    ↓
Exchange code for access_token
    ↓
🆕 get_account_identifier(platform, access_token)
    ├─ YouTube → GET https://www.googleapis.com/oauth2/v2/userinfo
    ├─ VK → GET https://api.vk.com/method/users.get
    └─ Zoom → GET https://api.zoom.us/v2/users/me
    ↓
Проверка существующих кредов (user_id, platform, account_name)
    ↓
Если существует → UPDATE
Если нет → CREATE
```

### 2. Upsert Pattern

```python
# Check if credentials exist
existing_cred = await cred_repo.get_by_platform(
    user_id=user_id,
    platform="youtube",
    account_name="user@gmail.com"  # Уникальный идентификатор
)

if existing_cred:
    # Update existing credentials (re-authorization)
    credential = await cred_repo.update(existing_cred.id, cred_update)
else:
    # Create new credentials (first authorization)
    credential = await cred_repo.create(cred_create)
```

---

## Примеры использования

### Сценарий 1: Один аккаунт YouTube

```bash
# Первая авторизация
User авторизуется с user1@gmail.com
→ Создается cred: (user_id=5, platform=youtube, account_name=user1@gmail.com)

# Повторная авторизация (обновление токена)
User снова авторизуется с user1@gmail.com
→ Обновляется существующий cred (refresh token обновился)
```

### Сценарий 2: Несколько аккаунтов YouTube

```bash
# Первый аккаунт
User авторизуется с user1@gmail.com
→ Создается cred ID=10: account_name=user1@gmail.com

# Второй аккаунт
User авторизуется с user2@gmail.com
→ Создается cred ID=11: account_name=user2@gmail.com

# Результат в БД:
user_credentials:
  id=10, user_id=5, platform=youtube, account_name=user1@gmail.com
  id=11, user_id=5, platform=youtube, account_name=user2@gmail.com
```

### Сценарий 3: VK Multiple Accounts

```bash
# Первый аккаунт VK
User авторизуется (VK user_id=123456)
→ Создается cred: account_name=vk_123456

# Второй аккаунт VK
User авторизуется (VK user_id=789012)
→ Создается cred: account_name=vk_789012
```

---

## API Endpoints

### List Credentials
```bash
GET /api/v1/credentials
Authorization: Bearer {jwt_token}

Response:
[
  {
    "id": 10,
    "platform": "youtube",
    "account_name": "user1@gmail.com",
    "is_active": true,
    "created_at": "2026-01-18T10:00:00Z"
  },
  {
    "id": 11,
    "platform": "youtube",
    "account_name": "user2@gmail.com",
    "is_active": true,
    "created_at": "2026-01-18T11:00:00Z"
  }
]
```

### Delete Specific Credential
```bash
DELETE /api/v1/credentials/10
Authorization: Bearer {jwt_token}

# Удаляет только user1@gmail.com, user2@gmail.com остается
```

---

## Fallback Behavior

Если не удалось получить идентификатор аккаунта (API недоступен, ошибка):

```python
account_name = "oauth_auto"  # Fallback
logger.warning(f"Failed to get account identifier, using fallback: oauth_auto")
```

**⚠️ В этом случае** при повторной авторизации креды будут перезаписаны.

---

## Database Schema

### user_credentials

```sql
CREATE TABLE user_credentials (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  platform VARCHAR(50) NOT NULL,
  account_name VARCHAR(255),  -- Уникальный идентификатор аккаунта
  encrypted_data TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,

  -- Unique constraint: один user может иметь несколько аккаунтов
  CONSTRAINT ix_user_credentials_user_platform_account
    UNIQUE (user_id, platform, account_name)
);
```

---

## Testing

### Manual Test

```bash
# 1. Start API
make api

# 2. Login
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}' \
  | jq -r '.access_token')

# 3. Authorize YouTube (first account)
curl http://localhost:8000/api/v1/oauth/youtube/authorize \
  -H "Authorization: Bearer $TOKEN"
# → Complete in browser with user1@gmail.com

# 4. Check credentials
curl http://localhost:8000/api/v1/credentials \
  -H "Authorization: Bearer $TOKEN"
# → Should see: account_name=user1@gmail.com

# 5. Authorize YouTube again (second account)
curl http://localhost:8000/api/v1/oauth/youtube/authorize \
  -H "Authorization: Bearer $TOKEN"
# → Complete in browser with user2@gmail.com

# 6. Check credentials again
curl http://localhost:8000/api/v1/credentials \
  -H "Authorization: Bearer $TOKEN"
# → Should see TWO credentials:
#   - account_name=user1@gmail.com
#   - account_name=user2@gmail.com
```

---

## Error Handling

### Ошибка 1: UniqueViolationError (Resolved)

**Before:**
```
ERROR: duplicate key value violates unique constraint
       "ix_user_credentials_user_platform_account"
DETAIL: Key (user_id, platform, account_name)=(6, youtube, oauth_auto) already exists.
```

**After:**
- ✅ Используется email из Google UserInfo
- ✅ Повторная авторизация обновляет существующий cred
- ✅ Разные аккаунты создают отдельные creds

---

## Implementation Files

**Core:**
- `api/routers/oauth.py` - OAuth callbacks + `get_account_identifier()`
- `api/repositories/auth_repos.py` - `UserCredentialRepository`

**Database:**
- `alembic/versions/005_add_account_name_to_credentials.py` - Migration
- `database/auth_models.py` - `UserCredentialModel`

---

## См. также

- [OAUTH.md](OAUTH.md) - Общее руководство по OAuth
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Схема БД

---

**Документ создан:** Январь 2026
**Статус:** Production Ready ✅
