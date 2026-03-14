"""
NLP Emotion Engine
==================
Wraps the HuggingFace GoEmotions classifier model.

Model: SamLowe/roberta-base-go_emotions
- 28 emotion labels (admiration, anger, anxiety, sadness, joy, etc.)
- Returns confidence scores per label
- Loaded once at startup (singleton pattern) for performance
"""

import logging
from functools import lru_cache

from transformers import pipeline

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    """
    Load the GoEmotions model once and cache it.

    lru_cache(maxsize=1) ensures this runs only on first call.
    Subsequent calls return the cached pipeline object instantly.
    """
    logger.info("Loading NLP model: %s", settings.nlp_model_name)
    classifier = pipeline(
        task="text-classification",
        model=settings.nlp_model_name,
        top_k=None,  # Return ALL label scores, we filter below
        device=-1,   # Force CPU (-1). Change to 0 for GPU if available.
    )
    logger.info("NLP model loaded successfully.")
    return classifier


def analyze_text(text: str) -> dict:
    """
    Analyze journal text and return emotion scores.

    Args:
        text: Raw journal entry text (max ~512 tokens; will be truncated silently)

    Returns:
        {
            "emotions": [{"label": str, "score": float}, ...],  # above threshold, sorted desc
            "top_emotion": str,
            "intensity": float,
            "word_count": int,
        }

    Raises:
        RuntimeError: If model inference fails unexpectedly
    """
    # Poka-Yoke: empty text produces a meaningless single-token result.
    # Reject early with a clear ValueError so callers get an actionable message.
    if not text.strip():
        raise ValueError("analyze_text requires non-empty input text.")

    classifier = _load_model()

    try:
        # The pipeline returns [[{"label":..., "score":...}, ...]]
        raw_results: list[dict] = classifier(
            text,
            truncation=True,     # Silently truncate at 512 tokens
            max_length=512,
        )[0]
    except Exception as exc:
        logger.error("NLP inference error: %s", exc, exc_info=True)
        raise RuntimeError("Emotion analysis failed. See logs for details.") from exc

    # Filter by threshold and sort by score descending
    filtered = sorted(
        [r for r in raw_results if r["score"] >= settings.nlp_emotion_threshold],
        key=lambda x: x["score"],
        reverse=True,
    )

    # Cap at top_k results
    top_results = filtered[: settings.nlp_top_k]

    # If nothing passed threshold (very short/neutral text), take the top 1
    if not top_results and raw_results:
        best = max(raw_results, key=lambda x: x["score"])
        top_results = [best]

    top = top_results[0]

    return {
        "emotions": top_results,
        "top_emotion": top["label"],
        "intensity": round(top["score"], 4),
        "word_count": len(text.split()),
    }
