"""Market Share Strategy — DiligenceIQ prompt-book share plan tests."""

from __future__ import annotations

from agetic_cdd_api.agent_document_market_share_strategy import (
    _heuristic_market_share_strategy_spec,
    _share_calculable,
    build_market_share_strategy_spec,
    render_market_share_strategy_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-mss-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _mss_corpus() -> str:
    return (
        "Accounts revenue for India E2W scooters FY24 is INR 1,200 crore from the "
        "management accounts. Approved market perimeter SAM India E2W scooters is "
        "INR 8,000 crore FY24. "
        "Focal share moved from 12% in FY22 to 15% in FY24 (+3 pp); organic; "
        "no acquisitions in the period. Market grew about 18% — separate from share gain. "
        "Growth plan requires 8,000 customers per month, volume 120,000 units, "
        "capacity 150,000 vehicles, sales headcount 240. "
        "CRM D2C channel: 12,000 leads per month, conversion rate 6%, sales cycle 21 days, "
        "CAC INR 4,200, retention 72%. "
        "Management ambition is 25% share by FY27; bottom-up attainable from current "
        "funnel rates is lower — gap must be closed by conversion or capacity."
    )


def test_market_share_strategy_prompt_book_listed() -> None:
    system = compose_system("market_share_strategy", sector="EV", geography="India")
    assert "market_share_strategy" in listed_agents()
    assert "share" in system.lower()
    body = agent_prompt("market_share_strategy")
    assert "Ola" not in body and "SoftBank" not in body
    assert "numerator" in body.lower() and "denominator" in body.lower()
    assert "unassessed" in body.lower() or "not calculable" in body.lower()


def test_market_share_strategy_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_market_share_strategy.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("market_share_strategy")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_share_calculable_unit_mismatch() -> None:
    ok, notes = _share_calculable(
        "accounts revenue INR",
        "TAM India E2W units",
        unit_numerator="INR",
        unit_denominator="units",
        service="E2W",
        geography="India",
        date_or_period="FY24",
    )
    assert ok is False
    assert "unassessed" in notes.lower() or "mismatch" in notes.lower()


def test_market_share_strategy_markdown_follows_prompt_book() -> None:
    heur = _heuristic_market_share_strategy_spec(
        company="Test3",
        corpus=_mss_corpus(),
        sources=["11_Market_Competition_Analysis.pdf"],
        legacy_spec={
            "share_trends": [
                {
                    "name": "Focal",
                    "market_share_pct": 15.0,
                    "trend": "Strong Gain",
                    "units_000s": None,
                    "flagship_price_inr": None,
                    "nps": None,
                    "software": None,
                }
            ],
            "wins": ["Share opportunity vs declining peer"],
            "losses": ["Share pressure from gaining peer"],
            "strategy_notes": ["Scale ambition"],
        },
    )
    md = render_market_share_strategy_markdown("Market Share Strategy", heur)

    assert "## 1. Matched Share" in md
    assert "## 2. Share Movement" in md
    assert "## 3." in md  # Physical Requirements
    assert "## 4." in md  # Funnel
    assert "## 5." in md  # Attainable
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "unassessed" in md.lower() or "not calculable" in md.lower() or heur.get(
        "matched_share", {}
    ).get("calculable") is True
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert isinstance(heur.get("share_trends"), list)
    assert isinstance(heur.get("wins"), list)
    assert isinstance(heur.get("losses"), list)
    assert isinstance(heur.get("strategy_notes"), list)


def test_normalise_strips_recommendation() -> None:
    from agetic_cdd_api.agent_document_market_share_strategy import _normalise_llm_spec
    import inspect

    sig = inspect.signature(_normalise_llm_spec)
    kwargs: dict = {
        "sources": ["a.pdf"],
        "legacy_spec": None,
    }
    if "corpus" in sig.parameters:
        kwargs["corpus"] = ""

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Target is the clear market leader",
            "matched_share": {
                "calculable": False,
                "numerator": "N/A (data room did not provide it)",
                "denominator": "N/A (data room did not provide it)",
                "share_pct": None,
                "match_notes": "unmatched",
                "information_request": "Information request: matched inputs",
            },
            "share_movement": [],
            "plan_requirements": {},
            "funnel_economics": [],
            "attainable_vs_ambition": {},
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "BLOCKED",
        },
        **kwargs,
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    snap = str(llm.get("insight_snapshot") or "").lower()
    assert "invest" not in snap
    # Leadership softened when share not calculable
    assert "leader" not in snap or "unassessed" in snap


def test_render_agent_document_market_share_strategy() -> None:
    output = {
        "agentName": "Market Share Strategy",
        "target_company": "Test3",
        "sources": ["11_Market_Competition_Analysis.pdf"],
        "document": (
            "# Market Share Strategy\n\n"
            "## 1. Matched Share (Numerator / Denominator)\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("market_share_strategy", output)
    assert "## 1. Matched Share" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_market_share_strategy_from_corpus() -> None:
    spec = build_market_share_strategy_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "11_Market_Competition_Analysis.pdf",
                    "cdl_category": "market_competition",
                    "excerpt": _mss_corpus(),
                }
            ],
            "category_counts": {"market_competition": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_market_share_strategy_markdown("Market Share Strategy", spec)
    assert "## 2. Share Movement" in md
    assert "## 5." in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-05"
