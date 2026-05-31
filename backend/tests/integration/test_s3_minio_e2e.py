"""End-to-end integration test against a real MinIO instance.

Prerequisite: MinIO running locally on :9000.

Start MinIO:
    docker run -d --name leap_minio_dev \\
        -p 9000:9000 -p 9001:9001 \\
        -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \\
        minio/minio:latest server /data --console-address ":9001"

Run only this file:
    uv run pytest tests/integration/test_s3_minio_e2e.py -v --no-cov

Verifies the full S3 backend code path (real HTTP, real multipart upload, real
presigned URL signing) — moto can't catch protocol-level regressions because it
intercepts at the boto3 client layer.
"""

import socket

import boto3
import pytest

from file_storage.backends.s3 import S3StorageBackend

MINIO_ENDPOINT = "http://localhost:9000"
MINIO_USER = "minioadmin"
MINIO_PASSWORD = "minioadmin"
BUCKET = "leap-test-e2e"


def _minio_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 9000), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _minio_reachable(),
    reason="MinIO not running on localhost:9000 — start it via docker before running this test",
)


@pytest.fixture(autouse=True)
def _isolate_aws_env(monkeypatch):
    """Prevent botocore from parsing a possibly-malformed ~/.aws/credentials on dev machines."""
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/tmp/__nonexistent_aws_creds_e2e__")
    monkeypatch.setenv("AWS_CONFIG_FILE", "/tmp/__nonexistent_aws_config_e2e__")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", MINIO_USER)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", MINIO_PASSWORD)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(scope="module")
def minio_bucket():
    """Ensure the test bucket exists and is empty at module start."""
    import os

    # Isolate at module level too (autouse fixture above is function-scoped).
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = "/tmp/__nonexistent_aws_creds_e2e__"
    os.environ["AWS_CONFIG_FILE"] = "/tmp/__nonexistent_aws_config_e2e__"

    client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_USER,
        aws_secret_access_key=MINIO_PASSWORD,
        region_name="us-east-1",
    )
    try:
        client.create_bucket(Bucket=BUCKET)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass
    except client.exceptions.BucketAlreadyExists:
        pass

    # Wipe any leftovers from a previous run.
    response = client.list_objects_v2(Bucket=BUCKET)
    for obj in response.get("Contents", []):
        client.delete_object(Bucket=BUCKET, Key=obj["Key"])

    yield BUCKET

    # Final cleanup so a re-run is hermetic.
    response = client.list_objects_v2(Bucket=BUCKET)
    for obj in response.get("Contents", []):
        client.delete_object(Bucket=BUCKET, Key=obj["Key"])


