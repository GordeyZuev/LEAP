"""Companion files stored next to the source video (chat, MTS materials)."""

from __future__ import annotations

import json

from api.schemas.source_extras import SourceExtraFile, SourceExtrasResponse
from database.models import RecordingModel
from logger import get_logger

logger = get_logger()


async def list_source_extras(recording: RecordingModel) -> SourceExtrasResponse:
    """Presigned download URLs for chat.json and files listed in the extras manifest."""
    from config.settings import get_settings
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import StoragePathBuilder, to_storage_key

    builder = StoragePathBuilder()
    user_slug = recording.owner.user_slug
    recording_id = recording.id
    storage = get_storage_backend()
    expires_in = get_settings().storage.s3_presign_expires

    async def _entry(key: str, name: str, size: int | None) -> SourceExtraFile | None:
        if not await storage.exists(key):
            return None
        url = await storage.presigned_url(key, expires_in=expires_in, download_filename=name)
        return SourceExtraFile(
            name=name,
            extension=name.rsplit(".", 1)[-1].lower() if "." in name else "file",
            size=size,
            url=url,
        )

    chat = await _entry(
        to_storage_key(builder.recording_source_chat(user_slug, recording_id)),
        f"recording-{recording_id}-chat.json",
        None,
    )

    files: list[SourceExtraFile] = []
    manifest_key = to_storage_key(builder.recording_source_files_manifest(user_slug, recording_id))
    if await storage.exists(manifest_key):
        try:
            manifest = json.loads((await storage.load(manifest_key)).decode())
        except (ValueError, UnicodeDecodeError) as e:
            logger.warning("Unreadable source extras manifest | rec={} error={}", recording_id, e)
            manifest = []

        for row in manifest if isinstance(manifest, list) else []:
            if not isinstance(row, dict) or not row.get("storage_key"):
                continue
            entry = await _entry(
                str(row["storage_key"]),
                str(row.get("name") or row.get("stored_as") or "attachment"),
                row.get("size") if isinstance(row.get("size"), int) else None,
            )
            if entry:
                files.append(entry)

    return SourceExtrasResponse(chat=chat, files=files, expires_in=expires_in)
