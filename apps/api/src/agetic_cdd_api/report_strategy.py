"""Strategy Report builder — consulting-grade .docx from Foundation / DD / Verdict stores.

Live DiligenceIQ storyline (3 sections):
  1.0 Deal Framing & Scope
  2.0 Company & Management
  3.0 Legal, IP & ESG

Layout parity targets (gap-close):
  cover + TOC + section divider pages · Insight callouts · Agent/Source tables
  · cleaned framing/ESG harvest (no deal-specific hardcoding).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from agetic_cdd_api.report_builder_base import BuildContext, ReportBuilder, _evt, _recover_legal_name, sanitize_report_prose
from agetic_cdd_api.report_store import report_artifact_dir
from agetic_cdd_api.report_storyline import StorylineSection
from agetic_cdd_api.routers_reports import register_builder
from agetic_cdd_api.services_deals import deals_root, resolve_sector, sector_label

# Agent key aliases: storyline / live slugs → our output filenames
_AGENT_ALIASES: dict[str, tuple[str, ...]] = {
    "recommendations": ("recommendation", "recommendations"),
    "recommendation": ("recommendation", "recommendations"),
    "executive_summary": ("executive_summary", "ic_synthesis"),
    "final_valuation_range": ("valuation_modeling", "final_valuation_range"),
    "valuation_model": ("valuation_modeling", "valuation_model"),
    "appendices": ("appendices", "scope_and_methodology"),
}

_NAVY = RGBColor(0x1F, 0x38, 0x64)
_SLATE = RGBColor(0x4B, 0x55, 0x63)
_MUTED = RGBColor(0x6B, 0x72, 0x80)
_ACCENT = RGBColor(0xC2, 0x41, 0x0C)  # orange-red confidentiality accent
_INSIGHT_BG = "E8EEF7"
_COVER_BG = "1F3864"
_STATUS_CONFIRMED = "CONFIRMED"
_STATUS_ASSUMED = "ASSUMED"
_STATUS_CONFIRMED_COLOR = RGBColor(0x15, 0x80, 0x3D)
_STATUS_ASSUMED_COLOR = RGBColor(0xB4, 0x53, 0x09)
_NOT_DOCUMENTED = "Not documented — requires management confirmation"

# Phrases that indicate CIM/table paste rather than discrete diligence findings.
# Generic patterns only — no deal/company names.
_NOISE_MARKERS = (
    "parameter details",
    "governing body status risk",
    "insight snapshot",
    "due diligence scope this due diligence package",
    "executive summary investment overview",
    "companies act compliance mca",
    "model launch range (km)",
    "corporate overview company profile",
    "regulatory area governing body",
    "key legal risks & litigation",
    "sebi lodr",
    "gst filing gstn",
    "technical due diligence software",
    "technology stack assessment",
    "vehicle os (moveos) linux-based",
)
_NOISE_PREFIX_RE = re.compile(r"^0\s+\d+\s+")
_META_FINDING_RE = re.compile(
    r"^(target|deal\s*/\s*strategy|sector|industry)\s*:|"
    r"\d+\s+file\(s\)|"
    r"^deal\s*/\s*strategy\b",
    re.I,
)


def _resolve_agent(ctx: BuildContext, key: str) -> dict[str, Any]:
    candidates = _AGENT_ALIASES.get(key, (key,))
    for cand in candidates:
        data = ctx.agent_outputs.get(cand)
        if isinstance(data, dict) and data:
            return data
    data = ctx.agent_outputs.get(key)
    return data if isinstance(data, dict) else {}


def _spec(agent: dict[str, Any]) -> dict[str, Any]:
    s = agent.get("spec")
    return s if isinstance(s, dict) else {}


def _agent_name(agent: dict[str, Any], fallback: str = "-") -> str:
    return str(agent.get("agentName") or agent.get("agent_key") or fallback)


def _agent_sources(agent: dict[str, Any], limit: int = 2) -> str:
    files: list[str] = []
    seen: set[str] = set()
    for s in agent.get("sources") or []:
        if isinstance(s, str) and s not in seen:
            seen.add(s)
            files.append(s)
    for s in _spec(agent).get("sources") or []:
        if isinstance(s, str) and s not in seen:
            seen.add(s)
            files.append(s)
    if not files:
        return "-"
    return ", ".join(files[:limit]) + ("…" if len(files) > limit else "")


def _company(ctx: BuildContext) -> str:
    if ctx.profile and ctx.profile.company:
        return ctx.profile.company
    return ctx.deal_slug


def _sector(ctx: BuildContext) -> str:
    if ctx.profile and ctx.profile.sector:
        return sector_label(resolve_sector(str(ctx.profile.sector)))
    return sector_label("generic")


# ---------------------------------------------------------------------------
# Text cleaning / noise filters (logic-driven, no deal hardcoding)
# ---------------------------------------------------------------------------

def _clean_prose(text: str, max_chars: int = 1200, *, company: str | None = None) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = t.replace("\x7f", " ").replace("■", " ").replace("", " ")
    t = sanitize_report_prose(t, company=company)
    if len(t) > max_chars:
        t = t[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return t


def _is_noisy(text: str) -> bool:
    """True when text looks like pasted CIM/table dump rather than a finding."""
    raw = (text or "").strip()
    if len(raw) < 12:
        return False
    if _NOISE_PREFIX_RE.match(raw):
        return True
    t = raw.lower()
    if any(m in t for m in _NOISE_MARKERS):
        return True
    # Jammed status tables
    if t.count(" compliant") >= 2 and ("risk level" in t or "governing" in t):
        return True
    # Long run-on without sentence structure
    if len(raw) > 420 and raw.count(".") < 2 and raw.count("—") < 1 and raw.count(":") < 3:
        return True
    # Many Title Case tokens packed (TOC / header paste)
    titleish = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){2,}\b", raw)
    if len(raw) > 200 and len(titleish) >= 4 and raw.count(".") <= 1:
        return True
    return False


def _is_meta_finding(text: str) -> bool:
    return bool(_META_FINDING_RE.search((text or "").strip()))


def _signal_line(text: str, *, max_chars: int = 280) -> str | None:
    """Return cleaned signal text, or None if noisy / meta / empty."""
    t = _clean_prose(text, max_chars=max_chars + 80)
    if not t or _is_meta_finding(t) or _is_noisy(t):
        return None
    if len(t) > max_chars:
        t = t[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return t


def _recover_field_value(raw: Any) -> str | None:
    """Recover a usable attribute value from store fields that may include CIM paste."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if not _is_noisy(text) and not _is_meta_finding(text):
        return _clean_prose(text, 200)
    # Common dump pattern: "Parameter Details Legal Name <Company> CIN …"
    m = re.search(r"Legal\s+Name\s+(.+?)(?:\s+CIN\b|\s+Founded\b|$)", text, re.I)
    if m:
        recovered = _clean_prose(m.group(1), 120)
        if recovered and not _is_noisy(recovered):
            return recovered
    return None


