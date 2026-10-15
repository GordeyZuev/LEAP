#!/usr/bin/env python3
"""Queue seek previews for every active recording with a processed video.

Dry-run by default. ``--run`` submits one recording at a time to the normal
``previews`` Celery queue and waits for it to finish before submitting the next.
The bounded queue keeps a large archive from overwhelming the preview worker.
Rerunning the command skips completed previews and safely resumes the scan.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

from redis.asyncio import from_url  # noqa: E402
from sqlalchemy import and_, select  # noqa: E402

from api.dependencies import get_async_session_maker  # noqa: E402
from api.services.video_previews import enqueue_video_previews, preview_key  # noqa: E402
from config.settings import settings  # noqa: E402
from database.auth_models import UserModel  # noqa: E402
from database.automation_models import AutomationJobModel  # noqa: E402, F401
from database.models import PreviewMakerStageModel, ProcessingStageModel, RecordingModel  # noqa: E402
from file_storage.factory import get_storage_backend  # noqa: E402
from models.recording import ProcessingStageType  # noqa: E402


@dataclass(frozen=True)
class Candidate:
    recording_id: int
    user_id: str
    user_slug: int
    video_path: str
    trimmed_at: datetime | None
    stage_status: str | None
    stage_video_path: str | None
    stage_trimmed_at: datetime | None

    @property
    def stage_matches(self) -> bool:
        return (self.stage_video_path, self.stage_trimmed_at) == (self.video_path, self.trimmed_at)


def completed(candidate: Candidate, vtt_exists: bool) -> bool:
    return candidate.stage_status == "COMPLETED" and candidate.stage_matches and vtt_exists


async def candidate_pages(batch_size: int, start_after: int):
    last_id = start_after
    session_maker = get_async_session_maker()
    while True:
        async with session_maker() as session:
            rows = (
                await session.execute(
                    select(
                        RecordingModel.id,
                        RecordingModel.user_id,
                        UserModel.user_slug,
                        RecordingModel.processed_video_path,
                        ProcessingStageModel.completed_at,
                        PreviewMakerStageModel.status,
                        PreviewMakerStageModel.source_video_path,
                        PreviewMakerStageModel.source_trimmed_at,
                    )
                    .join(UserModel, UserModel.id == RecordingModel.user_id)
                    .outerjoin(
                        ProcessingStageModel,
                        and_(
                            ProcessingStageModel.recording_id == RecordingModel.id,
                            ProcessingStageModel.stage_type == ProcessingStageType.TRIM,
                        ),
                    )
                    .outerjoin(PreviewMakerStageModel, PreviewMakerStageModel.recording_id == RecordingModel.id)
                    .where(
                        RecordingModel.id > last_id,
                        RecordingModel.processed_video_path.is_not(None),
                        RecordingModel.processed_video_path != "",
                        RecordingModel.deleted.is_(False),
                        RecordingModel.delete_state == "active",
                    )
                    .order_by(RecordingModel.id)
                    .limit(batch_size)
                )
            ).all()
        if not rows:
            return
        page = [Candidate(*row) for row in rows]
        yield page
        last_id = page[-1].recording_id


async def wait_for_preview(candidate: Candidate, vtt_key: str, *, interval: int, timeout: int) -> str:
    session_maker = get_async_session_maker()
    storage = get_storage_backend()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(interval)
        async with session_maker() as session:
            stage = await session.get(PreviewMakerStageModel, candidate.recording_id)
        if stage is None:
            continue
        if (stage.source_video_path, stage.source_trimmed_at) != (candidate.video_path, candidate.trimmed_at):
            return "source_changed"
        if stage.status == "FAILED":
            return "failed"
        if stage.status == "COMPLETED":
            return "completed" if await storage.exists(vtt_key) else "missing_vtt"
    return "timed_out"


async def preview_is_active(candidate: Candidate) -> bool:
    async with get_async_session_maker()() as session:
        stage = await session.get(PreviewMakerStageModel, candidate.recording_id)
    return bool(
        stage
        and stage.status in {"PENDING", "IN_PROGRESS"}
        and (stage.source_video_path, stage.source_trimmed_at) == (candidate.video_path, candidate.trimmed_at)
    )


async def main(args: argparse.Namespace) -> int:
    storage = get_storage_backend()
    counts: dict[str, int] = {}
    redis = from_url(settings.celery.broker_url, decode_responses=True) if args.run else None
    try:
        async for page in candidate_pages(args.batch_size, args.start_after):
            for candidate in page:
                vtt_key = preview_key(candidate.user_slug, candidate.recording_id, "storyboard.vtt")
                index_exists = await storage.exists(vtt_key)
                if completed(candidate, index_exists):
                    result = "already_complete"
                elif not args.run:
                    result = "needs_preview"
                else:
                    queued = await enqueue_video_previews(
                        redis,
                        candidate.recording_id,
                        candidate.user_id,
                        force=index_exists,
                    )
                    active = queued or await preview_is_active(candidate)
                    if active:
                        print(
                            f"recording={candidate.recording_id} status={'queued' if queued else 'already_active'}",
                            flush=True,
                        )
                        result = await wait_for_preview(
                            candidate,
                            vtt_key,
                            interval=args.poll_seconds,
                            timeout=args.wait_seconds,
                        )
                    else:
                        # An old claim or retry cooldown can block publication.
                        # A later run will inspect the final stage before retrying.
                        result = "already_queued_or_retry_blocked"
                counts[result] = counts.get(result, 0) + 1
                print(f"recording={candidate.recording_id} result={result}", flush=True)
                if args.limit and sum(counts.values()) >= args.limit:
                    break
            if args.limit and sum(counts.values()) >= args.limit:
                break
    finally:
        if redis is not None:
            await redis.aclose()
    print("Summary: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())), flush=True)
    incomplete = ("already_queued_or_retry_blocked", "failed", "missing_vtt", "source_changed", "timed_out")
    return int(args.run and any(counts.get(key) for key in incomplete))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Queue and wait for every missing preview")
    parser.add_argument("--limit", type=int, default=0, help="Inspect at most this many recordings (0: all)")
    parser.add_argument("--start-after", type=int, default=0, help="Resume scanning after this recording ID")
    parser.add_argument("--batch-size", type=int, default=100, help="Database page size")
    parser.add_argument("--poll-seconds", type=int, default=5, help="Seconds between stage checks")
    parser.add_argument("--wait-seconds", type=int, default=4500, help="Maximum wait per recording")
    arguments = parser.parse_args()
    if arguments.limit < 0 or arguments.start_after < 0 or arguments.batch_size < 1:
        parser.error("--limit and --start-after must be nonnegative; --batch-size must be positive")
    if arguments.poll_seconds < 1 or arguments.wait_seconds < arguments.poll_seconds:
        parser.error("--poll-seconds must be positive and no greater than --wait-seconds")
    raise SystemExit(asyncio.run(main(arguments)))
