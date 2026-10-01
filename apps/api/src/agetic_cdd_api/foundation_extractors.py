"""S3 heuristic extractors for Foundation roles (no LLM required)."""

from __future__ import annotations

import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


ThesisFramework = Literal["pe", "strategic", "growth_equity"]
TimelineGranularity = Literal["weekly", "daily"]
ProcessCoverage = Literal["full", "partial", "missing_process_letter"]
Severity = Literal["R", "A", "G"]


class WorkstreamItem(BaseModel):
    name: str
    priority: int = Field(ge=1, le=5)


class MilestoneItem(BaseModel):
    week: int = Field(ge=1)
    label: str


class DatedItem(BaseModel):
    label: str
    value: str


class RiskItem(BaseModel):
    clause: str
    severity: int | Severity = Field(ge=1, le=5)
    mitigant: str = ""


class CSuiteItem(BaseModel):
    role: str
    name: str
    criticality: int = Field(ge=1, le=5)
    replaceability: int = Field(ge=1, le=5)


class F01Thesis(BaseModel):
    investment_drivers: list[str]
    must_be_true: list[str]
    deal_breaker_risks: list[str]
    attractiveness_score: int = Field(ge=1, le=10)
    thesis_framework: ThesisFramework
    scoring_notes: list[str]
    sources: list[str]


class F02Roadmap(BaseModel):
    ic_hooks: list[str]
    workstreams: list[WorkstreamItem]
    milestones: list[MilestoneItem]
    consumes_f01_score: int | None = None
    timeline_granularity: TimelineGranularity = "weekly"


class F03Process(BaseModel):
    dates: list[DatedItem]
    submission_rules: list[str]
    unusual_terms: list[str]
    coverage: ProcessCoverage


class F04Compliance(BaseModel):
    risks: list[RiskItem]
    restricted_activities: list[str]
    data_handling: list[str]
    penalty_notes: list[str]


class F05Entity(BaseModel):
    legal_name: str | None = None
    jurisdiction: str | None = None
    entity_type: str | None = None
    incorporation_date: str | None = None
    share_classes: list[str] = Field(default_factory=list)
    registered_agent: str | None = None
    governance_notes: list[str] = Field(default_factory=list)


class F06OrgRisk(BaseModel):
    org_depth: int | None = None
    span_of_control: str | None = None
    c_suite: list[CSuiteItem] = Field(default_factory=list)
    succession_gaps: list[str] = Field(default_factory=list)
    org_risk_score: int = Field(ge=1, le=10)
    consumes_f05: bool = False


class FIpBaseline(BaseModel):
    patents: list[str] = Field(default_factory=list)
    core_tech: list[str] = Field(default_factory=list)
    architecture_notes: list[str] = Field(default_factory=list)


class FEsgBaseline(BaseModel):
    themes: list[str] = Field(default_factory=list)
    labour_flags: list[str] = Field(default_factory=list)
    environment_flags: list[str] = Field(default_factory=list)


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_DATE_RE = re.compile(
    r"\b("
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r")\b"
)
_LEGAL_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\'\- ]{1,80}(?:Limited|Ltd\.?|Inc\.?|LLC|PLC|GmbH|S\.A\.|Pvt\.?\s*Ltd\.?))\b"
)
_LEGAL_NAME_LABEL_RE = re.compile(
    r"(?i)Legal Name\s+(.+?)\s+(?:CIN|Founded|Headquarters|Registered)\b"
)
_FOUNDED_RE = re.compile(r"(?i)Founded\s+(\d{4})")
_HQ_RE = re.compile(
    r"(?i)Headquarters\s+(.+?)\s+(?:Registered Office|Registered|Sector)\b"
)
_CIN_RE = re.compile(r"\bCIN\s+([A-Z0-9]+(?:\s*\([^)]+\))?)\b")
_YEAR_RE = re.compile(r"\b(?:founded|incorporated|incorporation)\b[^\d]{0,24}(\d{4})", re.I)
_CSUITE_RE = re.compile(
    r"\b(CEO|CFO|CTO|COO|CHRO|CMO|CRO|CISO|Founder|Chair(?:man|person)?)\b"
    r"(?:\s+is|\s+as)?[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})"
)
_HR_LEADER_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+"
    r"(CEO(?:\s*&\s*Founder)?|CFO|CTO|COO(?:\s*[—–-]\s*Manufacturing)?|CHRO|"
    r"VP(?:\s*[—–-]\s*(?:Software|Sales & Marketing))?)\s+"
    r"Since\s+\d{4}\s+"
    r".{0,100}?"
    r"(High(?:\s*\([^)]+\))?|Medium|Low)"
)
_CORP_EXEC_RE = re.compile(
    r"(?i)(CEO(?:\s*&\s*Founder)?|CFO|CTO|CHRO)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
)
_HR_RISK_SECTION_RE = re.compile(
    r"(?i)HR Risk Assessment\s+(.+?)(?:\Z)",
    re.DOTALL,
)
_BAD_F06 = (
    "insight snapshot", "parameter details", "company fact sheet", "metric fy20",
    "workforce overview", "name title tenure", "product portfolio",
)
_JURISDICTION_RE = re.compile(
    r"(?i:incorporated in|jurisdiction(?: of)?|under the laws of|headquartered in)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)",
)
_SHARE_RE = re.compile(r"\b((?:ordinary|preferred|preference|class\s+[A-Z]|equity)\s+shares?)\b", re.I)
_WEEK_RE = re.compile(r"\bweek\s*(\d{1,2})\b[:\s-]+(.{8,80}?)(?:\.|$)", re.I)

_F04_KNOWN_REGULATORY_AREAS: tuple[str, ...] = (
    "Companies Act Compliance",
    "SEBI LODR (Post-IPO)",
    "SEBI LODR",
    "GST Filing",
    "FAME-II Subsidy Claims",
    "CCPA Consumer Complaints",
    "AIS 156 Battery Safety Standard",
    "Environmental Clearance (Factory)",
    "Environmental Clearance",
    "Labor Law Compliance (Factories Act)",
    "Labor Law Compliance",
    "Data Protection (DPDPA 2023)",
    "Data Protection",
    "Customs / IGCR (Import duties)",
    "Customs / IGCR",
)
_F04_KNOWN_LITIGATION: tuple[str, ...] = (
    "CCPA Class Complaint",
    "IP Dispute",
    "FAME-II Subsidy Recovery Notice",
    "Tax Assessment",
    "Vendor Payment Dispute",
    "Ex-Employee NDAs",
)
_F04_REGULATORY_STATUS = (
    "Compliant|Under Review|Active Proceedings|Ongoing|Generally Compliant|"
    "Obtained|Under Assessment|Implementation Ongoing|Compliant \\(Gen 2\\+\\)"
)
_F04_RISK_LEVEL = r"(?:Low|Medium|High)"
_F04_REGULATORY_RE = re.compile(
    rf"(?i)({'|'.join(re.escape(a) for a in _F04_KNOWN_REGULATORY_AREAS)})"
    rf".{{0,48}}?"
    rf"({_F04_REGULATORY_STATUS})\s+"
    rf"({_F04_RISK_LEVEL})\b"
)
_F04_LITIGATION_RE = re.compile(
    rf"(?i)({'|'.join(re.escape(a) for a in _F04_KNOWN_LITIGATION)})"
    r".{0,48}?(INR\s+[\d,]+\s+Crore|Active|Disputed|Pre-litigation|Negotiation|Arbitration|Appeal)"
)
_F04_LEGAL_VERDICT_RE = re.compile(r"(?i)Overall legal risk:\s*(Low|Medium|High)")
_F04_CONTRACTS_SECTION_RE = re.compile(
    r"(?i)Material Contracts & Agreements\s+(.+?)(?=Legal Due Diligence Verdict|\Z)",
    re.DOTALL,
)
_BAD_F04 = (
    "insight snapshot", "regulatory area governing", "ip category", "matter nature",
    "intellectual property portfolio", "key areas patents",
)


