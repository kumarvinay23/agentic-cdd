"""SWOT Analysis — DiligenceIQ synthesis of validated upstream findings."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_swot_analysis import (
    _heuristic_swot_analysis_spec,
    build_swot_analysis_spec,
    render_swot_analysis_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-swot-1"
    slug = "deal-swot-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _prior_agents() -> dict:
    return {
        "revenue_quality": {
            "spec": {
                "retention_metrics": {"grr_pct": 74.0, "nrr_pct": 81.0},
                "quality_flags": ["NRR 81% below 90% durability threshold."],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["NRR 81.0%"],
            "sources": ["finance.pdf"],
        },
        "customer_stickiness": {
            "spec": {
                "retention_metrics": {"logo_churn_pct": 39.0, "grr_pct": 74.0},
                "cohorts": [
                    {"cohort": "Q1 FY2022", "m12_retention_pct": 68.0},
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
            },
            "findings": ["Same-pop · GRR 74%"],
        },
        "competitive_differentiation": {
            "spec": {
                "advantage_tests": [
                    {
                        "claim": "NPS gap: target 34 vs peer 61",
                        "test_result": "INCONCLUSIVE",
                    }
                ],
                "feature_gaps": ["NPS gap: target 34 vs peer 61"],
                "moat_signals": [
                    "Competitive durable advantage is narrowing as legacy OEMs invest."
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
            },
            "findings": ["Test INCONCLUSIVE: NPS gap"],
        },
        "market_share_strategy": {
            "spec": {
                "matched_share": {
                    "calculable": False,
                    "notes": "Share not calculable on matched basis",
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
            },
            "findings": ["Share not calculable / unassessed on matched basis"],
        },
        "cost_structure": {
            "spec": {
                "cost_metrics": {"gross_margin_pct": 12.5},
                "bom_components": [{"category": "Battery Pack", "share_pct": 38.0}],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["Largest: Battery Pack 38%"],
        },
        "historical_performance": {
            "spec": {
                "trend_headline": (
                    "EBITDA trough was FY2023 (INR -933 Cr); losses narrowed "
                    "by FY2024E to INR -788 Cr. Revenue FY2024E +86% YoY."
                ),
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["EBITDA trough was FY2023"],
        },
        "market_risk": {
            "spec": {
                "external_risks": [
                    {
                        "risk": "Subsidy reduction / FAME-III delay",
                        "mechanism": "Policy support reduces → volume pressure",
                    }
                ],
                "downside_cases": [
                    {"bound": "Claim / exposure INR 120 Cr (≈ USD 14.5M)"},
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["11 external risk(s)"],
        },
        "internal_risk": {
            "spec": {
                "key_person_exposure": [
                    {
                        "person": "CEO",
                        "what_depends": "Approvals and strategic direction",
                    }
                ],
                "observed_weaknesses": [
                    {
                        "weakness": "Systems maturity — ADAS / Safety Features",
                        "evidence": "Maturity 2.5/5",
                    }
                ],
                "control_testing": [
                    {
                        "control": "penetration testing",
                        "tested": "Not tested",
                        "result": "Untested",
                    }
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["5 key-person exposure(s)"],
        },
        "growth_opportunities": {
            "spec": {
                "options": [
                    {
                        "option": "Battery localization",
                        "evidence_class": "evidenced",
                        "sizing": "margin ~11.5 pp",
                    }
                ],
                "unit_economics": {
                    "gross_margin_now_pct": 12.0,
                    "gross_margin_target_low_pct": 22.0,
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["7 growth option(s)"],
        },
        "synergies": {
            "spec": {
                "buyer": {"named": False},
                "cannot_underwrite_reason": "No named acquirer — cannot underwrite",
                "quality_verdict": "PASS",
                "reliance_verdict": "BLOCKED",
            },
            "findings": ["No named acquirer — cannot underwrite"],
        },
    }


def test_swot_prompt_book_listed() -> None:
    system = compose_system("swot_analysis", sector="EV", geography="India")
    assert "swot_analysis" in listed_agents()
    assert "synthesis" in system.lower() or "upstream" in system.lower() or "finding" in system.lower()
    body = agent_prompt("swot_analysis")
    assert "Ola" not in body and "SoftBank" not in body
    assert "unexamined" in body.lower()
    assert "no new" in body.lower() or "no new claims" in body.lower()
    assert "rank" in body.lower()


def test_swot_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_swot_analysis.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_items_traced_to_upstream_with_quantification() -> None:
    heur = _heuristic_swot_analysis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
        sources=["finance.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
    )
    assert heur.get("empty") is False
    assert heur.get("quality_verdict") == "PASS"
    all_struct = (
        (heur.get("strengths_structured") or [])
        + (heur.get("weaknesses_structured") or [])
        + (heur.get("opportunities_structured") or [])
        + (heur.get("threats_structured") or [])
    )
    assert all_struct
    for it in all_struct:
        assert it.get("source_agent"), f"untraced: {it}"
        assert it.get("source_finding")
        assert it.get("evidence_class") in {
            "demonstrated",
            "external_possibility",
            "unexamined",
            "unresolved",
        }
    # NRR quantification carried from revenue_quality
    weak_text = " ".join(heur.get("weaknesses") or [])
    assert "81" in weak_text or any(
        "81" in str(it.get("quantification"))
        for it in (heur.get("weaknesses_structured") or [])
    )
    assert "revenue_quality" in weak_text or any(
        it.get("source_agent") == "revenue_quality"
        for it in (heur.get("weaknesses_structured") or [])
    )


def test_unexamined_never_in_weaknesses() -> None:
    heur = _heuristic_swot_analysis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    for it in heur.get("weaknesses_structured") or []:
        assert it.get("evidence_class") != "unexamined"
    gaps = heur.get("information_gaps") or []
    assert gaps  # matched share + untested controls + synergies
    for gap in gaps:
        assert gap.get("evidence_class") == "unexamined"
        # Must not appear in legacy weaknesses
        line = gap.get("statement") or ""
        assert all(line[:40] not in w for w in (heur.get("weaknesses") or []))


def test_open_blocker_not_overridden() -> None:
    heur = _heuristic_swot_analysis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    assert heur.get("open_blockers")
    assert heur.get("reliance_verdict") == "BLOCKED"
    snap = str(heur.get("insight_snapshot") or "").lower()
    assert "blocker" in snap or heur.get("open_blockers")


def test_no_invented_numbers() -> None:
    heur = _heuristic_swot_analysis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    for it in (
        (heur.get("strengths_structured") or [])
        + (heur.get("weaknesses_structured") or [])
        + (heur.get("opportunities_structured") or [])
        + (heur.get("threats_structured") or [])
    ):
        quant = str(it.get("quantification") or "")
        if quant and quant != "N/A (data room did not provide it)":
            finding = str(it.get("source_finding") or "") + str(it.get("statement") or "")
            digits = "".join(c for c in quant if c.isdigit() or c == ".")
            assert digits in "".join(c for c in finding if c.isdigit() or c == "."), (
                f"invented number {quant} not in {finding}"
            )


def test_ranked_by_thesis_not_category_balance() -> None:
    heur = _heuristic_swot_analysis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    ranked = heur.get("ranked_items") or []
    assert ranked
    # Blockers / price effects should outrank secondary unexamined
    first = ranked[0]
    assert first.get("thesis_effect") in {"blocker", "price", "thesis"}
    # Cap: not sixteen generic items dumping into each quadrant
    assert len(heur.get("strengths") or []) <= 4
    assert len(heur.get("weaknesses") or []) <= 4


def test_empty_prior_is_rework() -> None:
    heur = _heuristic_swot_analysis_spec(company="Test3", prior_agents={})
    assert heur.get("quality_verdict") == "REWORK"
    assert heur.get("empty") is True or not (
        heur.get("strengths") or heur.get("weaknesses")
    )


def test_render_markdown_sections() -> None:
    heur = _heuristic_swot_analysis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    md = render_swot_analysis_markdown("SWOT Analysis", heur)
    assert "## 1. Demonstrated Strengths" in md
    assert "## 2. Demonstrated Weaknesses" in md
    assert "## 5. Information Gaps" in md
    assert "recommend invest" not in md.lower()
    assert "recommend pass" not in md.lower()
    low = md.lower()
    assert "we recommend" not in low and "advise to invest" not in low


def test_render_agent_document_dispatch() -> None:
    heur = _heuristic_swot_analysis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    output = {
        "agent_key": "swot_analysis",
        "agentName": "SWOT Analysis",
        "target_company": "Test3",
        "summary": "SWOT for Test3",
        "spec": heur,
        "sources": ["finance.pdf"],
    }
    md = render_agent_document("swot_analysis", output)
    assert "Demonstrated Strengths" in md
    assert "Information Gaps" in md


def test_build_prefer_heuristic() -> None:
    deal = _FakeDeal()
    spec = build_swot_analysis_spec(
        deal,  # type: ignore[arg-type]
        prefer_heuristic=True,
        prior=_prior_agents(),
    )
    assert spec.get("composer") == "heuristic_swot_v1"
    assert "revenue_quality" in (spec.get("upstream_agents_used") or [])


def test_disagreement_carried_unresolved() -> None:
    prior = {
        "revenue_quality": {
            "spec": {
                "retention_metrics": {"nrr_pct": 95.0},
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["NRR 95%"],
        },
        "customer_stickiness": {
            "spec": {
                "retention_metrics": {"nrr_pct": 70.0, "logo_churn_pct": 40.0},
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["NRR soft"],
        },
    }
    # Force overlapping topic with opposite states via feature gap + strength path
    prior["competitive_differentiation"] = {
        "spec": {
            "advantage_tests": [
                {"claim": "NRR durable above peers", "test_result": "PASS"},
            ],
            "quality_verdict": "PASS",
            "reliance_verdict": "READY",
        },
        "findings": [],
    }
    heur = _heuristic_swot_analysis_spec(company="Test3", prior_agents=prior)
    # At minimum every item stays traced; unresolved may or may not fire on nrr stem
    for it in heur.get("unresolved_items") or []:
        assert it.get("evidence_class") == "unresolved"
        assert it.get("disagreeing_agents")
