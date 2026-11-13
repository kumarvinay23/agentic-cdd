"""Focused fix: resolve {{ex:…}} tokens + consistent $k/$m PPTX display."""

from __future__ import annotations

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    CommentaryDoc,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    SectionDraft,
)
from agetic_cdd_api.services_fdd_chapters import (
    DisplayCtx,
    _DISPLAY_CTX,
    _fmt_num,
    plan_chapter_slides,
)
from agetic_cdd_api.services_fdd_tokens import (
    format_pptx_money,
    make_token,
    resolve_text_pptx,
    scrub_store_unit_labels,
)


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int | None = 2025,
    scale: str = "M",
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
        scale=scale,
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )


def test_format_pptx_money_table_and_prose() -> None:
    assert format_pptx_money(13.282, prose=False) == "13,282"
    assert format_pptx_money(0.572, prose=False) == "572"
    assert format_pptx_money(-0.65, prose=False) == "(650)"
    assert format_pptx_money(13.282, prose=True) == "$13.28m"
    assert format_pptx_money(0.572, prose=True) == "$572k"
    assert format_pptx_money(-0.65, prose=True) == "($650k)"


def test_fmt_num_prose_flag() -> None:
    ctx = DisplayCtx(display_scale="k", store_scale="M")
    token = _DISPLAY_CTX.set(ctx)
    try:
        assert _fmt_num(13.282, money=True) == "13,282"
        assert _fmt_num(13.282, money=True, prose=True) == "$13.28m"
        assert _fmt_num(0.572, money=True, prose=True) == "$572k"
    finally:
        _DISPLAY_CTX.reset(token)


def test_resolve_text_pptx_replaces_tokens_and_scrubs_usd_m() -> None:
    eid = "ex_m1_trading"
    store = ExhibitStoreDoc(
        run_id="r",
        deal_slug="d",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id=eid,
                title="Trading",
                cells=[
                    _cell(eid, "revenue_fy2025", metric_key="revenue", value=13.282),
                ],
            )
        ],
    )
    tok = make_token(eid, "revenue_fy2025")
    text = f"Historical trading: FY2025 revenue {tok} (USD M)"
    resolved = resolve_text_pptx(text, store)
    assert "{{ex:" not in resolved.text
    assert "USD M" not in resolved.text
    assert "$13.28m" in resolved.text
    assert resolved.unresolved == []


def test_resolve_text_pptx_unresolved_becomes_em_dash() -> None:
    store = ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="", exhibits=[])
    text = "Revenue {{ex:ex_missing.revenue_fy2025}} (USD M)"
    resolved = resolve_text_pptx(text, store)
    assert "{{ex:" not in resolved.text
    assert "—" in resolved.text
    assert "USD M" not in resolved.text


def test_scrub_store_unit_labels() -> None:
    assert scrub_store_unit_labels("foo (USD M) bar") == "foo bar"
    assert "USD" not in scrub_store_unit_labels("EBITDA 1.2 USD M")


def test_plan_chapter_slides_resolves_commentary_tokens() -> None:
    eid = "ex_m1_trading"
    store = ExhibitStoreDoc(
        run_id="r",
        deal_slug="d",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id=eid,
                title="Trading",
                cells=[
                    _cell(eid, "revenue_fy2025", metric_key="revenue", value=13.282, fiscal_year=2025),
                    _cell(eid, "ebitda_fy2025", metric_key="ebitda", value=0.572, fiscal_year=2025),
                    _cell(eid, "ebitda_fy2024", metric_key="ebitda", value=1.115, fiscal_year=2024),
                    _cell(eid, "gross_margin_fy2025", metric_key="gross_margin", value=30.44, fiscal_year=2025),
                    _cell(eid, "revenue_fy2024", metric_key="revenue", value=11.741, fiscal_year=2024),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m2_margin",
                title="Margin",
                cells=[
                    _cell("ex_m2_margin", "gross_margin_fy2025", metric_key="gross_margin", value=30.44),
                    _cell("ex_m2_margin", "ebitda_margin_fy2025", metric_key="ebitda_margin", value=4.25),
                    _cell("ex_m2_margin", "revenue_fy2025", metric_key="revenue", value=13.282),
                    _cell("ex_m2_margin", "ebitda_fy2025", metric_key="ebitda", value=0.572),
                ],
            ),
        ],
    )
    tok = make_token(eid, "revenue_fy2025")
    commentary = CommentaryDoc(
        run_id="r",
        deal_slug="d",
        updated_at="",
        sections=[
            SectionDraft(
                section_id="SEC-B",
                title="Trading",
                body=f"Historical trading: FY2025 revenue {tok} (USD M)",
            )
        ],
    )
    slides = plan_chapter_slides(company="Acme", store=store, commentary=commentary)
    blob = "\n".join(
        "\n".join([s.headline or "", *list(s.observations or [])]) for s in slides
    )
    assert "{{ex:" not in blob
    assert "USD M" not in blob
    # KPI / headline prose money
    es = next(s for s in slides if s.slide_id == "ch_es_kpi")
    assert any(v.startswith("$") and (v.endswith("k") or v.endswith("m") or v.endswith("k)") or v.endswith("m)")) for v in (k.value for k in es.kpis))
    assert "$" in (es.headline or "")
    # Trading observations should carry resolved $ figure from commentary token
    trading = [s for s in slides if s.chapter == "trading"]
    trading_blob = "\n".join("\n".join(s.observations or []) for s in trading)
    assert "$13.28m" in trading_blob or "$13,282k" in trading_blob or "13.28" in trading_blob
