"""Storage request count and missing-object behavior for extraction reads."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from transcription_module.manager import TranscriptionManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_extracted_uses_one_get_without_head():
    storage = MagicMock()
    storage.load = AsyncMock(return_value=b'{"active_version":"v1"}')
    storage.exists = AsyncMock()

    with patch("transcription_module.manager.get_storage_backend", return_value=storage):
        result = await TranscriptionManager().load_extracted(2550, 1)

    assert result == {"active_version": "v1"}
    storage.load.assert_awaited_once_with("users/user_000001/recordings/2550/transcriptions/extracted.json")
    storage.exists.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_extracted_preserves_missing_object_error():
    storage = MagicMock()
    storage.load = AsyncMock(side_effect=FileNotFoundError("missing"))

    with patch("transcription_module.manager.get_storage_backend", return_value=storage):
        with pytest.raises(FileNotFoundError, match=r"extracted\.json not found for recording 2550"):
            await TranscriptionManager().load_extracted(2550, 1)
