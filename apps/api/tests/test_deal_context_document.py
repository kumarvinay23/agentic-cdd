"""Deal Context prompt-book document — DiligenceIQ house rules + agent prompt."""

from __future__ import annotations

from agetic_cdd_api.agent_document_deal_context import (
    build_deal_context_spec,
    render_deal_context_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import compose_system, house_rules, listed_agents


class _FakeDeal:
    id = "deal-dc-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _ola_index() -> dict:
    excerpt = (
        "Legal Name Ola Electric Mobility Limited. Indian electric two-wheeler market. "
        "Line Item FY2021 FY2022 FY2023 FY2024E FY2025E "
        "Revenue 8 456 2,630 4,900 8,200. EBITDA still negative. "
        "Market share of 35%. Revenue CAGR of 120%. "
        "Total Headcount (FTE) 3,200 8,500 9,800. "
        "Acquisition growth equity investment thesis. FAME-II subsidy noted."
    )
    return {
        "document_count": 3,
        "category_counts": {
            "deal_strategy": 1,
            "company_management": 1,
            "financial": 1,
            "market_competition": 1,
        },
        "documents": [
            {
                "filename": "01_Executive_Summary.pdf",
                "cdl_category": "deal_strategy",
                "excerpt": excerpt,
            },
            {
                "filename": "05_Financial_Due_Diligence.pdf",
                "cdl_category": "financial",
                "excerpt": excerpt,
            },
            {
                "filename": "02_Corporate_Overview.pdf",
                "cdl_category": "company_management",
                "excerpt": excerpt,
            },
        ],
    }


def test_compose_system_prepends_house_rules() -> None:
    system = compose_system(
        "deal_context_and_objectives",
        sector="Electric Two-Wheelers",
        geography="India",
        materiality="₹50 cr",
    )
    rules = house_rules(materiality="₹50 cr", sector="Electric Two-Wheelers", geography="India")
    assert system.startswith(rules[:80])
    assert "WHERE TO LOOK" in system
    assert "deal_context_and_objectives" in listed_agents()
    assert "Do not issue an investment verdict" in system
    assert "Electric Two-Wheelers" in system
    assert "₹50 cr" in system
    # House rules appear once (not duplicated inside agent body).
    assert system.count("WHERE TO LOOK, IN THIS ORDER") == 1


def test_deal_context_markdown_follows_prompt_book() -> None:
    corpus = (
        _ola_index()["documents"][0]["excerpt"]
        + " "
        + _ola_index()["documents"][1]["excerpt"]
    )
    spec = build_deal_context_spec(
        _FakeDeal(),
        index=_ola_index(),
        company="Test3",
    )
    # Force heuristic path for deterministic assertions when Gemini is off —
    # build may call Gemini; if so, still assert render contract.
    from agetic_cdd_api.agent_document_deal_context import _heuristic_deal_context_spec

    heur = _heuristic_deal_context_spec(
        company="Test3",
        corpus=corpus,
        sources=[d["filename"] for d in _ola_index()["documents"]],
        document_count=3,
    )
    md = render_deal_context_markdown("Deal Context & Objectives", heur)

    assert "## 1. Executive Summary" in md
    assert "## 2. Key Investment Hypotheses (Must-Be-True)" in md
    assert "## 5. Headline Fact Ledger" in md
    assert "## 6. Quality & Reliance" in md
    assert "Preliminary Investment Verdict" not in md
    assert "Invest in Test3" not in md
    assert "**Quality:**" in md
    assert "**Reliance:**" in md
    assert "Legal Entity" in md
    assert "Perimeter" in md
    assert "Fail Threshold" in md or "threshold" in md.lower()
    assert "Source Locator" in md
    assert len(heur.get("fact_ledger") or []) >= 15
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    # Sanity: build_deal_context_spec returns a renderable spec
    rendered = render_deal_context_markdown("Deal Context & Objectives", spec)
    assert "## 1. Executive Summary" in rendered
    assert "Preliminary Investment Verdict" not in rendered


def test_render_agent_document_deal_context_prefers_quality_section() -> None:
    output = {
        "agentName": "Deal Context & Objectives",
        "target_company": "Test3",
        "document": (
            "# Deal Context & Objectives\n\n"
            "## 5. Headline Fact Ledger\n\n"
            "facts\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("deal_context_and_objectives", output)
    assert "## 6. Quality & Reliance" in rendered
    assert "Preliminary Investment Verdict" not in rendered
