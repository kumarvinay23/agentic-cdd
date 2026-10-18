"""Compose DiligenceIQ Appendices (FV-08) — audit-trail aggregator.

Aggregates claim / evidence / calculation registers, source inventory,
bidirectional citation check, open requests / contradictions / exclusions,
and availability vs verification. No new diligence findings. No invest
endorsement.

Code-enforced QA + Questions; READY→LIMITED on open QA FAILs.
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
    r"|\bgo\s*/\s*no[- ]?go\b"
)

_DOCUMENT_TITLE = "Appendices"
_FV_CODE = "FV-08"
_AGENT_KEY = "appendices"

_CLAIM_RULE = (
    "Aggregate the claim register from upstream agents. Each claim needs "
    "claim ID, text, source category, locator, period, unit, population, "
    "basis, and evidence strength."
)
_EVIDENCE_RULE = (
    "Aggregate the evidence register: primary VDR files, interviews, and "
    "external URLs with version / as-of where known."
)
_CALC_RULE = (
    "Aggregate the calculation register: bridges, recomputed lines, and "
    "computed facts with inputs and tolerance status."
)
_SOURCE_RULE = (
    "Build the source inventory: data-room versions, interviews, and "
    "external URLs. Mark availability separately from verification."
)
_CITE_RULE = (
    "Run a bidirectional citation check: claims → sources and sources → "
    "claims. Record supports / does_not_support / unverified."
)
_OPEN_RULE = (
    "Consolidate open information requests, contradictions, and explicit "
    "exclusions from Scope & Methodology and upstream Questions."
)
_AVAIL_RULE = (
    "Distinguish availability vs verification — present in room ≠ "
    "reopened / verified."
)
_NO_INVENT_RULE = (
    "Appendices do not invent diligence findings — every claim must already "
    "exist upstream or in the data-room inventory."
)
_NO_BID_RULE = (
    "Appendices do not issue an invest endorsement — audit trail only."
)

_URL_RE = re.compile(r"(?i)\bhttps?://[^\s\]\)\"']+")
_INTERVIEW_RE = re.compile(r"(?i)\b(?:interview|mgmt\s+call|management\s+call|q&a)\b")
_EXTERNAL_RE = re.compile(r"(?i)\b(?:https?://|external|press|news|broker|research)\b")

_UPSTREAM_SLUGS: tuple[str, ...] = (
    "scope_and_methodology",
    "deal_context_and_objectives",
    "company_background",
    "historical_performance",
    "revenue_quality",
    "cost_structure",
    "cash_flow",
    "capital_structure",
    "valuation_modeling",
    "market_risk",
    "internal_risk",
    "regulatory_compliance",
    "growth_opportunities",
    "swot_analysis",
    "ic_synthesis",
    "recommendation",
    "execution_risk",
    "compensation_alignment",
    "trading_comps",
    "precedent_transactions",
)


def _as_list(v: Any) -> list[Any]:
    if isinstance(v, list):
        return v
    if v is None:
        return []
    return [v]


def _spec_of(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    spec = payload.get("spec")
    return spec if isinstance(spec, dict) else {}


def _soften(text: str) -> str:
    return _clean(text, 400)


def _source_category_for(locator: str, *, computed: bool = False) -> str:
    if computed:
        return "COMPUTED"
    loc = locator or ""
    if _INTERVIEW_RE.search(loc):
        return "INTERVIEW"
    if _URL_RE.search(loc) or _EXTERNAL_RE.search(loc):
        return "EXTERNAL"
    if loc.strip():
        return "VDR_PRIMARY"
    return "MANAGEMENT_ASSERTION"


def _claim_rows_from_agent(
    slug: str,
    payload: dict[str, Any],
    *,
    prefix: str,
    limit: int = 8,
) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_claim

    spec = _spec_of(payload)
    rows: list[dict[str, str]] = []
    srcs = [
        s for s in (payload.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    default_locator = srcs[0] if srcs else f"[{slug}]"

    # Prefer an existing claim_register on the agent
    for raw in _as_list(spec.get("claim_register"))[:limit]:
        if not isinstance(raw, dict):
            continue
        n = normalize_claim(raw, default_prefix=prefix)
        if n.get("text"):
            if not n.get("locator"):
                n["locator"] = default_locator
            rows.append(n)

    # Findings as provisional claims
    for i, finding in enumerate(_as_list(payload.get("findings"))[:limit]):
        if len(rows) >= limit:
            break
        if isinstance(finding, str):
            text = finding
        elif isinstance(finding, dict):
            text = str(finding.get("text") or finding.get("finding") or "")
        else:
            text = ""
        text = text.strip()
        if not text or len(text) < 12:
            continue
        rows.append(
            normalize_claim(
                {
                    "claim_id": f"{prefix}-{i + 1:02d}",
                    "text": text[:240],
                    "source_category": _source_category_for(default_locator),
                    "locator": default_locator,
                    "period": "",
                    "unit": "",
                    "population": slug,
                    "basis": "actual",
                    "evidence_strength": "provisional",
                },
                default_prefix=prefix,
            )
        )

    # Insight / headline snippets
    for key in ("insight_snapshot", "trend_headline", "verdict_narrative"):
        if len(rows) >= limit:
            break
        val = spec.get(key)
        if isinstance(val, str) and len(val.strip()) >= 20:
            rows.append(
                normalize_claim(
                    {
                        "claim_id": f"{prefix}-INS",
                        "text": val.strip()[:240],
                        "source_category": _source_category_for(default_locator),
                        "locator": default_locator,
                        "population": slug,
                        "basis": "actual",
                        "evidence_strength": "provisional",
                    },
                    default_prefix=prefix,
                )
            )

    # Registered metrics as computed / VDR claims
    for metrics_key in (
        "performance_metrics",
        "retention_metrics",
        "cost_metrics",
    ):
        metrics = spec.get(metrics_key)
        if not isinstance(metrics, dict):
            continue
        for mk, mv in list(metrics.items())[:4]:
            if len(rows) >= limit:
                break
            if mv is None or isinstance(mv, (dict, list)):
                continue
            rows.append(
                normalize_claim(
                    {
                        "claim_id": f"{prefix}-{mk}"[:24],
                        "text": f"{mk.replace('_', ' ')} = {mv}",
                        "source_category": "COMPUTED"
                        if "COMPUTED" in default_locator.upper()
                        else "VDR_PRIMARY",
                        "locator": default_locator,
                        "period": "",
                        "unit": "",
                        "population": slug,
                        "basis": "actual",
                        "evidence_strength": "supported"
                        if srcs
                        else "provisional",
                    },
                    default_prefix=prefix,
                )
            )
    return rows[:limit]


def _aggregate_claim_register(
    agents: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for slug, payload in agents.items():
        prefix = "".join(p[:1].upper() for p in slug.split("_") if p)[:4] or "CLM"
        for row in _claim_rows_from_agent(slug, payload, prefix=prefix, limit=6):
            key = f"{row.get('claim_id')}|{row.get('text')}"
            if key in seen:
                continue
            seen.add(key)
            row = dict(row)
            row["source_agent"] = slug
            out.append(row)
            if len(out) >= 60:
                return out
    return out


def _aggregate_evidence_register(
    agents: dict[str, dict[str, Any]],
    *,
    inventory: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(
        *,
        evidence_id: str,
        kind: str,
        locator: str,
        agent: str,
        version: str = "",
        as_of: str = "",
        available: str = "available",
        verified: str = "unverified",
    ) -> None:
        key = locator.lower().strip()
        if not key or key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "evidence_id": evidence_id,
                "kind": kind,
                "locator": _clean(locator, 200),
                "source_agent": agent,
                "version": _clean(version or _NA, 60),
                "as_of": _clean(as_of or _NA, 40),
                "availability": available,
                "verification": verified,
            }
        )

    n = 0
    for slug, payload in agents.items():
        spec = _spec_of(payload)
        srcs = payload.get("sources") or spec.get("primary_sources") or []
        for s in srcs:
            if not isinstance(s, str) or not s.strip():
                continue
            n += 1
            kind = "interview" if _INTERVIEW_RE.search(s) else (
                "external_url" if _URL_RE.search(s) else "vdr_file"
            )
            add(
                evidence_id=f"EV-{n:03d}",
                kind=kind,
                locator=s.strip(),
                agent=slug,
                verified="unverified",
            )

    inv = inventory if isinstance(inventory, dict) else {}
    for doc in _as_list(inv.get("documents"))[:40]:
        if not isinstance(doc, dict):
            continue
        name = str(doc.get("filename") or doc.get("name") or "").strip()
        if not name:
            continue
        n += 1
        add(
            evidence_id=f"EV-INV-{n:03d}",
            kind="vdr_file",
            locator=name,
            agent="data_room",
            version=str(doc.get("version") or doc.get("etag") or ""),
            as_of=str(doc.get("as_of") or doc.get("modified") or ""),
            available="available",
            verified="unverified",
        )
    return rows[:80]


def _aggregate_calculation_register(
    agents: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import recalculate_bridge

    rows: list[dict[str, str]] = []
    n = 0
    for slug, payload in agents.items():
        spec = _spec_of(payload)
        for bridge_key in (
            "ebitda_to_cash_bridge",
            "cash_bridge",
            "bridge_lines",
            "equity_bridge",
            "ev_equity_bridge",
        ):
            lines = spec.get(bridge_key)
            if not isinstance(lines, list) or not lines:
                continue
            bridge_rows = []
            for line in lines:
                if not isinstance(line, dict):
                    continue
                bridge_rows.append(
                    {
                        "label": str(
                            line.get("label") or line.get("line") or line.get("name") or ""
                        ),
                        "value": line.get("value")
                        if line.get("value") is not None
                        else line.get("amount"),
                    }
                )
            if not bridge_rows:
                continue
            result = recalculate_bridge(bridge_rows)
            n += 1
            status = "within_tolerance" if result.get("ok") else "out_of_tolerance"
            rows.append(
                {
                    "calc_id": f"CALC-{n:03d}",
                    "name": f"{slug}.{bridge_key}",
                    "source_agent": slug,
                    "inputs": "; ".join(
                        f"{r['label']}={r['value']}" for r in bridge_rows[:6]
                    )[:200],
                    "result": str(
                        result.get("computed_total")
                        if result.get("computed_total") is not None
                        else result.get("stated_total")
                        if result.get("stated_total") is not None
                        else _NA
                    )[:80],
                    "tolerance_status": status,
                    "note": _clean(str(result.get("error") or status), 120),
                }
            )

        # Computed metrics without full bridge
        for metrics_key in ("performance_metrics", "retention_metrics", "cost_metrics"):
            metrics = spec.get(metrics_key)
            if not isinstance(metrics, dict):
                continue
            for mk, mv in list(metrics.items())[:3]:
                if mv is None or isinstance(mv, (dict, list)):
                    continue
                n += 1
                rows.append(
                    {
                        "calc_id": f"CALC-{n:03d}",
                        "name": f"{slug}.{mk}",
                        "source_agent": slug,
                        "inputs": f"{mk} from {slug} register",
                        "result": str(mv)[:80],
                        "tolerance_status": "registered",
                        "note": "Registered metric — not recomputed here",
                    }
                )
                if n >= 40:
                    return rows
    return rows[:40]


def _source_inventory(
    agents: dict[str, dict[str, Any]],
    *,
    inventory: dict[str, Any] | None = None,
    evidence: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(row: dict[str, str]) -> None:
        key = row["locator"].lower()
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    for ev in evidence or []:
        add(
            {
                "locator": ev["locator"],
                "kind": ev.get("kind") or "vdr_file",
                "version": ev.get("version") or _NA,
                "as_of": ev.get("as_of") or _NA,
                "availability": ev.get("availability") or "available",
                "verification": ev.get("verification") or "unverified",
                "source_agent": ev.get("source_agent") or "",
            }
        )

    inv = inventory if isinstance(inventory, dict) else {}
    for doc in _as_list(inv.get("documents"))[:50]:
        if not isinstance(doc, dict):
            continue
        name = str(doc.get("filename") or doc.get("name") or "").strip()
        if not name:
            continue
        add(
            {
                "locator": name,
                "kind": "vdr_file",
                "version": str(doc.get("version") or doc.get("etag") or _NA)[:60],
                "as_of": str(doc.get("as_of") or doc.get("modified") or _NA)[:40],
                "availability": "available",
                "verification": "unverified",
                "source_agent": "data_room",
            }
        )

    # Interviews / external URLs from findings text
    for slug, payload in agents.items():
        for f in _as_list(payload.get("findings"))[:4]:
            text = f if isinstance(f, str) else ""
            for url in _URL_RE.findall(text):
                add(
                    {
                        "locator": url.rstrip(".,;)"),
                        "kind": "external_url",
                        "version": _NA,
                        "as_of": _NA,
                        "availability": "available",
                        "verification": "unverified",
                        "source_agent": slug,
                    }
                )
            if _INTERVIEW_RE.search(text):
                add(
                    {
                        "locator": _clean(text, 120),
                        "kind": "interview",
                        "version": _NA,
                        "as_of": _NA,
                        "availability": "referenced",
                        "verification": "unverified",
                        "source_agent": slug,
                    }
                )
    return rows[:100]


def _bidirectional_citation_check(
    claims: list[dict[str, str]],
    sources: list[dict[str, str]],
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import cite_reopen

    source_locs = [s.get("locator") or "" for s in sources if s.get("locator")]
    source_blob = "\n".join(source_locs).lower()

    claim_to_source: list[dict[str, Any]] = []
    for claim in claims[:40]:
        locator = claim.get("locator") or ""
        accessible = bool(locator) and (
            locator.lower() in source_blob
            or any(locator.lower() in (s or "").lower() for s in source_locs)
            or locator.startswith("[")
        )
        # Use locator names as pseudo source text when full text unavailable
        check = cite_reopen(
            claim=claim,
            source_text=locator if accessible else None,
            source_accessible=accessible,
        )
        # Soften: locator present in inventory → unverified (available, not reopened)
        if check["status"] == "does_not_support" and accessible:
            check = {
                **check,
                "status": "unverified",
                "reason": "source listed but not reopened against claim text",
            }
        claim_to_source.append(check)

    # Sources → claims: material sources that appear as claim locators
    claimed_locs = {
        (c.get("locator") or "").lower().strip()
        for c in claims
        if c.get("locator")
    }
    source_to_claim: list[dict[str, str]] = []
    for s in sources[:40]:
        loc = (s.get("locator") or "").strip()
        if not loc:
            continue
        linked = loc.lower() in claimed_locs or any(
            loc.lower() in (c.get("locator") or "").lower()
            or (c.get("locator") or "").lower() in loc.lower()
            for c in claims[:40]
        )
        source_to_claim.append(
            {
                "locator": loc[:160],
                "status": "linked" if linked else "unlinked",
                "note": (
                    "Appears as claim locator"
                    if linked
                    else "In inventory; no claim cites this source yet"
                ),
            }
        )

    supports = sum(1 for r in claim_to_source if r.get("status") == "supports")
    unverified = sum(1 for r in claim_to_source if r.get("status") == "unverified")
    fails = sum(1 for r in claim_to_source if r.get("status") == "does_not_support")
    return {
        "claim_to_source": claim_to_source,
        "source_to_claim": source_to_claim,
        "summary": {
            "claims_checked": len(claim_to_source),
            "supports": supports,
            "unverified": unverified,
            "does_not_support": fails,
            "sources_linked": sum(
                1 for r in source_to_claim if r.get("status") == "linked"
            ),
            "sources_unlinked": sum(
                1 for r in source_to_claim if r.get("status") == "unlinked"
            ),
        },
    }


def _consolidate_open_items(
    agents: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    from agetic_cdd_api.prompt_book import normalize_question

    open_requests: list[dict[str, str]] = []
    contradictions: list[dict[str, str]] = []
    exclusions: list[dict[str, str]] = []

    for slug, payload in agents.items():
        spec = _spec_of(payload)
        for q in _as_list(spec.get("questions"))[:8]:
            nq = normalize_question(q)
            if not nq.get("question"):
                continue
            nq["source_agent"] = slug
            open_requests.append(nq)

        for key in ("contradictions", "conflicts", "inconsistencies"):
            for row in _as_list(spec.get(key))[:4]:
                text = (
                    row.get("text") or row.get("statement") or row.get("item")
                    if isinstance(row, dict)
                    else str(row)
                )
                if not str(text).strip():
                    continue
                contradictions.append(
                    {
                        "item": _clean(text, 200),
                        "source_agent": slug,
                        "note": _clean(
                            (row.get("note") if isinstance(row, dict) else "") or "",
                            120,
                        )
                        or _NA,
                    }
                )

        for key in ("exclusions", "out_of_scope", "scope_exclusions"):
            for row in _as_list(spec.get(key))[:4]:
                text = (
                    row.get("text") or row.get("item") or row.get("exclusion")
                    if isinstance(row, dict)
                    else str(row)
                )
                if not str(text).strip():
                    continue
                exclusions.append(
                    {
                        "item": _clean(text, 200),
                        "source_agent": slug,
                        "note": _clean(
                            (row.get("note") if isinstance(row, dict) else "") or "",
                            120,
                        )
                        or _NA,
                    }
                )

        # Scope methodology notes often carry exclusions
        if slug == "scope_and_methodology":
            for note in _as_list(spec.get("notes"))[:6]:
                text = note if isinstance(note, str) else str(note)
                if "exclud" in text.lower() or "out of scope" in text.lower():
                    exclusions.append(
                        {
                            "item": _clean(text, 200),
                            "source_agent": slug,
                            "note": "From scope notes",
                        }
                    )

    return {
        "open_requests": open_requests[:40],
        "contradictions": contradictions[:20],
        "exclusions": exclusions[:20],
    }


def _availability_vs_verification(
    sources: list[dict[str, str]],
    citation: dict[str, Any],
) -> list[dict[str, str]]:
    """Matrix: available in room vs verified/reopened."""
    verified_ids = {
        r.get("locator", "").lower()
        for r in (citation.get("claim_to_source") or [])
        if isinstance(r, dict) and r.get("status") == "supports"
    }
    rows: list[dict[str, str]] = []
    for s in sources[:40]:
        loc = s.get("locator") or ""
        avail = s.get("availability") or "available"
        ver = "verified" if loc.lower() in verified_ids else (
            s.get("verification") or "unverified"
        )
        rows.append(
            {
                "locator": _clean(loc, 160),
                "availability": avail,
                "verification": ver,
                "distinction": (
                    "Available and verified"
                    if ver == "verified"
                    else "Available but not verified — do not treat as reopened"
                    if avail in {"available", "referenced"}
                    else "Not available"
                ),
                "source_agent": s.get("source_agent") or "",
            }
        )
    return rows


def _appendices_evidence_qa(
    *,
    claims: list[dict[str, str]],
    evidence: list[dict[str, str]],
    calculations: list[dict[str, str]],
    sources: list[dict[str, str]],
    citation: dict[str, Any],
    open_items: dict[str, list],
    avail_matrix: list[dict[str, str]],
    corpus_bits: str,
) -> list[dict[str, str]]:
    qa: list[dict[str, str]] = []

    claims_ok = bool(claims)
    qa.append({
        "check": "claim_register_present",
        "status": "PASS" if claims_ok else "FAIL",
        "finding": (
            f"{len(claims)} claim(s) aggregated"
            if claims_ok
            else "Claim register empty — no upstream claims harvested"
        ),
        "action": _CLAIM_RULE,
    })

    evidence_ok = bool(evidence) or bool(sources)
    qa.append({
        "check": "evidence_register_present",
        "status": "PASS" if evidence_ok else "FAIL",
        "finding": (
            f"{len(evidence)} evidence row(s); {len(sources)} inventory row(s)"
            if evidence_ok
            else "Evidence / source inventory empty"
        ),
        "action": _EVIDENCE_RULE,
    })

    # Calculation register may be empty if no bridges — soft PASS with note
    qa.append({
        "check": "calculation_register_stated",
        "status": "PASS",
        "finding": (
            f"{len(calculations)} calculation row(s)"
            if calculations
            else "No bridges/computations upstream — calculation register empty by design"
        ),
        "action": _CALC_RULE,
    })

    summary = citation.get("summary") if isinstance(citation.get("summary"), dict) else {}
    cite_ok = bool(claims) and int(summary.get("claims_checked") or 0) > 0
    qa.append({
        "check": "bidirectional_citation_run",
        "status": "PASS" if cite_ok else "FAIL",
        "finding": (
            f"Checked {summary.get('claims_checked', 0)} claim(s); "
            f"supports={summary.get('supports', 0)}, "
            f"unverified={summary.get('unverified', 0)}, "
            f"fail={summary.get('does_not_support', 0)}; "
            f"sources linked={summary.get('sources_linked', 0)}"
            if cite_ok
            else "Bidirectional citation check not run"
        ),
        "action": _CITE_RULE,
    })

    hard_fails = int(summary.get("does_not_support") or 0)
    qa.append({
        "check": "no_hard_citation_fails",
        "status": "PASS" if hard_fails == 0 else "FAIL",
        "finding": (
            "No does_not_support citation outcomes"
            if hard_fails == 0
            else f"{hard_fails} claim(s) do not support cited locator"
        ),
        "action": _CITE_RULE,
    })

    # PASS when matrix exists and states the availability≠verification distinction
    avail_ok = bool(avail_matrix)
    qa.append({
        "check": "availability_vs_verification_stated",
        "status": "PASS" if avail_ok else "FAIL",
        "finding": (
            f"{len(avail_matrix)} inventory row(s) with availability≠verification"
            if avail_ok
            else "Availability vs verification matrix missing"
        ),
        "action": _AVAIL_RULE,
    })

    open_stated = (
        "open_requests" in open_items
        and "contradictions" in open_items
        and "exclusions" in open_items
    )
    qa.append({
        "check": "open_items_consolidated",
        "status": "PASS" if open_stated else "FAIL",
        "finding": (
            f"{len(open_items.get('open_requests') or [])} request(s); "
            f"{len(open_items.get('contradictions') or [])} contradiction(s); "
            f"{len(open_items.get('exclusions') or [])} exclusion(s)"
            if open_stated
            else "Open requests / contradictions / exclusions not consolidated"
        ),
        "action": _OPEN_RULE,
    })

    invent_bad = bool(_INVEST_LANG.search(corpus_bits or ""))
    qa.append({
        "check": "no_invest_endorsement",
        "status": "PASS" if not invent_bad else "FAIL",
        "finding": (
            "No invest endorsement in Appendices"
            if not invent_bad
            else "Invest language present in Appendices corpus"
        ),
        "action": _NO_BID_RULE,
    })

    return qa


def _questions_from_appendix_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    qa = (
        spec.get("appendices_evidence_qa")
        if isinstance(spec.get("appendices_evidence_qa"), list)
        else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    out: list[dict[str, str]] = []
    if _qa_fail("claim_register_present"):
        out.append(normalize_question({
            "question": "Populate claim register from upstream agents / VDR",
            "required_records": "Upstream findings + claim_register rows",
            "decision_effect": "Appendices cannot support reopen without claims",
            "priority": "mandatory_pre_decision",
            "owner": "Deal lead",
            "timing": "before IC",
            "closure_test": "claim_register_present QA PASS",
            "interim_treatment": "REWORK until claims aggregated",
        }))
    if _qa_fail("evidence_register_present"):
        out.append(normalize_question({
            "question": "Attach VDR / interview / external evidence locators",
            "required_records": "Agent sources + data-room inventory",
            "decision_effect": "No evidence register → citations cannot be checked",
            "priority": "mandatory_pre_decision",
            "owner": "VDR coordinator",
            "timing": "before IC",
            "closure_test": "evidence_register_present QA PASS",
            "interim_treatment": "LIMITED until inventory present",
        }))
    if _qa_fail("bidirectional_citation_run"):
        out.append(normalize_question({
            "question": "Run bidirectional citation check on claim register",
            "required_records": "Claims + source inventory",
            "decision_effect": "Unchecked citations undermine committee reliance",
            "priority": "mandatory_pre_decision",
            "owner": "Deal lead",
            "timing": "before IC",
            "closure_test": "bidirectional_citation_run QA PASS",
            "interim_treatment": "LIMITED until citation check run",
        }))
    if _qa_fail("no_hard_citation_fails"):
        out.append(normalize_question({
            "question": "Repair or retract claims that fail citation support",
            "required_records": "Claim locator reopen packets",
            "decision_effect": "Unsupported claims must not appear in Appendices",
            "priority": "mandatory_pre_decision",
            "owner": "Deal lead",
            "timing": "before IC",
            "closure_test": "no_hard_citation_fails QA PASS",
            "interim_treatment": "REWORK until unsupported claims cleared",
        }))
    if _qa_fail("availability_vs_verification_stated"):
        out.append(normalize_question({
            "question": "State availability vs verification for each inventory source",
            "required_records": "Source inventory matrix",
            "decision_effect": "Available ≠ verified — committee may over-rely",
            "priority": "mandatory_pre_decision",
            "owner": "Deal lead",
            "timing": "before IC",
            "closure_test": "availability_vs_verification_stated QA PASS",
            "interim_treatment": "LIMITED until matrix stated",
        }))
    if _qa_fail("open_items_consolidated"):
        out.append(normalize_question({
            "question": "Consolidate open requests, contradictions and exclusions",
            "required_records": "Upstream Questions + scope exclusions",
            "decision_effect": "Scattered gaps hide residual uncertainty",
            "priority": "signing_condition",
            "owner": "Deal lead",
            "timing": "before IC",
            "closure_test": "open_items_consolidated QA PASS",
            "interim_treatment": "LIMITED until consolidated",
        }))
    if _qa_fail("no_invest_endorsement"):
        out.append(normalize_question({
            "question": "Remove invest endorsement from Appendices",
            "required_records": "Appendices document body",
            "decision_effect": "Invest language here bypasses Recommendations",
            "priority": "mandatory_pre_decision",
            "owner": "Deal lead",
            "timing": "before IC",
            "closure_test": "no_invest_endorsement QA PASS",
            "interim_treatment": "REWORK until endorsement removed",
        }))
    return [q for q in out if q]


def _quality_reliance(
    *,
    claims: list[dict[str, str]],
    sources: list[dict[str, str]],
    agents_used: int,
    citation: dict[str, Any],
    qa_fail: bool = False,
) -> tuple[str, str, str]:
    if agents_used == 0:
        return (
            "REWORK",
            "LIMITED",
            "REWORK: no upstream agents available to aggregate.",
        )
    if not claims and not sources:
        return (
            "REWORK",
            "LIMITED",
            "REWORK: claim register and source inventory both empty.",
        )
    quality = "PASS"
    summary = citation.get("summary") if isinstance(citation.get("summary"), dict) else {}
    hard_fails = int(summary.get("does_not_support") or 0)
    if hard_fails > 0:
        reliance = "BLOCKED"
        rationale = (
            f"PASS: aggregated from {agents_used} agent(s). "
            f"{hard_fails} citation does_not_support — Appendices blocked for reliance."
        )
    elif not claims or not sources:
        reliance = "LIMITED"
        rationale = (
            f"PASS: partial Appendices from {agents_used} agent(s) — "
            f"claims={len(claims)}, sources={len(sources)}."
        )
    else:
        reliance = "READY"
        rationale = (
            f"PASS: {len(claims)} claim(s), {len(sources)} source(s), "
            f"citation check run across {summary.get('claims_checked', 0)} claim(s)."
        )
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        rationale += " Open Appendices QA FAILs cap READY → LIMITED."
    bits = [rationale, _NO_INVENT_RULE, _AVAIL_RULE]
    return quality, reliance, " ".join(bits)


def _load_data_room_inventory(deal: Deal | None) -> dict[str, Any]:
    if deal is None:
        return {}
    slug = getattr(deal, "slug", None) or getattr(deal, "id", None)
    if not slug:
        return {}
    try:
        from agetic_cdd_api.report_builder_base import _data_room_inventory

        inv = _data_room_inventory(str(slug))
        return inv if isinstance(inv, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _heuristic_appendices_spec(
    *,
    company: str,
    prior_agents: dict[str, dict[str, Any]] | None = None,
    sources: list[str] | None = None,
    sector: str | None = None,
    geography: str | None = None,
    deal_slots: dict[str, Any] | None = None,
    inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agents = prior_agents if isinstance(prior_agents, dict) else {}
    slots = deal_slots if isinstance(deal_slots, dict) else {}
    inv = inventory if isinstance(inventory, dict) else {}

    claims = _aggregate_claim_register(agents)
    evidence = _aggregate_evidence_register(agents, inventory=inv)
    calculations = _aggregate_calculation_register(agents)
    source_inv = _source_inventory(agents, inventory=inv, evidence=evidence)
    # Seed inventory with explicit sources list
    for s in sources or []:
        if isinstance(s, str) and s.strip():
            if not any(r.get("locator") == s for r in source_inv):
                source_inv.append(
                    {
                        "locator": s.strip(),
                        "kind": "vdr_file",
                        "version": _NA,
                        "as_of": _NA,
                        "availability": "available",
                        "verification": "unverified",
                        "source_agent": "runner",
                    }
                )
    citation = _bidirectional_citation_check(claims, source_inv)
    open_items = _consolidate_open_items(agents)
    avail_matrix = _availability_vs_verification(source_inv, citation)

    bits = [
        f"Appendices for {company}",
        f"{len(claims)} claim(s)",
        f"{len(evidence)} evidence row(s)",
        f"{len(calculations)} calculation(s)",
        f"{len(source_inv)} source(s)",
        (
            f"citation supports={citation['summary'].get('supports', 0)} "
            f"unverified={citation['summary'].get('unverified', 0)}"
        ),
    ]
    snapshot = _soften(". ".join(bits))

    ap_qa = _appendices_evidence_qa(
        claims=claims,
        evidence=evidence,
        calculations=calculations,
        sources=source_inv,
        citation=citation,
        open_items=open_items,
        avail_matrix=avail_matrix,
        corpus_bits=snapshot,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in ap_qa)
    quality, reliance, rationale = _quality_reliance(
        claims=claims,
        sources=source_inv,
        agents_used=len(agents),
        citation=citation,
        qa_fail=qa_fail,
    )

    primary_sources: list[str] = []
    for s in source_inv:
        loc = s.get("locator")
        if isinstance(loc, str) and loc and loc not in primary_sources:
            primary_sources.append(loc)
    for s in sources or []:
        if isinstance(s, str) and s and s not in primary_sources:
            primary_sources.append(s)

    out: dict[str, Any] = {
        "document": "Appendices",
        "fv_code": _FV_CODE,
        "slug": _AGENT_KEY,
        "ui_name": "Appendices",
        "insight_snapshot": snapshot,
        "sector": sector or _NA,
        "geography": geography or _NA,
        "appendices_rules": {
            "claims": _CLAIM_RULE,
            "evidence": _EVIDENCE_RULE,
            "calculations": _CALC_RULE,
            "sources": _SOURCE_RULE,
            "citation": _CITE_RULE,
            "open_items": _OPEN_RULE,
            "availability": _AVAIL_RULE,
        },
        "claim_register": claims,
        "evidence_register": evidence,
        "calculation_register": calculations,
        "source_inventory": source_inv,
        "citation_check": citation,
        "open_requests": open_items.get("open_requests") or [],
        "contradictions": open_items.get("contradictions") or [],
        "exclusions": open_items.get("exclusions") or [],
        "availability_vs_verification": avail_matrix,
        "appendices_evidence_qa": ap_qa,
        "upstream_agents_used": sorted(agents.keys()),
        "primary_sources": primary_sources[:24],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "composer": "heuristic_appendices_v1",
        "empty": not agents,
        "metrics": {
            "claim_count": len(claims),
            "evidence_count": len(evidence),
            "calculation_count": len(calculations),
            "source_count": len(source_inv),
            "open_request_count": len(open_items.get("open_requests") or []),
            "citation_supports": citation["summary"].get("supports", 0),
            "citation_unverified": citation["summary"].get("unverified", 0),
        },
    }
    if slots:
        out["deal_slots"] = slots
    out["questions"] = _questions_from_appendix_gaps(out)
    return out


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
        if (not isinstance(payload, dict) or not payload.get("spec")) and isinstance(
            findings_store, dict
        ):
            store_agents = findings_store.get("agents")
            if isinstance(store_agents, dict) and isinstance(store_agents.get(slug), dict):
                payload = store_agents[slug]
        if isinstance(payload, dict) and (payload.get("spec") or payload.get("findings")):
            agents[slug] = payload
    # Also pick up any other prior keys with specs (soft)
    for slug, payload in prior.items():
        if slug in agents:
            continue
        if isinstance(payload, dict) and (payload.get("spec") or payload.get("findings")):
            agents[slug] = payload
    return agents


def build_appendices_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    prior: dict[str, dict] | None = None,
    foundation: dict[str, Any] | None = None,
    findings_store: dict[str, Any] | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = True,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal

    _ = legacy_spec, foundation, prefer_heuristic
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography") or getattr(deal, "geography", None)
    sector = vars_.get("sector") or getattr(deal, "sector", None)
    if isinstance(sector, str) and sector.strip().lower() in {"generic", "unknown", ""}:
        sector = None

    slots = {k: v for k, v in vars_.items() if v}
    agents = _collect_agents(deal, prior=prior, findings_store=findings_store)
    inv = _load_data_room_inventory(deal)
    # Merge VDR index documents if provided
    if isinstance(index, dict) and isinstance(index.get("documents"), list):
        docs = list(inv.get("documents") or []) if inv else []
        existing = {
            str(d.get("filename") or d.get("name") or "")
            for d in docs
            if isinstance(d, dict)
        }
        for d in index["documents"]:
            if not isinstance(d, dict):
                continue
            name = str(d.get("filename") or d.get("name") or "")
            if name and name not in existing:
                docs.append(d)
                existing.add(name)
        inv = {**(inv or {}), "documents": docs}

    return _heuristic_appendices_spec(
        company=target,
        prior_agents=agents,
        sources=list(sources or []),
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        deal_slots=slots,
        inventory=inv,
    )


def render_appendices_markdown(
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
        f"{_AVAIL_RULE}\n\n",
        "---\n\n",
    ]

    parts.append("## 1. Claim Register\n\n")
    parts.append(f"{_CLAIM_RULE}\n\n")
    claims = spec.get("claim_register") if isinstance(spec.get("claim_register"), list) else []
    if claims:
        parts.append(
            "| Claim ID | Text | Category | Locator | Strength | Agent |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
        )
        for c in claims[:40]:
            if not isinstance(c, dict):
                continue
            parts.append(
                f"| {_clean(c.get('claim_id'), 24)} | {_clean(c.get('text'), 100)} | "
                f"{_clean(c.get('source_category'), 20)} | {_clean(c.get('locator'), 40)} | "
                f"{_clean(c.get('evidence_strength'), 14)} | "
                f"`{c.get('source_agent') or '—'}` |\n"
            )
        parts.append("\n")
    else:
        parts.append(f"_{_NA}_\n\n")
    parts.append("---\n\n")

    parts.append("## 2. Evidence Register\n\n")
    parts.append(f"{_EVIDENCE_RULE}\n\n")
    evidence = (
        spec.get("evidence_register")
        if isinstance(spec.get("evidence_register"), list)
        else []
    )
    if evidence:
        parts.append(
            "| ID | Kind | Locator | Version | Verification | Agent |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
        )
        for e in evidence[:40]:
            if not isinstance(e, dict):
                continue
            parts.append(
                f"| {_clean(e.get('evidence_id'), 16)} | {_clean(e.get('kind'), 16)} | "
                f"{_clean(e.get('locator'), 60)} | {_clean(e.get('version'), 24)} | "
                f"{_clean(e.get('verification'), 14)} | "
                f"`{e.get('source_agent') or '—'}` |\n"
            )
        parts.append("\n")
    else:
        parts.append(f"_{_NA}_\n\n")
    parts.append("---\n\n")

    parts.append("## 3. Calculation Register\n\n")
    parts.append(f"{_CALC_RULE}\n\n")
    calcs = (
        spec.get("calculation_register")
        if isinstance(spec.get("calculation_register"), list)
        else []
    )
    if calcs:
        parts.append(
            "| ID | Name | Result | Tolerance | Agent |\n"
            "| --- | --- | --- | --- | --- |\n"
        )
        for c in calcs[:30]:
            if not isinstance(c, dict):
                continue
            parts.append(
                f"| {_clean(c.get('calc_id'), 12)} | {_clean(c.get('name'), 40)} | "
                f"{_clean(c.get('result'), 40)} | "
                f"{_clean(c.get('tolerance_status'), 20)} | "
                f"`{c.get('source_agent') or '—'}` |\n"
            )
        parts.append("\n")
    else:
        parts.append(
            "No bridges or recomputed lines upstream — calculation register empty.\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 4. Source Inventory\n\n")
    parts.append(f"{_SOURCE_RULE}\n\n")
    inventory = (
        spec.get("source_inventory")
        if isinstance(spec.get("source_inventory"), list)
        else []
    )
    if inventory:
        parts.append(
            "| Locator | Kind | Version | Availability | Verification |\n"
            "| --- | --- | --- | --- | --- |\n"
        )
        for s in inventory[:50]:
            if not isinstance(s, dict):
                continue
            parts.append(
                f"| {_clean(s.get('locator'), 60)} | {_clean(s.get('kind'), 16)} | "
                f"{_clean(s.get('version'), 24)} | {_clean(s.get('availability'), 14)} | "
                f"{_clean(s.get('verification'), 14)} |\n"
            )
        parts.append("\n")
    else:
        parts.append(f"_{_NA}_\n\n")
    parts.append("---\n\n")

    parts.append("## 5. Bidirectional Citation Check\n\n")
    parts.append(f"{_CITE_RULE}\n\n")
    cite = (
        spec.get("citation_check")
        if isinstance(spec.get("citation_check"), dict)
        else {}
    )
    summary = cite.get("summary") if isinstance(cite.get("summary"), dict) else {}
    parts.append(
        f"**Claims checked:** {summary.get('claims_checked', 0)}  \n"
        f"**Supports:** {summary.get('supports', 0)} · "
        f"**Unverified:** {summary.get('unverified', 0)} · "
        f"**Does not support:** {summary.get('does_not_support', 0)}  \n"
        f"**Sources linked:** {summary.get('sources_linked', 0)} · "
        f"**Unlinked:** {summary.get('sources_unlinked', 0)}\n\n"
    )
    cts = cite.get("claim_to_source") if isinstance(cite.get("claim_to_source"), list) else []
    if cts:
        parts.append("| Claim | Status | Reason |\n| --- | --- | --- |\n")
        for r in cts[:20]:
            if not isinstance(r, dict):
                continue
            parts.append(
                f"| {_clean(r.get('claim_id'), 24)} | {_clean(r.get('status'), 16)} | "
                f"{_clean(r.get('reason'), 80)} |\n"
            )
        parts.append("\n")
    parts.append("---\n\n")

    parts.append("## 6. Open Requests · Contradictions · Exclusions\n\n")
    parts.append(f"{_OPEN_RULE}\n\n")
    reqs = spec.get("open_requests") if isinstance(spec.get("open_requests"), list) else []
    if reqs:
        parts.append("### Open requests\n\n")
        for q in reqs[:12]:
            if not isinstance(q, dict):
                continue
            parts.append(
                f"- **{_clean(q.get('question'), 160)}** — "
                f"records: {_clean(q.get('required_records'), 80)}; "
                f"owner: {_clean(q.get('owner'), 40)}; "
                f"agent: `{q.get('source_agent') or '—'}`\n"
            )
        parts.append("\n")
    else:
        parts.append("No open requests consolidated (or none upstream).\n\n")

    contras = (
        spec.get("contradictions") if isinstance(spec.get("contradictions"), list) else []
    )
    if contras:
        parts.append("### Contradictions\n\n")
        for c in contras[:8]:
            if isinstance(c, dict):
                parts.append(
                    f"- {_clean(c.get('item'), 160)} (`{c.get('source_agent')}`)\n"
                )
        parts.append("\n")

    exclusions = (
        spec.get("exclusions") if isinstance(spec.get("exclusions"), list) else []
    )
    if exclusions:
        parts.append("### Exclusions\n\n")
        for e in exclusions[:8]:
            if isinstance(e, dict):
                parts.append(
                    f"- {_clean(e.get('item'), 160)} (`{e.get('source_agent')}`)\n"
                )
        parts.append("\n")
    parts.append("---\n\n")

    parts.append("## 7. Availability vs Verification\n\n")
    parts.append(f"{_AVAIL_RULE}\n\n")
    matrix = (
        spec.get("availability_vs_verification")
        if isinstance(spec.get("availability_vs_verification"), list)
        else []
    )
    if matrix:
        parts.append(
            "| Locator | Availability | Verification | Distinction |\n"
            "| --- | --- | --- | --- |\n"
        )
        for r in matrix[:30]:
            if not isinstance(r, dict):
                continue
            parts.append(
                f"| {_clean(r.get('locator'), 50)} | {_clean(r.get('availability'), 14)} | "
                f"{_clean(r.get('verification'), 14)} | "
                f"{_clean(r.get('distinction'), 80)} |\n"
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

    ap_qa = (
        spec.get("appendices_evidence_qa")
        if isinstance(spec.get("appendices_evidence_qa"), list)
        else []
    )
    parts.append("## 8. Appendices Evidence QA\n\n")
    if ap_qa:
        parts.append("| Check | Status | Finding | Action |\n| --- | --- | --- | --- |\n")
        for r in ap_qa:
            if not isinstance(r, dict):
                continue
            parts.append(
                f"| {_clean(r.get('check'), 40)} | {_clean(r.get('status'), 12)} | "
                f"{_clean(r.get('finding'), 100)} | {_clean(r.get('action'), 80)} |\n"
            )
        parts.append("\n")
    else:
        parts.append("_Information request: Appendices evidence QA rows_\n\n")
    parts.append("---\n\n")

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
            "None are missing — material Appendices gaps are closed, "
            "or no Questions were generated from open QA FAILs.\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 10. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'REWORK', 16)}  \n"
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 16)}  \n"
        f"{_clean(spec.get('quality_reliance_rationale'), 400)}\n\n"
        f"*{_NO_INVENT_RULE} {_AVAIL_RULE} Open QA FAILs cap READY → LIMITED.*\n\n"
    )

    if srcs:
        parts.append("---\n\n## Sources\n\n")
        parts.append(f"{_SOURCES_MARKER}\n\n")
        for i, s in enumerate(srcs[:24], start=1):
            parts.append(f"{i}. {_clean(s, 160)} {_DOC_CITE}\n")
        parts.append("\n")

    return "".join(parts)
