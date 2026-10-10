"""FDD Phase 5b — M3 costs and people workbook."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus, EightLabels, FactTableDoc, FddFact
from agetic_cdd_api.services_fdd_commentary import (
    COSTS_EXHIBIT_ID,
    build_commentary,
    draft_section,
)
from agetic_cdd_api.services_fdd_models import (
    _Line,
    build_costs_exhibit,
    ensure_phase5b_models,
)
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import save_fact_table


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _line(metric: str, year: int, value: float) -> _Line:
    return _Line(
        metric_key=metric,
        fiscal_year=year,
        value=value,
        fact_id=f"db:{metric}:{year}",
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
    )


def _fact(metric: str, year: int, value: float) -> FddFact:
    return FddFact(
        fact_id=f"db:t:{metric}:{year}",
        metric_key=metric,
        fiscal_year=year,
        value=value,
        status=CellStatus.PROVEN,
        release_status=CellStatus.PROVEN,
        labels=EightLabels(statement="IS", line=metric.replace("_", " ").title()),
        currency="USD",
        scale="M",
    )


def test_costs_ratios_and_yoy() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    lines = [
        _line("revenue", prior, 80.0),
        _line("revenue", closed, 100.0),
        _line("cogs", prior, 48.0),  # 60%
        _line("cogs", closed, 55.0),  # 55%
        _line("sga", prior, 16.0),  # 20%
        _line("sga", closed, 18.0),  # 18%
        _line("labor_cost", closed, 30.0),  # 30%
        _line("headcount", closed, 50.0),
    ]
    cells, notes = build_costs_exhibit(lines, years=[closed, prior])
    by = {(c.metric_key, c.fiscal_year): c for c in cells}

    assert by[("cogs", closed)].value == pytest.approx(55.0)
    assert by[("sga", closed)].value == pytest.approx(18.0)
    assert by[("cogs_pct_revenue", closed)].value == pytest.approx(55.0)
    assert by[("sga_pct_revenue", closed)].value == pytest.approx(18.0)
    assert by[("labor_pct_revenue", closed)].value == pytest.approx(30.0)
    assert by[("revenue_per_head", closed)].value == pytest.approx(2.0)
    assert by[("sga_yoy", closed)].value == pytest.approx(12.5)
    assert by[("cogs_yoy", closed)].value == pytest.approx(14.5833, rel=1e-3)
    assert any(n.startswith("m3_years:") for n in notes)
    assert all(c.model_id == "M3" for c in cells)
    assert all(c.exhibit_id == COSTS_EXHIBIT_ID for c in cells)


def test_costs_derives_cogs_from_gp() -> None:
    closed = date.today().year - 1
    cells, _ = build_costs_exhibit(
        [
            _line("revenue", closed, 100.0),
            _line("gross_profit", closed, 40.0),
            _line("sga", closed, 15.0),
        ],
        years=[closed],
    )
    by = {c.metric_key: c for c in cells}
    assert by["cogs"].value == pytest.approx(60.0)
    assert by["cogs_pct_revenue"].value == pytest.approx(60.0)
    assert by["sga"].value == pytest.approx(15.0)


def test_costs_empty_without_cost_lines() -> None:
    closed = date.today().year - 1
    cells, notes = build_costs_exhibit(
        [_line("revenue", closed, 100.0)],
        years=[closed],
    )
    assert cells == []
    assert any("no_cost_lines" in n for n in notes)


def test_m8_inventory_prefers_nonzero_pack() -> None:
    from agetic_cdd_api.services_fdd_models import build_balance_sheet_exhibit

    closed = date.today().year - 1
    pack = "Compost Crew Monthly Financials 23YTD26.xlsx"
    dep = "CC - Depreciation Schedule as on 07_31_2026.xlsx"
    lines = [
        _Line(
            metric_key="inventory",
            fiscal_year=closed,
            value=0.0,
            fact_id="db:inv:0",
            currency="USD",
            scale="M",
            status=CellStatus.DRAFT,
            sources=[dep],
            label="Compost Crew supplies and inventory",
        ),
        _Line(
            metric_key="inventory",
            fiscal_year=closed,
            value=0.228,
            fact_id="db:inv:pack",
            currency="USD",
            scale="M",
            status=CellStatus.DRAFT,
            sources=[pack],
            label="Inventory",
        ),
        _Line(
            metric_key="cash",
            fiscal_year=closed,
            value=2.668,
            fact_id="db:cash",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
            sources=[pack],
        ),
    ]
    cells, _ = build_balance_sheet_exhibit(lines, year=closed)
    inv = [c for c in cells if c.metric_key == "inventory"]
    assert len(inv) == 1
    assert inv[0].value == pytest.approx(0.228)


def test_costs_ratio_uses_same_source_basis() -> None:
    """Pack COGS must divide by pack revenue, not workbook revenue."""
    closed = date.today().year - 1
    pack = "Compost Crew Monthly Financials 23YTD26.xlsx"
    workbook = "CC_Investor_Workbook_EXTERNAL.xlsx"
    lines = [
        _Line(
            metric_key="revenue",
            fiscal_year=closed,
            value=13.282,
            fact_id="db:rev:wb",
            currency="USD",
            scale="M",
            status=CellStatus.DOUBTFUL,
            sources=[workbook],
        ),
        _Line(
            metric_key="revenue",
            fiscal_year=closed,
            value=13.4115,
            fact_id="db:rev:pack",
            currency="USD",
            scale="M",
            status=CellStatus.DOUBTFUL,
            sources=[pack],
        ),
        _Line(
            metric_key="cogs",
            fiscal_year=closed,
            value=9.3292,
            fact_id="db:cogs",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
            sources=[pack],
        ),
        _Line(
            metric_key="sga",
            fiscal_year=closed,
            value=4.23,
            fact_id="db:sga",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
            sources=[pack],
        ),
        _Line(
            metric_key="labor_cost",
            fiscal_year=closed,
            value=6.24,
            fact_id="db:labor",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
            sources=[pack],
        ),
    ]
    cells, _ = build_costs_exhibit(lines, years=[closed])
    by = {c.metric_key: c for c in cells}
    assert by["revenue"].value == pytest.approx(13.4115, rel=1e-4)
    assert by["cogs_pct_revenue"].value == pytest.approx(69.56, abs=0.05)
    assert by["labor_pct_revenue"].value == pytest.approx(46.53, abs=0.1)
    assert by["sga_pct_revenue"].value == pytest.approx(31.54, abs=0.05)


def test_ensure_m3_unblocks_sec_d(deal_root: Path) -> None:
    slug = "m3-costs"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    prior = closed - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="CostCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("revenue", prior, 80.0),
                _fact("revenue", closed, 100.0),
                _fact("cogs", prior, 48.0),
                _fact("cogs", closed, 55.0),
                _fact("sga", prior, 16.0),
                _fact("sga", closed, 18.0),
            ],
        )
    )
    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="CostCo", build_qoe=True
    )
    assert summary.get("models", {}).get("sections", {}).get("SEC-D") is True
    assert any(e.exhibit_id == COSTS_EXHIBIT_ID for e in store2.exhibits)

    draft = draft_section(
        "SEC-D",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="CostCo",
    )
    assert draft.held_back is False, draft.held_back_reason
    assert draft.cell_refs
    assert COSTS_EXHIBIT_ID in draft.exhibit_ids

    doc = build_commentary(
        slug, manifest.run_id, company="CostCo", update_report_spec=True
    )
    assert "SEC-D" not in (doc.held_back_sections or [])
