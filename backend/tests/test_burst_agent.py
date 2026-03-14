"""
tests/test_burst_agent.py
==========================
Behavioral contract + adversarial tests for the Burst Session agents.

Methodology (mirrors test_reflection_agent.py conventions):
  - Mock the LLM entirely — test OUR orchestration code, not Groq's responses
  - Behavioral contracts: verify structural invariants, NOT exact LLM outputs
  - Cover normal, edge-case, and API-failure paths
  - Route-level integration (TestClient) with mocked agent functions

Test categories:
  1. Unit: run_burst_ack — structural invariants
  2. Unit: run_burst_ack — fallback on API failure
  3. Unit: run_burst_close — structural invariants
  4. Unit: run_burst_close — fallback on API failure
  5. Integration: POST /agent/burst/ack via TestClient
  6. Integration: POST /agent/burst/close via TestClient
"""

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

_SAMPLE_PARTIAL = "I'm so tired of pretending everything is okay."
_SAMPLE_SESSION = (
    "I've been holding this in for weeks. Work is overwhelming. "
    "I feel invisible. I'm exhausted but I can't stop."
)


# ── 1. run_burst_ack — structural invariants ──────────────────────────────────

class TestRunBurstAck:
    """Unit tests for run_burst_ack with mocked LangGraph graph."""

    def _run(self, partial=_SAMPLE_PARTIAL, elapsed=40, ack_return="I hear you."):
        from app.agents import burst_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"acknowledgment": ack_return}

        with patch.object(burst_agent, "_get_ack_graph", return_value=mock_graph):
            return burst_agent.run_burst_ack(
                partial_text=partial,
                elapsed_seconds=elapsed,
            )

    def test_returns_string(self):
        result = self._run()
        assert isinstance(result, str)

    def test_returns_non_empty(self):
        result = self._run()
        assert len(result.strip()) > 0

    def test_elapsed_zero_allowed(self):
        """Edge case: session just started."""
        result = self._run(elapsed=0)
        assert isinstance(result, str)

    def test_elapsed_max_allowed(self):
        """Edge case: very end of session."""
        result = self._run(elapsed=300)
        assert isinstance(result, str)

    def test_uses_returned_acknowledgment(self):
        result = self._run(ack_return="You're safe here.")
        assert result == "You're safe here."


# ── 2. run_burst_ack — fallback on API failure ────────────────────────────────

class TestRunBurstAckFallback:
    """Behavioral: fallback is used when graph fails or returns empty."""

    def test_fallback_when_graph_returns_empty_string(self):
        from app.agents import burst_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"acknowledgment": ""}

        with patch.object(burst_agent, "_get_ack_graph", return_value=mock_graph):
            result = burst_agent.run_burst_ack("test", 30)

        # Empty string → fallback constant
        assert result == burst_agent._FALLBACK_ACK

    def test_fallback_when_acknowledgment_key_missing(self):
        from app.agents import burst_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {}  # Missing key

        with patch.object(burst_agent, "_get_ack_graph", return_value=mock_graph):
            result = burst_agent.run_burst_ack("test", 30)

        assert result == burst_agent._FALLBACK_ACK

    def test_ack_node_fallback_on_groq_exception(self):
        """Unit: ack_node catches Exception and returns fallback dict."""
        from app.agents.burst_agent import ack_node, AckState, _FALLBACK_ACK

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Groq down")

        with patch("app.agents.burst_agent._get_client", return_value=mock_client):
            result = ack_node({
                "partial_text": "I feel awful.",
                "elapsed_seconds": 60,
                "acknowledgment": "",
            })

        assert result["acknowledgment"] == _FALLBACK_ACK


# ── 3. run_burst_close — structural invariants ────────────────────────────────

class TestRunBurstClose:
    """Unit tests for run_burst_close with mocked LangGraph graph."""

    def _run(self, session=_SAMPLE_SESSION, close_return="You showed up for yourself."):
        from app.agents import burst_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"closing_message": close_return}

        with patch.object(burst_agent, "_get_close_graph", return_value=mock_graph):
            return burst_agent.run_burst_close(session_text=session)

    def test_returns_string(self):
        result = self._run()
        assert isinstance(result, str)

    def test_returns_non_empty(self):
        result = self._run()
        assert len(result.strip()) > 0

    def test_uses_returned_closing_message(self):
        expected = "That took real honesty. Rest now."
        result = self._run(close_return=expected)
        assert result == expected

    def test_very_short_session_text(self):
        """Edge case: user only typed a few words."""
        result = self._run(session="I'm tired.")
        assert isinstance(result, str)

    def test_very_long_session_text(self):
        """Edge case: user wrote extensively."""
        long_text = "I feel overwhelmed. " * 200
        result = self._run(session=long_text)
        assert isinstance(result, str)


# ── 4. run_burst_close — fallback on API failure ─────────────────────────────

