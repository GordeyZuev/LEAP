"""Unit tests for template JSON bundle normalization and validation."""

import pytest

from api.schemas.template.bundle import RecordingTemplateReplace
from api.schemas.template.matching_rules import MatchingRules
from api.services.template_bundle_service import (
    TemplateBundleError,
    normalize_raw_to_bundle_dict,
)


@pytest.mark.unit
class TestNormalizeBundle:
    def test_strips_null_keys(self):
        raw = {
            "leap_template_bundle": 1,
            "templates": [
                {
                    "name": "Test Template",
                    "matching_rules": {"keywords": None, "exact_matches": ["A"]},
                    "is_draft": True,
                }
            ],
        }
        normalized = normalize_raw_to_bundle_dict(raw)
        rules = normalized["templates"][0]["matching_rules"]
        assert "keywords" not in rules
        assert rules["exact_matches"] == ["A"]

    def test_wraps_single_template_object(self):
        raw = {"name": "Solo", "is_draft": True}
        normalized = normalize_raw_to_bundle_dict(raw)
        assert normalized["leap_template_bundle"] == 1
        assert len(normalized["templates"]) == 1
        assert normalized["templates"][0]["name"] == "Solo"

    def test_rejects_legacy_title_placeholder(self):
        raw = {
            "templates": [
                {
                    "name": "Bad Title",
                    "metadata_config": {"title_template": "X | {themes} ({record_time:DD.MM.YY})"},
                }
            ]
        }
        with pytest.raises(TemplateBundleError, match="legacy single-brace"):
            normalize_raw_to_bundle_dict(raw)


@pytest.mark.unit
class TestRecordingTemplateReplace:
    def test_non_draft_allows_empty_matching(self):
        replace = RecordingTemplateReplace(
            name="Tmpl One",
            description=None,
            is_draft=False,
            is_active=True,
            matching_rules=None,
            processing_config=None,
            metadata_config=None,
            output_config=None,
        )
        replace.validate_business_rules(is_default=False)
        warnings = replace.warnings(is_default=False)
        assert any(code == "empty_matching_rules" for code, _ in warnings)

    def test_default_allows_null_matching(self):
        replace = RecordingTemplateReplace(
            name="Default",
            description=None,
            is_draft=False,
            is_active=True,
            matching_rules=None,
            processing_config=None,
            metadata_config=None,
            output_config=None,
        )
        replace.validate_business_rules(is_default=True)
        assert replace.warnings(is_default=True) == []

    def test_source_ids_only_passes_validator(self):
        replace = RecordingTemplateReplace(
            name="Tmpl Two",
            description=None,
            is_draft=False,
            is_active=True,
            matching_rules=MatchingRules(source_ids=[1]),
            processing_config=None,
            metadata_config=None,
            output_config=None,
        )
        replace.validate_business_rules(is_default=False)
        warnings = replace.warnings()
        assert any(code == "source_ids_without_positive_rule" for code, _ in warnings)
