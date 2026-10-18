"""Compose DiligenceIQ SWOT Analysis — synthesis of validated upstream findings.

Creates no new facts. Every item traced with finding-ID + evidence status.
Quantification only when the source finding carried it. Information gaps kept
separate from proven weaknesses (gap ≠ weakness). Ranked by thesis effect.
Priority combos get action rows (owner / timing / success measure). Dedup /
conflict QA. Open blockers not overridden by net-positive narrative.
READY→LIMITED on open SWOT QA FAILs.

Dual-writes legacy DD-07 fields (strengths / weaknesses / opportunities /
threats / porter_forces).

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
_NUMBER_RE = re.compile(
    r"(?i)(?:~?\d[\d,]*(?:\.\d+)?\s*(?:%|pp|x|cr|crore|mn|m|bn|b|usd|inr|km)?)"
)

_DOCUMENT_TITLE = "SWOT Analysis"
_DD_CODE = "DD-07"
_AGENT_KEY = "swot_analysis"

_TRACE_RULE = (
    "Every item is built from an upstream finding. Carry its source agent, "
    "its number and its evidence status. No new claims."
)
_STATE_RULE = (
    "Keep four states distinct: a demonstrated strength, a demonstrated "
    "weakness, an external possibility, and an unexamined area. An "
    "unexamined area is never a weakness."
)
_QUANT_RULE = (
    "Quantify wherever the source finding did — customer concentration as a "
    "percentage, retention as a rate, margin as a number."
)
_RANK_RULE = (
    "Rank by effect on the investment case, not by category balance. Four "
    "sharp items beat sixteen generic ones."
)
_DISAGREE_RULE = (
    "Where two agents disagree, carry the item as unresolved and name both. "
    "Do not upgrade confidence during synthesis."
)
_FINDING_ID_RULE = (
    "Every SWOT item carries a finding-ID and an evidence status — no orphan "
    "synthesis claims."
)
_GAP_RULE = (
    "An unexamined area is never a weakness — gaps stay in Information Gaps."
)
_ACTION_RULE = (
    "Priority Strength/Weakness × Opportunity/Threat combos carry action rows "
    "with owner, timing and success measure."
)
_DEDUP_RULE = (
    "Duplicate or conflicting upstream findings are deduped or carried as "
    "unresolved — not silently merged."
)
_BLOCKER_RULE = (
    "Open blockers are not overridden by a net-positive narrative. Synthesis "
    "does not clear blockers."
)

# Upstream agents SWOT synthesises from (deep dive + foundations).
_UPSTREAM_SLUGS: tuple[str, ...] = (
    "competitor_identification",
    "competitive_differentiation",
    "market_share_strategy",
    "customer_stickiness",
    "customer_satisfaction",
    "buying_behavior",
    "customer_segmentation",
    "revenue_quality",
    "cost_structure",
    "historical_performance",
    "cash_flow",
    "capital_structure",
    "market_definition",
    "market_risk",
    "internal_risk",
    "growth_opportunities",
    "synergies",
    "market_volume_and_growth",
    "market_pricing",
    "demand_drivers",
    "supplier_dependence",
    "supply_chain_resilience",
    "operational_risk",
    "ip_and_technology",
    "management_quality",
    "strategic_direction",
    "regulatory_compliance",
    "esg_and_sustainability",
)

_FOUNDATION_SLUG_BY_CODE = {
    "F-IP": "ip_and_technology",
    "F-01": "strategic_direction",
    "F-06": "management_quality",
    "F-04": "regulatory_compliance",
    "F-ESG": "esg_and_sustainability",
}


def _soften_invest(text: str) -> str:
    return _INVEST_LANG.sub("frame the finding", text or "")


def _prose(text: str) -> str:
    t = _ZWSP.sub("", text or "")
    t = _PDF_BULLETS.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _numbers_in(text: str) -> list[str]:
    return [m.group(0).strip() for m in _NUMBER_RE.finditer(text or "")]


def _quant_from(text: str) -> str:
    nums = _numbers_in(text)
    if not nums:
        return _NA
    # Prefer percentage / rate style first
    for n in nums:
        if "%" in n or "pp" in n.lower():
            return n
    return nums[0]


def _evidence_status(spec: dict[str, Any], payload: dict[str, Any]) -> str:
    q = str(spec.get("quality_verdict") or payload.get("quality_verdict") or "").strip()
    r = str(spec.get("reliance_verdict") or payload.get("reliance_verdict") or "").strip()
    if q or r:
        return f"Quality {q or '—'} · Reliance {r or '—'}"
    return "Upstream evidence status not stated"


def _item(
    *,
    state: str,
    evidence_class: str,
    statement: str,
    source_agent: str,
    source_finding: str,
    quantification: str | None = None,
    evidence_status: str,
    thesis_effect: str,
    rank_hint: int = 50,
    disagreeing_agents: list[str] | None = None,
    finding_id: str | None = None,
) -> dict[str, Any]:
    stmt = _soften_invest(_clean(statement, 220))
    finding = _soften_invest(_clean(source_finding, 280))
    quant = quantification if quantification is not None else _quant_from(finding)
    # Defect guard: never invent a number absent from the source finding
    if quant != _NA and quant:
        if not any(q in finding or q in stmt for q in (quant, quant.replace(",", ""))):
            # Allow quant if digits appear in finding
            digits = re.sub(r"[^\d.]", "", quant)
            if digits and digits not in re.sub(r"[^\d.]", "", finding + stmt):
                quant = _NA
    # Normalize legacy "assertion" into a bucketed class (gap ≠ weakness)
    ec = evidence_class
    if ec == "assertion":
        ec = "unexamined" if state in {"opportunity", "threat"} else "demonstrated"
    return {
        "state": state,
        "evidence_class": ec,
        "statement": stmt,
        "source_agent": source_agent,
        "source_finding": finding,
        "quantification": quant or _NA,
        "evidence_status": evidence_status or "Upstream evidence status not stated",
        "thesis_effect": thesis_effect,
        "rank_hint": rank_hint,
        "disagreeing_agents": list(disagreeing_agents or []),
        "finding_id": finding_id or "",
    }


def _spec_of(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    spec = payload.get("spec")
    return spec if isinstance(spec, dict) else {}


def _harvest_revenue_quality(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    ret = spec.get("retention_metrics") if isinstance(spec.get("retention_metrics"), dict) else {}
    nrr = ret.get("nrr_pct")
    grr = ret.get("grr_pct")
    if nrr is not None:
        try:
            nrr_f = float(nrr)
        except (TypeError, ValueError):
            nrr_f = None
        if nrr_f is not None:
            if nrr_f < 90:
                out.append(
                    _item(
                        state="weakness",
                        evidence_class="demonstrated",
                        statement=f"Net revenue retention {nrr_f}% is below a 90% durability threshold.",
                        source_agent="revenue_quality",
                        source_finding=f"NRR {nrr_f}%",
                        quantification=f"{nrr_f}%",
                        evidence_status=status,
                        thesis_effect="price",
                        rank_hint=12,
                    )
                )
            else:
                out.append(
                    _item(
                        state="strength",
                        evidence_class="demonstrated",
                        statement=f"Net revenue retention {nrr_f}% supports durable recurring revenue.",
                        source_agent="revenue_quality",
                        source_finding=f"NRR {nrr_f}%",
                        quantification=f"{nrr_f}%",
                        evidence_status=status,
                        thesis_effect="thesis",
                        rank_hint=25,
                    )
                )
    if grr is not None:
        try:
            grr_f = float(grr)
        except (TypeError, ValueError):
            grr_f = None
        if grr_f is not None and grr_f < 80:
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=f"Gross revenue retention {grr_f}% indicates material revenue leakage.",
                    source_agent="revenue_quality",
                    source_finding=f"GRR {grr_f}%",
                    quantification=f"{grr_f}%",
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=14,
                )
            )
    for flag in (spec.get("quality_flags") or [])[:3]:
        if isinstance(flag, str) and flag.strip():
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=flag.strip(),
                    source_agent="revenue_quality",
                    source_finding=flag.strip(),
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=18,
                )
            )
    split = spec.get("revenue_split") if isinstance(spec.get("revenue_split"), list) else []
    for row in split[:2]:
        if not isinstance(row, dict):
            continue
        if "information request" in str(row.get("share_pct") or "").lower():
            out.append(
                _item(
                    state="opportunity",  # placeholder bucket; remapped to unexamined
                    evidence_class="unexamined",
                    statement=f"Revenue mix bucket '{row.get('bucket')}' not sized in the data room.",
                    source_agent="revenue_quality",
                    source_finding=str(row.get("notes") or row.get("amount") or row.get("bucket")),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=70,
                )
            )
    # Contracted share strength / weakness
    for row in split:
        if not isinstance(row, dict):
            continue
        if "under contract" not in str(row.get("bucket") or "").lower():
            continue
        share = row.get("share_pct")
        try:
            share_f = float(share) if share is not None else None
        except (TypeError, ValueError):
            share_f = None
        if share_f is None:
            continue
        out.append(
            _item(
                state="strength" if share_f >= 40 else "weakness",
                evidence_class="demonstrated",
                statement=f"~{share_f:g}% of revenue under contract.",
                source_agent="revenue_quality",
                source_finding=str(row.get("evidence") or row.get("bucket")),
                quantification=f"{share_f:g}%",
                evidence_status=status,
                thesis_effect="thesis" if share_f >= 40 else "price",
                rank_hint=22 if share_f >= 40 else 16,
            )
        )
        break
    # Taxonomy / renewal / pipeline gaps from QA FAILs
    for qa in (spec.get("rq_evidence_qa") or [])[:4]:
        if not isinstance(qa, dict) or qa.get("status") != "FAIL":
            continue
        check = str(qa.get("check") or "")
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"Revenue quality gap — {check}: {str(qa.get('finding') or '')[:120]}",
                source_agent="revenue_quality",
                source_finding=str(qa.get("action") or check)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=65,
            )
        )
    cross = (
        spec.get("stickiness_cash_flow_cross_check")
        if isinstance(spec.get("stickiness_cash_flow_cross_check"), dict) else {}
    )
    for conflict in (cross.get("conflicts") or [])[:2]:
        if isinstance(conflict, str) and conflict.strip():
            out.append(
                _item(
                    state="threat",
                    evidence_class="demonstrated",
                    statement=f"Stickiness/Cash Flow conflict: {conflict[:140]}",
                    source_agent="revenue_quality",
                    source_finding=conflict[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=13,
                )
            )
    return out


def _harvest_customer_stickiness(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    ret = spec.get("retention_metrics") if isinstance(spec.get("retention_metrics"), dict) else {}
    logo = ret.get("logo_churn_pct")
    if logo is not None:
        try:
            logo_f = float(logo)
        except (TypeError, ValueError):
            logo_f = None
        if logo_f is not None and logo_f >= 20:
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=f"Logo churn {logo_f}% shows weak customer stickiness.",
                    source_agent="customer_stickiness",
                    source_finding=f"logo_churn_pct {logo_f}%",
                    quantification=f"{logo_f}%",
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=16,
                )
            )
    for delta in (spec.get("retention_delta") or [])[:2]:
        if not isinstance(delta, dict) or not delta.get("is_finding"):
            continue
        mag = str(delta.get("magnitude") or "")
        metric = str(delta.get("metric") or "retention")
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=(
                    f"Falling {metric}: {delta.get('from_value')} → {delta.get('to_value')}"
                    + (f" ({mag})" if mag else "")
                    + " — recorded as a finding."
                ),
                source_agent="customer_stickiness",
                source_finding=f"{metric} down",
                quantification=mag or _NA,
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=14,
            )
        )
    for cohort in (spec.get("cohorts") or [])[:2]:
        if not isinstance(cohort, dict):
            continue
        m12 = cohort.get("m12_retention_pct")
        if m12 is None:
            continue
        try:
            m12_f = float(m12)
        except (TypeError, ValueError):
            continue
        label = cohort.get("cohort") or "cohort"
        if m12_f < 70:
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=f"Cohort {label} M12 retention {m12_f}% is soft.",
                    source_agent="customer_stickiness",
                    source_finding=f"Cohort {label} · M12 {m12_f}%",
                    quantification=f"{m12_f}%",
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=22,
                )
            )
    for r in (spec.get("new_logo_exclusion_qa") or [])[:2]:
        if isinstance(r, dict) and r.get("status") == "FAIL":
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=(
                        "New-logo exclusion from retention numerators not confirmed — "
                        "headline retention not diligence-grade."
                    ),
                    source_agent="customer_stickiness",
                    source_finding=str(r.get("check") or "new_logo_exclusion"),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=55,
                )
            )
    for gap in (spec.get("loss_reasons") or [])[:2]:
        text = gap.get("reason") if isinstance(gap, dict) else gap
        if isinstance(text, str) and "not stated" in text.lower():
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement="Loss reasons not sized — unexamined, not a proven weakness.",
                    source_agent="customer_stickiness",
                    source_finding=text,
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=72,
                )
            )
    return out


def _harvest_buying_behavior(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    maps = spec.get("purchase_maps") if isinstance(spec.get("purchase_maps"), list) else []
    map_filled = sum(
        1
        for m in maps
        if isinstance(m, dict)
        and any(
            m.get(k)
            for k in (
                "decision_maker",
                "budget_holder",
                "purchase_trigger",
            )
        )
    )
    if map_filled == 0:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Per-segment purchase maps not opened — growth-plan sales assumptions untested.",
                source_agent="buying_behavior",
                source_finding="purchase_maps empty",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=64,
            )
        )
    cycles = spec.get("sales_cycles") if isinstance(spec.get("sales_cycles"), list) else []
    evidenced = [c for c in cycles if isinstance(c, dict) and c.get("crm_evidenced")]
    if cycles and not evidenced:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Sales-cycle lengths lack CRM provenance — no universal cycle assigned.",
                source_agent="buying_behavior",
                source_finding="crm_evidenced=false",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=58,
            )
        )
    for c in evidenced[:2]:
        med = str(c.get("median") or "")
        seg = str(c.get("segment") or "segment")
        if med:
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="demonstrated",
                    statement=f"CRM sales cycle for {seg}: median {med}.",
                    source_agent="buying_behavior",
                    source_finding=f"{seg} median {med}",
                    quantification=med,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=32,
                )
            )
    switching = spec.get("switching") if isinstance(spec.get("switching"), dict) else {}
    if int(switching.get("anecdotal_count") or 0) > 0:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Interview claims labelled anecdotal — sample/dates/method incomplete.",
                source_agent="buying_behavior",
                source_finding="anecdotal_count",
                quantification=str(switching.get("anecdotal_count")),
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=62,
            )
        )
    seasonality = spec.get("seasonality") if isinstance(spec.get("seasonality"), dict) else {}
    if not seasonality.get("measured"):
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Seasonality not measured — not asserted without monthly data.",
                source_agent="buying_behavior",
                source_finding="seasonality unmeasured",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=66,
            )
        )
    for r in (spec.get("buying_evidence_qa") or [])[:2]:
        if isinstance(r, dict) and r.get("status") == "FAIL":
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Buying QA FAIL: {r.get('check')}",
                    source_agent="buying_behavior",
                    source_finding=str(r.get("finding") or r.get("check"))[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=55,
                )
            )
    return out


def _harvest_customer_satisfaction(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    survey = (
        spec.get("survey_assessment")
        if isinstance(spec.get("survey_assessment"), dict)
        else {}
    )
    if survey.get("inaccessible_file_note"):
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=(
                    "Survey file inaccessible — information gap, not poor customer focus."
                ),
                source_agent="customer_satisfaction",
                source_finding="inaccessible survey",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=68,
            )
        )
    nps = spec.get("nps")
    try:
        nps_f = float(nps) if nps is not None else None
    except (TypeError, ValueError):
        nps_f = None
    if nps_f is not None and nps_f < 20:
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Traceable NPS {nps_f:g} is soft.",
                source_agent="customer_satisfaction",
                source_finding=f"nps {nps_f:g}",
                quantification=f"{nps_f:g}",
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=17,
            )
        )
    for row in (spec.get("operational_signals") or [])[:2]:
        if not isinstance(row, dict):
            continue
        measure = str(row.get("measure") or row.get("signal_type") or "").strip()
        value = str(row.get("value") or "").strip()
        if not measure or not value:
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Ops quality signal: {measure} = {value}",
                source_agent="customer_satisfaction",
                source_finding=f"{measure}={value}",
                quantification=value,
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=24,
            )
        )
    assoc = (
        spec.get("churn_association")
        if isinstance(spec.get("churn_association"), dict)
        else {}
    )
    if assoc.get("comparable") and assoc.get("association_only"):
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=(
                    "Service failure ↔ subsequent cancellation association "
                    "(not Stickiness causation)."
                ),
                source_agent="customer_satisfaction",
                source_finding=str(assoc.get("notes") or "association")[:160],
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=28,
            )
        )
    research = (
        spec.get("research_design")
        if isinstance(spec.get("research_design"), dict)
        else {}
    )
    if research.get("needed"):
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Sentiment evidence thin — research design proposed for commission.",
                source_agent="customer_satisfaction",
                source_finding="research_design.needed",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=70,
            )
        )
    for r in (spec.get("survey_evidence_qa") or [])[:2]:
        if isinstance(r, dict) and r.get("status") == "FAIL":
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Satisfaction QA FAIL: {r.get('check')}",
                    source_agent="customer_satisfaction",
                    source_finding=str(r.get("finding") or r.get("check"))[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=56,
                )
            )
    for finding in (payload.get("findings") or [])[:2]:
        if not isinstance(finding, str):
            continue
        low = finding.lower()
        if "nps" in low and ("gap" in low or "below" in low or "vs" in low):
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=finding,
                    source_agent="customer_satisfaction",
                    source_finding=finding,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=15,
                )
            )
    return out


def _harvest_competitive_differentiation(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("advantage_tests") or [])[:4]:
        if not isinstance(row, dict) or not row.get("claim"):
            continue
        claim = str(row["claim"])
        result = str(row.get("test_result") or "UNTESTED").upper()
        if result == "PASS":
            out.append(
                _item(
                    state="strength",
                    evidence_class="demonstrated",
                    statement=claim,
                    source_agent="competitive_differentiation",
                    source_finding=f"Test PASS: {claim}",
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=20,
                )
            )
        elif result in {"FAIL", "INCONCLUSIVE"}:
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=claim,
                    source_agent="competitive_differentiation",
                    source_finding=f"Test {result}: {claim}",
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=13,
                )
            )
        else:
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Advantage claim untested: {claim}",
                    source_agent="competitive_differentiation",
                    source_finding=f"Test UNTESTED: {claim}",
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=65,
                )
            )
    for gap in (spec.get("feature_gaps") or [])[:2]:
        if isinstance(gap, str) and gap.strip():
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=gap.strip(),
                    source_agent="competitive_differentiation",
                    source_finding=gap.strip(),
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=17,
                )
            )
    for moat in (spec.get("moat_signals") or [])[:2]:
        if isinstance(moat, str) and moat.strip():
            low = moat.lower()
            if "narrow" in low or "erod" in low:
                out.append(
                    _item(
                        state="threat",
                        evidence_class="external_possibility",
                        statement=moat.strip(),
                        source_agent="competitive_differentiation",
                        source_finding=moat.strip(),
                        evidence_status=status,
                        thesis_effect="thesis",
                        rank_hint=19,
                    )
                )
            else:
                out.append(
                    _item(
                        state="strength",
                        evidence_class="demonstrated",
                        statement=moat.strip(),
                        source_agent="competitive_differentiation",
                        source_finding=moat.strip(),
                        evidence_status=status,
                        thesis_effect="thesis",
                        rank_hint=28,
                    )
                )
    for b in (spec.get("unsupported_benchmarks") or [])[:2]:
        if isinstance(b, dict) and b.get("status") == "REJECTED" and b.get("phrase"):
            out.append(
                _item(
                    state="weakness",
                    evidence_class="unexamined",
                    statement=(
                        f"Unsupported benchmark rejected: {b['phrase']} — "
                        "replace with named peer metric before relying on differentiation."
                    ),
                    source_agent="competitive_differentiation",
                    source_finding=str(b.get("phrase")),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=58,
                )
            )
    for x in (spec.get("moat_cross_checks") or [])[:2]:
        if isinstance(x, dict) and x.get("status") == "BLOCK_MOAT":
            out.append(
                _item(
                    state="weakness",
                    evidence_class="unexamined",
                    statement=(
                        f"Moat language blocked pending {x.get('check')} "
                        f"reconcile with {x.get('against_agent')}."
                    ),
                    source_agent="competitive_differentiation",
                    source_finding=str(x.get("check") or "moat_cross_check"),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=52,
                )
            )
    return out


def _harvest_market_share(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    matched = spec.get("matched_share") if isinstance(spec.get("matched_share"), dict) else {}
    if matched.get("calculable") is False:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=(
                    "Share is not calculable on a matched numerator/denominator "
                    "basis — unexamined, not a leadership or weakness finding."
                ),
                source_agent="market_share_strategy",
                source_finding=str(
                    matched.get("notes")
                    or "Share not calculable / unassessed on matched basis"
                ),
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=60,
            )
        )
    elif matched.get("share_pct") not in (None, ""):
        share = matched.get("share_pct")
        out.append(
            _item(
                state="strength",
                evidence_class="demonstrated",
                statement=f"Matched share {share} on stated numerator/denominator.",
                source_agent="market_share_strategy",
                source_finding=f"Matched share: {share}",
                quantification=str(share),
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=24,
            )
        )
    for row in (spec.get("share_trends") or [])[:1]:
        if isinstance(row, dict) and row.get("market_share_pct") is not None:
            name = row.get("name") or "focal"
            pct = row["market_share_pct"]
            trend = row.get("trend") or ""
            finding = f"{name} share {pct}% {trend}".strip()
            # Only treat as strength if calculable matched share OR explicit trend with number from this agent
            if matched.get("calculable"):
                out.append(
                    _item(
                        state="strength",
                        evidence_class="demonstrated",
                        statement=finding,
                        source_agent="market_share_strategy",
                        source_finding=finding,
                        quantification=f"{pct}%",
                        evidence_status=status,
                        thesis_effect="thesis",
                        rank_hint=26,
                    )
                )
    for c in (spec.get("capacity_constraints") or [])[:2]:
        if isinstance(c, dict) and c.get("status") == "CONSTRAINT":
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=(
                        f"Capacity constraint ({c.get('constraint')}): "
                        f"{c.get('action') or c.get('plan_need')}"
                    ),
                    source_agent="market_share_strategy",
                    source_finding=str(c.get("constraint") or "capacity_constraint"),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=22,
                )
            )
    return out


def _harvest_competitor_identification(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    peers = spec.get("competitive_set") or spec.get("competitors_legacy") or spec.get("competitors") or []
    named = [
        r for r in peers
        if isinstance(r, dict)
        and r.get("name")
        and not str(r["name"]).startswith("Information")
        and not r.get("context_only")
    ]
    if named:
        names = ", ".join(str(r["name"]) for r in named[:5])
        out.append(
            _item(
                state="threat",
                evidence_class="external_possibility",
                statement=f"Identified competitive set includes {len(named)} peer(s): {names}.",
                source_agent="competitor_identification",
                source_finding=names,
                quantification=str(len(named)),
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=35,
            )
        )
    else:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Competitive set not established from opened packs.",
                source_agent="competitor_identification",
                source_finding="No named peers in competitive set",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=68,
            )
        )
    unc = spec.get("capability_uncertainty") if isinstance(spec.get("capability_uncertainty"), list) else []
    unverified = [
        r for r in unc
        if isinstance(r, dict) and r.get("verification_status") == "unverified"
    ]
    if unverified:
        ent = ", ".join(str(r.get("entity") or "") for r in unverified[:3] if r.get("entity"))
        out.append(
            _item(
                state="weakness",
                evidence_class="internal_possibility",
                statement=(
                    f"Unverified peer capability claim(s) for {ent or 'named peers'} — "
                    "exclude from moat conclusions until verified."
                ),
                source_agent="competitor_identification",
                source_finding=ent or "capability_uncertainty",
                quantification=str(len(unverified)),
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=55,
            )
        )
    return out


def _harvest_cost_structure(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    metrics = spec.get("cost_metrics") if isinstance(spec.get("cost_metrics"), dict) else {}
    gm = metrics.get("gross_margin_pct")
    if gm is not None:
        try:
            gm_f = float(gm)
        except (TypeError, ValueError):
            gm_f = None
        if gm_f is not None:
            state = "weakness" if gm_f < 20 else "strength"
            out.append(
                _item(
                    state=state,
                    evidence_class="demonstrated",
                    statement=f"Gross margin {gm_f}%.",
                    source_agent="cost_structure",
                    source_finding=f"gross_margin_pct {gm_f}%",
                    quantification=f"{gm_f}%",
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=11 if gm_f < 20 else 27,
                )
            )
    cats = spec.get("operating_categories") if isinstance(spec.get("operating_categories"), list) else []
    top_cat = None
    top_pct: float | None = None
    for row in cats:
        if not isinstance(row, dict):
            continue
        share = row.get("share_pct")
        try:
            share_f = float(share) if share is not None else None
        except (TypeError, ValueError):
            share_f = None
        if share_f is None:
            continue
        if top_pct is None or share_f > top_pct:
            top_pct = share_f
            top_cat = str(row.get("category") or "Operating cost")
    if top_cat is None:
        for bom in (spec.get("bom_components") or [])[:1]:
            if isinstance(bom, dict) and bom.get("share_pct") is not None:
                top_cat = str(bom.get("category") or "BOM")
                try:
                    top_pct = float(bom["share_pct"])
                except (TypeError, ValueError):
                    top_pct = None
    if top_cat and top_pct is not None:
        out.append(
            _item(
                state="weakness" if top_pct >= 30 else "strength",
                evidence_class="demonstrated",
                statement=f"Largest cost bucket {top_cat} at {top_pct:g}% of mapped costs.",
                source_agent="cost_structure",
                source_finding=f"{top_cat} {top_pct:g}%",
                quantification=f"{top_pct:g}%",
                evidence_status=status,
                thesis_effect="price",
                rank_hint=21,
            )
        )
    for row in (spec.get("unit_economics") or [])[:1]:
        if not isinstance(row, dict):
            continue
        cost = str(row.get("cost") or "").strip()
        if cost and not cost.startswith("Information") and cost != _NA:
            out.append(
                _item(
                    state="strength",
                    evidence_class="demonstrated",
                    statement=f"Unit economics evidenced: {str(row.get('unit') or 'unit')[:80]} — {cost[:80]}.",
                    source_agent="cost_structure",
                    source_finding=cost[:120],
                    quantification=cost[:40],
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=28,
                )
            )
    for row in (spec.get("efficiency_opportunities") or [])[:1]:
        if not isinstance(row, dict):
            continue
        opp = str(row.get("opportunity") or "").strip()
        if not opp or opp.startswith("Information"):
            continue
        if row.get("synergy_flag"):
            out.append(
                _item(
                    state="threat",
                    evidence_class="demonstrated",
                    statement=f"Efficiency/synergy overlap risk: {opp[:120]}",
                    source_agent="cost_structure",
                    source_finding=opp[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=18,
                )
            )
        else:
            net = str(row.get("net_benefit") or "").strip()
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="demonstrated" if net and not net.startswith("Information") else "inferred",
                    statement=f"Stand-alone efficiency: {opp[:120]}",
                    source_agent="cost_structure",
                    source_finding=opp[:160],
                    quantification=net[:40] if net and not net.startswith("Information") else _NA,
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=42,
                )
            )
    for miss in (spec.get("missing_accounts") or [])[:2]:
        text = miss if isinstance(miss, str) else str((miss or {}).get("account") or miss)
        if text.strip():
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Cost account unexamined: {text}",
                    source_agent="cost_structure",
                    source_finding=text,
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=74,
                )
            )
    for r in (spec.get("cost_evidence_qa") or [])[:3]:
        if isinstance(r, dict) and r.get("status") == "FAIL":
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Cost QA FAIL: {r.get('check')}",
                    source_agent="cost_structure",
                    source_finding=str(r.get("finding") or r.get("check"))[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=54,
                )
            )
    return out


def _harvest_historical_performance(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    headline = str(spec.get("trend_headline") or "").strip()
    if headline:
        low = headline.lower()
        state = "weakness" if any(w in low for w in ("loss", "trough", "decline", "negative")) else "strength"
        # Growth with losses → still carry quantified path as demonstrated
        out.append(
            _item(
                state=state,
                evidence_class="demonstrated",
                statement=headline,
                source_agent="historical_performance",
                source_finding=headline,
                evidence_status=status,
                thesis_effect="price",
                rank_hint=10,
            )
        )
    return out


def _harvest_market_risk(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("external_risks") or spec.get("market_risk_items") or [])[:4]:
        if not isinstance(row, dict):
            continue
        risk = str(row.get("risk") or "").strip()
        if not risk or risk.startswith("Information"):
            continue
        trigger = str(row.get("trigger") or "").strip()
        mech = str(row.get("mechanism") or row.get("likelihood_argument") or "").strip()
        bits = [b for b in (trigger, mech) if b and not b.startswith("Information")]
        finding = f"{risk}" + (f" — {'; '.join(bits)}" if bits else "")
        out.append(
            _item(
                state="threat",
                evidence_class="external_possibility",
                statement=risk,
                source_agent="market_risk",
                source_finding=finding,
                evidence_status=status,
                thesis_effect="blocker" if "indemnity" in finding.lower() or "cp" in finding.lower() else "thesis",
                rank_hint=9 if row.get("impact") or row.get("sized") else 23,
            )
        )
    for row in (spec.get("downside_cases") or [])[:2]:
        if not isinstance(row, dict):
            continue
        bound = str(row.get("bound") or row.get("scenario") or "").strip()
        if bound:
            out.append(
                _item(
                    state="threat",
                    evidence_class="external_possibility",
                    statement=bound,
                    source_agent="market_risk",
                    source_finding=bound,
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=8,
                )
            )
    for row in (spec.get("unsized_risks") or [])[:2]:
        text = row.get("risk") if isinstance(row, dict) else row
        if isinstance(text, str) and text.strip():
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Unsized external risk (unexamined): {text}",
                    source_agent="market_risk",
                    source_finding=text,
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=66,
                )
            )
    return out


def _harvest_internal_risk(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("key_person_exposure") or [])[:2]:
        if not isinstance(row, dict):
            continue
        person = str(row.get("person") or "Key person").strip()
        if person.startswith("Information"):
            continue
        depends = str(row.get("what_depends") or "").strip()
        finding = f"{person}: {depends}" if depends else person
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Key-person exposure — {person}.",
                source_agent="internal_risk",
                source_finding=finding,
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=7,
            )
        )
    register_harvested = 0
    for row in (spec.get("risk_register") or [])[:4]:
        if not isinstance(row, dict):
            continue
        risk = str(row.get("risk") or "").strip()
        if not risk or risk.startswith("Information"):
            continue
        evid = str(row.get("evidence_class") or "").lower()
        cls = "demonstrated" if evid == "known_weakness" else "unexamined"
        residual = str(row.get("residual") or "").strip()
        finding = f"{risk}" + (f" — residual {residual}" if residual else "")
        out.append(
            _item(
                state="weakness" if cls == "demonstrated" else "opportunity",
                evidence_class=cls,
                statement=risk,
                source_agent="internal_risk",
                source_finding=finding,
                quantification=str(row.get("exposure") or _NA)[:120],
                evidence_status=status,
                thesis_effect=(
                    "blocker"
                    if str(row.get("rank_effect") or "") in {"Structure", "Price"}
                    else "thesis"
                ),
                rank_hint=8 if cls == "demonstrated" else 62,
            )
        )
        register_harvested += 1
    if register_harvested == 0:
        for row in (spec.get("observed_weaknesses") or [])[:3]:
            if not isinstance(row, dict):
                continue
            w = str(row.get("weakness") or "").strip()
            ev = str(row.get("evidence") or "").strip()
            if not w or w.startswith("Information"):
                continue
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=w,
                    source_agent="internal_risk",
                    source_finding=f"{w} — {ev}" if ev else w,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=14,
                )
            )
    for row in (spec.get("control_testing") or [])[:2]:
        if not isinstance(row, dict):
            continue
        tested = str(row.get("tested") or "").lower()
        if "not tested" in tested or "untested" in tested:
            ctrl = str(row.get("control") or "control").strip()
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Control unexamined / untested: {ctrl}",
                    source_agent="internal_risk",
                    source_finding=str(row.get("result") or ctrl),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=64,
                )
            )
    return out


def _harvest_growth(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("options") or [])[:4]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("option") or row.get("name") or "").strip()
        if not name or name.startswith("Information"):
            continue
        evid_status = str(row.get("evidence_status") or row.get("evidence_class") or row.get("status") or "").lower()
        sizing = str(
            row.get("incremental_margin")
            or row.get("net_value")
            or row.get("sizing")
            or row.get("size")
            or row.get("note")
            or ""
        )
        finding = f"{name}: {sizing}".strip(": ")
        is_hyp = "hypothesis" in evid_status or bool(row.get("hypothesis"))
        out.append(
            _item(
                state="opportunity",
                evidence_class="external_possibility" if not is_hyp else "unexamined",
                statement=name,
                source_agent="growth_opportunities",
                source_finding=finding,
                quantification=_clean(sizing, 80) if sizing else _NA,
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=40 if is_hyp else 30,
            )
        )
    ue = spec.get("unit_economics") if isinstance(spec.get("unit_economics"), dict) else {}
    if ue.get("gross_margin_now_pct") is not None and ue.get("gross_margin_target_low_pct") is not None:
        now = ue["gross_margin_now_pct"]
        tgt = ue["gross_margin_target_low_pct"]
        finding = f"gross margin {now}% → target {tgt}%"
        out.append(
            _item(
                state="opportunity",
                evidence_class="external_possibility",
                statement=f"Margin path {now}% toward {tgt}%+.",
                source_agent="growth_opportunities",
                source_finding=finding,
                quantification=f"{now}%",
                evidence_status=status,
                thesis_effect="price",
                rank_hint=32,
            )
        )
    return out


def _harvest_synergies(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    buyer = spec.get("buyer") if isinstance(spec.get("buyer"), dict) else {}
    out: list[dict[str, Any]] = []
    if not buyer.get("named"):
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=(
                    "No named acquirer — synergies cannot be underwritten "
                    "(unexamined buyer case, not a proven weakness)."
                ),
                source_agent="synergies",
                source_finding=str(
                    spec.get("cannot_underwrite_reason")
                    or "No named acquirer — cannot underwrite"
                ),
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=55,
            )
        )
    elif spec.get("underwritable"):
        fvr = (
            spec.get("fvr_exclusion")
            if isinstance(spec.get("fvr_exclusion"), dict)
            else {}
        )
        out.append(
            _item(
                state="opportunity",
                evidence_class="external_possibility",
                statement=f"Named buyer {buyer.get('buyer_name')} — underwritable synergies present.",
                source_agent="synergies",
                source_finding=str(buyer.get("what_they_bring") or buyer.get("buyer_name")),
                evidence_status=status,
                thesis_effect="price",
                rank_hint=33,
            )
        )
        if not fvr.get("include_in_final_valuation_range"):
            out.append(
                _item(
                    state="weakness",
                    evidence_class="known_gap",
                    statement=(
                        "Unverified or incomplete synergy levers remain excluded "
                        "from Final Valuation Range."
                    ),
                    source_agent="synergies",
                    source_finding=str(fvr.get("treatment") or "FVR exclusion"),
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=48,
                )
            )
        for risk in (spec.get("execution_risks") or [])[:2]:
            if not isinstance(risk, dict) or not risk.get("risk"):
                continue
            if "Not applicable" in str(risk.get("risk") or ""):
                continue
            if str(risk.get("risk") or "").startswith("Information"):
                continue
            out.append(
                _item(
                    state="threat",
                    evidence_class="external_possibility",
                    statement=(
                        f"Synergy execution risk: {risk.get('risk')} "
                        f"(owner {risk.get('owner')})"
                    ),
                    source_agent="synergies",
                    source_finding=str(
                        risk.get("effect_on_timing_or_amount") or risk.get("risk")
                    ),
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=42,
                )
            )
    return out


def _harvest_market_definition(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    export = (
        spec.get("perimeter_export")
        if isinstance(spec.get("perimeter_export"), dict)
        else {}
    )
    perim = spec.get("perimeter") if isinstance(spec.get("perimeter"), dict) else {}
    axes = 0
    for key in ("service", "customer_types", "geography", "value_chain_stage"):
        val = str((export or perim).get(key) or "")
        if val and not val.startswith("Information") and val != "N/A (data room did not provide it)":
            axes += 1
    if axes >= 3:
        geo = str((export or perim).get("geography") or "")[:120]
        out.append(
            _item(
                state="strength",
                evidence_class="demonstrated",
                statement=f"Market perimeter set on {axes}/4 axes"
                + (f" ({geo})" if geo and not geo.startswith("Information") else ""),
                source_agent="market_definition",
                source_finding=f"axes={axes}",
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=18,
            )
        )
    elif axes:
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Market perimeter incomplete ({axes}/4 axes) — downstream market sizing blocked",
                source_agent="market_definition",
                source_finding=f"axes={axes}",
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=12,
            )
        )
    if spec.get("right_to_win_deferred") is True or (
        isinstance(export, dict) and export.get("right_to_win") == "deferred"
    ):
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Right-to-win deferred from Market Definition — score in differentiation / share",
                source_agent="market_definition",
                source_finding="right_to_win=deferred",
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=35,
            )
        )
    return out


def _harvest_cash_flow(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    metrics = spec.get("cash_metrics") if isinstance(spec.get("cash_metrics"), dict) else {}
    conv = metrics.get("cash_conversion_pct")
    if isinstance(conv, (int, float)):
        state = "strength" if conv >= 80 else "weakness"
        out.append(
            _item(
                state=state,
                evidence_class="demonstrated",
                statement=f"Cash conversion {conv:g}% (OCF / |EBITDA|)",
                source_agent="cash_flow",
                source_finding=f"cash_conversion_pct={conv:g}",
                evidence_status=status,
                thesis_effect="price",
                rank_hint=11,
            )
        )
    liq = spec.get("liquidity") if isinstance(spec.get("liquidity"), dict) else {}
    pressure = str(liq.get("pressure") or "")
    if pressure == "verified_tight":
        runway = liq.get("runway_months_computed")
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=(
                    f"Verified tight liquidity runway"
                    + (f" (~{runway:g} months)" if isinstance(runway, (int, float)) else "")
                ),
                source_agent="cash_flow",
                source_finding=str(liq.get("notes") or pressure)[:200],
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=8,
            )
        )
    elif pressure == "unavailable":
        # Explicit: missing ≠ distress — harvest as information gap, not weakness.
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Liquidity inputs incomplete — do not infer distress from missing cash data",
                source_agent="cash_flow",
                source_finding="pressure=unavailable",
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=28,
            )
        )
    return out


def _harvest_capital_structure(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("facilities") or spec.get("facility_schedule") or [])[:2]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("facility") or row.get("name") or "").strip()
        amount = row.get("drawn_balance")
        if amount is None:
            amount = row.get("amount") or row.get("drawn") or ""
        if name:
            finding = f"{name} {amount}".strip()
            out.append(
                _item(
                    state="threat",
                    evidence_class="demonstrated",
                    statement=finding,
                    source_agent="capital_structure",
                    source_finding=finding,
                    quantification=str(amount) if amount not in (None, "") else _NA,
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=18,
                )
            )
    if not spec.get("schedule_complete"):
        gap_txt = "; ".join(str(g) for g in (spec.get("schedule_gaps") or [])[:2])
        out.append(
            _item(
                state="threat",
                evidence_class="unexamined",
                statement="Facility schedule incomplete — leverage withheld.",
                source_agent="capital_structure",
                source_finding=gap_txt or "schedule incomplete",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=8,
            )
        )
    for row in (spec.get("change_of_control") or [])[:2]:
        if not isinstance(row, dict):
            continue
        trigger = str(row.get("trigger") or "").strip()
        if not trigger or trigger.startswith("Information"):
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=f"CoC / consent: {trigger[:120]}",
                source_agent="capital_structure",
                source_finding=str(row.get("kind") or trigger)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=7,
            )
        )
    for qa in (spec.get("cap_evidence_qa") or [])[:3]:
        if not isinstance(qa, dict) or qa.get("status") != "FAIL":
            continue
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"Capital structure gap — {qa.get('check')}: {str(qa.get('finding') or '')[:120]}",
                source_agent="capital_structure",
                source_finding=str(qa.get("action") or qa.get("check"))[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=66,
            )
        )
    for finding in (payload.get("findings") or [])[:2]:
        if isinstance(finding, str) and ("mezzanine" in finding.lower() or "maturity" in finding.lower()):
            out.append(
                _item(
                    state="threat",
                    evidence_class="demonstrated",
                    statement=finding,
                    source_agent="capital_structure",
                    source_finding=finding,
                    evidence_status=status,
                    thesis_effect="blocker",
                    rank_hint=6,
                )
            )
    return out


def _harvest_supplier(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("spend_by_supplier") or [])[:2]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("supplier") or "").strip()
        pct = row.get("share_of_total_pct")
        if not name:
            continue
        try:
            pct_f = float(str(pct).replace("%", "")) if pct is not None else None
        except (TypeError, ValueError):
            pct_f = None
        if pct_f is not None and pct_f >= 15:
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=f"Supplier spend concentration — {name} at {pct_f:g}%.",
                    source_agent="supplier_dependence",
                    source_finding=f"{name} {pct_f:g}%",
                    quantification=f"{pct_f:g}%",
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=16,
                )
            )
    for row in (spec.get("operational_criticality") or [])[:2]:
        if not isinstance(row, dict):
            continue
        if "critical" not in str(row.get("criticality") or "").lower():
            continue
        name = str(row.get("supplier") or "").strip()
        if not name:
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=(
                    f"Critical supplier {name}: "
                    f"{str(row.get('what_stops') or 'operations stop if supply stops')[:120]}"
                ),
                source_agent="supplier_dependence",
                source_finding=f"critical:{name}",
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=12,
            )
        )
    for row in (spec.get("disruption_priority") or [])[:2]:
        if not isinstance(row, dict) or int(row.get("priority") or 99) > 2:
            continue
        name = str(row.get("supplier") or "").strip()
        if not name or name.startswith("Information"):
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Disruption priority #{row.get('priority')}: {name}.",
                source_agent="supplier_dependence",
                source_finding=f"priority {row.get('priority')} {name}",
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=14,
            )
        )
    scr = spec.get("scr_reconcile") if isinstance(spec.get("scr_reconcile"), dict) else {}
    if str(scr.get("status") or "") in {"missing", "partial"}:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"Supply Chain Resilience reconcile {scr.get('status')} — gaps open.",
                source_agent="supplier_dependence",
                source_finding="scr_reconcile",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=60,
            )
        )
    for r in (spec.get("supplier_evidence_qa") or [])[:2]:
        if isinstance(r, dict) and r.get("status") == "FAIL":
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Supplier QA FAIL: {r.get('check')}",
                    source_agent="supplier_dependence",
                    source_finding=str(r.get("finding") or r.get("check"))[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=54,
                )
            )
    return out


def _harvest_operational_risk(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("priced_vs_noise") or [])[:2]:
        if not isinstance(row, dict):
            continue
        cls = str(row.get("classification") or "").lower()
        risk = str(row.get("risk") or "").strip()
        if not risk or risk.startswith("Information"):
            continue
        if "protection" in cls or "price" in cls:
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=f"Ops risk priced/protection: {risk[:120]}",
                    source_agent="operational_risk",
                    source_finding=str(row.get("rationale") or risk)[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=15,
                )
            )
    for row in (spec.get("sized_risks") or [])[:2]:
        if not isinstance(row, dict) or str(row.get("sized") or "") not in {"Yes", "Partial"}:
            continue
        ebitda = str(row.get("ebitda_if_recurs") or "").strip()
        if not ebitda or ebitda.startswith("Information"):
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=f"Sized ops disruption — {row.get('risk')}: {ebitda[:80]}",
                source_agent="operational_risk",
                source_finding=ebitda[:160],
                quantification=ebitda[:40],
                evidence_status=status,
                thesis_effect="price",
                rank_hint=18,
            )
        )
    for row in (spec.get("continuity_arrangements") or [])[:2]:
        if not isinstance(row, dict):
            continue
        arr = str(row.get("arrangement") or "").strip()
        if not arr or arr.startswith("Information"):
            continue
        tested = str(row.get("tested_or_used") or "")
        if "untested" in tested.lower():
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Ops continuity untested: {arr[:120]}",
                    source_agent="operational_risk",
                    source_finding=tested[:120],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=57,
                )
            )
    for row in (spec.get("historical_vs_plan") or [])[:1]:
        if not isinstance(row, dict):
            continue
        if "plan" not in str(row.get("bucket") or "").lower():
            continue
        risk = str(row.get("risk") or "").strip()
        if risk and not risk.startswith("Information"):
            out.append(
                _item(
                    state="threat",
                    evidence_class="demonstrated",
                    statement=f"Plan-amplified ops risk: {risk[:120]}",
                    source_agent="operational_risk",
                    source_finding=str(row.get("plan_driver") or risk)[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=22,
                )
            )
    for r in (spec.get("ops_evidence_qa") or [])[:3]:
        if isinstance(r, dict) and r.get("status") == "FAIL":
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Ops QA FAIL: {r.get('check')}",
                    source_agent="operational_risk",
                    source_finding=str(r.get("finding") or r.get("check"))[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=56,
                )
            )
    return out


def _harvest_supply_chain_resilience(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for node in (spec.get("critical_path") or [])[:3]:
        if not isinstance(node, dict):
            continue
        if str(node.get("spof") or "").lower() != "yes":
            continue
        name = str(node.get("supplier_or_asset") or node.get("stage") or "SPOF").strip()
        if not name or name.startswith("Information"):
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=(
                    f"Critical-path SPOF ({node.get('layer') or 'physical'}): {name}."
                ),
                source_agent="supply_chain_resilience",
                source_finding=str(node.get("description") or name)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=13,
            )
        )
    for row in (spec.get("continuity_arrangements") or [])[:2]:
        if not isinstance(row, dict):
            continue
        arr = str(row.get("arrangement") or "").strip()
        if not arr or arr.startswith("Information"):
            continue
        tested = str(row.get("tested_or_used") or "")
        if "untested" in tested.lower():
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"Continuity untested: {arr[:120]}",
                    source_agent="supply_chain_resilience",
                    source_finding=tested[:120],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=58,
                )
            )
        elif "tested" in tested.lower():
            out.append(
                _item(
                    state="strength",
                    evidence_class="demonstrated",
                    statement=f"Continuity used/tested: {arr[:120]}",
                    source_agent="supply_chain_resilience",
                    source_finding=tested[:120],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=36,
                )
            )
    for row in (spec.get("plausible_downsides") or [])[:2]:
        if not isinstance(row, dict):
            continue
        if str(row.get("bounded") or "").lower() != "yes":
            continue
        cost = str(row.get("plausible_cost") or "").strip()
        if not cost or cost.startswith("Information"):
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=(
                    f"Bounded SCR downside — {row.get('exposure')}: {cost}"
                    f" / {row.get('duration') or 'duration N/A'}."
                ),
                source_agent="supply_chain_resilience",
                source_finding=cost[:160],
                quantification=cost[:40],
                evidence_status=status,
                thesis_effect="price",
                rank_hint=17,
            )
        )
    for row in (spec.get("disruption_scenarios") or [])[:1]:
        if not isinstance(row, dict):
            continue
        scen = str(row.get("scenario") or "").strip()
        if not scen or scen.startswith("Information"):
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=f"Disruption scenario: {scen[:120]}",
                source_agent="supply_chain_resilience",
                source_finding=str(row.get("cost_impact") or scen)[:160],
                quantification=(
                    str(row.get("cost_impact"))[:40]
                    if str(row.get("cost_impact") or "").strip()
                    and not str(row.get("cost_impact")).startswith("Information")
                    else _NA
                ),
                evidence_status=status,
                thesis_effect="price",
                rank_hint=19,
            )
        )
    for r in (spec.get("scr_evidence_qa") or [])[:3]:
        if isinstance(r, dict) and r.get("status") == "FAIL":
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=f"SCR QA FAIL: {r.get('check')}",
                    source_agent="supply_chain_resilience",
                    source_finding=str(r.get("finding") or r.get("check"))[:160],
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=55,
                )
            )
    return out


def _harvest_volume(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    note = str(spec.get("market_growth_note") or "")
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", note)
    if m:
        try:
            v = float(m.group(1))
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="external_possibility",
                    statement=f"Market growth ~{v:g}% (stated / endpoint series).",
                    source_agent="market_volume_and_growth",
                    source_finding=note[:160],
                    quantification=f"{v:g}%",
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=34,
                )
            )
        except (TypeError, ValueError):
            pass
    if not out:
        for key in ("sam_cagr_pct", "tam_cagr_pct", "cagr_pct"):
            growth = spec.get("market_growth") if isinstance(spec.get("market_growth"), dict) else {}
            val = growth.get(key) if growth else spec.get(key)
            if val is None and isinstance(spec.get("ceiling"), dict):
                val = spec["ceiling"].get(key)
            if isinstance(val, list) and val:
                val = val[0]
            if val is not None:
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    continue
                out.append(
                    _item(
                        state="opportunity",
                        evidence_class="external_possibility",
                        statement=f"Market growth {key.replace('_', ' ')} {v}%.",
                        source_agent="market_volume_and_growth",
                        source_finding=f"{key} {v}%",
                        quantification=f"{v}%",
                        evidence_status=status,
                        thesis_effect="thesis",
                        rank_hint=34,
                    )
                )
                break
    plan = spec.get("plan_vs_market") if isinstance(spec.get("plan_vs_market"), dict) else {}
    multiple = str(plan.get("multiple") or "")
    mm = re.search(r"([\d.]+)\s*×", multiple)
    if mm:
        try:
            mult = float(mm.group(1))
            out.append(
                _item(
                    state="weakness" if mult >= 2 else "opportunity",
                    evidence_class="demonstrated" if mult >= 2 else "external_possibility",
                    statement=f"Plan/market growth multiple ~{mult:g}×",
                    source_agent="market_volume_and_growth",
                    source_finding=multiple[:120],
                    quantification=f"{mult:g}×",
                    evidence_status=status,
                    thesis_effect="thesis" if mult < 2 else "blocker",
                    rank_hint=22 if mult >= 2 else 36,
                )
            )
        except (TypeError, ValueError):
            pass
    binding = (
        spec.get("perimeter_binding")
        if isinstance(spec.get("perimeter_binding"), dict)
        else {}
    )
    if binding and not binding.get("bound"):
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Market volume series not yet bound to approved perimeter",
                source_agent="market_volume_and_growth",
                source_finding=str(binding.get("note") or "unbound")[:160],
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=14,
            )
        )
    return out


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if value is None:
        return []
    return [value]


def _harvest_ip(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    reconcile = spec.get("ip_advantage_reconcile")
    claims: list[str] = []
    if isinstance(reconcile, dict):
        for key in ("contradicted", "evidenced", "other_agent_claims"):
            for item in _as_list(reconcile.get(key)):
                if isinstance(item, str) and item.strip():
                    claims.append(item.strip())
                elif isinstance(item, dict):
                    claims.append(
                        str(item.get("claim") or item.get("contradiction") or item)[:200]
                    )
    elif isinstance(reconcile, list):
        for row in reconcile:
            if isinstance(row, dict):
                claims.append(
                    str(row.get("claim") or row.get("contradiction") or "")[:200]
                )
            elif isinstance(row, str):
                claims.append(row)
    for claim in claims[:3]:
        if not claim.strip():
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=claim,
                source_agent="ip_and_technology",
                source_finding=claim,
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=20,
            )
        )
    for row in (spec.get("moat_test") or [])[:2]:
        if not isinstance(row, dict):
            continue
        if "FAIL" not in str(row.get("moat_verdict") or ""):
            continue
        asset = str(row.get("asset") or "").strip()
        if not asset or asset.startswith("Information"):
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="unexamined",
                statement=f"Moat test incomplete: {asset[:100]}",
                source_agent="ip_and_technology",
                source_finding=str(row.get("moat_verdict") or asset)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=22,
            )
        )
    for row in (spec.get("cyber_checklist") or [])[:2]:
        if not isinstance(row, dict) or row.get("status") != "OPEN":
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="unexamined",
                statement=f"Cyber / restore OPEN: {row.get('item')}",
                source_agent="ip_and_technology",
                source_finding=str(row.get("detail") or row.get("item"))[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=11,
            )
        )
    for qa in (spec.get("ip_evidence_qa") or [])[:3]:
        if not isinstance(qa, dict) or qa.get("status") != "FAIL":
            continue
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"IP/tech gap — {qa.get('check')}: {str(qa.get('finding') or '')[:120]}",
                source_agent="ip_and_technology",
                source_finding=str(qa.get("action") or qa.get("check"))[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=65,
            )
        )
    for finding in (payload.get("findings") or [])[:2]:
        if isinstance(finding, str) and "contradiction" in finding.lower():
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=finding,
                    source_agent="ip_and_technology",
                    source_finding=finding,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=20,
                )
            )
    return out


def _harvest_generic_findings(slug: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Fallback: carry blocked upstream as unexamined (not invented weaknesses)."""
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    reliance = str(spec.get("reliance_verdict") or "").upper()
    out: list[dict[str, Any]] = []
    if reliance == "BLOCKED":
        note = f"Upstream {slug} Reliance BLOCKED — findings not upgraded in synthesis."
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=note,
                source_agent=slug,
                source_finding=note,
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=5,
            )
        )
    return out


