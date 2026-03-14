"""
agents/burst_agent.py
=====================
Two single-node LangGraph graphs for the ephemeral Burst Session feature.

  - Ack graph  (START → ack_node → END):
      Called mid-session every ~20 s. Returns a ≤12-word empathetic
      acknowledgment. Keeps the user feeling witnessed without interrupting.

  - Close graph (START → close_node → END):
      Called once at session end. Returns a 2–3 sentence warm closure with
      no questions and no advice — just affirming presence.

Design (mirrors reflection_agent.py patterns):
  - Single-node StateGraphs — no cycles, one-shot calls
  - TypedDict state with explicit fields for debuggability
  - Groq client cached via lru_cache (same as reflection_agent)
  - lru_cache on compiled graph — warms once, reused across requests
  - Graceful fallback strings when Groq is unavailable

Privacy-by-design:
  - No user_id in state
  - No writes to any store (DB, vector store, analytics)
  - Session text passes through Groq API only — treated as ephemeral

Agent persona (Prompt Engineering):
  - Warm, present, non-judgmental witness
  - Never diagnoses, advises therapy, or recommends actions
  - Acknowledges without redirecting — the user is in control
  - Language: simple, calm, human — like a trusted friend in the room
"""

import logging
from functools import lru_cache
from typing import TypedDict

from groq import Groq
from langgraph.graph import END, StateGraph

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Fallback strings (used when Groq API is unreachable) ─────────────────────

_FALLBACK_ACK = "I'm right here with you."
_FALLBACK_CLOSE = (
    "You showed up for yourself tonight — that matters. "
    "Whatever you're carrying, it heard you. "
    "Take a gentle breath when you're ready."
)


# ── System Prompts ────────────────────────────────────────────────────────────

_ACK_SYSTEM_PROMPT = """\
You are a warm, silent companion inside a safe venting space called Burst.
The user is in the middle of freely expressing their feelings — do not interrupt
their flow. Your only job is to send one brief acknowledgment that makes them
feel witnessed, not judged.

Rules you MUST follow:
1. Return EXACTLY one sentence of 12 words or fewer.
2. No questions — do not ask anything.
3. No advice, suggestions, or redirections.
4. No clinical language ("trauma", "anxiety disorder", "depression", etc.).
5. Warm and present — like a caring friend nodding in the room.
6. Vary your phrases across calls — do not repeat "I hear you" every time.
7. Return ONLY the plain text acknowledgment. No quotes, no JSON, no formatting.

Good examples:
- I hear you. Keep going.
- You're safe here.
- That sounds really heavy.
- I'm right with you.
- Thank you for trusting this space.
- That makes complete sense.
"""

_CLOSE_SYSTEM_PROMPT = """\
You are a warm, caring companion inside a safe venting space called Burst.
The user has just finished a 5-minute session of freely expressing their feelings.
Write a closing message that makes them feel seen, grounded, and not alone.

Rules you MUST follow:
1. Write exactly 2–3 sentences.
2. No questions — do not ask anything.
3. No advice, no coping strategies, no action items.
4. No clinical language ("trauma", "anxiety", "mental health", etc.).
5. Warm, human, and affirming — acknowledge what they did (showed up, expressed themselves).
6. End on a gentle, grounding note (a breath, a moment of rest, or simply presence).
7. Return ONLY the plain text closing. No quotes, no JSON, no formatting.

Good examples:
"You showed up for yourself tonight — that's not small. Whatever you're carrying got some air.
Take a breath. You're okay."

"Letting it out takes courage, even here in private. This moment of honesty with yourself matters.
Rest easy when you're ready."
"""


# ── Groq client (shared, cached) ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_client() -> Groq:
    """
    Build and cache the Groq client (reuses the same pattern as reflection_agent).
    Uses GROQ_API_KEY from .env. Free tier at https://console.groq.com.
    """
    if not settings.groq_api_key:
        logger.error(
            "GROQ_API_KEY is not configured. "
            "Set it in .env to enable Burst session AI responses."
        )
    return Groq(api_key=settings.groq_api_key)


# ─────────────────────────────────────────────────────────────────────────────
# ACK GRAPH
# ─────────────────────────────────────────────────────────────────────────────

class AckState(TypedDict):
    partial_text: str       # Whatever the user has written so far
    elapsed_seconds: int    # How far into the 5-minute session they are
    acknowledgment: str     # Populated by ack_node


def _ack_user_prompt(partial_text: str, elapsed_seconds: int) -> str:
    elapsed_min = elapsed_seconds // 60
    elapsed_sec = elapsed_seconds % 60
    return (
        f"The user has been writing for {elapsed_min}m {elapsed_sec}s.\n\n"
        f"What they've written so far:\n\"\"\"\n{partial_text}\n\"\"\"\n\n"
        "Send one brief, warm acknowledgment now."
    )


