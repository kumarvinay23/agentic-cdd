"""Compose DiligenceIQ Operational Risk — evidence-derived register (prompt book).

Covers ways the business can fail day to day: capacity, quality, safety,
people, systems — and what each would cost. Register drawn from records, not
a generic taxonomy. Each risk sized (frequency, cost, EBITDA). Controls with
tested/untested status. Historical vs plan-amplified. Price/protection vs
ordinary noise. Hypotheses labeled with what would test them.

No invest/pass. No company allowlists. Preserves legacy Billing Integrity Audit
shape (kpi_gaps / risk_items / integrity_notes).
"""

from __future__ import annotations

import re
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
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_HEADER_LINE = re.compile(r"(?m)^\s*#{1,6}\s*\S+\s*$")

_DOCUMENT_TITLE = "Billing Integrity Audit"
_DD_CODE = "DD-19"

_REGISTER_RULE = (
    "The risk register is drawn from records (incidents, downtime, rework, "
    "quality failures, safety events, staff turnover, system outages, permit/"
    "licence conditions) — not from a generic risk taxonomy."
)
_SIZE_RULE = (
    "Each risk is sized: how often it has occurred, what it cost, and what it "
    "would do to EBITDA if it recurred at that rate."
)
_CONTROL_RULE = (
    "Controls in place are recorded with whether each has been **tested**. "
    "An untested control is not mitigation."
)
_PLAN_RULE = (
    "Risks already reflected in historical results are separated from risks "
    "that would be new or larger under the plan (higher volume, new geography, "
    "new service)."
)
_PRICE_RULE = (
    "Risks capable of changing price or requiring specific protection are "
    "separated from ordinary operating noise."
)
_HYPOTHESIS_RULE = (
    "Risks with no evidence in the records are hypotheses — labelled as such "
    "with what would test them."
)

_EVIDENCE_CUE = re.compile(
    r"(?i)\b(incident|downtime|rework|defect|stockout|recall|safety|"
    r"turnover|attrition|outage|permit|licence|license|kpi\s+gap|"
    r"below\s+target|at\s+risk|bottleneck|quality\s+failure|"
    r"service\s+resolution|capacity\s+(?:shortfall|miss)|injury|"
    r"near[- ]miss|sla\s+breach|system\s+(?:outage|failure))\b"
)
_CONTROL_CUE = re.compile(
    r"(?i)\b(control|mitigation|SOP|procedure|audit|inspection|training|"
    r"monitoring|alert|backup|tested|untested|never\s+tested|drill|"
    r"QA|QC|ISO|certification)\b"
)
_PLAN_CUE = re.compile(
    r"(?i)\b(plan|ramp|FY20\d{2}|expansion|new\s+(?:geography|market|plant|"
    r"service|city)|higher\s+volume|scale[- ]up|target)\b"
)
_COST_RE = re.compile(
    r"(?i)(INR\s*[\d,]+(?:\.\d+)?\s*(?:Cr|cr|crore)?|"
    r"[\d,]+(?:\.\d+)?\s*%\s+(?:of\s+)?(?:revenue|EBITDA|cost|sales)|"
    r"\$[\d,]+(?:\.\d+)?[kKmMbB]?)"
)
_FREQ_RE = re.compile(
    r"(?i)(\d+\s*(?:x|times)\s*(?:per|/)\s*(?:year|month|quarter)|"
    r"(?:once|twice)\s+(?:a|per)\s+(?:year|month|quarter)|"
    r"\d+\s*(?:incidents?|events?|outages?)\s*(?:in|over|during)\s*"
    r"(?:FY\d{2,4}|20\d{2}|Q[1-4]|the\s+(?:year|period))|"
    r"(?:monthly|quarterly|annual(?:ly)?))"
)
_KPI_GAP_RE = re.compile(
    r"(?i)(Defect Rate|Parts Stockout Rate|Service Resolution(?: Time)?|"
    r"Capacity Utilization|Monthly Production Capacity|OTIF|On[- ]Time|"
    r"First[- ]Time Fix|Safety Incidents?|Attrition|Turnover)"
    r"[^.%]{0,80}?((?:At Risk|Below Target|On Track|Monitor|HIGH|MEDIUM|LOW|"
    r"<\s*\d|[\d.]+%|\d[\d,]*)[^.%]{0,40})"
)
_OPS_MATRIX_RE = re.compile(
    r"(?i)(Production bottlenecks|Quality defects?|Stockouts?|"
    r"Service resolution|Staff attrition|System outages?|"
    r"Safety events?|Permit|Licence|License|Capacity shortfall)"
    r"[^.|]{0,40}?(High|Medium|Low)\s*/\s*(High|Medium|Low)"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)


