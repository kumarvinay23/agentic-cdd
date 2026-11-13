"""FDD chapter storyline planners (Phases C–E) — expected TOC 01–09.

Phase C: chapter shells + held policy + TOC page numbers.
Phase D: exhibit-backed tables, QoE bridge/ADJ, ES KPIs, NWC peg rule,
debt-like dividends, deal protections/R##, claims inconsistencies appendix.
Phase E: PPTX display scale ($k), LTM/YTD columns, basis labels, evidence tiers.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    CommentaryDoc,
    ExhibitStoreDoc,
    FindingRankRow,
    KpiTile,
    PptxChrome,
    SlideSpec,
    SlideTable,
    TocEntry,
)
from agetic_cdd_api.services_fdd_tokens import format_pptx_money, resolve_text_pptx

DEFAULT_CHAPTER_ORDER: tuple[tuple[str, str, str, str], ...] = (
    ("01", "intro", "INTRODUCTION", "Introduction"),
    ("02", "es", "EXECUTIVE SUMMARY", "Executive summary"),
    ("03", "transaction", "TRANSACTION AND BUSINESS", "Transaction and business"),
    ("04", "qoe", "QUALITY OF EARNINGS", "Quality of earnings"),
    ("05", "trading", "TRADING", "Trading"),
    ("06", "cash", "CASH FLOW", "Cash flow"),
    ("07", "bs", "BALANCE SHEET, DEBT AND LEASES", "Balance sheet, debt and leases"),
    ("08", "deal", "DEAL CONSIDERATIONS", "Deal considerations"),
    ("09", "appendix", "APPENDICES", "Appendices"),
)

_CHAPTER_SEC_SOURCES: dict[str, tuple[str, ...]] = {
    "intro": ("SEC-A",),
    "es": ("SEC-ES", "SEC-K"),
    "transaction": (),
    "qoe": ("SEC-E",),
    "trading": ("SEC-B", "SEC-C", "SEC-D"),
    "cash": ("SEC-I",),
    "bs": ("SEC-F", "SEC-G", "SEC-H"),
    "deal": (),
    "appendix": (),
}

_SOURCE_DEFAULT = "Approved databook exhibits; Diligence analysis"
_BASIS_DEFAULT = "Unaudited monthly management accounts"


@dataclass
class DisplayCtx:
    """Phase E display policy for chapter slides (store units stay unchanged)."""

    display_scale: str = "k"  # k | M — PPTX presentation scale
    store_scale: str = "M"
    currency: str = "USD"
    basis_default: str = _BASIS_DEFAULT
    include_ytd: bool = True
    include_ltm: bool = True


_DISPLAY_CTX: ContextVar[DisplayCtx | None] = ContextVar("fdd_chapter_display_ctx", default=None)


def _ctx() -> DisplayCtx:
    return _DISPLAY_CTX.get() or DisplayCtx()


def resolve_pptx_display_scale(scope: Any | None = None) -> str:
    """FDD Report PPTX defaults to $k even when store/scope scale is M."""
    raw = None
    if scope is not None:
        raw = getattr(scope, "report_display_scale", None)
    scale = str(raw or "k").strip() or "k"
    if scale.lower() in {"k", "$k", "000", "thousands"}:
        return "k"
    if scale.lower() in {"m", "$m", "mm", "millions"}:
        return "M"
    return scale


def resolve_basis_default(scope: Any | None = None, *, chrome: PptxChrome | None = None) -> str:
    if scope is not None and getattr(scope, "basis_of_preparation", None):
        return str(scope.basis_of_preparation).strip()
    if chrome is not None and chrome.basis_short:
        # Prefer a preparation-style basis over the short chrome subtitle alone.
        if "unaudited" in chrome.basis_short.lower() or "management" in chrome.basis_short.lower():
            return chrome.basis_short
    return _BASIS_DEFAULT


def resolve_project_label(*, company: str | None = None, scope: Any | None = None) -> str:
    """Chrome project label from the deal entity — never a fixed deal nickname."""
    entity = None
    if scope is not None and getattr(scope, "entities_in", None):
        ents = [str(e).strip() for e in list(scope.entities_in) if str(e).strip()]
        if ents:
            entity = ents[0]
    if not entity and company and str(company).strip():
        entity = str(company).strip()
    if not entity:
        return "FDD"
    # "Compost Crew Inc." → "Project Compost Crew"
    stem = re.split(r"\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|PLC)\b", entity, maxsplit=1)[0]
    stem = re.sub(r"[,.\s]+$", "", stem).strip() or entity
    if stem.lower().startswith("project "):
        return stem
    return f"Project {stem}"


def default_chrome(*, company: str | None = None, scope: Any | None = None) -> PptxChrome:
    basis = resolve_basis_default(scope)
    return PptxChrome(
        project_label=resolve_project_label(company=company, scope=scope),
        basis_short=basis if "draft" in basis.lower() else f"Draft for discussion - {basis}",
        display_scale=resolve_pptx_display_scale(scope),
        currency=(getattr(scope, "currency", None) if scope is not None else None) or "USD",
    )


def scale_suffix(display_scale: str | None = None) -> str:
    ds = (display_scale or _ctx().display_scale or "k").lower()
    return "($k)" if ds == "k" else "($m)" if ds == "m" else f"({ds})"


# ---------------------------------------------------------------------------
# Exhibit / figure helpers
# ---------------------------------------------------------------------------


def _draft_by_id(commentary: CommentaryDoc | None) -> dict[str, Any]:
    if commentary is None:
        return {}
    return {s.section_id: s for s in commentary.sections}


_FILLER_OBS_RE = re.compile(
    r"(?i)^("
    r"historical trading|"
    r"revenue and margin:|"
    r"costs and people:|"
    r"cash conversion:|"
    r"balance sheet:|"
    r"nwc:|"
    r"fy20\d{2}\s+revenue\s+\$"
    r")"
)


def _is_filler_obs(line: str) -> bool:
    t = str(line or "").strip()
    if not t:
        return True
    if _FILLER_OBS_RE.match(t):
        return True
    # Template leftovers like "FY2025 gross margin 30.44 (%)".
    if re.search(r"\d+\.\d+\s*\(%\)", t):
        return True
    return False


def _clean_draft_obs(lines: list[str] | None) -> list[str]:
    out: list[str] = []
    for line in lines or []:
        t = str(line or "").strip()
        if _is_filler_obs(t):
            continue
        if t not in out:
            out.append(t)
    return out


def _humanize_request_title(raw: Any) -> str:
    """Turn claim-scaffold request titles into reader-facing asks."""
    title = str(raw or "").strip()
    if not title:
        return "Information request"
    low = title.lower()
    if low.startswith("resolve claim"):
        title = re.sub(r"(?i)^resolve claim\s+", "Reconcile ", title)
        title = re.sub(r"\s*\((?:contradicted|unverifiable|pass)\)\s*$", "", title)
        title = title.replace("_", " ")
        title = re.sub(r"\s+", " ", title).strip()
        # "Reconcile ebitda FY2026" / "Reconcile ebitda margin FY2027".
        m = re.match(r"(?i)^reconcile\s+(.+?)\s+fy(\d{4})$", title)
        if m:
            metric = m.group(1).strip()
            metric = re.sub(
                r"(?i)\b(ebitda|sg&a|nwc|cim|ltm|ytd)\b",
                lambda mm: mm.group(1).upper(),
                metric,
            )
            title = f"Support {metric} outlook for FY{m.group(2)}"
    return title[:90]


def _obs_from_drafts(
    commentary: CommentaryDoc | None,
    section_ids: tuple[str, ...],
    *,
    limit: int = 6,
) -> list[str]:
    by_id = _draft_by_id(commentary)
    lines: list[str] = []
    held = False
    for sid in section_ids:
        draft = by_id.get(sid)
        if draft is None:
            continue
        if getattr(draft, "held_back", False):
            held = True
        title = (getattr(draft, "action_title", None) or getattr(draft, "title", "") or "").strip()
        body = (getattr(draft, "body", None) or "").strip()
        if title and title not in lines and not _is_filler_obs(title):
            lines.append(title)
        for raw in body.splitlines():
            t = raw.strip().lstrip("•-* ").strip()
            if not t or t.startswith("[") or _is_filler_obs(t):
                continue
            if t not in lines:
                lines.append(t)
            if len(lines) >= limit:
                break
        if len(lines) >= limit:
            break
    if held and not any("held" in x.lower() for x in lines):
        lines.append("Section held back pending schedules or scope confirmation.")
    return _clean_draft_obs(lines)[:limit]


def _any_held(commentary: CommentaryDoc | None, section_ids: tuple[str, ...]) -> bool:
    by_id = _draft_by_id(commentary)
    return any(
        getattr(by_id.get(sid), "held_back", False) for sid in section_ids if by_id.get(sid)
    )


def _exhibit_by_id(store: ExhibitStoreDoc, exhibit_id: str) -> Any | None:
    for ex in store.exhibits or []:
        if ex.exhibit_id == exhibit_id:
            return ex
    return None


# Preferred closed-year pack for advisory tables (matches Project_Crew expected).
_PREFERRED_FY_YEARS: tuple[int, ...] = (2023, 2024, 2025)
_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _cell_period_token(cell: Any) -> str | None:
    """Best available period stamp from cell attrs / eight-labels / metric suffix."""
    for attr in ("period_label", "period", "period_id", "as_of_label"):
        raw = getattr(cell, attr, None)
        if raw:
            return str(raw).strip()
    labels = getattr(cell, "labels", None)
    if labels is not None:
        plen = getattr(labels, "period_length", None)
        if plen:
            return str(plen).strip()
    label = str(getattr(cell, "label", "") or "")
    if label:
        return label
    mk = str(getattr(cell, "metric_key", None) or "")
    if mk.endswith("_ytd") or mk.endswith("_ltm"):
        return mk.rsplit("_", 1)[-1].upper()
    return None


def _is_ytd_token(token: str | None) -> bool:
    if not token:
        return False
    t = token.upper().replace(" ", "")
    return "YTD" in t


def _is_ltm_token(token: str | None) -> bool:
    if not token:
        return False
    t = token.upper().replace(" ", "")
    return "LTM" in t or "TTM" in t or "LASTTWELVEMONTHS" in t


def _is_ytd_cell(cell: Any) -> bool:
    if _is_ytd_token(_cell_period_token(cell)):
        return True
    labels = getattr(cell, "labels", None)
    if labels is not None and _is_ytd_token(str(getattr(labels, "period_length", "") or "")):
        return True
    mk = str(getattr(cell, "metric_key", None) or "")
    return mk.endswith("_ytd")


def _is_ltm_cell(cell: Any) -> bool:
    if _is_ltm_token(_cell_period_token(cell)):
        return True
    labels = getattr(cell, "labels", None)
    if labels is not None and _is_ltm_token(str(getattr(labels, "period_length", "") or "")):
        return True
    mk = str(getattr(cell, "metric_key", None) or "")
    return mk.endswith("_ltm")


def _is_plan_cell(cell: Any) -> bool:
    if _is_ytd_cell(cell) or _is_ltm_cell(cell):
        return False
    label = str(getattr(cell, "label", "") or "")
    if re.search(r"\bplan\b", label, flags=re.I):
        return True
    if re.search(r"FY\d{2,4}E\b", label, flags=re.I):
        return True
    return False


def _is_closed_fy_cell(cell: Any) -> bool:
    if cell is None or getattr(cell, "fiscal_year", None) is None:
        return False
    if _is_ytd_cell(cell) or _is_ltm_cell(cell) or _is_plan_cell(cell):
        return False
    return True


def _period_column_header(cell: Any | None, *, kind: str) -> str:
    """Build ``YTD Jul-26`` / ``LTM Jul-26`` headers from period_end when present."""
    base = "YTD" if kind == "ytd" else "LTM"
    if cell is None:
        return base
    labels = getattr(cell, "labels", None)
    pend = str(getattr(labels, "period_end", None) or "") if labels is not None else ""
    if len(pend) >= 7 and pend[5:7].isdigit():
        month = max(1, min(12, int(pend[5:7])))
        yy = int(pend[:4]) % 100
        return f"{base} {_MONTH_ABBR[month - 1]}-{yy:02d}"
    label = str(getattr(cell, "label", "") or "")
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*[–\-]\s*"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
        label,
        flags=re.I,
    )
    if m:
        return f"{base} {m.group(2).title()}-{int(m.group(3)) % 100:02d}"
    m2 = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^\d]*(\d{2,4})",
        label,
        flags=re.I,
    )
    if m2:
        yy = int(m2.group(2))
        if yy > 100:
            yy %= 100
        return f"{base} {m2.group(1).title()}-{yy:02d}"
    return base


def _cell_map(store: ExhibitStoreDoc, exhibit_id: str) -> dict[tuple[str, int | None], Any]:
    """Index closed-FY cells by (metric_key, fiscal_year).

    YTD / LTM / plan cells are omitted — use ``_cells_for_metric`` + ``_pick_period_cell``.
    """
    ex = _exhibit_by_id(store, exhibit_id)
    out: dict[tuple[str, int | None], Any] = {}
    if ex is None:
        return out
    for cell in ex.cells or []:
        if _is_ytd_cell(cell) or _is_ltm_cell(cell) or _is_plan_cell(cell):
            continue
        mk = str(getattr(cell, "metric_key", None) or cell.cell_id)
        fy = getattr(cell, "fiscal_year", None)
        out[(mk, fy)] = cell
    return out


def _cells_for_metric(store: ExhibitStoreDoc, exhibit_id: str, metric_key: str) -> list[Any]:
    ex = _exhibit_by_id(store, exhibit_id)
    if ex is None:
        return []
    return [
        cell
        for cell in (ex.cells or [])
        if str(getattr(cell, "metric_key", None) or cell.cell_id) == metric_key
    ]


def _cells_for_metric_multi(
    store: ExhibitStoreDoc,
    exhibit_ids: tuple[str, ...] | list[str],
    metric_key: str,
) -> list[Any]:
    out: list[Any] = []
    for eid in exhibit_ids:
        out.extend(_cells_for_metric(store, eid, metric_key))
    return out


def _normalize_exhibit_ids(exhibit_id: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(exhibit_id, str):
        return (exhibit_id,)
    return tuple(str(x) for x in exhibit_id)


def _fmt_num(
    val: Any,
    *,
    pct: bool = False,
    money: bool = False,
    prose: bool = False,
    ctx: DisplayCtx | None = None,
) -> str:
    """Format a figure for chapter slides.

    ``money=True, prose=False`` → table cell under ($k), e.g. ``13,282``.
    ``money=True, prose=True`` → KPI/headline, e.g. ``$13.28m`` / ``$572k``.
    """
    if val is None:
        return "—"
    try:
        num = float(val)
    except (TypeError, ValueError):
        return str(val)
    if pct:
        # Values may already be in percent points (4.25) or fractions (0.042).
        if abs(num) <= 1.5:
            num *= 100.0
        return f"{num:,.1f}%"
    if money:
        c = ctx or _ctx()
        return format_pptx_money(
            num,
            store_scale=c.store_scale or "M",
            display_scale=c.display_scale or "k",
            prose=prose,
        )
    if abs(num) >= 100:
        return f"{num:,.1f}"
    return f"{num:,.2f}"


def _pick_period_cell(
    cmap: dict[tuple[str, int | None], Any],
    metric_key: str,
    *,
    year: int | None = None,
    ytd: bool = False,
    ltm: bool = False,
    all_cells: list[Any] | None = None,
) -> Any | None:
    """Pick a cell for closed FY year and/or YTD/LTM period labels.

    Databook YTD often arrives as ``fiscal_year=2026`` + ``labels.period_length=YTD``
    (not fiscal_year=None) — always classify via period labels, not year alone.
    """
    candidates = list(all_cells) if all_cells is not None else [
        cell for (mk, _fy), cell in cmap.items() if mk == metric_key
    ]
    if ytd or ltm:
        for cell in candidates:
            if ytd and _is_ytd_cell(cell):
                return cell
            if ltm and _is_ltm_cell(cell):
                return cell
        suffix = "_ytd" if ytd else "_ltm"
        for cell in candidates:
            mk = str(getattr(cell, "metric_key", None) or "")
            if mk == f"{metric_key}{suffix}":
                return cell
        return cmap.get((f"{metric_key}{suffix}", None))
    if not candidates and year is not None:
        return cmap.get((metric_key, year))
    if year is not None:
        hit = cmap.get((metric_key, year))
        if hit is not None and _is_closed_fy_cell(hit):
            return hit
        for cell in candidates:
            if getattr(cell, "fiscal_year", None) == year and _is_closed_fy_cell(cell):
                return cell
        return None
    for cell in candidates:
        if _is_closed_fy_cell(cell):
            return cell
    return None


def _discover_fy_years(
    store: ExhibitStoreDoc,
    exhibit_ids: tuple[str, ...],
    metrics: list[tuple[str, str, str]],
    *,
    preferred: tuple[int, ...] = _PREFERRED_FY_YEARS,
) -> tuple[int, ...]:
    """Closed FY years present for the metrics — prefer FY23–FY25 when available."""
    found: set[int] = set()
    for mk, _lab, _kind in metrics:
        for cell in _cells_for_metric_multi(store, exhibit_ids, mk):
            if _is_closed_fy_cell(cell):
                found.add(int(cell.fiscal_year))
    preferred_hit = tuple(y for y in preferred if y in found)
    if preferred_hit:
        return preferred_hit
    # Fall back to all closed years at/before current calendar year.
    closed_cap = date.today().year
    return tuple(sorted(y for y in found if y <= closed_cap))


def _discover_ytd_ltm_cells(
    store: ExhibitStoreDoc,
    exhibit_ids: tuple[str, ...],
    metrics: list[tuple[str, str, str]],
) -> tuple[Any | None, Any | None]:
    """Return sample YTD and LTM cells (for headers) if any metric has them."""
    ytd_cell = None
    ltm_cell = None
    for mk, _lab, _kind in metrics:
        cells = _cells_for_metric_multi(store, exhibit_ids, mk)
        if ytd_cell is None:
            ytd_cell = _pick_period_cell({}, mk, ytd=True, all_cells=cells)
        if ltm_cell is None:
            ltm_cell = _pick_period_cell({}, mk, ltm=True, all_cells=cells)
        if ytd_cell is not None and ltm_cell is not None:
            break
    return ytd_cell, ltm_cell


def _metric(
    store: ExhibitStoreDoc,
    exhibit_ids: tuple[str, ...] | str,
    metric_key: str,
    year: int | None = 2025,
) -> Any | None:
    ids = (exhibit_ids,) if isinstance(exhibit_ids, str) else exhibit_ids
    for eid in ids:
        cmap = _cell_map(store, eid)
        cell = _pick_period_cell(cmap, metric_key, year=year)
        if cell is not None:
            return cell.value
    return None


def _metric_cell(
    store: ExhibitStoreDoc,
    exhibit_ids: tuple[str, ...] | str,
    metric_key: str,
    year: int | None = 2025,
) -> Any | None:
    ids = (exhibit_ids,) if isinstance(exhibit_ids, str) else exhibit_ids
    for eid in ids:
        cmap = _cell_map(store, eid)
        cell = _pick_period_cell(cmap, metric_key, year=year)
        if cell is not None:
            return cell
    return None


def _evidence_tier_from_cell(cell: Any | None) -> str | None:
    if cell is None:
        return None
    for attr in ("evidence_tier", "tier", "confidence_tier", "source_tier"):
        raw = getattr(cell, attr, None)
        if raw is None:
            continue
        # Enum / str — take the value letter.
        val = getattr(raw, "value", raw)
        t = str(val).strip().upper()
        if t in {"A", "B", "C"}:
            return t
        if t.endswith(".A") or t.endswith("_A") or "TIER_A" in t:
            return "A"
        if t.endswith(".B") or t.endswith("_B") or "TIER_B" in t:
            return "B"
        if t.endswith(".C") or t.endswith("_C") or "TIER_C" in t:
            return "C"
    return None


def _basis_from_cell(cell: Any | None, *, fallback: str | None = None) -> str | None:
    if cell is not None:
        for attr in ("basis_label", "basis", "basis_of_preparation", "source_basis"):
            raw = getattr(cell, attr, None)
            if raw:
                return str(raw).strip()
        labels = getattr(cell, "labels", None)
        if labels is not None and getattr(labels, "basis", None):
            return str(labels.basis).strip()
    return fallback or _ctx().basis_default


def _format_source_ref(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        for key in ("doc_id", "register_id", "source_id", "id", "label", "path"):
            if raw.get(key):
                return str(raw[key]).strip()
        # Compact fallback for small dicts.
        bits = [f"{k}={v}" for k, v in list(raw.items())[:3] if v is not None]
        return "; ".join(bits) if bits else None
    s = str(raw).strip()
    return s or None


def _source_from_cells(cells: list[Any], *, exhibit_id: str | None = None) -> str:
    cites: list[str] = []
    for cell in cells:
        hit = False
        for attr in ("source_ref", "source", "citation", "source_id"):
            raw = getattr(cell, attr, None)
            formatted = _format_source_ref(raw)
            if formatted and formatted not in cites:
                cites.append(formatted)
                hit = True
                break
        labels = getattr(cell, "labels", None)
        if labels is not None and getattr(labels, "source", None):
            s = str(labels.source).strip()
            if s and s not in cites:
                cites.append(s)
                hit = True
        if hit:
            continue
    if cites:
        return "; ".join(cites[:4])
    if exhibit_id:
        return f"Exhibit {exhibit_id}"
    return _SOURCE_DEFAULT


def _period_table(
    store: ExhibitStoreDoc,
    *,
    exhibit_id: str | tuple[str, ...] | list[str],
    metrics: list[tuple[str, str, str]],
    years: tuple[int, ...] | None = None,
    title: str,
    basis: str | None = None,
    include_ytd: bool | None = None,
    include_ltm: bool | None = None,
) -> SlideTable | None:
    """metrics: list of (metric_key, label, kind) where kind in money|pct|num.

    Auto-discovers closed FY years (prefer FY23–FY25) and appends YTD/LTM columns
    when those periods exist on any of the listed exhibits. Money values convert
    store→display scale; basis/Source/Evidence come from used cells.
    """
    exhibit_ids = _normalize_exhibit_ids(exhibit_id)
    primary_id = exhibit_ids[0]
    # Merge cells across exhibits so YTD on ex_db_* fills model-exhibit tables.
    metric_cells: dict[str, list[Any]] = {
        mk: _cells_for_metric_multi(store, exhibit_ids, mk) for mk, _lab, _kind in metrics
    }
    if not any(metric_cells.values()):
        return None

    # Combined FY map (primary first wins via reverse update order).
    cmap: dict[tuple[str, int | None], Any] = {}
    for eid in reversed(exhibit_ids):
        cmap.update(_cell_map(store, eid))

    resolved_years = (
        years
        if years is not None
        else _discover_fy_years(store, exhibit_ids, metrics)
    )
    if not resolved_years:
        resolved_years = ()

    ctx = _ctx()
    want_ytd = ctx.include_ytd if include_ytd is None else include_ytd
    want_ltm = ctx.include_ltm if include_ltm is None else include_ltm
    ytd_sample, ltm_sample = (None, None)
    if want_ytd or want_ltm:
        ytd_sample, ltm_sample = _discover_ytd_ltm_cells(store, exhibit_ids, metrics)
    has_ytd = bool(want_ytd and ytd_sample is not None)
    has_ltm = bool(want_ltm and ltm_sample is not None)
    if not resolved_years and not has_ytd and not has_ltm:
        return None

    headers = ["Metric", *[f"FY{y % 100:02d}" for y in resolved_years]]
    if has_ytd:
        headers.append(_period_column_header(ytd_sample, kind="ytd"))
    if has_ltm:
        headers.append(_period_column_header(ltm_sample, kind="ltm"))

    def _fmt_kind(val: Any, kind: str) -> str:
        if kind == "pct":
            return _fmt_num(val, pct=True, ctx=ctx)
        if kind == "money":
            return _fmt_num(val, money=True, ctx=ctx)
        return _fmt_num(val, ctx=ctx)

    rows: list[list[str]] = []
    used_cells: list[Any] = []
    tiers: list[str] = []
    for metric_key, label, kind in metrics:
        cells = metric_cells.get(metric_key) or []
        row = [label]
        any_val = False
        for y in resolved_years:
            cell = _pick_period_cell(cmap, metric_key, year=y, all_cells=cells)
            val = cell.value if cell is not None else None
            if cell is not None:
                used_cells.append(cell)
                tier = _evidence_tier_from_cell(cell)
                if tier:
                    tiers.append(tier)
            if val is not None:
                any_val = True
            row.append(_fmt_kind(val, kind))
        if has_ytd:
            cell = _pick_period_cell(cmap, metric_key, ytd=True, all_cells=cells)
            val = cell.value if cell is not None else None
            if cell is not None:
                used_cells.append(cell)
                tier = _evidence_tier_from_cell(cell)
                if tier:
                    tiers.append(tier)
            if val is not None:
                any_val = True
            row.append(_fmt_kind(val, kind))
        if has_ltm:
            cell = _pick_period_cell(cmap, metric_key, ltm=True, all_cells=cells)
            val = cell.value if cell is not None else None
            if cell is not None:
                used_cells.append(cell)
                tier = _evidence_tier_from_cell(cell)
                if tier:
                    tiers.append(tier)
            if val is not None:
                any_val = True
            row.append(_fmt_kind(val, kind))
        if any_val:
            rows.append(row)
    if not rows:
        return None

    moneyish = any(k == "money" for _mk, _lab, k in metrics)
    final_title = title
    if (
        moneyish
        and scale_suffix() not in title.lower()
        and "($k)" not in title
        and "($m)" not in title.lower()
    ):
        final_title = f"{title} {scale_suffix()}"

    table_basis = basis or _basis_from_cell(used_cells[0] if used_cells else None)
    source = _source_from_cells(used_cells, exhibit_id=primary_id)
    evidence = None
    if tiers:
        rank = {"A": 1, "B": 2, "C": 3}
        evidence = max(tiers, key=lambda t: rank.get(t, 0))

    return SlideTable(
        title=final_title,
        headers=headers,
        rows=rows,
        basis=table_basis or "",
        source=source,
        evidence_tier=evidence,
    )



def _held_obs(*, chapter_title: str, requests: list[str] | None = None) -> list[str]:
    lines = [
        f"{chapter_title} is held — evidence incomplete for this run.",
        "Do not price from this chapter until schedules are provided or the section is scoped out.",
    ]
    for req in (requests or [])[:3]:
        lines.append(
            req
            if req.lower().startswith(("r", "open", "ask"))
            else f"Open request: {req}"
        )
    if not requests:
        lines.append("Open request: Supply the missing schedules or confirm out of scope.")
    return lines


def _public_request_id(raw: Any, *, index: int) -> str:
    """Prefer R01-style labels; hide internal req_/uuid tokens from slides."""
    text = str(raw or "").strip()
    if not text:
        return f"R{index:02d}"
    low = text.lower()
    if low.startswith("req_") or low.startswith("fnd_") or len(text) >= 20:
        return f"R{index:02d}"
    if re.fullmatch(r"[0-9a-f-]{12,}", low):
        return f"R{index:02d}"
    return text


def _request_hints(
    *,
    request_list: Any | None,
    findings: Any | None,
    claims: Any | None = None,
    limit: int = 8,
) -> list[str]:
    hints: list[str] = []
    for i, item in enumerate(list(getattr(request_list, "items", None) or [])[:limit], start=1):
        title = _humanize_request_title(
            getattr(item, "title", None) or getattr(item, "detail", None) or "Information request"
        )
        rid = _public_request_id(getattr(item, "request_id", None), index=i)
        hints.append(f"{rid}: {title}")
    if hints:
        return hints[:limit]
    for f in list(getattr(findings, "findings", None) or []):
        ask = getattr(f, "ask_management", None)
        if ask:
            hints.append(str(ask))
        if len(hints) >= limit:
            break
    for c in list(getattr(claims, "claims", None) or []):
        if getattr(c, "test_result", None) != "contradicted":
            continue
        metric = getattr(c, "metric_key", None) or "figure"
        year = getattr(c, "fiscal_year", None)
        hints.append(
            f"Reconcile {metric}"
            + (f" FY{year}" if year else "")
            + " (claim contradicted vs databook)"
        )
        if len(hints) >= limit:
            break
    return hints[:limit]


def _findings_list(findings: Any | None) -> list[Any]:
    return list(getattr(findings, "findings", None) or [])


def _high_mod_findings(findings: Any | None) -> list[Any]:
    out = []
    for f in _findings_list(findings):
        sev = getattr(getattr(f, "severity", None), "value", "") or ""
        if sev in {"high", "moderate"}:
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Chapter planners (Phase D depth)
# ---------------------------------------------------------------------------


def plan_cover(
    *,
    company: str,
    chrome: PptxChrome,
    scope: Any | None,
    qoe: Any | None = None,
) -> SlideSpec:
    entity = company
    if scope is not None and getattr(scope, "entities_in", None):
        ents = list(scope.entities_in)
        if ents:
            entity = ", ".join(str(e) for e in ents[:3])
    basis = chrome.basis_short
    mat = _fmt_materiality(resolve_materiality_m(scope=scope, qoe=qoe))
    if mat:
        basis = f"{basis}. Materiality {mat}".strip()
    deal = getattr(scope, "deal_type", None) if scope is not None else None
    entity_line = entity if not deal else f"{entity} — {deal}"
    return SlideSpec(
        slide_id="ch_cover",
        layout="cover",
        chapter="cover",
        deal_name=chrome.project_label,
        engagement="Financial due diligence",
        entity_line=entity_line,
        basis_line=basis,
        date_line="",
    )


def plan_toc_placeholder() -> SlideSpec:
    return SlideSpec(
        slide_id="ch_toc",
        layout="toc",
        chapter="contents",
        banner="CONTENTS",
        headline="Contents",
        toc_entries=[],
    )


def _fmt_materiality(raw: Any) -> str | None:
    """Render materiality as a money figure (never bare 0.03)."""
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        text = str(raw).strip()
        return text or None
    # Convention: values < 1 are millions (0.03 → $30k); ≥1 already money units.
    if abs(val) < 1.0:
        return _fmt_num(val, money=True, prose=True)
    return _fmt_num(val, money=True, prose=True)


def resolve_materiality_m(*, scope: Any | None = None, qoe: Any | None = None) -> Any | None:
    """Prefer QoE-computed M (pct × adj. EBITDA band) over a draft scope placeholder."""
    qoe_m = getattr(qoe, "materiality_m", None) if qoe is not None else None
    scope_m = getattr(scope, "materiality_m", None) if scope is not None else None
    if qoe_m is not None:
        return qoe_m
    if scope_m is not None:
        return scope_m
    # Last resort: pct × diligence EBITDA when both are present.
    pct = getattr(scope, "materiality_pct", None) if scope is not None else None
    dil = getattr(qoe, "adjusted_ebitda_diligence", None) if qoe is not None else None
    if pct is not None and dil is not None:
        try:
            return float(pct) * float(dil)
        except (TypeError, ValueError):
            return None
    return None


def plan_intro(
    *,
    commentary: CommentaryDoc | None,
    scope: Any | None,
    company: str,
    requests: list[str],
    qoe: Any | None = None,
) -> list[SlideSpec]:
    secs = _CHAPTER_SEC_SOURCES["intro"]
    obs = _obs_from_drafts(commentary, secs)
    mat = _fmt_materiality(resolve_materiality_m(scope=scope, qoe=qoe))
    mat_pct = getattr(scope, "materiality_pct", None) if scope is not None else None
    if mat_pct is None:
        try:
            from agetic_cdd_api.fdd_schemas import DEFAULT_MATERIALITY_PCT

            mat_pct = DEFAULT_MATERIALITY_PCT
        except Exception:
            mat_pct = 0.05
    mat_basis = (
        f"{float(mat_pct) * 100:.0f}% of adj. EBITDA band"
        if mat_pct is not None
        else "Adj. EBITDA basis"
    )
    periods = ""
    if scope is not None and getattr(scope, "periods", None):
        periods = ", ".join(str(p) for p in list(scope.periods)[:10])
    currency = getattr(scope, "currency", None) or getattr(qoe, "currency", None) or "USD"
    deal_type = getattr(scope, "deal_type", None) or "—"
    period_label = periods or "FY23–FY25, YTD Jul-26, LTM Jul-26"
    # Project Crew-style period / source / basis / tier register.
    rows = [
        [period_label, "Management accounts / CIM", "Unaudited management", "B"],
        ["QoE bridge (FY25)", "QoE workbook / Diligence", "Adjusted EBITDA", "B"],
        ["Balance sheet / net debt", "Databook BS / SoCF", "Management BS", "B"],
        ["Cash / USDA / leases", "CIM + FPEP + lease files", "Contract / grant", "A/B"],
        ["Materiality", mat or "Per scope / QoE", mat_basis, "B"],
        ["Entity / perimeter", company, str(deal_type), "—"],
        ["Currency / scale", f"{currency}", "Exhibit scale as labelled", "—"],
    ]
    if not obs:
        obs = [
            "Scope locked from the engagement profile; every historical figure is unaudited unless noted.",
            "Evidence tiers: A = contract/grant; B = management accounts / approved exhibits; C = management representation.",
            "Limitations: no audited figures assumed; lease / tax / peg items may remain open.",
            "Reader: buy-side / growth investor diligence pack." if deal_type == "buy-side" else "Reader: diligence pack for the stated deal type.",
        ]
    if requests:
        obs = list(obs[:4]) + [f"Open: {requests[0]}"]
    headline = (
        f"Scope and basis: unaudited management accounts"
        + (f"; materiality {mat} ({mat_basis})" if mat else "")
    )
    return [
        SlideSpec(
            slide_id="ch_intro_1",
            layout="section_table_obs",
            chapter="intro",
            banner="INTRODUCTION",
            headline=headline[:180],
            table=SlideTable(
                title="Periods, sources and evidence tiers",
                headers=["Period", "Source", "Basis", "Tier"],
                rows=rows,
            ),
            observations=obs[:6],
            source="Scope profile; Diligence analysis",
            evidence_tier="B",
            footnotes=[
                "Limitations: figures remain subject to evidence tiers A/B/C and open information requests.",
            ],
        )
    ]


def _metric_period(
    store: ExhibitStoreDoc,
    exhibit_ids: tuple[str, ...] | str,
    metric_key: str,
    *,
    year: int | None = None,
    ytd: bool = False,
    ltm: bool = False,
) -> Any | None:
    """Closed-FY / YTD / LTM metric value across one or more exhibits."""
    ids = (exhibit_ids,) if isinstance(exhibit_ids, str) else exhibit_ids
    for eid in ids:
        cells = _cells_for_metric(store, eid, metric_key)
        cell = _pick_period_cell(
            {}, metric_key, year=year, ytd=ytd, ltm=ltm, all_cells=cells
        )
        if cell is not None and getattr(cell, "value", None) is not None:
            return cell.value
    return None


def _es_rating(sev: str) -> str:
    s = (sev or "").strip().lower()
    if s == "moderate":
        return "Medium"
    if not s:
        return ""
    return s.title()


def _es_quantified(f: Any) -> str:
    for attr in ("implication", "observation"):
        raw = getattr(f, attr, None)
        if raw:
            text = " ".join(str(raw).split())
            return text[:72]
    return "Size / effect pending"


def _es_protection(f: Any) -> str:
    ask = getattr(f, "ask_management", None)
    if ask:
        return " ".join(str(ask).split())[:70]
    return "Confirm with management / counsel"


def _es_tier(f: Any) -> str:
    refs = list(getattr(f, "evidence_refs", None) or [])
    for ref in refs:
        t = str(ref).strip().upper()
        if t in {"A", "B", "C"}:
            return t
        if "TIER A" in t or t.endswith(".A"):
            return "A"
        if "TIER B" in t or t.endswith(".B"):
            return "B"
        if "TIER C" in t or t.endswith(".C"):
            return "C"
    src = getattr(getattr(f, "source", None), "value", None) or getattr(f, "source", None)
    if str(src) in {"model", "qoe"}:
        return "B"
    if str(src) == "claim":
        return "B"
    return "B"


def _overlay_es_ebitda_rows(
    table: SlideTable,
    *,
    dil_ebitda: Any | None,
    mgmt_ebitda: Any | None,
    reported_fy25: Any | None = None,
) -> SlideTable:
    """Rename reported EBITDA and inject management / diligence rows for FY25."""
    if not table.rows or not table.headers:
        return table
    rows = [list(r) for r in table.rows]
    headers = list(table.headers)
    fy_cols = [i for i, h in enumerate(headers) if str(h).upper().startswith("FY")]
    fy25_col = None
    for i, h in enumerate(headers):
        if str(h).upper() in {"FY25", "FY2025"}:
            fy25_col = i
            break
    if fy25_col is None and fy_cols:
        fy25_col = fy_cols[-1]

    # Prefer a dedicated reported row label.
    ebitda_i = None
    for i, r in enumerate(rows):
        lab = str(r[0]).lower()
        if "ebitda" in lab and "margin" not in lab and "diligence" not in lab and "management" not in lab:
            ebitda_i = i
            break
    if ebitda_i is not None:
        rows[ebitda_i][0] = "Reported EBITDA"
        if fy25_col is not None and reported_fy25 is not None:
            while len(rows[ebitda_i]) <= fy25_col:
                rows[ebitda_i].append("—")
            rows[ebitda_i][fy25_col] = _fmt_num(reported_fy25, money=True)

    def _insert_after(label: str, value: Any | None) -> None:
        if value is None or fy25_col is None:
            return
        # Skip if already present.
        if any(str(r[0]).lower() == label.lower() for r in rows):
            for r in rows:
                if str(r[0]).lower() == label.lower():
                    while len(r) <= fy25_col:
                        r.append("—")
                    r[fy25_col] = _fmt_num(value, money=True)
            return
        anchor = ebitda_i if ebitda_i is not None else 0
        # Place management then diligence immediately after reported.
        insert_at = anchor + 1
        if label.lower().startswith("diligence"):
            for i, r in enumerate(rows):
                if str(r[0]).lower().startswith("management ebitda"):
                    insert_at = i + 1
                    break
        row = [label] + ["—"] * (len(headers) - 1)
        row[fy25_col] = _fmt_num(value, money=True)
        rows.insert(insert_at, row)

    _insert_after("Management EBITDA", mgmt_ebitda)
    _insert_after("Diligence EBITDA", dil_ebitda)

    # Reported margin stays labelled as reported (figures are management/reported).
    for r in rows:
        lab = str(r[0]).lower()
        if lab in {"ebitda margin", "ebitda / diligence margin", "diligence ebitda margin"}:
            r[0] = "Reported EBITDA margin"
            break

    return table.model_copy(update={"rows": rows})


def plan_es(
    *,
    commentary: CommentaryDoc | None,
    store: ExhibitStoreDoc,
    findings: Any | None,
    qoe: Any | None = None,
) -> list[SlideSpec]:
    from agetic_cdd_api.services_fdd_findings import top_findings

    secs = _CHAPTER_SEC_SOURCES["es"]
    draft_obs = _obs_from_drafts(commentary, secs, limit=4)

    es_exhibits = (
        "ex_m1_trading",
        "ex_db_metrics",
        "ex_db_is",
        "ex_m2_margin",
        "ex_m5_nwc",
        "ex_m6_net_debt",
        "ex_m7_cash",
        "ex_db_cf",
        "ex_db_bs",
        "ex_m8_bs",
        "ex_qoe_bridge",
    )
    rev25 = _metric(store, ("ex_m1_trading", "ex_db_metrics", "ex_db_is"), "revenue", 2025)
    rev24 = _metric(store, ("ex_m1_trading", "ex_db_metrics", "ex_db_is"), "revenue", 2024)
    rev_ltm = _metric_period(
        store, ("ex_m1_trading", "ex_db_metrics", "ex_db_is"), "revenue", ltm=True
    )
    rev_ytd = _metric_period(
        store, ("ex_m1_trading", "ex_db_metrics", "ex_db_is"), "revenue", ytd=True
    )
    ebitda25 = _metric(store, ("ex_m1_trading", "ex_qoe_bridge", "ex_db_is"), "ebitda", 2025)
    if ebitda25 is None:
        ebitda25 = _metric(store, "ex_qoe_bridge", "reported_ebitda", None)
    ebitda24 = _metric(store, ("ex_m1_trading", "ex_db_is"), "ebitda", 2024)
    ebitda_ltm = _metric_period(
        store, ("ex_m1_trading", "ex_db_is", "ex_db_metrics"), "ebitda", ltm=True
    )
    ebitda_ytd = _metric_period(
        store, ("ex_m1_trading", "ex_db_is", "ex_db_metrics"), "ebitda", ytd=True
    )
    ebitda_m25 = _metric(store, ("ex_m1_trading", "ex_m2_margin"), "ebitda_margin", 2025)
    ebitda_m_ltm = _metric_period(
        store, ("ex_m1_trading", "ex_m2_margin", "ex_db_is"), "ebitda_margin", ltm=True
    )
    gm25 = _metric(store, ("ex_m1_trading", "ex_m2_margin"), "gross_margin", 2025)
    net_debt = _metric(store, "ex_m6_net_debt", "net_debt", 2025)
    cash = _metric(store, ("ex_m6_net_debt", "ex_m8_bs", "ex_db_bs"), "cash", 2025)
    divs = _metric(store, ("ex_db_bs", "ex_m6_net_debt"), "dividends", 2025)
    if divs is None:
        divs = _metric(store, ("ex_db_bs", "ex_m6_net_debt"), "dividends_payable", 2025)
    # Prefer Jul-26 accrued dividends + LTM from cash/BS pack when exhibits lack LTM.
    deal_slug_es = str(getattr(store, "deal_slug", None) or "")
    _bs_pack = None
    if deal_slug_es:
        try:
            from agetic_cdd_api.services_fdd_chapter_depth import build_cash_bs_pack

            _bs_pack = build_cash_bs_pack(deal_slug_es)
            if _bs_pack.dividends_payable.get("Jul-26") is not None:
                divs = _bs_pack.dividends_payable.get("Jul-26")
            elif divs is None:
                divs = _bs_pack.dividends_payable.get(2025)
            if rev_ltm is None and _bs_pack.ltm_revenue is not None:
                rev_ltm = _bs_pack.ltm_revenue
            if ebitda_ltm is None and _bs_pack.ltm_ebitda is not None:
                ebitda_ltm = _bs_pack.ltm_ebitda
        except Exception:
            _bs_pack = None
    rev_yoy = _metric(store, "ex_m1_trading", "revenue_yoy", 2025)

    dil_ebitda = getattr(qoe, "adjusted_ebitda_diligence", None) if qoe else None
    mgmt_ebitda = getattr(qoe, "adjusted_ebitda_management", None) if qoe else None
    cim_ebitda = getattr(qoe, "cim_ebitda", None) if qoe else None
    sens_low = getattr(qoe, "sensitivity_low", None) if qoe else None
    sens_high = getattr(qoe, "sensitivity_high", None) if qoe else None
    if dil_ebitda is None:
        dil_ebitda = ebitda25
    # LTM diligence defaults to LTM reported when QoE is FY-only.
    dil_ltm = ebitda_ltm if ebitda_ltm is not None else None
    mgmt_ltm = getattr(_bs_pack, "ltm_ebitda_management", None) if _bs_pack else None

    # Optional top-contract concentration from trading pack (labels from extract).
    dc_share_pct = None
    dc_billings = None
    top_contract_label = "largest contract"
    top_contract_term = None
    acct_rev: dict[int, float] = {}
    deal_slug = str(getattr(store, "deal_slug", None) or "")
    if deal_slug:
        try:
            from agetic_cdd_api.services_fdd_trading import (
                build_trading_pack,
                concentration_rows,
            )

            pack = build_trading_pack(deal_slug)
            if pack is not None:
                top_contract_label = pack.top_contract_label or top_contract_label
                top_contract_term = pack.top_contract_term
                # Prefer accounts revenue so FY sits on the same basis as LTM.
                acct_rev = {
                    y: v
                    for y, v in {
                        y: pack.revenue_fy.get(y)
                        or (pack.fy.get("Revenue") or {}).get(y)
                        for y in (2023, 2024, 2025)
                    }.items()
                    if v is not None
                }
                if 2025 in acct_rev:
                    rev25 = acct_rev[2025]
                if 2024 in acct_rev:
                    rev24 = acct_rev[2024]
                if rev_yoy is None and rev24 and rev25 and abs(float(rev24)) > 1e-12:
                    rev_yoy = 100.0 * (float(rev25) / float(rev24) - 1.0)
                for lab, val, kind in concentration_rows(pack, year=2025):
                    lab_l = lab.lower()
                    if (
                        kind == "pct"
                        and "share of total revenue" in lab_l
                        and "municipal share" not in lab_l
                    ):
                        dc_share_pct = val
                    if kind == "money" and "billings" in lab_l:
                        dc_billings = val
        except Exception:
            pass

    # Diligence margins from diligence EBITDA / accounts revenue (not management %).
    dil_m25 = None
    if dil_ebitda is not None and rev25 is not None and abs(float(rev25)) > 1e-12:
        dil_m25 = 100.0 * float(dil_ebitda) / float(rev25)
    dil_m_ltm = None
    if dil_ltm is not None and rev_ltm is not None and abs(float(rev_ltm)) > 1e-12:
        dil_m_ltm = 100.0 * float(dil_ltm) / float(rev_ltm)
    elif ebitda_m_ltm is not None:
        dil_m_ltm = ebitda_m_ltm

    _ltm_cell = next(
        (
            c
            for c in _cells_for_metric_multi(
                store, ("ex_db_is", "ex_m1_trading", "ex_db_metrics"), "ebitda"
            )
            if _is_ltm_cell(c)
        ),
        next(
            (
                c
                for c in _cells_for_metric_multi(
                    store, ("ex_db_is", "ex_m1_trading", "ex_db_metrics"), "revenue"
                )
                if _is_ltm_cell(c)
            ),
            None,
        ),
    )
    if _ltm_cell is not None:
        ltm_hdr = _period_column_header(_ltm_cell, kind="ltm")
    elif rev_ltm is not None or ebitda_ltm is not None:
        ltm_hdr = "LTM Jul-26"
    else:
        ltm_hdr = _period_column_header(None, kind="ltm")
    ytd_hdr = _period_column_header(
        next(
            (
                c
                for c in _cells_for_metric_multi(
                    store, ("ex_db_is", "ex_m1_trading", "ex_db_metrics"), "ebitda"
                )
                if _is_ytd_cell(c)
            ),
            None,
        ),
        kind="ytd",
    )

    kpis: list[KpiTile] = []
    if rev_ltm is not None:
        kpis.append(
            KpiTile(
                label=f"Revenue, {ltm_hdr}",
                value=_fmt_num(rev_ltm, money=True, prose=True),
                detail=(
                    f"FY25 growth {_fmt_num(rev_yoy, pct=True)}"
                    if rev_yoy is not None
                    else "Trailing twelve months"
                ),
            )
        )
    else:
        kpis.append(
            KpiTile(
                label="Revenue, FY25",
                value=_fmt_num(rev25, money=True, prose=True),
                detail=f"YoY {_fmt_num(rev_yoy, pct=True)}" if rev_yoy is not None else "Closed year",
            )
        )
    kpis.append(
        KpiTile(
            label="Diligence EBITDA, FY25",
            value=_fmt_num(dil_ebitda, money=True, prose=True),
            detail=(
                f"Margin {_fmt_num(dil_m25, pct=True)}"
                + (
                    f"; FY24 {_fmt_num(ebitda24, money=True, prose=True)}"
                    if ebitda24 is not None
                    else ""
                )
                if dil_m25 is not None
                else "Unadjusted pending QoE"
            ),
        )
    )
    if dil_ltm is not None:
        kpis.append(
            KpiTile(
                label=f"Diligence EBITDA, {ltm_hdr}",
                value=_fmt_num(dil_ltm, money=True, prose=True),
                detail=(
                    f"Margin {_fmt_num(dil_m_ltm, pct=True)}"
                    if dil_m_ltm is not None
                    else "Trailing twelve months"
                ),
            )
        )
    elif ebitda24 is not None:
        kpis.append(
            KpiTile(
                label="EBITDA, FY24",
                value=_fmt_num(ebitda24, money=True, prose=True),
                detail="Prior closed year",
            )
        )
    if dc_share_pct is not None:
        kpis.append(
            KpiTile(
                label=f"{top_contract_label} share, FY25"[:42],
                value=_fmt_num(dc_share_pct, pct=True),
                detail=(
                    (
                        top_contract_term[:48]
                        if top_contract_term
                        else (
                            f"Billings {_fmt_num(dc_billings, money=True, prose=True)}"
                            if dc_billings is not None
                            else "Concentration — confirm term / renewal"
                        )
                    )
                ),
            )
        )
    else:
        kpis.append(
            KpiTile(
                label="Gross margin, FY25",
                value=_fmt_num(gm25, pct=True),
                detail="Monthly pack / exhibit basis",
            )
        )
    kpis.append(
        KpiTile(
            label="Cash, FY25",
            value=_fmt_num(cash, money=True, prose=True),
            detail=f"Net debt {_fmt_num(net_debt, money=True, prose=True)}" if net_debt is not None else "",
        )
    )
    kpis.append(
        KpiTile(
            label="Accrued / dividends payable",
            value=_fmt_num(divs, money=True, prose=True) if divs is not None else "—",
            detail="Proposed debt-like if cumulative" if divs is not None else "Not in exhibits",
        )
    )
    kpis = kpis[:6]

    key_table = _period_table(
        store,
        exhibit_id=es_exhibits,
        metrics=[
            ("revenue", "Revenue", "money"),
            ("gross_margin", "Gross margin", "pct"),
            ("ebitda", "Reported EBITDA", "money"),
            ("ebitda_margin", "Reported EBITDA margin", "pct"),
            ("net_income", "Net income (loss)", "money"),
            ("operating_cash_flow", "Operating cash flow", "money"),
            ("nwc", "NWC", "money"),
            ("net_debt", "Net debt / (cash)", "money"),
        ],
        title="Key figures",
    )
    if key_table is None:
        headers = ["Metric", "FY24", "FY25"]
        if ebitda_ytd is not None or rev_ytd is not None:
            headers.append(ytd_hdr)
        if dil_ltm is not None or rev_ltm is not None:
            headers.append(ltm_hdr)
        row_rev = ["Revenue", _fmt_num(rev24, money=True), _fmt_num(rev25, money=True)]
        row_eb = [
            "Reported EBITDA",
            _fmt_num(ebitda24, money=True),
            _fmt_num(ebitda25 if ebitda25 is not None else dil_ebitda, money=True),
        ]
        if ebitda_ytd is not None or rev_ytd is not None:
            row_rev.append(_fmt_num(rev_ytd, money=True))
            row_eb.append(_fmt_num(ebitda_ytd, money=True))
        if dil_ltm is not None or rev_ltm is not None:
            row_rev.append(_fmt_num(rev_ltm, money=True))
            row_eb.append(
                _fmt_num(
                    mgmt_ltm if mgmt_ltm is not None else dil_ltm,
                    money=True,
                )
            )
        key_table = SlideTable(
            title=f"Key figures {scale_suffix()}",
            headers=headers,
            rows=[
                row_rev,
                row_eb,
                [
                    "Reported EBITDA margin",
                    _fmt_num(
                        _metric(store, "ex_m1_trading", "ebitda_margin", 2024), pct=True
                    ),
                    _fmt_num(ebitda_m25, pct=True),
                ],
            ],
        )
    # Prefer accounts revenue in the FY columns when exhibits carried CIM basis.
    if key_table is not None and acct_rev:
        hdrs = list(key_table.headers or [])
        fy_idx = {
            y: next(
                (
                    i
                    for i, h in enumerate(hdrs)
                    if str(h).upper() in {f"FY{y % 100:02d}", f"FY{y}"}
                ),
                None,
            )
            for y in acct_rev
        }
        new_rows = []
        for r in key_table.rows:
            row = list(r)
            if row and str(row[0]).lower() == "revenue":
                for y, idx in fy_idx.items():
                    val = acct_rev.get(y)
                    if idx is not None and val is not None and idx < len(row):
                        row[idx] = _fmt_num(val, money=True)
            new_rows.append(row)
        key_table = key_table.model_copy(update={"rows": new_rows})
    # Inject / correct LTM column from trading/cash pack (mgmt vs diligence).
    if key_table is not None and (rev_ltm is not None or dil_ltm is not None):
        hdrs = list(key_table.headers or [])
        ltm_col = next((i for i, h in enumerate(hdrs) if "LTM" in str(h).upper()), None)
        if ltm_col is None:
            hdrs.append(ltm_hdr)
            ltm_col = len(hdrs) - 1
            appending = True
        else:
            appending = False

        def _ltm_cell(lab: str) -> str:
            if lab == "revenue":
                return _fmt_num(rev_ltm, money=True)
            if lab in {"reported ebitda", "ebitda"}:
                return _fmt_num(
                    mgmt_ltm
                    if mgmt_ltm is not None
                    else (ebitda_ltm if ebitda_ltm is not None else dil_ltm),
                    money=True,
                )
            if lab == "diligence ebitda":
                return _fmt_num(dil_ltm, money=True)
            if "reported ebitda margin" in lab or lab == "ebitda margin":
                if mgmt_ltm is not None and rev_ltm and abs(float(rev_ltm)) > 1e-12:
                    return _fmt_num(100.0 * float(mgmt_ltm) / float(rev_ltm), pct=True)
                return _fmt_num(ebitda_m_ltm, pct=True)
            if "diligence ebitda margin" in lab:
                return _fmt_num(dil_m_ltm, pct=True)
            return "—"

        new_rows = []
        for r in key_table.rows:
            row = list(r)
            lab = str(row[0]).lower() if row else ""
            cell = _ltm_cell(lab)
            if appending:
                row.append(cell)
            else:
                while len(row) <= ltm_col:
                    row.append("—")
                if lab in {
                    "revenue",
                    "reported ebitda",
                    "ebitda",
                    "diligence ebitda",
                } or "ebitda margin" in lab:
                    row[ltm_col] = cell
            new_rows.append(row)
        key_table = key_table.model_copy(update={"headers": hdrs, "rows": new_rows})
    key_table = _overlay_es_ebitda_rows(
        key_table,
        dil_ebitda=dil_ebitda,
        mgmt_ebitda=mgmt_ebitda,
        reported_fy25=ebitda25 if ebitda25 is not None else dil_ebitda,
    )
    # After overlay, fill Diligence EBITDA LTM + diligence margin FY25/LTM.
    if key_table is not None:
        hdrs = list(key_table.headers or [])
        fy25_i = next(
            (i for i, h in enumerate(hdrs) if str(h).upper() in {"FY25", "FY2025"}),
            None,
        )
        ltm_i = next((i for i, h in enumerate(hdrs) if "LTM" in str(h).upper()), None)
        rows = [list(r) for r in key_table.rows]
        dil_i = next(
            (i for i, r in enumerate(rows) if str(r[0]).lower() == "diligence ebitda"),
            None,
        )
        if dil_i is not None and ltm_i is not None and dil_ltm is not None:
            while len(rows[dil_i]) <= ltm_i:
                rows[dil_i].append("—")
            rows[dil_i][ltm_i] = _fmt_num(dil_ltm, money=True)
        # Inject diligence margin row (FY25 + LTM) distinct from reported margin.
        if dil_m25 is not None or dil_m_ltm is not None:
            if not any("diligence ebitda margin" in str(r[0]).lower() for r in rows):
                anchor = next(
                    (
                        i
                        for i, r in enumerate(rows)
                        if "reported ebitda margin" in str(r[0]).lower()
                    ),
                    dil_i if dil_i is not None else len(rows) - 1,
                )
                row = ["Diligence EBITDA margin"] + ["—"] * (len(hdrs) - 1)
                if fy25_i is not None and dil_m25 is not None:
                    row[fy25_i] = _fmt_num(dil_m25, pct=True)
                if ltm_i is not None and dil_m_ltm is not None:
                    row[ltm_i] = _fmt_num(dil_m_ltm, pct=True)
                rows.insert(anchor + 1, row)
            else:
                for r in rows:
                    if "diligence ebitda margin" in str(r[0]).lower():
                        while len(r) < len(hdrs):
                            r.append("—")
                        if fy25_i is not None and dil_m25 is not None:
                            r[fy25_i] = _fmt_num(dil_m25, pct=True)
                        if ltm_i is not None and dil_m_ltm is not None:
                            r[ltm_i] = _fmt_num(dil_m_ltm, pct=True)
        key_table = key_table.model_copy(update={"rows": rows})

    obs: list[str] = []
    if ebitda24 is not None and dil_ebitda is not None and abs(float(ebitda24)) > 1e-12:
        try:
            drop = (float(dil_ebitda) / float(ebitda24) - 1.0) * 100.0
            obs.append(
                f"Earnings moved {_fmt_num(drop, pct=True)} vs FY24 "
                f"({_fmt_num(ebitda24, money=True, prose=True)} → "
                f"{_fmt_num(dil_ebitda, money=True, prose=True)})."
            )
        except Exception:
            pass
    if rev_yoy is not None:
        obs.append(
            f"Revenue grew {_fmt_num(rev_yoy, pct=True)} into FY25 on the investor workbook basis."
        )
    sga_yoy = _metric(store, "ex_m3_costs", "sga_yoy", 2025)
    if sga_yoy is not None:
        obs.append(
            f"SG&A grew {_fmt_num(sga_yoy, pct=True)} — cost intensity is a primary earnings driver."
        )
    if dc_share_pct is not None:
        obs.append(
            f"Growth is concentrated: {top_contract_label} is "
            f"{_fmt_num(dc_share_pct, pct=True)} of FY25 revenue."
        )
    if divs is not None:
        obs.append(
            f"Dividends payable {_fmt_num(divs, money=True, prose=True)} sit on the balance sheet — "
            "treat as debt-like pending legal review."
        )
    obs.extend(draft_obs)
    if not obs:
        obs = ["Executive summary drafted from approved exhibits and findings."]

    headline = obs[0][:180]
    if dil_ebitda is not None:
        half = ""
        if ebitda24 is not None and abs(float(ebitda24)) > 1e-12:
            ratio = float(dil_ebitda) / float(ebitda24)
            half = (
                ", half of FY24"
                if ratio <= 0.55
                else f", vs {_fmt_num(ebitda24, money=True, prose=True)} in FY24"
            )
        if dil_ltm is not None:
            headline = (
                f"Diligence EBITDA is {_fmt_num(dil_ebitda, money=True, prose=True)} in FY25 "
                f"and {_fmt_num(dil_ltm, money=True, prose=True)} for {ltm_hdr}{half}"
            )
        else:
            headline = (
                f"Diligence EBITDA is {_fmt_num(dil_ebitda, money=True, prose=True)} "
                f"in FY25{half}"
            )

    es_kpi = SlideSpec(
        slide_id="ch_es_kpi",
        layout="kpi_strip",
        chapter="es",
        banner="EXECUTIVE SUMMARY",
        headline=headline[:180],
        kpis=kpis,
        table=key_table,
        observations=obs[:4],
        source=_SOURCE_DEFAULT,
        evidence_tier="B",
        figure_ids=["ex_m1_trading", "ex_m6_net_debt", "ex_m5_nwc"],
    )

    # Prefer business MODEL / QoE findings over claim-noise for the ES ranking.
    raw_findings = _findings_list(findings)
    # Closed-year revenue "claimed vs accounts" gaps are already reconciled on Trading —
    # keep them off the ES lead list so High claim noise does not crowd the page.
    def _is_revenue_basis_claim(f: Any) -> bool:
        src = getattr(getattr(f, "source", None), "value", None) or getattr(f, "source", None)
        title_l = str(getattr(f, "title", "") or "").lower()
        return str(src) == "claim" and "revenue" in title_l and (
            "contradicted" in title_l or "claimed vs" in title_l or "resolve claim" in title_l
        )

    filtered = [f for f in raw_findings if not _is_revenue_basis_claim(f)]
    ranked_src = top_findings(filtered or raw_findings, limit=10) if raw_findings else []
    ranked: list[FindingRankRow] = []
    finding_rows: list[list[str]] = []
    for i, f in enumerate(ranked_src, start=1):
        sev = getattr(getattr(f, "severity", None), "value", "") or ""
        title = getattr(f, "title", "") or "Finding"
        # Soften legacy "Resolve claim …" scaffolding still stored on older runs.
        if title.lower().startswith("resolve claim"):
            title = re.sub(r"(?i)^resolve claim\s+", "", title)
            title = re.sub(r"\s*\((?:contradicted|unverifiable|pass)\)\s*$", "", title)
            title = title.replace("_", " ").strip().title() or title
        detail = (getattr(f, "observation", None) or "")[:90]
        quant = _es_quantified(f)
        prot = _es_protection(f)
        tier = _es_tier(f)
        ranked.append(
            FindingRankRow(
                rank=f"F{i}",
                severity=_es_rating(sev),
                title=title,
                detail=detail,
            )
        )
        finding_rows.append(
            [
                f"F{i}",
                title[:110],
                _es_rating(sev),
                quant,
                tier,
                prot,
            ]
        )
    counts = dict(getattr(findings, "counts", None) or {})
    high_n = int(counts.get("high", 0) or 0)
    med_n = int(counts.get("moderate", 0) or 0)
    if ranked and dc_share_pct is not None and dil_ebitda is not None and ebitda24 is not None:
        findings_headline = (
            f"{_fmt_num(dc_share_pct, pct=True)} of revenue rides on {top_contract_label} "
            f"and earnings halved: {len(ranked)} findings ranked"
            if abs(float(ebitda24)) > 1e-12
            and float(dil_ebitda) / float(ebitda24) <= 0.55
            else f"{len(ranked)} findings ranked — concentration and earnings quality lead"
        )
    elif ranked:
        findings_headline = (
            f"{high_n} high / {med_n} moderate findings ranked"
            if high_n or med_n
            else f"{len(ranked)} findings ranked"
        )
    else:
        findings_headline = "Findings register — none material yet for this run"

    es_findings = SlideSpec(
        slide_id="ch_es_findings",
        layout="findings_rank",
        chapter="es",
        banner="EXECUTIVE SUMMARY",
        headline=findings_headline[:180],
        findings=ranked
        or [
            FindingRankRow(
                rank="—",
                severity="info",
                title="No ranked findings yet",
                detail="Complete models / claims to populate",
            )
        ],
        table=SlideTable(
            title="Findings ranked",
            headers=[
                "#",
                "Finding",
                "Rating",
                "Quantified effect",
                "Tier",
                "Protection or action",
            ],
            rows=finding_rows
            or [["—", "No ranked findings yet", "info", "", "", ""]],
        ),
        source="Diligence analysis",
        evidence_tier="A/B/C",
    )

    slides: list[SlideSpec] = [es_kpi, es_findings]

    # Case slide: Management / CIM / Diligence + sensitivity range (needs QoE views).
    if qoe is not None and any(
        v is not None for v in (mgmt_ebitda, cim_ebitda, sens_low, sens_high)
    ):
        case_rows = [
            ["Management", _fmt_num(mgmt_ebitda, money=True)],
            ["CIM", _fmt_num(cim_ebitda, money=True)],
            ["Diligence", _fmt_num(dil_ebitda, money=True)],
            ["Downside", _fmt_num(sens_low, money=True)],
            ["Upside", _fmt_num(sens_high, money=True)],
        ]
        # Project Crew "within $X" is CIM vs diligence (not max of all three views).
        within = None
        if cim_ebitda is not None and dil_ebitda is not None:
            within = abs(float(cim_ebitda) - float(dil_ebitda))
        elif mgmt_ebitda is not None and dil_ebitda is not None:
            within = abs(float(mgmt_ebitda) - float(dil_ebitda))
        if within is not None and sens_low is not None and sens_high is not None:
            case_headline = (
                f"Management, CIM and diligence EBITDA for FY25 sit within "
                f"{_fmt_num(within, money=True, prose=True)} of each other; "
                f"the range runs {_fmt_num(sens_low, money=True, prose=True)} "
                f"to {_fmt_num(sens_high, money=True, prose=True)}"
            )
        elif sens_low is not None and sens_high is not None:
            case_headline = (
                f"FY25 EBITDA cases run {_fmt_num(sens_low, money=True, prose=True)} "
                f"to {_fmt_num(sens_high, money=True, prose=True)}; "
                f"diligence is {_fmt_num(dil_ebitda, money=True, prose=True)}"
            )
        else:
            case_headline = "FY25 EBITDA by view — management, CIM and diligence"
        case_obs: list[str] = []
        if mgmt_ebitda is not None and dil_ebitda is not None and abs(float(mgmt_ebitda) - float(dil_ebitda)) > 1e-9:
            case_obs.append(
                f"Management {_fmt_num(mgmt_ebitda, money=True, prose=True)} vs diligence "
                f"{_fmt_num(dil_ebitda, money=True, prose=True)} after register treatments."
            )
        if cim_ebitda is not None and dil_ebitda is not None:
            cim_delta = float(cim_ebitda) - float(dil_ebitda)
            case_obs.append(
                f"CIM shows {_fmt_num(cim_ebitda, money=True, prose=True)} "
                f"({_fmt_num(cim_delta, money=True, prose=True)} "
                f"{'above' if cim_delta >= 0 else 'below'} diligence)."
            )
        case_obs.append(
            "Sensitivities are judgemental and are not added to diligence EBITDA."
        )
        slides.append(
            SlideSpec(
                slide_id="ch_es_cases",
                layout="section_table_obs",
                chapter="es",
                banner="EXECUTIVE SUMMARY",
                headline=case_headline[:180],
                table=SlideTable(
                    title=f"FY25 EBITDA by view and case {scale_suffix()}",
                    headers=["View / case", "Amount"],
                    rows=case_rows,
                ),
                observations=case_obs[:5],
                footnotes=[
                    "Sensitivities are grey: they rest on tier C judgements and are not added to diligence EBITDA."
                ],
                source="QoE workbook; CIM / investor workbook crosswalk",
                evidence_tier="B/C",
                figure_ids=["ex_qoe_bridge"],
            )
        )

    asks = []
    for f in _high_mod_findings(findings)[:8]:
        ask = getattr(f, "ask_management", None) or getattr(f, "title", None)
        if ask:
            asks.append(
                [
                    _es_rating(
                        getattr(getattr(f, "severity", None), "value", "") or ""
                    ).upper()
                    or "—",
                    getattr(f, "title", "")[:50],
                    str(ask)[:70],
                ]
            )
    if not asks:
        asks = [["—", "No deal asks yet", "Complete findings / request list"]]
    price_on = dil_ltm if dil_ltm is not None else dil_ebitda
    if divs is not None and price_on is not None:
        asks_headline = (
            f"Deal considerations: settle {_fmt_num(divs, money=True, prose=True)} of "
            f"dividend arrears"
            + (f" and see the {top_contract_label}" if dc_share_pct is not None else "")
            + f" before pricing on {_fmt_num(price_on, money=True, prose=True)}"
        )
    elif price_on is not None and dc_share_pct is not None:
        asks_headline = (
            f"Deal considerations: see {top_contract_label} before pricing on "
            f"{_fmt_num(price_on, money=True, prose=True)}"
        )
    else:
        asks_headline = (
            "Deal considerations: settle high-priority diligence asks before pricing"
        )
    slides.append(
        SlideSpec(
            slide_id="ch_es_asks",
            layout="request_table",
            chapter="es",
            banner="EXECUTIVE SUMMARY",
            headline=asks_headline[:180],
            table=SlideTable(
                title="Deal asks from findings",
                headers=["Priority", "Item", "Ask management"],
                rows=asks,
            ),
            source="Diligence analysis",
            evidence_tier="A/B",
        )
    )
    return slides


def plan_transaction(
    *,
    store: ExhibitStoreDoc,
    scope: Any | None,
    requests: list[str],
    company: str | None = None,
) -> list[SlideSpec]:
    from agetic_cdd_api.services_fdd_chapter_depth import parse_transaction_terms
    from agetic_cdd_api.services_fdd_trading import build_trading_pack, stream_table_rows

    deal_slug = str(getattr(store, "deal_slug", None) or "")
    entity = company
    if scope is not None and getattr(scope, "entities_in", None):
        ents = list(scope.entities_in)
        if ents:
            entity = ", ".join(str(e) for e in ents[:2])
    terms = parse_transaction_terms(deal_slug, company=entity) if deal_slug else None

    term_rows: list[list[str]] = []
    if terms is not None:
        term_rows.extend(
            [
                ["Issuer", terms.issuer or entity or "—"],
                [
                    "Round",
                    (
                        f"{terms.round_label or 'Series round'}: "
                        + (
                            f"about {_fmt_num(terms.primary_m, money=True, prose=True)} of primary capital"
                            if terms.primary_m is not None
                            else "size pending"
                        )
                        + (
                            f"; secondary not less than {_fmt_num(terms.secondary_m, money=True, prose=True)}"
                            if terms.secondary_m is not None
                            else ""
                        )
                    )[:120],
                ],
                [
                    "Use of proceeds",
                    (terms.use_of_proceeds or "Pending CIM schedule (open request)")[:120],
                ],
                [
                    "Existing preferred",
                    (terms.existing_preferred or "Cumulative / participating terms pending charter")[:120],
                ],
                ["Control", (terms.control or "Cap table pending")[:120]],
                [
                    "Valuation reference",
                    (
                        terms.valuation_ref
                        or f"{terms.round_label or 'Round'} price not in the data room"
                    )[:120],
                ],
            ]
        )
        prior_amt = getattr(terms, "prior_raised_m", None)
        if prior_amt is None:
            prior_amt = getattr(terms, "series_a_raised_m", None)
        if prior_amt is not None:
            prior_lab = getattr(terms, "prior_round_label", None) or "Prior preferred"
            term_rows.append(
                [
                    f"{prior_lab} raised",
                    _fmt_num(prior_amt, money=True, prose=True),
                ]
            )
    if not term_rows:
        term_rows = [
            ["Issuer", entity or "—"],
            ["Round / use of proceeds", "Pending CIM / teaser"],
            ["Existing preferred", "Pending charter / stock purchase agreement"],
        ]
    for req in (requests or [])[:2]:
        term_rows.append(["Open request", str(req)[:100]])

    if terms is not None and terms.primary_m is not None:
        round_name = terms.round_label or "The round"
        terms_headline = (
            f"{round_name} seeks {_fmt_num(terms.primary_m, money=True, prose=True)} of primary capital"
            + (
                "; existing preferred carries cumulative dividends and participation"
                if terms.existing_preferred
                else ""
            )
        )
    else:
        terms_headline = "Transaction terms — round size and preferred rights pending CIM / teaser"

    slides: list[SlideSpec] = [
        SlideSpec(
            slide_id="ch_tx_terms",
            layout="section_table_obs",
            chapter="transaction",
            banner="TRANSACTION AND BUSINESS",
            headline=terms_headline[:180],
            table=SlideTable(
                title="Transaction overview",
                headers=["Item", "Position"],
                rows=term_rows,
            ),
            observations=[
                "Arrears on cumulative preferred may rank ahead of new money — confirm in the charter.",
                *(terms.notes[:2] if terms else []),
                *(requests[:1] if requests else []),
            ][:6],
            source="CIM / teaser; Diligence analysis",
            evidence_tier="B/C",
        )
    ]

    # Business overview — stream mix from trading pack when available.
    pack = build_trading_pack(deal_slug) if deal_slug else None
    rev25 = _metric(store, ("ex_m1_trading", "ex_db_is"), "revenue", 2025)
    rev_yoy = _metric(store, "ex_m1_trading", "revenue_yoy", 2025)
    if pack is not None and pack.revenue_fy.get(2025) is not None:
        rev25 = pack.revenue_fy.get(2025)
    stream_rows: list[list[str]] = []
    if pack is not None and pack.has_streams:
        years = list(pack.years)
        headers = ["Stream", *[f"FY{y % 100:02d}" for y in years]]
        for label, fy, _ytd in stream_table_rows(pack):
            if label in {
                "Cost of operations",
                "Gross profit",
                "EBITDA",
                "Net income",
            }:
                continue
            stream_rows.append(
                [label, *[_fmt_num(fy.get(y), money=True) for y in years]]
            )
        mix_table = SlideTable(
            title=f"Revenue by stream {scale_suffix()}",
            headers=headers,
            rows=stream_rows,
            basis=_ctx().basis_default,
            source="Monthly management accounts; Investor workbook",
            evidence_tier="B",
        )
        muni25 = (pack.fy.get("Municipal") or {}).get(2025)
        dc = pack.dc_billings
        biz_obs = []
        if muni25 is not None:
            biz_obs.append(
                f"Municipal revenue {_fmt_num(muni25, money=True, prose=True)} in FY25"
                + (
                    (
                        f"; top contract billings {_fmt_num(dc, money=True, prose=True)}"
                        if dc is not None
                        else ""
                    )
                )
                + "."
            )
        if rev_yoy is not None:
            biz_obs.append(f"Total revenue grew {_fmt_num(rev_yoy, pct=True)} into FY25.")
        biz_headline = (
            f"Revenue reached {_fmt_num(rev25, money=True, prose=True)} in FY25"
            + (f", up {_fmt_num(rev_yoy, pct=True)}" if rev_yoy is not None else "")
            + (
                "; municipal / contract concentration drove the growth"
                if dc is not None or muni25 is not None
                else ""
            )
            if rev25 is not None
            else "Revenue and stream mix"
        )
        slides.append(
            SlideSpec(
                slide_id="ch_tx_business",
                layout="section_table_obs",
                chapter="transaction",
                banner="TRANSACTION AND BUSINESS",
                headline=biz_headline[:180],
                table=mix_table,
                observations=biz_obs[:6]
                or ["Stream mix from monthly / investor workbook schedules."],
                source="Monthly management accounts; Investor workbook",
                evidence_tier="B",
                figure_ids=["ex_m1_trading"],
            )
        )
    else:
        rev_table = _period_table(
            store,
            exhibit_id=("ex_m1_trading", "ex_db_metrics", "ex_db_is", "ex_m2_margin"),
            metrics=[
                ("revenue", "Revenue", "money"),
                ("revenue_yoy", "Revenue YoY %", "pct"),
                ("gross_margin", "Gross margin %", "pct"),
                ("ebitda", "EBITDA", "money"),
            ],
            title="Revenue and earnings by year",
        )
        slides.append(
            SlideSpec(
                slide_id="ch_tx_business",
                layout="section_table_obs",
                chapter="transaction",
                banner="TRANSACTION AND BUSINESS",
                headline=(
                    f"Revenue reached {_fmt_num(rev25, money=True, prose=True)} in FY25"
                    if rev25 is not None
                    else "Business overview — stream mix held pending schedules"
                )[:180],
                table=rev_table
                or SlideTable(
                    title="Business overview",
                    headers=["Item", "Status"],
                    rows=[["Revenue by stream", "Pending mix schedule"]],
                ),
                observations=_held_obs(
                    chapter_title="Revenue by stream",
                    requests=requests
                    or ["Provide municipal / DC / commercial / residential split"],
                ),
                source=_SOURCE_DEFAULT,
                evidence_tier="B/C",
                figure_ids=["ex_m1_trading"] if rev_table else [],
            )
        )
    return slides


def _qoe_adj_body(row: Any) -> str:
    """Prose body for an ADJ card (nature / amounts / treatment)."""
    aid = getattr(row, "adjustment_id", "") or "ADJ"
    label = getattr(row, "label", "") or ""
    lines = [f"{aid} {label}".strip()]
    rationale = (getattr(row, "rationale", None) or "").strip()
    if rationale:
        lines.append(f"Nature\n{rationale}")
    mgmt = getattr(row, "management_amount", None)
    dil = getattr(row, "diligence_amount", None)
    lines.append(
        "Amount\n"
        f"Management {_fmt_num(mgmt, money=True, prose=True)}; "
        f"diligence {_fmt_num(dil, money=True, prose=True)}."
    )
    recur = getattr(row, "recurring_status", None)
    if recur:
        lines.append(f"Recurrence\n{str(recur).replace('_', ' ').title()}.")
    treatment = str(getattr(row, "treatment", "") or "pending")
    diff_reason = (getattr(row, "difference_reason", None) or "").strip()
    treat_line = f"Treatment\n{treatment.title()}"
    if diff_reason:
        treat_line += f": {diff_reason}"
    lines.append(treat_line)
    return "\n\n".join(lines)


def plan_qoe(
    *,
    commentary: CommentaryDoc | None,
    store: ExhibitStoreDoc,
    qoe: Any | None,
    requests: list[str],
) -> list[SlideSpec]:
    secs = _CHAPTER_SEC_SOURCES["qoe"]
    draft_obs = _obs_from_drafts(commentary, secs)
    slides: list[SlideSpec] = []

    register = list(getattr(qoe, "register_rows", None) or []) if qoe else []
    candidates = list(getattr(qoe, "candidates", None) or []) if qoe else []
    adj_rows = register or candidates
    bridge_adj = [
        r
        for r in adj_rows
        if str(getattr(r, "treatment", "") or "") in {"accept", "partial", "reject"}
        and (
            getattr(r, "management_amount", None) is not None
            or getattr(r, "diligence_amount", None) is not None
        )
    ]
    nil_adj = [
        r
        for r in adj_rows
        if str(getattr(r, "adjustment_id", "") or "").upper().startswith("ADJ")
        and str(getattr(r, "treatment", "") or "") in {"pending", "reject"}
        and abs(float(getattr(r, "diligence_amount", None) or 0.0)) < 1e-12
        and abs(float(getattr(r, "management_amount", None) or 0.0)) < 1e-12
    ]
    # Rejected management add-backs still belong on the bridge summary, not the nil card.
    nil_adj = [r for r in nil_adj if r not in bridge_adj]

    bridge_periods = list(getattr(qoe, "bridge", None) or []) if qoe else []
    bridge_rows: list[list[str]] = []
    period_label = getattr(qoe, "period", None) or "FY25A"
    reported = None
    dil = getattr(qoe, "adjusted_ebitda_diligence", None) if qoe else None
    mgmt = getattr(qoe, "adjusted_ebitda_management", None) if qoe else None

    if bridge_periods:
        bp = bridge_periods[0]
        period_label = getattr(bp, "period", None) or period_label
        reported = getattr(bp, "reported_ebitda", None)
        for step in list(getattr(bp, "steps", None) or []):
            bridge_rows.append(
                [
                    getattr(step, "label", None) or getattr(step, "step_id", ""),
                    _fmt_num(getattr(step, "amount", None), money=True),
                    _fmt_num(getattr(step, "running_total", None), money=True),
                ]
            )
        # Show management add-backs that diligence rejected (real bridge, not empty).
        for row in bridge_adj:
            if str(getattr(row, "treatment", "")) != "reject":
                continue
            mgmt_amt = getattr(row, "management_amount", None)
            if mgmt_amt is None or abs(float(mgmt_amt)) < 1e-12:
                continue
            bridge_rows.append(
                [
                    f"{getattr(row, 'adjustment_id', '')} "
                    f"{getattr(row, 'label', '')} (management)".strip(),
                    _fmt_num(mgmt_amt, money=True),
                    _fmt_num(
                        (float(reported) if reported is not None else 0.0)
                        + float(mgmt_amt),
                        money=True,
                    ),
                ]
            )
            bridge_rows.append(
                [
                    f"{getattr(row, 'adjustment_id', '')} reversed for diligence".strip(),
                    _fmt_num(-float(mgmt_amt), money=True),
                    _fmt_num(reported, money=True),
                ]
            )
        for row in nil_adj:
            bridge_rows.append(
                [
                    f"{getattr(row, 'adjustment_id', '')} {getattr(row, 'label', '')}".strip(),
                    "—",
                    "Nil / pending",
                ]
            )
        bridge_rows.append(
            [
                "Diligence adjusted EBITDA",
                _fmt_num(
                    dil if dil is not None else getattr(bp, "adjusted_ebitda", None),
                    money=True,
                ),
                "",
            ]
        )
        if mgmt is not None:
            # Insert management EBITDA line after reported + add-backs when distinct.
            if abs(float(mgmt) - float(dil or reported or 0.0)) > 1e-9:
                # Place after first reject add-back block if present, else after base.
                insert_at = 1
                for i, row in enumerate(bridge_rows):
                    if "management" in str(row[0]).lower():
                        insert_at = i + 1
                bridge_rows.insert(
                    insert_at,
                    ["Management EBITDA", _fmt_num(mgmt, money=True), ""],
                )
        cim_ebitda_bridge = getattr(qoe, "cim_ebitda", None) if qoe else None
        if cim_ebitda_bridge is not None:
            bridge_rows.append(
                ["CIM / investor workbook EBITDA", _fmt_num(cim_ebitda_bridge, money=True), ""]
            )
        sens_low = getattr(qoe, "sensitivity_low", None) if qoe else None
        sens_high = getattr(qoe, "sensitivity_high", None) if qoe else None
        if sens_low is not None or sens_high is not None:
            bridge_rows.append(
                [
                    "Sensitivity range (low–high)",
                    f"{_fmt_num(sens_low, money=True)} – {_fmt_num(sens_high, money=True)}",
                    "",
                ]
            )
    else:
        reported = _metric(store, "ex_qoe_bridge", "reported_ebitda", None)
        if reported is None:
            reported = _metric(store, "ex_m1_trading", "ebitda", 2025)
        bridge_rows = [
            ["Reported EBITDA", _fmt_num(reported, money=True), ""],
            ["Adjustments", "—", "Register empty / pending"],
            ["Diligence EBITDA", _fmt_num(reported, money=True), "Unadjusted"],
        ]

    obs = list(draft_obs)
    if dil is not None and mgmt is not None and abs(float(dil) - float(mgmt)) > 1e-9:
        obs.insert(
            0,
            f"Diligence EBITDA {_fmt_num(dil, money=True, prose=True)} vs management "
            f"{_fmt_num(mgmt, money=True, prose=True)} after register treatments.",
        )
    elif dil is not None:
        obs.insert(
            0,
            f"Diligence EBITDA {_fmt_num(dil, money=True, prose=True)} "
            "(no material bridge gap vs management).",
        )
    if nil_adj:
        obs.append(
            f"{len(nil_adj)} candidate(s) considered at nil — listed for validation, "
            "not folded into diligence EBITDA."
        )
    if not obs:
        obs = _held_obs(chapter_title="Quality of earnings", requests=requests)

    # Optional LTM diligence from trading pack (same basis as ES).
    dil_ltm_qoe = None
    deal_slug_qoe = str(getattr(store, "deal_slug", None) or "")
    if deal_slug_qoe:
        try:
            from agetic_cdd_api.services_fdd_chapter_depth import build_cash_bs_pack

            dil_ltm_qoe = build_cash_bs_pack(deal_slug_qoe).ltm_ebitda
        except Exception:
            dil_ltm_qoe = None
    headline_bits = [
        f"Diligence EBITDA is {_fmt_num(dil if dil is not None else reported, money=True, prose=True)}"
        f" for {period_label}"
    ]
    if dil_ltm_qoe is not None:
        headline_bits[0] += (
            f" and {_fmt_num(dil_ltm_qoe, money=True, prose=True)} for LTM Jul-26"
        )
    elif mgmt is not None and dil is not None and abs(float(mgmt) - float(dil)) > 1e-9:
        headline_bits.append(
            f"after reversing management add-backs "
            f"({_fmt_num(mgmt, money=True, prose=True)} → "
            f"{_fmt_num(dil, money=True, prose=True)})"
        )
    if (
        dil_ltm_qoe is not None
        and mgmt is not None
        and dil is not None
        and abs(float(mgmt) - float(dil)) > 1e-9
    ):
        headline_bits.append("after reversing management's bad-debt add-back")
    slides.append(
        SlideSpec(
            slide_id="ch_qoe_bridge",
            layout="section_table_obs",
            chapter="qoe",
            banner="QUALITY OF EARNINGS",
            headline=" ".join(headline_bits)[:180],
            table=SlideTable(
                title=f"Quality of earnings summary ({period_label}) {scale_suffix()}",
                headers=["Bridge step", "Amount", "Running"],
                rows=bridge_rows,
            ),
            observations=obs[:6],
            source="QoE workbook; Approved databook exhibits",
            evidence_tier="B",
            figure_ids=["ex_qoe_bridge"],
            footnotes=[
                "Nil / pending adjustments remain outside diligence EBITDA until G4-approved.",
                "Sensitivities stay beside adjusted EBITDA.",
            ],
        )
    )

    # Management → diligence walk (real bridge when register differs).
    walk = list(getattr(qoe, "management_to_diligence_walk", None) or []) if qoe else []
    if walk and mgmt is not None and dil is not None and abs(float(mgmt) - float(dil)) > 1e-9:
        walk_rows = [
            [
                getattr(step, "label", None) or getattr(step, "step_id", ""),
                _fmt_num(getattr(step, "amount", None), money=True),
                _fmt_num(getattr(step, "running_total", None), money=True),
            ]
            for step in walk
        ]
        slides.append(
            SlideSpec(
                slide_id="ch_qoe_walk",
                layout="section_table_obs",
                chapter="qoe",
                banner="QUALITY OF EARNINGS",
                headline=(
                    f"{period_label} walk from management "
                    f"{_fmt_num(mgmt, money=True, prose=True)} to diligence "
                    f"{_fmt_num(dil, money=True, prose=True)}"
                )[:180],
                table=SlideTable(
                    title=f"{period_label} management to diligence EBITDA {scale_suffix()}",
                    headers=["Walk step", "Amount", "Running"],
                    rows=walk_rows,
                ),
                observations=[
                    "Walk re-adds diligence−management on each accepted / rejected add-back.",
                    *(draft_obs[:2] if draft_obs else []),
                ][:6],
                source="QoE workbook",
                evidence_tier="B",
                figure_ids=["ex_qoe_bridge"],
            )
        )

    # CIM vs diligence / management comparison.
    cim_ebitda = getattr(qoe, "cim_ebitda", None) if qoe else None
    cim_revenue = getattr(qoe, "cim_revenue", None) if qoe else None
    accounts_rev = getattr(qoe, "accounts_revenue", None) if qoe else None
    other_rev_row = next(
        (
            r
            for r in adj_rows
            if "other revenue" in str(getattr(r, "label", "") or "").lower()
            or str(getattr(r, "adjustment_id", "")).upper() == "ADJ-02"
        ),
        None,
    )
    other_rev_amt = None
    if other_rev_row is not None:
        # Prefer rationale-parsed amount from extract meta via abs(mgmt/dil) if stored on S-01.
        for r in adj_rows:
            if str(getattr(r, "treatment", "")) == "sensitivity" and "other revenue" in str(
                getattr(r, "label", "") or ""
            ).lower():
                other_rev_amt = abs(float(getattr(r, "amount", None) or getattr(r, "diligence_amount", None) or 0.0))
                break
    if cim_ebitda is not None or cim_revenue is not None:
        ebitda_rows = [
            ["Management EBITDA", _fmt_num(mgmt, money=True)],
            ["Diligence EBITDA", _fmt_num(dil, money=True)],
            ["CIM / investor workbook EBITDA", _fmt_num(cim_ebitda, money=True)],
        ]
        if dil is not None and cim_ebitda is not None:
            ebitda_rows.append(
                [
                    "CIM − diligence",
                    _fmt_num(float(cim_ebitda) - float(dil), money=True),
                ]
            )
        rev_rows: list[list[str]] = []
        if accounts_rev is not None or cim_revenue is not None:
            rev_rows.append(
                ["Revenue — management accounts", _fmt_num(accounts_rev, money=True)]
            )
            if other_rev_amt:
                rev_rows.append(
                    [
                        "Other revenue excluded by the CIM",
                        _fmt_num(-float(other_rev_amt), money=True),
                    ]
                )
                if accounts_rev is not None:
                    residual = float(accounts_rev) - float(other_rev_amt) - float(
                        cim_revenue or 0.0
                    )
                    rev_rows.append(
                        [
                            "Residual difference, unexplained",
                            _fmt_num(residual, money=True),
                        ]
                    )
            rev_rows.append(
                ["Revenue — CIM crosswalk", _fmt_num(cim_revenue, money=True)]
            )
        cim_delta = None
        if dil is not None and cim_ebitda is not None:
            cim_delta = float(cim_ebitda) - float(dil)
        slides.append(
            SlideSpec(
                slide_id="ch_qoe_cim",
                layout="section_table_obs",
                chapter="qoe",
                banner="QUALITY OF EARNINGS",
                headline=(
                    (
                        f"CIM EBITDA is {_fmt_num(cim_delta, money=True, prose=True)} "
                        f"{'above' if (cim_delta or 0) >= 0 else 'below'} diligence"
                        if cim_delta is not None
                        else "CIM vs diligence EBITDA"
                    )
                    + (
                        f"; CIM revenue excludes {_fmt_num(other_rev_amt, money=True, prose=True)} other revenue"
                        if other_rev_amt
                        else ""
                    )
                )[:180],
                table=SlideTable(
                    title=f"{period_label} EBITDA: management to diligence to CIM {scale_suffix()}",
                    headers=["View", "Amount"],
                    rows=ebitda_rows,
                ),
                observations=[
                    "CIM / investor-workbook figures are asserted until tied to accounts.",
                    *(
                        [
                            f"Accounts revenue {_fmt_num(accounts_rev, money=True, prose=True)} "
                            f"vs CIM {_fmt_num(cim_revenue, money=True, prose=True)}."
                        ]
                        if accounts_rev is not None and cim_revenue is not None
                        else []
                    ),
                    "Gross margin and SG&A may differ when the CIM reclassifies other revenue.",
                ][:6],
                source="QoE workbook; CIM / investor workbook crosswalk",
                evidence_tier="B/C",
                footnotes=[
                    " | ".join(f"{r[0]} {r[1]}" for r in rev_rows[:4]) if rev_rows else ""
                ],
            )
        )

    # ADJ cards — material / non-nil first (pairs of two), then pending shell.
    card_rows = [
        r
        for r in adj_rows
        if str(getattr(r, "adjustment_id", "") or "").upper().startswith(("ADJ", "A-"))
        and str(getattr(r, "treatment", "")) != "sensitivity"
    ]
    if card_rows:
        # Prefer ADJ-01/02 style cards with real amounts or explicit nil candidates.
        primary = [
            r
            for r in card_rows
            if abs(float(getattr(r, "management_amount", None) or 0.0)) > 1e-12
            or abs(float(getattr(r, "diligence_amount", None) or 0.0)) > 1e-12
            or str(getattr(r, "adjustment_id", "")).upper() in {"ADJ-01", "ADJ-02", "A-01", "A-02"}
        ]
        if not primary:
            primary = card_rows[:2]
        # Emit cards in pairs of two (Project Crew layout).
        pair = primary[:2]
        if len(primary) > 2:
            # First slide: first two with amounts; later nils on candidates slide.
            pair = primary[:2]
        ids = " and ".join(
            str(getattr(r, "adjustment_id", "") or "") for r in pair if getattr(r, "adjustment_id", None)
        )
        slides.append(
            SlideSpec(
                slide_id="ch_qoe_adj",
                layout="adj_detail",
                chapter="qoe",
                banner="QUALITY OF EARNINGS",
                headline=(
                    f"{ids}: "
                    + "; ".join(
                        (getattr(r, "difference_reason", None) or getattr(r, "label", "") or "")[:60]
                        for r in pair
                    )
                )[:180],
                adj_id=" / ".join(
                    str(getattr(r, "adjustment_id", "") or "") for r in pair
                ),
                adj_body="\n\n---\n\n".join(_qoe_adj_body(r) for r in pair),
                table=SlideTable(
                    title="Register amounts",
                    headers=["ID", "Mgmt", "Diligence", "Treatment"],
                    rows=[
                        [
                            str(getattr(r, "adjustment_id", "") or ""),
                            _fmt_num(getattr(r, "management_amount", None), money=True),
                            _fmt_num(getattr(r, "diligence_amount", None), money=True),
                            str(getattr(r, "treatment", "") or ""),
                        ]
                        for r in pair
                    ],
                ),
                observations=[
                    "Bridge treatments only; sensitivities stay outside diligence EBITDA.",
                    "Evidence status remains subject to G4 approval.",
                ],
                source="QoE workbook",
                evidence_tier="B",
            )
        )
        # Additional ADJ cards beyond the first pair (A-03… on worked example).
        rest = [
            r
            for r in card_rows
            if r not in pair
            and (
                abs(float(getattr(r, "management_amount", None) or 0.0)) > 1e-12
                or abs(float(getattr(r, "diligence_amount", None) or 0.0)) > 1e-12
            )
        ]
        for i in range(0, len(rest), 2):
            chunk = rest[i : i + 2]
            slides.append(
                SlideSpec(
                    slide_id=f"ch_qoe_adj_{i // 2 + 2}",
                    layout="adj_detail",
                    chapter="qoe",
                    banner="QUALITY OF EARNINGS",
                    headline=" / ".join(
                        str(getattr(r, "adjustment_id", "") or "") for r in chunk
                    )[:180],
                    adj_id=" / ".join(
                        str(getattr(r, "adjustment_id", "") or "") for r in chunk
                    ),
                    adj_body="\n\n---\n\n".join(_qoe_adj_body(r) for r in chunk),
                    table=SlideTable(
                        title="Register amounts",
                        headers=["ID", "Mgmt", "Diligence", "Treatment"],
                        rows=[
                            [
                                str(getattr(r, "adjustment_id", "") or ""),
                                _fmt_num(
                                    getattr(r, "management_amount", None), money=True
                                ),
                                _fmt_num(
                                    getattr(r, "diligence_amount", None), money=True
                                ),
                                str(getattr(r, "treatment", "") or ""),
                            ]
                            for r in chunk
                        ],
                    ),
                    observations=[
                        "Additional register items feeding (or excluded from) diligence EBITDA."
                    ],
                    source="QoE workbook",
                    evidence_tier="B/C",
                )
            )
    else:
        slides.append(
            SlideSpec(
                slide_id="ch_qoe_adj",
                layout="adj_detail",
                chapter="qoe",
                banner="QUALITY OF EARNINGS",
                headline="ADJ register empty — reported EBITDA shown unadjusted pending normalisations",
                adj_id="ADJ register (pending)",
                adj_body=(
                    "No material QoE adjustments have been booked for this run. "
                    "Diligence EBITDA equals reported EBITDA until the register is populated and G4-approved."
                ),
                observations=_held_obs(
                    chapter_title="QoE adjustments",
                    requests=requests
                    or ["Confirm one-off / non-recurring items for the closed year."],
                ),
                source="QoE workbook",
                evidence_tier="C",
            )
        )

    if nil_adj:
        rows = []
        for r in nil_adj[:8]:
            rows.append(
                [
                    str(getattr(r, "adjustment_id", "") or ""),
                    str(getattr(r, "label", "") or ""),
                    "Nil",
                    (getattr(r, "rationale", None) or "Pending evidence")[:80],
                ]
            )
        slides.append(
            SlideSpec(
                slide_id="ch_qoe_candidates",
                layout="section_table_obs",
                chapter="qoe",
                banner="QUALITY OF EARNINGS",
                headline=(
                    f"{nil_adj[0].adjustment_id} to {nil_adj[-1].adjustment_id} "
                    "considered at nil"
                    if len(nil_adj) > 1
                    else f"{nil_adj[0].adjustment_id} considered at nil"
                )[:180],
                table=SlideTable(
                    title="Candidates considered at nil",
                    headers=["ID", "Item", "Diligence view", "Notes"],
                    rows=rows,
                ),
                observations=[
                    "Nil candidates stay outside diligence EBITDA until evidence supports a treatment.",
                    *(requests[:2] if requests else []),
                ][:6],
                source="QoE workbook",
                evidence_tier="C",
            )
        )

    sens = list(getattr(qoe, "sensitivities", None) or []) if qoe else []
    if sens or getattr(qoe, "sensitivity_low", None) is not None:
        rows = []
        if dil is not None:
            rows.append(
                ["Diligence EBITDA", _fmt_num(dil, money=True), "Base"]
            )
        for s in sens[:8]:
            running = None
            if dil is not None and getattr(s, "amount", None) is not None:
                running = float(dil) + float(s.amount)
            rows.append(
                [
                    getattr(s, "label", None) or getattr(s, "sensitivity_id", "") or "",
                    _fmt_num(
                        running if running is not None else getattr(s, "amount", None),
                        money=True,
                    ),
                    getattr(s, "direction", "") or "",
                ]
            )
        if len(rows) <= 1 and getattr(qoe, "sensitivity_low", None) is not None:
            rows = [
                ["Diligence EBITDA", _fmt_num(dil, money=True), "Base"],
                [
                    "Sensitivity low",
                    _fmt_num(getattr(qoe, "sensitivity_low", None), money=True),
                    "downside",
                ],
                [
                    "Sensitivity high",
                    _fmt_num(getattr(qoe, "sensitivity_high", None), money=True),
                    "upside",
                ],
            ]
        slides.append(
            SlideSpec(
                slide_id="ch_qoe_sens",
                layout="section_table_obs",
                chapter="qoe",
                banner="QUALITY OF EARNINGS",
                headline=(
                    f"Judgemental items move {period_label} EBITDA between "
                    f"{_fmt_num(getattr(qoe, 'sensitivity_low', None), money=True, prose=True)} "
                    f"and {_fmt_num(getattr(qoe, 'sensitivity_high', None), money=True, prose=True)}; "
                    f"none enters diligence "
                    f"{_fmt_num(dil, money=True, prose=True)}"
                    if getattr(qoe, "sensitivity_low", None) is not None
                    else "Sensitivities remain outside diligence EBITDA"
                )[:180],
                table=SlideTable(
                    title=f"{period_label} sensitivities to diligence EBITDA {scale_suffix()}",
                    headers=["Case", "EBITDA", "Direction"],
                    rows=rows,
                ),
                observations=[
                    "Sensitivities are judgemental and do not enter diligence EBITDA.",
                    "Validate before using either case in price.",
                ],
                source="QoE workbook",
                evidence_tier="C",
            )
        )
    return slides


def plan_trading(
    *,
    commentary: CommentaryDoc | None,
    store: ExhibitStoreDoc,
    requests: list[str],
) -> list[SlideSpec]:
    from agetic_cdd_api.services_fdd_trading import (
        build_trading_pack,
        concentration_rows,
        cost_ratio_rows,
        ebitda_bridge_rows,
        stream_table_rows,
        ytd_compare_rows,
        _sga_ex_dep,
        _total_labour,
    )

    secs = _CHAPTER_SEC_SOURCES["trading"]
    draft_obs = _obs_from_drafts(commentary, secs)
    deal_slug = str(getattr(store, "deal_slug", None) or "")
    pack = build_trading_pack(deal_slug) if deal_slug else None

    # --- Condensed IS / margin (streams when extract has them) ---
    margin = None
    if pack is not None and pack.has_streams:
        ytd_years = sorted(
            {
                y
                for _lab, _fy, ytd in stream_table_rows(pack)
                for y in ytd
            }
        )
        headers = ["Metric", *[f"FY{y % 100:02d}" for y in pack.years]]
        for y in ytd_years:
            headers.append(f"YTD Jul-{y % 100:02d} ({pack.ytd_months}m)")
        rows: list[list[str]] = []
        for label, fy, ytd in stream_table_rows(pack):
            row = [label]
            for y in pack.years:
                row.append(_fmt_num(fy.get(y), money=True))
            for y in ytd_years:
                row.append(_fmt_num(ytd.get(y), money=True))
            rows.append(row)
            if label == "Gross profit":
                # Insert gross margin % after GP.
                gm_row = ["Gross margin"]
                for y in pack.years:
                    rev = pack.revenue_fy.get(y) or (pack.fy.get("Revenue") or {}).get(y)
                    gp = fy.get(y)
                    if rev is not None and gp is not None and abs(float(rev)) > 1e-12:
                        gm_row.append(_fmt_num(100.0 * float(gp) / float(rev), pct=True))
                    else:
                        gm_row.append("—")
                for y in ytd_years:
                    rev = (pack.ytd.get("Revenue") or {}).get(y)
                    gp = ytd.get(y)
                    if rev is not None and gp is not None and abs(float(rev)) > 1e-12:
                        gm_row.append(_fmt_num(100.0 * float(gp) / float(rev), pct=True))
                    else:
                        gm_row.append("—")
                rows.append(gm_row)
            if label == "EBITDA":
                em_row = ["EBITDA margin"]
                for y in pack.years:
                    rev = pack.revenue_fy.get(y) or (pack.fy.get("Revenue") or {}).get(y)
                    eb = fy.get(y)
                    if rev is not None and eb is not None and abs(float(rev)) > 1e-12:
                        em_row.append(_fmt_num(100.0 * float(eb) / float(rev), pct=True))
                    else:
                        em_row.append("—")
                for y in ytd_years:
                    rev = (pack.ytd.get("Revenue") or {}).get(y)
                    eb = ytd.get(y)
                    if rev is not None and eb is not None and abs(float(rev)) > 1e-12:
                        em_row.append(_fmt_num(100.0 * float(eb) / float(rev), pct=True))
                    else:
                        em_row.append("—")
                rows.append(em_row)
        # SG&A ex-dep row if available.
        sga_row = ["SG&A excluding depreciation"]
        any_sga = False
        for y in pack.years:
            val = _sga_ex_dep(pack, y)
            if val is not None:
                any_sga = True
            sga_row.append(_fmt_num(val, money=True))
        for y in ytd_years:
            val = (pack.ytd.get("SG&A (reported)") or {}).get(y)
            if val is not None:
                any_sga = True
            sga_row.append(_fmt_num(val, money=True))
        if any_sga:
            # Insert before EBITDA if present.
            insert_at = next(
                (i for i, r in enumerate(rows) if r[0] == "EBITDA"), len(rows)
            )
            rows.insert(insert_at, sga_row)
        margin = SlideTable(
            title=f"Condensed income statement {scale_suffix()}",
            headers=headers,
            rows=rows,
            basis=_ctx().basis_default,
            source="Monthly management accounts; Diligence analysis",
            evidence_tier="B",
        )
    if margin is None:
        margin = _period_table(
            store,
            exhibit_id=(
                "ex_m2_margin",
                "ex_m1_trading",
                "ex_db_is",
                "ex_db_metrics",
            ),
            metrics=[
                ("revenue", "Revenue", "money"),
                ("gross_margin", "Gross margin %", "pct"),
                ("ebitda", "EBITDA", "money"),
                ("ebitda_margin", "EBITDA margin %", "pct"),
                ("gross_margin_delta_pp", "Gross margin Δpp", "num"),
                ("ebitda_margin_delta_pp", "EBITDA margin Δpp", "num"),
            ],
            title="Revenue and margin",
        )

    obs = _clean_draft_obs(list(draft_obs))
    gm25 = None
    em25 = None
    if pack is not None:
        rev25 = pack.revenue_fy.get(2025) or (pack.fy.get("Revenue") or {}).get(2025)
        gp25 = (pack.fy.get("Gross profit") or {}).get(2025)
        eb25 = (pack.fy.get("EBITDA") or {}).get(2025)
        sga25 = _sga_ex_dep(pack, 2025)
        if rev25 and gp25 is not None and abs(float(rev25)) > 1e-12:
            gm25 = 100.0 * float(gp25) / float(rev25)
        if rev25 and eb25 is not None and abs(float(rev25)) > 1e-12:
            em25 = 100.0 * float(eb25) / float(rev25)
        if gm25 is not None and sga25 is not None and rev25:
            sga_pct = 100.0 * float(sga25) / float(rev25)
            obs.insert(
                0,
                f"Gross margin held at {_fmt_num(gm25, pct=True)} in FY25 but SG&A rose to "
                f"{_fmt_num(sga_pct, pct=True)} of revenue, cutting the EBITDA margin to "
                f"{_fmt_num(em25, pct=True)}."
                if em25 is not None
                else f"Gross margin {_fmt_num(gm25, pct=True)} in FY25.",
            )
    if not obs:
        gm_d = _metric(store, "ex_m2_margin", "gross_margin_delta_pp", 2025)
        em_d = _metric(store, "ex_m2_margin", "ebitda_margin_delta_pp", 2025)
        if gm_d is not None:
            obs.append(f"Gross margin moved {_fmt_num(gm_d)} pp year on year.")
        if em_d is not None:
            obs.append(f"EBITDA margin moved {_fmt_num(em_d)} pp year on year.")
    if not obs:
        obs = _held_obs(chapter_title="Trading", requests=requests)

    if gm25 is None:
        gm25 = _metric(store, ("ex_m2_margin", "ex_m1_trading"), "gross_margin", 2025)
    if em25 is None:
        em25 = _metric(store, ("ex_m2_margin", "ex_m1_trading"), "ebitda_margin", 2025)
    headline = (
        f"Gross margin {_fmt_num(gm25, pct=True)} with EBITDA margin {_fmt_num(em25, pct=True)} in FY25"
        if gm25 is not None
        else (obs[0] if obs else "Historical trading")
    )

    slides: list[SlideSpec] = [
        SlideSpec(
            slide_id="ch_trading_margin",
            layout="section_table_obs",
            chapter="trading",
            banner="TRADING",
            headline=headline[:180],
            table=margin
            or SlideTable(
                title="Trading summary",
                headers=["Metric", "Status"],
                rows=[["Revenue / margin", "Pending exhibits"]],
            ),
            observations=obs[:6],
            source="Monthly management accounts; Approved databook exhibits (M1/M2)",
            evidence_tier="B",
            figure_ids=["ex_m2_margin", "ex_m1_trading"],
        )
    ]

    # --- Concentration / mix ---
    conc = concentration_rows(pack, year=2025) if pack is not None else []
    if conc:
        muni_share = next((v for lab, v, k in conc if "Municipal share" in lab), None)
        # Prefer the top-contract share — not the municipal channel share.
        dc_share = next(
            (
                v
                for lab, v, k in conc
                if "share of total revenue" in lab.lower()
                and "municipal share" not in lab.lower()
            ),
            None,
        )
        contract_lab = (
            (pack.top_contract_label if pack is not None else None)
            or "Largest evidenced contract"
        )
        mix_headline = (
            f"Municipal is {_fmt_num(muni_share, pct=True)} of FY25 revenue"
            + (
                f"; {contract_lab} alone is {_fmt_num(dc_share, pct=True)}"
                if dc_share is not None
                else ""
            )
            if muni_share is not None
            else "Revenue concentration indicators for FY25"
        )
        mix_rows = []
        for lab, val, kind in conc:
            if kind == "pct":
                mix_rows.append([lab, _fmt_num(val, pct=True)])
            else:
                mix_rows.append([lab, _fmt_num(val, money=True)])
        # Stream mix mini-table as observations support — primary table is indicators.
        stream_obs = []
        if pack is not None:
            rev = pack.revenue_fy.get(2025)
            for label in ("Residential", "Municipal", "Commercial"):
                amt = (pack.fy.get(label) or {}).get(2025)
                if amt is not None and rev is not None and abs(float(rev)) > 1e-12:
                    stream_obs.append(
                        f"{label} {_fmt_num(amt, money=True, prose=True)} "
                        f"({_fmt_num(100.0 * float(amt) / float(rev), pct=True)})."
                    )
        if pack is not None and pack.dc_billings is not None:
            stream_obs.append(
                f"Loss of {contract_lab} would remove about "
                f"{_fmt_num(pack.dc_billings, money=True, prose=True)} of annual revenue."
            )
        slides.append(
            SlideSpec(
                slide_id="ch_trading_mix",
                layout="section_table_obs",
                chapter="trading",
                banner="TRADING",
                headline=mix_headline[:180],
                table=SlideTable(
                    title="Concentration indicators",
                    headers=["Indicator", "FY25"],
                    rows=mix_rows,
                    basis=_ctx().basis_default,
                    source="Monthly management accounts; Investor workbook municipal / commercial schedules",
                    evidence_tier="B/C",
                ),
                observations=(stream_obs + _clean_draft_obs(list(draft_obs)))[:6]
                or [
                    "Contract term and renewal options remain a diligence ask.",
                ],
                source="Monthly management accounts; Investor workbook",
                evidence_tier="B/C",
                figure_ids=["ex_m1_trading"],
            )
        )
    else:
        slides.append(
            SlideSpec(
                slide_id="ch_trading_mix",
                layout="section_chart_obs",
                chapter="trading",
                banner="TRADING",
                headline="Revenue mix / concentration held — municipal and DC schedules not bridged",
                chart_title="Revenue by stream (pending)",
                observations=_held_obs(
                    chapter_title="Revenue concentration",
                    requests=requests
                    or [
                        "Provide municipal / DC / commercial / residential revenue split for FY23–FY25 and LTM."
                    ],
                ),
                source="Diligence analysis",
                evidence_tier="C",
            )
        )

    # --- EBITDA bridge + cost ratios ---
    bridge = ebitda_bridge_rows(pack) if pack is not None else []
    ratios = cost_ratio_rows(pack) if pack is not None else []
    if bridge or ratios:
        e24 = bridge[0][1] if bridge else None
        e25 = bridge[-1][1] if bridge else None
        delta = (
            float(e25) - float(e24)
            if e24 is not None and e25 is not None
            else None
        )
        gp_step = next((v for lab, v in bridge if lab.startswith("Gross profit")), None)
        bridge_headline = (
            f"FY25 EBITDA fell {_fmt_num(abs(delta), money=True, prose=True)}"
            if delta is not None and delta < 0
            else "FY25 EBITDA bridge"
        )
        if gp_step is not None and delta is not None and delta < 0:
            # Keep headline tight — cost detail belongs in observations.
            bridge_headline += (
                f" as cost growth outran gross profit of "
                f"{_fmt_num(gp_step, money=True, prose=True)}"
            )
        if bridge:
            b_rows = [
                [lab, _fmt_num(val, money=True)]
                for lab, val in bridge
            ]
            table = SlideTable(
                title=f"Reported EBITDA, FY24 to FY25 {scale_suffix()}",
                headers=["Bridge step", "Amount"],
                rows=b_rows,
                basis=_ctx().basis_default,
                source="Monthly management accounts; Diligence analysis",
                evidence_tier="B",
            )
        else:
            # Ratios-only fallback.
            cols = list(ratios[0][1].keys()) if ratios else ["FY25"]
            table = SlideTable(
                title="Cost ratios (% of revenue)",
                headers=["% of revenue", *cols],
                rows=[
                    [lab, *[_fmt_num(cols_map.get(c), pct=True) for c in cols]]
                    for lab, cols_map in ratios
                ],
            )
        lab25 = _total_labour(pack, 2025) if pack is not None else None
        lab24 = _total_labour(pack, 2024) if pack is not None else None
        bridge_obs = _clean_draft_obs(list(draft_obs))
        if lab24 is not None and lab25 is not None and abs(float(lab24)) > 1e-12:
            lab_yoy = 100.0 * (float(lab25) - float(lab24)) / float(lab24)
            bridge_obs.insert(
                0,
                f"Labour grew {_fmt_num(lab_yoy, pct=True)} to "
                f"{_fmt_num(lab25, money=True, prose=True)}, faster than revenue.",
            )
        if ratios and bridge:
            # Append ratio snapshot as footnote-style obs.
            fy25_eb = next(
                (
                    cols.get("FY25")
                    for lab, cols in ratios
                    if lab.startswith("Reported EBITDA")
                ),
                None,
            )
            if fy25_eb is not None:
                bridge_obs.append(
                    f"Reported EBITDA margin {_fmt_num(fy25_eb, pct=True)} in FY25."
                )
        slides.append(
            SlideSpec(
                slide_id="ch_trading_bridge",
                layout="section_table_obs",
                chapter="trading",
                banner="TRADING",
                headline=bridge_headline[:180],
                table=table,
                observations=bridge_obs[:6]
                or ["Cost step-ups versus gross profit in the closed year."],
                source="Monthly management accounts; Diligence analysis",
                evidence_tier="B",
                figure_ids=["ex_m3_costs", "ex_m1_trading"],
                footnotes=[
                    "Cost ratios: "
                    + "; ".join(
                        f"{lab} FY25 {_fmt_num(cols.get('FY25'), pct=True)}"
                        for lab, cols in ratios[:3]
                    )
                ]
                if ratios and bridge
                else None,
            )
        )
    else:
        costs = _period_table(
            store,
            exhibit_id=(
                "ex_m3_costs",
                "ex_db_costs",
                "ex_m1_trading",
                "ex_db_is",
                "ex_db_metrics",
            ),
            metrics=[
                ("revenue", "Revenue (cost basis)", "money"),
                ("labor_cost", "Labour", "money"),
                ("labor_pct_revenue", "Labour % revenue", "pct"),
                ("sga", "SG&A", "money"),
                ("sga_pct_revenue", "SG&A % revenue", "pct"),
                ("sga_yoy", "SG&A YoY %", "pct"),
                ("labor_yoy", "Labour YoY %", "pct"),
            ],
            title="Costs and people",
        )
        if costs is not None:
            slides.append(
                SlideSpec(
                    slide_id="ch_trading_costs",
                    layout="section_table_obs",
                    chapter="trading",
                    banner="TRADING",
                    headline="Cost intensity: labour and SG&A versus revenue",
                    table=costs,
                    observations=[
                        "Ask management which FY25 cost step-ups are structural vs one-off.",
                    ],
                    source="Approved databook exhibits (M3)",
                    evidence_tier="B",
                    figure_ids=["ex_m3_costs"],
                )
            )

    # --- YTD Jul-25 vs Jul-26 ---
    ytd_rows = (
        ytd_compare_rows(pack, prior_year=2025, later_year=2026)
        if pack is not None
        else []
    )
    if ytd_rows:
        rev = next((r for r in ytd_rows if r[0] == "Revenue"), None)
        eb = next((r for r in ytd_rows if r[0] == "EBITDA"), None)
        res = next((r for r in ytd_rows if r[0] == "Residential"), None)
        com = next((r for r in ytd_rows if r[0] == "Commercial"), None)
        muni = next((r for r in ytd_rows if r[0] == "Municipal"), None)
        ytd_headline = "Current trading: YTD Jul-26 against YTD Jul-25"
        if rev is not None and rev[4] is not None:
            ytd_headline = (
                f"YTD Jul-26 ({pack.ytd_months}m) revenue is "
                f"{'up' if rev[4] >= 0 else 'down'} {_fmt_num(abs(rev[4]), pct=True)}"
            )
            if eb is not None and eb[4] is not None:
                ytd_headline += (
                    f" but reported EBITDA is "
                    f"{'up' if eb[4] >= 0 else 'down'} {_fmt_num(abs(eb[4]), pct=True)}"
                )
            if (
                res is not None
                and com is not None
                and (res[3] or 0) < 0
                and (com[3] or 0) < 0
            ):
                ytd_headline += "; commercial and residential revenue fell"
        table_rows = []
        for lab, a, b, chg, pct in ytd_rows:
            # ytd_compare_rows already returns percent points — do not re-scale.
            if pct is not None:
                pct_txt = f"{float(pct):,.1f}%"
            else:
                pct_txt = "—"
            # Round sub-$0.5k changes to 0 so near-flat GP does not print as 0.38.
            chg_show = chg
            if chg is not None and abs(float(chg)) < 0.0005:  # <$0.5k in $m store scale
                chg_show = 0.0
                if pct is not None and abs(float(pct)) < 0.05:
                    pct_txt = "0.0%"
            table_rows.append(
                [
                    lab,
                    _fmt_num(a, money=True),
                    _fmt_num(b, money=True),
                    _fmt_num(chg_show, money=True),
                    pct_txt,
                ]
            )
        ytd_obs = _clean_draft_obs(list(draft_obs))
        if muni is not None and muni[3] is not None and muni[3] > 0:
            ytd_obs.insert(
                0,
                f"Municipal (+{_fmt_num(muni[3], money=True, prose=True)}) carries the year.",
            )
        if (
            res is not None
            and com is not None
            and res[3] is not None
            and com[3] is not None
        ):
            combined = float(res[3]) + float(com[3])
            ytd_obs.append(
                f"Residential and commercial together moved "
                f"{_fmt_num(combined, money=True, prose=True)}."
            )
        slides.append(
            SlideSpec(
                slide_id="ch_trading_ytd",
                layout="section_table_obs",
                chapter="trading",
                banner="TRADING",
                headline=ytd_headline[:180],
                table=SlideTable(
                    title=(
                        f"Current trading: YTD Jul-26 ({pack.ytd_months}m) against "
                        f"YTD Jul-25 ({pack.ytd_months}m) {scale_suffix()}"
                    ),
                    headers=[
                        "Metric",
                        f"YTD Jul-25 ({pack.ytd_months}m)",
                        f"YTD Jul-26 ({pack.ytd_months}m)",
                        "Change",
                        "Change %",
                    ],
                    rows=table_rows,
                    basis=_ctx().basis_default,
                    source="Monthly management accounts; Diligence analysis",
                    evidence_tier="B",
                ),
                observations=ytd_obs[:6],
                source="Monthly management accounts; Diligence analysis",
                evidence_tier="B",
                figure_ids=["ex_m1_trading", "ex_db_is"],
            )
        )

    return slides


def plan_cash(
    *,
    commentary: CommentaryDoc | None,
    store: ExhibitStoreDoc,
    requests: list[str],
) -> list[SlideSpec]:
    from agetic_cdd_api.services_fdd_chapter_depth import build_cash_bs_pack

    secs = _CHAPTER_SEC_SOURCES["cash"]
    draft_obs = _obs_from_drafts(commentary, secs)
    deal_slug = str(getattr(store, "deal_slug", None) or "")
    pack = build_cash_bs_pack(deal_slug) if deal_slug else None

    ocf = _metric(store, ("ex_m7_cash", "ex_db_cf"), "operating_cash_flow", 2025)
    fcf = _metric(store, "ex_m7_cash", "free_cash_flow", 2025)
    capex = _metric(store, ("ex_m7_cash", "ex_db_cf"), "capex", 2025)
    net_chg = _metric(store, ("ex_m7_cash", "ex_db_cf"), "net_change_in_cash", 2025)
    div25 = _metric(store, "ex_db_bs", "dividends", 2025)
    if pack is not None:
        ocf = pack.ocf.get(2025, ocf)
        capex = pack.capex.get(2025, capex)
        net_chg = pack.net_change_cash.get(2025, net_chg)
        if div25 is None:
            div25 = pack.dividends_payable.get(2025)
        if fcf is None and ocf is not None and capex is not None:
            fcf = float(ocf) - abs(float(capex))

    # Prefer extract-backed multi-period cash summary when pack has OCF.
    table = None
    if pack is not None and any(pack.ocf.get(y) is not None for y in pack.years):
        headers = ["Metric", *[f"FY{y % 100:02d}" for y in pack.years]]
        if pack.ocf.get("Jul-26") is not None:
            headers.append("YTD Jul-26 (7m)")
        keys = list(pack.years) + (
            ["Jul-26"] if pack.ocf.get("Jul-26") is not None else []
        )

        def _row(label: str, series: dict, *, signed: bool = False) -> list[str]:
            cells: list[str] = [label]
            for k in keys:
                val = series.get(k)
                if val is None:
                    cells.append("—")
                elif signed and float(val) < 0:
                    cells.append(_fmt_num(val, money=True))
                else:
                    cells.append(_fmt_num(val, money=True))
            return cells

        rows = [
            _row("Net income (loss)", pack.net_income),
            _row("Dividend accrual (P&L) added back", pack.dividend_accrual),
            _row("Depreciation", pack.depreciation),
        ]
        if any(pack.retained_earnings_adj.get(k) for k in keys):
            rows.append(_row("Retained earnings adjustment", pack.retained_earnings_adj))
        if any(pack.wc_movement.get(k) is not None for k in keys):
            rows.append(_row("Working capital movement", pack.wc_movement))
        rows.extend(
            [
                _row("Operating cash flow", pack.ocf),
                _row("Capital expenditure", pack.capex),
                _row("Free cash flow", pack.fcf),
            ]
        )
        if any(pack.loans_cf.get(k) is not None for k in keys):
            rows.append(_row("Loans drawn less repaid", pack.loans_cf))
        if any(
            pack.dividend_paid.get(k) is not None and abs(float(pack.dividend_paid[k])) > 1e-9
            for k in keys
        ):
            # Show cash dividends as outflows (negative); nil years as —.
            paid_signed = {
                k: (
                    -abs(float(v))
                    if v is not None and abs(float(v)) > 1e-9
                    else None
                )
                for k, v in pack.dividend_paid.items()
            }
            rows.append(_row("Dividends paid", paid_signed))
        if any(
            pack.equity_issued.get(k) is not None and abs(float(pack.equity_issued[k])) > 5e-4
            for k in keys
        ):
            rows.append(_row("Equity issued", pack.equity_issued))
        rows.append(_row("Net change in cash", pack.net_change_cash))
        rows.append(_row("Closing cash", pack.cash))
        # Conversion vs diligence / stripped EBITDA when LTM pack available.
        dil_by = {2024: None, 2025: None}
        try:
            from agetic_cdd_api.services_fdd_trading import build_trading_pack

            tpack = build_trading_pack(deal_slug) if deal_slug else None
            if tpack is not None:
                for y in (2024, 2025):
                    dil_by[y] = (tpack.fy.get("EBITDA") or {}).get(y)
        except Exception:
            pass
        conv_row = ["Operating cash flow / diligence EBITDA"]
        for k in keys:
            ocf_k = pack.ocf.get(k)
            dil_k = dil_by.get(k) if isinstance(k, int) else None
            if ocf_k is not None and dil_k is not None and abs(float(dil_k)) > 1e-12:
                conv_row.append(_fmt_num(100.0 * float(ocf_k) / float(dil_k), pct=True))
            else:
                conv_row.append("—")
        if any(c != "—" for c in conv_row[1:]):
            rows.append(conv_row)
        table = SlideTable(
            title=f"Cash flow summary {scale_suffix()}",
            headers=headers,
            rows=rows,
            basis=_ctx().basis_default,
            source="Monthly management accounts (SoCF)",
            evidence_tier="B",
        )
    if table is None:
        table = _period_table(
            store,
            exhibit_id=("ex_m7_cash", "ex_db_cf", "ex_db_is", "ex_m1_trading"),
            metrics=[
                ("operating_cash_flow", "Operating cash flow", "money"),
                ("capex", "Capex", "money"),
                ("free_cash_flow", "Free cash flow", "money"),
                ("net_change_in_cash", "Net change in cash", "money"),
                ("ebitda", "EBITDA (conversion)", "money"),
            ],
            title="Cash conversion and capex",
        )

    obs = _clean_draft_obs(list(draft_obs))
    if ocf is not None and capex is not None:
        obs.append(
            f"FY25 operating cash flow {_fmt_num(ocf, money=True, prose=True)} covered capex "
            f"of {_fmt_num(capex, money=True, prose=True)}."
        )
    paid25 = pack.dividend_paid.get(2025) if pack is not None else None
    loans25 = pack.loans_cf.get(2025) if pack is not None else None
    if paid25 is not None and loans25 is not None and net_chg is not None:
        obs.append(
            f"Cash dividends {_fmt_num(paid25, money=True, prose=True)} and net loan "
            f"{'repayments' if float(loans25) < 0 else 'draws'} "
            f"{_fmt_num(abs(float(loans25)), money=True, prose=True)} drove the "
            f"{_fmt_num(net_chg, money=True, prose=True)} cash change in FY25."
        )
    elif div25 is not None and net_chg is not None:
        obs.append(
            f"Dividends / financing drew cash; net change in cash "
            f"{_fmt_num(net_chg, money=True, prose=True)} in FY25."
        )
    if not obs:
        obs = _held_obs(chapter_title="Cash flow", requests=requests)

    div_headline = paid25 if paid25 is not None else div25
    if ocf is not None and net_chg is not None and div_headline is not None:
        headline = (
            f"FY25 operating cash flow of {_fmt_num(ocf, money=True, prose=True)} covered capex, "
            f"but loan repayments and {_fmt_num(div_headline, money=True, prose=True)} of dividends "
            f"drew cash down {_fmt_num(abs(float(net_chg)), money=True, prose=True)}"
            if float(net_chg) < 0
            else (
                f"FY25 OCF {_fmt_num(ocf, money=True, prose=True)}; "
                f"net cash change {_fmt_num(net_chg, money=True, prose=True)}"
            )
        )
    elif ocf is not None:
        headline = (
            f"FY25 OCF {_fmt_num(ocf, money=True, prose=True)} covered capex; "
            f"FCF {_fmt_num(fcf, money=True, prose=True)}"
        )
    else:
        headline = obs[0] if obs else "Cash flow"

    slides = [
        SlideSpec(
            slide_id="ch_cash_1",
            layout="section_table_obs",
            chapter="cash",
            banner="CASH FLOW",
            headline=headline[:180],
            table=table
            or SlideTable(
                title="Cash flow",
                headers=["Metric", "Status"],
                rows=[["Operating cash flow / FCF", "Pending exhibits"]],
            ),
            observations=obs[:6],
            source="Monthly management accounts; Approved databook exhibits (M7)",
            evidence_tier="B",
            figure_ids=["ex_m7_cash", "ex_db_cf"],
        )
    ]

    # Cash stock + USDA / capex second slide.
    cash22 = pack.cash.get(2022) if pack else None
    if cash22 is None and pack is not None:
        # Dec-22 may be fiscal_year 2022 on extract.
        cash22 = pack.cash.get(2022)
    # Ensure Dec-22 loaded — build_cash_bs_pack only did 2023-25; pull if needed.
    cash_jul = pack.cash.get("Jul-26") if pack else None
    cash25 = (
        (pack.cash.get(2025) if pack else None)
        or _metric(store, ("ex_m7_cash", "ex_m8_bs", "ex_m6_net_debt"), "cash", 2025)
    )
    # Backfill Dec-22 from extract when pack present.
    if pack is not None and cash22 is None and deal_slug:
        from agetic_cdd_api.services_fdd_chapter_depth import _fy_balance, _load_extract

        cash22 = _fy_balance(_load_extract(deal_slug), ("Cash",), 2022)

    cash_headers = ["Metric"]
    cash_keys: list[int | str] = []
    if cash22 is not None:
        cash_headers.append("Dec-22")
        cash_keys.append(2022)
    for y in (2023, 2024, 2025):
        cash_headers.append(f"Dec-{y % 100:02d}")
        cash_keys.append(y)
    if cash_jul is not None:
        cash_headers.append("Jul-26")
        cash_keys.append("Jul-26")

    def _cash_val(k: int | str) -> Any:
        if pack is None:
            return cash25 if k == 2025 else None
        if k == 2022:
            return cash22
        return pack.cash.get(k)

    cash_rows = [
        ["Cash", *[_fmt_num(_cash_val(k), money=True) for k in cash_keys]],
    ]
    if pack is not None and any(pack.capex.get(y) is not None for y in pack.years):
        capex_keys = list(pack.years)
        if pack.capex.get("Jul-26") is not None:
            capex_keys.append("Jul-26")
        capex_headers = ["Metric", *[f"FY{y % 100:02d}" if isinstance(y, int) else "YTD Jul-26" for y in capex_keys]]
        capex_row = ["Capital expenditure"]
        dep_row = ["Depreciation"]
        ratio_row = ["Capex / depreciation"]
        for y in capex_keys:
            c = pack.capex.get(y)
            d = pack.depreciation.get(y)
            capex_row.append(_fmt_num(c, money=True))
            dep_row.append(_fmt_num(d, money=True))
            if c is not None and d is not None and abs(float(d)) > 1e-12:
                ratio_row.append(f"{float(c) / abs(float(d)):.2f}x")
            else:
                ratio_row.append("—")
        capex_table = SlideTable(
            title=f"Capex {scale_suffix()}",
            headers=capex_headers,
            rows=[capex_row, dep_row, ratio_row],
        )
    else:
        capex_table = None

    cash_drop = None
    if cash22 is not None and cash_jul is not None:
        cash_drop = float(cash22) - float(cash_jul)
    usda = pack.usda_grant_m if pack else None
    usda_match = pack.usda_match_m if pack else None
    cash2_obs = _clean_draft_obs(list(draft_obs))
    if cash_drop is not None:
        cash2_obs.insert(
            0,
            f"Cash fell {_fmt_num(cash_drop, money=True, prose=True)} since Dec-22 "
            f"to {_fmt_num(cash_jul, money=True, prose=True)}.",
        )
    if usda is not None:
        cash2_obs.append(
            f"USDA grant about {_fmt_num(usda, money=True, prose=True)} cited in the CIM"
            + (
                f"; matching funds {_fmt_num(usda_match, money=True, prose=True)}"
                if usda_match is not None
                else " — matching schedule to confirm"
            )
            + "."
        )
        if pack is not None and any("recapture" in n.lower() for n in pack.notes):
            cash2_obs.append(
                "FPEP grant may be recaptured if matching funds are not spent; "
                "ownership changes can require USDA review."
            )
    elif requests:
        cash2_obs.append(_humanize_request_title(requests[0]))
    if not cash2_obs:
        cash2_obs = _held_obs(chapter_title="Cash stock / grants", requests=requests)

    if cash_drop is not None:
        cash2_headline = (
            f"Cash fell {_fmt_num(cash_drop, money=True, prose=True)} since Dec-22 "
            f"to {_fmt_num(cash_jul, money=True, prose=True)}"
        )
        if usda_match is not None:
            cash2_headline += (
                f"; the USDA grant needs {_fmt_num(usda_match, money=True, prose=True)} "
                "of matching funds"
            )
        elif usda is not None:
            cash2_headline += f"; USDA grant about {_fmt_num(usda, money=True, prose=True)}"
    else:
        cash2_headline = (
            f"Cash {_fmt_num(cash_jul or cash25, money=True, prose=True)} "
            "with capex and grant match diligence open"
        )

    slides.append(
        SlideSpec(
            slide_id="ch_cash_2",
            layout="section_table_obs",
            chapter="cash",
            banner="CASH FLOW",
            headline=cash2_headline[:180],
            table=SlideTable(
                title=f"Cash at period end {scale_suffix()}",
                headers=cash_headers,
                rows=cash_rows,
                basis=_ctx().basis_default,
                source="Monthly management accounts",
                evidence_tier="B",
            ),
            observations=cash2_obs[:6],
            footnotes=[
                (
                    f"Capex FY25 {_fmt_num(pack.capex.get(2025), money=True, prose=True)}; "
                    f"depreciation {_fmt_num(pack.depreciation.get(2025), money=True, prose=True)}."
                    if pack is not None
                    else ""
                ),
                *(
                    [
                        " | ".join(
                            f"{r[0]} "
                            + " / ".join(r[1:])
                            for r in (capex_table.rows if capex_table else [])
                        )
                    ]
                    if capex_table
                    else []
                ),
            ],
            source="Monthly management accounts; CIM (USDA)",
            evidence_tier="B/C",
            figure_ids=["ex_m7_cash", "ex_m6_net_debt"],
        )
    )
    return slides


def plan_bs(
    *,
    commentary: CommentaryDoc | None,
    store: ExhibitStoreDoc,
    requests: list[str],
) -> list[SlideSpec]:
    from agetic_cdd_api.services_fdd_chapter_depth import build_cash_bs_pack

    secs = _CHAPTER_SEC_SOURCES["bs"]
    draft_obs = _clean_draft_obs(_obs_from_drafts(commentary, secs))
    slides: list[SlideSpec] = []
    deal_slug = str(getattr(store, "deal_slug", None) or "")
    pack = build_cash_bs_pack(deal_slug) if deal_slug else None

    nd_cash = _metric(store, "ex_m6_net_debt", "cash", 2025)
    nd_debt = _metric(store, "ex_m6_net_debt", "gross_debt", 2025)
    nd_net = _metric(store, "ex_m6_net_debt", "net_debt", 2025)
    div25 = _metric(store, "ex_db_bs", "dividends", 2025)
    equity = _metric(store, ("ex_m8_bs", "ex_db_bs"), "total_equity", 2025)
    if pack is not None:
        nd_cash = pack.cash.get(2025, nd_cash)
        if div25 is None:
            div25 = pack.dividends_payable.get(2025)
        jul_div = pack.dividends_payable.get("Jul-26")
        jul_cash = pack.cash.get("Jul-26")
    else:
        jul_div = None
        jul_cash = None

    # --- 1) Summary BS ---
    asof_years = [2023, 2024, 2025]
    headers = ["Metric", "Dec-23", "Dec-24", "Dec-25"]
    keys: list[int | str] = list(asof_years)
    if pack is not None and pack.cash.get("Jul-26") is not None:
        headers.append("Jul-26")
        keys.append("Jul-26")

    def _series_row(label: str, series: dict | None, fallback: Any = None) -> list[str]:
        row = [label]
        for k in keys:
            val = (series or {}).get(k) if series is not None else None
            if val is None and k == 2025 and fallback is not None:
                val = fallback
            row.append(_fmt_num(val, money=True))
        return row

    if pack is not None and any(pack.cash.get(y) is not None for y in asof_years):
        bs_rows = [
            _series_row("Cash", pack.cash, nd_cash),
            _series_row("Accounts receivable", pack.ar),
            _series_row("Inventory", pack.inventory),
            _series_row("Prepaid and other current assets", pack.prepaid),
            _series_row("Accounts payable", pack.ap),
            _series_row("Dividends payable", pack.dividends_payable, div25),
            _series_row(
                "Financial debt (Vehicle + SBA)",
                pack.financial_debt or pack.loans_payable,
                nd_debt,
            ),
        ]
        # Drop empty rows.
        bs_rows = [r for r in bs_rows if any(c != "—" for c in r[1:])]
        cash_now = jul_cash if jul_cash is not None else nd_cash
        debt_now = (
            (pack.financial_debt or pack.loans_payable).get("Jul-26")
            or (pack.financial_debt or pack.loans_payable).get(2025)
            or nd_debt
        )
        slides.append(
            SlideSpec(
                slide_id="ch_bs_summary",
                layout="section_table_obs",
                chapter="bs",
                banner="BALANCE SHEET, DEBT AND LEASES",
                headline=(
                    f"Cash of {_fmt_num(cash_now, money=True, prose=True)} is the largest liquid asset"
                    + (
                        f"; financial debt {_fmt_num(debt_now, money=True, prose=True)}"
                        if debt_now is not None
                        else ""
                    )
                )[:180],
                table=SlideTable(
                    title=f"Summary balance sheet {scale_suffix()}",
                    headers=headers,
                    rows=bs_rows,
                    basis=_ctx().basis_default,
                    source="Monthly management accounts",
                    evidence_tier="B",
                ),
                observations=draft_obs[:3]
                or [
                    "Balances from unaudited monthly management accounts.",
                    "Financial debt = Vehicle Loans + State & Fed (SBA) loans payable.",
                    "Tie-outs to cash flow deepen when monthly BS is fully bridged.",
                ],
                source="Monthly management accounts",
                evidence_tier="B",
                figure_ids=["ex_m8_bs", "ex_db_bs"],
            )
        )

    # --- 2) Net debt / debt-like ---
    debt_table = _period_table(
        store,
        exhibit_id=("ex_m6_net_debt", "ex_db_bs", "ex_m8_bs", "ex_db_metrics"),
        metrics=[
            ("cash", "Freely available cash", "money"),
            ("gross_debt", "Gross interest-bearing debt", "money"),
            ("net_debt", "Net debt / (cash)", "money"),
            ("dividends", "Dividends payable (proposed debt-like)", "money"),
            ("total_equity", "Total shareholders' equity", "money"),
        ],
        title="Net debt and debt-like items",
    )
    if pack is not None and (nd_cash is not None or div25 is not None):
        d_headers = ["Metric", *[f"Dec-{y % 100:02d}" for y in asof_years]]
        d_keys: list[int | str] = list(asof_years)
        debt_series = pack.financial_debt or pack.loans_payable
        jul_debt = debt_series.get("Jul-26")
        if jul_cash is not None or jul_div is not None or jul_debt is not None:
            d_headers.append("Jul-26")
            d_keys.append("Jul-26")
        debt_rows = [
            ["Cash", *[_fmt_num(pack.cash.get(k), money=True) for k in d_keys]],
            [
                "Financial debt (Vehicle + SBA)",
                *[
                    _fmt_num(
                        debt_series.get(k)
                        if k != 2025
                        else (debt_series.get(k) or nd_debt),
                        money=True,
                    )
                    for k in d_keys
                ],
            ],
            [
                "Dividends payable (proposed debt-like)",
                *[
                    _fmt_num(
                        pack.dividends_payable.get(k)
                        if k != 2025
                        else (pack.dividends_payable.get(k) or div25),
                        money=True,
                    )
                    for k in d_keys
                ],
            ],
        ]
        if nd_net is not None or jul_debt is not None:
            net_row = ["Net debt / (cash)"]
            after_row = ["Net debt / (cash) after debt-like"]
            for k in d_keys:
                cash_k = pack.cash.get(k) if k != 2025 else (pack.cash.get(k) or nd_cash)
                debt_k = debt_series.get(k)
                if k == 2025:
                    debt_k = debt_k if debt_k is not None else nd_debt
                elif k == "Jul-26":
                    debt_k = jul_debt if jul_debt is not None else nd_debt
                    cash_k = jul_cash if jul_cash is not None else cash_k
                div_k = pack.dividends_payable.get(k)
                if k == 2025 and div_k is None:
                    div_k = div25
                if k == 2025 and nd_net is not None:
                    net_row.append(_fmt_num(nd_net, money=True))
                elif cash_k is not None and debt_k is not None:
                    net_row.append(_fmt_num(float(debt_k) - float(cash_k), money=True))
                else:
                    net_row.append("—")
                if cash_k is not None and debt_k is not None and div_k is not None:
                    after_row.append(
                        _fmt_num(
                            float(debt_k) + float(div_k) - float(cash_k),
                            money=True,
                        )
                    )
                else:
                    after_row.append("—")
            debt_rows.append(net_row)
            if any(c != "—" for c in after_row[1:]):
                debt_rows.append(after_row)
        debt_table = SlideTable(
            title=f"Net debt and debt-like items {scale_suffix()}",
            headers=d_headers,
            rows=debt_rows,
            basis=_ctx().basis_default,
            source="Monthly management accounts; M6 net debt",
            evidence_tier="B",
        )
    elif debt_table is None:
        debt_table = SlideTable(
            title=f"Net debt and debt-like items {scale_suffix()}",
            headers=["Item", "FY25"],
            rows=[
                ["Freely available cash", _fmt_num(nd_cash, money=True)],
                ["Gross interest-bearing debt", _fmt_num(nd_debt, money=True)],
                ["Net debt / (cash)", _fmt_num(nd_net, money=True)],
                [
                    "Dividends payable (proposed debt-like)",
                    _fmt_num(div25, money=True) if div25 is not None else "Not evidenced",
                ],
                ["Total shareholders' equity", _fmt_num(equity, money=True)],
            ],
        )

    div_show = jul_div if jul_div is not None else div25
    debt_show = (
        (pack.financial_debt or pack.loans_payable).get("Jul-26")
        if pack is not None
        else None
    )
    if debt_show is None and pack is not None:
        debt_show = (pack.financial_debt or pack.loans_payable).get(2025)
    if debt_show is None:
        debt_show = nd_debt
    debt_headline = (
        f"Financial debt {_fmt_num(debt_show, money=True, prose=True)} vs cash "
        f"{_fmt_num(jul_cash or nd_cash, money=True, prose=True)}"
        if debt_show is not None
        else f"Net debt {_fmt_num(nd_net, money=True, prose=True)}"
    )
    if div_show is not None:
        debt_headline += (
            f"; accrued dividends of {_fmt_num(div_show, money=True, prose=True)} "
            "proposed debt-like"
        )
    slides.append(
        SlideSpec(
            slide_id="ch_bs_net_debt",
            layout="section_table_obs",
            chapter="bs",
            banner="BALANCE SHEET, DEBT AND LEASES",
            headline=debt_headline[:180],
            table=debt_table,
            observations=[
                "Proposed: accrued cumulative dividends are debt-like; operating payables stay in NWC.",
                *draft_obs[:2],
            ][:6],
            source="Approved databook exhibits (M6/M8); Dividends payable from BS",
            evidence_tier="B",
            figure_ids=["ex_m6_net_debt", "ex_db_bs", "ex_m8_bs"],
        )
    )

    # --- 3) Leases ---
    rent = pack.rent_fy25 if pack is not None else None
    lease_evidenced = pack.evidenced_lease_rent_m if pack is not None else None
    lease_label = (
        (pack.evidenced_lease_label or "Lease in data room")
        if pack is not None
        else "Lease in data room"
    )
    uncovered = None
    if rent is not None and lease_evidenced is not None:
        uncovered = max(0.0, float(rent) - float(lease_evidenced))
    lease_rows = [
        [
            "Rent expense FY25",
            _fmt_num(rent, money=True) if rent is not None else "—",
            "Management accounts",
        ],
        [
            f"Evidenced lease rent ({lease_label})" if lease_evidenced is not None else "Lease files in data room",
            _fmt_num(lease_evidenced, money=True) if lease_evidenced is not None else "Amount not parsed",
            "Lease PDF" if lease_evidenced is not None else "Data room",
        ],
        [
            "Rent not covered by a lease in the data room",
            _fmt_num(uncovered, money=True) if uncovered is not None else "Unknown — open request",
            "Calculation" if uncovered is not None else "Pending lease schedule",
        ],
        ["ASC 842 ROU / lease liability", "Not recorded", "Management accounts"],
        ["Lease schedule (all sites)", "Missing — open request", "Information request"],
    ]
    if rent is not None and lease_evidenced is not None and float(rent) > 1e-12:
        frac = 100.0 * float(lease_evidenced) / float(rent)
        lease_headline = (
            f"Only {_fmt_num(frac, pct=True)} of FY25 rent of "
            f"{_fmt_num(rent, money=True, prose=True)} is backed by a lease in the data room; "
            "commitments are unknown"
        )
    elif rent is not None:
        lease_headline = (
            f"FY25 rent of {_fmt_num(rent, money=True, prose=True)} "
            "has limited lease-file backing; commitments are unknown"
        )
    else:
        lease_headline = (
            "Lease commitments largely unevidenced — rent may be expensed with no ROU / liability"
        )
    slides.append(
        SlideSpec(
            slide_id="ch_bs_leases",
            layout="section_table_obs",
            chapter="bs",
            banner="BALANCE SHEET, DEBT AND LEASES",
            headline=lease_headline[:180],
            table=SlideTable(
                title="Lease and commitment evidence",
                headers=["Item", "Amount", "Source"],
                rows=lease_rows,
            ),
            observations=_held_obs(
                chapter_title="Leases and commitments",
                requests=requests
                or [
                    "R05: Schedule of all leases and site agreements with term, rent and termination rights"
                ],
            ),
            source="Diligence analysis; lease PDF if present",
            evidence_tier="A/C",
        )
    )

    # --- 4) NWC ---
    nwc = _metric(store, "ex_m5_nwc", "nwc", 2025)
    ar = _metric(store, "ex_m5_nwc", "accounts_receivable", 2025)
    inv = _metric(store, "ex_m5_nwc", "inventory", 2025)
    ap = _metric(store, "ex_m5_nwc", "accounts_payable", 2025)
    if pack is not None:
        ar = pack.ar.get(2025, ar)
        inv = pack.inventory.get(2025, inv)
        ap = pack.ap.get(2025, ap)
        if nwc is None and ar is not None and ap is not None:
            nwc = float(ar) + float(inv or 0.0) - abs(float(ap))
    nwc_table = None
    if pack is not None and any(pack.ar.get(y) is not None for y in asof_years):
        nwc_table = SlideTable(
            title=f"Trade working capital {scale_suffix()}",
            headers=headers,
            rows=[
                _series_row("Accounts receivable", pack.ar, ar),
                _series_row("Inventory", pack.inventory, inv),
                _series_row("Prepaid and other current assets", pack.prepaid),
                _series_row("Accounts payable", pack.ap, ap),
            ],
            basis=_ctx().basis_default,
            source="Monthly management accounts; M5",
            evidence_tier="B",
        )
    if nwc_table is None:
        nwc_table = _period_table(
            store,
            exhibit_id=("ex_m5_nwc", "ex_db_bs", "ex_db_metrics"),
            metrics=[
                ("accounts_receivable", "Accounts receivable", "money"),
                ("inventory", "Inventory", "money"),
                ("accounts_payable", "Accounts payable", "money"),
                ("nwc", "Net working capital", "money"),
            ],
            title="Trade working capital",
        ) or SlideTable(
            title=f"Trade working capital {scale_suffix()}",
            headers=["Component", "FY25"],
            rows=[
                ["Accounts receivable", _fmt_num(ar, money=True)],
                ["Inventory", _fmt_num(inv, money=True)],
                ["Accounts payable", _fmt_num(ap, money=True)],
                ["Net working capital", _fmt_num(nwc, money=True)],
            ],
        )
    ar23 = pack.ar.get(2023) if pack is not None else None
    ar25 = pack.ar.get(2025) if pack is not None else ar
    nwc_headline = f"Trade working capital {_fmt_num(nwc, money=True, prose=True)} at FY25; no peg is proposed"
    if ar23 is not None and ar25 is not None and abs(float(ar23)) > 1e-12:
        ar_growth = 100.0 * (float(ar25) - float(ar23)) / abs(float(ar23))
        nwc_headline = (
            f"Trade working capital {_fmt_num(nwc, money=True, prose=True)} at FY25 "
            f"as receivables grew {_fmt_num(ar_growth, pct=True)} since Dec-23; no peg is proposed"
        )
    slides.append(
        SlideSpec(
            slide_id="ch_bs_nwc",
            layout="section_table_obs",
            chapter="bs",
            banner="BALANCE SHEET, DEBT AND LEASES",
            headline=nwc_headline[:180],
            table=nwc_table,
            observations=[
                "No peg proposed without an audited year-end reconciliation.",
                "Request ageing and a reconciled monthly NWC series before SPA peg mechanics.",
            ],
            source="Approved databook exhibits (M5)",
            evidence_tier="B",
            figure_ids=["ex_m5_nwc"],
            footnotes=["Rule applied: no NWC peg without audited year-end tie-out."],
        )
    )

    # --- 5) Equity / dividend roll ---
    eq_headers = ["Metric", "FY23", "FY24", "FY25"]
    eq_keys: list[int | str] = [2023, 2024, 2025]
    if pack is not None and (
        pack.net_income.get("Jul-26") is not None
        or pack.dividends_payable.get("Jul-26") is not None
    ):
        eq_headers.append("YTD Jul-26 (7m)")
        eq_keys.append("Jul-26")
    ni_row = ["Net income (loss)", *[_fmt_num((pack.net_income if pack else {}).get(k), money=True) for k in eq_keys]]
    div_acc = [
        "Dividend accrual through P&L",
        *[
            _fmt_num((pack.dividend_accrual if pack else {}).get(k), money=True)
            for k in eq_keys
        ],
    ]
    div_paid = [
        "Cash dividends paid",
        *[
            _fmt_num((pack.dividend_paid if pack else {}).get(k), money=True)
            for k in eq_keys
        ],
    ]
    div_pay = [
        "Closing dividends payable",
        *[
            _fmt_num(
                (pack.dividends_payable if pack else {}).get(k)
                if k != 2025
                else ((pack.dividends_payable if pack else {}).get(k) or div25),
                money=True,
            )
            for k in eq_keys
        ],
    ]
    eq_rows = [ni_row, div_acc]
    if pack is not None and any(
        pack.dividend_paid.get(k) is not None for k in eq_keys
    ):
        eq_rows.append(div_paid)
    eq_rows.append(div_pay)
    equity_series = pack.total_equity if pack is not None else {}
    if equity is not None and equity_series.get(2025) is None:
        equity_series = {**equity_series, 2025: equity}
    if any(equity_series.get(k) is not None for k in eq_keys):
        eq_rows.append(
            [
                "Total shareholders' equity",
                *[_fmt_num(equity_series.get(k), money=True) for k in eq_keys],
            ]
        )
    eq25 = equity_series.get(2025, equity)
    paid_ytd = pack.dividend_paid.get("Jul-26") if pack is not None else None
    if div_show is not None and eq25 is not None:
        equity_headline = (
            f"Dividends payable {_fmt_num(div_show, money=True, prose=True)} "
            f"while equity stands at {_fmt_num(eq25, money=True, prose=True)} — treat arrears as debt-like"
        )
    elif div_show is not None:
        equity_headline = (
            f"Dividends payable {_fmt_num(div_show, money=True, prose=True)} "
            "while losses cut equity — treat arrears as debt-like"
        )
    else:
        equity_headline = "Equity and dividend roll — confirm cash leakage before funding"
    if paid_ytd is not None:
        # Prefer a cash-dividends led headline when YTD paid is evidenced and material.
        pass
    slides.append(
        SlideSpec(
            slide_id="ch_bs_equity",
            layout="section_table_obs",
            chapter="bs",
            banner="BALANCE SHEET, DEBT AND LEASES",
            headline=equity_headline[:180],
            table=SlideTable(
                title=f"Earnings and dividends payable roll {scale_suffix()}",
                headers=eq_headers,
                rows=eq_rows,
                basis=_ctx().basis_default,
                source="Monthly management accounts",
                evidence_tier="B",
            ),
            observations=[
                o
                for o in [
                    "Protect new money with a no-leakage covenant to closing and a bar on using proceeds for arrears.",
                    (
                        f"Total equity {_fmt_num(equity, money=True, prose=True)} on closed-year exhibits."
                        if equity is not None
                        else "Equity stock pending full BS bridge."
                    ),
                    (
                        f"YTD Jul-26 cash dividends paid "
                        f"{_fmt_num(pack.dividend_paid.get('Jul-26'), money=True, prose=True)}."
                        if pack is not None and pack.dividend_paid.get("Jul-26") is not None
                        else None
                    ),
                ]
                if o
            ],
            source="Monthly management accounts; Diligence analysis",
            evidence_tier="B",
            figure_ids=["ex_db_bs", "ex_m8_bs"],
        )
    )
    return slides


def plan_deal(
    *,
    findings: Any | None,
    request_list: Any | None,
    requests: list[str],
    claims: Any | None = None,
) -> list[SlideSpec]:
    from agetic_cdd_api.services_fdd_chapter_depth import chunked
    from agetic_cdd_api.services_fdd_findings import top_findings

    findings_list = top_findings(_high_mod_findings(findings), limit=10) or _high_mod_findings(
        findings
    )[:10]
    prot_rows: list[list[str]] = []
    ranked: list[FindingRankRow] = []
    for i, f in enumerate(findings_list, start=1):
        sev = _es_rating(getattr(getattr(f, "severity", None), "value", "") or "")
        title = getattr(f, "title", "") or "Item"
        ask = (getattr(f, "ask_management", None) or _es_protection(f))[:90]
        mechanism = "Closing condition / warranty" if sev == "High" else "Information rights / covenant"
        prot_rows.append([f"F{i}", title[:70], ask[:70], mechanism, sev])
        ranked.append(FindingRankRow(rank=f"F{i}", severity=sev, title=title, detail=ask))
    if not prot_rows:
        prot_rows = [["—", "No high/moderate protections mapped yet", "—", "—", "—"]]

    high_prot = sum(1 for r in prot_rows if r[-1] == "High")
    protections = SlideSpec(
        slide_id="ch_deal_protections",
        layout="findings_rank",
        chapter="deal",
        banner="DEAL CONSIDERATIONS",
        headline=(
            f"Protections map: {high_prot} high-priority items from diligence findings"
            if high_prot
            else f"Protections map: {len(ranked)} high/moderate items from diligence findings"
        ),
        findings=ranked,
        table=SlideTable(
            title="Protections map",
            headers=["Finding", "Protection or action", "Mechanism", "Priority"],
            rows=[[r[0] + " " + r[1], r[2], r[3], r[4]] for r in prot_rows],
        ),
        observations=[
            "Operational follow-ups kept separate from deal protections where possible.",
        ],
        source="Diligence analysis",
        evidence_tier="A/B",
    )

    req_items = list(getattr(request_list, "items", None) or [])
    # High when the gap blocks a material chapter, or is a closed-year claim on a
    # pricing/earnings metric. Forecast-year / appendix-only gaps stay Medium.
    _HIGH_BLOCK = {
        "SEC-A",
        "SEC-B",
        "SEC-C",
        "SEC-D",
        "SEC-E",
        "SEC-F",
        "SEC-G",
        "SEC-ES",
        "SEC-QOE",
        "SEC-TRADING",
    }
    _HIGH_METRICS = {
        "revenue",
        "ebitda",
        "gross_profit",
        "net_debt",
        "cash",
        "dividends",
        "gross_debt",
        "operating_cash_flow",
    }
    closed_fy = date.today().year - 1  # e.g. 2025 in 2026

    def _request_priority(item: Any) -> str:
        blocking = {str(x) for x in list(getattr(item, "blocking_sections", None) or [])}
        if blocking & _HIGH_BLOCK:
            return "High"
        metric = str(getattr(item, "metric_key", None) or "").lower()
        fy = getattr(item, "fiscal_year", None)
        try:
            fy_i = int(fy) if fy is not None else None
        except (TypeError, ValueError):
            fy_i = None
        if (
            getattr(item, "claim_id", None)
            and metric in _HIGH_METRICS
            and fy_i is not None
            and fy_i <= closed_fy
        ):
            return "High"
        sev = str(getattr(getattr(item, "severity", None), "value", "") or "").lower()
        if sev == "high":
            return "High"
        if blocking or getattr(item, "claim_id", None):
            return "Medium"
        return "Low"

    req_rows: list[list[str]] = []
    for i, item in enumerate(req_items, start=1):
        rid = getattr(item, "request_id", None) or f"R{i:02d}"
        rid_s = rid if str(rid).startswith("R") else f"R{i:02d}"
        blocking = [str(x) for x in list(getattr(item, "blocking_sections", None) or [])]
        why = (
            getattr(item, "detail", None)
            or getattr(item, "figure_impact", None)
            or "Diligence completeness"
        )[:70]
        affects = (
            ", ".join(blocking[:3])
            if blocking
            else (getattr(item, "metric_key", None) or "General")
        )
        req_rows.append(
            [
                rid_s if len(str(rid_s)) <= 8 else f"R{i:02d}",
                _humanize_request_title(
                    getattr(item, "title", None)
                    or getattr(item, "detail", None)
                    or "Request"
                )[:70],
                str(why)[:70],
                str(affects)[:40],
                _request_priority(item),
            ]
        )
    if not req_rows:
        synth = list(requests or [])
        if not synth:
            for f in findings_list[:12]:
                ask = getattr(f, "ask_management", None) or getattr(f, "title", None)
                if ask:
                    synth.append(str(ask))
        for i, hint in enumerate(
            synth or ["Supply missing schedules or confirm out of scope"], start=1
        ):
            req_rows.append(
                [
                    f"R{i:02d}",
                    _humanize_request_title(hint)[:70],
                    "Diligence completeness",
                    "General",
                    "High" if i <= max(1, min(len(findings_list), 4)) else "Medium",
                ]
            )

    # Deck budget: at most two request slides (~11 rows each). Rank High first.
    _prio_rank = {"High": 0, "Medium": 1, "Low": 2}
    req_rows.sort(key=lambda r: (_prio_rank.get(r[4], 9), r[0]))
    register_n = len(req_rows)
    req_rows = req_rows[:22]
    high_n = sum(1 for r in req_rows if r[4] == "High")
    total_n = len(req_rows)
    pages = chunked(req_rows, 11)
    slides = [protections]
    page_n = min(len(pages), 2)
    for pi, page_rows in enumerate(pages[:page_n], start=1):
        suffix = f" ({pi}/{page_n})" if page_n > 1 else ""
        slides.append(
            SlideSpec(
                slide_id=f"ch_deal_requests_{pi}",
                layout="request_table",
                chapter="deal",
                banner="DEAL CONSIDERATIONS",
                headline=(
                    f"{total_n} information requests, {high_n} high priority"
                    f"{suffix}"
                )[:180],
                table=SlideTable(
                    title=f"Information requests{suffix}",
                    headers=[
                        "Ref",
                        "Document or information requested",
                        "Why it matters",
                        "Affects",
                        "Priority",
                    ],
                    rows=page_rows,
                ),
                observations=[
                    "Close high-priority requests before relying on unadjusted earnings.",
                    (
                        f"Register holds {register_n} requests; deck shows the top {total_n} by priority."
                        if register_n > total_n
                        else "Priorities follow material chapters and closed-year earnings claims."
                    ),
                ],
                source="Diligence analysis",
                evidence_tier="A/B",
            )
        )
    return slides


def plan_appendix(
    *,
    claims: Any | None,
    deal_slug: str | None = None,
) -> list[SlideSpec]:
    from agetic_cdd_api.services_fdd_chapter_depth import chunked, list_data_room_files

    claims_list = list(getattr(claims, "claims", None) or [])
    contradicted = [c for c in claims_list if getattr(c, "test_result", None) == "contradicted"]
    failed = [
        c
        for c in claims_list
        if getattr(c, "test_result", None) in {"contradicted", "unverifiable"}
        or getattr(c, "failed", False)
    ]
    # Prefer failed/contradicted first, then a sample of the rest for multi-page ledger.
    ordered = list(contradicted) + [c for c in failed if c not in contradicted]
    seen_ids = {id(c) for c in ordered}
    for c in claims_list:
        if id(c) not in seen_ids:
            ordered.append(c)
            seen_ids.add(id(c))
        if len(ordered) >= 36:
            break

    rows: list[list[str]] = []
    for i, c in enumerate(ordered, start=1):
        result = str(getattr(c, "test_result", None) or "")
        use = (
            "rejected"
            if result in {"contradicted", "unverifiable"} or getattr(c, "failed", False)
            else ("context only" if result == "agrees" else result or "pending")
        )
        rows.append(
            [
                f"C{i:02d}",
                str(getattr(c, "source_agent", None) or getattr(c, "metric_key", None) or "—")[:28],
                (getattr(c, "text", None) or "")[:70],
                (
                    f"{getattr(c, 'metric_key', '')} FY{getattr(c, 'fiscal_year', '')}".strip()
                    or "Databook / narrative"
                )[:40],
                result or "—",
                use,
            ]
        )
    if not rows:
        rows = [["—", "—", "No claims tested", "—", "empty", "—"]]

    agrees = getattr(claims, "agrees", None)
    contr_n = getattr(claims, "contradicted", None) or len(contradicted)
    total = getattr(claims, "claim_count", None) or len(claims_list)
    rejected_n = len(failed) if failed else contr_n
    claim_pages = chunked(rows, 12)
    slides: list[SlideSpec] = []
    n_claim_pages = min(len(claim_pages), 3)
    for pi, page_rows in enumerate(claim_pages[:3], start=1):
        suffix = f" ({pi}/{n_claim_pages})" if n_claim_pages > 1 else ""
        slides.append(
            SlideSpec(
                slide_id=f"ch_app_claims_{pi}",
                layout="ledger_table",
                chapter="appendix",
                banner="APPENDICES",
                headline=(
                    f"Claims ledger: {total} claims tested"
                    + (f", {rejected_n} rejected / failed" if rejected_n else "")
                    + (f", {agrees} agree" if agrees is not None else "")
                    + suffix
                )[:180],
                table=SlideTable(
                    title=f"Claims ledger{suffix}",
                    headers=["ID", "Agent module", "Claim as stated", "Tested against", "Result", "Use"],
                    rows=page_rows,
                ),
                source="Diligence analysis",
                evidence_tier="B",
            )
        )

    # Document register from VDR files.
    docs = list_data_room_files(deal_slug) if deal_slug else []
    doc_rows = [
        [d["id"], d["document"], d["subject"], d["basis"], d["period_end"], d["tier"], d["use"]]
        for d in docs
    ]
    if doc_rows:
        doc_pages = chunked(doc_rows, 12)
        n_doc = min(len(doc_pages), 3)
        for pi, page_rows in enumerate(doc_pages[:3], start=1):
            suffix = f" ({pi}/{n_doc})" if n_doc > 1 else ""
            slides.append(
                SlideSpec(
                    slide_id=f"ch_app_register_{pi}",
                    layout="ledger_table",
                    chapter="appendix",
                    banner="APPENDICES",
                    headline=(
                        f"Document register: {len(doc_rows)} entries covering data-room files"
                        + suffix
                    )[:180],
                    table=SlideTable(
                        title=f"Document register{suffix}",
                        headers=["ID", "Document", "Subject", "Basis", "Period end", "Tier", "Use"],
                        rows=page_rows,
                    ),
                    source="Data room register",
                    evidence_tier="A/B/C",
                )
            )

    inconsist_rows = []
    for c in contradicted[:12]:
        inconsist_rows.append(
            [
                f"{getattr(c, 'metric_key', '')} FY{getattr(c, 'fiscal_year', '')}".strip()
                or str(getattr(c, "claim_id", "")),
                f"Claimed {_fmt_num(getattr(c, 'claimed_value', None), money=True, prose=True)}",
                f"Databook {_fmt_num(getattr(c, 'databook_value', None), money=True, prose=True)} — reconcile before IC use",
            ]
        )
    if not inconsist_rows:
        inconsist_rows = [["None material", "—", "No contradicted claim pairs for appendix"]]
    slides.append(
        SlideSpec(
            slide_id="ch_app_inconsistencies",
            layout="section_table_obs",
            chapter="appendix",
            banner="APPENDICES",
            headline=(
                f"Source inconsistencies: {len(contradicted)} contradicted claim(s) vs approved databook"
                if contradicted
                else "Source inconsistencies — agent claims vs approved databook"
            )[:180],
            table=SlideTable(
                title="Source inconsistencies",
                headers=["Document / metric", "What it says", "Why it is inconsistent"],
                rows=inconsist_rows,
            ),
            observations=[
                "Reconcile contradicted claims before IC relies on the claimed figure.",
                "Databook remains source of truth for exhibit numbers.",
            ],
            source="Claims ledger; Diligence analysis",
            evidence_tier="B",
        )
    )

    slides.append(
        SlideSpec(
            slide_id="ch_app_glossary",
            layout="glossary",
            chapter="appendix",
            banner="APPENDICES",
            headline="Glossary",
            table=SlideTable(
                title="Glossary",
                headers=["Term", "Definition"],
                rows=[
                    ["Diligence EBITDA", "Reported EBITDA after diligence treatments (e.g. reverse non-recurring add-backs)"],
                    ["Management EBITDA", "Management's adjusted EBITDA including proposed add-backs"],
                    ["Reported EBITDA", "Operating income + depreciation from management accounts"],
                    ["LTM", "Last twelve months to the latest actual month"],
                    ["YTD", "Year-to-date from fiscal year start to latest actual month"],
                    ["Debt-like", "Items treated as debt for value (e.g. dividend arrears)"],
                    ["Evidence A/B/C", "Source trust tiers (contracts / management accounts / weaker)"],
                    ["Peg", "Normalised NWC target for SPA true-up — none proposed without audit tie-out"],
                    ["QoE", "Quality of earnings; normalisation of reported earnings"],
                    ["NWC", "Net working capital (operating CA less operating CL)"],
                ],
            ),
            source="Diligence analysis",
        )
    )
    return slides


def assign_page_numbers_and_toc(slides: list[SlideSpec]) -> list[SlideSpec]:
    numbered: list[SlideSpec] = []
    for i, slide in enumerate(slides, start=1):
        numbered.append(slide.model_copy(update={"page_no": i}))

    first_page: dict[str, int] = {}
    for slide in numbered:
        ch = str(slide.chapter or "")
        if ch in {"cover", "contents"}:
            continue
        if ch not in first_page and slide.page_no is not None:
            first_page[ch] = slide.page_no

    toc_entries = [
        TocEntry(number=num, title=title, page=str(first_page.get(ch, "")))
        for num, ch, _banner, title in DEFAULT_CHAPTER_ORDER
    ]
    out: list[SlideSpec] = []
    for slide in numbered:
        if slide.layout == "toc" or slide.chapter == "contents":
            out.append(
                slide.model_copy(
                    update={
                        "toc_entries": toc_entries,
                        "headline": "Contents",
                        "banner": "CONTENTS",
                    }
                )
            )
        else:
            out.append(slide)
    return out


def _lift_table_provenance(slides: list[SlideSpec]) -> list[SlideSpec]:
    """Copy SlideTable source/evidence/basis onto the slide when unset (Phase E)."""
    out: list[SlideSpec] = []
    for slide in slides:
        table = slide.table
        if table is None:
            out.append(slide)
            continue
        updates: dict[str, Any] = {}
        if not slide.source and table.source:
            updates["source"] = table.source
        if not slide.evidence_tier and table.evidence_tier:
            updates["evidence_tier"] = table.evidence_tier
        # Prefer table basis as a footnote when the slide has none yet.
        if table.basis and not any(
            "basis" in (n or "").lower() for n in (slide.footnotes or [])
        ):
            updates["footnotes"] = list(slide.footnotes or []) + [f"Basis: {table.basis}"]
        out.append(slide.model_copy(update=updates) if updates else slide)
    return out


def _resolve_slide_text(text: str, store: ExhibitStoreDoc, *, ctx: DisplayCtx) -> str:
    if not text or "{{ex:" not in text:
        # Still scrub leftover USD M labels from non-token prose.
        from agetic_cdd_api.services_fdd_tokens import scrub_store_unit_labels

        return scrub_store_unit_labels(text, display_scale=ctx.display_scale)
    return resolve_text_pptx(
        text,
        store,
        store_scale=ctx.store_scale or "M",
        display_scale=ctx.display_scale or "k",
    ).text


def _resolve_tokens_on_slides(
    slides: list[SlideSpec],
    store: ExhibitStoreDoc,
    *,
    ctx: DisplayCtx,
) -> list[SlideSpec]:
    """Resolve ``{{ex:…}}`` tokens in headlines/observations to $k/$m display strings."""
    out: list[SlideSpec] = []
    for slide in slides:
        updates: dict[str, Any] = {}
        if slide.headline and ("{{ex:" in slide.headline or "USD" in slide.headline):
            updates["headline"] = _resolve_slide_text(slide.headline, store, ctx=ctx)
        if slide.observations:
            resolved_obs = [
                _resolve_slide_text(line, store, ctx=ctx) for line in slide.observations
            ]
            # Drop empty lines left after scrubbing.
            resolved_obs = [x for x in resolved_obs if x and x.strip()]
            if resolved_obs != list(slide.observations):
                updates["observations"] = resolved_obs
        if slide.footnotes:
            resolved_fn = [
                _resolve_slide_text(line, store, ctx=ctx) for line in slide.footnotes
            ]
            if resolved_fn != list(slide.footnotes):
                updates["footnotes"] = resolved_fn
        if slide.adj_body and ("{{ex:" in slide.adj_body or "USD" in slide.adj_body):
            updates["adj_body"] = _resolve_slide_text(slide.adj_body, store, ctx=ctx)
        if slide.kpis:
            new_kpis = []
            changed = False
            for k in slide.kpis:
                detail = k.detail
                if detail and ("{{ex:" in detail or "USD" in detail):
                    detail = _resolve_slide_text(detail, store, ctx=ctx)
                    changed = True
                value = k.value
                if value and "{{ex:" in value:
                    value = _resolve_slide_text(value, store, ctx=ctx)
                    changed = True
                new_kpis.append(
                    k if (detail == k.detail and value == k.value) else k.model_copy(
                        update={"detail": detail, "value": value}
                    )
                )
            if changed:
                updates["kpis"] = new_kpis
        out.append(slide.model_copy(update=updates) if updates else slide)
    return out


def plan_chapter_slides(
    *,
    company: str,
    store: ExhibitStoreDoc,
    commentary: CommentaryDoc | None = None,
    scope: Any | None = None,
    findings: Any | None = None,
    qoe: Any | None = None,
    request_list: Any | None = None,
    claims: Any | None = None,
    chrome: PptxChrome | None = None,
) -> list[SlideSpec]:
    """Build the full 01–09 chapter slide list with Phase D–E content depth."""
    chrome = chrome or default_chrome(company=company, scope=scope)
    store_scale = "M"
    if scope is not None and getattr(scope, "scale", None):
        store_scale = str(scope.scale)
    ctx = DisplayCtx(
        display_scale=resolve_pptx_display_scale(scope)
        if scope is not None
        else (chrome.display_scale or "k"),
        store_scale=store_scale,
        currency=(getattr(scope, "currency", None) if scope is not None else None)
        or chrome.currency
        or "USD",
        basis_default=resolve_basis_default(scope, chrome=chrome),
        include_ytd=True,
        include_ltm=True,
    )
    token = _DISPLAY_CTX.set(ctx)
    try:
        requests = _request_hints(
            request_list=request_list, findings=findings, claims=claims
        )
        slides: list[SlideSpec] = [
            plan_cover(company=company, chrome=chrome, scope=scope, qoe=qoe),
            plan_toc_placeholder(),
        ]
        for _num, chapter_id, _banner, _title in DEFAULT_CHAPTER_ORDER:
            if chapter_id == "intro":
                slides.extend(
                    plan_intro(
                        commentary=commentary,
                        scope=scope,
                        company=company,
                        requests=requests,
                        qoe=qoe,
                    )
                )
            elif chapter_id == "es":
                slides.extend(
                    plan_es(
                        commentary=commentary,
                        store=store,
                        findings=findings,
                        qoe=qoe,
                    )
                )
            elif chapter_id == "transaction":
                slides.extend(
                    plan_transaction(
                        store=store,
                        scope=scope,
                        requests=requests,
                        company=company,
                    )
                )
            elif chapter_id == "qoe":
                slides.extend(
                    plan_qoe(
                        commentary=commentary,
                        store=store,
                        qoe=qoe,
                        requests=requests,
                    )
                )
            elif chapter_id == "trading":
                slides.extend(
                    plan_trading(commentary=commentary, store=store, requests=requests)
                )
            elif chapter_id == "cash":
                slides.extend(
                    plan_cash(commentary=commentary, store=store, requests=requests)
                )
            elif chapter_id == "bs":
                slides.extend(
                    plan_bs(commentary=commentary, store=store, requests=requests)
                )
            elif chapter_id == "deal":
                slides.extend(
                    plan_deal(
                        findings=findings,
                        request_list=request_list,
                        requests=requests,
                        claims=claims,
                    )
                )
            elif chapter_id == "appendix":
                slides.extend(
                    plan_appendix(
                        claims=claims,
                        deal_slug=str(getattr(store, "deal_slug", None) or ""),
                    )
                )
        slides = _lift_table_provenance(slides)
        slides = _resolve_tokens_on_slides(slides, store, ctx=ctx)
        return assign_page_numbers_and_toc(slides)
    finally:
        _DISPLAY_CTX.reset(token)


def chapter_sequence(slides: list[SlideSpec]) -> list[str]:
    seen: list[str] = []
    for s in slides:
        ch = str(s.chapter or "")
        if ch in {"cover", "contents"}:
            continue
        if ch not in seen:
            seen.append(ch)
    return seen


def expected_chapter_ids() -> list[str]:
    return [ch for _n, ch, _b, _t in DEFAULT_CHAPTER_ORDER]


def chapter_slide_ids(slides: list[SlideSpec], chapter: str) -> list[str]:
    return [s.slide_id for s in slides if s.chapter == chapter]
