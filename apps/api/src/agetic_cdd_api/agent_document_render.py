"""Render agent output JSON into DiligenceIQ-style markdown documents."""

from __future__ import annotations

import re
from typing import Any


_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"


def _clean(text: Any, max_chars: int = 600) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip()).replace("\x7f", " ")
    if len(t) > max_chars:
        t = t[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return t


def _agent_title(output: dict[str, Any], agent_key: str) -> str:
    name = output.get("agentName") or agent_key.replace("_", " ").title()
    return str(name)


def _insight_block(text: str) -> str:
    body = _clean(text, 420)
    if not body:
        return ""
    return f"> **Insight Snapshot:** {body}\n\n"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
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
            clean_cell = str(val or "—").replace("|", "\\|").replace("\n", " ").strip()
            cells.append(clean_cell)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _findings_bullets(findings: Any, *, limit: int = 12) -> str:
    if not isinstance(findings, list) or not findings:
        return ""
    lines: list[str] = []
    for item in findings[:limit]:
        if isinstance(item, dict):
            text = item.get("finding") or item.get("note") or item.get("name") or item.get("risk")
            if text:
                lines.append(f"- {_clean(text, 320)}")
        elif item is not None and str(item).strip():
            lines.append(f"- {_clean(str(item), 320)}")
    return ("\n".join(lines) + "\n\n") if lines else ""


def _sources_section(sources: Any) -> str:
    lines = ["## Sources\n", f"{_SOURCES_MARKER}\n"]
    if isinstance(sources, list):
        for i, src in enumerate(sources[:40], start=1):
            if isinstance(src, str) and src.strip():
                lines.append(f"**[{i}]** {src.strip()}")
            elif isinstance(src, dict):
                title = src.get("title") or src.get("name") or src.get("file") or "Source"
                lines.append(f"**[{i}]** {_clean(title, 120)}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _spec_overview_rows(spec: dict[str, Any]) -> list[list[str]]:
    skip = {
        "empty", "extractor", "sources", "coverage", "metrics", "extract_source",
        "vdr_backed", "llm_refined", "document", "dd_code", "fv_code", "role_code",
        "slug", "track", "stage",
    }
    rows: list[list[str]] = []
    for key, val in spec.items():
        if key in skip or val is None or val == "" or val == []:
            continue
        label = key.replace("_", " ").title()
        if isinstance(val, (str, int, float, bool)):
            rows.append([label, _clean(val, 160)])
        elif isinstance(val, list) and val and all(isinstance(x, (str, int, float)) for x in val[:6]):
            rows.append([label, _clean(", ".join(str(x) for x in val[:6]), 160)])
        if len(rows) >= 12:
            break
    return rows


def _render_deal_context(output: dict[str, Any], title: str) -> str:
    """Prompt-book Deal Context template (exec summary → Quality & Reliance)."""
    from agetic_cdd_api.agent_document_deal_context import render_deal_context_markdown

    # Prefer a previously composed full document when present and well-formed.
    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## Headline Fact Ledger" in existing
        or "## 5. Headline Fact Ledger" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"
    # Legacy verdict docs: re-compose from spec if available rather than serving invest language.
    if isinstance(existing, str) and "## 2. Key Investment Hypotheses" in existing and "## 6. Preliminary Investment Verdict" not in existing:
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if spec.get("overview") or spec.get("drivers") or spec.get("hypotheses") or spec.get("fact_ledger"):
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_deal_context_markdown(title, spec, sources=sources)

    # Thin Phase-1 / legacy JSON — emit the prompt-book section skeleton (no invest verdict).
    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin_spec = {
        "insight_snapshot": str(output.get("summary") or f"Deal context frame for {company}."),
        "overview": {
            "target_company": company,
            "legal_entity": company,
            "perimeter": "Information request: acquisition perimeter (not stated in the data room)",
            "buyer_context": "Information request: buyer / sponsor context (not stated in the data room)",
            "acquirer_context": "Information request: buyer / sponsor context (not stated in the data room)",
            "industry": "N/A (data room did not provide it)",
            "transaction_type": "Acquisition",
            "deal_rationale": ", ".join(
                str(f) for f in (output.get("findings") or [])[:3] if f
            )
            or f"Commercial diligence on {company}",
        },
        "drivers": [
            {
                "label": f"Driver {i}",
                "text": f"[Hypothesis] {item}",
                "figure": "N/A (data room did not provide it)",
                "source": "N/A",
                "is_hypothesis": True,
            }
            for i, item in enumerate((output.get("findings") or [])[:3], start=1)
            if item
        ],
        "thesis_read": str(output.get("summary") or ""),
        "hypotheses_insight": "Key hypotheses will firm up as foundation and deep-dive agents complete.",
        "hypotheses": [],
        "hypotheses_read": "Re-run Deal Context after richer VDR coverage to populate Must-Be-True tests.",
        "risks_insight": "Critical risks will be sourced from strategy / financial packs.",
        "risk_bullets": [],
        "risk_table": [],
        "risks_read": "",
        "questions_insight": "Open questions track diligence gaps in the current data room.",
        "questions": [
            {
                "priority": "High",
                "question": gap,
                "why": "Coverage gap in the Central Data Library",
                "unlocking_document": f"Source files for: {gap}",
            }
            for gap in (output.get("gaps") or [])[:3]
        ],
        "questions_read": "",
        "fact_ledger": [
            {
                "fact": "VDR documents indexed",
                "value": str(output.get("document_count") or "—"),
                "unit": "count",
                "period": "current",
                "basis": "actual",
                "source_locator": "library/index.json",
            }
        ],
        "metrics_insight": "Headline facts appear once financial extracts are available.",
        "metrics": [],
        "metrics_read": "",
        "synthesis": str(output.get("summary") or ""),
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "Frame is honest about limits but too thin for an IC decision until "
            "accounting and perimeter facts are located."
        ),
        "primary_sources": output.get("sources") or output.get("context_sources") or [],
    }
    if not thin_spec["drivers"]:
        thin_spec["drivers"] = [
            {
                "label": "Driver 1",
                "text": f"[Hypothesis] Thesis drivers pending richer extracts for {company}.",
                "figure": "N/A (data room did not provide it)",
                "source": "N/A",
                "is_hypothesis": True,
            },
            {
                "label": "Driver 2",
                "text": "[Hypothesis] Share / growth evidence not yet structured.",
                "figure": "N/A (data room did not provide it)",
                "source": "N/A",
                "is_hypothesis": True,
            },
            {
                "label": "Driver 3",
                "text": "[Hypothesis] Profitability path not yet evidenced.",
                "figure": "N/A (data room did not provide it)",
                "source": "N/A",
                "is_hypothesis": True,
            },
        ]
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_deal_context_markdown(title, thin_spec, sources=sources)


def _render_scope_methodology(output: dict[str, Any], title: str) -> str:
    """Prompt-book Scope & Methodology — coverage record (no investment verdict)."""
    from agetic_cdd_api.agent_document_scope_methodology import render_scope_methodology_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Coverage Record" in existing
        or "### Coverage Table" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if spec.get("coverage_table") or spec.get("coverage_counts") or spec.get("exclusions"):
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_scope_methodology_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    findings = output.get("findings") if isinstance(output.get("findings"), list) else []
    covered = [
        str(f).replace("Covered: ", "", 1)
        for f in findings
        if isinstance(f, str) and f.startswith("Covered:")
    ]
    gaps = [str(g) for g in (output.get("gaps") or []) if g]
    doc_count = int(output.get("document_count") or 0)
    in_scope = max(len(covered) + len(gaps), 1)
    evidenced = len(covered)
    must_close = len(gaps)
    thin_spec = {
        "insight_snapshot": (
            f"Coverage record for {company}: {evidenced}/{in_scope} categories with files; "
            f"documents indexed {doc_count}."
        ),
        "coverage_counts": {
            "questions_evidenced": evidenced,
            "questions_in_scope": in_scope,
            "questions_complete": evidenced,
            "documents_read": doc_count,
            "documents_available": doc_count,
        },
        "coverage_table": [
            {
                "question": f"Diligence under {label}",
                "work_done": "VDR files present in category",
                "source": "Central Data Library",
                "period": "N/A (data room did not provide it)",
                "method": "Category coverage scan",
                "status": "partial",
            }
            for label in (covered or ["Deal / Strategy"])[:8]
        ],
        "completed_work": [f"Indexed files under {c}" for c in covered[:6]],
        "planned_work": [f"Deepen diligence under {g}" for g in gaps[:6]],
        "blocked_work": [
            f"{g}: cannot finish without VDR files" for g in gaps[:6]
        ],
        "exclusions": [
            {
                "item": f"Primary diligence under {g}",
                "reason": f"No indexed files for {g}",
                "state": "cannot_with_evidence",
                "workstream": g,
            }
            for g in gaps[:6]
        ]
        or [
            {
                "item": "Macro overlay beyond engagement perimeter",
                "reason": "Out of scope by agreement",
                "state": "out_of_scope",
                "workstream": "Deal / Strategy",
            }
        ],
        "fieldwork": [
            {
                "date": "undated — does not count as work performed",
                "participants": "N/A (data room did not provide it)",
                "type": "Interview / site visit",
                "status": "none_claimed",
            }
        ],
        "unfinished": [
            {
                "item": f"Obtain and review {g} pack",
                "could_change": "decision",
                "gate": "must_close",
                "workstream": g,
            }
            for g in gaps[:6]
        ],
        "coverage_conclusion": (
            f"Diligence coverage for {company} is incomplete."
            if must_close
            else f"Diligence coverage for {company}: {evidenced}/{in_scope} categories evidenced."
        )
        + " This concludes on completeness only — not investment attractiveness.",
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED" if must_close else "LIMITED",
        "quality_reliance_rationale": (
            f"{evidenced}/{in_scope} categories with files; {must_close} gap(s); "
            f"{doc_count} documents indexed."
        ),
        "primary_sources": output.get("sources") or output.get("context_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_scope_methodology_markdown(title, thin_spec, sources=sources)



def _render_company_background(output: dict[str, Any], title: str) -> str:
    """Prompt-book Company Background — real operating business (no invest verdict)."""
    from agetic_cdd_api.agent_document_company_background import render_company_background_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 5. Quality & Reliance" in existing
        or "## 1. What It Sells" in existing
        or "## 4. Operating Model" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("offers")
        or spec.get("operating_model")
        or spec.get("revenue_by_service_line")
        or spec.get("ownership")
    ):
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_company_background_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    legal = str(spec.get("legal_name") or company)
    hq = str(spec.get("jurisdiction") or "")
    founded = str(spec.get("incorporation_date") or "")
    na = "N/A (data room did not provide it)"
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"{legal}: operating description pending fuller VDR extracts."
        ),
        "offers": {
            "sells": na,
            "how_charges": na,
            "who_pays": na,
        },
        "revenue_by_service_line": [],
        "revenue_by_customer_type": [],
        "revenue_by_geography": [],
        "recurring_by_contract": "Omitted: Contract-level recurring % not in the data room",
        "accounts_reconciliation": "Information request: revenue by service line / customer / geography",
        "products_in_company_terms": [],
        "omitted_fields": [
            {"field": "revenue_by_service_line", "reason": "Not yet composed from VDR"},
        ],
        "sites": (
            [{"site": hq, "type": "HQ", "role": "Headquarters", "source": "(DOC: corporate / HR pack)"}]
            if hq
            else []
        ),
        "capacity": {
            "fleet_or_capacity": "Omitted: No capacity figure in VDR",
            "utilisation": "Omitted: Utilisation not measurable",
            "source": na,
        },
        "headcount_by_function": [],
        "ownership": {
            "legal_entities": legal,
            "ownership_or_cap_table": "Information request: cap table and corporate record",
            "headquarters": hq or na,
            "founded": founded or na,
            "history_events": [],
            "corporate_record_requests": [
                "Information request: cap table and corporate record",
            ],
        },
        "operating_model": (
            f"Operating model for {legal} is not yet evidenced end-to-end in the current pack."
        ),
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "Thin VDR extract — later agents lack a reliable operating picture.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
        "legal_name": legal,
        "jurisdiction": hq or None,
        "incorporation_date": founded or None,
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_company_background_markdown(title, thin, sources=sources)


def _render_market_pricing(output: dict[str, Any], title: str) -> str:
    """Prompt-book Market Pricing — realised price & power (no invest verdict)."""
    from agetic_cdd_api.agent_document_market_pricing import render_market_pricing_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Realised Net Price" in existing
        or "## 5. Contract Escalators" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("realised_prices")
        or spec.get("price_points")
        or spec.get("competitor_comparisons")
    ):
        if not spec.get("realised_prices"):
            points = [
                {
                    "service_or_segment": str(p.get("label") or "price"),
                    "period": p.get("as_of") or "as stated",
                    "list_price": (
                        f"{p.get('unit', '')} {p['value']:g}"
                        if str(p.get("label") or "").lower() in {"flagship", "list", "mrp"}
                        else "N/A (data room did not provide it)"
                    ),
                    "realised_net_price": (
                        f"{p.get('unit', '')} {p['value']:g}"
                        if str(p.get("label") or "").lower() in {"asp", "realised", "net"}
                        or str(p.get("label") or "").lower() not in {"flagship", "list", "mrp"}
                        else "N/A (data room did not provide it)"
                    ),
                    "notes": str(p.get("raw") or ""),
                }
                for p in (spec.get("price_points") or [])
                if isinstance(p, dict) and p.get("value") is not None
            ]
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary") or "Market Pricing from deep-dive extract."
                ),
                "realised_prices": points
                or [
                    {
                        "service_or_segment": "Information request: service / segment",
                        "period": "Information request: period",
                        "list_price": "Information request: list price",
                        "realised_net_price": "Information request: realised net price",
                        "notes": "Keep list and realised separate",
                    }
                ],
                "competitor_comparisons": [
                    {
                        "competitor": "Information request: named competitor",
                        "equivalent_service": "Information request: equivalent service",
                        "their_price": "Information request: dated quote",
                        "date_or_source": "N/A (data room did not provide it)",
                        "notes": "Unnamed comparators are not acceptable",
                    }
                ],
                "pvm_bridge": [],
                "observed_response": [],
                "escalators": {
                    "present": "Information request: escalators",
                    "revenue_coverage": "Information request: revenue coverage",
                    "notes": "Distinguish % from percentage points",
                },
                "pct_vs_pp_note": (
                    "Distinguish percentage change from percentage-point change every time."
                ),
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
                "quality_reliance_rationale": "Legacy price extract present; comps incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_market_pricing_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Market Pricing for {company} pending opened commercial / billing packs."
        ),
        "realised_prices": [],
        "competitor_comparisons": [],
        "pvm_bridge": [],
        "observed_response": [],
        "escalators": {
            "present": "N/A (data room did not provide it)",
            "revenue_coverage": "N/A (data room did not provide it)",
            "notes": "Distinguish % from percentage points",
        },
        "pct_vs_pp_note": (
            "Distinguish percentage change from percentage-point change every time."
        ),
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No pricing packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_market_pricing_markdown(title, thin, sources=sources)


