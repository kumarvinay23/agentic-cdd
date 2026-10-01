"""Slice 6 heuristic extractors for Risk & Opportunity Deep Dive agents (no LLM)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from agetic_cdd_api.deep_dive_extractors import (
    _hits,
    _is_noisy_sentence,
    _sentences,
)

RISK_SLUGS: frozenset[str] = frozenset(
    {
        "market_risk",
        "internal_risk",
        "growth_opportunities",
        "synergies",
    }
)

# Known VDR entities (Test1 / Indian EV). Regexes are built from these lists so
# new domains can extend coverage without rewriting parser logic.
_KNOWN_REGULATORY_AREAS: tuple[str, ...] = (
    "Companies Act Compliance",
    "SEBI LODR (Post-IPO)",
    "SEBI LODR",
    "GST Filing",
    "FAME-II Subsidy Claims",
    "CCPA Consumer Complaints",
    "AIS 156 Battery Safety Standard",
    "Environmental Clearance (Factory)",
    "Environmental Clearance",
    "Labor Law Compliance",
    "Data Protection (DPDPA 2023)",
    "Data Protection",
    "Customs / IGCR (Import duties)",
    "Customs / IGCR",
)
_KNOWN_LITIGATION_TYPES: tuple[str, ...] = (
    "CCPA Class Complaint",
    "IP Dispute",
    "FAME-II Subsidy Recovery Notice",
    "Tax Assessment",
    "Vendor Payment Dispute",
    "Ex-Employee NDAs",
)
_KNOWN_INVESTMENT_RISKS: tuple[str, ...] = (
    "Subsidy reduction / FAME-III delay",
    "OEM counter-attack (TVS, Bajaj)",
    "Battery cost plateau",
    "Execution failure at scale",
    "Capital market downturn",
    "China supply chain disruption",
    "Customer trust erosion",
)
_KNOWN_TECH_COMPONENTS: tuple[str, ...] = (
    "Vehicle OS (MoveOS)",
    "Mobile App (iOS/Android)",
    "OTA Update System",
    "BMS (Battery Mgmt System)",
    "ADAS / Safety Features",
    "Manufacturing MES",
    "Connected Cloud Backend",
    "AI/ML Analytics Engine",
    "Cybersecurity Framework",
)
_KNOWN_TECH_BULLETS: tuple[str, ...] = (
    "Battery thermal incidents",
    "Cybersecurity:",
    "MoveOS firmware fragmentation",
    "OTA rollback failure",
    "ADAS roadmap lags",
)
_KNOWN_GROWTH_PILLARS: tuple[str, ...] = (
    "Technology-First Positioning",
    "Vertical Integration Strategy",
    "Scale Advantage",
    "Brand Equity Among Youth",
    "Ecosystem Monetization",
)
_KNOWN_MILESTONE_LABELS: tuple[str, ...] = (
    "EBITDA Breakeven",
    "PAT Breakeven",
    "FCF Positive",
)

_REGULATORY_STATUS = (
    "Compliant|Under Review|Active Proceedings|Ongoing|Generally Compliant|"
    "Obtained|Under Assessment|Implementation Ongoing"
)
_RISK_LEVEL = r"(?:Low|Medium|High)"


def _alt_pattern(items: tuple[str, ...]) -> str:
    return "|".join(re.escape(item) for item in items)


def _compile_known_regulatory_re() -> re.Pattern[str]:
    areas = _alt_pattern(_KNOWN_REGULATORY_AREAS)
    status_tail = rf"(?:\s*\([^)]*\))?\s+({_RISK_LEVEL})\b"
    return re.compile(
        rf"(?i)({areas})"
        rf".{{0,48}}?"
        rf"({_REGULATORY_STATUS})"
        + status_tail
    )


_REGULATORY_ROW_RE = _compile_known_regulatory_re()
_GENERIC_REGULATORY_RE = re.compile(
    rf"(?i)([A-Z][A-Za-z0-9 /().,&'-]{{8,55}}?)\s+"
    rf"(?:.{{0,32}})?({_REGULATORY_STATUS})"
    rf"(?:\s*\([^)]*\))?\s+({_RISK_LEVEL})\b"
)

_LITIGATION_RE = re.compile(
    rf"(?i)({_alt_pattern(_KNOWN_LITIGATION_TYPES)})"
    r".{0,80}?(INR\s+[\d,]+\s+Crore|Active|Disputed|Pre-litigation|Negotiation|Arbitration)"
)

_REGULATORY_ROW_LIMIT = 10
_LITIGATION_ROW_LIMIT = 6

_NOISY_RISK_NOTE_RE = re.compile(
    r"(?i)(regulatory area governing body|status risk level|section [a-z0-9]+\s*[—–-]|"
    r"insight snapshot|matter nature estimated exposure|probability impact mitigation|"
    r"risk factor probability impact)"
)

_INV_RISK_RE = re.compile(
    rf"(?i)({_alt_pattern(_KNOWN_INVESTMENT_RISKS)})"
    rf"\s+({_RISK_LEVEL})\s+({_RISK_LEVEL})\b"
)
_GENERIC_INV_RISK_RE = re.compile(
    rf"(?i)([A-Za-z][A-Za-z0-9 /(),'-]{{10,70}}?)\s+({_RISK_LEVEL})\s+({_RISK_LEVEL})\b"
)

_TECH_HEADER_RE = re.compile(
    rf"(?i)({_alt_pattern(_KNOWN_TECH_COMPONENTS)})"
)
# Maturity is on a 1–5 scale; exclude hyphenated ordinals (e.g. Tier-1) and ISO/year numbers.
_TECH_MATURITY_SCORE_RE = re.compile(
    r"(?<![-\w])([1-5](?:\.\d+)?)(?!\d)\s+(.{8,120}?)(?=\Z|[.;])",
    re.DOTALL,
)
_TECH_COMPONENT_ROW_LIMIT = 10
_GENERIC_TECH_HEADER_RE = re.compile(
    r"(?i)([A-Z][A-Za-z0-9 /-]{2,28}\([^)]{2,32}\))"
)

_TECH_BULLET_RE = re.compile(
    rf"(?i)({_alt_pattern(_KNOWN_TECH_BULLETS)})"
    r"\s*(.{10,120}?)(?=Battery thermal|Cybersecurity:|MoveOS|OTA rollback|ADAS|\Z)"
)

_PILLAR_HEADER_RE = re.compile(
    rf"(?i)({_alt_pattern(_KNOWN_GROWTH_PILLARS)})"
)

_TAM_ROW_RE = re.compile(
    r"(?i)TAM\s*[—–-]\s*India 2W Market\s+USD\s+[\d.]+\s*B\s+USD\s+[\d.]+\s*B\s+~?([\d.]+)%"
)
_SAM_ROW_RE = re.compile(
    r"(?i)SAM\s*[—–-]\s*EV 2W Segment\s+USD\s+[\d.]+\s*B\s+USD\s+[\d.]+\s*B\s+~?([\d.]+)%"
)
_GENERIC_TAM_RE = re.compile(r"(?i)TAM\s*[—–-]\s*.{0,80}?~?([\d.]+)%")
_GENERIC_SAM_RE = re.compile(r"(?i)SAM\s*[—–-]\s*.{0,80}?~?([\d.]+)%")

_EV_PENETRATION_RE = re.compile(
    r"(?i)EV penetration in the two-wheeler segment stood at\s+~?(\d+(?:\.\d+)?)%"
)
_GENERIC_PENETRATION_RE = re.compile(
    r"(?i)(?:market )?penetration.{0,40}?~?(\d+(?:\.\d+)?)%"
)
_EV_PENETRATION_TARGET_RE = re.compile(
    r"(?i)projected to reach\s+(\d+(?:\.\d+)?)[–-](\d+(?:\.\d+)?)%\s+by\s+FY2030"
)
_GENERIC_PENETRATION_TARGET_RE = re.compile(
    r"(?i)reach\s+(\d+(?:\.\d+)?)[–-](\d+(?:\.\d+)?)%\s+by\s+FY20\d{2}"
)

_MILESTONE_START_RE = re.compile(
    r"(?i)(Gross Margin > \d+%|"
    + _alt_pattern(_KNOWN_MILESTONE_LABELS)
    + r"|Revenue > INR [\d,]+ Cr)\s+(FY\d{4})\s+"
)

_LEGAL_VERDICT_RE = re.compile(
    r"(?i)Overall legal risk:\s*(Low|Medium|High)"
)

# Max chars scanned per segment when slicing between known headers (ReDoS guard).
_SEGMENT_WINDOW = 160

_MARKET_RISK_NEEDLES = (
    "regulatory", "fame-ii", "subsidy", "compliance", "litigation", "legal risk",
    "ccpa", "market risk", "policy",
)
_INTERNAL_RISK_NEEDLES = (
    "tech debt", "cybersecurity", "firmware", "technical risk", "maturity",
    "scalability", "ota", "moveos", "attrition",
)
_GROWTH_NEEDLES = (
    "growth", "tam", "sam", "penetration", "cagr", "expansion", "milestone",
    "pillar", "opportunity",
)
_SYNERGY_NEEDLES = (
    "synergy", "value creation", "vertical integration", "ecosystem", "monetization",
    "scale advantage", "localization", "moat",
)
_BAD_RISK = (
    "nps score", "market share trend", "porter", "competitive rivalry",
    "bargaining power of",
)


class RegulatoryItem(BaseModel):
    area: str
    status: str = ""
    risk_level: str = ""


class MarketRiskItem(BaseModel):
    risk: str
    probability: str = ""
    impact: str = ""


class TechComponent(BaseModel):
    component: str
    maturity_score: float | None = None
    key_risk: str = ""


class GrowthLever(BaseModel):
    name: str
    note: str = ""


class MarketRiskSpec(BaseModel):
    """DD-20 — ESG Eligibility / Market Risk."""

    document: str = "ESG Eligibility / Market Risk"
    dd_code: str = "DD-20"
    regulatory_items: list[RegulatoryItem] = Field(default_factory=list)
    market_risk_items: list[MarketRiskItem] = Field(default_factory=list)
    litigation_exposures: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class InternalRiskSpec(BaseModel):
    """DD-21 — Tech Debt & Scalability Assessment."""

    document: str = "Tech Debt & Scalability Assessment"
    dd_code: str = "DD-21"
    tech_components: list[TechComponent] = Field(default_factory=list)
    technical_risks: list[str] = Field(default_factory=list)
    scalability_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class GrowthOpportunitiesSpec(BaseModel):
    """DD-01b — Growth Levers."""

    document: str = "Growth Levers"
    dd_code: str = "DD-01b"
    growth_levers: list[GrowthLever] = Field(default_factory=list)
    market_growth: dict[str, float] = Field(default_factory=dict)
    milestone_targets: list[str] = Field(default_factory=list)
    opportunity_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class SynergiesSpec(BaseModel):
    """DD-06b — Synergy Thesis."""

    document: str = "Synergy Thesis"
    dd_code: str = "DD-06b"
    synergy_themes: list[str] = Field(default_factory=list)
    value_milestones: list[str] = Field(default_factory=list)
    synergy_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


def _clean(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "").strip()


def _safe_float(val: Any) -> float | None:
    """Convert numeric strings and numbers without raising ValueError."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d.-]", "", val.strip())
        if not cleaned or cleaned in {"-", ".", "-."}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _segment_slices(
    text: str,
    header_re: re.Pattern[str],
    *,
    window: int = _SEGMENT_WINDOW,
) -> list[tuple[str, str]]:
    """Return (header label, bounded segment text) pairs without dot-star lookaheads."""
    bounded = (text or "")[:50_000]
    hits = list(header_re.finditer(bounded))
    if not hits:
        return []
    slices: list[tuple[str, str]] = []
    for idx, hit in enumerate(hits):
        label = re.sub(r"\s+", " ", hit.group(1)).strip()
        seg_start = hit.end()
        if idx + 1 < len(hits):
            seg_end = min(hits[idx + 1].start(), seg_start + window)
        else:
            seg_end = min(len(bounded), seg_start + window)
        segment = bounded[seg_start:seg_end]
        slices.append((label, segment))
    return slices


