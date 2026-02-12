"""Celery tasks for uploading videos with multi-tenancy support."""

from datetime import UTC, datetime
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from api.celery_app import celery_app
from api.core.context import ServiceContext
from api.dependencies import get_async_session_maker
from api.helpers.template_renderer import TemplateRenderer
from api.repositories.auth_repos import UserCredentialRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import OutputPresetRepository, RecordingTemplateRepository
from api.services.config_resolver import ConfigResolver
from api.services.timing_service import TimingService
from api.shared.exceptions import CredentialError, ResourceNotFoundError
from api.tasks.base import UploadTask
from config.settings import get_settings
from database.template_models import OutputPresetModel
from logger import format_task_context, get_logger
from models.recording import TargetStatus
from utils.thumbnail_manager import get_thumbnail_manager
from video_upload_module.platforms.youtube.token_handler import TokenRefreshError
from video_upload_module.uploader_factory import create_uploader_from_db

logger = get_logger()
settings = get_settings()


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
    try:
        ctx = format_task_context(
            task_id=self.request.id, recording_id=recording_id, user_id=user_id, platform=platform
        )
        logger.info(f"{ctx} | Uploading | metadata_override={bool(metadata_override)}")

        result = self.run_async(
            _async_upload_recording(
                recording_id=recording_id,
                user_id=user_id,
                platform=platform,
                preset_id=preset_id,
                credential_id=credential_id,
                metadata_override=metadata_override,
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
        ctx = format_task_context(
            task_id=self.request.id, recording_id=recording_id, user_id=user_id, platform=platform
        )
        logger.error(f"{ctx} | Soft time limit exceeded")
        raise self.retry(countdown=900, exc=SoftTimeLimitExceeded())

    except TokenRefreshError as exc:
        ctx = format_task_context(
            task_id=self.request.id, recording_id=recording_id, user_id=user_id, platform=exc.platform
        )
        logger.error(f"{ctx} | Token refresh failed - re-authentication needed")
        return self.build_result(
            user_id=user_id,
            status="failed",
            recording_id=recording_id,
            platform=exc.platform,
            error="token_refresh_error",
            reason="Token refresh failed. Please re-authenticate via OAuth.",
        )

    except CredentialError as exc:
        ctx = format_task_context(
            task_id=self.request.id, recording_id=recording_id, user_id=user_id, platform=platform
        )
        logger.error(f"{ctx} | Credential error: {exc.reason}")
        return self.build_result(
            user_id=user_id,
            status="failed",
            recording_id=recording_id,
            platform=platform,
            error="credential_error",
            reason=exc.reason,
        )

    except ResourceNotFoundError as exc:
        ctx = format_task_context(
            task_id=self.request.id, recording_id=recording_id, user_id=user_id, platform=platform
        )
        logger.error(f"{ctx} | Resource not found: {exc.resource_type} {exc.resource_id}")
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
        ctx = format_task_context(
            task_id=self.request.id, recording_id=recording_id, user_id=user_id, platform=platform
        )
        logger.error(f"{ctx} | Unexpected error: {type(exc).__name__}: {exc}", exc_info=True)
        raise self.retry(exc=exc)


async def _async_upload_recording(
    recording_id: int,
    user_id: str,
    platform: str,
    preset_id: int | None = None,
    credential_id: int | None = None,
    metadata_override: dict | None = None,
) -> dict:
    """
    Async function for uploading recording.

    Args:
        recording_id: ID of recording
        user_id: ID of user
        platform: Platform
        preset_id: ID of output preset
        credential_id: ID of credential

        Returns:
            Upload results
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
            logger.info(f"[Upload] Skipping upload to {platform}: recording {recording_id} is paused")
            return {"status": "paused", "message": "Pipeline paused by user"}

        logger.debug(f"[Upload] Recording {recording_id} loaded from DB")
        logger.debug(
            f"[Upload] Recording has main_topics: {hasattr(recording, 'main_topics')} = {getattr(recording, 'main_topics', None)}"
        )
        logger.debug(
            f"[Upload] Recording has topic_timestamps: {hasattr(recording, 'topic_timestamps')} = {type(getattr(recording, 'topic_timestamps', None))}"
        )
        if hasattr(recording, "topic_timestamps") and recording.topic_timestamps:
            logger.debug(
                f"[Upload] topic_timestamps is list: {isinstance(recording.topic_timestamps, list)}, length: {len(recording.topic_timestamps) if isinstance(recording.topic_timestamps, list) else 'N/A'}"
            )

        target_type_map = {
            "youtube": "YOUTUBE",
            "vk": "VK",
            "yandex_disk": "YANDEX_DISK",
        }
        target_type = target_type_map.get(platform.lower(), platform.upper())

        output_target = await recording_repo.get_or_create_output_target(
            recording=recording,
            target_type=target_type,
            preset_id=preset_id,
        )

        if output_target.status == TargetStatus.UPLOADED and output_target.target_meta:
            video_id = output_target.target_meta.get("video_id")
            video_url = output_target.target_meta.get("video_url")
            if video_id:
                logger.warning(
                    f"[Upload] Recording {recording_id} already uploaded to {platform} "
                    f"(video_id: {video_id}). Skipping duplicate upload."
                )
                return {
                    "success": True,
                    "video_id": video_id,
                    "video_url": video_url,
                    "skipped": True,
                    "reason": "Already uploaded",
                }

        # Check video file exists BEFORE marking as uploading
        if not recording.processed_video_path:
            raise ResourceNotFoundError("processed video", recording_id)

        video_path = recording.processed_video_path
        if not Path(video_path).exists():
            raise ResourceNotFoundError("video file", video_path)

        preset_metadata = {}
        preset = None

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
                            logger.info(
                                f"[Upload] Auto-selected preset {preset_id} ('{candidate_preset.name}') "
                                f"from template '{template.name}' for platform {platform}"
                            )
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
            logger.debug(f"Resolved metadata from preset '{preset.name}' + template: {list(preset_metadata.keys())}")

            if metadata_override:
                logger.info(f"Applying metadata_override for platform-specific fields: {metadata_override}")
                preset_metadata = config_resolver._merge_configs(preset_metadata, metadata_override)
                logger.info(f"After override - preset_metadata has keys: {list(preset_metadata.keys())}")

            platform_map = {
                "YOUTUBE": "youtube",
                "VK": "vk_video",
                "VK_VIDEO": "vk_video",
                "YANDEX_DISK": "yandex_disk",
            }
            mapped_platform = platform_map.get(preset.platform.upper(), preset.platform.lower())

            uploader = await create_uploader_from_db(
                platform=mapped_platform,
                credential_id=preset.credential_id,
                session=ctx.session,
            )
        elif credential_id:
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

            uploader = await create_uploader_from_db(
                platform=platform,
                credential_id=credentials[0].id,
                session=ctx.session,
            )

        topics_display = preset_metadata.get("topics_display") if preset_metadata else None
        template_context = TemplateRenderer.prepare_recording_context(recording, topics_display)

        logger.debug(
            f"[Upload {platform}] Preset metadata keys: {list(preset_metadata.keys()) if preset_metadata else 'None'}"
        )
        logger.debug(f"[Upload {platform}] Template context keys: {list(template_context.keys())}")
        logger.debug(
            f"[Upload {platform}] Has topic_timestamps: {hasattr(recording, 'topic_timestamps') and recording.topic_timestamps is not None}"
        )
        if hasattr(recording, "topic_timestamps") and recording.topic_timestamps:
            logger.debug(f"[Upload {platform}] topic_timestamps count: {len(recording.topic_timestamps)}")
        logger.debug(
            f"[Upload {platform}] Has main_topics: {hasattr(recording, 'main_topics') and recording.main_topics is not None}"
        )
        if hasattr(recording, "main_topics") and recording.main_topics:
            logger.debug(f"[Upload {platform}] main_topics: {recording.main_topics}")

        try:
            auth_success = await uploader.authenticate()
            if not auth_success:
                raise CredentialError(
                    platform=platform,
                    reason="Token validation failed or expired. Please re-authenticate via OAuth.",
                )

            title_template = preset_metadata.get("title_template", "{display_name}")
            description_template = preset_metadata.get("description_template", "Uploaded on {record_time:date}")

            logger.debug(f"[Upload {platform}] title_template: {title_template[:100]}...")
            logger.debug(f"[Upload {platform}] description_template: {description_template[:200]}...")

            title = TemplateRenderer.render(title_template, template_context)
            description = TemplateRenderer.render(description_template, template_context)

            logger.debug(f"[Upload {platform}] Rendered title: {title[:100] if title else 'EMPTY'}")
            logger.debug(f"[Upload {platform}] Rendered description length: {len(description)} chars")
            logger.debug(
                f"[Upload {platform}] Rendered description preview: {description[:200] if description else 'EMPTY'}"
            )

            if not title:
                logger.warning(f"[Upload {platform}] Title is empty, using fallback")
                title = recording.display_name or "Recording"
            if not description:
                logger.warning(f"[Upload {platform}] Description is empty, using fallback")
                fallback_desc = TemplateRenderer.render("Uploaded on {record_time:date}", template_context)
                description = fallback_desc or "Uploaded"
                if recording.main_topics:
                    if topics_display and topics_display.get("enabled", True):
                        topics_str = TemplateRenderer._format_topics_list(recording.main_topics, topics_display)
                    else:
                        topics_str = ", ".join(recording.main_topics[:5])
                    description += f"\n\n{topics_str}"

            logger.debug(f"[Upload {platform}] Final title: {title[:50]}...")
            logger.debug(f"[Upload {platform}] Final description length: {len(description)}")

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
                logger.debug(
                    f"[Upload YouTube] Playlist lookup: top-level={preset_metadata.get('playlist_id')}, youtube={preset_metadata.get('youtube', {}).get('playlist_id')}"
                )
                if playlist_id:
                    upload_params["playlist_id"] = playlist_id
                    logger.debug(f"[Upload YouTube] Using playlist_id: {playlist_id}")
                else:
                    logger.warning("[Upload YouTube] No playlist_id found in metadata")

                if "publish_at" in preset_metadata:
                    upload_params["publish_at"] = preset_metadata["publish_at"]

                thumbnail_filename = preset_metadata.get("youtube", {}).get("thumbnail_name") or preset_metadata.get(
                    "thumbnail_name"
                )
                logger.debug(
                    f"[Upload YouTube] Thumbnail lookup: youtube-specific={preset_metadata.get('youtube', {}).get('thumbnail_name')}, common={preset_metadata.get('thumbnail_name')}"
                )
                if thumbnail_filename:
                    thumbnail_manager = get_thumbnail_manager()
                    user_slug = recording.owner.user_slug
                    resolved_path = thumbnail_manager.get_thumbnail_path(
                        user_slug=user_slug,
                        thumbnail_name=thumbnail_filename,
                        fallback_to_template=True,
                    )

                    if resolved_path and resolved_path.exists():
                        upload_params["thumbnail_path"] = str(resolved_path)
                        logger.debug(
                            f"[Upload YouTube] Using thumbnail: {resolved_path} (resolved from '{thumbnail_filename}')"
                        )
                    else:
                        logger.warning(
                            f"[Upload YouTube] Thumbnail not found: '{thumbnail_filename}' for user_slug {user_slug}"
                        )
                else:
                    logger.debug("[Upload YouTube] No thumbnail_name found in metadata")

                for key in ["made_for_kids", "embeddable", "license", "public_stats_viewable"]:
                    if key in preset_metadata:
                        upload_params[key] = preset_metadata[key]

            elif platform.lower() in ["vk", "vk_video"]:
                album_id = preset_metadata.get("album_id") or preset_metadata.get("vk", {}).get("album_id")
                if album_id:
                    upload_params["album_id"] = str(album_id)
                    logger.debug(f"[Upload VK] Using album_id: {album_id}")
                else:
                    logger.warning("[Upload VK] No album_id found in metadata")

                thumbnail_filename = preset_metadata.get("vk", {}).get("thumbnail_name") or preset_metadata.get(
                    "thumbnail_name"
                )
                if thumbnail_filename:
                    thumbnail_manager = get_thumbnail_manager()
                    user_slug = recording.owner.user_slug
                    resolved_path = thumbnail_manager.get_thumbnail_path(
                        user_slug=user_slug,
                        thumbnail_name=thumbnail_filename,
                        fallback_to_template=True,
                    )

                    if resolved_path and resolved_path.exists():
                        upload_params["thumbnail_path"] = str(resolved_path)
                        logger.debug(
                            f"[Upload VK] Using thumbnail: {resolved_path} (resolved from '{thumbnail_filename}')"
                        )
                    else:
                        logger.warning(
                            f"[Upload VK] Thumbnail not found: '{thumbnail_filename}' for user_slug {user_slug}"
                        )
                else:
                    logger.debug("[Upload VK] No thumbnail_name found in metadata")

                for key in ["group_id", "privacy_view", "privacy_comment", "no_comments", "repeat", "wallpost"]:
                    if key in preset_metadata:
                        upload_params[key] = preset_metadata[key]

            elif platform.lower() == "yandex_disk":
                # Resolve folder path template
                folder_path_template = preset_metadata.get("yandex_disk", {}).get(
                    "folder_path_template"
                ) or preset_metadata.get("folder_path_template", "/Video/Uploads")
                folder_path = TemplateRenderer.render(folder_path_template, template_context)
                upload_params["folder_path"] = folder_path

                filename_template = preset_metadata.get("yandex_disk", {}).get(
                    "filename_template"
                ) or preset_metadata.get("filename_template")
                if filename_template:
                    filename = TemplateRenderer.render(filename_template, template_context)
                    upload_params["filename"] = filename

                if "overwrite" in preset_metadata:
                    upload_params["overwrite"] = preset_metadata["overwrite"]

                logger.debug(f"[Upload YaDisk] folder_path={folder_path}")

            # Start upload timing
            timing_service = TimingService(session)
            stage_name = f"UPLOAD:{target_type}"
            timing = await timing_service.start_stage(recording_id, user_id, stage_name)

            # Mark output as UPLOADING RIGHT BEFORE actual upload starts
            logger.info(f"[Upload {platform}] Marking recording {recording_id} as UPLOADING")
            output_target.started_at = datetime.now(UTC)
            await recording_repo.mark_output_uploading(output_target)
            await session.commit()

            upload_result = await uploader.upload_video(**upload_params)

            if not upload_result or upload_result.error_message:
                error_message = upload_result.error_message if upload_result else "Unknown error"
                await timing_service.fail_stage(timing, f"Upload failed: {error_message}")
                await recording_repo.mark_output_failed(output_target, f"Upload failed: {error_message}")
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

            # Update pipeline timing
            now = datetime.now(UTC)
            recording.pipeline_completed_at = now
            if recording.pipeline_started_at:
                recording.pipeline_duration_seconds = (now - recording.pipeline_started_at).total_seconds()

            await session.commit()

            return {
                "success": True,
                "video_id": upload_result.video_id,
                "video_url": upload_result.video_url,
                "metadata": upload_result.metadata,
            }

        except Exception as e:
            # Fail timing if it was started but not yet completed/failed
            if "timing" in locals() and timing.status == "IN_PROGRESS":
                try:
                    await timing_service.fail_stage(timing, str(e))
                except Exception:
                    logger.debug(f"[Upload] Failed to record timing failure: {e}")

            if output_target.status not in (TargetStatus.FAILED, TargetStatus.UPLOADED):
                await recording_repo.mark_output_failed(output_target, str(e))
                await session.commit()
            raise


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
    Batch uploading recordings to platforms.
    """
    try:
        ctx = format_task_context(task_id=self.request.id, user_id=user_id)
        logger.info(f"{ctx} | Batch upload: {len(recording_ids)} recordings | platforms={platforms}")

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
        ctx = format_task_context(task_id=self.request.id, user_id=user_id)
        logger.error(f"{ctx} | Error in batch upload: {exc}", exc_info=True)
        raise
