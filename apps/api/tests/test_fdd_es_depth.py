"""Executive summary depth — LTM KPIs, denser findings, mgmt/CIM/diligence case."""

from __future__ import annotations

import pytest

from agetic_cdd_api.fdd_schemas import (
    AdjustmentRow,
    CellStatus,
    EightLabels,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    Finding,
    FindingSeverity,
    FindingSource,
    FindingsDoc,
    QoeBaselinePeriod,
    QoeWorkbookDoc,
)
from agetic_cdd_api.services_fdd_chapters import (
    DisplayCtx,
    _DISPLAY_CTX,
    plan_chapter_slides,
    plan_es,
)
from agetic_cdd_api.services_fdd_qoe import recompute_qoe


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int | None = 2025,
    period_length: str | None = None,
    period_end: str | None = None,
) -> ExhibitCell:
    labels = None
    if period_length or period_end:
        labels = EightLabels(period_length=period_length, period_end=period_end)
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=metric_key,
        value=value,
        fact_id=f"hand:{metric_key}:{fiscal_year or period_length or 'x'}",
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
        labels=labels,
    )


def _store() -> ExhibitStoreDoc:
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug="es-depth",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                cells=[
                    _cell("ex_m1_trading", "r24", metric_key="revenue", value=11.869, fiscal_year=2024),
                    _cell("ex_m1_trading", "r25", metric_key="revenue", value=13.412, fiscal_year=2025),
                    _cell("ex_m1_trading", "e24", metric_key="ebitda", value=1.115, fiscal_year=2024),
                    _cell("ex_m1_trading", "e25", metric_key="ebitda", value=0.561, fiscal_year=2025),
                    _cell("ex_m1_trading", "em25", metric_key="ebitda_margin", value=4.2, fiscal_year=2025),
                    _cell("ex_m1_trading", "gm25", metric_key="gross_margin", value=30.4, fiscal_year=2025),
                    _cell("ex_m1_trading", "ry25", metric_key="revenue_yoy", value=13.0, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m2_margin",
                title="Margin",
                cells=[
                    _cell("ex_m2_margin", "gm25", metric_key="gross_margin", value=30.4, fiscal_year=2025),
                    _cell("ex_m2_margin", "em25", metric_key="ebitda_margin", value=4.2, fiscal_year=2025),
                    _cell("ex_m2_margin", "e25", metric_key="ebitda", value=0.561, fiscal_year=2025),
                    _cell("ex_m2_margin", "r25", metric_key="revenue", value=13.412, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_db_is",
                title="P&L",
                cells=[
                    _cell(
                        "ex_db_is",
                        "r_ytd",
                        metric_key="revenue",
                        value=8.055,
                        fiscal_year=2026,
                        period_length="YTD",
                        period_end="2026-07-31",
                    ),
                    _cell(
                        "ex_db_is",
                        "e_ytd",
                        metric_key="ebitda",
                        value=0.439,
                        fiscal_year=2026,
                        period_length="YTD",
                        period_end="2026-07-31",
                    ),
                    _cell(
                        "ex_db_is",
                        "r_ltm",
                        metric_key="revenue",
                        value=13.649,
                        fiscal_year=2026,
                        period_length="LTM",
                        period_end="2026-07-31",
                    ),
                    _cell(
                        "ex_db_is",
                        "e_ltm",
                        metric_key="ebitda",
                        value=0.502,
                        fiscal_year=2026,
                        period_length="LTM",
                        period_end="2026-07-31",
                    ),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m6_net_debt",
                title="Net debt",
                cells=[
                    _cell("ex_m6_net_debt", "cash", metric_key="cash", value=2.325, fiscal_year=2025),
                    _cell("ex_m6_net_debt", "nd", metric_key="net_debt", value=-0.418, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_db_bs",
                title="BS",
                cells=[
                    _cell("ex_db_bs", "div", metric_key="dividends", value=0.407, fiscal_year=2025),
                ],
            ),
        ],
    )


def _qoe() -> QoeWorkbookDoc:
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
            treatment="reject",
            evidence_status="supported",
            rationale="Bad debt is a recurring operating cost",
            recurring_status="recurring",
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
        deal_slug="es-depth",
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


def _findings() -> FindingsDoc:
    return FindingsDoc(
        run_id="r1",
        deal_slug="es-depth",
        updated_at="",
        findings=[
            Finding(
                finding_id="f_cost",
                severity=FindingSeverity.HIGH,
                title="Cost growth outpaced revenue into FY2025",
                observation="EBITDA fell about 50% as SG&A rose faster than revenue.",
                implication="Value on LTM diligence EBITDA, not plan",
                ask_management="Explain labour and SG&A step-up vs revenue growth",
                source=FindingSource.MODEL,
            ),
            Finding(
                finding_id="f_claim",
                severity=FindingSeverity.HIGH,
                title="Resolve claim revenue FY2025 (contradicted)",
                observation="revenue FY2025: claimed 13.41 vs databook 13.28.",
                implication="Revenue basis differs by source",
                ask_management="Provide the schedule that supports revenue for FY2025",
                source=FindingSource.CLAIM,
            ),
            Finding(
                finding_id="f_div",
                severity=FindingSeverity.MODERATE,
                title="Dividend arrears sit as debt-like",
                observation="Accrued Series A dividends remain unpaid.",
                implication="Debt-like $407k",
                ask_management="Confirm dividend waiver or deduction at closing",
                source=FindingSource.MODEL,
            ),
        ],
        counts={"high": 2, "moderate": 1, "low": 0, "info": 0, "total": 3},
    )


def test_plan_es_includes_ltm_and_case_and_dense_findings() -> None:
    token = _DISPLAY_CTX.set(DisplayCtx(display_scale="k", store_scale="M", include_ltm=True))
    try:
        slides = plan_es(
            commentary=None,
            store=_store(),
            findings=_findings(),
            qoe=_qoe(),
        )
    finally:
        _DISPLAY_CTX.reset(token)

    ids = [s.slide_id for s in slides]
    assert ids == ["ch_es_kpi", "ch_es_findings", "ch_es_cases", "ch_es_asks"]

    kpi = slides[0]
    assert "LTM" in kpi.headline or "502" in kpi.headline or "half of FY24" in kpi.headline
    assert kpi.table is not None
    assert any(str(h).startswith("LTM") for h in kpi.table.headers)
    assert any(str(h).startswith("YTD") for h in kpi.table.headers)
    labels = [r[0] for r in kpi.table.rows]
    assert any("Diligence EBITDA" == lab for lab in labels)
    assert any("Management EBITDA" == lab for lab in labels)
    assert any(k.label.startswith("Diligence EBITDA") and "LTM" in k.label for k in kpi.kpis) or any(
        "502" in k.value or "0.50" in k.value for k in kpi.kpis
    )

    findings = slides[1]
    assert findings.table is not None
    assert findings.table.headers[:4] == ["#", "Finding", "Rating", "Quantified effect"]
    assert "Protection or action" in findings.table.headers
    # MODEL finding should rank ahead of claim noise.
    assert findings.table.rows[0][1].startswith("Cost growth")
    assert findings.table.rows[0][2] == "High"

    cases = slides[2]
    assert cases.table is not None
    case_labels = [r[0] for r in cases.table.rows]
    assert case_labels == ["Management", "CIM", "Diligence", "Downside", "Upside"]
    assert "within" in cases.headline.lower() or "range" in cases.headline.lower()
    # Range $418k–$855k style from sensitivities.
    assert "418" in cases.headline or "855" in cases.headline or "0.42" in cases.headline

    asks = slides[3]
    assert "407" in asks.headline or "dividend" in asks.headline.lower()


def test_plan_chapter_slides_es_depth_count() -> None:
    slides = plan_chapter_slides(
        company="Compost Crew",
        store=_store(),
        findings=_findings(),
        qoe=_qoe(),
    )
    es = [s for s in slides if s.chapter == "es"]
    assert len(es) == 4
    assert {s.slide_id for s in es} >= {
        "ch_es_kpi",
        "ch_es_findings",
        "ch_es_cases",
        "ch_es_asks",
    }


def test_plan_es_ltm_from_cash_bs_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    from agetic_cdd_api.services_fdd_chapter_depth import CashBsPack

    store = _store()
    # Strip LTM exhibit cells so the pack must supply LTM.
    for ex in store.exhibits:
        ex.cells = [
            c
            for c in ex.cells
            if not (
                c.labels
                and str(getattr(c.labels, "period_length", "") or "").upper() == "LTM"
            )
        ]
    pack = CashBsPack(deal_slug="es-depth")
    pack.ltm_revenue = 13.649
    pack.ltm_ebitda = 0.496
    pack.dividends_payable = {"Jul-26": 0.407}
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.build_cash_bs_pack",
        lambda *_a, **_k: pack,
    )
    token = _DISPLAY_CTX.set(DisplayCtx(display_scale="k", store_scale="M", include_ltm=True))
    try:
        slides = plan_es(
            commentary=None,
            store=store,
            findings=_findings(),
            qoe=_qoe(),
        )
    finally:
        _DISPLAY_CTX.reset(token)
    kpi = slides[0]
    assert kpi.table is not None
    assert any("LTM" in str(h) for h in kpi.table.headers)
    assert any(
        k.label.startswith("Diligence EBITDA") and "LTM" in k.label for k in kpi.kpis
    )


def test_es_without_qoe_skips_case_slide() -> None:
    slides = plan_es(
        commentary=None,
        store=_store(),
        findings=_findings(),
        qoe=None,
    )
    ids = [s.slide_id for s in slides]
    assert "ch_es_cases" not in ids
    assert "ch_es_kpi" in ids and "ch_es_findings" in ids and "ch_es_asks" in ids
