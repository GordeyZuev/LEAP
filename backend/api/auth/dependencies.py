"""Authentication and authorization dependencies."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.cookies import ACCESS_COOKIE_NAME
from api.auth.security import JWTHelper
from api.dependencies import get_db_session
from api.repositories.auth_repos import UserRepository
from api.schemas.auth import UserInDB
from logger import get_logger

logger = get_logger()


def _extract_access_token(request: Request) -> str | None:
    """Pull an access token from ``Authorization: Bearer`` (preferred) or the access cookie.

    Bearer takes precedence so an explicit header always wins over a cookie left
    from a different browser session.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip() or None
    return request.cookies.get(ACCESS_COOKIE_NAME)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> UserInDB:
    """Get current user from JWT token (header or httpOnly cookie)."""
    token = _extract_access_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = JWTHelper.verify_token(token, token_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # Surface the authenticated user_id to the HTTP access-log middleware
    # (and any other downstream code that reads request.state). Truncated to
    # the leading 8 chars to match the convention used elsewhere in logs.
    request.state.user_id = str(user.id)[:8]

    return user


async def get_current_active_user(
    current_user: UserInDB = Depends(get_current_user),
) -> UserInDB:
    """Get current active user.

    Deprecated: use ``get_current_user`` directly — it already checks ``is_active``.
    This wrapper is kept only for backward compatibility.
    """
    return current_user


async def check_user_quotas(
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserInDB:
    """Check user quotas (new subscription system)."""
    from api.services.quota_service import QuotaService

    quota_service = QuotaService(session)

    # Check recordings quota
    allowed, error = await quota_service.check_recordings_quota(current_user.id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error,
        )

    # Check concurrent tasks quota
    allowed, error = await quota_service.check_concurrent_tasks_quota(current_user.id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error,
        )

    return current_user
