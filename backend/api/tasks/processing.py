"""Celery tasks for processing recordings with multi-tenancy support."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from celery import chain, group
from celery.exceptions import SoftTimeLimitExceeded

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.helpers.status_manager import update_aggregate_status
from api.observability import track_pipeline_stage
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import OutputPresetRepository
from api.services.config_utils import resolve_full_config
from api.services.timing_service import TimingService
from api.tasks.base import ProcessingTask
from config.settings import get_settings
from database.models import RecordingModel
from deepseek_module import DeepSeekConfig, TopicExtractor
from file_storage.path_builder import StoragePathBuilder
from logger import format_details, format_status_change, get_logger, short_task_id, short_user_id
from models import MeetingRecording, ProcessingStageStatus, ProcessingStageType, ProcessingStatus
from transcription_module.manager import get_transcription_manager
from video_download_module.downloader import ZoomDownloader
from video_download_module.factory import create_downloader
from video_processing_module.config import ProcessingConfig
from video_processing_module.video_processor import VideoProcessor, output_suffix_for_trim

logger = get_logger()
settings = get_settings()


def _update_pipeline_completed(recording: RecordingModel) -> None:
    """Update pipeline_completed_at and duration after stage completion."""
    now = datetime.now(UTC)
    recording.pipeline_completed_at = now
    if recording.pipeline_started_at:
        recording.pipeline_duration_seconds = (now - recording.pipeline_started_at).total_seconds()


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
    Download recording from source (Zoom, yt-dlp, Yandex Disk, etc.).

    Dispatches to the appropriate downloader based on recording source_type.

    Args:
        recording_id: ID of recording
        user_id: ID of user
        force: Force download if already downloaded
        manual_override: Optional configuration override

    Returns:
        Result of download
    """
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info("Downloading")

            self.update_progress(user_id=user_id, progress=10, status="Initializing download...", step="download")

            with track_pipeline_stage("download"):
                result = self.run_async(_async_download_recording(self, recording_id, user_id, force, manual_override))

            return self.build_result(
                user_id=user_id,
                status="completed",
                recording_id=recording_id,
                result=result,
            )

        except SoftTimeLimitExceeded:
            logger.error("Soft time limit exceeded")
            raise self.retry(countdown=900, exc=SoftTimeLimitExceeded())

        except Exception as exc:
            logger.error(f"Error downloading: {exc!r}", exc_info=True)
            raise self.retry(exc=exc)


