"""VK API error 6 is a rate limit, not a generic upload failure."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.shared.exceptions import ExternalRateLimitError
from video_upload_module.config_factory import VKConfig
from video_upload_module.platforms.vk.uploader import VKUploader


def _http(response) -> AsyncMock:
    http = AsyncMock()
    http.post = AsyncMock(return_value=response)
    http.__aenter__ = AsyncMock(return_value=http)
    http.__aexit__ = AsyncMock(return_value=None)
    return http


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_6_retries_then_raises(mocker) -> None:
    uploader = VKUploader(VKConfig(access_token="test"))
    uploader.credential_id = 17
    mocker.patch("video_upload_module.platforms.vk.uploader.acquire_external_slot", new_callable=AsyncMock)
    mocker.patch("video_upload_module.platforms.vk.uploader.asyncio.sleep", new_callable=AsyncMock)
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {"error": {"error_code": 6, "error_msg": "Too many requests per second"}}
    http = _http(response)
    mocker.patch("video_upload_module.platforms.vk.uploader.httpx.AsyncClient", return_value=http)

    with pytest.raises(ExternalRateLimitError) as exc:
        await VKUploader._make_request.__wrapped__(uploader, "video.save", {"name": "x"})

    assert exc.value.platform == "vk_video"
    assert exc.value.credential_id == 17
    assert http.post.await_count == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_5_is_returned_for_token_decorator(mocker) -> None:
    uploader = VKUploader(VKConfig(access_token="test"))
    uploader.credential_id = 17
    mocker.patch("video_upload_module.platforms.vk.uploader.acquire_external_slot", new_callable=AsyncMock)
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {"error": {"error_code": 5, "error_msg": "User authorization failed"}}
    http = _http(response)
    mocker.patch("video_upload_module.platforms.vk.uploader.httpx.AsyncClient", return_value=http)

    result = await VKUploader._make_request.__wrapped__(uploader, "users.get", {})

    assert result["error"]["error_code"] == 5
    assert http.post.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_28_is_returned_for_token_decorator(mocker) -> None:
    uploader = VKUploader(VKConfig(access_token="test"))
    uploader.credential_id = 17
    mocker.patch("video_upload_module.platforms.vk.uploader.acquire_external_slot", new_callable=AsyncMock)
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {"error": {"error_code": 28, "error_msg": "Application authorization failed"}}
    http = _http(response)
    mocker.patch("video_upload_module.platforms.vk.uploader.httpx.AsyncClient", return_value=http)

    result = await VKUploader._make_request.__wrapped__(uploader, "users.get", {})

    assert result["error"]["error_code"] == 28
    assert http.post.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_video_reraises_rate_limit(mocker) -> None:
    uploader = VKUploader(VKConfig(access_token="test"))
    uploader._authenticated = True
    mocker.patch.object(
        uploader,
        "_get_upload_url",
        side_effect=ExternalRateLimitError(platform="vk_video", credential_id=17),
    )

    with pytest.raises(ExternalRateLimitError) as exc:
        await uploader.upload_video("/tmp/x.mp4", "title")

    assert exc.value.platform == "vk_video"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_reraises_rate_limit(mocker) -> None:
    uploader = VKUploader(VKConfig(access_token="test"))
    uploader.credential_id = 17
    mocker.patch.object(
        uploader,
        "_make_request",
        side_effect=ExternalRateLimitError(platform="vk_video", credential_id=17),
    )

    with pytest.raises(ExternalRateLimitError):
        await uploader.authenticate()
