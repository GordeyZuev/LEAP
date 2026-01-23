.PHONY: clean-pycache

clean-pycache:
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

# ==================== Production-Ready API Commands ====================

# Setup: Установка всех зависимостей
.PHONY: install
install:
	@echo "📦 Установка зависимостей..."
	@uv pip install -r requirements.txt
	@echo "✅ Готово!"

# API: Запуск FastAPI сервера
.PHONY: api
api:
	uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# API: Production запуск (без reload)
.PHONY: api-prod
api-prod:
	uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

# ==================== Production Workers (Optimized) ====================

# CPU-bound: Video trimming only (prefork, 3 workers)
.PHONY: celery-cpu
celery-cpu:
	PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app worker \
		--loglevel=info -Q processing_cpu \
		--pool=prefork --concurrency=3 \
		--max-tasks-per-child=20

# Maintenance: Periodic cleanup tasks (prefork, 1 worker)
.PHONY: celery-maintenance
celery-maintenance:
	PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app worker \
		--loglevel=info -Q maintenance \
		--pool=prefork --concurrency=1

# Async: ALL async operations - processing, upload, template, sync, automation (threads, 20 workers)
# IMPORTANT: Uses threads pool for asyncio compatibility (gevent causes InterfaceError)
.PHONY: celery-async
celery-async:
	PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app worker \
		--loglevel=info -Q async_operations \
		--pool=threads --concurrency=20

# Beat: Task scheduler (single process)
.PHONY: celery-beat
celery-beat:
	PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app beat \
		--loglevel=info \
		--scheduler celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler

# ==================== Development ====================

# Dev: Single worker for all queues (local development)
.PHONY: celery-dev
celery-dev:
	PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app worker --beat \
		--loglevel=info \
		--queues=processing_cpu,async_operations,maintenance \
		--pool=prefork --concurrency=4

# All-in-One: Start all production workers in background
.PHONY: celery-all
celery-all:
	@echo "🚀 Starting Redis..."
	@brew services start redis
	@sleep 2
	@echo "🚀 Starting all Celery workers in background..."
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app worker -Q processing_cpu --pool=prefork --concurrency=3 --max-tasks-per-child=20 --loglevel=info --logfile=logs/celery-cpu.log --detach --pidfile=logs/celery-cpu.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app worker -Q async_operations --pool=threads --concurrency=20 --loglevel=info --logfile=logs/celery-async.log --detach --pidfile=logs/celery-async.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app worker -Q maintenance --pool=prefork --concurrency=1 --loglevel=info --logfile=logs/celery-maintenance.log --detach --pidfile=logs/celery-maintenance.pid
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app beat --loglevel=info --logfile=logs/celery-beat.log --detach --pidfile=logs/celery-beat.pid --scheduler celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler
	@echo "✅ All workers started! Check logs/ folder for output"
	@echo "📊 Use 'make celery-stop' to stop all workers"
	@echo "📊 Use 'make celery-status' to check workers"

# Stop all Celery workers
.PHONY: celery-stop
celery-stop:
	@echo "🛑 Stopping all Celery workers..."
	@-pkill -9 -f "celery.*api.celery_app" 2>/dev/null || true
	@-rm -f logs/celery-*.pid 2>/dev/null || true
	@echo "✅ All workers stopped"

# ==================== Monitoring ====================

# Flower: Web UI for monitoring Celery
.PHONY: flower
flower:
	PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app flower --port=5555

# Celery: Проверить активные tasks
.PHONY: celery-status
celery-status:
	@echo "📊 Active workers:"
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app inspect active
	@echo "\n📋 Registered tasks:"
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app inspect registered
	@echo "\n📈 Stats:"
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app inspect stats

# Celery: Очистить все задачи из очередей
.PHONY: celery-purge
celery-purge:
	@echo "⚠️  Удаление всех задач из очередей..."
	@PYTHONPATH=$$PWD:$$PYTHONPATH uv run celery -A api.celery_app purge -f
	@echo "✅ Очереди очищены!"

# Docker: Запуск PostgreSQL и Redis
.PHONY: docker-up
docker-up:
	docker-compose up -d postgres redis

# Docker: Остановка всех сервисов
.PHONY: docker-down
docker-down:
	docker-compose down

# Docker: Полная сборка и запуск
.PHONY: docker-full
docker-full:
	docker-compose up --build -d

