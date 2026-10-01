"""Executive Summary (IC Synthesis) — committee page from the fact register."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_ic_synthesis import (
    _heuristic_ic_synthesis_spec,
    build_ic_synthesis_spec,
    render_ic_synthesis_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-ic-1"
    slug = "deal-ic-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _prior_agents() -> dict:
    return {
        "company_background": {
            "spec": {
                "insight_snapshot": (
                    "Test3 Mobility Limited manufactures electric two-wheelers "
                    "with software services."
                ),
                "legal_name": "Test3 Mobility Limited",
            },
            "findings": [
                "Sells: Electric two-wheelers and connected software services.",
            ],
            "sources": ["overview.pdf"],
        },
        "deal_context_and_objectives": {
            "spec": {
                "insight_snapshot": "E2W manufacturer targeting vertical integration.",
                "overview": {
                    "transaction_type": "Growth equity diligence for a minority stake",
                    "deal_rationale": "Scale manufacturing and software differentiation",
                    "perimeter": "Minority equity stake under diligence",
                },
                "hypotheses": [
                    {"hypothesis": "Software differentiation supports retention"},
                ],
            },
            "findings": ["Target: Test3", "SAM expanding at 57.6% CAGR"],
        },
        "historical_performance": {
            "spec": {
                "trend_headline": (
                    "EBITDA trough was FY2023 (INR -933 Cr); losses narrowed "
                    "by FY2024E to INR -788 Cr. Revenue FY2024E +86% YoY."
                ),
                "performance_metrics": {
                    "revenue_fy2024_inr_cr": 4900.0,
                    "ebitda_fy2024_inr_cr": -788.0,
                    "gross_margin_fy2024_pct": 12.5,
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["EBITDA trough was FY2023"],
        },
        "revenue_quality": {
            "spec": {
                "retention_metrics": {"nrr_pct": 81.0},
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["NRR 81.0%"],
        },
        "cost_structure": {
            "spec": {
                "cost_metrics": {"gross_margin_pct": 12.5},
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["GM 12.5%"],
        },
        "growth_opportunities": {
            "spec": {
                "options": [
                    {
                        "option": "Battery localization",
                        "evidence_class": "evidenced",
                        "sizing": "margin path",
                    }
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["7 growth option(s)"],
        },
        "valuation_modeling": {
            "spec": {
                "final_valuation_range": {
                    "range_published": False,
                    "blockers": [{"name": "Net debt (capital structure)", "ready": False}],
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
            },
            "findings": ["Final range withheld — Net debt"],
        },
        "internal_risk": {
            "spec": {
                "key_person_exposure": [
                    {"person": "CEO", "what_depends": "Approvals and strategy"},
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["5 key-person exposure(s)"],
        },
    }


def test_ic_synthesis_prompt_book_listed() -> None:
    system = compose_system("ic_synthesis", sector="EV", geography="India")
    assert "ic_synthesis" in listed_agents()
    assert "executive_summary" in listed_agents()
    body = agent_prompt("ic_synthesis")
    assert "Ola" not in body and "SoftBank" not in body
    assert "fact register" in body.lower() or "registered" in body.lower()
    assert "not to invest" in body.lower() or "not to invest" in system.lower()
    assert "blocker" in body.lower()


def test_ic_synthesis_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_ic_synthesis.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_opening_uses_registered_figures() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    opening = " ".join(heur.get("opening_lines") or [])
    assert "4900" in opening or "INR" in opening
    assert "Growth equity" in opening or "proposed" in opening.lower() or "Proposed" in opening
    # Must not harvest free-form market findings as the proposed line
    assert "SAM" not in opening and "57.6%" not in opening


def test_proposed_from_overview_not_findings() -> None:
    priors = _prior_agents()
    # Strip overview so only findings remain — must not invent from SAM finding
    priors["deal_context_and_objectives"]["spec"]["overview"] = {}
    heur = _heuristic_ic_synthesis_spec(company="Test3", prior_agents=priors)
    proposed = (heur.get("opening_lines") or ["", "", ""])[2]
    assert "SAM" not in proposed
    assert "not stated" in proposed.lower() or "Proposed:" in proposed


def test_earnings_fallen_stated_in_opening() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    fin = heur.get("financial_picture") or {}
    assert fin.get("earnings_fallen_or_negative") is True
    opening = " ".join(heur.get("opening_lines") or []).lower()
    assert "trough" in opening or "loss" in opening or "-788" in opening or "negative" in opening


def test_case_depends_on_with_evidence_status() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    deps = heur.get("case_depends_on") or []
    assert 1 <= len(deps) <= 3
    for d in deps:
        assert d.get("source_agent")
        assert d.get("finding")
        assert d.get("evidence_status")


def test_blockers_have_owner_and_could_change() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    blockers = heur.get("blockers") or []
    assert blockers
    for b in blockers:
        assert b.get("item")
        assert b.get("owner")
        assert b.get("could_change")
        assert b.get("source_agent")


def test_recommendation_not_invest_when_blocked() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    rec = heur.get("recommendation") or {}
    assert rec.get("invest_recommended") is False
    stance = str(rec.get("stance") or "").lower()
    assert "diligence" in stance
    assert "invest" not in stance or "not invest" in stance
    assert heur.get("reliance_verdict") == "BLOCKED"
    # Dual-write go_no_go must not be bare Invest/Go
    go = str(heur.get("go_no_go") or "").lower()
    assert go != "go" and "invest" not in go.replace("not invest", "")


def test_no_invented_score() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    assert heur.get("overall_score_1_5") is None


def test_no_invest_language_in_markdown() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    md = render_ic_synthesis_markdown("Executive Summary", heur)
    assert "## 1. Opening" in md
    assert "## 5. Recommendation" in md
    low = md.lower()
    assert "we recommend invest" not in low
    assert "recommend to invest" not in low
    assert "invest recommended:** no" in low or "invest recommended:** no" in md.lower()
    assert "not to invest" in low or "not invest" in low


def test_render_dispatch() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    output = {
        "agent_key": "ic_synthesis",
        "agentName": "Executive Summary",
        "target_company": "Test3",
        "spec": heur,
        "sources": ["overview.pdf"],
    }
    md = render_agent_document("ic_synthesis", output)
    assert "Opening" in md
    assert "Case Depends On" in md


def test_build_prefer_heuristic() -> None:
    deal = _FakeDeal()
    spec = build_ic_synthesis_spec(
        deal,  # type: ignore[arg-type]
        prefer_heuristic=True,
        prior=_prior_agents(),
    )
    assert spec.get("composer") == "heuristic_ic_synthesis_v1"
    assert "historical_performance" in (spec.get("upstream_agents_used") or [])


def test_empty_prior_rework() -> None:
    heur = _heuristic_ic_synthesis_spec(company="Test3", prior_agents={})
    assert heur.get("quality_verdict") == "REWORK"
