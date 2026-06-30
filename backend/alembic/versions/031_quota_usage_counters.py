"""Add transcriptions_count, processing_count, uploads_count to quota_usage;
add max_transcriptions_per_month, max_processing_per_month to subscription_plans

Revision ID: 031
Revises: 030
Create Date: 2026-06-30
"""

import sqlalchemy as sa

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quota_usage", sa.Column("transcriptions_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("quota_usage", sa.Column("processing_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("quota_usage", sa.Column("uploads_count", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("subscription_plans", sa.Column("max_transcriptions_per_month", sa.Integer(), nullable=True))
    op.add_column("subscription_plans", sa.Column("max_processing_per_month", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscription_plans", "max_processing_per_month")
    op.drop_column("subscription_plans", "max_transcriptions_per_month")
    op.drop_column("quota_usage", "uploads_count")
    op.drop_column("quota_usage", "processing_count")
    op.drop_column("quota_usage", "transcriptions_count")
