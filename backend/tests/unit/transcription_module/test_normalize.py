"""Unit tests for transcription_module.normalize."""

import pytest

from transcription_module.normalize import build_segments_from_words, extract_words


@pytest.mark.unit
class TestExtractWords:
    def test_ms_to_seconds(self):
        raw = [{"text": "hello", "start": 1000, "end": 1500}]
        words = extract_words(raw)
        assert len(words) == 1
        assert words[0]["start"] == pytest.approx(1.0)
        assert words[0]["end"] == pytest.approx(1.5)

    def test_word_field_alias(self):
        raw = [{"word": "привет", "start": 2000, "end": 2500}]
        words = extract_words(raw)
        assert words[0]["word"] == "привет"

    def test_sorted_by_start(self):
        raw = [
            {"text": "b", "start": 2000, "end": 2100},
            {"text": "a", "start": 1000, "end": 1100},
        ]
        words = extract_words(raw)
        assert words[0]["word"] == "a"
        assert words[1]["word"] == "b"

    def test_skips_empty_text(self):
        raw = [{"text": "", "start": 0, "end": 100}, {"text": "word", "start": 200, "end": 300}]
        words = extract_words(raw)
        assert len(words) == 1

    def test_ids_sequential(self):
        raw = [{"text": f"w{i}", "start": i * 1000, "end": i * 1000 + 500} for i in range(5)]
        words = extract_words(raw)
        assert [w["id"] for w in words] == list(range(5))

    def test_end_clamped_when_lte_start(self):
        raw = [{"text": "word", "start": 1000, "end": 1000}]
        words = extract_words(raw)
        assert words[0]["end"] > words[0]["start"]


@pytest.mark.unit
class TestBuildSegmentsFromWords:
    def _make_words(self, texts_with_times):
        return [
            {"id": i, "word": text, "start": start, "end": end} for i, (text, start, end) in enumerate(texts_with_times)
        ]

    def test_empty_input(self):
        assert build_segments_from_words([]) == []

    def test_single_sentence(self):
        words = self._make_words([("Hello.", 0.0, 0.5)])
        segs = build_segments_from_words(words)
        assert len(segs) == 1
        assert segs[0]["text"] == "Hello."

    def test_sentence_boundary_creates_segments(self):
        words = self._make_words(
            [
                ("First.", 0.0, 1.0),
                ("Second.", 2.0, 3.0),
                ("Third.", 4.0, 5.0),
            ]
        )
        segs = build_segments_from_words(words)
        # Each sentence ending triggers a boundary; segments may merge short ones
        assert len(segs) >= 1
        # All words text must appear in some segment
        full_text = " ".join(s["text"] for s in segs)
        assert "First." in full_text
        assert "Second." in full_text

    def test_segments_have_required_fields(self):
        words = self._make_words([("word", 0.0, 1.0)])
        segs = build_segments_from_words(words)
        assert "id" in segs[0]
        assert "start" in segs[0]
        assert "end" in segs[0]
        assert "text" in segs[0]
