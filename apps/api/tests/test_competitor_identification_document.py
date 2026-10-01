"""Competitor Identification — DiligenceIQ prompt-book named competitive set."""

from __future__ import annotations

from agetic_cdd_api.agent_document_competitor_identification import (
    _heuristic_competitor_identification_spec,
    _is_placeholder_name,
    _is_target_name,
    build_competitor_identification_spec,
    render_competitor_identification_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-ci-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _comp_corpus() -> str:
    return (
        "Competitive landscape: Ather Energy competes directly in India metro E2W "
        "with ~20% share; TVS Motor iQube overlapping scooter service; "
        "Bajaj Auto Chetak is a direct rival. "
        "Lost bid notes show customers shortlisted Ather Energy and TVS in CRM. "
        "Substitute: customers doing nothing or in-housing fleet maintenance. "
        "Potential entrant: a national Chinese OEM without India dealer density is context only. "
        "Barriers: dealer network density, manufacturing capacity, FAME permit lead times, "
        "contracted volumes with fleets, and capital required for a plant. "
        "Competitor A and Peer 1 are placeholders and must be ignored."
    )


def test_competitor_identification_prompt_book_listed() -> None:
    system = compose_system("competitor_identification", sector="EV", geography="India")
    assert "competitor_identification" in listed_agents()
    assert "placeholder" in system.lower()
    body = agent_prompt("competitor_identification")
    assert "Ola" not in body and "SoftBank" not in body
    assert "doing nothing" in body.lower() or "in-housing" in body.lower()


def test_competitor_identification_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_competitor_identification.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bajaj Auto"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("competitor_identification")
    for banned in ("Ola", "SoftBank", "Ather", "TVS", "Bajaj"):
        assert banned not in prompt


def test_placeholder_and_target_rules() -> None:
    assert _is_placeholder_name("Competitor A")
    assert _is_placeholder_name("Peer 1")
    assert not _is_placeholder_name("Ather Energy")
    assert _is_target_name("Test3", "Test3")
    assert _is_target_name("Test3 Electric", "Test3")


def test_competitor_identification_markdown_follows_prompt_book() -> None:
    heur = _heuristic_competitor_identification_spec(
        company="Test3",
        corpus=_comp_corpus(),
        sources=["11_Market_Competition_Analysis.pdf"],
        geography="India",
        legacy_spec={
            "competitors": [
                {"name": "Ather Energy", "market_share_pct": 20.0, "trend": "Gaining"},
                {"name": "Test3", "market_share_pct": 32.0},  # must not stay in set
            ],
        },
    )
    md = render_competitor_identification_markdown("Competitor Identification", heur)

    assert "## 1. Target Reference" in md
    assert "## 2. Named Competitive Set" in md
    assert "## 3. Classification" in md
    assert "## 4. Customer Choice" in md
    assert "## 5. Barriers" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    names = [
        str(r.get("name") or "")
        for r in (heur.get("competitive_set") or [])
        if isinstance(r, dict)
    ]
    assert not any(_is_target_name(n, "Test3") for n in names)
    assert not any(_is_placeholder_name(n) for n in names if n)
    assert any("doing nothing" in n.lower() or "in-hous" in n.lower() for n in names)
    assert any("Ather" in n for n in names)
    # Report-shaped list must not include target
    legacy_names = [
        str(r.get("name") or "")
        for r in (heur.get("competitors") or [])
        if isinstance(r, dict)
    ]
    assert not any(_is_target_name(n, "Test3") for n in legacy_names)
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_placeholder_dropped_in_normalise() -> None:
    from agetic_cdd_api.agent_document_competitor_identification import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "competitors": [
                {"name": "Competitor A", "classification": "direct_competitor"},
                {"name": "Test3", "classification": "direct_competitor"},
                {
                    "name": "Northwind Systems",
                    "geography": "India",
                    "classification": "direct_competitor",
                    "service_overlap": "same service",
                },
            ],
            "customer_choice": [],
            "barriers": [],
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        company="Test3",
        sources=["a.pdf"],
        geography="India",
        legacy_spec=None,
    )
    rich = [str(r.get("name")) for r in llm["competitive_set"]]
    assert "Competitor A" not in rich
    assert not any(_is_target_name(n, "Test3") for n in rich)
    assert any("Northwind" in n for n in rich)
    assert any("doing nothing" in n.lower() or "in-hous" in n.lower() for n in rich)
    # competitors key is report-shaped
    for row in llm["competitors"]:
        assert "market_share_pct" in row or "name" in row


def test_render_agent_document_competitor_identification() -> None:
    output = {
        "agentName": "Competitor Identification",
        "target_company": "Test3",
        "sources": ["11_Market_Competition_Analysis.pdf"],
        "document": (
            "# Competitor Identification\n\n"
            "## 1. Target Reference (Not a Competitor)\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("competitor_identification", output)
    assert "## 1. Target Reference" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_competitor_identification_from_corpus() -> None:
    spec = build_competitor_identification_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "11_Market_Competition_Analysis.pdf",
                    "cdl_category": "market_competition",
                    "excerpt": _comp_corpus(),
                }
            ],
            "category_counts": {"market_competition": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_competitor_identification_markdown("Competitor Identification", spec)
    assert "## 2. Named Competitive Set" in md
    assert "## 5. Barriers" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
