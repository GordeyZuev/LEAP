# Recording template JSON bundle

Export, import, and full JSON replace for **recording templates**. Same bundle shape for one template or many.

**Product documentation (canonical for users):** in the web app, **Documentation → Templates → JSON config (import / edit)** and following subsections (metadata, matching, validate).

**Related (operators):** field details in [TEMPLATES_PRESETS_SOURCES_GUIDE.md](TEMPLATES_PRESETS_SOURCES_GUIDE.md), Jinja rules in [JINJA_METADATA_TEMPLATES.md](JINJA_METADATA_TEMPLATES.md).

---

## Envelope

```json
{
  "leap_template_bundle": 1,
  "exported_at": "2026-09-13T12:00:00Z",
  "reference": {
    "presets": [{ "id": 4, "name": "VK Main", "platform": "vk" }],
    "sources": [{ "id": 2, "name": "Zoom HSE" }],
    "playlists": [{ "id": 7, "name": "Course fall", "missing": false }]
  },
  "templates": [ { "...": "..." } ]
}
```

| Field | Role |
|-------|------|
| `leap_template_bundle` | Must be `1` |
| `exported_at` | Set on export; optional on import |
| `reference` | **Hints only** (names for ids in this file). Ignored on import |
| `templates` | One or more template objects |

Import also accepts `{ "templates": [...] }` or a **single template object** (wrapped automatically).

---

## Template object

| Field | Notes |
|-------|--------|
| `id` | Optional. Present → update existing; absent → create |
| `name` | Required, 3–255 chars, unique per user |
| `description` | Optional |
| `is_draft` | Default `false`. Drafts skip auto-matching until activated |
| `is_active` | Default `true` |
| `is_default` | **Export only.** Cannot set via import; base template has special rules |
| `matching_rules` | See [Matching rules vs form editor](#matching-rules-vs-form-editor) |
| `processing_config` | Nested `transcription` (+ optional `trimming`, `transcription_vocabulary`) |
| `metadata_config` | Jinja title/description + optional `youtube` / `vk` / `yandex_disk` / `leap` |
| `output_config` | `preset_ids`, `playlist_ids` (LEAP courses), `channel_ids` (LEAP channel Videos), `auto_upload`, `publish_leap`, `upload_captions` |

**LEAP playlists:** `output_config.playlist_ids` are applied when **LEAP publish** runs after successful processing (not on bind/import). Empty list → inherit playlists from the **leap** preset in `preset_ids` at pipeline time. **YouTube** playlist ids live on the **preset** (`playlist_id`), not here.

**LEAP channels:** `output_config.channel_ids` append the recording to those channels’ **Videos** tab on the same LEAP publish step. Empty list inherits from the leap preset. Share is **not** enabled automatically. See [CHANNELS.md](CHANNELS.md).

**PUT / full replace:** Send **all** config keys explicitly (`null` clears JSONB). Omitted keys are not “leave unchanged” — use Download → edit → Save for safe round-trip.

**Form editor vs JSON:** The web form PATCH merges some platform metadata when presets change. JSON replace overwrites exactly what is in the file.

---

## Matching rules vs form editor

JSON validation follows the **same rules as the template form**, not stricter ones.

| Template kind | Form UI | JSON (`PUT`, import, create) |
|---------------|---------|--------------------------------|
| **Base (default)** | No matching section | Omit `matching_rules` or set `null`. Any non-empty rule → error |
| **Named, draft** | Rules optional | `matching_rules` optional |
| **Named, active** | Rules may be left empty | `matching_rules` may be `null` or empty lists → **allowed**; validate/import returns warning `empty_matching_rules` (no auto-link until you add rules) |
| **Runtime** | — | `source_ids` alone never matches; warning `source_ids_without_positive_rule` |

The JSON **edit** dialog loads a **PUT body** (no bundle envelope, no `reference`). Base template exports omit the `matching_rules` key in the editor.

---

## Validation (strict vs warnings)

**Errors (save blocked):**

- Jinja2 only in templates (`{{ display_name }}`, …). Legacy `{record_time:DD.MM.YY}` is **rejected**.
- Base template: cannot set matching rules, cannot draft/deactivate.
- `auto_upload: true` → `processing_config` required and at least one copy preset (not leap-only).
- Global `metadata_config.title_template` → `output_config` object required.
- `preset_ids` must exist, be active, and include at most one `leap` preset.
- Import: duplicate names inside one file → error; quota checked for creates; all-or-nothing apply.

**Warnings (save allowed):**

- `empty_matching_rules` — active named template with no positive rules.
- `source_ids_without_positive_rule` — see table above.

Export responses omit JSON `null` fields where possible (`response_model_exclude_none`).

---

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/templates/export?ids=1,2` | Export bundle |
| POST | `/api/v1/templates/import?dry_run=true\|false&auto_rematch=false` | Validate or apply bundle |
| PUT | `/api/v1/templates/{id}` | Full replace (JSON editor) |
| POST | `/api/v1/templates/{id}/validate-replace` | Validate PUT body without save |

Partial updates remain `PATCH /api/v1/templates/{id}` (form UI).

---

## UI

See in-app **Documentation → Templates** (JSON subsections). Entry points:

- **Template detail → More:** Download JSON config, Edit JSON config (PUT).
- **Templates list:** Import JSON config (bulk).

---

## Examples

- [template_bundle_single.json](../examples/template_bundle_single.json)
- [template_bundle_multi.json](../examples/template_bundle_multi.json)

Local bulk generation: `docs/examples/generate_templates.py` → `template_bundle_hse.generated.json`. Upload: `LEAP_API_EMAIL`, `LEAP_API_PASSWORD`, `docs/examples/upload_templates.py [path]`.

---

## Troubleshooting

| Error / warning | Fix |
|-----------------|-----|
| legacy single-brace placeholders | Use `{{ record_date_short }}` etc. |
| Default template cannot have matching rules | Remove or null out `matching_rules` for base template |
| `empty_matching_rules` (warning) | Add keywords/patterns/exact_matches/source_ids, or set `is_draft: true` while configuring |
| Unknown preset ids | Fix ids or create presets; check `reference` on export |
| Template name already exists | Rename or import with `"id": …` to update |