@pytest.fixture
def backend(minio_bucket):
    return S3StorageBackend(
        bucket=minio_bucket,
        prefix="storage",
        region="us-east-1",
        access_key_id=MINIO_USER,
        secret_access_key=MINIO_PASSWORD,
        endpoint_url=MINIO_ENDPOINT,
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestS3MinIOEndToEnd:
    """Real MinIO smoke tests for S3StorageBackend."""

    async def test_save_load_round_trip(self, backend):
        await backend.save("users/000001/test.json", b'{"hello": "world"}')
        assert await backend.load("users/000001/test.json") == b'{"hello": "world"}'

    async def test_exists_get_size(self, backend):
        await backend.save("size_test.bin", b"x" * 12345)
        assert await backend.exists("size_test.bin")
        assert await backend.get_size("size_test.bin") == 12345

    async def test_delete(self, backend):
        await backend.save("doomed.txt", b"goodbye")
        assert await backend.delete("doomed.txt") is True
        assert await backend.delete("doomed.txt") is False

    async def test_save_file_upload(self, backend, tmp_path):
        """upload_file path with multipart support (auto for >8MB; we test small file)."""
        src = tmp_path / "local.mp4"
        src.write_bytes(b"VIDEO" * 1024)  # 5 KB

        await backend.save_file("users/000001/recordings/42/video.mp4", src)

        assert await backend.exists("users/000001/recordings/42/video.mp4")
        # Round-trip verifies bytes match
        loaded = await backend.load("users/000001/recordings/42/video.mp4")
        assert loaded == b"VIDEO" * 1024

    async def test_save_file_large_multipart(self, backend, tmp_path):
        """Multipart kicks in around 8 MB — verify with a 12 MB file."""
        src = tmp_path / "big.mp4"
        size = 12 * 1024 * 1024
        with src.open("wb") as f:
            f.write(b"\x00" * size)

        await backend.save_file("users/000001/recordings/42/big.mp4", src)

        assert await backend.exists("users/000001/recordings/42/big.mp4")
        assert await backend.get_size("users/000001/recordings/42/big.mp4") == size

    async def test_download_to_file(self, backend, tmp_path):
        await backend.save("users/000001/audio.mp3", b"audio bytes here")
        dst = tmp_path / "downloaded.mp3"
        await backend.download_to_file("users/000001/audio.mp3", dst)
        assert dst.read_bytes() == b"audio bytes here"

    async def test_download_to_file_missing(self, backend, tmp_path):
        with pytest.raises(FileNotFoundError):
            await backend.download_to_file("nope.bin", tmp_path / "x.bin")

    async def test_presigned_url_actually_downloads(self, backend):
        """A presigned URL must be retrievable with an unauthenticated HTTP GET."""
        import httpx

        await backend.save("users/000001/public.txt", b"streamed via presign")
        url = await backend.presigned_url("users/000001/public.txt", expires_in=600)

        # No auth header — relying purely on the URL signature.
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        assert response.status_code == 200
        assert response.content == b"streamed via presign"

    async def test_list_keys_with_pagination(self, backend):
        # Write enough objects to verify pagination still returns all of them.
        for i in range(15):
            await backend.save(f"users/000001/list/file_{i:03d}.bin", f"#{i}".encode())

        keys = await backend.list_keys("users/000001/list")
        names = sorted(k.rsplit("/", 1)[-1] for k in keys)
        assert names == [f"file_{i:03d}.bin" for i in range(15)]


@pytest.mark.integration
@pytest.mark.asyncio
class TestPipelineComponentsWithMinIO:
    """Verify TranscriptionManager + thumbnails go through a real backend."""

    async def test_transcription_manager_round_trip(self, backend, monkeypatch):
        """Save master.json and read it back via the manager API."""
        from transcription_module.manager import TranscriptionManager

        # Point the manager at our test backend (singleton override).
        monkeypatch.setattr("transcription_module.manager.get_storage_backend", lambda: backend)

        manager = TranscriptionManager()
        await manager.save_master(
            recording_id=99,
            words=[{"word": "hi", "start": 0.0, "end": 0.5}],
            segments=[{"text": "hi", "start": 0.0, "end": 0.5}],
            language="ru",
            user_slug=1,
        )

        assert await manager.has_master(99, 1)
        master = await manager.load_master(99, 1)
        assert master["recording_id"] == 99
        assert master["language"] == "ru"

        files = await manager.generate_cache_files(99, 1)
        assert "segments_txt" in files and "words_txt" in files
        # Both files must actually be in storage
        assert await backend.exists(files["segments_txt"])
        assert await backend.exists(files["words_txt"])

    async def test_subtitles_from_segments(self, backend, monkeypatch):
        """End-to-end: master.json → segments.txt → SRT/VTT."""
        from subtitle_module.subtitle_generator import SubtitleGenerator
        from transcription_module.manager import TranscriptionManager

        monkeypatch.setattr("transcription_module.manager.get_storage_backend", lambda: backend)
        monkeypatch.setattr("subtitle_module.subtitle_generator.get_storage_backend", lambda: backend)

        manager = TranscriptionManager()
        await manager.save_master(
            recording_id=100,
            words=[],
            segments=[
                {"text": "Привет мир", "start": 0.0, "end": 2.0},
                {"text": "Это тест", "start": 2.0, "end": 4.0},
            ],
            language="ru",
            user_slug=1,
        )

        segments_key = await manager.ensure_segments_txt(100, 1)
        assert await backend.exists(segments_key)

        generator = SubtitleGenerator()
        result = await generator.generate_from_transcription(
            transcription_key=segments_key,
            output_dir_key=segments_key.rsplit("/", 1)[0],
            formats=["srt", "vtt"],
        )

        assert "srt" in result and "vtt" in result
        srt = (await backend.load(result["srt"])).decode("utf-8")
        vtt = (await backend.load(result["vtt"])).decode("utf-8")

        assert "00:00:00,000 --> 00:00:02,000" in srt
        assert "Привет мир" in srt
        assert vtt.startswith("WEBVTT")
        assert "00:00:00.000 --> 00:00:02.000" in vtt


@pytest.mark.integration
@pytest.mark.asyncio
async def test_legacy_storage_prefix_compat(backend):
    """Backend should treat ``storage/...`` keys (legacy DB rows) as bare keys.

    Our S3 backend doesn't auto-strip ``storage/`` (that's a LOCAL-only concern),
    so legacy DB rows must be normalized through ``to_storage_key`` before they
    reach the backend. This test documents the expected boundary.
    """
    from file_storage.path_builder import to_storage_key

    legacy_path = "storage/users/000001/recordings/42/source.mp4"
    key = to_storage_key(legacy_path)
    assert key == "users/000001/recordings/42/source.mp4"

    await backend.save(key, b"OK")
    assert await backend.exists(key)
