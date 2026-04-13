SYSTEM_PROMPT = "Ты — самый лучший аналитик учебных материалов. Анализируй транскрипции и выделяй структуру видео."

SYSTEM_PROMPT_EN = (
    "You are an expert analyst of educational content. Analyze transcripts and extract the video structure."
)

TOPIC_EXTRACTION_PROMPT = """Проанализируй транскрипцию видео и выдели структуру:{context_line}{pauses_instruction}

## САММАРИ ВИДЕО

Краткое содержание в 2–4 предложения: что обсуждалось, основные идеи. Язык: {summary_language}.

## ОСНОВНАЯ ТЕМА ВИДЕО

Выведи РОВНО ОДНУ тему (2–5 слова, не более):{recording_topic_hint}

Название темы

Примеры: "Stable Diffusion", "Архитектура трансформеров", "SQL и ORM в Python"

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

## ВОПРОСЫ ДЛЯ САМОПРОВЕРКИ

Сформулируй вопросы для самопроверки. Количество: {questions_count}. Критерии:
- Опираться на ключевые идеи из транскрипции
- Открытая форма (что? как? почему?)
- Покрывать разные части материала
- Язык: {summary_language}

Формат: по одному вопросу на строку с номером (1. 2. 3.)

Транскрипция:
{transcript}
"""

TOPIC_EXTRACTION_PROMPT_EN = """Analyze the video transcript and extract its structure:{context_line}{pauses_instruction}

## VIDEO SUMMARY

Brief summary in 2–4 sentences: what was discussed and the main ideas. Language: {summary_language}.

## MAIN VIDEO TOPIC

Output EXACTLY ONE topic (2–5 words, no more):{recording_topic_hint}

Topic title

Examples: "Stable Diffusion", "Transformer architecture", "SQL and ORM in Python"

## DETAILED TOPICS ({min_topics}-{max_topics} topics)

Format: [HH:MM:SS] - Topic title

CRITICAL RULES:
1. Count: EXACTLY {min_topics}-{max_topics} topics. If more — merge similar ones.
2. Duration: {duration_rule}
3. If a topic is <{duration_min} minutes — MUST merge with a neighbor.
4. If a topic is >{duration_max} minutes — MUST {split_instruction}
5. Minimum spacing between topics: {min_spacing_minutes:.1f} minutes.
6. Titles: 3–6 words, informative, in Russian or English as appropriate for terminology.
7. Chronological order.
8. Only factual topics from the transcript.
9. IMPORTANT: Use REAL timestamps from the transcript [HH:MM:SS]; do not invent times.

Before sending, verify: topic count, each topic duration ({duration_range} min), gaps >=8 min.
If violated — relabel until fully compliant.

## SELF-CHECK QUESTIONS

Write self-check questions. Count: {questions_count}. Criteria:
- Grounded in key ideas from the transcript
- Open-ended (what? how? why?)
- Cover different parts of the material
- Language: {summary_language}

Format: one question per line with a number (1. 2. 3.)

Transcript:
{transcript}
"""

# Keys match Granularity enum. Prompt text derived in topic_extractor from duration_min/max.
GRANULARITY_CONFIG = {
    "short": {
        "duration_min": 5,
        "duration_max": 40,
        "spacing_min": 10,
        "spacing_max": 18,
        "spacing_factor": 0.12,
    },
    "medium": {
        "duration_min": 4,
        "duration_max": 20,
        "spacing_min": 6,
        "spacing_max": 10,
        "spacing_factor": 0.08,
    },
    "long": {
        "duration_min": 3,
        "duration_max": 12,
        "split_instruction": "разбей на 2–3 темы",
        "split_instruction_en": "split into 2–3 topics",
        "spacing_min": 4,
        "spacing_max": 6,
        "spacing_factor": 0.05,
    },
}
