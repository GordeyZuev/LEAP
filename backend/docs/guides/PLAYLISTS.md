# Playlists (LEAP courses)

Ordered collections of recordings for watching as a course. This is **not** a YouTube `playlist_id` in upload metadata — that field still lives on templates/presets for destination platforms.

Limits: **200 playlists per user**, **200 items per playlist**, unique `name` per user. Schema: `playlists` / `playlist_items` (migration **043**). REST detail: [TECHNICAL.md](../TECHNICAL.md) (Public Share Links, Playlists REST).

## Owner UI and API

Sidebar **Playlists** → card grid → editor (reorder by drag). Publications on a recording can chip membership.

```bash
GET/POST   /api/v1/playlists
GET/PATCH/DELETE /api/v1/playlists/{id}
GET/POST   /api/v1/playlists/{id}/items
DELETE     /api/v1/playlists/{id}/items/{itemId}
PUT        /api/v1/playlists/{id}/items/order   # full item id set or 409
POST       /api/v1/playlists/{id}/share         # Enable (mint token if empty)
DELETE     /api/v1/playlists/{id}/share         # Disable (token kept)
POST       /api/v1/playlists/{id}/share/rotate
```

## Public course link

URL: `{origin}/share/p/{uuid}`.

| Action | Token | Public GET |
|--------|--------|------------|
| **Enable** | Mint once if empty | 200 while `share_enabled` |
| **Disable** | Kept | **404** (same body as unknown token) |
| **Rotate** | New UUID; old URL 404 | 200 on the new URL |

Recording share uses the same Enable / Disable / Rotate contract. Public recording URL is `{origin}/share/{uuid}`. Migration **044** adds `recordings.share_enabled`. Messengers (Telegram) unfurl that URL via Open Graph (`opengraph-image` + `GET /api/v1/share/{token}/poster`).

The playlist **landing** (`/share/p/{uuid}`) is the course page: first-item poster (image only; the picture links to the first playable video) and a video list. Opening a video uses `/share/p/{uuid}?v={itemId}` (real navigation). Watch uses the same layout as recording share: player, companion tabs **Videos / Topics / Transcript**, then Extra content, Files, and Overview for that item. Items without processed video are listed but not playable. Course landing has no Files panel. Opening a **playable** video on watch counts as a **page view on that recording** (`POST …/items/{itemId}/beacon`, same Redis ~30 min dedup as recording share). Processing rows and the landing page do not increment views.

## Revoke / disable and 404

Backend uses one public message (`SHARE_NOT_FOUND`) for unknown tokens and disabled share (recording or playlist) so callers cannot distinguish “never existed” from “turned off”.

The public UI must treat **HTTP 404** on `GET /api/v1/share/{token}` and `GET /api/v1/share/p/{token}` as “link not found” (no retry). If the page was already open, a later media/item 404 should **re-fetch** that metadata: metadata 404 → same full-page message; metadata still 200 → “this video is unavailable” (item removed or not playable).

Owner `GET /api/v1/playlists/{id}` 404/403 → playlist missing (deleted or another tenant).

## Templates

Named templates may set `output_config.playlist_ids` (≤10). When `template_id` is set (bind / create / match), the recording is **appended**. The default/base template is ignored. Missing playlist ids are skipped. Empty override lists do not clear membership. See [TEMPLATES.md](TEMPLATES.md).
