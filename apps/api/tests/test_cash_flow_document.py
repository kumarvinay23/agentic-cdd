"""Cash Flow — DiligenceIQ prompt-book EBITDA→cash bridge + liquidity."""

from __future__ import annotations

from agetic_cdd_api.agent_document_cash_flow import (
    _heuristic_cash_flow_spec,
    build_cash_flow_spec,
    render_cash_flow_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import (
    agent_prompt,
    compose_system,
    listed_agents,
    questions_complete,
)


class _FakeDeal:
    id = "deal-cf-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"
    materiality = None
    cdd_metadata: dict = {}


def _cf_corpus() -> str:
    return (
        "05 Financial Due Diligence Cash Flow Statement. "
        "Opening cash INR 120 Cr. Operating cash flow INR 45 Cr. "
        "Closing cash INR 95 Cr. EBITDA INR 80 Cr for FY2024. "
        "Capex INR 30 Cr. Maintenance capex INR 12 Cr. Growth capex INR 18 Cr. "
        "Change in working capital outflow INR 8 Cr. "
        "Free cash flow INR 15 Cr. "
        "Monthly cash burn INR 5 Cr. Liquidity runway 18–24 months. "
        "DSO 42 days. DPO 35 days. Inventory days 28 days. "
        "One-off restructuring cash cost noted. Debt repayment financing outflow."
    )


def test_cash_flow_prompt_book_listed() -> None:
    system = compose_system("cash_flow", sector="EV", geography="India")
    assert "cash_flow" in listed_agents()
    assert "EBITDA" in system or "cash" in system.lower()
    body = agent_prompt("cash_flow")
    assert "distress" in body.lower() or "missing" in body.lower()
    assert "Ola" not in body and "SoftBank" not in body


def test_heuristic_builds_bridges_and_questions() -> None:
    heur = _heuristic_cash_flow_spec(
        company="Test3",
        corpus=_cf_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
        prior_historical={
            "shared_fact_register": [
                {
                    "metric": "EBITDA",
                    "value": "80",
                    "period": "FY2024",
                    "period_type": "actual",
                    "unit": "INR Cr",
                }
            ]
        },
    )
    assert heur.get("cash_bridge")
    assert any("Opening" in str(r.get("label")) for r in heur["cash_bridge"])
    assert any("Closing" in str(r.get("label")) for r in heur["cash_bridge"])
    assert heur.get("ebitda_to_cash_bridge")
    assert any(
        "EBITDA" in str(r.get("label")) for r in heur["ebitda_to_cash_bridge"]
    )
    assert heur.get("cash_metrics", {}).get("cash_conversion_pct") is not None
    assert heur.get("liquidity", {}).get("pressure") != "unavailable"
    assert heur.get("questions")
    assert questions_complete(heur["questions"])
    # Rich corpus may explicitly state no material gaps
    assert any(
        "missing" in q.get("question", "").lower()
        or "no material" in q.get("question", "").lower()
        for q in heur["questions"]
    )
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    # Capex split present
    cats = {r.get("category") for r in (heur.get("capex_split") or []) if isinstance(r, dict)}
    assert "maintenance" in cats or "growth" in cats or "undifferentiated" in cats


def test_missing_cash_is_not_distress() -> None:
    heur = _heuristic_cash_flow_spec(
        company="SparseCo",
        corpus="SparseCo Limited provides services. No cash statement disclosed.",
        sources=["note.pdf"],
    )
    liq = heur.get("liquidity") or {}
    assert liq.get("pressure") == "unavailable"
    joined = " ".join(str(n) for n in (liq.get("notes") or [])).lower()
    assert "distress" in joined or "missing" in joined
    assert heur.get("reliance_verdict") in {"LIMITED", "BLOCKED"}
    assert questions_complete(heur.get("questions") or [])


def test_markdown_follows_prompt_book() -> None:
    heur = _heuristic_cash_flow_spec(
        company="Test3",
        corpus=_cf_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
    )
    md = render_cash_flow_markdown("Cash Flow", heur)
    assert "## 1. Opening → Closing Cash" in md
    assert "## 2. EBITDA → OCF → FCF" in md
    assert "## 5. Liquidity & Runway" in md
    assert "## 6. Questions and Inputs Required" in md or "## 7. Quality" in md
    assert "## 7. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "invest or pass" in md.lower()
    assert "Formula" in md or "formula" in md.lower()


def test_build_cash_flow_prefer_heuristic() -> None:
    spec = build_cash_flow_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "05_Financial_Due_Diligence.pdf",
                    "cdl_category": "financial",
                    "excerpt": _cf_corpus(),
                }
            ],
            "category_counts": {"financial": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-24a"
    md = render_cash_flow_markdown("Cash Flow", spec)
    assert "## 1. Opening" in md


def test_render_agent_document_cash_flow() -> None:
    output = {
        "agentName": "Cash Flow",
        "target_company": "Test3",
        "sources": ["05_Financial_Due_Diligence.pdf"],
        "document": (
            "# Cash Flow\n\n"
            "## 1. Opening → Closing Cash\n\n"
            "Seeded.\n\n"
            "## 7. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("cash_flow", output)
    assert "## 1. Opening" in rendered
    assert "**Recommendation:**" not in rendered


def test_wc_days_require_denominator_note() -> None:
    heur = _heuristic_cash_flow_spec(
        company="Test3",
        corpus=_cf_corpus(),
        sources=["cf.pdf"],
    )
    days = heur.get("wc_days") or []
    assert days
    for row in days:
        if row.get("value_days") is not None:
            assert "match" in str(row.get("denominator") or "").lower()
