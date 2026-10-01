"""Slice 2 — Competitive Landscape Deep Dive extractors."""

from __future__ import annotations

import json
from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_competitive import COMPETITIVE_SLUGS, extract_competitive_spec
from agetic_cdd_api.services_deals import ensure_deal_folder

COMPETITION_CIM = (
    "Competitive Landscape Matrix Insight Snapshot: Head-to-head benchmarking of key competitors "
    "across strategic dimensions. Dimension Ola Electric Ather Energy TVS iQube Bajaj Chetak Hero Vida "
    "Market Share (FY2024E) ~32% ~12% ~18% ~9% ~8% Units Sold (FY2024E, 000s) ~320 ~114 ~171 ~85 ~76 "
    "Flagship Price (INR) 1,47,499 1,54,999 1,24,999 1,30,000 1,06,000 Range (km, claimed) 195 146 145 126 165 "
    "Software / OTA Yes (MoveOS) Yes (Atherstack) Basic Basic Yes Fast Charging Yes Yes Yes No Yes "
    "Dealer/Service Network Digital-first Service-led Dealer (TVS) Dealer (Bajaj) Dealer (Hero) "
    "NPS Score 34 61 48 52 44 Valuation (USD B) ~4.1B ~1.2B Part of TVS Part of Bajaj Part of Hero "
    "Porter's Five Forces Analysis Threat of New Entrants — MEDIUM High capital requirements and technology "
    "complexity create barriers. However, Chinese OEMs (Yadea, NIU) and new Indian startups continue to enter. "
    "Bargaining Power of Suppliers — HIGH Lithium-ion cells from Korea/China create concentrated supplier risk. "
    "Bargaining Power of Buyers — MEDIUM Individual consumers have low individual power but collectively high. "
    "Threat of Substitutes — LOW-MEDIUM ICE scooters remain a substitute where range anxiety persists. "
    "Competitive Rivalry — HIGH Intense rivalry with 10+ meaningful players. Legacy OEMs with deep pockets. "
    "Market Share Trend Company FY2022 FY2023 FY2024E Trend Ola Electric 8% 27% 32% Strong Gain "
    "TVS iQube 12% 17% 18% Steady Growth Ather Energy 18% 14% 12% Losing Share Bajaj Chetak 22% 11% 9% Declining "
    "Hero Vida 0% 4% 8% Gaining Ampere (Greaves) 15% 8% 6% Declining Others 25% 19% 15% Fragmented "
    "Competitive Verdict Ola Electric holds the leading market share position in India's E2W segment and "
    "benefits from superior software capabilities and manufacturing scale ambition. However, the competitive "
    "moat is narrowing as legacy OEMs invest aggressively. The key battleground is service reliability — where "
    "Ola Electric currently underperforms. Sustained market leadership requires operational execution "
    "improvements alongside continued product and technology investment."
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_competitor_identification_parses_matrix() -> None:
    spec = extract_competitive_spec(
        "competitor_identification",
        COMPETITION_CIM,
        sources=["11_Market_Competition_Analysis.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["extractor"] == "heuristic_v1"
    assert spec["track"] == "B"
    names = [c["name"] for c in spec["competitors"]]
    assert "Ola Electric" in names
    assert "Ather Energy" in names
    ola = next(c for c in spec["competitors"] if c["name"] == "Ola Electric")
    assert ola["market_share_pct"] == 32.0
    assert ola["units_000s"] == 320.0
    assert ola["flagship_price_inr"] == 147499.0
    assert ola["trend"] == "Strong Gain"
    assert any("leading market share" in n.lower() for n in (spec.get("positioning_notes") or []))
    assert all(
        "requires operational" not in n.lower() for n in (spec.get("positioning_notes") or [])
    )
    # Share-desc order: Ola (32) before TVS (18) before Ather (12).
    shares = [c["market_share_pct"] for c in spec["competitors"] if c.get("market_share_pct") is not None]
    assert shares == sorted(shares, reverse=True)


def test_landscape_order_agnostic_and_no_fake_peers() -> None:
    """Metric rows parse when reordered; absent OEMs are not invented."""
    reordered = (
        "Dimension Acme Mobility Beta Motors Gamma Scooters "
        "Flagship Price (INR) 99,000 88,000 77,000 "
        "Units Sold (FY2024E, 000s) ~10 ~20 ~30 "
        "Market Share (FY2024E) ~40% ~35% ~25% "
        "Software / OTA Yes (AcmeOS) Basic No "
        "NPS Score 50 40 30 "
        "Porter's Five Forces Analysis Threat of New Entrants — HIGH Barriers remain low in this niche."
    )
    spec = extract_competitive_spec(
        "competitor_identification",
        reordered,
        sources=["alt.txt"],
        coverage="full",
    )
    assert spec["empty"] is False
    names = [c["name"] for c in spec["competitors"]]
    assert "Ola Electric" not in names  # must not inject sector defaults
    assert len(spec["competitors"]) >= 3
    first = spec["competitors"][0]
    assert first["market_share_pct"] == 40.0
    assert first["units_000s"] == 10.0
    assert first["flagship_price_inr"] == 99000.0


def test_share_strategy_wins_losses_and_swot() -> None:
    share = extract_competitive_spec(
        "market_share_strategy",
        COMPETITION_CIM,
        sources=["competition.txt"],
        coverage="full",
    )
    assert share["empty"] is False
    assert any("Ola Electric" in w and "Strong Gain" in w for w in share["wins"])
    assert any("Ather Energy" in w and "Losing" in w for w in share["wins"] + share["losses"])
    assert all("Others" not in w for w in share["wins"] + share["losses"])
    assert all("Steady Growth" not in w for w in share["wins"] + share["losses"])
    assert all("Fragmented" not in w for w in share["wins"] + share["losses"])
    assert all(
        "service reliability" not in n.lower() for n in (share.get("strategy_notes") or [])
    )
    assert all(
        "requires operational" not in n.lower() for n in (share.get("strategy_notes") or [])
    )
    assert any("leading" in n.lower() or "share" in n.lower() for n in (share.get("strategy_notes") or []))
    assert any("Share opportunity" in w for w in share["wins"])
    assert any("Share pressure" in w for w in share["losses"])

    diff = extract_competitive_spec(
        "competitive_differentiation",
        COMPETITION_CIM,
        sources=["competition.txt"],
        coverage="full",
    )
    assert diff["empty"] is False
    assert any("software" in d.lower() or "scale" in d.lower() for d in (diff.get("differentiators") or []))
    assert any("moat" in m.lower() for m in (diff.get("moat_signals") or []))
    assert all("underperform" not in m.lower() for m in (diff.get("moat_signals") or []))
    assert all("service reliability" not in m.lower() for m in (diff.get("moat_signals") or []))
    assert any("NPS gap" in f or "service reliability" in f.lower() for f in (diff.get("feature_gaps") or []))
    assert any("MoveOS" in s for s in (diff.get("peer_software") or []) + (diff.get("differentiators") or []))
    assert all("Threat of Substitutes" not in d for d in (diff.get("differentiators") or []))
    assert all("Threat of Substitutes" not in d for d in (diff.get("moat_signals") or []))
    # Summary should not lead with moat erosion.
    findings_lead = (diff.get("differentiators") or [""])[0].lower()
    assert "narrowing" not in findings_lead

    swot = extract_competitive_spec(
        "swot_analysis",
        COMPETITION_CIM,
        sources=["competition.txt"],
        coverage="full",
    )
    assert swot["empty"] is False
    assert swot["porter_forces"]
    assert any(p["force"].startswith("Competitive Rivalry") for p in swot["porter_forces"])
    assert swot["strengths"] or swot["weaknesses"]
    assert any("underperform" in w.lower() or "moat" in w.lower() or "nps" in w.lower() for w in swot["weaknesses"] + swot["threats"])
    assert all("requires operational" not in s.lower() for s in (swot.get("strengths") or []))
    # Moat narrowing belongs in threats, not duplicated as weakness.
    assert all("moat is narrowing" not in w.lower() for w in (swot.get("weaknesses") or []))
    assert any("moat is narrowing" in t.lower() or "Rivalry" in t for t in (swot.get("threats") or []))


def test_competitive_agents_live_on_vdr() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Comp Slice2", "slug": "comp-slice2", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        files = [
            ("11_Market_Competition_Analysis.txt", COMPETITION_CIM.encode()),
            (
                "02_Corporate_Overview.txt",
                b"Ola Electric Mobility Limited is headquartered in Bengaluru. Founded in 2017.",
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

        for slug in COMPETITIVE_SLUGS:
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            )
            assert run.status_code == 202, slug

        for slug in COMPETITIVE_SLUGS:
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200, slug
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["stub"] is False
            assert payload["slice"] == "deep_dive_s2"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False, slug
            assert payload["spec"]["extractor"] == "heuristic_v1"
            assert payload["findings"]

        ident = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/competitor_identification/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert ident["spec"]["competitors"][0]["market_share_pct"] == 32.0

        store_path = ensure_deal_folder("comp-slice2") / "library" / "deep_dive_findings.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        for slug in COMPETITIVE_SLUGS:
            entry = store["agents"][slug]
            assert entry["status"] == "completed"
            assert entry["spec"]["empty"] is False
