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
_OPS_MAP_RULE = (
    "Day-to-day delivery depends on a mapped set of processes, assets, sites "
    "and labour — SPOF-style dependencies are named from records."
)
_UTIL_RULE = (
    "Capacity and utilisation are stated against current and planned volume; "
    "where the plan binds capacity, say when."
)
_INCIDENT_RULE = (
    "Incidents, maintenance and insurance are reviewed only where evidenced — "
    "missing packs are named, not invented."
)
_CASH_IMPACT_RULE = (
    "Disruption impacts are traced to revenue, EBITDA and cash where the "
    "packs allow — not EBITDA alone."
)
_CONTINUITY_OPS_RULE = (
    "Continuity / BCP arrangements state whether each has been used or tested "
    "(untested is not mitigation)."
)
_BOTTLENECK_CF_RULE = (
    "Growth-plan bottlenecks are reconciled with Cash Flow — funding and "
    "working-capital constraints must not contradict ops capacity claims."
)
_NO_PROXY_RULE = (
    "Cyber and insurance conclusions are not invented from weak proxies "
    "(IT/CRM/ERP mentions alone are not cyber evidence)."
)
_SITE_CUE = re.compile(
    r"(?i)\b(plant|site|facility|factory|depot|warehouse|campus|Hosur|"
    r"manufacturing\s+(?:site|location))\b"
)
_ASSET_CUE = re.compile(
    r"(?i)\b(line|fleet|asset|equipment|tooling|mould|mold|conveyor|"
    r"press|kiln|reactor|vehicle\s+fleet)\b"
)
_LABOUR_CUE = re.compile(
    r"(?i)\b(labour|labor|workforce|headcount|operators?|technicians?|"
    r"attrition|turnover|shift|staff(?:ing)?)\b"
)
_PROCESS_CUE = re.compile(
    r"(?i)\b(process|SOP|assembly|manufactur|fulfilment|QA|QC|inspect|"
    r"service\s+resolution|last[- ]mile)\b"
)
_UTIL_CUE = re.compile(
    r"(?i)\b(capacity\s+utili[sz]ation|utili[sz]ation|headroom|throughput|"
    r"binds?|bottleneck|monthly\s+production\s+capacity)\b"
)
_MAINT_CUE = re.compile(
    r"(?i)\b(maintenance|preventive\s+maintenance|PM\s+schedule|overhaul|"
    r"downtime\s+for\s+maintenance|MTBF|MTTR)\b"
)
_INSURANCE_CUE = re.compile(
    r"(?i)\b(insurance|indemnity|policy\s+limit|cover(?:age)?|insured|"
    r"business\s+interruption\s+(?:cover|policy)|BI\s+cover)\b"
)
_CYBER_CUE = re.compile(
    r"(?i)\b(cyber|ransomware|data\s+breach|security\s+incident|"
    r"penetration\s+test|SOC\s+2|ISO\s*27001)\b"
)
_WEAK_IT_PROXY = re.compile(
    r"(?i)\b(IT|CRM|ERP|software|system|SaaS|cloud)\b"
)
_CASH_CUE = re.compile(
    r"(?i)\b(cash|liquidity|working\s+capital|WC\s+impact|cash\s+burn|"
    r"free\s+cash\s+flow|FCF)\b"
)
_CONTINUITY_OPS_CUE = re.compile(
    r"(?i)\b(BCP|business\s+continuity|contingency|backup|spare\s+capacity|"
    r"continuity\s+plan|disaster\s+recovery|DR\s+plan|tested|untested|drill)\b"
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

    revenue = _NA
    rm = re.search(r"(?i)(?:revenue|sales)\s+impact[^.%]{0,40}?(INR\s*[\d,]+(?:\.\d+)?\s*(?:Cr|cr)?)", search_in)
    if rm:
        revenue = _clean(rm.group(0), 80)
    elif cost != _NA and re.search(r"(?i)revenue", search_in):
        revenue = cost

    cash = _NA
    if _CASH_CUE.search(search_in):
        cm_cash = _COST_RE.search(search_in) if _CASH_CUE.search(search_in) else None
        cash_sent = next(
            (s for s in _sentences(text) if _CASH_CUE.search(s) and (
                any(tok in s.lower() for tok in risk.lower().split()[:2] if len(tok) > 3)
                or _COST_RE.search(s)
            )),
            None,
        )
        if cash_sent:
            cash = _clean(cash_sent, 100)
        elif cm_cash:
            cash = _clean(cm_cash.group(0), 60)
        else:
            cash = _info_request(f"cash / liquidity impact if '{_clean(risk, 40)}' recurs")
    else:
        cash = _info_request(f"cash / liquidity impact if '{_clean(risk, 40)}' recurs")

    sized = "Yes" if (freq != _NA or cost != _NA) and not str(ebitda).startswith("Information") else (
        "Partial" if freq != _NA or cost != _NA else "No"
    )
    return {
        "risk": _clean(risk, 120),
        "frequency": freq if freq != _NA else _info_request("how often this has occurred"),
        "cost": cost if cost != _NA else _info_request("what it cost historically"),
        "revenue_impact": revenue if revenue != _NA else _info_request("revenue impact if recurs"),
        "ebitda_if_recurs": ebitda,
        "cash_impact": cash,
        "sized": sized,
        "source": _DOC_CITE if local or _is_filled(evidence) else _NA,
        "notes": f"{_SIZE_RULE} {_CASH_IMPACT_RULE}",
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
            "revenue_impact": _NA,
            "ebitda_if_recurs": _NA,
            "cash_impact": _NA,
            "sized": "No",
            "source": _NA,
            "notes": f"{_SIZE_RULE} {_CASH_IMPACT_RULE}",
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


def _extract_ops_map(corpus: str) -> list[dict[str, Any]]:
    """Process / asset / site / labour map from records."""
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(kind: str, name: str, evidence: str, *, source: str = _DOC_CITE) -> None:
        key = f"{kind}:{name.strip().lower()[:60]}"
        if not name.strip() or key in seen:
            return
        seen.add(key)
        rows.append({
            "element_type": kind,
            "name": _clean(name, 80),
            "evidence": _clean(evidence, 160),
            "source": source,
            "notes": _OPS_MAP_RULE,
        })

    for s in _sentences(text)[:40]:
        if _SITE_CUE.search(s):
            m = re.search(
                r"(?i)(?:plant|site|facility|factory|depot|warehouse)\s+(?:at\s+)?"
                r"([A-Z][A-Za-z0-9&'.-]{2,}(?:\s+[A-Z][A-Za-z0-9&'.-]{1,}){0,2})",
                s,
            )
            _add("site", m.group(1) if m else _clean(s, 60), s)
        if _ASSET_CUE.search(s):
            _add("asset", _clean(s, 60), s)
        if _LABOUR_CUE.search(s):
            _add("labour", _clean(s, 60), s)
        if _PROCESS_CUE.search(s):
            _add("process", _clean(s, 60), s)
        if len(rows) >= 10:
            break

    kinds = {r.get("element_type") for r in rows}
    for need in ("process", "asset", "site", "labour"):
        if need not in kinds:
            rows.append({
                "element_type": need,
                "name": _info_request(f"{need} map for day-to-day delivery"),
                "evidence": _NA,
                "source": _NA,
                "notes": _OPS_MAP_RULE,
            })
    return rows[:12]


def _extract_capacity_utilisation(corpus: str) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    util_m = re.search(
        r"(?i)(?:capacity\s+)?utili[sz]ation[^.%]{0,30}?(\d+(?:\.\d+)?)\s*%",
        text,
    )
    cap_m = re.search(
        r"(?i)(?:monthly\s+)?(?:production\s+)?capacity[^.%]{0,40}?"
        r"([\d,]+(?:\.\d+)?)\s*(units?|vehicles?)?",
        text,
    )
    bind = next(
        (s for s in _sentences(text) if re.search(r"(?i)\bbinds?\b|bottleneck|plan\s+ramp", s)),
        None,
    )
    if util_m or cap_m or bind:
        rows.append({
            "stage": "operations / plant",
            "current_capacity": (
                _clean(cap_m.group(0), 80) if cap_m else _info_request("current capacity")
            ),
            "utilisation": (
                f"{util_m.group(1)}%" if util_m else _info_request("utilisation %")
            ),
            "headroom": (
                _info_request("headroom vs plan")
                if not bind
                else _clean(bind, 120)
            ),
            "when_binds": _clean(bind, 120) if bind else _info_request("when plan binds capacity"),
            "source": _DOC_CITE if (util_m or cap_m or bind) else _NA,
            "notes": _UTIL_RULE,
        })
    else:
        rows.append({
            "stage": "operations",
            "current_capacity": _info_request("current capacity"),
            "utilisation": _info_request("utilisation %"),
            "headroom": _info_request("headroom vs plan"),
            "when_binds": _info_request("when plan binds capacity"),
            "source": _NA,
            "notes": _UTIL_RULE,
        })
    return rows


def _extract_incident_maintenance_insurance(corpus: str) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    for s in _sentences(text):
        kind = None
        if _EVIDENCE_CUE.search(s) and re.search(
            r"(?i)\b(incident|downtime|outage|near[- ]miss|injury|recall)\b", s
        ):
            kind = "incident"
        elif _MAINT_CUE.search(s):
            kind = "maintenance"
        elif _INSURANCE_CUE.search(s):
            kind = "insurance"
        if not kind:
            continue
        rows.append({
            "review_type": kind,
            "finding": _clean(s, 180),
            "source": _DOC_CITE,
            "notes": _INCIDENT_RULE,
        })
        if len(rows) >= 8:
            break
    for need in ("incident", "maintenance", "insurance"):
        if not any(r.get("review_type") == need for r in rows):
            rows.append({
                "review_type": need,
                "finding": _info_request(f"{need} review evidence"),
                "source": _NA,
                "notes": _INCIDENT_RULE,
            })
    return rows[:9]


def _extract_continuity_ops(corpus: str, controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    for s in _sentences(text):
        if not _CONTINUITY_OPS_CUE.search(s):
            continue
        tested = "Untested / not evidenced"
        if re.search(r"(?i)\b(tested|drill|used\s+in|invoked)\b", s):
            if re.search(r"(?i)\b(never|untested|not\s+tested)\b", s):
                tested = "Untested"
            else:
                tested = "Used or tested"
        elif re.search(r"(?i)\b(never|untested|not\s+tested)\b", s):
            tested = "Untested"
        rows.append({
            "arrangement": _clean(s, 180),
            "tested_or_used": tested,
            "mitigation_status": (
                "Mitigation credited" if tested == "Used or tested"
                else "Not mitigation — continuity untested or not evidenced"
            ),
            "source": _DOC_CITE,
            "notes": _CONTINUITY_OPS_RULE,
        })
        if len(rows) >= 6:
            break
    # Fold control rows that look like continuity
    for c in controls:
        if not isinstance(c, dict):
            continue
        blob = f"{c.get('control') or ''} {c.get('risk') or ''}"
        if not _CONTINUITY_OPS_CUE.search(blob):
            continue
        if any(
            str(c.get("control") or "")[:40].lower() in str(r.get("arrangement") or "").lower()
            for r in rows
        ):
            continue
        tested = str(c.get("tested") or "Untested / not evidenced")
        rows.append({
            "arrangement": _clean(c.get("control") or c.get("risk"), 180),
            "tested_or_used": tested,
            "mitigation_status": c.get("mitigation_status") or (
                "Mitigation credited" if tested == "Tested"
                else "Not mitigation — continuity untested or not evidenced"
            ),
            "source": str(c.get("source") or _DOC_CITE),
            "notes": _CONTINUITY_OPS_RULE,
        })
    if not rows:
        rows.append({
            "arrangement": _info_request("continuity / BCP arrangements"),
            "tested_or_used": "Untested / not evidenced",
            "mitigation_status": "Not mitigation — continuity untested or not evidenced",
            "source": _NA,
            "notes": _CONTINUITY_OPS_RULE,
        })
    return rows[:8]


def _reconcile_growth_bottlenecks(
    *,
    hist_plan: list[dict[str, Any]],
    capacity: list[dict[str, Any]],
    cash_flow_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reconcile plan-amplified ops bottlenecks with Cash Flow where available."""
    plan_rows = [
        r for r in hist_plan
        if isinstance(r, dict)
        and "plan" in str(r.get("bucket") or "").lower()
    ]
    binds = [
        c for c in capacity
        if isinstance(c, dict)
        and _is_filled(c.get("when_binds"))
        and not str(c.get("when_binds")).startswith("Information")
    ]
    cf_present = isinstance(cash_flow_spec, dict) and bool(cash_flow_spec)
    conflicts: list[str] = []
    aligned: list[str] = []
    cf_notes: list[str] = []

    if not cf_present:
        return {
            "cash_flow_present": False,
            "plan_bottlenecks": len(plan_rows),
            "capacity_binds": len(binds),
            "aligned": [],
            "conflicts": [],
            "notes": (
                f"{_BOTTLENECK_CF_RULE} Cash Flow output not available in this run — "
                f"bottleneck reconcile deferred."
            ),
            "source": _NA,
        }

    # Pull WC / liquidity signals from cash flow
    metrics = cash_flow_spec.get("cash_metrics") if isinstance(cash_flow_spec.get("cash_metrics"), dict) else {}
    bridges = cash_flow_spec.get("bridges") if isinstance(cash_flow_spec.get("bridges"), list) else []
    wc = cash_flow_spec.get("working_capital") if isinstance(cash_flow_spec.get("working_capital"), dict) else {}
    liquidity = cash_flow_spec.get("liquidity") if isinstance(cash_flow_spec.get("liquidity"), dict) else {}
    if metrics:
        cf_notes.append(f"cash_metrics keys: {', '.join(list(metrics.keys())[:6])}")
    if wc:
        cf_notes.append("working_capital present")
    if liquidity:
        cf_notes.append("liquidity present")

    if plan_rows and (metrics or wc or liquidity or bridges):
        aligned.append(
            f"{len(plan_rows)} plan-amplified ops risk(s) cross-checked against Cash Flow packs."
        )
    elif plan_rows:
        conflicts.append(
            "Plan-amplified ops bottlenecks present but Cash Flow has no WC/liquidity/"
            "bridge evidence to reconcile funding."
        )
    if binds and not (wc or liquidity or metrics):
        conflicts.append(
            "Capacity bind evidenced in ops but Cash Flow lacks utilisation/funding bridge."
        )
    elif binds:
        aligned.append("Capacity bind(s) noted alongside Cash Flow evidence.")

    return {
        "cash_flow_present": True,
        "plan_bottlenecks": len(plan_rows),
        "capacity_binds": len(binds),
        "aligned": aligned[:6] or ["No overlapping bottleneck facts to compare yet."],
        "conflicts": conflicts[:6],
        "notes": (
            f"{_BOTTLENECK_CF_RULE} "
            + (
                f"{len(conflicts)} conflict(s) — reconcile ops capacity with Cash Flow."
                if conflicts
                else "No bottleneck conflicts detected against Cash Flow."
            )
            + ((" " + "; ".join(cf_notes)) if cf_notes else "")
        ),
        "source": _DOC_CITE,
    }


def _guard_cyber_insurance_proxies(
    register: list[dict[str, Any]],
    incident_review: list[dict[str, Any]],
    corpus: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Strip invented cyber/insurance claims grounded only in weak IT proxies."""
    text = _prose(corpus)
    has_cyber = bool(_CYBER_CUE.search(text))
    has_insurance = bool(_INSURANCE_CUE.search(text))
    flags: list[str] = []
    out: list[dict[str, Any]] = []
    for row in register:
        if not isinstance(row, dict):
            continue
        r = dict(row)
        blob = f"{r.get('risk') or ''} {r.get('evidence') or ''} {r.get('category') or ''}"
        # Cyber from IT/CRM/ERP alone
        if re.search(r"(?i)\bcyber\b", blob) and not has_cyber:
            if _WEAK_IT_PROXY.search(blob) or str(r.get("category") or "") == "systems":
                flags.append(
                    f"Stripped weak-proxy cyber claim: {_clean(r.get('risk'), 80)}"
                )
                r["hypothesis"] = True
                r["risk"] = _clean(f"[Hypothesis] {r.get('risk')}", 120)
                r["test_request"] = _info_request(
                    "cyber evidence (incident / pen-test / control report) — not IT system name alone"
                )
                r["notes"] = _NO_PROXY_RULE
        # Insurance invented without insurance language
        if re.search(r"(?i)\binsurance\b", blob) and not has_insurance:
            flags.append(
                f"Stripped unverified insurance claim: {_clean(r.get('risk'), 80)}"
            )
            r["hypothesis"] = True
            r["risk"] = _clean(f"[Hypothesis] {r.get('risk')}", 120)
            r["test_request"] = _info_request(
                "insurance policy / BI cover evidence"
            )
            r["notes"] = _NO_PROXY_RULE
        out.append(r)

    # Flag incident-review insurance rows without evidence
    for row in incident_review:
        if not isinstance(row, dict):
            continue
        if row.get("review_type") == "insurance" and str(row.get("finding") or "").startswith("Information"):
            flags.append("Insurance review unevidenced — not invented from proxies.")
    return out, flags[:8]


def _ops_evidence_qa(
    *,
    ops_map: list[dict[str, Any]],
    capacity: list[dict[str, Any]],
    incident_review: list[dict[str, Any]],
    sized: list[dict[str, Any]],
    continuity: list[dict[str, Any]],
    bottleneck_cf: dict[str, Any],
    proxy_flags: list[str],
) -> list[dict[str, str]]:
    """Explicit PASS/FAIL QA for operational-risk discipline."""
    rows: list[dict[str, str]] = []

    filled_kinds = {
        str(r.get("element_type") or "")
        for r in ops_map
        if isinstance(r, dict)
        and _is_filled(r.get("name"))
        and not str(r.get("name")).startswith("Information")
    }
    map_ok = len(filled_kinds & {"process", "asset", "site", "labour"}) >= 2
    rows.append({
        "check": "process_asset_site_labour_map",
        "status": "PASS" if map_ok else "FAIL",
        "finding": (
            f"Mapped element types: {', '.join(sorted(filled_kinds)) or 'none'}"
            if map_ok
            else _info_request("process / asset / site / labour map from records")
        ),
        "action": _OPS_MAP_RULE,
    })

    util_ok = any(
        isinstance(c, dict)
        and (
            (
                _is_filled(c.get("utilisation"))
                and not str(c.get("utilisation")).startswith("Information")
            )
            or (
                _is_filled(c.get("current_capacity"))
                and not str(c.get("current_capacity")).startswith("Information")
            )
        )
        for c in capacity
    )
    rows.append({
        "check": "capacity_utilisation",
        "status": "PASS" if util_ok else "FAIL",
        "finding": (
            "Capacity and/or utilisation evidenced"
            if util_ok
            else _info_request("capacity and utilisation vs plan")
        ),
        "action": _UTIL_RULE,
    })

    inc_ok = sum(
        1 for r in incident_review
        if isinstance(r, dict)
        and r.get("review_type") in {"incident", "maintenance", "insurance"}
        and _is_filled(r.get("finding"))
        and not str(r.get("finding")).startswith("Information")
    )
    rows.append({
        "check": "incident_maintenance_insurance",
        "status": "PASS" if inc_ok >= 1 else "FAIL",
        "finding": (
            f"{inc_ok} incident/maintenance/insurance finding(s) evidenced"
            if inc_ok >= 1
            else _info_request("incident / maintenance / insurance review")
        ),
        "action": _INCIDENT_RULE,
    })

    pnl_ok = sum(
        1 for s in sized
        if isinstance(s, dict)
        and str(s.get("sized") or "") in {"Yes", "Partial"}
        and (
            (
                _is_filled(s.get("ebitda_if_recurs"))
                and not str(s.get("ebitda_if_recurs")).startswith("Information")
            )
            or (
                _is_filled(s.get("cash_impact"))
                and not str(s.get("cash_impact")).startswith("Information")
            )
            or (
                _is_filled(s.get("revenue_impact"))
                and not str(s.get("revenue_impact")).startswith("Information")
            )
        )
    )
    rows.append({
        "check": "disruption_to_pnl_cash",
        "status": "PASS" if pnl_ok >= 1 else "FAIL",
        "finding": (
            f"{pnl_ok} risk(s) sized to revenue/EBITDA/cash"
            if pnl_ok >= 1
            else _info_request("disruption → revenue / EBITDA / cash sizing")
        ),
        "action": _CASH_IMPACT_RULE,
    })

    tested = sum(
        1 for c in continuity
        if isinstance(c, dict)
        and (
            str(c.get("tested_or_used") or "") in {"Used or tested", "Tested"}
            or (
                "tested" in str(c.get("tested_or_used") or "").lower()
                and "untested" not in str(c.get("tested_or_used") or "").lower()
            )
        )
    )
    has_cont = any(
        isinstance(c, dict)
        and _is_filled(c.get("arrangement"))
        and not str(c.get("arrangement")).startswith("Information")
        for c in continuity
    )
    rows.append({
        "check": "continuity_tested_vs_untested",
        "status": "PASS" if has_cont else "FAIL",
        "finding": (
            f"{tested} used/tested; continuity status stated"
            if has_cont
            else _info_request("continuity arrangements with used/tested status")
        ),
        "action": _CONTINUITY_OPS_RULE,
    })

    cf_present = bool(bottleneck_cf.get("cash_flow_present"))
    conflicts = len(bottleneck_cf.get("conflicts") or [])
    rows.append({
        "check": "growth_bottleneck_cash_flow",
        "status": "FAIL" if (not cf_present or conflicts) else "PASS",
        "finding": (
            f"{conflicts} bottleneck conflict(s) vs Cash Flow"
            if conflicts
            else (
                "Growth-plan bottlenecks reconciled with Cash Flow"
                if cf_present
                else _info_request("Cash Flow output for growth-bottleneck reconcile")
            )
        ),
        "action": _BOTTLENECK_CF_RULE,
    })

    rows.append({
        "check": "no_invented_cyber_insurance",
        "status": "FAIL" if proxy_flags else "PASS",
        "finding": (
            "; ".join(proxy_flags[:3])
            if proxy_flags
            else _NO_PROXY_RULE
        ),
        "action": _NO_PROXY_RULE,
    })
    return rows


def _questions_from_ops_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("ops_evidence_qa")
        if isinstance(spec.get("ops_evidence_qa"), list)
        else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("process_asset_site_labour_map"):
        out.append(
            normalize_question(
                {
                    "question": (
                        "Provide the process / asset / site / labour map for day-to-day "
                        "delivery from ops records"
                    ),
                    "required_records": "Ops site register + asset list + labour roster",
                    "decision_effect": "Operational failure modes cannot be grounded without a map",
                    "priority": "mandatory_pre_decision",
                    "owner": "ops diligence lead",
                    "timing": "before IC",
                    "closure_test": "process_asset_site_labour_map QA PASS",
                    "interim_treatment": "BLOCKED — do not invent an ops map",
                }
            )
        )
    if _qa_fail("capacity_utilisation"):
        out.append(
            normalize_question(
                {
                    "question": "Provide capacity and utilisation vs current and planned volume",
                    "required_records": "Capacity pack + utilisation series + plan volumes",
                    "decision_effect": "Plan ramp may bind capacity without this evidence",
                    "priority": "signing_condition",
                    "owner": "ops diligence lead",
                    "timing": "per deal timetable",
                    "closure_test": "capacity_utilisation QA PASS",
                    "interim_treatment": "LIMITED — flag capacity as untested vs plan",
                }
            )
        )
    if _qa_fail("incident_maintenance_insurance"):
        out.append(
            normalize_question(
                {
                    "question": (
                        "Provide incident log, maintenance schedule and insurance / BI "
                        "cover evidence"
                    ),
                    "required_records": "Incident register + PM schedule + insurance certificates",
                    "decision_effect": "Cannot size absorbability without incident/insurance packs",
                    "priority": "signing_condition",
                    "owner": "ops / insurance diligence",
                    "timing": "per deal timetable",
                    "closure_test": "incident_maintenance_insurance QA PASS",
                    "interim_treatment": "LIMITED — do not invent cover from proxies",
                }
            )
        )
    if _qa_fail("disruption_to_pnl_cash"):
        out.append(
            normalize_question(
                {
                    "question": (
                        "Size each material disruption to revenue, EBITDA and cash "
                        "at the observed recurrence rate"
                    ),
                    "required_records": "Incident cost bridge + P&L / cash impact schedule",
                    "decision_effect": "EBITDA-only sizing understates cash at risk",
                    "priority": "signing_condition",
                    "owner": "financial / ops diligence",
                    "timing": "before IC",
                    "closure_test": "disruption_to_pnl_cash QA PASS",
                    "interim_treatment": "LIMITED — withhold unsigned cash impacts",
                }
            )
        )
    if _qa_fail("continuity_tested_vs_untested"):
        out.append(
            normalize_question(
                {
                    "question": (
                        "List continuity / BCP arrangements and whether each has been "
                        "used or tested"
                    ),
                    "required_records": "BCP register + drill / invocation evidence",
                    "decision_effect": "Untested continuity overstates absorbability",
                    "priority": "signing_condition",
                    "owner": "ops diligence lead",
                    "timing": "per deal timetable",
                    "closure_test": "continuity_tested_vs_untested QA PASS",
                    "interim_treatment": "LIMITED — treat untested plans as unproven",
                }
            )
        )
    if _qa_fail("growth_bottleneck_cash_flow"):
        out.append(
            normalize_question(
                {
                    "question": (
                        "Reconcile growth-plan ops bottlenecks with Cash Flow "
                        "(WC / liquidity / funding)"
                    ),
                    "required_records": "Cash Flow agent output + plan capacity bridge",
                    "decision_effect": "Ops capacity claims may contradict funding reality",
                    "priority": "mandatory_pre_decision",
                    "owner": "financial diligence lead",
                    "timing": "before IC",
                    "closure_test": "growth_bottleneck_cash_flow QA PASS",
                    "interim_treatment": "LIMITED — do not credit unfunded capacity ramps",
                }
            )
        )
    if _qa_fail("no_invented_cyber_insurance"):
        out.append(
            normalize_question(
                {
                    "question": (
                        "Remove cyber/insurance claims grounded only in weak IT proxies; "
                        "supply real cyber incident / insurance evidence or label hypotheses"
                    ),
                    "required_records": "Cyber control report and/or insurance certificates",
                    "decision_effect": "Invented cyber/insurance distorts the risk register",
                    "priority": "mandatory_pre_decision",
                    "owner": "ops / cyber diligence",
                    "timing": "before IC",
                    "closure_test": "no_invented_cyber_insurance QA PASS",
                    "interim_treatment": "Strip proxy claims; reliance LIMITED",
                }
            )
        )
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
    cash_flow_spec: dict[str, Any] | None = None,
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
    ops_map = _extract_ops_map(corpus_full)
    capacity = _extract_capacity_utilisation(corpus_full)
    incident_review = _extract_incident_maintenance_insurance(corpus_full)
    register, proxy_flags = _guard_cyber_insurance_proxies(
        register, incident_review, corpus_full,
    )
    sized = _extract_sized(register, corpus_full)
    controls = _extract_controls(register, corpus_full)
    continuity = _extract_continuity_ops(corpus_full, controls)
    hist_plan = _extract_historical_vs_plan(register, corpus_full)
    bottleneck_cf = _reconcile_growth_bottlenecks(
        hist_plan=hist_plan, capacity=capacity, cash_flow_spec=cash_flow_spec,
    )
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
        _OPS_MAP_RULE,
        _UTIL_RULE,
        _INCIDENT_RULE,
        _CASH_IMPACT_RULE,
        _CONTINUITY_OPS_RULE,
        _BOTTLENECK_CF_RULE,
        _NO_PROXY_RULE,
    ]
    if proxy_flags:
        notes.append(_NO_PROXY_RULE + " " + proxy_flags[0])
    if bottleneck_cf.get("conflicts"):
        notes.append(
            f"Cash Flow bottleneck reconcile: {len(bottleneck_cf['conflicts'])} conflict(s)."
        )
    for n in (legacy.get("integrity_notes") or [])[:3]:
        if isinstance(n, str) and n.strip():
            notes.append(_soften_invest(_clean(n, 240)))

    ops_qa = _ops_evidence_qa(
        ops_map=ops_map,
        capacity=capacity,
        incident_review=incident_review,
        sized=sized,
        continuity=continuity,
        bottleneck_cf=bottleneck_cf,
        proxy_flags=proxy_flags,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in ops_qa)

    quality, reliance, rationale = _quality_reliance(
        register=register, sized=sized, controls=controls, priced=priced,
    )
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        rationale = "Ops evidence QA has open FAILs — reliance limited. " + rationale
    if bottleneck_cf.get("conflicts"):
        quality = "REWORK"
        rationale = "Growth-bottleneck vs Cash Flow conflicts — rework. " + rationale

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

    out = {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "ops_map": ops_map,
        "capacity_utilisation": capacity,
        "incident_maintenance_insurance": incident_review,
        "risk_register": register,
        "sized_risks": sized,
        "controls": controls,
        "continuity_arrangements": continuity,
        "historical_vs_plan": hist_plan,
        "growth_bottleneck_reconcile": bottleneck_cf,
        "priced_vs_noise": priced,
        "proxy_flags": proxy_flags,
        "ops_evidence_qa": ops_qa,
        # Legacy dual-write
        "kpi_gaps": kpi_gaps,
        "risk_items": risk_items,
        "integrity_notes": notes[:12],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": evidenced_n == 0 and not kpi_gaps and not risk_items,
    }
    out["questions"] = _questions_from_ops_gaps(out)
    return out


def _llm_operational_risk_spec(
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
    cash_flow_spec: dict[str, Any] | None = None,
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
    cf_blob = ""
    if isinstance(cash_flow_spec, dict) and cash_flow_spec:
        cf_blob = (
            "\nCASH_FLOW_SPEC (reconcile growth bottlenecks — do not contradict):\n"
            + str({
                "cash_metrics": cash_flow_spec.get("cash_metrics"),
                "working_capital": cash_flow_spec.get("working_capital"),
                "liquidity": cash_flow_spec.get("liquidity"),
            })[:3_000]
            + "\n"
        )
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n"
        f"{cf_blob}\n"
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "ops_map: [{element_type (process|asset|site|labour), name, evidence, source, notes}],\n"
        "capacity_utilisation: [{stage, current_capacity, utilisation, headroom, when_binds, "
        "source, notes}],\n"
        "incident_maintenance_insurance: [{review_type, finding, source, notes}],\n"
        "risk_register: [{risk, category, evidence, record_type, hypothesis, "
        "test_request, source, notes}],\n"
        "sized_risks: [{risk, frequency, cost, revenue_impact, ebitda_if_recurs, cash_impact, "
        "sized, source, notes}],\n"
        "controls: [{risk, control, tested, mitigation_status, source, notes}],\n"
        "continuity_arrangements: [{arrangement, tested_or_used, mitigation_status, source, notes}],\n"
        "historical_vs_plan: [{risk, bucket, plan_driver, source, notes}],\n"
        "priced_vs_noise: [{risk, classification, rationale, source, notes}],\n"
        "ops_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
        "process_asset_site_labour_map, capacity_utilisation, incident_maintenance_insurance, "
        "disruption_to_pnl_cash, continuity_tested_vs_untested, growth_bottleneck_cash_flow, "
        "no_invented_cyber_insurance,\n"
        "questions: [{question, required_records, decision_effect, priority, owner, "
        "timing, closure_test, interim_treatment}],\n"
        "kpi_gaps: [{kpi, status}], risk_items: [{risk, likelihood, impact}],\n"
        "integrity_notes: [string],\n"
        "quality_verdict (PASS|REWORK), reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Derive risks ONLY from records — no generic taxonomy. "
        "Untested controls are not mitigation. Label hypotheses. "
        "Do not invent cyber/insurance from weak IT proxies. "
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
    cash_flow_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    heur = _heuristic_operational_risk_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy,
        cash_flow_spec=cash_flow_spec,
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

    ops_map = _rows("ops_map", "name") or heur.get("ops_map") or []
    llm["ops_map"] = ops_map
    capacity = _rows("capacity_utilisation", "stage") or heur.get("capacity_utilisation") or []
    llm["capacity_utilisation"] = capacity
    incident_review = (
        _rows("incident_maintenance_insurance", "review_type")
        or heur.get("incident_maintenance_insurance")
        or []
    )
    llm["incident_maintenance_insurance"] = incident_review

    register, proxy_flags = _guard_cyber_insurance_proxies(
        register, incident_review, corpus,
    )
    llm["risk_register"] = register
    llm["proxy_flags"] = proxy_flags or list(heur.get("proxy_flags") or [])

    sized = _rows("sized_risks", "risk")
    for row in sized:
        if not row.get("cash_impact"):
            row["cash_impact"] = _info_request("cash / liquidity impact if recurs")
        if not row.get("revenue_impact"):
            row["revenue_impact"] = _info_request("revenue impact if recurs")
        row["notes"] = f"{_SIZE_RULE} {_CASH_IMPACT_RULE}"
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

    continuity = _rows("continuity_arrangements", "arrangement")
    if not continuity:
        continuity = heur.get("continuity_arrangements") or _extract_continuity_ops(
            corpus, controls,
        )
    for row in continuity:
        row["notes"] = _CONTINUITY_OPS_RULE
    llm["continuity_arrangements"] = continuity

    hist = _rows("historical_vs_plan", "risk")
    for row in hist:
        row["notes"] = _PLAN_RULE
    llm["historical_vs_plan"] = hist

    bottleneck_cf = _reconcile_growth_bottlenecks(
        hist_plan=hist, capacity=capacity, cash_flow_spec=cash_flow_spec,
    )
    llm["growth_bottleneck_reconcile"] = bottleneck_cf

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
        _OPS_MAP_RULE, _UTIL_RULE, _INCIDENT_RULE, _CASH_IMPACT_RULE,
        _CONTINUITY_OPS_RULE, _BOTTLENECK_CF_RULE, _NO_PROXY_RULE,
    ):
        if not any(rule[:28].lower() in x.lower() for x in notes):
            notes.append(rule)
    if not notes:
        notes = heur["integrity_notes"]
    llm["integrity_notes"] = notes[:12]

    ops_qa = _ops_evidence_qa(
        ops_map=ops_map,
        capacity=capacity,
        incident_review=incident_review,
        sized=sized,
        continuity=continuity,
        bottleneck_cf=bottleneck_cf,
        proxy_flags=llm["proxy_flags"],
    )
    llm["ops_evidence_qa"] = ops_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in ops_qa)

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
    if bottleneck_cf.get("conflicts"):
        llm["quality_verdict"] = "REWORK"
    if qa_fail and llm["reliance_verdict"] == "READY":
        llm["reliance_verdict"] = "LIMITED"
        llm["quality_reliance_rationale"] = (
            "Ops evidence QA has open FAILs — reliance limited. "
            + _clean(llm.get("quality_reliance_rationale"), 300)
        )

    if not llm.get("questions"):
        llm["questions"] = _questions_from_ops_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in llm.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_ops_gaps(llm)

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
    cash_flow_spec: dict[str, Any] | None = None,
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
            deal_perimeter=vars_.get("deal_perimeter"),
            transaction_type=vars_.get("transaction_type"),
            as_of_date=vars_.get("as_of_date"),
            review_periods=vars_.get("review_periods"),
            decision_stage=vars_.get("decision_stage"),
            cash_flow_spec=cash_flow_spec,
        )
        if llm:
            out = _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
                cash_flow_spec=cash_flow_spec,
            )
            out["deal_slots"] = {k: v for k, v in vars_.items() if v}
            return out

    heur = _heuristic_operational_risk_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
        cash_flow_spec=cash_flow_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return heur


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
    ops_map = spec.get("ops_map") if isinstance(spec.get("ops_map"), list) else []
    capacity = (
        spec.get("capacity_utilisation")
        if isinstance(spec.get("capacity_utilisation"), list) else []
    )
    incident_review = (
        spec.get("incident_maintenance_insurance")
        if isinstance(spec.get("incident_maintenance_insurance"), list) else []
    )
    continuity = (
        spec.get("continuity_arrangements")
        if isinstance(spec.get("continuity_arrangements"), list) else []
    )
    bottleneck = (
        spec.get("growth_bottleneck_reconcile")
        if isinstance(spec.get("growth_bottleneck_reconcile"), dict) else {}
    )
    kpi_gaps = spec.get("kpi_gaps") if isinstance(spec.get("kpi_gaps"), list) else []
    risk_items = spec.get("risk_items") if isinstance(spec.get("risk_items"), list) else []
    notes = spec.get("integrity_notes") if isinstance(spec.get("integrity_notes"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_NO_PROXY_RULE}\n\n")

    # 1
    parts.append("## 1. Evidence-Derived Risk Register\n\n")
    parts.append(f"{_REGISTER_RULE}\n\n")
    if ops_map:
        parts.append(f"### Process / asset / site / labour map\n\n{_OPS_MAP_RULE}\n\n")
        parts.append(_table(
            ["Type", "Name", "Evidence", "Source"],
            [
                [
                    _clean(r.get("element_type"), 20),
                    _clean(r.get("name"), 80),
                    _clean(r.get("evidence"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in ops_map if isinstance(r, dict)
            ],
        ))
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
    parts.append("## 2. Sized Risks (Revenue / EBITDA / Cash)\n\n")
    parts.append(f"{_SIZE_RULE} {_CASH_IMPACT_RULE}\n\n")
    if capacity:
        parts.append(f"### Capacity & utilisation\n\n{_UTIL_RULE}\n\n")
        parts.append(_table(
            ["Stage", "Capacity", "Utilisation", "Headroom", "When binds", "Source"],
            [
                [
                    _clean(r.get("stage"), 40),
                    _clean(r.get("current_capacity"), 80),
                    _clean(r.get("utilisation"), 40),
                    _clean(r.get("headroom"), 80),
                    _clean(r.get("when_binds"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in capacity if isinstance(r, dict)
            ],
        ))
    if sized:
        parts.append(_table(
            ["Risk", "Frequency", "Cost", "Revenue", "EBITDA", "Cash", "Sized?", "Source"],
            [
                [
                    _clean(r.get("risk"), 80),
                    _clean(r.get("frequency"), 50),
                    _clean(r.get("cost"), 50),
                    _clean(r.get("revenue_impact"), 50),
                    _clean(r.get("ebitda_if_recurs"), 80),
                    _clean(r.get("cash_impact"), 60),
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
    parts.append("## 3. Controls, Continuity & Reviews\n\n")
    parts.append(f"{_CONTROL_RULE} {_CONTINUITY_OPS_RULE}\n\n")
    if incident_review:
        parts.append(f"### Incident / maintenance / insurance\n\n{_INCIDENT_RULE}\n\n")
        parts.append(_table(
            ["Type", "Finding", "Source"],
            [
                [
                    _clean(r.get("review_type"), 20),
                    _clean(r.get("finding"), 180),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in incident_review if isinstance(r, dict)
            ],
        ))
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
    if continuity:
        parts.append("### Continuity arrangements (tested vs untested)\n\n")
        parts.append(_table(
            ["Arrangement", "Used or tested?", "Mitigation status", "Source"],
            [
                [
                    _clean(r.get("arrangement"), 140),
                    _clean(r.get("tested_or_used"), 40),
                    _clean(r.get("mitigation_status"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in continuity if isinstance(r, dict)
            ],
        ))
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
    parts.append(f"### Growth-bottleneck ↔ Cash Flow\n\n{_BOTTLENECK_CF_RULE}\n\n")
    parts.append(_table(
        ["Item", "Statement"],
        [
            [
                "Cash Flow present",
                "Yes" if bottleneck.get("cash_flow_present") else "No",
            ],
            ["Plan bottlenecks", str(bottleneck.get("plan_bottlenecks") or 0)],
            ["Capacity binds", str(bottleneck.get("capacity_binds") or 0)],
            [
                "Aligned",
                "; ".join(
                    _clean(a, 120) for a in (bottleneck.get("aligned") or [])[:3]
                    if isinstance(a, str)
                ) or "—",
            ],
            [
                "Conflicts",
                "; ".join(
                    _clean(c, 120) for c in (bottleneck.get("conflicts") or [])[:3]
                    if isinstance(c, str)
                ) or "None",
            ],
            ["Notes", _clean(bottleneck.get("notes"), 280)],
        ],
    ))
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
        "mitigation. Hypotheses are labelled and request what would test them. "
        f"{_NO_PROXY_RULE}*\n\n"
    )
    parts.append("---\n\n")

    # 6
    ops_qa = (
        spec.get("ops_evidence_qa")
        if isinstance(spec.get("ops_evidence_qa"), list)
        else []
    )
    parts.append("## 6. Operational Risk Evidence QA\n\n")
    parts.append(
        "QA enforces ops map, capacity/utilisation, incident/maintenance/insurance, "
        "disruption → P&L/cash, continuity tested vs untested, growth-bottleneck "
        "Cash Flow reconcile, and no invented cyber/insurance from weak proxies.\n\n"
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
                for r in ops_qa
                if isinstance(r, dict)
            ],
        )
        or f"{_info_request('ops evidence QA rows')}\n\n"
    )
    parts.append("---\n\n")

    # 7
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    parts.append("## 7. Questions and Inputs Required\n\n")
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
        parts.append(f"{_info_request('Questions for material operational-risk gaps')}\n\n")
    parts.append("---\n\n")

    # 8
    parts.append("## 8. Quality & Reliance\n\n")
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
        for n in notes[:8]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This document builds an operational risk register from evidence and sizes "
        "what each failure mode would cost. Open ops-evidence QA FAILs cap READY → LIMITED. "
        "It does not recommend invest or pass.*\n\n"
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
