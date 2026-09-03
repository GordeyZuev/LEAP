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

- New MP4/MOV/M4V outputs use FFmpeg `-movflags +faststart`, so the `moov` index is placed before `mdat` and playback can begin without downloading the tail first.
- `-avoid_negative_ts make_zero` normalizes negative timestamps.
- Uploads set a MIME type inferred from the object suffix; `.mp4` is stored as `video/mp4`.

Faststart is an optimization, not a fixed startup-time guarantee. It does not shrink a large `moov` atom. With stream-copy trimming, the first video frame may also wait for the next source keyframe. HLS or fragmented MP4 is the next step if a strict startup bound is required on slow links.

## Player recovery

The shared player handles initial-load timeout, media `error`, and `stalled` events. On failure it invalidates the cached URL and requests a new signed URL once. If recovery does not succeed, the UI stops the spinner, explains the problem and exposes Retry. Playback position is stored by recording ID and media variant; a public share token is never stored in the key.

## Existing-object backfill

Run from `backend/`. The command is dry-run by default and does not modify storage or the database:

```bash
uv run python scripts/backfill_video_faststart.py
```

Apply only after reviewing the dry-run:

```bash
uv run python scripts/backfill_video_faststart.py --apply
```

Apply mode downloads the current processed MP4, remuxes without re-encoding, verifies that `moov` precedes `mdat`, uploads a new `*.faststart.mp4` object, and conditionally updates the recording path. The prior object remains available for rollback. A concurrent path change prevents the database switch.

## Worker delivery guarantees

`api.tasks.processing.finalize_pipeline` is explicitly routed to `async_operations`; `celery.backend_cleanup` is routed to `maintenance`. Production temporarily consumes the legacy default `celery` queue as well, so messages published before the routing fix can drain. Queue metrics must include that legacy queue until it remains empty and the compatibility subscription is removed.

## Verification checklist

- Object metadata reports the expected video MIME type and accepts byte ranges.
- For MP4, the `moov` atom appears before `mdat`.
- Opening a recording triggers metadata and media requests together, followed by Object Storage range traffic.
- An expired or invalid media URL causes one refresh and then a visible Retry state, not an endless loader.
- `async_operations`, `maintenance`, and temporary `celery` queue depths are monitored during rollout.

See also [MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md), [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md), and [CELERY_WORKERS_GUIDE.md](CELERY_WORKERS_GUIDE.md).
