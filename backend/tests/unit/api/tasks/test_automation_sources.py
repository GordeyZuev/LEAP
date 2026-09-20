from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.tasks.automation import _sources_for_templates


def _source(*, source_id, source_type, credential_id=None, config=None, is_active=True):
    return SimpleNamespace(
        id=source_id,
        source_type=source_type,
        credential_id=credential_id,
        config=config,
        is_active=is_active,
    )


def _template(*source_ids):
    rules = {"source_ids": list(source_ids)} if source_ids else {}
    return SimpleNamespace(matching_rules=rules)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_job_syncs_mts_and_public_disk_without_a_disk_credential(mocker):
    mts = _source(source_id=1, source_type="MTS_LINK", credential_id=5)
    public = _source(
        source_id=2,
        source_type="YANDEX_DISK",
        config={"public_url": "https://disk.yandex.ru/d/shared"},
    )
    private = _source(source_id=3, source_type="YANDEX_DISK", config={"folder_path": "/lectures"})
    by_id = {1: mts, 2: public, 3: private}
    repo = mocker.patch("api.tasks.automation.InputSourceRepository").return_value
    repo.find_by_id = AsyncMock(side_effect=lambda source_id, _user_id: by_id[source_id])

    sources = await _sources_for_templates(
        AsyncMock(),
        [_template(1), _template(2), _template(3)],
        "user",
    )

    assert [source.id for source in sources] == [1, 2]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unscoped_templates_include_public_links_and_skip_private_disk(mocker):
    mts = _source(source_id=1, source_type="MTS_LINK", credential_id=5)
    public = _source(
        source_id=2,
        source_type="YANDEX_DISK",
        config={"public_url": "https://disk.yandex.ru/d/shared"},
    )
    video = _source(source_id=4, source_type="VIDEO_URL", config={"url": "https://youtu.be/abc"})
    private = _source(source_id=3, source_type="YANDEX_DISK", config={"folder_path": "/lectures"})
    local = _source(source_id=5, source_type="LOCAL")
    inactive = _source(
        source_id=6,
        source_type="YANDEX_DISK",
        config={"public_url": "https://disk.yandex.ru/d/off"},
        is_active=False,
    )
    repo = mocker.patch("api.tasks.automation.InputSourceRepository").return_value
    repo.find_active_by_user = AsyncMock(return_value=[mts, public, video, private, local, inactive])

    sources = await _sources_for_templates(AsyncMock(), [_template()], "user")

    assert [source.id for source in sources] == [1, 2, 4]
