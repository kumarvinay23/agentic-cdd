"""Strategic Direction — DiligenceIQ prompt-book growth-plan test."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_strategic_direction import (
    _heuristic_strategic_direction_spec,
    build_strategic_direction_spec,
    render_strategic_direction_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-sd-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"
    metadata = {
        "deal_perimeter": "standalone ops",
        "transaction_type": "majority buyout",
        "as_of_date": "2024-12-31",
        "decision_stage": "IC",
    }


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
    system = compose_system(
        "strategic_direction",
        sector="EV",
        geography="India",
        deal_perimeter="standalone ops",
        transaction_type="majority buyout",
        as_of_date="2024-12-31",
        decision_stage="IC",
    )
    assert "strategic_direction" in listed_agents()
    assert "Separate three things" in system
    assert "high-confidence" in system.lower() or "high confidence" in system.lower()
    assert "price, volume, mix" in system.lower()
    assert "board-approved budget" in system.lower()
    assert "synerg" in system.lower()
    body = agent_prompt("strategic_direction")
    assert "questions" in body.lower()
    assert "cash flow" in body.lower() or "capital structure" in body.lower()


def test_strategic_direction_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_strategic_direction.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


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
    assert "## 7. Strategic Direction Evidence QA" in md
    assert "## 8. Questions and Inputs Required" in md
    assert "## 9. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "does not recommend invest or pass" in md.lower()
    assert "high-confidence" in md.lower() or "high confidence" in md.lower()
    assert "Management ambition" in md
    assert "Board-approved budget" in md
    assert "Stand-alone / Synergy" in md
    assert any(leg.get("driver") == "overall (all legs)" for leg in heur["bridge"])
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    # Material funding/capacity gaps must not yield READY with high confidence language
    if any(
        "fund" in str(a.get("assumption", "")).lower()
        or "capacity" in str(a.get("assumption", "")).lower()
        for a in heur.get("untested_assumptions") or []
    ):
        assert heur.get("reliance_verdict") != "READY" or "untested" in str(
            heur.get("strategy_read", "")
        ).lower()


def test_sd_qa_questions_synergy_and_funding_priors() -> None:
    heur = _heuristic_strategic_direction_spec(
        company="Test3",
        corpus=_strategy_corpus(),
        sources=["01_Executive_Summary.pdf"],
        f01_spec={"investment_drivers": ["Volume scale"]},
        cash_flow_spec={"cash_metrics": {"closing_cash": "INR 850 cr"}},
        capital_structure_spec={"debt_total_usd_m": 150},
    )
    assert heur.get("cash_flow_prior_present") is True
    assert heur.get("capital_structure_prior_present") is True
    initiatives = heur.get("initiatives") or []
    assert initiatives
    assert all(
        isinstance(r, dict) and r.get("synergy_flag")
        for r in initiatives
        if isinstance(r, dict)
    )
    assert any(
        isinstance(r, dict) and "stand" in str(r.get("synergy_flag") or "").lower()
        for r in initiatives
    )
    qa = heur.get("sd_evidence_qa") or []
    checks = {r.get("check") for r in qa if isinstance(r, dict)}
    for need in (
        "three_case_separation",
        "bridge_drivers",
        "plan_vs_actual",
        "initiatives_complete",
        "funding_vs_cf_cs",
        "synergy_vs_standalone",
        "no_high_confidence_while_untested",
    ):
        assert need in checks
    fund_qa = next(r for r in qa if r.get("check") == "funding_vs_cf_cs")
    assert fund_qa.get("status") == "PASS"
    hc_qa = next(r for r in qa if r.get("check") == "no_high_confidence_while_untested")
    assert hc_qa.get("status") == "PASS"
    questions = heur.get("questions") or []
    # Questions only for FAILs — may be empty if pack is strong
    assert isinstance(questions, list)
    # Funding/capacity untested or open QA must not leave READY uncapped
    if any(isinstance(r, dict) and r.get("status") == "FAIL" for r in qa):
        assert heur.get("reliance_verdict") != "READY"


def test_render_agent_document_strategic_direction() -> None:
    output = {
        "agentName": "Strategic Direction",
        "target_company": "Test3",
        "sources": ["03_Investment_Thesis.pdf"],
        "document": (
            "# Strategic Direction\n\n"
            "## 1. Three Cases — Do Not Merge\n\n"
            "Seeded.\n\n"
            "## 9. Quality & Reliance\n\n"
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
        prefer_heuristic=True,
    )
    md = render_strategic_direction_markdown("Strategic Direction", spec)
    assert "## 2. Bridge" in md
    assert "## 5. Funding" in md
    assert "## 7. Strategic Direction Evidence QA" in md
    assert "## 9. Quality & Reliance" in md
    assert spec.get("composer") in {"heuristic_v1", "llm_v1"}
    assert isinstance(spec.get("deal_slots"), dict)
    assert spec.get("sd_evidence_qa")
