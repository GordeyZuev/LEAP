# 🚀 Deployment Guide

**Complete guide: development → production**

---

> **Монорепозиторий:** в **корне** репозитория лежит `docker-compose.yml` (контекст сборки образов — `./backend`). Команды `docker compose` / `docker-compose` для этого файла выполняйте из корня. Исходный код API — в каталоге `backend/`.

## ⚡ Quick Start (актуально на апрель 2026)

### Current Production Configuration

**Production-ready setup (корневой compose по умолчанию):**
- API: 4 воркера Uvicorn (`python -m uvicorn`)
- Celery worker: один процесс на очередях `downloads`, `uploads`, `async_operations`, `processing_cpu`, `maintenance` (см. `api/celery_app.py`)
- Celery Beat: планировщик (в т.ч. `celery_sqlalchemy_scheduler`)
- PostgreSQL 15 + Redis 7 + Flower

**Note:** Отдельные цели `make celery-maintenance`, `celery-async` и т.д. — для **разнесённых** воркеров локально; в дефолтном `docker-compose.yml` все перечисленные очереди обслуживает один worker.

### Deploy in 3 Steps

```bash
# 1. Copy and configure environment (из каталога backend/)
cd backend && cp .env.example .env
# В .env: SECURITY_JWT_SECRET_KEY (≥32), SECURITY_ENCRYPTION_KEY (Fernet), пароль БД.
# Для корневого compose: имя БД leap_platform (как в docker-compose.yml) и пароль **DB_PASSWORD** на хосте (подставляется в POSTGRES_PASSWORD и в сервисы).

# 2. Из корня репозитория — сборка и запуск
cd .. && docker compose up --build -d
# Продакшен: переопределите сервисы api/celery_* и передайте SECURITY_ENCRYPTION_KEY и прочие секреты (в базовом compose они не перечислены полностью).

# 3. Verify (из корня)
docker compose ps
curl http://localhost:8000/api/v1/health
```

**Monitoring:** http://localhost:5555 (Flower)

---

## 📋 Содержание

