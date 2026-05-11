#!/usr/bin/env -S uv run python
"""
Вычислить final_duration из обрезанного аудио/видео для записей, где оно отсутствует.

Источники (по приоритету):
  1. audio.mp3 — ffprobe (обрезанное аудио после trim)
  2. video.mp4 — ffprobe (обрезанное видео)
  3. transcriptions/master.json — поле duration (если транскрипция есть, но файлов нет)
  4. ``source.<ext>`` (original, fallback — see pipeline ingress whitelist; legacy ``source.mp4``)

Использование:
  PYTHONPATH=$PWD uv run python scripts/compute_final_duration_from_files.py
  PYTHONPATH=$PWD uv run python scripts/compute_final_duration_from_files.py --update   # записать в БД
  PYTHONPATH=$PWD uv run python scripts/compute_final_duration_from_files.py --storage /path/to/storage

Требует .env с DATABASE_* и ffprobe в PATH.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.dependencies import get_async_session_maker
from config.settings import get_settings
from database.auth_models import UserModel
from database.automation_models import AutomationJobModel  # noqa: F401 - UserModel.relationship
from database.models import RecordingModel
from utils.pipeline_video_formats import (
    find_source_video_in_recording_dir,
    pipeline_ingress_suffixes_from_settings_formats,
)


def _ffprobe_duration(file_path: Path) -> float | None:
    """Get duration in seconds via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def _master_json_duration(master_path: Path) -> float | None:
    """Get duration from transcriptions/master.json."""
    try:
        data = json.loads(master_path.read_text())
        d = data.get("duration")
        if d is not None and isinstance(d, (int, float)) and d > 0:
            return float(d)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return None


def compute_duration(base_path: Path, user_slug: int, recording_id: int) -> tuple[float | None, str]:
    """
    Try to get final_duration from files. Returns (duration_sec, source).
    """
    root = base_path / "users" / f"user_{user_slug:06d}" / "recordings" / str(recording_id)

    # 1. audio.mp3 (trimmed audio)
    audio_path = root / "audio.mp3"
    if audio_path.exists():
        d = _ffprobe_duration(audio_path)
        if d is not None:
            return (d, "audio.mp3")

    # 2. video.mp4 (trimmed video)
    video_path = root / "video.mp4"
    if video_path.exists():
        d = _ffprobe_duration(video_path)
        if d is not None:
            return (d, "video.mp4")

    # 3. transcriptions/master.json
    master_path = root / "transcriptions" / "master.json"
    if master_path.exists():
        d = _master_json_duration(master_path)
        if d is not None:
            return (d, "master.json")

    # 4. source.<ext> (original, fallback; legacy source.mp4)
    ingress_suffixes = pipeline_ingress_suffixes_from_settings_formats(
        get_settings().storage.supported_video_formats,
    )
    source_path = find_source_video_in_recording_dir(root, ingress_suffixes)
    if source_path and source_path.is_file():
        d = _ffprobe_duration(source_path)
        if d is not None:
            return (d, source_path.name)

    return (None, "not_found")


async def main(storage_path: Path, do_update: bool) -> None:
    async_session = get_async_session_maker()
    async with async_session() as session:
        stmt = (
            select(RecordingModel.id, RecordingModel.duration, RecordingModel.final_duration, UserModel.user_slug)
            .join(UserModel, RecordingModel.user_id == UserModel.id)
            .where(
                RecordingModel.status.in_(("READY", "PROCESSED")),
                RecordingModel.final_duration.is_(None),
                RecordingModel.deleted.is_(False),
            )
            .order_by(RecordingModel.start_time)
        )
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        print("No recordings with status READY/PROCESSED and final_duration IS NULL.")
        return

    print(f"Found {len(rows)} recordings without final_duration. Storage: {storage_path}\n")

    updated_ids: list[int] = []
    not_found: list[tuple[int, float]] = []
    by_source: dict[str, int] = {}

    for r in rows:
        rec_id, orig_duration, _, user_slug = r
        duration, source = compute_duration(storage_path, user_slug, rec_id)

        by_source[source] = by_source.get(source, 0) + 1

        if duration is not None:
            if do_update:
                async with async_session() as session:
                    await session.execute(
                        update(RecordingModel).where(RecordingModel.id == rec_id).values(final_duration=duration)
                    )
                    await session.commit()
            updated_ids.append(rec_id)
            print(f"  id={rec_id:5}  duration={orig_duration:.0f}s  →  final_duration={duration:.2f}s  [{source}]")
        else:
            not_found.append((rec_id, orig_duration))
            print(f"  id={rec_id:5}  duration={orig_duration:.0f}s  →  SKIP (no files)")

    print("\n--- Summary ---")
    print(f"Computed: {len(updated_ids)}")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {src}: {cnt}")
    if not_found:
        print(
            f"\nNot found (no audio/video/master): {len(not_found)} ids: {[x[0] for x in not_found[:20]]}{'...' if len(not_found) > 20 else ''}"
        )
    if do_update and updated_ids:
        print(f"\nUpdated {len(updated_ids)} rows in database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute final_duration from trimmed audio/video files")
    parser.add_argument("--update", action="store_true", help="Write computed values to database")
    parser.add_argument("--storage", type=Path, default=Path.cwd() / "storage", help="Storage root path")
    args = parser.parse_args()

    if not args.storage.exists():
        print(f"Storage path does not exist: {args.storage}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main(args.storage, args.update))
