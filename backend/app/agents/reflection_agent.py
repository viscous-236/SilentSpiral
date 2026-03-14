"""
agents/reflection_agent.py
===========================
A single-node LangGraph graph that accepts journal text + detected
emotions and returns 2 gentle, open-ended reflection questions.

Design choices (LangGraph best practices):
  - Single StateGraph node (no cycles needed — one-shot reflection)
  - TypedDict state with explicit fields (no opaque message list)
  - Groq InferenceClient for chat completions (free tier, OpenAI-compatible)
  - lru_cache on the compiled graph — warms once, reuses across requests

Model: llama-3.3-70b-versatile (configurable via GROQ_MODEL in .env)
  - Free on Groq's free tier — no credit card, no usage limits for dev
  - OpenAI-compatible API: same .chat.completions.create() interface
  - Get a free API key at https://console.groq.com

Kaizen change log
-----------------
- 2026-03-07: Initial implementation using HuggingFace InferenceClient
  (deepseek-ai/DeepSeek-R1 via Together provider).
- 2026-03-13: Migrated to Groq (free tier) after HuggingFace monthly
  credits were depleted (HTTP 402). Groq uses the same OpenAI-style
  interface — minimal code change (swap client, drop HF-specific
  reasoning-chain extraction). Kaizen: smallest viable fix for root cause.

Agent persona (System Prompt Engineering):
  - Gentle, non-clinical companion
  - Never diagnoses or prescribes
  - Always asks open questions (not yes/no)
  - Short questions (<=20 words each) — accessible for all emotional states
"""

import json
import logging
import re
from functools import lru_cache
from typing import TypedDict

from groq import Groq
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

# How many previous reflections to include in the prompt context
_MAX_HISTORY_IN_PROMPT = 3

# Fallback questions used when structured output is malformed or API unavailable
_FALLBACK_QUESTIONS = [
    "What feeling is sitting with you the most right now?",
    "When did you first notice this sensation today?",
]


# ── Structured output ────────────────────────────────────────────────────────

class ReflectionOutput(BaseModel):
    """Structured output from the LLM — two reflection questions."""

    questions: list[str] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Exactly two open-ended reflection questions, each <=20 words.",
    )


# ── Agent State ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    journal_text: str                 # Raw journal entry
    emotions: list[dict]              # Top emotions from /analyze
    history: list[str]                # Previous session reflections (<=5)
    mirror_phrase: str | None         # Past entry surfaced by find_mirror_phrase()
    output: ReflectionOutput | None   # Populated by reflection_node


# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a gentle, non-clinical self-awareness companion inside an app called
The Silent Spiral. Your only job is to help the user explore their inner world
through curiosity, never judgment.

Rules you MUST follow:
1. Ask exactly 2 open-ended questions (cannot be answered with yes/no).
2. Each question must be 20 words or fewer.
3. Ground each question in the emotions and words the user shared.
4. Never use clinical terms: no "depression", "anxiety disorder", "trauma", etc.
5. Never diagnose, advise therapy, or recommend actions.
6. Use calm, warm, everyday language.
7. Vary question style — one can be about the past, one about right now.