def _render_demand_drivers(output: dict[str, Any], title: str) -> str:
    """Prompt-book Demand Drivers — cause → customers → cash (no invest verdict)."""
    from agetic_cdd_api.agent_document_demand_drivers import render_demand_drivers_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Drivers That Apply" in existing
        or "## 3. Transmission Path" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if spec.get("drivers") or spec.get("demand_drivers") or spec.get("transmission"):
        if not spec.get("drivers") and spec.get("demand_drivers"):
            legacy_rows = []
            for item in (spec.get("demand_drivers") or [])[:6]:
                if isinstance(item, str) and item.strip():
                    legacy_rows.append({
                        "driver": item[:80],
                        "mechanism": item,
                        "customer_population_exposed": (
                            "N/A (data room did not provide it)"
                        ),
                        "effective_date": "N/A (data room did not provide it)",
                        "expected_size": "N/A (data room did not provide it)",
                        "persistence": "N/A (data room did not provide it)",
                        "instrument_type": "voluntary_commitment",
                        "geography": "N/A (data room did not provide it)",
                        "notes": "Legacy extract — confirm instrument type and dates",
                    })
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary") or "Demand Drivers from deep-dive extract."
                ),
                "drivers": legacy_rows,
                "instrument_separation": spec.get("instrument_separation") or [],
                "transmission": spec.get("transmission") or [],
                "counter_drivers": [
                    {
                        "counter_driver": r,
                        "cyclicality": "N/A (data room did not provide it)",
                        "company_history": "N/A (data room did not provide it)",
                        "notes": "From legacy cycle_risks",
                    }
                    for r in (spec.get("cycle_risks") or [])[:4]
                    if isinstance(r, str)
                ] or spec.get("counter_drivers") or [],
                "ranked_contribution": spec.get("ranked_contribution") or [],
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy demand extract present; transmission incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_demand_drivers_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Demand Drivers for {company} pending opened commercial / policy packs."
        ),
        "drivers": [],
        "instrument_separation": [],
        "transmission": [],
        "counter_drivers": [],
        "ranked_contribution": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No demand / policy packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_demand_drivers_markdown(title, thin, sources=sources)


def _render_competitor_identification(output: dict[str, Any], title: str) -> str:
    """Prompt-book Competitor Identification — named set (no invest verdict)."""
    from agetic_cdd_api.agent_document_competitor_identification import (
        render_competitor_identification_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Target Reference" in existing
        or "## 2. Named Competitive Set" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("competitive_set")
        or spec.get("competitors")
        or spec.get("target_reference")
    ):
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_competitor_identification_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Competitor Identification for {company} pending opened competition packs."
        ),
        "target_reference": {
            "name": company,
            "geography": "N/A (data room did not provide it)",
            "service_overlap": "Target reference — not a competitor",
            "scale": "N/A (data room did not provide it)",
            "trading_status": "Target company (reference row only)",
            "source": "N/A (data room did not provide it)",
            "notes": "Never place the target in its own competitor list",
        },
        "competitive_set": [],
        "competitors": [],
        "customer_choice": [],
        "barriers": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No competition packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_competitor_identification_markdown(title, thin, sources=sources)


def _render_competitive_differentiation(output: dict[str, Any], title: str) -> str:
    """Prompt-book Competitive Differentiation — advantage tests (no invest verdict)."""
    from agetic_cdd_api.agent_document_competitive_differentiation import (
        render_competitive_differentiation_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Claimed Advantages" in existing
        or "## 2. Advantage Tests" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("claimed_advantages")
        or spec.get("advantage_tests")
        or spec.get("differentiators")
    ):
        if not spec.get("claimed_advantages") and spec.get("differentiators"):
            claims = []
            for item in (spec.get("differentiators") or [])[:6]:
                if isinstance(item, str) and item.strip():
                    claims.append({
                        "claim": item[:120],
                        "claimed_by": "N/A (data room did not provide it)",
                        "where_stated": item,
                        "source": "(DOC: data room financials)",
                    })
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Competitive Differentiation from deep-dive extract."
                ),
                "claimed_advantages": claims,
                "advantage_tests": spec.get("advantage_tests") or [],
                "capability_separation": spec.get("capability_separation") or {
                    "ordinary_capability": [],
                    "management_assertion": claims,
                    "demonstrated_advantage": [],
                },
                "economic_effects": spec.get("economic_effects") or [],
                "replication": spec.get("replication") or [],
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy differentiator extract present; advantage tests incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_competitive_differentiation_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Competitive Differentiation for {company} pending opened competition packs."
        ),
        "claimed_advantages": [],
        "advantage_tests": [],
        "capability_separation": {
            "ordinary_capability": [],
            "management_assertion": [],
            "demonstrated_advantage": [],
        },
        "economic_effects": [],
        "replication": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No differentiation packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_competitive_differentiation_markdown(title, thin, sources=sources)


def _render_market_share_strategy(output: dict[str, Any], title: str) -> str:
    """Prompt-book Market Share Strategy — matched share / funnel / attainable (no invest)."""
    from agetic_cdd_api.agent_document_market_share_strategy import (
        render_market_share_strategy_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Matched Share" in existing
        or "## 5. Bottom-Up Attainable" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("matched_share")
        or spec.get("share_movement")
        or spec.get("share_trends")
        or spec.get("wins")
        or spec.get("strategy_notes")
    ):
        if not isinstance(spec.get("matched_share"), dict):
            trends = spec.get("share_trends") or []
            stated = None
            for row in trends:
                if isinstance(row, dict) and row.get("market_share_pct") is not None:
                    stated = row.get("market_share_pct")
                    break
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Market Share Strategy from deep-dive extract."
                ),
                "matched_share": {
                    "calculable": False,
                    "numerator": "N/A (data room did not provide it)",
                    "denominator": "N/A (data room did not provide it)",
                    "share_pct": None,
                    "service": "N/A (data room did not provide it)",
                    "geography": "N/A (data room did not provide it)",
                    "unit": "N/A (data room did not provide it)",
                    "date_or_period": "N/A (data room did not provide it)",
                    "match_notes": (
                        f"Legacy share trend stated at {stated}% but numerator/denominator "
                        f"match on service/geography/unit/date was not evidenced — "
                        f"share remains unassessed on a matched basis."
                        if stated is not None
                        else "Share not calculable; missing matched numerator and denominator."
                    ),
                    "information_request": (
                        "Information request: accounts numerator and approved market "
                        "perimeter denominator matched on service, geography, unit and date"
                    ),
                    "source": "(DOC: data room financials)",
                },
                "share_movement": spec.get("share_movement") or [],
                "plan_requirements": spec.get("plan_requirements") or {
                    "customers_per_month": "N/A (data room did not provide it)",
                    "volume": "N/A (data room did not provide it)",
                    "capacity": "N/A (data room did not provide it)",
                    "sales_headcount": "N/A (data room did not provide it)",
                    "other_physical": "N/A (data room did not provide it)",
                    "source": "(DOC: data room financials)",
                    "gaps": "Information request: physical requirements of the growth plan",
                },
                "funnel_economics": spec.get("funnel_economics") or [],
                "attainable_vs_ambition": spec.get("attainable_vs_ambition") or {
                    "bottom_up_attainable": "N/A (data room did not provide it)",
                    "management_ambition": "N/A (data room did not provide it)",
                    "gap": "N/A (data room did not provide it)",
                    "what_must_change": "Information request: funnel rates and management target",
                    "source": "(DOC: data room financials)",
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy win/loss extract present; matched-share and funnel tests incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_market_share_strategy_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Market Share Strategy for {company} pending opened competition packs. "
            f"Share is unassessed until numerator and denominator can be matched."
        ),
        "matched_share": {
            "calculable": False,
            "numerator": "N/A (data room did not provide it)",
            "denominator": "N/A (data room did not provide it)",
            "share_pct": None,
            "service": "N/A (data room did not provide it)",
            "geography": "N/A (data room did not provide it)",
            "unit": "N/A (data room did not provide it)",
            "date_or_period": "N/A (data room did not provide it)",
            "match_notes": "Share not calculable; no competition packs resolved.",
            "information_request": (
                "Information request: accounts numerator and approved market perimeter denominator"
            ),
            "source": "(DOC: data room financials)",
        },
        "share_movement": [],
        "plan_requirements": {
            "customers_per_month": "N/A (data room did not provide it)",
            "volume": "N/A (data room did not provide it)",
            "capacity": "N/A (data room did not provide it)",
            "sales_headcount": "N/A (data room did not provide it)",
            "other_physical": "N/A (data room did not provide it)",
            "source": "(DOC: data room financials)",
            "gaps": "Information request: physical requirements of the growth plan",
        },
        "funnel_economics": [],
        "attainable_vs_ambition": {
            "bottom_up_attainable": "N/A (data room did not provide it)",
            "management_ambition": "N/A (data room did not provide it)",
            "gap": "N/A (data room did not provide it)",
            "what_must_change": "Information request: funnel rates and management target",
            "source": "(DOC: data room financials)",
        },
        "share_trends": [],
        "wins": [],
        "losses": [],
        "strategy_notes": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No share / plan packs resolved; share unassessed.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_market_share_strategy_markdown(title, thin, sources=sources)


def _render_customer_segmentation(output: dict[str, Any], title: str) -> str:
    """Prompt-book Customer Segmentation — concentration calculated (no invest)."""
    from agetic_cdd_api.agent_document_customer_segmentation import (
        render_customer_segmentation_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Ledger" in existing
        or "## 3. Concentration" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("concentration")
        or spec.get("segments_by_axis")
        or spec.get("segments")
        or spec.get("largest_contracts")
    ):
        if not isinstance(spec.get("concentration"), dict):
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Customer Segmentation from deep-dive extract."
                ),
                "ledger_resolution": spec.get("ledger_resolution") or {
                    "status": "missing",
                    "source_doc": "N/A (data room did not provide it)",
                    "grain": "N/A (data room did not provide it)",
                    "notes": "Billing ledger / investor workbook not resolved in legacy extract.",
                    "information_request": (
                        "Information request: billing ledger or investor workbook with "
                        "account, parent and location identifiers"
                    ),
                    "source": "(DOC: data room financials)",
                },
                "customer_universe": spec.get("customer_universe") or {
                    "accounts_n": "N/A (data room did not provide it)",
                    "parents_n": "N/A (data room did not provide it)",
                    "locations_n": "N/A (data room did not provide it)",
                    "subscriptions_n": "N/A (data room did not provide it)",
                    "population_label": "N/A (data room did not provide it)",
                    "source": "(DOC: data room financials)",
                },
                "segments_by_axis": spec.get("segments_by_axis") or [],
                "concentration": {
                    "calculable": False,
                    "population": "parents",
                    "top_1_share_pct": None,
                    "top_5_share_pct": None,
                    "top_10_share_pct": None,
                    "concentration_index": None,
                    "gross_profit_top_1_share_pct": None,
                    "gross_profit_top_5_share_pct": None,
                    "calculation_notes": (
                        "Concentration unassessed — parent-level revenue shares not "
                        "calculated from a billing ledger in the legacy extract."
                    ),
                    "information_request": (
                        "Information request: parent-aggregated revenue shares for "
                        "top 1 / top 5 / top 10 from the billing ledger"
                    ),
                    "risk_rating": "withheld",
                    "source": "(DOC: data room financials)",
                },
                "largest_contracts": spec.get("largest_contracts") or [],
                "population_discipline": spec.get("population_discipline") or {
                    "statement": (
                        "Population for each count must be stated (accounts / parents / "
                        "locations / subscriptions); never mix in one table."
                    ),
                    "caveats": "Legacy ICP extract does not enforce population discipline.",
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy ICP extract present; concentration unassessed pending ledger.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_customer_segmentation_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Customer Segmentation for {company} pending opened customer packs. "
            f"Concentration is unassessed until the billing ledger can be opened."
        ),
        "ledger_resolution": {
            "status": "missing",
            "source_doc": "N/A (data room did not provide it)",
            "grain": "N/A (data room did not provide it)",
            "notes": "No customer packs resolved.",
            "information_request": (
                "Information request: billing ledger or investor workbook"
            ),
            "source": "(DOC: data room financials)",
        },
        "customer_universe": {
            "accounts_n": "N/A (data room did not provide it)",
            "parents_n": "N/A (data room did not provide it)",
            "locations_n": "N/A (data room did not provide it)",
            "subscriptions_n": "N/A (data room did not provide it)",
            "population_label": "N/A (data room did not provide it)",
            "source": "(DOC: data room financials)",
        },
        "segments_by_axis": [],
        "concentration": {
            "calculable": False,
            "population": "parents",
            "top_1_share_pct": None,
            "top_5_share_pct": None,
            "top_10_share_pct": None,
            "concentration_index": None,
            "gross_profit_top_1_share_pct": None,
            "gross_profit_top_5_share_pct": None,
            "calculation_notes": "Concentration unassessed — no packs resolved.",
            "information_request": (
                "Information request: parent-aggregated top 1 / 5 / 10 revenue shares"
            ),
            "risk_rating": "withheld",
            "source": "(DOC: data room financials)",
        },
        "largest_contracts": [],
        "population_discipline": {
            "statement": (
                "Every count must name its population "
                "(accounts / parents / locations / subscriptions)."
            ),
            "caveats": "No customer packs resolved.",
        },
        "segments": [],
        "geo_mix": [],
        "icp_notes": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No customer packs resolved; concentration unassessed; risk rating withheld."
        ),
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_customer_segmentation_markdown(title, thin, sources=sources)


