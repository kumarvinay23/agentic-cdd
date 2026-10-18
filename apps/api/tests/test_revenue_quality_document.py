"""Revenue Quality — DiligenceIQ prompt-book durability of revenue."""

from __future__ import annotations

from pathlib import Path

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
    metadata = {
        "deal_perimeter": "standalone ops",
        "transaction_type": "majority buyout",
        "as_of_date": "2024-12-31",
        "decision_stage": "IC",
    }


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
        "Billed revenue INR 1,200 Cr; recognised revenue INR 1,150 Cr with "
        "deferred revenue of INR 50 Cr at year-end cut-off. "
        "Sales pipeline INR 180 Cr soft; enforceable backlog / committed orders "
        "INR 40 Cr booked not billed. "
        "Price contribution +2pp; volume contribution +4pp; mix shift to fleet +1pp. "
        "New customers / acquisition added INR 90 Cr logos. "
        "Upcoming renewal book: 22% of contracted revenue renews in next 12 months; "
        "cancellation exposure limited to 30-day notice on retail deposits. "
        "No ARR definition stated in the data room."
    )


def test_revenue_quality_prompt_book_listed() -> None:
    system = compose_system(
        "revenue_quality",
        sector="EV",
        geography="India",
        deal_perimeter="standalone ops",
        transaction_type="majority buyout",
        as_of_date="2024-12-31",
        decision_stage="IC",
    )
    assert "revenue_quality" in listed_agents()
    assert "recurring" in system.lower() or "repeat" in system.lower()
    body = agent_prompt("revenue_quality")
    assert "Ola" not in body and "SoftBank" not in body
    assert "balance-sheet" in body.lower() or "Balance-sheet" in body
    assert "bridge" in body.lower()
    assert "questions" in body.lower()
    assert "arr" in body.lower() or "backlog" in body.lower()
    assert "standalone ops" in system.lower() or "deal perimeter" in system.lower()


def test_revenue_quality_not_company_hardcoded() -> None:
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
    assert "Price" in comps and "Volume" in comps and "Mix" in comps
    assert heur.get("retention_metrics", {}).get("nrr_pct") == 81.0


def test_billing_taxonomy_pipeline_arr() -> None:
    heur = _heuristic_revenue_quality_spec(
        company="Test3",
        corpus=_rq_corpus(),
        sources=["13_Valuation_Retention_Comparable_Analysis.pdf"],
    )
    billing = heur.get("billing_recognised") or []
    assert billing
    assert any(
        isinstance(r, dict)
        and (
            "deferred" in str(r.get("recognised") or "").lower()
            or "billed" in str(r.get("billed") or "").lower()
            or "recognised" in str(r.get("recognised") or "").lower()
        )
        for r in billing
    )
    taxonomy = heur.get("revenue_taxonomy") or []
    taxes = {
        str(r.get("taxonomy"))
        for r in taxonomy
        if isinstance(r, dict) and r.get("taxonomy")
    }
    assert "contracted" in taxes
    assert "cancellable" in taxes or "habitual" in taxes or "one_off" in taxes
    pipeline = heur.get("pipeline_vs_backlog") or []
    kinds = {str(r.get("kind")) for r in pipeline if isinstance(r, dict)}
    assert "pipeline" in kinds and "backlog" in kinds
    arr = heur.get("arr_discipline") or {}
    assert arr.get("stated") is False or not arr.get("definition_present")
    renewals = heur.get("renewal_cancellation") or []
    assert renewals


def test_rq_evidence_qa_and_questions() -> None:
    heur = _heuristic_revenue_quality_spec(
        company="Test3",
        corpus=_rq_corpus(),
        sources=["a.pdf"],
    )
    qa = heur.get("rq_evidence_qa") or []
    checks = {r.get("check") for r in qa if isinstance(r, dict)}
    for need in (
        "billing_recognised_reconcile",
        "revenue_taxonomy",
        "price_volume_mix_acquisition",
        "renewal_cancellation_exposure",
        "pipeline_vs_backlog",
        "arr_discipline",
        "stickiness_cash_flow_cross_check",
        "recurring_ne_enforceable_backlog",
    ):
        assert need in checks
    assert any(r.get("status") == "FAIL" for r in qa if isinstance(r, dict))
    # Without Stickiness/Cash Flow priors, cross-check FAILs and READY is capped
    assert heur.get("reliance_verdict") in {"LIMITED", "BLOCKED"}
    questions = heur.get("questions") or []
    assert questions
    assert all(
        isinstance(q, dict) and q.get("question") and q.get("priority")
        for q in questions
    )


def test_stickiness_cross_check_conflict_forces_rework() -> None:
    heur = _heuristic_revenue_quality_spec(
        company="Test3",
        corpus=_rq_corpus(),
        sources=["a.pdf"],
        stickiness_spec={"retention_metrics": {"nrr_pct": 95.0, "grr_pct": 74.0}},
        cash_flow_spec={"cash_metrics": {"ocf": 10.0}},
    )
    cross = heur.get("stickiness_cash_flow_cross_check") or {}
    assert cross.get("stickiness_present")
    assert cross.get("cash_flow_present")
    assert cross.get("conflicts")
    assert heur.get("quality_verdict") == "REWORK"


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
    assert "## 6. Revenue Quality Evidence QA" in md
    assert "## 7. Questions and Inputs Required" in md
    assert "## 8. Quality & Reliance" in md
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
    assert llm.get("reliance_verdict") == "LIMITED"  # open QA FAILs cap READY
    assert llm.get("rq_evidence_qa")
    assert llm.get("questions")


def test_render_agent_document_revenue_quality() -> None:
    output = {
        "agentName": "Revenue Quality",
        "target_company": "Test3",
        "sources": ["13_Valuation_Retention_Comparable_Analysis.pdf"],
        "document": (
            "# Revenue Quality\n\n"
            "## 1. Revenue Split\n\n"
            "Seeded.\n\n"
            "## 8. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("revenue_quality", output)
    assert "## 1. Revenue Split" in rendered
    assert "**Recommendation:**" not in rendered


def test_deal_slots_on_build() -> None:
    deal = _FakeDeal()
    spec = build_revenue_quality_spec(
        deal,  # type: ignore[arg-type]
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
    slots = spec.get("deal_slots") or {}
    assert isinstance(slots, dict)
    assert slots.get("deal_perimeter") == "standalone ops"
    assert slots.get("decision_stage") == "IC"
    assert slots.get("geography") == "India" or slots.get("sector")
    md = render_revenue_quality_markdown("Revenue Quality", spec)
    assert "## 3. Revenue Bridge" in md
    assert "## 8. Quality & Reliance" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-09b"
    assert spec.get("rq_evidence_qa")
