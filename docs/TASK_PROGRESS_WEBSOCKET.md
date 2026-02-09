# Task Progress: Real-Time Updates via SSE

## Problem

Currently, clients poll `GET /api/v1/tasks/{task_id}` to check Celery task progress. This approach:

- Wastes bandwidth and server resources with repeated requests
- Introduces latency (progress updates only visible on next poll)
- Requires clients to manage polling intervals and backoff logic
- Scales poorly as number of concurrent tasks grows

## Solution Options

### WebSocket

**Pros:** Full-duplex, low latency, client can send messages too.
**Cons:** Requires dedicated connection management, harder to pass through HTTP proxies/CDNs, more complex reconnection logic, heavier server-side state.

### Server-Sent Events (SSE)

**Pros:** Simple HTTP-based protocol, works through all proxies/CDNs, automatic reconnection built into `EventSource` API, lightweight, one-directional (which is exactly what we need for progress).
**Cons:** Unidirectional (server -> client only), limited to text data (no binary).

## Recommended Approach: SSE

SSE is the right fit because:

1. **One-directional** -- we only push progress from server to client
2. **HTTP native** -- works through Nginx, Cloudflare, any reverse proxy
3. **Auto-reconnect** -- `EventSource` API handles reconnection with `Last-Event-ID`
4. **Simple** -- no special protocol negotiation or frame parsing

## Architecture

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│  Browser  │────▶│  FastAPI SSE │◀────│  Redis       │◀────│  Celery     │
│  (client) │ SSE │  endpoint    │ Sub │  Pub/Sub     │ Pub │  Worker     │
└──────────┘     └──────────────┘     └─────────────┘     └─────────────┘
```

### Components

1. **Celery Worker** -- publishes progress events to Redis channel during task execution
2. **Redis Pub/Sub** -- message broker for real-time event distribution
3. **FastAPI SSE Endpoint** -- subscribes to Redis channel, streams events to client via `StreamingResponse`
4. **Browser Client** -- connects via `EventSource`, receives progress updates

### Redis Channel Naming

```
task_progress:{user_id}:{task_id}
```

Per-user channels ensure tenant isolation. A wildcard subscription `task_progress:{user_id}:*` allows listening to all tasks for a user.

## Event Format

Events follow the SSE specification with JSON payloads:

```
id: evt_001
event: progress
data: {"task_id": "abc-123", "progress": 45, "stage": "transcribing", "message": "Transcribing audio...", "updated_at": "2025-01-15T10:30:00Z"}

id: evt_002
event: progress
data: {"task_id": "abc-123", "progress": 100, "stage": "completed", "message": "Processing complete", "updated_at": "2025-01-15T10:31:00Z"}

id: evt_003
event: error
data: {"task_id": "abc-123", "stage": "failed", "error": "Transcription service unavailable", "updated_at": "2025-01-15T10:31:05Z"}
```

### Event Types

| Event    | Description                          |
|----------|--------------------------------------|
| progress | Task progress update (0-100%)        |
| complete | Task completed successfully          |
| error    | Task failed with error details       |
| heartbeat| Keep-alive ping (every 30s)          |

### Payload Fields

| Field       | Type     | Description                           |
|-------------|----------|---------------------------------------|
| task_id     | string   | Celery task ID                        |
| progress    | int      | Progress percentage (0-100)           |
| stage       | string   | Current processing stage              |
| message     | string   | Human-readable status message         |
| updated_at  | datetime | Timestamp of this update              |
| error       | string   | Error message (only for error events) |
| result      | object   | Task result (only for complete events)|

## Endpoint Design

```
GET /api/v1/tasks/stream?task_ids=abc-123,def-456
Authorization: Bearer <token>
Accept: text/event-stream
```

### Query Parameters

| Parameter | Type   | Description                                          |
|-----------|--------|------------------------------------------------------|
| task_ids  | string | Comma-separated task IDs to subscribe to (optional)  |
| all       | bool   | Subscribe to all tasks for current user (default: false) |

### Response Headers

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

## FastAPI Implementation Sketch

```python
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import redis.asyncio as redis
import json
import asyncio

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


@router.get("/stream")
async def stream_task_progress(
    task_ids: str | None = Query(None, description="Comma-separated task IDs"),
    current_user = Depends(get_current_user),
):
    """Stream real-time task progress via SSE."""

    async def event_generator():
        r = redis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()

        # Subscribe to specific tasks or all user tasks
        if task_ids:
            channels = [f"task_progress:{current_user.id}:{tid}" for tid in task_ids.split(",")]
        else:
            channels = [f"task_progress:{current_user.id}:*"]
            await pubsub.psubscribe(*channels)
            channels = None  # flag for psubscribe mode

        if channels:
            await pubsub.subscribe(*channels)

        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] in ("message", "pmessage"):
                    data = json.loads(message["data"])
                    event_type = data.pop("event_type", "progress")
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

                    # Close stream if all tasks completed
                    if event_type in ("complete", "error") and task_ids:
                        break
                else:
                    # Heartbeat every 30s
                    yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.utcnow().isoformat()})}\n\n"
                    await asyncio.sleep(1)
        finally:
            await pubsub.unsubscribe()
            await r.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