def _harvest_customer_segmentation(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for finding in (payload.get("findings") or [])[:3]:
        if not isinstance(finding, str) or not finding.strip():
            continue
        low = finding.lower()
        if any(tok in low for tok in ("unassessed", "not stated", "n/a", "information request", "withheld")):
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="unexamined",
                    statement=finding.strip(),
                    source_agent="customer_segmentation",
                    source_finding=finding.strip(),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=67,
                )
            )
        elif "%" in finding:
            out.append(
                _item(
                    state="strength" if "top" not in low else "weakness",
                    evidence_class="demonstrated",
                    statement=finding.strip(),
                    source_agent="customer_segmentation",
                    source_finding=finding.strip(),
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=29,
                )
            )
    conc = spec.get("concentration") if isinstance(spec.get("concentration"), dict) else {}
    if conc.get("calculable") is False:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=(
                    "Concentration unassessed — ledger not opened; risk rating withheld "
                    "(empty table is not high risk)."
                ),
                source_agent="customer_segmentation",
                source_finding="concentration unassessed",
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=66,
            )
        )
    elif conc.get("top_10_share_pct"):
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=(
                    f"Parent-level concentration: top 10 = {conc.get('top_10_share_pct')} "
                    f"(top 1 = {conc.get('top_1_share_pct') or 'n/a'})."
                ),
                source_agent="customer_segmentation",
                source_finding=f"top10={conc.get('top_10_share_pct')}",
                quantification=str(conc.get("top_10_share_pct")),
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=18,
            )
        )
    for r in (spec.get("population_definition_qa") or [])[:2]:
        if isinstance(r, dict) and r.get("status") == "REJECTED":
            out.append(
                _item(
                    state="weakness",
                    evidence_class="unexamined",
                    statement=f"Overlapping/mixed population rejected: {r.get('action')}",
                    source_agent="customer_segmentation",
                    source_finding=str(r.get("check") or "population_qa"),
                    quantification=_NA,
                    evidence_status=status,
                    thesis_effect="secondary",
                    rank_hint=54,
                )
            )
    return out


