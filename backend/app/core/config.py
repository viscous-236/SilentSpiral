"""
core/config.py
==============
Application settings loaded from environment variables via pydantic-settings.

Kaizen improvements applied
----------------------------
- Poka-Yoke: `groq_api_key` emits a WARNING at startup if empty,
  rather than failing silently on the first /agent/reflect call.
- `nlp_emotion_threshold` and `nlp_top_k` have Field validators to
  prevent nonsense values (threshold must be 0–1, top_k must be ≥1).
- Module-level docstring added for consistency with rest of codebase.
- Added Vector Store / Mirror Prompt settings: qdrant_url,
    qdrant_api_key, qdrant_collection_name, embedding_model_name,
    mirror_similarity_threshold, mirror_min_age_days.
- 2026-03-13: Switched reflection LLM to Groq (free tier) after HuggingFace
  inference credits were depleted. Groq offers llama-3.3-70b-versatile at
  no cost on the free tier with no credit card required.
"""

import logging
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All values can be overridden via a .env file at the backend root.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
      extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "Silent Spiral API"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── NLP ───────────────────────────────────────────────────────────────────
    nlp_model_name: str = "SamLowe/roberta-base-go_emotions"
    nlp_emotion_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    nlp_top_k: int = Field(default=5, ge=1)

    # ── HuggingFace (NLP emotion classifier only — not reflection LLM) ────────
    huggingface_api_token: str = ""

    # ── Groq (free-tier LLM for Reflection Agent) ────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"  # free on Groq; no credits needed

    # ── Vector Store / Mirror Prompt ─────────────────────────────────────────
    qdrant_url: str = ""            # e.g. https://xxx.gcp.cloud.qdrant.io
    qdrant_api_key: str = ""         # Qdrant Cloud API key
    qdrant_collection_name: str = "journal_entries"
    embedding_model_name: str = "all-MiniLM-L6-v2"
    mirror_similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    mirror_min_age_days: int = Field(default=7, ge=0)

    # ── Database (MongoDB Atlas preferred) ──────────────────────────────────
    # Example: mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
    mongodb_url: str = ""
    mongodb_db_name: str = "silent_spiral"
    mongodb_users_collection: str = "users"

    # ── Legacy Postgres fallback (optional during migration) ───────────────
    # Prefer Neon pooled URL when available:
    # postgresql+asyncpg://<user>:<password>@ep-xxx-pooler.<region>.aws.neon.tech/<db>
    neon_database_url: str = ""

    # Backward-compatible fallback (older envs may still use DATABASE_URL).
    # postgresql+asyncpg://postgres.xxx:pass@pooler.supabase.com:6543/postgres
    database_url: str = ""

    # ── Kaizen / Poka-Yoke: warn at startup if keys are missing ────────────────
    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug_aliases(cls, v):
        """
        Tolerate common non-boolean env values from shell environments.

        Some tooling exports DEBUG=release globally, which otherwise crashes
        startup before dotenv values are applied.
        """
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return v

    @field_validator("groq_api_key", mode="after")
    @classmethod
    def _warn_if_groq_key_missing(cls, v: str) -> str:
        if not v:
            logger.warning(
                "GROQ_API_KEY is not set. "
                "POST /agent/reflect will return fallback questions. "
                "Get a free key at https://console.groq.com"
            )
        return v

    @model_validator(mode="after")
    def _warn_if_database_url_missing(self):
        mongo_url = (self.mongodb_url or "").strip()
        if mongo_url:
            return self

        active_url = (self.neon_database_url or self.database_url or "").strip()
        if not active_url:
            logger.warning(
                "No database URL configured. Auth routes will fail. "
                "Set MONGODB_URL (preferred) or NEON_DATABASE_URL/DATABASE_URL."
            )
        elif "sqlite" in active_url:
            logger.warning(
                "Database URL points to SQLite ('%s'). "
                "This will fail in production — use MongoDB Atlas or managed Postgres.",
                active_url,
            )
        return self

    @field_validator("qdrant_url", mode="after")
    @classmethod
    def _warn_if_qdrant_url_missing(cls, v: str) -> str:
        if not v:
            logger.warning(
                "QDRANT_URL is not set. Vector store operations will fail. "
                "Create a free cluster at https://cloud.qdrant.io"
            )
        return v


# Singleton — import this everywhere, instantiated once at module load
settings = Settings()
