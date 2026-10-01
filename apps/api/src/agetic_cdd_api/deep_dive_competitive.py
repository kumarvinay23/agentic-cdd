"""Slice 2 heuristic extractors for Competitive Landscape Deep Dive agents (no LLM)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from agetic_cdd_api.deep_dive_extractors import (
    _hits,
    _is_noisy_sentence,
    _sentences,
)

COMPETITIVE_SLUGS: frozenset[str] = frozenset(
    {
        "competitor_identification",
        "competitive_differentiation",
        "market_share_strategy",
        "swot_analysis",
    }
)

# Multi-word name hints used only when those tokens appear in the source text.
# Never injected as peers when absent from the VDR.
_NAME_HINTS = (
    "Ola Electric",
    "Ather Energy",
    "TVS iQube",
    "Bajaj Chetak",
    "Hero Vida",
    "Ampere (Greaves)",
)

# Preferred full-matrix match (any order of metric blocks after Dimension names).
_LANDSCAPE_RE = re.compile(
    r"(?i)Dimension\s+(?P<names>.+?)\s+"
    r"(?=Market Share|Units Sold|Flagship Price)"
    r"(?P<body>.{0,900}?)"
    r"(?=Porter|Market Share Trend|Competitive Verdict|\Z)",
    re.S,
)

_DIMENSION_NAMES_RE = re.compile(
    r"(?i)Dimension\s+(.+?)\s+(?=Market Share|Units Sold|Flagship Price|NPS Score)"
)

# Independent metric rows — order-agnostic (flattened PDF-friendly).
_ROW_SHARE_RE = re.compile(
    r"(?i)Market Share\s*(?:\([^)]*\))?\s+((?:~?\d+(?:\.\d+)?%\s*){2,})"
)
_ROW_UNITS_RE = re.compile(
    r"(?i)Units Sold\s*(?:\([^)]*\))?\s+((?:~?\d+(?:\.\d+)?\s*){2,})"
)
_ROW_PRICE_RE = re.compile(
    r"(?i)Flagship Price\s*(?:\([^)]*\))?\s+((?:[\d,]+\s*){2,})"
)

_TREND_LABELS = (
    "Strong Gain",
    "Steady Growth",
    "Losing Share",
    "Declining",
    "Gaining",
    "Fragmented",
)
_TREND_ROW_RE = re.compile(
    r"(?i)([A-Za-z][A-Za-z0-9/.+\-]*(?:\s+[A-Za-z0-9/.+\-()]+){0,3})\s+"
    r"(~?\d+(?:\.\d+)?)%\s+(~?\d+(?:\.\d+)?)%\s+(~?\d+(?:\.\d+)?)%\s+"
    r"(" + "|".join(_TREND_LABELS) + r")\b"
)
_TREND_NAME_BLOCKLIST = frozenset(
    {
        "company",
        "market share trend",
        "trend",
        "fy2022",
        "dimension",
        "insight snapshot",
    }
)

_FORCE_RE = re.compile(
    r"(?i)(Threat of New Entrants|Bargaining Power of Suppliers|Bargaining Power of Buyers|"
    r"Threat of Substitutes|Competitive Rivalry)\s*[—\-–:]\s*"
    r"(LOW(?:\s*[-–]\s*MEDIUM)?|MEDIUM|HIGH)\b"
    r"\s*([^.]{20,220})"
)

_VERDICT_RE = re.compile(
    r"(?i)Competitive Verdict\s+(.+?)(?=\s*Sustained market leadership|\Z)",
    re.S,
)

_NPS_ROW_RE = re.compile(
    r"(?i)NPS Score\s+((?:\d+\s+){2,})"
)

# Soft stop at next matrix row or section; do not require Fast Charging specifically.
_SOFTWARE_ROW_RE = re.compile(
    r"(?i)Software\s*/\s*OTA\s+(.+?)"
    r"(?=\s+(?:Fast Charging|Charging Infrastructure|Dealer(?:/Service)?|"
    r"Service Network|NPS Score|Valuation|Porter|Market Share Trend)|$)",
    re.S,
)

_DIFF_NEEDLES = (
    "moat", "differenti", "software", "ota", "moveos", "atherstack",
    "service reliability", "manufacturing scale", "superior software",
    "software capabilities",
)
_BAD_DIFF = (
    "threat of", "bargaining power", "porter", "substitutes", "new entrants",
    "competitive rivalry", "range anxiety", "ice scooters remain",
)
_WINLOSS_NEEDLES = (
    "strong gain", "losing share", "declining", "gaining", "steady growth",
    "win", "loss", "market share", "leadership",
)
_SWOT_STRENGTH = (
    "leading market share", "superior software", "manufacturing scale",
    "software capabilities", "holds the leading",
)
_SWOT_WEAK = (
    "underperform", "service reliability", "nps significantly", "service experience",
    "nps score",
)
_SWOT_OPP = (
    "penetration", "cagr", "niti", "14x", "annual market",
)
_SWOT_THREAT = (
    "legacy oem", "new entrant", "chinese oem", "supplier",
    "substitute", "competitive response", "moat is narrowing", "rivalry",
)
_BAD_STRENGTH = (
    "requires", "improvement", "underperform", "narrowing", "risk",
)


class CompetitorRow(BaseModel):
    name: str
    market_share_pct: float | None = None
    units_000s: float | None = None
    flagship_price_inr: float | None = None
    trend: str | None = None
    nps: float | None = None
    software: str | None = None


class PorterForce(BaseModel):
    force: str
    intensity: str
    note: str = ""


class CompetitorIdentificationSpec(BaseModel):
    """DD-04 — Competitive Positioning Matrix."""

    document: str = "Competitive Positioning Matrix"
    dd_code: str = "DD-04"
    competitors: list[CompetitorRow] = Field(default_factory=list)
    positioning_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class CompetitiveDifferentiationSpec(BaseModel):
    """DD-06 — Imitability Ladder Report."""

    document: str = "Imitability Ladder Report"
    dd_code: str = "DD-06"
    differentiators: list[str] = Field(default_factory=list)
    moat_signals: list[str] = Field(default_factory=list)
    feature_gaps: list[str] = Field(default_factory=list)
    peer_software: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class MarketShareStrategySpec(BaseModel):
    """DD-05 — Win/Loss Matrix."""

    document: str = "Win/Loss Matrix"
    dd_code: str = "DD-05"
    share_trends: list[CompetitorRow] = Field(default_factory=list)
    wins: list[str] = Field(default_factory=list)
    losses: list[str] = Field(default_factory=list)
    strategy_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class SwotAnalysisSpec(BaseModel):
    """DD-07 — Buyer's Perspective Analysis (SWOT)."""

    document: str = "Buyer's Perspective Analysis"
    dd_code: str = "DD-07"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)
    porter_forces: list[PorterForce] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