def _render_customer_stickiness(output: dict[str, Any], title: str) -> str:
    """Prompt-book Customer Stickiness — GRR/NRR/cohorts/contracts (no invest)."""
    from agetic_cdd_api.agent_document_customer_stickiness import (
        render_customer_stickiness_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Population" in existing
        or "## 2. Retention Bridge" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("retention_metrics")
        or spec.get("cohorts")
        or spec.get("retention_bridge")
        or spec.get("contract_protections")
    ):
        if not isinstance(spec.get("population_definition"), dict):
            metrics = spec.get("retention_metrics") if isinstance(spec.get("retention_metrics"), dict) else {}
            grr = metrics.get("grr_pct")
            nrr = metrics.get("nrr_pct")
            logo_churn = metrics.get("logo_churn_pct")
            logo_ret = None
            if logo_churn is not None:
                try:
                    logo_ret = f"{100.0 - float(logo_churn):g}%"
                except (TypeError, ValueError):
                    logo_ret = None
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Customer Stickiness from deep-dive extract."
                ),
                "population_definition": {
                    "population": "logos",
                    "definition": "N/A (data room did not provide it) — population inferred from legacy extract",
                    "constant_rule": "Information request: confirm population held constant across periods",
                    "source": "(DOC: data room financials)",
                    "information_request": (
                        "Information request: define population (logos/accounts/locations/subscriptions) and hold constant"
                    ),
                },
                "retention_bridge": spec.get("retention_bridge") or {
                    "period": "N/A (data room did not provide it)",
                    "opening_revenue": "N/A (data room did not provide it)",
                    "churn": "N/A (data room did not provide it)",
                    "contraction": "N/A (data room did not provide it)",
                    "expansion": "N/A (data room did not provide it)",
                    "closing_revenue": "N/A (data room did not provide it)",
                    "new_customers_excluded": "Information request: confirm new customers excluded from retention numerators",
                    "source": "(DOC: data room financials)",
                    "gaps": "Legacy extract had metrics without a full bridge",
                },
                "retention_on_same_population": {
                    "population": "logos",
                    "grr": f"{grr}%" if grr is not None else "N/A (data room did not provide it)",
                    "nrr": f"{nrr}%" if nrr is not None else "N/A (data room did not provide it)",
                    "logo_retention": logo_ret or "N/A (data room did not provide it)",
                    "notes": "Legacy metrics; same-population and new-customer exclusion not evidenced.",
                },
                "retention_delta": spec.get("retention_delta") or [],
                "retention_by_segment": spec.get("retention_by_segment") or [],
                "retention_by_tenure": spec.get("retention_by_tenure") or [],
                "loss_reasons": spec.get("loss_reasons") or [],
                "loss_concentration": spec.get("loss_concentration") or {
                    "statement": "N/A (data room did not provide it)",
                    "source": "(DOC: data room financials)",
                },
                "contract_protections": spec.get("contract_protections") or [],
                "renewal_cliff": spec.get("renewal_cliff") or {
                    "material_share_pct": "N/A (data room did not provide it)",
                    "window": "N/A (data room did not provide it)",
                    "note": "Information request: renewal cliff for material revenue share",
                    "source": "(DOC: data room financials)",
                    "information_request": (
                        "Information request: when material share of revenue comes up for renewal"
                    ),
                },
                "behaviour_vs_protection": spec.get("behaviour_vs_protection") or {
                    "stayed_note": "N/A (data room did not provide it)",
                    "committed_note": "N/A (data room did not provide it)",
                    "distinction": "Customers who have stayed are not the same as customers who are contractually committed.",
                    "source": "(DOC: data room financials)",
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy retention extract present; bridge and contract protection incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_customer_stickiness_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Customer Stickiness for {company} pending opened retention packs."
        ),
        "population_definition": {
            "population": "logos",
            "definition": "N/A (data room did not provide it)",
            "constant_rule": "Information request: define and hold population constant",
            "source": "(DOC: data room financials)",
            "information_request": "Information request: cohort population definition",
        },
        "cohorts": [],
        "retention_bridge": {
            "period": "N/A (data room did not provide it)",
            "opening_revenue": "N/A (data room did not provide it)",
            "churn": "N/A (data room did not provide it)",
            "contraction": "N/A (data room did not provide it)",
            "expansion": "N/A (data room did not provide it)",
            "closing_revenue": "N/A (data room did not provide it)",
            "new_customers_excluded": "Information request: confirm new customers excluded",
            "source": "(DOC: data room financials)",
            "gaps": "No retention packs resolved.",
        },
        "retention_metrics": {},
        "retention_on_same_population": {
            "population": "logos",
            "grr": "N/A (data room did not provide it)",
            "nrr": "N/A (data room did not provide it)",
            "logo_retention": "N/A (data room did not provide it)",
            "notes": "No packs resolved.",
        },
        "retention_delta": [],
        "retention_by_segment": [],
        "retention_by_tenure": [],
        "loss_reasons": [],
        "loss_concentration": {
            "statement": "N/A (data room did not provide it)",
            "source": "(DOC: data room financials)",
        },
        "contract_protections": [],
        "renewal_cliff": {
            "material_share_pct": "N/A (data room did not provide it)",
            "window": "N/A (data room did not provide it)",
            "note": "Information request: renewal cliff",
            "source": "(DOC: data room financials)",
            "information_request": "Information request: renewal cliff",
        },
        "behaviour_vs_protection": {
            "stayed_note": "N/A (data room did not provide it)",
            "committed_note": "N/A (data room did not provide it)",
            "distinction": "Customers who have stayed are not the same as customers who are contractually committed.",
            "source": "(DOC: data room financials)",
        },
        "stickiness_notes": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No retention packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_customer_stickiness_markdown(title, thin, sources=sources)


def _render_customer_satisfaction(output: dict[str, Any], title: str) -> str:
    """Prompt-book Customer Satisfaction — survey/ops/association/research (no invest)."""
    from agetic_cdd_api.agent_document_customer_satisfaction import (
        render_customer_satisfaction_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Survey" in existing
        or "## 2. Operational" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("survey_assessment")
        or spec.get("operational_signals")
        or spec.get("churn_association")
        or spec.get("nps") is not None
        or spec.get("service_satisfaction_pct") is not None
        or spec.get("churn_drivers")
    ):
        if not isinstance(spec.get("survey_assessment"), dict):
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Customer Satisfaction from deep-dive extract."
                ),
                "survey_assessment": {
                    "present": False,
                    "date": "N/A (data room did not provide it)",
                    "target_population": "N/A (data room did not provide it)",
                    "sample_size": "N/A (data room did not provide it)",
                    "response_rate": "N/A (data room did not provide it)",
                    "segment_mix": "N/A (data room did not provide it)",
                    "question_wording": "N/A (data room did not provide it)",
                    "selection_bias": "Information request: selection / non-response bias assessment",
                    "score_definition": "N/A (data room did not provide it)",
                    "scores_from_valid_only": "Information request: confirm scores use valid responses only",
                    "inaccessible_file_note": "",
                    "information_request": (
                        "Information request: survey design (date, population, sample, "
                        "response rate, wording)"
                    ),
                    "source": "(DOC: data room financials)",
                },
                "operational_signals": spec.get("operational_signals") or [],
                "churn_association": spec.get("churn_association") or {
                    "comparable": False,
                    "association_only": True,
                    "service_failure": "N/A (data room did not provide it)",
                    "subsequent_cancellation": "N/A (data room did not provide it)",
                    "notes": (
                        "Information request: matched service-failure and subsequent-"
                        "cancellation records"
                    ),
                    "source": "N/A (data room did not provide it)",
                    "information_request": (
                        "Information request: customer-level link of service failures to "
                        "subsequent cancellations"
                    ),
                },
                "public_reviews": spec.get("public_reviews") or {
                    "treated_as": "self_selected_signal",
                    "notes": (
                        "No public-review corpus was opened. If used later, treat as a "
                        "self-selected signal, not research."
                    ),
                    "source": "N/A (data room did not provide it)",
                },
                "research_design": spec.get("research_design") or {
                    "needed": True,
                    "population": "Information request: define surveyed population",
                    "sample": "Information request: sample size and frame",
                    "method": "Information request: method (e.g. structured survey / interview)",
                    "questions": "Information request: question wording and scale definition",
                    "timing": "Information request: fieldwork window",
                    "rationale": "Sentiment evidence thin — commission designed research.",
                },
                "score_traceability": spec.get("score_traceability") or {
                    "nps_traceable": spec.get("nps") is not None,
                    "csat_traceable": spec.get("service_satisfaction_pct") is not None,
                    "notes": "Legacy extract; confirm scores are from valid responses only.",
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy satisfaction extract present; survey design incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_customer_satisfaction_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Customer Satisfaction for {company} pending opened sentiment packs."
        ),
        "survey_assessment": {
            "present": False,
            "date": "N/A (data room did not provide it)",
            "target_population": "N/A (data room did not provide it)",
            "sample_size": "N/A (data room did not provide it)",
            "response_rate": "N/A (data room did not provide it)",
            "segment_mix": "N/A (data room did not provide it)",
            "question_wording": "N/A (data room did not provide it)",
            "selection_bias": "Information request: selection / non-response bias assessment",
            "score_definition": "N/A (data room did not provide it)",
            "scores_from_valid_only": "Information request: confirm scores use valid responses only",
            "inaccessible_file_note": (
                "Absence of an accessible survey file does **not** imply poor customer focus — "
                "it is an information gap, not a finding about service quality."
            ),
            "information_request": "Information request: survey design pack",
            "source": "N/A (data room did not provide it)",
        },
        "nps": None,
        "peer_nps": [],
        "service_satisfaction_pct": None,
        "churn_drivers": [],
        "satisfaction_notes": [],
        "operational_signals": [],
        "churn_association": {
            "comparable": False,
            "association_only": True,
            "service_failure": "N/A (data room did not provide it)",
            "subsequent_cancellation": "N/A (data room did not provide it)",
            "notes": "Information request: matched service-failure and subsequent-cancellation records",
            "source": "N/A (data room did not provide it)",
            "information_request": (
                "Information request: customer-level link of service failures to subsequent cancellations"
            ),
        },
        "public_reviews": {
            "treated_as": "self_selected_signal",
            "notes": (
                "No public-review corpus was opened. If used later, treat as a self-selected "
                "signal, not research."
            ),
            "source": "N/A (data room did not provide it)",
        },
        "research_design": {
            "needed": True,
            "population": "Information request: define surveyed population",
            "sample": "Information request: sample size and frame",
            "method": "Information request: method (e.g. structured survey / interview)",
            "questions": "Information request: question wording and scale definition",
            "timing": "Information request: fieldwork window",
            "rationale": "No sentiment packs resolved — commission designed research.",
        },
        "score_traceability": {
            "nps_traceable": False,
            "csat_traceable": False,
            "notes": "No scores quoted — none were traceable.",
        },
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No survey or operational sentiment packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_customer_satisfaction_markdown(title, thin, sources=sources)


