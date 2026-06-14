"""AssemblyAI transcription service using REST API (httpx)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx

from logger import get_logger
from transcription_module.normalize import build_segments_from_words, extract_words

from .config import AssemblyAIConfig

logger = get_logger()


class AssemblyAITranscriptionService:
    """Async transcription via AssemblyAI REST API (submit → poll → normalize)."""

    def __init__(self, config: AssemblyAIConfig) -> None:
        self.config = config
        self._headers = {
            "Authorization": config.api_key,
            "Content-Type": "application/json",
        }

    async def transcribe_audio(
        self,
        audio_storage_key: str,
        language: str | None,
        keyterms: list[str],
    ) -> dict[str, Any]:
        """Transcribe audio from S3/storage key.

        Prod: generates presigned URL → passes as audio_url.
        Local dev: presigned returns relative path → downloads file → uploads via /v2/upload.

        Returns: {text, words, segments, language}
        """
        audio_url = await self._resolve_audio_url(audio_storage_key)

        transcript_id = await self._submit(audio_url, language, keyterms)
        result = await self._poll(transcript_id)
        raw_sentences = await self._fetch_sentences(transcript_id)
        return self._normalize(result, language, raw_sentences)

    async def _resolve_audio_url(self, audio_storage_key: str) -> str:
        """Return a public URL for the audio key, uploading via AssemblyAI if needed."""
        from file_storage.factory import get_storage_backend
        from file_storage.path_builder import StoragePathBuilder

        storage = get_storage_backend()
        presigned = await storage.presigned_url(audio_storage_key, expires_in=7200)

        if presigned.startswith("http"):
            logger.debug(f"AssemblyAI | Using presigned URL for {audio_storage_key}")
            return presigned

        # Local dev: presigned is a relative path — upload file bytes to AssemblyAI
        logger.info("AssemblyAI | Local backend detected, uploading file bytes to /v2/upload")
        builder = StoragePathBuilder()
        tmp = builder.create_temp_file(prefix="aai_upload_", suffix=Path(audio_storage_key).suffix or ".mp3")
        try:
            await storage.download_to_file(audio_storage_key, tmp)
            return await self._upload_file(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    async def _upload_file(self, local_path: Path) -> str:
        """Upload local file to AssemblyAI and return the upload URL."""
        upload_url = f"{self.config.base_url}/v2/upload"
        headers = {"Authorization": self.config.api_key}

        async with httpx.AsyncClient(timeout=300.0) as client:
            with local_path.open("rb") as f:
                response = await client.post(upload_url, headers=headers, content=f.read())

        response.raise_for_status()
        return response.json()["upload_url"]

    async def _submit(self, audio_url: str, language: str | None, keyterms: list[str]) -> str:
        """Submit transcription job and return transcript_id."""
        settings = self.config.settings
        payload: dict[str, Any] = {
            "audio_url": audio_url,
            "speech_models": settings.speech_models,
            "punctuate": True,
            "format_text": True,
            "audio_start_from": None,
            "audio_end_at": None,
        }

        if settings.language_detection:
            payload["language_detection"] = True
        elif language:
            payload["language_code"] = language
        elif settings.language_code:
            payload["language_code"] = settings.language_code

        if keyterms:
            payload["keyterms_prompt"] = keyterms

        logger.info(
            f"AssemblyAI | Submitting | models={settings.speech_models} | "
            f"lang={payload.get('language_code') or 'detect'} | keyterms={len(keyterms)}"
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.config.base_url}/v2/transcript",
                headers=self._headers,
                json=payload,
            )

        response.raise_for_status()
        data = response.json()
        transcript_id = data["id"]
        logger.info(f"AssemblyAI | Job submitted | id={transcript_id}")
        return transcript_id

    async def _poll(self, transcript_id: str) -> dict[str, Any]:
        """Poll until completed or error. Returns the completed response."""
        settings = self.config.settings
        poll_url = f"{self.config.base_url}/v2/transcript/{transcript_id}"
        start = time.monotonic()

        async with httpx.AsyncClient(timeout=30.0) as client:
            attempt = 0
            while True:
                attempt += 1
                elapsed = time.monotonic() - start

                if elapsed > settings.max_wait_seconds:
                    raise TimeoutError(f"AssemblyAI transcription timed out after {elapsed:.0f}s (id={transcript_id})")

                response = await client.get(poll_url, headers={"Authorization": self.config.api_key})
                response.raise_for_status()
                data = response.json()
                status = data.get("status")

                if status == "completed":
                    logger.info(
                        f"AssemblyAI | Completed | id={transcript_id} | elapsed={elapsed:.1f}s | attempts={attempt}"
                    )
                    return data

                if status == "error":
                    raise RuntimeError(f"AssemblyAI transcription failed: {data.get('error')} (id={transcript_id})")

                logger.debug(f"AssemblyAI | Polling | status={status} | elapsed={elapsed:.0f}s | attempt={attempt}")
                await asyncio.sleep(settings.poll_interval)

    async def _fetch_sentences(self, transcript_id: str) -> list[dict[str, Any]]:
        """Fetch sentence-level segments from AssemblyAI (free derived view of transcript)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.config.base_url}/v2/transcript/{transcript_id}/sentences",
                headers={"Authorization": self.config.api_key},
            )
        response.raise_for_status()
        return response.json().get("sentences", [])

    def _normalize_sentences(self, raw_sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert AssemblyAI sentences (ms) to LEAP segment format (seconds)."""
        segments = []
        for s in raw_sentences:
            start_s = float(s.get("start") or 0) / 1000.0
            end_s = float(s.get("end") or 0) / 1000.0
            if end_s <= start_s:
                end_s = start_s + 0.1
            text = (s.get("text") or "").strip()
            if text:
                segments.append({"id": len(segments), "start": start_s, "end": end_s, "text": text})
        return segments

    def _normalize(
        self,
        data: dict[str, Any],
        fallback_language: str | None,
        raw_sentences: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Convert AssemblyAI response to LEAP format {text, words, segments, language}."""
        text = data.get("text") or ""
        language = data.get("language_code") or fallback_language or "ru"

        raw_words = data.get("words") or []
        if not raw_words:
            raise ValueError("No words in AssemblyAI response — check audio quality or language settings")

        words = extract_words(raw_words)

        segments = self._normalize_sentences(raw_sentences) if raw_sentences else []
        if segments:
            logger.info(
                f"AssemblyAI | segments=sentences | count={len(segments)} | words={len(words)} | lang={language}"
            )
        else:
            if raw_sentences:
                logger.warning("AssemblyAI | /sentences returned no usable text, falling back to heuristic")
            segments = build_segments_from_words(words)
            logger.info(
                f"AssemblyAI | segments=heuristic(fallback) | count={len(segments)} | words={len(words)} | lang={language}"
            )
        return {
            "text": text,
            "words": words,
            "segments": segments,
            "language": language,
        }
