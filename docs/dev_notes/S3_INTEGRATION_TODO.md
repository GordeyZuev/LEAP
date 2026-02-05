# S3 Integration TODO

**Version:** v0.9.4
**Date:** 2026-01-22
**Status:** 🚧 Ready for S3 Implementation
**Estimated Time:** 2-3 hours

---

## 📋 Current Status

### ✅ COMPLETED (v0.9.4)

**Storage Architecture:**
- ✅ `file_storage/` module created (code separated from data)
- ✅ `StorageBackend` abstract interface
- ✅ `LocalStorageBackend` implementation (with aiofiles)
- ✅ `StoragePathBuilder` - single source of truth for paths
- ✅ Backend factory with singleton pattern
- ✅ Clean `storage/` directory (only media files)

**Code Quality:**
- ✅ ID-based file naming (no Cyrillic in paths)
- ✅ All legacy code removed (UserPathManager, TranscriptionService)
- ✅ user_slug required (no optional parameters)
- ✅ All imports updated to `file_storage.*`
- ✅ Linting passed (F,E,W,N,A rules)

**Current Structure:**
```
file_storage/              # Python module (code)
├── path_builder.py       # StoragePathBuilder class
├── factory.py            # Backend factory + singleton
└── backends/
    ├── base.py           # StorageBackend interface
    └── local.py          # LocalStorageBackend (aiofiles)

storage/                   # Data directory (media files only)
├── shared/thumbnails/    # 22 shared thumbnails
├── temp/                 # Temporary processing files
└── users/user_XXXXXX/    # User recordings (ID-based)
```

---

## 🚀 TODO for S3 Integration

### PHASE 1: S3 Backend Implementation (1 hour)

**1.1 Create S3StorageBackend**

```bash
# Create file: file_storage/backends/s3.py
```

**Implementation requirements:**

```python
"""S3 storage backend using boto3"""

from pathlib import Path
import aioboto3
from botocore.exceptions import ClientError

from file_storage.backends.base import StorageBackend, StorageQuotaExceededError
from logger import get_logger

logger = get_logger(__name__)


class S3StorageBackend(StorageBackend):
    """S3 storage backend implementation"""

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "storage",
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
        max_size_gb: int | None = None,
    ):
        """
        Initialize S3 backend.

        Args:
            bucket_name: S3 bucket name
            prefix: Prefix for all keys (default: "storage")
            region: AWS region
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            endpoint_url: Custom endpoint URL (for S3-compatible services)
            max_size_gb: Maximum storage size in GB (optional)
        """
        self.bucket_name = bucket_name
        self.prefix = prefix.rstrip("/")
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url
        self.max_size_gb = max_size_gb

        # Create boto3 session config
        self.session_config = {
            "region_name": region,
        }
        if access_key_id and secret_access_key:
            self.session_config.update({
                "aws_access_key_id": access_key_id,
                "aws_secret_access_key": secret_access_key,
            })

    def _get_s3_key(self, path: str) -> str:
        """Convert local path to S3 key"""
        return f"{self.prefix}/{path}"

    async def save(self, path: str, content: bytes) -> str:
        """Save file to S3"""
        # Check quota if enabled
        if self.max_size_gb is not None:
            current_size = await self.get_total_size()
            if current_size + len(content) > self.max_size_gb * (1024**3):
                raise StorageQuotaExceededError(
                    f"Storage quota exceeded: {current_size / (1024**3):.2f}GB / {self.max_size_gb}GB"
                )

        s3_key = self._get_s3_key(path)

        session = aioboto3.Session(**self.session_config)
        async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
            try:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=content,
                )
                logger.info(f"Saved to S3: s3://{self.bucket_name}/{s3_key}")
                return s3_key
            except ClientError as e:
                logger.error(f"Failed to save to S3: {e}")
                raise

    async def load(self, path: str) -> bytes:
        """Load file from S3"""
        s3_key = self._get_s3_key(path)

        session = aioboto3.Session(**self.session_config)
        async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                content = await response["Body"].read()
                return content
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    raise FileNotFoundError(f"File not found: s3://{self.bucket_name}/{s3_key}")
                logger.error(f"Failed to load from S3: {e}")
                raise

    async def delete(self, path: str) -> None:
        """Delete file from S3"""
        s3_key = self._get_s3_key(path)

        session = aioboto3.Session(**self.session_config)
        async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
            try:
                await s3.delete_object(Bucket=self.bucket_name, Key=s3_key)
                logger.info(f"Deleted from S3: s3://{self.bucket_name}/{s3_key}")
            except ClientError as e:
                logger.error(f"Failed to delete from S3: {e}")
                raise

    async def exists(self, path: str) -> bool:
        """Check if file exists in S3"""
        s3_key = self._get_s3_key(path)

        session = aioboto3.Session(**self.session_config)
        async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
            try:
                await s3.head_object(Bucket=self.bucket_name, Key=s3_key)
                return True
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    return False
                raise

    async def get_size(self, path: str) -> int:
        """Get file size in bytes"""
        s3_key = self._get_s3_key(path)

        session = aioboto3.Session(**self.session_config)
        async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
            try:
                response = await s3.head_object(Bucket=self.bucket_name, Key=s3_key)
                return response["ContentLength"]
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    raise FileNotFoundError(f"File not found: s3://{self.bucket_name}/{s3_key}")
                raise

    async def get_total_size(self) -> int:
        """Get total size of all files in storage"""
        total_size = 0
        prefix = f"{self.prefix}/"

        session = aioboto3.Session(**self.session_config)
        async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        total_size += obj["Size"]

        return total_size
```

