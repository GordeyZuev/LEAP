"""User credentials management endpoints (multi-tenancy)"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.auth.encryption import get_encryption
from api.dependencies import get_db_session
from api.repositories.auth_repos import UserCredentialRepository
from api.schemas.auth import UserCredentialCreate, UserCredentialUpdate, UserInDB
from api.schemas.credentials import (
    CredentialCreateRequest,
    CredentialDeleteResponse,
    CredentialResponse,
    CredentialStatusResponse,
    CredentialUpdateRequest,
    VKCredentialsManual,
    YouTubeCredentialsManual,
    ZoomCredentialsManual,
)
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/v1/credentials", tags=["Credentials"])


@router.get("/", response_model=list[CredentialResponse])
async def list_credentials(
    platform: str | None = None,
    include_data: bool = False,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get user's credentials, optionally filtered by platform."""
    cred_repo = UserCredentialRepository(session)

    credentials = (
        await cred_repo.list_by_platform(current_user.id, platform)
        if platform
        else await cred_repo.find_by_user(current_user.id)
    )

    result = []
    encryption = get_encryption() if include_data else None

    for cred in credentials:
        response = CredentialResponse(
            id=cred.id,
            platform=cred.platform,
            account_name=cred.account_name,
            is_active=cred.is_active,
            last_used_at=cred.last_used_at.isoformat() if cred.last_used_at else None,
        )

        if include_data and encryption:
            try:
                response.credentials = encryption.decrypt_credentials(cred.encrypted_data)
            except Exception as e:
                logger.error(f"Failed to decrypt credentials for id={cred.id}: {e}")

        result.append(response)

    return result


