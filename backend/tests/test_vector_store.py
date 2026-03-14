"""
tests/test_vector_store.py
===========================
Unit tests for app/services/vector_store.py.

Methodology:
  - All Qdrant + sentence-transformers calls are mocked (no network/model load).
  - Behavioral contracts: verify guards and score handling, not embedding values.
  - Poka-Yoke coverage: similarity and age guards for mirror phrase retrieval.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return _now() - timedelta(days=n)


@dataclass
class FakePoint:
    id: str
    score: float
    payload: dict


class TestUpsertEntry:
    def test_raises_on_empty_entry_id(self):
        from app.services.vector_store import upsert_entry

        with pytest.raises(ValueError, match="entry_id"):
            upsert_entry("", "some text", _now())

    def test_raises_on_empty_text(self):
        from app.services.vector_store import upsert_entry

        with pytest.raises(ValueError, match="text"):
            upsert_entry("id1", "   ", _now())

    def test_calls_qdrant_upsert(self):
        from app.services import vector_store

        mock_model = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [0.1, 0.2]
        mock_client = MagicMock()

        with patch.object(vector_store, "_load_embedding_model", return_value=mock_model), patch.object(
            vector_store,
            "_get_qdrant_client",
            return_value=mock_client,
        ):
            vector_store.upsert_entry("e1", "I feel heavy today.", _days_ago(10))

        mock_client.upsert.assert_called_once()
        kwargs = mock_client.upsert.call_args.kwargs
        assert kwargs["collection_name"] == vector_store.settings.qdrant_collection_name
        assert kwargs["wait"] is True
        point = kwargs["points"][0]
        assert str(point.id) == "e1"
        assert point.payload["text"] == "I feel heavy today."
        assert isinstance(point.payload["timestamp"], float)


class TestSearchSimilar:
    def _mock_client(self, points, count=5):
        mock_client = MagicMock()
        mock_client.count.return_value = SimpleNamespace(count=count)
        mock_client.search.return_value = points
        return mock_client

    def test_returns_empty_for_empty_collection(self):
        from app.services import vector_store

        mock_model = MagicMock()
        mock_client = self._mock_client(points=[], count=0)

        with patch.object(vector_store, "_load_embedding_model", return_value=mock_model), patch.object(
            vector_store,
            "_get_qdrant_client",
            return_value=mock_client,
        ):
            result = vector_store.search_similar("anything")

        assert result == []

    def test_raises_on_empty_query(self):
        from app.services.vector_store import search_similar

        with pytest.raises(ValueError, match="query text"):
            search_similar("   ")

    def test_similarity_uses_qdrant_score_directly(self):
        from app.services import vector_store

        ts = _days_ago(10).timestamp()
        mock_model = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [0.1, 0.2]
        mock_client = self._mock_client(
            points=[
                FakePoint(
                    id="e1",
                    score=0.8,
                    payload={"text": "I feel invisible.", "timestamp": ts},
                )
            ],
            count=1,
        )

        with patch.object(vector_store, "_load_embedding_model", return_value=mock_model), patch.object(
            vector_store,
            "_get_qdrant_client",
            return_value=mock_client,
        ):
            results = vector_store.search_similar("I feel unseen.")

        assert len(results) == 1
        assert results[0]["similarity"] == pytest.approx(0.8, abs=1e-3)
        assert results[0]["id"] == "e1"

    def test_min_similarity_filter_excludes_low_scores(self):
        from app.services import vector_store

        ts = _days_ago(10).timestamp()
        mock_model = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [0.1, 0.2]
        mock_client = self._mock_client(
            points=[
                FakePoint(id="e1", score=0.95, payload={"text": "text one", "timestamp": ts}),
                FakePoint(id="e2", score=0.5, payload={"text": "text two", "timestamp": ts}),
            ],
            count=2,
        )

        with patch.object(vector_store, "_load_embedding_model", return_value=mock_model), patch.object(
            vector_store,
            "_get_qdrant_client",
            return_value=mock_client,
        ):
            results = vector_store.search_similar("query", min_similarity=0.8)

        assert len(results) == 1
        assert results[0]["id"] == "e1"

    def test_similarity_clamped_to_one(self):
        """Floating-point edge case: score > 1 gets clamped to 1.0."""
        from app.services import vector_store

        ts = _days_ago(10).timestamp()
        mock_model = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [0.1, 0.2]
        mock_client = self._mock_client(
            points=[
                FakePoint(
                    id="e1",
                    score=1.0001,
                    payload={"text": "text", "timestamp": ts},
                )
            ],
            count=1,
        )

        with patch.object(vector_store, "_load_embedding_model", return_value=mock_model), patch.object(
            vector_store,
            "_get_qdrant_client",
            return_value=mock_client,
        ):
            results = vector_store.search_similar("text")

        assert results[0]["similarity"] == pytest.approx(1.0)


class TestFindMirrorPhrase:
    """
    Poka-Yoke coverage for the double guard in find_mirror_phrase:
      Guard 1 — similarity >= mirror_similarity_threshold (default 0.85)
      Guard 2 — entry age   >= mirror_min_age_days         (default 7)
    """

    def _patch_search(self, results, vector_store_module):
        return patch.object(vector_store_module, "search_similar", return_value=results)

    def test_returns_none_when_no_candidates(self):
        from app.services import vector_store

        with self._patch_search([], vector_store):
            result = vector_store.find_mirror_phrase("I feel sad today.")

        assert result is None

    def test_returns_none_when_entry_too_recent(self):
        from app.services import vector_store

        recent_ts = _days_ago(3).timestamp()
        candidates = [
            {
                "id": "e1",
                "text": "I feel invisible at work.",
                "similarity": 0.92,
                "metadata": {"timestamp": recent_ts},
            }
        ]

        with self._patch_search(candidates, vector_store):
            result = vector_store.find_mirror_phrase("I feel unseen at work.")

        assert result is None

    def test_returns_phrase_when_both_guards_pass(self):
        from app.services import vector_store

        old_ts = _days_ago(14).timestamp()
        candidates = [
            {
                "id": "e1",
                "text": "I feel invisible at work.",
                "similarity": 0.90,
                "metadata": {"timestamp": old_ts},
            }
        ]

        with self._patch_search(candidates, vector_store):
            result = vector_store.find_mirror_phrase("Nobody notices me at work.")

        assert result == "I feel invisible at work."

    def test_returns_best_match_skipping_recent_ones(self):
        from app.services import vector_store

        recent_ts = _days_ago(2).timestamp()
        old_ts = _days_ago(10).timestamp()

        candidates = [
            {
                "id": "e1",
                "text": "Best match but too recent.",
                "similarity": 0.95,
                "metadata": {"timestamp": recent_ts},
            },
            {
                "id": "e2",
                "text": "Older good match.",
                "similarity": 0.88,
                "metadata": {"timestamp": old_ts},
            },
        ]

        with self._patch_search(candidates, vector_store):
            result = vector_store.find_mirror_phrase("something similar")

        assert result == "Older good match."

    def test_returns_none_when_all_candidates_too_recent(self):
        from app.services import vector_store

        ts = _days_ago(1).timestamp()
        candidates = [
            {
                "id": f"e{i}",
                "text": f"entry {i}",
                "similarity": 0.9,
                "metadata": {"timestamp": ts},
            }
            for i in range(5)
        ]

        with self._patch_search(candidates, vector_store):
            result = vector_store.find_mirror_phrase("query")

        assert result is None