def _harvest_demand_drivers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    ranked = (
        spec.get("ranked_contribution")
        if isinstance(spec.get("ranked_contribution"), list)
        else []
    )
    for row in ranked[:2]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("driver") or "")
        if not name or name.startswith("Information"):
            continue
        flag = "FLAG" in str(row.get("double_count_check") or "").upper()
        out.append(
            _item(
                state="weakness" if flag else "opportunity",
                evidence_class="demonstrated" if flag else "external_possibility",
                statement=(
                    f"Demand driver double-count FLAG: {name}"
                    if flag
                    else f"Ranked demand driver: {name}"
                ),
                source_agent="demand_drivers",
                source_finding=str(row.get("evidenced_contribution") or name)[:160],
                evidence_status=status,
                thesis_effect="blocker" if flag else "thesis",
                rank_hint=15 if flag else 33,
            )
        )
    counters = (
        spec.get("counter_drivers")
        if isinstance(spec.get("counter_drivers"), list)
        else []
    )
    for row in counters[:1]:
        if not isinstance(row, dict):
            continue
        cd = str(row.get("counter_driver") or "")
        if not cd or cd.startswith("Information"):
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Demand counter-driver / cyclicality: {_clean(cd, 120)}",
                source_agent="demand_drivers",
                source_finding=cd[:160],
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=26,
            )
        )
        break
    return out


