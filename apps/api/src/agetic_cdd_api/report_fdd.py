"""FDD report + deck builders — Phase 7 dual-render from one assembled report_spec."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Inches as PptxInches
from pptx.util import Pt as PptxPt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from agetic_cdd_api.report_builder_base import BuildContext, ReportBuilder, _evt
from agetic_cdd_api.report_store import report_artifact_dir
from agetic_cdd_api.routers_reports import register_builder
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import (
    Exhibit,
    ExhibitStoreDoc,
    StubRenderPage,
    StubRenderResult,
)
from agetic_cdd_api.services_fdd_render import ensure_phase0_run, render_stub
from agetic_cdd_api.services_fdd_tokens import display_unit_for_cell

_SAFE_NAME_MAX = 100
_CACHE_ATTR = "_fdd_render_cache"
_MUTED = RGBColor(0x55, 0x55, 0x55)
_CHART_METRICS = (
    "revenue",
    "gross_profit",
    "ebitda",
    "adjusted_ebitda",
    "operating_cash_flow",
    "free_cash_flow",
    "net_debt",
    "nwc",
)
# Costs exhibit (ex_m3 / ex_db_costs) — prefer cost lines over revenue-only.
_COST_CHART_METRICS = (
    "cogs",
    "sga",
    "labor_cost",
    "labour_cost",
    "revenue",
    "headcount",
)
def _safe_name(raw: str, slug: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", raw).strip().replace(" ", "_")
    cleaned = (cleaned or slug)[:_SAFE_NAME_MAX]
    return cleaned or slug[:_SAFE_NAME_MAX]


def _company(ctx: BuildContext) -> str:
    from agetic_cdd_api.services_accounts_extract import is_placeholder_company
    from agetic_cdd_api.services_fdd_scope import _resolve_scope_entity

    if ctx.profile and ctx.profile.company:
        if not is_placeholder_company(ctx.profile.company, ctx.deal_slug):
            return ctx.profile.company
    return _resolve_scope_entity(
        ctx.deal_slug,
        ctx.profile.company if ctx.profile else None,
    )


def _ensure_bundle(ctx: BuildContext):
    """Load/create FDD run, bridge current databook, assemble Phase 7 report_spec."""
    return ensure_phase0_run(
        ctx.deal_slug,
        company=_company(ctx),
        bridge_databook=True,
        prefer_current_release=True,
    )


def _cached_bundle_and_render(
    ctx: BuildContext, *, kind: str
) -> tuple[Any, Any, Any, StubRenderResult]:
    """Run ensure + render once per generate(); reuse when content_hash is unchanged."""
    cache: dict[str, Any] = getattr(ctx, _CACHE_ATTR, None) or {}
    setattr(ctx, _CACHE_ATTR, cache)

    bundle = cache.get("bundle")
    if bundle is None:
        bundle = _ensure_bundle(ctx)
        cache["bundle"] = bundle
    manifest, store, spec = bundle

    renders: dict[str, tuple[str, StubRenderResult]] = cache.setdefault("renders", {})
    cached = renders.get(kind)
    if cached is not None:
        prev_hash, rendered = cached
        if prev_hash == spec.content_hash:
            return manifest, store, spec, rendered

    rendered = render_stub(kind=kind, spec=spec, store=store)
    renders[kind] = (spec.content_hash, rendered)
    return manifest, store, spec, rendered


def _artifact_relpath(path: Path, deal_slug: str) -> str:
    deal_root = deals_mod.deals_root() / deal_slug
    try:
        return str(path.relative_to(deal_root))
    except ValueError:
        return str(path)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _write_fdd_pdf(
    *,
    path,
    title: str,
    pages: list[StubRenderPage],
    figures: dict[str, Any],
) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FddTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=14,
    )
    page_title = ParagraphStyle(
        "FddPageTitle",
        parent=styles["Heading2"],
        fontSize=13,
        spaceAfter=10,
        spaceBefore=4,
    )
    body_style = ParagraphStyle(
        "FddBody",
        parent=styles["BodyText"],
        fontSize=10,
        leading=13,
        spaceAfter=6,
    )
    foot_style = ParagraphStyle(
        "FddFoot",
        parent=styles["Normal"],
        fontSize=8,
        textColor="#555555",
    )
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story: list[Any] = []
    if not pages:
        story.append(Paragraph(_escape(title), title_style))
        story.append(Paragraph("No pages in report_spec.", body_style))
    else:
        for i, page in enumerate(pages):
            if i:
                story.append(PageBreak())
            if page.kind == "cover":
                story.append(Paragraph(_escape(title), title_style))
                story.append(Spacer(1, 10))
            else:
                story.append(Paragraph(_escape(page.title), page_title))
            body = page.body or ""
            chunks = body.split("\n\n") if "\n\n" in body else [body]
            for chunk in chunks:
                if not chunk.strip():
                    continue
                for line in chunk.split("\n"):
                    if not line.strip():
                        story.append(Spacer(1, 4))
                        continue
                    story.append(Paragraph(_escape(line), body_style))
    fig_bits = ", ".join(f"{k}={v}" for k, v in sorted(figures.items())[:12])
    extra = len(figures) - 12
    if extra > 0:
        fig_bits = f"{fig_bits}, …(+{extra})"
    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            f"FDD report · {len(pages)} page(s) · shared figures: {fig_bits or '—'} "
            f"· sources on exhibit cells",
            foot_style,
        )
    )
    doc.build(story)


def _write_fdd_docx(
    *,
    path,
    title: str,
    company: str,
    pages: list[StubRenderPage],
    figures: dict[str, Any],
) -> None:
    """Word report from the same resolved pages as the PDF (AS-5)."""
    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.85)
        section.bottom_margin = Inches(0.85)
        section.left_margin = Inches(0.95)
        section.right_margin = Inches(0.95)
        header = section.header
        header.is_linked_to_previous = False
        hp = header.paragraphs[0]
        hp.text = ""
        run = hp.add_run(f"FDD Report | {company}")
        run.font.size = Pt(8)
        run.font.color.rgb = _MUTED
        run2 = hp.add_run("\tStrictly Private & Confidential")
        run2.font.size = Pt(8)
        run2.font.bold = True
        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0]
        fp.text = ""
        fr = fp.add_run(
            f"Agentic CDD · {len(pages)} section(s) · {len(figures)} shared figure(s)"
        )
        fr.font.size = Pt(8)
        fr.font.color.rgb = _MUTED

    if not pages:
        h = doc.add_heading(title, level=0)
        h.alignment = WD_ALIGN_PARAGRAPH.LEFT
        doc.add_paragraph("No pages in report_spec.")
    else:
        for i, page in enumerate(pages):
            if i == 0 or page.kind == "cover":
                heading = doc.add_heading(title if page.kind == "cover" else page.title, level=0)
                heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
            else:
                doc.add_heading(page.title, level=1)
            for line in (page.body or "").split("\n"):
                text = line.strip()
                if not text:
                    doc.add_paragraph("")
                    continue
                if text.startswith(("•", "-", "*")):
                    p = doc.add_paragraph(text.lstrip("•-* ").strip(), style="List Bullet")
                else:
                    p = doc.add_paragraph(text)
                for run in p.runs:
                    run.font.size = Pt(10)
            if i < len(pages) - 1:
                doc.add_page_break()

    note = doc.add_paragraph()
    nr = note.add_run(
        "Figures resolve from the exhibit store via number tokens; "
        "negatives in brackets; one currency/scale per exhibit."
    )
    nr.font.size = Pt(8)
    nr.font.color.rgb = _MUTED
    nr.font.italic = True
    doc.save(str(path))


def _slide_body_lines(body: str, *, max_content: int = 8) -> list[str]:
    """Strip lines for PPTX; keep one structural blank between blocks; cap content."""
    lines: list[str] = []
    non_empty = 0
    for raw in (body or "").split("\n"):
        stripped = raw.strip()
        if stripped:
            lines.append(stripped)
            non_empty += 1
            if non_empty >= max_content:
                break
        elif lines and lines[-1] != "":
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines or ["—"]


def _fy_axis_label(year: int) -> str:
    """Closed years use A. Incomplete / plan years are not charted with A/E."""
    from datetime import date

    closed_cutoff = date.today().year - 1
    suffix = "A" if int(year) <= closed_cutoff else "E"
    return f"FY{int(year) % 100:02d}{suffix}"


def _chart_closed_cutoff() -> int:
    from datetime import date

    return date.today().year - 1


def _chart_metric_order(ex: Exhibit) -> tuple[str, ...]:
    eid = (ex.exhibit_id or "").lower()
    if "cost" in eid or eid.endswith("_m3_costs"):
        return _COST_CHART_METRICS
    return _CHART_METRICS


def _chart_series_from_exhibit(
    ex: Exhibit,
) -> tuple[list[str], list[tuple[str, list[float]]], str] | None:
    """Build (categories, series, value_axis_title) for multi-year exhibits.

    Years are the intersection across plotted series (no zero-fill phantoms).
    Only closed fiscal years are plotted — YTD / stub outer years (FY26E) are
    omitted so partial pack months are not shown beside full years.
    """
    by_metric: dict[str, dict[int, float]] = defaultdict(dict)
    unit_guess = ""
    closed = _chart_closed_cutoff()
    for cell in ex.cells:
        if cell.value is None or cell.fiscal_year is None:
            continue
        year = int(cell.fiscal_year)
        if year > closed:
            continue
        mk = (cell.metric_key or "").strip().lower()
        if not mk or mk.endswith("_pct") or "margin" in mk or "yoy" in mk:
            continue
        # Skip YTD / incomplete periods when stamped on the cell.
        basis = (cell.basis_label or cell.label or "").upper()
        if "YTD" in basis:
            continue
        by_metric[mk][year] = float(cell.value)
        if not unit_guess:
            unit_guess = display_unit_for_cell(cell) or ""

    preferred = [m for m in _chart_metric_order(ex) if m in by_metric]
    candidates = preferred or sorted(
        m for m, ys in by_metric.items() if len(ys) >= 2
    )
    # Keep series that share ≥2 years with the primary metric.
    picked: list[str] = []
    for mk in candidates:
        if len(by_metric[mk]) < 2:
            continue
        picked.append(mk)
        if len(picked) >= 3:
            break
    if len(picked) < 1:
        return None

    year_sets = [set(by_metric[mk]) for mk in picked]
    years = sorted(set.intersection(*year_sets)) if len(year_sets) > 1 else sorted(year_sets[0])
    # Drop sparse leading years that only one metric carried before intersection
    # collapsed — require ≥2 points.
    if len(years) < 2 and picked:
        # Fall back to primary metric years only (single series).
        years = sorted(by_metric[picked[0]])
        picked = picked[:1]
    if len(years) < 2:
        return None

    series: list[tuple[str, list[float]]] = []
    for mk in picked:
        # Round to 3 d.p. so float noise never appears in chart data labels.
        vals = [round(by_metric[mk][y], 3) for y in years]  # no zero-fill
        label = mk.replace("_", " ").title()
        if mk in {"cogs", "cost_of_sales"}:
            label = "Cost of sales"
        elif mk in {"sga", "operating_costs", "operating_expenses"}:
            label = "SG&A"
        elif mk in {"labor_cost", "labour_cost"}:
            label = "Labour"
        series.append((label, vals))

    cats = [_fy_axis_label(y) for y in years]
    axis = unit_guess or (ex.scale_header or "Value")
    return cats, series, axis


def _add_labelled_chart(slide, ex: Exhibit) -> bool:
    """AS-7 — column chart with labelled Period / value axes when multi-year."""
    built = _chart_series_from_exhibit(ex)
    if built is None:
        return False
    cats, series, axis_title = built
    chart_data = CategoryChartData()
    chart_data.categories = cats
    for name, vals in series:
        chart_data.add_series(name, vals)

    graphic = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        PptxInches(0.6),
        PptxInches(3.4),
        PptxInches(8.5),
        PptxInches(3.0),
        chart_data,
    )
    chart = graphic.chart
    chart.has_legend = len(series) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False

    cat_axis = chart.category_axis
    cat_axis.has_title = True
    cat_axis.axis_title.text_frame.paragraphs[0].text = "Period"
    cat_axis.axis_title.text_frame.paragraphs[0].font.size = PptxPt(10)

    val_axis = chart.value_axis
    val_axis.has_title = True
    val_axis.axis_title.text_frame.paragraphs[0].text = axis_title[:40]
    val_axis.axis_title.text_frame.paragraphs[0].font.size = PptxPt(10)
    val_axis.has_major_gridlines = True
    return True


def _exhibits_by_id(store: ExhibitStoreDoc | None) -> dict[str, Exhibit]:
    if store is None:
        return {}
    return {ex.exhibit_id: ex for ex in store.exhibits}


def _add_slide(
    prs: Presentation,
    page: StubRenderPage,
    *,
    is_title: bool,
    store: ExhibitStoreDoc | None = None,
):
    layout = prs.slide_layouts[5]  # blank
    slide = prs.slides.add_slide(layout)
    box = slide.shapes.add_textbox(
        PptxInches(0.6), PptxInches(0.35), PptxInches(8.5), PptxInches(0.7)
    )
    tf = box.text_frame
    p = tf.paragraphs[0]
    p.text = page.title
    p.font.size = PptxPt(26 if is_title else 18)
    p.font.bold = True

    has_chart = False
    if page.exhibit_id and store is not None:
        ex = _exhibits_by_id(store).get(page.exhibit_id)
        if ex is not None:
            has_chart = _add_labelled_chart(slide, ex)

    body_h = 2.0 if has_chart else 5.2
    body_box = slide.shapes.add_textbox(
        PptxInches(0.6), PptxInches(1.15), PptxInches(8.5), PptxInches(body_h)
    )
    btf = body_box.text_frame
    btf.word_wrap = True
    first = True
    max_lines = 4 if has_chart else 8
    for line in _slide_body_lines(page.body or "", max_content=max_lines):
        para = btf.paragraphs[0] if first else btf.add_paragraph()
        first = False
        para.text = line
        para.font.size = PptxPt(14 if is_title else 12)
        para.space_after = PptxPt(4)
    return slide


def _write_fdd_pptx(
    *,
    path,
    title: str,
    pages: list[StubRenderPage],
    figures: dict[str, Any],
    store: ExhibitStoreDoc | None = None,
) -> None:
    prs = Presentation()
    last_slide = None
    if not pages:
        last_slide = _add_slide(
            prs,
            StubRenderPage(title=title, body="No slides in report_spec.", kind="slide"),
            is_title=True,
            store=store,
        )
    else:
        for i, page in enumerate(pages):
            last_slide = _add_slide(
                prs,
                page,
                is_title=(i == 0 or page.kind == "cover"),
                store=store,
            )

    if last_slide is not None:
        foot = last_slide.shapes.add_textbox(
            PptxInches(0.6), PptxInches(6.6), PptxInches(8.5), PptxInches(0.4)
        )
        fp = foot.text_frame.paragraphs[0]
        fp.text = (
            f"FDD IC deck · {len(pages)} slide(s) · "
            f"{len(figures)} shared figure(s) · identical to report · "
            "chart axes labelled Period / scale"
        )
        fp.font.size = PptxPt(9)

    prs.save(str(path))


def _side_json(path, *, manifest, rendered: StubRenderResult) -> None:
    side = path.parent / f"{path.stem}_figures.json"
    side.write_text(
        json.dumps(
            {
                "run_id": manifest.run_id,
                "kind": rendered.kind,
                "figures": rendered.figures,
                "displays": rendered.displays,
                "content_hash": rendered.content_hash,
                "page_count": len(rendered.pages),
                "pages": [p.model_dump(mode="json") for p in rendered.pages],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


class FddReportBuilder(ReportBuilder):
    """DOCX (+ PDF twin) driven by the shared Phase 7 FDD report_spec."""

    report_type = "fdd_report"

    def build_sections(self, ctx: BuildContext) -> Iterator[dict[str, Any]]:
        manifest, _store, spec, rendered = _cached_bundle_and_render(ctx, kind="report")
        n_figs = len(rendered.figures)
        n_comment = sum(
            1 for n in spec.nodes if n.node_id.startswith("sec_comment_")
        )
        yield _evt(
            "section",
            f"FDD report · {len(rendered.pages)} page(s) · {n_comment} commentary "
            f"section(s) · run {manifest.run_id} · {n_figs} shared figure(s)",
            run_id=manifest.run_id,
            figures=rendered.figures,
            page_count=len(rendered.pages),
            commentary_sections=n_comment,
        )
        if manifest.draft_mode:
            yield _evt(
                "validation",
                "draft_mode=true — databook contract incomplete; G6 blocked",
                contract_reasons=manifest.contract_reasons[:8],
                g6_blocked=manifest.g6_blocked,
            )
        else:
            yield _evt(
                "validation",
                f"databook contract complete · release {manifest.databook_release_id}",
            )

    def export_artifact(self, ctx: BuildContext) -> str:
        manifest, _store, spec, rendered = _cached_bundle_and_render(ctx, kind="report")
        out_dir = report_artifact_dir(ctx.deal_slug, "fdd_report")
        base = _safe_name(_company(ctx), ctx.deal_slug)
        docx_path = out_dir / f"{base}_FDD_Report.docx"
        pdf_path = out_dir / f"{base}_FDD_Report.pdf"
        _write_fdd_docx(
            path=docx_path,
            title=spec.title,
            company=_company(ctx),
            pages=rendered.pages,
            figures=rendered.figures,
        )
        _write_fdd_pdf(
            path=pdf_path,
            title=spec.title,
            pages=rendered.pages,
            figures=rendered.figures,
        )
        _side_json(docx_path, manifest=manifest, rendered=rendered)
        return _artifact_relpath(docx_path, ctx.deal_slug)


class FddDeckBuilder(ReportBuilder):
    """PPTX driven by the same Phase 7 FDD report_spec + exhibit store."""

    report_type = "fdd_deck"

    def build_sections(self, ctx: BuildContext) -> Iterator[dict[str, Any]]:
        manifest, _store, spec, rendered = _cached_bundle_and_render(ctx, kind="deck")
        n_comment = sum(
            1 for n in spec.nodes if n.node_id.startswith("slide_comment_")
        )
        yield _evt(
            "section",
            f"FDD deck · {len(rendered.pages)} slide(s) · {n_comment} commentary "
            f"slide(s) · run {manifest.run_id} · {len(rendered.figures)} shared figure(s)",
            run_id=manifest.run_id,
            figures=rendered.figures,
            slide_count=len(rendered.pages),
            commentary_sections=n_comment,
        )

    def export_artifact(self, ctx: BuildContext) -> str:
        manifest, store, spec, rendered = _cached_bundle_and_render(ctx, kind="deck")
        out_dir = report_artifact_dir(ctx.deal_slug, "fdd_deck")
        filename = f"{_safe_name(_company(ctx), ctx.deal_slug)}_FDD_Deck.pptx"
        path = out_dir / filename
        _write_fdd_pptx(
            path=path,
            title=spec.title,
            pages=rendered.pages,
            figures=rendered.figures,
            store=store,
        )
        _side_json(path, manifest=manifest, rendered=rendered)
        return _artifact_relpath(path, ctx.deal_slug)


register_builder("fdd_report", FddReportBuilder)
register_builder("fdd_deck", FddDeckBuilder)
