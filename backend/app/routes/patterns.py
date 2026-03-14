"""
routes/patterns.py
==================
POST /patterns/analyze — accepts a list of EmotionRecords, runs the
pattern engine, and returns WindowStats + optional AnomalyFlag.

Kaizen improvements applied
----------------------------
- Poka-Yoke: max_length=90 on the records list prevents unbounded payloads
  (90 days = practical upper limit; Pydantic rejects larger lists at 422).
- Response building simplified: WindowStats is now a Pydantic BaseModel,
  so WindowStatsResponse is constructed directly from model_fields instead
  of going through model_dump() → dict unpacking.
- Explicit status_code=200 and response_description make the OpenAPI spec
  self-documenting without requiring readers to infer the contract.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.emotion import EmotionRecord
from app.services.pattern_engine import (
    AnomalyFlag,
    WindowStats,
    compute_window,
    detect_anomaly,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patterns", tags=["Patterns"])


# ── Response schemas ──────────────────────────────────────────────────────────
# Co-located with the route because they are tightly coupled to the
# pattern_engine service contract and are not reused elsewhere (JIT).


class WindowStatsResponse(BaseModel):
    """Aggregated emotion statistics over the submitted window."""

    avg_scores: dict[str, float] = Field(
        ..., description="Mean confidence score per emotion label (rounded to 4 dp)"
    )
    dominant_emotion: str = Field(
        ..., description="Emotion label with the highest average score"
    )
    volatility_score: float = Field(
        ...,
        ge=0.0,
        description=(
            "Population std-dev of the top-emotion score per entry. "
            "Higher values = more erratic emotional swings."
        ),
    )
    entry_count: int = Field(..., ge=1, description="Number of records in this window")

    @classmethod
    def from_window(cls, window: WindowStats) -> "WindowStatsResponse":
        """Kaizen: factory method keeps construction logic in one place."""
        return cls(
            avg_scores=window.avg_scores,
            dominant_emotion=window.dominant_emotion,
            volatility_score=window.volatility_score,
            entry_count=window.entry_count,
        )


class PatternAnalysisResponse(BaseModel):
    """Full response from POST /patterns/analyze."""

    window: WindowStatsResponse = Field(..., description="Aggregated window statistics")
    anomaly: AnomalyFlag | None = Field(
        None,
        description=(
            "Detected anomaly flag, or null if behaviour is within normal range. "
            "One of: HIGH_VOLATILITY | DOWNWARD_SPIRAL | LOW_ENGAGEMENT"
        ),
    )


# ── Request schema ────────────────────────────────────────────────────────────


class PatternAnalysisRequest(BaseModel):
    """Request body: a list of EmotionRecords to analyse."""

    records: list[EmotionRecord] = Field(
        ...,
        min_length=1,
        # Kaizen / Poka-Yoke: cap at 90 records (≈90-day window).
        # Without this, a caller could send thousands of records and starve
        # the server. Pydantic returns 422 automatically — no extra code needed.
        max_length=90,
        description=(
            "Ordered list of EmotionRecords. "
            "Minimum 1, maximum 90 (≈90-day window)."
        ),
    )


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post(
    "/analyze",
    status_code=200,
    response_model=PatternAnalysisResponse,
    response_description="WindowStats and optional AnomalyFlag",
    summary="Analyse an emotion record window for patterns and anomalies",
    description=(
        "Accepts 1–90 EmotionRecords (typically a 7-day history) and returns "
        "aggregated WindowStats (avg scores, dominant emotion, volatility) plus an "
        "optional AnomalyFlag if a concerning behavioural pattern is detected."
    ),
)
async def analyze_patterns(body: PatternAnalysisRequest) -> PatternAnalysisResponse:
    """
    POST /patterns/analyze

    Returns WindowStats and an AnomalyFlag (or null) based on the submitted
    emotion history. Pydantic validates the payload; ValueError from the
    engine is surfaced as HTTP 400.
    """
    logger.info("Pattern analysis requested for %d records", len(body.records))

    try:
        window = compute_window(body.records)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    flag = detect_anomaly(window)

    if flag:
        logger.warning(
            "Anomaly detected: %s | dominant=%s volatility=%.4f entries=%d",
            flag, window.dominant_emotion, window.volatility_score, window.entry_count,
        )
    else:
        logger.info(
            "No anomaly | dominant=%s volatility=%.4f entries=%d",
            window.dominant_emotion, window.volatility_score, window.entry_count,
        )

    return PatternAnalysisResponse(
        window=WindowStatsResponse.from_window(window),
        anomaly=flag,
    )
