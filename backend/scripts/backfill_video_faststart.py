#!/usr/bin/env python3
"""Repair existing MP4 objects for Safari: MIME type and moov-before-mdat.

Dry-run is the default. ``--apply``:

- Sets ``Content-Type: video/mp4`` in place when HEAD is missing or octet-stream
  (processed and original keys).
- For processed files that are not already ``*.faststart.mp4``, remuxes when
  ``moov`` is after ``mdat``, uploads a new object, and switches
  ``processed_video_path``. The old object is retained for rollback.

Canary first, then the rest::

    uv run python scripts/backfill_video_faststart.py
    uv run python scripts/backfill_video_faststart.py --apply --recording-id 38
    uv run python scripts/backfill_video_faststart.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from botocore.exceptions import ClientError
from sqlalchemy import select, update

from api.dependencies import get_async_session_maker
from database.automation_models import AutomationJobModel  # noqa: F401 — UserModel.relationship
from database.models import RecordingModel
from file_storage.backends.s3 import S3StorageBackend
from file_storage.factory import get_storage_backend

VIDEO_MP4 = "video/mp4"


def faststart_key(key: str) -> str:
    path = Path(key)
    return str(path.with_name(f"{path.stem}.faststart{path.suffix}"))


def needs_video_mp4_content_type(content_type: str | None) -> bool:
    if not content_type:
        return True
    return content_type.split(";", 1)[0].strip().lower() != VIDEO_MP4


def needs_faststart_remux(atoms: list[str]) -> bool:
    if "moov" not in atoms or "mdat" not in atoms:
        return True
    return atoms.index("moov") > atoms.index("mdat")


def top_level_atoms(path: Path) -> list[str]:
    atoms: list[str] = []
    with path.open("rb") as media:
        file_size = path.stat().st_size
        offset = 0
        while offset + 8 <= file_size:
            media.seek(offset)
            header = media.read(16)
            if len(header) < 8:
                break
            atom_size = int.from_bytes(header[:4], "big")
            atom_type = header[4:8].decode("ascii", errors="replace")
            header_size = 8
            if atom_size == 1:
                if len(header) < 16:
                    break
                atom_size = int.from_bytes(header[8:16], "big")
                header_size = 16
            elif atom_size == 0:
                atom_size = file_size - offset
            if atom_size < header_size or offset + atom_size > file_size:
                raise ValueError(f"Invalid MP4 atom {atom_type!r} at offset {offset}")
            atoms.append(atom_type)
            offset += atom_size
    return atoms


def remux_faststart(source: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed or is not in PATH")
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-avoid_negative_ts",
            "make_zero",
            "-y",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg faststart remux failed")
    atoms = top_level_atoms(destination)
    if needs_faststart_remux(atoms):
        raise RuntimeError(f"Faststart verification failed: top-level atoms are {atoms}")


async def _head_content_type(storage: object, path: str) -> str | None:
    if not isinstance(storage, S3StorageBackend):
        return VIDEO_MP4
    try:
        async with storage._client() as s3:
            response = await s3.head_object(Bucket=storage.bucket, Key=storage._key(path))
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise FileNotFoundError(path) from exc
        raise
    return response.get("ContentType")


async def _set_video_mp4_content_type(storage: object, path: str) -> None:
    if not isinstance(storage, S3StorageBackend):
        return
    key = storage._key(path)
    async with storage._client() as s3:
        head = await s3.head_object(Bucket=storage.bucket, Key=key)
        await s3.copy_object(
            Bucket=storage.bucket,
            Key=key,
            CopySource={"Bucket": storage.bucket, "Key": key},
            ContentType=VIDEO_MP4,
            Metadata=head.get("Metadata") or {},
            MetadataDirective="REPLACE",
        )


async def _ensure_video_mp4(storage: object, path: str, *, apply: bool) -> str:
    try:
        content_type = await _head_content_type(storage, path)
    except FileNotFoundError:
        return "missing"
    if not needs_video_mp4_content_type(content_type):
        return "ok"
    if apply:
        await _set_video_mp4_content_type(storage, path)
        return "fixed"
    return f"would-fix ({content_type or 'missing-header'})"


async def run(*, apply: bool, recording_ids: list[int] | None) -> None:
    session_factory = get_async_session_maker()
    storage = get_storage_backend()
    async with session_factory() as session:
        processed_stmt = select(RecordingModel.id, RecordingModel.processed_video_path).where(
            RecordingModel.deleted.is_(False),
            RecordingModel.processed_video_path.isnot(None),
            RecordingModel.processed_video_path.endswith(".mp4"),
        )
        original_stmt = select(RecordingModel.id, RecordingModel.local_video_path).where(
            RecordingModel.deleted.is_(False),
            RecordingModel.local_video_path.isnot(None),
            RecordingModel.local_video_path.endswith(".mp4"),
        )
        if recording_ids:
            processed_stmt = processed_stmt.where(RecordingModel.id.in_(recording_ids))
            original_stmt = original_stmt.where(RecordingModel.id.in_(recording_ids))
        processed_rows = list((await session.execute(processed_stmt.order_by(RecordingModel.id))).all())
        original_rows = list((await session.execute(original_stmt.order_by(RecordingModel.id))).all())

    remux_rows = [
        (recording_id, key) for recording_id, key in processed_rows if key and not key.endswith(".faststart.mp4")
    ]
    print(
        f"Processed={len(processed_rows)} remux-candidates={len(remux_rows)} "
        f"originals={len(original_rows)}; mode={'APPLY' if apply else 'DRY-RUN'}"
    )

    for recording_id, source_key in remux_rows:
        destination_key = faststart_key(source_key)
        try:
            if not apply:
                mime = await _ensure_video_mp4(storage, source_key, apply=False)
                print(f"recording={recording_id} processed: {source_key} mime={mime} remux->{destination_key}")
                continue

            with tempfile.TemporaryDirectory(prefix=f"leap-faststart-{recording_id}-") as directory:
                source = Path(directory) / "source.mp4"
                destination = Path(directory) / "faststart.mp4"
                await storage.download_to_file(source_key, source)
                atoms = top_level_atoms(source)
                if needs_faststart_remux(atoms):
                    await asyncio.to_thread(remux_faststart, source, destination)
                    await storage.save_file(destination_key, destination)
                    if await storage.get_size(destination_key) <= 0:
                        raise RuntimeError(f"Uploaded object is empty: {destination_key}")
                    async with session_factory() as session:
                        result = await session.execute(
                            update(RecordingModel)
                            .where(
                                RecordingModel.id == recording_id,
                                RecordingModel.processed_video_path == source_key,
                            )
                            .values(processed_video_path=destination_key)
                        )
                        if result.rowcount != 1:
                            await session.rollback()
                            raise RuntimeError(f"Recording {recording_id} changed during backfill; old object retained")
                        await session.commit()
                    print(f"recording={recording_id}: switched to {destination_key}; old object retained")
                else:
                    mime = await _ensure_video_mp4(storage, source_key, apply=True)
                    print(f"recording={recording_id}: remux skipped (moov already first); mime={mime}")
        except Exception as exc:
            print(f"recording={recording_id} processed FAILED: {exc}")

    already_faststart = [
        (recording_id, key) for recording_id, key in processed_rows if key and key.endswith(".faststart.mp4")
    ]
    for recording_id, key in already_faststart:
        try:
            mime = await _ensure_video_mp4(storage, key, apply=apply)
            print(f"recording={recording_id} processed-faststart: {key} mime={mime}")
        except Exception as exc:
            print(f"recording={recording_id} processed-faststart FAILED: {exc}")

    seen_original: set[str] = set()
    for recording_id, key in original_rows:
        if not key or key in seen_original:
            continue
        seen_original.add(key)
        try:
            mime = await _ensure_video_mp4(storage, key, apply=apply)
            print(f"recording={recording_id} original: {key} mime={mime}")
        except Exception as exc:
            print(f"recording={recording_id} original FAILED: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write storage and conditional DB updates")
    parser.add_argument("--recording-id", type=int, action="append", dest="recording_ids")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, recording_ids=args.recording_ids))


if __name__ == "__main__":
    main()
