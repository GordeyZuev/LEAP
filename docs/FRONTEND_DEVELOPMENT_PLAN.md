# План разработки фронтенда LEAP

**Цель:** Запустить разработку веб-интерфейса и обеспечить возможность тестирования на production.

**Версия:** v1.0  
**Дата:** February 2026

---

## Содержание

1. [Фаза 0: Подготовка (1–2 дня)](#фаза-0-подготовка-12-дня)
2. [Фаза 1: MVP фронтенда (1–2 недели)](#фаза-1-mvp-фронтенда-12-недели)
3. [Фаза 2: Основные фичи (2–3 недели)](#фаза-2-основные-фичи-23-недели)
4. [Фаза 3: Production-ready (3–5 дней)](#фаза-3-production-ready-35-дней)

---

## Фаза 0: Подготовка (1–2 дня)

### 0.1 Верификация API

| # | Задача | Команда/действие | Критерий готовности |
|---|--------|------------------|---------------------|
| 1 | Запустить API локально | `make docker-up` или `make api` | `curl http://localhost:8000/api/v1/health` → 200 OK |
| 2 | Инициализировать БД | `make init-db` | Миграции применены, ошибок нет |
| 3 | Проверить OpenAPI | Открыть http://localhost:8000/docs | Swagger UI отвечает |
| 4 | Скачать OpenAPI schema | `curl http://localhost:8000/openapi.json > openapi.json` | Файл сохранён |
| 5 | Тестовый login | `POST /api/v1/auth/register` + `POST /api/v1/auth/login` через Swagger | Получен JWT |

### 0.2 Выбор технологий

| Решение | Варианты | Рекомендация |
|---------|----------|--------------|
| Фреймворк | React, Vue, Svelte | React + Vite (быстрый старт, экосистема) |
| API-клиент | Ручной, OpenAPI Generator, @hey-api/openapi-ts | OpenAPI Generator или axios + типы вручную |
| State | TanStack Query, SWR, Zustand | TanStack Query (кэш, retry) |
| Auth хранение | localStorage, cookie, memory | localStorage + refresh при 401 |
| Стили | Tailwind, CSS Modules, MUI | Tailwind (скорость разработки) |

### 0.3 Результат фазы

- [ ] API работает локально
- [ ] Выбран стек фронтенда
- [ ] OpenAPI schema сохранена
- [ ] Успешно выполнен register + login

---

## Фаза 1: MVP фронтенда (1–2 недели)

### 1.1 Структура проекта

```
frontend/                 # или web/, client/
├── src/
│   ├── api/              # API client, типы
│   ├── auth/             # login, logout, token refresh
│   ├── components/
│   ├── pages/
│   ├── hooks/
│   └── lib/
├── public/
├── package.json
└── vite.config.ts
```

### 1.2 Задачи по приоритету

| # | Задача | Оценка | Зависимости |
|---|--------|--------|-------------|
| 1 | Создать проект (Vite + React) | 1 ч | — |
| 2 | Настроить API client (base URL, axios/fetch) | 2 ч | 1 |
| 3 | Реализовать Auth: Login / Register | 4 ч | 2 |
| 4 | Хранение токена + auto-refresh при 401 | 2 ч | 3 |
| 5 | Protected routes / Layout | 2 ч | 3 |
| 6 | Страница Recordings: список | 4 ч | 4, 5 |
| 7 | Recordings: добавление по URL (add-url) | 2 ч | 6 |
| 8 | Recordings: статус pipeline, базовый прогресс | 4 ч | 6 |

### 1.3 Ключевые API endpoints для MVP

| Endpoint | Метод | Использование |
|----------|-------|---------------|
| `/api/v1/auth/register` | POST | Регистрация |
| `/api/v1/auth/login` | POST | Вход |
| `/api/v1/auth/refresh` | POST | Обновление токена |
| `/api/v1/users/me` | GET | Профиль |
| `/api/v1/recordings` | GET | Список записей |
| `/api/v1/recordings/add-url` | POST | Добавить видео по ссылке |
| `/api/v1/recordings/{id}` | GET | Детали записи |
| `/api/v1/recordings/{id}/full-pipeline` | POST | Запуск пайплайна |

### 1.4 Результат фазы

- [ ] Пользователь может зарегистрироваться и войти
- [ ] Отображается список recordings
- [ ] Можно добавить видео по URL
- [ ] Виден статус обработки (INITIALIZED, DOWNLOADING, PROCESSING и т.д.)

---

## Фаза 2: Основные фичи (2–3 недели)

### 2.1 Credentials и OAuth

| # | Задача | Оценка | Endpoints |
|---|--------|--------|-----------|
| 1 | Страница Credentials: список | 2 ч | `GET /api/v1/credentials` |
| 2 | OAuth: кнопки "Подключить YouTube/VK/Zoom" | 2 ч | `GET /api/v1/oauth/{platform}/authorize` |
| 3 | OAuth callback → redirect на фронт | 2 ч | Настроить redirect_uri / frontend URL |
| 4 | Отображение статуса подключённых аккаунтов | 2 ч | `GET /api/v1/credentials/status` |

### 2.2 Templates

| # | Задача | Оценка | Endpoints |
|---|--------|--------|-----------|
| 1 | Список templates | 2 ч | `GET /api/v1/templates` |
| 2 | Создание / редактирование template | 4 ч | `POST`, `PATCH /api/v1/templates` |
| 3 | Output presets в template | 2 ч | `GET /api/v1/output-presets` |
| 4 | Preview match | 2 ч | `POST /api/v1/templates/{id}/preview-match` |

### 2.3 Recordings (расширение)

| # | Задача | Оценка |
|---|--------|--------|
| 1 | Детали записи: таймкоды, темы, субтитры | 4 ч |
| 2 | Загрузка на платформу (YouTube/VK) | 3 ч |
| 3 | Input Sources (Zoom sync, yt-dlp) | 4 ч |
| 4 | Плейлисты: add-playlist | 2 ч |
| 5 | Яндекс Диск: add-yadisk | 2 ч |

### 2.4 Автоматизация

| # | Задача | Оценка |
|---|--------|--------|
| 1 | Список automation jobs | 2 ч |
| 2 | Создание / редактирование job | 3 ч |
| 3 | Просмотр расписания | 1 ч |

### 2.5 User Config и Profile

| # | Задача | Оценка |
|---|--------|--------|
| 1 | Страница профиля | 2 ч |
| 2 | User config (настройки обработки) | 3 ч |
| 3 | Статистика (recordings, storage, quota) | 2 ч |

### 2.6 Результат фазы

- [ ] OAuth подключение YouTube, VK, Zoom
- [ ] CRUD templates
- [ ] Полный pipeline: add → process → upload
- [ ] Input sources и sync
- [ ] Automation jobs
- [ ] Профиль и статистика

---

## Фаза 3: Production-ready (3–5 дней)

### 3.1 Инфраструктура production

| # | Задача | Действие |
|---|--------|----------|
| 1 | CORS для фронтенда | `SERVER_CORS_ORIGINS=https://app.domain.com` |
| 2 | OAuth redirect URIs | HTTPS в Google/VK/Zoom консолях |
| 3 | Nginx/Cloudflare HTTPS | По [DEPLOYMENT.md](DEPLOYMENT.md) |
| 4 | Docker Compose | Проверить все сервисы, очереди Celery |

### 3.2 Фронтенд для production

| # | Задача | Действие |
|---|--------|----------|
| 1 | Environment variables | `VITE_API_URL=https://api.domain.com` |
| 2 | Build | `npm run build` или `pnpm build` |
| 3 | Деплой статики | Nginx, S3+CloudFront, Vercel, Netlify |
| 4 | Error tracking | Sentry (опционально) |

### 3.3 Чеклист перед релизом

- [ ] Все env-переменные prod настроены
- [ ] CORS указаны только нужные origins
- [ ] OAuth callbacks ведут на HTTPS
- [ ] Health check отвечает
- [ ] Celery workers обрабатывают задачи
- [ ] Резервное копирование БД и storage настроено

---

## Сводная таблица

| Фаза | Срок | Результат |
|------|------|-----------|
| 0. Подготовка | 1–2 дня | API работает, стек выбран |
| 1. MVP | 1–2 недели | Login, Recordings (список + add-url) |
| 2. Основные фичи | 2–3 недели | OAuth, Templates, полный pipeline, automation |
| 3. Production | 3–5 дней | Деплой, HTTPS, мониторинг |

**Общая оценка:** 4–6 недель до полноценного MVP с прод-тестированием.

---

## Связанные документы

- [TECHNICAL.md](TECHNICAL.md) — REST API reference
- [DEPLOYMENT.md](DEPLOYMENT.md) — Production deployment
- [OAUTH.md](OAUTH.md) — OAuth настройка
- [INDEX.md](INDEX.md) — Навигация по документации

---

## Next Actions (первый день)

1. Выполнить все пункты [Фазы 0](#фаза-0-подготовка-12-дня)
2. Создать React/Vite проект в `frontend/` или отдельном репозитории
3. Реализовать Auth (Login/Register) и защищённые маршруты
4. Добавить страницу Recordings со списком и формой add-url
