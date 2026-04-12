"""Unit tests for Transcription Manager.

NOTE: TranscriptionManager is a file manager, not a transcription service.
It manages transcription files (master.json, extracted.json) but doesn't perform transcription.
Actual transcription is done by Celery tasks using Fireworks API.
"""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest


@pytest.mark.unit
class TestTranscriptionManager:
    """Tests for TranscriptionManager file management."""

    def test_get_dir(self):
        """Test getting transcription directory path."""
        # Arrange
        from transcription_module.manager import TranscriptionManager

        manager = TranscriptionManager()
        recording_id = 123
        user_slug = 456789

        # Act
        dir_path = manager.get_dir(recording_id, user_slug)

        # Assert
        assert dir_path is not None
        assert isinstance(dir_path, Path)
        assert "transcriptions" in str(dir_path)

    def test_get_dir_without_user_slug(self):
        """Test get_dir raises error when user_slug is None."""
        # Arrange
        from transcription_module.manager import TranscriptionManager

        manager = TranscriptionManager()

        # Act & Assert
        with pytest.raises(ValueError, match="user_slug is required"):
            manager.get_dir(123, None)

    @pytest.mark.parametrize(
        ("method", "exists"),
        [
            ("has_master", True),
            ("has_master", False),
            ("has_extracted", True),
            ("has_extracted", False),
        ],
    )
    def test_has_transcription_file(self, method, exists):
        """has_master / has_extracted reflect master.json / extracted.json existence."""
        from transcription_module.manager import TranscriptionManager

        manager = TranscriptionManager()

        with patch.object(Path, "exists", return_value=exists):
            assert getattr(manager, method)(123, 456789) is exists

    @pytest.mark.parametrize(
        ("words", "segments", "exp_w", "exp_s"),
        [
            ([{"word": "test", "start": 0.0, "end": 1.0}], [], 1, 0),
            ([], [{"text": "seg", "start": 0.0, "end": 1.0}], 0, 1),
            (
                [{"word": "a"}, {"word": "b"}],
                [{"text": "x"}],
                2,
                1,
            ),
        ],
    )
    def test_save_master_writes_stats_counts(self, words, segments, exp_w, exp_s):
        """save_master embeds words_count / segments_count in stats."""
        from transcription_module.manager import TranscriptionManager

        manager = TranscriptionManager()
        recording_id = 123
        user_slug = 456789

        with patch("file_storage.path_builder.StoragePathBuilder.transcription_dir") as mock_dir:
            mock_dir_path = MagicMock(spec=Path)
            mock_master_path = MagicMock(spec=Path)
            mock_dir_path.__truediv__ = MagicMock(return_value=mock_master_path)
            mock_dir.return_value = mock_dir_path

            mock_master_path.open = mock_open()

            with patch("json.dump") as mock_dump:
                manager.save_master(
                    recording_id=recording_id,
                    words=words,
                    segments=segments,
                    language="ru",
                    model="fireworks",
                    duration=120.0,
                    user_slug=user_slug,
                )

            mock_dump.assert_called_once()
            payload = mock_dump.call_args[0][0]
            assert payload["stats"]["words_count"] == exp_w
            assert payload["stats"]["segments_count"] == exp_s

    def test_load_master_success(self):
        """Test loading transcription from master.json."""
        # Arrange
        from transcription_module.manager import TranscriptionManager

        manager = TranscriptionManager()
        recording_id = 123
        user_slug = 456789

        mock_data = {
            "recording_id": recording_id,
            "words": [{"word": "test"}],
            "segments": [{"text": "test"}],
        }

        with patch("file_storage.path_builder.StoragePathBuilder.transcription_dir") as mock_dir:
            mock_path = MagicMock(spec=Path)
            mock_file_path = MagicMock(spec=Path)
            mock_file_path.exists.return_value = True
            mock_file_path.open = mock_open(read_data='{"recording_id": 123}')
            mock_path.__truediv__ = MagicMock(return_value=mock_file_path)
            mock_dir.return_value = mock_path

            with patch("json.load", return_value=mock_data):
                # Act
                result = manager.load_master(recording_id, user_slug)

                # Assert
                assert result["recording_id"] == recording_id
                assert "words" in result

    def test_load_master_file_not_found(self):
        """Test load_master raises error when file doesn't exist."""
        # Arrange
        from transcription_module.manager import TranscriptionManager

        manager = TranscriptionManager()

        with patch.object(Path, "exists", return_value=False):
            # Act & Assert
            with pytest.raises(FileNotFoundError):
                manager.load_master(123, 456789)
