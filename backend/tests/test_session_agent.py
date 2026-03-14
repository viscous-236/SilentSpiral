"""
tests/test_session_agent.py
==========================
Behavioral tests for private session chat endpoints and session agent fallbacks.
"""

import time
from unittest.mock import patch

import pytest

from app.agents import session_agent


class TestSessionAgentFallbacks:
    def test_opening_fallback_on_exception(self):
        with patch.object(session_agent, "_chat", side_effect=Exception("boom")):
            result = session_agent.run_session_opening()
        assert result == session_agent._FALLBACK_OPENING

    def test_reply_fallback_on_empty_response(self):
        with patch.object(session_agent, "_chat", return_value=""):
            result = session_agent.run_session_reply(
                user_message="I feel overloaded today",
                elapsed_seconds=40,
                history=[],
            )
        assert result == session_agent._FALLBACK_REPLY

    def test_close_fallback_on_exception(self):
        with patch.object(session_agent, "_chat", side_effect=Exception("boom")):
            result = session_agent.run_session_close(session_text="It is too much.", history=[])
        assert result == session_agent._FALLBACK_CLOSE


class TestSessionEndpoints:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_session_start_returns_id_and_opening(self, client):
        with patch("app.routes.agents.run_session_opening", return_value="I am here with you."):
            resp = client.post("/agent/session/start", json={"duration_seconds": 600})

        assert resp.status_code == 200
        payload = resp.json()
        assert "session_id" in payload
        assert payload["agent_message"] == "I am here with you."
        assert payload["remaining_seconds"] == 600

    def test_session_message_happy_path(self, client):
        session_id = f"ssn_test_{int(time.time())}"

        with patch("app.routes.agents.run_session_reply", return_value="That sounds very heavy."):
            resp = client.post(
                "/agent/session/message",
                json={
                    "session_id": session_id,
                    "user_message": "I cannot carry this alone",
                    "elapsed_seconds": 15,
                    "history": [{"role": "agent", "content": "I am listening."}],
                },
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["agent_reply"] == "That sounds very heavy."
        assert payload["session_ended"] is False
        assert 0 < payload["remaining_seconds"] <= 600

    def test_session_message_returns_end_when_expired(self, client):
        old_ts = int(time.time()) - 660
        session_id = f"ssn_test_{old_ts}"

        resp = client.post(
            "/agent/session/message",
            json={
                "session_id": session_id,
                "user_message": "still here",
                "elapsed_seconds": 600,
                "history": [],
            },
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["session_ended"] is True
        assert payload["remaining_seconds"] == 0

    def test_session_message_rejects_invalid_session_id(self, client):
        resp = client.post(
            "/agent/session/message",
            json={
                "session_id": "badid",
                "user_message": "hello",
                "elapsed_seconds": 1,
                "history": [],
            },
        )

        assert resp.status_code == 400

    def test_session_close_happy_path(self, client):
        session_id = f"ssn_test_{int(time.time())}"

        with patch("app.routes.agents.run_session_close", return_value="You did something brave today."):
            resp = client.post(
                "/agent/session/close",
                json={
                    "session_id": session_id,
                    "history": [{"role": "user", "content": "I shared a lot."}],
                    "session_text": "I shared a lot.",
                },
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["closing_message"] == "You did something brave today."

    def test_session_endpoints_no_auth_required(self, client):
        with patch("app.routes.agents.run_session_opening", return_value="I am here."):
            resp = client.post("/agent/session/start", json={"duration_seconds": 600})

        assert resp.status_code not in (401, 403)
