# Polite API & Jitter — План Rate Limiting для внешних платформ

**Актуализация:** 27 февраля 2026  
**Предыдущее обсуждение:** транскрипт чата 7bd73c82 (VK rate limit, 29 jan 2026)  
**Статус:** В планах, не реализовано

---

## 📋 Контекст

При массовой загрузке видео на VK API возникает ошибка **error_code 6** ("Too many requests per second") — аналог HTTP 429. Логи (jan 2026) показывают:

- 7 задач загрузки стартуют одновременно
- VK отклоняет несколько запросов `video.save` (rate limit ~3 req/s)
- Retry через 10 минут — все 4 failed задачи снова стартуют одновременно
- Цикл повторяется (recording 74 падает повторно)

**Логи:** `logs/app.log` (в .gitignore, но выдержки из транскрипта чата подтверждают паттерн).

---

## ✅ Текущее состояние проекта (v0.9.6.3, Mar 2026)

### Что уже есть

| Компонент | Реализация |
|-----------|------------|
| **Rate limiting API** | `RateLimitMiddleware` — 60 req/min, 1000 req/hr на входящие HTTP-запросы |
| **Queues Celery** | Очередь `uploads` — все upload задачи (VK, YouTube, Yandex) в одну очередь |
| **Retry upload** | `upload_max_retries=5`, `upload_retry_delay=600` (фиксированные 10 мин) |
| **Конфиг** | Все настройки через `.env` + `config/settings.py` |
| **Платформы** | VK, YouTube, Яндекс Диск (Yandex Disk добавлен v0.9.5) |

### Чего нет (из исходного плана)

| Уровень | Состояние |
|---------|-----------|
| **Redis rate limiter** для внешних API | ❌ Не реализован |
| **Platform-specific очереди** | ❌ Всё в `uploads` |
| **Exponential backoff + jitter** | ❌ Фиксированный countdown |
| **Специальная обработка rate limit (429 / error_code 6)** | ❌ Все ошибки обрабатываются одинаково |
| **Circuit Breaker** | ❌ Отложен |

### VK uploader

- `_make_request()` возвращает `None` при любой ошибке API (в т.ч. error_code 6)
- В вызывающем коде ошибка превращается в `Exception("Upload failed: Unknown error")`
- Celery retry не различает rate limit от других ошибок

---

## 🎯 План реализации (3 уровня)

### Level 1: Redis Rate Limiter для внешних API

- Distributed rate limiter (token bucket или sliding window)
- Лимиты per-platform, настраиваемые через `.env`:
  - `PLATFORM_VK_REQUESTS_PER_SECOND=3`
  - `PLATFORM_YOUTUBE_REQUESTS_PER_SECOND=10`
  - `PLATFORM_YANDEX_DISK_REQUESTS_PER_SECOND=5` (уточнить)
- Перед запросом к API — `acquire()` блокирует до получения токена
- Использовать Redis (уже настроен для Celery)

### Level 2: Platform-specific очереди Celery

- Отдельные очереди: `vk_upload`, `youtube_upload`, `yandex_disk_upload`
- Celery rate limit на уровне очереди: `rate_limit='3/s'` для VK
- Task routing по platform в `api/celery_app.py`
- Concurrency для VK-очереди — ниже (напр. 2 worker'а)

### Level 3: Smart Retry с exponential backoff + jitter

- **Exponential backoff:** 10s → 30s → 90s → 270s (как обсуждалось)
- **Jitter:** `delay = base_delay + random.uniform(0, 0.3 * base_delay)` — размазывает retry во времени
- **Специальная обработка rate limit:**
  - VK error_code 6, HTTP 429 → retry с короткой задержкой (10–30s) вместо 600s
  - Пробросить специальный exception `RateLimitError` из uploader в task

### Level 4 (опционально): Circuit Breaker

- При массовых rate limit — кратковременная блокировка запросов к платформе
- Состояния: CLOSED → OPEN → HALF_OPEN
- Архитектуру заложить, реализацию отложить

---

## 🔧 Детали реализации

### 1. Распознавание rate limit в VK uploader

```python
# video_upload_module/platforms/vk/uploader.py
VK_RATE_LIMIT_ERROR_CODE = 6

class VKRateLimitError(Exception):
    """VK API error_code 6: Too many requests per second"""

# В _make_request: при error_code == 6 — raise VKRateLimitError
```

### 2. Новые настройки в config/settings.py

```python
class PlatformRateLimitSettings(BaseSettings):
    env_prefix = "PLATFORM_"
    vk_requests_per_second: float = 3.0
    youtube_requests_per_second: float = 10.0
    yandex_disk_requests_per_second: float = 5.0
```

### 3. Celery retry с exponential backoff + jitter

```python
def get_retry_countdown(retries: int, is_rate_limit: bool) -> int:
    if is_rate_limit:
        base = [10, 30, 90, 270, 600][min(retries, 4)]
    else:
        base = [60, 180, 600, 600, 600][min(retries, 4)]
    jitter = random.uniform(0, 0.3 * base)
    return int(base + jitter)
```

### 4. Структура кода

```
api/
  services/
    platform_rate_limiter.py   # Redis-based, token bucket
  tasks/
    upload.py                 # Обработка RateLimitError, countdown
video_upload_module/platforms/vk/
  uploader.py                 # Raise VKRateLimitError при error_code 6
config/
  settings.py                 # PlatformRateLimitSettings
```

---

## 📊 Масштабирование (10–100 пользователей)

- **Redis rate limiter** — ключ по платформе (не по пользователю), т.к. лимиты VK/YouTube глобальные на приложение
- **Platform-specific очереди** — изоляция нагрузки; при 20+ пользователях важно не бомбить VK одновременно
- **Jitter** — предотвращает синхронный retry всех failed задач
- **Circuit Breaker** — защита при сбоях/перегрузке платформы

---

## 📅 Приоритеты

1. **Quick win:** Level 3 (smart retry + jitter) — можно внедрить без Redis, только в `upload.py` и VK uploader
2. **Level 2:** Platform-specific queues — изменение routing в Celery
3. **Level 1:** Redis rate limiter — полноценное решение для production

---

## Zoom API (Recordings / Downloads)

**Источник:** [Zoom API Rate Limits](https://developers.zoom.us/docs/api/rate-limits/)

| План | Лимит |
|------|-------|
| Free | 4 req/s |
| Enterprise | до 80 req/s |

Cloud Recordings (Tier 2). При 20 параллельных downloads — ~20 активных операций, укладываемся в Enterprise. Для Free-аккаунта рекомендуется `--concurrency=6` в celery-downloads.

---

## 📚 Связанные документы

- [PLAN.md](../PLAN.md) — Rate Limiting API провайдеров (раздел «Проблемы»)
- [ROADMAP.md](../ROADMAP.md) — техническая дорожная карта
- [transcription_retry_INFO.md](transcription_retry_INFO.md) — аналогия: retry для транскрибации
- Транскрипт [7bd73c82] (agent-transcripts) — исходное обсуждение VK rate limit
