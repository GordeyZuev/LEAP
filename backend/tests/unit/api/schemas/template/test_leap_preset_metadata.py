from api.schemas.template.preset_metadata import LeapPresetMetadata


def test_leap_preset_playlists_and_auto_share() -> None:
    meta = LeapPresetMetadata.model_validate(
        {"title_template": "{{ display_name }}", "playlist_ids": [1, 2], "auto_share": True}
    )
    assert meta.playlist_ids == [1, 2]
    assert meta.auto_share is True


def test_leap_preset_rejects_duplicate_playlists() -> None:
    import pytest

    with pytest.raises(ValueError, match="unique"):
        LeapPresetMetadata.model_validate({"playlist_ids": [1, 1]})
