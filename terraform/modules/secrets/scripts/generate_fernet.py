#!/usr/bin/env python3
"""Emit a fresh Fernet key as JSON for Terraform's `external` data source.

The Fernet key format is urlsafe-base64-encoded 32 random bytes. We avoid the
`cryptography` library dependency by using stdlib `secrets` + `base64`.

Terraform's `external` provider expects:
  - stdin:  ignored (we don't read input)
  - stdout: a single JSON object whose values are all strings
"""

from __future__ import annotations

import base64
import json
import secrets


def main() -> None:
    raw = secrets.token_bytes(32)
    fernet_key = base64.urlsafe_b64encode(raw).decode("ascii")
    json.dump({"key": fernet_key}, fp=__import__("sys").stdout)


if __name__ == "__main__":
    main()
