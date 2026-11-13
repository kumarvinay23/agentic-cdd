"""Phase D — chapter content depth (exhibit-backed tables / QoE / deal asks)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    Finding,
    FindingSeverity,
    FindingsDoc,
    QoeBridgePeriod,
    QoeBridgeStep,
    QoeWorkbookDoc,
)
from agetic_cdd_api.services_fdd_chapters import (
    chapter_sequence,
    chapter_slide_ids,
    expected_chapter_ids,
    plan_chapter_slides,
)
from agetic_cdd_api.services_fdd_pptx import slide_chrome_inventory, write_fdd_presentation


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int | None = 2025,
    label: str | None = None,
) -> ExhibitCell:
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=label or metric_key,
        value=value,
        fact_id=f"hand:{metric_key}:{fiscal_year or 'x'}",
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )


def _ex(exhibit_id: str, title: str, cells: list[ExhibitCell]) -> Exhibit:
    return Exhibit(exhibit_id=exhibit_id, title=title, cells=cells)


def _store() -> ExhibitStoreDoc:
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug="phase-d",
        updated_at="",
        exhibits=[
            _ex(
                "ex_m1_trading",
                "Historical trading",
                [
                    _cell("ex_m1_trading", "r24", metric_key="revenue", value=11.741, fiscal_year=2024),
                    _cell("ex_m1_trading", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                    _cell("ex_m1_trading", "e24", metric_key="ebitda", value=1.115, fiscal_year=2024),
                    _cell("ex_m1_trading", "e25", metric_key="ebitda", value=0.572, fiscal_year=2025),
                    _cell("ex_m1_trading", "em25", metric_key="ebitda_margin", value=4.25, fiscal_year=2025),
                    _cell("ex_m1_trading", "gm25", metric_key="gross_margin", value=30.44, fiscal_year=2025),
                    _cell("ex_m1_trading", "ry25", metric_key="revenue_yoy", value=13.12, fiscal_year=2025),
                ],
            ),
            _ex(
                "ex_m2_margin",
                "Margin",
                [
                    _cell("ex_m2_margin", "gm24", metric_key="gross_margin", value=31.78, fiscal_year=2024),
                    _cell("ex_m2_margin", "gm25", metric_key="gross_margin", value=30.44, fiscal_year=2025),
                    _cell("ex_m2_margin", "emd", metric_key="ebitda_margin_delta_pp", value=-5.24, fiscal_year=2025),
                    _cell("ex_m2_margin", "gmd", metric_key="gross_margin_delta_pp", value=-1.34, fiscal_year=2025),
                    _cell("ex_m2_margin", "e25", metric_key="ebitda", value=0.572, fiscal_year=2025),
                    _cell("ex_m2_margin", "em25", metric_key="ebitda_margin", value=4.25, fiscal_year=2025),
                    _cell("ex_m2_margin", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                ],
            ),
            _ex(
                "ex_m3_costs",
                "Costs",
                [
                    _cell("ex_m3_costs", "sga25", metric_key="sga", value=4.23, fiscal_year=2025),
                    _cell("ex_m3_costs", "sga_y", metric_key="sga_yoy", value=29.28, fiscal_year=2025),
                    _cell("ex_m3_costs", "lab_y", metric_key="labor_yoy", value=17.61, fiscal_year=2025),
                    _cell("ex_m3_costs", "sga_p", metric_key="sga_pct_revenue", value=31.85, fiscal_year=2025),
                    _cell("ex_m3_costs", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                ],
            ),
            _ex(
                "ex_m5_nwc",
                "NWC",
                [
                    _cell("ex_m5_nwc", "ar", metric_key="accounts_receivable", value=1.22),
                    _cell("ex_m5_nwc", "inv", metric_key="inventory", value=0.23),
                    _cell("ex_m5_nwc", "ap", metric_key="accounts_payable", value=0.50),
                    _cell("ex_m5_nwc", "nwc", metric_key="nwc", value=0.95),
                ],
            ),
            _ex(
                "ex_m6_net_debt",
                "Net debt",
                [
                    _cell("ex_m6_net_debt", "cash", metric_key="cash", value=2.67),
                    _cell("ex_m6_net_debt", "gd", metric_key="gross_debt", value=2.02),
                    _cell("ex_m6_net_debt", "nd", metric_key="net_debt", value=-0.65),
                ],
            ),
            _ex(
                "ex_m7_cash",
                "Cash",
                [
                    _cell("ex_m7_cash", "ocf", metric_key="operating_cash_flow", value=0.61),
                    _cell("ex_m7_cash", "fcf", metric_key="free_cash_flow", value=0.18),
                    _cell("ex_m7_cash", "cc", metric_key="cash_conversion", value=106.78),
                    _cell("ex_m7_cash", "capex", metric_key="capex", value=0.43),
                ],
            ),
            _ex(
                "ex_m8_bs",
                "BS",
                [
                    _cell("ex_m8_bs", "eq", metric_key="total_equity", value=3.65),
                    _cell("ex_m8_bs", "cash", metric_key="cash", value=2.67),
                ],
            ),
            _ex(
                "ex_db_bs",
                "BS databook",
                [
                    _cell("ex_db_bs", "div24", metric_key="dividends", value=0.38, fiscal_year=2024, label="Dividends Payable"),
                    _cell("ex_db_bs", "div25", metric_key="dividends", value=0.37, fiscal_year=2025, label="Dividends Payable"),
                    _cell("ex_db_bs", "eq", metric_key="total_equity", value=3.65),
                ],
            ),
            _ex(
                "ex_qoe_bridge",
                "QoE",
                [
                    _cell("ex_qoe_bridge", "rep", metric_key="reported_ebitda", value=0.572, fiscal_year=None, label="Reported EBITDA"),
                ],
            ),
        ],
    )


def _findings() -> FindingsDoc:
    return FindingsDoc(
        run_id="r1",
        deal_slug="phase-d",
        updated_at="",
        findings=[
            Finding(
                finding_id="f1",
                severity=FindingSeverity.HIGH,
                title="Cost growth outpaced revenue",
                observation="SG&A grew faster than revenue into FY25.",
                ask_management="Explain FY25 labour and SG&A step-up versus revenue.",
            ),
            Finding(
                finding_id="f2",
                severity=FindingSeverity.MODERATE,
                title="QoE adjustments pending",
                observation="Register empty.",
                ask_management="Confirm one-off items for the closed year.",
            ),
        ],
        counts={"high": 1, "moderate": 1, "low": 0, "info": 0, "total": 2},
    )


def _qoe() -> QoeWorkbookDoc:
    return QoeWorkbookDoc(
        run_id="r1",
        deal_slug="phase-d",
        updated_at="",
        adjusted_ebitda_diligence=0.572,
        adjusted_ebitda_management=0.572,
        materiality_m=0.03,
        bridge=[
            QoeBridgePeriod(
                period="FY25A",
                reported_ebitda=0.572,
                adjustments_total=0.0,
                adjusted_ebitda=0.572,
                steps=[
                    QoeBridgeStep(
                        step_id="base",
                        label="Reported EBITDA",
                        amount=0.572,
                        running_total=0.572,
                    )
                ],
            )
        ],
    )


@pytest.fixture()
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agetic_cdd_api import services_deals as deals_mod

    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_phase_d_es_qoe_trading_bs_deal_shapes() -> None:
    slides = plan_chapter_slides(
        company="Compost Crew",
        store=_store(),
        findings=_findings(),
        qoe=_qoe(),
    )
    assert chapter_sequence(slides) == expected_chapter_ids()

    es_ids = chapter_slide_ids(slides, "es")
    assert "ch_es_kpi" in es_ids and "ch_es_findings" in es_ids and "ch_es_asks" in es_ids
    es_kpi = next(s for s in slides if s.slide_id == "ch_es_kpi")
    # Phase E: store M → PPTX $k (13.282 → 13,282; 0.572 → 572).
    assert es_kpi.kpis and any(
        v in k.value for k in es_kpi.kpis for v in ("13.28", "13.282", "13,282")
    )
    assert es_kpi.table and es_kpi.table.rows
    assert (
        "0.57" in es_kpi.headline
        or "572" in es_kpi.headline
        or "Diligence EBITDA" in es_kpi.headline
    )

    qoe_ids = chapter_slide_ids(slides, "qoe")
    assert "ch_qoe_bridge" in qoe_ids and "ch_qoe_adj" in qoe_ids
    bridge = next(s for s in slides if s.slide_id == "ch_qoe_bridge")
    assert bridge.table and any("Reported EBITDA" in r[0] for r in bridge.table.rows)

    trading_ids = chapter_slide_ids(slides, "trading")
    assert "ch_trading_margin" in trading_ids and "ch_trading_costs" in trading_ids
    margin = next(s for s in slides if s.slide_id == "ch_trading_margin")
    assert margin.table and margin.table.headers[0] == "Metric"

    bs_ids = chapter_slide_ids(slides, "bs")
    assert "ch_bs_net_debt" in bs_ids and "ch_bs_nwc" in bs_ids and "ch_bs_leases" in bs_ids
    nwc = next(s for s in slides if s.slide_id == "ch_bs_nwc")
    assert any("no peg" in o.lower() for o in nwc.observations)
    nd = next(s for s in slides if s.slide_id == "ch_bs_net_debt")
    assert any("dividend" in r[0].lower() for r in (nd.table.rows if nd.table else []))

    deal_ids = chapter_slide_ids(slides, "deal")
    assert "ch_deal_protections" in deal_ids
    assert any(i.startswith("ch_deal_requests") for i in deal_ids)
    req = next(s for s in slides if str(s.slide_id).startswith("ch_deal_requests"))
    assert req.table and req.table.rows[0][0].startswith("R")


def test_phase_d_pptx_renders_content_chapters(tmp_path: Path) -> None:
    slides = plan_chapter_slides(
        company="Compost Crew",
        store=_store(),
        findings=_findings(),
        qoe=_qoe(),
    )
    path = tmp_path / "phase_d.pptx"
    write_fdd_presentation(path, slides)
    inv = slide_chrome_inventory(path)
    blob = "\n".join(" | ".join(r["texts"][:4]) for r in inv)
    assert "EXECUTIVE SUMMARY" in blob
    assert "QUALITY OF EARNINGS" in blob
    assert "TRADE WORKING CAPITAL" in blob.upper() or "working capital" in blob.lower() or "Net working capital" in blob or "Trade working capital" in blob
    assert "DEAL CONSIDERATIONS" in blob
    assert any(r["tables"] >= 1 for r in inv)


def test_assemble_phase_d_persists_deeper_slides(deal_root: Path) -> None:
    from agetic_cdd_api.services_fdd_assemble import assemble_report_spec

    slug = "phase-d-asm"
    (deal_root / slug).mkdir(parents=True)
    store = _store().model_copy(update={"deal_slug": slug})
    findings = _findings().model_copy(update={"deal_slug": slug, "run_id": "run1"})
    qoe = _qoe().model_copy(update={"deal_slug": slug, "run_id": "run1"})
    spec = assemble_report_spec(
        run_id="run1",
        deal_slug=slug,
        store=store,
        company="Compost Crew",
        findings=findings,
        qoe=qoe,
    )
    assert chapter_sequence(list(spec.slides)) == expected_chapter_ids()
    assert any(s.slide_id == "ch_es_asks" for s in spec.slides)
    assert any(s.slide_id == "ch_bs_nwc" for s in spec.slides)
    assert any(s.slide_id == "ch_qoe_bridge" for s in spec.slides)
