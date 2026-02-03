"""Celery tasks for processing recordings with multi-tenancy support."""

import asyncio
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from celery import chain, group
from celery.exceptions import SoftTimeLimitExceeded

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.helpers.status_manager import update_aggregate_status
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import OutputPresetRepository
from api.services.config_utils import resolve_full_config
from api.tasks.base import ProcessingTask
from config.settings import get_settings
from deepseek_module import DeepSeekConfig, TopicExtractor
from file_storage.path_builder import StoragePathBuilder
from fireworks_module import FireworksConfig, FireworksTranscriptionService
from logger import get_logger
from models import MeetingRecording, ProcessingStageType, ProcessingStatus, recording as models
from models.recording import ProcessingStageStatus
from transcription_module.manager import TranscriptionManager, get_transcription_manager
from video_download_module.downloader import ZoomDownloader
from video_processing_module.config import ProcessingConfig
from video_processing_module.video_processor import VideoProcessor

logger = get_logger()
settings = get_settings()


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.download_recording",
    max_retries=settings.celery.download_max_retries,
    default_retry_delay=settings.celery.download_retry_delay,
)
def download_recording_task(
    self,
    recording_id: int,
    user_id: str,
    force: bool = False,
    manual_override: dict | None = None,
) -> dict:
    """
    Download recording from Zoom (template-driven).

    Args:
        recording_id: ID of recording
        user_id: ID of user
        force: Force download if already downloaded
        manual_override: Optional configuration override

    Returns:
        Result of download
    """
    try:
        logger.info(f"[Task {self.request.id}] Downloading recording {recording_id} for user {user_id}")

        self.update_progress(user_id=user_id, progress=10, status="Initializing download...", step="download")

        result = self.run_async(_async_download_recording(self, recording_id, user_id, force, manual_override))

        return self.build_result(
            user_id=user_id,
            status="completed",
            recording_id=recording_id,
            result=result,
        )

    except SoftTimeLimitExceeded:
        logger.error(f"[Task {self.request.id}] Soft time limit exceeded")
        raise self.retry(countdown=900, exc=SoftTimeLimitExceeded())

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error downloading: {exc!r}", exc_info=True)
        raise self.retry(exc=exc)


async def _refresh_download_token_if_needed(
    session,
    recording,
    user_id: str,
    meeting_id: str,
    force: bool,
    task_id: str,
) -> str | None:
    """
    Refresh download_access_token if needed (old/missing/force).

    Returns fresh token or None if refresh failed.
    """
    from api.auth.encryption import get_encryption
    from api.repositories.auth_repos import UserCredentialRepository
    from api.repositories.template_repos import InputSourceRepository
    from api.zoom_api import ZoomAPI
    from models.zoom_auth import create_zoom_credentials

    current_token = (
        recording.source.meta.get("download_access_token") if recording.source and recording.source.meta else None
    )

    token_age_days = None
    if recording.updated_at:
        token_age_days = (datetime.now(UTC) - recording.updated_at).days

    # Refresh if: old (>1 day), missing, or force
    if not (force or not current_token or (token_age_days and token_age_days > 1)):
        return current_token

    logger.info(
        f"[Task {task_id}] Refreshing download_access_token for recording {recording.id} "
        f"(age={token_age_days} days, force={force}, has_token={bool(current_token)})"
    )

    try:
        # Get input source
        if not recording.source or not recording.source.input_source_id:
            logger.warning(f"[Task {task_id}] No input source for recording {recording.id}")
            return current_token

        source_repo = InputSourceRepository(session)
        source = await source_repo.find_by_id(recording.source.input_source_id, user_id)

        if not source or not source.credential_id:
            logger.warning(f"[Task {task_id}] Source not found or no credential for recording {recording.id}")
            return current_token

        # Get credentials
        cred_repo = UserCredentialRepository(session)
        credential = await cred_repo.get_by_id(source.credential_id)

        if not credential:
            logger.warning(f"[Task {task_id}] Credential {source.credential_id} not found")
            return current_token

        # Decrypt credentials
        encryption = get_encryption()
        credentials_dict = encryption.decrypt_credentials(credential.encrypted_data)
        zoom_config = create_zoom_credentials(credentials_dict)
        zoom_api = ZoomAPI(zoom_config)

        # Get fresh token from Zoom API
        meeting_details = await zoom_api.get_recording_details(meeting_id, include_download_token=True)
        fresh_token = meeting_details.get("download_access_token")

        if fresh_token:
            logger.info(f"[Task {task_id}] Successfully refreshed download_access_token (length={len(fresh_token)})")

            # Update in source.meta for future use
            if recording.source and recording.source.meta:
                recording.source.meta["download_access_token"] = fresh_token
                recording.updated_at = datetime.now(UTC)
                await session.commit()

            return fresh_token

        logger.warning(f"[Task {task_id}] No fresh token received, using existing")
        return current_token

    except Exception as e:
        logger.warning(f"[Task {task_id}] Error refreshing token: {e}. Using existing")
        return current_token


