"""Yandex Disk REST API client for file listing, download, and upload."""

import re
from pathlib import Path
from typing import Any

import httpx

from config.settings import storage_video_ingress_suffixes
from logger import format_details, get_logger

logger = get_logger(__name__)

BASE_URL = "https://cloud-api.yandex.net/v1/disk"
YANDEX_DISK_REST_LIST_FOLDER_ITEM_FIELDS: str = (
    "_embedded.items.name,_embedded.items.path,_embedded.items.type,"
    "_embedded.items.size,_embedded.items.modified,_embedded.items.created,"
    "_embedded.items.md5,_embedded.items.mime_type,_embedded.items.resource_id"
)

_VIDEO_MIME_TYPE_PREFIXES = ("video/",)


class YandexDiskError(Exception):
    """Yandex Disk API error (see https://yandex.ru/dev/disk-api/doc/ru/reference/response-objects#error)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        description: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.description = description


class YandexDiskClient:
    """Client for Yandex Disk REST API (https://yandex.ru/dev/disk/rest)."""

    def __init__(self, oauth_token: str | None = None):
        self.oauth_token = oauth_token

    def _json_headers(self) -> dict[str, str]:
        """Disk API expects JSON Accept/Content-Type for REST calls."""
        h: dict[str, str] = {"Accept": "application/json"}
        if self.oauth_token:
            h["Authorization"] = f"OAuth {self.oauth_token}"
        return h

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
        merged = {**self._json_headers(), **headers}

        async with self._build_client() as client:
            response = await client.request(method, url, headers=merged, **kwargs)

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    msg = error_data.get("message", error_data.get("description", response.text))
                    err = error_data.get("error")
                    desc = error_data.get("description")
                except Exception:
                    msg = response.text
                    err = None
                    desc = None
                raise YandexDiskError(
                    f"Yandex Disk API error: {msg}",
                    response.status_code,
                    error_code=err,
                    description=desc if isinstance(desc, str) else None,
                )

            if response.status_code == 204:
                return {}
            if not response.content:
                return {}
            return response.json()

    # --- Disk / resource metadata ---

    async def get_disk_info(self) -> dict[str, Any]:
        """Return user disk quota and profile (GET /v1/disk). Requires OAuth."""
        return await self._request("GET", BASE_URL)

    async def get_resource_meta(self, path: str) -> dict[str, Any]:
        """Metadata for a file or folder (GET /v1/disk/resources). Requires OAuth."""
        return await self._request("GET", f"{BASE_URL}/resources", params={"path": path})

    async def move_resource(self, from_path: str, to_path: str, *, overwrite: bool = False) -> dict[str, Any]:
        """Move or rename a resource (POST /v1/disk/resources/move). Requires OAuth."""
        return await self._request(
            "POST",
            f"{BASE_URL}/resources/move",
            params={"from": from_path, "path": to_path, "overwrite": str(overwrite).lower()},
        )

    async def delete_resource(self, path: str, *, permanently: bool = False) -> None:
        """Delete file or folder (DELETE /v1/disk/resources). Requires OAuth."""
        await self._request(
            "DELETE",
            f"{BASE_URL}/resources",
            params={"path": path, "permanently": str(permanently).lower()},
        )

    async def publish_resource(self, path: str) -> str:
        """Publish resource and return public_url (PUT publish, then read meta). Requires OAuth."""
        await self._request("PUT", f"{BASE_URL}/resources/publish", params={"path": path})
        meta = await self.get_resource_meta(path)
        public_url = meta.get("public_url")
        if not public_url:
            raise YandexDiskError(
                f"Publish succeeded but public_url missing for path: {path}",
                None,
                error_code="MissingPublicUrl",
            )
        return str(public_url)

    async def unpublish_resource(self, path: str) -> None:
        """Revoke public access (PUT /v1/disk/resources/unpublish). Requires OAuth."""
        await self._request("PUT", f"{BASE_URL}/resources/unpublish", params={"path": path})

    # --- Folder listing ---

    async def list_folder(
        self,
        path: str,
        limit: int = 100,
        offset: int = 0,
        *,
        fields: str | None = YANDEX_DISK_REST_LIST_FOLDER_ITEM_FIELDS,
    ) -> dict[str, Any]:
        """List resources in a folder. Requires OAuth token.

        GET /v1/disk/resources?path=<path>&limit=<limit>&offset=<offset>

        ``fields`` defaults to :data:`YANDEX_DISK_REST_LIST_FOLDER_ITEM_FIELDS` so each
        listed file includes ``md5`` / ``resource_id`` where the API provides them.
        Pass ``fields=""`` or ``None`` to omit the parameter (full/default server shape).
        """
        params: dict[str, str | int] = {"path": path, "limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields
        return await self._request(
            "GET",
            f"{BASE_URL}/resources",
            params=params,
        )

    async def list_published_resources(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        fields: str | None = None,
    ) -> dict[str, Any]:
        """List files/folders you published (created a public link for).

        GET /v1/disk/resources/public?limit=&offset=&fields=

        This is **not** the same as Yandex 360 «shared folder» invitations: it only returns
        resources for which a public URL was enabled. Anonymous access to those URLs uses
        :meth:`get_public_meta` / ``GET /v1/disk/public/resources``.

        ``fields`` is optional; omit it unless you need a sparse document (parameter shape
        differs from :meth:`list_folder`).
        """
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields
        return await self._request("GET", f"{BASE_URL}/resources/public", params=params)

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

    async def get_public_meta(
        self,
        public_key: str,
        path: str | None = None,
        limit: int = 100,
        offset: int = 0,
        *,
        fields: str | None = None,
    ) -> dict[str, Any]:
        """Get meta information of a public resource (supports pagination, nested path).

        GET /v1/disk/public/resources?public_key=<key>&path=<path>&limit=&offset=
        """
        params: dict[str, str | int] = {
            "public_key": public_key,
            "limit": limit,
            "offset": offset,
        }
        if path:
            params["path"] = path
        if fields:
            params["fields"] = fields
        return await self._request("GET", f"{BASE_URL}/public/resources", params=params)

    async def list_public_video_files(
        self,
        public_key: str,
        file_pattern: str | None = None,
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        """List video files from a public resource (file or folder)."""
        meta = await self.get_public_meta(public_key)

        if meta.get("type") == "file":
            if self._is_video_file(meta, file_pattern):
                return [meta]
            return []

        video_files: list[dict[str, Any]] = []
        await self._collect_public_video_files(
            public_key=public_key,
            path=None,
            recursive=recursive,
            file_pattern=file_pattern,
            result=video_files,
        )
        logger.info(f"Found {len(video_files)} video files in public resource")
        return video_files

    async def _collect_public_video_files(
        self,
        public_key: str,
        path: str | None,
        recursive: bool,
        file_pattern: str | None,
        result: list[dict[str, Any]],
    ) -> None:
        """Collect video files from a public folder with pagination and optional recursion."""
        offset = 0
        limit = 100

        while True:
            meta = await self.get_public_meta(public_key, path=path, limit=limit, offset=offset)
            embedded = meta.get("_embedded", {})
            items = embedded.get("items", [])

            for item in items:
                if item.get("type") == "dir" and recursive:
                    await self._collect_public_video_files(public_key, item["path"], recursive, file_pattern, result)
                elif item.get("type") == "file" and self._is_video_file(item, file_pattern):
                    result.append(item)

            total = embedded.get("total", 0)
            offset += limit
            if offset >= total:
                break

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
        is_video = any(mime_type.startswith(prefix) for prefix in _VIDEO_MIME_TYPE_PREFIXES)

        # Fallback to extension check
        if not is_video:
            ext = Path(name).suffix.lower()
            is_video = ext in storage_video_ingress_suffixes()

        if not is_video:
            return False

        # Apply file_pattern filter if specified
        if file_pattern:
            try:
                if not re.search(file_pattern, name, re.IGNORECASE):
                    return False
            except re.error as e:
                logger.warning(f"Invalid regex pattern | {format_details(pattern=file_pattern, error=str(e))}")
                return False

        return True
