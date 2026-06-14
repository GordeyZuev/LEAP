"""
Quick AssemblyAI transcription test.

Usage (from backend/):
    uv run python scripts/test_assemblyai.py <audio_file> [term1] [term2] ...

Example:
    uv run python scripts/test_assemblyai.py /tmp/lecture.mp3 FastAPI SQLAlchemy "машинное обучение"
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

CREDS_FILE = Path(__file__).parent.parent / "config" / "assemblyai_creds.json"
BASE_URL = "https://api.assemblyai.com"
POLL_INTERVAL = 3.0


def load_api_key() -> str:
    data = json.loads(CREDS_FILE.read_text())
    key = data.get("api_key", "")
    if not key:
        sys.exit(f"api_key missing in {CREDS_FILE}")
    return key


async def upload_file(client: httpx.AsyncClient, api_key: str, path: Path) -> str:
    print(f"  Uploading {path.name} ({path.stat().st_size // 1024} KB)...")
    r = await client.post(
        f"{BASE_URL}/v2/upload",
        headers={"Authorization": api_key},
        content=path.read_bytes(),
        timeout=300.0,
    )
    r.raise_for_status()
    url = r.json()["upload_url"]
    print(f"  Upload URL: {url[:80]}...")
    return url


async def submit(client: httpx.AsyncClient, api_key: str, audio_url: str, keyterms: list[str]) -> str:
    payload = {
        "audio_url": audio_url,
        "speech_models": ["universal-3-pro", "universal-2"],
        "punctuate": True,
        "format_text": True,
        "language_code": "ru",
        "audio_start_from": None,
        "audio_end_at": None,
    }
    if keyterms:
        payload["keyterms_prompt"] = keyterms

    print(f"\n  Payload: {json.dumps({k: v for k, v in payload.items() if k != 'audio_url'}, ensure_ascii=False)}")

    r = await client.post(
        f"{BASE_URL}/v2/transcript",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60.0,
    )
    r.raise_for_status()
    tid = r.json()["id"]
    print(f"  transcript_id = {tid}")
    return tid


async def poll(client: httpx.AsyncClient, api_key: str, tid: str) -> dict:
    url = f"{BASE_URL}/v2/transcript/{tid}"
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        r = await client.get(url, headers={"Authorization": api_key}, timeout=30.0)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        elapsed = time.monotonic() - start
        print(f"  [{elapsed:5.1f}s] attempt={attempt} status={status}")
        if status == "completed":
            return data
        if status == "error":
            sys.exit(f"AssemblyAI error: {data.get('error')}")
        await asyncio.sleep(POLL_INTERVAL)


async def fetch_sentences(client: httpx.AsyncClient, api_key: str, tid: str) -> list[dict]:
    r = await client.get(
        f"{BASE_URL}/v2/transcript/{tid}/sentences",
        headers={"Authorization": api_key},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json().get("sentences", [])


def print_section(title: str, data) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)
    if isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data)


async def main(audio_path: Path, keyterms: list[str]) -> None:
    api_key = load_api_key()
    print(f"\nAssemblyAI test | file={audio_path.name} | keyterms={keyterms}")

    async with httpx.AsyncClient() as client:
        # Step 1: upload
        print("\n[1/4] Uploading file...")
        audio_url = await upload_file(client, api_key, audio_path)

        # Step 2: submit
        print("\n[2/4] Submitting transcript job...")
        tid = await submit(client, api_key, audio_url, keyterms)

        # Step 3: poll
        print("\n[3/4] Polling...")
        result = await poll(client, api_key, tid)

        # Step 4: /sentences
        print("\n[4/4] Fetching /sentences endpoint...")
        sentences = await fetch_sentences(client, api_key, tid)

    # ── Output ──────────────────────────────────────────────────────────
    print_section("FULL TEXT", result.get("text", ""))
    print_section("LANGUAGE", result.get("language_code"))

    words = result.get("words", [])
    print_section(f"WORDS (first 10 of {len(words)})", words[:10])

    # Check punctuation in words
    print("\n── Punctuation check (words ending with . ! ? …) ──")
    punct_words = [w for w in words if str(w.get("text", "")).rstrip().endswith((".", "!", "?", "…"))]
    print(f"  Words with sentence-ending punctuation: {len(punct_words)} / {len(words)}")
    print(f"  Examples: {[w.get('text') for w in punct_words[:5]]}")

    print_section(f"SENTENCES from /sentences (first 5 of {len(sentences)})", sentences[:5])

    # Raw dump to file
    out = audio_path.with_suffix(".assemblyai_raw.json")
    out.write_text(
        json.dumps(
            {
                "transcript_id": tid,
                "text": result.get("text"),
                "language_code": result.get("language_code"),
                "audio_duration": result.get("audio_duration"),
                "words": words,
                "sentences": sentences,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"\n  Full output saved to: {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    audio = Path(sys.argv[1])
    if not audio.exists():
        sys.exit(f"File not found: {audio}")

    vocab = sys.argv[2:]
    asyncio.run(main(audio, vocab))
