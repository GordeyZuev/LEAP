"""Unified application settings - single source of truth for all configuration"""

import warnings
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ============================================================================
# APP SETTINGS
# ============================================================================


class AppSettings(BaseSettings):
    """Application-level settings"""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        case_sensitive=False,
    )

    name: str = Field(default="LEAP API", description="Application name")
    version: str = Field(default="0.9.3", description="Application version")
    description: str = Field(
        default="AI-powered platform for intelligent educational video content processing",
        description="Application description",
    )
    debug: bool = Field(default=False, description="Debug mode")
    timezone: str = Field(default="Europe/Moscow", description="Application timezone")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone"""
        try:
            import pytz

            pytz.timezone(v)
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")
        return v


# ============================================================================
# SERVER SETTINGS
# ============================================================================


class ServerSettings(BaseSettings):
    """Server settings"""

    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        case_sensitive=False,
    )

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    reload: bool = Field(default=False, description="Auto-reload on code changes")
    workers: int = Field(default=4, ge=1, description="Number of Uvicorn workers")

    # API Documentation
    docs_url: str = Field(default="/docs", description="Swagger UI URL")
    redoc_url: str = Field(default="/redoc", description="ReDoc URL")
    openapi_url: str = Field(default="/openapi.json", description="OpenAPI schema URL")

    # CORS
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS")
    cors_allow_methods: list[str] = Field(default=["*"], description="Allowed HTTP methods")
    cors_allow_headers: list[str] = Field(default=["*"], description="Allowed HTTP headers")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


# ============================================================================
# DATABASE SETTINGS
# ============================================================================


class DatabaseSettings(BaseSettings):
    """PostgreSQL database settings"""

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        case_sensitive=False,
    )

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, ge=1, le=65535, description="Database port")
    database: str = Field(default="zoom_manager", description="Database name")
    username: str = Field(default="postgres", description="Database username")
    password: str = Field(default="", description="Database password")

    # Connection pool settings
    pool_size: int = Field(default=20, ge=1, description="Connection pool size")
    max_overflow: int = Field(default=10, ge=0, description="Max overflow connections")
    pool_timeout: int = Field(default=30, ge=1, description="Pool timeout in seconds")

    @property
    def url(self) -> str:
        """Async database URL"""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        """Sync database URL for Alembic"""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


# ============================================================================
# REDIS SETTINGS
# ============================================================================


class RedisSettings(BaseSettings):
    """Redis settings"""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        case_sensitive=False,
    )

    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    db: int = Field(default=0, ge=0, le=15, description="Redis database number")
    password: str = Field(default="", description="Redis password (optional)")

    @property
    def url(self) -> str:
        """Redis URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


# ============================================================================
# CELERY SETTINGS
# ============================================================================


class CelerySettings(BaseSettings):
    """Celery task queue settings"""

    model_config = SettingsConfigDict(
        env_prefix="CELERY_",
        case_sensitive=False,
    )

    # Broker & Backend (auto-constructed from Redis settings)
    broker_url: str = Field(default="redis://localhost:6379/0", description="Celery broker URL")
    result_backend: str = Field(default="redis://localhost:6379/0", description="Celery result backend URL")

    # Task execution limits
    task_time_limit: int = Field(default=3600, ge=60, description="Hard time limit per task (seconds)")
    task_soft_time_limit: int = Field(default=3300, ge=60, description="Soft time limit per task (seconds)")
    task_acks_late: bool = Field(default=True, description="Acknowledge tasks after completion")
    task_reject_on_worker_lost: bool = Field(default=True, description="Reject task if worker is lost")
    result_expires: int = Field(default=86400, ge=3600, description="Result expiration time (seconds)")

    # Worker settings
    worker_concurrency: int = Field(default=8, ge=1, description="Number of concurrent workers")
    worker_prefetch_multiplier: int = Field(default=1, ge=1, description="Worker prefetch multiplier")
    worker_max_tasks_per_child: int = Field(default=50, ge=1, description="Max tasks per worker before restart")

    # Default retry settings
    task_default_max_retries: int = Field(default=3, ge=0, description="Default max retries for tasks")
    task_default_retry_delay: int = Field(default=300, ge=0, description="Default retry delay (seconds)")

    # Task-specific retry settings
    download_max_retries: int = Field(default=3, ge=0, description="Max retries for download tasks")
    download_retry_delay: int = Field(default=600, ge=0, description="Retry delay for download tasks (seconds)")

    processing_max_retries: int = Field(default=2, ge=0, description="Max retries for processing tasks")
    processing_retry_delay: int = Field(default=180, ge=0, description="Retry delay for processing tasks (seconds)")

    upload_max_retries: int = Field(default=5, ge=0, description="Max retries for upload tasks")
    upload_retry_delay: int = Field(default=600, ge=0, description="Retry delay for upload tasks (seconds)")

    automation_max_retries: int = Field(default=1, ge=0, description="Max retries for automation tasks")
    automation_retry_delay: int = Field(default=300, ge=0, description="Retry delay for automation tasks (seconds)")

    sync_max_retries: int = Field(default=3, ge=0, description="Max retries for sync tasks")
    sync_retry_delay: int = Field(default=600, ge=0, description="Retry delay for sync tasks (seconds)")

    maintenance_max_retries: int = Field(default=2, ge=0, description="Max retries for maintenance tasks")
    maintenance_retry_delay: int = Field(default=300, ge=0, description="Retry delay for maintenance tasks (seconds)")

    @model_validator(mode="after")
    def validate_time_limits(self) -> "CelerySettings":
        """Validate that soft limit is less than hard limit"""
        if self.task_soft_time_limit >= self.task_time_limit:
            raise ValueError("task_soft_time_limit must be less than task_time_limit")
        return self


