"""OAuth href download headers (private Disk) vs public CDN strategies."""

import pytest

from video_download_module.platforms.yadisk.downloader import (
    _yandex_disk_api_download_headers,
    _yandex_disk_cdn_header_strategies,
    _yandex_disk_href_host_needs_oauth,
)


@pytest.mark.unit
def test_api_download_headers_includes_oauth() -> None:
    h = _yandex_disk_api_download_headers("secret-token")
    assert h["Authorization"] == "OAuth secret-token"
    assert "Referer" not in h
    assert "Origin" not in h


@pytest.mark.unit
def test_api_download_headers_no_token_no_authorization() -> None:
    h = _yandex_disk_api_download_headers(None)
    assert "Authorization" not in h
    assert "User-Agent" not in h


@pytest.mark.unit
def test_href_host_needs_oauth_allowlist() -> None:
    assert _yandex_disk_href_host_needs_oauth("s123.storage.yandex.net") is False
    assert _yandex_disk_href_host_needs_oauth("downloader.dst.yandex.ru") is True
    assert _yandex_disk_href_host_needs_oauth("api-internal.yandex.net") is True
    assert _yandex_disk_href_host_needs_oauth("downloader.example.yandex.com") is True
    assert _yandex_disk_href_host_needs_oauth("cdn.example.com") is False
    assert _yandex_disk_href_host_needs_oauth(None) is False


@pytest.mark.unit
def test_cdn_strategies_public_vs_api() -> None:
    pub = _yandex_disk_cdn_header_strategies(
        {"download_method": "public", "public_key": "https://disk.yandex.ru/d/abc"}
    )
    assert pub[0].get("Referer", "").startswith("https://disk.yandex.ru/")

    api = _yandex_disk_cdn_header_strategies({"download_method": "api", "public_key": ""})
    assert all("Authorization" not in x for x in api)
