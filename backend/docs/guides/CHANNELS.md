# Channels (LEAP programs)

A **channel** is a public hub (`/c/{slug}`) with two tabs: **Playlists** (courses) then **Videos** (explicit recordings). It is not a third player: cards open existing `/share/{uuid}` and `/share/p/{uuid}` with `?from={slug}`.

Limits: **20 channels per user**, **200 videos** and **200 playlists** per channel. A playlist may belong to many channels (M:N). Schema: `channels`, `channel_videos`, `channel_playlists` (migration **050**). Covers: `playlists.cover_key` (**049**). Analytics subjects: `share_access_events.playlist_id` / `channel_id` (**051**).

## Slug and availability

Public URL: `{origin}/c/{slug}`. Slug is **globally unique**, 5–64 chars, `a-z0-9`, hyphen, and underscore. It can be changed (PATCH); the old URL **404**s (no redirect). **Enable / Disable** — Disable keeps the slug; delete frees it. There is no UUID token and no Rotate. Template and recording pickers select existing channels; new ones are created on the Channels page (name + slug).

## Visibility

The course link `/share/p/{uuid}` still lets viewers watch lectures without a per-recording share. On the **channel** showcase, only share-enabled playlists and share-enabled playable videos appear. Video cards use the recording **display name** (not the YouTube/VK publication title) plus lecture date. The editor keeps Hidden rows with **Share off** / **Not ready** and a link to Enable share.

Templates `channel_ids` append the recording to **Videos** after processing. They do **not** turn share on. Empty `channel_ids` inherits the LEAP preset.

## Owner API

```bash
GET/POST   /api/v1/channels
GET/PATCH/DELETE /api/v1/channels/{id}
POST/DELETE /api/v1/channels/{id}/banner
GET/POST   /api/v1/channels/{id}/videos
DELETE     /api/v1/channels/{id}/videos/{recordingId}
PUT        /api/v1/channels/{id}/videos/order
GET/POST   /api/v1/channels/{id}/playlists
DELETE     /api/v1/channels/{id}/playlists/{playlistId}
PUT        /api/v1/channels/{id}/playlists/order
POST/DELETE /api/v1/channels/{id}/share
GET        /api/v1/channels/{id}/share/analytics
GET        /api/v1/c/{slug}
POST       /api/v1/c/{slug}/beacon
```

Owner `GET /channels/{id}` is metadata plus counts. Tab membership is `GET …/videos` and `GET …/playlists`. Description Jinja: `video_count`, `playlist_count`, `duration_hm`, `items`, `playlists` (see [JINJA_METADATA_TEMPLATES.md](JINJA_METADATA_TEMPLATES.md)). Description source is at most **4000** characters. The public page shows **four lines** with a light fade, then **Show more**. List view includes a two-line **blurb**: video `main_topics` from the recording row, playlist description (Jinja rendered with counts, not the full `{{ items }}` list). Viewers can search (title and blurb), sort (channel order / date / name / duration), and switch grid or list (`?q=` `?sort=` `?view=`). Banner upload is `multipart/form-data` field `file`.

Owner UI: **Content** / **Settings** / **Analytics** (`?tab=`). Compact analytics plaque with **View analytics**. Playlist rows can copy `/share/p/{token}` when the course is shared. `/channels/{id}/analytics` redirects to `?tab=analytics`. Public `/c/{slug}` uses the same header as share watch (LEAP, 12+, Copy link) and a short YouTube-style banner strip (`3:1` / `4:1` / `6:1`).

Playlist custom cover: `POST/DELETE /api/v1/playlists/{id}/cover`. Owner playlist list uses SQL aggregates and batched posters (not `selectinload` of all items).