def _harvest_market_pricing(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    realised = spec.get("realised_prices") if isinstance(spec.get("realised_prices"), list) else []
    for row in realised[:2]:
        if not isinstance(row, dict):
            continue
        net = str(row.get("realised_net_price") or "")
        if not net or net.startswith("Information") or net.startswith("N/A"):
            continue
        out.append(
            _item(
                state="strength",
                evidence_class="demonstrated",
                statement=f"Realised net price evidenced ({_clean(row.get('service_or_segment'), 40)})",
                source_agent="market_pricing",
                source_finding=net[:160],
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=24,
            )
        )
        break
    comps = (
        spec.get("competitor_comparisons")
        if isinstance(spec.get("competitor_comparisons"), list)
        else []
    )
    named = [
        c
        for c in comps
        if isinstance(c, dict)
        and c.get("competitor")
        and not str(c["competitor"]).startswith("Information")
        and "unnamed" not in str(c.get("notes", "")).lower()
    ]
    if named:
        out.append(
            _item(
                state="strength",
                evidence_class="demonstrated",
                statement=f"Named competitor price comps ({len(named)})",
                source_agent="market_pricing",
                source_finding=str(named[0].get("competitor") or "")[:120],
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=30,
            )
        )
    else:
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="No named competitor price comps — unnamed industry ASP rejected",
                source_agent="market_pricing",
                source_finding="unnamed comps rejected",
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=16,
            )
        )
    response = (
        spec.get("observed_response")
        if isinstance(spec.get("observed_response"), list)
        else []
    )
    if any(
        isinstance(r, dict)
        and r.get("event")
        and not str(r["event"]).startswith("Information")
        for r in response
    ):
        out.append(
            _item(
                state="opportunity",
                evidence_class="demonstrated",
                statement="Observed price-increase response evidenced (not invented elasticity)",
                source_agent="market_pricing",
                source_finding=str((response[0] or {}).get("label") or "")[:160],
                evidence_status=status,
                thesis_effect="thesis",
                rank_hint=32,
            )
        )
    return out


