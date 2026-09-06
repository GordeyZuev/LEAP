#!/usr/bin/env -S uv run python
"""Apply MTS Link duration/blank filter to existing recordings.

Uses GET /fileSystem/file/{recordId} (same as sync). Dry-run is the default.

    cd backend
    uv run python scripts/backfill_mts_link_blank.py
    uv run python scripts/backfill_mts_link_blank.py --apply
    uv run python scripts/backfill_mts_link_blank.py --apply --recording-id 42
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_PAUSE_SECONDS = 0.5


def _setup_path() -> None:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    os.chdir(project_root)

    from dotenv import load_dotenv

    load_dotenv()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill MTS Link duration and blank_record")
    p.add_argument("--apply", action="store_true", help="Write duration/blank/status to the database")
    p.add_argument("--recording-id", type=int, help="Only this recording id")
    return p.parse_args()


async def _run(args: argparse.Namespace) -> int:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from api.auth.encryption import get_encryption
    from api.dependencies import get_async_session_maker
    from api.helpers.blank_record import (
        BLANK_REASON_TOO_SHORT,
        apply_blank_record,
        is_mts_link_blank,
        mts_link_record_id_from_source_key,
        positive_duration_seconds,
    )
    from api.mts_link_api import MtsLinkAPIError
    from api.repositories.auth_repos import UserCredentialRepository
    from database.automation_models import AutomationJobModel  # noqa: F401
    from database.models import RecordingModel, SourceMetadataModel
    from models.mts_link_auth import create_mts_link_client, create_mts_link_credentials
    from models.recording import SourceType

    session_maker = get_async_session_maker()
    clients: dict = {}
    scanned = 0
    would_blank = 0
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
            source_key = rec.source.source_key if rec.source else None
            record_id = mts_link_record_id_from_source_key(source_key)
            source = rec.input_source
            if record_id is None or source is None:
                print(f"  skip rec={rec.id} (no mts record id or input source)")
                continue
            client = await load_client(session, source)
            if client is None:
                print(f"  skip rec={rec.id} (no credential)")
                continue
            try:
                payload = await client.get_file(record_id)
            except MtsLinkAPIError as e:
                print(f"  rec={rec.id} record={record_id} FAIL {e}")
                await asyncio.sleep(_PAUSE_SECONDS)
                continue
            duration = positive_duration_seconds(payload.get("duration"))
            is_blank = is_mts_link_blank(duration)
            print(
                f"  rec={rec.id} record={record_id} duration={duration} "
                f"blank={is_blank} status={rec.status} was_blank={rec.blank_record}"
            )
            if is_blank:
                would_blank += 1
            if args.apply and duration is not None:
                rec.duration = duration
                apply_blank_record(rec, is_blank, reason=BLANK_REASON_TOO_SHORT)
                updated += 1
            await asyncio.sleep(_PAUSE_SECONDS)

        if args.apply:
            await session.commit()

    print(f"scanned={scanned} blank={would_blank} written={updated if args.apply else 0}")
    return 0


def main() -> None:
    _setup_path()
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
