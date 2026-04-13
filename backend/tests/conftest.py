"""Shared test fixtures for all tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_user():
    """Mock user for testing endpoints."""
    user = MagicMock()
    user.id = "user_123"
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.role = "user"
    user.is_active = True
    user.is_verified = True
    user.timezone = "UTC"
    user.user_slug = "test_user"
    user.can_create_templates = True
    user.created_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
    return user


@pytest.fixture
def mock_admin_user():
    """Mock admin user for testing admin endpoints."""
    user = MagicMock()
    user.id = "admin_123"
    user.email = "admin@example.com"
    user.full_name = "Admin User"
    user.role = "admin"
    user.is_active = True
    user.is_verified = True
    user.timezone = "UTC"
    user.user_slug = "admin_user"
    user.can_create_templates = True
    user.created_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
    return user


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_service_context(mock_db_session, mock_user):
    """Mock ServiceContext for testing."""
    from api.core.context import ServiceContext

    return ServiceContext(session=mock_db_session, user_id=mock_user.id)


@pytest.fixture
def client(mock_user, mock_db_session):
    """TestClient with mocked dependencies."""
    from api.auth.dependencies import get_current_active_user, get_current_user
    from api.core.dependencies import get_service_context
    from api.dependencies import get_db_session
    from api.main import app

    # Mock authentication
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: mock_db_session

    # Mock service context
    def mock_get_service_context():
        from api.core.context import ServiceContext

        return ServiceContext(session=mock_db_session, user_id=mock_user.id)

    app.dependency_overrides[get_service_context] = mock_get_service_context

    with TestClient(app) as test_client:
        yield test_client

    # Clear overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(mock_admin_user, mock_db_session):
    """TestClient with admin user."""
    from api.auth.dependencies import get_current_active_user, get_current_user
    from api.core.dependencies import get_service_context
    from api.dependencies import get_db_session
    from api.main import app

    # Mock admin authentication
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_current_active_user] = lambda: mock_admin_user
    app.dependency_overrides[get_db_session] = lambda: mock_db_session

    # Mock service context for admin
    def mock_get_service_context():
        from api.core.context import ServiceContext

        return ServiceContext(session=mock_db_session, user_id=mock_admin_user.id)

    app.dependency_overrides[get_service_context] = mock_get_service_context

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
