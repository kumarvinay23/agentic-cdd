"""Deal Context prompt-book document — DiligenceIQ house rules + agent prompt."""

from __future__ import annotations

import re

from agetic_cdd_api.agent_document_deal_context import (
    _CAGR,
    _SHARE,
    _first_captured_group,
    _first_match,
    _heuristic_deal_context_spec,
    build_deal_context_spec,
    render_deal_context_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import (
    compose_system,
    house_rules,
    listed_agents,
    questions_complete,
    validate_question,
)


class _FakeDeal:
    id = "deal-dc-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"
    materiality = None
    cdd_metadata: dict = {}


class _FakeDealWithSlots(_FakeDeal):
    company = "Compost Crew"
    name = "Compost Crew"
    sector = "Waste"
    cdd_metadata = {
        "geography": "UK",
        "deal_perimeter": "UK operating subsidiaries",
        "transaction_type": "share purchase",
        "as_of_date": "31 Mar 2026",
        "decision_stage": "IC",
        "materiality": "£0.5m EBITDA",
    }


def _ola_index() -> dict:
    excerpt = (
        "Legal Name Ola Electric Mobility Limited. Indian electric two-wheeler market. "
        "Line Item FY2021 FY2022 FY2023 FY2024E FY2025E "
        "Revenue 8 456 2,630 4,900 8,200. EBITDA still negative. "
        "Market share of 35%. Revenue CAGR of 120%. "
        "Total Headcount (FTE) 3,200 8,500 9,800. "
        "Acquisition growth equity investment thesis. FAME-II subsidy noted."
    )
    return {
        "document_count": 3,
        "category_counts": {
            "deal_strategy": 1,
            "company_management": 1,
            "financial": 1,
            "market_competition": 1,
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
                "excerpt": excerpt,
            },
            {
                "filename": "02_Corporate_Overview.pdf",
                "cdl_category": "company_management",
                "excerpt": excerpt,
            },
        ],
    }


def test_compose_system_prepends_house_rules() -> None:
    system = compose_system(
        "deal_context_and_objectives",
        sector="Electric Two-Wheelers",
        geography="India",
        materiality="₹50 cr",
    )
    rules = house_rules(materiality="₹50 cr", sector="Electric Two-Wheelers", geography="India")
    assert system.startswith(rules[:80])
    assert "WHERE TO LOOK" in system
    assert "deal_context_and_objectives" in listed_agents()
    assert "Do not issue an investment verdict" in system
    assert "Electric Two-Wheelers" in system
    assert "₹50 cr" in system
    # House rules appear once (not duplicated inside agent body).
    assert system.count("WHERE TO LOOK, IN THIS ORDER") == 1


def test_deal_context_markdown_follows_prompt_book() -> None:
    corpus = (
        _ola_index()["documents"][0]["excerpt"]
        + " "
        + _ola_index()["documents"][1]["excerpt"]
    )
    spec = build_deal_context_spec(
        _FakeDeal(),
        index=_ola_index(),
        company="Test3",
    )
    # Force heuristic path for deterministic assertions when Gemini is off —
    # build may call Gemini; if so, still assert render contract.
    from agetic_cdd_api.agent_document_deal_context import _heuristic_deal_context_spec

    heur = _heuristic_deal_context_spec(
        company="Test3",
        corpus=corpus,
        sources=[d["filename"] for d in _ola_index()["documents"]],
        document_count=3,
    )
    md = render_deal_context_markdown("Deal Context & Objectives", heur)

    assert "## 1. Executive Summary" in md
    assert "## 2. Key Investment Hypotheses (Must-Be-True)" in md
    assert "## 5. Headline Fact Ledger" in md
    assert "## 6. Quality & Reliance" in md
    assert "## 4. Questions and Inputs Required" in md
    assert "Preliminary Investment Verdict" not in md
    assert "Invest in Test3" not in md
    assert "**Quality:**" in md
    assert "**Reliance:**" in md
    assert "Legal Entity" in md
    assert "Perimeter" in md
    assert "Fail Threshold" in md or "threshold" in md.lower()
    assert "Source Locator" in md
    assert "Closure Test" in md
    assert len(heur.get("fact_ledger") or []) >= 15
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    for hyp in heur.get("hypotheses") or []:
        assert hyp.get("tested_by_agent"), "hypothesis missing tested_by_agent"
    qs = heur.get("questions") or []
    assert qs
    assert questions_complete(qs)
    for q in qs:
        assert validate_question(q) == []
    # Sanity: build_deal_context_spec returns a renderable spec
    rendered = render_deal_context_markdown("Deal Context & Objectives", spec)
    assert "## 1. Executive Summary" in rendered
    assert "Preliminary Investment Verdict" not in rendered


