#!/usr/bin/env -S uv run python
"""Smoke-test MTS Link UserAPI with an org API key.

Run from ``backend/`` (requires network)::

    export MTS_LINK_API_KEY='your-key'
    uv run python scripts/mts_link_smoke.py

Optional::

    uv run python scripts/mts_link_smoke.py --from '2024-01-01 00:00:00' --limit 5
    uv run python scripts/mts_link_smoke.py --list-members
    uv run python scripts/mts_link_smoke.py --list-members --query пономарен
    uv run python scripts/mts_link_smoke.py --list-members --member-email user@example.com
    uv run python scripts/mts_link_smoke.py --user-id 12345678 --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _setup_path() -> None:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    os.chdir(project_root)

    from dotenv import load_dotenv

    load_dotenv()


def _resolve_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    if args.token_file:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    env = os.getenv("MTS_LINK_API_KEY", "").strip()
    if env:
        return env
    raise SystemExit(
        "No API key: set MTS_LINK_API_KEY, or pass --token / --token-file",
    )


def _parse_args() -> argparse.Namespace:
    default_from = (datetime.now(UTC) - timedelta(days=365)).strftime("%Y-%m-%d 00:00:00")
    default_to = datetime.now(UTC).strftime("%Y-%m-%d 23:59:59")

    p = argparse.ArgumentParser(description="MTS Link UserAPI smoke test")
    p.add_argument("--token", help="Org API key (overrides MTS_LINK_API_KEY)")
    p.add_argument("--token-file", help="File containing the API key (one line)")
    p.add_argument("--from", dest="from_date", default=default_from, help="records from (required by API)")
    p.add_argument("--to", dest="to_date", default=default_to, help="records to")
    p.add_argument("--limit", type=int, default=5, help="records page size (1–500)")
    p.add_argument("--skip-converted", action="store_true", help="Skip GET /converted-records")
    p.add_argument(
        "--list-members",
        action="store_true",
        help="List org employees (GET /organization/members) with userId and email",
    )
    p.add_argument(
        "--query",
        help="Local substring filter on name, email, or position (case-insensitive; after fetching all pages)",
    )
    p.add_argument("--member-email", help="Local substring filter on email (after fetching all pages)")
    p.add_argument("--member-role", choices=("admin", "lecturer", "ADMIN", "LECTURER"), help="Filter by role")
    p.add_argument(
        "--user-id",
        type=int,
        help="Filter GET /records by MTS Link userId (from --list-members)",
    )
    return p.parse_args()


def _summarize_record(rec: dict) -> dict:
    event_session = rec.get("eventSession") or {}
    create_user = event_session.get("createUser") if isinstance(event_session, dict) else None
    owner = None
    if isinstance(create_user, dict):
        owner = {
            "id": create_user.get("id"),
            "email": create_user.get("email"),
            "name": " ".join(p for p in (create_user.get("secondName"), create_user.get("name")) if p).strip()
            or create_user.get("nickname"),
        }
    return {
        "id": rec.get("id"),
        "name": rec.get("name"),
        "size": rec.get("size"),
        "createAt": rec.get("createAt"),
        "eventSessionId": event_session.get("id") if isinstance(event_session, dict) else None,
        "owner": owner,
        "link": rec.get("link"),
    }


def _summarize_member(member: dict) -> dict:
    return {
        "userId": member.get("id"),
        "membershipId": member.get("membershipId"),
        "role": member.get("role"),
        "email": member.get("email"),
        "name": " ".join(
            p for p in (member.get("secondName"), member.get("name"), member.get("patrName")) if p
        ).strip(),
        "position": member.get("position"),
    }


def _member_haystack(member: dict) -> str:
    summary = _summarize_member(member)
    return " ".join(str(summary.get(key) or "") for key in ("email", "name", "position", "userId", "role")).casefold()


async def _fetch_all_members(client, *, role: str | None) -> list[dict]:
    """Walk GET /organization/members pages (max 500 per page) until a short page."""
    members: list[dict] = []
    page = 1
    page_size = 500
    while True:
        batch = await client.list_organization_members(role=role, page=page, per_page=page_size)
        members.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
        if page > 50:
            print(f"WARN stopped after {page - 1} pages ({len(members)} rows)")
            break
    return members


async def _print_members(client, args: argparse.Namespace) -> int:
    from api.mts_link_api import MtsLinkAPIError

    role = args.member_role.upper() if args.member_role and args.member_role.islower() else args.member_role
    try:
        members = await _fetch_all_members(client, role=role)
    except MtsLinkAPIError as e:
        print(f"FAIL list_organization_members: {e}")
        return 1

    print(f"OK GET /organization/members — {len(members)} employee(s) before local filter")
    needles = [s.casefold() for s in (args.query, args.member_email) if s]
    if needles:
        members = [m for m in members if all(n in _member_haystack(m) for n in needles)]
        print(f"after filter — {len(members)} match(es)")

    for i, member in enumerate(members):
        print(f"  [{i + 1}] {json.dumps(_summarize_member(member), ensure_ascii=False)}")
    return 0


async def _run(args: argparse.Namespace) -> int:
    from api.mts_link_api import MtsLinkAPI, MtsLinkAPIError

    token = _resolve_token(args)
    client = MtsLinkAPI(api_token=token)

    if args.list_members:
        print("=== MTS Link organization members ===")
        if args.query:
            print(f"filter query={args.query!r}")
        if args.member_email:
            print(f"filter email={args.member_email!r}")
        if args.member_role:
            print(f"filter role={args.member_role!r}")
        print()
        return await _print_members(client, args)

    print("=== MTS Link smoke test ===")
    print(f"from={args.from_date!r} to={args.to_date!r} limit={args.limit}", end="")
    if args.user_id is not None:
        print(f" userId={args.user_id}", end="")
    print()
    print()

    try:
        records = await client.list_records(
            from_date=args.from_date,
            to_date=args.to_date,
            limit=args.limit,
            offset=0,
            user_id=args.user_id,
        )
    except MtsLinkAPIError as e:
        print(f"FAIL list_records: {e}")
        return 1

    print(f"OK GET /records — {len(records)} item(s)")
    for i, rec in enumerate(records[: args.limit]):
        summary = _summarize_record(rec)
        print(f"  [{i + 1}] {json.dumps(summary, ensure_ascii=False)}")

    if not records:
        print("\nNo online records in range. Try an earlier --from date.")
        return 0

    first = records[0]
    event_session = first.get("eventSession") or {}
    event_session_id = event_session.get("id") if isinstance(event_session, dict) else None
    record_id = first.get("id")

    if event_session_id:
        print(f"\n--- GET /eventsessions/{event_session_id}/converted-records ---")
        try:
            converted = await client.get_converted_records_by_event_session(event_session_id)
            print(json.dumps(converted, ensure_ascii=False, indent=2)[:2000])
        except MtsLinkAPIError as e:
            print(f"WARN converted-records: {e}")

    if record_id:
        print(f"\n(first record id={record_id} — use for POST /records/{{id}}/conversions in a later step)")

    if not args.skip_converted:
        print("\n--- GET /converted-records (recent conversions) ---")
        try:
            conv_from = args.from_date.split()[0] if args.from_date else None
            conv_to = args.to_date.split()[0] if args.to_date else None
            conv_list = await client.list_converted_records(
                from_date=conv_from,
                to_date=conv_to,
                page=1,
                per_page=10,
            )
            items = (conv_list.get("data") or {}).get("items") if isinstance(conv_list.get("data"), dict) else None
            if items is None and isinstance(conv_list.get("items"), list):
                items = conv_list["items"]
            count = len(items) if isinstance(items, list) else 0
            print(f"OK — {count} conversion row(s) on page 1")
            if isinstance(items, list):
                for row in items[:3]:
                    state = row.get("state")
                    es = (row.get("recordFile") or {}).get("eventSession") or {}
                    print(
                        f"  conversion id={row.get('id')} state={state!r} "
                        f"eventSession={es.get('id') if isinstance(es, dict) else None}"
                    )
        except MtsLinkAPIError as e:
            print(f"WARN list_converted_records: {e}")

    print("\nDone.")
    return 0


def main() -> None:
    _setup_path()
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
