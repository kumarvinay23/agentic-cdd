"""Phase 0: freeze `/view` and `/lines` contracts (no Postgres required)."""

from __future__ import annotations

import json
from pathlib import Path

from agetic_cdd_api.services_databook_view import filter_line_rows
from agetic_cdd_api.services_databook_view_models import (
    DatabookLineRow,
    DatabookLinesResponse,
    DatabookViewResponse,
)

_FIX = Path(__file__).resolve().parent / "fixtures"


def test_view_fixture_round_trips() -> None:
    payload = json.loads((_FIX / "databook_view_contract.json").read_text())
    view = DatabookViewResponse.model_validate(payload)
    assert view.status == "ready"
    assert view.reporting_currency == "USD"
    assert view.actual_through == 2025
    assert "revenue" in view.series
    assert view.series["revenue"]["2023"].value == 100.0
    assert view.dq_cells["revenue|2023"][0].kind == "conflict"
    assert view.totals.rows == 3


def test_lines_fixture_round_trips_and_types() -> None:
    payload = json.loads((_FIX / "databook_lines_contract.json").read_text())
    lines = DatabookLinesResponse.model_validate(payload)
    assert len(lines.rows) == 3
    mapped = [r for r in lines.rows if r.metric]
    unmapped = [r for r in lines.rows if r.metric == ""]
    assert len(mapped) == 2
    assert len(unmapped) == 1
    for row in lines.rows:
        assert isinstance(row.period, int)
        assert isinstance(row.scale_applied, bool)
        assert row.metric == "" or row.metric.isidentifier() or "_" in row.metric
    forecast = next(r for r in lines.rows if r.forecast is True)
    assert forecast.period == 2026
    assert forecast.kind == "percent"


def test_dq_cells_n_appears_on_line_rows() -> None:
    view = DatabookViewResponse.model_validate(
        json.loads((_FIX / "databook_view_contract.json").read_text())
    )
    lines = DatabookLinesResponse.model_validate(
        json.loads((_FIX / "databook_lines_contract.json").read_text())
    )
    line_ns = {issue.n for row in lines.rows for issue in row.dq}
    for issues in view.dq_cells.values():
        for issue in issues:
            assert issue.n in line_ns


def test_q_filter_matches_caption_or_file() -> None:
    rows = DatabookLinesResponse.model_validate(
        json.loads((_FIX / "databook_lines_contract.json").read_text())
    ).rows
    by_caption = filter_line_rows(rows, q="EBITDA")
    assert [r.line_item for r in by_caption] == ["EBITDA"]
    by_file = filter_line_rows(rows, q="notes.xlsx")
    assert len(by_file) == 1 and by_file[0].metric == ""
    assert filter_line_rows(rows, q="") == rows
    unmapped = filter_line_rows(rows, unmapped=True)
    assert len(unmapped) == 1 and unmapped[0].metric == ""
    conflicts = filter_line_rows(rows, issue="conflict")
    assert len(conflicts) == 1 and conflicts[0].metric == "revenue"


def test_line_row_rejects_wrong_scale_applied_type() -> None:
    row = DatabookLineRow.model_validate(
        {
            "key": "a|schedule|x|2023",
            "period": 2023,
            "scale_applied": True,
            "metric": "",
            "line_item": "x",
        }
    )
    assert row.scale_applied is True
