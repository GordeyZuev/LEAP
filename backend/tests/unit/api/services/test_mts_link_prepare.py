"""Unit tests for MTS Link prepare-before-run service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.mts_link_api import MtsLinkConversionBusyError
from api.services.mts_link_prepare import (
    MtsLinkPrepareResult,
    MtsPrepareOutcome,
    apply_prepare_result,
    prepare_mts_link_recording,
    recording_needs_mts_prepare,
    should_skip_mts_prepare,
)
from models.recording import ProcessingStatus, SourceType


def _recording(*, status=ProcessingStatus.INITIALIZED, meta=None, local_video_path=None):
    rec = MagicMock()
    rec.local_video_path = local_video_path
    rec.status = status
    rec.is_mapped = True
    rec.failed = False
    rec.failed_reason = None
    rec.failed_at_stage = None
    rec.source = MagicMock()
    rec.source.source_type = SourceType.MTS_LINK
    rec.source.meta = meta or {"mts_record_id": 1, "event_session_id": 2, "needs_mp4": True}
    rec.source.input_source_id = 10
    return rec


@pytest.mark.unit
class TestMtsPrepareGuards:
    def test_needs_prepare_for_mts_initialized_without_file(self):
        assert recording_needs_mts_prepare(_recording()) is True

    def test_skip_when_local_video_exists(self):
        assert recording_needs_mts_prepare(_recording(local_video_path="users/u/1/source.mp4")) is False

    def test_should_skip_after_fresh_ready_ping(self):
        rec = _recording(meta={"needs_mp4": False, "mts_prepare_checked_at": "2099-01-01T00:00:00+00:00"})
        assert should_skip_mts_prepare(rec) is True


@pytest.mark.unit
class TestPrepareOutcomes:
    @pytest.mark.asyncio
    async def test_ready_when_mp4_url_exists(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = [{"size": 100}]
        api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.READY
        assert result.download_url == "https://cdn/ready.mp4"

    @pytest.mark.asyncio
    async def test_assembling_when_size_zero(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = [{"size": 0}]

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.ASSEMBLING

    @pytest.mark.asyncio
    async def test_converting_when_busy(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = [{"size": 100}]
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {"data": {"items": []}}
        api.start_conversion.side_effect = MtsLinkConversionBusyError(403, "busy")

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.CONVERTING


@pytest.mark.unit
class TestApplyPrepareResult:
    def test_converting_sets_pending_conversion_status(self):
        rec = _recording()
        apply_prepare_result(rec, MtsLinkPrepareResult(outcome=MtsPrepareOutcome.CONVERTING, conversion_progress=81))
        assert rec.status == ProcessingStatus.PENDING_CONVERSION
        assert rec.source.meta["conversion_progress"] == 81
        assert rec.failed is False

    def test_ready_clears_failed_flag(self):
        rec = _recording()
        rec.failed = True
        rec.failed_reason = "MTS Link prepare failed"
        rec.failed_at_stage = "download"
        apply_prepare_result(
            rec,
            MtsLinkPrepareResult(outcome=MtsPrepareOutcome.READY, download_url="https://cdn/ready.mp4"),
        )
        assert rec.failed is False
        assert rec.failed_reason is None
        assert rec.failed_at_stage is None
        assert rec.status == ProcessingStatus.INITIALIZED
