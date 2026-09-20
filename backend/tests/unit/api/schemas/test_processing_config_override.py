"""Typed processing overrides reject FFmpeg filter injection."""

import pytest
from pydantic import ValidationError

from api.schemas.recording.request import ConfigOverrideRequest
from video_processing_module.audio_detector import AudioDetector


@pytest.mark.unit
class TestProcessingConfigOverride:
    def test_rejects_filter_injection_in_silence_duration(self) -> None:
        with pytest.raises(ValidationError):
            ConfigOverrideRequest.model_validate(
                {
                    "processing_config": {
                        "trimming": {
                            "min_silence_duration": "1,movie=http://169.254.169.254/",
                        }
                    }
                }
            )

    def test_accepts_numeric_trimming(self) -> None:
        req = ConfigOverrideRequest.model_validate(
            {"processing_config": {"trimming": {"min_silence_duration": 1.5, "silence_threshold": -35}}}
        )
        assert req.processing_config is not None
        assert req.processing_config["trimming"]["min_silence_duration"] == 1.5

    def test_drops_unknown_ffmpeg_keys(self) -> None:
        req = ConfigOverrideRequest.model_validate(
            {
                "processing_config": {
                    "ffmpeg_af": "movie=http://169.254.169.254/",
                    "trimming": {"min_silence_duration": 1.0},
                }
            }
        )
        assert req.processing_config is not None
        assert "ffmpeg_af" not in req.processing_config


@pytest.mark.unit
class TestAudioDetectorFilter:
    def test_filter_is_numeric_only(self) -> None:
        detector = AudioDetector(silence_threshold=-40.0, min_silence_duration=2.0)
        assert detector._silence_detect_filter() == "silencedetect=noise=-40.0dB:d=2.000"

    def test_rejects_comma_string(self) -> None:
        with pytest.raises(ValueError, match=r"finite|could not convert"):
            AudioDetector(min_silence_duration="1,movie=http://169.254.169.254/")  # type: ignore[arg-type]
