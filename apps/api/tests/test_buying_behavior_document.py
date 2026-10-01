"""Buying Behavior — DiligenceIQ prompt-book purchase maps & sales assumptions."""

from __future__ import annotations

from agetic_cdd_api.agent_document_buying_behavior import (
    _heuristic_buying_behavior_spec,
    _label_anecdotal,
    build_buying_behavior_spec,
    render_buying_behavior_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-buy-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _buy_corpus() -> str:
    return (
        "Retail customers decide via the vehicle owner; Fleet segment decision-maker "
        "is the fleet manager with CFO budget holder and two-level approval. "
        "Procurement via tender for fleet; direct purchase for retail. "
        "Purchase trigger: vehicle replacement cycle. "
        "Retail sales cycle median 12 days range 5-21 days. "
        "Fleet sales cycle median 45 days range 30-90 days. "
        "Time to purchase 18 days overall. "
        "Won deal citing range and service; lost to peer on software features. "
        "Customers said price mattered; they chose on service resolution. "
        "Online sales mix 38%. EMI purchase 42%. CAC INR 12,400. "
        "Fleet segment (28% of revenue). "
        "Jan 1200 Feb 1100 Mar 1800 Apr 1400 May 1300 Jun 1250 — monthly signups "
        "after controlling for acquisitions. "
        "Interviewed 8 fleet buyers in Q1 FY2024 using structured interviews."
    )


def test_buying_behavior_prompt_book_listed() -> None:
    system = compose_system("buying_behavior", sector="EV", geography="India")
    assert "buying_behavior" in listed_agents()
    assert "sales cycle" in system.lower() or "purchase" in system.lower()
    body = agent_prompt("buying_behavior")
    assert "Ola" not in body and "SoftBank" not in body
    assert "seasonality" in body.lower()
    assert "anecdotal" in body.lower()


def test_buying_behavior_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_buying_behavior.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("buying_behavior")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_anecdotal_label_and_no_global_cycle() -> None:
    labelled, is_anec = _label_anecdotal(
        "Management said customers hate the price",
        corpus="interview told us",
    )
    assert is_anec is True
    assert "anecdotal" in labelled.lower()

    heur = _heuristic_buying_behavior_spec(
        company="Test3",
        corpus="Sales cycle median 30 days. Retail and Fleet both buy vehicles.",
        sources=["a.pdf"],
    )
    cycles = heur.get("sales_cycles") or []
    assert len(cycles) >= 2
    # One pack figure must not be assigned to every segment
    assert not all(c.get("crm_evidenced") for c in cycles if isinstance(c, dict))


def test_buying_behavior_markdown_follows_prompt_book() -> None:
    heur = _heuristic_buying_behavior_spec(
        company="Test3",
        corpus=_buy_corpus(),
        sources=["04_Commercial_Due_Diligence.pdf"],
        legacy_spec={
            "buying_metrics": {"online_sales_pct": 38.0},
            "concentration_flags": ["Legacy concentration note"],
            "behavior_notes": ["Legacy behavior note"],
        },
    )
    md = render_buying_behavior_markdown("Buying Behavior", heur)

    assert "## 1. Purchase" in md
    assert "## 2. Sales Cycle" in md
    assert "## 3. Purchase Criteria" in md or "## 3." in md
    assert "## 4. Seasonality" in md
    assert "## 5. Implications" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    maps = heur.get("purchase_maps") or []
    assert isinstance(maps, list) and len(maps) >= 2
    cycles = heur.get("sales_cycles") or []
    assert any(isinstance(c, dict) and c.get("crm_evidenced") for c in cycles)
    assert (heur.get("seasonality") or {}).get("measured") is True
    assert (heur.get("switching") or {}).get("evidenced") is True
    metrics = heur.get("buying_metrics") or {}
    assert metrics.get("online_sales_pct") == 38.0 or metrics.get("online_sales_pct") == 38
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert isinstance(heur.get("behavior_notes"), list)
    assert "not asserted" in md.lower() or "association" in md.lower() or "seasonality" in md.lower()


def test_seasonality_not_asserted_without_data() -> None:
    heur = _heuristic_buying_behavior_spec(
        company="Test3",
        corpus="Demand is highly seasonal around festivals. No monthly series provided.",
        sources=["a.pdf"],
    )
    season = heur.get("seasonality") or {}
    assert season.get("measured") is False
    assert season.get("asserted_without_data") is False
    md = render_buying_behavior_markdown("Buying Behavior", heur)
    assert "not asserted" in md.lower() or "do not assert" in md.lower() or "not in the data" in md.lower()


def test_normalise_strips_recommendation() -> None:
    from agetic_cdd_api.agent_document_buying_behavior import _normalise_llm_spec
    import inspect

    sig = inspect.signature(_normalise_llm_spec)
    kwargs: dict = {"sources": ["a.pdf"], "legacy_spec": None}
    if "corpus" in sig.parameters:
        kwargs["corpus"] = "Retail sales cycle median 12 days. Fleet sales cycle median 45 days."

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Buyers love us — invest",
            "purchase_maps": [{"segment": "Retail / B2C", "decision_maker": "Owner"}],
            "sales_cycles": [
                {
                    "segment": "Retail / B2C",
                    "median": "12 days",
                    "crm_evidenced": True,
                },
                {
                    "segment": "Fleet / B2B",
                    "median": "12 days",
                    "crm_evidenced": True,
                },
            ],
            "switching": {"evidenced": True, "customers_say": ["said price"]},
            "seasonality": {"measured": True, "pattern": "festive spike"},
            "implications": {},
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        **kwargs,
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()
    # Identical median forced onto both segments → heuristic guard may replace
    cycles = llm.get("sales_cycles") or []
    assert isinstance(cycles, list)
    season = llm.get("seasonality") or {}
    # Without monthly data in corpus, measured must not stay True from LLM alone
    assert season.get("asserted_without_data") is False


def test_render_agent_document_buying_behavior() -> None:
    output = {
        "agentName": "Buying Behavior",
        "target_company": "Test3",
        "sources": ["04_Commercial_Due_Diligence.pdf"],
        "document": (
            "# Buying Behavior\n\n"
            "## 1. Purchase Maps (by Segment)\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("buying_behavior", output)
    assert "## 1. Purchase" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_buying_behavior_from_corpus() -> None:
    spec = build_buying_behavior_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "04_Commercial_Due_Diligence.pdf",
                    "cdl_category": "customer",
                    "excerpt": _buy_corpus(),
                }
            ],
            "category_counts": {"customer": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_buying_behavior_markdown("Buying Behavior", spec)
    assert "## 2. Sales Cycle" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-09"
