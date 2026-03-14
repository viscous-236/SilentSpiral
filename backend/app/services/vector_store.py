"""
services/vector_store.py
========================
Qdrant-backed vector store for journal entry embeddings.

Used by the Mirror Prompt feature to surface semantically similar past
phrases from a user's journal history — reflecting the user's own words
back to them in reflection prompts.

Design choices
--------------
- sentence-transformers model loaded once (lru_cache singleton).
- Qdrant client loaded once (lru_cache singleton).
- Collection configured with cosine distance to match semantic search use-case.
- `find_mirror_phrase` enforces BOTH guards as Poka-Yoke:
    1. Age guard  — entry must be >= mirror_min_age_days old
    2. Similarity — cosine_similarity must be >= mirror_similarity_threshold
  The system is architecturally incapable of surfacing a recent or
  weakly-matched entry (not just a policy — a hard filter).

Public API
----------
  upsert_entry(entry_id, text, timestamp, metadata)  → None
  search_similar(text, top_k, min_similarity)         → list[dict]
  find_mirror_phrase(text)                            → str | None
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)

_VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension


# ── Singletons (loaded once, cached forever) ─────────────────────────────────

@lru_cache(maxsize=1)
def _load_embedding_model() -> SentenceTransformer:
    """Load sentence-transformers model once at first call."""
    logger.info("Loading embedding model: %s", settings.embedding_model_name)
    model = SentenceTransformer(settings.embedding_model_name)
    logger.info("Embedding model loaded.")
    return model


@lru_cache(maxsize=1)
def _get_qdrant_client() -> QdrantClient:
    """
    Create and cache a Qdrant client.

    Also ensures the configured collection exists.
    """
    if not settings.qdrant_url:
        raise RuntimeError("QDRANT_URL is not configured.")

    logger.info("Initialising Qdrant client at: %s", settings.qdrant_url)
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )

    collection_name = settings.qdrant_collection_name
    existing = {c.name for c in client.get_collections().collections}
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'.", collection_name)
    else:
        logger.info("Qdrant collection '%s' ready.", collection_name)

    return client


# ── Public API ────────────────────────────────────────────────────────────────

def upsert_entry(
    entry_id: str,
    text: str,
    timestamp: datetime,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Embed a journal entry and persist it in Qdrant.

    Args:
        entry_id  : Unique identifier for the entry (used as Qdrant point ID).
        text      : Raw journal text to embed.
        timestamp : When the entry was written (timezone-aware recommended).
        metadata  : Optional extra key-value data stored alongside the vector.

    Raises:
        ValueError: If entry_id or text is empty.
    """
    if not entry_id.strip():
        raise ValueError("upsert_entry: entry_id must not be empty.")
    if not text.strip():
        raise ValueError("upsert_entry: text must not be empty.")

    # Normalise timestamp to UTC unix epoch (float) for age comparisons
    ts_epoch = timestamp.timestamp()

    payload: dict[str, Any] = {
        "timestamp": ts_epoch,
        "text": text,
        **(metadata or {}),
    }

    model = _load_embedding_model()
    embedding: list[float] = model.encode(text, normalize_embeddings=True).tolist()

    client = _get_qdrant_client()
    client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=[
            PointStruct(
                id=entry_id,
                vector=embedding,
                payload=payload,
            )
        ],
        wait=True,
    )
    logger.debug("Upserted entry '%s' into vector store.", entry_id)


def search_similar(
    text: str,
    top_k: int = 5,
    min_similarity: float | None = None,
) -> list[dict]:
    """
    Find the most semantically similar past journal entries in Qdrant.

    Args:
        text           : Query text to compare against stored entries.
        top_k          : Maximum number of results to return before filtering.
        min_similarity : If set, only return results with cosine similarity >= this.

    Returns:
        List of dicts, each containing:
          {
            "id":         str,    # entry_id
            "text":       str,    # original journal text
            "similarity": float,  # cosine similarity in [0, 1]
            "metadata":   dict,   # stored metadata (includes "timestamp")
          }
        Sorted descending by similarity. Empty list if no results qualify.
    """
    if not text.strip():
        raise ValueError("search_similar: query text must not be empty.")

    client = _get_qdrant_client()
    count_result = client.count(
        collection_name=settings.qdrant_collection_name,
        exact=False,
    )
    if count_result.count == 0:
        return []

    model = _load_embedding_model()
    query_embedding: list[float] = model.encode(text, normalize_embeddings=True).tolist()

    results = client.search(
        collection_name=settings.qdrant_collection_name,
        query_vector=query_embedding,
        limit=min(top_k, count_result.count),
        with_payload=True,
    )

    output: list[dict] = []
    for point in results:
        similarity = round(max(0.0, min(1.0, float(point.score))), 4)

        if min_similarity is not None and similarity < min_similarity:
            continue

        payload = dict(point.payload or {})
        text_value = str(payload.pop("text", ""))

        output.append({
            "id":         str(point.id),
            "text":       text_value,
            "similarity": similarity,
            "metadata":   payload,
        })

    # Qdrant returns highest score first for cosine search.
    return output


def find_mirror_phrase(text: str) -> str | None:
    """
    Return a past journal phrase suitable for a Mirror Prompt, or None.

    Applies BOTH guards from the plan spec (Poka-Yoke):
      1. Similarity >= settings.mirror_similarity_threshold (default 0.85)
      2. Entry written >= settings.mirror_min_age_days ago  (default 7 days)

    Only the single best-matching candidate (highest similarity) that
    passes both guards is returned.

    Args:
        text: Current journal text to find a mirror phrase for.

    Returns:
        The original stored journal text of the best match, or None if no
        entry passes both guards.
    """
    candidates = search_similar(
        text,
        top_k=10,  # fetch extra candidates so age filter has room to work
        min_similarity=settings.mirror_similarity_threshold,
    )

    if not candidates:
        return None

    now_epoch = datetime.now(timezone.utc).timestamp()
    min_age_seconds = settings.mirror_min_age_days * 86_400  # days → seconds

    for candidate in candidates:  # sorted best-first
        entry_ts: float = candidate["metadata"].get("timestamp", now_epoch)
        age_seconds = now_epoch - entry_ts

        if age_seconds >= min_age_seconds:
            logger.debug(
                "Mirror phrase found: entry '%s' (similarity=%.4f, age_days=%.1f)",
                candidate["id"],
                candidate["similarity"],
                age_seconds / 86_400,
            )
            return candidate["text"]

    logger.debug("No mirror phrase met both similarity and age guards for this entry.")
    return None
