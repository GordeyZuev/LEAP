"""
Centralized token manager for Zoom API with synchronization and retry mechanism.

Implements Singleton pattern to prevent race conditions during parallel requests.
"""

import asyncio
import base64
import time

import httpx

from logger import get_logger
from models.zoom_auth import ZoomServerToServerCredentials

logger = get_logger()


class TokenManager:
    """
    Per-account token manager with thread-safe caching and automatic refresh.

    Prevents duplicate token requests through synchronized access control.
    """

    _instances: dict[str, "TokenManager"] = {}
    _locks: dict[str, asyncio.Lock] = {}
    _class_lock = asyncio.Lock()
    _REFRESH_BUFFER = 60

    def __init__(self, account: str):
        self.account = account
        self._cached_token: str | None = None
        self._token_expires_at: float | None = None

    @classmethod
    async def get_instance(cls, account: str) -> "TokenManager":
        """Get or create TokenManager instance for account (Singleton pattern)."""
        async with cls._class_lock:
            if account not in cls._instances:
                cls._instances[account] = cls(account)
                cls._locks[account] = asyncio.Lock()
            return cls._instances[account]

    @classmethod
    def get_lock(cls, account: str) -> asyncio.Lock:
        """Get synchronization lock for account."""
        if account not in cls._locks:
            cls._locks[account] = asyncio.Lock()
        return cls._locks[account]

    def _is_token_valid(self) -> bool:
        """Check if cached token is still valid with safety buffer."""
        if not self._cached_token or not self._token_expires_at:
            return False
        return time.time() < (self._token_expires_at - self._REFRESH_BUFFER)

    async def _fetch_token(
        self,
        config: ZoomServerToServerCredentials,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> tuple[str | None, int | None]:
        """Fetch token with exponential backoff retry mechanism."""
        credentials = f"{config.client_id}:{config.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://zoom.us/oauth/token",
                        headers={"Authorization": f"Basic {encoded_credentials}"},
                        params={
                            "grant_type": "account_credentials",
                            "account_id": config.account_id,
                        },
                    )

                    if response.status_code == 200:
                        token_data = response.json()
                        access_token = token_data.get("access_token")
                        expires_in = token_data.get("expires_in", 3600)

                        if access_token:
                            return (access_token, expires_in)

                        logger.error("Token missing in response", account=config.account)
                        return (None, None)

                    if response.status_code in (401, 403):
                        logger.error(
                            "Auth failed, invalid credentials",
                            account=config.account,
                            status=response.status_code,
                        )
                        return (None, None)

                    logger.warning(
                        "Token fetch failed",
                        account=config.account,
                        status=response.status_code,
                        attempt=attempt + 1,
                    )

                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2**attempt), max_delay)
                        await asyncio.sleep(delay)
                    else:
                        return (None, None)

            except (httpx.NetworkError, httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(
                    "Network error during token fetch",
                    account=config.account,
                    error=type(e).__name__,
                    attempt=attempt + 1,
                )

                if attempt < max_retries - 1:
                    delay = min(base_delay * (2**attempt), max_delay)
                    await asyncio.sleep(delay)
                else:
                    logger.error("Token fetch exhausted retries", account=config.account)
                    return (None, None)

            except Exception as e:
                logger.error(
                    "Unexpected token fetch error",
                    account=config.account,
                    error=type(e).__name__,
                    exc_info=True,
                )
                return (None, None)

        return (None, None)

    async def get_token(
        self,
        config: ZoomServerToServerCredentials,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> str | None:
        """
        Get cached or fresh access token with thread-safe synchronization.

        Uses double-checked locking to prevent duplicate requests.
        """
        if self._is_token_valid():
            return self._cached_token

        lock = self.get_lock(config.account)
        async with lock:
            if self._is_token_valid():
                return self._cached_token

            access_token, expires_in = await self._fetch_token(
                config, max_retries, base_delay, max_delay
            )

            if access_token:
                self._cached_token = access_token
                self._token_expires_at = time.time() + (expires_in or 3600)
                return access_token

            logger.error("Token fetch failed", account=config.account)
            return None

    def invalidate_token(self) -> None:
        """Force token refresh on next request."""
        self._cached_token = None
        self._token_expires_at = None
