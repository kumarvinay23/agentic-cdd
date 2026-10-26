"""Typed value parsing for evidence cells.

The v2 drafter took the first digit run it found in a cell, so "$10-$50 per month" charted as
10, "$256.00M" and "4.01%" could land on one axis, "2030 (F)" lost its forecast flag and "N/A"
rows silently vanished. Every numeric use of evidence now goes through `parse_value`, and
charts are built only from values whose unit, scale and period basis agree.

    >>> parse_value("$256.00M").describe()
    'currency USD 256.0 M'
    >>> parse_value("$10-$50 per month").is_range
    True
    >>> parse_value("N/A").is_missing
    True
    >>> parse_label("2030 (F)")
    ('2030', True)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MISSING_RX = re.compile(r"^\s*(n/?a|na|n\.a\.|none|nil|not (?:provided|available|disclosed|stated)|"
                        r"unknown|tbd|tbc|-|—|–|\.|inconclusive|insufficient.*)\s*$", re.I)
FORECAST_RX = re.compile(r"\((?:f|e|p|fc|fcst|forecast|est|estimate|proj|plan|budget)\)|"
                         r"\b(?:\d{4}\s*[pfe]|fy\d{2,4}\s*[pfe]|forecast|projected|plan|budget|target)\b", re.I)
CURRENCY = {"$": "USD", "us$": "USD", "usd": "USD", "₹": "INR", "inr": "INR", "rs": "INR",
            "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP"}
SCALE = {"k": ("k", 1e3), "thousand": ("k", 1e3), "m": ("M", 1e6), "mm": ("M", 1e6), "mn": ("M", 1e6),
         "million": ("M", 1e6), "b": ("B", 1e9), "bn": ("B", 1e9), "billion": ("B", 1e9),
         "cr": ("cr", 1e7), "crore": ("cr", 1e7), "lakh": ("lakh", 1e5), "t": ("T", 1e12),
         "trillion": ("T", 1e12)}
PER = re.compile(r"\bper\s+(month|mo|year|yr|annum|week|home|household|location|account|customer|"
                 r"ton|tonne|unit|order|cy|cyd|pound|lb|kg|bag|stop|route)\b|/\s*(mo|month|yr|year|home|location|account)\b", re.I)
NUM = r"-?\(?\d[\d,]*(?:\.\d+)?\)?"
RANGE_RX = re.compile(rf"({NUM})\s*(?:%|[kmb]n?|million|billion)?\s*(?:-|–|—|to)\s*\$?\s*({NUM})", re.I)


@dataclass
class Value:
    raw: str
    value: float | None = None          # point value, in the stated scale
    low: float | None = None
    high: float | None = None
    kind: str = "number"                # currency | percent | ratio | count | number | label | missing
    currency: str | None = None
    scale: str = ""                     # "", k, M, B, cr ...
    per: str | None = None              # month, year, home ...
    is_range: bool = False
    is_missing: bool = False
    is_forecast: bool = False
    literal: str = ""                   # the digits exactly as printed, for traceability
    notes: list = field(default_factory=list)

    @property
    def unit_key(self) -> tuple:
        """Two values may share an axis only if their unit_key is equal."""
        return (self.kind, self.currency, self.scale, self.per)

    @property
    def chartable(self) -> bool:
        return (not self.is_missing and not self.is_range and self.value is not None
                and self.kind not in ("label",))

    def describe(self) -> str:
        if self.is_missing:
            return "missing"
        if self.is_range:
            return f"{self.kind} range {self.low}-{self.high} {self.scale}".strip()
        bits = [self.kind]
        if self.currency:
            bits.append(self.currency)
        bits.append(str(self.value))
        if self.scale:
            bits.append(self.scale)
        if self.per:
            bits.append("per " + self.per)
        return " ".join(bits)

    def unit_label(self) -> str:
        if self.kind == "percent":
            return "%"
        if self.kind == "ratio":
            return "x"
        cur = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}.get(self.currency or "", "")
        s = f"{cur}{self.scale}" if cur else self.scale
        if self.per:
            s = f"{s} per {self.per}".strip()
        return s or "count"


def _num(tok: str) -> float:
    neg = tok.startswith("(") and tok.endswith(")") or tok.startswith("-")
    v = float(tok.strip("()-").replace(",", ""))
    return -v if neg else v


def parse_label(s: str) -> tuple[str, bool]:
    """Category label -> (label with the forecast marker kept visible, is_forecast)."""
    s = " ".join(str(s or "").split())
    is_f = bool(FORECAST_RX.search(s))
    return s, is_f


def parse_value(raw, header: str = "") -> Value:
    """Parse one cell. `header` (the column heading) supplies units the cell omits,
    e.g. a column 'Market Size ($M)' makes '256' a USD M value."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v = Value(raw=str(raw), value=float(raw), literal=str(raw))
        _apply_header(v, header)
        return v
    s = " ".join(str(raw or "").split())
    v = Value(raw=s)
    if not s or MISSING_RX.match(s):
        v.is_missing, v.kind = True, "missing"
        return v
    if re.fullmatch(r"\[\d{1,3}\](?:\s*.*)?", s) or re.match(r"^(doc|source|ref)\s*:", s, re.I):
        v.kind = "label"               # a citation marker, not a value
        return v
    # a parenthesised period such as "(2024-25)" or "(2025-30)" annotates the value; it is
    # not a range of the value itself
    pm = re.search(r"\((?:fy)?(\d{4})\s*[-–]\s*(?:fy)?(\d{2,4})\)", s, re.I)
    period = None
    if pm:
        period = pm.group(0).strip("()")
        v.notes.append(f"period {period}")
        s = (s[:pm.start()] + s[pm.end():]).strip()
    low = s.lower()
    v.is_forecast = bool(FORECAST_RX.search(s)) or bool(FORECAST_RX.search(header or ""))
    m = PER.search(s)
    if m:
        v.per = (m.group(1) or m.group(2)).lower().replace("mo", "month").replace("monthnth", "month") \
            .replace("yr", "year").replace("annum", "year")
    for sym, code in CURRENCY.items():
        if (sym in ("$", "₹", "€", "£") and sym in s) or re.search(rf"\b{re.escape(sym)}\b", low):
            v.currency = code
            v.kind = "currency"
            break
    rm = RANGE_RX.search(s)
    if rm:
        v.is_range = True
        v.low, v.high = _num(rm.group(1)), _num(rm.group(2))
        v.literal = rm.group(0)
    nm = None
    for cand in re.finditer(NUM, s):
        a, b = cand.start(), cand.end()
        if (a > 0 and re.match(r"[A-Za-z_]", s[a - 1])) or (b < len(s) and re.match(r"[A-Za-z_]", s[b]) and
                                                            not re.match(r"[kKmMbBxX]\b|mn\b|bn\b|cr\b", s[b:b + 3])):
            continue                     # digits inside a code or file name are not a value
        nm = cand
        break
    if not nm or re.search(r"\.(pdf|xlsx|pptx|docx|txt)\b", s, re.I):
        v.kind = "label"
        v.is_range = False
        return v
    v.literal = v.literal or nm.group(0)
    v.value = None if v.is_range else _num(nm.group(0))
    # "-$0.72M" / "−$1.2bn" / "($0.4M)": the sign sits before the currency symbol
    if v.value is not None and v.value > 0:
        pre = s[:nm.start()]
        if re.fullmatch(r"\s*[-−–]\s*(?:us)?[$₹€£]\s*", pre, re.I) or re.fullmatch(r"\s*\(\s*[$₹€£]\s*", pre):
            v.value = -v.value
        elif (re.fullmatch(r"\s*\(?\s*[$₹€£]?\s*", pre) and re.match(r"^\s*\(", s)
              and re.search(r"\)\s*$", s)):
            v.value = -v.value                        # accounting negative: "(9.9%)", "($0.7)"
    tail = s[nm.end():nm.end() + 12].strip().lower()
    if v.is_range and rm and "%" in s[rm.start():rm.end() + 2]:
        v.kind = "percent"
    elif tail.startswith("%") or "%" in s[nm.end():nm.end() + 2]:
        v.kind = "percent"
    elif re.match(r"^x\b", tail) or re.search(r"\d\s*x\b", s[nm.start():nm.end() + 2], re.I):
        v.kind = "ratio"
    sm = re.match(r"^(k|mm|mn|m|bn|b|cr|crore|lakh|thousand|million|billion|trillion|t)\b", tail)
    if sm and v.kind not in ("percent", "ratio"):
        v.scale = SCALE[sm.group(1)][0]
    if v.kind == "number" and v.currency:
        v.kind = "currency"
    _apply_header(v, header)
    if v.kind == "number" and re.search(r"\b(homes|households|locations|accounts|customers|tons|"
                                        r"businesses|subscribers|orders|units|employees)\b", low):
        v.kind = "count"
    return v


