# Zoom Credentials Guide

Полное руководство по добавлению Zoom-аккаунтов в систему.

---

## Содержание

1. [Способы добавления](#способы-добавления)
2. [Способ 1: Server-to-Server OAuth (ручное добавление)](#способ-1-server-to-server-oauth-ручное-добавление)
3. [Способ 2: OAuth 2.0 (через браузер)](#способ-2-oauth-20-через-браузер)
4. [Способ 3: Master Account (несколько под-аккаунтов)](#способ-3-master-account-несколько-под-аккаунтов)
5. [Scopes (разрешения)](#scopes-разрешения)
6. [Создание Input Source](#создание-input-source)
7. [FAQ](#faq)

---

## Способы добавления

| Способ | Тип | Токен | Master Account | Подходит для |
|--------|-----|-------|----------------|--------------|
| Server-to-Server OAuth | Ручное | Бессрочный (auto-refresh) | Да | Продакшн, автоматизация |
| OAuth 2.0 | Через браузер | Временный (refresh_token) | Нет | Быстрый старт, тестирование |

---

## Способ 1: Server-to-Server OAuth (ручное добавление)

Рекомендуемый способ. Токен генерируется автоматически и не истекает.

### Шаг 1: Создать приложение в Zoom Marketplace

1. Перейти на [Zoom Marketplace](https://marketplace.zoom.us/)
2. **Develop** → **Build App**
3. Выбрать тип: **Server-to-Server OAuth**
4. Указать имя приложения (например, `ZoomUploader`)

### Шаг 2: Получить credentials

На странице **App Credentials** скопировать:

| Поле | Где найти | Пример |
|------|-----------|--------|
| `account_id` | App Credentials → Account ID | `Ab1CdEf2GhIjKlMnO` |
| `client_id` | App Credentials → Client ID | `Tex0m1WATNWdFfnbBmwjSg` |
| `client_secret` | App Credentials → Client Secret | `dr8XzWRVA6Hh5FuWReynMV7Ke54UrYas` |

### Шаг 3: Настроить Scopes

На вкладке **Scopes** добавить (подробнее в разделе [Scopes](#scopes-разрешения)):

- `cloud_recording:read:list_user_recordings` — список записей
- `cloud_recording:read:recording` — детали и скачивание записей
- `user:read:user` — информация о пользователе
- `user:read:list_users` — список пользователей (для Master Account)

### Шаг 4: Активировать приложение

На вкладке **Activation** нажать **Activate your app**.

### Шаг 5: Добавить в систему

```bash
curl -X POST 'http://localhost:8000/api/v1/credentials/' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "platform": "zoom",
    "account_name": "my_zoom_account",
    "credentials": {
      "account_id": "Ab1CdEf2GhIjKlMnO",
      "client_id": "Tex0m1WATNWdFfnbBmwjSg",
      "client_secret": "dr8XzWRVA6Hh5FuWReynMV7Ke54UrYas"
    }
  }'
```

**JSON-тело запроса:**

```json
{
  "platform": "zoom",
  "account_name": "my_zoom_account",
  "credentials": {
    "account_id": "Ab1CdEf2GhIjKlMnO",
    "client_id": "Tex0m1WATNWdFfnbBmwjSg",
    "client_secret": "dr8XzWRVA6Hh5FuWReynMV7Ke54UrYas"
  }
}
```

**Поля credentials:**

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `account_id` | string | Да | Account ID из Zoom Marketplace (min 5 символов) |
| `client_id` | string | Да | Client ID приложения (min 5 символов) |
| `client_secret` | string | Да | Client Secret приложения (min 10 символов) |
| `account` | string | Нет | Произвольное имя для идентификации |
| `is_master_account` | bool | Нет | `true` если это Master Account (по умолчанию `false`) |

---

## Способ 2: OAuth 2.0 (через браузер)

Пользователь авторизуется через браузер. Подходит для быстрого подключения.

### Шаг 1: Создать OAuth-приложение в Zoom Marketplace

1. Перейти на [Zoom Marketplace](https://marketplace.zoom.us/)
2. **Develop** → **Build App**
3. Выбрать тип: **OAuth** (User-managed)
4. Указать Redirect URI: `http://localhost:8000/api/v1/oauth/zoom/callback`
5. Добавить необходимые [Scopes](#scopes-разрешения)

### Шаг 2: Настроить конфиг

Файл `config/oauth_zoom.json`:

```json
{
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "redirect_uri": "http://localhost:8000/api/v1/oauth/zoom/callback"
}
```

Или через переменные окружения (`.env`):

```
OAUTH_ZOOM_CLIENT_ID=YOUR_CLIENT_ID
OAUTH_ZOOM_CLIENT_SECRET=YOUR_CLIENT_SECRET
```

### Шаг 3: Запустить OAuth-флоу

1. Вызвать `GET /api/v1/oauth/zoom/authorize` — вернёт `authorization_url`
2. Перенаправить пользователя по этому URL
3. Пользователь авторизуется в Zoom
4. Zoom сделает callback на `/api/v1/oauth/zoom/callback`
5. Система автоматически сохранит credentials

**Credentials сохраняются автоматически** с `account_name` = email пользователя Zoom.

### Что сохраняется при OAuth:

```json
{
  "client_id": "...",
  "client_secret": "...",
  "access_token": "eyJzdiI6IjAwMDAwMSIs...",
  "refresh_token": "eyJzdiI6IjAwMDAwMSIs...",
  "token_type": "bearer",
  "scope": "cloud_recording:read:list_user_recordings cloud_recording:read:recording",
  "expires_in": 3600,
  "expiry": "2026-02-06T15:00:00Z"
}
```

### Ручное добавление OAuth-токена (без браузерного флоу)

Если OAuth-токен получен извне:

```json
{
  "platform": "zoom",
  "account_name": "user@example.com",
  "credentials": {
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "access_token": "eyJzdiI6IjAwMDAwMSIs...",
    "refresh_token": "eyJzdiI6IjAwMDAwMSIs..."
  }
}
```

**Поля OAuth credentials:**

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `access_token` | string | Да | OAuth access token (min 10 символов) |
| `refresh_token` | string | Нет | Для автообновления токена |
| `client_id` | string | Нет | Client ID приложения |
| `client_secret` | string | Нет | Client Secret приложения |
| `token_type` | string | Нет | Тип токена (обычно `bearer`) |
| `scope` | string | Нет | Предоставленные разрешения |
| `expires_in` | int | Нет | Время жизни токена в секундах |
| `expiry` | string | Нет | Время истечения в ISO формате |

> **Важно:** OAuth-токен выдаётся на конкретного пользователя. Он видит только **свои** записи. Для Master Account используйте Server-to-Server.

---

## Способ 3: Master Account (несколько под-аккаунтов)

Позволяет одним приложением собирать записи со всех под-аккаунтов организации.

### Требования

- Тип аккаунта: **Business** или **Enterprise** с sub-accounts
- Тип приложения: **Server-to-Server OAuth** (OAuth 2.0 не подходит)
- Один `client_id` / `client_secret` — работает для всех под-аккаунтов

### Два варианта конфигурации

| Вариант | Поле | Что указывать | Когда использовать |
|---------|------|---------------|-------------------|
| **A (рекомендуемый)** | `user_emails` | Email-адреса пользователей | Знаете email'ы, не хотите искать Account ID |
| **B (продвинутый)** | `account_ids` | Zoom Account ID каждого аккаунта | Нужен отдельный токен на каждый под-аккаунт |

### Шаг 1: Добавить credentials (Master Account)

```json
{
  "platform": "zoom",
  "account_name": "company_master",
  "credentials": {
    "account_id": "MASTER_ACCOUNT_ID",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "is_master_account": true
  }
}
```

> `is_master_account: true` — обязательный флаг. Без него система будет синхронизировать только записи одного аккаунта.

### Шаг 2A: Input Source с user_emails (рекомендуемый)

Просто укажите email-адреса всех пользователей, чьи записи нужно синхронизировать. Система будет использовать один токен Master Account и запрашивать записи каждого пользователя через `GET /v2/users/{email}/recordings`.

```json
{
  "name": "All Company Recordings",
  "platform": "ZOOM",
  "credential_id": 123,
  "config": {
    "is_master_account": true,
    "user_emails": [
      "admin@company.com",
      "user1@company.com",
      "user2@company.com"
    ],
    "recording_type": "cloud"
  }
}
```

> **Важно:** Если хотите записи самого Master Account — включите его email в список `user_emails`.

### Шаг 2B: Input Source с account_ids (продвинутый)

Если каждый под-аккаунт — отдельный Zoom-аккаунт со своим Account ID, можно использовать `account_ids`. Система создаст отдельный S2S-токен для каждого аккаунта.

```json
{
  "name": "All Company Recordings",
  "platform": "ZOOM",
  "credential_id": 123,
  "config": {
    "is_master_account": true,
    "account_ids": [
      "MASTER_ACCOUNT_ID",
      "SUB_ACCOUNT_1_ID",
      "SUB_ACCOUNT_2_ID"
    ],
    "recording_type": "cloud"
  }
}
```

Где взять Account IDs:
- **Zoom Admin Panel** → Account Management → Sub Accounts
- **API**: `GET https://api.zoom.us/v2/accounts`

### Поля config для Master Account

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `is_master_account` | bool | Да | `true` для Master Account |
| `user_emails` | list[str] | Одно из двух | Email-адреса пользователей (рекомендуется) |
| `account_ids` | list[str] | Одно из двух | Zoom Account IDs (продвинутый вариант) |
| `recording_type` | string | Нет | `cloud` (по умолчанию) или `all` |
| `user_id` | string | Нет | Фильтр по Zoom user ID |
| `include_trash` | bool | Нет | Включать удалённые записи (`false` по умолчанию) |

> **Нельзя** использовать `user_emails` и `account_ids` одновременно — выберите один вариант.

### Полный пример (curl)

```bash
# 1. Добавить credentials
curl -X POST 'http://localhost:8000/api/v1/credentials/' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "platform": "zoom",
    "account_name": "company_master",
    "credentials": {
      "account_id": "Ab1CdEf2GhIjKlMnO",
      "client_id": "Tex0m1WATNWdFfnbBmwjSg",
      "client_secret": "dr8XzWRVA6Hh5FuWReynMV7Ke54UrYas",
      "is_master_account": true
    }
  }'

# Ответ: { "id": 5, "platform": "zoom", ... }

# 2. Создать Input Source (вариант с user_emails)
curl -X POST 'http://localhost:8000/api/v1/sources' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "All Company Recordings",
    "platform": "ZOOM",
    "credential_id": 5,
    "config": {
      "is_master_account": true,
      "user_emails": [
        "admin@company.com",
        "user1@company.com",
        "user2@company.com"
      ],
      "recording_type": "cloud"
    }
  }'

# 3. Запустить синхронизацию
curl -X POST 'http://localhost:8000/api/v1/sources/1/sync?from_date=2025-01-01' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN'
```

---

## Scopes (разрешения)

### Server-to-Server OAuth (рекомендуемые)

Настраиваются в Zoom Marketplace → App → Scopes.

| Scope | Описание | Обязательный |
|-------|----------|-------------|
| `cloud_recording:read:list_user_recordings` | Список записей пользователя | Да |
| `cloud_recording:read:recording` | Детали записи + скачивание | Да |
| `user:read:user` | Информация о пользователе | Да |
| `user:read:list_users` | Список пользователей аккаунта | Для Master Account |

### Admin-level scopes (для Master Account)

Если нужен доступ ко всем записям всех пользователей аккаунта:

| Scope | Описание |
|-------|----------|
| `account:read:admin` | Чтение информации об аккаунте |
| `recording:read:admin` | Чтение записей всех пользователей |
| `cloud_recording:read:list_account_recordings` | Список записей всего аккаунта |

### OAuth 2.0 scopes

Запрашиваются автоматически при OAuth-флоу (настроены в `api/services/oauth_platforms.py`):

| Scope | Описание |
|-------|----------|
| `cloud_recording:read:list_user_recordings` | Список записей |
| `cloud_recording:read:recording` | Детали записей |
| `recording:write:recording` | Удаление записей |
| `user:read:user` | Информация о пользователе |

> **Granular Scopes:** Zoom перешёл на гранулярные scopes. Старые scopes вида `recording:read` / `user:read` всё ещё работают, но при создании нового приложения используйте гранулярные.

---

## Создание Input Source

После добавления credentials нужно создать Input Source, который будет использоваться для синхронизации.

### Обычный аккаунт

```json
POST /api/v1/sources
{
  "name": "My Zoom Recordings",
  "platform": "ZOOM",
  "credential_id": 1,
  "config": {
    "recording_type": "cloud"
  }
}
```

### Master Account (с user_emails)

```json
POST /api/v1/sources
{
  "name": "All Company Recordings",
  "platform": "ZOOM",
  "credential_id": 5,
  "config": {
    "is_master_account": true,
    "user_emails": ["admin@company.com", "user1@company.com", "user2@company.com"],
    "recording_type": "cloud"
  }
}
```

### Master Account (с account_ids)

```json
POST /api/v1/sources
{
  "name": "All Company Recordings",
  "platform": "ZOOM",
  "credential_id": 5,
  "config": {
    "is_master_account": true,
    "account_ids": ["MASTER_ID", "SUB_1_ID", "SUB_2_ID"],
    "recording_type": "cloud"
  }
}
```

### Все поля ZoomSourceConfig

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `user_id` | string \| null | `null` | Фильтр по Zoom user ID |
| `include_trash` | bool | `false` | Включать удалённые записи |
| `recording_type` | `cloud` \| `all` | `cloud` | Тип записей |
| `is_master_account` | bool | `false` | Режим Master Account |
| `user_emails` | list[string] \| null | `null` | Email-адреса пользователей для синхронизации (рекомендуется) |
| `account_ids` | list[string] \| null | `null` | Zoom Account IDs (продвинутый вариант) |

> `user_emails` и `account_ids` взаимоисключающие — используйте одно из двух.

---

## FAQ

### Какой способ лучше?

**Server-to-Server OAuth** — для продакшна. Токен не истекает, не требует действий пользователя, поддерживает Master Account.

**OAuth 2.0** — для быстрого тестирования или если нет доступа к Zoom Marketplace.

### user_emails или account_ids?

**`user_emails`** (рекомендуется) — просто перечислите email'ы пользователей. Система использует один токен Master Account и запрашивает записи через `GET /v2/users/{email}/recordings`.

**`account_ids`** — если нужны отдельные S2S-токены для каждого под-аккаунта. Требуется знать Zoom Account ID каждого аккаунта.

### Нужно ли создавать приложение в каждом под-аккаунте?

Нет. Одно Server-to-Server приложение в Master Account работает для всех связанных под-аккаунтов.

### Можно ли получать записи Master Account + под-аккаунтов одновременно?

Да. Включите email Master Account в список `user_emails`:

```json
{
  "is_master_account": true,
  "user_emails": ["master@company.com", "sub1@company.com", "sub2@company.com"]
}
```

### Что если один из пользователей недоступен?

Система продолжит синхронизацию остальных. Ошибка будет залогирована, но не прервёт процесс.

### Чем отличается `account` от `account_id`?

- `account` — произвольное имя для удобства идентификации (например, `"my_company"`)
- `account_id` — технический ID аккаунта из Zoom Marketplace, используется для аутентификации

### Как проверить, что credentials работают?

Создайте Input Source и запустите синхронизацию:

```bash
POST /api/v1/sources/{source_id}/sync?from_date=2025-01-01
```

В ответе будет `task_id` — отслеживайте через `GET /api/v1/tasks/{task_id}`.

### OAuth: что будет когда токен истечёт?

Access token живёт ~1 час. Если есть `refresh_token` — система может обновить токен (зависит от реализации). Для надёжной автоматизации используйте Server-to-Server OAuth.

### Валидация credentials

При добавлении credentials система проверяет:

- **Server-to-Server**: `account_id` (min 5), `client_id` (min 5), `client_secret` (min 10) — все обязательны
- **OAuth**: `access_token` (min 10) — обязателен
- **Master Account**: `is_master_account=true` → обязательно Server-to-Server (OAuth не поддерживается)
- **Дубликаты**: нельзя добавить credentials с тем же `account_id` + `client_id`
