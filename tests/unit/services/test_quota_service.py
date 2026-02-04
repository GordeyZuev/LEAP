"""Unit tests for QuotaService."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.unit
class TestQuotaServiceEffectiveQuotas:
    """Tests for effective quotas calculation."""

    @pytest.mark.asyncio
    async def test_get_effective_quotas_with_free_plan(self, mock_db_session):
        """Test effective quotas for free plan user."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"

        # Mock repositories
        service = QuotaService(mock_db_session)

        # Mock subscription repo - no subscription
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=None)

        # Mock free plan
        mock_free_plan = MagicMock()
        mock_free_plan.included_recordings_per_month = 10
        mock_free_plan.included_storage_gb = 5
        mock_free_plan.max_concurrent_tasks = 1
        mock_free_plan.max_automation_jobs = 1
        mock_free_plan.min_automation_interval_hours = 24
        service.plan_repo.get_by_name = AsyncMock(return_value=mock_free_plan)

        # Act
        quotas = await service.get_effective_quotas(user_id)

        # Assert
        assert quotas["max_recordings_per_month"] == 10
        assert quotas["max_storage_gb"] == 5
        assert quotas["max_concurrent_tasks"] == 1
        assert quotas["max_automation_jobs"] == 1
        assert quotas["min_automation_interval_hours"] == 24

    @pytest.mark.asyncio
    async def test_get_effective_quotas_with_custom_overrides(self, mock_db_session):
        """Test effective quotas with custom overrides."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        # Mock subscription with custom overrides
        mock_subscription = MagicMock()
        mock_subscription.plan_id = 2
        mock_subscription.custom_max_recordings_per_month = 500  # Override
        mock_subscription.custom_max_storage_gb = None  # Use plan default
        mock_subscription.custom_max_concurrent_tasks = 10  # Override
        mock_subscription.custom_max_automation_jobs = None
        mock_subscription.custom_min_automation_interval_hours = None
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=mock_subscription)

        # Mock plan
        mock_plan = MagicMock()
        mock_plan.included_recordings_per_month = 100
        mock_plan.included_storage_gb = 50
        mock_plan.max_concurrent_tasks = 5
        mock_plan.max_automation_jobs = 10
        mock_plan.min_automation_interval_hours = 1
        service.plan_repo.get_by_id = AsyncMock(return_value=mock_plan)

        # Act
        quotas = await service.get_effective_quotas(user_id)

        # Assert
        assert quotas["max_recordings_per_month"] == 500  # Custom override
        assert quotas["max_storage_gb"] == 50  # Plan default
        assert quotas["max_concurrent_tasks"] == 10  # Custom override
        assert quotas["max_automation_jobs"] == 10  # Plan default
        assert quotas["min_automation_interval_hours"] == 1  # Plan default

    @pytest.mark.asyncio
    async def test_get_effective_quotas_unlimited(self, mock_db_session):
        """Test effective quotas when no plan exists (unlimited)."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        # No subscription and no free plan found
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=None)
        service.plan_repo.get_by_name = AsyncMock(return_value=None)

        # Act
        quotas = await service.get_effective_quotas(user_id)

        # Assert - all None (unlimited)
        assert quotas["max_recordings_per_month"] is None
        assert quotas["max_storage_gb"] is None
        assert quotas["max_concurrent_tasks"] is None
        assert quotas["max_automation_jobs"] is None
        assert quotas["min_automation_interval_hours"] is None


