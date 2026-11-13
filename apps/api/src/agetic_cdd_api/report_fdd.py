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
from agetic_cdd_api.services_fdd_report_pdf import write_fdd_findings_pdf
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


def _write_fdd_pdf(
    *,
    path,
    title: str,
    company: str,
    pages: list[StubRenderPage],
    figures: dict[str, Any],
    findings_counts: dict[str, int] | None = None,
    top_findings: list[dict[str, Any]] | None = None,
) -> None:
    """Landscape findings-report PDF matching Compost Crew Latest formatting."""
    write_fdd_findings_pdf(
        path=path,
        title=title,
        company=company,
        pages=pages,
        figures=figures,
        findings_counts=findings_counts,
        top_findings=top_findings,
    )


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
            f"DiligenceIQ · {len(pages)} section(s) · {len(figures)} shared figure(s)"
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
        "Figures are taken from the approved databook exhibits; "
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
        PptxInches(12.1),
        PptxInches(3.2),
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


_DECK_WIDTH = PptxInches(13.333)
_DECK_HEIGHT = PptxInches(7.5)
_DECK_CONTENT_WIDTH = PptxInches(12.1)


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
        PptxInches(0.6), PptxInches(0.35), _DECK_CONTENT_WIDTH, PptxInches(0.7)
    )
    tf = box.text_frame
    p = tf.paragraphs[0]
    p.text = page.title
    p.font.size = PptxPt(28 if is_title else 20)
    p.font.bold = True

    has_chart = False
    if page.exhibit_id and store is not None:
        ex = _exhibits_by_id(store).get(page.exhibit_id)
        if ex is not None:
            has_chart = _add_labelled_chart(slide, ex)

    body_h = 2.0 if has_chart else 5.4
    body_box = slide.shapes.add_textbox(
        PptxInches(0.6), PptxInches(1.15), _DECK_CONTENT_WIDTH, PptxInches(body_h)
    )
    btf = body_box.text_frame
    btf.word_wrap = True
    first = True
    max_lines = 4 if has_chart else 10
    body_lines = _slide_body_lines(page.body or "", max_content=max_lines)
    for idx, line in enumerate(body_lines):
        para = btf.paragraphs[0] if first else btf.add_paragraph()
        first = False
        para.text = line
        # Hierarchy: first line = takeaway, rest = supporting.
        if idx == 0:
            para.font.size = PptxPt(16)
            para.font.bold = True
        else:
            para.font.size = PptxPt(13)
        para.space_after = PptxPt(4)
    return slide


