"""Slice 6 — Risk & Opportunity Deep Dive extractors."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_risk import RISK_SLUGS, _safe_float, extract_risk_spec, findings_from_risk_spec

_LEGAL_CIM = (
    "Legal Due Diligence Regulatory IP Compliance Review "
    "Companies Act Compliance MCA / ROC Compliant Low "
    "SEBI LODR (Post-IPO) SEBI Compliant Low "
    "FAME-II Subsidy Claims MHI / DHI Under Review Medium "
    "CCPA Consumer Complaints CCPA Active Proceedings High "
    "Data Protection (DPDPA 2023) MeitY Implementation Ongoing Medium "
    "CCPA Class Complaint (Service Deficiency) Consumer Protection INR 120 Crore Active "
    "FAME-II Subsidy Recovery Notice Regulatory INR 300 Crore Disputed — Under Appeal "
    "Overall legal risk: Medium."
)

_THESIS_CIM = (
    "Investment Thesis Strategic Rationale Value Creation "
    "EV penetration in the two-wheeler segment stood at ~6% in FY2024 and is projected to reach 35–40% by FY2030. "
    "TAM — India 2W Market USD 24.5B USD 41.2B ~13.8% "
    "SAM — EV 2W Segment USD 1.5B USD 14.4B ~57.6% "
    "Technology-First Positioning MoveOS differentiates Ola from hardware-only competitors. "
    "Vertical Integration Strategy In-house battery cells Gigafactory motors controllers software reduce BOM costs. "
    "Scale Advantage Futurefactory 2M+ unit capacity improves gross margins from ~12% today to an estimated 22–25% by FY2027. "
    "Ecosystem Monetization charging network Hypercharger battery swapping insurance financing software subscriptions. "
    "Gross Margin > 20% FY2026 Battery localization + scale "
    "EBITDA Breakeven FY2027 Cost structure improvement "
    "Subsidy reduction / FAME-III delay Medium High "
    "OEM counter-attack (TVS, Bajaj) High Medium "
    "China supply chain disruption Medium Medium "
)

_TECH_CIM = (
    "Technical Due Diligence Software Battery R&D Assessment "
    "Vehicle OS (MoveOS) Linux-based custom OS 3.5 Stability issues in older firmware "
    "Mobile App (iOS/Android) React Native + Native modules 4.0 Battery drain reports "
    "BMS (Battery Mgmt System) In-house + Tier-1 hybrid 3.5 Thermal events in high-temp zones "
    "Cybersecurity Framework ISO 27001 (partial) 2.5 Vehicle-level pen testing gaps "
    "Technical Risks Battery thermal incidents (7.8 per 1,000 units) above acceptable thresholds "
    "Cybersecurity: Vehicle-level penetration testing not yet complete "
    "MoveOS firmware fragmentation across 5 legacy versions creates maintenance overhead "
    "Technology attrition at 31% creates IP and continuity risk in core R&D teams."
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_market_risk_regulatory_and_investment_risks() -> None:
    text = _LEGAL_CIM + " " + _THESIS_CIM
    spec = extract_risk_spec(
        "market_risk",
        text,
        sources=["06_Legal_Due_Diligence.pdf", "03_Investment_Thesis.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["track"] == "E"
    areas = [r["area"] for r in spec["regulatory_items"]]
    assert any("FAME-II" in a for a in areas)
    assert len(spec["market_risk_items"]) >= 2
    assert any("FAME" in f for f in spec["risk_flags"])
    findings = findings_from_risk_spec("market_risk", spec)
    assert any("CCPA" in f for f in findings)
    assert any("120" in lit for lit in spec["litigation_exposures"])
    assert not any("Regulatory Area Governing Body" in n for n in spec["risk_notes"])


def test_market_risk_parses_test2_legal_dd() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    legal_path = root / "06_Legal_Due_Diligence_3a5f48ed.json"
    thesis_path = root / "03_Investment_Thesis_da1b5a1a.json"
    assert legal_path.is_file()
    legal = json.loads(legal_path.read_text(encoding="utf-8"))["text"]
    thesis = json.loads(thesis_path.read_text(encoding="utf-8"))["text"] if thesis_path.is_file() else ""
    spec = extract_risk_spec(
        "market_risk",
        legal + " " + thesis,
        sources=["06_Legal_Due_Diligence.pdf", "03_Investment_Thesis.pdf"],
        coverage="full",
    )
    areas = [r["area"] for r in spec["regulatory_items"]]
    assert any("AIS 156" in a for a in areas)
    assert any("Customs" in a for a in areas)
    assert any("CCPA Class Complaint" in lit and "120" in lit for lit in spec["litigation_exposures"])
    assert len(spec["litigation_exposures"]) >= 6
    assert len(spec["market_risk_items"]) >= 2
    assert not any("Regulatory Area Governing Body" in n for n in spec["risk_notes"])


def test_internal_risk_tech_stack() -> None:
    spec = extract_risk_spec(
        "internal_risk",
        _TECH_CIM,
        sources=["08_Technical_Due_Diligence.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    names = [c["component"] for c in spec["tech_components"]]
    assert any("MoveOS" in n for n in names)
    bms = next(c for c in spec["tech_components"] if "BMS" in c["component"])
    assert bms["maturity_score"] == 3.5
    assert "thermal" in bms["key_risk"].lower()
    assert len(spec["technical_risks"]) >= 2
    assert any("attrition" in n.lower() or "maturity" in n.lower() for n in spec["scalability_notes"])


def test_internal_risk_parses_test2_technical_dd() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    tech_path = root / "08_Technical_Due_Diligence_6bfb4204.json"
    assert tech_path.is_file()
    text = json.loads(tech_path.read_text(encoding="utf-8"))["text"]
    spec = extract_risk_spec(
        "internal_risk",
        text,
        sources=["08_Technical_Due_Diligence.pdf"],
        coverage="full",
    )
    bms = next(c for c in spec["tech_components"] if "BMS" in c["component"])
    assert bms["maturity_score"] == 3.5
    assert "thermal" in bms["key_risk"].lower()
    names = [c["component"] for c in spec["tech_components"]]
    assert any("Cybersecurity Framework" in n for n in names)
    cyber = next(c for c in spec["tech_components"] if "Cybersecurity Framework" in c["component"])
    assert cyber["maturity_score"] == 2.5
    assert "pen testing" in cyber["key_risk"].lower()
    assert not any("Low maturity: BMS" in n for n in spec["scalability_notes"])
    assert all("\x7f" not in risk for risk in spec["technical_risks"])


def test_internal_risk_parses_test2_three_source_bind() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    blobs: list[str] = []
    for pat in ("08_Technical*.json", "07_Operational*.json", "12_Manufacturing*.json"):
        for path in sorted(root.glob(pat)):
            blobs.append(json.loads(path.read_text(encoding="utf-8"))["text"])
    spec = extract_risk_spec(
        "internal_risk",
        "\n".join(blobs),
        sources=[
            "08_Technical_Due_Diligence.pdf",
            "07_Operational_Due_Diligence.pdf",
            "12_Manufacturing_Supply_Chain_Review.pdf",
        ],
        coverage="full",
    )
    cyber = next(c for c in spec["tech_components"] if "Cybersecurity Framework" in c["component"])
    assert cyber["maturity_score"] == 2.5
    assert "pen testing" in cyber["key_risk"].lower()
    bms = next(c for c in spec["tech_components"] if "BMS" in c["component"])
    assert bms["maturity_score"] == 3.5


def test_growth_opportunities_levers_and_cagr() -> None:
    spec = extract_risk_spec(
        "growth_opportunities",
        _THESIS_CIM,
        sources=["03_Investment_Thesis.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    lever_names = [lv["name"] for lv in spec["growth_levers"]]
    assert "Scale Advantage" in lever_names
    assert spec["market_growth"].get("sam_cagr_pct") == 57.6
    assert spec["market_growth"].get("ev_penetration_fy2024_pct") == 6.0
    assert len(spec["milestone_targets"]) >= 2


def test_synergies_from_thesis_and_prior() -> None:
    prior = {
        "differentiators": ["MoveOS software moat", "Vertical integration on cells"],
    }
    spec = extract_risk_spec(
        "synergies",
        _THESIS_CIM,
        sources=["03_Investment_Thesis.pdf"],
        coverage="full",
        prior_spec=prior,
    )
    assert spec["empty"] is False
    assert any("Vertical Integration" in t for t in spec["synergy_themes"])
    assert any("moat" in t.lower() for t in spec["synergy_themes"])
    assert len(spec["value_milestones"]) >= 1


def test_risk_agents_live_on_vdr() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Risk Slice6", "slug": "risk-slice6", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        files = [
            ("06_Legal_Due_Diligence.txt", _LEGAL_CIM.encode()),
            ("03_Investment_Thesis.txt", _THESIS_CIM.encode()),
            ("08_Technical_Due_Diligence.txt", _TECH_CIM.encode()),
            (
                "11_Market_Competition_Analysis.txt",
                (
                    "Market Competition Analysis EV penetration growing at 55% CAGR. "
                    "Ola Electric market share 32% MoveOS differentiation."
                ).encode(),
            ),
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

        for slug in (
            "demand_drivers",
            "market_volume_and_growth",
            "market_pricing",
            "competitive_differentiation",
        ):
            assert client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            ).status_code == 202

        for slug in RISK_SLUGS:
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            )
            assert run.status_code == 202, slug

        for slug in RISK_SLUGS:
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200, slug
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["stub"] is False
            assert payload["slice"] == "deep_dive_s6"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False, slug
            assert payload["findings"]


def test_risk_extractors_on_test1_vdr_snippets() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test1" / "library" / "documents"
    legal_path = root / "06_Legal_Due_Diligence.json"
    thesis_path = root / "03_Investment_Thesis.json"
    tech_path = root / "08_Technical_Due_Diligence.json"
    if not legal_path.is_file():
        return
    legal = json.loads(legal_path.read_text(encoding="utf-8"))["text"]
    market = extract_risk_spec("market_risk", legal, coverage="full")
    assert market["metrics"]["regulatory_count"] >= 4
    if thesis_path.is_file():
        thesis = json.loads(thesis_path.read_text(encoding="utf-8"))["text"]
        growth = extract_risk_spec("growth_opportunities", thesis, coverage="full")
        assert growth["metrics"]["lever_count"] >= 3
    if tech_path.is_file():
        tech = json.loads(tech_path.read_text(encoding="utf-8"))["text"]
        internal = extract_risk_spec("internal_risk", tech, coverage="full")
        assert internal["metrics"]["component_count"] >= 3


def test_safe_float_handles_formatted_and_invalid_prior_metrics() -> None:
    assert _safe_float("12.5%") == 12.5
    assert _safe_float("N/A") is None
    assert _safe_float("") is None
    spec = extract_risk_spec(
        "growth_opportunities",
        "TAM — Global SaaS USD 10B USD 20B ~18.2%",
        coverage="partial",
        prior_spec={
            "tam_cagr_pct": "N/A",
            "sam_cagr_pct": "57.6%",
            "volume_metrics": {"market_cagr_pct": "not-a-number"},
        },
    )
    assert spec["market_growth"].get("sam_cagr_pct") == 57.6
    assert spec["market_growth"].get("tam_cagr_pct") == 18.2


def test_generic_regulatory_and_tech_fallbacks() -> None:
    legal = (
        "Legal Due Diligence Summary "
        "GDPR Data Processing Records DPA signed Compliant Low "
        "SOC 2 Type II Audit Completed Obtained Low "
    )
    market = extract_risk_spec("market_risk", legal, coverage="partial")
    assert market["empty"] is False
    assert len(market["regulatory_items"]) >= 2

    tech = (
        "Technical Assessment "
        "API Gateway (Kong) Enterprise tier 4.2 Rate limiting configured "
        "Identity Provider (Okta) SAML SSO 3.8 MFA rollout in progress "
    )
    internal = extract_risk_spec("internal_risk", tech, coverage="partial")
    assert internal["empty"] is False
    assert len(internal["tech_components"]) >= 2
