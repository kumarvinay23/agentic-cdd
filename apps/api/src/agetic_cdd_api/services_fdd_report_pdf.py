"""Landscape FDD findings-report PDF — visual parity with Compost Crew Latest.

Renders widescreen (10\" × 5.625\") pages via HTML + headless Chrome when
available, with a reportlab canvas fallback that keeps the same page size,
palette, and finding-card chrome.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdf_canvas

from agetic_cdd_api.fdd_schemas import StubRenderPage

# Widescreen slide-like page (matches Compost_Crew_Latest - FDD Report.pdf).
PAGE_W = 10.0 * inch  # 720 pt
PAGE_H = 5.625 * inch  # 405 pt

# Palette sampled from the reference Chromium print.
C_TITLE = HexColor("#9A7B4F")
C_TITLE_DARK = HexColor("#6B4F27")
C_MUTED = HexColor("#8A8070")
C_BODY = HexColor("#3A3A3A")
C_RULE = HexColor("#D8CBB2")
C_RULE_SOFT = HexColor("#EAE3D5")
C_CHIP_BG = HexColor("#F4EFE4")
C_HIGH = HexColor("#CE3B2E")
C_MOD = HexColor("#D4A017")
C_LOW = HexColor("#2E9B57")
C_INFO = HexColor("#6B7280")
C_EVIDENCE_BAR = HexColor("#C4B08A")

_SEVERITY_LETTER = {
    "high": ("H", C_HIGH),
    "moderate": ("M", C_MOD),
    "low": ("L", C_LOW),
    "info": ("I", C_INFO),
}

_FINDING_TITLE_RE = re.compile(r"^Finding\s*[—\-–]\s*(.+)$", re.I)
_SEVERITY_LINE_RE = re.compile(
    r"^\[(HIGH|MODERATE|LOW|INFO)\]\s*(.*)$", re.I
)


def _escape(text: str) -> str:
    return html.escape(text or "", quote=True).replace("\n", "<br/>")


def _plain_lines(body: str) -> list[str]:
    return [ln.strip() for ln in (body or "").split("\n") if ln.strip()]


def _parse_finding(page: StubRenderPage) -> dict[str, Any] | None:
    """Detect finding-card pages from title/body shape."""
    title = page.title or ""
    body = page.body or ""
    m = _FINDING_TITLE_RE.match(title.strip())
    finding_title = m.group(1).strip() if m else None
    severity = None
    observation = ""
    implication = ""
    ask = ""
    evidence: list[str] = []
    lines = _plain_lines(body)
    if not lines:
        return None
    first = _SEVERITY_LINE_RE.match(lines[0])
    if first:
        severity = first.group(1).lower()
        if not finding_title:
            finding_title = (first.group(2) or "").strip() or title
        rest = lines[1:]
    elif finding_title or title.lower().startswith("finding"):
        rest = lines
        severity = "info"
        finding_title = finding_title or title
    else:
        return None
    for ln in rest:
        low = ln.lower()
        if low.startswith("observation:"):
            observation = ln.split(":", 1)[1].strip()
        elif low.startswith("implication:"):
            implication = ln.split(":", 1)[1].strip()
        elif low.startswith("ask management:"):
            ask = ln.split(":", 1)[1].strip()
        elif low.startswith("evidence:"):
            evidence = [p.strip() for p in ln.split(":", 1)[1].split(";") if p.strip()]
        elif not observation:
            observation = ln
        elif not implication:
            implication = ln
    return {
        "severity": severity or "info",
        "title": finding_title or title,
        "observation": observation,
        "implication": implication,
        "ask": ask,
        "evidence": evidence,
    }


def _page_role(page: StubRenderPage) -> str:
    if page.kind == "cover":
        return "cover"
    title = (page.title or "").strip().lower()
    if _parse_finding(page):
        return "finding"
    if title in {"contents", "table of contents"}:
        return "toc"
    if title.startswith("abbreviations"):
        return "abbreviations"
    if title.startswith("data integrity"):
        return "caveats"
    if title.startswith("basis of preparation"):
        return "basis"
    if "executive summary" in title:
        return "executive"
    if title.startswith("not evidenced"):
        return "gaps"
    return "section"


def _chrome_bin() -> str | None:
    env = os.environ.get("CHROME_BIN") or os.environ.get("GOOGLE_CHROME_BIN")
    if env and Path(env).exists():
        return env
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _css() -> str:
    return f"""
