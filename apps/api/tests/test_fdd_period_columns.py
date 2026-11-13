"""FY23–25 + YTD/LTM period columns when present in the databook/exhibits."""

from __future__ import annotations

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    EightLabels,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
)
from agetic_cdd_api.services_fdd_chapters import (
    DisplayCtx,
    _DISPLAY_CTX,
    _discover_fy_years,
    _period_column_header,
    _period_table,
    plan_chapter_slides,
)


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int | None,
    period_length: str | None = None,
    period_end: str | None = None,
    label: str | None = None,
) -> ExhibitCell:
    labels = None
    if period_length or period_end:
        labels = EightLabels(period_length=period_length, period_end=period_end)
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=label or metric_key,
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
    """Test6-shaped: FY23–25 on model exhibits; YTD on databook P&L/CF."""
    return ExhibitStoreDoc(
        run_id="r",
        deal_slug="periods",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                cells=[
                    _cell("ex_m1_trading", "r23", metric_key="revenue", value=7.528, fiscal_year=2023),
                    _cell("ex_m1_trading", "r24", metric_key="revenue", value=11.741, fiscal_year=2024),
                    _cell("ex_m1_trading", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                    _cell("ex_m1_trading", "e23", metric_key="ebitda", value=-0.744, fiscal_year=2023),
                    _cell("ex_m1_trading", "e24", metric_key="ebitda", value=1.115, fiscal_year=2024),
                    _cell("ex_m1_trading", "e25", metric_key="ebitda", value=0.572, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m2_margin",
                title="Margin",
                cells=[
                    _cell("ex_m2_margin", "r24", metric_key="revenue", value=11.741, fiscal_year=2024),
                    _cell("ex_m2_margin", "r25", metric_key="revenue", value=13.282, fiscal_year=2025),
                    _cell("ex_m2_margin", "gm25", metric_key="gross_margin", value=30.44, fiscal_year=2025),
                    _cell("ex_m2_margin", "em25", metric_key="ebitda_margin", value=4.25, fiscal_year=2025),
                    _cell("ex_m2_margin", "e25", metric_key="ebitda", value=0.572, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_db_is",
                title="P&L databook",
                cells=[
                    _cell(
                        "ex_db_is",
                        "r_ytd",
                        metric_key="revenue",
                        value=8.055,
                        fiscal_year=2026,
                        period_length="YTD",
                        period_end="2026-07-31",
                        label="Revenue · Jan–Jul 2026 YTD",
                    ),
                    _cell(
                        "ex_db_is",
                        "e_ytd",
                        metric_key="ebitda",
                        value=0.439,
                        fiscal_year=2026,
                        period_length="YTD",
                        period_end="2026-07-31",
                        label="EBITDA · Jan–Jul 2026 YTD",
                    ),
                    _cell(
                        "ex_db_is",
                        "r_ltm",
                        metric_key="revenue",
                        value=13.649,
                        fiscal_year=2026,
                        period_length="LTM",
                        period_end="2026-07-31",
                        label="Revenue · LTM Jul-26",
                    ),
                    _cell(
                        "ex_db_is",
                        "e_ltm",
                        metric_key="ebitda",
                        value=0.502,
                        fiscal_year=2026,
                        period_length="LTM",
                        period_end="2026-07-31",
                        label="EBITDA · LTM Jul-26",
                    ),
                    _cell(
                        "ex_db_is",
                        "e_plan",
                        metric_key="ebitda",
                        value=0.86,
                        fiscal_year=2026,
                        period_length="FY",
                        period_end="2026-12-31",
                        label="EBITDA · FY2026E (plan)",
                    ),
                ],
            ),
            Exhibit(
                exhibit_id="ex_db_cf",
                title="CF databook",
                cells=[
                    _cell("ex_db_cf", "ocf23", metric_key="operating_cash_flow", value=-0.52, fiscal_year=2023, period_length="FY", period_end="2023-12-31"),
                    _cell("ex_db_cf", "ocf24", metric_key="operating_cash_flow", value=0.54, fiscal_year=2024, period_length="FY", period_end="2024-12-31"),
                    _cell("ex_db_cf", "ocf25", metric_key="operating_cash_flow", value=0.61, fiscal_year=2025, period_length="FY", period_end="2025-12-31"),
                    _cell(
                        "ex_db_cf",
                        "ocf_ytd",
                        metric_key="operating_cash_flow",
                        value=0.228,
                        fiscal_year=2026,
                        period_length="YTD",
                        period_end="2026-07-31",
                        label="OCF · Jan–Jul 2026 YTD",
                    ),
                    _cell("ex_db_cf", "capex25", metric_key="capex", value=-0.43, fiscal_year=2025, period_length="FY", period_end="2025-12-31"),
                    _cell(
                        "ex_db_cf",
                        "capex_ytd",
                        metric_key="capex",
                        value=-0.27,
                        fiscal_year=2026,
                        period_length="YTD",
                        period_end="2026-07-31",
                    ),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m7_cash",
                title="Cash model",
                cells=[
                    _cell("ex_m7_cash", "ocf25", metric_key="operating_cash_flow", value=0.61, fiscal_year=2025),
                    _cell("ex_m7_cash", "fcf25", metric_key="free_cash_flow", value=0.18, fiscal_year=2025),
                ],
            ),
        ],
    )


def test_period_column_header_from_period_end() -> None:
    cell = _cell(
        "ex_db_is",
        "x",
        metric_key="revenue",
        value=1.0,
        fiscal_year=2026,
        period_length="YTD",
        period_end="2026-07-31",
    )
    assert _period_column_header(cell, kind="ytd") == "YTD Jul-26"


def test_discover_fy_prefers_23_25_and_skips_plan() -> None:
    store = _store()
    years = _discover_fy_years(
        store,
        ("ex_m1_trading", "ex_db_is"),
        [("revenue", "Revenue", "money"), ("ebitda", "EBITDA", "money")],
    )
    assert years == (2023, 2024, 2025)


def test_period_table_adds_fy23_and_ytd_jul_26() -> None:
    store = _store()
    token = _DISPLAY_CTX.set(DisplayCtx(display_scale="k", store_scale="M"))
    try:
        table = _period_table(
            store,
            exhibit_id=("ex_m2_margin", "ex_m1_trading", "ex_db_is"),
            metrics=[
                ("revenue", "Revenue", "money"),
                ("ebitda", "EBITDA", "money"),
            ],
            title="Revenue and margin",
        )
    finally:
        _DISPLAY_CTX.reset(token)

    assert table is not None
    assert table.headers[:4] == ["Metric", "FY23", "FY24", "FY25"]
    assert any(h.startswith("YTD") for h in table.headers)
    assert "YTD Jul-26" in table.headers
    # Plan FY2026 must not appear as a FY26 column.
    assert "FY26" not in table.headers
    rev = next(r for r in table.rows if r[0] == "Revenue")
    assert rev[1] == "7,528"
    assert rev[2] == "11,741"
    assert rev[3] == "13,282"
    assert rev[4] == "8,055"


def test_cash_table_pulls_ytd_from_databook_cf() -> None:
    store = _store()
    token = _DISPLAY_CTX.set(DisplayCtx())
    try:
        table = _period_table(
            store,
            exhibit_id=("ex_m7_cash", "ex_db_cf"),
            metrics=[
                ("operating_cash_flow", "Operating cash flow", "money"),
                ("capex", "Capex", "money"),
            ],
            title="Cash",
        )
    finally:
        _DISPLAY_CTX.reset(token)
    assert table is not None
    assert "FY23" in table.headers and "FY25" in table.headers
    assert "YTD Jul-26" in table.headers
    ocf = next(r for r in table.rows if r[0] == "Operating cash flow")
    assert ocf[-1] == "228"  # 0.228 M → $k


def test_plan_chapter_slides_trading_and_es_have_period_pack() -> None:
    slides = plan_chapter_slides(company="Acme", store=_store())
    trading = next(s for s in slides if s.slide_id == "ch_trading_margin")
    assert trading.table is not None
    assert trading.table.headers[:4] == ["Metric", "FY23", "FY24", "FY25"]
    assert "YTD Jul-26" in trading.table.headers

    es = next(s for s in slides if s.slide_id == "ch_es_kpi")
    assert es.table is not None
    assert "FY23" in es.table.headers
    assert any(str(h).startswith("YTD") for h in es.table.headers)
    assert any(str(h).startswith("LTM") for h in es.table.headers)
    assert "LTM" in es.headline or "half of FY24" in es.headline or any(
        "LTM" in k.label for k in es.kpis
    )

    cash = next(s for s in slides if s.slide_id == "ch_cash_1")
    assert cash.table is not None
    assert "YTD Jul-26" in cash.table.headers
