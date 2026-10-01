"""Extract candidate Databook rows from CDL library tables."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_map import MetricMapHit, map_caption, normalize_caption
from agetic_cdd_api.services_databook_models import (
    DealDatabookParams,
    ExtractedRow,
    MetricFamily,
    RowStatus,
    StatementBlock,
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


def _row_id(
    *,
    doc_id: str,
    table: str,
    caption: str,
    year: int | None,
    value: float,
    line_idx: int | None = None,
) -> str:
    raw = f"{doc_id}|{table}|{caption}|{year}|{value:.6g}"
    if line_idx is not None:
        raw = f"{raw}|{line_idx}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _parse_number(cell: str) -> float | None:
    """Parse a numeric cell; preserve parentheses / hyphen negatives and trailing %."""
    text = (cell or "").strip()
    if not text or text.upper() in _BLANK_NUM:
        return None

    m = re.search(r"(\(?\s*-?\s*[\d,]+(?:\.\d+)?\s*%?\s*\)?)", text)
    if not m:
        return None
    clean = m.group(1).strip()

    # Accounting negatives: (12.5%) or -150 / −150 / –150
    neg = clean.startswith("(") or bool(re.search(r"[-−–]", clean))

    digits = re.sub(r"[^\d.]", "", clean)
    if not digits or digits.count(".") > 1:
        return None
    try:
        val = float(digits)
    except ValueError:
        return None
    return -val if neg else val


def _detect_year_headers(header: list[str]) -> dict[int, int]:
    """Map column index → fiscal year (1990–2099). Prefer FY/Year prefixes; bare years only for year-only cells."""
    years: dict[int, int] = {}
    for idx, cell in enumerate(header):
        text = (cell or "").strip()
        if not text:
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


def _infer_unit(caption: str) -> tuple[str | None, str | None, str | None]:
    """Return (unit, currency, scale) hints from caption."""
    text = caption.lower()
    currency = None
    scale = None
    unit = None
    if "inr" in text:
        currency = "INR"
    elif "usd" in text or "$" in text or "£" in text or "gbp" in text:
        currency = "USD" if ("usd" in text or "$" in text) else "GBP"
    if "£" in text or "gbp" in text:
        currency = "GBP"

    if re.search(r"\b(?:bn?|billions?)\b", text):
        scale = "B"
    elif re.search(r"\b(?:m|mn|millions?)\b", text) or re.search(r"\$\s*m\b|\bin\s*\$m\b", text):
        scale = "M"
    elif re.search(r"\bcr\b|crore", text):
        scale = "Cr"
    elif re.search(r"\blakh|lac\b", text):
        scale = "Lakh"
    elif re.search(r"\b(?:k|thousands?)\b", text) or re.search(r"\b'?000s?\b", text):
        scale = "K"

    if "%" in caption or "share" in text or "margin" in text or "growth" in text or "retention" in text:
        unit = "%"
    elif "000" in text or "units" in text:
        unit = "000s"
    return unit, currency, scale


def _resolve_unit_meta(
    caption: str,
    hit: MetricMapHit | None,
) -> tuple[str | None, str | None, str | None]:
    """Merge caption inference with map_caption hit metadata (hit wins when present)."""
    unit_h, currency_h, scale_h = _infer_unit(caption)
    if hit is None:
        return unit_h, currency_h, scale_h
    unit = hit.unit if hit.unit else unit_h
    currency = hit.currency or currency_h
    scale = hit.scale or scale_h
    return unit, currency, scale


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


def rows_from_table(
    *,
    source_name: str,
    doc_id: str,
    table: dict[str, Any],
) -> list[ExtractedRow]:
    rows_raw = table.get("rows") or []
    if not isinstance(rows_raw, list) or len(rows_raw) < 2:
        return []
    grid = [[str(c or "").strip() for c in (row if isinstance(row, list) else [])] for row in rows_raw]
    header = grid[0]
    year_cols = _detect_year_headers(header)
    if not year_cols and len(grid) >= 2:
        # Title row + year headers (works for exactly 2 rows and for longer grids)
        alt = _detect_year_headers(grid[1])
        if alt:
            year_cols = alt
            header = grid[1]
            body = grid[2:]
        else:
            body = grid[1:]
    else:
        body = grid[1:]

    table_name = str(table.get("name") or "table")
    out: list[ExtractedRow] = []

    if year_cols:
        for line_idx, row in enumerate(body):
            if not row:
                continue
            caption = normalize_caption(row[0] if row else "")
            if not caption or _is_year_only_caption(caption):
                continue

            hit = map_caption(caption)
            unit, currency, scale = _resolve_unit_meta(caption, hit)
            metric_key = hit.metric_key if hit else None
            metric_family = hit.family if hit else MetricFamily.UNKNOWN
            assumption = currency is None and metric_family == MetricFamily.REVENUE

            for col_idx, year in year_cols.items():
                if col_idx >= len(row):
                    continue
                value = _parse_number(row[col_idx])
                if value is None:
                    continue
                out.append(
                    ExtractedRow(
                        row_id=_row_id(
                            doc_id=doc_id,
                            table=table_name,
                            caption=caption,
                            year=year,
                            value=value,
                            line_idx=line_idx,
                        ),
                        doc_id=doc_id,
                        source_name=source_name,
                        caption=caption,
                        metric_key=metric_key,
                        metric_family=metric_family,
                        fiscal_year=year,
                        period=f"FY{year}",
                        value=value,
                        unit=unit,
                        currency=currency,
                        scale=scale,
                        assumption=assumption,
                        status=RowStatus.CANDIDATE,
                        table_name=table_name,
                    )
                )
        return out

    # Fallback: no year headers — emit one row per numeric cell (not only the first).
    for line_idx, row in enumerate(body):
        if len(row) < 2:
            continue
        caption = normalize_caption(row[0])
        if not caption:
            continue
        hit = map_caption(caption)
        unit, currency, scale = _resolve_unit_meta(caption, hit)
        metric_key = hit.metric_key if hit else None
        metric_family = hit.family if hit else MetricFamily.UNKNOWN
        for col_offset, cell in enumerate(row[1:]):
            value = _parse_number(cell)
            if value is None:
                continue
            col_idx = col_offset + 1
            year = _year_from_header_cell(header[col_idx] if col_idx < len(header) else "")
            out.append(
                ExtractedRow(
                    row_id=_row_id(
                        doc_id=doc_id,
                        table=table_name,
                        caption=caption,
                        year=year,
                        value=value,
                        line_idx=line_idx,
                    ),
                    doc_id=doc_id,
                    source_name=source_name,
                    caption=caption,
                    metric_key=metric_key,
                    metric_family=metric_family,
                    fiscal_year=year,
                    period=f"FY{year}" if year is not None else (header[col_idx] if col_idx < len(header) else None),
                    value=value,
                    unit=unit,
                    currency=currency,
                    scale=scale,
                    assumption=currency is None or year is None,
                    status=RowStatus.CANDIDATE,
                    table_name=table_name,
                )
            )
    return out


def extract_from_library(
    deal: Deal,
    *,
    params: DealDatabookParams | None = None,
) -> tuple[list[ExtractedRow], list[StatementBlock]]:
    """Extract candidate rows and statement blocks from the CDL library."""
    from agetic_cdd_api.services_databook_blocks import annotate_and_detect_blocks

    block_params = params or DealDatabookParams()

    index = load_library_index(deal) or {}
    entries = index.get("documents") if isinstance(index, dict) else None
    if not isinstance(entries, list):
        entries = []

    rows: list[ExtractedRow] = []
    blocks: list[StatementBlock] = []
    seen: set[str] = set()
    docs_with_tables: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "")
        if not filename:
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
            )
            for row in table_rows:
                if row.row_id in seen:
                    continue
                seen.add(row.row_id)
                rows.append(row)
            blocks.extend(table_blocks)

        # Free-text facts when tables are sparse / absent
        text = str(payload.get("text") or "")
        if tables and len(tables) > 0:
            continue
        for caption, year, value in _iter_all_text_facts(text):
            hit = map_caption(caption)
            unit, currency, scale = _resolve_unit_meta(caption, hit)
            row = ExtractedRow(
                row_id=_row_id(doc_id=doc_id, table="text", caption=caption, year=year, value=value),
                doc_id=doc_id,
                source_name=filename,
                caption=caption,
                metric_key=hit.metric_key if hit else None,
                metric_family=hit.family if hit else MetricFamily.UNKNOWN,
                fiscal_year=year,
                period=f"FY{year}",
                value=value,
                unit=unit,
                currency=currency,
                scale=scale,
                assumption=currency is None,
                status=RowStatus.CANDIDATE,
                table_name="text",
            )
            if row.row_id not in seen:
                seen.add(row.row_id)
                rows.append(row)

    # Docs in the index with no year-based table → explicit no_table sentinel for Findings.
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "")
        if not filename or filename in docs_with_tables:
            continue
        doc_id = str(entry.get("library_stem") or filename)
        if any(r.source_name == filename for r in rows):
            continue
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

    return rows, blocks


def extract_rows_from_library(deal: Deal) -> list[ExtractedRow]:
    rows, _ = extract_from_library(deal)
    return rows
