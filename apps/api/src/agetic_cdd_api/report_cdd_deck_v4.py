"""CDD deck in the DiligenceIQ v4 shape.

Page order follows the published standard (engagement, five chapters, sizing
method, evidence appendix, glossary, close). A content page is withheld when
the agent specs do not contain the exhibit it needs. Figures are taken from
those specs; nothing is filled from a reference deal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from agetic_cdd_api.report_builder_base import BuildContext, sanitize_report_prose
from agetic_cdd_api.report_storyline import StorylineSection

_SLIDE_W = Inches(13.333)
_SLIDE_H = Inches(7.5)

_NAVY = RGBColor(0x1F, 0x38, 0x64)
_SLATE = RGBColor(0x37, 0x41, 0x51)
_MUTED = RGBColor(0x6B, 0x72, 0x80)
_ORANGE = RGBColor(0xE8, 0x7A, 0x2E)
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_LIGHT = RGBColor(0xF4, 0xF7, 0xFB)
_RED = RGBColor(0xB9, 0x1C, 0x1C)
_TEAL = RGBColor(0x0F, 0x76, 0x6E)

_CHAPTERS: tuple[tuple[str, str, str], ...] = (
    ("01", "Business Introduction & Market Primer", "Who the target is, how the industry works and where the target sits in it"),
    ("02", "Investment Highlights", "The main findings, each stated at the strength of its evidence"),
    ("03", "Market Dynamics & Opportunity", "How large, how fast-growing and how resilient the addressable market is"),
    ("04", "Competitive Landscape", "Who the target actually competes with, and what the data room shows"),
    ("05", "Growth Opportunities", "The levers in the plan, each tied to a figure or marked as untested"),
    ("A", "Appendix A - Market Sizing Methodology", "How every number in the sizing was built"),
    ("B", "Appendix B - Evidence & Audit Trail", "Module verdicts, source register and exceptions"),
)

_NEW_TITLES = {title for _n, title, _s in _CHAPTERS} | {"Engagement Overview"}


@dataclass
class ChartSpec:
    kind: str  # column | line
    categories: list[str]
    series: list[tuple[str, list[float]]]


@dataclass
class Page:
    kind: str  # cover | disclaimer | content | divider | close
    section: str = ""
    title: str = ""
    subtitle: str = ""
    source: str = ""
    bullets: list[str] = field(default_factory=list)
    kpis: list[tuple[str, str]] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    chart: ChartSpec | None = None
    note: str = ""
    chapter: str = ""


@dataclass
class DeckPlan:
    pages: list[Page]
    withheld: list[tuple[str, str]]  # page, why


def _resolve(ctx: BuildContext, key: str) -> dict[str, Any]:
    data = ctx.agent_outputs.get(key)
    return data if isinstance(data, dict) else {}


def _spec(agent: dict[str, Any]) -> dict[str, Any]:
    raw = agent.get("spec")
    if isinstance(raw, dict) and raw:
        return raw
    return agent if isinstance(agent, dict) else {}


def _company(ctx: BuildContext) -> str:
    if ctx.profile and ctx.profile.company:
        return str(ctx.profile.company)
    return ctx.deal_slug or "the target"


def _clean(text: Any, limit: int = 220) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = re.sub(r"\(\s*\.?\s*\)\.?", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;")
    t = sanitize_report_prose(t)
    if len(t) <= limit:
        return t
    cut = t[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def _filled(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    return not re.match(r"(?i)^(n/?a|none|not available|information request|—|-)$", text)


def _chapter_enabled(ctx: BuildContext, title: str) -> bool:
    sections = [s for s in (ctx.storyline or []) if isinstance(s, StorylineSection)]
    if not sections:
        return True
    titles = {s.title for s in sections}
    if not (titles & _NEW_TITLES):
        return True
    for section in sections:
        if section.title == title:
            return bool(section.included)
    return True


def _fmt_money(metric: Any) -> str | None:
    if isinstance(metric, (int, float)) and not isinstance(metric, bool):
        return _fmt_number(float(metric), scale="million")
    if not isinstance(metric, dict):
        return None
    raw = metric.get("value")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    scale = str(metric.get("scale") or metric.get("unit") or "").lower()
    return _fmt_number(float(raw), scale=scale)


def _revenue_millions(value: float) -> float:
    """Account extracts may be stored in dollars or already in millions."""
    if abs(value) >= 100_000:
        return value / 1_000_000
    return value


def _fmt_number(value: float, *, scale: str = "") -> str:
    scale = scale.lower()
    if "billion" in scale or scale in {"b", "bn"}:
        return f"${value:,.1f}B"
    if "crore" in scale or scale in {"cr", "inr cr"}:
        return f"INR {value:,.1f} Cr"
    if "million" in scale or scale in {"m", "usd m", "$m", "usdm"}:
        return f"${value:,.1f}M"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"${value:,.0f}"
    return f"${value:,.1f}"


def _pct_from(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if 0 < number <= 1.5:
            return round(number * 100, 2)
        if 1.5 < number <= 400:
            return round(number, 2)
        return None
    match = re.search(r"(-?\d{1,3}(?:\.\d+)?)\s*%", str(value or ""))
    if not match:
        return None
    return float(match.group(1))


_PLAN_TYPES = {"plan", "forecast", "budget", "projection", "projected"}
_PARTIAL_TYPES = {"ytd", "ttm", "year to date", "last twelve months"}

# A bare calendar year from 2026 onward is a plan year in this product's accounts
# convention, including when an extract stored it as "actual". A partial period
# (YTD, TTM, a named month) stays a result.
_OPEN_YEAR = 2026

_CAP_TABLE_RE = re.compile(
    r"(?i)(?:"
    r"\bCS-\d+\b|"
    r"\bGR-\d{4}\b|"
    r"securities[\s-]*ledger|"
    r"stock\s+option|"
    r"option\s+plan|"
    r"cap(?:italization)?\s+table|"
    r"common\s+equity|"
    r"shares?\s+outstanding|"
    r"\b[\d,]{4,}\s+shares?\b|"
    r"\bshares?\s+(?:issued|granted|outstanding)\b"
    r")"
)
_OWNERSHIP_PERIMETER_RE = re.compile(
    r"(?i)(?:"
    r"total evidenced common equity|"
    r"\bshares?\b|"
    r"securities[\s-]*ledger|"
    r"\bCS-\d+\b|"
    r"%\s*of common|"
    r"option holder|"
    r"cap(?:italization)?\s+table"
    r")"
)
_LEDGER_SIZING_RE = re.compile(
    r"(?i)(?:"
    r"securities[\s-]*ledger|"
    r"\bCS-\d+\b|"
    r"stock\s+option|"
    r"common\s+equity|"
    r"\bshares?\b|"
    r"information\s+request|"
    r"quality\s+(?:pass|fail|rework)|"
    r"reliance\s+blocked"
    r")"
)
_QA_META_RE = re.compile(
    r"(?i)(?:"
    r"quality\s+(?:pass|fail|rework)|"
    r"reliance\s+blocked|"
    r"information\s+request|"
    r"\bqa\s+\d+\s*/\s*\d+|"
    r"\buntested:\s*information|"
    r"\b0\s+external\s+risk|"
    r"\b0\s+claimed\s+advantage|"
    r"internal\s+prior\s*=|"
    r"databook\s+promoted|"
    r"accounting\s+period\(s\)\s+published"
    r")"
)


def _period_label(period: Any, period_type: str = "") -> str:
    text = str(period or "").strip()
    kind = (period_type or "").lower()
    if kind in _PLAN_TYPES and text and not text.endswith("P"):
        return f"{text}P"
    return text


def _reported_period_type(label: str, period_type: str) -> str:
    """Actual, ytd, ttm, or forecast. A bare year from 2026 on is forecast."""
    kind = (period_type or "").strip().lower().replace("_", " ")
    text = str(label or "").strip()
    if kind in _PLAN_TYPES or re.search(r"(?i)\b(?:plan|forecast|budget|projection)\b", text):
        return "forecast"
    if re.search(r"(?i)\b(?:fy)?20\d{2}\s*[pe]\b", text):
        return "forecast"
    partial = kind in _PARTIAL_TYPES or bool(
        re.search(r"(?i)\b(?:ytd|ttm|l12m|year to date)\b|\bjan(?:uary)?\b|\bq[1-4]\b|\bh[12]\b", text)
    )
    if partial:
        if "ytd" in kind or re.search(r"(?i)\bytd|year to date|\bjan(?:uary)?\b", text):
            return "ytd"
        return "ttm"
    year_match = re.search(r"(20\d{2})", text)
    year = int(year_match.group(1)) if year_match else None
    if year is not None and year >= _OPEN_YEAR and kind in {"", "actual"}:
        return "forecast"
    if kind in {"", "actual"}:
        return "actual"
    return kind


def _year_sort_key(label: str) -> int:
    match = re.search(r"(20\d{2})", str(label or ""))
    return int(match.group(1)) if match else 0


def _is_cap_table_text(text: str) -> bool:
    return bool(_CAP_TABLE_RE.search(str(text or "")))


def _is_ownership_perimeter(text: str) -> bool:
    """A share count, including a home count presented as shares, is not a market perimeter."""
    return bool(_OWNERSHIP_PERIMETER_RE.search(str(text or "")))


def _is_ledger_sizing_text(text: str) -> bool:
    return bool(_LEDGER_SIZING_RE.search(str(text or "")))


def _is_qa_meta(text: str) -> bool:
    return bool(_QA_META_RE.search(str(text or "")))


def _pl_revenue_points(hist: dict[str, Any]) -> list[tuple[str, float, str]]:
    """(label, value, period_type) for revenue. Plan years are labelled forecast."""
    spec = _spec(hist)
    facts = spec.get("period_facts") if isinstance(spec.get("period_facts"), list) else []
    points: list[tuple[str, float, str]] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        metric = str(fact.get("metric") or fact.get("line") or "")
        if not re.search(r"(?i)revenue", metric):
            continue
        raw = fact.get("value")
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        raw_label = str(fact.get("period") or fact.get("year") or "").strip()
        ptype = _reported_period_type(raw_label, str(fact.get("period_type") or "actual"))
        label = _period_label(raw_label, ptype)
        if label:
            points.append((label, float(raw), ptype))
    if points:
        return points
    lines = spec.get("pl_lines") if isinstance(spec.get("pl_lines"), list) else []
    for line in lines:
        if not isinstance(line, dict):
            continue
        if not re.search(r"(?i)^revenue|net sales|total revenue", str(line.get("line_item") or "")):
            continue
        for key, raw in line.items():
            match = re.fullmatch(r"fy(\d{4})_value", str(key))
            if not match or not isinstance(raw, (int, float)) or isinstance(raw, bool):
                continue
            year = match.group(1)
            stored = str(line.get(f"fy{year}_period_type") or "actual")
            ptype = _reported_period_type(year, stored)
            points.append((_period_label(year, ptype), float(raw), ptype))
    return points


def revenue_for_snapshot(hist: dict[str, Any]) -> tuple[list[tuple[str, float, str]], list[tuple[str, float, str]]]:
    """Full-year actuals, then partial periods. Plan years are omitted."""
    actuals: list[tuple[str, float, str]] = []
    partials: list[tuple[str, float, str]] = []
    for label, value, ptype in _pl_revenue_points(hist):
        kind = (ptype or "").lower()
        if kind == "actual":
            actuals.append((label, value, kind))
        elif kind in {"ytd", "ttm"}:
            partials.append((label, value, kind))
    actuals.sort(key=lambda point: _year_sort_key(point[0]))
    return actuals, partials


def _margin_text(hist: dict[str, Any]) -> str | None:
    spec = _spec(hist)
    rows = spec.get("growth_and_margins") if isinstance(spec.get("growth_and_margins"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if re.search(r"(?i)ebitda", str(row.get("metric") or "")):
            value = row.get("value")
            pct = _pct_from(value)
            period = row.get("period") or ""
            if pct is not None:
                return f"{pct:.1f}% EBITDA margin" + (f" ({period})" if period else "")
            if _filled(value):
                return _clean(f"{value} EBITDA margin", 80)
    return None


def _source_line(ctx: BuildContext, *keys: str) -> str:
    names: list[str] = []
    for key in keys:
        agent = _resolve(ctx, key)
        spec = _spec(agent)
        for item in list(agent.get("sources") or []) + list(spec.get("primary_sources") or []) + list(spec.get("sources") or []):
            label = item.get("name") if isinstance(item, dict) else item
            text = _clean(label, 80)
            if text and text not in names:
                names.append(text)
            if len(names) >= 4:
                break
    if not names:
        return "Source: diligence agent outputs for this deal."
    return "Source: " + "; ".join(names)


def _findings(agent: dict[str, Any], limit: int = 4) -> list[str]:
    spec = _spec(agent)
    out: list[str] = []
    for key in ("findings", "insight_snapshot", "trend_headline"):
        raw = spec.get(key) if key != "findings" else (spec.get("findings") or agent.get("findings"))
        items = raw if isinstance(raw, list) else ([raw] if _filled(raw) else [])
        for item in items:
            text = item.get("text") if isinstance(item, dict) else item
            cleaned = _clean(text, 240)
            if cleaned and cleaned not in out:
                out.append(cleaned)
            if len(out) >= limit:
                return out
    return out


def plan_cdd_deck(ctx: BuildContext) -> DeckPlan:
    company = _company(ctx)
    pages: list[Page] = []
    withheld: list[tuple[str, str]] = []
    chapter_pages: dict[str, list[Page]] = {title: [] for _n, title, _s in _CHAPTERS}

    def keep(chapter: str, page: Page | None, why: str) -> None:
        if page is None:
            withheld.append((why.split(":", 1)[0], why))
            return
        page.chapter = chapter
        chapter_pages[chapter].append(page)

    if _chapter_enabled(ctx, "Business Introduction & Market Primer"):
        keep("Business Introduction & Market Primer", _page_snapshot(ctx, company), "Company snapshot: no revenue or EBITDA series")
        keep("Business Introduction & Market Primer", _page_history(ctx, company), "Platform history: no history events")
        keep("Business Introduction & Market Primer", _page_cost(ctx, company), "Value chain: no cost structure")
        keep("Business Introduction & Market Primer", _page_segments(ctx, company), "Segments: no segment exhibit")
        keep("Business Introduction & Market Primer", _page_protection(ctx, company), "Protection: no evidenced moat or contract concentration")
    if _chapter_enabled(ctx, "Investment Highlights"):
        keep("Investment Highlights", _page_thesis(ctx, company), "Highlights: no executive finding")
        keep("Investment Highlights", _page_sizing(ctx, company), "Sizing: no TAM, SAM or SOM figure")
        keep("Investment Highlights", _page_growth(ctx, company), "Growth decomposition: no revenue bridge")
        keep("Investment Highlights", _page_claims(ctx, company), "Claim test: no differentiators to test")
    if _chapter_enabled(ctx, "Market Dynamics & Opportunity"):
        keep("Market Dynamics & Opportunity", _page_definition(ctx, company), "Market definition: perimeter not stated")
        keep("Market Dynamics & Opportunity", _page_sam_lines(ctx, company), "SAM lines: fewer than two sized lines")
        keep("Market Dynamics & Opportunity", _page_mix(ctx, company), "Mix shift: no multi-year segment revenue")
        keep("Market Dynamics & Opportunity", _page_drivers(ctx, company), "Demand drivers: none evidenced")
        keep("Market Dynamics & Opportunity", _page_plan(ctx, company), "Plan versus market: plan rate or market rate missing")
    if _chapter_enabled(ctx, "Competitive Landscape"):
        keep("Competitive Landscape", _page_competitors(ctx, company), "Competitors: no named peers")
        keep("Competitive Landscape", _page_positioning(ctx, company), "Positioning: no comparison")
        keep("Competitive Landscape", _page_price(ctx, company), "Price: no evidenced price points")
        keep("Competitive Landscape", _page_retention(ctx, company), "Retention: no GRR or NRR")
    if _chapter_enabled(ctx, "Growth Opportunities"):
        keep("Growth Opportunities", _page_levers(ctx, company), "Growth levers: none evidenced")
        keep("Growth Opportunities", _page_customers(ctx, company), "Customers: no named accounts or segments")
        keep("Growth Opportunities", _page_geography(ctx, company), "Geography: no prioritised locations")
        keep("Growth Opportunities", _page_initiatives(ctx, company), "Initiatives: no product or capacity items")
        keep("Growth Opportunities", _page_synergy(ctx, company), "M&A: no synergy or acquisition record")
    if _chapter_enabled(ctx, "Appendix A - Market Sizing Methodology"):
        keep("Appendix A - Market Sizing Methodology", _page_method(ctx, company), "Sizing method: no build steps")

    active = [(num, title, sub) for num, title, sub in _CHAPTERS if chapter_pages.get(title)]
    pages.append(_page_cover(ctx, company))
    pages.append(_page_disclaimer(ctx, company))
    pages.append(_page_mandate(ctx, company, active))
    pages.append(_page_contents(active))
    pages.append(_page_hierarchy(ctx))

    for num, title, subtitle in active:
        pages.append(Page(
            kind="divider",
            section=title,
            title=title,
            subtitle=subtitle,
            chapter=num,
            bullets=[f"{n}  {name}" for n, name, _s in active],
        ))
        pages.extend(chapter_pages[title])

    if _chapter_enabled(ctx, "Appendix B - Evidence & Audit Trail"):
        audit = _audit_pages(ctx, withheld)
        if audit:
            num, title, subtitle = _CHAPTERS[-1]
            pages.append(Page(
                kind="divider",
                section=title,
                title=title,
                subtitle=subtitle,
                chapter=num,
                bullets=[f"{n}  {name}" for n, name, _s in active] + [f"{num}  {title}"],
            ))
            pages.extend(audit)

    glossary = _page_glossary(pages)
    if glossary:
        pages.extend(glossary)
    pages.append(_page_close(company))
    return DeckPlan(pages=pages, withheld=withheld)


def _page_cover(ctx: BuildContext, company: str) -> Page:
    sector = ""
    if ctx.profile and ctx.profile.sector and ctx.profile.sector != "generic":
        sector = str(ctx.profile.sector).replace("_", " ")
    return Page(
        kind="cover",
        title=f"Commercial Due Diligence: {company}",
        subtitle=sector or "Commercial due diligence",
        source=date.today().strftime("%B %Y"),
        note="Draft for discussion. Prepared for DiligenceIQ.",
    )


def _page_disclaimer(ctx: BuildContext, company: str) -> Page:
    modules = len([k for k, v in ctx.agent_outputs.items() if isinstance(v, dict) and v])
    return Page(
        kind="content",
        section="ENGAGEMENT OVERVIEW",
        title="Disclaimer & reliance limitations",
        subtitle=(
            f"This report is limited to the diligence outputs and data-room documents listed in the source register. "
            f"It is prepared for discussion of {company} and is not a recommendation to invest."
        ),
        bullets=[
            f"Evidence comprises {modules} diligence module(s) loaded for this deal. A module that did not return a fact base is an open request, not a negative finding.",
            "No customer survey is assumed. Customer-side findings rest on company records and management statements unless a research source is cited.",
            "Plan years are marked with a P suffix and are not results. Where accounts and a CIM disagree, the accounts are used.",
        ],
        source="Source: DiligenceIQ. Scope and reliance follow the v4 CDD standard.",
        note="Grade: method. No deal figure on this page.",
    )


def _page_mandate(ctx: BuildContext, company: str, active: list[tuple[str, str, str]]) -> Page:
    plan = _spec(_resolve(ctx, "market_volume_and_growth")).get("plan_vs_market")
    plan_bit = ""
    if isinstance(plan, dict) and _filled(plan.get("plan_rate")):
        plan_bit = f" The management plan rate on record is {_clean(plan.get('plan_rate'), 40)}."
    work = [title for _n, title, _s in active if not title.startswith("Appendix")]
    return Page(
        kind="content",
        section="ENGAGEMENT OVERVIEW",
        title=f"The mandate: test whether {company}'s trading, customers and market support the management plan",
        subtitle="Each finding is graded established, indicated or asserted by the evidence behind it." + plan_bit,
        bullets=work or ["Business introduction", "Market", "Competition", "Growth"],
        source=_source_line(ctx, "deal_context_and_objectives", "strategic_direction"),
        note="Grade: indicated where a plan figure is cited; otherwise the mandate is the question, not a finding.",
    )


def _page_contents(active: list[tuple[str, str, str]]) -> Page:
    return Page(
        kind="content",
        section="ENGAGEMENT OVERVIEW",
        title="Contents",
        bullets=[f"{num}   {title}" for num, title, _s in active] or ["No evidenced chapters — see exceptions."],
        source="Source: DiligenceIQ. Chapters with no supporting exhibit are withheld.",
    )


def _page_hierarchy(ctx: BuildContext) -> Page:
    return Page(
        kind="content",
        section="ENGAGEMENT OVERVIEW",
        title="The findings rest on the data room first: company accounts and workbooks outrank the CIM, and the CIM outranks the agent outputs",
        subtitle="Where the agents and the data room disagree, the data room is used and the agent finding is logged as an exception.",
        headers=["Rank", "Source", "Use"],
        rows=[
            ["1", "Monthly accounts / QBO actuals", "Established results"],
            ["2", "Company workbook (model, retention, sizing)", "Indicated, labelled as the company's model"],
            ["3", "CIM and management material", "Asserted until tied to accounts"],
            ["4", "Diligence agent outputs", "A lead. Rejected when off-perimeter or uncited"],
        ],
        source=_source_line(ctx, "scope_and_methodology", "historical_performance"),
        note="Grade: method.",
    )


def _page_snapshot(ctx: BuildContext, company: str) -> Page | None:
    hist = _resolve(ctx, "historical_performance")
    actuals, partials = revenue_for_snapshot(hist)
    points = actuals or partials
    if len(points) < 1:
        headline = [line for line in _findings(hist, 4) if not _is_qa_meta(line) and not _is_cap_table_text(line)]
        if not headline:
            return None
        return Page(
            kind="content",
            section="BUSINESS INTRODUCTION & MARKET PRIMER",
            title=_clean(headline[0], 160),
            subtitle=f"Historical performance for {company}. A full revenue series was not in the accounts extract.",
            bullets=headline[:4],
            source=_source_line(ctx, "historical_performance"),
            note="Grade: indicated. No chart — series missing.",
        )
    latest = points[-1]
    prior = points[-2] if len(points) > 1 else None
    title = f"{_fmt_number(_revenue_millions(latest[1]), scale='million')} revenue in {latest[0]}"
    if prior and prior[1]:
        change = (latest[1] - prior[1]) / abs(prior[1]) * 100
        title = (
            f"Revenue was {_fmt_number(_revenue_millions(prior[1]), scale='million')} in {prior[0]} and "
            f"{_fmt_number(_revenue_millions(latest[1]), scale='million')} in {latest[0]} ({change:+.0f}%)"
        )
    margin = _margin_text(hist)
    kpis = [
        (f"Revenue {label}", _fmt_number(_revenue_millions(value), scale="million"))
        for label, value, _t in points[-4:]
    ]
    if actuals and partials:
        label, value, _t = partials[-1]
        kpis.append((f"Revenue {label}", _fmt_number(_revenue_millions(value), scale="million")))
    if margin:
        kpis.append(("Margin", margin))
    chart = None
    if len(points) >= 2:
        chart = ChartSpec(
            kind="column",
            categories=[p[0] for p in points[-6:]],
            series=[("Revenue $M", [_revenue_millions(p[1]) for p in points[-6:]])],
        )
    return Page(
        kind="content",
        section="BUSINESS INTRODUCTION & MARKET PRIMER",
        title=title,
        subtitle="Actuals from the accounts extract. Plan years are excluded from this chart.",
        kpis=kpis[:5],
        chart=chart,
        source=_source_line(ctx, "historical_performance", "company_background"),
        note="Grade: established when the series is an accounts extract; otherwise indicated.",
    )


def _page_history(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "company_background"))
    ownership = spec.get("ownership") if isinstance(spec.get("ownership"), dict) else {}
    events = spec.get("history_events") or ownership.get("history_events")
    if not isinstance(events, list) or not events:
        products = spec.get("products_in_company_terms") or spec.get("products") or []
        if not isinstance(products, list) or not products:
            return None
        return Page(
            kind="content",
            section="BUSINESS INTRODUCTION & MARKET PRIMER",
            title=f"{company} is described in its own product terms",
            bullets=[_clean(p, 120) for p in products[:6] if _filled(p)],
            source=_source_line(ctx, "company_background"),
            note="Grade: indicated. No milestone timeline in the background spec.",
        )
    rows = []
    for event in events[:6]:
        if isinstance(event, dict):
            when = _clean(event.get("year") or event.get("date") or event.get("when") or "—", 24)
            what = _clean(event.get("event") or event.get("description") or event.get("text") or "", 140)
        else:
            when, what = "—", _clean(event, 140)
        if what and not _is_cap_table_text(f"{when} {what}"):
            rows.append([when, what])
    if not rows:
        return None
    return Page(
        kind="content",
        section="BUSINESS INTRODUCTION & MARKET PRIMER",
        title=f"How {company} was assembled, from the events in the company record",
        subtitle="Milestones are management's unless the accounts also show them.",
        headers=["When", "Event"],
        rows=rows,
        source=_source_line(ctx, "company_background"),
        note="Grade: asserted unless an event cites accounts.",
    )


def _page_cost(ctx: BuildContext, company: str) -> Page | None:
    cost = _resolve(ctx, "cost_structure")
    findings = _findings(cost, 4)
    spec = _spec(cost)
    rows_raw = spec.get("cost_lines") or spec.get("lines") or spec.get("cost_buckets") or []
    rows: list[list[str]] = []
    if isinstance(rows_raw, list):
        for line in rows_raw[:6]:
            if not isinstance(line, dict):
                continue
            name = _clean(line.get("line_item") or line.get("name") or line.get("bucket") or "", 40)
            value = _fmt_money(line) or _clean(line.get("value") or line.get("amount") or "", 24)
            share = _clean(line.get("share") or line.get("pct_of_revenue") or "", 16)
            if name and value:
                rows.append([name, value, share or "—"])
    if not rows and not findings:
        return None
    title = findings[0] if findings else f"Cost structure for {company}"
    return Page(
        kind="content",
        section="BUSINESS INTRODUCTION & MARKET PRIMER",
        title=_clean(title, 160),
        subtitle="Cost lines from the cost-structure module. Shares are of revenue only when the spec states them.",
        headers=["Cost", "Amount", "Share"] if rows else [],
        rows=rows,
        bullets=[] if rows else findings[:4],
        source=_source_line(ctx, "cost_structure", "historical_performance"),
        note="Grade: indicated.",
    )


def _page_segments(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "customer_segmentation"))
    segments = spec.get("segments") if isinstance(spec.get("segments"), list) else []
    rows = []
    cats: list[str] = []
    values: list[float] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        name = _clean(seg.get("name") or "", 40)
        if not name:
            continue
        share = seg.get("share_pct")
        share_txt = f"{float(share):.0f}%" if isinstance(share, (int, float)) else _clean(share or seg.get("use_case") or "", 40)
        rows.append([name, share_txt or "—", _clean(seg.get("key_driver") or seg.get("use_case") or "", 80)])
        if isinstance(share, (int, float)):
            cats.append(name)
            values.append(float(share))
    if len(rows) < 2:
        return None
    chart = ChartSpec(kind="column", categories=cats, series=[("Share %", values)]) if len(cats) >= 2 else None
    return Page(
        kind="content",
        section="BUSINESS INTRODUCTION & MARKET PRIMER",
        title=f"{company} is reported in {len(rows)} segments",
        subtitle="Segment names and shares from the customer-segmentation module. A share is shown only when the spec states one.",
        headers=["Segment", "Share", "Driver"],
        rows=rows[:6],
        chart=chart,
        source=_source_line(ctx, "customer_segmentation"),
        note="Grade: indicated.",
    )


def _page_protection(ctx: BuildContext, company: str) -> Page | None:
    diff = _resolve(ctx, "competitive_differentiation")
    findings = _findings(diff, 3)
    risks = _findings(_resolve(ctx, "market_risk"), 2)
    if not findings and not risks:
        return None
    return Page(
        kind="content",
        section="BUSINESS INTRODUCTION & MARKET PRIMER",
        title=f"What the record says protects {company}, and what it does not establish",
        subtitle="A moat is not adopted from an agent label. The points below are the differentiation and risk findings on file.",
        bullets=(findings + risks)[:5],
        source=_source_line(ctx, "competitive_differentiation", "market_risk"),
        note="Grade: asserted until a contract or account exhibit is cited.",
    )


def _page_thesis(ctx: BuildContext, company: str) -> Page | None:
    findings = _findings(_resolve(ctx, "executive_summary"), 2) or _findings(_resolve(ctx, "recommendations"), 2)
    if not findings:
        return None
    return Page(
        kind="content",
        section="INVESTMENT HIGHLIGHTS",
        title=_clean(findings[0], 170),
        subtitle=f"Lead finding for {company}. It is stated at the strength of the modules behind it, not as an investment recommendation.",
        bullets=findings[:4],
        source=_source_line(ctx, "executive_summary", "recommendations", "historical_performance"),
        note="Grade: indicated. Not a recommendation to invest.",
    )


def _sizing_metrics(ctx: BuildContext) -> list[tuple[str, str]]:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    out = []
    for key, label in (("tam", "TAM"), ("sam", "SAM"), ("som", "SOM")):
        text = _fmt_money(spec.get(key))
        if text:
            out.append((label, text))
    return out


def _page_sizing(ctx: BuildContext, company: str) -> Page | None:
    metrics = _sizing_metrics(ctx)
    if not metrics:
        return None
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    note_bits = []
    for key in ("market_growth_note", "insight_snapshot"):
        if _filled(spec.get(key)):
            note_bits.append(_clean(spec.get(key), 180))
    cats = [label for label, _v in metrics]
    values = []
    for _label, text in metrics:
        match = re.search(r"([\d,.]+)", text)
        values.append(float(match.group(1).replace(",", "")) if match else 0.0)
    joined = ", ".join(f"{label} {value}" for label, value in metrics)
    return Page(
        kind="content",
        section="INVESTMENT HIGHLIGHTS",
        title=f"On the evidenced model the market for {company} is {joined}",
        subtitle="TAM, SAM and SOM from the market-volume module. The figure is the company's or the agent's only when that module says so.",
        kpis=[(label, value) for label, value in metrics],
        chart=ChartSpec(kind="column", categories=cats, series=[("Market", values)]),
        bullets=note_bits[:2],
        source=_source_line(ctx, "market_volume_and_growth"),
        note="Grade: indicated. Third-party sizing is not assumed.",
    )


def _page_growth(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    hist = _spec(_resolve(ctx, "historical_performance"))
    decomp = spec.get("growth_decomposition") if isinstance(spec.get("growth_decomposition"), list) else []
    rows = []
    for item in decomp:
        if not isinstance(item, dict):
            continue
        driver = _clean(item.get("driver") or "", 40)
        contrib = _clean(item.get("contribution") or "", 40)
        if driver and contrib:
            rows.append([driver, contrib, _clean(item.get("evidence") or "", 80)])
    points = [
        p for p in _pl_revenue_points(_resolve(ctx, "historical_performance"))
        if p[2].lower() in {"actual", "ytd", "ttm", ""}
    ]
    if not rows and len(points) >= 2:
        for (label, value, _t), (plabel, pvalue, _pt) in zip(points[1:], points):
            if pvalue:
                delta = _revenue_millions(value) - _revenue_millions(pvalue)
                rows.append([f"{plabel} → {label}", _fmt_number(delta, scale="million"), "Revenue change"])
    if not rows:
        headline = hist.get("trend_headline")
        if not _filled(headline):
            return None
        return Page(
            kind="content",
            section="INVESTMENT HIGHLIGHTS",
            title=_clean(headline, 160),
            source=_source_line(ctx, "historical_performance"),
            note="Grade: indicated. No decomposition rows.",
        )
    return Page(
        kind="content",
        section="INVESTMENT HIGHLIGHTS",
        title=f"What changed {company}'s revenue, by the decomposition on record",
        headers=["Driver", "Contribution", "Evidence"],
        rows=rows[:6],
        source=_source_line(ctx, "historical_performance", "market_volume_and_growth"),
        note="Grade: established for account changes; indicated for attributed drivers.",
    )


def _page_claims(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "competitive_differentiation"))
    items = spec.get("differentiators") or spec.get("claims") or spec.get("moat") or []
    rows = []
    if isinstance(items, list):
        for item in items[:6]:
            if isinstance(item, dict):
                claim = _clean(item.get("claim") or item.get("name") or item.get("text") or "", 80)
                evidence = _clean(item.get("evidence") or item.get("support") or item.get("grade") or "", 80)
            else:
                claim, evidence = _clean(item, 80), "—"
            if claim:
                rows.append([claim, evidence or "Not in the data room"])
    if not rows:
        return None
    return Page(
        kind="content",
        section="INVESTMENT HIGHLIGHTS",
        title=f"Which of {company}'s claimed differentiators have a figure behind them",
        subtitle="Each claim is set against the evidence field on the differentiation module. An empty evidence cell is not support.",
        headers=["Claim", "Evidence on file"],
        rows=rows,
        source=_source_line(ctx, "competitive_differentiation"),
        note="Grade: per row. A claim without evidence stays asserted.",
    )


def _page_definition(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "market_definition"))
    perimeter = spec.get("perimeter") or spec.get("market_definition") or spec.get("definition") or spec.get("insight_snapshot")
    if not _filled(perimeter) and not _findings(_resolve(ctx, "market_definition"), 1):
        return None
    raw_text = perimeter if _filled(perimeter) else _findings(_resolve(ctx, "market_definition"), 1)[0]
    if _is_ownership_perimeter(str(raw_text)):
        return None
    text = _clean(raw_text, 200)
    excluded = spec.get("excluded") or spec.get("out_of_perimeter") or []
    bullets = [text]
    if isinstance(excluded, list):
        bullets.extend(_clean(x, 120) for x in excluded[:3] if _filled(x))
    elif _filled(excluded):
        bullets.append(_clean(excluded, 140))
    return Page(
        kind="content",
        section="MARKET DYNAMICS & OPPORTUNITY",
        title=f"The market used for {company} is the perimeter in the market-definition module",
        subtitle=text,
        bullets=[b for b in bullets[1:] if b] or ["Adjacent markets stay out of the sizing unless the perimeter includes them."],
        source=_source_line(ctx, "market_definition"),
        note="Grade: indicated. Agent perimeters that disagree with this page are exceptions.",
    )


def _page_sam_lines(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    lines = spec.get("lines") or spec.get("sam_lines") or spec.get("revenue_lines") or []
    rows = []
    cats: list[str] = []
    vals: list[float] = []
    if isinstance(lines, list):
        for line in lines:
            if not isinstance(line, dict):
                continue
            name = _clean(line.get("name") or line.get("line") or "", 40)
            money = _fmt_money(line) or _fmt_money(line.get("sam") or line.get("value"))
            if name and money:
                rows.append([name, money])
                match = re.search(r"([\d,.]+)", money)
                if match:
                    cats.append(name)
                    vals.append(float(match.group(1).replace(",", "")))
    if len(rows) < 2:
        return None
    return Page(
        kind="content",
        section="MARKET DYNAMICS & OPPORTUNITY",
        title=f"Serviceable market for {company} by the lines in the sizing module",
        headers=["Line", "Size"],
        rows=rows[:6],
        chart=ChartSpec(kind="column", categories=cats, series=[("SAM", vals)]) if len(cats) >= 2 else None,
        source=_source_line(ctx, "market_volume_and_growth"),
        note="Grade: indicated. Company model unless the source says otherwise.",
    )


def _page_mix(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "customer_segmentation"))
    series = spec.get("mix_by_year") or spec.get("revenue_by_segment_year") or []
    if not isinstance(series, list) or len(series) < 2:
        return None
    # series: [{year, segment, value}]
    years: list[str] = []
    by_seg: dict[str, dict[str, float]] = {}
    for row in series:
        if not isinstance(row, dict):
            continue
        year = str(row.get("year") or row.get("period") or "")
        seg = str(row.get("segment") or "")
        raw = row.get("value")
        if not year or not seg or not isinstance(raw, (int, float)):
            continue
        if year not in years:
            years.append(year)
        by_seg.setdefault(seg, {})[year] = float(raw)
    if len(years) < 2 or not by_seg:
        return None
    chart_series = []
    for seg, vals in list(by_seg.items())[:4]:
        chart_series.append((seg, [vals.get(y, 0.0) for y in years]))
    return Page(
        kind="content",
        section="MARKET DYNAMICS & OPPORTUNITY",
        title=f"{company}'s mix across {len(years)} periods on the segment revenue exhibit",
        chart=ChartSpec(kind="column", categories=years, series=chart_series),
        source=_source_line(ctx, "customer_segmentation", "historical_performance"),
        note="Grade: established when the exhibit is accounts; otherwise indicated.",
    )


def _page_drivers(ctx: BuildContext, company: str) -> Page | None:
    findings = _findings(_resolve(ctx, "demand_drivers"), 4)
    if not findings:
        return None
    return Page(
        kind="content",
        section="MARKET DYNAMICS & OPPORTUNITY",
        title=f"What the demand-driver module says moves the market {company} sells into",
        bullets=findings,
        source=_source_line(ctx, "demand_drivers"),
        note="Grade: indicated.",
    )


def _page_plan(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    plan = spec.get("plan_vs_market") if isinstance(spec.get("plan_vs_market"), dict) else {}
    if not _filled(plan.get("plan_rate")) and not _filled(plan.get("market_rate")):
        strategic = _findings(_resolve(ctx, "strategic_direction"), 2)
        if not strategic:
            return None
        return Page(
            kind="content",
            section="MARKET DYNAMICS & OPPORTUNITY",
            title=f"The plan for {company}, as stated — not yet tested against a market rate",
            bullets=strategic,
            source=_source_line(ctx, "strategic_direction"),
            note="Grade: asserted. No plan-versus-market rates.",
        )
    rows = [
        ["Plan rate", _clean(plan.get("plan_rate"), 40)],
        ["Market rate", _clean(plan.get("market_rate"), 40)],
        ["What must be true", _clean(plan.get("what_must_be_true") or plan.get("plain_english"), 120)],
    ]
    for label, value, ptype in _pl_revenue_points(_resolve(ctx, "historical_performance")):
        if ptype.lower() in {"plan", "forecast", "budget", "projection"}:
            rows.append([f"Plan revenue {label}", _fmt_number(_revenue_millions(value), scale="million")])
    return Page(
        kind="content",
        section="MARKET DYNAMICS & OPPORTUNITY",
        title=f"{company}'s plan rate against the market rate on record",
        subtitle=_clean(plan.get("plain_english") or "", 180),
        headers=["Item", "On record"],
        rows=[row for row in rows if row[1]],
        source=_source_line(ctx, "market_volume_and_growth", "strategic_direction"),
        note="Grade: indicated. The plan is not a result.",
    )


def _page_competitors(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "competitor_identification"))
    rows_raw = spec.get("competitors") if isinstance(spec.get("competitors"), list) else []
    rows = []
    for row in rows_raw[:6]:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("name") or row.get("competitor") or "", 40)
        if not name or name.lower() == company.lower():
            continue
        geo = _clean(row.get("geography") or row.get("geo") or "", 28)
        note = _clean(row.get("position") or row.get("note") or row.get("overlap") or "", 80)
        rows.append([name, geo or "—", note or "—"])
    if not rows:
        return None
    return Page(
        kind="content",
        section="COMPETITIVE LANDSCAPE",
        title=f"Named competitors for {company} from the competitor module",
        subtitle="Peers the module named. A name without geography or overlap is still listed, and marked thin.",
        headers=["Competitor", "Geography", "Overlap"],
        rows=rows,
        source=_source_line(ctx, "competitor_identification"),
        note="Grade: indicated. Agent peers outside the stated geography are not added here.",
    )


def _page_positioning(ctx: BuildContext, company: str) -> Page | None:
    findings = _findings(_resolve(ctx, "competitive_differentiation"), 4)
    if len(findings) < 1:
        return None
    return Page(
        kind="content",
        section="COMPETITIVE LANDSCAPE",
        title=f"How {company} is positioned against the peers on file",
        bullets=findings[:4],
        source=_source_line(ctx, "competitive_differentiation"),
        note="Grade: indicated.",
    )


def _page_price(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "market_pricing"))
    points = spec.get("price_points") or spec.get("prices") or spec.get("benchmarks") or []
    rows = []
    if isinstance(points, list):
        for item in points[:6]:
            if isinstance(item, dict):
                name = _clean(item.get("name") or item.get("offer") or item.get("peer") or "", 40)
                price = _clean(item.get("price") or item.get("value") or "", 24)
            else:
                continue
            if name and price:
                rows.append([name, price])
    if len(rows) < 2:
        return None
    return Page(
        kind="content",
        section="COMPETITIVE LANDSCAPE",
        title=f"Price points on record for {company} and the named offers",
        headers=["Offer", "Price"],
        rows=rows,
        source=_source_line(ctx, "market_pricing"),
        note="Grade: indicated.",
    )


def _page_retention(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "customer_stickiness"))
    same = spec.get("retention_on_same_population") if isinstance(spec.get("retention_on_same_population"), dict) else {}
    grr = _pct_from(same.get("grr") if same else spec.get("grr"))
    nrr = _pct_from(same.get("nrr") if same else spec.get("nrr"))
    if grr is None and nrr is None:
        return None
    cats = ["Retention"]
    series = []
    kpis = []
    if grr is not None:
        series.append(("GRR %", [grr]))
        kpis.append(("GRR", f"{grr:.1f}%"))
    if nrr is not None:
        series.append(("NRR %", [nrr]))
        kpis.append(("NRR", f"{nrr:.1f}%"))
    population = _clean(same.get("population") or "stated population", 60)
    return Page(
        kind="content",
        section="COMPETITIVE LANDSCAPE",
        title=f"Retention for {company} on {population}",
        subtitle="Gross and net retention are shown only when the stickiness module states them for one population.",
        kpis=kpis,
        chart=ChartSpec(kind="column", categories=cats, series=series),
        source=_source_line(ctx, "customer_stickiness"),
        note="Grade: established when tied to the same-population workbook; otherwise indicated.",
    )


def _page_levers(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "growth_opportunities"))
    levers = spec.get("levers") or spec.get("opportunities") or []
    rows = []
    if isinstance(levers, list):
        for lever in levers[:6]:
            if isinstance(lever, dict):
                name = _clean(lever.get("name") or lever.get("lever") or "", 40)
                effect = _clean(lever.get("effect") or lever.get("impact") or lever.get("evidence") or "", 80)
            else:
                name, effect = _clean(lever, 40), "—"
            if name:
                rows.append([name, effect or "Untested"])
    if not rows:
        findings = _findings(_resolve(ctx, "growth_opportunities"), 4)
        if not findings:
            return None
        return Page(
            kind="content",
            section="GROWTH OPPORTUNITIES",
            title=f"Growth points on file for {company}",
            bullets=findings,
            source=_source_line(ctx, "growth_opportunities"),
            note="Grade: asserted until a lever has a figure.",
        )
    return Page(
        kind="content",
        section="GROWTH OPPORTUNITIES",
        title=f"Growth levers for {company}, with the effect the module states",
        headers=["Lever", "Effect on file"],
        rows=rows,
        source=_source_line(ctx, "growth_opportunities"),
        note="Grade: indicated when an effect is numeric; otherwise asserted.",
    )


def _page_customers(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "customer_segmentation"))
    logos = spec.get("logos") or spec.get("key_accounts") or spec.get("customers") or []
    names = []
    if isinstance(logos, list):
        for item in logos[:8]:
            name = item.get("name") if isinstance(item, dict) else item
            if _filled(name):
                names.append(_clean(name, 40))
    if len(names) < 2:
        return None
    return Page(
        kind="content",
        section="GROWTH OPPORTUNITIES",
        title=f"Accounts named for {company}",
        bullets=names,
        source=_source_line(ctx, "customer_segmentation", "revenue_quality"),
        note="Grade: indicated.",
    )


def _page_geography(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "customer_segmentation"))
    geos = spec.get("geo_mix") or spec.get("geographies") or []
    rows = []
    if isinstance(geos, list):
        for geo in geos[:6]:
            if isinstance(geo, dict):
                name = _clean(geo.get("name") or geo.get("geography") or "", 40)
                share = _clean(geo.get("share") or geo.get("share_pct") or geo.get("score") or "", 20)
            else:
                name, share = _clean(geo, 40), "—"
            if name:
                rows.append([name, share or "—"])
    if len(rows) < 2:
        return None
    return Page(
        kind="content",
        section="GROWTH OPPORTUNITIES",
        title=f"Where {company}'s footprint or priority locations are recorded",
        headers=["Location", "Share or score"],
        rows=rows,
        source=_source_line(ctx, "customer_segmentation"),
        note="Grade: indicated. A score ranks where to go; it is not revenue.",
    )


def _page_initiatives(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "strategic_direction"))
    items = spec.get("initiatives") or spec.get("priorities") or []
    rows = []
    if isinstance(items, list):
        for item in items[:6]:
            if isinstance(item, dict):
                name = _clean(item.get("name") or item.get("initiative") or "", 40)
                status = _clean(item.get("status") or item.get("evidence") or "", 60)
            else:
                name, status = _clean(item, 60), "—"
            if name:
                rows.append([name, status or "—"])
    if not rows:
        return None
    return Page(
        kind="content",
        section="GROWTH OPPORTUNITIES",
        title=f"Initiatives recorded for {company}, and the status on file",
        headers=["Initiative", "Status"],
        rows=rows,
        source=_source_line(ctx, "strategic_direction"),
        note="Grade: asserted until actual revenue is tied to the initiative.",
    )


def _page_synergy(ctx: BuildContext, company: str) -> Page | None:
    findings = _findings(_resolve(ctx, "synergies"), 4)
    if not findings:
        return None
    return Page(
        kind="content",
        section="GROWTH OPPORTUNITIES",
        title=f"Acquisition and synergy statements for {company} — gross until a cost is shown",
        bullets=findings,
        source=_source_line(ctx, "synergies", "company_background"),
        note="Grade: asserted. A synergy without cost, capex and overlap is not net value.",
    )


def _page_method(ctx: BuildContext, company: str) -> Page | None:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    bottom = spec.get("bottom_up") if isinstance(spec.get("bottom_up"), dict) else {}
    if not any(_filled(bottom.get(k)) for k in ("units", "capture_share", "realised_price", "arithmetic", "bottom_up_size")):
        metrics = _sizing_metrics(ctx)
        if not metrics:
            return None
        return Page(
            kind="content",
            section="APPENDIX A - MARKET SIZING METHODOLOGY",
            title=f"Sizing figures for {company} are the module outputs; the build steps were not stored",
            kpis=metrics,
            source=_source_line(ctx, "market_volume_and_growth"),
            note="Grade: indicated. Method steps withheld because bottom_up is empty.",
        )
    rows = []
    for key, label in (
        ("units", "Units"),
        ("capture_share", "Capture"),
        ("realised_price", "Price"),
        ("arithmetic", "Arithmetic"),
        ("bottom_up_size", "Bottom-up size"),
    ):
        if _filled(bottom.get(key)) and not _is_ledger_sizing_text(str(bottom.get(key))):
            rows.append([label, _clean(bottom.get(key), 80)])
    if not rows:
        return None
    return Page(
        kind="content",
        section="APPENDIX A - MARKET SIZING METHODOLOGY",
        title=f"How the {company} sizing was built, from the bottom-up record",
        headers=["Step", "On record"],
        rows=rows,
        source=_source_line(ctx, "market_volume_and_growth"),
        note="Grade: indicated. Every SOM figure moves with these assumptions.",
    )


def _audit_pages(ctx: BuildContext, withheld: list[tuple[str, str]]) -> list[Page]:
    pages: list[Page] = []
    rows = []
    for key, agent in ctx.agent_outputs.items():
        if not isinstance(agent, dict):
            continue
        spec = _spec(agent)
        quality = spec.get("quality_verdict")
        reliance = spec.get("reliance_verdict")
        if not _filled(quality) and not _filled(reliance):
            continue
        rows.append([key.replace("_", " "), _clean(quality or "—", 16), _clean(reliance or "—", 16)])
    if rows:
        pages.append(Page(
            kind="content",
            section="APPENDIX B - EVIDENCE & AUDIT TRAIL",
            title="Module verdicts, restated from the quality and reliance fields on each module",
            headers=["Module", "Quality", "Reliance"],
            rows=rows[:12],
            source="Source: DiligenceIQ analysis.",
            note="Grade: method. A PASS on a thin module is not a finding.",
        ))
    names: list[str] = []
    for agent in ctx.agent_outputs.values():
        if not isinstance(agent, dict):
            continue
        spec = _spec(agent)
        for item in list(agent.get("sources") or []) + list(spec.get("primary_sources") or [])[:8]:
            label = item.get("name") if isinstance(item, dict) else item
            text = _clean(label, 90)
            if text and text not in names:
                names.append(text)
    if names:
        pages.append(Page(
            kind="content",
            section="APPENDIX B - EVIDENCE & AUDIT TRAIL",
            title="Sources the report rests on",
            bullets=names[:12],
            source="Source: DiligenceIQ analysis.",
            note="Grade: method.",
        ))
    exception_rows = [[name, why] for name, why in withheld[:12]]
    questions = []
    for agent in ctx.agent_outputs.values():
        spec = _spec(agent) if isinstance(agent, dict) else {}
        for q in spec.get("questions") or []:
            if isinstance(q, dict) and _filled(q.get("question")):
                questions.append(_clean(q.get("question"), 120))
            if len(questions) >= 6:
                break
    if exception_rows or questions:
        pages.append(Page(
            kind="content",
            section="APPENDIX B - EVIDENCE & AUDIT TRAIL",
            title="What this report could not establish, and the page that was withheld",
            subtitle=f"{len(withheld)} page(s) withheld. Open questions from the modules follow.",
            headers=["Withheld", "Why"] if exception_rows else [],
            rows=exception_rows,
            bullets=questions[:6],
            source="Source: DiligenceIQ analysis.",
            note="Grade: method. A withheld page is not a negative finding.",
        ))
    return pages


_GLOSSARY = (
    ("TAM", "Total addressable market, as defined on the market-definition page."),
    ("SAM", "Serviceable market inside that perimeter."),
    ("SOM", "Obtainable market after the capture assumptions in the sizing method."),
    ("GRR", "Gross revenue retention on one stated population."),
    ("NRR", "Net revenue retention on that same population."),
    ("EBITDA", "Earnings before interest, tax, depreciation and amortisation."),
    ("P", "A P suffix marks a plan year. It is not a result."),
)


def _page_glossary(pages: list[Page]) -> list[Page]:
    blob = " ".join(
        " ".join([p.title, p.subtitle, p.source, " ".join(p.bullets), " ".join(h for h in p.headers)] + [" ".join(r) for r in p.rows])
        for p in pages
    )
    rows = []
    for term, meaning in _GLOSSARY:
        if re.search(rf"\b{re.escape(term)}\b", blob):
            rows.append([term, meaning])
    if not rows:
        return []
    return [Page(
        kind="content",
        section="ENGAGEMENT OVERVIEW",
        title="Terms and abbreviations used in this report",
        subtitle="Plan years carry a P suffix and are never results.",
        headers=["Term", "As used here"],
        rows=rows,
        source="Source: DiligenceIQ analysis.",
        note="Terms are listed only where they appear in this report.",
    )]


def _page_close(company: str) -> Page:
    return Page(
        kind="close",
        title=f"DiligenceIQ · Commercial due diligence on {company}",
        subtitle="Draft for discussion. This document is confidential and prepared solely for the addressee.",
        source=date.today().strftime("%B %Y"),
    )


def _add_text(slide, left, top, width, height, text, *, size=14, bold=False, color=_SLATE, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Calibri"
    return box


def _fill(shape, color: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _chrome(slide, page: Page, index: int, total: int) -> None:
    header = page.section or "DILIGENCEIQ  ·  CDD"
    _add_text(slide, 0.45, 0.16, 8.2, 0.28, header, size=11, bold=True, color=_NAVY)
    _add_text(slide, 8.4, 0.16, 4.5, 0.28, "STRICTLY PRIVATE & CONFIDENTIAL", size=10, bold=True, color=_RED, align=PP_ALIGN.RIGHT)
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.45), Inches(0.48), Inches(12.4), Inches(0.03))
    _fill(rule, _ORANGE)
    foot = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.45), Inches(7.08), Inches(12.4), Inches(0.015))
    _fill(foot, _ORANGE)
    _add_text(
        slide, 0.45, 7.14, 9.2, 0.26,
        f"{page.section or 'CDD'}  ·  © DiligenceIQ",
        size=10, color=_MUTED,
    )
    _add_text(slide, 10.6, 7.12, 2.2, 0.28, f"{index:02d}", size=12, bold=True, color=_NAVY, align=PP_ALIGN.RIGHT)


def _render_chart(slide, chart: ChartSpec, left: float, top: float, width: float, height: float) -> None:
    data = CategoryChartData()
    data.categories = chart.categories
    for name, values in chart.series:
        data.add_series(name, values)
    kind = XL_CHART_TYPE.LINE if chart.kind == "line" else XL_CHART_TYPE.COLUMN_CLUSTERED
    graphic = slide.shapes.add_chart(kind, Inches(left), Inches(top), Inches(width), Inches(height), data)
    plot = graphic.chart.plots[0]
    plot.has_data_labels = False
    graphic.chart.has_legend = len(chart.series) > 1


def _render_table(slide, headers: list[str], rows: list[list[str]], left: float, top: float, width: float, height: float) -> None:
    if not headers or not rows:
        return
    table_shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(left), Inches(top), Inches(width), Inches(height))
    table = table_shape.table
    for c, header in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = header
        for p in cell.text_frame.paragraphs:
            for run in p.runs:
                run.font.size = Pt(11)
                run.font.bold = True
                run.font.color.rgb = _WHITE
        cell.fill.solid()
        cell.fill.fore_color.rgb = _NAVY
    for r, row in enumerate(rows, start=1):
        for c in range(len(headers)):
            text = row[c] if c < len(row) else ""
            cell = table.cell(r, c)
            cell.text = text
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(11)
                    run.font.color.rgb = _SLATE
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = _LIGHT


def _render_content(slide, page: Page) -> None:
    _add_text(slide, 0.5, 0.62, 12.3, 1.15, page.title, size=20, bold=True, color=_NAVY)
    top = 1.85
    if page.subtitle:
        _add_text(slide, 0.5, top, 12.3, 0.55, page.subtitle, size=13, color=_SLATE)
        top = 2.6
    if page.kpis:
        width = min(2.4, 12.2 / max(1, len(page.kpis)))
        for i, (label, value) in enumerate(page.kpis[:5]):
            left = 0.5 + i * (width + 0.12)
            card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(0.85))
            _fill(card, _LIGHT)
            _add_text(slide, left + 0.08, top + 0.08, width - 0.16, 0.28, label, size=10, color=_MUTED)
            _add_text(slide, left + 0.08, top + 0.36, width - 0.16, 0.4, value, size=16, bold=True, color=_NAVY)
        top += 1.0
    body_top = top
    if page.chart and (page.rows or page.bullets):
        _render_chart(slide, page.chart, 0.5, body_top, 5.6, 3.3)
        if page.headers:
            _render_table(slide, page.headers, page.rows[:6], 6.3, body_top, 6.5, 3.2)
        else:
            _add_text(slide, 6.3, body_top, 6.5, 3.2, "\n".join(f"•  {b}" for b in page.bullets[:6]), size=13, color=_SLATE)
    elif page.chart:
        _render_chart(slide, page.chart, 0.5, body_top, 12.2, 3.6)
    elif page.headers:
        _render_table(slide, page.headers, page.rows[:8], 0.5, body_top, 12.2, min(3.8, 0.36 * (len(page.rows) + 2)))
    elif page.bullets:
        _add_text(slide, 0.55, body_top, 12.2, 3.6, "\n".join(f"•  {b}" for b in page.bullets[:8]), size=15, color=_SLATE)
    if page.source:
        _add_text(slide, 0.5, 6.65, 12.3, 0.38, page.source, size=10, color=_MUTED)


def _render_divider(slide, page: Page) -> None:
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.18), _SLIDE_H)
    _fill(band, _ORANGE)
    _add_text(slide, 0.7, 1.3, 3, 0.8, page.chapter, size=54, bold=True, color=_TEAL)
    _add_text(slide, 0.7, 2.3, 11.5, 1.1, page.title, size=32, bold=True, color=_NAVY)
    _add_text(slide, 0.7, 3.5, 10, 0.6, page.subtitle, size=16, color=_SLATE)
    _add_text(slide, 0.7, 4.4, 8, 2.2, "\n".join(page.bullets[:8]), size=14, color=_SLATE)


def _render_cover(slide, page: Page) -> None:
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.22), _SLIDE_H)
    _fill(band, _TEAL)
    _add_text(slide, 0.7, 1.5, 10, 0.4, "DiligenceIQ", size=18, bold=True, color=_TEAL)
    _add_text(slide, 0.7, 2.05, 11, 0.35, "Commercial due diligence", size=16, color=_MUTED)
    _add_text(slide, 0.7, 2.7, 11.5, 1.4, page.title, size=32, bold=True, color=_NAVY)
    _add_text(slide, 0.7, 4.4, 10, 0.4, page.subtitle, size=16, color=_SLATE)
    _add_text(slide, 0.7, 6.3, 8, 0.3, page.note or "", size=13, color=_MUTED)
    _add_text(slide, 0.7, 6.7, 6, 0.3, page.source, size=13, color=_NAVY)


def _render_close(slide, page: Page) -> None:
    _add_text(slide, 0.7, 2.4, 11, 0.4, "DiligenceIQ", size=18, bold=True, color=_TEAL)
    _add_text(slide, 0.7, 3.0, 11.5, 1.2, page.title, size=26, bold=True, color=_NAVY)
    _add_text(slide, 0.7, 4.4, 11, 0.8, page.subtitle, size=14, color=_SLATE)
    _add_text(slide, 0.7, 6.4, 6, 0.3, page.source, size=13, color=_MUTED)


def render_cdd_deck(ctx: BuildContext) -> tuple[Presentation, DeckPlan]:
    plan = plan_cdd_deck(ctx)
    prs = Presentation()
    prs.slide_width = Emu(_SLIDE_W)
    prs.slide_height = Emu(_SLIDE_H)
    blank = prs.slide_layouts[6]
    total = len(plan.pages)
    for index, page in enumerate(plan.pages, start=1):
        slide = prs.slides.add_slide(blank)
        if page.kind == "cover":
            _render_cover(slide, page)
        elif page.kind == "close":
            _render_close(slide, page)
        elif page.kind == "divider":
            _render_divider(slide, page)
        else:
            _render_content(slide, page)
            _chrome(slide, page, index, total)
        if page.note:
            slide.notes_slide.notes_text_frame.text = page.note
    return prs, plan
