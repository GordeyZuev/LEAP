# Bugfix: Processing Status Not Updating (2026-01-30)

## 🐛 Problem Description

Three critical issues were discovered with status updates:

### Issue A: Processing Status Not Updating (Transcription)

1. **AttributeError**: `'RecordingModel' object has no attribute 'mark_stage_in_progress'`
2. **Status not updating**: Recording remained in `DOWNLOADED` status instead of changing to `PROCESSING`
3. **Incorrect ready_to_upload**: Field showed `true` while processing should be running

### Issue B: Upload Status Not Updating

After successful upload to platform (VK/YouTube):
- Recording status stayed in `PROCESSED` instead of changing to `UPLOADING` → `READY`
- Upload completed successfully, but status never reflected the upload state

### Error Log

```
[2026-01-30 19:57:54,766: INFO/MainProcess] Task api.tasks.processing.transcribe_recording[...] retry: 
Retry in 180s: AttributeError("'RecordingModel' object has no attribute 'mark_stage_in_progress'")
```

### API Response Issue

```json
{
  "status": "DOWNLOADED",
  "processing_stages": [],
  "ready_to_upload": true,
  "failed": false
}
```

**Expected behavior:**
- Status should be `PROCESSING`
- Processing stages should contain TRANSCRIBE stage with `IN_PROGRESS` status
- `ready_to_upload` should be `false`

---

## 🔍 Root Cause Analysis

### Issue 1: Missing Methods in RecordingModel

**Location:** `database/models.py`

The `RecordingModel` class had only `mark_stage_completed()` method, but processing tasks were trying to call:
- `mark_stage_in_progress()` - to mark stage as IN_PROGRESS
- `mark_stage_failed()` - to mark stage as FAILED

**Impact:** Task failed immediately with `AttributeError`, preventing any stage tracking.

### Issue 2: Wrong Priority in Status Computation

**Location:** `api/helpers/status_manager.py` → `compute_aggregate_status()`

The function checked statuses in wrong order:

```python
# OLD (BROKEN) ORDER:
# 1. EXPIRED
# 2. SKIPPED, PENDING_SOURCE
# 3. Base statuses (INITIALIZED, DOWNLOADING, DOWNLOADED) ← returned immediately
# 4. PROCESSING (any stage IN_PROGRESS) ← never reached!
```

When recording was in `DOWNLOADED` status, the function returned `DOWNLOADED` at step 3 without ever checking if any processing stages were `IN_PROGRESS` (step 4).

**Impact:** Even if stage was marked as IN_PROGRESS, the aggregate status remained DOWNLOADED.

### Issue 3: Missing Status Updates in Upload Repository Methods

**Location:** `api/repositories/recording_repos.py`

The repository methods for managing upload outputs:
- `mark_output_uploading()` - marks output as UPLOADING
- `save_upload_result()` - marks output as UPLOADED
- `mark_output_failed()` - marks output as FAILED

These methods updated `OutputTargetModel` status but **never called `update_aggregate_status(recording)`**, so the recording's aggregate status was never recalculated after upload state changes.

**Impact:** Recording status remained PROCESSED even after uploads started or completed.

---

## ✅ Solution

### Fix 1: Add Missing Methods to RecordingModel

**File:** `database/models.py`

Added two new methods to `RecordingModel` class:

```python
def mark_stage_in_progress(self, stage_type: ProcessingStageType) -> None:
    """Mark stage as in progress."""
    # Find or create stage
    stage = None
    for s in self.processing_stages:
        if s.stage_type == stage_type:
            stage = s
            break

    if stage is None:
        # Create new stage
        stage = ProcessingStageModel(
            recording_id=self.id,
            user_id=self.user_id,
            stage_type=stage_type,
            status=ProcessingStageStatus.IN_PROGRESS,
        )
        self.processing_stages.append(stage)
    else:
        # Update existing
        stage.status = ProcessingStageStatus.IN_PROGRESS
        stage.failed = False

def mark_stage_failed(self, stage_type: ProcessingStageType, reason: str) -> None:
    """Mark stage as failed."""
    # Find or create stage
    stage = None
    for s in self.processing_stages:
        if s.stage_type == stage_type:
            stage = s
            break

    if stage is None:
        # Create new stage
        stage = ProcessingStageModel(
            recording_id=self.id,
            user_id=self.user_id,
            stage_type=stage_type,
            status=ProcessingStageStatus.FAILED,
            failed=True,
            failed_at=datetime.utcnow(),
            failed_reason=reason,
        )
        self.processing_stages.append(stage)
    else:
        # Update existing
        stage.status = ProcessingStageStatus.FAILED
        stage.failed = True
        stage.failed_at = datetime.utcnow()
        stage.failed_reason = reason
```

