"""Regression checks for queued public analytics persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Update
from sqlalchemy.dialects import postgresql

from api.tasks.share_events import _persist_share_event_batch


class _Session:
    def __init__(self, inserted_rows: list[tuple[int | None, str]]) -> None:
        self.statements: list = []
        self.inserted_rows = inserted_rows
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.statements.append(statement)
        result = MagicMock()
        result.all.return_value = self.inserted_rows
        return result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_preserves_surface_channel_and_normalizes_mixed_access_batch(mocker) -> None:
    session = _Session([(None, "page_view"), (12, "file_download")])
    mocker.patch("api.tasks.share_events.get_async_session_maker", return_value=lambda: session)
    resolve_channel = mocker.patch("api.tasks.share_events._channel_id_from_slug", new=AsyncMock())
    queued_at = datetime(2026, 10, 3, tzinfo=UTC).timestamp()

    await _persist_share_event_batch(
        {
            "queued_at": queued_at,
            "access_events": [
                {
                    "id": "01surface",
                    "owner_user_id": "owner",
                    "event_type": "page_view",
                    "visitor_key": "visitor",
                    "channel_id": 7,
                },
                {
                    "id": "02download",
                    "owner_user_id": "owner",
                    "event_type": "file_download",
                    "visitor_key": "visitor",
                    "recording_id": 12,
                    "artifact_type": "vtt",
                },
            ],
        }
    )

    params = session.statements[0].compile(dialect=postgresql.dialect()).params
    assert params["channel_id_m0"] == 7
    assert params["channel_id_m1"] is None
    assert params["artifact_type_m0"] is None
    assert params["artifact_type_m1"] == "vtt"
    assert params["created_at_m0"] == datetime(2026, 10, 3, tzinfo=UTC)
    assert len([statement for statement in session.statements if isinstance(statement, Update)]) == 1
    session.commit.assert_awaited_once()
    resolve_channel.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_retry_does_not_increment_recording_counter_again(mocker) -> None:
    session = _Session([])
    mocker.patch("api.tasks.share_events.get_async_session_maker", return_value=lambda: session)

    await _persist_share_event_batch(
        {
            "access_events": [
                {
                    "id": "01duplicate",
                    "owner_user_id": "owner",
                    "event_type": "page_view",
                    "visitor_key": "visitor",
                    "recording_id": 12,
                }
            ]
        }
    )

    assert len(session.statements) == 1
    session.commit.assert_awaited_once()
