"""Shared recording-template business validation (create, replace, import)."""

from __future__ import annotations

from api.schemas.template.matching_rules import MatchingRules
from api.schemas.template.metadata_config import TemplateMetadataConfig
from api.schemas.template.output_config import TemplateOutputConfig
from api.schemas.template.processing_config import TemplateProcessingConfig


def matching_rules_has_content(matching_rules: MatchingRules | None) -> bool:
    """True when any positive matching field is non-empty (same notion as the form editor)."""
    if matching_rules is None:
        return False
    rules = matching_rules
    return bool(
        (rules.exact_matches and len(rules.exact_matches) > 0)
        or (rules.keywords and len(rules.keywords) > 0)
        or (rules.patterns and len(rules.patterns) > 0)
        or (rules.source_ids and len(rules.source_ids) > 0)
    )


def validate_template_state(
    *,
    is_default: bool,
    matching_rules: MatchingRules | None,
    processing_config: TemplateProcessingConfig | None,
    metadata_config: TemplateMetadataConfig | None,
    output_config: TemplateOutputConfig | None,
) -> None:
    """Cross-field rules shared by create, full replace, and import."""
    if is_default:
        if matching_rules_has_content(matching_rules):
            raise ValueError("Default template cannot have matching rules")
        return

    # Named templates may keep matching_rules null/empty (same as PATCH from the form UI).
    # Auto-assignment simply does nothing until rules are added; validate warns instead.

    if output_config and output_config.auto_upload:
        if not processing_config:
            raise ValueError("auto_upload=True requires processing_config")

    if metadata_config and metadata_config.title_template:
        if not output_config:
            raise ValueError("title_template requires output_config with preset_ids")


def collect_template_warnings(
    matching_rules: MatchingRules | None,
    *,
    is_draft: bool = False,
    is_default: bool = False,
) -> list[tuple[str, str]]:
    """Non-fatal import/validate warnings (code, message)."""
    warnings: list[tuple[str, str]] = []
    if not is_default and not is_draft and not matching_rules_has_content(matching_rules):
        warnings.append(
            (
                "empty_matching_rules",
                "Active named template has no matching rules; new recordings will not auto-link to it",
            )
        )
    if not matching_rules:
        return warnings
    has_positive = bool(
        (matching_rules.exact_matches and len(matching_rules.exact_matches) > 0)
        or (matching_rules.keywords and len(matching_rules.keywords) > 0)
        or (matching_rules.patterns and len(matching_rules.patterns) > 0)
    )
    has_source = bool(matching_rules.source_ids and len(matching_rules.source_ids) > 0)
    if has_source and not has_positive:
        warnings.append(
            (
                "source_ids_without_positive_rule",
                "source_ids alone does not match recordings at runtime; add keywords, patterns, or exact_matches",
            )
        )
    return warnings
