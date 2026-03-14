"""
tests/test_coach_agent.py
==========================
Agent evaluation tests for agents/coach_agent.py

Methodology (mirrors test_reflection_agent.py conventions):
  - LLM mocked entirely — test OUR orchestration code, not the model
  - Behavioral contracts: verify structural invariants (suggestion count, framing)
  - Short-circuit guard coverage: anomaly_flag=None → empty output, no LLM call
  - Fallback guard coverage: None output → anomaly-specific fallback fires
  - Route-level integration tests via TestClient (mocked run_coach)

Test categories:
  1. Unit: _build_user_prompt — deterministic, no LLM
  2. Unit: run_coach short-circuit (no anomaly → empty, no LLM invoked)
  3. Unit: run_coach with mocked graph (all 3 anomaly types)
  4. Unit: fallback guard fires on None output
  5. Integration: POST /agent/coach via TestClient
"""

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_coach_output(suggestions=None, challenge="Tomorrow: write one sentence before checking your phone."):
    from app.agents.coach_agent import CoachOutput
    return CoachOutput(
        suggestions=suggestions or [
            "You might try writing just one sentence about something small that felt okay today.",
        ],
        challenge=challenge,
    )


# ── 1. _build_user_prompt (pure function) ────────────────────────────────────

class TestBuildUserPrompt:

    def _build(self, anomaly="DOWNWARD_SPIRAL", insight="You've been feeling heavy.", prefs=None):
        from app.agents.coach_agent import _build_user_prompt
        return _build_user_prompt(insight, anomaly, prefs or {})

    def test_contains_pattern_insight(self):
        prompt = self._build(insight="Sadness has been dominant.")
        assert "Sadness has been dominant." in prompt

    def test_anomaly_rendered_human_readable_downward(self):
        prompt = self._build(anomaly="DOWNWARD_SPIRAL")
        assert "downward" in prompt.lower()

    def test_anomaly_rendered_human_readable_volatility(self):
        prompt = self._build(anomaly="HIGH_VOLATILITY")
        assert "volatility" in prompt.lower()

    def test_anomaly_rendered_human_readable_engagement(self):
        prompt = self._build(anomaly="LOW_ENGAGEMENT")
        assert "engagement" in prompt.lower()

    def test_user_preferences_included_when_provided(self):
        prompt = self._build(prefs={"pace": "slow", "interest": "walking"})
        assert "pace" in prompt
        assert "walking" in prompt

    def test_no_prefs_block_when_empty(self):
        prompt = self._build(prefs={})
        assert "preferences" not in prompt.lower()


# ── 2. Short-circuit guard — no anomaly ──────────────────────────────────────

class TestRunCoachShortCircuit:
    """
    When anomaly_flag is None, run_coach must:
      - Return CoachOutput(suggestions=[], challenge="")
      - NOT invoke the LangGraph graph at all
    """

    def test_returns_empty_output_when_no_anomaly(self):
        from app.agents import coach_agent

        mock_graph = MagicMock()
        with patch.object(coach_agent, "get_coach_graph", return_value=mock_graph):
            result = coach_agent.run_coach(
                pattern_insight="Everything looks fine.",
                anomaly_flag=None,
            )

        assert result.suggestions == []
        assert result.challenge == ""

    def test_graph_never_invoked_when_no_anomaly(self):
        from app.agents import coach_agent

        mock_graph = MagicMock()
        with patch.object(coach_agent, "get_coach_graph", return_value=mock_graph):
            coach_agent.run_coach(
                pattern_insight="Everything fine.",
                anomaly_flag=None,
            )

        mock_graph.invoke.assert_not_called()


# ── 3. run_coach with mocked graph ───────────────────────────────────────────

