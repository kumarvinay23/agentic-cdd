"""Slice E: reviewer decisions write ontology fact status, and CDD YoY cites the winner."""

from agetic_cdd_api.services_databook_hitl import (
    accept_conflict,
    concept_for_metric,
    drop_fact,
    remap_fact,
    vouch_fact,
    yoy_citations,
)
from agetic_cdd_api.services_fact_repository import get_fact, save_fact
from agetic_cdd_api.services_mapper import mappings_for


_DEAL = "slice-e-hitl"


def test_accept_conflict_selects_the_fact_and_the_yoy_page_cites_it() -> None:
    _clear()
    save_fact(_fact("fact-early", 10, "2024-12-31", status="SELECTED"))
    save_fact(_fact("fact-late-a", 12, "2025-12-31", status="SELECTED"))
    save_fact(_fact("fact-late-b", 15, "2025-12-31", status="CANDIDATE"))

    result = accept_conflict(
        _DEAL,
        fact_id="fact-late-b",
        metric_key="revenue",
        fiscal_year=2025,
        value=15,
        reason="audited total",
        actor="reviewer@example.com",
    )
    assert result is not None
    assert get_fact("fact-late-b")["status"] == "SELECTED"
    assert get_fact("fact-late-a")["status"] == "COMPARATIVE"
    assert get_fact("fact-late-a")["reason_code"] == "LOWER_AUTHORITY"
    assert get_fact("fact-early")["status"] == "SELECTED"

    rows = yoy_citations(_DEAL)
    assert rows
    assert rows[-1]["later_id"] == "fact-late-b"
    assert rows[-1]["later_amount"] == 15
    assert rows[-1]["earlier_id"] == "fact-early"


def test_drop_remap_and_vouch_write_reviewer_status() -> None:
    _clear()
    save_fact(_fact("fact-drop", 9, "2025-12-31", status="SELECTED"))
    dropped = drop_fact(_DEAL, "fact-drop", reason="not a statement line", actor="reviewer@example.com")
    assert dropped is not None
    assert get_fact("fact-drop")["status"] == "REJECTED"
    assert get_fact("fact-drop")["reason_code"] == "USER_EXCLUDED"

    save_fact(_fact("fact-map", 8, "2025-12-31", status="SELECTED", concept_id="fin.pl.opex"))
    remapped = remap_fact(
        _DEAL,
        "fact-map",
        metric_key="cogs",
        reason="caption is cost of sales",
        actor="reviewer@example.com",
    )
    assert remapped is not None
    assert get_fact("fact-map")["concept_id"] == "fin.pl.cost_of_sales"
    assert concept_for_metric("cogs") == "fin.pl.cost_of_sales"
    decisions = mappings_for(_DEAL)["decisions"]
    assert any(row["method"] == "USER" and row["concept_id"] == "fin.pl.cost_of_sales" for row in decisions)

    save_fact(
        _fact(
            "fact-vouch",
            7,
            "2025-12-31",
            status="CANDIDATE",
            mapping={"currency_source": "assumed"},
        )
    )
    vouched = vouch_fact(_DEAL, "fact-vouch", reason="inherited reporting currency", actor="reviewer@example.com")
    assert vouched is not None
    assert get_fact("fact-vouch")["status"] == "SELECTED"
    assert get_fact("fact-vouch")["currency"] == "USD"
    assert get_fact("fact-vouch")["mapping"]["currency_source"] == "confirmed"
    assert get_fact("fact-vouch")["reviewed_by"] == "reviewer@example.com"


def test_vouch_refuses_to_invent_a_currency() -> None:
    _clear()
    save_fact(_fact("fact-bare", 4, "2025-12-31", status="CANDIDATE"))
    from agetic_cdd_api.services_fact_repository import _MEMORY

    _MEMORY["fact-bare"]["currency"] = None
    try:
        vouch_fact(_DEAL, "fact-bare", reason="please invent", actor="reviewer@example.com")
    except ValueError as exc:
        assert "ISO" in str(exc)
    else:
        raise AssertionError("vouch invented or accepted a currency-less amount")


def _clear() -> None:
    from agetic_cdd_api.services_fact_repository import _MEMORY

    for fact_id in [key for key, row in _MEMORY.items() if row.get("deal_id") == _DEAL]:
        _MEMORY.pop(fact_id, None)


def _fact(
    fact_id: str,
    value: float,
    period_end: str,
    *,
    status: str,
    concept_id: str = "fin.pl.revenue",
    currency: str | None = "USD",
    unit_type: str = "CURRENCY",
    mapping: dict | None = None,
) -> dict:
    return {
        "fact_id": fact_id,
        "deal_id": _DEAL,
        "concept_id": concept_id,
        "value": value,
        "unit_type": unit_type,
        "currency": currency,
        "period_type": "FY",
        "period_start": period_end[:4] + "-01-01",
        "period_end": period_end,
        "months_covered": 12,
        "fiscal_year": int(period_end[:4]),
        "basis": "ACTUAL",
        "status": status,
        "evidence_tier": "B",
        "source_location_ids": [f"loc-{fact_id}"],
        "mapping": {"cell_range": "B2", **(mapping or {})},
        "dimensions": {},
    }
