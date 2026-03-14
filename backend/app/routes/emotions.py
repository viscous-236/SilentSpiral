"""
Emotions Router
===============
Provides the POST /analyze endpoint for NLP emotion detection.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.emotion import (
    AnalyzeRequest,
    AnalyzeResponse,
    EmotionScore,
    classify_emotion_category,
    detect_crisis,
)
from app.services.nlp_engine import analyze_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["Emotions"])


@router.post(
    "",
    response_model=AnalyzeResponse,
    summary="Analyze journal text for emotions",
    description=(
        "Runs the HuggingFace GoEmotions classifier on the provided text. "
        "Returns top emotions, emotion category, and a crisis_flag for safety."
    ),
)
async def analyze_emotions(body: AnalyzeRequest) -> AnalyzeResponse:
    """
    POST /analyze

    Accepts a journal entry and returns multi-label emotion scores.
    crisis_flag=True means the text contains crisis-level language —
    the frontend MUST show a gentle support prompt in this case.
    """
    logger.info("Analyzing text | chars=%d words=%d", len(body.text), len(body.text.split()))

    # ── Poka-Yoke: crisis check happens at the boundary, before NLP ──────────
    is_crisis = detect_crisis(body.text)
    if is_crisis:
        logger.warning("Crisis language detected in journal entry")

    try:
        result = analyze_text(body.text)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="NLP model unavailable — install transformers and torch to enable /analyze.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AnalyzeResponse(
        emotions=[EmotionScore(**e) for e in result["emotions"]],
        top_emotion=result["top_emotion"],
        intensity=result["intensity"],
        emotion_category=classify_emotion_category(result["top_emotion"]),
        word_count=result["word_count"],
        crisis_flag=is_crisis,
    )