def _is_noisy_risk_note(line: str) -> bool:
    cleaned = re.sub(r"\s+", " ", line).strip()
    if not cleaned:
        return True
    if _NOISY_RISK_NOTE_RE.search(cleaned):
        return True
    # Concatenated compliance-table dumps (multiple status/risk pairs in one line).
    status_hits = len(re.findall(rf"(?i)({_REGULATORY_STATUS})\s+(?:\([^)]*\)\s+)?({_RISK_LEVEL})\b", cleaned))
    return status_hits >= 3


def _dedupe(lines: list[str], *, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        cleaned = re.sub(r"\s+", " ", _clean(line)).strip()
        cleaned = re.sub(r"^[\W_]{1,4}", "", cleaned).strip()
        key = cleaned.lower()
        if len(cleaned) < 20 or key in seen:
            continue
        if any(bad in key for bad in _BAD_RISK):
            continue
        if _is_noisy_risk_note(cleaned):
            continue
        seen.add(key)
        out.append(cleaned[:280])
        if len(out) >= limit:
            break
    return out


def _format_number(val: Any) -> str:
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int | float):
        return f"{val:g}"
    return str(val)


def _append_regulatory_row(
    rows: list[RegulatoryItem],
    seen: set[str],
    area: str,
    status: str,
    risk_level: str,
    *,
    limit: int = _REGULATORY_ROW_LIMIT,
) -> None:
    cleaned_area = re.sub(r"\s+", " ", area).strip()
    key = cleaned_area.lower()
    if not cleaned_area or key in seen:
        return
    seen.add(key)
    rows.append(
        RegulatoryItem(
            area=cleaned_area,
            status=status.strip(),
            risk_level=risk_level.title(),
        )
    )
    if len(rows) >= limit:
        return


