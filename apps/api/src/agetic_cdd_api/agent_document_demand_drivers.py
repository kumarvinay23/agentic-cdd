"""Compose DiligenceIQ Demand Drivers — cause → customers → cash (prompt book).

Drivers with mechanism/population/timing/magnitude/persistence/evidence;
instrument types do not stack; transmission to volume/price; counter-drivers
and cyclicality; ranked contribution; anti-double-count vs Volume/Growth;
regulatory cross-check; hypothesis register for untested drivers.
No invest/pass.
"""

from __future__ import annotations

import re
import textwrap
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _pick_sentences,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")

_INSTRUMENT_TYPES = (
    "legal_mandate",
    "grant",
    "subsidy",
    "voluntary_commitment",
    "operating_saving",
)

_INSTRUMENT_LABELS = {
    "legal_mandate": "Legal mandate",
    "grant": "Grant",
    "subsidy": "Subsidy / incentive",
    "voluntary_commitment": "Voluntary commitment",
    "operating_saving": "Operating saving",
}

_MANDATE = re.compile(
    r"\b(mandat(?:e|ory)|ban\b|prohibit|phase[- ]?out|obligation|enacted|"
    r"regulation|statute|law\b|must\s+comply|compliance\s+deadline)\b",
    re.IGNORECASE,
)
_GRANT = re.compile(
    r"\b(grant|capital\s+support|capex\s+support|production[- ]linked|"
    r"\bpli\b|one[- ]time\s+(?:award|payment))\b",
    re.IGNORECASE,
)
_SUBSIDY = re.compile(
    r"\b(subsid(?:y|ies|ised)|incentive|rebate|tax\s+credit|"
    r"purchase\s+incentive|consumer\s+incentive)\b",
    re.IGNORECASE,
)
_VOLUNTARY = re.compile(
    r"\b(voluntary|net[- ]zero\s+commit|ESG\s+target|pledge|commitment|"
    r"corporate\s+target|self[- ]imposed)\b",
    re.IGNORECASE,
)
_OPERATING = re.compile(
    r"\b(operating\s+sav(?:ing|ings)|TCO|total\s+cost\s+of\s+ownership|"
    r"fuel\s+sav(?:ing|ings)|energy\s+cost|payback|ROI\b)\b",
    re.IGNORECASE,
)
_DRIVER_CUE = re.compile(
    r"\b(demand\s+driver|growth\s+driver|tailwind|structural\s+driver|"
    r"catalyst|boost(?:s|ed|ing)?\s+demand|drives?\s+demand|"
    r"urbani[sz]ation|electrification|digitali[sz]ation|"
    r"policy|regulation|subsidy|incentive|mandate)\b",
    re.IGNORECASE,
)
_COUNTER = re.compile(
    r"\b(headwind|counter[- ]?driver|risk\s+to\s+demand|demand\s+risk|"
    r"cyclical|downturn|recession|slowdown|seasonal|monsoon|"
    r"policy\s+reversal|subsidy\s+(?:cut|phase[- ]?out|expiry)|"
    r"competition\s+from|substitution)\b",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"\b((?:FY|CY)?(?:19|20)\d{2}(?:[-–/](?:\d{2}|\d{4}))?|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2}|"
    r"(?:Q[1-4]\s*(?:FY|CY)?\s*(?:19|20)\d{2}))\b",
    re.IGNORECASE,
)
_PLACEHOLDER_POLICY = re.compile(
    r"\b(TBD|to\s+be\s+announced|placeholder|forthcoming\s+policy|"
    r"expected\s+scheme|proposed\s+but\s+not\s+enacted|draft\s+bill)\b",
    re.IGNORECASE,
)
_POPULATION = re.compile(
    r"\b((?:[\d,.]+)\s*(?:m|mn|million|bn|billion|k|thousand)?\s+"
    r"(?:customers?|households?|premises|fleets?|vehicles?|units?|"
    r"subscribers?|SMEs?|enterprises?|accounts?))\b",
    re.IGNORECASE,
)


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


def _classify_instrument(text: str) -> str:
    """Pick one instrument type — they do not stack."""
    t = text or ""
    # Mandate first: legal compulsion behaves differently from money incentives.
    if _MANDATE.search(t):
        return "legal_mandate"
    if _GRANT.search(t):
        return "grant"
    if _SUBSIDY.search(t):
        return "subsidy"
    if _OPERATING.search(t):
        return "operating_saving"
    if _VOLUNTARY.search(t):
        return "voluntary_commitment"
    return "voluntary_commitment"


def _instrument_label(key: str) -> str:
    return _INSTRUMENT_LABELS.get(key, key.replace("_", " ").title())


