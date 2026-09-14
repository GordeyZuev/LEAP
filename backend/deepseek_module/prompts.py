SYSTEM_PROMPT = (
    "Ты — аналитик учебных материалов. Анализируй транскрипции и выделяй структуру видео. "
    "Ответ — один json-объект по схеме из запроса: без markdown, без комментариев, без лишних ключей."
)

SYSTEM_PROMPT_EN = (
    "You are an expert analyst of educational content. Analyze transcripts and extract the video structure. "
    "Reply with one json object matching the requested schema: no markdown, no commentary, no extra keys."
)

# Injected via .format({json_example}); braces in this string are not template fields.
JSON_EXAMPLE = """{
  "summary": "Brief overview of what the lecture covered.",
  "main_topic": "SQL joins",
  "chapters": [
    {"start": "00:05:10", "title": "Inner join syntax"},
    {"start": "00:18:40", "title": "Outer join pitfalls"}
  ],
  "questions": ["How does an inner join differ from a left join?"]
}"""

TOPIC_EXTRACTION_PROMPT = """Проанализируй транскрипцию видео и выдели структуру. Верни json-объект той же схемы, что в примере.{context_line}

Пример json:
{json_example}

## Саммари
Краткое содержание в 2–4 предложения: что обсуждалось, основные идеи. Язык: {summary_language}.

## Основная тема
Ровно одна тема, {main_topic_min_words}–{main_topic_max_words} слов, не более.{recording_topic_hint}

## Главы ({min_topics}–{max_topics})

Каждая глава: start строго HH:MM:SS (три части) и title. Без markdown в значениях.

Критические правила:
1. Количество: {min_topics}–{max_topics} глав. Если больше — объедини похожие.
2. Длительность: {duration_rule}
3. Если глава <{duration_min} минут — обязательно объедини с соседней.
4. Если глава >{duration_max} минут — обязательно {split_instruction}
5. Минимальный шаг между главами: {min_spacing_minutes:.1f} минут.
6. Названия: 3–6 слов, информативные, на русском или английском (по терминологии лекции).
7. Хронологический порядок.
8. Только фактические темы из транскрипции, не выдумывай.
9. Используй реальные временные метки из транскрипции HH:MM:SS, не придумывай свои.

Перед отправкой проверь: число глав, длительность каждой ({duration_range} мин), хронология, факты из текста.
Если нарушено — переразметь до соответствия.

## Вопросы для самопроверки
Количество: {questions_count}. Критерии:
- опираться на ключевые идеи из транскрипции
- открытая форма (что? как? почему?)
- покрывать разные части материала
- язык: {summary_language}

Транскрипция:
{transcript}
"""

TOPIC_EXTRACTION_PROMPT_EN = """Analyze the video transcript and extract its structure. Return a json object with the same schema as the example.{context_line}

Example json:
{json_example}

## Summary
Brief summary in 2–4 sentences: what was discussed and the main ideas. Language: {summary_language}.

## Main topic
Exactly one topic, {main_topic_min_words}–{main_topic_max_words} words, no more.{recording_topic_hint}

## Chapters ({min_topics}–{max_topics})

Each chapter: start must be HH:MM:SS (three parts) and title. No markdown inside values.

Critical rules:
1. Count: {min_topics}–{max_topics} chapters. If more — merge similar ones.
2. Duration: {duration_rule}
3. If a chapter is <{duration_min} minutes — must merge with a neighbor.
4. If a chapter is >{duration_max} minutes — must {split_instruction}
5. Minimum spacing between chapters: {min_spacing_minutes:.1f} minutes.
6. Titles: 3–6 words, informative, in Russian or English as used in the lecture terminology.
7. Chronological order.
8. Only factual topics from the transcript; do not invent.
9. Use real transcript timestamps HH:MM:SS; do not invent times.

Before sending, verify: chapter count, each chapter duration ({duration_range} min), chronology, facts from the text.
If violated — relabel until compliant.

## Self-check questions
Count: {questions_count}. Criteria:
- grounded in key ideas from the transcript
- open-ended (what? how? why?)
- cover different parts of the material
- language: {summary_language}

Transcript:
{transcript}
"""

# Keys match Granularity enum. split_instruction is generated in code (RU/EN).
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
        "spacing_min": 4,
        "spacing_max": 6,
        "spacing_factor": 0.05,
    },
}
