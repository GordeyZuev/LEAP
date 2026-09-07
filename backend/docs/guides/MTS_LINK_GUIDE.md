# MTS Link Guide

Руководство по интеграции с МТС Линк как источником записей (input): подключение org API key, выбор лекторов, конвертация в MP4 и сопровождающие файлы (чат, презентации).

---

## Содержание

1. [Обзор](#обзор)
2. [API key организации](#api-key-организации)
3. [Input Source](#input-source)
4. [Sync: что находится](#sync-что-находится)
5. [Prepare и Run: конвертация в MP4](#prepare-и-run-конвертация-в-mp4)
6. [Сопровождающие файлы](#сопровождающие-файлы)
7. [Архитектура](#архитектура)
8. [FAQ](#faq)

---

## Обзор

| Что | Поведение |
|-----|-----------|
| Аутентификация | Org API key (`x-auth-token`), вкладка **Manual** в Credentials. OAuth пока не поддержан |
| Кто синхронизируется | Список email лекторов в конфиге Input Source (обязателен, минимум один) |
| Основное медиа | Официальный MP4 после конвертации на серверах МТС Линк |
| Конвертация | Короткий **prepare** на **`POST /run`** (или автоматизация); не на Sync и не на `POST /download` |
| Сопровождающие файлы | Чат и файлы мероприятия — best-effort, рядом с видео |

**Ключевое ограничение платформы:** интерактивную онлайн-запись **нельзя скачать одним файлом** — это набор медиа. МТС Линк умеет перекодировать её в MP4 по запросу; только этот MP4 идёт в пайплайн. Поле `link` у записи — это HTML-страница плеера, а не файл, поэтому LEAP хранит её лишь как ссылку «открыть в МТС Линк».

---

## API key организации

1. Личный кабинет МТС Линк → **Бизнес** → **API/Вебхуки** → **API**.
2. Создать ключ и скопировать значение.
3. В LEAP: **Credentials** → **Add** → **MTS Link** → вставить ключ → Save.

Ключ работает **от имени владельца организации** и видит записи всех сотрудников. Персонального ключа лектора в продукте нет, поэтому ограничение «чьи записи забираем» задаётся не на credential, а на Input Source через список email.

Ключ хранится зашифрованным в `user_credentials` (платформа `mts_link`), как и остальные credentials — см. [CREDENTIAL_SECURITY.md](CREDENTIAL_SECURITY.md).

---

## Input Source

**Sources** → **Add** → тип **MTS Link**.

| Поле в UI | Ключ конфига | Назначение |
|-----------|--------------|-----------|
| **Lecturer emails** | `user_emails` | Обязательно, по одному на строку. Каждый email резолвится в `userId` через `GET /organization/members` |
| **Video quality** | `conversion_quality` | `720` (по умолчанию) или `1080` |
| **What the video shows** | `conversion_view` | Что «вшивается» в кадр MP4: `none` — только ведущие (по умолчанию), `chat`, `questions`, `minichat` |
| **Save chat as a file** | `fetch_chat` | Сохранять `chat.json` рядом с видео (по умолчанию включено) |
| **Save presentations and files** | `fetch_session_files` | Сохранять презентации и вложения (по умолчанию включено) |

Без email источник не создаётся (422): иначе один org-ключ синхронизировал бы записи всей организации.

Если email не найден или ему соответствует несколько сотрудников, sync пропускает **только этого** лектора и продолжает с остальными; ошибка попадает в лог.

---

## Sync: что находится

Sync только **находит** записи и пишет метаданные — конвертацию не запускает (иначе sync исчерпал бы очередь конвертаций org API).

| Условие | Статус после sync | Метаданные |
|---------|-------------------|------------|
| `GET /fileSystem/file` duration **&lt; 10 мин** | `SKIPPED`, `blank_record` | `online_duration` задан |
| Duration известен, `size == 0`, MP4 ещё нет | `INITIALIZED` (если шаблон) | не Pending: запись уже собрана |
| Duration неизвестен и `size == 0` и нет MP4 | `PENDING_SOURCE` (prepare) | `online_size: 0`, `needs_mp4: true` |
| Запись готова, MP4 ещё нет | `INITIALIZED` | `needs_mp4: true` |
| Для сессии уже есть сконвертированная запись | `INITIALIZED` | `needs_mp4: false`, `download_url` в метаданных |

Длительность на синке берётся из `GET /fileSystem/file/{recordId}` (поле `duration` в секундах), не из урезанного `GET /records` и **не** из ISO `PT1H20M0S` у мероприятия (это слот в календаре).

| Где | Что это |
|-----|---------|
| `source.meta.online_duration` | Длина **онлайн-записи** в плеере МТС. Sync обновляет всегда. |
| `recordings.duration` | Исходная длина (online до скачивания, потом ffprobe MP4). Sync это не затирает, если файл уже есть. В API списка / карточки / share отдаётся `final_duration`, если он уже есть. |
| Плеер | Длина **этого** MP4 (браузер). Если расходится с сайдбаром — в БД ещё сессия, на диске другой файл. |
| `final_duration` | После транскрипции (таймлайн речи), не длина файла. |

Порог blank **10 минут** (`duration < 600`). Без файла — online-сессия. С файлом — **ffprobe MP4 в storage**, не цифра в карточке (там часто ещё длина сессии). Blank видны с **Include blanks**.

Уже существующие строки (на сервере, после деплоя):

```bash
docker compose exec api uv run python scripts/backfill_mts_link_blank.py
docker compose exec api uv run python scripts/backfill_mts_link_blank.py --apply
```

Скрипт печатает `api_duration`, `db_duration`, `file_duration` (ffprobe объекта в storage). С файлом blank берётся с **файла**, не с длинной сессии API. `--apply` записывает длительность файла в карточку.

**`PENDING_CONVERSION`** выставляет только prepare (Run / автоматизация). **`PENDING_SOURCE`** — sync на **новую** карточку, если ещё нет duration и `size == 0`, либо prepare, если Run застал ту же ситуацию.

`source_key` записи — `mtslink:record:{recordId}`, поэтому две онлайн-записи одной сессии не схлопываются в одну запись LEAP.

Диапазон даты берётся из тех же `from_date` / `to_date`, что и sync Zoom; `GET /records` требует времени, поэтому дата без времени расширяется до полных суток.

---

## Prepare и Run: конвертация в MP4

**Единая точка входа в пайплайн для MTS Link — `POST /api/v1/recordings/{id}/run`** (и bulk run / автоматизация через тот же smart run). Отдельный **`POST /download` для MTS Link возвращает 400** с текстом *«MTS Link recordings must use POST /run to prepare and download.»*

### Зачем так

Раньше конвертация заказывалась внутри Celery-задачи download: воркер очереди `downloads` до **30 минут** опрашивал API МТС Линк и уходил в **Celery-retry**, занимая слот. У org API key **одна активная конвертация на сотрудника** — параллельные Run только тратили воркеры.

Теперь:

1. **Prepare** (`api.services.mts_link_prepare.py`) — короткий проход: готовый MP4 на сессии; reuse конвертации; иначе заказ `POST /records/{id}/conversions`. `size == 0` сам по себе не Pending — только вместе с неизвестным `duration`.
2. Если MP4 **ещё не готов** — запись → **`PENDING_CONVERSION`** (или **`PENDING_SOURCE`**, если запись ещё собирается), **`on_air` не ставится**, ответ Run: `awaiting_source: true`, блок `mts` с прогрессом.
3. Пользователь или **автоматизация** снова жмёт Run / срабатывает job — prepare повторяется, пока не появится `downloadUrl`.
4. Когда MP4 готов — prepare → `READY`, проверка квоты, **`on_air: true`**, стартует обычная цепочка download → trim → …
5. **Download-задача** только **стримит** уже готовый файл в storage; долгого poll нет.

### Ответ `POST /run` при ожидании МТС

```json
{
  "success": true,
  "task_id": null,
  "awaiting_source": true,
  "recording_status": "PENDING_CONVERSION",
  "message": "MTS Link is still converting; run again or wait for automation",
  "mts": {
    "outcome": "converting",
    "conversion_progress": 42,
    "conversion_state": "processing"
  }
}
```

### Поток prepare (кратко)

1. `GET /eventsessions/{id}/converted-records` — если есть готовый MP4, outcome **READY**.
2. `GET /converted-records` (и незавершённые, и завершённые) + `GET` сохранённого `conversion_id`. Берём `completed` (**READY**, даже если в ответе нет `downloadUrl`), иначе **`processing` с наибольшим `progress`**. `canceled` / `failed` не берём.
3. Пока есть такая джоба — **без POST**.
4. Иначе `GET /records` + duration (meta `online_duration` или `GET /fileSystem/file`): нет записи → failed; **нет duration и `size == 0`** → **ASSEMBLING** / `PENDING_SOURCE`. Известный duration при `size == 0` — запись уже собрана, заказываем конвертацию.
5. Иначе `POST /records/{id}/conversions`. 403 `Simultaneous conversions quantity exceeded` — ждём, не reauth.
6. Outcome **CONVERTING** → `PENDING_CONVERSION` до следующего Run.

**Длительность рендера** на стороне МТС Линк — обычно 15–25 минут (до ~2× длительности лекции). LEAP **не держит** воркер всё это время.

**Очередь вместо второго заказа:** готовые MP4 видны на `converted-records` сессии; незавершённые — в общем списке конвертаций. Ответ `403` «одна конвертация на сотрудника» — ждём, не считаем мёртвым ключом.

Записи длиннее ~24 часов МТС Линк требует сначала обрезать в их интерфейсе — LEAP такую конвертацию не делает и падает с понятной ошибкой.

### Автоматизация

`run_recording_task` в начале вызывает тот же `prepare_mts_link_recording`. Job с фильтром **Initialized** / **Converting** / **Pending** периодически «пингует» МТС, пока MP4 не появится. В форме автоматизации эти статусы есть по умолчанию у новых правил. Старые jobs, где выбран только `INITIALIZED`, нужно обновить: включить **Converting** (и **Pending**, если запись ещё собирается).

### Сброс застрявших записей

Если запись осталась в `DOWNLOADING` с `on_air=true` после обновления со старой версии — **`POST /api/v1/recordings/{id}/reset`** (при необходимости `delete_files=true`), затем снова Run.

---

## Настройки выбираются один раз

`quality` и «что показывает видео» **вплавлены в MP4** в момент рендера, и API МТС Линк не сообщает, с какими настройками сделан каждый готовый файл. Поэтому в v1 всё просто: берётся любой готовый MP4 сессии, а если готового нет — заказывается конвертация с текущими настройками источника.

Практические следствия:

- Настройки имеет смысл выбрать до первого скачивания.
- Если поменять их у уже скачанной записи, лежащий `source.mp4` не изменится. В метаданных сохраняются `conversion_quality` и `conversion_view`, с которыми он сделан, — по ним видно расхождение.
- Если у сессии несколько готовых MP4, prepare/download берут запись с тем же `recordId`. Без id (sync) — первый готовый URL.

Перерендер по требованию и добор сопровождающих файлов к уже скачанному видео **не реализованы** — сознательно оставлено на будущее.

---

## Сопровождающие файлы

После успешного скачивания видео LEAP **best-effort** забирает:

- **Чат** — `GET /eventsessions/{id}/chat` → `source_extras/chat.json`
- **Файлы мероприятия** — `GET /eventsessions/{id}/files` → `source_extras/files/` + `source_extras/files_manifest.json`

```
storage/users/user_{slug}/recordings/{id}/
  source.mp4
  source_extras/
    chat.json
    files/slides.pdf
    files_manifest.json
```

В интерфейсе они видны в карточке **Files** на странице записи — под разделителем **From the source**, отдельно от артефактов пайплайна. Ссылки на скачивание отдаёт `GET /api/v1/recordings/{id}/source-extras`.

- Сама запись и её MP4 в списке файлов пропускаются — это не вложения.
- Имена файлов приводятся к безопасному виду; дубликаты получают префикс с id файла.
- Ошибка или отсутствие чата/файлов **не ломает** пайплайн: в метаданных источника обновляются флаги `extras.chat`, `extras.files_count`, `extras.error`.

**Не путать с `view=chat`:** этот параметр конвертации вшивает чат **в картинку** MP4. `chat.json` — отдельный структурированный лог. Для лекций обычно нужен `view=none` плюс `chat.json`.

---

## Архитектура

| Слой | Файл |
|------|------|
| HTTP-клиент UserAPI | [`api/mts_link_api.py`](../../api/mts_link_api.py) |
| Prepare-before-run | [`api/services/mts_link_prepare.py`](../../api/services/mts_link_prepare.py) |
| Smart run / блок `/download` | [`api/routers/recordings.py`](../../api/routers/recordings.py) |
| Credentials | [`models/mts_link_auth.py`](../../models/mts_link_auth.py) |
| Конфиг источника | [`api/schemas/template/source_config.py`](../../api/schemas/template/source_config.py) |
| Sync | [`api/routers/input_sources.py`](../../api/routers/input_sources.py) |
| Стрим MP4 + сопровождающие файлы | [`video_download_module/platforms/mtslink/downloader.py`](../../video_download_module/platforms/mtslink/downloader.py) |
| Пути в storage | [`file_storage/path_builder.py`](../../file_storage/path_builder.py) |

Проверка ключа и выдачи API без UI — скрипт [`scripts/mts_link_smoke.py`](../../scripts/mts_link_smoke.py):

```bash
export MTS_LINK_API_KEY='your-key'
uv run python scripts/mts_link_smoke.py --list-members
uv run python scripts/mts_link_smoke.py --list-members --query пономарен
uv run python scripts/mts_link_smoke.py --user-id 176030889 --limit 10
uv run python scripts/mts_link_smoke.py --user-id 176030889 --limit 15 --skip-converted
```

Duration probe (default): `GET /fileSystem/file/{recordId}` for each listed record and `files[].duration` on the first event session. Skip with `--skip-duration`; extra id with `--file-id`.

---

## FAQ

**Можно выдать доступ только к записям одного преподавателя?**
Нет, ключ всегда организационный. Ограничение — список email на Input Source.

**Почему запись в `PENDING_SOURCE`?**
Онлайн-запись ещё собирается: нет `duration` в `GET /fileSystem/file`, `size == 0` **и** готового MP4 ещё нет. Если duration уже есть, `size == 0` больше не ставит Pending. Если MP4 уже есть в `converted-records`, **Run** забирает его даже при `size == 0`. Повторный sync не создаёт вторую строку: ключ `mtslink:record:{id}` уникален на пользователя (миграция `046`).

**Почему запись в `PENDING_CONVERSION`?**
Заказан или уже идёт рендер MP4 на серверах МТС Линк (`waiting` / `processing`). **Run** пингует статус; воркер download не занят. В UI — бейдж **Converting**. Если в meta уже `conversion_state: completed` и `conversion_progress: 100`, а статус всё ещё Converting — это баг старого prepare (`GET` конверсии без `downloadUrl`); после фикса Run должен стартовать пайплайн.

**Почему `/download` отвечает 400?**
Для MTS Link отдельный download отключён: конвертацию заказывает только **`POST /run`**. Используйте Run на карточке записи или bulk run.

**Почему «скачивание» занимало часы в старых версиях?**
Download-задача держала Celery-воркер на poll до 30 минут и ретраилась. После prepare-before-run ожидание — это статус записи и повторные короткие Run, не блокировка очереди `downloads`.

**Почему в карточке ~1 ч, а в плеере несколько часов?**
Сайдбар часто показывает `final_duration` (речь после ASR). Плеер — длину **`video.mp4`**. Если trim не срезал цифровую тишину до конца слота МТС (нет `silence_end` у FFmpeg), файл остаётся на весь слот. С **v0.10.8.3** незакрытый `silence_start` до EOF режется; уже обработанные строки нужно прогнать trim снова.

**Почему в карточке 1 ч 41 мин, а в плеере несколько секунд?**
Карточка брала `recordings.duration` с **онлайн-сессии** МТС; плеер — длину **скачанного MP4**. Это разные файлы (ранняя конвертация или чужой MP4 с той же сессии). После download длительность карточки = ffprobe MP4; `online_duration` остаётся в `source.meta`.

**Почему backfill на проде ничего не пометил blank?**
Первый прогон смотрел только API (сессии длинные). Нужен деплой с ffprobe файла: в логе `file_duration=4` и `blank=True`, затем `--apply`.

**Что считается blank у MTS Link?**
Длительность **< 10 минут** (строго меньше 600 с) у online-записи **или** у лежащего в LEAP файла. Zoom по-прежнему 20 мин или &lt; 25 МБ. В списке blank скрыты, пока не включён **Include blanks**.

**Расшифровка МТС Линк используется?**
Нет, LEAP делает свой ASR. Q&A и вебхуки МТС Линк тоже пока не используются.
