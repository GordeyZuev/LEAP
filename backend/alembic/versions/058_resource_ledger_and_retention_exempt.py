"""Resource ledger and recording retention exemption.

Revision ID: 058
Revises: 057
Create Date: 2026-10-04

Backfills AssemblyAI minutes from usage_events, then one estimate per recording
from final_duration where no transcription_completed event has a duration. DeepSeek
token files are walked after deploy by maintenance.reconcile_transcription_ledger:
this upgrade runs inside the migration transaction, which cannot open object
storage on another connection before the new table is committed.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("retention_exempt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "resource_ledger",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("recording_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("provider_job_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("audio_seconds", sa.Float(), nullable=True),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_miss_tokens", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("idempotency_key", name="uq_resource_ledger_idempotency"),
        sa.UniqueConstraint("provider_job_id", name="uq_resource_ledger_provider_job"),
    )
    op.create_index("ix_resource_ledger_user_occurred", "resource_ledger", ["user_id", "occurred_at"])
    op.create_index("ix_resource_ledger_occurred", "resource_ledger", ["occurred_at"])
    op.create_index("ix_resource_ledger_recording", "resource_ledger", ["recording_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO resource_ledger (
                id, user_id, recording_id, provider, operation, status,
                audio_seconds, occurred_at, idempotency_key, metadata, created_at
            )
            SELECT
                e.id,
                e.user_id,
                e.recording_id,
                'assemblyai',
                'transcribe',
                'completed',
                e.duration_seconds,
                e.created_at,
                'backfill:event:' || e.id,
                jsonb_build_object('basis', 'segment_end'),
                e.created_at
            FROM usage_events e
            WHERE e.event_type = 'transcription_completed'
              AND e.duration_seconds IS NOT NULL
              AND e.duration_seconds > 0
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO resource_ledger (
                id, user_id, recording_id, provider, operation, status,
                audio_seconds, occurred_at, idempotency_key, metadata, created_at
            )
            SELECT
                substr(md5('timing:' || r.id::text), 1, 26),
                r.user_id,
                r.id,
                'assemblyai',
                'transcribe',
                'completed',
                r.final_duration,
                latest.completed_at,
                'backfill:timing:' || r.id::text,
                jsonb_build_object('basis', 'segment_end'),
                latest.completed_at
            FROM recordings r
            JOIN (
                SELECT DISTINCT ON (st.recording_id)
                    st.recording_id,
                    st.completed_at
                FROM stage_timings st
                WHERE st.stage_type = 'TRANSCRIBE'
                  AND st.status = 'COMPLETED'
                  AND st.substep IS NULL
                  AND st.completed_at IS NOT NULL
                ORDER BY st.recording_id, st.completed_at DESC
            ) latest ON latest.recording_id = r.id
            WHERE r.final_duration IS NOT NULL
              AND r.final_duration > 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM usage_events e
                  WHERE e.recording_id = r.id
                    AND e.event_type = 'transcription_completed'
                    AND e.duration_seconds IS NOT NULL
              )
            """
        )
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                GRANT SELECT ON resource_ledger TO grafana_ro;
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_resource_ledger_recording", table_name="resource_ledger")
    op.drop_index("ix_resource_ledger_occurred", table_name="resource_ledger")
    op.drop_index("ix_resource_ledger_user_occurred", table_name="resource_ledger")
    op.drop_table("resource_ledger")
    op.drop_column("recordings", "retention_exempt")
