"""
Agents Router
=============
Provides agent endpoints backed by LangGraph agents.

Provider mapping:
    - Reflection Agent: HuggingFace Inference API
    - Pattern Agent: Groq
    - Coach Agent: Groq
    - Burst Agent: Groq (ephemeral — no data stored)

Endpoints:
  POST /agent/reflect        — Reflection Agent (2 empathetic follow-up questions)
  POST /agent/pattern        — Pattern Agent (3-5 sentence trend narrative + card headline)
  POST /agent/coach          — Coach Agent (1-2 micro-habit suggestions + 1-day challenge)
  POST /agent/burst/ack      — Burst Agent: mid-session acknowledgment (no auth, no storage)
  POST /agent/burst/close    — Burst Agent: session closing message (no auth, no storage)
    POST /agent/session/start  — Session Agent: start private listening session (no auth, no storage)
    POST /agent/session/message— Session Agent: reply in private session (no auth, no storage)
    POST /agent/session/close  — Session Agent: end private session (no auth, no storage)
"""

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from groq import APIConnectionError, APIStatusError
from huggingface_hub.errors import HfHubHTTPError

from app.agents.burst_agent import run_burst_ack, run_burst_close
from app.agents.coach_agent import run_coach
from app.agents.pattern_agent import run_pattern
from app.agents.reflection_agent import run_reflection
from app.agents.session_agent import (
    run_session_close,
    run_session_opening,
    run_session_reply,
)
from app.schemas.agent import (
    CoachRequest,
    CoachResponse,
    PatternRequest,
    PatternResponse,
    ReflectRequest,
    ReflectResponse,
    WindowStatsInput,
)
from app.schemas.burst import (
    BurstAckRequest,
    BurstAckResponse,
    BurstCloseRequest,
    BurstCloseResponse,
)
from app.schemas.session import (
    SessionCloseRequest,
    SessionCloseResponse,
    SessionMessageRequest,
    SessionMessageResponse,
    SessionStartRequest,
    SessionStartResponse,
)
from app.services.pattern_engine import WindowStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])

SESSION_DURATION_SECONDS = 600


def _build_session_id() -> str:
    """Encode a creation timestamp in the session ID to avoid server-side storage."""
    return f"ssn_{uuid.uuid4().hex}_{int(time.time())}"


def _parse_session_started_at(session_id: str) -> int:
    parts = session_id.split("_")
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    try:
        started_at = int(parts[-1])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id") from exc
    if started_at <= 0:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    return started_at


def _compute_elapsed_seconds(session_id: str, client_elapsed: int) -> int:
    started_at = _parse_session_started_at(session_id)
    server_elapsed = max(0, int(time.time()) - started_at)
    return min(SESSION_DURATION_SECONDS, max(server_elapsed, client_elapsed))


@router.post(
    "/reflect",
    response_model=ReflectResponse,
    summary="Generate reflection questions for a journal entry",
    description=(
        "Invokes the LangGraph Reflection Agent (powered by HuggingFace Inference API). "
        "Returns 2 gentle, open-ended questions to help the user explore their "
        "emotional state. Never diagnoses or gives medical advice."
    ),
)
async def reflect(body: ReflectRequest) -> ReflectResponse:
    """
    POST /agent/reflect

    Feed in a journal entry + detected emotions → get back 2 reflection questions.
    """
    logger.info(
        "Reflection requested | emotions=%s | text_len=%d",
        [e.label for e in body.emotions],
        len(body.journal_text),
    )

    emotions_dicts = [e.model_dump() for e in body.emotions]
    top_emotion = body.emotions[0].label if body.emotions else "neutral"

    try:
        result = run_reflection(
            journal_text=body.journal_text,
            emotions=emotions_dicts,
            history=body.history,
            mirror_phrase=body.mirror_phrase,
        )
    except HfHubHTTPError as exc:
        # Poka-Yoke: HF quota / auth errors surface as 429, not 500
        logger.warning("HuggingFace API error (status=%s): %s", exc.response.status_code if exc.response else "?", exc)
        status = exc.response.status_code if exc.response else 503
        if status == 401:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing HUGGINGFACE_API_TOKEN in .env.",
            ) from exc
        raise HTTPException(
            status_code=429 if status == 429 else 503,
            detail=(
                "HuggingFace API quota exceeded or model unavailable. "
                "Wait a moment and retry, or switch HF_MODEL in .env."
            ),
        ) from exc
    except Exception as exc:
        logger.error("Reflection agent error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Reflection agent failed. Check HUGGINGFACE_API_TOKEN in .env.",
        ) from exc

    return ReflectResponse(
        questions=result.questions,
        top_emotion=top_emotion,
        mirror_phrase_used=body.mirror_phrase,
    )


