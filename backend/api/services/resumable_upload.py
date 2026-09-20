"""Temporary, owner-scoped upload sessions for large local videos."""

import fcntl
import json
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from file_storage.path_builder import StoragePathBuilder

CHUNK_BYTES = 8 * 1024 * 1024
SESSION_TTL_SECONDS = 24 * 60 * 60
_ID = re.compile(r"^[0-9a-f]{32}$")


def upload_dir() -> Path:
    path = StoragePathBuilder().temp_dir() / "resumable"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _paths(upload_id: str) -> tuple[Path, Path, Path]:
    if not _ID.fullmatch(upload_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    root = upload_dir()
    return root / f"{upload_id}.json", root / f"{upload_id}.part", root / f"{upload_id}.lock"


@contextmanager
def lock_upload(upload_id: str) -> Iterator[None]:
    meta_path, _, lock_path = _paths(upload_id)
    if not meta_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload is busy; retry shortly") from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def save_session(upload_id: str, data: dict[str, Any]) -> None:
    meta_path, _, _ = _paths(upload_id)
    temporary = meta_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(meta_path)


def read_session(upload_id: str, user_id: str) -> tuple[dict[str, Any], Path]:
    meta_path, part_path, _ = _paths(upload_id)
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found") from exc
    if data.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    if time.time() - data.get("updated_at", 0) > SESSION_TTL_SECONDS:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Upload expired; select the file again")
    return data, part_path


def session_status(data: dict[str, Any], part_path: Path) -> dict[str, Any]:
    return {
        "upload_id": data["upload_id"],
        "offset": data["size"]
        if data.get("recording_id")
        else min(part_path.stat().st_size if part_path.exists() else 0, data["size"]),
        "size": data["size"],
        "fingerprint": data["fingerprint"],
        "chunk_size": CHUNK_BYTES,
        "recording_id": data.get("recording_id"),
        "display_name": data["display_name"],
        "auto_run": data["auto_run"],
    }


def create_session(
    user_id: str, filename: str, size: int, display_name: str, auto_run: bool, fingerprint: str
) -> dict[str, Any]:
    cleanup_expired()
    upload_id = uuid.uuid4().hex
    data = {
        "upload_id": upload_id,
        "user_id": user_id,
        "filename": filename,
        "size": size,
        "display_name": display_name,
        "auto_run": auto_run,
        "fingerprint": fingerprint,
        "updated_at": time.time(),
    }
    _, part_path, _ = _paths(upload_id)
    part_path.touch(exist_ok=False)
    save_session(upload_id, data)
    return session_status(data, part_path)


def cleanup_expired() -> None:
    now = time.time()
    for meta_path in upload_dir().glob("*.json"):
        try:
            if now - meta_path.stat().st_mtime <= SESSION_TTL_SECONDS:
                continue
            upload_id = meta_path.stem
            with lock_upload(upload_id):
                if now - meta_path.stat().st_mtime <= SESSION_TTL_SECONDS:
                    continue
                _, part_path, _ = _paths(upload_id)
                meta_path.unlink(missing_ok=True)
                part_path.unlink(missing_ok=True)
        except (OSError, HTTPException):
            continue
