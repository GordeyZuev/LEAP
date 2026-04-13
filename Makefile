# LEAP — корень монорепозитория: только Docker Compose и подсказки по структуре.
# Все цели разработки бэкенда (uv, pytest, Celery, миграции) — в backend/Makefile.
# Фронтенд (позже): в frontend/ — свои package.json / pnpm, без смешения с этим файлом.

BACKEND_DIR := backend
FRONTEND_DIR := frontend

_ROOT_MK := $(lastword $(MAKEFILE_LIST))
REPO_ROOT := $(abspath $(dir $(_ROOT_MK)))
COMPOSE_FILE := $(REPO_ROOT)/docker-compose.yml

DOCKER_COMPOSE_BIN := $(strip $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose"))
DOCKER_COMPOSE := $(DOCKER_COMPOSE_BIN) -f $(COMPOSE_FILE)

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "LEAP — корень репозитория"
	@echo ""
	@echo "Docker (docker-compose.yml здесь; образы API собираются из ./backend):"
	@echo "  make docker-up       - PostgreSQL + Redis"
	@echo "  make docker-down     — остановить сервисы этого compose-проекта"
	@echo "  make docker-ps       — статус контейнеров"
	@echo "  make docker-logs     — логи postgres и redis (follow)"
	@echo "  make docker-build    — пересобрать образы api/celery/flower"
	@echo ""
	@echo "Разработка:"
	@echo "  cd $(BACKEND_DIR) && make help   — API, тесты, uv, Celery, БД"
	@echo "  cd $(FRONTEND_DIR) && …          — UI, когда появится каталог (pnpm/npm)"
	@echo ""
	@echo "Полный стек в фоне из этого каталога:"
	@echo "  $(DOCKER_COMPOSE_BIN) -f docker-compose.yml up -d"

.PHONY: docker-up docker-down docker-ps docker-logs docker-build
docker-up:
	$(DOCKER_COMPOSE) up -d postgres redis

docker-down:
	$(DOCKER_COMPOSE) down

docker-ps:
	$(DOCKER_COMPOSE) ps

docker-logs:
	$(DOCKER_COMPOSE) logs -f postgres redis

docker-build:
	$(DOCKER_COMPOSE) build