def _render_buying_behavior(output: dict[str, Any], title: str) -> str:
    """Prompt-book Buying Behavior — maps/cycles/switching/seasonality (no invest)."""
    from agetic_cdd_api.agent_document_buying_behavior import (
        render_buying_behavior_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Purchase" in existing
        or "## 2. Sales Cycle" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("purchase_maps")
        or spec.get("sales_cycles")
        or spec.get("switching")
        or spec.get("buying_metrics")
        or spec.get("concentration_flags")
        or spec.get("behavior_notes")
    ):
        if not isinstance(spec.get("purchase_maps"), list):
            metrics = (
                spec.get("buying_metrics")
                if isinstance(spec.get("buying_metrics"), dict)
                else {}
            )
            ttp = metrics.get("time_to_purchase_days")
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Buying Behavior from deep-dive extract."
                ),
                "purchase_maps": [],
                "sales_cycles": (
                    [
                        {
                            "segment": "All (unsegmented legacy)",
                            "median": (
                                f"{ttp:g} days" if ttp is not None
                                else "N/A (data room did not provide it)"
                            ),
                            "range_low": "N/A (data room did not provide it)",
                            "range_high": "N/A (data room did not provide it)",
                            "unit": "days",
                            "source": "(DOC: data room financials)",
                            "notes": (
                                "Legacy extract had a single cycle figure — not assigned "
                                "to all segments without per-segment CRM."
                            ),
                            "crm_evidenced": ttp is not None,
                        }
                    ]
                    if ttp is not None
                    else []
                ),
                "switching": spec.get("switching") or {
                    "evidenced": False,
                    "purchase_criteria": [
                        "Information request: purchase criteria from bid outcomes / win-loss"
                    ],
                    "switching_triggers": [
                        "Information request: switching triggers from wins and losses"
                    ],
                    "customers_say": [
                        "Information request: stated preferences (with sample/dates/method)"
                    ],
                    "customers_did": [
                        "Information request: observed win/loss outcomes"
                    ],
                    "say_vs_did_note": (
                        "What customers **say** is distinguished from what they **did** "
                        "(bid outcomes / win-loss)."
                    ),
                    "anecdotal_count": 0,
                    "source": "N/A (data room did not provide it)",
                    "information_request": (
                        "Information request: win/loss notes and bid outcomes"
                    ),
                },
                "seasonality": spec.get("seasonality") or {
                    "measured": False,
                    "pattern": (
                        "Seasonality is measured from monthly records; if the pattern is "
                        "not in the data, it is **not asserted**. Information request: "
                        "monthly signups, cancellations and volume series"
                    ),
                    "controls_for_growth_acq": False,
                    "asserted_without_data": False,
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Seasonality is measured from monthly records; if the pattern is "
                        "not in the data, it is **not asserted**."
                    ),
                },
                "implications": spec.get("implications") or {
                    "sales_capacity": (
                        "Information request: sales capacity implications from cycle "
                        "length and segment mix"
                    ),
                    "conversion_assumptions": (
                        "Information request: conversion assumptions by segment from CRM funnel"
                    ),
                    "pricing_strategy": (
                        "Information request: pricing strategy implications from purchase "
                        "criteria / switching"
                    ),
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy buying extract present; per-segment maps and cycles incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_buying_behavior_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Buying Behavior for {company} pending opened CRM / win-loss packs."
        ),
        "purchase_maps": [],
        "sales_cycles": [],
        "switching": {
            "evidenced": False,
            "purchase_criteria": [
                "Information request: purchase criteria from bid outcomes / win-loss"
            ],
            "switching_triggers": [
                "Information request: switching triggers from wins and losses"
            ],
            "customers_say": [
                "Information request: stated preferences (with sample/dates/method)"
            ],
            "customers_did": ["Information request: observed win/loss outcomes"],
            "say_vs_did_note": (
                "What customers **say** is distinguished from what they **did** "
                "(bid outcomes / win-loss)."
            ),
            "anecdotal_count": 0,
            "source": "N/A (data room did not provide it)",
            "information_request": (
                "Information request: win/loss notes and bid outcomes"
            ),
        },
        "seasonality": {
            "measured": False,
            "pattern": (
                "Seasonality is measured from monthly records; if the pattern is not "
                "in the data, it is **not asserted**. Information request: monthly "
                "signups, cancellations and volume series"
            ),
            "controls_for_growth_acq": False,
            "asserted_without_data": False,
            "source": "N/A (data room did not provide it)",
            "notes": (
                "Seasonality is measured from monthly records; if the pattern is not "
                "in the data, it is **not asserted**."
            ),
        },
        "implications": {
            "sales_capacity": (
                "Information request: sales capacity implications from cycle length "
                "and segment mix"
            ),
            "conversion_assumptions": (
                "Information request: conversion assumptions by segment from CRM funnel"
            ),
            "pricing_strategy": (
                "Information request: pricing strategy implications from purchase "
                "criteria / switching"
            ),
        },
        "concentration_flags": [],
        "channel_mix": [],
        "buying_metrics": {},
        "behavior_notes": [],
        "segment_hhi": None,
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No CRM / win-loss / monthly buying packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_buying_behavior_markdown(title, thin, sources=sources)


def _render_supplier_dependence(output: dict[str, Any], title: str) -> str:
    """Prompt-book Supplier Dependence — spend/criticality/contracts/switch (no invest)."""
    from agetic_cdd_api.agent_document_supplier_dependence import (
        render_supplier_dependence_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Supplier Spend" in existing
        or "## 2. Operational Criticality" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("spend_by_supplier")
        or spec.get("operational_criticality")
        or spec.get("contract_terms")
        or spec.get("vendors")
        or spec.get("concentration_flags")
    ):
        if not isinstance(spec.get("spend_by_supplier"), list):
            vendors = [
                v for v in (spec.get("vendors") or []) if isinstance(v, dict)
            ]
            spend_rows = []
            for v in vendors:
                spend = v.get("annual_value_inr_cr")
                spend_rows.append({
                    "supplier": v.get("name") or "N/A (data room did not provide it)",
                    "period": "N/A (data room did not provide it)",
                    "spend": (
                        f"{spend:g} Cr" if spend is not None
                        else "Information request: payables spend"
                    ),
                    "share_of_total_pct": (
                        "Information request: share of total payables spend"
                    ),
                    "component": v.get("component") or "N/A (data room did not provide it)",
                    "country": v.get("country") or "N/A (data room did not provide it)",
                    "source": "(DOC: data room financials)",
                    "ledger_evidenced": spend is not None,
                })
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Supplier Dependence from deep-dive extract."
                ),
                "spend_by_supplier": spend_rows,
                "operational_criticality": [
                    {
                        "supplier": v.get("name") or "Vendor",
                        "criticality": v.get("risk_level") or (
                            "Information request: operational criticality separate from spend"
                        ),
                        "what_stops": (
                            "Information request: what stops if this supplier stops"
                        ),
                        "spend_vs_criticality": (
                            "Operational criticality is rated separately from spend."
                        ),
                        "source": "(DOC: data room financials)",
                    }
                    for v in vendors[:8]
                ] or [{
                    "supplier": "Information request: critical suppliers",
                    "criticality": "Information request: operational criticality",
                    "what_stops": "Information request: what stops",
                    "spend_vs_criticality": (
                        "Operational criticality is rated separately from spend."
                    ),
                    "source": "N/A (data room did not provide it)",
                }],
                "contract_terms": spec.get("contract_terms") or [{
                    "supplier": "Information request: critical supplier contracts",
                    "contract_read": "No — terms not stated",
                    "duration": "N/A (data room did not provide it)",
                    "renewal": "N/A (data room did not provide it)",
                    "pricing_mechanism": "N/A (data room did not provide it)",
                    "service_levels": "N/A (data room did not provide it)",
                    "termination_rights": "N/A (data room did not provide it)",
                    "assignment": "N/A (data room did not provide it)",
                    "change_of_control": "N/A (data room did not provide it)",
                    "exclusivity": "N/A (data room did not provide it)",
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Contract terms are taken only from executed documents that "
                        "were read — unread terms are not stated."
                    ),
                }],
                "substitutability": spec.get("substitutability") or [],
                "change_of_control": spec.get("change_of_control") or {
                    "transaction_triggers_flagged": False,
                    "consents": [
                        "Information request: change-of-control consents the "
                        "transaction would trigger"
                    ],
                    "notes": (
                        "Change-of-control consents that the transaction would "
                        "trigger are flagged."
                    ),
                    "source": "N/A (data room did not provide it)",
                },
                "evidence_status": spec.get("evidence_status") or {
                    "evidenced": [],
                    "assumed": [],
                    "sole_source_rule": (
                        "A named supplier is **not** automatically sole source."
                    ),
                    "resilience_reconcile": (
                        "Dependencies are reconciled with supply chain resilience "
                        "findings where available."
                    ),
                    "notes": "Legacy extract — mark evidenced vs assumed.",
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy vendor extract present; contracts and substitutability incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_supplier_dependence_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Supplier Dependence for {company} pending opened payables / contract packs."
        ),
        "spend_by_supplier": [],
        "operational_criticality": [],
        "contract_terms": [],
        "substitutability": [],
        "change_of_control": {
            "transaction_triggers_flagged": False,
            "consents": [
                "Information request: change-of-control consents the transaction would trigger"
            ],
            "notes": (
                "Change-of-control consents that the transaction would trigger are flagged."
            ),
            "source": "N/A (data room did not provide it)",
        },
        "evidence_status": {
            "evidenced": [],
            "assumed": [],
            "sole_source_rule": (
                "A named supplier is **not** automatically sole source."
            ),
            "resilience_reconcile": (
                "Dependencies are reconciled with supply chain resilience findings "
                "where available."
            ),
            "notes": "No packs resolved.",
        },
        "vendors": [],
        "concentration_flags": [],
        "dependency_notes": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No payables ledger or supplier contract packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_supplier_dependence_markdown(title, thin, sources=sources)


def _render_supply_chain_resilience(output: dict[str, Any], title: str) -> str:
    """Prompt-book Supply Chain Resilience — SPOF / capacity / continuity (no invest)."""
    from agetic_cdd_api.agent_document_supply_chain_resilience import (
        render_supply_chain_resilience_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Critical Path" in existing
        or "## 4. Continuity" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("critical_path")
        or spec.get("capacity_headroom")
        or spec.get("disruption_history")
        or spec.get("continuity_arrangements")
        or spec.get("logistics_metrics")
        or spec.get("resilience_notes")
    ):
        if not isinstance(spec.get("critical_path"), list):
            metrics = (
                spec.get("logistics_metrics")
                if isinstance(spec.get("logistics_metrics"), dict) else {}
            )
            notes = [
                n for n in (spec.get("resilience_notes") or [])
                if isinstance(n, str) and n.strip()
            ]
            milestones = [
                m for m in (spec.get("localization_milestones") or [])
                if isinstance(m, str) and m.strip()
            ]
            capacity_rows = []
            if metrics:
                bits = []
                if metrics.get("dio_days") is not None:
                    bits.append(f"DIO {metrics['dio_days']:g} days")
                if metrics.get("lead_time_days") is not None:
                    bits.append(f"Lead time {metrics['lead_time_days']:g} days")
                if metrics.get("stockout_actual_pct") is not None:
                    bits.append(f"Stockout {metrics['stockout_actual_pct']:g}%")
                capacity_rows.append({
                    "stage": "inventory / logistics",
                    "current_capacity": " · ".join(bits) if bits else (
                        "Information request: capacity at each stage"
                    ),
                    "utilization": "N/A (data room did not provide it)",
                    "headroom": "Information request: headroom vs current and planned volume",
                    "planned_volume": "Information request: planned volume",
                    "when_binds": "Information request: when the plan binds capacity",
                    "source": "(DOC: data room financials)",
                    "notes": (
                        "Capacity and headroom are stated against current and planned volume."
                    ),
                })
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Supply Chain Resilience from deep-dive extract."
                ),
                "critical_path": [{
                    "stage": "end-to-end",
                    "description": (
                        notes[0] if notes else
                        "Information request: critical path from input to delivered service "
                        "with SPOFs marked"
                    ),
                    "spof": "Unknown",
                    "spof_type": "none",
                    "supplier_or_asset": "N/A (data room did not provide it)",
                    "source": "(DOC: data room financials)" if notes else (
                        "N/A (data room did not provide it)"
                    ),
                    "notes": (
                        "Every point with a single supplier, single site or single asset "
                        "class is marked as a single point of failure."
                    ),
                }],
                "capacity_headroom": capacity_rows or [{
                    "stage": "end-to-end",
                    "current_capacity": "Information request: capacity at each stage",
                    "utilization": "N/A (data room did not provide it)",
                    "headroom": "Information request: headroom vs current and planned volume",
                    "planned_volume": "Information request: planned volume",
                    "when_binds": "Information request: when the plan binds capacity",
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Capacity and headroom are stated against current and planned volume."
                    ),
                }],
                "disruption_history": [{
                    "incident": "Information request: company disruption incidents",
                    "duration": "N/A (data room did not provide it)",
                    "impact": "N/A (data room did not provide it)",
                    "resolution": "N/A (data room did not provide it)",
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Disruption history uses the company's own incidents."
                    ),
                }],
                "continuity_arrangements": [
                    {
                        "arrangement": m,
                        "type": "other",
                        "tested_or_used": "Untested / not evidenced",
                        "source": "(DOC: data room financials)",
                        "notes": (
                            "Continuity arrangements record whether each has been used "
                            "or tested."
                        ),
                    }
                    for m in milestones[:4]
                ] or [{
                    "arrangement": (
                        "Information request: continuity arrangements (backup processors, "
                        "spare capacity, contractual priority)"
                    ),
                    "type": "other",
                    "tested_or_used": "Untested / not evidenced",
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Continuity arrangements record whether each has been used or tested."
                    ),
                }],
                "plausible_downsides": [{
                    "exposure": "Information request: material operational exposures",
                    "plausible_cost": "N/A (data room did not provide it)",
                    "duration": "N/A (data room did not provide it)",
                    "bounded": "No",
                    "unbounded_reason": (
                        "Information request: why downside cannot yet be bounded"
                    ),
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Plausible downside is bounded with cost and duration, or stated "
                        "as unbounded with why."
                    ),
                }],
                "supplier_reconcile": spec.get("supplier_reconcile") or {
                    "supplier_agent_present": False,
                    "aligned": [],
                    "conflicts": [],
                    "notes": (
                        "Every supplier fact is reconciled with the supplier agent."
                    ),
                    "source": "N/A (data room did not provide it)",
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy logistics extract present; critical-path SPOF map incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_supply_chain_resilience_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Supply Chain Resilience for {company} pending opened ops / logistics packs."
        ),
        "critical_path": [],
        "capacity_headroom": [],
        "disruption_history": [],
        "continuity_arrangements": [],
        "plausible_downsides": [],
        "supplier_reconcile": {
            "supplier_agent_present": False,
            "aligned": [],
            "conflicts": [],
            "notes": (
                "Every supplier fact is reconciled with the supplier agent — two agents "
                "must not report different terms for the same contract."
            ),
            "source": "N/A (data room did not provide it)",
        },
        "logistics_metrics": {},
        "localization_milestones": [],
        "resilience_notes": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No critical-path map, capacity headroom or disruption history was opened."
        ),
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_supply_chain_resilience_markdown(title, thin, sources=sources)


