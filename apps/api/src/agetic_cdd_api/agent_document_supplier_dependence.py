"""Compose DiligenceIQ Supplier Dependence — vendor criticality & contracts (prompt book).

Identifies vendors the business cannot easily replace and contract protection.
Spend from payables is one measure; operational criticality is rated separately.
Contract terms only from executed documents that were read. Substitutability
tested (alternatives, qualification, time, cost). Change-of-control consents
flagged. Named supplier is not automatically sole source — evidence vs assumption
is stated, and reconciled with supply chain resilience.

No invest/pass. No company allowlists. Preserves legacy Vendor Concentration
Risk Analysis shape (vendors / concentration_flags / dependency_notes).
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

_DOCUMENT_TITLE = "Vendor Concentration Risk Analysis"
_DD_CODE = "DD-22"

_SOLE_SOURCE_RULE = (
    "A named supplier is **not** automatically sole source — say which "
    "dependencies are evidenced and which are assumed."
)
_CRITICALITY_RULE = (
    "Operational criticality is rated **separately** from spend: what stops "
    "if this supplier stops?"
)
_CONTRACT_RULE = (
    "Contract terms are taken only from executed documents that were read — "
    "unread terms are not stated."
)
_COC_RULE = (
    "Change-of-control consents that the transaction would trigger are flagged."
)
_RESILIENCE_RULE = (
    "Dependencies are reconciled with supply chain resilience findings where available."
)

_SPEND_SHARE_RE = re.compile(
    r"(?i)([A-Z][A-Za-z0-9&'.\- ]{1,40}?)\s+"
    r"(?:spend|payables?|annual\s+value|purchases?)?\s*"
    r"(?:INR|Rs\.?|₹)?\s*~?([\d,]+(?:\.\d+)?)\s*(?:Cr|cr|crore)?\s*"
    r"(?:\(?(\d+(?:\.\d+)?)\s*%\)?)?"
)
_TOTAL_SPEND_RE = re.compile(
    r"(?i)(?:total\s+(?:supplier\s+)?(?:spend|payables)|payables\s+ledger\s+total)"
    r"[^.\d]{0,40}?([\d,]+(?:\.\d+)?)\s*(?:Cr|cr)?"
)
_CRITICAL_CUE = re.compile(
    r"(?i)\b(critical|single[- ]source|sole[- ]source|no\s+alternative|"
    r"cannot\s+(?:easily\s+)?replace|stops?\s+if|bottleneck|key\s+supplier)\b"
)
_CONTRACT_CUE = re.compile(
    r"(?i)\b(executed\s+contract|MSA|supply\s+agreement|framework\s+agreement|"
    r"termination\s+(?:for\s+convenience|rights)|change[- ]of[- ]control|"
    r"assignment\s+clause|exclusivity|SLA|service\s+level)\b"
)
_SWITCH_CUE = re.compile(
    r"(?i)\b(switch(?:ing)?|substitut|alternate|alternative|qualify|qualification|"
    r"lead\s+time|months?\s+to\s+(?:qualify|switch)|switching\s+cost)\b"
)
_COC_CUE = re.compile(
    r"(?i)\b(change[- ]of[- ]control|CoC\s+consent|assignment\s+consent|"
    r"transaction\s+would\s+trigger|consent\s+required)\b"
)
_EVIDENCED_CUE = re.compile(
    r"(?i)\b(evidenced|documented|ledger|executed|payables|contract\s+pack)\b"
)
_ASSUMED_CUE = re.compile(
    r"(?i)\b(assumed|inference|inferred|likely|appears?\s+to|management\s+said)\b"
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
    out = _INVEST_LANG.sub("supplier evidence only — no deal verdict expressed", raw)
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


def gather_supplier_dependence_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "operations": 0,
        "financial": 1,
        "legal_esg": 2,
        "customer": 3,
        "deal_strategy": 4,
        "market_competition": 5,
    }
    needles = (
        "supplier", "vendor", "payable", "operational", "manufacturing",
        "supply", "contract", "procurement", "bom", "localization",
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


def _legacy_vendors(legacy: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in legacy.get("vendors") or []:
        if isinstance(row, dict) and row.get("name"):
            out.append({
                "name": _clean(row.get("name"), 80),
                "component": _clean(row.get("component"), 80),
                "country": _clean(row.get("country"), 40),
                "annual_value_inr_cr": _num(row.get("annual_value_inr_cr")),
                "risk_level": _clean(row.get("risk_level"), 20) or None,
                "alternate_available": _clean(row.get("alternate_available"), 40) or None,
            })
        elif hasattr(row, "name"):
            out.append({
                "name": _clean(getattr(row, "name", ""), 80),
                "component": _clean(getattr(row, "component", ""), 80),
                "country": _clean(getattr(row, "country", ""), 40),
                "annual_value_inr_cr": _num(getattr(row, "annual_value_inr_cr", None)),
                "risk_level": _clean(getattr(row, "risk_level", ""), 20) or None,
                "alternate_available": _clean(getattr(row, "alternate_available", ""), 40) or None,
            })
    return out


def _extract_vendors_from_corpus(corpus: str, legacy: dict[str, Any]) -> list[dict[str, Any]]:
    from agetic_cdd_api.deep_dive_ops import _parse_vendors

    parsed = _parse_vendors(corpus or "")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for v in parsed:
        key = str(v.name or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "name": v.name,
            "component": v.component or "",
            "country": v.country or "",
            "annual_value_inr_cr": v.annual_value_inr_cr,
            "risk_level": v.risk_level,
            "alternate_available": v.alternate_available,
        })
    for row in _legacy_vendors(legacy):
        key = str(row.get("name") or "").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(row)
    return out[:12]


def _build_spend_table(
    vendors: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, Any]]:
    """Spend + share of total; share computed when ledger total or row shares exist."""
    text = _prose(corpus)
    total_m = _TOTAL_SPEND_RE.search(text)
    total = _num(total_m.group(1)) if total_m else None
    values = [v.get("annual_value_inr_cr") for v in vendors if v.get("annual_value_inr_cr") is not None]
    if total is None and values:
        total = sum(float(x) for x in values if x is not None)

    period = _NA
    per_m = re.search(r"(?i)(?:FY|CY)\s?20\d{2}(?:[–\-]\d{2})?|FY\d{2}", text)
    if per_m:
        period = _clean(per_m.group(0), 20)

    rows: list[dict[str, Any]] = []
    for v in vendors:
        spend = v.get("annual_value_inr_cr")
        share = None
        if spend is not None and total and total > 0:
            share = round(100.0 * float(spend) / float(total), 1)
        rows.append({
            "supplier": v.get("name") or _NA,
            "period": period,
            "spend": f"{spend:g} Cr" if spend is not None else _info_request("payables spend"),
            "share_of_total_pct": (
                f"{share:g}%" if share is not None
                else _info_request("share of total payables spend")
            ),
            "component": v.get("component") or _NA,
            "country": v.get("country") or _NA,
            "source": _DOC_CITE if spend is not None else _NA,
            "ledger_evidenced": spend is not None,
        })
    if not rows:
        rows.append({
            "supplier": _info_request("supplier list from payables ledger"),
            "period": period,
            "spend": _NA,
            "share_of_total_pct": _NA,
            "component": _NA,
            "country": _NA,
            "source": _NA,
            "ledger_evidenced": False,
        })
    return rows


def _rate_criticality(
    vendors: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, str]]:
    text = _prose(corpus)
    out: list[dict[str, str]] = []
    for v in vendors:
        name = str(v.get("name") or "")
        if not name:
            continue
        local = " ".join(
            s for s in _sentences(text)
            if name.lower()[:8] in s.lower()
            or (v.get("component") and str(v["component"]).lower()[:6] in s.lower())
        )
        hay = local or text
        stops = _NA
        if _CRITICAL_CUE.search(hay) or (v.get("risk_level") or "").lower() == "high":
            stops = _clean(
                next(
                    (
                        s for s in _sentences(hay)
                        if _CRITICAL_CUE.search(s)
                        or name.lower()[:6] in s.lower()
                    ),
                    f"High-risk / constrained supply for {name} — production/service impact if interrupted.",
                ),
                200,
            )
        alt = v.get("alternate_available")
        spend = v.get("annual_value_inr_cr")
        # Criticality separate from spend: low spend + no alt can outrank high spend commodity
        if alt and str(alt).lower() in {"no", "none", "n/a"}:
            rating = "Critical"
            if not _is_filled(stops) or stops == _NA:
                stops = (
                    f"No alternate evidenced for {name} — what stops is the "
                    f"{v.get('component') or 'supplied input'} stream. {_CRITICALITY_RULE}"
                )
        elif (v.get("risk_level") or "").lower() == "high":
            rating = "High"
        elif (v.get("risk_level") or "").lower() == "medium":
            rating = "Medium"
        elif alt and str(alt).lower() in {"yes", "partial"}:
            rating = "Lower (alternates noted)"
        else:
            rating = _info_request(f"operational criticality for {name} (separate from spend)")

        spend_note = (
            f"Spend {spend:g} Cr is not the criticality rating."
            if spend is not None else _CRITICALITY_RULE
        )
        out.append({
            "supplier": name,
            "criticality": rating,
            "what_stops": stops if stops != _NA else _info_request(f"what stops if {name} stops"),
            "spend_vs_criticality": spend_note,
            "source": _DOC_CITE if _CRITICAL_CUE.search(hay) or v.get("risk_level") or alt else _NA,
        })
    if not out:
        out.append({
            "supplier": _info_request("critical suppliers"),
            "criticality": _info_request("operational criticality separate from spend"),
            "what_stops": _info_request("what stops if each critical supplier stops"),
            "spend_vs_criticality": _CRITICALITY_RULE,
            "source": _NA,
        })
    return out


def _extract_contract_terms(
    vendors: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, str]]:
    text = _prose(corpus)
    has_contract_lang = bool(_CONTRACT_CUE.search(text))
    critical_names = [
        v.get("name") for v in vendors
        if (v.get("risk_level") or "").lower() == "high"
        or (v.get("alternate_available") or "").lower() in {"no", "none"}
    ]
    if not critical_names:
        critical_names = [v.get("name") for v in vendors[:3] if v.get("name")]

    fields = (
        "duration", "renewal", "pricing_mechanism", "service_levels",
        "termination_rights", "assignment", "change_of_control", "exclusivity",
    )
    out: list[dict[str, str]] = []
    for name in critical_names:
        if not name:
            continue
        local_sents = [
            s for s in _sentences(text)
            if str(name).lower()[:6] in s.lower() and _CONTRACT_CUE.search(s)
        ]
        row: dict[str, str] = {
            "supplier": str(name),
            "contract_read": "Yes" if local_sents or (
                has_contract_lang and str(name).lower()[:6] in text.lower()
            ) else "No — terms not stated",
            "source": _DOC_CITE if local_sents else _NA,
        }
        # Only fill terms when wording appears near the supplier or in clear contract excerpts
        for field in fields:
            pattern = {
                "duration": r"(?i)\b(term|duration|years?|months?)\b",
                "renewal": r"(?i)\b(renewal|auto[- ]renew|extend)\b",
                "pricing_mechanism": r"(?i)\b(pricing|price\s+escalat|index|fixed\s+price)\b",
                "service_levels": r"(?i)\b(SLA|service\s+level|OTIF|delivery\s+standard)\b",
                "termination_rights": r"(?i)\b(termination|terminate|for\s+convenience)\b",
                "assignment": r"(?i)\b(assignment|assignable|anti[- ]assignment)\b",
                "change_of_control": r"(?i)\b(change[- ]of[- ]control|CoC)\b",
                "exclusivity": r"(?i)\b(exclusiv|sole\s+supply)\b",
            }[field]
            hit = next(
                (s for s in (local_sents or _sentences(text)[:40]) if re.search(pattern, s)),
                None,
            )
            if hit and (local_sents or (has_contract_lang and str(name).lower()[:6] in hit.lower())):
                row[field] = _clean(hit, 160)
            else:
                row[field] = (
                    _info_request(f"executed contract — {field.replace('_', ' ')} for {name}")
                    if row["contract_read"].startswith("No")
                    else _NA
                )
        # Enforce unread rule
        if row["contract_read"].startswith("No"):
            for field in fields:
                if _is_filled(row.get(field)) and not str(row[field]).startswith("Information"):
                    # Should not quote unread terms
                    row[field] = _info_request(f"read executed contract for {name} before stating {field.replace('_', ' ')}")
            row["notes"] = _CONTRACT_RULE
        else:
            row["notes"] = _CONTRACT_RULE
        out.append(row)
    if not out:
        out.append({
            "supplier": _info_request("critical supplier contracts"),
            "contract_read": "No — terms not stated",
            "duration": _NA,
            "renewal": _NA,
            "pricing_mechanism": _NA,
            "service_levels": _NA,
            "termination_rights": _NA,
            "assignment": _NA,
            "change_of_control": _NA,
            "exclusivity": _NA,
            "source": _NA,
            "notes": _CONTRACT_RULE,
        })
    return out


def _extract_substitutability(
    vendors: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, str]]:
    text = _prose(corpus)
    out: list[dict[str, str]] = []
    for v in vendors:
        name = str(v.get("name") or "")
        if not name:
            continue
        if (v.get("risk_level") or "").lower() not in {"high", "medium"} and (
            v.get("alternate_available") or ""
        ).lower() not in {"no", "none", "partial", ""}:
            # Still include high-spend top vendors
            if (v.get("annual_value_inr_cr") or 0) < 5:
                continue
        local = " ".join(
            s for s in _sentences(text)
            if name.lower()[:6] in s.lower() or _SWITCH_CUE.search(s)
        )
        alt = v.get("alternate_available")
        alternatives = (
            f"Alternate available: {alt}" if alt
            else _info_request(f"alternatives in geography for {name}")
        )
        if alt and str(alt).lower() in {"no", "none"}:
            alternatives = f"No alternate evidenced in packs for {name}."
        switch_time = _NA
        switch_cost = _NA
        qualify = _info_request(f"qualification requirements to switch from {name}")
        for s in _sentences(local or text):
            if re.search(r"(?i)(\d+)\s*(months?|weeks?|years?).{0,40}(switch|qualif|alternate)", s):
                switch_time = _clean(s, 160)
            if re.search(r"(?i)(switch(?:ing)?\s+cost|cost\s+to\s+switch|INR).{0,40}switch", s):
                switch_cost = _clean(s, 160)
            if re.search(r"(?i)qualif", s) and name.lower()[:5] in s.lower():
                qualify = _clean(s, 160)
        if switch_time == _NA:
            switch_time = _info_request(f"time to switch from {name}")
        if switch_cost == _NA:
            switch_cost = _info_request(f"cost to switch from {name}")
        # Sole-source guard
        sole = "Assumed sole source — not evidenced" if (
            alt and str(alt).lower() in {"no", "none"} and not _EVIDENCED_CUE.search(local or "")
        ) else (
            "Sole/limited source evidenced" if alt and str(alt).lower() in {"no", "none"}
            else "Not automatically sole source"
        )
        out.append({
            "supplier": name,
            "alternatives": alternatives,
            "qualification": qualify,
            "switch_time": switch_time,
            "switch_cost": switch_cost,
            "sole_source_status": f"{sole}. {_SOLE_SOURCE_RULE}",
            "source": _DOC_CITE if alt or _SWITCH_CUE.search(local or "") else _NA,
        })
        if len(out) >= 8:
            break
    if not out:
        out.append({
            "supplier": _info_request("critical suppliers for substitutability test"),
            "alternatives": _info_request("alternatives in geography"),
            "qualification": _info_request("qualification needed"),
            "switch_time": _info_request("time to switch"),
            "switch_cost": _info_request("cost to switch"),
            "sole_source_status": _SOLE_SOURCE_RULE,
            "source": _NA,
        })
    return out


def _extract_change_of_control(corpus: str, contracts: list[dict]) -> dict[str, Any]:
    text = _prose(corpus)
    hits = [s for s in _sentences(text) if _COC_CUE.search(s)]
    from_contracts = [
        c for c in contracts
        if isinstance(c, dict) and _is_filled(c.get("change_of_control"))
        and not str(c.get("change_of_control")).startswith("Information")
        and str(c.get("change_of_control")) != _NA
    ]
    flagged = bool(hits or from_contracts)
    consents: list[str] = []
    for s in hits[:4]:
        consents.append(_clean(s, 200))
    for c in from_contracts[:4]:
        consents.append(f"{c.get('supplier')}: {_clean(c.get('change_of_control'), 160)}")
    return {
        "transaction_triggers_flagged": flagged,
        "consents": consents or [
            _info_request("change-of-control / assignment consents the transaction would trigger")
        ],
        "notes": _COC_RULE,
        "source": _DOC_CITE if flagged else _NA,
    }


def _extract_evidence_status(
    vendors: list[dict[str, Any]],
    spend_rows: list[dict],
    corpus: str,
) -> dict[str, Any]:
    text = _prose(corpus)
    evidenced: list[str] = []
    assumed: list[str] = []
    for row in spend_rows:
        if row.get("ledger_evidenced"):
            evidenced.append(f"Spend for {row.get('supplier')} from payables/vendor pack.")
    for v in vendors:
        if v.get("alternate_available"):
            evidenced.append(
                f"Alternate status for {v.get('name')}: {v.get('alternate_available')}."
            )
        elif (v.get("risk_level") or "").lower() == "high":
            assumed.append(
                f"High risk for {v.get('name')} without alternate status — dependence partially assumed."
            )
    for s in _pick_sentences(
        _sentences(text),
        keywords=("assumed", "inferred", "likely sole", "appears dependent"),
        limit=3,
    ):
        assumed.append(_clean(s, 180))
    if not evidenced and not assumed:
        evidenced.append(_info_request("mark each dependency as evidenced vs assumed"))
    return {
        "evidenced": evidenced[:6],
        "assumed": assumed[:6],
        "sole_source_rule": _SOLE_SOURCE_RULE,
        "resilience_reconcile": _RESILIENCE_RULE,
        "notes": (
            "Reconcile supplier dependence with supply_chain_resilience localization / "
            "logistics findings; do not treat naming a vendor as proving sole-source status."
        ),
    }


def _quality_reliance(
    *,
    spend_rows: list[dict],
    criticality: list[dict],
    contracts: list[dict],
    substitutability: list[dict],
    coc: dict,
) -> tuple[str, str, str]:
    ledger_n = sum(1 for r in spend_rows if r.get("ledger_evidenced"))
    crit_n = sum(
        1 for r in criticality
        if _is_filled(r.get("criticality")) and not str(r.get("criticality")).startswith("Information")
    )
    contract_read = sum(
        1 for r in contracts
        if str(r.get("contract_read") or "").lower().startswith("yes")
    )
    switch_n = sum(
        1 for r in substitutability
        if _is_filled(r.get("alternatives")) and not str(r.get("alternatives")).startswith("Information")
    )

    if ledger_n and crit_n and (contract_read or switch_n):
        reliance = "READY" if contract_read and coc.get("transaction_triggers_flagged") else "LIMITED"
        return (
            "PASS",
            reliance,
            f"Payables spend for {ledger_n} supplier(s); criticality separate from spend; "
            f"{contract_read} contract(s) read; {switch_n} substitutability row(s). "
            f"{_SOLE_SOURCE_RULE} {_CONTRACT_RULE}",
        )
    if ledger_n or crit_n:
        return (
            "PASS",
            "LIMITED",
            "Partial supplier evidence — contracts unread and/or substitutability thin. "
            f"{_CONTRACT_RULE} {_SOLE_SOURCE_RULE}",
        )
    return (
        "PASS",
        "BLOCKED",
        "No payables ledger spend, criticality ratings or executed supplier contracts were opened.",
    )


# ---------------------------------------------------------------------------
# heuristic / LLM / normalise / build / render
# ---------------------------------------------------------------------------


def _heuristic_supplier_dependence_spec(
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
    for note in (legacy.get("dependency_notes") or [])[:6]:
        if isinstance(note, str) and note.strip():
            extra += "\n" + note.strip()
    for flag in (legacy.get("concentration_flags") or [])[:4]:
        if isinstance(flag, str) and flag.strip():
            extra += "\n" + flag.strip()
    corpus_full = (corpus or "") + extra

    vendors = _extract_vendors_from_corpus(corpus_full, legacy)
    spend_rows = _build_spend_table(vendors, corpus_full)
    criticality = _rate_criticality(vendors, corpus_full)
    contracts = _extract_contract_terms(vendors, corpus_full)
    substitutability = _extract_substitutability(vendors, corpus_full)
    coc = _extract_change_of_control(corpus_full, contracts)
    evidence = _extract_evidence_status(vendors, spend_rows, corpus_full)

    flags: list[str] = []
    for f in (legacy.get("concentration_flags") or [])[:4]:
        if isinstance(f, str) and f.strip():
            flags.append(_clean(f, 200))
    high = [v for v in vendors if (v.get("risk_level") or "").lower() == "high"]
    if high:
        flags.append(
            f"{len(high)} vendor(s) rated HIGH risk (top: {high[0].get('name')})."
        )
    no_alt = [
        v for v in vendors
        if (v.get("alternate_available") or "").lower() in {"no", "none"}
    ]
    if no_alt:
        flags.append(
            "No-alternate suppliers: "
            + ", ".join(str(v.get("name")) for v in no_alt[:3])
            + f". {_SOLE_SOURCE_RULE}"
        )
    for s in _pick_sentences(
        _sentences(_prose(corpus_full)),
        keywords=("concentration", "china", "single-source", "import", "localization"),
        limit=3,
    ):
        line = _clean(s, 180)
        if line and line not in flags:
            flags.append(line)

    notes: list[str] = [
        _CRITICALITY_RULE,
        _CONTRACT_RULE,
        _SOLE_SOURCE_RULE,
        _COC_RULE,
        _RESILIENCE_RULE,
    ]
    for n in (legacy.get("dependency_notes") or [])[:4]:
        if isinstance(n, str) and n.strip():
            notes.append(_soften_invest(_clean(n, 240)))

    quality, reliance, rationale = _quality_reliance(
        spend_rows=spend_rows,
        criticality=criticality,
        contracts=contracts,
        substitutability=substitutability,
        coc=coc,
    )

    bits = [f"Supplier Dependence for {company}:"]
    bits.append(f"{len(vendors)} supplier(s) listed")
    bits.append(f"{sum(1 for r in spend_rows if r.get('ledger_evidenced'))} with ledger spend")
    bits.append(
        f"{sum(1 for c in contracts if str(c.get('contract_read','')).startswith('Yes'))} "
        f"contract(s) read"
    )
    bits.append(
        "CoC " + ("flagged" if coc.get("transaction_triggers_flagged") else "not evidenced")
    )

    return {
        "insight_snapshot": _soften_invest("; ".join(bits)),
        "spend_by_supplier": spend_rows,
        "operational_criticality": criticality,
        "contract_terms": contracts,
        "substitutability": substitutability,
        "change_of_control": coc,
        "evidence_status": evidence,
        # Legacy dual-write
        "vendors": vendors,
        "concentration_flags": flags[:6],
        "dependency_notes": notes[:8],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": not vendors and not any(r.get("ledger_evidenced") for r in spend_rows),
    }


def _llm_supplier_dependence_spec(
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
            "supplier_dependence",
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
        "spend_by_supplier: [{supplier, period, spend, share_of_total_pct, component, country, "
        "source, ledger_evidenced}],\n"
        "operational_criticality: [{supplier, criticality, what_stops, spend_vs_criticality, source}],\n"
        "contract_terms: [{supplier, contract_read, duration, renewal, pricing_mechanism, "
        "service_levels, termination_rights, assignment, change_of_control, exclusivity, source, notes}],\n"
        "substitutability: [{supplier, alternatives, qualification, switch_time, switch_cost, "
        "sole_source_status, source}],\n"
        "change_of_control: {transaction_triggers_flagged, consents: [string], notes, source},\n"
        "evidence_status: {evidenced: [string], assumed: [string], sole_source_rule, "
        "resilience_reconcile, notes},\n"
        "vendors: [{name, component, country, annual_value_inr_cr, risk_level, alternate_available}],\n"
        "concentration_flags: [string], dependency_notes: [string],\n"
        "quality_verdict (PASS|REWORK), reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT state contract terms you have not read. "
        "Do NOT treat a named supplier as automatically sole source. "
        "Rate criticality separately from spend. "
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
    heur = _heuristic_supplier_dependence_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy,
    )

    def _list_of_dicts(key: str, required: str) -> list[dict[str, Any]]:
        raw = llm.get(key) if isinstance(llm.get(key), list) else []
        cleaned = [r for r in raw if isinstance(r, dict) and r.get(required)]
        return cleaned or heur.get(key) or []

    llm["spend_by_supplier"] = _list_of_dicts("spend_by_supplier", "supplier")
    llm["operational_criticality"] = _list_of_dicts("operational_criticality", "supplier")

    contracts = _list_of_dicts("contract_terms", "supplier")
    # Enforce unread contract rule
    for row in contracts:
        if not str(row.get("contract_read") or "").lower().startswith("yes"):
            row["contract_read"] = "No — terms not stated"
            for field in (
                "duration", "renewal", "pricing_mechanism", "service_levels",
                "termination_rights", "assignment", "change_of_control", "exclusivity",
            ):
                if _is_filled(row.get(field)) and not str(row.get(field)).startswith("Information"):
                    # Drop unread quoted terms
                    row[field] = _info_request(
                        f"read executed contract before stating {field.replace('_', ' ')}"
                    )
            row["notes"] = _CONTRACT_RULE
        else:
            row["notes"] = _CONTRACT_RULE
    llm["contract_terms"] = contracts

    subst = _list_of_dicts("substitutability", "supplier")
    for row in subst:
        status = str(row.get("sole_source_status") or "")
        if "sole" in status.lower() and "not automatically" not in status.lower():
            if "evidenced" not in status.lower() and "assumed" not in status.lower():
                row["sole_source_status"] = f"{status} {_SOLE_SOURCE_RULE}"
        elif not status:
            row["sole_source_status"] = _SOLE_SOURCE_RULE
    llm["substitutability"] = subst

    coc = llm.get("change_of_control") if isinstance(llm.get("change_of_control"), dict) else {}
    if not coc:
        coc = heur["change_of_control"]
    else:
        base = dict(heur["change_of_control"])
        base.update({k: v for k, v in coc.items() if v is not None})
        base["notes"] = _COC_RULE
        coc = base
    llm["change_of_control"] = coc

    evidence = llm.get("evidence_status") if isinstance(llm.get("evidence_status"), dict) else {}
    if not evidence:
        evidence = heur["evidence_status"]
    else:
        base = dict(heur["evidence_status"])
        base.update({k: v for k, v in evidence.items() if v is not None})
        base["sole_source_rule"] = _SOLE_SOURCE_RULE
        base["resilience_reconcile"] = _RESILIENCE_RULE
        evidence = base
    llm["evidence_status"] = evidence

    # Legacy dual-write
    vendors = llm.get("vendors") if isinstance(llm.get("vendors"), list) else []
    cleaned_vendors: list[dict[str, Any]] = []
    for row in vendors:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        cleaned_vendors.append({
            "name": _clean(row.get("name"), 80),
            "component": _clean(row.get("component"), 80),
            "country": _clean(row.get("country"), 40),
            "annual_value_inr_cr": _num(row.get("annual_value_inr_cr")),
            "risk_level": _clean(row.get("risk_level"), 20) or None,
            "alternate_available": _clean(row.get("alternate_available"), 40) or None,
        })
    if not cleaned_vendors:
        cleaned_vendors = heur["vendors"]
    llm["vendors"] = cleaned_vendors

    flags = llm.get("concentration_flags") if isinstance(llm.get("concentration_flags"), list) else []
    flags = [_soften_invest(_clean(f, 200)) for f in flags if isinstance(f, str) and f.strip()]
    if not flags:
        flags = heur["concentration_flags"]
    llm["concentration_flags"] = flags[:6]

    notes = llm.get("dependency_notes") if isinstance(llm.get("dependency_notes"), list) else []
    notes = [_soften_invest(_clean(n, 240)) for n in notes if isinstance(n, str) and n.strip()]
    for rule in (_CRITICALITY_RULE, _CONTRACT_RULE, _SOLE_SOURCE_RULE, _COC_RULE, _RESILIENCE_RULE):
        if not any(rule[:30].lower() in x.lower() for x in notes):
            notes.append(rule)
    if not notes:
        notes = heur["dependency_notes"]
    llm["dependency_notes"] = notes[:8]

    quality, reliance, rationale = _quality_reliance(
        spend_rows=llm["spend_by_supplier"],
        criticality=llm["operational_criticality"],
        contracts=contracts,
        substitutability=subst,
        coc=coc,
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
    llm["empty"] = not cleaned_vendors
    return llm


def build_supplier_dependence_spec(
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
        gathered_corpus, gathered_sources = gather_supplier_dependence_corpus(deal, idx)
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
        llm = _llm_supplier_dependence_spec(
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

    return _heuristic_supplier_dependence_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )


def render_supplier_dependence_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    spend = spec.get("spend_by_supplier") if isinstance(spec.get("spend_by_supplier"), list) else []
    criticality = (
        spec.get("operational_criticality")
        if isinstance(spec.get("operational_criticality"), list) else []
    )
    contracts = spec.get("contract_terms") if isinstance(spec.get("contract_terms"), list) else []
    subst = spec.get("substitutability") if isinstance(spec.get("substitutability"), list) else []
    coc = spec.get("change_of_control") if isinstance(spec.get("change_of_control"), dict) else {}
    evidence = spec.get("evidence_status") if isinstance(spec.get("evidence_status"), dict) else {}
    flags = spec.get("concentration_flags") if isinstance(spec.get("concentration_flags"), list) else []
    notes = spec.get("dependency_notes") if isinstance(spec.get("dependency_notes"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # 1
    parts.append("## 1. Supplier Spend (Payables Ledger)\n\n")
    parts.append(
        "Supplier list built from the payables ledger. Each supplier's spend and its share "
        "of total spend for each period.\n\n"
    )
    if spend:
        parts.append(_table(
            ["Supplier", "Period", "Spend", "Share of total", "Component", "Country", "Source"],
            [
                [
                    _clean(r.get("supplier"), 60),
                    _clean(r.get("period"), 20),
                    _clean(r.get("spend"), 40),
                    _clean(r.get("share_of_total_pct"), 40),
                    _clean(r.get("component"), 60),
                    _clean(r.get("country"), 30),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in spend if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('supplier list and spend from payables ledger')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Operational Criticality (Separate from Spend)\n\n")
    parts.append(f"{_CRITICALITY_RULE} A low-spend processor with no alternative outranks a "
                 f"high-spend commodity vendor.\n\n")
    if criticality:
        parts.append(_table(
            ["Supplier", "Criticality", "What stops if they stop?", "Spend vs criticality", "Source"],
            [
                [
                    _clean(r.get("supplier"), 60),
                    _clean(r.get("criticality"), 60),
                    _clean(r.get("what_stops"), 160),
                    _clean(r.get("spend_vs_criticality"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in criticality if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('operational criticality ratings separate from spend')}**\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Contract Terms (Executed Documents Only)\n\n")
    parts.append(f"{_CONTRACT_RULE}\n\n")
    if contracts:
        for row in contracts:
            if not isinstance(row, dict):
                continue
            parts.append(f"### {_clean(row.get('supplier'), 60)}\n\n")
            parts.append(_table(
                ["Term", "Value"],
                [
                    ["Contract read", _clean(row.get("contract_read"), 80)],
                    ["Duration", _clean(row.get("duration"), 160)],
                    ["Renewal", _clean(row.get("renewal"), 160)],
                    ["Pricing mechanism", _clean(row.get("pricing_mechanism"), 160)],
                    ["Service levels", _clean(row.get("service_levels"), 160)],
                    ["Termination rights", _clean(row.get("termination_rights"), 160)],
                    ["Assignment", _clean(row.get("assignment"), 160)],
                    ["Change-of-control", _clean(row.get("change_of_control"), 160)],
                    ["Exclusivity", _clean(row.get("exclusivity"), 160)],
                    ["Source", _clean(row.get("source") or _NA, 60)],
                ],
            ))
            if _is_filled(row.get("notes")):
                parts.append(f"*{_clean(row.get('notes'), 240)}*\n\n")
    else:
        parts.append(f"**{_info_request('executed contracts for critical suppliers')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Substitutability (Time & Cost to Switch)\n\n")
    parts.append(
        "Alternatives in geography, qualification needed, time to switch, and cost. "
        f"{_SOLE_SOURCE_RULE}\n\n"
    )
    if subst:
        parts.append(_table(
            ["Supplier", "Alternatives", "Qualification", "Switch time", "Switch cost",
             "Sole-source status", "Source"],
            [
                [
                    _clean(r.get("supplier"), 50),
                    _clean(r.get("alternatives"), 100),
                    _clean(r.get("qualification"), 100),
                    _clean(r.get("switch_time"), 80),
                    _clean(r.get("switch_cost"), 80),
                    _clean(r.get("sole_source_status"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in subst if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('substitutability test for critical suppliers')}**\n\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Change-of-Control Consents\n\n")
    parts.append(f"{_COC_RULE}\n\n")
    parts.append(_table(
        ["Item", "Statement"],
        [
            [
                "Transaction triggers flagged",
                "Yes" if coc.get("transaction_triggers_flagged") else "No / not evidenced",
            ],
            [
                "Consents",
                "; ".join(
                    _clean(c, 160) for c in (coc.get("consents") or [])[:4] if isinstance(c, str)
                ) or _NA,
            ],
            ["Source", _clean(coc.get("source") or _NA, 60)],
        ],
    ))
    parts.append("### Evidenced vs assumed\n\n")
    parts.append(f"{_SOLE_SOURCE_RULE} {_RESILIENCE_RULE}\n\n")
    evidenced = evidence.get("evidenced") if isinstance(evidence.get("evidenced"), list) else []
    assumed = evidence.get("assumed") if isinstance(evidence.get("assumed"), list) else []
    if evidenced:
        parts.append("**Evidenced**\n\n")
        for e in evidenced[:5]:
            if isinstance(e, str):
                parts.append(f"- {_clean(e, 200)}\n")
        parts.append("\n")
    if assumed:
        parts.append("**Assumed**\n\n")
        for a in assumed[:5]:
            if isinstance(a, str):
                parts.append(f"- {_clean(a, 200)}\n")
        parts.append("\n")
    if flags:
        parts.append("### Concentration flags\n\n")
        for f in flags[:5]:
            if isinstance(f, str):
                parts.append(f"- {_clean(f, 200)}\n")
        parts.append("\n")
    parts.append(
        "*This section does not recommend invest or pass. Unread contract terms are not stated. "
        "A named supplier is not automatically sole source.*\n\n"
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
        f"can diligence rest on these dependence ratings and contracts?\n\n"
    )
    if notes:
        parts.append("### Dependency notes\n\n")
        for n in notes[:6]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This document identifies vendors the business cannot easily replace and the "
        "protection in their contracts. It does not recommend invest or pass.*\n\n"
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
