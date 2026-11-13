"""FDD Phase 5b — M2 revenue / margin walk workbook."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus, EightLabels, FactTableDoc, FddFact
from agetic_cdd_api.services_fdd_commentary import (
    MARGIN_EXHIBIT_ID,
    build_commentary,
    draft_section,
)
from agetic_cdd_api.services_fdd_models import (
    _Line,
    build_margin_exhibit,
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


def test_margin_walk_levels_and_delta_pp() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    lines = [
        _line("revenue", prior, 80.0),
        _line("revenue", closed, 100.0),
        _line("gross_profit", prior, 28.0),  # 35%
        _line("gross_profit", closed, 40.0),  # 40%
        _line("ebitda", prior, 10.0),  # 12.5%
        _line("ebitda", closed, 12.0),  # 12%
    ]
    cells, notes = build_margin_exhibit(lines, years=[closed, prior])
    by = {(c.metric_key, c.fiscal_year): c for c in cells}

    assert by[("gross_margin", closed)].value == pytest.approx(40.0)
    assert by[("gross_margin", prior)].value == pytest.approx(35.0)
    assert by[("gross_margin_delta_pp", closed)].value == pytest.approx(5.0)
    assert by[("ebitda_margin_delta_pp", closed)].value == pytest.approx(-0.5)
    assert by[("revenue_yoy", closed)].value == pytest.approx(25.0)
    assert by[("cogs", closed)].value == pytest.approx(60.0)  # 100 − 40
    assert any(n.startswith("gm_walk:") for n in notes)
    assert all(c.model_id == "M2" for c in cells)
    assert all(c.exhibit_id == MARGIN_EXHIBIT_ID for c in cells)


def test_margin_derives_gp_from_cogs() -> None:
    closed = date.today().year - 1
    cells, _ = build_margin_exhibit(
        [
            _line("revenue", closed, 100.0),
            _line("cogs", closed, 55.0),
        ],
        years=[closed],
    )
    by = {c.metric_key: c for c in cells}
    assert by["gross_profit"].value == pytest.approx(45.0)
    assert by["gross_margin"].value == pytest.approx(45.0)


def test_margin_prefers_levels_over_mismatched_reported_pct() -> None:
    """Workbook revenue + pack GM% must not break G3 — compute GM/EM from levels."""
    from agetic_cdd_api.services_fdd_checks import run_model_check_packs
    from agetic_cdd_api.fdd_schemas import Exhibit, ExhibitStoreDoc, ArtefactStatus

    closed = date.today().year - 1
    cells, _ = build_margin_exhibit(
        [
            _line("revenue", closed, 11.741),  # workbook
            _line("gross_profit", closed, 3.77199441),  # pack GP
            _line("gross_margin", closed, 0.317807),  # pack GM on pack revenue
            _line("ebitda", closed, 0.5717607),
            _line("ebitda_margin", closed, 0.042539),  # pack EM on pack revenue
        ],
        years=[closed],
    )
    by = {c.metric_key: c for c in cells}
    assert by["gross_margin"].value == pytest.approx(3.77199441 / 11.741 * 100.0, rel=1e-4)
    assert by["ebitda_margin"].value == pytest.approx(0.5717607 / 11.741 * 100.0, rel=1e-4)
    assert by["gross_margin"].figure_type.value == "calculated"
    assert by["ebitda_margin"].figure_type.value == "calculated"

    store = ExhibitStoreDoc(
        deal_slug="m2-g3",
        run_id="r",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id=MARGIN_EXHIBIT_ID,
                title="Margin",
                section_id="SEC-C",
                status=ArtefactStatus.CHECKED,
                cells=cells,
            )
        ],
    )
    doc = run_model_check_packs(store)
    pack = next(p for p in doc.packs if p.exhibit_id == MARGIN_EXHIBIT_ID)
    assert pack.checks_passed, [c.message for c in pack.checks if not c.passed]


def test_ensure_m2_unblocks_sec_c(deal_root: Path) -> None:
    slug = "m2-margin"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    prior = closed - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="MarginCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("revenue", prior, 80.0),
                _fact("revenue", closed, 100.0),
                _fact("gross_profit", prior, 28.0),
                _fact("gross_profit", closed, 40.0),
                _fact("ebitda", prior, 10.0),
                _fact("ebitda", closed, 12.0),
            ],
        )
    )
    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="MarginCo", build_qoe=True
    )
    assert summary.get("models", {}).get("sections", {}).get("SEC-C") is True
    assert any(e.exhibit_id == MARGIN_EXHIBIT_ID for e in store2.exhibits)

    draft = draft_section(
        "SEC-C",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="MarginCo",
    )
    assert draft.held_back is False, draft.held_back_reason
    assert draft.cell_refs
    assert MARGIN_EXHIBIT_ID in draft.exhibit_ids

    doc = build_commentary(
        slug, manifest.run_id, company="MarginCo", update_report_spec=True
    )
    assert "SEC-C" not in (doc.held_back_sections or [])


def test_margin_gm_series_locks_to_one_source_when_workbook_gp_incomplete() -> None:
    """Do not mix workbook FY2025 GM with pack FY2024 GM — lock series to pack."""
    closed = date.today().year - 1
    prior = closed - 1
    pack = "Compost Crew Monthly Financials 23YTD26.xlsx"
    workbook = "CC_Investor_Workbook_EXTERNAL.xlsx"

    def _sourced(mk: str, year: int, value: float, src: str) -> _Line:
        return _Line(
            metric_key=mk,
            fiscal_year=year,
            value=value,
            fact_id=f"{mk}:{year}:{src[:3]}",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
            sources=[src],
        )

    cells, notes = build_margin_exhibit(
        [
            _sourced("revenue", prior, 11.741, workbook),
            _sourced("revenue", closed, 13.282, workbook),
            _sourced("gross_profit", closed, 3.952, workbook),
            _sourced("gross_profit", prior, 3.772, pack),
            _sourced("cogs", prior, 8.097, pack),
            _sourced("cogs", closed, 9.329, pack),
            _sourced("gross_margin", prior, 31.7807, pack),
            _sourced("gross_margin", closed, 30.4388, pack),
            _sourced("ebitda", prior, 1.115, workbook),
            _sourced("ebitda", closed, 0.572, pack),
        ],
        years=[closed, prior],
    )
    by = {(c.metric_key, c.fiscal_year): c for c in cells}
    assert "gm_series_locked_to_pack" in notes
    assert by[("gross_margin", closed)].value == pytest.approx(30.44, abs=0.05)
    assert by[("gross_margin", prior)].value == pytest.approx(31.78, abs=0.05)
    assert "pack" in (by[("gross_margin", closed)].basis_label or "").lower()
    assert "pack" in (by[("gross_margin", prior)].basis_label or "").lower()
    assert by[("gross_margin_delta_pp", closed)].value == pytest.approx(-1.35, abs=0.05)


def test_prefer_metric_ref_exact_and_first_exhibit_rank() -> None:
    """ES must cite M2 GM%, not reported IS % or revenue_yoy for revenue."""
    from agetic_cdd_api.fdd_schemas import (
        ArtefactStatus,
        Exhibit,
        ExhibitCell,
        ExhibitStoreDoc,
        FigureType,
    )
    from agetic_cdd_api.services_fdd_commentary import (
        TRADING_EXHIBIT_ID,
        _prefer_metric_ref,
    )

    closed = date.today().year - 1

    def _cell(
        eid: str,
        mk: str,
        value: float,
        *,
        figure_type: FigureType = FigureType.REPORTED,
    ) -> ExhibitCell:
        return ExhibitCell(
            exhibit_id=eid,
            cell_id=f"{mk}_fy{closed}",
            fact_id=f"f:{eid}:{mk}:{closed}",
            metric_key=mk,
            fiscal_year=closed,
            value=value,
            figure_type=figure_type,
            status=CellStatus.PROVEN,
            label=mk,
        )

    store = ExhibitStoreDoc(
        deal_slug="pref",
        run_id="r",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id="ex_db_is",
                title="IS",
                section_id="SEC-B",
                status=ArtefactStatus.CHECKED,
                cells=[_cell("ex_db_is", "gross_margin", 30.44)],
            ),
            Exhibit(
                exhibit_id=MARGIN_EXHIBIT_ID,
                title="M2",
                section_id="SEC-C",
                status=ArtefactStatus.CHECKED,
                cells=[
                    _cell(
                        MARGIN_EXHIBIT_ID,
                        "gross_margin",
                        29.75,
                        figure_type=FigureType.CALCULATED,
                    ),
                    _cell(
                        MARGIN_EXHIBIT_ID,
                        "revenue",
                        13.28,
                        figure_type=FigureType.CALCULATED,
                    ),
                    _cell(
                        MARGIN_EXHIBIT_ID,
                        "revenue_yoy",
                        13.12,
                        figure_type=FigureType.CALCULATED,
                    ),
                ],
            ),
            Exhibit(
                exhibit_id=TRADING_EXHIBIT_ID,
                title="M1",
                section_id="SEC-B",
                status=ArtefactStatus.CHECKED,
                cells=[
                    _cell(
                        TRADING_EXHIBIT_ID,
                        "revenue",
                        13.28,
                        figure_type=FigureType.CALCULATED,
                    )
                ],
            ),
        ],
    )
    # Callers append full exhibit_ids after the preferred list — ranks must keep
    # the first occurrence so M2 stays ahead of ex_db_is.
    all_ids = [e.exhibit_id for e in store.exhibits]
    prefer_ids = [MARGIN_EXHIBIT_ID, TRADING_EXHIBIT_ID, "ex_db_is", *all_ids]
    assert _prefer_metric_ref(
        store, prefer_ids, "gross_margin", historical_only=True
    ) == f"{MARGIN_EXHIBIT_ID}.gross_margin_fy{closed}"
    assert _prefer_metric_ref(
        store, prefer_ids, "revenue", historical_only=True
    ) == f"{MARGIN_EXHIBIT_ID}.revenue_fy{closed}"
    assert "revenue_yoy" not in (
        _prefer_metric_ref(store, prefer_ids, "revenue", historical_only=True) or ""
    )