Return ONLY valid JSON matching this schema:
{"questions": ["<question_1>", "<question_2>"]}
"""


def _build_user_prompt(
    journal_text: str,
    emotions: list[dict],
    history: list[str],
    mirror_phrase: str | None = None,
) -> str:
    emotion_summary = (
        ", ".join(f'{e["label"]} ({e["score"]:.0%})' for e in emotions[:3])
        if emotions
        else "not specified"
    )

    history_block = ""
    if history:
        recent = history[-_MAX_HISTORY_IN_PROMPT:]
        history_block = (
            "\n\nPrevious reflections shared with this user:\n"
            + "\n".join(f"- {h}" for h in recent)
        )

    # Mirror Prompt injection — reflect a semantically similar past phrase back
    # Only surfaces entries >=7 days old with similarity >=0.85 (enforced upstream
    # by find_mirror_phrase; the agent layer trusts the caller's guard).
    mirror_block = ""
    if mirror_phrase:
        mirror_block = (
            f"\n\nMirror Prompt: The user previously wrote the following. "
            f"Make one of your questions gently ask whether it still feels true today:\n"
            f'"{mirror_phrase}"'
        )

    return (
        f"The user is feeling: {emotion_summary}\n\n"
        f'Their journal entry:\n"""\n{journal_text}\n"""'
        f"{history_block}"
        f"{mirror_block}\n\n"
        "Generate your 2 reflection questions now."
    )


# ── JSON parsing helper ───────────────────────────────────────────────────────

def _parse_questions(raw: str) -> ReflectionOutput:
    """
    Extract JSON with 'questions' key from raw model output.
    Handles markdown code fences and prose wrapping.
    """
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()

    # Try to find a JSON object with a 'questions' key
    match = re.search(r'\{[^{}]*"questions"[^{}]*\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    data = json.loads(cleaned)
    return ReflectionOutput(**data)


# ── Groq client (cached) ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_client() -> Groq:
    """
    Build and cache the Groq client.

    Uses GROQ_API_KEY from .env. Free tier at https://console.groq.com.
    The Groq client is OpenAI-API-compatible — same interface as before.
    """
    if not settings.groq_api_key:
        logger.error(
            "GROQ_API_KEY is not configured. "
            "Set it in .env to enable reflection questions."
        )
    return Groq(api_key=settings.groq_api_key)


# ── Graph node ───────────────────────────────────────────────────────────────

def reflection_node(state: AgentState) -> dict:
    """
    Single LangGraph node. Calls Groq API via the Groq client.
    Returns a partial state update (only 'output' field).
    """
    client = _get_client()

    user_prompt = _build_user_prompt(
        state["journal_text"],
        state["emotions"],
        state["history"],
        state["mirror_phrase"],
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    logger.info("Calling Groq reflection node (model: %s)…", settings.groq_model)

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            max_tokens=512,    # Reflection questions are short; 512 is plenty
            temperature=0.7,
        )
        raw_content: str = completion.choices[0].message.content or ""
        finish_reason = completion.choices[0].finish_reason

        if finish_reason == "length":
            logger.warning(
                "LLM response truncated (finish_reason=length). "
                "Consider raising max_tokens."
            )
        logger.debug("Raw LLM response (finish=%s): %s", finish_reason, raw_content)

        result = _parse_questions(raw_content)
        logger.info("Reflection questions generated: %s", result.questions)
        return {"output": result}

    except (json.JSONDecodeError, ValueError, TypeError) as parse_exc:
        logger.warning(
            "Failed to parse LLM output as ReflectionOutput (%s). Using fallback.",
            parse_exc,
        )
        return {"output": ReflectionOutput(questions=_FALLBACK_QUESTIONS)}
    except Exception as api_exc:
        logger.error("Groq API call failed: %s", api_exc, exc_info=True)
        return {"output": ReflectionOutput(questions=_FALLBACK_QUESTIONS)}


# ── Graph compilation ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_reflection_graph():
    """
    Builds and compiles the LangGraph graph once.

    Graph topology:  START -> reflect -> END
    """
    graph = StateGraph(AgentState)
    graph.add_node("reflect", reflection_node)
    graph.set_entry_point("reflect")
    graph.add_edge("reflect", END)
    return graph.compile()


# ── Public API ───────────────────────────────────────────────────────────────

def run_reflection(
    journal_text: str,
    emotions: list[dict],
    history: list[str] | None = None,
    mirror_phrase: str | None = None,
) -> ReflectionOutput:
    """
    Invoke the reflection graph and return structured output.

    Args:
        journal_text:  Raw journal entry from the user.
        emotions:      Dicts with 'label' and 'score' keys (from /analyze).
        history:       Past reflection strings for conversational continuity.
        mirror_phrase: A past journal phrase surfaced by find_mirror_phrase().
                       When provided, one of the two questions will gently ask
                       whether that past feeling still holds true today.
                       Callers are responsible for the similarity + age guards
                       (enforced in vector_store.find_mirror_phrase).

    Returns:
        ReflectionOutput with exactly 2 reflection questions.
    """
    graph = get_reflection_graph()

    initial_state: AgentState = {
        "journal_text": journal_text,
        "emotions": emotions,
        "history": history or [],
        "mirror_phrase": mirror_phrase,
        "output": None,
    }

    final_state = graph.invoke(initial_state)
    output: ReflectionOutput = final_state["output"]

    if not output or len(output.questions) != 2:
        logger.warning(
            "Agent returned unexpected output (got %s questions). Using fallback.",
            len(output.questions) if output else 0,
        )
        output = ReflectionOutput(questions=_FALLBACK_QUESTIONS)

    return output
