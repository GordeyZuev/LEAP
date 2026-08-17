"""Normalize recordings.failed_at_stage to lowercase stage keys

Four code paths wrote this column in three different casings, plus one present
participle ("downloading"). The value is not merely displayed: retry logic
compares it as a plain string, so the spellings had to converge. Lowercase is
canonical because that is what production already holds.

Revision ID: 036
Revises: 035
Create Date: 2026-08-17
"""

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None

# Legacy spelling -> canonical lowercase stage key. Applied after lower(), so
# only the non-casing variants need listing.
_ALIASES = {
    "downloading": "download",
    "uploading": "upload",
    "transcription": "transcribe",
    "topics": "extract_topics",
    "subtitles": "generate_subtitles",
}


def upgrade() -> None:
    op.execute(
        "UPDATE recordings SET failed_at_stage = lower(failed_at_stage) "
        "WHERE failed_at_stage IS NOT NULL AND failed_at_stage <> lower(failed_at_stage)"
    )
    for legacy, canonical in _ALIASES.items():
        op.execute(f"UPDATE recordings SET failed_at_stage = '{canonical}' WHERE failed_at_stage = '{legacy}'")


def downgrade() -> None:
    """No-op.

    This is a data normalization: the previous state was an inconsistent mix of
    casings across rows, with no record of which row used which. There is
    nothing to restore, and restoring it would reintroduce the defect.
    """
