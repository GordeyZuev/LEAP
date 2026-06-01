"""Smoke tests for the new ``/auth/sessions*`` endpoints and logout-all behaviour.

The repo layer is mocked — these tests verify route wiring, ownership checks,
and ``is_current`` resolution, not real DB interactions.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_session_row(**kwargs):
    defaults = {
        "id": 1,
        "user_id": "user_123",
        "token": "refresh-token-A",
        "expires_at": datetime.now(UTC) + timedelta(days=7),
        "is_revoked": False,
        "created_at": datetime.now(UTC),
        "last_used_at": datetime.now(UTC),
        "user_agent": "Mozilla/5.0",
        "ip_hash": "deadbeef",
        "device_label": "Chrome · macOS",
    }
    defaults.update(kwargs)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


@pytest.mark.unit
class TestListSessions:
    def test_returns_active_sessions_with_is_current_flag(self, client, mocker):
        row_current = _mock_session_row(id=1, token="cookie-refresh", device_label="Chrome · macOS")
        row_other = _mock_session_row(id=2, token="other-refresh", device_label="Safari · iOS")

        mock_repo = mocker.patch("api.routers.auth.RefreshTokenRepository")
        mock_repo.return_value.list_active_by_user = AsyncMock(return_value=[row_current, row_other])

        client.cookies.set("refresh_token", "cookie-refresh")
        r = client.get("/api/v1/auth/sessions")

        assert r.status_code == 200, r.text
        sessions = r.json()["sessions"]
        assert len(sessions) == 2
        by_id = {s["id"]: s for s in sessions}
        assert by_id[1]["is_current"] is True
        assert by_id[2]["is_current"] is False
        assert by_id[1]["device_label"] == "Chrome · macOS"

    def test_empty_list(self, client, mocker):
        mock_repo = mocker.patch("api.routers.auth.RefreshTokenRepository")
        mock_repo.return_value.list_active_by_user = AsyncMock(return_value=[])

        r = client.get("/api/v1/auth/sessions")
        assert r.status_code == 200
        assert r.json() == {"sessions": []}


@pytest.mark.unit
class TestRevokeSession:
    def test_revoke_returns_200(self, client, mocker):
        target = _mock_session_row(id=42, token="other-token")
        mock_repo = mocker.patch("api.routers.auth.RefreshTokenRepository")
        mock_repo.return_value.get_by_id_for_user = AsyncMock(return_value=target)
        mock_repo.return_value.revoke_by_id = AsyncMock(return_value=True)

        r = client.delete("/api/v1/auth/sessions/42")
        assert r.status_code == 200
        mock_repo.return_value.revoke_by_id.assert_awaited_once_with(42)

    def test_revoke_not_found(self, client, mocker):
        mock_repo = mocker.patch("api.routers.auth.RefreshTokenRepository")
        mock_repo.return_value.get_by_id_for_user = AsyncMock(return_value=None)

        r = client.delete("/api/v1/auth/sessions/999")
        assert r.status_code == 404

    def test_revoke_current_clears_cookies(self, client, mocker):
        target = _mock_session_row(id=7, token="my-cookie-refresh")
        mock_repo = mocker.patch("api.routers.auth.RefreshTokenRepository")
        mock_repo.return_value.get_by_id_for_user = AsyncMock(return_value=target)
        mock_repo.return_value.revoke_by_id = AsyncMock(return_value=True)

        # The refresh cookie triggers the double-submit CSRF middleware; provide
        # a matching csrf_token cookie + X-CSRF-Token header so the request gets
        # past it and hits the route.
        client.cookies.set("refresh_token", "my-cookie-refresh")
        client.cookies.set("csrf_token", "test-csrf")
        r = client.delete("/api/v1/auth/sessions/7", headers={"X-CSRF-Token": "test-csrf"})

        assert r.status_code == 200, r.text
        # clear_auth_cookies sets cookies to empty with max-age=0
        set_cookie = r.headers.get("set-cookie", "")
        assert "refresh_token" in set_cookie.lower() or "access_token" in set_cookie.lower()


@pytest.mark.unit
class TestLogoutAll:
    def test_bumps_token_version_and_revokes(self, client, mocker):
        mock_user_repo = mocker.patch("api.routers.auth.UserRepository")
        mock_user_repo.return_value.bump_token_version = AsyncMock(return_value=1)

        mock_token_repo = mocker.patch("api.routers.auth.RefreshTokenRepository")
        mock_token_repo.return_value.revoke_all_by_user = AsyncMock(return_value=3)

        r = client.post("/api/v1/auth/logout-all")
        assert r.status_code == 200, r.text
        assert r.json()["revoked_tokens"] == 3
        mock_user_repo.return_value.bump_token_version.assert_awaited_once_with("user_123")
        mock_token_repo.return_value.revoke_all_by_user.assert_awaited_once_with("user_123")


@pytest.mark.unit
class TestLogoutOthers:
    def test_bumps_revokes_and_mints_fresh_pair(self, client, mocker):
        """The caller keeps a live session; only the *other* devices die."""
        fresh_user = MagicMock()
        fresh_user.id = "user_123"
        fresh_user.email = "test@example.com"
        fresh_user.token_version = 4  # bumped

        mock_user_repo = mocker.patch("api.routers.auth.UserRepository")
        mock_user_repo.return_value.bump_token_version = AsyncMock(return_value=4)
        mock_user_repo.return_value.get_by_id = AsyncMock(return_value=fresh_user)

        # _issue_session creates a new refresh row — return a dummy.
        mock_token_repo = mocker.patch("api.routers.auth.RefreshTokenRepository")
        mock_token_repo.return_value.revoke_all_by_user = AsyncMock(return_value=2)
        mock_token_repo.return_value.create = AsyncMock(return_value=_mock_session_row(id=99))

        r = client.post("/api/v1/auth/logout-others")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body and "refresh_token" in body and "csrf_token" in body
        mock_user_repo.return_value.bump_token_version.assert_awaited_once_with("user_123")
        mock_token_repo.return_value.revoke_all_by_user.assert_awaited_once_with("user_123")
        mock_token_repo.return_value.create.assert_awaited_once()