def _norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _dedupe(lines: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key = _norm_key(line)[:120]
        if not key or key in seen:
            continue
        # Skip near-duplicates (prefix overlap)
        if any(key.startswith(s[:80]) or s.startswith(key[:80]) for s in seen if len(s) > 24):
            continue
        seen.add(key)
        out.append(line)
    return out


def _findings(agent: dict[str, Any], limit: int = 8, *, clean: bool = True) -> list[str]:
    raw = agent.get("findings") or []
    out: list[str] = []
    for item in raw:
        text = ""
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("finding") or item.get("note") or item.get("name") or item.get("risk") or ""
            ).strip()
        if not text:
            continue
        if clean:
            sig = _signal_line(text)
            if not sig:
                continue
            out.append(sig)
        else:
            out.append(_clean_prose(text, 500))
        if len(out) >= limit:
            break
    return _dedupe(out)


def _as_str_list(value: Any, limit: int = 12, *, clean: bool = True) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = ""
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("name")
                or item.get("note")
                or item.get("detail")
                or item.get("clause")
                or item.get("risk")
                or item.get("theme")
                or item.get("driver")
                or ""
            ).strip()
            if text:
                extra = item.get("severity") or item.get("impact") or item.get("status")
                # Append severity/status only for short labelled items
                if extra is not None and item.get("name") and len(text) < 80:
                    text = f"{text} ({extra})"
        if not text:
            continue
        if clean:
            sig = _signal_line(text, max_chars=320)
            if not sig:
                continue
            out.append(sig)
        else:
            out.append(_clean_prose(text, 400))
        if len(out) >= limit:
            break
    return _dedupe(out)


def _insight_from_agents(*agents: dict[str, Any], fallback: str = "") -> str:
    """Build a short Insight sentence from summary / first clean finding."""
    for a in agents:
        if not a:
            continue
        summary = a.get("summary")
        if isinstance(summary, str):
            sig = _signal_line(summary, max_chars=320)
            if sig:
                return sig
        findings = _findings(a, limit=1)
        if findings:
            return findings[0]
    return fallback


# ---------------------------------------------------------------------------
# Document chrome helpers
# ---------------------------------------------------------------------------

def _set_run_font(
    run,
    *,
    bold: bool = False,
    size: int = 11,
    color: RGBColor | None = None,
    italic: bool = False,
) -> None:
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), "Calibri")
    if color is not None:
        run.font.color.rgb = color


def _shade_cell(cell, fill_hex: str) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill_hex)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def _shade_paragraph(paragraph, fill_hex: str) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill_hex)
    shd.set(qn("w:val"), "clear")
    pPr.append(shd)


def _set_cell_text(cell, text: str, *, bold: bool = False, size: int = 10, color: RGBColor | None = None) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(_clean_prose(text, 500))
    _set_run_font(run, bold=bold, size=size, color=color)


def _add_heading(doc: Document, text: str, level: int = 1) -> None:
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        size = 16 if level == 1 else (13 if level == 2 else 11)
        _set_run_font(run, bold=True, size=size, color=_NAVY if level <= 2 else None)
    if level == 1:
        # Blue rule under H1
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "12")
        bottom.set(qn("w:space"), "4")
        bottom.set(qn("w:color"), "1F3864")
        pBdr.append(bottom)
        pPr.append(pBdr)


def _add_para(
    doc: Document,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    size: int = 11,
    color: RGBColor | None = None,
) -> None:
    p = doc.add_paragraph()
    run = p.add_run(_clean_prose(text, 2000))
    _set_run_font(run, bold=bold, size=size, color=color, italic=italic)
    p.paragraph_format.space_after = Pt(6)


def _add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        sig = _signal_line(item, max_chars=400) or _clean_prose(item, 280)
        if not sig:
            continue
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(sig)
        _set_run_font(run, size=11)


def _add_kv_table(doc: Document, rows: list[tuple[str, str]], *, headers: tuple[str, str] = ("Item", "Detail")) -> None:
    if not rows:
        return
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    _set_cell_text(hdr[0], headers[0], bold=True, size=10, color=RGBColor(0xFF, 0xFF, 0xFF))
    _set_cell_text(hdr[1], headers[1], bold=True, size=10, color=RGBColor(0xFF, 0xFF, 0xFF))
    _shade_cell(hdr[0], "1F3864")
    _shade_cell(hdr[1], "1F3864")
    for i, (k, v) in enumerate(rows):
        row = table.add_row().cells
        _set_cell_text(row[0], k, bold=True, size=10)
        _set_cell_text(row[1], v, size=10)
        if i % 2 == 0:
            _shade_cell(row[0], "F3F6FB")
            _shade_cell(row[1], "F3F6FB")
    doc.add_paragraph()


def _evidence_status(value: Any, *, sources: str = "") -> str:
    """CONFIRMED when a concrete store-backed value exists; else ASSUMED."""
    if value is None:
        return _STATUS_ASSUMED
    text = str(value).strip()
    if not text or text in {"-", "n/a", "N/A"}:
        return _STATUS_ASSUMED
    low = text.lower()
    if any(
        x in low
        for x in (
            "not documented",
            "requires management",
            "not stated",
            "not well-defined",
            "unclear",
            "assumed",
        )
    ):
        return _STATUS_ASSUMED
    if _is_noisy(text):
        return _STATUS_ASSUMED
    # Real value with (or without) a cited source → confirmed from workflow store
    if sources and sources not in {"-", ""}:
        return _STATUS_CONFIRMED
    return _STATUS_CONFIRMED


def _set_status_pill(cell, status: str) -> None:
    """Render a CONFIRMED / ASSUMED status pill in a table cell."""
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(status)
    if status == _STATUS_CONFIRMED:
        _set_run_font(run, bold=True, size=9, color=_STATUS_CONFIRMED_COLOR)
        _shade_cell(cell, "ECFDF3")
    else:
        _set_run_font(run, bold=True, size=9, color=_STATUS_ASSUMED_COLOR)
        _shade_cell(cell, "FFFBEB")


def _add_status_attribute_table(
    doc: Document,
    rows: list[tuple[str, str, str, str]],
    *,
    col_headers: tuple[str, str, str, str] = ("Attribute", "Details", "Source", "Status"),
) -> None:
    """Live-style attribute table with CONFIRMED / ASSUMED status column."""
    if not rows:
        return
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(col_headers):
        _set_cell_text(hdr[i], h, bold=True, size=9, color=RGBColor(0xFF, 0xFF, 0xFF))
        _shade_cell(hdr[i], "1F3864")
    for i, (attr, detail, source, status) in enumerate(rows):
        cells = table.add_row().cells
        _set_cell_text(cells[0], attr, bold=True, size=9)
        _set_cell_text(cells[1], detail, size=9)
        _set_cell_text(cells[2], source or "-", size=9)
        _set_status_pill(cells[3], status if status in {_STATUS_CONFIRMED, _STATUS_ASSUMED} else _STATUS_ASSUMED)
        if i % 2 == 0:
            for c in cells[:3]:
                _shade_cell(c, "F3F6FB")
    doc.add_paragraph()


