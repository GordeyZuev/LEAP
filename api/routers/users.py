"""User profile management endpoints"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.auth.security import PasswordHelper
from api.dependencies import get_db_session
from api.repositories.auth_repos import (
    RefreshTokenRepository,
    UserRepository,
)
from api.repositories.recording_repos import RecordingRepository
from api.schemas.auth import QuotaStatusResponse, UserInDB, UserResponse, UserUpdate
from api.schemas.auth.response import UserMeResponse
from api.schemas.user import (
    AccountDeleteResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    PasswordChangeResponse,
    UserProfileUpdate,
)
from api.schemas.user.stats import UserStatsResponse
from api.services.quota_service import QuotaService
from api.services.stats_service import StatsService
from database.auth_models import (
    RefreshTokenModel,
    UserCredentialModel,
    UserModel,
)
from database.config_models import UserConfigModel
from database.models import (
    OutputTargetModel,
    ProcessingStageModel,
    RecordingModel,
    SourceMetadataModel,
)
from database.template_models import (
    InputSourceModel,
    OutputPresetModel,
    RecordingTemplateModel,
)
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/v1/users", tags=["User Management"])


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    current_user: UserInDB = Depends(get_current_user),
):
    """Get current user profile (use /me/quota for quota information)."""
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        timezone=current_user.timezone,
        role=current_user.role,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_my_stats(
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    from_date: date | None = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
):
    """Get usage statistics: recordings, transcription minutes, storage. Optional date range filter."""
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'from' must be <= 'to'")

    stats_service = StatsService(session)
    return await stats_service.get_user_stats(current_user.id, current_user.user_slug, from_date, to_date)


@router.get("/me/quota", response_model=QuotaStatusResponse)
async def get_my_quota(
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get current quota status with usage, limits, and pay-as-you-go info."""
    quota_service = QuotaService(session)

    try:
        return await quota_service.get_quota_status(current_user.id, current_user.user_slug)
    except ValueError as e:
        logger.error(f"Error getting quota status for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfileUpdate,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Update current user profile (full_name, email)."""
    user_repo = UserRepository(session)

    # Check that email is not used by another user
    if profile_data.email and profile_data.email != current_user.email:
        existing_user = await user_repo.get_by_email(profile_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use by another user",
            )

    # Update only fields that were passed (exclude_unset)
    user_update = UserUpdate(**profile_data.model_dump(exclude_unset=True))

    updated_user = await user_repo.update(current_user.id, user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    logger.info(f"User profile updated: {updated_user.email} (ID: {updated_user.id})")

    return UserResponse.model_validate(updated_user)


@router.post("/me/password", response_model=PasswordChangeResponse, status_code=status.HTTP_200_OK)
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PasswordChangeResponse:
    """Change password and revoke all active sessions."""
    # Check current password
    if not PasswordHelper.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Check that new password is different from old
    if PasswordHelper.verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    # Hash new password
    new_hashed_password = PasswordHelper.hash_password(password_data.new_password)

    # Update password in DB
    result = await session.execute(select(UserModel).where(UserModel.id == current_user.id))
    db_user = result.scalars().first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db_user.hashed_password = new_hashed_password
    await session.commit()

    # Revoke all refresh tokens (logout on all devices)
    token_repo = RefreshTokenRepository(session)
    result = await session.execute(select(RefreshTokenModel).where(RefreshTokenModel.user_id == current_user.id))
    tokens = result.scalars().all()
    for token in tokens:
        await token_repo.revoke(token.token)

    logger.info(f"Password changed for user: {current_user.email} (ID: {current_user.id})")

    return PasswordChangeResponse(
        message="Password changed successfully",
        detail="All active sessions have been terminated. Please login again.",
    )


@router.delete("/me", response_model=AccountDeleteResponse, status_code=status.HTTP_200_OK)
async def delete_account(
    delete_data: DeleteAccountRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AccountDeleteResponse:
    """
    Permanently delete account and all associated data (IRREVERSIBLE).

    Deletes: profile, recordings, credentials, templates, presets, tokens.
    """
    # Check password
    if not PasswordHelper.verify_password(delete_data.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )

    user_id = current_user.id
    user_email = current_user.email

    # Delete all related data (in correct order due to FK)
    # 1. Output targets
    result = await session.execute(select(OutputTargetModel).where(OutputTargetModel.user_id == user_id))
    output_targets = result.scalars().all()
    for target in output_targets:
        await session.delete(target)

    # 2. Processing stages
    result = await session.execute(select(ProcessingStageModel).where(ProcessingStageModel.user_id == user_id))
    stages = result.scalars().all()
    for stage in stages:
        await session.delete(stage)

    # 3. Source metadata
    result = await session.execute(select(SourceMetadataModel).where(SourceMetadataModel.user_id == user_id))
    sources = result.scalars().all()
    for source in sources:
        await session.delete(source)

    # 4. Recordings (use repository to delete files and update quota)
    result = await session.execute(select(RecordingModel).where(RecordingModel.user_id == user_id))
    recordings = result.scalars().all()
    recording_repo = RecordingRepository(session)
    for recording in recordings:
        await recording_repo.delete(recording)

    # 5. Templates
    result = await session.execute(select(RecordingTemplateModel).where(RecordingTemplateModel.user_id == user_id))
    templates = result.scalars().all()
    for template in templates:
        await session.delete(template)

    # 6. Output presets
    result = await session.execute(select(OutputPresetModel).where(OutputPresetModel.user_id == user_id))
    presets = result.scalars().all()
    for preset in presets:
        await session.delete(preset)

    # 7. Input sources
    result = await session.execute(select(InputSourceModel).where(InputSourceModel.user_id == user_id))
    input_sources = result.scalars().all()
    for input_source in input_sources:
        await session.delete(input_source)

    # 8. User config
    result = await session.execute(select(UserConfigModel).where(UserConfigModel.user_id == user_id))
    user_config = result.scalars().first()
    if user_config:
        await session.delete(user_config)

    # 9. Credentials
    result = await session.execute(select(UserCredentialModel).where(UserCredentialModel.user_id == user_id))
    credentials = result.scalars().all()
    for credential in credentials:
        await session.delete(credential)

    # 10. Refresh tokens
    result = await session.execute(select(RefreshTokenModel).where(RefreshTokenModel.user_id == user_id))
    tokens = result.scalars().all()
    for token in tokens:
        await session.delete(token)

    # 11. User (last!) - subscriptions and quotas will be deleted via CASCADE
    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    db_user = result.scalars().first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await session.delete(db_user)
    await session.commit()

    logger.info(f"Account deleted: {user_email} (ID: {user_id})")

    return AccountDeleteResponse(
        message="Account successfully deleted",
        detail="All your data has been permanently removed from our system.",
    )
