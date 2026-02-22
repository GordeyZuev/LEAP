"""User config API: per-user preferences (trimming, transcription, etc.)."""

import copy

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.dependencies import get_db_session
from api.repositories.config_repos import UserConfigRepository, deep_merge
from api.schemas.auth import UserInDB
from api.schemas.config.user_config import UserConfigResponse, UserConfigUpdate
from config.settings import DEFAULT_USER_CONFIG
from logger import get_logger

router = APIRouter(prefix="/api/v1/users/me/config", tags=["User Config"])
logger = get_logger()


@router.get("", response_model=UserConfigResponse)
async def get_user_config(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Get user config with automatic merge of new default fields.

    Uses UserConfigRepository.get_effective_config() to ensure backward compatibility.
    If user has no config in DB (shouldn't happen after registration), creates it lazily.
    """
    repo = UserConfigRepository(session)
    config_model = await repo.get_by_user_id(current_user.id)

    if not config_model:
        # Shouldn't happen if registration works correctly, but handle gracefully
        effective_config = await repo.get_effective_config(current_user.id)
        config_model = await repo.create(current_user.id, effective_config)
        await session.commit()
        logger.warning(f"Config was missing for user {current_user.id}, created lazily")
        return config_model

    # Get effective config (merged with defaults from code)
    effective_config = await repo.get_effective_config(current_user.id)

    # Update model in memory for response (don't persist)
    config_model.config_data = effective_config

    return config_model


@router.patch("", response_model=UserConfigResponse)
async def update_user_config(
    update_data: UserConfigUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Update user config with partial data.

    Requires existing config (should be created during registration).
    """
    repo = UserConfigRepository(session)
    config = await repo.get_by_user_id(current_user.id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User config not found. This indicates a data integrity issue.",
        )

    # deep_merge will handle deep copying
    update_dict = update_data.model_dump(exclude_unset=True)
    merged_config = deep_merge(config.config_data, update_dict)

    config = await repo.update(config, merged_config)
    await session.commit()

    logger.info(f"User config updated: user_id={current_user.id}")
    return config


@router.post("/reset", response_model=UserConfigResponse)
async def reset_user_config(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Reset user config to default values.

    Requires existing config (should be created during registration).
    """
    repo = UserConfigRepository(session)
    config = await repo.get_by_user_id(current_user.id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User config not found. This indicates a data integrity issue.",
        )

    # Deep copy to avoid mutating the global DEFAULT_USER_CONFIG
    config = await repo.update(config, copy.deepcopy(DEFAULT_USER_CONFIG))
    await session.commit()

    logger.info(f"User config reset to defaults: user_id={current_user.id}")
    return config
