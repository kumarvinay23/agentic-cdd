"""FDD number tokens — ``{{ex:exhibit_id.cell_id}}`` resolve to exhibit cells."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    ExhibitCell,
    ExhibitStoreDoc,
    ResolvedToken,
    TokenResolveResult,
)
from agetic_cdd_api.services_fdd_exhibit import cell_ref, index_cells

# {{ex:exhibit_id.cell_id}} — exhibit_id is slug-safe; cell_id may include
# spaces/parens (legacy metric labels) until fully slugified at bridge.
TOKEN_RE = re.compile(
    r"\{\{ex:([A-Za-z0-9_-]+)\.([^}]+?)\}\}"
)

_CLIENT_TAG_RE = re.compile(r"^\[([FAMQ])\]\s*(.*)$")
_CLIENT_SECTION_LINE_RE = re.compile(r"^Section:\s*SEC-[A-Z]+\s*$", re.I)
_CLIENT_REQ_RE = re.compile(r"\breq_[a-z0-9]+\b", re.I)


def slugify_cell_id(raw: str) -> str:
    """Normalize metric labels to slug-safe cell ids (spaces/parens → underscores)."""
    s = re.sub(r"[^\w]+", "_", (raw or "").strip(), flags=re.ASCII)
    return re.sub(r"_+", "_", s).strip("_").lower() or "metric"


def metric_cell_id(metric_key: str, fiscal_year: int | None = None) -> str:
    base = slugify_cell_id(metric_key)
    if fiscal_year is None:
        return base
    return f"{base}_fy{int(fiscal_year)}"


def make_token(exhibit_id: str, cell_id: str) -> str:
    return f"{{{{ex:{exhibit_id}.{cell_id}}}}}"


def find_tokens(text: str) -> list[tuple[str, str, str]]:
    """Return list of (raw, exhibit_id, cell_id)."""
    return [
        (m.group(0), m.group(1), m.group(2).strip())
        for m in TOKEN_RE.finditer(text or "")
    ]


def format_fdd_number(
    value: float | None, *, brackets_for_negative: bool = True
) -> str:
    """Shared display rounding — Decimal HALF_UP so 0.565 → 0.57 everywhere.

    AS-6: negatives render in accounting brackets ``(1.23)`` unless disabled.
    """
    if value is None:
        return "—"
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    negative = d < 0
    if negative:
        d = abs(d)
    if d == d.to_integral_value():
        body = f"{int(d):,}"
    else:
        quantized = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        body = f"{quantized:,.2f}"
    if brackets_for_negative and negative:
        return f"({body})"
    if negative:
        return f"-{body}"
    return body


def format_cell_display(cell: ExhibitCell) -> str:
    if cell.display:
        return cell.display
    num = format_fdd_number(cell.value)
    unit = display_unit_for_cell(cell)
    # Keep % / pp glued to the figure so brackets read as "(1.91)%", not a bare label.
    if unit in {"%", "pp"} and num not in {"—", ""}:
        return f"{num}{unit}"
    return num


def display_unit_for_cell(cell: ExhibitCell | None) -> str:
    """Single display unit — never ``USD M M`` / ``% %`` / ``pp pp``."""
    if cell is None:
        return ""
    scale = (cell.scale or "").strip()
    currency = (cell.currency or "").strip()
    unit = (cell.unit or "").strip()
    if scale in {"%", "pp", "pct", "percent"} or unit in {"%", "pp", "pct", "percent"}:
        raw = unit or scale
        return "%" if raw == "pct" else raw
    # Prefer an already-composed unit when it embeds currency/scale.
    if unit and (not currency or currency.upper() in unit.upper()) and (
        not scale or scale.upper() in unit.upper() or unit.upper().endswith(scale.upper())
    ):
        return unit
    parts: list[str] = []
    for p in (currency, scale, unit):
        if not p:
            continue
        joined = " ".join(parts)
        if any(p.upper() == x.upper() for x in parts):
            continue
        if parts and p.upper() in joined.upper():
            continue
        if parts and joined.upper() in p.upper():
            parts = [p]
            continue
        parts.append(p)
    # Collapse adjacent duplicates ("M M", "% %")
    out: list[str] = []
    for t in parts:
        if out and out[-1].upper() == t.upper():
            continue
        out.append(t)
    return " ".join(out)


def _lookup_cell(
    exhibit_id: str,
    cell_id: str,
    cells: Mapping[str, ExhibitCell],
) -> ExhibitCell | None:
    """Exact match, then slug-normalized match within the exhibit."""
    key = cell_ref(exhibit_id, cell_id)
    cell = cells.get(key)
    if cell is not None:
        return cell
    slug = slugify_cell_id(cell_id)
    cell = cells.get(cell_ref(exhibit_id, slug))
    if cell is not None:
        return cell
    for c in cells.values():
        if c.exhibit_id == exhibit_id and slugify_cell_id(c.cell_id) == slug:
            return c
    return None


def resolve_token(
    exhibit_id: str,
    cell_id: str,
    cells: Mapping[str, ExhibitCell],
) -> ResolvedToken | None:
    cell = _lookup_cell(exhibit_id, cell_id.strip(), cells)
    if cell is None:
        return None
    return ResolvedToken(
        raw=make_token(exhibit_id, cell_id.strip()),
        exhibit_id=exhibit_id,
        cell_id=cell.cell_id,
        value=cell.value,
        display=format_cell_display(cell),
        fact_id=cell.fact_id,
        status=cell.status,
    )


def client_facing_text(text: str) -> str:
    """Strip internal tags / request ids from client PDF/deck prose.

    Does **not** strip arbitrary ``SEC-*`` tokens from prose — that turned
    held-back footers into \"Held back: No exhibits mapped to\". Section codes
    should be written as human titles at draft time; only bare
    ``Section: SEC-X`` exhibit lines are dropped.
    """
    out: list[str] = []
    for raw in (text or "").split("\n"):
        line = raw
        m = _CLIENT_TAG_RE.match(line.strip())
        if m:
            line = m.group(2)
        if _CLIENT_SECTION_LINE_RE.match(line.strip()):
            continue
        line = _CLIENT_REQ_RE.sub("open diligence request", line)
        line = re.sub(r"[ \t]{2,}", " ", line).rstrip()
        out.append(line)
    # Drop trailing empties but keep structural blanks mid-block
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def infer_currency_scale_from_store(
    store: ExhibitStoreDoc | None,
) -> tuple[str | None, str | None]:
    """Majority currency/scale from exhibit cells (None if empty)."""
    if store is None or not store.exhibits:
        return None, None
    from collections import Counter

    curs = Counter(
        (c.currency or "").strip()
        for ex in store.exhibits
        for c in (ex.cells or [])
        if (c.currency or "").strip()
    )
    scales = Counter(
        (c.scale or "").strip()
        for ex in store.exhibits
        for c in (ex.cells or [])
        if (c.scale or "").strip()
    )
    cur = curs.most_common(1)[0][0] if curs else None
    scale = scales.most_common(1)[0][0] if scales else None
    return cur, scale


def effective_currency_scale(
    *,
    scope: object | None = None,
    store: ExhibitStoreDoc | None = None,
    qoe: object | None = None,
) -> tuple[str, str]:
    """Resolve display currency/scale.

    Exhibit-cell majority wins (databook figures are SoT for unit). Scope/QoE
    are fallbacks — stale INR/Cr scope must not override USD exhibits.
    """
    inferred_c, inferred_s = infer_currency_scale_from_store(store)
    scope_c = getattr(scope, "currency", None) if scope is not None else None
    scope_s = getattr(scope, "scale", None) if scope is not None else None
    qoe_c = getattr(qoe, "currency", None) if qoe is not None else None
    qoe_s = getattr(qoe, "scale", None) if qoe is not None else None

    if inferred_c:
        cur = inferred_c.strip()
    else:
        cur = ((scope_c or qoe_c or "USD") or "USD").strip() or "USD"

    if inferred_s:
        scale = str(inferred_s).strip() or "M"
    else:
        scale = str(scope_s or qoe_s or "M").strip() or "M"

    return cur, scale


_INR_BASIS_RE = re.compile(r"\bon a INR basis\b", re.I)


def apply_currency_to_prose(text: str, currency: str | None) -> str:
    """Rewrite stale 'on a INR basis' when the effective currency is not INR."""
    if not text or not currency or currency.upper() == "INR":
        return text or ""
    return _INR_BASIS_RE.sub(f"on a {currency} basis", text)


def resolve_text(
    text: str,
    store: ExhibitStoreDoc | Mapping[str, ExhibitCell],
) -> TokenResolveResult:
    """Replace all ``{{ex:…}}`` tokens; collect bindings and unresolved refs."""
    cells: Mapping[str, ExhibitCell]
    if isinstance(store, ExhibitStoreDoc):
        cells = index_cells(store)
    else:
        cells = store

    bindings: list[ResolvedToken] = []
    unresolved: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        exhibit_id, cell_id = match.group(1), match.group(2)
        resolved = resolve_token(exhibit_id, cell_id, cells)
        if resolved is None:
            unresolved.append(match.group(0))
            return match.group(0)
        bindings.append(resolved)
        return resolved.display

    out = TOKEN_RE.sub(_sub, text or "")
    return TokenResolveResult(text=out, bindings=bindings, unresolved=unresolved)


def figures_from_store(
    store: ExhibitStoreDoc, refs: list[str] | None = None
) -> dict[str, float | None]:
    idx = index_cells(store)
    keys = refs if refs is not None else sorted(idx.keys())
    return {k: (idx[k].value if k in idx else None) for k in keys}


# Period / id labels allowed outside tokens (PDF P6: "except period labels").
# Do NOT match bare digit runs — that would swallow typed figures like 101.3.
_PERIOD_LABEL_RE = re.compile(
    r"\bFY\d{2,4}[ABab]?\b"
    r"|\bCY\d{2,4}[ABab]?\b"
    r"|\bH[12]\b"
    r"|\bQ[1-4]\b"
    r"|\bLTM\b"
    r"|\bYTD\b"
    r"|\bR-\d+\b"  # request ids (R-12)
    r"|\breq_[a-z0-9]+\b"  # internal request ids
    r"|\bqoe:[A-Za-z0-9_.:-]+\b"
    r"|\bSEC-[A-Z]+\b"
    r"|\bG[0-7]\b"
    r"|\bP(?:10|[0-9])\b"  # stages P0–P10
    r"|\bPhase\s+\d+\b"  # "Phase 5" in status notes
    r"|\bM[1-9](?:\s*[–-]\s*M[1-9])?\b"  # M4 or M1–M9
    r"|\bv\d+\b"  # version stamps
)


def strip_allowed_labels(text: str) -> str:
    """Remove tokens and allowed period/request labels before digit scan."""
    stripped = TOKEN_RE.sub("", text or "")
    return _PERIOD_LABEL_RE.sub("", stripped)


def assert_no_raw_numeric_literals(text: str) -> list[str]:
    """Flag digit runs outside tokens (AS-2 / P6). Empty list = pass.

    Period labels (FY25A), request ids (R-12), and section/gate ids are allowed.
    """
    stripped = strip_allowed_labels(text)
    return re.findall(r"\d[\d,]*(?:\.\d+)?%?", stripped)