@page {{
  size: {PAGE_W:.2f}pt {PAGE_H:.2f}pt;
  margin: 0;
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0;
  font-family: "Liberation Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #3A3A3A;
  background: #fff;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}
.page {{
  width: {PAGE_W:.2f}pt;
  height: {PAGE_H:.2f}pt;
  padding: 28pt 32pt 36pt 32pt;
  position: relative;
  page-break-after: always;
  overflow: hidden;
  background: #fff;
}}
.page.executive {{
  /* Prefer PTI list over a long KEY POINTS dump when space is tight. */
  padding-top: 22pt;
}}
.page.executive .findings-list {{
  max-height: 95pt;
  overflow: hidden;
}}
.page.executive .body-lines,
.page.executive .bullet {{
  font-size: 8.5pt;
}}
.page:last-child {{ page-break-after: auto; }}
.footer {{
  position: absolute; left: 32pt; right: 32pt; bottom: 14pt;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 8pt; color: #A39886;
}}
.footer .num {{ position: absolute; left: 50%; transform: translateX(-50%); }}
h1.page-title {{
  margin: 0 0 6pt 0;
  font-size: 18pt; font-weight: 600;
  color: #9A7B4F;
  font-family: Georgia, "Times New Roman", serif;
}}
.subhead {{
  margin: 0 0 14pt 0;
  font-size: 9.5pt; color: #8A8070;
}}
.cover {{
  display: flex; flex-direction: column; justify-content: center;
  height: 100%; padding-left: 8pt;
}}
.cover-brand {{
  display: flex; align-items: center; gap: 8pt;
  margin-bottom: 48pt;
}}
.cover-mark {{
  width: 18pt; height: 18pt; background: #6B4F27; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 10pt; font-weight: 700;
}}
.cover-brand-name {{ font-size: 11pt; color: #3A3A3A; }}
.cover-title {{
  font-size: 28pt; font-weight: 600; color: #6B4F27;
  margin: 0 0 10pt 0; line-height: 1.15;
}}
.cover-sub {{
  font-size: 13pt; color: #B38B5D; margin: 0 0 8pt 0;
}}
.cover-conf {{
  font-size: 10pt; color: #B38B5D; margin: 0;
}}
.kv-table, .abbr-table, .toc-table, .caveat-table {{
  width: 100%; border-collapse: collapse; font-size: 9.5pt;
}}
.kv-table td, .abbr-table td, .toc-table td, .caveat-table td,
.caveat-table th {{
  padding: 7pt 6pt; vertical-align: top;
  border-bottom: 0.6pt solid #EAE3D5;
}}
.caveat-table th {{
  text-align: left; color: #8A8070; font-weight: 600;
  border-bottom: 0.8pt solid #D8CBB2;
}}
.abbr-table td:first-child, .toc-table td:first-child {{
  width: 22%; color: #9A7B4F; font-weight: 600; white-space: nowrap;
}}
.toc-table td:first-child {{ width: 36pt; }}
.body-lines p {{
  margin: 0 0 6pt 0; font-size: 10pt; line-height: 1.35;
}}
.bullet {{
  margin: 0 0 4pt 0; padding-left: 10pt; position: relative;
  font-size: 10pt; line-height: 1.35;
}}
.bullet::before {{
  content: "▸"; position: absolute; left: 0; color: #9A7B4F; font-size: 8pt;
  top: 1pt;
}}
.finding-head {{
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 10pt; gap: 12pt;
}}
.finding-head .meta {{ font-size: 9pt; color: #8A8070; text-align: right; }}
.finding-grid {{
  display: grid;
  grid-template-columns: 1.1fr 1.6fr 1.4fr;
  gap: 0;
  min-height: 210pt;
}}
.finding-col {{
  padding: 0 12pt;
  border-right: 0.75pt solid #EAE3D5;
}}
.finding-col:first-child {{ padding-left: 0; }}
.finding-col:last-child {{ border-right: none; padding-right: 0; }}
.sev-row {{ display: flex; align-items: center; gap: 8pt; margin-bottom: 8pt; }}
.sev-badge {{
  width: 18pt; height: 18pt; border-radius: 50%;
  color: #fff; font-size: 9pt; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}}
.sev-high {{ background: #CE3B2E; }}
.sev-moderate {{ background: #D4A017; }}
.sev-low {{ background: #2E9B57; }}
.sev-info {{ background: #6B7280; }}
.col-label {{
  font-size: 8.5pt; letter-spacing: 0.06em; color: #9A7B4F;
  font-weight: 700; margin: 0 0 6pt 0;
}}
.key-finding {{
  font-size: 12pt; font-weight: 700; color: #2F2F2F; line-height: 1.3;
  margin: 0;
}}
.obs, .impl {{
  font-size: 9pt; line-height: 1.4; color: #4A4A4A; margin: 0 0 6pt 0;
}}
.evidence {{
  margin-top: 12pt;
  border: 0.75pt solid #D8CBB2;
}}
.evidence-bar {{
  background: #C4B08A; color: #fff;
  font-size: 8.5pt; font-weight: 600;
  padding: 4pt 8pt;
}}
.evidence table {{
  width: 100%; border-collapse: collapse; font-size: 8.5pt;
}}
.evidence td {{
  padding: 5pt 8pt; border-bottom: 0.5pt solid #EAE3D5; vertical-align: top;
}}
.evidence tr:last-child td {{ border-bottom: none; }}
.kpi-row {{
  display: flex; gap: 0; margin: 8pt 0 14pt 0;
  border-top: 0.6pt solid #EAE3D5; border-bottom: 0.6pt solid #EAE3D5;
}}
.kpi {{
  flex: 1; padding: 10pt 12pt; display: flex; align-items: center; gap: 8pt;
  border-right: 0.6pt solid #EAE3D5;
}}
.kpi:last-child {{ border-right: none; }}
.kpi-label {{ font-size: 9pt; font-weight: 700; letter-spacing: 0.04em; }}
.chip-grid {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 10pt; margin-bottom: 12pt;
}}
.chip {{
  background: #F4EFE4; padding: 10pt 12pt; border-radius: 2pt;
}}
.chip .label {{ font-size: 8.5pt; color: #9A7B4F; font-weight: 600; margin: 0 0 4pt 0; }}
.chip .value {{ font-size: 16pt; font-weight: 700; color: #2F2F2F; margin: 0; }}
.chip .hint {{ font-size: 8pt; color: #8A8070; margin: 4pt 0 0 0; }}
.findings-list {{ margin-top: 6pt; }}
.findings-list .row {{
  display: flex; gap: 10pt; align-items: flex-start;
  padding: 6pt 0; border-bottom: 0.5pt solid #EAE3D5;
  font-size: 9pt;
}}
.findings-list .row:last-child {{ border-bottom: none; }}
.note {{
  margin-top: 10pt; font-size: 8.5pt; font-style: italic; color: #8A8070;
}}
.source {{
  margin-top: 6pt; font-size: 8pt; color: #A39886;
}}
"""


def _footer_html(company: str, page_num: int, total: int) -> str:
    label = f"{company} - Financial &amp; Tax Due Diligence"
    return (
        f'<div class="footer"><span></span>'
        f'<span class="num">{page_num}</span>'
        f'<span>{label}</span></div>'
    )


def _render_cover(company: str, page: StubRenderPage) -> str:
    initial = (company.strip()[:1] or "F").upper()
    return f"""
    <div class="cover">
      <div class="cover-brand">
        <div class="cover-mark">{_escape(initial)}</div>
        <div class="cover-brand-name">{_escape(company)}</div>
      </div>
      <h1 class="cover-title">{_escape(company)}</h1>
      <p class="cover-sub">Financial &amp; tax due diligence — findings report</p>
      <p class="cover-conf">Strictly Private and Confidential</p>
    </div>
    """


def _render_basis(page: StubRenderPage) -> str:
    rows = ""
    for ln in _plain_lines(page.body):
        if ":" in ln:
            k, v = ln.split(":", 1)
            rows += (
                f"<tr><td style='width:28%;color:#9A7B4F;font-weight:600'>"
                f"{_escape(k.strip())}</td><td>{_escape(v.strip())}</td></tr>"
            )
        else:
            rows += f"<tr><td colspan='2'>{_escape(ln)}</td></tr>"
    return f"""
    <h1 class="page-title">Basis of preparation</h1>
    <p class="subhead">Scope, perimeter and information basis for this engagement</p>
    <table class="kv-table">{rows}</table>
    <p class="note">Figures are taken from the approved databook exhibits for this run.</p>
    """


def _render_caveats(page: StubRenderPage) -> str:
    rows = ""
    for ln in _plain_lines(page.body):
        text = ln.lstrip("•-* ").strip()
        # Split "Area — detail" or keep whole as Position.
        if "—" in text:
            area, rest = text.split("—", 1)
        elif ":" in text:
            area, rest = text.split(":", 1)
        else:
            area, rest = "Caveat", text
        rows += (
            f"<tr><td>{_escape(area.strip())}</td>"
            f"<td>{_escape(rest.strip())}</td>"
            f"<td>Review before relying on related analyses.</td></tr>"
        )
    return f"""
    <h1 class="page-title">Data integrity and caveats</h1>
    <p class="subhead">What the engine could and could not establish from the supplied inputs</p>
    <table class="caveat-table">
      <tr><th>Area</th><th>Position</th><th>What this means for the reader</th></tr>
      {rows}
    </table>
    <p class="note">Every figure in this report is computed from the supplied databook and is unvouched. Where an input could not be resolved, no finding was produced rather than an estimated one.</p>
    <p class="source">Source: FDD analytical engine — input diagnostics</p>
    """


def _render_toc(page: StubRenderPage) -> str:
    rows = ""
    for i, ln in enumerate(_plain_lines(page.body), start=1):
        text = ln.lstrip("•-* ").strip()
        rows += (
            f"<tr><td>{i:02d}</td><td>{_escape(text)}</td></tr>"
        )
    return f"""
    <h1 class="page-title">Contents</h1>
    <table class="toc-table">{rows}</table>
    """


def _render_abbreviations(page: StubRenderPage) -> str:
    rows = ""
    for ln in _plain_lines(page.body):
        text = ln.lstrip("•-* ").strip()
        if "—" in text:
            term, defn = text.split("—", 1)
        elif " - " in text:
            term, defn = text.split(" - ", 1)
        else:
            term, defn = text, ""
        rows += (
            f"<tr><td>{_escape(term.strip())}</td>"
            f"<td>{_escape(defn.strip())}</td></tr>"
        )
    return f"""
    <h1 class="page-title">Abbreviations &amp; key terms</h1>
    <table class="abbr-table">{rows}</table>
    """


def _severity_counts_from_pages(pages: list[StubRenderPage]) -> dict[str, int]:
    counts = {"high": 0, "moderate": 0, "low": 0, "info": 0}
    for page in pages:
        parsed = _parse_finding(page)
        if parsed:
            sev = parsed["severity"]
            counts[sev] = counts.get(sev, 0) + 1
    return counts


def _render_executive(
    page: StubRenderPage,
    all_pages: list[StubRenderPage],
    *,
    findings_counts: dict[str, int] | None = None,
    top_findings: list[dict[str, Any]] | None = None,
) -> str:
    counts = {
        "high": 0,
        "moderate": 0,
        "low": 0,
        "info": 0,
        **(findings_counts or {}),
    }
    if not findings_counts:
        counts = _severity_counts_from_pages(all_pages)
        for ln in _plain_lines(page.body):
            low = ln.lower()
            if "high" in low and "moderate" in low:
                m = re.search(
                    r"(\d+)\s*high.*?(\d+)\s*moderate.*?(\d+)\s*low"
                    r"(?:.*?(\d+)\s*info)?.*?total\s*(\d+)",
                    low,
                )
                if m:
                    counts["high"] = int(m.group(1))
                    counts["moderate"] = int(m.group(2))
                    counts["low"] = int(m.group(3))
                    if m.group(4) is not None:
                        counts["info"] = int(m.group(4))
                    if m.group(5) is not None:
                        counts["total"] = int(m.group(5))
                break

    total = int(counts.get("total") or sum(
        int(counts.get(k, 0) or 0) for k in ("high", "moderate", "low", "info")
    ))

    kpi = f"""
    <div class="kpi-row">
      <div class="kpi"><div class="sev-badge sev-high">H</div>
        <div class="kpi-label">{counts.get('high', 0)} HIGH PTI</div></div>
      <div class="kpi"><div class="sev-badge sev-moderate">M</div>
        <div class="kpi-label">{counts.get('moderate', 0)} MODERATE PTI</div></div>
      <div class="kpi"><div class="sev-badge sev-low">L</div>
        <div class="kpi-label">{counts.get('low', 0)} LOW PTI</div></div>
    </div>
    """
    # Keep KEY POINTS short so KEY POTENTIAL fits on the landscape page.
    skip_prefixes = (
        "findings:",
        "resolve claim",
        "ebitda basis is the",
        "open diligence findings",
        "material open diligence",
        "no new facts",
    )
    key_points: list[str] = []
    for ln in _plain_lines(page.body):
        low = ln.lstrip("•-* ").strip().lower()
        if not low or any(low.startswith(p) for p in skip_prefixes):
            continue
        if "fy20" in low and ("unverifiable" in low or "contradicted" in low):
            continue
        key_points.append(ln.lstrip("•-* ").strip())
        if len(key_points) >= 5:
            break
    bullets = "".join(
        f'<div class="bullet">{_escape(ln)}</div>' for ln in key_points
    )
    findings_rows = ""
    structured = list(top_findings or [])
    if structured:
        for item in structured[:6]:
            sev = str(item.get("severity") or "info").lower()
            letter, _ = _SEVERITY_LETTER.get(sev, ("I", C_INFO))
            cls = f"sev-{sev}"
            findings_rows += (
                f'<div class="row"><div class="sev-badge {cls}">{letter}</div>'
                f'<div><strong>{_escape(str(item.get("title") or ""))}</strong>'
                f' — {_escape(str(item.get("observation") or "")[:180])}</div></div>'
            )
    else:
        for p in all_pages:
            parsed = _parse_finding(p)
            if not parsed or parsed["severity"] == "info":
                continue
            letter, _ = _SEVERITY_LETTER.get(parsed["severity"], ("I", C_INFO))
            cls = f"sev-{parsed['severity']}"
            findings_rows += (
                f'<div class="row"><div class="sev-badge {cls}">{letter}</div>'
                f'<div><strong>{_escape(parsed["title"])}</strong>'
                f' — {_escape((parsed["observation"] or "")[:180])}</div></div>'
            )
            if findings_rows.count('class="row"') >= 6:
                break
    return f"""
    <h1 class="page-title">Executive summary</h1>
    {kpi}
    <div class="chip-grid">
      <div class="chip">
        <p class="label">Findings ledger</p>
        <p class="value">{total}</p>
        <p class="hint">Structured PTI items from claims, model checks and QoE</p>
      </div>
      <div class="chip">
        <p class="label">Open / not evidenced</p>
        <p class="value">see appendix</p>
        <p class="hint">Items without sufficient databook support</p>
      </div>
    </div>
    <p class="col-label">KEY POTENTIAL TRANSACTION IMPACTS</p>
    <div class="findings-list">{findings_rows or '<div class="row">No structured findings yet.</div>'}</div>
    <p class="col-label" style="margin-top:8pt">KEY POINTS</p>
    {bullets or '<div class="bullet">See section commentary for supporting detail.</div>'}
    """


def _short_title(text: str, *, limit: int = 72) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" —,;:") + "…"


def _render_finding(page: StubRenderPage, parsed: dict[str, Any]) -> str:
    sev = parsed["severity"]
    letter, _ = _SEVERITY_LETTER.get(sev, ("I", C_INFO))
    evidence_rows = ""
    refs = parsed.get("evidence") or []
    if not refs:
        refs = ["—"]
    for ref in refs[:6]:
        evidence_rows += (
            f"<tr><td>{_escape(ref)}</td>"
            f"<td>{_escape(_short_title(parsed['title'], limit=48))}</td>"
            f"<td></td><td>Databook / exhibit store</td></tr>"
        )
    ask = parsed.get("ask") or ""
    impl = parsed.get("implication") or ""
    if ask:
        impl = (impl + " " if impl else "") + f"Ask management: {ask}"
    head = _short_title(page.title or parsed["title"], limit=78)
    return f"""
    <div class="finding-head">
      <h1 class="page-title" style="margin:0">{_escape(head)}</h1>
      <div class="meta">{_escape(sev.upper())}</div>
    </div>
    <div class="finding-grid">
      <div class="finding-col">
        <div class="sev-row">
          <div class="sev-badge sev-{sev}">{letter}</div>
          <p class="col-label" style="margin:0">KEY FINDING</p>
        </div>
        <p class="key-finding">{_escape(parsed['title'])}</p>
      </div>
      <div class="finding-col">
        <p class="col-label">OBSERVATIONS</p>
        <p class="obs">{_escape(parsed.get('observation') or '—')}</p>
      </div>
      <div class="finding-col">
        <p class="col-label">IMPLICATIONS</p>
        <p class="impl">{_escape(impl or '—')}</p>
      </div>
    </div>
    <div class="evidence">
      <div class="evidence-bar">Evidence and provenance</div>
      <table>
        <tr><td style="width:22%">Subpoint</td><td>Detail</td><td>Evidence</td><td>Source</td></tr>
        {evidence_rows}
      </table>
    </div>
    """


def _render_section(page: StubRenderPage) -> str:
    blocks = []
    for ln in _plain_lines(page.body):
        if ln.startswith(("•", "-", "*")):
            blocks.append(f'<div class="bullet">{_escape(ln.lstrip("•-* ").strip())}</div>')
        else:
            blocks.append(f'<p>{_escape(ln)}</p>')
    body = "".join(blocks) or "<p>—</p>"
    return f"""
    <h1 class="page-title">{_escape(page.title)}</h1>
    <div class="body-lines">{body}</div>
    """


def build_fdd_report_html(
    *,
    title: str,
    company: str,
    pages: list[StubRenderPage],
    findings_counts: dict[str, int] | None = None,
    top_findings: list[dict[str, Any]] | None = None,
) -> str:
    parts: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>",
        f"<title>{_escape(title)}</title>",
        f"<style>{_css()}</style></head><body>",
    ]
    total = max(len(pages), 1)
    for i, page in enumerate(pages):
        role = _page_role(page)
        if role == "cover":
            inner = _render_cover(company, page)
        elif role == "basis":
            inner = _render_basis(page)
        elif role == "caveats":
            inner = _render_caveats(page)
        elif role == "toc":
            inner = _render_toc(page)
        elif role == "abbreviations":
            inner = _render_abbreviations(page)
        elif role == "executive":
            inner = _render_executive(
                page,
                pages,
                findings_counts=findings_counts,
                top_findings=top_findings,
            )
            # Mark page for tighter ES layout CSS.
            parts.append(
                f'<section class="page executive">{inner}'
                f'{"" if role == "cover" else _footer_html(company, i + 1, total)}'
                f"</section>"
            )
            continue
        elif role == "finding":
            parsed = _parse_finding(page)
            assert parsed is not None
            inner = _render_finding(page, parsed)
        else:
            inner = _render_section(page)
        # Cover has no page number in the reference.
        footer = "" if role == "cover" else _footer_html(company, i + 1, total)
        parts.append(f'<section class="page">{inner}{footer}</section>')
    parts.append("</body></html>")
    return "\n".join(parts)


def _print_html_chrome(html_text: str, path: Path, chrome: str) -> None:
    with tempfile.TemporaryDirectory(prefix="fdd_pdf_") as tmp:
        tmp_path = Path(tmp)
        html_path = tmp_path / "report.html"
        html_path.write_text(html_text, encoding="utf-8")
        out_pdf = tmp_path / "out.pdf"
        profile = tmp_path / "chrome-profile"
        profile.mkdir()
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--no-first-run",
            "--disable-extensions",
            "--disable-dev-shm-usage",
            f"--user-data-dir={profile}",
            f"--crash-dumps-dir={tmp_path / 'crashes'}",
            f"--print-to-pdf={out_pdf}",
            html_path.resolve().as_uri(),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0 or not out_pdf.exists() or out_pdf.stat().st_size < 100:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
            raise RuntimeError(
                f"Chrome print failed (code={proc.returncode}): {err or 'empty PDF'}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(out_pdf.read_bytes())


def _draw_wrapped(
    c: pdf_canvas.Canvas,
    text: str,
    x: float,
    y: float,
    *,
    width: float,
    font: str = "Helvetica",
    size: float = 9,
    leading: float = 11,
    color: Color = C_BODY,
    max_lines: int = 12,
) -> float:
    c.setFillColor(color)
    c.setFont(font, size)
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if c.stringWidth(trial, font, size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    for i, ln in enumerate(lines):
        c.drawString(x, y - i * leading, ln)
    return y - max(len(lines), 1) * leading


def _write_fdd_pdf_reportlab(
    *,
    path: Path,
    title: str,
    company: str,
    pages: list[StubRenderPage],
) -> None:
    """Canvas fallback — same page size/palette when Chrome is unavailable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = pdf_canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    total = max(len(pages), 1)

    def footer(n: int) -> None:
        c.setStrokeColor(C_RULE_SOFT)
        c.setLineWidth(0.5)
        c.line(32, 22, PAGE_W - 32, 22)
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(PAGE_W / 2, 12, str(n))
        c.drawRightString(
            PAGE_W - 32, 12, f"{company} - Financial & Tax Due Diligence"
        )

    if not pages:
        c.setFillColor(C_TITLE_DARK)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(40, PAGE_H / 2, title)
        c.showPage()
        c.save()
        return

    for i, page in enumerate(pages):
        role = _page_role(page)
        if role == "cover":
            initial = (company[:1] or "F").upper()
            c.setFillColor(C_TITLE_DARK)
            c.rect(40, PAGE_H - 70, 16, 16, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(48, PAGE_H - 66, initial)
            c.setFillColor(C_BODY)
            c.setFont("Helvetica", 10)
            c.drawString(62, PAGE_H - 66, company)
            c.setFillColor(C_TITLE_DARK)
            c.setFont("Helvetica-Bold", 26)
            c.drawString(40, PAGE_H / 2 + 10, company)
            c.setFillColor(HexColor("#B38B5D"))
            c.setFont("Helvetica", 12)
            c.drawString(
                40,
                PAGE_H / 2 - 12,
                "Financial & tax due diligence — findings report",
            )
            c.setFont("Helvetica", 9)
            c.drawString(40, PAGE_H / 2 - 30, "Strictly Private and Confidential")
        else:
            c.setFillColor(C_TITLE)
            c.setFont("Times-Bold", 16)
            c.drawString(32, PAGE_H - 40, (page.title or "")[:90])
            y = PAGE_H - 62
            parsed = _parse_finding(page) if role == "finding" else None
            if parsed:
                letter, color = _SEVERITY_LETTER.get(
                    parsed["severity"], ("I", C_INFO)
                )
                c.setFillColor(color)
                c.circle(42, y - 4, 8, fill=1, stroke=0)
                c.setFillColor(white)
                c.setFont("Helvetica-Bold", 8)
                c.drawCentredString(42, y - 7, letter)
                c.setFillColor(C_TITLE)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(56, y - 7, "KEY FINDING")
                y = _draw_wrapped(
                    c,
                    parsed["title"],
                    32,
                    y - 24,
                    width=200,
                    font="Helvetica-Bold",
                    size=11,
                    leading=13,
                    max_lines=5,
                )
                c.setStrokeColor(C_RULE_SOFT)
                c.setLineWidth(0.7)
                c.line(250, PAGE_H - 55, 250, 70)
                c.line(470, PAGE_H - 55, 470, 70)
                c.setFillColor(C_TITLE)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(262, PAGE_H - 58, "OBSERVATIONS")
                _draw_wrapped(
                    c,
                    parsed.get("observation") or "—",
                    262,
                    PAGE_H - 74,
                    width=195,
                    size=8.5,
                    leading=11,
                    max_lines=12,
                )
                c.drawString(482, PAGE_H - 58, "IMPLICATIONS")
                impl = parsed.get("implication") or ""
                if parsed.get("ask"):
                    impl = (impl + " " if impl else "") + f"Ask: {parsed['ask']}"
                _draw_wrapped(
                    c,
                    impl or "—",
                    482,
                    PAGE_H - 74,
                    width=200,
                    size=8.5,
                    leading=11,
                    max_lines=12,
                )
                c.setFillColor(C_EVIDENCE_BAR)
                c.rect(32, 52, PAGE_W - 64, 14, fill=1, stroke=0)
                c.setFillColor(white)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(40, 56, "Evidence and provenance")
                c.setStrokeColor(C_RULE)
                c.setLineWidth(0.6)
                c.rect(32, 28, PAGE_W - 64, 38, fill=0, stroke=1)
                c.setFillColor(C_MUTED)
                c.setFont("Helvetica", 7)
                c.drawString(40, 44, "Subpoint")
                c.drawString(160, 44, "Detail")
                c.drawString(400, 44, "Evidence")
                c.drawString(520, 44, "Source")
                c.setStrokeColor(C_RULE_SOFT)
                c.line(40, 40, PAGE_W - 40, 40)
                refs = parsed.get("evidence") or ["—"]
                c.setFillColor(C_BODY)
                c.setFont("Helvetica", 7.5)
                c.drawString(40, 32, str(refs[0])[:28])
                c.drawString(160, 32, parsed["title"][:40])
                c.drawString(520, 32, "Databook / exhibit store")
            elif role == "executive":
                counts = _severity_counts_from_pages(pages)
                x = 40
                for key, label in (
                    ("high", "HIGH PTI"),
                    ("moderate", "MODERATE PTI"),
                    ("low", "LOW PTI"),
                ):
                    letter, color = _SEVERITY_LETTER[key]
                    c.setFillColor(color)
                    c.circle(x, y - 2, 7, fill=1, stroke=0)
                    c.setFillColor(white)
                    c.setFont("Helvetica-Bold", 7)
                    c.drawCentredString(x, y - 5, letter)
                    c.setFillColor(C_BODY)
                    c.setFont("Helvetica-Bold", 9)
                    c.drawString(x + 12, y - 5, f"{counts.get(key, 0)} {label}")
                    x += 140
                y -= 24
                for ln in _plain_lines(page.body)[:12]:
                    y = _draw_wrapped(
                        c,
                        "▸ " + ln.lstrip("•-* "),
                        32,
                        y,
                        width=PAGE_W - 64,
                        size=9,
                        leading=11,
                        max_lines=2,
                    )
                    y -= 2
                    if y < 40:
                        break
            else:
                for ln in _plain_lines(page.body):
                    prefix = "▸ " if ln.startswith(("•", "-", "*")) else ""
                    text = prefix + ln.lstrip("•-* ")
                    y = _draw_wrapped(
                        c,
                        text,
                        32,
                        y,
                        width=PAGE_W - 64,
                        size=9.5,
                        leading=12,
                        color=C_BODY if not prefix else C_BODY,
                        max_lines=3,
                    )
                    y -= 2
                    if y < 40:
                        break
            footer(i + 1)
        c.showPage()
    c.save()


def write_fdd_findings_pdf(
    *,
    path: Path | str,
    title: str,
    company: str,
    pages: list[StubRenderPage],
    figures: dict[str, Any] | None = None,
    findings_counts: dict[str, int] | None = None,
    top_findings: list[dict[str, Any]] | None = None,
) -> None:
    """Write the landscape findings-report PDF (Chrome preferred)."""
    del figures  # reserved for future chart embeds
    out = Path(path)
    html_text = build_fdd_report_html(
        title=title,
        company=company,
        pages=pages,
        findings_counts=findings_counts,
        top_findings=top_findings,
    )
    chrome = _chrome_bin()
    if chrome:
        try:
            _print_html_chrome(html_text, out, chrome)
            return
        except (OSError, subprocess.SubprocessError, RuntimeError):
            pass
    _write_fdd_pdf_reportlab(
        path=out, title=title, company=company, pages=pages
    )
