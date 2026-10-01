"""Slice 2 — Stage B Final Verdict (trading_comps + precedent_transactions + valuation_modeling)."""

from __future__ import annotations

import json
import uuid
from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_deals import ensure_deal_folder
from agetic_cdd_api.verdict_valuation import (
    extract_verdict_valuation_from_documents,
    extract_verdict_valuation_spec,
    findings_from_verdict_valuation_spec,
    merge_verdict_valuation_spec,
)
from agetic_cdd_api.verdict_store import validate_verdict_store

TEST2_VALUATION = (
    "SECTION B — COMPARABLE COMPANY & PRECEDENT TRANSACTION ANALYSIS "
    "B1. Comparable Company Analysis (Public Peers) "
    "Peer Company Exchange Market Cap (USD B) EV / EBITDA (LTM) EV / Revenue (LTM) Revenue Growth (%) Gross Margin (%) "
    "Ola Electric (Subject) BSE/NSE 4.1 N/M (neg. EBITDA) 0.84x +86.3% 12.5% "
    "Ather Energy (Private — est.) Unlisted ~1.2 N/M ~1.1x +62% ~14% "
    "TVS Motor Co. NSE 14.8 28.4x 2.1x +18.2% 27.3% "
    "Median (Ex-Subject, Ex-N/M) — — 21.4x 1.8x +18.5% 22.0% "
    "B1a. Implied Valuation Range from Comparable Multiples "
    "EV / Revenue USD ~590M Revenue 0.8x 2.1x 0.47B 1.24B "
    "IPO Implied EV (August 2024) — — — ~4.10B ~4.10B (reference) "
    "B2. Precedent Transaction Analysis (Relevant M&A) "
    "Mar 2024 Simple Energy (E2W startup) Strategic Auto OEM (undisclosed) India Market share + tech ~USD 180M ~1.8x Rev (FY24E) "
    "Oct 2023 Okinawa Autotech (E2W) PE Consortium India Consolidation play ~USD 95M ~1.4x Rev "
    "Jun 2023 Gogoro (E2W — Taiwan) SPAC Merger Taiwan/Global Battery swap + software ~USD 2.35B ~6.4x Rev "
    "Feb 2023 Revolt Motors (E-Motorcycle) Hero MotoCorp India EV portfolio entry ~USD 50M ~2.1x Rev "
    "Jan 2022 Hero Electric (minority) Investors consortium India Scale financing ~USD 60M ~2.2x Rev "
    "B2a. Precedent Transaction Multiple Summary "
    "Median 2.1x +17% "
    "Applied Range (Ola Electric) 2.0x – 4.5x Revenue +11%–+150% Reflects tech + scale premium "
    "Implied EV Range (FY2024E Rev) USD 1.18B – USD 2.66B — Ex-IPO growth optionality "
    "SECTION C — INTRINSIC VALUATION (DCF) & SENSITIVITY ANALYSIS "
    "C1. DCF Model Assumptions WACC (Base) 9.0% 11.5% 7.5% "
    "C1b. Terminal Value & Enterprise Value Bridge (Base Case) "
    "Enterprise Value (DCF) 21,280 2.55B PV UFCF + PV Terminal Value "
    "Equity Value (DCF) 19,280 2.31B Enterprise Value minus Net Debt "
    "Implied Share Price (DCF Base) INR 43.1 ~USD 0.52 vs IPO Price of INR 76 "
    "C3. Scenario Summary — Bear / Base / Bull Case "
    "Bear Case (WACC 11.5%, TG 1.5%) 8,600 1.03B INR 14.9 -80.4% vs IPO Execution failure; subsidy cut "
    "Base Case (WACC 9.0%, TG 3.0%) 17,560 2.10B INR 34.9 -54.1% vs IPO Moderate growth; service improvement "
    "Bull Case (WACC 7.5%, TG 4.5%) 40,600 4.87B INR 86.5 +13.8% vs IPO Scale + margin + battery success "
    "IPO Market Price (Reference) ~34,200 ~4.10B INR 76.0 — Market growth optionality premium"
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal_for_stage_b(client: TestClient, headers: dict[str, str], *, slug: str) -> str:
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={"name": "FV S2", "slug": slug, "industry": "generic"},
    )
    deal_id = created.json()["data"]["id"]
    upload = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={"file": ("CIM.pdf", BytesIO(b"%PDF-1.4 market sizing TAM SAM"), "application/pdf")},
    )
    assert upload.status_code == 200
    return deal_id


