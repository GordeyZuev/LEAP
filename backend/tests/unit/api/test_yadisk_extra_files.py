"""_upload_extra_files_to_yadisk — best-effort sidecar uploads (mocked client / transcription)."""

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
        local_path = call.args[0]
        assert local_path.exists() is False

    @pytest.mark.asyncio
    async def test_subtitles_srt_uses_generated_path(self, tmp_path: Path) -> None:
        srt_file = tmp_path / "subtitles.srt"
        srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

        mock_client_inst = MagicMock()
        mock_client_inst.upload_file = AsyncMock(return_value=True)
        mock_tm = MagicMock()
        mock_tm.generate_subtitles = MagicMock(return_value={"srt": str(srt_file)})

        with (
            patch("yandex_disk_module.client.YandexDiskClient", return_value=mock_client_inst),
            patch("transcription_module.manager.get_transcription_manager", return_value=mock_tm),
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

        mock_tm.generate_subtitles.assert_called_once_with(7, ["srt"], 2)
        mock_client_inst.upload_file.assert_called_once()
        assert mock_client_inst.upload_file.call_args.kwargs["disk_path"] == "/Out/v.srt"
