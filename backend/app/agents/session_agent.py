"""
agents/session_agent.py
======================
Groq-backed ephemeral listener session responses.

The server does not store conversation state. The client sends recent history.
"""

import logging
from functools import lru_cache
from typing import Sequence

from groq import Groq

from app.core.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_OPENING = "I am here with you. Take your time and say anything you need."
_FALLBACK_REPLY = "I hear you. Keep going if you want to."
_FALLBACK_CLOSE = (
    "Thank you for letting that out. "
    "You gave your feelings space, and that matters. "
    "Take one gentle breath before you move on."
)

_OPENING_SYSTEM_PROMPT = """\
You are a warm listener inside a private 10-minute venting session.
Write one short opening line that helps the user feel safe to speak freely.
Rules:
1. 1-2 sentences.
2. No diagnosis, no clinical language, no medical advice.
3. Warm, calm, non-judgmental.
4. Output plain text only.
"""

_REPLY_SYSTEM_PROMPT = """\
You are a warm listening companion in a private 10-minute venting session.
The user is expressing emotional load. Reply like an attentive human listener.
Rules:
1. Keep response to 1-3 short sentences.
2. Validate and reflect; avoid lectures.
3. No diagnosis, no clinical claims, no medical advice.
4. Do not mention saving, storing, or memory.
5. Output plain text only.
"""

_CLOSE_SYSTEM_PROMPT = """\
The 10-minute private session has ended.
Write a warm closing in exactly 2-3 short sentences.
Rules:
1. No questions.
2. No diagnosis, no clinical language.
3. No action plan or long advice.
4. Output plain text only.
"""


@lru_cache(maxsize=1)
def _get_client() -> Groq:
    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY missing; session agent will use fallbacks.")
    return Groq(api_key=settings.groq_api_key)


def _format_history(history: Sequence[dict], user_message: str) -> str:
    clipped = list(history)[-8:]
    lines: list[str] = []
    for item in clipped:
        role = item.get("role", "user")
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        speaker = "User" if role == "user" else "Listener"
        lines.append(f"{speaker}: {content}")

    lines.append(f"User: {user_message.strip()}")
    return "\n".join(lines)


def _chat(system_prompt: str, user_prompt: str, *, max_tokens: int, temperature: float) -> str:
    client = _get_client()
    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (completion.choices[0].message.content or "").strip()


def run_session_opening() -> str:
    """Generate an opening line for the private session."""
    try:
        opening = _chat(
            _OPENING_SYSTEM_PROMPT,
            "Give one opening line for the listener session.",
            max_tokens=90,
            temperature=0.7,
        )
        return opening or _FALLBACK_OPENING
    except Exception:
        logger.warning("Session opening fallback used.")
        return _FALLBACK_OPENING


def run_session_reply(*, user_message: str, elapsed_seconds: int, history: Sequence[dict]) -> str:
    """Generate one listener reply for the current turn."""
    prompt = (
        f"Elapsed seconds: {elapsed_seconds}\n"
        f"Conversation so far:\n{_format_history(history, user_message)}\n\n"
        "Respond to the latest user message as a warm listener."
    )
    try:
        reply = _chat(
            _REPLY_SYSTEM_PROMPT,
            prompt,
            max_tokens=150,
            temperature=0.75,
        )
        return reply or _FALLBACK_REPLY
    except Exception:
        logger.warning("Session reply fallback used.")
        return _FALLBACK_REPLY


def run_session_close(*, session_text: str, history: Sequence[dict]) -> str:
    """Generate a short closing message when the session ends."""
    history_text = _format_history(history, "").strip()
    if history_text.endswith("User:"):
        history_text = history_text[:-5].strip()

    prompt = (
        "Session transcript snippet:\n"
        f"{history_text or session_text or 'User shared difficult emotions.'}\n\n"
        "Write the closing now."
    )

    try:
        closing = _chat(
            _CLOSE_SYSTEM_PROMPT,
            prompt,
            max_tokens=180,
            temperature=0.7,
        )
        return closing or _FALLBACK_CLOSE
    except Exception:
        logger.warning("Session close fallback used.")
        return _FALLBACK_CLOSE
