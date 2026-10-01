"""Compose DiligenceIQ Competitor Identification — named peers in-geography (prompt book).

Named competitors with geography/overlap/scale; classification; target as separate
reference; customer-choice evidence; barriers as buy/build. No invest/pass.
No OEM allowlist — extract names from the corpus only. Preserve competitors_legacy.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _fmt_num,
    _pick_sentences,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")

_CLASSIFICATIONS = (
    "direct_competitor",
    "processing_or_subcontract_partner",
    "integrated_operator",
    "substitute",
    "potential_entrant",
)

_CLASSIFICATION_LABELS = {
    "direct_competitor": "Direct competitor",
    "processing_or_subcontract_partner": "Processing / subcontract partner",
    "integrated_operator": "Integrated operator",
    "substitute": "Substitute",
    "potential_entrant": "Potential entrant",
}

_SUBSTITUTE_INHOUSE = "Customer doing nothing / in-housing"

_PLACEHOLDER_NAME = re.compile(
    r"(?i)^(?:"
    r"competitor\s*[A-Z0-9]|"
    r"peer\s*[A-Z0-9]?|"
    r"peer\s*\d+|"
    r"competitor\s*\d+|"
    r"tbd|"
    r"n/?a|"
    r"unnamed|"
    r"industry\s+average|"
    r"industry\s+avg|"
    r"average\s+peer|"
    r"placeholder|"
    r"others?|"
    r"various|"
    r"multiple\s+peers?"
    r")$",
)

_PLACEHOLDER_BLOB = re.compile(
    r"(?i)\b("
    r"competitor\s+[A-Z]|"
    r"peer\s+\d+|"
    r"competitor\s+\d+|"
    r"\bTBD\b|"
    r"industry\s+average|"
    r"placeholder\s+name"
    r")\b",
)

_COMPETITOR_CUE = re.compile(
    r"\b(competitor|compete[sd]?|rival|peer|vs\.?|versus|lost\s+(?:to|bid)|"
    r"alternative|incumbent|entrant|landscape|positioning)\b",
    re.IGNORECASE,
)
_PARTNER_CUE = re.compile(
    r"\b(subcontract|sub[- ]?contract|processing\s+partner|toll\s+process|"
    r"outsourc|white[- ]?label|contract\s+manufactur)\b",
    re.IGNORECASE,
)
_INTEGRATED_CUE = re.compile(
    r"\b(integrated\s+operator|vertically\s+integrated|full[- ]?service|"
    r"end[- ]to[- ]end|captive\s+fleet)\b",
    re.IGNORECASE,
)
_SUBSTITUTE_CUE = re.compile(
    r"\b(substitut|do(?:ing)?\s+nothing|in[- ]?hous(?:e|ing)|self[- ]?perform|"
    r"DIY|status\s+quo|no\s+change)\b",
    re.IGNORECASE,
)
_ENTRANT_CUE = re.compile(
    r"\b(potential\s+entrant|new\s+entrant|may\s+enter|could\s+enter|"
    r"expand(?:ing|s)?\s+into|planning\s+to\s+enter)\b",
    re.IGNORECASE,
)
_CUSTOMER_CHOICE_CUE = re.compile(
    r"\b(tender|RFT|RFP|RFQ|lost[- ]?bid|win[- ]?loss|CRM|"
    r"customer\s+interview|chose|selected|awarded\s+to)\b",
    re.IGNORECASE,
)
_OUT_OF_GEO = re.compile(
    r"\b(outside|out[- ]of[- ](?:market|geography|region|area)|"
    r"no\s+(?:local|regional)\s+(?:presence|operations?)|"
    r"does\s+not\s+operate\s+in|national[- ]only|"
    r"no\s+footprint\s+in)\b",
    re.IGNORECASE,
)
_NATIONAL_SCALE = re.compile(
    r"\b(national\s+(?:scale|player|leader)|pan[- ]India|nationwide|"
    r"country[- ]wide)\b",
    re.IGNORECASE,
)
_SHARE = re.compile(
    r"(?:market\s+share|share)\s*(?:of\s+)?(?:~)?"
    r"(\d{1,2}(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)
_UNITS = re.compile(
    r"(?:~|approx\.?\s*)?"
    r"([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s*(?:k|thousand|000s?)?\s*"
    r"(?:units?|vehicles?|tonnes?|loads?|sites?)\b",
    re.IGNORECASE,
)
_PRICE = re.compile(
    r"(?:flagship\s+price|ASP|priced?\s+at|list\s+price)"
    r"[^\d₹$]{0,40}?(?:INR\s*|USD\s*|₹\s*|\$)?\s*"
    r"([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_NPS = re.compile(
    r"\bNPS\b[^\d]{0,20}?(~)?(\d{1,3}(?:\.\d+)?)",
    re.IGNORECASE,
)
_TREND = re.compile(
    r"\b(Strong Gain|Steady Growth|Losing Share|Declining|Gaining|Fragmented)\b",
    re.IGNORECASE,
)
_SOFTWARE = re.compile(
    r"(?i)\b(Software\s*/\s*OTA|OTA|software\s+stack)\b[^\n.]{0,40}?"
    r"(Yes\s*\([^)]+\)|Yes|No|Basic)",
)
_PROPER_NAME = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+(?:\s+(?:of|and|the|for|&)?"
    r"\s*[A-Z][A-Za-z0-9&.\-]+){0,3})\b"
)
_BARRIER_KEYS = (
    ("route_density", ("route density", "route network", "density of routes", "coverage density")),
    ("permits_lead_time", ("permit", "licence", "license", "lead time", "authorisation", "authorization")),
    ("processing_capacity", ("processing capacity", "throughput", "plant capacity", "treatment capacity")),
    ("contracted_volumes", ("contracted volume", "contracted tonnes", "committed volume", "take-or-pay")),
    ("capital", ("capital required", "capex", "capital intensity", "upfront capital", "investment required")),
)

_UNNAMED_TOKENS = frozenset({
    "industry", "peer", "peers", "competitor", "competitors", "alternative",
    "alternatives", "market", "avg", "average", "company", "target", "the",
    "and", "or", "vs", "versus", "incumbent", "player", "players", "others",
    "various", "multiple", "local", "national", "regional",
})


def _insight(text: Any, *, max_chars: int = 520) -> str:
    body = _clean(text, max_chars)
    return f"**Insight Snapshot:** {body}\n\n" if body else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for i in range(len(headers)):
            val = row[i] if i < len(row) else "—"
            cells.append(str(val or "—").replace("|", "\\|").replace("\n", " ").strip())
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _info_request(label: str) -> str:
    return f"Information request: {label} (not stated in the data room)"


def _classification_label(key: str) -> str:
    return _CLASSIFICATION_LABELS.get(key, key.replace("_", " ").title())


def _norm_name(name: str) -> str:
    return re.sub(r"\W+", " ", (name or "").strip().lower()).strip()


def _is_placeholder_name(name: str) -> bool:
    """True for Competitor A / Peer 1 / TBD / industry average style labels."""
    n = (name or "").strip()
    if not n:
        return True
    if _PLACEHOLDER_NAME.match(n):
        return True
    if _PLACEHOLDER_BLOB.search(n) and len(n) < 40:
        return True
    toks = [t for t in re.split(r"\s+", n) if t]
    if toks and all(t.lower().rstrip(".,;:") in _UNNAMED_TOKENS for t in toks):
        return True
    return False


def _is_target_name(name: str, target: str) -> bool:
    """True when name refers to the deal target (must not sit in competitor list)."""
    n = _norm_name(name)
    t = _norm_name(target)
    if not n or not t:
        return False
    if n == t:
        return True
    if t in n or n in t:
        # Avoid matching short shared tokens (e.g. "EV" inside longer names).
        if min(len(n), len(t)) >= 4:
            return True
    return False


def _classify_row(text: str, *, name: str | None = None) -> str:
    """Pick one classification — substitute / partner / integrated / entrant / direct."""
    blob = f"{name or ''} {text or ''}"
    if name and _norm_name(name) == _norm_name(_SUBSTITUTE_INHOUSE):
        return "substitute"
    if _SUBSTITUTE_CUE.search(blob):
        return "substitute"
    if _PARTNER_CUE.search(blob):
        return "processing_or_subcontract_partner"
    if _INTEGRATED_CUE.search(blob):
        return "integrated_operator"
    if _ENTRANT_CUE.search(blob):
        return "potential_entrant"
    return "direct_competitor"


def _parse_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("%", "").replace("~", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def gather_competitor_identification_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "market_competition": 0,
        "deal_strategy": 1,
        "customer": 2,
        "company_management": 3,
        "financial": 4,
        "operations": 5,
    }
    needles = (
        "competition", "competitor", "market", "positioning", "landscape",
        "peer", "rival", "g2", "win", "loss", "tender",
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
            elif excerpt is not None:
                text = str(excerpt)
        text = _ZWSP.sub("", text)
        text = _PDF_BULLETS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


def _geo_overlap_note(
    sent: str,
    geography: str | None,
) -> tuple[str, bool]:
    """Return (geography cell, is_context_only). Out-of-geo / national≠local."""
    if _OUT_OF_GEO.search(sent):
        geo = geography or "stated geography"
        return (
            f"Out of geography vs {geo} — context only, not a local competitor {_DOC_CITE}",
            True,
        )
    if geography and _NATIONAL_SCALE.search(sent) and geography.lower() not in sent.lower():
        return (
            f"National scale noted; not automatically a local threat in {geography} {_DOC_CITE}",
            False,
        )
    if geography and geography.lower() in sent.lower():
        return f"{geography} {_DOC_CITE}", False
    return (geography or _info_request("geography served"), False)


def _candidate_names_from_sent(sent: str, target: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for m in _PROPER_NAME.finditer(sent):
        name = m.group(1).strip(" ,;.")
        if len(name) < 3 or _is_placeholder_name(name):
            continue
        if _is_target_name(name, target):
            continue
        # Drop sentence-leading noise that looks like labels.
        if name.lower() in {
            "dimension", "market share", "units sold", "flagship price",
            "competitive", "insight snapshot", "porter",
        }:
            continue
        key = _norm_name(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names[:4]


def _extract_competitive_set(
    corpus: str,
    *,
    company: str,
    geography: str | None,
) -> list[dict[str, Any]]:
    sents = _sentences(corpus)
    hits = [
        s for s in _pick_sentences(
            sents,
            keywords=(
                "competitor", "compete", "rival", "peer", "versus", "vs",
                "alternative", "entrant", "subcontract", "in-hous", "substitute",
                "lost", "tender", "landscape",
            ),
            limit=16,
        )
        if _COMPETITOR_CUE.search(s)
        or _PARTNER_CUE.search(s)
        or _SUBSTITUTE_CUE.search(s)
        or _ENTRANT_CUE.search(s)
        or _INTEGRATED_CUE.search(s)
    ]

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sent in hits:
        for name in _candidate_names_from_sent(sent, company):
            key = _norm_name(name)
            if key in seen:
                continue
            seen.add(key)
            geo, context_only = _geo_overlap_note(sent, geography)
            classification = _classify_row(sent, name=name)
            if context_only:
                # Keep as context note via classification + geography flag.
                notes = (
                    "Out-of-geography context — not counted as an in-market competitor "
                    f"{_COMPUTED}"
                )
            else:
                notes = f"Classified from corpus cues {_COMPUTED}"
            share_m = _SHARE.search(sent)
            units_m = _UNITS.search(sent)
            scale_bits: list[str] = []
            if share_m:
                scale_bits.append(f"share ~{share_m.group(1)}%")
            if units_m:
                scale_bits.append(f"~{_fmt_num(units_m.group(1))} units")
            rows.append({
                "name": name,
                "geography": geo,
                "service_overlap": (
                    _clean(sent, 140) + f" {_DOC_CITE}"
                    if re.search(r"(?i)service|overlap|same|compete|vs", sent)
                    else _info_request(f"service overlap with {name}")
                ),
                "scale": (
                    "; ".join(scale_bits) + f" {_DOC_CITE}"
                    if scale_bits
                    else _info_request(f"approximate scale for {name}")
                ),
                "trading_status": _info_request(f"trading / operating status for {name}"),
                "classification": classification,
                "source": _DOC_CITE,
                "notes": notes,
                "context_only": context_only,
                "market_share_pct": _parse_float(share_m.group(1)) if share_m else None,
                "units_000s": _parse_float(units_m.group(1)) if units_m else None,
                "flagship_price_inr": (
                    _parse_float(_PRICE.search(sent).group(1))
                    if _PRICE.search(sent)
                    else None
                ),
                "trend": (
                    _TREND.search(sent).group(1)
                    if _TREND.search(sent)
                    else None
                ),
                "nps": (
                    _parse_float(_NPS.search(sent).group(2))
                    if _NPS.search(sent)
                    else None
                ),
                "software": (
                    _SOFTWARE.search(sent).group(2)
                    if _SOFTWARE.search(sent)
                    else None
                ),
            })
            if len(rows) >= 8:
                break
        if len(rows) >= 8:
            break

    return rows


def _ensure_substitute(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has = any(
        isinstance(r, dict)
        and (
            _norm_name(str(r.get("name") or "")) == _norm_name(_SUBSTITUTE_INHOUSE)
            or (
                r.get("classification") == "substitute"
                and re.search(r"(?i)doing nothing|in[- ]?hous", str(r.get("name") or ""))
            )
        )
        for r in rows
    )
    if has:
        return rows
    out = list(rows)
    out.append({
        "name": _SUBSTITUTE_INHOUSE,
        "geography": "Customer decision — any geography",
        "service_overlap": (
            "Customer retains status quo or brings the work in-house "
            "instead of buying from the market"
        ),
        "scale": _NA,
        "trading_status": "n/a — customer behaviour, not a trading entity",
        "classification": "substitute",
        "source": _COMPUTED,
        "notes": "Always include as a substitute when missing from the competitive set",
        "context_only": False,
        "market_share_pct": None,
        "units_000s": None,
        "flagship_price_inr": None,
        "trend": None,
        "nps": None,
        "software": None,
    })
    return out


def _target_reference(
    *,
    company: str,
    corpus: str,
    geography: str | None,
) -> dict[str, str]:
    sents = _sentences(corpus)
    hits = _pick_sentences(
        sents,
        keywords=(company.split()[0].lower() if company else "company", "target", "operates"),
        limit=3,
    )
    hit = next(
        (h for h in hits if company.lower()[: min(8, len(company))] in h.lower()),
        hits[0] if hits else None,
    )
    share_m = _SHARE.search(corpus)
    return {
        "name": company,
        "geography": geography or _info_request("target operating geography"),
        "service_overlap": "Target reference — not a competitor",
        "scale": (
            f"share ~{share_m.group(1)}% {_DOC_CITE}"
            if share_m
            else _info_request("target scale / share")
        ),
        "trading_status": "Target company under diligence",
        "source": _DOC_CITE if hit else _NA,
        "notes": (
            _clean(hit, 180) + f" {_DOC_CITE}"
            if hit
            else "Shown as a separate reference row — never listed among competitors"
        ),
    }


def _customer_choice_rows(
    competitive_set: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    evidence_hits = [
        s for s in _pick_sentences(
            sents,
            keywords=("tender", "lost", "win", "CRM", "interview", "awarded", "RFP", "RFQ"),
            limit=8,
        )
        if _CUSTOMER_CHOICE_CUE.search(s)
    ]
    rows: list[dict[str, str]] = []
    for r in competitive_set:
        if not isinstance(r, dict):
            continue
        if r.get("context_only"):
            continue
        name = str(r.get("name") or "")
        if not name or name.startswith("Information"):
            continue
        hit = next(
            (h for h in evidence_hits if _norm_name(name).split()[0] in h.lower()),
            None,
        )
        if hit:
            rows.append({
                "competitor": name,
                "evidence_type": "actual_customer_choice",
                "evidence": _clean(hit, 200) + f" {_DOC_CITE}",
                "notes": "Tender / lost-bid / CRM / interview evidence present",
            })
        else:
            rows.append({
                "competitor": name,
                "evidence_type": "inferred",
                "evidence": (
                    "Competitive set inferred from landscape language — "
                    + _info_request(
                        "tender records, lost-bid notes, CRM competitor fields, "
                        "or customer interviews"
                    )
                ),
                "notes": "Request primary customer-choice evidence",
            })
        if len(rows) >= 8:
            break
    if not rows:
        rows.append({
            "competitor": _info_request("named competitor"),
            "evidence_type": "inferred",
            "evidence": _info_request(
                "tender records, lost-bid notes, CRM competitor fields, or customer interviews"
            ),
            "notes": "No customer-choice evidence in opened packs",
        })
    return rows


def _barriers_rows(corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    rows: list[dict[str, str]] = []
    for key, needles in _BARRIER_KEYS:
        label = key.replace("_", " ")
        hit = next(
            (
                s for s in _pick_sentences(sents, keywords=needles, limit=4)
                if any(n in s.lower() for n in needles)
            ),
            None,
        )
        rows.append({
            "barrier": label.title(),
            "buy_or_build": (
                "Buy (acquire density/capacity) or build (organic) — assess both paths"
            ),
            "detail": (
                _clean(hit, 200) + f" {_DOC_CITE}"
                if hit
                else _info_request(f"{label} as a barrier (buy vs build)")
            ),
            "evidence": _DOC_CITE if hit else _NA,
        })
    return rows


def _legacy_from_rows(
    competitive_set: list[dict[str, Any]],
    legacy_spec: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in competitive_set:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "").strip()
        if not name or _is_placeholder_name(name):
            continue
        if _norm_name(name) == _norm_name(_SUBSTITUTE_INHOUSE):
            continue
        if r.get("context_only"):
            continue
        key = _norm_name(name)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": name,
            "market_share_pct": r.get("market_share_pct"),
            "units_000s": r.get("units_000s"),
            "flagship_price_inr": r.get("flagship_price_inr"),
            "trend": r.get("trend"),
            "nps": r.get("nps"),
            "software": r.get("software"),
        })
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    for row in (legacy.get("competitors") or legacy.get("competitors_legacy") or [])[:8]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name or _is_placeholder_name(name):
            continue
        key = _norm_name(name)
        if key in seen:
            # Merge metrics into existing legacy row when missing.
            for existing in out:
                if _norm_name(str(existing.get("name") or "")) == key:
                    for field in (
                        "market_share_pct", "units_000s", "flagship_price_inr",
                        "trend", "nps", "software",
                    ):
                        if existing.get(field) is None and row.get(field) is not None:
                            existing[field] = row.get(field)
                    break
            continue
        seen.add(key)
        out.append({
            "name": name,
            "market_share_pct": row.get("market_share_pct"),
            "units_000s": row.get("units_000s"),
            "flagship_price_inr": row.get("flagship_price_inr"),
            "trend": row.get("trend"),
            "nps": row.get("nps"),
            "software": row.get("software"),
        })
    return out[:8]


def _positioning_notes(corpus: str, legacy_spec: dict[str, Any] | None) -> list[str]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    notes: list[str] = []
    for n in (legacy.get("positioning_notes") or [])[:4]:
        if isinstance(n, str) and n.strip() and not _PLACEHOLDER_BLOB.search(n):
            notes.append(_clean(n, 220))
    sents = _sentences(corpus)
    hits = _pick_sentences(
        sents,
        keywords=("competitive", "position", "landscape", "moat", "share", "rival"),
        limit=4,
    )
    for h in hits:
        if _PLACEHOLDER_BLOB.search(h):
            continue
        notes.append(_clean(h, 220) + f" {_DOC_CITE}")
        if len(notes) >= 3:
            break
    # Dedupe
    out: list[str] = []
    seen: set[str] = set()
    for n in notes:
        key = n.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out[:3]


def _quality_reliance(
    *,
    named_count: int,
    actual_choice: int,
    barriers_evidenced: int,
) -> tuple[str, str, str]:
    if named_count >= 1 and actual_choice >= 1:
        return (
            "PASS",
            "READY" if barriers_evidenced >= 2 else "LIMITED",
            (
                f"{named_count} named competitor(s); {actual_choice} with actual "
                f"customer-choice evidence; {barriers_evidenced} barrier(s) evidenced."
            ),
        )
    if named_count >= 1:
        return (
            "PASS",
            "LIMITED",
            "Named peers present but customer-choice evidence is mostly inferred.",
        )
    return "PASS", "BLOCKED", "No named in-geography competitors evidenced in the data room."


def _llm_competitor_identification_spec(
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
            "competitor_identification",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "target_reference: {name, geography, service_overlap, scale, trading_status, source, notes} "
        "— the target only; never place it in competitors,\n"
        "competitors: [{name, geography, service_overlap, scale, trading_status, classification, "
        "source, notes, market_share_pct, units_000s, flagship_price_inr, trend, nps, software}] "
        "— classification one of direct_competitor|processing_or_subcontract_partner|"
        "integrated_operator|substitute|potential_entrant; "
        "named legal/trading names only (no Competitor A / Peer 1 / TBD / industry average); "
        "always include substitute 'Customer doing nothing / in-housing' if missing; "
        "out-of-geography names are context not competitors; national scale ≠ local threat,\n"
        "customer_choice: [{competitor, evidence_type, evidence, notes}] "
        "— evidence_type actual_customer_choice|inferred; "
        "when inferred request tender/CRM/lost-bid evidence,\n"
        "barriers: [{barrier, buy_or_build, detail, evidence}] "
        "— cover route density, permits/lead time, processing capacity, contracted volumes, capital,\n"
        "positioning_notes: [string],\n"
        "competitors_legacy: [{name, market_share_pct, units_000s, flagship_price_inr, trend, nps, software}],\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
        "Do NOT invent OEM peer lists — extract names from the evidence only.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_competitor_identification_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra = ""
    for key in ("positioning_notes",):
        for item in (legacy.get(key) or [])[:4]:
            if isinstance(item, str) and item.strip():
                extra += "\n" + item.strip()
    for row in (legacy.get("competitors") or legacy.get("competitors_legacy") or [])[:6]:
        if isinstance(row, dict) and row.get("name"):
            extra += f"\nCompetitor {row['name']} share {row.get('market_share_pct')}"
    corpus_full = (corpus or "") + extra

    competitive_set = _extract_competitive_set(
        corpus_full, company=company, geography=geography,
    )
    # Drop target if heuristic slipped it in.
    competitive_set = [
        r for r in competitive_set
        if isinstance(r, dict) and not _is_target_name(str(r.get("name") or ""), company)
        and not _is_placeholder_name(str(r.get("name") or ""))
    ]
    competitive_set = _ensure_substitute(competitive_set)
    target_ref = _target_reference(company=company, corpus=corpus_full, geography=geography)
    choice = _customer_choice_rows(competitive_set, corpus_full)
    barriers = _barriers_rows(corpus_full)
    notes = _positioning_notes(corpus_full, legacy)
    legacy_rows = _legacy_from_rows(competitive_set, legacy)

    named = sum(
        1 for r in competitive_set
        if isinstance(r, dict)
        and r.get("name")
        and not str(r["name"]).startswith("Information")
        and _norm_name(str(r["name"])) != _norm_name(_SUBSTITUTE_INHOUSE)
        and not r.get("context_only")
    )
    actual = sum(
        1 for c in choice
        if isinstance(c, dict) and c.get("evidence_type") == "actual_customer_choice"
    )
    barriers_ok = sum(
        1 for b in barriers
        if isinstance(b, dict)
        and b.get("detail")
        and not str(b["detail"]).startswith("Information")
        and b["detail"] != _NA
    )
    quality, reliance, qr = _quality_reliance(
        named_count=named,
        actual_choice=actual,
        barriers_evidenced=barriers_ok,
    )

    insight = (
        f"Competitor Identification for {company}: {named} named peer(s) in/near "
        f"{geography or 'stated geography'}; target held as a separate reference row; "
        f"classifications applied; customer-choice "
        f"{'evidenced' if actual else 'mostly inferred'}; barriers framed as buy or build."
    )

    return {
        "insight_snapshot": insight,
        "target_reference": target_ref,
        "competitive_set": competitive_set,
        "competitors": legacy_rows,  # CompetitorRow-shaped for report consumers
        "customer_choice": choice,
        "barriers": barriers,
        "positioning_notes": notes,
        "competitors_legacy": legacy_rows,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": "Competitive Positioning Matrix",
        "dd_code": legacy.get("dd_code") or "DD-04",
        "empty": named == 0 and not legacy_rows,
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    company: str,
    sources: list[str],
    geography: str | None,
    legacy_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    for key in ("competitors", "customer_choice", "barriers", "positioning_notes", "competitors_legacy"):
        if key == "positioning_notes":
            if not isinstance(llm.get(key), list):
                llm[key] = []
        elif not isinstance(llm.get(key), list):
            llm[key] = []

    if not isinstance(llm.get("target_reference"), dict):
        llm["target_reference"] = _target_reference(
            company=company, corpus="", geography=geography,
        )
    else:
        llm["target_reference"]["name"] = company
        llm["target_reference"].setdefault(
            "notes",
            "Shown as a separate reference row — never listed among competitors",
        )

    cleaned: list[dict[str, Any]] = []
    for row in llm.get("competitors") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name or _is_placeholder_name(name) or _is_target_name(name, company):
            continue
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("name", "geography", "service_overlap", "notes", "classification")
        )
        if _OUT_OF_GEO.search(blob):
            row["notes"] = (
                (str(row.get("notes") or "") + " ").strip()
                + f" Out-of-geography context — not an in-market competitor {_COMPUTED}"
            ).strip()
            row["context_only"] = True
        ctype = str(row.get("classification") or "").strip().lower().replace(" ", "_")
        ctype = ctype.replace("-", "_")
        aliases = {
            "direct": "direct_competitor",
            "partner": "processing_or_subcontract_partner",
            "processing_partner": "processing_or_subcontract_partner",
            "subcontract": "processing_or_subcontract_partner",
            "subcontract_partner": "processing_or_subcontract_partner",
            "integrated": "integrated_operator",
            "entrant": "potential_entrant",
            "new_entrant": "potential_entrant",
        }
        ctype = aliases.get(ctype, ctype)
        if ctype not in _CLASSIFICATIONS:
            ctype = _classify_row(blob, name=name)
        row["classification"] = ctype
        if not row.get("geography"):
            row["geography"] = geography or _info_request("geography served")
        cleaned.append(row)

    cleaned = _ensure_substitute(cleaned)
    llm["competitive_set"] = cleaned
    # LLM may have put rich rows in competitors — move report shape to competitors.

    for row in llm.get("customer_choice") or []:
        if not isinstance(row, dict):
            continue
        et = str(row.get("evidence_type") or "").strip().lower().replace(" ", "_")
        if et not in {"actual_customer_choice", "inferred"}:
            if _CUSTOMER_CHOICE_CUE.search(str(row.get("evidence") or "")):
                et = "actual_customer_choice"
            else:
                et = "inferred"
        row["evidence_type"] = et
        if et == "inferred" and "Information request" not in str(row.get("evidence") or ""):
            row["evidence"] = (
                str(row.get("evidence") or "Inferred competitive set").rstrip()
                + " — "
                + _info_request(
                    "tender records, lost-bid notes, CRM competitor fields, "
                    "or customer interviews"
                )
            )

    if not llm.get("customer_choice"):
        llm["customer_choice"] = _customer_choice_rows(cleaned, "")

    if not llm.get("barriers"):
        llm["barriers"] = _barriers_rows("")

    if not llm.get("competitors_legacy"):
        llm["competitors_legacy"] = _legacy_from_rows(cleaned, legacy_spec)
    else:
        # Strip placeholders / target from legacy list.
        legacy_clean: list[dict[str, Any]] = []
        for row in llm["competitors_legacy"]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name or _is_placeholder_name(name) or _is_target_name(name, company):
                continue
            legacy_clean.append({
                "name": name,
                "market_share_pct": row.get("market_share_pct"),
                "units_000s": row.get("units_000s"),
                "flagship_price_inr": row.get("flagship_price_inr"),
                "trend": row.get("trend"),
                "nps": row.get("nps"),
                "software": row.get("software"),
            })
        llm["competitors_legacy"] = legacy_clean or _legacy_from_rows(cleaned, legacy_spec)

    notes = llm.get("positioning_notes") or []
    llm["positioning_notes"] = [
        _clean(n, 220) for n in notes if isinstance(n, str) and n.strip()
    ][:4]
    if not llm["positioning_notes"]:
        legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
        llm["positioning_notes"] = [
            _clean(n, 220)
            for n in (legacy.get("positioning_notes") or [])[:3]
            if isinstance(n, str) and n.strip()
        ]

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else "PASS"
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else "LIMITED"

    for dead in ("recommendation", "confidence", "key_conditions"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = "Competitive Positioning Matrix"
    llm["dd_code"] = "DD-04"
    # Report-safe CompetitorRow list lives on competitors; rich set on competitive_set.
    llm["competitors"] = list(llm.get("competitors_legacy") or [])
    named = sum(
        1 for r in cleaned
        if r.get("name")
        and _norm_name(str(r["name"])) != _norm_name(_SUBSTITUTE_INHOUSE)
        and not r.get("context_only")
    )
    llm["empty"] = named == 0 and not llm.get("competitors_legacy")
    return llm


def build_competitor_identification_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography")

    if corpus is None:
        gathered_corpus, gathered_sources = gather_competitor_identification_corpus(deal, idx)
        corpus = gathered_corpus
        if not sources:
            sources = gathered_sources
    sources = list(sources or [])
    if not corpus:
        bits: list[str] = []
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                name = str(doc.get("filename") or "source")
                if name not in sources:
                    sources.append(name)
        corpus = "\n".join(bits)

    if not prefer_heuristic:
        llm = _llm_competitor_identification_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=geography,
            materiality=vars_.get("materiality"),
        )
        if llm:
            return _normalise_llm_spec(
                llm,
                company=target,
                sources=sources,
                geography=geography,
                legacy_spec=legacy_spec,
            )

    return _heuristic_competitor_identification_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )


def render_competitor_identification_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    target_ref = (
        spec.get("target_reference")
        if isinstance(spec.get("target_reference"), dict)
        else {}
    )
    competitors = (
        spec.get("competitive_set")
        if isinstance(spec.get("competitive_set"), list)
        else None
    )
    if not competitors:
        # Fall back: rich rows may still be under competitors, or legacy only.
        raw = spec.get("competitors") if isinstance(spec.get("competitors"), list) else []
        if raw and isinstance(raw[0], dict) and (
            "classification" in raw[0] or "service_overlap" in raw[0] or "geography" in raw[0]
        ):
            competitors = raw
        else:
            competitors = [
                {
                    "name": r.get("name"),
                    "geography": _NA,
                    "service_overlap": _NA,
                    "scale": (
                        f"Share {r['market_share_pct']:g}%"
                        if isinstance(r, dict) and r.get("market_share_pct") is not None
                        else _NA
                    ),
                    "trading_status": (r.get("trend") if isinstance(r, dict) else None) or _NA,
                    "classification": "direct_competitor",
                    "source": _DOC_CITE,
                    "notes": "",
                }
                for r in (spec.get("competitors_legacy") or raw or [])
                if isinstance(r, dict) and r.get("name")
            ]
    choice = (
        spec.get("customer_choice")
        if isinstance(spec.get("customer_choice"), list)
        else []
    )
    barriers = spec.get("barriers") if isinstance(spec.get("barriers"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Target Reference (Not a Competitor)\n\n")
    parts.append(
        "The target is shown here only. "
        "**Never place the target in its own competitor list.**\n\n"
    )
    if target_ref:
        parts.append(_table(
            ["Name", "Geography", "Services", "Scale", "Trading Status", "Source"],
            [[
                _clean(target_ref.get("name"), 40),
                _clean(target_ref.get("geography"), 60),
                _clean(target_ref.get("service_overlap"), 80),
                _clean(target_ref.get("scale"), 60),
                _clean(target_ref.get("trading_status"), 60),
                _clean(target_ref.get("source"), 40),
            ]],
        ))
        if target_ref.get("notes"):
            parts.append(f"*{_clean(target_ref.get('notes'), 200)}*\n\n")
    parts.append("---\n\n")

    parts.append("## 2. Named Competitive Set\n\n")
    parts.append(
        "Legal or trading names operating in the same places. "
        "**Placeholder names are prohibited. National scale ≠ local threat; "
        "out-of-geography is context, not a competitor.**\n\n"
    )
    named_rows = [
        r for r in competitors
        if isinstance(r, dict)
        and r.get("name")
        and not _is_placeholder_name(str(r.get("name") or ""))
    ]
    if named_rows:
        parts.append(_table(
            [
                "Name", "Geography", "Service Overlap", "Scale",
                "Trading Status", "Source",
            ],
            [
                [
                    _clean(r.get("name"), 40),
                    _clean(r.get("geography"), 60),
                    _clean(r.get("service_overlap"), 100),
                    _clean(r.get("scale"), 60),
                    _clean(r.get("trading_status"), 50),
                    _clean(r.get("source"), 40),
                ]
                for r in named_rows
            ],
        ))
    else:
        parts.append(
            f"{_info_request('named competitors with geography and service overlap')}\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 3. Classification\n\n")
    parts.append(
        "Direct competitor · processing/subcontract partner · integrated operator · "
        "substitute (including doing nothing / in-housing) · potential entrant.\n\n"
    )
    if named_rows:
        parts.append(_table(
            ["Name", "Classification", "Notes"],
            [
                [
                    _clean(r.get("name"), 40),
                    _classification_label(str(r.get("classification") or "")),
                    _clean(r.get("notes"), 120),
                ]
                for r in named_rows
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 4. Customer Choice Evidence\n\n")
    parts.append(
        "Prefer tender records, lost-bid notes, CRM competitor fields, customer interviews. "
        "**Mark inferred where that evidence is absent and request it.**\n\n"
    )
    if choice:
        parts.append(_table(
            ["Competitor", "Evidence Type", "Evidence", "Notes"],
            [
                [
                    _clean(r.get("competitor"), 40),
                    _clean(r.get("evidence_type"), 40).replace("_", " "),
                    _clean(r.get("evidence"), 140),
                    _clean(r.get("notes"), 80),
                ]
                for r in choice if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 5. Barriers to Entry (Buy or Build)\n\n")
    parts.append(
        "Route density, permits and lead time, processing capacity, "
        "contracted volumes, capital required — framed as buy or build.\n\n"
    )
    if barriers:
        parts.append(_table(
            ["Barrier", "Buy or Build", "Detail", "Evidence"],
            [
                [
                    _clean(r.get("barrier"), 40),
                    _clean(r.get("buy_or_build"), 80),
                    _clean(r.get("detail"), 140),
                    _clean(r.get("evidence"), 40),
                ]
                for r in barriers if isinstance(r, dict)
            ],
        ))
    parts.append(
        "*This section does not recommend invest or pass. "
        "It establishes who the business actually loses deals to — named companies "
        "in the same places, not a list of industry giants.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(spec.get("quality_verdict") or "PASS", 30)],
            ["Reliance Verdict", _clean(spec.get("reliance_verdict") or "LIMITED", 30)],
            [
                "Rationale",
                _clean(
                    spec.get("quality_reliance_rationale")
                    or "Limits stated in the sections above.",
                    300,
                ),
            ],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can diligence rest on this competitive set?\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(srcs[:16], start=1):
            parts.append(f"[{i}] {_clean(name, 120)}\n")
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n\n")

    return "".join(parts)
