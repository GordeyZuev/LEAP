#!/usr/bin/env python3
"""Losslessly move MP4 metadata to the front for existing processed videos.

Dry-run is the default. Add ``--apply`` to download, remux into a new object,
verify its atom order, and conditionally switch ``processed_video_path``. The
old object is deliberately retained for rollback.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import select, update

from api.dependencies import get_async_session_maker
from database.models import RecordingModel
from file_storage.factory import get_storage_backend


def faststart_key(key: str) -> str:
    path = Path(key)
    return str(path.with_name(f"{path.stem}.faststart{path.suffix}"))


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
    if "moov" not in atoms or "mdat" not in atoms or atoms.index("moov") > atoms.index("mdat"):
        raise RuntimeError(f"Faststart verification failed: top-level atoms are {atoms}")


async def run(*, apply: bool, recording_ids: list[int] | None) -> None:
    session_factory = get_async_session_maker()
    storage = get_storage_backend()
    async with session_factory() as session:
        statement = select(RecordingModel.id, RecordingModel.processed_video_path).where(
            RecordingModel.deleted.is_(False),
            RecordingModel.processed_video_path.isnot(None),
            RecordingModel.processed_video_path.endswith(".mp4"),
            ~RecordingModel.processed_video_path.endswith(".faststart.mp4"),
        )
        if recording_ids:
            statement = statement.where(RecordingModel.id.in_(recording_ids))
        rows = list((await session.execute(statement.order_by(RecordingModel.id))).all())

    print(f"Found {len(rows)} processed MP4 files; mode={'APPLY' if apply else 'DRY-RUN'}")
    for recording_id, source_key in rows:
        if not source_key:
            continue
        destination_key = faststart_key(source_key)
        if not apply:
            print(f"recording={recording_id}: {source_key} -> {destination_key}")
            continue

        with tempfile.TemporaryDirectory(prefix=f"leap-faststart-{recording_id}-") as directory:
            source = Path(directory) / "source.mp4"
            destination = Path(directory) / "faststart.mp4"
            await storage.download_to_file(source_key, source)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform remux, upload, and conditional DB update")
    parser.add_argument("--recording-id", type=int, action="append", dest="recording_ids")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, recording_ids=args.recording_ids))


if __name__ == "__main__":
    main()
