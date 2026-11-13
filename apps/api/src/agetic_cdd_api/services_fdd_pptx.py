"""FDD Report PPTX layouts — Phase B chrome matching Project_Crew_FDD_1.

Layouts emit banner / headline / KPI|table|chart / Observations / Source /
Evidence / page number. Numbers still come from callers (exhibit-bound later).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from agetic_cdd_api.fdd_schemas import (
    FindingRankRow,
    KpiTile,
    PptxChrome,
    SlideSpec,
    SlideTable,
    StubRenderPage,
    TocEntry,
)

# Widescreen 13.33 × 7.5 in (matches expected pack).
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# Palette from Project_Crew_FDD_1 (2).pptx
_COLOR_NAVY = RGBColor(0x14, 0x21, 0x3D)
_COLOR_TEAL = RGBColor(0x0F, 0x7C, 0x80)
_COLOR_MUTED = RGBColor(0x7B, 0x87, 0x94)
_COLOR_TILE = RGBColor(0xEE, 0xF2, 0xF6)
_COLOR_EVIDENCE = RGBColor(0xB7, 0x79, 0x1F)
_COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_COLOR_RULE = RGBColor(0xD0, 0xD7, 0xDE)
_COLOR_OBS_CALL = RGBColor(0xF5, 0xF7, 0xFA)

_FONT = "Arial"
_MARGIN_L = Inches(0.45)
_MARGIN_R = Inches(0.45)
_CONTENT_W = Inches(12.43)
_BANNER_TOP = Inches(0.20)
_HEADLINE_TOP = Inches(0.42)
_BODY_TOP = Inches(1.30)
_FOOTER_TOP = Inches(6.90)
_SOURCE_W = Inches(10.60)
_EVIDENCE_L = Inches(11.30)
_PAGE_L = Inches(12.40)


def _set_run_font(
    run,
    *,
    size_pt: float,
    bold: bool | None = None,
    color: RGBColor | None = None,
    name: str = _FONT,
) -> None:
    run.font.name = name
    run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    # Force Arial even when theme latin is set.
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:cs", "a:ea"):
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {})
            rpr.append(el)
        el.set("typeface", name)


def _add_textbox(
    slide,
    left,
    top,
    width,
    height,
    text: str,
    *,
    size_pt: float = 10,
    bold: bool = False,
    color: RGBColor | None = None,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    word_wrap: bool = True,
):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = word_wrap
    try:
        tf.auto_size = None
    except Exception:
        pass
    tf.paragraphs[0].alignment = align
    try:
        box.text_frame._txBody.bodyPr.set("anchor", {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}.get(anchor, "t"))
    except Exception:
        pass
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text or ""
    _set_run_font(run, size_pt=size_pt, bold=bold, color=color or _COLOR_NAVY)
    return box


def _add_multiline(
    slide,
    left,
    top,
    width,
    height,
    lines: Sequence[str],
    *,
    size_pt: float = 9,
    bold_first: bool = False,
    color: RGBColor | None = None,
    bullet: bool = True,
) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, raw in enumerate(lines):
        line = (raw or "").strip()
        if not line:
            continue
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(4)
        run = p.add_run()
        run.text = f"• {line}" if bullet and not line.startswith(("•", "-", "*")) else line.lstrip("•-* ").strip() if bullet else line
        if bullet and line.startswith(("•", "-", "*")):
            run.text = "• " + line.lstrip("•-* ").strip()
        _set_run_font(
            run,
            size_pt=size_pt,
            bold=bold_first and i == 0,
            color=color or _COLOR_NAVY,
        )


def _solid_fill(shape, color: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _chrome_header(slide, spec: SlideSpec, chrome: PptxChrome) -> None:
    banner = (spec.banner or "").strip().upper() or "FDD"
    _add_textbox(
        slide,
        _MARGIN_L,
        _BANNER_TOP,
        Inches(8.0),
        Inches(0.22),
        banner,
        size_pt=8,
        bold=True,
        color=_COLOR_TEAL,
    )
    subtitle = f"{chrome.project_label} | {chrome.basis_short}"
    _add_textbox(
        slide,
        Inches(8.38),
        _BANNER_TOP,
        Inches(4.5),
        Inches(0.22),
        subtitle,
        size_pt=8,
        bold=False,
        color=_COLOR_MUTED,
        align=PP_ALIGN.RIGHT,
    )
    if spec.headline:
        _add_textbox(
            slide,
            _MARGIN_L,
            _HEADLINE_TOP,
            _CONTENT_W,
            Inches(0.80),
            spec.headline,
            size_pt=18,
            bold=True,
            color=_COLOR_NAVY,
        )


def _chrome_footer(slide, spec: SlideSpec) -> None:
    if spec.source:
        _add_textbox(
            slide,
            _MARGIN_L,
            _FOOTER_TOP,
            _SOURCE_W,
            Inches(0.42),
            spec.source if spec.source.lower().startswith("source") else f"Source: {spec.source}",
            size_pt=7,
            bold=False,
            color=_COLOR_MUTED,
        )
    if spec.evidence_tier:
        badge = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            _EVIDENCE_L,
            Inches(6.95),
            Inches(1.05),
            Inches(0.24),
        )
        _solid_fill(badge, _COLOR_EVIDENCE)
        tf = badge.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = f"Evidence {spec.evidence_tier}"
        _set_run_font(run, size_pt=7, bold=True, color=_COLOR_WHITE)
    if spec.page_no is not None:
        _add_textbox(
            slide,
            _PAGE_L,
            Inches(6.95),
            Inches(0.50),
            Inches(0.24),
            str(spec.page_no),
            size_pt=8,
            bold=False,
            color=_COLOR_MUTED,
            align=PP_ALIGN.RIGHT,
        )


def _add_table_title(
    slide,
    table: SlideTable,
    *,
    left,
    top,
    width,
) -> Any:
    """Render table title plus optional Phase E basis line; returns next top emu."""
    title_h = Inches(0.24) if table.title else Inches(0)
    if table.title:
        _add_textbox(
            slide,
            left,
            top,
            width,
            title_h,
            table.title,
            size_pt=10,
            bold=True,
            color=_COLOR_NAVY,
        )
    next_top = Emu(int(top) + int(title_h))
    if table.basis:
        basis_h = Inches(0.18)
        basis_text = (
            table.basis
            if table.basis.lower().startswith("basis")
            else f"Basis: {table.basis}"
        )
        _add_textbox(
            slide,
            left,
            next_top,
            width,
            basis_h,
            basis_text,
            size_pt=7,
            bold=False,
            color=_COLOR_MUTED,
        )
        next_top = Emu(int(next_top) + int(basis_h))
    return next_top


def _add_table(
    slide,
    table: SlideTable,
    *,
    left,
    top,
    width,
    height,
) -> Any:
    headers = list(table.headers or [])
    rows = [list(r) for r in (table.rows or [])]
    n_cols = max(len(headers), max((len(r) for r in rows), default=0), 1)
    n_rows = 1 + len(rows) if headers else max(len(rows), 1)
    if headers and len(headers) < n_cols:
        headers = headers + [""] * (n_cols - len(headers))
    shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    tbl = shape.table
    # Prefer compact row heights.
    for ri in range(n_rows):
        tbl.rows[ri].height = int(height / max(n_rows, 1))
    start_data = 0
    if headers:
        for ci, h in enumerate(headers[:n_cols]):
            cell = tbl.cell(0, ci)
            cell.text = str(h)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    _set_run_font(run, size_pt=8, bold=True, color=_COLOR_NAVY)
        start_data = 1
    for ri, row in enumerate(rows):
        for ci in range(n_cols):
            val = row[ci] if ci < len(row) else ""
            cell = tbl.cell(start_data + ri, ci)
            cell.text = str(val)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    _set_run_font(run, size_pt=8, bold=ci == 0, color=_COLOR_NAVY)
    return shape


def _obs_panel(
    slide,
    observations: Sequence[str],
    *,
    left,
    top,
    width,
    height,
    callout: str | None = None,
) -> None:
    _add_textbox(
        slide,
        left,
        top,
        width,
        Inches(0.26),
        "Observations",
        size_pt=10,
        bold=True,
        color=_COLOR_NAVY,
    )
    body_h = height - Inches(0.30)
    if callout:
        body_h = height - Inches(1.15)
    _add_multiline(
        slide,
        left,
        top + Inches(0.30),
        width,
        body_h,
        list(observations)[:10],
        size_pt=9,
        bullet=True,
    )
    if callout:
        call = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            left,
            top + height - Inches(0.78),
            width,
            Inches(0.72),
        )
        _solid_fill(call, _COLOR_OBS_CALL)
        tf = call.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = callout
        _set_run_font(run, size_pt=8, bold=False, color=_COLOR_NAVY)


def _layout_cover(slide, spec: SlideSpec) -> None:
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), SLIDE_W, SLIDE_H)
    _solid_fill(bg, _COLOR_NAVY)
    _add_textbox(
        slide,
        Inches(0.80),
        Inches(1.60),
        Inches(11.50),
        Inches(0.50),
        spec.deal_name or spec.banner or "FDD",
        size_pt=16,
        bold=False,
        color=_COLOR_WHITE,
    )
    _add_textbox(
        slide,
        Inches(0.80),
        Inches(2.20),
        Inches(11.50),
        Inches(1.00),
        spec.engagement or "Financial due diligence",
        size_pt=36,
        bold=True,
        color=_COLOR_WHITE,
    )
    if spec.entity_line:
        _add_textbox(
            slide,
            Inches(0.80),
            Inches(3.70),
            Inches(11.50),
            Inches(0.70),
            spec.entity_line,
            size_pt=14,
            bold=False,
            color=_COLOR_WHITE,
        )
    bits = [b for b in (spec.basis_line, spec.date_line) if b]
    if bits:
        _add_textbox(
            slide,
            Inches(0.80),
            Inches(5.60),
            Inches(11.50),
            Inches(0.70),
            "\n".join(bits),
            size_pt=11,
            bold=False,
            color=_COLOR_WHITE,
        )
    _add_textbox(
        slide,
        Inches(0.80),
        Inches(6.70),
        Inches(11.50),
        Inches(0.30),
        spec.confidentiality,
        size_pt=9,
        bold=False,
        color=RGBColor(0xC5, 0xCD, 0xD6),
    )


def _layout_toc(slide, spec: SlideSpec, chrome: PptxChrome) -> None:
    _chrome_header(slide, spec, chrome)
    entries = list(spec.toc_entries or [])
    y = Inches(1.50)
    for entry in entries[:12]:
        _add_textbox(
            slide,
            _MARGIN_L,
            y,
            Inches(0.60),
            Inches(0.36),
            entry.number,
            size_pt=14,
            bold=True,
            color=_COLOR_TEAL,
        )
        _add_textbox(
            slide,
            Inches(1.15),
            y,
            Inches(9.0),
            Inches(0.36),
            entry.title,
            size_pt=14,
            bold=False,
            color=_COLOR_NAVY,
        )
        _add_textbox(
            slide,
            Inches(11.80),
            y,
            Inches(1.0),
            Inches(0.36),
            entry.page,
            size_pt=14,
            bold=False,
            color=_COLOR_MUTED,
            align=PP_ALIGN.RIGHT,
        )
        y = Emu(int(y) + int(Inches(0.42)))


def _layout_kpi_strip(slide, spec: SlideSpec, chrome: PptxChrome) -> None:
    _chrome_header(slide, spec, chrome)
    tiles = list(spec.kpis or [])[:6]
    if tiles:
        gap = Inches(0.18)
        tile_w = Inches(1.92)
        x = _MARGIN_L
        for tile in tiles:
            card = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, _BODY_TOP, tile_w, Inches(0.97))
            _solid_fill(card, _COLOR_TILE)
            _add_textbox(
                slide,
                Emu(int(x) + int(Inches(0.10))),
                Inches(1.38),
                Inches(1.72),
                Inches(0.14),
                tile.label,
                size_pt=7,
                bold=False,
                color=_COLOR_MUTED,
            )
            _add_textbox(
                slide,
                Emu(int(x) + int(Inches(0.10))),
                Inches(1.56),
                Inches(1.72),
                Inches(0.33),
                tile.value,
                size_pt=16,
                bold=True,
                color=_COLOR_NAVY,
            )
            if tile.detail:
                _add_textbox(
                    slide,
                    Emu(int(x) + int(Inches(0.10))),
                    Inches(1.93),
                    Inches(1.72),
                    Inches(0.26),
                    tile.detail,
                    size_pt=7,
                    bold=False,
                    color=_COLOR_MUTED,
                )
            x = Emu(int(x) + int(tile_w) + int(gap))

    table_top = Inches(2.45)
    if spec.table and (spec.table.headers or spec.table.rows):
        grid_top = _add_table_title(
            slide,
            spec.table,
            left=_MARGIN_L,
            top=table_top,
            width=Inches(6.32),
        )
        _add_table(
            slide,
            spec.table,
            left=_MARGIN_L,
            top=grid_top,
            width=Inches(6.32),
            height=Inches(2.69),
        )
        _obs_panel(
            slide,
            spec.observations,
            left=Inches(7.07),
            top=table_top,
            width=Inches(5.82),
            height=Inches(3.05),
        )
    else:
        _obs_panel(
            slide,
            spec.observations,
            left=_MARGIN_L,
            top=table_top,
            width=_CONTENT_W,
            height=Inches(3.90),
        )
    _chrome_footer(slide, spec)


def _layout_section_table_obs(slide, spec: SlideSpec, chrome: PptxChrome) -> None:
    _chrome_header(slide, spec, chrome)
    left_w = Inches(8.06)
    right_l = Inches(8.81)
    right_w = Inches(4.08)
    table = spec.table or SlideTable(headers=["Item", "Value"], rows=[])
    grid_top = _BODY_TOP
    if table.title or table.basis:
        grid_top = _add_table_title(
            slide,
            table,
            left=_MARGIN_L,
            top=_BODY_TOP,
            width=left_w,
        )
    _add_table(
        slide,
        table,
        left=_MARGIN_L,
        top=grid_top if (table.title or table.basis) else Inches(1.56),
        width=left_w,
        height=Inches(4.50) if table.rows else Inches(2.0),
    )
    callout = spec.footnotes[0] if spec.footnotes else None
    _obs_panel(
        slide,
        spec.observations,
        left=right_l,
        top=_BODY_TOP,
        width=right_w,
        height=Inches(4.0),
        callout=callout,
    )
    for i, note in enumerate(spec.footnotes[1:3]):
        _add_textbox(
            slide,
            _MARGIN_L,
            Emu(int(Inches(6.60)) + i * int(Inches(0.14))),
            _CONTENT_W,
            Inches(0.14),
            note,
            size_pt=7,
            bold=False,
            color=_COLOR_MUTED,
        )
    _chrome_footer(slide, spec)


def _layout_section_chart_obs(slide, spec: SlideSpec, chrome: PptxChrome) -> None:
    _chrome_header(slide, spec, chrome)
    # Chart placeholder frame (real chart binding comes in later phases).
    frame = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, _MARGIN_L, _BODY_TOP, Inches(8.06), Inches(4.80)
    )
    _solid_fill(frame, _COLOR_TILE)
    label = spec.chart_title or "Chart"
    _add_textbox(
        slide,
        _MARGIN_L,
        Inches(3.40),
        Inches(8.06),
        Inches(0.40),
        label,
        size_pt=12,
        bold=True,
        color=_COLOR_MUTED,
        align=PP_ALIGN.CENTER,
    )
    _obs_panel(
        slide,
        spec.observations,
        left=Inches(8.81),
        top=_BODY_TOP,
        width=Inches(4.08),
        height=Inches(4.80),
    )
    _chrome_footer(slide, spec)


def _layout_findings_rank(slide, spec: SlideSpec, chrome: PptxChrome) -> None:
    _chrome_header(slide, spec, chrome)
    # Prefer an authored table (ES depth: Rating / Quantified effect / Tier / Protection).
    if spec.table and (spec.table.headers or spec.table.rows):
        table = spec.table
    else:
        headers = ["#", "Severity", "Finding", "Detail"]
        rows: list[list[str]] = []
        for fr in spec.findings or []:
            rows.append([str(fr.rank), fr.severity, fr.title, fr.detail])
        table = SlideTable(
            title=spec.table.title if spec.table else "",
            headers=headers,
            rows=rows,
        )
    if table.title:
        _add_textbox(
            slide,
            _MARGIN_L,
            _BODY_TOP,
            _CONTENT_W,
            Inches(0.24),
            table.title,
            size_pt=10,
            bold=True,
            color=_COLOR_NAVY,
        )
    _add_table(
        slide,
        table,
        left=_MARGIN_L,
        top=Inches(1.56),
        width=_CONTENT_W,
        height=Inches(4.80),
    )
    _chrome_footer(slide, spec)


def _layout_adj_detail(slide, spec: SlideSpec, chrome: PptxChrome) -> None:
    _chrome_header(slide, spec, chrome)
    title = spec.adj_id or (spec.table.title if spec.table else "Adjustment")
    _add_textbox(
        slide,
        _MARGIN_L,
        _BODY_TOP,
        Inches(8.06),
        Inches(0.30),
        title,
        size_pt=12,
        bold=True,
        color=_COLOR_NAVY,
    )
    body = spec.adj_body or "\n".join(spec.observations[:2])
    _add_textbox(
        slide,
        _MARGIN_L,
        Inches(1.70),
        Inches(8.06),
        Inches(4.40),
        body,
        size_pt=11,
        bold=False,
        color=_COLOR_NAVY,
    )
    if spec.table and (spec.table.headers or spec.table.rows):
        _add_table(
            slide,
            spec.table,
            left=Inches(8.81),
            top=_BODY_TOP,
            width=Inches(4.08),
            height=Inches(3.20),
        )
    else:
        _obs_panel(
            slide,
            spec.observations[2:] or spec.observations,
            left=Inches(8.81),
            top=_BODY_TOP,
            width=Inches(4.08),
            height=Inches(4.80),
        )
    _chrome_footer(slide, spec)


def _layout_simple_table(
    slide,
    spec: SlideSpec,
    chrome: PptxChrome,
    *,
    default_title: str,
) -> None:
    _chrome_header(slide, spec, chrome)
    table = spec.table or SlideTable(headers=["Item", "Notes"], rows=[])
    if not table.title:
        table = table.model_copy(update={"title": default_title})
    grid_top = _add_table_title(
        slide,
        table,
        left=_MARGIN_L,
        top=_BODY_TOP,
        width=_CONTENT_W,
    )
    _add_table(
        slide,
        table,
        left=_MARGIN_L,
        top=grid_top,
        width=_CONTENT_W,
        height=Inches(4.80),
    )
    if spec.observations:
        # compact note under table area when present
        _add_multiline(
            slide,
            _MARGIN_L,
            Inches(6.40),
            _CONTENT_W,
            Inches(0.40),
            spec.observations[:2],
            size_pt=8,
            bullet=False,
            color=_COLOR_MUTED,
        )
    _chrome_footer(slide, spec)


def render_slide(prs: Presentation, spec: SlideSpec, chrome: PptxChrome | None = None):
    """Append one layout slide to ``prs`` and return the slide."""
    chrome = chrome or PptxChrome()
    blank = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[5]
    slide = prs.slides.add_slide(blank)
    layout = spec.layout
    if layout == "cover":
        _layout_cover(slide, spec)
    elif layout == "toc":
        _layout_toc(slide, spec, chrome)
    elif layout == "kpi_strip":
        _layout_kpi_strip(slide, spec, chrome)
    elif layout == "section_table_obs":
        _layout_section_table_obs(slide, spec, chrome)
    elif layout == "section_chart_obs":
        _layout_section_chart_obs(slide, spec, chrome)
    elif layout == "findings_rank":
        _layout_findings_rank(slide, spec, chrome)
    elif layout == "adj_detail":
        _layout_adj_detail(slide, spec, chrome)
    elif layout == "request_table":
        _layout_simple_table(slide, spec, chrome, default_title="Information requests")
    elif layout == "ledger_table":
        _layout_simple_table(slide, spec, chrome, default_title="Claims ledger")
    elif layout == "glossary":
        _layout_simple_table(slide, spec, chrome, default_title="Glossary")
    else:
        _layout_section_table_obs(slide, spec, chrome)
    return slide


def write_fdd_presentation(
    path: Path | str,
    slides: Sequence[SlideSpec],
    *,
    chrome: PptxChrome | None = None,
) -> Path:
    """Render typed SlideSpec layouts to a widescreen PPTX."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    chrome = chrome or PptxChrome()
    if not slides:
        render_slide(
            prs,
            SlideSpec(
                slide_id="empty",
                layout="cover",
                deal_name=chrome.project_label,
                engagement="Financial due diligence",
                basis_line="No slides in report_spec.",
            ),
            chrome,
        )
    else:
        for spec in slides:
            render_slide(prs, spec, chrome)
    prs.save(str(out))
    return out


