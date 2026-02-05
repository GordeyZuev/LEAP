"""Service Context для передачи user_id и session через все сервисы.

Implements the Context Object pattern to avoid passing many parameters
through a chain of function calls.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.config_service import ConfigService


@dataclass
class ServiceContext:
    """
    Context for executing an operation for a user.

    Centralizes access to session, user_id and config_helper,
    avoiding passing many parameters.
    """

    session: AsyncSession
    user_id: str

    def __post_init__(self):
        """Initialization of config_helper."""
        self._config_helper: ConfigService | None = None

    @property
    def config_helper(self) -> ConfigService:
        """
        Lazy-loaded ConfigService for accessing credentials.
        """
        if self._config_helper is None:
            self._config_helper = ConfigService(self.session, self.user_id)
        return self._config_helper

    @classmethod
    def create(cls, session: AsyncSession, user_id: str) -> "ServiceContext":
        """
        Factory method for creating a context.
        """
        return cls(session=session, user_id=user_id)
