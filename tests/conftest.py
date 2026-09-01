"""
conftest.py — Shared pytest fixtures and test configuration.

Key concern: FormatSkill calls Gemini (LLM) if GEMINI_API_KEY is set.
Tests must be deterministic and offline. This conftest patches LLMService
so NO real Gemini API calls are made during pytest runs.

Why disable LLM in tests:
  • Deterministic — same result every run regardless of network/quota
  • Fast          — no 1-2s round trips per FormatSkill test
  • Offline       — works in CI environments without credentials

The real Gemini integration is verified by running demo.py manually.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_null_llm() -> MagicMock:
    """Create a mock LLMService that reports unavailable and returns None for all calls."""
    mock = MagicMock()
    mock.is_available.return_value = False
    mock.generate.return_value = None
    mock.clarify_request.return_value = None
    mock.enhance_clarification_questions.return_value = None
    mock.summarise_readiness.return_value = None
    return mock


@pytest.fixture(autouse=True, scope="session")
def patch_llm_for_tests():
    """
    Session-scoped fixture: patches the LLM service OFF for the entire test suite.

    Patches the get_llm_service function in every module that imports it,
    so no real Gemini API calls are made regardless of .env settings.
    """
    null_llm = _make_null_llm()
    null_llm_factory = lambda api_key=None, **kwargs: null_llm  # noqa: E731

    with patch("app.services.llm_service.get_llm_service", null_llm_factory):
        with patch("app.skills.format_skill.get_llm_service", null_llm_factory):
            with patch("app.agents.planner_agent.get_llm_service", null_llm_factory):
                yield null_llm
