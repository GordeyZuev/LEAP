"""In-memory list sort used by sources, jobs, credentials, playlists, presets."""

from types import SimpleNamespace

import pytest

from api.schemas.common.pagination import paginate_list


@pytest.mark.unit
def test_null_sort_values_come_last_in_both_directions():
    items = [
        SimpleNamespace(last_sync_at=None, name="empty"),
        SimpleNamespace(last_sync_at=2, name="late"),
        SimpleNamespace(last_sync_at=1, name="early"),
    ]

    asc, _, _ = paginate_list(list(items), 1, 20, "last_sync_at", "asc")
    assert [i.name for i in asc] == ["early", "late", "empty"]

    desc, _, _ = paginate_list(list(items), 1, 20, "last_sync_at", "desc")
    assert [i.name for i in desc] == ["late", "early", "empty"]
