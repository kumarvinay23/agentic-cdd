"""Extract candidate Databook rows from CDL library tables."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import replace
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_header import (
    TableHeaderMeta,
    parse_header_date,
    parse_table_header_from_grid,
    period_end_for_year,
    period_length_from_header_cell,
    resolve_unit_meta,
)
from agetic_cdd_api.services_databook_map import MetricMapHit, map_caption, normalize_caption
from agetic_cdd_api.services_databook_models import (
    DealDatabookParams,
    ExtractedRow,
    MetricFamily,
    NoteFact,
    PageClass,
    PageRegister,
    RowStatus,
    SourceRef,
    StatementBlock,
    StatementSource,
)
from agetic_cdd_api.services_library import load_library_document, load_library_index


# Fiscal-year bounds only (avoid treating codes / large amounts as years).
_YEAR_PREFIXED_RE = re.compile(r"\b(?:fy|f\.?y\.?|year)\s*(19\d{2}|20\d{2})\b", re.I)
_YEAR_BARE_CELL_RE = re.compile(r"^(?:fy|f\.?y\.?)?(19\d{2}|20\d{2})$", re.I)
_YEAR_RE = re.compile(r"\b(?:fy|f\.?y\.?|year)?\s*(19\d{2}|20\d{2})\b", re.I)  # caption year-only check
# Stepped free-text extraction (avoid nested [^\n]{0,N}? backtracking).
_TEXT_METRIC_RE = re.compile(r"(?i)\b(revenue|units?\s+sold|yoy\s+growth|nrr|grr)\b")
_TEXT_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_TEXT_VALUE_RE = re.compile(r"(\(?\s*-?\s*[\d,]+(?:\.\d+)?\s*%?\s*\)?)")
# Flattened P&L / KPI series: "FY2021 FY2022 … Revenue 8 456 2,630 …"
_FY_RUN_RE = re.compile(r"(?:FY\s*(?:19|20)\d{2}E?\b[\s,/|]*){2,}", re.I)
_FY_TOKEN_RE = re.compile(r"FY\s*((?:19|20)\d{2})E?", re.I)
_SERIES_METRIC_RE = re.compile(
    r"(?i)\b("
    r"units?\s+sold(?:\s*\([^)]{0,40}\))?"
    r"|gross\s+margin(?:\s*\(%\))?"
    r"|ebitda(?:\s+margin)?(?:\s*\([^)]{0,40}\))?"
    r"|net\s+revenue\s+retention|\bnrr\b"
    r"|gross\s+revenue\s+retention|\bgrr\b"
    r"|revenue(?:\s*\([^)]{0,40}\))?"
    r")\b"
)
_SERIES_NUM_RE = re.compile(
    r"~?\(?\s*-?\s*[\d,]+(?:\.\d+)?\s*%?\s*\)?"
    r"|\+\d+(?:\.\d+)?\s*(?:%|pp)?"
)
_BLANK_NUM = {"N/A", "NA", "N/M", "-", "—", "–"}

# Money metrics where a cell equal to the fiscal year is almost always a header leak.
_YEAR_AS_VALUE_METRICS = frozenset(
    {
        "revenue",
        "ebitda",
        "gross_profit",
        "cash",
        "net_debt",
        "arr",
    }
)

# Printed P&L lines are almost never ≥100k in the workbook's display units
# (USD millions / INR Cr). Absolute dollar figures belong in extract, not release.
_RAW_UNIT_MONEY_METRICS = frozenset({"revenue", "ebitda", "gross_profit"})
# BS / CF money lines often arrive in absolute currency units; scale to millions.
_SCALE_TO_MILLIONS_METRICS = frozenset(
    {
        "revenue",
        "ebitda",
        "gross_profit",
        "net_income",
        "operating_profit",
        "sga",
        "cogs",
        "labor_cost",
        "dividends",
        "cash",
        "accounts_receivable",
        "accounts_payable",
        "inventory",
        "current_assets",
        "current_liabilities",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "long_term_liabilities",
        "long_term_debt",
        "gross_debt",
        "term_loan",
        "sba_loan",
        "net_debt",
        "operating_cash_flow",
        "capex",
        "free_cash_flow",
        "net_change_in_cash",
        "deferred_revenue",
        "prepaid_expenses",
        "other_current_assets",
        "accrued_expenses",
    }
)
_CAPTION_SKIP = frozenset(
    {"account", "accounts", "line item", "description", "metric", "item"}
)


def is_year_as_value(
    metric_key: str | None,
    fiscal_year: int | None,
    value: float,
) -> bool:
    """True when a money metric's value is literally the fiscal year (header leak)."""
    if not metric_key or fiscal_year is None:
        return False
    if metric_key not in _YEAR_AS_VALUE_METRICS:
        return False
    try:
        return abs(float(value) - float(fiscal_year)) < 1e-9
    except (TypeError, ValueError):
        return False


