"""FDD content fixes — CoA operating costs, QoE single reported line, SEC-K digest."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CellStatus,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    SectionDraft,
)
from agetic_cdd_api.services_databook_map import map_caption
from agetic_cdd_api.services_fdd_commentary import (
    _enrich_key_findings_with_held,
    sync_qoe_exhibit,
)
from agetic_cdd_api.services_fdd_qoe import build_qoe_from_facts
from agetic_cdd_api.services_fdd_store import create_run, save_qoe_workbook
from agetic_cdd_api.services_fdd_tokens import format_cell_display


@pytest.fixture()
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agetic_cdd_api import services_deals as deals_mod

    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_operating_costs_maps_to_sga() -> None:
    hit = map_caption("Operating costs")
    assert hit is not None
    assert hit.metric_key == "sga"


def test_labor_related_benefits_still_maps() -> None:
    hit = map_caption("Labor & related benefits")
    assert hit is not None
    assert hit.metric_key == "labor_cost"


def test_labor_sga_line_dual_agrees() -> None:
    hit = map_caption("Labor & related benefits - SG&A")
    assert hit is not None
    assert hit.metric_key == "labor_cost"
    assert hit.dual_agree is True


def test_total_sga_typo_dual_agrees() -> None:
    hit = map_caption("Total Selling, General, & Adminsitrative")
    assert hit is not None
    assert hit.metric_key == "sga"
    assert hit.dual_agree is True


def test_bs_plug_total_not_mapped_as_equity() -> None:
    assert map_caption("Total Liabilities & Shareholders' Equity") is None
    hit = map_caption("Total Shareholders' Equity")
    assert hit is not None
    assert hit.metric_key == "total_equity"


def test_shareholders_equity_not_percent_unit() -> None:
    from agetic_cdd_api.services_databook_header import infer_caption_unit_hints

    unit, _cur, _scl = infer_caption_unit_hints("Total Shareholders' Equity")
    assert unit != "%"


def test_vehicle_loan_asset_id_not_mapped() -> None:
    assert map_caption("Vehicle Loans:501 F-250 SRW-2023 (Ford Credit)") is None
    hit = map_caption("Vehicle Loans")
    assert hit is not None
    assert hit.metric_key == "term_loan"


def test_checking_maps_to_cash() -> None:
    hit = map_caption("Checking")
    assert hit is not None
    assert hit.metric_key == "cash"


def test_qoe_empty_register_one_reported_line(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import FactTableDoc, FddFact
    from agetic_cdd_api.services_fdd_store import save_fact_table
    from agetic_cdd_api.services_fdd_exhibit import persist_store

    slug = "qoe-one"
    m = create_run(slug)
    save_fact_table(
        FactTableDoc(
            run_id=m.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="f:ebitda:2025",
                    metric_key="ebitda",
                    fiscal_year=2025,
                    value=0.572,
                    display="0.57",
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                )
            ],
        )
    )
    persist_store(
        slug,
        m.run_id,
        ExhibitStoreDoc(
            run_id=m.run_id,
            deal_slug=slug,
            updated_at="t",
            exhibits=[],
        ),
    )
    qoe = build_qoe_from_facts(slug, m.run_id, fiscal_year=2025)
    save_qoe_workbook(qoe)
    store = sync_qoe_exhibit(slug, m.run_id)
    qoe_ex = next(e for e in store.exhibits if e.exhibit_id == "ex_qoe_bridge")
    labels = [c.label for c in qoe_ex.cells]
    assert labels.count("Reported EBITDA") == 1
    assert not any("Adjusted" in (c.label or "") for c in qoe_ex.cells)


def test_enrich_sec_k_adds_held_digest() -> None:
    drafts = [
        SectionDraft(
            section_id="SEC-F",
            title="Balance sheet / NAV",
            held_back=True,
            held_back_reason="Balance sheet figures not available",
            sentences=[],
        ),
        SectionDraft(
            section_id="SEC-K",
            title="Key findings",
            held_back=False,
            sentences=[],
            body="",
        ),
    ]
    out = _enrich_key_findings_with_held(drafts)
    k = next(d for d in out if d.section_id == "SEC-K")
    assert any("Held-back analysis sections" in (s.text or "") for s in k.sentences)
    assert "Balance sheet" in (k.body or "")


def test_margin_display_keeps_unit_with_brackets() -> None:
    cell = ExhibitCell(
        cell_id="gm",
        exhibit_id="ex",
        label="Gross margin %",
        value=-1.91,
        fact_id="f",
        metric_key="gross_margin",
        scale="%",
        status=CellStatus.PROVEN,
        figure_type=FigureType.CALCULATED,
    )
    assert format_cell_display(cell) == "(1.91)%"
