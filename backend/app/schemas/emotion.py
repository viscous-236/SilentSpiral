from typing import Literal

from pydantic import BaseModel, Field

# ── Poka-Yoke: crisis keywords are checked at the boundary,
#    not buried in business logic. Any text containing these phrases
#    triggers crisis_flag=True in the response — making it impossible
#    for consumers to accidentally treat a crisis entry as normal.
CRISIS_KEYWORDS: frozenset[str] = frozenset([
    "suicide", "suicidal", "kill myself", "end my life", "want to die",
    "don't want to live", "don't want to be alive", "self harm", "self-harm",
    "cut myself", "cutting myself", "overdose", "no reason to live",
])

# Emotion labels that map to each category — derived once, used everywhere
_POSITIVE_EMOTIONS = frozenset([
    "joy", "love", "admiration", "amusement", "approval", "caring",
    "desire", "excitement", "gratitude", "optimism", "pride", "relief",
])
_NEGATIVE_EMOTIONS = frozenset([
    "sadness", "anger", "disgust", "fear", "grief", "nervousness",
    "remorse", "disappointment", "annoyance", "embarrassment",
])


def classify_emotion_category(label: str) -> Literal["positive", "negative", "neutral"]:
    """Derive a 3-way category from a GoEmotions label."""
    if label in _POSITIVE_EMOTIONS:
        return "positive"
    if label in _NEGATIVE_EMOTIONS:
        return "negative"
    return "neutral"


def detect_crisis(text: str) -> bool:
    """
    Poka-Yoke guard: returns True if any crisis keyword is found in text.
    Case-insensitive, whole-word aware via simple substring check.
    Fast enough for real-time use (no regex overhead needed at this scale).
    """
    lowered = text.lower()
    return any(kw in lowered for kw in CRISIS_KEYWORDS)


class AnalyzeRequest(BaseModel):
    """Request body for POST /analyze"""

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Journal entry text to analyze for emotions",
        examples=["I feel a strange heaviness today. Work was fine but I can't shake it."],
    )


class EmotionScore(BaseModel):
    """Single emotion label with its confidence score"""

    label: str = Field(..., description="Emotion label (e.g. 'sadness', 'anxiety')")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0–1.0")


class AnalyzeResponse(BaseModel):
    """Response from POST /analyze"""

    emotions: list[EmotionScore] = Field(
        ..., description="Top emotions above threshold, sorted by score descending"
    )
    top_emotion: str = Field(..., description="Highest-scoring emotion label")
    intensity: float = Field(
        ..., ge=0.0, le=1.0, description="Score of the top emotion (emotional intensity)"
    )
    emotion_category: Literal["positive", "negative", "neutral"] = Field(
        ..., description="Derived category of the top emotion"
    )
    word_count: int = Field(..., description="Word count of the input text")
    crisis_flag: bool = Field(
        ...,
        description=(
            "True if the text contains crisis-level language (e.g. suicidal ideation). "
            "Frontend MUST show a gentle support message when this is True."
        ),
    )