def _upload_valuation_doc(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    upload = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={
            "file": (
                "13_Valuation_Retention_Comparable_Analysis.txt",
                BytesIO(TEST2_VALUATION.encode("utf-8")),
                "text/plain",
            )
        },
    )
    assert upload.status_code == 200
    sync = client.post(f"/api/v1/portfolios/{deal_id}/cdd/sync", headers=headers)
    assert sync.status_code == 200
    ingest = client.post(
        f"/api/v1/portfolios/{deal_id}/pipeline/run",
        headers=headers,
        json={"phase_id": "data_ingestion"},
    )
    assert ingest.status_code == 202


def _run_through_deep_dive(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    for phase in ("data_ingestion", "foundations", "deep_dive"):
        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": phase},
        ).status_code == 202


def test_bind_verdict_documents_matches_valuation_doc() -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.services_final_verdict import _bind_verdict_documents

    role = SimpleNamespace(
        slug="trading_comps",
        filename_needles=("valuation", "comparable", "comps", "trading", "multiple"),
    )
    index = {
        "documents": [
            {"filename": "10_HR_Organizational_Due_Diligence.txt"},
            {"filename": "13_Valuation_Retention_Comparable_Analysis.txt"},
            {"filename": "deal_summary_old.pdf"},
        ]
    }
    bound = _bind_verdict_documents(index, role)
    names = [d["filename"] for d in bound]
    assert names[0] == "13_Valuation_Retention_Comparable_Analysis.txt"


def test_trading_comps_parses_test2_valuation() -> None:
    spec = extract_verdict_valuation_spec(
        "trading_comps",
        TEST2_VALUATION,
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        coverage="full",
        market_definition={"segments": ["EV 2W"]},
        historical_performance={"revenue_usd_m": 590.0},
    )
    assert spec["empty"] is False
    assert spec["fv_code"] == "FV-03"
    subject = spec["subject_peer"]
    assert subject["ev_revenue_x"] == 0.84
    assert subject["market_cap_usd_b"] == 4.1
    medians = spec["peer_medians"]
    assert medians["ev_revenue_x"] == 1.8
    assert spec["ipo_implied_ev_usd_b"] == 4.1
    ev_range = spec["implied_ev_range_usd_b"]
    assert ev_range["low"] == 0.47
    assert ev_range["high"] == 1.24
    findings = findings_from_verdict_valuation_spec("trading_comps", spec)
    assert any("0.84x" in f for f in findings)
    assert any("IPO-implied EV" in f for f in findings)


def test_precedent_transactions_parses_test2_valuation() -> None:
    spec = extract_verdict_valuation_spec(
        "precedent_transactions",
        TEST2_VALUATION,
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        coverage="full",
        foundation_f05={"deal_context": "EV sector"},
        compensation_alignment={"esop_pool_inr_cr": 400.0},
    )
    assert spec["empty"] is False
    assert spec["fv_code"] == "FV-04"
    assert spec["median_ev_revenue_x"] == 2.1
    applied = spec["applied_ev_revenue_range_x"]
    assert applied["low"] == 2.0
    assert applied["high"] == 4.5
    ev_range = spec["implied_ev_range_usd_b"]
    assert ev_range["low"] == 1.18
    assert ev_range["high"] == 2.66
    assert len(spec["transactions"]) >= 2
    targets = {tx["target"] for tx in spec["transactions"]}
    assert "Simple Energy (E2W startup)" in targets or any("Simple Energy" in t for t in targets)
    assert any("Gogoro" in t for t in targets)
    assert not any(
        t.startswith(("Date Target", "FY24E", "Jan 2022", "Taiwan"))
        or t in {"Taiwan)", "Jan 2022", "FY24E)"}
        for t in targets
    )
    gogoro = next(tx for tx in spec["transactions"] if "Gogoro" in tx["target"])
    assert gogoro["value_usd_m"] == 2350.0
    assert gogoro["ev_revenue_x"] == 6.4
    findings = findings_from_verdict_valuation_spec("precedent_transactions", spec)
    assert any("2.1x" in f for f in findings)
    assert any("1.18B" in f for f in findings)


