"""Phase 3 Deep Dive — Slice 0 skeleton runners + Findings Store."""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from collections.abc import Callable, Iterator
from typing import Any

from sqlalchemy.orm import Session

from agetic_cdd_api.deep_dive_competitive import (
    COMPETITIVE_SLUGS,
    extract_competitive_spec,
    findings_from_competitive_spec,
)
from agetic_cdd_api.deep_dive_customer import (
    CUSTOMER_SLUGS,
    extract_customer_spec,
    findings_from_customer_spec,
)
from agetic_cdd_api.deep_dive_financial import (
    FINANCIAL_SLUGS,
    extract_financial_spec,
    findings_from_financial_spec,
)
from agetic_cdd_api.deep_dive_ops import (
    OPS_SLUGS,
    extract_ops_spec,
    findings_from_ops_spec,
)
from agetic_cdd_api.deep_dive_risk import (
    RISK_SLUGS,
    extract_risk_spec,
    findings_from_risk_spec,
)
from agetic_cdd_api.deep_dive_extractors import (
    MARKET_SLUGS,
    extract_deep_dive_spec,
    findings_from_market_spec,
)
from agetic_cdd_api.deep_dive_cascade import (
    cascade_run_order,
    frozen_upstream_slugs,
    plan_cascade_rerun,
)
from agetic_cdd_api.deep_dive_findings import (
    build_findings_store,
    load_deep_dive_findings,
    write_deep_dive_findings,
)
from agetic_cdd_api.deep_dive_roles import (
    DeepDiveRole,
    role_by_slug,
    topo_order,
)
from agetic_cdd_api.foundation_context import load_foundation_context
from agetic_cdd_api.models import Deal
from agetic_cdd_api.pipeline_catalog import PHASE3_AGENT_KEYS
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_library import (
    documents_for_agent,
    ingest_vdr_to_library,
    load_library_document,
    load_library_index,
)
from agetic_cdd_api.services_pipeline import read_agent_output_file

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")
EventCb = Callable[[dict[str, Any]], None]
TextCache = OrderedDict[str, str]

# Cap per-document text retained in the shared TextCache (characters).
_CACHE_DOC_CHAR_LIMIT = 200_000
# Soft cap on total cached characters across all docs in one Deep Dive run.
_CACHE_TOTAL_CHAR_LIMIT = 1_200_000
# Normalized prefix for foundation soft-fill rows in findings lists.
_FOUNDATION_FINDING_PREFIX = "Foundation · "



def _emit(cb: EventCb | None, payload: dict[str, Any]) -> None:
    if cb:
        cb(payload)


def _clip(text: str, limit: int) -> str:
    """Truncate on Unicode code-point boundaries; avoid mid-token cuts when possible."""
    value = text or ""
    if len(value) <= limit:
        return value
    cut = value[: max(0, limit - 1)].rstrip()
    # Prefer breaking at whitespace in the last stretch.
    tail_start = max(0, len(cut) - 48)
    if " " in cut[tail_start:]:
        cut = cut[: tail_start + cut[tail_start:].rfind(" ")].rstrip()
    return cut + "…"


def _bind_documents(index: dict, role: DeepDiveRole) -> list[dict]:
    """Merge catalog routing with role needle/kind scores (never short-circuit on one doc)."""
    needles = tuple(n.lower() for n in role.filename_needles)
    kinds = {str(k).strip().lower() for k in role.primary_kinds if str(k).strip()}
    catalog_names = {
        str(d.get("filename") or d.get("name") or "").strip().lower()
        for d in (documents_for_agent(index, role.slug) or [])
        if (d.get("filename") or d.get("name"))
    }
    scored: list[tuple[float, dict]] = []
    for doc in index.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        filename = str(doc.get("filename") or doc.get("name") or "").lower()
        category = str(doc.get("cdl_category") or "").strip().lower()
        score = 0.0
        if filename and filename in catalog_names:
            score += 2.0
        if category and category in kinds:
            score += 3.0
        score += sum(2.0 for n in needles if n and n in filename)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    # Cap keeps extractors focused; Market agents need thesis + commercial + competition.
    return [doc for _, doc in scored[:6]]


def _cache_get(cache: TextCache, filename: str) -> str | None:
    """Return cached doc text and mark as most-recently used."""
    if filename not in cache:
        return None
    move = getattr(cache, "move_to_end", None)
    if move is not None:
        move(filename)
    return cache[filename]


def _cache_put(cache: TextCache, filename: str, text: str) -> None:
    """Insert doc text; evict least-recently-used entries until under total cap."""
    if not filename:
        return
    if filename in cache:
        del cache[filename]
    cache[filename] = text
    move = getattr(cache, "move_to_end", None)
    popitem = getattr(cache, "popitem", None)
    if move is not None:
        move(filename)
    if popitem is None:
        return
    while cache and sum(len(v) for v in cache.values()) > _CACHE_TOTAL_CHAR_LIMIT:
        popitem(last=False)


def _source_text(deal: Deal, doc: dict, *, cache: TextCache | None = None) -> str:
    filename = str(doc.get("filename") or doc.get("name") or "")
    if cache is not None and filename:
        cached = _cache_get(cache, filename)
        if cached is not None:
            return cached
    try:
        payload = load_library_document(deal, filename=filename) if filename else None
    except Exception:  # noqa: BLE001
        payload = None
    if isinstance(payload, dict) and payload.get("text"):
        text = str(payload["text"])
    else:
        text = str(doc.get("excerpt") or "")
    # Bound per-doc retention so large CIM PDFs cannot balloon process RSS.
    if len(text) > _CACHE_DOC_CHAR_LIMIT:
        text = _clip(text, _CACHE_DOC_CHAR_LIMIT)
    if cache is not None and filename:
        _cache_put(cache, filename, text)
    return text


def _excerpt(deal: Deal, doc: dict, *, limit: int = 900, cache: TextCache | None = None) -> str:
    cleaned = _WHITESPACE.sub(" ", _source_text(deal, doc, cache=cache)).strip()
    return _clip(cleaned, limit) if len(cleaned) > limit else cleaned


def _foundation_snippets(store: dict | None, codes: tuple[str, ...]) -> list[str]:
    """Return normalized foundation finding lines for soft-fill / fallback paths."""
    if not store:
        return []
    roles = store.get("roles") if isinstance(store.get("roles"), dict) else {}
    out: list[str] = []
    for code in codes:
        entry = roles.get(code) if isinstance(roles, dict) else None
        if not isinstance(entry, dict):
            continue
        summary = str(entry.get("summary") or "").strip()
        if summary:
            out.append(f"{_FOUNDATION_FINDING_PREFIX}{code}: {_clip(summary, 260)}")
    return out


def _prior_spec(prior: dict[str, dict], depends_on: tuple[str, ...]) -> dict | None:
    for dep in depends_on:
        upstream = prior.get(dep)
        if not upstream:
            continue
        spec = upstream.get("spec")
        if isinstance(spec, dict) and not spec.get("empty"):
            return spec
    for dep in depends_on:
        upstream = prior.get(dep)
        if upstream and isinstance(upstream.get("spec"), dict):
            return upstream["spec"]
    return None


def _store_entry_as_payload(entry: dict) -> dict:
    """Preserve structural tags when rehydrating prior Findings Store rows for partial runs."""
    payload = dict(entry)
    payload.update(
        {
            "status": entry.get("status") or "missing",
            "summary": entry.get("summary"),
            "findings": entry.get("findings") or [],
            "sources": entry.get("sources") or [],
            "spec": entry.get("spec"),
            "empty_vdr": bool(entry.get("empty_vdr") or entry.get("status") == "empty_vdr"),
            # Normalize runner-facing aliases so consumers of agent_outputs stay stable.
            "agent_key": entry.get("agent_key") or entry.get("slug"),
            "agentName": entry.get("agentName") or entry.get("name"),
            "dd_code": entry.get("dd_code"),
            "track": entry.get("track"),
            "slice": entry.get("slice"),
        }
    )
    return payload


def _hydrate_stored_outputs(deal: Deal, slugs: set[str]) -> dict[str, dict]:
    """Load upstream agent payloads from output files or the Findings Store."""
    if not slugs:
        return {}
    store = load_deep_dive_findings(deal)
    store_agents = (store or {}).get("agents") if isinstance(store, dict) else {}
    hydrated: dict[str, dict] = {}
    for slug in slugs:
        payload = read_agent_output_file(deal, agent_key=slug)
        if not payload and isinstance(store_agents, dict):
            entry = store_agents.get(slug)
            if isinstance(entry, dict):
                payload = _store_entry_as_payload(entry)
        if payload:
            hydrated[slug] = payload
    return hydrated


def _apply_cascade_tags(
    payload: dict[str, Any],
    *,
    trigger: str,
    slug: str,
    reason: str = "blast_radius",
) -> dict[str, Any]:
    tagged = dict(payload)
    tagged["cascade"] = {
        "rerun": True,
        "trigger": trigger,
        "reason": reason,
        "orchestrator": "deep_dive_s7",
    }
    return tagged


