"""
Менеджер токенов для Zoom API с синхронизацией и механизмом повторных попыток.

Реализует паттерн Singleton для централизованного управления токенами доступа
на уровне аккаунта, предотвращая race conditions при параллельных запросах.
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
    Централизованный менеджер токенов с синхронизацией на уровне аккаунта.

    Использует паттерн Singleton для обеспечения единой точки доступа к токенам
    для каждого аккаунта, предотвращая дублирование запросов при параллельной обработке.
    """

    # Классовые переменные для хранения экземпляров и блокировок
    _instances: dict[str, "TokenManager"] = {}
    _locks: dict[str, asyncio.Lock] = {}
    _class_lock = asyncio.Lock()

    def __init__(self, account: str):
        """
        Инициализация менеджера токенов для конкретного аккаунта.

        Args:
            account: Email аккаунта Zoom
        """
        self.account = account
        self._cached_token: str | None = None
        self._token_expires_at: float | None = None
        self._refresh_buffer = 60  # Обновляем токен за 60 секунд до истечения

    @classmethod
    async def get_instance(cls, account: str) -> "TokenManager":
        """
        Получение или создание экземпляра TokenManager для аккаунта (Singleton).

        Args:
            account: Email аккаунта Zoom

        Returns:
            Экземпляр TokenManager для указанного аккаунта
        """
        async with cls._class_lock:
            if account not in cls._instances:
                cls._instances[account] = cls(account)
                cls._locks[account] = asyncio.Lock()
            return cls._instances[account]

    @classmethod
    def get_lock(cls, account: str) -> asyncio.Lock:
        """
        Получение блокировки для конкретного аккаунта.

        Args:
            account: Email аккаунта Zoom

        Returns:
            Блокировка для синхронизации доступа к токену аккаунта
        """
        if account not in cls._locks:
            cls._locks[account] = asyncio.Lock()
        return cls._locks[account]

    def _is_token_valid(self) -> bool:
        """
        Проверка валидности кэшированного токена.

        Returns:
            True если токен валиден и не истечет в ближайшие refresh_buffer секунд
        """
        if not self._cached_token or not self._token_expires_at:
            return False
        return time.time() < (self._token_expires_at - self._refresh_buffer)

    async def _fetch_token(
        self,
        config: ZoomServerToServerCredentials,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> tuple[str | None, int | None]:
        """
        Fetch token with retry mechanism and exponential backoff.

        Args:
            config: Zoom Server-to-Server credentials
            max_retries: Maximum retry attempts
            base_delay: Base delay in seconds (for first retry)
            max_delay: Maximum delay in seconds

        Returns:
            Tuple (access_token, expires_in) or (None, None) on failure
        """
        credentials = f"{config.client_id}:{config.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Fetching token: account={config.account} | attempt={attempt + 1}/{max_retries}",
                    account=config.account,
                    attempt=attempt + 1,
                    max_retries=max_retries
                )

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
                        expires_in = token_data.get("expires_in", 3600)  # По умолчанию 1 час

                        if access_token:
                            logger.info(
                                f"Token fetched successfully: account={config.account} | expires_in={expires_in}s",
                                account=config.account,
                                expires_in=expires_in
                            )
                            return (access_token, expires_in)
                        logger.error(
                            f"Token not found in API response: account={config.account}",
                            account=config.account
                        )
                        return (None, None)
                    logger.error(
                        f"Error fetching token: account={config.account} | status={response.status_code}",
                        account=config.account,
                        status_code=response.status_code,
                        response_preview=response.text[:200]
                    )

                    # Для ошибок аутентификации (401, 403) не имеет смысла повторять
                    if response.status_code in (401, 403):
                        logger.error(
                            f"Authentication error, retries won't help: account={config.account} | status={response.status_code}",
                            account=config.account,
                            status_code=response.status_code
                        )
                        return (None, None)

                    # Для других ошибок продолжаем попытки
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2**attempt), max_delay)
                        logger.warning(
                            f"Retrying token fetch: account={config.account} | delay={delay:.1f}s | attempt={attempt + 2}",
                            account=config.account,
                            delay_seconds=delay,
                            next_attempt=attempt + 2
                        )
                        await asyncio.sleep(delay)
                    else:
                        return (None, None)

            except (httpx.NetworkError, httpx.TimeoutException, httpx.ConnectError) as e:
                error_type = type(e).__name__
                logger.warning(
                    f"Network error fetching token: account={config.account} | error_type={error_type}",
                    account=config.account,
                    error_type=error_type,
                    error=str(e)
                )

                if attempt < max_retries - 1:
                    delay = min(base_delay * (2**attempt), max_delay)
                    logger.info(
                        f"Retrying token fetch: account={config.account} | delay={delay:.1f}s | attempt={attempt + 2}/{max_retries}",
                        account=config.account,
                        delay_seconds=delay,
                        attempt=attempt + 2,
                        max_retries=max_retries
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All token fetch attempts exhausted: account={config.account} | error={error_type}",
                        account=config.account,
                        error_type=error_type,
                        last_error=str(e)
                    )
                    return (None, None)

            except Exception as e:
                error_type = type(e).__name__
                logger.error(
                    f"Unexpected error fetching token: account={config.account} | error_type={error_type}",
                    account=config.account,
                    error_type=error_type,
                    error=str(e),
                    exc_info=True
                )
                # Для неожиданных ошибок не повторяем
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
        Get access token with caching and synchronization.

        Thread-safe method that prevents duplicate requests during parallel access.

        Args:
            config: Zoom Server-to-Server credentials
            max_retries: Maximum retry attempts on errors
            base_delay: Base delay for exponential backoff
            max_delay: Maximum delay between retries

        Returns:
            Access token or None on failure
        """
        # Проверяем валидность кэшированного токена без блокировки
        if self._is_token_valid():
            logger.debug(f"Using cached token: account={config.account}", account=config.account)
            return self._cached_token

        # Get lock for synchronization access
        lock = self.get_lock(config.account)
        async with lock:
            # Double check: maybe token was fetched by another coroutine
            # while we were waiting for the lock
            if self._is_token_valid():
                logger.debug(
                    f"Using cached token (fetched by another coroutine): account={config.account}",
                    account=config.account
                )
                return self._cached_token

            # Получаем новый токен
            access_token, expires_in = await self._fetch_token(config, max_retries, base_delay, max_delay)

            if access_token:
                # Кэшируем токен
                self._cached_token = access_token
                # Используем время истечения из ответа API или значение по умолчанию
                expires_in = expires_in or 3600  # 1 час по умолчанию
                self._token_expires_at = time.time() + expires_in
                return access_token
            logger.error(f"Failed to fetch token: account={config.account}", account=config.account)
            return None

    def invalidate_token(self) -> None:
        """
        Инвалидация кэшированного токена.

        Полезно при ошибках аутентификации для принудительного обновления токена.
        """
        logger.debug(f"Invalidating token: account={self.account}", account=self.account)
        self._cached_token = None
        self._token_expires_at = None