def _parse_regulatory_items(text: str) -> list[RegulatoryItem]:
    rows: list[RegulatoryItem] = []
    seen: set[str] = set()
    for match in _REGULATORY_ROW_RE.finditer(text or ""):
        _append_regulatory_row(
            rows, seen, match.group(1), match.group(2), match.group(3)
        )
        if len(rows) >= _REGULATORY_ROW_LIMIT:
            break
    if len(rows) < 3:
        for match in _GENERIC_REGULATORY_RE.finditer(text or ""):
            area = match.group(1).strip()
            if any(area.lower() == known.lower() for known in _KNOWN_REGULATORY_AREAS):
                continue
            _append_regulatory_row(
                rows, seen, area, match.group(2), match.group(3)
            )
            if len(rows) >= _REGULATORY_ROW_LIMIT:
                break
    return rows


def _parse_market_risk_items(text: str) -> list[MarketRiskItem]:
    items: list[MarketRiskItem] = []
    seen: set[str] = set()
    for match in _INV_RISK_RE.finditer(text or ""):
        risk = re.sub(r"\s+", " ", match.group(1)).strip()
        seen.add(risk.lower())
        items.append(
            MarketRiskItem(
                risk=risk,
                probability=match.group(2).title(),
                impact=match.group(3).title(),
            )
        )
        if len(items) >= 6:
            break
    if len(items) < 2:
        for match in _GENERIC_INV_RISK_RE.finditer(text or ""):
            risk = re.sub(r"\s+", " ", match.group(1)).strip()
            key = risk.lower()
            if key in seen or len(risk) < 12:
                continue
            if any(k in key for k in ("gross margin", "ebitda", "fy20")):
                continue
            seen.add(key)
            items.append(
                MarketRiskItem(
                    risk=risk,
                    probability=match.group(2).title(),
                    impact=match.group(3).title(),
                )
            )
            if len(items) >= 6:
                break
    return items