def _info_request(label: str) -> str:
    return f"Information request: {label}"


def _is_filled(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text == _NA:
        return False
    return not text.startswith("Information request")


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


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("operational risk evidence only — no deal verdict expressed", raw)
    out = re.sub(
        r"(?i)(?:^|[\s—\-–:])(?:invest|pass)(?:\s+recommendation)?(?=[\s.,;:!?]|$)",
        " (no deal verdict) ",
        out,
    )
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


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
        cells = [(_clean(c, 220) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    text = _HEADER_LINE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_operational_risk_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "operations": 0,
        "financial": 1,
        "legal_esg": 2,
        "company_management": 3,
        "deal_strategy": 4,
        "customer": 5,
        "market_competition": 6,
    }
    needles = (
        "operational", "manufacturing", "quality", "safety", "hr", "people",
        "defect", "stockout", "service", "audit", "integrity", "kpi",
        "incident", "downtime", "permit", "licence",
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


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------


def _risk_category(text: str) -> str:
    low = text.lower()
    if re.search(r"(?i)defect|quality|rework|recall", low):
        return "quality"
    if re.search(r"(?i)stockout|capacity|bottleneck|utilization|production", low):
        return "capacity"
    if re.search(r"(?i)safety|injury|near[- ]miss", low):
        return "safety"
    if re.search(r"(?i)turnover|attrition|staff|people|hiring", low):
        return "people"
    if re.search(r"(?i)outage|system|IT|CRM|ERP|software", low):
        return "systems"
    if re.search(r"(?i)permit|licence|license|regulatory", low):
        return "permit_licence"
    if re.search(r"(?i)service\s+resolution|SLA|downtime", low):
        return "service_delivery"
    return "operations"


def _extract_register(corpus: str, legacy: dict[str, Any]) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(
        *,
        risk: str,
        evidence: str,
        category: str,
        source: str = _DOC_CITE,
        hypothesis: bool = False,
    ) -> None:
        key = re.sub(r"\s+", " ", risk.lower())[:80]
        if key in seen or len(key) < 8:
            return
        seen.add(key)
        rows.append({
            "risk": _clean(risk, 140),
            "category": category,
            "evidence": _clean(evidence, 200) if evidence else _NA,
            "record_type": category,
            "hypothesis": hypothesis,
            "test_request": (
                _info_request(f"what would test hypothesis '{_clean(risk, 60)}'")
                if hypothesis else ""
            ),
            "source": source,
            "notes": _REGISTER_RULE if not hypothesis else _HYPOTHESIS_RULE,
        })

    # KPI gaps from records
    for m in _KPI_GAP_RE.finditer(text):
        kpi = m.group(1).strip()
        status = _clean(m.group(2), 80)
        _add(
            risk=f"{kpi} performance gap ({status})",
            evidence=m.group(0),
            category=_risk_category(kpi + " " + status),
        )

    # Ops risk matrix rows
    for m in _OPS_MATRIX_RE.finditer(text):
        _add(
            risk=m.group(1).strip(),
            evidence=f"{m.group(1)} — likelihood {m.group(2)} / impact {m.group(3)}",
            category=_risk_category(m.group(1)),
        )

    # Evidence sentences
    for s in _sentences(text):
        if not _EVIDENCE_CUE.search(s) or len(s) < 35:
            continue
        # Skip pure taxonomy language
        if re.search(r"(?i)generic\s+risk|risk\s+taxonomy|enterprise\s+risk\s+framework", s):
            continue
        _add(
            risk=_clean(s, 120),
            evidence=_clean(s, 200),
            category=_risk_category(s),
        )
        if len(rows) >= 10:
            break

    # Legacy dual-write inputs
    for g in (legacy.get("kpi_gaps") or [])[:6]:
        if isinstance(g, dict) and g.get("kpi"):
            _add(
                risk=f"{g['kpi']} — {g.get('status') or 'gap'}",
                evidence=f"Legacy KPI gap: {g['kpi']}",
                category=_risk_category(str(g["kpi"])),
            )
    for r in (legacy.get("risk_items") or [])[:6]:
        if isinstance(r, dict) and r.get("risk"):
            _add(
                risk=str(r["risk"]),
                evidence=(
                    f"Legacy matrix: {r.get('likelihood') or '?'} / {r.get('impact') or '?'}"
                ),
                category=_risk_category(str(r["risk"])),
            )

    if not rows:
        rows.append({
            "risk": _info_request(
                "operational risks evidenced in incidents / KPI / downtime records"
            ),
            "category": "operations",
            "evidence": _NA,
            "record_type": "none",
            "hypothesis": False,
            "test_request": "",
            "source": _NA,
            "notes": _REGISTER_RULE,
        })
    return rows[:12]


def _size_risk(row: dict[str, Any], corpus: str) -> dict[str, str]:
    text = _prose(corpus)
    risk = str(row.get("risk") or "")
    evidence = str(row.get("evidence") or "")
    blob = f"{evidence} {risk}"
    # Prefer local sentence with same keywords
    local = next(
        (
            s for s in _sentences(text)
            if any(tok in s.lower() for tok in risk.lower().split()[:3] if len(tok) > 3)
            and (_COST_RE.search(s) or _FREQ_RE.search(s) or _EVIDENCE_CUE.search(s))
        ),
        evidence if _is_filled(evidence) else "",
    )
    search_in = local or blob

    freq = _NA
    fm = _FREQ_RE.search(search_in) or _FREQ_RE.search(text)
    if fm:
        freq = _clean(fm.group(0), 60)
    elif re.search(r"(?i)at\s+risk|below\s+target|ongoing", search_in):
        freq = "Ongoing / observed in latest reporting period"

    cost = _NA
    cm = _COST_RE.search(search_in)
    if cm:
        cost = _clean(cm.group(0), 60)
    else:
        # KPI deltas sometimes imply cost without INR
        pct = re.search(r"(?i)(\d+(?:\.\d+)?)\s*%", search_in)
        if pct and re.search(r"(?i)defect|stockout|utilization|attrition", search_in):
            cost = f"Observed gap at {pct.group(1)}% (cost not stated in packs)"

    ebitda = _NA
    em = re.search(r"(?i)EBITDA[^.%]{0,40}?(\d+(?:\.\d+)?\s*%|INR\s*[\d,]+)", search_in)
    if em:
        ebitda = _clean(em.group(0), 80)
    elif cost != _NA and "INR" in cost.upper():
        ebitda = (
            f"If recurred at stated rate, earnings impact on order of {cost} "
            f"(bridge to EBITDA not provided) {_COMPUTED}"
        )
    else:
        ebitda = _info_request(f"EBITDA impact if '{_clean(risk, 40)}' recurs at observed rate")

    sized = "Yes" if (freq != _NA or cost != _NA) and not str(ebitda).startswith("Information") else (
        "Partial" if freq != _NA or cost != _NA else "No"
    )
    return {
        "risk": _clean(risk, 120),
        "frequency": freq if freq != _NA else _info_request("how often this has occurred"),
        "cost": cost if cost != _NA else _info_request("what it cost historically"),
        "ebitda_if_recurs": ebitda,
        "sized": sized,
        "source": _DOC_CITE if local or _is_filled(evidence) else _NA,
        "notes": _SIZE_RULE,
    }


def _extract_sized(register: list[dict], corpus: str) -> list[dict[str, str]]:
    out = [
        _size_risk(r, corpus)
        for r in register
        if isinstance(r, dict) and not r.get("hypothesis")
    ]
    if not out:
        out.append({
            "risk": _info_request("evidenced operational risks to size"),
            "frequency": _NA,
            "cost": _NA,
            "ebitda_if_recurs": _NA,
            "sized": "No",
            "source": _NA,
            "notes": _SIZE_RULE,
        })
    return out[:10]


def _extract_controls(register: list[dict], corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    control_sents = [s for s in _sentences(text) if _CONTROL_CUE.search(s)][:10]
    rows: list[dict[str, str]] = []
    for r in register[:8]:
        if not isinstance(r, dict) or r.get("hypothesis"):
            continue
        risk = str(r.get("risk") or "")
        local = next(
            (
                s for s in control_sents
                if any(tok in s.lower() for tok in risk.lower().split()[:3] if len(tok) > 3)
            ),
            None,
        )
        if not local and control_sents and len(rows) < 2:
            local = control_sents[0]
        tested = "Untested / not evidenced"
        control = _info_request(f"control in place for '{_clean(risk, 50)}'")
        if local:
            control = _clean(local, 180)
            if re.search(r"(?i)\b(tested|drill|audited|inspection\s+passed)\b", local):
                if re.search(r"(?i)\b(never|untested|not\s+tested)\b", local):
                    tested = "Untested"
                else:
                    tested = "Tested"
            elif re.search(r"(?i)\b(never|untested|not\s+tested)\b", local):
                tested = "Untested"
        rows.append({
            "risk": _clean(risk, 100),
            "control": control,
            "tested": tested,
            "mitigation_status": (
                "Mitigation credited" if tested == "Tested"
                else "Not mitigation — control untested or not evidenced"
            ),
            "source": _DOC_CITE if local else _NA,
            "notes": _CONTROL_RULE,
        })
    if not rows:
        rows.append({
            "risk": _info_request("risks needing control evidence"),
            "control": _NA,
            "tested": "Untested / not evidenced",
            "mitigation_status": "Not mitigation — control untested or not evidenced",
            "source": _NA,
            "notes": _CONTROL_RULE,
        })
    return rows[:8]


def _extract_historical_vs_plan(
    register: list[dict],
    corpus: str,
) -> list[dict[str, str]]:
    text = _prose(corpus)
    plan_sents = [s for s in _sentences(text) if _PLAN_CUE.search(s)][:8]
    rows: list[dict[str, str]] = []
    for r in register[:8]:
        if not isinstance(r, dict) or r.get("hypothesis"):
            continue
        risk = str(r.get("risk") or "")
        evidence = str(r.get("evidence") or "")
        in_history = _is_filled(evidence) and not evidence.startswith("Information")
        plan_hit = next(
            (
                s for s in plan_sents
                if any(tok in s.lower() for tok in risk.lower().split()[:2] if len(tok) > 3)
                or re.search(r"(?i)volume|geography|service|capacity|ramp", s)
            ),
            None,
        )
        if in_history and plan_hit:
            bucket = "Amplified under plan"
            plan_note = _clean(plan_hit, 160)
        elif in_history:
            bucket = "In historical results"
            plan_note = "Reflected in observed KPI / incident history; plan amplification not evidenced."
        else:
            bucket = "New under plan (unproven)"
            plan_note = _info_request("whether plan volume/geography/service amplifies this risk")
        rows.append({
            "risk": _clean(risk, 100),
            "bucket": bucket,
            "plan_driver": plan_note,
            "source": _DOC_CITE if in_history or plan_hit else _NA,
            "notes": _PLAN_RULE,
        })
    if not rows:
        rows.append({
            "risk": _info_request("risks to classify vs plan"),
            "bucket": "Unassessed",
            "plan_driver": _NA,
            "source": _NA,
            "notes": _PLAN_RULE,
        })
    return rows[:8]


def _extract_priced_vs_noise(
    register: list[dict],
    sized: list[dict],
    corpus: str,
) -> list[dict[str, str]]:
    del corpus
    size_map = {
        str(s.get("risk") or "").lower()[:60]: s
        for s in sized if isinstance(s, dict)
    }
    rows: list[dict[str, str]] = []
    for r in register[:8]:
        if not isinstance(r, dict):
            continue
        risk = str(r.get("risk") or "")
        if r.get("hypothesis"):
            rows.append({
                "risk": _clean(risk, 100),
                "classification": "Hypothesis",
                "rationale": (
                    f"{_HYPOTHESIS_RULE} "
                    f"{r.get('test_request') or _info_request('what would test this')}"
                ),
                "source": _NA,
                "notes": _HYPOTHESIS_RULE,
            })
            continue
        sz = size_map.get(risk.lower()[:60]) or {}
        cost = str(sz.get("cost") or "")
        ebitda = str(sz.get("ebitda_if_recurs") or "")
        cat = str(r.get("category") or "")
        material = (
            "INR" in cost.upper()
            or "EBITDA" in ebitda.upper()
            or cat in {"safety", "permit_licence", "capacity"}
            or re.search(r"(?i)high|at\s+risk|recall|injury", risk + cost)
        )
        if material:
            classification = "Price / protection relevant"
            rationale = (
                "Capable of changing price or requiring specific protection "
                f"(category={cat}; sized={sz.get('sized') or 'No'}). {_PRICE_RULE}"
            )
        else:
            classification = "Ordinary operating noise"
            rationale = (
                "Treated as ordinary operating noise unless packs show earnings "
                f"or pricing sensitivity. {_PRICE_RULE}"
            )
        rows.append({
            "risk": _clean(risk, 100),
            "classification": classification,
            "rationale": _clean(rationale, 240),
            "source": _DOC_CITE if _is_filled(r.get("evidence")) else _NA,
            "notes": _PRICE_RULE,
        })
    # Explicit hypotheses placeholder if none
    if not any(x.get("classification") == "Hypothesis" for x in rows):
        rows.append({
            "risk": _info_request("unproven operational risk hypotheses"),
            "classification": "Hypothesis",
            "rationale": (
                f"{_HYPOTHESIS_RULE} "
                f"{_info_request('packs or interviews that would test each hypothesis')}"
            ),
            "source": _NA,
            "notes": _HYPOTHESIS_RULE,
        })
    return rows[:10]


def _legacy_kpi_gaps(register: list[dict], legacy: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for g in (legacy.get("kpi_gaps") or [])[:6]:
        if isinstance(g, dict) and g.get("kpi"):
            out.append({"kpi": str(g["kpi"]), "status": str(g.get("status") or "")})
    for r in register:
        if not isinstance(r, dict):
            continue
        risk = str(r.get("risk") or "")
        if re.search(r"(?i)defect|stockout|utilization|capacity|resolution|attrition", risk):
            m = re.match(r"^([^—(]+)", risk)
            kpi = (m.group(1).strip() if m else risk)[:80]
            if not any(k["kpi"].lower() == kpi.lower() for k in out):
                status = "At Risk" if re.search(r"(?i)at\s+risk|below|gap", risk) else "Observed"
                out.append({"kpi": kpi, "status": status})
        if len(out) >= 8:
            break
    return out


def _legacy_risk_items(register: list[dict], sized: list[dict], legacy: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in (legacy.get("risk_items") or [])[:6]:
        if isinstance(r, dict) and r.get("risk"):
            out.append({
                "risk": str(r["risk"]),
                "likelihood": str(r.get("likelihood") or ""),
                "impact": str(r.get("impact") or ""),
            })
    size_map = {
        str(s.get("risk") or "").lower()[:50]: s
        for s in sized if isinstance(s, dict)
    }
    for r in register:
        if not isinstance(r, dict) or r.get("hypothesis"):
            continue
        risk = str(r.get("risk") or "")
        if any(o["risk"].lower()[:40] == risk.lower()[:40] for o in out):
            continue
        sz = size_map.get(risk.lower()[:50]) or {}
        freq = str(sz.get("frequency") or "")
        cost = str(sz.get("cost") or "")
        likelihood = "Medium"
        if re.search(r"(?i)ongoing|monthly|quarterly|high", freq + risk):
            likelihood = "High"
        elif re.search(r"(?i)once|rare|annual", freq):
            likelihood = "Low"
        impact = "Medium"
        if "INR" in cost.upper() or re.search(r"(?i)high|at\s+risk|recall", risk + cost):
            impact = "High"
        out.append({"risk": _clean(risk, 100), "likelihood": likelihood, "impact": impact})
        if len(out) >= 8:
            break
    return out


def _quality_reliance(
    *,
    register: list[dict],
    sized: list[dict],
    controls: list[dict],
    priced: list[dict],
) -> tuple[str, str, str]:
    evidenced = sum(
        1 for r in register
        if isinstance(r, dict)
        and not r.get("hypothesis")
        and _is_filled(r.get("evidence"))
        and not str(r.get("evidence")).startswith("Information")
    )
    sized_ok = sum(
        1 for s in sized
        if isinstance(s, dict) and str(s.get("sized") or "") in {"Yes", "Partial"}
    )
    tested = sum(
        1 for c in controls
        if isinstance(c, dict) and str(c.get("tested") or "") == "Tested"
    )
    hypotheses = sum(
        1 for p in priced
        if isinstance(p, dict) and p.get("classification") == "Hypothesis"
        and _is_filled(p.get("risk"))
        and not str(p.get("risk")).startswith("Information")
    )
    material = sum(
        1 for p in priced
        if isinstance(p, dict) and "protection" in str(p.get("classification") or "").lower()
    )

    if evidenced >= 2 and sized_ok >= 1:
        reliance = "READY" if tested >= 1 and material >= 1 else "LIMITED"
        return (
            "PASS",
            reliance,
            f"Evidence-derived register with {evidenced} record-backed risk(s); "
            f"{sized_ok} sized; {tested} tested control(s); "
            f"{material} price/protection-relevant; {hypotheses} labelled hypothesis(es). "
            f"{_CONTROL_RULE}",
        )
    if evidenced >= 1:
        return (
            "PASS",
            "LIMITED",
            "Partial operational-risk evidence — sizing and/or tested controls thin. "
            f"{_SIZE_RULE} {_CONTROL_RULE}",
        )
    return (
        "PASS",
        "BLOCKED",
        "No incident / KPI / downtime records opened to build an evidence-derived register.",
    )


# ---------------------------------------------------------------------------
# heuristic / LLM / normalise / build / render
# ---------------------------------------------------------------------------


def _heuristic_operational_risk_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra = ""
    for note in (legacy.get("integrity_notes") or [])[:6]:
        if isinstance(note, str) and note.strip():
            extra += "\n" + note.strip()
    for g in (legacy.get("kpi_gaps") or [])[:4]:
        if isinstance(g, dict) and g.get("kpi"):
            extra += f"\n{g['kpi']} {g.get('status') or ''}"
    for r in (legacy.get("risk_items") or [])[:4]:
        if isinstance(r, dict) and r.get("risk"):
            extra += f"\n{r['risk']} {r.get('likelihood') or ''} {r.get('impact') or ''}"
    corpus_full = (corpus or "") + extra

    register = _extract_register(corpus_full, legacy)
    sized = _extract_sized(register, corpus_full)
    controls = _extract_controls(register, corpus_full)
    hist_plan = _extract_historical_vs_plan(register, corpus_full)
    priced = _extract_priced_vs_noise(register, sized, corpus_full)
    kpi_gaps = _legacy_kpi_gaps(register, legacy)
    risk_items = _legacy_risk_items(register, sized, legacy)

    notes: list[str] = [
        _REGISTER_RULE,
        _SIZE_RULE,
        _CONTROL_RULE,
        _PLAN_RULE,
        _PRICE_RULE,
        _HYPOTHESIS_RULE,
    ]
    for n in (legacy.get("integrity_notes") or [])[:3]:
        if isinstance(n, str) and n.strip():
            notes.append(_soften_invest(_clean(n, 240)))

    quality, reliance, rationale = _quality_reliance(
        register=register, sized=sized, controls=controls, priced=priced,
    )

    evidenced_n = sum(
        1 for r in register
        if not r.get("hypothesis")
        and _is_filled(r.get("evidence"))
        and not str(r.get("evidence")).startswith("Information")
    )
    tested_n = sum(1 for c in controls if c.get("tested") == "Tested")
    bits = [
        f"Operational Risk for {company}",
        f"{evidenced_n} evidence-derived risk(s)",
        f"{sum(1 for s in sized if s.get('sized') in {'Yes', 'Partial'})} sized",
        f"{tested_n} tested control(s)",
    ]

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "risk_register": register,
        "sized_risks": sized,
        "controls": controls,
        "historical_vs_plan": hist_plan,
        "priced_vs_noise": priced,
        # Legacy dual-write
        "kpi_gaps": kpi_gaps,
        "risk_items": risk_items,
        "integrity_notes": notes[:8],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": evidenced_n == 0 and not kpi_gaps and not risk_items,
    }


def _llm_operational_risk_spec(
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
            "operational_risk",
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
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "risk_register: [{risk, category, evidence, record_type, hypothesis, "
        "test_request, source, notes}],\n"
        "sized_risks: [{risk, frequency, cost, ebitda_if_recurs, sized, source, notes}],\n"
        "controls: [{risk, control, tested, mitigation_status, source, notes}],\n"
        "historical_vs_plan: [{risk, bucket, plan_driver, source, notes}],\n"
        "priced_vs_noise: [{risk, classification, rationale, source, notes}],\n"
        "kpi_gaps: [{kpi, status}], risk_items: [{risk, likelihood, impact}],\n"
        "integrity_notes: [string],\n"
        "quality_verdict (PASS|REWORK), reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Derive risks ONLY from records — no generic taxonomy. "
        "Untested controls are not mitigation. Label hypotheses. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    heur = _heuristic_operational_risk_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy,
    )

    def _rows(key: str, required: str) -> list[dict[str, Any]]:
        raw = llm.get(key) if isinstance(llm.get(key), list) else []
        cleaned = [r for r in raw if isinstance(r, dict) and r.get(required)]
        return cleaned or heur.get(key) or []

    register = _rows("risk_register", "risk")
    for row in register:
        if row.get("hypothesis") in (True, "true", "True", "yes", "Yes"):
            row["hypothesis"] = True
            if not _is_filled(row.get("test_request")):
                row["test_request"] = _info_request(
                    f"what would test hypothesis '{_clean(row.get('risk'), 60)}'"
                )
            row["notes"] = _HYPOTHESIS_RULE
        else:
            row["hypothesis"] = False
            row["notes"] = _REGISTER_RULE
    llm["risk_register"] = register

    sized = _rows("sized_risks", "risk")
    for row in sized:
        row["notes"] = _SIZE_RULE
    llm["sized_risks"] = sized

    controls = _rows("controls", "risk")
    for row in controls:
        tested = str(row.get("tested") or "")
        if not tested:
            row["tested"] = "Untested / not evidenced"
        if "Tested" not in str(row.get("tested")) or "Untested" in str(row.get("tested")):
            if str(row.get("tested")) != "Tested":
                row["mitigation_status"] = (
                    "Not mitigation — control untested or not evidenced"
                )
        else:
            row["mitigation_status"] = "Mitigation credited"
        row["notes"] = _CONTROL_RULE
    llm["controls"] = controls

    hist = _rows("historical_vs_plan", "risk")
    for row in hist:
        row["notes"] = _PLAN_RULE
    llm["historical_vs_plan"] = hist

    priced = _rows("priced_vs_noise", "risk")
    for row in priced:
        if "hypothesis" in str(row.get("classification") or "").lower():
            row["notes"] = _HYPOTHESIS_RULE
        else:
            row["notes"] = _PRICE_RULE
    llm["priced_vs_noise"] = priced

    kpi = llm.get("kpi_gaps") if isinstance(llm.get("kpi_gaps"), list) else []
    kpi = [g for g in kpi if isinstance(g, dict) and g.get("kpi")] or heur["kpi_gaps"]
    llm["kpi_gaps"] = kpi[:8]

    items = llm.get("risk_items") if isinstance(llm.get("risk_items"), list) else []
    items = [r for r in items if isinstance(r, dict) and r.get("risk")] or heur["risk_items"]
    llm["risk_items"] = items[:8]

    notes = llm.get("integrity_notes") if isinstance(llm.get("integrity_notes"), list) else []
    notes = [_soften_invest(_clean(n, 240)) for n in notes if isinstance(n, str) and n.strip()]
    for rule in (
        _REGISTER_RULE, _SIZE_RULE, _CONTROL_RULE, _PLAN_RULE, _PRICE_RULE, _HYPOTHESIS_RULE,
    ):
        if not any(rule[:28].lower() in x.lower() for x in notes):
            notes.append(rule)
    if not notes:
        notes = heur["integrity_notes"]
    llm["integrity_notes"] = notes[:8]

    quality, reliance, rationale = _quality_reliance(
        register=register, sized=sized, controls=controls, priced=priced,
    )
    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else quality
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else reliance
    llm["quality_reliance_rationale"] = (
        _soften_invest(_clean(llm.get("quality_reliance_rationale"), 460))
        if str(llm.get("quality_reliance_rationale") or "").strip()
        else rationale
    )

    for dead in ("recommendation", "confidence", "investment_verdict", "verdict", "invest_recommendation"):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_invest(
        llm.get("insight_snapshot") or heur.get("insight_snapshot") or ""
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = not register and not kpi
    return llm


def build_operational_risk_spec(
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
        gathered_corpus, gathered_sources = gather_operational_risk_corpus(deal, idx)
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
        llm = _llm_operational_risk_spec(
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
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
            )

    return _heuristic_operational_risk_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )


def render_operational_risk_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    register = spec.get("risk_register") if isinstance(spec.get("risk_register"), list) else []
    sized = spec.get("sized_risks") if isinstance(spec.get("sized_risks"), list) else []
    controls = spec.get("controls") if isinstance(spec.get("controls"), list) else []
    hist = (
        spec.get("historical_vs_plan")
        if isinstance(spec.get("historical_vs_plan"), list) else []
    )
    priced = (
        spec.get("priced_vs_noise")
        if isinstance(spec.get("priced_vs_noise"), list) else []
    )
    kpi_gaps = spec.get("kpi_gaps") if isinstance(spec.get("kpi_gaps"), list) else []
    risk_items = spec.get("risk_items") if isinstance(spec.get("risk_items"), list) else []
    notes = spec.get("integrity_notes") if isinstance(spec.get("integrity_notes"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # 1
    parts.append("## 1. Evidence-Derived Risk Register\n\n")
    parts.append(f"{_REGISTER_RULE}\n\n")
    if register:
        parts.append(_table(
            ["Risk", "Category", "Evidence from records", "Hypothesis?", "Source"],
            [
                [
                    _clean(r.get("risk"), 120),
                    _clean(r.get("category"), 30),
                    _clean(r.get("evidence"), 140),
                    "Yes" if r.get("hypothesis") else "No",
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in register if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('evidence-derived operational risk register')}**\n\n")
    if kpi_gaps:
        parts.append("### KPI gaps observed in packs\n\n")
        parts.append(_table(
            ["KPI", "Status"],
            [
                [_clean(g.get("kpi"), 80), _clean(g.get("status"), 60)]
                for g in kpi_gaps if isinstance(g, dict)
            ],
        ))
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Sized Risks (Frequency / Cost / EBITDA)\n\n")
    parts.append(f"{_SIZE_RULE}\n\n")
    if sized:
        parts.append(_table(
            ["Risk", "Frequency", "Historical cost", "EBITDA if recurs", "Sized?", "Source"],
            [
                [
                    _clean(r.get("risk"), 100),
                    _clean(r.get("frequency"), 60),
                    _clean(r.get("cost"), 60),
                    _clean(r.get("ebitda_if_recurs"), 100),
                    _clean(r.get("sized"), 20),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in sized if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('sized operational risks')}**\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Controls & Testing\n\n")
    parts.append(f"{_CONTROL_RULE}\n\n")
    if controls:
        parts.append(_table(
            ["Risk", "Control in place", "Tested?", "Mitigation status", "Source"],
            [
                [
                    _clean(r.get("risk"), 80),
                    _clean(r.get("control"), 120),
                    _clean(r.get("tested"), 40),
                    _clean(r.get("mitigation_status"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in controls if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('controls and test status')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Historical vs Plan-Amplified\n\n")
    parts.append(f"{_PLAN_RULE}\n\n")
    if hist:
        parts.append(_table(
            ["Risk", "Bucket", "Plan driver / note", "Source"],
            [
                [
                    _clean(r.get("risk"), 100),
                    _clean(r.get("bucket"), 40),
                    _clean(r.get("plan_driver"), 140),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in hist if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('historical vs plan classification')}**\n\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Price / Protection vs Noise & Hypotheses\n\n")
    parts.append(f"{_PRICE_RULE} {_HYPOTHESIS_RULE}\n\n")
    if priced:
        parts.append(_table(
            ["Risk", "Classification", "Rationale", "Source"],
            [
                [
                    _clean(r.get("risk"), 100),
                    _clean(r.get("classification"), 40),
                    _clean(r.get("rationale"), 160),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in priced if isinstance(r, dict)
            ],
        ))
    if risk_items:
        parts.append("### Legacy likelihood / impact matrix\n\n")
        parts.append(_table(
            ["Risk", "Likelihood", "Impact"],
            [
                [
                    _clean(r.get("risk"), 100),
                    _clean(r.get("likelihood"), 20),
                    _clean(r.get("impact"), 20),
                ]
                for r in risk_items if isinstance(r, dict)
            ],
        ))
    parts.append(
        "*This section does not recommend invest or pass. Untested controls are not "
        "mitigation. Hypotheses are labelled and request what would test them.*\n\n"
    )
    parts.append("---\n\n")

    # 6
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
                    360,
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
        f"can diligence rest on this operational risk register?\n\n"
    )
    if notes:
        parts.append("### Integrity notes\n\n")
        for n in notes[:6]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This document builds an operational risk register from evidence and sizes "
        "what each failure mode would cost. It does not recommend invest or pass.*\n\n"
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
