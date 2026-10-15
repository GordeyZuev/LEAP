"""YouTube playlist API service behavior."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.credentials.youtube_playlists import YouTubePlaylistCreateRequest, YouTubePlaylistUpdateRequest
from api.services import youtube_playlists
from api.services.youtube_playlists import _playlist, _raise_youtube_error, list_playlists
from video_upload_module.config_factory import YouTubeConfig
from video_upload_module.platforms.youtube.playlist_manager import YouTubePlaylistManager
from video_upload_module.platforms.youtube.token_handler import TokenRefreshError, is_youtube_auth_error


class FakeRequest:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


def test_playlist_response_is_normalized_for_picker() -> None:
    result = _playlist(
        {
            "id": "PL123",
            "snippet": {"title": "Lecture series", "description": "Course videos"},
            "contentDetails": {"itemCount": 8},
            "status": {"privacyStatus": "unlisted"},
        }
    )

    assert result == {
        "id": "PL123",
        "title": "Lecture series",
        "description": "Course videos",
        "privacy_status": "unlisted",
        "item_count": 8,
        "url": "https://www.youtube.com/playlist?list=PL123",
    }


def test_playlist_write_schemas_trim_titles_and_reject_blank_titles() -> None:
    assert YouTubePlaylistCreateRequest(title="  New playlist  ").title == "New playlist"
    assert YouTubePlaylistUpdateRequest(title="  Renamed  ").title == "Renamed"
    with pytest.raises(ValueError):
        YouTubePlaylistCreateRequest(title="   ")
    with pytest.raises(ValueError):
        YouTubePlaylistUpdateRequest(title="  ")


@pytest.mark.asyncio
async def test_playlist_search_scans_all_pages_and_matches_title_or_description() -> None:
    manager = AsyncMock()
    manager.list_playlists.side_effect = [
        {
            "items": [
                {"id": "PL1", "snippet": {"title": "Other", "description": "No match"}},
                {"id": "PL2", "snippet": {"title": "Machine Learning", "description": ""}},
            ],
            "nextPageToken": "next",
        },
        {
            "items": [
                {"id": "PL3", "snippet": {"title": "Seminar", "description": "Machine learning"}},
                {"id": "PL4", "snippet": {"title": "Different", "description": ""}},
            ]
        },
    ]

    result = await list_playlists(manager, "machine learning", None)

    assert [item["id"] for item in result["items"]] == ["PL2", "PL3"]
    assert result["total"] == 2
    assert result["next_page_token"] is None
    assert manager.list_playlists.await_args_list[0].kwargs == {"page_token": None}
    assert manager.list_playlists.await_args_list[1].kwargs == {"page_token": "next"}


@pytest.mark.asyncio
async def test_playlist_search_has_a_total_timeout(monkeypatch) -> None:
    monkeypatch.setattr(youtube_playlists, "YOUTUBE_PLAYLIST_SEARCH_TIMEOUT_SECONDS", 0.001)
    manager = AsyncMock()

    async def slow_page(*, page_token: str | None = None):
        await asyncio.sleep(0.02)
        return {"items": [], "nextPageToken": "next"}

    manager.list_playlists.side_effect = slow_page

    with pytest.raises(HTTPException) as raised:
        await list_playlists(manager, "lecture", None)

    assert raised.value.status_code == 504
    assert "took too long" in raised.value.detail


@pytest.mark.asyncio
async def test_playlist_listing_preserves_provider_pagination() -> None:
    manager = AsyncMock()
    manager.list_playlists.return_value = {
        "items": [{"id": "PL1", "snippet": {"title": "One"}}],
        "nextPageToken": "next",
        "pageInfo": {"totalResults": 51},
    }

    result = await list_playlists(manager, None, "current")

    assert result["items"][0]["id"] == "PL1"
    assert result["next_page_token"] == "next"
    assert result["total"] == 51
    manager.list_playlists.assert_awaited_once_with(page_token="current")


@pytest.mark.asyncio
async def test_playlist_manager_lists_and_creates_using_youtube_data_api() -> None:
    service = MagicMock()
    playlists = service.playlists.return_value
    playlists.list.return_value = FakeRequest({"items": [], "nextPageToken": "next"})
    playlists.insert.return_value = FakeRequest({"id": "PLnew"})
    manager = YouTubePlaylistManager(service, YouTubeConfig())

    listed = await manager.list_playlists(page_token="cursor")
    created = await manager.create_playlist_record("New", "Description", "private")

    assert listed["nextPageToken"] == "next"
    assert created["id"] == "PLnew"
    playlists.list.assert_called_once_with(
        part="snippet,contentDetails,status", mine=True, maxResults=50, pageToken="cursor"
    )
    playlists.insert.assert_called_once_with(
        part="snippet,status",
        body={
            "snippet": {"title": "New", "description": "Description"},
            "status": {"privacyStatus": "private"},
        },
    )


@pytest.mark.asyncio
async def test_playlist_update_preserves_fields_not_changed_by_user() -> None:
    service = MagicMock()
    playlists = service.playlists.return_value
    playlists.list.return_value = FakeRequest(
        {
            "items": [
                {
                    "id": "PL1",
                    "snippet": {
                        "title": "Old title",
                        "description": "Old description",
                        "defaultLanguage": "ru",
                    },
                    "status": {"privacyStatus": "private", "podcastStatus": "enabled"},
                }
            ]
        }
    )
    playlists.update.return_value = FakeRequest(
        {
            "id": "PL1",
            "snippet": {"title": "New title", "description": "Old description", "defaultLanguage": "ru"},
            "status": {"privacyStatus": "public", "podcastStatus": "enabled"},
        }
    )
    manager = YouTubePlaylistManager(service, YouTubeConfig())

    result = await manager.update_playlist_record("PL1", title="New title", privacy_status="public")

    assert result["snippet"]["title"] == "New title"
    assert result["snippet"]["description"] == "Old description"
    assert result["status"]["privacyStatus"] == "public"
    assert result["snippet"]["defaultLanguage"] == "ru"
    assert result["status"]["podcastStatus"] == "enabled"
    playlists.update.assert_called_once_with(
        part="snippet,status",
        body={
            "id": "PL1",
            "snippet": {"title": "New title", "description": "Old description", "defaultLanguage": "ru"},
            "status": {"privacyStatus": "public", "podcastStatus": "enabled"},
        },
    )


@pytest.mark.asyncio
async def test_playlist_manager_rejects_credentials_not_owned_by_user(monkeypatch) -> None:
    repository = AsyncMock()
    repository.get_by_id.return_value = None
    monkeypatch.setattr(youtube_playlists, "UserCredentialRepository", lambda _session: repository)

    with pytest.raises(HTTPException) as raised:
        await youtube_playlists.get_playlist_manager(12, "user-1", cast("AsyncSession", object()))

    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_oauth_refresh_timeout_does_not_mark_credential_for_reauthorization(monkeypatch) -> None:
    repository = AsyncMock()
    repository.get_by_id.return_value = MagicMock(platform="youtube", is_active=True)
    monkeypatch.setattr(youtube_playlists, "UserCredentialRepository", lambda _session: repository)
    uploader = MagicMock()
    uploader.authenticate = AsyncMock(side_effect=TimeoutError("network timeout"))
    monkeypatch.setattr(youtube_playlists, "create_youtube_uploader_from_db", AsyncMock(return_value=uploader))

    with pytest.raises(HTTPException) as raised:
        await youtube_playlists.get_playlist_manager(12, "user-1", cast("AsyncSession", object()))

    assert raised.value.status_code == 504
    repository.set_needs_reauth.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_youtube_scope_marks_credential_for_reauthorization(monkeypatch) -> None:
    repository = AsyncMock()
    monkeypatch.setattr(youtube_playlists, "UserCredentialRepository", lambda _session: repository)
    error = HttpError(
        Response({"status": "403"}),
        b'{"error":{"errors":[{"reason":"insufficientPermissions"}]}}',
    )

    response = await youtube_playlists.map_youtube_playlist_error(error, 12, "user-1", cast("AsyncSession", object()))

    assert response.status_code == 403
    assert "Reconnect" in response.detail
    repository.set_needs_reauth.assert_awaited_once_with(12, True, user_id="user-1")

    refresh_response = await youtube_playlists.map_youtube_playlist_error(
        TokenRefreshError("youtube", "refresh token expired"),
        12,
        "user-1",
        cast("AsyncSession", object()),
    )

    assert refresh_response.status_code == 403
    assert "Reconnect" in refresh_response.detail
    assert repository.set_needs_reauth.await_count == 2


@pytest.mark.asyncio
async def test_timeout_does_not_mark_credential_for_reauthorization() -> None:
    response = await youtube_playlists.map_youtube_playlist_error(
        TimeoutError("request timed out"), 12, "user-1", cast("AsyncSession", object())
    )

    assert response.status_code == 504
    assert "timed out" in response.detail


def test_youtube_token_refresh_only_retries_auth_errors() -> None:
    def error(status: str, reason: str) -> HttpError:
        return HttpError(
            Response({"status": status}),
            f'{{"error":{{"errors":[{{"reason":"{reason}"}}]}}}}'.encode(),
        )

    assert is_youtube_auth_error(error("401", "authError"))
    assert not is_youtube_auth_error(error("403", "insufficientPermissions"))
    assert not is_youtube_auth_error(error("403", "quotaExceeded"))


def test_youtube_setup_and_playlist_limit_errors_are_actionable() -> None:
    def error(status_code: str, reason: str) -> HttpError:
        return HttpError(
            Response({"status": status_code}),
            f'{{"error":{{"errors":[{{"reason":"{reason}"}}]}}}}'.encode(),
        )

    disabled_api = _raise_youtube_error(error("403", "accessNotConfigured"))
    playlist_limit = _raise_youtube_error(error("400", "maxPlaylistExceeded"))
    expired_youtube_auth = _raise_youtube_error(error("401", "authError"))

    assert disabled_api.status_code == 503
    assert "YouTube Data API v3" in disabled_api.detail
    assert playlist_limit.status_code == 409
    assert "playlist limit" in playlist_limit.detail
    assert expired_youtube_auth.status_code == 403
