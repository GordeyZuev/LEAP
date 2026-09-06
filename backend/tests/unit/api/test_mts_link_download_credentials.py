"""MTS Link download wiring: credential resolution and needs_reauth on a dead key."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.mts_link_api import MtsLinkAuthenticationError
from api.tasks.processing import _mts_link_download_options


def _recording(input_source_id: int | None = 7):
    return SimpleNamespace(
        id=42,
        source=SimpleNamespace(input_source_id=input_source_id, meta={}),
    )


def _source(credential_id: int | None = 3, config: dict | None = None):
    return SimpleNamespace(credential_id=credential_id, config=config)


@pytest.mark.unit
class TestMtsLinkDownloadOptions:
    @pytest.mark.asyncio
    async def test_returns_credential_id_and_source_settings(self):
        source = _source(config={"conversion_quality": "1080", "fetch_chat": False})
        credential = SimpleNamespace(id=3, encrypted_data="enc")

        with (
            patch("api.repositories.template_repos.InputSourceRepository") as source_repo,
            patch("api.repositories.auth_repos.UserCredentialRepository") as cred_repo,
            patch("api.auth.encryption.get_encryption") as encryption,
        ):
            source_repo.return_value.find_by_id = AsyncMock(return_value=source)
            cred_repo.return_value.get_by_id = AsyncMock(return_value=credential)
            encryption.return_value.decrypt_credentials.return_value = {
                "auth_type": "api_key",
                "api_token": "org-key-value",
            }

            credential_id, kwargs = await _mts_link_download_options(None, _recording(), "user-1")

        assert credential_id == 3
        assert kwargs["api_token"] == "org-key-value"
        assert kwargs["conversion_quality"] == "1080"
        assert kwargs["fetch_chat"] is False
        # Unset keys fall back to the same defaults as the source schema.
        assert kwargs["conversion_view"] == "none"
        assert kwargs["fetch_session_files"] is True

    @pytest.mark.asyncio
    async def test_recording_without_input_source_is_rejected(self):
        with pytest.raises(ValueError, match="no input source"):
            await _mts_link_download_options(None, _recording(input_source_id=None), "user-1")

    @pytest.mark.asyncio
    async def test_source_without_credential_is_rejected(self):
        with patch("api.repositories.template_repos.InputSourceRepository") as source_repo:
            source_repo.return_value.find_by_id = AsyncMock(return_value=_source(credential_id=None))

            with pytest.raises(ValueError, match="no credential"):
                await _mts_link_download_options(None, _recording(), "user-1")


@pytest.mark.unit
class TestDeadKeyFlagsCredential:
    @pytest.mark.asyncio
    async def test_auth_error_marks_credential_for_reauth(self):
        """A revoked org key must surface as "Re-auth needed", not as a mystery failure."""
        from api.tasks import processing

        cred_repo = AsyncMock()
        downloader = AsyncMock()
        downloader.download.side_effect = MtsLinkAuthenticationError("Authentication failed (401)")

        recording = SimpleNamespace(
            id=42,
            status="INITIALIZED",
            download_started_at=None,
            source=SimpleNamespace(input_source_id=7, meta={}),
        )

        with (
            patch.object(processing, "create_downloader", return_value=downloader),
            patch.object(
                processing,
                "_mts_link_download_options",
                new=AsyncMock(return_value=(3, {"api_token": "dead-key"})),
            ),
            patch("api.repositories.auth_repos.UserCredentialRepository", return_value=cred_repo),
            pytest.raises(MtsLinkAuthenticationError),
        ):
            await processing._download_via_external(
                task_self=AsyncMock(),
                session=AsyncMock(),
                recording=recording,
                recording_repo=AsyncMock(),
                user_id="user-1",
                user_slug=1,
                storage_builder=None,
                source_type="MTS_LINK",
                force=False,
            )

        cred_repo.set_needs_reauth.assert_awaited_once_with(3, True)

    @pytest.mark.asyncio
    async def test_pending_conversion_returns_awaiting_without_raising(self):
        from api.tasks import processing
        from video_download_module.platforms.mtslink.downloader import MtsLinkConversionPendingError

        downloader = AsyncMock()
        downloader.download.side_effect = MtsLinkConversionPendingError("still converting")
        recording = SimpleNamespace(
            id=42,
            status="INITIALIZED",
            download_started_at=None,
            on_air=True,
            pipeline_task_id="abc",
            source=SimpleNamespace(input_source_id=7, meta={}),
        )
        recording_repo = AsyncMock()

        with (
            patch.object(processing, "create_downloader", return_value=downloader),
            patch.object(
                processing,
                "_mts_link_download_options",
                new=AsyncMock(return_value=(3, {"api_token": "ok"})),
            ),
            patch("api.services.mts_link_prepare.apply_prepare_result"),
        ):
            result = await processing._download_via_external(
                task_self=AsyncMock(),
                session=AsyncMock(),
                recording=recording,
                recording_repo=recording_repo,
                user_id="user-1",
                user_slug=1,
                storage_builder=None,
                source_type="MTS_LINK",
                force=False,
            )

        assert result["status"] == "awaiting_mts"
        assert result["success"] is True
        assert recording.on_air is False
        assert recording.pipeline_task_id is None


@pytest.mark.unit
def test_waiting_for_external_source_statuses():
    from types import SimpleNamespace

    from api.tasks.processing import _waiting_for_external_source
    from models import ProcessingStatus

    assert _waiting_for_external_source(SimpleNamespace(status=ProcessingStatus.PENDING_CONVERSION))
    assert _waiting_for_external_source(SimpleNamespace(status=ProcessingStatus.PENDING_SOURCE))
    assert not _waiting_for_external_source(SimpleNamespace(status=ProcessingStatus.DOWNLOADED))


@pytest.mark.unit
def test_run_download_recording_treats_pending_as_success():
    from unittest.mock import Mock

    from api.tasks.processing import _run_download_recording
    from video_download_module.platforms.mtslink.downloader import MtsLinkConversionPendingError

    task = SimpleNamespace(run_async=Mock(side_effect=MtsLinkConversionPendingError("wait")))
    result = _run_download_recording(task, 1, "user-1", False, None)
    assert result["status"] == "awaiting_mts"
    assert result["success"] is True
