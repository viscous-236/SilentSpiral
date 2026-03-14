"""
tests/test_pattern_agent.py
============================
Agent evaluation tests for agents/pattern_agent.py

Methodology (mirrors test_reflection_agent.py conventions):
  - LLM mocked entirely — test OUR orchestration code, not the model
  - Behavioral contracts: verify structural invariants (insight count, types)
  - Fallback guard coverage: None output, wrong insight count → fallback fires
  - Route-level integration tests via TestClient (LLM mocked)
  - Adversarial: missing anomaly flag, empty history, boundary insight counts

Test categories:
  1. Unit: _build_user_prompt — deterministic, no LLM
  2. Unit: run_pattern with mocked graph
  3. Unit: fallback guard — fires when insight count out of 3-5 range
  4. Integration: POST /agent/pattern via TestClient (mocked run_pattern)
"""

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_window_stats(
    dominant="sadness",
    avg_scores=None,
    volatility=0.25,
    entry_count=5,
):
    from app.services.pattern_engine import WindowStats
    return WindowStats(
        dominant_emotion=dominant,
        avg_scores=avg_scores or {"sadness": 0.7, "joy": 0.1},
        volatility_score=volatility,
        entry_count=entry_count,
    )


def _make_pattern_output(insights=None, highlight="Your week shows a heavy emotional tone."):
    from app.agents.pattern_agent import PatternOutput
    return PatternOutput(
        insights=insights or [
            "You've been feeling more weighed down lately.",
            "Sadness has been the most present emotion across your entries.",
            "Your emotional intensity has stayed relatively stable.",
        ],
        highlight=highlight,
    )


# ── 1. _build_user_prompt (pure function) ────────────────────────────────────

class TestBuildUserPrompt:

    def _build(self, anomaly=None, history="", dominant="sadness"):
        from app.agents.pattern_agent import _build_user_prompt
        stats = _make_window_stats(dominant=dominant)
        return _build_user_prompt(stats.model_dump(), anomaly, history)

    def test_contains_dominant_emotion(self):
        prompt = self._build(dominant="anger")
        assert "anger" in prompt

    def test_contains_entry_count(self):
        prompt = self._build()
        assert "5" in prompt

    def test_anomaly_rendered_as_human_text_downward_spiral(self):
        prompt = self._build(anomaly="DOWNWARD_SPIRAL")
        assert "downward" in prompt.lower()

    def test_anomaly_rendered_as_human_text_high_volatility(self):
        prompt = self._build(anomaly="HIGH_VOLATILITY")
        assert "volatility" in prompt.lower()

    def test_anomaly_rendered_as_human_text_low_engagement(self):
        prompt = self._build(anomaly="LOW_ENGAGEMENT")
        assert "engagement" in prompt.lower()

    def test_no_anomaly_shows_none_detected(self):
        prompt = self._build(anomaly=None)
        assert "no significant anomaly" in prompt.lower()

    def test_history_included_when_provided(self):
        prompt = self._build(history="Last week showed calm patterns.")
        assert "Last week showed calm patterns." in prompt

    def test_no_history_block_when_empty(self):
        prompt = self._build(history="")
        assert "Previous pattern summary" not in prompt


# ── 2. run_pattern with mocked graph ─────────────────────────────────────────

