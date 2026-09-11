# Playlists (LEAP courses)

Ordered collections of recordings for watching as a course. This is **not** a YouTube `playlist_id` in upload metadata — that field still lives on templates/presets for destination platforms.

Limits: **200 playlists per user**, **200 items per playlist**, unique `name` per user. Schema: `playlists` / `playlist_items` (migration **043**). REST detail: [TECHNICAL.md](../TECHNICAL.md) (Public Share Links, Playlists REST).

## Owner UI and API

Sidebar **Playlists** → card grid → editor (reorder by drag). On a recording, **Publications** groups LEAP Link and course membership; row icons sit vertically centered with the status text and actions. Membership can also show as chips in that card.

**List cards** (enabled share only): **LEAP** opens `{origin}/share/p/{uuid}` in a new tab; **Copy link** copies that absolute URL. Disabled or never-enabled playlists have no list controls (enable from the editor). Poster, name, and duration go to the editor. Description and share controls sit **beside** that link (not inside it) so markdown links and the public URL stay real `<a>` elements. After Enable / Disable / Rotate, the list query is invalidated so the card matches the editor.

```bash
GET/POST   /api/v1/playlists                    # items: share_token, share_enabled
GET/PATCH/DELETE /api/v1/playlists/{id}
GET/POST   /api/v1/playlists/{id}/items
DELETE     /api/v1/playlists/{id}/items/{itemId}
PUT        /api/v1/playlists/{id}/items/order   # full item id set or 409
POST       /api/v1/playlists/{id}/share         # Enable (mint token if empty)
DELETE     /api/v1/playlists/{id}/share         # Disable (token kept)
POST       /api/v1/playlists/{id}/share/rotate
```

## Public course link

URL: `{origin}/share/p/{uuid}`. Owner list **LEAP** / **Copy link** use this URL only while share is enabled.

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

Playlist **description** is a Jinja string (owner GET/PATCH stores the source). Allowed variables: `video_count`, `duration_hm` (total length, same `H:MM:SS` / `M:SS` as recordings), `items` (numbered titles in watch order). Public GET and the playlist card list **render** Jinja; markup (`**bold**`, `*italic*`, `++underline++`, `~~strike~~`, `[label](url)`) is applied in the UI after render. Cmd/Ctrl+B, I, U, K, and Shift+X wrap only the text around `{{ … }}`, e.g. `**Курс:** {{ items }} **далее**`. The editor keeps the marks; **Public look** (and the share page) is formatted. Marks do not span line breaks, so they cannot wrap a multi-line `{{ items }}` block. A `*` in a video title can look like italic on the public page. YouTube/VK/Yandex receive **plain text** (`markup_to_plain` after Jinja).

## Templates

Named templates may set `output_config.playlist_ids` (≤10). When `template_id` is set (bind / create / match), the recording is **appended**. The default/base template is ignored. Missing playlist ids are skipped. Empty override lists do not clear membership.

Run and named templates can add a recording to LEAP courses **without** upload presets: membership is not an upload. See [TEMPLATES.md](TEMPLATES.md).

## Publication titles (LEAP look preset)

Course and share titles are computed on **read**. They are not stored on `playlist_items` and do not overwrite `recordings.display_name`.

1. Active `platform=leap` preset in the resolved `output_config.preset_ids` (`title_template`)
2. Else the template’s global `metadata_config.title_template`
3. Else `display_name`
4. If Jinja renders blank → `display_name`

A leap preset is a LEAP publication target (title, description, optional cover, optional share link, default courses). It is **not** a copy upload: no credential, no YouTube/Yandex file transfer. Add it to a template’s `preset_ids`. At most one leap preset. After processing, a `LEAP` output target is marked uploaded so the recording can go **READY**. `auto_upload` still needs a copy preset (YouTube / Yandex Disk) for those platforms. `metadata_config.leap` overlays the look and `auto_share` **only** when an active leap preset is resolved.

Owner playlist items keep `display_name` (library name) and add `title` (publication). Public `/share/p/…` items expose publication `title` only. Add-to-playlist search still uses `display_name`. Editing the leap preset or rebinding the template changes names on the next GET.

Course membership (`playlist_ids`) can be set on the **leap preset** (default), then replaced by a **named template** or **Run** `output_config.playlist_ids` when that list is non-empty. In the template editor, leave **LEAP playlists** empty to keep inheriting the preset list (do not expect the UI to pre-fill those ids into the form). Template and Run can override look fields and `auto_share` via `metadata_config.leap` under **Metadata → Platform overrides → LEAP** (not in the Output section).
