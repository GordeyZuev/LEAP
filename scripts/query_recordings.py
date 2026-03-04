#!/usr/bin/env -S uv run python
"""
Query recordings from DB: by id or by display_name search.
Run: PYTHONPATH=$PWD uv run python scripts/query_recordings.py [recording_id] [search_term]
     (requires .env with DATABASE_* or DATABASE_URL)
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.dependencies import get_async_session_maker
from database.automation_models import AutomationJobModel  # noqa: F401 - UserModel relationship
from database.models import RecordingModel


async def query_recording_by_id(session: AsyncSession, recording_id: int) -> dict | None:
    """Get recording 803 metadata (display_name, template_id) - no user filter."""
    stmt = select(
        RecordingModel.id,
        RecordingModel.display_name,
        RecordingModel.template_id,
        RecordingModel.user_id,
        RecordingModel.status,
        RecordingModel.start_time,
        RecordingModel.duration,
        RecordingModel.transcription_dir,
    ).where(
        RecordingModel.id == recording_id,
        RecordingModel.deleted.is_(False),
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    if not row:
        return None
    return {
        "id": row.id,
        "display_name": row.display_name,
        "template_id": row.template_id,
        "user_id": row.user_id,
        "status": str(row.status) if row.status else None,
        "start_time": str(row.start_time) if row.start_time else None,
        "duration": row.duration,
        "transcription_dir": row.transcription_dir,
    }


async def query_recordings_by_search(session: AsyncSession, search: str, limit: int = 20) -> list[dict]:
    """Search recordings by display_name (ILIKE)."""
    stmt = (
        select(
            RecordingModel.id,
            RecordingModel.display_name,
            RecordingModel.template_id,
            RecordingModel.start_time,
        )
        .where(
            RecordingModel.display_name.ilike(f"%{search}%"),
            RecordingModel.deleted.is_(False),
        )
        .order_by(RecordingModel.start_time.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "id": r.id,
            "display_name": r.display_name,
            "template_id": r.template_id,
            "start_time": str(r.start_time) if r.start_time else None,
        }
        for r in rows
    ]


async def main():
    recording_id = None
    search_term = None

    if len(sys.argv) >= 2:
        try:
            recording_id = int(sys.argv[1])
        except ValueError:
            search_term = " ".join(sys.argv[1:])
    if len(sys.argv) >= 3 and recording_id is not None:
        search_term = " ".join(sys.argv[2:])

    async_session = get_async_session_maker()
    async with async_session() as session:
        if recording_id is not None:
            rec = await query_recording_by_id(session, recording_id)
            if rec:
                print("=== Recording by ID ===")
                for k, v in rec.items():
                    print(f"  {k}: {v}")
            else:
                print(f"Recording {recording_id} not found.")

        if search_term:
            recs = await query_recordings_by_search(session, search_term)
            print("\n=== Recordings by display_name search ===")
            if not recs:
                print(f"No recordings matching '{search_term}'")
            else:
                for r in recs:
                    print(f"  id={r['id']} | template_id={r['template_id']} | {r['display_name'][:80]!r}")


if __name__ == "__main__":
    asyncio.run(main())
