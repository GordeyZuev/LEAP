"""Token error handler with automatic refresh for YouTube and VK."""

import asyncio
import functools
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request

from logger import get_logger

logger = get_logger()

T = TypeVar("T")
GOOGLE_AUTH_REFRESH_TIMEOUT_SECONDS = 10
GOOGLE_BLOCKING_WORK_TIMEOUT_SECONDS = 12
GOOGLE_API_HTTP_TIMEOUT_SECONDS = 15


async def refresh_youtube_credentials(credentials: Any) -> None:
    """Refresh OAuth credentials off the event loop with a finite HTTP timeout."""
    request = Request()

    def bounded_request(url: str, **kwargs: Any) -> Any:
        kwargs["timeout"] = GOOGLE_AUTH_REFRESH_TIMEOUT_SECONDS
        return request(url, **kwargs)

    try:
        await asyncio.wait_for(
            asyncio.to_thread(credentials.refresh, bounded_request),
            timeout=GOOGLE_BLOCKING_WORK_TIMEOUT_SECONDS,
        )
    except (TimeoutError, TransportError) as exc:
        raise TimeoutError("YouTube OAuth token refresh timed out") from exc


async def build_youtube_service(credentials: Any) -> Any:
    """Build the bundled YouTube API client off the event loop and bound API calls."""
    from googleapiclient.discovery import build

    service = await asyncio.wait_for(
        asyncio.to_thread(build, "youtube", "v3", credentials=credentials, static_discovery=True),
        timeout=GOOGLE_BLOCKING_WORK_TIMEOUT_SECONDS,
    )
    transport = getattr(getattr(service, "_http", None), "http", None)
    if transport is not None and hasattr(transport, "timeout"):
        transport.timeout = GOOGLE_API_HTTP_TIMEOUT_SECONDS
    return service


class TokenRefreshError(Exception):
    """Raised when token refresh fails."""

    def __init__(self, platform: str, message: str, original_error: Exception | None = None):
        super().__init__(f"[{platform}] {message}")
        self.platform = platform
        self.original_error = original_error


def is_youtube_auth_error(error: Exception) -> bool:
    """Check whether a YouTube response may succeed after refreshing its access token."""
    try:
        from googleapiclient.errors import HttpError

        if isinstance(error, HttpError) and error.resp:
            if error.resp.status == 401:
                return True
            if error.resp.status == 403:
                body = json.loads(error.content.decode("utf-8", errors="replace"))
                reasons = {str(row.get("reason", "")) for row in body.get("error", {}).get("errors", [])}
                return bool(reasons & {"authError", "invalidCredentials"})
    except ImportError:
        pass
    except (AttributeError, json.JSONDecodeError, TypeError):
        return False
    return False


def is_vk_auth_error(response_data: dict) -> bool:
    """Check if VK response contains auth error (codes 5, 28)."""
    if not isinstance(response_data, dict):
        return False

    error_info = response_data.get("error")
    if error_info and isinstance(error_info, dict):
        error_code = error_info.get("error_code")
        return error_code in (5, 28)

    return False


def requires_valid_token(max_retries: int = 1):
    """Decorator that catches YouTube auth errors and refreshes token."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> T:
            from googleapiclient.errors import HttpError

            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(self, *args, **kwargs)

                except HttpError as e:
                    last_error = e

                    if not is_youtube_auth_error(e):
                        raise

                    if attempt >= max_retries:
                        logger.error(f"YouTube auth failed after {max_retries} retries")
                        raise TokenRefreshError(
                            "youtube",
                            f"Token refresh failed after {max_retries} attempts",
                            original_error=e,
                        ) from e

                    logger.warning(f"YouTube {e.resp.status} error, refreshing token (attempt {attempt + 1})")

                    try:
                        if not hasattr(self, "credentials") or not self.credentials:
                            raise TokenRefreshError("youtube", "No credentials", original_error=e) from e

                        if not self.credentials.refresh_token:
                            raise TokenRefreshError("youtube", "No refresh_token", original_error=e) from e

                        await refresh_youtube_credentials(self.credentials)

                        if hasattr(self, "credential_provider") and self.credential_provider:
                            await self.credential_provider.update_google_credentials(self.credentials)

                        if hasattr(self, "service") and self.service:
                            self.service = await build_youtube_service(self.credentials)

                        logger.info("YouTube token refreshed")
                        continue

                    except TimeoutError:
                        raise
                    except (RefreshError, TransportError) as refresh_err:
                        raise TokenRefreshError(
                            "youtube", "Refresh failed", original_error=refresh_err
                        ) from refresh_err

            if last_error:
                raise last_error
            raise RuntimeError("Unexpected state in decorator")

        return wrapper

    return decorator


def requires_valid_vk_token(max_retries: int = 1):
    """Decorator that catches VK auth errors and refreshes token."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> T:
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    result = await func(self, *args, **kwargs)

                    # VK may return result with error inside
                    if isinstance(result, dict) and is_vk_auth_error(result):
                        if attempt >= max_retries:
                            error_info = cast("dict[str, Any]", result).get("error")
                            error_msg = (
                                error_info.get("error_msg", "Unknown") if isinstance(error_info, dict) else "Unknown"
                            )
                            logger.error(f"VK auth failed after {max_retries} retries: {error_msg}")
                            raise TokenRefreshError("vk", f"Token invalid: {error_msg}")

                        logger.warning(f"VK token error, refreshing (attempt {attempt + 1})")

                        if not hasattr(self, "credential_provider") or not self.credential_provider:
                            raise TokenRefreshError("vk", "No credential_provider")

                        if hasattr(self.credential_provider, "refresh_vk_token"):
                            refreshed = await self.credential_provider.refresh_vk_token()
                            if refreshed and "access_token" in refreshed:
                                self.config.access_token = refreshed["access_token"]
                                logger.info("VK token refreshed")
                                continue
                            raise TokenRefreshError("vk", "Failed to refresh VK token")

                        raise TokenRefreshError("vk", "Credential provider doesn't support VK refresh")

                    return result

                except Exception as e:
                    last_error = e
                    if attempt >= max_retries:
                        raise
                    raise

            if last_error:
                raise last_error
            raise RuntimeError("Unexpected state in decorator")

        return wrapper

    return decorator
