"""Customer Stickiness — DiligenceIQ prompt-book retention & contracts."""

from __future__ import annotations

from agetic_cdd_api.agent_document_customer_stickiness import (
    _heuristic_customer_stickiness_spec,
    _normalise_llm_spec,
    _retention_moved,
    build_customer_stickiness_spec,
    render_customer_stickiness_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import (
    agent_prompt,
    compose_system,
    listed_agents,
    questions_complete,
)


class _FakeDeal:
    id = "deal-stick-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _stick_corpus() -> str:
    return (
        "Population: logos (paying customers), held constant across periods. "
        "Opening ARR INR 412 cr. Churned revenue INR 108 cr. Contraction INR 20 cr. "
        "Expansion INR 45 cr. Closing ARR INR 329 cr. New customers excluded from "
        "retention numerators. "
        "Gross Revenue Retention (GRR) 74%. Net Revenue Retention (NRR) 81%. "
        "Logo Churn 39%. 12-Month Customer Retention Rate 61%. "
        "GRR fell from 82% to 74% year on year. "
        "Q1 FY2022 (Launch Cohort) 4,200 82% 68% 41%. "
        "Q1 FY2023 3,100 79% 62%. "
        "Loss reason: Service Delay 28% Critical — concentrates in Fleet Operator. "
        "Largest customer Metro Fleet Holdings: 3-year term, auto-renewal, 90-day notice, "
        "minimum commitment INR 4cr/yr, CPI price escalator, termination for convenience "
        "with 90-day notice. "
        "Renewal cliff: ~22% of revenue comes up for renewal in the next 12 months. "
        "Customers who stayed are not the same as customers who are contractually committed."
    )


def _thin_corpus() -> str:
    return (
        "Management asserts strong stickiness. No retention workbook opened. "
        "No bridge, cohorts or contracts provided."
    )


def test_customer_stickiness_prompt_book_listed() -> None:
    system = compose_system("customer_stickiness", sector="EV", geography="India")
    assert "customer_stickiness" in listed_agents()
    assert "retention" in system.lower()
    assert "questions" in system.lower()
    assert "[DEAL_PERIMETER]" in system or "Deal perimeter" in system
    body = agent_prompt("customer_stickiness")
    assert "Ola" not in body and "SoftBank" not in body
    assert "gross revenue retention" in body.lower() or "grr" in body.lower()
    assert "finding" in body.lower()
    assert "contract" in body.lower()
    assert "new" in body.lower() and "exclud" in body.lower()


def test_customer_stickiness_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_customer_stickiness.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("customer_stickiness")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_retention_moved_falling_is_finding() -> None:
    direction, magnitude, is_finding = _retention_moved(82, 74, metric="grr")
    assert direction == "down"
    assert is_finding is True
    assert "8" in magnitude or "pp" in magnitude.lower()


def test_customer_stickiness_markdown_follows_prompt_book() -> None:
    heur = _heuristic_customer_stickiness_spec(
        company="Test3",
        corpus=_stick_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec={
            "retention_metrics": {"grr_pct": 74.0, "nrr_pct": 81.0},
            "cohorts": [
                {
                    "cohort": "Q1 FY2022",
                    "size_units": 4200.0,
                    "m6_retention_pct": 82.0,
                    "m12_retention_pct": 68.0,
                    "m36_retention_pct": 41.0,
                }
            ],
            "stickiness_notes": ["Legacy stickiness note"],
        },
    )
    md = render_customer_stickiness_markdown("Customer Stickiness", heur)

    assert "## 1. Population" in md
    assert "## 2. Retention Bridge" in md
    assert "## 3." in md
    assert "## 4. Contract" in md
    assert "## 5. Behaviour" in md or "## 5. Behavior" in md
    assert "## 6. New-Logo Exclusion QA" in md
    assert "## 7. Questions and Inputs Required" in md
    assert "## 8. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    metrics = heur.get("retention_metrics") or {}
    assert metrics.get("grr_pct") == 74.0 or metrics.get("grr_pct") == 74
    assert isinstance(heur.get("cohorts"), list) and heur["cohorts"]
    deltas = heur.get("retention_delta") or []
    assert any(isinstance(d, dict) and d.get("is_finding") for d in deltas)
    assert "finding" in md.lower() or any(d.get("is_finding") for d in deltas)
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert isinstance(heur.get("stickiness_notes"), list)
    qa = heur.get("new_logo_exclusion_qa") or []
    assert any(isinstance(r, dict) and r.get("check") == "new_logo_exclusion" for r in qa)
    assert any(
        isinstance(r, dict)
        and r.get("check") == "new_logo_exclusion"
        and r.get("status") == "PASS"
        for r in qa
    )
    assert heur.get("questions")
    assert questions_complete(heur["questions"])


def test_new_logo_exclusion_qa_fails_without_confirmation() -> None:
    heur = _heuristic_customer_stickiness_spec(
        company="Test3",
        corpus=_thin_corpus(),
        sources=["mgmt.pdf"],
    )
    qa = heur.get("new_logo_exclusion_qa") or []
    assert any(
        isinstance(r, dict)
        and r.get("check") == "new_logo_exclusion"
        and r.get("status") == "FAIL"
        for r in qa
    )
    assert heur.get("questions")
    assert questions_complete(heur["questions"])
    assert any(
        "new logo" in str(q.get("question") or "").lower()
        or "exclud" in str(q.get("question") or "").lower()
        for q in heur["questions"]
        if isinstance(q, dict)
    )
    md = render_customer_stickiness_markdown("Customer Stickiness", heur)
    assert "## 6. New-Logo Exclusion QA" in md
    assert "FAIL" in md


def test_normalise_strips_recommendation() -> None:
    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Retention looks fine — invest",
            "population_definition": {"population": "logos"},
            "cohorts": [],
            "retention_bridge": {},
            "retention_metrics": {"grr_pct": 74, "nrr_pct": 81},
            "retention_delta": [
                {
                    "metric": "GRR",
                    "from_value": "82%",
                    "to_value": "74%",
                    "direction": "flat",
                    "is_finding": False,
                }
            ],
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        sources=["a.pdf"],
        legacy_spec=None,
        corpus="GRR fell from 82% to 74%.",
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()
    deltas = llm.get("retention_delta") or []
    if deltas:
        assert any(
            isinstance(d, dict) and (d.get("is_finding") or d.get("direction") == "down")
            for d in deltas
        )
    assert llm.get("new_logo_exclusion_qa")
    assert llm.get("questions")
    assert questions_complete(llm["questions"])


def test_render_agent_document_customer_stickiness() -> None:
    output = {
        "agentName": "Customer Stickiness",
        "target_company": "Test3",
        "sources": ["13_Valuation_Retention_Comparable_Analysis.pdf"],
        "document": (
            "# Customer Stickiness\n\n"
            "## 1. Population & Cohorts\n\n"
            "Seeded.\n\n"
            "## 8. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("customer_stickiness", output)
    assert "## 1. Population" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_customer_stickiness_from_corpus() -> None:
    spec = build_customer_stickiness_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "13_Valuation_Retention_Comparable_Analysis.pdf",
                    "cdl_category": "customer",
                    "excerpt": _stick_corpus(),
                }
            ],
            "category_counts": {"customer": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_customer_stickiness_markdown("Customer Stickiness", spec)
    assert "## 2. Retention Bridge" in md
    assert "## 6. New-Logo Exclusion QA" in md
    assert "## 7. Questions" in md
    assert "## 8. Quality & Reliance" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-11"
    assert spec.get("questions")
    assert questions_complete(spec["questions"])
    assert spec.get("deal_slots")
    assert spec.get("new_logo_exclusion_qa")
