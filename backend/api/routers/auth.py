"""Authentication endpoints.

Browser clients authenticate via httpOnly cookies set on the same response as
the bootstrap call plus a ``X-CSRF-Token`` header echoed from the csrf cookie.
CLI / server-to-server clients keep using ``Authorization: Bearer`` with the
tokens returned in the response body.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.cookies import (
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    generate_csrf_token,
    set_auth_cookies,
)
from api.auth.dependencies import get_current_user
from api.auth.device import extract_client_ip, hash_ip, parse_device_label
from api.auth.security import JWTHelper, PasswordHelper
from api.dependencies import get_db_session
from api.repositories.auth_repos import (
    RefreshTokenRepository,
    UserRepository,
)
from api.repositories.config_repos import UserConfigRepository
from api.schemas.auth import (
    LoginRequest,
    LogoutAllResponse,
    LogoutResponse,
    RefreshTokenCreate,
    RefreshTokenRequest,
    RegisterRequest,
    SessionInfo,
    SessionListResponse,
    SessionResponse,
    UserCreate,
    UserInDB,
    UserResponse,
    UserUpdate,
)
from config.settings import get_settings
from logger import get_logger
from utils.thumbnail_manager import get_thumbnail_manager

logger = get_logger()
settings = get_settings()

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _resolve_refresh_token(request: Request, body: RefreshTokenRequest) -> str:
    """Return the refresh token from the request body or the refresh cookie."""
    token = body.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
    return token


async def _issue_session(
    *,
    user: UserInDB,
    request: Request,
    response: Response,
    token_repo: RefreshTokenRepository,
) -> SessionResponse:
    """Mint a fresh token pair, persist the refresh token, and write session cookies.

    Shared by ``/auth/login``, ``/auth/refresh``, and ``/auth/logout-others`` so
    all session-issuing paths produce an identical shape and capture the same
    device metadata.
    """
    access_token = JWTHelper.create_access_token({"user_id": user.id, "email": user.email, "tv": user.token_version})
    refresh_token = JWTHelper.create_refresh_token({"user_id": user.id, "tv": user.token_version})

    user_agent = request.headers.get("user-agent")
    client_ip = extract_client_ip(request)

    expires_at = datetime.now(UTC) + timedelta(days=settings.security.jwt_refresh_token_expire_days)
    await token_repo.create(
        token_data=RefreshTokenCreate(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
            user_agent=user_agent[:500] if user_agent else None,
            ip_hash=hash_ip(client_ip),
            device_label=parse_device_label(user_agent),
        ),
    )

    csrf_token = generate_csrf_token()
    set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
    )

    return SessionResponse(
        csrf_token=csrf_token,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.security.jwt_access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_db_session)):
    """Register a new user. No automatic login — call ``/auth/login`` next."""
    user_repo = UserRepository(session)
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

    default_config = await config_repo.get_effective_config(user.id)
    await config_repo.create(user_id=user.id, config_data=default_config)
    logger.info(f"Created default config for user: user_id={user.id}")

    # Storage backend creates per-user prefixes lazily on first write; only
    # thumbnails need an explicit seed copy.
    thumbnail_manager = get_thumbnail_manager()
    await thumbnail_manager.initialize_user_thumbnails(user.user_slug, copy_templates=True)

    await session.commit()

    logger.info(f"New user registered: {user.email} (ID: {user.id})")

    return UserResponse.model_validate(user)


@router.post("/login", response_model=SessionResponse)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Authenticate the user and issue a fresh session (cookies + JSON body)."""
    user_repo = UserRepository(session)
    token_repo = RefreshTokenRepository(session)

    user = await user_repo.get_by_email(body.email)
    if not user or not PasswordHelper.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")

    await user_repo.update(user.id, UserUpdate(last_login_at=datetime.now(UTC)))

    session_response = await _issue_session(user=user, request=request, response=response, token_repo=token_repo)
    logger.info(f"User logged in: {user.email} (ID: {user.id})")
    return session_response