def _estimate_content_pages(enabled_kinds: list[str]) -> dict[str, str]:
    """Estimate DiligenceIQ-style content page numbers (front matter excluded).

    Live TOC numbers content pages starting at 01 for section 1.0 — not absolute
    Word pagination. We approximate spacing from our divider + section layout.
    """
    pages: dict[str, str] = {}
    p = 1
    for kind in enabled_kinds:
        if kind == "framing":
            pages["1.0"] = f"{p:02d}"
            pages["1.1"] = f"{p:02d}"
            pages["1.2"] = f"{p + 2:02d}"
            p += 6
        elif kind == "company":
            pages["2.0"] = f"{p:02d}"
            pages["2.1"] = f"{p:02d}"
            pages["2.2"] = f"{p + 3:02d}"
            pages["2.3"] = f"{p + 5:02d}"
            p += 8
        elif kind == "legal":
            pages["3.0"] = f"{p:02d}"
            pages["3.1"] = f"{p:02d}"
            pages["3.2"] = f"{p + 1:02d}"
            pages["3.3"] = f"{p + 2:02d}"
            p += 5
    return pages


def _add_insight(doc: Document, text: str) -> None:
    sig = _signal_line(text, max_chars=420) or _clean_prose(text, 420)
    if not sig:
        return
    p = doc.add_paragraph()
    _shade_paragraph(p, _INSIGHT_BG)
    # Left accent via paragraph border
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "24")
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), "1F3864")
    pBdr.append(left)
    pPr.append(pBdr)
    label = p.add_run("Insight: ")
    _set_run_font(label, bold=True, size=10, color=_NAVY)
    body = p.add_run(sig)
    _set_run_font(body, italic=True, size=10, color=_SLATE)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)


def _add_agent_source_table(
    doc: Document,
    rows: list[tuple[str, str, str, str]],
    *,
    col_headers: tuple[str, str, str, str] = ("Item", "What the workflow found", "Agent", "Source document(s)"),
) -> None:
    if not rows:
        return
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(col_headers):
        _set_cell_text(hdr[i], h, bold=True, size=9, color=RGBColor(0xFF, 0xFF, 0xFF))
        _shade_cell(hdr[i], "1F3864")
    for i, (item, found, agent, src) in enumerate(rows):
        cells = table.add_row().cells
        _set_cell_text(cells[0], item, bold=True, size=9)
        _set_cell_text(cells[1], found, size=9)
        _set_cell_text(cells[2], agent, size=9)
        _set_cell_text(cells[3], src, size=9)
        if i % 2 == 0:
            for c in cells:
                _shade_cell(c, "F3F6FB")
    doc.add_paragraph()


def _sources_attribution(doc: Document, agents: list[dict[str, Any]]) -> None:
    names: list[str] = []
    files: list[str] = []
    seen_n: set[str] = set()
    seen_f: set[str] = set()
    for a in agents:
        if not a:
            continue
        n = _agent_name(a)
        if n != "-" and n not in seen_n:
            seen_n.add(n)
            names.append(n)
        for s in a.get("sources") or []:
            if isinstance(s, str) and s not in seen_f:
                seen_f.add(s)
                files.append(s)
    if not names and not files:
        return
    parts = ["Source: this deal's diligence workflow output"]
    if names:
        parts.append("— the " + ", ".join(names[:6]) + ("…" if len(names) > 6 else "") + " agents")
    parts.append(". Not re-derived here.")
    if files:
        parts.append(" That analysis cites: " + ", ".join(files[:5]) + ("…" if len(files) > 5 else "") + ".")
    _add_para(doc, "".join(parts), italic=True, size=9, color=_MUTED)


def _page_break(doc: Document) -> None:
    doc.add_page_break()


def _compose_cover(doc: Document, ctx: BuildContext) -> None:
    company = _company(ctx)
    sector = _sector(ctx)
    today = date.today().strftime("%d %B %Y")

    # Hero block (shaded table)
    hero = doc.add_table(rows=1, cols=1)
    cell = hero.rows[0].cells[0]
    _shade_cell(cell, _COVER_BG)
    cell.text = ""
    for i, (text, size, bold) in enumerate(
        (
            ("INVESTMENT DUE DILIGENCE / STRATEGY REPORT", 9, False),
            ("Strategy Report", 28, True),
            (f"Investment Due Diligence — {company}", 14, False),
            ("Deal hypothesis, strategic direction, legal structure and key risks", 10, False),
        )
    ):
        p = cell.add_paragraph() if i else cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(text)
        _set_run_font(run, bold=bold, size=size, color=RGBColor(0xFF, 0xFF, 0xFF))
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.space_before = Pt(4 if i else 12)
    # spacer paragraph inside cell
    sp = cell.add_paragraph()
    sp.paragraph_format.space_before = Pt(8)

    doc.add_paragraph()

    meta = [
        ("Document", "Strategy Report"),
        ("Target", company),
        ("Sector", sector or "Other / Generic"),
        ("Report Date", today),
        ("Prepared By", "Agentic CDD"),
        ("Document Reference", f"STRAT / {date.today().strftime('%y')} / 001"),
    ]
    # 2-col metadata grid
    grid = doc.add_table(rows=3, cols=4)
    grid.style = "Table Grid"
    pairs = meta
    for idx, (k, v) in enumerate(pairs):
        r, c = divmod(idx, 2)
        _set_cell_text(grid.rows[r].cells[c * 2], k, bold=True, size=9, color=_MUTED)
        _set_cell_text(grid.rows[r].cells[c * 2 + 1], v, bold=True, size=10, color=_NAVY)

    doc.add_paragraph()

    # Confidentiality callout
    box = doc.add_table(rows=1, cols=1)
    cell = box.rows[0].cells[0]
    _shade_cell(cell, "F8F5F2")
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run("STRICTLY PRIVATE & CONFIDENTIAL")
    _set_run_font(run, bold=True, size=11, color=_ACCENT)
    p2 = cell.add_paragraph()
    run2 = p2.add_run(
        "This Strategy Report is intended solely for the Investment Committee and authorised "
        "advisers. Redistribution outside the engagement team is prohibited without written consent."
    )
    _set_run_font(run2, size=9, color=_SLATE)


def _compose_toc(doc: Document, ctx: BuildContext, *, has_exec: bool) -> None:
    """TOC mirrors live DiligenceIQ nesting + page numbers.

    Soft change: Executive Summary and Appendices stay in the document body but
    are omitted from the TOC list (live product lists only 1.0–3.3).
    """
    _add_heading(doc, "Table of Contents", level=1)

    enabled = [s for s in (ctx.storyline or []) if s.included]
    kinds = [s.kind for s in enabled]
    page_map = _estimate_content_pages(kinds)

    # (indent_title, page_key or None)
    entries: list[tuple[str, str | None]] = []
    for section in enabled:
        kind = section.kind
        if kind == "framing":
            entries.append((section.title, "1.0"))
            entries.append(("    1.1 Deal Context & Objectives", "1.1"))
            entries.append(("    1.2 Scope & Methodology", "1.2"))
        elif kind == "company":
            entries.append((section.title, "2.0"))
            entries.append(("    2.1 Company Background", "2.1"))
            entries.append(("    2.2 Strategic Direction", "2.2"))
            entries.append(("    2.3 Management Quality", "2.3"))
        elif kind == "legal":
            entries.append((section.title, "3.0"))
            entries.append(("    3.1 Regulatory Compliance", "3.1"))
            entries.append(("    3.2 IP & Technology Assessment", "3.2"))
            entries.append(("    3.3 ESG & Sustainability", "3.3"))
        else:
            entries.append((section.title, None))

    for title, page_key in entries:
        page = page_map.get(page_key or "", "")
        p = doc.add_paragraph()
        # Leader-style row: title …… page
        run = p.add_run(title)
        _set_run_font(run, bold=not title.startswith(" "), size=11, color=_NAVY)
        if page:
            # tab + dotted leaders via trailing dots then page number
            gap = max(2, 48 - len(title))
            run_dots = p.add_run(" " + ("." * gap) + " ")
            _set_run_font(run_dots, size=10, color=_MUTED)
            run_pg = p.add_run(page)
            _set_run_font(run_pg, bold=True, size=11, color=_NAVY)
        p.paragraph_format.space_after = Pt(4)

    # Soft note — body still has Exec Summary / Appendices
    extras: list[str] = []
    if has_exec:
        extras.append("Executive Summary")
    extras.append("Appendices — Source Index")
    note = (
        "Also included in this document (not listed above, matching the live Strategy TOC): "
        + " · ".join(extras)
        + "."
    )
    _add_para(doc, note, italic=True, size=9, color=_MUTED)


