"""Product news, newsletter subscriptions, delivery records, and feedback."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ulid import ULID

from database.models import Base


def _new_id() -> str:
    return str(ULID())


class ProductUpdateModel(Base):
    """One public product update; the same content backs the archive and emails."""

    __tablename__ = "product_updates"
    __table_args__ = (
        Index("ix_product_updates_published", "published_at"),
        UniqueConstraint("version", name="uq_product_updates_version"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_new_id)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    audience_bullets: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    creator_bullets: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # Stable interest codes: viewers, course_publishing, video_processing.
    audiences: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    is_published: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    newsletter_enabled: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    release_date: Mapped[date | None] = mapped_column(nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NewsletterSubscriptionModel(Base):
    """Explicitly confirmed opt-in to product news by email."""

    __tablename__ = "product_news_subscriptions"
    __table_args__ = (
        Index("ix_product_news_subscriptions_status", "status"),
        UniqueConstraint("email", name="uq_product_news_subscriptions_email"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'unsubscribed')", name="ck_product_news_subscription_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    interests: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )


class ProductUpdateDeliveryModel(Base):
    """Per-recipient idempotency and outcome for one update email."""

    __tablename__ = "product_update_deliveries"
    __table_args__ = (
        UniqueConstraint("update_id", "subscription_id", name="uq_product_update_delivery_recipient"),
        Index("ix_product_update_deliveries_status", "status"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'skipped')", name="ck_product_update_delivery_status"
        ),
        CheckConstraint("attempts >= 0", name="ck_product_update_delivery_attempts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    update_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("product_updates.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("product_news_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProductFeedbackModel(Base):
    """Feedback submitted independently from newsletter subscription."""

    __tablename__ = "product_feedback"
    __table_args__ = (
        Index("ix_product_feedback_created", "created_at"),
        CheckConstraint("kind IN ('idea', 'problem', 'question', 'other')", name="ck_product_feedback_kind"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_new_id)
    interests: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reply_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
