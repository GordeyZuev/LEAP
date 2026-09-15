# LEAP

> Lecture Enhancement & Automation Platform – AI-обработка образовательного видео от загрузки до публикации

<!-- Backend -->
![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)
![Redis](https://img.shields.io/badge/Redis-7+-blue.svg)
![Celery](https://img.shields.io/badge/Celery-5+-blue.svg)
<!-- Frontend -->
![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)
![React](https://img.shields.io/badge/React-19-61DAFB.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6.svg)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4.svg)
<!-- Meta -->
![License](https://img.shields.io/badge/license-BSL%201.1-orange.svg)
![Age](https://img.shields.io/badge/age-12%2B-black.svg)

**LEAP** – multi-tenant платформа с REST API и веб-интерфейсом для образовательного видео: импорт, обрезка тишины, транскрибация, темы с таймкодами, субтитры, публикация на площадки и публичные ссылки внутри LEAP.

**Версия:** `v0.11.0.0` (September 2026) · **Статус:** Beta · **Возраст:** 12+
**Backend:** Python 3.14 · FastAPI · PostgreSQL · Redis · Celery · AssemblyAI · DeepSeek · yt-dlp · S3-compatible storage
**Frontend:** Next.js 16 · React 19 · TypeScript 5 · Tailwind CSS 4 · TanStack Query v5 · shadcn/ui

**Репозиторий:** API – [`backend/`](backend/) (`uv`, `make`, тесты, Celery); веб-клиент – [`frontend/`](frontend/) (`pnpm`, Next.js). В корне – [`docker-compose.yml`](docker-compose.yml) и [`Makefile`](Makefile) для Docker.

Встроенная справка в приложении: раздел **Documentation**. Навигация по техническим гайдам: [`backend/docs/INDEX.md`](backend/docs/INDEX.md). Частые вопросы: [`backend/docs/FAQ.md`](backend/docs/FAQ.md).

---

## Для кого

- **Университеты и EdTech** – массовая публикация лекций, изоляция факультетов и преподавателей, шаблоны курсов.
- **Онлайн-школы** – таймкоды, субтитры, описание по шаблону, расписание обработки.
- **Контент-команды** – batch, пресеты площадок, API для своей обвязки.
- **Админы платформы** – RBAC, квоты, audit, мониторинг.

---

## Что умеет сейчас

**Источники**

- Zoom (OAuth)
- МТС Линк (организационный API-ключ; MP4 готовится при Run)
- Ссылка через yt-dlp: YouTube, Rutube и сотни других сайтов (видео и плейлисты)
- Яндекс Диск (публичная ссылка или OAuth)
- Загрузка файла с компьютера

**Обработка**

- FFmpeg: обрезка тишины, в том числе длинного тихого хвоста после лекции
- Транскрибация: AssemblyAI
- Темы, главы, саммари и вопросы: DeepSeek
- Субтитры SRT и VTT
- Медиа в объектном хранилище (Yandex Object Storage / MinIO); локальный диск только для временных файлов FFmpeg и ASR

**Публикация**

- YouTube и Яндекс Диск – параллельно, с пресетами и шаблонами метаданных
- Публичные страницы LEAP: запись `/share/{token}`, курс `/share/p/{uuid}`, канал `/c/{slug}`
- Плейлисты-курсы, оформление Look LEAP (название, описание, обложка) без выгрузки на внешние площадки

**Автоматизация**

- Шаблоны (базовый + именованные с matching rules)
- Пресеты площадок
- Celery Beat: sync + process + upload, dry-run

Google Drive как источник и выгрузка на Rutube – в планах, не в текущем релизе.

---

## Как это работает

```
Источник → FFmpeg → AssemblyAI + DeepSeek → метаданные → публикация
            обрезка     транскрипт, темы,         шаблоны         YouTube / Я.Диск /
            тишины      субтитры                  Jinja2          share LEAP
```

1. **Импорт** – sync источника, ссылка, плейлист или файл. Запись создаётся в БД, файл уходит в tenant storage.
2. **Обработка** – Celery-цепочка: download → trim → transcribe → topics → subtitles. Каждый шаг на своей очереди.
3. **Метаданные** – заголовок, описание, таймкоды, миниатюра по шаблону и user config.
4. **Публикация** – выбранные пресеты и/или публичная ссылка LEAP. Статусы по каждой площадке отдельно.

**Статусы записи (сокращённо):** `INITIALIZED` → `DOWNLOADING` → `PROCESSING` → `PROCESSED` → `UPLOADING` → `READY`. Для МТС Линк бывают `PENDING_SOURCE` / `PENDING_CONVERSION`. Ещё: `SKIPPED`, `EXPIRED`, `Failed`.

---

## Стек

**Backend:** Python 3.14+, FastAPI, SQLAlchemy 2 (async), PostgreSQL 15+, Redis 7+, Celery 5 + Beat, Alembic, Pydantic v2, uv, Ruff, ty.

**AI и медиа:** AssemblyAI (ASR), DeepSeek (темы), FFmpeg, yt-dlp, Jinja2.

**Интеграции:** Zoom OAuth, МТС Линк UserAPI, YouTube Data API v3, Яндекс Диск REST.

**Хранение:** S3-compatible (production – Yandex Object Storage, local – MinIO). Credentials в БД шифруются (Fernet). JWT + RBAC + CSRF через Redis.

**Frontend:** Next.js 16 (App Router), React 19, TypeScript 5, Tailwind CSS 4, TanStack Query v5, Axios, Plyr, pnpm.

Горизонтальное масштабирование – отдельные Celery-очереди: `downloads`, `processing_cpu`, `async_operations`, `uploads`, `maintenance`.

Подробнее: [`backend/docs/TECHNICAL.md`](backend/docs/TECHNICAL.md), [`backend/docs/ADR_OVERVIEW.md`](backend/docs/ADR_OVERVIEW.md).

---

## Документация

| Документ | Зачем |
|----------|--------|
| [FAQ.md](backend/docs/FAQ.md) | Частые вопросы: шаблоны, share, ASR, возраст 12+ |
| [INDEX.md](backend/docs/INDEX.md) | Полная навигация по гайдам |
| [TECHNICAL.md](backend/docs/TECHNICAL.md) | REST API и модули |
| [DEPLOYMENT.md](backend/docs/guides/DEPLOYMENT.md) | Деплой |
| [PLAYLISTS.md](backend/docs/guides/PLAYLISTS.md) | Курсы и публичные ссылки |
| [CHANNELS.md](backend/docs/guides/CHANNELS.md) | Каналы `/c/{slug}` |
| [MTS_LINK_GUIDE.md](backend/docs/guides/MTS_LINK_GUIDE.md) | МТС Линк |
| [CHANGELOG.md](backend/docs/CHANGELOG.md) | Полная история релизов |

В приложении тот же материал в более коротком виде: **Documentation** (поиск по разделам, FAQ, troubleshooting).

---

## Последние релизы

Полная история – **[CHANGELOG.md](backend/docs/CHANGELOG.md)**. Ниже только текущая линейка.

**Новое в `v0.11.0.0`** – **Каналы:** у программы появляется своя публичная страница — видео и курсы вместе, короткий баннер и описание. Зритель ищет, сортирует, переключает сетку и список; в списке видны дата, длительность и короткая строка из тем лекции или описания курса. Владелец собирает состав в Channels, включает и выключает ту же ссылку; если сменить адрес — старая страница пропадает. У курса может быть своя обложка. Открытия витрины канала и курса видны в аналитике, как у обычной публичной ссылки. Шаблон после обработки может положить лекцию на вкладку Videos, но сам публичную ссылку на лекцию не включает. **Просмотр:** лекция в курсе открывается быстрее; под заголовком тот же переключатель Edited / Original, что и на одиночной ссылке; кнопки плеера не пропадают при смене ролика; по желанию — сразу следующее видео. **Вовлечённость:** в аналитике публичной ссылки, курса и канала видно, какие главы выбирают, как часто досматривают лекцию, где зрители обычно останавливаются и как переходят между видео в курсе — в том же периоде, что просмотры и скачивания.

**Новое в `v0.10.9.1`** – **Скорость:** публичный watch (share и курс) стартует с меньшим числом API-запросов — `play_url` и субтитры в одном ответе, VTT и файлы уходят на S3 редиректом, а не через прокси API. **Списки** записей и плейлистов в редакторе грузятся быстрее (постеры без N+1 конфига, SQL-пагинация плейлистов, компактный список записей). **Run** сразу ставит задачу в очередь — подготовка MTS Link только в worker. На карточке записи статус пайплайна опрашивается лёгким endpoint без повторной загрузки артефактов из S3. **Главы:** если модель не вернула темы, лекция не считается готовой и не уходит на площадки; на карточке можно заново запросить главы (**Retry topics**), перерывы по-прежнему отмечаются отдельно. Операторам: расширенные HTTP-гистограммы и панель 4xx по маршруту в Grafana.

**Новое в `v0.10.9.0`** – **Креденшелы:** если платформа отвергла ключ (`needs_reauth`), баннер по приложению и жёлтая метка на Credentials в сайдбаре. **Просмотр:** один плеер на share, плейлисте и записи — главы рядом с картинкой, Wide Screen без морфинга рельса, Edited / Original, Theme в Summary & questions, Created Overview. На записи Theme / главы / саммари / вопросы и overview правятся карандашом (Save / Cancel). **Автоматизации:** таблица как у Templates (Job, Schedule, Status, Actions). **Share:** Summary & questions и Files открыты сразу. Списки Recordings не расходятся с SSR из‑за grid/table в `localStorage`. **LEAP курсы:** запись попадает в плейлисты и получает share только после успешной обработки (как публикация на LEAP), не при привязке шаблона.

**Новое в `v0.10.8.3`** – **Usage & analytics:** Settings → Usage — все квоты (`использовано / лимит`, включая automation jobs), Activity с графиками и своим периодом (до 366 дней); Admin → Analytics и Activity по пользователю; share-аналитика с произвольными датами. **Автоматизации:** Dry run синкает источники и показывает, какие записи обработаются, без запуска пайплайна; Run с подтверждением; в истории — какие записи уехали. **LEAP:** публикация на платформу после обработки (`publish_leap`, миграция **048**); в шаблоне и Run — отдельно LEAP и Upload, оверрайды look в Metadata → Platform overrides, подсказки из leap preset. **Стабильность:** просмотр публичной шары считается и если вы залогинены в LEAP; Grafana WARNING не заливает 401/404. Плюс: быстрее списки без «мигания»; docs hub и FAQ; обрезка «тихого хвоста» МТС Линк; переименование обложки в picker. Гайды: [`USAGE_AND_ANALYTICS.md`](backend/docs/guides/USAGE_AND_ANALYTICS.md), [`TEMPLATES.md`](backend/docs/guides/TEMPLATES.md), [`PLAYLISTS.md`](backend/docs/guides/PLAYLISTS.md), [`MONITORING.md`](backend/docs/guides/MONITORING.md), [`AUTOMATION_CELERY_BEAT.md`](backend/docs/guides/AUTOMATION_CELERY_BEAT.md).

**Новое в `v0.10.8.2`** – форматирование описаний курсов; Look LEAP без выгрузки на площадки; МТС Линк короче 10 минут помечается blank; наследование блоков в конфигах; плеер: J/L, «?», длительность на панели.

**Ранее в `v0.10.8`** – МТС Линк как источник, чат и материалы сессии, проверка креденшелов, аналитика share, плейлисты-курсы с публичной ссылкой, стабильность плеера.

**Ранее в `v0.10.x`** – веб-интерфейс, объектное хранилище, квоты и Admin, AssemblyAI, сессии, тёмная тема, редактор AI-контента на странице записи.

---

## Лицензия

Business Source License 1.1. Текст: [LICENSE](LICENSE).

---

## Контакты

**Телеграм:** [Gordey Zuev](https://t.me/WhiteShape)
**Почта:** [gordey.zuev@gmail.com](mailto:gordey.zuev@gmail.com)

Информационная продукция: **12+**.

**Status:** In Active Development · Beta