def _compose_divider(doc: Document, number: str, title: str, subtitle: str) -> None:
    _page_break(doc)
    # Full-bleed feel via shaded single-cell table
    table = doc.add_table(rows=1, cols=1)
    cell = table.rows[0].cells[0]
    _shade_cell(cell, _COVER_BG)
    cell.text = ""
    for _ in range(4):
        cell.add_paragraph()
    p_num = cell.add_paragraph()
    p_num.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p_num.add_run(number)
    _set_run_font(run, bold=True, size=48, color=RGBColor(0x9C, 0xA8, 0xC0))
    p_title = cell.add_paragraph()
    run = p_title.add_run(title)
    _set_run_font(run, bold=True, size=26, color=RGBColor(0xFF, 0xFF, 0xFF))
    p_sub = cell.add_paragraph()
    run = p_sub.add_run(subtitle)
    _set_run_font(run, size=12, color=RGBColor(0xD0, 0xD7, 0xE2))
    for _ in range(6):
        cell.add_paragraph()
    foot = cell.add_paragraph()
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = foot.add_run("AGENTIC CDD  ·  INVESTMENT DUE DILIGENCE  ·  STRICTLY PRIVATE & CONFIDENTIAL")
    _set_run_font(run, size=8, color=RGBColor(0xB0, 0xBA, 0xCC))
    _page_break(doc)


# ---------------------------------------------------------------------------
# Section composers
# ---------------------------------------------------------------------------

def _compose_executive_summary(doc: Document, ctx: BuildContext) -> None:
    ics = _resolve_agent(ctx, "ic_synthesis")
    rec = _resolve_agent(ctx, "recommendation")
    if not ics and not rec:
        return

    _add_heading(doc, "Executive Summary", level=1)
    company = _company(ctx)
    ics_spec = _spec(ics)
    rec_spec = _spec(rec)

    go = ics_spec.get("go_no_go") or rec_spec.get("aligned_go_no_go")
    score = ics_spec.get("overall_score_1_5")
    label = ics_spec.get("overall_label")
    conf = ics_spec.get("confidence")

    insight_bits = [f"Strategy assessment for {company}."]
    if go:
        insight_bits.append(f"Investment stance: {go}.")
    if score is not None:
        insight_bits.append(f"Overall rating: {score}/5" + (f" ({label})" if label else "") + ".")
    if conf:
        insight_bits.append(f"Confidence: {conf}.")
    _add_insight(doc, " ".join(insight_bits))

    narrative = ics_spec.get("verdict_narrative") or ics_spec.get("value_creation_thesis")
    if isinstance(narrative, str) and narrative.strip():
        sig = _signal_line(narrative, max_chars=900) or _clean_prose(narrative, 900)
        if sig:
            _add_para(doc, sig)

    pillars = _as_str_list(ics_spec.get("investment_pillars"), limit=6)
    if pillars:
        _add_heading(doc, "Investment pillars", level=2)
        _add_bullets(doc, pillars)

    risks = _as_str_list(ics_spec.get("primary_risks"), limit=6)
    if not risks:
        risks = _findings(ics, limit=4)
    if risks:
        _add_heading(doc, "Primary risks", level=2)
        _add_bullets(doc, risks)

    if rec_spec.get("deal_structure") or rec_spec.get("returns_by_scenario"):
        _add_heading(doc, "Transaction posture", level=2)
        if rec_spec.get("deal_structure"):
            _add_para(doc, f"Structure: {rec_spec['deal_structure']}")
        scenarios = rec_spec.get("returns_by_scenario")
        if isinstance(scenarios, list) and scenarios:
            rows = []
            for sc in scenarios:
                if not isinstance(sc, dict):
                    continue
                name = str(sc.get("scenario") or "Scenario")
                detail = []
                if sc.get("irr_pct") is not None:
                    detail.append(f"IRR {sc['irr_pct']}%")
                if sc.get("moic_x") is not None:
                    detail.append(f"MOIC {sc['moic_x']}x")
                rows.append((name, " · ".join(detail) if detail else "-"))
            if rows:
                _add_kv_table(doc, rows)

    _sources_attribution(doc, [ics, rec])


