# Video delivery and playback stability

This guide describes the path from opening a recording page to the first playable frame, plus recovery and operational checks. The API does not proxy video bytes: it authorizes access and returns a temporary Object Storage URL.

## Request path

```text
recording/share page
  ├─ recording metadata API ───────────────┐
  └─ media API (started in parallel)       ├─ render player
       └─ presigned Object Storage URL ────┘
            └─ browser Range requests → MP4 bytes
```

- Authenticated and public share pages begin fetching the media URL while their metadata loads.
- Storage checks for video, audio and subtitles are concurrent, avoiding serial Object Storage round trips.
- Presigned URLs live for 60 minutes. The client cache treats them as stale after 50 minutes, leaving time to refresh before expiry.
- The browser reads media directly from Object Storage with HTTP Range requests; API memory and bandwidth are not on the media path.

## MP4 requirements

- New MP4/MOV/M4V outputs use FFmpeg `-movflags +faststart`, so the `moov` index (file table of contents) is placed before `mdat` (media bytes). Safari otherwise often requests `Range: 0–end` of a large file.
- `-avoid_negative_ts make_zero` normalizes negative timestamps.
- Uploads set a MIME type from the object suffix; `.mp4` must be stored as `video/mp4`. `application/octet-stream` makes WebKit treat the object as an opaque blob.

Faststart does not shrink a large `moov` atom. Stream-copy trim may still wait for the next source keyframe. HLS is a later step if progressive MP4 is not enough on slow links.

## Player recovery

The shared player times out only until the first playable frame. After `playing`, `waiting` / `stalled` are treated as buffering (Safari fires `stalled` when the buffer is full and the download pauses). A signed URL is refreshed once on native media `error`. Retry remounts the `<video>` element. Position is stored by recording ID and variant, never by a public share token.

## Existing-object backfill

Old objects (uploaded before MIME/faststart in the pipeline) are not updated automatically. Run from `backend/`. Dry-run is the default:

```bash
uv run python scripts/backfill_video_faststart.py
```

Canary one recording (for example 38), then all remaining processed and original `.mp4` keys:

```bash
uv run python scripts/backfill_video_faststart.py --apply --recording-id 38
uv run python scripts/backfill_video_faststart.py --apply
```

Apply mode sets `Content-Type: video/mp4` in place when HEAD is wrong. For processed files that are not already `*.faststart.mp4`, it remuxes only when `moov` follows `mdat`, uploads a new object, and switches `processed_video_path`. The prior object is kept for rollback.

## Worker delivery guarantees

`api.tasks.processing.finalize_pipeline` is explicitly routed to `async_operations`; `celery.backend_cleanup` is routed to `maintenance`. Production temporarily consumes the legacy default `celery` queue as well, so messages published before the routing fix can drain. Queue metrics must include that legacy queue until it remains empty and the compatibility subscription is removed.

## Verification checklist

- Object metadata reports the expected video MIME type and accepts byte ranges.
- For MP4, the `moov` atom appears before `mdat`.
- Opening a recording triggers metadata and media requests together, followed by Object Storage range traffic.
- After playback has started, buffering must not replace the player with Retry. An expired or invalid media URL causes one refresh on `error`, then Retry remounts the element.
- `async_operations`, `maintenance`, and temporary `celery` queue depths are monitored during rollout.

See also [MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md), [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md), and [CELERY_WORKERS_GUIDE.md](CELERY_WORKERS_GUIDE.md).
