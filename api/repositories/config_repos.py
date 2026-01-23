"""User configuration repository"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import DEFAULT_USER_CONFIG
from database.config_models import UserConfigModel


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries.

    Base values are used as defaults, override values take precedence.
    Nested dicts are merged recursively.

    Creates a deep copy to avoid mutating original dicts.
    """
    import copy

    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            # Deep copy the value to avoid reference issues
            result[key] = copy.deepcopy(value)
    return result


class UserConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> UserConfigModel | None:
        result = await self.session.execute(select(UserConfigModel).where(UserConfigModel.user_id == user_id))
        return result.scalars().first()

    async def get_effective_config(self, user_id: str) -> dict:
        """
        Get user config merged with defaults.

        Returns effective configuration with:
        - Default values from DEFAULT_USER_CONFIG constant
        - User-specific overrides from database

        This ensures backward compatibility - users automatically get new config fields
        (like retention settings) without manual migration.

        Args:
            user_id: User ID

        Returns:
            Merged configuration dict (deep copy)
        """
        import copy

        user_config_model = await self.get_by_user_id(user_id)

        if not user_config_model:
            # User has no config yet, return deep copy of defaults
            return copy.deepcopy(DEFAULT_USER_CONFIG)

        # Merge: defaults as base, user overrides on top (deep_merge does deep copy)
        return deep_merge(DEFAULT_USER_CONFIG, user_config_model.config_data)

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