def _failed_agent_payload(
    deal: Deal,
    *,
    role: DeepDiveRole,
    error: str,
    blocked_by: str | None = None,
) -> dict[str, Any]:
    reason = (
        f"{role.name} blocked because {blocked_by} failed."
        if blocked_by
        else f"{role.name} failed: {error}"
    )
    return {
        "stub": False,
        "status": "failed",
        "agent_key": role.slug,
        "agentName": role.name,
        "dd_code": role.code,
        "track": role.track,
        "src": role.src,
        "phase_id": "deep_dive",
        "deal_id": deal.id,
        "summary": reason,
        "findings": [f"Blocked by {blocked_by}."] if blocked_by else [error[:280]],
        "sources": [],
        "error": error if not blocked_by else f"{blocked_by} failed",
        "spec": {
            "document": role.spec_output,
            "dd_code": role.code,
            "track": role.track,
            "empty": True,
        },
        "empty_vdr": False,
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{role.slug}.json",
    }


def _build_extracted_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
    slice_id: str,
    extract_fn,
    findings_fn,
) -> dict[str, Any]:
    docs = _bind_documents(index, role)
    sources = [
        str(d.get("filename") or d.get("name") or "")
        for d in docs
        if d.get("filename") or d.get("name")
    ]
    coverage = "full" if docs else "missing"
    blobs = [_source_text(deal, doc, cache=cache) for doc in docs]
    foundation_bits = _foundation_snippets(foundation, role.foundation_deps)

    vdr_text = "\n".join(b for b in blobs if b and b.strip()).strip()
    if vdr_text:
        text_to_parse = vdr_text
        extract_source = "vdr"
    elif foundation_bits:
        text_to_parse = "\n".join(foundation_bits)
        extract_source = "foundation"
    else:
        text_to_parse = ""
        extract_source = "none"

    prior_spec = _prior_spec(prior, role.depends_on)
    spec = extract_fn(
        role.slug,
        text_to_parse,
        sources=sources,
        coverage=coverage,
        prior_spec=prior_spec,
    )
    spec["extract_source"] = extract_source
    spec["vdr_backed"] = coverage != "missing"

    findings = findings_fn(role.slug, spec)
    # Foundation snippets soft-fill only when VDR extract is empty/missing —
    # never append F-0x prose into a completed VDR-backed findings list.
    foundation_soft_fill = extract_source == "foundation"
    if extract_source == "foundation":
        spec["foundation_soft_fill"] = True
    if foundation_bits and (not findings or spec.get("empty")):
        if extract_source != "foundation":
            foundation_soft_fill = True
            spec["foundation_soft_fill"] = True
        findings.extend(foundation_bits)
    for dep in role.depends_on:
        upstream = prior.get(dep)
        if upstream and upstream.get("summary"):
            findings.append(f"Uses {dep}: {_clip(str(upstream['summary']), 200)}")
    if not findings:
        findings = [
            f"No structured signals for {role.name}; empty_vdr skeleton retained.",
        ]

    empty_vdr = coverage == "missing"
    status = "empty_vdr" if empty_vdr else "completed"
    if empty_vdr and extract_source == "none":
        spec["empty"] = True

    from agetic_cdd_api.services_accounts_extract import resolve_target_display_name

    target = resolve_target_display_name(deal, index=index, foundation=foundation)
    lead = findings[0] if findings else f"Analysis for {role.name}."
    metrics = spec.get("metrics") if isinstance(spec.get("metrics"), dict) else {}
    metric_bits = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:4] if v)
    raw_summary = (
        f"{role.spec_output} for {target} "
        f"({coverage} bind · {len(sources)} source(s) · extract={extract_source}"
        + (f" · {metric_bits}" if metric_bits else "")
        + "). "
        + lead
    )
    return {
        "stub": False,
        "slice": slice_id,
        "status": status,
        "empty_vdr": empty_vdr,
        "extract_source": extract_source,
        "foundation_soft_fill": foundation_soft_fill,
        "agent_key": role.slug,
        "agentName": role.name,
        "dd_code": role.code,
        "track": role.track,
        "src": role.src,
        "description": role.spec_output,
        "phase_id": "deep_dive",
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": target,
        "sources": sources,
        "source_coverage": coverage,
        "depends_on": list(role.depends_on),
        "foundation_deps": list(role.foundation_deps),
        "summary": _clip(raw_summary, 600),
        "findings": findings[:8],
        "spec": spec,
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{role.slug}.json",
    }


