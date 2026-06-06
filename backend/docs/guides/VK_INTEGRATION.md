# VK Integration Guide

**VK Video API integration с Implicit Flow**

**Статус:** ✅ Production Ready

---

## 📋 Содержание

1. [Overview](#overview)
2. [VK Policy Update 2026](#vk-policy-update-2026)
3. [Implicit Flow API](#implicit-flow-api)
4. [Setup Guide](#setup-guide)
5. [API Reference](#api-reference)

---

## Overview

### Что изменилось (2026)

**VK изменила политику OAuth:**
- ❌ **Новые проекты:** VK больше не одобряет новые OAuth приложения для сторонних сервисов
- ✅ **Решение:** Implicit Flow API - доступен всем без approval

### Два режима VK OAuth

| Режим | Кому | Approval | Token Lifetime | Refresh |
|-------|------|----------|----------------|---------|
| **VK ID OAuth 2.1** | Legacy apps | Требуется | Long-lived | ✅ Да |
| **Implicit Flow API** | Новые проекты | НЕ требуется | 24 hours | ❌ Нет |

**Рекомендация:** Используйте **Implicit Flow API** для новых проектов

---

## VK Policy Update 2026

### Официальное сообщение от VK Support

**Дата:** 8 января 2026

> "Здравствуйте! К сожалению, мы не можем одобрить ваше приложение для использования OAuth API, так как оно предназначено для интеграции стороннего сервиса с VK. Политика VK не допускает такие кейсы использования."

### Что это означает

**VK OAuth 2.1 (VK ID):**
- Для интеграции "Войти через VK"
- Для получения данных пользователя (email, profile)
- НЕ для загрузки контента от имени пользователя

**Implicit Flow API:**
- Для загрузки видео
- Токен получается через официальный VK сайт
- Доступно ВСЕМ без approval

### Миграция

**Если у вас legacy VK OAuth app:**
- Продолжайте использовать (не отзовут)
- Для новых пользователей → Implicit Flow

**Если вы новый проект:**
- Используйте Implicit Flow API
- См. [Setup Guide](#setup-guide)

---

## Implicit Flow API

### Как это работает

```
┌─────────────────────────────────────────┐
│     VK Implicit Flow API Flow           │
└─────────────────────────────────────────┘

1. User opens VK.com settings
    ↓
2. Generates access token (VK website)
    ↓
3. Copies token
    ↓
4. Submits to API: POST /oauth/vk/token/submit
    ↓
5. Token saved to database (encrypted)
    ↓
6. Ready to upload videos!
```

### Преимущества

- ✅ **No approval required** - работает сразу
- ✅ **Official VK method** - безопасно и легально
- ✅ **Simple** - минимум шагов
- ✅ **Multi-user** - каждый пользователь получает свой токен

### Недостатки

- ⚠️ **Token lifetime:** 24 hours (need re-authorization)
- ⚠️ **No refresh:** нужно получать новый токен вручную
- ⚠️ **Manual step:** пользователь должен скопировать токен

### Сравнение с OAuth 2.1

| Feature | Implicit Flow | VK OAuth 2.1 |
|---------|--------------|--------------|
| Approval required | ❌ Нет | ✅ Да |
| Token lifetime | 24 hours | Long-lived |
| Refresh token | ❌ Нет | ✅ Да |
| User experience | Copy-paste | OAuth redirect |
| Available for new | ✅ Да | ❌ Нет |

---

## Setup Guide

### Step 1: Get VK Token (User)

**Instructions for users:**

1. **Открыть:** https://vk.com/settings?act=tokens
2. **Нажать:** "Создать токен"
3. **Выбрать права:**
   - Video
   - Offline (для 24h lifetime)
4. **Скопировать токен** (начинается с `vk1.a.`)

### Step 2: Submit Token (API)

**Endpoint:** `POST /api/v1/oauth/vk/token/submit`

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/oauth/vk/token/submit \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "vk1.a.xxx",
    "user_id": 123456789,
    "expires_in": 86400
  }'
```

**Response:**
```json
{
  "credential_id": 5,
  "platform": "vk_video",
  "account_name": "VK Account",
  "created_at": "2026-01-14T10:00:00Z",
  "expires_at": "2026-01-15T10:00:00Z"
}
```

**Token saved:** Encrypted in `user_credentials` table

### Step 3: Verify

```bash
# Check credentials
GET /api/v1/credentials

# Response
[
  {
    "id": 5,
    "platform": "vk_video",
    "account_name": "VK Account",
    "is_active": true,
    "last_used_at": null
  }
]
```

### Step 4: Upload Video

```bash
POST /api/v1/recordings/123/upload/vk
```

**Работает автоматически!** Token берется из БД.

---

## API Reference

### Token Submission

**Endpoint:** `POST /api/v1/oauth/vk/token/submit`

**Request Body:**
```typescript
{
  access_token: string,      // Required: VK access token
  user_id?: number,          // Optional: VK user ID
  expires_in?: number        // Optional: Token lifetime (seconds)
}
```

**Response:** `CredentialResponse`

**Errors:**
- `400 Bad Request` - Invalid token format
- `401 Unauthorized` - JWT token missing/invalid
- `409 Conflict` - Token already exists

---

### Validation

**Endpoint:** `GET /api/v1/credentials/{id}/status`

**Response:**
```json
{
  "credential_id": 5,
  "platform": "vk_video",
  "is_valid": true,
  "expires_at": "2026-01-15T10:00:00Z",
  "expires_in_hours": 18,
  "needs_refresh": false
}
```

**Token считается expired:** если `expires_at < now()`

---

### Token Refresh (Implicit Flow)

**⚠️ Implicit Flow не поддерживает автоматический refresh**

**Workflow:**
1. Token expired → upload fails
2. User gets notification: "VK token expired"
3. User generates new token (см. Step 1)
4. User submits new token: `POST /oauth/vk/token/submit`

**Alternative (future):** Email reminder когда токен скоро истечет

---

## VK Video API Features

### Upload Settings

**Supported:**
- `group_id` - группа для публикации
- `album_id` - альбом
- `privacy_view` - приватность просмотра (0=all, 1=friends, 2=friends_of_friends, 3=only_me)
- `privacy_comment` - приватность комментариев
- `disable_comments` - отключить комментарии (в VK API — `no_comments`)
- `repeat` - зациклить видео
- `compression` - сжатие на стороне VK
- `wallpost` - опубликовать на стену

**Example:**
```json
{
  "group_id": -227011779,
  "album_id": 63,
  "privacy_view": 0,
  "disable_comments": false,
  "wallpost": true
}
```

### Thumbnail Upload

```python
# VK supports thumbnail upload
await vk_uploader.set_thumbnail(
    video_id=456239730,
    thumbnail_name="lecture.png"  # Filename only, API resolves to user's directory
)
```

### Album Management

```python
# Add video to album
await vk_uploader.upload_video(
    video_path="video.mp4",
    title="Lecture 1",
    album_id=63  # Album ID
)
```

---

## Troubleshooting

### Issue 1: Token Invalid

```
Error: VK API error 5: User authorization failed
```

**Причины:**
- Token expired (>24h)
- Token revoked
- Неправильные права (нет "video" scope)

**Solution:**
- Получить новый токен
- Submit через `/oauth/vk/token/submit`

---

### Issue 2: Group Access

```
Error: Access denied to group
```

**Причины:**
- User не admin группы
- Группа не существует
- Неправильный `group_id` (должен быть отрицательный)

**Solution:**
- Проверить что user - admin группы
- `group_id` должен быть `-227011779` (с минусом!)

---

### Issue 3: Album Not Found

```
Error: Album not found
```

**Solution:**
- Создать альбом в группе VK
- Скопировать album_id из URL
- Использовать положительное число (без минуса)

---

## Legacy: VK OAuth 2.1 (PKCE)

**Для legacy apps с approval:**

### Configuration

```json
{
  "client_id": "YOUR_APP_ID",
  "client_secret": "YOUR_SECRET",
  "redirect_uri": "http://localhost:8000/api/v1/oauth/vk/callback",
  "code_verifier": "GENERATED",
  "code_challenge": "SHA256(code_verifier)"
}
```

### Flow

```
1. GET /api/v1/oauth/vk/authorize
    ↓
2. Redirect to VK with PKCE
    ↓
3. User authorizes
    ↓
4. Callback: GET /api/v1/oauth/vk/callback?code=xxx
    ↓
5. Exchange code for token (with code_verifier)
    ↓
6. Save token to DB
```

### Refresh Token

```python
# Auto-refresh when expired
await vk_uploader.authenticate()  # Checks expiry, refreshes if needed
```

**⚠️ Новым проектам недоступно** - используйте Implicit Flow

---

## Best Practices

### 1. Token Expiry Notifications

```python
# Check expiry daily
async def check_vk_token_expiry(user_id: int):
    credentials = await get_vk_credentials(user_id)

    expires_at = credentials["expires_at"]
    hours_left = (expires_at - now()).total_seconds() / 3600

    if hours_left < 6:
        await send_notification(
            user_id,
            "VK token expires in 6 hours. Please renew."
        )
```

### 2. Graceful Degradation

```python
# Handle expired tokens gracefully
try:
    result = await vk_uploader.upload_video(...)
except VKTokenExpiredError:
    await notify_user("Please renew VK token")
    # Mark upload as failed
    await set_upload_failed(recording_id, "VK token expired")
```

### 3. Multiple VK Accounts

```python
# Users can have multiple VK accounts
credentials = await get_all_vk_credentials(user_id)

# Use account_name to distinguish
await create_uploader(credential_id=5)  # Account "Main Group"
await create_uploader(credential_id=6)  # Account "Secondary Group"
```

---

## См. также

- [OAUTH.md](OAUTH.md) - Полное руководство по OAuth
- [OAUTH.md](OAUTH.md) - OAuth credentials & formats
- [TEMPLATES.md](TEMPLATES.md) - VK metadata configuration

---

**Документ обновлен:** Январь 2026
**VK Policy:** Implicit Flow recommended ✅
