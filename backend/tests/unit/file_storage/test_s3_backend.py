"""Unit tests for S3StorageBackend using a real moto HTTP server.

moto's in-process mock_aws is incompatible with aioboto3's chunked-encoding
upload path (sync vs async stream handling). We work around this by running a
ThreadedMotoServer on a local port and pointing the backend at it via
``endpoint_url`` — the same mechanism we'll use for MinIO and Yandex Cloud.
"""

import socket

import boto3
import pytest
from moto.server import ThreadedMotoServer

from file_storage.backends.s3 import S3StorageBackend

BUCKET = "leap-test-bucket"
REGION = "us-east-1"


def _free_port() -> int:
    """Allocate an unused TCP port on localhost."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def moto_endpoint():
    """Start a ThreadedMotoServer for the test module lifetime."""
    port = _free_port()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Isolate from any local ~/.aws/credentials on the dev machine."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/tmp/__nonexistent_aws_creds__")
    monkeypatch.setenv("AWS_CONFIG_FILE", "/tmp/__nonexistent_aws_config__")


@pytest.fixture
def s3_bucket(moto_endpoint):
    """Create a fresh bucket on the moto server and clean it up after the test."""
    client = boto3.client(
        "s3",
        region_name=REGION,
        endpoint_url=moto_endpoint,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    try:
        client.create_bucket(Bucket=BUCKET)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass

    yield BUCKET

    # Cleanup: delete all objects so the next test starts clean.
    response = client.list_objects_v2(Bucket=BUCKET)
    for obj in response.get("Contents", []):
        client.delete_object(Bucket=BUCKET, Key=obj["Key"])


@pytest.fixture
def backend(s3_bucket, moto_endpoint):
    return S3StorageBackend(
        bucket=s3_bucket,
        prefix="storage",
        region=REGION,
        access_key_id="testing",
        secret_access_key="testing",
        endpoint_url=moto_endpoint,
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestS3StorageBackend:
    """Tests for S3StorageBackend covering all CRUD ops and streaming."""

    async def test_init_requires_bucket(self):
        with pytest.raises(ValueError):
            S3StorageBackend(bucket="")

    async def test_save_and_load(self, backend):
        await backend.save("users/000001/test.json", b'{"k": "v"}')
        assert await backend.load("users/000001/test.json") == b'{"k": "v"}'

    async def test_exists(self, backend):
        assert not await backend.exists("missing.txt")
        await backend.save("there.txt", b"hi")
        assert await backend.exists("there.txt")

    async def test_get_size(self, backend):
        await backend.save("size.bin", b"123456789")
        assert await backend.get_size("size.bin") == 9

    async def test_get_size_missing(self, backend):
        with pytest.raises(FileNotFoundError):
            await backend.get_size("nope.bin")

    async def test_load_missing(self, backend):
        with pytest.raises(FileNotFoundError):
            await backend.load("nope.bin")

    async def test_delete(self, backend):
        await backend.save("kill.me", b"x")
        assert await backend.delete("kill.me") is True
        assert await backend.delete("kill.me") is False

    async def test_save_file_uploads(self, backend, tmp_path):
        src = tmp_path / "source.mp4"
        src.write_bytes(b"video bytes here")
        await backend.save_file("users/000001/video.mp4", src)
        assert await backend.exists("users/000001/video.mp4")
        assert await backend.load("users/000001/video.mp4") == b"video bytes here"

    async def test_download_to_file(self, backend, tmp_path):
        await backend.save("users/000001/audio.mp3", b"audio bytes")
        dst = tmp_path / "out" / "audio.mp3"
        await backend.download_to_file("users/000001/audio.mp3", dst)
        assert dst.read_bytes() == b"audio bytes"

    async def test_download_to_file_missing(self, backend, tmp_path):
        with pytest.raises(FileNotFoundError):
            await backend.download_to_file("missing.bin", tmp_path / "out.bin")

    async def test_presigned_url(self, backend):
        await backend.save("public.txt", b"hello")
        url = await backend.presigned_url("public.txt", expires_in=600)
        assert url.startswith(("https://", "http://"))
        assert "public.txt" in url
        assert "X-Amz-Signature" in url or "Signature" in url

    async def test_prefix_namespacing(self, s3_bucket, moto_endpoint):
        """The configured prefix should be applied to all keys."""
        backend = S3StorageBackend(
            bucket=s3_bucket,
            prefix="custom/root",
            region=REGION,
            access_key_id="testing",
            secret_access_key="testing",
            endpoint_url=moto_endpoint,
        )
        await backend.save("a/b.txt", b"data")

        client = boto3.client(
            "s3",
            region_name=REGION,
            endpoint_url=moto_endpoint,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        response = client.list_objects_v2(Bucket=s3_bucket)
        keys = [obj["Key"] for obj in response.get("Contents", [])]
        assert "custom/root/a/b.txt" in keys

    async def test_no_prefix(self, s3_bucket, moto_endpoint):
        """Empty prefix should write at bucket root."""
        backend = S3StorageBackend(
            bucket=s3_bucket,
            prefix="",
            region=REGION,
            access_key_id="testing",
            secret_access_key="testing",
            endpoint_url=moto_endpoint,
        )
        await backend.save("root_a/b.txt", b"data")

        client = boto3.client(
            "s3",
            region_name=REGION,
            endpoint_url=moto_endpoint,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        response = client.list_objects_v2(Bucket=s3_bucket)
        keys = [obj["Key"] for obj in response.get("Contents", [])]
        assert "root_a/b.txt" in keys
