"""
Burst Session Schemas
=====================
Pydantic models for the /agent/burst/* endpoints.

Schemas defined here:
  - BurstAckRequest    — POST /agent/burst/ack  (mid-session acknowledgment)
  - BurstAckResponse   — POST /agent/burst/ack  response
  - BurstCloseRequest  — POST /agent/burst/close (session closing message)
  - BurstCloseResponse — POST /agent/burst/close response

Design note:
  No user_id, no auth, no emotion scores. Burst is intentionally ephemeral —
  nothing from these requests is written to the database, vector store, or
  analytics pipeline. The only effect is a Groq API call → text response.
"""

from pydantic import BaseModel, Field


class BurstAckRequest(BaseModel):
    """
    Request body for POST /agent/burst/ack.

    Called every ~20 seconds during an active Burst session.
    The agent returns a single short empathetic acknowledgment line.
    The partial text is NOT stored anywhere after the request completes.
    """

    partial_text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Whatever the user has typed so far in this Burst session",
        examples=["I'm so tired of pretending everything is fine at work."],
    )
    elapsed_seconds: int = Field(
        ...,
        ge=0,
        le=300,
        description="How many seconds have elapsed in the session (0–300)",
    )


class BurstAckResponse(BaseModel):
    """
    Response from POST /agent/burst/ack.

    Returns a single short acknowledgment line (≤12 words).
    The agent persona: warm, present, non-judgmental — not therapeutic.
    """

    acknowledgment: str = Field(
        ...,
        description="A short, warm acknowledgment line (≤12 words). E.g. 'I hear you. Keep going.'",
    )


class BurstCloseRequest(BaseModel):
    """
    Request body for POST /agent/burst/close.

    Called once when the Burst session ends (timer expires or user taps 'I'm done').
    The full session text is passed so the agent can craft a warm closing.
    Nothing is persisted after this call.
    """

    session_text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="The complete text the user wrote during the Burst session",
        examples=["I've been holding this in for weeks. Work is overwhelming and I feel invisible."],
    )


class BurstCloseResponse(BaseModel):
    """
    Response from POST /agent/burst/close.

    Returns 2–3 sentences of warm, affirming closure. No questions, no advice.
    """

    closing_message: str = Field(
        ...,
        description="2–3 sentence warm closing affirmation. No advice, no questions, no clinical language.",
    )
