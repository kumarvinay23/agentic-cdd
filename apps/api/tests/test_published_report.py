"""CDD and FDD pages come from published tabs, and the pipeline invariants hold."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from agetic_cdd_api.report_builder_base import BuildContext
from agetic_cdd_api.report_cdd_calcs import derive
from agetic_cdd_api.report_cdd_evidence import EvidenceBook
from agetic_cdd_api.report_fdd import FddDeckBuilder, FddReportBuilder
from agetic_cdd_api.services_published_pages import comparisons_from_pages, pages_for_deal, pages_from_tabs

_AGENT_REVENUE = 999


def test_a_published_schedule_is_a_page_and_an_agent_figure_is_not_chosen() -> None:
    tabs = {
        "FDD-14": [_cell("fact-rent", "lease.rent_expense_gaap", 8, "2025-03-31", "B4")],
        "FDD-06": [
            _cell("fact-rev-1", "fin.pl.revenue", 10, "2024-03-31", "B2"),
            _cell("fact-rev-2", "fin.pl.revenue", 12, "2025-03-31", "C2"),
            _cell("fact-cost", "fin.pl.cost_of_sales", 4, "2025-03-31", "C3"),
            {"fact_id": "fact-unsourced", "concept_id": "fin.pl.da", "value": 1, "cell_range": None},
        ],
        "FDD-13": [_cell("fact-debt", "debt.balance", 20, "2025-03-31", "D2")],
        "FDD-07": [],
        "GOV-05": [{"record_class": "data_gap"}],
    }
    pages = pages_from_tabs(tabs)
    by_schedule = {page["schedule_id"]: page for page in pages}
    assert set(by_schedule) == {"FDD-14", "FDD-06", "FDD-13"}
    assert by_schedule["FDD-14"]["renders"] == "rent"
    assert by_schedule["FDD-14"]["figures"][0]["fact_id"] == "fact-rent"
    assert by_schedule["FDD-06"]["renders"] == "revenue_and_costs"
    concepts = {row["concept_id"] for row in by_schedule["FDD-06"]["figures"]}
    assert concepts == {"fin.pl.revenue", "fin.pl.cost_of_sales"}
    assert by_schedule["FDD-06"]["comparison"]["recipe"] == "bridge"
    assert by_schedule["FDD-06"]["comparison"]["fact_ids"] == ["fact-rev-1", "fact-rev-2"]
    assert _AGENT_REVENUE not in {row["value"] for row in by_schedule["FDD-06"]["figures"]}
    assert by_schedule["FDD-13"]["renders"] == "debt"
    trend = pages_from_tabs({"FDD-06": [
        _cell("a", "fin.pl.revenue", 10, "2023-03-31", "A2"),
        _cell("b", "fin.pl.revenue", 11, "2024-03-31", "B2"),
        _cell("c", "fin.pl.revenue", 12, "2025-03-31", "C2"),
    ]})
    assert trend[0]["comparison"]["chart"] == "line"
    segments = pages_from_tabs({"FDD-07": [
        _cell("s1", "fin.pl.revenue", 3, "2024-03-31", "B2", {"service_line": "one"}),
        _cell("s2", "fin.pl.revenue", 4, "2025-03-31", "C2", {"service_line": "one"}),
        _cell("s3", "fin.pl.revenue", 5, "2024-03-31", "B3", {"service_line": "two"}),
        _cell("s4", "fin.pl.revenue", 6, "2025-03-31", "C3", {"service_line": "two"}),
    ]})
    assert segments[0]["comparison"]["chart"] == "grouped_bar"
    rows = comparisons_from_pages(pages)
    assert rows[0]["earlier_id"] == "fact-rev-1"
    assert rows[0]["later_id"] == "fact-rev-2"
    assert rows[0]["later_amount"] == 12


def test_report_slug_resolves_to_the_databook_deal_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _Scalar:
        def scalar(self, _stmt):
            return "6dcc1d5c99ba0d09d3e360ea"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("agetic_cdd_api.settings.settings.databook_database_url", "postgresql:///agetic_cdd_databook")
    monkeypatch.setattr("agetic_cdd_api.db.SessionLocal", lambda: _Scalar())
    monkeypatch.setattr(
        "agetic_cdd_api.services_publisher.publish",
        lambda deal_id: calls.append(deal_id) or {"tabs": {
            "FDD-06": [_cell("fact-rev", "fin.pl.revenue", 10, "2025-03-31", "B2")],
        }},
    )
    pages = pages_for_deal("baytown-travel-center-1")
    assert calls == ["6dcc1d5c99ba0d09d3e360ea"]
    assert pages[0]["schedule_id"] == "FDD-06"


def test_builders_use_published_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = pages_from_tabs({"FDD-06": [
        _cell("fact-rev-1", "fin.pl.revenue", 10, "2024-03-31", "B2"),
        _cell("fact-rev-2", "fin.pl.revenue", 12, "2025-03-31", "C2"),
        _cell("fact-cost", "fin.pl.cost_of_sales", 4, "2025-03-31", "C3"),
    ]})
    monkeypatch.setattr("agetic_cdd_api.services_published_pages.pages_for_deal", lambda deal_id: pages)
    ctx = BuildContext(deal_slug="step12-case", report_type="cdd_deck", agent_outputs={"historical_performance": {"revenue": _AGENT_REVENUE}})
    math = derive(ctx, EvidenceBook())
    assert math.yoy[0]["later_id"] == "fact-rev-2"
    assert math.yoy[0]["later_amount"] == 12
    assert _AGENT_REVENUE not in {row["later_amount"] for row in math.yoy}
    report = list(FddReportBuilder("step12-case").build_sections(ctx))
    deck = list(FddDeckBuilder("step12-case").build_sections(ctx))
    assert report[0]["renders"] == "revenue_and_costs"
    assert report[0]["figures"]["fact-rev-2"] == 12
    assert deck[0]["fact_ids"] == ["fact-rev-1", "fact-rev-2", "fact-cost"]


def test_reference_pipeline_holds_on_the_databook() -> None:
    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("databook URL is not set")
    root = Path(__file__).resolve().parents[3]
    archive = root / "DiligenceIQ_Databook_For_Engineering_v1.zip"
    if not archive.is_file():
        pytest.skip("engineering pack is not in the workspace")
    from tempfile import TemporaryDirectory

    from agetic_cdd_api.services_case_run import run_case
    from agetic_cdd_api.services_published_pages import pages_for_deal

    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        with zipfile.ZipFile(archive) as packed:
            packed.extract("DiligenceIQ_Databook_For_Engineering_v1/4_Reference_Code/uk_mgmt_synthetic.xlsx", folder)
            packed.extract("DiligenceIQ_Databook_For_Engineering_v1/4_Reference_Code/test_pipeline.py", folder)
        workbook = folder / "DiligenceIQ_Databook_For_Engineering_v1/4_Reference_Code/uk_mgmt_synthetic.xlsx"
        out = folder / "run"
        run_case(
            str(workbook),
            deal_id="step12-case",
            currency="GBP",
            fye="03-31",
            out_dir=str(out),
            database_url=url,
        )
        script = folder / "DiligenceIQ_Databook_For_Engineering_v1/4_Reference_Code/test_pipeline.py"
        result = subprocess.run([sys.executable, str(script), str(out)], capture_output=True, text=True)
    assert "ALL INVARIANTS HOLD" in result.stdout, result.stdout + result.stderr
    pages = pages_for_deal("step12-case")
    revenue = next(page for page in pages if page["renders"] == "revenue_and_costs")
    assert revenue["figures"]
    assert all(row["fact_id"] and row["cell_range"] for row in revenue["figures"])


def _cell(fact_id, concept, value, period, cell, dimensions=None):
    return {
        "fact_id": fact_id,
        "concept_id": concept,
        "value": value,
        "period_end": period,
        "cell_range": cell,
        "dimensions": dimensions or {},
    }
