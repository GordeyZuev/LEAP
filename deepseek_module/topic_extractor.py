"""Topic extraction from transcription using DeepSeek"""

import re
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from logger import get_logger

from .config import DeepSeekConfig

logger = get_logger(__name__)

# Constants
MIN_PAUSE_MINUTES = 8.0
MIN_TOPIC_DURATION_SECONDS = 60
NOISE_WINDOW_MINUTES = 15
TIMESTAMP_PATTERN = r"\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*[-–—]?\s*(.+)"
TIMESTAMP_PATTERN_MS = r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.+)"
NOISE_PATTERNS = [r"редактор субтитров", r"корректор", r"продолжение следует"]
FIREWORKS_MAX_TOKENS_NON_STREAM = 4096
MAIN_TOPIC_MIN_WORDS = 2
MAIN_TOPIC_MAX_WORDS = 4
MAIN_TOPIC_MIN_LENGTH = 3


class TopicExtractor:
    """Extract topics from transcription using MapReduce approach"""

    def __init__(self, config: DeepSeekConfig):
        self.config = config

        base = (config.base_url or "").lower()
        allowed_domains = ("deepseek.com", "fireworks.ai")

        if not any(domain in base for domain in allowed_domains):
            raise ValueError(
                "❌ ОШИБКА: Некорректный endpoint для TopicExtractor! "
                "Ожидается DeepSeek API (https://api.deepseek.com/v1) "
                "или Fireworks API (https://api.fireworks.ai/inference/v1). "
                f"Получен: {config.base_url}"
            )

        # Определяем провайдер
        self.is_fireworks = "fireworks.ai" in base

        # Определяем способ подключения к API
        # Для Fireworks используем прямой HTTP-запрос через httpx (нужны специфичные параметры)
        # Для прямого DeepSeek используем OpenAI клиент (OpenAI-compatible API)
        if self.is_fireworks:
            self.client = None  # Будем использовать httpx напрямую
            self.api_key = config.api_key
            self.base_url = config.base_url
        else:
            # Для DeepSeek используем AsyncOpenAI (OpenAI-compatible API)
            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )
            self.api_key = None
            self.base_url = None

        # Определяем провайдер для логирования
        if self.is_fireworks:
            provider = "fireworks_deepseek"
        else:
            provider = "deepseek"
        logger.info(
            f"TopicExtractor initialized: provider={provider} | base_url={config.base_url} | model={config.model}",
            provider=provider,
            base_url=config.base_url,
            model=config.model,
        )

    async def extract_topics(
        self,
        segments: list[dict],
        recording_topic: str | None = None,
        granularity: str = "long",  # "short" | "long"
    ) -> dict[str, Any]:
        """
        Извлечение тем из транскрипции через DeepSeek.

        Args:
            segments: Список сегментов с временными метками (обязательно)
            recording_topic: Название курса/предмета для контекста (опционально)

        Returns:
            Словарь с темами:
            {
                'topic_timestamps': [
                    {'topic': str, 'start': float, 'end': float},
                    ...
                ],
                'main_topics': [str, ...]  # Максимум 2 темы
                'long_pauses': [
                    {'start': float, 'end': float, 'duration_minutes': float},
                    ...
                ]  # Паузы >=8 минут между сегментами
            }
        """
        if not segments:
            raise ValueError("Сегменты обязательны для извлечения тем")

        total_duration = segments[-1].get("end", 0) if segments else 0
        duration_minutes = total_duration / 60
        min_topics, max_topics = self._calculate_topic_range(duration_minutes, granularity=granularity)

        # Unified topics extraction start log
        context_info = f" | topic={recording_topic}" if recording_topic else ""
        logger.info(
            f"Extracting topics: segments={len(segments)} | duration={duration_minutes:.1f}min | "
            f"range={min_topics}-{max_topics}{context_info}"
        )

        transcript_with_timestamps = self._format_transcript_with_timestamps(segments)

        try:
            result = await self._analyze_full_transcript(
                transcript_with_timestamps,
                total_duration,
                recording_topic,
                min_topics,
                max_topics,
                granularity=granularity,
                segments=segments,
            )

            main_topics = result.get("main_topics", [])
            topic_timestamps = result.get("topic_timestamps", [])

            topic_timestamps_with_end = self._add_end_timestamps(topic_timestamps, total_duration)

            logger.info(
                f"Topics extracted successfully: main={len(main_topics)} | detailed={len(topic_timestamps_with_end)}",
                main_topics=len(main_topics),
                detailed_topics=len(topic_timestamps_with_end),
            )

            return {
                "topic_timestamps": topic_timestamps_with_end,
                "main_topics": main_topics,
                "long_pauses": result.get("long_pauses", []),
            }
        except Exception as error:
            logger.exception(f"Failed to extract topics: error={error}", error=str(error))
            return {
                "topic_timestamps": [],
                "main_topics": [],
            }

    async def extract_topics_from_file(
        self,
        segments_file_path: str,
        recording_topic: str | None = None,
        granularity: str = "long",  # "short" | "long"
    ) -> dict[str, Any]:
        """
        Извлечение тем из файла segments.txt.

        Args:
            segments_file_path: Путь к файлу segments.txt с форматом [HH:MM:SS - HH:MM:SS] текст
            recording_topic: Название курса/предмета для контекста (опционально)
            granularity: Режим извлечения тем: "short" или "long"

        Returns:
            Словарь с темами (аналогично extract_topics)
        """
        segments_path = Path(segments_file_path)
        if not segments_path.exists():
            raise FileNotFoundError(f"Файл segments.txt не найден: {segments_file_path}")

        logger.info(f"Reading segments from file: {segments_file_path}")

        segments = self._parse_segments_from_file(segments_path)

        if not segments:
            raise ValueError(f"Не удалось извлечь сегменты из файла {segments_file_path}")

        logger.info(f"Read {len(segments)} segments from file {segments_file_path}")

        return await self.extract_topics(
            segments=segments,
            recording_topic=recording_topic,
            granularity=granularity,
        )

    def _format_transcript_with_timestamps(self, segments: list[dict]) -> str:
        """Format transcript with timestamps, filtering noise."""
        exclude_from, exclude_to = self._detect_noise_window(segments)
        segments_text = []

        for seg in segments:
            start = seg.get("start", 0)
            text = seg.get("text", "").strip()
            if not text:
                continue

            # Skip noise segments and segments in noise window
            if any(re.search(pat, text.lower()) for pat in NOISE_PATTERNS):
                continue
            if exclude_from is not None and exclude_from <= start <= exclude_to:
                continue

            time_str = self._format_time(start)
            segments_text.append(f"{time_str} {text}")

        return "\n".join(segments_text)

    def _detect_noise_window(self, segments: list[dict]) -> tuple[float | None, float | None]:
        """Detect long noise window in segments."""
        noise_times = [
            float(seg.get("start", 0))
            for seg in segments
            if (text := (seg.get("text") or "").strip().lower()) and any(re.search(pat, text) for pat in NOISE_PATTERNS)
        ]

        if noise_times:
            first_noise, last_noise = min(noise_times), max(noise_times)
            if (last_noise - first_noise) >= NOISE_WINDOW_MINUTES * 60:
                return first_noise, last_noise

        return None, None

    def _parse_segments_from_file(self, segments_path: Path) -> list[dict]:
        """Parse segments from file with timestamps."""
        segments = []
        timestamp_pattern = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2}):(\d{2})\]\s*(.+)")
        timestamp_pattern_ms = re.compile(TIMESTAMP_PATTERN_MS)

        with segments_path.open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                match_ms = timestamp_pattern_ms.match(line)
                match_s = timestamp_pattern.match(line) if not match_ms else None

                if match_ms or match_s:
                    try:
                        if match_ms:
                            start_h, start_m, start_s, start_ms = map(int, match_ms.groups()[:4])
                            end_h, end_m, end_s, end_ms = map(int, match_ms.groups()[4:8])
                            text = match_ms.groups()[8].strip()
                            start_seconds = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0
                            end_seconds = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0
                        else:
                            start_h, start_m, start_s, end_h, end_m, end_s = map(int, match_s.groups()[:6])
                            text = match_s.groups()[6].strip()
                            start_seconds = start_h * 3600 + start_m * 60 + start_s
                            end_seconds = end_h * 3600 + end_m * 60 + end_s

                        if text:
                            segments.append(
                                {
                                    "start": float(start_seconds),
                                    "end": float(end_seconds),
                                    "text": text,
                                }
                            )
                    except (ValueError, IndexError) as e:
                        logger.warning(f"⚠️ Parse error at line {line_num}: {line[:50]}... - {e}")
                        continue

        return segments

    def _calculate_topic_range(self, duration_minutes: float, granularity: str = "long") -> tuple[int, int]:
        """
        Вычисление динамического диапазона топиков на основе длительности пары.

        Режимы:
        - long (длинный режим, детальнее):
          - 50 минут -> 10–14
          - 90 минут -> 14–20
          - 120 минут -> 18–24
          - 180 минут -> 22–28
        - short (короткий режим, крупнее):
          - 50 минут -> 3–5
          - 90 минут -> 5–8
          - 120 минут -> 6–9
          - 180 минут -> 8–12

        Args:
            duration_minutes: Длительность пары в минутах
            granularity: "short" или "long"

        Returns:
            Кортеж (min_topics, max_topics)
        """
        duration_minutes = max(50, min(180, duration_minutes))

        if granularity == "short":
            # Короткий режим: меньше тем, крупнее (5-10 тем для 90-минутной лекции)
            min_topics = int(3 + (duration_minutes - 50) * 4 / 130)
            max_topics = int(5 + (duration_minutes - 50) * 5 / 130)
            min_topics = max(3, min(8, min_topics))
            max_topics = max(5, min(12, max_topics))
            return min_topics, max_topics

        min_topics = int(10 + (duration_minutes - 50) * 8 / 130)
        max_topics = int(16 + (duration_minutes - 50) * 10 / 130)
        min_topics = max(10, min(18, min_topics))
        max_topics = max(16, min(26, max_topics))

        return min_topics, max_topics

    async def _analyze_full_transcript(
        self,
        transcript: str,
        total_duration: float,
        recording_topic: str | None = None,
        min_topics: int = 10,
        max_topics: int = 30,
        granularity: str = "long",  # "short" | "long"
        segments: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Анализ полной транскрипции через DeepSeek.

        Args:
            transcript: Полная транскрипция с временными метками
            total_duration: Общая длительность видео в секундах
            recording_topic: Название курса/предмета

        Returns:
            Словарь с основными темами и детализированными топиками
        """
        context_line = ""
        if recording_topic:
            context_line = f"\nКонтекст: это лекция по курсу '{recording_topic}'.\n"

        if granularity == "short":
            min_spacing_minutes = max(10, min(18, total_duration / 60 * 0.12))
        else:  # granularity == "long"
            min_spacing_minutes = max(4, min(6, total_duration / 60 * 0.05))

        long_pauses = self._detect_long_pauses(segments or [], min_gap_minutes=MIN_PAUSE_MINUTES)
        pauses_instruction = ""
        if long_pauses:
            pauses_lines = [
                f"- {self._format_time(pause['start'])} – {self._format_time(pause['end'])} (≈{pause['duration_minutes']:.1f} мин)"
                for pause in long_pauses
            ]
            pauses_instruction = (
                "\n\n⚠️ ВАЖНО: Найдены перерывы >=8 минут. ОБЯЗАТЕЛЬНО добавь их в список тем:\n"
                + "\n".join(pauses_lines)
                + "\n\nДля каждой паузы: [HH:MM:SS] - Перерыв (где HH:MM:SS — время начала из списка выше)."
            )

        if granularity == "short":
            # Короткий режим: упрощенный промпт с крупными темами
            prompt = f"""Проанализируй транскрипцию учебной лекции и выдели структуру:{context_line}{pauses_instruction}

## ОСНОВНАЯ ТЕМА ПАРЫ

Выведи РОВНО ОДНУ тему (2–4 слова):{f" Название темы НЕ должно содержать слова из названия курса '{recording_topic}'. Если тема содержит такие слова — убери их. Например, если курс называется 'Прикладной Python', а тема 'Асинхронное программирование Python', напиши только 'Асинхронное программирование'." if recording_topic else ""}
Название темы

Примеры: "Stable Diffusion", "Архитектура трансформеров", "Generative Models"

## ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ ({min_topics}-{max_topics} топиков)

Формат: [HH:MM:SS] - Название топика

КРИТИЧЕСКИЕ ПРАВИЛА:
1. Количество: РОВНО {min_topics}-{max_topics} топиков. Если больше — объедини похожие.
2. Длительность: МИНИМУМ 5 минут, МАКСИМУМ 40 минут на тему.
3. Если тема <5 минут — ОБЯЗАТЕЛЬНО объедини с соседней.
4. Если тема >40 минут — ОБЯЗАТЕЛЬНО разбей на несколько тем по 5–40 минут каждая.
5. Минимальный шаг между темами: {min_spacing_minutes:.1f} минут.
6. Названия: 3–6 слов, информативные, на русском или английском (по терминологии).
7. Хронологический порядок.
8. Только фактические темы из транскрипции.
9. ВАЖНО: Используй РЕАЛЬНЫЕ временные метки из транскрипции [HH:MM:SS], не придумывай свои.

ФИНАЛЬНАЯ ПРОВЕРКА:
- Количество: {min_topics}-{max_topics} тем
- Длительность: каждая тема 5–40 минут (проверь последнюю тему до конца транскрипции)
- Перерывы: все >=5 минут добавлены (если были указаны)
- Нет нарушений: нет тем <5 минут или >40 минут

Если нарушено любое правило — переразметь список до полного соответствия.

Транскрипция:
{transcript}
"""
        else:
            prompt = f"""Проанализируй транскрипцию учебной лекции и выдели структуру:{context_line}{pauses_instruction}

## ОСНОВНАЯ ТЕМА ПАРЫ

Выведи РОВНО ОДНУ тему (2–4 слова):{f" Название темы НЕ должно содержать слова из названия курса '{recording_topic}'. Если тема содержит такие слова — убери их. Например, если курс называется 'Прикладной Python', а тема 'Асинхронное программирование Python', напиши только 'Асинхронное программирование'." if recording_topic else ""}
Название темы

Примеры: "Stable Diffusion", "Архитектура трансформеров", "Generative Models"

## ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ ({min_topics}-{max_topics} топиков)

Формат: [HH:MM:SS] - Название топика

КРИТИЧЕСКИЕ ПРАВИЛА:
1. Количество: РОВНО {min_topics}-{max_topics} топиков. Если больше — объедини похожие.
2. Длительность: МИНИМУМ 3–4 минуты, МАКСИМУМ 12 минут на тему.
3. Если тема <3 минут — ОБЯЗАТЕЛЬНО объедини с соседней.
4. Если тема >12 минут — ОБЯЗАТЕЛЬНО разбей на 2–3 темы.
5. Минимальный шаг между темами: {min_spacing_minutes:.1f} минут.
6. Названия: 3–6 слов, информативные, на русском или английском (по терминологии).
7. Хронологический порядок.
8. Только фактические темы из транскрипции.

ФИНАЛЬНАЯ ПРОВЕРКА:
- Количество: {min_topics}-{max_topics} тем
- Длительность: каждая тема 3–12 минут
- Перерывы: все >=8 минут добавлены (если были указаны)
- Нет нарушений: нет тем <3 минут или >12 минут

Если нарушено любое правило — переразметь список до полного соответствия.

Транскрипция:
{transcript}
"""

        try:
            if self.is_fireworks:
                # Для Fireworks используем прямой HTTP-запрос, чтобы поддерживать все параметры
                content = await self._fireworks_request(prompt)
            else:
                # Для прямого DeepSeek используем OpenAI клиент (OpenAI-compatible API)
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты — самый лучший аналитик учебных материалов на магистратуре Computer Science. Анализируй транскрипции и выделяй структуру лекций.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    **self.config.to_request_params(),
                )
                # Проверяем, что response является объектом с атрибутом choices
                if not hasattr(response, "choices") or not response.choices:
                    error_msg = (
                        f"Неожиданный формат ответа от DeepSeek API: response type={type(response)}, value={response}"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                content = response.choices[0].message.content.strip()

            if not content:
                return {"main_topics": [], "topic_timestamps": []}

            logger.debug(f"Prompt sent to DeepSeek: preview={prompt[:1000]}... | total_length={len(prompt)}")
            logger.debug(f"Full DeepSeek response: length={len(content)} | preview={content[:200]}...")

            parsed = self._parse_structured_response(content, total_duration)
            parsed["long_pauses"] = long_pauses
            logger.debug(
                f"Результат парсинга: main_topics={len(parsed.get('main_topics', []))} | "
                f"topic_timestamps={len(parsed.get('topic_timestamps', []))} | total_duration={total_duration}s"
            )

            return parsed

        except Exception as error:
            logger.exception(f"Failed to analyze transcript: error={error}", error=str(error))
            return {"main_topics": [], "topic_timestamps": []}

    async def _fireworks_request(self, prompt: str) -> str:
        """
        Прямой HTTP-запрос к Fireworks API.

        Параметры передаются согласно официальной документации Fireworks API:
          - model
          - max_tokens
          - top_p
          - top_k
          - presence_penalty
          - frequency_penalty
          - temperature
          - messages

        Args:
            prompt: Промпт для отправки

        Returns:
            Текст ответа от модели
        """
        url = f"{self.base_url}/chat/completions"

        # Собираем параметры согласно спецификации Fireworks API
        params: dict[str, Any] = {
            "max_tokens": self.config.max_tokens,
            "top_k": self.config.top_k,
            "presence_penalty": self.config.presence_penalty,
            "frequency_penalty": self.config.frequency_penalty,
            "temperature": self.config.temperature,
        }

        # Для максимальной детерминированности: если top_k=1, не используем top_p
        # (top_p и top_k могут конфликтовать при детерминированных настройках)
        if self.config.top_k != 1 and self.config.top_p is not None:
            params["top_p"] = self.config.top_p

        # Fireworks non-stream requests require max_tokens <= 4096
        if params.get("max_tokens", 0) > FIREWORKS_MAX_TOKENS_NON_STREAM:
            logger.warning(
                f"⚠️ max_tokens={params.get('max_tokens')} exceeds Fireworks limit ({FIREWORKS_MAX_TOKENS_NON_STREAM}). "
                f"Reducing to {FIREWORKS_MAX_TOKENS_NON_STREAM}."
            )
            params["max_tokens"] = FIREWORKS_MAX_TOKENS_NON_STREAM

        # Фильтруем None значения, чтобы не передавать их в API
        params = {k: v for k, v in params.items() if v is not None}

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты — самый лучший аналитик учебных материалов на магистратуре Computer Science. Анализируй транскрипции и выделяй структуру лекций.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            **params,
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        timeout = httpx.Timeout(self.config.timeout, connect=10.0)

        logger.debug(f"Fireworks API request: url={url} | model={self.config.model} | params={list(params.keys())}")

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code != 200:
                    self._log_api_error(response, url, payload, params)
                    response.raise_for_status()

                data = response.json()

                if "choices" not in data or not data["choices"]:
                    raise ValueError(f"Invalid Fireworks API response format: {data}")

                return data["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as e:
                if e.response is not None:
                    self._log_http_error(e.response)
                raise

    def _log_api_error(self, response: httpx.Response, url: str, payload: dict, params: dict) -> None:
        """Log Fireworks API error response."""
        try:
            error_text = str(response.json())
        except Exception:
            error_text = response.text

        logger.error(
            f"❌ Fireworks API error (status {response.status_code}):\n"
            f"URL: {url}\n"
            f"Payload keys: {list(payload.keys())}\n"
            f"Params: {params}\n"
            f"Response: {error_text[:2000]}"
        )

    def _log_http_error(self, response: httpx.Response) -> None:
        """Log HTTP error details."""
        try:
            error_data = response.json()
            logger.error(f"Fireworks API error: data={error_data}", error_data=error_data)
        except Exception:
            error_text = response.text
            logger.error(f"Fireworks API error: text={error_text[:1000]}", error_text=error_text[:1000])

    def _detect_long_pauses(self, segments: list[dict], min_gap_minutes: float = 8.0) -> list[dict]:
        """
        Поиск длинных пауз между сегментами.

        Args:
            segments: Список сегментов (ожидается отсортированный список)
            min_gap_minutes: Минимальная длительность паузы (в минутах) для фиксации

        Returns:
            Список словарей с паузами: [{"start": float, "end": float, "duration_minutes": float}, ...]
        """
        if not segments:
            return []

        min_gap_seconds = min_gap_minutes * 60
        pauses: list[dict] = []

        sorted_segments = sorted(segments, key=lambda s: s.get("start", 0))

        for idx in range(len(sorted_segments) - 1):
            current = sorted_segments[idx]
            nxt = sorted_segments[idx + 1]

            current_end = float(current.get("end", current.get("start", 0) or 0))
            next_start = float(nxt.get("start", 0) or 0)

            gap = next_start - current_end
            if gap >= min_gap_seconds:
                pauses.append(
                    {
                        "start": current_end,
                        "end": next_start,
                        "duration_minutes": gap / 60,
                    }
                )

        return pauses

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds to HH:MM:SS."""
        total_seconds = int(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _parse_structured_response(self, text: str, total_duration: float) -> dict[str, Any]:
        """
        Парсинг структурированного ответа от DeepSeek.

        Формат ответа:
        ## ОСНОВНЫЕ ТЕМЫ ПАРЫ
        - Тема 1
        - Тема 2

        ## ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ С ТАЙМКОДАМИ
        [HH:MM:SS] - [Название топика]
        [HH:MM:SS] - [Название топика]

        Args:
            text: Текст ответа от DeepSeek
            total_duration: Общая длительность видео в секундах

        Returns:
            Словарь с основными темами и детализированными топиками
        """
        main_topics = []
        topic_timestamps = []

        lines = text.split("\n")

        in_main_topics = False
        in_detailed_topics = False
        main_topics_section_found = False

        # Try to find main topic before detailed topics section
        main_topic = self._find_main_topic_before_section(lines)
        if main_topic:
            main_topics.append(main_topic)

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            if (
                "ОСНОВНЫЕ ТЕМЫ" in line.upper()
                or "ОСНОВНЫЕ ТЕМЫ ПАРЫ" in line.upper()
                or "ОСНОВНАЯ ТЕМА" in line.upper()
            ):
                in_main_topics = True
                in_detailed_topics = False
                main_topics_section_found = True
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith("##") and not next_line.startswith("#"):
                        topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", next_line).strip()
                        topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
                        if topic_candidate and len(topic_candidate) > 3 and "выведи" not in topic_candidate.lower():
                            words = topic_candidate.split()
                            if len(words) <= 4:
                                main_topics.append(topic_candidate)
                continue
            if "ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ" in line.upper() or "ТОПИКИ С ТАЙМКОДАМИ" in line.upper():
                in_main_topics = False
                in_detailed_topics = True
                continue
            if line.startswith("##"):
                in_main_topics = False
                in_detailed_topics = False
                continue

            # Timestamp indicates detailed topic
            timestamp_match = re.match(TIMESTAMP_PATTERN, line)
            if timestamp_match:
                in_detailed_topics = True
                in_main_topics = False
                # Парсим топик сразу
                hours_str, minutes_str, seconds_str, topic = timestamp_match.groups()
                total_seconds = self._parse_timestamp_to_seconds(hours_str, minutes_str, seconds_str)
                if 0 <= total_seconds <= total_duration:
                    topic_timestamps.append(
                        {
                            "topic": topic.strip(),
                            "start": float(total_seconds),
                        }
                    )
                continue

            if in_main_topics:
                if not line or line.startswith(("##", "#")):
                    continue

                topic = re.sub(r"^[-*•\d.)]+\s*", "", line).strip()
                topic = re.sub(r"^\[.*?\]\s*", "", topic).strip()

                if topic.startswith("[") and "выведи" in topic.lower():
                    continue

                if topic and len(topic) > 3:
                    words = topic.split()
                    if len(words) > 7:
                        topic = " ".join(words[:15]) + "..."
                    elif len(topic) > 150:
                        topic = topic[:150].rsplit(" ", 1)[0] + "..."
                    main_topics.append(topic)

            elif in_detailed_topics:
                match = re.match(TIMESTAMP_PATTERN, line)
                if match:
                    hours_str, minutes_str, seconds_str, topic = match.groups()
                    total_seconds = self._parse_timestamp_to_seconds(hours_str, minutes_str, seconds_str)

                    if 0 <= total_seconds <= total_duration:
                        topic_timestamps.append(
                            {
                                "topic": topic.strip(),
                                "start": float(total_seconds),
                            }
                        )
                    else:
                        logger.debug(
                            f"Timestamp skipped (out of range): topic={topic.strip()} | position={total_seconds / 60:.1f}min | range=0-{total_duration / 60:.1f}min",
                            topic=topic.strip(),
                            position_min=round(total_seconds / 60, 1),
                            valid_range=f"0-{round(total_duration / 60, 1)}",
                        )

        # Fallback: parse all lines with timestamps
        if not topic_timestamps:
            topic_timestamps = self._parse_all_timestamps(lines, total_duration)

        if not topic_timestamps and not main_topics:
            topic_timestamps = self._parse_simple_timestamps(text, total_duration)

        if main_topics_section_found and not main_topics:
            logger.debug("Main topics section found but not extracted. Fallback search.")
            main_topic = self._find_topic_after_section_header(lines)
            if main_topic:
                main_topics.append(main_topic)

        processed_main_topics = self._process_main_topics(main_topics)

        if processed_main_topics:
            logger.info(f"Main topic: {processed_main_topics[0]}")
        elif main_topics_section_found:
            logger.warning(
                f"⚠️ Main topics section found but extraction failed. First lines:\n{chr(10).join(lines[:10])}"
            )

        return {
            "main_topics": processed_main_topics,
            "topic_timestamps": topic_timestamps,
        }

    @staticmethod
    def _process_main_topics(main_topics: list[str]) -> list[str]:
        """Process and normalize main topics."""
        processed = []
        for topic in main_topics[:1]:
            topic = " ".join(topic.split())
            if topic and len(topic) > MAIN_TOPIC_MIN_LENGTH:
                words = topic.split()
                if len(words) > 7:
                    topic = " ".join(words[:7]) + "..."
                processed.append(topic)
        return processed

    def _find_main_topic_before_section(self, lines: list[str]) -> str | None:
        """Find main topic before detailed topics section."""
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            if "ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ" in line_stripped.upper() or "ТОПИКИ С ТАЙМКОДАМИ" in line_stripped.upper():
                # Look for topic in previous 10 lines
                for j in range(max(0, i - 10), i):
                    candidate = lines[j].strip()
                    if not candidate or candidate.startswith(("##", "#")):
                        continue
                    if any(word in candidate.lower() for word in ["выведи", "тема", "пример"]):
                        continue
                    if re.match(TIMESTAMP_PATTERN, candidate):
                        continue

                    topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", candidate).strip()
                    topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
                    if topic_candidate and MAIN_TOPIC_MIN_WORDS <= len(topic_candidate.split()) <= MAIN_TOPIC_MAX_WORDS:
                        return topic_candidate
                break

        # Check first 10 lines if not found before section
        for line in lines[:10]:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith(("##", "#")):
                continue
            if re.match(TIMESTAMP_PATTERN, line_stripped):
                break
            if any(word in line_stripped.lower() for word in ["выведи", "тема", "пример"]):
                continue

            topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", line_stripped).strip()
            topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
            if topic_candidate and MAIN_TOPIC_MIN_WORDS <= len(topic_candidate.split()) <= MAIN_TOPIC_MAX_WORDS:
                return topic_candidate

        return None

    def _find_topic_after_section_header(self, lines: list[str]) -> str | None:
        """Find main topic after section header."""
        for i, line in enumerate(lines):
            if "ОСНОВНЫЕ ТЕМЫ" in line.upper() or "ОСНОВНЫЕ ТЕМЫ ПАРЫ" in line.upper():
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if not candidate or candidate.startswith(("##", "#")):
                        continue

                    topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", candidate).strip()
                    topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()

                    if (
                        topic_candidate
                        and len(topic_candidate) > MAIN_TOPIC_MIN_LENGTH
                        and not any(word in topic_candidate.lower() for word in ["выведи", "тема", "пример"])
                        and MAIN_TOPIC_MIN_WORDS <= len(topic_candidate.split()) <= MAIN_TOPIC_MAX_WORDS
                    ):
                        return topic_candidate
                break
        return None

    @staticmethod
    def _parse_timestamp_to_seconds(hours_str: str, minutes_str: str, seconds_str: str | None) -> int:
        """Convert timestamp components to total seconds."""
        if seconds_str is None:
            return int(hours_str) * 60 + int(minutes_str)
        return int(hours_str) * 3600 + int(minutes_str) * 60 + int(seconds_str)

    def _parse_all_timestamps(self, lines: list[str], total_duration: float) -> list[dict]:
        """Parse all lines with timestamps as fallback."""
        timestamps = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(TIMESTAMP_PATTERN, line)
            if match:
                hours_str, minutes_str, seconds_str, topic = match.groups()
                total_seconds = self._parse_timestamp_to_seconds(hours_str, minutes_str, seconds_str)
                if 0 <= total_seconds <= total_duration:
                    timestamps.append({"topic": topic.strip(), "start": float(total_seconds)})
        return timestamps

    def _parse_simple_timestamps(self, text: str, total_duration: float) -> list[dict]:
        """Parse simple timestamp format as fallback."""
        return self._parse_all_timestamps(text.split("\n"), total_duration)

    def _merge_close_topics(self, timestamps: list[dict], min_spacing: float) -> list[dict]:
        """Merge topics that are too close together."""
        merged = []
        for ts in timestamps:
            start = ts.get("start", 0)
            topic = ts.get("topic", "").strip()

            if not topic:
                continue

            if merged and (start - merged[-1].get("start", 0)) < min_spacing:
                prev_topic = merged[-1].get("topic", "")
                if len(topic) > len(prev_topic):
                    merged[-1]["topic"] = topic
                if start < merged[-1].get("start", 0):
                    merged[-1]["start"] = start
            else:
                merged.append(ts)

        return merged

    def _add_missing_topics(
        self, merged: list[dict], all_timestamps: list[dict], min_topics: int, min_spacing: float
    ) -> list[dict]:
        """Add more topics to reach minimum count."""
        additional_step = len(all_timestamps) / (min_topics - len(merged))
        added_indices = set()

        for i in range(min_topics - len(merged)):
            idx = int(i * additional_step)
            if idx >= len(all_timestamps) or idx in added_indices:
                continue

            ts = all_timestamps[idx]
            start = ts.get("start", 0)
            topic = ts.get("topic", "").strip()

            if topic and not any(abs(start - existing.get("start", 0)) < min_spacing for existing in merged):
                merged.append(ts)
                added_indices.add(idx)

        return sorted(merged, key=lambda x: x.get("start", 0))

    def _add_end_timestamps(self, timestamps: list[dict], total_duration: float) -> list[dict]:
        """Add end timestamps to topics."""
        if not timestamps:
            return []

        sorted_timestamps = sorted(timestamps, key=lambda x: x.get("start", 0))
        result = []

        for i, ts in enumerate(sorted_timestamps):
            start = ts.get("start", 0)
            topic = ts.get("topic", "").strip()

            if not topic:
                continue

            # Calculate end time
            if i < len(sorted_timestamps) - 1:
                end = sorted_timestamps[i + 1].get("start", 0)
                # Ensure minimum duration
                if end - start < MIN_TOPIC_DURATION_SECONDS:
                    end = min(start + MIN_TOPIC_DURATION_SECONDS, sorted_timestamps[i + 1].get("start", 0))
            else:
                end = total_duration

            end = min(end, total_duration)

            if start >= end:
                logger.warning(
                    f"Topic skipped (invalid timestamps): topic={topic} | start={start:.1f}s | end={end:.1f}s",
                    topic=topic,
                    start_sec=round(start, 1),
                    end_sec=round(end, 1),
                )
                continue

            result.append({"topic": topic, "start": start, "end": end})

        return result
