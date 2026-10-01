"""Demand Drivers — DiligenceIQ prompt-book cause → customers → cash."""

from __future__ import annotations

from agetic_cdd_api.agent_document_demand_drivers import (
    _classify_instrument,
    _heuristic_demand_drivers_spec,
    build_demand_drivers_spec,
    render_demand_drivers_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-dd-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _demand_corpus() -> str:
    return (
        "ICE two-wheeler sales ban enacted FY2025 covering Tier-1 cities; "
        "legal mandate drives fleet and retail adoption among 12 million households. "
        "Purchase subsidy / consumer incentive of INR 10,000 per unit under the "
        "2023 scheme boosts demand but does not stack with the mandate. "
        "Production-linked grant (PLI) capital support for manufacturers is separate. "
        "Corporate ESG voluntary commitments and fleet TCO / operating savings "
        "also support electrification. "
        "Transmission: customers won via dealer network converted to unit volume "
        "and ASP revenue for the company. "
        "Headwind: subsidy phase-out and monsoon seasonal cyclical slowdown. "
        "In FY2020 COVID downturn, company revenue contracted then recovered. "
        "Placeholder forthcoming policy TBD is not enacted — ignore."
    )


def test_demand_drivers_prompt_book_listed() -> None:
    system = compose_system("demand_drivers", sector="EV", geography="India")
    assert "demand_drivers" in listed_agents()
    assert "transmission" in system.lower() or "customers won" in system.lower()
    assert "do not stack" in system.lower() or "do not stack" in agent_prompt("demand_drivers").lower()
    body = agent_prompt("demand_drivers")
    assert "Ola" not in body and "SoftBank" not in body
    assert "placeholder" in body.lower()


def test_demand_drivers_composer_not_company_hardcoded() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src/agetic_cdd_api/agent_document_demand_drivers.py"
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "FAME II", "FAME-II"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("demand_drivers")
    for banned in ("Ola", "SoftBank", "FAME"):
        assert banned not in prompt


def test_instrument_classification_no_stack() -> None:
    assert _classify_instrument("ICE ban enacted as legal mandate") == "legal_mandate"
    assert _classify_instrument("purchase subsidy incentive of INR 10k") == "subsidy"
    assert _classify_instrument("production-linked grant PLI capital support") == "grant"
    assert _classify_instrument("fleet TCO operating savings payback") == "operating_saving"
    assert _classify_instrument("corporate ESG voluntary commitment pledge") == "voluntary_commitment"


def test_driver_name_word_boundary_clip() -> None:
    from agetic_cdd_api.agent_document_demand_drivers import _driver_name_from_sent

    long = (
        "Government Mandated Energy Efficiency Standard for Commercial Buildings "
        "drives demand across the addressable base without a colon delimiter"
    )
    name = _driver_name_from_sent(long)
    assert len(name) <= 80
    assert not name.endswith("Buil")  # mid-word cut avoided
    assert name.endswith("...") or " " in name
    # Delimiter path still preferred
    assert _driver_name_from_sent("Fuel cost savings: TCO advantage for fleets") == "Fuel cost savings"


def test_demand_drivers_markdown_follows_prompt_book() -> None:
    heur = _heuristic_demand_drivers_spec(
        company="Test3",
        corpus=_demand_corpus(),
        sources=["04_Commercial_Due_Diligence.pdf", "03_Investment_Thesis.pdf"],
        geography="India",
        legacy_spec={"demand_drivers": ["legacy structural demand"]},
    )
    md = render_demand_drivers_markdown("Demand Drivers", heur)

    assert "## 1. Drivers That Apply" in md
    assert "## 2. Instrument Separation" in md
    assert "## 3. Transmission Path" in md
    assert "## 4. Counter-Drivers" in md
    assert "## 5. Ranked Contribution" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "do not stack" in md.lower() or "do not stack" in str(heur).lower()
    assert any(
        isinstance(d, dict) and d.get("instrument_type") == "legal_mandate"
        for d in (heur.get("drivers") or [])
    )
    assert "placeholder" not in " ".join(
        str(d.get("driver") or "") for d in (heur.get("drivers") or []) if isinstance(d, dict)
    ).lower() or "tbd" not in " ".join(
        str(d.get("driver") or "") for d in (heur.get("drivers") or []) if isinstance(d, dict)
    ).lower()
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_placeholder_policy_dropped_in_normalise() -> None:
    from agetic_cdd_api.agent_document_demand_drivers import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "drivers": [
                {
                    "driver": "Forthcoming policy TBD",
                    "mechanism": "placeholder expected scheme",
                    "instrument_type": "subsidy",
                },
                {
                    "driver": "ICE phase-out ban",
                    "mechanism": "legal mandate enacted FY2025",
                    "effective_date": "FY2025",
                    "instrument_type": "legal_mandate",
                },
            ],
            "transmission": [],
            "counter_drivers": [],
            "ranked_contribution": [
                {"rank": "1", "driver": "ICE phase-out ban", "double_count_check": "OK"},
                {"rank": "2", "driver": "ICE phase-out ban", "double_count_check": "OK"},
            ],
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        sources=["a.pdf"],
        geography="India",
        legacy_spec=None,
    )
    names = [str(d.get("driver") or "").lower() for d in llm["drivers"]]
    assert not any("tbd" in n or "forthcoming" in n for n in names)
    assert any("phase-out" in n or "ban" in n for n in names)
    flags = [r.get("double_count_check") for r in llm["ranked_contribution"]]
    assert any("FLAG" in str(f) for f in flags)


def test_render_agent_document_demand_drivers() -> None:
    output = {
        "agentName": "Demand Drivers",
        "target_company": "Test3",
        "sources": ["04_Commercial_Due_Diligence.pdf"],
        "document": (
            "# Demand Drivers\n\n"
            "## 1. Drivers That Apply\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("demand_drivers", output)
    assert "## 1. Drivers" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_demand_drivers_from_corpus() -> None:
    spec = build_demand_drivers_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "04_Commercial_Due_Diligence.pdf",
                    "cdl_category": "deal_strategy",
                    "excerpt": _demand_corpus(),
                }
            ],
            "category_counts": {"deal_strategy": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_demand_drivers_markdown("Demand Drivers", spec)
    assert "## 1. Drivers" in md
    assert "## 3. Transmission" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
