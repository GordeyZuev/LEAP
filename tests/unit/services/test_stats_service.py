"""Unit tests for StatsService."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from api.schemas.user.stats import UserStatsResponse


@pytest.mark.unit
class TestStatsServiceGetUserStats:
    """Tests for StatsService.get_user_stats."""

    @pytest.mark.asyncio
    async def test_get_user_stats_all_time(self, mock_db_session, mocker):
        """Test stats aggregation without date filter returns all-time data."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)

        service._count_recordings = AsyncMock(return_value=15)
        service._count_by_status = AsyncMock(return_value={"READY": 10, "PROCESSING": 5})
        service._count_ready_by_template = AsyncMock(return_value=[])
        service._sum_transcription_seconds = AsyncMock(return_value=3600.55)
        mocker.patch.object(StatsService, "_calc_storage_bytes", return_value=2 * 1024**3)

        result = await service.get_user_stats("user_123", user_slug=42)

        assert isinstance(result, UserStatsResponse)
        assert result.recordings_total == 15
        assert result.recordings_by_status == {"READY": 10, "PROCESSING": 5}
        assert result.transcription_total_seconds == 3600.55
        assert result.storage_bytes == 2 * 1024**3
        assert result.storage_gb == round(2 * 1024**3 / (1024**3), 3)
        assert result.period is None

    @pytest.mark.asyncio
    async def test_get_user_stats_with_date_range(self, mock_db_session, mocker):
        """Test stats with date range returns period info."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)

        service._count_recordings = AsyncMock(return_value=3)
        service._count_by_status = AsyncMock(return_value={"READY": 3})
        service._count_ready_by_template = AsyncMock(return_value=[])
        service._sum_transcription_seconds = AsyncMock(return_value=900.0)
        mocker.patch.object(StatsService, "_calc_storage_bytes", return_value=0)

        result = await service.get_user_stats(
            "user_123", user_slug=42, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31)
        )

        assert result.recordings_total == 3
        assert result.period is not None
        assert result.period.from_date == date(2026, 1, 1)
        assert result.period.to_date == date(2026, 1, 31)

    @pytest.mark.asyncio
    async def test_get_user_stats_empty(self, mock_db_session, mocker):
        """Test stats for user with zero recordings."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)

        service._count_recordings = AsyncMock(return_value=0)
        service._count_by_status = AsyncMock(return_value={})
        service._count_ready_by_template = AsyncMock(return_value=[])
        service._sum_transcription_seconds = AsyncMock(return_value=0.0)
        mocker.patch.object(StatsService, "_calc_storage_bytes", return_value=0)

        result = await service.get_user_stats("user_123", user_slug=42)

        assert result.recordings_total == 0
        assert result.transcription_total_seconds == 0.0
        assert result.storage_bytes == 0
        assert result.storage_gb == 0.0

    @pytest.mark.asyncio
    async def test_get_user_stats_transcription_seconds_rounding(self, mock_db_session, mocker):
        """Test that transcription seconds are rounded to 2 decimal places."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)

        service._count_recordings = AsyncMock(return_value=1)
        service._count_by_status = AsyncMock(return_value={"READY": 1})
        service._count_ready_by_template = AsyncMock(return_value=[])
        service._sum_transcription_seconds = AsyncMock(return_value=123.456789)
        mocker.patch.object(StatsService, "_calc_storage_bytes", return_value=0)

        result = await service.get_user_stats("user_123", user_slug=42)

        assert result.transcription_total_seconds == 123.46


@pytest.mark.unit
class TestStatsServiceHelpers:
    """Tests for StatsService helper methods."""

    @pytest.mark.asyncio
    async def test_sum_transcription_seconds_with_data(self, mock_db_session):
        """Test transcription seconds sum returns float from DB scalar."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)
        mock_db_session.scalar = AsyncMock(return_value=7200.5)

        result = await service._sum_transcription_seconds([])

        assert result == 7200.5

    @pytest.mark.asyncio
    async def test_sum_transcription_seconds_null(self, mock_db_session):
        """Test transcription seconds returns 0.0 when no data."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)
        mock_db_session.scalar = AsyncMock(return_value=None)

        result = await service._sum_transcription_seconds([])

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_count_recordings(self, mock_db_session):
        """Test recording count from DB scalar."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)
        mock_db_session.scalar = AsyncMock(return_value=42)

        result = await service._count_recordings([])

        assert result == 42

    @pytest.mark.asyncio
    async def test_count_recordings_none(self, mock_db_session):
        """Test recording count returns 0 when scalar is None."""
        from api.services.stats_service import StatsService

        service = StatsService(mock_db_session)
        mock_db_session.scalar = AsyncMock(return_value=None)

        result = await service._count_recordings([])

        assert result == 0
