"""Market Volume & Growth — DiligenceIQ prompt-book sizing."""

from __future__ import annotations

from agetic_cdd_api.agent_document_market_volume import (
    _heuristic_market_volume_spec,
    build_market_volume_spec,
    render_market_volume_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents, questions_complete


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
        "No acquisition in base case. Base scenario adoption sensitivity noted."
    )


def test_market_volume_prompt_book_listed() -> None:
    system = compose_system("market_volume_and_growth", sector="EV", geography="India")
    assert "market_volume_and_growth" in listed_agents()
    assert "bottom-up" in system.lower()
    assert "one-year" in system.lower() or "multi-year" in system.lower()
    assert "Not available" in system
    assert "questions" in system.lower()
    assert "volume" in system.lower() and "value" in system.lower()
    assert "[DEAL_PERIMETER]" in system or "Deal perimeter" in system
    body = agent_prompt("market_volume_and_growth")
    assert "Ola" not in body and "SoftBank" not in body


def test_market_volume_markdown_follows_prompt_book() -> None:
    heur = _heuristic_market_volume_spec(
        company="Test3",
        corpus=_volume_corpus(),
        sources=["11_Market_Competition_Analysis.pdf", "05_Financial_Due_Diligence.pdf"],
        perimeter={
            "service": "E2W",
            "customer_types": "retail + fleet",
            "geography": "India",
            "value_chain_stage": "OEM + software",
            "as_of_date": "2024-12-31",
        },
        legacy_spec={
            "tam": {"label": "TAM", "value": 24.5, "unit": "USD", "scale": "billion"},
            "sam": {"label": "SAM", "value": 1.5, "unit": "USD", "scale": "billion"},
            "cagr_pct": [55.0, 57.6],
        },
    )
    md = render_market_volume_markdown("Market Volume & Growth", heur)

    assert "## 1. Perimeter Binding" in md
    assert "## 2. Bottom-Up" in md
    assert "## 3. Top-Down" in md
    assert "## 4. Market Series" in md
    assert "## 5. Company Growth" in md
    assert "## 6. Plan vs Market" in md
    assert "## 7. Questions" in md
    assert "## 8. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "×" in md or "arithmetic" in md.lower()
    assert "Not available" not in str(heur.get("company_growth", {}).get("historical_growth", ""))
    assert "COMPUTED" in str(heur.get("company_growth", {}).get("historical_growth", ""))
    assert heur.get("perimeter_binding", {}).get("bound") is True
    assert heur.get("volume_vs_value")
    assert heur.get("endpoint_cagr")
    assert heur.get("scenarios")
    assert heur.get("questions")
    assert questions_complete(heur["questions"])
    drivers = {r.get("driver") for r in (heur.get("growth_decomposition") or []) if isinstance(r, dict)}
    assert "organic" in drivers or "m_and_a" in drivers or "share_gain" in drivers
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
            "## 1. Perimeter Binding\n\n"
            "Seeded.\n\n"
            "## 8. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("market_volume_and_growth", output)
    assert "## 1. Perimeter" in rendered
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
        perimeter={
            "service": "E2W",
            "geography": "India",
            "customer_types": "retail",
            "value_chain_stage": "OEM",
        },
        prefer_heuristic=True,
    )
    md = render_market_volume_markdown("Market Volume & Growth", spec)
    assert "## 1. Perimeter Binding" in md
    assert "## 6. Plan vs Market" in md
    assert "## 7. Questions" in md
    assert "## 8. Quality & Reliance" in md
    assert "## Sources" in md
    assert "<!-- cdd:sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("questions")
    assert questions_complete(spec["questions"])


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


def test_unbound_perimeter_emits_question() -> None:
    heur = _heuristic_market_volume_spec(
        company="ThinCo",
        corpus="No units or ASP here.",
        sources=["empty.pdf"],
        perimeter=None,
    )
    assert heur.get("questions")
    assert questions_complete(heur["questions"])
    assert heur.get("perimeter_binding", {}).get("bound") is False
    assert any(
        "perimeter" in q.get("question", "").lower() for q in heur["questions"]
    )
