"""Database models for the admin audit trail"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from database.models import Base


class AdminAuditLogModel(Base):
    """One administrative action taken against an account.

    Actor and target identities are denormalised alongside the foreign keys:
    the point of an audit trail is to survive the deletion of the very rows it
    describes, so the entry must stay readable after a user is removed.
    """

    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    actor_user_id = Column(String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_email = Column(String(255), nullable=False)

    # Dotted verb, e.g. "user.role_changed", "subscription.assigned".
    action = Column(String(64), nullable=False, index=True)

    target_user_id = Column(String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_label = Column(String(255), nullable=True)

    # What actually changed: {"field": {"from": ..., "to": ...}}.
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)

    def __repr__(self):
        return f"<AdminAuditLog(id={self.id}, action='{self.action}', target='{self.target_label}')>"


class AuditAction:
    """Action names written to the trail. Keep in sync with the UI labels."""

    USER_UPDATED = "user.updated"
    SUBSCRIPTION_ASSIGNED = "subscription.assigned"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_REMOVED = "subscription.removed"
    PLAN_CREATED = "plan.created"
    PLAN_UPDATED = "plan.updated"
    PLAN_DELETED = "plan.deleted"
