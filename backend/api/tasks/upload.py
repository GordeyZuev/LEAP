"""Celery tasks for uploading videos with multi-tenancy support."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from api.celery_app import celery_app
from api.core.context import ServiceContext
from api.dependencies import get_async_session_maker
from api.helpers.template_renderer import TemplateRenderer, render_jinja, render_upload_title_and_description
from api.observability import track_pipeline_stage
from api.repositories.auth_repos import UserCredentialRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import OutputPresetRepository, RecordingTemplateRepository
from api.services.config_resolver import ConfigResolver
from api.services.timing_service import TimingService
from api.shared.exceptions import CredentialError, ResourceNotFoundError
from api.tasks.base import UploadTask
from config.settings import get_settings
from database.template_models import OutputPresetModel
from logger import format_details, format_status_change, get_logger, short_task_id, short_user_id
from models.recording import TargetStatus
from utils.thumbnail_manager import get_thumbnail_manager
from video_upload_module.platforms.youtube.token_handler import TokenRefreshError
from video_upload_module.uploader_factory import create_uploader_from_db

logger = get_logger()
settings = get_settings()

_UPLOAD_STALE_BUFFER_SECONDS = 300


def _vk_upload_params_from_metadata(preset_metadata: dict[str, Any]) -> dict[str, Any]:
    """Build VK video.save kwargs from flat or nested ``metadata_config.vk`` fields."""
    vk_block = preset_metadata.get("vk")
    if not isinstance(vk_block, dict):
        vk_block = {}

    params: dict[str, Any] = {}
    for key in ("group_id", "privacy_view", "privacy_comment", "repeat", "wallpost", "compression"):
        if key in preset_metadata:
            params[key] = preset_metadata[key]
        elif key in vk_block:
            params[key] = vk_block[key]

    if "no_comments" in preset_metadata:
        params["no_comments"] = preset_metadata["no_comments"]
    elif "disable_comments" in preset_metadata:
        params["no_comments"] = preset_metadata["disable_comments"]
    elif "no_comments" in vk_block:
        params["no_comments"] = vk_block["no_comments"]
    elif "disable_comments" in vk_block:
        params["no_comments"] = vk_block["disable_comments"]

    return params


def platform_to_target_type(platform: str) -> str:
    """Map API platform name to output target type."""
    target_type_map = {
        "youtube": "YOUTUBE",
        "vk": "VK",
        "vk_video": "VK",
        "yandex_disk": "YANDEX_DISK",
    }
    return target_type_map.get(platform.lower(), platform.upper())


def upload_enqueue_skip_reason(
    output_target,
    *,
    now: datetime | None = None,
    allow_active_upload: bool = False,
) -> str | None:
    if output_target.status == TargetStatus.UPLOADED and output_target.target_meta:
        if output_target.target_meta.get("video_id"):
            return "Already uploaded"

    if output_target.status != TargetStatus.UPLOADING:
        return None

    if allow_active_upload:
        return None

    if not output_target.started_at:
        return "Upload in progress"

    started = output_target.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)

    now = now or datetime.now(UTC)
    stale_after = settings.celery.task_time_limit + _UPLOAD_STALE_BUFFER_SECONDS
    if (now - started).total_seconds() < stale_after:
        return "Upload in progress"

    return None


def _upload_skip_result(output_target, reason: str) -> dict:
    if reason == "Already uploaded":
        return {
            "success": True,
            "video_id": output_target.target_meta.get("video_id"),
            "video_url": output_target.target_meta.get("video_url"),
            "skipped": True,
            "reason": reason,
        }
    return {"success": True, "skipped": True, "reason": reason}


# Platform limits (API constraints)
# vk_video is normalized to vk for lookup
TITLE_MAX_LENGTH: dict[str, int] = {
    "youtube": 100,
    "vk": 128,
}
DESCRIPTION_MAX_LENGTH: dict[str, int] = {
    "youtube": 5000,
    "vk": 5000,
}

ELLIPSIS = "..."


def _platform_key(platform: str) -> str:
    """Normalize platform for limit lookup (vk_video -> vk)."""
    p = platform.lower()
    return "vk" if p == "vk_video" else p


def _truncate_with_ellipsis(text: str, max_len: int, suffix: str = ELLIPSIS) -> str:
    """Truncate text to max_len, appending suffix if needed."""
    if len(text) <= max_len:
        return text
    if max_len <= len(suffix):
        return text[:max_len]
    return text[: max_len - len(suffix)] + suffix


def _truncate_title_for_platform(title: str, platform: str) -> str:
    """Truncate title to platform limit."""
    max_len = TITLE_MAX_LENGTH.get(_platform_key(platform))
    if max_len is None:
        return title
    return _truncate_with_ellipsis(title, max_len)


def _truncate_description_for_platform(description: str, platform: str) -> str:
    """Truncate description to platform limit."""
    max_len = DESCRIPTION_MAX_LENGTH.get(_platform_key(platform))
    if max_len is None:
        return description
    return _truncate_with_ellipsis(description, max_len)


def _yandex_extra_cfg_as_dict(cfg: object) -> dict:
    if cfg is None:
        return {}
    if isinstance(cfg, dict):
        return cfg
    model_dump = getattr(cfg, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {}


async def _upload_extra_files_to_yadisk(
    oauth_token: str | None,
    recording_id: int,
    user_slug: int,
    video_folder_path: str,
    video_base_name: str,
    preset_metadata: dict,
    template_context: dict,
    rendered_description: str,
    *,
    overwrite: bool = False,
) -> None:
    """Best-effort upload of sidecar files (subtitles, transcription, description) to Yandex Disk."""
    if not oauth_token:
        logger.warning(
            "Yandex Disk extra files skipped: no oauth_token (video upload already done; "
            "re-link preset credential or check YandexDiskUploader.oauth_token)"
        )
        return

    from tempfile import NamedTemporaryFile

    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import StoragePathBuilder
    from transcription_module.manager import get_transcription_manager
    from yandex_disk_module.client import YandexDiskClient, YandexDiskError

    client = YandexDiskClient(oauth_token=oauth_token)
    tm = get_transcription_manager()
    storage = get_storage_backend()
    storage_builder = StoragePathBuilder()

    async def _upload_one_local(local: Path, disk_folder: str, filename: str) -> None:
        disk_path = f"{disk_folder.rstrip('/')}/{filename}"
        try:
            await client.upload_file(local, disk_path=disk_path, overwrite=overwrite)
            logger.info(f"Yandex Disk extra file uploaded | {format_details(path=disk_path)}")
        except (YandexDiskError, OSError, FileNotFoundError) as e:
            logger.warning(f"Yandex Disk extra file failed | {format_details(path=disk_path, error=str(e))}")

    async def _upload_storage_key(storage_key: str, disk_folder: str, filename: str, suffix: str) -> None:
        """Materialize a storage key to a temp file and upload it, then clean up."""
        tmp = storage_builder.create_temp_file(prefix="yadisk_extra_", suffix=suffix)
        try:
            await storage.download_to_file(storage_key, tmp)
            await _upload_one_local(tmp, disk_folder, filename)
        finally:
            tmp.unlink(missing_ok=True)

    for key, ext, fmt in (
        ("subtitles_srt", ".srt", "srt"),
        ("subtitles_vtt", ".vtt", "vtt"),
    ):
        if preset_metadata.get(key) is None:
            continue
        cfg = _yandex_extra_cfg_as_dict(preset_metadata.get(key))
        folder_t = cfg.get("folder_path_template")
        folder = render_jinja(folder_t, template_context) if folder_t else video_folder_path
        fn_t = cfg.get("filename_template")
        filename = render_jinja(fn_t, template_context) if fn_t else f"{video_base_name}{ext}"
        try:
            paths = await tm.generate_subtitles(recording_id, [fmt], user_slug)
            await _upload_storage_key(paths[fmt], folder, filename, suffix=ext)
        except Exception as e:
            logger.warning(f"Yandex Disk {key} skipped | {format_details(error=str(e))}")

    if preset_metadata.get("transcription") is not None:
        cfg = _yandex_extra_cfg_as_dict(preset_metadata.get("transcription"))
        folder_t = cfg.get("folder_path_template")
        folder = render_jinja(folder_t, template_context) if folder_t else video_folder_path
        fn_t = cfg.get("filename_template")
        filename = render_jinja(fn_t, template_context) if fn_t else f"{video_base_name}_transcription.txt"
        try:
            segments_key = await tm.ensure_segments_txt(recording_id, user_slug)
            await _upload_storage_key(segments_key, folder, filename, suffix=".txt")
        except Exception as e:
            logger.warning(f"Yandex Disk transcription skipped | {format_details(error=str(e))}")

    if preset_metadata.get("description_txt") is not None:
        cfg = _yandex_extra_cfg_as_dict(preset_metadata.get("description_txt"))
        folder_t = cfg.get("folder_path_template")
        folder = render_jinja(folder_t, template_context) if folder_t else video_folder_path
        fn_t = cfg.get("filename_template")
        filename = render_jinja(fn_t, template_context) if fn_t else f"{video_base_name}_description.txt"
        ct = cfg.get("content_template")
        content = render_jinja(ct, template_context) if ct else rendered_description
        tmp_path: Path | None = None
        try:
            with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            await _upload_one_local(tmp_path, folder, filename)
        except Exception as e:
            logger.warning(f"Yandex Disk description_txt skipped | {format_details(error=str(e))}")
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)


@celery_app.task(
    bind=True,
    base=UploadTask,
    name="api.tasks.upload.upload_recording_to_platform",
    max_retries=settings.celery.upload_max_retries,
    default_retry_delay=settings.celery.upload_retry_delay,
)
def upload_recording_to_platform(
    self,
    recording_id: int,
    user_id: str,
    platform: str,
    preset_id: int | None = None,
    credential_id: int | None = None,
    metadata_override: dict | None = None,
) -> dict:
    """
    Upload one recording to platform with user credentials.

    Args:
        recording_id: ID of recording
        user_id: ID of user
        platform: Platform (youtube, vk)
        preset_id: ID of output preset (optional)
        credential_id: ID of credential (optional)
        metadata_override: Override for preset metadata (playlist_id, album_id, etc.)

    Returns:
        Dictionary with upload results
    """
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        recording_id=recording_id,
        user_id=short_user_id(user_id),
        platform=platform,
    ):
        try:
            logger.info(f"Uploading | {format_details(metadata_override=bool(metadata_override))}")

            with track_pipeline_stage("upload", platform=platform):
                result = self.run_async(
                    _async_upload_recording(
                        recording_id=recording_id,
                        user_id=user_id,
                        platform=platform,
                        preset_id=preset_id,
                        credential_id=credential_id,
                        metadata_override=metadata_override,
                        allow_active_upload=self.request.retries > 0,
                    )
                )

            return self.build_result(
                user_id=user_id,
                status="completed",
                recording_id=recording_id,
                platform=platform,
                result=result,
            )

        except SoftTimeLimitExceeded:
            logger.error("Soft time limit exceeded")
            raise self.retry(countdown=900, exc=SoftTimeLimitExceeded())

        except TokenRefreshError as exc:
            logger.error("Token refresh failed - re-authentication needed")
            return self.build_result(
                user_id=user_id,
                status="failed",
                recording_id=recording_id,
                platform=exc.platform,
                error="token_refresh_error",
                reason="Token refresh failed. Please re-authenticate via OAuth.",
            )

        except CredentialError as exc:
            logger.error(f"Credential error: {exc.reason}")
            return self.build_result(
                user_id=user_id,
                status="failed",
                recording_id=recording_id,
                platform=platform,
                error="credential_error",
                reason=exc.reason,
            )

        except ResourceNotFoundError as exc:
            logger.error(f"Resource not found | {format_details(type=exc.resource_type, id=exc.resource_id)}")
            return self.build_result(
                user_id=user_id,
                status="failed",
                recording_id=recording_id,
                platform=platform,
                error="resource_not_found",
                resource_type=exc.resource_type,
                resource_id=exc.resource_id,
            )

        except Exception as exc:
            logger.error(f"Unexpected error: {type(exc).__name__}: {exc}", exc_info=True)
            raise self.retry(exc=exc)


async def _async_upload_recording(
    recording_id: int,
    user_id: str,
    platform: str,
    preset_id: int | None = None,
    credential_id: int | None = None,
    metadata_override: dict | None = None,
    allow_active_upload: bool = False,
) -> dict:
    """
    Async function for uploading recording.

    Args:
        recording_id: ID of recording
        user_id: ID of user (all DB queries filtered by this)
        platform: Target platform (youtube, vk, vk_video, yandex_disk)
        preset_id: ID of output preset (optional)
        credential_id: ID of credential (optional)
        metadata_override: Override for preset metadata (optional)

    Returns:
        Upload results (success, video_id, video_url, metadata)
    """
    session_maker = get_async_session_maker()

    async with session_maker() as session:
        ctx = ServiceContext.create(session=session, user_id=user_id)
        recording_repo = RecordingRepository(session)

        recording = await recording_repo.get_by_id(recording_id, user_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found for user {user_id}")

        # Check pause flag before starting upload
        if recording.on_pause:
            logger.info("Skipped: recording paused")
            return {"status": "paused", "message": "Pipeline paused by user"}

        target_type = platform_to_target_type(platform)

        output_target = await recording_repo.get_or_create_output_target(
            recording=recording,
            target_type=target_type,
            preset_id=preset_id,
        )

        skip_reason = upload_enqueue_skip_reason(output_target, allow_active_upload=allow_active_upload)
        if skip_reason:
            logger.info(f"Skipped: {skip_reason.lower()}")
            return _upload_skip_result(output_target, skip_reason)

        # Check video file exists BEFORE marking as uploading
        if not recording.processed_video_path:
            raise ResourceNotFoundError("processed video", recording_id)

        from file_storage.factory import get_storage_backend
        from file_storage.path_builder import StoragePathBuilder

        storage_backend = get_storage_backend()
        storage_builder = StoragePathBuilder()
        video_storage_key = recording.processed_video_path
        if not await storage_backend.exists(video_storage_key):
            raise ResourceNotFoundError("video file", video_storage_key)

        # Materialize the processed video to a local temp file for platform SDKs
        # (YouTube/VK/YaDisk all require a local file). Cleaned up in finally.
        _local_temps: list[Path] = []
        video_temp = storage_builder.create_temp_file(
            prefix=f"upload_{recording_id}_", suffix=Path(video_storage_key).suffix or ".mp4"
        )
        await storage_backend.download_to_file(video_storage_key, video_temp)
        _local_temps.append(video_temp)
        video_path = str(video_temp)

        async def _resolve_thumbnail_to_temp(user_slug: int, filename: str) -> Path | None:
            """Resolve a thumbnail name to a local temp file and register cleanup."""
            tm = get_thumbnail_manager()
            key = await tm.get_thumbnail_key(user_slug=user_slug, thumbnail_name=filename, fallback_to_template=True)
            if key is None:
                return None
            tmp = storage_builder.create_temp_file(prefix="thumb_", suffix=Path(filename).suffix or ".jpg")
            await storage_backend.download_to_file(key, tmp)
            _local_temps.append(tmp)
            return tmp

        preset_metadata = {}
        preset = None
        effective_credential_id: int | None = None

        if not preset_id and recording.template_id:
            template_repo = RecordingTemplateRepository(ctx.session)
            template = await template_repo.find_by_id(recording.template_id, user_id)

            if template and template.output_config:
                preset_ids = template.output_config.get("preset_ids", [])
                if preset_ids:
                    stmt = select(OutputPresetModel).where(
                        OutputPresetModel.id.in_(preset_ids),
                        OutputPresetModel.user_id == user_id,
                    )
                    result = await ctx.session.execute(stmt)
                    presets = result.scalars().all()

                    for candidate_preset in presets:
                        if candidate_preset.platform.lower() == platform.lower():
                            preset_id = candidate_preset.id
                            logger.info(f"Auto-selected preset | {format_details(preset=preset_id)}")
                            break

        if preset_id:
            preset_repo = OutputPresetRepository(ctx.session)
            preset = await preset_repo.find_by_id(preset_id, user_id)

            if not preset:
                raise ValueError(f"Output preset {preset_id} not found for user {user_id}")

            if not preset.credential_id:
                raise ValueError(f"Output preset {preset_id} has no credential configured")

            config_resolver = ConfigResolver(ctx.session)
            preset_metadata = await config_resolver.resolve_upload_metadata(
                recording=recording, user_id=user_id, preset_id=preset.id
            )

            if metadata_override:
                preset_metadata = config_resolver._merge_configs(preset_metadata, metadata_override)

            platform_map = {
                "YOUTUBE": "youtube",
                "VK": "vk_video",
                "VK_VIDEO": "vk_video",
                "YANDEX_DISK": "yandex_disk",
            }
            mapped_platform = platform_map.get(preset.platform.upper(), preset.platform.lower())

            effective_credential_id = preset.credential_id
            uploader = await create_uploader_from_db(
                platform=mapped_platform,
                credential_id=preset.credential_id,
                session=ctx.session,
            )
        elif credential_id:
            effective_credential_id = credential_id
            uploader = await create_uploader_from_db(
                platform=platform,
                credential_id=credential_id,
                session=ctx.session,
            )
        else:
            cred_repo = UserCredentialRepository(ctx.session)
            credentials = await cred_repo.list_by_platform(user_id, platform)

            if not credentials:
                raise ValueError(f"No credentials found for platform {platform}")

            effective_credential_id = credentials[0].id
            uploader = await create_uploader_from_db(
                platform=platform,
                credential_id=credentials[0].id,
                session=ctx.session,
            )

        topics_display = preset_metadata.get("topics_display") if preset_metadata else None
        questions_display = preset_metadata.get("questions_display") if preset_metadata else None

        # Pre-load active extraction (summary/questions) from storage; the sync
        # prepare_recording_context can no longer touch the async TranscriptionManager.
        owner = getattr(recording, "owner", None)
        extracted_active: dict | None = None
        if owner is not None and getattr(owner, "user_slug", None) is not None:
            try:
                from transcription_module.manager import get_transcription_manager

                extracted_active = await get_transcription_manager().get_active_extracted(recording.id, owner.user_slug)
            except Exception as exc:
                logger.debug(f"Could not load extracted for template context: {exc}")

        template_context = TemplateRenderer.prepare_recording_context(
            recording,
            topics_display=topics_display,
            questions_display=questions_display,
            extracted_data=extracted_active,
        )

        cred_repo = UserCredentialRepository(ctx.session)

        try:
            auth_success = await uploader.authenticate()
            if not auth_success:
                raise CredentialError(
                    platform=platform,
                    reason="Token validation failed or expired. Please re-authenticate via OAuth.",
                )

            if effective_credential_id:
                await cred_repo.update_last_used(effective_credential_id)
                await cred_repo.set_needs_reauth(effective_credential_id, False)

            title_template = preset_metadata.get("title_template", "{{ display_name }}")
            description_template = preset_metadata.get("description_template", "Uploaded on {{ record_date_iso }}")

            title, description = render_upload_title_and_description(
                title_template, description_template, template_context
            )

            if not title:
                logger.warning("Title is empty, using fallback")
                title = recording.display_name or "Recording"
            if not description:
                logger.warning("Description is empty, using fallback")
                fallback_desc = render_jinja("Uploaded on {{ record_date_iso }}", template_context)
                description = fallback_desc or "Uploaded"
                topics_for_fallback: list[Any] = []
                tts = getattr(recording, "topic_timestamps", None)
                if tts and isinstance(tts, (list, tuple)):
                    topics_for_fallback = list(tts)
                elif recording.main_topics:
                    mt = recording.main_topics
                    topics_for_fallback = list(mt) if isinstance(mt, (list, tuple)) else [mt]
                if topics_for_fallback:
                    if topics_display and topics_display.get("enabled", True):
                        topics_str = TemplateRenderer._format_topics_list(topics_for_fallback, topics_display)
                    else:
                        topics_str = ", ".join(
                            str(t.get("topic", t) if isinstance(t, dict) else t) for t in topics_for_fallback[:5]
                        )
                    description += f"\n\n{topics_str}"
                if questions_display and questions_display.get("enabled") and template_context.get("questions"):
                    description += f"\n\n{template_context['questions']}"

            original_title_len = len(title)
            title = _truncate_title_for_platform(title, platform)
            if len(title) < original_title_len:
                logger.info(f"Title truncated from {original_title_len} to {len(title)} chars for {platform}")

            original_desc_len = len(description)
            description = _truncate_description_for_platform(description, platform)
            if len(description) < original_desc_len:
                logger.info(
                    f"Description truncated from {original_desc_len} to {len(description)} chars for {platform}"
                )

            upload_params = {
                "video_path": video_path,
                "title": title,
                "description": description,
            }

            if platform.lower() in ["youtube"]:
                if "tags" in preset_metadata:
                    upload_params["tags"] = preset_metadata["tags"]

                if "category_id" in preset_metadata and preset_metadata["category_id"] is not None:
                    upload_params["category_id"] = preset_metadata["category_id"]

                if "privacy" in preset_metadata:
                    upload_params["privacy_status"] = preset_metadata["privacy"]

                playlist_id = preset_metadata.get("playlist_id") or preset_metadata.get("youtube", {}).get(
                    "playlist_id"
                )
                if playlist_id:
                    upload_params["playlist_id"] = playlist_id

                if "publish_at" in preset_metadata:
                    upload_params["publish_at"] = preset_metadata["publish_at"]

                thumbnail_filename = preset_metadata.get("youtube", {}).get("thumbnail_name") or preset_metadata.get(
                    "thumbnail_name"
                )
                if thumbnail_filename:
                    thumb_local = await _resolve_thumbnail_to_temp(recording.owner.user_slug, thumbnail_filename)
                    if thumb_local is not None:
                        upload_params["thumbnail_path"] = str(thumb_local)
                    else:
                        logger.warning(f"Thumbnail not found: '{thumbnail_filename}'")

                for key in ["made_for_kids", "embeddable", "license", "public_stats_viewable"]:
                    if key in preset_metadata:
                        upload_params[key] = preset_metadata[key]

            elif platform.lower() in ["vk", "vk_video"]:
                album_id = preset_metadata.get("album_id") or preset_metadata.get("vk", {}).get("album_id")
                if album_id:
                    upload_params["album_id"] = str(album_id)

                thumbnail_filename = preset_metadata.get("vk", {}).get("thumbnail_name") or preset_metadata.get(
                    "thumbnail_name"
                )
                if thumbnail_filename:
                    thumb_local = await _resolve_thumbnail_to_temp(recording.owner.user_slug, thumbnail_filename)
                    if thumb_local is not None:
                        upload_params["thumbnail_path"] = str(thumb_local)
                    else:
                        logger.warning(f"Thumbnail not found: '{thumbnail_filename}'")
                else:
                    logger.debug("No thumbnail_name found in metadata")

                upload_params.update(_vk_upload_params_from_metadata(preset_metadata))

            elif platform.lower() == "yandex_disk":
                # Resolve folder path template
                folder_path_template = preset_metadata.get("yandex_disk", {}).get(
                    "folder_path_template"
                ) or preset_metadata.get("folder_path_template", "/Video/Uploads")
                folder_path = render_jinja(folder_path_template, template_context)
                upload_params["folder_path"] = folder_path

                filename_template = preset_metadata.get("yandex_disk", {}).get(
                    "filename_template"
                ) or preset_metadata.get("filename_template")
                if filename_template:
                    filename = render_jinja(filename_template, template_context)
                    upload_params["filename"] = filename

                yd_block = preset_metadata.get("yandex_disk") or {}
                if "overwrite" in yd_block:
                    upload_params["overwrite"] = yd_block["overwrite"]
                elif "overwrite" in preset_metadata:
                    upload_params["overwrite"] = preset_metadata["overwrite"]

                if "publish" in yd_block:
                    upload_params["publish"] = bool(yd_block["publish"])
                elif preset_metadata.get("publish") is True:
                    upload_params["publish"] = True

            timing_service = TimingService(session)
            stage_name = f"UPLOAD:{target_type}"
            timing = await timing_service.start_stage(recording_id, user_id, stage_name)

            await session.refresh(output_target)
            skip_reason = upload_enqueue_skip_reason(output_target, allow_active_upload=allow_active_upload)
            if skip_reason:
                logger.info(f"Skipped before upload start: {skip_reason.lower()}")
                return _upload_skip_result(output_target, skip_reason)

            old_status = output_target.status
            output_target.started_at = datetime.now(UTC)
            await recording_repo.mark_output_uploading(output_target)
            logger.info(format_status_change("Output", old_status, TargetStatus.UPLOADING))
            await session.commit()

            upload_result = await uploader.upload_video(**upload_params)

            if not upload_result or upload_result.error_message:
                error_message = upload_result.error_message if upload_result else "Unknown error"
                await timing_service.fail_stage(timing, f"Upload failed: {error_message}")
                await session.commit()
                raise Exception(f"Upload failed: {error_message}")

            await recording_repo.save_upload_result(
                recording=recording,
                target_type=target_type,
                preset_id=preset_id,
                video_id=upload_result.video_id,
                video_url=upload_result.video_url,
                target_meta={
                    "platform": platform,
                    "uploaded_by_task": True,
                    # Thumbnail metadata
                    "thumbnail_set": (upload_result.metadata or {}).get("thumbnail_set"),
                    "thumbnail_error": (upload_result.metadata or {}).get("thumbnail_error"),
                    # YouTube playlist metadata
                    "playlist_id": (upload_result.metadata or {}).get("playlist_id"),
                    "added_to_playlist": (upload_result.metadata or {}).get("added_to_playlist"),
                    "playlist_error": (upload_result.metadata or {}).get("playlist_error"),
                    # VK album metadata
                    "album_id": (upload_result.metadata or {}).get("album_id"),
                    "added_to_album": (upload_result.metadata or {}).get("added_to_album"),
                    "owner_id": (upload_result.metadata or {}).get("owner_id"),
                },
            )

            await timing_service.complete_stage(timing, meta={"platform": platform})

            if platform.lower() == "yandex_disk" and any(
                preset_metadata.get(k) is not None
                for k in ("subtitles_srt", "subtitles_vtt", "transcription", "description_txt")
            ):
                try:
                    owner = recording.owner
                    if owner is None:
                        logger.warning("Yandex Disk extra files skipped: recording has no owner")
                    else:
                        video_base = (
                            Path(upload_params["filename"]).stem
                            if upload_params.get("filename")
                            else Path(video_path).stem
                        )
                        yd_oauth = getattr(uploader, "oauth_token", None) or (
                            (getattr(uploader, "credentials_data", None) or {}).get("oauth_token")
                        )
                        await _upload_extra_files_to_yadisk(
                            oauth_token=yd_oauth,
                            recording_id=recording_id,
                            user_slug=owner.user_slug,
                            video_folder_path=upload_params["folder_path"],
                            video_base_name=video_base,
                            preset_metadata=preset_metadata,
                            template_context=template_context,
                            rendered_description=description,
                            overwrite=bool(upload_params.get("overwrite", False)),
                        )
                except Exception as e:
                    logger.warning(f"Yandex Disk extra files batch failed (non-fatal): {e}")

            # Update pipeline timing
            now = datetime.now(UTC)
            recording.pipeline_completed_at = now
            if recording.pipeline_started_at:
                recording.pipeline_duration_seconds = (now - recording.pipeline_started_at).total_seconds()

            await session.commit()

            logger.success(
                f"Upload complete | {format_details(url=upload_result.video_url, video_id=upload_result.video_id, elapsed=f'{timing.duration_seconds:.1f}s')}"
            )

            return {
                "success": True,
                "video_id": upload_result.video_id,
                "video_url": upload_result.video_url,
                "metadata": upload_result.metadata,
            }

        except (TokenRefreshError, CredentialError):
            if effective_credential_id:
                try:
                    await cred_repo.set_needs_reauth(effective_credential_id, True)
                except Exception as _err:
                    logger.debug(f"Failed to set needs_reauth on credential {effective_credential_id}: {_err}")
            raise
        except Exception as e:
            if "timing" in locals() and timing.status == "IN_PROGRESS":
                try:
                    await timing_service.fail_stage(timing, str(e))
                    await session.commit()
                except Exception:
                    logger.debug(f"Failed to record timing failure: {e}")
            raise
        finally:
            # Always purge local temp materializations (video + thumbnail).
            # _local_temps is local to this coroutine; safe to reference here.
            for tmp in _local_temps:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception as exc:
                    logger.debug(f"Failed to remove temp {tmp}: {exc}")


@celery_app.task(
    bind=True,
    base=UploadTask,
    name="api.tasks.upload.batch_upload_recordings",
    max_retries=settings.celery.upload_max_retries,
    default_retry_delay=settings.celery.upload_retry_delay,
)
def batch_upload_recordings(
    self,
    recording_ids: list[int],
    user_id: str,
    platforms: list[str],
    preset_ids: dict[str, int] | None = None,
) -> dict:
    """
    Batch upload recordings to multiple platforms.

    Args:
        recording_ids: List of recording IDs
        user_id: ID of user
        platforms: Target platforms (youtube, vk, etc.)
        preset_ids: Optional mapping platform -> preset_id per platform

    Returns:
        Result with status and list of queued subtasks
    """
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info(f"Batch upload | {format_details(recordings=len(recording_ids), platforms=platforms)}")

            results = []
            for recording_id in recording_ids:
                for platform in platforms:
                    preset_id = preset_ids.get(platform) if preset_ids else None

                    subtask_result = upload_recording_to_platform.delay(
                        recording_id=recording_id,
                        user_id=user_id,
                        platform=platform,
                        preset_id=preset_id,
                    )

                    results.append(
                        {
                            "recording_id": recording_id,
                            "platform": platform,
                            "task_id": subtask_result.id,
                            "status": "queued",
                        }
                    )

            return self.build_result(
                user_id=user_id,
                status="dispatched",
                subtasks=results,
            )

        except Exception as exc:
            logger.error(f"Error in batch upload: {exc}", exc_info=True)
            raise
