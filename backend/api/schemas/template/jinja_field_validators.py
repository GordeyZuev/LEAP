"""Shared Pydantic validators for Jinja2 metadata templates."""

from __future__ import annotations

from api.helpers.template_renderer import assert_title_template_has_substitution, validate_jinja_template


def validate_optional_jinja(value: str | None) -> str | None:
    """Compile + dry-run optional template fields (description, paths, etc.)."""
    return validate_jinja_template(value, optional=True)


def validate_optional_jinja_title(value: str | None) -> str | None:
    """Optional title template: Jinja valid + at least one whitelisted variable when set."""
    validated = validate_jinja_template(value, optional=True)
    if validated:
        assert_title_template_has_substitution(validated)
    return validated


def validate_required_jinja(value: str) -> str:
    """Required template string (e.g. Yandex folder path)."""
    out = validate_jinja_template(value, optional=False)
    if out is None:
        raise ValueError("Template is required")
    return out


def validate_required_jinja_title(value: str) -> str:
    """Required title template with substitution rule."""
    out = validate_jinja_template(value, optional=False)
    if out is None:
        raise ValueError("title_template is required")
    assert_title_template_has_substitution(out)
    return out
