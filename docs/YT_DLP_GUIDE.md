# yt-dlp Video Sources Guide

Руководство по загрузке видео из внешних источников через yt-dlp: YouTube, VK Video, Rutube и 1000+ других платформ.

---

## Содержание

1. [Обзор возможностей](#обзор-возможностей)
2. [Поддерживаемые платформы](#поддерживаемые-платформы)
3. [Input Source: видео по ссылке](#input-source-видео-по-ссылке)
4. [Плейлисты и каналы](#плейлисты-и-каналы)
5. [Настройки качества](#настройки-качества)
6. [Архитектура](#архитектура)
7. [FAQ](#faq)

---

## Обзор возможностей

| Функция | Описание |
|---------|----------|
| Загрузка одного видео | Ввести URL → синхронизировать → скачать → обработать |
| Загрузка плейлиста | Ввести URL плейлиста → получить все видео → скачать каждое |
| Автоопределение платформы | По URL определяется YouTube / VK / Rutube / другие |
| Выбор качества | `best`, `1080p`, `720p`, `480p` |
| Формат контейнера | `mp4` (рекомендуется) или `any` |
| Data transfer | Загрузить с одной платформы → обработать → выгрузить на другую |

**Credentials не требуются.** Все публичные видео скачиваются без авторизации.

---

## Поддерживаемые платформы

### Автоматически определяемые

| Платформа | Паттерн URL | `video_platform` |
|-----------|------------|------------------|
| YouTube | `youtube.com`, `youtu.be` | `youtube` |
| VK Video | `vk.com`, `vkvideo.ru` | `vk` |
| Rutube | `rutube.ru` | `rutube` |

### Другие платформы (через yt-dlp)

yt-dlp поддерживает 1000+ сайтов. Любой URL, поддерживаемый yt-dlp, будет работать с `video_platform: "other"` (или автоопределением).

Примеры: Dailymotion, Vimeo, Twitch, Mail.ru, Одноклассники и др.

> Полный список: [yt-dlp Supported Sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

---

## Быстрое добавление: видео по ссылке

Самый простой способ — прямые эндпоинты, без создания InputSource.

### Добавить одно видео

```bash
curl -X POST 'http://localhost:8000/api/v1/recordings/add-url' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "quality": "1080p",
    "auto_run": true
  }'
```

**Ответ:**

```json
{
  "success": true,
  "recording_id": 42,
  "display_name": "Video Title",
  "platform": "youtube",
  "task_id": "abc-123",
  "message": "Video added from youtube — pipeline started"
}
```

### Поля AddVideoByUrlRequest

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `url` | string | *обязательное* | URL видео |
| `display_name` | string \| null | `null` (авто) | Кастомное имя (иначе извлекается из видео) |
| `quality` | string | `"best"` | Качество: `best`, `1080p`, `720p`, `480p` |
| `format_preference` | string | `"mp4"` | Формат: `mp4` или `any` |
| `template_id` | int \| null | `null` | Привязать к шаблону |
| `auto_run` | bool | `false` | Сразу запустить pipeline (download → process → upload) |

> Credentials **не нужны**. Один вызов API = видео добавлено и (опционально) запущено в обработку.

---

## Input Source: видео по ссылке (альтернативный способ)

Для регулярной синхронизации (например, плейлиста) можно также создать InputSource:

### Создание Input Source

```bash
curl -X POST 'http://localhost:8000/api/v1/sources' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "YouTube Lecture",
    "platform": "VIDEO_URL",
    "config": {
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "quality": "1080p",
      "format_preference": "mp4"
    }
  }'
```

### Поля VideoUrlSourceConfig

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `url` | string | *обязательное* | URL видео или плейлиста |
| `video_platform` | string \| null | `null` (авто) | Платформа: `youtube`, `vk`, `rutube`, `other` |
| `is_playlist` | bool | `false` | Обрабатывать как плейлист |
| `quality` | string | `"best"` | Качество: `best`, `1080p`, `720p`, `480p` |
| `format_preference` | string | `"mp4"` | Формат: `mp4` или `any` |

### Синхронизация

При синхронизации yt-dlp извлекает метаданные видео **без скачивания**:

```bash
# Запустить синхронизацию
curl -X POST 'http://localhost:8000/api/v1/sources/{source_id}/sync' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN'
```

Для каждого видео создаётся `Recording` с метаданными:

| Поле | Описание |
|------|----------|
| `url` | URL видео |
| `platform` | Определённая платформа |
| `video_id` | ID видео на платформе |
| `title` | Название видео |
| `duration` | Длительность (секунды) |
| `thumbnail` | URL превью |
| `uploader` | Автор/канал |

### Пример с VK Video

```json
{
  "name": "VK Lecture Series",
  "platform": "VIDEO_URL",
  "config": {
    "url": "https://vk.com/video-123456_789012",
    "video_platform": "vk",
    "quality": "720p"
  }
}
```

### Пример с Rutube

```json
{
  "name": "Rutube Recording",
  "platform": "VIDEO_URL",
  "config": {
    "url": "https://rutube.ru/video/abc123def456/",
    "quality": "best"
  }
}
```

---

## Плейлисты и каналы

### Быстрое добавление плейлиста (рекомендуется)

```bash
curl -X POST 'http://localhost:8000/api/v1/recordings/add-playlist' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxx",
    "quality": "1080p",
    "auto_run": false
  }'
```

**Ответ:**

```json
{
  "success": true,
  "total_videos": 15,
  "recordings_created": 15,
  "recordings_updated": 0,
  "recordings": [
    {"recording_id": 42, "display_name": "Лекция 1", "is_new": true},
    {"recording_id": 43, "display_name": "Лекция 2", "is_new": true}
  ],
  "task_ids": [],
  "message": "Playlist processed: 15 new, 0 updated"
}
```

### Поля AddPlaylistByUrlRequest

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `url` | string | *обязательное* | URL плейлиста или канала |
| `quality` | string | `"best"` | Качество для всех видео |
| `format_preference` | string | `"mp4"` | Формат контейнера |
| `template_id` | int \| null | `null` | Привязать все записи к шаблону |
| `auto_run` | bool | `false` | Запустить pipeline для всех новых записей |

### Примеры URL для плейлистов

| Платформа | Пример URL |
|-----------|-----------|
| YouTube плейлист | `https://www.youtube.com/playlist?list=PLxxxxxxxx` |
| YouTube канал | `https://www.youtube.com/@channel_name/videos` |
| VK альбом | `https://vk.com/videos-123456?section=album_789` |

### Через InputSource (для регулярной синхронизации)

Если нужно регулярно проверять плейлист на новые видео:

```json
{
  "name": "ML Course Playlist",
  "platform": "VIDEO_URL",
  "config": {
    "url": "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxx",
    "is_playlist": true,
    "quality": "1080p",
    "format_preference": "mp4"
  }
}
```

### Как работает синхронизация плейлистов

1. yt-dlp извлекает список видео из плейлиста (`extract_flat=True` — без скачивания)
2. Для каждого видео создаётся отдельный `Recording`
3. `source_key` формируется как `{platform}:{video_id}` — дубликаты не создаются при повторной синхронизации
4. При повторной синхронизации новые видео (добавленные в плейлист) будут обнаружены

---

## Настройки качества

### Параметр `quality`

| Значение | Описание | yt-dlp формат |
|----------|----------|---------------|
| `best` | Лучшее доступное | `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best` |
| `1080p` | До 1080p | `bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/...` |
| `720p` | До 720p | `bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/...` |
| `480p` | До 480p | `bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/...` |

### Параметр `format_preference`

| Значение | Описание |
|----------|----------|
| `mp4` | Предпочитать MP4 контейнер (рекомендуется для совместимости) |
| `any` | Любой доступный формат (`best`) |

> При `format_preference: "mp4"` yt-dlp использует `merge_output_format: "mp4"` для мёрджа видео- и аудиодорожек.

---

## Архитектура

### Модули

```
video_download_module/
└── platforms/
    └── ytdlp/
        ├── __init__.py
        ├── downloader.py      # YtDlpDownloader (BaseDownloader)
        └── metadata.py        # Извлечение метаданных, определение платформы
```

### Процесс

```
URL → sync (extract metadata) → Recording → download (yt-dlp) → Processing → Upload
```

1. **Синхронизация** (`_sync_video_url_source`)
   - `detect_platform(url)` — определяет платформу по URL
   - `extract_video_info(url)` — извлекает метаданные одного видео
   - `extract_playlist_entries(url)` — извлекает список видео из плейлиста
   - Создаёт `Recording` для каждого видео

2. **Скачивание** (`YtDlpDownloader.download`)
   - Получает URL из `source_meta`
   - Формирует yt-dlp опции (формат, качество)
   - Скачивает в `storage/users/user_XXXXXX/recordings/{id}/source.mp4`
   - Возвращает `DownloadResult` с метаданными

3. **Обработка** — стандартный пайплайн (transcription, topic extraction и т.д.)

### Ключевые функции

| Функция | Файл | Описание |
|---------|------|----------|
| `detect_platform(url)` | `metadata.py` | Определение платформы по regex |
| `extract_video_info(url)` | `metadata.py` | Метаданные видео без скачивания |
| `extract_playlist_entries(url)` | `metadata.py` | Список видео из плейлиста (flat) |
| `YtDlpDownloader.download()` | `downloader.py` | Скачивание через yt-dlp |
| `_build_format_spec()` | `downloader.py` | Формирование строки формата |

---

## Data Transfer (перенос видео между платформами)

Одна из ключевых возможностей — перенос видео между платформами:

### YouTube → VK

```json
{
  "name": "YouTube Source",
  "platform": "VIDEO_URL",
  "config": {
    "url": "https://www.youtube.com/playlist?list=PLxxx",
    "is_playlist": true,
    "quality": "1080p"
  }
}
```

Шаблон с VK output preset:

```json
{
  "name": "YouTube to VK",
  "matching_rules": { "source_ids": [1] },
  "output_presets": [
    {
      "platform": "vk_video",
      "credential_id": 5,
      "metadata": {
        "title_template": "{display_name}",
        "description_template": "{summary}"
      }
    }
  ]
}
```

### VK → YouTube

Аналогично: VIDEO_URL с VK-ссылкой → шаблон с YouTube output preset.

### Любая платформа → Yandex Disk

```json
{
  "output_presets": [
    {
      "platform": "yandex_disk",
      "credential_id": 3,
      "metadata": {
        "folder_path_template": "/Backup/{display_name}",
        "overwrite": false
      }
    }
  ]
}
```

---

## FAQ

### Нужны ли credentials для VIDEO_URL?

Нет. Все публичные видео скачиваются без авторизации. Платформа VIDEO_URL не требует `credential_id`.

### Можно ли скачивать приватные видео?

Нет. yt-dlp работает только с публично доступными видео (без авторизации на платформе-источнике).

### Как определяется платформа?

Автоматически по URL:
- `youtube.com`, `youtu.be` → `youtube`
- `vk.com`, `vkvideo.ru` → `vk`
- `rutube.ru` → `rutube`
- Всё остальное → `other`

Можно указать явно через `video_platform`.

### Что если yt-dlp не может скачать видео?

Возможные причины:
- Видео приватное или удалено
- Платформа не поддерживается yt-dlp
- Geo-ограничения
- Проверьте URL вручную: `yt-dlp --simulate URL`

### Что если видео в плейлисте недоступно?

Система пропускает недоступные видео и продолжает обработку остальных. Ошибка логируется.

### Какой формат видео рекомендуется?

`format_preference: "mp4"` с `quality: "best"` — оптимальный баланс качества и совместимости. MP4 поддерживается всеми выходными платформами.

### Можно ли повторно синхронизировать плейлист?

Да. `source_key` формируется как `{platform}:{video_id}`. При повторной синхронизации существующие записи обновляются, новые — создаются. Дубликаты не возникают.

### Можно ли указать несколько URL в одном источнике?

Нет. Один Input Source = один URL. Для нескольких видео используйте плейлист или создайте отдельные источники.

### Где хранятся скачанные видео?

В директории `storage/users/user_XXXXXX/recordings/{recording_id}/source.mp4`. Структура идентична Zoom-записям.

### Как обновить yt-dlp?

```bash
uv pip install --upgrade yt-dlp
# или
pip install --upgrade yt-dlp
```

> Рекомендуется регулярно обновлять yt-dlp — платформы часто меняют API, и новые версии содержат исправления.

### Поддерживает ли система ограничение скорости скачивания?

На данный момент нет. yt-dlp скачивает на максимальной доступной скорости. Rate limiting можно добавить в будущем через `ratelimit` опцию yt-dlp.