1. [Development Setup](#development-setup)
2. [Production Infrastructure](#production-infrastructure)
3. [Configuration](#configuration)
4. [Monitoring](#monitoring)

---

## Development Setup

### Requirements

- **Python 3.14+** (Python 3.14-slim in Docker)
- **PostgreSQL 15+** (using postgres:15-alpine)
- **Redis 7+** (using redis:7-alpine)
- **FFmpeg** (required for video processing)
- **UV** (Python package manager, recommended for local dev)

### Quick Start (Local Development)

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Start PostgreSQL & Redis via Docker
make docker-up

# Initialize database
make init-db

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run services (команды из каталога backend/)
make api              # API server (dev mode with reload)
make celery-dev       # Один воркер + встроенный beat: очереди processing_cpu, async_operations, downloads, uploads, maintenance

# Или разнести воркеры (как в проде / BATCH_TESTING)
make celery-downloads
make celery-uploads
make celery-async     # только async_operations (транскрипт, темы, субтитры, run, sync, automation — см. api/celery_app.py)
make celery-cpu       # только processing_cpu (trim)
make celery-maintenance  # только maintenance (периодические maintenance.*)
make celery-beat      # планировщик (отдельный процесс)

# macOS + Homebrew: фоновый запуск всех воркеров (поднимает Redis через brew services)
make celery-start

# Если Redis уже есть (например после make docker-up из корня) — можно не вызывать brew: закомментируйте/адаптируйте или запускайте воркеры вручную целями выше
```

### Makefile Commands

See `make help` for complete list. Key commands:
- `make api` / `make api-prod` - Start API server
- `make celery-start` / `make celery-stop` - Manage all workers
- `make celery-status` - Check worker status
- `make flower` - Start monitoring UI (port 5555)
- `make init-db` - Create database and run migrations
- `make test` - Run tests

---

## Production Infrastructure

### Recommended: Hetzner CPX31

```
Provider:   Hetzner Cloud
Model:      CPX31
vCPU:       8 (AMD EPYC)
RAM:        16 GB
Storage:    160 GB NVMe SSD
Bandwidth:  20 TB/month
Cost:       €26/month (~$28)
```

**Capacity:** 10-20 users, 5-10 videos per user per day

### OS Setup

```bash
# Ubuntu 24.04 LTS (recommended)
apt update && apt upgrade -y

# Install Docker
apt install -y docker.io docker-compose-v2

# Install system dependencies
apt install -y ffmpeg postgresql-client redis-tools

# Security
ufw enable
ufw allow 22,80,443/tcp

# Add user to docker group (optional)
usermod -aG docker $USER
```

### Docker Images Used

**Production containers:**
- **API & Workers:** Python 3.14-slim (built from Dockerfile)
- **PostgreSQL:** postgres:15-alpine
- **Redis:** redis:7-alpine

**Dockerfile overview:**
```dockerfile
FROM python:3.11-slim

# System dependencies: gcc, postgresql-client, ffmpeg
RUN apt-get update && apt-get install -y gcc postgresql-client ffmpeg

# Python dependencies from requirements.txt
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create storage directory
RUN mkdir -p storage

# Entrypoint: database initialization + migration
ENTRYPOINT ["/entrypoint.sh"]

# Default command: start API
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Entrypoint behavior (`entrypoint.sh`):**
1. Wait for PostgreSQL to be ready
2. Create database if not exists (using async Python)
3. Run Alembic migrations (`alembic upgrade head`)
4. Execute the provided command (API, worker, beat, etc.)

**Important:** The entrypoint ensures database is ready before starting services. It uses environment variables from docker-compose (DATABASE_HOST, DATABASE_PORT, etc.).

---

### Service Configuration

**Complete `docker-compose.yml`** (current production config):

#### PostgreSQL 15

```yaml
postgres:
  image: postgres:15-alpine
  container_name: leap_postgres
  environment:
    POSTGRES_DB: leap_platform
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: ${DB_PASSWORD:-postgres}
  volumes:
    - postgres_data:/var/lib/postgresql/data
  ports:
    - "5432:5432"
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres"]
    interval: 10s
    timeout: 5s
    retries: 5
```

**Note:** Database name is `leap_platform` in docker-compose. For local dev, you can use `zoom_manager` (configured via `DATABASE_DATABASE` env var).

**Production PostgreSQL tuning** (add to postgresql.conf):
```ini
shared_buffers = 1GB
effective_cache_size = 3GB
work_mem = 16MB
maintenance_work_mem = 256MB
max_connections = 100
```

#### Redis 7

```yaml
redis:
  image: redis:7-alpine
  container_name: leap_redis
  ports:
    - "6379:6379"
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 5
```

**Production Redis config** (add to command):
```yaml
command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

#### API (FastAPI)

```yaml
api:
  build: .
  container_name: leap_api
  command: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
  environment:
    DATABASE_HOST: postgres
    DATABASE_PORT: 5432
    DATABASE_DATABASE: leap_platform
    DATABASE_USERNAME: postgres
    DATABASE_PASSWORD: ${DB_PASSWORD:-postgres}
    CELERY_BROKER_URL: redis://redis:6379/0
    CELERY_RESULT_BACKEND: redis://redis:6379/0
    SECURITY_JWT_SECRET_KEY: ${SECURITY_JWT_SECRET_KEY:-${JWT_SECRET_KEY:-docker-compose-dev-jwt-secret-min-32-characters}}
  ports:
    - "8000:8000"
  volumes:
    - ./backend/storage:/app/storage
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
```

**Important:** Use structured environment variables (DATABASE_HOST, DATABASE_PORT, etc.) instead of DATABASE_URL.

#### Celery Worker

**Пример worker (согласован с корневым `docker-compose.yml`, монорепо):**
```yaml
celery_worker:
  build:
    context: ./backend
    dockerfile: Dockerfile
  container_name: leap_celery_worker
  command: python -m celery -A api.celery_app worker --loglevel=info --queues=downloads,uploads,async_operations,processing_cpu,maintenance --concurrency=8
  environment:
    DATABASE_HOST: postgres
    DATABASE_PORT: 5432
    DATABASE_DATABASE: leap_platform
    DATABASE_USERNAME: postgres
    DATABASE_PASSWORD: ${DB_PASSWORD:-postgres}
    CELERY_BROKER_URL: redis://redis:6379/0
    CELERY_RESULT_BACKEND: redis://redis:6379/0
  volumes:
    - ./backend/storage:/app/storage
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
```

**✅ Альтернативы масштабирования (опционально):**

**Option 1: Single worker (simpler, but not optimal):**
```yaml
celery_worker:
  command: python -m celery -A api.celery_app worker --loglevel=info --queues=processing_cpu,async_operations --concurrency=10
```

**Option 2: Specialized workers (RECOMMENDED for production):**
```yaml
# CPU worker (video trimming only)
celery_cpu:
  build: .
  container_name: leap_celery_cpu
  command: celery -A api.celery_app worker -Q processing_cpu --pool=prefork --concurrency=3 --max-tasks-per-child=20 --loglevel=info
  environment:
    # ... same as above ...
  volumes:
    - ./backend/storage:/app/storage
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy

# Async worker (all I/O operations)
celery_async:
  build: .
  container_name: leap_celery_async
  command: celery -A api.celery_app worker -Q async_operations --pool=threads --concurrency=20 --loglevel=info
  environment:
    # ... same as above ...
  volumes:
    - ./backend/storage:/app/storage
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
```

**Очереди (фактическая маршрутизация в `api/celery_app.py`):**
- **`downloads`** — `download_recording` (сеть, источники)
- **`uploads`** — `api.tasks.upload.*` (выгрузка на платформы)
- **`async_operations`** — транскрипт, темы, субтитры, `run_recording`, `launch_uploads`, `api.tasks.template.*`, `api.tasks.sync.*`, задачи `automation.*`
- **`processing_cpu`** — только `trim_video` (FFmpeg)
- **`maintenance`** — задачи `maintenance.*` (очистка токенов, истечение записей, файлы, hard delete по расписанию из `beat_schedule`)

В корневом **`docker-compose.yml`** один процесс воркера слушает все пять очередей (`--queues=downloads,uploads,async_operations,processing_cpu,maintenance`, `--concurrency=8`).

#### Celery Beat (Scheduler)

```yaml
celery_beat:
  build: .
  container_name: leap_celery_beat
  command: celery -A api.celery_app beat --loglevel=info --scheduler celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler
  environment:
    DATABASE_HOST: postgres
    DATABASE_PORT: 5432
    DATABASE_DATABASE: leap_platform
    DATABASE_USERNAME: postgres
    DATABASE_PASSWORD: ${DB_PASSWORD:-postgres}
    CELERY_BROKER_URL: redis://redis:6379/0
    CELERY_RESULT_BACKEND: redis://redis:6379/0
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
```

#### Flower (Monitoring)

В репозитории Flower запускается **без** `entrypoint.sh` (ожидание Postgres), иначе контейнер зависнет — см. сервис `flower` в корневом `docker-compose.yml` (`entrypoint: ["python", "-m", "celery"]`, `command: ["-A", "api.celery_app", "flower", "--port=5555"]`).

Упрощённый пример для своего compose:

```yaml
flower:
  build:
    context: ./backend
    dockerfile: Dockerfile
  entrypoint: ["python", "-m", "celery"]
  command: ["-A", "api.celery_app", "flower", "--port=5555"]
  environment:
    CELERY_BROKER_URL: redis://redis:6379/0
    CELERY_RESULT_BACKEND: redis://redis:6379/0
  ports:
    - "5555:5555"
  depends_on:
    - redis
```

#### Volumes and Networks

```yaml
volumes:
  postgres_data:
    driver: local

networks:
  default:
    name: leap_network
```

---

## Configuration

### Important Notes

**Celery (корневой `docker-compose.yml`, монорепо):** worker по умолчанию слушает очереди
`downloads,uploads,async_operations,processing_cpu,maintenance` (один процесс, `python -m celery`). Для продакшена при необходимости разнесите воркеры по очередям (ориентир — цели `celery-*` в `backend/Makefile`).

**Database Name Discrepancy:**
- `docker-compose.yml` uses: `leap_platform` (PostgreSQL container env)
- `.env.example` default: `zoom_manager` (application legacy name)
- **Solution:** Set `DATABASE_DATABASE=leap_platform` in `.env` when using Docker, or create `zoom_manager` database for local dev

**Environment Variables:**
- JWT: приложение читает **`SECURITY_JWT_SECRET_KEY`** (префикс `SECURITY_`). В корневом `docker-compose.yml` задано с подстановкой: сначала `SECURITY_JWT_SECRET_KEY`, иначе legacy **`JWT_SECRET_KEY`**, иначе dev-дефолт (≥32 символов для валидации).
- Пароль БД в compose: **`DB_PASSWORD`** (общий для Postgres и сервисов); в `.env` для локальной разработки см. **`DATABASE_PASSWORD`** / `.env.example`.

**Storage Paths:**
- Docker (монорепо): `./backend/storage:/app/storage` на хосте
- Local dev: каталог `storage/` под `backend/` (см. `STORAGE_LOCAL_PATH` в `config/settings.py`, по умолчанию `storage`)

**Container Names:**
All containers use `leap_` prefix:
- `leap_postgres` (PostgreSQL)
- `leap_redis` (Redis)
- `leap_api` (FastAPI)
- `leap_celery_worker` (Celery worker)
- `leap_celery_beat` (Celery Beat)
- `leap_flower` (Flower monitoring)

### Environment Variables

Configuration uses **structured prefixes** (APP_, SERVER_, DATABASE_, etc.). See `.env.example` for complete reference.

#### Core Settings

```bash
# Application
APP_DEBUG=false
APP_TIMEZONE=Europe/Moscow

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
SERVER_WORKERS=4
SERVER_RELOAD=false  # true for development

# Database (PostgreSQL)
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_DATABASE=zoom_manager  # or leap_platform for docker
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=your_secure_password_here
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Celery (auto-constructed from Redis settings if not set)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_WORKER_CONCURRENCY=8
```

#### Security Settings

```bash
# JWT Authentication
SECURITY_JWT_SECRET_KEY=your-super-secret-jwt-key-min-32-characters-change-me-in-production
SECURITY_JWT_ALGORITHM=HS256
SECURITY_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
SECURITY_JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Password Hashing
SECURITY_BCRYPT_ROUNDS=12  # 4 for dev, 12 for production

# Encryption (Fernet key for sensitive data)
SECURITY_ENCRYPTION_KEY=  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Rate Limiting
SECURITY_RATE_LIMIT_ENABLED=true
SECURITY_RATE_LIMIT_PER_MINUTE=60
SECURITY_RATE_LIMIT_PER_HOUR=1000
```

#### Storage Settings

```bash
# Storage backend: LOCAL or S3
STORAGE_TYPE=LOCAL

# LOCAL Storage
STORAGE_LOCAL_PATH=storage
STORAGE_LOCAL_MAX_SIZE_GB=1000  # optional, unlimited if not set

# S3 Storage (if STORAGE_TYPE=S3)
STORAGE_S3_BUCKET=my-bucket
STORAGE_S3_PREFIX=storage
STORAGE_S3_REGION=us-east-1
STORAGE_S3_ACCESS_KEY_ID=your-key
STORAGE_S3_SECRET_ACCESS_KEY=your-secret
STORAGE_S3_ENDPOINT_URL=  # optional, for S3-compatible services
STORAGE_S3_MAX_SIZE_GB=5000  # optional

# File limits
STORAGE_MAX_UPLOAD_SIZE_MB=5000
STORAGE_MAX_THUMBNAIL_SIZE_MB=10
```

#### Logging Settings

```bash
LOGGING_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOGGING_STRUCTURED=false  # true for JSON logging
LOGGING_INCLUDE_TRACE_ID=true
```

#### Monitoring Settings

```bash
MONITORING_ENABLED=false  # enable for production
MONITORING_SENTRY_DSN=  # optional, for error tracking
MONITORING_SENTRY_ENVIRONMENT=production
MONITORING_PROMETHEUS_ENABLED=false
```

#### Feature Flags

```bash
# Processing features (all enabled by default)
FEATURE_AUTO_TRANSCRIPTION=true
FEATURE_AUTO_TOPIC_EXTRACTION=true
FEATURE_AUTO_SUBTITLE_GENERATION=true
FEATURE_AUTO_THUMBNAIL_GENERATION=false

# Automation
FEATURE_AUTOMATION_ENABLED=true
FEATURE_AUTOMATION_MAX_JOBS_PER_USER=10

# Admin features
FEATURE_ADMIN_API_ENABLED=true
FEATURE_USER_STATS_ENABLED=true
```

#### Processing Settings

```bash
# Silence detection
PROCESSING_SILENCE_THRESHOLD=-40.0
PROCESSING_MIN_SILENCE_DURATION=2.0
PROCESSING_PADDING_BEFORE=5.0
PROCESSING_PADDING_AFTER=5.0

# Trimming
PROCESSING_REMOVE_INTRO=true
PROCESSING_REMOVE_OUTRO=true
PROCESSING_INTRO_DURATION=30.0
PROCESSING_OUTRO_DURATION=30.0

# Cleanup
PROCESSING_KEEP_TEMP_FILES=false
```

#### Retention Policy

```bash
RETENTION_SOFT_DELETE_DAYS=3    # Days before file cleanup after deletion
RETENTION_HARD_DELETE_DAYS=30   # Days before DB removal
RETENTION_AUTO_EXPIRE_DAYS=90   # Days before auto-expiration
```

#### Legacy Variables (backward compatibility)

```bash
# Старые имена там, где они ещё встречаются (compose / внешние скрипты).
# Для самого приложения JWT задаётся как SECURITY_JWT_SECRET_KEY (≥32 символов).
# В корневом docker-compose.yml legacy JWT_SECRET_KEY подставляется в SECURITY_JWT_SECRET_KEY.
DB_PASSWORD=your_secure_password_here   # в compose часто прокидывается как POSTGRES_PASSWORD
LOG_LEVEL=INFO
TIMEZONE=Europe/Moscow
```

### OAuth Configuration

OAuth credentials can be configured via:
1. **Environment variables** (recommended for production)
2. **JSON files** in `config/` directory (legacy method)

#### Environment Variables (Recommended)

```bash
# Base URL for callbacks
OAUTH_BASE_URL=http://localhost:8000

# YouTube OAuth
OAUTH_YOUTUBE_ENABLED=true
OAUTH_YOUTUBE_CLIENT_ID=xxx.apps.googleusercontent.com
OAUTH_YOUTUBE_CLIENT_SECRET=xxx
OAUTH_YOUTUBE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/youtube/callback

# VK OAuth
OAUTH_VK_ENABLED=true
OAUTH_VK_CLIENT_ID=xxx
OAUTH_VK_CLIENT_SECRET=xxx
OAUTH_VK_REDIRECT_URI=http://localhost:8000/api/v1/oauth/vk/callback

# Zoom OAuth
OAUTH_ZOOM_ENABLED=true
OAUTH_ZOOM_CLIENT_ID=xxx
OAUTH_ZOOM_CLIENT_SECRET=xxx
OAUTH_ZOOM_REDIRECT_URI=http://localhost:8000/api/v1/oauth/zoom/callback
```

#### JSON Files (Legacy, still supported)

```bash
# config/oauth_google.json (YouTube)
{
  "client_id": "xxx.apps.googleusercontent.com",
  "client_secret": "xxx",
  "redirect_uri": "https://yourdomain.com/api/v1/oauth/youtube/callback"
}

# config/oauth_vk.json (VK Video)
{
  "app_id": "xxx",
  "client_secret": "xxx",
  "redirect_uri": "https://yourdomain.com/api/v1/oauth/vk/callback"
}
```

**See [OAUTH.md](OAUTH.md) for detailed setup guides.**

### Database Migrations

```bash
# Initialize database (create DB + run migrations)
make init-db

# Or manually:
# 1. Create database
python -c "
import asyncio
from database.config import DatabaseConfig
from database.manager import DatabaseManager

async def init():
    db = DatabaseManager(DatabaseConfig.from_env())
    await db.create_database_if_not_exists()
    await db.close()

asyncio.run(init())
"

# 2. Run migrations
alembic upgrade head

# Create admin user (if needed)
# Note: User management is done via API, no utility script currently
```

#### Migration Commands

```bash
make migrate          # Apply pending migrations
make migrate-down     # Rollback last migration
make migration        # Create new migration (auto-generate)
make db-version       # Show current DB version
make db-history       # Show migration history
```

---

## Monitoring

### Health Checks

```bash
# API health endpoint
curl http://localhost:8000/api/v1/health

# Expected response:
# {"status": "OK", "service": "LEAP API"}

# Celery worker status
make celery-status

# Or manually:
celery -A api.celery_app inspect active
celery -A api.celery_app inspect stats
celery -A api.celery_app inspect registered
```

### Flower Monitoring UI

```bash
# Start Flower (web UI for Celery monitoring)
make flower

# Access at: http://localhost:5555

# In Docker:
docker-compose up -d flower
```

**Flower provides:**
- Real-time task monitoring
- Worker status and stats
- Task history and results
- Queue lengths
- Worker resource usage

### Logs

```bash
# Docker logs
docker-compose logs -f api
docker-compose logs -f celery_worker
docker-compose logs -f celery_beat
docker-compose logs -f flower

# Follow all services
docker-compose logs -f

# Application logs (local development)
tail -f logs/app.log
tail -f logs/celery-cpu.log
tail -f logs/celery-async.log
tail -f logs/celery-maintenance.log
tail -f logs/celery-beat.log

# Error logs
tail -f logs/error.log
```

### Resource Monitoring

```bash
# Docker container stats
docker stats

# PostgreSQL monitoring
docker exec leap_postgres psql -U postgres -d leap_platform -c "
  SELECT pid, state, query_start, wait_event_type, query
  FROM pg_stat_activity
  WHERE state != 'idle'
  ORDER BY query_start;
"

# Check database size
docker exec leap_postgres psql -U postgres -c "
  SELECT pg_database.datname,
         pg_size_pretty(pg_database_size(pg_database.datname)) AS size
  FROM pg_database
  ORDER BY pg_database_size(pg_database.datname) DESC;
"

# Redis monitoring
docker exec leap_redis redis-cli INFO memory
docker exec leap_redis redis-cli INFO stats

# Check queue lengths
docker exec leap_redis redis-cli LLEN celery

# Disk usage (Docker)
docker exec leap_api df -h /app/storage
docker exec leap_api du -sh /app/storage/*

# Disk usage (local)
df -h storage/
du -sh storage/users/*
```

### Performance Metrics

```bash
# Check slow queries (PostgreSQL)
docker exec leap_postgres psql -U postgres -c "
  SELECT query, calls, total_time, mean_time
  FROM pg_stat_statements
  ORDER BY mean_time DESC
  LIMIT 10;
"

# Note: requires pg_stat_statements extension
# Enable with: CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

---

## Backup Strategy

### Database Backups

```bash
# PostgreSQL backup (Docker)
docker exec leap_postgres pg_dump -U postgres leap_platform | gzip > backup_$(date +%Y%m%d).sql.gz

# Local PostgreSQL backup
pg_dump -U postgres zoom_manager | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore from backup
gunzip -c backup_20260205.sql.gz | docker exec -i leap_postgres psql -U postgres leap_platform

# Backup to remote location (example with S3)
docker exec leap_postgres pg_dump -U postgres leap_platform | gzip | aws s3 cp - s3://my-bucket/backups/db_$(date +%Y%m%d).sql.gz
```

### Media Files Backup

```bash
# Backup storage directory (Docker)
tar -czf storage_backup_$(date +%Y%m%d).tar.gz -C . storage/

# Backup storage directory (local)
tar -czf storage_backup_$(date +%Y%m%d).tar.gz -C . storage/

# Incremental backup with rsync
rsync -avz --delete storage/ backup-server:/backups/storage/

# Backup to S3 (if STORAGE_TYPE=LOCAL)
aws s3 sync storage/ s3://my-bucket/storage-backups/ --exclude "temp/*"
```

### Automated Backup Script

```bash
#!/bin/bash
# /opt/backup.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR="/backups"
RETENTION_DAYS=7

# Database backup
docker exec leap_postgres pg_dump -U postgres leap_platform | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Media backup
tar -czf "$BACKUP_DIR/storage_$DATE.tar.gz" -C /path/to/project storage/

# Remove old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $DATE"
```

**Cron schedule (daily at 3 AM):**
```bash
0 3 * * * /opt/backup.sh >> /var/log/backup.log 2>&1
```

### Backup Retention Policy

- **Daily backups**: Keep 7 days
- **Weekly backups**: Keep 4 weeks
- **Monthly backups**: Keep 6 months
- **Critical data**: Replicate to remote location

### Restore Procedure

```bash
# 1. Stop services
docker-compose stop api celery_worker celery_beat

# 2. Restore database
gunzip -c backup_20260205.sql.gz | docker exec -i leap_postgres psql -U postgres leap_platform

# 3. Restore storage files
tar -xzf storage_backup_20260205.tar.gz

# 4. Restart services
docker-compose start api celery_worker celery_beat

# 5. Verify
curl http://localhost:8000/api/v1/health
```

---

## SSL/HTTPS (Production)

### Option 1: Nginx + Let's Encrypt (Recommended)

#### Install Nginx

```bash
apt update
apt install -y nginx certbot python3-certbot-nginx
```

#### Configure Nginx

```nginx
# /etc/nginx/sites-available/leap-api

# HTTP (will be redirected to HTTPS)
server {
    listen 80;
    server_name api.yourdomain.com;

    # Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL certificates (will be added by certbot)
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    # Max upload size (adjust for large videos)
    client_max_body_size 5000M;

    # API proxy
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Timeouts for long-running requests
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }

    # Flower monitoring (optional, secure with auth)
    location /flower/ {
        proxy_pass http://localhost:5555/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;

        # Basic auth for Flower
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

#### Enable site and get certificate

```bash
# Enable site
ln -s /etc/nginx/sites-available/leap-api /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Get SSL certificate
certbot --nginx -d api.yourdomain.com

# Test renewal
certbot renew --dry-run

# Auto-renewal (already enabled by default)
systemctl status certbot.timer
```

### Option 2: Docker + Nginx + Let's Encrypt

#### docker-compose.yml with Nginx

```yaml
version: '3.8'

services:
  # ... (existing services)

  nginx:
    image: nginx:alpine
    container_name: leap_nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certbot/conf:/etc/letsencrypt:ro
      - ./certbot/www:/var/www/certbot:ro
    depends_on:
      - api
    restart: unless-stopped

  certbot:
    image: certbot/certbot
    container_name: leap_certbot
    volumes:
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

#### Get certificate (first time)

```bash
# Create certbot directories
mkdir -p certbot/conf certbot/www

# Get certificate
docker-compose run --rm certbot certonly --webroot \
  --webroot-path=/var/www/certbot \
  --email admin@yourdomain.com \
  --agree-tos \
  --no-eff-email \
  -d api.yourdomain.com

# Restart nginx
docker-compose restart nginx
```

### Option 3: Cloudflare (Easiest)

**Benefits:**
- Free SSL/TLS
- Built-in CDN
- DDoS protection
- Automatic certificate renewal

**Setup:**
1. Add domain to Cloudflare
2. Point DNS to your server
3. Enable "Full (strict)" SSL mode
4. Enable "Always Use HTTPS"
5. Optional: Enable HTTP/3

**Cloudflare Origin Certificate:**
```bash
# Download certificate from Cloudflare dashboard
# Add to nginx or docker-compose
```

### Security Best Practices

#### Firewall Configuration

```bash
# Allow only necessary ports
ufw enable
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP (for Let's Encrypt)
ufw allow 443/tcp  # HTTPS
ufw status
```

#### SSH Hardening

```bash
# Disable root login
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

# Disable password authentication (use SSH keys)
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# Restart SSH
systemctl restart sshd
```

#### Fail2ban

```bash
# Install fail2ban
apt install -y fail2ban

# Configure
cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
EOF

# Start fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

### Update OAuth Redirect URIs

After setting up HTTPS, update OAuth redirect URIs:

```bash
# Update .env
OAUTH_BASE_URL=https://api.yourdomain.com
OAUTH_YOUTUBE_REDIRECT_URI=https://api.yourdomain.com/api/v1/oauth/youtube/callback
OAUTH_VK_REDIRECT_URI=https://api.yourdomain.com/api/v1/oauth/vk/callback
OAUTH_ZOOM_REDIRECT_URI=https://api.yourdomain.com/api/v1/oauth/zoom/callback

# Restart services
docker-compose restart api
```

**Also update in OAuth provider dashboards:**
- Google Cloud Console (YouTube)
- VK Developers (VK Video)
- Zoom App Marketplace

### Testing

```bash
# Test SSL configuration
curl -I https://api.yourdomain.com

# Check SSL grade
# Visit: https://www.ssllabs.com/ssltest/analyze.html?d=api.yourdomain.com

# Test certificate renewal
certbot renew --dry-run
```

---

## Scaling

### Current Architecture (10-20 users)

**Типичный compose:** один контейнер API (4 воркера Uvicorn) + **один** Celery worker на всех пяти очередях + Beat + Flower — см. корневой `docker-compose.yml`.

**Расширение (как в `backend/Makefile`):** отдельные процессы на `downloads` / `uploads` / `async_operations` / `processing_cpu` / `maintenance` с разным pool/concurrency.

**Resources:** Hetzner CPX31 (8 vCPU, 16GB RAM)

**Очереди:** `downloads`, `uploads`, `async_operations`, `processing_cpu`, `maintenance` — назначение см. раздел *Queue Configuration* выше.

### Vertical Scaling (20-50 users)

**Upgrade server:**
- Model: Hetzner CPX41
- vCPU: 16
- RAM: 32GB
- Storage: 240GB NVMe SSD

**Increase workers:**
```yaml
# docker-compose.yml adjustments
api:
  command: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 8

celery_worker:
  command: python -m celery -A api.celery_app worker --loglevel=info --queues=downloads,uploads,async_operations,processing_cpu,maintenance --concurrency=16
```

**Or tune existing workers:**
```bash
# CPU worker: increase from 3 to 6 for more parallel video processing
celery -A api.celery_app worker -Q processing_cpu --pool=prefork --concurrency=6

# Async worker: increase from 20 to 40 for more concurrent I/O operations
celery -A api.celery_app worker -Q async_operations --pool=threads --concurrency=40
```

**Important:** В коде маршрутизации задач используются очереди `downloads`, `uploads`, `async_operations`, `processing_cpu`, `maintenance` (см. `api/celery_app.py`).

**Database tuning:**
```ini
# postgresql.conf
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 32MB
maintenance_work_mem = 512MB
max_connections = 200
```

### Horizontal Scaling (50+ users)

**Multi-server architecture:**

#### Load Balancer (nginx)
```nginx
upstream api_backend {
    server api1:8000;
    server api2:8000;
    server api3:8000;
}

server {
    listen 80;
    location / {
        proxy_pass http://api_backend;
    }
}
```

#### Dedicated Celery Workers

**Server 1: API + Beat**
- 8 API workers
- 1 Celery Beat scheduler

**Server 2-3: Celery Workers**
- 6-8 CPU workers (video trimming, queue: `processing_cpu`)
- 40-60 Async workers (all I/O operations, queue: `async_operations`)

**Shared Services:**
- PostgreSQL: Dedicated server or managed service (AWS RDS, DigitalOcean Managed DB)
- Redis: Dedicated server with Redis Sentinel for HA

#### PostgreSQL High Availability

**Option 1: Read Replicas**
```python
# In settings.py, add read replica URL
DATABASE_REPLICA_URL = "postgresql://user:pass@replica-host/db"

# Use for read-only queries
```

**Option 2: Managed PostgreSQL**
- AWS RDS PostgreSQL
- DigitalOcean Managed Database
- Google Cloud SQL
- Azure Database for PostgreSQL

#### Redis High Availability

**Redis Sentinel:**
```yaml
# docker-compose.yml
redis_master:
  image: redis:7-alpine

redis_sentinel:
  image: redis:7-alpine
  command: redis-sentinel /etc/redis/sentinel.conf
```

**Or managed Redis:**
- AWS ElastiCache
- Redis Cloud
- DigitalOcean Managed Redis

### Storage Scaling

#### S3 Storage Backend

**Enable S3 in `.env`:**
```bash
STORAGE_TYPE=S3
STORAGE_S3_BUCKET=my-bucket
STORAGE_S3_REGION=us-east-1
STORAGE_S3_ACCESS_KEY_ID=xxx
STORAGE_S3_SECRET_ACCESS_KEY=xxx
```

**Benefits:**
- Unlimited storage
- No disk space management
- Geographic distribution
- Built-in CDN (via CloudFront)

**Cost comparison (example):**
- Local storage: $0.10-0.20/GB/month (server disk)
- S3 Standard: $0.023/GB/month
- S3 Intelligent-Tiering: $0.023/GB/month (auto-optimization)

#### CDN for Media Delivery

**CloudFront + S3:**
```bash
# S3 bucket for storage
aws s3 mb s3://my-media-bucket

# CloudFront distribution for delivery
aws cloudfront create-distribution --origin-domain-name my-media-bucket.s3.amazonaws.com
```

### Monitoring at Scale

**Prometheus + Grafana:**
```yaml
# docker-compose.yml
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
```

**Sentry for error tracking:**
```bash
MONITORING_ENABLED=true
MONITORING_SENTRY_DSN=https://xxx@sentry.io/xxx
MONITORING_SENTRY_ENVIRONMENT=production
```

**Custom metrics:**
- Task processing time
- Queue lengths
- API response times
- Upload success rates
- Storage usage per user

### Cost Optimization

**Current setup (10-20 users):**
- Hetzner CPX31: €26/month
- Total: **~$30/month**

**Scaled setup (50-100 users):**
- 3x Hetzner CPX41: €69/month each = €207/month
- Managed PostgreSQL: $50/month
- Managed Redis: $30/month
- S3 Storage (1TB): $23/month
- CloudFront CDN: $50/month
- Total: **~$400/month**

**Optimization tips:**
- Use S3 Intelligent-Tiering for automatic cost optimization
- Enable S3 Lifecycle policies (move to Glacier after 90 days)
- Use spot instances for non-critical workers
- Implement aggressive caching (Redis)
- Compress videos before upload
- Enable auto-scaling for workers

---

## Troubleshooting

### High Memory Usage

```bash
# Check container resource usage
docker stats

# Check specific container
docker stats leap_celery_worker

# Inspect worker memory
docker exec leap_celery_worker ps aux --sort=-%mem | head -10

# Check for memory leaks in Celery
docker logs leap_celery_worker | grep -i "memory\|oom"

# Restart services
docker-compose restart celery_worker

# Local: Restart all workers
make celery-restart
```

**Common causes:**
- Too many concurrent tasks (reduce CELERY_WORKER_CONCURRENCY)
- Memory leaks in FFmpeg processes
- Large video files in memory
- Old tasks not cleaned up

**Solutions:**
- Increase `--max-tasks-per-child` (default: 50)
- Monitor with Flower: http://localhost:5555
- Add memory limits to docker-compose.yml
- Clear old task results: `celery -A api.celery_app purge`

### Slow Queries

```bash
# Enable slow query log (PostgreSQL)
docker exec leap_postgres psql -U postgres -c "
  ALTER SYSTEM SET log_min_duration_statement = 1000;  -- 1 second
  SELECT pg_reload_conf();
"

# View slow queries in logs
docker logs leap_postgres | grep "duration:"

# Check currently running queries
docker exec leap_postgres psql -U postgres -c "
  SELECT pid, now() - query_start AS duration, state, query
  FROM pg_stat_activity
  WHERE state != 'idle' AND now() - query_start > interval '1 second'
  ORDER BY duration DESC;
"

# Kill long-running query (if needed)
docker exec leap_postgres psql -U postgres -c "SELECT pg_terminate_backend(PID);"

# Analyze query performance
docker exec leap_postgres psql -U postgres -c "EXPLAIN ANALYZE <your_query>;"
```

**Common causes:**
- Missing indexes
- Large table scans
- Inefficient joins
- Too many concurrent connections

**Solutions:**
- Add indexes to frequently queried columns
- Optimize queries with EXPLAIN ANALYZE
- Increase `shared_buffers` and `work_mem`
- Use connection pooling (already enabled via SQLAlchemy)

### Disk Full

```bash
# Check disk usage
docker exec leap_api df -h
du -sh storage/*
du -sh storage/*

# Clean temp files (safe)
find storage/temp -name "*" -mtime +1 -delete
# Or in Docker:
docker exec leap_api find /app/storage/temp -name "*" -mtime +1 -delete

# Clean old processed audio files (created during transcription)
find storage/users/*/recordings/*/processed_audio.wav -mtime +7 -delete

# Clean old transcription files (if not needed)
find storage/users/*/recordings/*/transcription.json -mtime +30 -delete

# Clean old logs
find logs/ -name "*.log" -mtime +30 -delete

# Clean Docker volumes (DANGEROUS - removes all data!)
# docker-compose down -v  # ⚠️ Use with caution!
```

**⚠️ IMPORTANT - User Data:**
```bash
# DO NOT delete user recordings without permission
# Recordings are managed by retention policy (RETENTION_* settings)

# Soft-deleted recordings cleanup (automated via maintenance worker)
# After RETENTION_SOFT_DELETE_DAYS (default: 3 days), files are deleted
# After RETENTION_HARD_DELETE_DAYS (default: 30 days), DB records are deleted

# Manual cleanup of soft-deleted recordings (use with caution)
# This should be handled by the maintenance worker automatically
```

### Celery Workers Not Processing Tasks

```bash
# Check worker status
make celery-status

# Check if workers are registered
celery -A api.celery_app inspect registered

# Check active tasks
celery -A api.celery_app inspect active

# Check queue lengths
docker exec leap_redis redis-cli LLEN celery

# Purge all tasks (DANGEROUS - removes all pending tasks!)
celery -A api.celery_app purge -f

# Restart workers
docker-compose restart celery_worker celery_beat

# Or locally:
make celery-restart
```

**Common causes:**
- Workers crashed or stopped
- Redis connection issues
- Database connection pool exhausted
- Task timeout (default: 3600s = 1 hour)

**Solutions:**
- Check logs: `docker logs leap_celery_worker`
- Increase connection pool: `DATABASE_POOL_SIZE=30`
- Increase task timeout: `CELERY_TASK_TIME_LIMIT=7200`
- Monitor with Flower: http://localhost:5555

### API Not Responding

```bash
# Check API status
curl http://localhost:8000/api/v1/health

# Check API logs
docker logs leap_api -f

# Check if API is running
docker ps | grep leap_api

# Restart API
docker-compose restart api

# Check database connection
docker exec leap_postgres psql -U postgres -l

# Check Redis connection
docker exec leap_redis redis-cli ping
```

**Common causes:**
- Database connection pool exhausted
- Too many concurrent requests
- Unhandled exceptions
- Worker blocking event loop (if using async incorrectly)

**Solutions:**
- Increase workers: `SERVER_WORKERS=8`
- Increase connection pool: `DATABASE_POOL_SIZE=30`
- Enable rate limiting: `SECURITY_RATE_LIMIT_ENABLED=true`
- Check logs for errors

### FFmpeg Errors

```bash
# Check FFmpeg installation
docker exec leap_celery_worker ffmpeg -version

# Test FFmpeg
docker exec leap_celery_worker ffmpeg -i /app/storage/test.mp4 -f null -

# Common FFmpeg errors:
# - "Invalid data found": Corrupted video file
# - "No such file": File path incorrect
# - "Permission denied": Volume mount issue

# Check file permissions
docker exec leap_celery_worker ls -la /app/storage/
```

### Redis Connection Errors

```bash
# Check Redis status
docker exec leap_redis redis-cli ping

# Check Redis connections
docker exec leap_redis redis-cli CLIENT LIST

# Check Redis memory
docker exec leap_redis redis-cli INFO memory

# Flush Redis (removes all cached data and task results)
docker exec leap_redis redis-cli FLUSHALL  # ⚠️ Use with caution!
```

### Database Connection Pool Exhausted

```bash
# Check active connections
docker exec leap_postgres psql -U postgres -c "
  SELECT count(*), state
  FROM pg_stat_activity
  GROUP BY state;
"

# Kill idle connections
docker exec leap_postgres psql -U postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE state = 'idle' AND state_change < now() - interval '10 minutes';
"
```

**Solutions:**
- Increase pool size: `DATABASE_POOL_SIZE=30`
- Increase max_connections in PostgreSQL: `max_connections=200`
- Check for connection leaks in code

---

## Additional Resources

### API Documentation

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI Schema:** http://localhost:8000/openapi.json

### Monitoring & Admin Tools

- **Flower (Celery Monitoring):** http://localhost:5555
- **Health Check:** http://localhost:8000/api/v1/health
- **API Status:** http://localhost:8000/api/v1/admin/status (requires admin auth)

### Credentials Management

Учётные данные платформ задаются через **REST API** (см. OpenAPI http://localhost:8000/docs): регистрация/логин, затем эндпоинты credentials/OAuth для Zoom, YouTube, VK, Fireworks, DeepSeek и т.д. Данные в БД хранятся в зашифрованном виде (Fernet).

**Security:**
- Credentials are encrypted using Fernet (AES-128 CBC)
- Set `SECURITY_ENCRYPTION_KEY` in `.env` (generate with `Fernet.generate_key()`)
- See [CREDENTIAL_SECURITY.md](CREDENTIAL_SECURITY.md) for key rotation and troubleshooting InvalidToken
- Never commit `.env` or credential files to git

### OAuth Setup

See [OAUTH.md](OAUTH.md) for detailed OAuth 2.0 setup guides:
- YouTube OAuth 2.0 flow
- VK OAuth (Implicit Flow)
- Zoom OAuth setup
- Multiple accounts per platform

### Configuration Reference

All settings are environment-driven via `.env` file. Configuration uses structured prefixes:
- `APP_*` - Application settings (debug, timezone)
- `SERVER_*` - Server settings (host, port, workers)
- `DATABASE_*` - PostgreSQL settings
- `REDIS_*` - Redis settings
- `CELERY_*` - Celery task queue settings
- `SECURITY_*` - Security settings (JWT, encryption, rate limiting)
- `STORAGE_*` - Storage backend settings (LOCAL/S3)
- `LOGGING_*` - Logging configuration
- `MONITORING_*` - Monitoring and observability
- `OAUTH_*` - OAuth configuration
- `FEATURE_*` - Feature flags
- `PROCESSING_*` - Video processing settings
- `RETENTION_*` - Data retention policy

See `.env.example` for complete reference with all available variables.

### Further Reading

**Core Documentation:**
- [README.md](../../../README.md) — обзор продукта (корень репозитория)
- [backend/README.md](../../README.md) — быстрый старт API из каталога `backend/`
- [INDEX.md](../INDEX.md) - Documentation map and developer entry points
- [CHANGELOG.md](../CHANGELOG.md) - Version history and changes

**Technical Documentation:**
- [TECHNICAL.md](../TECHNICAL.md) — архитектура, модули и справка по API (детали эндпоинтов — OpenAPI `/docs`)
- [DATABASE_DESIGN.md](../DATABASE_DESIGN.md) - Database schema and models

**Feature Documentation:**
- [TEMPLATES.md](TEMPLATES.md) - Template system and presets
- [TEMPLATES_PRESETS_SOURCES_GUIDE.md](TEMPLATES_PRESETS_SOURCES_GUIDE.md) - Complete guide
- [OAUTH.md](OAUTH.md) - OAuth integration

**Celery & Workers:**
- [CELERY_WORKERS_GUIDE.md](CELERY_WORKERS_GUIDE.md) - Worker architecture and queues
- [CELERY_ASYNCIO_TECHNICAL.md](CELERY_ASYNCIO_TECHNICAL.md) - Async I/O implementation
- [AUTOMATION_CELERY_BEAT.md](AUTOMATION_CELERY_BEAT.md) - Automation and scheduling

**Storage:**
- [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md) - File organization
- [S3_INTEGRATION_TODO.md](../dev_notes/S3_INTEGRATION_TODO.md) - S3 backend implementation

**Other:**
- [tests/ROADMAP.md](../../tests/ROADMAP.md) - Testing roadmap & plans

### Project Structure

Исходный код API и документация для разработчиков: каталог **`backend/`** (там же `Makefile`, `pyproject.toml`, `alembic/`, `docs/`). Корень монорепозитория: **`docker-compose.yml`**, корневой **`Makefile`** (Docker), **`README.md`** с обзором продукта.

### Getting Help

- **Documentation:** [INDEX.md](../INDEX.md) (все гайды под `backend/docs/`)
- **API Reference:** http://localhost:8000/docs

### Ориентиры по стеку

- **Обновление гайда:** 2026-04-18
- **Python:** 3.14+ (в Docker — образ `python:3.14-slim-bookworm` в `backend/Dockerfile`)
- **PostgreSQL:** 15 (образ `postgres:15-alpine` в корневом compose)
- **Redis:** 7
- **Очереди Celery:** `downloads`, `uploads`, `async_operations`, `processing_cpu`, `maintenance` — назначение задаётся в `api/celery_app.py`

---

## Quick Reference

### Essential Commands

```bash
# Development
make api                  # Start API (dev mode with reload)
make celery-dev          # Один процесс: worker (5 очередей) + встроенный beat — см. backend/Makefile
make docker-up           # Start PostgreSQL + Redis
make init-db             # Initialize database

# Production
make api-prod            # Start API (production mode)
make celery-start        # Start all workers (background)
make celery-stop         # Stop all workers
make celery-restart      # Restart all workers
make celery-status       # Check worker status

# Docker
docker-compose up -d     # Start all services
docker-compose down      # Stop all services
docker-compose ps        # Check service status
docker-compose logs -f   # Follow logs

# Database
make migrate             # Apply migrations
make migration           # Create new migration
make db-version          # Show current version

# Monitoring
make flower              # Start Flower UI (port 5555)
make celery-status       # Worker status
curl http://localhost:8000/api/v1/health  # Health check

# Testing
make test                # Run all tests
make tests-mock          # Unit tests only
make tests-quality       # Code quality checks

# Quality
make lint                # Check code
make lint-fix            # Auto-fix issues
make format              # Format code
make typecheck           # Type checking
```

### Important URLs

- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/api/v1/health
- **Flower Monitoring:** http://localhost:5555
- **ReDoc:** http://localhost:8000/redoc

### Key Files

- **Configuration:** `.env` (copy from `.env.example`)
- **Settings:** `config/settings.py` (Pydantic settings with backward compatibility)
- **Docker:** корневой `docker-compose.yml`, `backend/Dockerfile`, `backend/entrypoint.sh`
- **Celery:** `api/celery_app.py` (маршрутизация по пяти очередям, см. выше)
- **Database:** `alembic/versions/` (migrations)
- **OAuth Examples:** `config/examples/oauth_google.json.example`, `config/examples/oauth_vk.json.example`
- **Documentation:** `backend/docs/`

### Environment Variables Quick Reference

```bash
# Minimal production setup (docker-compose)
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_DATABASE=leap_platform  # Must match docker-compose.yml
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=xxx
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Security (JWT в приложении только SECURITY_*; JWT_SECRET_KEY — для подстановки в compose, см. docker-compose.yml)
SECURITY_JWT_SECRET_KEY=xxx-min-32-chars
SECURITY_ENCRYPTION_KEY=xxx-fernet-key    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Troubleshooting Quick Fixes

```bash
# Workers not processing
make celery-restart

# Database connection issues
docker-compose restart postgres

# Clear all tasks
celery -A api.celery_app purge -f

# Reset everything (DANGEROUS!)
docker-compose down -v && docker-compose up -d

# Check logs
docker logs leap_celery_worker -f
docker logs leap_api -f
```

### Production Checklist

- [ ] Проверить очереди Celery в compose / Makefile (в корневом `docker-compose.yml` для worker: `downloads,uploads,async_operations,processing_cpu,maintenance`)
- [ ] Set `APP_DEBUG=false`
- [ ] Задать **`SECURITY_JWT_SECRET_KEY`** (≥32 символов); **`JWT_SECRET_KEY`** — только при подстановке в compose (см. корневой `docker-compose.yml`)
- [ ] Set `DATABASE_PASSWORD` or `DB_PASSWORD` (strong password)
- [ ] Set `DATABASE_DATABASE=leap_platform` in `.env` to match docker-compose
- [ ] Generate `SECURITY_ENCRYPTION_KEY` (Fernet: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- [ ] Configure OAuth redirect URIs (HTTPS) - must use `/api/v1/oauth/{platform}/callback`
- [ ] Enable rate limiting (`SECURITY_RATE_LIMIT_ENABLED=true`)
- [ ] Configure backups (database + storage)
- [ ] Set up monitoring (Sentry, Prometheus)
- [ ] Configure SSL/HTTPS (Let's Encrypt or Cloudflare)
- [ ] Set up firewall (ufw allow 22,80,443/tcp)
- [ ] Configure log rotation
- [ ] Test disaster recovery procedure
- [ ] Verify Celery workers are processing tasks: `celery -A api.celery_app inspect active`

---

## License

[Business Source License 1.1](../../LICENSE)

## Support

For issues and questions:
- **Documentation:** `backend/docs/` ([INDEX.md](../INDEX.md))
- **API Reference:** http://localhost:8000/docs
