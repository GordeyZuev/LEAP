"""Tests for share analytics API query parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
def test_share_analytics_accepts_days_28_query_string(client) -> None:
    """HTTP query params arrive as strings; days=28 must not 422."""
    recording = MagicMock()
    recording.id = 38
    recording.user_id = "user_123"
    recording.share_view_count = 2
    recording.share_download_count = 1
    recording.share_last_viewed_at = datetime.now(UTC)
    recording.share_last_downloaded_at = None

    with patch("api.routers.share.RecordingRepository") as recording_repo_cls:
        recording_repo_cls.return_value.get_by_id = AsyncMock(return_value=recording)
        with patch("api.routers.share.ShareEventRepository") as event_repo_cls:
            event_repo_cls.return_value.daily_aggregates = AsyncMock(return_value=[])
            event_repo_cls.return_value.downloads_by_type = AsyncMock(return_value={})

            response = client.get("/api/v1/recordings/38/share/analytics?days=28")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["view_count"] == 2
    assert body["summary"]["download_count"] == 1
    assert len(body["daily"]) == 28


@pytest.mark.unit
def test_share_analytics_rejects_invalid_days(client) -> None:
    response = client.get("/api/v1/recordings/38/share/analytics?days=14")
    assert response.status_code == 422
