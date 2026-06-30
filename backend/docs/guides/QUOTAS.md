# Квоты, лимиты и feature-флаги — как это работает

Краткий концептуальный гайд по системе квот LEAP: из чего складывается лимит,
что считается, где проверяется и как этим управляет админ.
API-справочник эндпоинтов — в [`QUOTA_AND_ADMIN_API.md`](QUOTA_AND_ADMIN_API.md).

Добавлено/актуализировано в **v0.10.5.0**.

---

## 1. Модель: план → подписка → оверайды → эффективный лимит

Лимиты пользователя вычисляются по приоритету (`QuotaService.get_effective_quotas`):

```
custom_max_* (UserSubscriptionModel)   ← персональный оверайд, высший приоритет
        ↓ если NULL
план (SubscriptionPlanModel)           ← лимиты тарифа
        ↓ если подписки нет
DEFAULT_QUOTAS (config/settings.py)    ← дефолты в коде
```

- **`subscription_plans`** — тарифы-шаблоны (Free, Pro, …): включённые лимиты и цены.
- **`user_subscriptions`** — один ряд на пользователя: какой план + персональные оверайды `custom_max_*`.
- **`DEFAULT_QUOTAS`** — если у пользователя нет подписки. Все значения по умолчанию `None`.

**`None` (NULL) везде означает «безлимит».**

Эффективные лимиты: `max_recordings_per_month`, `max_storage_gb`,
`max_concurrent_tasks`, `max_automation_jobs`, `min_automation_interval_hours`,
`max_transcriptions_per_month`, `max_processing_per_month`.

---

## 2. Что считается (usage)

Месячные счётчики живут в **`quota_usage`**, ключ — `period` = `YYYYMM` (например `202607`).
Новая строка на каждый месяц создаётся автоматически (reset не нужен).

| Счётчик | Когда инкрементируется |
| --- | --- |
| `recordings_count` | при создании записи через `POST /add-url`, `/add-playlist`, локальную загрузку |
| `transcriptions_count` | при завершении транскрибации (standalone и в пайплайне) |
| `processing_count` | при старте пайплайна обработки |
| `uploads_count` | при успешной загрузке на платформу |
| `storage_bytes` | **не используется для гейта** — объём считается на лету из хранилища |
| `concurrent_tasks_count` | **не используется для гейта** — активные задачи считаются из `on_air` |

> Трекинг — **best-effort**: сбой записи счётчика/события логируется и не роняет
> операцию (в худшем случае лёгкий недосчёт, никогда не сломанный пайплайн).

### Storage — на лету из S3
`max_storage_gb` сверяется с реальным объёмом папки пользователя
`users/user_{slug:06d}/` через `storage.get_prefix_size()` (Yandex Object
Storage / MinIO), а не с локального диска и не из хранимого счётчика.

### Concurrent tasks — из флага `on_air`
`max_concurrent_tasks` сверяется с числом записей, у которых `on_air = true`
(`_count_active_pipelines`). `on_air` выставляется оркестратором
`run_recording_task` (одинаково для manual / auto-run / bulk) и сбрасывается при
завершении, ошибке (`on_failure`), паузе и maintenance-свипе застрявших записей —
поэтому значение **не дрейфует** и самовосстанавливается.

---

## 3. Где проверяются лимиты (enforcement)

### Soft-гейт на создание/запуск — `check_user_quotas` (зависимость FastAPI)
Подключён к `POST /add-url`, `/add-playlist`, локальной загрузке. Проверяет три
лимита и возвращает **HTTP 429**:

1. `check_recordings_quota` — месячный лимит записей.
2. `check_concurrent_tasks_quota` — активные пайплайны (по `on_air`).
3. `check_storage_quota` — объём хранилища.

### Hard-limits на обработку/транскрибацию
Дублируются на двух уровнях, чтобы ни один путь не обошёл лимит:

| Лимит | Роутер (быстрый 429) | Задача (авторитетный гейт) |
| --- | --- | --- |
| `max_processing_per_month` | `POST /{id}/run` | `run_recording_task` → статус `quota_exceeded`, `on_air` сброшен |
| `max_transcriptions_per_month` | `POST /{id}/transcribe` | `_async_transcribe_recording` → `RuntimeError`, стадия падает |

Роутерный гейт даёт мгновенный 429 пользователю; task-гейт ловит auto-run, bulk
и запуск из пайплайна, которые не проходят через роутер.

---

## 4. Feature-флаги (права)

8 булевых флагов на `UserModel`, по умолчанию `True`. Проверяются фабрикой
`require_feature(...)` → **HTTP 403** при отключении.

| Флаг | Где enforced |
| --- | --- |
| `can_transcribe` | `POST /{id}/transcribe` |
| `can_process_video` | `POST /{id}/run`, `/{id}/topics`, `/{id}/subtitles` |
| `can_upload` | `POST /{id}/upload/{platform}`, `/bulk/upload` |
| `can_delete_recordings` | `DELETE /{id}`, `/bulk/delete` |
| `can_export_data` | `POST /export` |
| `can_manage_credentials` | create / update / delete `/credentials` |
| `can_create_templates` | эндпоинты `/templates` (инлайн-проверка) |
| `can_update_uploaded_videos` | зарезервирован (эндпоинтов пока нет) |

Управляются админом через `PATCH /admin/users/{id}`.

---

## 5. История действий (`usage_events`)

Неизменяемый лог для аналитики: `recording_created`, `recording_deleted`,
`processing_started` / `processing_completed`, `transcription_completed`,
`upload_completed`. Поля: `event_type`, `recording_id`, `duration_seconds`,
`bytes_delta`, `event_metadata` (JSONB), `created_at`.
Доступ админу: `GET /admin/users/{id}/events`.

---

## 6. Управление (админ)

- **Пользователь:** `GET/PATCH /admin/users/{id}` — роль, `is_active`, все 8 флагов.
- **Подписка:** `POST/PATCH /admin/users/{id}/subscription` — назначить план,
  задать/расширить `custom_*` оверайды квот.
- **Просмотр:** `GET /admin/users/{id}/subscription` — подписка + эффективные
  лимиты + текущее использование (`quota_status`).
- **Планы:** `GET/POST/PATCH /admin/plans`.

Пользователь видит своё потребление и лимиты: `GET /api/v1/users/me/quota`
(блоки `recordings`, `storage`, `concurrent_tasks`, `transcriptions`,
`processing` + `current_usage`).

---

## 7. Что НЕ считается (известные границы)

- **Sync-пути** (`InputSource` sync: Zoom / Yandex Disk / video-url) создают записи
  через `create_or_update` и **не** трекают `recording_created` и не считаются в
  квоту записей. Это намеренно: фоновая синхронизация не должна неожиданно выедать
  месячный лимит. При необходимости трекинг можно добавить точечно.
- **Pay-as-you-go** — схема в БД есть, биллинговая логика не реализована (YAGNI).
- **Стадии download/trim/topics/subtitles** — отдельных `usage_events` не пишут;
  весь пайплайн охватывают `processing_started` / `processing_completed`.

---

## Файлы

- `api/services/quota_service.py` — расчёт эффективных лимитов, проверки, статус.
- `api/auth/dependencies.py` — `check_user_quotas`, `require_feature`.
- `api/repositories/subscription_repos.py` — счётчики `quota_usage`.
- `api/repositories/usage_event_repo.py` — лог событий.
- `database/auth_models.py` — `SubscriptionPlanModel`, `UserSubscriptionModel`, `QuotaUsageModel`, `UsageEventModel`.
- `config/settings.py` — `DEFAULT_QUOTAS`.
