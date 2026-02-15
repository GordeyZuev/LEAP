"""Prompt templates for transcription (Fireworks/Whisper). Use .format() placeholders."""

# Default base prompt when transcription.prompt is empty. {topic} = recording name / course.
TRANSCRIPTION_DEFAULT_PROMPT = (
    "Это видео-семинар по курсу «{topic}». "
    "Сохраняй правильное написание профильных терминов (включая английские), "
    "аббревиатур и имён собственных. "
    "Учитывай особенности устной речи: неполные предложения, паузы, естественные интонации."
)

# Topic hint for Whisper (when using non-default prompt). Topic = recording name.
TRANSCRIPTION_TOPIC = "Курс: «{topic}». Учитывай специфику курса при распознавании терминов."

# Vocabulary: comma-separated terms that help Whisper (e.g. domain terms, names, abbreviations)
TRANSCRIPTION_VOCABULARY = "Дополнительные термины для учёта при распознавании: {vocabulary}."
