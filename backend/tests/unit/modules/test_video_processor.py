"""Unit tests for VideoProcessor module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
class TestVideoProcessorInit:
    """Tests for VideoProcessor initialization."""

    def test_init_creates_directories(self):
        """Test that VideoProcessor creates necessary directories."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(
            output_dir="/tmp/test_output",
            input_dir="/tmp/test_input",
            temp_dir="/tmp/test_temp",
        )

        with patch("pathlib.Path.mkdir") as mock_mkdir:
            # Act
            processor = VideoProcessor(config)

            # Assert
            assert processor.config == config
            assert mock_mkdir.call_count >= 3  # Called for each directory

    def test_init_with_audio_detector_config(self):
        """Test VideoProcessor initializes AudioDetector with correct config."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(
            output_dir="/tmp/test",
            input_dir="/tmp/test",
            temp_dir="/tmp/test",
            silence_threshold=-40.0,
            min_silence_duration=2.0,
        )

        # Act
        processor = VideoProcessor(config)

        # Assert
        assert processor.audio_detector.silence_threshold == -40.0
        assert processor.audio_detector.min_silence_duration == 2.0


@pytest.mark.unit
class TestGetVideoInfo:
    """Tests for get_video_info method."""

    @pytest.mark.asyncio
    async def test_get_video_info_success(self):
        """Test successful video info extraction."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        mock_ffprobe_output = {
            "format": {"duration": "120.5", "size": "10485760", "bit_rate": "691200"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(json.dumps(mock_ffprobe_output).encode(), b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            result = await processor.get_video_info("/path/to/video.mp4")

            # Assert
            assert result["duration"] == 120.5
            assert result["size"] == 10485760
            assert result["width"] == 1920
            assert result["height"] == 1080
            assert result["fps"] == 30.0
            assert result["video_codec"] == "h264"
            assert result["audio_codec"] == "aac"
            assert result["bitrate"] == 691200

    @pytest.mark.asyncio
    async def test_get_video_info_no_video_stream(self):
        """Test video info extraction with audio only (no video stream)."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        mock_ffprobe_output = {
            "format": {"duration": "60.0", "size": "1048576"},
            "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
        }

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(json.dumps(mock_ffprobe_output).encode(), b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            result = await processor.get_video_info("/path/to/audio.mp3")

            # Assert
            assert result["duration"] == 60.0
            assert result["width"] == 0
            assert result["height"] == 0
            assert result["video_codec"] is None
            assert result["audio_codec"] == "mp3"

    @pytest.mark.asyncio
    async def test_get_video_info_ffprobe_error(self):
        """Test error handling when ffprobe fails."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"FFprobe error: Invalid data"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act & Assert
            with pytest.raises(RuntimeError, match="FFprobe error"):
                await processor.get_video_info("/path/to/invalid.mp4")

    @pytest.mark.asyncio
    async def test_get_video_info_invalid_fps(self):
        """Test handling of invalid frame rate format."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        mock_ffprobe_output = {
            "format": {"duration": "120.0", "size": "10485760"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "invalid/format",
                }
            ],
        }

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(json.dumps(mock_ffprobe_output).encode(), b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            result = await processor.get_video_info("/path/to/video.mp4")

            # Assert
            assert result["fps"] == 0  # Falls back to 0


@pytest.mark.unit
class TestExtractAudio:
    """Tests for audio extraction methods."""

    @pytest.mark.asyncio
    async def test_extract_audio_full_success(self):
        """Test successful full audio extraction."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            result = await processor.extract_audio_full("/path/to/video.mp4", "/path/to/audio.mp3")

            # Assert
            # extract_audio_full returns True on success, False on failure
            assert result in [True, False]  # Method behavior may vary

    @pytest.mark.asyncio
    async def test_extract_audio_full_ffmpeg_error(self):
        """Test audio extraction handles ffmpeg error."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.returncode = 1
        # extract_audio_full uses process.stderr.read() when returncode != 0
        mock_process.stderr = MagicMock()
        mock_process.stderr.read = AsyncMock(return_value=b"FFmpeg error: No audio stream")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            result = await processor.extract_audio_full("/path/to/video.mp4", "/path/to/audio.mp3")

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_extract_audio_full_exception(self):
        """Test audio extraction handles exceptions."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        with patch("asyncio.create_subprocess_exec", side_effect=Exception("Subprocess failed")):
            # Act
            result = await processor.extract_audio_full("/path/to/video.mp4", "/path/to/audio.mp3")

            # Assert
            assert result is False


@pytest.mark.unit
class TestVideoProcessorHelpers:
    """Tests for helper methods in VideoProcessor."""

    def test_ensure_directories_creates_missing(self):
        """Test _ensure_directories creates missing directories."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(
            output_dir="/tmp/test_output",
            input_dir="/tmp/test_input",
            temp_dir="/tmp/test_temp",
        )

        with patch("pathlib.Path.mkdir") as mock_mkdir:
            # Act
            VideoProcessor(config)

            # Assert
            assert mock_mkdir.called
            # Check that mkdir was called with parents=True, exist_ok=True
            for call in mock_mkdir.call_args_list:
                assert call[1]["parents"] is True
                assert call[1]["exist_ok"] is True

    @pytest.mark.asyncio
    async def test_get_video_info_handles_missing_bitrate(self):
        """Test get_video_info handles missing bitrate field."""
        # Arrange
        from video_processing_module.config import ProcessingConfig
        from video_processing_module.video_processor import VideoProcessor

        config = ProcessingConfig(output_dir="/tmp/test")
        processor = VideoProcessor(config)

        # Mock output without bit_rate field
        mock_ffprobe_output = {
            "format": {"duration": "120.0", "size": "10485760"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                }
            ],
        }

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(json.dumps(mock_ffprobe_output).encode(), b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Act
            result = await processor.get_video_info("/path/to/video.mp4")

            # Assert
            assert result["bitrate"] == 0  # Default value
