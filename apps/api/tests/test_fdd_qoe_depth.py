"""QoE PPTX depth — real bridge, ADJ cards, CIM vs diligence."""

from __future__ import annotations

import pytest

from agetic_cdd_api.fdd_schemas import (
    AdjustmentRow,
    CellStatus,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    QoeBaselinePeriod,
    QoeWorkbookDoc,
)
from agetic_cdd_api.services_fdd_chapters import plan_chapter_slides, plan_qoe
from agetic_cdd_api.services_fdd_qoe import recompute_qoe


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int | None = 2025,
) -> ExhibitCell:
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=metric_key,
        value=value,
        fact_id=f"hand:{metric_key}:{fiscal_year or 'x'}",
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )


def _store() -> ExhibitStoreDoc:
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug="qoe-depth",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                cells=[
                    _cell("ex_m1_trading", "e25", metric_key="ebitda", value=0.572),
                    _cell("ex_m1_trading", "r25", metric_key="revenue", value=13.282),
                ],
            ),
            Exhibit(
                exhibit_id="ex_qoe_bridge",
                title="QoE",
                cells=[
                    _cell(
                        "ex_qoe_bridge",
                        "rep",
                        metric_key="reported_ebitda",
                        value=0.561,
                        fiscal_year=None,
                    )
                ],
            ),
        ],
    )


def _compost_style_qoe() -> QoeWorkbookDoc:
    """Compost Crew–shaped register: reverse bad-debt add-back + nil candidates."""
    period = "FY25A"
    register = [
        AdjustmentRow(
            adjustment_id="ADJ-01",
            event_key="bad-debt-addback:2025",
            period=period,
            label="Bad debt add-back reversed",
            category="normalisation",
            proposed_by="management",
            management_amount=0.011,
            diligence_amount=0.0,
            amount=0.0,
            difference=-0.011,
            difference_reason="Bad debt is a recurring operating cost — reverse management add-back",
            treatment="reject",
            evidence_status="supported",
            rationale="Management EBITDA adds back bad debt; diligence treats it as recurring.",
            recurring_status="recurring",
        ),
        AdjustmentRow(
            adjustment_id="ADJ-02",
            event_key="other-revenue-nature:2025",
            period=period,
            label="Other revenue, nature unknown",
            category="normalisation",
            proposed_by="diligence",
            management_amount=0.0,
            diligence_amount=0.0,
            amount=0.0,
            treatment="pending",
            evidence_status="supported",
            rationale="Other revenue of 0.143 M stays in pending GL nature.",
            recurring_status="uncertain",
        ),
        AdjustmentRow(
            adjustment_id="ADJ-03",
            event_key="professional-fees-stepup:2025",
            period=period,
            label="Professional fee step-up",
            category="non_recurring",
            proposed_by="diligence",
            management_amount=0.0,
            diligence_amount=0.0,
            amount=0.0,
            treatment="pending",
            evidence_status="supported",
            rationale="Nil pending one-off evidence.",
        ),
        AdjustmentRow(
            adjustment_id="S-01",
            event_key="sensitivity:other-revenue:2025",
            period=period,
            label="Downside: other revenue removed",
            category="sensitivity",
            proposed_by="diligence",
            diligence_amount=-0.143,
            amount=-0.143,
            treatment="sensitivity",
            evidence_status="supported",
        ),
        AdjustmentRow(
            adjustment_id="S-02",
            event_key="sensitivity:cost-stepups-oneoff:2025",
            period=period,
            label="Upside: cost step-ups treated as one-off",
            category="sensitivity",
            proposed_by="diligence",
            diligence_amount=0.294,
            amount=0.294,
            treatment="sensitivity",
            evidence_status="pending",
        ),
    ]
    doc = QoeWorkbookDoc(
        run_id="r1",
        deal_slug="qoe-depth",
        updated_at="",
        scale="M",
        period=period,
        baseline=[
            QoeBaselinePeriod(
                period=period,
                management_reported_ebitda=0.561,
                diligence_reported_ebitda=0.561,
                revenue=13.412,
            )
        ],
        candidates=list(register),
        register_rows=list(register),
        cim_ebitda=0.565,
        cim_revenue=13.282,
        accounts_revenue=13.412,
    )
    return recompute_qoe(doc)


def test_compost_style_qoe_bridge_and_walk() -> None:
    qoe = _compost_style_qoe()
    assert qoe.adjusted_ebitda_management == pytest.approx(0.572)
    assert qoe.adjusted_ebitda_diligence == pytest.approx(0.561)
    assert qoe.sensitivity_low == pytest.approx(0.561 - 0.143)
    assert qoe.sensitivity_high == pytest.approx(0.561 + 0.294)
    walk = qoe.management_to_diligence_walk
    assert walk[0].running_total == pytest.approx(0.572)
    assert walk[-1].running_total == pytest.approx(0.561)
    assert any("bad debt" in (s.label or "").lower() for s in walk)