def _compose_framing(doc: Document, ctx: BuildContext, section: StorylineSection) -> None:
    """Live TOC: 1.1 Deal Context & Objectives · 1.2 Scope & Methodology."""
    _add_heading(doc, section.title, level=1)
    _add_para(
        doc,
        "Extracting deal context, hypotheses and defining the analytical roadmap.",
        italic=True,
        size=10,
        color=_MUTED,
    )

    strat = _resolve_agent(ctx, "strategic_direction")
    growth = _resolve_agent(ctx, "growth_opportunities")
    market = _resolve_agent(ctx, "market_definition")
    deal = _resolve_agent(ctx, "deal_context_and_objectives")
    syn = _resolve_agent(ctx, "synergies")
    scope = _resolve_agent(ctx, "scope_and_methodology")
    agents = [a for a in (strat, growth, market, deal, syn, scope) if a]

    company = _company(ctx)
    sector = _sector(ctx)

    # --- 1.1 Deal Context & Objectives ---
    _add_heading(doc, "1.1 Deal Context & Objectives", level=2)
    insight = _insight_from_agents(
        deal,
        strat,
        fallback=f"Deal framing for {company} drawn from workflow agents; price terms may be absent from the data room.",
    )
    _add_insight(doc, insight)

    overview_rows_raw = [
        ("Target Company", company if not deal.get("target_company") else str(deal["target_company"])),
        ("Industry / Sector", sector or "Other / Generic"),
    ]
    if deal.get("description"):
        desc = _signal_line(str(deal["description"]), max_chars=200)
        if desc:
            overview_rows_raw.append(("Engagement focus", desc))
    deal_src = _agent_sources(deal)
    overview_status = [
        (
            label,
            detail,
            deal_src if _evidence_status(detail, sources=deal_src) == _STATUS_CONFIRMED else "-",
            _evidence_status(detail, sources=deal_src),
        )
        for label, detail in overview_rows_raw
    ]
    # Indicative EV often absent from data room — surface as ASSUMED like live
    overview_status.append(("Indicative EV", "Not stated in the data room", "-", _STATUS_ASSUMED))
    _add_status_attribute_table(
        doc,
        overview_status,
        col_headers=("Parameter", "Details", "Source", "Status"),
    )

    deal_findings = _findings(deal, limit=4)
    if deal_findings:
        _add_heading(doc, "1.1.1 Key context findings", level=3)
        rows = [
            (
                f"Finding {i + 1}",
                f,
                _agent_name(deal, "Deal Context & Objectives"),
                _agent_sources(deal),
            )
            for i, f in enumerate(deal_findings)
        ]
        _add_agent_source_table(doc, rows)

    # Investment hypotheses folded under 1.1 (live nests these here, not as separate H2s)
    strat_spec = _spec(strat)
    drivers = _as_str_list(strat_spec.get("investment_drivers"), limit=5)
    must = _as_str_list(strat_spec.get("must_be_true"), limit=5)
    breakers = _as_str_list(strat_spec.get("deal_breaker_risks"), limit=5)
    if not drivers and not must:
        drivers = _findings(strat, limit=5)

    if drivers or must or breakers:
        _add_heading(doc, "1.1.2 Key investment hypotheses (Must-Be-True)", level=3)
        bits = []
        if strat_spec.get("thesis_framework"):
            bits.append(f"Thesis framework: {strat_spec['thesis_framework']}.")
        if strat_spec.get("attractiveness_score") is not None:
            bits.append(f"Attractiveness score: {strat_spec['attractiveness_score']}/10.")
        if bits:
            _add_insight(doc, " ".join(str(b) for b in bits))
        elif drivers:
            _add_insight(doc, drivers[0])

        as_rows: list[tuple[str, str, str, str]] = []
        for i, d in enumerate(drivers[:5]):
            as_rows.append(
                (f"Driver {i + 1}", d, _agent_name(strat, "Strategic Direction"), _agent_sources(strat))
            )
        for i, m in enumerate(must[:4]):
            as_rows.append(
                (f"Must-be-true {i + 1}", m, _agent_name(strat, "Strategic Direction"), _agent_sources(strat))
            )
        for i, b in enumerate(breakers[:4]):
            as_rows.append(
                (f"Deal-breaker {i + 1}", b, _agent_name(strat, "Strategic Direction"), _agent_sources(strat))
            )
        if as_rows:
            _add_agent_source_table(
                doc,
                as_rows,
                col_headers=("Hypothesis", "What the workflow found", "Agent", "Source document(s)"),
            )

    market_spec = _spec(market)
    framing = _as_str_list(market_spec.get("market_framing"), limit=4) or _findings(market, limit=4)
    framing = [
        f for f in framing
        if f and "Foundation ·" not in f and "plan relies" not in f.lower()
        and not str(f).startswith("Information")
    ]
    perim = market_spec.get("perimeter") if isinstance(market_spec.get("perimeter"), dict) else {}
    if not framing:
        svc = str(perim.get("service") or "").strip()
        if svc and not svc.startswith("Information") and "Foundation ·" not in svc:
            framing = [svc]
    geos = _as_str_list(market_spec.get("geographies"), limit=5)
    if not geos and perim.get("geography"):
        geos = [str(perim["geography"])]
    if framing or geos:
        _add_heading(doc, "1.1.3 Market perimeter signals", level=3)
        if framing:
            _add_insight(doc, framing[0])
            rows = [
                (f"Perimeter {i + 1}", f, _agent_name(market, "Market Definition"), _agent_sources(market))
                for i, f in enumerate(framing)
            ]
            _add_agent_source_table(doc, rows)
        if geos:
            _add_para(doc, "Geographic mix:", bold=True)
            _add_bullets(doc, geos)

    # --- 1.2 Scope & Methodology (live TOC slot) ---
    _add_heading(doc, "1.2 Scope & Methodology", level=2)
    scope_findings = _findings(scope, limit=5)
    scope_insight = _insight_from_agents(
        scope,
        fallback="Engagement boundaries and analytical methodology from the scope-and-methodology agent.",
    )
    _add_insight(doc, scope_insight)

    scope_rows: list[tuple[str, str]] = [
        ("In-scope", "Financial performance, market analysis, operational risks, and management assessment"),
        ("Out-of-scope", "Deep technical assessment of proprietary source code (unless surfaced by workflow agents)"),
        ("Primary inputs", "Foundation / Deep Dive / Verdict agent stores (not raw VDR re-derivation)"),
    ]
    if company:
        scope_rows.append(("Target", company))
    _add_kv_table(doc, scope_rows, headers=("Category", "Scope"))

    if scope_findings:
        rows = [
            (f"Note {i + 1}", f, _agent_name(scope, "Scope & Methodology"), _agent_sources(scope))
            for i, f in enumerate(scope_findings)
        ]
        _add_agent_source_table(doc, rows)

    # Light growth/synergy pointers stay under framing as methodology deliverable notes
    growth_spec = _spec(growth)
    lever_lines: list[str] = []
    levers = growth_spec.get("growth_levers")
    if isinstance(levers, list):
        for lev in levers[:4]:
            if isinstance(lev, dict):
                name = str(lev.get("name") or "").strip()
                if name and not _is_noisy(name):
                    lever_lines.append(name)
            elif isinstance(lev, str):
                sig = _signal_line(lev, max_chars=80)
                if sig:
                    lever_lines.append(sig)
    if not lever_lines:
        lever_lines = [f for f in _findings(growth, limit=3) if len(f) < 80]

    syn_spec = _spec(syn)
    themes = _as_str_list(syn_spec.get("synergy_themes"), limit=3) or _findings(syn, limit=3)
    themes = [t for t in themes if len(t) < 120]

    if lever_lines or themes:
        _add_heading(doc, "1.2.1 Deliverable focus areas", level=3)
        focus_rows: list[tuple[str, str, str, str]] = []
        for i, L in enumerate(lever_lines[:4]):
            focus_rows.append(
                (f"Growth lever {i + 1}", L, _agent_name(growth, "Growth Opportunities"), _agent_sources(growth))
            )
        for i, t in enumerate(themes[:3]):
            focus_rows.append((f"Synergy theme {i + 1}", t, _agent_name(syn, "Synergies"), _agent_sources(syn)))
        if focus_rows:
            _add_agent_source_table(doc, focus_rows)

    _sources_attribution(doc, agents)


