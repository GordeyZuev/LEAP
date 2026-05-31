# Цель по умолчанию при запуске make без аргументов
.DEFAULT_GOAL := help

# REPO_ROOT от каталога этого Makefile — чтобы `make -f frontend/Makefile`
# из корня не ломал пути.
_FRONTEND_MAKEFILE := $(lastword $(MAKEFILE_LIST))
FRONTEND_DIR := $(abspath $(dir $(_FRONTEND_MAKEFILE)))
REPO_ROOT := $(abspath $(FRONTEND_DIR)/..)

# pnpm — lockfile в frontend/; npm как fallback, если pnpm не установлен.
PNPM := $(strip $(shell command -v pnpm 2>/dev/null))
ifeq ($(PNPM),)
  PKG_RUN := npm run
  PKG_EXEC := npx
  PKG_INSTALL := npm install
else
  PKG_RUN := pnpm run
  PKG_EXEC := pnpm exec
  PKG_INSTALL := pnpm install
endif

.PHONY: help
help:
	@echo "LEAP Frontend — Next.js ($(FRONTEND_DIR))"
	@echo ""
	@echo "📦 Зависимости:"
	@echo "  make install        - Установить зависимости (pnpm или npm)"
	@echo ""
	@echo "🚀 Разработка:"
	@echo "  make dev            - Dev-сервер (http://localhost:3000)"
	@echo "  make build          - Production-сборка"
	@echo "  make start          - Запуск production-сервера (после build)"
	@echo ""
	@echo "🔍 Проверка качества:"
	@echo "  make lint           - ESLint"
	@echo "  make lint-fix       - ESLint с авто-исправлениями"
	@echo "  make typecheck      - TypeScript (tsc --noEmit)"
	@echo "  make quality        - lint + typecheck"
	@echo ""
	@echo "🧹 Очистка:"
	@echo "  make clean          - Удалить .next и кэши Next.js"
	@echo ""
	@echo "ℹ️ Переменные окружения (см. src/api/client.ts, next.config.ts):"
	@echo "  NEXT_PUBLIC_API_URL          — URL API (по умолчанию http://localhost:8000)"
	@echo "  NEXT_DEV_ALLOWED_ORIGINS     — LAN IP для HMR (.env.local)"

.PHONY: install
install:
	@cd $(FRONTEND_DIR) && $(PKG_INSTALL)

.PHONY: dev
dev:
	@cd $(FRONTEND_DIR) && $(PKG_RUN) dev

.PHONY: build
build:
	@cd $(FRONTEND_DIR) && $(PKG_RUN) build

.PHONY: start
start:
	@cd $(FRONTEND_DIR) && $(PKG_RUN) start

.PHONY: lint
lint:
	@echo "🔍 Running ESLint..."
	@cd $(FRONTEND_DIR) && $(PKG_RUN) lint

.PHONY: lint-fix
lint-fix:
	@echo "🔧 Running ESLint with auto-fix..."
	@cd $(FRONTEND_DIR) && $(PKG_RUN) lint:fix

.PHONY: typecheck
typecheck:
	@echo "🔍 Running TypeScript..."
	@cd $(FRONTEND_DIR) && $(PKG_EXEC) tsc --noEmit

.PHONY: quality
quality: lint typecheck
	@echo "✅ All quality checks passed"

.PHONY: clean
clean:
	@rm -rf $(FRONTEND_DIR)/.next
	@echo "🧹 Removed .next/"
