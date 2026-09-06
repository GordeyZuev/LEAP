"""Blank-record heuristics shared by Zoom sync, MTS Link sync, and backfill."""

from __future__ import annotations

from typing import Any

from database.models import RecordingModel
from models.recording import ProcessingStatus

# Zoom: meetings shorter than 20 min or files under 25 MB are junk (same as historical sync).
ZOOM_BLANK_MIN_DURATION_SECONDS = 1200
ZOOM_BLANK_MIN_FILE_SIZE_MB = 25

# MTS online `size` is not MP4 bytes (`size == 0` can still be a 1h+ lecture). Duration
# from GET /fileSystem/file is reliable. 10 min drops cut-offs (4s / 39s); ~17 min
# seminars stay. Blanks remain visible in the UI via include-blank.
MTS_LINK_BLANK_MIN_DURATION_SECONDS = 600

_BLANK_SKIP_STATUSES = frozenset(
    {
        ProcessingStatus.INITIALIZED,
        ProcessingStatus.PENDING_SOURCE,
        ProcessingStatus.SKIPPED,
        ProcessingStatus.DOWNLOADED,
    }
)

BLANK_REASON_TOO_SHORT = "Blank record (too short or too small)"
BLANK_REASON_NO_SPEECH = "Blank record (no speech in transcript)"


def positive_duration_seconds(value: Any) -> float | None:
    """Parse a duration in seconds; None if missing or not a positive number."""
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def is_blank_recording(
    duration: float,
    video_file_size: int = 0,
    *,
    source_processing_incomplete: bool = False,
    min_duration_seconds: int = ZOOM_BLANK_MIN_DURATION_SECONDS,
    min_file_size_mb: int = ZOOM_BLANK_MIN_FILE_SIZE_MB,
) -> bool:
    """True when the recording should be skipped as blank (too short and/or too small)."""
    if source_processing_incomplete:
        return False
    if duration < min_duration_seconds:
        return True
    return min_file_size_mb > 0 and video_file_size < min_file_size_mb * 1024 * 1024


def is_mts_link_blank(duration_seconds: float | None) -> bool:
    """MTS Link blank uses duration only; unknown duration is not blank."""
    if duration_seconds is None:
        return False
    return is_blank_recording(
        duration_seconds,
        0,
        source_processing_incomplete=False,
        min_duration_seconds=MTS_LINK_BLANK_MIN_DURATION_SECONDS,
        min_file_size_mb=0,
    )


def mts_link_record_id_from_source_key(source_key: str | None) -> int | None:
    prefix = "mtslink:record:"
    if not source_key or not source_key.startswith(prefix):
        return None
    raw = source_key[len(prefix) :]
    try:
        return int(raw)
    except ValueError:
        return None


def apply_blank_record(
    recording: RecordingModel,
    is_blank: bool,
    *,
    reason: str,
    force_status_skip: bool = False,
) -> None:
    """Set ``blank_record`` and SKIPPED for idle rows. In-flight / uploaded keep their status."""
    recording.blank_record = is_blank
    if not is_blank:
        return
    if not force_status_skip:
        if recording.on_air:
            return
        if recording.status not in _BLANK_SKIP_STATUSES:
            return
    recording.status = ProcessingStatus.SKIPPED
    recording.failed = False
    recording.failed_reason = reason
    recording.on_air = False
    recording.pipeline_task_id = None
