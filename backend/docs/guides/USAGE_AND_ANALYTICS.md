# Usage, quotas, and product analytics

**Product release:** v0.11.1.0 (October 2026)

This guide is the canonical reference for **in-app usage observability**: what users and admins see in the web UI, how it maps to API responses, and how it relates to `usage_events`, `quota_usage`, and share counters.

For **ops observability** (Loki, Prometheus, Grafana), see [MONITORING.md](MONITORING.md).
For **quota enforcement** (limits, overrides, admin API), see [QUOTAS.md](QUOTAS.md) and [QUOTA_AND_ADMIN_API.md](QUOTA_AND_ADMIN_API.md).

---

## 1. Where to look in the UI

| Surface | Path | What it shows |
| --- | --- | --- |
| **Quota + activity** | Settings → **Usage** | Plan limits (`used / limit`, `∞` when unlimited) and activity charts for the signed-in user |
| **Platform trends** | Admin → **Analytics** | Recordings, transcribed minutes, active users, share views — same date filter as Usage |
| **Per-user activity** | Admin → Users → edit user → **Activity** | Charts + recent `usage_events` for one account |
| **Share link stats** | Recording → Manage share | Views/downloads; custom date range on the chart |
| **Account plan name** | Settings → Account | Plan display name from `GET /users/me/quota` (quota numbers live on Usage) |

---

## 2. Settings → Usage

### Quota

All effective limits from `GET /api/v1/users/me/quota`, shown as **`used / limit`** (limit `∞` when the plan has no cap):

| Label | Period | Source |
| --- | --- | --- |
| Recordings / month | Monthly | `quota_usage.recordings_count` |
| Storage | Total (GB) | Live S3 prefix size |
| Concurrent tasks | Snapshot | Active pipelines (`on_air`) |
| Automation jobs | Total | Live row count in `automation_jobs` |
| Transcriptions / month | Monthly | `quota_usage.transcriptions_count` |
| Processing / month | Monthly | `quota_usage.processing_count` |
| Templates | Total | Named templates (default template excluded) |
| Credentials | Total | Live row count in `user_credentials` |

Progress bars appear only when the limit is a positive finite number.

### Activity

- **Date range:** presets (7 / 28 / 90 days, month, all time, …) or custom range; max **366 calendar days** (UTC), same as the analytics API.
- **Summary cards:** recordings created, transcribed content (minutes), transcription jobs, uploads, share views (when &gt; 0).
- **Charts:** recordings, transcribed minutes, uploads by platform (stacked), share views; long ranges auto-bucket by week or month so bars stay readable.
- **Breakdowns:** recordings by status, top templates in the selected period.

Activity totals come from **`GET /api/v1/users/me/analytics`**.

---

## 3. Admin analytics

### Platform (Admin → Analytics)

- Single date filter drives summary cards and all charts.
- Metrics align with user analytics: new recordings, transcribed minutes, uploads, share views, **active users** (distinct users with ≥1 new recording that day).
- API: `GET /api/v1/admin/stats/analytics?from=&to=`.

### Per user (edit user modal → Activity)

- Same chart kit and date range as Usage, scoped to one `user_id`.
- **Recent events** list from `GET /api/v1/admin/users/{id}/events?from=&to=` (`usage_events` table).

---

## 4. Share analytics (owner)

| Surface | Path | What you see |
| --- | --- | --- |
| **Recording** | Manage share (recording page) | Views, downloads, **Engagement** (popular chapters, completion, typical stop point) |
| **Course (playlist)** | `/playlists/{id}?tab=analytics` | Opens, views, downloads, **Engagement** (chapters, completion, navigation between lectures) |
| **Channel** | `/channels/{id}?tab=analytics` | Same catalog aggregates + **Engagement** across channel videos |