# Database: Инициализация (создание БД + миграции)
.PHONY: init-db
init-db:
	@echo "🚀 Инициализация базы данных..."
	@uv run python -c "\
import asyncio; \
from database.config import DatabaseConfig; \
from database.manager import DatabaseManager; \
async def init(): \
    db = DatabaseManager(DatabaseConfig.from_env()); \
    await db.create_database_if_not_exists(); \
    await db.close(); \
asyncio.run(init())" 2>/dev/null || true
	@echo "✅ База данных создана"
	@echo "🔄 Применение миграций..."
	@uv run alembic upgrade head
	@echo "✅ Миграции применены!"

# Database: Применить миграции
.PHONY: migrate
migrate:
	uv run alembic upgrade head

# Database: Откатить последнюю миграцию
.PHONY: migrate-down
migrate-down:
	uv run alembic downgrade -1

# Database: Создать новую миграцию
.PHONY: migration
migration:
	@read -p "Enter migration name: " name; \
	uv run alembic revision --autogenerate -m "$$name"

# Database: Проверить текущую версию БД
.PHONY: db-version
db-version:
	@uv run alembic current

# Database: Показать историю миграций
.PHONY: db-history
db-history:
	@uv run alembic history

# Tests: Запуск всех тестов
.PHONY: test
test:
	uv run pytest tests/ -v

.PHONY: help
help:
	@echo "📦 Установка и обновление:"
	@echo "  make install        - Установка зависимостей из requirements.txt"
	@echo "  make uv-install     - Установка через uv sync"
	@echo "  make uv-update      - Обновить lock и синхронизировать"
	@echo ""
	@echo "🔍 Проверка и форматирование:"
	@echo "  make lint           - Проверка кода (ruff check)"
	@echo "  make lint-fix       - Авто-исправления (ruff check --fix)"
	@echo "  make format         - Форматирование (ruff format)"
	@echo ""
	@echo "🚀 API & Workers:"
	@echo "  make api            - Запуск FastAPI (dev режим)"
	@echo "  make api-prod       - Запуск FastAPI (production)"
	@echo "  make celery-dev     - Запуск Celery worker + beat (dev, все очереди)"
	@echo "  make celery-all     - 🔥 Запуск ВСЕХ воркеров + Redis (фон)"
	@echo "  make celery-stop    - 🛑 Остановить все воркеры"
	@echo "  make celery-status  - 📊 Статус воркеров"
	@echo ""
	@echo "🔧 Production Workers (специализированные):"
	@echo "  make celery-cpu     - CPU воркер (video trimming, prefork, 3 workers)"
	@echo "  make celery-async   - Async воркер (ALL async I/O ops, threads, 20) 🔥"
	@echo "  make celery-maintenance - Maintenance воркер (cleanup, prefork, 1)"
	@echo "  make celery-beat    - Beat scheduler (periodic tasks)"
	@echo "  make flower         - Flower UI (мониторинг Celery)"
	@echo ""
	@echo "🐳 Docker:"
	@echo "  make docker-up      - Запуск PostgreSQL + Redis"
	@echo "  make docker-down    - Остановка сервисов"
	@echo ""
	@echo "🗄️ База данных:"
	@echo "  make init-db        - Инициализация БД (создание + миграции)"
	@echo "  make migrate        - Применить миграции БД"
	@echo "  make migrate-down   - Откатить последнюю миграцию"
	@echo "  make db-version     - Показать текущую версию БД"
	@echo "  make db-history     - Показать историю миграций"
	@echo ""
	@echo "🧹 Очистка:"
	@echo "  make clean-pycache  - Очистить __pycache__ и *.pyc/*.pyo"
	@echo "  make clean-logs     - Очистить логи"
	@echo "  make clean          - Очистить кэши и логи"
	@echo ""
	@echo "ℹ️ Документация:"
	@echo "  API Documentation: http://localhost:8000/docs"
	@echo "  Flower Monitoring: http://localhost:5555"

.PHONY: uv-install uv-update uv-run
uv-install:
	@uv sync

uv-update:
	@uv lock --upgrade && uv sync

.PHONY: lint
lint:
	@ruff check .

.PHONY: lint-fix
lint-fix:
	@ruff check . --fix

.PHONY: format
format:
	@ruff format .

.PHONY: clean-logs
clean-logs:
	@rm -rf logs/*

.PHONY: clean
clean: clean-pycache clean-logs