def is_implausible_money_magnitude(metric_key: str | None, value: float | None) -> bool:
    """True when a money metric looks like unscaled currency units (e.g. 4_161_985)."""
    if not metric_key or value is None or metric_key not in _RAW_UNIT_MONEY_METRICS:
        return False
    try:
        return abs(float(value)) >= 100_000.0
    except (TypeError, ValueError):
        return False


def _row_id(
    *,
    doc_id: str,
    table: str,
    caption: str,
    year: int | None,
    value: float,
    line_idx: int | None = None,
    col_idx: int | None = None,
) -> str:
    raw = f"{doc_id}|{table}|{caption}|{year}|{value:.6g}"
    if line_idx is not None:
        raw = f"{raw}|{line_idx}"
    if col_idx is not None:
        raw = f"{raw}|c{col_idx}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _parse_number(cell: str) -> float | None:
    """Parse a numeric cell; preserve parentheses / leading-hyphen negatives and trailing %."""
    text = (cell or "").strip()
    if not text or text.upper() in _BLANK_NUM:
        return None
    # Hyphenated ranges (e.g. 10-12) are not a single number.
    if re.search(r"\d\s*[-−–]\s*\d", text):
        return None

    m = re.search(r"(\(?\s*[-−–]?\s*[\d,]+(?:\.\d+)?\s*%?\s*\)?)", text)
    if not m:
        return None
    clean = m.group(1).strip()

    # Accounting negatives: (12.5%) or leading -150 / −150 / –150 only.
    neg = clean.startswith("(") or bool(re.match(r"^[-−–]", clean))

    digits = re.sub(r"[^\d.]", "", clean)
    if not digits or digits.count(".") > 1:
        return None
    try:
        val = float(digits)
    except ValueError:
        return None
    return -val if neg else val


def _detect_year_headers(header: list[str]) -> dict[int, int]:
    """Map column index → fiscal year (1990–2099). Prefer FY/Year prefixes; bare years only for year-only cells.

    Phase 1: columns labelled Year 1–5 / forecast-relative periods are excluded from history.
    Also accepts ISO / Excel date headers (``2025-12-31 00:00:00``).
    """
    from agetic_cdd_api.services_databook_classify import is_forecast_period_header

    years: dict[int, int] = {}
    for idx, cell in enumerate(header):
        text = (cell or "").strip()
        if not text:
            continue
        if is_forecast_period_header(text):
            continue
        parsed = parse_header_date(text)
        if parsed is not None:
            year = parsed[0]
            if 1990 <= year <= 2099:
                years[idx] = year
            continue
        pref = list(_YEAR_PREFIXED_RE.finditer(text))
        if pref:
            year = int(pref[-1].group(1))
            if 1990 <= year <= 2099:
                years[idx] = year
            continue
        compact = re.sub(r"[^\w.]", "", text)
        bare = _YEAR_BARE_CELL_RE.fullmatch(compact)
        if bare:
            year = int(bare.group(1))
            if 1990 <= year <= 2099:
                years[idx] = year
    return years


def _count_date_headers(header: list[str]) -> int:
    return sum(1 for cell in header if parse_header_date(cell) is not None)


def _row_caption(row: list[str]) -> str:
    """First non-empty label cell (monthly packs put Account in col 1)."""
    for cell in row[:4]:
        text = normalize_caption(cell)
        if not text or _is_year_only_caption(text):
            continue
        if text.lower() in _CAPTION_SKIP:
            continue
        return text
    return ""


def _maybe_scale_to_millions(
    metric_key: str | None,
    value: float,
    scale: str | None,
    *,
    enabled: bool,
) -> tuple[float, str | None]:
    """Convert absolute currency units to millions on monthly packs.

    Only runs when *enabled* (date-header monthly BS/CF/P&L). Ordinary year
    tables already in display units must not be divided by 1e6.
    """
    if (
        not enabled
        or scale
        or not metric_key
        or metric_key not in _SCALE_TO_MILLIONS_METRICS
    ):
        return value, scale
    # Threshold 10k so mid-size BS lines (e.g. inventory ~70k) still rescale;
    # leaving them in $ while peers are in $M triggers series-drop of the M years.
    if abs(float(value)) < 10_000.0:
        return value, scale
    return float(value) / 1_000_000.0, "M"