- Supports **`from` / `to`** (presets 7 / 28 / 90 days) or legacy rolling `days=7|28`.
- Same share analytics API as views/downloads; engagement metrics use the selected date range.
- Course and channel analytics include **downloads by file type** for lectures currently in the catalog (same `FILE_DOWNLOAD` events as the daily chart).
- Counting runs on public watch pages only (single share and lecture inside a course); not mixed into Settings → Usage or Admin → Analytics.
- A viewer who is **signed in to LEAP** still increments share views: `navigator.sendBeacon` cannot send a CSRF header, so those POSTs are exempt. Owner Enable / Disable / Rotate still require CSRF.
- Public access and engagement beacons publish events to the `async_operations` Celery queue. The worker writes rows and recording counters in one transaction, using event IDs to avoid double counting on retries. If Redis deduplication or queue publishing fails, the API attempts a synchronous database write; tracking remains best-effort and must not fail playback. Channel surface opens retain their channel ID, while `?from=` attribution requires an enabled channel, the same owner, and actual catalog membership. A Redis outage can still cause duplicate views from simultaneous requests before either database write commits.
- Analytics can lag behind a successful beacon while events wait in the queue. Event timestamps use publication time so a delayed worker does not move traffic into a later UTC day. See [MONITORING.md](MONITORING.md) for queue and publish metrics.

---

## 5. HTTP API (product analytics)

All endpoints require auth. Dates are inclusive `YYYY-MM-DD` (UTC day boundaries). Default window when omitted: last **28 days**.

| Endpoint | Role | Response highlights |
| --- | --- | --- |
| `GET /users/me/quota` | owner | `recordings`, `storage`, `concurrent_tasks`, `automation_jobs`, `transcriptions`, `processing`, `templates`, `credentials` — each `{ used, limit, available }` |
| `GET /users/me/analytics` | owner | `summary`, `daily[]`, `daily_uploads`, `breakdown` |
| `GET /admin/stats/analytics` | admin | Platform `summary`, `daily[]` (same shape as user analytics) |
| `GET /admin/users/{id}/analytics` | admin | Same shape as user analytics for one account |
| `GET /admin/users/{id}/events` | admin | Paginated `usage_events` with optional `from` / `to` |
| `GET /recordings/{id}/share/analytics` | owner | Share views/downloads series |

**Metric labels**

- **`transcription_minutes`** — sum of processed content length (`final_duration`) for completed transcriptions in the period (deduped per recording per day; aligned with Grafana Overview logic).
- **`transcription_jobs`** — count of completed transcription jobs in the period.
- **Monthly quota transcriptions** — `quota_usage.transcriptions_count` via `/users/me/quota` (not the same as activity job count over an arbitrary range).

---

## 6. Data model (backend)

| Store | Purpose |
| --- | --- |
| **`quota_usage`** | Monthly counters (`period` = `YYYYMM`): recordings, transcriptions, processing, uploads |
| **`usage_events`** | Immutable audit log for admin timeline (`recording_created`, `processing_started`, …) |
| **`share_access_events`** + recording counters | Share views/downloads |
| **`share_engagement_events`** (migration **053**) | Anonymous engagement on public watch (chapters, completion, navigation, stop point) |
| **Live counts** | Storage (S3), concurrent tasks (`on_air`), automation jobs, templates, credentials |

Tracking hooks are **best-effort**: a failed counter write is logged and does not fail the user operation.

---

## 7. Related release notes (v0.10.8.3)

Same release also shipped:

- **Faster lists** — TanStack Query `placeholderData` / prefetch; no empty flash when switching pages.
- **MTS Link trim** — trailing digital silence to EOF is trimmed (see [MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md](MEDIA_INTEGRITY_DOWNLOAD_AND_TRIM.md)).
- **Docs hub** — [INDEX.md](../INDEX.md), [FAQ.md](../FAQ.md), in-app Documentation search; product age rating **12+**.
- **Stability** — share view beacons work while signed in; Loki WARNING is reserved for signal (see [MONITORING.md](MONITORING.md)).

Full file-level history: [CHANGELOG.md](../CHANGELOG.md) (dated sections **2026-09-09**, **2026-09-10**).


## Home

`/home` is the signed-in landing page: a standard Home heading, personal greeting,
current operational counts, one list of up to five recordings with **Recently added** / **With errors** tabs,
and weekly activity with a daily public-video views chart.