### Fix 2: Reorder Priority Logic in compute_aggregate_status

**File:** `api/helpers/status_manager.py`

Moved IN_PROGRESS check BEFORE base statuses check:

```python
# NEW (CORRECT) ORDER:
# 1. EXPIRED
# 2. SKIPPED, PENDING_SOURCE
# 3. PROCESSING (any stage IN_PROGRESS) ← moved up!
# 4. Base statuses (INITIALIZED, DOWNLOADING, DOWNLOADED)
# 5. PROCESSED
# 6. UPLOADING/READY
```

**Code changes:**

```python
# 3. Check for IN_PROGRESS stages first (takes priority over base statuses like DOWNLOADED)
if recording.processing_stages:
    if any(s.status == ProcessingStageStatus.IN_PROGRESS for s in recording.processing_stages):
        return ProcessingStatus.PROCESSING

# 4. Base statuses (no stages dependency)
if current_status in [
    ProcessingStatus.INITIALIZED,
    ProcessingStatus.DOWNLOADING,
    ProcessingStatus.DOWNLOADED,
]:
    return current_status
```

Updated docstring to reflect new priority:

```python
"""
Compute aggregated recording status from processing_stages and outputs.

Priority logic:
1. EXPIRED - if deleted and retention expired
2. SKIPPED, PENDING_SOURCE - special statuses
3. PROCESSING - any stage IN_PROGRESS (takes priority over base statuses)
4. Base statuses (INITIALIZED, DOWNLOADING, DOWNLOADED)
5. PROCESSED - all active stages COMPLETED or SKIPPED
6. UPLOADING - any output UPLOADING
7. READY - all outputs UPLOADED
"""
```

### Fix 3: Add Status Updates to Upload Repository Methods

**File:** `api/repositories/recording_repos.py`

Added `update_aggregate_status(recording)` calls to all upload-related methods:

#### mark_output_uploading()

```python
async def mark_output_uploading(self, output_target: OutputTargetModel) -> None:
    """Mark output_target as uploading and update aggregate status."""
    from api.helpers.status_manager import update_aggregate_status

    output_target.status = TargetStatus.UPLOADING
    output_target.failed = False
    output_target.updated_at = datetime.utcnow()
    await self.session.flush()
    
    # Refresh recording to ensure outputs are loaded
    recording = output_target.recording
    await self.session.refresh(recording, ["outputs"])
    
    # Update aggregate recording status (PROCESSED → UPLOADING)
    update_aggregate_status(recording)
```

#### save_upload_result()

```python
async def save_upload_result(self, recording, target_type, ...) -> OutputTargetModel:
    """Save upload results and update aggregate status."""
    from api.helpers.status_manager import update_aggregate_status
    
    # ... save output as UPLOADED ...
    
    # Refresh recording to ensure outputs are loaded
    await self.session.refresh(recording, ["outputs"])
    
    # Update aggregate recording status (UPLOADING → READY)
    update_aggregate_status(recording)
    
    return output
```

#### mark_output_failed()

```python
async def mark_output_failed(self, output_target, error_message) -> None:
    """Mark output_target as failed and update aggregate status."""
    from api.helpers.status_manager import update_aggregate_status
    
    output_target.status = TargetStatus.FAILED
    # ... update failure fields ...
    await self.session.flush()
    
    # Refresh recording to ensure outputs are loaded
    recording = output_target.recording
    await self.session.refresh(recording, ["outputs"])
    
    # Update aggregate recording status (may revert from UPLOADING to PROCESSED)
    update_aggregate_status(recording)
```

**Critical detail:** `await self.session.refresh(recording, ["outputs"])` ensures that all outputs are loaded before computing aggregate status, otherwise `compute_aggregate_status()` might see incomplete data.

---

## 🎯 Expected Behavior After Fix

### When transcription task starts:

1. Task calls `recording.mark_stage_in_progress(ProcessingStageType.TRANSCRIBE)`
2. Stage is created/updated with status `IN_PROGRESS`
3. `update_aggregate_status()` is called
4. `compute_aggregate_status()` detects IN_PROGRESS stage (priority 3)
5. Returns `ProcessingStatus.PROCESSING`
6. Recording is saved with new status