def test_valuation_modeling_parses_dcf_and_football_field() -> None:
    trading = extract_verdict_valuation_spec(
        "trading_comps",
        TEST2_VALUATION,
        sources=["doc.txt"],
        coverage="full",
    )
    precedent = extract_verdict_valuation_spec(
        "precedent_transactions",
        TEST2_VALUATION,
        sources=["doc.txt"],
        coverage="full",
    )
    spec = extract_verdict_valuation_spec(
        "valuation_modeling",
        TEST2_VALUATION,
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        coverage="full",
        trading_comps=trading,
        precedent_transactions=precedent,
        historical_performance={"revenue_usd_m": 590.0},
        capital_structure={"net_debt_usd_m": 240.0},
    )
    assert spec["empty"] is False
    assert spec["fv_code"] == "FV-05"
    dcf = spec["dcf"]
    assert dcf["wacc_pct"] == 9.0
    assert dcf["enterprise_value_usd_b"] == 2.55
    assert dcf["implied_share_price_inr"] == 43.1
    scenarios = dcf["scenarios"]
    labels = [row["label"] for row in scenarios]
    assert "Base Case" in labels
    base = next(row for row in scenarios if row["label"] == "Base Case")
    assert base["equity_value_per_share_inr"] == 34.9
    assert base["premium_discount_vs_ipo_pct"] == -54.1
    football = spec["football_field"]
    methods = {row.get("method") for row in football if isinstance(row, dict)}
    assert "Trading comps" in methods
    assert "Precedent transactions" in methods
    findings = findings_from_verdict_valuation_spec("valuation_modeling", spec)
    assert any("34.9" in f or "43.1" in f for f in findings)
    assert any("2.55B" in f for f in findings)


def test_merge_verdict_valuation_preserves_transactions() -> None:
    base = {
        "empty": False,
        "transactions": [{"target": "Simple Energy", "ev_revenue_x": 1.8}],
        "median_ev_revenue_x": 2.1,
        "sources": ["doc1.txt"],
    }
    incoming = {
        "empty": False,
        "transactions": [{"target": "Revolt Motors", "ev_revenue_x": 2.1}],
        "median_ev_revenue_x": None,
        "sources": ["doc2.txt"],
    }
    merged = merge_verdict_valuation_spec("precedent_transactions", base, incoming)
    names = {row["target"] for row in merged["transactions"]}
    assert "Simple Energy" in names
    assert "Revolt Motors" in names
    assert merged["median_ev_revenue_x"] == 2.1


def test_extract_verdict_valuation_from_documents_merges_chunks() -> None:
    comps_section = (
        "Ola Electric (Subject) BSE/NSE 4.1 N/M (neg. EBITDA) 0.84x +86.3% 12.5% "
        "Median (Ex-Subject, Ex-N/M) — — 21.4x 1.8x +18.5% 22.0% "
    )
    dcf_section = (
        "Enterprise Value (DCF) 21,280 2.55B "
        "Implied Share Price (DCF Base) INR 43.1 "
        "Base Case (WACC 9.0%, TG 3.0%) 17,560 2.10B INR 34.9 -54.1% vs IPO "
    )
    spec = extract_verdict_valuation_from_documents(
        "valuation_modeling",
        [
            ("comps.txt", comps_section),
            ("dcf.txt", dcf_section),
        ],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["dcf"]["enterprise_value_usd_b"] == 2.55
    assert len(spec["sources"]) <= 4


def test_stage_b_diagnostics_on_store_fallback() -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.services_final_verdict import _stage_b_diagnostics

    role = SimpleNamespace(
        slug="valuation_modeling",
        foundation_deps=(),
        deep_dive_deps=("historical_performance", "capital_structure"),
        depends_on=("trading_comps", "precedent_transactions"),
    )
    diagnostics = _stage_b_diagnostics(
        role,
        docs=[],
        market_definition=None,
        historical_performance={"metrics": {"revenue": 590}},
        capital_structure=None,
        foundation_f05=None,
        compensation_alignment=None,
        trading_comps={"metrics": {"median_ev_revenue_x": 1.8}},
        precedent_transactions=None,
        extract_source="stores",
    )
    assert diagnostics["extract_source"] == "stores"
    assert "capital_structure" in diagnostics["missing_deps"]
    assert "precedent_transactions" in diagnostics["missing_deps"]


def test_final_verdict_s2_stage_b_integration() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_slug = f"fv-s2-{uuid.uuid4().hex[:8]}"
        deal_id = _create_deal_for_stage_b(client, headers, slug=deal_slug)
        _run_through_deep_dive(client, headers, deal_id)
        _upload_valuation_doc(client, headers, deal_id)

        for slug in ("trading_comps", "precedent_transactions", "valuation_modeling"):
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"phase_id": "final_verdict", "agent_key": slug},
            )
            assert run.status_code == 202, slug

        for slug in ("trading_comps", "precedent_transactions", "valuation_modeling"):
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["slice"] == "final_verdict_s2"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False

        comps_payload = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/trading_comps/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert comps_payload["spec"]["subject_peer"]["ev_revenue_x"] == 0.84

        model_payload = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/valuation_modeling/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert model_payload["spec"]["dcf"]["wacc_pct"] == 9.0
        assert any("34.9" in f or "2.55B" in f for f in model_payload.get("findings") or [])

        store_path = ensure_deal_folder(deal_slug) / "library" / "verdict_store.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        assert validate_verdict_store(store) == []
        assert store["completeness"]["stage_ready"]["B"] is True
