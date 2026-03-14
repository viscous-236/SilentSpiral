"""
agents/coach_agent.py
======================
A single-node LangGraph graph that accepts a pattern narrative and an
AnomalyFlag, then suggests 1–2 gentle micro-habits and one 1-day
micro-challenge for the user to try tomorrow.

Design choices (mirrors reflection_agent.py / pattern_agent.py conventions):
  - Single StateGraph node (one-shot output, no cycles needed)
  - TypedDict state with explicit fields
  - Direct HuggingFace InferenceClient for chat completions (same model)
  - lru_cache on the compiled graph — warms once, reuses across requests
  - Manual JSON parse + regex fallback

Short-circuit guard (Poka-Yoke):
  - If `anomaly_flag` is None, the LLM is never called.
  - `run_coach()` returns an empty CoachOutput immediately.
  - This prevents the Coach Agent from triggering on neutral or positive
    weeks — suggestions should only appear when there is a real signal.

Output contract:
  - `suggestions` : 1–2 items, each framed as "you might try…"
  - `challenge`   : Single actionable 1-day task (≤20 words)

Agent persona (System Prompt Engineering):
  - Warm, encouraging, never prescriptive
  - Frames every suggestion as optional ("you might try…", "one thing
    that sometimes helps…")
  - Never uses clinical language or tells the user what they must do
  - Ties suggestions directly to the observed emotional pattern

Kaizen improvements applied
----------------------------
- Follows the exact same lru_cache / InferenceClient / JSON-fallback
  pattern as reflection_agent.py and pattern_agent.py.
- AnomalyFlag rendered as human-readable text in the prompt.
- Empty short-circuit means no wasted LLM tokens on healthy weeks.
- Fallback suggestions are provided per anomaly type so the endpoint
  never silently returns an empty body on parse failure.
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
from app.services.pattern_engine import AnomalyFlag

logger = logging.getLogger(__name__)

# ── Fallback content per anomaly type ────────────────────────────────────────

_FALLBACK_BY_ANOMALY: dict[str, dict] = {
    "DOWNWARD_SPIRAL": {
        "suggestions": [
            "You might try writing just one sentence about something small that felt okay today.",
            "You might try stepping outside for five minutes without your phone.",
        ],
        "challenge": "Tomorrow: notice one moment that felt slightly lighter and write it down.",
    },
    "HIGH_VOLATILITY": {
        "suggestions": [
            "You might try a short breathing pause before you start writing your next entry.",
            "You might try rating your energy on a scale of 1–5 at the same time each day.",
        ],
        "challenge": "Tomorrow: write one sentence about how your body feels when you first wake up.",
    },
    "LOW_ENGAGEMENT": {
        "suggestions": [
            "You might try a 2-minute silent check-in — just notice what's present without writing.",
            "You might try setting a single gentle reminder to pause and breathe mid-afternoon.",
        ],
        "challenge": "Tomorrow: open the app and write just one word that describes your day.",
    },
}

_EMPTY_OUTPUT_SUGGESTIONS: list[str] = []
_EMPTY_OUTPUT_CHALLENGE: str = ""

# Human-readable descriptions for each anomaly type (matches pattern_agent.py)
_ANOMALY_DESCRIPTIONS: dict[str, str] = {
    "HIGH_VOLATILITY": "significant emotional volatility — mood swings more than usual",
    "DOWNWARD_SPIRAL": "a sustained downward trend — negative emotions dominant for several days",
    "LOW_ENGAGEMENT":  "low engagement — very few journal entries in this period",
}


# ── Structured output ─────────────────────────────────────────────────────────

class CoachOutput(BaseModel):
    """Structured output from the Coach Agent LLM call."""

    suggestions: list[str] = Field(
        ...,
        min_length=0,
        max_length=2,
        description="0–2 gentle micro-habit suggestions, each framed as 'you might try…'",
    )
    challenge: str = Field(
        ...,
        description="Single 1-day micro-challenge (≤20 words), actionable for tomorrow.",
    )


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    pattern_insight:   str               # Narrative from the Pattern Agent
    anomaly_flag:      AnomalyFlag       # Must be non-None (enforced in run_coach)
    user_preferences:  dict              # Optional user profile hints (habits, pace, etc.)
    output:            CoachOutput | None


# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a warm, supportive micro-habit coach inside an app called The Silent
Spiral. Your only job is to suggest one or two small, optional things the user
might try — grounded in the emotional pattern they have been experiencing.

Rules you MUST follow:
1. Write exactly 1 or 2 items for `suggestions`. Each must:
   - Start with "You might try" or "One thing that sometimes helps is"
   - Be a concrete, tiny action (not a mindset shift or vague advice)
   - Be completable in under 10 minutes
   - Be directly tied to the emotional pattern described
2. Write exactly 1 sentence for `challenge` — a specific action for tomorrow,
   20 words or fewer (e.g. "Tomorrow: write one sentence before you check
   your phone.").
3. Frame everything as optional and gentle. Never say "you should", "you must",
   "you need to".
4. Never use clinical terms: no "depression", "anxiety disorder", "trauma".
5. Never suggest therapy, medication, or professional help.
6. Keep the tone warm and curious — like a thoughtful friend, not a coach.

Return ONLY valid JSON matching this schema — no prose, no markdown fences:
{
  "suggestions": ["<suggestion_1>", "<suggestion_2>"],
  "challenge": "<tomorrow_challenge>"
}
"""


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_user_prompt(
    pattern_insight: str,
    anomaly_flag: AnomalyFlag,
    user_preferences: dict,
) -> str:
    anomaly_str = _ANOMALY_DESCRIPTIONS.get(anomaly_flag, anomaly_flag)

    prefs_block = ""
    if user_preferences:
        prefs_lines = "\n".join(f"  - {k}: {v}" for k, v in user_preferences.items())
        prefs_block = f"\n\nUser preferences / context:\n{prefs_lines}"

    return (
        f"Observed emotional pattern:\n"
        f"  - Anomaly type : {anomaly_str}\n\n"
        f"Pattern Agent narrative:\n\"\"\"\n{pattern_insight}\n\"\"\""
        f"{prefs_block}\n\n"
        "Generate your micro-habit suggestions and 1-day challenge now."
    )


