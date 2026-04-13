"""Prompt templates for transcription (Fireworks/Whisper). Use .format() placeholders."""

# Default base prompt when transcription.prompt is empty. {topic} = recording name / course.
TRANSCRIPTION_DEFAULT_PROMPT_RU = (
    "Это видео-семинар по курсу «{topic}». "
    "Сохраняй правильное написание профильных терминов (включая английские), "
    "аббревиатур и имён собственных. "
    "Учитывай особенности устной речи: неполные предложения, паузы, естественные интонации."
)

TRANSCRIPTION_DEFAULT_PROMPT_EN = (
    "This is a video lecture from the course «{topic}». "
    "Preserve correct spelling of domain terms (including proper nouns), "
    "abbreviations and technical terms. "
    "Account for features of spoken language: incomplete sentences, pauses, natural intonation."
)

# Topic hint for Whisper (when using non-default prompt). Topic = recording name.
TRANSCRIPTION_TOPIC_RU = "Курс: «{topic}». Учитывай специфику курса при распознавании терминов."
TRANSCRIPTION_TOPIC_EN = "Course: «{topic}». Consider course specifics when recognizing terms."

# Vocabulary: comma-separated terms that help Whisper (e.g. domain terms, names, abbreviations)
TRANSCRIPTION_VOCABULARY_RU = "Дополнительные термины для учёта при распознавании: {vocabulary}."
TRANSCRIPTION_VOCABULARY_EN = "Additional terms to consider when transcribing: {vocabulary}."

# Backward compatibility
TRANSCRIPTION_DEFAULT_PROMPT = TRANSCRIPTION_DEFAULT_PROMPT_RU
TRANSCRIPTION_TOPIC = TRANSCRIPTION_TOPIC_RU
TRANSCRIPTION_VOCABULARY = TRANSCRIPTION_VOCABULARY_RU