def _render_operational_risk(output: dict[str, Any], title: str) -> str:
    """Prompt-book Operational Risk — evidence register / size / controls (no invest)."""
    from agetic_cdd_api.agent_document_operational_risk import (
        render_operational_risk_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Evidence-Derived Risk Register" in existing
        or "## 3. Controls" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("risk_register")
        or spec.get("sized_risks")
        or spec.get("kpi_gaps")
        or spec.get("risk_items")
        or spec.get("integrity_notes")
    ):
        if not isinstance(spec.get("risk_register"), list):
            kpi_gaps = [
                g for g in (spec.get("kpi_gaps") or []) if isinstance(g, dict)
            ]
            risk_items = [
                r for r in (spec.get("risk_items") or []) if isinstance(r, dict)
            ]
            notes = [
                n for n in (spec.get("integrity_notes") or [])
                if isinstance(n, str) and n.strip()
            ]
            register = []
            for g in kpi_gaps[:6]:
                register.append({
                    "risk": f"{g.get('kpi') or 'KPI'} — {g.get('status') or 'gap'}",
                    "category": "operations",
                    "evidence": f"Legacy KPI gap: {g.get('kpi')}",
                    "record_type": "kpi",
                    "hypothesis": False,
                    "test_request": "",
                    "source": "(DOC: data room financials)",
                    "notes": (
                        "The risk register is drawn from records — not from a "
                        "generic risk taxonomy."
                    ),
                })
            for r in risk_items[:6]:
                register.append({
                    "risk": str(r.get("risk") or "Risk"),
                    "category": "operations",
                    "evidence": (
                        f"Legacy matrix: {r.get('likelihood') or '?'} / "
                        f"{r.get('impact') or '?'}"
                    ),
                    "record_type": "matrix",
                    "hypothesis": False,
                    "test_request": "",
                    "source": "(DOC: data room financials)",
                    "notes": (
                        "The risk register is drawn from records — not from a "
                        "generic risk taxonomy."
                    ),
                })
            if not register and notes:
                register.append({
                    "risk": notes[0][:140],
                    "category": "operations",
                    "evidence": notes[0],
                    "record_type": "note",
                    "hypothesis": False,
                    "test_request": "",
                    "source": "(DOC: data room financials)",
                    "notes": (
                        "The risk register is drawn from records — not from a "
                        "generic risk taxonomy."
                    ),
                })
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "Operational Risk from deep-dive extract."
                ),
                "risk_register": register or [{
                    "risk": (
                        "Information request: operational risks evidenced in "
                        "incidents / KPI / downtime records"
                    ),
                    "category": "operations",
                    "evidence": "N/A (data room did not provide it)",
                    "record_type": "none",
                    "hypothesis": False,
                    "test_request": "",
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "The risk register is drawn from records — not from a "
                        "generic risk taxonomy."
                    ),
                }],
                "sized_risks": spec.get("sized_risks") or [{
                    "risk": "Information request: evidenced operational risks to size",
                    "frequency": "N/A (data room did not provide it)",
                    "cost": "N/A (data room did not provide it)",
                    "ebitda_if_recurs": "N/A (data room did not provide it)",
                    "sized": "No",
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Each risk is sized: frequency, cost, and EBITDA if it recurs."
                    ),
                }],
                "controls": spec.get("controls") or [{
                    "risk": "Information request: risks needing control evidence",
                    "control": "N/A (data room did not provide it)",
                    "tested": "Untested / not evidenced",
                    "mitigation_status": (
                        "Not mitigation — control untested or not evidenced"
                    ),
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "An untested control is not mitigation."
                    ),
                }],
                "historical_vs_plan": spec.get("historical_vs_plan") or [],
                "priced_vs_noise": spec.get("priced_vs_noise") or [],
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy KPI / risk extract present; evidence-derived sizing incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_operational_risk_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Operational Risk for {company} pending opened ops / KPI packs."
        ),
        "risk_register": [],
        "sized_risks": [],
        "controls": [],
        "historical_vs_plan": [],
        "priced_vs_noise": [],
        "kpi_gaps": [],
        "risk_items": [],
        "integrity_notes": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No incident / KPI / downtime records opened to build an "
            "evidence-derived register."
        ),
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_operational_risk_markdown(title, thin, sources=sources)


def _render_cost_structure(output: dict[str, Any], title: str) -> str:
    """Prompt-book Cost Structure — GL map / behaviour / unit economics (no invest)."""
    from agetic_cdd_api.agent_document_cost_structure import (
        render_cost_structure_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Operating Category Map" in existing
        or "## 2. Fixed / Variable / Step" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("operating_categories")
        or spec.get("cost_classification")
        or spec.get("bom_components")
        or spec.get("cost_metrics")
        or spec.get("efficiency_notes")
    ):
        if not isinstance(spec.get("operating_categories"), list):
            # Thin upgrade from legacy BOM-only extract
            from agetic_cdd_api.agent_document_cost_structure import (
                _heuristic_cost_structure_spec,
            )

            company = str(
                output.get("target_company")
                or output.get("deal_name")
                or "Target"
            )
            seed_bits: list[str] = []
            for b in spec.get("bom_components") or []:
                if isinstance(b, dict) and b.get("category") is not None:
                    share = b.get("share_pct")
                    seed_bits.append(
                        f"{b['category']} — {share}%"
                        if share is not None
                        else str(b["category"])
                    )
            for k, v in (spec.get("cost_metrics") or {}).items():
                seed_bits.append(f"{k} {v}")
            for note in spec.get("efficiency_notes") or []:
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_cost_structure_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=list(output.get("sources") or []),
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            sources = output.get("sources") if isinstance(output.get("sources"), list) else None
            return render_cost_structure_markdown(title, merged, sources=sources)
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_cost_structure_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Cost Structure for {company} pending opened GL / COS packs."
        ),
        "operating_categories": [],
        "reconciliation": [],
        "cost_classification": [],
        "unit_economics": [],
        "inflation_exposure": [],
        "efficiency_opportunities": [],
        "missing_accounts": ["General ledger / trial balance detail"],
        "bom_components": [],
        "cost_metrics": {},
        "efficiency_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No GL / COS / BOM packs opened to map the cost base."
        ),
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_cost_structure_markdown(title, thin, sources=sources)


def _render_market_volume(output: dict[str, Any], title: str) -> str:
    """Prompt-book Market Volume & Growth — size + growth split (no invest verdict)."""
    from agetic_cdd_api.agent_document_market_volume import render_market_volume_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Bottom-Up" in existing
        or "## 5. Plan vs Market" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if spec.get("bottom_up") or spec.get("tam") or spec.get("sam") or spec.get("cagr_pct"):
        if not spec.get("bottom_up"):
            tam = spec.get("tam") if isinstance(spec.get("tam"), dict) else {}
            sam = spec.get("sam") if isinstance(spec.get("sam"), dict) else {}
            cagrs = [str(c) for c in (spec.get("cagr_pct") or [])[:3]]
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary") or "Market Volume & Growth from deep-dive extract."
                ),
                "bottom_up": {
                    "units": (
                        "; ".join(spec.get("unit_volume_notes") or [])[:200]
                        or "Information request: countable units"
                    ),
                    "capture_share": "Information request: capturable share",
                    "realised_price": "Information request: realised price per unit",
                    "arithmetic": "Information request: units × capture × price",
                    "bottom_up_size": (
                        f"SAM {sam.get('value')} {sam.get('scale') or ''}"
                        if sam.get("value") is not None
                        else "Information request: bottom-up size"
                    ),
                },
                "top_down": {
                    "published_figure": (
                        f"TAM {tam.get('value')} {tam.get('scale') or ''}"
                        if tam.get("value") is not None
                        else "N/A (data room did not provide it)"
                    ),
                    "published_perimeter": "Confirm against Market Definition",
                    "matches_ours": "unknown",
                    "use": "Cross-check only if perimeter matches",
                    "fallback": "Rely on bottom-up if no match",
                },
                "market_series": [],
                "market_growth_note": (
                    f"CAGR signals: {', '.join(cagrs)}%" if cagrs else "Information request: market growth"
                ),
                "company_growth": {
                    "geography_period_align": "Information request: same geography / period",
                    "historical_growth": "Information request: company growth from accounts",
                    "basis": "N/A (data room did not provide it)",
                },
                "growth_decomposition": [],
                "plan_vs_market": {
                    "plan_rate": "Information request: plan growth",
                    "market_rate": "Information request: market growth",
                    "multiple": "Information request: multiple",
                    "plain_english": "Cannot state multiple yet.",
                    "what_must_be_true": "N/A (data room did not provide it)",
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
                "quality_reliance_rationale": "Legacy ceiling extract present; bottom-up incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_market_volume_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Market Volume & Growth for {company} pending opened market / financial packs."
        ),
        "bottom_up": {
            "units": "N/A (data room did not provide it)",
            "capture_share": "N/A (data room did not provide it)",
            "realised_price": "N/A (data room did not provide it)",
            "arithmetic": "Information request: units × capture × price",
            "bottom_up_size": "Information request: bottom-up size",
        },
        "top_down": {
            "published_figure": "N/A (data room did not provide it)",
            "published_perimeter": "N/A (data room did not provide it)",
            "matches_ours": "No matching source",
            "use": "Rely on bottom-up",
            "fallback": "No matching top-down source",
        },
        "market_series": [],
        "market_growth_note": "Information request: market growth from endpoints",
        "company_growth": {
            "geography_period_align": "N/A (data room did not provide it)",
            "historical_growth": "Information request: company growth from accounts",
            "basis": "N/A (data room did not provide it)",
        },
        "growth_decomposition": [],
        "plan_vs_market": {
            "plan_rate": "Information request: plan rate",
            "market_rate": "Information request: market rate",
            "multiple": "Information request: multiple",
            "plain_english": "Cannot state multiple yet.",
            "what_must_be_true": "N/A (data room did not provide it)",
        },
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No market / financial packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_market_volume_markdown(title, thin, sources=sources)


