"""Transcription Router
===================
Provides POST /transcribe endpoint for audio-to-text fallback.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.transcription import TranscriptionResponse
from app.services.transcription_service import transcribe_audio_bytes

router = APIRouter(prefix="/transcribe", tags=["Transcription"])

MAX_AUDIO_BYTES = 12 * 1024 * 1024
ALLOWED_AUDIO_EXTS = (".m4a", ".mp4", ".wav", ".mp3", ".aac", ".ogg", ".webm", ".caf", ".3gp")


@router.post(
    "",
    response_model=TranscriptionResponse,
    summary="Transcribe uploaded audio to text",
    description=(
        "Accepts an audio file and locale, then returns recognized text. "
        "Used as Expo Go fallback for voice input."
    ),
)
async def transcribe_audio(
    audio: UploadFile = File(...),
    locale: Literal["en-US", "hi-IN"] = Form("en-US"),
) -> TranscriptionResponse:
    content_type = (audio.content_type or "").lower()
    filename = (audio.filename or "voice-input.m4a").lower()
    has_audio_mime = content_type.startswith("audio/")
    has_audio_ext = filename.endswith(ALLOWED_AUDIO_EXTS)

    if not has_audio_mime and not has_audio_ext:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be a supported audio type.",
        )

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio file too large. Max supported size is 12MB.",
        )

    try:
        transcript = transcribe_audio_bytes(
            audio_bytes=data,
            filename=filename,
            locale=locale,
        )
    except RuntimeError as exc:
        message = str(exc)
        if "Invalid GROQ_API_KEY" in message:
            raise HTTPException(status_code=401, detail=message) from exc
        if "rate limit" in message.lower():
            raise HTTPException(status_code=429, detail=message) from exc
        if "No speech detected" in message:
            raise HTTPException(status_code=422, detail=message) from exc
        raise HTTPException(status_code=503, detail=message) from exc

    return TranscriptionResponse(text=transcript, locale=locale)