# ============================================================================
# SECURITY SETTINGS
# ============================================================================


class SecuritySettings(BaseSettings):
    """Security and authentication settings"""

    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        case_sensitive=False,
    )

    # JWT
    jwt_secret_key: str = Field(
        default="your-secret-key-change-in-production",
        min_length=32,
        description="JWT secret key (min 32 chars)",
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512", "RS256"] = Field(
        default="HS256", description="JWT signing algorithm"
    )
    jwt_access_token_expire_minutes: int = Field(
        default=30, ge=1, le=1440, description="Access token expiration (minutes)"
    )
    jwt_refresh_token_expire_days: int = Field(default=7, ge=1, le=30, description="Refresh token expiration (days)")

    # Password hashing
    bcrypt_rounds: int = Field(default=12, ge=4, le=31, description="BCrypt hashing rounds")

    # Encryption (Fernet)
    encryption_key: str = Field(default="", description="Fernet encryption key (base64, 32 bytes)")

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(default=60, ge=1, description="Requests per minute limit")
    rate_limit_per_hour: int = Field(default=1000, ge=1, description="Requests per hour limit")

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret key"""
        if v == "your-secret-key-change-in-production":
            warnings.warn(
                "Using default JWT secret key! Change it in production via SECURITY_JWT_SECRET_KEY",
                stacklevel=2,
            )
        if len(v) < 32:
            raise ValueError("JWT secret key must be at least 32 characters")
        return v

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """Validate Fernet encryption key"""
        if not v:
            return v
        try:
            import base64

            key_bytes = base64.urlsafe_b64decode(v)
            if len(key_bytes) != 32:
                raise ValueError("Encryption key must be 32 bytes when decoded")
        except Exception as e:
            raise ValueError(f"Invalid Fernet encryption key: {e}")
        return v


# ============================================================================
# STORAGE SETTINGS
# ============================================================================


class StorageSettings(BaseSettings):
    """File storage and media settings"""

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_",
        case_sensitive=False,
    )

    # Storage backend type
    type: Literal["LOCAL", "S3"] = Field(default="LOCAL", description="Storage backend type")

    # LOCAL storage settings
    local_path: str = Field(default="storage", description="Local storage root path")
    local_max_size_gb: int | None = Field(default=None, ge=1, description="Max local storage size (GB)")

    # S3 storage settings
    s3_bucket: str | None = Field(default=None, description="S3 bucket name")
    s3_prefix: str = Field(default="storage", description="S3 key prefix")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    s3_max_size_gb: int | None = Field(default=None, ge=1, description="Max S3 storage size (GB)")
    s3_access_key_id: str | None = Field(default=None, description="AWS access key ID")
    s3_secret_access_key: str | None = Field(default=None, description="AWS secret access key")
    s3_endpoint_url: str | None = Field(default=None, description="Custom S3 endpoint (for S3-compatible services)")

    log_dir: str = Field(default="logs", description="Log directory")

    # Thumbnails
    thumbnail_dir: str = Field(default="thumbnails", description="Thumbnail directory")
    template_thumbnail_dir: str = Field(default="storage/shared/thumbnails", description="Template thumbnail directory")

    # Max file sizes
    max_upload_size_mb: int = Field(default=5000, ge=1, description="Max upload size (MB)")
    max_thumbnail_size_mb: int = Field(default=10, ge=1, description="Max thumbnail size (MB)")

    # Supported formats
    supported_video_formats: list[str] = Field(
        default=["mp4", "avi", "mov", "mkv", "webm", "m4v"], description="Supported video formats"
    )
    supported_image_formats: list[str] = Field(
        default=["jpg", "jpeg", "png", "gif"], description="Supported image formats"
    )

    @model_validator(mode="after")
    def validate_storage_config(self) -> "StorageSettings":
        """Validate storage configuration based on type"""
        if self.type == "S3":
            if not self.s3_bucket:
                raise ValueError("STORAGE_S3_BUCKET is required when STORAGE_TYPE=S3")
            if not self.s3_access_key_id or not self.s3_secret_access_key:
                warnings.warn(
                    "S3 credentials not provided. Will attempt to use IAM role or environment credentials.",
                    stacklevel=2,
                )
        elif self.type == "LOCAL":
            # Ensure local storage directory exists
            local_path = Path(self.local_path)
            if not local_path.exists():
                try:
                    local_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    warnings.warn(f"Could not create storage directory {self.local_path}: {e}", stacklevel=2)
        return self

    @field_validator("log_dir")
    @classmethod
    def ensure_directory_exists(cls, v: str) -> str:
        """Ensure directory exists or can be created"""
        path = Path(v)
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                warnings.warn(f"Could not create directory {v}: {e}", stacklevel=2)
        return v


# ============================================================================
# LOGGING SETTINGS
# ============================================================================


class LoggingSettings(BaseSettings):
    """Logging configuration"""

    model_config = SettingsConfigDict(
        env_prefix="LOGGING_",
        case_sensitive=False,
    )

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", description="Logging level")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format string")
    file_path: str | None = Field(default=None, description="Log file path (None = console only)")
    max_bytes: int = Field(default=10485760, ge=1024, description="Max log file size in bytes (10MB)")
    backup_count: int = Field(default=5, ge=0, description="Number of backup log files")

    # Structured logging
    structured: bool = Field(default=False, description="Enable structured JSON logging")
    include_trace_id: bool = Field(default=True, description="Include trace ID in logs")


# ============================================================================
# MONITORING SETTINGS
# ============================================================================


class MonitoringSettings(BaseSettings):
    """Monitoring and observability settings"""

    model_config = SettingsConfigDict(
        env_prefix="MONITORING_",
        case_sensitive=False,
    )

    enabled: bool = Field(default=False, description="Enable monitoring")

    # Sentry
    sentry_dsn: str = Field(default="", description="Sentry DSN for error tracking")
    sentry_environment: str = Field(default="development", description="Sentry environment")
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Sentry traces sample rate")

    # Prometheus
    prometheus_enabled: bool = Field(default=False, description="Enable Prometheus metrics")
    prometheus_port: int = Field(default=9090, ge=1, le=65535, description="Prometheus metrics port")

    # Health checks
    health_check_enabled: bool = Field(default=True, description="Enable health check endpoint")


# ============================================================================
# OAUTH SETTINGS
# ============================================================================


class OAuthSettings(BaseSettings):
    """OAuth 2.0 settings for external platforms"""

    model_config = SettingsConfigDict(
        env_prefix="OAUTH_",
        case_sensitive=False,
    )

    # Base URL for callbacks
    base_url: str = Field(default="http://localhost:8000", description="Base URL for OAuth callbacks")

    # YouTube OAuth
    youtube_enabled: bool = Field(default=True, description="Enable YouTube OAuth")
    youtube_client_id: str = Field(default="", description="YouTube OAuth client ID")
    youtube_client_secret: str = Field(default="", description="YouTube OAuth client secret")
    youtube_redirect_uri: str = Field(
        default="http://localhost:8000/oauth/youtube/callback", description="YouTube OAuth redirect URI"
    )

    # VK OAuth
    vk_enabled: bool = Field(default=True, description="Enable VK OAuth")
    vk_client_id: str = Field(default="", description="VK OAuth client ID")
    vk_client_secret: str = Field(default="", description="VK OAuth client secret")
    vk_redirect_uri: str = Field(default="http://localhost:8000/oauth/vk/callback", description="VK OAuth redirect URI")

    # Zoom OAuth
    zoom_enabled: bool = Field(default=True, description="Enable Zoom OAuth")
    zoom_client_id: str = Field(default="", description="Zoom OAuth client ID")
    zoom_client_secret: str = Field(default="", description="Zoom OAuth client secret")
    zoom_redirect_uri: str = Field(
        default="http://localhost:8000/oauth/zoom/callback", description="Zoom OAuth redirect URI"
    )

    @field_validator("youtube_redirect_uri", "vk_redirect_uri", "zoom_redirect_uri")
    @classmethod
    def validate_redirect_uri(cls, v: str) -> str:
        """Validate redirect URI format"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Redirect URI must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def validate_enabled_platforms(self) -> "OAuthSettings":
        """Validate that enabled platforms have credentials"""
        if self.youtube_enabled and not (self.youtube_client_id and self.youtube_client_secret):
            warnings.warn("YouTube OAuth enabled but credentials missing", stacklevel=2)

        if self.vk_enabled and not (self.vk_client_id and self.vk_client_secret):
            warnings.warn("VK OAuth enabled but credentials missing", stacklevel=2)

        if self.zoom_enabled and not (self.zoom_client_id and self.zoom_client_secret):
            warnings.warn("Zoom OAuth enabled but credentials missing", stacklevel=2)

        return self


