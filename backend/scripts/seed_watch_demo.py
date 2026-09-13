#!/usr/bin/env python3
"""One-off local helper: demo chapters on recording 2541 for hse_ai@hse.ru."""

# chdir + load_dotenv before app imports so settings pick up backend/.env
# ruff: noqa: E402

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings
from database.auth_models import UserModel
from database.automation_models import AutomationJobModel  # noqa: F401
from database.models import RecordingModel
from transcription_module.manager import get_transcription_manager

USER_EMAIL = "hse_ai@hse.ru"
RECORDING_ID = 2541


async def main() -> None:
    engine = create_async_engine(settings.database.url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        user = (await session.execute(select(UserModel).where(UserModel.email == USER_EMAIL))).scalar_one()
        rec = await session.get(RecordingModel, RECORDING_ID)
        if rec is None or rec.user_id != user.id:
            raise SystemExit(f"recording {RECORDING_ID} not owned by {USER_EMAIL}")
        if not rec.processed_video_path:
            raise SystemExit("recording has no processed video")

        duration = float(rec.final_duration or rec.duration or 900)
        chapters = [
            {"topic": "Introduction", "start": 0},
            {"topic": "Problem setup", "start": min(45, duration * 0.1)},
            {"topic": "Main argument", "start": min(120, duration * 0.25)},
            {"topic": "Examples", "start": min(240, duration * 0.45)},
            {"topic": "Wrap-up", "start": min(max(duration - 30, 0), duration * 0.85)},
        ]
        main_topics = ["Watch-player demo", "Chapters", "Summary"]
        rec.topic_timestamps = chapters
        rec.main_topics = main_topics
        if not rec.share_token:
            rec.share_token = uuid.uuid4()
        rec.share_enabled = True
        await session.commit()
        token = rec.share_token

        mgr = get_transcription_manager()
        await mgr.add_extracted_version(
            recording_id=RECORDING_ID,
            version_id="watch-demo",
            model="demo",
            granularity="coarse",
            main_topics=main_topics,
            topic_timestamps=chapters,
            summary="Demo summary for the shared watch layout: chapters sit beside the player on large screens.",
            questions=["What should the default player width be?", "When should the companion column appear?"],
            is_active=True,
            user_slug=user.user_slug,
        )

        print(f"recording={RECORDING_ID}")
        print(f"editor=/recordings/{RECORDING_ID}")
        print(f"share=/share/{token}")
        print(f"duration_s={duration:.0f}")
        print(f"chapters={len(chapters)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