### API Response:

```json
{
  "status": "PROCESSING",
  "processing_stages": [
    {
      "stage_type": "TRANSCRIBE",
      "status": "IN_PROGRESS",
      "failed": false
    }
  ],
  "ready_to_upload": false,
  "failed": false
}
```

### When transcription completes:

1. Task calls `recording.mark_stage_completed(ProcessingStageType.TRANSCRIBE)`
2. Stage updated with status `COMPLETED`
3. Status changes to `PROCESSED`
4. `ready_to_upload` becomes `true`

### When upload starts:

1. `mark_output_uploading()` is called
2. Output status set to `UPLOADING`
3. Recording refreshed with outputs
4. `update_aggregate_status()` computes new status
5. Recording status changes: `PROCESSED` → `UPLOADING`

### API Response (during upload):

```json
{
  "status": "UPLOADING",
  "processing_stages": [
    {"stage_type": "TRANSCRIBE", "status": "COMPLETED"}
  ],
  "uploads": {
    "vk": {
      "status": "uploading",
      "url": null,
      "uploaded_at": null
    }
  },
  "ready_to_upload": true
}
```

### When upload completes:

1. `save_upload_result()` is called
2. Output status set to `UPLOADED`
3. Recording refreshed with outputs
4. `update_aggregate_status()` computes new status
5. Recording status changes: `UPLOADING` → `READY`

### API Response (after upload):

```json
{
  "status": "READY",
  "processing_stages": [
    {"stage_type": "TRANSCRIBE", "status": "COMPLETED"}
  ],
  "uploads": {
    "vk": {
      "status": "uploaded",
      "url": "https://vk.com/video-227011779_456239803",
      "uploaded_at": "2026-01-31T06:17:06.376379Z"
    }
  },
  "ready_to_upload": true
}
```

---

## 📋 Files Modified

| File | Changes | Description |
|------|---------|-------------|
| `database/models.py` | +75 lines | Added `mark_stage_in_progress()` and `mark_stage_failed()` methods |
| `api/helpers/status_manager.py` | ~15 lines | Reordered priority logic, moved IN_PROGRESS check before base statuses |
| `api/repositories/recording_repos.py` | ~40 lines | Added `update_aggregate_status()` calls to upload methods with refresh |

---

## 🧪 Testing

### To test the fix:

1. **Restart Celery worker** to load new code:
   ```bash
   make celery-restart
   ```

2. **Trigger processing** on a recording:
   ```bash
   POST /recordings/{id}/run
   ```

3. **Check status immediately**:
   ```bash
   GET /recordings/{id}
   ```
   
   Should show:
   - `status: "PROCESSING"`
   - `processing_stages: [{"stage_type": "TRANSCRIBE", "status": "IN_PROGRESS"}]`
   - `ready_to_upload: false`

4. **Wait for completion** and check again:
   - `status: "PROCESSED"`
   - `processing_stages: [{"stage_type": "TRANSCRIBE", "status": "COMPLETED"}]`
   - `ready_to_upload: true`

---

## 🔗 Related Code

### Processing Task Flow

```
api/tasks/processing.py:transcribe_recording()
  ↓
recording.mark_stage_in_progress(TRANSCRIBE)  ← Fixed: method now exists
  ↓
update_aggregate_status(recording)  ← Fixed: now checks IN_PROGRESS first
  ↓
recording.status = PROCESSING
  ↓
await session.commit()
```

### Status Manager Logic

```
api/helpers/status_manager.py:
- compute_aggregate_status() - compute new status from stages/outputs
- update_aggregate_status() - apply computed status to recording
```

### Stage Tracking Methods

```
database/models.py:RecordingModel:
- mark_stage_in_progress() - NEW
- mark_stage_completed() - existing
- mark_stage_failed() - NEW
```

---

## 📝 Notes

- The `models/recording.py` file has similar methods in the domain model, but `database/models.py` is the SQLAlchemy model actually used in tasks
- The `ready_to_upload` field is computed in `api/schemas/recording/response.py` and correctly checks for COMPLETED stages
- Celery tasks use the database model directly via `RecordingRepository`

---

## ✅ Status

**Fixed:** 2026-01-30

**Verified:** Pending Celery worker restart and test run
