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

## Embedding a public recording

On the recording page, open **Publications → LEAP Link → Manage** (or **Create link**), enable the public link, then use **Embed player → Copy iframe code**. **Preview player** opens `/embed/{token}` in a new tab. Paste the copied HTML into a page that accepts iframe code. The default iframe is 560 × 350 pixels, including the video footer. **Chapters** opens a scrollable list with titles, timestamps, and preview frames when available; selecting a chapter seeks within the video. **Open in LEAP** opens the full recording page with transcript and files.

The embed uses the same share token and page-view beacon as `/share/{token}`. Recording analytics combine both surfaces and apply the existing 30-minute repeat-view rule. The number is **views**, not unique people or simultaneous viewers. Disabling the share link makes the embed unavailable; rotating the token invalidates old iframe code.

The iframe requests `view=player&embed=true`. Its response keeps the play URL, subtitle URL, title, and edited chapter timestamps, while skipping the file inventory, source attachments, and original-video presign. The optional `embed` flag is safe for an already open iframe when nginx rolls back to an older API: that API ignores the extra query parameter and returns the regular player payload. The iframe still has the checked API subtitle fallback when a browser cannot fetch the presigned VTT from Object Storage.

To authorize multiple websites, set Terraform `embed_allowed_origins` to their comma-separated exact HTTPS origins, for example `https://courses.example.edu,https://portal.example.org`, then apply, refresh the environment, and redeploy the frontend. The variable becomes `EMBED_ALLOWED_ORIGINS` in Compose. Use origins, not paths or wildcards. Next.js sends `Content-Security-Policy: frame-ancestors 'self' ...` only on `/embed/`; nginx omits `X-Frame-Options` only there. With an empty setting, embedding is limited to the LEAP origin. Every parent origin must be listed if a site nests frames. The host site must also permit external iframe HTML. Allowing arbitrary sites removes the browser's framing restriction and increases clickjacking and unwanted-republication risk, so keep an explicit list of trusted origins. See [DEPLOYMENT.md](DEPLOYMENT.md) for rollout details.

The embed is intentionally public to anyone holding its token. Keep the token out of private logs and rotate it if it has been exposed. Already issued media and preview URLs remain usable until their own short expiry even after the share link is disabled, as with ordinary shared video playback.

## Seek previews

A background CPU task extracts at most 300 frames, 320 × 180 pixels each, into up to three JPEG sprite sheets and a WebVTT index. FFprobe checks keyframe spacing first; when all gaps are within half a preview interval, FFmpeg decodes keyframes only. A sparse keyframe stream or failed probe falls back to full decoding, preserving useful seek images and the existing VTT timing. Short videos still produce one complete sprite sheet: FFmpeg pads the source at the end before sampling and fills unused cells with its last frame. The chapter list shows frames at 64 × 36; the seek tooltip is 144 × 81, so hover thumbnails remain sharp on high-density screens. Plyr's full-player scrubbing overlay is hidden because even these small frames would be blurry when stretched across the video. Video playback uses the processed source file without changing its resolution or bitrate.

After `TRIM`, a short step in the main Celery chain queues preview generation and lets transcription continue. FFmpeg runs on the separate `previews` queue and `celery_preview_worker` (one concurrent job by default). Generation requires `processed_video_path`; when trimming finds no cut to make, that path references the original file. The optional `PREVIEW_MAKER` stage is persisted in the separate `preview_maker_stages` table with status, source revision, timestamps, and failure reason. This avoids changing the required-stage enum or recording readiness; the stage is not shown in the UI. An old recording queues generation on first preview request. Both paths share one Redis queue lock, so opening the page while a new preview is pending does not schedule duplicate CPU work. If Redis is unavailable, no on-demand CPU work is queued and dispatch failure does not stop transcription. A running worker renews only its own lock every 30 seconds; the 65-minute TTL permits recovery after an interrupted worker. A delayed message can reclaim its own expired lock, but cannot take a newer claim. A failed build of the same source has a five-minute retry cooldown to prevent request-driven retry storms; `--force` on the local canary bypasses it. The generator probes the downloaded processed video for its actual duration before creating VTT cues and takes a 640-pixel-wide poster frame from its midpoint. It discards an index if the trim stage completes again during generation and queues a fresh attempt; view counters and metadata edits do not trigger regeneration. Publication of the poster and VTT is serialized with the recording's trim update. FFmpeg output is capped at the number of sheets needed by the VTT. FFmpeg extraction times out after at most 50 minutes, with an earlier deadline when the configured Celery soft limit is shorter; the poster extraction has a five-minute timeout. Timed-out child processes are killed and reaped. The preview task hard limit is at most 57.5 minutes, below the default one-hour Redis broker visibility timeout. Re-trimming invalidates the old index and poster before regeneration. Preview worker failures are visible as failed Celery tasks and `PREVIEW_MAKER` failures; they do not fail transcription. Missing previews never prevent playback: chapter markers and the full-page chapter list still work.