@pytest.mark.unit
@pytest.mark.skip(reason="QuotaService not fully activated yet - tests for future use")
class TestQuotaServiceChecks:
    """Tests for quota checking methods."""

    @pytest.mark.asyncio
    async def test_check_recordings_quota_within_limit(self, mock_db_session):
        """Test quota check passes when within limit."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        # Mock effective quotas
        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": 100})

        # Mock current usage
        mock_usage = MagicMock()
        mock_usage.recordings_count = 50
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        # Act
        allowed, error = await service.check_recordings_quota(user_id)

        # Assert
        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_recordings_quota_exceeded(self, mock_db_session):
        """Test quota check fails when limit exceeded."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        # Mock effective quotas
        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": 10})

        # Mock current usage - at limit
        mock_usage = MagicMock()
        mock_usage.recordings_count = 10
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        # Mock subscription without pay-as-you-go
        mock_subscription = MagicMock()
        mock_subscription.pay_as_you_go_enabled = False
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=mock_subscription)

        # Act
        allowed, error = await service.check_recordings_quota(user_id)

        # Assert
        assert allowed is False
        assert "10" in error
        assert "quota" in error.lower() or "превышена" in error.lower()

    @pytest.mark.asyncio
    async def test_check_recordings_quota_with_pay_as_you_go(self, mock_db_session):
        """Test quota check allows overage with pay-as-you-go."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        # Mock effective quotas
        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": 10})

        # Mock current usage - at limit
        mock_usage = MagicMock()
        mock_usage.recordings_count = 10
        mock_usage.overage_cost = Decimal("5.00")
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        # Mock subscription with pay-as-you-go enabled
        mock_subscription = MagicMock()
        mock_subscription.pay_as_you_go_enabled = True
        mock_subscription.pay_as_you_go_monthly_limit = Decimal("50.00")
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=mock_subscription)

        # Act
        allowed, error = await service.check_recordings_quota(user_id)

        # Assert
        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_recordings_quota_overage_limit_reached(self, mock_db_session):
        """Test quota check fails when overage limit reached."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": 10})

        # Mock usage with overage at limit
        mock_usage = MagicMock()
        mock_usage.recordings_count = 15
        mock_usage.overage_cost = Decimal("50.00")  # At limit
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        # Mock subscription with overage limit
        mock_subscription = MagicMock()
        mock_subscription.pay_as_you_go_enabled = True
        mock_subscription.pay_as_you_go_monthly_limit = Decimal("50.00")
        service.subscription_repo.get_by_user_id = AsyncMock(return_value=mock_subscription)

        # Act
        allowed, error = await service.check_recordings_quota(user_id)

        # Assert
        assert allowed is False
        assert "overage" in error.lower() or "50" in error

    @pytest.mark.asyncio
    async def test_check_storage_quota_within_limit(self, mock_db_session):
        """Test storage quota check passes."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        service.get_effective_quotas = AsyncMock(return_value={"max_storage_gb": 50})

        # Mock current usage: 10GB
        mock_usage = MagicMock()
        mock_usage.storage_bytes = 10 * 1024 * 1024 * 1024
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        # Act - try to add 5GB
        bytes_to_add = 5 * 1024 * 1024 * 1024
        allowed, error = await service.check_storage_quota(user_id, bytes_to_add)

        # Assert
        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_storage_quota_exceeded(self, mock_db_session):
        """Test storage quota check fails when exceeded."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        service.get_effective_quotas = AsyncMock(return_value={"max_storage_gb": 50})

        # Mock current usage: 48GB
        mock_usage = MagicMock()
        mock_usage.storage_bytes = 48 * 1024 * 1024 * 1024
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        # Act - try to add 5GB (would exceed)
        bytes_to_add = 5 * 1024 * 1024 * 1024
        allowed, error = await service.check_storage_quota(user_id, bytes_to_add)

        # Assert
        assert allowed is False
        assert "50" in error
        assert "gb" in error.lower()

    @pytest.mark.asyncio
    async def test_check_concurrent_tasks_quota(self, mock_db_session):
        """Test concurrent tasks quota check."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        service.get_effective_quotas = AsyncMock(return_value={"max_concurrent_tasks": 3})

        # Mock current tasks count
        mock_usage = MagicMock()
        mock_usage.concurrent_tasks_count = 2
        service.usage_repo.get_by_user_and_period = AsyncMock(return_value=mock_usage)

        # Act
        allowed, error = await service.check_concurrent_tasks_quota(user_id)

        # Assert
        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_check_quota_unlimited(self, mock_db_session):
        """Test quota check with unlimited quota (None)."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)

        service.get_effective_quotas = AsyncMock(return_value={"max_recordings_per_month": None})

        # Act
        allowed, error = await service.check_recordings_quota(user_id)

        # Assert
        assert allowed is True
        assert error is None


@pytest.mark.unit
@pytest.mark.skip(reason="QuotaService not fully activated yet - tests for future use")
class TestQuotaServiceTracking:
    """Tests for usage tracking methods."""

    @pytest.mark.asyncio
    async def test_track_recording_created(self, mock_db_session):
        """Test tracking recording creation."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        service = QuotaService(mock_db_session)
        service.usage_repo.increment_recordings = AsyncMock()

        # Act
        await service.track_recording_created(user_id)

        # Assert
        service.usage_repo.increment_recordings.assert_called_once()
        call_args = service.usage_repo.increment_recordings.call_args
        assert call_args[0][0] == user_id  # user_id
        assert call_args[1]["count"] == 1

    @pytest.mark.asyncio
    async def test_track_storage_added(self, mock_db_session):
        """Test tracking storage usage increase."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        bytes_added = 1024 * 1024 * 100  # 100 MB
        service = QuotaService(mock_db_session)
        service.usage_repo.increment_storage = AsyncMock()

        # Act
        await service.track_storage_added(user_id, bytes_added)

        # Assert
        service.usage_repo.increment_storage.assert_called_once()
        call_args = service.usage_repo.increment_storage.call_args
        assert call_args[0][2] == bytes_added

    @pytest.mark.asyncio
    async def test_track_storage_removed(self, mock_db_session):
        """Test tracking storage usage decrease."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        bytes_removed = 1024 * 1024 * 50  # 50 MB
        service = QuotaService(mock_db_session)
        service.usage_repo.increment_storage = AsyncMock()

        # Act
        await service.track_storage_removed(user_id, bytes_removed)

        # Assert
        service.usage_repo.increment_storage.assert_called_once()
        call_args = service.usage_repo.increment_storage.call_args
        assert call_args[0][2] == -bytes_removed  # Negative value

    @pytest.mark.asyncio
    async def test_set_concurrent_tasks_count(self, mock_db_session):
        """Test setting concurrent tasks count."""
        # Arrange
        from api.services.quota_service import QuotaService

        user_id = "user_123"
        count = 5
        service = QuotaService(mock_db_session)
        service.usage_repo.set_concurrent_tasks = AsyncMock()

        # Act
        await service.set_concurrent_tasks_count(user_id, count)

        # Assert
        service.usage_repo.set_concurrent_tasks.assert_called_once()
        call_args = service.usage_repo.set_concurrent_tasks.call_args
        assert call_args[0][2] == count