# ============================================================================
# FEATURE FLAGS
# ============================================================================


class FeatureFlagsSettings(BaseSettings):
    """Feature flags for enabling/disabling features"""

    model_config = SettingsConfigDict(
        env_prefix="FEATURE_",
        case_sensitive=False,
    )

    # Processing features
    auto_transcription: bool = Field(default=True, description="Enable automatic transcription")
    auto_topic_extraction: bool = Field(default=True, description="Enable automatic topic extraction")
    auto_subtitle_generation: bool = Field(default=True, description="Enable automatic subtitle generation")
    auto_thumbnail_generation: bool = Field(default=False, description="Enable automatic thumbnail generation")

    # Upload features
    scheduled_publishing: bool = Field(default=True, description="Enable scheduled publishing")
    batch_operations: bool = Field(default=True, description="Enable batch operations")

    # Automation
    automation_enabled: bool = Field(default=True, description="Enable automation system")
    automation_max_jobs_per_user: int = Field(default=10, ge=0, description="Max automation jobs per user")

    # Admin features
    admin_api_enabled: bool = Field(default=True, description="Enable admin API endpoints")
    user_stats_enabled: bool = Field(default=True, description="Enable user statistics")


# ============================================================================
# PROCESSING SETTINGS
# ============================================================================


class ProcessingSettings(BaseSettings):
    """Video processing settings"""

    model_config = SettingsConfigDict(
        env_prefix="PROCESSING_",
        case_sensitive=False,
    )

    # FFmpeg settings - stream copy (no re-encoding)
    video_codec: str = Field(default="copy", description="Video codec (copy = no re-encoding)")
    audio_codec: str = Field(default="copy", description="Audio codec (copy = no re-encoding)")
    video_bitrate: str = Field(default="original", description="Video bitrate (original = no change)")
    audio_bitrate: str = Field(default="original", description="Audio bitrate (original = no change)")
    fps: int = Field(default=0, ge=0, description="FPS (0 = no change)")
    resolution: str = Field(default="original", description="Resolution (original = no change)")

    # Silence detection
    silence_threshold: float = Field(default=-40.0, le=0.0, description="Silence threshold in dB")
    min_silence_duration: float = Field(default=2.0, ge=0.0, description="Min silence duration (seconds)")
    padding_before: float = Field(default=5.0, ge=0.0, description="Padding before audio (seconds)")
    padding_after: float = Field(default=5.0, ge=0.0, description="Padding after audio (seconds)")

    # Trimming
    remove_intro: bool = Field(default=True, description="Remove intro")
    remove_outro: bool = Field(default=True, description="Remove outro")
    intro_duration: float = Field(default=30.0, ge=0.0, description="Intro duration (seconds)")
    outro_duration: float = Field(default=30.0, ge=0.0, description="Outro duration (seconds)")

    # Cleanup
    keep_temp_files: bool = Field(default=False, description="Keep temporary files")