def test_plan_qoe_emits_bridge_walk_cim_adj_sens() -> None:
    qoe = _compost_style_qoe()
    slides = plan_qoe(commentary=None, store=_store(), qoe=qoe, requests=[])
    ids = [s.slide_id for s in slides]
    assert "ch_qoe_bridge" in ids
    assert "ch_qoe_walk" in ids
    assert "ch_qoe_cim" in ids
    assert "ch_qoe_adj" in ids
    assert "ch_qoe_candidates" in ids
    assert "ch_qoe_sens" in ids

    bridge = next(s for s in slides if s.slide_id == "ch_qoe_bridge")
    assert bridge.table is not None
    labels = [r[0].lower() for r in bridge.table.rows]
    assert any("reported" in x for x in labels)
    assert any("management" in x for x in labels)
    assert any("diligence" in x for x in labels)
    assert any("bad debt" in x or "adj-01" in x for x in labels)

    adj = next(s for s in slides if s.slide_id == "ch_qoe_adj")
    assert adj.layout == "adj_detail"
    assert "ADJ-01" in (adj.adj_id or "")
    assert "Bad debt" in (adj.adj_body or "") or "bad debt" in (adj.adj_body or "").lower()

    cim = next(s for s in slides if s.slide_id == "ch_qoe_cim")
    assert cim.table is not None
    assert any("CIM" in r[0] for r in cim.table.rows)


def test_plan_chapter_slides_includes_qoe_depth() -> None:
    slides = plan_chapter_slides(
        company="Compost Crew",
        store=_store(),
        qoe=_compost_style_qoe(),
    )
    qoe_ids = [s.slide_id for s in slides if s.chapter == "qoe"]
    assert "ch_qoe_bridge" in qoe_ids
    assert "ch_qoe_adj" in qoe_ids
    assert "ch_qoe_cim" in qoe_ids


def test_propose_register_from_extract_compost_captions(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.services_fdd_qoe import propose_register_from_extract

    rows = [
        SimpleNamespace(
            caption="Bad Debt",
            fiscal_year=2025,
            value=10890.62,
            scale=None,
            period="FY2025",
            period_length="FY",
            source_name="Compost Crew Monthly Financials 23YTD26.xlsx",
            row_id="bad25",
            table_name="Monthly P&L",
        ),
        SimpleNamespace(
            caption="Other Revenue",
            fiscal_year=2025,
            value=0.142967,
            scale="M",
            period="FY2025",
            period_length="FY",
            source_name="Compost Crew Monthly Financials 23YTD26.xlsx",
            row_id="or25",
            table_name="Monthly P&L",
        ),
        SimpleNamespace(
            caption="Professional Fees",
            fiscal_year=2024,
            value=258765.7,
            scale=None,
            period="FY2024",
            period_length="FY",
            source_name="Compost Crew Monthly Financials 23YTD26.xlsx",
            row_id="pf24",
            table_name="Monthly P&L",
        ),
        SimpleNamespace(
            caption="Professional Fees",
            fiscal_year=2025,
            value=444533.87,
            scale=None,
            period="FY2025",
            period_length="FY",
            source_name="Compost Crew Monthly Financials 23YTD26.xlsx",
            row_id="pf25",
            table_name="Monthly P&L",
        ),
        SimpleNamespace(
            caption="Compost Business Development",
            fiscal_year=2025,
            value=108015.95,
            scale=None,
            period="FY2025",
            period_length="FY",
            source_name="Compost Crew Monthly Financials 23YTD26.xlsx",
            row_id="bd25",
            table_name="Monthly P&L",
        ),
        SimpleNamespace(
            caption="Total Revenues",
            fiscal_year=2025,
            value=13.4115,
            scale="M",
            period="FY2025",
            period_length="FY",
            source_name="Compost Crew Monthly Financials 23YTD26.xlsx",
            row_id="tr25",
            table_name="Monthly P&L",
        ),
        SimpleNamespace(
            caption="EBITDA",
            fiscal_year=2025,
            value=0.565,
            scale="M",
            period="FY2025",
            period_length="FY",
            source_name="CC_Investor_Workbook_EXTERNAL.xlsx",
            row_id="cim_e",
            table_name="Financial Summary",
        ),
        SimpleNamespace(
            caption="Revenue",
            fiscal_year=2025,
            value=13.282,
            scale="M",
            period="FY2025",
            period_length="FY",
            source_name="CC_Investor_Workbook_EXTERNAL.xlsx",
            row_id="cim_r",
            table_name="Financial Summary",
        ),
    ]
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_store.load_rows",
        lambda _deal: rows,
    )
    reg, meta, notes = propose_register_from_extract(
        "test6",
        year=2025,
        period="FY25A",
        target_scale="M",
        ebitda_fact=0.57176,
    )
    assert "bad-debt" in " ".join(notes).lower()
    assert meta["reported_base"] == pytest.approx(0.57176 - 0.01089062)
    assert meta["cim_ebitda"] == pytest.approx(0.565)
    assert meta["cim_revenue"] == pytest.approx(13.282)
    ids = {r.adjustment_id for r in reg}
    assert {"ADJ-01", "ADJ-02", "ADJ-03", "ADJ-04", "ADJ-05", "S-01", "S-02"} <= ids
    bad = next(r for r in reg if r.adjustment_id == "ADJ-01")
    assert bad.treatment == "reject"
    assert bad.management_amount == pytest.approx(0.01089062)
    assert bad.diligence_amount == pytest.approx(0.0)
