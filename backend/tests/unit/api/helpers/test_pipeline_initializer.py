"""ensure_output_targets skips leap look presets (unknown TargetType)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.helpers.pipeline_initializer import ensure_output_targets


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_output_targets_skips_leap_preset() -> None:
    session = MagicMock()
    result = MagicMock()
    leap = SimpleNamespace(id=1, platform="leap", is_active=True)
    result.scalars.return_value.all.return_value = [leap]
    session.execute = AsyncMock(return_value=result)

    recording = SimpleNamespace(id=9, user_id="u1", outputs=[])
    created = await ensure_output_targets(session, recording, {"preset_ids": [1]})
    assert created == []
    session.add.assert_not_called()
