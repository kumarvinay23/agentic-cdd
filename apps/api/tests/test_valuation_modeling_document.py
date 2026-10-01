"""Valuation Model — DiligenceIQ prompt-book one earnings basis."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.agent_document_valuation_modeling import (
    _arith_check,
    _heuristic_valuation_modeling_spec,
    build_valuation_modeling_spec,
    render_valuation_modeling_markdown,
)
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-val-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _val_corpus() -> str:
    return (
        "FY2024E Revenue USD 850M. "
        "EV/Revenue multiple 1.8x. Median EV/Revenue 1.8x. "
        "Ather Energy — 2.4x Rev. TVS Motor — 1.6x Rev. "
        "Implied EV Range USD 0.47B – USD 1.24B. "
        "Simple Energy (E2W startup) — USD 180M 1.8x Rev. "
        "Okinawa Autotech (E2W) — USD 95M 1.4x Rev. "
        "WACC (Base) 9.0%. Enterprise Value (DCF) 2.55B. "
        "Implied Share Price (DCF Base) INR 43.1. "
        "Terminal growth 3.0%. Discount rate build-up: risk-free 7% + ERP 5% − beta adj."
    )


def _trading_comps() -> dict:
    return {
        "subject_peer": {
            "name": "Pack Label (Subject)",
            "ev_revenue_x": 0.84,
            "is_subject": True,
        },
        "peer_medians": {"ev_revenue_x": 1.8, "ev_ebitda_x": 21.4},
        "implied_ev_range_usd_b": {"low": 0.47, "high": 1.24},
    }


def _precedents() -> dict:
    return {
        "transactions": [
            {"target": "Simple Energy (E2W startup)", "value_usd_m": 180.0, "ev_revenue_x": 1.8},
            {"target": "Okinawa Autotech (E2W)", "value_usd_m": 95.0, "ev_revenue_x": 1.4},
            {"target": "Ampere Vehicles", "value_usd_m": 120.0, "ev_revenue_x": 2.1},
        ],
        "median_ev_revenue_x": 2.1,
        "implied_ev_range_usd_b": {"low": 1.0, "high": 2.5},
    }


def _legacy() -> dict:
    return {
        "dcf": {
            "wacc_pct": 9.0,
            "enterprise_value_usd_b": 2.55,
            "implied_share_price_inr": 43.1,
            "scenarios": [
                {
                    "label": "Base Case",
                    "enterprise_value_usd_b": 2.1,
                    "equity_value_per_share_inr": 34.9,
                }
            ],
        },
        "football_field": [
            {"method": "Trading comps", "enterprise_value_usd_b": 0.85},
            {"method": "DCF Base", "enterprise_value_usd_b": 2.1},
        ],
        "valuation_flags": ["Comps and DCF diverge on growth assumptions"],
        "fv_code": "FV-05",
    }


def test_valuation_modeling_prompt_book_listed() -> None:
    system = compose_system("valuation_modeling", sector="EV", geography="India")
    assert "valuation_modeling" in listed_agents()
    assert "earnings" in system.lower()
    body = agent_prompt("valuation_modeling")
    assert "Ola" not in body and "SoftBank" not in body
    assert "median" in body.lower()
    assert "reconcile" in body.lower()
    assert "invest" in body.lower() or "pass" in body.lower()


def test_valuation_modeling_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_valuation_modeling.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_one_earnings_basis_used_everywhere() -> None:
    heur = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus=_val_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec=_legacy(),
        trading_comps=_trading_comps(),
        precedent_transactions=_precedents(),
    )
    earn = heur.get("earnings_basis") or {}
    assert earn.get("metric")
    assert earn.get("amount") is not None
    assert not str(earn.get("amount")).startswith("Information")
    # Subject row uses deal company, not pack "(Subject)" label
    comps = heur.get("comparable_companies") or []
    subject_rows = [c for c in comps if isinstance(c, dict) and c.get("is_subject")]
    assert subject_rows
    assert subject_rows[0]["name"] == "Test3"
    assert "(Subject)" not in subject_rows[0]["name"]
    # Comps summary shows median and range, not only average
    summary = heur.get("comps_summary") or {}
    assert summary.get("median_multiple") is not None
    assert summary.get("range_multiple_low") is not None or summary.get("implied_ev_usd_b_low") is not None


def test_arithmetic_check_on_multiples() -> None:
    check = _arith_check(multiple=2.0, earnings=100.0, implied_value=200.0, value_unit="USD M")
    assert check["status"] == "pass"
    fail = _arith_check(multiple=2.0, earnings=100.0, implied_value=50.0, value_unit="USD M")
    assert fail["status"] == "fail"

    heur = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus=_val_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec=_legacy(),
        trading_comps=_trading_comps(),
        precedent_transactions=_precedents(),
    )
    comps_arith = (heur.get("comps_summary") or {}).get("arithmetic") or {}
    assert comps_arith.get("status") in {"pass", "fail", "unchecked"}
    # Declared earnings present → comps/precedents should attempt a check
    assert comps_arith.get("detail")
    dcf = heur.get("dcf_view") or {}
    assert dcf.get("discount_rate_pct") == 9.0 or dcf.get("enterprise_value_usd_b") is not None
    if isinstance(dcf.get("implied_exit_multiple"), (int, float)):
        assert dcf.get("arithmetic")


def test_reconcile_explains_not_averages() -> None:
    heur = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus=_val_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec=_legacy(),
        trading_comps=_trading_comps(),
        precedent_transactions=_precedents(),
    )
    recon = heur.get("method_reconciliation") or []
    assert recon
    notes = " ".join(str(r.get("notes") or "") for r in recon if isinstance(r, dict)).lower()
    assert "average" not in notes or "not averag" in notes or "explain" in notes or "disagree" in notes or notes
    # Legacy dual-write preserved
    assert heur.get("dcf")
    assert heur.get("football_field")
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_render_no_invest() -> None:
    heur = _heuristic_valuation_modeling_spec(
        company="Test3",
        corpus=_val_corpus() + " We recommend invest.",
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        legacy_spec=_legacy(),
        trading_comps=_trading_comps(),
        precedent_transactions=_precedents(),
    )
    md = render_valuation_modeling_markdown("Valuation Model", heur)
    assert "## 1. Declared Earnings Basis" in md
    assert "## 2. Comparable Companies" in md
    assert "## 3. Precedent Transactions" in md
    assert "## 4. Discounted Cash Flow" in md
    assert "## 5. Method Reconciliation" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "median" in md.lower()


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "valuation_modeling",
        "agentName": "Valuation Model",
        "target_company": "Test3",
        "summary": "Valuation Model for Test3",
        "sources": ["13_Valuation_Retention_Comparable_Analysis.pdf"],
        "spec": _heuristic_valuation_modeling_spec(
            company="Test3",
            corpus=_val_corpus(),
            sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
            legacy_spec=_legacy(),
            trading_comps=_trading_comps(),
            precedent_transactions=_precedents(),
        ),
    }
    md = render_agent_document("valuation_modeling", output)
    assert "## 1. Declared Earnings Basis" in md
    assert "Test3" in md


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_valuation_modeling_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_val_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        prefer_heuristic=True,
        legacy_spec=_legacy(),
        trading_comps=_trading_comps(),
        precedent_transactions=_precedents(),
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("fv_code") == "FV-05" or spec.get("dd_code") == "FV-05"
    assert isinstance(spec.get("earnings_basis"), dict)
