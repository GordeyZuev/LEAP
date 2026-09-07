"""Tests for product analytics API endpoints."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.analytics import AnalyticsBreakdown, AnalyticsSummary, UserAnalyticsResponse
from api.schemas.user.stats import StatsPeriod


def _user_analytics_response() -> UserAnalyticsResponse:
    period = StatsPeriod(**{"from": date(2026, 1, 1), "to": date(2026, 1, 31)})
    return UserAnalyticsResponse(
        period=period,
        daily=[],
        daily_uploads=[],
        summary=AnalyticsSummary(),
        breakdown=AnalyticsBreakdown(),
    )


def _platform_analytics_response() -> UserAnalyticsResponse:
    return _user_analytics_response()


@pytest.mark.unit
class TestUserAnalyticsApi:
    def test_get_my_analytics_success(self, client, mocker, mock_user):
        mock_svc = mocker.patch("api.routers.users.AnalyticsService")
        mock_svc.return_value.get_user_analytics = AsyncMock(return_value=_user_analytics_response())

        response = client.get("/api/v1/users/me/analytics?from=2026-01-01&to=2026-01-31")

        assert response.status_code == 200
        mock_svc.return_value.get_user_analytics.assert_awaited_once_with(mock_user.id, "2026-01-01", "2026-01-31")

    def test_get_my_analytics_invalid_range(self, client):
        response = client.get("/api/v1/users/me/analytics?from=2026-02-01&to=2026-01-01")
        assert response.status_code == 400


@pytest.mark.unit
class TestAdminAnalyticsApi:
    def test_platform_analytics_success(self, admin_client, mocker):
        mock_svc = mocker.patch("api.routers.admin.AnalyticsService")
        mock_svc.return_value.get_platform_analytics = AsyncMock(return_value=_platform_analytics_response())

        response = admin_client.get("/api/v1/admin/stats/analytics?from=2026-01-01&to=2026-01-31")

        assert response.status_code == 200

    def test_platform_analytics_forbidden_for_non_admin(self, client):
        response = client.get("/api/v1/admin/stats/analytics?from=2026-01-01&to=2026-01-31")
        assert response.status_code == 403

    def test_user_analytics_success(self, admin_client, mocker, mock_db_session):
        mock_svc = mocker.patch("api.routers.admin.AnalyticsService")
        mock_svc.return_value.get_user_analytics = AsyncMock(return_value=_user_analytics_response())

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = MagicMock(id="user_abc")
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = admin_client.get("/api/v1/admin/users/user_abc/analytics?from=2026-01-01&to=2026-01-31")

        assert response.status_code == 200

    def test_user_analytics_forbidden_for_non_admin(self, client):
        response = client.get("/api/v1/admin/users/user_abc/analytics?from=2026-01-01&to=2026-01-31")
        assert response.status_code == 403

    def test_user_analytics_scoped_to_requested_user(self, admin_client, mocker, mock_db_session):
        mock_svc = mocker.patch("api.routers.admin.AnalyticsService")
        mock_svc.return_value.get_user_analytics = AsyncMock(return_value=_user_analytics_response())

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = MagicMock(id="user_target")
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = admin_client.get("/api/v1/admin/users/user_target/analytics?from=2026-01-01&to=2026-01-31")

        assert response.status_code == 200
        mock_svc.return_value.get_user_analytics.assert_awaited_once_with("user_target", "2026-01-01", "2026-01-31")


@pytest.mark.unit
def test_share_analytics_accepts_from_to(client) -> None:
    recording = MagicMock()
    recording.id = 38
    recording.user_id = "user_123"
    recording.share_view_count = 2
    recording.share_download_count = 1
    recording.share_last_viewed_at = None
    recording.share_last_downloaded_at = None

    with patch("api.routers.share.RecordingRepository") as recording_repo_cls:
        recording_repo_cls.return_value.get_by_id = AsyncMock(return_value=recording)
        with patch("api.routers.share.ShareEventRepository") as event_repo_cls:
            event_repo_cls.return_value.daily_aggregates = AsyncMock(return_value=[])
            event_repo_cls.return_value.downloads_by_type = AsyncMock(return_value={})

            response = client.get("/api/v1/recordings/38/share/analytics?from=2026-01-01&to=2026-01-07")

    assert response.status_code == 200
    assert len(response.json()["daily"]) == 7
