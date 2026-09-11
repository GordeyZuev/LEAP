"""POST /api/v1/thumbnails stores custom_filename, not the original file name."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest


def _png_file(filename: str = "photo.png") -> dict:
    return {"file": (filename, BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32), "image/png")}


def _mock_manager(mocker, stored_name: str) -> MagicMock:
    mgr = MagicMock()
    mgr.thumbnail_exists = AsyncMock(return_value=False)
    mgr.write_user_thumbnail = AsyncMock(return_value=f"users/test_user/thumbnails/{stored_name}")
    mgr.get_thumbnail_info = AsyncMock(return_value={"size_bytes": 40, "size_kb": 0.04})
    mocker.patch("api.routers.thumbnails.get_thumbnail_manager", return_value=mgr)
    return mgr


def _written_filename(mgr: MagicMock) -> str:
    mgr.write_user_thumbnail.assert_awaited_once()
    return mgr.write_user_thumbnail.await_args.args[1]


@pytest.mark.unit
class TestCreateThumbnailName:
    def test_custom_filename_is_stored(self, client, mocker):
        mgr = _mock_manager(mocker, "lecture_cover.png")

        response = client.post(
            "/api/v1/thumbnails",
            files=_png_file("photo.png"),
            data={"custom_filename": "lecture_cover"},
        )

        assert response.status_code == 201
        assert response.json()["thumbnail"]["name"] == "lecture_cover.png"
        assert _written_filename(mgr) == "lecture_cover.png"

    def test_custom_filename_sanitizes_spaces(self, client, mocker):
        mgr = _mock_manager(mocker, "lecture_cover.png")

        response = client.post(
            "/api/v1/thumbnails",
            files=_png_file("photo.png"),
            data={"custom_filename": "lecture cover"},
        )

        assert response.status_code == 201
        assert _written_filename(mgr) == "lecture_cover.png"

    def test_original_filename_when_custom_omitted(self, client, mocker):
        mgr = _mock_manager(mocker, "photo.png")

        response = client.post("/api/v1/thumbnails", files=_png_file("photo.png"))

        assert response.status_code == 201
        assert _written_filename(mgr) == "photo.png"

    def test_original_filename_with_spaces_is_sanitized(self, client, mocker):
        mgr = _mock_manager(mocker, "Screenshot_2024.png")

        response = client.post("/api/v1/thumbnails", files=_png_file("Screenshot 2024.png"))

        assert response.status_code == 201
        assert _written_filename(mgr) == "Screenshot_2024.png"
