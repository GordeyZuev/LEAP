# Celery Workers: Operations Guide

> **Quick Start**: `make celery-all` → запускает все workers
> **Technical Deep Dive**: См. [CELERY_ASYNCIO_TECHNICAL.md](CELERY_ASYNCIO_TECHNICAL.md)

## Overview

ZoomUploader использует специализированные Celery worker pools для оптимальной обработки разных типов задач. Каждый pool оптимизирован для конкретного паттерна работы.

**Workers:**
- **CPU pool** - video processing (prefork)
- **Async pool** - database + async I/O (threads)
- **Maintenance pool** - periodic cleanup (prefork)

## Worker Pools Architecture

### 1. CPU-Intensive Pool (`processing_cpu`)

**Queue**: `processing_cpu`
**Pool Type**: `prefork`
**Concurrency**: 3 workers
**Use Case**: CPU-bound операции (video processing)

```bash
make celery-cpu
```

**Задачи**:
- `api.tasks.processing.trim_video` - обрезка видео

**Почему prefork?**
- Реальный параллелизм через процессы
- Обходит Python GIL для CPU-bound задач
- Изоляция: сбой одной задачи не влияет на другие

**Scaling для production**:
```bash
# Увеличить на количество CPU cores
--concurrency=8  # для 8-core машины
```

---

### 2. Async Operations Pool (`async_operations`)

**Queue**: `async_operations`
**Pool Type**: `threads`
**Concurrency**: 20 threads
**Use Case**: All async I/O operations (database, API calls, uploads)

```bash
make celery-async
```

**Задачи (все async I/O):**
- `api.tasks.processing.*` - download, transcription, topics, subtitles
- `api.tasks.upload.*` - YouTube/VK uploads
- `api.tasks.template.*` - template matching, rematch
- `api.tasks.sync.*` - Zoom sync operations
- `automation.*` - automation tasks
- `maintenance.*` - cleanup operations

**Почему threads pool?**
- ✅ Полная совместимость с asyncio + asyncpg
- ✅ Хорошая concurrency для I/O (20 threads)
- ✅ Нет конфликтов с event loop

> **Техническая причина**: Gevent pool несовместим с asyncio (InterfaceError).
> **Детали**: См. [CELERY_ASYNCIO_TECHNICAL.md](CELERY_ASYNCIO_TECHNICAL.md)

**Scaling для production:**
```bash
# Увеличить threads для большего количества пользователей
--concurrency=30  # 100-300 users
--concurrency=50  # 300-500 users
```

---

### 3. Maintenance Pool (`maintenance`)

**Queue**: `maintenance`
**Pool Type**: `prefork`
**Concurrency**: 1 worker
**Use Case**: Periodic cleanup tasks

```bash
make celery-maintenance
```

**Задачи**:
- Token cleanup
- File cleanup
- Database cleanup

**Почему single worker?**
- Maintenance tasks должны выполняться последовательно
- Предотвращает race conditions

---

## Production Deployment

### Quick Start (All Workers)

```bash
# Запуск всех workers в background
make celery-all

# Проверка статуса
make celery-status

# Остановка всех
make celery-stop
```

**Запускаются:**
- `processing_cpu` (prefork, 3 workers)
- `async_operations` (threads, 20 workers)
- `maintenance` (prefork, 1 worker)
- `beat` (scheduler)

### Manual Start (для development)

```bash
# Терминал 1: CPU worker
make celery-cpu

# Терминал 2: Async worker (большинство задач)
make celery-async

# Терминал 3: Maintenance worker
make celery-maintenance

# Терминал 4: Beat scheduler
make celery-beat
```

---

## Scaling Recommendations

### Small Setup (1-50 users)
```
CPU:    3 workers (prefork)
Async:  10 threads
Maintenance: 1 worker
```

### Medium Setup (50-200 users)
```
CPU:    4 workers (prefork)
Async:  20 threads
Maintenance: 1 worker
```

### Large Setup (200-500 users)
```
CPU:    8 workers (prefork, max = CPU cores)
Async:  30-50 threads
Maintenance: 1 worker
```

### Very Large Setup (500+ users)
**Horizontal Scaling:**
```bash
# Несколько машин
# Machine 1: CPU worker (8 workers)
# Machine 2: Async worker (50 threads)
# Machine 3: Async worker (50 threads)  ← Дополнительная машина
# Machine 4: Maintenance + Beat
```

---

## Monitoring

### Flower UI
```bash
make flower
# Open: http://localhost:5555
```

### Check Active Tasks
```bash
make celery-status
```

### Clear All Queues
```bash
make celery-purge
```

---

## Best Practices

### 1. Task Routing
- CPU-intensive → `processing_cpu` (video processing)
- Async I/O → `async_operations` (database, API, uploads)
- Periodic cleanup → `maintenance`

### 2. Monitoring
- Use Flower для real-time monitoring
- Set up alerts for failed tasks
- Monitor queue lengths

### 3. Error Handling
- Use `max_retries` для transient errors
- Use `autoretry_for` для network errors
- Log all failures

### 4. Resource Management
- Set `max-tasks-per-child` для prefork (memory leaks)
- Monitor memory usage
- Scale horizontally when needed

---

## Troubleshooting

### Issue: Tasks не выполняются
**Проверить:**
```bash
make celery-status  # Запущены ли workers?
tail -f logs/celery-async.log  # Есть ли ошибки?
```

### Issue: Low throughput
**Cause**: Недостаточно workers
**Solution**: Увеличить `--concurrency` для async pool

### Issue: High memory usage
**Cause**: Слишком много concurrent workers
**Solution**: Уменьшить concurrency или добавить машины

### Issue: InterfaceError / asyncio errors
**Solution**: См. [CELERY_ASYNCIO_TECHNICAL.md](CELERY_ASYNCIO_TECHNICAL.md)

---

## Summary

| Pool | Queue | Type | Concurrency | Use Case |
|------|-------|------|-------------|----------|
| CPU | processing_cpu | prefork | 3 | Video processing |
| **Async** | **async_operations** | **threads** | **20** | **All async I/O** |
| Maintenance | maintenance | prefork | 1 | Cleanup tasks |

**Total Workers:** 3 pools, ~24 concurrent tasks

---

## Related Documentation

- **[CELERY_ASYNCIO_TECHNICAL.md](CELERY_ASYNCIO_TECHNICAL.md)** - Technical deep dive: asyncio + threads решение
- **[API_GUIDE.md](API_GUIDE.md)** - API endpoints и schemas
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment

---

**Last Updated**: 2026-01-24
**Status**: Production Ready