def _severity_from_level(level: str) -> int:
    return {"low": 2, "medium": 4, "high": 5}.get(level.lower(), 3)


def _is_f04_noise(text: str) -> bool:
    low = text.lower()
    return any(n in low for n in _BAD_F04) or len(text) > 220


def _parse_f04_regulatory_rows(text: str) -> list[RiskItem]:
    rows: list[RiskItem] = []
    seen: set[str] = set()
    for match in _F04_REGULATORY_RE.finditer(text or ""):
        area = re.sub(r"\s+", " ", match.group(1)).strip()
        key = area.lower()
        if key in seen:
            continue
        seen.add(key)
        status = match.group(2).strip()
        level = match.group(3).title()
        sev = _severity_from_level(level)
        mitigant = "Counsel review and carve-outs" if sev >= 4 else "Monitor in legal DD"
        rows.append(
            RiskItem(
                clause=f"{area} — {status} ({level} risk)"[:220],
                severity=sev,
                mitigant=mitigant,
            )
        )
        if len(rows) >= 12:
            break
    rows.sort(key=lambda item: item.severity, reverse=True)
    return rows


def _parse_f04_litigation(text: str) -> list[RiskItem]:
    items: list[RiskItem] = []
    for match in _F04_LITIGATION_RE.finditer(text or ""):
        bit = re.sub(r"\s+", " ", match.group(0)).strip()[:200]
        low = bit.lower()
        sev = 5 if "300" in bit or "fame-ii subsidy recovery" in low else 4 if "120" in bit else 3
        items.append(
            RiskItem(
                clause=bit,
                severity=sev,
                mitigant="Counsel review and carve-outs" if sev >= 4 else "Monitor in legal DD",
            )
        )
        if len(items) >= 6:
            break
    return items


def _parse_f04_contract_flags(text: str) -> list[str]:
    section = _F04_CONTRACTS_SECTION_RE.search(text or "")
    if not section:
        return []
    return _extract_bullets(section.group(1), limit=5)


def _parse_f04_data_handling(text: str) -> list[str]:
    out: list[str] = []
    for match in _F04_REGULATORY_RE.finditer(text or ""):
        area = match.group(1).lower()
        if "data protection" in area or "dpdpa" in area:
            out.append(
                f"{match.group(1).strip()} — {match.group(2).strip()} ({match.group(3).title()} risk)"
            )
    verdict = re.search(
        r"(?i)data protection implementation needs to be completed[^.]*\.",
        text or "",
    )
    if verdict:
        out.append(_clip_f01(verdict.group(0), 180))
    return out[:4]


def _parse_f04_penalty_notes(text: str) -> list[str]:
    notes: list[str] = []
    for match in _F04_LITIGATION_RE.finditer(text or ""):
        bit = re.sub(r"\s+", " ", match.group(0)).strip()[:180]
        if "INR" in bit:
            notes.append(bit)
    fame = re.search(
        r"(?i)FAME-II subsidy recovery notice \(INR [^)]+\)",
        text or "",
    )
    if fame:
        notes.append(_clip_f01(fame.group(0), 160))
    return notes[:6]


def _extract_f04_legal_dd(text: str) -> dict[str, Any]:
    regulatory = _parse_f04_regulatory_rows(text)
    litigation = _parse_f04_litigation(text)
    risks = regulatory[:6] + litigation[:5]
    verdict = _F04_LEGAL_VERDICT_RE.search(text or "")
    if verdict:
        level = verdict.group(1).title()
        risks.append(
            RiskItem(
                clause=f"Overall legal risk rated {level}.",
                severity=_severity_from_level(level),
                mitigant="Monitor in legal DD",
            )
        )
    restricted = _parse_f04_contract_flags(text)
    handling = _parse_f04_data_handling(text)
    penalties = _parse_f04_penalty_notes(text)
    if not risks:
        sentences = [s for s in _sentences(text) if not _is_f04_noise(s)]
        risks = [
            RiskItem(clause=_clip_f01(s), severity=2, mitigant="Monitor in legal DD")
            for s in _hits(sentences, ("risk", "litigation", "regulatory"))[:4]
        ]
    model = F04Compliance(
        risks=risks[:12] or [RiskItem(clause="No legal risks extracted.", severity=2, mitigant="Obtain legal DD")],
        restricted_activities=restricted,
        data_handling=handling,
        penalty_notes=penalties,
    )
    return model.model_dump(mode="json")


def _extract_f04_nda(text: str) -> dict[str, Any]:
    sentences = _sentences(text)
    risk_sents = _hits(sentences, ("risk", "restrict", "prohibit", "confidential", "standstill", "non-solicit"))
    risks: list[RiskItem] = []
    for sentence in risk_sents[:6]:
        low = sentence.lower()
        if any(k in low for k in ("penalty", "injunction", "damages", "liquidated")):
            sev: int = 5
        elif any(k in low for k in ("prohibit", "shall not", "restrict", "standstill")):
            sev = 4
        elif "confidential" in low:
            sev = 3
        else:
            sev = 2
        mitigant = "Counsel review and carve-outs" if sev >= 4 else "Monitor in legal DD"
        risks.append(RiskItem(clause=sentence[:240], severity=sev, mitigant=mitigant))
    restricted = _hits(sentences, ("shall not", "restricted", "prohibit", "not disclose", "non-solicit", "standstill"))
    handling = _hits(sentences, ("confidential", "data room", "personal data", "gdpr", "return or destroy"))
    penalties = _hits(sentences, ("penalty", "damages", "injunction", "liquidated", "indemnif"))
    model = F04Compliance(
        risks=risks or [RiskItem(clause="No NDA risk clauses extracted.", severity=2, mitigant="Obtain NDA / legal DD")],
        restricted_activities=restricted[:6],
        data_handling=handling[:6],
        penalty_notes=penalties[:6],
    )
    return model.model_dump(mode="json")


