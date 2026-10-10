"""Phase 2 — dual independent grid extract (S1-2 / S1-3).

Method A: structured row-major extract (``rows_from_table``).
Method B: independent re-parse of the same grid (alternate numeric tokenizer).
Cells that disagree on value are marked ``read_dual_agree=False``
(assumption → L1 / doubtful).
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.services_databook_extract import rows_from_table
from agetic_cdd_api.services_databook_map import normalize_caption
from agetic_cdd_api.services_databook_models import DealDatabookParams, ExtractedRow

# Independent tokenizer for Method B — does not share _parse_number path.
_B_NUM_RE = re.compile(
    r"^\s*\(?\s*-?\s*\$?\s*([\d,]+(?:\.\d+)?)\s*%?\s*\)?\s*$"
)
# Accounting negatives with trailing footnotes / currency outside the parens:
# "(125.4) *", "(£450.00)a", " (1,234) note".
_B_PAREN_NEG_RE = re.compile(r"\([^)]*[\d,]+(?:\.\d+)?[^)]*\)")


def _format_number_for_cell(value: float) -> str:
    """Decimal string without scientific notation (Method A tokenizer rejects ``1e+06``)."""
    if not isinstance(value, (int, float)):
        return str(value)
    if value != value:  # NaN
        return "nan"
    if abs(value) == float("inf"):
        return "inf" if value > 0 else "-inf"
    # Exact integers stay integer-form (avoids trailing .0 drift).
    as_int = int(value)
    if value == as_int and abs(as_int) < 10**15:
        return str(as_int)
    text = f"{value:.15f}".rstrip("0").rstrip(".")
    return text or "0"


def parse_number_method_b(cell: str) -> float | None:
    """Second numeric parser (parentheses negative, strip currency/%)."""
    text = str(cell or "").strip()
    if not text or text in {"—", "-", "–", "n/a", "N/A", "NA"}:
        return None

    # Negative indicators robust across surrounding symbols / footnote marks.
    neg = bool(_B_PAREN_NEG_RE.search(text)) or bool(
        re.match(r"^[-−–]", text.lstrip())
    )

    m = _B_NUM_RE.match(text.replace(" ", ""))
    if not m:
        # Free-form: take first number-like token
        m2 = re.search(r"([\d,]+(?:\.\d+)?)", text)
        if not m2:
            return None
        raw = m2.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            return None
        return -abs(value) if neg else value

    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return -abs(value) if neg else value


def _rebuild_grid_method_b(grid: list[list[str]]) -> list[list[str]]:
    """Independent reshape: skip leading empty rows; keep title+header band intact.

    Do **not** drop a title above year headers. ``rows_from_table`` already promotes
    the year row via ``body_start``, and ``parse_table_header_from_grid`` needs the
    pre-header title band for currency/scale. Dropping the title would also push a
    unit banner under the years into body-as-data inconsistently with Method A.
    """
    if len(grid) < 2:
        return grid
    start = 0
    while start < len(grid) - 1 and not any(str(c or "").strip() for c in grid[start]):
        start += 1
    return grid[start:] if start else grid


_BARE_YEAR_RE = re.compile(r"^(?:FY)?(?:19|20)\d{2}$", re.I)


def _is_headerish_cell(cell: str) -> bool:
    """True for date / bare-year header tokens — never rewrite these as amounts.

    Monthly packs put an ISO date band under a repeated-year band. Method B used
    to re-tokenize ``2025-12-31`` → ``2025``, which collapsed month columns into
    false FY totals and forced dual-read disagreement on every BS/CF/P&L line.
    """
    text = str(cell or "").strip()
    if not text:
        return False
    from agetic_cdd_api.services_databook_header import parse_header_date

    if parse_header_date(text) is not None:
        return True
    return bool(_BARE_YEAR_RE.fullmatch(text))


def rows_from_table_method_b(
    *,
    source_name: str,
    doc_id: str,
    table: dict[str, Any],
    fy_convention: str = "calendar",
    sector_pack: str = "generic",
    deal: Any | None = None,
    page_register: Any | None = None,
) -> list[ExtractedRow]:
    """Method B: rebuild grid then run the shared extractor with B-tagged rule."""
    rows_raw = table.get("rows") or []
    if not isinstance(rows_raw, list) or len(rows_raw) < 2:
        return []
    grid = [[str(c or "").strip() for c in (row if isinstance(row, list) else [])] for row in rows_raw]
    rebuilt = _rebuild_grid_method_b(grid)
    # Re-tokenize numeric cells with Method B parser for disagreement leverage:
    # leave captions and header-band date/year cells alone.
    if len(rebuilt) >= 2:
        header = rebuilt[0]
        body: list[list[str]] = []
        for row in rebuilt[1:]:
            new_row = list(row)
            for i, cell in enumerate(row):
                if i == 0:
                    continue
                if _is_headerish_cell(cell):
                    continue
                b_val = parse_number_method_b(cell)
                if b_val is not None:
                    # Canonicalize without scientific notation (A rejects ``1e+06``).
                    new_row[i] = _format_number_for_cell(b_val)
            body.append(new_row)
        rebuilt = [header, *body]

    # Suffix must not look like a scale token: "#B" made header parse stamp
    # scale=B via ``\bbn?\b`` (lone B = billions), skipping $→millions rescale.
    alt_table = {
        "name": str(table.get("name") or "table") + "#dualB",
        "rows": rebuilt,
    }
    rows = rows_from_table(
        source_name=source_name,
        doc_id=doc_id,
        table=alt_table,
        fy_convention=fy_convention,
        sector_pack=sector_pack,
        deal=deal,
        page_register=page_register,
    )
    stamped: list[ExtractedRow] = []
    for r in rows:
        ref = r.source_ref
        methods = ["B"]
        if ref is not None:
            ref = ref.model_copy(
                update={
                    "rule": (ref.rule or "year_column") + "+B",
                    "extract_methods": methods,
                }
            )
        stamped.append(
            r.model_copy(
                update={
                    "extract_methods": methods,
                    "source_ref": ref,
                    # Keep original table identity so dual-agree keys align with Method A.
                    "table_name": str(table.get("name") or r.table_name),
                }
            )
        )
    return stamped


def _agree_key(row: ExtractedRow) -> tuple[str, str, str, int | None]:
    """Cell identity for dual-agree — caption alone collides across sections/tables."""
    return (
        (row.table_name or "").strip().lower(),
        (row.statement or "").strip().lower(),
        normalize_caption(row.caption),
        row.fiscal_year,
    )


def merge_dual_extract(
    method_a: list[ExtractedRow],
    method_b: list[ExtractedRow],
) -> list[ExtractedRow]:
    """Stamp read_dual_agree on Method A rows using Method B as the second reader.

    - Both present, values match → read_dual_agree=True
    - Both present, values differ → read_dual_agree=False, assumption=True
    - Only A → read_dual_agree=None (single method; not a disagreement)
    """
    b_by_key: dict[tuple[str, str, str, int | None], list[ExtractedRow]] = {}
    for row in method_b:
        b_by_key.setdefault(_agree_key(row), []).append(row)

    out: list[ExtractedRow] = []
    for row in method_a:
        key = _agree_key(row)
        peers = b_by_key.get(key) or []
        methods = list(dict.fromkeys([*(row.extract_methods or []), "A"]))
        updates: dict[str, Any] = {"extract_methods": methods}
        if not peers:
            updates["read_dual_agree"] = None
        else:
            methods = list(dict.fromkeys([*methods, "B"]))
            updates["extract_methods"] = methods
            # Agree if any B peer matches value within 1e-6
            agreed = any(abs(float(p.value) - float(row.value)) < 1e-6 for p in peers)
            updates["read_dual_agree"] = bool(agreed)
            if not agreed:
                updates["assumption"] = True
            ref = row.source_ref
            if ref is not None:
                updates["source_ref"] = ref.model_copy(
                    update={"extract_methods": methods}
                )
        out.append(row.model_copy(update=updates))
    return out


def dual_extract_table(
    *,
    source_name: str,
    doc_id: str,
    table: dict[str, Any],
    params: DealDatabookParams | None = None,
    deal: Any | None = None,
    page_register: Any | None = None,
) -> list[ExtractedRow]:
    """Run Method A + Method B and merge agreement flags."""
    params = params or DealDatabookParams()
    fy = (params.fy_convention or "calendar")
    sector = (params.sector_pack or "generic")
    method_a = rows_from_table(
        source_name=source_name,
        doc_id=doc_id,
        table=table,
        fy_convention=fy,
        sector_pack=sector,
        deal=deal,
        page_register=page_register,
    )
    for i, row in enumerate(method_a):
        methods = list(dict.fromkeys([*(row.extract_methods or []), "A"]))
        ref = row.source_ref
        if ref is not None:
            ref = ref.model_copy(update={"extract_methods": methods})
        method_a[i] = row.model_copy(update={"extract_methods": methods, "source_ref": ref})

    method_b = rows_from_table_method_b(
        source_name=source_name,
        doc_id=doc_id,
        table=table,
        fy_convention=fy,
        sector_pack=sector,
        deal=deal,
        page_register=page_register,
    )
    return merge_dual_extract(method_a, method_b)
