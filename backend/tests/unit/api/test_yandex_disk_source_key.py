"""Yandex Disk source_key helpers: stable identity across renames."""

import pytest

from api.routers.input_sources import _yandex_disk_canonical_source_key, _yandex_disk_path_source_key


@pytest.mark.unit
def test_path_key() -> None:
    assert _yandex_disk_path_source_key("/disk/a.mp4", "a.mp4") == "yadisk:/disk/a.mp4"
    assert _yandex_disk_path_source_key("", "only_name.mp4") == "yadisk:only_name.mp4"


@pytest.mark.unit
def test_canonical_prefers_resource_id() -> None:
    info = {"resource_id": "abc123", "md5": "deadbeef", "size": 100, "path": "/x.mp4"}
    assert _yandex_disk_canonical_source_key(info, "/x.mp4", "x.mp4") == "yadisk:rid:abc123"


@pytest.mark.unit
def test_canonical_md5_when_no_rid() -> None:
    info = {"md5": "aaa", "size": 42, "path": "/a.mp4"}
    assert _yandex_disk_canonical_source_key(info, "/a.mp4", "a.mp4") == "yadisk:md5:aaa:42"


@pytest.mark.unit
def test_canonical_falls_back_to_path() -> None:
    info = {"path": "/disk/z.mp4", "name": "z.mp4", "size": 1}
    assert _yandex_disk_canonical_source_key(info, "/disk/z.mp4", "z.mp4") == "yadisk:/disk/z.mp4"
