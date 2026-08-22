"""User configuration repository"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.default_template import account_only_user_config, product_default_account_config
from api.services.merger import deep_merge
from database.config_models import UserConfigModel


class UserConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> UserConfigModel | None:
        result = await self.session.execute(select(UserConfigModel).where(UserConfigModel.user_id == user_id))
        return result.scalars().first()

    async def get_effective_config(self, user_id: str) -> dict:
        """
        Get account-level user config (retention, download, platforms) merged with defaults.

        Args:
            user_id: User ID

        Returns:
            Merged configuration dict (deep copy)
        """
        user_config_model = await self.get_by_user_id(user_id)

        if not user_config_model:
            return product_default_account_config()

        stored = account_only_user_config(cast("dict", user_config_model.config_data))
        return deep_merge(product_default_account_config(), stored)

    async def create(self, user_id: str, config_data: dict) -> UserConfigModel:
        config = UserConfigModel(user_id=user_id, config_data=config_data)
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def update(self, config: UserConfigModel, config_data: dict) -> UserConfigModel:
        config.config_data = config_data
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def delete(self, config: UserConfigModel) -> None:
        await self.session.delete(config)
        await self.session.flush()