class RetentionSettings(BaseSettings):
    """Default retention policy settings for recordings"""

    model_config = SettingsConfigDict(
        env_prefix="RETENTION_",
        case_sensitive=False,
    )

    soft_delete_days: int = Field(
        default=3,
        ge=1,
        le=90,
        description="Days before files cleanup after deletion",
    )
    hard_delete_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Days before DB removal (from deleted_at)",
    )
    auto_expire_days: int = Field(
        default=90,
        ge=1,
        le=730,
        description="Days before auto-expiration for active recordings",
    )


# ============================================================================
# MAIN SETTINGS
# ============================================================================


class Settings(BaseSettings):
    """Main application settings - single source of truth"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # All settings sections
    app: AppSettings = Field(default_factory=AppSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    oauth: OAuthSettings = Field(default_factory=OAuthSettings)
    features: FeatureFlagsSettings = Field(default_factory=FeatureFlagsSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Validate critical settings for production"""
        # Only validate in strict production mode (when explicitly set, not default)
        # Allow default values for development/testing
        import os

        # Check if running in strict production mode (explicitly set APP_DEBUG=false)
        is_strict_production = os.getenv("APP_DEBUG", "").lower() == "false"

        if is_strict_production:
            # JWT secret must not be default
            if self.security.jwt_secret_key == "your-secret-key-change-in-production":
                raise ValueError("JWT secret key must be changed in production!")

            # Database password should not be empty (warning only)
            if not self.database.password:
                import warnings

                warnings.warn("Database password is empty in production mode", stacklevel=2)

        return self

    @model_validator(mode="after")
    def sync_redis_to_celery(self) -> "Settings":
        """Auto-sync Redis settings to Celery if not explicitly set"""
        # If Celery URLs are default, construct from Redis settings
        if self.celery.broker_url == "redis://localhost:6379/0":
            self.celery.broker_url = self.redis.url

        if self.celery.result_backend == "redis://localhost:6379/0":
            self.celery.result_backend = self.redis.url

        return self


