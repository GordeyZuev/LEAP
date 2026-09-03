"""User credentials management endpoints (multi-tenancy)"""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.auth.encryption import get_encryption
from api.dependencies import get_db_session
from api.repositories.auth_repos import UserCredentialRepository
from api.schemas.auth import UserCredentialCreate, UserCredentialUpdate, UserInDB
from api.schemas.common.pagination import filter_by_search, paginate_list
from api.schemas.credentials import (
    CredentialCheckResponse,
    CredentialCreateRequest,
    CredentialListResponse,
    CredentialResponse,
    CredentialStatusResponse,
    CredentialUpdateRequest,
    MtsLinkCredentialsManual,
    VKCredentialsManual,
    YandexDiskBrowseItem,
    YandexDiskBrowseResponse,
    YandexDiskCredentialsManual,
    YouTubeCredentialsManual,
    ZoomCredentialsManual,
)
from api.services.quota_service import QuotaService
from api.services.yandex_disk_credentials import get_yandex_disk_client_for_credential
from logger import format_details, get_logger
from yandex_disk_module.client import YandexDiskError
from yandex_disk_module.paths import normalize_disk_path

logger = get_logger()

router = APIRouter(prefix="/api/v1/credentials", tags=["Credentials"])

CREDENTIAL_SORT_FIELDS = {"created_at", "platform", "account_name", "last_used_at", "status"}
CREDENTIAL_SEARCH_FIELDS = ("account_name", "platform")


def _credential_status_key(credential: Any) -> tuple[int, str]:
    """Sort key for the status column: ascending puts what needs attention first.

    Status is derived from two columns, so it cannot be sorted as a plain attribute.
    """
    if credential.needs_reauth:
        rank = 0
    elif not credential.is_active:
        rank = 1
    else:
        rank = 2
    return rank, str(credential.account_name or credential.platform or "").lower()


CREDENTIAL_SORT_KEYS = {"status": _credential_status_key}

YANDEX_DISK_BROWSE_LIST_FIELDS = (
    "_embedded.items.name,_embedded.items.path,_embedded.items.type,_embedded.items.size,_embedded.items.mime_type"
)


