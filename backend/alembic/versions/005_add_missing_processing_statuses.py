"""Add missing processing statuses

Revision ID: 005
Revises: 004
Create Date: 2026-01-23 14:15:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL refuses to USE a newly-added enum value in the same
    # transaction that ADDed it. Alembic runs the whole upgrade chain in one
    # transaction by default, so a later migration (007) that references
    # 'TRANSCRIBING' would fail with UnsafeNewEnumValueUsageError unless each
    # ADD VALUE is committed via autocommit_block.
    ctx = op.get_context()
    new_values = [
        ("PENDING_SOURCE", "BEFORE 'INITIALIZED'"),
        ("DOWNLOADING", "AFTER 'INITIALIZED'"),
        ("PROCESSING", "AFTER 'PROCESSED'"),
        ("PREPARING", "AFTER 'PROCESSING'"),
        ("TRANSCRIBING", "AFTER 'PREPARING'"),
        ("UPLOADING", "AFTER 'TRANSCRIBED'"),
        ("READY", "AFTER 'UPLOADED'"),
    ]
    for value, position in new_values:
        with ctx.autocommit_block():
            op.execute(f"ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS '{value}' {position}")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly
    # We would need to recreate the enum type, which is complex
    # For simplicity, we'll leave the values in place
    # If you need to remove them, you'll need to:
    # 1. Create new enum without these values
    # 2. Alter column to use new enum
    # 3. Drop old enum
    # 4. Rename new enum
    pass