async def _async_download_recording(
    task_self,
    recording_id: int,
    user_id: str,
    force: bool,
    manual_override: dict | None = None,
) -> dict:
    """Async function for downloading (template-driven)."""
    from api.helpers.failure_reset import reset_recording_failure, should_reset_on_retry

    async_session_maker = get_async_session_maker()
    async with async_session_maker() as session:
        # Resolve config
        full_config, recording = await resolve_full_config(session, recording_id, user_id, manual_override)

        recording_repo = RecordingRepository(session)

        # Reset failure flags if retrying after download failure
        if should_reset_on_retry(recording, "download"):
            reset_recording_failure(recording, "download")
            await recording_repo.update(recording)
            await session.commit()

        download_config = full_config.get("download", {})

        # Extract download parameters
        max_file_size_mb = download_config.get("max_file_size_mb", 5000)
        retry_attempts = download_config.get("retry_attempts", 3)

        logger.debug(
            f"Download config for recording {recording_id}: "
            f"max_file_size_mb={max_file_size_mb}, retry_attempts={retry_attempts}"
        )

        # Check download_url
        download_url = None
        if recording.source and recording.source.meta:
            download_url = recording.source.meta.get("download_url")

        if not download_url:
            raise ValueError("No download URL available. Please sync from Zoom first.")

        # Check if not already downloaded
        if not force and recording.status == ProcessingStatus.DOWNLOADED and recording.local_video_path:
            if Path(recording.local_video_path).exists():
                return {
                    "success": True,
                    "message": "Already downloaded",
                    "local_video_path": recording.local_video_path,
                }

        task_self.update_progress(
            user_id=user_id,
            progress=30,
            status="Downloading from Zoom...",
            step="download",
        )

        # Get user_slug for path generation
        user_slug = recording.owner.user_slug

        # Create downloader with StoragePathBuilder
        storage_builder = StoragePathBuilder()
        downloader = ZoomDownloader(user_slug=user_slug, storage_builder=storage_builder)

        # Convert to MeetingRecording
        meeting_id = recording.source.source_key if recording.source else str(recording.id)
        file_size = recording.source.meta.get("file_size", 0) if recording.source and recording.source.meta else 0
        passcode = (
            recording.source.meta.get("recording_play_passcode") if recording.source and recording.source.meta else None
        )
        password = recording.source.meta.get("password") if recording.source and recording.source.meta else None
        account = recording.source.meta.get("account") if recording.source and recording.source.meta else None

        # Refresh download_access_token if needed (for old/skipped recordings)
        download_access_token = await _refresh_download_token_if_needed(
            session, recording, user_id, meeting_id, force, task_self.request.id
        )

        meeting_recording = MeetingRecording(
            {
                "id": meeting_id,
                "uuid": meeting_id,
                "topic": recording.display_name,
                "start_time": recording.start_time.isoformat(),
                "duration": recording.duration or 0,
                "account": account or "default",
                "recording_files": [
                    {
                        "file_type": "MP4",
                        "file_size": file_size,
                        "download_url": download_url,
                        "recording_type": "shared_screen_with_speaker_view",
                        "download_access_token": download_access_token,
                    }
                ],
                "password": password,
                "recording_play_passcode": passcode,
            }
        )
        meeting_recording.db_id = recording.id

        task_self.update_progress(user_id, 40, "Starting download...", step="download")

        # Set DOWNLOADING status BEFORE actual download starts
        recording.status = ProcessingStatus.DOWNLOADING
        await recording_repo.update(recording)
        await session.commit()

        task_self.update_progress(user_id, 50, "Downloading video file...", step="download")

        # Download
        success = await downloader.download_recording(meeting_recording, force_download=force)

        if success:
            task_self.update_progress(user_id, 90, "Updating database...", step="download")

            recording.local_video_path = meeting_recording.local_video_path
            recording.status = ProcessingStatus.DOWNLOADED
            await recording_repo.update(recording)
            await session.commit()

            return {
                "success": True,
                "local_video_path": recording.local_video_path,
            }
        raise Exception("Download failed")


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.trim_video",
    max_retries=settings.celery.processing_max_retries,
    default_retry_delay=settings.celery.processing_retry_delay,
)
def trim_video_task(
    self,
    recording_id: int,
    user_id: str,
    manual_override: dict | None = None,
) -> dict:
    """
    Trim video - FFmpeg (silence removal, template-driven).

    Parameters are taken from resolved config (user_config < template < manual_override):
    - processing.silence_threshold
    - processing.min_silence_duration
    - processing.padding_before
    - processing.padding_after

    Args:
        recording_id: ID of recording
        user_id: ID of user
        manual_override: Optional configuration override

    Returns:
        Result of processing
    """
    try:
        logger.info(f"[Task {self.request.id}] Trimming video {recording_id} for user {user_id}")

        self.update_progress(user_id, 10, "Initializing video trimming...", step="trim")

        result = self.run_async(_async_process_video(self, recording_id, user_id, manual_override))

        return self.build_result(
            user_id=user_id,
            status="completed",
            recording_id=recording_id,
            result=result,
        )

    except SoftTimeLimitExceeded:
        logger.error(f"[Task {self.request.id}] Soft time limit exceeded")
        raise self.retry(countdown=600, exc=SoftTimeLimitExceeded())

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error processing: {exc!r}", exc_info=True)
        raise self.retry(exc=exc)


