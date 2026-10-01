"""Strategic Direction — DiligenceIQ prompt-book growth-plan test."""

from __future__ import annotations

from agetic_cdd_api.agent_document_strategic_direction import (
    _heuristic_strategic_direction_spec,
    build_strategic_direction_spec,
    render_strategic_direction_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import compose_system, listed_agents


class _FakeDeal:
    id = "deal-sd-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _strategy_corpus() -> str:
    return (
        "01 Executive Summary Investment Overview. "
        "Management ambition: path to FY2028E scale via volume and software mix. "
        "Board approved FY2025 budget guidance Revenue 4,200 cr. "
        "FY 2021 FY 2022 FY 2023 FY 2024E FY 2025E "
        "Revenue 1,200 2,100 3,000 3,800 4,800 "
        "EBITDA (140) 80 220 380 520. "
        "CAGR of approximately 32% from FY2023 to FY2025E. "
        "Gross Margin > 25% FY2025E. EBITDA > 12% FY2026E. "
        "Capacity Localization Localization of battery packs by FY2026E. "
        "New geography export push into ASEAN. Acquisition not in base case. "
        "Price and volume drivers underpin the plan; mix shift to software. "
        "Cash balance INR 850 cr. Total debt INR 1,200 cr senior facilities. "
        "FY2023 target Revenue 2,800 cr vs actual revenue trajectory. "
        "FY2022 budget guidance Revenue 1,900 cr. "
        "Stand-alone growth funded from operating cash; no buyer contribution assumed."
    )


def test_strategic_direction_prompt_book_listed() -> None:
    system = compose_system("strategic_direction", sector="EV", geography="India")
    assert "strategic_direction" in listed_agents()
    assert "Separate three things" in system
    assert "high-confidence" in system.lower() or "high confidence" in system.lower()
    assert "price, volume, mix" in system.lower()
    assert "board-approved budget" in system.lower()


def test_strategic_direction_markdown_follows_prompt_book() -> None:
    f01 = {
        "investment_drivers": [
            "Volume scale — two-wheeler unit growth",
            "Mix — software and services attach",
            "Localization — battery cost reduction",
        ],
        "must_be_true": ["Gross margin expands with localization"],
        "deal_breaker_risks": ["Funding gap vs capacity build"],
        "attractiveness_score": 7,
    }
    heur = _heuristic_strategic_direction_spec(
        company="Test3",
        corpus=_strategy_corpus(),
        sources=["01_Executive_Summary.pdf", "03_Investment_Thesis.pdf"],
        f01_spec=f01,
    )
    md = render_strategic_direction_markdown("Strategic Direction", heur)

    assert "## 1. Three Cases" in md
    assert "## 2. Bridge" in md
    assert "## 3. Plan vs Actual" in md
    assert "## 4. Initiatives" in md
    assert "## 5. Funding Reconciliation" in md
    assert "## 6. Assumptions" in md
    assert "## 7. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "does not recommend invest or pass" in md.lower()
    assert "high-confidence" in md.lower() or "high confidence" in md.lower()
    assert "Management ambition" in md
    assert "Board-approved budget" in md
    assert any(leg.get("driver") == "overall (all legs)" for leg in heur["bridge"])
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    # Material funding/capacity gaps must not yield READY with high confidence language
    if any("fund" in str(a.get("assumption", "")).lower() or "capacity" in str(a.get("assumption", "")).lower()
           for a in heur.get("untested_assumptions") or []):
        assert heur.get("reliance_verdict") != "READY" or "untested" in str(heur.get("strategy_read", "")).lower()


def test_render_agent_document_strategic_direction() -> None:
    output = {
        "agentName": "Strategic Direction",
        "target_company": "Test3",
        "sources": ["03_Investment_Thesis.pdf"],
        "document": (
            "# Strategic Direction\n\n"
            "## 1. Three Cases — Do Not Merge\n\n"
            "Seeded.\n\n"
            "## 7. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("strategic_direction", output)
    assert "## 1. Three Cases" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_strategic_direction_from_f01_only() -> None:
    spec = build_strategic_direction_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "03_Investment_Thesis.pdf",
                    "cdl_category": "deal_strategy",
                    "excerpt": _strategy_corpus(),
                }
            ],
            "category_counts": {"deal_strategy": 1},
        },
        company="Test3",
        f01_spec={
            "investment_drivers": ["Volume scale"],
            "must_be_true": [],
            "deal_breaker_risks": [],
        },
    )
    md = render_strategic_direction_markdown("Strategic Direction", spec)
    assert "## 2. Bridge" in md
    assert "## 5. Funding" in md
    assert spec.get("composer") in {"heuristic_v1", "llm_v1"}
