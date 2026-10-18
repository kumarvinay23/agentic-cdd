"""Agent 0 — shared house_rules, shared QA, Questions schema, helpers."""

from __future__ import annotations

from types import SimpleNamespace

from agetic_cdd_api.prompt_book import (
    SOURCE_CATEGORIES,
    agent_prompt,
    cite_reopen,
    compose_qa,
    compose_system,
    house_rules,
    listed_agents,
    normalize_claim,
    normalize_question,
    normalize_questions,
    normalize_verdicts,
    prompt_vars_from_deal,
    questions_complete,
    recalculate_bridge,
    shared_qa_prompt,
    validate_claim,
    validate_question,
)


def test_house_rules_includes_claim_taxonomy_and_six_sections() -> None:
    text = house_rules(
        sector="Waste",
        geography="UK",
        materiality="£0.5m EBITDA",
        target_company="Compost Crew",
        deal_perimeter="UK operating subsidiaries",
        transaction_type="share purchase",
        as_of_date="31 Mar 2026",
        decision_stage="IC",
    )
    assert "VDR_PRIMARY" in text
    assert "MANAGEMENT_ASSERTION" in text
    assert "COMPUTED" in text
    assert "INTERVIEW" in text
    assert "EXTERNAL" in text
    assert "claim ID" in text.lower() or "claim id" in text.lower()
    assert "Questions and inputs required" in text
    assert "Conclusion and reliance status" in text
    assert "Key findings" in text
    assert "Compost Crew" in text
    assert "share purchase" in text
    assert "31 Mar 2026" in text
    assert "£0.5m EBITDA" in text
    # No unfilled deal-slot brackets for known keys
    for key in (
        "TARGET_COMPANY",
        "DEAL_PERIMETER",
        "TRANSACTION_TYPE",
        "AS_OF_DATE",
        "DECISION_STAGE",
        "MATERIALITY",
        "SECTOR",
        "GEOGRAPHY",
    ):
        assert f"[{key}]" not in text


def test_compose_system_prepends_house_rules() -> None:
    system = compose_system(
        "capital_structure",
        sector="Waste",
        geography="UK",
        target_company="Compost Crew",
    )
    assert "due-diligence analyst" in system.lower() or "investment committee" in system.lower()
    assert "Capital Structure" in system or "facility" in system.lower()
    assert "---" in system
    assert "Compost Crew" in system


def test_shared_qa_and_compose_qa() -> None:
    qa = shared_qa_prompt("capital_structure", target_company="Compost Crew")
    assert "QA issue register" in qa or "issue_id" in qa
    assert "Critical" in qa and "Major" in qa and "Minor" in qa
    assert "cite" in qa.lower() or "Reopen" in qa
    assert "Recalculate" in qa or "recalculate" in qa.lower()
    assert "Capital Structure" in qa
    assert "Compost Crew" in qa

    composed = compose_qa(
        "historical_performance",
        sector="Waste",
        agent_specific_qa="Reject mixed actual/forecast trends.",
    )
    assert "Historical Performance" in composed
    assert "Reject mixed actual/forecast" in composed
    assert "PASS" in composed and "BLOCKED" in composed


def test_questions_schema_normalize_and_validate() -> None:
    loose = {
        "priority": "High",
        "question": "Provide monthly cash bridge FY2025",
        "why": "Could change net debt / liquidity reliance",
        "unlocking_document": "Treasury cash pack, monthly, FY2025",
    }
    row = normalize_question(loose)
    assert row["priority"] == "mandatory_pre_decision"
    assert row["required_records"]
    assert row["decision_effect"]
    assert row["owner"] == "unassigned"
    # Missing closure_test / timing still fail validation until filled
    errs = validate_question(row)
    assert "closure_test" in " ".join(errs)

    complete = {
        **row,
        "closure_test": "Monthly open→close cash reconciling to bank statements",
        "timing": "before IC",
        "interim_treatment": "Liquidity conclusion BLOCKED",
    }
    assert validate_question(complete) == []
    assert questions_complete([complete]) is True
    assert questions_complete([]) is True
    assert questions_complete("No material inputs are missing.") is True
    assert questions_complete([loose]) is False