async def _refresh_download_token_if_needed(
    session,
    recording,
    user_id: str,
    meeting_id: str,
    force: bool,
) -> str | None:
    """Refresh download_access_token if needed (old/missing/force).

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

    logger.info(f"Refreshing download token | {format_details(age_days=token_age_days, force=force)}")

    try:
        # Get input source
        if not recording.source or not recording.source.input_source_id:
            logger.warning("No input source for token refresh")
            return current_token

        source_repo = InputSourceRepository(session)
        source = await source_repo.find_by_id(recording.source.input_source_id, user_id)

        if not source or not source.credential_id:
            logger.warning("Source not found or no credential for token refresh")
            return current_token

        # Get credentials
        cred_repo = UserCredentialRepository(session)
        credential = await cred_repo.get_by_id(source.credential_id)

        if not credential:
            logger.warning(f"Credential not found | credential={source.credential_id}")
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
            logger.info(f"Download token refreshed | {format_details(length=len(fresh_token))}")

            # Update in source.meta for future use
            if recording.source and recording.source.meta:
                recording.source.meta["download_access_token"] = fresh_token
                recording.updated_at = datetime.now(UTC)
                await session.commit()

            return fresh_token

        logger.warning("No fresh token received, using existing")
        return current_token

    except Exception as e:
        logger.warning(f"Error refreshing token: {e}, using existing")
        return current_token


async def _async_download_recording(
    task_self,
    recording_id: int,
    user_id: str,
    force: bool,
    manual_override: dict | None = None,
) -> dict:
    """Async function for downloading (template-driven, multi-source)."""
    from api.helpers.failure_reset import reset_recording_failure, should_reset_on_retry
    from models.recording import SourceType

    async_session_maker = get_async_session_maker()
    async with async_session_maker() as session:
        # Resolve config
        full_config, recording = await resolve_full_config(session, recording_id, user_id, manual_override)

        # Check pause flag before starting
        if recording.on_pause:
            logger.info("Skipped: recording paused")
            return {"status": "paused", "message": "Pipeline paused by user"}

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
            f"Download config | {format_details(max_file_size_mb=max_file_size_mb, retry_attempts=retry_attempts)}"
        )

        # Check if not already downloaded (consult storage backend, key may be S3 or LOCAL)
        if not force and recording.status == ProcessingStatus.DOWNLOADED and recording.local_video_path:
            from file_storage.factory import get_storage_backend as _get_storage

            if await _get_storage().exists(recording.local_video_path):
                return {
                    "success": True,
                    "message": "Already downloaded",
                    "local_video_path": recording.local_video_path,
                }

        # Get user_slug for path generation
        user_slug = recording.owner.user_slug
        storage_builder = StoragePathBuilder()

        source_type = recording.source.source_type if recording.source else SourceType.ZOOM
        if not recording.source:
            logger.warning("No source, defaulting to ZOOM")

        # Start download timing (stage_timings only, not processing_stages)
        timing_service = TimingService(session)
        timing = await timing_service.start_stage(recording_id, user_id, "DOWNLOAD")
        await session.commit()

        try:
            if source_type in (SourceType.EXTERNAL_URL, SourceType.YOUTUBE, SourceType.YANDEX_DISK):
                result = await _download_via_external(
                    task_self,
                    session,
                    recording,
                    recording_repo,
                    user_id,
                    user_slug,
                    storage_builder,
                    source_type,
                    force,
                )
            else:
                result = await _download_via_zoom(
                    task_self,
                    session,
                    recording,
                    recording_repo,
                    user_id,
                    user_slug,
                    storage_builder,
                    force,
                )

            await timing_service.complete_stage(timing, meta={"file_size": recording.video_file_size})
            _update_pipeline_completed(recording)
            await session.commit()
            return result

        except Exception as e:
            await timing_service.fail_stage(timing, str(e))
            await session.commit()
            raise


async def _refresh_yandex_disk_oauth_if_expiring(
    creds_data: dict,
    credential,
    cred_repo,
    encryption,
) -> None:
    """
    If the stored Yandex Disk access token is near expiry, refresh via Yandex OAuth and persist.

    Mirrors the idea of ``_refresh_download_token_if_needed`` for Zoom: avoid starting a long
    download with a token that will expire mid-transfer when refresh_token + client_id exist.
    """
    from api.schemas.auth import UserCredentialUpdate
    from api.services.oauth_service import refresh_yandex_disk_oauth_token

    rt = creds_data.get("refresh_token")
    cid = creds_data.get("client_id")
    if not rt or not cid:
        return
    exp = creds_data.get("expiry")
    need_refresh = False
    if exp:
        try:
            normalized = exp.replace("Z", "+00:00") if exp.endswith("Z") else exp
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            need_refresh = datetime.now(UTC) >= dt - timedelta(seconds=300)
        except ValueError:
            need_refresh = False
    if not need_refresh:
        return
    try:
        token_data = await refresh_yandex_disk_oauth_token(
            rt,
            override_client_id=cid,
            override_client_secret=creds_data.get("client_secret"),
        )
    except Exception as e:
        logger.warning(f"Yandex Disk credential refresh before download failed: {e}")
        return
    creds_data["oauth_token"] = token_data["access_token"]
    if token_data.get("refresh_token"):
        creds_data["refresh_token"] = token_data["refresh_token"]
    expires_in = int(token_data.get("expires_in", 3600))
    creds_data["expires_in"] = expires_in
    creds_data["expiry"] = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat().replace("+00:00", "Z")
    enc = encryption.encrypt_credentials(creds_data)
    await cred_repo.update(credential.id, UserCredentialUpdate(encrypted_data=enc))


async def _download_via_external(
    task_self,
    session,
    recording,
    recording_repo,
    user_id: str,
    user_slug: int,
    storage_builder: StoragePathBuilder,
    source_type: str,
    force: bool,
) -> dict:
    """Download via factory-based downloader (yt-dlp, Yandex Disk, etc.)."""
    from api.auth.encryption import get_encryption
    from api.repositories.auth_repos import UserCredentialRepository
    from api.repositories.template_repos import InputSourceRepository

    source_meta = recording.source.meta if recording.source and recording.source.meta else {}

    task_self.update_progress(user_id=user_id, progress=30, status="Preparing download...", step="download")

    # Yandex Disk OAuth token is stored encrypted, not in source_meta
    oauth_token = None
    if source_type == "YANDEX_DISK" and recording.source and recording.source.input_source_id:
        source_repo = InputSourceRepository(session)
        source = await source_repo.find_by_id(recording.source.input_source_id, user_id)
        if source and source.credential_id:
            cred_repo = UserCredentialRepository(session)
            credential = await cred_repo.get_by_id(source.credential_id)
            if credential:
                encryption = get_encryption()
                creds_data = encryption.decrypt_credentials(credential.encrypted_data)
                await _refresh_yandex_disk_oauth_if_expiring(creds_data, credential, cred_repo, encryption)
                oauth_token = creds_data.get("oauth_token")

    downloader = create_downloader(
        source_type=source_type,
        user_slug=user_slug,
        storage_builder=storage_builder,
        oauth_token=oauth_token,
    )

    old_status = recording.status
    recording.status = ProcessingStatus.DOWNLOADING
    recording.download_started_at = datetime.now(UTC)
    logger.info(format_status_change("Recording", old_status, recording.status))
    await recording_repo.update(recording)
    await session.commit()

    task_self.update_progress(user_id=user_id, progress=50, status="Downloading video...", step="download")

    result = await downloader.download(
        recording_id=recording.id,
        source_meta=source_meta,
        force=force,
    )

    task_self.update_progress(user_id=user_id, progress=90, status="Updating database...", step="download")

    recording.local_video_path = result.storage_key
    old_status = recording.status
    recording.status = ProcessingStatus.DOWNLOADED
    recording.downloaded_at = datetime.now(UTC)
    recording.video_file_size = result.file_size
    logger.info(
        f"{format_status_change('Recording', old_status, recording.status)} | {format_details(size=result.file_size)}"
    )
    await recording_repo.update(recording)
    await session.commit()

    return {"success": True, "local_video_path": recording.local_video_path}


async def _download_via_zoom(
    task_self,
    session,
    recording,
    recording_repo,
    user_id: str,
    user_slug: int,
    storage_builder: StoragePathBuilder,
    force: bool,
) -> dict:
    """Download via Zoom API with token refresh."""
    download_url = None
    if recording.source and recording.source.meta:
        download_url = recording.source.meta.get("download_url")

    if not download_url:
        raise ValueError("No download URL available. Please sync from Zoom first.")

    task_self.update_progress(
        user_id=user_id,
        progress=30,
        status="Downloading from Zoom...",
        step="download",
    )

    downloader = ZoomDownloader(user_slug=user_slug, storage_builder=storage_builder)

    meeting_id = recording.source.source_key if recording.source else str(recording.id)
    file_size = recording.source.meta.get("file_size", 0) if recording.source and recording.source.meta else 0
    passcode = (
        recording.source.meta.get("recording_play_passcode") if recording.source and recording.source.meta else None
    )
    password = recording.source.meta.get("password") if recording.source and recording.source.meta else None
    account = recording.source.meta.get("account") if recording.source and recording.source.meta else None

    download_access_token = await _refresh_download_token_if_needed(session, recording, user_id, meeting_id, force)

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
    old_status = recording.status
    recording.status = ProcessingStatus.DOWNLOADING
    logger.info(format_status_change("Recording", old_status, recording.status))
    await recording_repo.update(recording)
    await session.commit()

    task_self.update_progress(user_id, 50, "Downloading video file...", step="download")

    from config.settings import get_settings
    from utils.pipeline_video_formats import (
        ingress_suffix_from_zoom_video_file_type,
        pipeline_ingress_suffixes_from_settings_formats,
    )

    zoom_meta = recording.source.meta if recording.source else None
    zoom_file_type = zoom_meta.get("video_file_type") if zoom_meta else None
    zoom_suffix = ingress_suffix_from_zoom_video_file_type(
        zoom_file_type,
        pipeline_ingress_suffixes_from_settings_formats(get_settings().storage.supported_video_formats),
    )

    # Download
    success = await downloader.download_recording(meeting_recording, force_download=force, source_suffix=zoom_suffix)

    # On failure, retry once with force-refreshed token (handles expired download_access_token)
    if not success:
        logger.warning("Download failed, retrying with fresh token")
        fresh_token = await _refresh_download_token_if_needed(session, recording, user_id, meeting_id, True)
        if fresh_token and fresh_token != download_access_token:
            meeting_recording.download_access_token = fresh_token
            task_self.update_progress(user_id, 55, "Retrying with fresh token...", step="download")
            success = await downloader.download_recording(
                meeting_recording, force_download=True, source_suffix=zoom_suffix
            )

    if success:
        task_self.update_progress(user_id, 90, "Updating database...", step="download")

        recording.local_video_path = meeting_recording.local_video_path
        old_status = recording.status
        recording.status = ProcessingStatus.DOWNLOADED
        logger.info(format_status_change("Recording", old_status, recording.status))
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
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info("Trimming")

            self.update_progress(user_id, 10, "Initializing video trimming...", step="trim")

            with track_pipeline_stage("trim"):
                result = self.run_async(_async_process_video(self, recording_id, user_id, manual_override))

            return self.build_result(
                user_id=user_id,
                status="completed",
                recording_id=recording_id,
                result=result,
            )

        except SoftTimeLimitExceeded:
            logger.error("Soft time limit exceeded")
            raise self.retry(countdown=600, exc=SoftTimeLimitExceeded())

        except Exception as exc:
            logger.error(f"Error trimming: {exc!r}", exc_info=True)
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

        # Check pause flag before starting
        if recording.on_pause:
            logger.info("Skipped: recording paused")
            return {"status": "paused", "message": "Pipeline paused by user"}

        # Idempotency: skip if trim already completed successfully
        trim_stage = next((s for s in recording.processing_stages if s.stage_type == ProcessingStageType.TRIM), None)
        if trim_stage and trim_stage.status == ProcessingStageStatus.COMPLETED:
            logger.info("Skipped: trim already completed")
            return {"status": "skipped", "reason": "already_completed"}

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
            f"Trim config | {format_details(silence_threshold=silence_threshold, min_silence_duration=min_silence_duration)}"
        )

        recording_repo = RecordingRepository(session)

        if not recording.local_video_path:
            raise ValueError("No video file available. Please download first.")

        from file_storage.factory import get_storage_backend
        from file_storage.path_builder import to_storage_key as _to_storage_key

        storage_backend = get_storage_backend()
        source_storage_key = recording.local_video_path

        if not await storage_backend.exists(source_storage_key):
            raise ValueError(f"Video file not found in storage: {source_storage_key}")

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

        # Materialize the source video locally for FFmpeg (it needs a real path).
        source_suffix = Path(source_storage_key).suffix or ".mp4"
        local_source_video = storage_builder.create_temp_file(prefix=f"trim_src_{recording_id}_", suffix=source_suffix)
        await storage_backend.download_to_file(source_storage_key, local_source_video)

        task_self.update_progress(user_id, 15, "Starting video trimming...", step="trim")

        # Mark TRIM stage as IN_PROGRESS
        recording.mark_stage_in_progress(ProcessingStageType.TRIM)
        logger.info(
            format_status_change("Stage TRIM", ProcessingStageStatus.PENDING, ProcessingStageStatus.IN_PROGRESS)
        )
        update_aggregate_status(recording)

        timing_service = TimingService(session)
        timing = await timing_service.start_stage(recording_id, user_id, "TRIM")
        await session.commit()

        try:
            # Step 1: Extract full audio from original video
            task_self.update_progress(user_id, 20, "Extracting audio from original video...", step="extract_audio")

            sub_extract = await timing_service.start_substep(recording_id, user_id, "TRIM", "extract_audio")
            await session.commit()

            temp_audio_path = Path(temp_dir) / f"{recording_id}_full_audio.mp3"
            temp_audio_path.parent.mkdir(parents=True, exist_ok=True)

            logger.debug("Extracting full audio")

            success = await processor.extract_audio_full(str(local_source_video), str(temp_audio_path))

            if not success:
                raise Exception("Failed to extract audio from video")

            await timing_service.complete_substep(sub_extract)
            await session.commit()

            # Step 2: Analyze audio file (faster than video)
            task_self.update_progress(user_id, 40, "Analyzing audio for silence...", step="analyze")

            sub_analyze = await timing_service.start_substep(recording_id, user_id, "TRIM", "analyze_silence")
            await session.commit()

            first_sound, last_sound = await processor.audio_detector.detect_audio_boundaries_from_file(
                str(temp_audio_path)
            )

            if first_sound is None:
                if temp_audio_path.exists():
                    temp_audio_path.unlink()
                raise Exception("Failed to detect audio start")

            await timing_service.complete_substep(sub_analyze)
            await session.commit()

            # Determine output container suffix from actual stream codecs to avoid
            # stream-copy into an incompatible muxer (e.g. VP8+Vorbis into .mp4).
            source_info = await processor.get_video_info(str(local_source_video))
            video_suffix = output_suffix_for_trim(source_info.get("video_codec"), source_info.get("audio_codec"))
            logger.debug(
                f"Output container | {format_details(video_codec=source_info.get('video_codec'), audio_codec=source_info.get('audio_codec'), suffix=video_suffix)}"
            )

            # Canonical storage keys for the processed artifacts.
            output_video_key = _to_storage_key(
                storage_builder.recording_video(user_slug, recording_id, suffix=video_suffix)
            )
            output_audio_key = _to_storage_key(storage_builder.recording_audio(user_slug, recording_id))

            # Sound throughout entire video - skip trimming, reuse source video as processed.
            if last_sound is None and first_sound == 0.0:
                logger.info("Skipped: sound throughout entire video")
                task_self.update_progress(user_id, 60, "Using original video...", step="reference_video")

                # No trim needed — keep source as processed video (avoid copying a multi-GB file).
                output_video_key = source_storage_key
                logger.debug(f"Processed video references source: {output_video_key}")

                # Commit the extracted full audio under the canonical audio key.
                await storage_backend.save_file(output_audio_key, temp_audio_path)

            else:
                # Normal case: trim video and audio (FFmpeg requires local files).
                if last_sound is None:
                    if temp_audio_path.exists():
                        temp_audio_path.unlink()
                    raise Exception("Failed to detect audio end")

                start_trim = max(0, first_sound - padding_before)
                end_trim = last_sound + padding_after

                if end_trim <= start_trim:
                    duration_fallback = await processor.audio_detector.get_duration_seconds(str(temp_audio_path))
                    if duration_fallback is None or duration_fallback <= 0:
                        if temp_audio_path.exists():
                            temp_audio_path.unlink()
                        raise Exception(
                            "Invalid trim window (end <= start) and could not read media duration for fallback"
                        )
                    logger.warning(
                        f"Invalid trim window (end<=start); using full media | "
                        f"start={start_trim:.1f}s end={end_trim:.1f}s duration={duration_fallback:.1f}s"
                    )
                    start_trim = 0.0
                    end_trim = duration_fallback

                logger.info(f"Audio boundaries | {format_details(start=f'{start_trim:.1f}s', end=f'{end_trim:.1f}s')}")

                # Silence-based bounds can exceed container duration (padding, MP3 vs video mismatch).
                video_meta = await processor.get_video_info(str(local_source_video))
                video_duration = float(video_meta["duration"])
                if end_trim > video_duration:
                    logger.warning(
                        f"Trim end exceeds video duration; clamping | "
                        f"end={end_trim:.2f}s video_duration={video_duration:.2f}s"
                    )
                    end_trim = video_duration
                if start_trim >= video_duration:
                    logger.warning(
                        f"Trim start past EOF; resetting | start={start_trim:.2f}s video_duration={video_duration:.2f}s"
                    )
                    start_trim = max(0.0, video_duration - 1.0)
                if end_trim <= start_trim:
                    duration_fallback = await processor.audio_detector.get_duration_seconds(str(temp_audio_path))
                    if duration_fallback is None or duration_fallback <= 0:
                        if temp_audio_path.exists():
                            temp_audio_path.unlink()
                        raise Exception(
                            "Invalid trim window after duration clamp and could not read media duration for fallback"
                        )
                    logger.warning(
                        f"Invalid trim window after clamp; using full media | "
                        f"start={start_trim:.1f}s end={end_trim:.1f}s duration={duration_fallback:.1f}s"
                    )
                    start_trim = 0.0
                    end_trim = min(duration_fallback, video_duration)

                logger.info(
                    f"Trim window vs video | {format_details(start=f'{start_trim:.1f}s', end=f'{end_trim:.1f}s', video=f'{video_duration:.1f}s')}"
                )

                # Step 3: Trim video into a local temp output.
                task_self.update_progress(user_id, 60, "Trimming video...", step="trim_video")

                sub_trim_v = await timing_service.start_substep(recording_id, user_id, "TRIM", "trim_video")
                await session.commit()

                local_video_out = storage_builder.create_temp_file(
                    prefix=f"trim_video_{recording_id}_", suffix=video_suffix
                )
                success = await processor.trim_video(
                    str(local_source_video), str(local_video_out), start_trim, end_trim
                )

                if not success:
                    if temp_audio_path.exists():
                        temp_audio_path.unlink()
                    local_video_out.unlink(missing_ok=True)
                    raise Exception("Failed to trim video")

                await timing_service.complete_substep(sub_trim_v)
                await session.commit()

                # Step 4: Trim audio (stream copy - instant) into a local temp output.
                task_self.update_progress(user_id, 80, "Trimming audio...", step="trim_audio")

                sub_trim_a = await timing_service.start_substep(recording_id, user_id, "TRIM", "trim_audio")
                await session.commit()

                local_audio_out = storage_builder.create_temp_file(prefix=f"trim_audio_{recording_id}_", suffix=".mp3")
                success = await processor.trim_audio(str(temp_audio_path), str(local_audio_out), start_trim, end_trim)

                if not success:
                    if temp_audio_path.exists():
                        temp_audio_path.unlink()
                    local_video_out.unlink(missing_ok=True)
                    local_audio_out.unlink(missing_ok=True)
                    raise Exception("Failed to trim audio")

                await timing_service.complete_substep(sub_trim_a)
                await session.commit()

                # Commit results to storage (save_file consumes the temp on LOCAL backend).
                await storage_backend.save_file(output_video_key, local_video_out)
                await storage_backend.save_file(output_audio_key, local_audio_out)
                local_video_out.unlink(missing_ok=True)
                local_audio_out.unlink(missing_ok=True)

                if temp_audio_path.exists():
                    temp_audio_path.unlink()
                    logger.debug(f"Temp audio cleaned: {temp_audio_path}")

            # Step 5: Update database
            task_self.update_progress(user_id, 90, "Updating database...", step="trim")

            recording.processed_video_path = output_video_key
            recording.processed_audio_path = output_audio_key

            # Mark TRIM stage as COMPLETED
            recording.mark_stage_completed(ProcessingStageType.TRIM)
            update_aggregate_status(recording)

            await timing_service.complete_stage(timing)
            _update_pipeline_completed(recording)

            logger.success(
                f"{format_status_change('Stage TRIM', ProcessingStageStatus.IN_PROGRESS, ProcessingStageStatus.COMPLETED)}"
                f" | {format_details(elapsed=f'{timing.duration_seconds:.1f}s')}"
            )

            await recording_repo.update(recording)
            await session.commit()

            logger.debug(f"Trim output | video={output_video_key} • audio={output_audio_key}")

            return {
                "success": True,
                "processed_video_path": output_video_key,
                "audio_path": output_audio_key,
            }

        except Exception as e:
            await timing_service.fail_stage(timing, str(e))
            await session.commit()
            raise
        finally:
            # Always purge the local temp materialization of the source video.
            local_source_video.unlink(missing_ok=True)


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

    IMPORTANT: Only transcription (AssemblyAI), WITHOUT topic extraction.
    For topic extraction, use extract_topics_task.

    Config parameters used:
    - transcription.language (default: "ru")
    - transcription.vocabulary (list[str], fed as keyterms_prompt)

    Args:
        recording_id: ID of recording
        user_id: ID of user
        manual_override: Optional configuration override

    Returns:
        Results of transcription (without topics)
    """
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info("Transcribing")

            self.update_progress(user_id, 10, "Initializing transcription...", step="transcribe")

            with track_pipeline_stage("transcribe"):
                result = self.run_async(_async_transcribe_recording(self, recording_id, user_id, manual_override))

            return self.build_result(
                user_id=user_id,
                status="completed",
                recording_id=recording_id,
                result=result,
            )

        except SoftTimeLimitExceeded:
            logger.error("Soft time limit exceeded")
            raise self.retry(countdown=600, exc=SoftTimeLimitExceeded())

        except Exception as exc:
            logger.error(f"Error transcribing: {exc!r}", exc_info=True)
            raise self.retry(exc=exc)


