#!/usr/bin/env python3
"""Inspect or generate video seek previews for one local recording."""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

from redis.asyncio import from_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from api.services.video_previews import (  # noqa: E402
    PREVIEW_QUEUE_LOCK_SECONDS,
    mark_preview_maker_stage,
    preview_key,
    preview_queue_key,
    release_preview_queue_lock,
)
from config.settings import settings  # noqa: E402
from database.automation_models import AutomationJobModel  # noqa: E402, F401
from database.models import RecordingModel  # noqa: E402
from file_storage.factory import get_storage_backend  # noqa: E402


async def main(recording_id: int, *, run: bool, force: bool) -> None:
    engine = create_async_engine(settings.database.url)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session:
            recording = await session.get(RecordingModel, recording_id)
            if recording is None or not recording.processed_video_path:
                raise SystemExit(f"Recording {recording_id} has no processed video")
            user_id = recording.user_id
            source_key = recording.processed_video_path
            vtt_key = preview_key(recording.owner.user_slug, recording_id, "storyboard.vtt")

        storage = get_storage_backend()
        size = await storage.get_size(source_key)
        exists = await storage.exists(vtt_key)
        print(f"recording={recording_id} source_bytes={size} storyboard_exists={exists}")
        if not run:
            print("Inspection only. Pass --run to generate the storyboard.")
            return
        if exists and not force:
            print("Storyboard already exists. Pass --force to regenerate it.")
            return

        from api.tasks.processing import _run_video_preview_job

        token = secrets.token_hex(16)
        async with from_url(settings.celery.broker_url, decode_responses=True) as redis:
            if not await redis.set(preview_queue_key(recording_id), token, nx=True, ex=PREVIEW_QUEUE_LOCK_SECONDS):
                raise SystemExit("Preview generation is already queued or running")
            try:
                if not await mark_preview_maker_stage(
                    recording_id, user_id, "PENDING", token, ignore_failure_cooldown=force
                ):
                    raise SystemExit(
                        "Recording is unavailable or a failed preview is cooling down; use --force to retry"
                    )
                await mark_preview_maker_stage(recording_id, user_id, "IN_PROGRESS", token)
                result = await _run_video_preview_job(recording_id, user_id, force=force, lock_token=token)
                print(result)
                if not result.get("success") or not await storage.exists(vtt_key):
                    raise RuntimeError(str(result.get("error") or "Storyboard generation did not complete"))
                await mark_preview_maker_stage(recording_id, user_id, "COMPLETED", token)
            except Exception as exc:
                await mark_preview_maker_stage(recording_id, user_id, "FAILED", token, error=str(exc))
                raise
            finally:
                await release_preview_queue_lock(redis, recording_id, token)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording_id", type=int)
    parser.add_argument("--run", action="store_true", help="Generate and upload the storyboard")
    parser.add_argument("--force", action="store_true", help="Regenerate an existing storyboard")
    args = parser.parse_args()
    asyncio.run(main(args.recording_id, run=args.run, force=args.force))