**1.2 Update factory.py**

Add S3 backend creation:

```python
# In file_storage/factory.py

def create_storage_backend() -> StorageBackend:
    """Create storage backend based on settings."""
    settings = get_settings()
    storage_type = settings.storage.storage_type.upper()

    logger.info(f"Creating storage backend: type={storage_type}")

    if storage_type == "LOCAL":
        from pathlib import Path
        base_path = Path(settings.storage.local_path)
        max_size_gb = settings.storage.local_max_size_gb
        backend = LocalStorageBackend(base_path=base_path, max_size_gb=max_size_gb)
        logger.info(f"LOCAL storage backend created: path={base_path} | max_size={max_size_gb}GB")
        return backend

    if storage_type == "S3":
        from file_storage.backends.s3 import S3StorageBackend

        backend = S3StorageBackend(
            bucket_name=settings.storage.s3_bucket,
            prefix=settings.storage.s3_prefix,
            region=settings.storage.s3_region,
            access_key_id=settings.storage.s3_access_key_id,
            secret_access_key=settings.storage.s3_secret_access_key,
            endpoint_url=settings.storage.s3_endpoint_url,
            max_size_gb=settings.storage.s3_max_size_gb,
        )
        logger.info(f"S3 storage backend created: bucket={settings.storage.s3_bucket} | prefix={settings.storage.s3_prefix}")
        return backend

    raise ValueError(f"Unknown storage type: {storage_type}. Supported types: LOCAL, S3")
```

**1.3 Add dependencies**

```bash
# Add to pyproject.toml or requirements.txt
aioboto3>=12.0.0
boto3>=1.34.0
botocore>=1.34.0
```

### PHASE 2: Replace Path Operations (1-2 hours)

**Current:** Direct Path operations
**Target:** Use `backend.save/load/delete` everywhere

**Files to update:**

1. **api/routers/recordings.py** - File upload
   ```python
   # BEFORE:
   temp_path.write_bytes(content)
   shutil.move(str(temp_path), str(final_path))

   # AFTER:
   backend = get_storage_backend()
   await backend.save(relative_path, content)
   ```

2. **api/tasks/processing.py** - Video/audio processing
   ```python
   # BEFORE:
   with open(audio_path, "rb") as f:
       content = f.read()

   # AFTER:
   backend = get_storage_backend()
   content = await backend.load(relative_path)
   ```

3. **transcription_module/manager.py** - Transcription files
   ```python
   # BEFORE:
   path.write_text(json.dumps(data), encoding="utf-8")

   # AFTER:
   backend = get_storage_backend()
   content = json.dumps(data).encode("utf-8")
   await backend.save(relative_path, content)
   ```

