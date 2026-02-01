"""Topic extraction from transcription using DeepSeek"""

import re
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from logger import get_logger

from .config import DeepSeekConfig

logger = get_logger(__name__)


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
            model=config.model
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
        if not segments or len(segments) == 0:
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
                detailed_topics=len(topic_timestamps_with_end)
            )

            return {
                "topic_timestamps": topic_timestamps_with_end,
                "main_topics": main_topics,
                "long_pauses": result.get("long_pauses", []),
            }
        except Exception as error:
            logger.exception(
                f"Failed to extract topics: error={error}",
                error=str(error)
            )
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

        segments = []
        timestamp_pattern = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2}):(\d{2})\]\s*(.+)")
        timestamp_pattern_ms = re.compile(
            r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.+)"
        )

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
                        logger.warning(
                            f"⚠️ Ошибка парсинга строки {line_num} в файле {segments_file_path}: {line[:50]}... - {e}"
                        )
                        continue

        if not segments:
            raise ValueError(f"Не удалось извлечь сегменты из файла {segments_file_path}")

        logger.info(f"Read {len(segments)} segments from file {segments_file_path}")

        return await self.extract_topics(
            segments=segments,
            recording_topic=recording_topic,
            granularity=granularity,
        )

    def _format_transcript_with_timestamps(self, segments: list[dict]) -> str:
        """
        Форматирование транскрипции с временными метками.

        Args:
            segments: Список сегментов с временными метками

        Returns:
            Отформатированная транскрипция
        """
        segments_text = []
        noise_patterns = [
            r"редактор субтитров",
            r"корректор",
            r"продолжение следует",
        ]
        # Оцениваем, есть ли длинное окно шума (15+ минут подряд)
        noise_times = []
        for seg in segments:
            text0 = (seg.get("text") or "").strip().lower()
            if text0 and any(re.search(pat, text0) for pat in noise_patterns):
                try:
                    noise_times.append(float(seg.get("start", 0)))
                except Exception as e:
                    logger.debug(f"Failed to parse noise segment start time: {e}")
        exclude_from = None
        exclude_to = None
        if noise_times:
            first_noise = min(noise_times)
            last_noise = max(noise_times)
            if (last_noise - first_noise) >= 15 * 60:
                exclude_from, exclude_to = first_noise, last_noise

        for seg in segments:
            start = seg.get("start", 0)
            text = seg.get("text", "").strip()
            if text:
                lowered = text.lower()
                # Пропускаем шумовые строки
                if any(re.search(pat, lowered) for pat in noise_patterns):
                    continue
                # Пропускаем всё, что попало в длинное окно шума
                if exclude_from is not None and exclude_to is not None:
                    try:
                        if exclude_from <= float(start) <= exclude_to:
                            continue
                    except Exception as e:
                        logger.debug(f"Failed to check segment time range: {e}")
                hours = int(start // 3600)
                minutes = int((start % 3600) // 60)
                seconds = int(start % 60)
                time_str = f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
                segments_text.append(f"{time_str} {text}")

        return "\n".join(segments_text)

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

        long_pauses = self._detect_long_pauses(segments or [], min_gap_minutes=8)
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
            logger.exception(
                f"Failed to analyze transcript: error={error}",
                error=str(error)
            )
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

        # Fireworks API: для всех моделей запросы с max_tokens > 4096 требуют stream=true
        # Для не-потоковых запросов ограничиваем max_tokens до 4096
        if params.get("max_tokens", 0) > 4096:
            logger.warning(
                f"⚠️ max_tokens={params.get('max_tokens')} превышает лимит Fireworks для не-потоковых запросов (4096). "
                f"Уменьшаем до 4096. Для большего значения требуется stream=true."
            )
            params["max_tokens"] = 4096

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
                    error_text = response.text
                    try:
                        error_data = response.json()
                        error_text = str(error_data)
                    except Exception as e:
                        logger.debug(f"Failed to parse error response as JSON: {e}")

                    logger.error(
                        f"❌ Ошибка Fireworks API (status {response.status_code}):\n"
                        f"URL: {url}\n"
                        f"Payload keys: {list(payload.keys())}\n"
                        f"Payload params: {params}\n"
                        f"Response: {error_text[:2000]}"
                    )
                    response.raise_for_status()

                data = response.json()

                if "choices" not in data or not data["choices"]:
                    raise ValueError(f"Неожиданный формат ответа от Fireworks API: {data}")

                return data["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as e:
                if e.response is not None:
                    try:
                        error_data = e.response.json()
                        logger.error(f"Fireworks API error: data={error_data}", error_data=error_data)
                    except Exception:
                        error_text = e.response.text
                        logger.error(f"Fireworks API error: text={error_text[:1000]}", error_text=error_text[:1000])
                raise

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
        """Форматирование секунд в HH:MM:SS"""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
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

        timestamp_pattern = r"\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*[-–—]?\s*(.+)"

        # Сначала ищем основную тему в начале ответа (до секции детализированных топиков)
        found_main_topic_before_section = False
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            if "ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ" in line_stripped.upper() or "ТОПИКИ С ТАЙМКОДАМИ" in line_stripped.upper():
                # Look for topic in previous 10 lines
                for j in range(max(0, i - 10), i):
                    candidate = lines[j].strip()
                    if candidate and not candidate.startswith("##") and not candidate.startswith("#"):
                        if (
                            "выведи" in candidate.lower()
                            or "тема" in candidate.lower()
                            or "пример" in candidate.lower()
                        ):
                            continue
                        if re.match(timestamp_pattern, candidate):
                            continue
                        topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", candidate).strip()
                        topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
                        if topic_candidate:
                            words = topic_candidate.split()
                            # Основная тема должна быть короткой (2-4 слова)
                            if 2 <= len(words) <= 4:
                                main_topics.append(topic_candidate)
                                found_main_topic_before_section = True
                                break
                break

        # Если не нашли тему перед секцией, проверяем первые строки ответа
        if not found_main_topic_before_section:
            for _, line in enumerate(lines[:10]):
                line_stripped = line.strip()
                if not line_stripped or line_stripped.startswith(("##", "#")):
                    continue
                if re.match(timestamp_pattern, line_stripped):
                    break
                if (
                    "выведи" in line_stripped.lower()
                    or "тема" in line_stripped.lower()
                    or "пример" in line_stripped.lower()
                ):
                    continue
                topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", line_stripped).strip()
                topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
                if topic_candidate:
                    words = topic_candidate.split()
                    if 2 <= len(words) <= 4:
                        main_topics.append(topic_candidate)
                        break

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
            timestamp_match = re.match(timestamp_pattern, line)
            if timestamp_match:
                in_detailed_topics = True
                in_main_topics = False
                # Парсим топик сразу
                hours_str, minutes_str, seconds_str, topic = timestamp_match.groups()
                if seconds_str is None:
                    hours = 0
                    minutes = int(hours_str)
                    seconds = int(minutes_str)
                else:
                    hours = int(hours_str)
                    minutes = int(minutes_str)
                    seconds = int(seconds_str)
                total_seconds = hours * 3600 + minutes * 60 + seconds
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
                match = re.match(timestamp_pattern, line)
                if match:
                    hours_str, minutes_str, seconds_str, topic = match.groups()

                    if seconds_str is None:
                        hours = 0
                        minutes = int(hours_str)
                        seconds = int(minutes_str)
                    else:
                        hours = int(hours_str)
                        minutes = int(minutes_str)
                        seconds = int(seconds_str)

                    total_seconds = hours * 3600 + minutes * 60 + seconds

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
                            valid_range=f"0-{round(total_duration / 60, 1)}"
                        )

        # Если не нашли топики через секции, пробуем парсить все строки с временными метками
        if not topic_timestamps:
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                match = re.match(timestamp_pattern, line)
                if match:
                    hours_str, minutes_str, seconds_str, topic = match.groups()
                    if seconds_str is None:
                        hours = 0
                        minutes = int(hours_str)
                        seconds = int(minutes_str)
                    else:
                        hours = int(hours_str)
                        minutes = int(minutes_str)
                        seconds = int(seconds_str)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    if 0 <= total_seconds <= total_duration:
                        topic_timestamps.append(
                            {
                                "topic": topic.strip(),
                                "start": float(total_seconds),
                            }
                        )

        if not topic_timestamps and not main_topics:
            topic_timestamps = self._parse_simple_timestamps(text, total_duration)

        if main_topics_section_found and not main_topics:
            logger.debug("Main topics section found but topics not extracted. Searching for topic at response start")
            for i, line in enumerate(lines):
                if "ОСНОВНЫЕ ТЕМЫ" in line.upper() or "ОСНОВНЫЕ ТЕМЫ ПАРЫ" in line.upper():
                    for j in range(i + 1, min(i + 5, len(lines))):
                        candidate = lines[j].strip()
                        if candidate and not candidate.startswith("##") and not candidate.startswith("#"):
                            topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", candidate).strip()
                            topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
                            if (
                                topic_candidate
                                and len(topic_candidate) > 3
                                and "выведи" not in topic_candidate.lower()
                                and "тема" not in topic_candidate.lower()
                                and "пример" not in topic_candidate.lower()
                            ):
                                words = topic_candidate.split()
                                if 2 <= len(words) <= 4:
                                    main_topics.append(topic_candidate)
                                    break
                    break

        processed_main_topics = []
        for topic in main_topics[:1]:
            topic = " ".join(topic.split())
            if topic and len(topic) > 3:
                words = topic.split()
                if len(words) > 7:
                    topic = " ".join(words[:7]) + "..."
                processed_main_topics.append(topic)

        if processed_main_topics:
            logger.info(f"Main topic: {processed_main_topics[0]}")
        if not processed_main_topics and main_topics_section_found:
            logger.warning(
                f"⚠️ Секция основных тем найдена, но не удалось извлечь тему. Первые строки ответа:\n{chr(10).join(lines[:10])}"
            )

        return {
            "main_topics": processed_main_topics,
            "topic_timestamps": topic_timestamps,
        }

    def _parse_simple_timestamps(self, text: str, total_duration: float) -> list[dict]:
        """
        Парсинг простого формата временных меток (fallback).

        Формат: [HH:MM:SS] - [Название] или [HH:MM:SS] [Название]

        Args:
            text: Текст ответа
            total_duration: Общая длительность видео

        Returns:
            Список временных меток
        """
        timestamps = []
        lines = text.split("\n")

        # Паттерн для [HH:MM:SS] - [Название] или [HH:MM:SS] [Название]
        pattern = r"\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*[-–—]?\s*(.+)"

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = re.match(pattern, line)
            if match:
                hours_str, minutes_str, seconds_str, topic = match.groups()

                if seconds_str is None:
                    hours = 0
                    minutes = int(hours_str)
                    seconds = int(minutes_str)
                else:
                    hours = int(hours_str)
                    minutes = int(minutes_str)
                    seconds = int(seconds_str)

                total_seconds = hours * 3600 + minutes * 60 + seconds

                if 0 <= total_seconds <= total_duration:
                    timestamps.append(
                        {
                            "topic": topic.strip(),
                            "start": float(total_seconds),
                        }
                    )

        return timestamps

    def _filter_and_merge_topics(
        self, timestamps: list[dict], total_duration: float, min_topics: int = 10, max_topics: int = 30
    ) -> list[dict]:
        """
        Фильтрация и объединение топиков для получения нужного диапазона.

        Объединяет близкие по времени топики и ограничивает общее количество.

        Args:
            timestamps: Список всех топиков с start
            total_duration: Общая длительность видео в секундах
            min_topics: Минимальное количество топиков
            max_topics: Максимальное количество топиков

        Returns:
            Отфильтрованный список топиков
        """
        if not timestamps:
            return []

        duration_minutes = total_duration / 60
        min_spacing = max(180, min(300, duration_minutes * 60 * 0.04))

        sorted_timestamps = sorted(timestamps, key=lambda x: x.get("start", 0))

        if len(sorted_timestamps) <= max_topics:
            merged = []

            for ts in sorted_timestamps:
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

        target_count = max_topics
        step = len(sorted_timestamps) / target_count

        filtered = []
        for i in range(target_count):
            idx = int(i * step)
            if idx < len(sorted_timestamps):
                filtered.append(sorted_timestamps[idx])

        merged = []

        for ts in filtered:
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

        if len(merged) < min_topics:
            additional_step = len(sorted_timestamps) / (min_topics - len(merged))
            added_indices = set()

            for i in range(min_topics - len(merged)):
                idx = int(i * additional_step)
                if idx < len(sorted_timestamps):
                    if idx not in added_indices:
                        ts = sorted_timestamps[idx]
                        start = ts.get("start", 0)
                        topic = ts.get("topic", "").strip()

                        if topic:
                            too_close = False
                            for existing in merged:
                                if abs(start - existing.get("start", 0)) < min_spacing:
                                    too_close = True
                                    break

                            if not too_close:
                                merged.append(ts)
                                added_indices.add(idx)

            # Сортируем по времени
            merged = sorted(merged, key=lambda x: x.get("start", 0))

        return merged

    def _add_end_timestamps(self, timestamps: list[dict], total_duration: float) -> list[dict]:
        """
        Добавление временных меток end для каждой темы.

        Args:
            timestamps: Список тем с start
            total_duration: Общая длительность видео

        Returns:
            Список тем с start и end
        """
        if not timestamps:
            return []

        sorted_timestamps = sorted(timestamps, key=lambda x: x.get("start", 0))

        result = []
        for i, ts in enumerate(sorted_timestamps):
            start = ts.get("start", 0)
            topic = ts.get("topic", "").strip()

            if not topic:
                continue

            if i < len(sorted_timestamps) - 1:
                end = sorted_timestamps[i + 1].get("start", 0)
            else:
                end = total_duration

            # Гарантируем минимальную длительность
            if end - start < 60 and i < len(sorted_timestamps) - 1:
                end = min(start + 60, sorted_timestamps[i + 1].get("start", 0))

            end = min(end, total_duration)

            if start >= end:
                logger.warning(
                    f"Topic skipped (invalid timestamps): topic={topic} | start={start:.1f}s | end={end:.1f}s",
                    topic=topic,
                    start_sec=round(start, 1),
                    end_sec=round(end, 1)
                )
                continue

            result.append(
                {
                    "topic": topic,
                    "start": start,
                    "end": end,
                }
            )

        return result
