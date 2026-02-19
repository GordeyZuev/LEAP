"""Prompt templates for topic extraction. All prompts use .format() placeholders."""

SYSTEM_PROMPT = (
    "Ты — самый лучший аналитик учебных материалов на магистратуре Computer Science. "
    "Анализируй транскрипции и выделяй структуру видео."
)

# Single template with duration placeholders: duration_rule, duration_min, duration_max, duration_range, split_instruction
TOPIC_EXTRACTION_PROMPT = """Проанализируй транскрипцию учебного видео и выдели структуру:{context_line}{pauses_instruction}

## САММАРИ ВИДЕО

Краткое содержание в 2–4 предложения: что обсуждалось, основные идеи. Язык: {summary_language}.

## ОСНОВНАЯ ТЕМА ВИДЕО

Выведи РОВНО ОДНУ тему (2–4 слова):{recording_topic_hint}

Название темы

Примеры: "Stable Diffusion", "Архитектура трансформеров", "Generative Models"

## ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ ({min_topics}-{max_topics} топиков)

Формат: [HH:MM:SS] - Название топика

КРИТИЧЕСКИЕ ПРАВИЛА:
1. Количество: РОВНО {min_topics}-{max_topics} топиков. Если больше — объедини похожие.
2. Длительность: {duration_rule}
3. Если тема <{duration_min} минут — ОБЯЗАТЕЛЬНО объедини с соседней.
4. Если тема >{duration_max} минут — ОБЯЗАТЕЛЬНО {split_instruction}
5. Минимальный шаг между темами: {min_spacing_minutes:.1f} минут.
6. Названия: 3–6 слов, информативные, на русском или английском (по терминологии).
7. Хронологический порядок.
8. Только фактические темы из транскрипции.
9. ВАЖНО: Используй РЕАЛЬНЫЕ временные метки из транскрипции [HH:MM:SS], не придумывай свои.

Перед отправкой проверь: количество тем, длительность каждой ({duration_range} мин), перерывы >=8 мин.
Если нарушено — переразметь до полного соответствия.

Транскрипция:
{transcript}
"""

# Duration config per granularity
DURATION_CONFIG = {
    "short": {
        "duration_rule": "МИНИМУМ 5 минут, МАКСИМУМ 40 минут на тему.",
        "duration_min": 5,
        "duration_max": 40,
        "duration_range": "5–40",
        "split_instruction": "разбей на несколько тем по 5–40 минут каждая",
    },
    "medium": {
        "duration_rule": "МИНИМУМ 4 минуты, МАКСИМУМ 20 минут на тему.",
        "duration_min": 4,
        "duration_max": 20,
        "duration_range": "4–20",
        "split_instruction": "разбей на несколько тем по 4–20 минут каждая",
    },
    "long": {
        "duration_rule": "МИНИМУМ 3–4 минуты, МАКСИМУМ 12 минут на тему.",
        "duration_min": 3,
        "duration_max": 12,
        "duration_range": "3–12",
        "split_instruction": "разбей на 2–3 темы",
    },
}
