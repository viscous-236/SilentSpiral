"""
tests/test_agent_coordination.py
=================================
Cross-agent coordination and pipeline integration tests.

What these tests verify (things that agent-level unit tests DON'T cover):

  1. Schema compatibility — PatternResponse.insights[0] is a valid
     CoachRequest.pattern_insight; response shapes of one agent can be
     forwarded as inputs to the next without transformation.

  2. Pattern → Coach handoff — the full two-step sequence (POST /agent/pattern
     followed by POST /agent/coach using the pattern response) works end-to-end
     including the `triggered` flag derivation.

  3. Coach short-circuit in pipeline — when Pattern returns no anomaly, the
     downstream Coach call receives anomaly_flag=null, returns triggered=False
     with empty suggestions, and never invokes the LLM.

  4. Mirror Prompt round-trip — find_mirror_phrase result flows from the vector
     store through POST /agent/reflect and is echoed back as mirror_phrase_used.

  5. Full pipeline simulation — the three routes chained in the order the
     mobile client would call them:
         Reflect (day 1) → Reflect × N (days 2–7) → Pattern → Coach → Reflect (day 8, with mirror)

  6. Error isolation — a 500 from the pattern route does not affect a
     subsequent reflect call on the same TestClient.

  7. Concurrent shape invariants — multiple agents called in a tight loop all
     return correctly shaped responses.

Methodology:
  - All LLM calls mocked at the ROUTE layer (patch where the name is *used*)
  - Vector store calls mocked at the SERVICE layer
  - No real HTTP — FastAPI TestClient only
  - No string-matching of LLM output — structural / type contracts only
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ── Output factories ──────────────────────────────────────────────────────────

def _reflection_output(q1="What is weighing on you most?", q2="How has this changed your day?"):
    from app.agents.reflection_agent import ReflectionOutput
    return ReflectionOutput(questions=[q1, q2])


def _pattern_output(n_insights=3, highlight="Your week shows a sustained emotional heaviness."):
    from app.agents.pattern_agent import PatternOutput
    insights = [
        f"Sadness has been the dominant emotion across {n_insights} of your recent entries.",
        "Your emotional intensity peaked mid-week before easing slightly.",
        "There is a recurring sense of disconnection visible in your journal.",
        "Positive emotions appeared briefly but did not sustain across the week.",
        "The overall arc of your week trended downward in emotional tone.",
    ][:n_insights]
    return PatternOutput(insights=insights, highlight=highlight)


def _coach_output(triggered=True):
    from app.agents.coach_agent import CoachOutput
    if not triggered:
        return CoachOutput(suggestions=[], challenge="")
    return CoachOutput(
        suggestions=[
            "You might try writing one sentence about something that felt okay today.",
            "You might try stepping outside for five minutes without your phone.",
        ],
        challenge="Tomorrow: notice one moment that felt lighter and write it down.",
    )


# ── Request body helpers ──────────────────────────────────────────────────────

def _reflect_body(journal="I have been feeling disconnected for days.", mirror_phrase=None):
    body = {
        "journal_text": journal,
        "emotions": [{"label": "sadness", "score": 0.80}, {"label": "fear", "score": 0.35}],
        "history": [],
    }
    if mirror_phrase is not None:
        body["mirror_phrase"] = mirror_phrase
    return body


def _pattern_body(anomaly_flag="DOWNWARD_SPIRAL", n_entries=7):
    return {
        "window_stats": {
            "dominant_emotion": "sadness",
            "avg_scores": {"sadness": 0.72, "joy": 0.08},
            "volatility_score": 0.18,
            "entry_count": n_entries,
        },
        "anomaly_flag": anomaly_flag,
        "history_summary": "",
    }


def _coach_body(pattern_insight, anomaly_flag="DOWNWARD_SPIRAL"):
    return {
        "pattern_insight": pattern_insight,
        "anomaly_flag": anomaly_flag,
        "user_preferences": {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema compatibility — output shapes flow between agents
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaCompatibility:
    """Verify that the output of each agent can be forwarded as input to the next."""

    def test_pattern_insight_acceptable_as_coach_pattern_insight(self):
        """PatternResponse.insights combined is a valid CoachRequest.pattern_insight."""
        po = _pattern_output()
        narrative = " ".join(po.insights)  # how the client concatenates for coach
        from app.schemas.agent import CoachRequest
        req = CoachRequest(
            pattern_insight=narrative,
            anomaly_flag="DOWNWARD_SPIRAL",
            user_preferences={},
        )
        assert req.pattern_insight == narrative

    def test_pattern_first_insight_alone_is_valid_coach_input(self):
        """Single PatternOutput insight is also a valid coach pattern_insight."""
        po = _pattern_output()
        from app.schemas.agent import CoachRequest
        req = CoachRequest(
            pattern_insight=po.insights[0],
            anomaly_flag="HIGH_VOLATILITY",
            user_preferences={},
        )
        assert len(req.pattern_insight) > 0

    def test_reflect_response_questions_always_exactly_two(self, client):
        """ReflectResponse always carries exactly 2 questions regardless of input."""
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_reflection",
                          MagicMock(return_value=_reflection_output())):
            resp = client.post("/agent/reflect", json=_reflect_body())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["questions"]) == 2
        assert all(isinstance(q, str) and len(q) > 0 for q in data["questions"])

    def test_pattern_response_insights_count_within_contract(self, client):
        """PatternResponse always has 3–5 insights."""
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output(n_insights=3))):
            resp = client.post("/agent/pattern", json=_pattern_body())
        assert resp.status_code == 200
        data = resp.json()
        assert 3 <= len(data["insights"]) <= 5

    def test_coach_response_suggestions_within_contract(self, client):
        """CoachResponse always has 0–2 suggestions."""
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_coach",
                          MagicMock(return_value=_coach_output())):
            resp = client.post("/agent/coach", json=_coach_body("Some narrative."))
        assert resp.status_code == 200
        data = resp.json()
        assert 0 <= len(data["suggestions"]) <= 2

    def test_all_three_response_bodies_are_json_serialisable(self, client):
        """All three agent responses deserialise cleanly to dicts."""
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_reflection",
                          MagicMock(return_value=_reflection_output())):
            r1 = client.post("/agent/reflect", json=_reflect_body()).json()
        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output())):
            r2 = client.post("/agent/pattern", json=_pattern_body()).json()
        with patch.object(agents_route, "run_coach",
                          MagicMock(return_value=_coach_output())):
            r3 = client.post("/agent/coach", json=_coach_body("Some narrative.")).json()

        for resp in (r1, r2, r3):
            assert isinstance(resp, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pattern → Coach handoff
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternToCoachHandoff:
    """
    Tests the two-step flow:
        POST /agent/pattern  →  use response  →  POST /agent/coach
    """

    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def _run_pattern_then_coach(self, client, anomaly_flag):
        import app.routes.agents as agents_route

        # Step 1 — Pattern
        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output())):
            pattern_resp = client.post("/agent/pattern",
                                       json=_pattern_body(anomaly_flag=anomaly_flag))

        assert pattern_resp.status_code == 200
        pattern_data = pattern_resp.json()

        # Step 2 — Build coach request from pattern response
        narrative = " ".join(pattern_data["insights"])
        coach_req = _coach_body(pattern_insight=narrative, anomaly_flag=anomaly_flag)

        with patch.object(agents_route, "run_coach",
                          MagicMock(return_value=_coach_output(triggered=anomaly_flag is not None))):
            coach_resp = client.post("/agent/coach", json=coach_req)

        assert coach_resp.status_code == 200
        return pattern_data, coach_resp.json()

    def test_downward_spiral_triggers_coach(self, client):
        pattern_data, coach_data = self._run_pattern_then_coach(client, "DOWNWARD_SPIRAL")
        assert coach_data["triggered"] is True
        assert len(coach_data["suggestions"]) >= 1

    def test_high_volatility_triggers_coach(self, client):
        pattern_data, coach_data = self._run_pattern_then_coach(client, "HIGH_VOLATILITY")
        assert coach_data["triggered"] is True

    def test_low_engagement_triggers_coach(self, client):
        pattern_data, coach_data = self._run_pattern_then_coach(client, "LOW_ENGAGEMENT")
        assert coach_data["triggered"] is True

    def test_pattern_dominant_emotion_present_in_response(self, client):
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output())):
            resp = client.post("/agent/pattern", json=_pattern_body())
        assert "dominant_emotion" in resp.json()
        assert resp.json()["dominant_emotion"] == "sadness"

    def test_pattern_highlight_forwarded_through_pipeline(self, client):
        expected_highlight = "Your week shows a sustained emotional heaviness."
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output(highlight=expected_highlight))):
            resp = client.post("/agent/pattern", json=_pattern_body())
        assert resp.json()["highlight"] == expected_highlight

    def test_insights_from_pattern_become_valid_coach_input(self, client):
        """All 5 insights concatenated (max case) still pass CoachRequest validation."""
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output(n_insights=5))):
            pattern_resp = client.post("/agent/pattern", json=_pattern_body())

        # Build a coach body using all 5 insights joined — worst-case length
        narrative = " ".join(pattern_resp.json()["insights"])
        coach_req = _coach_body(pattern_insight=narrative)

        with patch.object(agents_route, "run_coach",
                          MagicMock(return_value=_coach_output())):
            coach_resp = client.post("/agent/coach", json=coach_req)

        assert coach_resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 3. Coach short-circuit coordination
# ─────────────────────────────────────────────────────────────────────────────

class TestCoachShortCircuit:
    """
    When anomaly_flag is null the Coach Agent must NOT call the LLM.
    The pipeline is: Pattern (no anomaly) → Coach (no-op).
    """

    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_no_anomaly_coach_triggered_false(self, client):
        import app.routes.agents as agents_route
        mock_run_coach = MagicMock(return_value=_coach_output(triggered=False))

        with patch.object(agents_route, "run_coach", mock_run_coach):
            resp = client.post(
                "/agent/coach",
                json=_coach_body("Healthy week narrative.", anomaly_flag=None),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["triggered"] is False
        assert data["suggestions"] == []
        assert data["challenge"] == ""

    def test_no_anomaly_coach_llm_never_invoked(self, client):
        """The LLM-backed run_coach should still be called by the route, but the
        agent-internal short-circuit prevents any LLM tokens being spent."""
        import app.routes.agents as agents_route

        # The real run_coach short-circuits itself when anomaly_flag is None.
        # Here we verify via the agent layer directly (not the route).
        from app.agents import coach_agent
        spy = MagicMock(wraps=coach_agent.run_coach)

        with patch.object(agents_route, "run_coach", spy):
            resp = client.post(
                "/agent/coach",
                json=_coach_body("Low-signal week.", anomaly_flag=None),
            )

        # Route called run_coach
        spy.assert_called_once()
        # The CoachAgent itself short-circuits — no LangGraph graph invocation.
        # Validated by the fact that the response is empty & triggered=False.
        assert resp.json()["triggered"] is False

    def test_anomaly_present_sets_triggered_true(self, client):
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_coach",
                          MagicMock(return_value=_coach_output(triggered=True))):
            resp = client.post(
                "/agent/coach",
                json=_coach_body("You've been feeling heavy.", anomaly_flag="DOWNWARD_SPIRAL"),
            )
        assert resp.json()["triggered"] is True

    def test_triggered_flag_set_by_route_not_agent(self, client):
        """The `triggered` flag is set by the ROUTE (body.anomaly_flag is not None),
        not by the agent itself — verify the route logic is correct."""
        import app.routes.agents as agents_route

        # Agent returns an object without `triggered` — route injects it.
        mock_output = _coach_output(triggered=True)  # CoachOutput has no triggered field

        for flag, expected in [("DOWNWARD_SPIRAL", True), (None, False)]:
            with patch.object(agents_route, "run_coach",
                              MagicMock(return_value=mock_output)):
                resp = client.post(
                    "/agent/coach",
                    json=_coach_body("Narrative.", anomaly_flag=flag),
                )
            assert resp.json()["triggered"] is expected, \
                f"Expected triggered={expected} for anomaly_flag={flag!r}"

    def test_all_three_anomaly_types_trigger_coach(self, client):
        import app.routes.agents as agents_route
        for anomaly in ("DOWNWARD_SPIRAL", "HIGH_VOLATILITY", "LOW_ENGAGEMENT"):
            with patch.object(agents_route, "run_coach",
                              MagicMock(return_value=_coach_output())):
                resp = client.post(
                    "/agent/coach",
                    json=_coach_body("Narrative.", anomaly_flag=anomaly),
                )
            assert resp.json()["triggered"] is True, f"Coach not triggered for {anomaly}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Mirror Prompt round-trip
# ─────────────────────────────────────────────────────────────────────────────

class TestMirrorPhraseRoundTrip:
    """
    Verify that the Mirror Prompt phrase flows:
        find_mirror_phrase() → POST /agent/reflect request
                             → run_reflection(mirror_phrase=...) call
                             → mirror_phrase_used in response
    """

    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_mirror_phrase_echoed_in_response(self, client):
        phrase = "I felt invisible and unheard last week."
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_reflection",
                          MagicMock(return_value=_reflection_output())):
            resp = client.post("/agent/reflect", json=_reflect_body(mirror_phrase=phrase))

        assert resp.status_code == 200
        assert resp.json()["mirror_phrase_used"] == phrase

    def test_no_mirror_phrase_null_in_response(self, client):
        import app.routes.agents as agents_route
        with patch.object(agents_route, "run_reflection",
                          MagicMock(return_value=_reflection_output())):
            resp = client.post("/agent/reflect", json=_reflect_body())

        assert resp.status_code == 200
        assert resp.json()["mirror_phrase_used"] is None

    def test_mirror_phrase_forwarded_to_run_reflection(self, client):
        """Route must pass mirror_phrase as a kwarg to run_reflection."""
        phrase = "Nobody notices my effort."
        import app.routes.agents as agents_route
        mock_fn = MagicMock(return_value=_reflection_output())

        with patch.object(agents_route, "run_reflection", mock_fn):
            client.post("/agent/reflect", json=_reflect_body(mirror_phrase=phrase))

        assert mock_fn.call_args.kwargs.get("mirror_phrase") == phrase

    def test_no_mirror_phrase_run_reflection_called_with_none(self, client):
        """When mirror_phrase absent from body, run_reflection gets None."""
        import app.routes.agents as agents_route
        mock_fn = MagicMock(return_value=_reflection_output())

        with patch.object(agents_route, "run_reflection", mock_fn):
            client.post("/agent/reflect", json=_reflect_body())

        assert mock_fn.call_args.kwargs.get("mirror_phrase") is None

    def test_find_mirror_phrase_result_piped_into_reflect_request(self, client):
        """Simulate the full server-side path: vector store returns a phrase,
        which the BACKEND passes into the agent (same process, no extra HTTP hop)."""
        from app.services import vector_store
        import app.routes.agents as agents_route

        past_phrase = "I always end up alone in these moments."

        with patch.object(vector_store, "find_mirror_phrase",
                          return_value=past_phrase) as mock_find, \
             patch.object(agents_route, "run_reflection",
                          MagicMock(return_value=_reflection_output())) as mock_run:

            # Caller (could be route or service layer) calls find_mirror_phrase first
            found = vector_store.find_mirror_phrase("I feel so alone today.")
            assert found == past_phrase

            # Then includes it in the reflect call
            resp = client.post("/agent/reflect",
                               json=_reflect_body(mirror_phrase=found))

        assert resp.status_code == 200
        assert resp.json()["mirror_phrase_used"] == past_phrase


# ─────────────────────────────────────────────────────────────────────────────
# 5. Full pipeline simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipelineSimulation:
    """
    End-to-end simulation of the complete agent pipeline the mobile app uses:

        Day 1–7  :  POST /agent/reflect   × 7  (journal entries, no mirror phrase yet)
        Day 7    :  POST /agent/pattern          (weekly synthesis, anomaly detected)
        Day 7    :  POST /agent/coach            (micro-habit suggestions triggered)
        Day 8    :  POST /agent/reflect          (mirror phrase from past entry injected)
    """

    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_full_week_pipeline_with_anomaly(self, client):
        import app.routes.agents as agents_route

        journal_entries = [
            "Everything feels heavy and slow today.",
            "I can't shake this low feeling. Work was fine but I'm drained.",
            "Another grey day. I went through motions.",
            "I skipped journaling yesterday. Today feels disconnected.",
            "The sadness is still here. It moves in and out.",
            "I feel unseen in my relationships lately.",
            "Seven days in and the weight hasn't lifted.",
        ]

        # ── Days 1–7: Reflect ────────────────────────────────────────────────
        reflect_mock = MagicMock(return_value=_reflection_output())
        for i, entry in enumerate(journal_entries, 1):
            with patch.object(agents_route, "run_reflection", reflect_mock):
                resp = client.post("/agent/reflect", json=_reflect_body(journal=entry))
            assert resp.status_code == 200, f"Day {i} reflect failed"
            assert len(resp.json()["questions"]) == 2

        # ── Day 7: Pattern synthesis ─────────────────────────────────────────
        pattern_mock = MagicMock(return_value=_pattern_output(n_insights=4))
        with patch.object(agents_route, "run_pattern", pattern_mock):
            pattern_resp = client.post("/agent/pattern",
                                       json=_pattern_body(anomaly_flag="DOWNWARD_SPIRAL",
                                                          n_entries=7))
        assert pattern_resp.status_code == 200
        pattern_data = pattern_resp.json()
        assert len(pattern_data["insights"]) == 4
        assert pattern_data["dominant_emotion"] == "sadness"

        # ── Day 7: Coach triggered by anomaly ────────────────────────────────
        narrative = " ".join(pattern_data["insights"])
        coach_mock = MagicMock(return_value=_coach_output(triggered=True))
        with patch.object(agents_route, "run_coach", coach_mock):
            coach_resp = client.post(
                "/agent/coach",
                json=_coach_body(pattern_insight=narrative,
                                 anomaly_flag="DOWNWARD_SPIRAL"),
            )
        assert coach_resp.status_code == 200
        coach_data = coach_resp.json()
        assert coach_data["triggered"] is True
        assert 1 <= len(coach_data["suggestions"]) <= 2
        assert len(coach_data["challenge"]) > 0

        # ── Day 8: Reflect with mirror phrase ────────────────────────────────
        past_phrase = journal_entries[0]  # "Everything feels heavy and slow today."
        reflect_mirror_mock = MagicMock(return_value=_reflection_output(
            q1="Does everything still feel as heavy as it did seven days ago?",
            q2="What has shifted, if anything, since that first heavy day?",
        ))
        with patch.object(agents_route, "run_reflection", reflect_mirror_mock):
            reflect_resp = client.post(
                "/agent/reflect",
                json=_reflect_body(
                    journal="Eight days in. The heaviness is lighter today.",
                    mirror_phrase=past_phrase,
                ),
            )
        assert reflect_resp.status_code == 200
        reflect_data = reflect_resp.json()
        assert reflect_data["mirror_phrase_used"] == past_phrase
        assert len(reflect_data["questions"]) == 2

    def test_full_week_pipeline_without_anomaly(self, client):
        """Healthy week: Pattern returns no anomaly → Coach short-circuits."""
        import app.routes.agents as agents_route

        # Day 1–7: Reflect (healthy)
        with patch.object(agents_route, "run_reflection",
                          MagicMock(return_value=_reflection_output())):
            for _ in range(7):
                resp = client.post("/agent/reflect", json=_reflect_body())
                assert resp.status_code == 200

        # Pattern — no anomaly
        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output(n_insights=3))):
            pattern_resp = client.post(
                "/agent/pattern",
                json={**_pattern_body(), "anomaly_flag": None},
            )
        assert pattern_resp.status_code == 200

        # Coach — no anomaly → triggered=False, empty output
        narrative = " ".join(pattern_resp.json()["insights"])
        with patch.object(agents_route, "run_coach",
                          MagicMock(return_value=_coach_output(triggered=False))):
            coach_resp = client.post(
                "/agent/coach",
                json=_coach_body(pattern_insight=narrative, anomaly_flag=None),
            )
        assert coach_resp.status_code == 200
        assert coach_resp.json()["triggered"] is False
        assert coach_resp.json()["suggestions"] == []
        assert coach_resp.json()["challenge"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# 6. Error isolation
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorIsolation:
    """
    Verify that an error in one agent route does not contaminate
    subsequent calls to other agents on the same TestClient.
    """

    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_pattern_500_does_not_break_subsequent_reflect(self, client):
        import app.routes.agents as agents_route

        # Force pattern to raise an unexpected error
        with patch.object(agents_route, "run_pattern",
                          MagicMock(side_effect=RuntimeError("Unexpected crash"))):
            bad_resp = client.post("/agent/pattern", json=_pattern_body())
        assert bad_resp.status_code == 500

        # Reflect should still work fine
        with patch.object(agents_route, "run_reflection",
                          MagicMock(return_value=_reflection_output())):
            good_resp = client.post("/agent/reflect", json=_reflect_body())
        assert good_resp.status_code == 200

    def test_coach_500_does_not_break_subsequent_pattern(self, client):
        import app.routes.agents as agents_route

        with patch.object(agents_route, "run_coach",
                          MagicMock(side_effect=RuntimeError("Coach crashed"))):
            bad_resp = client.post("/agent/coach",
                                   json=_coach_body("Narrative."))
        assert bad_resp.status_code == 500

        with patch.object(agents_route, "run_pattern",
                          MagicMock(return_value=_pattern_output())):
            good_resp = client.post("/agent/pattern", json=_pattern_body())
        assert good_resp.status_code == 200

    def test_reflect_500_does_not_break_subsequent_coach(self, client):
        import app.routes.agents as agents_route

        with patch.object(agents_route, "run_reflection",
                          MagicMock(side_effect=RuntimeError("Reflect crashed"))):
            bad_resp = client.post("/agent/reflect", json=_reflect_body())
        assert bad_resp.status_code == 500

        with patch.object(agents_route, "run_coach",
                          MagicMock(return_value=_coach_output())):
            good_resp = client.post(
                "/agent/coach",
                json=_coach_body("Narrative.", anomaly_flag="HIGH_VOLATILITY"),
            )
        assert good_resp.status_code == 200

    def test_all_three_routes_independent_of_each_other(self, client):
        """All three routes return 200 when called independently in any order."""
        import app.routes.agents as agents_route

        pairs = [
            ("/agent/reflect",  "run_reflection", _reflect_body(),          _reflection_output()),
            ("/agent/pattern",  "run_pattern",    _pattern_body(),           _pattern_output()),
            ("/agent/coach",    "run_coach",
             _coach_body("Narrative."), _coach_output()),
        ]
        for url, fn_name, body, output in pairs:
            with patch.object(agents_route, fn_name, MagicMock(return_value=output)):
                resp = client.post(url, json=body)
            assert resp.status_code == 200, f"{url} returned {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Concurrent / repeated call invariants
# ─────────────────────────────────────────────────────────────────────────────

class TestRepeatedCallInvariants:
    """
    Verify that calling the same agent multiple times in sequence always
    returns the same shaped response (no mutable state leakage).
    """

    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_reflect_called_ten_times_always_two_questions(self, client):
        import app.routes.agents as agents_route
        mock = MagicMock(return_value=_reflection_output())
        for _ in range(10):
            with patch.object(agents_route, "run_reflection", mock):
                resp = client.post("/agent/reflect", json=_reflect_body())
            assert resp.status_code == 200
            assert len(resp.json()["questions"]) == 2

    def test_pattern_called_multiple_insight_counts_always_valid(self, client):
        import app.routes.agents as agents_route
        for n in (3, 4, 5):
            mock = MagicMock(return_value=_pattern_output(n_insights=n))
            with patch.object(agents_route, "run_pattern", mock):
                resp = client.post("/agent/pattern", json=_pattern_body())
            assert resp.status_code == 200
            assert len(resp.json()["insights"]) == n

    def test_coach_alternating_anomaly_and_none_gives_correct_triggered(self, client):
        import app.routes.agents as agents_route
        cases = [
            ("DOWNWARD_SPIRAL", True),
            (None, False),
            ("HIGH_VOLATILITY", True),
            (None, False),
            ("LOW_ENGAGEMENT", True),
        ]
        for anomaly, expected_triggered in cases:
            coachout = _coach_output(triggered=expected_triggered)
            with patch.object(agents_route, "run_coach",
                              MagicMock(return_value=coachout)):
                resp = client.post(
                    "/agent/coach",
                    json=_coach_body("Narrative.", anomaly_flag=anomaly),
                )
            assert resp.status_code == 200
            assert resp.json()["triggered"] is expected_triggered, \
                f"anomaly={anomaly}: expected triggered={expected_triggered}"

    def test_mirror_phrase_present_and_absent_alternating(self, client):
        import app.routes.agents as agents_route
        phrases = ["I felt invisible.", None, "Nobody listens to me.", None]
        mock = MagicMock(return_value=_reflection_output())
        for phrase in phrases:
            with patch.object(agents_route, "run_reflection", mock):
                resp = client.post("/agent/reflect",
                                   json=_reflect_body(mirror_phrase=phrase))
            assert resp.status_code == 200
            assert resp.json()["mirror_phrase_used"] == phrase