def test_claim_taxonomy_and_cite_reopen() -> None:
    claim = normalize_claim(
        {
            "claim_id": "CF-01",
            "text": "Closing cash was 1.2 million at 31 December 2025",
            "category": "VDR",
            "locator": "Bank schedule!B12",
            "period": "FY2025",
            "unit": "GBP m",
            "population": "group",
            "basis": "actual",
            "strength": "supported",
        }
    )
    assert claim["source_category"] == "VDR_PRIMARY"
    assert claim["evidence_strength"] == "supported"
    assert validate_claim(claim) == []
    assert "VDR_PRIMARY" in SOURCE_CATEGORIES

    hit = cite_reopen(
        claim=claim,
        source_text="Closing cash balance 1.2 million as at 31 December 2025 per bank.",
        source_accessible=True,
    )
    assert hit["status"] == "supports"

    miss = cite_reopen(
        claim=claim,
        source_text=None,
        source_accessible=False,
    )
    assert miss["status"] == "unverified"


def test_recalculate_bridge() -> None:
    result = recalculate_bridge(
        [
            {"label": "Opening cash", "value": 1.0},
            {"label": "Operating cash flow", "value": 0.5},
            {"label": "Capex", "value": 0.2, "sign": -1},
            {"label": "Closing cash", "value": 1.3},
        ]
    )
    assert result["ok"] is True
    assert abs(result["computed_total"] - 1.3) < 1e-9

    bad = recalculate_bridge(
        [
            {"label": "Opening", "value": 1.0},
            {"label": "Inflow", "value": 0.5},
            {"label": "Closing", "value": 2.0},
        ]
    )
    assert bad["ok"] is False
    assert bad["residual"] is not None


def test_normalize_verdicts() -> None:
    assert normalize_verdicts(quality="PASS", reliance="BLOCKED") == ("PASS", "BLOCKED")
    assert normalize_verdicts(quality="rework_required", reliance="maybe") == (
        "REWORK",
        "BLOCKED",
    )


def test_prompt_vars_from_deal_exports_slots() -> None:
    deal = SimpleNamespace(
        company="Compost Crew",
        sector="Waste",
        geography=None,
        materiality=None,
        cdd_metadata={
            "geography": "UK",
            "deal_perimeter": "UK ops",
            "transaction_type": "share purchase",
            "as_of_date": "31 Mar 2026",
            "decision_stage": "IC",
            "materiality": "£0.5m",
        },
    )
    vars_ = prompt_vars_from_deal(deal)
    assert vars_["target_company"] == "Compost Crew"
    assert vars_["sector"] == "Waste"
    assert vars_["geography"] == "UK"
    assert vars_["deal_perimeter"] == "UK ops"
    assert vars_["transaction_type"] == "share purchase"
    assert vars_["as_of_date"] == "31 Mar 2026"
    assert vars_["decision_stage"] == "IC"
    assert vars_["materiality"] == "£0.5m"

    system = compose_system("scope_and_methodology", **{k: v for k, v in vars_.items() if v})
    assert "Compost Crew" in system
    assert "share purchase" in system


def test_listed_agents_still_includes_core() -> None:
    agents = listed_agents()
    assert "capital_structure" in agents
    assert "deal_context_and_objectives" in agents
    body = agent_prompt("capital_structure", sector="Waste")
    assert "Waste" in body or "facility" in body.lower()


def test_normalize_questions_batch() -> None:
    rows = normalize_questions(
        [
            {
                "question": "Q1",
                "required_records": "R1",
                "decision_effect": "price",
                "priority": "signing_condition",
                "owner": "CFO",
                "timing": "T+5",
                "closure_test": "file received",
                "interim_treatment": "exclude",
            }
        ]
    )
    assert len(rows) == 1
    assert questions_complete(rows)
