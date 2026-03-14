"""
models/emotion.py
=================
Pydantic model for a single emotion journal entry.

EmotionRecord is the *input* data type — it records what the NLP engine
returned for one journal entry so that the pattern engine can aggregate
multiple entries into a time-windowed analysis.

Kept in ``models/`` (input/domain objects) and separate from ``schemas/``
(request/response wire shapes) following existing project conventions.

Kaizen improvements applied
----------------------------
- Poka-Yoke: ``emotions`` values are validated as [0.0, 1.0] at the
  boundary via a model_validator, making it impossible for invalid scores
  to propagate into the analytics engine.
- ``entry_id`` moved before ``emotions`` so the natural read order
  (who → when → which entry → what scores) matches the struct layout.
"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class EmotionRecord(BaseModel):
    """
    A single analysed journal entry with per-emotion confidence scores.

    Fields
    ------
    user_id   : Unique identifier of the user who authored the entry.
    timestamp : UTC datetime when the entry was created / analysed.
    entry_id  : Unique identifier for this specific journal entry.
    emotions  : Mapping of emotion label → confidence score (0.0 – 1.0).
                Example: {"sadness": 0.82, "joy": 0.05, "fear": 0.11}
    """

    user_id: str = Field(..., description="Unique user identifier")
    timestamp: datetime = Field(..., description="UTC datetime of the journal entry")
    entry_id: str = Field(..., description="Unique identifier for this journal entry")
    emotions: dict[str, float] = Field(
        ...,
        description="Emotion label → confidence score mapping (values 0.0–1.0)",
        examples=[{"sadness": 0.82, "joy": 0.05}],
    )

    # ── Kaizen / Poka-Yoke: validate score bounds at ingestion boundary ────────
    # Scores outside [0, 1] would silently corrupt avg_scores and volatility.
    # Catching this here — not inside the analytics engine — keeps the engine
    # pure and makes the error message actionable for callers.
    @model_validator(mode="after")
    def _validate_emotion_scores(self) -> "EmotionRecord":
        bad = {
            label: score
            for label, score in self.emotions.items()
            if not (0.0 <= score <= 1.0)
        }
        if bad:
            raise ValueError(
                f"All emotion scores must be between 0.0 and 1.0. "
                f"Invalid scores: {bad}"
            )
        return self
