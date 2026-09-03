"""Connection checks for stored platform credentials.

Each probe makes the cheapest authenticated call its platform offers. Outcomes are
deliberately three-way: only an explicit rejection means the credential is dead, so a
provider outage or a network blip never marks a working key as needing re-authorization.

Probes may refresh and persist tokens — that is the same work the pipeline does — so a
check both answers "is this alive" and keeps a near-expiry token usable.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from logger import format_details, get_logger

logger = get_logger()

CheckStatus = Literal["ok", "auth_failed", "unavailable", "unsupported"]


@dataclass(frozen=True)
class CredentialCheckResult:
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class ProbeContext:
    """What a probe needs: the decrypted blob, plus the row for token persistence."""

    credential_id: int
    credentials: dict[str, Any]
    session: AsyncSession


def _ok(detail: str) -> CredentialCheckResult:
    return CredentialCheckResult("ok", detail)


def _rejected(detail: str) -> CredentialCheckResult:
    return CredentialCheckResult("auth_failed", detail)


def _unavailable(detail: str) -> CredentialCheckResult:
    return CredentialCheckResult("unavailable", detail)


async def _probe_zoom(ctx: ProbeContext) -> CredentialCheckResult:
    from api.zoom_api import ZoomAPI, ZoomAPIError, ZoomAuthenticationError
    from models.zoom_auth import create_zoom_credentials

    try:
        api = ZoomAPI(create_zoom_credentials(ctx.credentials))
    except (ValueError, KeyError) as e:
        return _rejected(f"Stored Zoom credentials are incomplete: {e}")

    try:
        await api.get_current_user()
    except ZoomAuthenticationError as e:
        return _rejected(str(e))
    except ZoomAPIError as e:
        return _unavailable(str(e))
    return _ok("Zoom accepted the credentials")


async def _probe_yandex_disk(ctx: ProbeContext) -> CredentialCheckResult:
    from api.auth.encryption import get_encryption
    from api.repositories.auth_repos import UserCredentialRepository
    from api.services.yandex_disk_credentials import refresh_yandex_disk_credential_if_needed
    from yandex_disk_module.client import YandexDiskClient, YandexDiskError

    credentials = dict(ctx.credentials)
    try:
        await refresh_yandex_disk_credential_if_needed(
            credentials,
            ctx.credential_id,
            UserCredentialRepository(ctx.session),
            get_encryption(),
        )
    except Exception as e:
        logger.warning(f"Yandex Disk refresh during check failed | {format_details(error=str(e))}")

    token = credentials.get("oauth_token")
    if not token:
        return _rejected("No OAuth token is stored for this connection")

    try:
        await YandexDiskClient(oauth_token=token).get_disk_info()
    except YandexDiskError as e:
        if e.status_code in (401, 403):
            return _rejected(f"Yandex Disk rejected the token ({e.status_code})")
        return _unavailable(str(e))
    return _ok("Yandex Disk accepted the token")


async def _probe_mts_link(ctx: ProbeContext) -> CredentialCheckResult:
    from api.mts_link_api import MtsLinkAPIError, MtsLinkAuthenticationError
    from models.mts_link_auth import create_mts_link_client, create_mts_link_credentials

    try:
        api = create_mts_link_client(create_mts_link_credentials(ctx.credentials))
    except ValueError as e:
        return _rejected(f"Stored MTS Link credentials are incomplete: {e}")

    try:
        await api.list_organization_members(per_page=10)
    except MtsLinkAuthenticationError as e:
        return _rejected(str(e))
    except MtsLinkAPIError as e:
        return _unavailable(str(e))
    return _ok("MTS Link accepted the API key")


async def _probe_youtube(ctx: ProbeContext) -> CredentialCheckResult:
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request

    from api.auth.encryption import get_encryption
    from api.repositories.auth_repos import UserCredentialRepository
    from api.services.oauth_platforms import get_platform_config
    from video_upload_module.credentials_provider import DatabaseCredentialProvider

    provider = DatabaseCredentialProvider(
        ctx.credential_id,
        get_encryption(),
        UserCredentialRepository(ctx.session),
    )
    google_credentials = await provider.get_google_credentials(list(get_platform_config("youtube").scopes))
    if google_credentials is None:
        return _rejected("Stored YouTube credentials could not be read")
    if google_credentials.valid:
        return _ok("YouTube access token is valid")
    if not google_credentials.refresh_token:
        return _rejected("Access token expired and no refresh token is stored")

    # google-auth is synchronous; keep the event loop free while it talks to Google.
    try:
        await asyncio.to_thread(google_credentials.refresh, Request())
    except RefreshError as e:
        return _rejected(f"Google refused to refresh the token: {e}")

    await provider.update_google_credentials(google_credentials)
    return _ok("YouTube token refreshed")


_PROBES: dict[str, Any] = {
    "zoom": _probe_zoom,
    "yandex_disk": _probe_yandex_disk,
    "mts_link": _probe_mts_link,
    "youtube": _probe_youtube,
}


async def check_credential(ctx: ProbeContext, platform: str) -> CredentialCheckResult:
    """Run the platform's connection check, never raising.

    Platforms without a probe report ``unsupported`` rather than a hopeful "ok".
    """
    probe = _PROBES.get(platform)
    if probe is None:
        return CredentialCheckResult("unsupported", f"Connection check is not available for {platform} yet")

    try:
        return await probe(ctx)
    except Exception as e:
        logger.warning(
            f"Credential check failed | {format_details(credential=ctx.credential_id, error=f'{type(e).__name__}: {e}')}"
        )
        return _unavailable(f"Check could not be completed: {type(e).__name__}")
