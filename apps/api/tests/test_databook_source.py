"""Slice F: ontology series skip the file summary; Close checks hold."""

from types import SimpleNamespace

import pytest

from agetic_cdd_api.services_databook_excel import import_edited_workbook
from agetic_cdd_api.services_databook_models import PromotedMetric
from agetic_cdd_api.services_databook_source import (
    no_sourced_fact_message,
    tinted_cells_resolve,
    view_for_deal,
)
from agetic_cdd_api.services_databook_view_models import (
    DatabookDqIssue,
    DatabookSeriesCell,
    DatabookViewResponse,
)
from agetic_cdd_api.services_fact_repository import get_fact, save_fact
from openpyxl import Workbook
import io


def test_ontology_series_does_not_call_the_file_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_ui_source",
        "ontology",
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("file summary")

    monkeypatch.setattr("agetic_cdd_api.services_databook.get_databook_summary", boom)
    view = view_for_deal(SimpleNamespace(id="slice-f-ontology"))
    assert view.source == "ontology"
    assert "sourced fact" in no_sourced_fact_message()


def test_dual_prefers_ontology_series(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.settings.settings.databook_ui_source", "dual")
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_source.build_databook_view",
        lambda _deal_id: DatabookViewResponse(
            series={"revenue": {"2024": DatabookSeriesCell(value=10, fact_id="fact-dual")}},
            status="ready",
            dq_cells={
                "revenue|2024": [
                    DatabookDqIssue(n=1001, kind="conflict", label="Sources disagree", detail="two values")
                ]
            },
        ),
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("file summary")

    monkeypatch.setattr("agetic_cdd_api.services_databook.get_databook_summary", boom)
    view = view_for_deal(SimpleNamespace(id="slice-f-dual"))
    assert view.series["revenue"]["2024"].fact_id == "fact-dual"
    assert tinted_cells_resolve(view)


def test_file_mode_reads_promoted_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.settings.settings.databook_ui_source", "file")
    summary = SimpleNamespace(
        promoted_preview=[
            PromotedMetric(
                metric_key="revenue",
                fiscal_year=2024,
                value=42,
                row_id="row-1",
                currency="USD",
                captions=["Revenue"],
                sources=["accounts.xlsx"],
            )
        ]
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook.get_databook_summary",
        lambda *_args, **_kwargs: summary,
    )
    view = view_for_deal(SimpleNamespace(id="slice-f-file"))
    assert view.source == "file"
    assert view.series["revenue"]["2024"].value == 42
    assert view.series["revenue"]["2024"].fact_id is None


def test_excel_import_updates_the_ontology_fact() -> None:
    deal_id = "slice-f-excel"
    save_fact(
        {
            "fact_id": "fact-slice-f",
            "deal_id": deal_id,
            "concept_id": "fin.pl.revenue",
            "value": 10,
            "unit_type": "CURRENCY",
            "currency": "USD",
            "period_type": "FY",
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "months_covered": 12,
            "fiscal_year": 2025,
            "basis": "ACTUAL",
            "status": "SELECTED",
            "evidence_tier": "B",
            "source_location_ids": ["loc-slice-f"],
            "dimensions": {},
        }
    )
    book = Workbook()
    sheet = book.active
    sheet.title = "Databook"
    sheet.append(["fact_id", "value"])
    sheet.append(["fact-slice-f", 18])
    buf = io.BytesIO()
    book.save(buf)
    result = import_edited_workbook(SimpleNamespace(id=deal_id, slug="slice-f-excel"), buf.getvalue(), actor="reviewer@example.com")
    assert result["applied"] == 1
    assert get_fact("fact-slice-f")["value"] == 18
