"""
tests/test_pattern_engine.py
=============================
Unit tests for services/pattern_engine.py
- compute_window: happy path, single record, uniform scores
- detect_anomaly: all 3 flag conditions + no-anomaly path
"""

from datetime import datetime, timezone

import pytest

from app.models.emotion import EmotionRecord
from app.services.pattern_engine import WindowStats, compute_window, detect_anomaly


# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_record(emotions: dict[str, float], entry_id: str = "e1") -> EmotionRecord:
    return EmotionRecord(
        user_id="test_user",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        emotions=emotions,
        entry_id=entry_id,
    )


def make_sad_records(n: int) -> list[EmotionRecord]:
    """n records with sadness dominant, stable scores (low volatility)."""
    return [
        make_record({"sadness": 0.75, "joy": 0.05}, entry_id=f"e{i}")
        for i in range(n)
    ]


# ── compute_window ────────────────────────────────────────────────────────────


def test_compute_window_happy_path():
    records = [
        make_record({"sadness": 0.8, "joy": 0.1}, "e1"),
        make_record({"sadness": 0.6, "joy": 0.3}, "e2"),
        make_record({"sadness": 0.7, "joy": 0.2}, "e3"),
    ]
    stats = compute_window(records)

    assert stats.entry_count == 3
    assert stats.dominant_emotion == "sadness"
    assert stats.avg_scores["sadness"] == pytest.approx(0.7, abs=1e-4)
    assert stats.avg_scores["joy"] == pytest.approx(0.2, abs=1e-4)
    assert isinstance(stats.volatility_score, float)
    assert stats.volatility_score >= 0.0


def test_compute_window_single_record():
    records = [make_record({"joy": 0.9, "sadness": 0.05}, "e1")]
    stats = compute_window(records)

    assert stats.entry_count == 1
    assert stats.dominant_emotion == "joy"
    assert stats.avg_scores["joy"] == pytest.approx(0.9)
    # std of a single value is 0
    assert stats.volatility_score == pytest.approx(0.0)


def test_compute_window_uniform_scores():
    """Identical records → zero volatility."""
    records = [
        make_record({"anger": 0.5, "fear": 0.3}, f"e{i}") for i in range(5)
    ]
    stats = compute_window(records)
    assert stats.volatility_score == pytest.approx(0.0)
    assert stats.dominant_emotion == "anger"


def test_compute_window_empty_raises():
    with pytest.raises(ValueError, match="non-empty"):
        compute_window([])


def test_compute_window_model_dump_keys():
    records = make_sad_records(2)
    stats = compute_window(records)
    d = stats.model_dump()
    assert set(d.keys()) == {"avg_scores", "dominant_emotion", "volatility_score", "entry_count"}


# ── detect_anomaly ────────────────────────────────────────────────────────────


def _make_window(
    dominant: str = "joy",
    volatility: float = 0.1,
    entry_count: int = 7,
    avg_scores: dict | None = None,
) -> WindowStats:
    if avg_scores is None:
        avg_scores = {dominant: 0.7}
    return WindowStats(
        avg_scores=avg_scores,
        dominant_emotion=dominant,
        volatility_score=volatility,
        entry_count=entry_count,
    )


def test_detect_anomaly_high_volatility():
    window = _make_window(volatility=0.45)
    assert detect_anomaly(window) == "HIGH_VOLATILITY"


def test_detect_anomaly_high_volatility_boundary():
    """Exactly 0.4 should NOT trigger HIGH_VOLATILITY (> not >=)."""
    window = _make_window(volatility=0.4, dominant="sadness", entry_count=5)
    # Rule 1 doesn't fire; rule 2 should
    assert detect_anomaly(window) == "DOWNWARD_SPIRAL"


def test_detect_anomaly_downward_spiral_sadness():
    window = _make_window(dominant="sadness", entry_count=5, volatility=0.1)
    assert detect_anomaly(window) == "DOWNWARD_SPIRAL"


def test_detect_anomaly_downward_spiral_fear():
    window = _make_window(dominant="fear", entry_count=7, volatility=0.05)
    assert detect_anomaly(window) == "DOWNWARD_SPIRAL"