def _compose_company(doc: Document, ctx: BuildContext, section: StorylineSection) -> None:
    """Live TOC: 2.1 Company Background · 2.2 Strategic Direction · 2.3 Management Quality."""
    _add_heading(doc, section.title, level=1)
    _add_para(
        doc,
        "Analyzing company background, strategic direction and management quality.",
        italic=True,
        size=10,
        color=_MUTED,
    )

    company_bg = _resolve_agent(ctx, "company_background")
    strat = _resolve_agent(ctx, "strategic_direction")
    growth = _resolve_agent(ctx, "growth_opportunities")
    syn = _resolve_agent(ctx, "synergies")
    mgmt = _resolve_agent(ctx, "management_quality")
    exec_risk = _resolve_agent(ctx, "execution_risk")
    ops = _resolve_agent(ctx, "operational_risk")
    internal = _resolve_agent(ctx, "internal_risk")
    cost = _resolve_agent(ctx, "cost_structure")
    comps = _resolve_agent(ctx, "competitor_identification")
    agents = [a for a in (company_bg, strat, growth, syn, mgmt, exec_risk, ops, internal, cost, comps) if a]

    # --- 2.1 Company Background ---
    _add_heading(doc, "2.1 Company Background", level=2)
    bg_spec = _spec(company_bg)
    src = _agent_sources(company_bg)
    snapshot_fields: list[tuple[str, Any]] = [
        ("Legal name", _recover_legal_name(bg_spec.get("legal_name")) or bg_spec.get("legal_name")),
        ("Entity type", bg_spec.get("entity_type")),
        ("Incorporated", bg_spec.get("incorporation_date")),
        ("Jurisdiction", bg_spec.get("jurisdiction")),
        ("Target name", _company(ctx)),
        ("Primary sector", _sector(ctx)),
    ]
    status_rows: list[tuple[str, str, str, str]] = []
    for label, raw in snapshot_fields:
        detail = _recover_field_value(raw)
        if detail:
            status = _evidence_status(detail, sources=src)
            status_rows.append((label, detail, src if status == _STATUS_CONFIRMED else "-", status))
        else:
            status_rows.append((label, _NOT_DOCUMENTED, "-", _STATUS_ASSUMED))

    insight = _insight_from_agents(
        company_bg,
        fallback=f"Entity profile for {_company(ctx)} from company-background workflow output.",
    )
    _add_insight(doc, insight)
    _add_status_attribute_table(doc, status_rows)

    ops_spec = _spec(ops)
    gaps = ops_spec.get("kpi_gaps")
    if isinstance(gaps, list) and gaps:
        _add_heading(doc, "2.1.1 Operational snapshot", level=3)
        lines = []
        for g in gaps[:6]:
            if isinstance(g, dict):
                lines.append(f"{g.get('kpi', 'KPI')}: {g.get('status', '-')}")
        if lines:
            _add_insight(doc, "Operational KPI posture from the operational-risk agent.")
            rows = [
                (L.split(":")[0], L, _agent_name(ops, "Operational Risk"), _agent_sources(ops))
                for L in lines
            ]
            _add_agent_source_table(doc, rows)

    cost_spec = _spec(cost)
    cost_metrics = cost_spec.get("cost_metrics")
    if isinstance(cost_metrics, dict) and cost_metrics:
        _add_heading(doc, "2.1.2 Cost structure highlights", level=3)
        rows = [
            (str(k).replace("_", " ").title(), str(v), _agent_name(cost, "Cost Structure"), _agent_sources(cost))
            for k, v in list(cost_metrics.items())[:6]
        ]
        _add_agent_source_table(
            doc,
            rows,
            col_headers=("Metric", "Value", "Agent", "Source document(s)"),
        )

    cf = _findings(comps, limit=5)
    if cf:
        _add_heading(doc, "2.1.3 Competitive context", level=3)
        rows = [
            (f"Competitor signal {i + 1}", f, _agent_name(comps, "Competitor Identification"), _agent_sources(comps))
            for i, f in enumerate(cf)
        ]
        _add_agent_source_table(doc, rows)

    # --- 2.2 Strategic Direction (live TOC slot) ---
    _add_heading(doc, "2.2 Strategic Direction", level=2)
    strat_spec = _spec(strat)
    bits = []
    if strat_spec.get("thesis_framework"):
        bits.append(f"Thesis framework: {strat_spec['thesis_framework']}.")
    if strat_spec.get("attractiveness_score") is not None:
        bits.append(f"Attractiveness score: {strat_spec['attractiveness_score']}/10.")
    strat_insight = " ".join(str(b) for b in bits) if bits else _insight_from_agents(
        strat,
        growth,
        fallback="Strategic direction summary from workflow agents.",
    )
    _add_insight(doc, strat_insight)

    drivers = _as_str_list(strat_spec.get("investment_drivers"), limit=5) or _findings(strat, limit=5)
    if drivers:
        rows = [
            (f"Direction {i + 1}", d, _agent_name(strat, "Strategic Direction"), _agent_sources(strat))
            for i, d in enumerate(drivers)
        ]
        _add_agent_source_table(doc, rows)

    growth_spec = _spec(growth)
    lever_lines: list[str] = []
    levers = growth_spec.get("growth_levers")
    if isinstance(levers, list):
        for lev in levers[:6]:
            if isinstance(lev, dict):
                name = str(lev.get("name") or "").strip()
                note = _signal_line(str(lev.get("note") or ""), max_chars=220) or ""
                if name and _is_noisy(name):
                    continue
                if not name and not note:
                    continue
                line = f"{name} — {note}".strip(" —") if note else name
                sig = _signal_line(line, max_chars=320)
                if sig:
                    lever_lines.append(sig)
            elif isinstance(lev, str):
                sig = _signal_line(lev)
                if sig:
                    lever_lines.append(sig)
    if not lever_lines:
        lever_lines = _findings(growth, limit=5)

    if lever_lines:
        _add_heading(doc, "2.2.1 Growth opportunities", level=3)
        _add_insight(doc, lever_lines[0])
        rows = [
            (f"Lever {i + 1}", L, _agent_name(growth, "Growth Opportunities"), _agent_sources(growth))
            for i, L in enumerate(lever_lines)
        ]
        _add_agent_source_table(doc, rows)
        milestones = _as_str_list(growth_spec.get("milestone_targets"), limit=5)
        if milestones:
            _add_para(doc, "Milestones:", bold=True)
            _add_bullets(doc, milestones)

    syn_spec = _spec(syn)
    lever_seen = {_norm_key(x)[:60] for x in lever_lines}
    themes = _as_str_list(syn_spec.get("synergy_themes"), limit=5) or _findings(syn, limit=4)
    themes = [
        t
        for t in themes
        if _norm_key(t)[:60] not in lever_seen
        and not any(_norm_key(t).startswith(s) or s.startswith(_norm_key(t)[:40]) for s in lever_seen if s)
    ]
    if themes:
        _add_heading(doc, "2.2.2 Synergy themes", level=3)
        rows = [
            (f"Theme {i + 1}", t, _agent_name(syn, "Synergies"), _agent_sources(syn))
            for i, t in enumerate(themes)
        ]
        _add_agent_source_table(doc, rows)

    int_spec = _spec(internal)
    comps_tech = int_spec.get("tech_components")
    if isinstance(comps_tech, list) and comps_tech:
        _add_heading(doc, "2.2.3 Technology & scalability", level=3)
        rows = []
        for c in comps_tech[:6]:
            if not isinstance(c, dict):
                continue
            detail = f"maturity {c.get('maturity_score', '-')}/5"
            if c.get("key_risk"):
                detail += f"; {c.get('key_risk')}"
            rows.append((
                str(c.get("component") or "Component"),
                detail,
                _agent_name(internal, "Internal Risk"),
                _agent_sources(internal),
            ))
        _add_agent_source_table(doc, rows)

    # --- 2.3 Management Quality (live TOC slot) ---
    _add_heading(doc, "2.3 Management Quality", level=2)
    mgmt_spec = _spec(mgmt)
    c_suite = mgmt_spec.get("c_suite")
    if isinstance(c_suite, list) and c_suite:
        _add_insight(
            doc,
            f"Organisation risk score: {mgmt_spec['org_risk_score']}/10."
            if mgmt_spec.get("org_risk_score") is not None
            else "Management roster sourced from the management-quality agent.",
        )
        rows = []
        for person in c_suite[:8]:
            if not isinstance(person, dict):
                continue
            name = str(person.get("name") or "-")
            role = str(person.get("role") or "")
            crit = person.get("criticality")
            detail = role + (f" · criticality {crit}/5" if crit is not None else "")
            rows.append((name, detail, _agent_name(mgmt, "Management Quality"), _agent_sources(mgmt)))
        _add_agent_source_table(
            doc,
            rows,
            col_headers=("Executive", "Role / criticality", "Agent", "Source document(s)"),
        )
    else:
        mf = _findings(mgmt, limit=4)
        if mf:
            _add_insight(doc, mf[0])
            _add_bullets(doc, mf)

    er_spec = _spec(exec_risk)
    if er_spec or _findings(exec_risk):
        _add_heading(doc, "2.3.1 Key-person & retention risk", level=3)
        hc = er_spec.get("overall_human_capital_risk_1_10")
        if hc is not None:
            _add_insight(doc, f"Overall human capital risk: {hc}/10.")
        flags = _as_str_list(er_spec.get("retention_risk_flags"), limit=5) or _findings(exec_risk, limit=5)
        if flags:
            rows = [
                (f"Flag {i + 1}", f, _agent_name(exec_risk, "Execution Risk"), _agent_sources(exec_risk))
                for i, f in enumerate(flags)
            ]
            _add_agent_source_table(doc, rows)
        execs = er_spec.get("executives")
        if isinstance(execs, list) and execs:
            rows = []
            for ex in execs[:6]:
                if not isinstance(ex, dict):
                    continue
                rows.append((
                    str(ex.get("name") or "-"),
                    f"{ex.get('role', '')} · succession {ex.get('succession_risk', '-')}",
                    _agent_name(exec_risk, "Execution Risk"),
                    _agent_sources(exec_risk),
                ))
            _add_agent_source_table(
                doc,
                rows,
                col_headers=("Executive", "Succession posture", "Agent", "Source document(s)"),
            )

    _sources_attribution(doc, agents)


