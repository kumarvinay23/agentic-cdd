"""Shared unit / scale / earnings-basis hygiene for agents and report builders.

Keeps raw-$ figures from sitting next to USD M peers, blocks zero or dust
earnings bases from being printed as declared valuation anchors, and filters
polluted agent strings (``Revenue 0.0 USD | USD M``, meta QA / Reliance lines)
out of report insights.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Reuse the FDD scale trap (0.57 vs 98097, 13.41 vs 9436).
from agetic_cdd_api.services_fdd_claims import _scale_mismatch as scale_mismatch

_UNIT_SPLIT_RE = re.compile(r"[|/]+")

# Agent / workflow meta lines that are process status, not diligence insight.
_META_INSIGHT_RE = re.compile(
    r"(?i)"
    r"(?:^|\b)(?:quality\s+pass|quality\s+rework)\b|"
    r"(?:^|\b)reliance\s+(?:blocked|limited|ready)\b|"
    r"\bqa\s*\d+\s*/\s*\d+\s*pass\b|"
    r"\bdatabook\s+promoted\b|"
    r"\d+\s+p&l\s+line\(s\)|"
    r"\d+\s+accounting\s+period\(s\)|"
    r"\d+\s+cim\s+gap\(s\)|"
    r"period\(s\)\s+from\s+accounts|"
    r"\b0\s+external\s+risk\b|"
    r"internal\s+prior\s*=|"
    r"^(?:target|deal\s*/\s*strategy|sector|industry)\s*:|"
    r"\d+\s+file\(s\)|"
    r"^deal\s*/\s*strategy\b"
)

# Zero / unit-join earnings pollution commonly pasted into IC / Strategy exec.
# Require an explicit zero amount — do not match the "0" inside FY2025.
_ZERO_EARNINGS_INSIGHT_RE = re.compile(
    r"(?i)"
    r"earnings\s+basis\s*:?[^\n]{0,80}\b0(?:\.0+)?\b|"
    r"earnings\s*\(registered\)\s*:?[^\n]{0,80}\b0(?:\.0+)?\b|"
    r"revenue(?:\s+fy\d{4})?\s*(?:=|:)\s*0(?:\.0+)?\b|"
    r"revenue\s+0(?:\.0+)?\s*usd\b|"
    r"\b0(?:\.0+)?\s*usd\s*[|/]\s*usd\b|"
    r"\busd\s*[|/]\s*usd\s*m\b"
)

# Trailing process chrome glued onto otherwise useful findings.
_META_SUFFIX_RE = re.compile(
    r"(?i)\s*[\(\[]?\s*(?:quality\s+pass|quality\s+rework)\s*[·•|/\-]*\s*"
    r"reliance\s+(?:blocked|limited|ready)\s*[\)\]]?\s*$"
)
_META_TRAILING_RE = re.compile(
    r"(?i)\s*(?:[\(\[·•\-–—]\s*)?(?:quality\s+pass|quality\s+rework|"
    r"reliance\s+(?:blocked|limited|ready)|qa\s*\d+\s*/\s*\d+\s*pass).*$"
)
_EARNINGS_REGISTERED_CLAUSE_RE = re.compile(
    r"(?i)\s*Earnings\s*\(registered\)\s*:?\s*.*$"
)
_EARNINGS_BASIS_CLAUSE_RE = re.compile(
    r"(?i)\s*Earnings\s+basis\s*:?\s*.*$"
)

# P&L / cash magnitudes that look like USD M (not raw currency units).
_MONEY_FAMILIES = frozenset(
    {
        "revenue",
        "ebitda",
        "ebit",
        "gross_profit",
        "gross_margin",  # ratio handled separately; abs still small
        "cogs",
        "opex",
        "net_income",
        "cash",
        "liquidity",
        "capex",
        "nwc",
    }
)


def is_positive_amount(value: Any) -> bool:
    """True when value is a finite number strictly greater than zero."""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower().startswith(("information", "n/a", "na ")):
            return False
        try:
            value = float(s.replace(",", ""))
        except ValueError:
            return False
    try:
        return float(value) > 0.0
    except (TypeError, ValueError):
        return False


def clean_money_unit(unit: str | None, *, default: str = "USD M") -> str:
    """Collapse noisy unit joins like ``USD | USD M`` / ``USD M | M``."""
    raw = (unit or "").strip()
    if not raw:
        return default
    parts = [p.strip() for p in _UNIT_SPLIT_RE.split(raw) if p.strip()]
    joined = " ".join(parts) if parts else raw
    low = joined.lower()
    if re.search(r"\binr\b", low):
        return "INR Cr" if "cr" in low else "INR"
    if re.search(r"\bb\b|billion", low):
        return "USD B"
    if re.search(r"\bm\b|million|usd\s*m", low):
        return "USD M"
    if re.search(r"\bk\b|thousand", low):
        return "USD k"
    if "%" in joined or "percent" in low or low in {"pp", "pct"}:
        return "%"
    return parts[-1] if parts else default


def earnings_basis_is_usable(earn: dict[str, Any] | None) -> bool:
    """True when an earnings_basis dict is safe to print / underwrite against."""
    if not isinstance(earn, dict):
        return False
    amount = earn.get("amount")
    if amount is None:
        return False
    if isinstance(amount, str) and amount.strip().lower().startswith(
        ("information", "n/a")
    ):
        return False
    return is_positive_amount(amount)


def sanitize_earnings_basis(earn: dict[str, Any] | None) -> dict[str, Any]:
    """Return a cleaned earnings basis; blank amount when non-positive / absurd scale."""
    if not isinstance(earn, dict):
        return {}
    out = dict(earn)
    if "unit" in out:
        out["unit"] = clean_money_unit(str(out.get("unit") or ""), default="USD M")
    amount = out.get("amount")
    unit = str(out.get("unit") or "USD M")
    bad = False
    if not is_positive_amount(amount):
        bad = True
    elif isinstance(amount, (int, float)) and not millions_like(
        float(amount), family="revenue", unit=unit
    ):
        # Declared USD M earnings of 53876 are raw-$ spills, not millions.
        bad = True
    if bad:
        if amount is not None and not (
            isinstance(amount, str)
            and str(amount).lower().startswith(("information", "n/a"))
        ):
            out["amount"] = None
            notes = str(out.get("notes") or "").strip()
            flag = "Rejected non-positive or scale-inconsistent earnings amount."
            out["notes"] = f"{notes} {flag}".strip() if notes else flag
    return out


def millions_like(value: float, *, family: str = "", unit: str = "") -> bool:
    """True when a money figure looks like USD M / ratio, not raw currency units."""
    try:
        a = abs(float(value))
    except (TypeError, ValueError):
        return False
    fam = (family or "").lower()
    unt = (unit or "").lower()
    if "margin" in fam or unt in {"%", "pp", "pct", "percent"}:
        return a <= 150.0
    if fam in {"cash", "liquidity"} or "cash" in fam:
        # Cash in USD M is typically < ~5k; raw ledger $ is often > 100k.
        return a < 5_000.0
    if fam in _MONEY_FAMILIES or "usd" in unt or unt in {"m", "usd m"}:
        return a < 10_000.0
    return True


def dominant_scale_reference(
    values: Iterable[float],
    *,
    family: str = "",
    unit: str = "",
) -> float | None:
    """Pick a scale reference that prefers the USD-M / ratio cluster."""
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return None
    preferred = [v for v in nums if millions_like(v, family=family, unit=unit)]
    pool = preferred or nums
    ordered = sorted(abs(v) for v in pool if abs(v) > 1e-12)
    if not ordered:
        ordered = sorted(abs(v) for v in pool)
    if not ordered:
        return None
    return ordered[len(ordered) // 2]


def value_fits_scale(
    value: float,
    reference: float | None,
    *,
    family: str = "",
    unit: str = "",
) -> bool:
    """False when value is a raw-$ spill next to a USD-M reference (or vice versa)."""
    if reference is None:
        return millions_like(value, family=family, unit=unit) or abs(value) < 1e-12
    if abs(value) < 1e-12:
        # Zero stubs are handled elsewhere; don't keep them as scale peers.
        return False
    if scale_mismatch(value, reference):
        return False
    # If reference is millions-like, reject non-millions candidates even when
    # scale_mismatch's 1000 floor does not fire (e.g. 50 vs 53876).
    if millions_like(reference, family=family, unit=unit) and not millions_like(
        value, family=family, unit=unit
    ):
        return False
    return True


def pick_scale_consistent_amount(
    candidates: list[tuple[int, float]],
    *,
    family: str = "revenue",
    unit: str = "USD M",
) -> tuple[int, float] | None:
    """Pick latest (year, amount) that fits the dominant USD-M cluster."""
    if not candidates:
        return None
    ref = dominant_scale_reference(
        (amt for _, amt in candidates), family=family, unit=unit
    )
    good = [
        (yr, amt)
        for yr, amt in candidates
        if is_positive_amount(amt)
        and value_fits_scale(float(amt), ref, family=family, unit=unit)
    ]
    if not good:
        return None
    good.sort(key=lambda x: x[0])
    return good[-1]


def scrub_insight_text(text: str | None) -> str:
    """Remove trailing QA/reliance chrome and earnings-registered pollution clauses."""
    t = (text or "").strip()
    if not t:
        return ""
    t = _EARNINGS_REGISTERED_CLAUSE_RE.sub("", t).strip()
    t = _EARNINGS_BASIS_CLAUSE_RE.sub("", t).strip()
    t = _META_SUFFIX_RE.sub("", t).strip()
    t = _META_TRAILING_RE.sub("", t).strip()
    t = re.sub(r"\s{2,}", " ", t).strip(" ·•-|")
    return t


def is_polluted_insight(text: str | None) -> bool:
    """True when a finding/insight line is agent meta or zero-earnings pollution.

    Used by IC / Strategy / Ops / Market printers so lines like
    ``Quality PASS · Reliance BLOCKED`` or ``Revenue 0.0 USD | USD M`` never
    surface as diligence insight. Callers should scrub first when the line may
    mix useful prose with a trailing meta suffix.
    """
    scrubbed = scrub_insight_text(text)
    raw = scrubbed if scrubbed else (text or "").strip()
    if not raw:
        return True
    # Pure meta after scrub (or still meta-only original).
    if _META_INSIGHT_RE.search(raw) and len(raw) < 120:
        return True
    if _META_INSIGHT_RE.fullmatch(raw.strip(" ·•-|")):
        return True
    if _ZERO_EARNINGS_INSIGHT_RE.search(raw):
        return True
    # Absurd declared earnings still present after scrub attempt.
    if re.search(
        r"(?i)earnings\s+basis\s*:?[^\n]{0,60}revenue[^\n]{0,40}\b\d{4,}(?:\.\d+)?\b",
        raw,
    ):
        return True
    return False


def filter_insight_lines(
    lines: Iterable[Any],
    *,
    limit: int | None = None,
) -> list[str]:
    """Return scrubbed, non-polluted insight strings, optionally capped."""
    out: list[str] = []
    for item in lines:
        text = ""
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("finding")
                or item.get("note")
                or item.get("name")
                or item.get("risk")
                or item.get("detail")
                or item.get("theme")
                or ""
            ).strip()
        else:
            continue
        scrubbed = scrub_insight_text(text)
        if not scrubbed or is_polluted_insight(scrubbed):
            continue
        out.append(scrubbed)
        if limit is not None and len(out) >= limit:
            break
    return out


_FY_VALUE_KEY_RE = re.compile(r"^fy(\d{4})_value$", re.I)


def quarantine_pl_line_scale(lines: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop fy*_value cells that are raw-$ spills within a P&L line series.

    Used on released databook pivots so EBITDA=98097 / Revenue=53876 never ship
    into Ops / valuation as canonical USD M figures.
    """
    out: list[dict[str, Any]] = []
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        row = dict(line)
        family = str(row.get("metric_key") or row.get("line_item") or "").strip().lower()
        family = family.replace(" ", "_")
        unit = clean_money_unit(str(row.get("unit") or "USD M"))
        year_vals: dict[int, float] = {}
        for k, v in list(row.items()):
            m = _FY_VALUE_KEY_RE.match(str(k))
            if not m:
                continue
            try:
                year_vals[int(m.group(1))] = float(v)
            except (TypeError, ValueError):
                continue
        if len(year_vals) < 2 and year_vals:
            # Single cell: still reject obvious raw-$ for money families.
            yr, amt = next(iter(year_vals.items()))
            if family in _MONEY_FAMILIES and not millions_like(amt, family=family, unit=unit):
                row.pop(f"fy{yr}_value", None)
                held = list(row.get("scale_held_years") or [])
                held.append(yr)
                row["scale_held_years"] = held
                row["databook_note"] = (
                    str(row.get("databook_note") or "")
                    + " Scale-held: raw currency figure withheld from USD M series."
                ).strip()
            out.append(row)
            continue
        ref = dominant_scale_reference(year_vals.values(), family=family, unit=unit)
        held: list[int] = list(row.get("scale_held_years") or [])
        for yr, amt in year_vals.items():
            if value_fits_scale(amt, ref, family=family, unit=unit):
                continue
            row.pop(f"fy{yr}_value", None)
            held.append(yr)
        if held:
            row["scale_held_years"] = sorted(set(held))
            row["databook_note"] = (
                str(row.get("databook_note") or "")
                + " Scale-held years removed (raw $ vs USD M hygiene)."
            ).strip()
            # Refresh unit from remaining fy_units if present.
            fy_units = row.get("fy_units") if isinstance(row.get("fy_units"), dict) else {}
            if fy_units and held:
                for yr in held:
                    fy_units.pop(str(yr), None)
        out.append(row)
    return out
