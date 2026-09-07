"""Duration of media already in the storage backend (ffprobe via a temp copy)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from api.helpers.blank_record import positive_duration_seconds
from logger import get_logger

logger = get_logger()


def display_duration_seconds(recording: Any) -> float:
    """Length for lists, cards, and share: trimmed/transcribed when known, else source."""
    final = positive_duration_seconds(getattr(recording, "final_duration", None))
    if final is not None:
        return final
    return float(getattr(recording, "duration", 0) or 0)


async def probe_stored_media_duration(storage_key: str | None) -> float | None:
    """Seconds of a stored object, or None if missing / unreadable."""
    if not storage_key:
        return None

    from file_storage.factory import get_storage_backend
    from video_processing_module.audio_detector import AudioDetector

    suffix = Path(storage_key).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        tmp = Path(handle.name)
    try:
        await get_storage_backend().download_to_file(storage_key, tmp)
        raw = await AudioDetector().get_duration_seconds(str(tmp))
        return positive_duration_seconds(raw)
    except Exception:
        logger.debug("Could not probe stored media duration | key=%s", storage_key, exc_info=True)
        return None
    finally:
        tmp.unlink(missing_ok=True)
