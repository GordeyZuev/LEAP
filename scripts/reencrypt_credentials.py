#!/usr/bin/env python3
"""Re-encrypt all user credentials from old key to new Fernet key.

Usage:
    # Dry-run (read-only, shows what would change):
    uv run python scripts/reencrypt_credentials.py --dry-run

    # Execute:
    uv run python scripts/reencrypt_credentials.py

Environment variables:
    SECURITY_ENCRYPTION_KEY   - New Fernet key (target). Required.
    OLD_ENCRYPTION_KEY        - Old Fernet key to decrypt existing data.
                                If empty, uses SECURITY_ENCRYPTION_KEY (same key, for stripping prefixes).

See docs/CREDENTIAL_SECURITY.md for details.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


def _setup_path() -> None:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    os.chdir(project_root)

    from dotenv import load_dotenv

    load_dotenv()


def _build_old_fernet(settings: Any) -> Any:
    """Build Fernet for decrypting existing data."""
    from cryptography.fernet import Fernet

    old_key = os.getenv("OLD_ENCRYPTION_KEY", "")
    if old_key:
        print(f"  Old key source: OLD_ENCRYPTION_KEY env ({len(old_key)} chars)")
        return Fernet(old_key.encode())

    key = settings.security.encryption_key
    print(f"  Old key source: SECURITY_ENCRYPTION_KEY ({len(key)} chars)")
    return Fernet(key.encode())


def _build_new_fernet(settings: Any) -> Any:
    """Build Fernet for encrypting with new key."""
    from cryptography.fernet import Fernet

    new_key = settings.security.encryption_key
    if not new_key:
        print("ERROR: SECURITY_ENCRYPTION_KEY is empty. Set it in .env before running.")
        print('Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"')
        sys.exit(1)
    print(f"  New key source: SECURITY_ENCRYPTION_KEY ({len(new_key)} chars)")
    return Fernet(new_key.encode())


async def _run(dry_run: bool) -> None:
    from cryptography.fernet import InvalidToken
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from config.settings import get_settings

    settings = get_settings()

    print("=== Credential Re-encryption ===")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"  Database: {settings.database.host}:{settings.database.port}/{settings.database.database}")
    print()

    old_fernet = _build_old_fernet(settings)
    new_fernet = _build_new_fernet(settings)
    print()

    engine = create_async_engine(settings.database.url)

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id, platform, account_name, encrypted_data FROM user_credentials"))
        rows = result.fetchall()

        print(f"Found {len(rows)} credential(s)")
        print()

        success = 0
        failed = 0
        skipped = 0

        for row in rows:
            cred_id, platform, account_name, encrypted_data = row
            label = f"  [{cred_id}] {platform}" + (f" ({account_name})" if account_name else "")

            # Strip v2: prefix if present (migration from old format)
            raw = encrypted_data.removeprefix("v2:")

            try:
                decrypted_bytes = old_fernet.decrypt(raw.encode())
                json.loads(decrypted_bytes.decode())
            except InvalidToken:
                print(f"{label}: FAILED — could not decrypt with old key")
                failed += 1
                continue
            except json.JSONDecodeError:
                print(f"{label}: FAILED — decrypted but invalid JSON")
                failed += 1
                continue

            new_ciphertext = new_fernet.encrypt(decrypted_bytes).decode()

            if new_ciphertext == raw and not encrypted_data.startswith("v2:"):
                print(f"{label}: SKIP — already on current key")
                skipped += 1
                continue

            if dry_run:
                print(f"{label}: OK — would re-encrypt")
            else:
                await conn.execute(
                    text("UPDATE user_credentials SET encrypted_data = :data WHERE id = :id"),
                    {"data": new_ciphertext, "id": cred_id},
                )
                print(f"{label}: OK — re-encrypted")
            success += 1

        print()
        print(f"Done: {success} re-encrypted, {skipped} skipped, {failed} failed")
        if failed > 0:
            print("WARNING: Some credentials could not be decrypted. They need manual re-connection.")

    await engine.dispose()

    if failed > 0:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-encrypt all user credentials")
    parser.add_argument("--dry-run", action="store_true", help="Read-only mode")
    args = parser.parse_args()

    asyncio.run(_run(args.dry_run))


if __name__ == "__main__":
    _setup_path()
    main()