def _build_market_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
) -> dict[str, Any]:
    payload = _build_extracted_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        prior=prior,
        cache=cache,
        slice_id="deep_dive_s1",
        extract_fn=extract_deep_dive_spec,
        findings_fn=findings_from_market_spec,
    )
    if role.slug == "market_definition":
        from agetic_cdd_api.agent_document_market_definition import (
            build_market_definition_spec,
            render_market_definition_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        prior_seed = None
        for code in ("F-05", "F-01"):
            entry = (foundation or {}).get(code) if isinstance(foundation, dict) else None
            if isinstance(entry, dict) and isinstance(entry.get("spec"), dict):
                prior_seed = entry["spec"]
                break
        # Reuse extractor prose — avoid a second full VDR load inside the 24-agent run.
        corpus_bits: list[str] = []
        for key in ("market_framing", "segments", "macro_drivers", "policy_context", "geographies"):
            for item in (legacy.get(key) or []):
                if isinstance(item, str) and item.strip():
                    corpus_bits.append(item.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        # Pipeline stays heuristic unless deep_dive_llm is enabled (avoids blocking 24-agent runs).
        md_spec = build_market_definition_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            prior_spec=prior_seed,
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **md_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (md_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_market_definition_markdown(
            str(payload.get("agentName") or "Market Definition"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(md_spec.get("insight_snapshot") or payload.get("summary") or "")
        md_findings: list[str] = []
        perim = md_spec.get("perimeter") if isinstance(md_spec.get("perimeter"), dict) else {}
        for axis in ("service", "customer_types", "geography", "value_chain_stage"):
            val = perim.get(axis)
            if val and not str(val).startswith("Information"):
                md_findings.append(f"{axis}: {_clip(str(val), 160)}")
        gate = md_spec.get("approval_gate") if isinstance(md_spec.get("approval_gate"), dict) else {}
        if gate:
            md_findings.append(
                f"Approval gate: {gate.get('status')} · blocks downstream="
                f"{gate.get('blocks_downstream_market_agents', True)}"
            )
        qv, rv = md_spec.get("quality_verdict"), md_spec.get("reliance_verdict")
        if qv or rv:
            md_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if md_findings:
            payload["findings"] = md_findings[:8]
        return payload

    if role.slug == "market_volume_and_growth":
        from agetic_cdd_api.agent_document_market_volume import (
            build_market_volume_spec,
            render_market_volume_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        perimeter = None
        md_prior = prior.get("market_definition") if isinstance(prior, dict) else None
        if isinstance(md_prior, dict) and isinstance(md_prior.get("spec"), dict):
            perimeter = md_prior["spec"].get("perimeter")
        # Do NOT build a thin corpus from legacy TAM/SAM/SOM raw values — that
        # re-injects segment rows (e.g. hauling-only $498) and blocks TOTAL Current
        # extract from the VDR workbook. Pass corpus=None so gather_market_volume_corpus
        # loads TAM_SAM tables; legacy_spec still feeds _prefer_sizing as fallback.
        mv_spec = build_market_volume_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            perimeter=perimeter if isinstance(perimeter, dict) else None,
            legacy_spec=legacy,
            corpus=None,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **mv_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (mv_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_market_volume_markdown(
            str(payload.get("agentName") or "Market Volume & Growth"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(mv_spec.get("insight_snapshot") or payload.get("summary") or "")
        mv_findings: list[str] = []
        bottom = mv_spec.get("bottom_up") if isinstance(mv_spec.get("bottom_up"), dict) else {}
        if bottom.get("bottom_up_size"):
            mv_findings.append(f"Bottom-up: {_clip(str(bottom['bottom_up_size']), 160)}")
        if mv_spec.get("market_growth_note"):
            mv_findings.append(f"Market: {_clip(str(mv_spec['market_growth_note']), 160)}")
        cg = mv_spec.get("company_growth") if isinstance(mv_spec.get("company_growth"), dict) else {}
        if cg.get("historical_growth"):
            mv_findings.append(f"Company: {_clip(str(cg['historical_growth']), 160)}")
        plan = mv_spec.get("plan_vs_market") if isinstance(mv_spec.get("plan_vs_market"), dict) else {}
        if plan.get("multiple") and not str(plan["multiple"]).startswith("Information"):
            mv_findings.append(f"Plan/market multiple: {plan['multiple']}")
        qv, rv = mv_spec.get("quality_verdict"), mv_spec.get("reliance_verdict")
        if qv or rv:
            mv_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if mv_findings:
            payload["findings"] = mv_findings[:8]
        return payload

    if role.slug == "market_pricing":
        from agetic_cdd_api.agent_document_market_pricing import (
            build_market_pricing_spec,
            render_market_pricing_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for pp in (legacy.get("price_points") or [])[:6]:
            if isinstance(pp, dict):
                corpus_bits.append(
                    f"{pp.get('label')}: {pp.get('unit', '')} {pp.get('value')} "
                    f"{pp.get('raw') or ''}"
                )
        for note in (legacy.get("pricing_notes") or [])[:4]:
            if isinstance(note, str):
                corpus_bits.append(note)
        for sig in (legacy.get("power_signals") or [])[:4]:
            if isinstance(sig, str):
                corpus_bits.append(sig)
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        mp_spec = build_market_pricing_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **mp_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (mp_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_market_pricing_markdown(
            str(payload.get("agentName") or "Market Pricing"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(mp_spec.get("insight_snapshot") or payload.get("summary") or "")
        mp_findings: list[str] = []
        for row in (mp_spec.get("realised_prices") or [])[:2]:
            if isinstance(row, dict) and row.get("realised_net_price"):
                mp_findings.append(
                    f"Realised: {_clip(str(row['realised_net_price']), 120)}"
                )
        for row in (mp_spec.get("competitor_comparisons") or [])[:2]:
            if isinstance(row, dict) and row.get("competitor"):
                if not str(row["competitor"]).startswith("Information"):
                    mp_findings.append(f"Comp: {_clip(str(row['competitor']), 80)}")
        qv, rv = mp_spec.get("quality_verdict"), mp_spec.get("reliance_verdict")
        if qv or rv:
            mp_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if mp_findings:
            payload["findings"] = mp_findings[:8]
        return payload

    if role.slug == "demand_drivers":
        from agetic_cdd_api.agent_document_demand_drivers import (
            build_demand_drivers_spec,
            render_demand_drivers_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for key in ("demand_drivers", "regional_signals", "cycle_risks"):
            for item in (legacy.get(key) or [])[:6]:
                if isinstance(item, str) and item.strip():
                    corpus_bits.append(item.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        dd_spec = build_demand_drivers_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **dd_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (dd_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_demand_drivers_markdown(
            str(payload.get("agentName") or "Demand Drivers"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(dd_spec.get("insight_snapshot") or payload.get("summary") or "")
        dd_findings: list[str] = []
        for row in (dd_spec.get("drivers") or [])[:2]:
            if isinstance(row, dict) and row.get("driver"):
                if not str(row["driver"]).startswith("Information"):
                    dd_findings.append(f"Driver: {_clip(str(row['driver']), 120)}")
        for row in (dd_spec.get("ranked_contribution") or [])[:2]:
            if isinstance(row, dict) and row.get("driver"):
                dd_findings.append(
                    f"Rank {row.get('rank')}: {_clip(str(row['driver']), 80)}"
                )
        qv, rv = dd_spec.get("quality_verdict"), dd_spec.get("reliance_verdict")
        if qv or rv:
            dd_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if dd_findings:
            payload["findings"] = dd_findings[:8]
        return payload

    return payload


def _build_competitive_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
) -> dict[str, Any]:
    payload = _build_extracted_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        prior=prior,
        cache=cache,
        slice_id="deep_dive_s2",
        extract_fn=extract_competitive_spec,
        findings_fn=findings_from_competitive_spec,
    )
    if role.slug == "competitor_identification":
        from agetic_cdd_api.agent_document_competitor_identification import (
            build_competitor_identification_spec,
            render_competitor_identification_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for row in (legacy.get("competitors") or [])[:8]:
            if isinstance(row, dict) and row.get("name"):
                bits = [str(row["name"])]
                if row.get("market_share_pct") is not None:
                    bits.append(f"share {row['market_share_pct']}%")
                if row.get("trend"):
                    bits.append(str(row["trend"]))
                corpus_bits.append(" ".join(bits))
        for note in (legacy.get("positioning_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        ci_spec = build_competitor_identification_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **ci_spec}
        if ci_spec.get("competitors_legacy"):
            merged["competitors"] = ci_spec["competitors_legacy"]
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (ci_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_competitor_identification_markdown(
            str(payload.get("agentName") or "Competitor Identification"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(ci_spec.get("insight_snapshot") or payload.get("summary") or "")
        ci_findings: list[str] = []
        for row in (ci_spec.get("competitive_set") or ci_spec.get("competitors_legacy") or [])[:3]:
            if isinstance(row, dict) and row.get("name"):
                if not str(row["name"]).startswith("Information"):
                    label = row.get("classification") or ""
                    ci_findings.append(
                        f"{row['name']}"
                        + (f" ({label})" if label else "")
                    )
        qv, rv = ci_spec.get("quality_verdict"), ci_spec.get("reliance_verdict")
        if qv or rv:
            ci_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if ci_findings:
            payload["findings"] = ci_findings[:8]
        return payload

    if role.slug == "competitive_differentiation":
        from agetic_cdd_api.agent_document_competitive_differentiation import (
            build_competitive_differentiation_spec,
            render_competitive_differentiation_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for key in ("differentiators", "moat_signals", "feature_gaps", "peer_software"):
            for item in (legacy.get(key) or [])[:6]:
                if isinstance(item, str) and item.strip():
                    corpus_bits.append(item.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        cd_spec = build_competitive_differentiation_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **cd_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (cd_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_competitive_differentiation_markdown(
            str(payload.get("agentName") or "Competitive Differentiation"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(cd_spec.get("insight_snapshot") or payload.get("summary") or "")
        cd_findings: list[str] = []
        for row in (cd_spec.get("advantage_tests") or [])[:2]:
            if isinstance(row, dict) and row.get("claim"):
                cd_findings.append(
                    f"Test {row.get('test_result') or '?'}: {_clip(str(row['claim']), 100)}"
                )
        for row in (cd_spec.get("claimed_advantages") or [])[:2]:
            if isinstance(row, dict) and row.get("claim"):
                if not any(str(row["claim"])[:40] in f for f in cd_findings):
                    cd_findings.append(f"Claim: {_clip(str(row['claim']), 100)}")
        qv, rv = cd_spec.get("quality_verdict"), cd_spec.get("reliance_verdict")
        if qv or rv:
            cd_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if cd_findings:
            payload["findings"] = cd_findings[:8]
        return payload

    if role.slug == "market_share_strategy":
        from agetic_cdd_api.agent_document_market_share_strategy import (
            build_market_share_strategy_spec,
            render_market_share_strategy_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for row in (legacy.get("share_trends") or [])[:8]:
            if isinstance(row, dict) and row.get("name"):
                bits = [str(row["name"])]
                if row.get("market_share_pct") is not None:
                    bits.append(f"share {row['market_share_pct']}%")
                if row.get("trend"):
                    bits.append(str(row["trend"]))
                corpus_bits.append(" ".join(bits))
        for key in ("wins", "losses", "strategy_notes"):
            for item in (legacy.get(key) or [])[:6]:
                if isinstance(item, str) and item.strip():
                    corpus_bits.append(item.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        mss_spec = build_market_share_strategy_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **mss_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (mss_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_market_share_strategy_markdown(
            str(payload.get("agentName") or "Market Share Strategy"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(mss_spec.get("insight_snapshot") or payload.get("summary") or "")
        mss_findings: list[str] = []
        matched = mss_spec.get("matched_share") if isinstance(mss_spec.get("matched_share"), dict) else {}
        if matched.get("calculable") and matched.get("share_pct") not in (None, ""):
            mss_findings.append(f"Matched share: {matched.get('share_pct')}")
        else:
            mss_findings.append("Share not calculable / unassessed on matched basis")
        for row in (mss_spec.get("share_movement") or [])[:2]:
            if isinstance(row, dict) and row.get("peer_or_focal"):
                mss_findings.append(
                    f"Movement · {row['peer_or_focal']}: {row.get('delta_pp') or '—'}"
                )
        att = (
            mss_spec.get("attainable_vs_ambition")
            if isinstance(mss_spec.get("attainable_vs_ambition"), dict)
            else {}
        )
        if att.get("gap") and not str(att["gap"]).startswith("Information"):
            mss_findings.append(f"Gap: {_clip(str(att['gap']), 120)}")
        qv, rv = mss_spec.get("quality_verdict"), mss_spec.get("reliance_verdict")
        if qv or rv:
            mss_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if mss_findings:
            payload["findings"] = mss_findings[:8]
        return payload

    if role.slug == "swot_analysis":
        from agetic_cdd_api.agent_document_swot_analysis import (
            build_swot_analysis_spec,
            render_swot_analysis_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        swot_spec = build_swot_analysis_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            prior=prior,
            foundation=foundation if isinstance(foundation, dict) else None,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **swot_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (swot_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_swot_analysis_markdown(
            str(payload.get("agentName") or "SWOT Analysis"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            swot_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings: list[str] = []
        for label, key in (
            ("S", "strengths"),
            ("W", "weaknesses"),
            ("O", "opportunities"),
            ("T", "threats"),
        ):
            for item in (swot_spec.get(key) or [])[:2]:
                if isinstance(item, str) and item.strip():
                    findings.append(f"{label}: {item.strip()[:160]}")
        gaps = swot_spec.get("information_gaps") or []
        if gaps:
            findings.append(f"{len(gaps)} unexamined gap(s) (not weaknesses)")
        blockers = swot_spec.get("open_blockers") or []
        if blockers:
            findings.append(f"OPEN BLOCKER: {str(blockers[0])[:120]}")
        qv, rv = swot_spec.get("quality_verdict"), swot_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]
        return payload

    return payload


def _build_customer_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
) -> dict[str, Any]:
    payload = _build_extracted_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        prior=prior,
        cache=cache,
        slice_id="deep_dive_s3",
        extract_fn=extract_customer_spec,
        findings_fn=findings_from_customer_spec,
    )
    if role.slug == "customer_segmentation":
        from agetic_cdd_api.agent_document_customer_segmentation import (
            build_customer_segmentation_spec,
            render_customer_segmentation_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for row in (legacy.get("segments") or [])[:8]:
            if isinstance(row, dict) and row.get("name"):
                bits = [str(row["name"])]
                if row.get("share_pct") is not None:
                    bits.append(f"{row['share_pct']}%")
                if row.get("use_case"):
                    bits.append(str(row["use_case"]))
                if row.get("key_driver"):
                    bits.append(str(row["key_driver"]))
                corpus_bits.append(" ".join(bits))
        for note in (legacy.get("icp_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for geo in (legacy.get("geo_mix") or [])[:6]:
            if isinstance(geo, str) and geo.strip():
                corpus_bits.append(geo.strip())
            elif isinstance(geo, dict) and geo.get("region"):
                corpus_bits.append(
                    f"{geo['region']} {geo.get('share_pct') or ''}".strip()
                )
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        cs_spec = build_customer_segmentation_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **cs_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (cs_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_customer_segmentation_markdown(
            str(payload.get("agentName") or "Customer Segmentation"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(cs_spec.get("insight_snapshot") or payload.get("summary") or "")
        cs_findings: list[str] = []
        conc = cs_spec.get("concentration") if isinstance(cs_spec.get("concentration"), dict) else {}
        if conc.get("calculable"):
            bits = ["Concentration (parents)"]
            for label, key in (
                ("T1", "top_1_share_pct"),
                ("T5", "top_5_share_pct"),
                ("T10", "top_10_share_pct"),
            ):
                if conc.get(key):
                    bits.append(f"{label} {conc[key]}")
            cs_findings.append(" · ".join(bits))
        else:
            cs_findings.append("Concentration unassessed — ledger requested; risk rating withheld")
        for row in (cs_spec.get("largest_contracts") or [])[:2]:
            if isinstance(row, dict) and row.get("name"):
                if not str(row["name"]).startswith("Information"):
                    cs_findings.append(f"Contract: {_clip(str(row['name']), 100)}")
        for row in (cs_spec.get("segments") or [])[:2]:
            if isinstance(row, dict) and row.get("name"):
                share = row.get("share_pct")
                cs_findings.append(
                    f"{row['name']}"
                    + (f" — {share}%" if share is not None else "")
                )
        qv, rv = cs_spec.get("quality_verdict"), cs_spec.get("reliance_verdict")
        if qv or rv:
            cs_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if cs_findings:
            payload["findings"] = cs_findings[:8]
        return payload

    if role.slug == "customer_stickiness":
        from agetic_cdd_api.agent_document_customer_stickiness import (
            build_customer_stickiness_spec,
            render_customer_stickiness_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        metrics = legacy.get("retention_metrics") if isinstance(legacy.get("retention_metrics"), dict) else {}
        for key, val in list(metrics.items())[:8]:
            if val is not None:
                corpus_bits.append(f"{key}: {val}")
        for row in (legacy.get("cohorts") or [])[:6]:
            if isinstance(row, dict) and row.get("cohort"):
                bits = [str(row["cohort"])]
                if row.get("m12_retention_pct") is not None:
                    bits.append(f"M12 {row['m12_retention_pct']}%")
                if row.get("size_units") is not None:
                    bits.append(f"size {row['size_units']}")
                corpus_bits.append(" ".join(bits))
        for note in (legacy.get("stickiness_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        stick_spec = build_customer_stickiness_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **stick_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (stick_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_customer_stickiness_markdown(
            str(payload.get("agentName") or "Customer Stickiness"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            stick_spec.get("insight_snapshot") or payload.get("summary") or ""
        )
        stick_findings: list[str] = []
        for row in (stick_spec.get("retention_delta") or [])[:2]:
            if isinstance(row, dict) and row.get("is_finding"):
                stick_findings.append(
                    f"Finding · {row.get('metric') or 'retention'} "
                    f"{row.get('direction') or 'down'}: {_clip(str(row.get('magnitude') or ''), 80)}"
                )
        same = (
            stick_spec.get("retention_on_same_population")
            if isinstance(stick_spec.get("retention_on_same_population"), dict)
            else {}
        )
        if same.get("grr") or same.get("nrr"):
            bits = ["Same-pop"]
            if same.get("grr"):
                bits.append(f"GRR {same['grr']}")
            if same.get("nrr"):
                bits.append(f"NRR {same['nrr']}")
            stick_findings.append(" · ".join(bits))
        for row in (stick_spec.get("cohorts") or [])[:2]:
            if isinstance(row, dict) and row.get("cohort"):
                stick_findings.append(
                    f"Cohort {row['cohort']}"
                    + (
                        f" · M12 {row['m12_retention_pct']}%"
                        if row.get("m12_retention_pct") is not None
                        else ""
                    )
                )
        qv, rv = stick_spec.get("quality_verdict"), stick_spec.get("reliance_verdict")
        if qv or rv:
            stick_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if stick_findings:
            payload["findings"] = stick_findings[:8]
        return payload

    if role.slug == "customer_satisfaction":
        from agetic_cdd_api.agent_document_customer_satisfaction import (
            build_customer_satisfaction_spec,
            render_customer_satisfaction_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        if legacy.get("nps") is not None:
            corpus_bits.append(f"NPS {legacy['nps']}")
        if legacy.get("service_satisfaction_pct") is not None:
            corpus_bits.append(f"Service Satisfaction {legacy['service_satisfaction_pct']}%")
        for peer in (legacy.get("peer_nps") or [])[:4]:
            if isinstance(peer, str) and peer.strip():
                corpus_bits.append(peer.strip())
        for row in (legacy.get("churn_drivers") or [])[:6]:
            if isinstance(row, dict) and row.get("driver"):
                bits = [str(row["driver"])]
                if row.get("contribution_pct") is not None:
                    bits.append(f"{row['contribution_pct']}%")
                if row.get("severity"):
                    bits.append(str(row["severity"]))
                corpus_bits.append(" ".join(bits))
        for note in (legacy.get("satisfaction_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        sat_spec = build_customer_satisfaction_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **sat_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (sat_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_customer_satisfaction_markdown(
            str(payload.get("agentName") or "Customer Satisfaction"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            sat_spec.get("insight_snapshot") or payload.get("summary") or ""
        )
        sat_findings: list[str] = []
        if sat_spec.get("nps") is not None:
            sat_findings.append(f"NPS {sat_spec['nps']:g}")
        if sat_spec.get("service_satisfaction_pct") is not None:
            sat_findings.append(
                f"Service satisfaction {sat_spec['service_satisfaction_pct']:g}%"
            )
        for row in (sat_spec.get("churn_drivers") or [])[:2]:
            if isinstance(row, dict) and row.get("driver"):
                sat_findings.append(
                    f"{row['driver']}"
                    + (
                        f" — {row['contribution_pct']}%"
                        if row.get("contribution_pct") is not None
                        else ""
                    )
                )
        assoc = (
            sat_spec.get("churn_association")
            if isinstance(sat_spec.get("churn_association"), dict)
            else {}
        )
        if assoc.get("comparable"):
            sat_findings.append("Service↔churn association evidenced (not causation)")
        research = (
            sat_spec.get("research_design")
            if isinstance(sat_spec.get("research_design"), dict)
            else {}
        )
        if research.get("needed"):
            sat_findings.append("Research design proposed — sentiment evidence thin")
        qv, rv = sat_spec.get("quality_verdict"), sat_spec.get("reliance_verdict")
        if qv or rv:
            sat_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if sat_findings:
            payload["findings"] = sat_findings[:8]
        return payload

    if role.slug == "buying_behavior":
        from agetic_cdd_api.agent_document_buying_behavior import (
            build_buying_behavior_spec,
            render_buying_behavior_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        metrics = legacy.get("buying_metrics") if isinstance(legacy.get("buying_metrics"), dict) else {}
        for key, val in list(metrics.items())[:8]:
            if val is not None:
                corpus_bits.append(f"{key}: {val}")
        for flag in (legacy.get("concentration_flags") or [])[:4]:
            if isinstance(flag, str) and flag.strip():
                corpus_bits.append(flag.strip())
        for ch in (legacy.get("channel_mix") or [])[:4]:
            if isinstance(ch, str) and ch.strip():
                corpus_bits.append(ch.strip())
        for note in (legacy.get("behavior_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        if legacy.get("segment_hhi") is not None:
            corpus_bits.append(f"Segment HHI {legacy['segment_hhi']}")
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        buy_spec = build_buying_behavior_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **buy_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (buy_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_buying_behavior_markdown(
            str(payload.get("agentName") or "Buying Behavior"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            buy_spec.get("insight_snapshot") or payload.get("summary") or ""
        )
        buy_findings: list[str] = []
        maps = buy_spec.get("purchase_maps") or []
        if maps:
            buy_findings.append(f"{len(maps)} segment purchase map(s)")
        cycles = buy_spec.get("sales_cycles") or []
        crm_n = sum(1 for c in cycles if isinstance(c, dict) and c.get("crm_evidenced"))
        if crm_n:
            buy_findings.append(f"{crm_n} segment cycle(s) CRM-evidenced")
        switching = (
            buy_spec.get("switching")
            if isinstance(buy_spec.get("switching"), dict)
            else {}
        )
        if switching.get("evidenced"):
            buy_findings.append("Switching triggers evidenced (say vs did)")
        seasonality = (
            buy_spec.get("seasonality")
            if isinstance(buy_spec.get("seasonality"), dict)
            else {}
        )
        if seasonality.get("measured"):
            buy_findings.append("Seasonality measured from monthly records")
        else:
            buy_findings.append("Seasonality not asserted — data thin")
        metrics2 = (
            buy_spec.get("buying_metrics")
            if isinstance(buy_spec.get("buying_metrics"), dict)
            else {}
        )
        if metrics2.get("time_to_purchase_days") is not None:
            buy_findings.append(
                f"TTP {metrics2['time_to_purchase_days']:g}d (not applied to all segments)"
            )
        qv, rv = buy_spec.get("quality_verdict"), buy_spec.get("reliance_verdict")
        if qv or rv:
            buy_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if buy_findings:
            payload["findings"] = buy_findings[:8]
        return payload

    return payload


def _build_ops_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
) -> dict[str, Any]:
    payload = _build_extracted_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        prior=prior,
        cache=cache,
        slice_id="deep_dive_s4",
        extract_fn=extract_ops_spec,
        findings_fn=findings_from_ops_spec,
    )

    if role.slug == "supplier_dependence":
        from agetic_cdd_api.agent_document_supplier_dependence import (
            build_supplier_dependence_spec,
            render_supplier_dependence_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for row in (legacy.get("vendors") or [])[:8]:
            if isinstance(row, dict) and row.get("name"):
                bits = [str(row["name"])]
                if row.get("component"):
                    bits.append(str(row["component"]))
                if row.get("country"):
                    bits.append(str(row["country"]))
                if row.get("annual_value_inr_cr") is not None:
                    bits.append(f"~{row['annual_value_inr_cr']}")
                if row.get("risk_level"):
                    bits.append(str(row["risk_level"]))
                if row.get("alternate_available"):
                    bits.append(str(row["alternate_available"]))
                corpus_bits.append(" ".join(bits))
        for flag in (legacy.get("concentration_flags") or [])[:4]:
            if isinstance(flag, str) and flag.strip():
                corpus_bits.append(flag.strip())
        for note in (legacy.get("dependency_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        sup_spec = build_supplier_dependence_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **sup_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (sup_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_supplier_dependence_markdown(
            str(payload.get("agentName") or "Supplier Dependence"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            sup_spec.get("insight_snapshot") or payload.get("summary") or ""
        )
        findings: list[str] = []
        vendors = [v for v in (sup_spec.get("vendors") or []) if isinstance(v, dict)]
        if vendors:
            findings.append(f"{len(vendors)} supplier(s) listed")
        spend = [
            r for r in (sup_spec.get("spend_by_supplier") or [])
            if isinstance(r, dict) and r.get("ledger_evidenced")
        ]
        if spend:
            findings.append(f"{len(spend)} with ledger spend")
        high = [
            v for v in vendors
            if (v.get("risk_level") or "").lower() == "high"
        ]
        if high:
            findings.append(f"{len(high)} HIGH-risk vendor(s)")
        contracts = [
            c for c in (sup_spec.get("contract_terms") or [])
            if isinstance(c, dict) and str(c.get("contract_read") or "").startswith("Yes")
        ]
        if contracts:
            findings.append(f"{len(contracts)} contract(s) read")
        coc = (
            sup_spec.get("change_of_control")
            if isinstance(sup_spec.get("change_of_control"), dict)
            else {}
        )
        if coc.get("transaction_triggers_flagged"):
            findings.append("Change-of-control consents flagged")
        qv, rv = sup_spec.get("quality_verdict"), sup_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    if role.slug == "supply_chain_resilience":
        from agetic_cdd_api.agent_document_supply_chain_resilience import (
            build_supply_chain_resilience_spec,
            render_supply_chain_resilience_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        # Prefer supplier agent output from cascade prior, else on-disk output
        supplier_spec = None
        prior_sup = prior.get("supplier_dependence") if isinstance(prior, dict) else None
        if isinstance(prior_sup, dict) and isinstance(prior_sup.get("spec"), dict):
            supplier_spec = prior_sup["spec"]
        if supplier_spec is None:
            try:
                from agetic_cdd_api.services_pipeline import read_agent_output_file

                disk = read_agent_output_file(deal, agent_key="supplier_dependence") or {}
                if isinstance(disk.get("spec"), dict):
                    supplier_spec = disk["spec"]
            except Exception:
                supplier_spec = None

        corpus_bits: list[str] = []
        metrics = (
            legacy.get("logistics_metrics")
            if isinstance(legacy.get("logistics_metrics"), dict) else {}
        )
        for key, val in list(metrics.items())[:8]:
            if val is not None:
                corpus_bits.append(f"{key}: {val}")
        for m in (legacy.get("localization_milestones") or [])[:4]:
            if isinstance(m, str) and m.strip():
                corpus_bits.append(m.strip())
        for note in (legacy.get("resilience_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        res_spec = build_supply_chain_resilience_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            supplier_spec=supplier_spec,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **res_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (res_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_supply_chain_resilience_markdown(
            str(payload.get("agentName") or "Supply Chain Resilience"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            res_spec.get("insight_snapshot") or payload.get("summary") or ""
        )
        findings = []
        chain = res_spec.get("critical_path") or []
        spof_n = sum(
            1 for n in chain
            if isinstance(n, dict) and str(n.get("spof") or "").lower() == "yes"
        )
        if chain:
            findings.append(f"{len(chain)} stage(s), {spof_n} SPOF(s)")
        hist = [
            h for h in (res_spec.get("disruption_history") or [])
            if isinstance(h, dict)
            and str(h.get("incident") or "")
            and not str(h.get("incident")).startswith("Information")
        ]
        if hist:
            findings.append(f"{len(hist)} disruption record(s)")
        cont = [
            c for c in (res_spec.get("continuity_arrangements") or [])
            if isinstance(c, dict)
            and "tested" in str(c.get("tested_or_used") or "").lower()
            and "untested" not in str(c.get("tested_or_used") or "").lower()
        ]
        if cont:
            findings.append(f"{len(cont)} continuity arrangement(s) used/tested")
        reconcile = (
            res_spec.get("supplier_reconcile")
            if isinstance(res_spec.get("supplier_reconcile"), dict) else {}
        )
        conflicts = reconcile.get("conflicts") or []
        if conflicts:
            findings.append(f"{len(conflicts)} supplier-reconcile conflict(s)")
        elif reconcile.get("supplier_agent_present"):
            findings.append("Supplier facts reconciled — no term conflicts")
        qv, rv = res_spec.get("quality_verdict"), res_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    if role.slug == "operational_risk":
        from agetic_cdd_api.agent_document_operational_risk import (
            build_operational_risk_spec,
            render_operational_risk_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for g in (legacy.get("kpi_gaps") or [])[:6]:
            if isinstance(g, dict) and g.get("kpi"):
                corpus_bits.append(f"{g['kpi']} {g.get('status') or ''}")
        for r in (legacy.get("risk_items") or [])[:6]:
            if isinstance(r, dict) and r.get("risk"):
                corpus_bits.append(
                    f"{r['risk']} {r.get('likelihood') or ''} {r.get('impact') or ''}"
                )
        for note in (legacy.get("integrity_notes") or [])[:4]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        ops_spec = build_operational_risk_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **ops_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (ops_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_operational_risk_markdown(
            str(payload.get("agentName") or "Operational Risk"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            ops_spec.get("insight_snapshot") or payload.get("summary") or ""
        )
        findings = []
        register = [
            r for r in (ops_spec.get("risk_register") or [])
            if isinstance(r, dict)
            and not r.get("hypothesis")
            and r.get("risk")
            and not str(r.get("risk")).startswith("Information")
        ]
        if register:
            findings.append(f"{len(register)} evidence-derived risk(s)")
        sized = [
            s for s in (ops_spec.get("sized_risks") or [])
            if isinstance(s, dict) and str(s.get("sized") or "") in {"Yes", "Partial"}
        ]
        if sized:
            findings.append(f"{len(sized)} risk(s) sized")
        tested = [
            c for c in (ops_spec.get("controls") or [])
            if isinstance(c, dict) and str(c.get("tested") or "") == "Tested"
        ]
        if tested:
            findings.append(f"{len(tested)} tested control(s)")
        material = [
            p for p in (ops_spec.get("priced_vs_noise") or [])
            if isinstance(p, dict)
            and "protection" in str(p.get("classification") or "").lower()
        ]
        if material:
            findings.append(f"{len(material)} priced / protection risk(s)")
        qv, rv = ops_spec.get("quality_verdict"), ops_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    if role.slug == "cost_structure":
        from agetic_cdd_api.agent_document_cost_structure import (
            build_cost_structure_spec,
            render_cost_structure_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        corpus_bits: list[str] = []
        for b in (legacy.get("bom_components") or [])[:10]:
            if isinstance(b, dict) and b.get("category"):
                share = b.get("share_pct")
                corpus_bits.append(
                    f"{b['category']} — {share}%" if share is not None else str(b["category"])
                )
        for k, v in (legacy.get("cost_metrics") or {}).items():
            corpus_bits.append(f"{k} {v}")
        for note in (legacy.get("efficiency_notes") or [])[:6]:
            if isinstance(note, str) and note.strip():
                corpus_bits.append(note.strip())
        for finding in (payload.get("findings") or [])[:8]:
            if isinstance(finding, str) and finding.strip():
                corpus_bits.append(finding.strip())
        corpus = "\n".join(corpus_bits) or None
        cs_spec = build_cost_structure_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            corpus=corpus,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **cs_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        extra = [
            s for s in (cs_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra:
            sources = list(dict.fromkeys([*sources, *extra]))
            payload["sources"] = sources
        document = render_cost_structure_markdown(
            str(payload.get("agentName") or "Cost Structure"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            cs_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings = []
        cats = [
            c for c in (cs_spec.get("operating_categories") or [])
            if isinstance(c, dict)
            and c.get("category")
            and not str(c.get("gl_accounts") or "").startswith("Information")
        ]
        if cats:
            findings.append(f"{len(cats)} operating categor{'y' if len(cats) == 1 else 'ies'} mapped")
        bom = [
            b for b in (cs_spec.get("bom_components") or [])
            if isinstance(b, dict) and b.get("category")
        ]
        if bom:
            top = max(
                (b for b in bom if isinstance(b.get("share_pct"), (int, float))),
                key=lambda b: float(b["share_pct"]),
                default=None,
            )
            if top:
                findings.append(f"Largest bucket: {top['category']} {float(top['share_pct']):g}%")
        units = [
            u for u in (cs_spec.get("unit_economics") or [])
            if isinstance(u, dict)
            and u.get("cost")
            and not str(u.get("cost")).startswith("Information")
            and str(u.get("cost")) != "N/A (data room did not provide it)"
        ]
        if units:
            findings.append(f"{len(units)} unit-economics line(s)")
        missing = cs_spec.get("missing_accounts") or []
        if missing:
            findings.append(f"{len(missing)} information gap(s)")
        qv, rv = cs_spec.get("quality_verdict"), cs_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    return payload


def _build_financial_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
) -> dict[str, Any]:
    out = _build_extracted_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        prior=prior,
        cache=cache,
        slice_id="deep_dive_s5",
        extract_fn=extract_financial_spec,
        findings_fn=findings_from_financial_spec,
    )
    if role.slug == "historical_performance":
        from agetic_cdd_api.agent_document_historical_performance import (
            build_historical_performance_spec,
            render_historical_performance_markdown,
        )
        from agetic_cdd_api.services_databook_consume import merge_promoted_into_historical_spec
        from agetic_cdd_api.settings import settings

        legacy = out.get("spec") if isinstance(out.get("spec"), dict) else {}
        # Prefer databook-promoted pl_lines as the accounting baseline when present.
        legacy = merge_promoted_into_historical_spec(deal, legacy)
        hp_spec = build_historical_performance_spec(
            deal,
            index=index,
            company=str(out.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(out.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **hp_spec}
        # Accounts extract / databook promoted lines beat regex CIM-page misreads
        if hp_spec.get("accounts_extract") and hp_spec.get("pl_lines"):
            merged["pl_lines"] = hp_spec["pl_lines"]
            merged["accounts_extract"] = True
        elif legacy.get("databook_promoted") and legacy.get("pl_lines"):
            # Keep promoted when composer regex is thinner or still INR-defaulted wrongly
            legacy_units = {
                str(r.get("unit") or "")
                for r in (legacy.get("pl_lines") or [])
                if isinstance(r, dict)
            }
            hp_units = {
                str(r.get("unit") or "")
                for r in (hp_spec.get("pl_lines") or [])
                if isinstance(r, dict)
            }
            if not hp_spec.get("pl_lines") or (
                "INR Cr" in hp_units and any("USD" in u for u in legacy_units)
            ):
                merged["pl_lines"] = legacy.get("pl_lines") or []
        if legacy.get("databook_promoted"):
            merged["databook_promoted"] = legacy.get("databook_promoted")
        out["spec"] = merged
        sources = list(out.get("sources") or [])
        for s in (hp_spec.get("primary_sources") or legacy.get("sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        out["sources"] = sources
        document = render_historical_performance_markdown(
            str(out.get("agentName") or "Historical Performance"),
            merged,
            sources=sources,
        )
        out["document"] = document
        out["summary"] = str(
            hp_spec.get("insight_snapshot") or out.get("summary") or ""
        )[:600]
        findings: list[str] = []
        if hp_spec.get("trend_headline") and not str(
            hp_spec.get("trend_headline")
        ).startswith("Information"):
            findings.append(str(hp_spec["trend_headline"])[:200])
        facts = [
            f for f in (hp_spec.get("period_facts") or [])
            if isinstance(f, dict) and f.get("value") is not None
        ]
        if facts:
            periods = {str(f.get("period")) for f in facts}
            findings.append(f"{len(periods)} accounting period(s) published")
        cim_gaps = [
            r for r in (hp_spec.get("accounts_vs_cim") or [])
            if isinstance(r, dict)
            and str(r.get("difference") or "") not in {"", "Aligned"}
            and not str(r.get("difference") or "").startswith("Information")
        ]
        if cim_gaps:
            findings.append(f"{len(cim_gaps)} accounts-vs-CIM gap(s)")
        if merged.get("databook_promoted"):
            findings.append(
                f"Databook promoted · {len(merged.get('pl_lines') or [])} P&L line(s)"
            )
        qv, rv = hp_spec.get("quality_verdict"), hp_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        # Fall back to legacy findings if composer thin
        if not findings:
            findings = findings_from_financial_spec(role.slug, merged)[:8]
        out["findings"] = findings[:8]

    if role.slug == "revenue_quality":
        from agetic_cdd_api.agent_document_revenue_quality import (
            build_revenue_quality_spec,
            render_revenue_quality_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = out.get("spec") if isinstance(out.get("spec"), dict) else {}
        # Soft-fill retention/mix from buying_behavior when present in prior chain
        prior_buying = None
        try:
            from agetic_cdd_api.services_pipeline import read_agent_output_file

            disk = read_agent_output_file(deal, agent_key="buying_behavior") or {}
            if isinstance(disk.get("spec"), dict):
                prior_buying = disk["spec"]
        except Exception:
            prior_buying = None
        if prior_buying and isinstance(legacy.get("revenue_mix"), dict):
            for src_key in ("online_sales_pct", "fleet_revenue_pct"):
                if (
                    legacy["revenue_mix"].get(src_key) is None
                    and prior_buying.get(src_key) is not None
                ):
                    legacy["revenue_mix"][src_key] = prior_buying[src_key]
        elif prior_buying:
            legacy.setdefault("revenue_mix", {})
            if isinstance(legacy["revenue_mix"], dict):
                for src_key in ("online_sales_pct", "fleet_revenue_pct"):
                    if prior_buying.get(src_key) is not None:
                        legacy["revenue_mix"].setdefault(src_key, prior_buying[src_key])

        rq_spec = build_revenue_quality_spec(
            deal,
            index=index,
            company=str(out.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(out.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **rq_spec}
        out["spec"] = merged
        sources = list(out.get("sources") or [])
        for s in (rq_spec.get("primary_sources") or legacy.get("sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        out["sources"] = sources
        document = render_revenue_quality_markdown(
            str(out.get("agentName") or "Revenue Quality"),
            merged,
            sources=sources,
        )
        out["document"] = document
        out["summary"] = str(
            rq_spec.get("insight_snapshot") or out.get("summary") or ""
        )[:600]
        findings = []
        split_n = sum(
            1 for r in (rq_spec.get("revenue_split") or [])
            if isinstance(r, dict) and isinstance(r.get("share_pct"), (int, float))
            and "reconcile" not in str(r.get("bucket") or "").lower()
        )
        if split_n:
            findings.append(f"{split_n} durability bucket(s) sized")
        ret = rq_spec.get("retention_metrics") or {}
        if isinstance(ret, dict) and ret.get("nrr_pct") is not None:
            findings.append(f"NRR {ret['nrr_pct']:g}%")
        if isinstance(ret, dict) and ret.get("grr_pct") is not None:
            findings.append(f"GRR {ret['grr_pct']:g}%")
        nonrep = [
            r for r in (rq_spec.get("non_repeating") or [])
            if isinstance(r, dict)
            and r.get("item")
            and not str(r.get("item")).startswith("Information")
        ]
        if nonrep:
            findings.append(f"{len(nonrep)} non-repeating item(s)")
        qv, rv = rq_spec.get("quality_verdict"), rq_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if not findings:
            findings = findings_from_financial_spec(role.slug, merged)[:8]
        out["findings"] = findings[:8]

    if role.slug == "capital_structure":
        from agetic_cdd_api.agent_document_capital_structure import (
            build_capital_structure_spec,
            render_capital_structure_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = out.get("spec") if isinstance(out.get("spec"), dict) else {}
        cs_spec = build_capital_structure_spec(
            deal,
            index=index,
            company=str(out.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(out.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **cs_spec}
        out["spec"] = merged
        sources = list(out.get("sources") or [])
        for s in (cs_spec.get("primary_sources") or legacy.get("sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        out["sources"] = sources
        document = render_capital_structure_markdown(
            str(out.get("agentName") or "Capital Structure"),
            merged,
            sources=sources,
        )
        out["document"] = document
        out["summary"] = str(
            cs_spec.get("insight_snapshot") or out.get("summary") or ""
        )[:600]
        findings = []
        fac_n = sum(
            1 for f in (cs_spec.get("facilities") or [])
            if isinstance(f, dict)
            and isinstance(f.get("drawn_balance"), (int, float))
        )
        if fac_n:
            findings.append(f"{fac_n} facility(ies) with balances")
        if cs_spec.get("debt_total_usd_m") is not None:
            findings.append(f"Gross debt ~{cs_spec['debt_total_usd_m']:g} USD M")
        findings.append(
            "Schedule complete"
            if cs_spec.get("schedule_complete")
            else "Schedule incomplete — leverage withheld"
        )
        gaps = cs_spec.get("schedule_gaps") or []
        if gaps:
            findings.append(f"{len(gaps)} schedule gap(s)")
        qv, rv = cs_spec.get("quality_verdict"), cs_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if not findings:
            findings = findings_from_financial_spec(role.slug, merged)[:8]
        out["findings"] = findings[:8]

    return out


def _build_risk_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
) -> dict[str, Any]:
    payload = _build_extracted_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        prior=prior,
        cache=cache,
        slice_id="deep_dive_s6",
        extract_fn=extract_risk_spec,
        findings_fn=findings_from_risk_spec,
    )

    if role.slug == "market_risk":
        from agetic_cdd_api.agent_document_market_risk import (
            build_market_risk_spec,
            render_market_risk_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        mr_spec = build_market_risk_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **mr_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (mr_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_market_risk_markdown(
            str(payload.get("agentName") or "Market Risk"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            mr_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings = []
        risks = [
            r for r in (mr_spec.get("external_risks") or [])
            if isinstance(r, dict)
            and r.get("risk")
            and not str(r.get("risk")).startswith("Information")
        ]
        if risks:
            findings.append(f"{len(risks)} external risk(s)")
        sized = [r for r in risks if r.get("sized")]
        if sized:
            findings.append(f"{len(sized)} sized exposure(s)")
        struct = [
            p for p in (mr_spec.get("price_vs_structure") or [])
            if isinstance(p, dict)
            and "structure" in str(p.get("classification") or "").lower()
        ]
        if struct:
            findings.append(f"{len(struct)} structure protection(s)")
        qv, rv = mr_spec.get("quality_verdict"), mr_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    if role.slug == "internal_risk":
        from agetic_cdd_api.agent_document_internal_risk import (
            build_internal_risk_spec,
            render_internal_risk_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        ir_spec = build_internal_risk_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **ir_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (ir_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_internal_risk_markdown(
            str(payload.get("agentName") or "Internal Risk"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            ir_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings = []
        kps = [
            r for r in (ir_spec.get("key_person_exposure") or [])
            if isinstance(r, dict)
            and r.get("person")
            and not str(r.get("person")).startswith("Information")
        ]
        if kps:
            findings.append(f"{len(kps)} key-person exposure(s)")
        obs = [
            o for o in (ir_spec.get("observed_weaknesses") or [])
            if isinstance(o, dict) and str(o.get("status") or "") == "Observed"
        ]
        if obs:
            findings.append(f"{len(obs)} observed control weakness(es)")
        tested_n = sum(
            1 for t in (ir_spec.get("control_testing") or [])
            if isinstance(t, dict) and str(t.get("tested") or "") == "Tested"
        )
        untested_n = sum(
            1 for t in (ir_spec.get("control_testing") or [])
            if isinstance(t, dict) and "not tested" in str(t.get("tested") or "").lower()
        )
        if tested_n or untested_n:
            findings.append(f"{tested_n} tested / {untested_n} untested control(s)")
        qv, rv = ir_spec.get("quality_verdict"), ir_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    if role.slug == "growth_opportunities":
        from agetic_cdd_api.agent_document_growth_opportunities import (
            build_growth_opportunities_spec,
            render_growth_opportunities_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        go_spec = build_growth_opportunities_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **go_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (go_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_growth_opportunities_markdown(
            str(payload.get("agentName") or "Growth Opportunities"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            go_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings = []
        opts = [
            o for o in (go_spec.get("options") or [])
            if isinstance(o, dict)
            and o.get("option")
            and not str(o.get("option")).startswith("Information")
        ]
        if opts:
            findings.append(f"{len(opts)} growth option(s)")
        evidenced = [o for o in opts if o.get("evidence_status") == "Evidenced"]
        if evidenced:
            findings.append(f"{len(evidenced)} evidenced")
        hypotheses = [o for o in opts if o.get("evidence_status") == "Hypothesis"]
        if hypotheses:
            findings.append(f"{len(hypotheses)} hypothesis")
        upside = [o for o in opts if "Additional" in str(o.get("plan_status") or "")]
        if upside:
            findings.append(f"{len(upside)} additional vs plan")
        qv, rv = go_spec.get("quality_verdict"), go_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    if role.slug == "synergies":
        from agetic_cdd_api.agent_document_synergies import (
            build_synergies_spec,
            render_synergies_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        syn_spec = build_synergies_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **syn_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (syn_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_synergies_markdown(
            str(payload.get("agentName") or "Synergies"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            syn_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings = []
        buyer = syn_spec.get("buyer") if isinstance(syn_spec.get("buyer"), dict) else {}
        if buyer.get("named"):
            findings.append(f"Named buyer: {buyer.get('buyer_name')}")
            if syn_spec.get("underwritable"):
                findings.append("Underwritable (bottom-up)")
            else:
                findings.append("Not underwritable — amounts missing")
            cost_n = sum(
                1 for r in (syn_spec.get("cost_synergies") or [])
                if isinstance(r, dict) and r.get("underwritable")
            )
            if cost_n:
                findings.append(f"{cost_n} cost synergy line(s)")
        else:
            findings.append("No named acquirer — cannot underwrite")
            hyp = [
                h for h in (syn_spec.get("hypotheses") or [])
                if isinstance(h, dict) and h.get("hypothesis")
            ]
            if hyp:
                findings.append(f"{len(hyp)} hypothesis theme(s)")
        qv, rv = syn_spec.get("quality_verdict"), syn_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    return payload


def _build_agent_output(
    deal: Deal,
    *,
    role: DeepDiveRole,
    index: dict,
    foundation: dict | None,
    prior: dict[str, dict],
    cache: TextCache | None = None,
) -> dict[str, Any]:
    if role.slug in MARKET_SLUGS:
        return _build_market_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            prior=prior,
            cache=cache,
        )
    if role.slug in COMPETITIVE_SLUGS:
        return _build_competitive_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            prior=prior,
            cache=cache,
        )
    if role.slug in CUSTOMER_SLUGS:
        return _build_customer_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            prior=prior,
            cache=cache,
        )
    if role.slug in OPS_SLUGS:
        return _build_ops_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            prior=prior,
            cache=cache,
        )
    if role.slug in FINANCIAL_SLUGS:
        return _build_financial_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            prior=prior,
            cache=cache,
        )
    if role.slug in RISK_SLUGS:
        return _build_risk_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            prior=prior,
            cache=cache,
        )

    docs = _bind_documents(index, role)
    sources = [str(d.get("filename") or d.get("name") or "") for d in docs if d.get("filename") or d.get("name")]
    coverage = "full" if docs else "missing"
    excerpts = [_excerpt(deal, doc, cache=cache) for doc in docs[:2]]
    findings: list[str] = []
    for text in excerpts:
        if text:
            findings.append(_clip(text, 220) if len(text) > 220 else text)
    findings.extend(_foundation_snippets(foundation, role.foundation_deps))
    for dep in role.depends_on:
        upstream = prior.get(dep)
        if upstream and upstream.get("summary"):
            findings.append(f"Uses {dep}: {_clip(str(upstream['summary']), 200)}")
    if not findings:
        findings = [
            f"No strong VDR bind for {role.name}; skeleton output recorded for Findings Store.",
        ]
    empty = coverage == "missing"
    status = "empty_vdr" if empty else "completed"
    target = deal.company or deal.name or "the company"
    lead = findings[0] if findings else f"Skeleton output for {role.name}."
    summary = (
        f"{role.spec_output} for {target} "
        f"({coverage} bind · {len(sources)} source(s)). "
        + lead
    )
    return {
        "stub": False,
        "slice": "deep_dive_s0",
        "status": status,
        "empty_vdr": empty,
        "extract_source": "vdr" if not empty else "none",
        "agent_key": role.slug,
        "agentName": role.name,
        "dd_code": role.code,
        "track": role.track,
        "src": role.src,
        "description": role.spec_output,
        "phase_id": "deep_dive",
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": target,
        "sources": sources,
        "source_coverage": coverage,
        "depends_on": list(role.depends_on),
        "foundation_deps": list(role.foundation_deps),
        "summary": _clip(summary, 600),
        "findings": findings[:8],
        "spec": {
            "document": role.spec_output,
            "dd_code": role.code,
            "track": role.track,
            "empty": empty,
            "metrics": {},
            "notes": findings[:3],
            "extract_source": "vdr" if not empty else "none",
            "vdr_backed": not empty,
        },
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{role.slug}.json",
    }


def _write_findings(deal: Deal, *, outputs: dict[str, dict], full_phase: bool) -> dict:
    merged = dict(outputs)
    if not full_phase:
        existing = load_deep_dive_findings(deal)
        agents = (existing or {}).get("agents") if isinstance(existing, dict) else None
        if isinstance(agents, dict):
            for slug, entry in agents.items():
                if slug not in merged and isinstance(entry, dict):
                    merged[slug] = _store_entry_as_payload(entry)
    store = build_findings_store(
        deal=deal,
        generated_at=utc_now_iso(),
        agent_outputs=merged,
    )
    write_deep_dive_findings(deal, store)
    return store


def iter_deep_dive_progress(
    db: Session,
    *,
    deal: Deal,
    agent_keys: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield progress events as each DAG node runs; final event is type=result."""
    index = load_library_index(deal)
    if index is None:
        index = ingest_vdr_to_library(db, deal=deal)
    foundation = load_foundation_context(deal)

    # Soft-fill display name / sector from CIM/profile when deal card is a placeholder
    try:
        from agetic_cdd_api.services_accounts_extract import (
            infer_sector_id_from_corpus,
            is_placeholder_company,
            resolve_target_display_name,
        )

        display = resolve_target_display_name(deal, index=index, foundation=foundation)
        if display and is_placeholder_company(deal.company or deal.name, deal.slug):
            deal.company = display
        # Sector: prefer organics over logistics-hauling false positive
        corpus_bits: list[str] = []
        if isinstance(foundation, dict):
            roles = foundation.get("roles") or {}
            if isinstance(roles, dict):
                for code in ("F-05", "F-01"):
                    entry = roles.get(code)
                    if isinstance(entry, dict):
                        corpus_bits.append(str((entry.get("spec") or {}).get("insight_snapshot") or ""))
                        corpus_bits.append(str((entry.get("spec") or {}).get("legal_name") or ""))
        try:
            from agetic_cdd_api.services_pipeline import read_agent_output_file

            bg = read_agent_output_file(deal, agent_key="company_background") or {}
            corpus_bits.append(str((bg.get("spec") or {}).get("insight_snapshot") or ""))
        except Exception:
            pass
        sid = infer_sector_id_from_corpus("\n".join(corpus_bits))
        if sid != "generic" and (not deal.sector or deal.sector in {"generic", "logistics"}):
            # Only override logistics when organics evidence is present
            if sid == "waste_organics" or not deal.sector or deal.sector == "generic":
                deal.sector = sid
        db.add(deal)
        db.commit()
    except Exception:
        db.rollback()

    requested = [k for k in (agent_keys or PHASE3_AGENT_KEYS) if k in PHASE3_AGENT_KEYS]
    if not requested:
        yield {"type": "result", "result": {}}
        return

    full_phase = not agent_keys or set(requested) == set(PHASE3_AGENT_KEYS)
    cascade_plan: dict[str, Any] | None = None
    if full_phase:
        order = topo_order(None)
        cascade_triggers: list[str] = []
    else:
        cascade_plan = plan_cascade_rerun(deal, requested)
        order = list(cascade_plan.get("agent_keys") or cascade_run_order(requested))
        cascade_triggers = list(cascade_plan.get("trigger") or requested)

    frozen = frozen_upstream_slugs(order)
    prior = _hydrate_stored_outputs(deal, frozen)
    outputs: dict[str, dict] = dict(prior)
    text_cache: TextCache = OrderedDict()
    rerun_slugs = set(order)
    cascade_trigger = cascade_triggers[0] if cascade_triggers else ""

    company = deal.company or deal.name or "deal"
    if cascade_plan and cascade_triggers:
        blast = cascade_plan.get("blast_radius") or []
        yield {
            "type": "log",
            "message": (
                f"Cascade re-run from {cascade_trigger}: "
                f"{len(order)} agent(s)"
                + (f" (+{len(blast)} downstream)" if blast else "")
            ),
            "level": "INFO",
        }
    yield {"type": "log", "message": f"Profiling {company} fact base…", "level": "INFO"}

    for slug in order:
        role = role_by_slug(slug)
        if role is None:
            continue

        yield {
            "type": "agent_started",
            "agent_key": role.slug,
            "agent": role.name,
            "agent_name": role.name,
            "id": role.slug,
            "name": role.name,
            "phase_id": "deep_dive",
            "stage_title": role.stage_key.replace("_", " ").title(),
            "stage_key": role.stage_key,
            "src": role.src,
        }
        yield {"type": "log", "message": f"Agent started: {role.name}", "level": "INFO"}

        blocked = next(
            (dep for dep in role.depends_on if prior.get(dep, {}).get("status") == "failed"),
            None,
        )
        # Market Definition perimeter gate: incomplete perimeter blocks other market agents.
        if not blocked and "market_definition" in role.depends_on:
            from agetic_cdd_api.agent_document_market_definition import market_definition_approved

            md_prior = prior.get("market_definition") or {}
            md_spec = md_prior.get("spec") if isinstance(md_prior.get("spec"), dict) else {}
            gate = md_spec.get("approval_gate") if isinstance(md_spec.get("approval_gate"), dict) else {}
            if (
                md_prior
                and gate.get("status") == "blocked"
                and not market_definition_approved(md_spec)
            ):
                blocked = "market_definition"
        if blocked:
            payload = _failed_agent_payload(
                deal,
                role=role,
                error=f"{blocked} failed" if blocked != "market_definition" else (
                    "Market Definition perimeter incomplete — approve before running other market agents"
                ),
                blocked_by=blocked,
            )
        else:
            try:
                payload = _build_agent_output(
                    deal,
                    role=role,
                    index=index or {},
                    foundation=foundation,
                    prior=prior,
                    cache=text_cache,
                )
            except Exception as exc:  # noqa: BLE001 — isolate extractor faults
                logger.exception("Deep Dive agent %s failed", role.slug)
                payload = _failed_agent_payload(
                    deal,
                    role=role,
                    error=str(exc) or exc.__class__.__name__,
                )
                yield {
                    "type": "log",
                    "message": f"Agent failed: {role.name} ({exc})",
                    "level": "ERROR",
                }
        prior[role.slug] = payload
        if role.slug in rerun_slugs and cascade_triggers:
            reason = "missing_upstream" if role.slug in (cascade_plan or {}).get("missing_upstream", []) else (
                "trigger" if role.slug == cascade_trigger else "blast_radius"
            )
            payload = _apply_cascade_tags(
                payload,
                trigger=cascade_trigger,
                slug=role.slug,
                reason=reason,
            )
            prior[role.slug] = payload
        outputs[role.slug] = payload
        yield {
            "type": "agent_completed" if payload.get("status") != "failed" else "agent_failed",
            "agent_key": role.slug,
            "status": payload.get("status"),
            "message": payload.get("error") or payload.get("summary"),
            "output": payload,
        }

    store = _write_findings(deal, outputs=outputs, full_phase=full_phase)
    present = len(store.get("completeness", {}).get("present_agents") or [])
    yield {
        "type": "log",
        "message": f"Deep Dive Findings Store written ({present}/24)",
        "level": "INFO",
    }
    yield {"type": "result", "result": outputs}


def run_deep_dive(
    db: Session,
    *,
    deal: Deal,
    agent_keys: list[str] | None = None,
    on_event: EventCb | None = None,
) -> dict[str, dict]:
    """Run Deep Dive agents in DAG order; write outputs + Findings Store."""
    outputs: dict[str, dict] = {}
    for event in iter_deep_dive_progress(db, deal=deal, agent_keys=agent_keys):
        if event.get("type") == "result":
            result = event.get("result")
            outputs = result if isinstance(result, dict) else {}
            continue
        _emit(on_event, event)
    return outputs


def iter_deep_dive_events(
    db: Session,
    *,
    deal: Deal,
    agent_keys: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield DIQ-shaped progress events in real time as each agent executes."""
    yield {
        "type": "pipeline_started",
        "pipeline_id": deal.id,
        "name": "Phase: Deep Dive",
    }
    yield {"type": "log", "message": "Phase: Deep Dive started", "level": "INFO"}
    yield {
        "type": "phase_started",
        "phase_id": "deep_dive",
        "id": "deep_dive",
        "name": "Deep Dive",
    }

    outputs: dict[str, dict] = {}
    for event in iter_deep_dive_progress(db, deal=deal, agent_keys=agent_keys):
        if event.get("type") == "result":
            result = event.get("result")
            outputs = result if isinstance(result, dict) else {}
            continue
        yield event

    completed = sum(1 for p in outputs.values() if p.get("status") in {"completed", "empty_vdr"})
    yield {
        "type": "phase_completed",
        "phase_id": "deep_dive",
        "completedAgents": completed,
        "totalAgents": len(PHASE3_AGENT_KEYS),
    }
    yield {
        "type": "pipeline_completed",
        "success": True,
        "phase_id": "deep_dive",
        "agent_keys": list(outputs.keys()),
    }
    yield {"type": "done", "success": True}
    yield {"type": "result", "result": outputs}
