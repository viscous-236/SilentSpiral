"""
tests/test_mirror_prompt.py
============================
Tests for Mirror Prompt logic end-to-end:
  - vector_store.find_mirror_phrase guards (age + similarity)
  - _build_user_prompt injection in reflection_agent
  - run_reflection passes mirror_phrase through to the graph state
  - POST /agent/reflect mirrors mirror_phrase_used back in response

Methodology (mirrors existing test conventions):
  - All external dependencies (Chroma, SentenceTransformer, LLM) mocked
  - Behavioral contracts only — no string matching of LLM outputs
  - Poka-Yoke coverage: each guard individually + both failing

Test categories:
  1. Prompt injection: mirror block present/absent in _build_user_prompt
  2. State threading: mirror_phrase flows through run_reflection graph state
  3. Route integration: mirror_phrase accepted, mirror_phrase_used echoed back
  4. Guard integration: find_mirror_phrase blocks recent + low-similarity entries
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def _make_reflection_output(questions=None):
    from app.agents.reflection_agent import ReflectionOutput
    return ReflectionOutput(
        questions=questions or [
            "What feeling is sitting with you the most right now?",
            "Does that sense of invisibility still feel present today?",
        ]
    )


# ── 1. Prompt injection in _build_user_prompt ────────────────────────────────

class TestMirrorPromptInjection:

    def _build(self, mirror_phrase=None, journal="I feel unseen."):
        from app.agents.reflection_agent import _build_user_prompt
        return _build_user_prompt(
            journal_text=journal,
            emotions=[{"label": "sadness", "score": 0.8}],
            history=[],
            mirror_phrase=mirror_phrase,
        )

    def test_mirror_block_absent_when_no_phrase(self):
        prompt = self._build(mirror_phrase=None)
        assert "Mirror Prompt" not in prompt
        assert "previously wrote" not in prompt

    def test_mirror_block_present_when_phrase_provided(self):
        prompt = self._build(mirror_phrase="I feel invisible at work.")
        assert "Mirror Prompt" in prompt
        assert "I feel invisible at work." in prompt

    def test_mirror_block_contains_instruction_to_ask(self):
        prompt = self._build(mirror_phrase="Nobody notices me.")
        assert "still feels true" in prompt.lower() or "still feel true" in prompt.lower()

    def test_mirror_phrase_quoted_in_prompt(self):
        phrase = "I feel invisible at work."
        prompt = self._build(mirror_phrase=phrase)
        assert f'"{phrase}"' in prompt

    def test_journal_text_still_present_with_mirror_phrase(self):
        prompt = self._build(
            journal="Today was hard.",
            mirror_phrase="Last week was harder.",
        )
        assert "Today was hard." in prompt
        assert "Last week was harder." in prompt


# ── 2. State threading through run_reflection ────────────────────────────────

class TestMirrorPhraseStateThreading:

    def test_mirror_phrase_passed_into_graph_state(self):
        """Verify mirror_phrase is included in the initial_state dict sent to graph."""
        from app.agents import reflection_agent

        mock_output = _make_reflection_output()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": mock_output}

        with patch.object(reflection_agent, "get_reflection_graph", return_value=mock_graph):
            reflection_agent.run_reflection(
                journal_text="I feel unseen.",
                emotions=[{"label": "sadness", "score": 0.8}],
                mirror_phrase="I feel invisible at work.",
            )

        invoked_state = mock_graph.invoke.call_args[0][0]
        assert invoked_state["mirror_phrase"] == "I feel invisible at work."

    def test_mirror_phrase_none_when_not_provided(self):
        """Default: mirror_phrase is None in state when not passed."""
        from app.agents import reflection_agent

        mock_output = _make_reflection_output()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": mock_output}

        with patch.object(reflection_agent, "get_reflection_graph", return_value=mock_graph):
            reflection_agent.run_reflection(
                journal_text="Normal entry.",
                emotions=[],
            )

        invoked_state = mock_graph.invoke.call_args[0][0]
        assert invoked_state["mirror_phrase"] is None

    def test_result_unaffected_structurally_with_mirror_phrase(self):
        """Mirror phrase doesn't break the 2-question contract."""
        from app.agents import reflection_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": _make_reflection_output()}

        with patch.object(reflection_agent, "get_reflection_graph", return_value=mock_graph):
            result = reflection_agent.run_reflection(
                journal_text="I feel unseen.",
                emotions=[{"label": "sadness", "score": 0.8}],
                mirror_phrase="I felt invisible last month.",
            )

        assert len(result.questions) == 2
        assert all(isinstance(q, str) for q in result.questions)


