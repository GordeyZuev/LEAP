#!/usr/bin/env -S uv run python
"""
Compute average trimming: original duration vs final (trimmed) duration.

Data source: database (duration = original from Zoom, final_duration = after trim/transcription).
Optional: ffprobe on storage files (source.mp4 vs video.mp4) if available.

Run: PYTHONPATH=$PWD uv run python scripts/trimming_stats.py
     (requires DATABASE_URL in env)
"""

import asyncio
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.dependencies import get_async_session_maker
from database.auth_models import UserModel
from database.automation_models import AutomationJobModel  # noqa: F401 - ensure model loaded for UserModel.relationship
from database.models import RecordingModel
from file_storage.path_builder import get_path_builder


def _ffprobe_duration(file_path: Path) -> float | None:
    """Get duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [  # noqa: S607
                "ffprobe",
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
            timeout=10,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def _ffprobe_audio_bitrate(file_path: Path) -> float | None:
    """Get audio stream bitrate in kbps via ffprobe."""
    try:
        result = subprocess.run(
            [  # noqa: S607
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=bit_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip()) / 1000  # bps -> kbps
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


async def stats_from_db(session: AsyncSession) -> dict:
    """Compute trimming stats from DB (duration vs final_duration)."""
    stmt = select(
        RecordingModel.id,
        RecordingModel.duration,
        RecordingModel.final_duration,
    ).where(
        RecordingModel.final_duration.isnot(None),
        RecordingModel.duration > 0,
        RecordingModel.deleted.is_(False),
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"count": 0, "message": "No recordings with both duration and final_duration"}

    trimmed_sec = []
    trimmed_pct = []
    for r in rows:
        orig = r.duration
        final = r.final_duration
        if orig <= 0 or final is None:
            continue
        diff = orig - final
        trimmed_sec.append(max(0, diff))
        trimmed_pct.append((diff / orig) * 100 if orig > 0 else 0)

    n = len(trimmed_sec)
    return {
        "count": n,
        "avg_trimmed_seconds": sum(trimmed_sec) / n,
        "avg_trimmed_percent": sum(trimmed_pct) / n,
        "total_original_seconds": sum(r.duration for r in rows),
        "total_final_seconds": sum(r.final_duration for r in rows),
    }


async def audio_format_stats(session: AsyncSession, base_path: Path) -> dict | None:
    """Compare source video audio vs extracted audio.mp3 (our format: 16kHz mono 64kbps)."""
    stmt = (
        select(RecordingModel.id, UserModel.user_slug, RecordingModel.final_duration)
        .join(UserModel, RecordingModel.user_id == UserModel.id)
        .where(
            RecordingModel.final_duration.isnot(None),
            RecordingModel.deleted.is_(False),
        )
    )
    result = await session.execute(stmt)
    rows = result.all()
    pb = get_path_builder(str(base_path))

    reductions = []  # (source_audio_bytes, our_audio_bytes, source_bitrate, our_duration) per recording
    source_bitrates = []
    for r in rows:
        source_path = pb.recording_root(r.user_slug, r.id) / "source.mp4"
        audio_path = pb.recording_root(r.user_slug, r.id) / "audio.mp3"
        if not source_path.exists() or not audio_path.exists():
            continue

        src_duration = _ffprobe_duration(source_path)
        our_duration = _ffprobe_duration(audio_path) or r.final_duration
        source_bitrate_kbps = _ffprobe_audio_bitrate(source_path)
        our_size = audio_path.stat().st_size

        if src_duration is None or src_duration <= 0 or our_size <= 0:
            continue

        if source_bitrate_kbps:
            source_bitrates.append(source_bitrate_kbps)
            source_audio_bytes = (source_bitrate_kbps * 1000 * src_duration) / 8
        else:
            source_audio_bytes = (128 * 1000 * src_duration) / 8  # Fallback: Zoom AAC ~128 kbps

        reductions.append((source_audio_bytes, our_size, source_bitrate_kbps or 128, our_duration or src_duration))

    if not reductions:
        return None

    total_source = sum(s for s, _, _, _ in reductions)
    total_ours = sum(o for _, o, _, _ in reductions)
    avg_reduction_pct = (1 - total_ours / total_source) * 100 if total_source > 0 else 0

    # Format-only: same duration, compare bitrates
    avg_src_kbps = sum(sb for _, _, sb, _ in reductions) / len(reductions) if reductions else 0
    our_kbps = 64

    # Vs uncompressed WAV (48 kHz stereo 16-bit = 1536 kbps) - as in the paper
    wav_kbps = 1536
    vs_wav_reduction = (1 - our_kbps / wav_kbps) * 100

    return {
        "count": len(reductions),
        "total_source_audio_mb": total_source / (1024 * 1024),
        "total_our_audio_mb": total_ours / (1024 * 1024),
        "avg_reduction_percent": avg_reduction_pct,
        "avg_source_bitrate_kbps": avg_src_kbps,
        "our_bitrate_kbps": our_kbps,
        "format_reduction_pct": (1 - our_kbps / avg_src_kbps) * 100 if avg_src_kbps > 0 else 0,
        "vs_wav_reduction_pct": vs_wav_reduction,
    }


async def stats_from_storage(session: AsyncSession, base_path: Path) -> dict | None:
    """Compute trimming from storage files (source.mp4 vs video.mp4) using ffprobe."""
    # Get recordings with user_slug for path building
    stmt = (
        select(RecordingModel.id, RecordingModel.user_id, UserModel.user_slug)
        .join(UserModel, RecordingModel.user_id == UserModel.id)
        .where(
            RecordingModel.final_duration.isnot(None),
            RecordingModel.deleted.is_(False),
        )
    )
    result = await session.execute(stmt)
    rows = result.all()
    pb = get_path_builder(str(base_path))

    durations_orig = []
    durations_final = []
    for r in rows:
        source_path = pb.recording_root(r.user_slug, r.id) / "source.mp4"
        video_path = pb.recording_root(r.user_slug, r.id) / "video.mp4"
        if not source_path.exists():
            continue
        # Use video.mp4 if exists (trimmed), else source is both
        final_path = video_path if video_path.exists() else source_path
        do = _ffprobe_duration(source_path)
        df = _ffprobe_duration(final_path)
        if do is not None and df is not None:
            durations_orig.append(do)
            durations_final.append(df)

    if not durations_orig:
        return None

    n = len(durations_orig)
    trimmed = [max(0, o - f) for o, f in zip(durations_orig, durations_final, strict=True)]
    pcts = [(d / o) * 100 for o, d in zip(durations_orig, trimmed, strict=True) if o > 0]
    return {
        "count": n,
        "avg_trimmed_seconds": sum(trimmed) / n,
        "avg_trimmed_percent": sum(pcts) / n if pcts else 0,
    }


async def main():
    async_session = get_async_session_maker()
    async with async_session() as session:
        db_stats = await stats_from_db(session)
        print("=== Trimming statistics (from database) ===")
        if db_stats.get("message"):
            print(db_stats["message"])
        else:
            print(f"Recordings: {db_stats['count']}")
            print(
                f"Average trimmed: {db_stats['avg_trimmed_seconds']:.1f} sec ({db_stats['avg_trimmed_percent']:.2f}%)"
            )
            if "total_original_seconds" in db_stats:
                orig_h = db_stats["total_original_seconds"] / 3600
                final_h = db_stats["total_final_seconds"] / 3600
                print(f"Total: {orig_h:.1f}h original → {final_h:.1f}h final")

        # Try storage if storage/ exists
        storage_root = Path.cwd() / "storage"
        if storage_root.exists():
            storage_stats = await stats_from_storage(session, storage_root)
            if storage_stats:
                print("\n=== Trimming (from storage files, ffprobe) ===")
                print(f"Recordings with files: {storage_stats['count']}")
                print(
                    f"Average trimmed: {storage_stats['avg_trimmed_seconds']:.1f} sec ({storage_stats['avg_trimmed_percent']:.2f}%)"
                )

            # Audio format: source video audio vs our MP3 64k 16kHz mono
            audio_stats = await audio_format_stats(session, storage_root)
            if audio_stats:
                print("\n=== Audio format (source vs MP3 64k 16kHz mono) ===")
                print(f"Recordings: {audio_stats['count']}")
                print(f"Source audio (estimated): {audio_stats['total_source_audio_mb']:.1f} MB")
                print(f"Our audio (MP3): {audio_stats['total_our_audio_mb']:.1f} MB")
                print(
                    f"Source avg bitrate: {audio_stats['avg_source_bitrate_kbps']:.0f} kbps | Ours: {audio_stats['our_bitrate_kbps']} kbps"
                )
                print(f"Size reduction (total, incl. trimming): {audio_stats['avg_reduction_percent']:.1f}%")
                print(f"Format vs source (same duration): {audio_stats['format_reduction_pct']:.1f}%")
                print(f"Vs uncompressed WAV (48k stereo): {audio_stats['vs_wav_reduction_pct']:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