def _parse_litigation(text: str) -> list[str]:
    out: list[str] = []
    for match in _LITIGATION_RE.finditer(text or ""):
        bit = re.sub(r"\s+", " ", match.group(0)).strip()[:200]
        out.append(bit)
        if len(out) >= _LITIGATION_ROW_LIMIT:
            break
    return out


def _clip_tech_component_segment(segment: str) -> str:
    """Stop before a later VDR section bleeds into the component maturity window."""
    bounded = segment or ""
    for marker in (
        "Battery Technology Roadmap",
        "Technical Risks",
        "R&D Investment",
        "R&D; Investment",
    ):
        idx = bounded.find(marker)
        if idx > 0:
            bounded = bounded[:idx]
    return bounded


def _parse_tech_maturity_from_segment(segment: str) -> re.Match[str] | None:
    """Return the first maturity score + key-risk tail, skipping Tier-1-style false positives."""
    clipped = _clip_tech_component_segment(segment)
    for candidate in _TECH_MATURITY_SCORE_RE.finditer(clipped):
        score = _safe_float(candidate.group(1))
        if score is None or score < 1.0 or score > 5.0:
            continue
        return candidate
    return None


def _parse_tech_components(text: str) -> list[TechComponent]:
    rows: list[TechComponent] = []
    seen: set[str] = set()
    for name, segment in _segment_slices(text, _TECH_HEADER_RE):
        key = name.lower()
        if key in seen:
            continue
        score_match = _parse_tech_maturity_from_segment(segment)
        if not score_match:
            continue
        score = _safe_float(score_match.group(1))
        if score is None:
            continue
        seen.add(key)
        risk = re.sub(r"\s+", " ", score_match.group(2)).strip()[:120]
        rows.append(
            TechComponent(
                component=name,
                maturity_score=score,
                key_risk=risk,
            )
        )
        if len(rows) >= _TECH_COMPONENT_ROW_LIMIT:
            break
    if len(rows) < 2:
        for name, segment in _segment_slices(text, _GENERIC_TECH_HEADER_RE):
            key = name.lower()
            if key in seen:
                continue
            score_match = _parse_tech_maturity_from_segment(segment)
            if not score_match:
                continue
            score = _safe_float(score_match.group(1))
            if score is None:
                continue
            seen.add(key)
            risk = re.sub(r"\s+", " ", score_match.group(2)).strip()[:120]
            rows.append(
                TechComponent(component=name, maturity_score=score, key_risk=risk)
            )
            if len(rows) >= _TECH_COMPONENT_ROW_LIMIT:
                break
    return rows