async def _async_process_video(
    task_self,
    recording_id: int,
    user_id: str,
    manual_override: dict | None = None,
) -> dict:
    """
    Async function for trimming video (template-driven).

    Optimized workflow:
    1. Extract full audio from original video (MP3)
    2. Analyze audio file for silence (faster than video analysis)
    3. Trim video based on detected boundaries
    4. Trim audio to match video (stream copy - instant)
    """
    from api.helpers.failure_reset import reset_recording_failure, should_reset_on_retry
    from api.services.config_utils import resolve_full_config

    session_maker = get_async_session_maker()

    async with session_maker() as session:
        full_config, recording = await resolve_full_config(session, recording_id, user_id, manual_override)

        recording_repo = RecordingRepository(session)

        # Reset failure flags if retrying after trim failure
        if should_reset_on_retry(recording, "trim"):
            reset_recording_failure(recording, "trim")
            await recording_repo.update(recording)
            await session.commit()

        trimming_config = full_config.get("trimming", {})

        silence_threshold = trimming_config.get("silence_threshold", -40.0)
        min_silence_duration = trimming_config.get("min_silence_duration", 2.0)
        padding_before = trimming_config.get("padding_before", 5.0)
        padding_after = trimming_config.get("padding_after", 5.0)

        logger.debug(
            f"Trimming config for recording {recording_id}: "
            f"silence_threshold={silence_threshold}, min_silence_duration={min_silence_duration}"
        )

        recording_repo = RecordingRepository(session)

        if not recording.local_video_path:
            raise ValueError("No video file available. Please download first.")

        if not Path(recording.local_video_path).exists():
            raise ValueError(f"Video file not found: {recording.local_video_path}")

        user_slug = recording.owner.user_slug
        storage_builder = StoragePathBuilder()

        temp_dir = str(storage_builder.temp_dir())
        config = ProcessingConfig(
            silence_threshold=silence_threshold,
            min_silence_duration=min_silence_duration,
            padding_before=padding_before,
            padding_after=padding_after,
            output_dir=temp_dir,
        )
        processor = VideoProcessor(config)

        task_self.update_progress(user_id, 15, "Starting video trimming...", step="trim")

        # Mark TRIM stage as IN_PROGRESS

        trim_stage = None
        for stage in recording.processing_stages:
            if stage.stage_type == ProcessingStageType.TRIM:
                trim_stage = stage
                break

        if trim_stage:
            trim_stage.status = models.recording.ProcessingStageStatus.IN_PROGRESS
            update_aggregate_status(recording)
            await session.commit()

        # Step 1: Extract full audio from original video
        task_self.update_progress(user_id, 20, "Extracting audio from original video...", step="extract_audio")

        temp_audio_path = Path(temp_dir) / f"{recording_id}_full_audio.mp3"
        temp_audio_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Extracting full audio: id={recording_id}")

        success = await processor.extract_audio_full(
            recording.local_video_path,
            str(temp_audio_path)
        )

        if not success:
            raise Exception("Failed to extract audio from video")

        # Step 2: Analyze audio file (faster than video)
        task_self.update_progress(user_id, 40, "Analyzing audio for silence...", step="analyze")

        first_sound, last_sound = await processor.audio_detector.detect_audio_boundaries_from_file(
            str(temp_audio_path)
        )

        if first_sound is None:
            if temp_audio_path.exists():
                temp_audio_path.unlink()
            raise Exception("Failed to detect audio start")

        output_video_path = str(storage_builder.recording_video(user_slug, recording_id))
        final_audio_path = str(storage_builder.recording_audio(user_slug, recording_id))
        Path(output_video_path).parent.mkdir(parents=True, exist_ok=True)
        Path(final_audio_path).parent.mkdir(parents=True, exist_ok=True)

        # Sound throughout entire video - skip trimming, reference original
        if last_sound is None and first_sound == 0.0:
            logger.info("Sound throughout entire video, skipping trim")
            task_self.update_progress(user_id, 60, "Using original video...", step="reference_video")

            output_video_path = recording.local_video_path
            logger.info(f"Processed video path references original: {output_video_path}")

            if Path(final_audio_path).exists():
                Path(final_audio_path).unlink()
            shutil.move(str(temp_audio_path), final_audio_path)
            logger.info(f"Full audio saved: {final_audio_path}")

        else:
            # Normal case: trim video and audio
            if last_sound is None:
                if temp_audio_path.exists():
                    temp_audio_path.unlink()
                raise Exception("Failed to detect audio end")

            start_trim = max(0, first_sound - padding_before)
            end_trim = last_sound + padding_after

            logger.info(f"Audio boundaries detected: {start_trim:.1f}s - {end_trim:.1f}s")

            # Step 3: Trim video
            task_self.update_progress(user_id, 60, "Trimming video...", step="trim_video")

            success = await processor.trim_video(
                recording.local_video_path,
                output_video_path,
                start_trim,
                end_trim
            )

            if not success:
                if temp_audio_path.exists():
                    temp_audio_path.unlink()
                raise Exception("Failed to trim video")

            # Step 4: Trim audio (stream copy - instant)
            task_self.update_progress(user_id, 80, "Trimming audio...", step="trim_audio")

            success = await processor.trim_audio(
                str(temp_audio_path),
                final_audio_path,
                start_trim,
                end_trim
            )

            if not success:
                if temp_audio_path.exists():
                    temp_audio_path.unlink()
                raise Exception("Failed to trim audio")

            if temp_audio_path.exists():
                temp_audio_path.unlink()
                logger.info(f"Temp audio cleaned: {temp_audio_path}")

        # Step 5: Update database
        task_self.update_progress(user_id, 90, "Updating database...", step="trim")

        recording.processed_video_path = output_video_path
        recording.processed_audio_path = final_audio_path

        # Mark TRIM stage as COMPLETED
        if trim_stage:
            trim_stage.status = models.recording.ProcessingStageStatus.COMPLETED
            trim_stage.completed_at = datetime.now(UTC)
            update_aggregate_status(recording)

        await recording_repo.update(recording)
        await session.commit()

        logger.info(
            f"✅ Trimming complete: id={recording_id}, "
            f"video={output_video_path}, audio={final_audio_path}"
        )

        return {
            "success": True,
            "processed_video_path": output_video_path,
            "audio_path": final_audio_path,
        }


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.transcribe_recording",
    max_retries=settings.celery.processing_max_retries,
    default_retry_delay=settings.celery.processing_retry_delay,
)
def transcribe_recording_task(
    self,
    recording_id: int,
    user_id: str,
    manual_override: dict | None = None,
) -> dict:
    """
    Transcription of recording with ADMIN credentials (template-driven).

    IMPORTANT: Only transcription (Fireworks), WITHOUT topic extraction.
    For topic extraction, use extract_topics_task.

    Config parameters used:
    - transcription.language (default: "ru")
    - transcription.prompt (default: "")
    - transcription.temperature (default: 0.0)

    Args:
        recording_id: ID of recording
        user_id: ID of user
        manual_override: Optional configuration override

    Returns:
        Results of transcription (without topics)
    """
    try:
        logger.info(f"[Task {self.request.id}] Transcribing recording {recording_id} for user {user_id}")

        self.update_progress(user_id, 10, "Initializing transcription...", step="transcribe")

        result = self.run_async(_async_transcribe_recording(self, recording_id, user_id, manual_override))

        return self.build_result(
            user_id=user_id,
            status="completed",
            recording_id=recording_id,
            result=result,
        )

    except SoftTimeLimitExceeded:
        logger.error(f"[Task {self.request.id}] Soft time limit exceeded")
        raise self.retry(countdown=600, exc=SoftTimeLimitExceeded())

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error transcribing: {exc!r}", exc_info=True)
        raise self.retry(exc=exc)


