    # 📁 Storage Structure - Final Design

**Version:** 2.1
**Date:** 2026-01-22
**Status:** Approved for implementation

**Changes in v2.1:**
- ✅ Removed `assets/` directory (all metadata in DB)
- ✅ Removed `temp/` directory (unused, system temp used instead)
- ✅ Single `extracted.json` with internal versioning (topics, summary from DeepSeek)
- ✅ Added `user_{slug}/thumbnails/` for user-uploaded thumbnails
- ✅ Added `STORAGE_TYPE` configuration (LOCAL/S3)
- ✅ Added storage quota parameters

---

## 🎯 Design Principles

1. **S3-Local Parity:** Абсолютно идентичная структура для local и S3
2. **Recording-Centric:** Все файлы одной записи в одном месте
3. **No Duplication:** Shared resources с fallback, не копировать
4. **Clear Lifecycle:** Файлы живут до expired статуса
5. **Breaking Change OK:** Полная реорганизация

---

## 📂 Directory Structure

### User ID Architecture

**Database**: Users table uses **ULID (26-character string)** as primary key
- Example: `01ARZ3NDEKTSV4RRFFQ69G5FAV`
- Benefits: Security (unpredictable), scalability, no enumeration attacks

**File System**: Uses **user_slug (6-digit integer)** for readable paths
- Example: `user_000001`, `user_000002`
- Mapping: `users.user_slug` auto-increments from sequence
- Benefits: Shorter paths, easier debugging, human-readable

```
storage/                             # Root (configurable: local path or S3 bucket)
│
├── shared/                          # Глобальные ресурсы (read-only для всех)
│   └── thumbnails/
│       ├── applied_python.png       # ~200KB each
│       ├── machine_learning.png
│       ├── big_data.png
│       └── ...                      # Total: 22 files (~5MB)
│
└── users/                           # User-specific storage
    └── user_{slug}/                 # 6-digit padded: user_000001, user_000002, etc.
        │
        ├── recordings/              # All recordings for this user
        │   └── {recording_id}/      # All files for one recording
        │       │
        │       ├── source.mp4       # Original video from Zoom/URL
        │       ├── video.mp4        # Processed/trimmed video
        │       ├── audio.mp3        # Extracted audio for transcription
        │       │
        │       └── transcriptions/  # All transcription-related files
        │           ├── master.json          # Full transcription with words & segments
        │           ├── extracted.json       # Topics + summary with versioning (v1, v2...)
        │           ├── subtitles.srt        # Subtitles (SRT format)
        │           └── subtitles.vtt        # Subtitles (VTT format)
        │
        └── thumbnails/              # User-uploaded custom thumbnails
            ├── custom_thumbnail_1.png
            ├── custom_thumbnail_2.png
            └── ...
```

---

## 🔑 Key Design Decisions

### 1. Why `storage/` instead of `media/`?

**Reasoning:**
- More professional and clear
- "Media" implies content, "Storage" implies infrastructure
- Easier to understand for DevOps (storage = files)

### 2. Why `recordings/{id}/` flat structure?

**Advantages:**
```python
# Easy cleanup - delete ALL files for recording:
shutil.rmtree(f"storage/users/{user_id}/recordings/{rec_id}")

# Easy size calculation:
def get_recording_size(user_id, rec_id):
    return sum(f.stat().st_size for f in Path(...).rglob("*") if f.is_file())

# Easy to find all files:
recording_files = list(Path(f"storage/users/{user_id}/recordings/{rec_id}").rglob("*"))
```

**vs Type-based:**
```python
# Hard cleanup - need to track multiple locations:
unlink(f"storage/users/{user_id}/videos/{rec_id}_original.mp4")
unlink(f"storage/users/{user_id}/videos/{rec_id}_processed.mp4")
unlink(f"storage/users/{user_id}/audio/{rec_id}.mp3")
rmtree(f"storage/users/{user_id}/transcriptions/{rec_id}")
# ❌ Error-prone, easy to miss files
```

