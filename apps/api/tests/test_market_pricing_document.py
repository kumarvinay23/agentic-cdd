"""Market Pricing — DiligenceIQ prompt-book realised pricing & power."""

from __future__ import annotations

from agetic_cdd_api.agent_document_market_pricing import (
    _heuristic_market_pricing_spec,
    build_market_pricing_spec,
    render_market_pricing_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-mp-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _pricing_corpus() -> str:
    return (
        "Avg Selling Price (INR) ASP ~98,200. Flagship list price INR 1,47,499. "
        "Discount of ~8% off list on volume deals. "
        "Ather Energy priced at INR 1,25,000 for equivalent scooter. "
        "TVS Motor iQube ASP around INR 1,10,000 published FY2024. "
        "Bajaj Auto Chetak list INR 1,20,000. "
        "After a 2023 price increase of 5%, churn rose and 1,200 customers downgraded; "
        "volume in the following quarter softened. "
        "Industry ASP ~80,000 is context only — not a named comparator. "
        "Some fleet contracts carry CPI escalators covering ~15% of revenue. "
        "Price volume mix bridge: price up, volume down, mix to higher ASP software attach."
    )


def test_market_pricing_prompt_book_listed() -> None:
    system = compose_system("market_pricing", sector="EV", geography="India")
    assert "market_pricing" in listed_agents()
    assert "realised" in system.lower()
    assert "unnamed" in system.lower()
    assert "percentage-point" in system.lower() or "percentage point" in system.lower()
    body = agent_prompt("market_pricing")
    assert "Ola" not in body and "SoftBank" not in body


def test_market_pricing_composer_not_company_hardcoded() -> None:
    """Composer / prompt must not embed a deal-specific OEM allowlist."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src/agetic_cdd_api/agent_document_market_pricing.py"
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bajaj Auto"):
        assert banned not in text, f"hardcoded comparator pattern: {banned}"
    prompt = agent_prompt("market_pricing")
    for banned in ("Ola", "SoftBank", "Ather", "TVS", "Bajaj", "Hero"):
        assert banned not in prompt


def test_market_pricing_markdown_follows_prompt_book() -> None:
    heur = _heuristic_market_pricing_spec(
        company="Test3",
        corpus=_pricing_corpus(),
        sources=["04_Commercial_Due_Diligence.pdf", "11_Market_Competition_Analysis.pdf"],
        legacy_spec={
            "price_points": [
                {"label": "asp", "value": 98200.0, "unit": "INR", "raw": "ASP ~98200"},
                {"label": "flagship", "value": 147499.0, "unit": "INR"},
            ],
            "power_signals": ["ASP premium vs industry"],
        },
    )
    md = render_market_pricing_markdown("Market Pricing", heur)

    assert "## 1. Realised Net Price" in md
    assert "## 2. Named Competitor" in md
    assert "## 3. Price–Volume–Mix" in md or "## 3. Price" in md
    assert "## 4. Observed Response" in md
    assert "## 5. Contract Escalators" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "percentage-point" in md.lower() or "percentage point" in md.lower()
    comps = heur.get("competitor_comparisons") or []
    assert any(
        isinstance(c, dict)
        and c.get("competitor")
        and not str(c["competitor"]).startswith("Information")
        for c in comps
    )
    assert "elasticity" not in str((heur.get("observed_response") or [{}])[0].get("label", "")).lower() or "not elasticity" in str(
        (heur.get("observed_response") or [{}])[0].get("label", "")
    ).lower()
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_unnamed_competitor_rejected_in_normalise() -> None:
    from agetic_cdd_api.agent_document_market_pricing import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "competitor_comparisons": [
                {"competitor": "industry", "their_price": "80k"},
                {"competitor": "Ather", "their_price": "125000", "equivalent_service": "scooter"},
            ],
            "observed_response": [
                {"label": "elasticity of demand after hike", "event": "2023 hike"}
            ],
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        sources=["a.pdf"],
        legacy_spec=None,
    )
    names = [c.get("competitor") for c in llm["competitor_comparisons"]]
    assert "industry" not in [str(n).lower() for n in names]
    assert any("Ather" in str(n) for n in names)
    assert "not elasticity" in str(llm["observed_response"][0].get("label", "")).lower()


def test_render_agent_document_market_pricing() -> None:
    output = {
        "agentName": "Market Pricing",
        "target_company": "Test3",
        "sources": ["04_Commercial_Due_Diligence.pdf"],
        "document": (
            "# Market Pricing\n\n"
            "## 1. Realised Net Price\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("market_pricing", output)
    assert "## 1. Realised" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_market_pricing_from_corpus() -> None:
    spec = build_market_pricing_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "04_Commercial_Due_Diligence.pdf",
                    "cdl_category": "customer",
                    "excerpt": _pricing_corpus(),
                }
            ],
            "category_counts": {"customer": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_market_pricing_markdown("Market Pricing", spec)
    assert "## 1. Realised" in md
    assert "## 5. Contract Escalators" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"


def test_asp_skips_intermediate_year() -> None:
    """'ASP increased in 2023 to $150' must capture 150, not the year 2023."""
    from agetic_cdd_api.agent_document_market_pricing import _labelled_money, _ASP_LABEL, _first_money

    money = _labelled_money("ASP increased in 2023 to $150 per unit.", _ASP_LABEL)
    assert money is not None
    assert money[1] == 150.0
    assert not str(money[0]).startswith("2023")

    # Bare year alone is not a price
    assert _first_money("in 2023 alone") is None
    # Currency after year still wins
    hit = _first_money("raised in 2024 to INR 98,200")
    assert hit is not None and hit[1] == 98200.0


def test_competitor_price_after_name_not_precontext() -> None:
    """Price search starts after the competitor name, not via window[len(name):]."""
    from agetic_cdd_api.agent_document_market_pricing import _competitor_comps

    # Pre-context has a decoy amount; the real price follows the name.
    corpus = (
        "Market note: INR 99 decoy ahead of peers. "
        "Northwind Systems priced at INR 1,25,000 for equivalent service in FY2024."
    )
    comps = _competitor_comps(corpus, None)
    named = [
        c for c in comps
        if isinstance(c, dict)
        and "Northwind" in str(c.get("competitor", ""))
        and not str(c.get("competitor", "")).startswith("Information")
    ]
    assert named, comps
    price = str(named[0].get("their_price") or "")
    assert "125000" in price.replace(",", "") or "1,25,000" in price or "125" in price
    assert "99" not in price.split()[0]  # decoy must not win


def test_pct_vs_pp_labelling() -> None:
    """List/realised gap is %; churn rate moves are percentage points."""
    from agetic_cdd_api.agent_document_market_pricing import (
        _realised_prices,
        _observed_response,
    )

    realised = _realised_prices(
        "ASP INR 100. Flagship list price INR 125. Discount of ~20% off list.",
        None,
    )
    gap = next(
        (r for r in realised if "gap" in str(r.get("service_or_segment", "")).lower()),
        None,
    )
    assert gap is not None
    assert "percentage points" in gap["notes"].lower() or "not percentage" in gap["notes"].lower()
    assert "percentage change" in gap["notes"].lower() or "relative" in gap["notes"].lower()

    disc_row = next(
        (r for r in realised if "discount" in str(r.get("notes", "")).lower()),
        None,
    )
    if disc_row:
        assert "not percentage points" in disc_row["notes"].lower()

    obs = _observed_response(
        "After the hike, churn rose from 3% to 5%; 400 customers affected."
    )
    note = str(obs[0].get("churn_or_downgrade") or "")
    assert "percentage point" in note.lower()
    assert "3" in note and "5" in note

