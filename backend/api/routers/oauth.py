"""OAuth endpoints for YouTube and VK"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.auth.encryption import get_encryption
from api.dependencies import get_db_session, get_redis
from api.repositories.auth_repos import UserCredentialRepository
from api.schemas.auth import UserCredentialCreate, UserInDB
from api.schemas.oauth import (
    OAuthAuthorizeResponse,
    OAuthImplicitFlowResponse,
    VKImplicitFlowCallbackResponse,
)
from api.services.oauth_platforms import OAuthPlatformConfig, get_platform_config
from api.services.oauth_service import OAuthService
from api.services.oauth_state import OAuthStateManager
from config.settings import get_settings
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/v1/oauth", tags=["OAuth"])


def get_state_manager(redis=Depends(get_redis)) -> OAuthStateManager:
    """Dependency to get OAuth state manager."""
    return OAuthStateManager(redis)


class _PlatformAccountConfig(TypedDict, total=False):
    """Config for OAuth account identifier fetch."""

    url: str
    headers: dict[str, str]
    params: dict[str, str]
    extract: Callable[[dict], str]


async def _fetch_api_data(
    url: str, headers: dict | None = None, params: dict | None = None
) -> tuple[bool, dict | None]:
    """Fetch data from API endpoint with error handling."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            logger.debug(f"API response: status={response.status_code}")

            if response.status_code == 200:
                return True, response.json()

            logger.warning(f"API request failed: status={response.status_code} body={response.text[:200]}")
            return False, None
    except Exception as e:
        logger.error(f"API request exception: {type(e).__name__}: {e}")
        return False, None


async def get_account_identifier(platform: str, access_token: str) -> str:
    """Get unique account identifier from OAuth provider (supports multiple accounts per platform)."""
    logger.info(f"Getting account identifier for platform={platform}")

    platform_configs: dict[str, _PlatformAccountConfig] = {
        "youtube": {
            "url": "https://www.googleapis.com/oauth2/v2/userinfo",
            "headers": {"Authorization": f"Bearer {access_token}"},
            "extract": lambda data: data.get("email", "unknown"),
        },
        "vk_video": {
            "url": "https://api.vk.com/method/users.get",
            "params": {"access_token": access_token, "v": "5.131"},
            "extract": lambda data: f"vk_{data['response'][0].get('id')}" if data.get("response") else "oauth_auto",
        },
        "zoom": {
            "url": "https://api.zoom.us/v2/users/me",
            "headers": {"Authorization": f"Bearer {access_token}"},
            "extract": lambda data: data.get("email", "unknown"),
        },
    }

    config = platform_configs.get(platform)
    if not config or "url" not in config:
        logger.warning(f"Unknown platform {platform}, returning fallback")
        return "oauth_auto"

    success, data = await _fetch_api_data(
        config["url"],
        headers=config.get("headers"),
        params=config.get("params"),
    )

    if success and data and (extract := config.get("extract")):
        account_id = extract(data)
        logger.info(f"Retrieved {platform} account identifier: {account_id}")
        return account_id

    return "oauth_auto"


def _build_oauth_credentials(platform: str, token_data: dict, config: OAuthPlatformConfig) -> dict:
    """Build platform-specific credential structure."""
    expires_in = token_data.get("expires_in", 3600 if platform != "vk_video" else 86400)
    expiry = datetime.now(UTC) + timedelta(seconds=expires_in)
    expiry_str = expiry.isoformat().replace("+00:00", "Z")

    if platform == "youtube":
        return {
            "client_secrets": {
                "web": {
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "project_id": "zoomuploader",
                    "auth_uri": config.authorization_url,
                    "token_uri": config.token_url,
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": [config.redirect_uri],
                }
            },
            "token": {
                "token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "token_uri": config.token_url,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "scopes": config.scopes,
                "expiry": expiry_str,
            },
        }

    if platform == "vk_video":
        return {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "user_id": token_data.get("user_id"),
            "expires_in": expires_in,
            "expiry": expiry_str,
        }

    if platform == "zoom":
        return {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "bearer"),
            "scope": token_data.get("scope", " ".join(config.scopes)),
            "expires_in": expires_in,
            "expiry": expiry_str,
        }

    raise ValueError(f"Unsupported platform: {platform}")


