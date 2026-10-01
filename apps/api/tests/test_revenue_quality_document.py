"""Revenue Quality — DiligenceIQ prompt-book durability of revenue."""

from __future__ import annotations

from agetic_cdd_api.agent_document_revenue_quality import (
    _heuristic_revenue_quality_spec,
    build_revenue_quality_spec,
    render_revenue_quality_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-rq-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _rq_corpus() -> str:
    return (
        "SECTION A — RETENTION & CHURN PERFORMANCE "
        "Gross Revenue Retention (GRR) 74% FY22: 68% → FY23: 71% → FY24: 74% "
        "Net Revenue Retention (NRR) 81% FY22: 72% → FY23: 78% → FY24: 81% "
        "Logo Churn (%) 39% FY22: 45% → FY23: 42% → FY24: 39% "
        "Revenue Churn (%) 26% FY22: 32% → FY23: 29% → FY24: 26% "
        "Fleet Contract Length Fleet agreements (gig economy, delivery): "
        "12–24 month renewable contracts. Fleet segment (8% of revenue) offers "
        "more predictable renewal visibility than retail. "
        "NRR includes expansion revenue from accessories, software, and service contracts. "
        "Repeat / Referral Purchase (%) N/A 18% 22% 35% "
        "Online Sales Share (%) 72% 70% 68% 31% "
        "One-off launch marketing cohort elevated early logo churn. "
        "No deferred revenue schedule opened in the data room."
    )


def test_revenue_quality_prompt_book_listed() -> None:
    system = compose_system("revenue_quality", sector="EV", geography="India")
    assert "revenue_quality" in listed_agents()
    assert "recurring" in system.lower() or "repeat" in system.lower()
    body = agent_prompt("revenue_quality")
    assert "Ola" not in body and "SoftBank" not in body
    assert "balance-sheet" in body.lower() or "Balance-sheet" in body
    assert "bridge" in body.lower()


def test_revenue_quality_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_revenue_quality.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_revenue_split_reconciles() -> None:
    heur = _heuristic_revenue_quality_spec(
        company="Test3",
        corpus=_rq_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
    )
    split = heur.get("revenue_split") or []
    numeric = [
        r for r in split
        if isinstance(r, dict)
        and isinstance(r.get("share_pct"), (int, float))
        and "reconcile" not in str(r.get("bucket") or "").lower()
    ]
    assert numeric
    total = sum(float(r["share_pct"]) for r in numeric)
    assert abs(total - 100.0) < 1.0
    contracted = next(
        (r for r in numeric if "under contract" in str(r.get("bucket") or "").lower()),
        None,
    )
    assert contracted and float(contracted["share_pct"]) == 8.0


def test_contract_terms_and_bridge() -> None:
    heur = _heuristic_revenue_quality_spec(
        company="Test3",
        corpus=_rq_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
    )
    contracts = heur.get("contract_terms") or []
    assert any(
        isinstance(c, dict) and "contract" in str(c.get("metric") or "").lower()
        for c in contracts
    )
    wart = next(
        (c for c in contracts if isinstance(c, dict) and "remaining term" in str(c.get("metric") or "").lower()),
        None,
    )
    assert wart and "month" in str(wart.get("value") or "").lower()
    bridge = heur.get("revenue_bridge") or []
    comps = {str(b.get("component")) for b in bridge if isinstance(b, dict)}
    assert "Churn" in comps or "Expansion" in comps
    assert heur.get("retention_metrics", {}).get("nrr_pct") == 81.0


def test_no_balance_sheet_ratios() -> None:
    heur = _heuristic_revenue_quality_spec(
        company="Test3",
        corpus=_rq_corpus() + " Current Ratio 1.2x Debt / Equity Ratio 3.5x.",
        sources=["a.pdf"],
    )
    md = render_revenue_quality_markdown("Revenue Quality", heur)
    assert "Current Ratio" not in md
    assert "Debt / Equity" not in md
    assert "balance-sheet" in md.lower() or "Balance-sheet" in md


def test_markdown_follows_prompt_book() -> None:
    heur = _heuristic_revenue_quality_spec(
        company="Test3",
        corpus=_rq_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
    )
    md = render_revenue_quality_markdown("Revenue Quality", heur)
    assert "## 1. Revenue Split" in md
    assert "## 2. Contract Share" in md
    assert "## 3. Revenue Bridge" in md
    assert "## 4. Recognition" in md
    assert "## 5. Non-repeating" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_normalise_strips_recommendation() -> None:
    from agetic_cdd_api.agent_document_revenue_quality import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Durable revenue — invest",
            "revenue_split": [
                {"bucket": "recurring under contract", "share_pct": 8, "period": "FY2024"}
            ],
            "contract_terms": [],
            "revenue_bridge": [],
            "recognition_cutoff": [],
            "non_repeating": [],
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "READY",
        },
        sources=["a.pdf"],
        legacy_spec=None,
        corpus=_rq_corpus(),
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()


def test_render_agent_document_revenue_quality() -> None:
    output = {
        "agentName": "Revenue Quality",
        "target_company": "Test3",
        "sources": ["13_Valuation_Retention_Comparable_Analysis.pdf"],
        "document": (
            "# Revenue Quality\n\n"
            "## 1. Revenue Split\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("revenue_quality", output)
    assert "## 1. Revenue Split" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_revenue_quality_from_corpus() -> None:
    spec = build_revenue_quality_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "13_Valuation_Retention_Comparable_Analysis.pdf",
                    "cdl_category": "financial",
                    "doc_kind": "financial",
                    "excerpt": _rq_corpus(),
                }
            ],
            "category_counts": {"financial": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_revenue_quality_markdown("Revenue Quality", spec)
    assert "## 3. Revenue Bridge" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-09b"
