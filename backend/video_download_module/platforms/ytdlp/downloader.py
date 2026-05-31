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
        """Download video (or audio) via yt-dlp into a temp file, then commit to storage."""
        from file_storage.factory import get_storage_backend

        url = source_meta.get("url") or source_meta.get("download_url")
        if not url:
            raise ValueError("No URL in source metadata for yt-dlp download")

        format_pref = source_meta.get("format_preference", "mp4")
        source_suffix = ".mp3" if self._is_audio_format(format_pref) else ".mp4"

        target_key = self._get_target_key(recording_id, source_suffix=source_suffix)
        storage_backend = get_storage_backend()

        # Skip if already in storage and not forced
        if not force and await storage_backend.exists(target_key):
            existing_size = await storage_backend.get_size(target_key)
            if existing_size > 1024:
                return DownloadResult(storage_key=target_key, file_size=existing_size)

        quality = source_meta.get("quality", "best")
        format_spec = self._build_format_spec(quality, format_pref)

        # yt-dlp needs a local writable path; we stream into a temp file then commit.
        temp_path = self._new_temp_path(source_suffix)
        # yt-dlp may produce a slightly different extension due to format negotiation; the
        # resolver below picks up the actual output file.
        try:
            logger.info(f"Downloading via yt-dlp: {url} -> {temp_path} (format={format_pref})")
            result_info = await self._run_ytdlp(url, temp_path, format_spec, format_pref)

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

            # yt-dlp may have written to a sibling extension; recover it.
            actual_path = self._resolve_ytdlp_output(temp_path, format_pref)
            if actual_path is None:
                raise RuntimeError(f"yt-dlp download completed but no file found near {temp_path}")

            file_size = actual_path.stat().st_size
            if file_size < 1024:
                actual_path.unlink(missing_ok=True)
                raise RuntimeError(f"yt-dlp produced too small file ({file_size} bytes)")

            if not self._is_audio_format(format_pref):
                validate_name = (
                    source_meta.get("title") and f"{source_meta['title']}{actual_path.suffix}"
                ) or actual_path.name
                if not self._validate_file(actual_path, None, file_size, source_name=validate_name):
                    actual_path.unlink(missing_ok=True)
                    raise RuntimeError("yt-dlp file failed pipeline ingress sniff / whitelist validation")

            # If yt-dlp produced a different extension, rewrite the key to match.
            if actual_path.suffix.lower() != source_suffix:
                target_key = self._get_target_key(recording_id, source_suffix=actual_path.suffix.lower())

            await self._commit_temp_to_storage(actual_path, target_key)

            return DownloadResult(
                storage_key=target_key,
                file_size=file_size,
                duration=result_info.get("duration"),
                metadata={
                    "title": result_info.get("title"),
                    "uploader": result_info.get("uploader"),
                    "extractor": result_info.get("extractor_key"),
                },
            )
        finally:
            # Clean any leftover temps (the canonical one and any siblings yt-dlp made).
            for p in temp_path.parent.glob(f"{temp_path.stem}*"):
                if p.is_file():
                    p.unlink(missing_ok=True)

    def _resolve_ytdlp_output(self, expected_path: Path, format_pref: str) -> Path | None:
        """yt-dlp may rename the output to a different extension; locate the actual file."""
        if expected_path.exists():
            return expected_path
        expected_exts = (".mp3",) if self._is_audio_format(format_pref) else (".mp4", ".mkv", ".webm", ".mov")
        for candidate in expected_path.parent.glob(f"{expected_path.stem}*"):
            if candidate.is_file() and candidate.suffix.lower() in expected_exts:
                return candidate
        return None

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
