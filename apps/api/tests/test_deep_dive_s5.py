"""Slice 5 — Financial Analysis Deep Dive extractors."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_financial import (
    FINANCIAL_SLUGS,
    extract_financial_spec,
    findings_from_financial_spec,
)

_FINANCIAL_CIM = (
    "Financial Due Diligence Profit & Loss Summary (INR Crore) "
    "Line Item FY2021 FY2022 FY2023 FY2024E FY2025E "
    "Revenue 8 456 2,630 4,900 8,200 "
    "Cost of Goods Sold (11) (420) (2,443) (4,288) (6,560) "
    "Gross Profit (3) 36 187 612 1,640 "
    "Gross Margin (%) -37.5% 7.9% 7.1% 12.5% 20.0% "
    "EBITDA (163) (474) (933) (788) 10 "
    "EBITDA Margin (%) N/M -103.9% -35.5% -16.1% 0.1% "
    "Net Loss (PAT) (193) (579) (1,245) (1,298) (655) "
    "Debt Instrument Amount (USD M) Interest Rate (%) "
    "Senior Term Loan A USD 85M 9.2% March 2027 Secured "
    "Senior Term Loan B USD 45M 9.8% September 2026 Secured "
    "Mezzanine Notes USD 30M 13.5% June 2028 Subordinated "
    "TOTAL DEBT USD 240M Blended ~10.2% "
    "Net Debt / Revenue 0.49x < 0.3x Elevated "
    "Interest Coverage (EBIT / Interest) -5.2x > 3.0x Below Threshold "
    "Cash Burn Rate (Monthly INR Cr) ~85 < 50 (target) Elevated "
    "Minimum Liquidity: INR 500 Crore at quarter-end (Currently ~INR 840 Crore — Compliant) "
    "Capex Cap: INR 2,500 Crore p.a. (FY2024 spend: ~INR 1,980 Crore — Compliant) "
    "Financing Health Rating: 2.5 / 5 — Elevated Risk "
    "Refinancing risk: Medium — USD 130M matures by FY2026. "
    "The post-IPO cash raise provides a 12–18 month liquidity runway without further fundraising."
)

_VALUATION_CIM = (
    "Valuation Retention Comparable Analysis "
    "Gross Revenue Retention (GRR) 74% FY22: 68% → FY23: 71% → FY24: 74% 82% (sector avg) "
    "Net Revenue Retention (NRR) 81% FY22: 72% → FY23: 78% → FY24: 81% 95% (sector avg) "
    "Logo Churn (%) 39% FY22: 45% → FY23: 42% → FY24: 39% 29% (industry avg) "
    "Revenue Churn (%) 26% FY22: 32% → FY23: 29% → FY24: 26% 18% (sector avg) "
    "Fleet segment (8% of revenue) offers more predictable renewal visibility than retail. "
    "~54% of customers purchase via EMI (12–48 months). "
    "Retention Warning: NRR at 81% (vs 95% benchmark) and Logo Churn at 39%. "
    "WACC (Base) 9.0% 11.5% 7.5% "
    "Unlevered Free Cash Flow (UFCF) (1,344) (916) (150) 570 1,280 "
    "Enterprise Value (DCF) 21,280 2.55B "
    "Equity Value (DCF) 19,280 2.31B "
    "Implied Share Price (DCF Base) INR 43.1 ~USD 0.52 vs IPO Price of INR 76 "
    "Base Case (WACC 9.0%, TG 3.0%) 17,560 2.10B INR 34.9 -54.1% vs IPO"
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_historical_performance_parses_pl() -> None:
    spec = extract_financial_spec(
        "historical_performance",
        _FINANCIAL_CIM,
        sources=["05_Financial_Due_Diligence.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["track"] == "F"
    assert spec["extractor"] == "heuristic_v1"
    metrics = spec["performance_metrics"]
    assert metrics.get("revenue_fy2024_inr_cr") == 4900.0
    assert metrics.get("ebitda_fy2024_inr_cr") == -788.0
    assert metrics.get("gross_margin_fy2024_pct") == 12.5
    rev = next(r for r in spec["pl_lines"] if r["line_item"] == "Revenue")
    assert rev["fy2024_value"] == 4900.0


def test_revenue_quality_retention_metrics() -> None:
    spec = extract_financial_spec(
        "revenue_quality",
        _VALUATION_CIM,
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    metrics = spec["retention_metrics"]
    assert metrics.get("grr_pct") == 74.0
    assert metrics.get("nrr_pct") == 81.0
    assert metrics.get("logo_churn_pct") == 39.0
    assert spec["revenue_mix"].get("fleet_revenue_pct") == 8.0
    assert any("NRR" in f for f in spec["quality_flags"])


def test_cash_flow_burn_and_liquidity() -> None:
    text = _FINANCIAL_CIM + " " + _VALUATION_CIM
    spec = extract_financial_spec(
        "cash_flow",
        text,
        sources=["05_Financial_Due_Diligence.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    metrics = spec["cash_metrics"]
    assert metrics.get("monthly_burn_inr_cr") == 85.0
    assert metrics.get("liquidity_inr_cr") == 840.0
    assert metrics.get("capex_fy2024_inr_cr") == 1980.0
    assert any("burn" in n.lower() or "liquidity" in n.lower() for n in spec["liquidity_notes"])


def test_capital_structure_debt_and_dcf() -> None:
    text = _FINANCIAL_CIM + " " + _VALUATION_CIM
    spec = extract_financial_spec(
        "capital_structure",
        text,
        sources=["05_Financial_Due_Diligence.pdf", "13_Valuation_Retention_Comparable_Analysis.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["debt_total_usd_m"] == 240.0
    assert len(spec["debt_instruments"]) >= 2
    assert spec["dcf_metrics"].get("wacc_pct") == 9.0
    assert spec["dcf_metrics"].get("implied_share_price_inr") == 43.1
    findings = findings_from_financial_spec("capital_structure", spec)
    assert any("240" in f for f in findings)


def test_financial_agents_live_on_vdr() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Fin Slice5", "slug": "fin-slice5", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        files = [
            ("05_Financial_Due_Diligence.txt", _FINANCIAL_CIM.encode()),
            ("13_Valuation_Retention_Comparable_Analysis.txt", _VALUATION_CIM.encode()),
        ]
        for name, body in files:
            upload = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (name, BytesIO(body), "text/plain")},
            )
            assert upload.status_code == 200

        for phase in ("data_ingestion", "foundations"):
            assert client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"phase_id": phase},
            ).status_code == 202

        # Upstream deps for financial track.
        for slug in (
            "buying_behavior",
            "operational_risk",
            "supply_chain_resilience",
            "customer_stickiness",
        ):
            assert client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            ).status_code == 202

        for slug in FINANCIAL_SLUGS:
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            )
            assert run.status_code == 202, slug

        for slug in FINANCIAL_SLUGS:
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200, slug
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["stub"] is False
            assert payload["slice"] == "deep_dive_s5"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False, slug
            assert payload["findings"]

        hist = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/historical_performance/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert hist["spec"]["performance_metrics"].get("revenue_fy2024_inr_cr") == 4900.0


def test_financial_extractors_on_test1_vdr_snippets() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test1" / "library" / "documents"
    fin_path = root / "05_Financial_Due_Diligence.json"
    val_path = root / "13_Valuation_Retention_Comparable_Analysis.json"
    if not fin_path.is_file():
        return
    fin = json.loads(fin_path.read_text(encoding="utf-8"))["text"]
    hist = extract_financial_spec("historical_performance", fin, coverage="full")
    assert hist["metrics"]["pl_line_count"] >= 5
    assert hist["performance_metrics"].get("revenue_fy2024_inr_cr") == 4900.0
    cap = extract_financial_spec("capital_structure", fin, coverage="full")
    assert cap["debt_total_usd_m"] == 240.0
    if val_path.is_file():
        val = json.loads(val_path.read_text(encoding="utf-8"))["text"]
        rev = extract_financial_spec("revenue_quality", val, coverage="full")
        assert rev["retention_metrics"].get("nrr_pct") == 81.0
