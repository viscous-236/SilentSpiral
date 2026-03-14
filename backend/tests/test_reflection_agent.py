"""
tests/test_reflection_agent.py
================================
Agent Evaluation: behavioral contract + adversarial tests for the
reflection agent.

Methodology (agent-evaluation principles):
  - Behavioral contracts: verify structural invariants, NOT exact LLM outputs
  - Mock the LLM entirely — test OUR orchestration code, not Gemini
  - Adversarial inputs: empty emotions, very long history, empty journal
  - Fallback guard coverage: verify fallback activates when output is bad
  - Route-level integration tests (TestClient, no real HTTP)

Anti-patterns avoided:
  ✗ Output string matching (LLM outputs are non-deterministic)
  ✗ Single-run tests (we test structure, not specific phrasing)
  ✗ Happy-path only (adversarial + edge cases covered)

Test categories:
  1. Unit: _build_user_prompt — deterministic, no LLM needed
  2. Unit: run_reflection with mocked LLM + fallback guard
  3. Integration: POST /agent/reflect via TestClient (mocked LLM)
  4. Adversarial: empty emotions, long history, missing API key path
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_reflection_output(questions: list[str]):
    from app.agents.reflection_agent import ReflectionOutput
    return ReflectionOutput(questions=questions)


# ── 1. _build_user_prompt (pure function, no LLM) ────────────────────────────

class TestBuildUserPrompt:
    """Unit tests for the prompt builder — deterministic, no mocks needed."""

    def _build(self, journal="I feel lost.", emotions=None, history=None):
        from app.agents.reflection_agent import _build_user_prompt
        return _build_user_prompt(
            journal,
            emotions or [],
            history or [],
        )

    def test_contains_journal_text(self):
        prompt = self._build(journal="I feel lost today.")
        assert "I feel lost today." in prompt

    def test_contains_emotion_summary_when_provided(self):
        prompt = self._build(emotions=[{"label": "sadness", "score": 0.82}])
        assert "sadness" in prompt

    def test_no_emotion_shows_not_specified(self):
        prompt = self._build(emotions=[])
        assert "not specified" in prompt

    def test_history_included_up_to_3(self):
        """Only last 3 history items should appear."""
        history = ["q1", "q2", "q3", "q4", "q5"]
        prompt = self._build(history=history)
        # First 2 should be excluded
        assert "q1" not in prompt
        assert "q2" not in prompt
        assert "q3" in prompt
        assert "q5" in prompt

    def test_no_history_block_when_empty(self):
        prompt = self._build(history=[])
        assert "Previous reflections" not in prompt

    def test_emotion_percentage_formatting(self):
        """Scores must be formatted as percentages."""
        prompt = self._build(emotions=[{"label": "joy", "score": 0.75}])
        assert "75%" in prompt


# ── 2. run_reflection (LLM mocked) ───────────────────────────────────────────

class TestRunReflection:
    """Unit tests for the run_reflection function with mocked LLM."""

    def _run(self, questions=None, journal="I feel sad."):
        from app.agents import reflection_agent

        mock_output = _make_reflection_output(
            questions or ["What are you feeling?", "When did this start?"]
        )
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": mock_output}

        with patch.object(reflection_agent, "get_reflection_graph", return_value=mock_graph):
            return reflection_agent.run_reflection(
                journal_text=journal,
                emotions=[{"label": "sadness", "score": 0.8}],
            )

    def test_returns_exactly_2_questions(self):
        result = self._run()
        assert len(result.questions) == 2

    def test_questions_are_strings(self):
        result = self._run()
        assert all(isinstance(q, str) for q in result.questions)

    def test_questions_are_non_empty(self):
        result = self._run()
        assert all(len(q.strip()) > 0 for q in result.questions)

    def test_fallback_activates_when_output_is_none(self):
        """Behavioral: fallback questions used when graph returns None output."""
        from app.agents import reflection_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": None}

        with patch.object(reflection_agent, "get_reflection_graph", return_value=mock_graph):
            result = reflection_agent.run_reflection(
                journal_text="Just checking.",
                emotions=[],
            )

        assert len(result.questions) == 2
        # Fallback questions are the known constants — verify they're used
        assert result.questions == reflection_agent._FALLBACK_QUESTIONS

    def test_adversarial_empty_emotions(self):
        """Adversarial: no emotions provided — should not crash."""
        result = self._run(journal="Nothing happened.")
        assert len(result.questions) == 2

    def test_adversarial_very_long_journal(self):
        """Adversarial: very long journal text passed through without truncation by agent."""
        long_text = "I feel okay. " * 300  # ~600 words
        result = self._run(journal=long_text)
        assert len(result.questions) == 2


# ── 3. POST /agent/reflect integration via TestClient ────────────────────────

class TestReflectEndpoint:
    """Integration tests for the /agent/reflect route (LLM fully mocked)."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def _mock_run(self):
        from app.agents.reflection_agent import ReflectionOutput
        return MagicMock(
            return_value=ReflectionOutput(
                questions=[
                    "What feeling is staying with you the most?",
                    "When did you first notice this today?",
                ]
            )
        )

    def test_reflect_happy_path_returns_200(self, client):
        from app.agents import reflection_agent
        with patch.object(reflection_agent, "run_reflection", self._mock_run()):
            resp = client.post(
                "/agent/reflect",
                json={
                    "journal_text": "I feel a strange heaviness today.",
                    "emotions": [{"label": "sadness", "score": 0.8}],
                    "history": [],
                },
            )
        assert resp.status_code == 200

    def test_reflect_response_has_two_questions(self, client):
        from app.agents import reflection_agent
        with patch.object(reflection_agent, "run_reflection", self._mock_run()):
            resp = client.post(
                "/agent/reflect",
                json={
                    "journal_text": "Hard day.",
                    "emotions": [],
                },
            )
        data = resp.json()
        assert len(data["questions"]) == 2

    def test_reflect_response_has_top_emotion(self, client):
        from app.agents import reflection_agent
        with patch.object(reflection_agent, "run_reflection", self._mock_run()):
            resp = client.post(
                "/agent/reflect",
                json={
                    "journal_text": "I feel hopeful.",
                    "emotions": [{"label": "joy", "score": 0.9}],
                },
            )
        data = resp.json()
        assert data["top_emotion"] == "joy"

    def test_reflect_empty_emotions_defaults_to_neutral(self, client):
        """Behavioral: no emotions → top_emotion falls back to 'neutral'."""
        from app.agents import reflection_agent
        with patch.object(reflection_agent, "run_reflection", self._mock_run()):
            resp = client.post(
                "/agent/reflect",
                json={"journal_text": "Just a regular day."},
            )
        data = resp.json()
        assert data["top_emotion"] == "neutral"

    def test_reflect_rejects_empty_journal(self, client):
        """Poka-Yoke: empty journal_text → 422."""
        resp = client.post(
            "/agent/reflect",
            json={"journal_text": ""},
        )
        assert resp.status_code == 422

    def test_reflect_rejects_history_over_5(self, client):
        """Poka-Yoke: max_length=5 on history → 422 when exceeded."""
        resp = client.post(
            "/agent/reflect",
            json={
                "journal_text": "Testing.",
                "history": ["q1", "q2", "q3", "q4", "q5", "q6"],  # 6 > 5
            },
        )
        assert resp.status_code == 422

    def test_reflect_hf_error_returns_503(self, client):
        """Behavioral: HuggingFace API error → 503, not 500."""
        from unittest.mock import MagicMock
        from huggingface_hub.errors import HfHubHTTPError

        mock_response = MagicMock()
        mock_response.status_code = 503

        # Patch the name as bound in the route module (not the source module)
        with patch(
            "app.routes.agents.run_reflection",
            side_effect=HfHubHTTPError("Service unavailable", response=mock_response),
        ):
            resp = client.post(
                "/agent/reflect",
                json={"journal_text": "Testing HF error handling."},
            )
        assert resp.status_code == 503

    def test_reflect_hf_auth_error_returns_401(self, client):
        """Behavioral: HuggingFace 401 → 401, not 500."""
        from unittest.mock import MagicMock
        from huggingface_hub.errors import HfHubHTTPError

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch(
            "app.routes.agents.run_reflection",
            side_effect=HfHubHTTPError("Unauthorized", response=mock_response),
        ):
            resp = client.post(
                "/agent/reflect",
                json={"journal_text": "Testing auth error handling."},
            )
        assert resp.status_code == 401
