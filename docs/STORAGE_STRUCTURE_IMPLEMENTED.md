# Storage Structure Implementation Complete

**Date:** 2026-01-22  
**Status:** ✅ LOCAL Implementation Complete  
**S3 Support:** 🚧 Prepared (not integrated yet)

## What Was Done

### 1. Separated Code and Data

**file_storage/** - Python module (code only):
```
file_storage/
├── backends/              # S3-ready backends
│   ├── base.py           # StorageBackend interface
│   ├── local.py          # LocalStorageBackend
│   └── __init__.py
├── factory.py             # Backend factory (prepared for S3)
├── path_builder.py        # ⭐ Used everywhere
└── __init__.py
```

**storage/** - Data directory (media files only):
```
storage/
├── shared/
│   └── thumbnails/        # 22 shared thumbnails (migrated)
├── temp/                  # Temporary processing files
└── users/                 # User recordings (created on demand)
    └── user_XXXXXX/
        ├── recordings/
        │   └── NN/
        └── thumbnails/
```

### 2. All Code Updated

**Files Using StoragePathBuilder (8 total):**
- `video_download_module/downloader.py` - Downloads to `source.mp4`
- `api/tasks/processing.py` - Processing to `video.mp4`, `audio.mp3`
- `api/routers/recordings.py` - File uploads and metadata
- `api/routers/auth.py` - User directory creation
- `transcription_module/manager.py` - All transcription paths
- `utils/thumbnail_manager.py` - ⭐ **NEW:** User and shared thumbnails
- `api/routers/thumbnails.py` - Thumbnail API endpoints
- `file_storage/__init__.py` - Module exports (code)

**Removed:**
- ❌ No `media/` paths in active code
- ❌ No `UserPathManager` usage (deprecated)
- ❌ No `display_name` in file paths

### 3. Configuration Updated

- `config/settings.py` - `storage/shared/thumbnails`
- `api/schemas/config_types.py` - All defaults point to `storage/`
- `api/schemas/template/metadata_config.py` - Examples with `storage/`

## New File Paths (ID-Based)

### Before (media/ with Cyrillic):
```
media/user_000006/video/unprocessed/Демо-собеседования_(1_курс_ИИ).mp4
media/user_000006/video/processed/Демо-собеседования_(1_курс_ИИ)_processed.mp4
media/user_000006/audio/processed/Демо-собеседования_(1_курс_ИИ)_processed.mp3
media/user_000006/transcriptions/74/master.json
```

### After (storage/ with IDs):
```
storage/users/user_000006/recordings/74/source.mp4
storage/users/user_000006/recordings/74/video.mp4
storage/users/user_000006/recordings/74/audio.mp3
storage/users/user_000006/recordings/74/transcriptions/master.json
```

## API Changes

### ThumbnailManager Methods

**All methods now use `user_slug` instead of `user_id`:**

```python
from utils.thumbnail_manager import get_thumbnail_manager

manager = get_thumbnail_manager()

# OLD (removed):
manager.list_user_thumbnails(user.id)  # ❌ Deprecated

# NEW (required):
manager.list_user_thumbnails(user.user_slug)  # ✅ Only way
manager.get_user_thumbnails_dir(user.user_slug)
manager.get_thumbnail_path(user.user_slug, "thumbnail.png")
manager.delete_user_thumbnail(user.user_slug, "thumbnail.png")
```

**Supported image formats:** `.png`, `.jpg`, `.jpeg`

All listing methods (`list_user_thumbnails()`, `list_template_thumbnails()`) now find all supported formats, not just PNG.

**Paths returned:**
```python
# Shared templates:
manager.get_global_templates_dir()
# → storage/shared/thumbnails

# User thumbnails:
manager.get_user_thumbnails_dir(1)
# → storage/users/user_000001/thumbnails

# Template thumbnail:
manager.get_thumbnail_path(1, "hse_ai.png", fallback_to_template=True)
# → storage/shared/thumbnails/hse_ai.png
```

### TranscriptionManager Methods

**All methods now require `user_slug` (not optional):**

```python
manager = TranscriptionManager()

# OLD (removed):
manager.get_dir(recording_id, user_id=user_id)  # ❌ Deprecated

# NEW (required):
manager.get_dir(recording_id, user_slug)  # ✅ Only way
manager.save_master(recording_id, ..., user_slug)
manager.load_master(recording_id, user_slug)
manager.add_topics_version(recording_id, ..., user_slug)
```

**Getting user_slug:**
```python
# From recording:
user_slug = recording.owner.user_slug

# From user:
user_slug = user.user_slug
```

## Code Patterns

### File Upload Pattern

```python
from file_storage.path_builder import StoragePathBuilder
import shutil

storage_builder = StoragePathBuilder()

# 1. Save to temp
temp_path = storage_builder.create_temp_file(suffix=".mp4")
with temp_path.open("wb") as f:
    f.write(content)

# 2. Move to final location
final_path = storage_builder.recording_source(user_slug, recording_id)
final_path.parent.mkdir(parents=True, exist_ok=True)
shutil.move(str(temp_path), str(final_path))

# TODO(S3): Replace with backend.save() when S3 support added
```

### Path Generation Pattern

```python
from file_storage.path_builder import StoragePathBuilder

builder = StoragePathBuilder()

# Recording files (ID-based naming!)
source = builder.recording_source(user_slug, recording_id)
# → storage/users/user_000006/recordings/74/source.mp4

video = builder.recording_video(user_slug, recording_id)
# → storage/users/user_000006/recordings/74/video.mp4

# Transcriptions
master = builder.transcription_master(user_slug, recording_id)
# → storage/users/user_000006/recordings/74/transcriptions/master.json

# Temp files
temp = builder.create_temp_file(prefix="video_", suffix=".mp4")
# → storage/temp/video_abc12345.mp4

# Cleanup
builder.cleanup_temp(max_age_hours=24)  # Returns count of deleted files
```

## Migration Status

| Component | Status | Notes |
|-----------|--------|-------|
| StoragePathBuilder | ✅ Complete | Used in 8 files |
| ThumbnailManager | ✅ Complete | Uses StoragePathBuilder |
| StorageBackend | 🚧 Prepared | For S3 (not integrated) |
| LOCAL support | ✅ Complete | Direct Path operations |
| S3 support | 📋 Planned | Needs backend integration |
| File naming | ✅ Complete | ID-based (no display_name) |
| Code cleanup | ✅ Complete | No media/ paths |
| UserPathManager | ⚠️ Deprecated | Shows warning |

## Configuration

**Current (.env):**
```env
STORAGE_TYPE=LOCAL
STORAGE_LOCAL_PATH=storage
```

**Future (S3):**
```env
STORAGE_TYPE=S3
STORAGE_S3_BUCKET=my-bucket
STORAGE_S3_PREFIX=storage
STORAGE_S3_REGION=us-east-1
STORAGE_S3_ACCESS_KEY_ID=...
STORAGE_S3_SECRET_ACCESS_KEY=...
```

## Testing Checklist

- [ ] Register new user → verify directories created
- [ ] Upload recording → verify `source.mp4` at correct path
- [ ] Process video → verify `video.mp4` and `audio.mp3` created
- [ ] Transcribe → verify `transcriptions/master.json` created
- [ ] Extract topics → verify `topics.json` created
- [ ] Generate subtitles → verify `.srt` and `.vtt` files created
- [ ] Check logs → no Cyrillic encoding issues
- [ ] Verify `storage/temp/` cleanup works

## Breaking Changes

- **TranscriptionManager API:** All methods require `user_slug` (not optional)
- **UserPathManager:** Deprecated (shows warning, will be removed)
- **File paths:** Changed from `media/` to `storage/`

## Rollback

If needed:
1. Git revert to previous commit
2. Restore `media/` directory structure
3. Update `.env` if changed

## Next Steps

1. Test with new recordings (create → process → transcribe)
2. Monitor `storage/` directory growth
3. Set up periodic `storage/temp/` cleanup (cron job)
4. When S3 needed → implement backend integration (separate task)

---

**Implementation:** Following INSTRUCTIONS.md (KISS, DRY, YAGNI)  
**Documentation:** docs/STORAGE_STRUCTURE.md  
**History:** MIGRATION_COMPLETED.md
