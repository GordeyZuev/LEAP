# ready_to_upload Computed Field

## Overview

`ready_to_upload` - computed field в API response schemas, который определяет готовность записи к загрузке на платформы.

## Implementation

**Location:** `api/schemas/recording/response.py`

**Pattern:** DRY через `ReadyToUploadMixin`

```python
class ReadyToUploadMixin(BaseModel):
    """Mixin for computing ready_to_upload field."""
    
    @computed_field
    @property
    def ready_to_upload(self) -> bool:
        """Check if recording is ready to upload to platforms."""
        # Единая реализация для всех schemas
```

**Used in:**
- `RecordingListItem` (list view)
- `RecordingResponse` (detail view)
- `DetailedRecordingResponse` (extended detail view)

## Conditions

Recording считается готовым к загрузке когда **ВСЕ** условия выполнены:

1. **✅ All processing_stages COMPLETED**
   - Если есть `processing_stages`, все должны быть в статусе `COMPLETED`
   - Проверяется: `TRANSCRIBE`, `EXTRACT_TOPICS`, `GENERATE_SUBTITLES`

2. **✅ Status >= DOWNLOADED**
   - Допустимые статусы:
     - `DOWNLOADED` - файл скачан, готов к загрузке без обработки
     - `PROCESSING` - any processing stage in progress (TRIM, TRANSCRIBE, etc.)
     - `PROCESSED` - all processing stages completed or skipped
     - `UPLOADING` - upload to platforms in progress
     - `READY` - all uploads complete

3. **✅ Not failed**
   - `recording.failed == False`

4. **✅ Not deleted**
   - `recording.deleted == False`

## Examples

### API Response (List View)

```json
{
  "id": 123,
  "display_name": "Team Meeting",
  "status": "PROCESSED",
  "ready_to_upload": true,
  "processing_stages": [
    {"stage_type": "TRIM", "status": "COMPLETED"},
    {"stage_type": "TRANSCRIBE", "status": "COMPLETED"},
    {"stage_type": "EXTRACT_TOPICS", "status": "COMPLETED"},
    {"stage_type": "GENERATE_SUBTITLES", "status": "COMPLETED"}
  ]
}
```

### Use Cases in UI

**1. Enable/Disable Upload Button:**
```typescript
const canUpload = recording.ready_to_upload;
<UploadButton disabled={!canUpload} />
```

**2. Show Status Badge:**
```typescript
if (recording.ready_to_upload) {
  return <Badge color="green">Ready to Upload</Badge>;
} else if (recording.status === "PROCESSING") {
  return <Badge color="blue">Processing...</Badge>;
}
```

**3. Bulk Operations:**
```typescript
const readyRecordings = recordings.filter(r => r.ready_to_upload);
await bulkUpload(readyRecordings.map(r => r.id));
```

## Edge Cases

### ❌ Not Ready Examples

**1. Processing stages not completed:**
```json
{
  "status": "PROCESSING",
  "ready_to_upload": false,
  "processing_stages": [
    {"stage_type": "TRANSCRIBE", "status": "IN_PROGRESS"}
  ]
}
```

**2. Failed recording:**
```json
{
  "status": "PROCESSED",
  "failed": true,
  "ready_to_upload": false
}
```

**3. Status too early (before DOWNLOADED):**
```json
{
  "status": "DOWNLOADING",
  "ready_to_upload": false
}
```

**4. Status DOWNLOADED but stages not completed:**
```json
{
  "status": "DOWNLOADED",
  "ready_to_upload": false,
  "processing_stages": [
    {"stage_type": "TRANSCRIBE", "status": "PENDING"}
  ]
}
```

### ✅ Ready Examples

**1. All completed:**
```json
{
  "status": "TRANSCRIBED",
  "failed": false,
  "deleted": false,
  "ready_to_upload": true,
  "processing_stages": [
    {"stage_type": "TRANSCRIBE", "status": "COMPLETED"},
    {"stage_type": "EXTRACT_TOPICS", "status": "COMPLETED"},
    {"stage_type": "GENERATE_SUBTITLES", "status": "COMPLETED"}
  ]
}
```

