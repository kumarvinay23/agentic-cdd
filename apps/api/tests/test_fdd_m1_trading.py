"""FDD Phase 5b — M1 historical trading workbook."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus, FactTableDoc, EightLabels, FddFact
from agetic_cdd_api.services_fdd_commentary import (
    TRADING_EXHIBIT_ID,
    build_commentary,
    draft_section,
)
from agetic_cdd_api.services_fdd_models import (
    _Line,
    build_trading_exhibit,
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


def test_trading_yoy_and_margin_calcs() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    lines = [
        _line("revenue", prior, 80.0),
        _line("revenue", closed, 100.0),
        _line("ebitda", prior, 10.0),
        _line("ebitda", closed, 12.0),
        _line("gross_profit", closed, 40.0),
    ]
    cells, notes = build_trading_exhibit(lines, years=[closed, prior])
    by = {(c.metric_key, c.fiscal_year): c for c in cells}

    assert by[("revenue", closed)].value == pytest.approx(100.0)
    assert by[("ebitda", closed)].value == pytest.approx(12.0)
    # YoY revenue = (100-80)/80 * 100 = 25%
    assert by[("revenue_yoy", closed)].value == pytest.approx(25.0)
    assert by[("ebitda_yoy", closed)].value == pytest.approx(20.0)
    # Gross margin = 40/100 * 100 = 40%
    assert by[("gross_margin", closed)].value == pytest.approx(40.0)
    # EBITDA margin = 12/100 * 100 = 12%
    assert by[("ebitda_margin", closed)].value == pytest.approx(12.0)
    assert any(n.startswith("m1_years:") for n in notes)
    assert all(c.model_id == "M1" for c in cells)
    assert all(c.exhibit_id == TRADING_EXHIBIT_ID for c in cells)


def test_trading_skips_open_year_when_closed_exists() -> None:
    this = date.today().year
    closed = this - 1
    lines = [
        _line("revenue", this, 999.0),
        _line("revenue", closed, 100.0),
        _line("ebitda", closed, 12.0),
    ]
    cells, _ = build_trading_exhibit(lines)
    years = {c.fiscal_year for c in cells}
    assert this not in years
    assert closed in years


def test_ensure_m1_unblocks_sec_b(deal_root: Path) -> None:
    slug = "m1-trading"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    prior = closed - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="TradeCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("revenue", prior, 80.0),
                _fact("revenue", closed, 100.0),
                _fact("ebitda", prior, 10.0),
                _fact("ebitda", closed, 12.0),
                _fact("gross_profit", closed, 40.0),
            ],
        )
    )
    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="TradeCo", build_qoe=True
    )
    assert summary.get("models", {}).get("sections", {}).get("SEC-B") is True
    assert any(e.exhibit_id == TRADING_EXHIBIT_ID for e in store2.exhibits)

    draft = draft_section(
        "SEC-B",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="TradeCo",
    )
    assert draft.held_back is False, draft.held_back_reason
    assert draft.cell_refs
    assert TRADING_EXHIBIT_ID in draft.exhibit_ids
    body = draft.body or ""
    assert "Historical trading" in body or "revenue" in body.lower()

    doc = build_commentary(slug, manifest.run_id, company="TradeCo", update_report_spec=True)
    assert "SEC-B" not in (doc.held_back_sections or [])
