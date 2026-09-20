"""Regression: poster presign uses looks only and shares one S3 client for HEAD + sign."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.helpers.leap_publication import PublicationLook
from api.routers.recordings import _poster_urls


def _recording(rid: int) -> MagicMock:
    recording = MagicMock()
    recording.id = rid
    recording.local_video_path = f"users/000042/recordings/{rid}/source.mp4"
    recording.processed_video_path = f"users/000042/recordings/{rid}/video.mp4"
    recording.owner = MagicMock(user_slug=42)
    return recording


def _session() -> AsyncMock:
    session = AsyncMock()
    slug_result = MagicMock()
    slug_result.scalar_one_or_none.return_value = 42
    session.execute = AsyncMock(return_value=slug_result)
    return session


@asynccontextmanager
async def _shared():
    yield


def _storage(*urls: str) -> AsyncMock:
    mock_storage = AsyncMock()
    mock_storage.presigned_urls = AsyncMock(return_value=list(urls))
    mock_storage.shared_operations = _shared
    return mock_storage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_urls_uses_looks_without_per_recording_resolve():
    recording = _recording(1)
    looks = {1: PublicationLook(title="T", description_template=None, thumbnail_name="cover.png")}
    thumb_key = "users/000042/thumbnails/cover.png"
    mock_storage = _storage("https://signed.example/cover.png", "https://signed.example/frame.jpg")

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

        previews = await _poster_urls(_session(), "user-1", [recording], looks=looks)

    assert 1 in previews
    mock_resolver_cls.assert_not_called()
    tm.get_thumbnail_key.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_urls_looks_without_thumb_uses_frame_only():
    recording = _recording(1)
    looks = {1: PublicationLook(title="T", description_template=None, thumbnail_name=None)}
    mock_storage = _storage("https://signed.example/frame.jpg")

    with (
        patch("file_storage.factory.get_storage_backend", return_value=mock_storage),
        patch("config.settings.get_settings") as mock_settings,
        patch("utils.thumbnail_manager.get_thumbnail_manager") as mock_tm_factory,
        patch("api.services.config_resolver.ConfigResolver") as mock_resolver_cls,
    ):
        mock_settings.return_value.storage.s3_presign_expires = 3600
        tm = AsyncMock()
        tm.get_thumbnail_key = AsyncMock(return_value="users/000042/thumbnails/from-template.png")
        mock_tm_factory.return_value = tm
        previews = await _poster_urls(_session(), "user-1", [recording], looks=looks)

    assert 1 in previews
    assert previews[1].source == "frame"
    mock_resolver_cls.assert_not_called()
    tm.get_thumbnail_key.assert_not_awaited()
    mock_storage.presigned_urls.assert_awaited_once()
    signed_keys = mock_storage.presigned_urls.await_args.args[0]
    assert len(signed_keys) == 1
    assert signed_keys[0].endswith("/recordings/1/poster.jpg")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_urls_resolves_duplicate_thumbnail_names_once():
    looks = {
        1: PublicationLook(title="A", description_template=None, thumbnail_name="cover.png"),
        2: PublicationLook(title="B", description_template=None, thumbnail_name="cover.png"),
    }
    thumb_key = "users/000042/thumbnails/cover.png"
    mock_storage = _storage(
        "https://signed.example/cover.png",
        "https://signed.example/frame-1.jpg",
        "https://signed.example/cover.png",
        "https://signed.example/frame-2.jpg",
    )

    with (
        patch("file_storage.factory.get_storage_backend", return_value=mock_storage),
        patch("config.settings.get_settings") as mock_settings,
        patch("utils.thumbnail_manager.get_thumbnail_manager") as mock_tm_factory,
    ):
        mock_settings.return_value.storage.s3_presign_expires = 3600
        tm = AsyncMock()
        tm.get_thumbnail_key = AsyncMock(return_value=thumb_key)
        mock_tm_factory.return_value = tm
        previews = await _poster_urls(_session(), "user-1", [_recording(1), _recording(2)], looks=looks)

    assert set(previews) == {1, 2}
    tm.get_thumbnail_key.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_urls_heads_thumbnails_inside_shared_operations():
    recording = _recording(1)
    looks = {1: PublicationLook(title="T", description_template=None, thumbnail_name="cover.png")}
    inside = {"shared": False}

    @asynccontextmanager
    async def tracking_shared():
        inside["shared"] = True
        try:
            yield
        finally:
            inside["shared"] = False

    mock_storage = AsyncMock()
    mock_storage.shared_operations = tracking_shared
    mock_storage.presigned_urls = AsyncMock(
        return_value=["https://signed.example/cover.png", "https://signed.example/frame.jpg"]
    )

    async def get_thumbnail_key(**_kwargs):
        assert inside["shared"] is True
        return "users/000042/thumbnails/cover.png"

    with (
        patch("file_storage.factory.get_storage_backend", return_value=mock_storage),
        patch("config.settings.get_settings") as mock_settings,
        patch("utils.thumbnail_manager.get_thumbnail_manager") as mock_tm_factory,
    ):
        mock_settings.return_value.storage.s3_presign_expires = 3600
        tm = AsyncMock()
        tm.get_thumbnail_key = get_thumbnail_key
        mock_tm_factory.return_value = tm
        previews = await _poster_urls(_session(), "user-1", [recording], looks=looks)

    assert 1 in previews