def _extract_f04(text: str) -> dict[str, Any]:
    if re.search(r"(?i)Regulatory Area|Regulatory Compliance Status|Key Legal Risks", text or ""):
        return _extract_f04_legal_dd(text)
    return _extract_f04_nda(text)


_GROWTH = (
    "tam", "sam", "growth", "cagr", "vertical integration", "market leader",
    "tailwind", "expand", "scale",
)
_BREAKERS = (
    "deal breaker", "deal-breaker", "litigation", "regulatory risk",
    "execution risk", "customer concentration", "key person", "going concern",
)
_MUST = ("must be true", "must-have", "requires", "need to", "conditional on", "depends on")
_DRIVER = ("thesis", "driver", "investment case", "why invest", "value creation", "moat")

_BAD_F01 = (
    "due diligence scope", "insight snapshot", "executive summary", "company overview",
    "hypothetical", "disclaimer", "metric fy20", "validating claims",
    "this due diligence package", "dimension rating", "overall investment rating",
    "yoy growth revenue (inr",
)
_KNOWN_PILLARS: tuple[str, ...] = (
    "Technology-First Positioning",
    "Vertical Integration Strategy",
    "Scale Advantage",
    "Brand Equity Among Youth",
    "Ecosystem Monetization",
)
_PILLAR_HEADER_RE = re.compile(
    rf"(?i)({'|'.join(re.escape(p) for p in _KNOWN_PILLARS)})"
)
_MACRO_RE = re.compile(
    r"(?i)Macro Tailwinds\s+(.{40,420}?)(?=TAM|Investment Pillars|Financial Value|\Z)"
)
_POSITIVE_SECTION_RE = re.compile(
    r"(?i)Key Positive Indicators\s+(.+?)(?=Key Risks|Due Diligence|Overall|\Z)",
    re.DOTALL,
)
_RISKS_SECTION_RE = re.compile(
    r"(?i)Key Risks\s*&\s*Concerns\s+(.+?)(?=Due Diligence|Overall Investment|\Z)",
    re.DOTALL,
)
_F01_MILESTONE_START_RE = re.compile(
    r"(?i)(Gross Margin > \d+%|EBITDA Breakeven|PAT Breakeven|FCF Positive|"
    r"Revenue > INR [\d,]+ Cr)\s+(FY\d{4})\s+"
)
_VERDICT_RE = re.compile(r"(?i)Verdict\s+(.{40,320}?)(?=Disclaimer|\Z)", re.DOTALL)
_F01_SEGMENT_WINDOW = 180


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_RE.split(re.sub(r"\s+", " ", text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 20]


def _hits(sentences: list[str], needles: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for sentence in sentences:
        low = sentence.lower()
        if any(n in low for n in needles):
            found.append(sentence)
    return found


def _clip_f01(text: str, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def _is_f01_noise(text: str) -> bool:
    low = text.lower()
    return any(n in low for n in _BAD_F01)


def _extract_bullets(block: str, *, limit: int = 6) -> list[str]:
    parts = re.split(r"[\u007f\u2022]\s*", block or "")
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = _clip_f01(part)
        if len(cleaned) < 15 or _is_f01_noise(cleaned):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _f01_segment_slices(text: str, header_re: re.Pattern[str]) -> list[tuple[str, str]]:
    bounded = (text or "")[:50_000]
    hits = list(header_re.finditer(bounded))
    slices: list[tuple[str, str]] = []
    for idx, hit in enumerate(hits):
        label = re.sub(r"\s+", " ", hit.group(1)).strip()
        seg_start = hit.end()
        if idx + 1 < len(hits):
            seg_end = min(hits[idx + 1].start(), seg_start + _F01_SEGMENT_WINDOW)
        else:
            seg_end = min(len(bounded), seg_start + _F01_SEGMENT_WINDOW)
        slices.append((label, bounded[seg_start:seg_end]))
    return slices


def _parse_f01_pillars(text: str) -> list[str]:
    drivers: list[str] = []
    for name, segment in _f01_segment_slices(text, _PILLAR_HEADER_RE):
        note = _clip_f01(segment, 160)
        if len(note) < 20:
            continue
        drivers.append(f"{name} — {note}")
    return drivers


def _parse_f01_drivers(text: str) -> list[str]:
    drivers: list[str] = []
    drivers.extend(_parse_f01_pillars(text))
    macro = _MACRO_RE.search(text or "")
    if macro:
        for sent in _sentences(macro.group(1))[:1]:
            if not _is_f01_noise(sent):
                drivers.insert(0, _clip_f01(sent))
    positive = _POSITIVE_SECTION_RE.search(text or "")
    if positive:
        drivers.extend(_extract_bullets(positive.group(1), limit=2))
    seen: set[str] = set()
    deduped: list[str] = []
    for item in drivers:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _parse_f01_risks(text: str) -> list[str]:
    section = _RISKS_SECTION_RE.search(text or "")
    if section:
        bullets = _extract_bullets(section.group(1), limit=6)
        if bullets:
            return bullets
    sentences = [s for s in _sentences(text or "") if not _is_f01_noise(s)]
    return _hits(sentences, _BREAKERS + ("risk", "concern", "competition"))[:6]


def _parse_f01_must_be_true(text: str) -> list[str]:
    out: list[str] = []
    bounded = text or ""
    hits = list(_F01_MILESTONE_START_RE.finditer(bounded))
    for idx, hit in enumerate(hits):
        detail_start = hit.end()
        if idx + 1 < len(hits):
            detail_end = hits[idx + 1].start()
        else:
            detail_end = min(len(bounded), detail_start + 100)
        detail = _clip_f01(bounded[detail_start:detail_end], 80)
        if len(detail) >= 5:
            out.append(f"{hit.group(1)} {hit.group(2)} — {detail}")
    verdict = _VERDICT_RE.search(bounded)
    if verdict:
        bit = _clip_f01(verdict.group(1), 180)
        if bit and not _is_f01_noise(bit):
            out.append(bit)
    for sent in _hits(_sentences(bounded), _MUST):
        if not _is_f01_noise(sent):
            out.append(_clip_f01(sent))
    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _score_f01(text: str) -> tuple[int, list[str]]:
    low = text.lower()
    score = 5
    notes: list[str] = ["base 5"]
    if "tam" in low or "sam" in low:
        score += 1
        notes.append("+1 market sizing")
    if "cagr" in low or "penetration" in low:
        score += 1
        notes.append("+1 growth trajectory")
    if "vertical integration" in low:
        score += 1
        notes.append("+1 vertical integration")
    if "tailwind" in low or "fame-ii" in low:
        score += 1
        notes.append("+1 macro tailwind")
    penalties = 0
    if "operating loss" in low or "cash burn" in low:
        penalties += 1
        notes.append("-1 losses/burn")
    if "competitive pressure" in low or "counter-attack" in low:
        penalties += 1
        notes.append("-1 competition")
    if "subsidy" in low and "risk" in low:
        penalties += 1
        notes.append("-1 subsidy risk")
    if "supply chain" in low:
        penalties += 1
        notes.append("-1 supply chain")
    score -= min(3, penalties)
    return max(1, min(10, score)), notes[:8]


def _pad(items: list[str], fillers: list[str], n: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items + fillers:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= n:
            return out
    while len(out) < n:
        out.append("Insufficient source text.")
    return out


def _optional_llm_refine(spec: dict[str, Any], *, role_code: str, text: str) -> dict[str, Any]:
    """Hook only. Schema never depends on an API key.

    Set AGETIC_CDD_FOUNDATIONS_LLM later to fill; ignored in v1.
    """
    _ = os.environ.get("AGETIC_CDD_FOUNDATIONS_LLM"), role_code, text
    return spec


def _extract_f01(text: str, sources: list[str]) -> dict[str, Any]:
    drivers = [_clip_f01(d) for d in _parse_f01_drivers(text)]
    must = [_clip_f01(m) for m in _parse_f01_must_be_true(text)]
    risks = [_clip_f01(r) for r in _parse_f01_risks(text)]
    clean_sentences = [_clip_f01(s) for s in _sentences(text) if not _is_f01_noise(s)]

    if len(drivers) < 3:
        drivers.extend(_clip_f01(s) for s in _hits(clean_sentences, _GROWTH)[:3])
    if len(risks) < 3:
        risks.extend(_clip_f01(s) for s in _hits(clean_sentences, ("risk", "concern"))[:3])
    if len(must) < 2:
        must.extend(_clip_f01(s) for s in _hits(clean_sentences, _MUST)[:2])

    score, notes = _score_f01(text)
    low = text.lower()
    if "strategic buyer" in low or "synerg" in low:
        framework: ThesisFramework = "strategic"
    elif "growth equity" in low or "cagr" in low:
        framework = "growth_equity"
    else:
        framework = "pe"
    model = F01Thesis(
        investment_drivers=_pad(drivers, clean_sentences),
        must_be_true=_pad(must, clean_sentences),
        deal_breaker_risks=_pad(risks, clean_sentences),
        attractiveness_score=score,
        thesis_framework=framework,
        scoring_notes=notes,
        sources=list(sources),
    )
    return model.model_dump(mode="json")


def _extract_f02(text: str, prior_spec: dict | None) -> dict[str, Any]:
    sentences = _sentences(text)
    hooks = _hits(sentences, ("hook", "ic ", "investment committee", "why now", "angle", "teaser"))
    if not hooks:
        hooks = sentences[:3]
    score = None
    if prior_spec and isinstance(prior_spec.get("attractiveness_score"), int):
        score = int(prior_spec["attractiveness_score"])
        hooks = [f"F-01 attractiveness score {score}"] + hooks
    streams = [
        WorkstreamItem(name="Commercial", priority=1 if score and score >= 7 else 2),
        WorkstreamItem(name="Financial", priority=2),
        WorkstreamItem(name="Legal / NDA", priority=1 if "nda" in text.lower() else 3),
        WorkstreamItem(name="Operations", priority=3),
        WorkstreamItem(name="Technology / IP", priority=2 if "patent" in text.lower() or "software" in text.lower() else 4),
        WorkstreamItem(name="ESG", priority=4),
    ]
    milestones: list[MilestoneItem] = []
    for match in _WEEK_RE.finditer(text):
        milestones.append(MilestoneItem(week=int(match.group(1)), label=match.group(2).strip()))
    if not milestones:
        milestones = [
            MilestoneItem(week=1, label="Confirm thesis and IC hooks"),
            MilestoneItem(week=2, label="Process letter / NDA review"),
            MilestoneItem(week=3, label="Entity and management baseline"),
        ]
    granularity: TimelineGranularity = "daily" if re.search(r"\bdaily\b", text, re.I) else "weekly"
    model = F02Roadmap(
        ic_hooks=_pad(hooks, sentences),
        workstreams=streams,
        milestones=milestones[:6],
        consumes_f01_score=score,
        timeline_granularity=granularity,
    )
    return model.model_dump(mode="json")


def _extract_f03(text: str, coverage: str) -> dict[str, Any]:
    sentences = _sentences(text)
    dates: list[DatedItem] = []
    for match in _DATE_RE.finditer(text):
        value = match.group(1)
        start = max(0, match.start() - 40)
        label = text[start:match.start()].strip(" :,-") or "date"
        label = re.sub(r"\s+", " ", label).split()[-4:]
        dates.append(DatedItem(label=" ".join(label) or "date", value=value))
    rules = _hits(sentences, ("submit", "binding", "non-binding", "process letter", "bid", "deadline", "round"))
    unusual = _hits(sentences, ("unusual", "go-shop", "exclusiv", "break fee", "staple", "management presentation"))
    if coverage == "missing" or (not text.strip() and coverage != "full"):
        mapped: ProcessCoverage = "missing_process_letter"
    elif coverage == "partial":
        mapped = "partial"
    else:
        mapped = "full" if dates or rules else "partial"
    model = F03Process(
        dates=dates[:8],
        submission_rules=rules[:6] or (["No submission rules extracted."] if mapped != "missing_process_letter" else []),
        unusual_terms=unusual[:6],
        coverage=mapped,
    )
    return model.model_dump(mode="json")


def _parse_legal_name(text: str) -> str | None:
    label = _LEGAL_NAME_LABEL_RE.search(text or "")
    if label:
        return re.sub(r"\s+", " ", label.group(1)).strip()
    for match in _LEGAL_NAME_RE.finditer(text or ""):
        candidate = re.sub(r"\s+", " ", match.group(1)).strip()
        low = candidate.lower()
        if any(noise in low for noise in ("parameter details", "legal name", "company fact")):
            continue
        return candidate
    return None


def _parse_f05_governance_notes(text: str) -> list[str]:
    notes: list[str] = []
    cin = _CIN_RE.search(text or "")
    if cin:
        notes.append(f"CIN {cin.group(1).strip()}")
    hq = _HQ_RE.search(text or "")
    if hq:
        hq_text = re.sub(r"\s+", " ", hq.group(1)).strip()[:120]
        notes.append(f"Headquarters: {hq_text}")
    listed = re.search(r"(?i)(BSE\s*&\s*NSE|Listed\s+(?:August\s+)?\d{4})", text or "")
    if listed:
        notes.append(f"Listing: {listed.group(1).strip()}")
    cap = re.search(r"(?i)Market Cap[^~]*~?([\d,]+ Crore[^.]*)", text or "")
    if cap:
        notes.append(f"Market cap: {cap.group(1).strip()[:80]}")
    board = re.search(r"(?i)Board of Directors.{0,40}?Independent", text or "")
    if board:
        notes.append("Board includes independent directors (post-IPO structure).")
    for match in re.finditer(
        r"(?i)(Bhavish Aggarwal|Harish Abichandani|Suvonil Chatterjee)[^A-Z]{0,30}"
        r"(Chairman|Managing Director|Chief Financial Officer|Chief Technology Officer)",
        text or "",
    ):
        notes.append(f"{match.group(1).strip()} — {match.group(2).strip()}")
        if len(notes) >= 6:
            break
    if not notes:
        notes = _hits(_sentences(text), ("board", "cin", "governance", "director", "shareholder"))[:4]
    seen: set[str] = set()
    clipped: list[str] = []
    for note in notes:
        cleaned = re.sub(r"\s+", " ", note).strip()[:220]
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        clipped.append(cleaned)
        if len(clipped) >= 6:
            break
    return clipped


def _extract_f05(text: str) -> dict[str, Any]:
    sentences = _sentences(text)
    name = _parse_legal_name(text)
    jur_match = _JURISDICTION_RE.search(text or "")
    jurisdiction = jur_match.group(1).strip() if jur_match else None
    if not jurisdiction:
        hq = _HQ_RE.search(text or "")
        if hq:
            jurisdiction = re.sub(r"\s+", " ", hq.group(1)).strip()[:80]
    year_match = _FOUNDED_RE.search(text or "") or _YEAR_RE.search(text or "")
    entity_type = None
    low = text.lower()
    if "private limited" in low or "pvt" in low:
        entity_type = "private_limited"
    elif "public" in low or "listed" in low:
        entity_type = "public"
    elif "llc" in low:
        entity_type = "llc"
    elif "limited" in low or "ltd" in low:
        entity_type = "limited"
    shares = [m.group(1) for m in _SHARE_RE.finditer(text)]
    agent = None
    agent_hit = re.search(r"registered agent[:\s]+(.{3,80}?)(?:\.|$)", text, re.I)
    if agent_hit:
        agent = agent_hit.group(1).strip()
    notes = _parse_f05_governance_notes(text)
    model = F05Entity(
        legal_name=name,
        jurisdiction=jurisdiction,
        entity_type=entity_type,
        incorporation_date=year_match.group(1) if year_match else None,
        share_classes=list(dict.fromkeys(shares))[:6],
        registered_agent=agent,
        governance_notes=notes,
    )
    return model.model_dump(mode="json")


def _is_f06_noise(text: str) -> bool:
    low = text.lower()
    return any(n in low for n in _BAD_F06) or len(text) > 240


def _normalize_exec_role(raw: str) -> str:
    role = re.sub(r"\s+", " ", raw).strip()
    if role.upper().startswith("CEO"):
        return "CEO"
    if role.upper().startswith("VP"):
        return role.replace("—", "-").strip()
    return role.split("—")[0].split("–")[0].strip()


def _risk_to_scores(level: str) -> tuple[int, int]:
    low = level.lower()
    if "high" in low:
        return 5, 1
    if "medium" in low:
        return 4, 2
    return 3, 3


def _is_valid_person_name(name: str) -> bool:
    low = name.lower()
    if any(bad in low for bad in ("title", "tenure", "risk", "experience", "succession", "parameter", "name ")):
        return False
    parts = name.split()
    return 2 <= len(parts) <= 4


def _leadership_section(text: str) -> str:
    match = re.search(
        r"(?i)Leadership Team.{0,120}?Succession Risk\s+(.+?)(?=Workforce Overview|\Z)",
        text or "",
        re.DOTALL,
    )
    if match:
        return match.group(1)
    return text or ""


def _parse_leadership_team(text: str) -> list[CSuiteItem]:
    suite: list[CSuiteItem] = []
    seen: set[str] = set()
    section = _leadership_section(text)
    for match in _HR_LEADER_RE.finditer(section):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        if not _is_valid_person_name(name):
            continue
        role = _normalize_exec_role(match.group(2))
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        crit, replace = _risk_to_scores(match.group(3))
        if "ceo" in role.lower() or "founder" in role.lower():
            crit = max(crit, 5)
            replace = 1
        suite.append(CSuiteItem(role=role, name=name, criticality=crit, replaceability=replace))
    if len(suite) < 3:
        for match in _CORP_EXEC_RE.finditer(text or ""):
            name = re.sub(r"\s+", " ", match.group(2)).strip()
            role = _normalize_exec_role(match.group(1))
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            crit = 5 if role == "CEO" else 4 if role == "CFO" else 3
            replace = 1 if crit == 5 else 2 if crit == 4 else 3
            suite.append(CSuiteItem(role=role, name=name, criticality=crit, replaceability=replace))
    if len(suite) < 2:
        for match in _CSUITE_RE.finditer(text or ""):
            role = match.group(1)
            name = match.group(2).strip()
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            crit = 5 if role in {"CEO", "Founder"} else 4 if role in {"CFO", "COO"} else 3
            replace = 1 if crit == 5 else 2 if crit == 4 else 3
            suite.append(CSuiteItem(role=role, name=name, criticality=crit, replaceability=replace))
    return suite[:8]


def _parse_f06_succession_gaps(text: str, prior_spec: dict | None) -> list[str]:
    gaps: list[str] = []
    section = _HR_RISK_SECTION_RE.search(text or "")
    if section:
        gaps.extend(_extract_bullets(section.group(1), limit=6))
    tech_attr = re.search(r"(?i)Attrition\s*[—–-]\s*Technology\s+(\d+(?:\.\d+)?)%", text or "")
    if tech_attr:
        gaps.append(f"Technology attrition {tech_attr.group(1)}% — IP continuity risk.")
    enps = re.search(r"(?i)eNPS[^0-9]*(\d+)\s+35", text or "")
    if enps:
        gaps.append(f"eNPS {enps.group(1)} vs 35 benchmark — cultural perception gap.")
    eng = re.search(r"(?i)Employee Engagement Score\s+(\d+)\s*/\s*100", text or "")
    if eng:
        gaps.append(f"Employee engagement {eng.group(1)}/100 — below benchmark.")
    if not gaps:
        for sent in _sentences(text or ""):
            if _is_f06_noise(sent):
                continue
            low = sent.lower()
            if any(k in low for k in ("succession", "key-man", "key person", "attrition")):
                gaps.append(_clip_f01(sent))
    legal = prior_spec.get("legal_name") if isinstance(prior_spec, dict) else None
    if legal and "parameter details" not in legal.lower() and "legal name" not in legal.lower():
        gaps = [f"{legal}: {g}" if not g.startswith(legal) else g for g in gaps]
    seen: set[str] = set()
    deduped: list[str] = []
    for gap in gaps:
        cleaned = _clip_f01(gap, 220)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
        if len(deduped) >= 6:
            break
    return deduped


def _extract_f06(text: str, prior_spec: dict | None) -> dict[str, Any]:
    suite = _parse_leadership_team(text)
    gaps = _parse_f06_succession_gaps(text, prior_spec)
    depth_match = re.search(r"\b(\d{1,2})\s+(?:layers|levels|direct reports)\b", text or "", re.I)
    span = None
    span_match = re.search(r"span of control[:\s]+(.{3,60}?)(?:\.|$)", text or "", re.I)
    if span_match:
        span = span_match.group(1).strip()
    risk = 5
    if gaps:
        risk += min(3, len(gaps))
    if any(item.criticality >= 5 and item.replaceability <= 2 for item in suite):
        risk += 1
    if any("31%" in g or "key-man" in g.lower() for g in gaps):
        risk += 1
    risk = max(1, min(10, risk))
    model = F06OrgRisk(
        org_depth=int(depth_match.group(1)) if depth_match else (2 if suite else None),
        span_of_control=span,
        c_suite=suite,
        succession_gaps=gaps,
        org_risk_score=risk,
        consumes_f05=bool(prior_spec),
    )
    return model.model_dump(mode="json")


_FIP_KNOWN_COMPONENTS: tuple[str, ...] = (
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
_FIP_BATTERY_PHASE_RE = re.compile(
    r"(?i)(Phase \d+ \([^)]+\))\s+(FY[\d–\-+FY\s]+?)\s+"
    r"([^~]+?)\s+(~[\d.]+\s*Wh/kg)\s+(~USD\s*[\d]+/kWh)"
)
_FIP_MOVEOS_SECTION_RE = re.compile(
    r"(?i)MoveOS Software Ecosystem\s+(.+?)(?=Technology Stack Assessment|\Z)",
    re.DOTALL,
)
_FIP_TECH_RISKS_SECTION_RE = re.compile(
    r"(?i)Technical Risks\s+(.+?)(?:\Z)",
    re.DOTALL,
)
_BAD_FIP = (
    "insight snapshot", "component technology maturity", "technical due diligence software",
    "r&d metric fy20", "battery technology roadmap phase timeline",
)


def _is_fip_noise(text: str) -> bool:
    low = text.lower()
    return any(n in low for n in _BAD_FIP) or len(text) > 220


def _parse_fip_stack_rows(text: str) -> list[str]:
    bounded = text or ""
    rows: list[tuple[str, float]] = []
    for index, component in enumerate(_FIP_KNOWN_COMPONENTS):
        start = bounded.find(component)
        if start < 0:
            continue
        end = len(bounded)
        for next_component in _FIP_KNOWN_COMPONENTS[index + 1 :]:
            pos = bounded.find(next_component, start + len(component))
            if pos >= 0:
                end = pos
                break
        segment = bounded[start:end]
        roadmap = segment.find("Battery Technology Roadmap")
        if roadmap >= 0:
            segment = segment[:roadmap]
        maturity_match = re.search(r"(\d\.\d)", segment)
        if not maturity_match:
            continue
        maturity = float(maturity_match.group(1))
        technology = re.sub(r"\s+", " ", segment[len(component) : maturity_match.start()]).strip(" ,—-")
        risk = re.sub(r"\s+", " ", segment[maturity_match.end() :]).strip(" ,—-")
        line = f"{component}: {technology} (maturity {maturity}/5)"
        if risk:
            line += f" — {risk}"
        rows.append((_clip_f01(line, 220), maturity))
    rows.sort(key=lambda item: item[1])
    return [line for line, _ in rows]


def _parse_fip_battery_phases(text: str) -> list[str]:
    out: list[str] = []
    for match in _FIP_BATTERY_PHASE_RE.finditer(text or ""):
        phase = match.group(1).strip()
        timeline = re.sub(r"\s+", " ", match.group(2)).strip()
        chemistry = re.sub(r"\s+", " ", match.group(3)).strip(" ,—-")
        density = match.group(4).strip()
        cost = match.group(5).strip()
        out.append(
            _clip_f01(f"{phase} ({timeline}): {chemistry}, {density}, {cost}", 220)
        )
        if len(out) >= 4:
            break
    return out


def _parse_fip_patents(text: str) -> list[str]:
    out: list[str] = []
    patents = re.search(r"(?i)Patents Filed \(Cumulative\)\s+(?:\d+\s+)*(\d+)\b", text or "")
    if patents:
        out.append(f"Patents filed (cumulative): {patents.group(1)}")
    rd_spend = re.search(r"(?i)R&D Spend \(INR Crore\)\s+(?:\d+\s+)*(\d+)\b", text or "")
    if rd_spend:
        out.append(f"R&D spend (FY2024E): INR {rd_spend.group(1)} Crore")
    engineers = re.search(r"(?i)Engineers \(R&D Headcount\)\s+(?:[\d,]+\s+)*([\d,]+)\b", text or "")
    if engineers:
        out.append(f"R&D engineers: {engineers.group(1)}")
    pct = re.search(r"(?i)R&D as % of Revenue\s+(?:[\d.]+%\s+)*([\d.]+)%\b", text or "")
    if pct:
        out.append(f"R&D as % of revenue (FY2024E): {pct.group(1)}%")
    return out[:4]


def _parse_fip_moveos_notes(text: str) -> list[str]:
    section = _FIP_MOVEOS_SECTION_RE.search(text or "")
    if not section:
        return []
    block = re.sub(r"\s+", " ", section.group(1)).strip()
    out: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", block):
        cleaned = _clip_f01(part, 180)
        if len(cleaned) >= 30 and not _is_fip_noise(cleaned):
            out.append(cleaned)
        if len(out) >= 2:
            break
    return out


def _parse_fip_technical_risks(text: str) -> list[str]:
    section = _FIP_TECH_RISKS_SECTION_RE.search(text or "")
    if not section:
        return []
    return [_clip_f01(item, 200) for item in _extract_bullets(section.group(1), limit=5)]


def _extract_fip_technical_dd(text: str) -> dict[str, Any]:
    stack = _parse_fip_stack_rows(text)
    battery = _parse_fip_battery_phases(text)
    patents = _parse_fip_patents(text)
    moveos = _parse_fip_moveos_notes(text)
    risks = _parse_fip_technical_risks(text)
    if not stack and not patents:
        return _extract_ip_generic(text)
    model = FIpBaseline(
        patents=patents or ["No patent metrics extracted."],
        core_tech=(stack[:5] + battery)[:8] or ["No core technology rows extracted."],
        architecture_notes=(moveos + risks)[:8] or ["No architecture notes extracted."],
    )
    return model.model_dump(mode="json")


def _extract_ip_generic(text: str) -> dict[str, Any]:
    sentences = _sentences(text)
    model = FIpBaseline(
        patents=_hits(sentences, ("patent", "ip ", "trademark", "copyright"))[:6],
        core_tech=_hits(sentences, ("software", "os", "battery", "ota", "firmware", "architecture"))[:6],
        architecture_notes=_hits(sentences, ("architecture", "stack", "linux", "cloud"))[:6],
    )
    return model.model_dump(mode="json")


def _extract_ip(text: str) -> dict[str, Any]:
    if re.search(r"(?i)Technology Stack Assessment|MoveOS Software Ecosystem|Technical Due Diligence", text or ""):
        return _extract_fip_technical_dd(text)
    return _extract_ip_generic(text)


_FESG_ENV_AREAS = (
    "environmental clearance",
    "battery safety",
    "fame-ii subsidy",
)
_FESG_LABOUR_AREAS = (
    "labor law",
    "labour",
    "employment law",
    "ex-employee",
)
_FESG_GOV_AREAS = (
    "sebi",
    "companies act",
    "data protection",
    "dpdpa",
    "ccpa consumer",
    "corporate governance",
)
_FESG_GOVERNANCE_SECTION_RE = re.compile(
    r"(?i)Corporate Governance Framework\s+(.+?)(?=Regulatory Compliance Status|\Z)",
    re.DOTALL,
)
_BAD_FESG = (
    "insight snapshot", "regulatory area governing", "ip category", "matter nature",
    "intellectual property portfolio", "key areas patents", "legal due diligence regulatory",
)


def _is_fesg_noise(text: str) -> bool:
    low = text.lower()
    return any(n in low for n in _BAD_FESG) or len(text) > 220


def _fesg_regulatory_line(area: str, status: str, level: str) -> str:
    return _clip_f01(f"{area} — {status} ({level} risk)", 220)


def _parse_fesg_regulatory_buckets(text: str) -> tuple[list[str], list[str], list[str]]:
    themes: list[str] = []
    labour: list[str] = []
    environment: list[str] = []
    seen: set[str] = set()
    for match in _F04_REGULATORY_RE.finditer(text or ""):
        area = re.sub(r"\s+", " ", match.group(1)).strip()
        key = area.lower()
        if key in seen:
            continue
        seen.add(key)
        line = _fesg_regulatory_line(area, match.group(2).strip(), match.group(3).title())
        if any(token in key for token in _FESG_ENV_AREAS):
            environment.append(line)
        elif any(token in key for token in _FESG_LABOUR_AREAS):
            labour.append(line)
        elif any(token in key for token in _FESG_GOV_AREAS):
            themes.append(line)
    environment.sort(key=lambda item: ("high risk" in item.lower(), "medium risk" in item.lower()), reverse=True)
    labour.sort(key=lambda item: ("high risk" in item.lower(), "medium risk" in item.lower()), reverse=True)
    themes.sort(key=lambda item: ("high risk" in item.lower(), "medium risk" in item.lower()), reverse=True)
    return themes, labour, environment


def _parse_fesg_governance_notes(text: str) -> list[str]:
    out: list[str] = []
    section = _FESG_GOVERNANCE_SECTION_RE.search(text or "")
    if section:
        block = re.sub(r"\s+", " ", section.group(1)).strip()
        for part in re.split(r"(?<=[.!?])\s+", block):
            cleaned = _clip_f01(part, 180)
            if len(cleaned) >= 40 and not _is_fesg_noise(cleaned):
                out.append(cleaned)
            if len(out) >= 2:
                break
    for pattern in (
        r"(?i)CCPA proceedings, if resolved adversely[^.]*\.",
        r"(?i)Data protection implementation needs to be completed[^.]*\.",
        r"(?i)Overall legal risk:\s*(?:Low|Medium|High)\.",
    ):
        match = re.search(pattern, text or "")
        if match:
            out.append(_clip_f01(match.group(0), 180))
    verdict = _F04_LEGAL_VERDICT_RE.search(text or "")
    if verdict:
        out.append(f"Overall legal risk rated {verdict.group(1).title()}.")
    seen: set[str] = set()
    deduped: list[str] = []
    for note in out:
        key = note.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(note)
    return deduped[:4]


def _parse_fesg_litigation_flags(text: str) -> tuple[list[str], list[str]]:
    labour: list[str] = []
    themes: list[str] = []
    for match in _F04_LITIGATION_RE.finditer(text or ""):
        bit = _clip_f01(re.sub(r"\s+", " ", match.group(0)).strip(), 200)
        low = bit.lower()
        if "ex-employee" in low or "employment law" in low:
            labour.append(bit)
        elif "ccpa" in low:
            themes.append(bit)
    return themes, labour


def _extract_fesg_legal_dd(text: str) -> dict[str, Any]:
    themes, labour, environment = _parse_fesg_regulatory_buckets(text)
    themes.extend(_parse_fesg_governance_notes(text))
    lit_themes, lit_labour = _parse_fesg_litigation_flags(text)
    themes.extend(lit_themes)
    labour.extend(lit_labour)
    if not themes and not labour and not environment:
        return _extract_esg_generic(text)
    model = FEsgBaseline(
        themes=themes[:6] or ["No governance themes extracted."],
        labour_flags=labour[:6] or ["No labour flags extracted."],
        environment_flags=environment[:6] or ["No environment flags extracted."],
    )
    return model.model_dump(mode="json")


def _extract_esg_generic(text: str) -> dict[str, Any]:
    sentences = _sentences(text)
    model = FEsgBaseline(
        themes=_hits(sentences, ("esg", "sustainability", "governance"))[:6],
        labour_flags=_hits(sentences, ("labour", "labor", "safety", "dei", "workforce"))[:6],
        environment_flags=_hits(sentences, ("emission", "environment", "climate", "waste"))[:6],
    )
    return model.model_dump(mode="json")


def _extract_esg(text: str) -> dict[str, Any]:
    if re.search(
        r"(?i)Regulatory Compliance Status|Corporate Governance Framework|Environmental Clearance",
        text or "",
    ):
        return _extract_fesg_legal_dd(text)
    return _extract_esg_generic(text)


_DISPATCH = {
    "F-01": lambda text, sources, coverage, prior: _extract_f01(text, sources),
    "F-02": lambda text, sources, coverage, prior: _extract_f02(text, prior),
    "F-03": lambda text, sources, coverage, prior: _extract_f03(text, coverage),
    "F-04": lambda text, sources, coverage, prior: _extract_f04(text),
    "F-05": lambda text, sources, coverage, prior: _extract_f05(text),
    "F-06": lambda text, sources, coverage, prior: _extract_f06(text, prior),
    "F-IP": lambda text, sources, coverage, prior: _extract_ip(text),
    "F-ESG": lambda text, sources, coverage, prior: _extract_esg(text),
}


def findings_from_f01_spec(spec: dict[str, Any]) -> list[str]:
    """Structured finding lines for Strategic Direction (F-01)."""
    out: list[str] = []
    score = spec.get("attractiveness_score")
    framework = spec.get("thesis_framework")
    if score is not None:
        out.append(f"Attractiveness: {score}/10 ({framework or 'unknown'})")
    for row in spec.get("investment_drivers") or []:
        if isinstance(row, str) and row.strip():
            out.append(f"Driver: {row.strip()}")
    for row in spec.get("must_be_true") or []:
        if isinstance(row, str) and row.strip():
            out.append(f"Must be true: {row.strip()}")
    for row in spec.get("deal_breaker_risks") or []:
        if isinstance(row, str) and row.strip():
            out.append(f"Risk: {row.strip()}")
    return out[:8]


def findings_from_f05_spec(spec: dict[str, Any]) -> list[str]:
    """Structured finding lines for Company Background (F-05)."""
    out: list[str] = []
    if spec.get("legal_name"):
        out.append(f"Legal name: {spec['legal_name']}")
    if spec.get("jurisdiction"):
        out.append(f"Jurisdiction: {spec['jurisdiction']}")
    if spec.get("incorporation_date"):
        out.append(f"Founded: {spec['incorporation_date']}")
    if spec.get("entity_type"):
        out.append(f"Entity type: {spec['entity_type']}")
    out.extend(spec.get("governance_notes") or [])
    return out[:8]


def findings_from_f04_spec(spec: dict[str, Any]) -> list[str]:
    """Structured finding lines for Regulatory Compliance (F-04)."""
    out: list[str] = []
    seen: set[str] = set()
    risks = spec.get("risks") or []
    for row in sorted(
        (r for r in risks if isinstance(r, dict)),
        key=lambda item: int(item.get("severity") or 0),
        reverse=True,
    ):
        clause = (row.get("clause") or "").strip()
        key = clause.lower()
        if clause and not _is_f04_noise(clause) and key not in seen:
            seen.add(key)
            out.append(clause)
        if len(out) >= 5:
            break
    for note in spec.get("data_handling") or []:
        if isinstance(note, str) and note.strip():
            key = note.strip().lower()
            if key not in seen:
                seen.add(key)
                out.append(note.strip())
        if len(out) >= 6:
            break
    for flag in spec.get("restricted_activities") or []:
        if isinstance(flag, str) and flag.strip():
            line = f"Contract: {flag.strip()}"
            key = line.lower()
            if key not in seen:
                seen.add(key)
                out.append(line)
        if len(out) >= 8:
            break
    return out[:8]


def findings_from_f06_spec(spec: dict[str, Any]) -> list[str]:
    """Structured finding lines for Management Quality (F-06)."""
    out: list[str] = []
    if spec.get("org_risk_score") is not None:
        out.append(f"Org risk score: {spec['org_risk_score']}/10")
    for row in spec.get("c_suite") or []:
        if isinstance(row, dict) and row.get("name"):
            role = row.get("role") or "Executive"
            crit = row.get("criticality")
            bit = f"{role}: {row['name']}"
            if crit is not None:
                bit += f" (criticality {crit}/5)"
            out.append(bit)
        if len(out) >= 5:
            break
    for gap in spec.get("succession_gaps") or []:
        if isinstance(gap, str) and gap.strip():
            out.append(gap.strip())
        if len(out) >= 8:
            break
    return out[:8]


def findings_from_fip_spec(spec: dict[str, Any]) -> list[str]:
    """Structured finding lines for IP & Technology (F-IP)."""
    out: list[str] = []
    seen: set[str] = set()

    applies = [
        t for t in (spec.get("technology_map") or [])
        if isinstance(t, dict) and str(t.get("applies") or "").lower() == "yes"
    ]
    if applies:
        out.append(f"{len(applies)} run-category(ies) mapped")
    verified = [
        o for o in (spec.get("ownership_separation") or [])
        if isinstance(o, dict) and str(o.get("register_verified") or "").startswith("Yes")
    ]
    if verified:
        out.append(f"{len(verified)} register-verified right(s)")
        for o in verified[:2]:
            asset = str(o.get("asset") or "").strip()
            if asset:
                out.append(f"IP · {asset[:120]}")
    contradicted = (
        (spec.get("ip_advantage_reconcile") or {}).get("contradicted")
        if isinstance(spec.get("ip_advantage_reconcile"), dict) else []
    ) or []
    if contradicted:
        out.append(f"{len(contradicted)} IP-advantage contradiction(s)")

    for note in spec.get("patents") or []:
        if isinstance(note, str) and note.strip():
            key = note.strip().lower()
            if key not in seen and not _is_fip_noise(note):
                seen.add(key)
                out.append(note.strip())
        if len(out) >= 6:
            break
    for note in spec.get("architecture_notes") or []:
        if isinstance(note, str) and note.strip() and "moveos" in note.lower():
            key = note.strip().lower()
            if key not in seen:
                seen.add(key)
                out.append(note.strip())
            break
    for row in spec.get("core_tech") or []:
        if isinstance(row, str) and row.strip() and "maturity" in row.lower():
            key = row.strip().lower()
            if key not in seen and not _is_fip_noise(row):
                seen.add(key)
                out.append(row.strip())
        if len(out) >= 8:
            break
    for note in spec.get("architecture_notes") or []:
        if isinstance(note, str) and note.strip():
            key = note.strip().lower()
            if key in seen or _is_fip_noise(note):
                continue
            if any(token in note.lower() for token in ("battery thermal", "cybersecurity", "adas", "ota", "firmware")):
                seen.add(key)
                out.append(note.strip())
        if len(out) >= 8:
            break
    return out[:8]


def findings_from_fesg_spec(spec: dict[str, Any]) -> list[str]:
    """Structured finding lines for ESG & Sustainability (F-ESG)."""
    out: list[str] = []
    seen: set[str] = set()
    buckets = (
        spec.get("environment_flags") or [],
        spec.get("labour_flags") or [],
        spec.get("themes") or [],
    )
    for bucket in buckets:
        for line in bucket:
            if not isinstance(line, str) or not line.strip():
                continue
            key = line.strip().lower()
            if key in seen or _is_fesg_noise(line):
                continue
            if "high risk" in key or "medium risk" in key:
                seen.add(key)
                out.append(line.strip())
            if len(out) >= 4:
                break
        if len(out) >= 4:
            break
    for bucket in buckets:
        for line in bucket:
            if not isinstance(line, str) or not line.strip():
                continue
            key = line.strip().lower()
            if key in seen or _is_fesg_noise(line):
                continue
            seen.add(key)
            out.append(line.strip())
            if len(out) >= 8:
                break
        if len(out) >= 8:
            break
    return out[:8]


def extract_role_spec(
    role_code: str,
    text: str,
    *,
    sources: list[str] | None = None,
    coverage: str = "missing",
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    """Return typed spec JSON for a Foundation role. Heuristic only; no API key."""
    handler = _DISPATCH.get(role_code)
    if handler is None:
        return {"role_code": role_code, "empty": True}
    clipped = (text or "")[:50_000]
    spec = handler(clipped, list(sources or []), coverage, prior_spec)
    spec["role_code"] = role_code
    spec["extractor"] = "heuristic_v1"
    return _optional_llm_refine(spec, role_code=role_code, text=clipped)