def _parse_floats(blob: str) -> list[float]:
    vals: list[float] = []
    for raw in re.findall(r"~?([\d,]+(?:\.\d+)?)", blob or ""):
        try:
            vals.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return vals


def _split_competitor_names(raw: str) -> list[str]:
    """Split a Dimension header into peer names without inventing absent OEMs."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return []

    # Collect hint matches in document order; longer spans win on overlap.
    hits: list[tuple[int, int, str]] = []
    for name in _NAME_HINTS:
        for match in re.finditer(re.escape(name), text, flags=re.I):
            hits.append((match.start(), match.end(), name))
    hits.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    found: list[str] = []
    cursor = -1
    covered = list(text)
    for start, end, name in hits:
        if start < cursor:
            continue
        found.append(name)
        for i in range(start, end):
            covered[i] = " "
        cursor = end

    remaining = "".join(covered)
    leftover = [p.strip(" ,;|") for p in re.split(r"\s{2,}|\s*\|\s*", remaining) if p.strip(" ,;|")]
    if leftover:
        for chunk in leftover:
            tokens = chunk.split()
            if len(tokens) >= 2 and all(t[:1].isupper() for t in tokens if t):
                if len(tokens) % 2 == 0 and len(tokens) >= 4:
                    for i in range(0, len(tokens), 2):
                        found.append(f"{tokens[i]} {tokens[i + 1]}")
                else:
                    found.append(chunk)
            elif chunk and chunk[0].isupper() and len(chunk) > 2:
                found.append(chunk)

    out: list[str] = []
    seen: set[str] = set()
    for name in found:
        key = name.lower()
        if key in seen or key in _TREND_NAME_BLOCKLIST or len(name) < 3:
            continue
        seen.add(key)
        out.append(name)
    return out[:8]


def _clean_trend_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").strip())
    name = re.sub(r"(?i)^(FY\s?\d{2,4}E?\s+)+", "", name).strip()
    name = re.sub(r"(?i)^(?:Trend|Company)\s+", "", name).strip()
    name = re.sub(r"(?i)^.*?\bTrend\s+", "", name).strip()
    return name


def _metric_floats(body: str, pattern: re.Pattern[str]) -> list[float]:
    match = pattern.search(body)
    return _parse_floats(match.group(1)) if match else []


def _software_vals(body: str) -> list[str]:
    soft_match = _SOFTWARE_ROW_RE.search(body)
    if not soft_match:
        return []
    chunk = re.sub(r"\s+", " ", soft_match.group(1)).strip()
    return re.findall(r"(?i)Yes\s*\([^)]+\)|Yes|No|Basic", chunk)


def _resolve_peer_names(body: str) -> list[str]:
    dim = _DIMENSION_NAMES_RE.search(body)
    if dim:
        names = _split_competitor_names(dim.group(1))
        if names:
            return names
    return [row.name for row in _extract_trend_rows(body) if row.name.lower() != "others"][:8]


def _extract_landscape_competitors(text: str) -> list[CompetitorRow]:
    body = text or ""
    names = _resolve_peer_names(body)

    scoped = body
    landscape = _LANDSCAPE_RE.search(body)
    if landscape:
        scoped = landscape.group("names") + " " + landscape.group("body")
        if not names:
            names = _split_competitor_names(landscape.group("names"))

    shares = _metric_floats(scoped, _ROW_SHARE_RE) or _metric_floats(body, _ROW_SHARE_RE)
    units = _metric_floats(scoped, _ROW_UNITS_RE) or _metric_floats(body, _ROW_UNITS_RE)
    prices = _metric_floats(scoped, _ROW_PRICE_RE) or _metric_floats(body, _ROW_PRICE_RE)

    nps_match = _NPS_ROW_RE.search(body)
    nps_vals = _parse_floats(nps_match.group(1)) if nps_match else []
    software_vals = _software_vals(scoped) or _software_vals(body)

    trends = {row.name: row.trend for row in _extract_trend_rows(body)}
    if not names and (shares or units or prices):
        col_count = max(len(shares), len(units), len(prices), len(nps_vals), 0)
        names = [f"Peer {i + 1}" for i in range(min(col_count, 8))]

    out: list[CompetitorRow] = []
    for i, name in enumerate(names[:8]):
        out.append(
            CompetitorRow(
                name=name,
                market_share_pct=shares[i] if i < len(shares) else None,
                units_000s=units[i] if i < len(units) else None,
                flagship_price_inr=prices[i] if i < len(prices) else None,
                trend=trends.get(name),
                nps=nps_vals[i] if i < len(nps_vals) else None,
                software=software_vals[i] if i < len(software_vals) else None,
            )
        )
    return out


def _extract_trend_rows(text: str) -> list[CompetitorRow]:
    out: list[CompetitorRow] = []
    seen: set[str] = set()
    for match in _TREND_ROW_RE.finditer(text or ""):
        name = _clean_trend_name(match.group(1))
        key = name.lower()
        if not name or key in seen or key in _TREND_NAME_BLOCKLIST:
            continue
        if re.fullmatch(r"FY\d{2,4}E?", name, re.I):
            continue
        seen.add(key)
        try:
            latest = float(match.group(4).replace("~", ""))
        except ValueError:
            latest = None
        out.append(
            CompetitorRow(
                name=name,
                market_share_pct=latest,
                trend=match.group(5).strip(),
            )
        )
    return out


def _extract_porter(text: str) -> list[PorterForce]:
    out: list[PorterForce] = []
    for match in _FORCE_RE.finditer(text or ""):
        note = re.sub(r"\s+", " ", match.group(3)).strip(" .")
        out.append(
            PorterForce(
                force=match.group(1).strip(),
                intensity=re.sub(r"\s+", "-", match.group(2).strip().upper()),
                note=note[:220],
            )
        )
    return out[:6]


def _verdict_sentences(text: str) -> list[str]:
    match = _VERDICT_RE.search(text or "")
    parts: list[str] = []
    if match:
        blob = re.sub(r"\s+", " ", match.group(1)).strip()
        parts.extend(
            p.strip() for p in re.split(r"(?<=[.!?])\s+", blob) if len(p.strip()) > 30
        )
    trail = re.search(r"(?i)(Sustained market leadership[^.]*\.)", text or "")
    if trail:
        parts.append(trail.group(1).strip())
    # Also pull moat / service sentences if present as standalone prose.
    for pat in (
        r"(?i)(However, the competitive moat is narrowing[^.]*\.)",
        r"(?i)(The key battleground is service reliability[^.]*\.)",
    ):
        m = re.search(pat, text or "")
        if m:
            parts.append(m.group(1).strip())
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _extract_competitor_identification(text: str, sentences: list[str]) -> CompetitorIdentificationSpec:
    competitors = _extract_landscape_competitors(text)
    # Positioning matrix reads best share-desc (leaders first).
    competitors = sorted(
        competitors,
        key=lambda c: (
            c.market_share_pct is not None,
            c.market_share_pct or 0.0,
        ),
        reverse=True,
    )
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _hits(
        clean,
        ("competitive", "competitor", "landscape", "position", "peer", "rival"),
        limit=4,
    )
    notes = list(dict.fromkeys([*_verdict_sentences(text), *notes]))
    notes = [
        n
        for n in notes
        if not re.search(
            r"(?i)requires|operational execution|alongside continued|"
            r"product and technology investment",
            n,
        )
    ]
    notes = sorted(
        notes,
        key=lambda s: (
            0
            if re.search(r"(?i)leading market share|holds the leading", s)
            else 1
            if re.search(r"(?i)\bmoat\b", s)
            else 2
            if re.search(r"(?i)battleground|service reliability|underperform", s)
            else 3
        ),
    )
    model = CompetitorIdentificationSpec(
        competitors=competitors,
        positioning_notes=notes[:3],
    )
    model.empty = not any([model.competitors, model.positioning_notes])
    return model


def _extract_differentiation(text: str, sentences: list[str]) -> CompetitiveDifferentiationSpec:
    competitors = _extract_landscape_competitors(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    pool = list(dict.fromkeys([*_verdict_sentences(text), *clean]))
    raw_hits = [
        s
        for s in _hits(pool, _DIFF_NEEDLES, limit=8)
        if not any(bad in s.lower() for bad in _BAD_DIFF)
    ]
    # Durable advantages — not erosion or service underperformance.
    diffs = [
        s
        for s in raw_hits
        if re.search(
            r"(?i)software capabilities|superior software|manufacturing scale|"
            r"moveos|atherstack|differenti|leading market share",
            s,
        )
        and not re.search(r"(?i)narrowing|underperform|battleground|requires", s)
    ]
    # Moat status only (durability or erosion) — exclude service/NPS bleed.
    moat = [
        s
        for s in raw_hits
        if re.search(r"(?i)\bmoat\b|imitab", s)
        and not re.search(r"(?i)underperform|battleground|service reliability", s)
    ]
    # Soft fill: software platform as hard-to-imitate asset if no prose moat line.
    if not moat:
        for c in competitors:
            if c.software and re.search(r"(?i)yes\s*\(|moveos|atherstack", c.software):
                moat.append(f"{c.name} software/OTA platform: {c.software}")
                break

    peer_software = [f"{c.name}: {c.software}" for c in competitors if c.software]
    feature_gaps = _feature_gaps_vs_peers(competitors, pool)

    model = CompetitiveDifferentiationSpec(
        differentiators=diffs[:5],
        moat_signals=moat[:4],
        feature_gaps=feature_gaps[:5],
        peer_software=peer_software[:5],
    )
    model.empty = not any(
        [model.differentiators, model.moat_signals, model.feature_gaps, model.peer_software]
    )
    return model


def _feature_gaps_vs_peers(competitors: list[CompetitorRow], pool: list[str]) -> list[str]:
    """Real gaps vs peers — not a full matrix dump."""
    gaps: list[str] = []
    for s in pool:
        if re.search(r"(?i)service reliability|underperform|battleground", s):
            gaps.append(s)
            break

    scored = [c for c in competitors if c.nps is not None]
    if len(scored) >= 2:
        # Focal ≈ highest share; else first row.
        with_share = [c for c in competitors if c.market_share_pct is not None]
        focal = max(with_share, key=lambda c: c.market_share_pct or 0.0) if with_share else competitors[0]
        leaders = [c for c in scored if c.name != focal.name]
        if focal.nps is not None and leaders:
            best = max(leaders, key=lambda c: c.nps or 0.0)
            if best.nps is not None and best.nps > focal.nps:
                gaps.append(
                    f"NPS gap: {focal.name} {focal.nps:g} vs {best.name} {best.nps:g} (category leader)"
                )

    # Soft fill: peer software ladder snippet when no prose/NPS gaps.
    if not gaps:
        for c in competitors:
            bits: list[str] = []
            if c.nps is not None:
                bits.append(f"NPS {c.nps:g}")
            if c.software:
                bits.append(f"OTA/software {c.software}")
            if bits:
                gaps.append(f"{c.name}: " + "; ".join(bits))
    return gaps


def _extract_share_strategy(text: str, sentences: list[str]) -> MarketShareStrategySpec:
    trends = _extract_trend_rows(text)
    if not trends:
        trends = [
            c
            for c in _extract_landscape_competitors(text)
            if c.market_share_pct is not None
        ]
    # Prefer highest-share named peer as the focal company for win/loss framing.
    named = [r for r in trends if r.name.lower() not in {"others", "other"}]
    focal = None
    if named:
        focal = max(
            named,
            key=lambda r: (
                1 if (r.trend or "").lower() in {"strong gain", "gaining"} else 0,
                r.market_share_pct or 0.0,
            ),
        )

    wins: list[str] = []
    losses: list[str] = []
    for row in named:
        label = (row.trend or "").lower()
        share = f"{row.market_share_pct:g}%" if row.market_share_pct is not None else "n/a"
        line = f"{row.name}: {row.trend} (share {share})"
        is_focal = focal is not None and row.name == focal.name
        if is_focal and any(k in label for k in ("strong gain", "gaining")):
            wins.append(line)
        elif is_focal and any(k in label for k in ("losing", "declining")):
            losses.append(line)
        elif not is_focal and any(k in label for k in ("losing", "declining")):
            # Competitor share loss = share opportunity / "win" context for focal.
            wins.append(f"Share opportunity · {line}")
        elif not is_focal and any(k in label for k in ("strong gain", "gaining")):
            # Competitor gain = competitive loss pressure.
            losses.append(f"Share pressure · {line}")
        # Steady Growth / Fragmented stay on share_trends only (neutral).

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    pool = list(dict.fromkeys([*_verdict_sentences(text), *clean]))
    notes = _hits(
        pool,
        ("market leadership", "leading market share", "share position", "strong gain", "leadership"),
        limit=5,
    )
    notes = [
        n
        for n in notes
        if not re.search(
            r"(?i)Market Share Trend Company|FY2022 FY2023|"
            r"service reliability|battleground|underperform|"
            r"requires|operational execution|improvement|"
            r"moat is narrowing",
            n,
        )
    ]
    # Prefer share-position prose; soft-fill from focal trend if none.
    if not notes:
        notes = [
            n
            for n in _verdict_sentences(text)
            if re.search(r"(?i)leading market share|share position", n)
            and not re.search(r"(?i)requires|underperform|narrowing", n)
        ][:2]
    if not notes and focal is not None and focal.trend:
        share = f"{focal.market_share_pct:g}%" if focal.market_share_pct is not None else "n/a"
        notes = [f"{focal.name} holds {share} share with trend {focal.trend}."]

    # Keep share_trends ordered by latest share desc when available.
    trends_sorted = sorted(
        trends,
        key=lambda r: (r.market_share_pct is not None, r.market_share_pct or 0.0),
        reverse=True,
    )
    model = MarketShareStrategySpec(
        share_trends=trends_sorted,
        wins=wins[:5],
        losses=losses[:5],
        strategy_notes=notes[:4],
    )
    model.empty = not any(
        [model.share_trends, model.wins, model.losses, model.strategy_notes]
    )
    return model


def _clean_swot_line(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    cleaned = re.sub(r"^[\W_]{1,4}", "", cleaned).strip()
    # Drop table-section glue: "Commercial Risks NPS significantly…"
    cleaned = re.sub(r"(?i)^Commercial Risks\s*[—\-–:]?\s*", "", cleaned)
    cleaned = re.sub(r"(?i)\b(Commercial Risks)\s+(NPS)\b", r"\1 — \2", cleaned)
    return cleaned.strip()


def _dedupe_lines(lines: list[str], *, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        cleaned = _clean_swot_line(line)
        key = cleaned.lower()
        if len(cleaned) < 25 or key in seen:
            continue
        seen.add(key)
        out.append(cleaned[:280])
        if len(out) >= limit:
            break
    return out


def _extract_swot(text: str, sentences: list[str]) -> SwotAnalysisSpec:
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    verdict = _verdict_sentences(text)
    pool = list(dict.fromkeys([*verdict, *clean]))
    porter = _extract_porter(text)

    strengths = [
        s
        for s in _hits(pool, _SWOT_STRENGTH, limit=6)
        if not any(bad in s.lower() for bad in _BAD_STRENGTH)
    ]
    if not strengths:
        strengths = [
            s
            for s in verdict
            if re.search(r"(?i)holds the leading|superior software|manufacturing scale", s)
            and not any(bad in s.lower() for bad in _BAD_STRENGTH)
        ][:3]

    weaknesses = [
        s
        for s in _hits(pool, _SWOT_WEAK, limit=6)
        if "moat" not in s.lower()
    ]
    opportunities = _hits(pool, _SWOT_OPP, limit=5)
    # Keep Porter prose out of hit-based threats — formatted force rows own that lane.
    threats = [
        s
        for s in _hits(pool, _SWOT_THREAT, limit=6)
        if not re.search(
            r"(?i)underperform|nps significantly|service experience|"
            r"threat of|bargaining power|competitive rivalry|deep pockets",
            s,
        )
    ]
    for force in sorted(
        porter,
        key=lambda f: 0 if f.intensity == "HIGH" else 1 if "MEDIUM" in f.intensity else 2,
    ):
        if force.intensity in {"HIGH", "MEDIUM", "LOW-MEDIUM"}:
            threats.append(f"{force.force} — {force.intensity}: {force.note}"[:240])

    strengths = _dedupe_lines(strengths, limit=4)
    weaknesses = _dedupe_lines(weaknesses, limit=4)
    opportunities = _dedupe_lines(opportunities, limit=4)
    threats = _dedupe_lines(threats, limit=6)

    claimed: set[str] = set()

    def _exclusive(lines: list[str]) -> list[str]:
        kept: list[str] = []
        for line in lines:
            key = line.lower()
            if key in claimed:
                continue
            claimed.add(key)
            kept.append(line)
        return kept

    strengths = _exclusive(strengths)
    weaknesses = _exclusive(weaknesses)
    opportunities = _exclusive(opportunities)
    threats = _exclusive(threats)

    model = SwotAnalysisSpec(
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=opportunities,
        threats=threats,
        porter_forces=porter,
    )
    model.empty = not any(
        [
            model.strengths,
            model.weaknesses,
            model.opportunities,
            model.threats,
            model.porter_forces,
        ]
    )
    return model


def extract_competitive_spec(
    slug: str,
    text: str,
    *,
    sources: list[str] | None = None,
    coverage: str = "missing",
    prior_spec: dict | None = None,  # noqa: ARG001 — reserved for cascade deps
) -> dict[str, Any]:
    """Return typed Competitive Landscape spec JSON. Heuristic only."""
    clipped = (text or "")[:50_000]
    sentences = _sentences(clipped)
    src = list(sources or [])

    if slug == "competitor_identification":
        model = _extract_competitor_identification(clipped, sentences)
    elif slug == "competitive_differentiation":
        model = _extract_differentiation(clipped, sentences)
    elif slug == "market_share_strategy":
        model = _extract_share_strategy(clipped, sentences)
    elif slug == "swot_analysis":
        model = _extract_swot(clipped, sentences)
    else:
        return {"slug": slug, "empty": True, "extractor": "none", "track": "B"}

    if coverage == "missing" and not clipped.strip():
        model.empty = True

    payload = model.model_dump(mode="json")
    payload["slug"] = slug
    payload["track"] = "B"
    payload["sources"] = src
    payload["coverage"] = coverage
    payload["extractor"] = "heuristic_v1"
    payload["metrics"] = _competitive_metrics(slug, payload)
    return payload


def _competitive_metrics(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "competitor_identification":
        return {
            "competitor_count": len(
                payload.get("competitive_set") or payload.get("competitors") or []
            ),
            "legacy_count": len(payload.get("competitors_legacy") or []),
            "note_count": len(payload.get("positioning_notes") or []),
            "barrier_count": len(payload.get("barriers") or []),
        }
    if slug == "competitive_differentiation":
        return {
            "claim_count": len(payload.get("claimed_advantages") or payload.get("differentiators") or []),
            "test_count": len(payload.get("advantage_tests") or []),
            "differentiator_count": len(payload.get("differentiators") or []),
            "feature_gap_count": len(payload.get("feature_gaps") or []),
            "replication_count": len(payload.get("replication") or []),
        }
    if slug == "market_share_strategy":
        matched = payload.get("matched_share") if isinstance(payload.get("matched_share"), dict) else {}
        attainable = (
            payload.get("attainable_vs_ambition")
            if isinstance(payload.get("attainable_vs_ambition"), dict)
            else {}
        )
        return {
            "trend_count": len(payload.get("share_trends") or []),
            "win_count": len(payload.get("wins") or []),
            "loss_count": len(payload.get("losses") or []),
            "movement_count": len(payload.get("share_movement") or []),
            "funnel_count": len(payload.get("funnel_economics") or []),
            "share_calculable": bool(matched.get("calculable")),
            "has_attainable_gap": bool(
                attainable.get("gap")
                and not str(attainable.get("gap") or "").startswith("Information")
                and str(attainable.get("gap") or "") != "N/A (data room did not provide it)"
            ),
        }
    if slug == "swot_analysis":
        return {
            "strength_count": len(payload.get("strengths") or []),
            "weakness_count": len(payload.get("weaknesses") or []),
            "opportunity_count": len(payload.get("opportunities") or []),
            "threat_count": len(payload.get("threats") or []),
            "unexamined_count": len(payload.get("information_gaps") or []),
            "unresolved_count": len(payload.get("unresolved_items") or []),
            "open_blocker_count": len(payload.get("open_blockers") or []),
            "upstream_count": len(payload.get("upstream_agents_used") or []),
            "porter_count": len(payload.get("porter_forces") or []),
        }
    return {}


def findings_from_competitive_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if slug == "competitor_identification":
        out: list[str] = []
        for row in (spec.get("competitive_set") or [])[:4]:
            if isinstance(row, dict) and row.get("name"):
                if str(row["name"]).startswith("Information"):
                    continue
                bits = [str(row["name"])]
                if row.get("classification"):
                    bits.append(str(row["classification"]).replace("_", " "))
                if row.get("scale"):
                    bits.append(str(row["scale"])[:40])
                out.append(" — ".join(bits))
        if not out:
            for row in spec.get("competitors") or []:
                if not isinstance(row, dict):
                    continue
                share = row.get("market_share_pct")
                bits = [row.get("name") or "Competitor"]
                if share is not None:
                    bits.append(f"share {share:g}%")
                if row.get("trend"):
                    bits.append(str(row["trend"]))
                out.append(" — ".join(bits))
        choice = spec.get("customer_choice") or []
        if isinstance(choice, list):
            for c in choice[:1]:
                if isinstance(c, dict) and c.get("evidence_type"):
                    out.append(f"Choice evidence: {c['evidence_type']}")
        out.extend(spec.get("positioning_notes") or [])
        return [x for x in out if isinstance(x, str) and x.strip()][:8]
    elif slug == "competitive_differentiation":
        for row in (spec.get("advantage_tests") or [])[:3]:
            if isinstance(row, dict) and row.get("claim"):
                out.append(
                    f"Test {row.get('test_result') or '?'}: {str(row['claim'])[:140]}"
                )
        if not out:
            out.extend(spec.get("differentiators") or [])
            out.extend(spec.get("moat_signals") or [])
            out.extend(spec.get("feature_gaps") or [])
        for row in (spec.get("economic_effects") or [])[:1]:
            if isinstance(row, dict) and row.get("magnitude"):
                out.append(f"Economic: {str(row.get('effect_label') or row.get('effect_type') or '')} {row['magnitude']}")
    elif slug == "market_share_strategy":
        matched = spec.get("matched_share") if isinstance(spec.get("matched_share"), dict) else {}
        if matched:
            if matched.get("calculable") and matched.get("share_pct") not in (None, ""):
                out.append(f"Matched share: {matched.get('share_pct')}")
            else:
                out.append("Share not calculable / unassessed on matched basis")
        for row in (spec.get("share_movement") or [])[:2]:
            if isinstance(row, dict) and row.get("peer_or_focal"):
                delta = row.get("delta_pp") or ""
                out.append(
                    f"Movement · {row['peer_or_focal']}"
                    + (f": {delta}" if delta else "")
                )
        att = (
            spec.get("attainable_vs_ambition")
            if isinstance(spec.get("attainable_vs_ambition"), dict)
            else {}
        )
        if att.get("gap") and not str(att["gap"]).startswith("Information"):
            out.append(f"Gap: {str(att['gap'])[:140]}")
        if not out:
            out.extend(spec.get("wins") or [])
            out.extend(spec.get("losses") or [])
            out.extend(spec.get("strategy_notes") or [])
    elif slug == "swot_analysis":
        for label, key in (
            ("S", "strengths"),
            ("W", "weaknesses"),
            ("O", "opportunities"),
            ("T", "threats"),
        ):
            for item in spec.get(key) or []:
                out.append(f"{label}: {item}")
        gaps = spec.get("information_gaps") or []
        if gaps:
            out.append(f"{len(gaps)} unexamined gap(s) (not weaknesses)")
        for blocker in (spec.get("open_blockers") or [])[:1]:
            out.append(f"OPEN BLOCKER: {blocker}")
        qv, rv = spec.get("quality_verdict"), spec.get("reliance_verdict")
        if qv or rv:
            out.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if not out:
            for force in spec.get("porter_forces") or []:
                if isinstance(force, dict):
                    out.append(
                        f"Porter · {force.get('force')}: {force.get('intensity')}"
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
