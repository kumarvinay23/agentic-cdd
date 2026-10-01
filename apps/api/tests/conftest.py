"""Ensure isolated SQLite DB for API tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_TEST_DB = Path(__file__).resolve().parent / "_pytest_agetic.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()

os.environ["AGETIC_CDD_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ.setdefault("AGETIC_CDD_JWT_SECRET", "test-secret-agetic-cdd-jwt-32bytes!!")
os.environ.setdefault("AGETIC_CDD_SEED_ADMIN_EMAIL", "admin@ageticcdd.com")
os.environ.setdefault("AGETIC_CDD_SEED_ADMIN_PASSWORD", "adminpass")
# Keep document tests deterministic / offline unless a test opts into Gemini.
os.environ["AGETIC_CDD_DOCUMENT_SYNTHESIS_LLM"] = "false"
os.environ["AGETIC_CDD_GEMINI_API_KEY"] = ""


@pytest.fixture(autouse=True)
def _offline_web_research(request: pytest.FixtureRequest):
    """Default: no live web I/O. Opt out with @pytest.mark.live_web."""
    if request.node.get_closest_marker("live_web"):
        yield
        return

    def _stub_research_web(
        *,
        prompt: str,
        subject: str,
        capability: dict[str, Any],
        limit: int = 6,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        return [], [f"{subject} stub"]

    with patch(
        "agetic_cdd_api.services_document_runner.research_web",
        side_effect=_stub_research_web,
    ):
        yield


def pytest_sessionfinish() -> None:
    if _TEST_DB.exists():
        _TEST_DB.unlink()