async def _async_transcribe_recording(
    task_self,
    recording_id: int,
    user_id: str,
    manual_override: dict | None = None,
) -> dict:
    """
    Async function for transcription with ADMIN credentials (template-driven).

    IMPORTANT: Only transcription (AssemblyAI), WITHOUT topic extraction.
    Topic extraction is done separately through /topics endpoint.

    Config parameters used:
    - transcription.language (default: "ru")
    - transcription.vocabulary (list[str], fed as keyterms_prompt)
    ASR model: application settings (AssemblyAISettings / env ASSEMBLYAI_*), not per-user.
    """
    from api.services.config_utils import resolve_full_config
    from assemblyai_module import AssemblyAIConfig, AssemblyAITranscriptionService
    from transcription_module.keyterms import compose_keyterms
    from transcription_module.manager import get_transcription_manager

    session_maker = get_async_session_maker()

    async with session_maker() as session:
        # Resolve config from hierarchy
        full_config, recording = await resolve_full_config(session, recording_id, user_id, manual_override)

        # Check pause flag before starting
        if recording.on_pause:
            logger.info("Skipped: recording paused")
            return {"status": "paused", "message": "Pipeline paused by user"}

        transcription_config = full_config.get("transcription", {})

        recording_repo = RecordingRepository(session)

        # Check if retrying after failure
        transcribe_stage = next(
            (s for s in recording.processing_stages if s.stage_type == ProcessingStageType.TRANSCRIBE), None
        )

        # Idempotency: skip if transcription already completed successfully
        if transcribe_stage and transcribe_stage.status == ProcessingStageStatus.COMPLETED:
            logger.info("Skipped: transcription already completed")
            return {"status": "skipped", "reason": "already_completed"}

        if transcribe_stage and transcribe_stage.status == ProcessingStageStatus.FAILED:
            logger.info(f"Retrying transcription | {format_details(attempt=transcribe_stage.retry_count + 1)}")

        # Extract transcription parameters
        language = transcription_config.get("language") or None
        vocabulary = transcription_config.get("vocabulary") or []

        logger.info(f"Transcription config | {format_details(lang=language, vocab=len(vocabulary))}")

        # Priority: processed audio > processed video > original video. Each is a storage key.
        from file_storage.factory import get_storage_backend as _get_storage

        storage_backend = _get_storage()

        audio_storage_key: str | None = None
        if recording.processed_audio_path and await storage_backend.exists(recording.processed_audio_path):
            audio_storage_key = recording.processed_audio_path
        elif recording.processed_video_path and await storage_backend.exists(recording.processed_video_path):
            audio_storage_key = recording.processed_video_path
            logger.debug(f"Using processed video for transcription: {audio_storage_key}")
        elif recording.local_video_path and await storage_backend.exists(recording.local_video_path):
            audio_storage_key = recording.local_video_path
            logger.debug(f"Using original video for transcription: {audio_storage_key}")

        if not audio_storage_key:
            raise ValueError("No audio or video file available for transcription")

        task_self.update_progress(user_id, 20, "Loading transcription service...", step="transcribe")

        aai_config = AssemblyAIConfig.from_file("config/assemblyai_creds.json")
        aai_service = AssemblyAITranscriptionService(aai_config)
        aai_model = (aai_config.settings.speech_models or ["universal-2"])[0]

        keyterms = compose_keyterms(vocabulary, recording.display_name)
        if keyterms:
            logger.info(f"Transcription keyterms | count={len(keyterms)} | preview={keyterms[:3]}")
        else:
            logger.info("Transcription keyterms | (none)")

        task_self.update_progress(user_id, 25, "Starting transcription...", step="transcribe")

        # Mark TRANSCRIBE stage as IN_PROGRESS BEFORE actual transcription
        recording.mark_stage_in_progress(ProcessingStageType.TRANSCRIBE)
        logger.info(
            format_status_change("Stage TRANSCRIBE", ProcessingStageStatus.PENDING, ProcessingStageStatus.IN_PROGRESS)
        )
        update_aggregate_status(recording)

        timing_service = TimingService(session)
        timing = await timing_service.start_stage(
            recording_id,
            user_id,
            "TRANSCRIBE",
            meta={"language": language, "model": aai_model},
        )
        await recording_repo.update(recording)
        await session.commit()

        try:
            task_self.update_progress(user_id, 30, "Transcribing audio...", step="transcribe")

            transcription_result = await aai_service.transcribe_audio(
                audio_storage_key=audio_storage_key,
                language=language,
                keyterms=keyterms,
            )

            task_self.update_progress(user_id, 70, "Saving transcription...", step="transcribe")

            transcription_manager = get_transcription_manager()
            user_slug = recording.owner.user_slug
            transcription_dir = transcription_manager.get_dir(recording_id, user_slug)

            words = transcription_result.get("words", [])
            segments = transcription_result.get("segments", [])
            detected_language = transcription_result.get("language", language)

            duration = 0.0
            if segments:
                duration = segments[-1].get("end", 0.0)

            usage_metadata = {
                "model": aai_model,
                "speech_models": aai_config.settings.speech_models,
                "keyterms_count": len(keyterms),
                "config": {
                    "language": language,
                    "detected_language": detected_language,
                    "language_detection": aai_config.settings.language_detection,
                },
                "audio_file": {
                    "path": audio_storage_key,
                    "duration_seconds": duration,
                },
            }

            await transcription_manager.save_master(
                recording_id=recording_id,
                words=words,
                segments=segments,
                language=language,
                model=aai_model,
                duration=duration,
                usage_metadata=usage_metadata,
                user_slug=user_slug,
                raw_response=transcription_result,
            )

            await transcription_manager.generate_cache_files(recording_id, user_slug)

            task_self.update_progress(user_id, 90, "Updating database...", step="transcribe")

            recording.transcription_dir = str(transcription_dir)
            recording.transcription_info = transcription_result
            recording.final_duration = duration or None

            recording.mark_stage_completed(
                ProcessingStageType.TRANSCRIBE,
                meta={"transcription_dir": str(transcription_dir), "language": language, "model": aai_model},
            )

            update_aggregate_status(recording)

            await timing_service.complete_stage(timing, meta={"language": language, "words": len(words)})
            _update_pipeline_completed(recording)

            await recording_repo.update(recording)
            await session.commit()

            logger.success(
                f"Transcription complete | "
                f"{format_details(words=len(words), segments=len(segments), lang=language, elapsed=f'{timing.duration_seconds:.1f}s')}"
            )

            return {
                "success": True,
                "transcription_dir": str(transcription_dir),
                "language": language,
                "words_count": len(words),
                "segments_count": len(segments),
            }

        except Exception as e:
            await timing_service.fail_stage(timing, str(e))
            await session.commit()
            raise