The VTT endpoint serves an existing object only when `PREVIEW_MAKER` is completed for the current processed video and trim revision; the sheet endpoint applies the same check. The comparison reads the current TRIM completion from the database in the same query as the preview stage, because public share and playlist lookups omit the `processing_stages` relationship. If old-object deletion fails during re-trim, VTT returns `202` and queues a forced rebuild instead of showing frames from the previous cut. A duplicate Celery delivery does not start another FFmpeg process or release the running worker's claim.

Beat checks preview recovery every 15 minutes. It retries a `FAILED` build after the five-minute cooldown, an `IN_PROGRESS` build older than 70 minutes, and a `PENDING` build older than 70 minutes only when the `previews` broker queue is empty. Each source revision gets at most three automatic attempts; the saved token and status prevent an old recovery pass from overwriting a newer run. Operators can use the local canary's `--force` option after investigating a persistent failure.

Sprite sheets and `storyboard.vtt` are stored under the recording's `previews/` prefix; the poster is stored beside the video as `poster.jpg`. For example, recording 2550 belonging to user slug 1 uses storage keys `users/user_000001/recordings/2550/previews/0.jpg`, `.../previews/storyboard.vtt`, and `.../poster.jpg`. The configured storage backend holds the artifacts (S3-compatible Object Storage in production, LOCAL in development); temporary downloads are removed after processing. A configured user cover still takes precedence over the generated poster.

The separately generated 640-pixel `poster.jpg` is used for recording and playlist cards when no configured cover takes precedence. The current `<video>` element does not set a poster image; the sprite frames are used only for seek hover and chapters. A large pre-play player cover would require a separate UI change and a suitable high-resolution image.

### Failure and retry boundaries

`PREVIEW_MAKER` is independent of transcription: a preview failure marks only its own stage and Celery task failed. Beat retries a completed FFmpeg failure after the five-minute cooldown, up to three attempts for the same source revision; a later VTT request can also enqueue an eligible attempt, and the local canary supports `--force`. A worker killed before it records failure can leave the stage `IN_PROGRESS`. Beat checks up to 25 candidates every 15 minutes and requeues those older than 70 minutes, after the task's hard limit. It removes only the old run's matching Redis claim and checks the old run token under the stage row lock before replacement. A concurrent successful or newer run cannot be overwritten. A long `PENDING` backlog stays queued; an old `PENDING` row is retried only when the broker queue is empty.

The preview artifacts and stage row are not one database transaction with Object Storage and Redis. The VTT is written last as the artifact completion marker, and readers also require a completed stage for the current trim revision. This prevents serving a partial or stale storyboard, but does not make queue publication, Object Storage writes, and the database update globally atomic. Under a crash, temporary or orphaned JPEGs may remain until a later regeneration; the video remains playable.

Each preview endpoint checks the current owner, share token, or playlist item before returning the VTT or a sheet. S3 sheets use short-lived signed URLs; LOCAL sheets are served by the checked route because the generic local storage endpoint requires owner login. Preview responses are browser-cacheable for one minute.