def _render_market_definition(output: dict[str, Any], title: str) -> str:
    """Prompt-book Market Definition — competition perimeter (no invest verdict)."""
    from agetic_cdd_api.agent_document_market_definition import render_market_definition_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 7. Quality & Reliance" in existing
        or "## 1. Perimeter" in existing
        or "## 6. Approval Gate" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if spec.get("perimeter") or spec.get("addressable_market") or spec.get("market_framing"):
        if not spec.get("perimeter"):
            framing = [s for s in (spec.get("market_framing") or []) if isinstance(s, str)]
            geos = [s for s in (spec.get("geographies") or []) if isinstance(s, str)]
            segs = [s for s in (spec.get("segments") or []) if isinstance(s, str)]
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary") or "Market Definition from deep-dive extract."
                ),
                "perimeter": {
                    "service": framing[0] if framing else "Information request: service sold",
                    "customer_types": segs[0] if segs else "Information request: customer types",
                    "geography": "; ".join(geos[:3]) if geos else "Information request: geography",
                    "value_chain_stage": "Information request: value-chain stage",
                    "footprint_basis": "Use operating footprint, not an industry label.",
                },
                "double_count_streams": [],
                "exclusions": [],
                "addressable_market": {
                    "label": "Addressable",
                    "value": "Information request: addressable market from perimeter",
                    "basis": "N/A (data room did not provide it)",
                    "source": "N/A (data room did not provide it)",
                },
                "obtainable_market": {
                    "label": "Obtainable",
                    "value": "Information request: obtainable market from perimeter",
                    "basis": "N/A (data room did not provide it)",
                    "source": "N/A (data room did not provide it)",
                },
                "assumptions": [],
                "published_figures": [],
                "industry_context_note": (
                    "Broader industry figures are context, not the market."
                ),
                "approval_gate": {
                    "status": "pending_approval",
                    "blocks_downstream_market_agents": True,
                    "axes_evidenced": 0,
                    "note": "Approve perimeter before running other market agents.",
                },
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
                "quality_reliance_rationale": "Legacy extract present; perimeter axes incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_market_definition_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Market Definition for {company} pending opened market / commercial packs."
        ),
        "perimeter": {
            "service": "N/A (data room did not provide it)",
            "customer_types": "N/A (data room did not provide it)",
            "geography": "N/A (data room did not provide it)",
            "value_chain_stage": "N/A (data room did not provide it)",
            "footprint_basis": "Use operating footprint, not an industry label.",
        },
        "double_count_streams": [],
        "exclusions": [],
        "addressable_market": {
            "label": "Addressable",
            "value": "Information request: addressable market",
            "basis": "N/A (data room did not provide it)",
            "source": "N/A (data room did not provide it)",
        },
        "obtainable_market": {
            "label": "Obtainable",
            "value": "Information request: obtainable market",
            "basis": "N/A (data room did not provide it)",
            "source": "N/A (data room did not provide it)",
        },
        "assumptions": [],
        "published_figures": [],
        "industry_context_note": "Broader industry figures are context, not the market.",
        "approval_gate": {
            "status": "blocked",
            "blocks_downstream_market_agents": True,
            "axes_evidenced": 0,
            "note": "Perimeter incomplete — all other market agents stay blocked.",
        },
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No market packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_market_definition_markdown(title, thin, sources=sources)


def _render_strategic_direction(output: dict[str, Any], title: str) -> str:
    """Prompt-book Strategic Direction — growth plan vs evidence (no invest verdict)."""
    from agetic_cdd_api.agent_document_strategic_direction import render_strategic_direction_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 7. Quality & Reliance" in existing
        or "## 2. Bridge" in existing
        or "## 1. Three Cases" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("bridge")
        or spec.get("three_cases")
        or spec.get("initiatives")
        or spec.get("investment_drivers")
    ):
        if not spec.get("three_cases") and isinstance(spec.get("investment_drivers"), list):
            drivers = [d for d in spec["investment_drivers"] if isinstance(d, str)][:2]
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary") or "Strategic Direction from F-01 extract."
                ),
                "three_cases": {
                    "management_ambition": (
                        drivers[0] if drivers else "N/A (data room did not provide it)"
                    ),
                    "board_approved_budget": (
                        "Information request: board-approved budget vs management ambition"
                    ),
                    "independently_tested_case": (
                        "Only Supported assumptions belong in the tested case."
                    ),
                },
                "bridge": [],
                "plan_vs_actual": [],
                "initiatives": [
                    {
                        "initiative": _clean(d.split("—")[0].split("-")[0], 60),
                        "investment": "Information request: investment required",
                        "capacity_or_hiring": "Information request: capacity / hiring",
                        "dependencies": "N/A (data room did not provide it)",
                        "owner": "Information request: owner",
                        "timing": "N/A (data room did not provide it)",
                        "milestone": d,
                        "source": "(DOC: data room financials)",
                    }
                    for d in drivers
                ],
                "funding": {
                    "available_cash": "Information request: available cash / liquidity",
                    "debt_capacity": "Information request: debt capacity",
                    "stand_alone_growth_funding": (
                        "Information request: stand-alone funding for the plan (ex-buyer)"
                    ),
                    "buyer_contributed": (
                        "Keep buyer contributions separate from stand-alone growth."
                    ),
                    "reconciliation": "N/A (data room did not provide it)",
                },
                "supported_assumptions": [],
                "untested_assumptions": [
                    {
                        "assumption": "Driver-level bridge and funding reconciliation",
                        "basis": "F-01 thesis present; bridge / funding not yet tested",
                    }
                ],
                "strategy_read": str(output.get("summary") or ""),
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
                "quality_reliance_rationale": (
                    "F-01 thesis present; do not assign high confidence while funding "
                    "or capacity assumptions remain untested."
                ),
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_strategic_direction_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Strategic Direction for {company} pending opened strategy / financial packs."
        ),
        "three_cases": {
            "management_ambition": "N/A (data room did not provide it)",
            "board_approved_budget": "N/A (data room did not provide it)",
            "independently_tested_case": "N/A (data room did not provide it)",
        },
        "bridge": [],
        "plan_vs_actual": [],
        "initiatives": [],
        "funding": {
            "available_cash": "Information request: available cash / liquidity",
            "debt_capacity": "Information request: debt capacity",
            "stand_alone_growth_funding": "Information request: stand-alone funding",
            "buyer_contributed": "Keep buyer contributions separate.",
            "reconciliation": "N/A (data room did not provide it)",
        },
        "supported_assumptions": [],
        "untested_assumptions": [
            {
                "assumption": "Growth plan bridge, delivery history, and funding",
                "basis": "Not yet composed from VDR",
            }
        ],
        "strategy_read": "Insufficient opened sources to test the growth plan.",
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No strategy / financial packs resolved.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_strategic_direction_markdown(title, thin, sources=sources)


def _render_management_quality(output: dict[str, Any], title: str) -> str:
    """Prompt-book Management Quality — team vs plan (no invest verdict)."""
    from agetic_cdd_api.agent_document_management_quality import render_management_quality_markdown

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 2. Executive & Senior Operating Roster" in existing
        or "## 5. Vacancies, Capability Gaps" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("executives")
        or spec.get("key_persons")
        or spec.get("confirmed_vacancies") is not None
        or spec.get("c_suite")
    ):
        if not spec.get("executives") and isinstance(spec.get("c_suite"), list):
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary") or "Management assessment from F-06 extract."
                ),
                "sources_resolved": [
                    {"pointer": s, "status": "opened", "note": "From agent output sources"}
                    for s in (output.get("sources") or [])[:8]
                    if isinstance(s, str) and not str(s).startswith("library/")
                ],
                "executives": [
                    {
                        "name": r.get("name"),
                        "role": r.get("role"),
                        "tenure": "N/A (data room did not provide it)",
                        "remit": r.get("role"),
                        "prior_delivery": "N/A (data room did not provide it)",
                        "vs_target": "N/A (data room did not provide it)",
                        "source": "(DOC: corporate / HR pack)",
                    }
                    for r in spec["c_suite"]
                    if isinstance(r, dict) and r.get("name")
                ],
                "key_persons": [],
                "succession": [],
                "board": [],
                "confirmed_vacancies": [],
                "capability_gaps": [
                    {
                        "item": g,
                        "evidence": g,
                        "hiring_cost_eligible": "yes — demonstrated capability gap",
                        "source": "(DOC: corporate / HR pack)",
                    }
                    for g in (spec.get("succession_gaps") or [])[:4]
                    if isinstance(g, str)
                ],
                "information_gaps": [
                    {
                        "item": "Full biographies / tenure / delivery vs target",
                        "evidence": "Not fully populated — information gap, not a vacancy",
                        "hiring_cost_eligible": "no — information gap only",
                        "source": "N/A (data room did not provide it)",
                    }
                ],
                "proposed_hires": [],
                "assessment_read": str(output.get("summary") or ""),
                "quality_verdict": "PASS",
                "reliance_verdict": "LIMITED",
                "quality_reliance_rationale": "F-06 roster present; biographies incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_management_quality_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Management assessment for {company} pending opened biographies / org charts."
        ),
        "sources_resolved": [],
        "executives": [],
        "key_persons": [],
        "succession": [],
        "board": [],
        "confirmed_vacancies": [],
        "capability_gaps": [],
        "information_gaps": [
            {
                "item": "Executive biographies and succession map",
                "evidence": "Not yet composed from VDR",
                "hiring_cost_eligible": "no — information gap only",
                "source": "N/A (data room did not provide it)",
            }
        ],
        "proposed_hires": [],
        "assessment_read": "Insufficient opened sources to assess the team against the plan.",
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No executives resolved from opened packs.",
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_management_quality_markdown(title, thin, sources=sources)


def _render_ip_and_technology(output: dict[str, Any], title: str) -> str:
    """Prompt-book IP & Technology — owned vs rented systems (no invest)."""
    from agetic_cdd_api.agent_document_ip_and_technology import (
        render_ip_and_technology_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Technology Map" in existing
        or "## 2. Owned IP" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if (
        spec.get("technology_map")
        or spec.get("ownership_separation")
        or spec.get("patents")
        or spec.get("core_tech")
        or spec.get("architecture_notes")
    ):
        if not isinstance(spec.get("technology_map"), list):
            patents = [
                p for p in (spec.get("patents") or [])
                if isinstance(p, str) and p.strip()
            ]
            core = [
                c for c in (spec.get("core_tech") or [])
                if isinstance(c, str) and c.strip()
            ]
            notes = [
                n for n in (spec.get("architecture_notes") or [])
                if isinstance(n, str) and n.strip()
            ]
            ownership = [
                {
                    "asset": p,
                    "classification": "owned_ip",
                    "owner": "Information request: registered owner from IP register",
                    "status": "Information request: registration status",
                    "jurisdiction": "Information request: jurisdiction",
                    "register_verified": (
                        "Partial — legacy patent metric; confirm on register"
                    ),
                    "evidence": p,
                    "source": "(DOC: data room financials)",
                    "notes": (
                        "Registrations, ownership and assignments are taken from the "
                        "register or certificates — not from assertion."
                    ),
                }
                for p in patents[:6]
                if "no patent" not in p.lower()
            ]
            for c in core[:4]:
                ownership.append({
                    "asset": c,
                    "classification": "licensed_technology",
                    "owner": "Information request: system owner",
                    "status": "N/A (data room did not provide it)",
                    "jurisdiction": "N/A (data room did not provide it)",
                    "register_verified": (
                        "No — stack row; not a registration certificate"
                    ),
                    "evidence": c,
                    "source": "(DOC: data room financials)",
                    "notes": (
                        "Using technology is not owning intellectual property."
                    ),
                })
            spec = {
                **spec,
                "insight_snapshot": str(
                    output.get("summary")
                    or "IP & Technology from foundation extract."
                ),
                "technology_map": [{
                    "category": "proprietary method",
                    "applies": "Yes" if core or notes else "No",
                    "system_or_method": (
                        (core[0] if core else notes[0]) if (core or notes)
                        else "N/A (data room did not provide it)"
                    ),
                    "owner": "Information request: who owns the system",
                    "omit_reason": (
                        "" if (core or notes)
                        else (
                            "No evidence this business runs on proprietary method "
                            "in opened packs."
                        )
                    ),
                    "source": (
                        "(DOC: data room financials)" if (core or notes)
                        else "N/A (data room did not provide it)"
                    ),
                    "notes": (
                        "Technology is mapped to how this business actually runs."
                    ),
                }],
                "ownership_separation": ownership or [{
                    "asset": (
                        "Information request: registered IP / licensed systems"
                    ),
                    "classification": "unknown",
                    "owner": "N/A (data room did not provide it)",
                    "status": "N/A (data room did not provide it)",
                    "jurisdiction": "N/A (data room did not provide it)",
                    "register_verified": "No",
                    "evidence": "N/A (data room did not provide it)",
                    "source": "N/A (data room did not provide it)",
                    "notes": (
                        "Registrations are taken from the register — not from assertion."
                    ),
                }],
                "change_of_control": [],
                "system_fitness": [],
                "upgrade_costs": [],
                "ip_advantage_reconcile": {
                    "other_agent_claims": [],
                    "evidenced": [],
                    "contradicted": [],
                    "notes": (
                        "Using technology is not owning intellectual property."
                    ),
                    "source": "N/A (data room did not provide it)",
                },
                "quality_verdict": spec.get("quality_verdict") or "PASS",
                "reliance_verdict": spec.get("reliance_verdict") or "LIMITED",
                "quality_reliance_rationale": spec.get("quality_reliance_rationale")
                or "Legacy F-IP extract present; register verification incomplete.",
            }
        sources = output.get("sources") if isinstance(output.get("sources"), list) else None
        return render_ip_and_technology_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"IP & Technology for {company} pending opened technical / IP packs."
        ),
        "technology_map": [],
        "ownership_separation": [],
        "change_of_control": [],
        "system_fitness": [],
        "upgrade_costs": [],
        "ip_advantage_reconcile": {
            "other_agent_claims": [],
            "evidenced": [],
            "contradicted": [],
            "notes": "Using technology is not owning intellectual property.",
            "source": "N/A (data room did not provide it)",
        },
        "patents": [],
        "core_tech": [],
        "architecture_notes": [],
        "quality_verdict": "PASS",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No technology map or register-backed IP evidence was opened."
        ),
        "primary_sources": output.get("sources") or output.get("primary_sources") or [],
    }
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    return render_ip_and_technology_markdown(title, thin, sources=sources)


