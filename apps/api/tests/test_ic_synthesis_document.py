"""Executive Summary (IC Synthesis) — committee page from the fact register."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_ic_synthesis import (
    _heuristic_ic_synthesis_spec,
    build_ic_synthesis_spec,
    render_ic_synthesis_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.pipeline_catalog import PIPELINE_PHASES
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents
from agetic_cdd_api.verdict_roles import role_by_slug


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
    assert "3" in body or "three" in body.lower()
    assert "counter-evidence" in body.lower() or "counter" in body.lower()
    assert "supportable" in body.lower()
    assert "[DEAL_PERIMETER]" in body or "Deal perimeter" in body


def test_ic_synthesis_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_ic_synthesis.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_ui_naming_executive_summary() -> None:
    role = role_by_slug("ic_synthesis")
    assert role is not None
    assert role.name == "Executive Summary"
    assert "IC Synthesis" in (role.spec_output or "")
    found = False
    for phase in PIPELINE_PHASES:
        for stage in phase.get("stages") or []:
            for agent in stage.get("agents") or []:
                if agent.get("agent_key") == "ic_synthesis":
                    assert agent.get("agentName") == "Executive Summary"
                    assert "IC Synthesis" in (agent.get("description") or "")
                    found = True
    assert found


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
    assert fin.get("direction")


def test_thesis_points_3_to_5_with_counter_evidence() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    thesis = heur.get("thesis_points") or []
    assert 3 <= len(thesis) <= 5
    # Legacy alias dual-write
    assert heur.get("case_depends_on") == thesis
    for d in thesis:
        assert d.get("source_agent")
        assert d.get("finding") or d.get("evidence")
        assert d.get("evidence_status")
        assert d.get("counter_evidence")
        assert not str(d.get("counter_evidence") or "").lower().startswith(
            "counter-evidence not yet"
        )


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


def test_decision_supportable_stated() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    ds = heur.get("decision_support") or {}
    assert "supportable_today" in ds
    assert ds.get("supportable_today") is False  # valuation blocker present
    assert isinstance(ds.get("prerequisites"), list)
    assert ds["prerequisites"]
    for p in ds["prerequisites"]:
        assert p.get("item")
        assert p.get("owner")
        assert p.get("effect")


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


def test_ic_synthesis_evidence_qa_and_questions() -> None:
    heur = _heuristic_ic_synthesis_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    qa = heur.get("ic_synthesis_evidence_qa") or []
    assert qa
    by_check = {r["check"]: r["status"] for r in qa if isinstance(r, dict)}
    assert by_check.get("opening_register_only") == "PASS"
    assert by_check.get("direction_of_travel_explicit") == "PASS"
    assert by_check.get("thesis_count_3_to_5") == "PASS"
    assert by_check.get("thesis_has_counter_evidence") == "PASS"
    assert by_check.get("blockers_owner_effect") == "PASS"
    assert by_check.get("decision_supportable_stated") == "PASS"
    assert by_check.get("no_invest_endorsement") == "PASS"
    assert isinstance(heur.get("questions"), list)


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
    assert "## 3. Thesis Points" in md
    assert "## 5. Decision Supportable Today" in md
    assert "## 6. Recommendation" in md
    assert "## 7. IC Synthesis Evidence QA" in md
    assert "## 8. Questions" in md
    assert "Counter-evidence:" in md
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
    assert "Thesis Points" in md
    assert "Decision Supportable" in md


def test_build_prefer_heuristic() -> None:
    deal = _FakeDeal()
    spec = build_ic_synthesis_spec(
        deal,  # type: ignore[arg-type]
        prefer_heuristic=True,
        prior=_prior_agents(),
    )
    assert spec.get("composer") == "heuristic_ic_synthesis_v1"
    assert "historical_performance" in (spec.get("upstream_agents_used") or [])
    assert spec.get("ui_name") == "Executive Summary"
    assert spec.get("also_known_as") == "IC Synthesis"


def test_empty_prior_rework() -> None:
    heur = _heuristic_ic_synthesis_spec(company="Test3", prior_agents={})
    assert heur.get("quality_verdict") == "REWORK"
    qa = heur.get("ic_synthesis_evidence_qa") or []
    fails = [r for r in qa if isinstance(r, dict) and r.get("status") == "FAIL"]
    assert fails
    assert heur.get("questions")
