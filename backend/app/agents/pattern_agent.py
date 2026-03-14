"""
agents/pattern_agent.py
========================
A single-node LangGraph graph that accepts a WindowStats summary and an
optional AnomalyFlag, then synthesises a 3–5 sentence natural-language
narrative describing the user's observed emotional trends.

Design choices (mirrors reflection_agent.py conventions):
  - Single StateGraph node (one-shot synthesis, no cycles needed)
  - TypedDict state with explicit fields
  - Direct HuggingFace InferenceClient for chat completions (same model)
  - lru_cache on the compiled graph — warms once, reuses across requests
  - Manual JSON parse + regex fallback (HF models don't support
    structured output / tool calls universally)

Output contract:
  - `insights`  : 3–5 sentences describing the emotional trend window
  - `highlight` : Single-sentence card headline (≤15 words)
    e.g. "Your Sunday nights have been heavy for the past 3 weeks."

Agent persona (System Prompt Engineering):
  - Insightful but never clinical
  - Speaks in second person ("you", "your") — personal and direct
  - Describes patterns as observations, not diagnoses
  - Always frames downward trends with curiosity, not alarm

Kaizen improvements applied
----------------------------
- Follows the exact same lru_cache / InferenceClient / JSON-fallback
  pattern as reflection_agent.py — no new abstractions introduced.
- AnomalyFlag is rendered as human-readable text in the prompt so the
  model understands its significance without seeing raw enum values.
- Fallback insights are pre-written for all three AnomalyFlag values
  so the endpoint never returns an empty body.
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
from app.services.pattern_engine import AnomalyFlag, WindowStats

logger = logging.getLogger(__name__)

# ── Fallback content — used when LLM output cannot be parsed ─────────────────

_FALLBACK_INSIGHTS = [
    "Your emotional patterns over the past week show some notable shifts.",
    "There have been recurring themes in how you're feeling across multiple entries.",
    "The data suggests your mood has been fluctuating more than usual recently.",
]
_FALLBACK_HIGHLIGHT = "Your recent entries show some interesting emotional patterns."

# Human-readable descriptions injected into the prompt for each anomaly type
_ANOMALY_DESCRIPTIONS: dict[str, str] = {
    "HIGH_VOLATILITY":  "significant emotional volatility — mood swings more than usual",
    "DOWNWARD_SPIRAL":  "a sustained downward trend — negative emotions dominant for several days",
    "LOW_ENGAGEMENT":   "low engagement — very few journal entries in this period",
}


# ── Structured output ─────────────────────────────────────────────────────────

class PatternOutput(BaseModel):
    """Structured output from the Pattern Agent LLM call."""

    insights: list[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3 to 5 sentences describing the user's emotional trend.",
    )
    highlight: str = Field(
        ...,
        description="Single headline sentence (≤15 words) for the Pattern Card UI.",
    )


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    window_stats:    dict              # WindowStats serialised via .model_dump()
    anomaly_flag:    AnomalyFlag | None
    history_summary: str               # Short summary of past pattern narratives
    output:          PatternOutput | None


# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an insightful, non-clinical emotional pattern analyst inside an app
called The Silent Spiral. Your role is to synthesise the past 7 days of
emotional data into a personal, warm narrative that helps the user
understand themselves better.

Rules you MUST follow:
1. Write exactly 3 to 5 sentences for `insights`. Each sentence should
   describe one distinct aspect of the emotional trend.
2. Write exactly 1 sentence for `highlight` — a punchy, specific card
   headline of 15 words or fewer (e.g. "Your evenings have been heavy
   for the past two weeks.").
3. Speak in second person: "you", "your".
4. Describe patterns as curious observations, not diagnoses or warnings.
5. Never use clinical terms: no "depression", "anxiety disorder",
   "trauma", "mental illness", etc.
6. Never tell the user what to do — observe only.
7. Ground your language in the specific emotions provided (dominant
   emotion, average scores). Be specific, not generic.

Return ONLY valid JSON matching this schema — no prose, no markdown:
{
  "insights": ["<sentence_1>", "<sentence_2>", "<sentence_3>"],
  "highlight": "<headline>"
}
"""


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_user_prompt(
    window_stats: dict,
    anomaly_flag: AnomalyFlag | None,
    history_summary: str,
) -> str:
    dominant = window_stats.get("dominant_emotion", "unknown")
    volatility = window_stats.get("volatility_score", 0.0)
    entry_count = window_stats.get("entry_count", 0)

    # Top-3 emotions by average score
    avg_scores: dict[str, float] = window_stats.get("avg_scores", {})
    top_emotions = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    emotions_str = ", ".join(
        f"{label} ({score:.0%})" for label, score in top_emotions
    ) or "not available"

    anomaly_str = (
        _ANOMALY_DESCRIPTIONS.get(anomaly_flag, anomaly_flag)
        if anomaly_flag
        else "no significant anomaly detected"
    )

    history_block = (
        f"\n\nPrevious pattern summary for context:\n{history_summary}"
        if history_summary.strip()
        else ""
    )

    return (
        f"Emotional window data:\n"
        f"  - Dominant emotion : {dominant}\n"
        f"  - Top emotions     : {emotions_str}\n"
        f"  - Volatility score : {volatility:.4f}\n"
        f"  - Entries analysed : {entry_count}\n"
        f"  - Anomaly detected : {anomaly_str}"
        f"{history_block}\n\n"
        "Generate the pattern narrative now."
    )


