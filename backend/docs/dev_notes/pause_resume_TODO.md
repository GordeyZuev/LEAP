# Smart Run & Pause - Future Improvements

**Date:** 2026-02-05
**Status:** TODO for future iterations

---

## Current Implementation (v1)

### Unified Smart `/run`
- Single endpoint `POST /recordings/{id}/run` — always determines correct action by status
- No `resume` parameter needed — state machine handles all cases
- State machine: INITIALIZED/SKIPPED → pipeline, DOWNLOADED → processing, PROCESSED/UPLOADED → retry uploads, paused → unpause, running → 409, READY → complete
- For full restart: `/reset` + `/run`

### Soft Pause
- `POST /recordings/{id}/pause` sets `on_pause=true`
- Tasks check flag before starting (7 entry points: download, trim, transcribe, topics, subtitles, upload, pipeline orchestrator)
- Graceful: current stage completes, pipeline stops before next stage

### Bulk Operations
- `POST /recordings/bulk/run` — smart run per recording, skips/rejects as needed
- `POST /recordings/bulk/pause` — pause multiple recordings, skips non-pausable

### UI Fields (`PipelineControlMixin`)
- `is_runtime` — True during DOWNLOADING/PROCESSING/UPLOADING
- `can_pause` — True when pause is available (runtime + not already paused)
- `can_run` — True when `/run` will take a meaningful action

### Duplicate Prevention
- Runtime statuses (DOWNLOADING/PROCESSING/UPLOADING) + not paused → 409 Conflict
- `can_pause` helper: whitelist DOWNLOADING/PROCESSING/UPLOADING only

## Future Enhancements

### 1. Hard Cancel (immediate stop with revoke)

Use `task.revoke(terminate=True)` for immediate stop.

Requirements:
- Cleanup mechanism for partial DB/file changes
- Rollback to last stable status
- Handle orphaned files from interrupted downloads/uploads

### 2. Granular `can_pause` (Variant B - by stages/outputs)

Check by individual stages/outputs instead of aggregate status:
```python
def can_pause(recording):
    has_pending_stages = any(s.status == PENDING for s in recording.processing_stages)
    has_pending_uploads = any(o.status == NOT_UPLOADED for o in recording.outputs)
    return has_pending_stages or has_pending_uploads
```

Better accuracy for complex scenarios with mixed stage states.

### 3. Stage-level pause

Allow pause within long-running stages:
- Checkpoint mechanism for transcription (save partial progress)
- Progress saving for uploads (resumable uploads)

### 4. Upload cancellation

Stop individual platform uploads during multi-platform upload:
- Per-platform task tracking
- Per-platform revoke mechanism
- UI: individual cancel buttons per platform

### 5. Idempotency keys

Optional `X-Idempotency-Key` header for advanced duplicate prevention:
- Replay protection for network retries
- Useful for UI double-click scenarios beyond status check

### 6. Allow multiple uploads to same platform

Currently one output per platform per recording. Future:
- Multiple uploads to same platform with different presets
- Re-upload without requiring reset
