"""Shared Yandex Disk credential decrypt, OAuth refresh, and client factory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from api.services.oauth_service import refresh_yandex_disk_oauth_token
from logger import get_logger
from yandex_disk_module.client import YandexDiskClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger()

REFRESH_MARGIN_SECONDS = 300


def token_expires_within(expiry: str | None, *, margin: int = REFRESH_MARGIN_SECONDS) -> bool:
    """Return True when the token expires within ``margin`` seconds."""
    if not expiry:
        return False
    try:
        normalized = expiry.replace("Z", "+00:00") if expiry.endswith("Z") else expiry
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return datetime.now(UTC) >= dt - timedelta(seconds=margin)
    except ValueError:
        return False


async def apply_yandex_disk_token_refresh(credentials: dict[str, Any]) -> bool:
    """Refresh OAuth token in ``credentials`` when near expiry. Returns True if refreshed."""
    rt = credentials.get("refresh_token")
    cid = credentials.get("client_id")
    if not rt or not cid:
        return False
    if not token_expires_within(credentials.get("expiry")):
        return False

    try:
        token_data = await refresh_yandex_disk_oauth_token(
            rt,
            override_client_id=cid,
            override_client_secret=credentials.get("client_secret"),
        )
    except Exception as e:
        logger.warning(f"Yandex Disk token refresh failed: {e}")
        return False

    credentials["oauth_token"] = token_data["access_token"]
    if token_data.get("refresh_token"):
        credentials["refresh_token"] = token_data["refresh_token"]
    expires_in = int(token_data.get("expires_in", 3600))
    credentials["expires_in"] = expires_in
    credentials["expiry"] = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat().replace("+00:00", "Z")
    return True


async def persist_refreshed_yandex_disk_credentials(
    credentials: dict[str, Any],
    credential_id: int,
    cred_repo: Any,
    encryption: Any,
) -> None:
    """Encrypt and save refreshed Yandex Disk credentials."""
    from api.schemas.auth import UserCredentialUpdate

    enc = encryption.encrypt_credentials(credentials)
    await cred_repo.update(credential_id, UserCredentialUpdate(encrypted_data=enc))


async def refresh_yandex_disk_credential_if_needed(
    credentials: dict[str, Any],
    credential_id: int,
    cred_repo: Any,
    encryption: Any,
) -> None:
    """Refresh near-expiry token, mutate ``credentials``, and persist when refreshed."""
    if await apply_yandex_disk_token_refresh(credentials):
        await persist_refreshed_yandex_disk_credentials(credentials, credential_id, cred_repo, encryption)


async def get_yandex_disk_client_for_credential(
    credential_id: int,
    user_id: str,
    session: AsyncSession,
    *,
    refresh_if_expiring: bool = True,
) -> YandexDiskClient:
    """Build an authenticated client after ownership and platform checks."""
    from api.auth.encryption import get_encryption
    from api.repositories.auth_repos import UserCredentialRepository
    from api.services.resource_access_validator import ResourceAccessValidator

    validator = ResourceAccessValidator(session)
    await validator.validate_credential_access(credential_id, user_id)

    cred_repo = UserCredentialRepository(session)
    credential = await cred_repo.get_by_id(credential_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential {credential_id} not found",
        )

    if credential.platform != "yandex_disk":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential is not yandex_disk",
        )

    if not credential.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential is inactive",
        )

    encryption = get_encryption()
    try:
        credentials = encryption.decrypt_credentials(credential.encrypted_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e

    oauth_token = credentials.get("oauth_token")
    if not oauth_token or not isinstance(oauth_token, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Yandex Disk credential has no oauth_token",
        )

    if refresh_if_expiring:
        await refresh_yandex_disk_credential_if_needed(credentials, credential_id, cred_repo, encryption)
        oauth_token = credentials.get("oauth_token", oauth_token)

    return YandexDiskClient(oauth_token=str(oauth_token))