## Celery Worker Integration

Add progress publishing to existing Celery tasks:

```python
import redis
import json
from datetime import datetime, UTC


def publish_progress(task_id: str, user_id: str, progress: int, stage: str, message: str = ""):
    """Publish task progress event to Redis Pub/Sub."""
    r = redis.from_url(settings.REDIS_URL)
    channel = f"task_progress:{user_id}:{task_id}"
    payload = {
        "event_type": "progress",
        "task_id": task_id,
        "progress": progress,
        "stage": stage,
        "message": message,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    r.publish(channel, json.dumps(payload))


# Usage in Celery task:
@celery_app.task(bind=True)
def process_recording_task(self, recording_id: int, user_id: str):
    publish_progress(self.request.id, user_id, 0, "started", "Processing started")

    # ... download step ...
    publish_progress(self.request.id, user_id, 20, "downloading", "Downloading recording")

    # ... transcription step ...
    publish_progress(self.request.id, user_id, 50, "transcribing", "Transcribing audio")

    # ... upload step ...
    publish_progress(self.request.id, user_id, 80, "uploading", "Uploading to platform")

    # ... done ...
    publish_progress(self.request.id, user_id, 100, "completed", "Processing complete")
```

## Client Example (JavaScript)

```javascript
function subscribeToTask(taskId, onProgress, onComplete, onError) {
  const token = getAuthToken();
  const url = `/api/v1/tasks/stream?task_ids=${taskId}`;

  const eventSource = new EventSource(url, {
    headers: { Authorization: `Bearer ${token}` }
  });

  eventSource.addEventListener('progress', (event) => {
    const data = JSON.parse(event.data);
    onProgress(data);
    // data.progress = 0..100, data.stage, data.message
  });

  eventSource.addEventListener('complete', (event) => {
    const data = JSON.parse(event.data);
    onComplete(data);
    eventSource.close();
  });

  eventSource.addEventListener('error', (event) => {
    if (event.data) {
      const data = JSON.parse(event.data);
      onError(data);
    }
    eventSource.close();
  });

  eventSource.addEventListener('heartbeat', () => {
    // Connection alive, no action needed
  });

  // Built-in reconnection on network failure
  eventSource.onerror = () => {
    console.log('SSE connection lost, auto-reconnecting...');
  };

  return eventSource; // caller can call .close() to unsubscribe
}

// Usage:
const stream = subscribeToTask(
  'abc-123',
  (data) => updateProgressBar(data.progress, data.message),
  (data) => showSuccess('Task completed!'),
  (data) => showError(data.error)
);
```

> **Note:** Standard `EventSource` does not support custom headers. For auth,
> either pass the token as a query param (`?token=...`) or use a polyfill like
> [eventsource](https://www.npmjs.com/package/eventsource) / `fetch` with
> `ReadableStream`.

## Connection Lifecycle

```
Client                        Server                        Redis
  |                             |                             |
  |-- GET /tasks/stream ------->|                             |
  |                             |-- SUBSCRIBE channel ------->|
  |                             |                             |
  |<---- event: heartbeat ------|                             |
  |                             |<---- message (progress) ----|
  |<---- event: progress -------|                             |
  |                             |<---- message (progress) ----|
  |<---- event: progress -------|                             |
  |                             |<---- message (complete) ----|
  |<---- event: complete -------|                             |
  |                             |-- UNSUBSCRIBE ------------->|
  |-- connection closed ------->|                             |
```

## Reconnection Strategy

1. `EventSource` auto-reconnects on network failure (default ~3s)
2. Server sends `id:` with each event for `Last-Event-ID` header on reconnect
3. Server checks `Last-Event-ID` and replays missed events from a short Redis buffer (optional, for reliability)
4. Heartbeat every 30s prevents proxy/load-balancer timeouts
5. Client-side: if `EventSource` enters permanent error state, fall back to polling

## Deployment Considerations

- **Nginx:** Set `proxy_buffering off;` and `proxy_read_timeout 3600s;` for SSE endpoints
- **Cloudflare:** SSE works out of the box; ensure the endpoint is not cached
- **Connection limits:** Each SSE connection holds a socket; monitor with `ulimit` / connection pool settings
- **Scaling:** Redis Pub/Sub works across multiple FastAPI instances naturally (all subscribe to same Redis)

## Migration Path

1. Implement SSE endpoint alongside existing `GET /tasks/{task_id}` polling
2. Add `publish_progress()` calls to Celery tasks incrementally
3. UI adopts SSE for real-time updates, with polling as fallback
4. Eventually deprecate polling endpoint for tasks that support SSE
