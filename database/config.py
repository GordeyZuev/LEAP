"""PostgreSQL connection configuration"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings import settings


class DatabaseConfig(BaseSettings):
    """PostgreSQL connection configuration"""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    host: str = Field(default_factory=lambda: settings.database.host)
    port: int = Field(default_factory=lambda: settings.database.port, ge=1, le=65535)
    database: str = Field(default_factory=lambda: settings.database.database)
    username: str = Field(default_factory=lambda: settings.database.username)
    password: str = Field(default_factory=lambda: settings.database.password)

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from Pydantic Settings."""
        return cls()

    @property
    def url(self) -> str:
        """PostgreSQL async URL for asyncpg."""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        """PostgreSQL sync URL for Alembic."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
