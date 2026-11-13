"""Phase E — display scale ($k), LTM/YTD columns, basis, evidence tiers."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    EightLabels,
    EvidenceTier,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    ScopeProfile,
)
from agetic_cdd_api.services_fdd_chapters import (
    DisplayCtx,
    _DISPLAY_CTX,
    _fmt_num,
    _period_table,
    default_chrome,
    plan_chapter_slides,
    resolve_pptx_display_scale,
)
from agetic_cdd_api.services_fdd_pptx import slide_chrome_inventory, write_fdd_presentation


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int | None = 2025,
    evidence_tier: EvidenceTier = EvidenceTier.B,
    basis_label: str | None = None,
    source_ref: dict | None = None,
    period_length: str | None = None,
    period_end: str | None = None,
    scale: str = "M",
) -> ExhibitCell:
    labels = None
    if period_length or period_end or basis_label:
        labels = EightLabels(
            period_length=period_length,
            period_end=period_end,
            basis=basis_label,
            source=(source_ref or {}).get("doc_id") if source_ref else None,
        )
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=metric_key,
        value=value,
        fact_id=f"fact:{metric_key}:{fiscal_year or period_length or 'x'}",
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        currency="USD",
        scale=scale,
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
        evidence_tier=evidence_tier,
        basis_label=basis_label,
        source_ref=source_ref,
        labels=labels,
    )


def _period_cells(eid: str) -> list[ExhibitCell]:
    return [
        _cell(
            eid,
            f"{eid}_r24",
            metric_key="revenue",
            value=11.741,
            fiscal_year=2024,
            evidence_tier=EvidenceTier.A,
            basis_label="Unaudited monthly management accounts",
            source_ref={"doc_id": "D12"},
        ),
        _cell(
            eid,
            f"{eid}_r25",
            metric_key="revenue",
            value=13.282,
            fiscal_year=2025,
            evidence_tier=EvidenceTier.A,
            basis_label="Unaudited monthly management accounts",
            source_ref={"doc_id": "D12"},
        ),
        _cell(
            eid,
            f"{eid}_rytd",
            metric_key="revenue",
            value=7.5,
            fiscal_year=None,
            evidence_tier=EvidenceTier.B,
            basis_label="Unaudited monthly management accounts",
            source_ref={"doc_id": "D12"},
            period_length="YTD Jul-26",
            period_end="2026-07-31",
        ),
        _cell(
            eid,
            f"{eid}_rltm",
            metric_key="revenue",
            value=14.1,
            fiscal_year=None,
            evidence_tier=EvidenceTier.B,
            basis_label="Unaudited monthly management accounts",
            source_ref={"doc_id": "D12"},
            period_length="LTM Jul-26",
            period_end="2026-07-31",
        ),
        _cell(
            eid,
            f"{eid}_e24",
            metric_key="ebitda",
            value=1.115,
            fiscal_year=2024,
            evidence_tier=EvidenceTier.A,
            source_ref={"doc_id": "D12"},
        ),
        _cell(
            eid,
            f"{eid}_e25",
            metric_key="ebitda",
            value=0.572,
            fiscal_year=2025,
            evidence_tier=EvidenceTier.A,
            source_ref={"doc_id": "D12"},
        ),
        _cell(
            eid,
            f"{eid}_em25",
            metric_key="ebitda_margin",
            value=4.25,
            fiscal_year=2025,
            evidence_tier=EvidenceTier.B,
        ),
        _cell(
            eid,
            f"{eid}_gm25",
            metric_key="gross_margin",
            value=30.44,
            fiscal_year=2025,
            evidence_tier=EvidenceTier.B,
        ),
    ]


def _store_with_periods() -> ExhibitStoreDoc:
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug="phase-e",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Historical trading",
                cells=_period_cells("ex_m1_trading"),
            ),
            Exhibit(
                exhibit_id="ex_m2_margin",
                title="Margin",
                cells=_period_cells("ex_m2_margin"),
            ),
        ],
    )


def test_resolve_pptx_display_scale_defaults_to_k() -> None:
    assert resolve_pptx_display_scale(None) == "k"
    scope = ScopeProfile(
        profile_id="p",
        deal_slug="d",
        scale="M",
        report_display_scale="k",
    )
    assert resolve_pptx_display_scale(scope) == "k"
    scope_m = scope.model_copy(update={"report_display_scale": "M"})
    assert resolve_pptx_display_scale(scope_m) == "M"


def test_fmt_num_converts_store_m_to_display_k() -> None:
    ctx = DisplayCtx(display_scale="k", store_scale="M")
    token = _DISPLAY_CTX.set(ctx)
    try:
        # 13.282 M → 13,282 k
        assert _fmt_num(13.282, money=True) == "13,282"
        assert _fmt_num(0.572, money=True) == "572"
    finally:
        _DISPLAY_CTX.reset(token)


def test_period_table_adds_ytd_ltm_basis_source_evidence() -> None:
    store = _store_with_periods()
    ctx = DisplayCtx(display_scale="k", store_scale="M")
    token = _DISPLAY_CTX.set(ctx)
    try:
        table = _period_table(
            store,
            exhibit_id="ex_m1_trading",
            metrics=[
                ("revenue", "Revenue", "money"),
                ("ebitda", "EBITDA", "money"),
                ("ebitda_margin", "EBITDA margin %", "pct"),
            ],
            years=(2024, 2025),
            title="Trading",
        )
    finally:
        _DISPLAY_CTX.reset(token)

    assert table is not None
    assert "($k)" in table.title.lower() or "($k)" in table.title
    assert any(str(h).startswith("YTD") for h in table.headers)
    assert any(str(h).startswith("LTM") for h in table.headers)
    assert "YTD Jul-26" in table.headers
    assert "LTM Jul-26" in table.headers
    rev = next(r for r in table.rows if r[0] == "Revenue")
    # FY24, FY25, YTD, LTM in $k
    assert rev[1] == "11,741"
    assert rev[2] == "13,282"
    assert rev[3] == "7,500"
    assert rev[4] == "14,100"
    assert table.basis and "unaudited" in table.basis.lower()
    assert "D12" in (table.source or "")
    assert table.evidence_tier in {"A", "B", "C"}


def test_plan_chapter_slides_propagates_scale_basis_evidence() -> None:
    store = _store_with_periods()
    scope = ScopeProfile(
        profile_id="p",
        deal_slug="phase-e",
        scale="M",
        report_display_scale="k",
        basis_of_preparation="Unaudited monthly management accounts",
        currency="USD",
    )
    slides = plan_chapter_slides(company="Acme", store=store, scope=scope)
    chrome = default_chrome(company="Acme", scope=scope)
    assert chrome.display_scale == "k"

    es = [s for s in slides if s.chapter == "es"]
    assert es
    # KPI / key table money figures are in thousands.
    moneyish = []
    basis_seen = False
    for s in es:
        for k in s.kpis:
            if k.value and k.value not in {"—"} and "%" not in k.value:
                moneyish.append(k.value)
        if s.table and s.table.rows and s.slide_id != "ch_es_findings":
            if s.table.basis or any("Basis:" in n for n in (s.footnotes or [])):
                basis_seen = True
            for row in s.table.rows:
                for cell in row[1:]:
                    if cell and cell != "—" and "%" not in cell:
                        moneyish.append(cell)
    assert basis_seen
    assert any("," in v or (v.replace(".", "").isdigit() and int(float(v.replace(",", ""))) >= 100) for v in moneyish)

    trading = [s for s in slides if s.chapter == "trading"]
    assert trading
    ytd_tables = [
        s.table
        for s in trading
        if s.table
        and any(
            str(h).startswith("YTD") or str(h).startswith("LTM")
            for h in (s.table.headers or [])
        )
    ]
    assert ytd_tables
    assert any(t.basis for t in ytd_tables)
    assert any(s.source for s in trading)
    assert any(s.evidence_tier for s in trading)


def test_phase_e_pptx_renders_basis_and_source(tmp_path: Path) -> None:
    store = _store_with_periods()
    scope = ScopeProfile(
        profile_id="p",
        deal_slug="phase-e",
        scale="M",
        report_display_scale="k",
        basis_of_preparation="Unaudited monthly management accounts",
    )
    slides = plan_chapter_slides(company="Acme", store=store, scope=scope)
    path = tmp_path / "phase_e.pptx"
    write_fdd_presentation(path, slides, chrome=default_chrome(company="Acme", scope=scope))
    inv = slide_chrome_inventory(path)
    blob = "\n".join(" | ".join(r["texts"]) for r in inv)
    assert "Basis:" in blob or "unaudited" in blob.lower()
    assert "Source:" in blob
    assert any(r["has_evidence"] for r in inv)
