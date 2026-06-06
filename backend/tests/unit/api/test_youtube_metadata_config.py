"""Unit tests for YouTubeMetadataConfig template overrides.

Regression guard: the template editor sends category_id/tags/made_for_kids and the
parity fields for YouTube overrides. Before these were added to the schema they were
silently dropped (BASE_MODEL_CONFIG uses Pydantic's default extra="ignore").
"""

import pytest
from pydantic import ValidationError

from api.schemas.template.metadata_config import (
    TemplateMetadataConfig,
    VKMetadataConfig,
    YouTubeMetadataConfig,
)


def test_youtube_metadata_config_accepts_parity_fields():
    cfg = YouTubeMetadataConfig.model_validate(
        {
            "privacy": "unlisted",
            "playlist_id": "PL123",
            "category_id": "27",
            "tags": ["ml", "lecture"],
            "made_for_kids": True,
            "embeddable": False,
            "license": "creativeCommon",
            "default_language": "ru",
            "disable_comments": True,
            "rating_disabled": True,
            "notify_subscribers": False,
        }
    )
    assert cfg.category_id == "27"
    assert cfg.tags == ["ml", "lecture"]
    assert cfg.made_for_kids is True
    assert cfg.embeddable is False
    assert cfg.license == "creativeCommon"
    assert cfg.default_language == "ru"
    assert cfg.disable_comments is True
    assert cfg.rating_disabled is True
    assert cfg.notify_subscribers is False


def test_youtube_metadata_config_fields_default_to_none():
    cfg = YouTubeMetadataConfig()
    assert cfg.category_id is None
    assert cfg.tags is None
    assert cfg.made_for_kids is None
    assert cfg.notify_subscribers is None


def test_youtube_metadata_config_category_id_normalised():
    assert YouTubeMetadataConfig(category_id="27").category_id == "27"
    with pytest.raises(ValidationError):
        YouTubeMetadataConfig(category_id="abc")
    with pytest.raises(ValidationError):
        YouTubeMetadataConfig(category_id="0")


def test_youtube_metadata_config_accepts_publish_at():
    cfg = YouTubeMetadataConfig(publish_at="2026-06-06T10:30:00Z")
    assert cfg.publish_at == "2026-06-06T10:30:00Z"


def test_vk_metadata_config_accepts_parity_fields():
    cfg = VKMetadataConfig.model_validate(
        {
            "repeat": True,
            "compression": True,
            "disable_comments": True,
            "privacy_view": 1,
            "privacy_comment": 0,
            "wallpost": True,
        }
    )
    assert cfg.repeat is True
    assert cfg.compression is True
    assert cfg.disable_comments is True
    # Regression guard: these were previously dropped (not in the schema) even
    # though the template/run-config VK override already sent them.
    assert cfg.privacy_view == 1
    assert cfg.privacy_comment == 0
    assert cfg.wallpost is True
    # Defaults stay None so existing rows are unaffected.
    assert VKMetadataConfig().repeat is None


def test_template_metadata_config_round_trips_youtube_overrides():
    cfg = TemplateMetadataConfig.model_validate(
        {"youtube": {"category_id": "10", "tags": ["a"], "made_for_kids": False}}
    )
    assert cfg.youtube is not None
    assert cfg.youtube.category_id == "10"
    assert cfg.youtube.tags == ["a"]
    assert cfg.youtube.made_for_kids is False