### 3. Why `shared/` instead of `templates/`?

**Future-proof:**
```
shared/
├── thumbnails/        # Current
├── intros/           # Future: intro videos
├── outros/           # Future: outro videos
├── watermarks/       # Future: watermarks
└── backgrounds/      # Future: background music
```

### 4. Why simple filenames (`source.mp4` not `142_original.mp4`)?

**Reasoning:**
- Recording ID already in path: `recordings/142/`
- Shorter paths (better for logs, debugging)
- No encoding issues (no display_name in filename)
- Clear purpose: `source` = what we got, `video` = what we processed

### 5. Why no `temp/` directory?

**Reasoning:**
- Temporary files handled in system temp directories (`/tmp`, OS-managed)
- No need for persistent temp storage in our structure
- FFmpeg and processing tools work directly with source/destination paths
- Cleaner structure, no orphaned temp files

---

## 📋 File Naming Conventions

### Video Files
- `source.mp4` - Original video (from Zoom, URL, upload)
- `video.mp4` - Processed video (trimmed, converted)

### Audio Files
- `audio.mp3` - Extracted audio (64kbps, mono, 16kHz for transcription)

### Transcription Files
- `master.json` - Full transcription (words, segments, summary, metadata)
- `extracted.json` - Topics + summary extraction with internal versioning (v1, v2, v3...)
- `subtitles.{format}` - Subtitles (srt, vtt, etc)

### User Thumbnails
- User-uploaded custom thumbnails stored in `users/{user_slug}/thumbnails/`
- All metadata (tags, notes, etc.) stored in database

---

## 🔄 Lifecycle Management

### File Retention Policy

| File Type | Retention | Notes |
|-----------|-----------|-------|
| `source.mp4` | Until expired | Original for re-processing |
| `video.mp4` | Until expired | For uploads/re-uploads |
| `audio.mp3` | Until expired | For re-transcription |
| `transcriptions/*` | Until expired | For API responses |
| `thumbnails/*` | Until deleted | User custom thumbnails |

### Expired Status Cleanup

```python
# When recording.status = EXPIRED:
1. Delete storage/users/{user_id}/recordings/{recording_id}/
2. Update quota_usage (decrement storage_bytes)
3. Delete DB record
```

---

## 🌐 Storage Backend Selection

### Configuration (.env)

```env
# Storage type: LOCAL or S3
STORAGE_TYPE=LOCAL

# LOCAL storage settings
STORAGE_LOCAL_PATH=storage/
STORAGE_LOCAL_MAX_SIZE_GB=1000        # Max storage quota (optional)

# S3 storage settings
STORAGE_S3_BUCKET=my-bucket
STORAGE_S3_PREFIX=storage/
STORAGE_S3_REGION=us-east-1
STORAGE_S3_MAX_SIZE_GB=5000           # Max bucket usage (optional)
STORAGE_S3_ACCESS_KEY_ID=...          # AWS credentials
STORAGE_S3_SECRET_ACCESS_KEY=...
```

### Path Compatibility

#### Local Path
```python
Path("storage/users/user_000005/recordings/142/source.mp4")
```

#### S3 Path (identical structure!)
```python
s3://my-bucket/storage/users/user_000005/recordings/142/source.mp4
```

**Structure is 100% identical after the prefix!**

### Implementation

