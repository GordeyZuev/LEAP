"""Tests for recording share Enable / Disable / Rotate."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.routers.share import SHARE_NOT_FOUND, _get_recording_by_share_token
from api.services.playlist_service import SHARE_NOT_FOUND as PLAYLIST_SHARE_NOT_FOUND
from tests.fixtures.factories import create_mock_recording

assert SHARE_NOT_FOUND == PLAYLIST_SHARE_NOT_FOUND


@pytest.mark.unit
class TestRecordingShareOwnerApi:
    def test_enable_mints_token(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8)
        rec.share_token = None
        rec.share_enabled = False
        mocker.patch("api.routers.share.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=rec)
        response = client.post("/api/v1/recordings/8/share")
        assert response.status_code == 200
        assert rec.share_enabled is True
        assert rec.share_token is not None
        body = response.json()
        assert body["share_enabled"] is True
        assert body["share_token"] == str(rec.share_token)

    def test_disable_keeps_token(self, client, mocker) -> None:
        token = uuid.uuid4()
        rec = create_mock_recording(record_id=8, share_token=token, share_enabled=True)
        mocker.patch("api.routers.share.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=rec)
        enabled = client.post("/api/v1/recordings/8/share")
        assert enabled.status_code == 200
        disabled = client.delete("/api/v1/recordings/8/share")
        assert disabled.status_code == 204
        assert rec.share_enabled is False
        assert rec.share_token == token

    def test_rotate_changes_token(self, client, mocker) -> None:
        old = uuid.uuid4()
        rec = create_mock_recording(record_id=8, share_token=old, share_enabled=True)
        mocker.patch("api.routers.share.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=rec)
        response = client.post("/api/v1/recordings/8/share/rotate")
        assert response.status_code == 200
        assert rec.share_token != old
        assert rec.share_enabled is True
        assert response.json()["share_token"] == str(rec.share_token)


@pytest.mark.unit
class TestSharePoster:
    def test_recording_poster_redirects(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8)
        rec.user_id = "user_123"
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        mocker.patch(
            "api.routers.share.poster_url_map",
            new=AsyncMock(return_value={rec.id: "https://cdn.example/poster.jpg"}),
        )
        response = client.get(f"/api/v1/share/{uuid.uuid4()}/poster", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "https://cdn.example/poster.jpg"

    def test_recording_poster_404_when_missing(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8)
        rec.user_id = "user_123"
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        mocker.patch("api.routers.share.poster_url_map", new=AsyncMock(return_value={}))
        response = client.get(f"/api/v1/share/{uuid.uuid4()}/poster", follow_redirects=False)
        assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_public_lookup_disabled_is_404() -> None:
    rec = create_mock_recording(share_token=uuid.uuid4(), share_enabled=False)
    rec.deleted = False
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = rec
    session.execute = AsyncMock(return_value=result)
    with pytest.raises(HTTPException) as exc:
        await _get_recording_by_share_token(uuid.uuid4(), session)
    assert exc.value.status_code == 404
    assert exc.value.detail == SHARE_NOT_FOUND
