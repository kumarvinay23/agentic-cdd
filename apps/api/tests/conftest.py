"""Ensure isolated SQLite DB for API tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "profile_gate: do not confirm the deal profile before the pipeline starts",
    )


@pytest.fixture(autouse=True)
def _confirm_profile_before_agents(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Existing agent tests start the pipeline directly. The product still requires a confirm."""
    if request.node.get_closest_marker("profile_gate"):
        yield
        return

    from agetic_cdd_api.routers_pipeline import schedule_pipeline_run as routed
    from agetic_cdd_api.services_deals import get_deal
    from agetic_cdd_api.services_deal_profile import confirm_profile

    def _wrapped(db, *, org_id: str, deal_id: str, **kwargs):
        deal = get_deal(db, org_id=org_id, deal_id=deal_id)
        confirm_profile(deal, {})
        return routed(db, org_id=org_id, deal_id=deal_id, **kwargs)

    monkeypatch.setattr("agetic_cdd_api.routers_pipeline.schedule_pipeline_run", _wrapped)
    yield


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
