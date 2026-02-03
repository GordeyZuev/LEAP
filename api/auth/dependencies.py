"""Authentication and authorization dependencies"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.security import JWTHelper
from api.dependencies import get_db_session
from api.repositories.auth_repos import UserRepository
from api.schemas.auth import UserInDB
from logger import get_logger

logger = get_logger()

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> UserInDB:
    """
    Get current user from JWT token.
    """
    token = credentials.credentials

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

    return user


async def get_current_active_user(
    current_user: UserInDB = Depends(get_current_user),
) -> UserInDB:
    """
    Get current active user.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


async def check_user_quotas(
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserInDB:
    """
    Check user quotas (new subscription system).
    """
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
