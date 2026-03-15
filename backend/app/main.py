"""
Reflectra — FastAPI Backend
================================
Entry point for the application.

Run locally:
    cd backend/
    uvicorn app.main:app --reload --port 8000

Documentation available at:
    http://localhost:8000/docs  (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.mongodb import close_mongo_client, init_mongodb
from app.routes.agents import router as agents_router
from app.routes.auth import router as auth_router
from app.routes.emotions import router as emotions_router
from app.routes.patterns import router as patterns_router
from app.routes.transcribe import router as transcribe_router
from app.services.nlp_engine import _load_model

# Configure structured logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ── Kaizen #3: Startup warmup ─────────────────────────────────────────────────
# The NLP model (~500MB) is loaded once via lru_cache. Without warmup, the
# first POST /analyze request would bear the full cold-start latency.
# This lifespan event forces the load at boot time instead.

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🗄️ Initialising MongoDB indexes...")
    await init_mongodb()
    logger.info("✅ Database ready.")

    logger.info("🔥 Warming up NLP model at startup...")
    try:
        _load_model()   # Triggers lru_cache population — subsequent calls are instant
        logger.info("✅ NLP model warm. Server ready.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️  NLP model failed to load (%s). /analyze will return 503 until the model is available.", exc)
    yield
    close_mongo_client()
    logger.info("🛑 Shutting down.")
# ── App creation ─────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    description=(
        "Backend API for Reflectra — a personal mental-state "
        "awareness companion. Provides NLP emotion analysis, pattern detection, "
        "and AI agent responses."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS ─────────────────────────────────────────────────────────────────────
# Allow React Native app (and localhost dev) to call this API

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production to your app's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ──────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(emotions_router)
app.include_router(patterns_router)
app.include_router(agents_router)
app.include_router(transcribe_router)

# Future routers (register here as tasks complete):
# from app.routes.journal import router as journal_router
# app.include_router(journal_router)


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"], summary="Health check")
async def health_check() -> dict:
    """Returns 200 OK when the service is up. Also surfaces active model names for ops."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "nlp_model": settings.nlp_model_name,
        "llm_model": settings.groq_model,
    }