def _render_regulatory_compliance(output: dict[str, Any], title: str) -> str:
    """Prompt-book Regulatory Compliance — jurisdiction-real permits & obligations."""
    from agetic_cdd_api.agent_document_regulatory_compliance import (
        render_regulatory_compliance_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Applicable Laws" in existing
        or "## 2. Permit & Licence Register" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("permit_register")
        or spec.get("obligations")
        or spec.get("litigation_register")
        or spec.get("risks")
        or spec.get("penalty_notes")
    ):
        if not isinstance(spec.get("permit_register"), list):
            from agetic_cdd_api.agent_document_regulatory_compliance import (
                _heuristic_regulatory_compliance_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            for item in spec.get("risks") or []:
                if isinstance(item, dict) and item.get("clause"):
                    seed_bits.append(str(item["clause"]))
            for note in list(spec.get("penalty_notes") or []) + list(
                spec.get("data_handling") or []
            ) + list(spec.get("restricted_activities") or []):
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_regulatory_compliance_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                geography=str(output.get("geography") or "") or None,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_regulatory_compliance_markdown(
                title, merged, sources=sources
            )
        return render_regulatory_compliance_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Regulatory Compliance for {company} pending opened legal / permit packs."
        ),
        "jurisdiction": "N/A (data room did not provide it)",
        "applicable_regime": [],
        "permit_register": [],
        "obligations": [],
        "litigation_register": [],
        "transaction_implications": [],
        "risks": [],
        "restricted_activities": [],
        "data_handling": [],
        "penalty_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No jurisdiction-bound permits, tested obligations, or litigation register opened."
        ),
        "primary_sources": sources,
    }
    return render_regulatory_compliance_markdown(title, thin, sources=sources)


def _render_esg_and_sustainability(output: dict[str, Any], title: str) -> str:
    """Prompt-book ESG & Sustainability — material ESG with consequence (no invest)."""
    from agetic_cdd_api.agent_document_esg_and_sustainability import (
        render_esg_and_sustainability_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Material Topics" in existing
        or "## 2. Product Impact" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("material_topics")
        or spec.get("measured_metrics")
        or spec.get("themes")
        or spec.get("environment_flags")
        or spec.get("labour_flags")
    ):
        if not isinstance(spec.get("material_topics"), list):
            from agetic_cdd_api.agent_document_esg_and_sustainability import (
                _heuristic_esg_and_sustainability_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            for note in list(spec.get("themes") or []) + list(
                spec.get("labour_flags") or []
            ) + list(spec.get("environment_flags") or []):
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_esg_and_sustainability_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                geography=str(output.get("geography") or "") or None,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_esg_and_sustainability_markdown(
                title, merged, sources=sources
            )
        return render_esg_and_sustainability_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"ESG & Sustainability for {company} pending opened ESG / HR packs."
        ),
        "jurisdiction": "N/A (data room did not provide it)",
        "sector": "N/A (data room did not provide it)",
        "material_topics": [],
        "product_vs_footprint": [],
        "measured_metrics": [],
        "workforce_safety": [],
        "consequences": [],
        "themes": [],
        "labour_flags": [],
        "environment_flags": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No material ESG topics or measured metrics opened from VDR yet."
        ),
        "primary_sources": sources,
    }
    return render_esg_and_sustainability_markdown(title, thin, sources=sources)


def _render_generic(output: dict[str, Any], title: str) -> str:
    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    parts = [
        f"# {title}\n\n",
        _insight_block(str(output.get("summary") or f"Agent output for {company}.")),
    ]
    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    if spec:
        rows = _spec_overview_rows(spec)
        if rows:
            parts.append("## Structured Overview\n\n")
            parts.append(_md_table(["Parameter", "Details"], rows))
    findings = _findings_bullets(output.get("findings"))
    if findings:
        parts.append("## Key Findings\n\n")
        parts.append(findings)
    status = output.get("status")
    if status:
        parts.append(f"*Agent status:* `{status}`\n\n")
    parts.append(_sources_section(output.get("sources") or output.get("primary_sources")))
    return "".join(parts)


def _render_historical_performance(output: dict[str, Any], title: str) -> str:
    """Prompt-book Historical Performance — shared P&L facts (no invest)."""
    from agetic_cdd_api.agent_document_historical_performance import (
        render_historical_performance_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Financial Record" in existing
        or "## 3. Accounts vs CIM" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("period_facts")
        or spec.get("pl_lines")
        or spec.get("performance_metrics")
        or spec.get("bridge_notes")
    ):
        # Thin legacy → ensure composer keys exist for render
        if not isinstance(spec.get("period_facts"), list):
            thin = {
                "insight_snapshot": output.get("summary") or "",
                "trend_headline": "",
                "period_facts": [],
                "growth_and_margins": [],
                "accounts_vs_cim": [],
                "seasonality": [],
                "comparability_distortions": [],
                "pl_lines": spec.get("pl_lines") or [],
                "performance_metrics": spec.get("performance_metrics") or {},
                "bridge_notes": spec.get("bridge_notes") or [],
                "quality_verdict": "REWORK",
                "reliance_verdict": "LIMITED",
                "quality_reliance_rationale": (
                    "Legacy Adjusted EBITDA Bridge fields only — re-run composer "
                    "for full prompt-book sections."
                ),
                "primary_sources": sources,
            }
            # Lift pl_lines into period_facts for display
            for row in thin["pl_lines"]:
                if not isinstance(row, dict):
                    continue
                item = str(row.get("line_item") or "")
                unit = str(row.get("unit") or "INR Cr")
                for key, period in (
                    ("fy2023_value", "FY2023"),
                    ("fy2024_value", "FY2024E"),
                ):
                    if row.get(key) is None:
                        continue
                    thin["period_facts"].append({
                        "line_item": item,
                        "period": period,
                        "period_type": "forecast" if period.endswith("E") else "actual",
                        "value": row[key],
                        "unit": unit,
                        "basis": "accounting_records",
                        "source": "(DOC: data room financials)",
                        "location": f"Legacy · {period}",
                        "notes": "",
                    })
            return render_historical_performance_markdown(title, thin, sources=sources)
        return render_historical_performance_markdown(title, spec, sources=sources)

    thin = {
        "insight_snapshot": output.get("summary") or "",
        "trend_headline": "",
        "period_facts": [],
        "growth_and_margins": [],
        "accounts_vs_cim": [],
        "seasonality": [],
        "comparability_distortions": [],
        "pl_lines": [],
        "performance_metrics": {},
        "bridge_notes": list(output.get("findings") or [])[:4],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No accounting-record P&L extracted yet.",
        "primary_sources": sources,
    }
    return render_historical_performance_markdown(title, thin, sources=sources)


def _render_revenue_quality(output: dict[str, Any], title: str) -> str:
    """Prompt-book Revenue Quality — durability split / bridge (no invest)."""
    from agetic_cdd_api.agent_document_revenue_quality import (
        render_revenue_quality_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Revenue Split" in existing
        or "## 3. Revenue Bridge" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("revenue_split")
        or spec.get("retention_metrics")
        or spec.get("revenue_mix")
        or spec.get("quality_flags")
    ):
        if not isinstance(spec.get("revenue_split"), list):
            thin = {
                "insight_snapshot": output.get("summary") or "",
                "revenue_split": [],
                "contract_terms": [],
                "revenue_bridge": [],
                "recognition_cutoff": [],
                "non_repeating": [],
                "retention_metrics": spec.get("retention_metrics") or {},
                "revenue_mix": spec.get("revenue_mix") or {},
                "quality_flags": spec.get("quality_flags") or [],
                "quality_notes": spec.get("quality_notes") or [],
                "quality_verdict": "REWORK",
                "reliance_verdict": "LIMITED",
                "quality_reliance_rationale": (
                    "Legacy Revenue Persistence fields only — re-run composer "
                    "for full prompt-book sections."
                ),
                "primary_sources": sources,
            }
            return render_revenue_quality_markdown(title, thin, sources=sources)
        return render_revenue_quality_markdown(title, spec, sources=sources)

    thin = {
        "insight_snapshot": output.get("summary") or "",
        "revenue_split": [],
        "contract_terms": [],
        "revenue_bridge": [],
        "recognition_cutoff": [],
        "non_repeating": [],
        "retention_metrics": {},
        "revenue_mix": {},
        "quality_flags": list(output.get("findings") or [])[:4],
        "quality_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No revenue-durability split extracted yet.",
        "primary_sources": sources,
    }
    return render_revenue_quality_markdown(title, thin, sources=sources)


def _render_capital_structure(output: dict[str, Any], title: str) -> str:
    """Prompt-book Capital Structure — facilities / cash / net debt (no invest)."""
    from agetic_cdd_api.agent_document_capital_structure import (
        render_capital_structure_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Facility Schedule" in existing
        or "## 5. Net Debt Bridge" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("facilities")
        or spec.get("debt_instruments")
        or spec.get("debt_total_usd_m") is not None
        or spec.get("leverage_ratios")
        or spec.get("capital_notes")
    ):
        if not isinstance(spec.get("facilities"), list):
            from agetic_cdd_api.agent_document_capital_structure import (
                _heuristic_capital_structure_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            for b in spec.get("debt_instruments") or []:
                if isinstance(b, dict) and b.get("name") is not None:
                    amt = b.get("amount_usd_m")
                    seed_bits.append(
                        f"{b['name']} — USD {amt}M" if amt is not None else str(b["name"])
                    )
            if spec.get("debt_total_usd_m") is not None:
                seed_bits.append(f"Total debt USD {spec['debt_total_usd_m']}M")
            for note in spec.get("capital_notes") or []:
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_capital_structure_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_capital_structure_markdown(title, merged, sources=sources)
        return render_capital_structure_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Capital Structure for {company} pending opened loan / cash packs."
        ),
        "facilities": [],
        "balance_sheet_reconciliation": [],
        "debt_like_items": [],
        "cash_split": [],
        "change_of_control": [],
        "net_debt_bridge": [],
        "schedule_complete": False,
        "schedule_gaps": ["No facilities scheduled from loan documents / ledger"],
        "debt_instruments": [],
        "debt_total_usd_m": None,
        "leverage_ratios": {
            "leverage_withheld": "Not calculated — facility schedule incomplete."
        },
        "dcf_metrics": {},
        "capital_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No facility schedule opened — leverage not calculated from an incomplete schedule."
        ),
        "primary_sources": sources,
    }
    return render_capital_structure_markdown(title, thin, sources=sources)


def _render_market_risk(output: dict[str, Any], title: str) -> str:
    """Prompt-book Market Risk — external risks sized to company numbers (no invest)."""
    from agetic_cdd_api.agent_document_market_risk import (
        render_market_risk_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. External Risks" in existing
        or "## 3. Bounded Downside" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("external_risks")
        or spec.get("market_risk_items")
        or spec.get("downside_cases")
        or spec.get("price_vs_structure")
    ):
        if not isinstance(spec.get("external_risks"), list):
            from agetic_cdd_api.agent_document_market_risk import (
                _heuristic_market_risk_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            for item in spec.get("market_risk_items") or []:
                if isinstance(item, dict) and item.get("risk"):
                    seed_bits.append(
                        f"{item['risk']} — probability {item.get('probability')} "
                        f"impact {item.get('impact')}"
                    )
            for reg in spec.get("regulatory_items") or []:
                if isinstance(reg, dict) and reg.get("area"):
                    seed_bits.append(
                        f"{reg['area']} — {reg.get('status')} ({reg.get('risk_level')})"
                    )
            for lit in (spec.get("litigation_exposures") or [])[:6]:
                if isinstance(lit, str) and lit.strip():
                    seed_bits.append(lit.strip())
            for note in spec.get("risk_notes") or []:
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_market_risk_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_market_risk_markdown(title, merged, sources=sources)
        return render_market_risk_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Market Risk for {company} pending opened market / legal / strategy packs."
        ),
        "external_risks": [],
        "downside_cases": [],
        "early_warnings": [],
        "price_vs_structure": [],
        "unsized_risks": [],
        "market_risk_items": [],
        "regulatory_items": [],
        "litigation_exposures": [],
        "risk_flags": [],
        "risk_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No external risks sized from VDR evidence yet.",
        "primary_sources": sources,
    }
    return render_market_risk_markdown(title, thin, sources=sources)


def _render_internal_risk(output: dict[str, Any], title: str) -> str:
    """Prompt-book Internal Risk — day-one inherited issues (no invest)."""
    from agetic_cdd_api.agent_document_internal_risk import (
        render_internal_risk_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Key-Person" in existing
        or "## 2. Financial Strain" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("key_person_exposure")
        or spec.get("financial_strain")
        or spec.get("observed_weaknesses")
        or spec.get("tech_components")
        or spec.get("technical_risks")
    ):
        if not isinstance(spec.get("key_person_exposure"), list):
            from agetic_cdd_api.agent_document_internal_risk import (
                _heuristic_internal_risk_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            for tc in spec.get("tech_components") or []:
                if isinstance(tc, dict) and tc.get("component"):
                    seed_bits.append(
                        f"{tc['component']} maturity {tc.get('maturity_score')} — "
                        f"{tc.get('key_risk') or ''}"
                    )
            for note in list(spec.get("technical_risks") or []) + list(
                spec.get("scalability_notes") or []
            ):
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_internal_risk_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_internal_risk_markdown(title, merged, sources=sources)
        return render_internal_risk_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Internal Risk for {company} pending management / capital / control packs."
        ),
        "key_person_exposure": [],
        "financial_strain": [],
        "observed_weaknesses": [],
        "control_testing": [],
        "remediation": [],
        "ranked_effects": [],
        "tech_components": [],
        "technical_risks": [],
        "scalability_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No key-person / strain / control evidence sized from VDR yet."
        ),
        "primary_sources": sources,
    }
    return render_internal_risk_markdown(title, thin, sources=sources)


