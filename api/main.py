import shutil
import subprocess

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

# Explicitly import Celery tasks to register them in the API server
import api.tasks.automation
import api.tasks.maintenance
import api.tasks.processing
import api.tasks.sync_tasks
import api.tasks.template
import api.tasks.upload  # noqa: F401
from api.middleware.error_handler import (
    api_exception_handler,
    global_exception_handler,
    http_exception_handler,
    response_validation_exception_handler,
    sqlalchemy_exception_handler,
    validation_exception_handler,
)
from api.middleware.logging import LoggingMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.routers import (
    admin,
    auth,
    automation,
    credentials,
    health,
    input_sources,
    oauth,
    output_presets,
    recordings,
    tasks,
    templates,
    thumbnails,
    user_config,
    users,
)
from api.shared.exceptions import APIException
from config.settings import get_settings
from database.config import DatabaseConfig
from database.manager import DatabaseManager
from logger import get_logger

settings = get_settings()
logger = get_logger()

app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    description=settings.app.description,
    docs_url=settings.server.docs_url,
    redoc_url=settings.server.redoc_url,
    openapi_url=settings.server.openapi_url,
)


@app.on_event("startup")
async def startup_event():
    """Initializing database on application startup."""
    try:
        logger.info("🚀 Initializing database...")

        # Create database if it doesn't exist
        db_config = DatabaseConfig.from_env()
        db_manager = DatabaseManager(db_config)
        await db_manager.create_database_if_not_exists()
        await db_manager.close()

        logger.info("✅ Database created (if not existed)")

        # Apply Alembic migrations
        logger.info("🔄 Applying Alembic migrations...")
        alembic_cmd = shutil.which("alembic") or "alembic"
        result = subprocess.run(
            [alembic_cmd, "upgrade", "head"],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            logger.info("✅ Migrations applied successfully")
        else:
            logger.error(f"❌ Error applying migrations: {result.stderr}")

    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")


# CORS middleware
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=settings.server.cors_origins,
    allow_credentials=settings.server.cors_allow_credentials,
    allow_methods=settings.server.cors_allow_methods,
    allow_headers=settings.server.cors_allow_headers,
)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware)  # type: ignore[arg-type]

# Logging middleware
app.add_middleware(LoggingMiddleware)  # type: ignore[arg-type]

# Exception handlers (order matters: specific first, generic last)
app.add_exception_handler(APIException, api_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(ResponseValidationError, response_validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, global_exception_handler)

# Routers
app.include_router(health.router)

app.include_router(auth.router)
app.include_router(oauth.router)

app.include_router(users.router)
app.include_router(user_config.router)
app.include_router(credentials.router)

app.include_router(recordings.router)
app.include_router(templates.router)
app.include_router(input_sources.router)
app.include_router(output_presets.router)
app.include_router(automation.router)

app.include_router(thumbnails.router)
app.include_router(admin.router)
app.include_router(tasks.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "LEAP API",
        "version": settings.app.version,
        "docs": settings.server.docs_url,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
    )
