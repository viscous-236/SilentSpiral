"""Speech transcription adapter service.

Uses Groq's OpenAI-compatible audio transcription endpoint so callers can pass
raw audio bytes and receive text output without handling provider specifics.
"""

from __future__ import annotations

from typing import Literal

import httpx

from app.core.config import settings

TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
SUPPORTED_LOCALES = ("en-US", "hi-IN")


def locale_to_language_code(locale: Literal["en-US", "hi-IN"]) -> str:
    """Convert BCP-47 locale to Whisper language code."""
    return "hi" if locale == "hi-IN" else "en"


def transcribe_audio_bytes(
    audio_bytes: bytes,
    filename: str,
    locale: Literal["en-US", "hi-IN"],
) -> str:
    """Transcribe uploaded audio bytes via Groq Whisper.

    Raises RuntimeError for configuration or provider failures.
    """
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Unable to transcribe audio."
        )

    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    files = {
        "file": (
            filename or "voice-input.m4a",
            audio_bytes,
            "application/octet-stream",
        )
    }
    data = {
        "model": "whisper-large-v3",
        "language": locale_to_language_code(locale),
        "response_format": "json",
        "temperature": "0",
    }

    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                TRANSCRIBE_URL,
                headers=headers,
                data=data,
                files=files,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            raise RuntimeError("Invalid GROQ_API_KEY for transcription.") from exc
        if status == 429:
            raise RuntimeError(
                "Transcription rate limit reached. Please retry shortly."
            ) from exc
        raise RuntimeError(
            "Transcription provider failed. Please retry."
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Unable to reach transcription provider. Check your network and retry."
        ) from exc

    payload = response.json()
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RuntimeError("No speech detected in audio.")
    return text
