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
- Public subtitle/transcript file routes return a short-lived `302` to a signed Object Storage URL on S3. Local storage still returns file bytes through the API. Signing does not check S3 object existence first; a stale database artifact can therefore redirect to an Object Storage 404. Download requests require `allow_files_download`; only `inline=true` for VTT subtitles bypasses that setting for the player. Media download URLs require `allow_video_download`.

## MP4 requirements

- New MP4/MOV/M4V outputs use FFmpeg `-movflags +faststart`, so the `moov` index (file table of contents) is placed before `mdat` (media bytes). Safari otherwise often requests `Range: 0–end` of a large file.
- `-avoid_negative_ts make_zero` normalizes negative timestamps.
- Uploads set a MIME type from the object suffix; `.mp4` must be stored as `video/mp4`. `application/octet-stream` makes WebKit treat the object as an opaque blob.

Faststart does not shrink a large `moov` atom. Stream-copy trim may still wait for the next source keyframe. HLS is a later step if progressive MP4 is not enough on slow links.

## Player recovery

The shared player has a 20-second metadata startup timeout and, while a visible tab or active PiP is playing, a 30-second no-progress timeout. `waiting` / `stalled` alone do not fail playback: Safari may fire `stalled` when the buffer is full. Native media errors or the no-progress timeout request a fresh signed URL. A new URL does not replace a playing `<video>`; it is used only for recovery after a failure. Recovery remounts the media element, seeks to the current position (including the last five seconds), and tries to continue playback. At most two automatic recoveries happen without sustained progress, avoiding an endless loop for a missing object; Manual Retry remains available. The client also requests a new URL shortly before expiry, retrying a failed refresh up to three times.

Switching tabs does not pause playback. The player suspends its startup and no-progress timers while the tab is hidden, except that an active PiP keeps the no-progress timer running. It saves position on `pagehide`. Ordinary return visits resume by recording ID and variant; playlist watch uses the playlist token, item ID, and variant. Near-end positions are ignored on a new visit. Manual Picture-in-Picture is available where the browser supports it (the custom control is hidden on narrow screens). Chromium may also request automatic PiP through the Media Session API for an audible playing video when its eligibility and site permissions allow it. The player does not force PiP on every tab switch; unsupported browsers keep normal background playback behavior. A Play or Next request in a playlist follows the selected item and waits for its media element to mount before attempting playback; browser autoplay policy may still reject it.

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
- Short buffering must not replace the player with Retry. A visible, playing tab or active PiP with no position progress for 30 seconds requests a fresh URL and restores playback. An expired or invalid media URL triggers the same recovery on `error`; if recovery fails, Retry remains available.
- Switching tabs preserves playback and pauses the client timeout clocks except for active PiP's no-progress timer. Check manual PiP and, where supported and permitted, browser-requested automatic PiP on desktop. Check playlist Play and Next after a cold load.
- A removed, blank, or unprocessed playlist item returns 404 from its direct watch, media, and file endpoints, while the catalog still lists it as unavailable.
- `async_operations`, `maintenance`, and temporary `celery` queue depths are monitored during rollout.

See also [MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md), [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md), and [CELERY_WORKERS_GUIDE.md](CELERY_WORKERS_GUIDE.md).
