# PENDING_SOURCE Status Implementation - 2026-01-22

## Overview
Added `PENDING_SOURCE` status to handle recordings that are still being processed on Zoom's side (API error code 3301).

## Changes

### 1. Core Model (`models/recording.py`)
- Added `PENDING_SOURCE` to `ProcessingStatus` enum (first in order)

### 2. Zoom API (`api/zoom_api.py`)
- Added `ZoomRecordingProcessingError` exception for code 3301
- Special handling: code 3301 → INFO log, other errors → ERROR log

### 3. Sync Logic (`api/routers/input_sources.py`)
- When `zoom_processing_incomplete=True`:
  - `status = PENDING_SOURCE`
  - `blank_record = False` (unknown yet)
- Passes `zoom_processing_incomplete` to `create_or_update`

### 4. Repository (`api/repositories/recording_repos.py`)

**Create (new recording):**
```python
if zoom_processing_incomplete:
    status = PENDING_SOURCE
elif is_blank:
    status = SKIPPED
elif is_mapped:
    status = INITIALIZED
else:
    status = SKIPPED
```

**Update (resync):**
- If `status == PENDING_SOURCE` and Zoom finished processing:
  - Recheck `is_blank`
  - Update to `INITIALIZED` or `SKIPPED`
- If still `PENDING_SOURCE`: keep status, update metadata

### 5. Status Manager (`api/helpers/status_manager.py`)
- `PENDING_SOURCE` blocked like `SKIPPED` in:
  - `should_allow_download()`
  - `should_allow_processing()`
  - `should_allow_transcription()`
  - `should_allow_upload()`
- Added to `compute_aggregate_status()` workflow

### 6. Recordings API (`api/routers/recordings.py`)
**RESET logic:**
- Checks `source_metadata.zoom_processing_incomplete`
- If true → `PENDING_SOURCE`
- Else → `INITIALIZED` or `SKIPPED` based on `is_mapped`

### 7. Templates (`api/routers/templates.py`, `api/tasks/template.py`)
**Rematch logic:**
- Includes `PENDING_SOURCE` in query filter
- When matched: keeps `PENDING_SOURCE` status (doesn't change to `INITIALIZED`)
- Updates `is_mapped` and `template_id` only

### 8. Database Migration (`alembic/versions/003_add_pending_source_status.py`)
- Adds `PENDING_SOURCE` to `processingstatus` enum
- Updates existing records: `SKIPPED` + `zoom_processing_incomplete=true` → `PENDING_SOURCE`

### 9. Documentation (`docs/DATABASE_DESIGN.md`)
- Updated FSM diagram to include `PENDING_SOURCE`

## FSM Flow

```
[sync from Zoom]
      ↓
zoom_processing_incomplete?
      ↓
     YES → PENDING_SOURCE
      |         ↓
      |    [resync after hours]
      |         ↓
      |    Zoom finished?
      |         ↓
      |    ┌───┴───┐
      |    ↓       ↓
      | is_blank? is_mapped?
      |    ↓       ↓
      | SKIPPED  INITIALIZED
      |
     NO → [check blank/mapped]
           ↓
      INITIALIZED or SKIPPED
```

## Testing

✅ All files pass `ruff check`
✅ Python syntax validated
✅ Migration created with upgrade/downgrade

## Files Modified
- `models/recording.py`
- `api/zoom_api.py`
- `api/routers/input_sources.py`
- `api/repositories/recording_repos.py`
- `api/helpers/status_manager.py`
- `api/routers/recordings.py`
- `api/routers/templates.py`
- `api/tasks/template.py`
- `docs/DATABASE_DESIGN.md`
- `alembic/versions/003_add_pending_source_status.py` (new)
