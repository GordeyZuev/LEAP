"""Seed default templates from user_configs and strip pipeline keys

Revision ID: 038
Revises: 037
Create Date: 2026-08-22
"""

from __future__ import annotations

import copy
import json

import sqlalchemy as sa

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None

_PIPELINE_KEYS = ("transcription", "metadata", "upload", "trimming")
_ACCOUNT_KEYS = ("retention", "download", "platforms")


def _upload_to_output(upload: dict) -> dict:
    result: dict = {"preset_ids": [], "auto_upload": False, "upload_captions": True}
    if not upload:
        return result
    for key in ("auto_upload", "upload_captions", "default_platforms"):
        if key in upload:
            result[key] = copy.deepcopy(upload[key])
    preset_ids = upload.get("default_preset_ids")
    if isinstance(preset_ids, dict) and preset_ids:
        result["preset_ids"] = list(preset_ids.values())
    return result


def _processing_from_user(config: dict) -> dict:
    processing: dict = {}
    transcription = config.get("transcription")
    if isinstance(transcription, dict):
        processing["transcription"] = copy.deepcopy(transcription)
    trimming = config.get("trimming")
    if isinstance(trimming, dict):
        processing["trimming"] = copy.deepcopy(trimming)
    return processing


def upgrade() -> None:
    conn = op.get_bind()

    users = conn.execute(sa.text("SELECT id FROM users")).fetchall()
    for (user_id,) in users:
        existing = conn.execute(
            sa.text("SELECT id FROM recording_templates WHERE user_id = :uid AND is_default = true LIMIT 1"),
            {"uid": user_id},
        ).first()
        if existing:
            continue

        row = conn.execute(
            sa.text("SELECT config_data FROM user_configs WHERE user_id = :uid LIMIT 1"),
            {"uid": user_id},
        ).first()

        config_data: dict = {}
        if row and row[0]:
            raw = row[0]
            config_data = raw if isinstance(raw, dict) else json.loads(raw)

        processing_config = _processing_from_user(config_data)
        metadata_config = copy.deepcopy(config_data.get("metadata") or {})
        output_config = _upload_to_output(config_data.get("upload") or {})

        conn.execute(
            sa.text(
                """
                INSERT INTO recording_templates (
                    user_id, name, description, is_draft, is_active, is_default,
                    matching_rules, processing_config, metadata_config, output_config,
                    used_count, created_at, updated_at
                ) VALUES (
                    :user_id, 'Default', 'Base video processing defaults', false, true, true,
                    NULL, CAST(:processing AS jsonb), CAST(:metadata AS jsonb),
                    CAST(:output AS jsonb), 0, NOW(), NOW()
                )
                """
            ),
            {
                "user_id": user_id,
                "processing": json.dumps(processing_config),
                "metadata": json.dumps(metadata_config),
                "output": json.dumps(output_config),
            },
        )

        if row:
            stripped = {k: copy.deepcopy(config_data[k]) for k in _ACCOUNT_KEYS if k in config_data}
            conn.execute(
                sa.text("UPDATE user_configs SET config_data = CAST(:data AS jsonb) WHERE user_id = :uid"),
                {"uid": user_id, "data": json.dumps(stripped)},
            )


def downgrade() -> None:
    """No-op: cannot restore stripped user_configs pipeline keys reliably."""
