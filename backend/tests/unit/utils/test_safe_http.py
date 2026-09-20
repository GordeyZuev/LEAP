"""SSRF guards: public-URL validation and redirect pinning."""

import ipaddress
import socket

import httpx
import pytest

from utils.safe_http import (
    YANDEX_DISK_HOST_SUFFIXES,
    YANDEX_DISK_PUBLIC_SHARE_SUFFIXES,
    YTDLP_HOST_SUFFIXES,
    UnsafeUrlError,
    assert_allowlisted_https_url,
    host_matches_suffixes,
    is_blocked_ip,
    safe_get,
    safe_stream,
    validate_public_url,
)

PUBLIC_A = "8.8.8.8"
METADATA_IP = "169.254.169.254"


def _addrinfo(host: str, port, *_args, **_kwargs):
    mapping = {
        "youtube.com": PUBLIC_A,
        "www.youtube.com": PUBLIC_A,
        "evil.example": PUBLIC_A,
        "cdn.example": "1.1.1.1",
        "internal.example": "10.0.0.1",
        "loopback.example": "127.0.0.1",
        "metadata.example": METADATA_IP,
    }
    ip = mapping.get(host)
    if ip is None:
        raise socket.gaierror(f"unknown host {host}")
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))]


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("utils.safe_http.socket.getaddrinfo", _addrinfo)


@pytest.mark.unit
class TestIsBlockedIp:
    def test_loopback(self) -> None:
        assert is_blocked_ip(ipaddress.ip_address("127.0.0.1"))

    def test_rfc1918(self) -> None:
        assert is_blocked_ip(ipaddress.ip_address("10.1.2.3"))
        assert is_blocked_ip(ipaddress.ip_address("192.168.0.1"))
        assert is_blocked_ip(ipaddress.ip_address("172.16.5.5"))

    def test_link_local_metadata(self) -> None:
        assert is_blocked_ip(ipaddress.ip_address(METADATA_IP))

    def test_public(self) -> None:
        assert not is_blocked_ip(ipaddress.ip_address("8.8.8.8"))

    def test_ipv4_mapped_loopback(self) -> None:
        assert is_blocked_ip(ipaddress.ip_address("::ffff:127.0.0.1"))

    def test_cgnat_and_alibaba_metadata(self) -> None:
        assert is_blocked_ip(ipaddress.ip_address("100.64.0.1"))
        assert is_blocked_ip(ipaddress.ip_address("100.100.100.200"))


@pytest.mark.unit
class TestValidatePublicUrl:
    def test_rejects_empty(self) -> None:
        with pytest.raises(UnsafeUrlError, match="empty"):
            validate_public_url("")

    def test_rejects_file_scheme(self) -> None:
        with pytest.raises(UnsafeUrlError, match="scheme"):
            validate_public_url("file:///etc/passwd")

    def test_rejects_gopher(self) -> None:
        with pytest.raises(UnsafeUrlError, match="scheme"):
            validate_public_url("gopher://127.0.0.1/")

    def test_rejects_loopback_literal(self) -> None:
        with pytest.raises(UnsafeUrlError, match="not allowed"):
            validate_public_url("http://127.0.0.1:6379/")

    def test_rejects_metadata_literal(self) -> None:
        with pytest.raises(UnsafeUrlError, match="not allowed"):
            validate_public_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_userinfo(self) -> None:
        with pytest.raises(UnsafeUrlError, match="userinfo"):
            validate_public_url("https://user:pass@youtube.com/watch")

    def test_rejects_unlisted_host(self) -> None:
        with pytest.raises(UnsafeUrlError, match="allowlist"):
            validate_public_url("https://evil.example/x", allowed_host_suffixes=YTDLP_HOST_SUFFIXES)

    def test_rejects_host_resolving_private(self) -> None:
        with pytest.raises(UnsafeUrlError, match="blocked"):
            validate_public_url("https://internal.example/x")

    def test_rejects_host_resolving_loopback(self) -> None:
        with pytest.raises(UnsafeUrlError, match="blocked"):
            validate_public_url("http://loopback.example/")

    def test_accepts_youtube(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_public_url(url, allowed_host_suffixes=YTDLP_HOST_SUFFIXES) == url

    def test_require_https(self) -> None:
        with pytest.raises(UnsafeUrlError, match="https"):
            validate_public_url("http://youtube.com/", require_https=True)


@pytest.mark.unit
class TestYandexShareAllowlist:
    def test_share_suffixes_reject_mail(self) -> None:
        assert not host_matches_suffixes("mail.yandex.ru", YANDEX_DISK_PUBLIC_SHARE_SUFFIXES)

    def test_fetch_suffixes_allow_downloader_dst(self) -> None:
        assert host_matches_suffixes("downloader.dst.yandex.ru", YANDEX_DISK_HOST_SUFFIXES)
        assert host_matches_suffixes("s123.storage.yandex.net", YANDEX_DISK_HOST_SUFFIXES)


@pytest.mark.unit
class TestAssertAllowlistedHttpsUrl:
    def test_rejects_http(self) -> None:
        with pytest.raises(UnsafeUrlError, match="https"):
            assert_allowlisted_https_url("http://userapi.mts-link.ru/v3", ("mts-link.ru",))

    def test_rejects_ip(self) -> None:
        with pytest.raises(UnsafeUrlError, match="hostname"):
            assert_allowlisted_https_url("https://127.0.0.1/v3", ("mts-link.ru",))

    def test_rejects_other_host(self) -> None:
        with pytest.raises(UnsafeUrlError, match="allowlist"):
            assert_allowlisted_https_url("https://evil.example/v3", ("mts-link.ru",))

    def test_accepts_mts_cloud(self) -> None:
        url = assert_allowlisted_https_url("https://userapi.mts-link.ru/v3/", ("mts-link.ru",))
        assert url == "https://userapi.mts-link.ru/v3"


def _redirect_then_ok(request: httpx.Request) -> httpx.Response:
    if request.url.host == "evil.example":
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
    if request.url.host == "cdn.example":
        return httpx.Response(200, content=b"ok-body")
    return httpx.Response(404)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSafeRedirects:
    async def test_blocks_redirect_to_metadata(self) -> None:
        transport = httpx.MockTransport(_redirect_then_ok)
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            with pytest.raises(UnsafeUrlError, match="not allowed"):
                await safe_get(client, "https://evil.example/start")

    async def test_allows_public_redirect_target(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "evil.example":
                return httpx.Response(302, headers={"Location": "https://cdn.example/file"})
            return httpx.Response(200, content=b"payload")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            response = await safe_get(client, "https://evil.example/start")
            assert response.status_code == 200
            assert response.content == b"payload"

    async def test_stream_blocks_metadata_redirect(self) -> None:
        transport = httpx.MockTransport(_redirect_then_ok)
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            with pytest.raises(UnsafeUrlError, match="not allowed"):
                async with safe_stream(client, "https://evil.example/start"):
                    pass
