#!/usr/bin/env -S uv run python
"""
Извлечение метрик батча из PostgreSQL.
Использование:
  uv run python scripts/batch_metrics_from_db.py --all-tests   # все 68 ID из тестов #2–#6
  uv run python scripts/batch_metrics_from_db.py --all          # все READY из БД
  uv run python scripts/batch_metrics_from_db.py 1032 1043 ... # позиционные ID
  uv run python scripts/batch_metrics_from_db.py --ids 1032,1043,1045  # через запятую

Возвращает JSON. Требует .env с DATABASE_*.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.dependencies import get_async_session_maker
from database.automation_models import AutomationJobModel  # noqa: F401 - UserModel.relationship
from database.models import RecordingModel
from models.recording import ProcessingStatus

# Все recording_id из тестов #2–#6 (из BATCH_TESTING.md). #1 — 24 записи, ID не сохранены.
ALL_TEST_RECORDING_IDS = [
    481,
    519,
    526,
    527,
    545,
    546,
    586,
    589,
    591,
    595,
    596,  # #2
    603,
    622,
    625,
    631,
    639,
    646,
    650,  # #3
    801,
    803,
    804,
    805,
    807,
    808,
    810,
    811,
    812,  # #4B
    814,
    827,
    830,
    831,
    834,
    842,  # #4A
    902,
    936,
    943,
    944,
    946,
    947,
    950,  # #5
    1032,
    1043,
    1045,
    1046,
    1047,  # #6B
    1053,
    1057,
    1058,
    1064,
    1082,
    1084,
    1090,
    1091,
    1092,
    1093,
    1103,
    1112,
    1113,  # #6A
]


async def fetch_all_recording_ids() -> list[int]:
    """Получить все id записей со статусом READY из БД."""
    async_session = get_async_session_maker()
    async with async_session() as session:
        stmt = (
            select(RecordingModel.id)
            .where(
                RecordingModel.status == ProcessingStatus.READY,
                RecordingModel.deleted.is_(False),
            )
            .order_by(RecordingModel.id)
        )
        result = await session.execute(stmt)
        return [r[0] for r in result.all()]


async def fetch_batch_metrics(recording_ids: list[int]) -> dict:
    """Получить метрики батча по списку recording_id."""
    async_session = get_async_session_maker()
    async with async_session() as session:
        stmt = (
            select(RecordingModel)
            .where(
                RecordingModel.id.in_(recording_ids),
                RecordingModel.deleted.is_(False),
            )
            .options(
                selectinload(RecordingModel.processing_stages),
                selectinload(RecordingModel.outputs),
            )
        )
        result = await session.execute(stmt)
        recordings = list(result.scalars().unique())

    if not recordings:
        return {"error": "No recordings found", "ids": recording_ids}

    # Агрегаты
    total_duration_min = sum(r.duration for r in recordings if r.duration) / 60
    total_size_gb = sum(r.video_file_size or 0 for r in recordings) / (1024**3)
    ready_count = sum(1 for r in recordings if str(r.status) == "READY")
    failed_count = sum(1 for r in recordings if r.failed)

    # Pipeline timing
    started = [r.pipeline_started_at for r in recordings if r.pipeline_started_at]
    completed = [r.pipeline_completed_at for r in recordings if r.pipeline_completed_at]
    durations = [r.pipeline_duration_seconds for r in recordings if r.pipeline_duration_seconds]

    wall_clock_min = None
    if started and completed:
        min_start = min(started)
        max_complete = max(completed)
        wall_clock_min = (max_complete - min_start).total_seconds() / 60

    # По этапам
    stage_stats: dict[str, list[float]] = {}
    for rec in recordings:
        for stage in rec.processing_stages:
            if stage.started_at and stage.completed_at:
                dur = (stage.completed_at - stage.started_at).total_seconds()
                st = str(stage.stage_type) if stage.stage_type else "unknown"
                stage_stats.setdefault(st, []).append(dur)

    return {
        "recording_ids": sorted(r.id for r in recordings),
        "count": len(recordings),
        "ready": ready_count,
        "failed": failed_count,
        "total_duration_hours": round(total_duration_min / 60, 2),
        "total_size_gb": round(total_size_gb, 2),
        "wall_clock_min": round(wall_clock_min, 1) if wall_clock_min else None,
        "avg_pipeline_sec": round(sum(durations) / len(durations), 1) if durations else None,
        "stage_avg_sec": {k: round(sum(v) / len(v), 1) for k, v in stage_stats.items()},
        "recordings": [
            {
                "id": r.id,
                "display_name": (r.display_name or "")[:60],
                "duration_min": round(r.duration / 60, 1) if r.duration else None,
                "size_mb": round((r.video_file_size or 0) / (1024**2), 1),
                "status": str(r.status),
                "pipeline_sec": r.pipeline_duration_seconds,
                "pipeline_started": r.pipeline_started_at.isoformat() if r.pipeline_started_at else None,
                "pipeline_completed": r.pipeline_completed_at.isoformat() if r.pipeline_completed_at else None,
            }
            for r in sorted(recordings, key=lambda x: x.id)
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Batch metrics from PostgreSQL",
        epilog="Пример: uv run python scripts/batch_metrics_from_db.py --all-tests",
    )
    parser.add_argument("ids", nargs="*", type=int, help="Recording IDs (позиционные)")
    parser.add_argument("--ids", dest="ids_csv", type=str, help="Recording IDs через запятую")
    parser.add_argument(
        "--all-tests",
        action="store_true",
        help="Все записи из тестов #2–#6 (58 ID из BATCH_TESTING.md)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Все записи со статусом READY из БД",
    )
    args = parser.parse_args()

    if args.all:
        recording_ids = asyncio.run(fetch_all_recording_ids())
        if not recording_ids:
            print('{"error": "No READY recordings in DB"}', file=sys.stderr)
            sys.exit(1)
    elif args.all_tests:
        recording_ids = ALL_TEST_RECORDING_IDS
    elif args.ids_csv:
        recording_ids = [int(x.strip()) for x in args.ids_csv.split(",")]
    else:
        recording_ids = list(args.ids or [])

    if not recording_ids:
        print("Укажите ID, --all-tests или --all", file=sys.stderr)
        sys.exit(1)

    result = asyncio.run(fetch_batch_metrics(recording_ids))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
