"""Add external source and target enum values

Revision ID: 012
Revises: 011
Create Date: 2026-02-12

Add new SourceType values (EXTERNAL_URL, YOUTUBE, OTHER, LOCAL_FILE)
and TargetType values (YANDEX_DISK, GOOGLE_DRIVE, RUTUBE, LOCAL_STORAGE, OTHER)
for external video source ingestion and Yandex Disk upload target.
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new SourceType values
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'EXTERNAL_URL'")
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'YOUTUBE'")
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'OTHER'")
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'LOCAL_FILE'")

    # Add new TargetType values
    op.execute("ALTER TYPE targettype ADD VALUE IF NOT EXISTS 'YANDEX_DISK'")
    op.execute("ALTER TYPE targettype ADD VALUE IF NOT EXISTS 'GOOGLE_DRIVE'")
    op.execute("ALTER TYPE targettype ADD VALUE IF NOT EXISTS 'RUTUBE'")
    op.execute("ALTER TYPE targettype ADD VALUE IF NOT EXISTS 'LOCAL_STORAGE'")
    op.execute("ALTER TYPE targettype ADD VALUE IF NOT EXISTS 'OTHER'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly.
    # Values are left in place; to remove them, recreate the enum type.
    pass
