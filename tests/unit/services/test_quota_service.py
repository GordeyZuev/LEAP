"""Unit tests for QuotaService."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.unit
class TestQuotaServiceEffectiveQuotas:
    """Tests for effective quotas calculation."""

    @pytest.mark.asyncio
    async def test_get_effective_quotas_no_subscription_uses_defaults(self, mock_db_session):
        """Test that users without a subscription get DEFAULT_QUOTAS from code."""
        from api.services.quota_service import QuotaService
        from config.settings import DEFAULT_QUOTAS

        service = QuotaService(mock_db_session)
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=None)

        quotas = await service.get_effective_quotas("user_123")

        assert quotas == DEFAULT_QUOTAS
        assert quotas is not DEFAULT_QUOTAS  # must be a copy

    @pytest.mark.asyncio
    async def test_get_effective_quotas_with_custom_overrides(self, mock_db_session):
        """Test effective quotas with subscription plan + custom overrides."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)

        mock_subscription = MagicMock()
        mock_subscription.plan_id = 2
        mock_subscription.custom_max_recordings_per_month = 500
        mock_subscription.custom_max_storage_gb = None
        mock_subscription.custom_max_concurrent_tasks = 10
        mock_subscription.custom_max_automation_jobs = None
        mock_subscription.custom_min_automation_interval_hours = None
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=mock_subscription)

        mock_plan = MagicMock()
        mock_plan.included_recordings_per_month = 100
        mock_plan.included_storage_gb = 50
        mock_plan.max_concurrent_tasks = 5
        mock_plan.max_automation_jobs = 10
        mock_plan.min_automation_interval_hours = 1
        service.plan_repo.get_by_id = AsyncMock(return_value=mock_plan)

        quotas = await service.get_effective_quotas("user_123")

        assert quotas["max_recordings_per_month"] == 500  # custom override
        assert quotas["max_storage_gb"] == 50  # plan default
        assert quotas["max_concurrent_tasks"] == 10  # custom override
        assert quotas["max_automation_jobs"] == 10  # plan default
        assert quotas["min_automation_interval_hours"] == 1  # plan default


@pytest.mark.unit
class TestQuotaServiceChecks:
    """Tests for quota checking methods."""

    @pytest.mark.asyncio
    async def test_check_recordings_quota_within_limit(self, mock_db_session):
        """Test quota check passes when within limit."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": 100})

        mock_usage = MagicMock()
        mock_usage.recordings_count = 50
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        allowed, error = await service.check_recordings_quota("user_123")

        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_recordings_quota_exceeded(self, mock_db_session):
        """Test quota check fails when limit exceeded."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": 10})

        mock_usage = MagicMock()
        mock_usage.recordings_count = 10
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        allowed, error = await service.check_recordings_quota("user_123")

        assert allowed is False
        assert "10" in error
        assert "exceeded" in error.lower() or "quota" in error.lower()

    @pytest.mark.asyncio
    async def test_check_storage_quota_within_limit(self, mock_db_session, mocker):
        """Test storage quota check passes when disk usage is below limit."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_storage_gb": 50})

        mocker.patch.object(QuotaService, "_calc_storage_bytes", return_value=10 * 1024 * 1024 * 1024)

        allowed, error = await service.check_storage_quota("user_123", user_slug=42)

        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_storage_quota_exceeded(self, mock_db_session, mocker):
        """Test storage quota check fails when disk usage exceeds limit."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_storage_gb": 50})

        mocker.patch.object(QuotaService, "_calc_storage_bytes", return_value=55 * 1024 * 1024 * 1024)

        allowed, error = await service.check_storage_quota("user_123", user_slug=42)

        assert allowed is False
        assert "50" in error
        assert "GB" in error

    @pytest.mark.asyncio
    async def test_check_concurrent_tasks_quota(self, mock_db_session):
        """Test concurrent tasks quota check."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_concurrent_tasks": 3})

        mock_usage = MagicMock()
        mock_usage.concurrent_tasks_count = 2
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        allowed, error = await service.check_concurrent_tasks_quota("user_123")

        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_concurrent_tasks_quota_exceeded(self, mock_db_session):
        """Test concurrent tasks quota check fails at limit."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_concurrent_tasks": 3})

        mock_usage = MagicMock()
        mock_usage.concurrent_tasks_count = 3
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        allowed, error = await service.check_concurrent_tasks_quota("user_123")

        assert allowed is False
        assert "3" in error

    @pytest.mark.asyncio
    async def test_check_quota_unlimited(self, mock_db_session):
        """Test quota check with unlimited quota (None)."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": None})

        allowed, error = await service.check_recordings_quota("user_123")

        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_storage_quota_unlimited(self, mock_db_session):
        """Test storage quota check passes when limit is None (unlimited)."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.get_effective_quotas = AsyncMock(return_value={"max_storage_gb": None})

        allowed, error = await service.check_storage_quota("user_123", user_slug=42)

        assert allowed is True
        assert error is None


@pytest.mark.unit
class TestQuotaServiceTracking:
    """Tests for usage tracking methods."""

    @pytest.mark.asyncio
    async def test_track_recording_created(self, mock_db_session):
        """Test tracking recording creation."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.usage_repo.increment_recordings = AsyncMock()

        await service.track_recording_created("user_123")

        service.usage_repo.increment_recordings.assert_called_once()
        call_args = service.usage_repo.increment_recordings.call_args
        assert call_args[0][0] == "user_123"
        assert call_args[1]["count"] == 1

    @pytest.mark.asyncio
    async def test_set_concurrent_tasks_count(self, mock_db_session):
        """Test setting concurrent tasks count."""
        from api.services.quota_service import QuotaService

        service = QuotaService(mock_db_session)
        service.usage_repo.set_concurrent_tasks = AsyncMock()

        await service.set_concurrent_tasks_count("user_123", 5)

        service.usage_repo.set_concurrent_tasks.assert_called_once()
        call_args = service.usage_repo.set_concurrent_tasks.call_args
        assert call_args[0][2] == 5