def _harvest_esg_and_sustainability(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("consequences") or [])[:3]:
        if not isinstance(row, dict):
            continue
        topic = str(row.get("topic") or "").strip()
        ctype = str(row.get("consequence_type") or "").strip()
        if not topic or topic.startswith("Information"):
            continue
        if "none" in ctype.lower():
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=f"ESG consequence ({ctype}): {topic[:100]}",
                source_agent="esg_and_sustainability",
                source_finding=str(row.get("detail") or topic)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="price" if "cost" in ctype.lower() else "blocker",
                rank_hint=12,
            )
        )
    for row in (spec.get("workforce_safety") or [])[:2]:
        if not isinstance(row, dict):
            continue
        factor = str(row.get("factor") or "").strip()
        if not factor or factor.startswith("Information"):
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Workforce / safety: {factor[:100]}",
                source_agent="esg_and_sustainability",
                source_finding=str(row.get("cost_or_continuity") or row.get("record") or factor)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="price",
                rank_hint=18,
            )
        )
    for qa in (spec.get("esg_evidence_qa") or [])[:3]:
        if not isinstance(qa, dict) or qa.get("status") != "FAIL":
            continue
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"ESG gap — {qa.get('check')}: {str(qa.get('finding') or '')[:120]}",
                source_agent="esg_and_sustainability",
                source_finding=str(qa.get("action") or qa.get("check"))[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=64,
            )
        )
    return out


def _harvest_regulatory_compliance(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("obligations") or [])[:3]:
        if not isinstance(row, dict):
            continue
        if str(row.get("tested") or "") != "Untested":
            continue
        obl = str(row.get("obligation") or "").strip()
        if not obl or obl.startswith("Information"):
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="unexamined",
                statement=f"Untested obligation: {obl[:120]}",
                source_agent="regulatory_compliance",
                source_finding=str(row.get("evidence") or obl)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=7,
            )
        )
    for row in (spec.get("litigation_register") or [])[:2]:
        if not isinstance(row, dict):
            continue
        matter = str(row.get("matter") or "").strip()
        if not matter or matter.startswith("Information"):
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=f"Litigation / claim: {matter[:120]}",
                source_agent="regulatory_compliance",
                source_finding=str(row.get("claimed_amount") or row.get("status") or matter)[:160],
                quantification=str(row.get("claimed_amount") or _NA),
                evidence_status=status,
                thesis_effect="price",
                rank_hint=10,
            )
        )
    for row in (spec.get("critical_permits") or [])[:2]:
        if not isinstance(row, dict):
            continue
        permit = str(row.get("permit") or "").strip()
        if not permit:
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=f"Critical permit CoC: {permit[:100]}",
                source_agent="regulatory_compliance",
                source_finding=str(row.get("recommendation_action") or permit)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=8,
            )
        )
    counsel = spec.get("counsel_letter") if isinstance(spec.get("counsel_letter"), dict) else {}
    if str(counsel.get("status") or "") == "OPEN":
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement="Counsel letter OPEN — litigation register not closed",
                source_agent="regulatory_compliance",
                source_finding=str(counsel.get("detail") or "counsel letter missing")[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=55,
            )
        )
    for qa in (spec.get("rc_evidence_qa") or [])[:3]:
        if not isinstance(qa, dict) or qa.get("status") != "FAIL":
            continue
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"Regulatory gap — {qa.get('check')}: {str(qa.get('finding') or '')[:120]}",
                source_agent="regulatory_compliance",
                source_finding=str(qa.get("action") or qa.get("check"))[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=66,
            )
        )
    return out


def _harvest_strategic_direction(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("untested_assumptions") or [])[:3]:
        if not isinstance(row, dict):
            continue
        assumption = str(row.get("assumption") or "").strip()
        if not assumption:
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="unexamined",
                statement=f"Untested strategic assumption: {assumption[:120]}",
                source_agent="strategic_direction",
                source_finding=str(row.get("basis") or assumption)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker" if "fund" in assumption.lower() or "capacity" in assumption.lower() else "price",
                rank_hint=9,
            )
        )
    for row in (spec.get("initiatives") or [])[:2]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("initiative") or "").strip()
        if not name or name.startswith("Information"):
            continue
        flag = str(row.get("synergy_flag") or "stand_alone")
        out.append(
            _item(
                state="opportunity" if "synerg" not in flag.lower() else "opportunity",
                evidence_class="demonstrated",
                statement=f"Initiative ({flag}): {name[:100]}",
                source_agent="strategic_direction",
                source_finding=str(row.get("milestone") or name)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=40,
            )
        )
    for qa in (spec.get("sd_evidence_qa") or [])[:3]:
        if not isinstance(qa, dict) or qa.get("status") != "FAIL":
            continue
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"Strategic direction gap — {qa.get('check')}: {str(qa.get('finding') or '')[:120]}",
                source_agent="strategic_direction",
                source_finding=str(qa.get("action") or qa.get("check"))[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=67,
            )
        )
    return out


