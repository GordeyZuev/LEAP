# LEAP — backend

Исходный код **REST API** (FastAPI), воркеров Celery, миграций Alembic и связанной логики.

## Быстрый старт

Из этого каталога:

```bash
uv sync   # обязательно после клонирования; подтягивает группу dev (pytest)
make docker-up    # PostgreSQL + Redis (compose-файл в корне репозитория)
make api          # http://localhost:8000 — docs: /docs
```

Полное описание продукта и сценариев — в [README.md](../README.md) в корне монорепозитория.

**Pre-commit:** конфиг в корне репозитория (`.pre-commit-config.yaml`). Установка хуков: `uv run pre-commit install` из корня или из `backend/` (нужен `uv` и dev-зависимости).

## Docker

Файл **`docker-compose.yml`** и **корневой `Makefile`** (только Docker: `docker-up`, `docker-down`, `docker-build`, …) лежат в **корне** репозитория. Из `backend/` команда `make docker-up` всё так же вызывает тот же compose-файл.

Полный стек в контейнерах:

```bash
cd ..
docker compose up -d
# или только инфраструктура: make docker-up
```

(контекст образа API — каталог `backend/`.)
