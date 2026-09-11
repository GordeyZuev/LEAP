"""LEAP publish helpers."""

import uuid
from unittest.mock import MagicMock

from api.services.leap_publish import effective_auto_share, effective_playlist_ids, maybe_enable_recording_share


def test_effective_playlist_ids_output_overrides_preset() -> None:
    assert effective_playlist_ids({"playlist_ids": [3]}, {"playlist_ids": [1, 2]}) == [3]


def test_effective_playlist_ids_inherits_preset() -> None:
    assert effective_playlist_ids({"playlist_ids": []}, {"playlist_ids": [1, 2]}) == [1, 2]


def test_effective_auto_share() -> None:
    assert effective_auto_share({"auto_share": True}) is True
    assert effective_auto_share({}) is False


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
