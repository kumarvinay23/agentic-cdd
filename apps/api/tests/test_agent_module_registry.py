"""One approved module per agent. An old copy cannot be stored as completed."""

from agetic_cdd_api.agent_module_registry import (
    APPROVED_REGULATORY_MODULE,
    RETIRED_REGULATORY_MODULE,
    approved_module_id,
    duplicate_agent_keys,
    prepare_completion,
)
from agetic_cdd_api.pipeline_catalog import all_agent_keys


def test_catalog_has_one_approved_module_per_agent() -> None:
    keys = all_agent_keys()
    assert duplicate_agent_keys() == []
    assert len(keys) == len(set(keys))
    modules = [approved_module_id(key) for key in keys]
    assert all(modules)
    assert len(modules) == len(set(modules))
    assert approved_module_id("regulatory_compliance") == APPROVED_REGULATORY_MODULE
    assert approved_module_id("company_background") == "pipeline.company_background"


def test_retired_regulatory_copy_cannot_complete() -> None:
    legacy = prepare_completion(
        "regulatory_compliance",
        {
            "status": "completed",
            "module_id": RETIRED_REGULATORY_MODULE,
            "spec": {"risks": [{"clause": "Pending lawsuit in Texas."}]},
        },
    )
    assert legacy["status"] == "needs_repair"
    assert legacy["status"] != "completed"

    unmarked = prepare_completion(
        "regulatory_compliance",
        {"status": "completed", "spec": {"risks": [{"clause": "Invented litigation."}]}},
    )
    assert unmarked["status"] == "needs_repair"

    forged = prepare_completion(
        "regulatory_compliance",
        {
            "status": "completed",
            "module_id": APPROVED_REGULATORY_MODULE,
            "spec": {"risks": [{"clause": "Invented litigation."}]},
        },
    )
    assert forged["status"] == "needs_repair"


def test_approved_regulatory_module_can_complete() -> None:
    approved = prepare_completion(
        "regulatory_compliance",
        {
            "status": "completed",
            "module_id": APPROVED_REGULATORY_MODULE,
            "module_version": "1",
            "spec": {
                "composer": "heuristic_v1",
                "permit_register": [],
                "litigation_register": [],
            },
        },
    )
    assert approved["status"] == "completed"
    assert approved["module_id"] == APPROVED_REGULATORY_MODULE


def test_other_agent_rejects_a_foreign_module() -> None:
    foreign = prepare_completion(
        "company_background",
        {"status": "completed", "module_id": "agent_document_company_background_v0"},
    )
    assert foreign["status"] == "needs_repair"

    official = prepare_completion("company_background", {"summary": "Entity profile."})
    assert official["status"] == "completed"
    assert official["module_id"] == "pipeline.company_background"
    assert official["module_version"] == "1"


def test_missing_required_input_cannot_complete() -> None:
    empty_room = prepare_completion(
        "market_volume_and_growth",
        {
            "status": "empty_vdr",
            "empty_vdr": True,
            "source_coverage": "missing",
            "summary": "No structured signals; foundation soft fill.",
        },
    )
    assert empty_room["status"] == "needs_repair"
    assert empty_room["status"] != "completed"

    no_sources = prepare_completion(
        "company_background",
        {"status": "completed", "source_coverage": "missing", "spec": {"legal_name": "Northwind"}},
    )
    assert no_sources["status"] == "needs_repair"

    fixture = prepare_completion(
        "trading_comps",
        {"stub": True, "status": "completed", "summary": "Fixture output for Trading Comps."},
    )
    assert fixture["status"] == "needs_repair"

    named = prepare_completion(
        "capital_structure",
        {"status": "completed", "missing_inputs": ["net debt schedule", "cap table"]},
    )
    assert named["status"] == "needs_repair"
    assert "net debt schedule" in named["error"]

    from_store = prepare_completion(
        "recommendation",
        {
            "status": "completed",
            "source_coverage": "missing",
            "extract_source": "stores",
            "sources": [],
        },
    )
    assert from_store["status"] == "completed"

    partial = prepare_completion(
        "company_background",
        {
            "status": "completed",
            "source_coverage": "partial",
            "sources": ["CIM.pdf"],
        },
    )
    assert partial["status"] == "completed"


def test_pass_closed_ready_require_a_specific_source() -> None:
    bare = prepare_completion(
        "company_background",
        {
            "status": "completed",
            "source_coverage": "full",
            "sources": ["data room"],
            "spec": {
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
                "counsel_letter": {"status": "CLOSED", "detail": "No letter in the data room."},
                "rc_evidence_qa": [{"check": "permits", "status": "PASS", "finding": "Present."}],
            },
        },
    )
    assert bare["spec"]["quality_verdict"] == "REWORK"
    assert bare["spec"]["reliance_verdict"] == "LIMITED"
    assert bare["spec"]["counsel_letter"]["status"] == "OPEN"
    assert bare["spec"]["rc_evidence_qa"][0]["status"] == "FAIL"
    assert bare["status"] == "completed"
    assert bare["verdicts_withheld"]

    named = prepare_completion(
        "company_background",
        {
            "status": "completed",
            "source_coverage": "full",
            "sources": ["Corporate Overview.pdf"],
            "spec": {
                "quality_verdict": "PASS",
                "reliance_verdict": "READY",
                "counsel_letter": {
                    "status": "CLOSED",
                    "detail": "Closed on Counsel letter 12.pdf.",
                },
            },
        },
    )
    assert named["spec"]["quality_verdict"] == "PASS"
    assert named["spec"]["reliance_verdict"] == "READY"
    assert named["spec"]["counsel_letter"]["status"] == "CLOSED"
    assert "verdicts_withheld" not in named


def test_unknown_agent_cannot_complete() -> None:
    unknown = prepare_completion("regulatory_compliance_old", {"status": "completed"})
    assert unknown["status"] == "needs_repair"
