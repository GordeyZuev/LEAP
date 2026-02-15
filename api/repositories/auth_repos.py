"""Authentication and user repositories"""

from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.auth import (
    RefreshTokenCreate,
    RefreshTokenInDB,
    UserCreate,
    UserCredentialCreate,
    UserCredentialInDB,
    UserCredentialUpdate,
    UserInDB,
    UserUpdate,
)
from database.auth_models import RefreshTokenModel, UserCredentialModel, UserModel


class UserRepository:
    """Repository for working with users."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str) -> UserInDB | None:
        """Get user by ID."""
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        db_user = result.scalars().first()
        if not db_user:
            return None
        return UserInDB.model_validate(db_user)

    async def get_by_email(self, email: str) -> UserInDB | None:
        """Get user by email."""
        result = await self.session.execute(select(UserModel).where(UserModel.email == email))
        db_user = result.scalars().first()
        if not db_user:
            return None
        return UserInDB.model_validate(db_user)

    async def create(self, user_data: UserCreate, hashed_password: str) -> UserInDB:
        """Create a new user."""
        user = UserModel(
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return UserInDB.model_validate(user)

    async def update(self, user_id: str, user_data: UserUpdate) -> UserInDB | None:
        """Update user."""
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        db_user = result.scalars().first()
        if not db_user:
            return None

        update_dict = user_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(db_user, key, value)

        await self.session.commit()
        await self.session.refresh(db_user)
        return UserInDB.model_validate(db_user)


class RefreshTokenRepository:
    """Repository for working with refresh tokens."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, token_data: RefreshTokenCreate) -> RefreshTokenInDB:
        """Create refresh token."""
        refresh_token = RefreshTokenModel(
            user_id=token_data.user_id,
            token=token_data.token,
            expires_at=token_data.expires_at,
        )
        self.session.add(refresh_token)
        await self.session.commit()
        await self.session.refresh(refresh_token)
        return RefreshTokenInDB.model_validate(refresh_token)

    async def get_by_token(self, token: str) -> RefreshTokenInDB | None:
        """Get active, non-expired refresh token."""
        result = await self.session.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.token == token,
                RefreshTokenModel.expires_at > datetime.now(UTC),
                RefreshTokenModel.is_revoked.is_(False),
            )
        )
        db_token = result.scalars().first()
        if not db_token:
            return None

        return RefreshTokenInDB.model_validate(db_token)

    async def revoke(self, token: str) -> RefreshTokenInDB | None:
        """Revoke refresh token."""
        result = await self.session.execute(select(RefreshTokenModel).where(RefreshTokenModel.token == token))
        db_token = result.scalars().first()
        if db_token:
            db_token.is_revoked = True
            await self.session.commit()
            await self.session.refresh(db_token)
            return RefreshTokenInDB.model_validate(db_token)
        return None

    async def revoke_all_by_user(self, user_id: str) -> int:
        """Revoke all active refresh tokens for user."""
        result = await self.session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await self.session.commit()
        return result.rowcount

    async def delete_expired(self) -> int:
        """Delete all expired tokens."""
        result = await self.session.execute(
            delete(RefreshTokenModel).where(RefreshTokenModel.expires_at < datetime.now(UTC))
        )
        await self.session.commit()
        return result.rowcount


class UserCredentialRepository:
    """Repository for working with user credentials."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, credential_data: UserCredentialCreate) -> UserCredentialInDB:
        """Create user credentials."""
        credential = UserCredentialModel(
            user_id=credential_data.user_id,
            platform=credential_data.platform,
            account_name=credential_data.account_name,
            encrypted_data=credential_data.encrypted_data,
        )
        self.session.add(credential)
        await self.session.commit()
        await self.session.refresh(credential)
        return UserCredentialInDB.model_validate(credential)

    async def get_by_platform(
        self, user_id: str, platform: str, account_name: str | None = None
    ) -> UserCredentialInDB | None:
        """
        Get user credentials for platform.

        Args:
            user_id: User ID
            platform: Platform
            account_name: Account name (optional, for multiple accounts)

        Returns:
            User credentials or None
        """
        query = select(UserCredentialModel).where(
            UserCredentialModel.user_id == user_id,
            UserCredentialModel.platform == platform,
            UserCredentialModel.is_active,
        )

        if account_name is not None:
            query = query.where(UserCredentialModel.account_name == account_name)
        else:
            # If account_name is not specified, take the first found
            query = query.where(UserCredentialModel.account_name.is_(None))

        result = await self.session.execute(query)
        db_credential = result.scalars().first()
        if not db_credential:
            return None
        return UserCredentialInDB.model_validate(db_credential)

    async def get_by_id(self, credential_id: int) -> UserCredentialInDB | None:
        """Get credentials by ID."""
        result = await self.session.execute(select(UserCredentialModel).where(UserCredentialModel.id == credential_id))
        db_credential = result.scalars().first()
        if not db_credential:
            return None
        return UserCredentialInDB.model_validate(db_credential)

    async def list_by_platform(self, user_id: str, platform: str) -> list[UserCredentialInDB]:
        """Get all user credentials for platform."""
        result = await self.session.execute(
            select(UserCredentialModel).where(
                UserCredentialModel.user_id == user_id,
                UserCredentialModel.platform == platform,
                UserCredentialModel.is_active,
            )
        )
        db_credentials = result.scalars().all()
        return [UserCredentialInDB.model_validate(cred) for cred in db_credentials]

    async def update(self, credential_id: int, credential_data: UserCredentialUpdate) -> UserCredentialInDB | None:
        """Update user credentials."""
        result = await self.session.execute(select(UserCredentialModel).where(UserCredentialModel.id == credential_id))
        db_credential = result.scalars().first()
        if not db_credential:
            return None

        update_dict = credential_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(db_credential, key, value)

        await self.session.commit()
        await self.session.refresh(db_credential)
        return UserCredentialInDB.model_validate(db_credential)

    async def delete(self, credential_id: int) -> bool:
        """Delete user credentials."""
        result = await self.session.execute(select(UserCredentialModel).where(UserCredentialModel.id == credential_id))
        db_credential = result.scalars().first()
        if db_credential:
            await self.session.delete(db_credential)
            await self.session.commit()
            return True
        return False

    async def find_by_user(self, user_id: str) -> list[UserCredentialInDB]:
        """Get all user credentials."""
        result = await self.session.execute(select(UserCredentialModel).where(UserCredentialModel.user_id == user_id))
        db_credentials = result.scalars().all()
        return [UserCredentialInDB.model_validate(cred) for cred in db_credentials]
