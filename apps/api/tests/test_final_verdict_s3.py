"""Slice 3 — Stage C Final Verdict (ic_synthesis + recommendation)."""

from __future__ import annotations

import json
import uuid
from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_deals import ensure_deal_folder
from agetic_cdd_api.verdict_store import validate_verdict_store
from agetic_cdd_api.verdict_synthesis import (
    extract_verdict_synthesis_from_documents,
    extract_verdict_synthesis_spec,
    findings_from_verdict_synthesis_spec,
    merge_verdict_synthesis_spec,
)

TEST2_THESIS = (
    "03 Investment Thesis Strategic Rationale & Value Creation "
    "Investment Pillars "
    "Technology-First Positioning MoveOS differentiates Ola from hardware-only competitors. "
    "OTA updates, connected features, and app-based controls create a sticky software moat. "
    "Vertical Integration Strategy In-house battery cells (Gigafactory), motors, controllers, "
    "and software reduce BOM costs and improve margins. "
    "Scale Advantage Futurefactory's 2M+ unit capacity creates unmatched cost per unit economics. "
    "Brand Equity Among Youth Ola Electric commands strong awareness (92% aided recall). "
    "Ecosystem Monetization Future revenue from charging network, battery swapping, and software. "
    "Investment Risks Key risk factors and probability/impact assessment. "
    "Risk Factor Probability Impact Mitigation "
    "Subsidy reduction / FAME-III delay Medium High Competitive pricing strategy "
    "OEM counter-attack (TVS, Bajaj) High Medium Software & brand moat "
    "Execution failure at scale Medium High Mgmt hires + systems "
    "Customer trust erosion Medium High Service network investment "
    "Verdict Ola Electric represents a high-risk, high-reward investment opportunity. "
    "Investors with a 5–7 year horizon may find the risk-reward attractive. "
    "A staged investment approach with performance milestones is recommended."
)

TEST2_EXEC_SUMMARY = (
    "01 Executive Summary Investment Overview — Ola Electric Mobility Limited "
    "Key Positive Indicators "
    "\x7f Strong brand recognition among urban millennials and Gen Z consumers. "
    "\x7f Proprietary MoveOS software ecosystem providing digital differentiation. "
    "Key Risks & Concerns "
    "\x7f Persistent operating losses with EBITDA breakeven projected no earlier than FY2026. "
    "\x7f Intense competitive pressure from TVS iQube, Ather 450X, Bajaj Chetak, and Hero Vida. "
    "Overall Investment Rating Dimension Rating (1–5) Commentary "
    "Financial Health 2.5 / 5 High losses; improving trajectory "
    "Market Opportunity 4.5 / 5 Large, fast-growing TAM "
    "Competitive Position 3.0 / 5 Strong brand; rising competition "
    "Operational Maturity 2.5 / 5 Scaling challenges persist "
    "Technology & IP 3.5 / 5 MoveOS differentiated; battery IP nascent "
    "ESG Profile 3.0 / 5 Positive intent; execution gaps "
    "Management Quality 3.5 / 5 Visionary founder; depth needed "
    "OVERALL 3.2 / 5 Conditional Positive — Monitor Closely "
    "Disclaimer: This document contains forward-looking statements."
)

TEST2_MONITORING = (
    "SECTION D — INTEGRATED VERDICT & INVESTMENT IMPLICATIONS "
    "D2. Key Monitoring Metrics for Investors Metric Current Trigger for Concern Trigger for Confidence "
    "NRR 81% < 78% > 88% "
    "Logo Churn 39% > 45% < 30% "
    "Gross Margin 12.5% < 10% > 18% "
    "Service Satisfaction Score 52% < 45% > 68%"
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal_for_stage_c(client: TestClient, headers: dict[str, str], *, slug: str) -> str:
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={"name": "FV S3", "slug": slug, "industry": "generic"},
    )
    deal_id = created.json()["data"]["id"]
    upload = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={"file": ("CIM.pdf", BytesIO(b"%PDF-1.4 market sizing TAM SAM"), "application/pdf")},
    )
    assert upload.status_code == 200
    return deal_id


def _upload_stage_c_docs(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    for filename, text in (
        ("03_Investment_Thesis.txt", TEST2_THESIS),
        ("01_Executive_Summary.txt", TEST2_EXEC_SUMMARY),
        ("13_Valuation_Retention_Comparable_Analysis.txt", TEST2_MONITORING),
    ):
        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": (filename, BytesIO(text.encode("utf-8")), "text/plain")},
        )
        assert upload.status_code == 200, filename
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


def test_bind_verdict_documents_matches_thesis_docs() -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.services_final_verdict import _bind_verdict_documents

    role = SimpleNamespace(
        slug="ic_synthesis",
        filename_needles=("findings", "investment thesis", "executive summary"),
    )
    index = {
        "documents": [
            {"filename": "CIM.pdf"},
            {"filename": "03_Investment_Thesis.txt"},
            {"filename": "01_Executive_Summary.txt"},
        ]
    }
    bound = _bind_verdict_documents(index, role)
    names = [d["filename"] for d in bound]
    assert "03_Investment_Thesis.txt" in names
    assert "01_Executive_Summary.txt" in names


