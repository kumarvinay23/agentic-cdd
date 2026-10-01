"""Slice 4 — Supplier & Operational Deep Dive extractors."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_ops import OPS_SLUGS, extract_ops_spec, findings_from_ops_spec

_MANUFACTURING_CIM = (
    "Manufacturing & Supply Chain Review Sourcing, Logistics & Vendor Analysis "
    "Bill of Materials (BOM) Breakdown Estimated component cost breakdown per vehicle "
    "(FY2024E, ~INR 55,000 COGS/unit). "
    "Battery Pack (Cells + BMS) 38% ~20,900 Korea/China import Phase 2 domestic "
    "Electric Motor 12% ~6,600 Domestic (partial) ~60% local "
    "Power Electronics / Inverter 9% ~4,950 China import Low localization "
    "Chassis & Frame 8% ~4,400 Domestic Fully local "
    "Body Panels (Plastic/Metal) 6% ~3,300 Domestic Fully local "
    "Tyres & Suspension 5% ~2,750 Domestic (MRF, Minda) Fully local "
    "Wiring Harness 4% ~2,200 Domestic (Motherson) Fully local "
    "Braking System 4% ~2,200 Domestic / Import mix ~70% local "
    "Display & Infotainment 5% ~2,750 Taiwan/Korea import Low localization "
    "Fasteners, Assembly & Others 9% ~4,950 Domestic Fully local "
    "Vendor Component Country Annual Value (INR Cr) Risk Level Alternate Vendor? "
    "CATL Li-ion Cells China ~480 High Yes (Samsung SDI) "
    "Samsung SDI Li-ion Cells Korea ~320 High Yes (CATL) "
    "BYD Supply (Indirect) Power Electronics China ~140 High Partial "
    "Motherson Sumi Wiring Harness India ~95 Low Yes (Delphi) "
    "MRF Tyres Tyres India ~65 Low Yes (CEAT) "
    "Minda Industries Switches/Electrics India ~80 Low Yes "
    "MediaTek Infotainment Chip Taiwan ~110 Medium Partial "
    "Bosch India ABS / Braking India ~75 Medium Yes (Continental) "
    "Days Inventory Outstanding (DIO) 68 days 45 days 42 days "
    "Days Payable Outstanding (DPO) 38 days 55 days 58 days "
    "Delivery Lead Time (Order-to-Delivery) 22 days 12 days 10 days "
    "Spare Parts Fill Rate (%) 78% 95% 93% "
    "Localization Roadmap Year Target Domestic Content (%) Key Milestones "
    "FY2024 (Current) 52% Motor, harness, body panels local "
    "FY2025 65% Domestic LFP cell pilot (1 GWh), BMS local "
    "FY2026 75% Gigafactory Phase 1 (5 GWh) operational "
    "China concentration risk (CATL, BYD supply) geopolitical disruption could halt production. "
    "Parts stockout rate at 11.2% vs 3% target inventory planning requires urgent improvement. "
    "DIO of 68 days vs 42-day benchmark excess working capital tied up in slow-moving parts. "
    "Gigafactory execution risk any delay in domestic cell manufacturing extends import dependency."
)

_OPERATIONAL_CIM = (
    "Operational Due Diligence Manufacturing, Service & Execution Review "
    "Monthly Production Capacity (Units) 30,000 26,500 -11.7% Below Target "
    "Capacity Utilization (%) 80% 71% -9 pp Monitor "
    "Defect Rate (units per 1000) < 8 13.2 +65% At Risk "
    "On-Time Delivery Rate (%) > 90% 78% -12 pp At Risk "
    "Customer Complaint Resolution (Days) < 5 8.3 +66% At Risk "
    "Parts Stockout Rate (%) < 3% 11.2% +8.2 pp At Risk "
    "Operational Risk Matrix Risk Likelihood Impact Mitigation Plan "
    "Production bottlenecks at Phase 2 transition Medium High Parallel ramp "
    "Spare parts shortage (imported) High High Domestic sourcing acceleration "
    "Service center quality inconsistency High Medium Standard training + audit "
    "Battery thermal incidents Low Very High BMS OTA updates + recall protocol "
    "Labor disputes at Futurefactory Low High IR team; welfare programs "
    "ERP/MES system downtime Medium Medium Redundancy + DR systems "
    "Operational risk rating: HIGH. Service Excellence program targeting resolution by Q4 FY2025."
)

_FINANCIAL_CIM = (
    "Financial Due Diligence Profit & Loss Summary "
    "Gross Margin (%) -37.5% 7.9% 7.1% 12.5% 20.0% "
    "Cost of Goods Sold (11) (420) (2,443) (4,288) (6,560) "
    "Customer Acquisition Cost (CAC) INR 4,200 "
    "Estimated 3-Year LTV (Vehicle + Ecosystem) INR 1,12,860."
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_supplier_dependence_parses_vendors() -> None:
    spec = extract_ops_spec(
        "supplier_dependence",
        _MANUFACTURING_CIM,
        sources=["12_Manufacturing_Supply_Chain_Review.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["track"] == "D"
    assert spec["extractor"] == "heuristic_v1"
    names = [v["name"] for v in spec["vendors"]]
    assert "CATL" in names
    assert "Samsung SDI" in names
    catl = next(v for v in spec["vendors"] if v["name"] == "CATL")
    assert catl["country"] == "China"
    assert catl["annual_value_inr_cr"] == 480.0
    assert any("china" in f.lower() for f in spec["concentration_flags"])
    findings = findings_from_ops_spec("supplier_dependence", spec)
    assert any("CATL" in f for f in findings)


def test_cost_structure_bom_and_margin() -> None:
    text = _MANUFACTURING_CIM + " " + _FINANCIAL_CIM
    spec = extract_ops_spec(
        "cost_structure",
        text,
        sources=["12_Manufacturing_Supply_Chain_Review.pdf", "05_Financial_Due_Diligence.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    cats = [b["category"] for b in spec["bom_components"]]
    assert "Battery Pack" in cats
    battery = next(b for b in spec["bom_components"] if b["category"] == "Battery Pack")
    assert battery["share_pct"] == 38.0
    assert spec["cost_metrics"].get("gross_margin_pct") == 12.5
    assert spec["cost_metrics"].get("cogs_per_unit_inr") == 55_000.0


def test_operational_risk_kpis_and_matrix() -> None:
    spec = extract_ops_spec(
        "operational_risk",
        _OPERATIONAL_CIM,
        sources=["07_Operational_Due_Diligence.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    kpis = [g["kpi"] for g in spec["kpi_gaps"]]
    assert any("Defect Rate" in k for k in kpis)
    assert any("Stockout" in k for k in kpis)
    risks = [r["risk"] for r in spec["risk_items"]]
    assert any("Production bottlenecks" in r for r in risks)
    assert any("HIGH" in n.upper() for n in spec["integrity_notes"])


def test_supply_chain_resilience_logistics() -> None:
    spec = extract_ops_spec(
        "supply_chain_resilience",
        _MANUFACTURING_CIM,
        sources=["12_Manufacturing_Supply_Chain_Review.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    metrics = spec["logistics_metrics"]
    assert metrics.get("dio_days") == 68.0
    assert metrics.get("dpo_days") == 38.0
    assert metrics.get("lead_time_days") == 22.0
    assert metrics.get("stockout_actual_pct") == 11.2
    assert len(spec["localization_milestones"]) >= 2
    assert any("FY2024" in m for m in spec["localization_milestones"])


def test_ops_agents_live_on_vdr() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Ops Slice4", "slug": "ops-slice4", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        files = [
            ("12_Manufacturing_Supply_Chain_Review.txt", _MANUFACTURING_CIM.encode()),
            ("07_Operational_Due_Diligence.txt", _OPERATIONAL_CIM.encode()),
            ("05_Financial_Due_Diligence.txt", _FINANCIAL_CIM.encode()),
        ]
        for name, body in files:
            upload = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (name, BytesIO(body), "text/plain")},
            )
            assert upload.status_code == 200

        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        ).status_code == 202
        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "foundations"},
        ).status_code == 202

        for slug in OPS_SLUGS:
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            )
            assert run.status_code == 202, slug

        for slug in OPS_SLUGS:
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200, slug
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["stub"] is False
            assert payload["slice"] == "deep_dive_s4"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False, slug
            assert payload["spec"]["extractor"] == "heuristic_v1"
            assert payload["findings"]

        vendor = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/supplier_dependence/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert vendor["spec"]["metrics"]["vendor_count"] >= 3

        cost = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/cost_structure/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert cost["spec"]["cost_metrics"].get("gross_margin_pct") == 12.5


def test_ops_extractors_on_test1_vdr_snippets() -> None:
    """Regression against real Test1 library text when present locally."""
    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test1" / "library" / "documents"
    mfg_path = root / "12_Manufacturing_Supply_Chain_Review.json"
    ops_path = root / "07_Operational_Due_Diligence.json"
    if not mfg_path.is_file() or not ops_path.is_file():
        return
    mfg = json.loads(mfg_path.read_text(encoding="utf-8"))["text"]
    ops = json.loads(ops_path.read_text(encoding="utf-8"))["text"]
    supplier = extract_ops_spec("supplier_dependence", mfg, coverage="full")
    assert supplier["metrics"]["vendor_count"] >= 5
    resilience = extract_ops_spec("supply_chain_resilience", mfg, coverage="full")
    assert resilience["logistics_metrics"].get("dio_days") == 68.0
    risk = extract_ops_spec("operational_risk", ops, coverage="full")
    assert risk["metrics"]["risk_item_count"] >= 3


def test_vendor_parser_handles_decimal_values_and_column_reorder() -> None:
    standard = (
        "Acme Cloud Hosting Infrastructure USA ~12.5 Medium Yes "
        "Globex Analytics API Gateway Singapore ~8.2 Low Partial"
    )
    country_first = (
        "Stripe Payments USA Payment Processing ~45.5 High Yes "
        "Twilio Communications UK SMS/Voice APIs ~22.1 Medium No"
    )
    spec_std = extract_ops_spec("supplier_dependence", standard, coverage="full")
    spec_cf = extract_ops_spec("supplier_dependence", country_first, coverage="full")
    assert spec_std["empty"] is False
    assert spec_cf["empty"] is False
    acme = next(v for v in spec_std["vendors"] if "Acme" in v["name"])
    assert acme["annual_value_inr_cr"] == 12.5
    stripe = next(v for v in spec_cf["vendors"] if "Stripe" in v["name"])
    assert stripe["country"] == "USA"
    assert stripe["annual_value_inr_cr"] == 45.5


def test_findings_from_ops_spec_safe_metric_formatting() -> None:
    spec = {
        "cost_metrics": {"gross_margin_pct": 12.5, "note": "FY2024E"},
        "bom_components": [],
        "efficiency_notes": [],
    }
    findings = findings_from_ops_spec("cost_structure", spec)
    assert "gross_margin_pct: 12.5" in findings
    assert "note: FY2024E" in findings

    resilience = {
        "logistics_metrics": {"dio_days": 68, "vendor": "3PL"},
        "localization_milestones": [],
        "resilience_notes": [],
    }
    res_findings = findings_from_ops_spec("supply_chain_resilience", resilience)
    assert "dio_days: 68" in res_findings
    assert "vendor: 3PL" in res_findings
