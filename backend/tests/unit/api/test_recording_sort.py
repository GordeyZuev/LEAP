"""Recording list sort fields."""

import pytest
from sqlalchemy.dialects import postgresql

from api.repositories.recording_repos import _recording_order_clause


@pytest.mark.unit
def test_view_count_sort_maps_to_share_counter_with_stable_tie_break():
    primary, tie = _recording_order_clause("view_count", "desc")
    dialect = postgresql.dialect()
    assert str(primary.compile(dialect=dialect)) == "recordings.share_view_count DESC NULLS LAST"
    assert str(tie.compile(dialect=dialect)) == "recordings.id DESC"


@pytest.mark.unit
def test_unknown_sort_falls_back_to_start_time():
    primary, _tie = _recording_order_clause("bogus", "asc")
    assert str(primary.compile(dialect=postgresql.dialect())) == "recordings.start_time ASC NULLS LAST"
