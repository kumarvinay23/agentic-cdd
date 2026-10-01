"""Slice 1 — Market Analysis Deep Dive extractors."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_extractors import MARKET_SLUGS, extract_deep_dive_spec
from agetic_cdd_api.pipeline_catalog import PHASE3_AGENT_KEYS
from agetic_cdd_api.services_deals import ensure_deal_folder

MARKET_CIM = (
    "India's two-wheeler (2W) market represents approximately 18–20 million units annually, "
    "making it the largest in the world. The Total Addressable Market (TAM) for the Indian 2W "
    "industry is valued at USD 24.5 billion in FY2024 and is projected to expand at a ~13.8% CAGR "
    "to reach USD 41.2 billion by FY2028E. Driven by macro tailwinds—including high petrol prices, "
    "urbanization, and government incentives such as FAME-II and PLI schemes—EV penetration in the "
    "2W segment is expected to rise sharply from ~6% in FY2024 to 35–40% by FY2030. "
    "The EV 2W Serviceable Addressable Market (SAM) is expanding at a ~57.6% CAGR, rising from "
    "USD 1.5 billion in FY2024 to USD 14.4 billion by FY2028E. The target Serviceable Obtainable "
    "Market (SOM) for Ola Electric is forecasted to grow from USD 0.6 billion to USD 4.2 billion "
    "over the same timeframe (~55.1% CAGR)."
)

PRICING = (
    "Van Westendorp optimal price point analysis places willingness to pay near INR 120000. "
    "Average selling price (ASP) is priced at INR 95000 for the base scooter. "
    "Pricing power remains moderate amid discount intensity from Bajaj and TVS."
)

GEO = (
    "Sales by region show urban South and West India driving demand, while rural North remains "
    "cyclical and sensitive to monsoon and fuel-price headwinds. Geographic mix is a demand driver."
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_market_extractor_edge_cases() -> None:
    """Currency mapping, alternate sizing formats, and word-boundary keyword hits."""
    from agetic_cdd_api.deep_dive_extractors import _extract_prices, _hits, extract_deep_dive_spec

    # No currency symbol → UNKNOWN (not silently USD).
    bare = _extract_prices("The scooter is priced at 50,000 after discounts.")
    assert bare and bare[0].unit == "UNKNOWN"

    eur = _extract_prices("Average selling price ASP is EUR 1200 for the EU trim.")
    assert eur and eur[0].unit == "EUR" and eur[0].value == 1200.0

    # Compact thesis table + ASP table form + no CAGR bleed into penetration.
    thesis_table = (
        "TAM / SAM / SOM Analysis. Market Segment FY2024 Size FY2028E Size CAGR "
        "TAM — India 2W Market USD 24.5B USD 41.2B ~13.8% "
        "SAM — EV 2W Segment USD 1.5B USD 14.4B ~57.6% "
        "SOM — Ola Electric Target USD 0.6B USD 4.2B ~55.1%. "
        "EV penetration in the two-wheeler segment stood at ~6% in FY2024 "
        "and is projected to reach 35–40% by FY2030 per NITI Aayog."
    )
    compact = extract_deep_dive_spec(
        "market_volume_and_growth",
        thesis_table,
        sources=["03_Investment_Thesis.pdf"],
        coverage="full",
    )
    assert compact["tam"]["value"] == 24.5
    assert compact["sam"]["value"] == 1.5
    assert compact["som"]["value"] == 0.6
    assert 13.8 in compact["cagr_pct"]
    assert 6.0 in compact["penetration_pct"]
    assert 55.1 not in compact["penetration_pct"]
    assert 55.0 not in compact["penetration_pct"]

    asp_table = _extract_prices(
        "Avg Selling Price (INR 000s) ~95 ~96.5 ~98.2 ~80 Revenue (INR Cr) 190"
    )
    assert asp_table and asp_table[0].unit == "INR"
    assert asp_table[0].value == 98200.0  # FY2024E ~98.2 × 1000 (000s scale)
    assert "industry_asp=80000" in (asp_table[0].raw or "")

    # Alternate sizing: 50B USD / crore notation.
    alt = extract_deep_dive_spec(
        "market_volume_and_growth",
        "TAM is estimated at 50B USD for FY2025. SAM stands near ₹5,000 Cr domestically.",
        sources=["alt.txt"],
        coverage="full",
    )
    assert alt["tam"]["value"] == 50.0
    assert alt["tam"]["scale"] == "billion"
    assert alt["tam"]["unit"] == "USD"
    assert alt["sam"]["value"] == 5000.0
    assert alt["sam"]["unit"] == "INR"
    assert alt["sam"]["scale"] == "crore"

    # Word boundaries: "events" must not match "ev"; "geography" matches via geography needle.
    sentences = [
        "Company events calendar has no market signal.",
        "EV two-wheeler demand is rising in urban India.",
        "Regional geography mix favors South and West.",
    ]
    hits = _hits(sentences, ("ev", "geography", "geo"), limit=5)
    assert any("EV two-wheeler" in h for h in hits)
    assert any("geography" in h.lower() for h in hits)
    assert not any("events calendar" in h.lower() for h in hits)


def test_market_soft_fill_tagged_not_mixed_into_vdr_text() -> None:
    """Foundation soft-fill is tagged; VDR metrics are not contaminated by foundation blobs."""
    from agetic_cdd_api.deep_dive_roles import role_by_slug
    from agetic_cdd_api.services_deep_dive import _build_market_output, _clip

    role = role_by_slug("market_volume_and_growth")
    assert role is not None

    class _Deal:
        id = "d1"
        name = "Acme"
        company = "Acme Co"

    # No VDR docs → foundation-only soft fill.
    foundation = {
        "roles": {
            "F-01": {
                "summary": (
                    "Thesis cites TAM of USD 24.5 billion and SAM of USD 1.5 billion for FY2024."
                )
            }
        }
    }
    soft = _build_market_output(
        _Deal(),  # type: ignore[arg-type]
        role=role,
        index={"documents": []},
        foundation=foundation,
        prior={},
    )
    assert soft["status"] == "empty_vdr"
    assert soft["empty_vdr"] is True
    assert soft["extract_source"] == "foundation"
    assert soft["foundation_soft_fill"] is True
    assert soft["spec"]["extract_source"] == "foundation"
    assert soft["spec"]["vdr_backed"] is False
    assert soft["spec"].get("tam") is not None

    # With VDR docs, extract_source is vdr even if foundation is present.
    index = {
        "documents": [
            {
                "filename": "Market_Stats.txt",
                "cdl_category": "market",
                "excerpt": (
                    "Total Addressable Market (TAM) is valued at USD 10.0 billion in FY2024. "
                    "Serviceable Addressable Market (SAM) is USD 2.0 billion."
                ),
            }
        ]
    }
    live = _build_market_output(
        _Deal(),  # type: ignore[arg-type]
        role=role,
        index=index,
        foundation=foundation,
        prior={},
        cache={},
    )
    assert live["status"] == "completed"
    assert live["extract_source"] == "vdr"
    assert live["foundation_soft_fill"] is False
    assert live["spec"]["vdr_backed"] is True
    assert live["spec"]["tam"]["value"] == 10.0  # not foundation's 24.5

    # Safe clip stays within limit and does not raise on unicode.
    clipped = _clip("αβγδε" * 200, 40)
    assert len(clipped) <= 40
    assert clipped.endswith("…")


def test_market_volume_extractor_tam_sam_som() -> None:
    spec = extract_deep_dive_spec(
        "market_volume_and_growth",
        MARKET_CIM,
        sources=["Market_Stats.txt"],
        coverage="full",
    )
    assert spec["extractor"] == "heuristic_v1"
    assert spec["empty"] is False
    assert spec["tam"]["value"] == 24.5
    assert spec["tam"]["scale"] == "billion"
    assert spec["sam"]["value"] == 1.5
    assert spec["som"]["value"] == 0.6
    assert 13.8 in spec["cagr_pct"] or 57.6 in spec["cagr_pct"]
    # TAM→SAM→SOM CAGRs lead the list when present.
    if 13.8 in spec["cagr_pct"] and 57.6 in spec["cagr_pct"]:
        assert spec["cagr_pct"].index(13.8) < spec["cagr_pct"].index(57.6)
    assert any(p in spec["penetration_pct"] for p in (6.0, 35.0, 40.0))
    assert 6.0 in spec["penetration_pct"]
    assert any(p in spec["penetration_pct"] for p in (35.0, 40.0))
    assert spec["metrics"]["has_tam"] is True

    noisy_vol = extract_deep_dive_spec(
        "market_volume_and_growth",
        (
            MARKET_CIM
            + " Advanced manufacturing at Futurefactory with target capacity of 10 million units p.a. "
            + "NITI Aayog projects 80% EV penetration in the 2W segment by FY2030."
        ),
        sources=["noisy.txt"],
        coverage="full",
    )
    assert all("10 million" not in u.lower() for u in (noisy_vol.get("unit_volume_notes") or []))
    assert 80.0 in (noisy_vol.get("penetration_pct") or [])


def test_market_definition_and_pricing_extractors() -> None:
    definition = extract_deep_dive_spec(
        "market_definition",
        MARKET_CIM,
        sources=["Industry_Overview.txt"],
        coverage="full",
    )
    assert definition["empty"] is False
    assert definition["macro_drivers"] or definition["policy_context"]
    assert any("fame" in x.lower() or "macro" in x.lower() or "petrol" in x.lower() for x in (
        *(definition.get("macro_drivers") or []),
        *(definition.get("policy_context") or []),
    ))
    # No competitive/company bleed; buckets are exclusive.
    all_def = (
        *(definition.get("market_framing") or []),
        *(definition.get("segments") or []),
        *(definition.get("macro_drivers") or []),
        *(definition.get("policy_context") or []),
        *(definition.get("geographies") or []),
    )
    assert all("service reliability" not in x.lower() for x in all_def)
    assert all("headquartered" not in x.lower() for x in all_def)
    assert all("founded in" not in x.lower() for x in all_def)
    seen: set[str] = set()
    for x in all_def:
        key = x.lower().strip()
        assert key not in seen, f"duplicate across buckets: {x[:80]}"
        seen.add(key)

    noisy_def = extract_deep_dive_spec(
        "market_definition",
        (
            MARKET_CIM
            + " The key battleground is service reliability — where Ola Electric currently underperforms. "
            + "Founded in 2017 and headquartered in Bengaluru, Karnataka. "
            + "Geographic Sales Distribution South India (TN, KA) 34% West India (MH, GJ) 28%. "
            + "Dependency on FAME-II and state-level subsidies; any policy reversal creates demand risk."
        ),
        sources=["noisy.txt"],
        coverage="full",
    )
    assert all(
        "service reliability" not in x.lower() and "headquartered" not in x.lower()
        for x in (
            *(noisy_def.get("market_framing") or []),
            *(noisy_def.get("geographies") or []),
        )
    )
    assert any("fame" in x.lower() or "subsidy" in x.lower() for x in (noisy_def.get("policy_context") or []))
    assert any("South India" in x for x in (noisy_def.get("geographies") or []))

    ceiling = extract_deep_dive_spec(
        "market_volume_and_growth",
        MARKET_CIM,
        sources=["Market_Stats.txt"],
        coverage="full",
    )
    pricing = extract_deep_dive_spec(
        "market_pricing",
        PRICING,
        sources=["Pricing.txt"],
        coverage="full",
        prior_spec=ceiling,
    )
    assert pricing["empty"] is False
    assert pricing["consumes_ceiling"] is True
    assert pricing["ceiling_sam"]["value"] == 1.5
    assert pricing["price_points"]
    assert pricing["price_points"][0]["unit"] == "INR"
    # Milestone / risk-matrix tables must not pollute pricing notes.
    noisy = extract_deep_dive_spec(
        "market_pricing",
        (
            "Milestone Target Year Key Driver Gross Margin > 20% FY2026 Battery localization "
            "EBITDA Breakeven FY2027 Competitive pricing strategy OEM counter-attack. "
            "Avg Selling Price (INR 000s) ~95 ~96.5 ~98.2 ~80. "
            "Flagship Price (INR) 1,47,499. "
            "Van Westendorp optimal price point analysis places willingness to pay near INR 120000."
        ),
        sources=["noise.txt"],
        coverage="full",
        prior_spec=ceiling,
    )
    assert noisy["price_points"]
    asp = next(p for p in noisy["price_points"] if p["label"] == "asp")
    assert asp["value"] == 98200.0  # FY2024E ~98.2 × 1000
    assert any(p["label"] == "flagship" and p["value"] == 147499.0 for p in noisy["price_points"])
    assert all("Milestone" not in n and "Risk Factor" not in n for n in (noisy.get("pricing_notes") or []))
    assert all("OEM counter-attack" not in n for n in (noisy.get("power_signals") or []))
    assert all(not n.lower().startswith("extracted ") for n in (noisy.get("pricing_notes") or []))
    assert any("premium" in p.lower() or "willingness" in p.lower() for p in (noisy.get("power_signals") or []) + (noisy.get("pricing_notes") or []))

    demand = extract_deep_dive_spec(
        "demand_drivers",
        GEO + " " + MARKET_CIM,
        sources=["Sales_by_Region.txt"],
        coverage="full",
        prior_spec=ceiling,
    )
    assert demand["empty"] is False
    assert demand["consumes_ceiling"] is True
    assert demand["regional_signals"] or demand["demand_drivers"]

    # Geographic sales table + no conversion-cycle / investor false positives.
    geo_table = (
        "Geographic Sales Distribution (FY2024E) Region Revenue Share (%) "
        "South India (TN, KA, AP, TS) 34% 36% +92% West India (MH, GJ) 28% 27% +78% "
        "North India (DL, UP, HR, RJ) 24% 24% +105% East India (WB, OR, AS) 9% 9% +123% "
        "Central India & Others 5% 4% +88%. "
        "Urbanization and petrol prices boost demand. "
        "Dependency on FAME-II subsidies; any policy reversal creates demand risk. "
        "High dependency on subsidies for volume — any reduction could impact demand materially. "
        "The online funnel captures ~68% of orders with a 3.1-day average conversion cycle. "
        "Investors with a 5–7 year horizon may find the risk-reward attractive."
    )
    demand2 = extract_deep_dive_spec(
        "demand_drivers",
        geo_table,
        sources=["04_Commercial_Due_Diligence.pdf"],
        coverage="full",
        prior_spec=ceiling,
    )
    assert any("South India" in s for s in (demand2.get("regional_signals") or []))
    assert any("Central India" in s for s in (demand2.get("regional_signals") or []))
    assert all("conversion cycle" not in s.lower() for s in (demand2.get("demand_drivers") or []))
    assert all("Investors with" not in s for s in (demand2.get("cycle_risks") or []))
    assert any("demand risk" in s.lower() or "fame" in s.lower() for s in (demand2.get("cycle_risks") or []))
    # Near-duplicate subsidy risks collapsed.
    subsidy_risks = [
        r for r in (demand2.get("cycle_risks") or [])
        if "subsidy" in r.lower() or "fame" in r.lower()
    ]
    assert len(subsidy_risks) <= 1


def test_market_agents_live_on_vdr() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Market Slice1", "slug": "market-slice1", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        files = [
            ("Market_Stats_TAM_SAM.txt", MARKET_CIM.encode()),
            ("Industry_Market_Overview.txt", MARKET_CIM.encode()),
            ("Van_Westendorp_Pricing.txt", PRICING.encode()),
            ("Sales_by_Region_Demand.txt", GEO.encode()),
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

        # Run Market track only (deps expand inside topo for pricing/demand).
        run = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"agent_key": "market_pricing"},
        )
        # Single-agent expands deps; also run definition + demand explicitly via phase subset.
        assert run.status_code == 202

        for slug in ("market_definition", "demand_drivers", "market_volume_and_growth"):
            client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"agent_key": slug},
            )

        for slug in MARKET_SLUGS:
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200, slug
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["stub"] is False
            assert payload["slice"] == "deep_dive_s1"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False, slug
            assert payload["spec"]["extractor"] == "heuristic_v1"
            assert payload["findings"]

        volume = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/market_volume_and_growth/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert volume["spec"]["tam"]["value"] == 24.5
        assert volume["spec"]["sam"]["value"] == 1.5

        pricing = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/market_pricing/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert pricing["spec"]["consumes_ceiling"] is True

        store_path = ensure_deal_folder("market-slice1") / "library" / "deep_dive_findings.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        track_a = store["tracks"]["A"]["agent_slugs"]
        assert set(track_a) == set(MARKET_SLUGS) or set(MARKET_SLUGS).issubset(set(track_a))
        for slug in MARKET_SLUGS:
            entry = store["agents"][slug]
            assert entry["status"] == "completed"
            assert entry["spec"]["empty"] is False

        # Sanity: Phase 3 still has 24 catalog keys.
        assert len(PHASE3_AGENT_KEYS) == 24
