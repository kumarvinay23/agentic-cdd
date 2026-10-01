"""Market Volume & Growth — DiligenceIQ prompt-book sizing."""

from __future__ import annotations

from agetic_cdd_api.agent_document_market_volume import (
    _heuristic_market_volume_spec,
    build_market_volume_spec,
    render_market_volume_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-mv-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _volume_corpus() -> str:
    return (
        "Indian EV two-wheeler market recorded sales of approximately 950,000 units in FY2024. "
        "Market share ~32%. ASP average selling price INR 95,000. "
        "SAM USD 1.5B EV 2W Segment. TAM USD 24.5B India 2W Market. "
        "The segment is growing at ~55% CAGR over FY2022–FY2024. "
        "SAM FY2024 USD 1.5B FY2028E USD 14.4B ~57.6% CAGR. "
        "FY 2021 FY 2022 FY 2023 FY 2024E FY 2025E "
        "Revenue 456 1200 2630 4900 8200. "
        "Plan path implies ~45% CAGR. Mix shift to software; price and volume drivers. "
        "No acquisition in base case."
    )


def test_market_volume_prompt_book_listed() -> None:
    system = compose_system("market_volume_and_growth", sector="EV", geography="India")
    assert "market_volume_and_growth" in listed_agents()
    assert "bottom-up" in system.lower()
    assert "one-year" in system.lower() or "multi-year" in system.lower()
    assert "Not available" in system
    body = agent_prompt("market_volume_and_growth")
    assert "Ola" not in body and "SoftBank" not in body


def test_market_volume_markdown_follows_prompt_book() -> None:
    heur = _heuristic_market_volume_spec(
        company="Test3",
        corpus=_volume_corpus(),
        sources=["11_Market_Competition_Analysis.pdf", "05_Financial_Due_Diligence.pdf"],
        perimeter={"service": "E2W", "geography": "India"},
        legacy_spec={
            "tam": {"label": "TAM", "value": 24.5, "unit": "USD", "scale": "billion"},
            "sam": {"label": "SAM", "value": 1.5, "unit": "USD", "scale": "billion"},
            "cagr_pct": [55.0, 57.6],
        },
    )
    md = render_market_volume_markdown("Market Volume & Growth", heur)

    assert "## 1. Bottom-Up" in md
    assert "## 2. Top-Down" in md
    assert "## 3. Market Series" in md
    assert "## 4. Company Growth" in md
    assert "## 5. Plan vs Market" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "×" in md or "arithmetic" in md.lower()
    assert "Not available" not in str(heur.get("company_growth", {}).get("historical_growth", ""))
    assert "COMPUTED" in str(heur.get("company_growth", {}).get("historical_growth", ""))
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_accounts_force_company_growth() -> None:
    """Accounts in room → must compute; Not available forbidden."""
    heur = _heuristic_market_volume_spec(
        company="Test3",
        corpus=_volume_corpus(),
        sources=["05_Financial.pdf"],
    )
    hist = str(heur["company_growth"]["historical_growth"])
    assert not hist.lower().startswith("not available")
    assert "Information request" not in hist
    assert "COMPUTED" in hist or "%" in hist


def test_render_agent_document_market_volume() -> None:
    output = {
        "agentName": "Market Volume & Growth",
        "target_company": "Test3",
        "sources": ["11_Market_Competition_Analysis.pdf"],
        "document": (
            "# Market Volume & Growth\n\n"
            "## 1. Bottom-Up Market Size\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("market_volume_and_growth", output)
    assert "## 1. Bottom-Up" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_market_volume_from_corpus() -> None:
    spec = build_market_volume_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "11_Market_Competition_Analysis.pdf",
                    "cdl_category": "market_competition",
                    "excerpt": _volume_corpus(),
                }
            ],
            "category_counts": {"market_competition": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_market_volume_markdown("Market Volume & Growth", spec)
    assert "## 1. Bottom-Up" in md
    assert "## 5. Plan vs Market" in md
    assert "## 6. Quality & Reliance" in md
    assert "## Sources" in md
    assert "<!-- cdd:sources" in md
    assert spec.get("composer") == "heuristic_v1"


def test_parse_num_locale_variants() -> None:
    from agetic_cdd_api.agent_document_market_volume import _parse_num

    assert _parse_num("1,234.56") == 1234.56
    assert _parse_num("1.234,56") == 1234.56
    assert _parse_num("950000") == 950000.0
    assert _parse_num("32,5") == 32.5


def test_non_positive_base_reports_endpoints_not_cagr() -> None:
    from agetic_cdd_api.agent_document_market_volume import _company_growth

    corpus = (
        "FY 2021 FY 2022 FY 2023 FY 2024E FY 2025E "
        "Revenue -100 50 200 400 800. "
        "market share 10% ASP 1000. 100000 units."
    )
    company, _ = _company_growth(corpus)
    hist = str(company.get("historical_growth") or "")
    assert "Not available" not in hist
    assert "COMPUTED" in hist
    assert "non-positive" in hist.lower() or "undefined" in hist.lower() or "%" in hist


def test_zero_year_cagr_span_not_multi_year() -> None:
    from agetic_cdd_api.agent_document_market_volume import _market_series

    note = _market_series("growing at 12% CAGR FY2024–FY2024", None)[1]
    assert "multi-year CAGR" not in note or "not a multi-year" in note.lower()
    assert "FY2024" in note