# ── Content extraction helper (handles thinking/reasoning models) ─────────────

def _extract_content(message) -> str:
    """
    Extract the final answer text from a chat completion message.

    DeepSeek-R1 reasoning models sometimes return an empty `content` field,
    placing the answer inside a `reasoning` attribute.  Try `content` first,
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
        match = re.search(r'\{[^{}]*"insights"[^{}]*\}', reasoning, re.DOTALL)
        if match:
            return match.group(0)

    return content


def _parse_pattern_output(raw: str) -> PatternOutput:
    """
    Parse the LLM response into a PatternOutput.
    Handles markdown code fences and light prose wrapping.
    """
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()

    # Find the JSON object that contains an 'insights' key
    match = re.search(r'\{.*?"insights".*?\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    data = json.loads(cleaned)
    return PatternOutput(**data)


# ── Groq client (cached) ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_client() -> Groq:
    """
    Build and cache the Groq client.

    Migrated from HuggingFace InferenceClient on 2026-03-13 after HF credits
    were depleted (HTTP 402). Groq is OpenAI-API-compatible — same
    .chat.completions.create() interface, minimal change.
    """
    if not settings.groq_api_key:
        logger.error(
            "GROQ_API_KEY is not configured. "
            "Set it in .env to enable pattern narrative."
        )
    return Groq(api_key=settings.groq_api_key)


# ── Graph node ────────────────────────────────────────────────────────────────

def pattern_node(state: AgentState) -> dict:
    """
    Single LangGraph node for the Pattern Agent.
    Calls HuggingFace Inference API and returns a partial state update.
    """
    client = _get_client()

    user_prompt = _build_user_prompt(
        state["window_stats"],
        state["anomaly_flag"],
        state["history_summary"],
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    logger.info(
        "Calling Groq pattern node (model: %s, anomaly: %s)…",
        settings.groq_model,
        state["anomaly_flag"],
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            max_tokens=4096,
            temperature=0.2,   # Lower temperature for stable, repeatable trend narratives
        )
        raw_content: str = _extract_content(completion.choices[0].message)
        finish_reason = completion.choices[0].finish_reason

        if finish_reason == "length":
            logger.warning(
                "Pattern LLM response truncated (finish_reason=length). "
                "Consider raising max_tokens."
            )
        logger.debug("Raw LLM response (finish=%s): %s", finish_reason, raw_content)

        result = _parse_pattern_output(raw_content)
        logger.info("Pattern insights generated: %s", result.insights)
        return {"output": result}

    except (json.JSONDecodeError, ValueError, TypeError) as parse_exc:
        logger.warning(
            "Failed to parse LLM output as PatternOutput (%s). Using fallback.",
            parse_exc,
        )
        return {
            "output": PatternOutput(
                insights=_FALLBACK_INSIGHTS,
                highlight=_FALLBACK_HIGHLIGHT,
            )
        }
    except Exception as api_exc:
        logger.error("HuggingFace API call failed in pattern node: %s", api_exc, exc_info=True)
        return {
            "output": PatternOutput(
                insights=_FALLBACK_INSIGHTS,
                highlight=_FALLBACK_HIGHLIGHT,
            )
        }


# ── Graph compilation ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_pattern_graph():
    """
    Builds and compiles the Pattern Agent LangGraph graph once.

    Graph topology:  START -> pattern -> END
    """
    graph = StateGraph(AgentState)
    graph.add_node("pattern", pattern_node)
    graph.set_entry_point("pattern")
    graph.add_edge("pattern", END)
    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_pattern(
    window_stats: WindowStats,
    anomaly_flag: AnomalyFlag | None = None,
    history_summary: str = "",
) -> PatternOutput:
    """
    Invoke the Pattern Agent graph and return structured output.

    Args:
        window_stats    : WindowStats from pattern_engine.compute_window().
        anomaly_flag    : Optional anomaly detected in the window.
        history_summary : Short prose summary of previous pattern narratives
                          for conversational continuity (empty string = skip).

    Returns:
        PatternOutput with 3–5 insight sentences and a highlight headline.
    """
    graph = get_pattern_graph()

    initial_state: AgentState = {
        "window_stats":    window_stats.model_dump(),
        "anomaly_flag":    anomaly_flag,
        "history_summary": history_summary,
        "output":          None,
    }

    final_state = graph.invoke(initial_state)
    output: PatternOutput = final_state["output"]

    if not output or not (3 <= len(output.insights) <= 5):
        logger.warning(
            "Pattern agent returned unexpected insight count (got %s). Using fallback.",
            len(output.insights) if output else 0,
        )
        output = PatternOutput(
            insights=_FALLBACK_INSIGHTS,
            highlight=_FALLBACK_HIGHLIGHT,
        )

    return output
