"""IC Memo builder — Investment Committee memorandum (.pdf).

Live DiligenceIQ storyline (10 sections / 3 parts):
  1.0 Risk & Opportunity → 1.1–1.4
  2.0 Valuation → 2.1–2.3
  3.0 Executive Synthesis → 3.1–3.3

Prefer Verdict Store (ic_synthesis, recommendation, valuation_modeling,
trading_comps, precedent_transactions, execution_risk) over thin RAG.
No deal-specific hardcoding.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agetic_cdd_api.report_builder_base import BuildContext, ReportBuilder, _evt
from agetic_cdd_api.report_store import report_artifact_dir
from agetic_cdd_api.report_storyline import StorylineSection
from agetic_cdd_api.routers_reports import register_builder
from agetic_cdd_api.services_deals import deals_root, resolve_sector, sector_label

_NAVY = colors.HexColor("#1F3864")
_SLATE = colors.HexColor("#4B5563")
_MUTED = colors.HexColor("#6B7280")
_ACCENT = colors.HexColor("#C2410C")
_INSIGHT_BG = colors.HexColor("#E8EEF7")
_ROW_ALT = colors.HexColor("#F3F6FB")
_WHITE = colors.white

_AGENT_ALIASES: dict[str, tuple[str, ...]] = {
    "recommendations": ("recommendation", "recommendations"),
    "recommendation": ("recommendation", "recommendations"),
    "executive_summary": ("ic_synthesis", "executive_summary"),
    "final_valuation_range": ("valuation_modeling", "final_valuation_range"),
    "valuation_model": ("valuation_modeling", "valuation_model"),
    "sensitivity_analysis": ("valuation_modeling", "sensitivity_analysis", "recommendation"),
    "appendices": ("appendices", "scope_and_methodology"),
}


def _resolve(ctx: BuildContext, key: str) -> dict[str, Any]:
    for cand in _AGENT_ALIASES.get(key, (key,)):
        data = ctx.agent_outputs.get(cand)
        if isinstance(data, dict) and data:
            return data
    data = ctx.agent_outputs.get(key)
    return data if isinstance(data, dict) else {}


def _spec(agent: dict[str, Any]) -> dict[str, Any]:
    s = agent.get("spec")
    return s if isinstance(s, dict) else {}


def _company(ctx: BuildContext) -> str:
    if ctx.profile and ctx.profile.company:
        return ctx.profile.company
    return ctx.deal_slug


def _sector(ctx: BuildContext) -> str:
    if ctx.profile and ctx.profile.sector:
        return resolve_sector(str(ctx.profile.sector))
    return "generic"


def _sector_display(ctx: BuildContext) -> str:
    return sector_label(_sector(ctx))


def _agent_name(agent: dict[str, Any], fallback: str = "-") -> str:
    return str(agent.get("agentName") or agent.get("agent_key") or fallback)


def _agent_sources(agent: dict[str, Any], limit: int = 2) -> str:
    files: list[str] = []
    seen: set[str] = set()
    for s in list(agent.get("sources") or []) + list(_spec(agent).get("sources") or []):
        if isinstance(s, str) and s not in seen:
            seen.add(s)
            files.append(s)
    if not files:
        return "-"
    return ", ".join(files[:limit]) + ("…" if len(files) > limit else "")


def _clean(text: str, max_chars: int = 400) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip()).replace("\x7f", " ")
    if len(t) > max_chars:
        t = t[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return t


def _fmt_money_metric(block: Any) -> str:
    """Format TAM/SAM/SOM dicts — prefer value/unit/scale over stale raw segment text."""
    if block is None:
        return "—"
    if isinstance(block, dict):
        if block.get("value") is not None:
            unit = str(block.get("unit") or "").strip()
            scale = str(block.get("scale") or "").strip()
            try:
                num = float(block["value"])
                val_txt = f"{num:,.2f}".rstrip("0").rstrip(".") if abs(num) < 1000 else f"{num:,.1f}"
            except (TypeError, ValueError):
                val_txt = str(block["value"])
            bits = [val_txt]
            if unit:
                bits.append(unit)
            if scale and scale.lower() not in unit.lower():
                bits.append({"million": "M", "billion": "B", "crore": "Cr"}.get(scale.lower(), scale))
            return " ".join(bits)
        raw = block.get("raw")
        if isinstance(raw, str) and raw.strip():
            return _clean(raw, 120)
        return _clean(str(block), 120)
    if isinstance(block, list):
        return ", ".join(_fmt_money_metric(x) for x in block[:6])
    return _clean(str(block), 120)


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def _findings(agent: dict[str, Any], limit: int = 8) -> list[str]:
    out: list[str] = []
    for item in agent.get("findings") or []:
        if isinstance(item, str) and item.strip():
            out.append(_clean(item, 360))
        elif isinstance(item, dict):
            text = item.get("finding") or item.get("note") or item.get("name") or item.get("risk")
            if text:
                out.append(_clean(str(text), 360))
        if len(out) >= limit:
            break
    return out


def _as_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(_clean(item, 280))
        elif isinstance(item, dict):
            text = (
                item.get("name")
                or item.get("risk")
                or item.get("note")
                or item.get("theme")
                or item.get("clause")
                or item.get("metric")
            )
            if text is not None:
                extra = item.get("impact")
                if extra is None:
                    extra = item.get("probability")
                if extra is None:
                    extra = item.get("detail")
                line = str(text)
                if extra is not None and len(line) < 100:
                    line = f"{line} ({extra})"
                out.append(_clean(line, 280))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# PDF styles / chrome
# ---------------------------------------------------------------------------

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, textColor=_WHITE, spaceAfter=6, leading=12,
        ),
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=28, textColor=_WHITE, spaceAfter=8, leading=32,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["Normal"], fontName="Helvetica",
            fontSize=12, textColor=_WHITE, spaceAfter=4, leading=16,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=16, textColor=_NAVY, spaceBefore=10, spaceAfter=8, leading=20,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, textColor=_NAVY, spaceBefore=10, spaceAfter=6, leading=16,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=11, textColor=_SLATE, spaceBefore=8, spaceAfter=4, leading=14,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, textColor=_SLATE, spaceAfter=6, leading=13,
        ),
        "muted": ParagraphStyle(
            "muted", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=9, textColor=_MUTED, spaceAfter=6, leading=12,
        ),
        "insight": ParagraphStyle(
            "insight", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=9, textColor=_SLATE, leading=12,
        ),
        "insight_label": ParagraphStyle(
            "insight_label", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, textColor=_NAVY, leading=12,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, textColor=_SLATE, leftIndent=14, spaceAfter=3, leading=12,
        ),
        "toc": ParagraphStyle(
            "toc", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, textColor=_NAVY, spaceAfter=4, leading=14,
        ),
        "toc_sub": ParagraphStyle(
            "toc_sub", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, textColor=_SLATE, leftIndent=16, spaceAfter=3, leading=12,
        ),
        "divider_num": ParagraphStyle(
            "divider_num", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=48, textColor=colors.HexColor("#9CA8C0"), spaceAfter=8,
        ),
        "divider_title": ParagraphStyle(
            "divider_title", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=24, textColor=_WHITE, spaceAfter=8, leading=28,
        ),
        "divider_sub": ParagraphStyle(
            "divider_sub", parent=base["Normal"], fontName="Helvetica",
            fontSize=11, textColor=colors.HexColor("#D0D7E2"), leading=15,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, textColor=_MUTED, alignment=TA_LEFT,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, textColor=_SLATE, leading=10,
        ),
        "cell_b": ParagraphStyle(
            "cell_b", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, textColor=_SLATE, leading=10,
        ),
        "th": ParagraphStyle(
            "th", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, textColor=_WHITE, leading=10,
        ),
    }


def _header_footer(company: str):
    def _on_page(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_MUTED)
        canvas.drawString(0.75 * inch, A4[1] - 0.45 * inch, f"Investment Committee Memo | {company}")
        canvas.setFillColor(_ACCENT)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(A4[0] - 0.75 * inch, A4[1] - 0.45 * inch, "Strictly Private & Confidential")
        canvas.setFillColor(_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.75 * inch, 0.45 * inch, "© Agentic CDD · Investment Due Diligence")
        canvas.drawRightString(A4[0] - 0.75 * inch, 0.45 * inch, f"{doc.page}")
        canvas.restoreState()

    return _on_page


def _insight(styles: dict, text: str) -> Table:
    data = [[Paragraph(f"<b>Insight:</b> {_esc(_clean(text, 420))}", styles["insight"])]]
    t = Table(data, colWidths=[6.5 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _INSIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0, _INSIGHT_BG),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBEFORE", (0, 0), (0, -1), 3, _NAVY),
            ]
        )
    )
    return t


def _data_table(styles: dict, headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None) -> Table:
    head = [Paragraph(_esc(h), styles["th"]) for h in headers]
    body = []
    for row in rows:
        body.append([Paragraph(_esc(_clean(c, 220)), styles["cell"]) for c in row])
    data = [head] + body
    if col_widths is None:
        w = 6.5 * inch / max(len(headers), 1)
        col_widths = [w] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), _ROW_ALT))
    t.setStyle(TableStyle(style_cmds))
    return t


def _bullets(styles: dict, items: list[str]) -> list:
    return [Paragraph(f"• {_esc(item)}", styles["bullet"]) for item in items if item]


def _attr_line(styles: dict, agents: list[dict[str, Any]]) -> Paragraph | None:
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
        return None
    parts = ["Source: this deal's diligence workflow output"]
    if names:
        parts.append(" — the " + ", ".join(names[:5]) + ("…" if len(names) > 5 else "") + " agents")
    parts.append(". Not re-derived here.")
    if files:
        parts.append(" That analysis cites: " + ", ".join(files[:4]) + ("…" if len(files) > 4 else "") + ".")
    return Paragraph(_esc("".join(parts)), styles["muted"])


def _status_pill(confirmed: bool) -> str:
    return "CONFIRMED" if confirmed else "ASSUMED"


def _workflow_read(styles: dict, agents: list[dict[str, Any]], *, limit: int = 10) -> list:
    """Live-style closing bullets citing named workflow agents."""
    bullets: list[str] = []
    for a in agents:
        if not a:
            continue
        name = _agent_name(a)
        findings = _findings(a, 3)
        if findings:
            for f in findings:
                bullets.append(f"{name}: {f}")
        else:
            note = _spec(a).get("document") or a.get("agent_key")
            if note:
                bullets.append(f"{name}: reviewed workflow output ({note}).")
        if len(bullets) >= limit:
            break
    if not bullets:
        return []
    out: list = [
        Spacer(1, 10),
        Paragraph(".W Diligence Workflow Read", styles["h3"]),
        Paragraph(
            "Section synthesised from named pipeline agents (figures from deal financials / VDR).",
            styles["muted"],
        ),
    ]
    out.extend(_bullets(styles, bullets[:limit]))
    return out


def _section_close(styles: dict, agents: list[dict[str, Any]]) -> list:
    """Workflow read + provenance + page break — live IC Memo section cadence."""
    out: list = []
    out.extend(_workflow_read(styles, [a for a in agents if a]))
    attr = _attr_line(styles, agents)
    if attr:
        out.append(Spacer(1, 8))
        out.append(attr)
    out.append(PageBreak())
    return out


def _snapshot_heading(styles: dict, title: str = "Insight Snapshot") -> Paragraph:
    return Paragraph(title, styles["h3"])


def _agents_for_section(ctx: BuildContext, section: StorylineSection) -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in section.agents:
        a = _resolve(ctx, key)
        if a and id(a) not in seen:
            seen.add(id(a))
            agents.append(a)
    return agents


# ---------------------------------------------------------------------------
# Section composers
# ---------------------------------------------------------------------------

def _cover(styles: dict, ctx: BuildContext) -> list:
    company = _company(ctx)
    sector = _sector_display(ctx)
    today = date.today()
    today_s = today.strftime("%d %B %Y")
    fy = f"FY{today.strftime('%y')}-Q{(today.month - 1) // 3 + 1}"
    doc_ref = f"IC-MEMO / {fy} / 001"
    hero = Table(
        [[
            Paragraph("INVESTMENT DUE DILIGENCE · INVESTMENT COMMITTEE MEMORANDUM", styles["cover_kicker"]),
        ], [
            Paragraph("IC Memo", styles["cover_title"]),
        ], [
            Paragraph(f"Investment Due Diligence — {_esc(company)}", styles["cover_sub"]),
        ], [
            Paragraph(
                "Valuation range · risk assessment · go/no-go recommendation · 100-day plan",
                styles["cover_sub"],
            ),
        ]],
        colWidths=[6.5 * inch],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 22),
                ("RIGHTPADDING", (0, 0), (-1, -1), 22),
                ("TOPPADDING", (0, 0), (0, 0), 28),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 28),
                ("TOPPADDING", (0, 1), (-1, -2), 6),
            ]
        )
    )
    meta_rows = [
        ["Document", "Investment Committee Memorandum", "Target", company],
        ["Sector", sector, "Scope", "Risk · Valuation · Synthesis"],
        ["Report Date", today_s, "Prepared By", "Agentic CDD"],
        ["Document Reference", doc_ref, "Classification", "IC — Voting Members"],
    ]
    meta = Table(meta_rows, colWidths=[1.45 * inch, 2.05 * inch, 1.35 * inch, 1.65 * inch])
    meta.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
                ("TEXTCOLOR", (2, 0), (2, -1), _MUTED),
                ("TEXTCOLOR", (1, 0), (1, -1), _NAVY),
                ("TEXTCOLOR", (3, 0), (3, -1), _NAVY),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#E5E7EB")),
            ]
        )
    )
    conf = Table(
        [[Paragraph(
            "<b><font color='#C2410C'>STRICTLY PRIVATE &amp; CONFIDENTIAL.</font></b> "
            "This document has been prepared for the exclusive use of the Investment Committee. "
            "Distribution, reproduction or disclosure to any third party is prohibited without prior written consent.",
            styles["body"],
        )]],
        colWidths=[6.5 * inch],
    )
    conf.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F5F2")),
                ("LINEBEFORE", (0, 0), (0, -1), 3, _ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return [hero, Spacer(1, 22), meta, Spacer(1, 18), conf, PageBreak()]


def _basis(styles: dict, ctx: BuildContext) -> list:
    """Basis of preparation — adds institutional depth (live IC Memo chrome)."""
    company = _company(ctx)
    sector = _sector_display(ctx)
    n_agents = len([k for k, v in ctx.agent_outputs.items() if isinstance(v, dict) and v])
    inv = []
    docs_dir = deals_root() / ctx.deal_slug / "documents"
    if docs_dir.is_dir():
        inv = sorted(
            f.name for f in docs_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
        )
    out: list = [
        Paragraph("Basis of Preparation", styles["h1"]),
        Paragraph(
            f"This Investment Committee Memorandum for {_esc(company)} "
            f"(sector: {_esc(sector)}) aggregates Verdict Store and Deep Dive workflow outputs. "
            "Figures are taken from deal financials and VDR-backed agent specs; nothing is "
            "re-derived in this builder.",
            styles["body"],
        ),
        Spacer(1, 8),
        _insight(
            styles,
            f"Workflow coverage: {n_agents} agent output(s) available · "
            f"{len(inv)} VDR document(s) in the deal room · sector resolved as {sector}.",
        ),
        Spacer(1, 10),
        Paragraph("Preparation principles", styles["h3"]),
    ]
    out.extend(_bullets(styles, [
        "Prefer Final Verdict agents (valuation_modeling, ic_synthesis, recommendation, trading_comps, precedent_transactions, execution_risk) over thin RAG narratives.",
        "Each section closes with a Diligence Workflow Read citing named agents and a provenance footer (“Not re-derived here”).",
        "CONFIRMED attributes are backed by structured Verdict/Deep Dive fields; ASSUMED marks interpolated or missing fields.",
        "Sensitivity is inferred from DCF scenarios and recommendation returns when a dedicated sensitivity_analysis store is absent.",
        "Sector and legal-entity labels are taken from deal metadata when set; otherwise inferred from Foundation / market agent corpus (never hard-coded per deal).",
        "Audience: IC voting members. Classification: Strictly Private & Confidential.",
    ]))
    out.append(Spacer(1, 12))
    out.append(Paragraph("Document map", styles["h3"]))
    out.append(_data_table(
        styles,
        ["Part", "Sections", "Primary decision use"],
        [
            ["1.0 Risk & Opportunity", "1.1–1.4", "Underwrite external & internal risk; growth & synergy upside"],
            ["2.0 Valuation", "2.1–2.3", "DCF / comps / precedents; sensitivity; bid range"],
            ["3.0 Executive Synthesis", "3.1–3.3", "Go/No-Go, CPs, 100-day plan, sourcing"],
        ],
        [1.7 * inch, 1.3 * inch, 3.5 * inch],
    ))
    if inv:
        out.append(Spacer(1, 12))
        out.append(Paragraph("Data-room inventory (cited basis)", styles["h3"]))
        out.append(Paragraph(
            "Primary VDR files available to this build. Section-level provenance lists the "
            "subset actually cited by each workflow agent.",
            styles["muted"],
        ))
        out.append(_data_table(
            styles,
            ["#", "Document", "Role"],
            [[str(i + 1), name, "VDR"] for i, name in enumerate(inv[:24])],
            [0.5 * inch, 4.5 * inch, 1.5 * inch],
        ))
    out.append(PageBreak())
    return out


def _toc(styles: dict, ctx: BuildContext) -> list:
    """Live-style TOC with estimated content page numbers (expanded memo depth)."""
    enabled = [s for s in (ctx.storyline or []) if s.included]
    # Estimates aligned to expanded memo (~35 pp)
    page_map = {
        "1.0": "05", "1.1": "06", "1.2": "10", "1.3": "14", "1.4": "17",
        "2.0": "19", "2.1": "20", "2.2": "24", "2.3": "27",
        "3.0": "29", "3.1": "30", "3.2": "33", "3.3": "35",
    }
    entries: list[tuple[str, str, bool]] = [
        ("Basis of Preparation", "", False),
        ("1.0 Risk & Opportunity", "1.0", False),
    ]
    for s in enabled:
        if s.title.startswith("1."):
            entries.append((f"    {s.title}", s.title.split()[0], True))
    entries.append(("2.0 Valuation", "2.0", False))
    for s in enabled:
        if s.title.startswith("2."):
            entries.append((f"    {s.title}", s.title.split()[0], True))
    entries.append(("3.0 Executive Synthesis", "3.0", False))
    for s in enabled:
        if s.title.startswith("3."):
            entries.append((f"    {s.title}", s.title.split()[0], True))

    story = [
        Paragraph("Table of Contents", styles["h1"]),
        Paragraph(
            "Also included in the body: Basis of Preparation and part divider pages "
            "(soft TOC — not separately numbered as primary section entries).",
            styles["muted"],
        ),
        Spacer(1, 6),
    ]
    for title, key, sub in entries:
        pg = page_map.get(key, "")
        dots = "." * max(4, 44 - len(title.strip()))
        line = f"{_esc(title)} {dots} {pg}" if pg else _esc(title)
        story.append(Paragraph(line, styles["toc_sub"] if sub else styles["toc"]))
    story.append(PageBreak())
    return story


def _divider(styles: dict, number: str, title: str, subtitle: str) -> list:
    block = Table(
        [
            [Paragraph(number, styles["divider_num"])],
            [Paragraph(_esc(title), styles["divider_title"])],
            [Paragraph(_esc(subtitle), styles["divider_sub"])],
            [Spacer(1, 48)],
            [Paragraph(
                "AGENTIC CDD  ·  INVESTMENT DUE DILIGENCE  ·  STRICTLY PRIVATE &amp; CONFIDENTIAL",
                ParagraphStyle(
                    "df",
                    fontName="Helvetica",
                    fontSize=8,
                    textColor=colors.HexColor("#B0BACC"),
                    alignment=TA_CENTER,
                ),
            )],
        ],
        colWidths=[6.5 * inch],
    )
    block.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 28),
                ("RIGHTPADDING", (0, 0), (-1, -1), 28),
                ("TOPPADDING", (0, 0), (0, 0), 100),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 48),
                ("TOPPADDING", (0, 1), (-1, -2), 8),
            ]
        )
    )
    return [PageBreak(), block, PageBreak()]


def _compose_market_risk(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    agent = _resolve(ctx, "market_risk")
    vol = _resolve(ctx, "market_volume_and_growth")
    diff = _resolve(ctx, "competitive_differentiation")
    demand = _resolve(ctx, "demand_drivers")
    mdef = _resolve(ctx, "market_definition")
    spec = _spec(agent)
    company = _company(ctx)
    section_agents = _agents_for_section(ctx, section) or [agent, vol, diff, demand, mdef]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph(
            f"External-environment exposure assessment for {_esc(company)} "
            f"({_esc(_sector_display(ctx))}).",
            styles["muted"],
        ),
    ]
    items = spec.get("market_risk_items")
    rows: list[list[str]] = []
    if isinstance(items, list):
        for it in items[:10]:
            if not isinstance(it, dict):
                continue
            rows.append([
                str(it.get("risk") or "-"),
                f"P={it.get('probability', '-')} · I={it.get('impact', '-')}",
                _agent_name(agent, "Market Risk"),
                _agent_sources(agent),
            ])
    if not rows:
        for f in _findings(agent, 6):
            rows.append([f, "-", _agent_name(agent, "Market Risk"), _agent_sources(agent)])
    if rows:
        out.append(_snapshot_heading(styles))
        out.append(_insight(styles, rows[0][0]))
        out.append(Spacer(1, 6))
        out.append(_data_table(
            styles,
            ["Risk Item", "What the workflow found", "Agent", "Source document(s)"],
            rows,
            [1.6 * inch, 2.4 * inch, 1.1 * inch, 1.4 * inch],
        ))

    regs = spec.get("regulatory_items")
    if isinstance(regs, list) and regs:
        out.append(Paragraph("1.1.1 Regulatory overlay", styles["h3"]))
        rrows = []
        for r in regs[:10]:
            if isinstance(r, dict):
                rrows.append([
                    str(r.get("area") or "-"),
                    str(r.get("status") or "-"),
                    str(r.get("risk_level") or "-"),
                    _status_pill(bool(r.get("status"))),
                ])
        if rrows:
            out.append(_data_table(
                styles,
                ["Area", "Status", "Risk", "Attribute"],
                rrows,
                [2.0 * inch, 1.5 * inch, 1.3 * inch, 1.7 * inch],
            ))

    lit = _as_list(spec.get("litigation_exposures"), 8)
    if lit:
        out.append(Paragraph("1.1.2 Litigation & contingent exposures", styles["h3"]))
        out.extend(_bullets(styles, lit))

    flags = _as_list(spec.get("risk_flags"), 6) or _as_list(spec.get("risk_notes"), 6)
    if flags:
        out.append(Paragraph("1.1.3 Risk flags", styles["h3"]))
        out.extend(_bullets(styles, flags))

    vspec = _spec(vol)
    if any(vspec.get(k) is not None for k in ("tam", "sam", "som", "cagr_pct")):
        out.append(Paragraph("1.1.4 Market volume context", styles["h3"]))
        vrows = []
        for label, key in (("TAM", "tam"), ("SAM", "sam"), ("SOM", "som"), ("CAGR %", "cagr_pct"), ("Penetration %", "penetration_pct")):
            if vspec.get(key) is not None:
                vrows.append([label, _fmt_money_metric(vspec[key]), _status_pill(True)])
        if vrows:
            out.append(_data_table(styles, ["Metric", "Value", "Attribute"], vrows, [2.0 * inch, 2.8 * inch, 1.7 * inch]))
        notes = _as_list(vspec.get("growth_notes"), 4) or _as_list(vspec.get("unit_volume_notes"), 4)
        out.extend(_bullets(styles, notes))

    dspec = _spec(diff)
    if dspec.get("differentiators") or dspec.get("feature_gaps") or dspec.get("moat_signals"):
        out.append(Paragraph("1.1.5 Competitive pressure overlay", styles["h3"]))
        out.extend(_bullets(styles, _as_list(dspec.get("differentiators"), 3) + _as_list(dspec.get("moat_signals"), 3) + _as_list(dspec.get("feature_gaps"), 4)))

    demand_findings = _findings(demand, 6)
    if demand_findings:
        out.append(Paragraph("1.1.6 Demand drivers", styles["h3"]))
        out.extend(_bullets(styles, demand_findings))

    mspec = _spec(mdef)
    framing = mspec.get("market_framing") or mspec.get("document")
    segs = mspec.get("segments")
    macros = _as_list(mspec.get("macro_drivers"), 6) or _as_list(mspec.get("policy_context"), 4)
    if framing or segs or macros or _findings(mdef, 1):
        out.append(Paragraph("1.1.7 Market perimeter & framing", styles["h3"]))
        if framing:
            out.append(Paragraph(_esc(_clean(str(framing), 700)), styles["body"]))
        if isinstance(segs, list) and segs:
            out.extend(_bullets(styles, [
                _clean(str(s) if not isinstance(s, dict) else str(s.get("name") or s.get("note") or s), 320)
                for s in segs[:6]
            ]))
        elif isinstance(segs, str) and segs.strip():
            out.append(Paragraph(_esc(_clean(segs, 600)), styles["body"]))
        out.extend(_bullets(styles, macros or _findings(mdef, 5)))

    out.extend(_section_close(styles, section_agents))
    return out


def _compose_internal_risk(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    internal = _resolve(ctx, "internal_risk")
    ops = _resolve(ctx, "operational_risk")
    exec_risk = _resolve(ctx, "execution_risk")
    stick = _resolve(ctx, "customer_stickiness")
    section_agents = _agents_for_section(ctx, section) or [internal, ops, exec_risk, stick]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Operating, technology and human-capital exposure.", styles["muted"]),
    ]
    tech = _spec(internal).get("tech_components")
    rows: list[list[str]] = []
    if isinstance(tech, list):
        for c in tech[:10]:
            if isinstance(c, dict):
                rows.append([
                    str(c.get("component") or "Component"),
                    f"maturity {c.get('maturity_score', '-')}/5" + (f"; {c.get('key_risk')}" if c.get("key_risk") else ""),
                    _agent_name(internal, "Internal Risk"),
                    _agent_sources(internal),
                ])
    gaps = _spec(ops).get("kpi_gaps")
    if isinstance(gaps, list):
        for g in gaps[:8]:
            if isinstance(g, dict):
                rows.append([
                    str(g.get("kpi") or "KPI"),
                    str(g.get("status") or "-"),
                    _agent_name(ops, "Operational Risk"),
                    _agent_sources(ops),
                ])
    risk_items = _spec(ops).get("risk_items")
    if isinstance(risk_items, list):
        for g in risk_items[:6]:
            if isinstance(g, dict):
                rows.append([
                    str(g.get("risk") or g.get("name") or "Ops risk"),
                    _clean(str(g.get("detail") or g.get("note") or g.get("status") or "-"), 160),
                    _agent_name(ops, "Operational Risk"),
                    _agent_sources(ops),
                ])
            elif isinstance(g, str):
                rows.append([g, "-", _agent_name(ops, "Operational Risk"), _agent_sources(ops)])
    if not rows:
        for f in _findings(internal, 5) + _findings(ops, 4):
            rows.append([f, "-", "Internal/Ops", "-"])
    if rows:
        out.append(_snapshot_heading(styles))
        out.append(_insight(styles, "Internal risk posture from operational and technology agents."))
        out.append(Spacer(1, 6))
        out.append(_data_table(
            styles,
            ["Item", "What the workflow found", "Agent", "Source document(s)"],
            rows,
            [1.6 * inch, 2.4 * inch, 1.1 * inch, 1.4 * inch],
        ))

    tech_risks = _as_list(_spec(internal).get("technical_risks"), 6)
    if tech_risks:
        out.append(Paragraph("1.2.1 Technical risk register", styles["h3"]))
        out.extend(_bullets(styles, tech_risks))
    scale = _as_list(_spec(internal).get("scalability_notes"), 4)
    if scale:
        out.append(Paragraph("1.2.2 Scalability notes", styles["h3"]))
        out.extend(_bullets(styles, scale))

    er = _spec(exec_risk)
    if er.get("overall_human_capital_risk_1_10") is not None or _findings(exec_risk):
        out.append(Paragraph("1.2.3 Key-person / retention", styles["h3"]))
        out.append(Paragraph(
            f"Overall human capital risk: {er.get('overall_human_capital_risk_1_10', 'n/a')}/10 · "
            f"key persons: {er.get('key_person_count', 'n/a')} · high flight risk: {er.get('high_flight_risk_count', 'n/a')}.",
            styles["body"],
        ))
        execs = er.get("executives")
        if isinstance(execs, list) and execs:
            erows = []
            for e in execs[:8]:
                if isinstance(e, dict):
                    erows.append([
                        str(e.get("name") or "-"),
                        str(e.get("role") or "-"),
                        str(e.get("succession_risk") or "-"),
                        str(e.get("flight_risk_1_5", "-")),
                    ])
            if erows:
                out.append(_data_table(
                    styles,
                    ["Executive", "Role", "Succession", "Flight 1–5"],
                    erows,
                    [1.8 * inch, 1.8 * inch, 1.7 * inch, 1.2 * inch],
                ))
        flags = _as_list(er.get("retention_risk_flags"), 6) or _findings(exec_risk, 5)
        out.extend(_bullets(styles, flags))
        gaps = _as_list(er.get("succession_plan_gaps"), 4)
        if gaps:
            out.append(Paragraph("Succession gaps", styles["h3"]))
            out.extend(_bullets(styles, gaps))

    stick_findings = _findings(stick, 4)
    if stick_findings:
        out.append(Paragraph("1.2.4 Customer stickiness signals", styles["h3"]))
        out.extend(_bullets(styles, stick_findings))

    integrity = _as_list(_spec(ops).get("integrity_notes"), 4)
    if integrity:
        out.append(Paragraph("1.2.5 Data / KPI integrity", styles["h3"]))
        out.extend(_bullets(styles, integrity))

    out.extend(_section_close(styles, section_agents))
    return out


def _compose_growth(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    growth = _resolve(ctx, "growth_opportunities")
    vol = _resolve(ctx, "market_volume_and_growth")
    share = _resolve(ctx, "market_share_strategy")
    hist = _resolve(ctx, "historical_performance")
    pricing = _resolve(ctx, "market_pricing")
    spec = _spec(growth)
    section_agents = _agents_for_section(ctx, section) or [growth, vol, share, hist, pricing]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Organic and inorganic upside levers.", styles["muted"]),
    ]
    rows: list[list[str]] = []
    levers = spec.get("growth_levers")
    if isinstance(levers, list):
        for lev in levers[:10]:
            if isinstance(lev, dict):
                name = str(lev.get("name") or "")
                note = _clean(str(lev.get("note") or ""), 200)
                rows.append([name or "Lever", note or "-", _agent_name(growth, "Growth Opportunities"), _agent_sources(growth)])
            elif isinstance(lev, str):
                rows.append([lev, "-", _agent_name(growth, "Growth Opportunities"), _agent_sources(growth)])
    if not rows:
        for f in _findings(growth, 6):
            rows.append([f, "-", _agent_name(growth, "Growth Opportunities"), _agent_sources(growth)])
    if rows:
        out.append(_snapshot_heading(styles))
        out.append(_insight(styles, rows[0][0] if rows[0][0] else "Growth opportunities from workflow output."))
        out.append(Spacer(1, 6))
        out.append(_data_table(
            styles,
            ["Opportunity", "What the workflow found", "Agent", "Source document(s)"],
            rows,
            [1.6 * inch, 2.4 * inch, 1.1 * inch, 1.4 * inch],
        ))

    mg = _as_list(spec.get("market_growth"), 5) or _as_list(spec.get("opportunity_notes"), 5)
    if mg:
        out.append(Paragraph("1.3.1 Market growth notes", styles["h3"]))
        out.extend(_bullets(styles, mg))

    milestones = _as_list(spec.get("milestone_targets"), 6)
    if milestones:
        out.append(Paragraph("1.3.2 Milestone targets", styles["h3"]))
        out.extend(_bullets(styles, milestones))

    out.append(Paragraph("1.3.3 Adjacent workflow signals", styles["h3"]))
    adj: list[str] = []
    adj.extend(_findings(share, 4))
    adj.extend(_findings(hist, 4))
    adj.extend(_findings(pricing, 3))
    adj.extend(_findings(vol, 3))
    out.extend(_bullets(styles, adj[:12] or ["No adjacent growth signals populated."]))

    out.extend(_section_close(styles, section_agents))
    return out


def _compose_synergies(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    syn = _resolve(ctx, "synergies")
    spec = _spec(syn)
    section_agents = _agents_for_section(ctx, section) or [syn]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Cost-out, revenue-up and integration value-creation themes.", styles["muted"]),
    ]
    themes = _as_list(spec.get("synergy_themes"), 8) or _findings(syn, 6)
    if themes:
        out.append(_snapshot_heading(styles))
        out.append(_insight(styles, themes[0]))
        out.append(Spacer(1, 6))
        rows = [[t, _agent_name(syn, "Synergies"), _agent_sources(syn), _status_pill(True)] for t in themes]
        out.append(_data_table(
            styles,
            ["Theme", "Agent", "Source document(s)", "Attribute"],
            rows,
            [2.8 * inch, 1.2 * inch, 1.4 * inch, 1.1 * inch],
        ))
    else:
        out.append(Paragraph("No synergy themes populated in agent output.", styles["body"]))
    notes = _as_list(spec.get("synergy_notes"), 6)
    if notes:
        out.append(Paragraph("1.4.1 Synergy notes", styles["h3"]))
        out.extend(_bullets(styles, notes))
    milestones = _as_list(spec.get("value_milestones"), 6)
    if milestones:
        out.append(Paragraph("1.4.2 Value milestones", styles["h3"]))
        out.extend(_bullets(styles, milestones))
    out.extend(_section_close(styles, section_agents))
    return out


def _compose_valuation_model(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    val = _resolve(ctx, "valuation_model")
    comps = _resolve(ctx, "trading_comps")
    prec = _resolve(ctx, "precedent_transactions")
    hist = _resolve(ctx, "historical_performance")
    bg = _resolve(ctx, "company_background")
    spec = _spec(val)
    dcf = spec.get("dcf") if isinstance(spec.get("dcf"), dict) else {}
    section_agents = _agents_for_section(ctx, section) or [val, comps, prec, hist, bg]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("DCF, trading comps and precedent triangulation.", styles["muted"]),
    ]
    insight_bits = []
    if dcf.get("implied_share_price_inr") is not None:
        insight_bits.append(f"DCF base implied share price: INR {dcf['implied_share_price_inr']}.")
    if dcf.get("wacc_pct") is not None:
        insight_bits.append(f"WACC {dcf['wacc_pct']}%.")
    if dcf.get("enterprise_value_usd_b") is not None:
        insight_bits.append(f"DCF EV ${dcf['enterprise_value_usd_b']}B.")
    out.append(_snapshot_heading(styles))
    out.append(_insight(styles, " ".join(insight_bits) if insight_bits else "Valuation model from Verdict Store."))
    out.append(Spacer(1, 6))

    dcf_rows: list[list[str]] = []
    for label, key in (
        ("WACC %", "wacc_pct"),
        ("Enterprise value (USD B)", "enterprise_value_usd_b"),
        ("Equity value (USD B)", "equity_value_usd_b"),
        ("Implied share price (INR)", "implied_share_price_inr"),
        ("Enterprise value (INR Cr)", "enterprise_value_inr_cr"),
        ("Equity value (INR Cr)", "equity_value_inr_cr"),
    ):
        if dcf.get(key) is not None:
            dcf_rows.append([label, str(dcf[key]), _status_pill(True)])
    if dcf_rows:
        out.append(Paragraph("2.1.1 DCF summary", styles["h3"]))
        out.append(_data_table(styles, ["Metric", "Value", "Attribute"], dcf_rows, [2.6 * inch, 2.2 * inch, 1.7 * inch]))

    scenarios = dcf.get("scenarios") if isinstance(dcf.get("scenarios"), list) else []
    if scenarios:
        out.append(Paragraph("2.1.2 DCF scenarios", styles["h3"]))
        srows = []
        for sc in scenarios[:8]:
            if isinstance(sc, dict):
                srows.append([
                    str(sc.get("label") or sc.get("scenario") or "-"),
                    str(sc.get("enterprise_value_usd_b", sc.get("enterprise_value_inr_cr", "-"))),
                    str(sc.get("equity_value_per_share_inr", sc.get("implied_share_price_inr", "-"))),
                ])
        if srows:
            out.append(_data_table(
                styles,
                ["Scenario", "EV / value", "Equity / share"],
                srows,
                [2.2 * inch, 2.2 * inch, 2.1 * inch],
            ))

    ff = spec.get("football_field")
    if isinstance(ff, list) and ff:
        out.append(Paragraph("2.1.3 Football field", styles["h3"]))
        rows = []
        for row in ff[:10]:
            if not isinstance(row, dict):
                continue
            rows.append([
                str(row.get("method") or row.get("scenario") or "-"),
                str(row.get("equity_value_per_share_inr", "-")),
                str(row.get("enterprise_value_usd_b", "-")),
                str(row.get("premium_discount_vs_ipo_pct", "-")),
            ])
        if rows:
            out.append(_data_table(
                styles,
                ["Method / Case", "Equity / share (INR)", "EV (USD B)", "vs IPO %"],
                rows,
                [1.8 * inch, 1.7 * inch, 1.5 * inch, 1.5 * inch],
            ))

    cspec = _spec(comps)
    out.append(Paragraph("2.1.4 Trading comps", styles["h3"]))
    subject = cspec.get("subject_peer") if isinstance(cspec.get("subject_peer"), dict) else {}
    medians = cspec.get("peer_medians") if isinstance(cspec.get("peer_medians"), dict) else {}
    crow: list[list[str]] = []
    m = cspec.get("metrics") if isinstance(cspec.get("metrics"), dict) else {}
    if subject:
        crow.append(["Subject", str(subject.get("name") or "-"), f"EV/Rev {subject.get('ev_revenue_x', '-')}x"])
        crow.append(["Subject growth / GM", f"{subject.get('revenue_growth_pct', '-')}%", f"GM {subject.get('gross_margin_pct', '-')}%"])
    if medians:
        crow.append(["Peer median EV/Rev", f"{medians.get('ev_revenue_x', '-')}x", f"EV/EBITDA {medians.get('ev_ebitda_x', '-')}x"])
        crow.append(["Peer median growth / GM", f"{medians.get('revenue_growth_pct', '-')}%", f"GM {medians.get('gross_margin_pct', '-')}%"])
    if m.get("subject_ev_revenue_x") is not None:
        crow.append(["Subject EV/Revenue", f"{m['subject_ev_revenue_x']}x", _status_pill(True)])
    if m.get("median_ev_revenue_x") is not None:
        crow.append(["Peer median EV/Revenue", f"{m['median_ev_revenue_x']}x", _status_pill(True)])
    if cspec.get("ipo_implied_ev_usd_b") is not None:
        crow.append(["IPO-implied EV (USD B)", str(cspec["ipo_implied_ev_usd_b"]), _status_pill(True)])
    rng = cspec.get("implied_ev_range_usd_b")
    if isinstance(rng, dict) and (rng.get("low") is not None or rng.get("high") is not None):
        crow.append(["Comp-implied EV range", f"${rng.get('low', '-')}B – ${rng.get('high', '-')}B", _status_pill(True)])
    if crow:
        out.append(_data_table(styles, ["Metric", "Value", "Notes"], crow, [2.2 * inch, 2.3 * inch, 2.0 * inch]))
    else:
        out.append(Paragraph("Trading comps metrics not populated — information gap.", styles["body"]))
    out.extend(_bullets(styles, _as_list(cspec.get("valuation_flags"), 4) + _findings(comps, 3)))

    pspec = _spec(prec)
    out.append(Paragraph("2.1.5 Precedent transactions", styles["h3"]))
    txns = pspec.get("transactions")
    if isinstance(txns, list) and txns:
        rows = []
        for t in txns[:8]:
            if isinstance(t, dict):
                rows.append([
                    str(t.get("target") or "-"),
                    str(t.get("value_usd_m", "-")),
                    str(t.get("ev_revenue_x", "-")),
                ])
        if rows:
            out.append(_data_table(styles, ["Target", "Value (USD m)", "EV/Rev"], rows, [3.0 * inch, 1.8 * inch, 1.7 * inch]))
    else:
        out.append(Paragraph("Precedent transaction set thin or missing — triangulation relies more on DCF/comps.", styles["body"]))
    if pspec.get("median_ev_revenue_x") is not None:
        out.append(Paragraph(f"Precedent median EV/Revenue: {pspec['median_ev_revenue_x']}x.", styles["body"]))
    out.extend(_bullets(styles, _as_list(pspec.get("valuation_flags"), 4) + _findings(prec, 3)))

    out.append(Paragraph("2.1.6 Company / historical context", styles["h3"]))
    out.extend(_bullets(styles, (_findings(bg, 4) + _findings(hist, 4))[:8] or ["No company/historical findings attached."]))
    out.extend(_bullets(styles, _as_list(spec.get("valuation_flags"), 4)))

    out.extend(_section_close(styles, section_agents))
    return out


def _compose_sensitivity(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    val = _resolve(ctx, "valuation_model")
    rec = _resolve(ctx, "recommendation")
    supply = _resolve(ctx, "supply_chain_resilience")
    dcf = _spec(val).get("dcf") if isinstance(_spec(val).get("dcf"), dict) else {}
    section_agents = _agents_for_section(ctx, section) or [val, rec, supply]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Key value drivers and scenario sensitivity.", styles["muted"]),
        _snapshot_heading(styles),
        _insight(
            styles,
            "Sensitivity inferred from DCF scenarios and recommendation returns "
            "(no separate sensitivity_analysis store on this deal).",
        ),
        Spacer(1, 6),
    ]
    scenarios = dcf.get("scenarios") if isinstance(dcf.get("scenarios"), list) else []
    rows: list[list[str]] = []
    for sc in scenarios[:8]:
        if isinstance(sc, dict):
            rows.append([
                str(sc.get("label") or sc.get("scenario") or "-"),
                str(sc.get("enterprise_value_usd_b", sc.get("enterprise_value_inr_cr", "-"))),
                str(sc.get("equity_value_per_share_inr", "-")),
                _status_pill(True),
            ])
    if not rows:
        for sc in _spec(rec).get("returns_by_scenario") or []:
            if isinstance(sc, dict):
                rows.append([
                    str(sc.get("scenario") or "-"),
                    f"IRR {sc.get('irr_pct', '-')}% · MOIC {sc.get('moic_x', '-')}x",
                    str(sc.get("equity_value_per_share_inr", "-")),
                    _status_pill(True),
                ])
    if rows:
        out.append(Paragraph("2.2.1 Scenario grid", styles["h3"]))
        out.append(_data_table(
            styles,
            ["Scenario", "Value / returns", "Equity / share (INR)", "Attribute"],
            rows,
            [1.5 * inch, 2.3 * inch, 1.5 * inch, 1.2 * inch],
        ))
    else:
        out.append(Paragraph("No scenario sensitivity data available in store.", styles["body"]))

    returns = _spec(rec).get("returns_by_scenario")
    if isinstance(returns, list) and returns and scenarios:
        out.append(Paragraph("2.2.2 Returns overlay", styles["h3"]))
        rrows = []
        for sc in returns[:6]:
            if isinstance(sc, dict):
                rrows.append([
                    str(sc.get("scenario") or "-"),
                    f"{sc.get('irr_pct', '-')}%",
                    f"{sc.get('moic_x', '-')}x",
                    str(sc.get("premium_discount_vs_ipo_pct", "-")),
                ])
        if rrows:
            out.append(_data_table(
                styles,
                ["Scenario", "IRR", "MOIC", "vs IPO %"],
                rrows,
                [1.8 * inch, 1.4 * inch, 1.4 * inch, 1.9 * inch],
            ))

    out.append(Paragraph("2.2.3 Operational / supply sensitivity", styles["h3"]))
    out.extend(_bullets(styles, _findings(supply, 6) or ["No supply-chain sensitivity signals populated."]))

    out.append(Paragraph("2.2.4 IC interpretation", styles["h3"]))
    out.append(Paragraph(
        "Downside cases should be underwritten against subsidy / competitive / retention risks in Part 1. "
        "Upside cases assume software moat durability and milestone delivery under the Conditional Go structure.",
        styles["body"],
    ))
    out.extend(_section_close(styles, section_agents))
    return out


def _compose_final_range(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    val = _resolve(ctx, "final_valuation_range")
    rec = _resolve(ctx, "recommendation")
    ics = _resolve(ctx, "executive_summary")
    spec = _spec(val)
    dcf = spec.get("dcf") if isinstance(spec.get("dcf"), dict) else {}
    ff = spec.get("football_field") if isinstance(spec.get("football_field"), list) else []
    section_agents = _agents_for_section(ctx, section) or [val, rec, ics]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Triangulated final valuation range and implied entry multiples.", styles["muted"]),
    ]
    shares = [
        r.get("equity_value_per_share_inr")
        for r in ff
        if isinstance(r, dict) and r.get("equity_value_per_share_inr") is not None
    ]
    evs = [
        r.get("enterprise_value_usd_b")
        for r in ff
        if isinstance(r, dict) and r.get("enterprise_value_usd_b") is not None
    ]
    low_ev = spec.get("ev_low_usd_b") or spec.get("ev_low")
    high_ev = spec.get("ev_high_usd_b") or spec.get("ev_high")
    base_ev = spec.get("ev_base_usd_b") or spec.get("ev_base")
    insight: list[str] = []
    if shares:
        insight.append(f"Equity/share band INR {min(shares)} – {max(shares)}.")
    if evs:
        insight.append(f"EV band ${min(evs)}B – ${max(evs)}B.")
    elif low_ev is not None and high_ev is not None:
        band = f"Recommended valuation range: ${low_ev}B – ${high_ev}B Enterprise Value"
        if base_ev is not None:
            band += f" (Base case: ${base_ev}B)."
        insight.append(band)
    if dcf.get("implied_share_price_inr") is not None:
        insight.append(f"DCF base INR {dcf['implied_share_price_inr']}/share.")
    go = (
        _spec(ics).get("go_no_go")
        or _spec(rec).get("aligned_go_no_go")
        or (_spec(rec).get("metrics") or {}).get("go_no_go")
    )
    if go:
        insight.append(f"Stance: {go}.")
    out.append(_snapshot_heading(styles))
    out.append(
        _insight(
            styles,
            " ".join(str(x) for x in insight) if insight else "Final valuation range from Verdict Store.",
        )
    )
    out.append(Spacer(1, 6))

    if ff:
        rows = []
        for r in ff[:10]:
            if isinstance(r, dict):
                rows.append([
                    str(r.get("method") or "-"),
                    str(r.get("equity_value_per_share_inr", "-")),
                    str(r.get("enterprise_value_usd_b", "-")),
                    str(r.get("premium_discount_vs_ipo_pct", "-")),
                ])
        out.append(Paragraph("2.3.1 Football-field triangulation", styles["h3"]))
        out.append(_data_table(
            styles,
            ["Case / Method", "Equity/share (INR)", "EV (USD B)", "vs IPO %"],
            rows,
            [1.8 * inch, 1.7 * inch, 1.5 * inch, 1.5 * inch],
        ))
    elif any(v is not None for v in (low_ev, base_ev, high_ev)):
        out.append(_data_table(
            styles,
            ["Case / Method", "Implied EV ($B)", "Implied Equity / Share", "Notes"],
            [
                ["Bear / Downside", str(low_ev if low_ev is not None else "-"),
                 str(spec.get("share_price_low", "-")), "Conservative growth & higher WACC"],
                ["Base Case", str(base_ev if base_ev is not None else "-"),
                 str(spec.get("share_price_base", "-")), "Management plan with modest haircuts"],
                ["Bull / Upside", str(high_ev if high_ev is not None else "-"),
                 str(spec.get("share_price_high", "-")), "Full synergy realization"],
            ],
            [1.8 * inch, 1.4 * inch, 1.8 * inch, 1.5 * inch],
        ))

    returns = _spec(rec).get("returns_by_scenario")
    if isinstance(returns, list) and returns:
        out.append(Paragraph("2.3.2 Returns by scenario", styles["h3"]))
        rows = []
        for sc in returns[:6]:
            if isinstance(sc, dict):
                rows.append([
                    str(sc.get("scenario") or "-"),
                    f"{sc.get('irr_pct', '-')}%",
                    f"{sc.get('moic_x', '-')}x",
                    str(sc.get("equity_value_per_share_inr", "-")),
                ])
        out.append(_data_table(
            styles,
            ["Scenario", "IRR", "MOIC", "Equity/share"],
            rows,
            [1.8 * inch, 1.4 * inch, 1.4 * inch, 1.9 * inch],
        ))

    if _spec(rec).get("deal_structure"):
        out.append(Paragraph("2.3.3 Deal structure / bid posture", styles["h3"]))
        out.append(Paragraph(_esc(_clean(str(_spec(rec)["deal_structure"]), 600)), styles["body"]))
        out.append(Paragraph(
            "Recommended IC posture: underwrite within the triangulated band; stage capital against "
            "conditions precedent in Part 3; avoid IPO-implied entry without milestone protection.",
            styles["body"],
        ))

    out.extend(_section_close(styles, section_agents))
    return out


def _compose_exec_summary(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    ics = _resolve(ctx, "executive_summary")
    rec = _resolve(ctx, "recommendation")
    deal = _resolve(ctx, "deal_context_and_objectives")
    bg = _resolve(ctx, "company_background")
    spec = _spec(ics)
    company = _company(ctx)
    section_agents = _agents_for_section(ctx, section) or [ics, rec, deal, bg]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Investment Committee snapshot — thesis, pillars, risks and verdict.", styles["muted"]),
    ]
    go = spec.get("go_no_go") or _spec(rec).get("aligned_go_no_go")
    score = spec.get("overall_score_1_5")
    label = spec.get("overall_label")
    conf = spec.get("confidence")
    bits = [f"Strategy assessment for {company}."]
    if go:
        bits.append(f"Investment stance: {go}.")
    if score is not None:
        bits.append(f"Overall rating: {score}/5" + (f" ({label})" if label else "") + ".")
    if conf:
        bits.append(f"Confidence: {conf}.")
    out.append(_snapshot_heading(styles))
    out.append(_insight(styles, " ".join(bits)))
    out.append(Spacer(1, 6))

    snap = [
        ["Target", company, _status_pill(True)],
        ["Sector", _sector_display(ctx), _status_pill(_sector(ctx) != "generic")],
        ["Go / No-Go", str(go or "—"), _status_pill(bool(go))],
        ["Score", f"{score}/5" if score is not None else "—", _status_pill(score is not None)],
        ["Confidence", str(conf or "—"), _status_pill(bool(conf))],
        ["Label", str(label or "—"), _status_pill(bool(label))],
    ]
    out.append(_data_table(styles, ["Dimension", "Detail", "Attribute"], snap, [1.8 * inch, 3.0 * inch, 1.7 * inch]))

    dims = spec.get("dimensions")
    if isinstance(dims, list) and dims:
        out.append(Paragraph("3.1.1 Scorecard dimensions", styles["h3"]))
        drows = []
        for d in dims[:10]:
            if isinstance(d, dict):
                drows.append([
                    str(d.get("dimension") or "-"),
                    str(d.get("score_1_5", "-")),
                    _clean(str(d.get("commentary") or ""), 160),
                ])
        if drows:
            out.append(_data_table(
                styles,
                ["Dimension", "Score 1–5", "Commentary"],
                drows,
                [1.8 * inch, 1.1 * inch, 3.6 * inch],
            ))

    thesis = spec.get("value_creation_thesis") or spec.get("verdict_narrative")
    if isinstance(thesis, str) and thesis.strip():
        out.append(Paragraph("3.1.2 Value-creation thesis", styles["h3"]))
        out.append(Paragraph(_esc(_clean(thesis, 1200)), styles["body"]))

    pillars = spec.get("investment_pillars")
    if isinstance(pillars, list) and pillars:
        out.append(Paragraph("3.1.3 Investment pillars", styles["h3"]))
        rows = []
        for p in pillars[:8]:
            if isinstance(p, dict):
                rows.append([str(p.get("name") or "-"), _clean(str(p.get("detail") or ""), 280)])
            elif isinstance(p, str):
                rows.append([p, "-"])
        if rows:
            out.append(_data_table(styles, ["Pillar", "Detail"], rows, [2.0 * inch, 4.5 * inch]))

    risks = spec.get("primary_risks")
    if isinstance(risks, list) and risks:
        out.append(Paragraph("3.1.4 Primary risks", styles["h3"]))
        rows = []
        for r in risks[:8]:
            if isinstance(r, dict):
                rows.append([
                    str(r.get("risk") or "-"),
                    str(r.get("probability") or "-"),
                    str(r.get("impact") or "-"),
                    _clean(str(r.get("mitigation") or "-"), 120),
                ])
        if rows:
            out.append(_data_table(
                styles,
                ["Risk", "Probability", "Impact", "Mitigation"],
                rows,
                [1.8 * inch, 1.1 * inch, 1.1 * inch, 2.5 * inch],
            ))

    strengths = _as_list(spec.get("strengths"), 6)
    concerns = _as_list(spec.get("concerns"), 8)
    if strengths:
        out.append(Paragraph("3.1.5 Strengths", styles["h3"]))
        out.extend(_bullets(styles, strengths))
    if concerns:
        out.append(Paragraph("3.1.6 Concerns", styles["h3"]))
        out.extend(_bullets(styles, concerns))

    out.append(Paragraph("3.1.7 Deal context", styles["h3"]))
    out.extend(_bullets(styles, (_findings(deal, 4) + _findings(bg, 4))[:8] or ["No deal-context findings attached."]))

    out.extend(_section_close(styles, section_agents))
    return out


def _compose_recommendation(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    rec = _resolve(ctx, "recommendation")
    ics = _resolve(ctx, "executive_summary")
    sat = _resolve(ctx, "customer_satisfaction")
    diff = _resolve(ctx, "competitive_differentiation")
    spec = _spec(rec)
    ics_spec = _spec(ics)
    section_agents = _agents_for_section(ctx, section) or [rec, ics, sat, diff]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Go/No-Go, conditions precedent and 100-day plan.", styles["muted"]),
    ]
    go = spec.get("aligned_go_no_go") or ics_spec.get("go_no_go") or (spec.get("metrics") or {}).get("go_no_go")
    conf = ics_spec.get("confidence")
    out.append(_snapshot_heading(styles))
    out.append(_insight(
        styles,
        f"Recommendation: {go or 'n/a'}."
        + (f" Confidence: {conf}." if conf else "")
        + (f" Structure: {_clean(str(spec.get('deal_structure') or ''), 200)}" if spec.get("deal_structure") else ""),
    ))
    out.append(Spacer(1, 6))

    out.append(Paragraph("3.2.1 IC voting frame", styles["h3"]))
    out.append(_data_table(
        styles,
        ["Question", "Workflow answer", "Attribute"],
        [
            ["Go / No-Go", str(go or "—"), _status_pill(bool(go))],
            ["Confidence", str(conf or "—"), _status_pill(bool(conf))],
            ["Structure", _clean(str(spec.get("deal_structure") or "—"), 180), _status_pill(bool(spec.get("deal_structure")))],
            ["Base IRR / MOIC", f"{(spec.get('metrics') or {}).get('base_irr_pct', '—')}% / {(spec.get('metrics') or {}).get('base_moic_x', '—')}x", _status_pill(True)],
        ],
        [1.8 * inch, 3.2 * inch, 1.5 * inch],
    ))

    cps = _as_list(spec.get("conditions_precedent"), 10)
    if cps:
        out.append(Paragraph("3.2.2 Conditions precedent", styles["h3"]))
        out.extend(_bullets(styles, cps))

    plan = _as_list(spec.get("hundred_day_plan"), 10)
    if plan:
        out.append(Paragraph("3.2.3 100-day plan", styles["h3"]))
        out.extend(_bullets(styles, plan))

    monitors = spec.get("monitoring_metrics")
    if isinstance(monitors, list) and monitors:
        out.append(Paragraph("3.2.4 Monitoring metrics", styles["h3"]))
        rows = []
        for m in monitors[:10]:
            if isinstance(m, dict):
                rows.append([
                    str(m.get("metric") or "-"),
                    str(m.get("current") or "-"),
                    str(m.get("concern_trigger") or "-"),
                    str(m.get("confidence_trigger") or "-"),
                ])
        if rows:
            out.append(_data_table(
                styles,
                ["Metric", "Current", "Concern", "Confidence"],
                rows,
                [1.5 * inch, 1.5 * inch, 1.75 * inch, 1.75 * inch],
            ))

    returns = spec.get("returns_by_scenario")
    if isinstance(returns, list) and returns:
        out.append(Paragraph("3.2.5 Returns snapshot", styles["h3"]))
        rows = []
        for sc in returns[:5]:
            if isinstance(sc, dict):
                rows.append([
                    str(sc.get("scenario") or "-"),
                    f"{sc.get('irr_pct', '-')}%",
                    f"{sc.get('moic_x', '-')}x",
                ])
        out.append(_data_table(styles, ["Scenario", "IRR", "MOIC"], rows, [2.5 * inch, 2.0 * inch, 2.0 * inch]))

    out.append(Paragraph("3.2.6 Supporting commercial signals", styles["h3"]))
    out.extend(_bullets(styles, (_findings(sat, 4) + _findings(diff, 4))[:8] or ["No supporting commercial findings attached."]))

    out.extend(_section_close(styles, section_agents))
    return out


def _compose_appendices(styles: dict, ctx: BuildContext, section: StorylineSection) -> list:
    scope = _resolve(ctx, "scope_and_methodology")
    section_agents = _agents_for_section(ctx, section) or [scope]
    out: list = [
        Paragraph(section.title, styles["h2"]),
        Paragraph("Agent → primary source document map.", styles["muted"]),
        _snapshot_heading(styles),
        _insight(styles, "Appendix sourcing from this deal's workflow outputs."),
        Spacer(1, 6),
    ]
    rows: list[list[str]] = []
    for key, agent in sorted(ctx.agent_outputs.items()):
        if not isinstance(agent, dict):
            continue
        name = agent.get("agentName") or key.replace("_", " ").title()
        sources = agent.get("sources") or []
        src = ", ".join(sources[:3]) if sources else "-"
        code = _spec(agent).get("dd_code") or _spec(agent).get("fv_code") or _spec(agent).get("role_code") or "-"
        rows.append([str(name), str(code), key, src])
    if rows:
        out.append(Paragraph("3.3.1 Agent source index", styles["h3"]))
        out.append(_data_table(
            styles,
            ["Agent", "Code", "Slug", "Source document(s)"],
            rows[:50],
            [1.8 * inch, 0.9 * inch, 1.5 * inch, 2.3 * inch],
        ))
        if len(rows) > 50:
            out.append(Paragraph(f"…and {len(rows) - 50} additional agents omitted.", styles["muted"]))

    out.append(Paragraph("3.3.2 Scope & methodology notes", styles["h3"]))
    out.extend(_bullets(styles, _findings(scope, 8) or _as_list(_spec(scope).get("notes"), 6) or [
        "Memo synthesises Verdict Store + Deep Dive agents; no independent re-modelling.",
        "Web research not required for this build path.",
    ]))

    out.append(Paragraph("3.3.3 Storyline coverage", styles["h3"]))
    cov_rows = []
    for s in (ctx.storyline or []):
        if not s.included:
            continue
        cov_rows.append([s.title, ", ".join(s.agents[:4]) + ("…" if len(s.agents) > 4 else ""), str(len(s.agents))])
    if cov_rows:
        out.append(_data_table(
            styles,
            ["Section", "Primary agents", "#"],
            cov_rows,
            [2.4 * inch, 3.3 * inch, 0.8 * inch],
        ))

    out.append(Spacer(1, 10))
    out.append(Paragraph("3.3.4 Attribute legend", styles["h3"]))
    out.append(_data_table(
        styles,
        ["Attribute", "Meaning"],
        [
            ["CONFIRMED", "Backed by a structured Verdict / Deep Dive / Foundation field present in this deal's stores."],
            ["ASSUMED", "Interpolated, missing, or only weakly evidenced in agent output — treat as diligence gap."],
            ["Not re-derived", "Figures shown as published by upstream agents; the IC Memo builder does not re-model."],
        ],
        [1.5 * inch, 5.0 * inch],
    ))

    out.append(Spacer(1, 10))
    out.append(Paragraph("3.3.5 IC glossary (selected)", styles["h3"]))
    out.extend(_bullets(styles, [
        "TAM / SAM / SOM — total / serviceable / obtainable market framing from market_volume_and_growth.",
        "Football field — cross-method equity / EV band (DCF, trading comps, precedents).",
        "WACC — discount rate used in DCF scenarios from valuation_modeling.",
        "IRR / MOIC — returns under recommendation scenario set.",
        "CP / 100-day plan — conditions precedent and post-close value-creation cadence from recommendation.",
        f"Sector label — {_esc(_sector_display(ctx))} (resolved from deal metadata or market/foundation corpus).",
    ]))

    out.extend(_section_close(styles, section_agents))
    return out


def _closing_attestation(styles: dict, ctx: BuildContext) -> list:
    company = _company(ctx)
    sector = _sector_display(ctx)
    today_s = date.today().strftime("%d %B %Y")
    block = Table(
        [
            [Paragraph("IC attestation", styles["h1"])],
            [Paragraph(
                f"This memorandum for {_esc(company)} ({_esc(sector)}) is generated for Investment "
                "Committee voting members. It summarises Verdict Store and Deep Dive outputs available "
                f"as of {today_s}. Readers should cross-check material figures against source agent "
                "specs and the cited VDR documents before a final vote.",
                styles["body"],
            )],
            [Spacer(1, 12)],
            [Paragraph(
                "Distribution control: Strictly Private &amp; Confidential — Agentic CDD deal workspace.",
                styles["muted"],
            )],
        ],
        colWidths=[6.5 * inch],
    )
    block.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, _NAVY),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    return [block, PageBreak()]


_COMPOSERS = {
    "1.1": _compose_market_risk,
    "1.2": _compose_internal_risk,
    "1.3": _compose_growth,
    "1.4": _compose_synergies,
    "2.1": _compose_valuation_model,
    "2.2": _compose_sensitivity,
    "2.3": _compose_final_range,
    "3.1": _compose_exec_summary,
    "3.2": _compose_recommendation,
    "3.3": _compose_appendices,
}

_PART_DIVIDERS = [
    ("01", "Risk & Opportunity", "Aggregating market and internal risks, growth opportunities and synergies."),
    ("02", "Valuation", "DCF, comps, precedents, sensitivity and recommended valuation band."),
    ("03", "Executive Synthesis", "IC snapshot, final recommendation, 100-day plan and sourcing."),
]


def _section_key(section: StorylineSection) -> str:
    # "1.1 Market Risk" → "1.1"
    parts = (section.title or "").split()
    return parts[0] if parts else ""


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class ICMemoBuilder(ReportBuilder):
    report_type = "ic_memo"

    def build_sections(self, ctx: BuildContext) -> Iterator[dict[str, Any]]:
        enabled = [s for s in (ctx.storyline or []) if s.included]
        total = 3 + 3 + len(enabled)  # cover/basis/toc + 3 dividers + sections
        current = 0
        current += 1
        yield _evt("section", "Generating cover & basis of preparation", i=current, total=total)
        current += 1
        yield _evt("section", "Generating table of contents", i=current, total=total)
        for part_title in ("Risk & Opportunity", "Valuation", "Executive Synthesis"):
            current += 1
            yield _evt("section", f"Generating part divider: {part_title}", i=current, total=total)
        for section in enabled:
            current += 1
            yield _evt(
                "section",
                f"Generating section {current} of {total}: {section.title}",
                i=current,
                total=total,
            )

    def export_artifact(self, ctx: BuildContext) -> str:
        styles = _styles()
        company = _company(ctx)
        story: list = []
        story.extend(_cover(styles, ctx))
        story.extend(_basis(styles, ctx))
        story.extend(_toc(styles, ctx))

        enabled = [s for s in (ctx.storyline or []) if s.included]
        # Group by part prefix
        parts = [
            ("1.", _PART_DIVIDERS[0]),
            ("2.", _PART_DIVIDERS[1]),
            ("3.", _PART_DIVIDERS[2]),
        ]
        for prefix, div in parts:
            part_sections = [s for s in enabled if s.title.startswith(prefix)]
            if not part_sections:
                continue
            story.extend(_divider(styles, *div))
            for section in part_sections:
                key = _section_key(section)
                composer = _COMPOSERS.get(key)
                if composer:
                    story.extend(composer(styles, ctx, section))
                else:
                    story.append(Paragraph(_esc(section.title), styles["h2"]))
                    agents = [_resolve(ctx, ak) for ak in section.agents]
                    for ak, agent in zip(section.agents, agents):
                        findings = _findings(agent, 4)
                        if findings:
                            story.append(Paragraph(_esc(_agent_name(agent, ak)), styles["h3"]))
                            story.extend(_bullets(styles, findings))
                    story.extend(_section_close(styles, agents))

        story.extend(_closing_attestation(styles, ctx))

        out_dir = report_artifact_dir(ctx.deal_slug, "ic_memo")
        safe = re.sub(r"[^\w\s-]", "", company).strip().replace(" ", "_") or ctx.deal_slug
        filename = f"{safe}_IC_Memo.pdf"
        path = out_dir / filename

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.65 * inch,
            title=f"IC Memo — {company}",
            author="Agentic CDD",
        )
        doc.build(story, onFirstPage=_header_footer(company), onLaterPages=_header_footer(company))

        deal_root = deals_root() / ctx.deal_slug
        try:
            return str(path.relative_to(deal_root))
        except ValueError:
            return str(path)


register_builder("ic_memo", ICMemoBuilder)
