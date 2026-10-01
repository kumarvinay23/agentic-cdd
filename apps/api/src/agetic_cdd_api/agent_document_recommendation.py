"""Compose DiligenceIQ Recommendations — findings converted to deal actions.

Every recommendation names its finding. A recommendation with no finding is
deleted. Actions classified as: price adjustment, deal structure, contractual
protection, condition precedent, or post-completion. Price / structure /
protection kept separate. CPs carry owner + acceptance test. First hundred
days only where a finding requires it. Open items state whether they block
a decision or can be carried with a protection.

Dual-writes legacy FV-07 fields (deal_structure / returns_by_scenario /
conditions_precedent / hundred_day_plan / monitoring_metrics).

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
    r"|\b(?:invest|pass)\s+recommendation\b"
    r"|\bgo\s*/\s*no[- ]?go\b"
)

_DOCUMENT_TITLE = "Recommendations"
_FV_CODE = "FV-07"
_AGENT_KEY = "recommendation"

_ACTION_CLASSES = (
    "price_adjustment",
    "deal_structure",
    "contractual_protection",
    "condition_precedent",
    "post_completion",
)

_CLASSIFY_RULE = (
    "For each material finding, state the action it implies and classify it: "
    "price adjustment, deal structure, contractual protection, condition "
    "precedent, or post-completion action."
)
_QUANT_RULE = (
    "Quantify the price or structural effect where the finding supports it. "
    "Say plainly where it cannot be quantified yet and what would bound it."
)
_CP_RULE = (
    "List conditions that must close before signing or completion, each with "
    "an owner and an acceptance test."
)
_DAY100_RULE = (
    "Give the first hundred days only where a finding requires it — an "
    "integration step, a control fix, a key-person retention action."
)
_OPEN_RULE = (
    "State what is still open, and whether the openness blocks a decision or "
    "can be carried with a protection."
)
_TRACE_RULE = (
    "Every recommendation names its finding. A recommendation with no finding "
    "behind it is deleted."
)

_UPSTREAM_SLUGS: tuple[str, ...] = (
    "market_risk",
    "internal_risk",
    "revenue_quality",
    "customer_stickiness",
    "cost_structure",
    "capital_structure",
    "historical_performance",
    "regulatory_compliance",
    "swot_analysis",
    "growth_opportunities",
    "synergies",
    "valuation_modeling",
    "ic_synthesis",
    "competitive_differentiation",
    "supplier_dependence",
    "operational_risk",
    "ip_and_technology",
)


def _soften(text: str) -> str:
    t = _INVEST_LANG.sub("frame the action", text or "")
    return t


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if value is None:
        return []
    return [value]


def _spec_of(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    spec = payload.get("spec")
    return spec if isinstance(spec, dict) else {}


def _action(
    *,
    action: str,
    action_class: str,
    source_finding: str,
    source_agent: str,
    quantified_effect: str | None = None,
    cannot_quantify_reason: str | None = None,
    bound_by: str | None = None,
    owner: str | None = None,
    acceptance_test: str | None = None,
    timing: str | None = None,
    blocks_decision: bool | None = None,
    carry_with_protection: str | None = None,
) -> dict[str, Any] | None:
    finding = _soften(_clean(source_finding, 280))
    act = _soften(_clean(action, 220))
    if not finding or not act:
        return None  # deleted — no finding or no action
    if action_class not in _ACTION_CLASSES:
        return None
    row: dict[str, Any] = {
        "action": act,
        "action_class": action_class,
        "source_finding": finding,
        "source_agent": source_agent,
        "quantified_effect": quantified_effect or _NA,
        "cannot_quantify_reason": cannot_quantify_reason or "",
        "bound_by": bound_by or "",
        "owner": owner or "",
        "acceptance_test": acceptance_test or "",
        "timing": timing or "",
        "blocks_decision": bool(blocks_decision) if blocks_decision is not None else False,
        "carry_with_protection": carry_with_protection or "",
    }
    if action_class == "condition_precedent":
        if not row["owner"]:
            row["owner"] = "Deal counsel / diligence lead"
        if not row["acceptance_test"]:
            row["acceptance_test"] = (
                f"Evidence that addresses: {finding[:120]}"
            )
        if not row["timing"]:
            row["timing"] = "Before signing / completion"
    if action_class == "post_completion" and not row["timing"]:
        row["timing"] = "Day 0–100"
    return row


def _quant_or_gap(
    finding: str,
    *,
    effect: str | None = None,
    bound: str | None = None,
) -> tuple[str, str, str]:
    if effect and any(c.isdigit() for c in effect):
        return effect, "", ""
    # Try pull a number from the finding itself
    m = re.search(
        r"(?i)(?:INR|USD|\$)?\s*~?[\d,]+(?:\.\d+)?\s*(?:%|pp|x|Cr|Crore|B|M|mn)?",
        finding or "",
    )
    if m and effect is None:
        return m.group(0).strip(), "", ""
    reason = (
        "Cannot be quantified yet from the upstream finding"
        if not effect
        else str(effect)
    )
    return (
        _NA,
        reason,
        bound or "Would be bounded by a sized exposure, earn-out formula, or escrow quantum from diligence",
    )


def _harvest_market_risk(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    for row in _as_list(spec.get("price_vs_structure")):
        if not isinstance(row, dict):
            continue
        risk = str(row.get("risk") or "").strip()
        if not risk:
            continue
        classification = str(row.get("classification") or "").lower()
        protection = str(row.get("protection") or "").strip()
        finding = f"{risk}" + (f" — {protection}" if protection else "")
        if "price" in classification:
            quant, reason, bound = _quant_or_gap(finding, bound="Downside case / revenue exposed")
            a = _action(
                action=f"Price / underwriting adjustment for {risk}",
                action_class="price_adjustment",
                source_finding=finding,
                source_agent="market_risk",
                quantified_effect=quant if quant != _NA else None,
                cannot_quantify_reason=reason if quant == _NA else None,
                bound_by=bound if quant == _NA else None,
                timing="Pre-signing negotiation",
            )
            if a:
                out.append(a)
        elif "structure" in classification or "indemnity" in protection.lower() or "precedent" in protection.lower():
            if "precedent" in protection.lower() or "condition" in protection.lower():
                a = _action(
                    action=f"Condition precedent covering: {risk}",
                    action_class="condition_precedent",
                    source_finding=finding,
                    source_agent="market_risk",
                    owner="Deal counsel",
                    acceptance_test=(
                        f"CP satisfied — {protection}" if protection else f"CP satisfied for: {risk}"
                    ),
                    timing="Before completion",
                )
            else:
                a = _action(
                    action=f"Contractual protection: {protection or risk}",
                    action_class="contractual_protection",
                    source_finding=finding,
                    source_agent="market_risk",
                    timing="SPA / side letter",
                )
            if a:
                out.append(a)
        else:
            a = _action(
                action=f"Address external risk — {risk}",
                action_class="contractual_protection",
                source_finding=finding,
                source_agent="market_risk",
            )
            if a:
                out.append(a)

    for row in _as_list(spec.get("downside_cases"))[:3]:
        if not isinstance(row, dict):
            continue
        bound = str(row.get("bound") or row.get("scenario") or "").strip()
        if not bound:
            continue
        quant, reason, gap_bound = _quant_or_gap(
            bound, effect=bound if any(c.isdigit() for c in bound) else None
        )
        a = _action(
            action=f"Reflect sized downside in price negotiation: {bound[:120]}",
            action_class="price_adjustment",
            source_finding=bound,
            source_agent="market_risk",
            quantified_effect=quant if quant != _NA else None,
            cannot_quantify_reason=reason if quant == _NA else None,
            bound_by=gap_bound if quant == _NA else None,
            timing="Pre-signing",
        )
        if a:
            out.append(a)

    for row in _as_list(spec.get("unsized_risks"))[:2]:
        text = row.get("risk") if isinstance(row, dict) else row
        if not isinstance(text, str) or not text.strip():
            continue
        a = _action(
            action=f"Carry unsized risk with protection until sized: {text[:100]}",
            action_class="contractual_protection",
            source_finding=text,
            source_agent="market_risk",
            cannot_quantify_reason="Unsized in market risk — needs mechanism and quantum",
            bound_by="What would size it: revenue/margin exposed and time horizon",
            blocks_decision=False,
            carry_with_protection="Specific indemnity / information covenant until sized",
            timing="SPA",
        )
        if a:
            out.append(a)
    return out


def _harvest_internal_risk(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    for row in _as_list(spec.get("key_person_exposure"))[:4]:
        if not isinstance(row, dict):
            continue
        person = str(row.get("person") or "Key person").strip()
        depends = str(row.get("what_depends") or "").strip()
        finding = f"{person}: {depends}" if depends else person
        a = _action(
            action=f"Key-person retention / succession plan for {person}",
            action_class="post_completion",
            source_finding=finding,
            source_agent="internal_risk",
            cannot_quantify_reason="Retention cost not sized in upstream finding",
            bound_by="Would be bounded by retention package quantum and role coverage map",
            owner="Buyer HR / deal team",
            timing="Day 0–100",
            blocks_decision=True,
            carry_with_protection="Retention agreement + succession CP if role is deal-critical",
        )
        if a:
            out.append(a)
        # Also a CP when continuity is deal-critical
        a2 = _action(
            action=f"Condition precedent: retention agreement executed for {person}",
            action_class="condition_precedent",
            source_finding=finding,
            source_agent="internal_risk",
            owner="Buyer HR / deal counsel",
            acceptance_test=f"Signed retention / employment continuity for {person}",
            timing="Before completion",
            blocks_decision=True,
        )
        if a2:
            out.append(a2)

    for row in _as_list(spec.get("observed_weaknesses"))[:3]:
        if not isinstance(row, dict):
            continue
        w = str(row.get("weakness") or "").strip()
        ev = str(row.get("evidence") or "").strip()
        if not w:
            continue
        finding = f"{w} — {ev}" if ev else w
        a = _action(
            action=f"Control / systems remediation: {w}",
            action_class="post_completion",
            source_finding=finding,
            source_agent="internal_risk",
            cannot_quantify_reason="Remediation cost not sized upstream",
            bound_by="Would be bounded by remediation plan cost and timeline",
            owner="Ops / CTO",
            timing="Day 0–100",
        )
        if a:
            out.append(a)

    for row in _as_list(spec.get("control_testing"))[:2]:
        if not isinstance(row, dict):
            continue
        tested = str(row.get("tested") or "").lower()
        if "not tested" not in tested and "untested" not in tested:
            continue
        ctrl = str(row.get("control") or "control").strip()
        a = _action(
            action=f"Condition precedent: complete testing of {ctrl[:80]}",
            action_class="condition_precedent",
            source_finding=str(row.get("result") or ctrl),
            source_agent="internal_risk",
            owner="Security / compliance lead",
            acceptance_test=f"Test report issued with no open critical findings for: {ctrl[:80]}",
            timing="Before completion",
            blocks_decision=False,
            carry_with_protection="Can carry with specific indemnity if testing slips post-sign",
        )
        if a:
            out.append(a)

    for row in _as_list(spec.get("ranked_effects"))[:3]:
        if not isinstance(row, dict):
            continue
        effect = str(row.get("effect") or "").lower()
        risk = str(row.get("risk") or "").strip()
        if not risk:
            continue
        if "hundred" in effect or "day" in effect:
            # already covered via key-person; skip dupes if same person
            continue
        if "price" in effect:
            a = _action(
                action=f"Price adjustment implied by internal risk: {risk}",
                action_class="price_adjustment",
                source_finding=risk,
                source_agent="internal_risk",
                cannot_quantify_reason="Internal risk ranked to price but quantum not stated",
                bound_by="Would be bounded by EBITDA / cash impact of the weakness",
            )
            if a:
                out.append(a)
        elif "structure" in effect:
            a = _action(
                action=f"Deal structure response to internal risk: {risk}",
                action_class="deal_structure",
                source_finding=risk,
                source_agent="internal_risk",
            )
            if a:
                out.append(a)
    return out


def _harvest_revenue_quality(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    ret = spec.get("retention_metrics") if isinstance(spec.get("retention_metrics"), dict) else {}
    nrr = ret.get("nrr_pct")
    if nrr is not None:
        try:
            nrr_f = float(nrr)
        except (TypeError, ValueError):
            nrr_f = None
        if nrr_f is not None and nrr_f < 90:
            finding = f"NRR {nrr_f}%"
            a = _action(
                action=f"Price / earn-out gate tied to NRR recovery (currently {nrr_f}%)",
                action_class="price_adjustment",
                source_finding=finding,
                source_agent="revenue_quality",
                quantified_effect=f"NRR {nrr_f}%",
                cannot_quantify_reason="EV haircut not computed from NRR alone",
                bound_by="Would be bounded by revenue × retention delta × multiple",
                timing="Pre-signing",
            )
            if a:
                out.append(a)
            a2 = _action(
                action=f"Day 0–100: retention programme to lift NRR from {nrr_f}%",
                action_class="post_completion",
                source_finding=finding,
                source_agent="revenue_quality",
                quantified_effect=f"NRR {nrr_f}%",
                owner="CRO / customer success",
                timing="Day 0–100",
            )
            if a2:
                out.append(a2)
    for flag in _as_list(spec.get("quality_flags"))[:2]:
        if isinstance(flag, str) and flag.strip():
            a = _action(
                action=f"Verify revenue quality flag before signing: {flag[:100]}",
                action_class="condition_precedent",
                source_finding=flag,
                source_agent="revenue_quality",
                owner="Financial diligence lead",
                acceptance_test=f"Flag cleared or quantified: {flag[:100]}",
                timing="Before signing",
            )
            if a:
                out.append(a)
    return out


def _harvest_customer_stickiness(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    ret = spec.get("retention_metrics") if isinstance(spec.get("retention_metrics"), dict) else {}
    logo = ret.get("logo_churn_pct")
    if logo is not None:
        try:
            logo_f = float(logo)
        except (TypeError, ValueError):
            logo_f = None
        if logo_f is not None and logo_f >= 20:
            finding = f"Logo churn {logo_f}%"
            a = _action(
                action=f"Post-completion churn reduction plan (logo churn {logo_f}%)",
                action_class="post_completion",
                source_finding=finding,
                source_agent="customer_stickiness",
                quantified_effect=f"{logo_f}%",
                owner="Customer success lead",
                timing="Day 0–100",
            )
            if a:
                out.append(a)
    return out


def _harvest_cost_structure(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    metrics = spec.get("cost_metrics") if isinstance(spec.get("cost_metrics"), dict) else {}
    gm = metrics.get("gross_margin_pct")
    if gm is not None:
        try:
            gm_f = float(gm)
        except (TypeError, ValueError):
            gm_f = None
        if gm_f is not None and gm_f < 20:
            finding = f"Gross margin {gm_f}%"
            a = _action(
                action=f"Underwrite margin path from {gm_f}% — price case until path evidenced",
                action_class="price_adjustment",
                source_finding=finding,
                source_agent="cost_structure",
                quantified_effect=f"{gm_f}%",
                cannot_quantify_reason="Margin-to-EV bridge not stated upstream",
                bound_by="Would be bounded by gross profit dollars × exit multiple",
            )
            if a:
                out.append(a)
    for bom in _as_list(spec.get("bom_components"))[:1]:
        if isinstance(bom, dict) and bom.get("share_pct") is not None:
            cat = bom.get("category") or "BOM"
            pct = bom["share_pct"]
            if float(pct) >= 30:
                finding = f"{cat} {pct}%"
                a = _action(
                    action=f"Supplier / cost concentration protection on {cat} ({pct}%)",
                    action_class="contractual_protection",
                    source_finding=finding,
                    source_agent="cost_structure",
                    quantified_effect=f"{pct}%",
                    timing="SPA / supply side letter",
                )
                if a:
                    out.append(a)
    return out


def _harvest_capital_structure(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    for row in _as_list(spec.get("facilities") or spec.get("facility_schedule"))[:3]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("facility") or row.get("name") or "").strip()
        amount = str(row.get("amount") or row.get("drawn") or "").strip()
        if not name:
            continue
        finding = f"{name} {amount}".strip()
        a = _action(
            action=f"Deal structure: confirm treatment of {name} in sources & uses",
            action_class="deal_structure",
            source_finding=finding,
            source_agent="capital_structure",
            quantified_effect=amount if any(c.isdigit() for c in amount) else _NA,
            cannot_quantify_reason="" if any(c.isdigit() for c in amount) else "Facility quantum not fully stated",
            bound_by="" if any(c.isdigit() for c in amount) else "Would be bounded by facility schedule / payoff quote",
            timing="Signing / completion funds flow",
        )
        if a:
            out.append(a)
    for finding in (payload.get("findings") or [])[:2]:
        if isinstance(finding, str) and ("mezzanine" in finding.lower() or "maturity" in finding.lower()):
            a = _action(
                action=f"Condition precedent: refinance / consent path for {finding[:80]}",
                action_class="condition_precedent",
                source_finding=finding,
                source_agent="capital_structure",
                owner="Debt advisor / deal counsel",
                acceptance_test="Lender consent or refinance commitment letter",
                timing="Before completion",
                blocks_decision=True,
            )
            if a:
                out.append(a)
    return out


def _harvest_valuation(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    fvr = spec.get("final_valuation_range") if isinstance(spec.get("final_valuation_range"), dict) else {}
    if fvr.get("range_published"):
        low, high = fvr.get("ev_low_usd_b"), fvr.get("ev_high_usd_b")
        finding = f"Final EV range USD {low}–{high}B"
        a = _action(
            action=f"Negotiate within published EV range USD {low}–{high}B",
            action_class="price_adjustment",
            source_finding=finding,
            source_agent="valuation_modeling",
            quantified_effect=f"USD {low}–{high}B",
            timing="Pre-signing",
        )
        if a:
            out.append(a)
        walk = fvr.get("walk_away") or fvr.get("walk_away_price")
        if walk:
            a2 = _action(
                action=f"Walk-away discipline at {walk}",
                action_class="price_adjustment",
                source_finding=str(walk),
                source_agent="valuation_modeling",
                quantified_effect=str(walk) if any(c.isdigit() for c in str(walk)) else _NA,
            )
            if a2:
                out.append(a2)
    else:
        blockers = [
            b.get("name")
            for b in _as_list(fvr.get("blockers"))
            if isinstance(b, dict) and not b.get("ready")
        ]
        if blockers:
            finding = f"Final range withheld — {blockers[0]}"
            a = _action(
                action=f"Open: resolve valuation blocker '{blockers[0]}' before locking price",
                action_class="condition_precedent",
                source_finding=finding,
                source_agent="valuation_modeling",
                owner="Valuation lead",
                acceptance_test=f"Blocker cleared: {blockers[0]}",
                timing="Before IC price lock",
                blocks_decision=True,
            )
            if a:
                out.append(a)
    earn = spec.get("earnings_basis") if isinstance(spec.get("earnings_basis"), dict) else {}
    if earn.get("amount") is not None and not str(earn.get("amount")).startswith("Information"):
        finding = (
            f"Earnings basis: {earn.get('metric')} {earn.get('amount')} "
            f"{earn.get('unit')} ({earn.get('period')})"
        )
        a = _action(
            action="Anchor all price methods to the declared earnings basis",
            action_class="price_adjustment",
            source_finding=finding,
            source_agent="valuation_modeling",
            quantified_effect=f"{earn.get('amount')} {earn.get('unit')}",
        )
        if a:
            out.append(a)
    return out


def _harvest_regulatory(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    for row in _as_list(spec.get("conditions_precedent") or spec.get("transaction_triggers"))[:4]:
        if isinstance(row, dict):
            cp = str(row.get("condition") or row.get("trigger") or row.get("item") or "").strip()
            owner = str(row.get("owner") or "Regulatory counsel").strip()
            test = str(row.get("acceptance_test") or row.get("test") or "").strip()
            if not cp:
                continue
            a = _action(
                action=f"Condition precedent: {cp}",
                action_class="condition_precedent",
                source_finding=cp,
                source_agent="regulatory_compliance",
                owner=owner,
                acceptance_test=test or f"Evidence of clearance: {cp[:100]}",
                timing="Before completion",
            )
            if a:
                out.append(a)
        elif isinstance(row, str) and row.strip():
            a = _action(
                action=f"Condition precedent: {row.strip()[:120]}",
                action_class="condition_precedent",
                source_finding=row.strip(),
                source_agent="regulatory_compliance",
                owner="Regulatory counsel",
                acceptance_test=f"Clearance evidenced for: {row.strip()[:100]}",
            )
            if a:
                out.append(a)
    for row in _as_list(spec.get("indemnity_items") or spec.get("litigation"))[:2]:
        text = ""
        if isinstance(row, dict):
            text = str(row.get("item") or row.get("matter") or row.get("exposure") or "").strip()
        elif isinstance(row, str):
            text = row.strip()
        if not text:
            continue
        a = _action(
            action=f"Specific indemnity: {text[:100]}",
            action_class="contractual_protection",
            source_finding=text,
            source_agent="regulatory_compliance",
            timing="SPA",
        )
        if a:
            out.append(a)
    return out


def _harvest_swot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    for blocker in _as_list(spec.get("open_blockers"))[:4]:
        text = blocker if isinstance(blocker, str) else str(blocker)
        if not text.strip():
            continue
        a = _action(
            action=f"Resolve open SWOT blocker before decision lock: {text[:100]}",
            action_class="condition_precedent",
            source_finding=text,
            source_agent="swot_analysis",
            owner="Deal team",
            acceptance_test=f"Blocker cleared or carried with named protection: {text[:80]}",
            timing="Before IC decision",
            blocks_decision=True,
        )
        if a:
            out.append(a)
    for gap in _as_list(spec.get("information_gaps"))[:3]:
        if not isinstance(gap, dict):
            continue
        stmt = str(gap.get("statement") or "").strip()
        if not stmt:
            continue
        a = _action(
            action=f"Carry information gap with protection: {stmt[:100]}",
            action_class="contractual_protection",
            source_finding=stmt,
            source_agent=str(gap.get("source_agent") or "swot_analysis"),
            cannot_quantify_reason="Unexamined area — not a proven weakness",
            bound_by="Would be bounded once the gap is sized by the source agent",
            blocks_decision=False,
            carry_with_protection="Information covenant / specific indemnity until examined",
        )
        if a:
            out.append(a)
    return out


def _harvest_synergies(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    buyer = spec.get("buyer") if isinstance(spec.get("buyer"), dict) else {}
    if not buyer.get("named"):
        finding = str(
            spec.get("cannot_underwrite_reason")
            or "No named acquirer — synergies cannot be underwritten"
        )
        a = _action(
            action="Keep synergies out of stand-alone price until a buyer is named",
            action_class="deal_structure",
            source_finding=finding,
            source_agent="synergies",
            cannot_quantify_reason="No named buyer — no synergy number",
            bound_by="Would be bounded by bottom-up cost/revenue synergies once buyer named",
            blocks_decision=False,
            carry_with_protection="Separate synergy layer the committee can remove",
        )
        if a:
            out.append(a)
    elif spec.get("underwritable"):
        finding = f"Named buyer {buyer.get('buyer_name')} — underwritable synergies"
        a = _action(
            action="Present buyer synergies as a separate layer (not in stand-alone)",
            action_class="deal_structure",
            source_finding=finding,
            source_agent="synergies",
        )
        if a:
            out.append(a)
    return out


def _harvest_growth(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    for row in _as_list(spec.get("options"))[:2]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("option") or row.get("name") or "").strip()
        if not name:
            continue
        evid = str(row.get("evidence_class") or row.get("status") or "").lower()
        finding = f"{name}: {row.get('sizing') or row.get('size') or ''}".strip(": ")
        if "hypothesis" in evid:
            a = _action(
                action=f"Do not bake hypothesis growth '{name}' into base price",
                action_class="price_adjustment",
                source_finding=finding,
                source_agent="growth_opportunities",
                cannot_quantify_reason="Hypothesis option — not evidenced for base case",
                bound_by="Would enter upside / earn-out only once evidenced",
            )
        else:
            a = _action(
                action=f"Day 0–100 integration step if underwriting '{name}'",
                action_class="post_completion",
                source_finding=finding,
                source_agent="growth_opportunities",
                owner="Value creation lead",
                timing="Day 0–100",
            )
        if a:
            out.append(a)
    return out


def _harvest_ic_synthesis(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Carry IC concerns as actions only when they name a concrete finding — no new go/no-go."""
    spec = _spec_of(payload)
    out: list[dict[str, Any]] = []
    for risk in _as_list(spec.get("primary_risks"))[:4]:
        if not isinstance(risk, dict):
            continue
        name = str(risk.get("risk") or "").strip()
        mit = str(risk.get("mitigation") or "").strip()
        if not name or len(mit) < 8:
            continue
        if mit.endswith(("&", "+", "/", "—", "-")):
            continue
        finding = f"{name} — mitigation: {mit}"
        low_mit = mit.lower()
        if any(tok in low_mit for tok in ("indemnity", "escrow", "warranty")):
            cls = "contractual_protection"
        elif any(tok in low_mit for tok in ("cp", "condition", "precedent", "consent")):
            cls = "condition_precedent"
        elif any(tok in low_mit for tok in ("price", "earn-out", "haircut", "discount")):
            cls = "price_adjustment"
        else:
            cls = "deal_structure"
        a = _action(
            action=f"{mit} (for {name})",
            action_class=cls,
            source_finding=finding,
            source_agent="ic_synthesis",
            owner="Deal counsel" if cls == "condition_precedent" else "Deal team",
            acceptance_test=f"Mitigation in place for: {name}" if cls == "condition_precedent" else "",
            timing="Before completion" if cls == "condition_precedent" else "Pre-signing",
        )
        if a:
            out.append(a)
    return out