@router.post("/refresh", response_model=SessionResponse)
async def refresh_token(
    request: Request,
    response: Response,
    body: RefreshTokenRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    """Rotate access + refresh tokens. Accepts the old refresh from cookie or body."""
    body = body or RefreshTokenRequest()
    user_repo = UserRepository(session)
    token_repo = RefreshTokenRepository(session)

    raw_refresh = _resolve_refresh_token(request, body)

    payload = JWTHelper.verify_token(raw_refresh, token_type="refresh")
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    token_exists = await token_repo.get_by_token(raw_refresh)
    if not token_exists or token_exists.is_revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked or not found")

    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not found or inactive")

    if payload.get("tv") != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalidated")

    await token_repo.touch_last_used(raw_refresh)
    await token_repo.revoke(raw_refresh)

    session_response = await _issue_session(user=user, request=request, response=response, token_repo=token_repo)
    logger.info(f"Token refreshed for user: {user.email} (ID: {user.id})")
    return session_response


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    body: RefreshTokenRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    """Revoke the refresh token (if present) and clear session cookies.

    Always succeeds — even without a valid refresh token we still scrub cookies
    so a broken session can recover by hitting this endpoint.
    """
    body = body or RefreshTokenRequest()
    token_repo = RefreshTokenRepository(session)

    raw_refresh = body.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh:
        await token_repo.revoke(raw_refresh)

    clear_auth_cookies(response)
    logger.info("User logged out")
    return LogoutResponse(message="Successfully logged out")


@router.post("/logout-all", response_model=LogoutAllResponse)
async def logout_all(
    response: Response,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> LogoutAllResponse:
    """Revoke every active session for the current user across all devices.

    Bumps ``users.token_version`` so any access token already in flight starts
    failing at the next protected request (no 30-min lag). Also revokes refresh
    rows for audit / per-session UI visibility.
    """
    user_repo = UserRepository(session)
    token_repo = RefreshTokenRepository(session)

    await user_repo.bump_token_version(current_user.id)
    count = await token_repo.revoke_all_by_user(current_user.id)
    clear_auth_cookies(response)

    logger.info(f"User {current_user.id} logged out from all devices ({count} tokens revoked)")

    return LogoutAllResponse(
        message="Successfully logged out from all devices",
        revoked_tokens=count,
    )


@router.post("/logout-others", response_model=SessionResponse)
async def logout_others(
    request: Request,
    response: Response,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """Sign out every other device while keeping the current session alive.

    Implementation: bump ``token_version`` (kills every JWT for this user) and
    immediately mint a fresh pair for the caller. Other devices fail their next
    request; the caller's cookies are silently rotated.
    """
    user_repo = UserRepository(session)
    token_repo = RefreshTokenRepository(session)

    await user_repo.bump_token_version(current_user.id)
    revoked = await token_repo.revoke_all_by_user(current_user.id)

    fresh_user = await user_repo.get_by_id(current_user.id)
    if not fresh_user:
        # Shouldn't happen — `get_current_user` just resolved the row.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    session_response = await _issue_session(user=fresh_user, request=request, response=response, token_repo=token_repo)
    logger.info(f"User {current_user.id} logged out from other devices ({max(revoked - 1, 0)} other sessions revoked)")
    return session_response


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SessionListResponse:
    """List active refresh-token sessions for the current user."""
    token_repo = RefreshTokenRepository(session)
    sessions = await token_repo.list_active_by_user(current_user.id)

    current_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=s.id,
                device_label=s.device_label,
                user_agent=s.user_agent,
                last_used_at=s.last_used_at,
                created_at=s.created_at,
                is_current=bool(current_refresh and s.token == current_refresh),
            )
            for s in sessions
        ]
    )


@router.delete("/sessions/{session_id}", response_model=LogoutResponse)
async def revoke_session(
    session_id: int,
    request: Request,
    response: Response,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    """Revoke a specific refresh-token session owned by the current user.

    Does NOT bump ``token_version`` — per-device revocation is eventually
    consistent (the revoked device's access token dies on next refresh, which
    happens within ``jwt_access_token_expire_minutes``). For an instant nuke
    use ``/auth/logout-all`` instead.
    """
    token_repo = RefreshTokenRepository(session)

    target = await token_repo.get_by_id_for_user(session_id, current_user.id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await token_repo.revoke_by_id(session_id)

    current_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if current_refresh and target.token == current_refresh:
        # Caller revoked their own current session — strip cookies so the
        # browser is forced back through login on the next request.
        clear_auth_cookies(response)

    logger.info(f"User {current_user.id} revoked session {session_id}")
    return LogoutResponse(message="Session revoked")
