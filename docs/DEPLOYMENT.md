# 🚀 Deployment Guide

**Complete guide: development → production**

---

## ⚡ Quick Start (Updated 2026-01-18)

### Current Production Configuration

**Ready for 10 users (5-10 videos each):**
- API: 4 FastAPI workers
- Celery Worker: 8 concurrent tasks (increased from 4)
- Celery Beat: Scheduler for automation
- PostgreSQL + Redis + Flower monitoring

### Deploy in 3 Steps

```bash
# 1. Ensure .env has production secrets
# (DB_PASSWORD and JWT_SECRET_KEY are already set)

# 2. Build and start all services
docker-compose up --build -d

# 3. Verify
docker-compose ps
curl http://localhost:8000/health
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

- **Python 3.11+**
- **PostgreSQL 14+**
- **Redis 7+**
- **FFmpeg**

### Quick Start

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Setup database
createdb zoom_manager
alembic upgrade head

# Configure
cp config/settings.py.example config/settings.py
# Edit config/settings.py

# Run
make api        # API (port 8000)
make worker     # Celery worker
make beat       # Celery beat
```

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

### OS Setup

```bash
# Ubuntu 24.04 LTS
apt update && apt upgrade -y
apt install -y docker.io docker-compose ffmpeg postgresql-client

# Security
ufw enable
ufw allow 22,80,443/tcp
```

---

### Service Configuration

#### PostgreSQL 15

```yaml
# docker-compose.yml
postgres:
  image: postgres:15-alpine
  environment:
    POSTGRES_DB: zoom_manager
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: ${DB_PASSWORD}
  volumes:
    - postgres_data:/var/lib/postgresql/data
  deploy:
    resources:
      limits:
        memory: 4G
```

**postgresql.conf:**
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
  command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
  deploy:
    resources:
      limits:
        memory: 2G
```

#### API (FastAPI)

```yaml
api:
  build: .
  command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
  deploy:
    resources:
      limits:
        memory: 4G
        cpus: "2"
  environment:
    DATABASE_URL: postgresql://postgres:${DB_PASSWORD}@postgres/zoom_manager
    REDIS_URL: redis://redis:6379
```

#### Celery Worker

```yaml
worker:
  build: .
  command: celery -A api.celery_app worker --loglevel=info --concurrency=4
  deploy:
    resources:
      limits:
        memory: 6G
        cpus: "4"
```

---

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/zoom_manager

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-fernet-key-here

# Storage
MEDIA_ROOT=/app/media
MAX_FILE_SIZE=10737418240  # 10GB

# API Keys
FIREWORKS_API_KEY=your-key
```

### OAuth Configuration

```bash
# config/oauth_google.json
{
  "client_id": "xxx.apps.googleusercontent.com",
  "client_secret": "xxx",
  "redirect_uri": "https://yourdomain.com/api/v1/oauth/youtube/callback"
}

# config/oauth_vk.json
{
  "app_id": "xxx",
  "client_secret": "xxx",
  "redirect_uri": "https://yourdomain.com/api/v1/oauth/vk/callback"
}
```

### Database Migrations

```bash
# Run migrations
alembic upgrade head

# Create superuser
python -m utils.create_test_user --email admin@example.com --is-admin
```

---

## Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Celery status
celery -A api.celery_app inspect active
```

### Logs

```bash
# Docker logs
docker-compose logs -f api
docker-compose logs -f worker

# Application logs
tail -f logs/api.log
tail -f logs/celery.log
```

### Resource Monitoring

```bash
# PostgreSQL
docker exec postgres psql -U postgres -c "
  SELECT pid, state, query_start, query 
  FROM pg_stat_activity 
  WHERE state != 'idle';
"

# Redis
docker exec redis redis-cli INFO memory

# Disk usage
df -h /app/media
```

---

## Backup Strategy

```bash
# PostgreSQL backup (daily)
pg_dump -U postgres zoom_manager | gzip > backup_$(date +%Y%m%d).sql.gz

# Media files backup (weekly)
tar -czf media_backup_$(date +%Y%m%d).tar.gz /app/media

# Retention: 7 daily, 4 weekly
```

---

## SSL/HTTPS (Production)

```bash
# Install certbot
apt install -y certbot python3-certbot-nginx

# Get certificate
certbot --nginx -d yourdomain.com

# Auto-renewal
systemctl enable certbot.timer
```

---

## Scaling (10+ users)

### Vertical Scaling
- Upgrade to CPX41 (16 vCPU, 32GB RAM)
- Increase worker concurrency: `--concurrency=8`

### Horizontal Scaling
- Add dedicated Celery workers
- Redis Sentinel for HA
- PostgreSQL read replicas

---

## Troubleshooting

### High Memory Usage

```bash
# Check processes
docker stats

# Restart services
docker-compose restart worker
```

### Slow Queries

```bash
# Enable slow query log
ALTER SYSTEM SET log_min_duration_statement = 1000;  # 1 second
SELECT pg_reload_conf();

# View slow queries
tail -f /var/log/postgresql/postgresql-15-main.log | grep "duration:"
```

### Disk Full

```bash
# Clean old temp files
find /app/storage/temp -name "*" -mtime +1 -delete

# Clean old recordings (if needed)
find /app/storage/users/user_*/recordings/*/video.mp4 -mtime +30 -delete

# Clean old thumbnails (users manage their own, be careful)
find /app/storage/users/user_*/thumbnails -mtime +90 -delete
```

---

## Additional Resources

**API Setup:**

All API credentials are managed through the web interface at http://localhost:8000:
1. Register/login
2. Navigate to Credentials section  
3. Add credentials for Zoom, YouTube, VK, Fireworks AI, DeepSeek
4. All credentials are encrypted (Fernet) and stored in database

**OAuth Setup:**

See [OAUTH.md](OAUTH.md) for detailed OAuth 2.0 guides:
- YouTube OAuth flow
- VK OAuth (Implicit Flow)
- Zoom OAuth setup

**Configuration:**

All settings are environment-driven via `.env` file. See `.env.example` for available variables.

**Further Reading:**
- [OAUTH.md](OAUTH.md) - OAuth integration guide
- [TECHNICAL.md](TECHNICAL.md) - Technical documentation
- [TEMPLATES.md](TEMPLATES.md) - Template system
- [README.md](../README.md) - Project overview

