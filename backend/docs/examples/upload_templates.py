"""One-time script to upload all HSE templates via API."""

import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
EMAIL = "data_culture@hse.ru"
PASSWORD = "Password0!"


def login() -> str:
    """Login and return access token."""
    resp = httpx.post(f"{BASE_URL}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["access_token"]
    print(f"Logged in as {EMAIL}")
    return token


def create_template(token: str, template: dict, idx: int) -> bool:
    """Create a single template. Returns True on success."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.post(f"{BASE_URL}/api/v1/templates", json=template, headers=headers, timeout=30.0)
    if resp.status_code in (200, 201):
        tid = resp.json().get("id", "?")
        print(f"  [{idx}] OK -> id={tid} | {template['name']}")
        return True
    print(f"  [{idx}] FAIL {resp.status_code} | {template['name']} | {resp.text[:200]}")
    return False


def main():
    with Path("docs/examples/hse_templates.json").open(encoding="utf-8") as f:
        templates = json.load(f)

    print(f"Loaded {len(templates)} templates")
    token = login()

    ok = 0
    fail = 0
    for i, t in enumerate(templates, 1):
        if create_template(token, t, i):
            ok += 1
        else:
            fail += 1

    print(f"\nDone: {ok} created, {fail} failed (total {len(templates)})")


if __name__ == "__main__":
    main()
