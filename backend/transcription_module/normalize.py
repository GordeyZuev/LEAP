"""Shared normalization helpers for ASR provider responses → LEAP format."""

from __future__ import annotations

from typing import Any


def extract_words(raw_words: list[Any]) -> list[dict[str, Any]]:
    """Normalize word list from AssemblyAI response to LEAP format.

    AssemblyAI words have start/end in milliseconds → convert to seconds.
    Output shape: [{id, start, end, word}]
    """
    words: list[dict[str, Any]] = []
    for item in raw_words:
        if isinstance(item, dict):
            word_dict = item
        elif hasattr(item, "model_dump"):
            word_dict = item.model_dump()
        elif hasattr(item, "to_dict"):
            word_dict = item.to_dict()
        else:
            continue

        text = (word_dict.get("text") or word_dict.get("word") or "").strip()
        if not text:
            continue

        start_ms = word_dict.get("start") or 0
        end_ms = word_dict.get("end") or 0

        start_s = float(start_ms) / 1000.0 if isinstance(start_ms, (int, float)) else 0.0
        end_s = float(end_ms) / 1000.0 if isinstance(end_ms, (int, float)) else 0.0

        if end_s <= start_s:
            end_s = start_s + 0.1

        words.append({"id": len(words), "start": start_s, "end": end_s, "word": text})

    words.sort(key=lambda x: x["start"])
    return words


# Legacy: heuristic segment builder (pause/punctuation/duration thresholds).
# Primary path uses AssemblyAI /sentences endpoint; this is the fallback.
def build_segments_from_words(
    words: list[dict[str, Any]],
    max_duration_seconds: float = 8.0,
    pause_threshold_seconds: float = 0.4,
) -> list[dict[str, Any]]:
    """Build segments from word list using sentence boundaries, pauses, duration limits."""
    if not words:
        return []

    sentence_endings = (".", "!", "?", "…")
    comma_punctuation = (",",)
    pause_for_comma = 0.25
    min_group_duration_for_pause_break = 0.7
    min_words_for_break = 3
    short_segment_duration = 1.2
    short_segment_words = 3

    segments: list[dict[str, Any]] = []
    current_group: list[dict[str, Any]] = []
    current_start: float | None = None
    segment_id = 0

    def _finalize(group: list[dict[str, Any]], start: float) -> dict[str, Any] | None:
        if not group or start is None:
            return None
        group_text = " ".join(w.get("word", "").strip() for w in group)
        if not group_text.strip():
            return None
        group_end = float(group[-1].get("end", 0.0))
        if group_end <= start:
            group_end = start + 0.1
        return {"id": segment_id, "start": start, "end": group_end, "text": group_text.strip()}

    for word_item in words:
        word_start = float(word_item.get("start", 0.0))
        word_end = float(word_item.get("end", 0.0))
        word_text = word_item.get("word", "").strip()

        if not word_text:
            continue
        if word_end <= word_start:
            word_end = word_start + 0.1

        word_item = {**word_item, "start": word_start, "end": word_end}

        if current_start is None:
            current_start = word_start

        pause_duration = 0.0
        if current_group:
            pause_duration = word_start - float(current_group[-1].get("end", 0.0))

        ends_with_sentence = word_text.endswith(sentence_endings)
        ends_with_comma = word_text.endswith(comma_punctuation)
        current_group_duration = (
            (float(current_group[-1].get("end", 0.0)) - current_start)
            if current_group and current_start is not None
            else 0.0
        )
        enough_group = (
            current_group_duration >= min_group_duration_for_pause_break or len(current_group) >= min_words_for_break
        )

        should_break_pause = pause_duration > pause_threshold_seconds and enough_group
        should_break_comma = ends_with_comma and pause_duration > pause_for_comma and enough_group
        group_duration_after = word_end - current_start
        should_break_duration = group_duration_after > max_duration_seconds and enough_group
        should_break_before = (
            should_break_pause or should_break_comma or should_break_duration
        ) and not ends_with_sentence

        if should_break_before and current_group and current_start is not None:
            seg = _finalize(current_group, current_start)
            if seg:
                segments.append(seg)
                segment_id += 1
            current_group = []
            current_start = word_start

        current_group.append(word_item)

        if ends_with_sentence and current_group and current_start is not None:
            seg = _finalize(current_group, current_start)
            if seg:
                segments.append(seg)
                segment_id += 1
            current_group = []
            current_start = None

    if current_group and current_start is not None:
        seg = _finalize(current_group, current_start)
        if seg:
            segments.append(seg)

    if not segments:
        return segments

    merged: list[dict[str, Any]] = []
    for seg in segments:
        word_count = len(seg.get("text", "").split())
        duration = seg.get("end", 0.0) - seg.get("start", 0.0)
        if merged and word_count < short_segment_words and duration < short_segment_duration:
            prev = merged.pop()
            merged.append(
                {
                    "id": prev["id"],
                    "start": prev["start"],
                    "end": seg["end"],
                    "text": f"{prev['text']} {seg['text']}".strip(),
                }
            )
        else:
            merged.append(seg)

    for idx, seg in enumerate(merged):
        seg["id"] = idx

    return merged
