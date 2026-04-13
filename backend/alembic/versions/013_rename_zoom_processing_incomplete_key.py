"""Rename zoom_processing_incomplete to source_processing_incomplete in metadata

Revision ID: 013
Revises: 012
Create Date: 2026-02-12

Renames the JSONB key 'zoom_processing_incomplete' to 'source_processing_incomplete'
in source_metadata.metadata for consistency with the source-agnostic architecture.
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE source_metadata
        SET metadata = (metadata - 'zoom_processing_incomplete')
                       || jsonb_build_object('source_processing_incomplete',
                                             metadata->'zoom_processing_incomplete')
        WHERE metadata ? 'zoom_processing_incomplete'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE source_metadata
        SET metadata = (metadata - 'source_processing_incomplete')
                       || jsonb_build_object('zoom_processing_incomplete',
                                             metadata->'source_processing_incomplete')
        WHERE metadata ? 'source_processing_incomplete'
    """)
