#!/usr/bin/env -S uv run python
"""Rewrite MTS Link recording.start_time from event-session startsAt.

Uses GET /eventsessions/{id} (same as sync). Dry-run is the default.
Does not invent now() when the API fails — those rows are skipped.

    cd backend
    uv run python scripts/backfill_mts_link_start_time.py
    uv run python scripts/backfill_mts_link_start_time.py --apply
    uv run python scripts/backfill_mts_link_start_time.py --apply --recording-id 42
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC
from pathlib import Path

_PAUSE_SECONDS = 0.5


def _setup_path() -> None:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    os.chdir(project_root)

    from dotenv import load_dotenv

    load_dotenv()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill MTS Link start_time from event session startsAt")
    p.add_argument("--apply", action="store_true", help="Write start_time and session_starts_at to the database")
    p.add_argument("--recording-id", type=int, help="Only this recording id")
    return p.parse_args()


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _run(args: argparse.Namespace) -> int:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from api.auth.encryption import get_encryption
    from api.dependencies import get_async_session_maker
    from api.helpers.mts_link_datetime import load_event_session, resolve_mts_link_start_time, session_starts_at_iso
    from api.repositories.auth_repos import UserCredentialRepository
    from database.automation_models import AutomationJobModel  # noqa: F401
    from database.models import RecordingModel, SourceMetadataModel
    from models.mts_link_auth import create_mts_link_client, create_mts_link_credentials
    from models.recording import SourceType

    session_maker = get_async_session_maker()
    clients: dict = {}
    event_sessions: dict = {}
    scanned = 0
    skipped = 0
    would_update = 0
    updated = 0

    async def load_client(session, source):
        cred_id = source.credential_id
        if cred_id in clients:
            return clients[cred_id]
        if not cred_id:
            clients[cred_id] = None
            return None
        cred_repo = UserCredentialRepository(session)
        credential = await cred_repo.get_by_id(cred_id)
        if not credential:
            clients[cred_id] = None
            return None
        credentials = get_encryption().decrypt_credentials(credential.encrypted_data)
        client = create_mts_link_client(create_mts_link_credentials(credentials))
        clients[cred_id] = client
        return client

    async with session_maker() as session:
        query = (
            select(RecordingModel)
            .join(SourceMetadataModel)
            .options(
                selectinload(RecordingModel.source),
                selectinload(RecordingModel.input_source),
            )
            .where(
                SourceMetadataModel.source_type == SourceType.MTS_LINK,
                RecordingModel.deleted.is_(False),
            )
            .order_by(RecordingModel.id.asc())
        )
        if args.recording_id is not None:
            query = query.where(RecordingModel.id == args.recording_id)

        rows = list((await session.execute(query)).scalars().unique().all())
        print(f"MTS Link recordings: {len(rows)} (apply={args.apply})")

        for rec in rows:
            scanned += 1
            meta = rec.source.meta if rec.source and isinstance(rec.source.meta, dict) else {}
            session_id = meta.get("event_session_id")
            source = rec.input_source
            if session_id is None or source is None:
                print(f"  rec={rec.id} old={rec.start_time} new=— source=skip (no event_session_id or input source)")
                skipped += 1
                continue
            client = await load_client(session, source)
            if client is None:
                print(f"  rec={rec.id} old={rec.start_time} new=— source=skip (no credential)")
                skipped += 1
                continue
            session_payload = await load_event_session(client, session_id, event_sessions, pause_seconds=_PAUSE_SECONDS)
            if session_payload is None:
                print(f"  rec={rec.id} old={rec.start_time} new=— source=skip (eventsession {session_id} failed)")
                skipped += 1
                continue
            new_dt, origin = resolve_mts_link_start_time({}, session_payload, allow_now=False)
            if new_dt is None:
                print(f"  rec={rec.id} old={rec.start_time} new=— source=skip (no session start)")
                skipped += 1
                continue
            old_dt = _aware(rec.start_time)
            same = old_dt is not None and abs((old_dt - new_dt).total_seconds()) < 1
            print(f"  rec={rec.id} old={old_dt} new={new_dt} source={origin}{' (unchanged)' if same else ''}")
            if same:
                continue
            would_update += 1
            if args.apply:
                rec.start_time = new_dt
                if rec.source:
                    merged = dict(meta)
                    iso = session_starts_at_iso(session_payload)
                    if iso:
                        merged["session_starts_at"] = iso
                    rec.source.meta = merged
                updated += 1

        if args.apply:
            await session.commit()

    print(f"scanned={scanned} skipped={skipped} would_update={would_update} written={updated if args.apply else 0}")
    return 0


def main() -> None:
    _setup_path()
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