4. **video_download_module/downloader.py** - Downloads
5. **video_processing_module/video_processor.py** - FFmpeg output
6. **api/routers/auth.py** - User directory creation

**Pattern to follow:**

```python
from file_storage.factory import get_storage_backend
from file_storage.path_builder import StoragePathBuilder

storage_builder = StoragePathBuilder()
backend = get_storage_backend()

# For save:
relative_path = storage_builder.recording_source(user_slug, recording_id)
await backend.save(str(relative_path), content)

# For load:
content = await backend.load(str(relative_path))

# For delete:
await backend.delete(str(relative_path))

# For exists check:
exists = await backend.exists(str(relative_path))
```

### PHASE 3: Configuration (15 min)

**Update .env:**

```bash
# Storage Configuration
STORAGE_TYPE=S3  # or LOCAL

# S3 Configuration (if STORAGE_TYPE=S3)
STORAGE_S3_BUCKET=my-leap-bucket
STORAGE_S3_PREFIX=storage
STORAGE_S3_REGION=us-east-1
STORAGE_S3_ACCESS_KEY_ID=your_access_key
STORAGE_S3_SECRET_ACCESS_KEY=your_secret_key
STORAGE_S3_ENDPOINT_URL=  # Optional, for S3-compatible services
STORAGE_S3_MAX_SIZE_GB=100  # Optional quota
```

**Already configured in config/settings.py:**
```python
class StorageSettings(BaseSettings):
    storage_type: str = "LOCAL"

    # S3 settings (already exist)
    s3_bucket: str = Field(default="", description="S3 bucket name")
    s3_prefix: str = Field(default="storage", description="S3 prefix")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    s3_max_size_gb: int | None = Field(default=None, ge=1, description="Max S3 storage size (GB)")
    s3_access_key_id: str | None = Field(default=None, description="AWS access key ID")
    s3_secret_access_key: str | None = Field(default=None, description="AWS secret access key")
    s3_endpoint_url: str | None = Field(default=None, description="Custom S3 endpoint")
```

### PHASE 4: Testing (30 min)

**4.1 Local Testing:**

```bash
# 1. Set STORAGE_TYPE=LOCAL
echo "STORAGE_TYPE=LOCAL" >> .env

# 2. Test upload/download/delete
make api
# Use API to upload a recording
# Verify files in storage/users/user_XXXXXX/
```

**4.2 S3 Testing:**

```bash
# 1. Create S3 bucket
aws s3 mb s3://my-leap-bucket --region us-east-1

# 2. Set environment variables
cat >> .env <<EOF
STORAGE_TYPE=S3
STORAGE_S3_BUCKET=my-leap-bucket
STORAGE_S3_REGION=us-east-1
STORAGE_S3_ACCESS_KEY_ID=your_key
STORAGE_S3_SECRET_ACCESS_KEY=your_secret
EOF

# 3. Test upload
make api
# Upload recording via API
# Verify in S3: aws s3 ls s3://my-leap-bucket/storage/
```

**4.3 Verify:**

- ✅ Files upload to S3 correctly
- ✅ Files download from S3 correctly
- ✅ Files delete from S3 correctly
- ✅ Quota tracking works (if enabled)
- ✅ Error handling works (bucket not found, etc.)

---

## 📝 Implementation Checklist

- [ ] **Phase 1:** Create S3StorageBackend (1 hour)
  - [ ] Create `file_storage/backends/s3.py`
  - [ ] Implement all methods (save, load, delete, exists, get_size)
  - [ ] Update `file_storage/factory.py`
  - [ ] Add `aioboto3` dependency
  - [ ] Update `file_storage/backends/__init__.py` exports

- [ ] **Phase 2:** Replace Path operations (1-2 hours)
  - [ ] Update `api/routers/recordings.py` (upload)
  - [ ] Update `api/tasks/processing.py` (video/audio)
  - [ ] Update `transcription_module/manager.py` (transcriptions)
  - [ ] Update `video_download_module/downloader.py` (downloads)
  - [ ] Update `video_processing_module/video_processor.py` (FFmpeg)
  - [ ] Update `api/routers/auth.py` (user dirs - may need special handling)