def _infer_unit(caption: str) -> tuple[str | None, str | None, str | None]:
    """Return (unit, currency, scale) hints from caption (legacy helper; prefer header)."""
    from agetic_cdd_api.services_databook_header import infer_caption_unit_hints

    return infer_caption_unit_hints(caption)


def _resolve_unit_meta(
    caption: str,
    hit: MetricMapHit | None,
    header: TableHeaderMeta | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Merge header → map hit → caption (header wins for currency/scale)."""
    meta = resolve_unit_meta(
        caption,
        header,
        hit_unit=hit.unit if hit else None,
        hit_currency=hit.currency if hit else None,
        hit_scale=hit.scale if hit else None,
    )
    return meta["unit"], meta["currency"], meta["scale"]


def _unit_meta_full(
    caption: str,
    hit: MetricMapHit | None,
    header: TableHeaderMeta | None,
) -> dict[str, Any]:
    return resolve_unit_meta(
        caption,
        header,
        hit_unit=hit.unit if hit else None,
        hit_currency=hit.currency if hit else None,
        hit_scale=hit.scale if hit else None,
    )


def _year_from_header_cell(cell: str) -> int | None:
    text = (cell or "").strip()
    if not text:
        return None
    pref = list(_YEAR_PREFIXED_RE.finditer(text))
    if pref:
        year = int(pref[-1].group(1))
        return year if 1990 <= year <= 2099 else None
    compact = re.sub(r"[^\w.]", "", text)
    bare = _YEAR_BARE_CELL_RE.fullmatch(compact)
    if bare:
        year = int(bare.group(1))
        return year if 1990 <= year <= 2099 else None
    return None


def _iter_text_facts(text: str) -> list[tuple[str, int, float]]:
    """
    Extract (caption, year, value) from free text without nested optional regex spans.

    For each metric keyword, search a bounded same-line window for year then value.
    """
    out: list[tuple[str, int, float]] = []
    if not text:
        return out
    for m in _TEXT_METRIC_RE.finditer(text):
        line_end = text.find("\n", m.start())
        if line_end < 0:
            line_end = len(text)
        # Cap look-ahead to avoid scanning whole documents from one hit.
        window_end = min(m.start() + 96, line_end)
        window = text[m.start():window_end]
        ym = _TEXT_YEAR_RE.search(window, pos=len(m.group(0)))
        if not ym:
            continue
        year = int(ym.group(1))
        if not (1990 <= year <= 2099):
            continue
        # Value should follow the year within a short span.
        after = window[ym.end(): ym.end() + 32]
        vm = _TEXT_VALUE_RE.search(after)
        if not vm:
            continue
        value = _parse_number(vm.group(1).rstrip("."))
        if value is None:
            continue
        out.append((normalize_caption(m.group(1)), year, value))
    return out


def _iter_prose_series(text: str) -> list[tuple[str, int, float]]:
    """
    Extract metric×year series from flattened diligence prose.

    Handles headers like ``FY2021 FY2022 FY2023 FY2024E`` followed by
    ``Revenue 8 456 2,630 4,900`` (years before the metric name).
    """
    out: list[tuple[str, int, float]] = []
    if not text:
        return out

    for hm in _FY_RUN_RE.finditer(text):
        years = [int(y) for y in _FY_TOKEN_RE.findall(hm.group(0))]
        years = [y for y in years if 1990 <= y <= 2099]
        if len(years) < 2:
            continue
        window = text[hm.end() : hm.end() + 1000]
        seen_captions: set[str] = set()
        for mm in _SERIES_METRIC_RE.finditer(window):
            caption = normalize_caption(mm.group(1))
            # Avoid "Revenue Per User" / nested repeats of the same label in one block.
            key = caption.lower()
            if key in seen_captions:
                continue
            if "per user" in window[mm.start() : mm.end() + 20].lower():
                continue
            rest = window[mm.end() : mm.end() + 240]
            values: list[float] = []
            for nm in _SERIES_NUM_RE.finditer(rest):
                tok = nm.group(0).strip()
                # Skip unit fragments like "(000s)" / "000s" glued to digits.
                tail = rest[nm.end() : nm.end() + 1]
                if tail.isalpha():
                    continue
                # Skip trailing YoY / pp deltas once the series is filled.
                if tok.startswith("+") and len(values) >= len(years):
                    break
                if tok.startswith("+") and ("%" in tok or "pp" in tok.lower()):
                    continue
                # Approximate markers (~320) — strip tilde then parse.
                val = _parse_number(tok.lstrip("~"))
                if val is None:
                    continue
                values.append(val)
                if len(values) >= len(years):
                    break
            if len(values) < len(years):
                continue
            seen_captions.add(key)
            for year, value in zip(years, values[: len(years)]):
                out.append((caption, year, value))
            # A few material lines per year-header is enough for MVP.
            if len(seen_captions) >= 6:
                break
    return out


def _iter_all_text_facts(text: str) -> list[tuple[str, int, float]]:
    """Combine simple metric→year→value hits with flattened series extraction."""
    seen: set[tuple[str, int, float]] = set()
    out: list[tuple[str, int, float]] = []
    for item in (*_iter_text_facts(text), *_iter_prose_series(text)):
        key = (item[0].lower(), item[1], round(item[2], 6))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _is_year_only_caption(caption: str) -> bool:
    compact = caption.replace(" ", "")
    return bool(_YEAR_RE.fullmatch(compact))


def _money_family(family: MetricFamily) -> bool:
    return family in {MetricFamily.REVENUE, MetricFamily.OTHER, MetricFamily.MARGIN}


def _assumption_for_row(
    *,
    metric_family: MetricFamily,
    currency: str | None,
    year: int | None,
    money_from_non_header: bool,
    require_year: bool = False,
    dual_agree: bool | None = None,
    read_dual_agree: bool | None = None,
) -> bool:
    if require_year and year is None:
        return True
    if dual_agree is False or read_dual_agree is False:
        return True
    if currency is None and metric_family == MetricFamily.REVENUE:
        return True
    if money_from_non_header and _money_family(metric_family):
        return True
    return False


def _build_row(
    *,
    doc_id: str,
    source_name: str,
    table_name: str,
    caption: str,
    hit: MetricMapHit | None,
    header_meta: TableHeaderMeta,
    year: int | None,
    value: float,
    line_idx: int,
    col_idx: int,
    header_cell: str,
    rule: str,
    require_year: bool = False,
    statement: str | None = None,
    page_class: PageClass | None = None,
    statement_source: StatementSource | None = None,
    statement_mismatch: bool = False,
) -> ExtractedRow:
    meta = _unit_meta_full(caption, hit, header_meta)
    metric_key = hit.metric_key if hit else None
    metric_family = hit.family if hit else MetricFamily.UNKNOWN
    col_period_length = period_length_from_header_cell(header_cell)
    period_length = (
        col_period_length
        if col_period_length != "UNKNOWN"
        else (header_meta.period_length or "FY")
    )
    period_end = (
        period_end_for_year(
            year,
            period_length=period_length,  # type: ignore[arg-type]
            fy_convention=header_meta.fy_convention,
        )
        if year is not None
        else None
    )
    period = (
        f"{period_length}{year}" if year is not None and period_length == "FY" else None
    )
    if period is None and year is not None:
        period = f"{period_length}{year}" if period_length != "UNKNOWN" else f"FY{year}"
    if period is None and header_cell:
        period = header_cell

    dual_agree = hit.dual_agree if hit is not None else None
    assumption = _assumption_for_row(
        metric_family=metric_family,
        currency=meta["currency"],
        year=year,
        money_from_non_header=bool(meta["money_from_non_header"]),
        require_year=require_year,
        dual_agree=dual_agree,
    )
    return ExtractedRow(
        row_id=_row_id(
            doc_id=doc_id,
            table=table_name,
            caption=caption,
            year=year,
            value=value,
            line_idx=line_idx,
            col_idx=col_idx,
        ),
        doc_id=doc_id,
        source_name=source_name,
        caption=caption,
        metric_key=metric_key,
        metric_family=metric_family,
        fiscal_year=year,
        period=period,
        value=value,
        unit=meta["unit"],
        currency=meta["currency"],
        scale=meta["scale"],
        assumption=assumption,
        status=RowStatus.CANDIDATE,
        table_name=table_name,
        scope=header_meta.scope,
        statement=statement if statement is not None else header_meta.statement,
        period_end=period_end,
        period_length=period_length if period_length != "UNKNOWN" else None,
        source_ref=SourceRef(
            doc=source_name,
            table=table_name,
            row=line_idx,
            col=col_idx,
            rule=rule,
            # Heuristic page-relative bbox (S1-8 lite) — real crops remain unavailable.
            page=_page_hint_from_table(table_name, header_meta),
            bbox=_heuristic_bbox(line_idx=line_idx, col_idx=col_idx),
            extract_methods=["A"],
        ),
        unit_source=meta["unit_source"],
        scale_source=meta["scale_source"],
        currency_source=meta["currency_source"],
        coa_id=hit.coa_id if hit else None,
        coa_section=hit.section if hit else None,
        derived=bool(hit.derived) if hit else False,
        dual_agree=dual_agree,
        extract_methods=["A"],
        page_class=page_class,
        statement_source=statement_source,
        statement_mismatch=statement_mismatch,
    )


def _page_hint_from_table(table_name: str, header_meta: Any) -> int | None:
    """Prefer sheet_index embedded in table name/meta; else None."""
    del header_meta
    m = re.search(r"(?:sheet|page)[_\s#-]*(\d+)", str(table_name or ""), re.I)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _heuristic_bbox(*, line_idx: int, col_idx: int) -> list[float]:
    """Page-normalized placeholder bbox from grid position (not a real crop)."""
    y0 = min(0.92, max(0.04, 0.05 + (line_idx % 40) * 0.02))
    x0 = min(0.85, max(0.04, 0.08 + (col_idx % 12) * 0.07))
    return [round(x0, 4), round(y0, 4), round(min(0.98, x0 + 0.12), 4), round(min(0.98, y0 + 0.025), 4)]


def rows_from_table(
    *,
    source_name: str,
    doc_id: str,
    table: dict[str, Any],
    fy_convention: str = "calendar",
    sector_pack: str = "generic",
    deal: Deal | None = None,
    page_register: PageRegister | None = None,
) -> list[ExtractedRow]:
    rows_raw = table.get("rows") or []
    if not isinstance(rows_raw, list) or len(rows_raw) < 2:
        return []
    grid = [[str(c or "").strip() for c in (row if isinstance(row, list) else [])] for row in rows_raw]
    header = grid[0]
    year_header_idx = 0
    body_start = 1
    # Prefer a date-header row (monthly BS/CF) over a repeated bare-year band.
    date_header_idx: int | None = None
    for candidate_idx in (0, 1):
        if candidate_idx >= len(grid):
            break
        if _count_date_headers(grid[candidate_idx]) >= 2:
            date_header_idx = candidate_idx
            break
    if date_header_idx is not None:
        header = grid[date_header_idx]
        year_cols = _detect_year_headers(header)
        year_header_idx = date_header_idx
        body_start = date_header_idx + 1
    else:
        year_cols = _detect_year_headers(header)
        if not year_cols and len(grid) >= 2:
            # Title row + year headers (works for exactly 2 rows and for longer grids)
            alt = _detect_year_headers(grid[1])
            if alt:
                year_cols = alt
                header = grid[1]
                year_header_idx = 1
                body_start = 2
    body = grid[body_start:]

    table_name = str(table.get("name") or "table")
    header_meta = parse_table_header_from_grid(
        grid,
        table_name=table_name,
        year_header_idx=year_header_idx,
        fy_convention=fy_convention,
    )
    from agetic_cdd_api.services_databook_pages import (
        classify_table_class,
        lookup_page_entry,
        resolve_statement_label,
    )

    page_no: int | None = None
    raw_sheet = table.get("sheet_index")
    if raw_sheet is not None:
        try:
            page_no = int(raw_sheet)
        except (TypeError, ValueError):
            page_no = None
    page_entry = lookup_page_entry(
        page_register, filename=source_name, page=page_no
    )
    page_hint = page_entry.page_class if page_entry else None
    table_hit = classify_table_class(
        table_name=table_name,
        title_band=header_meta.header_text,
        page_class_hint=page_hint,
    )
    statement, stmt_source, stmt_mismatch = resolve_statement_label(
        header_statement=header_meta.statement,
        page_class=page_hint,
        table_class=table_hit.page_class,
    )
    row_page_class = (
        table_hit.page_class
        if table_hit.page_class != PageClass.UNKNOWN
        else page_hint
    )
    stmt_key = (statement or "").lower().replace(" ", "_")
    is_income = stmt_key in {
        "income_statement",
        "pnl",
        "p&l",
        "profit_and_loss",
    } or "p&l" in (table_name or "").lower() or "pnl" in (table_name or "").lower()
    is_cash_flow = stmt_key in {"cash_flow", "cashflow"} or "socf" in (
        table_name or ""
    ).lower() or "cash flow" in (table_name or "").lower()
    is_balance = stmt_key in {"balance_sheet", "bs"} or re.search(
        r"(?i)\bbs\b|balance", table_name or ""
    )
    has_date_headers = _count_date_headers(header) >= 2
    # Years that already have a printed annual (bare-year) total column.
    bare_fy_years = {
        y
        for i, y in year_cols.items()
        if parse_header_date(header[i] if i < len(header) else "") is None
        and period_length_from_header_cell(header[i] if i < len(header) else "")
        == "FY"
    }
    # Bare "2026" columns on a Jan–Jul pack are YTD, not full-year.
    months_present: dict[int, set[int]] = defaultdict(set)
    for i, y in year_cols.items():
        parsed = parse_header_date(header[i] if i < len(header) else "")
        if parsed is not None:
            months_present[int(y)].add(int(parsed[1]))
    ytd_years = {
        y for y, months in months_present.items() if months and max(months) < 12
    }
    # Monthly management packs: open-year bare totals are YTD stubs even when
    # that sheet only prints a bare year column (no month headers on the P&L).
    src_l = (source_name or "").lower()
    if "monthly" in src_l or "ytd" in src_l:
        from datetime import date

        closed = date.today().year - 1
        for y in year_cols.values():
            if int(y) > closed:
                ytd_years.add(int(y))
    out: list[ExtractedRow] = []
    # Monthly cash-flow: accumulate calendar months then emit FY totals
    # when no bare annual column exists for that year.
    cf_accum: dict[tuple[str, int], dict[str, Any]] = {}

    if year_cols:
        for idx, row in enumerate(body):
            if not row:
                continue
            line_idx = idx + body_start  # absolute grid row for SourceRef / row_id
            caption = _row_caption(row)
            if not caption:
                continue

            hit = map_caption(
                caption,
                statement=statement,
                sector_pack=sector_pack,
                deal=deal,
            )
            for col_idx, year in year_cols.items():
                if col_idx >= len(row):
                    continue
                value = _parse_number(row[col_idx])
                if value is None:
                    continue
                header_cell = header[col_idx] if col_idx < len(header) else ""
                col_period = period_length_from_header_cell(header_cell)
                is_date_col = parse_header_date(header_cell) is not None
                # Income monthly packs: keep bare FY totals; skip month columns.
                if is_income and is_date_col:
                    continue
                # Stamp incomplete bare-year totals as YTD (not FY).
                if (
                    not is_date_col
                    and int(year) in ytd_years
                    and col_period == "FY"
                ):
                    header_cell = f"YTD{int(year)}"
                    col_period = "YTD"
                # Balance sheet: Dec snapshot only — skip bare FY duplicates of Dec.
                if is_balance:
                    if col_period != "FY":
                        continue
                    if has_date_headers and not is_date_col:
                        continue
                # Cash flow: prefer bare annual totals; else sum months.
                if is_cash_flow and is_date_col:
                    if int(year) in bare_fy_years:
                        continue
                    metric_key = hit.metric_key if hit else None
                    if is_year_as_value(metric_key, year, value):
                        continue
                    key = (caption, int(year))
                    slot = cf_accum.setdefault(
                        key,
                        {
                            "hit": hit,
                            "line_idx": line_idx,
                            "col_idx": col_idx,
                            "total": 0.0,
                            "n": 0,
                        },
                    )
                    slot["total"] = float(slot["total"]) + float(value)
                    slot["n"] = int(slot["n"]) + 1
                    slot["line_idx"] = line_idx
                    slot["col_idx"] = col_idx
                    continue
                if col_period == "UNKNOWN" and is_date_col:
                    continue
                metric_key = hit.metric_key if hit else None
                if is_year_as_value(metric_key, year, value):
                    continue
                value, scaled = _maybe_scale_to_millions(
                    metric_key,
                    float(value),
                    header_meta.scale,
                    enabled=has_date_headers,
                )
                if is_implausible_money_magnitude(metric_key, value):
                    continue
                meta = (
                    replace(header_meta, scale=scaled)
                    if scaled and scaled != header_meta.scale
                    else header_meta
                )
                out.append(
                    _build_row(
                        doc_id=doc_id,
                        source_name=source_name,
                        table_name=table_name,
                        caption=caption,
                        hit=hit,
                        header_meta=meta,
                        year=year,
                        value=value,
                        line_idx=line_idx,
                        col_idx=col_idx,
                        # Keep YTD / stub stamps (do not collapse back to bare FY).
                        header_cell=header_cell
                        if col_period
                        in {"FY", "YTD", "H1", "H2", "Q1", "Q2", "Q3", "Q4"}
                        else f"FY{year}",
                        rule="year_column",
                        statement=statement,
                        page_class=row_page_class,
                        statement_source=stmt_source,
                        statement_mismatch=stmt_mismatch,
                    )
                )
        for (caption, year), slot in cf_accum.items():
            if int(slot["n"]) < 1:
                continue
            hit = slot["hit"]
            metric_key = hit.metric_key if hit else None
            total = float(slot["total"])
            total, scaled = _maybe_scale_to_millions(
                metric_key,
                total,
                header_meta.scale,
                enabled=has_date_headers,
            )
            if is_implausible_money_magnitude(metric_key, total):
                continue
            meta = (
                replace(header_meta, scale=scaled)
                if scaled and scaled != header_meta.scale
                else header_meta
            )
            out.append(
                _build_row(
                    doc_id=doc_id,
                    source_name=source_name,
                    table_name=table_name,
                    caption=caption,
                    hit=hit,
                    header_meta=meta,
                    year=year,
                    value=total,
                    line_idx=int(slot["line_idx"]),
                    col_idx=int(slot["col_idx"]),
                    header_cell=f"FY{year}",
                    rule="year_column_summed",
                    statement=statement,
                    page_class=row_page_class,
                    statement_source=stmt_source,
                    statement_mismatch=stmt_mismatch,
                )
            )
        return out

    # Fallback: no year headers — emit one row per numeric cell (not only the first).
    for idx, row in enumerate(body):
        if len(row) < 2:
            continue
        line_idx = idx + body_start
        caption = normalize_caption(row[0])
        if not caption:
            continue
        hit = map_caption(
            caption,
            statement=statement,
            sector_pack=sector_pack,
            deal=deal,
        )
        for col_offset, cell in enumerate(row[1:]):
            value = _parse_number(cell)
            if value is None:
                continue
            col_idx = col_offset + 1
            header_cell = header[col_idx] if col_idx < len(header) else ""
            year = _year_from_header_cell(header_cell)
            metric_key = hit.metric_key if hit else None
            if year is not None and is_year_as_value(metric_key, year, value):
                continue
            out.append(
                _build_row(
                    doc_id=doc_id,
                    source_name=source_name,
                    table_name=table_name,
                    caption=caption,
                    hit=hit,
                    header_meta=header_meta,
                    year=year,
                    value=value,
                    line_idx=line_idx,
                    col_idx=col_idx,
                    header_cell=header_cell,
                    rule="fallback_numeric",
                    require_year=True,
                    statement=statement,
                    page_class=row_page_class,
                    statement_source=stmt_source,
                    statement_mismatch=stmt_mismatch,
                )
            )
    return out


def _stamp_classify(
    row: ExtractedRow,
    reg_entry: Any,
) -> ExtractedRow:
    if reg_entry is None:
        return row
    return row.model_copy(
        update={
            "source_basis": reg_entry.basis,
            "ladder_score": reg_entry.ladder_score,
            "actual_forecast": reg_entry.actual_forecast,
        }
    )


def _note_id(
    *,
    doc_id: str,
    caption: str,
    year: int | None,
    value: float,
) -> str:
    raw = f"{doc_id}|note|{caption}|{year}|{value:.6g}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def notes_from_prose(
    *,
    source_name: str,
    doc_id: str,
    text: str,
) -> list[NoteFact]:
    """Extract sentence/prose figures into the notes store (never statement rows)."""
    out: list[NoteFact] = []
    seen: set[str] = set()
    for caption, year, value in _iter_all_text_facts(text):
        hit = map_caption(caption, sector_pack="generic")
        # Scale/currency from prose caption only — notes keep the hint, but these
        # never become statement lines (S1-9 / S3-11).
        unit, currency, scale = _infer_unit(caption)
        if hit and hit.unit:
            unit = hit.unit
        if hit and hit.currency:
            currency = hit.currency
        if hit and hit.scale:
            scale = hit.scale
        nid = _note_id(doc_id=doc_id, caption=caption, year=year, value=value)
        if nid in seen:
            continue
        seen.add(nid)
        out.append(
            NoteFact(
                note_id=nid,
                doc_id=doc_id,
                source_name=source_name,
                caption=caption,
                fiscal_year=year,
                value=value,
                unit=unit,
                currency=currency,
                scale=scale,
                excerpt=None,
                reason="prose",
                metric_key=hit.metric_key if hit else None,
                metric_family=hit.family if hit else MetricFamily.UNKNOWN,
            )
        )
    return out


def extract_from_library(
    deal: Deal,
    *,
    params: DealDatabookParams | None = None,
) -> tuple[list[ExtractedRow], list[StatementBlock], list[NoteFact]]:
    """Extract candidate rows, statement blocks, and prose notes from the CDL library.

    Phase 1: builds the file register first; set-aside and forecast-only files
    contribute no history rows (silence logged via Findings / register).
    Phase 3: sentence figures go to the notes store, never statement lines.
    """
    from agetic_cdd_api.services_databook_blocks import annotate_and_detect_blocks
    from agetic_cdd_api.services_databook_classify import (
        allows_history_extract,
        build_file_register,
        register_by_filename,
    )

    block_params = params or DealDatabookParams()
    register = build_file_register(deal)
    by_file = register_by_filename(register)

    # Phase 2 — page register (S1-1 / unread honesty) + G3 page classes
    page_register: PageRegister | None = None
    try:
        from agetic_cdd_api.services_databook_pages import build_page_register
        from agetic_cdd_api.services_databook_store import load_page_register

        page_register = build_page_register(deal)
    except Exception:  # noqa: BLE001 — page register must not block extract
        try:
            from agetic_cdd_api.services_databook_store import load_page_register as _load_pr

            page_register = _load_pr(deal)
        except Exception:  # noqa: BLE001
            page_register = None

    index = load_library_index(deal) or {}
    entries = index.get("documents") if isinstance(index, dict) else None
    if not isinstance(entries, list):
        entries = []

    rows: list[ExtractedRow] = []
    blocks: list[StatementBlock] = []
    notes: list[NoteFact] = []
    seen: set[str] = set()
    seen_notes: set[str] = set()
    docs_with_tables: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "")
        if not filename:
            continue
        reg = by_file.get(filename)
        if not allows_history_extract(reg):
            # Still record set-aside / forecast-only for Findings via no_table-style silence.
            continue
        payload = load_library_document(deal, filename)
        if not payload:
            continue
        tables = payload.get("tables") or []
        doc_id = str(entry.get("library_stem") or filename)
        if not isinstance(tables, list):
            tables = []
        for table in tables:
            if not isinstance(table, dict):
                continue
            docs_with_tables.add(filename)
            table_rows, table_blocks = annotate_and_detect_blocks(
                source_name=filename,
                doc_id=doc_id,
                table=table,
                params=block_params,
                deal=deal,
                page_register=page_register,
            )
            for row in table_rows:
                if row.row_id in seen:
                    continue
                seen.add(row.row_id)
                rows.append(_stamp_classify(row, reg))
            blocks.extend(table_blocks)

        # Free-text / sentence figures → notes store only (never statement lines).
        text = str(payload.get("text") or "")
        if text.strip():
            for note in notes_from_prose(source_name=filename, doc_id=doc_id, text=text):
                if note.note_id in seen_notes:
                    continue
                seen_notes.add(note.note_id)
                notes.append(note)

    # Docs in the index with no year-based table → explicit no_table sentinel for Findings.
    # Set-aside / forecast-only get explicit sentinel blocks so the trust ledger stays complete.
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "")
        if not filename or filename in docs_with_tables:
            continue
        doc_id = str(entry.get("library_stem") or filename)
        blocks.append(
            StatementBlock(
                block_id=hashlib.sha1(f"{doc_id}|no_table".encode()).hexdigest()[:16],
                doc_id=doc_id,
                source_name=filename,
                period=None,
                fiscal_year=None,
                line_row_ids=[],
                printed_subtotal=None,
                computed_sum=None,
                ties=None,
                outcome="no_table",
            )
        )
        # Classify reason (set-aside / forecast-only) lives on the file register / findings.

    return rows, blocks, notes


def extract_rows_from_library(deal: Deal) -> list[ExtractedRow]:
    rows, _, _ = extract_from_library(deal)
    return rows
