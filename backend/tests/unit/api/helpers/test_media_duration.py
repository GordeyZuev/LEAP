"""Unit tests for probing duration of objects already in storage."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from api.helpers.media_duration import display_duration_seconds, probe_stored_media_duration


@pytest.mark.unit
def test_display_prefers_final_duration():
    rec = type("R", (), {"final_duration": 321.0, "duration": 6000.0})()
    assert display_duration_seconds(rec) == 321.0


@pytest.mark.unit
def test_display_falls_back_to_source_when_final_missing():
    rec = type("R", (), {"final_duration": None, "duration": 6058.0})()
    assert display_duration_seconds(rec) == 6058.0


@pytest.mark.unit
def test_display_zero_final_falls_back_to_source():
    rec = type("R", (), {"final_duration": 0.0, "duration": 100.0})()
    assert display_duration_seconds(rec) == 100.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_probe_returns_none_without_key():
    assert await probe_stored_media_duration(None) is None
    assert await probe_stored_media_duration("") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_probe_uses_ffprobe_on_downloaded_temp(tmp_path: Path):
    storage = AsyncMock()

    async def fake_download(_key, dest: Path):
        dest.write_bytes(b"fake")

    storage.download_to_file.side_effect = fake_download

    with (
        patch("file_storage.factory.get_storage_backend", return_value=storage),
        patch(
            "video_processing_module.audio_detector.AudioDetector.get_duration_seconds",
            new=AsyncMock(return_value=4.2),
        ),
    ):
        assert await probe_stored_media_duration("users/1/recordings/42/source.mp4") == pytest.approx(4.2)

    storage.download_to_file.assert_awaited()