- [ ] **Phase 3:** Configuration (15 min)
  - [ ] Update `.env.example` with S3 variables
  - [ ] Document S3 setup in docs

- [ ] **Phase 4:** Testing (30 min)
  - [ ] Test LOCAL backend still works
  - [ ] Test S3 backend works
  - [ ] Test switching between backends
  - [ ] Test quota enforcement
  - [ ] Test error handling

---

## ⚠️ Important Considerations

### 1. FFmpeg and S3

FFmpeg **cannot read/write directly from/to S3**. You'll need to:

**Option A:** Download to temp, process, upload back
```python
# 1. Download from S3 to temp file
temp_input = storage_builder.create_temp_file(suffix=".mp4")
content = await backend.load(input_path)
temp_input.write_bytes(content)

# 2. Process with FFmpeg (needs local file)
ffmpeg_command = [
    "ffmpeg", "-i", str(temp_input),
    "-c:v", "libx264", str(temp_output)
]
subprocess.run(ffmpeg_command)

# 3. Upload result to S3
output_content = temp_output.read_bytes()
await backend.save(output_path, output_content)

# 4. Cleanup temp files
temp_input.unlink()
temp_output.unlink()
```

**Option B:** Keep using LOCAL for temp processing
- Download source from S3 → process locally → upload result to S3
- Use `storage/temp/` as LOCAL scratch space

### 2. Directory Operations

S3 doesn't have "directories" - it's a flat key-value store:

```python
# For user directory "creation" (S3):
# No-op! S3 creates "directories" implicitly when you save keys with /

# For LOCAL:
user_root = storage_builder.user_root(user_slug)
user_root.mkdir(parents=True, exist_ok=True)

# Solution: Make directory operations conditional
if isinstance(backend, LocalStorageBackend):
    path.mkdir(parents=True, exist_ok=True)
# S3 doesn't need directory creation
```

### 3. Listing Files

If you need to list files in a directory:

```python
# Add to StorageBackend interface:
async def list_files(self, prefix: str) -> list[str]:
    """List all files with given prefix"""
    pass

# LocalStorageBackend:
async def list_files(self, prefix: str) -> list[str]:
    path = self.base / prefix
    return [str(f.relative_to(self.base)) for f in path.rglob("*") if f.is_file()]

# S3StorageBackend:
async def list_files(self, prefix: str) -> list[str]:
    results = []
    s3_prefix = self._get_s3_key(prefix)
    # Use list_objects_v2 paginator
    # Return list of keys
```

### 4. Presigned URLs (Optional)

For direct browser uploads/downloads:

```python
# Add to S3StorageBackend:
async def get_presigned_url(
    self,
    path: str,
    expires_in: int = 3600,
    method: str = "GET"
) -> str:
    """Generate presigned URL for direct access"""
    s3_key = self._get_s3_key(path)
    session = aioboto3.Session(**self.session_config)
    async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
        if method == "GET":
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expires_in,
            )
        elif method == "PUT":
            url = await s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expires_in,
            )
        return url
```

---

## 🔄 Migration Strategy

### Option 1: Fresh Start (Recommended for new deployments)
- Set `STORAGE_TYPE=S3` before first recording
- All new recordings go directly to S3

### Option 2: Gradual Migration
1. Keep `STORAGE_TYPE=LOCAL` for existing recordings
2. Write script to copy LOCAL → S3:
   ```python
   async def migrate_to_s3():
       local_backend = LocalStorageBackend(Path("storage"))
       s3_backend = S3StorageBackend(...)

       # Get all recording files
       for recording in all_recordings:
           for file_path in recording.get_all_files():
               content = await local_backend.load(file_path)
               await s3_backend.save(file_path, content)

       # Update database: recording.storage_backend = "S3"
       # Switch STORAGE_TYPE=S3
   ```

### Option 3: Hybrid (Advanced)
- Store metadata about which backend each file uses
- Support both backends simultaneously
- Gradually migrate old files

---

## 📚 Related Documentation

### Core Documentation

