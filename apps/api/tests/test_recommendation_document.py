"""Recommendations — DiligenceIQ findings converted to deal actions."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_recommendation import (
    _heuristic_recommendation_spec,
    build_recommendation_spec,
    render_recommendation_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-rec-1"
    slug = "deal-rec-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _prior_agents() -> dict:
    return {
        "market_risk": {
            "spec": {
                "price_vs_structure": [
                    {
                        "risk": "Subsidy reduction / FAME-III delay",
                        "classification": "Changes structure",
                        "protection": "Specific indemnity and/or condition precedent",
                    },
                    {
                        "risk": "OEM counter-attack",
                        "classification": "Changes price",
                        "protection": "Price / underwriting adjustment",
                    },
                ],
                "downside_cases": [
                    {"bound": "Claim / exposure INR 120 Cr (≈ USD 14.5M)"},
                ],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["11 external risk(s)"],
            "sources": ["legal.pdf"],
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
                        "weakness": "Systems maturity — ADAS",
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
        "revenue_quality": {
            "spec": {
                "retention_metrics": {"nrr_pct": 81.0, "grr_pct": 74.0},
                "quality_flags": ["NRR 81% below 90% durability threshold."],
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
            },
            "findings": ["NRR 81.0%"],
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
        "valuation_modeling": {
            "spec": {
                "earnings_basis": {
                    "metric": "Revenue",
                    "amount": 590.0,
                    "unit": "USD M",
                    "period": "FY2024E",
                },
                "final_valuation_range": {
                    "range_published": False,
                    "blockers": [{"name": "Net debt (capital structure)", "ready": False}],
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
            },
            "findings": ["Final range withheld — Net debt"],
        },
        "synergies": {
            "spec": {
                "buyer": {"named": False},
                "cannot_underwrite_reason": "No named acquirer — cannot underwrite",
                "quality_verdict": "PASS",
                "reliance_verdict": "BLOCKED",
            },
            "findings": ["No named acquirer"],
        },
    }


def test_recommendation_prompt_book_listed() -> None:
    system = compose_system("recommendation", sector="EV", geography="India")
    assert "recommendation" in listed_agents()
    body = agent_prompt("recommendation")
    assert "Ola" not in body and "SoftBank" not in body
    assert "condition" in body.lower() and "precedent" in body.lower()
    assert "hundred" in body.lower() or "100" in body
    assert "finding" in body.lower()


def test_recommendation_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_recommendation.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_every_action_names_finding() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
        sources=["legal.pdf"],
    )
    assert heur.get("empty") is False
    assert heur.get("quality_verdict") == "PASS"
    for row in heur.get("recommendations") or []:
        assert row.get("source_finding"), row
        assert row.get("source_agent"), row
        assert row.get("action_class") in {
            "price_adjustment",
            "deal_structure",
            "contractual_protection",
            "condition_precedent",
            "post_completion",
        }


def test_price_structure_protection_separated() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    assert heur.get("price_actions")
    assert heur.get("structure_actions") or heur.get("protection_actions")
    # OEM counter-attack → price; subsidy → structure/CP
    price_text = " ".join(a.get("action", "") for a in heur["price_actions"]).lower()
    assert "oem" in price_text or "price" in price_text or "nrr" in price_text
    cps = heur.get("conditions_precedent_structured") or []
    assert cps
    for cp in cps:
        assert cp.get("owner")
        assert cp.get("acceptance_test")


def test_day100_only_where_finding_requires() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    posts = heur.get("post_completion_actions") or []
    assert posts  # key-person + NRR programme
    for row in posts:
        assert row.get("source_finding")
        assert "day" in str(row.get("timing") or "").lower() or row.get("action_class") == "post_completion"
    plan = heur.get("hundred_day_plan") or []
    assert plan
    # No generic invented day-100 without finding
    for line in plan:
        assert "[" in line  # source agent tag


def test_open_items_block_or_carry() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    open_items = heur.get("open_items") or []
    assert open_items
    assert any(o.get("blocks_decision") for o in open_items)
    assert heur.get("reliance_verdict") == "BLOCKED"


def test_untraced_recommendation_deleted() -> None:
    # Empty prior → no actions (nothing to invent)
    heur = _heuristic_recommendation_spec(company="Test3", prior_agents={})
    assert heur.get("quality_verdict") == "REWORK"
    assert not (heur.get("recommendations") or [])


def test_no_invest_pass_language() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    md = render_recommendation_markdown("Recommendations", heur)
    low = md.lower()
    assert "recommend invest" not in low
    assert "recommend pass" not in low
    assert "## 1. Price Adjustments" in md
    assert "## 4. Conditions Precedent" in md
    assert "## 6. Still Open" in md


def test_quantify_or_state_gap() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    # Downside INR 120 Cr should appear as quantified price action
    prices = heur.get("price_actions") or []
    assert any(
        "120" in str(p.get("quantified_effect") or "") or "120" in str(p.get("source_finding") or "")
        for p in prices
    )
    # Some items explicitly cannot quantify yet
    assert any(
        p.get("cannot_quantify_reason") for p in prices
    ) or any(
        p.get("quantified_effect") and p.get("quantified_effect") != "N/A (data room did not provide it)"
        for p in prices
    )


def test_render_dispatch() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    output = {
        "agent_key": "recommendation",
        "agentName": "Recommendation",
        "target_company": "Test3",
        "spec": heur,
        "sources": ["legal.pdf"],
    }
    md = render_agent_document("recommendation", output)
    assert "Price Adjustments" in md
    assert "Conditions Precedent" in md


def test_build_prefer_heuristic() -> None:
    deal = _FakeDeal()
    spec = build_recommendation_spec(
        deal,  # type: ignore[arg-type]
        prefer_heuristic=True,
        prior=_prior_agents(),
    )
    assert spec.get("composer") == "heuristic_recommendation_v1"
    assert "market_risk" in (spec.get("upstream_agents_used") or [])


def test_legacy_dual_write_cps() -> None:
    heur = _heuristic_recommendation_spec(
        company="Test3",
        prior_agents=_prior_agents(),
    )
    cps = heur.get("conditions_precedent") or []
    assert cps
    assert all(isinstance(c, str) and c.startswith("CP:") for c in cps)
    assert all("owner:" in c for c in cps)
