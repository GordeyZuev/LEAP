"""Unit tests for AudioDetector module."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
class TestAudioDetector:
    """Tests for AudioDetector class."""

    def test_audio_detector_init(self):
        """Test AudioDetector initialization with config."""
        # Arrange & Act
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector(silence_threshold=-40.0, min_silence_duration=2.0)

        # Assert
        assert detector.silence_threshold == -40.0
        assert detector.min_silence_duration == 2.0

    def test_audio_detector_default_values(self):
        """Test AudioDetector with default values."""
        # Arrange & Act
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()

        # Assert
        assert detector.silence_threshold is not None
        assert detector.min_silence_duration is not None

    @pytest.mark.skip(reason="AudioDetector doesn't have detect_silence_periods method")
    @pytest.mark.asyncio
    async def test_detect_silence_periods_success(self):
        """Test successful silence detection."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector(silence_threshold=-40.0, min_silence_duration=1.0)
        audio_path = "/path/to/audio.mp3"

        # Mock ffmpeg silence detection output
        mock_output = """
        [silencedetect @ 0x123] silence_start: 10.5
        [silencedetect @ 0x123] silence_end: 15.2 | silence_duration: 4.7
        [silencedetect @ 0x123] silence_start: 30.0
        [silencedetect @ 0x123] silence_end: 35.5 | silence_duration: 5.5
        """

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", mock_output.encode()))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            silence_periods = await detector.detect_silence_periods(audio_path)

            # Assert
            assert len(silence_periods) == 2
            assert silence_periods[0]["start"] == 10.5
            assert silence_periods[0]["end"] == 15.2
            assert silence_periods[1]["start"] == 30.0
            assert silence_periods[1]["end"] == 35.5

    @pytest.mark.asyncio
    async def test_detect_audio_boundaries_no_silence(self):
        """Test when no silence is detected."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()
        audio_path = "/path/to/audio.mp3"

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"No silence detected"))
        mock_process.returncode = 0

        with patch("pathlib.Path.exists", return_value=True):
            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                # Act
                first_sound, last_sound = await detector.detect_audio_boundaries_from_file(audio_path)

                # Assert
                assert first_sound == 0.0
                assert last_sound is None

    @pytest.mark.asyncio
    async def test_detect_audio_boundaries_ffmpeg_error(self):
        """Test handling of ffmpeg errors."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()
        audio_path = "/path/to/invalid_audio.mp3"

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error: Invalid audio file"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            first_sound, last_sound = await detector.detect_audio_boundaries_from_file(audio_path)

            # Assert - returns None, None on error
            assert first_sound is None
            assert last_sound is None

    @pytest.mark.asyncio
    async def test_detect_audio_boundaries_file_not_found(self):
        """Test when audio file doesn't exist."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()
        audio_path = "/path/to/nonexistent.mp3"

        with patch("pathlib.Path.exists", return_value=False):
            # Act
            first_sound, last_sound = await detector.detect_audio_boundaries_from_file(audio_path)

            # Assert
            assert first_sound is None
            assert last_sound is None

    @pytest.mark.asyncio
    async def test_detect_audio_boundaries_custom_threshold(self):
        """Test audio boundary detection with custom threshold."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector(silence_threshold=-30.0, min_silence_duration=0.5)
        audio_path = "/path/to/audio.mp3"

        mock_stderr = b"[silencedetect @ 0x123] silence_start: 0.0\n[silencedetect @ 0x123] silence_end: 5.0"

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", mock_stderr))
        mock_process.returncode = 0

        with patch("pathlib.Path.exists", return_value=True):
            with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
                with patch.object(detector, "_get_duration", return_value=60.0):
                    # Act
                    await detector.detect_audio_boundaries_from_file(audio_path)

                    # Assert
                    # Verify ffmpeg was called with correct threshold
                    mock_exec.assert_called_once()
                    call_args = mock_exec.call_args[0]
                    # Should include silencedetect filter with -30dB threshold
                    assert any("noise=-30" in str(arg) for arg in call_args)


@pytest.mark.unit
class TestAudioDetectorHelpers:
    """Tests for AudioDetector helper methods."""

    def test_parse_silence_detection(self):
        """Test parsing of ffmpeg silence detection output."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()
        ffmpeg_output = """
        [silencedetect @ 0x123] silence_start: 10.5
        [silencedetect @ 0x123] silence_end: 15.2 | silence_duration: 4.7
        [silencedetect @ 0x123] silence_start: 30.0
        [silencedetect @ 0x123] silence_end: 35.0 | silence_duration: 5.0
        """

        # Act
        periods = detector._parse_silence_detection(ffmpeg_output)

        # Assert
        assert len(periods) == 2
        assert periods[0] == (10.5, 15.2)
        assert periods[1] == (30.0, 35.0)

    def test_find_first_sound(self):
        """Test finding when first sound starts."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()

        # Case 1: Silence at start
        silence_periods = [(0.0, 2.5), (10.0, 15.0)]
        result = detector._find_first_sound(silence_periods)
        assert result == 2.5

        # Case 2: Sound starts immediately
        silence_periods = [(5.0, 10.0)]
        result = detector._find_first_sound(silence_periods)
        assert result == 0.0

        # Case 3: No silence
        silence_periods = []
        result = detector._find_first_sound(silence_periods)
        assert result == 0.0

    def test_find_last_sound(self):
        """Test finding when last sound ends."""
        # Arrange
        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()
        duration = 120.0

        # Case 1: Silence at end
        silence_periods = [(5.0, 10.0), (115.0, 120.0)]
        result = detector._find_last_sound(silence_periods, duration)
        assert result == 115.0

        # Case 2: Sound continues to end
        silence_periods = [(5.0, 10.0)]
        result = detector._find_last_sound(silence_periods, duration)
        assert result == duration

        # Case 3: No duration provided
        silence_periods = [(5.0, 10.0)]
        result = detector._find_last_sound(silence_periods, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_duration(self):
        """Test getting media file duration."""
        # Arrange
        import json

        from video_processing_module.audio_detector import AudioDetector

        detector = AudioDetector()
        file_path = "/path/to/audio.mp3"

        mock_ffprobe_output = {"format": {"duration": "120.5"}}

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(json.dumps(mock_ffprobe_output).encode(), b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            duration = await detector._get_duration(file_path)

            # Assert
            assert duration == 120.5