def ack_node(state: AckState) -> dict:
    """
    LangGraph node: calls Groq and returns a short acknowledgment line.
    Falls back to _FALLBACK_ACK on any API or parse error.
    """
    client = _get_client()
    user_prompt = _ack_user_prompt(state["partial_text"], state["elapsed_seconds"])

    logger.info(
        "Burst ack requested | elapsed=%ds | text_len=%d",
        state["elapsed_seconds"],
        len(state["partial_text"]),
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _ACK_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=64,      # Ack is ≤12 words — 64 tokens is very generous
            temperature=0.85,   # Slightly higher than reflection for variety
        )
        raw: str = (completion.choices[0].message.content or "").strip()

        if not raw:
            logger.warning("Burst ack: empty response from Groq. Using fallback.")
            return {"acknowledgment": _FALLBACK_ACK}

        # Trim to first sentence if the model over-generates
        first_sentence = raw.split(".")[0].strip()
        ack = first_sentence if first_sentence else raw
        logger.info("Burst ack generated: %r", ack)
        return {"acknowledgment": ack}

    except Exception as exc:
        logger.error("Burst ack: Groq API call failed: %s", exc, exc_info=True)
        return {"acknowledgment": _FALLBACK_ACK}


@lru_cache(maxsize=1)
def _get_ack_graph():
    """Compile the one-shot ack graph (START → ack → END)."""
    g = StateGraph(AckState)
    g.add_node("ack", ack_node)
    g.set_entry_point("ack")
    g.add_edge("ack", END)
    return g.compile()


def run_burst_ack(partial_text: str, elapsed_seconds: int) -> str:
    """
    Invoke the Burst Ack graph.

    Args:
        partial_text:     Whatever the user has typed in this session so far.
        elapsed_seconds:  Seconds elapsed since session start (0–300).

    Returns:
        A short, warm acknowledgment string (≤12 words).
        Returns a hardcoded fallback if Groq is unreachable.
    """
    graph = _get_ack_graph()
    result = graph.invoke(
        {
            "partial_text": partial_text,
            "elapsed_seconds": elapsed_seconds,
            "acknowledgment": "",
        }
    )
    return result.get("acknowledgment") or _FALLBACK_ACK


# ─────────────────────────────────────────────────────────────────────────────
# CLOSE GRAPH
# ─────────────────────────────────────────────────────────────────────────────

class CloseState(TypedDict):
    session_text: str       # Complete text from the full session
    closing_message: str    # Populated by close_node


def _close_user_prompt(session_text: str) -> str:
    return (
        f"The user just finished their Burst session.\n\n"
        f"Here is everything they wrote:\n\"\"\"\n{session_text}\n\"\"\"\n\n"
        "Write a warm, affirming 2–3 sentence closing now."
    )


def close_node(state: CloseState) -> dict:
    """
    LangGraph node: calls Groq and returns a warm closing message.
    Falls back to _FALLBACK_CLOSE on any API or parse error.
    """
    client = _get_client()
    user_prompt = _close_user_prompt(state["session_text"])

    logger.info(
        "Burst close requested | session_text_len=%d",
        len(state["session_text"]),
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _CLOSE_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=200,     # 2–3 sentences fit easily in 200 tokens
            temperature=0.75,
        )
        raw: str = (completion.choices[0].message.content or "").strip()

        if not raw:
            logger.warning("Burst close: empty response from Groq. Using fallback.")
            return {"closing_message": _FALLBACK_CLOSE}

        logger.info("Burst close generated: %r", raw[:80])
        return {"closing_message": raw}

    except Exception as exc:
        logger.error("Burst close: Groq API call failed: %s", exc, exc_info=True)
        return {"closing_message": _FALLBACK_CLOSE}


@lru_cache(maxsize=1)
def _get_close_graph():
    """Compile the one-shot close graph (START → close → END)."""
    g = StateGraph(CloseState)
    g.add_node("close", close_node)
    g.set_entry_point("close")
    g.add_edge("close", END)
    return g.compile()


def run_burst_close(session_text: str) -> str:
    """
    Invoke the Burst Close graph.

    Args:
        session_text: The complete text the user wrote during the session.

    Returns:
        A warm 2–3 sentence closing affirmation string.
        Returns a hardcoded fallback if Groq is unreachable.
    """
    graph = _get_close_graph()
    result = graph.invoke(
        {
            "session_text": session_text,
            "closing_message": "",
        }
    )
    return result.get("closing_message") or _FALLBACK_CLOSE
