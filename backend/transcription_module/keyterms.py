"""Shared keyterms builder for AssemblyAI keyterms_prompt."""

from __future__ import annotations

_MAX_WORDS_PER_TERM = 6


def compose_keyterms(
    vocabulary: list[str] | None,
    recording_topic: str | None,
    *,
    max_terms: int = 200,
) -> list[str]:
    """Build keyterms list for AssemblyAI keyterms_prompt.

    Rules:
    - Each term must be 1–6 words (AssemblyAI limit).
    - Deduplication is case-insensitive.
    - recording_topic words are prepended so they are prioritised.
    - Result capped at max_terms (200 for Universal-2, 1000 for Universal-3-Pro).
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(term: str) -> None:
        cleaned = term.strip()
        if not cleaned:
            return
        word_count = len(cleaned.split())
        if word_count < 1 or word_count > _MAX_WORDS_PER_TERM:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        result.append(cleaned)

    # Topic first — highest priority
    if recording_topic:
        _add(recording_topic.strip())

    for term in vocabulary or []:
        _add(term)

    return result[:max_terms]
