"""The same facts with different claim statuses reach different conclusions."""

from agetic_cdd_api.agent_module_registry import prepare_completion
from agetic_cdd_api.services_claims import (
    basis_of,
    conclude,
    deal_separation,
    history_figure,
    like_with_like,
    matches_source,
    move,
    select_by_authority,
    trend,
    wording_rate,
)

_FACTS = {"revenue_latest": 8, "revenue_prior": 10, "revenue_peak": 12}
_DEALS = ("north", "harbour", "inland")
_SOURCE = "Revenue was 8 in the latest actual year, 10 in the prior year and peaked at 12."


def test_paired_statuses_on_every_deal() -> None:
    for _deal in _DEALS:
        assert conclude("unknown", problem=True) == {"conclusion": "held", "proves_problem": False}
        assert conclude("management_claim", problem=True)["proves_problem"] is False
        assert conclude("known", problem=True) == {"conclusion": "fact", "proves_problem": True}
        assert conclude("tested", problem=True)["conclusion"] == "supported"
        assert conclude("failed", problem=True)["conclusion"] == "rejected"
        assert move("unknown", "test_fail") == "unknown"
        assert move("management_claim", "test_pass") == "tested"
        assert move("tested", "adopt") == "known"
        assert move("known", "test_fail") == "failed"
        assert _FACTS["revenue_latest"] < _FACTS["revenue_prior"]


def test_basis_authority_and_like_with_like() -> None:
    assert basis_of("management forecast for next year") == "forecast"
    assert basis_of("audited revenue") == "actual"
    try:
        history_figure({"basis": "plan", "value": 20})
    except ValueError as exc:
        assert "actual" in str(exc)
    else:
        raise AssertionError("a plan was accepted as history")
    assert history_figure({"basis": "actual", "value": 8})["basis"] == "actual"
    assert trend(8, 10, 12) == {"versus_prior": "down", "versus_peak": "below_peak"}

    chosen, conflicts = select_by_authority(
        "FINANCIAL_ACTUAL",
        [
            {"doc_type": "CIM", "value": 9},
            {"doc_type": "FIN_AUDITED_FS", "value": 8},
        ],
    )
    assert chosen["value"] == 8
    assert conflicts[0]["value"] == 9
    assert like_with_like({"population": "commercial", "period": "FY2025"}, {"population": "residential", "period": "FY2025"})
    assert like_with_like({"population": "commercial", "period": "FY2025"}, {"population": "commercial", "period": "FY2025"}) is None
    assert deal_separation({"subject": "target_acquisition", "as_deal": True})


def test_claim_wording_matches_the_source() -> None:
    pairs = [(f"Revenue was {_FACTS['revenue_latest']} in the latest actual year.", _SOURCE) for _ in range(49)]
    pairs.append(("Revenue was 99 in the latest actual year.", _SOURCE))
    assert wording_rate(pairs) >= 0.98
    assert matches_source(pairs[0][0], pairs[0][1]) is True
    assert matches_source(pairs[-1][0], pairs[-1][1]) is False


def test_unknown_cannot_prove_a_problem_and_a_plan_is_not_history() -> None:
    blocked = prepare_completion(
        "historical_performance",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "claims": [{"status": "unknown", "proves_problem": True, "claim_as_stated": "Revenue fell.", "source_wording": "Revenue fell."}],
        },
    )
    assert blocked["status"] == "needs_repair"
    assert "unknown" in blocked["error"]

    history = prepare_completion(
        "historical_performance",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "claims": [{"status": "known", "use": "history", "basis": "forecast", "claim_as_stated": "Revenue forecast is 20.", "source_wording": "Revenue forecast is 20."}],
        },
    )
    assert history["status"] == "needs_repair"
    assert "actual" in history["error"]

    published = prepare_completion(
        "revenue_quality",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "claims": [{
                "status": "known",
                "problem": True,
                "claim_as_stated": "Revenue was 8 in the latest actual year.",
                "source_wording": _SOURCE,
                "facts": ["fact-1"],
                "sources": [
                    {"doc_type": "CIM", "value": 9},
                    {"doc_type": "FIN_AUDITED_FS", "value": 8},
                ],
                "family": "FINANCIAL_ACTUAL",
            }],
        },
    )
    assert published["status"] == "completed"
    row = published["claims_ledger"]["claims"][0]
    assert published["claims_ledger"]["schedule"] == "GOV-04"
    assert row["status"] == "known"
    assert row["result"] == "confirmed"
    assert row["wording_match"] is True
    assert row["selected"]["value"] == 8
    assert row["conflicts"]