A centered, width-limited column aligns the recording status cards, list, and activity
section to the same edges. The activity metrics share one surface with the chart.
**Open library** is the main navigation action; an empty library offers **Connect a
source**. Video creation stays in the recording library. Connection warnings reuse
the app-wide banner. Home is separated from the remaining sidebar navigation. The logo,
authenticated `/`, successful login, an already signed-in visit to login or register,
unknown routes, and render-error screens lead to `/home`. A recording still returns
to the library, and **Open library** stays the way into Recordings.

The list initially selects **With errors** when needed; subsequent refreshes preserve
the selected tab. Recently added sorts by `created_at DESC`; With errors sorts by
`updated_at DESC`. Each row opens the recording details and shows its status or failed
stage. The page does not infer successful publication from an absence of errors.

Activity appears only when at least one visible recording has an enabled public LEAP
link, or can be played in an enabled public playlist belonging to the same owner.
Both publication paths require a non-null share token and an active recording deletion
state; playlist playback also requires a non-empty processed video path. A recording
in several playlists counts once. Without published recordings,
Home does not request analytics. Publication is independent of whether views occurred
in the selected week.

Activity shows public video views, recordings added, and hours of transcribed content
for the UTC period. **View analytics** opens Settings → Usage. Values of 10,000 or more
use compact notation; exact displayed values remain available in tooltips and
screen-reader text. Transcribed hours are rounded to one decimal before formatting.

- `GET /api/v1/users/me/home-summary` returns `total`, `published`, `in_progress`, `waiting_source`,
  `paused`, and `error` for the authenticated owner; responses use `private, no-store`.
- Counts exclude deleted and blank recordings. Categories are exclusive: errors first,
  then paused, then source/conversion waits, then `on_air` (including queued work).
  These categories are not exhaustive: idle/finished recordings also belong to `total`.
- Catalog, export, and bulk filters accept `operational_state` with those four category keys.
  Counts and filters share SQL predicates.
- Home list requests use `compact=true&include_posters=false&per_page=5`, avoiding unused
  poster lookups. Only the selected tab is fetched/polled.
- Current data refreshes every 30 seconds on an active tab and on window focus; weekly
  analytics refreshes every five minutes. Analytics reuses the existing UTC metrics,
  covering today and the preceding six days; the period label exposes the exact range.
- Queries are scoped to the signed-in user. Successful login cancels outstanding queries
  and clears the client cache before navigating to Home.
- Failed/missing data is not replaced with zeros. A failed refresh retains previously loaded
  results with an error and a retry action. A stale zero summary cannot hide a nonempty
  list. Cached empty-list messages are suppressed while that list's refresh is in error.
- Home adds no database migration. Deploy the API with `/users/me/home-summary` and
  `operational_state` support before, or together with, the frontend.

Settings tab contents and Home use the shared `useHydrated` hook to keep the first
client render consistent with server markup even when the parent auth guard has
already populated the user cache. Settings keeps its heading and tab navigation
server-rendered while its data-dependent panel starts with a skeleton.

## API errors in the interface

Toasts and load-error placeholders share one reader, `extractApiError`. A specific API
`detail` is shown as written: quota text, the first FastAPI validation `msg`, and an
auth lockout. These generic bodies are not shown literally: `Rate limit exceeded`,
`Too many requests`, and `Internal Server Error`. A sentence longer than 240 characters
is also replaced.

| Situation | What the UI says |
| --- | --- |
| 429 with no useful `detail` | Too many requests, plus a wait taken from JSON `retry_after` or the `Retry-After` header: about a minute up to 90 seconds, then whole minutes, an hour up to 90 minutes, otherwise whole hours. With neither value: wait a moment. |
| No response, `ERR_NETWORK` | Could not reach the server. |
| `ECONNABORTED` or `ETIMEDOUT` | The request timed out. |
| `ERR_CANCELED` | The caller's own fallback. A cancel is not described as a dropped connection. |
| 413 with no useful `detail` | The file is larger than the upload limit. The upload form still states the configured byte limit first. |
| 5xx with no useful `detail` | The server had a problem; try again in a moment. |
| Anything else | The caller's fallback, such as "Failed to load recordings". |

Missing recordings, playlists, and channels (404/403) keep their own "not found" copy.
A failed Connections load is an error with retry, not an empty account. Charts, share
statistics, the recording player, and a failed automation job use the same reader.
