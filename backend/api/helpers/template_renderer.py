"""Jinja2-based template rendering for upload metadata and validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jinja2 import ChainableUndefined, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from logger import get_logger

logger = get_logger(__name__)

# Human-readable datetime/date for preset context keys (user-local wall time after astimezone).
_DATETIME_DISPLAY_SPEC: Final[str] = "DD.MM.YYYY hh:mm"
_DATE_DISPLAY_SPEC: Final[str] = "DD.MM.YYYY"
_DATE_SHORT_SPEC: Final[str] = "DD.MM.YY"
_TIMESTAMP_LOCAL_SPEC: Final[str] = "%Y-%m-%dT%H:%M:%S"

# At least one of these must appear as a Jinja variable in title_template (first identifier after {{).
TITLE_TEMPLATE_VARIABLE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "display_name",
        "themes",
        "topic",
        "record_time",
        "publish_time",
        "duration",
        "summary",
        "topics",
        "questions",
        "record_date",
        "publish_date",
        "record_datetime",
        "publish_datetime",
        "record_date_iso",
        "publish_date_iso",
        "record_date_short",
        "publish_date_short",
        "record_time_hm",
        "publish_time_hm",
        "record_datetime_iso",
        "publish_datetime_iso",
        "record_timestamp_local",
        "publish_timestamp_local",
        "recording_id",
        "duration_hm",
        "title",
        "date",
        "original_title",
    }
)

# Keys included in stub context for compile+render validation (types must satisfy template usage).
_STUB_DATETIME: Final[datetime] = datetime(2026, 6, 15, 14, 30, 0, tzinfo=UTC)

_JINJA_VAR_START: Final[re.Pattern[str]] = re.compile(
    r"\{\{[-+\s]*([a-zA-Z_][a-zA-Z0-9_]*)",
)


def _format_list_style_field(raw: Any, default: str = "numbered_list") -> str:
    """Normalize Pydantic enum or other values to str keys for format_map."""
    if raw is None:
        return default
    value = raw.value if hasattr(raw, "value") else raw
    return value if isinstance(value, str) else str(value)


def format_datetime_for_template(dt: datetime, format_spec: str) -> str:
    """Format a timezone-aware datetime for preset/title strings (call after astimezone)."""
    if not isinstance(format_spec, str):
        format_spec = str(format_spec)
    if format_spec == "date":
        return dt.strftime("%Y-%m-%d")
    if format_spec == "time":
        return dt.strftime("%H:%M")
    if format_spec == "datetime":
        return dt.strftime("%Y-%m-%d %H:%M")

    replacements = {
        "YYYY": dt.strftime("%Y"),
        "YY": dt.strftime("%y"),
        "MM": dt.strftime("%m"),
        "DD": dt.strftime("%d"),
        "hh": dt.strftime("%H"),
        "mm": dt.strftime("%M"),
        "ss": dt.strftime("%S"),
    }

    # Iterate (token, repl) by descending token length so longer tokens (e.g. YYYY) replace first.
    result: str = format_spec
    for token, repl in sorted(replacements.items(), key=lambda kv: len(kv[0]), reverse=True):
        result = result.replace(token, repl)

    return result


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _zoneinfo_for_owner(owner: Any) -> ZoneInfo:
    """Resolve IANA timezone from recording owner; invalid or missing → UTC with one warning."""
    raw = ""
    if owner is not None:
        raw = (getattr(owner, "timezone", None) or "").strip()
    if not raw:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError, OSError, TypeError):
        logger.warning("Invalid user timezone {!r}, using UTC", raw)
        return ZoneInfo("UTC")


class SilentUndefined(ChainableUndefined):
    """Undefined that stringifies to empty (optional fields in user templates)."""

    __slots__ = ()

    def __str__(self) -> str:
        return ""

    def __html__(self) -> str:
        return ""


def _jinja_split_path(value: object, separator: str = "_") -> str:
    """Replace separator with / for path-like folder segments (e.g. A_B_C -> A/B/C)."""
    return str(value).replace(separator, "/")


def _jinja_part(value: object, index: int = 0, separator: str = "_") -> str:
    """Return segment index after splitting by separator; empty string if out of range."""
    parts = str(value).split(separator)
    return parts[index] if index < len(parts) else ""


def _get_sandboxed_env() -> SandboxedEnvironment:
    env = SandboxedEnvironment(
        undefined=SilentUndefined,
        autoescape=False,
        enable_async=False,
    )
    env.filters["split_path"] = _jinja_split_path
    env.filters["part"] = _jinja_part
    return env


def render_jinja(template: str, context: Mapping[str, Any]) -> str:
    """
    Render a Jinja2 template string with the given context (sandboxed).

    Args:
        template: Jinja source (e.g. "{{ display_name }}").
        context: Mapping of names to values (str, numbers, etc.).

    Returns:
        Rendered string; empty if template is empty.
    """
    if not template or not template.strip():
        return ""
    env = _get_sandboxed_env()
    try:
        jinja_template = env.from_string(template)
        return jinja_template.render(**dict(context))
    except Exception as exc:
        logger.debug("Jinja render failed: {}", type(exc).__name__)
        raise


def build_stub_validation_context() -> dict[str, Any]:
    """Build a context for dry-run validation (deterministic UTC wall times, all string dates)."""
    stub_ts = _STUB_DATETIME.strftime(_TIMESTAMP_LOCAL_SPEC)
    ctx: dict[str, Any] = {
        "display_name": "Stub Recording",
        "duration": 3600.0,
        "duration_hm": "1:00:00",
        "record_time": stub_ts,
        "publish_time": stub_ts,
        "record_timestamp_local": stub_ts,
        "publish_timestamp_local": stub_ts,
        "summary": "Stub summary text.",
        "themes": "theme_a, theme_b",
        "topics": "1. Topic one\n2. Topic two",
        "questions": "1. Question one?",
        "record_date": "15.06.2026",
        "publish_date": "15.06.2026",
        "record_datetime": "15.06.2026 14:30",
        "publish_datetime": "15.06.2026 14:30",
        "record_date_iso": "2026-06-15",
        "publish_date_iso": "2026-06-15",
        "record_date_short": "15.06.26",
        "publish_date_short": "15.06.26",
        "record_time_hm": "14:30",
        "publish_time_hm": "14:30",
        "record_datetime_iso": "2026-06-15 14:30",
        "publish_datetime_iso": "2026-06-15 14:30",
        "recording_id": "0",
        "title": "Stub Title",
        "topic": "stub_topic",
        "date": "15.06.2026",
        "original_title": "Stub Original Title",
    }
    return ctx


def validate_jinja_template(
    source: str | None,
    *,
    optional: bool = True,
    dry_run_render: bool = True,
) -> str | None:
    """
    Validate Jinja syntax and optionally dry-run render with stub context.

    Args:
        source: Template string or None.
        optional: If True, None/blank becomes None; if False, blank raises.
        dry_run_render: If True, render with stub context to catch runtime errors.

    Returns:
        Stripped template, or None if optional and empty.

    Raises:
        ValueError: Invalid template or empty when not optional.
    """
    if source is None or not str(source).strip():
        if optional:
            return None
        raise ValueError("Template is required")
    text = str(source).strip()
    env = _get_sandboxed_env()
    try:
        env.from_string(text)
    except TemplateSyntaxError as exc:
        raise ValueError(f"Invalid template syntax: {exc.message}") from exc
    if dry_run_render:
        try:
            render_jinja(text, build_stub_validation_context())
        except Exception as exc:
            raise ValueError(f"Template failed render (dry-run): {exc}") from exc
    return text


def assert_title_template_has_substitution(template: str) -> None:
    """
    Ensure title template is not a plain constant: at least one whitelisted variable is used.

    Raises:
        ValueError: If no allowed variable appears as the first identifier in a {{ ... }} expression.
    """
    if not template or not template.strip():
        raise ValueError("title_template is required")
    found: set[str] = set(_JINJA_VAR_START.findall(template))
    if not found.intersection(TITLE_TEMPLATE_VARIABLE_NAMES):
        raise ValueError(
            f"title_template must use at least one variable from: {', '.join(sorted(TITLE_TEMPLATE_VARIABLE_NAMES))}"
        )


def compute_metadata_preview(
    *,
    title_template: str | None,
    description_template: str | None,
    folder_path_template: str | None,
    filename_template: str | None,
    context: Mapping[str, Any],
) -> tuple[bool, list[str], list[str], dict[str, str | None]]:
    """
    Dry-run render for preview API. Collects errors and optional warnings (e.g. empty title).

    Returns:
        (valid, errors, warnings, rendered) where rendered keys: title, description, folder_path, filename.
    """
    errors: list[str] = []
    warnings: list[str] = []
    rendered: dict[str, str | None] = {}
    try:
        if title_template and description_template:
            t, d = render_upload_title_and_description(title_template, description_template, context)
            rendered["title"] = t
            rendered["description"] = d
        else:
            if title_template:
                rendered["title"] = render_jinja(title_template, context)
            if description_template:
                rendered["description"] = render_jinja(description_template, context)
        if folder_path_template:
            rendered["folder_path"] = render_jinja(folder_path_template, context)
        if filename_template:
            rendered["filename"] = render_jinja(filename_template, context)
    except Exception as exc:
        errors.append(str(exc))
        return False, errors, warnings, rendered
    if rendered.get("title") == "":
        warnings.append("Rendered title is empty")
    return True, [], warnings, rendered


def render_upload_title_and_description(
    title_template: str,
    description_template: str,
    context: Mapping[str, Any],
) -> tuple[str, str]:
    """
    Render title then description so description may reference {{ title }}.

    Args:
        title_template: Jinja title string.
        description_template: Jinja description string.
        context: Recording context (must not include title unless intentional).

    Returns:
        (rendered_title, rendered_description)
    """
    ctx = dict(context)
    title = render_jinja(title_template, ctx)
    ctx["title"] = title
    description = render_jinja(description_template, ctx)
    return title, description


class TemplateRenderer:
    """Upload metadata: Jinja rendering and recording context preparation."""

    @staticmethod
    def render(template: str, context: Mapping[str, Any]) -> str:
        """Render Jinja template (backward-compatible name for callers)."""
        return render_jinja(template, context)

    @staticmethod
    def _format_topics_list(
        topics: Sequence[Any],
        config: Mapping[str, Any],
    ) -> str:
        cfg: dict[str, Any] = dict(config)

        if not cfg.get("enabled", True) or not topics:
            return ""

        # Preset metadata uses `show_timestamps`; user config TopicsDisplay uses `include_timestamps`.
        show_timestamps = bool(
            cfg["show_timestamps"] if "show_timestamps" in cfg else cfg.get("include_timestamps", True)
        )

        normalized_topics = [
            item if isinstance(item, dict) else {"topic": str(item), "start": None, "end": None} for item in topics
        ]

        min_length = cfg.get("min_length") or 0
        max_length = cfg.get("max_length") or 999

        filtered_topics = [t for t in normalized_topics if min_length <= len(str(t.get("topic", ""))) <= max_length]

        max_count = cfg.get("max_count") or 999
        if max_count > 0:
            filtered_topics = filtered_topics[:max_count]

        if not filtered_topics:
            return ""

        format_type = _format_list_style_field(cfg.get("format", "numbered_list"))
        separator = str(cfg.get("separator", "\n"))

        def format_topic_item(topic_dict: dict[str, Any]) -> str:
            topic_text = topic_dict.get("topic", "")
            start = topic_dict.get("start")

            if show_timestamps and start is not None:
                try:
                    sec = float(start)
                except (TypeError, ValueError):
                    return topic_text
                timestamp = TemplateRenderer._format_seconds_to_timestamp(sec)
                return f"{timestamp} — {topic_text}"
            return topic_text

        format_map = {
            "numbered_list": lambda: separator.join(
                f"{i + 1}. {format_topic_item(t)}" for i, t in enumerate(filtered_topics)
            ),
            "bullet_list": lambda: separator.join(f"• {format_topic_item(t)}" for t in filtered_topics),
            "dash_list": lambda: separator.join(f"- {format_topic_item(t)}" for t in filtered_topics),
            "comma_separated": lambda: ", ".join(format_topic_item(t) for t in filtered_topics),
            "inline": lambda: " | ".join(format_topic_item(t) for t in filtered_topics),
        }

        formatted = format_map.get(format_type, format_map["numbered_list"])()

        prefix = cfg.get("prefix", "")
        if prefix:
            formatted = f"{prefix}{separator}{formatted}"

        return formatted

    @staticmethod
    def _format_questions_list(questions: list[str], config: Mapping[str, Any]) -> str:
        cfg: dict[str, Any] = dict(config)

        if not cfg.get("enabled", False) or not questions:
            return ""
        if not isinstance(questions, list):
            return ""

        min_length = cfg.get("min_length") or 0
        max_length = cfg.get("max_length") or 1000

        filtered = [q.strip() for q in questions if q and min_length <= len(q.strip()) <= max_length]

        max_count = cfg.get("max_count") or 20
        if max_count > 0:
            filtered = filtered[:max_count]

        if not filtered:
            return ""

        format_type = _format_list_style_field(cfg.get("format", "numbered_list"))
        separator = str(cfg.get("separator", "\n"))

        format_map = {
            "numbered_list": lambda: separator.join(f"{i + 1}. {q}" for i, q in enumerate(filtered)),
            "bullet_list": lambda: separator.join(f"• {q}" for q in filtered),
            "dash_list": lambda: separator.join(f"- {q}" for q in filtered),
            "comma_separated": lambda: ", ".join(filtered),
            "inline": lambda: " | ".join(filtered),
            "plain": lambda: separator.join(filtered),
        }

        formatted = format_map.get(format_type, format_map["numbered_list"])()

        prefix = cfg.get("prefix", "")
        if prefix:
            formatted = f"{prefix}{separator}{formatted}"

        return formatted

    @staticmethod
    def _format_seconds_to_timestamp(seconds: float | int) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _duration_hm_str(duration: Any) -> str:
        if duration is None or duration == "":
            return ""
        try:
            sec = float(duration)
        except (TypeError, ValueError):
            return ""
        if sec < 0:
            return ""
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @staticmethod
    def prepare_recording_context(
        recording: Any,
        topics_display: Mapping[str, Any] | None = None,
        questions_display: Mapping[str, Any] | None = None,
        extracted_data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build Jinja context from a recording model.

        Datetimes are converted to the recording owner's IANA timezone (``users.timezone``), then
        exposed as **strings** only (``record_date``, ``record_date_iso``, ``record_timestamp_local``,
        etc.). ``record_time`` / ``publish_time`` are aliases of the ``*_timestamp_local`` strings.
        """
        display_name = recording.display_name or "Recording"
        _raw_duration = getattr(recording, "duration", None)
        # Avoid `0.0 or ""` — zero seconds is a valid duration.
        duration_val: Any = "" if _raw_duration is None else _raw_duration

        owner = getattr(recording, "owner", None)
        zone = _zoneinfo_for_owner(owner)

        record_src = recording.start_time if getattr(recording, "start_time", None) else None
        publish_src = datetime.now(UTC)
        record_utc = _to_utc(record_src) if record_src is not None else None
        publish_utc = _to_utc(publish_src)
        record_local = record_utc.astimezone(zone) if record_utc is not None else None
        publish_local = publish_utc.astimezone(zone)

        rl = record_local if record_local is not None else publish_local
        record_ts = record_local.strftime(_TIMESTAMP_LOCAL_SPEC) if record_local is not None else ""
        publish_ts = publish_local.strftime(_TIMESTAMP_LOCAL_SPEC)

        context: dict[str, Any] = {
            "display_name": display_name,
            "duration": duration_val,
            "record_time": record_ts,
            "publish_time": publish_ts,
            "record_timestamp_local": record_ts,
            "publish_timestamp_local": publish_ts,
            "duration_hm": TemplateRenderer._duration_hm_str(duration_val),
            "recording_id": str(getattr(recording, "id", "") or ""),
        }

        context["record_date"] = format_datetime_for_template(rl, _DATE_DISPLAY_SPEC) if rl else ""
        context["publish_date"] = format_datetime_for_template(publish_local, _DATE_DISPLAY_SPEC)
        context["record_datetime"] = format_datetime_for_template(rl, _DATETIME_DISPLAY_SPEC) if rl else ""
        context["publish_datetime"] = format_datetime_for_template(publish_local, _DATETIME_DISPLAY_SPEC)
        context["record_date_iso"] = format_datetime_for_template(rl, "date") if rl else ""
        context["publish_date_iso"] = format_datetime_for_template(publish_local, "date")
        context["record_date_short"] = format_datetime_for_template(rl, _DATE_SHORT_SPEC) if rl else ""
        context["publish_date_short"] = format_datetime_for_template(publish_local, _DATE_SHORT_SPEC)
        context["record_time_hm"] = format_datetime_for_template(rl, "time") if rl else ""
        context["publish_time_hm"] = format_datetime_for_template(publish_local, "time")
        context["record_datetime_iso"] = format_datetime_for_template(rl, "datetime") if rl else ""
        context["publish_datetime_iso"] = format_datetime_for_template(publish_local, "datetime")

        # ``extracted_data`` (active version dict from extracted.json) must be loaded
        # by the async caller and passed in. We cannot call the (now async)
        # TranscriptionManager from this sync helper. If not provided, fields default
        # to empty — callers that need them must fetch the data upstream.
        summary = ""
        questions: list[str] = []
        if extracted_data:
            summary = (extracted_data.get("summary") or "").strip()
            raw_q = extracted_data.get("questions") or []
            questions = raw_q if isinstance(raw_q, list) else []
        context["summary"] = summary or ""

        if questions_display and questions_display.get("enabled"):
            context["questions"] = TemplateRenderer._format_questions_list(questions, dict(questions_display))
        else:
            context["questions"] = ""

        main_topics = getattr(recording, "main_topics", None)
        if main_topics:
            if isinstance(main_topics, (list, tuple)):
                context["themes"] = ", ".join(str(x) for x in main_topics[:3])
            else:
                context["themes"] = str(main_topics)
        else:
            context["themes"] = ""

        topics_for_description: list[Any] = []
        tts = getattr(recording, "topic_timestamps", None)
        if tts and isinstance(tts, (list, tuple)):
            topics_for_description = list(tts)
        elif main_topics and isinstance(main_topics, (list, tuple)):
            topics_for_description = list(main_topics)

        if topics_for_description:
            if topics_display:
                context["topics"] = TemplateRenderer._format_topics_list(topics_for_description, dict(topics_display))
            elif topics_for_description and isinstance(topics_for_description[0], dict):
                context["topics"] = "\n".join(
                    f"{i + 1}. {item.get('topic', '')}" for i, item in enumerate(topics_for_description[:10])
                )
            else:
                context["topics"] = "\n".join(
                    f"{i + 1}. {topic}" for i, topic in enumerate(topics_for_description[:10])
                )
        else:
            context["topics"] = ""

        context["topic"] = context["themes"]
        context["date"] = context["record_date"]
        # Alias for video-mapping style templates; no separate DB field — same as display name.
        context["original_title"] = display_name

        return context
