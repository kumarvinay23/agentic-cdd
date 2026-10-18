"""Compose DiligenceIQ Regulatory Compliance — rules that bind this business.

Permits/licences by entity and site (expiry, transfer); obligations tested
with evidence (untested ≠ compliant); litigation register from counsel/case
records (never invent); transaction implications (consents, CPs, indemnities).
Jurisdiction-real, not a generic list. Award/certification/grant ≠ compliance.

Dual-writes legacy F-04 fields (risks / restricted_activities / data_handling /
penalty_notes).

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

_DOCUMENT_TITLE = "Regulatory Compliance"
_DD_CODE = "F-04"
_AGENT_KEY = "regulatory_compliance"

_APPLY_RULE = (
    "Laws, permits, licences and consents that actually apply — by legal "
    "entity, site and activity — for this jurisdiction. Not a generic list "
    "from other sectors or countries."
)
_PERMIT_RULE = (
    "Each permit: identifier, holder, conditions, expiry, renewal status, "
    "and whether it transfers on a change of control or needs consent."
)
_OBLIGATION_RULE = (
    "For each material obligation: whether compliance was tested and what "
    "evidence supports it. Untested obligations are reported as untested, "
    "not as compliant. An award, certification or grant is not evidence of "
    "compliance."
)
_LITIGATION_RULE = (
    "Litigation and claims register from counsel correspondence and case "
    "records: matter, status, claimed amount, provision, insurance and "
    "counsel's assessment. Never invent a matter or a probability."
)
_TXN_RULE = (
    "Transaction implications: consents required, notifications, conditions "
    "precedent, and any exposure that should be indemnified."
)
_AWARD_NE_COMPLIANCE = (
    "An award, certification or grant is not evidence of compliance."
)
_COUNSEL_LETTER_RULE = (
    "A counsel letter (or equivalent counsel sign-off) closes the litigation "
    "/ claims register; absence is an open gap, not implied clearance."
)
_QUANTIFY_RULE = (
    "Quantify financial or regulatory effects only when the pack supports "
    "the figure — never invent amounts or probabilities."
)
_IP_CROSS_RULE = (
    "Cross-check IP and Technology for overlapping IP disputes and licence "
    "change-of-control; carry critical permits to Recommendations."
)
_NO_INVENT_RULE = (
    "Never invent a law, regulation from another sector/country, litigation "
    "matter, case, or probability."
)
_COUNSEL_LETTER_CUE = re.compile(
    r"(?i)\b("
    r"counsel\s+letter|legal\s+opinion|solicitor(?:s)?'?\s+letter|"
    r"external\s+counsel\s+(?:letter|opinion|sign[- ]?off)|"
    r"litigation\s+comfort\s+letter|bring[- ]down\s+letter|"
    r"counsel(?:'s)?\s+(?:sign[- ]?off|confirmation)"
    r")\b"
)

_AMOUNT_RE = re.compile(
    r"(?i)(?:USD|US\$|\$)\s*~?([\d.]+)\s*([MB])\b|"
    r"(?:INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(Cr|cr|crore)?"
)
_PERMIT_CUE = re.compile(
    r"(?i)\b("
    r"environmental\s+clearance|factory\s+licence|factory\s+license|"
    r"operating\s+(?:permit|licence|license)|trade\s+licence|"
    r"consent\s+to\s+(?:operate|establish)|CTO|CTE|"
    r"fire\s+NOC|pollution\s+control|ais\s*\d+|battery\s+safety|"
    r"import\s+(?:licence|license)|customs\s*/?\s*igcr|"
    r"gst\s+(?:registration|filing)|sebi\s+lodr|"
    r"companies\s+act\s+compliance|fame[-\s]?i{1,3}|"
    r"data\s+protection|dpdpa|ccpa|"
    r"permit|licence|license|consent"
    r")\b"
)
_STATUS_RE = re.compile(
    r"(?i)\b(compliant|obtained|active\s+proceedings?|under\s+review|"
    r"under\s+assessment|implementation\s+ongoing|generally\s+compliant|"
    r"granted|pending|expired|renewed|disputed|under\s+appeal|"
    r"pre[- ]?litigation|arbitration|negotiation|active)\b"
)
_RISK_LEVEL_RE = re.compile(r"(?i)\b(high|medium|low)\s+risk\b|\b(High|Medium|Low)\b")
_LIT_CUE = re.compile(
    r"(?i)\b("
    r"litigation|complaint|dispute|arbitration|claim|recovery\s+notice|"
    r"class\s+complaint|pre[- ]?litigation|proceedings?"
    r")\b"
)
_COC_CUE = re.compile(
    r"(?i)\b("
    r"change\s+of\s+control|consent\s+(?:required|to\s+assign)|"
    r"assignment\s+(?:consent|restriction)|notification\s+(?:to|required)|"
    r"condition\s+precedent|\bCP\b|indemnit(?:y|ies)|holdback|escrow|"
    r"transfer(?:s|able)?\s+on\s+(?:sale|change)"
    r")\b"
)
_TESTED_CUE = re.compile(
    r"(?i)\b(tested|audited|sample\s+tested|walkthrough|inspection\s+passed|"
    r"filing\s+confirmed|certificate\s+sighted|register\s+checked)\b"
)
_UNTESTED_CUE = re.compile(
    r"(?i)\b(not\s+(?:yet\s+)?(?:tested|audited|reviewed)|untested|"
    r"unable\s+to\s+test|implementation\s+ongoing|under\s+assessment|"
    r"under\s+review|access\s+not\s+provided)\b"
)
_AWARD_CUE = re.compile(
    r"(?i)\b(award|certification|accredited|grant\s+of|iso\s*\d+|"
    r"quality\s+award|industry\s+award)\b"
)
_EXPIRY_RE = re.compile(
    r"(?i)(?:expir(?:y|es|ed)|valid\s+(?:until|thru|through)|renewal\s+due)"
    r"[:\s]+([A-Za-z0-9\s,/.-]{4,40})"
)
_ENTITY_RE = re.compile(
    r"(?i)\b([A-Z][A-Za-z0-9&'.-]+(?:\s+[A-Z][A-Za-z0-9&'.-]+){0,6}\s+"
    r"(?:Limited|Ltd\.?|Inc\.?|PLC|LLC|GmbH|Private\s+Limited))\b"
)
_SITE_RE = re.compile(
    r"(?i)\b(factory|plant|site|facility|warehouse|gigafactory|"
    r"manufacturing\s+(?:unit|site)|registered\s+office)\b"
)


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("compliance evidence only — no deal verdict expressed", raw)
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _info_request(need: str) -> str:
    return f"Information request: {need}"


def _round(val: float, digits: int = 1) -> float:
    return round(float(val), digits)


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


def _window(text: str, start: int, *, radius: int = 160) -> str:
    return text[max(0, start - radius) : min(len(text), start + radius)]


def _is_info(val: Any) -> bool:
    s = str(val or "")
    return (
        not s
        or s.startswith("Information")
        or s.startswith("N/A")
        or s == _NA
    )


def _usd_m_from_match(m: re.Match[str]) -> float | None:
    if m.group(1):
        val = float(m.group(1))
        unit = (m.group(2) or "M").upper()
        return val * 1000.0 if unit.startswith("B") else val
    if m.group(3):
        inr = float(m.group(3).replace(",", ""))
        if m.group(4):
            return _round(inr * 10.0 / 83.0, 1)
        return _round(inr / 83.0, 1)
    return None


def _format_amount(window: str) -> str:
    m = _AMOUNT_RE.search(window)
    if not m:
        return _NA
    if m.group(1):
        return f"USD {m.group(1)}{m.group(2) or 'M'}"
    inr = m.group(3)
    unit = m.group(4) or ""
    return f"INR {inr} {unit}".strip()


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


def gather_regulatory_compliance_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "legal_esg": 0,
        "deal_strategy": 1,
        "company_management": 2,
        "operations": 3,
        "financial": 4,
    }
    needles = (
        "legal", "regulatory", "compliance", "licence", "license", "permit",
        "litigation", "consent", "esg", "environmental", "fame",
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
    for doc in ranked[:10]:
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
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 48_000:
            break
    return "\n\n".join(blobs), sources


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------


def _infer_geography(corpus: str, geography: str | None) -> str | None:
    if geography and str(geography).strip() and not str(geography).startswith("Information"):
        return str(geography).strip()
    low = (corpus or "").lower()
    if re.search(r"\b(india|mca|roc|sebi|gstn|moefcc|meity|cbic|fame)\b", low):
        return "India"
    if re.search(r"\b(united states|u\.s\.a?\.|sec\b|fda\b)\b", low):
        return "United States"
    if re.search(r"\b(united kingdom|u\.k\.|fca\b|companies house)\b", low):
        return "United Kingdom"
    if re.search(r"\b(european union|eu\b|gdpr)\b", low):
        return "European Union"
    return None


def _detect_entity(corpus: str, company: str) -> str:
    m = _ENTITY_RE.search(corpus)
    if m:
        return _clean(m.group(1), 80)
    if company and company.strip():
        return company.strip()
    return _info_request("legal entity holding the permits / licences")


def _detect_site(window: str) -> str:
    m = _SITE_RE.search(window)
    if m:
        # Prefer a short noun phrase around the site cue
        return _clean(_window(window, m.start(), radius=40), 60)
    if "factory" in window.lower() or "plant" in window.lower():
        return _clean(window, 60)
    return _info_request("site / facility for this permit")


def _transfer_on_coc(name: str, window: str) -> dict[str, str]:
    low = f"{name} {window}".lower()
    if _COC_CUE.search(low):
        if "consent" in low or "assign" in low:
            return {
                "transfer": "Consent required",
                "detail": "Change-of-control / assignment consent referenced near this instrument",
            }
        if "notification" in low or "notify" in low:
            return {
                "transfer": "Notification required",
                "detail": "Notification to authority / counterparty referenced",
            }
        if "transfer" in low:
            return {
                "transfer": "May transfer",
                "detail": "Transfer language present — confirm against instrument",
            }
    # Environmental clearances / factory licences often need consent
    if any(
        k in name.lower()
        for k in ("environmental clearance", "factory", "consent to operate", "cto", "cte")
    ):
        return {
            "transfer": "Likely consent / re-issuance",
            "detail": _info_request(
                "confirm whether this permit transfers on change of control or needs consent"
            ),
        }
    return {
        "transfer": _info_request("whether permit transfers on CoC or needs consent"),
        "detail": _PERMIT_RULE,
    }


def _parse_applicable_regime(
    *,
    corpus: str,
    legacy: dict[str, Any],
    geography: str | None,
    company: str,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    entity = _detect_entity(corpus, company)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Seed from legacy F-04 risk clauses (regulatory areas)
    for item in legacy.get("risks") or []:
        if not isinstance(item, dict) or not item.get("clause"):
            continue
        clause = _clean(item.get("clause"), 120)
        key = clause.lower()
        if key in seen:
            continue
        seen.add(key)
        status_m = _STATUS_RE.search(clause)
        status = _clean(status_m.group(0), 40) if status_m else _NA
        rows.append(
            {
                "instrument": clause.split("—")[0].split(" - ")[0].strip()[:80],
                "entity": entity,
                "site": _detect_site(clause),
                "activity": _clean(clause, 80),
                "jurisdiction": geography or _info_request("governing jurisdiction"),
                "pack_status": status,
                "source": _DOC_CITE,
                "notes": _APPLY_RULE,
            }
        )

    # Discover additional permit/licence cues from corpus
    for m in _PERMIT_CUE.finditer(text):
        raw = _clean(m.group(0), 60)
        key = raw.lower()
        if any(key in s or s in key for s in seen):
            continue
        # Skip bare generic "permit/licence/consent" without a typed instrument
        if key in {"permit", "licence", "license", "consent"}:
            continue
        win = _window(text, m.start(), radius=100)
        seen.add(key)
        rows.append(
            {
                "instrument": raw.title() if raw.islower() else raw,
                "entity": entity,
                "site": _detect_site(win),
                "activity": _clean(win, 100),
                "jurisdiction": geography or _info_request("governing jurisdiction"),
                "pack_status": (
                    _clean(_STATUS_RE.search(win).group(0), 40)
                    if _STATUS_RE.search(win)
                    else _NA
                ),
                "source": _DOC_CITE,
                "notes": _APPLY_RULE,
            }
        )
        if len(rows) >= 14:
            break

    if not rows:
        rows.append(
            {
                "instrument": _info_request(
                    "laws / permits / licences / consents that apply in this jurisdiction"
                ),
                "entity": entity,
                "site": _info_request("site"),
                "activity": _info_request("activity"),
                "jurisdiction": geography or _info_request("jurisdiction"),
                "pack_status": _NA,
                "source": _NA,
                "notes": _APPLY_RULE,
            }
        )
    return rows[:14]


def _build_permit_register(
    *,
    applicable: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    for row in applicable:
        if not isinstance(row, dict):
            continue
        name = str(row.get("instrument") or "")
        if _is_info(name):
            continue
        # Prefer permit-like instruments
        low = name.lower()
        is_permitish = any(
            k in low
            for k in (
                "clearance", "licence", "license", "permit", "consent", "ais",
                "fame", "gst", "registration", "lodr", "compliance", "dpdpa",
                "customs", "igcr", "ccpa", "labor", "labour", "factories",
            )
        )
        if not is_permitish:
            continue
        idx = text.lower().find(low[:24]) if low else -1
        win = _window(text, idx, radius=140) if idx >= 0 else text[:300]
        expiry_m = _EXPIRY_RE.search(win)
        expiry = _clean(expiry_m.group(1), 40) if expiry_m else _info_request(
            f"expiry / validity for '{name}'"
        )
        transfer = _transfer_on_coc(name, win)
        status = row.get("pack_status") or _NA
        renewal = (
            "Under review / renewal open"
            if isinstance(status, str)
            and any(k in status.lower() for k in ("review", "ongoing", "assessment", "pending"))
            else (
                "Current per pack"
                if isinstance(status, str)
                and any(k in status.lower() for k in ("compliant", "obtained", "granted"))
                else _info_request(f"renewal status for '{name}'")
            )
        )
        rows.append(
            {
                "identifier": name,
                "holder": row.get("entity") or _info_request("permit holder entity"),
                "site": row.get("site") or _info_request("site"),
                "conditions": _clean(row.get("activity"), 100)
                if not _is_info(row.get("activity"))
                else _info_request(f"conditions attached to '{name}'"),
                "expiry": expiry,
                "renewal_status": renewal,
                "transfer_on_coc": transfer["transfer"],
                "transfer_detail": transfer["detail"],
                "source": row.get("source") or _DOC_CITE,
                "notes": _PERMIT_RULE,
            }
        )
    if not rows:
        rows.append(
            {
                "identifier": _info_request("permit / licence identifier"),
                "holder": _info_request("holder entity"),
                "site": _info_request("site"),
                "conditions": _info_request("conditions"),
                "expiry": _info_request("expiry"),
                "renewal_status": _info_request("renewal status"),
                "transfer_on_coc": _info_request("transfer on CoC / consent needed"),
                "transfer_detail": _PERMIT_RULE,
                "source": _NA,
                "notes": _PERMIT_RULE,
            }
        )
    return rows[:12]


def _is_award_not_compliance(evidence: str) -> bool:
    return bool(_AWARD_CUE.search(evidence or "")) and not bool(
        re.search(r"(?i)\b(filing|register|permit|licence|license|consent|audit)\b", evidence or "")
    )


def _build_obligations(
    *,
    applicable: list[dict[str, Any]],
    corpus: str,
    legacy: dict[str, Any],
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in applicable:
        if not isinstance(row, dict):
            continue
        name = str(row.get("instrument") or "")
        if _is_info(name) or name.lower() in seen:
            continue
        seen.add(name.lower())
        status = str(row.get("pack_status") or "")
        idx = text.lower().find(name.lower()[:24])
        win = _window(text, idx, radius=120) if idx >= 0 else name + " " + status

        tested = "Untested"
        evidence = _info_request(f"tested evidence of compliance for '{name}'")
        # Prefer a corpus window that actually mentions a test for this obligation
        test_hit = None
        name_key = name.lower()[:28]
        for tm in _TESTED_CUE.finditer(text):
            # Forward-biased so prior award/cert language does not pollute evidence
            tw = text[tm.start() : min(len(text), tm.start() + 160)]
            if name_key and name_key.split()[0] in tw.lower():
                test_hit = tw
                break
            # Also allow match when cue sits just after the obligation name
            back = text[max(0, tm.start() - 80) : tm.start() + 80]
            if name_key and name_key.split()[0] in back.lower():
                test_hit = tw
                break
        if test_hit and not _is_award_not_compliance(test_hit):
            tested = "Tested"
            evidence = _clean(test_hit, 140)
        elif _TESTED_CUE.search(win) and not _is_award_not_compliance(win):
            tested = "Tested"
            evidence = _clean(win, 140)
        elif _UNTESTED_CUE.search(win) or any(
            k in status.lower()
            for k in ("under review", "under assessment", "implementation", "ongoing", "active")
        ):
            tested = "Untested"
            evidence = (
                f"Pack status '{status}' — not treated as tested compliance. "
                f"{_OBLIGATION_RULE}"
            )
        elif any(k in status.lower() for k in ("compliant", "obtained", "granted")):
            # Assertion in register without test evidence
            tested = "Untested"
            evidence = (
                f"Pack asserts '{status}' without evidenced test "
                f"(filing sample, certificate sighted, or audit). "
                f"Not recorded as compliant."
            )

        # Strip award/certification as false compliance when that is the only "evidence"
        if tested == "Tested" and _is_award_not_compliance(evidence):
            tested = "Untested"
            evidence = (
                f"Award/certification/grant language — "
                f"{_AWARD_NE_COMPLIANCE} Obligation remains untested."
            )
        elif tested != "Tested" and _is_award_not_compliance(win) and not test_hit:
            tested = "Untested"
            evidence = (
                f"Award/certification/grant language nearby — "
                f"{_AWARD_NE_COMPLIANCE} Obligation remains untested."
            )

        rows.append(
            {
                "obligation": name,
                "tested": tested,
                "evidence": evidence,
                "pack_status_tag": status or _NA,
                "source": row.get("source") or _DOC_CITE,
                "notes": _OBLIGATION_RULE,
            }
        )

    # Data-handling obligations from legacy
    for note in legacy.get("data_handling") or []:
        if not isinstance(note, str) or not note.strip():
            continue
        key = note.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        tested = "Untested"
        if _TESTED_CUE.search(note):
            tested = "Tested"
        rows.append(
            {
                "obligation": _clean(note, 100),
                "tested": tested,
                "evidence": (
                    _clean(note, 140)
                    if tested == "Tested"
                    else (
                        "Data-handling obligation noted — compliance not evidenced as tested"
                    )
                ),
                "pack_status_tag": _NA,
                "source": _DOC_CITE,
                "notes": _OBLIGATION_RULE,
            }
        )

    if not rows:
        rows.append(
            {
                "obligation": _info_request("material regulatory obligations"),
                "tested": "Untested",
                "evidence": _info_request("tested compliance evidence"),
                "pack_status_tag": _NA,
                "source": _NA,
                "notes": _OBLIGATION_RULE,
            }
        )
    return rows[:14]


def _build_litigation_register(
    *,
    corpus: str,
    legacy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Only from pack / counsel records — never invent a matter or probability."""
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Legacy penalty notes are the best structured litigation seeds
    for note in legacy.get("penalty_notes") or []:
        if not isinstance(note, str) or not note.strip():
            continue
        key = note.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        status_m = _STATUS_RE.search(note)
        status = (
            _clean(status_m.group(0), 40)
            if status_m
            else _NA
        )
        # Enrich status from full corpus when the penalty line omits it
        if status == _NA or status.startswith("Information"):
            matter_key = _clean(note.split("INR")[0], 40).lower()
            idx = text.lower().find(matter_key[:20]) if matter_key else -1
            if idx >= 0:
                win = _window(text, idx, radius=80)
                sm = _STATUS_RE.search(win)
                if sm:
                    status = _clean(sm.group(0), 40)
        if status == _NA:
            status = _info_request("matter status from counsel / case record")
        rows.append(
            {
                "matter": _clean(note.split("INR")[0].split("USD")[0], 100),
                "status": status,
                "claimed_amount": _format_amount(note),
                "provision": _info_request("provision / reserve for this matter"),
                "insurance": _info_request("insurance cover for this matter"),
                "counsel_assessment": _info_request(
                    "counsel's assessment (no invented probability)"
                ),
                "numeric_probability": None,
                "source": _DOC_CITE,
                "notes": _LITIGATION_RULE,
            }
        )

    # High-severity legacy risks that are clearly litigation / proceedings
    for item in legacy.get("risks") or []:
        if not isinstance(item, dict):
            continue
        clause = str(item.get("clause") or "")
        if not _LIT_CUE.search(clause) and "active" not in clause.lower():
            continue
        key = clause.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "matter": _clean(clause, 100),
                "status": (
                    _clean(_STATUS_RE.search(clause).group(0), 40)
                    if _STATUS_RE.search(clause)
                    else _info_request("matter status")
                ),
                "claimed_amount": _format_amount(clause) if _AMOUNT_RE.search(clause) else _NA,
                "provision": _info_request("provision / reserve"),
                "insurance": _info_request("insurance cover"),
                "counsel_assessment": _info_request(
                    "counsel's assessment (no invented probability)"
                ),
                "numeric_probability": None,
                "source": _DOC_CITE,
                "notes": _LITIGATION_RULE,
            }
        )

    # Corpus "Key Legal Risks & Litigation" style hits — only if amount or clear matter cue
    for m in _LIT_CUE.finditer(text):
        win = text[m.start() : min(len(text), m.start() + 180)]
        if not _AMOUNT_RE.search(win) and "complaint" not in win.lower() and "dispute" not in win.lower():
            continue
        matter = _clean(win.split("INR")[0].split("USD")[0], 100)
        key = matter.lower()[:60]
        if not matter or key in seen:
            continue
        # Avoid re-adding regulatory area labels without a matter shape
        if matter.lower() in {"litigation", "complaint", "dispute", "claim", "proceedings"}:
            continue
        seen.add(key)
        rows.append(
            {
                "matter": matter,
                "status": (
                    _clean(_STATUS_RE.search(win).group(0), 40)
                    if _STATUS_RE.search(win)
                    else _info_request("matter status from counsel / case record")
                ),
                "claimed_amount": _format_amount(win),
                "provision": _info_request("provision / reserve"),
                "insurance": _info_request("insurance cover"),
                "counsel_assessment": _info_request(
                    "counsel's assessment (no invented probability)"
                ),
                "numeric_probability": None,
                "source": _DOC_CITE,
                "notes": _LITIGATION_RULE,
            }
        )
        if len(rows) >= 10:
            break

    if not rows:
        rows.append(
            {
                "matter": _info_request(
                    "litigation / claims matters from counsel correspondence or case records"
                ),
                "status": _NA,
                "claimed_amount": _NA,
                "provision": _NA,
                "insurance": _NA,
                "counsel_assessment": _NA,
                "numeric_probability": None,
                "source": _NA,
                "notes": _LITIGATION_RULE,
            }
        )
    return rows[:10]