def gather_demand_drivers_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "deal_strategy": 0,
        "market_competition": 1,
        "customer": 2,
        "financial": 3,
        "company_management": 4,
    }
    needles = (
        "commercial", "thesis", "demand", "market", "policy", "subsidy",
        "incentive", "regulation", "geographic", "region", "growth",
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


def _driver_name_from_sent(sent: str) -> str:
    s = _clean(sent, 120)
    for sep in (" — ", " - ", ": ", "; "):
        if sep in s:
            head = s.split(sep, 1)[0].strip()
            if 8 <= len(head) <= 80:
                return head
    # Word-boundary clip — avoid mid-word truncation in table names.
    return textwrap.shorten(s, width=80, placeholder="...")


def _extract_drivers(corpus: str, geography: str | None) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    hits = [
        s for s in _pick_sentences(
            sents,
            keywords=(
                "demand", "driver", "tailwind", "mandate", "subsidy", "incentive",
                "grant", "regulation", "urbanization", "urbanisation", "electrification",
                "adoption", "boost", "growth",
            ),
            limit=12,
        )
        if _DRIVER_CUE.search(s) or _MANDATE.search(s) or _SUBSIDY.search(s) or _GRANT.search(s)
    ]
    hits = [h for h in hits if not _PLACEHOLDER_POLICY.search(h)]

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    geo_note = f" in {geography}" if geography else ""
    for sent in hits:
        name = _driver_name_from_sent(sent)
        key = name.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        instrument = _classify_instrument(sent)
        date_m = _DATE.search(sent)
        pop_m = _POPULATION.search(sent)
        rows.append({
            "driver": name,
            "mechanism": _clean(sent, 220) + f" {_DOC_CITE}",
            "customer_population_exposed": (
                _clean(pop_m.group(1), 80) + f" {_DOC_CITE}"
                if pop_m
                else _info_request(f"customer population exposed{geo_note}")
            ),
            "effective_date": (
                f"{date_m.group(1)} {_DOC_CITE}"
                if date_m
                else _info_request("enacted effective date / coverage window")
            ),
            "expected_size": _info_request("expected size / magnitude for this business"),
            "persistence": _info_request("how long the driver persists"),
            "instrument_type": instrument,
            "geography": geography or _info_request("geography where driver applies"),
            "notes": (
                f"Instrument: {_instrument_label(instrument)} — "
                f"do not stack with other instrument types for the same growth {_COMPUTED}"
            ),
        })
        if len(rows) >= 6:
            break

    if not rows:
        rows.append({
            "driver": _info_request("demand driver that applies to this business"),
            "mechanism": _info_request("mechanism"),
            "customer_population_exposed": _info_request("customer population exposed"),
            "effective_date": _info_request("enacted date and coverage"),
            "expected_size": _info_request("expected size"),
            "persistence": _info_request("persistence"),
            "instrument_type": "legal_mandate",
            "geography": geography or _info_request("geography"),
            "notes": "No enacted driver evidenced — no placeholder policies",
        })
    return rows


def _separate_instruments(drivers: list[dict[str, str]]) -> list[dict[str, str]]:
    by_type: dict[str, list[str]] = {k: [] for k in _INSTRUMENT_TYPES}
    for d in drivers:
        if not isinstance(d, dict):
            continue
        t = str(d.get("instrument_type") or "")
        if t not in by_type:
            t = _classify_instrument(str(d.get("mechanism") or d.get("driver") or ""))
            d["instrument_type"] = t
        name = str(d.get("driver") or "").strip()
        if name and not name.startswith("Information"):
            by_type.setdefault(t, []).append(name)

    behaviour = {
        "legal_mandate": "Compels adoption; binary once enacted; does not add to subsidy cash",
        "grant": "One-off / capped capital support; expires with scheme budget",
        "subsidy": "Price/cash incentive; reversible; demand sensitive to phase-out",
        "voluntary_commitment": "Buyer choice; can slip without legal force",
        "operating_saving": "Economics-led adoption; persists if TCO holds",
    }
    rows: list[dict[str, str]] = []
    for key in _INSTRUMENT_TYPES:
        names = by_type.get(key) or []
        rows.append({
            "instrument_type": _instrument_label(key),
            "drivers_in_type": "; ".join(names[:4]) if names else _NA,
            "behaviour": behaviour.get(key, ""),
            "stacking_rule": "Do not stack — count growth under one instrument only",
        })
    return rows


def _transmission(drivers: list[dict[str, str]], corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    path_hits = _pick_sentences(
        sents,
        keywords=("customer", "volume", "revenue", "conversion", "win", "attach", "ASP"),
        limit=6,
    )
    rows: list[dict[str, str]] = []
    for d in drivers[:5]:
        if not isinstance(d, dict):
            continue
        name = str(d.get("driver") or "driver")
        if name.startswith("Information"):
            continue
        toks = re.findall(r"[a-z]{4,}", name.lower())[:3]
        hit = next(
            (h for h in path_hits if any(tok in h.lower() for tok in toks)),
            path_hits[0] if path_hits else None,
        )
        proven = bool(hit) and not _PLACEHOLDER_POLICY.search(hit or "")
        rows.append({
            "driver": _clean(name, 80),
            "customers_won": (
                _clean(hit, 160) + f" {_DOC_CITE}"
                if hit and re.search(r"(?i)customer|win|adopt|fleet|account", hit or "")
                else _info_request(f"customers won via {name}")
            ),
            "volume": (
                _clean(hit, 160) + f" {_DOC_CITE}"
                if hit and re.search(r"(?i)volume|unit|shipment|registration", hit or "")
                else _info_request(f"volume from {name}")
            ),
            "revenue": (
                _clean(hit, 160) + f" {_DOC_CITE}"
                if hit and re.search(r"(?i)revenue|ASP|sales|INR|USD", hit or "")
                else _info_request(f"revenue for this company from {name}")
            ),
            "chain_status": (
                f"Partially evidenced {_DOC_CITE}" if proven
                else "Unproven — transmission chain not evidenced in the data room"
            ),
        })
    if not rows:
        rows.append({
            "driver": _info_request("driver"),
            "customers_won": _info_request("customers won"),
            "volume": _info_request("volume"),
            "revenue": _info_request("revenue for this company"),
            "chain_status": "Unproven — transmission chain not evidenced in the data room",
        })
    return rows[:6]


def _counter_drivers(corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    hits = [
        s for s in _pick_sentences(
            sents,
            keywords=(
                "headwind", "risk", "cyclical", "downturn", "seasonal",
                "subsidy", "reversal", "slowdown", "monsoon",
            ),
            limit=8,
        )
        if _COUNTER.search(s)
    ]
    hist = _pick_sentences(
        sents,
        keywords=("FY20", "FY201", "COVID", "downturn", "recession", "crisis", "historical"),
        limit=3,
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for sent in hits:
        key = sent.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        hist_hit = next((h for h in hist if h), None)
        rows.append({
            "counter_driver": _clean(sent, 160) + f" {_DOC_CITE}",
            "cyclicality": (
                "Cyclical / seasonal signal evidenced"
                if re.search(r"(?i)cyclical|seasonal|monsoon|downturn", sent)
                else _info_request("cyclicality pattern")
            ),
            "company_history": (
                _clean(hist_hit, 180) + f" {_DOC_CITE}"
                if hist_hit
                else _info_request("company history covering a downturn")
            ),
            "notes": "Use own-history evidence where a downturn is covered",
        })
        if len(rows) >= 4:
            break
    if not rows:
        rows.append({
            "counter_driver": _info_request("counter-driver / downside"),
            "cyclicality": _info_request("cyclicality"),
            "company_history": _info_request("company history covering a downturn"),
            "notes": "No counter-driver evidenced in opened packs",
        })
    return rows


def _rank_drivers(
    drivers: list[dict[str, str]],
    transmission: list[dict[str, str]],
) -> list[dict[str, str]]:
    proven = {
        str(t.get("driver") or "").lower()
        for t in transmission
        if isinstance(t, dict) and "Partially evidenced" in str(t.get("chain_status") or "")
    }
    scored: list[tuple[int, dict[str, str]]] = []
    for d in drivers:
        if not isinstance(d, dict):
            continue
        name = str(d.get("driver") or "")
        if name.startswith("Information"):
            continue
        score = 0
        if name.lower() in proven or any(name.lower()[:40] in p for p in proven):
            score += 3
        if not str(d.get("effective_date") or "").startswith("Information"):
            score += 2
        if not str(d.get("customer_population_exposed") or "").startswith("Information"):
            score += 1
        if d.get("instrument_type") == "legal_mandate":
            score += 1
        scored.append((score, d))
    scored.sort(key=lambda x: (-x[0], x[1].get("driver") or ""))

    rows: list[dict[str, str]] = []
    claimed_growth: set[str] = set()
    for rank, (score, d) in enumerate(scored, start=1):
        name = str(d.get("driver") or "")
        growth_key = re.sub(r"\W+", " ", name.lower())[:40].strip()
        double = growth_key in claimed_growth
        claimed_growth.add(growth_key)
        rows.append({
            "rank": str(rank),
            "driver": _clean(name, 80),
            "evidenced_contribution": (
                f"Score {score} {_COMPUTED} — "
                f"{'transmission partially evidenced' if score >= 3 else 'limited evidence'}"
            ),
            "double_count_check": (
                "FLAG: same growth already counted under another driver"
                if double
                else "OK — growth attributed to this driver only"
            ),
            "instrument_type": _instrument_label(str(d.get("instrument_type") or "")),
        })
    if not rows:
        rows.append({
            "rank": "—",
            "driver": _info_request("ranked driver"),
            "evidenced_contribution": _info_request("evidenced contribution to growth case"),
            "double_count_check": "Do not let the same growth appear under two drivers",
            "instrument_type": _NA,
        })
    return rows[:6]


def _regulatory_cross_check(
    drivers: list[dict[str, str]],
    corpus: str,
) -> list[dict[str, str]]:
    """Cross-check mandate/policy drivers against regulatory evidence in pack."""
    rows: list[dict[str, str]] = []
    reg_hits = _pick_sentences(
        _sentences(corpus),
        keywords=("regulation", "enacted", "compliance", "jurisdiction", "licence", "license"),
        limit=3,
    )
    for d in drivers:
        if not isinstance(d, dict):
            continue
        itype = str(d.get("instrument_type") or "")
        if itype not in {"legal_mandate", "grant", "subsidy"}:
            continue
        name = str(d.get("driver") or "")
        if name.startswith("Information"):
            continue
        dated = (
            d.get("effective_date")
            and not str(d["effective_date"]).startswith("Information")
            and d["effective_date"] != _NA
        )
        rows.append({
            "driver": _clean(name, 80),
            "against_agent": "regulatory_compliance",
            "status": "aligned_pending_confirm" if dated and reg_hits else "needs_reconcile",
            "note": (
                f"Enacted date {_clean(d.get('effective_date'), 40)}; "
                f"regulatory text {'evidenced' if reg_hits else 'thin'} in pack — "
                f"confirm jurisdiction/coverage with Regulatory Compliance {_DOC_CITE if reg_hits else ''}".strip()
            ),
        })
    if not rows:
        rows.append({
            "driver": _info_request("policy / mandate driver"),
            "against_agent": "regulatory_compliance",
            "status": "n/a",
            "note": "No mandate/grant/subsidy driver to cross-check yet",
        })
    return rows[:6]


def _hypothesis_register(
    drivers: list[dict[str, str]],
    transmission: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Untested drivers / unproven transmission chains — what would close them."""
    unproven_tx = {
        str(t.get("driver") or "").lower()[:60]
        for t in transmission
        if isinstance(t, dict) and "Unproven" in str(t.get("chain_status") or "")
    }
    rows: list[dict[str, str]] = []
    for d in drivers:
        if not isinstance(d, dict):
            continue
        name = str(d.get("driver") or "")
        if name.startswith("Information"):
            continue
        gaps: list[str] = []
        if str(d.get("effective_date") or "").startswith("Information"):
            gaps.append("effective date")
        if str(d.get("customer_population_exposed") or "").startswith("Information"):
            gaps.append("population exposed")
        if str(d.get("expected_size") or "").startswith("Information"):
            gaps.append("magnitude")
        if name.lower()[:60] in unproven_tx or any(
            name.lower()[:40] in u for u in unproven_tx
        ):
            gaps.append("transmission chain")
        if not gaps:
            continue
        rows.append({
            "hypothesis": _clean(name, 80),
            "why_untested": f"Missing: {', '.join(gaps)}",
            "closure_test": (
                f"Evidence {_clean(', '.join(gaps), 120)} with locator on this geography"
            ),
            "interim_treatment": "Do not count in READY growth contribution until closed",
        })
    if not rows:
        rows.append({
            "hypothesis": "No untested drivers — all ranked items have minimum evidence",
            "why_untested": "N/A",
            "closure_test": "Re-open if new policy or geography expands the perimeter",
            "interim_treatment": "None",
        })
    return rows[:8]


def _volume_growth_anti_double_count(
    ranked: list[dict[str, str]],
) -> dict[str, str]:
    """Same growth must not appear under Demand Drivers and Volume without reconcile."""
    flagged = [
        str(r.get("driver") or "")
        for r in ranked
        if isinstance(r, dict) and "FLAG" in str(r.get("double_count_check") or "").upper()
    ]
    return {
        "against_agent": "market_volume_and_growth",
        "status": "flagged" if flagged else "ok_pending_volume_reconcile",
        "note": (
            f"Internal double-count FLAG on: {', '.join(_clean(f, 40) for f in flagged[:3])}. "
            f"Also reconcile attributed growth with Market Volume & Growth series "
            f"so the same CAGR is not claimed twice."
            if flagged
            else (
                "No internal double-count FLAG. Still reconcile driver-attributed growth "
                "with Market Volume & Growth endpoint series before READY reliance."
            )
        ),
    }


def _questions_from_dd_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    drivers = spec.get("drivers") if isinstance(spec.get("drivers"), list) else []
    named = [
        d for d in drivers
        if isinstance(d, dict)
        and d.get("driver")
        and not str(d["driver"]).startswith("Information")
    ]
    if not named:
        out.append(
            normalize_question(
                {
                    "question": "Identify enacted demand drivers with dates for this geography",
                    "required_records": "Policy / commercial pack with effective dates and coverage",
                    "decision_effect": "Growth case lacks cause→cash chain",
                    "priority": "mandatory_pre_decision",
                    "owner": "market diligence lead",
                    "timing": "before IC",
                    "closure_test": "≥1 enacted driver with mechanism, population, date",
                    "interim_treatment": "Do not invent industry themes as drivers",
                }
            )
        )

    for d in named:
        if str(d.get("effective_date") or "").startswith("Information"):
            out.append(
                normalize_question(
                    {
                        "question": f"Provide effective date / coverage for {_clean(d.get('driver'), 60)}",
                        "required_records": "Enacted policy text or commercial programme note",
                        "decision_effect": "Timing of demand shift for volume/plan multiple",
                        "priority": "mandatory_pre_decision",
                        "owner": "market / regulatory lead",
                        "timing": "before IC",
                        "closure_test": "Dated enactment with geography coverage",
                        "interim_treatment": "Treat timing as unknown; do not front-load growth",
                    }
                )
            )
            break

    transmission = spec.get("transmission") if isinstance(spec.get("transmission"), list) else []
    if all(
        isinstance(t, dict) and "Unproven" in str(t.get("chain_status") or "")
        for t in transmission
    ) or not transmission:
        out.append(
            normalize_question(
                {
                    "question": "Evidence transmission from driver → customers → volume → revenue",
                    "required_records": "Win data / volume bridge / ASP × units attributable to driver",
                    "decision_effect": "Unproven chain cannot support pricing-led or volume-led plan",
                    "priority": "mandatory_pre_decision",
                    "owner": "commercial diligence lead",
                    "timing": "before IC",
                    "closure_test": "At least one driver with partially evidenced transmission",
                    "interim_treatment": "Mark chain Unproven; exclude from READY contribution",
                }
            )
        )

    counters = spec.get("counter_drivers") if isinstance(spec.get("counter_drivers"), list) else []
    if not any(
        isinstance(c, dict)
        and c.get("counter_driver")
        and not str(c["counter_driver"]).startswith("Information")
        for c in counters
    ):
        out.append(
            normalize_question(
                {
                    "question": "Document counter-drivers and cyclicality from company history",
                    "required_records": "Downturn P&L history / seasonal volume / subsidy phase-out notes",
                    "decision_effect": "One-sided driver list overstates durability of growth",
                    "priority": "signing_condition",
                    "owner": "market diligence lead",
                    "timing": "per deal timetable",
                    "closure_test": "≥1 counter-driver with cyclicality or company history note",
                    "interim_treatment": "Treat persistence as untested",
                }
            )
        )

    reg = spec.get("regulatory_cross_checks") if isinstance(spec.get("regulatory_cross_checks"), list) else []
    if any(isinstance(r, dict) and r.get("status") == "needs_reconcile" for r in reg):
        out.append(
            normalize_question(
                {
                    "question": "Reconcile mandate/subsidy drivers with Regulatory Compliance",
                    "required_records": "Regulatory memo with jurisdiction, coverage, effective date",
                    "decision_effect": "Policy-driven demand may not apply as modelled",
                    "priority": "signing_condition",
                    "owner": "regulatory lead",
                    "timing": "per deal timetable",
                    "closure_test": "Same date/coverage as Demand Drivers or conflict logged",
                    "interim_treatment": "LIMITED reliance on policy-driven volume",
                }
            )
        )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for q in out:
        key = q.get("question", "").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
    if not unique:
        unique.append(
            normalize_question(
                {
                    "question": "No material demand-driver inputs are missing for the stated geography",
                    "required_records": "N/A — current pack sufficient for ranked drivers",
                    "decision_effect": "None — drivers publishable as shared basis",
                    "priority": "residual_uncertainty",
                    "owner": "market diligence lead",
                    "timing": "n/a",
                    "closure_test": "Re-run if geography or policy set changes",
                    "interim_treatment": "None",
                }
            )
        )
    return unique[:12]


def _quality_reliance(
    *,
    driver_count: int,
    enacted_dated: int,
    transmission_proven: int,
    has_counter: bool,
) -> tuple[str, str, str]:
    if driver_count >= 1 and enacted_dated >= 1 and transmission_proven >= 1:
        return (
            "PASS",
            "READY" if transmission_proven >= 2 and has_counter else "LIMITED",
            (
                f"{driver_count} driver(s); {enacted_dated} with enacted date; "
                f"{transmission_proven} transmission path(s) partially evidenced."
            ),
        )
    if driver_count >= 1:
        return (
            "PASS",
            "LIMITED",
            "Drivers identified but dates, transmission, or counter-drivers incomplete.",
        )
    return "PASS", "BLOCKED", "No enacted demand drivers evidenced in the data room."


def _llm_demand_drivers_spec(
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
            "demand_drivers",
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
        "drivers: [{driver, mechanism, customer_population_exposed, effective_date, "
        "expected_size, persistence, instrument_type, geography, evidence, notes}] "
        "— instrument_type one of legal_mandate|grant|subsidy|voluntary_commitment|operating_saving; "
        "enacted policies with dates only (no placeholders),\n"
        "instrument_separation: [{instrument_type, drivers_in_type, behaviour, stacking_rule}],\n"
        "transmission: [{driver, customers_won, volume, revenue, price_path, chain_status}] "
        "— say Unproven where the chain is not evidenced,\n"
        "counter_drivers: [{counter_driver, cyclicality, company_history, notes}],\n"
        "ranked_contribution: [{rank, driver, evidenced_contribution, double_count_check, instrument_type}] "
        "— do not attribute the same growth to two drivers,\n"
        "regulatory_cross_checks: [{driver, against_agent, status, note}],\n"
        "hypothesis_register: [{hypothesis, why_untested, closure_test, interim_treatment}],\n"
        "questions: [{question, required_records, decision_effect, priority, "
        "owner, timing, closure_test, interim_treatment}],\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Reconcile with Market Volume & Growth — same growth must not be claimed twice. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_demand_drivers_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra = ""
    for key in ("demand_drivers", "regional_signals", "cycle_risks"):
        for item in (legacy.get(key) or [])[:6]:
            if isinstance(item, str) and item.strip():
                extra += "\n" + item.strip()
    corpus_full = (corpus or "") + extra

    drivers = _extract_drivers(corpus_full, geography)
    instruments = _separate_instruments(drivers)
    transmission = _transmission(drivers, corpus_full)
    counters = _counter_drivers(corpus_full)
    ranked = _rank_drivers(drivers, transmission)
    regulatory = _regulatory_cross_check(drivers, corpus_full)
    hypotheses = _hypothesis_register(drivers, transmission)
    volume_reconcile = _volume_growth_anti_double_count(ranked)

    enacted = sum(
        1 for d in drivers
        if d.get("effective_date")
        and not str(d["effective_date"]).startswith("Information")
        and d["effective_date"] != _NA
    )
    proven = sum(
        1 for t in transmission
        if "Partially evidenced" in str(t.get("chain_status") or "")
    )
    has_counter = any(
        c.get("counter_driver") and not str(c["counter_driver"]).startswith("Information")
        for c in counters
    )
    named_drivers = sum(
        1 for d in drivers if d.get("driver") and not str(d["driver"]).startswith("Information")
    )
    quality, reliance, qr = _quality_reliance(
        driver_count=named_drivers,
        enacted_dated=enacted,
        transmission_proven=proven,
        has_counter=has_counter,
    )
    if volume_reconcile.get("status") == "flagged" and reliance == "READY":
        reliance = "LIMITED"
        qr = f"{qr} Double-count FLAG vs Volume/Growth reconcile."

    insight = (
        f"Demand Drivers for {company}: {named_drivers} driver(s) with instrument types "
        f"separated (no stacking); transmission driver→customers→volume→revenue traced "
        f"where evidenced; counter-drivers and ranking without double-counted growth; "
        f"regulatory cross-check and hypothesis register for untested items."
    )

    out: dict[str, Any] = {
        "insight_snapshot": insight,
        "drivers": drivers,
        "instrument_separation": instruments,
        "transmission": transmission,
        "counter_drivers": counters,
        "ranked_contribution": ranked,
        "regulatory_cross_checks": regulatory,
        "hypothesis_register": hypotheses,
        "volume_growth_reconcile": volume_reconcile,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": "Demand Drivers",
        "dd_code": legacy.get("dd_code") or "DD-03",
        "demand_drivers": [
            str(d.get("driver")) for d in drivers
            if isinstance(d, dict) and d.get("driver")
            and not str(d["driver"]).startswith("Information")
        ] or legacy.get("demand_drivers") or [],
        "regional_signals": legacy.get("regional_signals") or [],
        "cycle_risks": [
            str(c.get("counter_driver")) for c in counters
            if isinstance(c, dict) and c.get("counter_driver")
            and not str(c["counter_driver"]).startswith("Information")
        ] or legacy.get("cycle_risks") or [],
        "consumes_ceiling": legacy.get("consumes_ceiling"),
        "ceiling_tam": legacy.get("ceiling_tam"),
    }
    out["questions"] = _questions_from_dd_gaps(out)
    return out


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    geography: str | None,
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
) -> dict[str, Any]:
    for key in (
        "drivers", "instrument_separation", "transmission",
        "counter_drivers", "ranked_contribution",
        "regulatory_cross_checks", "hypothesis_register",
    ):
        if not isinstance(llm.get(key), list):
            llm[key] = []

    cleaned_drivers: list[dict[str, Any]] = []
    for row in llm.get("drivers") or []:
        if not isinstance(row, dict):
            continue
        blob = " ".join(
            str(row.get(k) or "") for k in ("driver", "mechanism", "effective_date", "notes")
        )
        if _PLACEHOLDER_POLICY.search(blob):
            continue
        itype = str(row.get("instrument_type") or "").strip().lower().replace(" ", "_")
        if itype not in _INSTRUMENT_TYPES:
            itype = _classify_instrument(blob)
        row["instrument_type"] = itype
        if not row.get("geography"):
            row["geography"] = geography or _info_request("geography")
        cleaned_drivers.append(row)
    if not cleaned_drivers:
        cleaned_drivers = _extract_drivers("", geography)
    llm["drivers"] = cleaned_drivers

    if not llm.get("instrument_separation"):
        llm["instrument_separation"] = _separate_instruments(cleaned_drivers)

    for row in llm.get("transmission") or []:
        if not isinstance(row, dict):
            continue
        if not str(row.get("chain_status") or "").strip():
            row["chain_status"] = (
                "Unproven — transmission chain not evidenced in the data room"
            )
        row.setdefault("price_path", _info_request("price transmission path"))

    seen_growth: set[str] = set()
    for row in llm.get("ranked_contribution") or []:
        if not isinstance(row, dict):
            continue
        key = re.sub(r"\W+", " ", str(row.get("driver") or "").lower())[:40].strip()
        check = str(row.get("double_count_check") or "")
        if key and key in seen_growth and "FLAG" not in check.upper():
            row["double_count_check"] = (
                "FLAG: same growth already counted under another driver"
            )
        if key:
            seen_growth.add(key)

    if not llm.get("regulatory_cross_checks"):
        llm["regulatory_cross_checks"] = _regulatory_cross_check(cleaned_drivers, corpus)
    if not llm.get("hypothesis_register"):
        llm["hypothesis_register"] = _hypothesis_register(
            cleaned_drivers, llm.get("transmission") or []
        )
    if not isinstance(llm.get("volume_growth_reconcile"), dict):
        llm["volume_growth_reconcile"] = _volume_growth_anti_double_count(
            llm.get("ranked_contribution") or []
        )

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else "PASS"
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else "LIMITED"

    if not llm.get("questions"):
        llm["questions"] = _questions_from_dd_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw in llm.get("questions") or []:
            q = normalize_question(raw)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_dd_gaps(llm)

    for dead in ("recommendation", "confidence", "key_conditions"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = "Demand Drivers"
    llm["dd_code"] = "DD-03"
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    llm["demand_drivers"] = [
        str(d.get("driver")) for d in cleaned_drivers
        if d.get("driver") and not str(d["driver"]).startswith("Information")
    ] or legacy.get("demand_drivers") or []
    llm.setdefault("regional_signals", legacy.get("regional_signals") or [])
    llm["cycle_risks"] = [
        str(c.get("counter_driver"))
        for c in (llm.get("counter_drivers") or [])
        if isinstance(c, dict) and c.get("counter_driver")
        and not str(c["counter_driver"]).startswith("Information")
    ] or legacy.get("cycle_risks") or []
    for k in ("consumes_ceiling", "ceiling_tam"):
        llm.setdefault(k, legacy.get(k))
    return llm


def build_demand_drivers_spec(
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
        gathered_corpus, gathered_sources = gather_demand_drivers_corpus(deal, idx)
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
        llm = _llm_demand_drivers_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=geography,
            materiality=vars_.get("materiality"),
            deal_perimeter=vars_.get("deal_perimeter"),
            transaction_type=vars_.get("transaction_type"),
            as_of_date=vars_.get("as_of_date"),
            review_periods=vars_.get("review_periods"),
            decision_stage=vars_.get("decision_stage"),
        )
        if llm:
            out = _normalise_llm_spec(
                llm,
                sources=sources,
                geography=geography,
                legacy_spec=legacy_spec,
                corpus=corpus,
            )
            out["deal_slots"] = {k: v for k, v in vars_.items() if v}
            return out

    heur = _heuristic_demand_drivers_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return heur


def render_demand_drivers_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    drivers = spec.get("drivers") if isinstance(spec.get("drivers"), list) else []
    instruments = (
        spec.get("instrument_separation")
        if isinstance(spec.get("instrument_separation"), list)
        else []
    )
    transmission = spec.get("transmission") if isinstance(spec.get("transmission"), list) else []
    counters = spec.get("counter_drivers") if isinstance(spec.get("counter_drivers"), list) else []
    ranked = (
        spec.get("ranked_contribution")
        if isinstance(spec.get("ranked_contribution"), list)
        else []
    )
    regulatory = (
        spec.get("regulatory_cross_checks")
        if isinstance(spec.get("regulatory_cross_checks"), list)
        else []
    )
    hypotheses = (
        spec.get("hypothesis_register")
        if isinstance(spec.get("hypothesis_register"), list)
        else []
    )
    volume_reconcile = (
        spec.get("volume_growth_reconcile")
        if isinstance(spec.get("volume_growth_reconcile"), dict)
        else {}
    )
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Drivers That Apply\n\n")
    parts.append(
        "Mechanism, exposed customer population, effective date, expected size (magnitude) "
        "and persistence. "
        "**Enacted policies with dates and coverage only — no placeholder policies.**\n\n"
    )
    if drivers:
        parts.append(_table(
            [
                "Driver", "Mechanism", "Population Exposed", "Effective Date",
                "Expected Size", "Persistence", "Instrument",
            ],
            [
                [
                    _clean(r.get("driver"), 50),
                    _clean(r.get("mechanism"), 140),
                    _clean(r.get("customer_population_exposed"), 60),
                    _clean(r.get("effective_date"), 40),
                    _clean(r.get("expected_size"), 60),
                    _clean(r.get("persistence"), 50),
                    _instrument_label(str(r.get("instrument_type") or "")),
                ]
                for r in drivers if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 2. Instrument Separation\n\n")
    parts.append(
        "Legal mandate vs grant vs subsidy vs voluntary commitment vs operating saving. "
        "**They behave differently and do not stack.**\n\n"
    )
    if instruments:
        parts.append(_table(
            ["Instrument", "Drivers in Type", "Behaviour", "Stacking Rule"],
            [
                [
                    _clean(r.get("instrument_type"), 40),
                    _clean(r.get("drivers_in_type"), 120),
                    _clean(r.get("behaviour"), 140),
                    _clean(r.get("stacking_rule"), 80),
                ]
                for r in instruments if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 3. Transmission Path\n\n")
    parts.append(
        "Driver → customers won → volume → revenue (and price where relevant) for this company. "
        "**Marked Unproven if unevidenced in the data room.**\n\n"
    )
    if transmission:
        parts.append(_table(
            ["Driver", "Customers Won", "Volume", "Revenue", "Chain Status"],
            [
                [
                    _clean(r.get("driver"), 50),
                    _clean(r.get("customers_won"), 100),
                    _clean(r.get("volume"), 100),
                    _clean(r.get("revenue"), 100),
                    _clean(r.get("chain_status"), 80),
                ]
                for r in transmission if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 4. Counter-Drivers & Cyclicality\n\n")
    parts.append(
        "Downside and cyclicality, using the company's own history where it covers a downturn.\n\n"
    )
    if counters:
        parts.append(_table(
            ["Counter-Driver / Risk", "Cyclicality Signal", "Company History in Downturn", "Notes"],
            [
                [
                    _clean(r.get("counter_driver"), 140),
                    _clean(r.get("cyclicality"), 80),
                    _clean(r.get("company_history"), 120),
                    _clean(r.get("notes"), 80),
                ]
                for r in counters if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 5. Ranked Contribution to Growth Case\n\n")
    parts.append(
        "Rank by evidenced contribution. "
        "**Do not let the same growth appear under two drivers**, or under both "
        "Demand Drivers and Market Volume & Growth without reconcile.\n\n"
    )
    if ranked:
        parts.append(_table(
            ["Rank", "Driver", "Evidenced Contribution", "Double-Count Check", "Instrument Type"],
            [
                [
                    str(r.get("rank") or "—"),
                    _clean(r.get("driver"), 60),
                    _clean(r.get("evidenced_contribution"), 120),
                    _clean(r.get("double_count_check"), 100),
                    _clean(r.get("instrument_type"), 40),
                ]
                for r in ranked if isinstance(r, dict)
            ],
        ))
    if volume_reconcile:
        parts.append(
            f"**vs Market Volume & Growth:** {_clean(volume_reconcile.get('status'), 40)} — "
            f"{_clean(volume_reconcile.get('note'), 280)}\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 6. Regulatory Cross-Check\n\n")
    parts.append(
        "Enacted mandate / grant / subsidy claims vs Regulatory Compliance "
        "(dates, coverage, jurisdiction).\n\n"
    )
    if regulatory:
        parts.append(_table(
            ["Driver", "Against", "Status", "Note"],
            [
                [
                    _clean(r.get("driver"), 60),
                    _clean(r.get("against_agent"), 40),
                    _clean(r.get("status"), 40),
                    _clean(r.get("note"), 160),
                ]
                for r in regulatory if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 7. Hypothesis Register (Untested Drivers)\n\n")
    parts.append(
        "Drivers stated but not fully evidenced — what would close them.\n\n"
    )
    if hypotheses:
        parts.append(_table(
            ["Hypothesis", "Why Untested", "Closure Test", "Interim Treatment"],
            [
                [
                    _clean(r.get("hypothesis"), 80),
                    _clean(r.get("why_untested"), 100),
                    _clean(r.get("closure_test"), 120),
                    _clean(r.get("interim_treatment"), 100),
                ]
                for r in hypotheses if isinstance(r, dict)
            ],
        ))
    parts.append(
        "*This section does not recommend invest or pass. "
        "A growth case is only credible if drivers transmit to this company's revenue "
        "without double-counted growth or stacked instruments.*\n\n"
    )
    parts.append("---\n\n")

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
        parts.append(f"{_info_request('Questions for material demand-driver gaps')}\n\n")
    parts.append("---\n\n")

    parts.append("## 9. Quality & Reliance\n\n")
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
        f"can the growth case rest on these demand drivers?\n\n"
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
