#!/usr/bin/env python3
"""Attach leap-test-114 (prod recording 114 artifacts) to local hse_ai@hse.ru.

Copies video, poster, VTT, master.json, extracted.json into local storage, creates
a READY recording with chapters + share, and leaves the source folder in place.

Run from backend/:
    uv run python scripts/import_watch_fixture.py
"""

# chdir + load_dotenv before app imports so settings pick up backend/.env
# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings
from database.auth_models import UserModel
from database.automation_models import AutomationJobModel  # noqa: F401
from database.models import RecordingModel, SourceMetadataModel
from file_storage.factory import get_storage_backend
from file_storage.path_builder import get_path_builder, to_storage_key
from models.recording import ProcessingStatus, SourceType

USER_EMAIL = "hse_ai@hse.ru"
FIXTURE = REPO / "leap-test-114"
DISPLAY_NAME = "ИИ_1 курс_SQL(GR-1) 2026-09-10 18:09:14"


def _copy_into_storage(storage, key: str, src: Path) -> None:
    """Copy (not move) a local file into the storage backend."""
    resolve = getattr(storage, "_resolve", None)
    if resolve is not None:
        dest = resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return
    raise RuntimeError("This fixture importer expects LOCAL storage (_resolve).")


async def main() -> None:
    for name in ("video.mp4", "poster.jpg", "master.json", "extracted.json", "subtitles.vtt"):
        path = FIXTURE / name
        if not path.is_file():
            raise SystemExit(f"missing {path}")

    extracted = json.loads((FIXTURE / "extracted.json").read_text(encoding="utf-8"))
    versions = extracted.get("versions") or []
    active = next((v for v in versions if v.get("is_active")), versions[0] if versions else {})
    topics = active.get("topic_timestamps") or []
    main_topics = active.get("main_topics") or []

    engine = create_async_engine(settings.database.url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        user = (await session.execute(select(UserModel).where(UserModel.email == USER_EMAIL))).scalar_one()
        slug = user.user_slug

        rec = RecordingModel(
            user_id=user.id,
            display_name=DISPLAY_NAME,
            start_time=datetime(2026, 9, 10, 15, 9, 14, tzinfo=UTC),
            duration=8231.0,
            final_duration=8123.382,
            status=ProcessingStatus.READY,
            topic_timestamps=topics,
            main_topics=main_topics,
            video_file_size=(FIXTURE / "video.mp4").stat().st_size,
            downloaded_at=datetime.now(UTC),
            pipeline_completed_at=datetime.now(UTC),
            share_enabled=True,
            share_token=uuid.uuid4(),
            allow_video_download=True,
            allow_files_download=True,
        )
        session.add(rec)
        await session.flush()
        rid = rec.id

        session.add(
            SourceMetadataModel(
                recording_id=rid,
                user_id=user.id,
                source_type=SourceType.LOCAL_FILE,
                source_key=f"leap-test-114:{rid}",
                meta={"imported_from": "prod recording 114", "fixture": str(FIXTURE)},
            )
        )

        builder = get_path_builder()
        video_key = to_storage_key(builder.recording_video(slug, rid))
        poster_key = to_storage_key(builder.recording_root(slug, rid) / "poster.jpg")
        tx_dir = builder.transcription_dir(slug, rid)
        master_key = to_storage_key(builder.transcription_master(slug, rid))
        extracted_key = to_storage_key(builder.transcription_extracted(slug, rid))
        vtt_key = to_storage_key(builder.transcription_cache_dir(slug, rid) / "subtitles.vtt")

        rec.processed_video_path = video_key
        rec.local_video_path = video_key
        rec.transcription_dir = str(tx_dir)

        storage = get_storage_backend()
        _copy_into_storage(storage, video_key, FIXTURE / "video.mp4")
        _copy_into_storage(storage, poster_key, FIXTURE / "poster.jpg")
        _copy_into_storage(storage, master_key, FIXTURE / "master.json")
        _copy_into_storage(storage, vtt_key, FIXTURE / "subtitles.vtt")

        extracted["recording_id"] = rid
        dest_extracted = Path(storage._resolve(extracted_key))
        dest_extracted.parent.mkdir(parents=True, exist_ok=True)
        dest_extracted.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")

        token = rec.share_token
        await session.commit()

        print(f"user={USER_EMAIL} slug={slug}")
        print(f"recording={rid}")
        print(f"editor=/recordings/{rid}")
        print(f"share=/share/{token}")
        print(f"video_key={video_key}")
        print(f"chapters={len(topics)}")
        print(f"video_bytes={(FIXTURE / 'video.mp4').stat().st_size}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
