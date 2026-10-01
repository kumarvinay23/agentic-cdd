"""Customer Satisfaction — DiligenceIQ prompt-book sentiment evidence."""

from __future__ import annotations

from agetic_cdd_api.agent_document_customer_satisfaction import (
    _association_only,
    _heuristic_customer_satisfaction_spec,
    _score_is_traceable,
    build_customer_satisfaction_spec,
    render_customer_satisfaction_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-sat-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _sat_corpus() -> str:
    return (
        "Customer survey dated Q1 FY2024. Target population: active riders. "
        "Sample size 2,400. Response rate 31%. Segment mix: retail 60% / fleet 40%. "
        "Question wording: 'How likely are you to recommend?' on a 0-10 scale. "
        "Scores from valid responses only (promoters minus detractors). "
        "NPS 34. Service Satisfaction 52%. "
        "Service Delay & Unresolved Complaints 31% Critical. "
        "Complaints 12,400. Resolution time 8.3 days. Missed service 4.2%. "
        "Service delays preceded subsequent cancellations in the churn analysis. "
        "App store reviews average 3.2 stars."
    )


def test_customer_satisfaction_prompt_book_listed() -> None:
    system = compose_system("customer_satisfaction", sector="EV", geography="India")
    assert "customer_satisfaction" in listed_agents()
    assert "survey" in system.lower() or "sentiment" in system.lower()
    body = agent_prompt("customer_satisfaction")
    assert "Ola" not in body and "SoftBank" not in body
    assert "association" in body.lower()
    assert "self-selected" in body.lower() or "self selected" in body.lower() or "self_selected" in body.lower() or "public reviews" in body.lower()


def test_customer_satisfaction_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_customer_satisfaction.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("customer_satisfaction")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_score_traceability_and_association() -> None:
    ok, _ = _score_is_traceable(
        34,
        corpus="NPS 34 from valid responses",
        definition="Scores from valid responses on 0-10 scale",
        source="(DOC: data room financials)",
    )
    assert ok is True
    bad, _ = _score_is_traceable(99, corpus="no score here", definition="", source="")
    assert bad is False
    assert _association_only("service delays preceded cancellations") is True


def test_customer_satisfaction_markdown_follows_prompt_book() -> None:
    heur = _heuristic_customer_satisfaction_spec(
        company="Test3",
        corpus=_sat_corpus(),
        sources=["04_Commercial_Due_Diligence.pdf"],
        legacy_spec={
            "nps": 34.0,
            "service_satisfaction_pct": 52.0,
            "churn_drivers": [
                {
                    "driver": "Service Delay & Unresolved Complaints",
                    "contribution_pct": 31.0,
                    "severity": "Critical",
                }
            ],
            "satisfaction_notes": ["Legacy satisfaction note"],
        },
    )
    md = render_customer_satisfaction_markdown("Customer Satisfaction", heur)

    assert "## 1. Survey" in md
    assert "## 2. Operational" in md
    assert "## 3. Service Quality" in md or "## 3." in md
    assert "## 4. Public Reviews" in md
    assert "## 5. Research" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert heur.get("nps") == 34.0 or heur.get("nps") == 34
    assert heur.get("service_satisfaction_pct") == 52.0 or heur.get("service_satisfaction_pct") == 52
    drivers = heur.get("churn_drivers") or []
    assert isinstance(drivers, list) and drivers
    assoc = heur.get("churn_association") or {}
    assert assoc.get("association_only") is True
    assert assoc.get("comparable") is True
    reviews = heur.get("public_reviews") or {}
    assert reviews.get("treated_as") == "self_selected_signal"
    assert "association" in md.lower()
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert isinstance(heur.get("satisfaction_notes"), list)


def test_inaccessible_survey_is_gap_not_finding() -> None:
    heur = _heuristic_customer_satisfaction_spec(
        company="Test3",
        corpus="Survey file missing / inaccessible. Pack could not be opened.",
        sources=["a.pdf"],
    )
    survey = heur.get("survey_assessment") or {}
    assert survey.get("inaccessible_file_note")
    snap = (heur.get("insight_snapshot") or "").lower()
    assert "poor customer focus" not in snap or "information gap" in str(survey).lower()
    md = render_customer_satisfaction_markdown("Customer Satisfaction", heur)
    assert "information gap" in md.lower() or "does **not** imply" in md.lower()


def test_normalise_strips_recommendation() -> None:
    from agetic_cdd_api.agent_document_customer_satisfaction import _normalise_llm_spec
    import inspect

    sig = inspect.signature(_normalise_llm_spec)
    kwargs: dict = {"sources": ["a.pdf"], "legacy_spec": None}
    if "corpus" in sig.parameters:
        kwargs["corpus"] = "NPS 34. Complaints 100."

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Customers hate the product — invest",
            "survey_assessment": {"present": True, "date": "Q1 FY2024"},
            "nps": 34,
            "service_satisfaction_pct": 52,
            "churn_drivers": [],
            "operational_signals": [],
            "churn_association": {"comparable": True, "association_only": False},
            "public_reviews": {"treated_as": "research"},
            "research_design": {"needed": False},
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
    assoc = llm.get("churn_association") or {}
    assert assoc.get("association_only") is True
    reviews = llm.get("public_reviews") or {}
    assert reviews.get("treated_as") == "self_selected_signal"


def test_render_agent_document_customer_satisfaction() -> None:
    output = {
        "agentName": "Customer Satisfaction",
        "target_company": "Test3",
        "sources": ["04_Commercial_Due_Diligence.pdf"],
        "document": (
            "# Customer Satisfaction\n\n"
            "## 1. Survey Representativeness\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("customer_satisfaction", output)
    assert "## 1. Survey" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_customer_satisfaction_from_corpus() -> None:
    spec = build_customer_satisfaction_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "04_Commercial_Due_Diligence.pdf",
                    "cdl_category": "customer",
                    "excerpt": _sat_corpus(),
                }
            ],
            "category_counts": {"customer": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_customer_satisfaction_markdown("Customer Satisfaction", spec)
    assert "## 2. Operational" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-12"
