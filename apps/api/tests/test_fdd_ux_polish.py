"""FDD UX polish — G2 gate, bracket negatives, DOCX, labelled deck chart series."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    Exhibit,
    ExhibitCell,
    FigureType,
)
from agetic_cdd_api.report_fdd import _chart_series_from_exhibit, _write_fdd_docx
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_claims import acknowledge_g2, evaluate_g2
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import create_run, save_manifest
from agetic_cdd_api.services_fdd_tokens import format_fdd_number


@pytest.fixture()
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agetic_cdd_api import services_deals as deals_mod

    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_format_fdd_number_brackets_negatives() -> None:
    assert format_fdd_number(0.565) == "0.57"
    assert format_fdd_number(-12.5) == "(12.50)"
    assert format_fdd_number(-100) == "(100)"
    assert format_fdd_number(-1.2, brackets_for_negative=False) == "-1.20"


def test_g2_auto_pass_when_claims_built_and_reliable(deal_root: Path) -> None:
    slug = "g2-ok"
    m = create_run(slug)
    save_manifest(
        m.model_copy(
            update={
                "claims_built": True,
                "unreliable_modules": [],
                "g2_passed": True,
            }
        )
    )
    status = evaluate_g2(slug, m.run_id)
    assert status["passed"] is True
    assert status["auto_ok"] is True
    assert status["blockers"] == []


def test_g2_blocks_unreliable_until_acknowledge(deal_root: Path) -> None:
    slug = "g2-bad"
    m = create_run(slug)
    save_manifest(
        m.model_copy(
            update={
                "claims_built": True,
                "unreliable_modules": ["historical_performance"],
                "g2_passed": False,
            }
        )
    )
    status = evaluate_g2(slug, m.run_id)
    assert status["passed"] is False
    assert "unreliable_modules:historical_performance" in status["blockers"]

    with pytest.raises(GateBlockedError):
        acknowledge_g2(slug, m.run_id, note="", allow_unreliable=True)

    _status, _appr, manifest = acknowledge_g2(
        slug,
        m.run_id,
        note="Lead accepts agent module risk pending re-extract",
        allow_unreliable=True,
    )
    assert manifest.g2_passed is True
    assert evaluate_g2(slug, m.run_id)["passed"] is True


def _cell(
    *,
    exhibit_id: str,
    metric_key: str,
    year: int,
    value: float,
    label: str | None = None,
) -> ExhibitCell:
    return ExhibitCell(
        cell_id=f"{metric_key}_fy{year}",
        exhibit_id=exhibit_id,
        label=label or metric_key.replace("_", " ").title(),
        value=value,
        fact_id=f"f:{metric_key}:{year}",
        metric_key=metric_key,
        fiscal_year=year,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )


def test_chart_series_labelled_periods() -> None:
    ex = Exhibit(
        exhibit_id="ex_m1_trading",
        title="Trading",
        section_id="SEC-B",
        cells=[
            _cell(exhibit_id="ex_m1_trading", metric_key="revenue", year=2022, value=80.0),
            _cell(exhibit_id="ex_m1_trading", metric_key="revenue", year=2023, value=90.0),
            _cell(exhibit_id="ex_m1_trading", metric_key="revenue", year=2024, value=100.0),
        ],
    )
    built = _chart_series_from_exhibit(ex)
    assert built is not None
    cats, series, axis = built
    assert cats == ["FY22A", "FY23A", "FY24A"]
    assert series[0][0] == "Revenue"
    assert series[0][1] == [80.0, 90.0, 100.0]
    assert "USD" in axis or "M" in axis


def test_chart_no_phantom_sparse_year_zero_fill() -> None:
    """Revenue-only FY20 must not appear with 0.0 GP/EBITDA."""
    eid = "ex_db_metrics"
    ex = Exhibit(
        exhibit_id=eid,
        title="Databook metrics",
        section_id="SEC-B",
        cells=[
            _cell(exhibit_id=eid, metric_key="revenue", year=2020, value=10.417),
            _cell(exhibit_id=eid, metric_key="revenue", year=2023, value=11.0),
            _cell(exhibit_id=eid, metric_key="revenue", year=2024, value=12.0),
            _cell(exhibit_id=eid, metric_key="gross_profit", year=2023, value=1.5),
            _cell(exhibit_id=eid, metric_key="gross_profit", year=2024, value=1.6),
            _cell(exhibit_id=eid, metric_key="ebitda", year=2023, value=0.5),
            _cell(exhibit_id=eid, metric_key="ebitda", year=2024, value=0.6),
        ],
    )
    built = _chart_series_from_exhibit(ex)
    assert built is not None
    cats, series, _axis = built
    assert "FY20A" not in cats
    assert cats == ["FY23A", "FY24A"]
    assert all(0.0 not in vals for _name, vals in series)


def test_chart_omits_incomplete_outer_years() -> None:
    """YTD / stub years after the closed cutoff are not plotted as FY26E."""
    from datetime import date

    eid = "ex_m1_trading"
    closed = date.today().year - 1
    ex = Exhibit(
        exhibit_id=eid,
        title="Trading",
        section_id="SEC-B",
        cells=[
            _cell(exhibit_id=eid, metric_key="revenue", year=closed - 1, value=12.0),
            _cell(exhibit_id=eid, metric_key="revenue", year=closed, value=13.0),
            _cell(exhibit_id=eid, metric_key="revenue", year=closed + 1, value=14.0),
            _cell(exhibit_id=eid, metric_key="revenue", year=closed + 2, value=15.0),
        ],
    )
    cats, series, _axis = _chart_series_from_exhibit(ex)  # type: ignore[misc]
    assert cats == [
        f"FY{(closed - 1) % 100:02d}A",
        f"FY{closed % 100:02d}A",
    ]
    assert f"FY{(closed + 1) % 100:02d}E" not in cats
    assert series[0][1] == [12.0, 13.0]


def test_costs_chart_prefers_cogs_and_sga_not_revenue_only() -> None:
    eid = "ex_m3_costs"
    ex = Exhibit(
        exhibit_id=eid,
        title="Costs",
        section_id="SEC-D",
        cells=[
            _cell(exhibit_id=eid, metric_key="revenue", year=2024, value=100.0),
            _cell(exhibit_id=eid, metric_key="revenue", year=2025, value=110.0),
            _cell(exhibit_id=eid, metric_key="cogs", year=2024, value=60.0),
            _cell(exhibit_id=eid, metric_key="cogs", year=2025, value=65.0),
            _cell(exhibit_id=eid, metric_key="sga", year=2024, value=20.0),
            _cell(exhibit_id=eid, metric_key="sga", year=2025, value=22.0),
        ],
    )
    _cats, series, _axis = _chart_series_from_exhibit(ex)  # type: ignore[misc]
    names = [n for n, _v in series]
    assert names[0] == "Cost of sales"
    assert "SG&A" in names


def test_chart_series_rounds_float_noise_to_3dp() -> None:
    eid = "ex_m1_trading"
    ex = Exhibit(
        exhibit_id=eid,
        title="Trading",
        section_id="SEC-B",
        cells=[
            _cell(exhibit_id=eid, metric_key="revenue", year=2024, value=18.066000000000003),
            _cell(exhibit_id=eid, metric_key="revenue", year=2025, value=24.478999999999996),
        ],
    )
    _cats, series, _axis = _chart_series_from_exhibit(ex)  # type: ignore[misc]
    assert series[0][1] == [18.066, 24.479]


def test_headline_cost_of_sales_no_fy_dup() -> None:
    from agetic_cdd_api.services_fdd_commentary import _headline_figure_phrase

    cell = ExhibitCell(
        cell_id="cogs_fy2025",
        exhibit_id="ex_m3_costs",
        label="Cost of sales FY2025",
        value=9.33,
        fact_id="f",
        metric_key="cogs",
        fiscal_year=2025,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )
    phrase = _headline_figure_phrase("9.33", cell, qoe_pending=False)
    assert "FY2025 Cost of sales FY2025" not in phrase
    assert phrase.startswith("FY2025 cost of sales")


def test_headline_margin_delta_reads_as_change() -> None:
    from agetic_cdd_api.services_fdd_commentary import _headline_figure_phrase

    cell = ExhibitCell(
        cell_id="gm_delta",
        exhibit_id="ex_m2_margin",
        label="Gross margin Δpp FY2025",
        value=-1.91,
        fact_id="f",
        metric_key="gross_margin_delta_pp",
        fiscal_year=2025,
        scale="pp",
        status=CellStatus.PROVEN,
        figure_type=FigureType.CALCULATED,
    )
    phrase = _headline_figure_phrase("(1.91)", cell, qoe_pending=False)
    assert "gross margin change" in phrase
    assert "FY2025 Gross margin Δpp FY2025" not in phrase


def test_exhibit_body_strips_duplicate_fy_in_label() -> None:
    from agetic_cdd_api.services_fdd_render import _exhibit_body

    eid = "ex_m2_margin"
    ex = Exhibit(
        exhibit_id=eid,
        title="Margin",
        section_id="SEC-C",
        cells=[
            ExhibitCell(
                cell_id="cogs_fy2025",
                exhibit_id=eid,
                label="FY2025 Cost of sales",
                value=9.33,
                fact_id="f:cogs:2025",
                metric_key="cogs",
                fiscal_year=2025,
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
                figure_type=FigureType.REPORTED,
            )
        ],
    )
    body, _refs = _exhibit_body(ex)
    assert "FY2025 Cost of sales FY2025" not in body
    assert "Cost of sales (FY2025" in body


def test_docx_and_pdf_twin_written(deal_root: Path) -> None:
    from agetic_cdd_api.report_fdd import FddReportBuilder

    slug = "docx-deal"
    (deal_root / slug).mkdir(parents=True)
    ensure_phase0_run(slug, company="Acme", revenue_fy24=100.0)
    events = list(FddReportBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in events)
    out = deal_root / slug / "reports" / "fdd_report"
    assert list(out.glob("*_FDD_Report.docx"))
    assert list(out.glob("*_FDD_Report.pdf"))


def test_write_fdd_docx_smoke(tmp_path: Path) -> None:
    from agetic_cdd_api.fdd_schemas import StubRenderPage

    path = tmp_path / "out.docx"
    _write_fdd_docx(
        path=path,
        title="FDD Report — Acme",
        company="Acme",
        pages=[
            StubRenderPage(title="Cover", body="Financial Due Diligence", kind="cover"),
            StubRenderPage(
                title="Trading",
                body="• Revenue: 100\n• EBITDA: (12.50)",
                kind="section",
            ),
        ],
        figures={"ex.a": 1.0},
    )
    assert path.is_file()
    assert path.stat().st_size > 1000
