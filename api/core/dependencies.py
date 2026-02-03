"""ServiceContext dependencies"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_active_user
from api.core.context import ServiceContext
from api.dependencies import get_db_session
from database.auth_models import UserModel


def get_service_context(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_active_user),
) -> ServiceContext:
    """
    Get ServiceContext for the current user.

    Centralizes access to session, user_id and config_helper.
    """
    return ServiceContext.create(session=session, user_id=current_user.id)
