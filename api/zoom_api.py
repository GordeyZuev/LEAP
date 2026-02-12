import json
from typing import Any
from urllib.parse import quote

import httpx

from logger import get_logger
from models.zoom_auth import ZoomOAuthCredentials, ZoomServerToServerCredentials

from .token_manager import TokenManager

logger = get_logger()


class ZoomAPIError(Exception):
    """Базовая ошибка Zoom API."""


class ZoomAuthenticationError(ZoomAPIError):
    """Ошибка аутентификации."""


class ZoomRequestError(ZoomAPIError):
    """Ошибка выполнения запроса."""


class ZoomResponseError(ZoomAPIError):
    """Ошибка ответа API."""


class ZoomRecordingProcessingError(ZoomAPIError):
    """Запись ещё обрабатывается на стороне Zoom (код 3301)."""


def _encode_meeting_uuid(meeting_id: str) -> str:
    """
    Encode meeting UUID for use in Zoom API URL path.

    Per Zoom API docs: if the meeting UUID begins with '/' or contains '//',
    it must be double-encoded before making an API request.
    """
    if meeting_id.startswith("/") or "//" in meeting_id:
        return quote(quote(meeting_id, safe=""), safe="")
    return quote(meeting_id, safe="")


class ZoomAPI:
    """
    Zoom API client.

    Uses TokenManager for centralized token management
    with synchronization and retry mechanism.
    """

    def __init__(self, config: ZoomServerToServerCredentials | ZoomOAuthCredentials):
        """Initialize API client with credentials."""
        self.config = config

    async def get_access_token(self) -> str | None:
        """
        Get access token with caching and synchronization.

        Supports two modes:
        1. OAuth 2.0 - uses access_token directly
        2. Server-to-Server - gets token via TokenManager

        Returns:
            Access token or None on failure
        """
        if isinstance(self.config, ZoomOAuthCredentials):
            # OAuth 2.0 - return access token directly
            return self.config.access_token

        # Server-to-Server - use TokenManager
        token_manager = await TokenManager.get_instance(self.config.account)
        return await token_manager.get_token(self.config)

    async def get_recordings(
        self,
        page_size: int = 30,
        from_date: str = "2025-01-01",
        to_date: str | None = None,
        meeting_id: str | None = None,
        user_id: str = "me",
    ) -> dict[str, Any]:
        """Fetch recordings list. user_id can be 'me', email, or Zoom user ID."""
        access_token = await self.get_access_token()
        if not access_token:
            raise ZoomAuthenticationError("Не удалось получить access token")

        params = {"page_size": str(page_size), "from": from_date, "trash": "false"}

        if to_date:
            params["to"] = to_date

        if meeting_id:
            params["meeting_id"] = meeting_id

        try:
            logger.info(
                f"Fetching recordings: user={user_id} | from={from_date} | to={to_date}",
                user_id=user_id,
                from_date=from_date,
                to_date=to_date,
            )
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.zoom.us/v2/users/{user_id}/recordings",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"Fetched recordings: count={len(data.get('meetings', []))}",
                        count=len(data.get("meetings", [])),
                    )
                    # Логируем сырые данные от Zoom API
                    import json

                    logger.debug(
                        f"Сырые данные от Zoom API (get_recordings):\n{json.dumps(data, indent=2, ensure_ascii=False)}"
                    )
                    return data
                account = self.config.account if isinstance(self.config, ZoomServerToServerCredentials) else "oauth"
                logger.error(
                    f"API error: account={account} | status={response.status_code}",
                    account=account,
                    status_code=response.status_code,
                    response_preview=response.text[:200],
                )
                raise ZoomResponseError(f"Ошибка API: {response.status_code} - {response.text}")

        except httpx.RequestError as e:
            error_type = type(e).__name__
            account = self.config.account if isinstance(self.config, ZoomServerToServerCredentials) else "oauth"
            logger.error(
                f"Network error: account={account} | error_type={error_type}",
                account=account,
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise ZoomRequestError(f"Ошибка сетевого запроса: {e}") from e
        except ZoomAPIError:
            raise
        except Exception as e:
            error_type = type(e).__name__
            account = self.config.account if isinstance(self.config, ZoomServerToServerCredentials) else "oauth"
            logger.error(
                f"Unexpected error: account={account} | error_type={error_type}",
                account=account,
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise ZoomAPIError(f"Неожиданная ошибка: {e}") from e

    async def get_recording_details(self, meeting_id: str, include_download_token: bool = True) -> dict[str, Any]:
        """Получение детальной информации о конкретной записи."""
        access_token = await self.get_access_token()
        if not access_token:
            raise ZoomAuthenticationError("Не удалось получить access token")

        try:
            params = {}
            if include_download_token:
                # ttl in seconds: 86400 = 24 hours (max is 604800 = 7 days)
                params = {"include_fields": "download_access_token", "ttl": "604800"}

            encoded_id = _encode_meeting_uuid(meeting_id)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.zoom.us/v2/meetings/{encoded_id}/recordings",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )

                if response.status_code == 200:
                    data = response.json()
                    # Логируем сырые данные от Zoom API
                    logger.debug(
                        f"Сырые данные от Zoom API (get_recording_details для meeting_id={meeting_id}):\n{json.dumps(data, indent=2, ensure_ascii=False)}"
                    )
                    return data

                # Handle error response
                account = self.config.account if isinstance(self.config, ZoomServerToServerCredentials) else "oauth"

                # Try to parse error details from response
                error_code = None
                error_message = None
                try:
                    error_data = response.json()
                    error_code = error_data.get("code")
                    error_message = error_data.get("message", response.text)
                except Exception:
                    error_message = response.text

                # Special handling for code 3301 - recording still processing on Zoom side
                if error_code == 3301:
                    logger.info(
                        f"Recording still processing on Zoom side: account={account} | meeting_id={meeting_id} | message={error_message}",
                        account=account,
                        meeting_id=meeting_id,
                        zoom_code=error_code,
                    )
                    raise ZoomRecordingProcessingError(f"Запись ещё обрабатывается: {error_message}")

                # Log other errors as ERROR
                logger.error(
                    f"API error getting recording: account={account} | meeting_id={meeting_id} | status={response.status_code} | zoom_code={error_code}",
                    account=account,
                    meeting_id=meeting_id,
                    status_code=response.status_code,
                    zoom_code=error_code,
                    response_preview=error_message[:200] if error_message else response.text[:200],
                )
                raise ZoomResponseError(f"Ошибка API: {response.status_code} - {error_message}")

        except httpx.RequestError as e:
            error_type = type(e).__name__
            account = self.config.account if isinstance(self.config, ZoomServerToServerCredentials) else "oauth"
            logger.error(
                f"Network error getting recording: account={account} | meeting_id={meeting_id} | error_type={error_type}",
                account=account,
                meeting_id=meeting_id,
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise ZoomRequestError(f"Ошибка сетевого запроса: {e}") from e
        except ZoomAPIError:
            raise
        except Exception as e:
            error_type = type(e).__name__
            account = self.config.account if isinstance(self.config, ZoomServerToServerCredentials) else "oauth"
            logger.error(
                f"Unexpected error getting recording: account={account} | meeting_id={meeting_id} | error_type={error_type}",
                account=account,
                meeting_id=meeting_id,
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise ZoomAPIError(f"Неожиданная ошибка: {e}") from e
