"""Unit tests for download failure rollback."""

import pytest

from api.helpers.failure_handler import handle_download_failure
from models.recording import ProcessingStatus
from tests.fixtures.factories import create_mock_recording


@pytest.mark.unit
@pytest.mark.asyncio
async def test_download_failure_without_file_skips_unmapped():
    recording = create_mock_recording(status=ProcessingStatus.DOWNLOADING, is_mapped=False, local_video_path=None)
    await handle_download_failure(recording, "HTTP 403")
    assert recording.status == ProcessingStatus.SKIPPED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_download_failure_keeps_processed_status():
    recording = create_mock_recording(
        status=ProcessingStatus.PROCESSING,
        local_video_path="user/1/source.mp4",
    )
    await handle_download_failure(recording, "HTTP 403")
    assert recording.status == ProcessingStatus.PROCESSING


@pytest.mark.unit
@pytest.mark.asyncio
async def test_download_failure_with_file_stays_downloaded():
    recording = create_mock_recording(
        status=ProcessingStatus.DOWNLOADING,
        local_video_path="user/1/source.mp4",
        is_mapped=False,
    )
    await handle_download_failure(recording, "HTTP 403")
    assert recording.status == ProcessingStatus.DOWNLOADED
