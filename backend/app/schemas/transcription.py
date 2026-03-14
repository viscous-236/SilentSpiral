from typing import Literal

from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    """Response body for POST /transcribe."""

    text: str = Field(..., description="Recognized text extracted from uploaded audio")
    locale: Literal["en-US", "hi-IN"] = Field(
        ..., description="Locale used during transcription"
    )
