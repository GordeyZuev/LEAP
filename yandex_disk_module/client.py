"""Yandex Disk REST API client for file listing, download, and upload."""

import re
from pathlib import Path
from typing import Any

import httpx

from logger import get_logger

logger = get_logger()

# Video file extensions for filtering
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts"}
_VIDEO_MIME_PREFIXES = ("video/",)

BASE_URL = "https://cloud-api.yandex.net/v1/disk"


class YandexDiskError(Exception):
    """Yandex Disk API error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class YandexDiskClient:
    """Client for Yandex Disk REST API (https://yandex.ru/dev/disk/rest)."""

    def __init__(self, oauth_token: str | None = None):
        self.oauth_token = oauth_token

    def _auth_headers(self) -> dict[str, str]:
        if not self.oauth_token:
            return {}
        return {"Authorization": f"OAuth {self.oauth_token}"}

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=60.0, connect=15.0, read=30.0),
            follow_redirects=True,
        )

    async def _request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        """Make an authenticated API request."""
        headers = kwargs.pop("headers", {})
        headers.update(self._auth_headers())

        async with self._build_client() as client:
            response = await client.request(method, url, headers=headers, **kwargs)

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    msg = error_data.get("message", error_data.get("description", response.text))
                except Exception:
                    msg = response.text
                raise YandexDiskError(f"Yandex Disk API error: {msg}", response.status_code)

            if response.status_code == 204:
                return {}
            return response.json()

    # --- Folder listing ---

    async def list_folder(
        self,
        path: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List resources in a folder. Requires OAuth token.

        GET /v1/disk/resources?path=<path>&limit=<limit>&offset=<offset>
        """
        return await self._request(
            "GET",
            f"{BASE_URL}/resources",
            params={"path": path, "limit": limit, "offset": offset},
        )

    async def list_video_files(
        self,
        folder_path: str,
        recursive: bool = True,
        file_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """List video files in a folder, optionally recursive."""
        video_files: list[dict[str, Any]] = []
        await self._collect_video_files(folder_path, recursive, file_pattern, video_files)
        logger.info(f"Found {len(video_files)} video files in {folder_path}")
        return video_files

    async def _collect_video_files(
        self,
        folder_path: str,
        recursive: bool,
        file_pattern: str | None,
        result: list[dict[str, Any]],
    ) -> None:
        """Recursively collect video files from folder."""
        offset = 0
        limit = 100

        while True:
            data = await self.list_folder(folder_path, limit=limit, offset=offset)
            embedded = data.get("_embedded", {})
            items = embedded.get("items", [])

            for item in items:
                if item.get("type") == "dir" and recursive:
                    await self._collect_video_files(item["path"], recursive, file_pattern, result)
                elif item.get("type") == "file" and self._is_video_file(item, file_pattern):
                    result.append(item)

            total = embedded.get("total", 0)
            offset += limit
            if offset >= total:
                break

    # --- Public resource listing ---

    async def get_public_meta(self, public_key: str) -> dict[str, Any]:
        """Get meta information of a public resource.

        GET /v1/disk/public/resources?public_key=<key>
        """
        return await self._request(
            "GET",
            f"{BASE_URL}/public/resources",
            params={"public_key": public_key, "limit": 100},
        )

    async def list_public_video_files(
        self,
        public_key: str,
        file_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """List video files from a public resource (file or folder)."""
        meta = await self.get_public_meta(public_key)

        if meta.get("type") == "file":
            if self._is_video_file(meta, file_pattern):
                return [meta]
            return []

        # It's a folder -- collect video files from _embedded.items
        video_files: list[dict[str, Any]] = []
        embedded = meta.get("_embedded", {})
        for item in embedded.get("items", []):
            if item.get("type") == "file" and self._is_video_file(item, file_pattern):
                video_files.append(item)

        logger.info(f"Found {len(video_files)} video files in public resource")
        return video_files

    # --- Download ---

    async def get_download_url(self, path: str) -> str:
        """Get temporary download URL for a file on user's Disk. Requires OAuth.

        GET /v1/disk/resources/download?path=<path>
        """
        data = await self._request(
            "GET",
            f"{BASE_URL}/resources/download",
            params={"path": path},
        )
        href = data.get("href")
        if not href:
            raise YandexDiskError(f"No download URL returned for path: {path}")
        return href

    async def get_public_download_url(self, public_key: str, path: str | None = None) -> str:
        """Get temporary download URL for a public file. No OAuth required.

        GET /v1/disk/public/resources/download?public_key=<key>&path=<path>
        """
        params: dict[str, str] = {"public_key": public_key}
        if path:
            params["path"] = path

        data = await self._request(
            "GET",
            f"{BASE_URL}/public/resources/download",
            params=params,
        )
        href = data.get("href")
        if not href:
            raise YandexDiskError(f"No download URL returned for public key: {public_key}")
        return href

    # --- Upload ---

    async def get_upload_url(self, path: str, overwrite: bool = False) -> str:
        """Get temporary upload URL. Requires OAuth.

        GET /v1/disk/resources/upload?path=<path>&overwrite=<true/false>
        """
        data = await self._request(
            "GET",
            f"{BASE_URL}/resources/upload",
            params={"path": path, "overwrite": str(overwrite).lower()},
        )
        href = data.get("href")
        if not href:
            raise YandexDiskError(f"No upload URL returned for path: {path}")
        return href

    async def create_folder(self, path: str) -> None:
        """Create a folder on Disk. Requires OAuth.

        PUT /v1/disk/resources?path=<path>
        """
        try:
            await self._request("PUT", f"{BASE_URL}/resources", params={"path": path})
        except YandexDiskError as e:
            # 409 = folder already exists
            if e.status_code == 409:
                return
            raise

    async def upload_file(
        self,
        local_path: Path,
        disk_path: str,
        overwrite: bool = False,
    ) -> bool:
        """Upload a local file to Yandex Disk (two-step: get URL, then PUT)."""
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        # Ensure parent folder exists
        parent_dir = str(Path(disk_path).parent)
        if parent_dir and parent_dir != ".":
            await self._ensure_folder_exists(parent_dir)

        upload_url = await self.get_upload_url(disk_path, overwrite=overwrite)

        logger.info(f"Uploading {local_path.name} to {disk_path}")

        async with self._build_client() as client:
            with local_path.open("rb") as f:
                response = await client.put(upload_url, content=f)

            if response.status_code in (201, 202):
                logger.info(f"Uploaded {local_path.name} to {disk_path}")
                return True

            raise YandexDiskError(
                f"Upload failed with status {response.status_code}: {response.text}",
                response.status_code,
            )

    async def _ensure_folder_exists(self, path: str) -> None:
        """Create folder and all parent folders if needed."""
        parts = Path(path).parts
        current = ""
        for part in parts:
            # Skip the root "/" from Path.parts on Unix
            if part == "/":
                continue
            current = f"{current}/{part}"
            await self.create_folder(current)

    # --- Helpers ---

    @staticmethod
    def _is_video_file(item: dict[str, Any], file_pattern: str | None = None) -> bool:
        """Check if a Disk resource item is a video file."""
        name = item.get("name", "")
        mime_type = item.get("mime_type", "")

        # Check MIME type
        is_video = any(mime_type.startswith(prefix) for prefix in _VIDEO_MIME_PREFIXES)

        # Fallback to extension check
        if not is_video:
            ext = Path(name).suffix.lower()
            is_video = ext in _VIDEO_EXTENSIONS

        if not is_video:
            return False

        # Apply file_pattern filter if specified
        if file_pattern:
            try:
                if not re.search(file_pattern, name, re.IGNORECASE):
                    return False
            except re.error:
                pass

        return True
