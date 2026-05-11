"""Custom Jinja filters split_path and part on SandboxedEnvironment."""

import pytest

from api.helpers.template_renderer import build_stub_validation_context, render_jinja


@pytest.mark.unit
class TestSplitPathPartFilters:
    def test_split_path_default_sep(self) -> None:
        assert render_jinja("{{ name | split_path('_') }}", {"name": "A_B_C"}) == "A/B/C"

    def test_split_path_custom_sep(self) -> None:
        assert render_jinja("{{ name | split_path('-') }}", {"name": "a-b-c"}) == "a/b/c"

    def test_part_first_segment(self) -> None:
        assert render_jinja("{{ name | part(0, '_') }}", {"name": "A_B_C"}) == "A"

    def test_part_out_of_range_empty(self) -> None:
        assert render_jinja("{{ name | part(5, '_') }}", {"name": "A_B"}) == ""

    def test_folder_path_with_split_path_stub_context(self) -> None:
        ctx = build_stub_validation_context()
        ctx["display_name"] = "Course_Lecture_01"
        out = render_jinja("/Video/{{ display_name | split_path('_') }}", ctx)
        assert out == "/Video/Course/Lecture/01"
