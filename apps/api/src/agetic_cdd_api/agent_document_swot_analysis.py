"""Compose DiligenceIQ SWOT Analysis — synthesis of validated upstream findings.

Creates no new facts. Every item traced to an upstream agent and finding.
Quantification only when the source finding carried it. Information gaps kept
separate from proven weaknesses. Ranked by effect on price or thesis.

Four states: demonstrated strength, demonstrated weakness, external
possibility, unexamined area (never a weakness). Disagreements carried as
unresolved naming both agents. No confidence upgrade. Open blockers are not
overridden by positive tone.

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

# Upstream agents SWOT synthesises from (deep dive + foundations).
_UPSTREAM_SLUGS: tuple[str, ...] = (
    "competitor_identification",
    "competitive_differentiation",
    "market_share_strategy",
    "customer_stickiness",
    "customer_satisfaction",
    "customer_segmentation",
    "revenue_quality",
    "cost_structure",
    "historical_performance",
    "capital_structure",
    "market_risk",
    "internal_risk",
    "growth_opportunities",
    "synergies",
    "market_volume_and_growth",
    "market_pricing",
    "demand_drivers",
    "supplier_dependence",
    "operational_risk",
    "ip_and_technology",
    "management_quality",
    "regulatory_compliance",
    "esg_and_sustainability",
)

_FOUNDATION_SLUG_BY_CODE = {
    "F-IP": "ip_and_technology",
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
    return {
        "state": state,
        "evidence_class": evidence_class,
        "statement": stmt,
        "source_agent": source_agent,
        "source_finding": finding,
        "quantification": quant or _NA,
        "evidence_status": evidence_status,
        "thesis_effect": thesis_effect,
        "rank_hint": rank_hint,
        "disagreeing_agents": list(disagreeing_agents or []),
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


def _harvest_customer_satisfaction(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("nps_benchmark") or spec.get("satisfaction_metrics") or []):
        if not isinstance(row, dict):
            continue
        finding = " ".join(
            str(row.get(k) or "")
            for k in ("metric", "value", "peer", "gap", "note", "nps")
            if row.get(k) is not None
        )
        if not finding.strip():
            continue
        nums = _quant_from(finding)
        low = finding.lower()
        if "gap" in low or "below" in low or "underperform" in low:
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=finding,
                    source_agent="customer_satisfaction",
                    source_finding=finding,
                    quantification=nums,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=15,
                )
            )
    for finding in (payload.get("findings") or [])[:3]:
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
    return out


def _harvest_competitor_identification(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    peers = spec.get("competitive_set") or spec.get("competitors_legacy") or spec.get("competitors") or []
    named = [
        r for r in peers
        if isinstance(r, dict) and r.get("name") and not str(r["name"]).startswith("Information")
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
    for bom in (spec.get("bom_components") or [])[:1]:
        if isinstance(bom, dict) and bom.get("share_pct") is not None:
            cat = bom.get("category") or "BOM"
            pct = bom["share_pct"]
            out.append(
                _item(
                    state="weakness" if float(pct) >= 30 else "strength",
                    evidence_class="demonstrated",
                    statement=f"Largest cost bucket {cat} at {pct}% of mapped costs.",
                    source_agent="cost_structure",
                    source_finding=f"{cat} {pct}%",
                    quantification=f"{pct}%",
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=21,
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
        if not risk:
            continue
        mech = str(row.get("mechanism") or row.get("likelihood_argument") or "").strip()
        finding = f"{risk}" + (f" — {mech}" if mech else "")
        out.append(
            _item(
                state="threat",
                evidence_class="external_possibility",
                statement=risk,
                source_agent="market_risk",
                source_finding=finding,
                evidence_status=status,
                thesis_effect="blocker" if "indemnity" in finding.lower() or "cp" in finding.lower() else "thesis",
                rank_hint=9 if row.get("impact") else 23,
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
    for row in (spec.get("observed_weaknesses") or [])[:3]:
        if not isinstance(row, dict):
            continue
        w = str(row.get("weakness") or "").strip()
        ev = str(row.get("evidence") or "").strip()
        if not w:
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
        if not name:
            continue
        evid = str(row.get("evidence_class") or row.get("status") or "").lower()
        sizing = str(row.get("sizing") or row.get("size") or row.get("note") or "")
        finding = f"{name}: {sizing}".strip(": ")
        if "hypothesis" in evid or row.get("hypothesis"):
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="external_possibility",
                    statement=name,
                    source_agent="growth_opportunities",
                    source_finding=finding,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=40,
                )
            )
        else:
            out.append(
                _item(
                    state="opportunity",
                    evidence_class="external_possibility",
                    statement=name,
                    source_agent="growth_opportunities",
                    source_finding=finding,
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=30,
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
    return out


def _harvest_capital_structure(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for row in (spec.get("facilities") or spec.get("facility_schedule") or [])[:2]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("facility") or row.get("name") or "").strip()
        amount = str(row.get("amount") or row.get("drawn") or "").strip()
        if name:
            finding = f"{name} {amount}".strip()
            out.append(
                _item(
                    state="threat",
                    evidence_class="demonstrated",
                    statement=finding,
                    source_agent="capital_structure",
                    source_finding=finding,
                    evidence_status=status,
                    thesis_effect="price",
                    rank_hint=18,
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
    for row in (spec.get("concentration") or spec.get("suppliers") or [])[:2]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("supplier") or row.get("name") or "").strip()
        pct = row.get("share_pct") or row.get("concentration_pct")
        if name and pct is not None:
            finding = f"{name} {pct}%"
            out.append(
                _item(
                    state="weakness",
                    evidence_class="demonstrated",
                    statement=f"Supplier concentration — {name} at {pct}%.",
                    source_agent="supplier_dependence",
                    source_finding=finding,
                    quantification=f"{pct}%",
                    evidence_status=status,
                    thesis_effect="thesis",
                    rank_hint=16,
                )
            )
    return out


def _harvest_volume(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    status = _evidence_status(spec, payload)
    out: list[dict[str, Any]] = []
    for key in ("sam_cagr_pct", "tam_cagr_pct", "cagr_pct"):
        growth = spec.get("market_growth") if isinstance(spec.get("market_growth"), dict) else {}
        val = growth.get(key) if growth else spec.get(key)
        if val is None and isinstance(spec.get("ceiling"), dict):
            val = spec["ceiling"].get(key)
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
    return out


_HARVESTERS: dict[str, Any] = {
    "revenue_quality": _harvest_revenue_quality,
    "customer_stickiness": _harvest_customer_stickiness,
    "customer_satisfaction": _harvest_customer_satisfaction,
    "customer_segmentation": _harvest_customer_segmentation,
    "competitive_differentiation": _harvest_competitive_differentiation,
    "market_share_strategy": _harvest_market_share,
    "competitor_identification": _harvest_competitor_identification,
    "cost_structure": _harvest_cost_structure,
    "historical_performance": _harvest_historical_performance,
    "market_risk": _harvest_market_risk,
    "internal_risk": _harvest_internal_risk,
    "growth_opportunities": _harvest_growth,
    "synergies": _harvest_synergies,
    "capital_structure": _harvest_capital_structure,
    "supplier_dependence": _harvest_supplier,
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


def _quality_reliance(
    *,
    items: list[dict[str, Any]],
    open_blockers: list[str],
    agents_used: int,
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
    quality, reliance, rationale = _quality_reliance(
        items=strengths + weaknesses + opportunities + threats + unresolved,
        open_blockers=open_blockers,
        agents_used=len(agents),
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

    return {
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
        },
        "strengths_structured": strengths,
        "weaknesses_structured": weaknesses,
        "opportunities_structured": opportunities,
        "threats_structured": threats,
        "information_gaps": unexamined,
        "unresolved_items": unresolved,
        "open_blockers": open_blockers,
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


def _llm_swot_analysis_spec(
    *,
    company: str,
    prior_digest: str,
    sources: list[str],
    sector: str | None,
    geography: str | None,
    materiality: str | None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import generate_json

    system = compose_system(
        "swot_analysis",
        sector=sector,
        geography=geography,
        materiality=materiality,
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
        "information_gaps, unresolved_items, open_blockers, "
        "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
        "Each structured item needs: state, evidence_class, statement, "
        "source_agent, source_finding, quantification, evidence_status, "
        "thesis_effect, rank. disagreeing_agents when unresolved.\n"
        "evidence_class must be one of: demonstrated, external_possibility, "
        "unexamined, unresolved. Unexamined items must NOT appear in weaknesses.\n"
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
            out[key] = normalised

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
    )
    if not llm_raw:
        return heur
    return _normalise_llm_spec(llm_raw, heur=heur)


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
                parts.append(f"- **{_format_line(it)}**\n")
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
            "An unexamined area is never a weakness.",
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

    upstream = spec.get("upstream_agents_used") or []
    parts.append("## Upstream Agents Used\n\n")
    if upstream:
        parts.append(", ".join(f"`{a}`" for a in upstream) + "\n\n")
    else:
        parts.append(f"{_NA}\n\n")

    parts.append("---\n\n")
    parts.append("## Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'REWORK', 16)}  \n"
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 16)}  \n"
        f"{_clean(spec.get('quality_reliance_rationale'), 400)}\n\n"
    )

    parts.append(f"{_SOURCES_MARKER}\n\n")
    parts.append("## Sources\n\n")
    if srcs:
        for i, s in enumerate(srcs, start=1):
            parts.append(f"{i}. {_clean(s, 120)}\n")
    else:
        parts.append(f"1. {_DOC_CITE}\n")
    parts.append(f"\n_{_COMPUTED}_\n")
    return "".join(parts)