@router.post(
    "/pattern",
    response_model=PatternResponse,
    summary="Synthesise emotional trend narrative for a time window",
    description=(
        "Invokes the LangGraph Pattern Agent (powered by Groq). "
        "Returns 3-5 sentences describing the user's emotional trends plus a one-line "
        "card headline. Never diagnoses or gives medical advice."
    ),
)
async def pattern(body: PatternRequest) -> PatternResponse:
    """
    POST /agent/pattern

    Feed in a WindowStats snapshot + optional anomaly flag →
    get back a natural-language trend narrative and card headline.
    """
    logger.info(
        "Pattern requested | dominant=%s | entries=%d | anomaly=%s",
        body.window_stats.dominant_emotion,
        body.window_stats.entry_count,
        body.anomaly_flag,
    )

    # Re-hydrate the schema input into the typed WindowStats model that
    # run_pattern expects, so the agent layer stays decoupled from HTTP schemas.
    window_stats = WindowStats(**body.window_stats.model_dump())

    try:
        result = run_pattern(
            window_stats=window_stats,
            anomaly_flag=body.anomaly_flag,
            history_summary=body.history_summary,
        )
    except APIStatusError as exc:
        logger.warning(
            "Groq API status error (status=%s): %s",
            exc.status_code,
            exc,
        )
        status = exc.status_code or 503
        if status == 401:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing GROQ_API_KEY in .env.",
            ) from exc
        raise HTTPException(
            status_code=429 if status == 429 else 503,
            detail=(
                "Groq API quota exceeded or model unavailable. "
                "Wait a moment and retry, or switch GROQ_MODEL in .env."
            ),
        ) from exc
    except APIConnectionError as exc:
        logger.warning("Groq API connection error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Unable to reach Groq API. Check network connectivity and retry.",
        ) from exc
    except Exception as exc:
        logger.error("Pattern agent error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Pattern agent failed. Check GROQ_API_KEY and GROQ_MODEL in .env.",
        ) from exc

    return PatternResponse(
        insights=result.insights,
        highlight=result.highlight,
        dominant_emotion=body.window_stats.dominant_emotion,
    )


@router.post(
    "/coach",
    response_model=CoachResponse,
    summary="Generate micro-habit suggestions when an emotional anomaly is detected",
    description=(
        "Invokes the LangGraph Coach Agent (powered by Groq). "
        "Returns 1-2 optional micro-habit suggestions and a 1-day challenge grounded "
        "in the observed emotional pattern. Returns an empty response when no anomaly "
        "is present. Never diagnoses or gives medical advice."
    ),
)
async def coach(body: CoachRequest) -> CoachResponse:
    """
    POST /agent/coach

    Feed in a pattern narrative + anomaly flag → get back micro-habit suggestions.
    Returns empty suggestions + challenge="" when anomaly_flag is null (no-op).
    """
    logger.info(
        "Coach requested | anomaly=%s | insight_len=%d",
        body.anomaly_flag,
        len(body.pattern_insight),
    )

    try:
        result = run_coach(
            pattern_insight=body.pattern_insight,
            anomaly_flag=body.anomaly_flag,
            user_preferences=body.user_preferences,
        )
    except APIStatusError as exc:
        logger.warning(
            "Groq API status error (status=%s): %s",
            exc.status_code,
            exc,
        )
        status = exc.status_code or 503
        if status == 401:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing GROQ_API_KEY in .env.",
            ) from exc
        raise HTTPException(
            status_code=429 if status == 429 else 503,
            detail=(
                "Groq API quota exceeded or model unavailable. "
                "Wait a moment and retry, or switch GROQ_MODEL in .env."
            ),
        ) from exc
    except APIConnectionError as exc:
        logger.warning("Groq API connection error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Unable to reach Groq API. Check network connectivity and retry.",
        ) from exc
    except Exception as exc:
        logger.error("Coach agent error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Coach agent failed. Check GROQ_API_KEY and GROQ_MODEL in .env.",
        ) from exc

    return CoachResponse(
        suggestions=result.suggestions,
        challenge=result.challenge,
        triggered=body.anomaly_flag is not None,
    )


# ── Burst Session ─────────────────────────────────────────────────────────────
# Intentionally no auth — Burst is ephemeral and anonymous by design.
# No user_id. No DB writes. Session text passes through Groq API only.


