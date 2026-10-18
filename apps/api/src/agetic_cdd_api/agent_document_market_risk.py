"""Compose DiligenceIQ Market Risk — external risks sized to company numbers.

Competitor moves, customer losses, regulatory change, demand cycles.
Each risk row: trigger, population, timing, mechanism, mitigation.
Likelihood argued from evidence (not arbitrary scores). Downside
quantified where bounded. Early-warning indicators. Price vs structure.
Non-overlap with Internal Risk. Reject unnamed threats. Unsized risks
still reported with what would size them.

Dual-writes legacy DD-20 fields (market_risk_items / regulatory_items /
litigation_exposures / risk_flags / risk_notes).

No invest/pass. No company hardcoding.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+)?(?:recommend|advise|suggest)\s+(?:to\s+)?(?:invest|pass)\b"
)

_DOCUMENT_TITLE = "Market Risk"
_DD_CODE = "DD-20"
_AGENT_KEY = "market_risk"

_IDENTIFY_RULE = (
    "External risks that matter for this business and geography: mechanism, "
    "revenue or margin exposed, and the time over which each would act."
)
_LIKELIHOOD_RULE = (
    "Likelihood is argued from evidence — competitor behaviour, contract "
    "renewal dates, policy timetables, historical cycles — not from arbitrary "
    "numeric probabilities."
)
_DOWNSIDE_RULE = (
    "Where exposure is bounded, downside is quantified: EBITDA if the largest "
    "contract is lost, or if volume falls to the last-downturn level."
)
_WARN_RULE = (
    "Each material risk has an early-warning indicator — what the buyer should "
    "watch monthly after completion."
)
_STRUCT_RULE = (
    "Risks that change price are separated from those that change structure "
    "(escrow, earn-out, specific indemnity, condition precedent)."
)
_UNSIZED_RULE = (
    "Risks that cannot be sized are still reported, with what would size them."
)
_ROW_RULE = (
    "Each external risk row states trigger, population exposed, timing, "
    "mechanism, and mitigation (or what would mitigate)."
)
_INTERNAL_CROSS_RULE = (
    "Market Risk stays external. Key-person, controls, cash/covenant strain "
    "and governance belong in Internal Risk — cross-check and do not restate."
)
_UNNAMED_RULE = (
    "Reject unnamed or generic threats (e.g. 'market risk', 'macro headwinds') "
    "that lack a named trigger and population."
)
_INTERNAL_FAMILY_RE = re.compile(
    r"(?i)\b(key[- ]?person|succession|founder\s+depart|"
    r"governance|board\s+weakness|control\s+fail|"
    r"reconcil(?:iation)?\s+not|approval\s+missing|"
    r"covenant\s+breach|liquidity\s+strain|cash\s+strain|"
    r"internal\s+control|erp\s+failure|systems?\s+outage\s+internal)\b"
)
_UNNAMED_RE = re.compile(
    r"(?i)^(market\s+risks?|external\s+risks?|macro(?:\s+headwinds?)?|"
    r"headwinds?|threats?|risks?|various\s+risks?|"
    r"general\s+(?:market\s+)?risks?|uncertainty)$"
)

_SUBSIDY_RE = re.compile(
    r"(?i)\b(FAME[-\s]?I{1,3}|PLI|subsidy(?:\s+reduction|\s+cut|\s+delay)?|"
    r"incentive\s+(?:cut|delay|change)|policy\s+(?:change|timetable))\b"
)
_OEM_RE = re.compile(
    r"(?i)\b(OEM\s+counter[- ]?attack|competitor\s+(?:move|pricing|share)|"
    r"share\s+(?:loss|erosion)|price\s+war|new\s+entrant)\b"
)
_CUSTOMER_RE = re.compile(
    r"(?i)\b(customer\s+loss|churn|contract\s+(?:loss|non[- ]?renewal|expiry)|"
    r"concentration|largest\s+customer|top\s+\d+\s+customers?)\b"
)
_CYCLE_RE = re.compile(
    r"(?i)\b(demand\s+cycle|downturn|recession|volume\s+(?:fall|decline|drop)|"
    r"cyclical|seasonal\s+demand)\b"
)
_SUPPLY_EXT_RE = re.compile(
    r"(?i)\b(supply\s+chain\s+disruption|China\s+supply|import\s+duty|"
    r"customs|battery\s+cost|commodity\s+spike)\b"
)
_REG_RE = re.compile(
    r"(?i)\b(regulatory\s+change|compliance|litigation|class\s+complaint|"
    r"CCPA|DPDPA|SEBI|GST|recovery\s+notice)\b"
)
_STRUCT_CUE = re.compile(
    r"(?i)\b(escrow|earn[- ]?out|indemnit(?:y|ies)|condition\s+precedent|"
    r"\bCP\b|holdback|price\s+chip|purchase\s+price\s+adjustment)\b"
)
_AMOUNT_RE = re.compile(
    r"(?i)(?:USD|US\$|\$)\s*~?([\d.]+)\s*([MB])\b|"
    r"(?:INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(Cr|cr|crore)?"
)
_PCT_RE = re.compile(r"(?i)([\d.]+)\s*%")
_TIME_RE = re.compile(
    r"(?i)(within\s+\d+\s+(?:months?|years?)|"
    r"over\s+\d+\s+(?:months?|years?)|"
    r"FY20\d{2}E?|"
    r"(?:monthly|quarterly|annual)|"
    r"\d+[-–]\d+\s+months?)"
)
_MONITOR_RE = re.compile(
    r"(?i)(monitor(?:ing)?|watch|early\s+warn(?:ing)?|kpi|dashboard|"
    r"monthly\s+(?:report|review)|leading\s+indicator)"
)


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("risk evidence only — no deal verdict expressed", raw)
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _info_request(need: str) -> str:
    return f"Information request: {need}"


def _is_info(val: Any) -> bool:
    s = str(val or "").strip()
    return (
        (not s)
        or s.startswith("Information")
        or s.startswith("N/A")
        or s.lower() == "n/a"
    )


def _is_filled(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return bool(s) and not s.startswith("Information") and s != _NA


def _num(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _round(n: float | None, places: int = 2) -> float | None:
    if n is None:
        return None
    return round(float(n), places)


def _insight(text: Any, *, max_chars: int = 520) -> str:
    snap = _soften_invest(_clean(text, max_chars))
    return f"**Insight Snapshot:** {snap}\n\n" if snap else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [(_soften_invest(_clean(c, 220)) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _window(text: str, start: int, *, radius: int = 180) -> str:
    return text[max(0, start - radius) : min(len(text), start + radius)]


def _usd_m_from_match(m: re.Match[str]) -> float | None:
    if m.group(1):
        val = float(m.group(1))
        unit = (m.group(2) or "M").upper()
        return val * 1000.0 if unit.startswith("B") else val
    if m.group(3):
        inr = float(m.group(3).replace(",", ""))
        # INR Cr → USD M at ~83
        if m.group(4):
            return _round(inr * 10.0 / 83.0, 1)
        return _round(inr / 83.0, 1)  # plain INR treated as units — rare
    return None


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


def gather_market_risk_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "market_competition": 0,
        "deal_strategy": 1,
        "legal_esg": 2,
        "customer": 3,
        "financial": 4,
        "operations": 5,
        "company_management": 6,
    }
    needles = (
        "risk", "market", "competition", "legal", "regulatory", "fame",
        "subsidy", "investment", "thesis", "customer", "commercial",
    )
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple[int, int, str]:
        name = str(d.get("filename") or "").lower()
        needle_hit = 0 if any(n in name for n in needles) else 1
        return (
            prefer.get(str(d.get("cdl_category") or ""), 9),
            needle_hit,
            str(d.get("filename") or ""),
        )

    ranked = sorted(docs, key=_rank)
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:12]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        loaded: dict[str, Any] = {}
        try:
            raw_loaded = load_library_document(deal, filename)
            if isinstance(raw_loaded, dict):
                loaded = raw_loaded
        except Exception:
            loaded = {}
        text = ""
        body = loaded.get("text")
        if isinstance(body, str) and body.strip():
            text = body
        elif body is not None:
            text = str(body)
        if not text.strip():
            excerpt = doc.get("excerpt")
            if isinstance(excerpt, str) and excerpt.strip():
                text = excerpt
        text = _ZWSP.sub("", text)
        text = _PDF_BULLETS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:12_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 48_000:
            break
    return "\n\n".join(blobs), sources


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------


def _seed_from_legacy(legacy: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in legacy.get("market_risk_items") or []:
        if not isinstance(item, dict) or not item.get("risk"):
            continue
        rows.append(
            {
                "risk": _clean(item.get("risk"), 80),
                "legacy_probability": item.get("probability") or "",
                "legacy_impact": item.get("impact") or "",
                "source": _DOC_CITE,
            }
        )
    return rows


def _classify_family(name: str) -> str:
    low = name.lower()
    if _SUBSIDY_RE.search(low) or "fame" in low or "subsidy" in low or "pli" in low:
        return "Regulatory / policy"
    if _OEM_RE.search(low) or "oem" in low or "competitor" in low or "share" in low:
        return "Competitor"
    if _CUSTOMER_RE.search(low) or "churn" in low or "customer" in low:
        return "Customer"
    if _CYCLE_RE.search(low) or "downturn" in low or "cycle" in low:
        return "Demand cycle"
    if _SUPPLY_EXT_RE.search(low) or "supply" in low or "battery cost" in low:
        return "External supply / input"
    if _REG_RE.search(low) or "litigation" in low or "compliance" in low:
        return "Regulatory / litigation"
    return "External market"


def _looks_internal(name: str, window: str = "") -> bool:
    blob = f"{name} {window}"
    return bool(_INTERNAL_FAMILY_RE.search(blob))


def _is_unnamed_threat(name: str) -> bool:
    raw = str(name or "").strip()
    if not raw or raw.startswith("Information"):
        return True
    return bool(_UNNAMED_RE.match(raw))


def _trigger_for(name: str, family: str, window: str) -> str:
    low = name.lower()
    win = window.lower()
    if "subsidy" in low or "fame" in low or "pli" in low:
        if "recovery" in win or "under review" in win:
            return "Subsidy claim recovery notice / policy review decision"
        return "Policy / incentive change or delay notice"
    if "oem" in low or "competitor" in low or "counter" in low:
        return "Peer pricing cut, share push, or new model launch in core geography"
    if "customer" in low or "churn" in low or "contract" in low or "concentration" in low:
        return "Contract non-renewal, churn event, or top-account loss"
    if "cycle" in low or "downturn" in low:
        return "Demand cycle trough / industry volume decline"
    if "battery" in low or "china" in low or "supply" in low:
        return "Import / input-cost spike or supply disruption"
    if "litigation" in low or "complaint" in low or "ccpa" in low:
        return "Adverse ruling, reserve step-up, or new complaint class"
    tm = _TIME_RE.search(window)
    if tm:
        return f"Timed event ({tm.group(1)}) cited in pack"
    return _info_request(f"named trigger for '{name}'")


def _population_for(name: str, family: str, window: str) -> str:
    low = name.lower()
    if "subsidy" in low or "fame" in low:
        return "Subsidy-dependent volume / ASP in the addressable mix"
    if "oem" in low or "competitor" in low:
        return "Share and mix in the company's core geography / segment"
    if "customer" in low or "concentration" in low or "contract" in low:
        pct = _PCT_RE.search(window)
        if pct:
            return f"Customer / contract population (~{pct.group(1)}% concentration cue)"
        return "Top customers / renewing contract base"
    if "cycle" in low or "downturn" in low:
        return "Cyclical volume across the served market"
    if "battery" in low or "supply" in low or "china" in low:
        return "Units / margin exposed to cell or import inputs"
    if family.startswith("Regulatory"):
        return "Geographies / SKUs under the cited rule or claim"
    return _info_request(f"population exposed for '{name}'")


def _mitigation_for(
    name: str,
    family: str,
    window: str,
    *,
    protection: str | None = None,
) -> str:
    if protection and not _is_info(protection):
        return f"Structural / deal protection: {protection}"
    low = name.lower()
    if "subsidy" in low or "fame" in low:
        return "Diversify away from incentive-dependent mix; indemnity / CP on recovery"
    if "oem" in low or "competitor" in low:
        return "Defend share via product / pricing response; underwrite case at lower share"
    if "customer" in low or "contract" in low:
        return "Renewal pipeline discipline; concentration caps; earn-out if delivery-tied"
    if "cycle" in low or "downturn" in low:
        return "Stress case at last-trough volume; working-capital / cost flexibility"
    if "supply" in low or "battery" in low or "china" in low:
        return "Dual-source / alternate geography; pass-through clauses where available"
    if family.startswith("Regulatory"):
        return "Counsel track + specific indemnity / CP for claim exposure"
    if _STRUCT_CUE.search(window):
        return "Use pack-cited escrow / earn-out / indemnity / CP"
    return _info_request(f"mitigation (or what would mitigate) for '{name}'")


def _mechanism_for(name: str, family: str, window: str) -> str:
    low = name.lower()
    if "subsidy" in low or "fame" in low:
        return (
            "Policy / subsidy support reduces or delays → volume and ASP pressure "
            "on the addressable EV mix"
        )
    if "oem" in low or "competitor" in low or "counter" in low:
        return (
            "Incumbent / peer pricing or product push erodes share and mix "
            "in the company's geography"
        )
    if "battery cost" in low:
        return "Input-cost plateau keeps unit economics from expanding as planned"
    if "capital market" in low:
        return "Funding / exit window closes → growth capital and multiple pressure"
    if "china" in low or "supply" in low:
        return "External supply disruption raises cost or constrains volume"
    if "execution" in low:
        return "Scale-up miss vs plan (treated as external only where market-driven)"
    if "customer" in low or "churn" in low or "contract" in low:
        return "Customer non-renewal or concentration loss removes recurring revenue"
    if "cycle" in low or "downturn" in low:
        return "Demand cycle trough cuts volume toward last-downturn levels"
    # Fall back to a short prose cue from the window
    cue = _clean(window, 120)
    return cue if cue else f"{family} shock transmits into revenue / margin"


def _exposure_from_context(
    *,
    name: str,
    window: str,
    revenue_usd_m: float | None,
    legacy_impact: str,
) -> dict[str, Any]:
    amt = None
    for m in _AMOUNT_RE.finditer(window):
        candidate = _usd_m_from_match(m)
        if candidate is None:
            continue
        # Reject market-size / TAM figures masquerading as company exposure.
        if revenue_usd_m is not None and candidate > max(revenue_usd_m * 1.5, 50.0):
            continue
        if candidate > 5000:
            continue
        amt = candidate
        break
    pct = None
    # Prefer a % near the risk name, not a random pack percentage.
    name_key = name.lower().split("/")[0].strip()[:24]
    local = window
    idx = window.lower().find(name_key) if name_key else -1
    if idx >= 0:
        local = window[max(0, idx - 80) : idx + 160]
    pm = _PCT_RE.search(local) or _PCT_RE.search(window)
    if pm:
        pct = float(pm.group(1))

    sized = False
    exposure = _info_request(f"revenue or margin exposed for '{name}'")
    if amt is not None:
        exposure = f"USD {amt:g}M (pack / litigation or claim size)"
        sized = True
    elif pct is not None and revenue_usd_m is not None and 0 < pct <= 100:
        exp_m = _round(revenue_usd_m * pct / 100.0, 1)
        exposure = f"~{pct:g}% of revenue ≈ USD {exp_m:g}M"
        sized = True
    elif legacy_impact and revenue_usd_m is not None:
        # Soft band from legacy High/Medium/Low impact — labelled as judgement span
        band = {
            "high": 0.25,
            "medium": 0.12,
            "low": 0.05,
        }.get(str(legacy_impact).strip().lower())
        if band:
            exposure = (
                f"Judgement band ~{band*100:.0f}% of declared revenue "
                f"(≈ USD {_round(revenue_usd_m * band, 1)}M) — not a measured exposure"
            )
    return {
        "exposure": exposure,
        "exposure_usd_m": amt if sized and amt is not None else None,
        "sized": sized,
        "size_request": (
            None
            if sized
            else _info_request(
                f"size revenue/margin exposed for '{name}' "
                f"(contract value, subsidy share, or volume × margin)"
            )
        ),
    }


def _time_horizon(window: str, family: str) -> str:
    tm = _TIME_RE.search(window)
    if tm:
        return tm.group(1)
    defaults = {
        "Regulatory / policy": "Policy timetable / next budget cycle (6–18 months)",
        "Competitor": "Share response over 2–4 quarters",
        "Customer": "At next renewal / notice period",
        "Demand cycle": "Through the next downturn cycle",
        "External supply / input": "Weeks to two quarters after disruption",
        "Regulatory / litigation": "Through current proceedings / notice period",
    }
    return defaults.get(family, _info_request("time over which the risk would act"))


def _likelihood_argument(
    *,
    name: str,
    family: str,
    window: str,
    legacy_probability: str,
) -> dict[str, Any]:
    evidence_bits: list[str] = []
    # Prefer the risk name; only use a tight window so unrelated pack text does not bleed in.
    name_l = name.lower()
    win_l = window.lower()[:280]
    low = f"{name_l} {win_l}"
    if "fame" in name_l or "subsidy" in name_l:
        if "under review" in low or "recovery" in low:
            evidence_bits.append("Policy / claim status under review or recovery notice in register")
        else:
            evidence_bits.append("Subsidy / FAME dependence cited in investment materials")
    if any(k in name_l for k in ("oem", "competitor", "counter")):
        evidence_bits.append("Competitor set named in market / competition pack")
    if any(k in name_l for k in ("ccpa", "litigation", "complaint")) or (
        family == "Regulatory / litigation"
    ):
        evidence_bits.append("Active proceeding or complaint on the legal register")
    if any(k in name_l for k in ("cycle", "downturn", "capital market")):
        evidence_bits.append("Historical cycle / downturn language in financials")
    if any(k in name_l for k in ("china", "supply", "battery")):
        evidence_bits.append("Supply-chain geography / import exposure referenced")
    if any(k in name_l for k in ("customer", "churn", "renewal", "concentration")):
        evidence_bits.append("Customer / renewal / concentration language in commercial pack")
    # Supplement from window only when name gave nothing family-relevant
    if not evidence_bits:
        if "fame" in win_l or "subsidy" in win_l:
            evidence_bits.append("Subsidy / FAME language appears near this risk in the pack")
        if "competitor" in win_l or "oem" in win_l:
            evidence_bits.append("Competitor language appears near this risk in the pack")
        if "renewal" in win_l or "customer" in win_l:
            evidence_bits.append("Customer / renewal language appears near this risk in the pack")

    if not evidence_bits:
        evidence_bits.append(
            _info_request(
                f"evidence for likelihood of '{name}' "
                f"(competitor behaviour, renewal dates, policy timetable, or cycle history)"
            )
        )

    # Do NOT invent a numeric probability — map legacy labels only as qualitative
    qualitative = None
    if legacy_probability and str(legacy_probability).strip().lower() in {
        "high", "medium", "low"
    }:
        qualitative = (
            f"Pack qualitative label '{legacy_probability}' — retained only as a "
            f"prior tag; likelihood below is argued from evidence, not from that score"
        )

    return {
        "likelihood_argument": "; ".join(evidence_bits),
        "numeric_probability": None,  # never invent
        "legacy_probability_tag": legacy_probability or None,
        "legacy_tag_note": qualitative,
        "notes": _LIKELIHOOD_RULE,
    }


def _early_warning(name: str, family: str, window: str) -> str:
    if _MONITOR_RE.search(window):
        # Prefer a concrete monthly watch
        pass
    low = name.lower()
    if "subsidy" in low or "fame" in low:
        return "Monthly: subsidy claim status / MHI–DHI notices / state incentive circulars"
    if "oem" in low or "competitor" in low:
        return "Monthly: peer pricing, share flash, and new model launches in core geography"
    if "customer" in low or "churn" in low:
        return "Monthly: renewal pipeline, churn / NRR, and top-account health"
    if "cycle" in low or "downturn" in low:
        return "Monthly: industry volume vs last-cycle trough; order book / backlog"
    if "battery" in low or "supply" in low or "china" in low:
        return "Monthly: cell/pack input prices, lead times, and alternate-source capacity"
    if "capital market" in low:
        return "Monthly: peer multiples, primary issuance window, and cash runway"
    if "ccpa" in low or "litigation" in low:
        return "Monthly: docket status, reserve movements, and complaint volume"
    return _info_request(f"monthly early-warning indicator for '{name}'")


def _price_vs_structure(name: str, window: str, family: str) -> dict[str, Any]:
    struct_hit = _STRUCT_CUE.search(window) or _STRUCT_CUE.search(name)
    if struct_hit:
        protection = _clean(struct_hit.group(0), 40)
        return {
            "classification": "Changes structure",
            "protection": protection.title() if protection else "Escrow / indemnity / CP",
            "rationale": (
                f"Evidence points to a structural protection ({protection}) "
                f"rather than a pure price chip"
            ),
            "notes": _STRUCT_RULE,
        }
    # Material regulatory / litigation / subsidy recovery → often structure
    if family in {"Regulatory / policy", "Regulatory / litigation"} and (
        "recovery" in name.lower()
        or "litigation" in name.lower()
        or "complaint" in name.lower()
        or "subsidy" in name.lower()
        or "fame" in name.lower()
        or "claim" in name.lower()
    ):
        return {
            "classification": "Changes structure",
            "protection": "Specific indemnity and/or condition precedent",
            "rationale": "Regulatory / claim exposure typically needs indemnity or CP, not only price",
            "notes": _STRUCT_RULE,
        }
    if family in {"Competitor", "Demand cycle", "Customer", "External supply / input"}:
        return {
            "classification": "Changes price",
            "protection": "Price / underwriting adjustment (or earn-out if tied to delivery)",
            "rationale": "Operating market shock — primarily a pricing / case underwriting matter",
            "notes": _STRUCT_RULE,
        }
    return {
        "classification": _info_request("price vs structure for this risk"),
        "protection": _info_request("escrow / earn-out / indemnity / CP / price chip"),
        "rationale": _STRUCT_RULE,
        "notes": _STRUCT_RULE,
    }


def _build_external_risks(
    *,
    corpus: str,
    legacy: dict[str, Any],
    revenue_usd_m: float | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text = _prose(corpus)
    seeds = _seed_from_legacy(legacy)
    seen: set[str] = {str(s.get("risk") or "").lower() for s in seeds}

    # Discover additional external risks from corpus cues
    cue_patterns = (
        (_SUBSIDY_RE, "Subsidy / incentive policy change"),
        (_OEM_RE, "Competitor share / pricing response"),
        (_CUSTOMER_RE, "Customer loss / non-renewal"),
        (_CYCLE_RE, "Demand-cycle volume downturn"),
        (_SUPPLY_EXT_RE, "External supply / input-cost shock"),
    )
    for cre, default_name in cue_patterns:
        m = cre.search(text)
        if not m:
            continue
        raw = _clean(m.group(0), 60)
        key = raw.lower()
        if any(key in s or s in key for s in seen):
            continue
        # Prefer a longer noun phrase around the match
        win = _window(text, m.start(), radius=60)
        name = default_name
        seeds.append({"risk": name, "legacy_probability": "", "legacy_impact": "", "source": _DOC_CITE})
        seen.add(name.lower())

    # Regulatory high-risk items from legacy as external
    for reg in legacy.get("regulatory_items") or []:
        if not isinstance(reg, dict):
            continue
        if str(reg.get("risk_level") or "").lower() not in {"high", "medium"}:
            continue
        area = _clean(reg.get("area"), 80)
        if not area or area.lower() in seen:
            continue
        if str(reg.get("status") or "").lower() in {"compliant", "obtained"}:
            continue
        seeds.append(
            {
                "risk": area,
                "legacy_probability": "",
                "legacy_impact": reg.get("risk_level") or "",
                "status": reg.get("status"),
                "source": _DOC_CITE,
            }
        )
        seen.add(area.lower())

    rows: list[dict[str, Any]] = []
    rejected_unnamed: list[str] = []
    handed_to_internal: list[str] = []
    for seed in seeds[:14]:
        name = str(seed.get("risk") or "")
        if _is_unnamed_threat(name):
            rejected_unnamed.append(name or "(blank)")
            continue
        # Find a context window
        idx = text.lower().find(name.lower().split("/")[0].strip()[:20])
        window = _window(text, idx, radius=200) if idx >= 0 else text[:400]
        if _looks_internal(name, window):
            handed_to_internal.append(name)
            continue
        family = _classify_family(name)
        mech = _mechanism_for(name, family, window)
        exp = _exposure_from_context(
            name=name,
            window=window,
            revenue_usd_m=revenue_usd_m,
            legacy_impact=str(seed.get("legacy_impact") or ""),
        )
        like = _likelihood_argument(
            name=name,
            family=family,
            window=window,
            legacy_probability=str(seed.get("legacy_probability") or ""),
        )
        warn = _early_warning(name, family, window)
        pvs = _price_vs_structure(name, window, family)
        timing = _time_horizon(window, family)
        trigger = _trigger_for(name, family, window)
        population = _population_for(name, family, window)
        mitigation = _mitigation_for(
            name, family, window, protection=str(pvs.get("protection") or "")
        )
        rows.append(
            {
                "risk": name,
                "family": family,
                "trigger": trigger,
                "population": population,
                "timing": timing,
                "mechanism": mech,
                "mitigation": mitigation,
                "exposure": exp["exposure"],
                "exposure_usd_m": exp.get("exposure_usd_m"),
                "sized": exp["sized"],
                "size_request": exp.get("size_request"),
                "time_horizon": timing,
                "likelihood_argument": like["likelihood_argument"],
                "numeric_probability": None,
                "legacy_probability_tag": like.get("legacy_probability_tag"),
                "early_warning": warn,
                "price_vs_structure": pvs["classification"],
                "suggested_protection": pvs["protection"],
                "structure_rationale": pvs["rationale"],
                "source": seed.get("source") or _DOC_CITE,
                "notes": _ROW_RULE,
            }
        )
        if len(rows) >= 12:
            break
    if not rows:
        rows.append(
            {
                "risk": _info_request("external risk for this business / geography"),
                "family": "External market",
                "trigger": _info_request("named trigger"),
                "population": _info_request("population exposed"),
                "timing": _info_request("timing"),
                "mechanism": _info_request("mechanism"),
                "mitigation": _info_request("mitigation"),
                "exposure": _info_request("revenue or margin exposed"),
                "sized": False,
                "size_request": _info_request("what would size this risk"),
                "time_horizon": _info_request("time horizon"),
                "likelihood_argument": _info_request("evidence for likelihood"),
                "numeric_probability": None,
                "early_warning": _info_request("monthly early-warning indicator"),
                "price_vs_structure": _info_request("price vs structure"),
                "suggested_protection": _NA,
                "source": _NA,
                "notes": _ROW_RULE,
            }
        )
    meta = {
        "rejected_unnamed": rejected_unnamed[:8],
        "handed_to_internal": handed_to_internal[:8],
        "notes": _UNNAMED_RULE,
    }
    return rows, meta


def _build_downsides(
    *,
    risks: list[dict[str, Any]],
    corpus: str,
    revenue_usd_m: float | None,
    historical: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []

    # Largest litigation / recovery as bounded claim downside
    for lit in re.finditer(
        r"(?i)([A-Z][^.]{8,60}?)\s+(?:Consumer Protection|Regulatory|Contract Law|"
        r"IP Litigation|Income Tax Act)\s+INR\s*([\d,]+)\s*Crore",
        text,
    ):
        inr = float(lit.group(2).replace(",", ""))
        usd = _round(inr * 10.0 / 83.0, 1)
        rows.append(
            {
                "scenario": f"Adverse outcome — { _clean(lit.group(1), 50) }",
                "bound": f"Claim / exposure INR {inr:g} Cr (≈ USD {usd}M)",
                "ebitda_impact": (
                    f"Cash / P&L hit up to ≈ USD {usd}M if fully adverse "
                    f"(not an EBITDA run-rate unless reserved)"
                ),
                "bounded": True,
                "source": _DOC_CITE,
                "notes": _DOWNSIDE_RULE,
            }
        )
        if len(rows) >= 3:
            break

    # Volume-to-last-downturn proxy from historical revenue trough — only when
    # the trough year is *after* the peak (actual give-back), not growth min/max.
    if isinstance(historical, dict) and revenue_usd_m is not None:
        for line in historical.get("pl_lines") or []:
            if not isinstance(line, dict):
                continue
            if "revenue" not in str(line.get("line_item") or "").lower():
                continue
            dated: list[tuple[int, float]] = []
            for key, year in (
                ("fy2021_value", 2021),
                ("fy2022_value", 2022),
                ("fy2023_value", 2023),
                ("fy2024_value", 2024),
                ("fy2025_value", 2025),
            ):
                v = _num(line.get(key))
                if isinstance(v, (int, float)) and v > 0:
                    dated.append((year, float(v)))
            if len(dated) < 2:
                break
            peak_year, peak = max(dated, key=lambda x: x[1])
            trough_year, trough = min(dated, key=lambda x: x[1])
            # Growth series (trough earlier than peak) is not a give-back scenario
            if trough_year <= peak_year or peak <= 0 or trough >= peak:
                break
            drop_pct = (peak - trough) / peak
            lost = _round(revenue_usd_m * drop_pct, 1)
            rows.append(
                {
                    "scenario": "Volume falls to last-cycle trough vs recent peak",
                    "bound": (
                        f"Accounts FY{peak_year}→FY{trough_year} trough/peak implies "
                        f"~{drop_pct*100:.0f}% volume give-back"
                    ),
                    "ebitda_impact": (
                        f"Revenue give-back ≈ USD {lost}M on declared basis; "
                        f"EBITDA impact = give-back × marginal contribution "
                        f"(margin still required)"
                    ),
                    "bounded": True,
                    "source": _COMPUTED,
                    "notes": _DOWNSIDE_RULE,
                }
            )
            break

    # Largest sized risk exposure
    sized = [
        r for r in risks
        if isinstance(r, dict) and r.get("sized") and isinstance(r.get("exposure_usd_m"), (int, float))
    ]
    if sized:
        top = max(sized, key=lambda r: float(r["exposure_usd_m"]))
        rows.append(
            {
                "scenario": f"Full adverse realisation — {top.get('risk')}",
                "bound": f"Exposed amount USD {top['exposure_usd_m']:g}M",
                "ebitda_impact": (
                    f"Up to USD {top['exposure_usd_m']:g}M revenue/claim hit; "
                    f"translate to EBITDA with evidenced contribution margin"
                ),
                "bounded": True,
                "source": top.get("source") or _DOC_CITE,
                "notes": _DOWNSIDE_RULE,
            }
        )

    if not rows:
        rows.append(
            {
                "scenario": _info_request("bounded downside scenario"),
                "bound": _info_request("largest contract value or last-downturn volume"),
                "ebitda_impact": _info_request("EBITDA impact when exposure is bounded"),
                "bounded": False,
                "source": _NA,
                "notes": _DOWNSIDE_RULE,
            }
        )
    return rows[:6]


def _unsized_register(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for r in risks:
        if not isinstance(r, dict) or r.get("sized"):
            continue
        rows.append(
            {
                "risk": r.get("risk"),
                "why_unsized": "Revenue/margin exposure not measured in dollars from the pack",
                "what_would_size": r.get("size_request")
                or _info_request(f"size exposure for '{r.get('risk')}'"),
                "source": r.get("source") or _NA,
                "notes": _UNSIZED_RULE,
            }
        )
    if not rows:
        rows.append(
            {
                "risk": "—",
                "why_unsized": "All listed material risks have at least a partial size cue",
                "what_would_size": "—",
                "source": _COMPUTED,
                "notes": _UNSIZED_RULE,
            }
        )
    return rows


def _legacy_dual_write(
    *,
    risks: list[dict[str, Any]],
    legacy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], list[str]]:
    items = []
    for r in risks:
        if not isinstance(r, dict) or not r.get("risk"):
            continue
        if str(r.get("risk") or "").startswith("Information"):
            continue
        # Preserve qualitative tags only — no invented numeric probabilities
        items.append(
            {
                "risk": r.get("risk"),
                "probability": r.get("legacy_probability_tag") or "",
                "impact": "",
                "likelihood_argument": r.get("likelihood_argument"),
                "exposure": r.get("exposure"),
            }
        )
    if not items and isinstance(legacy.get("market_risk_items"), list):
        items = [i for i in legacy["market_risk_items"] if isinstance(i, dict)]

    regulatory = [
        i for i in (legacy.get("regulatory_items") or []) if isinstance(i, dict)
    ]
    litigation = [
        x for x in (legacy.get("litigation_exposures") or []) if isinstance(x, str)
    ]
    flags = []
    for r in risks:
        if not isinstance(r, dict):
            continue
        if r.get("price_vs_structure") == "Changes structure":
            flags.append(f"Structure protection: {r.get('risk')} → {r.get('suggested_protection')}")
        if r.get("sized"):
            flags.append(f"Sized exposure: {r.get('risk')} — {r.get('exposure')}")
    for f in legacy.get("risk_flags") or []:
        if isinstance(f, str) and f not in flags:
            flags.append(f)
    notes = [str(r.get("early_warning")) for r in risks[:4] if isinstance(r, dict)]
    for n in legacy.get("risk_notes") or []:
        if isinstance(n, str) and n not in notes:
            notes.append(n)
    return items[:12], regulatory[:16], litigation[:12], flags[:8], notes[:8]


def _mr_internal_risk_cross_check(
    *,
    risks: list[dict[str, Any]],
    build_meta: dict[str, Any],
    internal_risk_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    present = isinstance(internal_risk_spec, dict) and bool(internal_risk_spec)
    overlap: list[str] = []
    conflicts: list[str] = []
    aligned: list[str] = []
    handed = list(build_meta.get("handed_to_internal") or [])

    internal_like = [
        r for r in risks
        if isinstance(r, dict)
        and not _is_info(r.get("risk"))
        and _looks_internal(
            str(r.get("risk") or ""),
            f"{r.get('mechanism')} {r.get('trigger')}",
        )
    ]
    for r in internal_like:
        conflicts.append(
            f"Market Risk row '{_clean(r.get('risk'), 60)}' looks internal — "
            f"move to Internal Risk"
        )

    if handed:
        aligned.append(
            f"Handed {len(handed)} internal-looking item(s) off Market Risk: "
            + "; ".join(_clean(h, 40) for h in handed[:4])
        )

    if present:
        ir_names: list[str] = []
        for key in (
            "key_person_exposure",
            "financial_strain",
            "control_governance",
            "ranked_effects",
            "internal_risks",
        ):
            for row in internal_risk_spec.get(key) or []:
                if not isinstance(row, dict):
                    continue
                label = (
                    row.get("person")
                    or row.get("issue")
                    or row.get("weakness")
                    or row.get("risk")
                    or row.get("control")
                )
                if label:
                    ir_names.append(str(label))
        for r in risks:
            if not isinstance(r, dict) or _is_info(r.get("risk")):
                continue
            name = str(r.get("risk") or "")
            hit = next(
                (
                    ir for ir in ir_names
                    if name.lower()[:18] in ir.lower() or ir.lower()[:18] in name.lower()
                ),
                None,
            )
            if hit:
                overlap.append(f"{_clean(name, 50)} ↔ Internal '{_clean(hit, 50)}'")
        if overlap:
            conflicts.append(
                f"{len(overlap)} Market Risk row(s) duplicate Internal Risk topics"
            )
        elif not conflicts:
            aligned.append("Internal Risk prior present; no duplicate restatement detected")
    else:
        if not conflicts and not handed:
            conflicts.append("Internal Risk prior not available for cross-check")
        elif not conflicts:
            aligned.append("Internal-looking items filtered; Internal prior absent")

    return {
        "internal_prior_present": present,
        "overlap": overlap[:6],
        "aligned": aligned,
        "conflicts": conflicts,
        "handed_to_internal": handed[:8],
        "notes": _INTERNAL_CROSS_RULE,
    }


def _mr_evidence_qa(
    *,
    risks: list[dict[str, Any]],
    downsides: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    price_struct: list[dict[str, Any]],
    build_meta: dict[str, Any],
    ir_cross: dict[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    real = [
        r for r in risks
        if isinstance(r, dict)
        and r.get("risk")
        and not _is_info(r.get("risk"))
    ]

    schema_ok = all(
        not _is_info(r.get("trigger"))
        and not _is_info(r.get("population"))
        and not _is_info(r.get("timing") or r.get("time_horizon"))
        and not _is_info(r.get("mechanism"))
        and not _is_info(r.get("mitigation"))
        for r in real
    ) if real else False
    rows.append({
        "check": "risk_row_schema",
        "status": "PASS" if real and schema_ok else "FAIL",
        "finding": (
            f"{len(real)} risk row(s) with trigger/population/timing/mechanism/mitigation"
            if real and schema_ok
            else _info_request(
                "external risk rows with trigger, population, timing, mechanism, mitigation"
            )
        ),
        "action": _ROW_RULE,
    })

    sized_n = sum(1 for r in real if r.get("sized"))
    downside_n = sum(1 for d in downsides if isinstance(d, dict) and d.get("bounded"))
    unsized_ok = all(
        r.get("sized") or not _is_info(r.get("size_request"))
        for r in real
    ) if real else False
    exposure_ok = real and (sized_n >= 1 or downside_n >= 1 or unsized_ok)
    rows.append({
        "check": "dollar_exposure",
        "status": "PASS" if exposure_ok else "FAIL",
        "finding": (
            f"{sized_n} sized · {downside_n} bounded downside; unsized carry sizing asks"
            if exposure_ok
            else _info_request("dollar exposure or what would size each risk")
        ),
        "action": _DOWNSIDE_RULE,
    })

    argued = sum(
        1 for r in real
        if not _is_info(r.get("likelihood_argument"))
    )
    numeric_abuse = sum(1 for r in real if r.get("numeric_probability") is not None)
    # Affirmative invented % only — strip advisory "do not assign…" sentences
    like_blob = " ".join(str(r.get("likelihood_argument") or "") for r in real)
    scrubbed = re.sub(
        r"(?i)[^.!?\n]*(?:"
        r"do\s+not\s+assign|"
        r"not\s+assigned|"
        r"without\s+a\s+basis|"
        r"no\s+evidenced\s+basis"
        r")[^.!?\n]*[.!?]?",
        " ",
        like_blob,
    )
    invent_pct = bool(re.search(r"(?i)\bprobability\s*[:=]\s*\d+\s*%", scrubbed))
    like_ok = (
        real
        and argued >= max(1, len(real) // 2)
        and numeric_abuse == 0
        and not invent_pct
    )
    rows.append({
        "check": "evidence_based_likelihood",
        "status": "PASS" if like_ok else "FAIL",
        "finding": (
            f"{argued}/{len(real)} likelihood argument(s); no invented numeric probability"
            if like_ok
            else (
                "Invented numeric probability — remove"
                if invent_pct or numeric_abuse
                else _info_request("evidence-based likelihood (no invented probabilities)")
            )
        ),
        "action": _LIKELIHOOD_RULE,
    })

    warn_real = [
        w for w in warnings
        if isinstance(w, dict)
        and not _is_info(w.get("risk"))
        and not _is_info(w.get("early_warning"))
    ]
    rows.append({
        "check": "early_warning_indicators",
        "status": "PASS" if warn_real else "FAIL",
        "finding": (
            f"{len(warn_real)} early-warning indicator(s)"
            if warn_real
            else _info_request("monthly early-warning indicators")
        ),
        "action": _WARN_RULE,
    })

    pvs_real = [
        p for p in price_struct
        if isinstance(p, dict)
        and not _is_info(p.get("risk"))
        and (
            "price" in str(p.get("classification") or "").lower()
            or "structure" in str(p.get("classification") or "").lower()
        )
    ]
    rows.append({
        "check": "price_vs_structure",
        "status": "PASS" if pvs_real else "FAIL",
        "finding": (
            f"{len(pvs_real)} price/structure classification(s)"
            if pvs_real
            else _info_request("price vs structure classification")
        ),
        "action": _STRUCT_RULE,
    })

    hard_ir = any(
        "looks internal" in str(c).lower() or "duplicate" in str(c).lower()
        for c in (ir_cross.get("conflicts") or [])
    )
    ir_ok = (not hard_ir) and (
        bool(ir_cross.get("internal_prior_present"))
        or bool(ir_cross.get("handed_to_internal"))
        or any("no duplicate" in str(a).lower() for a in (ir_cross.get("aligned") or []))
    )
    # Soft: prior missing alone is FAIL only when no handoff evidence
    prior_missing = any(
        "not available" in str(c).lower() for c in (ir_cross.get("conflicts") or [])
    )
    if prior_missing and not hard_ir and not ir_cross.get("handed_to_internal"):
        ir_ok = False
    elif prior_missing and not hard_ir:
        ir_ok = True
    rows.append({
        "check": "non_overlap_internal_risk",
        "status": "PASS" if ir_ok else "FAIL",
        "finding": (
            "; ".join(ir_cross.get("aligned") or [])
            or "Internal Risk boundary respected"
            if ir_ok
            else (
                "; ".join(ir_cross.get("conflicts") or [])
                or _info_request("Internal Risk prior for non-overlap cross-check")
            )
        ),
        "action": _INTERNAL_CROSS_RULE,
    })

    rejected = list(build_meta.get("rejected_unnamed") or [])
    unnamed_in_rows = [
        r for r in risks
        if isinstance(r, dict)
        and not _is_info(r.get("risk"))
        and _is_unnamed_threat(str(r.get("risk") or ""))
    ]
    unnamed_ok = not unnamed_in_rows
    rows.append({
        "check": "reject_unnamed_threats",
        "status": "PASS" if unnamed_ok else "FAIL",
        "finding": (
            (
                f"Unnamed threats rejected ({len(rejected)})"
                if rejected
                else "No unnamed / generic threats in register"
            )
            if unnamed_ok
            else f"Unnamed threats still present: "
            + "; ".join(_clean(r.get("risk"), 40) for r in unnamed_in_rows[:4])
        ),
        "action": _UNNAMED_RULE,
    })
    return rows


def _questions_from_mr_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("mr_evidence_qa")
        if isinstance(spec.get("mr_evidence_qa"), list) else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("risk_row_schema"):
        out.append(normalize_question({
            "question": (
                "Complete external risk rows with trigger, population, timing, "
                "mechanism and mitigation"
            ),
            "required_records": "Market / legal / commercial packs with named external risks",
            "decision_effect": "Incomplete rows leave exposure and timing unusable for IC",
            "priority": "mandatory_pre_decision",
            "owner": "Market diligence lead",
            "timing": "before IC",
            "closure_test": "risk_row_schema QA PASS",
            "interim_treatment": "LIMITED — do not underwrite unnamed / incomplete risks",
        }))
    if _qa_fail("dollar_exposure"):
        out.append(normalize_question({
            "question": "Size dollar revenue/margin exposure (or state what would size it)",
            "required_records": "Contract values, subsidy share, volume × margin bridges",
            "decision_effect": "Unsized external risks cannot set price or structure",
            "priority": "signing_condition",
            "owner": "Market diligence lead",
            "timing": "per deal timetable",
            "closure_test": "dollar_exposure QA PASS",
            "interim_treatment": "LIMITED — keep unsized risks on the open register",
        }))
    if _qa_fail("evidence_based_likelihood"):
        out.append(normalize_question({
            "question": "Argue likelihood from evidence; remove invented numeric probabilities",
            "required_records": "Renewal dates, policy timetables, competitor behaviour, cycle history",
            "decision_effect": "Arbitrary probabilities mis-rank diligence priority",
            "priority": "mandatory_pre_decision",
            "owner": "Market diligence lead",
            "timing": "before IC",
            "closure_test": "evidence_based_likelihood QA PASS",
            "interim_treatment": "LIMITED — treat likelihood as open",
        }))
    if _qa_fail("early_warning_indicators"):
        out.append(normalize_question({
            "question": "State monthly early-warning indicators for each material external risk",
            "required_records": "KPI / monitoring plan post-completion",
            "decision_effect": "No watch list leaves buyer blind after close",
            "priority": "post_close_action",
            "owner": "Portfolio ops",
            "timing": "at signing / first 100 days",
            "closure_test": "early_warning_indicators QA PASS",
            "interim_treatment": "LIMITED — flag monitoring gap",
        }))
    if _qa_fail("price_vs_structure"):
        out.append(normalize_question({
            "question": "Classify each material risk as price vs structure with protection",
            "required_records": "SPA term sheet cues (escrow, earn-out, indemnity, CP)",
            "decision_effect": "Misclassified risks leave wrong protection on the table",
            "priority": "signing_condition",
            "owner": "Deal counsel + market lead",
            "timing": "before SPA",
            "closure_test": "price_vs_structure QA PASS",
            "interim_treatment": "LIMITED — do not assume price chip alone",
        }))
    if _qa_fail("non_overlap_internal_risk"):
        out.append(normalize_question({
            "question": "Reconcile Market Risk with Internal Risk — remove internal duplicates",
            "required_records": "Internal Risk register (key-person, controls, cash/covenant)",
            "decision_effect": "Double-counting blurs external vs inherited operating risk",
            "priority": "mandatory_pre_decision",
            "owner": "Market + ops diligence leads",
            "timing": "before IC",
            "closure_test": "non_overlap_internal_risk QA PASS",
            "interim_treatment": "LIMITED until Internal Risk cross-check complete",
        }))
    if _qa_fail("reject_unnamed_threats"):
        out.append(normalize_question({
            "question": "Replace unnamed / generic threats with named trigger and population",
            "required_records": "Named competitor, customer, policy, or cycle events",
            "decision_effect": "Generic headwinds are not diligence findings",
            "priority": "mandatory_pre_decision",
            "owner": "Market diligence lead",
            "timing": "before IC",
            "closure_test": "reject_unnamed_threats QA PASS",
            "interim_treatment": "LIMITED — strip generic threats from the register",
        }))
    return out


def _quality_reliance(
    *,
    risks: list[dict[str, Any]],
    downsides: list[dict[str, Any]],
    qa_fail: bool = False,
) -> tuple[str, str, str]:
    real = [
        r for r in risks
        if isinstance(r, dict)
        and r.get("risk")
        and not str(r.get("risk")).startswith("Information")
    ]
    argued = sum(
        1 for r in real
        if _is_filled(r.get("likelihood_argument"))
        and "information request" not in str(r.get("likelihood_argument") or "").lower()
    )
    sized_n = sum(1 for r in real if r.get("sized"))
    warn_n = sum(
        1 for r in real
        if _is_filled(r.get("early_warning"))
        and "information request" not in str(r.get("early_warning") or "").lower()
    )
    downside_n = sum(1 for d in downsides if isinstance(d, dict) and d.get("bounded"))
    # No numeric probabilities invented
    numeric_abuse = sum(1 for r in real if r.get("numeric_probability") is not None)
    schema_n = sum(
        1 for r in real
        if not _is_info(r.get("trigger"))
        and not _is_info(r.get("population"))
        and not _is_info(r.get("mechanism"))
        and not _is_info(r.get("mitigation"))
    )

    if (
        real
        and argued >= max(1, len(real) // 2)
        and warn_n >= 1
        and numeric_abuse == 0
        and schema_n >= max(1, len(real) // 2)
    ):
        quality = "PASS"
    else:
        quality = "REWORK"

    if real and (sized_n >= 1 or downside_n >= 1) and argued >= 1:
        reliance = "READY"
    elif real:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    if qa_fail and reliance == "READY":
        reliance = "LIMITED"

    bits = [
        f"Quality {quality}: {len(real)} external risk(s); "
        f"{argued} with evidence-based likelihood; {sized_n} sized; "
        f"{schema_n} with full row schema.",
        f"Reliance {reliance}.",
        _LIKELIHOOD_RULE,
        _ROW_RULE,
    ]
    if qa_fail:
        bits.append("Open Market Risk QA FAILs cap READY → LIMITED")
    if numeric_abuse:
        bits.append("Numeric probabilities found without basis — remove.")
    if sized_n == 0:
        bits.append("No dollar exposure sized yet — unsized risks still listed with sizing asks.")
    return quality, reliance, " ".join(bits)


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _declared_revenue_usd_m(
    valuation: dict[str, Any] | None,
    historical: dict[str, Any] | None,
    corpus: str,
) -> float | None:
    if isinstance(valuation, dict):
        earn = valuation.get("earnings_basis") if isinstance(valuation.get("earnings_basis"), dict) else {}
        amt = _num(earn.get("amount"))
        unit = str(earn.get("unit") or "").upper()
        if amt is not None:
            if "INR" in unit and "CR" in unit:
                return _round(amt * 10.0 / 83.0, 1)
            return float(amt)
    text = _prose(corpus)
    m = re.search(r"(?i)(?:Revenue|Sales)\s+(?:USD|US\$|\$)\s*~?([\d.]+)\s*([MB])\b", text)
    if m:
        val = float(m.group(1))
        return val * 1000.0 if m.group(2).upper().startswith("B") else val
    if isinstance(historical, dict):
        for line in historical.get("pl_lines") or []:
            if isinstance(line, dict) and "revenue" in str(line.get("line_item") or "").lower():
                v = _num(line.get("fy2024_value"))
                if v is not None:
                    return _round(v * 10.0 / 83.0, 1)
    return None


def _heuristic_market_risk_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    legacy_spec: dict[str, Any] | None = None,
    valuation_spec: dict[str, Any] | None = None,
    historical_performance: dict[str, Any] | None = None,
    internal_risk_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    revenue = _declared_revenue_usd_m(valuation_spec, historical_performance, corpus)
    risks, build_meta = _build_external_risks(
        corpus=corpus, legacy=legacy, revenue_usd_m=revenue
    )
    downsides = _build_downsides(
        risks=risks,
        corpus=corpus,
        revenue_usd_m=revenue,
        historical=historical_performance,
    )
    unsized = _unsized_register(risks)
    price_struct = [
        {
            "risk": r.get("risk"),
            "classification": r.get("price_vs_structure"),
            "protection": r.get("suggested_protection"),
            "rationale": r.get("structure_rationale"),
            "source": r.get("source"),
            "notes": _STRUCT_RULE,
        }
        for r in risks
        if isinstance(r, dict) and not str(r.get("risk") or "").startswith("Information")
    ]
    warnings = [
        {
            "risk": r.get("risk"),
            "early_warning": r.get("early_warning"),
            "source": r.get("source"),
            "notes": _WARN_RULE,
        }
        for r in risks
        if isinstance(r, dict) and not str(r.get("risk") or "").startswith("Information")
    ]
    items, regulatory, litigation, flags, notes = _legacy_dual_write(risks=risks, legacy=legacy)
    ir_cross = _mr_internal_risk_cross_check(
        risks=risks,
        build_meta=build_meta,
        internal_risk_spec=internal_risk_spec,
    )
    mr_qa = _mr_evidence_qa(
        risks=risks,
        downsides=downsides,
        warnings=warnings,
        price_struct=price_struct,
        build_meta=build_meta,
        ir_cross=ir_cross,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in mr_qa)
    quality, reliance, rationale = _quality_reliance(
        risks=risks, downsides=downsides, qa_fail=qa_fail
    )

    real_n = sum(
        1 for r in risks
        if isinstance(r, dict) and not _is_info(r.get("risk"))
    )
    bits = [f"Market Risk for {company}", f"{real_n} external risk(s)"]
    sized_n = sum(1 for r in risks if r.get("sized"))
    if sized_n:
        bits.append(f"{sized_n} sized")
    struct_n = sum(1 for p in price_struct if "structure" in str(p.get("classification") or "").lower())
    if struct_n:
        bits.append(f"{struct_n} structure protection(s)")
    bits.append(
        f"Internal prior={'yes' if ir_cross.get('internal_prior_present') else 'no'}"
    )

    out = {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "external_risks": risks,
        "downside_cases": downsides,
        "early_warnings": warnings,
        "price_vs_structure": price_struct,
        "unsized_risks": unsized,
        "internal_risk_cross_check": ir_cross,
        "rejected_unnamed": list(build_meta.get("rejected_unnamed") or []),
        "mr_evidence_qa": mr_qa,
        # Legacy dual-write
        "market_risk_items": items,
        "regulatory_items": regulatory,
        "litigation_exposures": litigation,
        "risk_flags": flags,
        "risk_notes": notes,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "slug": _AGENT_KEY,
        "track": legacy.get("track") or "E",
        "empty": real_n == 0,
        "declared_revenue_usd_m": revenue,
    }
    out["questions"] = _questions_from_mr_gaps(out)
    return out


def _llm_market_risk_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "market_risk",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
        src_lines = "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:16], start=1)) or "[1] VDR"
        user = (
            f"Company: {company}\n\nSources:\n{src_lines}\n\n"
            f"Corpus:\n{corpus[:32000]}\n\n"
            "Return JSON with keys:\n"
            "insight_snapshot,\n"
            "external_risks: [{risk, family, trigger, population, timing, mechanism, "
            "mitigation, exposure, time_horizon, likelihood_argument, early_warning, "
            "price_vs_structure, suggested_protection, sized (bool), size_request, source}],\n"
            "downside_cases: [{scenario, bound, ebitda_impact, bounded, source}],\n"
            "early_warnings: [{risk, early_warning, source}],\n"
            "price_vs_structure: [{risk, classification, protection, rationale, source}],\n"
            "unsized_risks: [{risk, why_unsized, what_would_size, source}],\n"
            "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
            "Reject unnamed/generic threats. Do not restate Internal Risk items. "
            "Do NOT invent numeric probabilities. No invest or pass."
        )
        return generate_json(system=system, user=user, temperature=0.15)
    except Exception:
        return None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    heur: dict[str, Any],
    internal_risk_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(heur)
    for key in (
        "insight_snapshot",
        "external_risks",
        "downside_cases",
        "early_warnings",
        "price_vs_structure",
        "unsized_risks",
        "quality_verdict",
        "reliance_verdict",
        "quality_reliance_rationale",
    ):
        if key in llm and llm[key]:
            out[key] = llm[key]
    # Strip invented numeric probabilities; fill schema aliases; drop unnamed
    cleaned: list[dict[str, Any]] = []
    rejected = list(out.get("rejected_unnamed") or [])
    for r in out.get("external_risks") or []:
        if not isinstance(r, dict):
            continue
        r["numeric_probability"] = None
        name = str(r.get("risk") or "")
        if _is_unnamed_threat(name):
            rejected.append(name or "(blank)")
            continue
        if not r.get("timing") and r.get("time_horizon"):
            r["timing"] = r.get("time_horizon")
        if not r.get("time_horizon") and r.get("timing"):
            r["time_horizon"] = r.get("timing")
        cleaned.append(r)
    out["external_risks"] = cleaned
    out["rejected_unnamed"] = rejected[:8]
    build_meta = {
        "rejected_unnamed": rejected,
        "handed_to_internal": list(
            (out.get("internal_risk_cross_check") or {}).get("handed_to_internal") or []
        ),
    }
    ir_cross = _mr_internal_risk_cross_check(
        risks=cleaned,
        build_meta=build_meta,
        internal_risk_spec=internal_risk_spec,
    )
    out["internal_risk_cross_check"] = ir_cross
    warnings = out.get("early_warnings") if isinstance(out.get("early_warnings"), list) else []
    price_struct = (
        out.get("price_vs_structure")
        if isinstance(out.get("price_vs_structure"), list) else []
    )
    downsides = (
        out.get("downside_cases") if isinstance(out.get("downside_cases"), list) else []
    )
    mr_qa = _mr_evidence_qa(
        risks=cleaned,
        downsides=downsides,
        warnings=warnings,
        price_struct=price_struct,
        build_meta=build_meta,
        ir_cross=ir_cross,
    )
    out["mr_evidence_qa"] = mr_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in mr_qa)
    qv = out.get("quality_verdict")
    rv = out.get("reliance_verdict")
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        qv, rv, rationale = _quality_reliance(
            risks=cleaned, downsides=downsides, qa_fail=qa_fail
        )
        out["quality_verdict"] = qv
        out["reliance_verdict"] = rv
        out["quality_reliance_rationale"] = rationale
    else:
        if qa_fail and rv == "READY":
            out["reliance_verdict"] = "LIMITED"
            out["quality_reliance_rationale"] = (
                str(out.get("quality_reliance_rationale") or "")
                + " Open Market Risk QA FAILs cap READY → LIMITED."
            ).strip()
    llm_questions = llm.get("questions") if isinstance(llm.get("questions"), list) else None
    if llm_questions:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q = []
        for raw_q in llm_questions:
            q = normalize_question(raw_q)
            if q:
                filled_q.append(q)
        out["questions"] = filled_q or _questions_from_mr_gaps(out)
    else:
        out["questions"] = _questions_from_mr_gaps(out)
    out["composer"] = "llm_v1"
    return out


def build_market_risk_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    internal_risk_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    def _load(agent_key: str) -> dict[str, Any] | None:
        try:
            disk = read_agent_output_file(deal, agent_key=agent_key) or {}
            spec = disk.get("spec")
            return spec if isinstance(spec, dict) else None
        except Exception:
            return None

    valuation = _load("valuation_modeling")
    historical = _load("historical_performance")
    ir_spec = internal_risk_spec if isinstance(internal_risk_spec, dict) else _load("internal_risk")

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_market_risk_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources

    # Seed corpus with legacy risk names so heuristic has anchors
    seed_bits = []
    for item in legacy.get("market_risk_items") or []:
        if isinstance(item, dict) and item.get("risk"):
            seed_bits.append(
                f"{item['risk']} — probability {item.get('probability')} "
                f"impact {item.get('impact')}"
            )
    for reg in legacy.get("regulatory_items") or []:
        if isinstance(reg, dict) and reg.get("area"):
            seed_bits.append(
                f"{reg['area']} — {reg.get('status')} ({reg.get('risk_level')})"
            )
    for lit in (legacy.get("litigation_exposures") or [])[:6]:
        if isinstance(lit, str):
            seed_bits.append(lit)
    full_corpus = "\n\n".join(x for x in (corpus or "", "\n".join(seed_bits)) if x.strip())

    heur = _heuristic_market_risk_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        legacy_spec=legacy,
        valuation_spec=valuation,
        historical_performance=historical,
        internal_risk_spec=ir_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    llm_raw = _llm_market_risk_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
    )
    if not llm_raw:
        return heur
    out = _normalise_llm_spec(llm_raw, heur=heur, internal_risk_spec=ir_spec)
    out["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return out


def render_market_risk_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    risks = spec.get("external_risks") if isinstance(spec.get("external_risks"), list) else []
    downsides = spec.get("downside_cases") if isinstance(spec.get("downside_cases"), list) else []
    warnings = spec.get("early_warnings") if isinstance(spec.get("early_warnings"), list) else []
    pvs = spec.get("price_vs_structure") if isinstance(spec.get("price_vs_structure"), list) else []
    unsized = spec.get("unsized_risks") if isinstance(spec.get("unsized_risks"), list) else []
    regulatory = spec.get("regulatory_items") if isinstance(spec.get("regulatory_items"), list) else []
    litigation = (
        spec.get("litigation_exposures")
        if isinstance(spec.get("litigation_exposures"), list)
        else []
    )
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_ROW_RULE}\n\n")
    parts.append(f"{_LIKELIHOOD_RULE}\n\n")
    parts.append(f"{_UNNAMED_RULE}\n\n")

    # 1
    parts.append("## 1. External Risks (trigger · population · timing · mechanism · mitigation)\n\n")
    parts.append(f"{_IDENTIFY_RULE}\n\n")
    parts.append(f"{_ROW_RULE}\n\n")
    if risks:
        parts.append(_table(
            [
                "Risk", "Family", "Trigger", "Population", "Timing",
                "Mechanism", "Mitigation", "Exposure", "Source",
            ],
            [
                [
                    _clean(r.get("risk"), 36),
                    _clean(r.get("family"), 20),
                    _clean(r.get("trigger"), 50),
                    _clean(r.get("population"), 50),
                    _clean(r.get("timing") or r.get("time_horizon"), 36),
                    _clean(r.get("mechanism"), 60),
                    _clean(r.get("mitigation"), 50),
                    _clean(r.get("exposure"), 50),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in risks if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('external risks for this business / geography')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Likelihood from Evidence\n\n")
    parts.append(f"{_LIKELIHOOD_RULE}\n\n")
    parts.append(_table(
        ["Risk", "Likelihood argument (evidence)", "Numeric probability"],
        [
            [
                _clean(r.get("risk"), 40),
                _clean(r.get("likelihood_argument"), 140),
                "Not assigned — no evidenced basis"
                if r.get("numeric_probability") is None
                else str(r.get("numeric_probability")),
            ]
            for r in risks if isinstance(r, dict)
        ],
    ))
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Quantified Downside (where bounded)\n\n")
    parts.append(f"{_DOWNSIDE_RULE}\n\n")
    if downsides:
        parts.append(_table(
            ["Scenario", "Bound", "EBITDA / P&L impact", "Bounded?", "Source"],
            [
                [
                    _clean(d.get("scenario"), 50),
                    _clean(d.get("bound"), 80),
                    _clean(d.get("ebitda_impact"), 100),
                    "Yes" if d.get("bounded") else "No",
                    _clean(d.get("source") or _NA, 40),
                ]
                for d in downsides if isinstance(d, dict)
            ],
        ))
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Early-Warning Indicators\n\n")
    parts.append(f"{_WARN_RULE}\n\n")
    if warnings:
        parts.append(_table(
            ["Risk", "Monthly watch (post-completion)", "Source"],
            [
                [
                    _clean(w.get("risk"), 40),
                    _clean(w.get("early_warning"), 120),
                    _clean(w.get("source") or _NA, 40),
                ]
                for w in warnings if isinstance(w, dict)
            ],
        ))
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Price vs Structure\n\n")
    parts.append(f"{_STRUCT_RULE}\n\n")
    if pvs:
        parts.append(_table(
            ["Risk", "Classification", "Protection", "Rationale"],
            [
                [
                    _clean(p.get("risk"), 40),
                    _clean(p.get("classification"), 24),
                    _clean(p.get("protection"), 40),
                    _clean(p.get("rationale"), 100),
                ]
                for p in pvs if isinstance(p, dict)
            ],
        ))
    parts.append(f"\n{_UNSIZED_RULE}\n\n")
    if unsized:
        parts.append(_table(
            ["Unsized risk", "Why unsized", "What would size it"],
            [
                [
                    _clean(u.get("risk"), 40),
                    _clean(u.get("why_unsized"), 80),
                    _clean(u.get("what_would_size"), 100),
                ]
                for u in unsized if isinstance(u, dict)
            ],
        ))
    parts.append("---\n\n")

    # 6 — Internal Risk boundary
    ir_cross = (
        spec.get("internal_risk_cross_check")
        if isinstance(spec.get("internal_risk_cross_check"), dict) else {}
    )
    parts.append("## 6. Internal Risk Boundary\n\n")
    parts.append(f"{_INTERNAL_CROSS_RULE}\n\n")
    parts.append(_table(
        ["Field", "Value"],
        [
            [
                "Internal prior present",
                "Yes" if ir_cross.get("internal_prior_present") else "No",
            ],
            [
                "Handed to Internal Risk",
                _clean("; ".join(ir_cross.get("handed_to_internal") or []) or _NA, 200),
            ],
            [
                "Overlap",
                _clean("; ".join(ir_cross.get("overlap") or []) or _NA, 200),
            ],
            [
                "Aligned",
                _clean("; ".join(ir_cross.get("aligned") or []) or _NA, 200),
            ],
            [
                "Conflicts",
                _clean("; ".join(ir_cross.get("conflicts") or []) or "None", 200),
            ],
        ],
    ))
    rejected = spec.get("rejected_unnamed") if isinstance(spec.get("rejected_unnamed"), list) else []
    if rejected:
        parts.append(
            f"\nRejected unnamed threats: {_clean('; '.join(str(x) for x in rejected[:6]), 200)}\n\n"
        )
    parts.append("---\n\n")

    # Supporting registers (legacy dual-write)
    if regulatory:
        parts.append("## Supporting — Regulatory Register\n\n")
        parts.append(_table(
            ["Area", "Status", "Risk level"],
            [
                [
                    _clean(r.get("area"), 40),
                    _clean(r.get("status"), 24),
                    _clean(r.get("risk_level"), 16),
                ]
                for r in regulatory if isinstance(r, dict)
            ],
        ))
        parts.append("---\n\n")
    if litigation:
        parts.append("## Supporting — Litigation / Claims\n\n")
        for lit in litigation[:8]:
            parts.append(f"- {_soften_invest(_clean(lit, 160))}\n")
        parts.append("\n---\n\n")

    # 7 QA
    mr_qa = (
        spec.get("mr_evidence_qa")
        if isinstance(spec.get("mr_evidence_qa"), list) else []
    )
    parts.append("## 7. Market Risk Evidence QA\n\n")
    parts.append(
        "QA enforces row schema (trigger/population/timing/mechanism/mitigation), "
        "dollar exposure (or sizing ask), evidence-based likelihood, early warnings, "
        "price vs structure, Internal Risk non-overlap, and unnamed-threat rejection.\n\n"
    )
    parts.append(
        _table(
            ["Check", "Status", "Finding", "Action"],
            [
                [
                    _clean(r.get("check"), 60),
                    _clean(r.get("status"), 20),
                    _clean(r.get("finding"), 220),
                    _clean(r.get("action"), 180),
                ]
                for r in mr_qa
                if isinstance(r, dict)
            ],
        )
        or f"**{_info_request('Market Risk evidence QA rows')}**\n\n"
    )
    parts.append("---\n\n")

    # 8 Questions
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    parts.append("## 8. Questions and Inputs Required\n\n")
    if questions:
        for row in questions[:12]:
            if not isinstance(row, dict):
                continue
            parts.append(
                f"- **{_clean(row.get('question'), 200)}** — "
                f"records: {_clean(row.get('required_records'), 120)}; "
                f"effect: {_clean(row.get('decision_effect'), 120)}; "
                f"priority: {_clean(row.get('priority'), 40)}; "
                f"owner: {_clean(row.get('owner'), 40)}; "
                f"timing: {_clean(row.get('timing'), 40)}; "
                f"closure: {_clean(row.get('closure_test'), 120)}; "
                f"interim: {_clean(row.get('interim_treatment'), 120)}\n"
            )
        parts.append("\n")
    else:
        parts.append(
            "None are missing — material Market Risk gaps are closed, "
            "or no Questions were generated from open QA FAILs.\n\n"
        )
    parts.append("---\n\n")

    # 9 Quality
    parts.append("## 9. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(qv, 30)],
            ["Reliance Verdict", _clean(rv, 30)],
            ["Rationale", _clean(rationale, 460)],
        ],
    ))
    parts.append(f"**Quality:** {_clean(qv, 20)} — is the work accurate and honest about limits?\n\n")
    parts.append(f"**Reliance:** {_clean(rv, 20)} — can a decision rest on this Market Risk assessment?\n\n")
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open Market Risk QA FAILs cap READY → LIMITED. "
        f"{_UNNAMED_RULE} {_INTERNAL_CROSS_RULE} "
        "This agent does not issue an invest or pass recommendation.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(srcs[:16], start=1):
            parts.append(f"{i}. {_clean(name, 120)}\n")
    else:
        parts.append(f"1. {_NA}\n")
    parts.append("\n")
    return "".join(parts)