def test_ic_synthesis_parses_test2_signals() -> None:
    valuation = {
        "empty": False,
        "dcf": {
            "implied_share_price_inr": 43.1,
            "scenarios": [
                {
                    "label": "Base Case",
                    "equity_value_per_share_inr": 34.9,
                    "premium_discount_vs_ipo_pct": -54.1,
                }
            ],
        },
        "valuation_flags": ["DCF base implied share price INR 43.1"],
    }
    spec = extract_verdict_synthesis_spec(
        "ic_synthesis",
        TEST2_THESIS + "\n" + TEST2_EXEC_SUMMARY,
        sources=["03_Investment_Thesis.pdf", "01_Executive_Summary.pdf"],
        coverage="full",
        valuation_modeling=valuation,
        execution_risk={"empty": False, "overall_human_capital_risk_1_10": 7, "retention_risk_flags": ["Key-man risk"]},
    )
    assert spec["empty"] is False
    assert spec["fv_code"] == "FV-06"
    assert spec["overall_score_1_5"] == 3.2
    assert "Conditional Positive" in (spec.get("overall_label") or "")
    assert spec["go_no_go"] == "Conditional Go"
    assert len(spec["investment_pillars"]) >= 3
    assert any(p["name"] == "Technology-First Positioning" for p in spec["investment_pillars"])
    pillar_names = {p["name"] for p in spec["investment_pillars"]}
    assert not any(
        bad in name
        for name in pillar_names
        for bad in ("Metric FY", "Executive", "Organizational Due", "Commentary")
    )
    assert len(spec["primary_risks"]) >= 2
    risk_names = [r["risk"] for r in spec["primary_risks"] if isinstance(r, dict)]
    assert any("OEM counter-attack" in n or "Subsidy" in n for n in risk_names)
    assert not any("pricing strategy OEM" in n for n in risk_names)
    dims = {d["dimension"] for d in spec.get("dimensions") or []}
    assert "Financial Health" in dims
    assert "ESG Profile" in dims
    assert "nascent ESG Profile" not in dims
    assert "Commentary Financial Health" not in dims
    strengths = spec.get("strengths") or []
    assert not any(s.startswith(("execution_risk:", "precedent_transactions:", "valuation_modeling:")) for s in strengths)
    findings = findings_from_verdict_synthesis_spec("ic_synthesis", spec)
    assert any("Conditional Go" in f for f in findings)
    assert any("3.2/5" in f for f in findings)


def test_recommendation_builds_structure_and_returns() -> None:
    ic = extract_verdict_synthesis_spec(
        "ic_synthesis",
        TEST2_THESIS + "\n" + TEST2_EXEC_SUMMARY,
        sources=["thesis.txt"],
        coverage="full",
    )
    valuation = {
        "empty": False,
        "dcf": {
            "scenarios": [
                {"label": "Bear Case", "equity_value_per_share_inr": 14.9, "premium_discount_vs_ipo_pct": -80.4},
                {"label": "Base Case", "equity_value_per_share_inr": 34.9, "premium_discount_vs_ipo_pct": -54.1},
                {"label": "Bull Case", "equity_value_per_share_inr": 86.5, "premium_discount_vs_ipo_pct": 13.8},
            ]
        },
    }
    precedent = {
        "empty": False,
        "implied_ev_range_usd_b": {"low": 1.18, "high": 2.66},
    }
    spec = extract_verdict_synthesis_spec(
        "recommendation",
        TEST2_THESIS + "\n" + TEST2_MONITORING,
        sources=["thesis.txt", "valuation.txt"],
        coverage="full",
        ic_synthesis=ic,
        valuation_modeling=valuation,
        precedent_transactions=precedent,
    )
    assert spec["empty"] is False
    assert spec["fv_code"] == "FV-07"
    assert "staged" in (spec.get("deal_structure") or "").lower()
    assert spec["aligned_go_no_go"] == "Conditional Go"
    scenarios = {row["scenario"]: row for row in spec["returns_by_scenario"]}
    assert "Base Case" in scenarios
    assert scenarios["Base Case"]["irr_pct"] is not None
    assert scenarios["Base Case"]["moic_x"] is not None
    assert any("precedent EV" in cp for cp in spec["conditions_precedent"])
    assert not any("via Software &" == cp[-14:] or cp.endswith("via Software &") for cp in spec["conditions_precedent"])
    assert not any("Insight Snapshot" in cp for cp in spec["conditions_precedent"])
    metrics = {row["metric"] for row in spec.get("monitoring_metrics") or []}
    assert "NRR" in metrics
    assert "Logo Churn" in metrics
    assert not any("Executive Summary" in m or "Confidence NRR" in m for m in metrics)
    assert len(spec["hundred_day_plan"]) >= 3
    assert not any("Executive Summary" in item for item in spec["hundred_day_plan"])
    findings = findings_from_verdict_synthesis_spec("recommendation", spec)
    assert any("IRR" in f and "MOIC" in f for f in findings)


