"""Publish a recording to LEAP as an output target (share link + playlists)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.recording_repos import RecordingRepository
from api.services.config_utils import is_leap_platform
from database.models import RecordingModel
from logger import get_logger

logger = get_logger(__name__)


def _as_int_ids(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            continue
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if n > 0 and n not in out:
            out.append(n)
    return out


def effective_playlist_ids(output_config: dict[str, Any] | None, leap_meta: dict[str, Any] | None) -> list[int]:
    """Template/Run playlist_ids replace; otherwise inherit from the leap preset."""
    from_output = _as_int_ids((output_config or {}).get("playlist_ids"))
    if from_output:
        return from_output
    return _as_int_ids((leap_meta or {}).get("playlist_ids"))


def effective_auto_share(leap_meta: dict[str, Any] | None) -> bool:
    return bool((leap_meta or {}).get("auto_share"))


def _share_url(token: uuid.UUID) -> str:
    from config.settings import get_settings

    origin = (get_settings().oauth.frontend_redirect_url or "").rstrip("/")
    return f"{origin}/share/{token}" if origin else f"/share/{token}"


def maybe_enable_recording_share(recording: RecordingModel, *, auto_share: bool) -> str | None:
    """Enable share unless the owner already disabled an existing token. Returns public URL or None."""
    if not auto_share:
        if recording.share_enabled and recording.share_token:
            return _share_url(recording.share_token)
        return None
    if recording.share_token is not None and not recording.share_enabled:
        return None
    if recording.share_token is None:
        recording.share_token = uuid.uuid4()
    recording.share_enabled = True
    return _share_url(recording.share_token) if recording.share_token else None


async def publish_leap_recording(
    session: AsyncSession,
    recording: RecordingModel,
    *,
    output_config: dict[str, Any] | None,
    leap_meta: dict[str, Any] | None,
    preset_id: int | None,
) -> dict[str, Any]:
    """Append to playlists, optionally enable share, mark the LEAP target UPLOADED."""
    from api.services.playlist_service import PlaylistService

    playlist_ids = effective_playlist_ids(output_config, leap_meta)
    if playlist_ids:
        await PlaylistService(session, recording.user_id).add_from_playlist_ids(recording, playlist_ids)

    auto_share = effective_auto_share(leap_meta)
    share_url = maybe_enable_recording_share(recording, auto_share=auto_share)
    video_id = str(recording.share_token) if recording.share_token and recording.share_enabled else "leap"

    repo = RecordingRepository(session)
    await repo.save_upload_result(
        recording,
        "LEAP",
        preset_id,
        video_id=video_id,
        video_url=share_url or "",
        target_meta={"playlist_ids": playlist_ids, "auto_share": auto_share},
    )
    logger.info(
        "LEAP published | rec={} playlists={} auto_share={} share={}",
        recording.id,
        playlist_ids,
        auto_share,
        bool(share_url),
    )
    return {
        "success": True,
        "video_id": video_id,
        "video_url": share_url or "",
        "playlist_ids": playlist_ids,
        "skipped": False,
    }


def leap_meta_from_preset(preset) -> dict[str, Any]:
    raw = getattr(preset, "preset_metadata", None)
    return dict(raw) if isinstance(raw, dict) else {}


def active_leap_from_presets(presets: list) -> Any | None:
    for preset in presets:
        if is_leap_platform(getattr(preset, "platform", None)) and getattr(preset, "is_active", False):
            return preset
    return None
