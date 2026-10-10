"""Statement-block detection and printed-subtotal reconcile (Phase 3)."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_dual import dual_extract_table
from agetic_cdd_api.services_databook_extract import (
    _detect_year_headers,
    _is_year_only_caption,
    _parse_number,
    _row_id,
    rows_from_table,
)
from agetic_cdd_api.services_databook_map import normalize_caption
from agetic_cdd_api.services_databook_models import (
    DealDatabookParams,
    ExtractedRow,
    StatementBlock,
)

# Captions that close a statement block (printed subtotal / total).
# Intermediate "Total X" rows still close local segments; nested grand totals are
# handled by optional prior-total carry when arithmetic supports it (see detect).
_TOTAL_CAPTION_RE = re.compile(
    r"(?i)^\s*(?:grand\s+)?(?:sub)?totals?\b"
    r"|^\s*total\s+(?:revenue|income|costs?|expenses?|sales|ebitda|"
    r"gross\s+profit|operating\s+(?:income|profit|expenses?)|"
    r"assets|liabilities|equity|comprehensive\s+income)\b"
)


def is_total_caption(caption: str) -> bool:
    text = normalize_caption(caption)
    if not text:
        return False
    # Any "Total …" line wins over components in within-doc conflicts
    # (e.g. Total Cost of Operations, Total Selling, General, & Administrative).
    if text.lower().startswith("total "):
        return True
    return bool(_TOTAL_CAPTION_RE.search(text))


def _block_id(*, doc_id: str, table: str, seq: int, year: int | None) -> str:
    raw = f"{doc_id}|{table}|{seq}|{year}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _ties(computed: float, printed: float, *, rel_tol: float) -> bool:
    """Absolute 1-unit slack or relative tolerance vs printed subtotal."""
    delta = abs(computed - printed)
    if delta <= 1.0 + 1e-9:
        return True
    denom = max(abs(printed), 1e-9)
    return (delta / denom) <= rel_tol


def detect_blocks_from_table(
    *,
    source_name: str,
    doc_id: str,
    table: dict[str, Any],
    rows: list[ExtractedRow],
    params: DealDatabookParams | None = None,
) -> list[StatementBlock]:
    """
    Split a year-header table into statement blocks (line items closed by a total row).

    One StatementBlock per (block region × fiscal year). Rows get ``block_id`` when they
    participate in a block for that year.

    Nested / multi-level tables: each total closes its pending lines. When a later total
    does not tie to those lines alone but *does* tie if the previous printed subtotal is
    included, that prior total is carried in (grand-total over intermediate subtotals).
    """
    rows_raw = table.get("rows") or []
    if not isinstance(rows_raw, list) or len(rows_raw) < 2:
        return []

    grid = [[str(c or "").strip() for c in (row if isinstance(row, list) else [])] for row in rows_raw]
    header = grid[0]
    year_cols = _detect_year_headers(header)
    body_start = 1
    if not year_cols and len(grid) >= 2:
        alt = _detect_year_headers(grid[1])
        if alt:
            year_cols = alt
            header = grid[1]
            body_start = 2
    if not year_cols:
        return []

    body = grid[body_start:]
    table_name = str(table.get("name") or "table")
    rel_tol = max(float((params or DealDatabookParams()).block_tie_rel_tol), 0.0)

    # Partition body into segments ending at total captions.
    # line_idx is the absolute grid row (same as rows_from_table / SourceRef.row).
    segments: list[tuple[list[tuple[int, list[str]]], list[str] | None, int | None]] = []
    pending: list[tuple[int, list[str]]] = []
    for idx, row in enumerate(body):
        if not row:
            continue
        line_idx = idx + body_start
        caption = normalize_caption(row[0] if row else "")
        if not caption or _is_year_only_caption(caption):
            continue
        if is_total_caption(caption):
            segments.append((pending, row, line_idx))
            pending = []
        else:
            pending.append((line_idx, row))
    if pending:
        segments.append((pending, None, None))

    row_by_id = {r.row_id: r for r in rows if r.source_name == source_name}
    # Queues so identical caption/year/value lines claim distinct ExtractedRows in order.
    unused: dict[tuple[str, int | None, float], deque[ExtractedRow]] = defaultdict(deque)
    for r in rows:
        if r.source_name != source_name:
            continue
        unused[(r.caption, r.fiscal_year, round(r.value, 6))].append(r)

    claimed: set[str] = set()

    def _claim(
        caption: str,
        year: int | None,
        value: float,
        line_idx: int | None,
        col_idx: int | None,
    ) -> ExtractedRow | None:
        rid = _row_id(
            doc_id=doc_id,
            table=table_name,
            caption=caption,
            year=year,
            value=value,
            line_idx=line_idx,
            col_idx=col_idx,
        )
        match = row_by_id.get(rid)
        if match is not None and match.row_id not in claimed:
            claimed.add(match.row_id)
            key = (match.caption, match.fiscal_year, round(match.value, 6))
            q = unused.get(key)
            if q:
                # Drop this instance from the fallback queue if present
                unused[key] = deque(x for x in q if x.row_id != match.row_id)
            return match
        key = (caption, year, round(value, 6))
        q = unused.get(key)
        while q:
            cand = q.popleft()
            if cand.row_id in claimed:
                continue
            claimed.add(cand.row_id)
            return cand
        return None

    blocks: list[StatementBlock] = []
    seq = 0
    block_by_row: dict[str, str] = {}
    # Prior printed subtotal per year — candidate carry for nested grand totals.
    prior_printed: dict[int, tuple[float, str]] = {}

    def _attach(row: ExtractedRow | None, bid: str) -> None:
        if row is None:
            return
        block_by_row[row.row_id] = bid

    for line_grid, total_row, total_idx in segments:
        seq += 1
        for col_idx, year in year_cols.items():
            line_ids: list[str] = []
            line_values: list[float] = []
            bid = _block_id(doc_id=doc_id, table=table_name, seq=seq, year=year)

            for line_idx, line in line_grid:
                if col_idx >= len(line):
                    continue
                caption = normalize_caption(line[0] if line else "")
                value = _parse_number(line[col_idx])
                if value is None or not caption:
                    continue
                match = _claim(caption, year, value, line_idx, col_idx)
                rid = match.row_id if match else _row_id(
                    doc_id=doc_id,
                    table=table_name,
                    caption=caption,
                    year=year,
                    value=value,
                    line_idx=line_idx,
                    col_idx=col_idx,
                )
                line_ids.append(rid)
                line_values.append(match.value if match else value)
                _attach(match, bid)

            printed: float | None = None
            total_match: ExtractedRow | None = None
            if total_row is not None and col_idx < len(total_row):
                printed = _parse_number(total_row[col_idx])
                t_caption = normalize_caption(total_row[0] if total_row else "")
                if printed is not None and t_caption:
                    total_match = _claim(t_caption, year, printed, total_idx, col_idx)
                    _attach(total_match, bid)

            if total_row is None:
                computed_open = sum(line_values) if line_values else None
                blocks.append(
                    StatementBlock(
                        block_id=bid,
                        doc_id=doc_id,
                        source_name=source_name,
                        period=f"FY{year}",
                        fiscal_year=year,
                        line_row_ids=line_ids,
                        printed_subtotal=None,
                        computed_sum=computed_open,
                        ties=None,
                        outcome="unchecked",
                    )
                )
                continue

            if printed is None:
                blocks.append(
                    StatementBlock(
                        block_id=bid,
                        doc_id=doc_id,
                        source_name=source_name,
                        period=f"FY{year}",
                        fiscal_year=year,
                        line_row_ids=line_ids,
                        printed_subtotal=None,
                        computed_sum=None,
                        ties=None,
                        outcome="no_table" if not line_ids else "unchecked",
                    )
                )
                continue

            if not line_ids and year not in prior_printed:
                blocks.append(
                    StatementBlock(
                        block_id=bid,
                        doc_id=doc_id,
                        source_name=source_name,
                        period=f"FY{year}",
                        fiscal_year=year,
                        line_row_ids=[],
                        printed_subtotal=printed,
                        computed_sum=None,
                        ties=None,
                        outcome="unchecked",
                    )
                )
                prior_printed[year] = (printed, bid)
                continue

            direct = sum(line_values)
            computed = direct
            # Nested grand-total: include prior printed subtotal only when it makes the check
            # pass and the direct lines alone do not (avoids poisoning independent sections).
            carry = prior_printed.get(year)
            if (
                carry is not None
                and printed is not None
                and not _ties(direct, printed, rel_tol=rel_tol)
                and _ties(direct + carry[0], printed, rel_tol=rel_tol)
            ):
                computed = direct + carry[0]
                # Reference prior block's total via a synthetic note in line_row_ids is avoided;
                # constituents remain the direct lines — hold-out on fail still targets them.
                # Tag prior total row if we claimed it earlier under another block — already tagged.

            blocks.append(
                StatementBlock(
                    block_id=bid,
                    doc_id=doc_id,
                    source_name=source_name,
                    period=f"FY{year}",
                    fiscal_year=year,
                    line_row_ids=line_ids,
                    printed_subtotal=printed,
                    computed_sum=computed,
                    ties=None,
                    outcome="unchecked",
                )
            )
            prior_printed[year] = (printed, bid)

    for i, row in enumerate(rows):
        bid = block_by_row.get(row.row_id)
        if bid and row.block_id != bid:
            rows[i] = row.model_copy(update={"block_id": bid})

    return blocks


def reconcile_blocks(
    blocks: list[StatementBlock],
    *,
    params: DealDatabookParams,
) -> tuple[list[StatementBlock], set[str], list[dict[str, Any]]]:
    """
    Apply printed-subtotal checks.

    Returns (updated blocks, hold_out row_ids from failed blocks, failed_check issues).
    """
    rel_tol = max(float(params.block_tie_rel_tol), 0.0)
    out: list[StatementBlock] = []
    hold_ids: set[str] = set()
    issues: list[dict[str, Any]] = []

    for block in blocks:
        if block.outcome in {"no_table"}:
            out.append(block)
            continue
        if (
            block.printed_subtotal is None
            or block.computed_sum is None
            or not block.line_row_ids
        ):
            # Silence / incomplete — not a pass.
            out.append(
                block.model_copy(
                    update={
                        "ties": None,
                        "outcome": block.outcome if block.outcome != "unchecked" else "unchecked",
                    }
                )
            )
            continue

        ties = _ties(block.computed_sum, block.printed_subtotal, rel_tol=rel_tol)
        outcome = "pass" if ties else "fail"
        updated = block.model_copy(update={"ties": ties, "outcome": outcome})
        out.append(updated)
        if outcome == "fail":
            hold_ids.update(block.line_row_ids)
            issues.append(
                {
                    "kind": "failed_check",
                    "source": block.source_name,
                    "block_id": block.block_id,
                    "fiscal_year": block.fiscal_year,
                    "period": block.period,
                    "printed_subtotal": block.printed_subtotal,
                    "computed_sum": block.computed_sum,
                    "row_ids": list(block.line_row_ids),
                    "reason": "Statement block does not tie to the printed subtotal",
                }
            )

    return out, hold_ids, issues


def annotate_and_detect_blocks(
    *,
    source_name: str,
    doc_id: str,
    table: dict[str, Any],
    params: DealDatabookParams | None = None,
    deal: Deal | None = None,
    page_register: Any | None = None,
) -> tuple[list[ExtractedRow], list[StatementBlock]]:
    """Extract rows (dual Method A+B) then detect blocks; annotates row.block_id."""
    rows = dual_extract_table(
        source_name=source_name,
        doc_id=doc_id,
        table=table,
        params=params,
        deal=deal,
        page_register=page_register,
    )
    sheet_idx = table.get("sheet_index")
    if sheet_idx is not None:
        try:
            page_no = int(sheet_idx)
        except (TypeError, ValueError):
            page_no = None
        if page_no is not None:
            stamped: list[ExtractedRow] = []
            for row in rows:
                ref = row.source_ref
                if ref is not None and ref.page is None:
                    ref = ref.model_copy(update={"page": page_no})
                    stamped.append(row.model_copy(update={"source_ref": ref}))
                else:
                    stamped.append(row)
            rows = stamped
    blocks = detect_blocks_from_table(
        source_name=source_name,
        doc_id=doc_id,
        table=table,
        rows=rows,
        params=params,
    )
    return rows, blocks