async def _async_transcribe_recording(
    task_self,
    recording_id: int,
    user_id: str,
    manual_override: dict | None = None,
) -> dict:
    """
    Async function for transcription with ADMIN credentials (template-driven).

    IMPORTANT: Only transcription (Fireworks), WITHOUT topic extraction.
    Topic extraction is done separately through /topics endpoint.

    Config parameters used:
    - transcription.language (default: "ru")
    - transcription.prompt (default: "")
    - transcription.temperature (default: 0.0)
    """
    from api.services.config_utils import resolve_full_config
    from fireworks_module import FireworksConfig, FireworksTranscriptionService
    from transcription_module.manager import get_transcription_manager

    session_maker = get_async_session_maker()

    async with session_maker() as session:
        # Resolve config from hierarchy
        full_config, recording = await resolve_full_config(session, recording_id, user_id, manual_override)

        transcription_config = full_config.get("transcription", {})

        recording_repo = RecordingRepository(session)

        # Check if retrying after failure
        transcribe_stage = next(
            (s for s in recording.processing_stages if s.stage_type == ProcessingStageType.TRANSCRIBE), None
        )
        if transcribe_stage and transcribe_stage.status == ProcessingStageStatus.FAILED:
            logger.info(
                f"Retrying transcription after failure for recording {recording_id} "
                f"(attempt {transcribe_stage.retry_count + 1})"
            )

        # Extract transcription parameters
        language = transcription_config.get("language", "ru")
        user_prompt = transcription_config.get("prompt", "")
        temperature = transcription_config.get("temperature", 0.0)

        logger.debug(
            f"Transcription config for recording {recording_id}: "
            f"language={language}, has_prompt={bool(user_prompt)}, temperature={temperature}"
        )

        # Priority: processed audio > processed video > original video
        audio_path = None

        # Use saved audio file path
        if recording.processed_audio_path:
            audio_path = Path(recording.processed_audio_path)
            if not audio_path.exists():
                raise ValueError(f"Audio file not found: {audio_path}")
        else:
            audio_path = None

        # 2. Fallback on processed or original video
        if not audio_path:
            audio_path = recording.processed_video_path or recording.local_video_path
            if audio_path:
                logger.info(f"🎬 Use video file (audio not found): {audio_path}")

        if not audio_path:
            raise ValueError("No audio or video file available for transcription")

        if not Path(audio_path).exists():
            raise ValueError(f"Audio/video file not found: {audio_path}")

        task_self.update_progress(user_id, 20, "Loading transcription service...", step="transcribe")

        # Load ADMIN credentials (only Fireworks)
        fireworks_config = FireworksConfig.from_file("config/fireworks_creds.json")
        fireworks_service = FireworksTranscriptionService(fireworks_config)

        task_self.update_progress(user_id, 25, "Starting transcription...", step="transcribe")

        # Mark TRANSCRIBE stage as IN_PROGRESS BEFORE actual transcription
        recording.mark_stage_in_progress(ProcessingStageType.TRANSCRIBE)
        update_aggregate_status(recording)  # Will set ProcessingStatus.TRANSCRIBING
        await recording_repo.update(recording)
        await session.commit()

        task_self.update_progress(user_id, 30, "Transcribing audio...", step="transcribe")

        # Compose prompt: user_prompt (from config) + display_name
        fireworks_prompt = fireworks_service.compose_fireworks_prompt(user_prompt, recording.display_name)

        # Transcription through Fireworks API (ONLY transcription, WITHOUT topic extraction)
        # Use language and temperature from resolved config
        transcription_result = await fireworks_service.transcribe_audio(
            audio_path=audio_path,
            language=language,  # ← from resolved config
            prompt=fireworks_prompt,
        )

        task_self.update_progress(user_id, 70, "Saving transcription...", step="transcribe")

        # Save only master.json (WITHOUT topics.json)
        transcription_manager = get_transcription_manager()
        user_slug = recording.owner.user_slug
        transcription_dir = transcription_manager.get_dir(recording_id, user_slug)

        # Prepare data for admin
        words = transcription_result.get("words", [])
        segments = transcription_result.get("segments", [])
        detected_language = transcription_result.get("language", language)

        # Calculate duration from last segment
        duration = 0.0
        if segments and len(segments) > 0:
            last_segment = segments[-1]
            duration = last_segment.get("end", 0.0)

        # Collect metadata for admin (for cost calculation)
        usage_metadata = {
            "model": fireworks_config.model,
            "prompt_used": fireworks_prompt,
            "config": {
                "temperature": temperature,  # ← from resolved config
                "language": language,  # ← from resolved config
                "detected_language": detected_language,
                "response_format": fireworks_config.response_format,
                "timestamp_granularities": fireworks_config.timestamp_granularities,
                "preprocessing": fireworks_config.preprocessing,
            },
            "audio_file": {
                "path": str(audio_path),  # Convert Path to string for JSON serialization
                "duration_seconds": duration,
            },
            # If Fireworks API returns usage, add here
            "usage": transcription_result.get("usage"),
        }

        # Save master.json
        transcription_manager.save_master(
            recording_id=recording_id,
            words=words,
            segments=segments,
            language=language,
            model="fireworks",
            duration=duration,
            usage_metadata=usage_metadata,
            user_slug=user_slug,
            raw_response=transcription_result,
        )

        # Generate cache files (segments.txt, words.txt)
        transcription_manager.generate_cache_files(recording_id, user_slug)

        task_self.update_progress(user_id, 90, "Updating database...", step="transcribe")

        # Update recording in DB (without topics)
        recording.transcription_dir = str(transcription_dir)
        recording.transcription_info = transcription_result

        # Mark transcription stage as completed
        recording.mark_stage_completed(
            ProcessingStageType.TRANSCRIBE,
            meta={"transcription_dir": str(transcription_dir), "language": language, "model": "fireworks"},
        )

        # Update aggregated status based on processing_stages (aggregate status)
        update_aggregate_status(recording)

        await recording_repo.update(recording)
        await session.commit()

        logger.info(
            f"✅ Transcription completed for recording {recording_id} (aggregate status): "
            f"words={len(words)}, segments={len(segments)}, language={language}"
        )

        return {
            "success": True,
            "transcription_dir": str(transcription_dir),
            "language": language,
            "words_count": len(words),
            "segments_count": len(segments),
        }


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.launch_uploads",
    max_retries=0,
)
def _launch_uploads_task(
    self,
    recording_id: int,
    user_id: str,
    platforms: list[str],
    preset_map: dict[str, int],
    metadata_override: dict | None = None,
) -> dict:
    """
    Launch upload tasks after processing chain completes.

    This task is added as final step in chain to ensure uploads start
    only after all processing is complete.

    Args:
        recording_id: ID of recording
        user_id: ID of user
        platforms: List of platforms to upload to
        preset_map: Mapping of platform -> preset_id
        metadata_override: Optional metadata override

    Returns:
        Dict with launched upload task IDs
    """
    from api.tasks.upload import upload_recording_to_platform

    logger.info(
        f"[Task {self.request.id}] Launching uploads for recording {recording_id}: platforms={platforms}"
    )

    upload_task_ids = []
    for platform in platforms:
        try:
            preset_id = preset_map.get(platform)
            upload_task = upload_recording_to_platform.delay(
                recording_id, user_id, platform, preset_id, None, metadata_override
            )

            upload_task_ids.append(
                {
                    "platform": platform,
                    "task_id": upload_task.id,
                    "preset_id": preset_id,
                }
            )
            logger.info(f"Upload task for {platform} launched: {upload_task.id}")
        except Exception as e:
            logger.error(f"Failed to launch upload to {platform}: {e}")

    return self.build_result(
        user_id=user_id,
        status="completed",
        recording_id=recording_id,
        result={"upload_tasks": upload_task_ids},
    )


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.run_recording",
    max_retries=settings.celery.processing_max_retries,
    default_retry_delay=settings.celery.processing_retry_delay,
)
def run_recording_task(
    self,
    recording_id: int,
    user_id: str,
    manual_override: dict | None = None,
) -> dict:
    """
    Full processing pipeline orchestrator using Celery chains for parallel execution.

    Benefits of chain approach:
    - Each step can run on any available worker
    - Better resource utilization during I/O operations
    - Natural task boundaries for monitoring and retries

    Args:
        recording_id: ID of recording
        user_id: ID of user
        manual_override: Optional configuration override

    Returns:
        Task chain signature (not blocking)
    """
    try:
        logger.info(f"[Task {self.request.id}] Orchestrating pipeline for recording {recording_id}, user {user_id}")

        from api.dependencies import get_async_session_maker
        from api.services.config_utils import resolve_full_config

        manual_override = manual_override or {}
        session_maker = get_async_session_maker()

        # Resolve config to determine which steps are enabled
        async def _resolve_pipeline_config():
            async with session_maker() as session:
                full_config, output_config, recording = await resolve_full_config(
                    session, recording_id, user_id, manual_override, include_output_config=True
                )

                preset_ids_list = output_config.get("preset_ids", [])
                presets = []
                if preset_ids_list:
                    preset_repo = OutputPresetRepository(session)
                    presets = await preset_repo.find_by_ids(preset_ids_list, user_id)

                return full_config, output_config, recording, presets

        full_config, output_config, recording, presets = self.run_async(_resolve_pipeline_config())

        # Check blank_record
        if recording.blank_record:
            logger.info(
                f"[Task {self.request.id}] Skipping pipeline for blank_record {recording_id}: "
                f"duration={recording.duration}min, size={recording.video_file_size} bytes"
            )

            async def _mark_skipped():
                async with session_maker() as session:
                    recording_repo = RecordingRepository(session)
                    rec = await recording_repo.get_by_id(recording_id, user_id)
                    if rec:
                        rec.status = ProcessingStatus.SKIPPED
                        rec.failed_reason = "Blank record (too short or too small)"
                        await session.commit()

            self.run_async(_mark_skipped())

            return self.build_result(
                user_id=user_id,
                status="skipped",
                reason="blank_record",
                recording_id=recording_id,
            )

        # Extract config flags
        trimming = full_config.get("trimming", {})
        transcription = full_config.get("transcription", {})

        download_enabled = True
        trim_enabled = trimming.get("enable_trimming", True)
        transcribe_enabled = transcription.get("enable_transcription", True)
        extract_topics_enabled = transcription.get("enable_topics", True)
        generate_subs_enabled = transcription.get("enable_subtitles", True)

        upload_enabled = output_config.get("auto_upload", False)
        platforms = output_config.get("default_platforms", [])

        granularity = transcription.get("granularity", "long")
        subtitle_formats = transcription.get("subtitle_formats", ["srt", "vtt"])

        logger.info(
            f"[Task {self.request.id}] Pipeline config: download={download_enabled}, "
            f"trim={trim_enabled}, transcribe={transcribe_enabled}, "
            f"topics={extract_topics_enabled}, subs={generate_subs_enabled}, upload={upload_enabled}"
        )

        # Build task chain based on enabled steps
        task_chain = []

        # Sequential tasks (must run in order)
        if download_enabled:
            task_chain.append(download_recording_task.si(recording_id, user_id, False, manual_override))

        if trim_enabled:
            task_chain.append(trim_video_task.si(recording_id, user_id, manual_override))

        if transcribe_enabled:
            task_chain.append(transcribe_recording_task.si(recording_id, user_id, manual_override))

        # Parallel tasks after transcription (both depend on transcribe, but not on each other)
        parallel_after_transcribe = []
        if extract_topics_enabled:
            parallel_after_transcribe.append(extract_topics_task.si(recording_id, user_id, granularity, None))

        if generate_subs_enabled:
            parallel_after_transcribe.append(generate_subtitles_task.si(recording_id, user_id, subtitle_formats))

        # Add parallel group to chain if there are tasks
        if parallel_after_transcribe:
            if len(parallel_after_transcribe) > 1:
                # Multiple tasks - run in parallel
                task_chain.append(group(*parallel_after_transcribe))
                logger.info(
                    f"[Task {self.request.id}] Added parallel group: {len(parallel_after_transcribe)} tasks "
                    f"(topics + subtitles)"
                )
            else:
                # Single task - just append normally
                task_chain.append(parallel_after_transcribe[0])

        if not task_chain:
            logger.warning(f"[Task {self.request.id}] No processing steps enabled for recording {recording_id}")
            return self.build_result(
                user_id=user_id,
                status="completed",
                recording_id=recording_id,
                result={"message": "No processing steps enabled"},
            )

        # Build chain with optional upload callback
        if upload_enabled and (platforms or presets):
            # Add upload launcher as final callback in chain
            preset_map = {preset.platform: preset.id for preset in presets}

            if not platforms and presets:
                platforms = [preset.platform for preset in presets]

            metadata_override = full_config.get("metadata_config", {})

            # Create upload callback task
            task_chain.append(
                _launch_uploads_task.si(
                    recording_id=recording_id,
                    user_id=user_id,
                    platforms=platforms,
                    preset_map=preset_map,
                    metadata_override=metadata_override,
                )
            )

            logger.info(
                f"[Task {self.request.id}] Added upload launcher for platforms: {platforms}"
            )

        # Launch chain
        chain_signature = chain(*task_chain)
        chain_result = chain_signature.apply_async()

        logger.info(
            f"[Task {self.request.id}] Pipeline chain launched: {len(task_chain)} tasks, root_id={chain_result.id}"
        )

        return self.build_result(
            user_id=user_id,
            status="launched",
            recording_id=recording_id,
            result={
                "chain_id": chain_result.id,
                "chain_tasks": len(task_chain),
                "upload_enabled": upload_enabled,
                "platforms": platforms if upload_enabled else [],
            },
        )

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Pipeline orchestration failed: {exc!r}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.extract_topics",
    max_retries=settings.celery.processing_max_retries,
    default_retry_delay=settings.celery.processing_retry_delay,
)
def extract_topics_task(
    self,
    recording_id: int,
    user_id: str,
    granularity: str = "long",
    version_id: str | None = None,
) -> dict:
    """
    Extract topics from existing transcription (only admin credentials).

    Model is selected automatically with retries and fallbacks:
    1. First deepseek (primary model)
    2. Fallback on fireworks_deepseek on error

    Args:
        recording_id: ID of recording
        user_id: ID of user
        granularity: Extraction mode ("short" | "long")
        version_id: ID of version (if None, generated automatically)

    Returns:
        Results of topic extraction
    """
    try:
        logger.info(f"[Task {self.request.id}] Extracting topics for recording {recording_id}, user {user_id}")

        self.update_progress(user_id, 10, "Initializing topic extraction...", step="extract_topics")

        result = self.run_async(_async_extract_topics(self, recording_id, user_id, granularity, version_id))

        return self.build_result(
            user_id=user_id,
            status="completed",
            recording_id=recording_id,
            result=result,
        )

    except SoftTimeLimitExceeded:
        logger.error(f"[Task {self.request.id}] Soft time limit exceeded")
        raise self.retry(countdown=600, exc=SoftTimeLimitExceeded())

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error extracting topics: {exc!r}", exc_info=True)
        raise self.retry(exc=exc)