def _parse_technical_bullets(text: str) -> list[str]:
    out: list[str] = []
    for match in _TECH_BULLET_RE.finditer(text or ""):
        head = re.sub(r"\s+", " ", _clean(match.group(1))).strip()
        tail = re.sub(r"\s+", " ", _clean(match.group(2))).strip()[:160]
        bit = f"{head}: {tail}".strip(": ")
        out.append(_clean(bit)[:240])
        if len(out) >= 5:
            break
    return out


def _parse_growth_levers(text: str) -> list[GrowthLever]:
    levers: list[GrowthLever] = []
    seen: set[str] = set()
    for name, segment in _segment_slices(text, _PILLAR_HEADER_RE, window=220):
        key = name.lower()
        if key in seen:
            continue
        note = re.sub(r"\s+", " ", segment).strip()[:200]
        if len(note) < 20:
            continue
        seen.add(key)
        levers.append(GrowthLever(name=name, note=note))
        if len(levers) >= 5:
            break
    return levers


def _parse_milestones(text: str) -> list[str]:
    out: list[str] = []
    bounded = (text or "")[:50_000]
    hits = list(_MILESTONE_START_RE.finditer(bounded))
    for idx, hit in enumerate(hits):
        detail_start = hit.end()
        if idx + 1 < len(hits):
            detail_end = hits[idx + 1].start()
        else:
            detail_end = min(len(bounded), detail_start + _SEGMENT_WINDOW)
        detail = re.sub(r"\s+", " ", bounded[detail_start:detail_end]).strip()
        if len(detail) < 5:
            continue
        out.append(f"{hit.group(1).strip()} — {detail}"[:220])
        if len(out) >= 5:
            break
    return out