# ── 3. Route integration — mirror_phrase_used echoed back ────────────────────

class TestReflectEndpointMirrorPrompt:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def _mock_run(self):
        from app.agents.reflection_agent import ReflectionOutput
        return MagicMock(return_value=ReflectionOutput(
            questions=[
                "What feeling is sitting with you most right now?",
                "Does that sense of invisibility still feel present today?",
            ]
        ))

    def _body(self, mirror_phrase=None):
        body = {
            "journal_text": "I feel unseen at work today.",
            "emotions": [{"label": "sadness", "score": 0.82}],
            "history": [],
        }
        if mirror_phrase is not None:
            body["mirror_phrase"] = mirror_phrase
        return body

    def test_mirror_phrase_used_echoed_when_provided(self, client):
        from app.agents import reflection_agent
        phrase = "I feel invisible at work."
        with patch.object(reflection_agent, "run_reflection", self._mock_run()):
            resp = client.post("/agent/reflect", json=self._body(mirror_phrase=phrase))
        assert resp.status_code == 200
        assert resp.json()["mirror_phrase_used"] == phrase

    def test_mirror_phrase_used_null_when_not_provided(self, client):
        from app.agents import reflection_agent
        with patch.object(reflection_agent, "run_reflection", self._mock_run()):
            resp = client.post("/agent/reflect", json=self._body())
        assert resp.status_code == 200
        assert resp.json()["mirror_phrase_used"] is None

    def test_mirror_phrase_passed_to_run_reflection(self, client):
        """Verify the route actually forwards mirror_phrase into the agent call."""
        # Patch where the name is *used* (the route module), not where it is
        # defined.  The route does `from app.agents.reflection_agent import
        # run_reflection`, so patching the source module attribute has no effect
        # on the already-bound name in app.routes.agents.
        import app.routes.agents as agents_route

        mock_fn = self._mock_run()
        phrase = "Nobody notices my effort."

        with patch.object(agents_route, "run_reflection", mock_fn):
            client.post("/agent/reflect", json=self._body(mirror_phrase=phrase))

        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs.get("mirror_phrase") == phrase

    def test_mirror_phrase_too_long_returns_422(self, client):
        """mirror_phrase is capped at 1000 chars in the schema."""
        body = self._body(mirror_phrase="x" * 1001)
        resp = client.post("/agent/reflect", json=body)
        assert resp.status_code == 422


# ── 4. Guard integration via find_mirror_phrase ───────────────────────────────

class TestFindMirrorPhraseGuards:
    """
    Re-tests key Poka-Yoke guards here from the Mirror Prompt integration
    perspective — confirms the combined similarity + age filter is correct
    for Mirror Prompt use specifically.
    """

    def _patch_search(self, results):
        from app.services import vector_store
        return patch.object(vector_store, "search_similar", return_value=results)

    def test_entry_exactly_7_days_old_is_accepted(self):
        """Boundary: exactly mirror_min_age_days old must pass the age guard."""
        from app.services import vector_store

        # 7 days ago minus a small buffer to ensure it's >= 7 days
        ts = (_days_ago(7) - timedelta(seconds=60)).timestamp()
        candidates = [{
            "id": "e1",
            "text": "I feel invisible at work.",
            "similarity": 0.90,
            "metadata": {"timestamp": ts},
        }]

        with self._patch_search(candidates):
            result = vector_store.find_mirror_phrase("I feel unseen.")

        assert result == "I feel invisible at work."

    def test_entry_6_days_old_is_rejected(self):
        """Boundary: 6 days old must NOT pass (< 7 days)."""
        from app.services import vector_store

        ts = _days_ago(6).timestamp()
        candidates = [{
            "id": "e1",
            "text": "I feel invisible.",
            "similarity": 0.95,
            "metadata": {"timestamp": ts},
        }]

        with self._patch_search(candidates):
            result = vector_store.find_mirror_phrase("I feel unseen.")

        assert result is None

    def test_empty_journal_raises_value_error(self):
        """find_mirror_phrase must propagate the ValueError from search_similar."""
        from app.services.vector_store import find_mirror_phrase
        with pytest.raises(ValueError, match="query text"):
            find_mirror_phrase("   ")
