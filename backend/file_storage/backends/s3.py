"""S3-compatible object storage backend (AWS S3, Yandex Object Storage, MinIO)."""

from pathlib import Path

import aioboto3
from botocore.exceptions import ClientError

from file_storage.backends.base import StorageBackend
from logger import get_logger

logger = get_logger(__name__)


class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend.

    Works with AWS S3, Yandex Object Storage, MinIO, and any other S3-compatible
    service. Set ``endpoint_url`` for non-AWS providers (e.g.
    ``https://storage.yandexcloud.net`` for Yandex Cloud).

    Keys are stored under an optional ``prefix`` (e.g. ``storage/users/...``).
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ):
        if not bucket:
            raise ValueError("S3StorageBackend: bucket is required")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self._session = aioboto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

    def _key(self, path: str) -> str:
        """Build the full S3 key from a logical path."""
        path = str(path).lstrip("/")
        return f"{self.prefix}/{path}" if self.prefix else path

    def _client(self):
        """Return an async S3 client context manager."""
        return self._session.client("s3", endpoint_url=self.endpoint_url)

    async def save(self, path: str, content: bytes) -> str:
        key = self._key(path)
        async with self._client() as s3:
            await s3.put_object(Bucket=self.bucket, Key=key, Body=content)
        return path

    async def load(self, path: str) -> bytes:
        key = self._key(path)
        async with self._client() as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=key)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    raise FileNotFoundError(f"S3 key not found: {key}") from e
                raise
            return await response["Body"].read()

    async def delete(self, path: str) -> bool:
        key = self._key(path)
        async with self._client() as s3:
            # Check existence first so we return False for missing keys.
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    return False
                raise
            await s3.delete_object(Bucket=self.bucket, Key=key)
            return True

    async def exists(self, path: str) -> bool:
        key = self._key(path)
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    return False
                raise

    async def get_size(self, path: str) -> int:
        key = self._key(path)
        async with self._client() as s3:
            try:
                response = await s3.head_object(Bucket=self.bucket, Key=key)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    raise FileNotFoundError(f"S3 key not found: {key}") from e
                raise
            return int(response["ContentLength"])

    async def save_file(self, path: str, local_path: Path) -> str:
        """Upload a local file using multipart (automatic for large files)."""
        key = self._key(path)
        async with self._client() as s3:
            await s3.upload_file(str(local_path), self.bucket, key)
        return path

    async def download_to_file(self, path: str, local_path: Path) -> None:
        """Download via streaming multipart download."""
        key = self._key(path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._client() as s3:
            try:
                await s3.download_file(self.bucket, key, str(local_path))
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    raise FileNotFoundError(f"S3 key not found: {key}") from e
                raise

    async def presigned_url(self, path: str, expires_in: int = 3600) -> str:
        """Generate a time-limited GET URL for direct browser access."""
        key = self._key(path)
        async with self._client() as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )

    async def list_keys(self, prefix: str) -> list[str]:
        """List logical keys under ``prefix`` (without the bucket prefix part)."""
        full_prefix = self._key(prefix)
        keys: list[str] = []
        prefix_strip = f"{self.prefix}/" if self.prefix else ""

        async with self._client() as s3:
            continuation_token: str | None = None
            while True:
                params = {"Bucket": self.bucket, "Prefix": full_prefix}
                if continuation_token:
                    params["ContinuationToken"] = continuation_token
                response = await s3.list_objects_v2(**params)
                for obj in response.get("Contents", []):
                    full_key = obj["Key"]
                    if prefix_strip and full_key.startswith(prefix_strip):
                        keys.append(full_key[len(prefix_strip) :])
                    else:
                        keys.append(full_key)
                if not response.get("IsTruncated"):
                    break
                continuation_token = response.get("NextContinuationToken")
        return keys
