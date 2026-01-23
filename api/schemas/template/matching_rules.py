"""Typed schemas for template matching_rules"""

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG
from api.schemas.common.validators import clean_and_deduplicate_strings, validate_regex_patterns

# ============================================================================
# Matching Rules
# ============================================================================


class MatchingRules(BaseModel):
    """
    Recording to template matching rules.

    Supports positive and negative matching:
    - exact_matches: exact name match
    - keywords: keyword search
    - patterns: regex patterns
    - source_ids: bind to specific input sources
    - exclude_keywords: exclude records with these words
    - exclude_patterns: exclude records matching regex patterns
    """

    model_config = BASE_MODEL_CONFIG

    # Exact matches
    exact_matches: list[str] | None = Field(
        None,
        description="List of exact matches",
        examples=[["Машинное обучение - лекция 1", "ML Lecture 1"]],
    )

    # Keywords (OR logic)
    keywords: list[str] | None = Field(
        None,
        description="Keywords for search (OR). By default case-insensitive (see case_sensitive)",
        examples=[["генеративные модели", "deep learning", "нейронные сети"]],
    )

    # Regex patterns (OR logic)
    patterns: list[str] | None = Field(
        None,
        description="Regex patterns for matching (OR)",
        examples=[
            ["^Лекция \\d+", "Временные ряды.*\\d{2}\\.\\d{2}"],
            ["ML-\\d{4}-\\d{2}-\\d{2}"],
        ],
    )

    # Bind to sources
    source_ids: list[int] | None = Field(
        None,
        description="Source IDs (input_sources). Only for records from these sources",
        examples=[[1, 2, 3]],
    )

    # Exclude rules (negative matching)
    exclude_keywords: list[str] | None = Field(
        None,
        description="Exclude records containing these words (simple substring search)",
        examples=[["тест", "черновик", "draft"], ["temp", "backup"]],
    )

    exclude_patterns: list[str] | None = Field(
        None,
        description="Exclude records matching regex patterns",
        examples=[[".*_temp$", ".*test.*"], ["^Draft_.*", ".*\\(копия\\).*"]],
    )

    # Case sensitivity
    case_sensitive: bool = Field(
        False, description="Consider case for exact_matches, keywords, exclude_keywords, patterns, exclude_patterns"
    )

    @field_validator("exact_matches")
    @classmethod
    def validate_exact_matches(cls, v: list[str] | None) -> list[str] | None:
        return clean_and_deduplicate_strings(v)

    @field_validator("keywords", mode="before")
    @classmethod
    def clean_keywords(cls, v: list[str] | None) -> list[str] | None:
        """Clean and deduplicate keywords."""
        return clean_and_deduplicate_strings(v)

    @field_validator("patterns")
    @classmethod
    def validate_patterns(cls, v: list[str] | None) -> list[str] | None:
        """Validate regex patterns."""
        return validate_regex_patterns(v, field_name="patterns")

    @field_validator("source_ids")
    @classmethod
    def validate_source_ids(cls, v: list[int] | None) -> list[int] | None:
        """Validate source IDs."""
        if v is not None and len(v) == 0:
            return None
        return v

    @field_validator("exclude_keywords", mode="before")
    @classmethod
    def clean_exclude_keywords(cls, v: list[str] | None) -> list[str] | None:
        """Clean and deduplicate exclude keywords."""
        return clean_and_deduplicate_strings(v)

    @field_validator("exclude_patterns")
    @classmethod
    def validate_exclude_patterns(cls, v: list[str] | None) -> list[str] | None:
        """Validate exclude regex patterns."""
        return validate_regex_patterns(v, field_name="exclude_patterns")
