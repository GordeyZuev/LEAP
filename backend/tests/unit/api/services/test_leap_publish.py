"""LEAP publish helpers."""

import uuid
from unittest.mock import MagicMock

from api.services.leap_publish import (
    effective_auto_share,
    effective_channel_ids,
    effective_playlist_ids,
    maybe_enable_recording_share,
    merge_leap_metadata,
    should_enqueue_leap_publish,
)


def test_effective_playlist_ids_output_overrides_preset() -> None:
    assert effective_playlist_ids({"playlist_ids": [3]}, {"playlist_ids": [1, 2]}) == [3]


def test_effective_playlist_ids_inherits_preset() -> None:
    assert effective_playlist_ids({"playlist_ids": []}, {"playlist_ids": [1, 2]}) == [1, 2]


def test_effective_auto_share() -> None:
    assert effective_auto_share({"auto_share": True}) is True
    assert effective_auto_share({}) is False


def test_effective_channel_ids_inherits_preset() -> None:
    assert effective_channel_ids({"channel_ids": []}, {"channel_ids": [9]}) == [9]
    assert effective_channel_ids({"channel_ids": [4]}, {"channel_ids": [9]}) == [4]


def test_should_enqueue_leap_publish_rules() -> None:
    assert should_enqueue_leap_publish({"publish_leap": False}, {}, has_leap_look_preset=True) is False
    assert should_enqueue_leap_publish({"publish_leap": True}, {}, has_leap_look_preset=True) is True
    assert (
        should_enqueue_leap_publish(
            {"publish_leap": True, "playlist_ids": [1]},
            {},
            has_leap_look_preset=False,
        )
        is True
    )
    assert (
        should_enqueue_leap_publish(
            {"publish_leap": True},
            {"auto_share": True},
            has_leap_look_preset=False,
        )
        is True
    )
    assert (
        should_enqueue_leap_publish(
            {"publish_leap": True, "channel_ids": [2]},
            {},
            has_leap_look_preset=False,
        )
        is True
    )
    assert should_enqueue_leap_publish({"publish_leap": True}, {}, has_leap_look_preset=False) is False


def test_merge_leap_metadata_overlays_metadata_config() -> None:
    merged = merge_leap_metadata(
        {"playlist_ids": [1]},
        metadata_config={"leap": {"auto_share": True}},
    )
    assert merged["playlist_ids"] == [1]
    assert merged["auto_share"] is True


def test_maybe_enable_share_mints_token() -> None:
    rec = MagicMock()
    rec.share_token = None
    rec.share_enabled = False
    url = maybe_enable_recording_share(rec, auto_share=True)
    assert rec.share_enabled is True
    assert rec.share_token is not None
    assert url


def test_maybe_enable_share_does_not_reenable_disabled() -> None:
    rec = MagicMock()
    rec.share_token = uuid.uuid4()
    rec.share_enabled = False
    assert maybe_enable_recording_share(rec, auto_share=True) is None
    assert rec.share_enabled is False