```python
# storage/backends/base.py
class StorageBackend(ABC):
    @abstractmethod
    async def save(self, path: str, content: bytes) -> str:
        """Save file, return full path"""

    @abstractmethod
    async def load(self, path: str) -> bytes:
        """Load file content"""

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete file"""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file exists"""

# storage/backends/local.py
class LocalStorageBackend(StorageBackend):
    def __init__(self, base_path: str = "storage", max_size_gb: int | None = None):
        self.base = Path(base_path)
        self.max_size_gb = max_size_gb

    async def save(self, path: str, content: bytes) -> str:
        # Check quota if configured
        if self.max_size_gb:
            current_size = self._get_total_size()
            if current_size + len(content) > self.max_size_gb * (1024**3):
                raise StorageQuotaExceededError()

        full_path = self.base / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(full_path)

# storage/backends/s3.py
class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        bucket: str,
        prefix: str = "storage",
        region: str = "us-east-1",
        max_size_gb: int | None = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.region = region
        self.max_size_gb = max_size_gb

    async def save(self, path: str, content: bytes) -> str:
        s3_key = f"{self.prefix}/{path}"
        await s3.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=content,
            ServerSideEncryption='AES256',  # Enable encryption
        )
        return f"s3://{self.bucket}/{s3_key}"

# storage/factory.py
def create_storage_backend() -> StorageBackend:
    """Create storage backend based on STORAGE_TYPE environment variable"""
    storage_type = os.getenv("STORAGE_TYPE", "LOCAL").upper()

    if storage_type == "LOCAL":
        return LocalStorageBackend(
            base_path=os.getenv("STORAGE_LOCAL_PATH", "storage"),
            max_size_gb=int(os.getenv("STORAGE_LOCAL_MAX_SIZE_GB", 0)) or None,
        )
    elif storage_type == "S3":
        return S3StorageBackend(
            bucket=os.getenv("STORAGE_S3_BUCKET"),
            prefix=os.getenv("STORAGE_S3_PREFIX", "storage"),
            region=os.getenv("STORAGE_S3_REGION", "us-east-1"),
            max_size_gb=int(os.getenv("STORAGE_S3_MAX_SIZE_GB", 0)) or None,
        )
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")
```

---

## 📝 Topics.json Versioning

Instead of separate files (`topics_v1.json`, `topics_v2.json`), we use a **single `extracted.json` file with internal versioning**:

```json
{
  "recording_id": 74,
  "active_version": "v4",
  "versions": [
    {
      "id": "v1",
      "model": "deepseek",
      "granularity": "long",
      "created_at": "2026-01-13T22:40:16.733544",
      "is_active": false,
      "main_topics": ["Topic 1", "Topic 2"],
      "topic_timestamps": [
        {"topic": "Introduction", "start": 0.0, "end": 120.0}
      ],
      "pauses": [],
      "_metadata": {"model": "deepseek", "config": {...}}
    },
    {
      "id": "v4",
      "model": "deepseek",
      "granularity": "long",
      "created_at": "2026-01-13T23:17:57.731738",
      "is_active": true,
      "main_topics": ["Updated Topic 1"],
      "topic_timestamps": [
        {"topic": "Intro", "start": 0.0, "end": 106.0}
      ],
      "_metadata": {...}
    }
  ]
}
```

**Benefits:**
- ✅ Single file to manage (no topics_v1, topics_v2, etc.)
- ✅ Easy to switch between versions (update `active_version`)
- ✅ Full history preserved in one place
- ✅ Atomic updates (no race conditions)
- ✅ Already implemented in `transcription_module/manager.py`!

---

## 🛠️ StoragePathBuilder API

```python
from storage.path_builder import StoragePathBuilder

builder = StoragePathBuilder()

# Shared resources
builder.shared_thumbnail("ml_extra.png")
# → "storage/shared/thumbnails/ml_extra.png"

# Recording files
builder.recording_source(user_id=5, recording_id=142)
# → "storage/users/5/recordings/142/source.mp4"

builder.recording_video(user_id=5, recording_id=142)
# → "storage/users/5/recordings/142/video.mp4"

builder.transcription_master(user_id=5, recording_id=142)
# → "storage/users/5/recordings/142/transcription/master.json"

builder.transcription_extracted(user_slug=5, recording_id=142)
# → "storage/users/5/recordings/142/transcriptions/extracted.json"

builder.user_thumbnail(user_id=5, filename="custom_thumbnail_1.png")
# → "storage/users/5/thumbnails/custom_thumbnail_1.png"

# Helpers
builder.delete_recording_files(user_id=5, recording_id=142)
# Deletes entire recording directory

builder.get_recording_size(user_id=5, recording_id=142)
# Returns total size in bytes
```