# ── Content extraction helper (handles thinking/reasoning models) ─────────────

def _extract_content(message) -> str:
    """
    Extract the final answer text from a chat completion message.

    DeepSeek-R1 reasoning models sometimes return an empty `content` field,
    placing the answer inside a `reasoning` attribute. Try `content` first,
    fall back to scanning `reasoning` for a JSON block.
    """
    content = getattr(message, "content", "") or ""
    if content.strip():
        return content

    reasoning = getattr(message, "reasoning", "") or ""
    if reasoning:
        logger.debug(
            "content is empty; attempting JSON extraction from reasoning chain (%d chars)",
            len(reasoning),
        )
        match = re.search(r'\{[^{}]*"suggestions"[^{}]*\}', reasoning, re.DOTALL)
        if match:
            return match.group(0)

    return content


def _parse_coach_output(raw: str) -> CoachOutput:
    """
    Parse the LLM response into a CoachOutput.
    Handles markdown code fences and light prose wrapping.
    """
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()

    match = re.search(r'\{.*?"suggestions".*?\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    data = json.loads(cleaned)
    return CoachOutput(**data)


# ── Groq client (cached) ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_client() -> Groq:
    """
    Build and cache the Groq client.
    """
    if not settings.groq_api_key:
        logger.error(
            "GROQ_API_KEY is not configured. "
            "Set it in .env to enable coach suggestions."
        )
    return Groq(api_key=settings.groq_api_key)


# ── Graph node ────────────────────────────────────────────────────────────────

def coach_node(state: AgentState) -> dict:
    """
    Single LangGraph node for the Coach Agent.
    Calls Groq API and returns a partial state update.
    """
    client = _get_client()

    user_prompt = _build_user_prompt(
        state["pattern_insight"],
        state["anomaly_flag"],
        state["user_preferences"],
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    logger.info(
        "Calling Groq coach node (model: %s, anomaly: %s)…",
        settings.groq_model,
        state["anomaly_flag"],
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            max_tokens=1024,   # Suggestions are short — no need for DeepSeek reasoning budget
            temperature=0.2,   # Prefer deterministic suggestions for dashboard stability
        )
        raw_content: str = _extract_content(completion.choices[0].message)
        finish_reason = completion.choices[0].finish_reason

        if finish_reason == "length":
            logger.warning(
                "Coach LLM response truncated (finish_reason=length). "
                "Consider raising max_tokens."
            )
        logger.debug("Raw LLM response (finish=%s): %s", finish_reason, raw_content)

        result = _parse_coach_output(raw_content)
        logger.info(
            "Coach suggestions generated: %d suggestions, challenge=%r",
            len(result.suggestions),
            result.challenge,
        )
        return {"output": result}

    except (json.JSONDecodeError, ValueError, TypeError) as parse_exc:
        logger.warning(
            "Failed to parse LLM output as CoachOutput (%s). Using fallback.",
            parse_exc,
        )
        fallback = _FALLBACK_BY_ANOMALY.get(state["anomaly_flag"], _FALLBACK_BY_ANOMALY["DOWNWARD_SPIRAL"])
        return {"output": CoachOutput(**fallback)}

    except Exception as api_exc:
        logger.error("Groq API call failed in coach node: %s", api_exc, exc_info=True)
        fallback = _FALLBACK_BY_ANOMALY.get(state["anomaly_flag"], _FALLBACK_BY_ANOMALY["DOWNWARD_SPIRAL"])
        return {"output": CoachOutput(**fallback)}


# ── Graph compilation ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_coach_graph():
    """
    Builds and compiles the Coach Agent LangGraph graph once.

    Graph topology:  START -> coach -> END
    """
    graph = StateGraph(AgentState)
    graph.add_node("coach", coach_node)
    graph.set_entry_point("coach")
    graph.add_edge("coach", END)
    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_coach(
    pattern_insight: str,
    anomaly_flag: AnomalyFlag | None,
    user_preferences: dict | None = None,
) -> CoachOutput:
    """
    Invoke the Coach Agent graph and return structured output.

    Short-circuit guard: if anomaly_flag is None, the LLM is never called
    and an empty CoachOutput is returned immediately. The Coach Agent only
    fires when there is a real anomaly signal — no suggestions on good weeks.

    Args:
        pattern_insight  : Natural-language narrative from the Pattern Agent.
        anomaly_flag     : Anomaly detected in the window. If None, returns empty.
        user_preferences : Optional dict of user profile hints (habits, pace, etc.).

    Returns:
        CoachOutput with 1–2 suggestions and a 1-day challenge.
        Returns CoachOutput(suggestions=[], challenge="") when anomaly_flag is None.
    """
    # Poka-Yoke short-circuit — no LLM call on healthy weeks
    if anomaly_flag is None:
        logger.info("Coach agent skipped — no anomaly flag present.")
        return CoachOutput(suggestions=_EMPTY_OUTPUT_SUGGESTIONS, challenge=_EMPTY_OUTPUT_CHALLENGE)

    graph = get_coach_graph()

    initial_state: AgentState = {
        "pattern_insight":  pattern_insight,
        "anomaly_flag":     anomaly_flag,
        "user_preferences": user_preferences or {},
        "output":           None,
    }

    final_state = graph.invoke(initial_state)
    output: CoachOutput = final_state["output"]

    if not output:
        logger.warning("Coach agent returned no output. Using fallback.")
        fallback = _FALLBACK_BY_ANOMALY.get(anomaly_flag, _FALLBACK_BY_ANOMALY["DOWNWARD_SPIRAL"])
        output = CoachOutput(**fallback)

    return output