def test_merge_verdict_synthesis_preserves_pillars() -> None:
    base = {
        "empty": False,
        "investment_pillars": [{"name": "Scale Advantage", "detail": "capacity"}],
        "strengths": ["brand"],
        "sources": ["a.txt"],
    }
    incoming = {
        "empty": False,
        "investment_pillars": [{"name": "Ecosystem Monetization", "detail": "ARPU"}],
        "strengths": ["software"],
        "go_no_go": "Conditional Go",
        "sources": ["b.txt"],
    }
    merged = merge_verdict_synthesis_spec("ic_synthesis", base, incoming)
    names = {p["name"] for p in merged["investment_pillars"]}
    assert "Scale Advantage" in names
    assert "Ecosystem Monetization" in names
    assert merged["go_no_go"] == "Conditional Go"


def test_generic_pillar_and_monitoring_patterns() -> None:
    generic_thesis = (
        "Investment Pillars "
        "Cloud Platform Expansion Expanding multi-tenant SaaS into mid-market accounts. "
        "Partner Channel Scale Building reseller network across North America. "
        "Overall Investment Rating Financial Health 3.0 / 5 Stable cash profile "
    )
    generic_monitor = (
        "Key Monitoring Metrics for Investors Metric Current Trigger for Concern Trigger for Confidence "
        "Net Dollar Retention 92% < 85% > 105% "
        "Gross Logo Churn 14% > 20% < 10% "
    )
    ic = extract_verdict_synthesis_spec(
        "ic_synthesis",
        generic_thesis,
        sources=["generic.txt"],
        coverage="full",
    )
    pillar_names = {p["name"] for p in ic.get("investment_pillars") or []}
    assert "Cloud Platform Expansion" in pillar_names or "Partner Channel Scale" in pillar_names

    rec = extract_verdict_synthesis_spec(
        "recommendation",
        generic_monitor,
        sources=["monitor.txt"],
        coverage="full",
        ic_synthesis={"empty": False, "go_no_go": "Conditional Go"},
    )
    metrics = {row["metric"] for row in rec.get("monitoring_metrics") or []}
    assert "Net Dollar Retention" in metrics or "Gross Logo Churn" in metrics


def test_extract_verdict_synthesis_from_documents_merges_chunks() -> None:
    spec = extract_verdict_synthesis_from_documents(
        "ic_synthesis",
        [
            ("thesis.txt", TEST2_THESIS),
            ("exec.txt", TEST2_EXEC_SUMMARY),
        ],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["overall_score_1_5"] == 3.2
    assert len(spec["investment_pillars"]) >= 2


def test_stage_c_diagnostics_on_store_fallback() -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.services_final_verdict import _stage_c_diagnostics

    role = SimpleNamespace(
        slug="recommendation",
        depends_on=("ic_synthesis",),
        filename_needles=("term sheet",),
    )
    diagnostics = _stage_c_diagnostics(
        role,
        docs=[],
        extract_source="stores",
        ic_synthesis=None,
        valuation_modeling={"empty": False},
    )
    assert diagnostics["extract_source"] == "stores"
    assert "ic_synthesis" in diagnostics["missing_deps"]


def test_final_verdict_s3_stage_c_integration() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_slug = f"fv-s3-{uuid.uuid4().hex[:8]}"
        deal_id = _create_deal_for_stage_c(client, headers, slug=deal_slug)
        _run_through_deep_dive(client, headers, deal_id)
        _upload_stage_c_docs(client, headers, deal_id)

        # Run Stage A/B first so Stage C has upstream hydration, then Stage C.
        for slug in (
            "execution_risk",
            "compensation_alignment",
            "trading_comps",
            "precedent_transactions",
            "valuation_modeling",
            "ic_synthesis",
            "recommendation",
        ):
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"phase_id": "final_verdict", "agent_key": slug},
            )
            assert run.status_code == 202, slug

        for slug in ("ic_synthesis", "recommendation"):
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["slice"] == "final_verdict_s3"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False

        ic_payload = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/ic_synthesis/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert ic_payload["spec"]["go_no_go"] == "Conditional Go"
        assert ic_payload["spec"].get("overall_score_1_5") == 3.2

        rec_payload = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/recommendation/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert "staged" in (rec_payload["spec"].get("deal_structure") or "").lower()
        assert any("IRR" in f for f in rec_payload.get("findings") or [])

        store_path = ensure_deal_folder(deal_slug) / "library" / "verdict_store.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        assert validate_verdict_store(store) == []
        assert store["completeness"]["stage_ready"]["C"] is True
