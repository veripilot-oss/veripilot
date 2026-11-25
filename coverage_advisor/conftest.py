"""Pytest configuration for coverage_advisor tests.

Ensures LLM environment variables are cleared for every test so no test
accidentally makes a real network request.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "VERIPILOT_LLM_API_KEY",
        "VERIPILOT_LLM_BASE_URL",
        "VERIPILOT_LLM_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
