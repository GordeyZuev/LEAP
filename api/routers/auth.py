"""Authentication and user management endpoints"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.security import JWTHelper, PasswordHelper
from api.dependencies import get_db_session
from api.repositories.auth_repos import (
    RefreshTokenRepository,
    UserRepository,
)
from api.repositories.config_repos import UserConfigRepository
from api.repositories.subscription_repos import (
    SubscriptionPlanRepository,
    UserSubscriptionRepository,
)
from api.schemas.auth import (
    LoginRequest,
    LogoutAllResponse,
    LogoutResponse,
    RefreshTokenCreate,
    RefreshTokenRequest,
    RegisterRequest,
    TokenPair,
    UserCreate,
    UserResponse,
    UserSubscriptionCreate,
    UserUpdate,
)
from config.settings import get_settings
from file_storage.path_builder import StoragePathBuilder
from logger import get_logger
from utils.thumbnail_manager import get_thumbnail_manager

logger = get_logger()
settings = get_settings()

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_db_session)):
    """
    Register new user.

    Args:
        request: Registration data
        session: Database session

    Returns:
        Information about created user

    Raises:
        HTTPException: If email already exists
    """
    user_repo = UserRepository(session)
    subscription_repo = UserSubscriptionRepository(session)
    plan_repo = SubscriptionPlanRepository(session)
    config_repo = UserConfigRepository(session)

    existing_user = await user_repo.get_by_email(request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    hashed_password = PasswordHelper.hash_password(request.password)

    user_create = UserCreate(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
    )

    user = await user_repo.create(user_data=user_create, hashed_password=hashed_password)

    # Create free subscription
    free_plan = await plan_repo.get_by_name("free")
    if not free_plan:
        logger.error("Free plan not found in database! User registered without subscription.")
    else:
        subscription_create = UserSubscriptionCreate(
            user_id=user.id,
            plan_id=free_plan.id,
        )
        await subscription_repo.create(subscription_create)

    # Create user config with default settings
    default_config = await config_repo.get_effective_config(user.id)
    await config_repo.create(user_id=user.id, config_data=default_config)
    logger.info(f"Created default config for user: user_id={user.id}")

    # Create user directories
    # TODO(S3): Replace with backend operations when S3 support added
    # For now: direct directory creation (LOCAL only)
    storage_builder = StoragePathBuilder()
    user_root = storage_builder.user_root(user.user_slug)
    user_root.mkdir(parents=True, exist_ok=True)

    # Create thumbnails directory for user thumbnails
    user_thumbnails = storage_builder.user_thumbnails_dir(user.user_slug)
    user_thumbnails.mkdir(parents=True, exist_ok=True)

    logger.info(f"Created user directories: {user_root}")

    # Initialize thumbnails (copy all shared templates)
    thumbnail_manager = get_thumbnail_manager()
    thumbnail_manager.initialize_user_thumbnails(user.user_slug, copy_templates=True)

    await session.commit()

    logger.info(f"New user registered: {user.email} (ID: {user.id})")

    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    """
    Login to the system.

    Args:
        request: Login data
        session: Database session

    Returns:
        Access and refresh tokens

    Raises:
        HTTPException: If credentials are incorrect
    """
    user_repo = UserRepository(session)
    token_repo = RefreshTokenRepository(session)

    user = await user_repo.get_by_email(request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not PasswordHelper.verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    access_token = JWTHelper.create_access_token({"user_id": user.id, "email": user.email})
    refresh_token = JWTHelper.create_refresh_token({"user_id": user.id})

    expires_at = datetime.utcnow() + timedelta(days=settings.security.jwt_refresh_token_expire_days)

    token_create = RefreshTokenCreate(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    await token_repo.create(token_data=token_create)

    user_update = UserUpdate(last_login_at=datetime.utcnow())
    await user_repo.update(user.id, user_update)

    logger.info(f"User logged in: {user.email} (ID: {user.id})")

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.security.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(request: RefreshTokenRequest, session: AsyncSession = Depends(get_db_session)):
    """
    Refresh access token using refresh token.

    Args:
        request: Refresh token
        session: Database session

    Returns:
        New access and refresh tokens

    Raises:
        HTTPException: If token is invalid
    """
    user_repo = UserRepository(session)
    token_repo = RefreshTokenRepository(session)

    payload = JWTHelper.verify_token(request.refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    token_exists = await token_repo.get_by_token(request.refresh_token)
    if not token_exists or token_exists.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked or not found",
        )

    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found or inactive",
        )

    new_access_token = JWTHelper.create_access_token({"user_id": user.id, "email": user.email})
    new_refresh_token = JWTHelper.create_refresh_token({"user_id": user.id})

    await token_repo.revoke(request.refresh_token)

    expires_at = datetime.utcnow() + timedelta(days=settings.security.jwt_refresh_token_expire_days)

    token_create = RefreshTokenCreate(
        user_id=user.id,
        token=new_refresh_token,
        expires_at=expires_at,
    )
    await token_repo.create(token_data=token_create)

    logger.info(f"Token refreshed for user: {user.email} (ID: {user.id})")

    return TokenPair(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.security.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: RefreshTokenRequest, session: AsyncSession = Depends(get_db_session)) -> LogoutResponse:
    """
    Logout from the system (revoke refresh token).

    Args:
        request: Refresh token
        session: Database session

    Returns:
        Confirmation of logout
    """
    token_repo = RefreshTokenRepository(session)
    await token_repo.revoke(request.refresh_token)
    logger.info("User logged out")
    return LogoutResponse(message="Successfully logged out")


@router.post("/logout-all", response_model=LogoutAllResponse)
async def logout_all(
    request: RefreshTokenRequest, session: AsyncSession = Depends(get_db_session)
) -> LogoutAllResponse:
    """
    Logout from all devices (revoke all refresh tokens for the user).

    Args:
        request: Any valid refresh token for the user
        session: Database session

    Returns:
        Number of revoked tokens
    """
    token_repo = RefreshTokenRepository(session)

    # Get user_id from token
    payload = JWTHelper.verify_token(request.refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Revoke all tokens for the user
    count = await token_repo.revoke_all_by_user(user_id)

    logger.info(f"User {user_id} logged out from all devices ({count} tokens revoked)")

    return LogoutAllResponse(
        message="Successfully logged out from all devices",
        revoked_tokens=count,
    )
