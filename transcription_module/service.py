"""Transcription and topic extraction service"""

import time
from pathlib import Path
from typing import Any

from deepseek_module import DeepSeekConfig, TopicExtractor
from fireworks_module import FireworksConfig, FireworksTranscriptionService
from logger import get_logger
from utils.audio_compressor import AudioCompressor

logger = get_logger()


class TranscriptionService:
    """Main service for transcription and text processing"""

    def __init__(
        self,
        deepseek_config: DeepSeekConfig | None = None,
        fireworks_config: FireworksConfig | None = None,
    ):
        if deepseek_config is None:
            deepseek_config = DeepSeekConfig.from_file()

        self.deepseek_config = deepseek_config

        if fireworks_config is None:
            fireworks_config = FireworksConfig.from_file()

        self.fireworks_config = fireworks_config

        self.fireworks_service = FireworksTranscriptionService(self.fireworks_config)
        self.topic_extractor = TopicExtractor(self.deepseek_config)

        target_bitrate = self.fireworks_config.audio_bitrate
        target_sample_rate = self.fireworks_config.audio_sample_rate
        max_file_size_mb = self.fireworks_config.max_file_size_mb

        self.audio_compressor = AudioCompressor(
            target_bitrate=target_bitrate,
            target_sample_rate=target_sample_rate,
            max_file_size_mb=max_file_size_mb,
        )

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """
        Formatting time in seconds to format HH:MM:SS
        """
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _format_timestamp_with_ms(seconds: float) -> str:
        """
        Formatting time in seconds to format HH:MM:SS.mmm
        """
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        milliseconds = int((seconds - total_seconds) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"

    async def process_audio(
        self,
        audio_path: str,
        user_id: int,
        recording_id: int | None = None,
        recording_topic: str | None = None,
        recording_start_time: str | None = None,
        granularity: str = "long",  # "short" | "long"
    ) -> dict[str, Any]:
        """
        Full audio processing: compression, transcription, topic extraction.

        Args:
            audio_path: Path to the audio file
            recording_id: Recording ID (for file naming)
            recording_topic: Recording topic (for file naming)
            granularity: Topic extraction mode: "short" or "long"

        Returns:
            Dictionary with results:
            {
                'transcription_dir': str,  # Path to the transcription folder
                'transcription_text': str,
                'topic_timestamps': list,
                'main_topics': list,
            }
        """
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info(
            f"Starting audio processing: file={audio_path} | model=Fireworks",
            file=audio_path,
            model="Fireworks"
        )

        fireworks_prompt = self.fireworks_service.compose_fireworks_prompt(self.fireworks_config.prompt, recording_topic)

        prepared_audio, temp_files_to_cleanup = await self._prepare_audio(audio_path)
        transcription_language = self.fireworks_config.language

        try:
            logger.info("Transcribing audio via Fireworks API...")
            transcription_result = await self.fireworks_service.transcribe_audio(
                audio_path=prepared_audio,
                language=transcription_language,
                prompt=fireworks_prompt,
            )

            transcription_text = transcription_result["text"]
            segments = transcription_result.get("segments", [])
            segments_auto = transcription_result.get("segments_auto", [])
            words = transcription_result.get("words", [])
            srt_content = transcription_result.get("srt_content")  # Original SRT from Fireworks
            transcription_language = transcription_result.get("language", "ru")

            logger.info(
                f"Transcription completed: chars={len(transcription_text)} | segments={len(segments)} | words={len(words)}",
                chars=len(transcription_text),
                segments=len(segments),
                words=len(words)
            )

            transcription_dir = self._save_transcription(
                transcription_text,
                segments,
                words=words,
                segments_auto=segments_auto,
                srt_content=srt_content,
                user_id=user_id,
                recording_id=recording_id,
                recording_topic=recording_topic,
                recording_start_time=recording_start_time,
            )

            logger.info("Extracting topics via DeepSeek from file...")
            segments_file_path = Path(transcription_dir) / "segments.txt"
            topics_result = await self.topic_extractor.extract_topics_from_file(
                segments_file_path=str(segments_file_path),
                recording_topic=recording_topic,
                granularity=granularity,
            )

            logger.info("Topic extraction completed")

            # Convert pauses to timestamp format
            topic_timestamps = topics_result.get("topic_timestamps", [])
            long_pauses = topics_result.get("long_pauses", [])

            existing_pause_starts = set()
            for ts in topic_timestamps:
                topic = ts.get("topic", "").strip()
                if topic.lower() in ["перерыв", "pause", "break"]:
                    existing_pause_starts.add(ts.get("start", 0))

            pause_timestamps = []
            for pause in long_pauses:
                pause_start = pause["start"]
                # Skip pauses already added by model (5 sec tolerance)
                if not any(abs(pause_start - existing_start) < 5.0 for existing_start in existing_pause_starts):
                    pause_timestamps.append(
                        {
                            "topic": "Перерыв",
                            "start": pause_start,
                            "end": pause["end"],
                            "type": "pause",
                            "duration_minutes": pause.get("duration_minutes", (pause["end"] - pause_start) / 60),
                        }
                    )

            # Combine topics and pauses, sort by start time
            all_timestamps = topic_timestamps + pause_timestamps
            all_timestamps.sort(key=lambda x: x.get("start", 0))

            # Form the result
            result = {
                "transcription_dir": transcription_dir,
                "transcription_text": transcription_text,
                "topic_timestamps": all_timestamps,
                "main_topics": topics_result.get("main_topics", []),
                "long_pauses": long_pauses,  # Save also original data about pauses
                "language": transcription_language,
                "fireworks_raw": transcription_result,
            }

            logger.info("Audio processing completed successfully")
            topics_count = len(topic_timestamps)
            pauses_count = len(long_pauses)
            logger.info(
                f"📊 Results: topics={topics_count} | main_topics={len(topics_result.get('main_topics', []))} | pauses={pauses_count}",
                topics=topics_count,
                main_topics=len(topics_result.get("main_topics", [])),
                pauses=pauses_count
            )

            return result

        finally:
            # Delete temporary files if they were created
            for temp_file in temp_files_to_cleanup:
                temp_file_path = Path(temp_file)
                if temp_file != audio_path and temp_file_path.exists():
                    try:
                        temp_file_path.unlink()
                        logger.debug(f"Deleted temporary file: file={temp_file}", file=temp_file)
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete temporary file: file={temp_file}",
                            file=temp_file,
                            error=str(e)
                        )

    async def _prepare_audio(self, audio_path: str) -> tuple[str, list[str]]:
        """
        Audio preparation: extraction from video if needed.
        Fireworks supports large files, so splitting is not needed.

        Args:
            audio_path: Path to the audio file

        Returns:
            Tuple: (path to the file, list of temporary files to delete)
        """
        file_size = Path(audio_path).stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        temp_files = []

        logger.info(
            f"Fireworks supports large files: size={file_size_mb:.2f}MB | splitting=not_needed",
            size_mb=file_size_mb
        )

        # Check if the file is a video (need to extract audio)
        is_video = audio_path.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"))
        if is_video:
            logger.info("Video file detected, extracting audio for Fireworks...")
            # Extract audio from video (but not split)
            compressed_path = await self.audio_compressor.compress_audio(audio_path)
            temp_files.append(compressed_path)
            return compressed_path, temp_files

        return audio_path, []

    def _save_transcription(
        self,
        transcription_text: str,
        segments: list[dict[str, Any]],
        words: list[dict[str, Any]] | None = None,
        segments_auto: list[dict[str, Any]] | None = None,
        srt_content: str | None = None,
        user_id: int | None = None,
        recording_id: int | None = None,
        _recording_topic: str | None = None,
        _recording_start_time: str | None = None,
    ) -> str:
        """
        Saving transcription to a folder with files.

        Folder structure:
        - media/user_{user_id}/transcriptions/{recording_id}/
          - words.txt (words with timestamps)
          - segments.txt (segments with timestamps)
          - subtitles.srt (subtitles SRT)
          - subtitles.vtt (subtitles VTT)

        Args:
            transcription_text: Full transcription text
            segments: List of segments with timestamps
            words: List of words with timestamps (required for subtitle generation)
            srt_content: Original SRT from Fireworks (optional)
            user_id: User ID (required for data isolation)
            recording_id: Recording ID
            recording_topic: Recording topic
            recording_start_time: Recording start time

        Returns:
            Relative path to the transcription folder
        """
        from utils.user_paths import get_path_manager

        if user_id is None:
            raise ValueError("user_id is required for transcription isolation")

        path_manager = get_path_manager()

        # Use recording_id to create a unique folder
        if recording_id is not None:
            transcription_folder = path_manager.get_transcription_dir(user_id, recording_id)
        else:
            # Fallback for cases without recording_id (e.g. tests)
            transcription_folder = path_manager.get_transcription_dir(user_id) / f"temp_{int(time.time())}"

        transcription_folder.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created transcription folder: path={transcription_folder}", path=str(transcription_folder))

        if words and len(words) > 0:
            words_file_path = transcription_folder / "words.txt"
            with words_file_path.open("w", encoding="utf-8") as f:
                logger.info(f"Saving transcription: words={len(words)} | with_timestamps=yes", words=len(words))

                for word_item in words:
                    start_time = word_item.get("start", 0) or 0.0
                    end_time = word_item.get("end", 0) or 0.0
                    word_text = word_item.get("word", "").strip()

                    if word_text:
                        start_formatted = self._format_timestamp_with_ms(start_time)
                        end_formatted = self._format_timestamp_with_ms(end_time)
                        f.write(f"[{start_formatted} - {end_formatted}] {word_text}\n")

            logger.info(
                f"Transcription (words) saved: path={words_file_path} | words={len(words)}",
                path=str(words_file_path),
                words=len(words)
            )
        else:
            logger.warning("Words not provided, subtitle generation may be impossible")

        def _write_segments_file(target_path: Path, segments_data: list[dict[str, Any]], label: str) -> None:
            with target_path.open("w", encoding="utf-8") as f:
                if segments_data and len(segments_data) > 0:
                    logger.info(
                        f"Saving transcription: segments={len(segments_data)} | source={label}",
                        segments=len(segments_data),
                        source=label
                    )

                    for seg in segments_data:
                        start_time = seg.get("start", 0) or 0.0
                        end_time = seg.get("end", 0) or 0.0
                        text = seg.get("text", "").strip()

                        if text:
                            start_formatted = self._format_timestamp_with_ms(start_time)
                            end_formatted = self._format_timestamp_with_ms(end_time)
                            # Protection from identical timestamps
                            if start_formatted == end_formatted:
                                end_time = float(end_time) + 0.001
                                end_formatted = self._format_timestamp_with_ms(end_time)
                            f.write(f"[{start_formatted} - {end_formatted}] {text}\n")
                else:
                    logger.warning(f"Segments ({label}) absent, saving only text")
                    f.write(transcription_text)

        # segments.txt — segments coming from Fireworks API (priority)
        segments_file_path = transcription_folder / "segments.txt"
        _write_segments_file(segments_file_path, segments, "Fireworks API")
        logger.info(
            f"Transcription saved: file=segments.txt | source=API | segments={len(segments) if segments else 0}",
            file=str(segments_file_path),
            segments=len(segments) if segments else 0
        )

        # segments_auto.txt — locally collected segments from words (for analysis/backup)
        if segments_auto is not None:
            segments_auto_path = transcription_folder / "segments_auto.txt"
            _write_segments_file(segments_auto_path, segments_auto, "local (auto)")
            logger.info(
                f"Transcription saved: file=segments_auto.txt | source=local | segments={len(segments_auto) if segments_auto else 0}",
                file=str(segments_auto_path),
                segments=len(segments_auto) if segments_auto else 0
            )

        if words and len(words) > 0:
            try:
                from subtitle_module import SubtitleGenerator

                generator = SubtitleGenerator()

                # Generate subtitles from segments.txt (already grouped segments)
                subtitle_source_path = str(segments_file_path)

                srt_target = transcription_folder / "subtitles.srt"
                vtt_target = transcription_folder / "subtitles.vtt"
                if srt_target.exists():
                    srt_target.unlink()
                if vtt_target.exists():
                    vtt_target.unlink()

                subtitle_result = generator.generate_from_transcription(
                    transcription_path=subtitle_source_path,
                    output_dir=str(transcription_folder),
                    formats=["srt", "vtt"],
                )

                if "srt" in subtitle_result:
                    srt_source = Path(subtitle_result["srt"])
                    if srt_source.exists() and srt_source != srt_target:
                        if srt_source.name != "subtitles.srt":
                            srt_source.rename(srt_target)
                        logger.info(f"Created SRT file: path={srt_target}", path=str(srt_target))
                    elif srt_source == srt_target:
                        logger.info(f"Created SRT file: path={srt_target}", path=str(srt_target))

                if "vtt" in subtitle_result:
                    vtt_source = Path(subtitle_result["vtt"])
                    if vtt_source.exists() and vtt_source != vtt_target:
                        if vtt_source.name != "subtitles.vtt":
                            vtt_source.rename(vtt_target)
                        logger.info(f"Created VTT file: path={vtt_target}", path=str(vtt_target))
                    elif vtt_source == vtt_target:
                        logger.info(f"Created VTT file: path={vtt_target}", path=str(vtt_target))
            except Exception as e:
                logger.warning(f"Failed to auto-create subtitles: error={e}", error=str(e))

        if srt_content:
            srt_backup_path = transcription_folder / "subtitles_fireworks_original.srt"
            with srt_backup_path.open("w", encoding="utf-8") as f:
                f.write(srt_content)
            logger.info(
                f"Original SRT backup saved: path={srt_backup_path}",
                path=str(srt_backup_path)
            )

        try:
            return str(transcription_folder.relative_to(Path.cwd()))
        except ValueError:
            logger.warning("Failed to get relative path for transcription, using absolute")
            return str(transcription_folder)