class TestRunPattern:

    def _run(self, output=None, anomaly="DOWNWARD_SPIRAL"):
        from app.agents import pattern_agent

        mock_output = output or _make_pattern_output()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": mock_output}

        with patch.object(pattern_agent, "get_pattern_graph", return_value=mock_graph):
            return pattern_agent.run_pattern(
                window_stats=_make_window_stats(),
                anomaly_flag=anomaly,
            )

    def test_returns_3_to_5_insights(self):
        result = self._run()
        assert 3 <= len(result.insights) <= 5

    def test_insights_are_strings(self):
        result = self._run()
        assert all(isinstance(s, str) for s in result.insights)

    def test_insights_are_non_empty(self):
        result = self._run()
        assert all(len(s.strip()) > 0 for s in result.insights)

    def test_highlight_is_non_empty_string(self):
        result = self._run()
        assert isinstance(result.highlight, str)
        assert len(result.highlight.strip()) > 0

    def test_no_anomaly_flag_still_runs(self):
        """Pattern agent must run even when anomaly_flag is None."""
        result = self._run(anomaly=None)
        assert 3 <= len(result.insights) <= 5

    def test_fallback_fires_when_output_is_none(self):
        from app.agents import pattern_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": None}

        with patch.object(pattern_agent, "get_pattern_graph", return_value=mock_graph):
            result = pattern_agent.run_pattern(
                window_stats=_make_window_stats(),
                anomaly_flag="DOWNWARD_SPIRAL",
            )

        assert result.insights == pattern_agent._FALLBACK_INSIGHTS
        assert result.highlight == pattern_agent._FALLBACK_HIGHLIGHT

    def test_fallback_fires_when_insight_count_too_low(self):
        from app.agents import pattern_agent

        # Use MagicMock to bypass Pydantic validation — we intentionally want
        # an object whose .insights list violates min_length=3 to test the guard.
        bad_output = MagicMock()
        bad_output.insights = ["Only one sentence."]  # 1 < min_length=3
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": bad_output}

        with patch.object(pattern_agent, "get_pattern_graph", return_value=mock_graph):
            result = pattern_agent.run_pattern(
                window_stats=_make_window_stats(),
                anomaly_flag=None,
            )

        assert result.insights == pattern_agent._FALLBACK_INSIGHTS

    def test_fallback_fires_when_insight_count_too_high(self):
        from app.agents import pattern_agent

        # Use MagicMock to bypass Pydantic validation — we intentionally want
        # an object whose .insights list violates max_length=5 to test the guard.
        bad_output = MagicMock()
        bad_output.insights = [f"Sentence {i}." for i in range(6)]  # 6 > max_length=5
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"output": bad_output}

        with patch.object(pattern_agent, "get_pattern_graph", return_value=mock_graph):
            result = pattern_agent.run_pattern(
                window_stats=_make_window_stats(),
                anomaly_flag=None,
            )

        assert result.insights == pattern_agent._FALLBACK_INSIGHTS


# ── 3. POST /agent/pattern integration via TestClient ────────────────────────

class TestPatternEndpoint:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def _valid_body(self, anomaly="DOWNWARD_SPIRAL"):
        return {
            "window_stats": {
                "dominant_emotion": "sadness",
                "avg_scores": {"sadness": 0.7, "joy": 0.1},
                "volatility_score": 0.25,
                "entry_count": 5,
            },
            "anomaly_flag": anomaly,
            "history_summary": "",
        }

    def _mock_run(self):
        return MagicMock(return_value=_make_pattern_output())

    def test_returns_200_with_valid_body(self, client):
        from app.agents import pattern_agent
        with patch.object(pattern_agent, "run_pattern", self._mock_run()):
            resp = client.post("/agent/pattern", json=self._valid_body())
        assert resp.status_code == 200

    def test_response_has_insights_and_highlight(self, client):
        from app.agents import pattern_agent
        with patch.object(pattern_agent, "run_pattern", self._mock_run()):
            resp = client.post("/agent/pattern", json=self._valid_body())
        data = resp.json()
        assert "insights" in data
        assert "highlight" in data
        assert "dominant_emotion" in data

    def test_dominant_emotion_echoed_from_request(self, client):
        from app.agents import pattern_agent
        with patch.object(pattern_agent, "run_pattern", self._mock_run()):
            resp = client.post("/agent/pattern", json=self._valid_body())
        assert resp.json()["dominant_emotion"] == "sadness"

    def test_no_anomaly_flag_returns_200(self, client):
        from app.agents import pattern_agent
        body = self._valid_body(anomaly=None)
        with patch.object(pattern_agent, "run_pattern", self._mock_run()):
            resp = client.post("/agent/pattern", json=body)
        assert resp.status_code == 200

    def test_missing_window_stats_returns_422(self, client):
        resp = client.post("/agent/pattern", json={"anomaly_flag": "DOWNWARD_SPIRAL"})
        assert resp.status_code == 422

    def test_invalid_anomaly_flag_returns_422(self, client):
        body = self._valid_body()
        body["anomaly_flag"] = "NOT_A_REAL_FLAG"
        resp = client.post("/agent/pattern", json=body)
        assert resp.status_code == 422

    def test_entry_count_zero_returns_422(self, client):
        body = self._valid_body()
        body["window_stats"]["entry_count"] = 0  # ge=1 constraint
        resp = client.post("/agent/pattern", json=body)
        assert resp.status_code == 422
