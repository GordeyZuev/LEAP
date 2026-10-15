"""YouTube playlist credential API route contracts."""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def youtube_playlist_manager(monkeypatch):
    from api.routers import credentials

    manager = AsyncMock()
    manager.create_playlist_record.return_value = {
        "id": "PLnew",
        "snippet": {"title": "New playlist", "description": "Description"},
        "contentDetails": {"itemCount": 0},
        "status": {"privacyStatus": "unlisted"},
    }
    manager.update_playlist_record.return_value = {
        "id": "PLnew",
        "snippet": {"title": "Updated", "description": "Description"},
        "contentDetails": {"itemCount": 2},
        "status": {"privacyStatus": "public"},
    }
    manager.get_playlist_record.return_value = manager.update_playlist_record.return_value
    monkeypatch.setattr(credentials, "get_playlist_manager", AsyncMock(return_value=manager))
    return manager


def test_youtube_playlist_routes_create_get_and_update(client, youtube_playlist_manager, monkeypatch) -> None:
    from api.routers import credentials

    async def get_item(manager, playlist_id):
        return {
            "id": playlist_id,
            "title": "Updated",
            "description": "Description",
            "privacy_status": "public",
            "item_count": 2,
            "url": f"https://www.youtube.com/playlist?list={playlist_id}",
        }

    monkeypatch.setattr(
        credentials,
        "list_playlists",
        AsyncMock(return_value={"items": [], "next_page_token": None, "total": 0}),
    )
    monkeypatch.setattr(credentials, "get_playlist", AsyncMock(side_effect=get_item))

    list_response = client.get("/api/v1/credentials/12/youtube/playlists", params={"q": "lecture"})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0

    create_response = client.post(
        "/api/v1/credentials/12/youtube/playlists",
        json={"title": "New playlist", "description": "Description", "privacy_status": "unlisted"},
    )
    assert create_response.status_code == 201
    assert create_response.json()["id"] == "PLnew"

    get_response = client.get("/api/v1/credentials/12/youtube/playlists/PLnew")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Updated"

    update_response = client.patch(
        "/api/v1/credentials/12/youtube/playlists/PLnew",
        json={"title": "Updated", "description": "Description", "privacy_status": "public"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["privacy_status"] == "public"
    youtube_playlist_manager.update_playlist_record.assert_awaited_once_with(
        "PLnew", title="Updated", description="Description", privacy_status="public"
    )
