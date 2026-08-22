#!/usr/bin/env python3
"""Normalize bloated recording.processing_preferences to diff-only overrides.

Run post-deploy from backend/:
  uv run python scripts/normalize_processing_preferences.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import copy

from sqlalchemy import select

from api.dependencies import get_async_session_maker
from api.services.config_resolver import ConfigResolver, ResolveContext
from database.models import RecordingModel


def _diff(base: dict, full: dict) -> dict:
    """Keep only keys in full that differ from base (shallow-ish for JSONB prefs)."""
    delta: dict = {}
    for key, value in full.items():
        if key not in base:
            delta[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            nested = _diff(base[key], value)
            if nested:
                delta[key] = nested
        elif value != base.get(key):
            delta[key] = copy.deepcopy(value)
    return delta


async def run(*, dry_run: bool) -> None:
    session_factory = get_async_session_maker()
    async with session_factory() as session:
        result = await session.execute(select(RecordingModel).where(RecordingModel.processing_preferences.isnot(None)))
        recordings = list(result.scalars().all())
        updated = 0
        for recording in recordings:
            prefs = recording.processing_preferences or {}
            saved = copy.deepcopy(prefs)
            recording.processing_preferences = None
            await session.flush()
            resolver = ConfigResolver(session)
            base = await resolver.resolve(ResolveContext(user_id=recording.user_id, recording=recording))
            base_bundle = {
                "processing_config": base.processing,
                "metadata_config": base.metadata,
                "output_config": base.output,
            }
            recording.processing_preferences = saved
            delta = _diff(base_bundle, prefs)
            if delta != prefs:
                recording.processing_preferences = delta or None
                updated += 1
        if dry_run:
            await session.rollback()
            print(f"Would normalize {updated} of {len(recordings)} recordings with preferences")
        else:
            await session.commit()
            print(f"Normalized {updated} of {len(recordings)} recordings with preferences")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
