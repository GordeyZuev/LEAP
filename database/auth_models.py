"""Database models for authentication and multi-tenancy"""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from ulid import ULID

from database.models import Base


class UserModel(Base):
    """User model for multi-tenancy"""

    __tablename__ = "users"

    # --- PK & identity ---
    id = Column(String(26), primary_key=True, default=lambda: str(ULID()))
    user_slug = Column(Integer, Sequence("user_slug_seq"), unique=True, nullable=False, index=True)

    # --- Core info ---
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    role = Column(String(50), default="user", nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)

    # --- Permissions ---
    can_transcribe = Column(Boolean, default=True, nullable=False)
    can_process_video = Column(Boolean, default=True, nullable=False)
    can_upload = Column(Boolean, default=True, nullable=False)
    can_create_templates = Column(Boolean, default=True, nullable=False)
    can_delete_recordings = Column(Boolean, default=True, nullable=False)
    can_update_uploaded_videos = Column(Boolean, default=True, nullable=False)
    can_manage_credentials = Column(Boolean, default=True, nullable=False)
    can_export_data = Column(Boolean, default=True, nullable=False)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    credentials = relationship("UserCredentialModel", back_populates="user", cascade="all, delete-orphan")
    recordings = relationship("RecordingModel", back_populates="owner", cascade="all, delete-orphan")
    subscription = relationship(
        "UserSubscriptionModel",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[UserSubscriptionModel.user_id]",
    )
    quota_usage = relationship("QuotaUsageModel", back_populates="user", cascade="all, delete-orphan")
    config = relationship("UserConfigModel", back_populates="user", uselist=False, cascade="all, delete-orphan")
    automation_jobs = relationship("AutomationJobModel", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role={self.role}, active={self.is_active})>"


class UserCredentialModel(Base):
    """User credentials for external services."""

    __tablename__ = "user_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "account_name", name="uq_credentials_user_platform_account"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    account_name = Column(String(255), nullable=True)
    encrypted_data = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    user = relationship("UserModel", back_populates="credentials")

    def __repr__(self):
        account_str = f", account='{self.account_name}'" if self.account_name else ""
        return f"<UserCredential(id={self.id}, user_id={self.user_id}, platform='{self.platform}'{account_str})>"


class SubscriptionPlanModel(Base):
    """Subscription plan with quotas and pricing."""

    __tablename__ = "subscription_plans"

    # --- PK & core info ---
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    sort_order = Column(Integer, default=0, nullable=False)

    # --- Quotas & limits ---
    included_recordings_per_month = Column(Integer, nullable=True)
    included_storage_gb = Column(Integer, nullable=True)
    max_concurrent_tasks = Column(Integer, nullable=True)
    max_automation_jobs = Column(Integer, nullable=True)
    min_automation_interval_hours = Column(Integer, nullable=True)

    # --- Pricing ---
    price_monthly = Column(Numeric(10, 2), default=0, nullable=False)
    price_yearly = Column(Numeric(10, 2), default=0, nullable=False)
    overage_price_per_unit = Column(Numeric(10, 4), nullable=True)
    overage_unit_type = Column(String(50), nullable=True)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    subscriptions = relationship("UserSubscriptionModel", back_populates="plan")

    def __repr__(self):
        return f"<SubscriptionPlan(id={self.id}, name='{self.name}', display_name='{self.display_name}')>"


class UserSubscriptionModel(Base):
    """User subscription with custom quotas."""

    __tablename__ = "user_subscriptions"

    # --- PK & FK ---
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False, index=True)

    # --- Custom quota overrides ---
    custom_max_recordings_per_month = Column(Integer, nullable=True)
    custom_max_storage_gb = Column(Integer, nullable=True)
    custom_max_concurrent_tasks = Column(Integer, nullable=True)
    custom_max_automation_jobs = Column(Integer, nullable=True)
    custom_min_automation_interval_hours = Column(Integer, nullable=True)

    # --- Pay-as-you-go ---
    pay_as_you_go_enabled = Column(Boolean, default=False, nullable=False)
    pay_as_you_go_monthly_limit = Column(Numeric(10, 2), nullable=True)

    # --- Lifecycle ---
    starts_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # --- Audit ---
    created_by = Column(String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    modified_by = Column(String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    user = relationship("UserModel", back_populates="subscription", foreign_keys=[user_id])
    plan = relationship("SubscriptionPlanModel", back_populates="subscriptions")

    def __repr__(self):
        return f"<UserSubscription(id={self.id}, user_id={self.user_id}, plan_id={self.plan_id})>"


class QuotaUsageModel(Base):
    """Quota usage tracking per user per period."""

    __tablename__ = "quota_usage"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period = Column(Integer, nullable=False, index=True)
    recordings_count = Column(Integer, default=0, nullable=False)
    storage_bytes = Column(BigInteger, default=0, nullable=False)
    concurrent_tasks_count = Column(Integer, default=0, nullable=False)
    overage_recordings_count = Column(Integer, default=0, nullable=False)
    overage_cost = Column(Numeric(10, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    user = relationship("UserModel", back_populates="quota_usage")

    def __repr__(self):
        return (
            f"<QuotaUsage(id={self.id}, user_id={self.user_id}, period={self.period}, "
            f"recordings={self.recordings_count})>"
        )


class RefreshTokenModel(Base):
    """Refresh token storage for JWT authentication."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(500), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.is_revoked})>"
