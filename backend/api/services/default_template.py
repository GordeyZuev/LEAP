"""Default template seeding and user_config → template mapping."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import DEFAULT_USER_CONFIG
from database.template_models import RecordingTemplateModel


def upload_config_to_output(upload: dict[str, Any]) -> dict[str, Any]:
    """Map legacy user ``upload`` block to template ``output_config`` shape."""
    result: dict[str, Any] = {"preset_ids": [], "auto_upload": False, "upload_captions": True}
    if not upload:
        return result
    for key in ("auto_upload", "upload_captions", "default_platforms"):
        if key in upload:
            result[key] = copy.deepcopy(upload[key])
    preset_ids = upload.get("default_preset_ids")
    if isinstance(preset_ids, dict) and preset_ids:
        result["preset_ids"] = list(preset_ids.values())
    elif isinstance(upload.get("preset_ids"), list):
        result["preset_ids"] = copy.deepcopy(upload["preset_ids"])
    return result


def build_processing_config_from_user(effective_user_config: dict[str, Any]) -> dict[str, Any]:
    """Build template processing_config JSON from flat user config."""
    processing: dict[str, Any] = {}
    transcription = effective_user_config.get("transcription")
    if not isinstance(transcription, dict):
        transcription = copy.deepcopy(DEFAULT_USER_CONFIG.get("transcription") or {})
    processing["transcription"] = copy.deepcopy(transcription)
    trimming = effective_user_config.get("trimming")
    if isinstance(trimming, dict):
        processing["trimming"] = copy.deepcopy(trimming)
    vocab = effective_user_config.get("transcription_vocabulary")
    if vocab is None and isinstance(transcription, dict):
        vocab = transcription.get("vocabulary")
    if isinstance(vocab, list) and vocab:
        processing["transcription_vocabulary"] = copy.deepcopy(vocab)
    return processing


def build_default_template_payload(effective_user_config: dict[str, Any]) -> dict[str, Any]:
    """Build JSONB fields for a user's Default Template from effective user config."""
    metadata = effective_user_config.get("metadata")
    upload = effective_user_config.get("upload") or {}
    output = upload_config_to_output(upload)
    return {
        "processing_config": build_processing_config_from_user(effective_user_config),
        "metadata_config": copy.deepcopy(metadata) if isinstance(metadata, dict) else {},
        "output_config": output,
    }


def account_only_user_config(config_data: dict[str, Any]) -> dict[str, Any]:
    """Strip pipeline keys; keep retention, download, platforms."""
    keep = ("retention", "download", "platforms")
    return {k: copy.deepcopy(config_data[k]) for k in keep if k in config_data}


def product_default_account_config() -> dict[str, Any]:
    """Account-level config for new users (no pipeline fields)."""
    return account_only_user_config(DEFAULT_USER_CONFIG)


async def ensure_default_template(session: AsyncSession, user_id: str) -> RecordingTemplateModel:
    """Create the user's Default Template from product defaults if missing."""
    from api.repositories.config_repos import UserConfigRepository
    from api.repositories.template_repos import RecordingTemplateRepository
    from config.settings import DEFAULT_USER_CONFIG

    repo = RecordingTemplateRepository(session)
    existing = await repo.find_default_by_user(user_id)
    if existing:
        return existing

    config_repo = UserConfigRepository(session)
    effective = await config_repo.get_effective_config(user_id)
    if not any(k in effective for k in ("transcription", "metadata", "upload", "trimming")):
        effective = DEFAULT_USER_CONFIG

    payload = build_default_template_payload(effective)
    template = RecordingTemplateModel(
        user_id=user_id,
        name="Default",
        description="Base video processing defaults",
        is_default=True,
        is_active=True,
        is_draft=False,
        matching_rules=None,
        processing_config=payload["processing_config"] or None,
        metadata_config=payload["metadata_config"] or None,
        output_config=payload["output_config"] or None,
    )
    session.add(template)
    await session.flush()
    return template


async def promote_template_to_default(
    session: AsyncSession,
    user_id: str,
    template_id: int,
) -> RecordingTemplateModel:
    """Move the base-template flag to an existing named template (promote)."""
    from api.repositories.template_repos import RecordingTemplateRepository

    repo = RecordingTemplateRepository(session)
    target = await repo.find_by_id(template_id, user_id)
    if not target:
        raise ValueError("Template not found")
    if target.is_default:
        raise ValueError("Template is already the base template")
    if target.is_draft:
        raise ValueError("Cannot promote a draft template")
    if not target.is_active:
        raise ValueError("Cannot promote an inactive template")

    current_default = await repo.find_default_by_user(user_id)
    if not current_default:
        current_default = await ensure_default_template(session, user_id)

    if current_default.id == target.id:
        return target

    await session.execute(
        update(RecordingTemplateModel)
        .where(
            RecordingTemplateModel.user_id == user_id,
            RecordingTemplateModel.is_default.is_(True),
        )
        .values(is_default=False, updated_at=datetime.now(UTC))
    )
    await session.flush()

    target.is_default = True
    await repo.update(target)
    return target