def stub_pages_to_slides(
    pages: Sequence[StubRenderPage],
    *,
    chrome: PptxChrome | None = None,
    company: str = "",
) -> list[SlideSpec]:
    """Transitional adapter: legacy stub pages → chrome SlideSpecs (Phase B shell)."""
    chrome = chrome or PptxChrome()
    slides: list[SlideSpec] = []
    for i, page in enumerate(pages, start=1):
        title = (page.title or "").strip()
        body_lines = [ln.strip() for ln in (page.body or "").splitlines() if ln.strip()]
        lower = title.lower()
        if page.kind == "cover" or i == 1:
            entity = company or title.replace("FDD —", "").replace("FDD -", "").strip()
            slides.append(
                SlideSpec(
                    slide_id=f"cover_{i}",
                    layout="cover",
                    chapter="cover",
                    deal_name=chrome.project_label,
                    engagement="Financial due diligence",
                    entity_line=entity,
                    basis_line=chrome.basis_short,
                    page_no=i,
                )
            )
            continue
        if "agenda" in lower or "content" in lower:
            entries: list[TocEntry] = []
            for idx, line in enumerate(body_lines, start=1):
                clean = line.lstrip("•-* ").strip()
                if not clean:
                    continue
                entries.append(
                    TocEntry(number=f"{idx:02d}", title=clean, page=str(i + idx))
                )
            slides.append(
                SlideSpec(
                    slide_id=f"toc_{i}",
                    layout="toc",
                    chapter="contents",
                    banner="CONTENTS",
                    headline="Contents",
                    toc_entries=entries[:12],
                    page_no=i,
                )
            )
            continue
        headline = body_lines[0] if body_lines else title
        observations = body_lines[1:9] if len(body_lines) > 1 else body_lines[:6]
        slides.append(
            SlideSpec(
                slide_id=f"slide_{i}",
                layout="section_table_obs",
                chapter="es",
                banner=title.upper()[:48] or "FDD",
                headline=headline[:180],
                table=SlideTable(
                    title="Key figures",
                    headers=["Metric", "Value"],
                    rows=[],
                ),
                observations=observations,
                source="Approved databook exhibits for this run.",
                evidence_tier="B",
                page_no=i,
                figure_ids=[page.exhibit_id] if page.exhibit_id else [],
            )
        )
    return slides


