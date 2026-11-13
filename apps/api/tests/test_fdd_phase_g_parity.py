"""Phase G — structural goldens, Test6 smoke, CI chrome/chapter guards."""

from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation

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
    DEFAULT_CHAPTER_ORDER,
    expected_chapter_ids,
    plan_chapter_slides,
)
from agetic_cdd_api.services_fdd_parity import (
    assert_pptx_parity,
    check_artifact_extensions,
    check_pptx_file_parity,
    check_slide_spec_parity,
    load_pptx_parity_contract,
    parity_contract_path,
)
from agetic_cdd_api.services_fdd_pptx import write_fdd_presentation


@pytest.fixture()
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agetic_cdd_api import services_deals as deals_mod

    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


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


def _test6_store() -> ExhibitStoreDoc:
    """Compost Crew / Test6-shaped exhibit pack for smoke generation."""
    return ExhibitStoreDoc(
        run_id="test6",
        deal_slug="test6-crew",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Historical trading",
                cells=[
                    _cell("ex_m1_trading", "r24", metric_key="revenue", value=11.741, fiscal_year=2024),
                    _cell("ex_m1_trading", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                    _cell("ex_m1_trading", "e24", metric_key="ebitda", value=1.115, fiscal_year=2024),
                    _cell("ex_m1_trading", "e25", metric_key="ebitda", value=0.572, fiscal_year=2025),
                    _cell("ex_m1_trading", "em25", metric_key="ebitda_margin", value=4.25, fiscal_year=2025),
                    _cell("ex_m1_trading", "gm25", metric_key="gross_margin", value=30.44, fiscal_year=2025),
                    _cell("ex_m1_trading", "ry25", metric_key="revenue_yoy", value=13.12, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m2_margin",
                title="Margin",
                cells=[
                    _cell("ex_m2_margin", "gm24", metric_key="gross_margin", value=31.78, fiscal_year=2024),
                    _cell("ex_m2_margin", "gm25", metric_key="gross_margin", value=30.44, fiscal_year=2025),
                    _cell("ex_m2_margin", "e25", metric_key="ebitda", value=0.572, fiscal_year=2025),
                    _cell("ex_m2_margin", "em25", metric_key="ebitda_margin", value=4.25, fiscal_year=2025),
                    _cell("ex_m2_margin", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m3_costs",
                title="Costs",
                cells=[
                    _cell("ex_m3_costs", "sga25", metric_key="sga", value=4.23, fiscal_year=2025),
                    _cell("ex_m3_costs", "sga_y", metric_key="sga_yoy", value=29.28, fiscal_year=2025),
                    _cell("ex_m3_costs", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m5_nwc",
                title="NWC",
                cells=[
                    _cell("ex_m5_nwc", "ar", metric_key="accounts_receivable", value=1.22),
                    _cell("ex_m5_nwc", "inv", metric_key="inventory", value=0.23),
                    _cell("ex_m5_nwc", "ap", metric_key="accounts_payable", value=0.50),
                    _cell("ex_m5_nwc", "nwc", metric_key="nwc", value=0.95),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m6_net_debt",
                title="Net debt",
                cells=[
                    _cell("ex_m6_net_debt", "cash", metric_key="cash", value=2.67),
                    _cell("ex_m6_net_debt", "gd", metric_key="gross_debt", value=2.02),
                    _cell("ex_m6_net_debt", "nd", metric_key="net_debt", value=-0.65),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m7_cash",
                title="Cash",
                cells=[
                    _cell("ex_m7_cash", "ocf", metric_key="operating_cash_flow", value=0.61),
                    _cell("ex_m7_cash", "fcf", metric_key="free_cash_flow", value=0.18),
                    _cell("ex_m7_cash", "cc", metric_key="cash_conversion", value=106.78),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m8_bs",
                title="BS",
                cells=[_cell("ex_m8_bs", "eq", metric_key="total_equity", value=3.65)],
            ),
            Exhibit(
                exhibit_id="ex_db_bs",
                title="BS databook",
                cells=[
                    _cell("ex_db_bs", "div25", metric_key="dividends", value=0.37),
                    _cell("ex_db_bs", "eq", metric_key="total_equity", value=3.65),
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
                        value=0.572,
                        fiscal_year=None,
                    )
                ],
            ),
        ],
    )


def _test6_findings() -> FindingsDoc:
    return FindingsDoc(
        run_id="test6",
        deal_slug="test6-crew",
        updated_at="",
        findings=[
            Finding(
                finding_id="f1",
                severity=FindingSeverity.HIGH,
                title="Cost growth outpaced revenue",
                observation="SG&A grew faster than revenue into FY25.",
                ask_management="Explain FY25 labour and SG&A step-up versus revenue.",
            )
        ],
        counts={"high": 1, "moderate": 0, "low": 0, "info": 0, "total": 1},
    )


def _test6_qoe() -> QoeWorkbookDoc:
    return QoeWorkbookDoc(
        run_id="test6",
        deal_slug="test6-crew",
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


@pytest.mark.fdd_ship
def test_parity_contract_matches_planner() -> None:
    contract = load_pptx_parity_contract()
    assert parity_contract_path().is_file()
    assert contract["contract_id"] == "fdd_pptx_parity_v1"
    assert contract["chapter_order"] == expected_chapter_ids()
    assert contract["chapter_order"] == [ch for _n, ch, _b, _t in DEFAULT_CHAPTER_ORDER]
    for banner in (
        "EXECUTIVE SUMMARY",
        "QUALITY OF EARNINGS",
        "TRADING",
        "DEAL CONSIDERATIONS",
        "APPENDICES",
    ):
        assert banner in contract["required_banners"]


@pytest.mark.fdd_ship
def test_slide_spec_passes_structural_golden() -> None:
    slides = plan_chapter_slides(
        company="Compost Crew",
        store=_test6_store(),
        findings=_test6_findings(),
        qoe=_test6_qoe(),
    )
    failures = check_slide_spec_parity(slides)
    assert failures == [], failures


@pytest.mark.fdd_ship
def test_rendered_pptx_passes_chrome_golden(tmp_path: Path) -> None:
    slides = plan_chapter_slides(
        company="Compost Crew",
        store=_test6_store(),
        findings=_test6_findings(),
        qoe=_test6_qoe(),
    )
    path = tmp_path / "parity.pptx"
    write_fdd_presentation(path, slides)
    failures = check_pptx_file_parity(path)
    assert failures == [], failures
    prs = Presentation(str(path))
    assert len(prs.slides) >= 12


@pytest.mark.fdd_ship
def test_test6_smoke_fdd_report_pptx_only(deal_root: Path) -> None:
    """Test6 smoke: generate FDD Report PPTX with required chapters; no DOCX/PDF."""
    from agetic_cdd_api.report_fdd import FddReportBuilder
    from agetic_cdd_api.services_fdd_assemble import assemble_and_persist
    from agetic_cdd_api.services_fdd_render import ensure_phase0_run
    from agetic_cdd_api.services_fdd_store import (
        load_report_spec,
        save_exhibit_store,
        save_findings,
        save_qoe_workbook,
    )

    slug = "test6-crew"
    (deal_root / slug).mkdir(parents=True)
    manifest, _store, _ = ensure_phase0_run(
        slug, company="Compost Crew", revenue_fy24=11.741, prefer_current_release=True
    )
    # Overlay Test6-shaped exhibits so chapters have table depth.
    rich = _test6_store().model_copy(
        update={"run_id": manifest.run_id, "deal_slug": slug}
    )
    save_exhibit_store(rich)
    findings = _test6_findings().model_copy(
        update={"run_id": manifest.run_id, "deal_slug": slug}
    )
    qoe = _test6_qoe().model_copy(update={"run_id": manifest.run_id, "deal_slug": slug})
    save_findings(findings)
    save_qoe_workbook(qoe)

    spec = assemble_and_persist(
        slug,
        manifest.run_id,
        store=rich,
        company="Compost Crew",
        update_manifest=True,
    )
    assert_pptx_parity(slides=list(spec.slides or []))

    events = list(FddReportBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in events)

    out_dir = deal_root / slug / "reports" / "fdd_report"
    pptx_files = list(out_dir.glob("*_FDD_Report.pptx"))
    assert pptx_files
    assert_pptx_parity(pptx_path=pptx_files[0], report_dir=out_dir)
    assert check_artifact_extensions(out_dir) == []
    assert not list(out_dir.glob("*.docx"))
    assert not list(out_dir.glob("*.pdf"))

    persisted = load_report_spec(slug, manifest.run_id)
    assert persisted is not None
    assert_pptx_parity(slides=list(persisted.slides or []))


@pytest.mark.fdd_ship
def test_ci_guard_fails_when_chapter_missing() -> None:
    slides = plan_chapter_slides(company="Acme", store=_test6_store())
    # Drop QoE slides — CI guard must fail.
    truncated = [s for s in slides if s.chapter != "qoe"]
    failures = check_slide_spec_parity(truncated)
    assert any("qoe" in f for f in failures)
    with pytest.raises(AssertionError, match="parity failures"):
        assert_pptx_parity(slides=truncated)
