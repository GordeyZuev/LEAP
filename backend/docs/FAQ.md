# FAQ

Short answers for operators and contributors. In-app copy (searchable, with the same topics) lives in the web client under **Documentation**. Deploy and API detail stay in the guides linked below.

Age rating of the product and of public share pages: **12+**.

---

## What is LEAP?

LEAP (Lecture Enhancement & Automation Platform) takes an educational recording from import to publication: trim silence, transcribe, extract topics with timecodes, generate subtitles, then upload to YouTube / Yandex Disk and/or publish a LEAP share link.

It is multi-tenant. Queries and storage are scoped to the owning user. Credentials are encrypted at rest.

## Where should I start?

| You want to… | Open |
|--------------|------|
| Use the product in the browser | In-app **Documentation** (Start here + FAQ) |
| Run or deploy the stack | [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) |
| Connect YouTube, Zoom, Yandex Disk | [guides/OAUTH.md](guides/OAUTH.md) |
| Connect MTS Link | [guides/MTS_LINK_GUIDE.md](guides/MTS_LINK_GUIDE.md) |
| Understand REST | [TECHNICAL.md](TECHNICAL.md) |
| See what shipped | [CHANGELOG.md](CHANGELOG.md) |

## Template, preset, source – what is what?

- **Template** – how to process and what to write (language, trim, Jinja title/description, which presets to use). Every account has exactly one **base template**. Named templates can auto-link via matching rules.
- **Preset** – where to publish (YouTube privacy, Disk folder, credential). A LEAP look preset sets title, description, and cover **inside LEAP** and does not upload a copy.
- **Source** – where new files come from (Zoom, MTS Link, Yandex Disk, saved URL). One-off URL/file ingest does not need a source.

Processing defaults live in the base template, not in Settings. Settings keep profile, theme, sessions, and retention.

## How does the pipeline run?

Celery chain, roughly: download → trim (FFmpeg) → transcribe (AssemblyAI) → topics (DeepSeek) → subtitles → optional upload.

Queues are split (`downloads`, `processing_cpu`, `async_operations`, `uploads`, `maintenance`). Persistent media lives in S3-compatible storage; the local disk is only for ephemeral FFmpeg/ASR temp files. Browser playback uses presigned URLs, not a byte proxy through the API. See [guides/VIDEO_DELIVERY.md](guides/VIDEO_DELIVERY.md) and [guides/STORAGE_STRUCTURE.md](guides/STORAGE_STRUCTURE.md).

## Which speech engine is in production?

**AssemblyAI**. DeepSeek extracts topics, summaries, and self-check questions. Older notes about Fireworks Whisper as the live ASR path are historical.

## What about MTS Link?

Connect with an organization API key (Credentials → Manual). Lecturers to sync are emails on the source. LEAP requests MP4 conversion when you **Run**, not via a separate download button. Recordings shorter than 10 minutes are marked blank and skipped. Chat and session files can come along with the video. Guide: [guides/MTS_LINK_GUIDE.md](guides/MTS_LINK_GUIDE.md).

## How do share links and playlists work?

- Recording: one public URL. Enable / Disable (same URL) / Rotate (new URL).
- Playlist: an ordered course with `/share/p/{uuid}`. Opening a video goes to the watch layout. Descriptions can use `{{ video_count }}`, `{{ duration_hm }}`, `{{ items }}`.
- Views still count if the visitor is signed in to LEAP (the public page uses `sendBeacon`).
- Look LEAP (title, description, cover) is not an upload destination.

Details: [guides/PLAYLISTS.md](guides/PLAYLISTS.md).

## Why is there a 12+ mark?

LEAP is educational software and hosts lecture video. The product, the marketing page, signed-in chrome, and public share pages carry the **12+** information-product label. It is not a YouTube “made for kids” flag and not an 18+ age gate on the player.

## A recording is stuck or failed. What now?

Open the recording: the pipeline panel names the stage. Pause an in-flight run, then Run again; completed artefacts (transcript, trimmed file) are reused when possible. Upload can be retried without reprocessing.

For download failures check the source credential and that the remote file still exists. For ASR, set language and Vocabulary on the template. For upload, re-authorize the platform credential.

Worker logs: `backend/logs/app.log`, `backend/logs/celery-async.log`. Correlate by recording id, task name, and queue. See the **Troubleshooting** section in in-app Documentation.

## Do I need every integration to try LEAP?

No. A public URL or a local file is enough to ingest. Credentials are required to sync Zoom / MTS Link / Disk and to publish to YouTube / Disk.

## Where are quotas and admin tools documented?

Concept: [guides/QUOTAS.md](guides/QUOTAS.md). In-app **Settings → Usage** and charts: [guides/USAGE_AND_ANALYTICS.md](guides/USAGE_AND_ANALYTICS.md). HTTP: [guides/QUOTA_AND_ADMIN_API.md](guides/QUOTA_AND_ADMIN_API.md).

## Is VK a destination?

No. VK upload is not supported. Current destinations are YouTube, Yandex Disk, and a LEAP share/course link.

## Google Drive / Rutube upload?

Not in the current release. yt-dlp can **download** from Rutube and many other sites. Native Google Drive and Rutube **publish** are planned.

---

**Related:** [INDEX.md](INDEX.md) · in-app **Documentation**
