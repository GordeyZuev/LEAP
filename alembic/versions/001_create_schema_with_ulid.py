"""Create complete schema with ULID user IDs

Revision ID: 001
Revises:
Create Date: 2026-01-22 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_slug sequence
    op.execute("CREATE SEQUENCE user_slug_seq START 1")

    # Create users table with ULID primary key
    op.create_table(
        "users",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_slug", sa.Integer, server_default=sa.text("nextval('user_slug_seq')"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("is_verified", sa.Boolean, default=False, nullable=False),
        sa.Column("is_superuser", sa.Boolean, default=False, nullable=False),
        sa.Column("role", sa.String(50), default="user", nullable=False),
        sa.Column("can_transcribe", sa.Boolean, default=True, nullable=False),
        sa.Column("can_process_video", sa.Boolean, default=True, nullable=False),
        sa.Column("can_upload", sa.Boolean, default=True, nullable=False),
        sa.Column("can_create_templates", sa.Boolean, default=True, nullable=False),
        sa.Column("can_delete_recordings", sa.Boolean, default=True, nullable=False),
        sa.Column("can_update_uploaded_videos", sa.Boolean, default=True, nullable=False),
        sa.Column("can_manage_credentials", sa.Boolean, default=True, nullable=False),
        sa.Column("can_export_data", sa.Boolean, default=True, nullable=False),
        sa.Column("timezone", sa.String(50), default="UTC", nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_user_slug", "users", ["user_slug"], unique=True)

    # Create user_credentials table
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("encrypted_data", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_user_credentials_id", "user_credentials", ["id"])
    op.create_index("ix_user_credentials_user_id", "user_credentials", ["user_id"])

    # Create subscription_plans table
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("included_recordings_per_month", sa.Integer, nullable=True),
        sa.Column("included_storage_gb", sa.Integer, nullable=True),
        sa.Column("max_concurrent_tasks", sa.Integer, nullable=True),
        sa.Column("max_automation_jobs", sa.Integer, nullable=True),
        sa.Column("min_automation_interval_hours", sa.Integer, nullable=True),
        sa.Column("price_monthly", sa.Numeric(10, 2), default=0, nullable=False),
        sa.Column("price_yearly", sa.Numeric(10, 2), default=0, nullable=False),
        sa.Column("overage_price_per_unit", sa.Numeric(10, 4), nullable=True),
        sa.Column("overage_unit_type", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("sort_order", sa.Integer, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subscription_plans_id", "subscription_plans", ["id"])
    op.create_index("ix_subscription_plans_name", "subscription_plans", ["name"])
    op.create_index("ix_subscription_plans_is_active", "subscription_plans", ["is_active"])

    # Create user_subscriptions table
    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("custom_max_recordings_per_month", sa.Integer, nullable=True),
        sa.Column("custom_max_storage_gb", sa.Integer, nullable=True),
        sa.Column("custom_max_concurrent_tasks", sa.Integer, nullable=True),
        sa.Column("custom_max_automation_jobs", sa.Integer, nullable=True),
        sa.Column("custom_min_automation_interval_hours", sa.Integer, nullable=True),
        sa.Column("pay_as_you_go_enabled", sa.Boolean, default=False, nullable=False),
        sa.Column("pay_as_you_go_monthly_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("starts_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("modified_by", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_subscriptions_id", "user_subscriptions", ["id"])
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
    op.create_index("ix_user_subscriptions_plan_id", "user_subscriptions", ["plan_id"])

    # Create quota_usage table
    op.create_table(
        "quota_usage",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Integer, nullable=False),
        sa.Column("recordings_count", sa.Integer, default=0, nullable=False),
        sa.Column("storage_bytes", sa.BigInteger, default=0, nullable=False),
        sa.Column("concurrent_tasks_count", sa.Integer, default=0, nullable=False),
        sa.Column("overage_recordings_count", sa.Integer, default=0, nullable=False),
        sa.Column("overage_cost", sa.Numeric(10, 2), default=0, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quota_usage_id", "quota_usage", ["id"])
    op.create_index("ix_quota_usage_user_id", "quota_usage", ["user_id"])
    op.create_index("ix_quota_usage_period", "quota_usage", ["period"])

    # Create quota_change_history table
    op.create_table(
        "quota_change_history",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("changed_by", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("old_plan_id", sa.Integer, sa.ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("new_plan_id", sa.Integer, sa.ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changes", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quota_change_history_id", "quota_change_history", ["id"])
    op.create_index("ix_quota_change_history_user_id", "quota_change_history", ["user_id"])
    op.create_index("ix_quota_change_history_change_type", "quota_change_history", ["change_type"])
    op.create_index("ix_quota_change_history_created_at", "quota_change_history", ["created_at"])

    # Create refresh_tokens table
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(500), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("is_revoked", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token", "refresh_tokens", ["token"])

    # Create input_sources table
    op.create_table(
        "input_sources",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("credential_id", sa.Integer, sa.ForeignKey("user_credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("last_sync_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "name", "source_type", "credential_id", name="uq_input_sources_user_name_type_credential"),
    )
    op.create_index("ix_input_sources_id", "input_sources", ["id"])
    op.create_index("ix_input_sources_user_id", "input_sources", ["user_id"])

    # Create output_presets table
    op.create_table(
        "output_presets",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("credential_id", sa.Integer, sa.ForeignKey("user_credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("preset_metadata", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_output_presets_id", "output_presets", ["id"])
    op.create_index("ix_output_presets_user_id", "output_presets", ["user_id"])

    # Create recording_templates table
    op.create_table(
        "recording_templates",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("matching_rules", postgresql.JSONB, nullable=True),
        sa.Column("processing_config", postgresql.JSONB, nullable=True),
        sa.Column("metadata_config", postgresql.JSONB, nullable=True),
        sa.Column("output_config", postgresql.JSONB, nullable=True),
        sa.Column("is_draft", sa.Boolean, default=False, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("used_count", sa.Integer, default=0, nullable=False),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recording_templates_id", "recording_templates", ["id"])
    op.create_index("ix_recording_templates_user_id", "recording_templates", ["user_id"])

    # Create base_configs table
    op.create_table(
        "base_configs",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("config_type", sa.String(50), nullable=True),
        sa.Column("config_data", postgresql.JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_base_configs_id", "base_configs", ["id"])
    op.create_index("ix_base_configs_user_id", "base_configs", ["user_id"])
    op.create_index("ix_base_configs_config_type", "base_configs", ["config_type"])

    # Create user_configs table
    op.create_table(
        "user_configs",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("config_data", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_configs_id", "user_configs", ["id"])
    op.create_index("ix_user_configs_user_id", "user_configs", ["user_id"])

    # Create automation_jobs table
    op.create_table(
        "automation_jobs",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("input_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_ids", postgresql.ARRAY(sa.Integer), nullable=False, server_default="{}"),
        sa.Column("schedule", postgresql.JSONB, nullable=False),
        sa.Column("sync_config", postgresql.JSONB, nullable=False, server_default='{"sync_days": 2, "allow_skipped": false}'),
        sa.Column("processing_config", postgresql.JSONB, nullable=False, server_default='{"auto_process": true, "auto_upload": true, "max_parallel": 3}'),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_count", sa.Integer, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_automation_jobs_id", "automation_jobs", ["id"])
    op.create_index("ix_automation_jobs_user_id", "automation_jobs", ["user_id"])
    op.create_index("ix_automation_jobs_source_id", "automation_jobs", ["source_id"])

    # Create recordings table
    op.create_table(
        "recordings",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("input_source_id", sa.Integer, sa.ForeignKey("input_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("recording_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("display_name", sa.String(500), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration", sa.Integer, nullable=False),
        sa.Column("status", sa.Enum("INITIALIZED", "SKIPPED", "DOWNLOADED", "PROCESSED", "TRANSCRIBED", "UPLOADED", "FAILED", "EXPIRED", name="processingstatus"), nullable=True),
        sa.Column("is_mapped", sa.Boolean, default=False),
        sa.Column("blank_record", sa.Boolean, default=False, server_default="false"),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted", sa.Boolean, default=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_state", sa.String(20), default="active", server_default="active"),
        sa.Column("deletion_reason", sa.String(20), nullable=True),
        sa.Column("soft_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hard_delete_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_video_path", sa.String(1000), nullable=True),
        sa.Column("processed_video_path", sa.String(1000), nullable=True),
        sa.Column("processed_audio_path", sa.String(1000), nullable=True),
        sa.Column("transcription_dir", sa.String(1000), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("video_file_size", sa.Integer, nullable=True),
        sa.Column("transcription_info", postgresql.JSONB, nullable=True),
        sa.Column("topic_timestamps", postgresql.JSONB, nullable=True),
        sa.Column("main_topics", postgresql.JSONB, nullable=True),
        sa.Column("processing_preferences", postgresql.JSONB, nullable=True),
        sa.Column("failed", sa.Boolean, default=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.String(1000), nullable=True),
        sa.Column("failed_at_stage", sa.String(50), nullable=True),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recordings_user_id", "recordings", ["user_id"])
    op.create_index("ix_recordings_input_source_id", "recordings", ["input_source_id"])
    op.create_index("ix_recordings_template_id", "recordings", ["template_id"])
    op.create_index("ix_recordings_deleted", "recordings", ["deleted"])
    op.create_index("ix_recordings_delete_state", "recordings", ["delete_state"])

    # Create source_metadata table
    op.create_table(
        "source_metadata",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("recording_id", sa.Integer, sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("input_source_id", sa.Integer, sa.ForeignKey("input_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_type", sa.Enum("ZOOM", "GOOGLE_DRIVE", "YANDEX_DISK", "LOCAL", "MANUAL", name="sourcetype"), nullable=False),
        sa.Column("source_key", sa.String(1000), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.UniqueConstraint("source_type", "source_key", "recording_id", name="unique_source_per_recording"),
    )
    op.create_index("ix_source_metadata_user_id", "source_metadata", ["user_id"])
    op.create_index("ix_source_metadata_input_source_id", "source_metadata", ["input_source_id"])

    # Create output_targets table
    op.create_table(
        "output_targets",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("recording_id", sa.Integer, sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("preset_id", sa.Integer, sa.ForeignKey("output_presets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_type", sa.Enum("YOUTUBE", "VK", "LOCAL", name="targettype"), nullable=False),
        sa.Column("status", sa.Enum("NOT_UPLOADED", "UPLOADING", "UPLOADED", "FAILED", name="targetstatus"), default="NOT_UPLOADED"),
        sa.Column("target_meta", postgresql.JSONB, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed", sa.Boolean, default=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.String(1000), nullable=True),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("recording_id", "target_type", name="unique_target_per_recording"),
    )
    op.create_index("ix_output_targets_user_id", "output_targets", ["user_id"])
    op.create_index("ix_output_targets_preset_id", "output_targets", ["preset_id"])

    # Create processing_stages table
    op.create_table(
        "processing_stages",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("recording_id", sa.Integer, sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("stage_type", sa.Enum("DOWNLOAD", "VIDEO_PROCESSING", "TRANSCRIPTION", "TOPIC_EXTRACTION", "UPLOAD", name="processingstagetype"), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "SKIPPED", name="processingstagestatus"), default="PENDING"),
        sa.Column("failed", sa.Boolean, default=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.String(1000), nullable=True),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("stage_meta", postgresql.JSONB, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("recording_id", "stage_type", name="unique_stage_per_recording"),
    )
    op.create_index("ix_processing_stages_user_id", "processing_stages", ["user_id"])

    # Note: Celery Beat tables are created in migration 008


def downgrade() -> None:
    op.drop_table("processing_stages")
    op.drop_table("output_targets")
    op.drop_table("source_metadata")
    op.drop_table("recordings")
    op.drop_table("automation_jobs")
    op.drop_table("user_configs")
    op.drop_table("base_configs")
    op.drop_table("recording_templates")
    op.drop_table("output_presets")
    op.drop_table("input_sources")
    op.drop_table("refresh_tokens")
    op.drop_table("quota_change_history")
    op.drop_table("quota_usage")
    op.drop_table("user_subscriptions")
    op.drop_table("subscription_plans")
    op.drop_table("user_credentials")
    op.drop_table("users")
    op.execute("DROP SEQUENCE IF EXISTS user_slug_seq")