def _render_growth_opportunities(output: dict[str, Any], title: str) -> str:
    """Prompt-book Growth Opportunities — costed upside options (no invest)."""
    from agetic_cdd_api.agent_document_growth_opportunities import (
        render_growth_opportunities_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 6. Quality & Reliance" in existing
        or "## 1. Available Options" in existing
        or "## 2. Sized Revenue" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("options")
        or spec.get("growth_levers")
        or spec.get("opportunity_notes")
    ):
        if not isinstance(spec.get("options"), list):
            from agetic_cdd_api.agent_document_growth_opportunities import (
                _heuristic_growth_opportunities_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            for lev in spec.get("growth_levers") or []:
                if isinstance(lev, dict) and lev.get("name"):
                    seed_bits.append(f"{lev['name']}. {lev.get('note') or ''}")
                elif isinstance(lev, str):
                    seed_bits.append(lev)
            for note in spec.get("opportunity_notes") or []:
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_growth_opportunities_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                sector=str(output.get("sector") or "") or None,
                geography=str(output.get("geography") or "") or None,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_growth_opportunities_markdown(
                title, merged, sources=sources
            )
        return render_growth_opportunities_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Growth Opportunities for {company} pending opened growth packs."
        ),
        "sector": "N/A (data room did not provide it)",
        "geography": "N/A (data room did not provide it)",
        "options": [],
        "rejected_options": [],
        "growth_levers": [],
        "market_growth": {},
        "milestone_targets": [],
        "opportunity_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No growth options sized from VDR yet."
        ),
        "primary_sources": sources,
    }
    return render_growth_opportunities_markdown(title, thin, sources=sources)


def _render_synergies(output: dict[str, Any], title: str) -> str:
    """Prompt-book Synergies — buyer-specific net of cost to achieve (no invest)."""
    from agetic_cdd_api.agent_document_synergies import (
        render_synergies_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 7. Quality & Reliance" in existing
        or "## 1. Named Buyer" in existing
        or "## 2. Hypotheses Only" in existing
        or "## 2. Cost Synergies" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("buyer")
        or spec.get("hypotheses")
        or spec.get("cost_synergies")
        or spec.get("synergy_themes")
    ):
        if not isinstance(spec.get("buyer"), dict):
            from agetic_cdd_api.agent_document_synergies import (
                _heuristic_synergies_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            for theme in spec.get("synergy_themes") or []:
                if isinstance(theme, str) and theme.strip():
                    seed_bits.append(theme.strip())
            for note in spec.get("synergy_notes") or []:
                if isinstance(note, str) and note.strip():
                    seed_bits.append(note.strip())
            thin_built = _heuristic_synergies_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                sector=str(output.get("sector") or "") or None,
                geography=str(output.get("geography") or "") or None,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_synergies_markdown(title, merged, sources=sources)
        return render_synergies_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Synergies for {company}: no named acquirer — cannot underwrite."
        ),
        "sector": "N/A (data room did not provide it)",
        "geography": "N/A (data room did not provide it)",
        "buyer": {
            "named": False,
            "buyer_name": None,
            "what_they_bring": "No named acquirer — synergies cannot be underwritten",
        },
        "underwritable": False,
        "cannot_underwrite_reason": (
            "No named acquirer — synergies cannot be underwritten; no number produced"
        ),
        "hypotheses": [],
        "cost_synergies": [],
        "revenue_synergies": [],
        "cost_to_achieve": [],
        "phasing": [],
        "run_rate": "Not produced — synergies cannot be underwritten",
        "year_one_realised": "Not produced — synergies cannot be underwritten",
        "seller_share": {
            "seller_share_expectation": "Not applicable — synergies cannot be underwritten",
        },
        "stand_alone_separation": {
            "in_standalone_valuation": False,
            "layer": "Separate buyer-synergy layer — committee can remove",
        },
        "synergy_themes": [],
        "value_milestones": [],
        "synergy_notes": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": "No named acquirer and no hypothesis themes yet.",
        "primary_sources": sources,
    }
    return render_synergies_markdown(title, thin, sources=sources)


def _render_swot_analysis(output: dict[str, Any], title: str) -> str:
    """Prompt-book SWOT — synthesis of upstream findings (no new facts)."""
    from agetic_cdd_api.agent_document_swot_analysis import (
        render_swot_analysis_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 1. Demonstrated Strengths" in existing
        or "## 5. Information Gaps" in existing
        or "## Open Blockers" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("strengths_structured")
        or spec.get("weaknesses_structured")
        or spec.get("information_gaps")
        or spec.get("upstream_agents_used")
    ):
        return render_swot_analysis_markdown(title, spec, sources=sources)

    # Thin / legacy-only payload: rebuild heuristic from empty prior
    from agetic_cdd_api.agent_document_swot_analysis import (
        _heuristic_swot_analysis_spec,
    )

    company = str(
        output.get("target_company")
        or output.get("deal_name")
        or "Target"
    )
    thin = _heuristic_swot_analysis_spec(
        company=company,
        prior_agents={},
        sources=sources,
        legacy_spec=spec,
    )
    merged = {**spec, **thin}
    return render_swot_analysis_markdown(title, merged, sources=sources)


def _render_recommendation(output: dict[str, Any], title: str) -> str:
    """Prompt-book Recommendations — findings converted to deal actions."""
    from agetic_cdd_api.agent_document_recommendation import (
        render_recommendation_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 1. Price Adjustments" in existing
        or "## 4. Conditions Precedent" in existing
        or "## 6. Still Open" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("price_actions")
        or spec.get("conditions_precedent_structured")
        or spec.get("recommendations")
        or spec.get("upstream_agents_used")
    ):
        return render_recommendation_markdown(title, spec, sources=sources)

    from agetic_cdd_api.agent_document_recommendation import (
        _heuristic_recommendation_spec,
    )

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = _heuristic_recommendation_spec(
        company=company,
        prior_agents={},
        sources=sources,
        legacy_spec=spec,
    )
    merged = {**spec, **thin}
    return render_recommendation_markdown(title, merged, sources=sources)


def _render_ic_synthesis(output: dict[str, Any], title: str) -> str:
    """Prompt-book Executive Summary — committee page from the fact register."""
    from agetic_cdd_api.agent_document_ic_synthesis import (
        render_ic_synthesis_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 1. Opening" in existing
        or "## 3. What the Case Depends On" in existing
        or "## 5. Recommendation (Proportionate)" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("opening_lines")
        or spec.get("case_depends_on")
        or spec.get("recommendation")
        or spec.get("upstream_agents_used")
    ):
        return render_ic_synthesis_markdown(title, spec, sources=sources)

    from agetic_cdd_api.agent_document_ic_synthesis import (
        _heuristic_ic_synthesis_spec,
    )

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = _heuristic_ic_synthesis_spec(
        company=company,
        prior_agents={},
        sources=sources,
        legacy_spec=spec,
    )
    merged = {**spec, **thin}
    return render_ic_synthesis_markdown(title, merged, sources=sources)


def _render_valuation_modeling(output: dict[str, Any], title: str) -> str:
    """Prompt-book Valuation Model — one earnings basis, three methods (no invest)."""
    from agetic_cdd_api.agent_document_valuation_modeling import (
        render_valuation_modeling_markdown,
    )

    existing = output.get("document")
    if isinstance(existing, str) and (
        "## 1. Declared Earnings Basis" in existing
        or "## 5. Method Reconciliation" in existing
        or "## 6. Quality & Reliance" in existing
        or "# Sensitivity Analysis" in existing
        or "# Final Valuation Range" in existing
    ):
        return existing if existing.endswith("\n") else existing + "\n"

    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    sources = [
        s for s in (output.get("sources") or spec.get("primary_sources") or [])
        if isinstance(s, str) and s.strip()
    ]
    if (
        spec.get("earnings_basis")
        or spec.get("comparable_companies")
        or spec.get("precedent_transactions")
        or spec.get("dcf_view")
        or spec.get("football_field")
        or spec.get("dcf")
    ):
        if not isinstance(spec.get("earnings_basis"), dict):
            from agetic_cdd_api.agent_document_valuation_modeling import (
                _heuristic_valuation_modeling_spec,
            )

            company = str(
                output.get("target_company") or output.get("deal_name") or "Target"
            )
            seed_bits: list[str] = []
            dcf = spec.get("dcf") if isinstance(spec.get("dcf"), dict) else {}
            if dcf.get("wacc_pct") is not None:
                seed_bits.append(f"WACC (Base) {dcf['wacc_pct']}%")
            if dcf.get("enterprise_value_usd_b") is not None:
                seed_bits.append(
                    f"Enterprise Value (DCF) {dcf['enterprise_value_usd_b']}B"
                )
            for flag in spec.get("valuation_flags") or []:
                if isinstance(flag, str) and flag.strip():
                    seed_bits.append(flag.strip())
            thin_built = _heuristic_valuation_modeling_spec(
                company=company,
                corpus="\n".join(seed_bits),
                sources=sources,
                legacy_spec=spec,
            )
            merged = {**spec, **thin_built}
            return render_valuation_modeling_markdown(title, merged, sources=sources)
        return render_valuation_modeling_markdown(title, spec, sources=sources)

    company = str(output.get("target_company") or output.get("deal_name") or "Target")
    thin = {
        "insight_snapshot": str(
            output.get("summary")
            or f"Valuation Model for {company} pending earnings basis and method packs."
        ),
        "earnings_basis": {},
        "comparable_companies": [],
        "comps_summary": {},
        "precedent_transactions": [],
        "precedents_summary": {},
        "dcf_view": {},
        "method_reconciliation": [],
        "dcf": {},
        "football_field": [],
        "valuation_flags": [],
        "quality_verdict": "REWORK",
        "reliance_verdict": "BLOCKED",
        "quality_reliance_rationale": (
            "No declared earnings figure — methods cannot be reconciled on one basis."
        ),
        "primary_sources": sources,
    }
    return render_valuation_modeling_markdown(title, thin, sources=sources)


def render_agent_document(agent_key: str, output: dict[str, Any] | None) -> str:
    """Build markdown for an agent document from its pipeline output JSON."""
    data = output if isinstance(output, dict) else {}
    title = _agent_title(data, agent_key)
    if agent_key == "deal_context_and_objectives":
        return _render_deal_context(data, title)
    if agent_key == "scope_and_methodology":
        return _render_scope_methodology(data, title)
    if agent_key == "company_background":
        return _render_company_background(data, title)
    if agent_key == "management_quality":
        return _render_management_quality(data, title)
    if agent_key == "ip_and_technology":
        return _render_ip_and_technology(data, title)
    if agent_key == "regulatory_compliance":
        return _render_regulatory_compliance(data, title)
    if agent_key == "esg_and_sustainability":
        return _render_esg_and_sustainability(data, title)
    if agent_key == "strategic_direction":
        return _render_strategic_direction(data, title)
    if agent_key == "market_definition":
        return _render_market_definition(data, title)
    if agent_key == "market_volume_and_growth":
        return _render_market_volume(data, title)
    if agent_key == "market_pricing":
        return _render_market_pricing(data, title)
    if agent_key == "demand_drivers":
        return _render_demand_drivers(data, title)
    if agent_key == "competitor_identification":
        return _render_competitor_identification(data, title)
    if agent_key == "competitive_differentiation":
        return _render_competitive_differentiation(data, title)
    if agent_key == "market_share_strategy":
        return _render_market_share_strategy(data, title)
    if agent_key == "customer_segmentation":
        return _render_customer_segmentation(data, title)
    if agent_key == "customer_stickiness":
        return _render_customer_stickiness(data, title)
    if agent_key == "customer_satisfaction":
        return _render_customer_satisfaction(data, title)
    if agent_key == "buying_behavior":
        return _render_buying_behavior(data, title)
    if agent_key == "supplier_dependence":
        return _render_supplier_dependence(data, title)
    if agent_key == "supply_chain_resilience":
        return _render_supply_chain_resilience(data, title)
    if agent_key == "operational_risk":
        return _render_operational_risk(data, title)
    if agent_key == "cost_structure":
        return _render_cost_structure(data, title)
    if agent_key == "historical_performance":
        return _render_historical_performance(data, title)
    if agent_key == "revenue_quality":
        return _render_revenue_quality(data, title)
    if agent_key == "capital_structure":
        return _render_capital_structure(data, title)
    if agent_key == "market_risk":
        return _render_market_risk(data, title)
    if agent_key == "internal_risk":
        return _render_internal_risk(data, title)
    if agent_key == "growth_opportunities":
        return _render_growth_opportunities(data, title)
    if agent_key == "synergies":
        return _render_synergies(data, title)
    if agent_key == "swot_analysis":
        return _render_swot_analysis(data, title)
    if agent_key == "recommendation":
        return _render_recommendation(data, title)
    if agent_key in {"ic_synthesis", "executive_summary"}:
        return _render_ic_synthesis(data, title)
    if agent_key == "valuation_modeling":
        return _render_valuation_modeling(data, title)
    return _render_generic(data, title)