class TestRunBurstCloseFallback:
    """Behavioral: fallback is used when graph fails or returns empty."""

    def test_fallback_when_graph_returns_empty_string(self):
        from app.agents import burst_agent

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"closing_message": ""}

        with patch.object(burst_agent, "_get_close_graph", return_value=mock_graph):
            result = burst_agent.run_burst_close("test session")

        assert result == burst_agent._FALLBACK_CLOSE

    def test_close_node_fallback_on_groq_exception(self):
        """Unit: close_node catches Exception and returns fallback dict."""
        from app.agents.burst_agent import close_node, CloseState, _FALLBACK_CLOSE

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Groq down")

        with patch("app.agents.burst_agent._get_client", return_value=mock_client):
            result = close_node({
                "session_text": "I've been carrying this for so long.",
                "closing_message": "",
            })

        assert result["closing_message"] == _FALLBACK_CLOSE


# ── 5. POST /agent/burst/ack integration ─────────────────────────────────────

class TestBurstAckEndpoint:
    """Integration tests for POST /agent/burst/ack (LLM fully mocked)."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_ack_happy_path_returns_200(self, client):
        with patch("app.routes.agents.run_burst_ack", return_value="I hear you."):
            resp = client.post(
                "/agent/burst/ack",
                json={"partial_text": _SAMPLE_PARTIAL, "elapsed_seconds": 40},
            )
        assert resp.status_code == 200

    def test_ack_response_has_acknowledgment_field(self, client):
        with patch("app.routes.agents.run_burst_ack", return_value="You're safe here."):
            resp = client.post(
                "/agent/burst/ack",
                json={"partial_text": _SAMPLE_PARTIAL, "elapsed_seconds": 40},
            )
        data = resp.json()
        assert "acknowledgment" in data
        assert isinstance(data["acknowledgment"], str)
        assert len(data["acknowledgment"]) > 0

    def test_ack_rejects_empty_partial_text(self, client):
        """Poka-Yoke: empty partial_text → 422."""
        resp = client.post(
            "/agent/burst/ack",
            json={"partial_text": "", "elapsed_seconds": 40},
        )
        assert resp.status_code == 422

    def test_ack_rejects_elapsed_out_of_range(self, client):
        """Poka-Yoke: elapsed_seconds > 300 → 422."""
        resp = client.post(
            "/agent/burst/ack",
            json={"partial_text": _SAMPLE_PARTIAL, "elapsed_seconds": 999},
        )
        assert resp.status_code == 422

    def test_ack_no_auth_required(self, client):
        """Design invariant: /burst/ack has no auth guard."""
        with patch("app.routes.agents.run_burst_ack", return_value="I'm with you."):
            resp = client.post(
                "/agent/burst/ack",
                json={"partial_text": _SAMPLE_PARTIAL, "elapsed_seconds": 20},
                # Note: no Authorization header
            )
        # Must NOT get 401 or 403
        assert resp.status_code not in (401, 403)

    def test_ack_graceful_fallback_on_api_error(self, client):
        """Behavioral: when run_burst_ack raises, route returns a fallback, not 500."""
        with patch(
            "app.routes.agents.run_burst_ack",
            side_effect=Exception("Groq died"),
        ):
            resp = client.post(
                "/agent/burst/ack",
                json={"partial_text": _SAMPLE_PARTIAL, "elapsed_seconds": 60},
            )
        # Route catches this and returns a fallback 200, not a crash 500
        assert resp.status_code == 200
        data = resp.json()
        assert "acknowledgment" in data


# ── 6. POST /agent/burst/close integration ───────────────────────────────────

class TestBurstCloseEndpoint:
    """Integration tests for POST /agent/burst/close (LLM fully mocked)."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_close_happy_path_returns_200(self, client):
        with patch(
            "app.routes.agents.run_burst_close",
            return_value="You showed up for yourself tonight.",
        ):
            resp = client.post(
                "/agent/burst/close",
                json={"session_text": _SAMPLE_SESSION},
            )
        assert resp.status_code == 200

    def test_close_response_has_closing_message_field(self, client):
        expected = "Thank you for trusting this space tonight."
        with patch("app.routes.agents.run_burst_close", return_value=expected):
            resp = client.post(
                "/agent/burst/close",
                json={"session_text": _SAMPLE_SESSION},
            )
        data = resp.json()
        assert "closing_message" in data
        assert isinstance(data["closing_message"], str)
        assert len(data["closing_message"]) > 0

    def test_close_rejects_empty_session_text(self, client):
        """Poka-Yoke: empty session_text → 422."""
        resp = client.post(
            "/agent/burst/close",
            json={"session_text": ""},
        )
        assert resp.status_code == 422

    def test_close_no_auth_required(self, client):
        """Design invariant: /burst/close has no auth guard."""
        with patch(
            "app.routes.agents.run_burst_close",
            return_value="Rest easy.",
        ):
            resp = client.post(
                "/agent/burst/close",
                json={"session_text": _SAMPLE_SESSION},
            )
        assert resp.status_code not in (401, 403)

    def test_close_graceful_fallback_on_api_error(self, client):
        """Behavioral: when run_burst_close raises, route returns a fallback, not 500."""
        with patch(
            "app.routes.agents.run_burst_close",
            side_effect=Exception("Groq died"),
        ):
            resp = client.post(
                "/agent/burst/close",
                json={"session_text": _SAMPLE_SESSION},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "closing_message" in data
