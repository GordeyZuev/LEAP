"""convert_datetime_columns_to_timezone_aware

Revision ID: 010
Revises: 009
Create Date: 2026-02-03

Converts all TIMESTAMP WITHOUT TIME ZONE columns to TIMESTAMP WITH TIME ZONE
to ensure consistent timezone-aware datetime handling across the application.
"""

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.alter_column("users", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("users", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("users", "last_login_at", type_=sa.DateTime(timezone=True), existing_nullable=True)

    # User credentials table
    op.alter_column("user_credentials", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("user_credentials", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("user_credentials", "last_used_at", type_=sa.DateTime(timezone=True), existing_nullable=True)

    # Subscription plans table
    op.alter_column("subscription_plans", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("subscription_plans", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # User subscriptions table
    op.alter_column("user_subscriptions", "starts_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("user_subscriptions", "expires_at", type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("user_subscriptions", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("user_subscriptions", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Quota usage table
    op.alter_column("quota_usage", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("quota_usage", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Quota change history table
    op.alter_column("quota_change_history", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Refresh tokens table
    op.alter_column("refresh_tokens", "expires_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("refresh_tokens", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Base configs table
    op.alter_column("base_configs", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("base_configs", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Input sources table
    op.alter_column("input_sources", "last_sync_at", type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("input_sources", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("input_sources", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Output presets table
    op.alter_column("output_presets", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("output_presets", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Recording templates table
    op.alter_column("recording_templates", "last_used_at", type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("recording_templates", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("recording_templates", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # Automation jobs table
    op.alter_column("automation_jobs", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("automation_jobs", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)

    # User configs table
    op.alter_column("user_configs", "created_at", type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("user_configs", "updated_at", type_=sa.DateTime(timezone=True), existing_nullable=False)


def downgrade() -> None:
    # Users table
    op.alter_column("users", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("users", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("users", "last_login_at", type_=sa.DateTime(timezone=False), existing_nullable=True)

    # User credentials table
    op.alter_column("user_credentials", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("user_credentials", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("user_credentials", "last_used_at", type_=sa.DateTime(timezone=False), existing_nullable=True)

    # Subscription plans table
    op.alter_column("subscription_plans", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("subscription_plans", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # User subscriptions table
    op.alter_column("user_subscriptions", "starts_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("user_subscriptions", "expires_at", type_=sa.DateTime(timezone=False), existing_nullable=True)
    op.alter_column("user_subscriptions", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("user_subscriptions", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Quota usage table
    op.alter_column("quota_usage", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("quota_usage", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Quota change history table
    op.alter_column("quota_change_history", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Refresh tokens table
    op.alter_column("refresh_tokens", "expires_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("refresh_tokens", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Base configs table
    op.alter_column("base_configs", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("base_configs", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Input sources table
    op.alter_column("input_sources", "last_sync_at", type_=sa.DateTime(timezone=False), existing_nullable=True)
    op.alter_column("input_sources", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("input_sources", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Output presets table
    op.alter_column("output_presets", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("output_presets", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Recording templates table
    op.alter_column("recording_templates", "last_used_at", type_=sa.DateTime(timezone=False), existing_nullable=True)
    op.alter_column("recording_templates", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("recording_templates", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # Automation jobs table
    op.alter_column("automation_jobs", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("automation_jobs", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)

    # User configs table
    op.alter_column("user_configs", "created_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
    op.alter_column("user_configs", "updated_at", type_=sa.DateTime(timezone=False), existing_nullable=False)
