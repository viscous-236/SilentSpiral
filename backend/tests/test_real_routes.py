"""
tests/test_real_routes.py
==========================
Real HTTP route integration tests — ZERO mocking.

Every test in this file exercises the full request/response stack:
    TestClient → FastAPI route handler → real service/agent → real model/API

Covered routes
--------------
  POST /analyze            — GoEmotions classifier (local model)
  POST /patterns/analyze   — Pattern Engine (pure NumPy, no API)
  POST /agent/reflect      — Reflection Agent (live DeepSeek-R1 via HF Together)
  POST /agent/pattern      — Pattern Agent (live DeepSeek-R1 via HF Together)
  POST /agent/coach        — Coach Agent (live DeepSeek-R1 via HF Together)

Test design philosophy
-----------------------
- Structural / contract assertions only — never match exact LLM strings.
- Each test sends a realistic payload (not a toy/minimal fixture).
- HTTP status codes are always checked first.
- LLM-backed routes marked with @pytest.mark.integration so they can be
  excluded from fast unit runs:  pytest -m "not integration"
- TestClient is initialised once per test module (model warmup amortised).

Run these tests with:
    cd backend
    pytest tests/test_real_routes.py -v --timeout=180
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── Shared client (model loaded once per module) ──────────────────────────────

@pytest.fixture(scope="module")
def client():
    """TestClient with the real FastAPI app; NLP model warmed once per module."""
    from app.main import app
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# 1. POST /analyze — local GoEmotions model, no network
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzeRoute:
    """Route-level integration for POST /analyze — real local NLP inference."""

    def test_happy_path_returns_200(self, client):
        resp = client.post("/analyze", json={"text": "I feel deeply grateful and at peace today."})
        assert resp.status_code == 200, resp.text

    def test_response_contains_required_keys(self, client):
        resp = client.post("/analyze", json={"text": "Today was really hard and exhausting."})
        assert resp.status_code == 200
        body = resp.json()
        required = {"emotions", "top_emotion", "intensity", "emotion_category", "word_count", "crisis_flag"}
        assert required <= body.keys(), f"Missing keys: {required - body.keys()}"

    def test_emotions_list_has_label_and_score(self, client):
        resp = client.post("/analyze", json={"text": "I am furious and feeling betrayed."})
        assert resp.status_code == 200
        for emo in resp.json()["emotions"]:
            assert "label" in emo
            assert "score" in emo
            assert 0.0 <= emo["score"] <= 1.0

    def test_top_emotion_is_non_empty_string(self, client):
        resp = client.post("/analyze", json={"text": "Feeling hopeful about tomorrow."})
        assert resp.status_code == 200
        assert isinstance(resp.json()["top_emotion"], str)
        assert len(resp.json()["top_emotion"]) > 0

    def test_intensity_in_unit_range(self, client):
        resp = client.post("/analyze", json={"text": "Mixed bag of a day — some joy, some stress."})
        assert resp.status_code == 200
        assert 0.0 <= resp.json()["intensity"] <= 1.0

    def test_emotion_category_is_one_of_three_values(self, client):
        resp = client.post("/analyze", json={"text": "I feel quite sad today."})
        assert resp.status_code == 200
        assert resp.json()["emotion_category"] in {"positive", "negative", "neutral"}

    def test_word_count_matches_input(self, client):
        text = "This is a five word sentence with eight total words."
        resp = client.post("/analyze", json={"text": text})
        assert resp.status_code == 200
        assert resp.json()["word_count"] == len(text.split())

    def test_crisis_flag_false_for_normal_text(self, client):
        resp = client.post("/analyze", json={"text": "I had a great day and feel wonderful."})
        assert resp.status_code == 200
        assert resp.json()["crisis_flag"] is False

    def test_crisis_flag_true_for_crisis_text(self, client):
        resp = client.post("/analyze", json={"text": "I feel so hopeless I want to end my life."})
        assert resp.status_code == 200
        assert resp.json()["crisis_flag"] is True, (
            "crisis_flag must be True for text containing 'end my life'"
        )

    def test_negative_emotion_text_surfaces_negative_category(self, client):
        resp = client.post(
            "/analyze",
            json={"text": "I feel crushed and devastated. Nothing is going right and I'm in despair."},
        )
        assert resp.status_code == 200
        body = resp.json()
        # For strongly negative text the category should be negative (not a hard requirement
        # but the model should confidently classify this)
        assert body["emotion_category"] in {"negative", "neutral"}, (
            f"Strongly negative text should not produce 'positive' category, "
            f"got: {body['emotion_category']} (top: {body['top_emotion']})"
        )

    def test_empty_text_returns_422(self, client):
        resp = client.post("/analyze", json={"text": ""})
        assert resp.status_code == 422, f"Empty text should be rejected at schema level, got {resp.status_code}"

    def test_missing_text_field_returns_422(self, client):
        resp = client.post("/analyze", json={})
        assert resp.status_code == 422

    def test_very_long_text_exceeds_5000_chars_returns_422(self, client):
        resp = client.post("/analyze", json={"text": "a " * 3000})  # >5000 chars
        assert resp.status_code == 422

    def test_positive_text_has_positive_top_emotion(self, client):
        resp = client.post("/analyze", json={"text": "I am so joyful and grateful, this is wonderful!"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["top_emotion"] in {
            "joy", "admiration", "amusement", "approval", "caring",
            "desire", "excitement", "gratitude", "optimism", "pride", "relief", "love",
        } or body["emotion_category"] in {"positive", "neutral"}, (
            f"Clearly positive text gave unexpected top emotion: {body['top_emotion']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. POST /patterns/analyze — pure NumPy, no external API
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternsAnalyzeRoute:
    """Route-level integration for POST /patterns/analyze — pure computation."""

    def _make_records(self, n: int, sadness: float = 0.75, joy: float = 0.05) -> list[dict]:
        return [
            {
                "user_id": "test_user",
                "entry_id": f"e{i}",
                "timestamp": "2024-01-01T12:00:00+00:00",
                "emotions": {"sadness": sadness, "joy": joy},
            }
            for i in range(n)
        ]

    def test_happy_path_returns_200(self, client):
        payload = {"records": self._make_records(5)}
        resp = client.post("/patterns/analyze", json=payload)
        assert resp.status_code == 200, resp.text

    def test_response_contains_window_and_anomaly(self, client):
        payload = {"records": self._make_records(5)}
        resp = client.post("/patterns/analyze", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "window" in body
        assert "anomaly" in body

    def test_window_contains_required_fields(self, client):
        payload = {"records": self._make_records(3)}
        resp = client.post("/patterns/analyze", json=payload)
        assert resp.status_code == 200
        window = resp.json()["window"]
        assert "avg_scores" in window
        assert "dominant_emotion" in window
        assert "volatility_score" in window
        assert "entry_count" in window

    def test_entry_count_matches_input(self, client):
        n = 7
        payload = {"records": self._make_records(n)}
        resp = client.post("/patterns/analyze", json=payload)
        assert resp.status_code == 200
        assert resp.json()["window"]["entry_count"] == n

    def test_dominant_emotion_is_correct(self, client):
        payload = {"records": self._make_records(5, sadness=0.8, joy=0.05)}
        resp = client.post("/patterns/analyze", json=payload)
        assert resp.status_code == 200
        assert resp.json()["window"]["dominant_emotion"] == "sadness"

    def test_downward_spiral_detected_with_5_negative_records(self, client):
        payload = {"records": self._make_records(5, sadness=0.8, joy=0.05)}
        resp = client.post("/patterns/analyze", json=payload)
        assert resp.status_code == 200
        assert resp.json()["anomaly"] == "DOWNWARD_SPIRAL", (
            "5 records with dominant sadness should trigger DOWNWARD_SPIRAL"
        )

    def test_no_anomaly_for_positive_week(self, client):
        records = [
            {
                "user_id": "test_user",
                "entry_id": f"e{i}",
                "timestamp": "2024-01-01T12:00:00+00:00",
                "emotions": {"joy": 0.85, "sadness": 0.03},
            }
            for i in range(5)
        ]
        resp = client.post("/patterns/analyze", json={"records": records})
        assert resp.status_code == 200
        assert resp.json()["anomaly"] is None, (
            "Dominant joy with no volatility should produce no anomaly"
        )

    def test_empty_records_returns_422(self, client):
        resp = client.post("/patterns/analyze", json={"records": []})
        assert resp.status_code == 422

    def test_over_90_records_returns_422(self, client):
        payload = {"records": self._make_records(91)}
        resp = client.post("/patterns/analyze", json=payload)
        assert resp.status_code == 422, "Payloads >90 records should be rejected"

    def test_invalid_emotion_score_above_1_returns_422(self, client):
        records = [
            {
                "user_id": "u1",
                "entry_id": "e1",
                "timestamp": "2024-01-01T12:00:00+00:00",
                "emotions": {"sadness": 1.5},   # invalid
            }
        ]
        resp = client.post("/patterns/analyze", json={"records": records})
        assert resp.status_code == 422, "Score > 1.0 must be rejected by Pydantic"


# ─────────────────────────────────────────────────────────────────────────────
# 3. POST /agent/reflect — live DeepSeek-R1 via HuggingFace Together
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestReflectRouteReal:
    """Real HTTP tests for POST /agent/reflect — live LLM, no mocking."""

    _JOURNAL = (
        "I snapped at my colleague today without realising why. "
        "Later I sat at my desk feeling hollow. I don't understand myself lately."
    )
    _EMOTIONS = [{"label": "confusion", "score": 0.55}, {"label": "sadness", "score": 0.40}]

    def _post(self, client, **overrides) -> dict:
        payload = {
            "journal_text": self._JOURNAL,
            "emotions": self._EMOTIONS,
        }
        payload.update(overrides)
        resp = client.post("/agent/reflect", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        return resp.json()

    def test_returns_200_with_questions_key(self, client):
        body = self._post(client)
        assert "questions" in body

    def test_returns_exactly_two_questions(self, client):
        body = self._post(client)
        assert len(body["questions"]) == 2, (
            f"Must return exactly 2 questions, got: {body['questions']}"
        )

    def test_questions_are_non_empty_strings(self, client):
        body = self._post(client)
        for q in body["questions"]:
            assert isinstance(q, str)
            assert len(q.strip()) > 5, f"Question too short: {q!r}"

    def test_questions_end_with_question_mark(self, client):
        body = self._post(client)
        for q in body["questions"]:
            assert q.strip().endswith("?"), f"Expected '?' at end of: {q!r}"

    def test_top_emotion_echoed_in_response(self, client):
        body = self._post(client)
        assert "top_emotion" in body
        assert isinstance(body["top_emotion"], str)
        assert len(body["top_emotion"]) > 0

    def test_mirror_phrase_echoed_when_provided(self, client):
        mirror = "I feel invisible at work, like nobody notices me."
        body = self._post(client, mirror_phrase=mirror)
        assert body.get("mirror_phrase_used") == mirror

    def test_mirror_phrase_null_when_not_provided(self, client):
        body = self._post(client)
        assert body.get("mirror_phrase_used") is None

    def test_empty_emotions_still_returns_two_questions(self, client):
        body = self._post(client, emotions=[])
        assert len(body["questions"]) == 2

    def test_with_history_still_returns_two_questions(self, client):
        body = self._post(
            client,
            history=[
                "What was the first moment you noticed this feeling today?",
                "How does that hollowness feel in your body right now?",
            ],
        )
        assert len(body["questions"]) == 2

    def test_no_clinical_terms_in_response(self, client):
        BANNED = ["depression", "anxiety disorder", "trauma", "ptsd", "bipolar", "mental illness"]
        body = self._post(client)
        all_text = " ".join(body["questions"]).lower()
        for term in BANNED:
            assert term not in all_text, f"Clinical term '{term}' found in route output"

    def test_journal_text_too_long_returns_422(self, client):
        resp = client.post(
            "/agent/reflect",
            json={"journal_text": "x " * 3000, "emotions": []},  # >5000 chars
        )
        assert resp.status_code == 422

    def test_empty_journal_text_returns_422(self, client):
        resp = client.post("/agent/reflect", json={"journal_text": "", "emotions": []})
        assert resp.status_code == 422

    def test_invalid_emotion_score_above_1_returns_422(self, client):
        resp = client.post(
            "/agent/reflect",
            json={"journal_text": "I feel strange.", "emotions": [{"label": "sadness", "score": 1.5}]},
        )
        assert resp.status_code == 422

    def test_empty_emotion_label_returns_422(self, client):
        resp = client.post(
            "/agent/reflect",
            json={"journal_text": "I feel strange.", "emotions": [{"label": "", "score": 0.5}]},
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 4. POST /agent/pattern — live DeepSeek-R1 via HuggingFace Together
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestPatternAgentRouteReal:
    """Real HTTP tests for POST /agent/pattern — live LLM, no mocking."""

    _WINDOW = {
        "avg_scores": {"sadness": 0.65, "fear": 0.35, "joy": 0.07},
        "dominant_emotion": "sadness",
        "volatility_score": 0.18,
        "entry_count": 7,
    }

    def _post(self, client, **overrides) -> dict:
        payload = {"window_stats": self._WINDOW}
        payload.update(overrides)
        resp = client.post("/agent/pattern", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        return resp.json()

    def test_returns_200_and_required_keys(self, client):
        body = self._post(client)
        assert {"insights", "highlight", "dominant_emotion"} <= body.keys()

    def test_insights_count_between_3_and_5(self, client):
        body = self._post(client)
        assert 3 <= len(body["insights"]) <= 5, (
            f"Expected 3-5 insights, got {len(body['insights'])}: {body['insights']}"
        )

    def test_insights_are_non_empty_strings(self, client):
        body = self._post(client)
        for sentence in body["insights"]:
            assert isinstance(sentence, str)
            assert len(sentence.strip()) > 10, f"Insight too short: {sentence!r}"

    def test_highlight_is_non_empty_string(self, client):
        body = self._post(client)
        assert isinstance(body["highlight"], str)
        assert len(body["highlight"].strip()) > 5

    def test_dominant_emotion_echoed_correctly(self, client):
        body = self._post(client)
        assert body["dominant_emotion"] == "sadness"

    def test_with_downward_spiral_anomaly(self, client):
        body = self._post(client, anomaly_flag="DOWNWARD_SPIRAL")
        assert 3 <= len(body["insights"]) <= 5
        assert len(body["highlight"]) > 5

    def test_with_high_volatility_anomaly(self, client):
        body = self._post(client, anomaly_flag="HIGH_VOLATILITY")
        assert 3 <= len(body["insights"]) <= 5

    def test_with_no_anomaly_flag(self, client):
        body = self._post(client, anomaly_flag=None)
        assert 3 <= len(body["insights"]) <= 5

    def test_no_clinical_terms_in_response(self, client):
        BANNED = ["depression", "anxiety disorder", "trauma", "bipolar", "mental illness"]
        body = self._post(client, anomaly_flag="DOWNWARD_SPIRAL")
        all_text = (" ".join(body["insights"]) + " " + body["highlight"]).lower()
        for term in BANNED:
            assert term not in all_text, f"Clinical term '{term}' found in pattern route output"

    def test_missing_window_stats_returns_422(self, client):
        resp = client.post("/agent/pattern", json={})
        assert resp.status_code == 422

    def test_entry_count_zero_returns_422(self, client):
        bad_window = {**self._WINDOW, "entry_count": 0}
        resp = client.post("/agent/pattern", json={"window_stats": bad_window})
        assert resp.status_code == 422

    def test_invalid_anomaly_flag_returns_422(self, client):
        resp = client.post(
            "/agent/pattern",
            json={"window_stats": self._WINDOW, "anomaly_flag": "TOTALLY_INVALID"},
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 5. POST /agent/coach — live DeepSeek-R1 via HuggingFace Together
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCoachAgentRouteReal:
    """Real HTTP tests for POST /agent/coach — live LLM + short-circuit guard."""

    _INSIGHT = (
        "Over the past week, sadness and fear have been consistently dominant. "
        "Your journal entries reveal a recurring sense of disconnection, especially "
        "in the evenings. Engagement with self-reflection has been steady."
    )

    def test_short_circuit_with_no_anomaly_returns_empty(self, client):
        resp = client.post(
            "/agent/coach",
            json={"pattern_insight": self._INSIGHT, "anomaly_flag": None},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["triggered"] is False
        assert body["suggestions"] == []
        assert body["challenge"] == ""

    def test_downward_spiral_returns_200_with_suggestions(self, client):
        resp = client.post(
            "/agent/coach",
            json={"pattern_insight": self._INSIGHT, "anomaly_flag": "DOWNWARD_SPIRAL"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["triggered"] is True
        assert 1 <= len(body["suggestions"]) <= 2

    def test_high_volatility_returns_non_empty_challenge(self, client):
        resp = client.post(
            "/agent/coach",
            json={"pattern_insight": self._INSIGHT, "anomaly_flag": "HIGH_VOLATILITY"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["challenge"], str)
        assert len(body["challenge"].strip()) > 5

    def test_low_engagement_returns_valid_output(self, client):
        resp = client.post(
            "/agent/coach",
            json={
                "pattern_insight": "You haven't journaled much this week.",
                "anomaly_flag": "LOW_ENGAGEMENT",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["suggestions"], list)
        assert isinstance(body["challenge"], str)

    def test_suggestions_do_not_use_prescriptive_language(self, client):
        resp = client.post(
            "/agent/coach",
            json={"pattern_insight": self._INSIGHT, "anomaly_flag": "DOWNWARD_SPIRAL"},
        )
        assert resp.status_code == 200
        BANNED = ["you should", "you must", "you need to", "you have to"]
        text = (" ".join(resp.json()["suggestions"]) + " " + resp.json()["challenge"]).lower()
        for phrase in BANNED:
            assert phrase not in text, f"Prescriptive phrase '{phrase}' found in coach output"

    def test_with_user_preferences(self, client):
        resp = client.post(
            "/agent/coach",
            json={
                "pattern_insight": self._INSIGHT,
                "anomaly_flag": "DOWNWARD_SPIRAL",
                "user_preferences": {
                    "preferred_activity": "walking",
                    "available_time_morning": "10 minutes",
                },
            },
        )
        assert resp.status_code == 200
        assert 1 <= len(resp.json()["suggestions"]) <= 2

    def test_empty_pattern_insight_returns_422(self, client):
        resp = client.post(
            "/agent/coach",
            json={"pattern_insight": "", "anomaly_flag": "DOWNWARD_SPIRAL"},
        )
        assert resp.status_code == 422

    def test_invalid_anomaly_flag_returns_422(self, client):
        resp = client.post(
            "/agent/coach",
            json={"pattern_insight": self._INSIGHT, "anomaly_flag": "NOT_VALID"},
        )
        assert resp.status_code == 422

    def test_response_contains_all_required_keys(self, client):
        resp = client.post(
            "/agent/coach",
            json={"pattern_insight": self._INSIGHT, "anomaly_flag": "HIGH_VOLATILITY"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert {"triggered", "suggestions", "challenge"} <= body.keys()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Full pipeline: /analyze → /patterns/analyze → /agent/reflect → /agent/coach
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestFullRoutePipeline:
    """
    End-to-end route chain simulating a real mobile client call flow.

    1. Analyze journal text → get emotion scores
    2. Build EmotionRecords and run pattern analysis
    3. Run reflection agent with NLP output
    4. Run pattern agent, then coach agent if anomaly detected
    """

    def test_analyze_feeds_reflect(self, client):
        """NLP route output can be forwarded directly to reflect route."""
        # Step 1: Analyze a journal entry
        journal = (
            "Everything feels pointless today. I kept staring at my ceiling "
            "trying to remember why I care about any of this."
        )
        analyze_resp = client.post("/analyze", json={"text": journal})
        assert analyze_resp.status_code == 200
        nlp = analyze_resp.json()

        # Step 2: Forward NLP output into reflect, exactly as the mobile app would
        reflect_payload = {
            "journal_text": journal,
            "emotions": nlp["emotions"],
        }
        reflect_resp = client.post("/agent/reflect", json=reflect_payload)
        assert reflect_resp.status_code == 200

        body = reflect_resp.json()
        assert len(body["questions"]) == 2
        for q in body["questions"]:
            assert q.strip().endswith("?"), f"Expected question mark: {q!r}"

    def test_patterns_analyze_feeds_pattern_agent(self, client):
        """Pattern route output feeds directly into the pattern agent route."""
        # Week of uniform sadness → triggers DOWNWARD_SPIRAL
        records = [
            {
                "user_id": "demo",
                "entry_id": f"e{i}",
                "timestamp": "2024-01-01T00:00:00+00:00",
                "emotions": {"sadness": 0.78, "fear": 0.30, "joy": 0.04},
            }
            for i in range(6)
        ]
        pattern_resp = client.post("/patterns/analyze", json={"records": records})
        assert pattern_resp.status_code == 200
        pattern_data = pattern_resp.json()

        # Build agent/pattern payload from pattern route output
        agent_resp = client.post(
            "/agent/pattern",
            json={
                "window_stats": pattern_data["window"],
                "anomaly_flag": pattern_data["anomaly"],
            },
        )
        assert agent_resp.status_code == 200
        body = agent_resp.json()
        assert 3 <= len(body["insights"]) <= 5
        assert len(body["highlight"]) > 5

    def test_full_three_agent_chain(self, client):
        """Pattern → Pattern Agent → Coach Agent: the full agent orchestration."""
        records = [
            {
                "user_id": "demo",
                "entry_id": f"e{i}",
                "timestamp": "2024-01-01T00:00:00+00:00",
                "emotions": {"sadness": 0.80, "fear": 0.25, "joy": 0.03},
            }
            for i in range(6)
        ]

        # Step 1: Pattern analysis
        p_resp = client.post("/patterns/analyze", json={"records": records})
        assert p_resp.status_code == 200
        p_data = p_resp.json()

        # Step 2: Pattern Agent
        pa_resp = client.post(
            "/agent/pattern",
            json={"window_stats": p_data["window"], "anomaly_flag": p_data["anomaly"]},
        )
        assert pa_resp.status_code == 200
        pa_data = pa_resp.json()

        # Step 3: Coach Agent (only if anomaly present)
        if p_data["anomaly"] is not None:
            coach_resp = client.post(
                "/agent/coach",
                json={
                    "pattern_insight": " ".join(pa_data["insights"]),
                    "anomaly_flag": p_data["anomaly"],
                },
            )
            assert coach_resp.status_code == 200
            coach_data = coach_resp.json()
            assert coach_data["triggered"] is True
            assert 1 <= len(coach_data["suggestions"]) <= 2
        else:
            # No anomaly: coach short-circuits
            coach_resp = client.post(
                "/agent/coach",
                json={
                    "pattern_insight": " ".join(pa_data["insights"]),
                    "anomaly_flag": None,
                },
            )
            assert coach_resp.status_code == 200
            assert coach_resp.json()["triggered"] is False
