"""
tests/test_config.py
====================
Kaizen: configuration validation tests.
Verifies that Settings enforces correct bounds and provides safe defaults.
"""

import pytest
from pydantic import ValidationError


def test_settings_loads_with_defaults():
    """Settings can be instantiated with all defaults."""
    from app.core.config import Settings
    s = Settings()
    assert s.app_name == "Reflectra API"
    assert s.nlp_emotion_threshold == 0.1
    assert s.nlp_top_k == 5
    assert s.debug is False


def test_nlp_threshold_rejects_above_1():
    """Poka-Yoke: threshold > 1 must fail at config construction."""
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings(nlp_emotion_threshold=1.5)


def test_nlp_threshold_rejects_negative():
    """Poka-Yoke: negative threshold must fail."""
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings(nlp_emotion_threshold=-0.1)


def test_nlp_top_k_rejects_zero():
    """Poka-Yoke: top_k=0 returns no results — must fail at config."""
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings(nlp_top_k=0)


def test_nlp_threshold_boundary_0():
    """Boundary: threshold=0.0 is valid (include all labels)."""
    from app.core.config import Settings
    s = Settings(nlp_emotion_threshold=0.0)
    assert s.nlp_emotion_threshold == 0.0


def test_nlp_threshold_boundary_1():
    """Boundary: threshold=1.0 is valid (only perfect confidence)."""
    from app.core.config import Settings
    s = Settings(nlp_emotion_threshold=1.0)
    assert s.nlp_emotion_threshold == 1.0


def test_groq_key_empty_warns(caplog):
    """Kaizen: empty groq_api_key logs a WARNING (not silent failure)."""
    import logging
    from app.core.config import Settings
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        Settings(groq_api_key="")
    assert any("GROQ_API_KEY" in msg for msg in caplog.messages)


def test_groq_key_set_no_warning(caplog):
    """No warning when a real Groq key is set."""
    import logging
    from app.core.config import Settings
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        Settings(groq_api_key="gsk_fake-key-for-testing")
    assert not any("GROQ_API_KEY" in msg for msg in caplog.messages)
