from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_active_user
from api.dependencies import get_db_session
from api.repositories.config_repos import UserConfigRepository, deep_merge
from api.schemas.config.user_config import UserConfigResponse, UserConfigUpdate
from config.settings import DEFAULT_USER_CONFIG
from database.auth_models import UserModel
from logger import get_logger

router = APIRouter(prefix="/api/v1/users/me/config", tags=["User Config"])
logger = get_logger()


@router.get("", response_model=UserConfigResponse)
async def get_user_config(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Get user config with automatic merge of new default fields.

    Uses UserConfigRepository.get_effective_config() to ensure backward compatibility.
    """
    repo = UserConfigRepository(session)
    config_model = await repo.get_by_user_id(current_user.id)

    if not config_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User config not found")

    # Get effective config (merged with defaults from code)
    effective_config = await repo.get_effective_config(current_user.id)

    # Update model in memory for response (don't persist)
    config_model.config_data = effective_config

    return config_model


@router.patch("", response_model=UserConfigResponse)
async def update_user_config(
    update_data: UserConfigUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_active_user),
):
    repo = UserConfigRepository(session)
    config = await repo.get_by_user_id(current_user.id)

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User config not found")

    current_config = config.config_data
    update_dict = update_data.model_dump(exclude_unset=True)

    merged_config = deep_merge(current_config, update_dict)

    updated_config = await repo.update(config, merged_config)
    await session.commit()

    logger.info(f"User config updated: user_id={current_user.id}")

    return updated_config


@router.post("/reset", response_model=UserConfigResponse)
async def reset_user_config(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_active_user),
):
    repo = UserConfigRepository(session)
    config = await repo.get_by_user_id(current_user.id)

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User config not found")

    updated_config = await repo.update(config, DEFAULT_USER_CONFIG.copy())
    await session.commit()

    logger.info(f"User config reset to defaults: user_id={current_user.id}")

    return updated_config