@router.get("/status", response_model=CredentialStatusResponse)
async def check_credentials_status(
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialStatusResponse:
    cred_repo = UserCredentialRepository(session)

    platforms = ["zoom", "youtube", "vk_video", "fireworks", "deepseek", "yandex_disk"]

    status_map = {}
    for platform in platforms:
        credentials = await cred_repo.list_by_platform(current_user.id, platform)
        status_map[platform] = len(credentials) > 0

    available_platforms = [p for p, has_creds in status_map.items() if has_creds]

    return CredentialStatusResponse(
        user_id=current_user.id,
        available_platforms=available_platforms,
        credentials_status=status_map,
    )


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential_by_id(
    credential_id: int,
    include_data: bool = False,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get specific credential by ID with optional decryption."""
    cred_repo = UserCredentialRepository(session)
    credential = await cred_repo.get_by_id(credential_id)

    if not credential or credential.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential {credential_id} not found",
        )

    response = CredentialResponse(
        id=credential.id,
        platform=credential.platform,
        account_name=credential.account_name,
        is_active=credential.is_active,
        last_used_at=credential.last_used_at.isoformat() if credential.last_used_at else None,
    )

    if include_data:
        encryption = get_encryption()
        try:
            decrypted_data = encryption.decrypt_credentials(credential.encrypted_data)
            response.credentials = decrypted_data
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt credentials",
            )

    return response


def _validate_credentials(platform: str, credentials: dict[str, Any]) -> None:
    """Validate credentials structure based on platform."""
    try:
        if platform == "youtube":
            YouTubeCredentialsManual(**credentials)
        elif platform in ("vk", "vk_video"):
            VKCredentialsManual(**credentials)
        elif platform == "zoom":
            ZoomCredentialsManual(**credentials)
        # Other platforms don't have specific validation yet
    except ValidationError as e:
        error_messages = []
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            message = error["msg"]
            error_messages.append(f"{field}: {message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {platform} credentials: {'; '.join(error_messages)}",
        ) from e


def _extract_account_name(platform: str, credentials: dict, explicit_name: str | None) -> str | None:
    """Extract or generate account name from credentials."""
    if explicit_name:
        return explicit_name

    if "account" in credentials:
        return credentials["account"]

    if platform == "vk" and "group_id" in credentials:
        return f"group_{credentials['group_id']}"

    return None


def _check_duplicate_credentials(
    platform: str, credentials: dict, existing_cred_data: dict, cred_id: int, account: str | None
) -> None:
    """Check if credentials are duplicates based on platform-specific key fields."""
    if platform == "zoom":
        if existing_cred_data.get("account_id") == credentials.get("account_id") and existing_cred_data.get(
            "client_id"
        ) == credentials.get("client_id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Credentials with same account_id and client_id already exist "
                    f"(credential_id: {cred_id}, account: {account or 'N/A'})"
                ),
            )
    elif platform == "youtube":
        existing_client_id = existing_cred_data.get("client_secrets", {}).get("installed", {}).get("client_id")
        new_client_id = credentials.get("client_secrets", {}).get("installed", {}).get("client_id")
        if existing_client_id and existing_client_id == new_client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credentials with same client_id already exist (credential_id: {cred_id})",
            )
    elif platform == "vk":
        if existing_cred_data.get("access_token") == credentials.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credentials with same access_token already exist (credential_id: {cred_id})",
            )


@router.post("/", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credentials(
    request: CredentialCreateRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Create new platform credentials with validation and duplicate checking."""
    _validate_credentials(request.platform, request.credentials)

    cred_repo = UserCredentialRepository(session)
    account_name = _extract_account_name(request.platform, request.credentials, request.account_name)

    if account_name:
        existing = await cred_repo.get_by_platform(current_user.id, request.platform, account_name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credentials for platform '{request.platform}' with account '{account_name}' already exist",
            )

    encryption = get_encryption()
    try:
        encrypted_data = encryption.encrypt_credentials(request.credentials)
    except Exception as e:
        logger.error(f"Failed to encrypt credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt credentials",
        )

    all_platform_creds = await cred_repo.list_by_platform(current_user.id, request.platform)
    for existing_cred in all_platform_creds:
        try:
            existing_decrypted = encryption.decrypt_credentials(existing_cred.encrypted_data)
            _check_duplicate_credentials(
                request.platform,
                request.credentials,
                existing_decrypted,
                existing_cred.id,
                existing_cred.account_name,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to decrypt existing credential {existing_cred.id}: {e}")

    cred_create = UserCredentialCreate(
        user_id=current_user.id,
        platform=request.platform,
        account_name=account_name,
        encrypted_data=encrypted_data,
    )
    credential = await cred_repo.create(credential_data=cred_create)

    logger.info(
        f"User credentials created: user_id={current_user.id} | platform={request.platform}"
        f"{' | account=' + account_name if account_name else ''}"
    )

    return CredentialResponse(
        id=credential.id,
        platform=credential.platform,
        account_name=credential.account_name,
        is_active=credential.is_active,
        last_used_at=None,
    )


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def update_credentials(
    credential_id: int,
    request: CredentialUpdateRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Update existing credential data (PATCH - partial update)."""
    cred_repo = UserCredentialRepository(session)

    credential = await cred_repo.get_by_id(credential_id)
    if not credential or credential.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential {credential_id} not found",
        )

    encryption = get_encryption()
    try:
        encrypted_data = encryption.encrypt_credentials(request.credentials)
    except Exception as e:
        logger.error(f"Failed to encrypt credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt credentials",
        )

    cred_update = UserCredentialUpdate(encrypted_data=encrypted_data)
    updated_credential = await cred_repo.update(credential.id, credential_data=cred_update)

    if not updated_credential:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update credential",
        )

    logger.info(f"User credentials updated: user_id={current_user.id} | credential_id={credential_id}")

    return CredentialResponse(
        id=updated_credential.id,
        platform=updated_credential.platform,
        account_name=updated_credential.account_name,
        is_active=updated_credential.is_active,
        last_used_at=(updated_credential.last_used_at.isoformat() if updated_credential.last_used_at else None),
    )


@router.delete("/{credential_id}")
async def delete_credentials(
    credential_id: int,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete platform credentials by ID."""
    cred_repo = UserCredentialRepository(session)

    credential = await cred_repo.get_by_id(credential_id)
    if not credential or credential.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential {credential_id} not found",
        )

    await cred_repo.delete(credential.id)

    logger.info(f"User credentials deleted: user_id={current_user.id} | credential_id={credential_id}")

    return CredentialDeleteResponse(message=f"Credential {credential_id} deleted successfully")
