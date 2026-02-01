import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()


def http_filter(record):
    """Filter out verbose HTTP logs from third-party libraries."""
    # Filter httpx/httpcore INFO logs but keep WARNING/ERROR

    if record["name"].startswith(("httpx", "httpcore", "hpack")):
        return record["level"].no >= 30  # Only WARNING and above
    return True


def setup_logger(log_level: str | None = None, log_file: str | None = None) -> None:
    """Setup logger."""
    if log_level is None:
        console_level = os.getenv("LOG_LEVEL", "INFO")
    else:
        console_level = log_level

    env_log_file = os.getenv("LOG_FILE")
    error_log_file = os.getenv("ERROR_LOG_FILE")
    if log_file is None:
        log_file = env_log_file

    logger.remove()
    logger.configure(extra={"module": "app"})

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[module]: <25}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[module]: <25} | {name}:{function}:{line} - {message}"
    )

    # Console handler - level from env
    logger.add(
        sys.stderr,
        format=console_format,
        level=console_level,
        colorize=True,
        filter=http_filter,  # Filter out verbose HTTP logs
    )

    # File handler - INFO level only
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            format=file_format,
            level="INFO",
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            filter=http_filter,  # Filter out verbose HTTP logs
        )

    if error_log_file:
        err_path = Path(error_log_file)
        err_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            error_log_file,
            format=file_format,
            level="ERROR",
            rotation="10 MB",
            retention="14 days",
            compression="zip",
        )

    # Suppress noisy third-party loggers at stdlib logging level (httpx uses standard logging, not loguru)
    # (httpx uses standard logging, not loguru)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(module_name: str | None = None):
    """Get configured logger."""
    if module_name:
        return logger.bind(module=module_name)
    return logger


def format_log(message: str, **details: Any) -> str:
    """Format unified log message text."""
    if not details:
        return message
    serialized_details: list[str] = []
    for key, value in details.items():
        serialized_details.append(f"{key}={value}")
    return f"{message} | " + " | ".join(serialized_details)


def short_task_id(task_id: str) -> str:
    """
    Get short task ID (first 8 characters) for logging.
    Full task_id can be recovered from Celery logs if needed.

    Args:
        task_id: Full UUID task ID

    Returns:
        First 8 characters of task_id
    """
    return task_id[:8] if task_id else "unknown"


def short_user_id(user_id: str) -> str:
    """
    Get short user ID (first 8 characters) for logging.

    Args:
        user_id: Full ULID user ID

    Returns:
        First 8 characters of user_id
    """
    return user_id[:8] if user_id else "unknown"


def format_task_context(
    task_id: str | None = None,
    recording_id: int | None = None,
    user_id: str | None = None,
    platform: str | None = None,
    **extra,
) -> str:
    """
    Format unified task context with | separators for better readability.

    Args:
        task_id: Task UUID (will be shortened)
        recording_id: Recording ID
        user_id: User ULID (will be shortened)
        platform: Platform name (youtube, vk, etc.)
        **extra: Additional context fields

    Returns:
        Formatted context string like: "Task:abc12345 | Rec:123 | User:01KFHA26"
    """
    parts = []

    if task_id:
        parts.append(f"Task:{short_task_id(task_id)}")
    if recording_id is not None:
        parts.append(f"Rec:{recording_id}")
    if user_id:
        parts.append(f"User:{short_user_id(user_id)}")
    if platform:
        parts.append(f"Platform:{platform}")

    # Add extra fields
    for key, value in extra.items():
        parts.append(f"{key}:{value}")

    return " | ".join(parts) if parts else ""


setup_logger()