async def _async_extract_topics(
    task_self, recording_id: int, user_id: str, granularity: str, version_id: str | None
) -> dict:
    """
    Async function for extracting topics with automatic model selection.

    Strategy:
    1. Try with deepseek (primary model)
    2. Fallback on fireworks_deepseek on error
    """
    session_maker = get_async_session_maker()

    async with session_maker() as session:
        recording_repo = RecordingRepository(session)

        recording = await recording_repo.get_by_id(recording_id, user_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found for user {user_id}")

        # Get user_slug for path generation
        user_slug = recording.owner.user_slug

        # Check presence of transcription
        transcription_manager = get_transcription_manager()
        if not transcription_manager.has_master(recording_id, user_slug):
            raise ValueError(f"Transcription not found for recording {recording_id}. Please run transcription first.")

        task_self.update_progress(user_id, 20, "Loading transcription...", step="extract_topics")

        # Ensure presence of segments.txt
        segments_path = transcription_manager.ensure_segments_txt(recording_id, user_slug)

        task_self.update_progress(user_id, 30, "Starting topic extraction...", step="extract_topics")

        # Mark EXTRACT_TOPICS stage as IN_PROGRESS BEFORE extraction
        from api.helpers.status_manager import update_aggregate_status

        recording.mark_stage_in_progress(ProcessingStageType.EXTRACT_TOPICS)
        update_aggregate_status(recording)
        await recording_repo.update(recording)
        await session.commit()

        # Try extracting topics with fallback strategy
        topics_result = None
        model_used = None
        last_error = None

        # Strategy 1: DeepSeek (primary model)
        try:
            logger.info(f"[Topics] Trying primary model: deepseek for recording {recording_id}")
            task_self.update_progress(user_id, 40, "Extracting topics (deepseek)...", step="extract_topics")

            deepseek_config = DeepSeekConfig.from_file("config/deepseek_creds.json")
            topic_extractor = TopicExtractor(deepseek_config)

            topics_result = await topic_extractor.extract_topics_from_file(
                segments_file_path=str(segments_path),
                recording_topic=recording.display_name,
                granularity=granularity,
            )
            model_used = "deepseek"
            logger.info(f"[Topics] Successfully extracted with deepseek for recording {recording_id}")

        except Exception as e:
            logger.warning(f"[Topics] DeepSeek failed for recording {recording_id}: {e}. Trying fallback...")
            last_error = e

            # Strategy 2: Fireworks DeepSeek (fallback)
            try:
                logger.info(f"[Topics] Trying fallback model: fireworks_deepseek for recording {recording_id}")
                task_self.update_progress(user_id, 50, "Extracting topics (fallback)...", step="extract_topics")

                deepseek_config = DeepSeekConfig.from_file("config/deepseek_fireworks_creds.json")
                topic_extractor = TopicExtractor(deepseek_config)

                topics_result = await topic_extractor.extract_topics_from_file(
                    segments_file_path=str(segments_path),
                    recording_topic=recording.display_name,
                    granularity=granularity,
                )
                model_used = "fireworks_deepseek"
                logger.info(f"[Topics] Successfully extracted with fireworks_deepseek for recording {recording_id}")

            except Exception as e2:
                logger.error(f"[Topics] All models failed for recording {recording_id}. Last error: {e2}")
                raise ValueError(f"Failed to extract topics with all models. Primary: {last_error}, Fallback: {e2}")

        if not topics_result:
            raise ValueError("Failed to extract topics: no result returned")

        task_self.update_progress(user_id, 80, "Saving topics...", step="extract_topics")

        # Generate version_id if not specified
        if not version_id:
            version_id = transcription_manager.generate_version_id(recording_id, user_slug)

        # Collect metadata for admin
        usage_metadata = {
            "model": model_used,
            "prompt_used": "See TopicExtractor code for prompt generation",
            "config": {
                "temperature": deepseek_config.temperature if deepseek_config else None,
                "max_tokens": deepseek_config.max_tokens if deepseek_config else None,
            },
            # Here you can add usage from API response, if available
        }

        # Save in topics.json
        transcription_manager.add_topics_version(
            recording_id=recording_id,
            version_id=version_id,
            model=model_used,
            granularity=granularity,
            main_topics=topics_result.get("main_topics", []),
            topic_timestamps=topics_result.get("topic_timestamps", []),
            pauses=topics_result.get("long_pauses", []),
            is_active=True,
            usage_metadata=usage_metadata,
            user_slug=user_slug,
        )

        # Update recording in DB (active version)
        recording.topic_timestamps = topics_result.get("topic_timestamps", [])
        recording.main_topics = topics_result.get("main_topics", [])

        # Mark topic extraction stage as completed
        recording.mark_stage_completed(
            ProcessingStageType.EXTRACT_TOPICS,
            meta={"version_id": version_id, "granularity": granularity, "model": model_used},
        )

        # Update aggregated status
        from api.helpers.status_manager import update_aggregate_status

        update_aggregate_status(recording)

        await recording_repo.update(recording)
        await session.commit()

        # Don't show model to user, only results
        return {
            "success": True,
            "version_id": version_id,
            "topics_count": len(topics_result.get("topic_timestamps", [])),
            "main_topics": topics_result.get("main_topics", []),
        }


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.generate_subtitles",
    max_retries=settings.celery.processing_max_retries,
    default_retry_delay=settings.celery.processing_retry_delay,
)
def generate_subtitles_task(
    self,
    recording_id: int,
    user_id: str,
    formats: list[str] | None = None,
) -> dict:
    """
    Generate subtitles from existing transcription.

    Args:
        recording_id: ID of recording
        user_id: ID of user
        formats: List of formats ('srt', 'vtt')

    Returns:
        Results of subtitle generation
    """
    try:
        logger.info(f"[Task {self.request.id}] Generating subtitles for recording {recording_id}, user {user_id}")

        formats = formats or ["srt", "vtt"]

        self.update_progress(user_id, 20, "Initializing subtitle generation...", step="generate_subtitles")

        result = self.run_async(_async_generate_subtitles(self, recording_id, user_id, formats))

        return self.build_result(
            user_id=user_id,
            status="completed",
            recording_id=recording_id,
            result=result,
        )

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error generating subtitles: {exc!r}", exc_info=True)
        raise self.retry(exc=exc)


