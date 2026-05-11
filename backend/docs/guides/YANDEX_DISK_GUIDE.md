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

**Видео для записей (пикер, скачивание, локальная загрузка):** канонический список — кортеж **`STORAGE_DEFAULT_VIDEO_FORMATS`** в `config/settings.py` (это же подставляется в `StorageSettings.supported_video_formats` через `default_factory`); `STORAGE_SUPPORTED_VIDEO_FORMATS` **игнорируется**.

---

## Получение OAuth-токена

Для работы с приватными папками (и для загрузки на Диск) нужен OAuth-токен Яндекса.

### Рекомендуемый способ: OAuth через API LEAP

1. Скопируйте [`backend/config/oauth_yandex_disk.json.example`](../../config/oauth_yandex_disk.json.example) в `backend/config/oauth_yandex_disk.json` и укажите `client_id` / `client_secret` (путь можно переопределить через `YANDEX_DISK_OAUTH_CONFIG` в `.env`, см. `backend/.env.example`).
2. В настройках приложения на [Яндекс OAuth](https://oauth.yandex.ru/) укажите **Redirect URI**: `{OAUTH_REDIRECT_BASE_URL}/api/v1/oauth/yandex_disk/callback` (как правило `http://localhost:8000/api/v1/oauth/yandex_disk/callback` для локальной разработки).
3. Авторизованный пользователь вызывает `GET /api/v1/oauth/yandex_disk/authorize`, переходит по `authorization_url`, после callback токен и refresh сохраняются в `user_credentials` (платформа `yandex_disk`).

### Шаг 1: Зарегистрировать приложение (ручной токен — legacy)

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

## Публичная ссылка без OAuth

Публичные папки/файлы добавляются через **Input Source** с `public_url` (credential не нужен). Создайте источник и вызовите sync — см. раздел ниже.

> Ранее использовался `POST /api/v1/recordings/add-yadisk`; эндпоинт удалён в пользу единого потока InputSource + sync.

---

## Input Source: загрузка видео с Диска

Для публичных ссылок, регулярной синхронизации или приватных папок используйте InputSource.

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

**Идентичность записи при переименовании на Диске (OAuth / папка):** при синхронизации листинг запрашивает у API поля вроде `md5` и `resource_id` (см. [REST API Диска](https://yandex.com/dev/disk/rest/)). Ключ записи строится в порядке: `resource_id` → `md5`+`size` → путь. Пока API отдаёт хэш или id, одна и та же лекция после переименования остаётся **той же** `Recording`, метаданные пути обновляются. Если хэш/id нет (ограничение ответа API), используется только путь — тогда переименование даёт новую запись.

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

Для источника **YANDEX_DISK** с привязанным OAuth-credential перед листингом API при необходимости **обновляет access token** (если до `expiry` осталось меньше ~5 минут и в зашифрованных credentials есть `refresh_token` и `client_id`). Публичные ссылки без credential этим не затрагиваются.

**Идентичность файла при переименовании (OAuth / папка):** при листинге запрашиваются поля `md5` и `resource_id` у элементов. Запись в БД привязывается к ключу вида `yadisk:rid:…` или `yadisk:md5:…:size`, а не только к пути; при sync ищется также старый path-ключ, затем ключ нормализуется. Так одна и та же лекция после переименования на Диске не создаётся вторым `Recording`. Если API не вернул ни `resource_id`, ни `md5`, используется только путь (как раньше) — переименование тогда даёт новую запись. Для публичных каталогов по ссылке стабильный hash в ответе не гарантирован.

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

Тело запроса — `POST /api/v1/output-presets`. Поле с настройками платформы называется **`preset_metadata`** (не `metadata`).

```json
{
  "platform": "yandex_disk",
  "credential_id": 3,
  "name": "Upload to Disk",
  "preset_metadata": {
    "folder_path_template": "/Video/{{ display_name }}/{{ record_date_iso }}",
    "filename_template": "{{ display_name }}.mp4",
    "overwrite": false,
    "publish": false
  }
}
```

Шаблоны путей и имён — **Jinja2** (`{{ variable }}`), тот же контекст, что и для YouTube/VK (см. `TemplateRenderer.prepare_recording_context`).

### Поля YandexDiskPresetMetadata

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `folder_path_template` | string | *обязательное* | Jinja: папка на Диске |
| `filename_template` | string \| null | `null` | Jinja: имя файла (иначе — как у обработанного видео) |
| `title_template` | string \| null | `null` | Jinja: заголовок загрузки |
| `description_template` | string \| null | `null` | Jinja: описание (в т.ч. для `description_txt`, см. ниже) |
| `overwrite` | bool | `false` | Перезаписывать существующие файлы |
| `publish` | bool | `false` | После загрузки опубликовать файл и сохранить публичную ссылку в результате |
| `subtitles_srt` | object \| null | `null` | Задан объект (в т.ч. `{}`) → после успешной загрузки видео best-effort выгрузить `.srt` |
| `subtitles_vtt` | object \| null | `null` | То же для `.vtt` |
| `transcription` | object \| null | `null` | То же для текстовой транскрипции (segments) |
| `description_txt` | object \| null | `null` | То же для `.txt` с описанием |

Для sidecar-файлов (`subtitles_*`, `transcription`, `description_txt`) вложенный объект может задавать `filename_template`, `folder_path_template` (Jinja); у `description_txt` дополнительно `content_template` (Jinja тела файла; если не задан — подставляется уже отрендеренное `description_template` / описание задачи).

### Поля YandexDiskMetadataConfig (в шаблоне)

Переопределения на уровне recording template: `metadata_config.yandex_disk`:

| Поле | Тип | Описание |
|------|-----|----------|
| `folder_path_template` | string \| null | Переопределить шаблон пути |
| `filename_template` | string \| null | Переопределить шаблон имени файла |
| `overwrite` | bool \| null | Переопределить `overwrite` пресета (если не `null`) |
| `publish` | bool \| null | Переопределить `publish` пресета (если не `null`) |

Приоритет: `recording.processing_preferences.metadata_config` → `template.metadata_config` (в т.ч. блок `yandex_disk`) → `preset.preset_metadata`. В коде загрузки сначала читается вложенный блок `preset_metadata.yandex_disk`, затем поля верхнего уровня merged-метаданных.

---

## Шаблоны путей

Используется **Jinja2**. Примеры переменных контекста: `display_name`, `record_date_iso`, `record_datetime`, `themes`, `topics`, `summary`, `duration`, … (полный набор — в коде `TemplateRenderer`).

Дополнительные **фильтры** для путей (Jinja):

- **`split_path`** — заменяет разделитель на `/` (по умолчанию разделитель сегментов — `_`). Пример: при `display_name` = `A_B_C` выражение с фильтром даёт `A/B/C`.
- **`part`** — `part(index, sep)` возвращает сегмент после `split(sep)` или пустую строку. Удобно для имён вида `Курс — Лекция 1`.

### Примеры шаблонов

```
/Video/Processed
/Video/{{ display_name }}
/Video/{{ display_name }}/{{ record_date_iso }}
/Courses/{{ record_date_iso }}/{{ display_name | split_path('_') }}
```

### Связка template + preset (как в API)

Шаблон записи ссылается на уже созданные пресеты через `output_config.preset_ids`, а не встраивает JSON пресета:

1. `POST /api/v1/output-presets` — создать пресет с `platform: "yandex_disk"` и нужным `preset_metadata`.
2. `POST /api/v1/templates` — в `output_config` указать `"preset_ids": [<id пресета>]`, при необходимости в `metadata_config.yandex_disk` задать переопределения пути/имени/`overwrite`/`publish`.

```json
{
  "name": "ML Course Template",
  "matching_rules": {
    "keywords": ["ML", "Machine Learning"]
  },
  "metadata_config": {
    "yandex_disk": {
      "folder_path_template": "/Courses/ML/{{ record_date_iso }}"
    }
  },
  "output_config": {
    "preset_ids": [42]
  }
}
```

Здесь `42` — id пресета «Disk Upload» с базовым `folder_path_template` в `preset_metadata`; блок шаблона уточняет/переопределяет папку для Яндекс Диска.

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
2. **Download** (`YandexDiskDownloader.download`) — для **`folder_path` (OAuth)** по шагам как в [официальной инструкции «Скачивание файла с Диска»](https://yandex.ru/dev/disk-api/doc/ru/reference/content): `GET /v1/disk/resources/download`, затем **GET по `href`** с тем же OAuth на «дисковых» хостах; после редиректа на **`*.storage.yandex.net`** запрос **без** `Authorization` (подписанный URL). Для **`public_url`** — отдельная ветка (анонимный `href`, cookies / веб-API — см. FAQ про 403).
3. **Processing** — стандартный пайплайн (транскрибация, topic extraction и т.д.)

### Процесс загрузки

1. **Upload task** — резолвит метаданные через `ConfigResolver.resolve_upload_metadata`, рендерит пути через Jinja (`render_jinja`)
2. `YandexDiskUploader.upload_video` → `YandexDiskClient.upload_file`
3. Клиент автоматически создаёт все промежуточные папки (`_ensure_folder_exists`)
4. Загружает файл двухшаговым процессом: получить upload URL → PUT файл
5. После успешной загрузки видео — **best-effort** выгрузка sidecar-файлов по полям `preset_metadata`, если они заданы (ошибка одного файла не отменяет запись о загрузке видео)

---

## FAQ

### Какие права нужны OAuth-токену?

Для скачивания: `cloud_api:disk.read`, `cloud_api:disk.info`.
Для загрузки: дополнительно `cloud_api:disk.write`.
Для полного доступа: `cloud_api:disk.app_folder`.

### Нужен ли OAuth для публичных ссылок?

Нет. Публичные ссылки (`https://disk.yandex.ru/d/...`) работают без авторизации. Используйте `public_url` вместо `folder_path`.

### Почему нет «общих папок» в списке корня / у них «нет пути»?

Три разных случая:

1. **Публичная ссылка на чужой каталог** — объект **не** монтируется в ваше личное дерево Диска, поэтому у него **нет** вашего `folder_path` в смысле OAuth. В API это другой сценарий: метаданные по `public_key` из ссылки (`GET /v1/disk/public/resources`). В LEAP для input задайте **`public_url`**, не папку с токеном.
2. **Вы сами опубликовали** файл или папку (включили доступ по ссылке) — такие ресурсы перечисляет отдельный метод **`GET /v1/disk/resources/public`** (в dev-скрипте: `scripts/list_yandex_disk_folders.py --published`). Это не список «всего Диска», только опубликованного вами.
3. **Приглашение в общую папку Yandex 360** (collaboration) — после **принятия** приглашения Яндекс создаёт **копию** с обычным путём `disk:/…` в вашем Диске; её должно быть видно в `GET /v1/disk/resources?path=/` наряду с остальными папками (см. [официальную справку](https://yandex.com/support/yandex-360/customers/disk/web/en/share/shared-folders-to-me)). Если папки нет — приглашение не принято, каталог перенесён/переименован, или смотрите только веб-раздел «Общие папки» без синхронизации копии.

### Какие файлы считаются видео?

Файлы определяются по MIME-типу (`video/*`) или расширению из **`StorageSettings.supported_video_formats`** (код: `mp4`, `webm`, `mkv`, `mov`).

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

### Скачивание падает с HTTP 403 после успешного sync

- **Источник с `folder_path` (API)** — на втором шаге должен быть **тот же OAuth-токен**, что и при запросе ссылки ([документация](https://yandex.ru/dev/disk-api/doc/ru/reference/content)). Браузерные `Referer`/`Origin` для этого сценария не нужны.
- **Публичная ссылка (`public_url`)** — временные URL на CDN часто требуют **cookies** и заголовки как у браузера; бэкенд дополнительно может использовать разбор ``store-prefetch`` и **POST** `…/public/api/download-url`. Если не работает (капча, пустой store), имеет смысл тот же контент через **`folder_path`**, если каталог доступен вашему Диску.

### Как проверить, что токен работает?

Создайте Input Source с `folder_path: "/"` и запустите синхронизацию. Если токен валиден — вернётся список файлов.

Локально можно вывести каталоги из корня или опубликованные ресурсы:

```bash
cd backend && PYTHONPATH=$PWD uv run python scripts/list_yandex_disk_folders.py
cd backend && PYTHONPATH=$PWD uv run python scripts/list_yandex_disk_folders.py --published
```

### Что если загрузка прервалась?

Скачивание поддерживает resume (возобновление с места остановки). При загрузке на Диск — файл загружается целиком через один PUT-запрос.

### Можно ли перезаписывать файлы при загрузке?

Да. Установите `overwrite: true` в `preset_metadata` пресета или переопределите через `metadata_config.yandex_disk.overwrite` в шаблоне. По умолчанию `false` — если файл существует, будет ошибка. Тот же флаг наследуют best-effort загрузки субтитров / транскрипции / `description.txt`.

### Типичные строки в логах (как читать)

| Сообщение | Что значит | Действие |
|-----------|------------|----------|
| `Yandex public \| no resource hash in store` | Для публичной шары не нашли hash в `store-prefetch`; скачивание всё равно может пойти по REST-`href`. | Если дальше 403/ошибка — капча, пустой store или смена вёрстки Яндекса; попробуйте `folder_path` + OAuth. |
| `Yandex API download \| HTTP 403` | Отказ CDN или неверный шаг OAuth/редиректа. | Проверьте токен, перезапуск воркеров после обновления кода; для API — актуальный `href`. |
| `Yandex Disk extra files skipped: no oauth_token` | Видео на Диск уже залито, но для **доп. файлов** (srt/vtt/транскрипт) не найден токен на аплоадере. | У пресета должен быть **credential** с Яндекс OAuth; код подставляет токен и из `credentials_data`, если на объекте поле пустое. |
| OAuth callback `access_denied` / `user_denied` | Пользователь **закрыл** окно согласия (YouTube/VK/Zoom/Яндекс). | Не ошибка сервера: в логе уровень **INFO**; на фронте обработайте `?oauth_error=`. |

Сообщения вроде `Audio file not found: /path/to/invalid_audio.mp3` из **юнит-тестов** (`video_processing_module`) в проде обычно не встречаются.

### Видео «обрезалось» или «битое» после скачивания / обработки

См. англ. гайд [MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md): валидация размера, трим по тишине, битый исходник (метаданные vs реальный поток), VP9+Opus в `source.mp4` / `video.mp4`, скрипт `scripts/diagnose_video_file.py`.

### Безопасность OAuth-токена

OAuth-токен хранится в зашифрованном виде (`encrypted_data`) в базе данных. Он **не** сохраняется в метаданных записей (`source_metadata`) и не виден в API-ответах. При скачивании токен извлекается из зашифрованных credentials в момент выполнения задачи.
