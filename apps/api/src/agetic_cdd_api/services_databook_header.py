"""Table header parser — currency/scale/period from the header band only (R5 / S3-11).

Never reads sentence body or free-text prose for scale. Line captions may still
contribute weaker unit hints when the header is silent (marked as non-header source).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

PeriodLength = Literal["FY", "H1", "H2", "Q1", "Q2", "Q3", "Q4", "YTD", "UNKNOWN"]

_CURRENCY_RE = re.compile(
    r"(?i)\b(?:in\s+)?(?P<code>inr|usd|gbp|eur|aud|cad|sgd|jpy)\b"
    r"|(?P<sym>[£$€])"
)
_SCALE_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:in\s+)?(?P<bn>bn?|billions?)\b"
    r"|\b(?:in\s+)?(?P<m>m|mn|millions?)\b"
    r"|\bin\s*\$\s*m\b"
    r"|\b(?P<cr>cr|crores?)\b"
    r"|\b(?P<lakh>lakh|lac)\b"
    r"|\b(?P<k>k|thousands?)\b"
    r"|\b'?000s?\b"
    r")"
)
_PERIOD_LENGTH_RE = re.compile(
    r"(?i)\b(?:"
    r"(?P<fy>fy|f\.?y\.?|fiscal\s*year|full\s*year)"
    r"|(?P<h1>h1|1h|first\s*half)"
    r"|(?P<h2>h2|2h|second\s*half)"
    r"|(?P<q1>q1|1q|first\s*quarter)"
    r"|(?P<q2>q2|2q|second\s*quarter)"
    r"|(?P<q3>q3|3q|third\s*quarter)"
    r"|(?P<q4>q4|4q|fourth\s*quarter)"
    r"|(?P<ytd>ytd|year[\s-]*to[\s-]*date)"
    r")\b"
)
_SCOPE_RE = re.compile(
    r"(?i)\b(?P<consol>consolidated|group|combined)\b"
    r"|\b(?P<sub>subsidiary|stand[\s-]*alone|statutory)\b"
)
_STATEMENT_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(?:p\s*&\s*l|pnl|income\s*statement|profit\s*(?:and|&)\s*loss)\b"), "income_statement"),
    (re.compile(r"(?i)\b(?:balance\s*sheet|statement\s*of\s*financial\s*position)\b"), "balance_sheet"),
    (re.compile(r"(?i)\b(?:cash\s*flow|statement\s*of\s*cash\s*flows?)\b"), "cash_flow"),
    (re.compile(r"(?i)\b(?:kpi|operating\s*metrics|key\s*metrics)\b"), "kpi"),
    (re.compile(r"(?i)\b(?:financials?|results)\b"), "financials"),
]


@dataclass(frozen=True, slots=True)
class TableHeaderMeta:
    """Parsed metadata from table title + column-header band (not body lines)."""

    currency: str | None = None
    scale: str | None = None
    period_length: PeriodLength | None = None
    scope: str | None = None
    statement: str | None = None
    fy_convention: str = "calendar"
    header_text: str = ""


def _currency_from_text(text: str) -> str | None:
    m = _CURRENCY_RE.search(text or "")
    if not m:
        return None
    code = m.group("code")
    if code:
        return code.upper()
    sym = m.group("sym")
    if sym == "$":
        return "USD"
    if sym == "£":
        return "GBP"
    if sym == "€":
        return "EUR"
    return None


def _scale_from_text(text: str) -> str | None:
    m = _SCALE_RE.search(text or "")
    if not m:
        return None
    if m.group("bn"):
        return "B"
    if m.group("m") or re.search(r"(?i)\$\s*m\b|in\s*\$m\b", text):
        return "M"
    if m.group("cr"):
        return "Cr"
    if m.group("lakh"):
        return "Lakh"
    if m.group("k") or re.search(r"(?i)\b'?000s?\b", text):
        return "K"
    return None


def _period_length_from_text(text: str) -> PeriodLength | None:
    m = _PERIOD_LENGTH_RE.search(text or "")
    if not m:
        return None
    for key in ("fy", "h1", "h2", "q1", "q2", "q3", "q4", "ytd"):
        if m.group(key):
            return key.upper()  # type: ignore[return-value]
    return None


_YEAR_END_MONTH_RE = re.compile(
    r"(?i)\b(?:dec(?:ember)?|year[\s-]*end|ye|31[\s/.-]*12|12[\s/.-]*31)\b"
)
_MONTH_ONLY_RE = re.compile(
    r"(?i)\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b"
)
# ISO / Excel-serialised month ends: 2025-12-31, 2025-12-31 00:00:00, 12/31/2025
_ISO_DATE_RE = re.compile(
    r"(?P<y>19\d{2}|20\d{2})-(?P<m>0[1-9]|1[0-2])-(?P<d>0[1-9]|[12]\d|3[01])"
)
_US_DATE_RE = re.compile(
    r"(?P<m>0?[1-9]|1[0-2])[/.-](?P<d>0?[1-9]|[12]\d|3[01])[/.-](?P<y>19\d{2}|20\d{2})"
)


def parse_header_date(cell: str) -> tuple[int, int, int] | None:
    """Return (year, month, day) from a date-like header cell, else None."""
    text = (cell or "").strip()
    if not text:
        return None
    m = _ISO_DATE_RE.search(text)
    if m:
        return int(m.group("y")), int(m.group("m")), int(m.group("d"))
    m = _US_DATE_RE.search(text)
    if m:
        return int(m.group("y")), int(m.group("m")), int(m.group("d"))
    return None


def period_length_from_header_cell(cell: str) -> PeriodLength:
    """Column-level period length; default FY when cell is a year header.

    December / year-end month columns on monthly BS/CF packs are treated as FY
    snapshots so year-end AR/AP/OCF can promote into the release.
    """
    text = (cell or "").strip()
    if not text:
        return "UNKNOWN"
    # Glued forms like YTD2026 (no word boundary after YTD) before bare-year FY.
    if re.match(r"(?i)^ytd\b|^ytd(?=\d)", text):
        return "YTD"
    found = _period_length_from_text(text)
    if found:
        return found
    # ISO / numeric month-end dates before bare-year matching (avoids "2025-01-31" → FY).
    # Only December is treated as a calendar year-end snapshot here; March year-end
    # packs still use bare FY / "Mar 2025" headers (see period_end_for_year).
    parsed = parse_header_date(text)
    if parsed is not None:
        _y, month, day = parsed
        if month == 12 and day >= 28:
            return "FY"
        return "UNKNOWN"
    # Bare / FY-prefixed year cells imply full-year unless H/Q markers present.
    if re.search(r"(?i)\b(?:fy|f\.?y\.?|year)?\s*(?:19|20)\d{2}\b", text):
        # "Dec 2025" / "December 31, 2025" → FY year-end snapshot
        if _YEAR_END_MONTH_RE.search(text):
            return "FY"
        # Other month+year headers stay unknown (not annualised here).
        if _MONTH_ONLY_RE.search(text):
            return "UNKNOWN"
        return "FY"
    if _YEAR_END_MONTH_RE.search(text):
        return "FY"
    return "UNKNOWN"


def period_end_for_year(
    year: int,
    *,
    period_length: PeriodLength | None,
    fy_convention: str,
) -> str | None:
    """Canonical period-end date string for a fiscal year column."""
    if year < 1990 or year > 2099:
        return None
    length = period_length or "FY"
    ending_march = (fy_convention or "calendar").lower() in {
        "ending_march",
        "march",
        "fy_march",
        "india",
    }
    if length == "FY":
        return f"{year}-03-31" if ending_march else f"{year}-12-31"
    if length == "H1":
        return f"{year}-09-30" if ending_march else f"{year}-06-30"
    if length == "H2":
        return f"{year}-03-31" if ending_march else f"{year}-12-31"
    if length == "Q1":
        return f"{year}-06-30" if ending_march else f"{year}-03-31"
    if length == "Q2":
        return f"{year}-09-30" if ending_march else f"{year}-06-30"
    if length == "Q3":
        return f"{year}-12-31" if ending_march else f"{year}-09-30"
    if length == "Q4":
        return f"{year}-03-31" if ending_march else f"{year}-12-31"
    if length == "YTD":
        # Calendar YTD stubs from monthly packs are typically mid-year (Jul);
        # March year-end packs keep the Q1/H1 stub date.
        return f"{year}-03-31" if ending_march else f"{year}-07-31"
    return f"{year}-12-31"


def _scope_from_text(text: str) -> str | None:
    m = _SCOPE_RE.search(text or "")
    if not m:
        return None
    if m.group("consol"):
        return "consolidated"
    if m.group("sub"):
        return "standalone"
    return None


def _statement_from_text(text: str) -> str | None:
    for pattern, label in _STATEMENT_HINTS:
        if pattern.search(text or ""):
            return label
    return None


def _statement_from_table_name(name: str) -> str | None:
    n = (name or "").lower()
    if any(tok in n for tok in ("pnl", "p&l", "income", "pl")):
        return "income_statement"
    if any(tok in n for tok in ("balance", "bs", "position")):
        return "balance_sheet"
    if any(tok in n for tok in ("cash", "cf")):
        return "cash_flow"
    if any(tok in n for tok in ("kpi", "metric", "operating")):
        return "kpi"
    if any(tok in n for tok in ("financial", "result")):
        return "financials"
    return None


def header_band_text(
    *,
    table_name: str,
    title_cells: list[str] | None,
    header_cells: list[str],
) -> str:
    parts: list[str] = []
    if table_name:
        parts.append(str(table_name))
    for cell in title_cells or []:
        if cell and str(cell).strip():
            parts.append(str(cell).strip())
    # Include non-year label cells from the header row (e.g. "Metric ($m)").
    for cell in header_cells:
        text = str(cell or "").strip()
        if not text:
            continue
        parts.append(text)
    return " | ".join(parts)


def parse_table_header(
    *,
    table_name: str,
    title_row: list[str] | None = None,
    header_row: list[str],
    fy_convention: str = "calendar",
) -> TableHeaderMeta:
    """Parse currency/scale/period/scope/statement from the table header band only."""
    text = header_band_text(
        table_name=table_name,
        title_cells=title_row,
        header_cells=header_row,
    )
    period = _period_length_from_text(text)
    # Prefer FY when year columns are clearly fiscal-year headers.
    if period is None:
        for cell in header_row:
            pl = period_length_from_header_cell(cell)
            if pl == "FY":
                period = "FY"
                break
            if pl != "UNKNOWN" and period is None:
                period = pl
    statement = _statement_from_text(text) or _statement_from_table_name(table_name)
    return TableHeaderMeta(
        currency=_currency_from_text(text),
        scale=_scale_from_text(text),
        period_length=period,
        scope=_scope_from_text(text) or "company",
        statement=statement or "table",
        fy_convention=fy_convention,
        header_text=text,
    )


def parse_table_header_from_grid(
    grid: list[list[str]],
    *,
    table_name: str,
    year_header_idx: int,
    fy_convention: str = "calendar",
) -> TableHeaderMeta:
    """Convenience: title rows above the year header + the year header itself."""
    title_row: list[str] | None = None
    if year_header_idx > 0 and grid:
        # Join all pre-header rows as title band (common: "Figures in $m" then years).
        title_parts: list[str] = []
        for r in grid[:year_header_idx]:
            title_parts.extend(c for c in r if c and str(c).strip())
        title_row = title_parts or None
    header_row = grid[year_header_idx] if year_header_idx < len(grid) else []
    return parse_table_header(
        table_name=table_name,
        title_row=title_row,
        header_row=header_row,
        fy_convention=fy_convention,
    )


def infer_caption_unit_hints(caption: str) -> tuple[str | None, str | None, str | None]:
    """Line-caption unit/currency/scale hints (weaker than header; for fallback only)."""
    import re

    text = (caption or "").lower()
    currency = _currency_from_text(caption or "")
    scale = _scale_from_text(caption or "")
    unit: str | None = None
    # "shareholders' equity" is money — do not treat bare "share" as %.
    pct_share = bool(
        re.search(r"\b(?:market\s+)?share\b", text)
        and "shareholder" not in text
    )
    if (
        "%" in (caption or "")
        or pct_share
        or "margin" in text
        or "growth" in text
        or "retention" in text
    ):
        unit = "%"
    elif "000" in text or "units" in text:
        unit = "000s"
    return unit, currency, scale


def resolve_unit_meta(
    caption: str,
    header: TableHeaderMeta | None,
    hit_unit: str | None = None,
    hit_currency: str | None = None,
    hit_scale: str | None = None,
) -> dict[str, Any]:
    """Merge header (wins) → map hit → caption for unit/currency/scale.

    Returns unit, currency, scale and their sources; ``assumption`` is True when
    money-relevant currency/scale came from caption/map rather than the header.
    """
    cap_unit, cap_currency, cap_scale = infer_caption_unit_hints(caption)

    unit: str | None = hit_unit or cap_unit
    unit_source: str | None = "map" if hit_unit else ("caption" if cap_unit else None)

    currency: str | None = None
    currency_source: str | None = None
    if header and header.currency:
        currency, currency_source = header.currency, "header"
    elif hit_currency:
        currency, currency_source = hit_currency, "map"
    elif cap_currency:
        currency, currency_source = cap_currency, "caption"

    scale: str | None = None
    scale_source: str | None = None
    if header and header.scale:
        scale, scale_source = header.scale, "header"
    elif hit_scale:
        scale, scale_source = hit_scale, "map"
    elif cap_scale:
        scale, scale_source = cap_scale, "caption"

    money_from_non_header = (
        (currency_source in {"caption", "map"} and currency is not None)
        or (scale_source in {"caption", "map"} and scale is not None)
    )
    return {
        "unit": unit,
        "currency": currency,
        "scale": scale,
        "unit_source": unit_source,
        "currency_source": currency_source,
        "scale_source": scale_source,
        "money_from_non_header": money_from_non_header,
    }
