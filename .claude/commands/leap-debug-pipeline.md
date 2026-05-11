# LEAP pipeline debugging

## Mental model

Stages (order may vary by config): **download → trim (FFmpeg) → transcribe → topics → subtitles → upload**.

Celery queues → make targets:

| Queue | Make target |
|-------|-------------|
| `downloads` | `celery-downloads` |
| `processing_cpu` | `celery-cpu` |
| `async_operations` | `celery-async` |
| `uploads` | `celery-uploads` |

## Logs (local)

| Log | Use |
|-----|-----|
| `backend/logs/app.log` | API, orchestration, many service errors |
| `backend/logs/celery-async.log` | `async_operations` worker (transcription, topics, async side-effects) |

Search by **recording id** (and task name if present). Do not paste secrets into chat.

## Debugging workflow

1. **Confirm state** — recording row / API status / last known stage (from app or DB if accessible).
2. **Map stage to queue** — e.g. trim → CPU queue; heavy I/O async → `async_operations`; platform upload → `uploads`.
3. **Scan the right log** for the recording id; note the **first** exception and stack trace.
4. **Classify the error:**
   - **External API** (Zoom, Fireworks, VK, yt-dlp): rate limits, auth, payload — check creds and `backend/docs/guides/`.
   - **DB / migration mismatch**: schema vs code — check `make db-version` vs expected head.
   - **Worker not running**: task stays pending — confirm the matching worker process is up for that queue.
5. **Code path** — open `backend/api/tasks/` for the failing stage; follow imports; prefer fixing root cause over silencing errors.

## Do not

- Commit or log access tokens, refresh tokens, or API keys.
- Assume `async_operations` uses gevent — project Makefile documents **threads** for asyncio compatibility.