def _extract_market_risk(text: str, sentences: list[str]) -> MarketRiskSpec:
    regulatory = _parse_regulatory_items(text)
    market_items = _parse_market_risk_items(text)
    litigation = _parse_litigation(text)
    flags: list[str] = []
    high_reg = [r for r in regulatory if (r.risk_level or "").lower() == "high"]
    if high_reg:
        flags.append(
            "High regulatory risk: "
            + ", ".join(r.area for r in high_reg[:3])
            + "."
        )
    fame = next((r for r in regulatory if "fame" in r.area.lower()), None)
    if fame:
        flags.append(f"FAME-II status: {fame.status} ({fame.risk_level} risk).")
    if any("fame-ii subsidy recovery" in lit.lower() for lit in litigation):
        flags.append("FAME-II subsidy recovery exposure flagged in litigation register.")
    verdict = _LEGAL_VERDICT_RE.search(text or "")
    if verdict:
        flags.append(f"Overall legal risk rated {verdict.group(1).title()}.")

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe([*flags, *_hits(clean, _MARKET_RISK_NEEDLES, limit=6)], limit=5)
    preferred = [
        s
        for s in clean
        if re.search(r"(?i)legal risk|regulatory|subsidy|fame-ii|ccpa|market risk", s)
    ]
    notes = _dedupe([*notes, *preferred], limit=5)

    model = MarketRiskSpec(
        regulatory_items=regulatory,
        market_risk_items=market_items,
        litigation_exposures=litigation,
        risk_flags=_dedupe(flags, limit=4),
        risk_notes=notes,
    )
    model.empty = not any(
        [model.regulatory_items, model.market_risk_items, model.litigation_exposures, model.risk_notes]
    )
    return model


def _extract_internal_risk(text: str, sentences: list[str]) -> InternalRiskSpec:
    components = _parse_tech_components(text)
    bullets = _parse_technical_bullets(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _INTERNAL_RISK_NEEDLES, limit=6), limit=4)
    low_maturity = [c for c in components if (c.maturity_score or 5) < 3.0]
    if low_maturity:
        notes = _dedupe(
            [
                f"Low maturity: {c.component} ({c.maturity_score:g}/5)."
                for c in low_maturity[:3]
            ]
            + notes,
            limit=4,
        )
    attrition = re.search(r"(?i)Technology attrition at\s+(\d+(?:\.\d+)?)%", text or "")
    if attrition:
        notes = _dedupe(
            [f"Technology attrition {attrition.group(1)}% — IP continuity risk.", *notes],
            limit=4,
        )
    notes = _dedupe([*bullets, *notes], limit=5)

    model = InternalRiskSpec(
        tech_components=components,
        technical_risks=bullets,
        scalability_notes=notes,
    )
    model.empty = not any([model.tech_components, model.technical_risks, model.scalability_notes])
    return model


