"""Unit tests for transcription_module.keyterms."""

import pytest

from transcription_module.keyterms import compose_keyterms


@pytest.mark.unit
class TestComposeKeyterms:
    def test_basic(self):
        result = compose_keyterms(["Python", "FastAPI"], "Backend разработка")
        assert "Backend разработка" in result
        assert "Python" in result
        assert "FastAPI" in result

    def test_topic_first(self):
        result = compose_keyterms(["Python"], "Мой курс")
        assert result[0] == "Мой курс"

    def test_deduplication_case_insensitive(self):
        result = compose_keyterms(["Python", "python", "PYTHON"], None)
        assert result.count("Python") + result.count("python") + result.count("PYTHON") == 1

    def test_filter_too_many_words(self):
        long_term = "один два три четыре пять шесть семь"  # 7 words — over limit
        result = compose_keyterms([long_term], None)
        assert long_term not in result

    def test_six_words_allowed(self):
        six_words = "один два три четыре пять шесть"
        result = compose_keyterms([six_words], None)
        assert six_words in result

    def test_cap_at_max_terms(self):
        vocab = [f"term{i}" for i in range(300)]
        result = compose_keyterms(vocab, None, max_terms=200)
        assert len(result) == 200

    def test_empty_vocab(self):
        result = compose_keyterms([], "Тема курса")
        assert result == ["Тема курса"]

    def test_none_vocab(self):
        result = compose_keyterms(None, None)
        assert result == []

    def test_empty_topic(self):
        result = compose_keyterms(["FastAPI"], "")
        assert "FastAPI" in result
        assert "" not in result
