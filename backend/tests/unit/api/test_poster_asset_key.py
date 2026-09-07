"""Poster asset key helpers — stable identity across presign refreshes."""

from api.routers.recordings import _poster_asset_key, _poster_fields, _PosterPreview


class TestPosterAssetKey:
    def test_compose_with_fallback(self) -> None:
        assert _poster_asset_key("users/1/rec/1/poster.jpg", "users/1/thumb.png") == (
            "users/1/rec/1/poster.jpg|users/1/thumb.png"
        )

    def test_compose_primary_only(self) -> None:
        assert _poster_asset_key("users/1/thumb.png") == "users/1/thumb.png|"

    def test_poster_fields_includes_asset_key(self) -> None:
        previews = {
            42: _PosterPreview(
                url="https://example.test/presigned",
                source="thumbnail",
                fallback_url="https://example.test/fallback",
                asset_key="thumb|frame",
            ),
        }
        fields = _poster_fields(previews, 42)
        assert fields["poster_url"] == "https://example.test/presigned"
        assert fields["poster_fallback_url"] == "https://example.test/fallback"
        assert fields["poster_asset_key"] == "thumb|frame"

    def test_poster_fields_missing_recording(self) -> None:
        assert _poster_fields({}, 1)["poster_asset_key"] is None
