"""Unit tests for Yandex Disk browse endpoint and helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.routers.credentials import _map_yandex_disk_browse_error, _sort_browse_items
from api.schemas.credentials import YandexDiskBrowseItem
from yandex_disk_module.client import YandexDiskError


@pytest.mark.unit
class TestYandexDiskBrowseHelpers:
    def test_sort_browse_items_dirs_first(self) -> None:
        items = [
            YandexDiskBrowseItem(name="b.mp4", path="/b.mp4", type="file"),
            YandexDiskBrowseItem(name="Zeta", path="/Zeta", type="dir"),
            YandexDiskBrowseItem(name="Alpha", path="/Alpha", type="dir"),
            YandexDiskBrowseItem(name="a.mp4", path="/a.mp4", type="file"),
        ]
        sorted_items = _sort_browse_items(items)
        assert [i.name for i in sorted_items] == ["Alpha", "Zeta", "a.mp4", "b.mp4"]

    def test_map_error_401(self) -> None:
        exc = _map_yandex_disk_browse_error(YandexDiskError("x", status_code=401))
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 401

    def test_map_error_404(self) -> None:
        exc = _map_yandex_disk_browse_error(
            YandexDiskError("x", status_code=404, error_code="DiskPathDoesntExistsError")
        )
        assert exc.status_code == 404


@pytest.mark.unit
class TestBrowseYandexDiskEndpoint:
    def test_browse_success(self, client, mocker, mock_user):  # noqa: ARG002
        mock_client = MagicMock()
        mock_client.list_folder = AsyncMock(
            return_value={
                "_embedded": {
                    "total": 2,
                    "items": [
                        {"type": "dir", "name": "Video", "path": "disk:/Video"},
                        {"type": "file", "name": "a.mp4", "path": "disk:/a.mp4", "size": 10, "mime_type": "video/mp4"},
                    ],
                }
            }
        )
        mocker.patch(
            "api.routers.credentials.get_yandex_disk_client_for_credential",
            new=AsyncMock(return_value=mock_client),
        )

        response = client.get("/api/v1/credentials/3/yandex-disk/browse?path=/")

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "/"
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["type"] == "dir"
        assert data["items"][0]["path"] == "/Video"
        assert data["items"][1]["path"] == "/a.mp4"

    def test_browse_normalizes_disk_prefix_in_query(self, client, mocker, mock_user):  # noqa: ARG002
        mock_client = MagicMock()
        mock_client.list_folder = AsyncMock(return_value={"_embedded": {"total": 0, "items": []}})
        mocker.patch(
            "api.routers.credentials.get_yandex_disk_client_for_credential",
            new=AsyncMock(return_value=mock_client),
        )

        response = client.get("/api/v1/credentials/3/yandex-disk/browse?path=disk:/Video")

        assert response.status_code == 200
        mock_client.list_folder.assert_awaited_once()
        assert mock_client.list_folder.call_args.args[0] == "/Video"

    def test_browse_yandex_api_error(self, client, mocker, mock_user):  # noqa: ARG002
        mock_client = MagicMock()
        mock_client.list_folder = AsyncMock(side_effect=YandexDiskError("nope", status_code=404))
        mocker.patch(
            "api.routers.credentials.get_yandex_disk_client_for_credential",
            new=AsyncMock(return_value=mock_client),
        )

        response = client.get("/api/v1/credentials/3/yandex-disk/browse")

        assert response.status_code == 404
