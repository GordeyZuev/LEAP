"""Yandex Disk video downloader."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from file_storage.path_builder import StoragePathBuilder
from logger import get_logger
from video_download_module.core.base import BaseDownloader, DownloadResult

logger = get_logger()

_YANDEX_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _yandex_disk_cdn_header_strategies(source_meta: dict) -> list[dict[str, str]]:
    """Yandex ``downloader.disk.yandex.ru`` links are picky about client headers.

    Behavior varies: some shares need ``Referer`` = the public folder URL; others reject
    a generic Referer or any Referer (see Habr Q&A on Disk API 403). Try a few patterns.
    """
    ua = {"User-Agent": _YANDEX_BROWSER_UA, "Accept": "*/*"}
    origin_disk = {
        "User-Agent": _YANDEX_BROWSER_UA,
        "Accept": "*/*",
        "Origin": "https://disk.yandex.ru",
        "Referer": "https://disk.yandex.ru/",
    }
    pk = (source_meta.get("public_key") or "").strip()
    if source_meta.get("download_method") == "public" and pk.startswith("http"):
        share_ref = pk.split("#", 1)[0].rstrip("/")
        return [
            {
                "User-Agent": _YANDEX_BROWSER_UA,
                "Accept": "*/*",
                "Origin": "https://disk.yandex.ru",
                "Referer": share_ref,
            },
            dict(origin_disk),
            dict(ua),
        ]
    return [origin_disk, ua]


def _yandex_disk_api_download_headers(oauth_token: str | None) -> dict[str, str]:
    """Minimal headers for a one-shot GET of ``href`` (fallback / tests)."""
    h: dict[str, str] = {"Accept": "*/*"}
    if oauth_token:
        h["Authorization"] = f"OAuth {oauth_token}"
    return h


def _yandex_disk_href_host_needs_oauth(hostname: str | None) -> bool:
    """Use ``Authorization: OAuth`` only on Yandex hosts (not ``*.storage.yandex.net``, not third-party CDNs)."""
    if not hostname:
        return False
    hn = hostname.lower()
    if "storage.yandex.net" in hn:
        return False
    return hn.endswith((".yandex.ru", ".yandex.net", ".yandex.com"))


def _parse_yandex_store_prefetch(html: str) -> dict[str, Any] | None:
    """Parse ``<script id='store-prefetch'>`` JSON (full body up to ``</script>``, not ``.+?``)."""
    for q in ('"', "'"):
        needle = f"id={q}store-prefetch{q}"
        pos = html.find(needle)
        if pos < 0:
            continue
        script_start = html.rfind("<script", 0, pos)
        if script_start < 0:
            continue
        gt = html.find(">", pos)
        if gt < 0:
            continue
        body_start = gt + 1
        end = html.find("</script>", body_start)
        if end < 0:
            continue
        raw = html[body_start:end].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def _iter_nested_dicts(obj: Any, max_depth: int = 40) -> Iterator[dict[str, Any]]:
    """Depth-first over all dicts (files often live under ``children``, not top-level ``resources``)."""
    if max_depth < 0 or not isinstance(obj, dict | list):
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_nested_dicts(v, max_depth - 1)
    else:
        for v in obj:
            yield from _iter_nested_dicts(v, max_depth - 1)


def _yandex_node_public_hash(node: dict[str, Any]) -> str | None:
    h = node.get("hash")
    if h:
        return str(h)
    meta = node.get("meta")
    if isinstance(meta, dict):
        mh = meta.get("hash")
        if mh:
            return str(mh)
    return None


def _paths_might_match(api_path: str, node_path: str) -> bool:
    a = api_path.replace("\\", "/").strip()
    b = node_path.replace("\\", "/").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    if a.endswith(b) or b.endswith(a):
        return True

    # ``disk:/foo`` vs ``/foo``
    def strip_disk(p: str) -> str:
        if p.lower().startswith("disk:"):
            return p[5:].lstrip("/")
        return p.lstrip("/")

    sa, sb = strip_disk(a), strip_disk(b)
    return sa == sb or sa.endswith(sb) or sb.endswith(sa)


def _public_resource_hash_for_file(store: dict[str, Any], source_meta: dict[str, Any]) -> str | None:
    """Find ``hash`` for a file anywhere in the embedded Disk store (nested folders)."""
    name = (source_meta.get("name") or "").strip()
    path = (source_meta.get("path") or "").replace("\\", "/")
    rid = source_meta.get("resource_id")
    nodes = [n for n in _iter_nested_dicts(store) if isinstance(n, dict)]

    if rid:
        rs = str(rid)
        for n in nodes:
            if str(n.get("id", "")) == rs or str(n.get("resource_id", "")) == rs:
                nh = _yandex_node_public_hash(n)
                if nh:
                    return nh

    by_name: list[dict[str, Any]] = []
    for n in nodes:
        if n.get("name") == name:
            by_name.append(n)

    if len(by_name) == 1:
        nh = _yandex_node_public_hash(by_name[0])
        if nh:
            return nh
    if len(by_name) > 1 and path:
        for n in by_name:
            rp = str(n.get("path") or "")
            if _paths_might_match(path, rp):
                nh = _yandex_node_public_hash(n)
                if nh:
                    return nh
    if name:
        nl = name.lower()
        for n in nodes:
            if str(n.get("name") or "").lower() != nl:
                continue
            nh = _yandex_node_public_hash(n)
            if nh:
                return nh
    if path:
        leaf = path.rstrip("/").rsplit("/", 1)[-1]
        for n in nodes:
            if n.get("name") == leaf:
                nh = _yandex_node_public_hash(n)
                if nh:
                    return nh
    return None


async def _yandex_web_public_download_url(
    client: httpx.AsyncClient,
    share_url: str,
    resource_hash: str,
    sk: str,
) -> str | None:
    """POST ``/public/api/download-url`` using **same** ``AsyncClient`` as the share page GET."""
    page_url = share_url.split("#", 1)[0]
    api_url = urljoin(page_url, "/public/api/download-url")
    origin = urljoin(page_url, "/").rstrip("/")
    headers = {
        "User-Agent": _YANDEX_BROWSER_UA,
        "Content-Type": "text/plain",
        "Accept": "application/json, text/plain, */*",
        "Origin": origin,
        "Referer": page_url,
    }
    body = json.dumps({"hash": resource_hash, "sk": sk})
    try:
        response = await client.post(api_url, content=body, headers=headers)
        if response.status_code != 200:
            logger.warning(
                f"Yandex web download-url | status={response.status_code} | body_head={response.text[:200]!r}"
            )
            return None
        payload = response.json()
    except Exception as e:
        logger.warning(f"Yandex web download-url request failed | {e!s}")
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning(f"Yandex web download-url | unexpected JSON shape | keys={list(payload.keys())}")
        return None
    url = data.get("url")
    return str(url) if url else None


class YandexDiskDownloader(BaseDownloader):
    """Downloads video files from Yandex Disk via REST API."""

    def __init__(
        self,
        user_slug: int,
        storage_builder: StoragePathBuilder | None = None,
        oauth_token: str | None = None,
        **kwargs,  # noqa: ARG002
    ):
        super().__init__(user_slug, storage_builder)
        self.oauth_token = oauth_token

    async def _stream_file_with_client(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        filepath: Path,
        expected_size: int | None,
        description: str,
        source_name: str | None = None,
    ) -> bool:
        """Stream one URL to disk using an existing client (keeps cookie jar)."""
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            async with client.stream("GET", url, headers=dict(headers)) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                if total_size == 0 and expected_size:
                    total_size = expected_size
                downloaded = 0
                with filepath.open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
            ref_size = total_size if total_size else expected_size
            if not self._validate_file(filepath, expected_size, ref_size, source_name=source_name):
                if filepath.exists():
                    filepath.unlink()
                return False
            logger.info(f"Downloaded {downloaded / (1024 * 1024):.1f} MB")
            return True
        except httpx.HTTPStatusError as e:
            logger.warning(f"Yandex stream | {description} | HTTP {e.response.status_code}")
            if filepath.exists():
                filepath.unlink()
            return False
        except Exception as e:
            logger.warning(f"Yandex stream | {description} | {e!s}")
            if filepath.exists():
                filepath.unlink()
            return False

    async def _download_yandex_public_unified(
        self,
        pk_url: str,
        source_meta: dict[str, Any],
        rest_href: str,
        target_path: Path,
        expected_size: int | None,
        description: str,
    ) -> bool:
        """One ``AsyncClient``: GET share page → POST download-url → GET file (cookie jar preserved)."""
        page_headers = {
            "User-Agent": _YANDEX_BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        timeout = httpx.Timeout(180.0, connect=30.0, read=120.0)
        web_url: str | None = None
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, limits=limits) as client:
            page = await client.get(pk_url.split("#", 1)[0], headers=page_headers)
            html = page.text
            if "SmartCaptcha" in html or "не робот" in html.lower():
                logger.warning("Yandex public page may be a bot/CAPTCHA challenge — store often missing")

            store = _parse_yandex_store_prefetch(html)
            if not store:
                logger.warning("Yandex public | no store-prefetch JSON | html_len=%s", len(html))
            else:
                raw_env = store.get("environment")
                env = raw_env if isinstance(raw_env, dict) else {}
                sk = env.get("sk")
                if not sk:
                    logger.warning("Yandex public | store.environment.sk missing")
                else:
                    rhash = _public_resource_hash_for_file(store, source_meta)
                    if not rhash:
                        root_id = store.get("rootResourceId")
                        res = (store.get("resources") or {}).get(root_id) if root_id else None
                        if isinstance(res, dict) and res.get("type") == "file":
                            rh = res.get("hash")
                            rhash = str(rh) if rh else None
                    if rhash:
                        web_url = await _yandex_web_public_download_url(client, pk_url, rhash, str(sk))
                        if web_url:
                            logger.info("Yandex public | URL from web /public/api/download-url")
                    else:
                        logger.warning("Yandex public | no resource hash in store for this recording")

            urls: list[str] = []
            if web_url:
                urls.append(web_url)
            if rest_href not in urls:
                urls.append(rest_href)

            for file_url in urls:
                for hdr in _yandex_disk_cdn_header_strategies(source_meta):
                    if await self._stream_file_with_client(
                        client,
                        file_url,
                        hdr,
                        target_path,
                        expected_size,
                        description,
                        source_name=source_meta.get("name"),
                    ):
                        return True
        return False

    async def _download_yandex_api_href(
        self,
        download_url: str,
        target_path: Path,
        oauth_token: str | None,
        expected_size: int | None,
        description: str,
        source_name: str | None = None,
    ) -> bool:
        """GET ``href`` from ``/resources/download`` with OAuth on Yandex hosts, without OAuth on storage CDN.

        ``httpx`` (like curl) does not forward ``Authorization`` to another host after a redirect; the
        first hop (``downloader.*.yandex.ru`` / similar) requires ``OAuth``, the final
        ``*.storage.yandex.net`` URL is signed and must be fetched without it.
        """
        timeout = httpx.Timeout(180.0, connect=30.0, read=120.0)
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        downloaded = target_path.stat().st_size if target_path.exists() else 0

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            current_url = download_url
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, limits=limits) as client:
                for _ in range(24):
                    host = urlparse(current_url).hostname
                    hdrs: dict[str, str] = {"Accept": "*/*"}
                    if oauth_token and _yandex_disk_href_host_needs_oauth(host):
                        hdrs["Authorization"] = f"OAuth {oauth_token}"
                    if downloaded > 0:
                        hdrs["Range"] = f"bytes={downloaded}-"

                    async with client.stream("GET", current_url, headers=hdrs) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            loc = response.headers.get("location")
                            if not loc:
                                logger.warning("Yandex API download | redirect without Location | %s", description)
                                return False
                            await response.aread()
                            current_url = urljoin(current_url, loc)
                            continue

                        if downloaded > 0 and response.status_code == 200:
                            logger.warning(
                                "Yandex API download | Range ignored (HTTP 200), restarting | %s",
                                description,
                            )
                            await response.aread()
                            if target_path.exists():
                                target_path.unlink()
                            downloaded = 0
                            current_url = download_url
                            continue

                        if response.status_code == 416 and target_path.exists():
                            await response.aread()
                            target_path.unlink()
                            downloaded = 0
                            current_url = download_url
                            continue

                        if response.status_code not in (200, 206):
                            await response.aread()
                            logger.warning(
                                "Yandex API download | HTTP %s | %s",
                                response.status_code,
                                description,
                            )
                            return False

                        total_size = int(response.headers.get("content-length", 0))
                        cr = response.headers.get("content-range")
                        if response.status_code == 206 and cr and "/" in cr:
                            try:
                                total_size = int(cr.split("/")[-1])
                            except ValueError:
                                pass
                        if total_size == 0 and expected_size:
                            total_size = expected_size

                        mode = "ab" if response.status_code == 206 else "wb"
                        if mode == "wb" and target_path.exists():
                            target_path.unlink()
                        write_base = downloaded if mode == "ab" else 0

                        with target_path.open(mode) as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                f.write(chunk)
                                write_base += len(chunk)

                        ref = total_size if total_size else expected_size
                        if not self._validate_file(target_path, expected_size, ref, source_name=source_name):
                            if target_path.exists():
                                target_path.unlink()
                            return False
                        logger.info("Downloaded %.1f MB", write_base / (1024 * 1024))
                        return True

                logger.warning("Yandex API download | too many redirects | %s", description)
                return False
        except httpx.HTTPStatusError as e:
            logger.warning("Yandex API download | %s | HTTP %s", description, e.response.status_code)
            if target_path.exists():
                target_path.unlink()
            return False
        except Exception as e:
            logger.warning("Yandex API download | %s | %s", description, e)
            if target_path.exists():
                target_path.unlink()
            return False

    async def download(
        self,
        recording_id: int,
        source_meta: dict[str, Any],
        force: bool = False,
    ) -> DownloadResult:
        """Download video from Yandex Disk (API or public link) to storage."""
        from config.settings import get_settings
        from file_storage.factory import get_storage_backend
        from utils.pipeline_video_formats import (
            pipeline_ingress_suffixes_from_settings_formats,
            strict_suffix_from_source_name,
        )
        from yandex_disk_module.client import YandexDiskClient

        allowed_suffixes = pipeline_ingress_suffixes_from_settings_formats(
            get_settings().storage.supported_video_formats
        )
        try:
            source_suffix = strict_suffix_from_source_name(source_meta.get("name"), allowed_suffixes)
        except ValueError as exc:
            raise RuntimeError(f"Ingress rejected for Yandex file: {exc}") from exc

        target_key = self._get_target_key(recording_id, source_suffix=source_suffix)
        storage_backend = get_storage_backend()

        # Skip if already committed and not forced
        if not force and await storage_backend.exists(target_key):
            existing_size = await storage_backend.get_size(target_key)
            if existing_size > 1024:
                return DownloadResult(storage_key=target_key, file_size=existing_size)

        # Stream into a local temp file; the internal Yandex helpers below all write to this Path
        # (with their own resume / fallback logic). On success we move it into storage.
        target_path = self._new_temp_path(source_suffix)

        download_method = source_meta.get("download_method", "api")
        oauth_token = self.oauth_token or source_meta.get("oauth_token")

        # Public shares: always use anonymous API for the download href. Passing OAuth here
        # can yield a different short-lived URL that then 403s from CDN for our client.
        api_client = (
            YandexDiskClient(oauth_token=None)
            if download_method == "public"
            else YandexDiskClient(oauth_token=oauth_token)
        )

        # Get temporary download URL from Yandex Disk API
        if download_method == "public":
            public_key = source_meta.get("public_key", "")
            file_path = source_meta.get("path")
            download_url = await api_client.get_public_download_url(public_key, path=file_path)
        else:
            file_path = source_meta.get("path", "")
            if not file_path:
                raise ValueError("No file path in source metadata for Yandex Disk download")
            download_url = await api_client.get_download_url(file_path)

        logger.info(f"Downloading from Yandex Disk: {source_meta.get('name', file_path)}")

        desc = f"Yandex Disk file: {source_meta.get('name', 'unknown')}"
        pk_url = (source_meta.get("public_key") or "").strip()
        success = False
        if download_method == "public" and pk_url.startswith("http"):
            success = await self._download_yandex_public_unified(
                pk_url,
                source_meta,
                download_url,
                target_path,
                source_meta.get("size"),
                desc,
            )

        if not success and download_method == "public":
            # Fallback: separate requests (e.g. unified path got no store)
            share_cookies, share_html = {}, ""
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(45.0, connect=20.0),
                    follow_redirects=True,
                ) as _c:
                    _r = await _c.get(pk_url.split("#", 1)[0], headers={"User-Agent": _YANDEX_BROWSER_UA})
                    share_cookies = dict(_r.cookies)
                    share_html = _r.text
            except Exception as e:
                logger.warning(f"Yandex public fallback page load | {e!s}")

            web_download_url: str | None = None
            store = _parse_yandex_store_prefetch(share_html)
            if store:
                raw_env = store.get("environment")
                env = raw_env if isinstance(raw_env, dict) else {}
                sk = env.get("sk")
                if sk:
                    rhash = _public_resource_hash_for_file(store, source_meta)
                    if rhash:
                        async with httpx.AsyncClient(
                            timeout=httpx.Timeout(45.0, connect=20.0),
                            follow_redirects=True,
                        ) as pc:
                            web_download_url = await _yandex_web_public_download_url(pc, pk_url, rhash, str(sk))

            download_urls = [download_url]
            if web_download_url and web_download_url != download_url:
                download_urls.append(web_download_url)
            cookie_sets: list[dict[str, str] | None] = [share_cookies] if share_cookies else []
            cookie_sets.append(None)
            for file_url in download_urls:
                for cookie_jar in cookie_sets:
                    for hdr in _yandex_disk_cdn_header_strategies(source_meta):
                        success = await self._download_url(
                            url=file_url,
                            filepath=target_path,
                            headers=hdr,
                            cookies=cookie_jar,
                            max_retries=2,
                            expected_size=source_meta.get("size"),
                            description=desc,
                            source_name=source_meta.get("name"),
                        )
                        if success:
                            break
                    if success:
                        break
                if success:
                    break

        elif not success:
            if download_method == "public":
                for hdr in _yandex_disk_cdn_header_strategies(source_meta):
                    success = await self._download_url(
                        url=download_url,
                        filepath=target_path,
                        headers=hdr,
                        max_retries=10,
                        expected_size=source_meta.get("size"),
                        description=desc,
                        source_name=source_meta.get("name"),
                    )
                    if success:
                        break
            else:
                if not oauth_token:
                    logger.warning(
                        "Yandex API download | oauth_token missing — check input source credential | %s",
                        desc,
                    )
                success = await self._download_yandex_api_href(
                    download_url,
                    target_path,
                    oauth_token,
                    source_meta.get("size"),
                    desc,
                    source_name=source_meta.get("name"),
                )

        try:
            if not success:
                raise RuntimeError(f"Failed to download from Yandex Disk: {source_meta.get('name', file_path)}")

            size = await self._commit_temp_to_storage(target_path, target_key)
            return DownloadResult(
                storage_key=target_key,
                file_size=size,
                metadata={
                    "name": source_meta.get("name"),
                    "path": file_path,
                    "download_method": download_method,
                },
            )
        finally:
            # Belt-and-suspenders: the commit consumes the temp; this clears partial files
            # left by the failure path.
            if target_path.exists():
                target_path.unlink(missing_ok=True)