async def _async_generate_subtitles(task_self, recording_id: int, user_id: str, formats: list[str]) -> dict:
    """Async function for generating subtitles."""
    session_maker = get_async_session_maker()

    async with session_maker() as session:
        recording_repo = RecordingRepository(session)

        recording = await recording_repo.get_by_id(recording_id, user_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found for user {user_id}")

        # Get user_slug for path generation
        user_slug = recording.owner.user_slug

        # Check presence of transcription
        transcription_manager = get_transcription_manager()
        if not transcription_manager.has_master(recording_id, user_slug):
            raise ValueError(f"Transcription not found for recording {recording_id}. Please run transcription first.")

        task_self.update_progress(user_id, 30, "Starting subtitle generation...", step="generate_subtitles")

        # Mark GENERATE_SUBTITLES stage as IN_PROGRESS BEFORE generation
        from api.helpers.status_manager import update_aggregate_status

        recording.mark_stage_in_progress(ProcessingStageType.GENERATE_SUBTITLES)
        update_aggregate_status(recording)
        await recording_repo.update(recording)
        await session.commit()

        task_self.update_progress(user_id, 40, "Generating subtitles...", step="generate_subtitles")

        # Generate subtitles
        subtitle_paths = transcription_manager.generate_subtitles(
            recording_id=recording_id,
            formats=formats,
            user_slug=user_slug,
        )

        task_self.update_progress(user_id, 90, "Saving results...", step="generate_subtitles")

        # Update recording in DB
        recording.mark_stage_completed(
            ProcessingStageType.GENERATE_SUBTITLES,
            meta={"formats": formats, "files": subtitle_paths},
        )

        # Update aggregated status
        from api.helpers.status_manager import update_aggregate_status

        update_aggregate_status(recording)

        await recording_repo.update(recording)
        await session.commit()

        return {
            "success": True,
            "formats": formats,
            "files": subtitle_paths,
        }


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.batch_transcribe_recording",
    max_retries=settings.celery.processing_max_retries,
    default_retry_delay=settings.celery.processing_retry_delay,
)
def batch_transcribe_recording_task(
    self,
    recording_id: int,
    user_id: str,
    batch_id: str,
    poll_interval: float = 10.0,
    max_wait_time: float = 3600.0,
) -> dict:
    """
    Polling for Fireworks Batch API transcription.

    This task is created after submit_batch_transcription() and waits for completion of batch job.
    Uses polling to check status every poll_interval seconds.

    Args:
        recording_id: ID of recording
        user_id: ID of user
        batch_id: ID of batch job from Fireworks
        poll_interval: Status check interval (seconds)
        max_wait_time: Maximum waiting time (seconds)

    Returns:
        Result of transcription
    """
    try:
        logger.info(
            f"[Task {self.request.id}] Batch transcription polling | recording={recording_id} | user={user_id} | batch_id={batch_id}"
        )

        self.update_progress(user_id, 10, "Waiting for batch transcription...", step="batch_transcribe")

        result = self.run_async(
            _async_poll_batch_transcription(
                self,
                recording_id,
                user_id,
                batch_id,
                poll_interval,
                max_wait_time,
            )
        )

        return self.build_result(
            user_id=user_id,
            status="completed",
            recording_id=recording_id,
            batch_id=batch_id,
            result=result,
        )

    except TimeoutError as exc:
        logger.error(
            f"[Task {self.request.id}] Batch transcription timeout | batch_id={batch_id} | max_wait={max_wait_time}s"
        )
        raise self.retry(countdown=600, exc=exc)

    except SoftTimeLimitExceeded:
        logger.error(f"[Task {self.request.id}] Soft time limit exceeded")
        raise self.retry(countdown=900, exc=SoftTimeLimitExceeded())

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error in batch transcription: {exc!r}", exc_info=True)
        raise self.retry(exc=exc)