The browser may reuse a completed VTT request from cache when Plyr loads its hover frames. A `202` is not cached and triggers retries with a delay growing to 60 seconds for up to 65 minutes while the page stays open; hidden tabs do not poll and resume on visibility. The full share page still checks downloadable artifacts and source extras. The attachment manifest is read with one GET, without a preliminary HEAD; attachment checks share an S3 client and run with a maximum of eight concurrent object lookups. The playlist catalog poster endpoint loads only requested visible item IDs (up to 25), with tenant scoping and batched related data; it does not hydrate the whole 200-item playlist for each poster page.

## MP4 requirements

- New MP4/MOV/M4V outputs use FFmpeg `-movflags +faststart`, so the `moov` index (file table of contents) is placed before `mdat` (media bytes). Safari otherwise often requests `Range: 0–end` of a large file.
- `-avoid_negative_ts make_zero` normalizes negative timestamps.
- Uploads set a MIME type from the object suffix; `.mp4` must be stored as `video/mp4`. `application/octet-stream` makes WebKit treat the object as an opaque blob.

Faststart does not shrink a large `moov` atom. Stream-copy trim may still wait for the next source keyframe. HLS is a later step if progressive MP4 is not enough on slow links.

## Player recovery

The shared player has a 20-second metadata startup timeout and, while a visible tab or active PiP is playing, a 30-second no-progress timeout. `waiting` / `stalled` alone do not fail playback: Safari may fire `stalled` when the buffer is full. Native media errors or the no-progress timeout request a fresh signed URL. A new URL does not replace a playing `<video>`; it is used only for recovery after a failure. Recovery remounts the media element, seeks to the current position (including the last five seconds), and tries to continue playback. At most two automatic recoveries happen without sustained progress, avoiding an endless loop for a missing object; Manual Retry remains available. The client also requests a new URL shortly before expiry, retrying a failed refresh up to three times.

Switching tabs does not pause playback. The player suspends its startup and no-progress timers while the tab is hidden, except that an active PiP keeps the no-progress timer running. It saves position on `pagehide`. Ordinary return visits resume by recording ID and variant; playlist watch uses the playlist token, item ID, and variant. Near-end positions are ignored on a new visit. Manual Picture-in-Picture is available where the browser supports it (the custom control is hidden on narrow screens). Chromium may also request automatic PiP through the Media Session API for an audible playing video when its eligibility and site permissions allow it. The player does not force PiP on every tab switch; unsupported browsers keep normal background playback behavior. A Play or Next request in a playlist follows the selected item and waits for its media element to mount before attempting playback; browser autoplay policy may still reject it.

## Seek preview canary

To inspect or generate seek previews for one recording using the local `backend/.env` database and storage settings, run from the repository root with an existing recording ID:

```bash
backend/.venv/bin/python backend/scripts/generate_recording_previews.py 123
backend/.venv/bin/python backend/scripts/generate_recording_previews.py 123 --run
```

Inspection is read-only and reports source size and whether the VTT exists. `--run` acquires the same Redis lock as the worker, records `PREVIEW_MAKER` in the database, copies the processed video to temporary storage, runs FFmpeg, and writes the JPEG sheets and midpoint poster before the VTT completion marker. It skips an existing VTT; add `--force` to regenerate. Force mode removes the old VTT first, so preview requests may return 202 until regeneration finishes. Ensure Redis and temporary disk space for the full source video are available. The page needs a backend serving the current code to use the preview endpoints.

## Preview backfill for all existing recordings

After deploying the preview worker and migrations 061–062, run from `/opt/leap` on the VPS. The first command only scans active recordings with a processed video; the second queues all missing or stale previews:

```bash
docker compose exec -T celery_preview_worker python scripts/backfill_recording_previews.py
docker compose exec -T celery_preview_worker python scripts/backfill_recording_previews.py --run
```

For a long archive, keep the command running after disconnecting and inspect its log:

```bash
nohup docker compose exec -T celery_preview_worker python scripts/backfill_recording_previews.py --run \
  > backend/logs/preview-backfill.log 2>&1 < /dev/null &
tail -f backend/logs/preview-backfill.log
```

