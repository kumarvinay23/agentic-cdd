"""Market Definition — DiligenceIQ prompt-book competition perimeter."""

from __future__ import annotations

from agetic_cdd_api.agent_document_market_definition import (
    _heuristic_market_definition_spec,
    build_market_definition_spec,
    market_definition_approved,
    render_market_definition_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.deep_dive_roles import role_by_slug
from agetic_cdd_api.prompt_book import compose_system, listed_agents


class _FakeDeal:
    id = "deal-md-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _market_corpus() -> str:
    return (
        "11 Market & Competition Analysis. Company sells electric two-wheelers and "
        "connected software (MoveOS) to retail consumers and limited fleet buyers. "
        "Operating footprint is India — South India ~34% revenue share, West ~28%, "
        "North ~24%. Manufacturing and assembly in-house; battery cells partially "
        "localized. Does not sell ICE vehicles — strategic exclusion. Cannot currently "
        "serve export markets pending homologation — capability limit. "
        "TAM USD 24.5B India 2W market. SAM USD 1.5B EV 2W segment. SOM USD 0.6B. "
        "EV penetration ~6% in FY2024. FAME-II and state subsidies support demand. "
        "Futurefactory capacity 2 million units p.a. "
        "Software attach and vehicle sale are separate revenue streams."
    )


def test_market_definition_prompt_book_listed() -> None:
    system = compose_system("market_definition", sector="EV", geography="India")
    assert "market_definition" in listed_agents()
    assert "four axes" in system.lower() or "four dimensions" in system.lower() or "Perimeter" in system
    assert "context only" in system.lower() or "context, not the market" in system.lower()
    assert "operating footprint" in system.lower()


def test_market_definition_markdown_follows_prompt_book() -> None:
    heur = _heuristic_market_definition_spec(
        company="Test3",
        corpus=_market_corpus(),
        sources=["11_Market_Competition_Analysis.pdf", "03_Investment_Thesis.pdf"],
    )
    md = render_market_definition_markdown("Market Definition", heur)

    assert "## 1. Perimeter" in md
    assert "## 2. Revenue Streams" in md
    assert "## 3. Exclusions" in md
    assert "## 4. Addressable" in md
    assert "## 5. Published Figures" in md
    assert "## 6. Approval Gate" in md
    assert "## 7. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "industry label" in md.lower() or "operating footprint" in md.lower()
    assert "context" in md.lower()
    assert heur.get("approval_gate", {}).get("blocks_downstream_market_agents") is True
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert not market_definition_approved(heur)  # not yet explicitly approved


def test_downstream_market_agents_depend_on_definition() -> None:
    for slug in (
        "market_volume_and_growth",
        "market_pricing",
        "demand_drivers",
        "competitor_identification",
        "competitive_differentiation",
        "market_share_strategy",
    ):
        role = role_by_slug(slug)
        assert role is not None
        assert "market_definition" in role.depends_on


def test_render_agent_document_market_definition() -> None:
    output = {
        "agentName": "Market Definition",
        "target_company": "Test3",
        "sources": ["11_Market_Competition_Analysis.pdf"],
        "document": (
            "# Market Definition\n\n"
            "## 1. Perimeter — Four Axes\n\n"
            "Seeded.\n\n"
            "## 7. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("market_definition", output)
    assert "## 1. Perimeter" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_market_definition_from_corpus() -> None:
    spec = build_market_definition_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "11_Market_Competition_Analysis.pdf",
                    "cdl_category": "market_competition",
                    "excerpt": _market_corpus(),
                }
            ],
            "category_counts": {"market_competition": 1},
        },
        company="Test3",
    )
    md = render_market_definition_markdown("Market Definition", spec)
    assert "## 1. Perimeter" in md
    assert "## 6. Approval Gate" in md
    assert spec.get("composer") in {"heuristic_v1", "llm_v1"}
    # Composer must not bake a specific target company into the prompt path.
    from agetic_cdd_api.prompt_book import agent_prompt

    body = agent_prompt("market_definition")
    assert "Ola" not in body and "SoftBank" not in body
