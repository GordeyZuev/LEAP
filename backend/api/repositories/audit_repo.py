"""Admin audit trail repository"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.audit_models import AdminAuditLogModel
from logger import get_logger

logger = get_logger()


class AdminAuditLogRepository:
    """Reads and writes the administrative audit trail."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        actor_id: str | None,
        actor_email: str,
        action: str,
        target_user_id: str | None = None,
        target_label: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Append an entry.

        Auditing must never be the reason an administrative action fails, so a
        write problem here is logged and swallowed rather than raised.
        """
        try:
            self.session.add(
                AdminAuditLogModel(
                    actor_user_id=actor_id,
                    actor_email=actor_email,
                    action=action,
                    target_user_id=target_user_id,
                    target_label=target_label,
                    details=details,
                    ip_address=ip_address,
                )
            )
            await self.session.flush()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Failed to write audit entry '{action}': {exc}")

    async def list_recent(self, limit: int = 500) -> list[AdminAuditLogModel]:
        """Newest entries first, capped so the admin screen stays responsive."""
        stmt = select(AdminAuditLogModel).order_by(AdminAuditLogModel.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


def diff_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """`{field: {"from": old, "to": new}}` for values that actually changed."""
    return {
        field: {"from": before.get(field), "to": value} for field, value in after.items() if before.get(field) != value
    }