The backfill submits one recording to the existing `previews` Celery queue, waits for its `PREVIEW_MAKER` result and VTT, then submits the next. It never reruns trimming, transcription, or uploads. Completed current-source previews are skipped, and the database scan uses keyset pages. A failed or timed-out recording is printed and does not stop the rest; the command exits nonzero if any recording was not confirmed complete. Rerun the same command after a worker restart or other interruption: completed previews are skipped. `--limit N` inspects the first N processed recordings for a canary, and `--start-after ID` resumes beyond a known ID. The preview worker still needs temporary disk space for one whole processed video at a time.

The command prints `queued` or `already_active` before waiting, then the final result for that recording. On a 1-CPU worker, a measured 82-minute H.264 recording used about 7 seconds of wall time to probe keyframes and 11 seconds of CPU time to generate the JPEG sheets: roughly 13 CPU seconds per video hour for those steps. Midpoint poster extraction, S3 transfers, and queue wait add time. Videos with sparse keyframes use full decoding and can take several minutes.

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

`api.tasks.processing.enqueue_video_previews` runs on `async_operations` after `TRIM`; `api.tasks.processing.generate_video_previews` and the legacy on-demand `generate_poster` fallback run on `previews`. Beat publishes `maintenance.requeue_stale_video_previews` to `maintenance`. The fallback rechecks the source revision under the recording lock before saving its poster, so it cannot overwrite a poster after re-trimming. The preview worker must be healthy before the producer is deployed. `PREVIEW_WORKER_CONCURRENCY` (default 1), `PREVIEW_WORKER_CPUS` (default 1.0), and `PREVIEW_WORKER_MEMORY` (default 2G) control its capacity. Raise concurrency only after checking `celery_queue_length{queue="previews"}`, CPU, memory, and free temporary disk space: each job downloads a complete processed video.

Alembic revision `061` creates the optional `preview_maker_stages` table. Apply it before starting the new workers. Old API versions can continue to read recordings during the blue/green switch because their `processingstagetype` enum and response schema are unchanged.

### Operational limits

- Worker and Beat healthchecks verify a live process, Redis, and PostgreSQL readiness; they do not treat unchanged queue depth as a dead worker. A legitimate FFmpeg job can run for many minutes. Watch queue depth, oldest message age, and failed tasks separately. Beat recovers old `IN_PROGRESS` preview stages, but completed failures still require a later request or a manual canary. A runtime preview failure does not turn an already completed CI deployment red.
- The legacy authenticated `POST /recordings/{id}/poster` fallback shares a per-recording Redis queue claim across clients. Its Celery job checks the object again before downloading and never releases a newer claim. It shares the `previews` worker capacity.
- One preview worker runs by default. Higher `PREVIEW_WORKER_CONCURRENCY` needs matching CPU, memory, and temporary disk; `container_name` currently prevents scaling this Compose service to multiple replicas with `docker compose --scale`.
- The Redis queue claim expires after 65 minutes. An original message can reclaim it if nobody has queued a newer one. Under a sustained backlog beyond that time, repeated page requests can supersede old queued messages and push work to the tail again; queue age and admission control need attention before large-scale backfill.

## Verification checklist

- Object metadata reports the expected video MIME type and accepts byte ranges.
- For MP4, the `moov` atom appears before `mdat`.
- Opening a recording triggers metadata and media requests together, followed by Object Storage range traffic.
- Short buffering must not replace the player with Retry. A visible, playing tab or active PiP with no position progress for 30 seconds requests a fresh URL and restores playback. An expired or invalid media URL triggers the same recovery on `error`; if recovery fails, Retry remains available.
- Switching tabs preserves playback and pauses the client timeout clocks except for active PiP's no-progress timer. Check manual PiP and, where supported and permitted, browser-requested automatic PiP on desktop. Check playlist Play and Next after a cold load.
- A removed, blank, or unprocessed playlist item returns 404 from its direct watch, media, and file endpoints, while the catalog still lists it as unavailable.
- `async_operations`, `maintenance`, and temporary `celery` queue depths are monitored during rollout.

See also [MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md), [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md), and [CELERY_WORKERS_GUIDE.md](CELERY_WORKERS_GUIDE.md).