def test_deal_slots_exported_into_overview_and_compose() -> None:
    system = compose_system(
        "deal_context_and_objectives",
        **{
            "sector": "Waste",
            "geography": "UK",
            "target_company": "Compost Crew",
            "deal_perimeter": "UK operating subsidiaries",
            "transaction_type": "share purchase",
            "as_of_date": "31 Mar 2026",
            "decision_stage": "IC",
            "materiality": "£0.5m EBITDA",
        },
    )
    assert "Compost Crew" in system
    assert "UK operating subsidiaries" in system
    assert "share purchase" in system
    assert "31 Mar 2026" in system

    from agetic_cdd_api.agent_document_deal_context import _heuristic_deal_context_spec

    # Build with metadata slots — perimeter must land on overview.
    index = {
        "document_count": 1,
        "documents": [
            {
                "filename": "teaser.pdf",
                "cdl_category": "deal_strategy",
                "excerpt": (
                    "Compost Crew Limited UK waste collections. "
                    "Share purchase of operating subsidiaries. "
                    "Revenue FY2024 12.0 FY2025 14.0. EBITDA positive."
                ),
            }
        ],
    }
    spec = build_deal_context_spec(
        _FakeDealWithSlots(),
        index=index,
        company="Compost Crew",
    )
    # If Gemini answered, still require slot export; else heuristic path.
    overview = spec.get("overview") if isinstance(spec.get("overview"), dict) else {}
    slots = spec.get("deal_slots") if isinstance(spec.get("deal_slots"), dict) else {}
    assert slots.get("deal_perimeter") == "UK operating subsidiaries" or overview.get(
        "perimeter"
    ) == "UK operating subsidiaries"
    assert "share purchase" in str(overview.get("transaction_type") or slots.get("transaction_type") or "")
    md = render_deal_context_markdown("Deal Context & Objectives", spec)
    assert "UK operating subsidiaries" in md or "share purchase" in md
    assert "Closure Test" in md


def test_perimeter_gap_raises_question_when_unevidenced() -> None:
    from agetic_cdd_api.agent_document_deal_context import (
        _ensure_perimeter_questions,
        _normalize_deal_context_questions,
    )

    qs = _ensure_perimeter_questions(
        _normalize_deal_context_questions(
            [
                {
                    "question": "What is top-customer share?",
                    "required_records": "Customer ledger",
                    "decision_effect": "concentration",
                    "priority": "signing_condition",
                    "owner": "commercial",
                    "timing": "T+10",
                    "closure_test": "Top-10 revenue reconcile",
                    "interim_treatment": "Concentration UNKNOWN",
                }
            ]
        ),
        overview={
            "perimeter": "N/A (data room did not provide it) — Information request: acquisition perimeter",
            "transaction_type": "",
        },
    )
    joined = " ".join(q["question"].lower() for q in qs)
    assert "perimeter" in joined
    assert "transaction" in joined
    assert questions_complete(qs)


def test_first_captured_group_safe_on_alt_branches() -> None:
    # Both _SHARE branches: never raise if match groups include None.
    m1 = _first_match(_SHARE, "market share of 35%")
    assert _first_captured_group(m1) == "35"
    m2 = _first_match(_SHARE, "~12.5% market share")
    assert _first_captured_group(m2) == "12.5"
    assert _first_captured_group(None) is None
    # Synthetic match with all-None groups must not raise StopIteration.
    empty = re.match(r"(a)|(b)", "x")
    assert empty is None or _first_captured_group(empty) is None
    class _FakeMatch:
        def groups(self):
            return (None, None)

    assert _first_captured_group(_FakeMatch()) is None  # type: ignore[arg-type]
    cagr = _first_captured_group(_first_match(_CAGR, "Revenue CAGR of 120%"))
    assert cagr == "120"


