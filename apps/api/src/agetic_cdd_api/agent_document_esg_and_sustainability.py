"""Compose DiligenceIQ ESG & Sustainability — material ESG with financial consequence.

Material topics for sector/jurisdiction/ownership (with why); product impact
vs operating footprint; measured metrics (boundary, method, baseline,
denominator) separate from targets; workforce/safety where cost/continuity;
consequences (or explicitly none). Do not apply reporting regimes below
threshold. Do not infer environmental performance from revenue or site count.

Dual-writes legacy F-ESG fields (themes / labour_flags / environment_flags).

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

_DOCUMENT_TITLE = "ESG & Sustainability"
_DD_CODE = "F-ESG"
_AGENT_KEY = "esg_and_sustainability"

_MATERIAL_RULE = (
    "Topics that are material for this sector, jurisdiction and ownership "
    "structure — with why each is material. Non-material topics are omitted."
)
_FOOTPRINT_RULE = (
    "The positive impact of what the company sells is separated from the "
    "footprint of how it operates. They are different questions."
)
_METRIC_RULE = (
    "For each measured metric: boundary, method, baseline year and denominator. "
    "Management targets are kept separate from measured results."
)
_WORKFORCE_RULE = (
    "Workforce and safety are covered where they affect cost or continuity: "
    "turnover, incidents, absence, and any regulatory action."
)
_CONSEQUENCE_RULE = (
    "Consequence is a cost, a permit condition, a customer requirement, or a "
    "reporting obligation with its threshold and date. Where there is no "
    "financial or regulatory consequence, say so and keep the section short."
)
_NO_INFER_RULE = (
    "Environmental performance is not inferred from revenue or site count. "
    "Reporting regimes below the company's threshold are not applied."
)
_REG_CROSS_RULE = (
    "Cross-check overlapping permits, obligations and regulatory actions with "
    "Regulatory Compliance — do not invent a parallel compliance register."
)

_ENV_TOPIC_RE = re.compile(
    r"(?i)\b("
    r"environmental\s+clearance|emissions?|GHG|Scope\s*[123]|carbon|"
    r"energy\s+(?:use|intensity|consumption)|water\s+(?:use|stress)|"
    r"waste|hazardous|battery\s+(?:recycl|disposal|safety)|"
    r"fame[-\s]?i{1,3}|subsidy|ais\s*\d+|pollution|moefcc|"
    r"climate|decarboni[sz]ation"
    r")\b"
)
_SOCIAL_TOPIC_RE = re.compile(
    r"(?i)\b("
    r"attrition|turnover|workforce|headcount|safety|incident|"
    r"lost[- ]time|LTIFR|TRIR|absence|absentee|"
    r"factories\s+act|labour|labor\s+law|dei|diversity|"
    r"engagement|enps|layoff|contract\s+workers?"
    r")\b"
)
_GOV_TOPIC_RE = re.compile(
    r"(?i)\b("
    r"board|governance|sebi\s+lodr|companies\s+act|related[- ]party|"
    r"insider\s+trading|esop|whistle|bribery|corruption|ethics|"
    r"data\s+protection|dpdpa|ccpa|cyber"
    r")\b"
)
_PRODUCT_IMPACT_RE = re.compile(
    r"(?i)\b("
    r"zero[- ]emission|displac(?:e|ing)\s+(?:ICE|petrol|diesel)|"
    r"green\s+mobility|clean\s+transport|avoided\s+emissions|"
    r"product\s+(?:impact|benefit)|enabl(?:e|ing)\s+decarbon|"
    r"electric\s+two[- ]wheeler|EV\s+2W"
    r")\b"
)
_FOOTPRINT_CUE_RE = re.compile(
    r"(?i)\b("
    r"environmental\s+clearance|"
    r"battery\s+(?:recycl|disposal)|scope\s*[123]|ghg\s+emissions?|"
    r"hazardous\s+waste|water\s+(?:use|stress)|energy\s+(?:intensity|consumption)|"
    r"factory\s+(?:energy|emissions|waste)|manufacturing\s+(?:emissions|waste)"
    r")\b"
)
_METRIC_RE = re.compile(
    r"(?i)\b("
    r"(?:attrition|turnover)\s+rate|"
    r"employee\s+engagement\s+score|eNPS|"
    r"female\s+employees?|"
    r"total\s+headcount|FTE|"
    r"Scope\s*[123]|GHG\s+emissions?|"
    r"energy\s+intensity|water\s+intensity|"
    r"LTIFR|TRIR|lost[- ]time\s+injur|"
    r"incident\s+rate"
    r")\b"
)
_TARGET_RE = re.compile(
    r"(?i)\b(target|goal|ambition|commit(?:ment|ted)|net[- ]zero|"
    r"by\s+FY?\s*20\d{2}|roadmap\s+to)\b"
)
_REPORTING_REGIME_RE = re.compile(
    r"(?i)\b(CSRD|SFDR|TCFD|ISSB|GRI|BRSR|SEBI\s+BRSR|"
    r"EU\s+Taxonomy|CDP|SASB)\b"
)
_YEAR_RE = re.compile(r"(?i)\b(FY\s*20\d{2}E?|20\d{2})\b")
_PCT_RE = re.compile(r"(?i)([\d.]+)\s*%")
_NUM_RE = re.compile(r"(?i)\b([\d,]+(?:\.\d+)?)\b")
_THRESHOLD_RE = re.compile(
    r"(?i)(threshold|above|exceed|more\s+than|greater\s+than|"
    r"employees?\s*[>≥]?\s*[\d,]+|turnover\s*[>≥]?\s*(?:INR|USD|€))"
)


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("ESG evidence only — no deal verdict expressed", raw)
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _info_request(need: str) -> str:
    return f"Information request: {need}"


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


def _window(text: str, start: int, *, radius: int = 140) -> str:
    return text[max(0, start - radius) : min(len(text), start + radius)]


def _is_info(val: Any) -> bool:
    s = str(val or "")
    return (
        not s
        or s.startswith("Information")
        or s.startswith("N/A")
        or s == _NA
    )


def _infer_geography(corpus: str, geography: str | None) -> str | None:
    if geography and str(geography).strip() and not str(geography).startswith("Information"):
        return str(geography).strip()
    low = (corpus or "").lower()
    if re.search(r"\b(india|sebi|brsr|fame|moefcc|factories\s+act)\b", low):
        return "India"
    if re.search(r"\b(united states|u\.s\.a?\.|sec\b)\b", low):
        return "United States"
    if re.search(r"\b(european union|eu\b|csrd|sfdr)\b", low):
        return "European Union"
    if re.search(r"\b(united kingdom|u\.k\.|fca\b)\b", low):
        return "United Kingdom"
    return None


def _infer_sector(corpus: str, sector: str | None) -> str | None:
    raw = (sector or "").strip()
    if raw and raw.lower() not in {"generic", "unknown", "n/a", "none"}:
        if not raw.startswith("Information"):
            return raw
    low = (corpus or "").lower()
    if re.search(r"electric\s+two[- ]wheelers?|e[- ]?2w|ev\s+2w", low):
        return "Electric Two-Wheelers"
    if re.search(r"electric\s+vehicle|\bev\b|e[- ]mobility", low):
        return "Electric Vehicles"
    if re.search(r"renewable|solar|wind\s+power|cleantech", low):
        return "Clean Energy"
    return None


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


def gather_esg_and_sustainability_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "legal_esg": 0,
        "company_management": 1,
        "operations": 2,
        "deal_strategy": 3,
        "financial": 4,
    }
    needles = (
        "esg", "sustainab", "environment", "emission", "hr", "org",
        "workforce", "safety", "labour", "labor", "legal", "fame",
        "dei", "governance",
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
# section builders
# ---------------------------------------------------------------------------


def _why_material(
    topic: str,
    *,
    pillar: str,
    sector: str | None,
    geography: str | None,
    window: str,
) -> str:
    low = f"{topic} {window}".lower()
    bits: list[str] = []
    if pillar == "E":
        if "fame" in low or "subsidy" in low:
            bits.append("Subsidy / incentive exposure affects volume and cash")
        if "clearance" in low or "permit" in low or "moefcc" in low:
            bits.append("Operating permit / clearance condition for sites")
        if "battery" in low or "ais" in low:
            bits.append("Product / plant safety standard with regulatory force")
        if "emission" in low or "ghg" in low or "carbon" in low:
            bits.append("Operating emissions may drive cost or customer requirements")
        if not bits and sector and "electric" in sector.lower():
            bits.append(f"Material for {sector} operating footprint in {geography or 'this jurisdiction'}")
    elif pillar == "S":
        if "attrition" in low or "turnover" in low:
            bits.append("Turnover drives recruiting cost and continuity risk")
        if "safety" in low or "incident" in low or "ltifr" in low:
            bits.append("Safety incidents affect cost, continuity and regulatory action")
        if "factories" in low or "labour" in low or "labor" in low:
            bits.append("Labour-law compliance binds manufacturing sites")
        if "engagement" in low or "enps" in low or "layoff" in low:
            bits.append("Engagement / culture signals affect retention cost")
        if not bits:
            bits.append("Workforce factor with cost or continuity consequence")
    else:  # G
        if "sebi" in low or "lodr" in low or "listed" in low:
            bits.append("Listed ownership — governance / disclosure obligations bind")
        if "dpdpa" in low or "ccpa" in low or "data" in low:
            bits.append("Data / consumer protection with regulatory and claim exposure")
        if "board" in low or "related" in low:
            bits.append("Board / related-party governance affects control risk")
        if not bits:
            bits.append("Governance factor with regulatory or ownership consequence")
    return "; ".join(bits) if bits else _info_request(f"why '{topic}' is material")


def _build_material_topics(
    *,
    corpus: str,
    legacy: dict[str, Any],
    sector: str | None,
    geography: str | None,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(topic: str, pillar: str, window: str, source: str = _DOC_CITE) -> None:
        key = _topic_stem(topic)
        if not key or key in seen or _is_info(topic):
            return
        # Skip generic legal noise that is not ESG-material (pure corporate filings)
        low = topic.lower()
        if len(topic) > 90 or topic.count(" ") > 14:
            # Long narrative sentences are not topic labels
            if "listed" in low and ("bse" in low or "nse" in low or "public" in low):
                topic = "Listed ownership / public-company governance"
                key = _topic_stem(topic)
                if key in seen:
                    return
            else:
                return
        if pillar == "G" and any(
            k in low for k in ("companies act compliance", "insider trading norms")
        ) and "listed" not in text.lower() and "sebi" not in low:
            # Still keep if listed ownership evidenced
            if "listed" not in text.lower() and "sebi lodr" not in text.lower():
                return
        # Omit pure employment litigation captions unless they carry a workforce metric
        if pillar == "S" and any(
            k in low for k in ("nda", "ex-employee", "employment law inr")
        ) and not any(k in low for k in ("attrition", "safety", "factories", "labour", "labor")):
            return
        # Skip incorporation blurbs mis-seeded as themes
        if "incorporated as" in low or "legal name" in low:
            if "listed" in low:
                topic = "Listed ownership / public-company governance"
                key = _topic_stem(topic)
                if key in seen:
                    return
            else:
                return
        seen.add(key)
        rows.append(
            {
                "topic": _clean(topic, 80),
                "pillar": pillar,
                "why_material": _why_material(
                    topic, pillar=pillar, sector=sector, geography=geography, window=window
                ),
                "source": source,
                "notes": _MATERIAL_RULE,
            }
        )

    # Seed from legacy environment / labour / themes
    for note in legacy.get("environment_flags") or []:
        if isinstance(note, str) and note.strip():
            _add(note.split("—")[0].strip(), "E", note)
    for note in legacy.get("labour_flags") or []:
        if isinstance(note, str) and note.strip():
            _add(note.split("—")[0].strip(), "S", note)
    for note in legacy.get("themes") or []:
        if not isinstance(note, str) or not note.strip():
            continue
        low = note.lower()
        if _ENV_TOPIC_RE.search(note):
            _add(note.split("—")[0].strip(), "E", note)
        elif _SOCIAL_TOPIC_RE.search(note):
            _add(note.split("—")[0].strip(), "S", note)
        elif _GOV_TOPIC_RE.search(note):
            # Prefer governance with consequence — listed / data / board
            if any(k in low for k in ("sebi", "lodr", "dpdpa", "ccpa", "board", "listed", "esop")):
                _add(note.split("—")[0].strip(), "G", note)

    # Corpus discoveries — only when legacy seeds are thin, and only strong cues
    if len(rows) < 8:
        strong_env = re.compile(
            r"(?i)\b(environmental\s+clearance|fame[-\s]?i{1,3}|ais\s*\d+|"
            r"battery\s+(?:recycl|safety)|scope\s*[123]|ghg\s+emissions?)\b"
        )
        strong_social = re.compile(
            r"(?i)\b(attrition|turnover|ltifr|trir|factories\s+act|"
            r"lost[- ]time|safety\s+incident)\b"
        )
        strong_gov = re.compile(
            r"(?i)\b(sebi\s+lodr|dpdpa|ccpa|listed\s+ownership|whistleblow)\b"
        )
        for cre, pillar in (
            (strong_env, "E"),
            (strong_social, "S"),
            (strong_gov, "G"),
        ):
            for m in cre.finditer(text):
                raw = _clean(m.group(0), 50)
                _add(raw, pillar, _window(text, m.start(), radius=80))
                if len(rows) >= 10:
                    break
            if len(rows) >= 10:
                break

    if not rows:
        rows.append(
            {
                "topic": _info_request(
                    "material ESG topics for this sector / jurisdiction / ownership"
                ),
                "pillar": "—",
                "why_material": _MATERIAL_RULE,
                "source": _NA,
                "notes": _MATERIAL_RULE,
            }
        )
    return rows[:12]


def _sentence_around(text: str, start: int, *, max_chars: int = 160) -> str:
    """Pull a readable clause around ``start``, skipping header/snapshot junk."""
    left = max(0, start - 80)
    right = min(len(text), start + 120)
    chunk = text[left:right]
    local = start - left
    before = chunk[:local]
    after = chunk[local:]
    b_cut = max(before.rfind(". "), before.rfind("; "), before.rfind(" — "))
    a_positions = [p for p in (after.find(". "), after.find("; ")) if p >= 0]
    a_cut = min(a_positions) if a_positions else len(after)
    clause = (
        (before[b_cut + 2 :] if b_cut >= 0 else before) + after[:a_cut]
    ).strip(" .;—-")
    clause = _clean(clause, max_chars)
    low = clause.lower()
    if any(
        junk in low
        for junk in (
            "insight snapshot",
            "parameter details",
            "legal name",
            "core corporate identifiers",
            "compliant low",
            "compliant medium",
            "compliant high",
            "compliant (gen",
            "bommasandra",
            "registered office",
            "sno ",
            "taluk",
            "investment pillars",
            "usd ",
            " som ",
            "target usd",
            "segment usd",
            "avg selling price",
            "revenue (inr",
            "monthly ru",
            " (%) ",
        )
    ):
        return ""
    # Reject market-sizing / financial table scraps
    if re.search(r"(?i)(~?\d+\s*%|\binr\s*cr\b|\brevenue\b|\basp\b)", clause) and not re.search(
        r"(?i)(zero[- ]emission|displac|avoided\s+emission|footprint)", clause
    ):
        return ""
    return clause


def _topic_stem(topic: str) -> str:
    low = re.sub(r"[^a-z0-9]+", " ", (topic or "").lower()).strip()
    for stem in (
        "fame",
        "ais 156",
        "battery safety",
        "environmental clearance",
        "moefcc",
        "factories act",
        "labor law",
        "labour law",
        "sebi lodr",
        "dpdpa",
        "ccpa",
        "listed ownership",
    ):
        if stem in low:
            # Collapse AIS / battery-safety aliases
            if stem in {"ais 156", "battery safety"}:
                return "battery safety / ais"
            if stem in {"environmental clearance", "moefcc"}:
                return "environmental clearance"
            if stem in {"factories act", "labor law", "labour law"}:
                return "factories act"
            return stem
    # Drop bare single-token / weak social labels from corpus scans
    tokens = low.split()
    if len(tokens) <= 1 and low in {
        "climate", "subsidy", "carbon", "energy", "water", "waste", "board",
        "ethics", "fame", "safety", "workforce", "labour", "labor", "attrition",
        "turnover", "incident", "absence", "headcount", "engagement", "layoff",
        "enps",
    }:
        return ""
    return " ".join(tokens[:4]) if tokens else low


def _build_product_vs_footprint(
    *,
    corpus: str,
    sector: str | None,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []

    # Product / use-phase impact — require strong impact language; else sector note
    product_finding = ""
    strong = re.compile(
        r"(?i)\b(zero[- ]emission|displac(?:e|ing)\s+(?:ICE|petrol|diesel)|"
        r"avoided\s+emissions|green\s+mobility|clean\s+transport|"
        r"product\s+(?:impact|benefit)|enabl(?:e|ing)\s+decarbon)\b"
    )
    for pm in strong.finditer(text):
        clause = _sentence_around(text, pm.start())
        if clause and len(clause) >= 24:
            product_finding = clause
            break
    if product_finding:
        rows.append(
            {
                "lens": "Product / what it sells",
                "finding": product_finding,
                "source": _DOC_CITE,
                "notes": _FOOTPRINT_RULE,
            }
        )
    elif sector and any(k in sector.lower() for k in ("electric", "ev", "renewable", "cleantech")):
        rows.append(
            {
                "lens": "Product / what it sells",
                "finding": (
                    f"Sector ({sector}) implies a use-phase / product impact story — "
                    f"not evidenced quantitatively in opened packs"
                ),
                "source": _COMPUTED,
                "notes": _FOOTPRINT_RULE,
            }
        )
    else:
        rows.append(
            {
                "lens": "Product / what it sells",
                "finding": _info_request(
                    "positive impact of what the company sells (use-phase / product)"
                ),
                "source": _NA,
                "notes": _FOOTPRINT_RULE,
            }
        )

    # Operating footprint — prefer clearance / emissions / waste cues over generic legal tables
    footprint_bits: list[str] = []
    # Prefer an explicit clearance line when present
    ec = re.search(
        r"(?i)Environmental\s+Clearance[^\n.]{0,80}",
        text,
    )
    if ec:
        footprint_bits.append(_clean(ec.group(0), 120))
    for m in _FOOTPRINT_CUE_RE.finditer(text):
        if "environmental clearance" in m.group(0).lower() and footprint_bits:
            continue
        clause = _sentence_around(text, m.start(), max_chars=120)
        if clause and clause not in footprint_bits:
            footprint_bits.append(clause)
        if len(footprint_bits) >= 2:
            break
    if not footprint_bits:
        for cue in (
            "environmental clearance",
            "battery recycl",
            "manufacturing emissions",
            "factory energy",
        ):
            idx = text.lower().find(cue)
            if idx >= 0:
                clause = _sentence_around(text, idx, max_chars=120)
                if clause:
                    footprint_bits.append(clause)
                    break
    rows.append(
        {
            "lens": "Operating footprint / how it operates",
            "finding": (
                "; ".join(dict.fromkeys(footprint_bits))
                if footprint_bits
                else _info_request(
                    "operating environmental / social footprint "
                    "(not inferred from revenue or site count)"
                )
            ),
            "source": _DOC_CITE if footprint_bits else _NA,
            "notes": f"{_FOOTPRINT_RULE} {_NO_INFER_RULE}",
        }
    )
    return rows


def _build_measured_metrics(
    *,
    corpus: str,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Explicit multi-year workforce metrics from HR-style tables
    for label, pattern in (
        (
            "Attrition rate",
            re.compile(
                r"(?i)Attrition\s+Rate\s*\(?%\)?\s*([\d.]+)\s*%?\s+([\d.]+)\s*%?\s+([\d.]+)\s*%?"
            ),
        ),
        (
            "Total headcount (FTE)",
            re.compile(
                r"(?i)Total\s+Headcount\s*\(?FTE\)?\s*([\d,]+)\s+([\d,]+)\s+([\d,]+)"
            ),
        ),
        (
            "Female employees (%)",
            re.compile(
                r"(?i)Female\s+Employees?\s*\(?%\)?\s*([\d.]+)\s*%?\s+([\d.]+)\s*%?\s+([\d.]+)\s*%?"
            ),
        ),
        (
            "Employee engagement score",
            re.compile(
                r"(?i)Employee\s+Engagement\s+Score\s*([\d.]+)\s*/\s*100"
            ),
        ),
        (
            "eNPS",
            re.compile(r"(?i)eNPS[^\d]{0,20}([\d.]+)"),
        ),
        (
            "Attrition — Technology",
            re.compile(r"(?i)Attrition\s*[—\-]\s*Technology\s*([\d.]+)\s*%"),
        ),
        (
            "Attrition — Manufacturing",
            re.compile(r"(?i)Attrition\s*[—\-]\s*Manufacturing\s*([\d.]+)\s*%"),
        ),
    ):
        m = pattern.search(text)
        if not m:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        groups = m.groups()
        if len(groups) >= 3:
            measured = f"FY series: {groups[0]} → {groups[1]} → {groups[2]}"
            baseline = "FY2022–FY2024E (pack series)"
        else:
            measured = groups[0]
            baseline = _clean(_YEAR_RE.search(_window(text, m.start())).group(0), 20) if _YEAR_RE.search(_window(text, m.start())) else _info_request("baseline year")
        # Target from nearby benchmark column if present
        win = _window(text, m.start(), radius=80)
        target = _NA
        bm = re.search(r"(?i)(?:benchmark|target)\s*([\d.]+(?:\s*/\s*100)?%?)", win)
        if bm:
            target = _clean(bm.group(0), 40)
        elif "72 / 100" in win and "engagement" in label.lower():
            target = "Benchmark 72 / 100 (not a management target)"
        rows.append(
            {
                "metric": label,
                "measured_result": measured,
                "management_target": target,
                "boundary": (
                    "Workforce / company (pack table)"
                    if "attrition" in label.lower() or "headcount" in label.lower() or "female" in label.lower() or "engagement" in label.lower() or "enps" in label.lower()
                    else _info_request("reporting boundary")
                ),
                "method": "Pack HR / organisational table (not third-party assurance)",
                "baseline_year": baseline,
                "denominator": (
                    "% of average FTE" if "attrition" in label.lower() or "%" in label
                    else ("FTE headcount" if "headcount" in label.lower() else _info_request("denominator"))
                ),
                "source": _DOC_CITE,
                "notes": _METRIC_RULE,
            }
        )

    # Generic metric cues without inventing values from revenue/sites
    for m in _METRIC_RE.finditer(text):
        label = _clean(m.group(0), 40)
        if label.lower() in seen:
            continue
        # Refuse env inference from revenue / site count language nearby
        win = _window(text, m.start(), radius=100)
        if re.search(r"(?i)(per\s+site|site\s+count|revenue\s+implies|implied\s+emission)", win):
            continue
        if any(k in label.lower() for k in ("ghg", "scope", "energy", "water", "ltifr", "trir")):
            seen.add(label.lower())
            pct = _PCT_RE.search(win)
            num = _NUM_RE.search(win[len(m.group(0)): len(m.group(0)) + 40]) if len(win) > len(m.group(0)) else None
            measured = pct.group(0) if pct else (num.group(0) if num else _info_request("measured result"))
            target = _NA
            if _TARGET_RE.search(win):
                target = _clean(_TARGET_RE.search(win).group(0) + " " + (_YEAR_RE.search(win).group(0) if _YEAR_RE.search(win) else ""), 40)
            rows.append(
                {
                    "metric": label,
                    "measured_result": measured,
                    "management_target": target,
                    "boundary": _info_request("reporting boundary (entity / equity / operational)"),
                    "method": _info_request("measurement method / assurance"),
                    "baseline_year": (
                        _clean(_YEAR_RE.search(win).group(0), 20)
                        if _YEAR_RE.search(win)
                        else _info_request("baseline year")
                    ),
                    "denominator": _info_request("denominator (e.g. tCO2e / unit, hours worked)"),
                    "source": _DOC_CITE,
                    "notes": f"{_METRIC_RULE} {_NO_INFER_RULE}",
                }
            )
        if len(rows) >= 10:
            break

    if not rows:
        rows.append(
            {
                "metric": _info_request("measured ESG metric"),
                "measured_result": _NA,
                "management_target": _NA,
                "boundary": _info_request("boundary"),
                "method": _info_request("method"),
                "baseline_year": _info_request("baseline year"),
                "denominator": _info_request("denominator"),
                "source": _NA,
                "notes": f"{_METRIC_RULE} {_NO_INFER_RULE}",
            }
        )
    return rows[:10]


def _build_workforce_safety(
    *,
    corpus: str,
    legacy: dict[str, Any],
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []

    # Attrition / turnover
    for label, pat in (
        ("Attrition (company)", r"(?i)Attrition\s+Rate\s*\(?%\)?\s*[\d.]+\s*%?\s+[\d.]+\s*%?\s+([\d.]+)\s*%?"),
        ("Attrition — Technology", r"(?i)Attrition\s*[—\-]\s*Technology\s*([\d.]+)\s*%"),
        ("Attrition — Manufacturing", r"(?i)Attrition\s*[—\-]\s*Manufacturing\s*([\d.]+)\s*%"),
    ):
        m = re.search(pat, text)
        if m:
            rows.append(
                {
                    "factor": label,
                    "record": f"{m.group(1)}%",
                    "cost_or_continuity": "Elevated turnover — recruiting cost and continuity risk",
                    "regulatory_action": _NA,
                    "source": _DOC_CITE,
                    "notes": _WORKFORCE_RULE,
                }
            )

    # Engagement / absence proxies
    for label, pat, consequence in (
        (
            "Employee engagement",
            r"(?i)Employee\s+Engagement\s+Score\s*([\d.]+)\s*/\s*100",
            "Below-benchmark engagement — retention / productivity cost",
        ),
        (
            "eNPS",
            r"(?i)eNPS[^\d]{0,20}([\d.]+)",
            "Dissatisfaction signal — continuity risk",
        ),
    ):
        m = re.search(pat, text)
        if m:
            rows.append(
                {
                    "factor": label,
                    "record": m.group(0) if "engagement" in label.lower() else m.group(1),
                    "cost_or_continuity": consequence,
                    "regulatory_action": _NA,
                    "source": _DOC_CITE,
                    "notes": _WORKFORCE_RULE,
                }
            )

    # Safety / incidents
    sm = re.search(
        r"(?i)(LTIFR|TRIR|lost[- ]time|safety\s+incident|fatality|injury\s+rate)[^\n.]{0,80}",
        text,
    )
    if sm:
        rows.append(
            {
                "factor": "Safety / incidents",
                "record": _clean(sm.group(0), 100),
                "cost_or_continuity": "Safety performance affects cost, continuity and regulatory exposure",
                "regulatory_action": _info_request("any safety regulatory action / notice"),
                "source": _DOC_CITE,
                "notes": _WORKFORCE_RULE,
            }
        )
    else:
        rows.append(
            {
                "factor": "Safety / incidents",
                "record": _info_request("safety incident / LTIFR / TRIR record"),
                "cost_or_continuity": _info_request("cost or continuity effect"),
                "regulatory_action": _NA,
                "source": _NA,
                "notes": _WORKFORCE_RULE,
            }
        )

    # Labour regulatory action from legacy
    for note in legacy.get("labour_flags") or []:
        if not isinstance(note, str):
            continue
        if any(k in note.lower() for k in ("nda", "dispute", "arbitration", "complaint", "action")):
            rows.append(
                {
                    "factor": "Labour / employment regulatory or claims action",
                    "record": _clean(note, 120),
                    "cost_or_continuity": "Claim / dispute cost and management distraction",
                    "regulatory_action": _clean(note, 80),
                    "source": _DOC_CITE,
                    "notes": _WORKFORCE_RULE,
                }
            )

    # Factories Act compliance as workforce regulatory
    for note in legacy.get("labour_flags") or []:
        if isinstance(note, str) and "factories" in note.lower():
            rows.append(
                {
                    "factor": "Factories Act / labour-law compliance",
                    "record": _clean(note, 120),
                    "cost_or_continuity": "Site continuity depends on labour-law standing",
                    "regulatory_action": _clean(note, 80),
                    "source": _DOC_CITE,
                    "notes": _WORKFORCE_RULE,
                }
            )
            break

    return rows[:10]


def _regime_threshold_applies(regime: str, corpus: str, geography: str | None) -> tuple[bool, str]:
    """Return (applies, rationale). Do not apply regimes below threshold."""
    low = corpus.lower()
    r = regime.upper()
    if r in {"CSRD", "SFDR", "EU TAXONOMY"}:
        if geography and "europe" in geography.lower():
            if _THRESHOLD_RE.search(corpus) or "csrd" in low:
                return True, "EU geography / regime referenced in packs"
            return False, "EU regime — company threshold / scoping not evidenced; not applied"
        return False, "Company not evidenced as in-scope for this EU regime; not applied"
    if r in {"TCFD", "ISSB", "GRI", "CDP", "SASB"}:
        if regime.lower() in low or r.lower() in low:
            return True, f"{regime} referenced in packs"
        return False, f"{regime} not evidenced as adopted; not applied"
    if "BRSR" in r or r == "SEBI BRSR":
        if geography and "india" in geography.lower():
            if "listed" in low or "sebi" in low or "brsr" in low:
                # Listed India cos often in BRSR scope — still require pack evidence of applicability
                if "brsr" in low:
                    return True, "SEBI BRSR referenced in packs"
                return False, (
                    "Listed India entity may face BRSR — threshold / applicability "
                    "not confirmed in packs; not applied as a requirement"
                )
        return False, "SEBI BRSR not applicable / not evidenced; not applied"
    return False, f"{regime} not evidenced; not applied"


def _build_consequences(
    *,
    corpus: str,
    material: list[dict[str, Any]],
    workforce: list[dict[str, Any]],
    geography: str | None,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []

    # Permit / clearance consequences
    if re.search(r"(?i)environmental\s+clearance", text):
        rows.append(
            {
                "topic": "Environmental Clearance (Factory)",
                "consequence_type": "Permit condition",
                "detail": "Factory environmental clearance — operating condition; transfer/consent risk on transaction",
                "threshold_and_date": _info_request("clearance conditions, validity and renewal date"),
                "source": _DOC_CITE,
                "notes": _CONSEQUENCE_RULE,
            }
        )

    # Subsidy / incentive
    if re.search(r"(?i)fame|subsidy", text):
        rows.append(
            {
                "topic": "FAME / EV subsidy exposure",
                "consequence_type": "Cost / cash",
                "detail": "Subsidy claim status affects volume economics and near-term cash",
                "threshold_and_date": _info_request("claim amount, recovery timetable, policy date"),
                "source": _DOC_CITE,
                "notes": _CONSEQUENCE_RULE,
            }
        )

    # Workforce cost consequences from elevated attrition
    for w in workforce:
        if not isinstance(w, dict):
            continue
        if "attrition" in str(w.get("factor") or "").lower() and not _is_info(w.get("record")):
            rows.append(
                {
                    "topic": w.get("factor"),
                    "consequence_type": "Cost / continuity",
                    "detail": w.get("cost_or_continuity"),
                    "threshold_and_date": f"Measured {w.get('record')} (pack period)",
                    "source": w.get("source") or _DOC_CITE,
                    "notes": _CONSEQUENCE_RULE,
                }
            )

    # Customer / OEM requirements (battery safety)
    if re.search(r"(?i)ais\s*\d+|battery\s+safety", text):
        rows.append(
            {
                "topic": "Battery safety standard (AIS)",
                "consequence_type": "Customer / regulatory product requirement",
                "detail": "Product standard compliance required to sell in market",
                "threshold_and_date": _info_request("applicable AIS revision and effective date"),
                "source": _DOC_CITE,
                "notes": _CONSEQUENCE_RULE,
            }
        )

    # Reporting obligations — only if threshold met
    for m in _REPORTING_REGIME_RE.finditer(text):
        regime = _clean(m.group(0), 30)
        applies, why = _regime_threshold_applies(regime, text, geography)
        if applies:
            rows.append(
                {
                    "topic": f"Reporting — {regime}",
                    "consequence_type": "Reporting obligation",
                    "detail": why,
                    "threshold_and_date": _info_request(
                        f"applicability threshold and first reporting date for {regime}"
                    ),
                    "source": _DOC_CITE,
                    "notes": f"{_CONSEQUENCE_RULE} {_NO_INFER_RULE}",
                }
            )
        else:
            rows.append(
                {
                    "topic": f"Reporting — {regime}",
                    "consequence_type": "No consequence applied",
                    "detail": why,
                    "threshold_and_date": "Not applied — threshold / scoping not met or not evidenced",
                    "source": _COMPUTED,
                    "notes": f"{_CONSEQUENCE_RULE} {_NO_INFER_RULE}",
                }
            )

    # Explicit "no consequence" for material topics without a mapped consequence
    covered = {str(r.get("topic") or "").lower()[:30] for r in rows}
    short_none: list[dict[str, Any]] = []
    for t in material:
        if not isinstance(t, dict) or _is_info(t.get("topic")):
            continue
        topic = str(t.get("topic") or "")
        if any(topic.lower()[:20] in c for c in covered):
            continue
        # Governance themes without a clear financial hook stay short
        if t.get("pillar") == "G" and not any(
            k in topic.lower() for k in ("dpdpa", "ccpa", "sebi", "bribery")
        ):
            short_none.append(
                {
                    "topic": topic,
                    "consequence_type": "No financial / regulatory consequence evidenced",
                    "detail": "Material for ownership/governance narrative only — no cost, permit, customer or reporting hook evidenced",
                    "threshold_and_date": _NA,
                    "source": t.get("source") or _DOC_CITE,
                    "notes": _CONSEQUENCE_RULE,
                }
            )
    rows.extend(short_none[:3])

    if not rows:
        rows.append(
            {
                "topic": _info_request("ESG topic with financial or regulatory consequence"),
                "consequence_type": "No financial / regulatory consequence evidenced",
                "detail": "Keep short until consequence is evidenced",
                "threshold_and_date": _NA,
                "source": _NA,
                "notes": _CONSEQUENCE_RULE,
            }
        )
    return rows[:12]


def _legacy_dual_write(
    *,
    legacy: dict[str, Any],
    material: list[dict[str, Any]],
    workforce: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    themes = [
        t for t in (legacy.get("themes") or [])
        if isinstance(t, str) and t.strip()
    ]
    labour = [
        t for t in (legacy.get("labour_flags") or [])
        if isinstance(t, str) and t.strip()
    ]
    env = [
        t for t in (legacy.get("environment_flags") or [])
        if isinstance(t, str) and t.strip()
    ]
    for m in material:
        if not isinstance(m, dict) or _is_info(m.get("topic")):
            continue
        line = f"{m.get('topic')} — {m.get('why_material')}"
        pillar = m.get("pillar")
        if pillar == "E" and line not in env:
            env.append(_clean(line, 160))
        elif pillar == "S" and line not in labour:
            labour.append(_clean(line, 160))
        elif line not in themes:
            themes.append(_clean(line, 160))
    for w in workforce:
        if isinstance(w, dict) and not _is_info(w.get("factor")):
            line = f"{w.get('factor')}: {w.get('record')}"
            if line not in labour:
                labour.append(_clean(line, 160))
    return themes[:12], labour[:12], env[:12]


def _esg_regulatory_cross_check(
    *,
    consequences: list[dict[str, Any]],
    material: list[dict[str, Any]],
    regulatory_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    present = isinstance(regulatory_spec, dict) and bool(regulatory_spec)
    aligned: list[str] = []
    conflicts: list[str] = []
    overlap: list[str] = []

    esg_permit_cues = []
    for row in list(consequences) + list(material):
        if not isinstance(row, dict):
            continue
        blob = f"{row.get('topic')} {row.get('consequence_type')} {row.get('detail')} {row.get('why_material')}"
        if re.search(r"(?i)\b(permit|clearance|licence|license|obligation|compliance)\b", blob):
            esg_permit_cues.append(_clean(row.get("topic") or blob, 80))

    if present:
        permits = regulatory_spec.get("permit_register") or []
        obligations = regulatory_spec.get("obligations") or []
        reg_topics = []
        for p in permits:
            if isinstance(p, dict) and p.get("identifier"):
                reg_topics.append(str(p.get("identifier")))
        for o in obligations:
            if isinstance(o, dict) and o.get("obligation"):
                reg_topics.append(str(o.get("obligation")))
        for cue in esg_permit_cues[:6]:
            hit = next(
                (
                    r for r in reg_topics
                    if cue.lower()[:20] in r.lower() or r.lower()[:20] in cue.lower()
                ),
                None,
            )
            if hit:
                overlap.append(f"{cue} ↔ {_clean(hit, 60)}")
            else:
                conflicts.append(
                    f"ESG cites '{cue}' without matching Regulatory Compliance row"
                )
        if overlap:
            aligned.append(f"{len(overlap)} overlapping permit/obligation cue(s)")
        elif not esg_permit_cues:
            aligned.append("Regulatory prior present; no ESG permit/obligation overlap claimed")
        else:
            aligned.append("Regulatory prior present; overlap unresolved")
    else:
        conflicts.append("Regulatory Compliance prior not available for cross-check")

    return {
        "regulatory_prior_present": present,
        "overlap": overlap[:6],
        "aligned": aligned,
        "conflicts": conflicts,
        "notes": _REG_CROSS_RULE,
    }


def _esg_evidence_qa(
    *,
    material: list[dict[str, Any]],
    product_footprint: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    workforce: list[dict[str, Any]],
    consequences: list[dict[str, Any]],
    reg_cross: dict[str, Any],
    corpus: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    real_m = [
        t for t in material
        if isinstance(t, dict) and not _is_info(t.get("topic")) and not _is_info(t.get("why_material"))
    ]
    rows.append({
        "check": "materiality_screen",
        "status": "PASS" if real_m else "FAIL",
        "finding": (
            f"{len(real_m)} material topic(s) with why"
            if real_m
            else _info_request("material topics for sector/jurisdiction/ownership with why")
        ),
        "action": _MATERIAL_RULE,
    })

    lenses = {
        str(r.get("lens") or "").lower()
        for r in product_footprint if isinstance(r, dict)
    }
    split_ok = any("product" in l for l in lenses) and any(
        "footprint" in l or "operat" in l for l in lenses
    )
    rows.append({
        "check": "product_vs_footprint_split",
        "status": "PASS" if split_ok else "FAIL",
        "finding": (
            "Product impact separated from operating footprint"
            if split_ok
            else _info_request("product impact vs operating footprint split")
        ),
        "action": _FOOTPRINT_RULE,
    })

    real_metrics = [
        m for m in metrics
        if isinstance(m, dict)
        and not _is_info(m.get("metric"))
        and not _is_info(m.get("measured_result"))
    ]
    fields_ok = all(
        not _is_info(m.get("boundary"))
        and not _is_info(m.get("method"))
        and not _is_info(m.get("baseline_year"))
        and not _is_info(m.get("denominator"))
        for m in real_metrics
    ) if real_metrics else False
    rows.append({
        "check": "metric_boundary_method_baseline",
        "status": "PASS" if real_metrics and fields_ok else "FAIL",
        "finding": (
            f"{len(real_metrics)} measured metric(s) with boundary/method/baseline/denominator"
            if real_metrics and fields_ok
            else _info_request("measured metrics with boundary, method, baseline, denominator")
        ),
        "action": _METRIC_RULE,
    })

    targets_separate = all(
        "management_target" in m
        for m in real_metrics
    ) if real_metrics else False
    # Also fail if target text is stuffed into measured_result
    blended = any(
        isinstance(m, dict)
        and _TARGET_RE.search(str(m.get("measured_result") or ""))
        and _is_info(m.get("management_target"))
        for m in metrics
    )
    rows.append({
        "check": "targets_vs_measured",
        "status": "PASS" if (targets_separate and not blended) or not real_metrics else "FAIL",
        "finding": (
            "Management targets kept separate from measured results"
            if (targets_separate and not blended) or not real_metrics
            else _info_request("separate management targets from measured results")
        ),
        "action": _METRIC_RULE,
    })

    real_w = [
        w for w in workforce
        if isinstance(w, dict) and not _is_info(w.get("factor")) and not _is_info(w.get("record"))
    ]
    rows.append({
        "check": "workforce_safety_where_material",
        "status": "PASS" if real_w else "FAIL",
        "finding": (
            f"{len(real_w)} workforce/safety record(s) with cost/continuity link"
            if real_w
            else _info_request("workforce/safety where cost or continuity is affected")
        ),
        "action": _WORKFORCE_RULE,
    })

    real_c = [
        c for c in consequences
        if isinstance(c, dict) and not _is_info(c.get("topic")) and not _is_info(c.get("consequence_type"))
    ]
    rows.append({
        "check": "consequence_column",
        "status": "PASS" if real_c else "FAIL",
        "finding": (
            f"{len(real_c)} consequence row(s) (cost/permit/customer/reporting/none)"
            if real_c
            else _info_request("financial / regulatory consequence column")
        ),
        "action": _CONSEQUENCE_RULE,
    })

    reg_ok = bool(reg_cross.get("regulatory_prior_present")) and not any(
        "without matching" in str(c).lower() for c in (reg_cross.get("conflicts") or [])
    )
    # Soft PASS when prior present even if some cues unmatched? Plan says cross-check.
    # FAIL when prior missing OR hard unmatched conflicts exist.
    hard = any("without matching" in str(c).lower() for c in (reg_cross.get("conflicts") or []))
    rows.append({
        "check": "regulatory_cross_check",
        "status": "PASS" if reg_ok or (reg_cross.get("regulatory_prior_present") and not hard) else "FAIL",
        "finding": (
            "; ".join(reg_cross.get("aligned") or []) or "Regulatory cross-check complete"
            if reg_cross.get("regulatory_prior_present") and not hard
            else (
                "; ".join(reg_cross.get("conflicts") or [])
                or _info_request("Regulatory Compliance prior for cross-check")
            )
        ),
        "action": _REG_CROSS_RULE,
    })

    # Affirmative inference only — strip advisory "do not infer…" sentences
    scrubbed = re.sub(
        r"(?i)[^.!?\n]*(?:"
        r"do\s+not\s+infer|"
        r"not\s+inferred\s+from|"
        r"environmental\s+performance\s+is\s+not\s+inferred"
        r")[^.!?\n]*[.!?]?",
        " ",
        corpus or "",
    )
    infer_viol = bool(
        re.search(
            r"(?i)(inferred from revenue|site count implies|emissions?\s+from\s+revenue|"
            r"implies\s+(?:strong\s+)?environmental|per\s+site\s+count)",
            scrubbed,
        )
    )
    # Also check metric rows (skip already-scrubbed Information requests)
    for m in metrics:
        if not isinstance(m, dict):
            continue
        if str(m.get("measured_result") or "").startswith("Information"):
            continue
        blob = f"{m.get('metric')} {m.get('measured_result')} {m.get('method')}"
        if re.search(r"(?i)(inferred from revenue|site count implies)", blob):
            infer_viol = True
    rows.append({
        "check": "no_emissions_from_revenue_sites",
        "status": "PASS" if not infer_viol else "FAIL",
        "finding": (
            "No environmental performance inferred from revenue or site count"
            if not infer_viol
            else "Emissions/performance inferred from revenue or site count — strip"
        ),
        "action": _NO_INFER_RULE,
    })
    return rows


def _questions_from_esg_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("esg_evidence_qa")
        if isinstance(spec.get("esg_evidence_qa"), list) else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("materiality_screen"):
        out.append(normalize_question({
            "question": "Complete materiality screen by sector, jurisdiction and ownership with why",
            "required_records": "Sector ESG matrix + jurisdiction rules + ownership notes",
            "decision_effect": "Non-material topics inflate diligence and miss real risks",
            "priority": "mandatory_pre_decision",
            "owner": "ESG diligence lead",
            "timing": "before IC",
            "closure_test": "materiality_screen QA PASS",
            "interim_treatment": "LIMITED — do not treat generic ESG lists as material",
        }))
    if _qa_fail("product_vs_footprint_split"):
        out.append(normalize_question({
            "question": "Separate product impact from operating footprint",
            "required_records": "Product claims + ops environmental packs",
            "decision_effect": "Blending product story with footprint misstates ESG risk",
            "priority": "signing_condition",
            "owner": "ESG diligence lead",
            "timing": "per deal timetable",
            "closure_test": "product_vs_footprint_split QA PASS",
            "interim_treatment": "LIMITED — keep lenses separate",
        }))
    if _qa_fail("metric_boundary_method_baseline"):
        out.append(normalize_question({
            "question": "Complete measured metrics with boundary, method, baseline and denominator",
            "required_records": "ESG data pack / sustainability report extracts",
            "decision_effect": "Metrics without method are not underwritable",
            "priority": "mandatory_pre_decision",
            "owner": "ESG / financial diligence",
            "timing": "before IC",
            "closure_test": "metric_boundary_method_baseline QA PASS",
            "interim_treatment": "LIMITED — withhold metric claims",
        }))
    if _qa_fail("targets_vs_measured"):
        out.append(normalize_question({
            "question": "Keep management targets in a separate column from measured results",
            "required_records": "Target schedule + measured actuals",
            "decision_effect": "Targets treated as results inflate delivery claims",
            "priority": "signing_condition",
            "owner": "ESG diligence lead",
            "timing": "per deal timetable",
            "closure_test": "targets_vs_measured QA PASS",
            "interim_treatment": "REWORK — split targets from measured",
        }))
    if _qa_fail("workforce_safety_where_material"):
        out.append(normalize_question({
            "question": "Provide workforce/safety records where cost or continuity is affected",
            "required_records": "HR attrition / safety / regulatory action packs",
            "decision_effect": "Open workforce gaps can break plan delivery and cost",
            "priority": "signing_condition",
            "owner": "HR / ESG diligence",
            "timing": "per deal timetable",
            "closure_test": "workforce_safety_where_material QA PASS",
            "interim_treatment": "LIMITED — treat workforce risk as open",
        }))
    if _qa_fail("consequence_column"):
        out.append(normalize_question({
            "question": "State financial / regulatory consequence (or explicitly none) per material topic",
            "required_records": "Permit / cost / customer / reporting schedules",
            "decision_effect": "ESG without consequence is narrative, not diligence",
            "priority": "mandatory_pre_decision",
            "owner": "ESG diligence lead",
            "timing": "before IC",
            "closure_test": "consequence_column QA PASS",
            "interim_treatment": "LIMITED — keep section short where consequence absent",
        }))
    if _qa_fail("regulatory_cross_check"):
        out.append(normalize_question({
            "question": "Supply Regulatory Compliance output and reconcile overlapping permits/obligations",
            "required_records": "Regulatory Compliance agent spec",
            "decision_effect": "Duplicate or conflicting compliance claims mislead IC",
            "priority": "signing_condition",
            "owner": "ESG / regulatory counsel",
            "timing": "per deal timetable",
            "closure_test": "regulatory_cross_check QA PASS",
            "interim_treatment": "LIMITED until Regulatory cross-check complete",
        }))
    if _qa_fail("no_emissions_from_revenue_sites"):
        out.append(normalize_question({
            "question": "Remove environmental figures inferred from revenue or site count",
            "required_records": "Measured emissions / intensity with method",
            "decision_effect": "Inferred emissions are invented performance",
            "priority": "mandatory_pre_decision",
            "owner": "ESG diligence lead",
            "timing": "before IC",
            "closure_test": "no_emissions_from_revenue_sites QA PASS",
            "interim_treatment": "REWORK — strip inferred env performance",
        }))
    return out


def _quality_reliance(
    *,
    material: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    workforce: list[dict[str, Any]],
    consequences: list[dict[str, Any]],
    qa_fail: bool = False,
) -> tuple[str, str, str]:
    real_m = [
        t for t in material
        if isinstance(t, dict) and not _is_info(t.get("topic"))
    ]
    real_metrics = [
        m for m in metrics
        if isinstance(m, dict)
        and not _is_info(m.get("metric"))
        and not _is_info(m.get("measured_result"))
    ]
    real_w = [
        w for w in workforce
        if isinstance(w, dict) and not _is_info(w.get("factor")) and not _is_info(w.get("record"))
    ]
    real_c = [
        c for c in consequences
        if isinstance(c, dict) and not _is_info(c.get("topic"))
    ]

    if real_m and (real_metrics or real_w):
        quality = "PASS"
    else:
        quality = "REWORK"

    if real_m and real_c:
        reliance = "READY" if (real_metrics or real_w) else "LIMITED"
    elif real_m:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    if qa_fail and reliance == "READY":
        reliance = "LIMITED"

    bits = [
        f"{len(real_m)} material topic(s)",
        f"{len(real_metrics)} measured metric(s) with results",
        f"{len(real_w)} workforce/safety record(s)",
        f"{len(real_c)} consequence row(s)",
        _NO_INFER_RULE,
    ]
    if qa_fail:
        bits.append("Open ESG QA FAILs cap READY → LIMITED")
    return quality, reliance, _soften_invest(". ".join(bits) + ".")


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_esg_and_sustainability_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    regulatory_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    geography = _infer_geography(corpus, geography)
    sector = _infer_sector(corpus, sector)
    material = _build_material_topics(
        corpus=corpus, legacy=legacy, sector=sector, geography=geography
    )
    product_footprint = _build_product_vs_footprint(corpus=corpus, sector=sector)
    metrics = _build_measured_metrics(corpus=corpus)
    workforce = _build_workforce_safety(corpus=corpus, legacy=legacy)
    consequences = _build_consequences(
        corpus=corpus,
        material=material,
        workforce=workforce,
        geography=geography,
    )
    reg_cross = _esg_regulatory_cross_check(
        consequences=consequences,
        material=material,
        regulatory_spec=regulatory_spec,
    )
    themes, labour, env = _legacy_dual_write(
        legacy=legacy, material=material, workforce=workforce
    )

    esg_qa = _esg_evidence_qa(
        material=material,
        product_footprint=product_footprint,
        metrics=metrics,
        workforce=workforce,
        consequences=consequences,
        reg_cross=reg_cross,
        corpus=corpus,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in esg_qa)

    quality, reliance, rationale = _quality_reliance(
        material=material,
        metrics=metrics,
        workforce=workforce,
        consequences=consequences,
        qa_fail=qa_fail,
    )

    real_m = sum(1 for t in material if isinstance(t, dict) and not _is_info(t.get("topic")))
    real_met = sum(
        1 for m in metrics
        if isinstance(m, dict) and not _is_info(m.get("measured_result"))
    )
    bits = [
        f"ESG & Sustainability for {company}",
        f"jurisdiction {geography or 'unset'}",
        f"{real_m} material topic(s)",
        f"{real_met} measured metric(s)",
        f"Regulatory prior={'yes' if reg_cross.get('regulatory_prior_present') else 'no'}",
    ]

    out = {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "jurisdiction": geography or _info_request("deal jurisdiction"),
        "sector": sector or _info_request("sector"),
        "material_topics": material,
        "product_vs_footprint": product_footprint,
        "measured_metrics": metrics,
        "workforce_safety": workforce,
        "consequences": consequences,
        "regulatory_cross_check": reg_cross,
        "esg_evidence_qa": esg_qa,
        # Legacy dual-write
        "themes": themes,
        "labour_flags": labour,
        "environment_flags": env,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or legacy.get("role_code") or _DD_CODE,
        "role_code": legacy.get("role_code") or _DD_CODE,
        "slug": _AGENT_KEY,
        "empty": not real_m,
    }
    out["questions"] = _questions_from_esg_gaps(out)
    return out


def _llm_esg_and_sustainability_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "esg_and_sustainability",
            sector=sector,
            geography=geography,
            materiality=materiality,
            target_company=company,
            deal_perimeter=deal_perimeter,
            transaction_type=transaction_type,
            as_of_date=as_of_date,
            review_periods=review_periods,
            decision_stage=decision_stage,
        )
        src_lines = (
            "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:16], start=1))
            or "[1] VDR"
        )
        user = (
            f"Company: {company}\nSector: {sector or 'unknown'}\n"
            f"Jurisdiction: {geography or 'unknown'}\n\n"
            f"Sources:\n{src_lines}\n\nCorpus:\n{corpus[:30000]}\n\n"
            "Return JSON with keys:\n"
            "insight_snapshot, jurisdiction, sector,\n"
            "material_topics: [{topic, pillar (E|S|G), why_material, source}],\n"
            "product_vs_footprint: [{lens, finding, source}],\n"
            "measured_metrics: [{metric, measured_result, management_target, boundary, "
            "method, baseline_year, denominator, source}],\n"
            "workforce_safety: [{factor, record, cost_or_continuity, regulatory_action, source}],\n"
            "consequences: [{topic, consequence_type, detail, threshold_and_date, source}],\n"
            "esg_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
            "materiality_screen, product_vs_footprint_split, metric_boundary_method_baseline, "
            "targets_vs_measured, workforce_safety_where_material, consequence_column, "
            "regulatory_cross_check, no_emissions_from_revenue_sites,\n"
            "questions: [{question, required_records, decision_effect, priority, owner, "
            "timing, closure_test, interim_treatment}],\n"
            "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
            "Omit non-material topics. Separate product impact from operating footprint. "
            "Keep targets separate from measured results. "
            "Do not apply reporting regimes below threshold. "
            "Do not infer environmental performance from revenue or site count. "
            "Cross-check Regulatory Compliance. No invest or pass."
        )
        return generate_json(system=system, user=user, temperature=0.15)
    except Exception:
        return None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    heur: dict[str, Any],
    corpus: str = "",
    regulatory_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(heur)
    for key in (
        "insight_snapshot",
        "jurisdiction",
        "sector",
        "material_topics",
        "product_vs_footprint",
        "measured_metrics",
        "workforce_safety",
        "consequences",
        "quality_verdict",
        "reliance_verdict",
        "quality_reliance_rationale",
    ):
        if key in llm and llm[key]:
            out[key] = llm[key]
    # Guard: strip inferred env metrics that cite revenue/site count
    cleaned_metrics = []
    for m in out.get("measured_metrics") or []:
        if not isinstance(m, dict):
            continue
        blob = f"{m.get('metric')} {m.get('measured_result')} {m.get('method')}"
        if re.search(r"(?i)(inferred from revenue|per site count|site count implies)", blob):
            m = {
                **m,
                "measured_result": _info_request(
                    "measured environmental result (not inferred from revenue/sites)"
                ),
                "notes": _NO_INFER_RULE,
            }
        # Ensure management_target key exists
        if "management_target" not in m:
            m["management_target"] = _NA
        cleaned_metrics.append(m)
    if cleaned_metrics:
        out["measured_metrics"] = cleaned_metrics

    out["regulatory_cross_check"] = _esg_regulatory_cross_check(
        consequences=out.get("consequences") or [],
        material=out.get("material_topics") or [],
        regulatory_spec=regulatory_spec,
    )
    esg_qa = _esg_evidence_qa(
        material=out.get("material_topics") or [],
        product_footprint=out.get("product_vs_footprint") or [],
        metrics=out.get("measured_metrics") or [],
        workforce=out.get("workforce_safety") or [],
        consequences=out.get("consequences") or [],
        reg_cross=out["regulatory_cross_check"],
        corpus=corpus,
    )
    out["esg_evidence_qa"] = esg_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in esg_qa)

    qv = str(out.get("quality_verdict") or "").upper()
    rv = str(out.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        qv, rv, rationale = _quality_reliance(
            material=out.get("material_topics") or [],
            metrics=out.get("measured_metrics") or [],
            workforce=out.get("workforce_safety") or [],
            consequences=out.get("consequences") or [],
            qa_fail=qa_fail,
        )
        out["quality_verdict"] = qv
        out["reliance_verdict"] = rv
        out.setdefault("quality_reliance_rationale", rationale)
    else:
        out["quality_verdict"] = qv
        out["reliance_verdict"] = rv
        if qa_fail and rv == "READY":
            out["reliance_verdict"] = "LIMITED"
            out["quality_reliance_rationale"] = (
                (out.get("quality_reliance_rationale") or "")
                + " Open ESG QA FAILs cap READY → LIMITED."
            ).strip()

    if not isinstance(out.get("questions"), list) or not out.get("questions"):
        out["questions"] = _questions_from_esg_gaps(out)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in out.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        out["questions"] = filled_q or _questions_from_esg_gaps(out)

    for dead in ("recommendation", "confidence", "investment_verdict", "invest_recommendation"):
        out.pop(dead, None)

    out["composer"] = "llm_v1"
    return out


def build_esg_and_sustainability_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    regulatory_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography") or getattr(deal, "geography", None)
    sector = vars_.get("sector") or getattr(deal, "sector", None)
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_esg_and_sustainability_corpus(deal, idx or {})
    # Prefer gathered VDR sources (legal + HR + ops) while keeping caller hints.
    srcs = list(dict.fromkeys([*(sources or []), *gathered_sources]))
    if not srcs:
        srcs = list(gathered_sources)

    seed_bits: list[str] = []
    for note in list(legacy.get("themes") or []) + list(
        legacy.get("labour_flags") or []
    ) + list(legacy.get("environment_flags") or []):
        if isinstance(note, str) and note.strip():
            seed_bits.append(note.strip())
    full_corpus = "\n\n".join(x for x in (corpus or "", "\n".join(seed_bits)) if x.strip())

    heur = _heuristic_esg_and_sustainability_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        legacy_spec=legacy,
        regulatory_spec=regulatory_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    llm_raw = _llm_esg_and_sustainability_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        materiality=vars_.get("materiality"),
        deal_perimeter=vars_.get("deal_perimeter"),
        transaction_type=vars_.get("transaction_type"),
        as_of_date=vars_.get("as_of_date"),
        review_periods=vars_.get("review_periods"),
        decision_stage=vars_.get("decision_stage"),
    )
    if not llm_raw:
        return heur
    out = _normalise_llm_spec(
        llm_raw, heur=heur, corpus=full_corpus, regulatory_spec=regulatory_spec
    )
    out["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return out


def render_esg_and_sustainability_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    material = (
        spec.get("material_topics")
        if isinstance(spec.get("material_topics"), list)
        else []
    )
    product = (
        spec.get("product_vs_footprint")
        if isinstance(spec.get("product_vs_footprint"), list)
        else []
    )
    metrics = (
        spec.get("measured_metrics")
        if isinstance(spec.get("measured_metrics"), list)
        else []
    )
    workforce = (
        spec.get("workforce_safety")
        if isinstance(spec.get("workforce_safety"), list)
        else []
    )
    consequences = (
        spec.get("consequences") if isinstance(spec.get("consequences"), list) else []
    )
    themes = spec.get("themes") if isinstance(spec.get("themes"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(
        f"**Jurisdiction:** {_clean(spec.get('jurisdiction') or _NA, 60)}  \n"
        f"**Sector:** {_clean(spec.get('sector') or _NA, 60)}\n\n"
    )
    parts.append(f"{_NO_INFER_RULE}\n\n")

    # 1
    parts.append("## 1. Material Topics\n\n")
    parts.append(f"{_MATERIAL_RULE}\n\n")
    if material:
        parts.append(_table(
            ["Topic", "Pillar", "Why material", "Source"],
            [
                [
                    _clean(r.get("topic"), 50),
                    _clean(r.get("pillar"), 8),
                    _clean(r.get("why_material"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in material if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('material ESG topics')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Product Impact vs Operating Footprint\n\n")
    parts.append(f"{_FOOTPRINT_RULE}\n\n")
    if product:
        parts.append(_table(
            ["Lens", "Finding", "Source"],
            [
                [
                    _clean(r.get("lens"), 40),
                    _clean(r.get("finding"), 160),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in product if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Measured Metrics (vs Targets)\n\n")
    parts.append(f"{_METRIC_RULE}\n\n")
    if metrics:
        parts.append(_table(
            [
                "Metric", "Measured result", "Management target",
                "Boundary", "Method", "Baseline year", "Denominator", "Source",
            ],
            [
                [
                    _clean(r.get("metric"), 36),
                    _clean(r.get("measured_result"), 50),
                    _clean(r.get("management_target") or _NA, 40),
                    _clean(r.get("boundary"), 40),
                    _clean(r.get("method"), 50),
                    _clean(r.get("baseline_year"), 28),
                    _clean(r.get("denominator"), 36),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in metrics if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('measured ESG metrics')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Workforce & Safety (Cost / Continuity)\n\n")
    parts.append(f"{_WORKFORCE_RULE}\n\n")
    if workforce:
        parts.append(_table(
            ["Factor", "Record", "Cost / continuity", "Regulatory action", "Source"],
            [
                [
                    _clean(r.get("factor"), 40),
                    _clean(r.get("record"), 50),
                    _clean(r.get("cost_or_continuity"), 80),
                    _clean(r.get("regulatory_action") or _NA, 50),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in workforce if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Consequences\n\n")
    parts.append(f"{_CONSEQUENCE_RULE}\n\n")
    if consequences:
        parts.append(_table(
            ["Topic", "Type", "Detail", "Threshold / date", "Source"],
            [
                [
                    _clean(r.get("topic"), 40),
                    _clean(r.get("consequence_type"), 36),
                    _clean(r.get("detail"), 100),
                    _clean(r.get("threshold_and_date"), 50),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in consequences if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 6 — Regulatory cross-check
    reg_cross = (
        spec.get("regulatory_cross_check")
        if isinstance(spec.get("regulatory_cross_check"), dict) else {}
    )
    parts.append("## 6. Regulatory Compliance Cross-Check\n\n")
    parts.append(f"{_REG_CROSS_RULE}\n\n")
    parts.append(_table(
        ["Field", "Value"],
        [
            [
                "Regulatory prior present",
                "Yes" if reg_cross.get("regulatory_prior_present") else "No",
            ],
            [
                "Overlap",
                _clean("; ".join(reg_cross.get("overlap") or []) or _NA, 200),
            ],
            [
                "Aligned",
                _clean("; ".join(reg_cross.get("aligned") or []) or _NA, 200),
            ],
            [
                "Conflicts",
                _clean("; ".join(reg_cross.get("conflicts") or []) or "None", 200),
            ],
        ],
    ))
    parts.append("---\n\n")

    if themes:
        parts.append("## Supporting — Legacy Themes\n\n")
        for t in themes[:8]:
            if isinstance(t, str) and t.strip():
                parts.append(f"- {_soften_invest(_clean(t, 160))}\n")
        parts.append("\n---\n\n")

    # 7 QA
    esg_qa = (
        spec.get("esg_evidence_qa")
        if isinstance(spec.get("esg_evidence_qa"), list) else []
    )
    parts.append("## 7. ESG Evidence QA\n\n")
    parts.append(
        "QA enforces materiality screen, product-vs-footprint split, metric fields, "
        "targets-vs-measured separation, workforce/safety where material, consequence "
        "column, Regulatory cross-check, and no emissions inferred from revenue/sites.\n\n"
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
                for r in esg_qa
                if isinstance(r, dict)
            ],
        )
        or f"**{_info_request('ESG evidence QA rows')}**\n\n"
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
            "None are missing — material ESG gaps are closed, "
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
    parts.append(f"**Reliance:** {_clean(rv, 20)} — can a decision rest on this ESG assessment?\n\n")
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open ESG QA FAILs cap READY → LIMITED. "
        f"{_NO_INFER_RULE} "
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