def _build_transaction_implications(
    *,
    permits: list[dict[str, Any]],
    litigation: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []

    # Consents from permits — only when transfer is evidenced, not an info request
    for p in permits:
        if not isinstance(p, dict) or _is_info(p.get("identifier")):
            continue
        transfer = str(p.get("transfer_on_coc") or "")
        if _is_info(transfer):
            continue
        low = transfer.lower()
        if any(k in low for k in ("consent", "notification", "re-issuance", "likely", "may transfer")):
            rows.append(
                {
                    "implication": "Consent / notification",
                    "detail": (
                        f"{p.get('identifier')}: {p.get('transfer_on_coc')} — "
                        f"{p.get('transfer_detail')}"
                    ),
                    "protection": "Condition precedent and/or undertaking to obtain consent",
                    "source": p.get("source") or _DOC_CITE,
                    "notes": _TXN_RULE,
                }
            )

    # Indemnities for active / high litigation
    for lit in litigation:
        if not isinstance(lit, dict) or _is_info(lit.get("matter")):
            continue
        status = str(lit.get("status") or "").lower()
        amount = lit.get("claimed_amount")
        if any(
            k in status
            for k in ("active", "disputed", "appeal", "arbitration", "pre-litigation", "negotiation")
        ) or (amount and not _is_info(amount)):
            rows.append(
                {
                    "implication": "Indemnity / escrow candidate",
                    "detail": (
                        f"{lit.get('matter')} — status {lit.get('status')}; "
                        f"claimed {lit.get('claimed_amount')}"
                    ),
                    "protection": "Specific indemnity and/or escrow / holdback",
                    "source": lit.get("source") or _DOC_CITE,
                    "notes": _TXN_RULE,
                }
            )

    # Generic CoC cues in corpus
    for m in _COC_CUE.finditer(text):
        win = _clean(text[m.start() : m.start() + 140], 140)
        if any(win[:40].lower() in str(r.get("detail") or "").lower() for r in rows):
            continue
        kind = "Consent / notification"
        protection = "Condition precedent"
        low = win.lower()
        if "indemnit" in low or "escrow" in low or "holdback" in low:
            kind = "Indemnity / escrow"
            protection = "Specific indemnity / escrow / holdback"
        elif "condition precedent" in low or re.search(r"\bcp\b", low):
            kind = "Condition precedent"
            protection = "Condition precedent"
        rows.append(
            {
                "implication": kind,
                "detail": win,
                "protection": protection,
                "source": _DOC_CITE,
                "notes": _TXN_RULE,
            }
        )
        if len(rows) >= 12:
            break

    if not rows:
        rows.append(
            {
                "implication": _info_request(
                    "transaction consents, notifications, CPs, and indemnities"
                ),
                "detail": _TXN_RULE,
                "protection": _info_request("CP / indemnity / escrow"),
                "source": _NA,
                "notes": _TXN_RULE,
            }
        )
    return rows[:12]


def _legacy_dual_write(
    *,
    legacy: dict[str, Any],
    obligations: list[dict[str, Any]],
    litigation: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    risks = [
        r for r in (legacy.get("risks") or [])
        if isinstance(r, dict)
    ]
    # If legacy empty, synthesise mild dual-write from obligations (no invented severity)
    if not risks:
        for ob in obligations[:8]:
            if not isinstance(ob, dict) or _is_info(ob.get("obligation")):
                continue
            sev = 3
            tested = str(ob.get("tested") or "")
            if tested == "Untested":
                sev = 4
            risks.append(
                {
                    "clause": ob.get("obligation"),
                    "severity": sev,
                    "mitigant": "Counsel review — untested ≠ compliant"
                    if tested == "Untested"
                    else "Monitor in legal DD",
                }
            )

    restricted = [
        r for r in (legacy.get("restricted_activities") or [])
        if isinstance(r, str) and r.strip()
    ]
    data_handling = [
        d for d in (legacy.get("data_handling") or [])
        if isinstance(d, str) and d.strip()
    ]
    penalties = [
        p for p in (legacy.get("penalty_notes") or [])
        if isinstance(p, str) and p.strip()
    ]
    if not penalties:
        for lit in litigation[:6]:
            if not isinstance(lit, dict) or _is_info(lit.get("matter")):
                continue
            bit = f"{lit.get('matter')} {lit.get('claimed_amount') or ''} {lit.get('status') or ''}"
            penalties.append(_clean(bit, 160))
    return risks[:16], restricted[:12], data_handling[:8], penalties[:12]


def _counsel_letter_status(corpus: str) -> dict[str, str]:
    text = _prose(corpus)
    m = _COUNSEL_LETTER_CUE.search(text)
    if m:
        win = _clean(_window(text, m.start(), radius=100), 160)
        return {
            "status": "CLOSED",
            "detail": f"{win} {_DOC_CITE}",
            "notes": _COUNSEL_LETTER_RULE,
        }
    return {
        "status": "OPEN",
        "detail": _info_request(
            "counsel letter / legal opinion closing the litigation register"
        ),
        "notes": _COUNSEL_LETTER_RULE,
    }


def _quantified_effects(
    *,
    litigation: list[dict[str, Any]],
    txn: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Only rows with pack-supported amounts — never invent."""
    rows: list[dict[str, str]] = []
    for lit in litigation:
        if not isinstance(lit, dict) or _is_info(lit.get("matter")):
            continue
        amount = lit.get("claimed_amount")
        if _is_info(amount):
            continue
        rows.append({
            "effect": f"Claimed exposure — {lit.get('matter')}",
            "amount": str(amount),
            "basis": f"status {lit.get('status')}; {_QUANTIFY_RULE}",
            "source": str(lit.get("source") or _DOC_CITE),
        })
    for t in txn:
        if not isinstance(t, dict) or _is_info(t.get("implication")):
            continue
        detail = str(t.get("detail") or "")
        if not _AMOUNT_RE.search(detail):
            continue
        rows.append({
            "effect": str(t.get("implication")),
            "amount": _format_amount(detail),
            "basis": f"{_clean(detail, 120)}; {_QUANTIFY_RULE}",
            "source": str(t.get("source") or _DOC_CITE),
        })
    if not rows:
        rows.append({
            "effect": _info_request("quantified regulatory / litigation effects"),
            "amount": _NA,
            "basis": _QUANTIFY_RULE,
            "source": _NA,
        })
    return rows[:8]


def _critical_permits_for_recommendations(
    permits: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Permits with CoC / consent / expiry risk — carried to Recommendations."""
    out: list[dict[str, str]] = []
    for p in permits:
        if not isinstance(p, dict) or _is_info(p.get("identifier")):
            continue
        transfer = str(p.get("transfer_on_coc") or "").lower()
        expiry = str(p.get("expiry") or "").lower()
        critical = any(
            k in transfer
            for k in ("consent", "notification", "re-issuance", "not transferable")
        ) or any(k in expiry for k in ("expir", "due", "pending"))
        if not critical and _is_info(p.get("transfer_on_coc")):
            # Unknown CoC still material for Recommendations
            critical = True
        if not critical:
            continue
        out.append({
            "permit": str(p.get("identifier")),
            "holder": str(p.get("holder") or _NA),
            "transfer_on_coc": str(p.get("transfer_on_coc") or _NA),
            "expiry": str(p.get("expiry") or _NA),
            "recommendation_action": (
                f"Condition precedent / consent: {p.get('identifier')} "
                f"({p.get('transfer_on_coc') or 'CoC status open'})"
            ),
            "source": str(p.get("source") or _DOC_CITE),
            "notes": _IP_CROSS_RULE,
        })
    return out[:8]


def _ip_cross_check(
    *,
    litigation: list[dict[str, Any]],
    ip_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    present = isinstance(ip_spec, dict) and bool(ip_spec)
    aligned: list[str] = []
    conflicts: list[str] = []
    ip_matters: list[str] = []

    for lit in litigation:
        if not isinstance(lit, dict) or _is_info(lit.get("matter")):
            continue
        matter = str(lit.get("matter") or "")
        if re.search(r"(?i)\b(ip|patent|trade\s*mark|copyright|design)\b", matter):
            ip_matters.append(_clean(matter, 80))

    if present:
        ip_assets = ip_spec.get("asset_map") or ip_spec.get("assets") or []
        ip_disputes = (
            ip_spec.get("disputes")
            or ip_spec.get("litigation")
            or ip_spec.get("ip_disputes")
            or []
        )
        if ip_matters and (ip_assets or ip_disputes):
            aligned.append(
                f"{len(ip_matters)} IP-tagged litigation matter(s) visible to IP prior"
            )
        elif ip_matters and not ip_disputes:
            conflicts.append(
                "Regulatory pack cites IP litigation but IP agent has no matching dispute rows"
            )
        elif not ip_matters and ip_disputes:
            aligned.append("IP prior present; no overlapping IP litigation in RC pack")
        else:
            aligned.append("IP prior present; no IP litigation overlap flagged")
    else:
        conflicts.append("IP and Technology prior not available for cross-check")

    return {
        "ip_prior_present": present,
        "ip_litigation_in_rc": ip_matters[:4],
        "aligned": aligned,
        "conflicts": conflicts,
        "notes": _IP_CROSS_RULE,
    }


def _rc_evidence_qa(
    *,
    applicable: list[dict[str, Any]],
    permits: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
    litigation: list[dict[str, Any]],
    counsel_letter: dict[str, Any],
    quantified: list[dict[str, Any]],
    ip_cross: dict[str, Any],
    geography: str | None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    real_app = [
        r for r in applicable
        if isinstance(r, dict) and not _is_info(r.get("instrument"))
    ]
    entity_site = any(
        (not _is_info(r.get("entity")) or not _is_info(r.get("site")))
        for r in real_app
    ) if real_app else False
    rows.append({
        "check": "obligation_register_entity_site",
        "status": "PASS" if real_app and (entity_site or geography) else "FAIL",
        "finding": (
            f"{len(real_app)} applicable instrument(s) with entity/site/jurisdiction cues"
            if real_app and (entity_site or geography)
            else _info_request("obligation / regime register by entity, site, activity")
        ),
        "action": _APPLY_RULE,
    })

    real_permits = [
        p for p in permits
        if isinstance(p, dict) and not _is_info(p.get("identifier"))
    ]
    coc_ok = all(
        not _is_info(p.get("transfer_on_coc"))
        and not _is_info(p.get("expiry"))
        for p in real_permits
    ) if real_permits else False
    rows.append({
        "check": "permit_coc_fields",
        "status": "PASS" if real_permits and coc_ok else "FAIL",
        "finding": (
            f"{len(real_permits)} permit(s) with expiry + CoC/transfer fields"
            if real_permits and coc_ok
            else _info_request("permit identifier, expiry, renewal, transfer-on-CoC")
        ),
        "action": _PERMIT_RULE,
    })

    real_lit = [
        l for l in litigation
        if isinstance(l, dict) and not _is_info(l.get("matter"))
    ]
    lit_fields_ok = all(
        l.get("numeric_probability") is None
        and (not _is_info(l.get("status")) or not _is_info(l.get("claimed_amount")))
        for l in real_lit
    ) if real_lit else False
    # Empty register with info request is FAIL (no pack evidence)
    rows.append({
        "check": "litigation_register_fields",
        "status": "PASS" if real_lit and lit_fields_ok else "FAIL",
        "finding": (
            f"{len(real_lit)} matter(s); no invented probabilities"
            if real_lit and lit_fields_ok
            else _info_request(
                "litigation register (matter, status, amount, provision, insurance, counsel)"
            )
        ),
        "action": _LITIGATION_RULE,
    })

    counsel_ok = str(counsel_letter.get("status") or "") == "CLOSED"
    rows.append({
        "check": "counsel_letter_closure",
        "status": "PASS" if counsel_ok else "FAIL",
        "finding": (
            counsel_letter.get("detail")
            if counsel_ok
            else _info_request("counsel letter closing litigation / claims")
        ),
        "action": _COUNSEL_LETTER_RULE,
    })

    quant_ok = any(
        isinstance(r, dict) and not _is_info(r.get("amount"))
        for r in quantified
    )
    # PASS if either quantified with support OR explicitly no inventable amounts
    invent_violation = any(
        isinstance(r, dict)
        and r.get("numeric_probability") not in (None, "", _NA)
        for r in litigation
        if isinstance(r, dict)
    )
    rows.append({
        "check": "quantify_only_when_supported",
        "status": "PASS" if (quant_ok or real_lit) and not invent_violation else "FAIL",
        "finding": (
            "Quantified effects limited to pack-supported amounts; no invented probabilities"
            if (quant_ok or real_lit) and not invent_violation
            else _info_request("supported quantified effects (or confirm none)")
        ),
        "action": _QUANTIFY_RULE,
    })

    ip_ok = bool(ip_cross.get("ip_prior_present")) and not ip_cross.get("conflicts")
    # Soft PASS when IP prior present even with informational conflicts? Plan says cross-check IP.
    # FAIL only when prior missing OR hard conflict about unmatched IP litigation.
    hard_conflict = any(
        "no matching" in str(c).lower() for c in (ip_cross.get("conflicts") or [])
    )
    rows.append({
        "check": "ip_cross_check",
        "status": "PASS" if ip_ok or (ip_cross.get("ip_prior_present") and not hard_conflict) else "FAIL",
        "finding": (
            "; ".join(ip_cross.get("aligned") or []) or "IP cross-check complete"
            if ip_cross.get("ip_prior_present") and not hard_conflict
            else (
                "; ".join(ip_cross.get("conflicts") or [])
                or _info_request("IP and Technology prior for cross-check")
            )
        ),
        "action": _IP_CROSS_RULE,
    })

    # Invented laws / cases / probabilities
    untested_marked_compliant = any(
        isinstance(o, dict)
        and str(o.get("tested") or "") == "Untested"
        and re.search(r"(?i)\bcompliant\b", str(o.get("evidence") or ""))
        and "not" not in str(o.get("evidence") or "").lower()
        for o in obligations
    )
    invent_ok = (
        not invent_violation
        and not untested_marked_compliant
        and all(
            isinstance(l, dict) and l.get("numeric_probability") is None
            for l in litigation
            if isinstance(l, dict) and not _is_info(l.get("matter"))
        )
    )
    rows.append({
        "check": "no_invented_laws_cases_probabilities",
        "status": "PASS" if invent_ok else "FAIL",
        "finding": (
            "No invented probabilities; untested not treated as compliant"
            if invent_ok
            else "Invented probability / untested-as-compliant detected — rework"
        ),
        "action": _NO_INVENT_RULE,
    })
    return rows


def _questions_from_rc_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("rc_evidence_qa")
        if isinstance(spec.get("rc_evidence_qa"), list) else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("obligation_register_entity_site"):
        out.append(normalize_question({
            "question": "Complete obligation / regime register by entity, site and activity",
            "required_records": "Legal entity chart + site list + licence schedule",
            "decision_effect": "Generic lists inflate compliance and miss site-level gaps",
            "priority": "mandatory_pre_decision",
            "owner": "regulatory counsel",
            "timing": "before IC",
            "closure_test": "obligation_register_entity_site QA PASS",
            "interim_treatment": "LIMITED — do not treat regime as complete",
        }))
    if _qa_fail("permit_coc_fields"):
        out.append(normalize_question({
            "question": "Complete permit register fields (expiry, renewal, transfer-on-CoC)",
            "required_records": "Permit / licence originals + CoC schedules",
            "decision_effect": "Unknown CoC can block completion or force re-issuance",
            "priority": "mandatory_pre_decision",
            "owner": "regulatory counsel",
            "timing": "before signing",
            "closure_test": "permit_coc_fields QA PASS",
            "interim_treatment": "LIMITED — assume CoC consent may be required",
        }))
    if _qa_fail("litigation_register_fields"):
        out.append(normalize_question({
            "question": "Build litigation register from counsel / case records (no invented matters)",
            "required_records": "Counsel correspondence + case dockets + provisions",
            "decision_effect": "Unlisted claims corrupt indemnity / escrow sizing",
            "priority": "mandatory_pre_decision",
            "owner": "litigation counsel",
            "timing": "before IC",
            "closure_test": "litigation_register_fields QA PASS",
            "interim_treatment": "BLOCKED — do not invent matters or probabilities",
        }))
    if _qa_fail("counsel_letter_closure"):
        out.append(normalize_question({
            "question": "Obtain counsel letter / legal opinion closing the litigation register",
            "required_records": "External counsel letter or equivalent sign-off",
            "decision_effect": "Without counsel closure, claims completeness is unproven",
            "priority": "signing_condition",
            "owner": "buyer counsel",
            "timing": "before signing / completion",
            "closure_test": "counsel_letter_closure QA PASS",
            "interim_treatment": "LIMITED — treat litigation register as open",
        }))
    if _qa_fail("quantify_only_when_supported"):
        out.append(normalize_question({
            "question": "Supply supported quantified effects (or confirm none) — no invented figures",
            "required_records": "Claim notices + provisions + insurance schedules",
            "decision_effect": "Invented amounts mis-size indemnities and price chips",
            "priority": "signing_condition",
            "owner": "financial / litigation counsel",
            "timing": "per deal timetable",
            "closure_test": "quantify_only_when_supported QA PASS",
            "interim_treatment": "REWORK — strip unsupported figures",
        }))
    if _qa_fail("ip_cross_check"):
        out.append(normalize_question({
            "question": "Supply IP and Technology output and reconcile overlapping IP disputes / CoC",
            "required_records": "IP agent spec + IP litigation / licence schedules",
            "decision_effect": "IP disputes may be double-counted or missed across agents",
            "priority": "signing_condition",
            "owner": "IP / regulatory counsel",
            "timing": "per deal timetable",
            "closure_test": "ip_cross_check QA PASS",
            "interim_treatment": "LIMITED until IP cross-check complete",
        }))
    if _qa_fail("no_invented_laws_cases_probabilities"):
        out.append(normalize_question({
            "question": "Remove invented laws, cases or probabilities; keep untested ≠ compliant",
            "required_records": "Jurisdiction-real instruments + counsel records only",
            "decision_effect": "Invented items corrupt underwriting and Recommendations",
            "priority": "mandatory_pre_decision",
            "owner": "regulatory counsel",
            "timing": "before IC",
            "closure_test": "no_invented_laws_cases_probabilities QA PASS",
            "interim_treatment": "REWORK — strip invented content",
        }))
    return out


def _quality_reliance(
    *,
    permits: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
    litigation: list[dict[str, Any]],
    geography: str | None,
    qa_fail: bool = False,
    counsel_open: bool = False,
) -> tuple[str, str, str]:
    real_permits = [
        p for p in permits
        if isinstance(p, dict) and not _is_info(p.get("identifier"))
    ]
    tested = [
        o for o in obligations
        if isinstance(o, dict) and str(o.get("tested") or "") == "Tested"
    ]
    untested = [
        o for o in obligations
        if isinstance(o, dict)
        and str(o.get("tested") or "") == "Untested"
        and not _is_info(o.get("obligation"))
    ]
    real_lit = [
        l for l in litigation
        if isinstance(l, dict) and not _is_info(l.get("matter"))
    ]

    if real_permits and (tested or untested):
        quality = "PASS"
    else:
        quality = "REWORK"

    if real_permits and (tested or untested):
        reliance = "READY"
    elif real_permits or real_lit:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    if counsel_open and reliance == "READY":
        reliance = "LIMITED"
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"

    bits = [
        f"Jurisdiction focus: {geography or 'not set'}",
        f"{len(real_permits)} permit/licence row(s)",
        f"{len(tested)} obligation(s) tested, {len(untested)} untested (untested ≠ compliant)",
        f"{len(real_lit)} litigation/claim matter(s) from pack",
        _AWARD_NE_COMPLIANCE,
    ]
    if counsel_open:
        bits.append("Counsel letter OPEN — litigation closure incomplete")
    if qa_fail:
        bits.append("Open regulatory QA FAILs cap READY → LIMITED")
    return quality, reliance, _soften_invest(". ".join(bits) + ".")


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_regulatory_compliance_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    ip_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    geography = _infer_geography(corpus, geography)
    applicable = _parse_applicable_regime(
        corpus=corpus,
        legacy=legacy,
        geography=geography,
        company=company,
    )
    permits = _build_permit_register(applicable=applicable, corpus=corpus)
    obligations = _build_obligations(
        applicable=applicable, corpus=corpus, legacy=legacy
    )
    litigation = _build_litigation_register(corpus=corpus, legacy=legacy)
    txn = _build_transaction_implications(
        permits=permits, litigation=litigation, corpus=corpus
    )
    counsel_letter = _counsel_letter_status(corpus)
    quantified = _quantified_effects(litigation=litigation, txn=txn)
    critical_permits = _critical_permits_for_recommendations(permits)
    ip_cross = _ip_cross_check(litigation=litigation, ip_spec=ip_spec)
    risks, restricted, data_handling, penalties = _legacy_dual_write(
        legacy=legacy, obligations=obligations, litigation=litigation
    )

    rc_qa = _rc_evidence_qa(
        applicable=applicable,
        permits=permits,
        obligations=obligations,
        litigation=litigation,
        counsel_letter=counsel_letter,
        quantified=quantified,
        ip_cross=ip_cross,
        geography=geography,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in rc_qa)
    counsel_open = str(counsel_letter.get("status") or "") != "CLOSED"

    quality, reliance, rationale = _quality_reliance(
        permits=permits,
        obligations=obligations,
        litigation=litigation,
        geography=geography,
        qa_fail=qa_fail,
        counsel_open=counsel_open,
    )

    real_p = sum(1 for p in permits if isinstance(p, dict) and not _is_info(p.get("identifier")))
    real_u = sum(
        1 for o in obligations
        if isinstance(o, dict)
        and str(o.get("tested") or "") == "Untested"
        and not _is_info(o.get("obligation"))
    )
    real_t = sum(
        1 for o in obligations
        if isinstance(o, dict) and str(o.get("tested") or "") == "Tested"
    )
    real_l = sum(1 for l in litigation if isinstance(l, dict) and not _is_info(l.get("matter")))
    bits = [
        f"Regulatory Compliance for {company}",
        f"jurisdiction {geography or 'unset'}",
        f"{real_p} permit/licence row(s)",
        f"{real_t} tested / {real_u} untested obligation(s)",
        f"{real_l} litigation matter(s)",
        f"counsel letter {counsel_letter.get('status')}",
    ]

    out = {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "jurisdiction": geography or _info_request("deal jurisdiction"),
        "applicable_regime": applicable,
        "permit_register": permits,
        "obligations": obligations,
        "litigation_register": litigation,
        "transaction_implications": txn,
        "counsel_letter": counsel_letter,
        "quantified_effects": quantified,
        "critical_permits": critical_permits,
        "ip_cross_check": ip_cross,
        "rc_evidence_qa": rc_qa,
        # Legacy F-04 dual-write
        "risks": risks,
        "restricted_activities": restricted,
        "data_handling": data_handling,
        "penalty_notes": penalties,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or legacy.get("role_code") or _DD_CODE,
        "role_code": legacy.get("role_code") or _DD_CODE,
        "slug": _AGENT_KEY,
        "empty": not real_p and not real_l,
    }
    out["questions"] = _questions_from_rc_gaps(out)
    return out


def _llm_regulatory_compliance_spec(
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
            "regulatory_compliance",
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
            f"Company: {company}\nJurisdiction: {geography or 'unknown'}\n\n"
            f"Sources:\n{src_lines}\n\n"
            f"Corpus:\n{corpus[:30000]}\n\n"
            "Return JSON with keys:\n"
            "insight_snapshot, jurisdiction,\n"
            "applicable_regime: [{instrument, entity, site, activity, jurisdiction, "
            "pack_status, source}],\n"
            "permit_register: [{identifier, holder, site, conditions, expiry, "
            "renewal_status, transfer_on_coc, transfer_detail, source}],\n"
            "obligations: [{obligation, tested (Tested|Untested), evidence, source}],\n"
            "litigation_register: [{matter, status, claimed_amount, provision, insurance, "
            "counsel_assessment, numeric_probability (always null unless evidenced), source}],\n"
            "counsel_letter: {status (CLOSED|OPEN), detail, notes},\n"
            "quantified_effects: [{effect, amount, basis, source}] "
            "(only pack-supported amounts),\n"
            "critical_permits: [{permit, holder, transfer_on_coc, expiry, "
            "recommendation_action, source}],\n"
            "transaction_implications: [{implication, detail, protection, source}],\n"
            "rc_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
            "obligation_register_entity_site, permit_coc_fields, litigation_register_fields, "
            "counsel_letter_closure, quantify_only_when_supported, ip_cross_check, "
            "no_invented_laws_cases_probabilities,\n"
            "questions: [{question, required_records, decision_effect, priority, owner, "
            "timing, closure_test, interim_treatment}],\n"
            "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
            "Untested ≠ compliant. Award/certification/grant ≠ compliance evidence. "
            "Never invent litigation, laws, cases or probabilities. No invest or pass. "
            "Do not list regulations from other sectors or countries. "
            "Counsel letter closes the litigation register."
        )
        return generate_json(system=system, user=user, temperature=0.15)
    except Exception:
        return None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    heur: dict[str, Any],
    corpus: str = "",
    ip_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(heur)
    for key in (
        "insight_snapshot",
        "jurisdiction",
        "applicable_regime",
        "permit_register",
        "obligations",
        "litigation_register",
        "transaction_implications",
        "counsel_letter",
        "quantified_effects",
        "critical_permits",
        "quality_verdict",
        "reliance_verdict",
        "quality_reliance_rationale",
    ):
        if key in llm and llm[key]:
            out[key] = llm[key]
    # Never allow invented numeric probabilities
    for row in out.get("litigation_register") or []:
        if isinstance(row, dict):
            row["numeric_probability"] = None
    # Force award-adjacent "Tested" back to Untested when evidence is award-only
    for row in out.get("obligations") or []:
        if not isinstance(row, dict):
            continue
        if _is_award_not_compliance(str(row.get("evidence") or "")):
            row["tested"] = "Untested"
            row["evidence"] = (
                f"{row.get('evidence')} — {_AWARD_NE_COMPLIANCE}"
            )

    if not isinstance(out.get("counsel_letter"), dict) or not out.get("counsel_letter"):
        out["counsel_letter"] = _counsel_letter_status(corpus) if corpus else heur.get(
            "counsel_letter"
        )
    out["ip_cross_check"] = _ip_cross_check(
        litigation=out.get("litigation_register") or [],
        ip_spec=ip_spec,
    )
    if not out.get("quantified_effects"):
        out["quantified_effects"] = _quantified_effects(
            litigation=out.get("litigation_register") or [],
            txn=out.get("transaction_implications") or [],
        )
    if not out.get("critical_permits"):
        out["critical_permits"] = _critical_permits_for_recommendations(
            out.get("permit_register") or []
        )

    rc_qa = _rc_evidence_qa(
        applicable=out.get("applicable_regime") or [],
        permits=out.get("permit_register") or [],
        obligations=out.get("obligations") or [],
        litigation=out.get("litigation_register") or [],
        counsel_letter=out.get("counsel_letter") or {},
        quantified=out.get("quantified_effects") or [],
        ip_cross=out.get("ip_cross_check") or {},
        geography=str(out.get("jurisdiction") or "") or None,
    )
    out["rc_evidence_qa"] = rc_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in rc_qa)
    counsel_open = str((out.get("counsel_letter") or {}).get("status") or "") != "CLOSED"

    qv = str(out.get("quality_verdict") or "").upper()
    rv = str(out.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        qv, rv, rationale = _quality_reliance(
            permits=out.get("permit_register") or [],
            obligations=out.get("obligations") or [],
            litigation=out.get("litigation_register") or [],
            geography=str(out.get("jurisdiction") or "") or None,
            qa_fail=qa_fail,
            counsel_open=counsel_open,
        )
        out["quality_verdict"] = qv
        out["reliance_verdict"] = rv
        out.setdefault("quality_reliance_rationale", rationale)
    else:
        out["quality_verdict"] = qv
        out["reliance_verdict"] = rv
        if (qa_fail or counsel_open) and rv == "READY":
            out["reliance_verdict"] = "LIMITED"
            out["quality_reliance_rationale"] = (
                (out.get("quality_reliance_rationale") or "")
                + " Open regulatory QA FAILs / counsel letter OPEN cap READY → LIMITED."
            ).strip()

    if not isinstance(out.get("questions"), list) or not out.get("questions"):
        out["questions"] = _questions_from_rc_gaps(out)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in out.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        out["questions"] = filled_q or _questions_from_rc_gaps(out)

    for dead in ("recommendation", "confidence", "investment_verdict", "invest_recommendation"):
        out.pop(dead, None)

    out["composer"] = "llm_v1"
    return out


def build_regulatory_compliance_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    ip_spec: dict[str, Any] | None = None,
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
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_regulatory_compliance_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources

    # Seed corpus from legacy so heuristic has anchors when VDR text is thin
    seed_bits: list[str] = []
    for item in legacy.get("risks") or []:
        if isinstance(item, dict) and item.get("clause"):
            seed_bits.append(str(item["clause"]))
    for note in list(legacy.get("penalty_notes") or []) + list(
        legacy.get("data_handling") or []
    ) + list(legacy.get("restricted_activities") or []):
        if isinstance(note, str) and note.strip():
            seed_bits.append(note.strip())
    full_corpus = "\n\n".join(x for x in (corpus or "", "\n".join(seed_bits)) if x.strip())

    heur = _heuristic_regulatory_compliance_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        geography=str(geography) if geography else None,
        legacy_spec=legacy,
        ip_spec=ip_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    llm_raw = _llm_regulatory_compliance_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=vars_.get("sector"),
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
        llm_raw, heur=heur, corpus=full_corpus, ip_spec=ip_spec
    )
    out["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return out


def render_regulatory_compliance_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    applicable = (
        spec.get("applicable_regime")
        if isinstance(spec.get("applicable_regime"), list)
        else []
    )
    permits = (
        spec.get("permit_register")
        if isinstance(spec.get("permit_register"), list)
        else []
    )
    obligations = (
        spec.get("obligations") if isinstance(spec.get("obligations"), list) else []
    )
    litigation = (
        spec.get("litigation_register")
        if isinstance(spec.get("litigation_register"), list)
        else []
    )
    txn = (
        spec.get("transaction_implications")
        if isinstance(spec.get("transaction_implications"), list)
        else []
    )
    risks = spec.get("risks") if isinstance(spec.get("risks"), list) else []
    srcs = sources or spec.get("primary_sources") or []
    jurisdiction = spec.get("jurisdiction") or _NA

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"**Jurisdiction:** {_clean(jurisdiction, 80)}\n\n")
    parts.append(f"{_AWARD_NE_COMPLIANCE}\n\n")

    # 1
    parts.append("## 1. Applicable Laws, Permits & Consents\n\n")
    parts.append(f"{_APPLY_RULE}\n\n")
    if applicable:
        parts.append(_table(
            ["Instrument", "Entity", "Site", "Activity", "Jurisdiction", "Pack status", "Source"],
            [
                [
                    _clean(r.get("instrument"), 40),
                    _clean(r.get("entity"), 40),
                    _clean(r.get("site"), 40),
                    _clean(r.get("activity"), 80),
                    _clean(r.get("jurisdiction"), 24),
                    _clean(r.get("pack_status"), 24),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in applicable if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('applicable regime for this jurisdiction')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Permit & Licence Register\n\n")
    parts.append(f"{_PERMIT_RULE}\n\n")
    if permits:
        parts.append(_table(
            [
                "Identifier", "Holder", "Site", "Conditions", "Expiry",
                "Renewal", "Transfer on CoC", "Source",
            ],
            [
                [
                    _clean(r.get("identifier"), 36),
                    _clean(r.get("holder"), 36),
                    _clean(r.get("site"), 36),
                    _clean(r.get("conditions"), 60),
                    _clean(r.get("expiry"), 28),
                    _clean(r.get("renewal_status"), 28),
                    _clean(r.get("transfer_on_coc"), 36),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in permits if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('permit / licence register')}**\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Obligations — Tested vs Untested\n\n")
    parts.append(f"{_OBLIGATION_RULE}\n\n")
    if obligations:
        parts.append(_table(
            ["Obligation", "Tested?", "Evidence", "Pack status tag", "Source"],
            [
                [
                    _clean(r.get("obligation"), 50),
                    _clean(r.get("tested"), 16),
                    _clean(r.get("evidence"), 120),
                    _clean(r.get("pack_status_tag") or _NA, 24),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in obligations if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('material obligations and test evidence')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Litigation & Claims Register\n\n")
    parts.append(f"{_LITIGATION_RULE}\n\n")
    if litigation:
        parts.append(_table(
            [
                "Matter", "Status", "Claimed amount", "Provision",
                "Insurance", "Counsel assessment", "Probability", "Source",
            ],
            [
                [
                    _clean(r.get("matter"), 50),
                    _clean(r.get("status"), 24),
                    _clean(r.get("claimed_amount") or _NA, 28),
                    _clean(r.get("provision") or _NA, 28),
                    _clean(r.get("insurance") or _NA, 28),
                    _clean(r.get("counsel_assessment") or _NA, 60),
                    (
                        "Not assigned — no evidenced basis"
                        if r.get("numeric_probability") is None
                        else str(r.get("numeric_probability"))
                    ),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in litigation if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(
            f"**{_info_request('litigation / claims from counsel or case records')}**\n\n"
        )
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Transaction Implications\n\n")
    parts.append(f"{_TXN_RULE}\n\n")
    if txn:
        parts.append(_table(
            ["Implication", "Detail", "Protection", "Source"],
            [
                [
                    _clean(r.get("implication"), 36),
                    _clean(r.get("detail"), 120),
                    _clean(r.get("protection"), 60),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in txn if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('transaction consents / CPs / indemnities')}**\n\n")
    parts.append("---\n\n")

    # 6 — Counsel closure, quantification, critical permits, IP cross-check
    counsel = (
        spec.get("counsel_letter")
        if isinstance(spec.get("counsel_letter"), dict) else {}
    )
    quantified = (
        spec.get("quantified_effects")
        if isinstance(spec.get("quantified_effects"), list) else []
    )
    critical = (
        spec.get("critical_permits")
        if isinstance(spec.get("critical_permits"), list) else []
    )
    ip_cross = (
        spec.get("ip_cross_check")
        if isinstance(spec.get("ip_cross_check"), dict) else {}
    )
    parts.append("## 6. Counsel Closure, Quantification & Critical Permits\n\n")
    parts.append(f"{_COUNSEL_LETTER_RULE} {_QUANTIFY_RULE} {_IP_CROSS_RULE}\n\n")
    parts.append("### Counsel letter\n\n")
    parts.append(
        f"- **Status:** {_clean(counsel.get('status') or 'OPEN', 20)}\n"
        f"- **Detail:** {_clean(counsel.get('detail') or _NA, 200)}\n\n"
    )
    parts.append("### Quantified effects (pack-supported only)\n\n")
    if quantified:
        parts.append(_table(
            ["Effect", "Amount", "Basis", "Source"],
            [
                [
                    _clean(r.get("effect"), 80),
                    _clean(r.get("amount") or _NA, 40),
                    _clean(r.get("basis"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in quantified if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('supported quantified effects')}**\n\n")
    parts.append("### Critical permits → Recommendations\n\n")
    if critical:
        parts.append(_table(
            ["Permit", "Holder", "Transfer on CoC", "Expiry", "Recommendation action", "Source"],
            [
                [
                    _clean(r.get("permit"), 40),
                    _clean(r.get("holder"), 36),
                    _clean(r.get("transfer_on_coc"), 40),
                    _clean(r.get("expiry"), 28),
                    _clean(r.get("recommendation_action"), 100),
                    _clean(r.get("source") or _NA, 36),
                ]
                for r in critical if isinstance(r, dict)
            ],
        ))
    else:
        parts.append("None flagged from the opened permit register.\n\n")
    parts.append("### IP and Technology cross-check\n\n")
    parts.append(_table(
        ["Field", "Value"],
        [
            [
                "IP prior present",
                "Yes" if ip_cross.get("ip_prior_present") else "No",
            ],
            [
                "IP litigation in RC",
                _clean("; ".join(ip_cross.get("ip_litigation_in_rc") or []) or _NA, 160),
            ],
            [
                "Aligned",
                _clean("; ".join(ip_cross.get("aligned") or []) or _NA, 200),
            ],
            [
                "Conflicts",
                _clean("; ".join(ip_cross.get("conflicts") or []) or "None", 200),
            ],
        ],
    ))
    parts.append("---\n\n")

    # Supporting legacy risk summary
    if risks:
        parts.append("## Supporting — Legacy Risk / Mitigant Summary\n\n")
        parts.append(_table(
            ["Clause", "Severity", "Mitigant"],
            [
                [
                    _clean(r.get("clause"), 80),
                    str(r.get("severity") if r.get("severity") is not None else "—"),
                    _clean(r.get("mitigant"), 60),
                ]
                for r in risks if isinstance(r, dict)
            ],
        ))
        parts.append("---\n\n")

    # 7 QA
    rc_qa = (
        spec.get("rc_evidence_qa")
        if isinstance(spec.get("rc_evidence_qa"), list) else []
    )
    parts.append("## 7. Regulatory Compliance Evidence QA\n\n")
    parts.append(
        "QA enforces entity/site regime completeness, permit CoC fields, "
        "litigation register discipline, counsel-letter closure, quantification "
        "only when supported, IP cross-check, and no invented laws/cases/probabilities.\n\n"
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
                for r in rc_qa
                if isinstance(r, dict)
            ],
        )
        or f"**{_info_request('regulatory compliance evidence QA rows')}**\n\n"
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
            "None are missing — material regulatory gaps are closed, "
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
    parts.append(f"**Reliance:** {_clean(rv, 20)} — can a decision rest on this compliance test?\n\n")
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open regulatory QA FAILs and an OPEN counsel letter cap READY → LIMITED. "
        "Untested obligations are not treated as compliant. "
        f"{_NO_INVENT_RULE} "
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
