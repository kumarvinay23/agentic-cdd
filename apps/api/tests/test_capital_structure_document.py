"""Capital Structure — DiligenceIQ prompt-book funding position."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_capital_structure import (
    _heuristic_capital_structure_spec,
    build_capital_structure_spec,
    render_capital_structure_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-cap-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _cap_corpus() -> str:
    return (
        "Debt schedule. Total debt USD 240M. "
        "Senior Term Loan A — USD 85M. "
        "Senior Term Loan B — USD 45M. "
        "Mezzanine Notes — USD 30M. "
        "Equipment Finance Lease — USD 22M. "
        "Debentures (Listed NCDs) — USD 18M. "
        "Refinancing risk: Medium. "
        "Change-of-control triggers mandatory prepayment on the senior facilities. "
        "Lender consent required for the transaction. "
        "Freely available cash USD 40M. Restricted cash USD 12M in escrow. "
        "Operating minimum cash floor USD 15M. "
        "Declared unpaid dividend USD 5M. Overdue trade creditors beyond normal terms USD 8M."
    )


def _complete_legacy() -> dict:
    return {
        "debt_total_usd_m": 200.0,
        "debt_instruments": [
            {
                "name": "Senior Term Loan A",
                "amount_usd_m": 85.0,
                "lender": "Bank Syndicate A",
                "rate": "SOFR+3.5%",
                "repayment_profile": "Amortising quarterly",
                "maturity": "2028",
                "security": "First ranking all-assets",
                "guarantees": "Holdco guarantee",
                "covenants_headroom": "Net debt/EBITDA 0.4x headroom",
            },
            {
                "name": "Senior Term Loan B",
                "amount_usd_m": 45.0,
                "lender": "Bank Syndicate B",
                "rate": "SOFR+4.0%",
                "repayment_profile": "Bullet",
                "maturity": "2029",
                "security": "Shared first ranking",
                "guarantees": "Holdco guarantee",
                "covenants_headroom": "Same package — 0.4x headroom",
            },
        ],
        "leverage_ratios": {"net_debt_revenue": 0.49},
        "dcf_metrics": {"wacc_pct": 9.0},
        "capital_notes": ["Refinancing risk: Medium."],
    }


def test_capital_structure_prompt_book_listed() -> None:
    system = compose_system("capital_structure", sector="EV", geography="India")
    assert "capital_structure" in listed_agents()
    assert "facility" in system.lower() or "net debt" in system.lower()
    body = agent_prompt("capital_structure")
    assert "Ola" not in body and "SoftBank" not in body
    assert "incomplete" in body.lower()
    assert "freely available" in body.lower()


def test_capital_structure_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_capital_structure.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_incomplete_schedule_withholds_leverage() -> None:
    heur = _heuristic_capital_structure_spec(
        company="Test3",
        corpus=_cap_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec={
            "debt_total_usd_m": 240.0,
            "debt_instruments": [
                {"name": "Senior Term Loan A", "amount_usd_m": 85.0},
                {"name": "Senior Term Loan B", "amount_usd_m": 45.0},
            ],
            "leverage_ratios": {"net_debt_revenue": 0.49, "debt_equity_ratio": 0.38},
        },
    )
    assert heur.get("schedule_complete") is False
    leverage = heur.get("leverage_ratios") or {}
    assert "leverage_withheld" in leverage
    assert "net_debt_revenue" not in leverage
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_complete_schedule_builds_net_debt() -> None:
    # Corpus has cash only — facilities come fully specified from loan-doc legacy.
    heur = _heuristic_capital_structure_spec(
        company="Test3",
        corpus=(
            "Freely available cash USD 40M. Restricted cash USD 12M in escrow. "
            "Operating minimum cash floor USD 15M. "
            "Change-of-control triggers mandatory prepayment. Lender consent required."
        ),
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec=_complete_legacy(),
    )
    assert heur.get("schedule_complete") is True
    facilities = heur.get("facilities") or []
    assert len(facilities) >= 2
    assert all(
        not str(f.get("lender") or "").startswith("Information")
        for f in facilities
        if isinstance(f, dict) and f.get("facility") in {
            "Senior Term Loan A", "Senior Term Loan B"
        }
    )
    bridge = heur.get("net_debt_bridge") or []
    closing = next(
        (
            r for r in bridge
            if isinstance(r, dict) and "net debt" in str(r.get("component") or "").lower()
        ),
        None,
    )
    assert closing is not None
    assert isinstance(closing.get("amount"), (int, float))
    leverage = heur.get("leverage_ratios") or {}
    assert "leverage_withheld" not in leverage
    assert leverage.get("net_debt_revenue") == 0.49


def test_cash_split_and_debt_like() -> None:
    heur = _heuristic_capital_structure_spec(
        company="Test3",
        corpus=_cap_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
    )
    cash = heur.get("cash_split") or []
    buckets = {str(c.get("bucket") or "") for c in cash if isinstance(c, dict)}
    assert any("Freely" in b for b in buckets)
    assert any("Restricted" in b for b in buckets)
    assert any("Operating" in b for b in buckets)
    debt_like = heur.get("debt_like_items") or []
    assert debt_like
    coc = heur.get("change_of_control") or []
    assert any(
        isinstance(r, dict)
        and not str(r.get("trigger") or "").startswith("Information")
        for r in coc
    )


def test_render_no_invest() -> None:
    heur = _heuristic_capital_structure_spec(
        company="Test3",
        corpus=_cap_corpus() + " We recommend invest.",
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec={"debt_instruments": [{"name": "Term Loan", "amount_usd_m": 10.0}]},
    )
    md = render_capital_structure_markdown("Capital Structure", heur)
    assert "## 1. Facility Schedule" in md
    assert "## 2. Debt-like Items" in md
    assert "## 3. Cash Split" in md
    assert "## 4. Change of Control" in md
    assert "## 5. Net Debt Bridge" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "incomplete" in md.lower() or "withheld" in md.lower()


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "capital_structure",
        "agentName": "Capital Structure",
        "target_company": "Test3",
        "summary": "Capital Structure for Test3",
        "sources": ["05_Financial_Due_Diligence.pdf"],
        "spec": _heuristic_capital_structure_spec(
            company="Test3",
            corpus=_cap_corpus(),
            sources=["05_Financial_Due_Diligence.pdf"],
            legacy_spec={
                "debt_instruments": [
                    {"name": "Senior Term Loan A", "amount_usd_m": 85.0},
                ],
                "debt_total_usd_m": 85.0,
            },
        ),
    }
    md = render_agent_document("capital_structure", output)
    assert "## 6. Quality & Reliance" in md
    assert "Senior Term Loan A" in md


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_capital_structure_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_cap_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
        prefer_heuristic=True,
        legacy_spec={"debt_instruments": [{"name": "Term Loan", "amount_usd_m": 10.0}]},
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-24"
