"""MTS Link downloader: conversion handling and best-effort companion files (mocked API/storage)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.mts_link_api import MtsLinkResponseError
from video_download_module.platforms.mtslink.downloader import (
    MtsLinkConversionPendingError,
    MtsLinkDownloader,
    _safe_filename,
)

SOURCE_META = {"mts_record_id": 2042825651, "event_session_id": 23607290372}


def _downloader(**overrides) -> MtsLinkDownloader:
    dl = MtsLinkDownloader(user_slug=1, api_token="org-key", **overrides)
    dl.api = AsyncMock()
    return dl


class _FakeStorage:
    """In-memory storage backend: ``saved`` holds byte payloads, ``files`` committed sizes."""

    def __init__(self):
        self.saved: dict[str, bytes] = {}
        self.files: dict[str, int] = {}

    async def exists(self, key: str) -> bool:
        return key in self.saved or key in self.files

    async def get_size(self, key: str) -> int:
        return self.files.get(key, len(self.saved.get(key, b"")))

    async def save(self, key: str, content: bytes) -> str:
        self.saved[key] = content
        return key

    async def save_file(self, key: str, local_path) -> str:
        self.files[key] = local_path.stat().st_size
        return key


@pytest.fixture(autouse=True)
def storage():
    """Fake backend for both lazy factory lookups and the one BaseDownloader imported."""
    fake = _FakeStorage()
    with (
        patch("file_storage.factory.get_storage_backend", return_value=fake),
        patch("video_download_module.core.base.get_storage_backend", return_value=fake),
    ):
        yield fake


def _patch_video_stream(downloader: MtsLinkDownloader, size: int = 4096):
    """Make the MP4 stream succeed without touching the network."""

    async def fake_download_url(*, filepath, **_kwargs):
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(b"0" * size)
        return True

    return patch.object(downloader, "_download_url", side_effect=fake_download_url)


@pytest.mark.unit
class TestSafeFilename:
    def test_strips_unsafe_characters(self):
        assert _safe_filename("Лекция 1 (итог).pdf", "fallback") == "Лекция_1_итог.pdf"
        assert _safe_filename("slides v2.pptx", "fallback") == "slides_v2.pptx"

    def test_falls_back_when_nothing_usable_remains(self):
        assert _safe_filename("///", "file_7") == "file_7"
        assert _safe_filename("", "file_7") == "file_7"


@pytest.mark.unit
class TestMtsLinkDownloaderRequirements:
    def test_api_token_is_required(self):
        with pytest.raises(ValueError, match="api_token"):
            MtsLinkDownloader(user_slug=1)

    @pytest.mark.asyncio
    async def test_incomplete_metadata_is_rejected(self):
        dl = _downloader()
        with pytest.raises(ValueError, match="event_session_id"):
            await dl.download(recording_id=42, source_meta={"mts_record_id": 1})


@pytest.mark.unit
class TestConversionHandling:
    @pytest.mark.asyncio
    async def test_existing_mp4_is_downloaded_without_new_conversion(self, storage):
        dl = _downloader(fetch_chat=False, fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"

        with _patch_video_stream(dl):
            result = await dl.download(recording_id=42, source_meta=SOURCE_META)

        dl.api.start_conversion.assert_not_awaited()
        assert result.storage_key == "users/user_000001/recordings/42/source.mp4"
        assert result.file_size == 4096
        assert result.metadata["needs_mp4"] is False
        assert list(storage.files) == [result.storage_key]

    @pytest.mark.asyncio
    async def test_missing_mp4_raises_pending_for_prepare(self):
        dl = _downloader(fetch_chat=False, fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = None

        with pytest.raises(MtsLinkConversionPendingError, match="not ready"):
            await dl.download(recording_id=42, source_meta=SOURCE_META)

        dl.api.start_conversion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_in_flight_conversion_is_not_polled_in_download(self):
        dl = _downloader(fetch_chat=False, fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = None

        with pytest.raises(MtsLinkConversionPendingError):
            await dl.download(recording_id=42, source_meta=SOURCE_META)

        dl.api.list_converted_records.assert_not_awaited()
        dl.api.start_conversion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_busy_403_is_not_handled_in_download(self):
        dl = _downloader(fetch_chat=False, fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = None

        with pytest.raises(MtsLinkConversionPendingError):
            await dl.download(recording_id=42, source_meta=SOURCE_META)

    @pytest.mark.asyncio
    async def test_failed_conversion_is_not_detected_in_download(self):
        dl = _downloader(fetch_chat=False, fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = None

        with pytest.raises(MtsLinkConversionPendingError):
            await dl.download(recording_id=42, source_meta=SOURCE_META)

    @pytest.mark.asyncio
    async def test_slow_conversion_defers_to_prepare_not_celery_poll(self):
        dl = _downloader(fetch_chat=False, fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = None

        with pytest.raises(MtsLinkConversionPendingError):
            await dl.download(recording_id=42, source_meta=SOURCE_META)


@pytest.mark.unit
class TestCompanionFiles:
    @pytest.mark.asyncio
    async def test_chat_and_attachments_are_stored_next_to_video(self, storage):
        dl = _downloader()
        dl.api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"
        dl.api.get_event_session_chat.return_value = [{"id": 1, "text": "hello"}]
        dl.api.list_event_session_files.return_value = [
            {"id": 10, "name": "Slides.pdf", "typeFile": "presentation", "downloadUrl": "https://cdn/s.pdf"},
            {"id": 11, "name": "recording", "typeFile": "record", "downloadUrl": "https://cdn/r.mp4"},
            {"id": 12, "name": "no-url.pdf", "typeFile": "document"},
        ]

        with (
            _patch_video_stream(dl),
            patch.object(dl, "_save_remote_file", new=AsyncMock(return_value=2048)),
        ):
            result = await dl.download(recording_id=42, source_meta=SOURCE_META)

        assert result.metadata["extras"] == {"chat": True, "files_count": 1, "error": None}

        chat_key = "users/user_000001/recordings/42/source_extras/chat.json"
        chat_doc = json.loads(storage.saved[chat_key])
        assert chat_doc["event_session_id"] == SOURCE_META["event_session_id"]
        assert chat_doc["data"] == [{"id": 1, "text": "hello"}]

        manifest_key = "users/user_000001/recordings/42/source_extras/files_manifest.json"
        manifest = json.loads(storage.saved[manifest_key])
        assert [row["stored_as"] for row in manifest] == ["Slides.pdf"]

    @pytest.mark.asyncio
    async def test_empty_chat_is_recorded_as_absent(self):
        dl = _downloader(fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"
        dl.api.get_event_session_chat.return_value = []

        with _patch_video_stream(dl):
            result = await dl.download(recording_id=42, source_meta=SOURCE_META)

        assert result.metadata["extras"]["chat"] is False
        assert result.metadata["extras"]["error"] is None

    @pytest.mark.asyncio
    async def test_companion_failure_does_not_fail_the_video(self):
        dl = _downloader()
        dl.api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"
        dl.api.get_event_session_chat.side_effect = MtsLinkResponseError(500, "chat boom")
        dl.api.list_event_session_files.side_effect = MtsLinkResponseError(403, "no access")

        with _patch_video_stream(dl):
            result = await dl.download(recording_id=42, source_meta=SOURCE_META)

        assert result.file_size == 4096
        assert result.metadata["extras"]["chat"] is False
        assert result.metadata["extras"]["files_count"] == 0
        assert "chat boom" in result.metadata["extras"]["error"]
        assert "no access" in result.metadata["extras"]["error"]

    @pytest.mark.asyncio
    async def test_toggles_off_skip_companion_calls(self):
        dl = _downloader(fetch_chat=False, fetch_session_files=False)
        dl.api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"

        with _patch_video_stream(dl):
            await dl.download(recording_id=42, source_meta=SOURCE_META)

        dl.api.get_event_session_chat.assert_not_awaited()
        dl.api.list_event_session_files.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duplicate_attachment_names_are_disambiguated(self, storage):
        dl = _downloader(fetch_chat=False)
        dl.api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"
        dl.api.list_event_session_files.return_value = [
            {"id": 10, "name": "slides.pdf", "typeFile": "document", "downloadUrl": "https://cdn/a.pdf"},
            {"id": 11, "name": "slides.pdf", "typeFile": "document", "downloadUrl": "https://cdn/b.pdf"},
        ]

        with (
            _patch_video_stream(dl),
            patch.object(dl, "_save_remote_file", new=AsyncMock(return_value=1024)),
        ):
            result = await dl.download(recording_id=42, source_meta=SOURCE_META)

        manifest_key = "users/user_000001/recordings/42/source_extras/files_manifest.json"
        manifest = json.loads(storage.saved[manifest_key])
        assert [row["stored_as"] for row in manifest] == ["slides.pdf", "11_slides.pdf"]
        assert result.metadata["extras"]["files_count"] == 2