_HARVESTERS: dict[str, Any] = {
    "market_risk": _harvest_market_risk,
    "internal_risk": _harvest_internal_risk,
    "revenue_quality": _harvest_revenue_quality,
    "customer_stickiness": _harvest_customer_stickiness,
    "cost_structure": _harvest_cost_structure,
    "capital_structure": _harvest_capital_structure,
    "valuation_modeling": _harvest_valuation,
    "regulatory_compliance": _harvest_regulatory,
    "swot_analysis": _harvest_swot,
    "synergies": _harvest_synergies,
    "growth_opportunities": _harvest_growth,
    "ic_synthesis": _harvest_ic_synthesis,
}


def _dedupe_actions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("source_finding") or not row.get("action"):
            continue  # hard delete untraced
        key = (
            f"{row.get('action_class')}|{row.get('source_agent')}|"
            f"{str(row.get('action') or '').lower()[:80]}"
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _split_buckets(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {c: [] for c in _ACTION_CLASSES}
    for row in rows:
        cls = row.get("action_class")
        if cls in buckets:
            buckets[cls].append(row)
    # Caps — sharp actions beat laundry lists
    buckets["price_adjustment"] = buckets["price_adjustment"][:5]
    buckets["deal_structure"] = buckets["deal_structure"][:4]
    buckets["contractual_protection"] = buckets["contractual_protection"][:5]
    buckets["condition_precedent"] = buckets["condition_precedent"][:8]
    buckets["post_completion"] = buckets["post_completion"][:5]
    return buckets


def _open_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    open_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("blocks_decision") or row.get("carry_with_protection") or (
            row.get("quantified_effect") == _NA and row.get("cannot_quantify_reason")
        ):
            open_rows.append(
                {
                    "item": row.get("action"),
                    "source_finding": row.get("source_finding"),
                    "source_agent": row.get("source_agent"),
                    "blocks_decision": bool(row.get("blocks_decision")),
                    "carry_with_protection": row.get("carry_with_protection")
                    or (
                        "Carry with contractual protection until sized"
                        if not row.get("blocks_decision")
                        else ""
                    ),
                }
            )
        if len(open_rows) >= 8:
            break
    return open_rows


def _legacy_cp_lines(cps: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in cps:
        owner = row.get("owner") or "Owner TBD"
        test = row.get("acceptance_test") or ""
        line = f"CP: {row.get('action')} — owner: {owner}"
        if test:
            line += f"; test: {test}"
        line += f" [{row.get('source_agent')}]"
        lines.append(line[:280])
    return lines


def _legacy_day100(posts: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in posts:
        timing = row.get("timing") or "Day 0–100"
        if "day" not in timing.lower() and "100" not in timing:
            continue
        lines.append(
            f"{timing}: {row.get('action')} [{row.get('source_agent')}]"[:280]
        )
    return lines[:6]


def _deal_structure_summary(structures: list[dict[str, Any]], protections: list[dict[str, Any]]) -> str:
    bits: list[str] = []
    for row in structures[:2]:
        bits.append(str(row.get("action") or ""))
    for row in protections[:1]:
        bits.append(str(row.get("action") or ""))
    if not bits:
        return "Structure actions derived from upstream findings only — no free-standing structure invented"
    return _soften("; ".join(bits)[:280])


_INVENTED_RETURN_LADDER = {(8.0, 1.2), (18.0, 2.0), (28.0, 3.2)}


def _is_invented_return_row(row: dict[str, Any]) -> bool:
    """Detect the old illustrative Bear/Base/Bull ladder (no VDR evidence)."""
    try:
        irr = float(row["irr_pct"]) if row.get("irr_pct") is not None else None
        moic = float(row["moic_x"]) if row.get("moic_x") is not None else None
    except (TypeError, ValueError):
        return False
    if (irr, moic) not in _INVENTED_RETURN_LADDER:
        return False
    # Invented ladder never carried equity / premium evidence
    return (
        row.get("equity_value_per_share_inr") is None
        and row.get("premium_discount_vs_ipo_pct") is None
    )


def _returns_from_valuation(val_spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(val_spec, dict):
        return []
    # Prefer nested sensitivity cases if present
    sens = val_spec.get("sensitivity_analysis") if isinstance(val_spec.get("sensitivity_analysis"), dict) else {}
    cases = sens.get("cases") if isinstance(sens.get("cases"), list) else []
    out: list[dict[str, Any]] = []
    for row in cases:
        if not isinstance(row, dict):
            continue
        label = row.get("scenario") or row.get("case") or row.get("name")
        if not label:
            continue
        if row.get("irr_pct") is None and row.get("moic_x") is None:
            continue
        if _is_invented_return_row(row):
            continue
        out.append(
            {
                "scenario": str(label),
                "irr_pct": row.get("irr_pct"),
                "moic_x": row.get("moic_x"),
                "equity_value_per_share_inr": row.get("equity_value_per_share_inr"),
                "premium_discount_vs_ipo_pct": row.get("premium_discount_vs_ipo_pct"),
            }
        )
    if out:
        return out[:4]
    # Fall back to legacy returns if composer already put them on valuation
    legacy = val_spec.get("returns_by_scenario")
    if isinstance(legacy, list):
        return [
            r for r in legacy
            if isinstance(r, dict)
            and (r.get("irr_pct") is not None or r.get("moic_x") is not None)
            and not _is_invented_return_row(r)
        ][:4]
    return []


def _collect_agents(
    deal: Deal,
    *,
    prior: dict[str, dict] | None,
    findings_store: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    agents: dict[str, dict[str, Any]] = {}
    prior = prior if isinstance(prior, dict) else {}
    for slug in _UPSTREAM_SLUGS:
        payload = prior.get(slug)
        if not isinstance(payload, dict) or not payload.get("spec"):
            try:
                disk = read_agent_output_file(deal, agent_key=slug)
            except Exception:  # noqa: BLE001
                disk = None
            if isinstance(disk, dict):
                payload = disk
        # Soft-fill from deep-dive findings store agents map
        if (not isinstance(payload, dict) or not payload.get("spec")) and isinstance(
            findings_store, dict
        ):
            store_agents = findings_store.get("agents")
            if isinstance(store_agents, dict) and isinstance(store_agents.get(slug), dict):
                payload = store_agents[slug]
        if isinstance(payload, dict) and (payload.get("spec") or payload.get("findings")):
            agents[slug] = payload
    return agents


def _quality_reliance(
    *,
    rows: list[dict[str, Any]],
    open_items: list[dict[str, Any]],
    agents_used: int,
) -> tuple[str, str, str]:
    untraced = [r for r in rows if not r.get("source_finding") or not r.get("source_agent")]
    if untraced:
        return (
            "REWORK",
            "BLOCKED",
            "REWORK: recommendation(s) without a named finding were produced — delete them.",
        )
    if agents_used == 0 or not rows:
        return (
            "REWORK",
            "LIMITED",
            "REWORK: no upstream findings available to convert into actions.",
        )
    blocking = [o for o in open_items if o.get("blocks_decision")]
    quality = "PASS"
    if blocking:
        reliance = "BLOCKED"
        rationale = (
            f"PASS: {len(rows)} action(s) traced. Open blocker(s) present — "
            "decision cannot clear until resolved or protected."
        )
    elif open_items:
        reliance = "LIMITED"
        rationale = (
            f"PASS: {len(rows)} action(s) traced. Open items can be carried with protection."
        )
    else:
        reliance = "READY"
        rationale = f"PASS: {len(rows)} action(s) traced to upstream findings."
    return quality, reliance, rationale


def _heuristic_recommendation_spec(
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

    raw: list[dict[str, Any]] = []
    for slug, payload in agents.items():
        harvester = _HARVESTERS.get(slug)
        if not harvester:
            continue
        try:
            raw.extend(harvester(payload))
        except Exception:  # noqa: BLE001
            continue

    rows = _dedupe_actions([r for r in raw if r])
    buckets = _split_buckets(rows)
    flat = (
        buckets["price_adjustment"]
        + buckets["deal_structure"]
        + buckets["contractual_protection"]
        + buckets["condition_precedent"]
        + buckets["post_completion"]
    )
    open_items = _open_items(flat)
    quality, reliance, rationale = _quality_reliance(
        rows=flat, open_items=open_items, agents_used=len(agents)
    )

    val_payload = agents.get("valuation_modeling") or {}
    returns = _returns_from_valuation(_spec_of(val_payload))
    if not returns and isinstance(legacy.get("returns_by_scenario"), list):
        # Only keep legacy returns that are quantified and not the invented ladder
        returns = [
            r for r in legacy["returns_by_scenario"]
            if isinstance(r, dict)
            and (r.get("irr_pct") is not None or r.get("moic_x") is not None)
            and not _is_invented_return_row(r)
        ][:4]

    cps = buckets["condition_precedent"]
    posts = buckets["post_completion"]
    structures = buckets["deal_structure"]
    protections = buckets["contractual_protection"]
    prices = buckets["price_adjustment"]

    # Dual-write legacy string lists — every line still names its finding via agent tag
    legacy_cps = _legacy_cp_lines(cps)
    legacy_day100 = _legacy_day100(posts)
    deal_structure = _deal_structure_summary(structures, protections)

    # Carry IC go/no-go only as upstream reference — do not invent or soft-promote
    ic = _spec_of(agents.get("ic_synthesis"))
    upstream_go = ic.get("go_no_go") if ic else None

    blocking_n = sum(1 for o in open_items if o.get("blocks_decision"))
    bits = [
        f"Recommendations for {company}",
        f"{len(prices)} price",
        f"{len(structures)} structure",
        f"{len(protections)} protection",
        f"{len(cps)} CP",
        f"{len(legacy_day100)} day-100",
    ]
    if blocking_n:
        bits.append(f"{blocking_n} open blocker(s)")
    snapshot = _soften(". ".join(bits))

    srcs = list(sources or [])
    for slug, payload in agents.items():
        for s in (payload.get("sources") or [])[:2]:
            if isinstance(s, str) and s and s not in srcs:
                srcs.append(s)

    empty = not flat
    base_return = next(
        (r for r in returns if str(r.get("scenario") or "").lower().startswith("base")),
        returns[0] if returns else {},
    )

    return {
        "document": "Transaction Structure & Returns Summary",
        "fv_code": _FV_CODE,
        "slug": _AGENT_KEY,
        "insight_snapshot": snapshot,
        "sector": sector or _NA,
        "geography": geography or _NA,
        "synthesis_rules": {
            "classify": _CLASSIFY_RULE,
            "quantify": _QUANT_RULE,
            "conditions": _CP_RULE,
            "day100": _DAY100_RULE,
            "open": _OPEN_RULE,
            "trace": _TRACE_RULE,
        },
        "price_actions": prices,
        "structure_actions": structures,
        "protection_actions": protections,
        "conditions_precedent_structured": cps,
        "post_completion_actions": posts,
        "open_items": open_items,
        "recommendations": flat,
        # Legacy dual-write
        "deal_structure": deal_structure,
        "returns_by_scenario": returns,
        "conditions_precedent": legacy_cps,
        "hundred_day_plan": legacy_day100,
        "monitoring_metrics": legacy.get("monitoring_metrics") or [],
        "aligned_go_no_go": upstream_go,  # carry-only; not invented here
        "upstream_agents_used": sorted(agents.keys()),
        "primary_sources": srcs[:12],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "composer": "heuristic_recommendation_v1",
        "empty": empty,
        "metrics": {
            "base_irr_pct": base_return.get("irr_pct") if isinstance(base_return, dict) else None,
            "base_moic_x": base_return.get("moic_x") if isinstance(base_return, dict) else None,
            "cp_count": len(legacy_cps),
            "plan_items": len(legacy_day100),
            "price_count": len(prices),
            "protection_count": len(protections),
            "open_blocking": blocking_n,
            "go_no_go": upstream_go,
        },
    }


def _llm_recommendation_spec(
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
        "recommendation",
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
    src_lines = "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:12], start=1)) or "[1] (none)"
    user = (
        f"Company: {company}\n"
        f"Sector: {sector or 'unknown'}\n"
        f"Geography: {geography or 'unknown'}\n\n"
        "Upstream findings (only source of truth):\n"
        f"{prior_digest[:12000]}\n\n"
        f"Sources:\n{src_lines}\n\n"
        "Return JSON with keys: insight_snapshot, price_actions, structure_actions, "
        "protection_actions, conditions_precedent_structured, post_completion_actions, "
        "open_items, quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
        "Each action needs: action, action_class, source_finding, source_agent, "
        "quantified_effect, cannot_quantify_reason, bound_by, owner, acceptance_test, "
        "timing, blocks_decision, carry_with_protection.\n"
        "Delete any recommendation without a source_finding. No invest/pass."
    )
    try:
        return generate_json(system=system, user=user)
    except Exception:  # noqa: BLE001
        return None


def _normalise_llm_spec(raw: dict[str, Any], *, heur: dict[str, Any]) -> dict[str, Any]:
    out = dict(heur)
    if not isinstance(raw, dict):
        return out

    def _norm_actions(key: str, default_class: str) -> list[dict[str, Any]]:
        rows = raw.get(key) if isinstance(raw.get(key), list) else []
        cleaned: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            a = _action(
                action=str(row.get("action") or ""),
                action_class=str(row.get("action_class") or default_class),
                source_finding=str(row.get("source_finding") or ""),
                source_agent=str(row.get("source_agent") or ""),
                quantified_effect=str(row.get("quantified_effect") or "") or None,
                cannot_quantify_reason=str(row.get("cannot_quantify_reason") or "") or None,
                bound_by=str(row.get("bound_by") or "") or None,
                owner=str(row.get("owner") or "") or None,
                acceptance_test=str(row.get("acceptance_test") or "") or None,
                timing=str(row.get("timing") or "") or None,
                blocks_decision=bool(row.get("blocks_decision")),
                carry_with_protection=str(row.get("carry_with_protection") or "") or None,
            )
            if a:
                cleaned.append(a)
        return cleaned

    for key, default in (
        ("price_actions", "price_adjustment"),
        ("structure_actions", "deal_structure"),
        ("protection_actions", "contractual_protection"),
        ("conditions_precedent_structured", "condition_precedent"),
        ("post_completion_actions", "post_completion"),
    ):
        normalised = _norm_actions(key, default)
        if normalised:
            out[key] = normalised

    flat = (
        out.get("price_actions")
        + out.get("structure_actions")
        + out.get("protection_actions")
        + out.get("conditions_precedent_structured")
        + out.get("post_completion_actions")
    )
    out["recommendations"] = flat
    out["conditions_precedent"] = _legacy_cp_lines(out.get("conditions_precedent_structured") or [])
    out["hundred_day_plan"] = _legacy_day100(out.get("post_completion_actions") or [])
    out["deal_structure"] = _deal_structure_summary(
        out.get("structure_actions") or [],
        out.get("protection_actions") or [],
    )
    out["open_items"] = _open_items(flat)
    # Never invent go/no-go; keep heuristic carry
    out["aligned_go_no_go"] = heur.get("aligned_go_no_go")
    if raw.get("insight_snapshot"):
        out["insight_snapshot"] = _soften(_clean(raw["insight_snapshot"], 400))
    q, r, rationale = _quality_reliance(
        rows=flat,
        open_items=out.get("open_items") or [],
        agents_used=len(heur.get("upstream_agents_used") or []),
    )
    # Do not upgrade reliance vs heuristic
    order = {"BLOCKED": 0, "LIMITED": 1, "READY": 2}
    heur_r = str(heur.get("reliance_verdict") or "LIMITED")
    out["reliance_verdict"] = r if order.get(r, 9) <= order.get(heur_r, 9) else heur_r
    if heur.get("quality_verdict") == "REWORK":
        out["quality_verdict"] = "REWORK"
    else:
        out["quality_verdict"] = q
    out["quality_reliance_rationale"] = rationale
    out["composer"] = "llm_recommendation_v1"
    out["empty"] = not flat
    return out


def build_recommendation_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    prior: dict[str, dict] | None = None,
    findings_store: dict[str, Any] | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal

    _ = index
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography") or getattr(deal, "geography", None)
    sector = vars_.get("sector") or getattr(deal, "sector", None)
    if isinstance(sector, str) and sector.strip().lower() in {"generic", "unknown", ""}:
        sector = None

    agents = _collect_agents(deal, prior=prior, findings_store=findings_store)
    heur = _heuristic_recommendation_spec(
        company=target,
        prior_agents=agents,
        sources=list(sources or []),
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        legacy_spec=legacy_spec,
    )
    if prefer_heuristic:
        return heur

    digest_bits: list[str] = []
    for slug, payload in agents.items():
        spec = _spec_of(payload)
        digest_bits.append(f"## {slug}")
        if spec.get("insight_snapshot"):
            digest_bits.append(str(spec["insight_snapshot"])[:300])
        for f in (payload.get("findings") or [])[:4]:
            if isinstance(f, str):
                digest_bits.append(f"- {f[:200]}")
    llm_raw = _llm_recommendation_spec(
        company=target,
        prior_digest="\n".join(digest_bits),
        sources=list(sources or heur.get("primary_sources") or []),
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        materiality=vars_.get("materiality"),
    )
    if not llm_raw:
        return heur
    return _normalise_llm_spec(llm_raw, heur=heur)


def render_recommendation_markdown(
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
            if not isinstance(it, dict):
                parts.append(f"- {_clean(it, 220)}\n")
                continue
            parts.append(f"- **{_clean(it.get('action'), 200)}**\n")
            parts.append(
                f"  - Class: `{it.get('action_class')}` · Agent: `{it.get('source_agent')}`\n"
                f"  - Finding: {_clean(it.get('source_finding'), 200)}\n"
            )
            quant = it.get("quantified_effect") or _NA
            parts.append(f"  - Quantified effect: {_clean(quant, 120)}\n")
            if it.get("cannot_quantify_reason"):
                parts.append(
                    f"  - Not quantified yet: {_clean(it.get('cannot_quantify_reason'), 160)}\n"
                )
            if it.get("bound_by"):
                parts.append(f"  - Would be bounded by: {_clean(it.get('bound_by'), 160)}\n")
            if it.get("owner"):
                parts.append(f"  - Owner: {_clean(it.get('owner'), 80)}\n")
            if it.get("acceptance_test"):
                parts.append(f"  - Acceptance test: {_clean(it.get('acceptance_test'), 160)}\n")
            if it.get("timing"):
                parts.append(f"  - Timing: {_clean(it.get('timing'), 60)}\n")
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

    parts.extend(_section("1. Price Adjustments", spec.get("price_actions") or [], _CLASSIFY_RULE))
    parts.append("---\n\n")
    parts.extend(_section("2. Deal Structure", spec.get("structure_actions") or [], _QUANT_RULE))
    parts.append("---\n\n")
    parts.extend(
        _section(
            "3. Contractual Protections",
            spec.get("protection_actions") or [],
            "Price, structure and protection actions are kept separate.",
        )
    )
    parts.append("---\n\n")
    parts.extend(
        _section(
            "4. Conditions Precedent",
            spec.get("conditions_precedent_structured") or [],
            _CP_RULE,
        )
    )
    parts.append("---\n\n")
    parts.extend(
        _section(
            "5. First Hundred Days (Post-Completion)",
            spec.get("post_completion_actions") or [],
            _DAY100_RULE,
        )
    )
    parts.append("---\n\n")

    parts.append("## 6. Still Open\n\n")
    parts.append(f"{_OPEN_RULE}\n\n")
    open_items = spec.get("open_items") if isinstance(spec.get("open_items"), list) else []
    if not open_items:
        parts.append(f"_{_NA}_\n\n")
    else:
        for row in open_items:
            if not isinstance(row, dict):
                continue
            block = "BLOCKS DECISION" if row.get("blocks_decision") else "Can carry with protection"
            parts.append(
                f"- **{_clean(row.get('item'), 160)}** — {block}\n"
                f"  - Finding: {_clean(row.get('source_finding'), 160)} "
                f"(`{row.get('source_agent')}`)\n"
            )
            if row.get("carry_with_protection"):
                parts.append(
                    f"  - Protection: {_clean(row.get('carry_with_protection'), 160)}\n"
                )
        parts.append("\n")
    parts.append("---\n\n")

    if spec.get("returns_by_scenario"):
        parts.append("## Returns by Scenario (from valuation)\n\n")
        for row in spec["returns_by_scenario"]:
            if not isinstance(row, dict):
                continue
            parts.append(
                f"- **{_clean(row.get('scenario'), 40)}** — "
                f"IRR {row.get('irr_pct') if row.get('irr_pct') is not None else '—'}% · "
                f"MOIC {row.get('moic_x') if row.get('moic_x') is not None else '—'}x\n"
            )
        parts.append("\n---\n\n")

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
        "*This agent converts findings into actions. It does not issue an invest or pass recommendation.*\n\n"
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