def _write_fdd_pptx(
    *,
    path,
    title: str,
    pages: list[StubRenderPage],
    figures: dict[str, Any],
    store: ExhibitStoreDoc | None = None,
    product_label: str = "FDD Report",
    company: str = "",
    use_chrome: bool = True,
) -> None:
    """Write widescreen PPTX. FDD Report uses Phase B chrome layouts by default."""
    if use_chrome:
        from agetic_cdd_api.fdd_schemas import PptxChrome
        from agetic_cdd_api.services_fdd_pptx import (
            stub_pages_to_slides,
            write_fdd_presentation,
        )

        from agetic_cdd_api.services_fdd_chapters import resolve_project_label

        chrome = PptxChrome(
            project_label=resolve_project_label(company=company or title),
            basis_short="Draft for discussion - unaudited basis",
        )
        slides = stub_pages_to_slides(pages, chrome=chrome, company=company or title)
        if not slides:
            slides = stub_pages_to_slides(
                [StubRenderPage(title=title, body="No slides in report_spec.", kind="cover")],
                chrome=chrome,
                company=company or title,
            )
        write_fdd_presentation(path, slides, chrome=chrome)
        return

    # Legacy IC-deck path (deprecated builder).
    prs = Presentation()
    prs.slide_width = _DECK_WIDTH
    prs.slide_height = _DECK_HEIGHT
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
            PptxInches(0.6), PptxInches(7.0), _DECK_CONTENT_WIDTH, PptxInches(0.35)
        )
        fp = foot.text_frame.paragraphs[0]
        fp.text = (
            f"{product_label} · {len(pages)} slide(s) · "
            f"{len(figures)} shared figure(s) · widescreen"
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


def _published_pages(ctx: BuildContext) -> list[dict[str, Any]]:
    from agetic_cdd_api.services_published_pages import pages_for_deal

    return pages_for_deal(ctx.deal_slug)


def _published_sections(pages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for page in pages:
        figures = {row["fact_id"]: row["value"] for row in page["figures"]}
        yield _evt(
            "section",
            _published_caption(page),
            schedule_id=page["schedule_id"],
            renders=page["renders"],
            figures=figures,
            fact_ids=list(figures),
        )


def _published_caption(page: dict[str, Any]) -> str:
    label = {"rent": "Rent", "revenue_and_costs": "Revenue and costs", "debt": "Debt"}.get(page["renders"], page["schedule_id"])
    return f"{page['schedule_id']} · {label}"


def _export_published(ctx: BuildContext, pages: list[dict[str, Any]], report_type: str, filename: str) -> str:
    """Export published databook pages. FDD types are forced to PPTX (Phase F)."""
    out_dir = report_artifact_dir(ctx.deal_slug, report_type)
    # FDD Report / deprecated deck alias: never emit Word/PDF from published pages.
    if report_type in {"fdd_report", "fdd_deck"} and not filename.endswith(".pptx"):
        filename = Path(filename).with_suffix(".pptx").name
    path = out_dir / filename
    if filename.endswith(".pptx"):
        _write_published_pptx(path, pages)
    else:
        _write_published_docx(path, pages)
    return _artifact_relpath(path, ctx.deal_slug)


def _export_chapter_pptx(
    ctx: BuildContext,
    *,
    report_type: str,
    filename: str,
    product_label: str,
) -> str:
    """Shared chaptered FDD PPTX export used by fdd_report and deprecated fdd_deck.

    Prefer assembled chapter slides. Published-page title stubs are a last resort
    only when no FDD chapter pack exists yet.
    """
    ctx.pdf_artifact_path = None
    out_dir = report_artifact_dir(ctx.deal_slug, report_type)
    path = out_dir / filename
    manifest, store, spec, rendered = _cached_bundle_and_render(ctx, kind="deck")
    chapter_slides = list(getattr(spec, "slides", None) or [])
    if chapter_slides:
        from agetic_cdd_api.services_fdd_chapters import default_chrome
        from agetic_cdd_api.services_fdd_pptx import write_fdd_presentation

        write_fdd_presentation(
            path,
            chapter_slides,
            chrome=default_chrome(company=_company(ctx)),
        )
        _side_json(path, manifest=manifest, rendered=rendered)
        return _artifact_relpath(path, ctx.deal_slug)

    pages = _published_pages(ctx)
    if pages:
        return _export_published(ctx, pages, report_type, filename)

    _write_fdd_pptx(
        path=path,
        title=spec.title,
        pages=rendered.pages,
        figures=rendered.figures,
        store=store,
        product_label=product_label,
        company=_company(ctx),
        use_chrome=True,
    )
    _side_json(path, manifest=manifest, rendered=rendered)
    return _artifact_relpath(path, ctx.deal_slug)


def _write_published_docx(path: Path, pages: list[dict[str, Any]]) -> None:
    document = Document()
    for page in pages:
        document.add_heading(_published_caption(page), level=1)
        for row in page["figures"]:
            document.add_paragraph(f"{row['fact_id']} {row['concept_id']} {row['value']}")
    document.save(str(path))


def _write_published_pptx(path: Path, pages: list[dict[str, Any]]) -> None:
    presentation = Presentation()
    for page in pages:
        slide = presentation.slides.add_slide(presentation.slide_layouts[5])
        slide.shapes.title.text = _published_caption(page)
    presentation.save(str(path))


class FddReportBuilder(ReportBuilder):
    """PPTX-only FDD Report from the shared Phase 7 report_spec (slide render).

    Phase A cutover: no DOCX/PDF twin. Uses the deck slide nodes until chaptered
    PPTX parity (Phases B–D) replaces the shell layouts.
    """

    report_type = "fdd_report"

    def build_sections(self, ctx: BuildContext) -> Iterator[dict[str, Any]]:
        pages = _published_pages(ctx)
        if pages:
            yield from _published_sections(pages)
            return
        # PPTX uses chaptered SlideSpecs (Phase C); deck render keeps shared figures.
        manifest, _store, spec, rendered = _cached_bundle_and_render(ctx, kind="deck")
        n_figs = len(rendered.figures)
        n_chapter = len(getattr(spec, "slides", None) or [])
        n_comment = sum(
            1 for n in spec.nodes if n.node_id.startswith("slide_ch_")
        )
        yield _evt(
            "section",
            f"FDD report · {n_chapter or len(rendered.pages)} chapter slide(s) · "
            f"{n_comment} commentary slide(s) · run {manifest.run_id} · "
            f"{n_figs} shared figure(s)",
            run_id=manifest.run_id,
            figures=rendered.figures,
            page_count=n_chapter or len(rendered.pages),
            slide_count=n_chapter or len(rendered.pages),
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
        # Never emit a PDF twin for the FDD Report.
        return _export_chapter_pptx(
            ctx,
            report_type="fdd_report",
            filename=f"{_safe_name(_company(ctx), ctx.deal_slug)}_FDD_Report.pptx",
            product_label="FDD Report",
        )


class FddDeckBuilder(FddReportBuilder):
    """Deprecated API alias — same chaptered PPTX as ``fdd_report`` (Phase F)."""

    report_type = "fdd_deck"

    def export_artifact(self, ctx: BuildContext) -> str:
        return _export_chapter_pptx(
            ctx,
            report_type="fdd_deck",
            filename=f"{_safe_name(_company(ctx), ctx.deal_slug)}_FDD_Deck.pptx",
            product_label="FDD Report",
        )


register_builder("fdd_report", FddReportBuilder)
register_builder("fdd_deck", FddDeckBuilder)
