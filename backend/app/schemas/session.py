"""
Session Chat Schemas
====================
Pydantic models for ephemeral 10-minute listening sessions.

No request payload in this module is persisted by design.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SessionMessage(BaseModel):
    """One message in the client-maintained in-session history."""

    role: Literal["user", "agent"] = Field(
        ...,
        description="Message speaker role",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=3000,
        description="Message text content",
    )


class SessionStartRequest(BaseModel):
    """Request body for POST /agent/session/start."""

    duration_seconds: int = Field(
        default=600,
        ge=600,
        le=600,
        description="Session duration in seconds. Fixed at 600 for v1.",
    )


class SessionStartResponse(BaseModel):
    """Response body for POST /agent/session/start."""

    session_id: str = Field(..., description="Ephemeral session identifier")
    agent_message: str = Field(..., description="Opening listening message")
    remaining_seconds: int = Field(..., ge=0, le=600)


class SessionMessageRequest(BaseModel):
    """Request body for POST /agent/session/message."""

    session_id: str = Field(..., min_length=5, max_length=128)
    user_message: str = Field(..., min_length=1, max_length=3000)
    elapsed_seconds: int = Field(..., ge=0, le=600)
    history: list[SessionMessage] = Field(
        default_factory=list,
        max_length=20,
        description="Recent in-session turns, provided by the client",
    )


class SessionMessageResponse(BaseModel):
    """Response body for POST /agent/session/message."""

    agent_reply: str = Field(...)
    remaining_seconds: int = Field(..., ge=0, le=600)
    session_ended: bool = Field(...)


class SessionCloseRequest(BaseModel):
    """Request body for POST /agent/session/close."""

    session_id: str = Field(..., min_length=5, max_length=128)
    history: list[SessionMessage] = Field(default_factory=list, max_length=24)
    session_text: str = Field(
        default="",
        max_length=12000,
        description="Optional plain transcript text built on client",
    )


class SessionCloseResponse(BaseModel):
    """Response body for POST /agent/session/close."""

    closing_message: str = Field(...)
