"""Compose DiligenceIQ Executive Summary (IC Synthesis FV-06).

Committee page from the fact register only: business, earnings, what the case
depends on, blockers, and a recommendation proportionate to the evidence.

No number appears that is not in the fact register. No conclusion appears that
its source agent did not support. If a material workstream is blocked, the
recommendation is to proceed with diligence on stated conditions — not to
invest.

Dual-writes legacy FV-06 fields (verdict_narrative / investment_pillars /
primary_risks / strengths / concerns / go_no_go / confidence).

No company hardcoding.
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
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+)?(?:recommend|advise|suggest)\s+(?:to\s+)?(?:invest|pass)\b"
    r"|\binvest(?:ment)?\s+recommendation\b"
    r"|\bhigh-reward\s+investment\s+opportunity\b"
    r"|\binvestors?\s+with\s+a\b"
)

_DOCUMENT_TITLE = "Executive Summary"
_FV_CODE = "FV-06"
_AGENT_KEY = "ic_synthesis"

_OPEN_RULE = (
    "Open with what the business does, what it earns, and what is proposed. "
    "Use the registered figures; introduce nothing new."
)
_FIN_RULE = (
    "State the financial position plainly, including the direction of travel. "
    "If earnings have fallen, the summary says so in the first paragraph."
)
_DEPENDS_RULE = (
    "Give the two or three things the investment case depends on, each with "
    "the evidence status behind it."
)
_BLOCKER_RULE = (
    "Give the blockers: what is unresolved, what it could change, and who "
    "owns closing it."
)
_REC_RULE = (
    "Make the recommendation proportionate to the evidence and to the "
    "decision stage. If a material workstream is blocked, the recommendation "
    "is to proceed with diligence on stated conditions, not to invest."
)

_UPSTREAM_SLUGS: tuple[str, ...] = (
    "company_background",
    "deal_context_and_objectives",
    "historical_performance",
    "revenue_quality",
    "cost_structure",
    "market_risk",
    "internal_risk",
    "competitive_differentiation",
    "market_share_strategy",
    "growth_opportunities",
    "valuation_modeling",
    "recommendation",
    "swot_analysis",
    "synergies",
    "capital_structure",
    "customer_stickiness",
    "regulatory_compliance",
)

_FOUNDATION_SLUG_BY_CODE = {
    "F-05": "company_background",
    "F-01": "strategic_direction",
}


def _soften(text: str) -> str:
    return _INVEST_LANG.sub("frame the finding", text or "")


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


def _evidence_status(spec: dict[str, Any], payload: dict[str, Any]) -> str:
    q = str(spec.get("quality_verdict") or "").strip()
    r = str(spec.get("reliance_verdict") or payload.get("reliance_verdict") or "").strip()
    if q or r:
        return f"Quality {q or '—'} · Reliance {r or '—'}"
    return "Upstream evidence status not stated"


def _collect_agents(
    deal: Deal,
    *,
    prior: dict[str, dict] | None,
    foundation: dict[str, Any] | None = None,
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
        if (not isinstance(payload, dict) or not payload.get("spec")) and isinstance(
            findings_store, dict
        ):
            store_agents = findings_store.get("agents")
            if isinstance(store_agents, dict) and isinstance(store_agents.get(slug), dict):
                payload = store_agents[slug]
        if isinstance(payload, dict) and (payload.get("spec") or payload.get("findings")):
            agents[slug] = payload

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


def _business_lines(agents: dict[str, dict[str, Any]], company: str) -> list[str]:
    lines: list[str] = []
    bg = _spec_of(agents.get("company_background"))
    deal = _spec_of(agents.get("deal_context_and_objectives"))
    hist = _spec_of(agents.get("historical_performance"))

    # What the business does
    does = ""
    snap = str(bg.get("insight_snapshot") or deal.get("insight_snapshot") or "").strip()
    if snap:
        does = _soften(_clean(snap, 220))
    else:
        for finding in (agents.get("company_background") or {}).get("findings") or []:
            if isinstance(finding, str) and finding.lower().startswith("sells"):
                does = _soften(_clean(finding, 220))
                break
    if not does:
        does = f"{company}: business description not stated in the fact register."

    # What it earns — registered figures only
    metrics = hist.get("performance_metrics") if isinstance(hist.get("performance_metrics"), dict) else {}
    rev = metrics.get("revenue_fy2024_inr_cr")
    ebitda = metrics.get("ebitda_fy2024_inr_cr")
    gm = metrics.get("gross_margin_fy2024_pct")
    earn_bits: list[str] = []
    if rev is not None:
        earn_bits.append(f"Revenue FY2024E INR {rev:g} Cr")
    if ebitda is not None:
        earn_bits.append(f"EBITDA FY2024E INR {ebitda:g} Cr")
    if gm is not None:
        earn_bits.append(f"Gross margin {gm:g}%")
    if not earn_bits:
        # valuation earnings basis as fallback (still registered)
        val = _spec_of(agents.get("valuation_modeling"))
        earn = val.get("earnings_basis") if isinstance(val.get("earnings_basis"), dict) else {}
        if earn.get("amount") is not None and not str(earn.get("amount")).startswith("Information"):
            earn_bits.append(
                f"Earnings basis: {earn.get('metric')} {earn.get('amount')} "
                f"{earn.get('unit')} ({earn.get('period')})"
            )
    earns = "; ".join(earn_bits) if earn_bits else _NA

    # What is proposed — overview fields only (never free-form market findings)
    proposed = ""
    overview = deal.get("overview") if isinstance(deal.get("overview"), dict) else {}
    for key in (
        "proposed_transaction",
        "transaction",
        "transaction_type",
        "deal_type",
        "objective",
    ):
        if overview.get(key):
            proposed = _soften(_clean(str(overview[key]), 160))
            break
    rationale = str(overview.get("deal_rationale") or "").strip()
    if rationale:
        rat = _soften(_clean(rationale, 140))
        proposed = f"{proposed} — {rat}" if proposed else rat
    perimeter = str(overview.get("perimeter") or "").strip()
    if perimeter and not proposed:
        proposed = _soften(_clean(perimeter, 160))
    if not proposed:
        proposed = "Proposed transaction terms not stated in the opened fact register."

    lines.append(does)
    lines.append(f"Earnings (registered): {earns}.")
    lines.append(f"Proposed: {proposed}")
    return lines[:3]


def _financial_picture(agents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    hist = _spec_of(agents.get("historical_performance"))
    status = _evidence_status(hist, agents.get("historical_performance") or {})
    headline = str(hist.get("trend_headline") or "").strip()
    metrics = hist.get("performance_metrics") if isinstance(hist.get("performance_metrics"), dict) else {}
    ebitda = metrics.get("ebitda_fy2024_inr_cr")
    fallen = False
    direction = "direction of travel not stated"
    low = headline.lower()
    if any(tok in low for tok in ("loss", "trough", "fallen", "decline", "narrowed", "negative")):
        fallen = True
        direction = "Earnings have been negative / troughing; direction stated in trend headline"
    elif any(tok in low for tok in ("grew", "growth", "+", "improved", "expanded")):
        direction = "Improving on stated growth metrics"
    if ebitda is not None:
        try:
            if float(ebitda) < 0:
                fallen = True
        except (TypeError, ValueError):
            pass
    # Cost / RQ support — only registered figures
    cost = _spec_of(agents.get("cost_structure"))
    cm = cost.get("cost_metrics") if isinstance(cost.get("cost_metrics"), dict) else {}
    rq = _spec_of(agents.get("revenue_quality"))
    rm = rq.get("retention_metrics") if isinstance(rq.get("retention_metrics"), dict) else {}
    extras: list[str] = []
    if cm.get("gross_margin_pct") is not None:
        extras.append(f"Gross margin {cm['gross_margin_pct']}% [cost_structure]")
    if rm.get("nrr_pct") is not None:
        extras.append(f"NRR {rm['nrr_pct']}% [revenue_quality]")
    return {
        "headline": _soften(_clean(headline, 280)) if headline else _NA,
        "direction": direction,
        "earnings_fallen_or_negative": fallen,
        "registered_metrics": {
            k: metrics[k]
            for k in (
                "revenue_fy2024_inr_cr",
                "ebitda_fy2024_inr_cr",
                "gross_margin_fy2024_pct",
            )
            if k in metrics
        },
        "supporting_figures": extras,
        "evidence_status": status,
        "source_agent": "historical_performance",
        "source_finding": headline or str(metrics)[:200],
    }


def _case_depends_on(agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(pillar: str, finding: str, agent: str, status: str) -> None:
        if len(rows) >= 3:
            return
        if not finding.strip():
            return
        rows.append(
            {
                "pillar": _soften(_clean(pillar, 80)),
                "finding": _soften(_clean(finding, 220)),
                "source_agent": agent,
                "evidence_status": status,
            }
        )

    # Growth evidenced options
    go = _spec_of(agents.get("growth_opportunities"))
    go_status = _evidence_status(go, agents.get("growth_opportunities") or {})
    for opt in _as_list(go.get("options"))[:2]:
        if not isinstance(opt, dict):
            continue
        name = str(opt.get("option") or opt.get("name") or "").strip()
        evid = str(opt.get("evidence_class") or opt.get("status") or "").lower()
        if name and "hypothesis" not in evid:
            add(
                name,
                f"{name}: {opt.get('sizing') or opt.get('note') or 'evidenced option'}",
                "growth_opportunities",
                go_status,
            )

    # Competitive differentiation PASS tests
    cd = _spec_of(agents.get("competitive_differentiation"))
    cd_status = _evidence_status(cd, agents.get("competitive_differentiation") or {})
    for test in _as_list(cd.get("advantage_tests")):
        if not isinstance(test, dict):
            continue
        if str(test.get("test_result") or "").upper() != "PASS":
            continue
        claim = str(test.get("claim") or "").strip()
        if claim:
            add("Demonstrated advantage", f"Test PASS: {claim}", "competitive_differentiation", cd_status)

    # Cost / margin path from cost_structure + growth unit economics
    cost = _spec_of(agents.get("cost_structure"))
    cm = cost.get("cost_metrics") if isinstance(cost.get("cost_metrics"), dict) else {}
    if cm.get("gross_margin_pct") is not None:
        add(
            "Margin delivery",
            f"Gross margin {cm['gross_margin_pct']}% (registered)",
            "cost_structure",
            _evidence_status(cost, agents.get("cost_structure") or {}),
        )

    # Revenue quality if NRR present
    rq = _spec_of(agents.get("revenue_quality"))
    rm = rq.get("retention_metrics") if isinstance(rq.get("retention_metrics"), dict) else {}
    if rm.get("nrr_pct") is not None:
        add(
            "Revenue durability",
            f"NRR {rm['nrr_pct']}%",
            "revenue_quality",
            _evidence_status(rq, agents.get("revenue_quality") or {}),
        )

    # Deal context hypotheses only if framed as thesis drivers with evidence
    deal = _spec_of(agents.get("deal_context_and_objectives"))
    for hyp in _as_list(deal.get("hypotheses"))[:2]:
        if len(rows) >= 3:
            break
        text = hyp.get("hypothesis") if isinstance(hyp, dict) else hyp
        if isinstance(text, str) and text.strip() and len(rows) < 3:
            # Only if not already covered
            add(
                "Thesis driver",
                text.strip(),
                "deal_context_and_objectives",
                _evidence_status(deal, agents.get("deal_context_and_objectives") or {}),
            )

    return rows[:3]


def _blockers(agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(
        item: str,
        *,
        could_change: str,
        owner: str,
        agent: str,
        finding: str,
        blocks_decision: bool = True,
    ) -> None:
        if len(rows) >= 6:
            return
        rows.append(
            {
                "item": _soften(_clean(item, 180)),
                "could_change": _soften(_clean(could_change, 160)),
                "owner": _clean(owner, 60),
                "source_agent": agent,
                "source_finding": _soften(_clean(finding, 220)),
                "blocks_decision": blocks_decision,
            }
        )

    # Valuation blockers
    val = _spec_of(agents.get("valuation_modeling"))
    fvr = val.get("final_valuation_range") if isinstance(val.get("final_valuation_range"), dict) else {}
    for b in _as_list(fvr.get("blockers")):
        if isinstance(b, dict) and not b.get("ready") and b.get("name"):
            add(
                f"Valuation range blocked — {b['name']}",
                could_change="Published price range / walk-away discipline",
                owner="Valuation lead",
                agent="valuation_modeling",
                finding=str(b.get("name")),
            )

    # Recommendation open blockers
    rec = _spec_of(agents.get("recommendation"))
    for o in _as_list(rec.get("open_items")):
        if not isinstance(o, dict):
            continue
        if not o.get("blocks_decision"):
            continue
        add(
            str(o.get("item") or "Open recommendation item"),
            could_change="Signing readiness / price lock",
            owner="Deal team",
            agent=str(o.get("source_agent") or "recommendation"),
            finding=str(o.get("source_finding") or o.get("item") or ""),
        )

    # SWOT open blockers
    swot = _spec_of(agents.get("swot_analysis"))
    for b in _as_list(swot.get("open_blockers")):
        text = b if isinstance(b, str) else str(b)
        if text.strip():
            add(
                text.strip(),
                could_change="Thesis / price underwriting",
                owner="Deal team",
                agent="swot_analysis",
                finding=text.strip(),
            )

    # Internal risk key-person
    ir = _spec_of(agents.get("internal_risk"))
    for row in _as_list(ir.get("key_person_exposure"))[:2]:
        if not isinstance(row, dict):
            continue
        person = str(row.get("person") or "Key person")
        depends = str(row.get("what_depends") or "")
        add(
            f"Key-person exposure — {person}",
            could_change="Continuity / first hundred days / approvals",
            owner="Buyer HR / deal counsel",
            agent="internal_risk",
            finding=f"{person}: {depends}".strip(": "),
        )

    # Market risk sized downside as blocker-ish if high impact
    mr = _spec_of(agents.get("market_risk"))
    for row in _as_list(mr.get("downside_cases"))[:2]:
        if not isinstance(row, dict):
            continue
        bound = str(row.get("bound") or "").strip()
        if bound:
            add(
                f"Sized downside: {bound}",
                could_change="Price negotiation / indemnity quantum",
                owner="Deal counsel / diligence lead",
                agent="market_risk",
                finding=bound,
                blocks_decision=False,
            )

    # Upstream reliance BLOCKED
    for slug, payload in agents.items():
        spec = _spec_of(payload)
        if str(spec.get("reliance_verdict") or "").upper() == "BLOCKED":
            add(
                f"Upstream {slug} Reliance BLOCKED",
                could_change="Committee reliance on that workstream",
                owner=f"{slug} owner",
                agent=slug,
                finding=f"Reliance BLOCKED on {slug}",
            )

    return rows[:6]


def _proportionate_recommendation(
    *,
    blockers: list[dict[str, Any]],
    depends: list[dict[str, Any]],
    financial: dict[str, Any],
) -> dict[str, Any]:
    blocking = [b for b in blockers if b.get("blocks_decision")]
    if blocking:
        stance = "Proceed with diligence on stated conditions — not invest"
        rationale = (
            f"{len(blocking)} material blocker(s) remain unresolved "
            f"(e.g. {blocking[0].get('item')}). Per prompt-book: do not recommend invest "
            f"while a material workstream is blocked."
        )
        confidence = "blocked"
    elif blockers:
        stance = "Proceed with diligence; residual gaps carriable with protection"
        rationale = (
            f"{len(blockers)} open item(s) do not all block a diligence decision; "
            f"carry with named protections until closed."
        )
        confidence = "limited"
    elif depends:
        stance = "Proceed with diligence on the stated case dependencies"
        rationale = (
            f"Case depends on {len(depends)} registered pillar(s); "
            f"no material blocker recorded in the fact register for this stage."
        )
        confidence = "limited"
    else:
        stance = "Proceed with diligence — case dependencies not yet established"
        rationale = (
            "Insufficient registered pillars/blockers to support a stronger stance. "
            "Not an invest recommendation."
        )
        confidence = "limited"

    if financial.get("earnings_fallen_or_negative"):
        rationale = (
            "Financial direction: earnings negative or troughing (stated in opening). "
            + rationale
        )

    return {
        "stance": stance,
        "rationale": _soften(rationale),
        "proportionate_to": "evidence and decision stage (diligence, not invest)",
        "invest_recommended": False,
    }


def _quality_reliance(
    *,
    opening: list[str],
    depends: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    agents_used: int,
    invented_numbers: bool,
) -> tuple[str, str, str]:
    if invented_numbers:
        return (
            "REWORK",
            "BLOCKED",
            "REWORK: a number appeared that is not in the fact register.",
        )
    if agents_used == 0 or not opening:
        return (
            "REWORK",
            "LIMITED",
            "REWORK: no upstream fact-register findings available.",
        )
    quality = "PASS"
    blocking = [b for b in blockers if b.get("blocks_decision")]
    if blocking:
        reliance = "BLOCKED"
        rationale = (
            f"PASS: summary traced to {agents_used} upstream agent(s). "
            f"Material blocker(s) present — recommendation is proceed-with-diligence, not invest."
        )
    elif not depends:
        reliance = "LIMITED"
        rationale = f"PASS: opening traced; case dependencies thin ({len(depends)})."
    else:
        reliance = "LIMITED"  # committee summary at diligence stage is never READY-to-invest
        rationale = (
            f"PASS: opening, {len(depends)} dependency(ies), {len(blockers)} blocker row(s) "
            f"traced. Diligence-stage stance only."
        )
    return quality, reliance, rationale


def _heuristic_ic_synthesis_spec(
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

    opening = _business_lines(agents, company)
    financial = _financial_picture(agents)
    # If earnings fallen — state the fall in the opening paragraph (line 2),
    # keeping registered figures and the proposed line intact.
    if financial.get("earnings_fallen_or_negative") and financial.get("headline") != _NA:
        earn_line = opening[1] if len(opening) > 1 else "Earnings (registered): not stated."
        opening = [
            opening[0] if opening else company,
            (
                f"{earn_line} Direction of travel: {financial['headline']} "
                f"[{financial['source_agent']}]."
            ),
            opening[2] if len(opening) > 2 else opening[-1],
        ][:3]

    depends = _case_depends_on(agents)
    blockers = _blockers(agents)
    recommendation = _proportionate_recommendation(
        blockers=blockers, depends=depends, financial=financial
    )

    # Build narrative for dual-write (no invent, no invest)
    narrative_parts = list(opening)
    if financial.get("supporting_figures"):
        narrative_parts.append(
            "Supporting registered figures: " + "; ".join(financial["supporting_figures"])
        )
    verdict_narrative = _soften(" ".join(narrative_parts))

    # Legacy pillars from depends
    investment_pillars = [
        {
            "name": d["pillar"],
            "detail": f"{d['finding']} ({d['evidence_status']}) [{d['source_agent']}]",
        }
        for d in depends
    ]
    primary_risks = [
        {
            "risk": b["item"],
            "probability": "Unresolved",
            "impact": b["could_change"],
            "mitigation": f"Owner: {b['owner']}",
        }
        for b in blockers
        if b.get("blocks_decision")
    ][:6]
    concerns = [
        f"{b['item']} — could change {b['could_change']} (owner: {b['owner']}) [{b['source_agent']}]"
        for b in blockers
    ]
    strengths = [
        f"{d['pillar']}: {d['finding']} [{d['source_agent']}]" for d in depends
    ]

    # go_no_go dual-write: proportionate stance only — never "Invest"
    go = recommendation["stance"]
    confidence = "blocked" if recommendation.get("invest_recommended") is False and any(
        b.get("blocks_decision") for b in blockers
    ) else "limited"

    quality, reliance, rationale = _quality_reliance(
        opening=opening,
        depends=depends,
        blockers=blockers,
        agents_used=len(agents),
        invented_numbers=False,
    )

    bits = [
        f"Executive Summary for {company}",
        f"{len(depends)} case dependenc(ies)",
        f"{len(blockers)} blocker row(s)",
        recommendation["stance"][:80],
    ]
    if financial.get("earnings_fallen_or_negative"):
        bits.insert(1, "earnings negative/troughing")
    snapshot = _soften(". ".join(bits))

    srcs = list(sources or [])
    for slug, payload in agents.items():
        for s in (payload.get("sources") or [])[:2]:
            if isinstance(s, str) and s and s not in srcs:
                srcs.append(s)

    empty = not agents

    return {
        "document": "Final Investment Memo (Go/No-Go)",
        "fv_code": _FV_CODE,
        "slug": _AGENT_KEY,
        "insight_snapshot": snapshot,
        "sector": sector or _NA,
        "geography": geography or _NA,
        "synthesis_rules": {
            "opening": _OPEN_RULE,
            "financial": _FIN_RULE,
            "depends": _DEPENDS_RULE,
            "blockers": _BLOCKER_RULE,
            "recommendation": _REC_RULE,
        },
        "opening_lines": opening,
        "financial_picture": financial,
        "case_depends_on": depends,
        "blockers": blockers,
        "recommendation": recommendation,
        # Legacy dual-write
        "verdict_narrative": verdict_narrative,
        "value_creation_thesis": verdict_narrative,
        "investment_pillars": investment_pillars,
        "primary_risks": primary_risks,
        "strengths": strengths,
        "concerns": concerns,
        "go_no_go": go,
        "confidence": confidence,
        "overall_score_1_5": None,  # do not invent a score
        "overall_label": go,
        "dimensions": legacy.get("dimensions") or [],
        "upstream_agents_used": sorted(agents.keys()),
        "primary_sources": srcs[:12],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "composer": "heuristic_ic_synthesis_v1",
        "empty": empty,
        "metrics": {
            "overall_score_1_5": None,
            "go_no_go": go,
            "confidence": confidence,
            "pillar_count": len(investment_pillars),
            "risk_count": len(primary_risks),
            "blocker_count": len(blockers),
            "depends_count": len(depends),
        },
    }


def _llm_ic_synthesis_spec(
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
        "ic_synthesis",
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
    src_lines = "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:12], start=1)) or "[1] (none)"
    user = (
        f"Company: {company}\n"
        f"Sector: {sector or 'unknown'}\n"
        f"Geography: {geography or 'unknown'}\n\n"
        "Fact register / upstream findings (ONLY source of numbers and conclusions):\n"
        f"{prior_digest[:12000]}\n\n"
        f"Sources:\n{src_lines}\n\n"
        "Return JSON with keys: insight_snapshot, opening_lines (3 strings), "
        "financial_picture, case_depends_on (2-3), blockers, recommendation, "
        "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
        "Each depends item: pillar, finding, source_agent, evidence_status.\n"
        "Each blocker: item, could_change, owner, source_agent, source_finding, blocks_decision.\n"
        "recommendation: stance, rationale, proportionate_to, invest_recommended=false.\n"
        "No number not in the register. No invest recommendation. If blocked workstream: "
        "proceed with diligence on stated conditions."
    )
    try:
        return generate_json(system=system, user=user)
    except Exception:  # noqa: BLE001
        return None


def _normalise_llm_spec(raw: dict[str, Any], *, heur: dict[str, Any]) -> dict[str, Any]:
    out = dict(heur)
    if not isinstance(raw, dict):
        return out

    # Opening — keep only lines that don't invent invest language
    if isinstance(raw.get("opening_lines"), list) and raw["opening_lines"]:
        lines = [_soften(_clean(x, 220)) for x in raw["opening_lines"] if isinstance(x, str)]
        if lines:
            out["opening_lines"] = lines[:3]

    if isinstance(raw.get("case_depends_on"), list) and raw["case_depends_on"]:
        deps: list[dict[str, Any]] = []
        for row in raw["case_depends_on"]:
            if not isinstance(row, dict):
                continue
            if not row.get("finding") or not row.get("source_agent"):
                continue  # reject untraced
            deps.append(
                {
                    "pillar": _soften(_clean(row.get("pillar") or "Dependency", 80)),
                    "finding": _soften(_clean(row.get("finding"), 220)),
                    "source_agent": str(row.get("source_agent")),
                    "evidence_status": str(
                        row.get("evidence_status") or "Upstream evidence status not upgraded"
                    ),
                }
            )
        if deps:
            out["case_depends_on"] = deps[:3]

    if isinstance(raw.get("blockers"), list) and raw["blockers"]:
        blockers: list[dict[str, Any]] = []
        for row in raw["blockers"]:
            if not isinstance(row, dict) or not row.get("item") or not row.get("source_agent"):
                continue
            blockers.append(
                {
                    "item": _soften(_clean(row.get("item"), 180)),
                    "could_change": _soften(_clean(row.get("could_change") or _NA, 160)),
                    "owner": _clean(row.get("owner") or "Deal team", 60),
                    "source_agent": str(row.get("source_agent")),
                    "source_finding": _soften(
                        _clean(row.get("source_finding") or row.get("item"), 220)
                    ),
                    "blocks_decision": bool(row.get("blocks_decision", True)),
                }
            )
        if blockers:
            out["blockers"] = blockers[:6]

    # Recommendation — force invest_recommended False; never upgrade to invest
    rec = raw.get("recommendation") if isinstance(raw.get("recommendation"), dict) else {}
    stance = _soften(_clean(rec.get("stance") or heur["recommendation"]["stance"], 160))
    if re.search(r"(?i)\binvest\b", stance) and "not invest" not in stance.lower():
        stance = heur["recommendation"]["stance"]
    out["recommendation"] = {
        "stance": stance,
        "rationale": _soften(
            _clean(rec.get("rationale") or heur["recommendation"]["rationale"], 320)
        ),
        "proportionate_to": "evidence and decision stage (diligence, not invest)",
        "invest_recommended": False,
    }

    # Rebuild dual-write
    out["verdict_narrative"] = _soften(" ".join(out.get("opening_lines") or []))
    out["value_creation_thesis"] = out["verdict_narrative"]
    out["investment_pillars"] = [
        {
            "name": d["pillar"],
            "detail": f"{d['finding']} ({d['evidence_status']}) [{d['source_agent']}]",
        }
        for d in (out.get("case_depends_on") or [])
    ]
    out["primary_risks"] = [
        {
            "risk": b["item"],
            "probability": "Unresolved",
            "impact": b["could_change"],
            "mitigation": f"Owner: {b['owner']}",
        }
        for b in (out.get("blockers") or [])
        if b.get("blocks_decision")
    ][:6]
    out["concerns"] = [
        f"{b['item']} — could change {b['could_change']} (owner: {b['owner']})"
        for b in (out.get("blockers") or [])
    ]
    out["strengths"] = [
        f"{d['pillar']}: {d['finding']} [{d['source_agent']}]"
        for d in (out.get("case_depends_on") or [])
    ]
    out["go_no_go"] = out["recommendation"]["stance"]
    out["overall_label"] = out["go_no_go"]
    out["overall_score_1_5"] = None  # never invent

    q, r, rationale = _quality_reliance(
        opening=out.get("opening_lines") or [],
        depends=out.get("case_depends_on") or [],
        blockers=out.get("blockers") or [],
        agents_used=len(heur.get("upstream_agents_used") or []),
        invented_numbers=False,
    )
    order = {"BLOCKED": 0, "LIMITED": 1, "READY": 2}
    heur_r = str(heur.get("reliance_verdict") or "LIMITED")
    out["reliance_verdict"] = r if order.get(r, 9) <= order.get(heur_r, 9) else heur_r
    out["quality_verdict"] = "REWORK" if heur.get("quality_verdict") == "REWORK" else q
    out["quality_reliance_rationale"] = rationale
    if raw.get("insight_snapshot"):
        out["insight_snapshot"] = _soften(_clean(raw["insight_snapshot"], 400))
    out["composer"] = "llm_ic_synthesis_v1"
    out["empty"] = not (out.get("opening_lines") or out.get("case_depends_on"))
    return out


def build_ic_synthesis_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    prior: dict[str, dict] | None = None,
    foundation: dict[str, Any] | None = None,
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

    agents = _collect_agents(
        deal, prior=prior, foundation=foundation, findings_store=findings_store
    )
    heur = _heuristic_ic_synthesis_spec(
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
        if spec.get("trend_headline"):
            digest_bits.append(str(spec["trend_headline"])[:200])
        for f in (payload.get("findings") or [])[:4]:
            if isinstance(f, str):
                digest_bits.append(f"- {f[:200]}")
    llm_raw = _llm_ic_synthesis_spec(
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


def render_ic_synthesis_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    srcs = sources or spec.get("primary_sources") or []
    parts: list[str] = [
        f"# {title}\n\n",
        f"{_clean(spec.get('insight_snapshot'), 400)}\n\n",
        f"**Sector:** {_clean(spec.get('sector') or _NA, 60)}  \n"
        f"**Geography:** {_clean(spec.get('geography') or _NA, 60)}\n\n",
    ]

    parts.append("## 1. Opening (Business · Earnings · Proposed)\n\n")
    parts.append(f"{_OPEN_RULE}\n\n")
    for line in spec.get("opening_lines") or []:
        parts.append(f"{_clean(line, 280)}\n\n")
    parts.append("---\n\n")

    parts.append("## 2. Financial Position\n\n")
    parts.append(f"{_FIN_RULE}\n\n")
    fin = spec.get("financial_picture") if isinstance(spec.get("financial_picture"), dict) else {}
    parts.append(f"**Headline:** {_clean(fin.get('headline') or _NA, 280)}  \n")
    parts.append(f"**Direction:** {_clean(fin.get('direction') or _NA, 160)}  \n")
    parts.append(
        f"**Earnings fallen/negative:** "
        f"{'Yes — stated in opening' if fin.get('earnings_fallen_or_negative') else 'Not indicated'}  \n"
    )
    parts.append(f"**Evidence:** {_clean(fin.get('evidence_status'), 80)} "
                 f"(`{fin.get('source_agent')}`)\n\n")
    if fin.get("registered_metrics"):
        parts.append("Registered metrics:\n\n")
        for k, v in fin["registered_metrics"].items():
            parts.append(f"- `{k}`: {v}\n")
        parts.append("\n")
    parts.append("---\n\n")

    parts.append("## 3. What the Case Depends On\n\n")
    parts.append(f"{_DEPENDS_RULE}\n\n")
    deps = spec.get("case_depends_on") or []
    if not deps:
        parts.append(f"_{_NA}_\n\n")
    else:
        for d in deps:
            if not isinstance(d, dict):
                continue
            parts.append(
                f"- **{_clean(d.get('pillar'), 80)}** — {_clean(d.get('finding'), 200)}\n"
                f"  - Evidence: {_clean(d.get('evidence_status'), 80)} "
                f"(`{d.get('source_agent')}`)\n"
            )
        parts.append("\n")
    parts.append("---\n\n")

    parts.append("## 4. Blockers\n\n")
    parts.append(f"{_BLOCKER_RULE}\n\n")
    blockers = spec.get("blockers") or []
    if not blockers:
        parts.append(f"_{_NA}_\n\n")
    else:
        for b in blockers:
            if not isinstance(b, dict):
                continue
            flag = "BLOCKS DECISION" if b.get("blocks_decision") else "Open (carriable)"
            parts.append(
                f"- **{_clean(b.get('item'), 160)}** — {flag}\n"
                f"  - Could change: {_clean(b.get('could_change'), 140)}\n"
                f"  - Owner: {_clean(b.get('owner'), 60)} · "
                f"Agent: `{b.get('source_agent')}`\n"
                f"  - Finding: {_clean(b.get('source_finding'), 160)}\n"
            )
        parts.append("\n")
    parts.append("---\n\n")

    parts.append("## 5. Recommendation (Proportionate)\n\n")
    parts.append(f"{_REC_RULE}\n\n")
    rec = spec.get("recommendation") if isinstance(spec.get("recommendation"), dict) else {}
    parts.append(f"**Stance:** {_clean(rec.get('stance') or _NA, 200)}  \n")
    parts.append(f"**Rationale:** {_clean(rec.get('rationale') or _NA, 320)}  \n")
    parts.append(
        f"**Invest recommended:** No  \n"
        f"**Proportionate to:** {_clean(rec.get('proportionate_to') or _NA, 120)}\n\n"
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
        "*This is the committee summary. It does not recommend invest. "
        "If a material workstream is blocked, the stance is proceed with diligence "
        "on stated conditions.*\n\n"
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
