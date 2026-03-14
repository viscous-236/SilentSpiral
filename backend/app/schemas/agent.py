"""
Agent Schemas
=============
Pydantic models for the /agent/* endpoints.

Schemas defined here:
  - EmotionInput       — shared input type for detected emotions
  - ReflectRequest     — POST /agent/reflect request
  - ReflectResponse    — POST /agent/reflect response
  - PatternRequest     — POST /agent/pattern request
  - PatternResponse    — POST /agent/pattern response
  - CoachRequest       — POST /agent/coach request
  - CoachResponse      — POST /agent/coach response
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EmotionInput(BaseModel):
    """A single detected emotion to pass into the agent."""

    label: str = Field(..., description="Emotion label, e.g. 'sadness'")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score")

    # Poka-Yoke: an empty label would silently corrupt the agent's prompt context.
    # Reject at the boundary with a clear validation error.
    @field_validator("label")
    @classmethod
    def _label_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("EmotionInput.label must be a non-empty string")
        return v.strip()  # normalise whitespace while we're here


class ReflectRequest(BaseModel):
    """
    Request body for POST /agent/reflect.

    Accepts the raw journal text plus the top detected emotions
    (output from POST /analyze) so the agent can personalise
    its reflective questions.

    Mirror Prompt: if the client has already called vector_store.find_mirror_phrase()
    (or the equivalent backend helper), it can pass the resulting phrase here.
    The agent will then weave one question around whether that past feeling
    still holds true today.
    """

    journal_text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The journal entry written by the user",
        examples=["I feel a strange heaviness today. Work was fine but I can't shake it."],
    )
    emotions: list[EmotionInput] = Field(
        default_factory=list,
        description="Detected emotions from /analyze (optional, enriches agent context)",
    )
    history: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Up to 5 previous reflections for conversational continuity",
    )
    mirror_phrase: Optional[str] = Field(
        default=None,
        max_length=1000,
        description=(
            "A past journal phrase surfaced by the Mirror Prompt logic "
            "(similarity \u22650.85, age \u22657 days). When present, one reflection "
            "question will gently ask whether it still feels true today."
        ),
    )


class ReflectResponse(BaseModel):
    """
    Response from POST /agent/reflect.

    Always returns exactly 2 open questions.
    """

    questions: list[str] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Two gentle, open-ended reflection questions for the user",
    )
    top_emotion: str = Field(
        ...,
        description="The dominant emotion the agent focused on",
    )
    mirror_phrase_used: Optional[str] = Field(
        default=None,
        description=(
            "The past journal phrase that was mirrored back, or null if no "
            "mirror phrase was provided. Lets the frontend highlight the source."
        ),
    )


# ── Pattern Agent ─────────────────────────────────────────────────────────────

# Inline literal mirrors AnomalyFlag from pattern_engine to avoid a cross-layer
# import inside the schema layer; both must be kept in sync.
AnomalyFlagInput = Literal["HIGH_VOLATILITY", "DOWNWARD_SPIRAL", "LOW_ENGAGEMENT"]


class WindowStatsInput(BaseModel):
    """
    Serialised form of pattern_engine.WindowStats passed into POST /agent/pattern.

    Mirrors WindowStats exactly so callers can forward .model_dump() output
    directly without any transformation.
    """

    avg_scores: dict[str, float] = Field(
        ...,
        description="Mean confidence score per emotion label (rounded to 4 dp)",
    )
    dominant_emotion: str = Field(
        ...,
        description="Emotion label with the highest average score",
    )
    volatility_score: float = Field(
        ...,
        ge=0.0,
        description="Population std-dev of top-emotion score per entry",
    )
    entry_count: int = Field(
        ...,
        ge=1,
        description="Number of records in this window",
    )


class PatternRequest(BaseModel):
    """
    Request body for POST /agent/pattern.

    Accepts a serialised WindowStats object (from pattern_engine.compute_window),
    the detected anomaly (if any), and an optional short summary of previous
    pattern narratives for continuity.
    """

    window_stats: WindowStatsInput = Field(
        ...,
        description="Aggregated emotional statistics for the analysis window",
    )
    anomaly_flag: Optional[AnomalyFlagInput] = Field(
        default=None,
        description="Anomaly detected in the window, or null if none",
    )
    history_summary: str = Field(
        default="",
        max_length=1000,
        description="Short prose summary of previous pattern narratives (optional)",
    )


class PatternResponse(BaseModel):
    """
    Response from POST /agent/pattern.

    Returns 3-5 insight sentences and a single card headline.
    """

    insights: list[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3 to 5 sentences describing the user's emotional trend",
    )
    highlight: str = Field(
        ...,
        description="Single headline sentence (≤15 words) for the Pattern Card UI",
    )
    dominant_emotion: str = Field(
        ...,
        description="The dominant emotion observed in this window",
    )


# ── Coach Agent ───────────────────────────────────────────────────────────────


class CoachRequest(BaseModel):
    """
    Request body for POST /agent/coach.

    Accepts the Pattern Agent narrative, the anomaly flag that triggered
    the coach, and optional user preference hints.

    The endpoint returns an empty CoachResponse when anomaly_flag is null —
    the Coach Agent only fires on real signal weeks.
    """

    pattern_insight: str = Field(
        ...,
        min_length=1,
        max_length=3000,
        description="Natural-language trend narrative from the Pattern Agent",
    )
    anomaly_flag: Optional[AnomalyFlagInput] = Field(
        default=None,
        description="Anomaly that triggered this coach request, or null for no-op",
    )
    user_preferences: dict = Field(
        default_factory=dict,
        description="Optional user profile hints (e.g. preferred habit pace, interests)",
    )


class CoachResponse(BaseModel):
    """
    Response from POST /agent/coach.

    Returns 0–2 micro-habit suggestions and a 1-day challenge.
    Both fields are empty strings / empty lists when anomaly_flag was null.
    """

    suggestions: list[str] = Field(
        ...,
        description="0–2 gentle micro-habit suggestions framed as 'you might try…'",
    )
    challenge: str = Field(
        ...,
        description="Single 1-day micro-challenge (≤20 words) for tomorrow, or empty string",
    )
    triggered: bool = Field(
        ...,
        description="True when the LLM was actually called (anomaly present); False for no-op",
    )