def _harvest_management_quality(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("key_persons") or [])[:2]:
        if not isinstance(row, dict):
            continue
        person = str(row.get("person") or "").strip()
        if not person or person.startswith("Information"):
            continue
        out.append(
            _item(
                state="threat",
                evidence_class="demonstrated",
                statement=f"Key-person dependency: {person[:100]}",
                source_agent="management_quality",
                source_finding=str(row.get("what_depends") or person)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="blocker",
                rank_hint=8,
            )
        )
    for row in (spec.get("confirmed_vacancies") or [])[:2]:
        if not isinstance(row, dict):
            continue
        item = str(row.get("item") or "").strip()
        if not item:
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Confirmed vacancy: {item[:120]}",
                source_agent="management_quality",
                source_finding=str(row.get("evidence") or item)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="price",
                rank_hint=14,
            )
        )
    for row in (spec.get("capability_gaps") or [])[:2]:
        if not isinstance(row, dict):
            continue
        item = str(row.get("item") or "").strip()
        if not item:
            continue
        out.append(
            _item(
                state="weakness",
                evidence_class="demonstrated",
                statement=f"Capability gap: {item[:120]}",
                source_agent="management_quality",
                source_finding=str(row.get("evidence") or item)[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="price",
                rank_hint=16,
            )
        )
    for qa in (spec.get("mq_evidence_qa") or [])[:3]:
        if not isinstance(qa, dict) or qa.get("status") != "FAIL":
            continue
        out.append(
            _item(
                state="opportunity",
                evidence_class="unexamined",
                statement=f"Management quality gap — {qa.get('check')}: {str(qa.get('finding') or '')[:120]}",
                source_agent="management_quality",
                source_finding=str(qa.get("action") or qa.get("check"))[:160],
                quantification=_NA,
                evidence_status=status,
                thesis_effect="secondary",
                rank_hint=68,
            )
        )
    return out


_HARVESTERS: dict[str, Any] = {
    "revenue_quality": _harvest_revenue_quality,
    "strategic_direction": _harvest_strategic_direction,
    "regulatory_compliance": _harvest_regulatory_compliance,
    "esg_and_sustainability": _harvest_esg_and_sustainability,
    "management_quality": _harvest_management_quality,
    "customer_stickiness": _harvest_customer_stickiness,
    "customer_satisfaction": _harvest_customer_satisfaction,
    "buying_behavior": _harvest_buying_behavior,
    "customer_segmentation": _harvest_customer_segmentation,
    "competitive_differentiation": _harvest_competitive_differentiation,
    "market_pricing": _harvest_market_pricing,
    "demand_drivers": _harvest_demand_drivers,
    "market_share_strategy": _harvest_market_share,
    "competitor_identification": _harvest_competitor_identification,
    "cost_structure": _harvest_cost_structure,
    "historical_performance": _harvest_historical_performance,
    "cash_flow": _harvest_cash_flow,
    "market_definition": _harvest_market_definition,
    "market_risk": _harvest_market_risk,
    "internal_risk": _harvest_internal_risk,
    "growth_opportunities": _harvest_growth,
    "synergies": _harvest_synergies,
    "capital_structure": _harvest_capital_structure,
    "supplier_dependence": _harvest_supplier,
    "supply_chain_resilience": _harvest_supply_chain_resilience,
    "operational_risk": _harvest_operational_risk,
    "market_volume_and_growth": _harvest_volume,
    "ip_and_technology": _harvest_ip,
}


def _topic_key(item: dict[str, Any]) -> str:
    text = f"{item.get('statement') or ''} {item.get('source_finding') or ''}".lower()
    for stem in (
        "nrr",
        "grr",
        "logo churn",
        "gross margin",
        "nps",
        "market share",
        "matched share",
        "key-person",
        "key person",
        "supplier",
        "moat",
        "synerg",
        "retention",
        "cohort",
        "battery",
        "subsidy",
        "fame",
        "mezzanine",
    ):
        if stem in text:
            return stem
    tokens = re.findall(r"[a-z0-9]+", text)
    return " ".join(tokens[:4])


def _detect_disagreements(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        if it.get("evidence_class") in {"unexamined", "external_possibility"}:
            continue
        if it.get("state") not in {"strength", "weakness"}:
            continue
        key = _topic_key(it)
        by_topic.setdefault(key, []).append(it)

    unresolved: list[dict[str, Any]] = []
    drop_ids: set[int] = set()
    for key, group in by_topic.items():
        if len(group) < 2:
            continue
        agents = {g["source_agent"] for g in group}
        states = {g["state"] for g in group}
        # True conflict only: demonstrated strength vs demonstrated weakness
        if len(agents) >= 2 and states >= {"strength", "weakness"}:
            agents_list = sorted(agents)
            statements = " | ".join(
                f"{g['source_agent']}: {g['statement']}" for g in group[:3]
            )
            unresolved.append(
                _item(
                    state="threat",
                    evidence_class="unresolved",
                    statement=f"Unresolved across {', '.join(agents_list)}: {key}",
                    source_agent=agents_list[0],
                    source_finding=statements,
                    quantification=_NA,
                    evidence_status="Unresolved — do not upgrade confidence",
                    thesis_effect="blocker",
                    rank_hint=4,
                    disagreeing_agents=agents_list,
                )
            )
            for g in group:
                drop_ids.add(id(g))
    kept = [it for it in items if id(it) not in drop_ids]
    return kept + unresolved


def _rank_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    effect_order = {"blocker": 0, "price": 1, "thesis": 2, "secondary": 3}
    class_order = {
        "unresolved": 0,
        "demonstrated": 1,
        "external_possibility": 2,
        "unexamined": 3,
    }

    def sort_key(it: dict[str, Any]) -> tuple:
        return (
            effect_order.get(str(it.get("thesis_effect")), 9),
            class_order.get(str(it.get("evidence_class")), 9),
            int(it.get("rank_hint") or 99),
            str(it.get("statement") or ""),
        )

    ranked = sorted(items, key=sort_key)
    for i, it in enumerate(ranked, start=1):
        it["rank"] = i
        it.pop("rank_hint", None)
    return ranked


def _format_line(it: dict[str, Any]) -> str:
    stmt = str(it.get("statement") or "").strip()
    agent = str(it.get("source_agent") or "").strip()
    quant = str(it.get("quantification") or "").strip()
    bits = [stmt]
    if quant and quant != _NA and quant not in stmt:
        bits.append(f"({quant})")
    if agent:
        bits.append(f"[{agent}]")
    if it.get("evidence_class") == "unresolved" and it.get("disagreeing_agents"):
        bits.append(f"unresolved: {', '.join(it['disagreeing_agents'])}")
    return " ".join(bits)[:280]


def _collect_prior_agents(
    deal: Deal,
    *,
    prior: dict[str, dict] | None,
    foundation: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    agents: dict[str, dict[str, Any]] = {}
    prior = prior if isinstance(prior, dict) else {}
    for slug in _UPSTREAM_SLUGS:
        payload = prior.get(slug)
        if not isinstance(payload, dict) or not payload.get("spec"):
            try:
                disk = read_agent_output_file(deal, agent_key=slug)
            except Exception:  # noqa: BLE001 — soft-load only
                disk = None
            if isinstance(disk, dict):
                payload = disk
        if isinstance(payload, dict) and (payload.get("spec") or payload.get("findings")):
            agents[slug] = payload

    # Foundation roles → slug map
    roles = foundation.get("roles") if isinstance(foundation, dict) else None
    if isinstance(roles, dict):
        for code, slug in _FOUNDATION_SLUG_BY_CODE.items():
            if slug in agents:
                continue
            entry = roles.get(code)
            if isinstance(entry, dict) and isinstance(entry.get("spec"), dict):
                agents[slug] = {
                    "agent_key": slug,
                    "spec": entry["spec"],
                    "findings": entry.get("findings") or [],
                    "summary": entry.get("summary") or "",
                }
    return agents


def _open_blockers(items: list[dict[str, Any]], agents: dict[str, dict]) -> list[str]:
    blockers: list[str] = []
    for it in items:
        if it.get("thesis_effect") == "blocker":
            blockers.append(_format_line(it))
        elif it.get("evidence_class") == "unresolved":
            blockers.append(_format_line(it))
    for slug, payload in agents.items():
        spec = _spec_of(payload)
        if str(spec.get("reliance_verdict") or "").upper() == "BLOCKED":
            blockers.append(f"Upstream {slug} Reliance BLOCKED")
    # dedupe
    seen: set[str] = set()
    out: list[str] = []
    for b in blockers:
        key = b.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(b[:220])
        if len(out) >= 6:
            break
    return out


def _assign_finding_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable SWOT-{S|W|O|T|G|U}-NN finding IDs on every item."""
    counters: dict[str, int] = {}
    prefix_map = {
        "strength": "S",
        "weakness": "W",
        "opportunity": "O",
        "threat": "T",
    }
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        if row.get("finding_id"):
            out.append(row)
            continue
        state = str(row.get("state") or "")
        ec = str(row.get("evidence_class") or "")
        if ec == "unexamined":
            prefix = "G"
        elif ec == "unresolved":
            prefix = "U"
        else:
            prefix = prefix_map.get(state, "X")
        counters[prefix] = counters.get(prefix, 0) + 1
        row["finding_id"] = f"SWOT-{prefix}-{counters[prefix]:02d}"
        out.append(row)
    return out


def _build_priority_action_rows(
    *,
    strengths: list[dict[str, Any]],
    weaknesses: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    threats: list[dict[str, Any]],
    open_blockers: list[str],
) -> list[dict[str, Any]]:
    """SO / ST / WO / WT action rows with owner, timing, success measure."""
    rows: list[dict[str, Any]] = []

    def _pair(
        combo: str,
        a: dict[str, Any] | None,
        b: dict[str, Any] | None,
        action: str,
    ) -> None:
        if not a or not b:
            return
        ids = [
            str(a.get("finding_id") or ""),
            str(b.get("finding_id") or ""),
        ]
        rows.append(
            {
                "combo": combo,
                "finding_ids": [i for i in ids if i],
                "action": _soften_invest(_clean(action, 200)),
                "owner": "Information request: action owner (deal / IMO / workstream lead)",
                "timing": "Information request: timing before IC / close",
                "success_measure": (
                    "Information request: measurable success test for this combo"
                ),
                "notes": _ACTION_RULE,
            }
        )

    s0 = strengths[0] if strengths else None
    w0 = weaknesses[0] if weaknesses else None
    o0 = opportunities[0] if opportunities else None
    t0 = threats[0] if threats else None

    if s0 and o0:
        _pair(
            "SO",
            s0,
            o0,
            f"Use strength '{_clean(s0.get('statement'), 60)}' to capture "
            f"opportunity '{_clean(o0.get('statement'), 60)}'",
        )
    if s0 and t0:
        _pair(
            "ST",
            s0,
            t0,
            f"Deploy strength '{_clean(s0.get('statement'), 60)}' against "
            f"threat '{_clean(t0.get('statement'), 60)}'",
        )
    if w0 and o0:
        _pair(
            "WO",
            w0,
            o0,
            f"Close weakness '{_clean(w0.get('statement'), 60)}' enough to "
            f"pursue opportunity '{_clean(o0.get('statement'), 60)}'",
        )
    if w0 and t0:
        _pair(
            "WT",
            w0,
            t0,
            f"Mitigate weakness '{_clean(w0.get('statement'), 60)}' before "
            f"threat '{_clean(t0.get('statement'), 60)}' crystallises",
        )

    if open_blockers and not rows:
        rows.append(
            {
                "combo": "BLOCKER",
                "finding_ids": [],
                "action": _clean(
                    f"Resolve open blocker before relying on SWOT narrative: "
                    f"{open_blockers[0]}",
                    200,
                ),
                "owner": "Information request: blocker owner",
                "timing": "before IC",
                "success_measure": "Blocker cleared or explicitly accepted with effect",
                "notes": _BLOCKER_RULE,
            }
        )
    return rows[:6]


def _swot_evidence_qa(
    *,
    strengths: list[dict[str, Any]],
    weaknesses: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    threats: list[dict[str, Any]],
    information_gaps: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    priority_action_rows: list[dict[str, Any]],
    open_blockers: list[str],
    insight_snapshot: str,
    agents_used: int,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    all_items = (
        strengths + weaknesses + opportunities + threats + information_gaps + unresolved
    )

    # Finding-ID + evidence status mandatory
    missing_id = [
        it for it in all_items
        if isinstance(it, dict) and not str(it.get("finding_id") or "").strip()
    ]
    status_empty = [
        it for it in all_items
        if isinstance(it, dict) and not str(it.get("evidence_status") or "").strip()
    ]
    id_ok = not missing_id and not status_empty and (
        not all_items or all(
            isinstance(it, dict)
            and it.get("finding_id")
            and it.get("evidence_status")
            for it in all_items
        )
    )
    rows.append({
        "check": "finding_id_and_evidence_status",
        "status": "PASS" if id_ok else "FAIL",
        "finding": (
            f"{len(all_items)} item(s) with finding-ID and evidence status"
            if id_ok
            else (
                f"{len(missing_id)} missing finding-ID; "
                f"{len(status_empty)} missing evidence status"
            )
        ),
        "action": _FINDING_ID_RULE,
    })

    # Gap ≠ weakness
    gap_in_weak = [
        it for it in weaknesses
        if isinstance(it, dict) and it.get("evidence_class") == "unexamined"
    ]
    gap_ok = not gap_in_weak
    rows.append({
        "check": "gap_not_in_weaknesses",
        "status": "PASS" if gap_ok else "FAIL",
        "finding": (
            f"{len(information_gaps)} information gap(s) kept out of weaknesses"
            if gap_ok
            else f"{len(gap_in_weak)} unexamined item(s) wrongly in weaknesses"
        ),
        "action": _GAP_RULE,
    })

    # Priority action rows complete when there are ranked S/W/O/T to combine
    combinable = bool(strengths or weaknesses) and bool(opportunities or threats)
    if not combinable and not open_blockers:
        action_ok = True
        action_finding = "No priority combos available — action rows not required"
    elif not priority_action_rows:
        action_ok = False
        action_finding = "Priority combos present but no action rows"
    else:
        incomplete = [
            r for r in priority_action_rows
            if isinstance(r, dict)
            and (
                not r.get("owner")
                or not r.get("timing")
                or not r.get("success_measure")
                or not r.get("action")
            )
        ]
        action_ok = not incomplete
        action_finding = (
            f"{len(priority_action_rows)} priority action row(s) with "
            f"owner / timing / success measure"
            if action_ok
            else f"{len(incomplete)} action row(s) missing owner/timing/success measure"
        )
    rows.append({
        "check": "priority_action_rows_complete",
        "status": "PASS" if action_ok else "FAIL",
        "finding": action_finding,
        "action": _ACTION_RULE,
    })

    # Dedup / conflict
    # Unresolved items with disagreeing agents = handled conflict; silent dupes = FAIL
    stmts = [
        str(it.get("statement") or "").strip().lower()[:80]
        for it in strengths + weaknesses + opportunities + threats
        if isinstance(it, dict) and it.get("statement")
    ]
    dupes = len(stmts) - len(set(stmts))
    unresolved_ok = all(
        isinstance(it, dict) and it.get("disagreeing_agents")
        for it in unresolved
    ) if unresolved else True
    dedup_ok = dupes == 0 and unresolved_ok
    rows.append({
        "check": "dedup_conflict_qa",
        "status": "PASS" if dedup_ok else "FAIL",
        "finding": (
            (
                f"{len(unresolved)} unresolved disagreement(s) named; no silent duplicates"
                if unresolved
                else "No silent duplicates across SWOT quadrants"
            )
            if dedup_ok
            else (
                f"{dupes} duplicate statement(s)"
                if dupes
                else "Unresolved items missing disagreeing_agents"
            )
        ),
        "action": _DEDUP_RULE,
    })

    # Blockers not overridden by net-positive narrative
    snap = (insight_snapshot or "").lower()
    positive_tone = bool(
        re.search(
            r"(?i)\b(strong\s+overall|net[- ]positive|attractive\s+thesis|"
            r"compelling\s+opportunity|overlook\s+blocker)\b",
            snap,
        )
    )
    blocker_cleared_in_snap = bool(open_blockers) and bool(
        re.search(r"(?i)\b(blockers?\s+cleared|no\s+open\s+blockers?)\b", snap)
    )
    # Require open blockers to appear in snapshot when present
    blocker_mentioned = (
        not open_blockers
        or "blocker" in snap
        or any(
            _clean(b, 40).lower()[:24] in snap
            for b in open_blockers
        )
    )
    blocker_ok = (
        (not open_blockers or blocker_mentioned)
        and not blocker_cleared_in_snap
        and not (open_blockers and positive_tone and not blocker_mentioned)
    )
    rows.append({
        "check": "blockers_not_overridden",
        "status": "PASS" if blocker_ok else "FAIL",
        "finding": (
            (
                f"{len(open_blockers)} open blocker(s) retained — not cleared by narrative"
                if open_blockers
                else "No open blockers"
            )
            if blocker_ok
            else "Open blocker(s) overridden or omitted by net-positive narrative"
        ),
        "action": _BLOCKER_RULE,
    })

    # Trace / no invented (light)
    untraced = [it for it in all_items if isinstance(it, dict) and not it.get("source_agent")]
    rows.append({
        "check": "items_traced_to_upstream",
        "status": "PASS" if not untraced else "FAIL",
        "finding": (
            f"{len(all_items)} item(s) traced to upstream"
            if not untraced
            else f"{len(untraced)} untraced item(s)"
        ),
        "action": _TRACE_RULE,
    })

    return rows


def _questions_from_swot_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    qa = (
        spec.get("swot_evidence_qa")
        if isinstance(spec.get("swot_evidence_qa"), list)
        else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    out: list[dict[str, str]] = []
    if _qa_fail("finding_id_and_evidence_status"):
        out.append(normalize_question({
            "question": "Assign finding-ID and evidence status to every SWOT item",
            "required_records": "Upstream finding register with IDs and status",
            "decision_effect": "Orphan synthesis claims cannot be diligence-tested",
            "priority": "mandatory_pre_decision",
            "owner": "SWOT synthesis lead",
            "timing": "before IC",
            "closure_test": "finding_id_and_evidence_status QA PASS",
            "interim_treatment": "LIMITED until every item is ID'd",
        }))
    if _qa_fail("gap_not_in_weaknesses"):
        out.append(normalize_question({
            "question": "Move unexamined items out of Weaknesses into Information Gaps",
            "required_records": "SWOT gap register (unexamined ≠ weakness)",
            "decision_effect": "Treating gaps as weaknesses overstates known failure",
            "priority": "mandatory_pre_decision",
            "owner": "SWOT synthesis lead",
            "timing": "before IC",
            "closure_test": "gap_not_in_weaknesses QA PASS",
            "interim_treatment": "LIMITED until gaps reclassified",
        }))
    if _qa_fail("priority_action_rows_complete"):
        out.append(normalize_question({
            "question": (
                "Complete priority SO/ST/WO/WT action rows with owner, timing "
                "and success measure"
            ),
            "required_records": "Priority combo action register",
            "decision_effect": "Unowned priority combos cannot be executed or tested",
            "priority": "mandatory_pre_decision",
            "owner": "Deal / IMO lead",
            "timing": "before IC",
            "closure_test": "priority_action_rows_complete QA PASS",
            "interim_treatment": "LIMITED until action rows complete",
        }))
    if _qa_fail("dedup_conflict_qa"):
        out.append(normalize_question({
            "question": "Resolve duplicate SWOT statements or carry conflicts as unresolved",
            "required_records": "Dedup log / disagreeing agent names",
            "decision_effect": "Silent merges hide material disagreements",
            "priority": "mandatory_pre_decision",
            "owner": "SWOT synthesis lead",
            "timing": "before IC",
            "closure_test": "dedup_conflict_qa QA PASS",
            "interim_treatment": "LIMITED until conflicts named",
        }))
    if _qa_fail("blockers_not_overridden"):
        out.append(normalize_question({
            "question": "Surface open blockers in the SWOT snapshot — do not clear by narrative",
            "required_records": "Open blocker list with owners",
            "decision_effect": "Net-positive tone must not override open blockers",
            "priority": "mandatory_pre_decision",
            "owner": "Deal lead",
            "timing": "before IC",
            "closure_test": "blockers_not_overridden QA PASS",
            "interim_treatment": "BLOCKED until blockers retained in narrative",
        }))
    if _qa_fail("items_traced_to_upstream"):
        out.append(normalize_question({
            "question": "Remove or re-trace SWOT items that lack an upstream source agent",
            "required_records": "Upstream agent finding citations",
            "decision_effect": "Untraced synthesis invents facts",
            "priority": "mandatory_pre_decision",
            "owner": "SWOT synthesis lead",
            "timing": "before IC",
            "closure_test": "items_traced_to_upstream QA PASS",
            "interim_treatment": "REWORK until all items traced",
        }))
    return [q for q in out if q]


def _quality_reliance(
    *,
    items: list[dict[str, Any]],
    open_blockers: list[str],
    agents_used: int,
    qa_fail: bool = False,
) -> tuple[str, str, str]:
    untraced = [it for it in items if not it.get("source_agent")]
    invented = []
    for it in items:
        quant = str(it.get("quantification") or "")
        if quant and quant != _NA:
            finding = str(it.get("source_finding") or "")
            digits = re.sub(r"[^\d.]", "", quant)
            if digits and digits not in re.sub(r"[^\d.]", "", finding + str(it.get("statement") or "")):
                invented.append(it)
    if untraced or invented:
        quality = "REWORK"
        rationale = (
            "REWORK: synthesis introduced untraced items or numbers absent from upstream findings."
        )
    elif agents_used == 0:
        quality = "REWORK"
        rationale = "REWORK: no upstream agent findings available to synthesise."
    else:
        quality = "PASS"
        rationale = (
            f"PASS: {len(items)} item(s) traced to upstream agents; no invented numbers."
        )

    if open_blockers:
        reliance = "BLOCKED"
        rationale += " Open blocker(s) present — positive tone must not override."
    elif any(it.get("evidence_class") == "unexamined" for it in items):
        reliance = "LIMITED"
    elif agents_used < 3:
        reliance = "LIMITED"
    else:
        reliance = "READY"

    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        rationale += " Open SWOT QA FAILs cap READY → LIMITED."
    elif qa_fail and reliance != "BLOCKED":
        rationale += " Open SWOT QA FAILs remain."
    return quality, reliance, rationale


def _heuristic_swot_analysis_spec(
    *,
    company: str,
    prior_agents: dict[str, dict[str, Any]] | None = None,
    sources: list[str] | None = None,
    sector: str | None = None,
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agents = prior_agents if isinstance(prior_agents, dict) else {}
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    raw_items: list[dict[str, Any]] = []
    for slug, payload in agents.items():
        harvester = _HARVESTERS.get(slug)
        try:
            if harvester:
                raw_items.extend(harvester(payload))
            else:
                raw_items.extend(_harvest_generic_findings(slug, payload))
        except Exception:  # noqa: BLE001 — one bad upstream must not kill synthesis
            continue

    # Remap unexamined out of SWOT weakness/opportunity display later
    items = _detect_disagreements(raw_items)
    items = _rank_items(items)
    items = _assign_finding_ids(items)

    strengths = [it for it in items if it["evidence_class"] == "demonstrated" and it["state"] == "strength"]
    weaknesses = [it for it in items if it["evidence_class"] == "demonstrated" and it["state"] == "weakness"]
    opportunities = [
        it for it in items
        if it["evidence_class"] == "external_possibility" and it["state"] == "opportunity"
    ]
    threats = [
        it for it in items
        if it["state"] == "threat" and it["evidence_class"] in {"external_possibility", "demonstrated", "unresolved"}
    ]
    unexamined = [it for it in items if it["evidence_class"] == "unexamined"]
    unresolved = [it for it in items if it["evidence_class"] == "unresolved"]

    # Cap by thesis effect — four sharp items beat sixteen generic ones
    strengths = strengths[:4]
    weaknesses = weaknesses[:4]
    opportunities = opportunities[:4]
    threats = threats[:6]
    unexamined = unexamined[:6]
    unresolved = unresolved[:4]

    open_blockers = _open_blockers(items, agents)
    priority_action_rows = _build_priority_action_rows(
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=opportunities,
        threats=threats,
        open_blockers=open_blockers,
    )

    # Dual-write legacy string lists (traced)
    legacy_strengths = [_format_line(it) for it in strengths]
    legacy_weaknesses = [_format_line(it) for it in weaknesses]
    legacy_opportunities = [_format_line(it) for it in opportunities]
    legacy_threats = [_format_line(it) for it in threats]
    # Never put unexamined into weaknesses
    assert all("unexamined" not in (it.get("evidence_class") or "") for it in weaknesses)

    # Porter: only carry if already in legacy AND also mirrored by market_risk/threats —
    # otherwise drop (synthesis must not invent Porter intensities).
    porter: list[dict[str, Any]] = []
    legacy_porter = legacy.get("porter_forces") if isinstance(legacy.get("porter_forces"), list) else []
    threat_text = " ".join(t.get("statement", "") for t in threats).lower()
    for force in legacy_porter:
        if not isinstance(force, dict):
            continue
        name = str(force.get("force") or "")
        if name and any(tok in threat_text for tok in name.lower().split()[:2] if len(tok) > 3):
            porter.append(force)

    bits = [
        f"SWOT synthesis for {company}",
        f"{len(strengths)} strength(s)",
        f"{len(weaknesses)} weakness(es)",
        f"{len(opportunities)} opportunit(ies)",
        f"{len(threats)} threat(s)",
        f"{len(unexamined)} unexamined",
    ]
    if unresolved:
        bits.append(f"{len(unresolved)} unresolved disagreement(s)")
    if open_blockers:
        bits.append(f"OPEN BLOCKER: {open_blockers[0][:80]}")
    snapshot = _soften_invest(". ".join(bits))

    srcs = list(sources or [])
    for slug, payload in agents.items():
        for s in (payload.get("sources") or [])[:2]:
            if isinstance(s, str) and s and s not in srcs:
                srcs.append(s)

    empty = not any([strengths, weaknesses, opportunities, threats, unexamined, unresolved])

    swot_qa = _swot_evidence_qa(
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=opportunities,
        threats=threats,
        information_gaps=unexamined,
        unresolved=unresolved,
        priority_action_rows=priority_action_rows,
        open_blockers=open_blockers,
        insight_snapshot=snapshot,
        agents_used=len(agents),
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in swot_qa)
    quality, reliance, rationale = _quality_reliance(
        items=strengths + weaknesses + opportunities + threats + unresolved,
        open_blockers=open_blockers,
        agents_used=len(agents),
        qa_fail=qa_fail,
    )

    out = {
        "document": "Buyer's Perspective Analysis",
        "dd_code": _DD_CODE,
        "slug": _AGENT_KEY,
        "insight_snapshot": snapshot,
        "sector": sector or _NA,
        "geography": geography or _NA,
        "synthesis_rules": {
            "trace": _TRACE_RULE,
            "states": _STATE_RULE,
            "quantify": _QUANT_RULE,
            "rank": _RANK_RULE,
            "disagree": _DISAGREE_RULE,
            "finding_id": _FINDING_ID_RULE,
            "gap": _GAP_RULE,
            "action": _ACTION_RULE,
            "dedup": _DEDUP_RULE,
            "blocker": _BLOCKER_RULE,
        },
        "strengths_structured": strengths,
        "weaknesses_structured": weaknesses,
        "opportunities_structured": opportunities,
        "threats_structured": threats,
        "information_gaps": unexamined,
        "unresolved_items": unresolved,
        "priority_action_rows": priority_action_rows,
        "open_blockers": open_blockers,
        "swot_evidence_qa": swot_qa,
        "ranked_items": (strengths + weaknesses + threats + opportunities + unresolved)[:12],
        # Legacy dual-write
        "strengths": legacy_strengths,
        "weaknesses": legacy_weaknesses,
        "opportunities": legacy_opportunities,
        "threats": legacy_threats,
        "porter_forces": porter,
        "upstream_agents_used": sorted(agents.keys()),
        "primary_sources": srcs[:12],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "composer": "heuristic_swot_v1",
        "empty": empty,
    }
    out["questions"] = _questions_from_swot_gaps(out)
    return out


def _llm_swot_analysis_spec(
    *,
    company: str,
    prior_digest: str,
    sources: list[str],
    sector: str | None,
    geography: str | None,
    materiality: str | None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import generate_json

    system = compose_system(
        "swot_analysis",
        sector=sector,
        geography=geography,
        materiality=materiality,
        deal_perimeter=deal_perimeter,
        transaction_type=transaction_type,
        as_of_date=as_of_date,
        review_periods=review_periods,
        decision_stage=decision_stage,
    )
    src_lines = "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:12], start=1)) or "[1] (none)"
    user = (
        f"Company: {company}\n"
        f"Sector: {sector or 'unknown'}\n"
        f"Geography: {geography or 'unknown'}\n\n"
        "Upstream agent findings (only source of truth — do not invent numbers):\n"
        f"{prior_digest[:12000]}\n\n"
        f"Sources:\n{src_lines}\n\n"
        "Return JSON with keys: insight_snapshot, strengths_structured, "
        "weaknesses_structured, opportunities_structured, threats_structured, "
        "information_gaps, unresolved_items, priority_action_rows, open_blockers, "
        "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
        "Each structured item needs: finding_id, state, evidence_class, statement, "
        "source_agent, source_finding, quantification, evidence_status, "
        "thesis_effect, rank. disagreeing_agents when unresolved.\n"
        "priority_action_rows: [{combo (SO|ST|WO|WT), finding_ids, action, owner, "
        "timing, success_measure}].\n"
        "evidence_class must be one of: demonstrated, external_possibility, "
        "unexamined, unresolved. Unexamined items must NOT appear in weaknesses.\n"
        "Open blockers must remain visible — do not clear by net-positive tone. "
        "No invest/pass. No new numbers."
    )
    try:
        return generate_json(system=system, user=user)
    except Exception:  # noqa: BLE001
        return None


def _normalise_llm_spec(raw: dict[str, Any], *, heur: dict[str, Any]) -> dict[str, Any]:
    out = dict(heur)
    if not isinstance(raw, dict):
        return out

    def _norm_list(key: str, evidence_class: str | None = None) -> list[dict[str, Any]]:
        rows = raw.get(key) if isinstance(raw.get(key), list) else []
        cleaned: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("statement"):
                continue
            agent = str(row.get("source_agent") or "").strip()
            finding = str(row.get("source_finding") or row.get("statement") or "")
            if not agent:
                continue  # reject untraced
            quant = str(row.get("quantification") or _NA)
            if quant != _NA:
                digits = re.sub(r"[^\d.]", "", quant)
                if digits and digits not in re.sub(r"[^\d.]", "", finding):
                    quant = _NA  # defect: invented number
            ec = str(row.get("evidence_class") or evidence_class or "demonstrated")
            if ec == "assertion":
                ec = "unexamined"
            if key == "information_gaps":
                ec = "unexamined"
            if key == "unresolved_items":
                ec = "unresolved"
            # Never allow unexamined into weaknesses
            state = str(row.get("state") or "opportunity")
            if ec == "unexamined":
                state = "opportunity"
            cleaned.append(
                {
                    "finding_id": str(row.get("finding_id") or "").strip(),
                    "state": state,
                    "evidence_class": ec,
                    "statement": _soften_invest(_clean(row.get("statement"), 220)),
                    "source_agent": agent,
                    "source_finding": _soften_invest(_clean(finding, 280)),
                    "quantification": quant,
                    "evidence_status": str(
                        row.get("evidence_status")
                        or "Upstream evidence status not upgraded"
                    ),
                    "thesis_effect": str(row.get("thesis_effect") or "secondary"),
                    "rank": int(row.get("rank") or len(cleaned) + 1),
                    "disagreeing_agents": [
                        str(a) for a in (row.get("disagreeing_agents") or []) if a
                    ],
                }
            )
        return cleaned

    for key in (
        "strengths_structured",
        "weaknesses_structured",
        "opportunities_structured",
        "threats_structured",
        "information_gaps",
        "unresolved_items",
    ):
        normalised = _norm_list(key)
        if normalised:
            out[key] = _assign_finding_ids(normalised)

    # Rebuild legacy dual-write from structured
    out["strengths"] = [_format_line(it) for it in out.get("strengths_structured") or []]
    # Strip any unexamined that LLM wrongly put in weaknesses
    weak = [
        it for it in (out.get("weaknesses_structured") or [])
        if it.get("evidence_class") != "unexamined"
    ]
    out["weaknesses_structured"] = weak
    out["weaknesses"] = [_format_line(it) for it in weak]
    out["opportunities"] = [_format_line(it) for it in out.get("opportunities_structured") or []]
    out["threats"] = [_format_line(it) for it in out.get("threats_structured") or []]

    if isinstance(raw.get("open_blockers"), list) and raw["open_blockers"]:
        out["open_blockers"] = [
            _clean(b, 220) for b in raw["open_blockers"] if isinstance(b, str)
        ][:6]
    if raw.get("insight_snapshot"):
        snap = _soften_invest(_clean(raw["insight_snapshot"], 400))
        if out.get("open_blockers") and "blocker" not in snap.lower():
            snap = f"{snap} OPEN BLOCKER: {out['open_blockers'][0][:80]}"
        out["insight_snapshot"] = snap

    strengths = list(out.get("strengths_structured") or [])
    weaknesses = list(out.get("weaknesses_structured") or [])
    opportunities = list(out.get("opportunities_structured") or [])
    threats = list(out.get("threats_structured") or [])
    gaps = list(out.get("information_gaps") or [])
    unresolved = list(out.get("unresolved_items") or [])
    open_blockers = list(out.get("open_blockers") or [])

    llm_actions = (
        raw.get("priority_action_rows")
        if isinstance(raw.get("priority_action_rows"), list)
        else None
    )
    if llm_actions:
        cleaned_actions = []
        for row in llm_actions:
            if not isinstance(row, dict) or not row.get("action"):
                continue
            cleaned_actions.append(
                {
                    "combo": str(row.get("combo") or "SO"),
                    "finding_ids": [
                        str(x) for x in (row.get("finding_ids") or []) if x
                    ],
                    "action": _soften_invest(_clean(row.get("action"), 200)),
                    "owner": str(
                        row.get("owner")
                        or "Information request: action owner"
                    ),
                    "timing": str(
                        row.get("timing")
                        or "Information request: timing before IC"
                    ),
                    "success_measure": str(
                        row.get("success_measure")
                        or "Information request: success measure"
                    ),
                    "notes": _ACTION_RULE,
                }
            )
        out["priority_action_rows"] = cleaned_actions or _build_priority_action_rows(
            strengths=strengths,
            weaknesses=weaknesses,
            opportunities=opportunities,
            threats=threats,
            open_blockers=open_blockers,
        )
    else:
        out["priority_action_rows"] = _build_priority_action_rows(
            strengths=strengths,
            weaknesses=weaknesses,
            opportunities=opportunities,
            threats=threats,
            open_blockers=open_blockers,
        )

    swot_qa = _swot_evidence_qa(
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=opportunities,
        threats=threats,
        information_gaps=gaps,
        unresolved=unresolved,
        priority_action_rows=list(out.get("priority_action_rows") or []),
        open_blockers=open_blockers,
        insight_snapshot=str(out.get("insight_snapshot") or ""),
        agents_used=len(out.get("upstream_agents_used") or []),
    )
    out["swot_evidence_qa"] = swot_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in swot_qa)

    # Never upgrade reliance above heuristic when blockers exist
    if out.get("open_blockers"):
        out["reliance_verdict"] = "BLOCKED"
    elif raw.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}:
        # Do not upgrade vs heuristic
        order = {"BLOCKED": 0, "LIMITED": 1, "READY": 2}
        llm_r = str(raw["reliance_verdict"])
        heur_r = str(heur.get("reliance_verdict") or "LIMITED")
        out["reliance_verdict"] = llm_r if order.get(llm_r, 9) <= order.get(heur_r, 9) else heur_r
    if raw.get("quality_verdict") in {"PASS", "REWORK"}:
        # Do not upgrade PASS over REWORK
        if heur.get("quality_verdict") == "REWORK":
            out["quality_verdict"] = "REWORK"
        else:
            out["quality_verdict"] = raw["quality_verdict"]

    if qa_fail and out.get("reliance_verdict") == "READY":
        out["reliance_verdict"] = "LIMITED"
        out["quality_reliance_rationale"] = (
            str(out.get("quality_reliance_rationale") or "")
            + " Open SWOT QA FAILs cap READY → LIMITED."
        ).strip()
    elif qa_fail:
        out["quality_reliance_rationale"] = (
            str(out.get("quality_reliance_rationale") or "")
            + " Open SWOT QA FAILs remain."
        ).strip()

    llm_questions = raw.get("questions") if isinstance(raw.get("questions"), list) else None
    if llm_questions:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q = []
        for raw_q in llm_questions:
            q = normalize_question(raw_q)
            if q:
                filled_q.append(q)
        out["questions"] = filled_q or _questions_from_swot_gaps(out)
    else:
        out["questions"] = _questions_from_swot_gaps(out)

    out["composer"] = "llm_swot_v1"
    out["empty"] = not any(
        [
            out.get("strengths"),
            out.get("weaknesses"),
            out.get("opportunities"),
            out.get("threats"),
            out.get("information_gaps"),
        ]
    )
    return out


def build_swot_analysis_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    prior: dict[str, dict] | None = None,
    foundation: dict[str, Any] | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal

    _ = index  # synthesis reads agents, not raw VDR
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography") or getattr(deal, "geography", None)
    sector = vars_.get("sector") or getattr(deal, "sector", None)
    if isinstance(sector, str) and sector.strip().lower() in {"generic", "unknown", ""}:
        sector = None

    agents = _collect_prior_agents(deal, prior=prior, foundation=foundation)
    srcs = list(sources or [])
    heur = _heuristic_swot_analysis_spec(
        company=target,
        prior_agents=agents,
        sources=srcs,
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        legacy_spec=legacy_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    # Digest for LLM
    digest_bits: list[str] = []
    for slug, payload in agents.items():
        spec = _spec_of(payload)
        digest_bits.append(f"## {slug}")
        if spec.get("insight_snapshot"):
            digest_bits.append(str(spec["insight_snapshot"])[:300])
        for f in (payload.get("findings") or [])[:4]:
            if isinstance(f, str):
                digest_bits.append(f"- {f[:200]}")
        digest_bits.append(
            f"quality={spec.get('quality_verdict')} reliance={spec.get('reliance_verdict')}"
        )
    llm_raw = _llm_swot_analysis_spec(
        company=target,
        prior_digest="\n".join(digest_bits),
        sources=srcs or heur.get("primary_sources") or [],
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
    out = _normalise_llm_spec(llm_raw, heur=heur)
    out["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return out


def render_swot_analysis_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    def _section(label: str, rows: list, rule: str) -> list[str]:
        parts = [f"## {label}\n\n", f"{rule}\n\n"]
        if not rows:
            parts.append(f"_{_NA}_\n\n")
            return parts
        for it in rows:
            if isinstance(it, dict):
                fid = _clean(it.get("finding_id") or "—", 24)
                parts.append(f"- **[{fid}] {_format_line(it)}**\n")
                parts.append(
                    f"  - Source finding: {_clean(it.get('source_finding'), 200)}\n"
                    f"  - Evidence class: {it.get('evidence_class')} · "
                    f"Status: {_clean(it.get('evidence_status'), 80)}\n"
                    f"  - Thesis effect: {it.get('thesis_effect')} · Rank: {it.get('rank')}\n"
                )
                if it.get("disagreeing_agents"):
                    parts.append(
                        f"  - Disagreeing agents: {', '.join(it['disagreeing_agents'])}\n"
                    )
            else:
                parts.append(f"- {_clean(it, 220)}\n")
        parts.append("\n")
        return parts

    srcs = sources or spec.get("primary_sources") or []
    parts: list[str] = [
        f"# {title}\n\n",
        f"{_clean(spec.get('insight_snapshot'), 400)}\n\n",
        f"**Sector:** {_clean(spec.get('sector') or _NA, 60)}  \n"
        f"**Geography:** {_clean(spec.get('geography') or _NA, 60)}\n\n",
        f"{_TRACE_RULE}\n\n",
        f"{_FINDING_ID_RULE}\n\n",
        f"{_GAP_RULE}\n\n",
        f"{_BLOCKER_RULE}\n\n",
    ]

    open_blockers = spec.get("open_blockers") if isinstance(spec.get("open_blockers"), list) else []
    if open_blockers:
        parts.append("## Open Blockers\n\n")
        parts.append(
            "Positive tone must not override these. Synthesis does not clear blockers.\n\n"
        )
        for b in open_blockers:
            parts.append(f"- **{_clean(b, 220)}**\n")
        parts.append("\n---\n\n")

    parts.extend(
        _section(
            "1. Demonstrated Strengths",
            spec.get("strengths_structured") or spec.get("strengths") or [],
            _STATE_RULE,
        )
    )
    parts.append("---\n\n")
    parts.extend(
        _section(
            "2. Demonstrated Weaknesses",
            spec.get("weaknesses_structured") or spec.get("weaknesses") or [],
            "Proven weaknesses only — unexamined areas are listed separately.",
        )
    )
    parts.append("---\n\n")
    parts.extend(
        _section(
            "3. External Possibilities (Opportunities)",
            spec.get("opportunities_structured") or spec.get("opportunities") or [],
            _QUANT_RULE,
        )
    )
    parts.append("---\n\n")
    parts.extend(
        _section(
            "4. External Possibilities (Threats)",
            spec.get("threats_structured") or spec.get("threats") or [],
            _RANK_RULE,
        )
    )
    parts.append("---\n\n")
    parts.extend(
        _section(
            "5. Information Gaps (Unexamined — Not Weaknesses)",
            spec.get("information_gaps") or [],
            _GAP_RULE,
        )
    )
    parts.append("---\n\n")
    parts.extend(
        _section(
            "6. Unresolved Disagreements",
            spec.get("unresolved_items") or [],
            _DISAGREE_RULE,
        )
    )
    parts.append("---\n\n")

    # 7 Priority action rows
    actions = (
        spec.get("priority_action_rows")
        if isinstance(spec.get("priority_action_rows"), list)
        else []
    )
    parts.append("## 7. Priority Action Rows\n\n")
    parts.append(f"{_ACTION_RULE}\n\n")
    if actions:
        parts.append("| Combo | Finding IDs | Action | Owner | Timing | Success measure |\n")
        parts.append("| --- | --- | --- | --- | --- | --- |\n")
        for row in actions:
            if not isinstance(row, dict):
                continue
            ids = ", ".join(str(x) for x in (row.get("finding_ids") or [])[:4]) or "—"
            parts.append(
                f"| {_clean(row.get('combo'), 12)} | {_clean(ids, 40)} | "
                f"{_clean(row.get('action'), 80)} | {_clean(row.get('owner'), 40)} | "
                f"{_clean(row.get('timing'), 36)} | "
                f"{_clean(row.get('success_measure'), 60)} |\n"
            )
        parts.append("\n")
    else:
        parts.append(f"_{_NA}_\n\n")
    parts.append("---\n\n")

    upstream = spec.get("upstream_agents_used") or []
    parts.append("## Upstream Agents Used\n\n")
    if upstream:
        parts.append(", ".join(f"`{a}`" for a in upstream) + "\n\n")
    else:
        parts.append(f"{_NA}\n\n")
    parts.append("---\n\n")

    # 8 QA
    swot_qa = (
        spec.get("swot_evidence_qa")
        if isinstance(spec.get("swot_evidence_qa"), list)
        else []
    )
    parts.append("## 8. SWOT Evidence QA\n\n")
    parts.append(
        "QA enforces finding-ID + evidence status, gap ≠ weakness, priority "
        "action-row completeness, dedup / conflict handling, blockers not "
        "overridden by net-positive narrative, and upstream tracing.\n\n"
    )
    if swot_qa:
        parts.append("| Check | Status | Finding | Action |\n")
        parts.append("| --- | --- | --- | --- |\n")
        for r in swot_qa:
            if not isinstance(r, dict):
                continue
            parts.append(
                f"| {_clean(r.get('check'), 48)} | {_clean(r.get('status'), 12)} | "
                f"{_clean(r.get('finding'), 160)} | {_clean(r.get('action'), 120)} |\n"
            )
        parts.append("\n")
    else:
        parts.append(
            f"**Information request: SWOT evidence QA rows**\n\n"
        )
    parts.append("---\n\n")

    # 9 Questions
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    parts.append("## 9. Questions and Inputs Required\n\n")
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
            "None are missing — material SWOT gaps are closed, "
            "or no Questions were generated from open QA FAILs.\n\n"
        )
    parts.append("---\n\n")

    # 10 Quality
    parts.append("## 10. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "LIMITED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append("| Metric | Verdict / Explanation |\n")
    parts.append("| --- | --- |\n")
    parts.append(f"| Quality Verdict | {_clean(qv, 30)} |\n")
    parts.append(f"| Reliance Verdict | {_clean(rv, 30)} |\n")
    parts.append(f"| Rationale | {_clean(rationale, 460)} |\n\n")
    parts.append(
        f"**Quality:** {_clean(qv, 20)} — is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(rv, 20)} — can a decision rest on this SWOT synthesis?\n\n"
    )
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open SWOT QA FAILs cap READY → LIMITED. Open blockers keep reliance BLOCKED. "
        f"{_GAP_RULE} {_BLOCKER_RULE} "
        "This agent does not issue an invest or pass recommendation.*\n\n"
    )
    parts.append("---\n\n")

    parts.append(f"{_SOURCES_MARKER}\n\n")
    parts.append("## Sources\n\n")
    if srcs:
        for i, s in enumerate(srcs, start=1):
            parts.append(f"{i}. {_clean(s, 120)}\n")
    else:
        parts.append(f"1. {_DOC_CITE}\n")
    parts.append(f"\n_{_COMPUTED}_\n")
    return "".join(parts)
