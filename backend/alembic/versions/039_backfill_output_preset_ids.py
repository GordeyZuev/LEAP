"""Backfill missing preset_ids in template output_config JSONB

Revision ID: 039
Revises: 038
Create Date: 2026-08-22
"""

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE recording_templates
        SET output_config = output_config || '{"preset_ids": []}'::jsonb
        WHERE output_config IS NOT NULL
          AND NOT (output_config ? 'preset_ids')
        """
    )


def downgrade() -> None:
    pass
