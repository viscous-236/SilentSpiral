"""
tests/test_nlp_engine.py
=========================
Agent Evaluation: NLP engine tests using mocks to avoid loading the
~500MB HuggingFace model in CI/unit test runs.

Evaluation methodology (agent-evaluation principles):
  - Behavioral contract tests: outputs conform to documented contracts
  - Adversarial inputs: empty text, single word, very long text, non-English
  - Boundary conditions: threshold edge cases
  - No output string matching — validate structure, not exact values
  - Mock the model — test OUR code, not HuggingFace's model

Test categories:
  1. Happy path — normal journal text
  2. Threshold filtering — only scores >= threshold included
  3. Fallback — nothing passes threshold → still returns top-1
  4. Adversarial — short/neutral/empty-adjacent text
  5. Behavioral invariants — top_emotion always matches first emotion
"""

from unittest.mock import MagicMock, patch

import pytest


# ── Test helpers ──────────────────────────────────────────────────────────────

def _make_raw_result(emotions: list[tuple[str, float]]) -> list[dict]:
    """Build mock HuggingFace pipeline output for a single input."""
    return [{"label": label, "score": score} for label, score in emotions]


def _run_analyze(mock_emotions: list[tuple[str, float]], text: str = "test") -> dict:
    """
    Run analyze_text with a mocked classifier.
    Clears lru_cache before each call to allow mock injection.
    """
    from app.services import nlp_engine

    mock_pipeline = MagicMock(return_value=[_make_raw_result(mock_emotions)])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        # Re-import to pick up patched model
        result = nlp_engine.analyze_text(text)

    return result


# ── Behavioral contracts ──────────────────────────────────────────────────────


def test_analyze_returns_required_keys():
    """Contract: analyze_text always returns the documented keys."""
    from app.services.nlp_engine import analyze_text
    from unittest.mock import MagicMock, patch
    from app.services import nlp_engine

    mock_result = _make_raw_result([("sadness", 0.82), ("joy", 0.05)])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text("I feel sad today.")

    assert set(result.keys()) == {"emotions", "top_emotion", "intensity", "word_count"}


def test_analyze_top_emotion_matches_first_emotion():
    """Invariant: top_emotion must always equal the first item in emotions."""
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    mock_result = _make_raw_result([("sadness", 0.82), ("joy", 0.05), ("anger", 0.03)])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text("Hard day at work.")

    assert result["top_emotion"] == result["emotions"][0]["label"]


def test_analyze_intensity_equals_top_score():
    """Invariant: intensity must equal the score of the top emotion."""
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    mock_result = _make_raw_result([("joy", 0.9123), ("sadness", 0.05)])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text("Great day!")

    assert result["intensity"] == pytest.approx(0.9123, abs=1e-4)


def test_analyze_emotions_sorted_desc():
    """Contract: emotions list must be sorted by score descending."""
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    # Raw results are intentionally out of order to test sorting
    mock_result = _make_raw_result([
        ("joy", 0.3),
        ("sadness", 0.8),
        ("anger", 0.5),
    ])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text("Mixed feelings today.")

    scores = [e["score"] for e in result["emotions"]]
    assert scores == sorted(scores, reverse=True)


def test_analyze_word_count_correct():
    """Contract: word_count matches actual word count of input."""
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    text = "I feel really sad and confused today"  # 7 words
    mock_result = _make_raw_result([("sadness", 0.8)])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text(text)

    assert result["word_count"] == 7


# ── Threshold filtering ───────────────────────────────────────────────────────


def test_analyze_filters_below_threshold():
    """Only emotions above nlp_emotion_threshold appear in output."""
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    # sadness=0.8 passes default threshold (0.1), joy=0.05 does not
    mock_result = _make_raw_result([("sadness", 0.8), ("joy", 0.05)])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text("Feeling low.")

    labels = [e["label"] for e in result["emotions"]]
    assert "sadness" in labels
    assert "joy" not in labels


def test_analyze_fallback_when_nothing_passes_threshold():
    """
    Edge case: if ALL scores are below threshold, still return 1 result.
    This prevents an empty emotions list from crashing the caller.
    """
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    # All scores below default threshold of 0.1
    mock_result = _make_raw_result([("joy", 0.05), ("sadness", 0.03)])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text("ok")

    assert len(result["emotions"]) >= 1
    assert result["top_emotion"]  # not empty


# ── Adversarial inputs ────────────────────────────────────────────────────────


def test_analyze_adversarial_single_word():
    """Adversarial: single-word input produces valid output structure."""
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    mock_result = _make_raw_result([("neutral", 0.6)])
    mock_pipeline = MagicMock(return_value=[mock_result])

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        result = nlp_engine.analyze_text("Fine.")

    assert isinstance(result["emotions"], list)
    assert isinstance(result["top_emotion"], str)


def test_analyze_raises_on_model_failure():
    """Adversarial: model exception is wrapped as RuntimeError (not leaked)."""
    from app.services import nlp_engine
    from unittest.mock import MagicMock, patch

    mock_pipeline = MagicMock(side_effect=RuntimeError("CUDA OOM"))

    with patch.object(nlp_engine, "_load_model", return_value=mock_pipeline):
        nlp_engine._load_model.cache_clear()
        with pytest.raises(RuntimeError, match="Emotion analysis failed"):
            nlp_engine.analyze_text("Some text")
