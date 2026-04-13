# Yandex Disk Guide

Руководство по интеграции с Яндекс Диском: загрузка видео с Диска (input) и выгрузка обработанных видео на Диск (output).

---

## Содержание

1. [Обзор возможностей](#обзор-возможностей)
2. [Получение OAuth-токена](#получение-oauth-токена)
3. [Добавление credentials](#добавление-credentials)
4. [Input Source: загрузка видео с Диска](#input-source-загрузка-видео-с-диска)
5. [Output Target: выгрузка видео на Диск](#output-target-выгрузка-видео-на-диск)
6. [Шаблоны путей](#шаблоны-путей)
7. [Архитектура](#архитектура)
8. [FAQ](#faq)

---

## Обзор возможностей

| Направление | Описание | OAuth нужен? |
|-------------|----------|-------------|
| **Input (скачивание)** — по папке | Рекурсивный обход папки, скачивание всех видео | Да |
| **Input (скачивание)** — по публичной ссылке | Скачивание видео/папки по публичной ссылке | Нет |
| **Output (загрузка)** | Загрузка обработанного видео на Диск с шаблоном пути | Да |

**Поддерживаемые форматы видео:** `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.wmv`, `.m4v`, `.ts`

---

## Получение OAuth-токена

Для работы с приватными папками (и для загрузки на Диск) нужен OAuth-токен Яндекса.

### Шаг 1: Зарегистрировать приложение

1. Перейти на [Яндекс OAuth](https://oauth.yandex.ru/client/new)
2. Заполнить:
   - **Название:** `ZoomUploader` (или любое)
   - **Платформа:** Веб-сервисы
   - **Redirect URI:** `https://oauth.yandex.ru/verification_code` (для ручного получения токена)
3. В разделе **Доступы** добавить:
   - `cloud_api:disk.app_folder` — доступ к папке приложения
   - `cloud_api:disk.read` — чтение файлов на Диске
   - `cloud_api:disk.write` — запись файлов на Диск (для загрузки)
   - `cloud_api:disk.info` — информация о Диске
4. Сохранить. Запомнить **ClientID**.

### Шаг 2: Получить токен

Открыть в браузере:

```
https://oauth.yandex.ru/authorize?response_type=token&client_id=YOUR_CLIENT_ID
```

После авторизации Яндекс перенаправит на страницу с `access_token` в URL. Скопировать его.

> **Срок жизни:** По умолчанию токен бессрочный, если не указано иное в настройках приложения.

---

## Добавление credentials

```bash
curl -X POST 'http://localhost:8000/api/v1/credentials/' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "platform": "yandex_disk",
    "account_name": "my_yandex",
    "credentials": {
      "oauth_token": "y0_AgAAAABkX1234567890abcdefghijklmnop"
    }
  }'
```

**Поля credentials:**

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `oauth_token` | string | Да | Яндекс OAuth-токен (min 10 символов) |

> Токен хранится в зашифрованном виде (AES). В API-ответах он не отображается.

---

## Быстрое добавление: публичная ссылка

Самый простой способ добавить видео с Яндекс Диска — без создания InputSource и без OAuth:

```bash
curl -X POST 'http://localhost:8000/api/v1/recordings/add-yadisk' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "public_url": "https://disk.yandex.ru/d/AbCdEf123",
    "auto_run": true
  }'
```

**Ответ:**

```json
{
  "success": true,
  "total_videos": 3,
  "recordings_created": 3,
  "recordings_updated": 0,
  "recordings": [
    {"recording_id": 50, "display_name": "lecture_01.mp4", "is_new": true},
    {"recording_id": 51, "display_name": "lecture_02.mp4", "is_new": true},
    {"recording_id": 52, "display_name": "lecture_03.mp4", "is_new": true}
  ],
  "task_ids": ["task-1", "task-2", "task-3"],
  "message": "Yandex Disk: 3 new, 0 updated, 3 pipelines started"
}
```

### Поля AddYandexDiskUrlRequest

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `public_url` | string | *обязательное* | Публичная ссылка на файл/папку |
| `file_pattern` | string \| null | `null` | Regex-паттерн фильтрации по имени |
| `template_id` | int \| null | `null` | Привязать записи к шаблону |
| `auto_run` | bool | `false` | Запустить pipeline для всех новых записей |

> Один API-вызов = все видео с публичной ссылки добавлены и (опционально) обрабатываются.

---

## Input Source: загрузка видео с Диска (расширенный способ)

Для регулярной синхронизации или приватных папок используйте InputSource.

Яндекс Диск как источник видео поддерживает два режима:

| Режим | Описание | OAuth нужен? | Поле config |
|-------|----------|-------------|-------------|
| **Папка** | Обход папки на Диске | Да | `folder_path` |
| **Публичная ссылка** | Скачивание по публичной ссылке | Нет | `public_url` |

### Вариант A: Папка на Диске (OAuth)

Рекурсивно сканирует папку, находит все видео-файлы, создаёт Recording для каждого.

```bash
curl -X POST 'http://localhost:8000/api/v1/sources' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Лекции с Диска",
    "platform": "YANDEX_DISK",
    "credential_id": 3,
    "config": {
      "folder_path": "/Video/Lectures",
      "recursive": true,
      "file_pattern": ".*\\.mp4$"
    }
  }'
```

### Вариант B: Публичная ссылка (без OAuth)

Не требует credentials. Работает с публичными ссылками вида `https://disk.yandex.ru/d/...` или `https://yadi.sk/d/...`.

```bash
curl -X POST 'http://localhost:8000/api/v1/sources' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Публичная папка",
    "platform": "YANDEX_DISK",
    "config": {
      "public_url": "https://disk.yandex.ru/d/AbCdEf123"
    }
  }'
```

> **Важно:** `credential_id` не нужен для публичных ссылок.

### Поля YandexDiskSourceConfig

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `folder_path` | string \| null | `null` | Путь к папке на Диске (требует OAuth) |
| `public_url` | string \| null | `null` | Публичная ссылка на файл/папку |
| `recursive` | bool | `true` | Рекурсивный обход подпапок |
| `file_pattern` | string \| null | `null` | Regex-паттерн фильтрации по имени файла |

> `folder_path` и `public_url` взаимоисключающие — используйте одно из двух.

### Синхронизация

```bash
# Запустить синхронизацию
curl -X POST 'http://localhost:8000/api/v1/sources/{source_id}/sync' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN'

# Ответ: { "task_id": "abc-123", "status": "queued", ... }

# Проверить статус
curl 'http://localhost:8000/api/v1/tasks/abc-123' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN'
```

При синхронизации для каждого видеофайла создаётся запись `Recording` со следующими метаданными:

- `path` — путь к файлу на Диске
- `name` — имя файла
- `size` — размер в байтах
- `mime_type` — MIME-тип файла
- `download_method` — `"api"` или `"public"`

---

## Output Target: выгрузка видео на Диск

После обработки видео можно выгрузить на Яндекс Диск. Настраивается через Output Preset в шаблоне.

### Создание Output Preset

```json
{
  "platform": "yandex_disk",
  "credential_id": 3,
  "name": "Upload to Disk",
  "metadata": {
    "folder_path_template": "/Video/{display_name}/{date}",
    "filename_template": "{display_name}.mp4",
    "overwrite": false
  }
}
```

### Поля YandexDiskPresetMetadata

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `folder_path_template` | string | *обязательное* | Шаблон пути папки на Диске |
| `filename_template` | string \| null | `null` | Шаблон имени файла (по умолчанию — оригинальное имя) |
| `overwrite` | bool | `false` | Перезаписывать существующие файлы |

### Поля YandexDiskMetadataConfig (в шаблоне)

Можно переопределить путь и имя файла на уровне шаблона в `metadata_config.yandex_disk`:

| Поле | Тип | Описание |
|------|-----|----------|
| `folder_path_template` | string \| null | Переопределить шаблон пути для этого шаблона |
| `filename_template` | string \| null | Переопределить шаблон имени файла |

Приоритет: `metadata_config.yandex_disk` > `preset.metadata` > значения по умолчанию.

---

## Шаблоны путей

Шаблоны поддерживают переменные, которые подставляются автоматически:

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `{display_name}` | Название записи | `Лекция 1` |
| `{date}` | Дата записи (YYYY-MM-DD) | `2026-02-11` |
| `{record_time}` | Время записи (с форматированием) | `2026-02-11T10:00:00` |
| `{record_time:DD.MM.YYYY}` | Время с кастомным форматом | `11.02.2026` |
| `{themes}` | Темы (через запятую) | `ML, Python` |
| `{duration}` | Длительность | `01:30:00` |

### Примеры шаблонов

```
/Video/Processed                              → /Video/Processed
/Video/{display_name}                         → /Video/Лекция 1
/Video/{display_name}/{date}                  → /Video/Лекция 1/2026-02-11
/Lectures/{record_time:YYYY-MM-DD}/{display_name}.mp4 → /Lectures/2026-02-11/Лекция 1.mp4
```

### Полный пример шаблона с Yandex Disk output

```json
{
  "name": "ML Course Template",
  "matching_rules": {
    "keywords": ["ML", "Machine Learning"]
  },
  "metadata_config": {
    "yandex_disk": {
      "folder_path_template": "/Courses/ML/{record_time:YYYY-MM-DD}"
    }
  },
  "output_presets": [
    {
      "platform": "yandex_disk",
      "credential_id": 3,
      "name": "Disk Upload",
      "metadata": {
        "folder_path_template": "/Video/Default",
        "filename_template": "{display_name}.mp4",
        "overwrite": false
      }
    }
  ]
}
```

> В этом примере `metadata_config.yandex_disk.folder_path_template` переопределит `preset.metadata.folder_path_template`. Итоговый путь: `/Courses/ML/2026-02-11/Лекция 1.mp4`.

---

## Архитектура

### Модули

```
yandex_disk_module/
├── __init__.py
└── client.py                  # REST API клиент (list, download, upload)

video_download_module/
└── platforms/
    └── yadisk/
        ├── __init__.py
        └── downloader.py      # YandexDiskDownloader (BaseDownloader)

video_upload_module/
└── platforms/
    └── yadisk/
        ├── __init__.py
        └── uploader.py        # YandexDiskUploader (BaseUploader)
```

### Yandex Disk REST API

Используемые эндпоинты ([документация](https://yandex.ru/dev/disk/rest)):

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/v1/disk/resources?path=` | Листинг папки |
| `GET` | `/v1/disk/resources/download?path=` | Получить URL для скачивания |
| `GET` | `/v1/disk/public/resources?public_key=` | Метаинформация публичного ресурса |
| `GET` | `/v1/disk/public/resources/download?public_key=` | URL для скачивания публичного файла |
| `GET` | `/v1/disk/resources/upload?path=` | Получить URL для загрузки |
| `PUT` | `/v1/disk/resources?path=` | Создать папку |
| `GET` | `/v1/disk` | Информация о Диске (для проверки токена) |

### Процесс скачивания

1. **Sync** (`_sync_yandex_disk_source`) — сканирует папку / публичную ссылку, создаёт `Recording` для каждого видео
2. **Download** (`YandexDiskDownloader.download`) — получает временный URL через API, скачивает потоково с поддержкой resume
3. **Processing** — стандартный пайплайн (транскрибация, topic extraction и т.д.)

### Процесс загрузки

1. **Upload task** — резолвит `folder_path_template` через `TemplateRenderer`
2. `YandexDiskUploader.upload_video` → `YandexDiskClient.upload_file`
3. Клиент автоматически создаёт все промежуточные папки (`_ensure_folder_exists`)
4. Загружает файл двухшаговым процессом: получить upload URL → PUT файл

---

## FAQ

### Какие права нужны OAuth-токену?

Для скачивания: `cloud_api:disk.read`, `cloud_api:disk.info`.
Для загрузки: дополнительно `cloud_api:disk.write`.
Для полного доступа: `cloud_api:disk.app_folder`.

### Нужен ли OAuth для публичных ссылок?

Нет. Публичные ссылки (`https://disk.yandex.ru/d/...`) работают без авторизации. Используйте `public_url` вместо `folder_path`.

### Какие файлы считаются видео?

Файлы определяются по MIME-типу (`video/*`) или расширению: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.wmv`, `.m4v`, `.ts`.

### Можно ли фильтровать файлы по имени?

Да. Используйте `file_pattern` — это regex-паттерн:

```json
{
  "folder_path": "/Video",
  "file_pattern": "Лекция.*\\.mp4$"
}
```

### Что если папка содержит подпапки?

По умолчанию `recursive: true` — система обходит все подпапки. Для сканирования только верхнего уровня установите `recursive: false`.

### Как проверить, что токен работает?

Создайте Input Source с `folder_path: "/"` и запустите синхронизацию. Если токен валиден — вернётся список файлов.

### Что если загрузка прервалась?

Скачивание поддерживает resume (возобновление с места остановки). При загрузке на Диск — файл загружается целиком через один PUT-запрос.

### Можно ли перезаписывать файлы при загрузке?

Да. Установите `overwrite: true` в `preset.metadata`. По умолчанию `false` — если файл существует, будет ошибка.

### Безопасность OAuth-токена

OAuth-токен хранится в зашифрованном виде (`encrypted_data`) в базе данных. Он **не** сохраняется в метаданных записей (`source_metadata`) и не виден в API-ответах. При скачивании токен извлекается из зашифрованных credentials в момент выполнения задачи.
