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
    # PostgreSQL requires ALTER TYPE ... ADD VALUE for enums
    # Add missing values one by one

    # Add PENDING_SOURCE (new status for recordings still processing on Zoom)
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'PENDING_SOURCE' BEFORE 'INITIALIZED'")

    # Add runtime statuses (in logical order)
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'DOWNLOADING' AFTER 'INITIALIZED'")
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'PROCESSING' AFTER 'PROCESSED'")
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'PREPARING' AFTER 'PROCESSING'")
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'TRANSCRIBING' AFTER 'PREPARING'")
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'UPLOADING' AFTER 'TRANSCRIBED'")
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'READY' AFTER 'UPLOADED'")


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
