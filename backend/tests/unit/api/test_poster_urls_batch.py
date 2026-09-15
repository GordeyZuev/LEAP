"""Regression: poster presign must not resolve metadata per recording when looks are batch-loaded."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.helpers.leap_publication import PublicationLook
from api.routers.recordings import _poster_urls


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_urls_uses_looks_without_per_recording_resolve():
    session = AsyncMock()
    slug_result = MagicMock()
    slug_result.scalar_one_or_none.return_value = 42
    session.execute = AsyncMock(return_value=slug_result)

    recording = MagicMock()
    recording.id = 1
    recording.local_video_path = "users/000042/recordings/1/source.mp4"
    recording.processed_video_path = "users/000042/recordings/1/video.mp4"
    recording.owner = MagicMock(user_slug=42)

    looks = {1: PublicationLook(title="T", description_template=None, thumbnail_name="cover.png")}

    thumb_key = "users/000042/thumbnails/cover.png"
    mock_storage = AsyncMock()
    mock_storage.presigned_urls = AsyncMock(
        return_value=[
            "https://signed.example/cover.png",
            "https://signed.example/frame.jpg",
        ]
    )

    @asynccontextmanager
    async def _shared():
        yield

    mock_storage.shared_operations = _shared

    with (
        patch("file_storage.factory.get_storage_backend", return_value=mock_storage),
        patch("config.settings.get_settings") as mock_settings,
        patch("utils.thumbnail_manager.get_thumbnail_manager") as mock_tm_factory,
        patch("api.services.config_resolver.ConfigResolver") as mock_resolver_cls,
    ):
        mock_settings.return_value.storage.s3_presign_expires = 3600
        tm = AsyncMock()
        tm.get_thumbnail_key = AsyncMock(return_value=thumb_key)
        mock_tm_factory.return_value = tm
        mock_resolver_cls.return_value.resolve_metadata_config = AsyncMock()

        previews = await _poster_urls(session, "user-1", [recording], looks=looks)

    assert 1 in previews
    mock_resolver_cls.return_value.resolve_metadata_config.assert_not_called()
    tm.get_thumbnail_key.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_urls_looks_without_thumb_falls_back_to_metadata():
    session = AsyncMock()
    slug_result = MagicMock()
    slug_result.scalar_one_or_none.return_value = 42
    session.execute = AsyncMock(return_value=slug_result)

    recording = MagicMock()
    recording.id = 1
    recording.local_video_path = "users/000042/recordings/1/source.mp4"
    recording.processed_video_path = "users/000042/recordings/1/video.mp4"
    recording.owner = MagicMock(user_slug=42)

    looks = {1: PublicationLook(title="T", description_template=None, thumbnail_name=None)}

    thumb_key = "users/000042/thumbnails/from-template.png"
    mock_storage = AsyncMock()
    mock_storage.presigned_urls = AsyncMock(
        return_value=[
            "https://signed.example/from-template.png",
            "https://signed.example/frame.jpg",
        ]
    )

    @asynccontextmanager
    async def _shared():
        yield

    mock_storage.shared_operations = _shared

    with (
        patch("file_storage.factory.get_storage_backend", return_value=mock_storage),
        patch("config.settings.get_settings") as mock_settings,
        patch("utils.thumbnail_manager.get_thumbnail_manager") as mock_tm_factory,
        patch("api.services.config_resolver.ConfigResolver") as mock_resolver_cls,
    ):
        mock_settings.return_value.storage.s3_presign_expires = 3600
        tm = AsyncMock()
        tm.get_thumbnail_key = AsyncMock(return_value=thumb_key)
        mock_tm_factory.return_value = tm
        mock_resolver_cls.return_value.resolve_metadata_config = AsyncMock(
            return_value={"thumbnail_name": "from-template.png"}
        )
        previews = await _poster_urls(session, "user-1", [recording], looks=looks)

    assert 1 in previews
    mock_resolver_cls.return_value.resolve_metadata_config.assert_awaited_once()
    tm.get_thumbnail_key.assert_awaited_once()
