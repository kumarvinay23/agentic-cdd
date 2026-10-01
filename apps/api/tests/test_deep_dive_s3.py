"""Slice 3 — Customer Analysis Deep Dive extractors."""

from __future__ import annotations

import json
from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_customer import CUSTOMER_SLUGS, extract_customer_spec
from agetic_cdd_api.services_deals import ensure_deal_folder

COMMERCIAL_CIM = (
    "04 Commercial Due Diligence Market, Sales & Customer Analysis "
    "Customer Profile & Segmentation Segment Share (%) Avg Age Primary Use Case Key Driver "
    "Urban Professional 38% 27–35 Daily Commute Cost savings + tech "
    "Student / Young Adult 22% 18–26 College/Short trips Aspirational brand "
    "Gig Economy Worker 18% 25–40 Delivery/Ride TCO advantage "
    "Family User 14% 35–50 Family errands Safety + range "
    "Fleet Operator 8% N/A Commercial fleet B2B economics "
    "Customer Acquisition & Retention Metric Ola Electric Ather Energy TVS iQube Industry Avg "
    "CAC (INR) 4,200 6,500 8,200 6,800 NPS Score 34 61 48 42 "
    "Retention Rate (12M) 61% 74% 69% 71% Avg Ticket Size (INR) 96,500 1,44,000 1,08,000 1,10,000 "
    "Time to Purchase (Days) 3.1 5.8 7.2 6.1 Service Satisfaction (%) 52% 78% 71% 68% "
    "Geographic Sales Distribution (FY2024E) Region Revenue Share (%) "
    "South India (TN, KA, AP, TS) 34% 36% +92% West India (MH, GJ) 28% 27% +78% "
    "North India (DL, UP, HR, RJ) 24% 24% +105% East India (WB, OR, AS) 9% 9% +123% "
    "Central India & Others 5% 4% +88% "
    "Channel Strategy Assessment Ola Electric employs a direct-to-consumer digital-first model "
    "supplemented by physical experience centers. The online funnel captures ~68% of orders with a "
    "3.1-day average conversion cycle. The experience center network (600+ locations) drives test rides. "
    "Commercial Risks NPS significantly below category leaders — indicates service experience gap. "
    "Service satisfaction at 52% well below the 68% industry average — reputational risk. "
    "Repeat purchase rate of 22% vs 35% industry average signals loyalty deficit. "
    "Online-heavy model limits reach in Tier-3 and rural markets. "
    "Brand Equity Among Youth Ola Electric commands strong awareness (92% aided recall) among "
    "18–35 urban consumers — the fastest-growing buyer segment for personal EVs."
)

RETENTION_CIM = (
    "Valuation, Retention & Comparable Analysis Customer Retention & Churn Performance "
    "The company's current 61% 12-month retention rate significantly lags the 71% industry average. "
    "Core Retention Metrics Metric Ola Electric (Est.) "
    "Gross Revenue Retention (GRR) 74% FY22: 68% → FY23: 71% → FY24: 74% 82% (sector avg) "
    "Net Revenue Retention (NRR) 81% FY22: 72% → FY23: 78% → FY24: 81% 95% (sector avg) "
    "Logo Churn (%) 39% FY22: 45% → FY23: 42% → FY24: 39% 29% (industry avg) "
    "Revenue Churn (%) 26% FY22: 32% → FY23: 29% → FY24: 26% 18% (sector avg) "
    "12-Month Customer Retention Rate 61% FY22: 55% → FY23: 58% → FY24: 61% 71% (industry avg) "
    "Repurchase Rate (Same Brand) 22% FY22: N/A → FY23: 18% → FY24: 22% 35% (sector avg) "
    "Root Cause Analysis — Churn Drivers "
    "Service Delay & Unresolved Complaints 31% Critical Service Excellence program initiated "
    "Software Bugs / Feature Gaps (MoveOS) 18% High OTA update cadence increased "
    "Battery Performance Below Expectations 16% High Gen 2 battery + BMS OTA fix "
    "Competitive Product Launch (TVS, Ather) 14% Medium Pricing and feature parity push "
    "Spare Parts Unavailability 11% High Inventory buffer expansion "
    "Price Increase / Subsidy Reduction 6% Medium S1 X entry-level launch "
    "Lifestyle / Need Change 4% Low N/A (natural attrition) "
    "Customer Cohort Retention Analysis Acquisition Cohort Cohort Size (Units) "
    "M-6 Retention M-12 Retention M-36 Retention (Est.) "
    "Q1 FY2022 (Launch Cohort) 4,200 82% 68% 41% "
    "Q3 FY2022 6,100 80% 65% 38% "
    "Q1 FY2023 18,400 78% 62% 36% "
    "Q3 FY2024 (Latest) 68,500 81% 65% N/A "
    "Financing Lock-in (EMI Customers) ~54% of customers purchase via EMI (12–48 months). "
    "EMI customers show 18% higher 12-month retention than outright buyers. "
    "Digital Ecosystem Stickiness MoveOS app required for vehicle features. "
    "Fleet segment (8% of revenue) offers more predictable renewal visibility than retail. "
    "Customer Acquisition Cost (CAC) INR 4,200 INR 6,800 (avg) Below avg — efficient digital funnel "
    "Estimated 3-Year LTV (Vehicle + Ecosystem) INR 1,12,860. LTV / CAC Ratio 26.9x."
)

