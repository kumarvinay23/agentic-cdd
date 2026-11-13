"""One result per agent: tables tie, and a count cannot contradict its detail."""

import pytest

from agetic_cdd_api.agent_module_registry import prepare_completion
from agetic_cdd_api.pipeline_catalog import all_agent_keys
from agetic_cdd_api.services_agent_result import (
    RESULT_FIELDS,
    build_agent_result,
    consistency_gate,
    note_fact,
)


def _deal(agent_key: str, **kwargs):
    result = build_agent_result(agent_key, source="ledger.xlsx", **kwargs)
    published = prepare_completion(
        agent_key,
        {"status": "completed", "sources": ["ledger.xlsx"], "result": result},
    )
    return published


def test_every_agent_uses_one_result_schema() -> None:
    for agent_key in all_agent_keys():
        result = build_agent_result(agent_key, counts={"risks": 1}, details={"risks": ["demand"]})
        assert consistency_gate(result) is None
        assert set(RESULT_FIELDS) <= set(result)
        assert all(isinstance(fact_id, str) for fact_id in result["numbers"].values())


def test_test_deals_have_no_contradictions_and_tables_tie() -> None:
    deals = [
        _deal(
            "customer_stickiness",
            counts={"cohorts": 2},
            details={"cohorts": ["2022", "2023"]},
            lines=[{"label": "Commercial", "amount": 60}, {"label": "Residential", "amount": 30}],
            total=100,
            verdict="LIMITED",
        ),
        _deal(
            "customer_segmentation",
            counts={"segments": 3},
            details={"segments": ["north", "south", "west"]},
            lines=[{"label": "Product", "amount": 40}, {"label": "Service", "amount": 60}],
            total=100,
            verdict="PASS",
        ),
        _deal(
            "market_risk",
            counts={"risks": 1},
            details={"risks": ["price"]},
            charts=[{"title": "Price", "series": [{"label": "2024", "value": 12}, {"label": "2025", "value": 11}]}],
            verdict="LIMITED",
        ),
    ]
    assert all(row["status"] == "completed" for row in deals)
    for row in deals:
        result = row["result"]
        assert consistency_gate(result) is None
        for table in result["tables"]:
            store = result["fact_store"]
            covered = sum(store[line["amount"]]["value"] for line in table["rows"])
            assert covered == store[table["total"]]["value"]
        for name, fact_id in result["counts"].items():
            assert str(result["fact_store"][fact_id]["value"]) in result["narrative"]
            assert name in result["narrative"]
    stickiness = deals[0]["result"]["tables"][0]
    assert stickiness["rows"][-1]["label"] == "Other"
    assert deals[0]["result"]["fact_store"][stickiness["rows"][-1]["amount"]]["value"] == 10.0


def test_zero_cohorts_above_cohort_figures_is_blocked() -> None:
    result = build_agent_result(
        "customer_stickiness",
        counts={"cohorts": 0},
        details={"cohorts": ["2022", "2023", "2024"]},
        verdict="0 cohorts",
        source="retention.xlsx",
    )
    published = prepare_completion(
        "customer_stickiness",
        {"status": "completed", "sources": ["retention.xlsx"], "result": result},
    )
    assert published["status"] == "needs_repair"
    assert published["status"] != "completed"
    assert "0" in published["error"]


def test_a_new_fact_must_pass_its_check_before_it_is_cited() -> None:
    with pytest.raises(ValueError):
        note_fact(
            {},
            name="grr",
            source="customer ledger",
            value=50,
            calc_id="CALC-KPI-GRR",
            inputs={"opening_revenue": 10000, "contraction": 1000, "churn": 273, "expansion": 0},
        )
    store: dict = {}
    fact_id = note_fact(
        store,
        name="grr",
        source="customer ledger",
        calc_id="CALC-KPI-GRR",
        inputs={"opening_revenue": 10000, "contraction": 1000, "churn": 273, "expansion": 0},
    )
    assert store[fact_id]["value"] == 0.8727
    assert fact_id.startswith("fact-")


def test_rows_above_the_total_do_not_publish() -> None:
    published = _deal(
        "revenue_quality",
        lines=[{"label": "Retained", "amount": 80}, {"label": "New", "amount": 40}],
        total=100,
    )
    assert published["status"] == "needs_repair"
    assert "tie" in published["error"]
