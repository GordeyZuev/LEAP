"""ensure_output_targets creates leap targets."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.helpers.pipeline_initializer import ensure_output_targets
from models.recording import TargetType


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_output_targets_creates_leap_preset(mocker) -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    result = MagicMock()
    leap = SimpleNamespace(id=1, platform="leap", is_active=True)
    result.scalars.return_value.all.return_value = [leap]
    session.execute = AsyncMock(return_value=result)
    fake = SimpleNamespace(target_type=TargetType.LEAP)
    mocker.patch("api.helpers.pipeline_initializer.OutputTargetModel", return_value=fake)

    recording = SimpleNamespace(id=9, user_id="u1", outputs=[])
    created = await ensure_output_targets(session, recording, {"preset_ids": [1]}, include_copy=False)
    assert created == [fake]
    session.add.assert_called_once_with(fake)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_output_targets_skips_copy_when_include_copy_false() -> None:
    session = MagicMock()
    result = MagicMock()
    yt = SimpleNamespace(id=2, platform="youtube", is_active=True)
    result.scalars.return_value.all.return_value = [yt]
    session.execute = AsyncMock(return_value=result)

    recording = SimpleNamespace(id=9, user_id="u1", outputs=[])
    created = await ensure_output_targets(session, recording, {"preset_ids": [2]}, include_copy=False)
    assert created == []
    session.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_output_targets_skips_leap_when_publish_leap_false() -> None:
    session = MagicMock()
    result = MagicMock()
    leap = SimpleNamespace(id=1, platform="leap", is_active=True)
    result.scalars.return_value.all.return_value = [leap]
    session.execute = AsyncMock(return_value=result)

    recording = SimpleNamespace(id=9, user_id="u1", outputs=[])
    created = await ensure_output_targets(
        session,
        recording,
        {"preset_ids": [1], "publish_leap": False},
        include_copy=False,
    )
    assert created == []
    session.add.assert_not_called()