COMPETITOR_PRIOR = {
    "competitors": [
        {"name": "Ola Electric", "nps": 34.0, "market_share_pct": 32.0},
        {"name": "Ather Energy", "nps": 61.0, "market_share_pct": 12.0},
        {"name": "TVS iQube", "nps": 48.0, "market_share_pct": 18.0},
    ]
}

SHARE_PRIOR = {
    "wins": ["Ola Electric: Strong Gain (share 32%)"],
    "losses": ["Share pressure · Hero Vida: Gaining (share 8%)"],
}


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_customer_segmentation_parses_segments() -> None:
    spec = extract_customer_spec(
        "customer_segmentation",
        COMMERCIAL_CIM,
        sources=["04_Commercial_Due_Diligence.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["extractor"] == "heuristic_v1"
    assert spec["track"] == "C"
    names = [s["name"] for s in spec["segments"]]
    assert "Urban Professional" in names
    urban = next(s for s in spec["segments"] if s["name"] == "Urban Professional")
    assert urban["share_pct"] == 38.0
    assert any("South India" in g for g in (spec.get("geo_mix") or []))
    assert any(
        "urban" in n.lower() or "18" in n or "buyer" in n.lower()
        for n in (spec.get("icp_notes") or [])
    )


def test_stickiness_retention_and_cohorts() -> None:
    spec = extract_customer_spec(
        "customer_stickiness",
        RETENTION_CIM,
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    metrics = spec["retention_metrics"]
    assert metrics["grr_pct"] == 74.0
    assert metrics["nrr_pct"] == 81.0
    assert metrics["logo_churn_pct"] == 39.0
    assert metrics["retention_12m_pct"] == 61.0
    assert metrics["repurchase_pct"] == 22.0
    assert len(spec["cohorts"]) >= 3
    first = spec["cohorts"][0]
    assert "Q1 FY2022" in first["cohort"]
    assert first["m12_retention_pct"] == 68.0


def test_satisfaction_and_buying_behavior() -> None:
    sat = extract_customer_spec(
        "customer_satisfaction",
        COMMERCIAL_CIM + "\n" + RETENTION_CIM,
        sources=["commercial.txt", "retention.txt"],
        coverage="full",
        prior_spec=COMPETITOR_PRIOR,
    )
    assert sat["empty"] is False
    assert sat["nps"] == 34.0
    assert sat["service_satisfaction_pct"] == 52.0
    assert any(d["driver"].startswith("Service Delay") for d in sat["churn_drivers"])
    assert any("Ather Energy" in p and "61" in p for p in sat["peer_nps"])
    assert all("Glassdoor" not in n for n in (sat.get("satisfaction_notes") or []))

    buy = extract_customer_spec(
        "buying_behavior",
        COMMERCIAL_CIM + "\n" + RETENTION_CIM,
        sources=["commercial.txt", "retention.txt"],
        coverage="full",
        prior_spec=SHARE_PRIOR,
    )
    assert buy["empty"] is False
    assert buy["buying_metrics"].get("online_sales_pct") == 68.0
    assert buy["buying_metrics"].get("emi_purchase_pct") == 54.0
    assert buy["buying_metrics"].get("fleet_revenue_pct") == 8.0
    assert buy["segment_hhi"] is not None
    assert buy["segment_hhi"] > 2000
    assert any("Urban Professional" in f for f in buy["concentration_flags"])
    assert any("digital-first" in c.lower() or "experience" in c.lower() for c in buy["channel_mix"])
    assert any("Share context" in n or "Strong Gain" in n for n in buy["behavior_notes"])
    # Flag off by default → pure heuristic.
    assert sat["extractor"] == "heuristic_v1"
    assert sat.get("llm_refined") is False
    assert buy["extractor"] == "heuristic_v1"


def test_hybrid_refine_satisfaction_and_buying(monkeypatch) -> None:
    """When AGETIC_CDD_DEEP_DIVE_LLM is on, Gemini refine merges grounded prose."""
    from agetic_cdd_api import deep_dive_llm as ddl
    from agetic_cdd_api.settings import settings

    monkeypatch.setattr(settings, "deep_dive_llm", True)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def fake_generate_json(*, system: str, user: str, temperature: float = 0.2):
        if "satisfaction" in system.lower() or "AGENT_SLUG: customer_satisfaction" in user:
            return {
                "satisfaction_notes": [
                    "NPS significantly below category leaders — indicates service experience gap.",
                    "Service satisfaction at 52% well below the 68% industry average — reputational risk.",
                ],
                "churn_drivers": [
                    {
                        "driver": "Service Delay & Unresolved Complaints",
                        "contribution_pct": 31,
                        "severity": "Critical",
                    },
                    {
                        "driver": "Software Bugs / Feature Gaps (MoveOS)",
                        "contribution_pct": 18,
                        "severity": "High",
                    },
                ],
            }
        return {
            "concentration_flags": [
                "Top segment concentration: Urban Professional at 38%.",
                "Online sales mix 68% creates channel concentration in digital funnel.",
            ],
            "channel_mix": [
                "Ola Electric employs a direct-to-consumer digital-first model supplemented by physical experience centers."
            ],
            "behavior_notes": [
                "Share context · Ola Electric: Strong Gain (share 32%)",
                "The online funnel captures ~68% of orders with a 3.1-day average conversion cycle.",
            ],
        }

    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.generate_json",
        fake_generate_json,
    )
    # Also patch the import path used after lazy import inside refine.
    monkeypatch.setattr(ddl, "deep_dive_llm_enabled", lambda: True)

    # Re-bind generate_json on the module used after import inside refine_customer_spec
    import agetic_cdd_api.services_gemini as gem

    monkeypatch.setattr(gem, "generate_json", fake_generate_json)

    sat = extract_customer_spec(
        "customer_satisfaction",
        COMMERCIAL_CIM + "\n" + RETENTION_CIM,
        sources=["commercial.txt"],
        coverage="full",
        prior_spec=COMPETITOR_PRIOR,
    )
    assert sat["extractor"] == "hybrid_v1"
    assert sat["llm_refined"] is True
    assert sat["nps"] == 34.0  # numeric lock
    assert any("service experience gap" in n.lower() for n in sat["satisfaction_notes"])
    assert sat["churn_drivers"][0]["contribution_pct"] == 31.0

    buy = extract_customer_spec(
        "buying_behavior",
        COMMERCIAL_CIM + "\n" + RETENTION_CIM,
        sources=["commercial.txt"],
        coverage="full",
        prior_spec=SHARE_PRIOR,
    )
    assert buy["extractor"] == "hybrid_v1"
    assert buy["llm_refined"] is True
    assert buy["buying_metrics"]["online_sales_pct"] == 68.0  # numeric lock
    assert buy["segment_hhi"] is not None
    assert any("Urban Professional" in f for f in buy["concentration_flags"])


def test_hybrid_falls_back_when_gemini_fails(monkeypatch) -> None:
    from agetic_cdd_api.settings import settings

    monkeypatch.setattr(settings, "deep_dive_llm", True)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.generate_json",
        lambda **_kwargs: None,
    )

    sat = extract_customer_spec(
        "customer_satisfaction",
        COMMERCIAL_CIM + "\n" + RETENTION_CIM,
        sources=["commercial.txt"],
        coverage="full",
        prior_spec=COMPETITOR_PRIOR,
    )
    assert sat["extractor"] == "heuristic_v1"
    assert sat.get("llm_refined") is False
    assert sat["nps"] == 34.0


def test_customer_agents_live_on_vdr() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Cust Slice3", "slug": "cust-slice3", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        files = [
            ("04_Commercial_Due_Diligence.txt", COMMERCIAL_CIM.encode()),
            ("13_Valuation_Retention_Comparable_Analysis.txt", RETENTION_CIM.encode()),
            (
                "11_Market_Competition_Analysis.txt",
                (
                    "Dimension Ola Electric Ather Energy TVS iQube "
                    "Market Share (FY2024E) ~32% ~12% ~18% "
                    "NPS Score 34 61 48 "
                    "Market Share Trend Company FY2022 FY2023 FY2024E Trend "
                    "Ola Electric 8% 27% 32% Strong Gain "
                    "Ather Energy 18% 14% 12% Losing Share "
                    "Hero Vida 0% 4% 8% Gaining"
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

        # Upstream deps for satisfaction / buying behavior.
        for slug in ("competitor_identification", "market_share_strategy"):
            assert client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            ).status_code == 202

        for slug in CUSTOMER_SLUGS:
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            )
            assert run.status_code == 202, slug

        for slug in CUSTOMER_SLUGS:
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200, slug
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["stub"] is False
            assert payload["slice"] == "deep_dive_s3"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False, slug
            assert payload["spec"]["extractor"] in {"heuristic_v1", "hybrid_v1"}
            assert payload["findings"]

        seg = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/customer_segmentation/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert seg["spec"]["segments"][0]["share_pct"] == 38.0

        stick = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/customer_stickiness/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert stick["spec"]["retention_metrics"]["nrr_pct"] == 81.0

        store_path = ensure_deal_folder("cust-slice3") / "library" / "deep_dive_findings.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        for slug in CUSTOMER_SLUGS:
            entry = store["agents"][slug]
            assert entry["status"] == "completed"
            assert entry["spec"]["empty"] is False
