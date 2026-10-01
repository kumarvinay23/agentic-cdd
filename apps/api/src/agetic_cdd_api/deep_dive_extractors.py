"""Slice 1 heuristic extractors for Market Analysis Deep Dive agents (no LLM required)."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

MARKET_SLUGS: frozenset[str] = frozenset(
    {
        "market_definition",
        "market_volume_and_growth",
        "market_pricing",
        "demand_drivers",
    }
)

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_LABEL = (
    r"TAM|SAM|SOM|total addressable market|serviceable addressable market|"
    r"serviceable obtainable market|obtainable market"
)
# Gap may include decimals (57.6) but must not cross sentence terminators or another sizing label.
_GAP = (
    rf"(?:(?!\.\s)(?!\b(?:{_LABEL})\b).){{0,120}}?"
)
# Currency-first: TAM … USD 24.5 billion | USD 24.5B
_SIZING_CURRENCY_FIRST = re.compile(
    rf"(?i)\b({_LABEL})\b{_GAP}"
    rf"(USD|US\$|\$|INR|₹|EUR|€|GBP|£)\s*([\d,]+(?:\.\d+)?)\s*"
    rf"(billion|bn|million|mn|trillion|tn|B|M|cr|crore|crores|lakh|lakhs)?\b"
)
# Scale-first / suffix: TAM … 50B USD | 500 million dollars
_SIZING_SCALE_FIRST = re.compile(
    rf"(?i)\b({_LABEL})\b{_GAP}"
    rf"([\d,]+(?:\.\d+)?)\s*(billion|bn|million|mn|trillion|tn|B|M|cr|crore|crores)\s*"
    rf"(USD|US\$|\$|INR|₹|EUR|€|GBP|£|dollars?)?\b"
)
# Compact thesis table: "TAM — India 2W Market USD 24.5B" (digits allowed in segment name)
_SIZING_COMPACT = re.compile(
    rf"(?i)\b({_LABEL})\b\s*[—\-–:]{{1,3}}\s*.{{0,80}}?"
    rf"(USD|US\$|\$|INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(B|Bn|BN|M|Mn|MN|billion|bn|million|mn|cr|crore)?\b"
)
# Workbook TOTAL rows: "TOTAL Current 726.90 218.07 65.42" (prefer over segment rows)
_SIZING_TOTAL_ROW = re.compile(
    r"(?i)\bTOTAL\b\s+(Current|Expanded[^\d]{0,40})\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)"
)
# Workbook segment triad after "TAM ($ million) … SOM ($ million)" headers:
# "Logistics (Hauling) Current … → SOM 498.44 149.53 44.86"
_SIZING_HEADER_TRIAD = re.compile(
    r"(?i)TAM\s*\(\$\s*(?:million|m)?\)\s*SAM\s*\(\$\s*(?:million|m)?\)\s*SOM\s*\(\$\s*(?:million|m)?\)"
)
_SIZING_ROW_TRIAD = re.compile(
    r"(?i)(Logistics\s*\(Hauling\)|Compost\s+Sales(?:\s*&\s*Soil\s+Amendments)?|"
    r"KeyCompostables|Organics(?:\s+Collection)?)"
    r"\s+(Current|Expanded[^\d→]{0,80}?)"
    r"(?:(?!\b(?:Logistics\s*\(Hauling\)|Compost\s+Sales|KeyCompostables|TOTAL)\b).){0,320}?"
    r"(?:→\s*SOM|SOM)\s*"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)"
)
# ASP / unit-price bleed: "homes × $300 ASP" must not become SOM=$300
_ASP_BLEED_RE = re.compile(
    r"(?i)(?:ASP|×\s*\$|x\s*\$|homes?\s*[×x]|businesses?\s*[×x]|cyds?/home|ARR\b)"
)
_CAGR_RE = re.compile(
    r"(?i)(?:(~?\d+(?:\.\d+)?)\s*%?\s*CAGR)|(?:CAGR\s*(?:of\s*)?(~?\d+(?:\.\d+)?)\s*%?)"
)
# Thesis table row: "USD 24.5B USD 41.2B ~13.8%" (CAGR column, no "CAGR" token beside %)
_TABLE_CAGR_RE = re.compile(
    r"(?i)(?:USD|US\$|\$|INR|₹)\s*[\d,]+(?:\.\d+)?\s*[BbMm](?:n|illion)?\s+"
    r"(?:(?:USD|US\$|\$|INR|₹)\s*[\d,]+(?:\.\d+)?\s*[BbMm](?:n|illion)?\s+)?"
    r"(~?\d+(?:\.\d+)?)\s*%"
)
# Prefer sizing-row CAGRs: "TAM — … USD 24.5B USD 41.2B ~13.8%"
_SIZING_CAGR_RE = re.compile(
    r"(?i)\b(TAM|SAM|SOM)\b.{0,120}?"
    r"(?:USD|US\$|\$|INR|₹)\s*[\d,]+(?:\.\d+)?\s*[BbMm](?:n|illion)?"
    r".{0,60}?"
    r"(?:(?:USD|US\$|\$|INR|₹)\s*[\d,]+(?:\.\d+)?\s*[BbMm](?:n|illion)?.{0,40}?)?"
    r"(~?\d+(?:\.\d+)?)\s*%"
)
# Forward only: "penetration … 6%" / "penetration … 35–40%".
# Do not match "% … penetration" (table CAGRs bleed into the next sentence).
_PENETRATION_RE = re.compile(
    r"(?i)\b(?:EV\s+)?penetration\b.{0,140}?"
    r"(~?\d+(?:\.\d+)?)\s*(?:[–\-]\s*(~?\d+(?:\.\d+)?)\s*)?%"
)
_PENETRATION_PREFIX_RE = re.compile(
    r"(?i)(~?\d+(?:\.\d+)?)\s*%\s+EV\s+penetration\b"
)
_UNITS_RE = re.compile(
    r"(?i)((?:\d+(?:\.\d+)?\s*[-–]\s*)?\d+(?:\.\d+)?)\s*(million|mn)?\s*units?\b"
)
_BAD_UNIT_WINDOW = (
    "capacity", "futurefactory", "manufacturing", "p.a.", "per annum",
    "target capacity", "factory", "production capacity",
)
# Explicit currency capture group (may be empty → UNKNOWN, not assumed USD).
_PRICE_RE = re.compile(
    r"(?i)\b(?:ASP|average selling price|price point|list price|priced at|van westendorp|"
    r"optimal price|OPP)\b"
    r"[^\d₹$€£]{0,40}?(INR|₹|USD|US\$|\$|EUR|€|GBP|£)?\s*(~?[\d,]+(?:\.\d+)?)"
)
# Commercial DD table: Avg Selling Price (INR 000s) ~95 ~96.5 ~98.2 ~80
_ASP_TABLE_RE = re.compile(
    r"(?i)Avg(?:erage)?\s+Selling\s+Price\s*\(\s*(INR|USD|US\$|₹|EUR|GBP)?(?P<scale>[^)]*)\)\s*"
    r"(?P<vals>(?:[:~]?\s*~?\d+(?:\.\d+)?\s*){1,6})"
)
_FLAGSHIP_PRICE_RE = re.compile(
    r"(?i)Flagship\s+Price\s*\(\s*(INR|USD|₹)?\s*\)\s*[:~]?\s*(~?[\d,]+)"
)
_YEAR_RE = re.compile(r"\b(FY\s?\d{2,4}|20\d{2}E?)\b")
_TABLE_NOISE_RE = re.compile(
    r"(?i)("
    r"Market Share Trend|Flagship Price|Dimension\s+\w|Strong Gain|Losing Share|"
    r"Steady Growth|Units Sold \(FY|000s\)|FY\d{2}\s+FY\d{2}|Software\s*$|"
    r"^\d+\s+\d+\s+Market|"
    r"Milestone Target Year|Risk Factor Probability|Probability Impact Mitigation|"
    r"Gross Margin\s*>\s*\d|EBITDA Breakeven|PAT Breakeven|FCF Positive|"
    r"Insight Snapshot:|Sales Metric FY|Key Driver Gross|"
    r"Competitive pricing strategy OEM|Battery cost plateau"
    r")"
)
_MULTI_FY_RE = re.compile(r"(?i)(?:FY\s?\d{2,4}E?\b.*){3,}")

_MACRO = (
    "macro", "tailwind", "headwind", "policy", "government", "fame", "pli",
    "subsidy", "urbanization", "petrol", "fuel", "regulation", "incentive", "niti",
)
_SEGMENT = (
    "segment", "category", "two-wheeler", "2w", "ev", "electric", "industry",
    "addressable", "market overview", "vertical", "e2w",
)
_GEO = (
    "region", "geographic", "geography", "south india", "west india", "north india",
    "east india", "tier-3", "tier 3", "rural", "urban", "metro", "state-level",
)
_GEO_TABLE_RE = re.compile(
    r"(?i)((?:South|West|North|East|Central)\s+India"
    r"(?:\s*\([^)]+\))?(?:\s*&\s*Others)?)\s+"
    r"(~?\d+(?:\.\d+)?)\s*%"
)
_DEMAND = (
    "demand", "driver", "adoption", "penetration", "volume growth", "unit growth",
    "urbanization", "petrol", "tailwind", "boost demand", "structural acceleration",
)
_CYCLE_RISK = (
    "cyclical", "seasonal", "headwind", "slowdown", "volatility",
    "subsidy reduction", "policy reversal", "demand risk", "demand materially",
    "monsoon", "fuel-price",
)
_BAD_DEMAND = (
    "conversion cycle", "online funnel", "brand equity", "investor",
    "aided recall", "service satisfaction", "channel model", "margin retention",
    "localization roadmap", "vertically integrated",
    "bargaining", "leverage", "public transport", "ridesharing",
)
_DRIVER_RISK_ONLY = (
    "demand risk", "policy reversal", "impact demand materially",
    "dependency on subsidies", "dependency on fame",
)
_PRICE_WORDS = (
    "average selling price", "selling price", "price point", "list price",
    "van westendorp", "willingness to pay", "pricing power", "discount intensity",
    "flagship price", "asp",
)
_POLICY = ("fame", "pli", "subsidy", "policy", "government", "incentive", "niti", "regulatory")
# Avoid bare "projected" — it matches financial milestone tables.
_GROWTH = ("cagr", "growth rate", "volume growth", "unit growth", "forecast", "penetration", "growing at")
_BAD_MACRO = ("bargaining", "leverage", "supplier", "buyer power", "porters")
_BAD_DEFINITION = (
    "service reliability", "battleground", "underperform", "founded in",
    "headquartered", "futurefactory", "brand equity", "aided recall",
    "vertically integrated", "bargaining", "porter", "nps ",
    "competitive moat", "legacy oem",
)
# Definition-specific needles (narrower than shared _SEGMENT / _GEO).
_FRAMING_DEF = (
    "india's two-wheeler", "two-wheeler market", "2w market", "million units annually",
    "growing at", "cagr", "14x", "million unit annual", "market overview",
    "world's largest", "total addressable",
)
_SEGMENT_DEF = (
    "buyer segment",
    "ev penetration in the two-wheeler",
    "two-wheeler segment stood",
    "fastest-growing buyer",
    "urban and semi-urban markets",
    "addressable market",
    "sam —",
    "tam —",
)
_GEO_DEF = (
    "south india", "west india", "north india", "east india", "central india",
    "tier-3", "tier 3", "rural markets", "urban and semi-urban",
    "geographic sales", "geography", "regional mix", "sales by region",
)
_POLICY_DEF = (
    "fame", "pli", "subsidy", "government support", "state subsidies",
    "policy reversal", "incentive", "regulatory",
)
_MACRO_DEF = (
    "urbanization", "petrol", "fuel", "climate awareness", "macro tailwind",
    "structural acceleration", "penetration", "niti aayog", "boost demand",
)
_BAD_PRICING = (
    "milestone", "breakeven", "risk factor", "probability impact", "mitigation",
    "opex leverage", "capex cycle", "competitive pricing strategy oem",
    "semiconductor", "supplier", "post-covid", "maintain pricing power",
)


class MoneyMetric(BaseModel):
    label: str
    value: float
    unit: str = "USD"
    scale: str | None = None  # billion | million | crore | …
    raw: str = ""
    as_of: str | None = None


class MarketCeilingSpec(BaseModel):
    """DD-01 — Market Ceiling Analysis."""

    document: str = "Market Ceiling Analysis"
    dd_code: str = "DD-01"
    tam: MoneyMetric | None = None
    sam: MoneyMetric | None = None
    som: MoneyMetric | None = None
    cagr_pct: list[float] = Field(default_factory=list)
    penetration_pct: list[float] = Field(default_factory=list)
    unit_volume_notes: list[str] = Field(default_factory=list)
    growth_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class MacroEnvironmentSpec(BaseModel):
    """DD-02 — Macro Environment Analysis."""

    document: str = "Macro Environment Analysis"
    dd_code: str = "DD-02"
    market_framing: list[str] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    macro_drivers: list[str] = Field(default_factory=list)
    policy_context: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class RegionalDemandSpec(BaseModel):
    """DD-03 — Regional Economic Cycle Risk."""

    document: str = "Regional Economic Cycle Risk"
    dd_code: str = "DD-03"
    demand_drivers: list[str] = Field(default_factory=list)
    regional_signals: list[str] = Field(default_factory=list)
    cycle_risks: list[str] = Field(default_factory=list)
    consumes_ceiling: bool = False
    ceiling_tam: MoneyMetric | None = None
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class OptimalPriceSpec(BaseModel):
    """DD-17 — Optimal Price Point Analysis."""

    document: str = "Optimal Price Point Analysis"
    dd_code: str = "DD-17"
    price_points: list[MoneyMetric] = Field(default_factory=list)
    pricing_notes: list[str] = Field(default_factory=list)
    power_signals: list[str] = Field(default_factory=list)
    consumes_ceiling: bool = False
    ceiling_sam: MoneyMetric | None = None
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_RE.split(re.sub(r"\s+", " ", text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 20]


def _is_noisy_sentence(sentence: str) -> bool:
    """Drop OCR/table blobs that pollute Market specs."""
    if not sentence or len(sentence) < 25:
        return True
    if _TABLE_NOISE_RE.search(sentence):
        return True
    if _MULTI_FY_RE.search(sentence):
        return True
    if sentence.count("%") >= 3:
        return True
    if len(re.findall(r"\b\d[\d,.]*\b", sentence)) >= 6:
        return True
    # Leading page markers like "1 1 Market & Competition"
    if re.match(r"^\d+\s+\d+\s+\w", sentence):
        return True
    digits = len(re.findall(r"\d", sentence))
    letters = len(re.findall(r"[A-Za-z]", sentence))
    if digits >= 12 and letters > 0 and digits / max(letters, 1) >= 0.35:
        return True
    return False


@lru_cache(maxsize=64)
def _needle_patterns(needles: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    patterns: list[re.Pattern[str]] = []
    for needle in needles:
        token = needle.strip()
        if not token:
            continue
        parts = [re.escape(p) for p in re.split(r"\s+", token) if p]
        body = r"\s+".join(parts)
        patterns.append(re.compile(rf"\b{body}\b", re.I))
    return tuple(patterns)


def _hits(sentences: list[str], needles: tuple[str, ...], *, limit: int = 6) -> list[str]:
    """Keyword matcher using word-boundary patterns (avoids 'ev'/'geo ' false positives)."""
    patterns = _needle_patterns(needles)
    if not patterns:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        if _is_noisy_sentence(sentence):
            continue
        if not any(pat.search(sentence) for pat in patterns):
            continue
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sentence).strip()
        # Drop leading OCR bullets / orphan symbols.
        cleaned = re.sub(r"^[\W_]{1,4}", "", cleaned).strip()
        if len(cleaned) < 25:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(cleaned[:280])
        if len(found) >= limit:
            break
    return found


def _map_currency(raw: str | None) -> str | None:
    if not raw:
        return None
    token = raw.strip()
    if re.search(r"INR|₹|Rs\.?", token, re.I):
        return "INR"
    if re.search(r"EUR|€", token, re.I):
        return "EUR"
    if re.search(r"GBP|£", token, re.I):
        return "GBP"
    if re.search(r"USD|US\$|\$|dollars?", token, re.I):
        return "USD"
    return None


def _scale_to_unit(scale: str | None) -> str | None:
    if not scale:
        return None
    s = scale.lower()
    if s in {"billion", "bn", "b"}:
        return "billion"
    if s in {"million", "mn", "m"}:
        return "million"
    if s in {"trillion", "tn"}:
        return "trillion"
    if s in {"cr", "crore", "crores"}:
        return "crore"
    if s in {"lakh", "lakhs"}:
        return "lakh"
    return s


def _normalize_label(raw: str) -> str:
    low = raw.lower()
    if "tam" in low or "total addressable" in low:
        return "TAM"
    if "sam" in low or "serviceable addressable" in low:
        return "SAM"
    if "som" in low or "obtainable" in low:
        return "SOM"
    return raw.upper()


def _metric_richness(metric: MoneyMetric) -> int:
    score = 0
    if metric.scale:
        score += 2
    if metric.unit and metric.unit != "UNKNOWN":
        score += 1
    if metric.as_of:
        score += 1
    if metric.scale in {"billion", "million", "trillion", "crore"}:
        score += 1
    return score


def _extract_sizing(text: str) -> dict[str, MoneyMetric]:
    out: dict[str, MoneyMetric] = {}
    body = text or ""

    def _consider(
        label_raw: str,
        value_raw: str,
        scale_raw: str | None,
        curr_raw: str | None,
        full: str,
        start: int,
        end: int,
        *,
        label_end: int | None = None,
        value_start: int | None = None,
        bonus: int = 0,
    ) -> None:
        label = _normalize_label(label_raw)
        try:
            value = float(value_raw.replace(",", ""))
        except ValueError:
            return
        # Skip header→row bleed: "TAM / SAM / SOM … TAM — … USD 24.5B"
        if label_end is not None and value_start is not None:
            gap = body[label_end:value_start]
            if re.search(rf"(?i)\b({_LABEL})\b", gap):
                return
            # Skip ASP / unit-price bleed: SOM ($ million) … homes × $300
            if _ASP_BLEED_RE.search(gap):
                return
        scale = _scale_to_unit(scale_raw)
        mapped = _map_currency(curr_raw)
        # Reject bare letter scales without currency (avoids "2W"-style noise).
        if scale_raw and scale_raw.lower() in {"b", "m"} and not mapped:
            return
        unit = mapped or ("INR" if scale in {"crore", "lakh"} else "USD")
        window_start = max(0, start - 24)
        window = body[window_start : end + 24]
        years = _YEAR_RE.findall(window)
        metric = MoneyMetric(
            label=label,
            value=value,
            unit=unit,
            scale=scale,
            raw=full.strip()[:120],
            as_of=years[0].replace(" ", "") if years else None,
        )
        existing = out.get(label)
        richness = _metric_richness(metric) + bonus
        if existing is None or richness > _metric_richness(existing):
            out[label] = metric

    def _parse_triad_nums(tam_v: str, sam_v: str, som_v: str) -> tuple[float, float, float] | None:
        try:
            vals = tuple(float(x.replace(",", "")) for x in (tam_v, sam_v, som_v))
        except ValueError:
            return None
        # Keep $ million figures (typically under ~5,000); skip absolute-$ rows
        if any(v <= 0 or v > 5_000 for v in vals):
            return None
        return vals  # type: ignore[return-value]

    def _apply_triad(
        vals: tuple[float, float, float],
        *,
        segment: str,
        territory: str,
        score: int,
    ) -> None:
        seg = re.sub(r"\s+", " ", (segment or "").strip())
        terr = re.sub(r"\s+", " ", (territory or "Current").strip()) or "Current"
        if re.search(r"(?i)logistics|hauling", seg) and not re.search(r"(?i)compost|organic", seg):
            seg_label = "Organics hauling"
        else:
            seg_label = seg
        note = f"{seg_label} · {terr}"
        for label, value in (("TAM", vals[0]), ("SAM", vals[1]), ("SOM", vals[2])):
            metric = MoneyMetric(
                label=label,
                value=round(value, 3) if value < 1000 else round(value, 1),
                unit="USD",
                scale="million",
                raw=f"{label} ${value:g}M ({note})"[:120],
                as_of=terr if re.match(r"(?i)current|expanded", terr) else None,
            )
            existing = out.get(label)
            richness = _metric_richness(metric) + score
            if existing is None or richness > _metric_richness(existing):
                out[label] = metric

    for match in _SIZING_CURRENCY_FIRST.finditer(body):
        _consider(
            match.group(1),
            match.group(3),
            match.group(4),
            match.group(2),
            match.group(0),
            match.start(),
            match.end(),
            label_end=match.end(1),
            value_start=match.start(2),
        )
    for match in _SIZING_SCALE_FIRST.finditer(body):
        _consider(
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
            match.group(0),
            match.start(),
            match.end(),
            label_end=match.end(1),
            value_start=match.start(2),
        )
    for match in _SIZING_COMPACT.finditer(body):
        _consider(
            match.group(1),
            match.group(3),
            match.group(4),
            match.group(2),
            match.group(0),
            match.start(),
            match.end(),
            bonus=2,  # prefer clean thesis-table rows over header→value spans
        )

    # Prefer workbook TOTAL Current rows (Residential + Commercial summed) over
    # any single segment like Logistics (Hauling).
    if _SIZING_HEADER_TRIAD.search(body) or re.search(r"(?i)TAM\s*\(\$\s*million\)", body) or _SIZING_TOTAL_ROW.search(body):
        total_current = [0.0, 0.0, 0.0]
        total_n = 0
        for match in _SIZING_TOTAL_ROW.finditer(body):
            terr = (match.group(1) or "").strip()
            if not re.match(r"(?i)^current", terr):
                continue
            vals = _parse_triad_nums(match.group(2), match.group(3), match.group(4))
            if vals is None:
                continue
            total_current[0] += vals[0]
            total_current[1] += vals[1]
            total_current[2] += vals[2]
            total_n += 1
        if total_n >= 1:
            summed = (round(total_current[0], 1), round(total_current[1], 1), round(total_current[2], 1))
            note = (
                f"Combined Residential+Commercial TOTAL · Current ({total_n} sections)"
                if total_n > 1
                else "TOTAL · Current"
            )
            _apply_triad(summed, segment=note, territory="Current", score=20)
            return out

        # Fallback: best single segment row (hauling Current) when no TOTAL rows
        best: tuple[int, float, str, str, tuple[float, float, float]] | None = None
        for match in _SIZING_ROW_TRIAD.finditer(body):
            vals = _parse_triad_nums(match.group(3), match.group(4), match.group(5))
            if vals is None:
                continue
            seg = match.group(1) or ""
            terr = (match.group(2) or "Current").strip()
            score = 3
            if re.match(r"(?i)^current", terr):
                score += 2
            if re.search(r"(?i)hauling|logistics", seg):
                score += 3
            elif re.search(r"(?i)compost", seg):
                score += 1
            key = (score, vals[0], seg, terr, vals)
            if best is None or key[0] > best[0] or (key[0] == best[0] and key[1] > best[1]):
                best = key
        if best is not None:
            _apply_triad(best[4], segment=best[2], territory=best[3], score=best[0])
    return out


def extract_sizing_from_workbook_tables(tables: list[Any]) -> dict[str, MoneyMetric]:
    """Sum TOTAL Current TAM/SAM/SOM from structured workbook tables ($ million preferred)."""
    out: dict[str, MoneyMetric] = {}
    if not isinstance(tables, list):
        return out

    def _cell(row: list[Any], idx: int) -> str:
        if idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    def _f(raw: str) -> float | None:
        try:
            return float(str(raw).replace(",", "").replace("$", "").strip())
        except (TypeError, ValueError):
            return None

    million_totals: list[tuple[float, float, float]] = []
    dollar_totals: list[tuple[float, float, float]] = []

    for table in tables:
        if not isinstance(table, dict):
            continue
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        # Detect $ million vs absolute $ from a nearby header row
        header_blob = " ".join(
            " ".join(str(c) for c in (r or [])[:8]) for r in rows[:3] if isinstance(r, list)
        )
        is_million = bool(re.search(r"(?i)\$\s*million|million\)", header_blob))
        is_dollar = bool(re.search(r"(?i)TAM\s*\(\$\)|SAM\s*\(\$\)|SOM\s*\(\$\)", header_blob))
        for row in rows:
            if not isinstance(row, list) or len(row) < 5:
                continue
            # Columns vary: ['', 'TOTAL', 'Current', '', tam, sam, som, ...]
            labels = [_cell(row, i) for i in range(min(4, len(row)))]
            if not any(re.match(r"(?i)^total$", x) for x in labels):
                continue
            if not any(re.match(r"(?i)^current$", x) for x in labels):
                continue
            # Find first triad of numeric cells after the labels
            nums: list[float] = []
            for cell in row[1:]:
                v = _f(str(cell) if cell is not None else "")
                if v is None or v == 0:
                    # skip blanks / zeros in spacer columns
                    if nums:
                        break
                    continue
                nums.append(v)
                if len(nums) == 3:
                    break
            if len(nums) != 3:
                continue
            triad = (nums[0], nums[1], nums[2])
            if is_million or (not is_dollar and all(v < 5_000 for v in triad)):
                million_totals.append(triad)
            elif is_dollar or all(v >= 5_000 for v in triad):
                dollar_totals.append(triad)

    chosen = million_totals
    scale = "million"
    if not chosen and dollar_totals:
        # Convert absolute $ → $ million
        chosen = [(a / 1_000_000, b / 1_000_000, c / 1_000_000) for a, b, c in dollar_totals]
        scale = "million"
    if not chosen:
        return out

    # Deduplicate near-identical TOTAL rows (million vs $ sheets of same book)
    unique: list[tuple[float, float, float]] = []
    for triad in chosen:
        if any(
            abs(triad[0] - u[0]) < 1.0 and abs(triad[1] - u[1]) < 1.0
            for u in unique
        ):
            continue
        unique.append(triad)
    # Prefer summing distinct section totals (Residential + Commercial ≈ 2 rows)
    if len(unique) >= 2:
        tam = round(sum(u[0] for u in unique), 1)
        sam = round(sum(u[1] for u in unique), 1)
        som = round(sum(u[2] for u in unique), 1)
        note = f"Combined Residential+Commercial TOTAL · Current ({len(unique)} sections)"
    else:
        tam, sam, som = (round(unique[0][0], 1), round(unique[0][1], 1), round(unique[0][2], 1))
        note = "TOTAL · Current"

    for label, value in (("TAM", tam), ("SAM", sam), ("SOM", som)):
        out[label] = MoneyMetric(
            label=label,
            value=value,
            unit="USD",
            scale=scale,
            raw=f"{label} ${value:g}M ({note})"[:120],
            as_of="Current",
        )
    return out


def _uniq_floats(vals: list[float], *, limit: int = 6, near: float = 0.0) -> list[float]:
    out: list[float] = []
    for v in vals:
        if any(abs(v - existing) <= near for existing in out):
            continue
        out.append(v)
        if len(out) >= limit:
            break
    return out


def _extract_cagrs(text: str) -> list[float]:
    """Prefer TAM→SAM→SOM table CAGRs, then other CAGR mentions."""
    body = text or ""
    by_label: dict[str, float] = {}
    for match in _SIZING_CAGR_RE.finditer(body):
        label = match.group(1).upper()
        try:
            by_label[label] = float(match.group(2).replace("~", ""))
        except ValueError:
            continue
    ordered: list[float] = []
    for label in ("TAM", "SAM", "SOM"):
        if label in by_label:
            ordered.append(by_label[label])

    extras: list[float] = []
    for match in _CAGR_RE.finditer(body):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        try:
            extras.append(float(raw.replace("~", "")))
        except ValueError:
            continue
    if not ordered:
        for match in _TABLE_CAGR_RE.finditer(body):
            try:
                extras.append(float(match.group(1).replace("~", "")))
            except ValueError:
                continue
    return _uniq_floats([*ordered, *extras], near=0.5)


def _extract_penetrations(text: str) -> list[float]:
    vals: list[float] = []
    body = text or ""
    for match in re.finditer(r"(?i)\b(?:EV\s+)?penetration\b", body):
        window = body[match.start() : match.start() + 220]
        # Stay inside the penetration sentence when possible.
        stop = re.search(r"(?<=[.!?])\s+[A-Z]", window[30:]) if len(window) > 30 else None
        if stop:
            window = window[: 30 + stop.start() + 1]
        # Skip windows that are clearly CAGR table bleed.
        if re.search(r"(?i)\bcagr\b", window[:60]):
            continue
        for pm in re.finditer(
            r"(~?\d+(?:\.\d+)?)\s*(?:[–\-]\s*(~?\d+(?:\.\d+)?)\s*)?%",
            window,
        ):
            local = window[max(0, pm.start() - 20) : pm.end() + 20]
            if re.search(r"(?i)cagr", local):
                continue
            for raw in (pm.group(1), pm.group(2)):
                if not raw:
                    continue
                try:
                    vals.append(float(raw.replace("~", "")))
                except ValueError:
                    continue
    for match in _PENETRATION_PREFIX_RE.finditer(body):
        try:
            vals.append(float(match.group(1).replace("~", "")))
        except ValueError:
            continue
    return _uniq_floats(vals)


def _extract_unit_volumes(text: str) -> list[str]:
    units: list[str] = []
    body = text or ""
    for match in _UNITS_RE.finditer(body):
        note = match.group(0).strip()
        if len(note) < 8 or note.lower().startswith("000"):
            continue
        window = body[max(0, match.start() - 50) : match.end() + 40].lower()
        if any(bad in window for bad in _BAD_UNIT_WINDOW):
            continue
        units.append(note[:120])
        if len(units) >= 4:
            break
    return units


def _extract_prices(text: str) -> list[MoneyMetric]:
    out: list[MoneyMetric] = []
    body = text or ""

    def _add(
        unit: str,
        value: float,
        raw: str,
        *,
        label: str = "price_point",
        scale: str | None = None,
    ) -> None:
        for existing in out:
            if (
                existing.unit == unit
                and existing.value
                and abs(existing.value - value) / max(value, 1) < 0.03
            ):
                return
        out.append(
            MoneyMetric(
                label=label,
                value=value,
                unit=unit,
                scale=scale,
                raw=raw.strip()[:120],
            )
        )

    for match in _PRICE_RE.finditer(body):
        curr_raw = match.group(1) or ""
        raw_num = match.group(2).replace(",", "").replace("~", "")
        try:
            value = float(raw_num)
        except ValueError:
            continue
        label = "asp" if re.search(r"(?i)\basp\b|selling price", match.group(0)) else "price_point"
        if re.search(r"(?i)van westendorp|optimal|willingness", match.group(0)):
            label = "opp"
        _add(_map_currency(curr_raw) or "UNKNOWN", value, match.group(0), label=label)
        if len(out) >= 6:
            return out

    for match in _ASP_TABLE_RE.finditer(body):
        unit = _map_currency(match.group(1)) or "INR"
        scale_hint = (match.group("scale") or "").lower()
        nums = [float(n) for n in re.findall(r"~?(\d+(?:\.\d+)?)", match.group("vals") or "")]
        if not nums:
            continue
        company = nums[0]
        industry_raw: float | None = None
        # FY series often ends with a lower industry-average column.
        if len(nums) >= 3 and nums[-1] == min(nums) and nums[-1] < nums[-2]:
            company = nums[-2]
            industry_raw = nums[-1]
        elif len(nums) >= 2:
            company = nums[-1]
        mult = 1000.0 if re.search(r"000|’000|'000|thousand", scale_hint) else 1.0
        value = company * mult
        raw = match.group(0).strip()[:120]
        if industry_raw is not None:
            industry_asp_scaled = industry_raw * mult
            raw = f"{raw} | industry_asp={industry_asp_scaled:g}"
        _add(
            unit,
            value,
            raw,
            label="asp",
            scale="INR thousands" if mult == 1000 else None,
        )
        if len(out) >= 6:
            break

    for match in _FLAGSHIP_PRICE_RE.finditer(body):
        unit = _map_currency(match.group(1)) or "INR"
        try:
            value = float(match.group(2).replace(",", "").replace("~", ""))
        except ValueError:
            continue
        _add(unit, value, match.group(0), label="flagship")
        if len(out) >= 6:
            break
    return out


def _extract_volume(text: str, sentences: list[str]) -> MarketCeilingSpec:
    sizing = _extract_sizing(text)
    units = _extract_unit_volumes(text)
    growth = _filter_hits(_hits(sentences, _GROWTH, limit=6), _BAD_DEFINITION)
    # Prefer growth notes that mention CAGR / penetration / forecast sizing.
    growth = [
        g
        for g in growth
        if re.search(r"(?i)cagr|penetration|million unit|forecast|growing at|fy20", g)
    ][:5]
    model = MarketCeilingSpec(
        tam=sizing.get("TAM"),
        sam=sizing.get("SAM"),
        som=sizing.get("SOM"),
        cagr_pct=_extract_cagrs(text),
        penetration_pct=_extract_penetrations(text),
        unit_volume_notes=units,
        growth_notes=growth,
    )
    model.empty = not any(
        [
            model.tam,
            model.sam,
            model.som,
            model.cagr_pct,
            model.penetration_pct,
            model.unit_volume_notes,
            model.growth_notes,
        ]
    )
    return model


def _extract_definition(text: str, sentences: list[str]) -> MacroEnvironmentSpec:
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    clean = _filter_hits(clean, _BAD_DEFINITION)

    policy = _filter_hits(_hits(clean, _POLICY_DEF, limit=8), _BAD_DEFINITION)
    # Prefer FAME/PLI/subsidy wording; keep NITI only when tied to policy/support.
    policy = sorted(
        policy,
        key=lambda s: (
            0
            if re.search(r"(?i)fame|pli|subsidy|incentive|government support|policy reversal", s)
            else 1
            if re.search(r"(?i)niti", s)
            else 2
        ),
    )
    macro = _filter_hits(_hits(clean, _MACRO_DEF, limit=8), _BAD_DEFINITION)
    # Drop pure policy-risk lines from macro (they belong in policy_context).
    macro = [
        s
        for s in macro
        if not re.search(r"(?i)policy reversal|dependency on (?:fame|subsid)", s)
    ]
    framing = _filter_hits(_hits(clean, _FRAMING_DEF, limit=8), _BAD_DEFINITION)
    segments = _filter_hits(_hits(clean, _SEGMENT_DEF, limit=8), _BAD_DEFINITION)
    geo_table = _extract_regional_table(text)
    geo_hits = _filter_hits(_hits(clean, _GEO_DEF, limit=6), _BAD_DEFINITION)
    # Geo prose must not be subsidy/policy sentences that only matched via "state".
    geo_hits = [
        s
        for s in geo_hits
        if not re.search(r"(?i)fame|subsidy|pli|policy reversal|niti aayog", s)
        and not re.search(r"(?i)brand equity|aided recall|buyer segment", s)
    ]
    geographies = list(dict.fromkeys([*geo_table, *geo_hits]))

    claimed: set[str] = set()

    def _take(lines: list[str], *, limit: int) -> list[str]:
        kept: list[str] = []
        for line in lines:
            key = line.lower().strip()
            if len(key) < 25 or key in claimed:
                continue
            claimed.add(key)
            kept.append(line[:280])
            if len(kept) >= limit:
                break
        return kept

    # Exclusive buckets — policy first, then segments/framing, then macro, then geo.
    policy_out = _take(policy, limit=4)
    segments_out = _take(segments, limit=4)
    framing_out = _take(framing, limit=4)
    macro_out = _take(macro, limit=5)
    geo_out = _take(geographies, limit=5)

    model = MacroEnvironmentSpec(
        market_framing=framing_out,
        segments=segments_out,
        macro_drivers=macro_out,
        policy_context=policy_out,
        geographies=geo_out,
    )
    model.empty = not any(
        [
            model.market_framing,
            model.segments,
            model.macro_drivers,
            model.policy_context,
            model.geographies,
        ]
    )
    return model


def _extract_regional_table(text: str) -> list[str]:
    """Pull region share rows from Geographic Sales Distribution tables."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _GEO_TABLE_RE.finditer(text or ""):
        region = re.sub(r"\s+", " ", match.group(1)).strip()
        share = match.group(2)
        note = f"{region}: ~{share}% revenue/units share"
        key = re.sub(r"\s*&\s*others", "", region.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(note)
        if len(out) >= 6:
            break
    return out


def _filter_hits(hits: list[str], bad: tuple[str, ...]) -> list[str]:
    return [h for h in hits if not any(b in h.lower() for b in bad)]


def _near_duplicate(a: str, b: str, *, threshold: float = 0.55) -> bool:
    ta = {t for t in re.findall(r"[a-z]{4,}", (a or "").lower()) if len(t) >= 4}
    tb = {t for t in re.findall(r"[a-z]{4,}", (b or "").lower()) if len(t) >= 4}
    if not ta or not tb:
        return False
    return len(ta & tb) / float(min(len(ta), len(tb))) >= threshold


def _dedupe_near(lines: list[str], *, limit: int = 5) -> list[str]:
    kept: list[str] = []
    for line in lines:
        cleaned = re.sub(r"\s+", " ", (line or "").strip())
        if len(cleaned) < 20:
            continue
        if any(_near_duplicate(cleaned, k) for k in kept):
            continue
        kept.append(cleaned[:280])
        if len(kept) >= limit:
            break
    return kept


def _extract_demand(
    text: str,
    sentences: list[str],
    *,
    prior_spec: dict | None,
) -> RegionalDemandSpec:
    ceiling_tam = None
    consumes = False
    if prior_spec and isinstance(prior_spec.get("tam"), dict):
        try:
            ceiling_tam = MoneyMetric.model_validate(prior_spec["tam"])
            consumes = True
        except Exception:  # noqa: BLE001
            ceiling_tam = None
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    drivers = _filter_hits(_hits(clean, _DEMAND + _MACRO, limit=8), _BAD_DEMAND)
    drivers = _filter_hits(drivers, _DRIVER_RISK_ONLY)
    # Prefer structural demand (urbanization/fuel) ahead of pure outlook/penetration.
    drivers = sorted(
        drivers,
        key=lambda s: (
            0
            if re.search(r"(?i)urbanization|petrol|fuel|climate|boost demand|structural", s)
            else 1
            if re.search(r"(?i)fame|pli|government support|subsidy", s)
            else 2
        ),
    )
    drivers = _dedupe_near(drivers, limit=4)

    geo_table = _extract_regional_table(text)
    geo_prose = [
        s
        for s in _filter_hits(_hits(clean, _GEO, limit=6), _BAD_DEMAND)
        if re.search(r"(?i)tier-?3|rural|geographic mix|sales by region", s)
        and not re.search(r"(?i)fame|subsidy|policy reversal|niti", s)
    ]
    regional: list[str] = []
    seen_reg: set[str] = set()
    for item in [*geo_table, *geo_prose]:
        key = item.lower().strip()
        if key in seen_reg:
            continue
        seen_reg.add(key)
        regional.append(item[:280])
        if len(regional) >= 6:
            break

    risks = _filter_hits(_hits(clean, _CYCLE_RISK, limit=8), _BAD_DEMAND)
    risks = sorted(
        risks,
        key=lambda s: (
            0
            if re.search(r"(?i)subsidy|fame|policy|demand risk|headwind|seasonal|monsoon", s)
            else 1
        ),
    )
    risks = _dedupe_near(risks, limit=4)
    # Collapse multiple subsidy/FAME dependency variants to one.
    collapsed: list[str] = []
    saw_subsidy = False
    for risk in risks:
        is_sub = bool(re.search(r"(?i)\bsubsid|\bfame\b", risk))
        if is_sub and saw_subsidy:
            continue
        if is_sub:
            saw_subsidy = True
        collapsed.append(risk)
    risks = collapsed[:3]

    # Exclusive: a line cannot sit in both drivers and cycle_risks.
    claimed = {d.lower() for d in drivers}
    risks = [r for r in risks if r.lower() not in claimed]

    model = RegionalDemandSpec(
        demand_drivers=drivers,
        regional_signals=regional,
        cycle_risks=risks,
        consumes_ceiling=consumes,
        ceiling_tam=ceiling_tam,
    )
    model.empty = not any(
        [model.demand_drivers, model.regional_signals, model.cycle_risks, model.ceiling_tam]
    )
    return model


def _extract_pricing(
    text: str,
    sentences: list[str],
    *,
    prior_spec: dict | None,
) -> OptimalPriceSpec:
    ceiling_sam = None
    consumes = False
    if prior_spec and isinstance(prior_spec.get("sam"), dict):
        try:
            ceiling_sam = MoneyMetric.model_validate(prior_spec["sam"])
            consumes = True
        except Exception:  # noqa: BLE001
            ceiling_sam = None
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    prices = _extract_prices(text)

    def _pricing_clean(hits: list[str]) -> list[str]:
        return [
            h
            for h in hits
            if not any(bad in h.lower() for bad in _BAD_PRICING)
        ]

    notes = _pricing_clean(_hits(clean, _PRICE_WORDS, limit=6))
    power = _pricing_clean(
        _hits(
            clean,
            ("pricing power", "premium", "discount", "elasticity", "willingness to pay"),
            limit=4,
        )
    )
    # Prefer real prose notes — do not echo raw price extractions into notes/power.
    notes = [n for n in notes if not re.search(r"(?i)^extracted |observed asp", n)][:5]
    power = [p for p in power if not re.search(r"(?i)^observed asp", p)][:4]

    asp = next((p for p in prices if p.label == "asp"), None)
    industry_val: float | None = None
    if asp and asp.raw:
        ind_m = re.search(r"industry_asp=(\d+(?:\.\d+)?)", asp.raw)
        if ind_m:
            industry_val = float(ind_m.group(1))
    flagship = next((p for p in prices if p.label == "flagship"), None)
    if asp and industry_val and asp.value > industry_val:
        premium = (asp.value - industry_val) / industry_val * 100.0
        power = list(
            dict.fromkeys(
                [
                    f"ASP ~{asp.unit} {asp.value:g} vs industry ~{industry_val:g} "
                    f"(~{premium:.0f}% premium).",
                    *power,
                ]
            )
        )[:4]
    if flagship and asp and flagship.value > asp.value * 1.2:
        notes = list(
            dict.fromkeys(
                [
                    f"Flagship list ({flagship.unit} {flagship.value:g}) sits above "
                    f"blended ASP ({asp.unit} {asp.value:g}).",
                    *notes,
                ]
            )
        )[:5]
    if not notes and prices:
        lead = prices[0]
        notes = [
            f"{lead.label.upper()}: {lead.unit} {lead.value:g}"
            + (f" ({lead.raw})" if lead.raw else "")
        ]

    prices = sorted(
        prices,
        key=lambda p: (
            0 if p.label == "asp" else 1 if p.label == "flagship" else 2 if p.label == "opp" else 3,
            -(p.value or 0),
        ),
    )

    model = OptimalPriceSpec(
        price_points=prices,
        pricing_notes=notes,
        power_signals=power,
        consumes_ceiling=consumes,
        ceiling_sam=ceiling_sam,
    )
    model.empty = not any(
        [model.price_points, model.pricing_notes, model.power_signals, model.ceiling_sam]
    )
    return model


def extract_deep_dive_spec(
    slug: str,
    text: str,
    *,
    sources: list[str] | None = None,
    coverage: str = "missing",
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    """Return typed Market Analysis spec JSON. Heuristic only; no API key."""
    clipped = (text or "")[:50_000]
    sentences = _sentences(clipped)
    src = list(sources or [])

    if slug == "market_volume_and_growth":
        model = _extract_volume(clipped, sentences)
    elif slug == "market_definition":
        model = _extract_definition(clipped, sentences)
    elif slug == "demand_drivers":
        model = _extract_demand(clipped, sentences, prior_spec=prior_spec)
    elif slug == "market_pricing":
        model = _extract_pricing(clipped, sentences, prior_spec=prior_spec)
    else:
        return {"slug": slug, "empty": True, "extractor": "none"}

    if coverage == "missing" and not clipped.strip():
        model.empty = True

    payload = model.model_dump(mode="json")
    payload["slug"] = slug
    payload["track"] = "A"
    payload["sources"] = src
    payload["coverage"] = coverage
    payload["extractor"] = "heuristic_v1"
    payload["metrics"] = _metrics_summary(slug, payload)
    return payload


def _metrics_summary(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "market_volume_and_growth":
        return {
            "has_tam": bool(payload.get("tam")),
            "has_sam": bool(payload.get("sam")),
            "has_som": bool(payload.get("som")),
            "cagr_count": len(payload.get("cagr_pct") or []),
            "penetration_count": len(payload.get("penetration_pct") or []),
        }
    if slug == "market_definition":
        return {
            "macro_count": len(payload.get("macro_drivers") or []),
            "segment_count": len(payload.get("segments") or []),
            "policy_count": len(payload.get("policy_context") or []),
        }
    if slug == "demand_drivers":
        return {
            "driver_count": len(payload.get("drivers") or payload.get("demand_drivers") or []),
            "transmission_count": len(payload.get("transmission") or []),
            "counter_count": len(payload.get("counter_drivers") or payload.get("cycle_risks") or []),
            "regional_count": len(payload.get("regional_signals") or []),
            "consumes_ceiling": bool(payload.get("consumes_ceiling")),
        }
    if slug == "market_pricing":
        return {
            "price_point_count": len(payload.get("price_points") or []),
            "note_count": len(payload.get("pricing_notes") or []),
            "consumes_ceiling": bool(payload.get("consumes_ceiling")),
        }
    return {}


def findings_from_market_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    """Turn structured market metrics into short finding bullets for the agent output."""
    out: list[str] = []
    if slug == "market_volume_and_growth":
        bottom = spec.get("bottom_up") if isinstance(spec.get("bottom_up"), dict) else {}
        if bottom.get("bottom_up_size") and not str(bottom["bottom_up_size"]).startswith("Information"):
            out.append(f"Bottom-up: {str(bottom['bottom_up_size'])[:200]}")
        if spec.get("market_growth_note"):
            out.append(f"Market growth: {str(spec['market_growth_note'])[:200]}")
        cg = spec.get("company_growth") if isinstance(spec.get("company_growth"), dict) else {}
        if cg.get("historical_growth") and not str(cg["historical_growth"]).startswith("Information"):
            out.append(f"Company growth: {str(cg['historical_growth'])[:200]}")
        plan = spec.get("plan_vs_market") if isinstance(spec.get("plan_vs_market"), dict) else {}
        if plan.get("multiple") and not str(plan["multiple"]).startswith("Information"):
            out.append(f"Plan/market: {plan['multiple']}")
        if not out:
            for key in ("tam", "sam", "som"):
                metric = spec.get(key)
                if isinstance(metric, dict) and metric.get("value") is not None:
                    scale = metric.get("scale") or ""
                    as_of = f" ({metric['as_of']})" if metric.get("as_of") else ""
                    out.append(
                        f"{metric.get('label', key.upper())}: "
                        f"{metric.get('unit', 'USD')} {metric['value']} {scale}".strip()
                        + as_of
                    )
            if spec.get("cagr_pct"):
                out.append("CAGR signals: " + ", ".join(f"{v}%" for v in spec["cagr_pct"][:4]))
            if spec.get("penetration_pct"):
                out.append(
                    "Penetration: " + ", ".join(f"{v}%" for v in spec["penetration_pct"][:4])
                )
            out.extend(spec.get("growth_notes") or [])
    elif slug == "market_definition":
        perim = spec.get("perimeter") if isinstance(spec.get("perimeter"), dict) else {}
        for axis in ("service", "customer_types", "geography", "value_chain_stage"):
            val = perim.get(axis)
            if val and not str(val).startswith("Information") and str(val) != "N/A (data room did not provide it)":
                out.append(f"{axis}: {str(val)[:200]}")
        gate = spec.get("approval_gate") if isinstance(spec.get("approval_gate"), dict) else {}
        if gate.get("status"):
            out.append(f"Approval gate: {gate.get('status')}")
        if not out:
            out.extend(spec.get("market_framing") or [])
            out.extend(spec.get("macro_drivers") or [])
            out.extend(spec.get("policy_context") or [])
            out.extend(spec.get("segments") or [])
            out.extend(spec.get("geographies") or [])
        addr = spec.get("addressable_market") if isinstance(spec.get("addressable_market"), dict) else {}
        if addr.get("value") and not str(addr["value"]).startswith("Information"):
            out.append(f"Addressable: {addr['value']}")
    elif slug == "demand_drivers":
        for row in (spec.get("drivers") or [])[:3]:
            if isinstance(row, dict) and row.get("driver"):
                if not str(row["driver"]).startswith("Information"):
                    out.append(f"Driver: {str(row['driver'])[:160]}")
        for row in (spec.get("transmission") or [])[:2]:
            if isinstance(row, dict) and row.get("chain_status"):
                out.append(f"Transmission: {str(row.get('driver') or '')[:60]} — {str(row['chain_status'])[:100]}")
        if not out:
            out.extend(spec.get("demand_drivers") or [])
            out.extend(spec.get("regional_signals") or [])
            out.extend(spec.get("cycle_risks") or [])
        if spec.get("consumes_ceiling") and isinstance(spec.get("ceiling_tam"), dict):
            tam = spec["ceiling_tam"]
            out.append(
                f"Uses Market Ceiling TAM: {tam.get('unit', 'USD')} "
                f"{tam.get('value')} {tam.get('scale') or ''}".strip()
            )
    elif slug == "market_pricing":
        realised = spec.get("realised_prices") if isinstance(spec.get("realised_prices"), list) else []
        for row in realised[:2]:
            if isinstance(row, dict) and row.get("realised_net_price"):
                if not str(row["realised_net_price"]).startswith("Information"):
                    out.append(f"Realised: {str(row['realised_net_price'])[:160]}")
        for row in (spec.get("competitor_comparisons") or [])[:2]:
            if isinstance(row, dict) and row.get("competitor"):
                if not str(row["competitor"]).startswith("Information"):
                    out.append(f"Comp: {row['competitor']}")
        if not out:
            for p in spec.get("price_points") or []:
                if isinstance(p, dict) and p.get("value") is not None:
                    label = str(p.get("label") or "price").upper()
                    out.append(
                        f"{label}: {p.get('unit', '')} {p['value']:g}".strip()
                    )
            out.extend(spec.get("pricing_notes") or [])
            out.extend(spec.get("power_signals") or [])
        if spec.get("consumes_ceiling") and isinstance(spec.get("ceiling_sam"), dict):
            sam = spec["ceiling_sam"]
            out.append(
                f"Uses Market Ceiling SAM: {sam.get('unit', 'USD')} "
                f"{sam.get('value')} {sam.get('scale') or ''}".strip()
            )
    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip()[:280])
        if len(deduped) >= 8:
            break
    return deduped
