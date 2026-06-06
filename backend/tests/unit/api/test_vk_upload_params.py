"""VK upload metadata → video.save kwargs extraction."""

import pytest

from api.tasks.upload import _vk_upload_params_from_metadata


@pytest.mark.unit
def test_flat_preset_metadata_maps_disable_comments() -> None:
    params = _vk_upload_params_from_metadata(
        {
            "group_id": 123,
            "disable_comments": True,
            "compression": True,
            "repeat": False,
        }
    )
    assert params == {
        "group_id": 123,
        "no_comments": True,
        "compression": True,
        "repeat": False,
    }


@pytest.mark.unit
def test_nested_vk_block_maps_disable_comments_and_compression() -> None:
    params = _vk_upload_params_from_metadata(
        {
            "vk": {
                "disable_comments": True,
                "compression": True,
                "wallpost": True,
            }
        }
    )
    assert params == {
        "no_comments": True,
        "compression": True,
        "wallpost": True,
    }


@pytest.mark.unit
def test_top_level_no_comments_takes_precedence_over_disable_comments() -> None:
    params = _vk_upload_params_from_metadata(
        {
            "no_comments": False,
            "disable_comments": True,
        }
    )
    assert params["no_comments"] is False