async def save_oauth_credentials(
    user_id: str,
    platform: str,
    token_data: dict,
    config: OAuthPlatformConfig,
    session: AsyncSession,
) -> int:
    """Save or update OAuth credentials with automatic account detection (upsert)."""
    from api.schemas.auth import UserCredentialUpdate

    encryption = get_encryption()
    cred_repo = UserCredentialRepository(session)

    credentials = _build_oauth_credentials(platform, token_data, config)
    account_name = await get_account_identifier(platform, token_data["access_token"])
    encrypted_data = encryption.encrypt_credentials(credentials)

    existing_cred = await cred_repo.get_by_platform(user_id, platform, account_name=account_name)

    if existing_cred:
        cred_update = UserCredentialUpdate(encrypted_data=encrypted_data, is_active=True)
        credential = await cred_repo.update(existing_cred.id, cred_update)
        action = "updated"
    else:
        cred_create = UserCredentialCreate(
            user_id=user_id,
            platform=platform,
            account_name=account_name,
            encrypted_data=encrypted_data,
        )
        credential = await cred_repo.create(credential_data=cred_create)
        action = "created"

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save OAuth credentials"
        )

    logger.info(
        f"OAuth credentials {action}: user_id={user_id} platform={platform} "
        f"account={account_name} credential_id={credential.id}"
    )

    return credential.id


@router.get("/youtube/authorize", response_model=OAuthAuthorizeResponse)
async def youtube_authorize(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
    state_manager: OAuthStateManager = Depends(get_state_manager),
):
    """Initiate YouTube OAuth flow."""
    try:
        config = get_platform_config("youtube")
        oauth_service = OAuthService(config, state_manager)

        ip_address = request.client.host if request.client else None
        result = await oauth_service.get_authorization_url(current_user.id, ip_address)

        logger.info(f"YouTube OAuth initiated: user_id={current_user.id}")
        return result

    except Exception as e:
        logger.error(f"YouTube OAuth authorization failed: user_id={current_user.id} error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        )


@router.get("/youtube/callback")
async def youtube_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State token for CSRF protection"),
    error: str | None = Query(None, description="Error from OAuth provider"),
    session: AsyncSession = Depends(get_db_session),
    state_manager: OAuthStateManager = Depends(get_state_manager),
):
    """Handle YouTube OAuth callback (exchange code for token)."""
    frontend_url = get_settings().oauth.frontend_redirect_url.rstrip("/")

    if error:
        logger.error(f"YouTube OAuth error: {error}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error={error}")

    try:
        # Validate state to get user_id and code_verifier (if PKCE was used)
        metadata = await state_manager.validate_state(state)
        if not metadata:
            raise ValueError("Invalid or expired state token")

        user_id = metadata["user_id"]
        code_verifier = metadata.get("code_verifier")  # For PKCE

        # Exchange code for token
        config = get_platform_config("youtube")
        oauth_service = OAuthService(config, state_manager)
        token_data = await oauth_service.exchange_code_for_token(code, code_verifier=code_verifier)

        # Validate token
        token_valid = await oauth_service.validate_token(token_data["access_token"])
        if not token_valid:
            logger.warning(f"YouTube token validation failed after exchange: user_id={user_id}")

        # Save credentials
        await save_oauth_credentials(user_id, "youtube", token_data, config, session)

        logger.info(f"YouTube OAuth completed successfully: user_id={user_id}")
        return RedirectResponse(url=f"{frontend_url}/settings/platforms?oauth_success=true&platform=youtube")

    except ValueError as e:
        logger.error(f"YouTube OAuth callback error: {e}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error=invalid_state")
    except Exception as e:
        logger.error(f"YouTube OAuth callback failed: {e}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error=token_exchange_failed")