async def _async_poll_batch_transcription(
    task_self,
    recording_id: int,
    user_id: str,
    batch_id: str,
    poll_interval: float,
    max_wait_time: float,
) -> dict:
    """Async function for polling batch transcription."""
    session_maker = get_async_session_maker()
    session = session_maker()

    try:
        recording_repo = RecordingRepository(session)
        recording_db = await recording_repo.find_by_id(recording_id, user_id)

        if not recording_db:
            raise ValueError(f"Recording {recording_id} not found for user {user_id}")

        recording = MeetingRecording.from_db_model(recording_db)

        # Initialize Fireworks service
        fireworks_config = FireworksConfig.from_file("config/fireworks_creds.json")
        fireworks_service = FireworksTranscriptionService(fireworks_config)

        # Polling loop
        start_time = time.time()
        attempt = 0

        while True:
            attempt += 1
            elapsed = time.time() - start_time

            if elapsed > max_wait_time:
                raise TimeoutError(
                    f"Batch transcription {batch_id} not completed after {max_wait_time}s (attempts: {attempt})"
                )

            # Check status
            status_response = await fireworks_service.check_batch_status(batch_id)
            status = status_response.get("status", "unknown")

            # Update progress (approximately)
            progress = min(20 + int((elapsed / max_wait_time) * 60), 80)
            task_self.update_progress(
                user_id,
                progress,
                f"Batch transcribing... ({status}, {elapsed:.0f}s)",
                step="batch_transcribe",
                batch_id=batch_id,
                attempt=attempt,
            )

            if status == "completed":
                logger.info(
                    f"[Batch Transcription] Completed ✅ | batch_id={batch_id} | elapsed={elapsed:.1f}s | attempts={attempt}"
                )

                task_self.update_progress(user_id, 85, "Parsing batch result...", step="batch_transcribe")

                # Get result
                transcription_result = await fireworks_service.get_batch_result(batch_id)

                # Save transcription (as usual)
                transcription_manager = TranscriptionManager()

                task_self.update_progress(user_id, 90, "Saving transcription...", step="batch_transcribe")

                # Get user_slug for path generation
                user_slug = recording.owner.user_slug

                # Save master.json
                words = transcription_result.get("words", [])
                segments = transcription_result.get("segments", [])
                language = transcription_result.get("language", "ru")

                master_data = {
                    "text": transcription_result.get("text", ""),
                    "segments": segments,
                    "words": words,
                    "language": language,
                }

                transcription_manager.save_master(
                    recording_id=recording_id,
                    master_data=master_data,
                    user_slug=user_slug,
                )

                # Update recording in DB
                recording.transcription_path = transcription_manager.get_dir(recording_id, user_slug)
                recording.mark_stage_completed(
                    ProcessingStageType.TRANSCRIBE,
                    meta={
                        "batch_id": batch_id,
                        "language": language,
                        "words_count": len(words),
                        "segments_count": len(segments),
                        "elapsed_seconds": elapsed,
                    },
                )

                # Update aggregated status
                from api.helpers.status_manager import update_aggregate_status

                update_aggregate_status(recording)

                await recording_repo.update(recording)
                await session.commit()

                return {
                    "success": True,
                    "batch_id": batch_id,
                    "language": language,
                    "elapsed_seconds": elapsed,
                    "attempts": attempt,
                }

            logger.debug(
                f"[Batch Transcription] Polling | batch_id={batch_id} | status={status} | attempt={attempt} | elapsed={elapsed:.1f}s"
            )

            await asyncio.sleep(poll_interval)

    finally:
        await session.close()
