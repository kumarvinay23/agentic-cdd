"""Must-fail cases fail. Honest gaps pass. A reordered source list keeps the citation."""

from agetic_cdd_api.agent_module_registry import prepare_completion
from agetic_cdd_api.services_calculation_library import ask_calculation
from agetic_cdd_api.services_verification import number_citations, permanent_id, verify

_PASSAGE = "Revenue was 8 in the latest actual year."
_SOURCE = {
    "source_id": "src-accounts",
    "page": 4,
    "text": _PASSAGE,
    "filename": "Accounts.pdf",
}


def _grr(**overrides: object) -> dict:
    published = ask_calculation(
        "CALC-KPI-GRR",
        inputs={"opening_revenue": 100, "contraction": 10, "churn": 5},
        sources=["Accounts.pdf"],
    )
    published.update(overrides)
    return published


def test_must_fail_cases_fail_their_gate() -> None:
    cases = [
        (
            "run_complete",
            {"result": {"fact_store": {}, "numbers": {"revenue": "fact-9"}, "counts": {}}},
        ),
        (
            "analysis_valid",
            {"calculations": [_grr(value=0.5)]},
        ),
        (
            "analysis_valid",
            {
                "calculations": [
                    ask_calculation(
                        "CALC-KPI-GRR",
                        inputs={"opening_revenue": 100, "contraction": 0, "churn": -10},
                        sources=["Accounts.pdf"],
                    )
                ]
            },
        ),
        (
            "analysis_valid",
            {
                "claims_ledger": {
                    "claims": [{
                        "status": "known",
                        "source_wording": _PASSAGE,
                        "wording_match": False,
                        "claim_as_stated": "Revenue was 99.",
                    }]
                }
            },
        ),
        ("output_publishable", {"verdict": "PASS", "sources": ["data room"]}),
        ("output_publishable", {"quality_verdict": "CLOSED"}),
        ("output_publishable", {"reliance_verdict": "READY"}),
        (
            "output_publishable",
            {"blocks": [{"text": "Revenue was 8.", "citations": [{"text": "[1]"}]}]},
        ),
        (
            "output_publishable",
            {
                "sources_index": [_SOURCE],
                "blocks": [{"text": _PASSAGE, "citations": [{"source_id": "src-accounts", "page": 9, "passage": _PASSAGE}]}],
            },
        ),
    ]
    for gate, payload in cases:
        report = verify(payload)
        assert report[gate] is False, gate
        assert report["errors"]


def test_honest_gaps_pass() -> None:
    gaps = [
        {"claims_ledger": {"claims": [{"status": "unknown", "claim_as_stated": "Churn is not in the data room.", "wording_match": False, "source_wording": "Churn is not in the data room."}]}},
        {"claims_ledger": {"claims": [{"status": "management_claim", "claim_as_stated": "Management says churn is low.", "wording_match": False}]}},
        {"gaps": [{"topic": "churn", "reason": "not in the data room"}]},
    ]
    for payload in gaps:
        report = verify(payload)
        assert report["run_complete"] is True
        assert report["analysis_valid"] is True
        assert report["output_publishable"] is True
        assert report["errors"] == []


def test_reordering_sources_keeps_the_citation() -> None:
    other = {"source_id": "src-cim", "page": 2, "text": "A later draft says 9.", "filename": "Overview.pdf"}
    block = {
        "block_id": permanent_id("blk", "revenue_quality", _PASSAGE),
        "text": _PASSAGE,
        "citations": [{"source_id": "src-accounts", "page": 4, "passage": _PASSAGE}],
    }
    first = number_citations([block], [_SOURCE, other])
    second = number_citations([block], [other, _SOURCE])
    assert first[0]["citation_id"] == second[0]["citation_id"]
    assert first[0]["passage"] == second[0]["passage"] == _PASSAGE
    assert first[0]["locator"] == "page:4"
    assert "src-accounts" in first[0]["citation_id"] or first[0]["source_id"] == "src-accounts"


def test_checked_output_publishes_and_an_unproven_verdict_does_not() -> None:
    published = prepare_completion(
        "revenue_quality",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "calculations": [_grr()],
            "sources_index": [_SOURCE],
            "blocks": [{"text": _PASSAGE, "citations": [{"source_id": "src-accounts", "page": 4, "passage": _PASSAGE}]}],
            "claims": [{
                "status": "known",
                "problem": False,
                "claim_as_stated": _PASSAGE,
                "source_wording": _PASSAGE,
                "facts": ["fact-1"],
            }],
        },
    )
    assert published["status"] == "completed"
    assert published["verification"] == {
        "run_complete": True,
        "analysis_valid": True,
        "output_publishable": True,
    }
    assert published["blocks"][0]["block_id"].startswith("blk-")
    assert published["claims_ledger"]["claims"][0]["claim_id"].startswith("claim-")
    assert published["citations"][0]["number"] == 1
    assert published["citations"][0]["locator"] == "page:4"

    pointer = prepare_completion(
        "revenue_quality",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "blocks": [{"text": _PASSAGE, "citations": [{"source_index": 0, "text": "[1]"}]}],
        },
    )
    assert pointer["status"] == "needs_repair"
    assert pointer["verification"]["output_publishable"] is False
    assert "page" in pointer["error"] or "slide" in pointer["error"] or "cell" in pointer["error"]
