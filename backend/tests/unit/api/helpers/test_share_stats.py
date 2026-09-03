"""Tests for share stats summary helpers."""

import uuid
from unittest.mock import MagicMock

from api.helpers.share_stats import (
    build_share_stats_for_detail,
    build_share_stats_summary,
)


def test_build_share_stats_summary_none_without_token() -> None:
    recording = MagicMock()
    recording.share_token = None
    assert build_share_stats_summary(recording) is None


def test_build_share_stats_summary_with_token() -> None:
    recording = MagicMock()
    recording.share_token = uuid.uuid4()
    recording.share_view_count = 3
    recording.share_download_count = 1
    recording.share_last_viewed_at = None
    recording.share_last_downloaded_at = None

    summary = build_share_stats_summary(recording)
    assert summary is not None
    assert summary.view_count == 3
    assert summary.download_count == 1


def test_build_share_stats_for_detail_after_revoke() -> None:
    recording = MagicMock()
    recording.share_token = None
    recording.share_view_count = 5
    recording.share_download_count = 0
    recording.share_last_viewed_at = None
    recording.share_last_downloaded_at = None

    summary = build_share_stats_for_detail(recording)
    assert summary is not None
    assert summary.view_count == 5


def test_build_share_stats_for_detail_none_without_activity() -> None:
    recording = MagicMock()
    recording.share_token = None
    recording.share_view_count = 0
    recording.share_download_count = 0

    assert build_share_stats_for_detail(recording) is None
