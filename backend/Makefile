# Цель по умолчанию при запуске make без аргументов
.DEFAULT_GOAL := help

# Docker Compose: файл в корне монорепозитория (контекст сборки — ./backend).
# REPO_ROOT от каталога этого Makefile, а не от $(CURDIR) — чтобы `make -f backend/Makefile`
# из корня не ломал путь.
_BACKEND_MAKEFILE := $(lastword $(MAKEFILE_LIST))
BACKEND_DIR := $(abspath $(dir $(_BACKEND_MAKEFILE)))
REPO_ROOT := $(abspath $(BACKEND_DIR)/..)
DOCKER_COMPOSE_BIN := $(strip $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose"))
DOCKER_COMPOSE := $(DOCKER_COMPOSE_BIN) -f $(REPO_ROOT)/docker-compose.yml

# Один интерпретатор на все цели: `uv run python` — тот же Python, что у проекта.
# Запуск через `python -m пакет` не зависит от обёрток в .venv/bin/ (shebang после переноса/смены Python).
UV_PY := uv run python

.PHONY: clean-pycache

clean-pycache:
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

# ==================== Production-Ready API Commands ====================

# API: Запуск FastAPI сервера
.PHONY: api
api:
	$(UV_PY) -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# API: Production запуск (без reload)
.PHONY: api-prod
api-prod:
	$(UV_PY) -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

# ==================== Production Workers (Optimized) ====================
# Architecture: 5 specialized workers, isolated by I/O profile (per BATCH_TESTING.md)
#   downloads      – Zoom/yt-dlp downloads      (threads, 20)
#   uploads        – VK/YouTube/YaDisk uploads   (threads, 20)
#   async_operations – transcription, topics, etc (threads, 28)
#   processing_cpu – FFmpeg trimming             (prefork, 6)
#   maintenance    – periodic cleanup            (prefork, 1)

# Downloads: Network-bound Zoom/yt-dlp downloads (threads, 20 workers)
# Isolated to prevent bandwidth starvation of other I/O tasks
.PHONY: celery-downloads
celery-downloads:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker \
		--loglevel=info -Q downloads \
		--pool=threads --concurrency=20 \
		-n downloads@%h

# Uploads: Network-bound platform uploads (threads, 20 workers)
# Isolated so uploads don't block processing pipeline
.PHONY: celery-uploads
celery-uploads:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker \
		--loglevel=info -Q uploads \
		--pool=threads --concurrency=20 \
		-n uploads@%h

# Async: Processing I/O — transcription, topics, subtitles, orchestration (threads, 28 workers)
# IMPORTANT: Uses threads pool for asyncio compatibility (gevent causes InterfaceError)
.PHONY: celery-async
celery-async:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker \
		--loglevel=info -Q async_operations \
		--pool=threads --concurrency=28 \
		-n async@%h

# CPU-bound: Video trimming only (prefork, 6 workers)
.PHONY: celery-cpu
celery-cpu:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker \
		--loglevel=info -Q processing_cpu \
		--pool=prefork --concurrency=6 \
		--max-tasks-per-child=20 \
		-n cpu@%h

# Maintenance: Periodic cleanup tasks (prefork, 1 worker)
.PHONY: celery-maintenance
celery-maintenance:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker \
		--loglevel=info -Q maintenance \
		--pool=prefork --concurrency=1 \
		-n maintenance@%h

# Beat: Task scheduler (single process)
.PHONY: celery-beat
celery-beat:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app beat \
		--loglevel=info \
		--scheduler celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler

# ==================== Development ====================

# Dev: Single worker for all queues (local development)
.PHONY: celery-dev
celery-dev:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker --beat \
		--loglevel=info \
		--queues=processing_cpu,async_operations,downloads,uploads,maintenance \
		--pool=prefork --concurrency=4

# All-in-One: Start all production workers in background
.PHONY: celery-start
celery-start:
	@echo "🚀 Starting Redis..."
	@brew services start redis
	@sleep 2
	@echo "🚀 Starting all Celery workers in background..."
	@mkdir -p logs
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker -Q downloads --pool=threads --concurrency=20 -n downloads@%h --loglevel=info --logfile=logs/celery-downloads.log --detach --pidfile=logs/celery-downloads.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker -Q uploads --pool=threads --concurrency=20 -n uploads@%h --loglevel=info --logfile=logs/celery-uploads.log --detach --pidfile=logs/celery-uploads.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker -Q async_operations --pool=threads --concurrency=28 -n async@%h --loglevel=info --logfile=logs/celery-async.log --detach --pidfile=logs/celery-async.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker -Q processing_cpu --pool=prefork --concurrency=6 --max-tasks-per-child=20 -n cpu@%h --loglevel=info --logfile=logs/celery-cpu.log --detach --pidfile=logs/celery-cpu.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app worker -Q maintenance --pool=prefork --concurrency=1 -n maintenance@%h --loglevel=info --logfile=logs/celery-maintenance.log --detach --pidfile=logs/celery-maintenance.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app beat --loglevel=info --logfile=logs/celery-beat.log --detach --pidfile=logs/celery-beat.pid --scheduler celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler
	@echo "✅ All workers started! Check logs/ folder for output"
	@echo "   downloads (20 threads) | uploads (20 threads) | async (28 threads) | cpu (6 prefork) | maintenance (1)"
	@echo "📊 Use 'make celery-stop' to stop all workers"
	@echo "📊 Use 'make celery-status' to check workers"

# Restart all Celery workers
.PHONY: celery-restart
celery-restart: celery-stop celery-start
	@echo "🔄 Workers restarted!"

# Stop all Celery workers
.PHONY: celery-stop
celery-stop:
	@echo "🛑 Stopping all Celery workers..."
	@-pkill -9 -f "celery.*api.celery_app" 2>/dev/null || true
	@-rm -f logs/celery-*.pid 2>/dev/null || true
	@echo "✅ All workers stopped"

# ==================== Monitoring ====================

# Flower: Web UI for monitoring Celery
.PHONY: flower flower-stop
flower:
	PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app flower --port=5555

flower-stop:
	@echo "🛑 Stopping Flower..."
	@-pkill -f "celery.*flower" 2>/dev/null || true
	@echo "✅ Flower stopped"

# Celery: Проверить активные tasks
.PHONY: celery-status
celery-status:
	@echo "📊 Active workers:"
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app inspect active
	@echo "\n📬 Queue assignment (async_operations = sync tasks):"
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app inspect active_queues 2>/dev/null || true
	@echo "\n📋 Registered tasks:"
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app inspect registered
	@echo "\n📈 Stats:"
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app inspect stats

# Celery: Очистить все задачи из очередей
.PHONY: celery-purge
celery-purge:
	@echo "⚠️  Удаление всех задач из очередей..."
	@PYTHONPATH=$$PWD:$$PYTHONPATH $(UV_PY) -m celery -A api.celery_app purge -f
	@echo "✅ Очереди очищены!"

# Docker: Запуск PostgreSQL и Redis (Compose v2)
.PHONY: docker-up
docker-up:
	$(DOCKER_COMPOSE) up -d postgres redis

# Docker: Остановка всех сервисов
.PHONY: docker-down
docker-down:
	$(DOCKER_COMPOSE) down

# Database: Инициализация (создание БД + миграции)
.PHONY: init-db
init-db:
	@echo "🚀 Инициализация базы данных..."
	@$(UV_PY) -c "\
import asyncio; \
from database.config import DatabaseConfig; \
from database.manager import DatabaseManager; \
async def init(): \
    db = DatabaseManager(DatabaseConfig.from_env()); \
    await db.create_database_if_not_exists(); \
    await db.close(); \
asyncio.run(init())"
	@echo "✅ База данных создана"
	@echo "🔄 Применение миграций..."
	@$(UV_PY) -m alembic upgrade head
	@echo "✅ Миграции применены!"

# Database: Применить миграции
.PHONY: migrate
migrate:
	$(UV_PY) -m alembic upgrade head

# Database: Откатить последнюю миграцию
.PHONY: migrate-down
migrate-down:
	$(UV_PY) -m alembic downgrade -1

# Database: Создать новую миграцию
.PHONY: migration
migration:
	@printf "Enter migration name: " >&2; read -r name && $(UV_PY) -m alembic revision --autogenerate -m "$$name"

# Database: Проверить текущую версию БД
.PHONY: db-version
db-version:
	@$(UV_PY) -m alembic current

# Database: Показать историю миграций
.PHONY: db-history
db-history:
	@$(UV_PY) -m alembic history

# Tests: Запуск всех тестов
.PHONY: test
test:
	$(UV_PY) -m pytest tests/ -v

# Tests: Запуск unit тестов (с моками, без БД)
.PHONY: tests-mock
tests-mock:
	@echo "🧪 Running unit tests with mocks..."
	@$(UV_PY) -m ruff check tests/
	@$(UV_PY) -m pytest tests/unit/ -v --tb=short

# Tests: Code quality checks
.PHONY: tests-quality
tests-quality:
	@echo "🔍 Running code quality tests..."
	@$(UV_PY) -m pytest tests/quality/ -v -m quality

# Tests: Security checks
.PHONY: tests-security
tests-security:
	@echo "🔒 Running security tests..."
	@$(UV_PY) -m pytest tests/quality/ -v -m security

.PHONY: help
help:
	@echo "LEAP backend — uv, тесты, API, Celery, БД. В корне репозитория Makefile только для Docker."
	@echo ""
	@echo "📦 Установка и обновление:"
	@echo "  make uv-install     - Установка зависимостей через uv sync"
	@echo "  make uv-update      - Обновить lock и синхронизировать"
	@echo ""
	@echo "🔍 Проверка и форматирование:"
	@echo "  make lint           - Проверка кода (ruff check)"
	@echo "  make lint-fix       - Авто-исправления + форматирование"
	@echo "  make format         - Форматирование кода"
	@echo "  make typecheck      - Проверка типов (ty)"
	@echo "  make typecheck-watch - Проверка типов в watch режиме"
	@echo "  make quality        - Все проверки качества"
	@echo "  make pre-commit-install - Установить pre-commit hooks"
	@echo "  make pre-commit-run     - Запустить pre-commit проверки"
	@echo ""
	@echo "🚀 API & Workers:"
	@echo "  make api            - Запуск FastAPI (dev режим)"
	@echo "  make api-prod       - Запуск FastAPI (production)"
	@echo "  make celery-dev     - Запуск Celery worker + beat (dev, все очереди)"
	@echo "  make celery-start   - 🔥 Запуск ВСЕХ воркеров + Redis (фон)"
	@echo "  make celery-stop    - 🛑 Остановить все воркеры"
	@echo "  make celery-restart - 🔄 Перезапустить все воркеры"
	@echo "  make celery-status  - 📊 Статус воркеров"
	@echo "  make celery-purge   - ⚠️  Удалить все задачи из очередей"
	@echo ""
	@echo "🔧 Production Workers (специализированные):"
	@echo "  make celery-downloads   - Downloads воркер (Zoom/yt-dlp, threads, 20)"
	@echo "  make celery-uploads     - Uploads воркер (VK/YT/YaDisk, threads, 20)"
	@echo "  make celery-async       - Async воркер (transcribe/topics, threads, 28)"
	@echo "  make celery-cpu         - CPU воркер (video trimming, prefork, 6)"
	@echo "  make celery-maintenance - Maintenance воркер (cleanup, prefork, 1)"
	@echo "  make celery-beat        - Beat scheduler (periodic tasks)"
	@echo "  make flower             - Flower UI (мониторинг Celery)"
	@echo "  make flower-stop       - Остановить Flower"
	@echo ""
	@echo "🐳 Docker:"
	@echo "  make docker-up      - PostgreSQL + Redis (compose-файл в корне репозитория)"
	@echo "  make docker-down    - Остановить сервисы этого compose-проекта"
	@echo ""
	@echo "🗄️ База данных:"
	@echo "  make init-db        - Инициализация БД (создание + миграции)"
	@echo "  make migrate        - Применить миграции БД"
	@echo "  make migrate-down   - Откатить последнюю миграцию"
	@echo "  make migration      - Создать новую миграцию (auto-generate)"
	@echo "  make db-version     - Показать текущую версию БД"
	@echo "  make db-history     - Показать историю миграций"
	@echo ""
	@echo "🧪 Тестирование:"
	@echo "  make test           - Запуск всех тестов"
	@echo "  make tests-mock     - Unit тесты (быстрые, с моками)"
	@echo "  make tests-quality  - Проверки качества кода"
	@echo "  make tests-security - Проверки безопасности"
	@echo ""
	@echo "🧹 Очистка:"
	@echo "  make clean-pycache  - Очистить __pycache__ и *.pyc/*.pyo"
	@echo "  make clean-logs     - Очистить логи"
	@echo "  make clean          - Очистить кэши и логи"
	@echo ""
	@echo "ℹ️ Документация:"
	@echo "  API Documentation: http://localhost:8000/docs"
	@echo "  Flower Monitoring: http://localhost:5555"

.PHONY: uv-install uv-update
uv-install:
	@uv sync

uv-update:
	@uv lock --upgrade && uv sync

.PHONY: lint
lint:
	@echo "🔍 Running ruff linter..."
	@$(UV_PY) -m ruff check .

.PHONY: lint-fix
lint-fix:
	@echo "🔧 Running ruff auto-fix..."
	@$(UV_PY) -m ruff check . --fix
	@$(UV_PY) -m ruff format .

.PHONY: format
format:
	@echo "✨ Formatting code..."
	@$(UV_PY) -m ruff format .

# Type checking with ty
.PHONY: typecheck
typecheck:
	@echo "🔍 Running ty type checker..."
	@$(UV_PY) -m ty check

# Watch mode for ty (useful during development)
.PHONY: typecheck-watch
typecheck-watch:
	@echo "👀 Running ty in watch mode..."
	@$(UV_PY) -m ty check --watch

# Type check with detailed output
.PHONY: typecheck-verbose
typecheck-verbose:
	@echo "🔍 Running ty with verbose output..."
	@$(UV_PY) -m ty check --verbose

# Pre-commit: Install hooks
.PHONY: pre-commit-install
pre-commit-install:
	@echo "🪝 Installing pre-commit hooks..."
	@uv add --group dev pre-commit
	@$(UV_PY) -m pre_commit install
	@echo "✅ Pre-commit hooks installed"

# Pre-commit: Run on all files
.PHONY: pre-commit-run
pre-commit-run:
	@echo "🔍 Running pre-commit on all files..."
	@$(UV_PY) -m pre_commit run --all-files

# Quality: Run all quality checks
.PHONY: quality
quality: lint typecheck tests-quality
	@echo "✅ All quality checks passed"

.PHONY: clean-logs
clean-logs:
	@rm -rf logs

.PHONY: clean
clean: clean-pycache clean-logs
