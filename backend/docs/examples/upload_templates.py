"""Upload a template JSON bundle via POST /api/v1/templates/import."""

import json
import os
import sys
from pathlib import Path

import httpx

BASE_URL = os.environ.get("LEAP_API_URL", "http://localhost:8000")
EMAIL = os.environ.get("LEAP_API_EMAIL")
PASSWORD = os.environ.get("LEAP_API_PASSWORD")


def login() -> str:
    if not EMAIL or not PASSWORD:
        print("Set LEAP_API_EMAIL and LEAP_API_PASSWORD", file=sys.stderr)
        sys.exit(1)
    resp = httpx.post(f"{BASE_URL}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["access_token"]
    print(f"Logged in as {EMAIL}")
    return token


def main() -> None:
    bundle_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/examples/template_bundle_multi.json")
    dry_run = "--dry-run" in sys.argv

    with bundle_path.open(encoding="utf-8") as f:
        bundle = json.load(f)

    count = len(bundle.get("templates", bundle if isinstance(bundle, list) else []))
    if isinstance(bundle, list):
        bundle = {"leap_template_bundle": 1, "templates": bundle}
        count = len(bundle["templates"])

    print(f"Loaded {count} template(s) from {bundle_path}")
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/v1/templates/import?dry_run={'true' if dry_run else 'false'}"
    resp = httpx.post(url, json=bundle, headers=headers, timeout=120.0)
    print(resp.status_code, resp.text[:500])
    if resp.status_code != 200:
        sys.exit(1)
    data = resp.json()
    if not data.get("ok"):
        sys.exit(1)
    print(f"Done: created={len(data.get('created', []))}, updated={len(data.get('updated', []))}")


if __name__ == "__main__":
    main()