def _extract_growth_opportunities(
    text: str,
    sentences: list[str],
    prior_spec: dict | None,
) -> GrowthOpportunitiesSpec:
    levers = _parse_growth_levers(text)
    metrics: dict[str, float] = {}
    tam = _TAM_ROW_RE.search(text or "") or _GENERIC_TAM_RE.search(text or "")
    if tam:
        val = _safe_float(tam.group(1))
        if val is not None:
            metrics["tam_cagr_pct"] = val
    sam = _SAM_ROW_RE.search(text or "") or _GENERIC_SAM_RE.search(text or "")
    if sam:
        val = _safe_float(sam.group(1))
        if val is not None:
            metrics["sam_cagr_pct"] = val
    ev = _EV_PENETRATION_RE.search(text or "") or _GENERIC_PENETRATION_RE.search(text or "")
    if ev:
        val = _safe_float(ev.group(1))
        if val is not None:
            metrics["ev_penetration_fy2024_pct"] = val
    ev_tgt = _EV_PENETRATION_TARGET_RE.search(text or "") or _GENERIC_PENETRATION_TARGET_RE.search(
        text or ""
    )
    if ev_tgt:
        lo = _safe_float(ev_tgt.group(1))
        hi = _safe_float(ev_tgt.group(2))
        if lo is not None:
            metrics["ev_penetration_fy2030_low_pct"] = lo
        if hi is not None:
            metrics["ev_penetration_fy2030_high_pct"] = hi

    if prior_spec:
        for src, dst in (
            ("tam_cagr_pct", "tam_cagr_pct"),
            ("sam_cagr_pct", "sam_cagr_pct"),
            ("som_cagr_pct", "som_cagr_pct"),
        ):
            if dst not in metrics:
                val = _safe_float(prior_spec.get(src))
                if val is not None:
                    metrics[dst] = val
        vol = prior_spec.get("volume_metrics") if isinstance(prior_spec.get("volume_metrics"), dict) else {}
        if isinstance(vol, dict):
            for key in ("tam_units", "market_cagr_pct"):
                if key not in metrics:
                    val = _safe_float(vol.get(key))
                    if val is not None:
                        metrics[key] = val

    milestones = _parse_milestones(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _GROWTH_NEEDLES, limit=6), limit=4)
    if metrics.get("sam_cagr_pct") is not None:
        notes = _dedupe(
            [f"SAM CAGR ~{metrics['sam_cagr_pct']:g}% — structural EV tailwind.", *notes],
            limit=4,
        )
    if levers:
        notes = _dedupe(
            [f"Growth lever: {levers[0].name}.", *notes],
            limit=4,
        )

    model = GrowthOpportunitiesSpec(
        growth_levers=levers,
        market_growth=metrics,
        milestone_targets=milestones,
        opportunity_notes=notes,
    )
    model.empty = not any(
        [model.growth_levers, model.market_growth, model.milestone_targets, model.opportunity_notes]
    )
    return model


def _extract_synergies(
    text: str,
    sentences: list[str],
    prior_spec: dict | None,
) -> SynergiesSpec:
    levers = _parse_growth_levers(text)
    themes = [f"{lv.name} — {lv.note[:120]}".strip(" —") for lv in levers if lv.name]
    milestones = _parse_milestones(text)

    if prior_spec:
        moats = prior_spec.get("moat_strengths") or prior_spec.get("differentiators") or []
        if isinstance(moats, list):
            for item in moats[:3]:
                if isinstance(item, str) and item.strip():
                    themes.append(f"Competitive moat: {item.strip()[:160]}")
                elif isinstance(item, dict) and item.get("theme"):
                    themes.append(f"Competitive moat: {item['theme']}")

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _SYNERGY_NEEDLES, limit=6), limit=4)
    preferred = [
        s
        for s in clean
        if re.search(
            r"(?i)value creation|vertical integration|ecosystem monetization|"
            r"localization roadmap|scale advantage|gross margin",
            s,
        )
    ]
    localization = re.search(
        r"(?i)localization roadmap targets\s+(\d+(?:\.\d+)?)%\+?\s+domestic content by FY(\d{4})",
        text or "",
    )
    if localization:
        notes = _dedupe(
            [
                f"Localization synergy: {localization.group(1)}% domestic content by FY{localization.group(2)}.",
                *notes,
            ],
            limit=4,
        )
    margin = re.search(
        r"(?i)gross margins from\s+~?(\d+(?:\.\d+)?)%\s+today to an estimated\s+(\d+(?:\.\d+)?)[–-](\d+(?:\.\d+)?)%",
        text or "",
    )
    if margin:
        notes = _dedupe(
            [
                f"Scale synergy: gross margin path {margin.group(1)}% → {margin.group(2)}–{margin.group(3)}%.",
                *notes,
            ],
            limit=4,
        )
    notes = _dedupe([*themes[:3], *preferred, *notes], limit=5)

    model = SynergiesSpec(
        synergy_themes=_dedupe(themes, limit=6),
        value_milestones=milestones,
        synergy_notes=notes,
    )
    model.empty = not any([model.synergy_themes, model.value_milestones, model.synergy_notes])
    return model