| Document | Description | Link |
|----------|-------------|------|
| **Storage Structure** | Complete storage architecture specification | [docs/STORAGE_STRUCTURE.md](docs/STORAGE_STRUCTURE.md) |
| **CHANGELOG** | Version history and breaking changes | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| **Storage Implementation** | Implementation guide for v0.9.4 | [STORAGE_STRUCTURE_IMPLEMENTED.md](STORAGE_STRUCTURE_IMPLEMENTED.md) |
| **Legacy Cleanup** | Details of removed legacy code | [LEGACY_CLEANUP_COMPLETE.md](LEGACY_CLEANUP_COMPLETE.md) |
| **Final Verification** | Complete verification report | [FINAL_VERIFICATION_REPORT.md](FINAL_VERIFICATION_REPORT.md) |

### Technical Reference

| Document | Description | Link |
|----------|-------------|------|
| **Technical Docs** | Complete technical reference | [docs/TECHNICAL.md](docs/TECHNICAL.md) |
| **Deployment** | Setup and deployment guide | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| **API Guide** | REST API documentation | [docs/API_GUIDE.md](docs/API_GUIDE.md) |
| **Database Design** | Database schema and migrations | [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) |

### Project Management

| Document | Description | Link |
|----------|-------------|------|
| **README** | Project overview and quick start | [README.md](README.md) |
| **ROADMAP** | Feature roadmap and priorities | [ROADMAP.md](ROADMAP.md) |
| **ADR Overview** | Architecture decision records | [docs/ADR_OVERVIEW.md](docs/ADR_OVERVIEW.md) |
| **ADR Features** | Feature-specific decisions | [docs/ADR_FEATURES.md](docs/ADR_FEATURES.md) |

### Module Documentation

| Document | Description | Link |
|----------|-------------|------|
| **Templates Guide** | Template-based automation | [docs/TEMPLATES.md](docs/TEMPLATES.md) |
| **OAuth Setup** | OAuth configuration guide | [docs/OAUTH.md](docs/OAUTH.md) |
| **Bulk Operations** | Batch processing guide | [docs/BULK_OPERATIONS_GUIDE.md](docs/BULK_OPERATIONS_GUIDE.md) |
| **VK Integration** | VK-specific features | [docs/VK_INTEGRATION.md](docs/VK_INTEGRATION.md) |
| **Fireworks Batch** | Batch transcription API | [docs/FIREWORKS_BATCH_API.md](docs/FIREWORKS_BATCH_API.md) |

### Code Reference

**Storage Module:**
- `file_storage/path_builder.py` - Path generation (single source of truth)
- `file_storage/backends/base.py` - StorageBackend interface
- `file_storage/backends/local.py` - LocalStorageBackend implementation
- `file_storage/factory.py` - Backend factory + singleton

**Configuration:**
- `config/settings.py` - StorageSettings (lines 285-310)
- `.env.example` - Environment variables template

**Usage Examples:**
- `api/routers/recordings.py` - File upload pattern
- `api/tasks/processing.py` - Video/audio processing
- `transcription_module/manager.py` - Transcription files
- `api/routers/auth.py` - User directory creation

---

## 💡 Tips

1. **Start Small:** Implement S3StorageBackend first, test it standalone
2. **Keep LOCAL Working:** Don't break existing LOCAL backend during integration
3. **Use Type Hints:** Make sure all async functions are properly typed
4. **Error Handling:** S3 operations can fail - handle ClientError properly
5. **Logging:** Add detailed logging for debugging S3 operations
6. **Testing:** Test with MinIO locally before using real AWS S3
7. **Costs:** Monitor S3 API calls and data transfer costs

---

## 🎯 Success Criteria

After implementation, you should be able to:

- ✅ Switch between LOCAL and S3 by changing `STORAGE_TYPE` env variable
- ✅ Upload recordings to S3 successfully
- ✅ Download recordings from S3 for processing
- ✅ Delete recordings from S3
- ✅ Enforce storage quotas on S3
- ✅ See clear logs for all S3 operations
- ✅ Handle S3 errors gracefully (bucket not found, no access, etc.)

---

**Good luck with S3 integration! 🚀**

*For questions or issues, refer to the documentation links above or check the code examples in the storage module.*