@router.get("/vk/authorize", response_model=OAuthAuthorizeResponse)
async def vk_authorize(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
    state_manager: OAuthStateManager = Depends(get_state_manager),
):
    """Initiate VK OAuth flow."""
    try:
        config = get_platform_config("vk_video")
        oauth_service = OAuthService(config, state_manager)

        ip_address = request.client.host if request.client else None
        result = await oauth_service.get_authorization_url(current_user.id, ip_address)

        logger.info(f"VK OAuth initiated: user_id={current_user.id}")
        return result

    except Exception as e:
        logger.error(f"VK OAuth authorization failed: user_id={current_user.id} error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        )


@router.get("/vk/authorize/implicit", response_model=OAuthImplicitFlowResponse)
async def vk_authorize_implicit(
    current_user: UserInDB = Depends(get_current_user),
) -> OAuthImplicitFlowResponse:
    """
       Generate VK Implicit Flow URL (no refresh token).

       Uses separate VK app configured for Implicit Flow.

       **How to use:**
       1. Redirect user to `redirect_uri` URL
       2. User authorizes and VK redirects to `blank_redirect_uri`
       3. Parse token from URL hash: `#access_token=XXX&expires_in=86400&user_id=YYY`
       4. Extract `access_token`, `expires_in`, and `user_id` from hash

       **Response fields:**
       - `method`: OAuth method type ("implicit_flow")
       - `app_id`: VK application ID
       - `redirect_uri`: Full authorization URL to redirect user to
       - `scope`: Requested permissions (e.g., "video,groups,wall")
       - `response_type`: Response type ("token" for implicit flow)
       - `blank_redirect_uri`: Final redirect URI where token will appear in URL hash

       **Pros:**
       - Works immediately without VK approval
       - Grants video, groups, wall permissions

    й    **Cons:**
       - Token expires in 24 hours
       - No refresh token
       - Deprecated by VK (use for testing only)
    """
    # Load VK config to get implicit_flow_app_id
    import os

    from api.services.oauth_platforms import load_oauth_config

    config_path = os.getenv("VK_OAUTH_CONFIG", "config/oauth_vk.json")
    vk_config = load_oauth_config(config_path)

    implicit_app_id = vk_config.get("implicit_flow_app_id", "54249533")

    scope = "video,groups,wall"
    response_type = "token"
    blank_redirect = "https://oauth.vk.com/blank.html"

    params = {
        "client_id": implicit_app_id,
        "display": "page",
        "redirect_uri": blank_redirect,
        "scope": scope,
        "response_type": response_type,
        "v": "5.131",
    }

    implicit_url = f"https://oauth.vk.com/authorize?{urlencode(params)}"

    logger.info(f"VK Implicit Flow URL generated: user_id={current_user.id} app_id={implicit_app_id}")

    return OAuthImplicitFlowResponse(
        method="implicit_flow",
        app_id=implicit_app_id,
        redirect_uri=implicit_url,
        scope=scope,
        response_type=response_type,
        blank_redirect_uri=blank_redirect,
    )


@router.post("/vk/authorize/implicit", response_model=VKImplicitFlowCallbackResponse)
async def vk_implicit_callback(
    redirect_url: str = Body(..., media_type="text/plain", description="Full VK redirect URL with #access_token=..."),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> VKImplicitFlowCallbackResponse:
    """Parse VK Implicit Flow redirect URL and upsert credentials, matching by VK user_id."""
    from api.schemas.auth import UserCredentialUpdate

    try:
        parsed = urlparse(redirect_url.strip())
        if not parsed.fragment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No URL fragment found. Expected #access_token=...&expires_in=...&user_id=...",
            )

        params = parse_qs(parsed.fragment)
        if not params.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="access_token not found in URL fragment",
            )

        access_token = params["access_token"][0]
        expires_in = int(params["expires_in"][0]) if params.get("expires_in") else 86400
        vk_user_id = int(params["user_id"][0]) if params.get("user_id") else None

        encryption = get_encryption()
        cred_repo = UserCredentialRepository(session)
        expiry = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat().replace("+00:00", "Z")

        # Find existing VK credential by user_id in decrypted data
        existing_cred = None
        if vk_user_id:
            for platform in ("vk", "vk_video"):
                for cred in await cred_repo.list_by_platform(current_user.id, platform):
                    try:
                        data = encryption.decrypt_credentials(cred.encrypted_data)
                        if data.get("user_id") == vk_user_id:
                            existing_cred = cred
                            break
                    except Exception:
                        logger.debug("Failed to decrypt credential %s", cred.id)
                        continue
                if existing_cred:
                    break

        new_creds = {
            "access_token": access_token,
            "user_id": vk_user_id,
            "expires_in": expires_in,
            "expiry": expiry,
        }

        if existing_cred:
            # Merge new token into existing credentials (preserve client_id, client_secret, etc.)
            merged = encryption.decrypt_credentials(existing_cred.encrypted_data)
            merged.update(new_creds)
            encrypted = encryption.encrypt_credentials(merged)
            await cred_repo.update(existing_cred.id, UserCredentialUpdate(encrypted_data=encrypted, is_active=True))
            credential_id = existing_cred.id
            account_name = existing_cred.account_name or "unknown"
            logger.info(f"VK implicit token updated: credential_id={credential_id}")
        else:
            config = get_platform_config("vk_video")
            new_creds.update({"client_id": config.client_id, "client_secret": config.client_secret})
            encrypted = encryption.encrypt_credentials(new_creds)
            account_name = await get_account_identifier("vk_video", access_token)
            created = await cred_repo.create(
                UserCredentialCreate(
                    user_id=current_user.id,
                    platform="vk_video",
                    account_name=account_name,
                    encrypted_data=encrypted,
                )
            )
            credential_id = created.id
            logger.info(f"VK implicit token created: credential_id={credential_id} account={account_name}")

        return VKImplicitFlowCallbackResponse(
            credential_id=credential_id,
            account_name=account_name,
            user_id=vk_user_id,
            expires_in=expires_in,
            message=f"VK credentials saved (expires in {expires_in}s, no refresh token)",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"VK implicit flow save failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save VK implicit flow credentials: {e}",
        )


