"""Helpers for share statistics on recording payloads."""

from __future__ import annotations

from api.schemas.share import ShareStatsSummary
from database.models import RecordingModel


def build_share_stats_from_recording(recording: RecordingModel) -> ShareStatsSummary:
    """Full counters for analytics (works after revoke)."""
    return ShareStatsSummary(
        view_count=recording.share_view_count or 0,
        download_count=recording.share_download_count or 0,
        last_viewed_at=recording.share_last_viewed_at,
        last_downloaded_at=recording.share_last_downloaded_at,
    )


def build_share_stats_summary(recording: RecordingModel) -> ShareStatsSummary | None:
    """Lightweight stats for list when a public link is active."""
    if recording.share_token is None:
        return None
    return build_share_stats_from_recording(recording)


def build_share_stats_for_detail(recording: RecordingModel) -> ShareStatsSummary | None:
    """Stats for recording detail/share modal: active link or any historical activity."""
    if recording.share_token is not None:
        return build_share_stats_from_recording(recording)
    if (recording.share_view_count or 0) > 0 or (recording.share_download_count or 0) > 0:
        return build_share_stats_from_recording(recording)
    return None
