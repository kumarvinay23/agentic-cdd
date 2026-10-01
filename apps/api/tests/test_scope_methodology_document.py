"""Scope & Methodology — DiligenceIQ coverage-record prompt book."""

from __future__ import annotations

from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.agent_document_scope_methodology import (
    _heuristic_scope_methodology_spec,
    build_scope_methodology_spec,
    render_scope_methodology_markdown,
)
from agetic_cdd_api.prompt_book import compose_system, listed_agents
from agetic_cdd_api.services_library import phase1_agent_output


class _FakeDeal:
    id = "deal-scope-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _ola_index() -> dict:
    excerpt = (
        "11 Market & Competition Analysis. Indian electric two-wheeler (E2W) market. "
        "Ola Electric Mobility Limited manufacturing and sales of electric two-wheelers in India. "
        "Revenue (INR Cr) FY2024E 4,900. EBITDA still negative. "
        "FAME-II subsidy claims noted. Competitive landscape with TVS iQube and Ather Energy. "
        "Historical FY2021-FY2025 performance with forward projections. "
        "Management interview on 15 Mar 2024 with Bhavish Aggarwal CEO present."
    )
    return {
        "document_count": 3,
        "category_counts": {
            "deal_strategy": 1,
            "company_management": 1,
            "market_competition": 1,
            "customer": 0,
            "operations": 0,
            "legal_esg": 0,
            "financial": 1,
        },
        "documents": [
            {
                "filename": "01_Executive_Summary.pdf",
                "cdl_category": "deal_strategy",
                "excerpt": excerpt,
            },
            {
                "filename": "05_Financial_Due_Diligence.pdf",
                "cdl_category": "financial",
                "excerpt": "Profit & Loss. Revenue FY2024E 4,900 cr. FY2021-FY2025.",
            },
            {
                "filename": "11_Market_Competition_Analysis.pdf",
                "cdl_category": "market_competition",
                "excerpt": excerpt,
            },
        ],
    }


def test_scope_prompt_book_listed() -> None:
    system = compose_system(
        "scope_and_methodology",
        sector="Electric Two-Wheelers",
        geography="India",
    )
    assert "scope_and_methodology" in listed_agents()
    assert "coverage record" in system.lower() or "Coverage" in system
    assert "Do not conclude on the attractiveness" in system or "attractiveness" in system
    assert system.count("WHERE TO LOOK, IN THIS ORDER") == 1


def test_scope_methodology_markdown_follows_prompt_book() -> None:
    corpus = " ".join(d["excerpt"] for d in _ola_index()["documents"])
    heur = _heuristic_scope_methodology_spec(
        company="Test3",
        corpus=corpus,
        sources=[d["filename"] for d in _ola_index()["documents"]],
        index=_ola_index(),
        covered=["Deal / Strategy", "Market / Competition", "Financial", "Company / Management"],
        gaps=["Customer", "Operations", "Legal / ESG"],
    )
    md = render_scope_methodology_markdown("Scope & Methodology", heur)

    assert "## 1. Coverage Record" in md
    assert "### Coverage Table" in md
    assert "## 2. Exclusions & Ownership" in md
    assert "## 3. Fieldwork Log" in md
    assert "## 4. Unfinished Work" in md
    assert "## 5. Coverage Conclusion" in md
    assert "## 6. Quality & Reliance" in md
    assert "questions evidenced" in md.lower() or "Questions evidenced" in md or "evidenced" in md
    assert "documents read" in md.lower() or "Documents read" in md
    assert "**Recommendation:**" not in md
    assert "**Confidence:**" not in md
    assert "does not recommend invest or pass" in md.lower()
    assert "Porter's 5 Forces" not in md
    assert "Final Recommendation" not in md

    counts = heur["coverage_counts"]
    assert counts["questions_in_scope"] >= 7
    assert counts["documents_available"] == 3
    assert isinstance(counts["questions_evidenced"], int)
    assert any(e.get("state") == "out_of_scope" for e in heur["exclusions"])
    assert any(e.get("state") == "cannot_with_evidence" for e in heur["exclusions"])
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    # Dated interview from corpus should appear
    assert any(
        "2024" in str(f.get("date") or "") or "Mar" in str(f.get("date") or "")
        for f in heur["fieldwork"]
    )
    assert any(u.get("gate") == "must_close" for u in heur["unfinished"])
    assert "comprehensive" not in (heur.get("coverage_conclusion") or "").lower() or "not" in (
        heur.get("coverage_conclusion") or ""
    ).lower()


def test_phase1_scope_embeds_coverage_document() -> None:
    output = phase1_agent_output(
        _FakeDeal(),
        agent_key="scope_and_methodology",
        index=_ola_index(),
    )
    assert output["stub"] is False
    assert "spec" in output
    assert "document" in output
    assert "## 1. Coverage Record" in output["document"]
    assert "**Recommendation:**" not in output["document"]
    rendered = render_agent_document("scope_and_methodology", output)
    assert rendered.startswith("# Scope")
    assert "Coverage Table" in rendered or "Coverage Record" in rendered
    assert "## 6. Quality & Reliance" in rendered


def test_build_scope_spec_renderable() -> None:
    spec = build_scope_methodology_spec(
        _FakeDeal(),
        index=_ola_index(),
        company="Test3",
        covered=["Deal / Strategy", "Market / Competition", "Financial"],
        gaps=["Customer", "Operations"],
    )
    md = render_scope_methodology_markdown("Scope & Methodology", spec)
    assert "## 1. Coverage Record" in md
    assert "Preliminary Investment" not in md