def _compose_legal(doc: Document, ctx: BuildContext, section: StorylineSection) -> None:
    _add_heading(doc, section.title, level=1)
    _add_para(
        doc,
        "Assessing regulatory compliance, IP portfolio and ESG sustainability.",
        italic=True,
        size=10,
        color=_MUTED,
    )

    reg = _resolve_agent(ctx, "regulatory_compliance")
    ip = _resolve_agent(ctx, "ip_and_technology")
    esg = _resolve_agent(ctx, "esg_and_sustainability")
    supply = _resolve_agent(ctx, "supply_chain_resilience")
    ops = _resolve_agent(ctx, "operational_risk")
    agents = [a for a in (reg, ip, esg, supply, ops) if a]

    # --- 3.1 Regulatory ---
    _add_heading(doc, "3.1 Regulatory Compliance", level=2)
    reg_spec = _spec(reg)
    risks = reg_spec.get("risks")
    lines: list[str] = []
    if isinstance(risks, list) and risks:
        for r in risks[:8]:
            if isinstance(r, dict):
                clause = str(r.get("clause") or r.get("risk") or "")
                sev = r.get("severity")
                sig = _signal_line(clause, max_chars=220)
                if not sig:
                    continue
                if sev is not None:
                    sig = f"{sig} — severity {sev}/5"
                lines.append(sig)
            elif isinstance(r, str):
                sig = _signal_line(r)
                if sig:
                    lines.append(sig)
    if not lines:
        lines = _findings(reg, limit=6)

    if lines:
        _add_insight(doc, lines[0])
        rows = [
            (f"Risk {i + 1}", L, _agent_name(reg, "Regulatory Compliance"), _agent_sources(reg))
            for i, L in enumerate(lines)
        ]
        _add_agent_source_table(doc, rows)
    else:
        _add_para(doc, "No regulatory findings available in the store.")

    penalties = _as_str_list(reg_spec.get("penalty_notes"), limit=4)
    if penalties:
        _add_para(doc, "Penalty / proceedings notes:", bold=True)
        rows = [
            (f"Matter {i + 1}", p, _agent_name(reg, "Regulatory Compliance"), _agent_sources(reg))
            for i, p in enumerate(penalties)
        ]
        _add_agent_source_table(doc, rows)

    # --- 3.2 IP ---
    _add_heading(doc, "3.2 IP & Technology Assessment", level=2)
    ip_spec = _spec(ip)
    ip_findings = _findings(ip, limit=6)
    if ip_findings:
        _add_insight(doc, ip_findings[0])
        rows = [
            (f"IP signal {i + 1}", f, _agent_name(ip, "IP & Technology"), _agent_sources(ip))
            for i, f in enumerate(ip_findings)
        ]
        _add_agent_source_table(doc, rows)
    else:
        structured_any = False
        for key in ("patents", "tech_assets", "ip_risks", "ip_notes"):
            items = _as_str_list(ip_spec.get(key), limit=5)
            if items:
                structured_any = True
                _add_para(doc, key.replace("_", " ").title() + ":", bold=True)
                _add_bullets(doc, items)
        if not structured_any:
            _add_para(doc, "IP findings not cleanly structured in agent output.")

    # --- 3.3 ESG (cleaned — reject legal-matrix paste) ---
    _add_heading(doc, "3.3 ESG & Sustainability", level=2)
    esg_spec = _spec(esg)
    esg_rows: list[tuple[str, str, str, str]] = []

    for key, label in (
        ("environment_flags", "Environment"),
        ("social_flags", "Social"),
        ("labour_flags", "Labour / social"),
        ("governance_flags", "Governance"),
        ("esg_notes", "ESG note"),
        ("themes", "Theme"),
    ):
        items = _as_str_list(esg_spec.get(key), limit=3)
        for i, item in enumerate(items):
            esg_rows.append((
                f"{label} {i + 1}",
                item,
                _agent_name(esg, "ESG & Sustainability"),
                _agent_sources(esg),
            ))

    # Clean findings only — legal dumps already filtered by _is_noisy
    for i, f in enumerate(_findings(esg, limit=4)):
        # Skip if already captured
        if any(_norm_key(f)[:50] == _norm_key(r[1])[:50] for r in esg_rows):
            continue
        esg_rows.append((f"ESG finding {i + 1}", f, _agent_name(esg, "ESG & Sustainability"), _agent_sources(esg)))

    if esg_rows:
        _add_insight(doc, esg_rows[0][1])
        _add_agent_source_table(
            doc,
            esg_rows[:10],
            col_headers=("Dimension", "What the workflow found", "Agent", "Source document(s)"),
        )
    else:
        _add_insight(
            doc,
            "ESG metrics are not cleanly structured in the ESG agent output. "
            "Related regulatory exposure is covered under 3.1; confirm E/S/G KPIs with management.",
        )
        _add_status_attribute_table(
            doc,
            [
                ("Carbon / waste / resource metrics", _NOT_DOCUMENTED, "-", _STATUS_ASSUMED),
                ("Workforce / DEI metrics", _NOT_DOCUMENTED, "-", _STATUS_ASSUMED),
                ("Board / ethics policies", _NOT_DOCUMENTED, "-", _STATUS_ASSUMED),
            ],
            col_headers=("Metric", "Current status", "Source", "Status"),
        )

    # Supply chain
    supply_findings = _findings(supply, limit=4)
    supply_spec = _spec(supply)
    metrics = supply_spec.get("metrics") if isinstance(supply_spec.get("metrics"), dict) else {}
    # Prefer numeric metrics dict; drop findings that are just "key: value" echoes
    if metrics:
        metric_keys = {_norm_key(str(k)) for k in metrics}
        supply_findings = [
            f
            for f in supply_findings
            if _norm_key(f.split(":", 1)[0]) not in metric_keys
        ]
    if supply_findings or metrics:
        _add_heading(doc, "3.3.1 Supply-chain resilience", level=3)
        if metrics:
            rows = [
                (str(k), str(v), _agent_name(supply, "Supply Chain Resilience"), _agent_sources(supply))
                for k, v in list(metrics.items())[:6]
                if v is not None and str(v).strip()
            ]
            if rows:
                _add_agent_source_table(
                    doc,
                    rows,
                    col_headers=("Metric", "Value", "Agent", "Source document(s)"),
                )
        if supply_findings:
            _add_bullets(doc, supply_findings)

    ops_notes = _as_str_list(_spec(ops).get("integrity_notes"), limit=3)
    if ops_notes:
        _add_heading(doc, "3.3.2 Operational integrity notes", level=3)
        _add_bullets(doc, ops_notes)

    _sources_attribution(doc, agents)


