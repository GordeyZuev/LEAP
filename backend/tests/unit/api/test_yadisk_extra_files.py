"""_upload_extra_files_to_yadisk — best-effort sidecar uploads (mocked client / storage)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.tasks.upload import _upload_extra_files_to_yadisk


@pytest.mark.unit
class TestYandexDiskExtraFiles:
    @pytest.mark.asyncio
    async def test_skips_when_no_oauth_token(self) -> None:
        await _upload_extra_files_to_yadisk(
            None,
            recording_id=1,
            user_slug=1,
            video_folder_path="/Video",
            video_base_name="lec",
            preset_metadata={"subtitles_srt": {}},
            template_context={},
            rendered_description="",
        )

    @pytest.mark.asyncio
    async def test_description_txt_calls_upload(self) -> None:
        """description_txt is rendered inline (not from storage) so the flow only
        needs the YaDisk client mock; the storage backend is never touched."""
        mock_client_inst = MagicMock()
        mock_client_inst.upload_file = AsyncMock(return_value=True)
        mock_tm = MagicMock()

        with (
            patch("yandex_disk_module.client.YandexDiskClient", return_value=mock_client_inst),
            patch("transcription_module.manager.get_transcription_manager", return_value=mock_tm),
        ):
            await _upload_extra_files_to_yadisk(
                "oauth-test",
                recording_id=1,
                user_slug=1,
                video_folder_path="/Video",
                video_base_name="lec",
                preset_metadata={"description_txt": {}},
                template_context={},
                rendered_description="body text",
                overwrite=True,
            )

        mock_client_inst.upload_file.assert_called_once()
        call = mock_client_inst.upload_file.call_args
        assert call.kwargs["disk_path"] == "/Video/lec_description.txt"
        # The NamedTemporaryFile is unlinked in the finally block.
        local_path = call.args[0]
        assert local_path.exists() is False

    @pytest.mark.asyncio
    async def test_subtitles_srt_downloads_from_storage_and_uploads(self) -> None:
        """generate_subtitles returns a storage key; the helper must materialize it
        to a temp file before handing it to YaDisk, then clean up."""
        mock_client_inst = MagicMock()
        mock_client_inst.upload_file = AsyncMock(return_value=True)

        mock_tm = MagicMock()
        mock_tm.generate_subtitles = AsyncMock(
            return_value={"srt": "users/000002/recordings/7/transcriptions/cache/subtitles.srt"}
        )

        # Storage stub: download_to_file writes a placeholder, exists/save not used here.
        async def _fake_download_to_file(key: str, local: Path) -> None:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

        mock_storage = MagicMock()
        mock_storage.download_to_file = AsyncMock(side_effect=_fake_download_to_file)

        with (
            patch("yandex_disk_module.client.YandexDiskClient", return_value=mock_client_inst),
            patch("transcription_module.manager.get_transcription_manager", return_value=mock_tm),
            patch("file_storage.factory.get_storage_backend", return_value=mock_storage),
        ):
            await _upload_extra_files_to_yadisk(
                "oauth-test",
                recording_id=7,
                user_slug=2,
                video_folder_path="/Out",
                video_base_name="v",
                preset_metadata={"subtitles_srt": {}},
                template_context={},
                rendered_description="",
            )

        mock_tm.generate_subtitles.assert_awaited_once_with(7, ["srt"], 2)
        mock_storage.download_to_file.assert_awaited_once()
        mock_client_inst.upload_file.assert_awaited_once()
        assert mock_client_inst.upload_file.call_args.kwargs["disk_path"] == "/Out/v.srt"

        # The temp file used for the upload must be cleaned up.
        local_path = mock_client_inst.upload_file.call_args.args[0]
        assert local_path.exists() is False
