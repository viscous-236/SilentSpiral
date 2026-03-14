"""
services/pattern_engine.py
===========================
Core analytics engine that converts a list of EmotionRecords into a
time-windowed statistical summary (WindowStats) and detects behavioural
anomalies (AnomalyFlag).

Design choices
--------------
- Pure functions — no I/O, no side effects — making them trivially testable.
- numpy for vectorised stats (mean, std) instead of manual loops.
- Returns ``None`` when no anomaly is present, keeping callers clean.

Anomaly priority order (first match wins):
  1. HIGH_VOLATILITY   — volatility_score > 0.4
  2. DOWNWARD_SPIRAL   — dominant negative emotion + ≥5 entries
  3. LOW_ENGAGEMENT    — fewer than 2 entries in the window

Kaizen improvements applied
----------------------------
- WindowStats is now a Pydantic BaseModel (standardised with the rest
  of the codebase; removes the hand-rolled model_dump() method).
- avg_scores and volatility_score are rounded at the source (4 dp) so
  all callers get consistent precision without extra ceremony.
- Label collection uses a set comprehension instead of a for-loop.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from app.models.emotion import EmotionRecord

# ── Type aliases ──────────────────────────────────────────────────────────────

AnomalyFlag = Literal["HIGH_VOLATILITY", "DOWNWARD_SPIRAL", "LOW_ENGAGEMENT"]

# Emotions whose sustained dominance indicates a downward spiral
_NEGATIVE_DOMINANT = frozenset({"sadness", "fear", "anger"})

# Thresholds — named constants for visibility and easy tuning
_VOLATILITY_THRESHOLD = 0.4
_SPIRAL_MIN_ENTRIES = 5
_LOW_ENGAGEMENT_MAX = 2
_SCORE_ROUND_DP = 4   # decimal places for all exported scores


# ── Data model ────────────────────────────────────────────────────────────────


class WindowStats(BaseModel):
    """
    Aggregated statistics for a set of EmotionRecords.

    Kaizen: Pydantic BaseModel (instead of a hand-rolled class) so that
    serialisation, validation, and OpenAPI schema generation are consistent
    with the rest of the codebase — no custom model_dump() needed.

    Attributes
    ----------
    avg_scores       : Mean confidence score per emotion label, rounded to 4 dp.
    dominant_emotion : Emotion label with the highest average score.
    volatility_score : Population std-dev of the top-emotion score per entry,
                       measuring how much emotional intensity fluctuates.
    entry_count      : Total number of records included in this window.
    """

    avg_scores: dict[str, float] = Field(
        ..., description="Mean confidence score per emotion label (rounded to 4 dp)"
    )
    dominant_emotion: str = Field(
        ..., description="Emotion label with the highest average score"
    )
    volatility_score: float = Field(
        ..., ge=0.0, description="Population std-dev of top-emotion score per entry"
    )
    entry_count: int = Field(..., ge=1, description="Number of records in this window")


# ── Public API ────────────────────────────────────────────────────────────────


def compute_window(records: list[EmotionRecord], days: int = 7) -> WindowStats:
    """
    Aggregate a list of EmotionRecords into a WindowStats summary.

    Parameters
    ----------
    records : Non-empty list of EmotionRecord objects.
    days    : Informational — the intended window size in days.
              The function does *not* filter by date; callers should
              pre-filter ``records`` to the desired window before passing.

    Returns
    -------
    WindowStats

    Raises
    ------
    ValueError  If ``records`` is empty.
    """
    if not records:
        raise ValueError("records must be non-empty to compute a window")

    # ── Kaizen: set comprehension is clearer than for+update ──────────────────
    all_labels: set[str] = {
        label for rec in records for label in rec.emotions
    }

    # ── Build per-label score arrays (0.0 for absent labels) ─────────────────
    label_arrays: dict[str, np.ndarray] = {
        label: np.array([rec.emotions.get(label, 0.0) for rec in records], dtype=float)
        for label in all_labels
    }

    # ── Average score per label — round at source (Kaizen: consistent precision)
    avg_scores: dict[str, float] = {
        label: round(float(np.mean(arr)), _SCORE_ROUND_DP)
        for label, arr in label_arrays.items()
    }

    # ── Dominant emotion (highest average) ────────────────────────────────────
    dominant_emotion: str = max(avg_scores, key=avg_scores.__getitem__)

    # ── Volatility: std-dev of the *top-scoring emotion per entry* ────────────
    # For each record, pick the score of its highest-confidence emotion.
    top_scores_per_entry = np.array(
        [max(rec.emotions.values()) if rec.emotions else 0.0 for rec in records],
        dtype=float,
    )
    # ddof=0 (population std) — consistent even with small windows (n<2)
    volatility_score: float = round(float(np.std(top_scores_per_entry, ddof=0)), _SCORE_ROUND_DP)

    return WindowStats(
        avg_scores=avg_scores,
        dominant_emotion=dominant_emotion,
        volatility_score=volatility_score,
        entry_count=len(records),
    )


def detect_anomaly(window: WindowStats) -> AnomalyFlag | None:
    """
    Inspect a WindowStats object and return the first matching AnomalyFlag,
    or None if no anomaly is detected.

    Priority order (first match wins)
    ----------------------------------
    1. HIGH_VOLATILITY  — volatility_score > 0.4
    2. DOWNWARD_SPIRAL  — dominant_emotion is negative AND entry_count >= 5
    3. LOW_ENGAGEMENT   — entry_count < 2

    Parameters
    ----------
    window : A computed WindowStats instance.

    Returns
    -------
    AnomalyFlag | None
    """
    # ── Rule 1: emotional instability ─────────────────────────────────────────
    if window.volatility_score > _VOLATILITY_THRESHOLD:
        return "HIGH_VOLATILITY"

    # ── Rule 2: sustained negative dominance ──────────────────────────────────
    if (
        window.dominant_emotion in _NEGATIVE_DOMINANT
        and window.entry_count >= _SPIRAL_MIN_ENTRIES
    ):
        return "DOWNWARD_SPIRAL"

    # ── Rule 3: low data — user barely journalling ────────────────────────────
    if window.entry_count < _LOW_ENGAGEMENT_MAX:
        return "LOW_ENGAGEMENT"

    return None
