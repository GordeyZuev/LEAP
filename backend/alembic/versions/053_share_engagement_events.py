"""Append-only public watch engagement events.

Revision ID: 053
Revises: 052
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "share_engagement_events",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("owner_user_id", sa.String(length=26), nullable=False),
        sa.Column("recording_id", sa.Integer(), nullable=True),
        sa.Column("playlist_id", sa.Integer(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("event_name", sa.String(length=32), nullable=False),
        sa.Column("visitor_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("session_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_share_engagement_recording_created",
        "share_engagement_events",
        ["recording_id", "created_at"],
    )
    op.create_index(
        "ix_share_engagement_playlist_created",
        "share_engagement_events",
        ["playlist_id", "created_at"],
    )
    op.create_index(
        "ix_share_engagement_owner_created",
        "share_engagement_events",
        ["owner_user_id", "created_at"],
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                GRANT SELECT ON share_engagement_events TO grafana_ro;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                REVOKE SELECT ON share_engagement_events FROM grafana_ro;
            END IF;
        END
        $$;
        """
    )
    op.drop_index("ix_share_engagement_owner_created", table_name="share_engagement_events")
    op.drop_index("ix_share_engagement_playlist_created", table_name="share_engagement_events")
    op.drop_index("ix_share_engagement_recording_created", table_name="share_engagement_events")
    op.drop_table("share_engagement_events")
