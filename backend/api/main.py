"""FastAPI application entrypoint and router configuration."""

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
from api.middleware.csrf import CSRFMiddleware
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
from api.observability import setup_prometheus
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
    references,
    storage,
    tasks,
    templates,
    thumbnails,
    user_config,
    users,
)
from api.shared.exceptions import APIException
from config.settings import get_settings

settings = get_settings()


app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    description=settings.app.description,
    docs_url=settings.server.docs_url,
    redoc_url=settings.server.redoc_url,
    openapi_url=settings.server.openapi_url,
)

app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=settings.server.cors_origins,
    allow_credentials=settings.server.cors_allow_credentials,
    allow_methods=settings.server.cors_allow_methods,
    allow_headers=settings.server.cors_allow_headers,
)
# CSRF runs after CORS (so preflight OPTIONS passes) but before route dispatch.
app.add_middleware(CSRFMiddleware)  # type: ignore[arg-type]
app.add_middleware(RateLimitMiddleware)  # type: ignore[arg-type]
app.add_middleware(LoggingMiddleware)  # type: ignore[arg-type]

# Prometheus /metrics — instrumented before routers so it observes them.
# Gated by settings so local dev runs don't expose the endpoint by default.
setup_prometheus(app, enabled=settings.monitoring.prometheus_enabled)
app.add_exception_handler(APIException, api_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(ResponseValidationError, response_validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, global_exception_handler)

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

app.include_router(references.router)
app.include_router(thumbnails.router)
app.include_router(storage.router)
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