@router.get("", response_model=CredentialListResponse)
async def list_credentials(
    platform: list[str] = Query(
        default=[],
        description="Filter by platform; repeat the param to pass several (?platform=youtube&platform=vk)",
    ),
    search: str | None = Query(None, description="Search substring in account name or platform (case-insensitive)"),
    is_active: bool | None = Query(None, description="Filter by active flag (true/false/omitted=all)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get paginated list of user's credentials."""
    cred_repo = UserCredentialRepository(session)

    credentials = await cred_repo.find_by_user(current_user.id)

    if platform:
        wanted = {p.lower() for p in platform}
        credentials = [c for c in credentials if str(c.platform).lower() in wanted]
    if is_active is not None:
        credentials = [c for c in credentials if bool(c.is_active) is is_active]
    credentials = filter_by_search(credentials, search, CREDENTIAL_SEARCH_FIELDS)

    items, total, total_pages = paginate_list(
        credentials,
        page,
        per_page,
        sort_by,
        sort_order,
        CREDENTIAL_SORT_FIELDS,
        sort_keys=CREDENTIAL_SORT_KEYS,
    )

    return CredentialListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.get("/status", response_model=CredentialStatusResponse)
async def check_credentials_status(
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialStatusResponse:
    cred_repo = UserCredentialRepository(session)

    platforms = ["zoom", "youtube", "vk_video", "assemblyai", "deepseek", "yandex_disk", "mts_link"]

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
        last_used_at=credential.last_used_at,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
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


def _map_yandex_disk_browse_error(exc: YandexDiskError) -> HTTPException:
    """Map Yandex Disk API errors to HTTP responses for browse."""
    code = exc.status_code
    if code == 401:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yandex Disk token invalid or expired — re-authenticate",
        )
    if code == 403:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this folder")
    if code == 404 or exc.error_code == "DiskPathDoesntExistsError":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    if code in (503, 504):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Yandex Disk temporarily unavailable")
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Yandex Disk API error: {exc.error_code or exc}",
    )


def _sort_browse_items(items: list[YandexDiskBrowseItem]) -> list[YandexDiskBrowseItem]:
    dirs = sorted((i for i in items if i.type == "dir"), key=lambda x: x.name.lower())
    files = sorted((i for i in items if i.type == "file"), key=lambda x: x.name.lower())
    return dirs + files


@router.get("/{credential_id}/yandex-disk/browse", response_model=YandexDiskBrowseResponse)
async def browse_yandex_disk(
    credential_id: int,
    path: str = Query("/", description="Folder path to list"),
    limit: int = Query(100, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List folders and files on Yandex Disk for UI folder picker."""
    folder_path = normalize_disk_path(path)
    client = await get_yandex_disk_client_for_credential(
        credential_id,
        current_user.id,
        session,
        refresh_if_expiring=True,
    )

    try:
        data = await client.list_folder(
            folder_path,
            limit=limit,
            offset=offset,
            fields=YANDEX_DISK_BROWSE_LIST_FIELDS,
        )
    except YandexDiskError as e:
        logger.warning(
            f"Yandex Disk browse failed | credential_id={credential_id} path={folder_path} error={e.error_code}"
        )
        raise _map_yandex_disk_browse_error(e) from e

    embedded = data.get("_embedded") or {}
    raw_items = embedded.get("items") or []
    total = int(embedded.get("total") or 0)

    items: list[YandexDiskBrowseItem] = []
    for item in raw_items:
        item_type = item.get("type")
        if item_type not in ("dir", "file"):
            continue
        name = item.get("name") or ""
        raw_path = item.get("path") or name
        items.append(
            YandexDiskBrowseItem(
                name=name,
                path=normalize_disk_path(str(raw_path)),
                type=item_type,
                size=item.get("size"),
                mime_type=item.get("mime_type"),
            )
        )

    return YandexDiskBrowseResponse(
        path=folder_path,
        items=_sort_browse_items(items),
        total=total,
        offset=offset,
        limit=limit,
    )


def _validate_credentials(platform: str, credentials: dict[str, Any]) -> None:
    """Validate credentials structure based on platform."""
    try:
        if platform == "youtube":
            YouTubeCredentialsManual(**credentials)
        elif platform in ("vk", "vk_video"):
            VKCredentialsManual(**credentials)
        elif platform == "zoom":
            ZoomCredentialsManual(**credentials)
        elif platform == "yandex_disk":
            YandexDiskCredentialsManual(**credentials)
        elif platform == "mts_link":
            validated = MtsLinkCredentialsManual(**credentials)
            # Normalize stored shape for create_mts_link_credentials()
            credentials.clear()
            credentials.update(
                {
                    "auth_type": "api_key",
                    "api_token": validated.api_token,
                }
            )
            if validated.account:
                credentials["account"] = validated.account
            if validated.base_url:
                credentials["base_url"] = validated.base_url.rstrip("/")
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
    elif platform == "mts_link":
        if existing_cred_data.get("api_token") == credentials.get("api_token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credentials with same api_token already exist (credential_id: {cred_id})",
            )


@router.post("/{credential_id}/check", response_model=CredentialCheckResponse)
async def check_credential_connection(
    credential_id: int,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialCheckResponse:
    """Verify stored credentials against the platform and update the re-auth flag.

    Only an explicit rejection sets ``needs_reauth``: a network or provider failure
    reports ``unavailable`` and leaves the flag alone, so a blip never sends the user
    off to reissue a working key. A successful check clears the flag.
    """
    from api.services.credential_probes import ProbeContext, check_credential

    cred_repo = UserCredentialRepository(session)
    credential = await cred_repo.get_by_id(credential_id)

    if not credential or credential.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential {credential_id} not found",
        )

    try:
        decrypted = get_encryption().decrypt_credentials(credential.encrypted_data)
    except Exception as e:
        logger.error(f"Failed to decrypt credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt credentials",
        )

    result = await check_credential(
        ProbeContext(credential_id=credential_id, credentials=decrypted, session=session),
        credential.platform,
    )

    needs_reauth = credential.needs_reauth
    if result.status == "ok":
        needs_reauth = False
        await cred_repo.set_needs_reauth(credential_id, False)
        await cred_repo.update_last_used(credential_id)
    elif result.status == "auth_failed":
        needs_reauth = True
        await cred_repo.set_needs_reauth(credential_id, True)

    logger.info(
        f"Credential check | {format_details(credential=credential_id, platform=credential.platform, result=result.status)}"
    )

    return CredentialCheckResponse(
        status=result.status,
        detail=result.detail,
        needs_reauth=needs_reauth,
        checked_at=datetime.now(UTC),
    )


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credentials(
    request: CredentialCreateRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Create new platform credentials with validation and duplicate checking."""
    allowed, error = await QuotaService(session).check_credentials_quota(current_user.id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)

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
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def update_credentials(
    credential_id: int,
    request: CredentialUpdateRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Update existing credential data (PATCH - partial update). Supports updating credentials and/or account_name."""
    cred_repo = UserCredentialRepository(session)

    credential = await cred_repo.get_by_id(credential_id)
    if not credential or credential.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential {credential_id} not found",
        )

    if request.credentials is None and request.account_name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of 'credentials' or 'account_name' must be provided",
        )

    cred_update = UserCredentialUpdate()

    if request.credentials is not None:
        encryption = get_encryption()
        try:
            cred_update.encrypted_data = encryption.encrypt_credentials(request.credentials)
        except Exception as e:
            logger.error(f"Failed to encrypt credentials: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to encrypt credentials",
            )

    if request.account_name is not None:
        cred_update.account_name = request.account_name or None

    try:
        updated_credential = await cred_repo.update(credential.id, credential_data=cred_update)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A connection with this name already exists for this platform",
        )

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
        last_used_at=updated_credential.last_used_at,
        created_at=updated_credential.created_at,
        updated_at=updated_credential.updated_at,
    )


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credentials(
    credential_id: int,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
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
