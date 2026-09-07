"""Unit tests for MTS Link prepare-before-run service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.mts_link_api import MtsLinkConversionBusyError, MtsLinkResponseError
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
        api.list_records.assert_not_called()

    @pytest.mark.asyncio
    async def test_assembling_when_size_zero(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = [{"size": 0}]
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {"data": {"items": []}}
        api.get_file.return_value = {}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.ASSEMBLING
        api.start_conversion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_size_zero_with_duration_orders_conversion(self):
        rec = _recording(
            meta={
                "mts_record_id": 1,
                "event_session_id": 2,
                "needs_mp4": True,
                "online_duration": 6058,
            }
        )
        api = AsyncMock()
        api.list_records.return_value = [{"size": 0}]
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {"data": {"items": []}}
        api.start_conversion.return_value = {"id": 9, "state": "waiting"}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.CONVERTING
        api.start_conversion.assert_awaited_once()
        api.get_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_size_zero_reuses_stored_conversion_instead_of_assembling(self):
        rec = _recording(
            status=ProcessingStatus.PENDING_CONVERSION,
            meta={
                "mts_record_id": 1,
                "event_session_id": 2,
                "needs_mp4": True,
                "conversion_id": 77,
            },
        )
        api = AsyncMock()
        api.list_records.return_value = [{"size": 0}]
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {"data": {"items": []}}
        api.get_conversion_status.return_value = {"id": 77, "state": "waiting", "progress": 0}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.CONVERTING
        assert result.conversion_id == 77
        api.start_conversion.assert_not_awaited()
        api.list_records.assert_not_called()

    @pytest.mark.asyncio
    async def test_assembling_when_converted_records_404(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = [{"size": 0}]
        api.get_ready_mp4_url.side_effect = MtsLinkResponseError(404, "missing")
        api.list_converted_records.return_value = {"data": {"items": []}}
        api.get_file.return_value = {}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.ASSEMBLING
        api.start_conversion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_when_converted_records_500(self):
        rec = _recording()
        api = AsyncMock()
        api.get_ready_mp4_url.side_effect = MtsLinkResponseError(500, "boom")

        with (
            patch(
                "api.services.mts_link_prepare.resolve_mts_link_context",
                new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
            ),
            patch("api.services.mts_link_prepare.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.FAILED

    @pytest.mark.asyncio
    async def test_ready_when_size_zero_but_mp4_exists(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = [{"size": 0}]
        api.get_ready_mp4_url.return_value = "https://cdn/ready.mp4"

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.READY
        assert result.download_url == "https://cdn/ready.mp4"
        api.list_records.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_when_record_missing_and_no_mp4(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = []
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {"data": {"items": []}}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.FAILED

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
        api.start_conversion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reuses_stored_conversion_id_instead_of_posting_again(self):
        rec = _recording(
            status=ProcessingStatus.PENDING_CONVERSION,
            meta={
                "mts_record_id": 1,
                "event_session_id": 2,
                "needs_mp4": True,
                "conversion_id": 77,
            },
        )
        api = AsyncMock()
        api.list_records.return_value = [{"size": 100}]
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {"data": {"items": []}}
        api.get_conversion_status.return_value = {"id": 77, "state": "processing", "progress": 40}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.CONVERTING
        assert result.conversion_id == 77
        api.start_conversion.assert_not_awaited()
        api.list_converted_records.assert_awaited()

    @pytest.mark.asyncio
    async def test_reuses_completed_job_from_list_instead_of_posting(self):
        rec = _recording()
        api = AsyncMock()
        api.list_records.return_value = [{"size": 100}]
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {
            "data": {"items": [{"id": 5, "state": "completed", "recordFile": {"id": 1}}]}
        }

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.READY
        assert result.conversion_id == 5
        api.start_conversion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ready_when_stored_conversion_is_completed_without_url(self):
        rec = _recording(
            status=ProcessingStatus.PENDING_CONVERSION,
            meta={
                "mts_record_id": 1,
                "event_session_id": 2,
                "needs_mp4": True,
                "conversion_id": 77,
                "download_url": "https://cdn/stored.mp4",
            },
        )
        api = AsyncMock()
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {"data": {"items": []}}
        api.get_conversion_status.return_value = {"id": 77, "state": "completed"}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.READY
        assert result.conversion_id == 77
        api.start_conversion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_prefers_list_processing_over_stored_canceled_id(self):
        rec = _recording(
            status=ProcessingStatus.PENDING_CONVERSION,
            meta={
                "mts_record_id": 1,
                "event_session_id": 2,
                "needs_mp4": True,
                "conversion_id": 11,
            },
        )
        api = AsyncMock()
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {
            "data": {
                "items": [
                    {"id": 11, "state": "canceled", "progress": 0, "recordFile": {"id": 1}},
                    {"id": 22, "state": "processing", "progress": 68, "recordFile": {"id": 1}},
                ]
            }
        }
        api.get_conversion_status.return_value = {"id": 11, "state": "canceled"}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.outcome == MtsPrepareOutcome.CONVERTING
        assert result.conversion_id == 22
        assert result.conversion_progress == 68
        api.start_conversion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_keeps_stored_processing_over_newer_lower_progress(self):
        rec = _recording(
            status=ProcessingStatus.PENDING_CONVERSION,
            meta={
                "mts_record_id": 1,
                "event_session_id": 2,
                "needs_mp4": True,
                "conversion_id": 11,
            },
        )
        api = AsyncMock()
        api.get_ready_mp4_url.return_value = None
        api.list_converted_records.return_value = {
            "data": {"items": [{"id": 22, "state": "processing", "progress": 5, "recordFile": {"id": 1}}]}
        }
        api.get_conversion_status.return_value = {"id": 11, "state": "processing", "progress": 65}

        with patch(
            "api.services.mts_link_prepare.resolve_mts_link_context",
            new=AsyncMock(return_value=(1, api, {"conversion_quality": "720", "conversion_view": "none"})),
        ):
            result = await prepare_mts_link_recording(AsyncMock(), rec, "user")

        assert result.conversion_id == 11
        assert result.conversion_progress == 65
        api.start_conversion.assert_not_awaited()


@pytest.mark.unit
class TestApplyPrepareResult:
    def test_converting_sets_pending_conversion_status(self):
        rec = _recording()
        apply_prepare_result(rec, MtsLinkPrepareResult(outcome=MtsPrepareOutcome.CONVERTING, conversion_progress=81))
        assert rec.status == ProcessingStatus.PENDING_CONVERSION
        assert rec.source.meta["conversion_progress"] == 81
        assert rec.source.meta["source_processing_incomplete"] is False
        assert rec.failed is False

    def test_converting_keeps_previous_progress_when_api_omits_it(self):
        rec = _recording(meta={"mts_record_id": 1, "event_session_id": 2, "conversion_progress": 65})
        apply_prepare_result(
            rec, MtsLinkPrepareResult(outcome=MtsPrepareOutcome.CONVERTING, conversion_state="processing")
        )
        assert rec.source.meta["conversion_progress"] == 65

    def test_assembling_sets_pending_source(self):
        rec = _recording()
        apply_prepare_result(rec, MtsLinkPrepareResult(outcome=MtsPrepareOutcome.ASSEMBLING, online_size=0))
        assert rec.status == ProcessingStatus.PENDING_SOURCE
        assert rec.source.meta["source_processing_incomplete"] is True

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
        assert rec.source.meta["source_processing_incomplete"] is False
        assert rec.source.meta["needs_mp4"] is False

    def test_ready_without_url_still_clears_pending_conversion(self):
        rec = _recording(status=ProcessingStatus.PENDING_CONVERSION)
        rec.source.meta["download_url"] = "https://cdn/stored.mp4"
        apply_prepare_result(rec, MtsLinkPrepareResult(outcome=MtsPrepareOutcome.READY, conversion_state="completed"))
        assert rec.status == ProcessingStatus.INITIALIZED
        assert rec.source.meta["needs_mp4"] is False
        assert rec.source.meta["download_url"] == "https://cdn/stored.mp4"