def _apply_header(v: Value, header: str):
    h = (header or "").lower()
    if not h:
        return
    if v.kind == "number":
        if "%" in h or "percent" in h or "margin" in h or "rate" in h or "cagr" in h or "share" in h:
            v.kind = "percent"
        elif "$" in h or "usd" in h or "revenue" in h or "arr" in h or "price" in h:
            v.kind = "currency"
            v.currency = v.currency or "USD"
    hm = re.search(r"\(\s*\$?\s*(k|m|mm|mn|b|bn|million|billion|thousand)\s*\)|\$\s*(m|mm|mn|b|bn|k)\b", h)
    if hm and not v.scale and v.kind in ("currency", "number"):
        v.scale = SCALE[(hm.group(1) or hm.group(2))][0]
        v.kind, v.currency = "currency", v.currency or "USD"
    if FORECAST_RX.search(header):
        v.is_forecast = True
    pm = PER.search(header or "") or re.search(r"\(\$\s*(?:per\s+|/\s*)(month|mo|year|yr)", header or "", re.I)
    if pm and not v.per and v.kind == "currency":
        v.per = (pm.group(1) or (pm.group(2) if pm.lastindex and pm.lastindex > 1 else "")).lower() \
            .replace("mo", "month").replace("monthnth", "month").replace("yr", "year").replace("annum", "year")


def same_axis(values: list[Value]) -> tuple[bool, str]:
    """Can these values share one chart axis? Returns (ok, reason)."""
    pts = [v for v in values if not v.is_missing]
    if len(pts) < 2:
        return False, "fewer than two populated points"
    if any(v.is_range for v in pts):
        return False, "contains ranges - show as a range table, not a bar"
    keys = {v.unit_key for v in pts}
    if len(keys) > 1:
        return False, "mixed units or scales: " + "; ".join(sorted(str(k) for k in keys))
    return True, ""


def fmt(v: float, kind: str, scale: str = "", currency: str | None = None, dp: int = 1) -> str:
    if v is None:
        return "n/a"
    if kind == "percent":
        return f"{v:.{dp}f}%"
    if kind == "ratio":
        return f"{v:.{dp}f}x"
    sym = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}.get(currency or "", "")
    neg = v < 0
    s = f"{abs(v):,.{dp}f}"
    s = f"{sym}{s}{scale}"
    return f"-{s}" if neg else s
