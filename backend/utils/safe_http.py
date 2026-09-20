"""SSRF guards for server-side HTTP fetches.

User-controlled URLs (yt-dlp, Yandex Disk public links, MTS Link, generic
downloaders) must not reach loopback, RFC1918, link-local, or cloud-metadata
addresses. Redirect hops are re-validated; DNS is resolved before each request.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlparse

import httpx

# Page hosts the product actually ingests via yt-dlp.
YTDLP_HOST_SUFFIXES: tuple[str, ...] = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "vk.com",
    "vk.ru",
    "vkvideo.ru",
    "rutube.ru",
    "vimeo.com",
)

# Share page + Disk REST + Yandex CDNs used after redirect.
YANDEX_DISK_HOST_SUFFIXES: tuple[str, ...] = (
    "yadi.sk",
    "disk.yandex.ru",
    "disk.yandex.com",
    "disk.yandex.net",
    "downloader.disk.yandex.ru",
    "cloud-api.yandex.net",
    "yandex.net",
    "yandex.ru",
    "yandex.com",
    "yastatic.net",
)

# User-entered share links only (not every yandex.ru property).
YANDEX_DISK_PUBLIC_SHARE_SUFFIXES: tuple[str, ...] = (
    "yadi.sk",
    "disk.yandex.ru",
    "disk.yandex.com",
    "disk.yandex.net",
)

# Cloud UserAPI and documented MTS Link hosts. On-prem URLs must match this suffix.
MTS_LINK_HOST_SUFFIXES: tuple[str, ...] = ("mts-link.ru",)

_MAX_REDIRECTS = 5


class UnsafeUrlError(ValueError):
    """URL is not safe to fetch from a worker or API process."""


def host_matches_suffixes(hostname: str, suffixes: Sequence[str]) -> bool:
    """True if hostname equals or is a subdomain of any allowed suffix."""
    host = hostname.lower().rstrip(".")
    if not host:
        return False
    for suffix in suffixes:
        allowed = suffix.lower().lstrip(".").rstrip(".")
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True unless the address is globally routable (blocks CGNAT / cloud IMDS too)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_blocked_ip(ip.ipv4_mapped)
    return not ip.is_global


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _resolve_host_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeUrlError(f"Cannot resolve host {hostname!r}") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        raw = sockaddr[0]
        if raw in seen:
            continue
        seen.add(raw)
        parsed = _parse_ip(raw)
        if parsed is not None:
            addresses.append(parsed)
    if not addresses:
        raise UnsafeUrlError(f"Cannot resolve host {hostname!r}")
    return addresses


def validate_public_url(
    url: str,
    *,
    allowed_host_suffixes: Sequence[str] | None = None,
    require_https: bool = False,
) -> str:
    """Validate that ``url`` is an http(s) URL to a public, optionally allowlisted host.

    Returns the stripped URL. Raises :class:`UnsafeUrlError` otherwise.
    """
    stripped = (url or "").strip()
    if not stripped:
        raise UnsafeUrlError("URL is empty")

    parsed = urlparse(stripped)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise UnsafeUrlError(f"URL scheme {scheme!r} is not allowed")
    if require_https and scheme != "https":
        raise UnsafeUrlError("URL must use https")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL must not contain userinfo")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL has no hostname")

    if allowed_host_suffixes is not None and not host_matches_suffixes(hostname, allowed_host_suffixes):
        raise UnsafeUrlError(f"Host {hostname!r} is not on the allowlist")

    literal_ip = _parse_ip(hostname)
    if literal_ip is not None:
        if is_blocked_ip(literal_ip):
            raise UnsafeUrlError(f"IP {hostname} is not allowed")
        return stripped

    for address in _resolve_host_ips(hostname):
        if is_blocked_ip(address):
            raise UnsafeUrlError(f"Host {hostname!r} resolves to a blocked address")

    return stripped


def assert_allowlisted_https_url(url: str, suffixes: Sequence[str]) -> str:
    """HTTPS URL on an allowlisted hostname. Does not resolve DNS (use at config time)."""
    stripped = (url or "").strip()
    if not stripped:
        raise UnsafeUrlError("URL is empty")
    parsed = urlparse(stripped)
    if parsed.scheme != "https":
        raise UnsafeUrlError("URL must use https")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL must not contain userinfo")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL has no hostname")
    if _parse_ip(hostname) is not None:
        raise UnsafeUrlError("URL must use a hostname, not an IP")
    if not host_matches_suffixes(hostname, suffixes):
        raise UnsafeUrlError(f"Host {hostname!r} is not on the allowlist")
    return stripped.rstrip("/")


async def _send_following_redirects(
    client: httpx.AsyncClient,
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    allowed_host_suffixes: Sequence[str] | None = None,
    require_https: bool = False,
    max_hops: int = _MAX_REDIRECTS,
    stream: bool = False,
) -> httpx.Response:
    current = validate_public_url(url, allowed_host_suffixes=allowed_host_suffixes, require_https=require_https)
    req_headers = dict(headers) if headers else None
    req_params = params
    req_cookies = cookies
    last_error: UnsafeUrlError | None = None

    for _hop in range(max_hops + 1):
        request = client.build_request(
            method,
            current,
            headers=req_headers,
            params=req_params,
            cookies=req_cookies,
        )
        response = await client.send(request, stream=stream, follow_redirects=False)
        if response.has_redirect_location:
            location = response.headers.get("location")
            await response.aclose()
            if not location:
                last_error = UnsafeUrlError("Redirect missing Location header")
                break
            current = validate_public_url(
                urljoin(str(response.url), location),
                allowed_host_suffixes=allowed_host_suffixes,
                require_https=require_https,
            )
            req_params = None
            continue
        return response

    raise last_error or UnsafeUrlError("Too many redirects")


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    allowed_host_suffixes: Sequence[str] | None = None,
    require_https: bool = False,
    max_hops: int = _MAX_REDIRECTS,
) -> httpx.Response:
    """GET ``url``, following redirects only to public (optionally allowlisted) hosts."""
    return await _send_following_redirects(
        client,
        url,
        method="GET",
        headers=headers,
        params=params,
        cookies=cookies,
        allowed_host_suffixes=allowed_host_suffixes,
        require_https=require_https,
        max_hops=max_hops,
        stream=False,
    )


@asynccontextmanager
async def safe_stream(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    allowed_host_suffixes: Sequence[str] | None = None,
    require_https: bool = False,
    max_hops: int = _MAX_REDIRECTS,
) -> AsyncIterator[httpx.Response]:
    """Stream GET ``url`` after validating every redirect hop."""
    response = await _send_following_redirects(
        client,
        url,
        method="GET",
        headers=headers,
        params=params,
        cookies=cookies,
        allowed_host_suffixes=allowed_host_suffixes,
        require_https=require_https,
        max_hops=max_hops,
        stream=True,
    )
    try:
        yield response
    finally:
        await response.aclose()
