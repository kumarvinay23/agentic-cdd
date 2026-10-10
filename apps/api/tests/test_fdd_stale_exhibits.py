"""Stale exhibit / unit / source-gap regressions from the figure-integrity review."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CellStatus,
    EightLabels,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FactTableDoc,
    FddFact,
    FigureType,
)
from agetic_cdd_api.services_databook_header import period_length_from_header_cell
from agetic_cdd_api.services_fdd_assemble import assemble_report_spec
from agetic_cdd_api.services_fdd_commentary import _source_gap_limitations, draft_section
from agetic_cdd_api.services_fdd_models import (
    BS_EXHIBIT_ID,
    CASH_CONV_EXHIBIT_ID,
    MARGIN_EXHIBIT_ID,
    NWC_EXHIBIT_ID,
    TRADING_EXHIBIT_ID,
    apply_model_exhibits,
    build_phase5b_exhibits,
    build_trading_exhibit,
    _Line,
)
from agetic_cdd_api.services_fdd_render import _exhibit_body, ensure_phase0_run
from agetic_cdd_api.services_fdd_store import save_fact_table
from agetic_cdd_api.services_fdd_tokens import display_unit_for_cell


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def test_display_unit_never_doubles() -> None:
    cell = ExhibitCell(
        cell_id="revenue_fy2025",
        exhibit_id="ex_m1_trading",
        label="Revenue",
        value=13.28,
        currency="USD",
        scale="M",
        unit="M",
        fact_id="x",
    )
    assert display_unit_for_cell(cell) == "USD M"
    pct = cell.model_copy(update={"scale": "%", "unit": "%", "currency": "USD", "value": 29.75})
    assert display_unit_for_cell(pct) == "%"
    pp = cell.model_copy(update={"scale": "pp", "unit": "pp", "currency": None, "value": -1.91})
    assert display_unit_for_cell(pp) == "pp"


def test_exhibit_body_units_not_doubled() -> None:
    ex = Exhibit(
        exhibit_id="ex_m2_margin",
        title="Margin",
        cells=[
            ExhibitCell(
                cell_id="gross_margin_delta_pp_fy2025",
                exhibit_id="ex_m2_margin",
                label="Gross margin Δpp",
                value=-1.91,
                currency=None,
                scale="pp",
                unit="pp",
                fiscal_year=2025,
                metric_key="gross_margin_delta_pp",
                fact_id="x",
            )
        ],
    )
    body, _ = _exhibit_body(ex)
    assert "pp pp" not in body
    assert "USD pp" not in body
    assert "pp" in body


def test_rebuild_clears_stale_bs_nwc_cash_cells(deal_root: Path) -> None:
    slug = "stale-ex"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="StaleCo", prefer_current_release=True
    )
    # Plant stale wrong cells on model exhibits
    stale = [
        ExhibitCell(
            cell_id="ebitda_margin_fy2025",
            exhibit_id=BS_EXHIBIT_ID,
            label="EBITDA margin mislabelled",
            value=0.04,
            currency="USD",
            scale="M",
            fiscal_year=closed,
            metric_key="ebitda_margin",
            fact_id="stale:em",
            model_id="M8",
        ),
        ExhibitCell(
            cell_id="nwc_fy2025",
            exhibit_id=NWC_EXHIBIT_ID,
            label="NWC",
            value=0.68,
            currency="USD",
            scale="M",
            fiscal_year=closed,
            metric_key="nwc",
            fact_id="stale:nwc",
            model_id="M5",
        ),
        ExhibitCell(
            cell_id="ebitda_fy2025",
            exhibit_id=CASH_CONV_EXHIBIT_ID,
            label="EBITDA only",
            value=0.57,
            currency="USD",
            scale="M",
            fiscal_year=closed,
            metric_key="ebitda",
            fact_id="stale:eb",
            model_id="M7",
        ),
    ]
    store = store.model_copy(
        update={
            "exhibits": [
                *[ex for ex in store.exhibits if ex.exhibit_id not in {
                    BS_EXHIBIT_ID, NWC_EXHIBIT_ID, CASH_CONV_EXHIBIT_ID
                }],
                Exhibit(
                    exhibit_id=BS_EXHIBIT_ID,
                    title="BS",
                    section_id="SEC-F",
                    cells=[stale[0]],
                    footnotes=["gm_walk:old:-0.02pp"],
                ),
                Exhibit(
                    exhibit_id=NWC_EXHIBIT_ID,
                    title="NWC",
                    section_id="SEC-G",
                    cells=[stale[1]],
                ),
                Exhibit(
                    exhibit_id=CASH_CONV_EXHIBIT_ID,
                    title="Cash",
                    section_id="SEC-I",
                    cells=[stale[2]],
                ),
            ]
        }
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="f:rev",
                    metric_key="revenue",
                    fiscal_year=closed,
                    value=13.28,
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                    labels=EightLabels(statement="IS", line="Revenue"),
                    currency="USD",
                    scale="M",
                ),
                FddFact(
                    fact_id="f:eb",
                    metric_key="ebitda",
                    fiscal_year=closed,
                    value=0.56,
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                    labels=EightLabels(statement="IS", line="EBITDA"),
                    currency="USD",
                    scale="M",
                    sources=["investor workbook"],
                ),
            ],
        )
    )
    store2, _ = build_phase5b_exhibits(slug, manifest.run_id, store=store, persist=True)
    by = {ex.exhibit_id: ex for ex in store2.exhibits}
    # Empty model exhibits are omitted entirely (no stale cells, no "figures pending").
    assert BS_EXHIBIT_ID not in by
    assert NWC_EXHIBIT_ID not in by
    assert CASH_CONV_EXHIBIT_ID not in by
    spec = assemble_report_spec(
        run_id=manifest.run_id,
        deal_slug=slug,
        store=store2,
        company="StaleCo",
    )
    appendix_ids = [
        n.exhibit_id for n in spec.nodes if n.exhibit_id in {
            BS_EXHIBIT_ID, NWC_EXHIBIT_ID, CASH_CONV_EXHIBIT_ID
        }
    ]
    assert appendix_ids == []
    # Cover and presentation standards share the same live-exhibit count.
    cover = next(n for n in spec.nodes if n.node_id == "sec_cover")
    standards = next(n for n in spec.nodes if n.node_id == "msg_standards")
    import re

    cover_n = re.search(r"Exhibits:\s*(\d+)", cover.body or "")
    std_n = re.search(r"Exhibits:\s*(\d+)", standards.body or "")
    assert cover_n and std_n
    assert cover_n.group(1) == std_n.group(1)


def test_prefer_workbook_ebitda_over_ledger() -> None:
    closed = date.today().year - 1
    cells, _ = build_trading_exhibit(
        [
            _Line(
                metric_key="ebitda",
                fiscal_year=closed,
                value=0.572,
                fact_id="qbo",
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
                sources=["qbo ledger"],
            ),
            _Line(
                metric_key="ebitda",
                fiscal_year=closed,
                value=0.565,
                fact_id="wb",
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
                sources=["investor workbook"],
            ),
            _Line(
                metric_key="revenue",
                fiscal_year=closed,
                value=13.28,
                fact_id="r",
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
                sources=["investor workbook"],
            ),
        ],
        years=[closed],
    )
    eb = next(c for c in cells if c.metric_key == "ebitda")
    assert eb.value == pytest.approx(0.565)


def test_yoy_from_loss_not_emitted_after_replace() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    cells, notes = build_trading_exhibit(
        [
            _Line(
                metric_key="ebitda",
                fiscal_year=prior,
                value=-0.74,
                fact_id="a",
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
            ),
            _Line(
                metric_key="ebitda",
                fiscal_year=closed,
                value=1.11,
                fact_id="b",
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
            ),
            _Line(
                metric_key="revenue",
                fiscal_year=prior,
                value=7.53,
                fact_id="c",
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
            ),
            _Line(
                metric_key="revenue",
                fiscal_year=closed,
                value=11.74,
                fact_id="d",
                currency="USD",
                scale="M",
                status=CellStatus.PROVEN,
            ),
        ],
        years=[closed, prior],
    )
    assert not any(c.metric_key == "ebitda_yoy" for c in cells)
    assert any("prior_loss" in n for n in notes)
    # Full replace drops any prior yoy cell
    store = ExhibitStoreDoc(
        run_id="r",
        deal_slug="d",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id=TRADING_EXHIBIT_ID,
                title="old",
                cells=[
                    ExhibitCell(
                        cell_id=f"ebitda_yoy_fy{closed}",
                        exhibit_id=TRADING_EXHIBIT_ID,
                        label="stale yoy",
                        value=249.87,
                        metric_key="ebitda_yoy",
                        fiscal_year=closed,
                        fact_id="stale",
                        model_id="M1",
                    )
                ],
            )
        ],
    )
    store2 = apply_model_exhibits(
        store,
        trading_cells=cells,
        margin_cells=[],
        cash_cells=[],
        bs_cells=[],
        nwc_cells=[],
        net_debt_cells=[],
        notes_by_exhibit={TRADING_EXHIBIT_ID: notes},
    )
    trading = next(ex for ex in store2.exhibits if ex.exhibit_id == TRADING_EXHIBIT_ID)
    assert not any(c.metric_key == "ebitda_yoy" for c in trading.cells)


def test_dec_header_maps_to_fy() -> None:
    assert period_length_from_header_cell("Dec 2025") == "FY"
    assert period_length_from_header_cell("December 31, 2025") == "FY"
    assert period_length_from_header_cell("Nov 2025") == "UNKNOWN"
    assert period_length_from_header_cell("2025-12-31 00:00:00") == "FY"
    assert period_length_from_header_cell("2025-01-31 00:00:00") == "UNKNOWN"


def test_source_gap_limitation_text(deal_root: Path) -> None:
    slug = "gap-lim"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, _, _ = ensure_phase0_run(slug, prefer_current_release=True)
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="f",
                    metric_key="revenue",
                    fiscal_year=closed,
                    value=13.282,
                    status=CellStatus.DOUBTFUL,
                    release_status=CellStatus.DOUBTFUL,
                    labels=EightLabels(statement="IS", line="Revenue", source="workbook"),
                    sources=["investor workbook"],
                    alternatives=[
                        {
                            "value": 13.412,
                            "sources": ["qbo ledger"],
                            "chosen": False,
                        }
                    ],
                )
            ],
        )
    )
    pointer = _source_gap_limitations(slug, manifest.run_id, section_id="SEC-B")
    assert len(pointer) == 1
    assert "sec-k" in pointer[0].text.lower()
    lims = _source_gap_limitations(slug, manifest.run_id, section_id="SEC-K")
    assert lims
    assert "13.412" in lims[0].text
    assert "13.282" in lims[0].text or "13.280" in lims[0].text
    assert "gap" in lims[0].text.lower()
