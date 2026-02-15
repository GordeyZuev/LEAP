import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def http_filter(record):
    """Filter out verbose HTTP logs from third-party libraries."""
    if record["name"].startswith(("httpx", "httpcore", "hpack")):
        return record["level"].no >= 30  # Only WARNING and above
    return True


# ---------------------------------------------------------------------------
# Format helpers (two-level separators: | for zones, • for related items)
# ---------------------------------------------------------------------------


def _build_context(record) -> str:
    """Build context zone from extra fields set via logger.contextualize().

    Returns string like: ``Task=8a5d • Rec=486 • User=01KF • Platform=vk``
    or empty string when no context is set.
    """
    extra = record["extra"]
    parts: list[str] = []
    for key, label in [
        ("task_id", "Task"),
        ("recording_id", "Rec"),
        ("user_id", "User"),
        ("platform", "Platform"),
    ]:
        val = extra.get(key)
        if val is not None:
            parts.append(f"{label}={val}")
    return " \u2022 ".join(parts)


def _console_format(record) -> str:
    """Dynamic format for console (colored) with optional context zone."""
    ctx = _build_context(record)
    ctx_zone = f" | {ctx}" if ctx else ""
    return (
        "<green>{time:YY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[module]: <25}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
        f"{ctx_zone}"
        " | <level>{message}</level>\n{exception}"
    )


def _file_format(record) -> str:
    """Dynamic format for file (plain text) with optional context zone."""
    ctx = _build_context(record)
    ctx_zone = f" | {ctx}" if ctx else ""
    return (
        "{time:YY-MM-DD HH:mm:ss} | {level: <8} | "
        "{extra[module]: <25} | "
        "{name}:{function}:{line}"
        f"{ctx_zone}"
        " | {message}\n{exception}"
    )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup_logger(log_level: str | None = None, log_file: str | None = None) -> None:
    """Setup logger with two-level separator format and optional JSON sink."""
    if log_level is None:
        console_level = os.getenv("LOG_LEVEL", "INFO")
    else:
        console_level = log_level

    env_log_file = os.getenv("LOG_FILE")
    error_log_file = os.getenv("ERROR_LOG_FILE")
    json_log_file = os.getenv("JSON_LOG_FILE")
    if log_file is None:
        log_file = env_log_file

    logger.remove()
    logger.configure(
        extra={
            "module": "app",
            "task_id": None,
            "recording_id": None,
            "user_id": None,
            "platform": None,
        }
    )

    # Console handler
    logger.add(
        sys.stderr,
        format=_console_format,
        level=console_level,
        colorize=True,
        filter=http_filter,
    )

    # Human-readable file handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            format=_file_format,
            level="INFO",
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            filter=http_filter,
        )

    # Error-only file handler
    if error_log_file:
        err_path = Path(error_log_file)
        err_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            error_log_file,
            format=_file_format,
            level="ERROR",
            rotation="10 MB",
            retention="14 days",
            compression="zip",
        )

    # JSON structured sink (for future monitoring / Grafana / alerting)
    if json_log_file:
        json_path = Path(json_log_file)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            json_log_file,
            serialize=True,
            level="INFO",
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            filter=http_filter,
        )

    # Suppress noisy third-party loggers at stdlib level
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_logger(module_name: str | None = None):
    """Get configured logger, optionally bound to a module name."""
    if module_name:
        return logger.bind(module=module_name)
    return logger


def short_task_id(task_id: Any) -> str:
    """First 8 chars of task UUID for compact logging."""
    return str(task_id)[:8] if task_id else "unknown"


def short_user_id(user_id: Any) -> str:
    """First 8 chars of user ULID for compact logging."""
    return str(user_id)[:8] if user_id else "unknown"


def format_details(**kwargs: Any) -> str:
    """Format key=value pairs joined with • for the details zone.

    Example: "Transcription complete | words=16912 • segments=408 • lang=ru"
    """
    if not kwargs:
        return ""
    return " \u2022 ".join(f"{k}={v}" for k, v in kwargs.items())


def format_status_change(entity: str, old: str, new: str) -> str:
    """Format a state transition message.

    Example: "Recording: INITIALIZED → DOWNLOADING"
    """
    return f"{entity}: {old} \u2192 {new}"


def format_task_context(
    task_id: str | None = None,
    recording_id: int | None = None,
    user_id: str | None = None,
    platform: str | None = None,
    **extra,
) -> str:
    """Format task context string for use *outside* of ``contextualize()`` scope.

    Example: "Task=abc12345 • Rec=123 • User=01KFHA26"
    """
    parts: list[str] = []

    if task_id:
        parts.append(f"Task={short_task_id(task_id)}")
    if recording_id is not None:
        parts.append(f"Rec={recording_id}")
    if user_id:
        parts.append(f"User={short_user_id(user_id)}")
    if platform:
        parts.append(f"Platform={platform}")

    for key, value in extra.items():
        parts.append(f"{key}={value}")

    return " \u2022 ".join(parts) if parts else ""


# Keep old name as alias for gradual migration
format_log = format_details


setup_logger()