@router.get("/vk/callback")
async def vk_callback(
    code: str = Query(..., description="Authorization code from VK"),
    state: str = Query(..., description="State token for CSRF protection"),
    device_id: str | None = Query(None, description="Device ID from VK (required for VK ID)"),
    error: str | None = Query(None, description="Error from OAuth provider"),
    session: AsyncSession = Depends(get_db_session),
    state_manager: OAuthStateManager = Depends(get_state_manager),
):
    """Handle VK OAuth callback with VK ID support."""
    frontend_url = get_settings().oauth.frontend_redirect_url.rstrip("/")

    if error:
        logger.error(f"VK OAuth error: {error}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error={error}")

    try:
        # Validate state to get user_id and code_verifier (for PKCE)
        metadata = await state_manager.validate_state(state)
        if not metadata:
            raise ValueError("Invalid or expired state token")

        user_id = metadata["user_id"]
        code_verifier = metadata.get("code_verifier")  # VK ID requires PKCE

        # Exchange code for token (VK ID requires device_id)
        config = get_platform_config("vk_video")
        oauth_service = OAuthService(config, state_manager)
        token_data = await oauth_service.exchange_code_for_token(code, code_verifier=code_verifier, device_id=device_id)

        # Validate token
        token_valid = await oauth_service.validate_token(token_data["access_token"])
        if not token_valid:
            logger.warning(f"VK token validation failed after exchange: user_id={user_id}")

        # Save credentials
        await save_oauth_credentials(user_id, "vk_video", token_data, config, session)

        logger.info(f"VK OAuth completed successfully: user_id={user_id}")
        return RedirectResponse(url=f"{frontend_url}/settings/platforms?oauth_success=true&platform=vk")

    except ValueError as e:
        logger.error(f"VK OAuth callback error: {e}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error=invalid_state")
    except Exception as e:
        logger.error(f"VK OAuth callback failed: {e}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error=token_exchange_failed")


@router.get("/zoom/authorize", response_model=OAuthAuthorizeResponse)
async def zoom_authorize(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
    state_manager: OAuthStateManager = Depends(get_state_manager),
):
    """Initiate Zoom OAuth flow."""
    try:
        config = get_platform_config("zoom")
        oauth_service = OAuthService(config, state_manager)

        ip_address = request.client.host if request.client else None
        result = await oauth_service.get_authorization_url(current_user.id, ip_address)

        logger.info(f"Zoom OAuth initiated: user_id={current_user.id}")
        return result

    except Exception as e:
        logger.error(f"Zoom OAuth authorization failed: user_id={current_user.id} error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        )


@router.get("/zoom/callback")
async def zoom_callback(
    code: str = Query(..., description="Authorization code from Zoom"),
    state: str = Query(..., description="State token for CSRF protection"),
    error: str | None = Query(None, description="Error from OAuth provider"),
    session: AsyncSession = Depends(get_db_session),
    state_manager: OAuthStateManager = Depends(get_state_manager),
):
    """Handle Zoom OAuth callback (exchange code for token)."""
    frontend_url = get_settings().oauth.frontend_redirect_url.rstrip("/")

    if error:
        logger.error(f"Zoom OAuth error: {error}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error={error}")

    try:
        # Validate state to get user_id
        metadata = await state_manager.validate_state(state)
        if not metadata:
            raise ValueError("Invalid or expired state token")

        user_id = metadata["user_id"]

        # Exchange code for token
        config = get_platform_config("zoom")
        oauth_service = OAuthService(config, state_manager)
        token_data = await oauth_service.exchange_code_for_token(code)

        # Validate token
        token_valid = await oauth_service.validate_token(token_data["access_token"])
        if not token_valid:
            logger.warning(f"Zoom token validation failed after exchange: user_id={user_id}")

        # Save credentials
        await save_oauth_credentials(user_id, "zoom", token_data, config, session)

        logger.info(f"Zoom OAuth completed successfully: user_id={user_id}")
        return RedirectResponse(url=f"{frontend_url}/settings/platforms?oauth_success=true&platform=zoom")

    except ValueError as e:
        logger.error(f"Zoom OAuth callback error: {e}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error=invalid_state")
    except Exception as e:
        logger.error(f"Zoom OAuth callback failed: {e}")
        return RedirectResponse(url=f"{frontend_url}/?oauth_error=token_exchange_failed")