**2. No processing stages (skip transcription):**
```json
{
  "status": "PROCESSED",
  "failed": false,
  "deleted": false,
  "ready_to_upload": true,
  "processing_stages": []
}
```

**3. Downloaded without processing:**
```json
{
  "status": "DOWNLOADED",
  "failed": false,
  "deleted": false,
  "ready_to_upload": true,
  "processing_stages": []
}
```

## Implementation Details

### Why Mixin?

**Before (DRY violation):**
- `RecordingListItem` had its own `ready_to_upload` implementation
- `RecordingResponse` had identical `ready_to_upload` implementation
- 40+ lines duplicated code

**After (DRY compliant):**
- Single `ReadyToUploadMixin` with computed field
- Inherited by both `RecordingListItem` and `RecordingResponse`
- Zero duplication

### Performance

- **Zero DB queries** - fully computed from existing data
- **No API overhead** - computed during serialization
- **Cached by Pydantic** - computed once per response

## Difference: ready_to_upload vs should_allow_upload

There are **TWO** separate validation checks for uploads:

### 1. `ready_to_upload` (Computed Field - UI)
**Location:** `api/schemas/recording/response.py`  
**Purpose:** General readiness indicator for UI

**Checks:**
- ✅ Status >= `DOWNLOADED`
- ✅ All `processing_stages` COMPLETED (if any)
- ✅ Not `failed`
- ✅ Not `deleted`
- ❌ Does NOT check existing targets/platforms

**Use case:** Enable/disable upload button, show badges, filter recordings

```typescript
// Frontend can use this directly
if (recording.ready_to_upload) {
  <UploadButton enabled />
}
```

---

### 2. `should_allow_upload()` (Server Function)
**Location:** `api/helpers/status_manager.py`  
**Purpose:** Server-side validation before actual upload to specific platform

**Checks:**
- ✅ Status >= `DOWNLOADED` (excludes `INITIALIZED`, `DOWNLOADING`)
- ✅ All `processing_stages` COMPLETED (if any)
- ✅ Not `failed`
- ✅ Not `deleted`
- ✅ Not `SKIPPED`, `PENDING_SOURCE`, or `EXPIRED`
- ✅ **Target platform check:**
  - No existing target → ✅ allow
  - Target exists with `NOT_UPLOADED` or `FAILED` → ✅ allow
  - Target exists with `UPLOADING` or `UPLOADED` → ❌ block

**Use case:** Validate upload request for specific platform

```python
# api/routers/recordings.py
if not should_allow_upload(recording, "YOUTUBE"):
    raise HTTPException(400, "Upload not allowed")
```

---

### Why Two Checks?

**Client-side (`ready_to_upload`):**
- Fast, computed in response
- General indicator across all platforms
- Can show "Ready" even if already uploaded to some platforms

**Server-side (`should_allow_upload`):**
- Platform-specific validation
- Prevents duplicate uploads
- Security: can't bypass via API

---

### Example Scenarios

| Scenario | ready_to_upload | should_allow_upload(YT) | should_allow_upload(VK) |
|----------|-----------------|-------------------------|-------------------------|
| Downloaded, no stages, no uploads | ✅ true | ✅ true | ✅ true |
| Processed, all completed, no uploads | ✅ true | ✅ true | ✅ true |
| Processed, uploaded to YT only | ✅ true | ❌ false | ✅ true |
| Processed, uploaded to YT & VK | ✅ true | ❌ false | ❌ false |
| Processing (stage IN_PROGRESS) | ❌ false | ❌ false | ❌ false |
| Downloaded, failed=true | ❌ false | ❌ false | ❌ false |
| DOWNLOADING status | ❌ false | ❌ false | ❌ false |

---

## Related Changes

See `WHAT_WAS_DONE.md` entry: "2026-01-28: Added Upload Metadata and ready_to_upload Field"

**Files modified:**
- `api/schemas/recording/response.py` - mixin + schemas
- `api/routers/recordings.py` - populate processing_stages
- `api/repositories/recording_repos.py` - load processing_stages
- `api/helpers/status_manager.py` - server-side validation