def test_heuristic_thesis_read_and_fact_ledger_bounds() -> None:
    heur = _heuristic_deal_context_spec(
        company="Test3",
        corpus=(
            "Legal Name Test3 Ltd. Electric two-wheeler market. "
            "Market share of 35%. Revenue CAGR of 120%. "
            "Acquisition growth equity."
        ),
        sources=["teaser.pdf"],
        document_count=1,
    )
    thesis = heur.get("thesis_read") or ""
    assert "Test3" in thesis
    assert thesis.strip().endswith(".") or "hypotheses" in thesis.lower()
    ledger = heur.get("fact_ledger") or []
    assert 15 <= len(ledger) <= 25
    # Padding stops once we hit 15 — gaps are N/A requests, not truncating real facts.
    real = [r for r in ledger if not str(r.get("value", "")).startswith("N/A")]
    assert any(r.get("fact") == "Market share" for r in real)


def test_sanitize_chart_label_paste_rewrites_slide_chrome() -> None:
    from agetic_cdd_api.report_builder_base import sanitize_chart_label_paste

    raw = (
        "CONTRACT POTENTIAL OUR MODEL ASSUMPTION 12,000 Homes today "
        "Waitlist = 2,300 60,000 Homes by 2030 30,000 Homes by 2030"
    )
    clean = sanitize_chart_label_paste(raw)
    assert "CONTRACT POTENTIAL OUR MODEL" not in clean
    assert "12,000 homes today" in clean.lower()
    assert "60,000 homes by 2030" in clean.lower()
    assert "30,000 homes by 2030" in clean.lower()


def test_align_homes_dollars_fixes_crossed_case_pairing() -> None:
    """60k must not keep the 30k case dollar when the corpus pairs them separately."""
    from agetic_cdd_api.agent_document_deal_context import _align_homes_dollars

    corpus = (
        "Case A: 30,000 homes generating $10.4M. "
        "Case B: 60,000 homes generating $22.2M."
    )
    bad = (
        "from 12,000 active locations in 2026 to 60,000 targeted locations "
        "by 2030, growing segment revenue from $3.00M in 2025 to $10.42M in 2030"
    )
    fixed = _align_homes_dollars(bad, corpus)
    assert "60,000" in fixed
    assert "$22.2M" in fixed
    assert "$3.00M" in fixed  # baseline left alone
    # Intact dual-case sentence must not be rewritten into $22.2M to $22.2M.
    good = (
        "to 30,000–60,000 homes by 2030, generating $10.4M to $22.2M."
    )
    assert _align_homes_dollars(good, corpus) == good


def test_heuristic_prefers_evidenced_contract_over_cim_marketing() -> None:
    """Driver 1 must quote figures from this corpus — not a hardcoded canon line."""
    corpus = (
        "Acme Organics is Metro Region's closed-loop composting leader with a "
        "path to a $50 million business by 2030 anchored by long-term contracts. "
        "Expansion of the D.C. municipal contract from ~12,000 homes "
        "($3.0M FY2025A municipal revenue) to 30,000–60,000 homes by 2030, "
        "generating $10.4M to $22.2M. Sustainability growth demand is strong."
    )
    heur = _heuristic_deal_context_spec(
        company="Acme Organics",
        corpus=corpus,
        sources=["cim.pdf", "model.xlsx"],
        document_count=2,
    )
    drivers = heur.get("drivers") or []
    assert drivers
    d1 = drivers[0]
    text = str(d1.get("text") or "")
    assert "[Hypothesis]" not in text
    assert "$50 million" not in text
    # Figures must come from the corpus sentence above.
    assert "12,000" in text and "$3.0M" in text
    assert "$10.4M" in text and "$22.2M" in text
    assert d1.get("is_hypothesis") is False
    assert "N/A" not in str(d1.get("figure") or "")

    # Different deal / different figures — must surface those, not Compost Crew canon.
    other = (
        "Municipal contract expands from 5,000 homes ($1.2M FY2024A) "
        "to 15,000 homes generating $4.5M by 2028."
    )
    heur2 = _heuristic_deal_context_spec(
        company="OtherCo",
        corpus=other,
        sources=["model.xlsx"],
        document_count=1,
    )
    d1b = (heur2.get("drivers") or [{}])[0]
    t2 = str(d1b.get("text") or "")
    assert "5,000" in t2 and "$1.2M" in t2
    assert "$4.5M" in t2
    assert "$3.0M" not in t2 and "$10.4M" not in t2


def test_render_agent_document_deal_context_prefers_quality_section() -> None:
    output = {
        "agentName": "Deal Context & Objectives",
        "target_company": "Test3",
        "document": (
            "# Deal Context & Objectives\n\n"
            "## 5. Headline Fact Ledger\n\n"
            "facts\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("deal_context_and_objectives", output)
    assert "## 6. Quality & Reliance" in rendered
    assert "Preliminary Investment Verdict" not in rendered