class TestRunCoach:

    def _run(self, anomaly="DOWNWARD_SPIRAL", output=None):
        from app.agents import coach_agent

        mock_output = output or _make_coach_output()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": mock_output}

        with patch.object(coach_agent, "get_coach_graph", return_value=mock_graph):
            return coach_agent.run_coach(
                pattern_insight="Sadness has been the dominant pattern.",
                anomaly_flag=anomaly,
            )

    def test_returns_1_or_2_suggestions(self):
        result = self._run()
        assert 1 <= len(result.suggestions) <= 2

    def test_suggestions_are_strings(self):
        result = self._run()
        assert all(isinstance(s, str) for s in result.suggestions)

    def test_challenge_is_non_empty_string(self):
        result = self._run()
        assert isinstance(result.challenge, str)
        assert len(result.challenge.strip()) > 0

    def test_works_for_all_anomaly_types(self):
        for anomaly in ("DOWNWARD_SPIRAL", "HIGH_VOLATILITY", "LOW_ENGAGEMENT"):
            result = self._run(anomaly=anomaly)
            assert 1 <= len(result.suggestions) <= 2

    def test_fallback_fires_when_output_is_none(self):
        from app.agents import coach_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": None}

        with patch.object(coach_agent, "get_coach_graph", return_value=mock_graph):
            result = coach_agent.run_coach(
                pattern_insight="Heavy week.",
                anomaly_flag="DOWNWARD_SPIRAL",
            )

        expected = coach_agent._FALLBACK_BY_ANOMALY["DOWNWARD_SPIRAL"]
        assert result.suggestions == expected["suggestions"]
        assert result.challenge == expected["challenge"]

    def test_fallback_is_anomaly_specific(self):
        """Each anomaly type gets its own tailored fallback, not a generic one."""
        from app.agents import coach_agent

        for anomaly in ("DOWNWARD_SPIRAL", "HIGH_VOLATILITY", "LOW_ENGAGEMENT"):
            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {"output": None}

            with patch.object(coach_agent, "get_coach_graph", return_value=mock_graph):
                result = coach_agent.run_coach(
                    pattern_insight="Some pattern.",
                    anomaly_flag=anomaly,
                )

            expected = coach_agent._FALLBACK_BY_ANOMALY[anomaly]
            assert result.suggestions == expected["suggestions"]


# ── 4. POST /agent/coach integration via TestClient ──────────────────────────

class TestCoachEndpoint:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def _valid_body(self, anomaly="DOWNWARD_SPIRAL"):
        return {
            "pattern_insight": "You've been feeling heavy for the past week.",
            "anomaly_flag": anomaly,
            "user_preferences": {},
        }

    def _mock_run(self, suggestions=None, challenge="Tomorrow: try one small thing.", triggered=True):
        return MagicMock(return_value=_make_coach_output(
            suggestions=suggestions or ["You might try stepping outside for five minutes."],
            challenge=challenge,
        ))

    def test_returns_200_with_anomaly(self, client):
        from app.agents import coach_agent
        with patch.object(coach_agent, "run_coach", self._mock_run()):
            resp = client.post("/agent/coach", json=self._valid_body())
        assert resp.status_code == 200

    def test_response_has_correct_fields(self, client):
        from app.agents import coach_agent
        with patch.object(coach_agent, "run_coach", self._mock_run()):
            resp = client.post("/agent/coach", json=self._valid_body())
        data = resp.json()
        assert "suggestions" in data
        assert "challenge" in data
        assert "triggered" in data

    def test_triggered_true_when_anomaly_present(self, client):
        from app.agents import coach_agent
        with patch.object(coach_agent, "run_coach", self._mock_run()):
            resp = client.post("/agent/coach", json=self._valid_body(anomaly="HIGH_VOLATILITY"))
        assert resp.json()["triggered"] is True

    def test_triggered_false_when_no_anomaly(self, client):
        from app.agents import coach_agent
        with patch.object(coach_agent, "run_coach", self._mock_run()):
            resp = client.post("/agent/coach", json=self._valid_body(anomaly=None))
        assert resp.json()["triggered"] is False

    def test_missing_pattern_insight_returns_422(self, client):
        resp = client.post("/agent/coach", json={"anomaly_flag": "DOWNWARD_SPIRAL"})
        assert resp.status_code == 422

    def test_invalid_anomaly_flag_returns_422(self, client):
        body = self._valid_body()
        body["anomaly_flag"] = "MADE_UP_FLAG"
        resp = client.post("/agent/coach", json=body)
        assert resp.status_code == 422
