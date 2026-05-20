#!/usr/bin/env -S uv run python
"""One-off: migrate data_culture@hse.ru template matching_rules to new filename regex."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.dependencies import get_async_session_maker
from database.auth_models import UserModel
from database.automation_models import AutomationJobModel  # noqa: F401 - UserModel.relationship
from database.template_models import RecordingTemplateModel

USER_EMAIL = "data_culture@hse.ru"
DATE_PREFIX = r"^\d{4}-\d{2}-\d{2}_\d{6}_"
GROUP_SEGMENT = re.compile(r"_(группа[^_]*|группы[^_]*)_")


def exact_to_pattern(exact: str) -> str:
    """Build regex for YYYY-MM-DD_HHMMSS_<body>..._<teacher>[.<ext>] filenames."""
    exact = exact.strip()
    if not exact:
        raise ValueError("empty exact_match")

    group_match = GROUP_SEGMENT.search(exact)
    if group_match:
        body = exact[: group_match.start()]
        teacher = exact[group_match.end() :]
    else:
        body, _, teacher = exact.rpartition("_")
        if not teacher:
            raise ValueError(f"cannot parse exact_match: {exact!r}")

    body_re = re.escape(body)
    teacher_re = re.escape(teacher)
    return f"{DATE_PREFIX}{body_re}_.*?{teacher_re}(\\..+)?$"


def merge_source_ids(existing: list[int] | None) -> list[int]:
    ids = set(existing or [])
    ids.add(4)
    ids.add(10)
    ids.discard(8)
    return sorted(ids)


def build_matching_rules(old: dict) -> dict:
    exact_matches = old.get("exact_matches") or []
    patterns: list[str] = []
    seen: set[str] = set()

    for exact in exact_matches:
        if not isinstance(exact, str) or not exact.strip():
            continue
        pattern = exact_to_pattern(exact)
        if pattern not in seen:
            seen.add(pattern)
            patterns.append(pattern)

    if not patterns:
        raise ValueError("no patterns produced")

    return {
        "patterns": patterns,
        "exact_matches": None,
        "keywords": old.get("keywords"),
        "source_ids": merge_source_ids(old.get("source_ids")),
        "exclude_keywords": old.get("exclude_keywords"),
        "exclude_patterns": old.get("exclude_patterns"),
        "case_sensitive": old.get("case_sensitive", False),
    }


async def main() -> int:
    dry_run = "--apply" not in sys.argv
    async_session = get_async_session_maker()

    async with async_session() as session:
        user_id = (
            await session.execute(select(UserModel.id).where(UserModel.email == USER_EMAIL))
        ).scalar_one_or_none()
        if user_id is None:
            print(f"User not found: {USER_EMAIL}", file=sys.stderr)
            return 1

        result = await session.execute(
            select(
                RecordingTemplateModel.id,
                RecordingTemplateModel.name,
                RecordingTemplateModel.matching_rules,
            )
            .where(
                RecordingTemplateModel.user_id == user_id,
                RecordingTemplateModel.is_draft.is_(False),
            )
            .order_by(RecordingTemplateModel.id)
        )
        rows = [(r.id, r.name, r.matching_rules) for r in result.all()]

        updates: list[tuple[int, str, dict, dict]] = []
        skipped: list[tuple[int, str, str]] = []

        for tid, name, rules in rows:
            rules = rules or {}
            try:
                new_rules = build_matching_rules(rules)
            except ValueError as exc:
                skipped.append((tid, name, str(exc)))
                continue
            updates.append((tid, name, rules, new_rules))

        print(f"User {USER_EMAIL} ({user_id}): {len(rows)} templates, {len(updates)} to update, {len(skipped)} skipped")
        for tid, name, old, new in updates[:3]:
            print(f"\n--- template {tid}: {name} ---")
            print("OLD:", json.dumps(old, ensure_ascii=False))
            print("NEW:", json.dumps(new, ensure_ascii=False))

        test_names = [
            "2026-04-25_130234_РИСО_Автоматизация коммуникационных процессов с помощью ИИ_Сусла Д.М..webm",
            "2026-04-22_093017_РИСО_Автоматизация коммуникационных процессов с помощью ИИ_группа 3,5_Анисимова К.М..webm",
            "2026-04-27_180523_МИЭМ_Методы МО_группа 2_Семенов Г.Ю..webm",
        ]
        pattern_by_id = {tid: new["patterns"] for tid, _, _, new in updates}
        for display_name in test_names:
            matched = [
                tid for tid, pats in pattern_by_id.items() if any(re.search(p, display_name, re.I) for p in pats)
            ]
            print(f"\nTest {display_name!r} -> templates {matched}")

        if dry_run:
            print("\nDry run only. Re-run with --apply to write changes.")
            return 0

        now = datetime.now(UTC)
        for tid, _, _, new_rules in updates:
            await session.execute(
                update(RecordingTemplateModel)
                .where(
                    RecordingTemplateModel.id == tid,
                    RecordingTemplateModel.user_id == user_id,
                )
                .values(matching_rules=new_rules, updated_at=now)
            )
        await session.commit()

    print(f"\nApplied {len(updates)} updates.")

    if skipped:
        print("Skipped:")
        for tid, name, reason in skipped:
            print(f"  {tid} {name}: {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
