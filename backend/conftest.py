"""
conftest.py — Root pytest configuration
=========================================
Adds the backend directory to sys.path so ``from app.xxx import yyy``
works without setting PYTHONPATH=. manually each time.

Markers
-------
  integration — tests that call live external APIs (HuggingFace, ChromaDB).
                Skipped in fast CI with: pytest -m "not integration"
"""
import sys
import os

import pytest

# Insert the backend root (directory containing this file) at the front of
# sys.path so all "from app.xxx import yyy" imports resolve correctly.
sys.path.insert(0, os.path.dirname(__file__))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that call live external services "
        "(deselect with: -m 'not integration')",
    )