---

## 📊 Migration from Old Structure

### Before (media/)
```
media/
├── data.db                          # ❌ Wrong place
├── video/                           # ❌ Legacy
├── transcriptions/                  # ❌ Legacy
├── templates/thumbnails/            # ✅ Keep as shared
└── user_4/
    ├── video/
    │   ├── unprocessed/
    │   │   └── Тюлягин_GenDL_25-12-25_12-55.mp4
    │   └── processed/
    │       └── Тюлягин_GenDL_25-12-25_12-55_processed.mp4
    ├── audio/processed/
    │   └── Тюлягин_GenDL_25-12-25_12-55_processed.mp3
    ├── processed_audio/             # ❌ Duplicate
    └── transcriptions/
        └── 21/
            ├── master.json
            └── topics_v1.json
```

### After (storage/)
```
storage/
├── shared/
│   └── thumbnails/                  # Moved from media/templates
└── users/
    └── 4/
        └── recordings/
            └── 21/                  # Clean, organized
                ├── source.mp4       # From unprocessed
                ├── video.mp4        # From processed
                ├── audio.mp3        # From audio/processed
                └── transcriptions/
                    ├── master.json
                    └── extracted.json  # Versioned internally!
```

### Migration Script

```bash
# Run migration
python scripts/migrate_to_new_structure.py

# Before:
$ du -sh media/
5.2G    media/

# After:
$ du -sh storage/
4.1G    storage/         # ~20% smaller (no duplicates!)
```

---

## ✅ Benefits Summary

| Aspect | Old (media/) | New (storage/) |
|--------|-------------|----------------|
| Structure | Inconsistent | Consistent |
| Duplication | audio/ + processed_audio/ | Single audio.mp3 |
| Cleanup | Manual, error-prone | `rm -rf recordings/{id}` |
| S3 Migration | Complex | Copy structure as-is |
| File Finding | Search multiple dirs | Single recording dir |
| Size Calculation | Walk all dirs | Single directory walk |
| Encoding Issues | Cyrillic in filenames | Only IDs in paths |
| Quota Tracking | Manual calculation | Automatic on save/delete |
| Topics/Summary | Multiple files (topics_v1, v2...) | Single extracted.json with versioning |
| Temp Files | temp/ directory (unused) | System temp (cleaner) |
| Metadata | metadata.json in assets/ | All in database |
| Storage Backend | Hardcoded local | Switchable LOCAL/S3 |

---

## 🚀 Implementation Checklist

### Phase 1: Configuration
- [ ] Add `STORAGE_TYPE` to `.env.example`
- [ ] Update `config/settings.py` with StorageSettings
- [ ] Add validation for storage configuration

### Phase 2: Storage Backends
- [ ] Create `storage/` module directory
- [ ] Create `storage/backends/base.py` (abstract StorageBackend)
- [ ] Create `storage/backends/local.py` (LocalStorageBackend)
- [ ] Create `storage/backends/s3.py` (S3StorageBackend - PHASE 5)
- [ ] Create `storage/factory.py` (backend factory)

### Phase 3: Path Builder
- [ ] Create `storage/path_builder.py` (StoragePathBuilder)
- [ ] Add methods for all path types (recordings, thumbnails, etc.)
- [ ] Integrate with storage backends

### Phase 4: Migration
- [ ] Create migration script `scripts/migrate_to_new_structure.py`
- [ ] Test migration on dev environment
- [ ] Update `utils/user_paths.py` to use new structure
- [ ] Update all file operations to use StoragePathBuilder
- [ ] Update database paths

### Phase 5: Deployment
- [ ] Run migration on production
- [ ] Verify all files migrated correctly
- [ ] Monitor for 24h
- [ ] Archive old `media/` directory
- [ ] Update all documentation

---

**Status:** Ready for implementation
**Estimated time:** 1 day (migration included)
**Breaking change:** Yes (acceptable per requirements)
