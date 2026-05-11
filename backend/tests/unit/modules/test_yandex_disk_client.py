"""YandexDiskClient HTTP behavior (mocked httpx)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from yandex_disk_module.client import YandexDiskClient, YandexDiskError


@pytest.mark.unit
class TestYandexDiskClientUploadUrl:
    @pytest.mark.asyncio
    async def test_get_upload_url_returns_href(self) -> None:
        client = YandexDiskClient(oauth_token="test-token")
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value={"href": "https://uploader.example/upload"},
        ):
            href = await client.get_upload_url("/disk/video.mp4", overwrite=False)
            assert href == "https://uploader.example/upload"

    @pytest.mark.asyncio
    async def test_create_folder_swallows_409(self) -> None:
        client = YandexDiskClient(oauth_token="t")
        err = YandexDiskError("exists", status_code=409)
        with patch.object(client, "_request", new_callable=AsyncMock, side_effect=err):
            await client.create_folder("/disk/Folder")

    @pytest.mark.asyncio
    async def test_create_folder_reraises_non_409(self) -> None:
        client = YandexDiskClient(oauth_token="t")
        err = YandexDiskError("nope", status_code=500)
        with (
            patch.object(client, "_request", new_callable=AsyncMock, side_effect=err),
            pytest.raises(YandexDiskError),
        ):
            await client.create_folder("/disk/Folder")


@pytest.mark.unit
class TestYandexDiskClientPublished:
    @pytest.mark.asyncio
    async def test_list_published_resources_calls_disk_endpoint(self) -> None:
        client = YandexDiskClient(oauth_token="t")
        sample = {
            "_embedded": {
                "items": [
                    {"type": "dir", "path": "disk:/Published", "public_url": "https://disk.yandex.ru/d/abc"},
                ],
            },
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=sample) as req:
            out = await client.list_published_resources(limit=50, offset=10)
        assert out == sample
        req.assert_awaited_once()
        call_kw = req.call_args
        assert call_kw[0][0] == "GET"
        assert str(call_kw[0][1]).endswith("/resources/public")
        params = call_kw[1]["params"]
        assert params["limit"] == 50
        assert params["offset"] == 10
        assert "fields" not in params


@pytest.mark.unit
class TestYandexDiskClientUploadFile:
    @pytest.mark.asyncio
    async def test_upload_file_missing_local_raises(self, tmp_path: Path) -> None:
        client = YandexDiskClient(oauth_token="t")
        missing = tmp_path / "nope.bin"
        with pytest.raises(FileNotFoundError):
            await client.upload_file(missing, disk_path="/disk/x.bin")