@celery_app.task(
    bind=True,
    base=ProcessingTask,
    name="api.tasks.processing.finalize_pipeline",
    max_retries=0,
)
def _finalize_pipeline_task(self, recording_id: int, user_id: str) -> dict:
    """
    Terminal step appended to every pipeline chain.

    Clears on_air / pipeline_task_id and records pipeline_completed_at so the
    recording lands in a clean "at rest" state regardless of which path the
    chain took. Also updates the aggregate status one final time.
    """
    session_maker = get_async_session_maker()

    async def _finalize():
        async with session_maker() as session:
            repo = RecordingRepository(session)
            rec = await repo.get_by_id(recording_id, user_id)
            if not rec:
                logger.warning(f"finalize_pipeline: recording {recording_id} not found — skipping")
                return
            # If the recording was paused while the pipeline was running, the pause
            # handler already cleared on_air and rolled back status. Running
            # update_aggregate_status here would overwrite that rollback.
            if rec.on_pause:
                logger.info(f"finalize_pipeline: recording {recording_id} is paused — skipping status update")
                rec.on_air = False
                rec.pipeline_task_id = None
                await session.commit()
                return
            rec.on_air = False
            rec.pipeline_task_id = None
            completed_at = datetime.now(UTC)
            rec.pipeline_completed_at = completed_at
            if rec.pipeline_started_at:
                rec.pipeline_duration_seconds = (completed_at - rec.pipeline_started_at).total_seconds()
            update_aggregate_status(rec)
            await session.commit()

    self.run_async(_finalize())
    return self.build_result(user_id=user_id, status="completed", recording_id=recording_id)


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
    from api.tasks.upload import platform_to_target_type, upload_enqueue_skip_reason, upload_recording_to_platform

    # Check pause flag before launching uploads
    session_maker = get_async_session_maker()

    async def _check_pause():
        async with session_maker() as session:
            recording_repo = RecordingRepository(session)
            recording = await recording_repo.get_by_id(recording_id, user_id)
            return recording.on_pause if recording else False

    async def _output_skip_reason(platform: str) -> str | None:
        async with session_maker() as session:
            recording_repo = RecordingRepository(session)
            recording = await recording_repo.get_by_id(recording_id, user_id)
            if not recording:
                return "Recording not found"

            target_type = platform_to_target_type(platform)
            preset_id = preset_map.get(platform)
            output_target = await recording_repo.get_or_create_output_target(
                recording=recording,
                target_type=target_type,
                preset_id=preset_id,
            )
            await session.commit()
            return upload_enqueue_skip_reason(output_target)

    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
    ):
        if self.run_async(_check_pause()):
            logger.info("Skipped: recording paused")
            return self.build_result(
                user_id=user_id,
                status="paused",
                recording_id=recording_id,
                result={"message": "Pipeline paused by user"},
            )

        logger.info(f"Launching uploads | {format_details(platforms=platforms)}")

        upload_task_ids = []
        for platform in platforms:
            try:
                skip_reason = self.run_async(_output_skip_reason(platform))
                if skip_reason:
                    logger.info(f"Upload launch skipped | {format_details(platform=platform, reason=skip_reason)}")
                    upload_task_ids.append(
                        {
                            "platform": platform,
                            "task_id": None,
                            "preset_id": preset_map.get(platform),
                            "status": "skipped",
                            "reason": skip_reason,
                        }
                    )
                    continue

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
                logger.info(
                    f"Upload task launched | {format_details(platform=platform, upload_task=short_task_id(upload_task.id))}"
                )
            except Exception as e:
                logger.error(f"Failed to launch upload | {format_details(platform=platform, error=e)}")

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
    _ctx = logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
    )
    _ctx.__enter__()
    try:
        logger.info("Orchestrating pipeline")

        from api.dependencies import get_async_session_maker
        from api.services.config_utils import resolve_full_config

        manual_override = manual_override or {}
        session_maker = get_async_session_maker()

        # Check pause flag before building pipeline
        async def _check_pause_before_pipeline():
            async with session_maker() as session:
                repo = RecordingRepository(session)
                rec = await repo.get_by_id(recording_id, user_id)
                return rec.on_pause if rec else False

        if self.run_async(_check_pause_before_pipeline()):
            logger.info("Skipped: recording paused")
            return self.build_result(
                user_id=user_id,
                status="paused",
                recording_id=recording_id,
                result={"message": "Pipeline paused by user"},
            )

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

        # Set pipeline_started_at
        async def _set_pipeline_started():
            async with session_maker() as session:
                recording_repo = RecordingRepository(session)
                rec = await recording_repo.get_by_id(recording_id, user_id)
                if rec:
                    rec.pipeline_started_at = datetime.now(UTC)
                    rec.pipeline_completed_at = None
                    rec.pipeline_duration_seconds = None
                    await session.commit()

        self.run_async(_set_pipeline_started())

        # Check blank_record
        if recording.blank_record:
            logger.info(
                f"Skipped: blank record | {format_details(duration=f'{recording.duration}s', size=recording.video_file_size)}"
            )

            async def _mark_skipped():
                async with session_maker() as session:
                    recording_repo = RecordingRepository(session)
                    rec = await recording_repo.get_by_id(recording_id, user_id)
                    if rec:
                        rec.status = ProcessingStatus.SKIPPED
                        rec.failed_reason = "Blank record (too short or too small)"
                        rec.on_air = False
                        rec.pipeline_task_id = None
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
            f"Pipeline config | {format_details(download=download_enabled, trim=trim_enabled, transcribe=transcribe_enabled, topics=extract_topics_enabled, subs=generate_subs_enabled, upload=upload_enabled)}"
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
                logger.debug(f"Added parallel group | {format_details(tasks=len(parallel_after_transcribe))}")
            else:
                # Single task - just append normally
                task_chain.append(parallel_after_transcribe[0])

        if not task_chain:
            logger.warning("No processing steps enabled")

            # Clear on_air since no chain will run _finalize_pipeline_task.
            async def _clear_on_air_no_steps():
                async with session_maker() as session:
                    repo = RecordingRepository(session)
                    rec = await repo.get_by_id(recording_id, user_id)
                    if rec:
                        rec.on_air = False
                        rec.pipeline_task_id = None
                        await session.commit()

            self.run_async(_clear_on_air_no_steps())
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

            logger.debug(f"Added upload launcher | {format_details(platforms=platforms)}")

        # Always append finalize step — clears on_air and records completion time
        task_chain.append(_finalize_pipeline_task.si(recording_id, user_id))

        # Launch chain
        chain_signature = chain(*task_chain)
        chain_result = chain_signature.apply_async()

        # Store the actual chain ID so pause can revoke it
        async def _store_chain_id():
            async with session_maker() as session:
                repo = RecordingRepository(session)
                rec = await repo.get_by_id(recording_id, user_id)
                if rec:
                    rec.pipeline_task_id = chain_result.id
                    await session.commit()

        self.run_async(_store_chain_id())

        logger.info(
            f"Pipeline launched | {format_details(tasks=len(task_chain), chain_id=short_task_id(chain_result.id))}"
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
        logger.error(f"Pipeline orchestration failed: {exc!r}", exc_info=True)
        raise
    finally:
        _ctx.__exit__(None, None, None)


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

    Uses DeepSeek (primary model); failure raises and fails the stage.

    Args:
        recording_id: ID of recording
        user_id: ID of user
        granularity: Extraction mode ("short" | "medium" | "long")
        version_id: ID of version (if None, generated automatically)

    Returns:
        Results of topic extraction
    """
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info("Extracting topics")

            self.update_progress(user_id, 10, "Initializing topic extraction...", step="extract_topics")

            with track_pipeline_stage("extract_topics"):
                result = self.run_async(_async_extract_topics(self, recording_id, user_id, granularity, version_id))

            return self.build_result(
                user_id=user_id,
                status="completed",
                recording_id=recording_id,
                result=result,
            )

        except SoftTimeLimitExceeded:
            logger.error("Soft time limit exceeded")
            raise self.retry(countdown=600, exc=SoftTimeLimitExceeded())

        except Exception as exc:
            logger.error(f"Error extracting topics: {exc!r}", exc_info=True)
            raise self.retry(exc=exc)


async def _async_extract_topics(
    task_self, recording_id: int, user_id: str, granularity: str, version_id: str | None
) -> dict:
    """Async function for extracting topics via DeepSeek. Failure raises — no fallback."""
    session_maker = get_async_session_maker()

    async with session_maker() as session:
        recording_repo = RecordingRepository(session)

        recording = await recording_repo.get_by_id(recording_id, user_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found for user {user_id}")

        # Check pause flag before starting
        if recording.on_pause:
            logger.info("Skipped: recording paused")
            return {"status": "paused", "message": "Pipeline paused by user"}

        # Idempotency: skip if topics already extracted successfully
        topics_stage = next(
            (s for s in recording.processing_stages if s.stage_type == ProcessingStageType.EXTRACT_TOPICS), None
        )
        if topics_stage and topics_stage.status == ProcessingStageStatus.COMPLETED:
            logger.info("Skipped: topic extraction already completed")
            return {"status": "skipped", "reason": "already_completed"}

        # Get user_slug for path generation
        user_slug = recording.owner.user_slug

        # Check presence of transcription
        transcription_manager = get_transcription_manager()
        if not await transcription_manager.has_master(recording_id, user_slug):
            raise ValueError(f"Transcription not found for recording {recording_id}. Please run transcription first.")

        task_self.update_progress(user_id, 20, "Loading transcription...", step="extract_topics")

        # Ensure segments.txt exists in storage, then materialize it for DeepSeek (requires local path).
        from file_storage.factory import get_storage_backend
        from file_storage.path_builder import StoragePathBuilder

        storage_backend = get_storage_backend()
        storage_builder = StoragePathBuilder()

        segments_key = await transcription_manager.ensure_segments_txt(recording_id, user_slug)
        segments_path = storage_builder.create_temp_file(prefix="segments_", suffix=".txt")
        await storage_backend.download_to_file(segments_key, segments_path)

        # Get language from master.json (from transcription)
        master = await transcription_manager.load_master(recording_id, user_slug)
        transcript_language = master.get("language") or "ru"

        # Get questions_count from resolved config (transcription.questions_count, default 3)
        from api.services.config_utils import resolve_full_config

        full_config, _ = await resolve_full_config(session, recording_id, user_id, None)
        transcription_config = full_config.get("transcription", {})
        questions_count = max(1, min(10, int(transcription_config.get("questions_count", 3))))

        task_self.update_progress(user_id, 30, "Starting topic extraction...", step="extract_topics")

        # Mark EXTRACT_TOPICS stage as IN_PROGRESS BEFORE extraction
        from api.helpers.status_manager import update_aggregate_status

        recording.mark_stage_in_progress(ProcessingStageType.EXTRACT_TOPICS)
        logger.info(
            format_status_change(
                "Stage EXTRACT_TOPICS", ProcessingStageStatus.PENDING, ProcessingStageStatus.IN_PROGRESS
            )
        )
        update_aggregate_status(recording)

        timing_service = TimingService(session)
        timing = await timing_service.start_stage(recording_id, user_id, "EXTRACT_TOPICS")
        await recording_repo.update(recording)
        await session.commit()

        try:
            logger.info("Topics: extracting via DeepSeek")
            task_self.update_progress(user_id, 40, "Extracting topics (deepseek)...", step="extract_topics")

            deepseek_config = DeepSeekConfig.from_file("config/deepseek_creds.json")
            topic_extractor = TopicExtractor(deepseek_config)

            topics_result = await topic_extractor.extract_topics_from_file(
                segments_file_path=str(segments_path),
                recording_topic=recording.display_name,
                granularity=granularity,
                language=transcript_language,
                questions_count=questions_count,
            )
            model_used = "deepseek"
            logger.info("Topics extracted with deepseek")

            if not topics_result:
                raise ValueError("Failed to extract topics: no result returned")

            task_self.update_progress(user_id, 80, "Saving topics...", step="extract_topics")

            # Generate version_id if not specified
            if not version_id:
                version_id = await transcription_manager.generate_version_id(recording_id, user_slug)

            # Collect metadata for admin (includes token usage if API returned it)
            usage_metadata = {
                "model": model_used,
                "config": {
                    "temperature": deepseek_config.temperature,
                    "max_tokens": deepseek_config.max_tokens,
                },
            }
            if topics_result.get("usage"):
                usage_metadata["tokens"] = topics_result["usage"]

            # Save in extracted.json (topics + summary + questions from single DeepSeek call)
            summary_value = topics_result.get("summary", "") or ""
            await transcription_manager.add_extracted_version(
                recording_id=recording_id,
                version_id=version_id,
                model=model_used,
                granularity=granularity,
                main_topics=topics_result.get("main_topics", []),
                topic_timestamps=topics_result.get("topic_timestamps", []),
                pauses=topics_result.get("long_pauses", []),
                summary=summary_value,
                questions=topics_result.get("questions", []),
                is_active=True,
                usage_metadata=usage_metadata,
                user_slug=user_slug,
            )

            # Clean up local segments temp file used by DeepSeek.
            segments_path.unlink(missing_ok=True)

            # Update recording in DB (active version)
            recording.topic_timestamps = topics_result.get("topic_timestamps", [])
            recording.main_topics = topics_result.get("main_topics", [])

            # Mark topic extraction stage as completed
            recording.mark_stage_completed(
                ProcessingStageType.EXTRACT_TOPICS,
                meta={"version_id": version_id, "granularity": granularity, "model": model_used},
            )

            update_aggregate_status(recording)

            await timing_service.complete_stage(timing, meta={"model": model_used, "granularity": granularity})
            _update_pipeline_completed(recording)

            await recording_repo.update(recording)
            await session.commit()

            topics_count = len(topics_result.get("topic_timestamps", []))
            logger.success(
                f"Topics extracted | {format_details(model=model_used, topics=topics_count, elapsed=f'{timing.duration_seconds:.1f}s')}"
            )

            return {
                "success": True,
                "version_id": version_id,
                "topics_count": topics_count,
                "main_topics": topics_result.get("main_topics", []),
            }

        except Exception as e:
            await timing_service.fail_stage(timing, str(e))
            await session.commit()
            raise


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
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info("Generating subtitles")

            formats = formats or ["srt", "vtt"]

            self.update_progress(user_id, 20, "Initializing subtitle generation...", step="generate_subtitles")

            with track_pipeline_stage("generate_subtitles"):
                result = self.run_async(_async_generate_subtitles(self, recording_id, user_id, formats))

            return self.build_result(
                user_id=user_id,
                status="completed",
                recording_id=recording_id,
                result=result,
            )

        except Exception as exc:
            logger.error(f"Error generating subtitles: {exc!r}", exc_info=True)
            raise self.retry(exc=exc)


async def _async_generate_subtitles(task_self, recording_id: int, user_id: str, formats: list[str]) -> dict:
    """Async function for generating subtitles."""
    session_maker = get_async_session_maker()

    async with session_maker() as session:
        recording_repo = RecordingRepository(session)

        recording = await recording_repo.get_by_id(recording_id, user_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found for user {user_id}")

        # Check pause flag before starting
        if recording.on_pause:
            logger.info("Skipped: recording paused")
            return {"status": "paused", "message": "Pipeline paused by user"}

        # Idempotency: skip if subtitles already generated successfully
        subs_stage = next(
            (s for s in recording.processing_stages if s.stage_type == ProcessingStageType.GENERATE_SUBTITLES), None
        )
        if subs_stage and subs_stage.status == ProcessingStageStatus.COMPLETED:
            logger.info("Skipped: subtitle generation already completed")
            return {"status": "skipped", "reason": "already_completed"}

        # Get user_slug for path generation
        user_slug = recording.owner.user_slug

        # Check presence of transcription
        transcription_manager = get_transcription_manager()
        if not await transcription_manager.has_master(recording_id, user_slug):
            raise ValueError(f"Transcription not found for recording {recording_id}. Please run transcription first.")

        task_self.update_progress(user_id, 30, "Starting subtitle generation...", step="generate_subtitles")

        # Mark GENERATE_SUBTITLES stage as IN_PROGRESS BEFORE generation
        from api.helpers.status_manager import update_aggregate_status

        recording.mark_stage_in_progress(ProcessingStageType.GENERATE_SUBTITLES)
        logger.info(
            format_status_change("Stage SUBTITLES", ProcessingStageStatus.PENDING, ProcessingStageStatus.IN_PROGRESS)
        )
        update_aggregate_status(recording)

        timing_service = TimingService(session)
        timing = await timing_service.start_stage(recording_id, user_id, "GENERATE_SUBTITLES")
        await recording_repo.update(recording)
        await session.commit()

        try:
            task_self.update_progress(user_id, 40, "Generating subtitles...", step="generate_subtitles")

            # Generate subtitles (returns storage keys, not local paths)
            subtitle_paths = await transcription_manager.generate_subtitles(
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

            update_aggregate_status(recording)

            await timing_service.complete_stage(timing, meta={"formats": formats})
            _update_pipeline_completed(recording)

            await recording_repo.update(recording)
            await session.commit()

            logger.info(
                f"{format_status_change('Stage SUBTITLES', ProcessingStageStatus.IN_PROGRESS, ProcessingStageStatus.COMPLETED)}"
                f" | {format_details(formats=formats, elapsed=f'{timing.duration_seconds:.1f}s')}"
            )

            return {
                "success": True,
                "formats": formats,
                "files": subtitle_paths,
            }

        except Exception as e:
            await timing_service.fail_stage(timing, str(e))
            await session.commit()
            raise
