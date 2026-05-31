# LEAP — root Makefile.
#
# Targets grouped into three areas:
#   - Production deploy (Terraform / Yandex Cloud VM)  → prefix: deploy-*
#   - Local Docker Compose (postgres/redis/etc.)       → prefix: dev-*
#   - Per-stack work (backend/, frontend/)             → cd into the dir
#
# Run `make help` to see everything.

BACKEND_DIR   := backend
FRONTEND_DIR  := frontend
TERRAFORM_DIR := terraform

_ROOT_MK     := $(lastword $(MAKEFILE_LIST))
REPO_ROOT    := $(abspath $(dir $(_ROOT_MK)))
COMPOSE_FILE := $(REPO_ROOT)/docker-compose.yml

DOCKER_COMPOSE_BIN := $(strip $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose"))
DOCKER_COMPOSE := $(DOCKER_COMPOSE_BIN) -f $(COMPOSE_FILE)

# Generate a short-lived IAM token from the yc CLI default profile.
# `terraform apply` will pick it up via the YC_TOKEN env var (the yandex
# provider doesn't auto-read ~/.config/yandex-cloud/config.yaml).
# Tokens are valid for ~12 hours which is more than enough for one session.
YC_TOKEN_CMD := YC_TOKEN=$$(yc iam create-token)
TF := $(YC_TOKEN_CMD) terraform -chdir=$(TERRAFORM_DIR)
VM_IP_CMD := $(TF) output -raw vm_public_ip 2>/dev/null
DOMAIN_CMD := $(TF) output -raw domain_url 2>/dev/null | sed 's#https://##'

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
.PHONY: help
help:
	@echo "LEAP — Makefile cheatsheet"
	@echo ""
	@echo "First-time setup:"
	@echo "  make deploy-check            — verify prerequisites (yc CLI, tfvars, mirror)"
	@echo "  make deploy-init             — terraform init (downloads YC provider)"
	@echo "  make deploy-plan             — terraform plan (preview, no changes)"
	@echo "  make deploy                  — terraform apply (creates everything in YC)"
	@echo "  make deploy-gh-secrets       — push Terraform outputs to GitHub Secrets"
	@echo ""
	@echo "Daily ops (after the VM is provisioned):"
	@echo "  make deploy-status           — show VM IP, registry ID, NS, bucket"
	@echo "  make deploy-ssh              — SSH to the VM"
	@echo "  make deploy-logs             — tail VM cloud-init bootstrap log"
	@echo "  make deploy-app-logs         — tail docker compose logs on the VM"
	@echo "  make deploy-refresh-env      — re-fetch Lockbox secrets, restart stack"
	@echo "  make deploy-smoke-test       — curl https://<domain>/api/v1/health"
	@echo "  make deploy-grafana-pw       — print Grafana admin password"
	@echo "  make deploy-rollback IMAGE_TAG=<sha>  — roll back to a previous image tag"
	@echo "  make deploy-backup-pg        — pg_dump on demand, upload to backups bucket"
	@echo ""
	@echo "DESTRUCTIVE:"
	@echo "  make deploy-destroy          — wipe EVERYTHING in YC (requires 'yes' confirm)"
	@echo ""
	@echo "Local development (Docker via colima):"
	@echo "  make dev-up                  — start local postgres + redis"
	@echo "  make dev-down                — stop local stack"
	@echo "  make dev-ps                  — local container status"
	@echo "  make dev-logs                — follow postgres + redis logs"
	@echo "  make dev-build               — rebuild API images locally"
	@echo ""
	@echo "Sub-projects:"
	@echo "  cd $(BACKEND_DIR)  && make help    — API, Celery, tests, alembic"
	@echo "  cd $(FRONTEND_DIR) && make help    — Next.js dev/build, lint"

# ============================================================================
# PRODUCTION DEPLOYMENT (Yandex Cloud via Terraform)
# ============================================================================

# --- Preflight check --------------------------------------------------------
.PHONY: deploy-check
deploy-check:
	@echo "==> Checking deploy prerequisites"
	@command -v terraform >/dev/null || { echo "  ✗ terraform not installed"; exit 1; }
	@command -v yc >/dev/null || { echo "  ✗ yc CLI not installed"; exit 1; }
	@echo "  ✓ terraform + yc CLI installed"
	@yc config get cloud-id >/dev/null 2>&1 || { echo "  ✗ run 'yc init' first"; exit 1; }
	@echo "  ✓ yc CLI authenticated"
	@test -f $$HOME/.terraformrc || { echo "  ✗ ~/.terraformrc missing (see DEPLOYMENT.md §2)"; exit 1; }
	@grep -q "terraform-mirror.yandexcloud.net" $$HOME/.terraformrc || { echo "  ✗ ~/.terraformrc missing YC mirror"; exit 1; }
	@grep -q 'include = \["registry.terraform.io/\*/\*"\]' $$HOME/.terraformrc || { echo "  ✗ ~/.terraformrc mirror needs wildcard '*/*'"; exit 1; }
	@echo "  ✓ ~/.terraformrc mirror configured"
	@test -f $(TERRAFORM_DIR)/terraform.tfvars || { echo "  ✗ terraform/terraform.tfvars missing — copy from terraform.tfvars.example"; exit 1; }
	@! grep -q "FILL_ME_" $(TERRAFORM_DIR)/terraform.tfvars || { echo "  ✗ terraform.tfvars has FILL_ME_ placeholders — fill them in"; exit 1; }
	@echo "  ✓ terraform.tfvars filled"
	@for f in oauth_zoom oauth_google oauth_vk oauth_yandex_disk fireworks_creds deepseek_creds; do \
	  test -f $(BACKEND_DIR)/config/$$f.json || { echo "  ✗ $(BACKEND_DIR)/config/$$f.json missing"; exit 1; }; \
	done
	@echo "  ✓ all credential files present in $(BACKEND_DIR)/config/"
	@echo ""
	@echo "✓ Ready for: make deploy-init && make deploy"

# --- Terraform lifecycle ----------------------------------------------------
.PHONY: deploy-init deploy-plan deploy
deploy-init: deploy-check
	$(TF) init

deploy-plan: deploy-check
	$(TF) plan

deploy: deploy-check
	$(TF) apply

# --- Post-deploy automation -------------------------------------------------
.PHONY: deploy-gh-secrets deploy-status
deploy-gh-secrets:
	@echo "==> Pushing Terraform outputs to GitHub Secrets..."
	@command -v gh >/dev/null || { echo "  ✗ gh CLI not installed (brew install gh && gh auth login)"; exit 1; }
	@$(TF) output -raw github_secrets_commands | bash

deploy-status:
	@$(TF) output

# --- Daily ops --------------------------------------------------------------
.PHONY: deploy-ssh deploy-logs deploy-app-logs deploy-refresh-env \
        deploy-smoke-test deploy-grafana-pw deploy-rollback deploy-backup-pg
deploy-ssh:
	@ip=$$($(VM_IP_CMD)); \
	test -n "$$ip" || { echo "VM not provisioned yet (run 'make deploy')"; exit 1; }; \
	ssh ubuntu@$$ip

deploy-logs:
	@ip=$$($(VM_IP_CMD)); \
	test -n "$$ip" || { echo "VM not provisioned yet"; exit 1; }; \
	ssh ubuntu@$$ip 'sudo tail -f /var/log/leap-bootstrap.log'

deploy-app-logs:
	@ip=$$($(VM_IP_CMD)); \
	test -n "$$ip" || { echo "VM not provisioned yet"; exit 1; }; \
	ssh ubuntu@$$ip 'cd /opt/leap && docker compose logs --tail=200 -f'

deploy-refresh-env:
	@ip=$$($(VM_IP_CMD)); \
	test -n "$$ip" || { echo "VM not provisioned yet"; exit 1; }; \
	ssh ubuntu@$$ip 'sudo /opt/leap/refresh-env.sh && cd /opt/leap && docker compose up -d'

deploy-smoke-test:
	@domain=$$($(DOMAIN_CMD)); \
	test -n "$$domain" || { echo "Domain unknown — has 'make deploy' been run?"; exit 1; }; \
	echo "GET https://$$domain/api/v1/health"; \
	curl -fsS "https://$$domain/api/v1/health" && echo " ✓"

deploy-grafana-pw:
	@$(TF) output -raw grafana_admin_password; echo

# Rollback: requires IMAGE_TAG=<sha> argument
deploy-rollback:
	@test -n "$(IMAGE_TAG)" || { echo "Usage: make deploy-rollback IMAGE_TAG=<git-sha>"; exit 1; }
	@ip=$$($(VM_IP_CMD)); \
	test -n "$$ip" || { echo "VM not provisioned yet"; exit 1; }; \
	echo "Rolling back to image tag: $(IMAGE_TAG)"; \
	ssh ubuntu@$$ip "cd /opt/leap && sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=$(IMAGE_TAG)/' .env && docker compose pull && docker compose up -d"

# On-demand Postgres backup → leap-backups bucket (same script as nightly cron)
deploy-backup-pg:
	@ip=$$($(VM_IP_CMD)); \
	test -n "$$ip" || { echo "VM not provisioned yet"; exit 1; }; \
	ssh ubuntu@$$ip 'bash /opt/leap/scripts/pg_backup.sh'

# --- DESTRUCTIVE ------------------------------------------------------------
.PHONY: deploy-destroy
deploy-destroy:
	@echo "⚠️  This DESTROYS the production VM, all bucket data, Lockbox, registry."
	@echo "Type 'yes' to continue: " ; read ans ; [ "$$ans" = "yes" ] || exit 1
	$(TF) destroy

# ============================================================================
# LOCAL DEVELOPMENT (Docker Compose)
# ============================================================================
.PHONY: dev-up dev-down dev-ps dev-logs dev-build
dev-up:
	$(DOCKER_COMPOSE) up -d postgres redis

dev-down:
	$(DOCKER_COMPOSE) down

dev-ps:
	$(DOCKER_COMPOSE) ps

dev-logs:
	$(DOCKER_COMPOSE) logs -f postgres redis

dev-build:
	$(DOCKER_COMPOSE) build

# ============================================================================
# Backward-compat aliases (old target names still work)
# ============================================================================
.PHONY: docker-up docker-down docker-ps docker-logs docker-build
docker-up: dev-up
docker-down: dev-down
docker-ps: dev-ps
docker-logs: dev-logs
docker-build: dev-build
