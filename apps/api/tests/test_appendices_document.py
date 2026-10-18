"""Appendices (FV-08) — claim / evidence / citation audit trail."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_appendices import (
    _heuristic_appendices_spec,
    build_appendices_spec,
    render_appendices_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.pipeline_catalog import PHASE4_AGENT_KEYS, PIPELINE_PHASES
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents
from agetic_cdd_api.verdict_roles import role_by_slug


class _FakeDeal:
    id = "deal-ap-1"
    slug = "deal-ap-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _prior_agents() -> dict:
    return {
        "scope_and_methodology": {
            "spec": {
                "notes": [
                    "Web scraping excluded from this diligence scope.",
                    "Interview programme limited to management.",
                ],
                "exclusions": [
                    {"item": "Retail channel audit out of scope"},
                ],
                "questions": [
                    {
                        "question": "Provide signed auditor consent letter",
                        "required_records": "Auditor consent PDF",
                        "decision_effect": "Blocks reliance on audited figures",
                        "priority": "mandatory_pre_decision",
                        "owner": "Deal counsel",
                        "timing": "before IC",
                        "closure_test": "Consent letter on VDR",
                        "interim_treatment": "LIMITED on audited figures",
                    }
                ],
            },
            "findings": ["Scope excludes retail channel audit"],
            "sources": ["01_Scope_and_Methodology.pdf"],
        },
        "historical_performance": {
            "spec": {
                "trend_headline": (
                    "EBITDA trough was FY2023 (INR -933 Cr); losses narrowed "
                    "by FY2024E to INR -788 Cr."
                ),
                "performance_metrics": {
                    "revenue_fy2024_inr_cr": 4900.0,
                    "ebitda_fy2024_inr_cr": -788.0,
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["EBITDA trough was FY2023 (INR -933 Cr)"],
            "sources": ["Financials_FY24.xlsx"],
        },
        "cash_flow": {
            "spec": {
                "ebitda_to_cash_bridge": [
                    {"label": "EBITDA", "value": -788.0},
                    {"label": "WC change", "value": -120.0},
                    {"label": "Capex", "value": -200.0},
                    {"label": "FCF total", "value": -1108.0},
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
            },
            "findings": ["EBITDA→cash bridge stated"],
            "sources": ["Cash_Flow_Bridge.xlsx"],
        },
        "revenue_quality": {
            "spec": {
                "retention_metrics": {"nrr_pct": 81.0},
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["NRR 81.0%"],
            "sources": ["Cohort_Retention.xlsx"],
        },
        "recommendation": {
            "spec": {
                "decision_stage": "continue_diligence",
                "insight_snapshot": "Continue diligence — valuation range withheld.",
                "questions": [
                    {
                        "question": "Confirm net debt schedule",
                        "required_records": "Capital structure schedule",
                        "decision_effect": "Blocks final range publish",
                        "priority": "mandatory_pre_decision",
                        "owner": "Financial diligence lead",
                        "timing": "before IC",
                        "closure_test": "Net debt reconciled",
                        "interim_treatment": "BLOCKED on FVR",
                    }
                ],
            },
            "findings": ["Continue diligence on stated conditions"],
            "sources": ["Term_Sheet_Draft_v1.pdf"],
        },
        "ic_synthesis": {
            "spec": {
                "insight_snapshot": "Executive Summary — 3 thesis points; decision not supportable today.",
                "opening_lines": [
                    "Test3 manufactures electric two-wheelers.",
                    "Earnings negative / troughing.",
                    "Proposed: growth equity minority stake.",
                ],
            },
            "findings": ["Decision not supportable today"],
            "sources": ["01_Executive_Summary.txt"],
        },
    }


def test_appendices_prompt_book_listed() -> None:
    system = compose_system("appendices", sector="EV", geography="India")
    assert "appendices" in listed_agents()
    body = agent_prompt("appendices")
    assert "Ola" not in body and "SoftBank" not in body
    assert "claim" in body.lower()
    assert "citation" in body.lower()
    assert "availability" in body.lower() and "verification" in body.lower()
    assert "[DEAL_PERIMETER]" in body or "Deal perimeter" in body
    assert "not to invent" in body.lower() or "never invent" in body.lower() or (
        "do not invent" in body.lower()
    )
    assert "invest" in system.lower() or "invest" in body.lower()


def test_appendices_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_appendices.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_appendices_registered_in_phase4() -> None:
    assert "appendices" in PHASE4_AGENT_KEYS
    role = role_by_slug("appendices")
    assert role is not None
    assert role.code == "FV-08"
    assert role.name == "Appendices"
    assert "recommendation" in role.depends_on
    found = False
    for phase in PIPELINE_PHASES:
        for stage in phase.get("stages") or []:
            for agent in stage.get("agents") or []:
                if agent.get("agent_key") == "appendices":
                    assert agent.get("agentName") == "Appendices"
                    found = True
    assert found


def test_claim_and_evidence_registers() -> None:
    heur = _heuristic_appendices_spec(
        company="Test3",
        prior_agents=_prior_agents(),
        inventory={
            "documents": [
                {"filename": "Financials_FY24.xlsx", "version": "v3"},
                {"filename": "Cash_Flow_Bridge.xlsx"},
            ]
        },
    )
    claims = heur.get("claim_register") or []
    assert claims
    for c in claims:
        assert c.get("claim_id")
        assert c.get("text")
        assert c.get("source_category")
        assert c.get("locator")
    evidence = heur.get("evidence_register") or []
    assert evidence
    inventory = heur.get("source_inventory") or []
    assert any("Financials_FY24" in (r.get("locator") or "") for r in inventory)


def test_calculation_register_from_bridge() -> None:
    heur = _heuristic_appendices_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    calcs = heur.get("calculation_register") or []
    assert any("cash_flow" in (c.get("name") or "") for c in calcs)
    assert any(c.get("tolerance_status") for c in calcs)


def test_bidirectional_citation_and_availability() -> None:
    heur = _heuristic_appendices_spec(
        company="Test3",
        prior_agents=_prior_agents(),
        inventory={"documents": [{"filename": "Financials_FY24.xlsx"}]},
    )
    cite = heur.get("citation_check") or {}
    assert isinstance(cite.get("claim_to_source"), list)
    assert isinstance(cite.get("source_to_claim"), list)
    summary = cite.get("summary") or {}
    assert summary.get("claims_checked", 0) >= 1
    matrix = heur.get("availability_vs_verification") or []
    assert matrix
    assert any(
        "not verified" in (r.get("distinction") or "").lower()
        or r.get("verification") == "unverified"
        for r in matrix
    )


def test_open_requests_contradictions_exclusions() -> None:
    heur = _heuristic_appendices_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    reqs = heur.get("open_requests") or []
    assert any("auditor" in (q.get("question") or "").lower() for q in reqs) or any(
        "net debt" in (q.get("question") or "").lower() for q in reqs
    )
    exclusions = heur.get("exclusions") or []
    assert exclusions


def test_appendices_qa_and_questions() -> None:
    heur = _heuristic_appendices_spec(
        company="Test3",
        prior_agents=_prior_agents(),
        inventory={"documents": [{"filename": "Financials_FY24.xlsx"}]},
    )
    qa = heur.get("appendices_evidence_qa") or []
    assert qa
    by_check = {r["check"]: r["status"] for r in qa if isinstance(r, dict)}
    assert by_check.get("claim_register_present") == "PASS"
    assert by_check.get("evidence_register_present") == "PASS"
    assert by_check.get("bidirectional_citation_run") == "PASS"
    assert by_check.get("availability_vs_verification_stated") == "PASS"
    assert by_check.get("open_items_consolidated") == "PASS"
    assert by_check.get("no_invest_endorsement") == "PASS"
    assert isinstance(heur.get("questions"), list)
    assert heur.get("quality_verdict") == "PASS"


def test_no_invest_in_markdown() -> None:
    heur = _heuristic_appendices_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    md = render_appendices_markdown("Appendices", heur)
    assert "## 1. Claim Register" in md
    assert "## 5. Bidirectional Citation Check" in md
    assert "## 7. Availability vs Verification" in md
    assert "## 9. Questions" in md
    low = md.lower()
    assert "we recommend invest" not in low
    assert "availability is not verification" in low or "≠" in md or "not verified" in low


def test_render_dispatch() -> None:
    heur = _heuristic_appendices_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    output = {
        "agent_key": "appendices",
        "agentName": "Appendices",
        "target_company": "Test3",
        "spec": heur,
        "sources": ["Financials_FY24.xlsx"],
    }
    md = render_agent_document("appendices", output)
    assert "Claim Register" in md
    assert "Citation Check" in md


def test_build_prefer_heuristic() -> None:
    deal = _FakeDeal()
    spec = build_appendices_spec(
        deal,  # type: ignore[arg-type]
        prefer_heuristic=True,
        prior=_prior_agents(),
        index={"documents": [{"filename": "extra.pdf"}]},
    )
    assert spec.get("composer") == "heuristic_appendices_v1"
    assert spec.get("fv_code") == "FV-08"
    assert "historical_performance" in (spec.get("upstream_agents_used") or [])


def test_empty_prior_rework() -> None:
    heur = _heuristic_appendices_spec(company="Test3", prior_agents={})
    assert heur.get("quality_verdict") == "REWORK"
    assert heur.get("empty") is True
    qa = heur.get("appendices_evidence_qa") or []
    fails = [r for r in qa if isinstance(r, dict) and r.get("status") == "FAIL"]
    assert fails
    assert heur.get("questions")
