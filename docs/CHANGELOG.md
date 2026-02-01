# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### ✨ Added

- **Bulk Dry-Run: Start Time Field** - Added `start_time` to bulk dry-run response
  - `/api/v1/recordings/bulk/run?dry_run=true` now includes `start_time` field for each recording
  - Format: ISO 8601 datetime string (e.g., `"2026-01-27T10:30:00"`)
  - Helps identify recordings by their conference start time in bulk operations
  - Updated documentation: `docs/BULK_OPERATIONS_GUIDE.md`

## [0.9.4] - 2026-01-23

### 🔧 Fixed

- **ThumbnailManager Storage Migration** - Completed migration to new storage structure
  - `ThumbnailManager` now uses `StoragePathBuilder` for all path operations
  - Fixed `/api/v1/thumbnails` endpoint returning old `media/` paths
  - All thumbnail paths now use new structure: `storage/shared/thumbnails/` and `storage/users/user_XXXXXX/thumbnails/`
  - Breaking change: All `ThumbnailManager` methods now require `user_slug` instead of `user_id`
  - Updated API endpoints: `api/routers/thumbnails.py` and `api/routers/auth.py`
  
- **ThumbnailManager Multi-Format Support** - Fixed listing methods to find all image formats
  - `list_user_thumbnails()` now finds `.png`, `.jpg`, and `.jpeg` files (was only `.png`)
  - `list_template_thumbnails()` now finds `.png`, `.jpg`, and `.jpeg` files (was only `.png`)
  - `initialize_user_thumbnails()` now copies all image formats from templates (was only `.png`)
  - Fixes issue where API returned empty arrays when user had only JPG/JPEG thumbnails

### 🔒 Security

- **Thumbnail API Security Improvements** - No filesystem path disclosure
  - **Breaking change:** API now returns `url` instead of `path` in responses
  - Changed: `{"path": "storage/users/..."}` → `{"url": "/api/v1/thumbnails/file.jpg"}`
  - Benefits: No information disclosure, better encapsulation, user enumeration prevented
  - Centralized format validation with `SUPPORTED_IMAGE_FORMATS` constant
  - Documentation: `docs/THUMBNAILS_SECURITY.md`

### 🗑️ Removed

- **Thumbnail API Simplification** - Removed `template_thumbnails` from response
  - **Breaking change:** Removed `include_templates` query parameter from GET `/api/v1/thumbnails`
  - **Breaking change:** Response schema changed from `{user_thumbnails, template_thumbnails}` to `{thumbnails}`
  - Rationale: Users get template copies at registration, no need to show shared templates separately
  - Simpler and clearer API - one array instead of two

### 📝 Changed

- **Templates & Presets: Thumbnail Path Format** - Filename-only approach
  - **Breaking change:** `thumbnail_path` now stores only filename, not full path
  - Old: `"thumbnail_path": "/data/thumbnails/default.jpg"` ❌
  - New: `"thumbnail_path": "ml_extra.png"` ✅
  - API automatically resolves filename to user's thumbnail directory
  - Updated schemas: `metadata_config.py`, `preset_metadata.py`
  - Updated upload logic: `api/tasks/upload.py` now uses `ThumbnailManager` for resolution
  - See `docs/THUMBNAILS_SECURITY.md` for usage examples

- **User Registration: Thumbnail Templates** - Each user gets own copies
  - At registration, all 22 shared templates are copied to user's directory
  - Users can modify, rename, or delete their copies independently
  - No naming conflicts - each user has their own namespace
  - Backward compatible: fallback to shared templates for old users

## [0.9.4] - 2026-01-22

### 🚀 MAJOR REFACTORING: Storage Structure Migration

Complete redesign of file storage system from `media/` to `storage/` with ID-based naming.

#### Added

- **New `file_storage/` Python module** - Clean separation of code and data
  - `file_storage/path_builder.py` - Centralized path generation (StoragePathBuilder)
  - `file_storage/backends/` - Abstract storage backend system (LOCAL/S3-ready)
    - `file_storage/backends/base.py` - StorageBackend interface
    - `file_storage/backends/local.py` - LocalStorageBackend implementation
  - `file_storage/factory.py` - Backend factory with singleton pattern

- **New `storage/` directory** - Pure data storage (media files only)
  - `storage/shared/thumbnails/` - Shared thumbnails (22 files migrated)
  - `storage/temp/` - Temporary processing files (auto-cleanup)
  - `storage/users/user_XXXXXX/recordings/NN/` - User recordings by ID

- **ID-based file naming** - No more Cyrillic or display_name in paths
  ```
  storage/users/user_000006/recordings/74/
  ├── source.mp4           # Original recording
  ├── video.mp4            # Processed video
  ├── audio.mp3            # Extracted audio
  └── transcriptions/      # All transcription data
      ├── master.json
      ├── topics.json
      └── cache/
          ├── segments.txt
          └── words.txt
  ```

