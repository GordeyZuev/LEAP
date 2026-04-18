---
name: leap-debug-pipeline
description: >-
  Debugs stuck or failed LEAP recording pipelines—Celery queues, pipeline
  stages, and log correlation. Use when a recording fails mid-flight, a Celery
  task errors, workers seem idle, or the user asks to trace download through
  upload.
---

# LEAP pipeline debugging

## Mental model

Stages (order may vary by config): **download → trim (FFmpeg) → transcribe → topics → subtitles → upload**. Work runs on **Celery** with queues such as `downloads`, `processing_cpu`, `async_operations`, `uploads`, `maintenance` (see `backend/Makefile` targets `celery-downloads`, `celery-cpu`, `celery-async`, `celery-uploads`, etc.).

## Logs (local)

| Log | Use |
|-----|-----|
| `backend/logs/app.log` | API, orchestration, many service errors |
| `backend/logs/celery-async.log` | `async_operations` worker (transcription, topics, async-side effects) |

Search by **recording id** (and task name if present). Do not paste secrets into chat.

## Workflow

1. **Confirm state** — recording row / API status / last known stage (from app or DB if the user has access).
2. **Map stage to queue** — e.g. trim → CPU queue; heavy I/O async → `async_operations`; platform upload → `uploads`.
3. **Scan the right log** for the recording id; note the **first** exception and stack trace.
4. **Classify**
   - **External API** (Zoom, Fireworks, VK, yt-dlp): rate limits, auth, payload — check creds and guides under `backend/docs/guides/`.
   - **DB / migration mismatch**: schema vs code — check `make db-version` vs expected head (see **`alembic-migrations.mdc`**).
   - **Worker not running**: task stays pending — confirm the matching worker process is up for that queue.
5. **Code path** — open the task module under `backend/api/tasks/` for the failing stage; follow imports; prefer fixing root cause over silencing errors.

## Do not

- Commit or log access tokens, refresh tokens, or API keys.
- Assume `async_operations` uses gevent — project Makefile documents **threads** for asyncio compatibility.
