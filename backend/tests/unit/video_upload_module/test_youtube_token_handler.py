"""YouTube OAuth and API transports stay off the event loop and have finite timeouts."""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from video_upload_module.platforms.youtube import token_handler


@pytest.mark.asyncio
async def test_refresh_runs_in_worker_thread_with_bounded_http_timeout(monkeypatch) -> None:
    caller_thread = threading.get_ident()
    request = MagicMock(return_value="response")
    monkeypatch.setattr(token_handler, "Request", lambda: request)

    class Credentials:
        def refresh(self, transport) -> None:
            assert threading.get_ident() != caller_thread
            transport("https://oauth.example/token", method="POST")

    await token_handler.refresh_youtube_credentials(Credentials())

    request.assert_called_once_with(
        "https://oauth.example/token",
        method="POST",
        timeout=token_handler.GOOGLE_AUTH_REFRESH_TIMEOUT_SECONDS,
    )


@pytest.mark.asyncio
async def test_service_uses_static_discovery_and_finite_api_timeout(monkeypatch) -> None:
    transport = SimpleNamespace(timeout=60)
    service = SimpleNamespace(_http=SimpleNamespace(http=transport))
    build = MagicMock(return_value=service)
    monkeypatch.setattr("googleapiclient.discovery.build", build)
    credentials = object()

    result = await token_handler.build_youtube_service(credentials)

    assert result is service
    build.assert_called_once_with("youtube", "v3", credentials=credentials, static_discovery=True)
    assert transport.timeout == token_handler.GOOGLE_API_HTTP_TIMEOUT_SECONDS