def build_phase_b_fixture_slides(*, chrome: PptxChrome | None = None) -> list[SlideSpec]:
    """Hand-built ~8-slide fixture exercising every chrome layout contract."""
    chrome = chrome or PptxChrome(project_label="Project Crew")
    return [
        SlideSpec(
            slide_id="fix_cover",
            layout="cover",
            chapter="cover",
            deal_name="Project Crew",
            engagement="Financial due diligence",
            entity_line="Compost Crew Inc., A Benefit Corporation - Series B",
            basis_line="Basis: unaudited monthly management accounts. Draft for discussion.",
            date_line="23 October 2026",
            page_no=1,
        ),
        SlideSpec(
            slide_id="fix_toc",
            layout="toc",
            chapter="contents",
            banner="CONTENTS",
            headline="Contents",
            toc_entries=[
                TocEntry(number="01", title="Introduction", page="3"),
                TocEntry(number="02", title="Executive summary", page="4"),
                TocEntry(number="03", title="Transaction and business", page="8"),
                TocEntry(number="04", title="Quality of earnings", page="10"),
                TocEntry(number="05", title="Trading", page="16"),
                TocEntry(number="06", title="Cash flow", page="20"),
                TocEntry(number="07", title="Balance sheet, debt and leases", page="22"),
                TocEntry(number="08", title="Deal considerations", page="27"),
                TocEntry(number="09", title="Appendices", page="30"),
            ],
            page_no=2,
        ),
        SlideSpec(
            slide_id="fix_kpi",
            layout="kpi_strip",
            chapter="es",
            banner="EXECUTIVE SUMMARY",
            headline="Diligence EBITDA is $561k in FY25 and $502k for LTM Jul-26, half of FY24",
            kpis=[
                KpiTile(label="Revenue, LTM Jul-26", value="$13.6m", detail="FY25 growth 13.0%"),
                KpiTile(label="Diligence EBITDA, FY25", value="$561k", detail="Margin 4.2%"),
                KpiTile(label="Diligence EBITDA, LTM", value="$502k", detail="Margin 3.7%"),
                KpiTile(label="DC contract share, FY25", value="22.9%", detail="One-year firm term"),
                KpiTile(label="Cash, Jul-26", value="$2.33m", detail="Down since Dec-22"),
                KpiTile(label="Accrued Series A dividends", value="$407k", detail="Proposed debt-like"),
            ],
            table=SlideTable(
                title="Key figures ($k)",
                headers=["Metric", "FY24", "FY25"],
                rows=[
                    ["Revenue", "11,741", "13,282"],
                    ["Diligence EBITDA", "1,115", "561"],
                    ["EBITDA margin %", "9.5", "4.2"],
                ],
            ),
            observations=[
                "Earnings halved in FY25 as SG&A rose faster than revenue.",
                "Growth is concentrated in municipal / DC contract revenue.",
                "Cash funded dividends and debt service.",
            ],
            source="Monthly management accounts; Investor Workbook; Diligence analysis",
            evidence_tier="B",
            page_no=4,
        ),
        SlideSpec(
            slide_id="fix_findings",
            layout="findings_rank",
            chapter="es",
            banner="EXECUTIVE SUMMARY",
            headline="Ten findings ranked — earnings compression and contract concentration lead",
            findings=[
                FindingRankRow(rank="1", severity="High", title="EBITDA halved in FY25", detail="SG&A step-up"),
                FindingRankRow(rank="2", severity="High", title="DC contract concentration", detail="22.9% of revenue"),
                FindingRankRow(rank="3", severity="Moderate", title="Dividend arrears debt-like", detail="$407k"),
            ],
            source="Diligence analysis",
            evidence_tier="A/B/C",
            page_no=5,
        ),
        SlideSpec(
            slide_id="fix_qoe",
            layout="section_table_obs",
            chapter="qoe",
            banner="QUALITY OF EARNINGS",
            headline="Diligence EBITDA is $561k for FY25 after reversing management's bad-debt add-back",
            table=SlideTable(
                title="Quality of earnings summary ($k)",
                headers=["Bridge step", "FY25"],
                rows=[
                    ["Reported / management EBITDA", "572"],
                    ["Bad debt add-back reversed", "(11)"],
                    ["Diligence EBITDA", "561"],
                ],
            ),
            observations=[
                "One change to management's figure: bad debt stays a recurring cost.",
                "Tier B throughout from unaudited management accounts.",
            ],
            footnotes=[
                "Evidence for every row is tier B; nil rows are proposed for validation.",
                "Totals are computed from unrounded figures and may not add due to rounding.",
            ],
            source="Monthly management accounts; Diligence analysis",
            evidence_tier="B",
            page_no=10,
        ),
        SlideSpec(
            slide_id="fix_chart",
            layout="section_chart_obs",
            chapter="trading",
            banner="TRADING",
            headline="Municipal is 35.7% of FY25 revenue; the DC contract alone is 22.9%",
            chart_title="Revenue by stream ($k)",
            observations=[
                "Municipal revenue rose with DC contract billings.",
                "Commercial grew but active accounts fell.",
            ],
            source="Monthly P&L; Investor Workbook; Diligence analysis",
            evidence_tier="B/C",
            page_no=17,
        ),
        SlideSpec(
            slide_id="fix_adj",
            layout="adj_detail",
            chapter="qoe",
            banner="QUALITY OF EARNINGS",
            headline="ADJ-01 and ADJ-02: bad debt stays a cost; other revenue stays in, pending nature",
            adj_id="ADJ-01 / ADJ-02",
            adj_body=(
                "ADJ-01 Bad debt ($11k) — treat as recurring operating cost; reverse "
                "management add-back.\n\n"
                "ADJ-02 Other revenue ($143k) — retain in diligence EBITDA pending "
                "nature; show as downside sensitivity only."
            ),
            observations=[
                "No bridge movement beyond ADJ-01.",
                "Sensitivities remain grey / tier C.",
            ],
            source="Diligence analysis",
            evidence_tier="B/C",
            page_no=13,
        ),
        SlideSpec(
            slide_id="fix_requests",
            layout="request_table",
            chapter="deal",
            banner="DEAL CONSIDERATIONS",
            headline="Information requests — high-priority items led by audited accounts and DC contract",
            table=SlideTable(
                title="Information requests",
                headers=["ID", "Priority", "Request"],
                rows=[
                    ["R01", "High", "Audited or reviewed financial statements"],
                    ["R03", "High", "Series A charter / dividend terms"],
                    ["R05", "High", "Schedule of all leases and site agreements"],
                ],
            ),
            source="Diligence analysis",
            evidence_tier="A/B",
            page_no=28,
        ),
        SlideSpec(
            slide_id="fix_ledger",
            layout="ledger_table",
            chapter="appendix",
            banner="APPENDICES",
            headline="Claims ledger: agent claims tested against the databook",
            table=SlideTable(
                title="Claims ledger",
                headers=["Claim", "Metric", "Period", "Result"],
                rows=[
                    ["cl_001", "revenue", "FY2025", "contradicted"],
                    ["cl_002", "ebitda", "FY2025", "agrees"],
                ],
            ),
            source="Diligence analysis",
            page_no=30,
        ),
        SlideSpec(
            slide_id="fix_glossary",
            layout="glossary",
            chapter="appendix",
            banner="APPENDICES",
            headline="Glossary",
            table=SlideTable(
                title="Glossary",
                headers=["Term", "Definition"],
                rows=[
                    ["QoE", "Quality of earnings; normalisation of reported earnings"],
                    ["LTM", "Last twelve months"],
                    ["NWC", "Net working capital"],
                ],
            ),
            source="Diligence analysis",
            page_no=37,
        ),
    ]


def slide_chrome_inventory(path: Path | str) -> list[dict[str, Any]]:
    """Test helper: extract key chrome strings from a rendered PPTX."""
    prs = Presentation(str(path))
    out: list[dict[str, Any]] = []
    for i, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        tables = 0
        for shape in slide.shapes:
            if shape.has_table:
                tables += 1
            if shape.has_text_frame:
                for p in shape.text_frame.paragraphs:
                    t = (p.text or "").strip()
                    if t:
                        texts.append(t)
        blob = "\n".join(texts)
        out.append(
            {
                "page": i,
                "tables": tables,
                "has_observations": "Observations" in blob,
                "has_source": "Source:" in blob or "Source :" in blob,
                "has_evidence": "Evidence" in blob,
                "texts": texts[:12],
            }
        )
    return out
