from urllib.parse import urlparse

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from logger import get_logger

from .config import DatabaseConfig
from .models import Base

logger = get_logger()


class DatabaseManager:
    """Database lifecycle manager (creation, migrations, cleanup)."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = create_async_engine(config.url, echo=False)
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def create_database_if_not_exists(self):
        """Create the database if it does not exist."""
        try:
            parsed = urlparse(self.config.url)

            conn = await asyncpg.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database="postgres",
            )

            result = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", self.config.database)

            if not result:
                await conn.execute(f'CREATE DATABASE "{self.config.database}"')
                logger.info(f"Database created: database={self.config.database}")

            await conn.close()

        except Exception as e:
            logger.error(f"Error creating database: database={self.config.database} | error={e}")
            raise

    async def recreate_database(self):
        """Full database recreation: deletion and creation again."""
        try:
            parsed = urlparse(self.config.url)

            try:
                await self.close()
            except Exception as e:
                logger.debug(f"Error closing connection (may not exist yet): {e}")

            conn = await asyncpg.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database="postgres",
            )

            db_exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", self.config.database)

            if db_exists:
                try:
                    await conn.execute(
                        """
                        SELECT pg_terminate_backend(pg_stat_activity.pid)
                        FROM pg_stat_activity
                        WHERE pg_stat_activity.datname = $1
                        AND pid <> pg_backend_pid()
                    """,
                        self.config.database,
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to terminate all connections: database={self.config.database}",
                        database=self.config.database,
                        error=str(e),
                    )

                db_name_quoted = self.config.database.replace('"', '""')
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_name_quoted}"')
                logger.info(f"Database deleted: database={self.config.database}")

            db_name_quoted = self.config.database.replace('"', '""')
            await conn.execute(f'CREATE DATABASE "{db_name_quoted}"')
            logger.info(f"Database created: database={self.config.database}")

            await conn.close()

            self.engine = create_async_engine(self.config.url, echo=False)
            self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

            await self.create_tables()

            logger.info(f"Database fully recreated: database={self.config.database}")

        except Exception as e:
            logger.error(f"Error recreating database: database={self.config.database} | error={e}")
            raise

    async def create_tables(self):
        """Create tables in the database."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Tables created")
        except Exception as e:
            logger.error(f"Error creating tables: error={e}")
            raise

    async def close(self):
        """Close database connection."""
        if hasattr(self, "engine") and self.engine is not None:
            await self.engine.dispose()
            logger.info("Database connection closed")
