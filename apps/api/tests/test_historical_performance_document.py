"""Historical Performance — DiligenceIQ prompt-book shared financial facts."""

from __future__ import annotations

from agetic_cdd_api.agent_document_historical_performance import (
    _heuristic_historical_performance_spec,
    build_historical_performance_spec,
    render_historical_performance_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-hp-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _hp_corpus() -> str:
    return (
        "05 Financial Due Diligence Capital Structure, P&L & Risk Analysis "
        "Profit & Loss Summary (INR Crore) "
        "Line Item FY2021 FY2022 FY2023 FY2024E FY2025E "
        "Revenue 8 456 2,630 4,900 8,200 "
        "Cost of Goods Sold (11) (420) (2,443) (4,288) (6,560) "
        "Gross Profit (3) 36 187 612 1,640 "
        "Gross Margin (%) -37.5% 7.9% 7.1% 12.5% 20.0% "
        "R&D Expenses (85) (210) (380) (480) (520) "
        "Sales & Marketing (40) (180) (420) (540) (680) "
        "G&A Expenses (35) (120) (320) (380) (430) "
        "EBITDA (163) (474) (933) (788) 10 "
        "EBITDA Margin (%) N/M -103.9% -35.5% -16.1% 0.1% "
        "04 Commercial Due Diligence Market, Sales & Customer Analysis "
        "Sales Metric FY2022 FY2023 FY2024E Industry Avg "
        "Revenue (INR Cr) 190 1,468 3,140 — "
        "Monthly Run Rate (Units) 1,675 12,675 26,667 — "
        "Customer mix shifted toward fleet contracts in FY2024. "
        "One-off launch marketing spend elevated FY2022 EBITDA loss. "
        "Q1 FY2024 revenue below Q1 FY2023 same period last year due to seasonality."
    )


def test_historical_performance_prompt_book_listed() -> None:
    system = compose_system("historical_performance", sector="EV", geography="India")
    assert "historical_performance" in listed_agents()
    assert "accounting" in system.lower() or "revenue" in system.lower()
    body = agent_prompt("historical_performance")
    assert "Ola" not in body and "SoftBank" not in body
    assert "CIM" in body or "management summary" in body.lower()
    assert "shared basis" in body.lower() or "every other agent" in body.lower()


def test_historical_performance_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_historical_performance.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("historical_performance")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_period_facts_labelled_from_accounts() -> None:
    heur = _heuristic_historical_performance_spec(
        company="Test3",
        corpus=_hp_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
    )
    facts = heur.get("period_facts") or []
    assert facts
    rev = [
        f for f in facts
        if isinstance(f, dict) and str(f.get("line_item") or "").lower() == "revenue"
    ]
    assert rev
    types = {str(f.get("period_type")) for f in rev}
    assert "actual" in types or "forecast" in types
    assert all(f.get("basis") == "accounting_records" for f in rev)


def test_trend_named_in_first_line() -> None:
    heur = _heuristic_historical_performance_spec(
        company="Test3",
        corpus=_hp_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
    )
    trend = str(heur.get("trend_headline") or "")
    snap = str(heur.get("insight_snapshot") or "")
    assert "EBITDA" in trend or "earnings" in trend.lower() or "trough" in trend.lower()
    assert "trough" in snap.lower() or "peaked" in snap.lower() or "EBITDA" in snap


def test_accounts_vs_cim_shows_both() -> None:
    heur = _heuristic_historical_performance_spec(
        company="Test3",
        corpus=_hp_corpus(),
        sources=["05_Financial_Due_Diligence.pdf", "04_Commercial_Due_Diligence.pdf"],
    )
    cim = heur.get("accounts_vs_cim") or []
    gaps = [
        r for r in cim
        if isinstance(r, dict)
        and str(r.get("difference") or "") not in {"", "Aligned"}
        and not str(r.get("difference") or "").startswith("Information")
    ]
    assert gaps
    assert any(r.get("chosen_basis") == "accounting_records" for r in gaps)
    assert any(
        "INR" in str(r.get("accounts_value")) and "INR" in str(r.get("cim_value"))
        for r in gaps
    )


def test_markdown_follows_prompt_book() -> None:
    heur = _heuristic_historical_performance_spec(
        company="Test3",
        corpus=_hp_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
    )
    md = render_historical_performance_markdown("Historical Performance", heur)
    assert "## 1. Financial Record" in md
    assert "## 2. Growth & Margin" in md
    assert "## 3. Accounts vs CIM" in md
    assert "## 4. Seasonal" in md
    assert "## 5. Comparability Distortions" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert heur.get("pl_lines")
    assert heur.get("performance_metrics")
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert "shared basis" in md.lower() or "accounting" in md.lower()


def test_normalise_strips_recommendation() -> None:
    from agetic_cdd_api.agent_document_historical_performance import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Revenue strong — invest",
            "trend_headline": "EBITDA trough was FY2023",
            "period_facts": [
                {
                    "line_item": "Revenue",
                    "period": "FY2024E",
                    "period_type": "forecast",
                    "value": 4900,
                    "unit": "INR Cr",
                    "basis": "accounting_records",
                }
            ],
            "growth_and_margins": [{"metric": "Revenue YoY growth", "value": "+86%"}],
            "accounts_vs_cim": [],
            "seasonality": [],
            "comparability_distortions": [],
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "READY",
        },
        sources=["a.pdf"],
        legacy_spec=None,
        corpus=_hp_corpus(),
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()


def test_render_agent_document_historical_performance() -> None:
    output = {
        "agentName": "Historical Performance",
        "target_company": "Test3",
        "sources": ["05_Financial_Due_Diligence.pdf"],
        "document": (
            "# Historical Performance\n\n"
            "## 1. Financial Record (Accounting Basis)\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("historical_performance", output)
    assert "## 1. Financial Record" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_historical_performance_from_corpus() -> None:
    spec = build_historical_performance_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "05_Financial_Due_Diligence.pdf",
                    "cdl_category": "financial",
                    "doc_kind": "financial",
                    "excerpt": _hp_corpus(),
                }
            ],
            "category_counts": {"financial": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_historical_performance_markdown("Historical Performance", spec)
    assert "## 2. Growth & Margin" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-23"
