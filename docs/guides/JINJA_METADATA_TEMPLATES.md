# Jinja2 metadata templates (upload titles, descriptions, Yandex paths)

This guide describes **metadata strings** used when uploading to YouTube, VK, and Yandex Disk: title, description, and (for Yandex) folder path and filename. They are **Jinja2** templates evaluated in a **sandboxed** environment at upload time and validated on save in the API.

**Related:** product overview of templates and presets — [TEMPLATES_PRESETS_SOURCES_GUIDE.md](TEMPLATES_PRESETS_SOURCES_GUIDE.md).

---

## Rules (non-negotiable)

1. **Syntax** — Only **Jinja2** (`{{ variable }}`, `{% ... %}`, filters). Legacy single-brace placeholders like `{display_name}` or `{record_time:DD.MM.YY}` are **not** interpreted by the app at runtime. Existing rows in the database were converted by migration `018_jinja_metadata_templates_data_migration`; `| leap_dt(...)` fragments were replaced by migration `019_replace_leap_dt_in_template_jsonb`.
2. **Validation** — Invalid syntax or failed dry-run render returns **422** when saving configs. Use preview endpoints (below) to test without persisting.
3. **Security** — Templates run in `jinja2.sandbox.SandboxedEnvironment`. Do not rely on sandboxing alone for untrusted admin input; keep normal API auth and tenant checks.
4. **Title templates** — Must contain at least one **allowed** variable (see list below). Plain constant titles are rejected.

---

## Dates and times (precomputed strings)

All date/time values in the context are **strings** already formatted in the **recording owner’s** IANA timezone (`users.timezone`; invalid or missing → UTC). There is **no** `leap_dt` filter — use the variables below.

| Variable | Example meaning |
|----------|-----------------|
| `record_date` / `publish_date` | `DD.MM.YYYY` |
| `record_datetime` / `publish_datetime` | `DD.MM.YYYY hh:mm` |
| `record_date_iso` / `publish_date_iso` | `YYYY-MM-DD` |
| `record_date_short` / `publish_date_short` | `DD.MM.YY` |
| `record_time_hm` / `publish_time_hm` | `HH:MM` |
| `record_datetime_iso` / `publish_datetime_iso` | `YYYY-MM-DD HH:MM` |
| `record_timestamp_local` / `publish_timestamp_local` | `YYYY-MM-DDTHH:MM:SS` (local wall time, no offset suffix) |
| `record_time` / `publish_time` | Same as `record_timestamp_local` / `publish_timestamp_local` |
| `date` | Alias of `record_date` |

`record_*` fields use the lecture start time when present; where the old context fell back to “publish” for display, the same fallback applies to the `record_*` strings. `record_time` / `record_timestamp_local` are **empty** when the recording has no `start_time`.

---

## Context variables (upload / preview)

Values are prepared in `api.helpers.template_renderer.TemplateRenderer.prepare_recording_context` (and matching **stub** data for validation/preview when no recording is selected). Stub times are fixed **UTC** examples for deterministic validation.

| Variable | Type / notes |
|----------|----------------|
| `display_name` | Recording title shown in UI |
| `original_title` | Same as `display_name` (alias for mapping-style templates; there is no separate “raw Zoom title” field in DB) |
| `record_time`, `publish_time` | String timestamps (see table above) |
| `record_timestamp_local`, `publish_timestamp_local` | Same strings as `record_time` / `publish_time` |
| `duration` | Duration in seconds (from DB) |
| `duration_hm` | String like `1:05:03` or `5:03` |
| `recording_id` | String ID |
| `summary` | Plain text from transcription extract (may be empty) |
| `themes` | Short comma-separated string from main topics |
| `topic` | Alias of `themes` (compatibility) |
| `topics` | Formatted block per `topics_display` settings |
| `questions` | Formatted self-check questions if enabled |
| All `record_*` / `publish_*` date keys | Precomputed strings (see table above) |
| `date` | Alias of `record_date` |

**After title render:** `title` is set to the rendered title string so **description** templates can use `{{ title }}` (two-step render).

**Undefined variables** stringify to **empty** (no error).

---

## Two-step render (title → description)

1. Render `title_template` → string `title`.
2. Inject `title` into the context.
3. Render `description_template`.

So descriptions may safely reference `{{ title }}`. If you preview **only** `description_template` with a real recording and it uses `{{ title }}`, also send `title_template` in the same preview request so the API runs the two-step path (see `compute_metadata_preview`).

---

## API: preview without saving

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/templates/render-preview` | Optional `template_id` (merge saved `metadata_config`), optional `recording_id`, body overrides |
| `POST` | `/api/v1/presets/render-preview` | Preset-style fields + optional `recording_id` |

Responses use **HTTP 200** with `valid`, `errors`, `warnings`, and rendered strings. **404** if `recording_id` or `template_id` does not belong to the current user (same patterns as the rest of the API).

---

## Where templates are validated

Central helper: `validate_jinja_template` / `assert_title_template_has_substitution` in `api/helpers/template_renderer.py`, wired via `api/schemas/template/jinja_field_validators.py` into:

- Template metadata (`TemplateMetadataConfig`, nested VK/YouTube/Yandex)
- Preset metadata
- User config `metadata` defaults
- Mapping rules / video mapping defaults (`api/schemas/config_types.py`)
- Recording request overrides where applicable

---

## Migration `018` (data)

- **Scope:** JSONB fields `metadata_config`, `preset_metadata`, `processing_preferences`, `config_data` (known template keys only).
- **Rule:** `{name}` → `{{ name }}`, `{name:fmt}` → `{{ name | leap_dt('fmt') }}`; strings already containing `{{` or `{%` are left as-is.
- **Downgrade:** No-op (data is not converted back).

## Migration `019` (data)

- **Scope:** Same JSONB trees as018 (recursive); any string containing `leap_dt` with base `record_time` or `publish_time` is rewritten to canonical variables (`record_date_iso`, etc.).
- **Downgrade:** No-op.

**Deploy order:** run application code that provides the new context variables **before** or together with migration `019`; then remove any remaining reliance on `leap_dt` (already removed in current code).

---

## Topics list timestamps

`TemplateRenderer._format_topics_list` respects **`show_timestamps`** (presets / template metadata) or **`include_timestamps`** (user `TopicsDisplayConfig`) when the former is absent — both control whether topic lines include timecodes from `topic_timestamps` data.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| 422 on save | Template syntax; dry-run error message; title must include an allowed variable name in a `{{ ... }}` expression |
| Empty `original_title` / wrong title | Use `{{ display_name }}` or `{{ original_title }}` (both set from the same source at upload) |
| Date looks wrong | Owner `users.timezone`; values are local wall time, not UTC |
| Preview differs from upload | Preview uses stub context without `recording_id`; pass `recording_id` for realistic values |

---

## Quick examples

**Title**

```jinja2
{{ display_name }} | {{ themes }} ({{ record_date_short }})
```

**Description (uses rendered title)**

```jinja2
{{ summary }}

Topics:
{{ topics }}
```

**Yandex folder**

```jinja2
/Video/{{ display_name | replace('/', '-') }}
```
