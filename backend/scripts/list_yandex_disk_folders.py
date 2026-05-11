#!/usr/bin/env -S uv run python
"""List folders on Yandex Disk (pick ``folder_path`` for Input Sources).

Run from ``backend/``::

    PYTHONPATH=$PWD uv run python scripts/list_yandex_disk_folders.py
    PYTHONPATH=$PWD uv run python scripts/list_yandex_disk_folders.py --published

**Что видит API (важно для «общих» каталогов):**

- **Личное дерево** — ``GET /v1/disk/resources?path=…`` (режим по умолчанию): папки с путями вида
  ``disk:/…``. Сюда попадают ваши каталоги и **принятые** приглашения Yandex 360 (копия на Диске);
  см. https://yandex.com/support/yandex-360/customers/disk/web/en/share/shared-folders-to-me
- **Чужая публичная ссылка** (``https://disk.yandex.ru/d/…``) **не** появляется в этом дереве — у неё
  нет вашего ``folder_path``. В LEAP для input используйте ``public_url``, не OAuth-путь.
- **Вы сами включили публичный доступ** к файлу/папке — такие объекты перечисляет
  ``GET /v1/disk/resources/public`` (в скрипте: ``--published``).

Token resolution (first match):

1. ``--token``
2. ``--token-file`` (file with one line: OAuth access token)
3. Decrypted ``oauth_token`` from ``user_credentials`` (``--credential-id``, default **11**)
4. ``YANDEX_DISK_OAUTH_TOKEN``

Step (3) needs ``DATABASE_URL`` / DB settings, ``SECURITY_ENCRYPTION_KEY``, and a row with
``platform == yandex_disk``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def _setup_path() -> None:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    os.chdir(project_root)

    from dotenv import load_dotenv

    load_dotenv()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="List Yandex Disk folders (OAuth).")
    p.add_argument(
        "--path",
        default="/",
        help="Folder path to start from (default: / — disk root).",
    )
    p.add_argument(
        "--credential-id",
        type=int,
        default=11,
        help="user_credentials.id when loading token from DB (default: 11).",
    )
    p.add_argument("--token", default=None, help="OAuth access token (overrides DB and env).")
    p.add_argument("--token-file", default=None, help="Path to file containing the token.")
    p.add_argument(
        "--recursive",
        action="store_true",
        help="List subfolders recursively (breadth-first per folder).",
    )
    p.add_argument(
        "--max-depth",
        type=int,
        default=None,
        metavar="N",
        help="With --recursive: max folder depth relative to start (0 = only --path).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Page size for list_folder (default: 200).",
    )
    p.add_argument(
        "--disk-info",
        action="store_true",
        help="Print GET /v1/disk summary before listing.",
    )
    p.add_argument(
        "--published",
        action="store_true",
        help="List resources you published (GET /v1/disk/resources/public), not disk tree.",
    )
    return p.parse_args()


def _read_token_file(path: str) -> str:
    raw = Path(path).read_text(encoding="utf-8").strip()
    if not raw:
        raise SystemExit(f"Token file is empty: {path}")
    return raw.splitlines()[0].strip()


async def _token_from_db(credential_id: int) -> str:
    from api.auth.encryption import get_encryption
    from api.dependencies import get_async_session_maker
    from api.repositories.auth_repos import UserCredentialRepository
    from database.automation_models import AutomationJobModel  # noqa: F401 - UserModel relationship

    async_session = get_async_session_maker()
    async with async_session() as session:
        repo = UserCredentialRepository(session)
        cred = await repo.get_by_id(credential_id)
        if not cred:
            raise SystemExit(f"user_credentials id={credential_id} not found.")
        if cred.platform != "yandex_disk":
            raise SystemExit(f"Credential {credential_id} has platform={cred.platform!r}, expected 'yandex_disk'.")
        data = get_encryption().decrypt_credentials(cred.encrypted_data)
        token = data.get("oauth_token")
        if not token or not isinstance(token, str):
            raise SystemExit("Decrypted credentials have no non-empty 'oauth_token'.")
        return token


async def _resolve_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    if args.token_file:
        return _read_token_file(args.token_file)
    try:
        return await _token_from_db(args.credential_id)
    except Exception:
        env_tok = os.getenv("YANDEX_DISK_OAUTH_TOKEN", "").strip()
        if env_tok:
            return env_tok
        raise


async def _list_folder_page(client, path: str, limit: int, offset: int) -> list[dict]:
    data = await client.list_folder(path, limit=limit, offset=offset)
    return (data.get("_embedded") or {}).get("items") or []


async def _print_one_level(client, path: str, limit: int) -> list[str]:
    """Return subfolder paths (type == dir)."""
    subdirs: list[str] = []
    offset = 0
    while True:
        items = await _list_folder_page(client, path, limit, offset)
        for it in items:
            if it.get("type") != "dir":
                continue
            p = it.get("path") or ""
            subdirs.append(p)
            print(p)
        if len(items) < limit:
            break
        offset += limit
    return subdirs


async def _run_recursive(
    client,
    root: str,
    limit: int,
    max_depth: int | None,
    depth: int,
) -> None:
    if max_depth is not None and depth > max_depth:
        return
    subdirs = await _print_one_level(client, root, limit)
    for sub in subdirs:
        await _run_recursive(client, sub, limit, max_depth, depth + 1)


async def _print_published(client, limit: int) -> None:
    """All published resources (paginated)."""
    offset = 0
    while True:
        data = await client.list_published_resources(limit=limit, offset=offset)
        items = (data.get("_embedded") or {}).get("items") or []
        for it in items:
            typ = it.get("type") or "?"
            path = it.get("path") or ""
            pub_url = it.get("public_url") or ""
            line = f"{typ}\t{path}"
            if pub_url:
                line = f"{line}\t{pub_url}"
            elif it.get("public_key"):
                line = f"{line}\tpublic_key={it['public_key'][:24]}…"
            print(line)
        if len(items) < limit:
            break
        offset += limit


async def _async_main() -> None:
    _setup_path()
    args = _parse_args()

    from yandex_disk_module.client import YandexDiskClient

    token = await _resolve_token(args)
    client = YandexDiskClient(oauth_token=token)

    if args.disk_info:
        info = await client.get_disk_info()
        total = info.get("total_space")
        used = info.get("used_space")
        trash = info.get("trash_size")
        print(f"# disk: total={total} used={used} trash={trash}")

    if args.published:
        await _print_published(client, args.limit)
        return

    start = args.path.rstrip("/") or "/"
    if not start.startswith("/"):
        start = "/" + start

    if args.recursive:
        await _run_recursive(client, start, args.limit, args.max_depth, 0)
    else:
        await _print_one_level(client, start, args.limit)


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
