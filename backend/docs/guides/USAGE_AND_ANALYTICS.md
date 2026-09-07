# Usage, quotas, and product analytics

**Product release:** v0.10.8.3 (September 2026)

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

- **Manage share** on a recording: views and downloads over time.
- Supports **`from` / `to`** (presets 7 / 28 / 90 days) or legacy rolling `days=7|28`.
- API: `GET /api/v1/recordings/{id}/share/analytics`.
- Public beacons and download routes are unchanged; see [TECHNICAL.md](../TECHNICAL.md) (Share analytics).
- A viewer who is **signed in to LEAP** still increments share views: `navigator.sendBeacon` cannot send a CSRF header, so those POSTs are exempt. Owner Enable / Disable / Rotate still require CSRF.

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
