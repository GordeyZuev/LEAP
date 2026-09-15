"""Share download artifact keys (cache column + public share file list)."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RecordingModel
from file_storage.path_builder import StoragePathBuilder, to_storage_key


def share_artifact_storage_keys(recording: RecordingModel, user_slug: int) -> dict[str, str]:
    builder = StoragePathBuilder()
    recording_id = recording.id
    cache_dir = builder.transcription_cache_dir(user_slug, recording_id)
    tx_dir = builder.transcription_dir(user_slug, recording_id)
    return {
        "transcript_json": to_storage_key(tx_dir / "master.json"),
        "transcript_txt": to_storage_key(cache_dir / "segments.txt"),
        "transcript_words": to_storage_key(cache_dir / "words.txt"),
        "srt": to_storage_key(cache_dir / "subtitles.srt"),
        "vtt": to_storage_key(cache_dir / "subtitles.vtt"),
    }


async def _scan_available_files(recording: RecordingModel, user_slug: int, storage) -> list[str]:
    candidate_keys = share_artifact_storage_keys(recording, user_slug)
    async with storage.shared_operations():
        candidate_exists = await asyncio.gather(*(storage.exists(path) for path in candidate_keys.values()))
    return [key for (key, _path), exists in zip(candidate_keys.items(), candidate_exists, strict=True) if exists]


async def resolve_share_available_files(recording: RecordingModel, user_slug: int, storage) -> list[str]:
    cached = recording.share_artifact_files
    if cached is not None:
        return list(cached)
    return await _scan_available_files(recording, user_slug, storage)


async def refresh_share_artifact_files(
    session: AsyncSession,
    recording: RecordingModel,
    *,
    user_slug: int,
    storage,
) -> list[str]:
    available = await _scan_available_files(recording, user_slug, storage)
    recording.share_artifact_files = available
    await session.flush()
    return available