def test_detect_anomaly_downward_spiral_anger():
    window = _make_window(dominant="anger", entry_count=5, volatility=0.0)
    assert detect_anomaly(window) == "DOWNWARD_SPIRAL"


def test_detect_anomaly_downward_spiral_requires_5_entries():
    """4 entries with sad dominant, low volatility → no anomaly triggered.
    Spiral needs >=5, engagement needs <2, volatility needs >0.4.
    """
    window = _make_window(dominant="sadness", entry_count=4, volatility=0.0)
    assert detect_anomaly(window) is None


def test_detect_anomaly_low_engagement():
    window = _make_window(dominant="joy", entry_count=1, volatility=0.05)
    assert detect_anomaly(window) == "LOW_ENGAGEMENT"


def test_detect_anomaly_low_engagement_boundary():
    """Exactly 2 entries should NOT trigger LOW_ENGAGEMENT (< not <=)."""
    window = _make_window(dominant="joy", entry_count=2, volatility=0.05)
    assert detect_anomaly(window) is None


def test_detect_anomaly_none():
    """Normal healthy usage — no anomaly."""
    window = _make_window(dominant="joy", entry_count=6, volatility=0.15)
    assert detect_anomaly(window) is None


def test_detect_anomaly_priority_volatility_over_spiral():
    """HIGH_VOLATILITY should be returned before DOWNWARD_SPIRAL."""
    window = _make_window(dominant="sadness", entry_count=7, volatility=0.5)
    assert detect_anomaly(window) == "HIGH_VOLATILITY"


# ── Kaizen tests: Poka-Yoke score validation ──────────────────────────────────


def test_emotion_record_rejects_score_above_1():
    """Poka-Yoke: score > 1.0 raises ValidationError at model boundary."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="0.0 and 1.0"):
        make_record({"sadness": 1.5})


def test_emotion_record_rejects_negative_score():
    """Poka-Yoke: negative score raises ValidationError at model boundary."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="0.0 and 1.0"):
        make_record({"joy": -0.1})


def test_emotion_record_accepts_boundary_scores():
    """Scores of exactly 0.0 and 1.0 are valid (inclusive bounds)."""
    rec = make_record({"sadness": 1.0, "joy": 0.0})
    assert rec.emotions["sadness"] == 1.0
    assert rec.emotions["joy"] == 0.0


def test_window_stats_is_pydantic_model():
    """Kaizen: WindowStats is a Pydantic BaseModel — model_dump() works natively."""
    stats = compute_window(make_sad_records(3))
    d = stats.model_dump()
    assert isinstance(d, dict)
    assert set(d.keys()) == {"avg_scores", "dominant_emotion", "volatility_score", "entry_count"}


def test_avg_scores_rounded_to_4dp():
    """Kaizen: avg_scores values are rounded to 4 decimal places at source."""
    # 1/3 ≈ 0.3333... — should be rounded to 4 dp
    records = [
        make_record({"sadness": 1 / 3}, entry_id=f"e{i}") for i in range(3)
    ]
    stats = compute_window(records)
    for score in stats.avg_scores.values():
        decimal_places = len(str(score).split(".")[-1])
        assert decimal_places <= 4, f"Score {score} has more than 4 decimal places"


def test_route_rejects_over_90_records():
    """Kaizen / Poka-Yoke: list > 90 records returns 422 (DoS guard)."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    payload = {
        "records": [
            {
                "user_id": "u1",
                "timestamp": "2024-01-01T10:00:00Z",
                "emotions": {"sadness": 0.8},
                "entry_id": f"e{i}",
            }
            for i in range(91)  # 91 > 90
        ]
    }
    response = client.post("/patterns/analyze", json=payload)
    assert response.status_code == 422


def test_route_accepts_exactly_90_records():
    """Boundary: exactly 90 records should be accepted (max_length inclusive)."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    payload = {
        "records": [
            {
                "user_id": "u1",
                "timestamp": "2024-01-01T10:00:00Z",
                "emotions": {"joy": 0.8},
                "entry_id": f"e{i}",
            }
            for i in range(90)
        ]
    }
    response = client.post("/patterns/analyze", json=payload)
    assert response.status_code == 200