def _compose_appendices(doc: Document, ctx: BuildContext) -> None:
    _page_break(doc)
    _add_heading(doc, "Appendices — Source Index", level=1)
    _add_insight(doc, "Agent → primary source document map from this deal's workflow outputs.")
    rows: list[tuple[str, str, str, str]] = []
    for key, agent in sorted(ctx.agent_outputs.items()):
        if not isinstance(agent, dict):
            continue
        name = agent.get("agentName") or key.replace("_", " ").title()
        sources = agent.get("sources") or []
        src = ", ".join(sources[:3]) if sources else "-"
        dd = _spec(agent).get("dd_code") or _spec(agent).get("fv_code") or _spec(agent).get("role_code") or "-"
        rows.append((str(name), str(dd), key, src))
    _add_agent_source_table(
        doc,
        rows[:40],
        col_headers=("Agent", "Code", "Slug", "Source document(s)"),
    )
    if len(rows) > 40:
        _add_para(doc, f"…and {len(rows) - 40} additional agents omitted from the printed index.")

    # G1 — released databook financial history (honest consume; never agent-only finals).
    try:
        from agetic_cdd_api.services_databook_consume import released_pl_display_rows

        hist = _resolve_agent(ctx, "historical_performance")
        hist_pl = (
            list(_spec(hist).get("pl_lines") or [])
            if isinstance(_spec(hist).get("pl_lines"), list)
            else []
        )
        fin_rows, _, footnote = released_pl_display_rows(ctx.deal_slug, hist_pl, limit=12)
        if fin_rows:
            _add_heading(doc, "Appendix — Databook financial history (released)", level=2)
            _add_para(
                doc,
                "Material company figures prefer the current Databook release "
                "(proven / doubtful / missing). Unproven agent figures are not shown as final.",
            )
            _add_agent_source_table(
                doc,
                [tuple(r) for r in fin_rows],
                col_headers=("Line", "FY values", "Unit", "Status"),
            )
            if footnote:
                _add_para(doc, footnote)
    except Exception:
        pass


_COMPOSERS = {
    "framing": _compose_framing,
    "company": _compose_company,
    "legal": _compose_legal,
}

_DIVIDER_COPY = {
    "framing": ("01", "Deal Framing & Scope", "Extracting deal context, hypotheses and defining the analytical roadmap."),
    "company": ("02", "Company & Management", "Analyzing company background, strategic direction and management quality."),
    "legal": ("03", "Legal, IP & ESG", "Assessing regulatory compliance, IP portfolio and ESG sustainability."),
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class StrategyReportBuilder(ReportBuilder):
    report_type = "strategy_report"

    def build_sections(self, ctx: BuildContext) -> Iterator[dict[str, Any]]:
        storyline = ctx.storyline or []
        enabled = [s for s in storyline if s.included]
        has_exec = bool(
            _resolve_agent(ctx, "ic_synthesis") or _resolve_agent(ctx, "recommendation")
        )
        # cover + toc + (optional exec) + enabled sections + appendices
        total = 2 + len(enabled) + (1 if has_exec else 0) + 1
        current = 0

        current += 1
        yield _evt("section", "Generating cover & table of contents", i=current, total=total)
        current += 1
        yield _evt("section", "Generating front matter", i=current, total=total)

        if has_exec:
            current += 1
            yield _evt("section", "Generating Executive Summary", i=current, total=total)

        for section in enabled:
            current += 1
            yield _evt(
                "section",
                f"Generating section {current} of {total}: {section.title}",
                i=current,
                total=total,
            )

        current += 1
        yield _evt("section", "Generating appendices", i=current, total=total)

    def export_artifact(self, ctx: BuildContext) -> str:
        doc = Document()
        for section in doc.sections:
            section.top_margin = Inches(0.85)
            section.bottom_margin = Inches(0.85)
            section.left_margin = Inches(0.95)
            section.right_margin = Inches(0.95)
            # Header / footer chrome
            header = section.header
            header.is_linked_to_previous = False
            hp = header.paragraphs[0]
            hp.text = ""
            run = hp.add_run(f"Strategy Report | {_company(ctx)}")
            _set_run_font(run, size=8, color=_MUTED)
            run2 = hp.add_run("\tStrictly Private & Confidential")
            _set_run_font(run2, bold=True, size=8, color=_ACCENT)
            footer = section.footer
            footer.is_linked_to_previous = False
            fp = footer.paragraphs[0]
            fp.text = ""
            run = fp.add_run("© Agentic CDD | Investment Due Diligence")
            _set_run_font(run, size=8, color=_MUTED)

        has_exec = bool(
            _resolve_agent(ctx, "ic_synthesis") or _resolve_agent(ctx, "recommendation")
        )

        _compose_cover(doc, ctx)
        _page_break(doc)
        _compose_toc(doc, ctx, has_exec=has_exec)
        _page_break(doc)

        if has_exec:
            _compose_executive_summary(doc, ctx)

        storyline = [s for s in (ctx.storyline or []) if s.included]
        for section in storyline:
            div = _DIVIDER_COPY.get(section.kind)
            if div:
                _compose_divider(doc, *div)
            composer = _COMPOSERS.get(section.kind)
            if composer:
                composer(doc, ctx, section)
            else:
                _add_heading(doc, section.title, level=1)
                for key in section.agents:
                    agent = _resolve_agent(ctx, key)
                    findings = _findings(agent, limit=5)
                    if findings:
                        _add_heading(
                            doc,
                            agent.get("agentName") or key.replace("_", " ").title(),
                            level=2,
                        )
                        _add_bullets(doc, findings)

        _compose_appendices(doc, ctx)

        out_dir = report_artifact_dir(ctx.deal_slug, "strategy_report")
        safe = re.sub(r"[^\w\s-]", "", _company(ctx)).strip().replace(" ", "_") or ctx.deal_slug
        filename = f"{safe}_Strategy_Report.docx"
        path = out_dir / filename
        doc.save(str(path))
        deal_root = deals_root() / ctx.deal_slug
        try:
            return str(path.relative_to(deal_root))
        except ValueError:
            return str(path)


register_builder("strategy_report", StrategyReportBuilder)
