"""yt-dlp based video downloader for YouTube, VK, Rutube, and other platforms."""

import asyncio
from pathlib import Path
from typing import Any

from file_storage.path_builder import StoragePathBuilder
from logger import get_logger
from video_download_module.core.base import BaseDownloader, DownloadResult
from video_download_module.platforms.ytdlp.opts import get_cookie_opts

logger = get_logger()


class YtDlpDownloader(BaseDownloader):
    """Downloads videos via yt-dlp from YouTube, VK, Rutube, and 1000+ other sites."""

    def __init__(
        self,
        user_slug: int,
        storage_builder: StoragePathBuilder | None = None,
        **kwargs,  # noqa: ARG002
    ):
        super().__init__(user_slug, storage_builder)

    async def download(
        self,
        recording_id: int,
        source_meta: dict[str, Any],
        force: bool = False,
    ) -> DownloadResult:
        """Download video (or audio) via yt-dlp."""
        url = source_meta.get("url") or source_meta.get("download_url")
        if not url:
            raise ValueError("No URL in source metadata for yt-dlp download")

        format_pref = source_meta.get("format_preference", "mp4")

        if self._is_audio_format(format_pref):
            source_suffix = ".mp3"
        else:
            source_suffix = ".mp4"

        target_path = self._get_target_path(recording_id, source_suffix=source_suffix)

        if not force and target_path.exists() and target_path.stat().st_size > 1024:
            return DownloadResult(
                file_path=target_path,
                file_size=target_path.stat().st_size,
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)

        quality = source_meta.get("quality", "best")

        format_spec = self._build_format_spec(quality, format_pref)

        logger.info(f"Downloading via yt-dlp: {url} -> {target_path} (format={format_pref})")

        result_info = await self._run_ytdlp(url, target_path, format_spec, format_pref)

        # Log actual quality selected by yt-dlp (may differ from requested due to availability).
        if result_info:
            actual_height = result_info.get("height")
            actual_ext = result_info.get("ext")
            actual_vcodec = result_info.get("vcodec")
            logger.info(
                f"yt-dlp selected | height={actual_height}p ext={actual_ext} vcodec={actual_vcodec} "
                f"(requested format={format_pref} quality={quality})"
            )
            if format_pref == "mp4" and actual_vcodec and actual_vcodec.startswith("vp"):
                logger.warning(
                    f"yt-dlp fell back to {actual_vcodec} instead of H.264 — "
                    f"no MP4-compatible stream found for quality={quality}"
                )

        if not target_path.exists():
            expected_exts = (".mp3",) if self._is_audio_format(format_pref) else (".mp4", ".mkv", ".webm", ".mov")
            for candidate in target_path.parent.glob(f"{target_path.stem}*"):
                if candidate.is_file() and candidate.suffix.lower() in expected_exts:
                    canonical = self._get_target_path(recording_id, source_suffix=candidate.suffix.lower())
                    if candidate.resolve() != canonical.resolve():
                        old_name = candidate.name
                        candidate.replace(canonical)
                        logger.info("Renamed yt-dlp output | %s -> %s", old_name, canonical.name)
                    else:
                        logger.info("yt-dlp output at expected path | %s", canonical.name)
                    break

        if not target_path.exists():
            raise RuntimeError(f"yt-dlp download completed but file not found: {target_path}")

        file_size = target_path.stat().st_size
        if file_size < 1024:
            target_path.unlink()
            raise RuntimeError(f"yt-dlp produced too small file ({file_size} bytes)")

        if not self._is_audio_format(format_pref):
            validate_name = (source_meta.get("title") and f"{source_meta['title']}{target_path.suffix}") or str(
                target_path.name,
            )
            if not self._validate_file(target_path, None, file_size, source_name=validate_name):
                target_path.unlink(missing_ok=True)
                raise RuntimeError("yt-dlp file failed pipeline ingress sniff / whitelist validation")

        return DownloadResult(
            file_path=target_path,
            file_size=file_size,
            duration=result_info.get("duration"),
            metadata={
                "title": result_info.get("title"),
                "uploader": result_info.get("uploader"),
                "extractor": result_info.get("extractor_key"),
            },
        )

    @staticmethod
    def _is_audio_format(format_pref: str) -> bool:
        return format_pref in ("mp3", "audio")

    def _build_format_spec(self, quality: str, format_pref: str) -> str:
        """Build yt-dlp format specification."""
        if self._is_audio_format(format_pref):
            return "bestaudio/best"
        if format_pref == "mp4":
            if quality == "best":
                return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            height_map = {"1080p": 1080, "720p": 720, "480p": 480}
            height = height_map.get(quality, 1080)
            return (
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"best[height<={height}][ext=mp4]/best[ext=mp4]/best"
            )
        return "best"

    def _build_ydl_opts(self, target_path: Path, format_spec: str, format_pref: str) -> dict[str, Any]:
        """Build yt-dlp options dict."""
        opts: dict[str, Any] = {
            "format": format_spec,
            "outtmpl": str(target_path),
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 30,
            "fixup": "detect_or_warn",
        }
        opts.update(get_cookie_opts())

        if self._is_audio_format(format_pref):
            # Extract audio → mp3 via ffmpeg post-processor
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            opts["merge_output_format"] = "mp4"

        return opts

    async def _run_ytdlp(
        self, url: str, target_path: Path, format_spec: str, format_pref: str = "mp4"
    ) -> dict[str, Any]:
        """Run yt-dlp download in executor thread."""
        import yt_dlp

        ydl_opts = self._build_ydl_opts(target_path, format_spec, format_pref)

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)

        info = await asyncio.get_event_loop().run_in_executor(None, _download)

        return info or {}