- **StorageSettings** in `config/settings.py`
  - `storage_type: "LOCAL" | "S3"` - Backend selection
  - `local_path: str` - Path to storage directory
  - `local_max_size_gb: int` - Optional quota limit

- **Documentation**
  - `docs/STORAGE_STRUCTURE.md` v2.1 - Complete specification
  - `STORAGE_STRUCTURE_IMPLEMENTED.md` - Implementation guide
  - `LEGACY_CLEANUP_COMPLETE.md` - Legacy removal details
  - `MIGRATION_COMPLETED.md` - Migration history

#### Changed

- **ALL file paths now use StoragePathBuilder** (11 files updated)
  - `api/routers/recordings.py` - Upload via temp → source.mp4
  - `api/routers/auth.py` - User directory creation on registration
  - `api/tasks/processing.py` - All processing paths
  - `transcription_module/manager.py` - **BREAKING:** user_slug now required (not optional)
  - `video_download_module/downloader.py` - Download to ID-based paths
  - `video_processing_module/video_processor.py` - Accept output_path parameter
  - `video_processing_module/config.py` - Defaults to `storage/temp`
  - `api/schemas/config_types.py` - storage/ paths in examples
  - `api/schemas/template/metadata_config.py` - storage/ paths in examples

- **TranscriptionManager API** - user_slug is now mandatory
  ```python
  # OLD (removed):
  manager.get_dir(recording_id, user_id=user_id)  # ❌
  
  # NEW (required):
  manager.get_dir(recording_id, user_slug)  # ✅
  ```

- **Module structure** - Code separated from data
  ```
  # OLD:
  storage/
  ├── __init__.py          # Code mixed with data ❌
  ├── path_builder.py
  ├── backends/
  └── shared/thumbnails/   # Data

  # NEW:
  file_storage/            # Python module (code) ✅
  ├── __init__.py
  ├── path_builder.py
  ├── factory.py
  └── backends/
      ├── base.py
      └── local.py
  
  storage/                 # Data only ✅
  ├── shared/thumbnails/
  ├── temp/
  └── users/
  ```

#### Removed

- **ALL legacy code and backward compatibility**
  - `utils/user_paths.py` (5571 bytes) - UserPathManager class
  - `transcription_module/service.py` - TranscriptionService class
  - `scripts/migrate_media_to_storage.py` - One-time migration script
  - `config.settings.media_root` - Legacy field
  - Fallback logic for old `media/` directories in `api/tasks/processing.py`
  - All "backward compatibility" comments and code paths

#### Breaking Changes

⚠️ **API Changes:**
- `TranscriptionManager` methods require `user_slug` (int), not `user_id` (str/ULID)
- No fallback search in old `media/` directories
- Old recordings must be migrated or will fail with clear errors

⚠️ **Configuration Changes:**
- Removed: `settings.media_root`
- Required: `STORAGE_TYPE=LOCAL` in `.env`
- Required: `STORAGE_LOCAL_PATH=storage` in `.env`

⚠️ **Import Changes:**
```python
# OLD:
from storage.path_builder import StoragePathBuilder  # ❌

# NEW:
from file_storage.path_builder import StoragePathBuilder  # ✅
```

#### Migration Guide

**For existing deployments:**

1. Run migration script (if available) or re-process recordings
2. Update `.env` file:
   ```env
   STORAGE_TYPE=LOCAL
   STORAGE_LOCAL_PATH=storage
   ```
3. Update any custom code using old imports
4. Verify new recordings work correctly
5. Archive or delete old `media/` directory

**For new deployments:**

Just set environment variables - everything works out of the box!

#### Technical Details

**Principles Followed:**
- ✅ **KISS** - Simple Path operations for LOCAL storage
- ✅ **DRY** - StoragePathBuilder as single source of truth
- ✅ **YAGNI** - Backends prepared but not integrated (until S3 needed)
- ✅ **Clean Architecture** - No fallbacks, clear error messages

**Performance:**
- No filesystem searches in old directories
- Direct path resolution
- Faster file operations

**Maintainability:**
- Less code to maintain (2 files deleted, ~6000 bytes removed)
- No confusing fallback logic
- Single source of truth for all paths
- Ready for S3 integration (2-3 hours estimated)

**Code Quality:**
- ✅ No F-type linting errors (undefined names, imports)
- ✅ All modules compile successfully
- ✅ No legacy imports or references
- ✅ StoragePathBuilder used consistently (7 files)

#### Future Work

**S3 Integration** (when needed):
1. Implement `file_storage/backends/s3.py` (S3StorageBackend)
2. Integrate backends throughout codebase
3. Replace Path operations with `backend.save/load/delete`
4. Add S3 settings to `.env`
5. Test with S3-compatible storage

**Estimated effort:** 2-3 hours

---

## Previous Versions

For changes before v2.0.0, see git history and `docs/archive/` directory.