def extract_risk_spec(
    slug: str,
    text: str,
    *,
    sources: list[str] | None = None,
    coverage: str = "missing",
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    """Return typed Risk & Opportunity spec JSON. Heuristic only."""
    clipped = (text or "")[:50_000]
    sentences = _sentences(clipped)
    src = list(sources or [])

    if slug == "market_risk":
        model = _extract_market_risk(clipped, sentences)
    elif slug == "internal_risk":
        model = _extract_internal_risk(clipped, sentences)
    elif slug == "growth_opportunities":
        model = _extract_growth_opportunities(clipped, sentences, prior_spec)
    elif slug == "synergies":
        model = _extract_synergies(clipped, sentences, prior_spec)
    else:
        return {"slug": slug, "empty": True, "extractor": "none", "track": "E"}

    if coverage == "missing" and not clipped.strip():
        model.empty = True

    payload = model.model_dump(mode="json")
    payload["slug"] = slug
    payload["track"] = "E"
    payload["sources"] = src
    payload["coverage"] = coverage
    payload["extractor"] = "heuristic_v1"
    payload["metrics"] = _risk_metrics(slug, payload)
    return payload


def _risk_metrics(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "market_risk":
        return {
            "regulatory_count": len(payload.get("regulatory_items") or []),
            "market_risk_count": len(payload.get("market_risk_items") or []),
            "flag_count": len(payload.get("risk_flags") or []),
        }
    if slug == "internal_risk":
        return {
            "component_count": len(payload.get("tech_components") or []),
            "technical_risk_count": len(payload.get("technical_risks") or []),
        }
    if slug == "growth_opportunities":
        return {
            "lever_count": len(payload.get("growth_levers") or []),
            "metric_count": len(payload.get("market_growth") or {}),
            "milestone_count": len(payload.get("milestone_targets") or []),
        }
    if slug == "synergies":
        return {
            "theme_count": len(payload.get("synergy_themes") or []),
            "milestone_count": len(payload.get("value_milestones") or []),
        }
    return {}


def findings_from_risk_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if slug == "market_risk":
        for row in spec.get("regulatory_items") or []:
            if isinstance(row, dict) and row.get("area"):
                out.append(
                    f"{row['area']} — {row.get('status') or '?'} ({row.get('risk_level') or '?'})"
                )
        for row in spec.get("market_risk_items") or []:
            if isinstance(row, dict) and row.get("risk"):
                out.append(
                    f"{row['risk']} — {row.get('probability') or '?'} / {row.get('impact') or '?'}"
                )
        out.extend(spec.get("litigation_exposures") or [])
        out.extend(spec.get("risk_flags") or [])
        out.extend(spec.get("risk_notes") or [])
    elif slug == "internal_risk":
        for row in spec.get("tech_components") or []:
            if isinstance(row, dict) and row.get("component"):
                bit = row["component"]
                if row.get("maturity_score") is not None:
                    bit += f" — maturity {_format_number(row['maturity_score'])}/5"
                out.append(bit)
        out.extend(spec.get("technical_risks") or [])
        out.extend(spec.get("scalability_notes") or [])
    elif slug == "growth_opportunities":
        for row in spec.get("growth_levers") or []:
            if isinstance(row, dict) and row.get("name"):
                out.append(row["name"])
        metrics = spec.get("market_growth") or {}
        if isinstance(metrics, dict):
            for key, val in list(metrics.items())[:5]:
                out.append(f"{key}: {_format_number(val)}")
        out.extend(spec.get("milestone_targets") or [])
        out.extend(spec.get("opportunity_notes") or [])
    elif slug == "synergies":
        out.extend(spec.get("synergy_themes") or [])
        out.extend(spec.get("value_milestones") or [])
        out.extend(spec.get("synergy_notes") or [])

    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())
    return deduped