@router.post(
    "/burst/ack",
    response_model=BurstAckResponse,
    summary="Get a mid-session Burst acknowledgment",
    description=(
        "Called every ~20 seconds during an active Burst session. "
        "Returns a single short, warm acknowledgment (\u226412 words) so the user "
        "feels witnessed. No data is stored. No authentication required."
    ),
)
async def burst_ack(body: BurstAckRequest) -> BurstAckResponse:
    """
    POST /agent/burst/ack

    Mid-session acknowledgment: stateless, ephemeral, no auth.
    """
    logger.info(
        "Burst ack requested | elapsed=%ds | text_len=%d",
        body.elapsed_seconds,
        len(body.partial_text),
    )

    try:
        ack = run_burst_ack(
            partial_text=body.partial_text,
            elapsed_seconds=body.elapsed_seconds,
        )
    except APIStatusError as exc:
        logger.warning("Burst ack: Groq API status error: %s", exc)
        # Return fallback gracefully — don't break the user's venting session
        ack = "I'm right here with you."
    except APIConnectionError as exc:
        logger.warning("Burst ack: Groq connection error: %s", exc)
        ack = "You're safe here."
    except Exception as exc:
        logger.error("Burst ack: unexpected error: %s", exc, exc_info=True)
        ack = "I hear you."

    return BurstAckResponse(acknowledgment=ack)


@router.post(
    "/burst/close",
    response_model=BurstCloseResponse,
    summary="Get a closing message at the end of a Burst session",
    description=(
        "Called once when a Burst session ends (timer expires or user taps done). "
        "Returns a warm 2\u20133 sentence closing affirmation. "
        "No data is stored. No authentication required."
    ),
)
async def burst_close(body: BurstCloseRequest) -> BurstCloseResponse:
    """
    POST /agent/burst/close

    Session closing message: stateless, ephemeral, no auth.
    """
    logger.info(
        "Burst close requested | session_text_len=%d",
        len(body.session_text),
    )

    try:
        closing = run_burst_close(session_text=body.session_text)
    except APIStatusError as exc:
        logger.warning("Burst close: Groq API status error: %s", exc)
        closing = (
            "You showed up for yourself tonight \u2014 that matters. "
            "Take a gentle breath when you're ready."
        )
    except APIConnectionError as exc:
        logger.warning("Burst close: Groq connection error: %s", exc)
        closing = (
            "Letting it out takes courage. "
            "Rest easy when you're ready."
        )
    except Exception as exc:
        logger.error("Burst close: unexpected error: %s", exc, exc_info=True)
        closing = "Thank you for being here with yourself tonight."

    return BurstCloseResponse(closing_message=closing)


@router.post(
    "/session/start",
    response_model=SessionStartResponse,
    summary="Start a private 10-minute listening session",
    description=(
        "Starts a private text session where the user can vent and receive warm replies. "
        "No authentication required. No data is stored server-side."
    ),
)
async def session_start(body: SessionStartRequest) -> SessionStartResponse:
    """
    POST /agent/session/start

    Returns an ephemeral session ID plus opening agent line.
    """
    logger.info("Session start requested")

    session_id = _build_session_id()
    opening = run_session_opening()

    return SessionStartResponse(
        session_id=session_id,
        agent_message=opening,
        remaining_seconds=SESSION_DURATION_SECONDS,
    )


@router.post(
    "/session/message",
    response_model=SessionMessageResponse,
    summary="Send one user message and get one listener reply",
    description=(
        "Returns one empathetic listener reply for the active private session turn. "
        "No authentication required. No data is stored server-side."
    ),
)
async def session_message(body: SessionMessageRequest) -> SessionMessageResponse:
    """
    POST /agent/session/message

    Stateless turn processing. Client sends recent history each turn.
    """
    elapsed_seconds = _compute_elapsed_seconds(body.session_id, body.elapsed_seconds)
    remaining_seconds = max(0, SESSION_DURATION_SECONDS - elapsed_seconds)

    logger.info(
        "Session message requested | elapsed=%ds | remaining=%ds",
        elapsed_seconds,
        remaining_seconds,
    )

    if remaining_seconds <= 0:
        return SessionMessageResponse(
            agent_reply=(
                "Our ten minutes are complete. "
                "When you are ready, tap done and I will close gently with you."
            ),
            remaining_seconds=0,
            session_ended=True,
        )

    history = [item.model_dump() for item in body.history]
    reply = run_session_reply(
        user_message=body.user_message,
        elapsed_seconds=elapsed_seconds,
        history=history,
    )

    return SessionMessageResponse(
        agent_reply=reply,
        remaining_seconds=remaining_seconds,
        session_ended=False,
    )


@router.post(
    "/session/close",
    response_model=SessionCloseResponse,
    summary="Close a private listening session",
    description=(
        "Returns a warm closing message and ends the private session. "
        "No authentication required. No data is stored server-side."
    ),
)
async def session_close(body: SessionCloseRequest) -> SessionCloseResponse:
    """
    POST /agent/session/close

    Generates a final closing line for the completed private session.
    """
    _parse_session_started_at(body.session_id)
    logger.info("Session close requested")

    history = [item.model_dump() for item in body.history]
    closing = run_session_close(
        session_text=body.session_text,
        history=history,
    )

    return SessionCloseResponse(closing_message=closing)
