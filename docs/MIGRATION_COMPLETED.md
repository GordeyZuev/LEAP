# Storage Migration Completed ✅

**Date:** 2026-01-22  
**Migration:** `media/` → `storage/`  
**Status:** ✅ Completed Successfully

## Summary

Successfully migrated from legacy `media/` structure to new `storage/` structure with **ID-based file naming** (no `display_name` in paths).

## What Changed

### File Structure

**Before:**
```
media/user_000006/video/unprocessed/Демо-собеседования_(1_курс_ИИ)_25-12-29_15-01.mp4
media/user_000006/video/processed/Демо-собеседования_(1_курс_ИИ)_25-12-29_15-01_processed.mp4
media/user_000006/audio/processed/Демо-собеседования_(1_курс_ИИ)_25-12-29_15-01_processed.mp3
media/user_000006/transcriptions/74/master.json
```

**After:**
```
storage/users/user_000006/recordings/74/source.mp4
storage/users/user_000006/recordings/74/video.mp4
storage/users/user_000006/recordings/74/audio.mp3
storage/users/user_000006/recordings/74/transcriptions/master.json
```

### Key Benefits

1. ✅ **No encoding issues** - No Cyrillic/special chars in file paths
2. ✅ **Shorter paths** - Recording ID already in path
3. ✅ **Easy cleanup** - Single command: `rm -rf recordings/{id}`
4. ✅ **S3-ready** - Structure identical for local and S3
5. ✅ **Organized** - All recording files in one directory

## New Modules

### Storage Module

- `storage/backends/base.py` - Abstract interface for storage backends
- `storage/backends/local.py` - Local filesystem implementation
- `storage/factory.py` - Backend factory with singleton pattern
- `storage/path_builder.py` - Centralized path generation (ID-based)

### Path Builder API

```python
from storage.path_builder import StoragePathBuilder

builder = StoragePathBuilder()

# Recording files (ID-based naming!)
builder.recording_source(user_slug=6, recording_id=74)
# → storage/users/user_000006/recordings/74/source.mp4

builder.recording_video(user_slug=6, recording_id=74)
# → storage/users/user_000006/recordings/74/video.mp4

builder.recording_audio(user_slug=6, recording_id=74)
# → storage/users/user_000006/recordings/74/audio.mp3

# Transcriptions
builder.transcription_master(user_slug=6, recording_id=74)
# → storage/users/user_000006/recordings/74/transcriptions/master.json

# Cleanup
builder.delete_recording_files(user_slug=6, recording_id=74)
# Deletes entire recordings/74/ directory
```

## Updated Code

### video_download_module/downloader.py
- ✅ Constructor now takes `user_slug` and `StoragePathBuilder`
- ✅ Removed `_get_filename()` method (no more display_name in paths!)
- ✅ Downloads directly to `source.mp4`

### api/tasks/processing.py
- ✅ Uses `StoragePathBuilder` for all paths
- ✅ Explicit output paths (no filename generation from title)
- ✅ Audio extracted to `audio.mp3` (ID-based)

### transcription_module/manager.py
- ✅ Added `user_slug` parameter to all methods
- ✅ Uses `StoragePathBuilder` when user_slug provided
- ✅ Backward compatible with legacy `user_id`

### utils/user_paths.py
- ⚠️ Deprecated with warning
- ✅ Still works for backward compatibility
- 🔄 Migrate to `StoragePathBuilder` over time

## Migration Script

**Location:** `scripts/migrate_media_to_storage.py`

```bash
# Preview (safe, no changes)
uv run python scripts/migrate_media_to_storage.py --dry-run

# Actual migration
uv run python scripts/migrate_media_to_storage.py
```

**Features:**
- Migrates all recording files from media/ to storage/
- Updates database paths automatically
- Copies shared thumbnails
- Safe dry-run mode
- Progress logging

## Backups Created

- **Database:** `backup_before_migration_20260122_022037.sql`
- **Media:** `media_backup_20260122_022052.tar.gz` (71MB)

## Migration Results

- ✅ 22 thumbnails migrated to `storage/shared/thumbnails/`
- ✅ 0 recordings (dev database empty)
- ✅ Database paths updated
- ✅ No errors

## Configuration

Storage settings in `.env`:

```env
# Storage backend type
STORAGE_TYPE=LOCAL

# Local storage settings
STORAGE_LOCAL_PATH=storage
# STORAGE_LOCAL_MAX_SIZE_GB=1000  # Optional quota

# S3 settings (for future)
# STORAGE_TYPE=S3
# STORAGE_S3_BUCKET=my-bucket
# STORAGE_S3_PREFIX=storage
# ...
```

## Testing Checklist

### For New Recordings

- [ ] Download → verify `source.mp4` created at correct path
- [ ] Process → verify `video.mp4` created
- [ ] Extract audio → verify `audio.mp3` created
- [ ] Transcribe → verify `transcriptions/master.json` created
- [ ] Extract topics → verify `transcriptions/topics.json` created
- [ ] Generate subtitles → verify `.srt` and `.vtt` files created

### Path Verification

```bash
# Check structure
ls -la storage/users/user_XXXXXX/recordings/{id}/

# Should see:
# - source.mp4 (original video)
# - video.mp4 (processed video)
# - audio.mp3 (extracted audio)
# - transcriptions/ (directory)
```

## Production Rollout

### Before Migration

1. **Backup everything:**
   ```bash
   pg_dump zoom_manager > backup_before_migration.sql
   tar -czf media_backup.tar.gz media/
   ```

2. **Check disk space:**
   ```bash
   df -h
   du -sh media/
   ```

3. **Test dry-run:**
   ```bash
   uv run python scripts/migrate_media_to_storage.py --dry-run
   ```

### During Migration

1. **Stop services** (optional but recommended)
2. **Run migration:**
   ```bash
   uv run python scripts/migrate_media_to_storage.py
   ```
3. **Verify structure:**
   ```bash
   ls -la storage/users/
   ```

### After Migration

1. **Restart services**
2. **Monitor logs** for 24h
3. **Test new recordings** through full pipeline
4. **Verify old recordings** still accessible

### Cleanup (After 24h)

```bash
# Archive old media/ directory
tar -czf media_archive_$(date +%Y%m%d).tar.gz media/
mv media/ media_archive/
```

## Rollback Plan

If issues arise:

1. Stop services
2. Restore database: `psql zoom_manager < backup_before_migration.sql`
3. Remove storage/: `rm -rf storage/`
4. Restore media/: `tar -xzf media_backup.tar.gz`
5. Revert code changes (git reset)
6. Restart services

## Documentation

- **Storage Structure:** `docs/STORAGE_STRUCTURE.md`
- **Migration Plan:** `.cursor/plans/storage_structure_migration_*.plan.md`
- **Instructions:** `INSTRUCTIONS.md` (KISS, DRY, YAGNI principles)

## Support

For issues or questions:
- Check logs in `logs/`
- Review migration script output
- Inspect database paths: `SELECT id, local_video_path, processed_video_path FROM recordings LIMIT 5;`

---

**Migration Team:** AI Assistant  
**Reviewed By:** _[To be filled]_  
**Approved By:** _[To be filled]_
