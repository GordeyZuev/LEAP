#!/usr/bin/env python3
"""Run production AudioDetector on a local video (extract MP3, then silencedetect)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow `uv run python scripts/...` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_processing_module.audio_detector import AudioDetector
from video_processing_module.config import ProcessingConfig
from video_processing_module.video_processor import VideoProcessor


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--threshold", type=float, default=-40.0)
    parser.add_argument("--min-silence", type=float, default=2.0)
    parser.add_argument("--pad-before", type=float, default=5.0)
    parser.add_argument("--pad-after", type=float, default=5.0)
    parser.add_argument("--keep-mp3", type=Path, default=None)
    args = parser.parse_args()

    video = args.video.expanduser().resolve()
    if not video.is_file():
        print(f"missing file: {video}", file=sys.stderr)
        return 1

    mp3 = args.keep_mp3 or Path("/tmp") / f"{video.stem}_leap_silence.mp3"
    print(f"video={video}")
    print(f"extract mp3 → {mp3}")

    processor = VideoProcessor(ProcessingConfig(output_dir="/tmp"))
    ok = await processor.extract_audio_full(str(video), str(mp3))
    if not ok:
        print("extract_audio_full failed", file=sys.stderr)
        return 1

    detector = AudioDetector(silence_threshold=args.threshold, min_silence_duration=args.min_silence)
    duration = await detector.get_duration_seconds(str(mp3))
    first, last = await detector.detect_audio_boundaries_from_file(str(mp3))
    print(f"mp3_duration={duration}")
    print(f"first_sound={first}")
    print(f"last_sound={last}")

    if first is not None and last is not None:
        start = max(0.0, first - args.pad_before)
        end = last + args.pad_after
        if duration is not None:
            end = min(end, duration)
        kept = end - start
        print(f"trim_window start={start:.1f}s end={end:.1f}s kept={kept:.1f}s ({kept / 3600:.2f}h)")
        if duration:
            print(f"would_drop_tail={(duration - end) / 3600:.2f}h")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