# ============================================================================
# DEFAULT USER CONFIGURATION
# ============================================================================

# Default user configuration
# This is the base configuration for all users, can be overridden per-user in DB
DEFAULT_USER_CONFIG = {
    "trimming": {
        "enable_trimming": True,
        "audio_detection": True,
        "silence_threshold": -40.0,
        "min_silence_duration": 2.0,
        "padding_before": 5.0,
        "padding_after": 5.0,
    },
    "transcription": {
        "enable_transcription": True,
        "provider": "fireworks",
        "language": "ru",
        "prompt": "",
        "temperature": 0.0,
        "granularity": "long",
        "enable_topics": True,
        "topic_mode": "long",
        "enable_subtitles": True,
        "subtitle_formats": ["srt", "vtt"],
        "enable_translation": False,
        "translation_language": "en",
    },
    "download": {
        "auto_download": False,
        "max_file_size_mb": 5000,
        "quality": "high",
        "retry_attempts": 3,
        "retry_delay": 5,
    },
    "upload": {
        "auto_upload": False,
        "upload_captions": True,
        "default_platforms": [],
        "default_preset_ids": {},
    },
    "metadata": {
        "title_template": "{display_name} | {topic} ({date})",
        "description_template": "Запись от {date}",
        "date_format": "DD.MM.YYYY",
        "tags": [],
        "thumbnail_name": None,
        "category": None,
        "topics_display": {
            "enabled": True,
            "max_count": 999,
            "min_length": 0,
            "max_length": 999,
            "display_location": "description",
            "format": "numbered_list",
            "separator": "\n",
            "prefix": "Темы:",
            "include_timestamps": False,
        },
    },
    "retention": {
        "soft_delete_days": 3,
        "hard_delete_days": 30,
        "auto_expire_days": 90,
    },
    "platforms": {
        "youtube": {
            "enabled": False,
            "default_privacy": "unlisted",
            "default_language": "ru",
        },
        "vk_video": {
            "enabled": False,
            "privacy_view": 0,
            "privacy_comment": 1,
            "no_comments": False,
            "repeat": False,
        },
    },
}


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """Get settings singleton instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reset_settings() -> None:
    """Reset settings singleton (useful for testing)"""
    global _settings_instance
    _settings_instance = None


# Convenience instance for direct import
settings = get_settings()
