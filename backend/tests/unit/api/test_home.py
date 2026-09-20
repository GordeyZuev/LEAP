"""Home aggregation, tenant isolation and operational filter regression tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, text

from api.repositories.recording_repos import RecordingRepository
from database import automation_models  # noqa: F401 — register ORM relationships before executing SQL


@pytest.mark.unit
@pytest.mark.asyncio
async def test_home_summary_and_filters_share_exclusive_tenant_scoped_categories():
    """Execute real SQL over overlapping flags, hidden rows, and another tenant."""
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(
            text("""
            CREATE TABLE recordings (
                id INTEGER PRIMARY KEY, user_id TEXT, status TEXT,
                failed BOOLEAN, on_pause BOOLEAN, on_air BOOLEAN,
                deleted BOOLEAN, blank_record BOOLEAN, created_at TEXT DEFAULT '2026-10-01',
                share_enabled BOOLEAN DEFAULT 0, share_token TEXT, delete_state TEXT DEFAULT 'active',
                processed_video_path TEXT
            )
        """)
        )
        connection.execute(
            text("CREATE TABLE playlists (id INTEGER, user_id TEXT, share_enabled BOOLEAN, share_token TEXT)")
        )
        connection.execute(text("CREATE TABLE playlist_items (playlist_id INTEGER, recording_id INTEGER)"))
        rows = [
            (1, "a", "PROCESSING", 1, 1, 1, 0, 0),
            (2, "a", "PENDING_SOURCE", 0, 1, 1, 0, 0),
            (3, "a", "PENDING_SOURCE", 0, 0, 1, 0, 0),
            (4, "a", "PENDING_CONVERSION", 0, 0, 0, 0, 0),
            (5, "a", "PROCESSING", 0, 0, 1, 0, 0),
            (6, "a", "READY", 0, 0, 0, 0, 0),
            (7, "a", "INITIALIZED", 0, 0, 1, 0, 0),
            (8, "a", "PROCESSING", 1, 0, 1, 1, 0),
            (9, "a", "PROCESSING", 1, 0, 1, 0, 1),
            (10, "b", "PROCESSING", 1, 0, 1, 0, 0),
        ]
        connection.exec_driver_sql(
            "INSERT INTO recordings (id, user_id, status, failed, on_pause, on_air, deleted, blank_record) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        session = AsyncMock()
        session.execute.side_effect = connection.execute
        repo = RecordingRepository(session)
        summary = await repo.home_summary("a")
        assert summary == {"total": 7, "published": 0, "error": 1, "paused": 1, "waiting_source": 2, "in_progress": 2}
        session.execute.assert_awaited_once()
        expected = {"error": [1], "paused": [2], "waiting_source": [3, 4], "in_progress": [5, 7]}
        for state, ids in expected.items():
            actual = await repo.get_filtered_ids("a", operational_state=state, sort_by="created_at")
            assert sorted(actual) == ids
        assert await repo.home_summary("empty") == {
            "total": 0,
            "published": 0,
            "error": 0,
            "paused": 0,
            "waiting_source": 0,
            "in_progress": 0,
        }
        # Public visibility is independent of operational status and recent views.
        connection.execute(text("UPDATE recordings SET share_enabled=1, share_token='public'"))
        connection.execute(text("UPDATE recordings SET share_enabled=0 WHERE id=1"))
        connection.execute(text("UPDATE recordings SET share_token=NULL WHERE id=2"))
        connection.execute(text("UPDATE recordings SET delete_state='deleting' WHERE id=3"))
        assert (await repo.home_summary("a"))["published"] == 4
        assert (await repo.home_summary("b"))["published"] == 1
        assert (await repo.home_summary("empty"))["published"] == 0
        # Playlist-only publication counts once, with the same owner and playable media.
        connection.execute(text("UPDATE recordings SET share_enabled=0, processed_video_path='video.mp4'"))
        connection.execute(text("INSERT INTO playlists VALUES (1,'a',1,'one'), (2,'a',1,'two'), (3,'b',1,'other')"))
        connection.execute(text("INSERT INTO playlist_items VALUES (1,1),(2,1),(3,2),(1,3),(1,8),(1,9),(1,10)"))
        assert (await repo.home_summary("a"))["published"] == 1
        assert (await repo.home_summary("b"))["published"] == 0
        connection.execute(text("UPDATE recordings SET share_enabled=1 WHERE id=1"))
        assert (await repo.home_summary("a"))["published"] == 1
        connection.execute(text("UPDATE recordings SET share_enabled=0, processed_video_path=NULL WHERE id=1"))
        assert (await repo.home_summary("a"))["published"] == 0
        connection.execute(text("UPDATE recordings SET processed_video_path='' WHERE id=1"))
        assert (await repo.home_summary("a"))["published"] == 0
        connection.execute(text("UPDATE recordings SET processed_video_path='video.mp4' WHERE id=1"))
        connection.execute(text("UPDATE playlists SET share_enabled=0 WHERE id=1"))
        connection.execute(text("UPDATE playlists SET share_token=NULL WHERE id=2"))
        assert (await repo.home_summary("a"))["published"] == 0
    engine.dispose()


@pytest.mark.unit
def test_home_endpoint_scopes_user_and_disables_shared_caching(client, mocker, mock_user):
    summary = {"total": 6, "published": 1, "error": 1, "paused": 1, "waiting_source": 1, "in_progress": 1}
    aggregate = mocker.patch(
        "api.routers.users.RecordingRepository.home_summary", new_callable=AsyncMock, return_value=summary
    )
    response = client.get("/api/v1/users/me/home-summary?user_id=someone_else")
    assert response.status_code == 200
    assert response.json() == summary
    assert response.headers["cache-control"] == "private, no-store"
    aggregate.assert_awaited_once_with(mock_user.id)


@pytest.mark.unit
def test_home_requires_authentication(client):
    from api.auth.dependencies import get_current_user
    from api.main import app

    override = app.dependency_overrides.pop(get_current_user)
    try:
        response = client.get("/api/v1/users/me/home-summary")
        assert response.status_code in (401, 403)
    finally:
        app.dependency_overrides[get_current_user] = override


@pytest.mark.unit
@pytest.mark.parametrize("value", ["unknown", "error' OR 1=1 --"])
def test_operational_filter_rejects_unknown_values(client, value):
    response = client.get("/api/v1/recordings", params={"operational_state": value})
    assert response.status_code == 422
    response = client.post("/api/v1/recordings/export", json={"filters": {"operational_state": value}})
    assert response.status_code == 422


@pytest.mark.unit
def test_export_forwards_operational_filter_and_owner(client, mocker, mock_user):
    get_ids = mocker.patch(
        "api.routers.recordings_helpers.RecordingRepository.get_filtered_ids",
        new_callable=AsyncMock,
        return_value=[],
    )
    response = client.post(
        "/api/v1/recordings/export", json={"format": "json", "filters": {"operational_state": "paused"}}
    )
    assert response.status_code == 200
    assert get_ids.call_args.args[0] == mock_user.id
    assert get_ids.call_args.kwargs["operational_state"] == "paused"


@pytest.mark.unit
def test_home_list_filter_skips_unused_posters(client, mocker, mock_user):
    listing = mocker.patch(
        "api.routers.recordings.RecordingRepository.list_filtered", new_callable=AsyncMock, return_value=([], 0)
    )
    posters = mocker.patch("api.routers.recordings._poster_urls", new_callable=AsyncMock)
    response = client.get(
        "/api/v1/recordings",
        params={"operational_state": "waiting_source", "per_page": 5, "compact": True, "include_posters": False},
    )
    assert response.status_code == 200
    assert listing.call_args.args[0] == mock_user.id
    assert listing.call_args.kwargs["operational_state"] == "waiting_source"
    assert listing.call_args.kwargs["per_page"] == 5
    posters.assert_not_awaited()


@pytest.mark.unit
def test_bulk_preview_forwards_operational_filter(client, mocker, mock_user):
    get_ids = mocker.patch(
        "api.routers.recordings_helpers.RecordingRepository.get_filtered_ids",
        new_callable=AsyncMock,
        return_value=[],
    )
    response = client.post("/api/v1/recordings/bulk/run?dry_run=true", json={"filters": {"operational_state": "error"}})
    assert response.status_code == 200
    assert get_ids.call_args.args[0] == mock_user.id
    assert get_ids.call_args.kwargs["operational_state"] == "error"
