"""VK uploader video.save parameter mapping."""

import pytest

from video_upload_module.config_factory import VKConfig
from video_upload_module.platforms.vk.uploader import VKUploader


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_upload_url_sends_compression_and_disable_comments_alias() -> None:
    uploader = VKUploader(VKConfig(access_token="test"))
    captured: dict = {}

    async def fake_request(method: str, params: dict) -> dict:
        captured["method"] = method
        captured["params"] = params
        return {"upload_url": "https://example.com/upload"}

    uploader._make_request = fake_request  # type: ignore[method-assign]

    url = await uploader._get_upload_url(
        "title",
        disable_comments=True,
        compression=True,
        wallpost=True,
    )

    assert url == "https://example.com/upload"
    assert captured["method"] == "video.save"
    assert captured["params"]["no_comments"] == 1
    assert captured["params"]["compression"] == 1
    assert captured["params"]["wallpost"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_upload_url_prefers_no_comments_over_disable_comments() -> None:
    uploader = VKUploader(VKConfig(access_token="test"))
    captured: dict = {}

    async def fake_request(_method: str, params: dict) -> dict:
        captured["params"] = params
        return {"upload_url": "https://example.com/upload"}

    uploader._make_request = fake_request  # type: ignore[method-assign]

    await uploader._get_upload_url("title", no_comments=False, disable_comments=True)

    assert captured["params"]["no_comments"] == 0
