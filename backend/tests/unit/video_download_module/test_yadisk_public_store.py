"""Yandex public share store-prefetch parsing (web download-url fallback)."""

import pytest

from video_download_module.platforms.yadisk.downloader import (
    _parse_yandex_store_prefetch,
    _public_resource_hash_for_file,
)


@pytest.mark.unit
def test_parse_yandex_store_prefetch_double_quoted() -> None:
    html = (
        '<html><script type="application/json" id="store-prefetch">'
        '{"resources":{"r1":{"name":"x.webm","hash":"abc","path":"/x.webm"}},'
        '"environment":{"sk":"sk1"},"rootResourceId":"r1"}'
        "</script></html>"
    )
    store = _parse_yandex_store_prefetch(html)
    assert store is not None
    assert store["environment"]["sk"] == "sk1"


@pytest.mark.unit
def test_public_resource_hash_matches_name() -> None:
    store = {
        "resources": {
            "a": {"name": "foo.webm", "hash": "H1", "path": "/disk/foo.webm"},
            "b": {"name": "bar.webm", "hash": "H2", "path": "/disk/bar.webm"},
        },
    }
    assert _public_resource_hash_for_file(store, {"name": "bar.webm", "path": "/disk/bar.webm"}) == "H2"


@pytest.mark.unit
def test_public_resource_hash_nested_children() -> None:
    store = {
        "resources": {
            "root": {
                "name": "share",
                "type": "dir",
                "children": [
                    {
                        "name": "nested.webm",
                        "hash": "Hnested",
                        "path": "/nested.webm",
                    },
                ],
            },
        },
    }
    assert _public_resource_hash_for_file(store, {"name": "nested.webm"}) == "Hnested"


@pytest.mark.unit
def test_public_resource_hash_by_resource_id() -> None:
    store = {
        "resources": {
            "x": {"id": "rid-99", "name": "other.webm", "hash": "H0"},
            "y": {"id": "rid-1", "name": "foo.webm", "hash": "H1"},
        },
    }
    assert _public_resource_hash_for_file(store, {"name": "foo.webm", "resource_id": "rid-1"}) == "H1"


@pytest.mark.unit
def test_public_resource_hash_case_insensitive_name() -> None:
    store = {
        "resources": {
            "a": {"name": "Foo.WEBM", "hash": "H1"},
        },
    }
    assert _public_resource_hash_for_file(store, {"name": "foo.webm"}) == "H1"
