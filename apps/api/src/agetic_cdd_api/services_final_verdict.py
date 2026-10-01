"""Phase 4 Final Verdict — Slice 0 scaffold + Stage A/B/C extractors."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from agetic_cdd_api.deep_dive_findings import load_deep_dive_findings
from agetic_cdd_api.foundation_context import load_foundation_context
from agetic_cdd_api.models import Deal
from agetic_cdd_api.pipeline_catalog import PHASE4_AGENT_KEYS
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_library import (
    documents_for_agent,
    ingest_vdr_to_library,
    load_library_document,
    load_library_index,
)
from agetic_cdd_api.services_pipeline import outputs_dir, read_agent_output_file
from agetic_cdd_api.verdict_risks import (
    STAGE_A_SLUGS,
    extract_verdict_risks_from_documents,
    findings_from_verdict_risks_spec,
    flatten_library_tables,
    prepare_verdict_risk_text,
)
from agetic_cdd_api.verdict_synthesis import (
    STAGE_C_SLUGS,
    extract_verdict_synthesis_from_documents,
    findings_from_verdict_synthesis_spec,
)
from agetic_cdd_api.verdict_valuation import (
    STAGE_B_SLUGS,
    extract_verdict_valuation_from_documents,
    findings_from_verdict_valuation_spec,
)
from agetic_cdd_api.verdict_roles import role_by_slug, topo_order
from agetic_cdd_api.verdict_cascade import (
    cascade_run_order,
    plan_cascade_rerun,
)
from agetic_cdd_api.verdict_store import (
    build_verdict_store,
    load_verdict_store,
    write_verdict_store,
)

logger = logging.getLogger(__name__)

EventCb = Callable[[dict[str, Any]], None]

STAGE_TITLE = {
    "A": "Risks & Growth",
    "B": "Valuation",
    "C": "Summary & Recommendation",
}

# Bound per-document text passed to Stage A extractors (characters).
_STAGE_A_DOC_CHAR_LIMIT = 200_000
_STAGE_A_PRIORITY_MARKERS = (
    "Leadership Team",
    "Succession Risk",
    "HR Risk Assessment",
    "Compensation",
    "ESOP",
    "Organizational Health",
    "Salary Benchmarking",
)
_STAGE_B_DOC_CHAR_LIMIT = 200_000
_STAGE_B_PRIORITY_MARKERS = (
    "Comparable Company",
    "Trading Multiples",
    "Precedent Transaction",
    "Applied Range",
    "Implied EV Range",
    "DCF Model",
    "Enterprise Value (DCF)",
    "WACC",
    "Football Field",
    "Scenario Summary",
)
_STAGE_C_DOC_CHAR_LIMIT = 200_000
_STAGE_C_PRIORITY_MARKERS = (
    "Investment Pillars",
    "Investment Risks",
    "Key Positive Indicators",
    "Key Risks",
    "Overall Investment Rating",
    "OVERALL",
    "Verdict",
    "Integrated Verdict",
    "Key Monitoring Metrics",
    "Term Sheet",
    "IRR",
    "MOIC",
    "100-Day",
    "Conditions Precedent",
)


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _foundation_snippet(foundation: dict | None, code: str) -> str | None:
    roles = (foundation or {}).get("roles") if isinstance(foundation, dict) else None
    if not isinstance(roles, dict):
        return None
    entry = roles.get(code)
    if not isinstance(entry, dict):
        return None
    summary = entry.get("summary")
    if not summary:
        return None
    return f"Foundation · {code}: {_clip(str(summary), 180)}"


def _deep_dive_snippet(findings: dict | None, slug: str) -> str | None:
    agents = (findings or {}).get("agents") if isinstance(findings, dict) else None
    if not isinstance(agents, dict):
        return None
    entry = agents.get(slug)
    if not isinstance(entry, dict):
        return None
    summary = entry.get("summary")
    if not summary:
        return None
    return f"Deep Dive · {slug}: {_clip(str(summary), 180)}"


def _store_entry_as_payload(entry: dict) -> dict[str, Any]:
    return {
        "stub": False,
        "slice": entry.get("slice") or "final_verdict_s0",
        "status": entry.get("status") or "completed",
        "empty_vdr": bool(entry.get("empty_vdr")),
        "agent_key": entry.get("slug"),
        "agentName": entry.get("name"),
        "fv_code": entry.get("fv_code"),
        "stage": entry.get("stage"),
        "summary": entry.get("summary"),
        "findings": entry.get("findings") or [],
        "sources": entry.get("sources") or [],
        "spec": entry.get("spec"),
        "depends_on": entry.get("depends_on") or [],
        "foundation_deps": entry.get("foundation_deps") or [],
        "deep_dive_deps": entry.get("deep_dive_deps") or [],
        "phase_id": "final_verdict",
    }


def _hydrate_all_existing_outputs(deal: Deal) -> dict[str, dict]:
    """Load every Phase 4 agent output so partial reruns retain full upstream context."""
    out: dict[str, dict] = {}
    out_dir = outputs_dir(deal)
    for slug in PHASE4_AGENT_KEYS:
        path = out_dir / f"{slug}.json"
        stored = read_agent_output_file(deal, agent_key=slug)
        if stored is None:
            if path.is_file():
                logger.warning(
                    "Final Verdict: skipping corrupt or invalid on-disk output for %s (deal=%s)",
                    slug,
                    deal.slug,
                )
            continue
        if stored.get("agent_key") != slug:
            logger.warning(
                "Final Verdict: ignoring mismatched agent_key in %s output (deal=%s)",
                slug,
                deal.slug,
            )
            continue
        out[slug] = stored
    return out


def _foundation_role_spec(foundation: dict | None, code: str) -> dict | None:
    roles = (foundation or {}).get("roles") if isinstance(foundation, dict) else None
    if not isinstance(roles, dict):
        return None
    entry = roles.get(code)
    if not isinstance(entry, dict):
        return None
    spec = entry.get("spec")
    return spec if isinstance(spec, dict) else None


def _dd_agent_spec(findings: dict | None, slug: str) -> dict | None:
    agents = (findings or {}).get("agents") if isinstance(findings, dict) else None
    if not isinstance(agents, dict):
        return None
    entry = agents.get(slug)
    if not isinstance(entry, dict):
        return None
    spec = entry.get("spec")
    return spec if isinstance(spec, dict) else None


def _normalize_filename(filename: str) -> str:
    normalized = re.sub(r"[_\-.]+", " ", filename.lower())
    return re.sub(r"\s+", " ", normalized).strip()


_NEEDLE_PATTERN_CACHE: dict[tuple[str, ...], re.Pattern[str]] = {}


def _needle_pattern(parts: tuple[str, ...]) -> re.Pattern[str]:
    cached = _NEEDLE_PATTERN_CACHE.get(parts)
    if cached is not None:
        return cached
    if len(parts) == 1:
        compiled = re.compile(rf"\b{parts[0]}\b")
    else:
        compiled = re.compile(r"[\W_]+".join(parts))
    _NEEDLE_PATTERN_CACHE[parts] = compiled
    return compiled


@dataclass(frozen=True)
class _RoleNeedleIndex:
    """Precompiled filename needles for one agent role (computed once per bind pass)."""

    single_tokens: frozenset[str]
    multi_parts: tuple[tuple[str, ...], ...]
    multi_patterns: tuple[re.Pattern[str], ...]


def _compile_role_needles(role) -> _RoleNeedleIndex:
    singles: set[str] = set()
    multi_parts: list[tuple[str, ...]] = []
    multi_patterns: list[re.Pattern[str]] = []
    for needle in role.filename_needles:
        token = (needle or "").strip().lower()
        if not token:
            continue
        parts = tuple(re.escape(part) for part in token.split() if part)
        if not parts:
            continue
        if len(parts) == 1:
            singles.add(parts[0])
        else:
            multi_parts.append(parts)
            multi_patterns.append(_needle_pattern(parts))
    if len(multi_parts) != len(multi_patterns):
        raise ValueError("needle multi_parts/multi_patterns length mismatch")
    return _RoleNeedleIndex(
        single_tokens=frozenset(singles),
        multi_parts=tuple(multi_parts),
        multi_patterns=tuple(multi_patterns),
    )


def _needle_score(normalized: str, needle_index: _RoleNeedleIndex) -> float:
    score = 0.0
    if needle_index.single_tokens:
        tokens = set(normalized.split())
        score += 2.0 * sum(1 for token in needle_index.single_tokens if token in tokens)
    for parts, pattern in zip(needle_index.multi_parts, needle_index.multi_patterns, strict=True):
        if not parts:
            continue
        # Cheap substring gate before regex for multi-word needles.
        if all(part in normalized for part in parts) or pattern.search(normalized):
            score += 2.0
    return score


def _filename_needle_match(needle: str, filename: str, *, normalized: str | None = None) -> bool:
    """Match filename tokens; support multi-word needles with flexible delimiters."""
    token = (needle or "").strip().lower()
    if not token or not filename:
        return False
    norm = normalized if normalized is not None else _normalize_filename(filename)
    parts = tuple(re.escape(part) for part in token.split() if part)
    if not parts:
        return False
    if len(parts) == 1:
        return parts[0] in set(norm.split())
    if all(part in norm for part in parts):
        return True
    return bool(_needle_pattern(parts).search(norm))


def _truncate_verdict_text(
    text: str,
    markers: tuple[str, ...],
    *,
    limit: int,
) -> str:
    """Prefer high-signal sections when bounding very long VDR extracts."""
    if len(text) <= limit:
        return text
    sections: list[str] = []
    lower = text.lower()
    slice_budget = max(limit // max(len(markers), 1), 8_000)
    for marker in markers:
        idx = lower.find(marker.lower())
        if idx < 0:
            continue
        sections.append(text[idx : idx + slice_budget])
    if sections:
        merged = "\n".join(dict.fromkeys(sections))
        if len(merged) > limit:
            return _clip(merged, limit)
        tail_room = limit - len(merged)
        if tail_room > 0 and not merged.startswith(text[: min(len(text), 1_000)]):
            merged = f"{text[: min(tail_room, 4_000)]}\n{merged}"
        return _clip(merged, limit)
    return _clip(text, limit)


def _truncate_stage_a_text(text: str, *, limit: int = _STAGE_A_DOC_CHAR_LIMIT) -> str:
    return _truncate_verdict_text(text, _STAGE_A_PRIORITY_MARKERS, limit=limit)


def _truncate_stage_b_text(text: str, *, limit: int = _STAGE_B_DOC_CHAR_LIMIT) -> str:
    return _truncate_verdict_text(text, _STAGE_B_PRIORITY_MARKERS, limit=limit)


def _truncate_stage_c_text(text: str, *, limit: int = _STAGE_C_DOC_CHAR_LIMIT) -> str:
    return _truncate_verdict_text(text, _STAGE_C_PRIORITY_MARKERS, limit=limit)


def _stage_char_limit(stage: str) -> int:
    if stage == "C":
        return _STAGE_C_DOC_CHAR_LIMIT
    if stage == "B":
        return _STAGE_B_DOC_CHAR_LIMIT
    return _STAGE_A_DOC_CHAR_LIMIT


def _bound_source_text(text: str, *, stage: str) -> str:
    """Apply stage truncation after all preprocessing; hard-cap to stage limit."""
    limit = _stage_char_limit(stage)
    if stage == "C":
        bounded = _truncate_stage_c_text(text, limit=limit)
    elif stage == "B":
        bounded = _truncate_stage_b_text(text, limit=limit)
    else:
        bounded = _truncate_stage_a_text(text, limit=limit)
    return _clip(bounded, limit)


def _source_text(deal: Deal, doc: dict, *, stage: str = "A") -> str:
    filename = str(doc.get("filename") or doc.get("name") or "")
    loaded = load_library_document(deal, filename)
    if isinstance(loaded, dict) and loaded.get("text"):
        text = str(loaded["text"])
        table_blob = flatten_library_tables(loaded.get("tables"))
    else:
        text = str(doc.get("text") or doc.get("excerpt") or "")
        table_blob = ""
    if table_blob:
        text = f"{text}\n{table_blob}".strip()
    # Flatten tables and normalize first; only then enforce stage char limits.
    text = prepare_verdict_risk_text(text)
    return _bound_source_text(text, stage=stage)


def _stage_a_missing_deps(
    role,
    *,
    foundation_f06: dict | None,
    cost_structure: dict | None,
) -> list[str]:
    missing: list[str] = []
    if "F-06" in role.foundation_deps and not foundation_f06:
        missing.append("F-06")
    if "cost_structure" in role.deep_dive_deps and not cost_structure:
        missing.append("cost_structure")
    return missing


def _stage_a_diagnostics(
    role,
    *,
    docs: list[dict],
    foundation_f06: dict | None,
    cost_structure: dict | None,
    extract_source: str,
) -> dict[str, Any]:
    missing_deps = _stage_a_missing_deps(
        role,
        foundation_f06=foundation_f06,
        cost_structure=cost_structure,
    )
    if extract_source == "stores":
        return {
            "extract_source": "stores",
            "missing_deps": missing_deps,
            "vdr_documents_bound": len(docs),
        }
    if missing_deps:
        return {"extract_source": extract_source, "missing_deps": missing_deps}
    return {}


def _log_stage_a_fallback(
    role,
    *,
    docs: list[dict],
    foundation_f06: dict | None,
    cost_structure: dict | None,
    extract_source: str,
) -> None:
    missing_deps = _stage_a_missing_deps(
        role,
        foundation_f06=foundation_f06,
        cost_structure=cost_structure,
    )
    if not docs:
        logger.warning(
            "Final Verdict Stage A %s (%s): no VDR documents bound; needles=%s",
            role.slug,
            role.code,
            list(role.filename_needles),
        )
    if extract_source == "stores":
        logger.warning(
            "Final Verdict Stage A %s (%s): falling back to store context (VDR text unavailable)",
            role.slug,
            role.code,
        )
    if missing_deps:
        logger.warning(
            "Final Verdict Stage A %s (%s): missing upstream deps: %s (extract=%s)",
            role.slug,
            role.code,
            missing_deps,
            extract_source,
        )


def _bind_verdict_documents(index: dict, role) -> list[dict]:
    """Score and bind VDR documents using catalog routing + token boundary needles."""
    needle_index = _compile_role_needles(role)
    catalog_names = {
        str(d.get("filename") or d.get("name") or "").strip().lower()
        for d in (documents_for_agent(index, role.slug) or [])
        if (d.get("filename") or d.get("name"))
    }
    scored: list[tuple[float, dict]] = []
    for doc in index.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        filename = str(doc.get("filename") or doc.get("name") or "").strip()
        if not filename:
            continue
        lowered = filename.lower()
        normalized = _normalize_filename(filename)
        score = 0.0
        if lowered in catalog_names:
            score += 2.0
        score += _needle_score(normalized, needle_index)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:4]]


def _prior_verdict_spec(prior: dict[str, dict], slug: str) -> dict | None:
    entry = prior.get(slug)
    if not isinstance(entry, dict):
        return None
    spec = entry.get("spec")
    return spec if isinstance(spec, dict) else None


def _stage_b_missing_deps(
    role,
    *,
    market_definition: dict | None,
    historical_performance: dict | None,
    capital_structure: dict | None,
    foundation_f05: dict | None,
    compensation_alignment: dict | None,
    trading_comps: dict | None,
    precedent_transactions: dict | None,
) -> list[str]:
    missing: list[str] = []
    if "market_definition" in role.deep_dive_deps and not market_definition:
        missing.append("market_definition")
    if "historical_performance" in role.deep_dive_deps and not historical_performance:
        missing.append("historical_performance")
    if "capital_structure" in role.deep_dive_deps and not capital_structure:
        missing.append("capital_structure")
    if "F-05" in role.foundation_deps and not foundation_f05:
        missing.append("F-05")
    if "compensation_alignment" in role.depends_on and not compensation_alignment:
        missing.append("compensation_alignment")
    if "trading_comps" in role.depends_on and not trading_comps:
        missing.append("trading_comps")
    if "precedent_transactions" in role.depends_on and not precedent_transactions:
        missing.append("precedent_transactions")
    return missing


def _stage_b_diagnostics(
    role,
    *,
    docs: list[dict],
    market_definition: dict | None,
    historical_performance: dict | None,
    capital_structure: dict | None,
    foundation_f05: dict | None,
    compensation_alignment: dict | None,
    trading_comps: dict | None,
    precedent_transactions: dict | None,
    extract_source: str,
) -> dict[str, Any]:
    missing_deps = _stage_b_missing_deps(
        role,
        market_definition=market_definition,
        historical_performance=historical_performance,
        capital_structure=capital_structure,
        foundation_f05=foundation_f05,
        compensation_alignment=compensation_alignment,
        trading_comps=trading_comps,
        precedent_transactions=precedent_transactions,
    )
    if extract_source == "stores":
        return {
            "extract_source": "stores",
            "missing_deps": missing_deps,
            "vdr_documents_bound": len(docs),
        }
    if missing_deps:
        return {"extract_source": extract_source, "missing_deps": missing_deps}
    return {}


def _log_stage_b_fallback(
    role,
    *,
    docs: list[dict],
    market_definition: dict | None,
    historical_performance: dict | None,
    capital_structure: dict | None,
    foundation_f05: dict | None,
    compensation_alignment: dict | None,
    trading_comps: dict | None,
    precedent_transactions: dict | None,
    extract_source: str,
) -> None:
    missing_deps = _stage_b_missing_deps(
        role,
        market_definition=market_definition,
        historical_performance=historical_performance,
        capital_structure=capital_structure,
        foundation_f05=foundation_f05,
        compensation_alignment=compensation_alignment,
        trading_comps=trading_comps,
        precedent_transactions=precedent_transactions,
    )
    if not docs:
        logger.warning(
            "Final Verdict Stage B %s (%s): no VDR documents bound; needles=%s",
            role.slug,
            role.code,
            list(role.filename_needles),
        )
    if extract_source == "stores":
        logger.warning(
            "Final Verdict Stage B %s (%s): falling back to store context (VDR text unavailable)",
            role.slug,
            role.code,
        )
    if missing_deps:
        logger.warning(
            "Final Verdict Stage B %s (%s): missing upstream deps: %s (extract=%s)",
            role.slug,
            role.code,
            missing_deps,
            extract_source,
        )


def _stage_c_missing_deps(role, deps: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for dep in role.depends_on:
        if not deps.get(dep):
            missing.append(dep)
    return missing


def _stage_c_diagnostics(
    role,
    *,
    docs: list[dict],
    extract_source: str,
    **deps: Any,
) -> dict[str, Any]:
    missing_deps = _stage_c_missing_deps(role, deps)
    if extract_source == "stores":
        return {
            "extract_source": "stores",
            "missing_deps": missing_deps,
            "vdr_documents_bound": len(docs),
        }
    if missing_deps:
        return {"extract_source": extract_source, "missing_deps": missing_deps}
    return {}


def _log_stage_c_fallback(
    role,
    *,
    docs: list[dict],
    extract_source: str,
    **deps: Any,
) -> None:
    missing_deps = _stage_c_missing_deps(role, deps)
    if not docs:
        logger.warning(
            "Final Verdict Stage C %s (%s): no VDR documents bound; needles=%s",
            role.slug,
            role.code,
            list(role.filename_needles),
        )
    if extract_source == "stores":
        logger.warning(
            "Final Verdict Stage C %s (%s): falling back to store context (VDR text unavailable)",
            role.slug,
            role.code,
        )
    if missing_deps:
        logger.warning(
            "Final Verdict Stage C %s (%s): missing upstream deps: %s (extract=%s)",
            role.slug,
            role.code,
            missing_deps,
            extract_source,
        )


def _prepare_stage_c_context(
    role,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> tuple[dict[str, Any], bool]:
    del foundation, findings
    full = {
        "execution_risk": _prior_verdict_spec(prior, "execution_risk"),
        "compensation_alignment": _prior_verdict_spec(prior, "compensation_alignment"),
        "trading_comps": _prior_verdict_spec(prior, "trading_comps"),
        "precedent_transactions": _prior_verdict_spec(prior, "precedent_transactions"),
        "valuation_modeling": _prior_verdict_spec(prior, "valuation_modeling"),
        "ic_synthesis": _prior_verdict_spec(prior, "ic_synthesis"),
    }
    if role.slug == "recommendation":
        ctx = {
            "ic_synthesis": full["ic_synthesis"],
            "precedent_transactions": full["precedent_transactions"],
            "valuation_modeling": full["valuation_modeling"],
        }
    else:
        ctx = {k: v for k, v in full.items() if k != "ic_synthesis"}
    return ctx, any(ctx.values())


@dataclass(frozen=True)
class _StageDriverConfig:
    slice_id: str
    source_stage: str
    stage_log_label: str
    empty_domain: str
    extract_fn: Callable[..., dict[str, Any]]
    findings_fn: Callable[[str, dict[str, Any]], list[str]]
    prepare: Callable[
        [Any, dict | None, dict | None, dict[str, dict]],
        tuple[dict[str, Any], bool],
    ]
    log_fallback: Callable[..., None]
    build_diagnostics: Callable[..., dict[str, Any]]


def _prepare_stage_a_context(
    role,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> tuple[dict[str, Any], bool]:
    del role, prior
    foundation_f06 = _foundation_role_spec(foundation, "F-06")
    cost_structure = _dd_agent_spec(findings, "cost_structure")
    ctx = {
        "foundation_f06": foundation_f06,
        "cost_structure": cost_structure,
    }
    return ctx, bool(foundation_f06 or cost_structure)


def _prepare_stage_b_context(
    role,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> tuple[dict[str, Any], bool]:
    del role
    ctx = {
        "market_definition": _dd_agent_spec(findings, "market_definition"),
        "historical_performance": _dd_agent_spec(findings, "historical_performance"),
        "capital_structure": _dd_agent_spec(findings, "capital_structure"),
        "foundation_f05": _foundation_role_spec(foundation, "F-05"),
        "compensation_alignment": _prior_verdict_spec(prior, "compensation_alignment"),
        "trading_comps": _prior_verdict_spec(prior, "trading_comps"),
        "precedent_transactions": _prior_verdict_spec(prior, "precedent_transactions"),
    }
    return ctx, any(ctx.values())


def _build_stage_output(
    deal: Deal,
    *,
    role,
    index: dict,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
    driver: _StageDriverConfig,
) -> dict[str, Any]:
    docs = _bind_verdict_documents(index, role)
    sources = [
        str(d.get("filename") or d.get("name") or "")
        for d in docs
        if d.get("filename") or d.get("name")
    ]
    coverage = "full" if docs else "missing"
    doc_chunks = [
        (
            str(doc.get("filename") or doc.get("name") or ""),
            _source_text(deal, doc, stage=driver.source_stage),
        )
        for doc in docs
    ]
    has_vdr_text = any(chunk.strip() for _, chunk in doc_chunks)

    ctx, stores_available = driver.prepare(role, foundation, findings, prior)
    extract_kwargs = {**ctx, "coverage": coverage}

    if has_vdr_text:
        extract_source = "vdr"
        spec = driver.extract_fn(role.slug, doc_chunks, **extract_kwargs)
    elif stores_available:
        extract_source = "stores"
        spec = driver.extract_fn(role.slug, [], **extract_kwargs)
    else:
        extract_source = "none"
        spec = driver.extract_fn(role.slug, [], coverage=coverage)

    driver.log_fallback(role, docs=docs, extract_source=extract_source, **ctx)
    spec["extract_source"] = extract_source
    spec["vdr_backed"] = coverage != "missing"
    diagnostics = driver.build_diagnostics(
        role,
        docs=docs,
        extract_source=extract_source,
        **ctx,
    )
    if diagnostics:
        spec["diagnostics"] = diagnostics

    findings_list = driver.findings_fn(role.slug, spec)
    if extract_source == "stores" and not findings_list:
        for code in role.foundation_deps:
            bit = _foundation_snippet(foundation, code)
            if bit:
                findings_list.append(bit)
        for dd_slug in role.deep_dive_deps:
            bit = _deep_dive_snippet(findings, dd_slug)
            if bit:
                findings_list.append(bit)
    for dep in role.depends_on:
        upstream = prior.get(dep)
        if upstream and upstream.get("summary"):
            findings_list.append(f"Uses {dep}: {_clip(str(upstream['summary']), 200)}")
    if not findings_list:
        findings_list = [f"No structured {driver.empty_domain} signals for {role.name}."]

    empty_vdr = coverage == "missing" and extract_source == "none"
    status = "empty_vdr" if empty_vdr else "completed"
    if empty_vdr:
        spec["empty"] = True

    target = deal.company or deal.name or "the company"
    metrics = spec.get("metrics") if isinstance(spec.get("metrics"), dict) else {}
    metric_bits = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:4] if v is not None)
    lead = findings_list[0] if findings_list else f"Analysis for {role.name}."
    summary = (
        f"{role.spec_output} for {target} "
        f"({coverage} bind · {len(sources)} source(s) · extract={extract_source}"
        + (f" · {metric_bits}" if metric_bits else "")
        + "). "
        + lead
    )
    return {
        "stub": False,
        "slice": driver.slice_id,
        "status": status,
        "empty_vdr": empty_vdr,
        "extract_source": extract_source,
        "agent_key": role.slug,
        "agentName": role.name,
        "fv_code": role.code,
        "stage": role.stage,
        "description": role.spec_output,
        "phase_id": "final_verdict",
        "stage_key": role.stage_key,
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": target,
        "sources": sources,
        "source_coverage": coverage,
        "depends_on": list(role.depends_on),
        "foundation_deps": list(role.foundation_deps),
        "deep_dive_deps": list(role.deep_dive_deps),
        "vdr_ref": role.vdr_ref,
        "summary": summary,
        "findings": findings_list[:8],
        "spec": spec,
        "diagnostics": diagnostics,
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{role.slug}.json",
    }


_STAGE_A_DRIVER = _StageDriverConfig(
    slice_id="final_verdict_s1",
    source_stage="A",
    stage_log_label="A",
    empty_domain="HR",
    extract_fn=extract_verdict_risks_from_documents,
    findings_fn=findings_from_verdict_risks_spec,
    prepare=_prepare_stage_a_context,
    log_fallback=_log_stage_a_fallback,
    build_diagnostics=_stage_a_diagnostics,
)

_STAGE_B_DRIVER = _StageDriverConfig(
    slice_id="final_verdict_s2",
    source_stage="B",
    stage_log_label="B",
    empty_domain="valuation",
    extract_fn=extract_verdict_valuation_from_documents,
    findings_fn=findings_from_verdict_valuation_spec,
    prepare=_prepare_stage_b_context,
    log_fallback=_log_stage_b_fallback,
    build_diagnostics=_stage_b_diagnostics,
)

_STAGE_C_DRIVER = _StageDriverConfig(
    slice_id="final_verdict_s3",
    source_stage="C",
    stage_log_label="C",
    empty_domain="synthesis",
    extract_fn=extract_verdict_synthesis_from_documents,
    findings_fn=findings_from_verdict_synthesis_spec,
    prepare=_prepare_stage_c_context,
    log_fallback=_log_stage_c_fallback,
    build_diagnostics=_stage_c_diagnostics,
)


def _build_stage_c_output(
    deal: Deal,
    *,
    role,
    index: dict,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> dict[str, Any]:
    payload = _build_stage_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        findings=findings,
        prior=prior,
        driver=_STAGE_C_DRIVER,
    )
    if role.slug == "ic_synthesis":
        from agetic_cdd_api.agent_document_ic_synthesis import (
            build_ic_synthesis_spec,
            render_ic_synthesis_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        ic_spec = build_ic_synthesis_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            prior=prior,
            foundation=foundation if isinstance(foundation, dict) else None,
            findings_store=findings if isinstance(findings, dict) else None,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **ic_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (ic_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_ic_synthesis_markdown(
            str(payload.get("agentName") or "Executive Summary"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            ic_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings_list: list[str] = []
        rec = ic_spec.get("recommendation") if isinstance(ic_spec.get("recommendation"), dict) else {}
        if rec.get("stance"):
            findings_list.append(f"Stance: {str(rec['stance'])[:140]}")
        for d in (ic_spec.get("case_depends_on") or [])[:2]:
            if isinstance(d, dict) and d.get("pillar"):
                findings_list.append(f"Depends: {d['pillar']}")
        blocking = [
            b for b in (ic_spec.get("blockers") or [])
            if isinstance(b, dict) and b.get("blocks_decision")
        ]
        if blocking:
            findings_list.append(f"OPEN BLOCKER: {str(blocking[0].get('item') or '')[:120]}")
        fin = ic_spec.get("financial_picture") if isinstance(ic_spec.get("financial_picture"), dict) else {}
        if fin.get("earnings_fallen_or_negative"):
            findings_list.append("Financial: earnings negative/troughing (stated in opening)")
        qv, rv = ic_spec.get("quality_verdict"), ic_spec.get("reliance_verdict")
        if qv or rv:
            findings_list.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings_list:
            payload["findings"] = findings_list[:8]
        return payload

    if role.slug == "recommendation":
        from agetic_cdd_api.agent_document_recommendation import (
            build_recommendation_spec,
            render_recommendation_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        # Expand prior with deep-dive agents soft-loaded by the composer
        rec_spec = build_recommendation_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            prior=prior,
            findings_store=findings if isinstance(findings, dict) else None,
            sources=list(payload.get("sources") or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **rec_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (rec_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_recommendation_markdown(
            str(payload.get("agentName") or "Recommendation"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            rec_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings_list: list[str] = []
        for row in (rec_spec.get("price_actions") or [])[:1]:
            if isinstance(row, dict) and row.get("action"):
                findings_list.append(f"Price: {str(row['action'])[:140]}")
        for row in (rec_spec.get("conditions_precedent_structured") or [])[:2]:
            if isinstance(row, dict) and row.get("action"):
                findings_list.append(f"CP: {str(row['action'])[:140]}")
        for row in (rec_spec.get("post_completion_actions") or [])[:1]:
            if isinstance(row, dict) and row.get("action"):
                findings_list.append(f"Day-100: {str(row['action'])[:140]}")
        open_block = [
            o for o in (rec_spec.get("open_items") or [])
            if isinstance(o, dict) and o.get("blocks_decision")
        ]
        if open_block:
            findings_list.append(
                f"OPEN BLOCKER: {str(open_block[0].get('item') or '')[:120]}"
            )
        qv, rv = rec_spec.get("quality_verdict"), rec_spec.get("reliance_verdict")
        if qv or rv:
            findings_list.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings_list:
            payload["findings"] = findings_list[:8]
    return payload


def _build_stage_b_output(
    deal: Deal,
    *,
    role,
    index: dict,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> dict[str, Any]:
    payload = _build_stage_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        findings=findings,
        prior=prior,
        driver=_STAGE_B_DRIVER,
    )
    if role.slug == "valuation_modeling":
        from agetic_cdd_api.agent_document_valuation_modeling import (
            build_valuation_modeling_spec,
            render_valuation_modeling_markdown,
        )
        from agetic_cdd_api.settings import settings

        legacy = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
        trading = _prior_verdict_spec(prior, "trading_comps")
        precedent = _prior_verdict_spec(prior, "precedent_transactions")
        # Soft-load historical from deep-dive prior if available
        historical = None
        try:
            from agetic_cdd_api.services_pipeline import read_agent_output_file

            disk = read_agent_output_file(deal, agent_key="historical_performance") or {}
            if isinstance(disk.get("spec"), dict):
                historical = disk["spec"]
        except Exception:
            historical = None

        vm_spec = build_valuation_modeling_spec(
            deal,
            index=index,
            company=str(payload.get("target_company") or deal.company or deal.name),
            legacy_spec=legacy,
            sources=list(payload.get("sources") or []),
            trading_comps=trading,
            precedent_transactions=precedent,
            historical_performance=historical,
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        merged = {**legacy, **vm_spec}
        payload["spec"] = merged
        sources = list(payload.get("sources") or [])
        for s in (vm_spec.get("primary_sources") or []):
            if isinstance(s, str) and s and s not in sources:
                sources.append(s)
        payload["sources"] = sources
        document = render_valuation_modeling_markdown(
            str(payload.get("agentName") or "Valuation Model"),
            merged,
            sources=sources,
        )
        payload["document"] = document
        payload["summary"] = str(
            vm_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        findings_list: list[str] = []
        earn = vm_spec.get("earnings_basis") if isinstance(vm_spec.get("earnings_basis"), dict) else {}
        if earn.get("amount") is not None and not str(earn.get("amount")).startswith("Information"):
            findings_list.append(
                f"Earnings basis: {earn.get('metric')} {earn.get('amount')} "
                f"{earn.get('unit')} ({earn.get('period')})"
            )
        comps_s = vm_spec.get("comps_summary") if isinstance(vm_spec.get("comps_summary"), dict) else {}
        if comps_s.get("median_multiple") is not None:
            findings_list.append(f"Comps median {comps_s['median_multiple']:g}x")
        prec_s = (
            vm_spec.get("precedents_summary")
            if isinstance(vm_spec.get("precedents_summary"), dict) else {}
        )
        if prec_s.get("median_multiple") is not None:
            findings_list.append(f"Precedents median {prec_s['median_multiple']:g}x")
        dcf_v = vm_spec.get("dcf_view") if isinstance(vm_spec.get("dcf_view"), dict) else {}
        if dcf_v.get("enterprise_value_usd_b") is not None:
            findings_list.append(f"DCF EV USD {dcf_v['enterprise_value_usd_b']:g}B")
        sens = (
            vm_spec.get("sensitivity_analysis")
            if isinstance(vm_spec.get("sensitivity_analysis"), dict)
            else {}
        )
        ranked = sens.get("ranked_drivers") if isinstance(sens.get("ranked_drivers"), list) else []
        if ranked and isinstance(ranked[0], dict) and ranked[0].get("assumption"):
            findings_list.append(f"Top sensitivity driver: {ranked[0]['assumption']}")
        grid = sens.get("two_driver_grid") if isinstance(sens.get("two_driver_grid"), dict) else {}
        direction = (
            grid.get("direction_check") if isinstance(grid.get("direction_check"), dict) else {}
        )
        if direction.get("status"):
            findings_list.append(f"Sensitivity grid direction {direction['status']}")
        fvr = (
            vm_spec.get("final_valuation_range")
            if isinstance(vm_spec.get("final_valuation_range"), dict)
            else {}
        )
        if fvr.get("range_published"):
            findings_list.append(
                f"Final range EV USD {fvr.get('ev_low_usd_b')}–{fvr.get('ev_high_usd_b')}B"
            )
        elif fvr:
            blocked = [
                b.get("name")
                for b in (fvr.get("blockers") or [])
                if isinstance(b, dict) and not b.get("ready")
            ]
            if blocked:
                findings_list.append(f"Final range withheld — {blocked[0]}")
        qv, rv = vm_spec.get("quality_verdict"), vm_spec.get("reliance_verdict")
        if qv or rv:
            findings_list.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings_list:
            payload["findings"] = findings_list[:8]
    return payload


def _build_stage_a_output(
    deal: Deal,
    *,
    role,
    index: dict,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> dict[str, Any]:
    return _build_stage_output(
        deal,
        role=role,
        index=index,
        foundation=foundation,
        findings=findings,
        prior=prior,
        driver=_STAGE_A_DRIVER,
    )


def _build_agent_output(
    deal: Deal,
    *,
    role,
    index: dict,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> dict[str, Any]:
    if role.slug in STAGE_A_SLUGS:
        return _build_stage_a_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            findings=findings,
            prior=prior,
        )
    if role.slug in STAGE_B_SLUGS:
        return _build_stage_b_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            findings=findings,
            prior=prior,
        )
    if role.slug in STAGE_C_SLUGS:
        return _build_stage_c_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            findings=findings,
            prior=prior,
        )
    return _build_stub_output(
        deal,
        role=role,
        foundation=foundation,
        findings=findings,
        prior=prior,
    )


def _build_stub_output(
    deal: Deal,
    *,
    role,
    foundation: dict | None,
    findings: dict | None,
    prior: dict[str, dict],
) -> dict[str, Any]:
    bullet_findings: list[str] = []
    for code in role.foundation_deps:
        bit = _foundation_snippet(foundation, code)
        if bit:
            bullet_findings.append(bit)
    for slug in role.deep_dive_deps:
        bit = _deep_dive_snippet(findings, slug)
        if bit:
            bullet_findings.append(bit)
    for dep in role.depends_on:
        upstream = prior.get(dep)
        if upstream and upstream.get("summary"):
            bullet_findings.append(f"Uses {dep}: {_clip(str(upstream['summary']), 200)}")

    if not bullet_findings:
        bullet_findings = [
            f"Skeleton {role.spec_output} for Final Verdict Slice 0; "
            f"VDR bind ({role.vdr_ref or 'n/a'}) arrives in later slices.",
        ]

    target = deal.company or deal.name or "the company"
    lead = bullet_findings[0]
    summary = (
        f"{role.spec_output} for {target} "
        f"(Stage {role.stage} · {len(bullet_findings)} context line(s)). "
        + lead
    )
    return {
        "stub": False,
        "slice": "final_verdict_s0",
        "status": "completed",
        "empty_vdr": False,
        "extract_source": "stores",
        "agent_key": role.slug,
        "agentName": role.name,
        "fv_code": role.code,
        "stage": role.stage,
        "description": role.spec_output,
        "phase_id": "final_verdict",
        "stage_key": role.stage_key,
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": target,
        "sources": [],
        "source_coverage": "stores",
        "depends_on": list(role.depends_on),
        "foundation_deps": list(role.foundation_deps),
        "deep_dive_deps": list(role.deep_dive_deps),
        "vdr_ref": role.vdr_ref,
        "summary": summary,
        "findings": bullet_findings[:8],
        "spec": {
            "empty": True,
            "document": role.spec_output,
            "stage": role.stage,
            "fv_code": role.code,
        },
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{role.slug}.json",
    }


def _write_store(
    deal: Deal,
    *,
    outputs: dict[str, dict],
    full_phase: bool,
) -> dict:
    merged = dict(outputs)
    if not full_phase:
        existing = load_verdict_store(deal)
        agents = (existing or {}).get("agents") if isinstance(existing, dict) else None
        if isinstance(agents, dict):
            for slug, entry in agents.items():
                if slug not in merged and isinstance(entry, dict):
                    merged[slug] = _store_entry_as_payload(entry)
    store = build_verdict_store(
        deal=deal,
        generated_at=utc_now_iso(),
        agent_outputs=merged,
    )
    write_verdict_store(deal, store)
    return store


def _apply_cascade_tags(
    payload: dict[str, Any],
    *,
    trigger: str,
    reason: str = "blast_radius",
) -> dict[str, Any]:
    tagged = dict(payload)
    tagged["cascade"] = {
        "rerun": True,
        "trigger": trigger,
        "reason": reason,
        "orchestrator": "final_verdict_s4",
    }
    return tagged


def _emit(on_event: EventCb | None, event: dict[str, Any]) -> None:
    if on_event:
        on_event(event)


def iter_final_verdict_progress(
    db: Session,
    *,
    deal: Deal,
    agent_keys: list[str] | None = None,
    lifecycle: bool = False,
) -> Iterator[dict[str, Any]]:
    """Yield progress events as each verdict node runs; final event is type=result.

    When ``lifecycle`` is True, also emit DIQ pipeline/phase wrapper events for SSE.
    Completes with store write, optional lifecycle events, and ``{"type": "result"}``.
    Partial agent_keys runs expand via smart cascade (seeds + downstream + missing upstream).
    """
    foundation = load_foundation_context(deal, db=db)
    findings = load_deep_dive_findings(deal, db=db)
    index = load_library_index(deal)
    if index is None:
        index = ingest_vdr_to_library(db, deal=deal)

    requested = [k for k in (agent_keys or PHASE4_AGENT_KEYS) if k in PHASE4_AGENT_KEYS]
    if not requested:
        yield {"type": "result", "result": {}}
        return

    if lifecycle:
        yield {
            "type": "pipeline_started",
            "pipeline_id": deal.id,
            "name": "Phase: Final Verdict",
        }
        yield {
            "type": "phase_started",
            "phase_id": "final_verdict",
            "id": "final_verdict",
            "name": "Final Verdict",
        }

    full_phase = not agent_keys or set(requested) == set(PHASE4_AGENT_KEYS)
    cascade_plan: dict[str, Any] | None = None
    if full_phase:
        order = topo_order(requested)
        cascade_triggers: list[str] = []
    else:
        cascade_plan = plan_cascade_rerun(deal, requested)
        order = list(cascade_plan.get("agent_keys") or cascade_run_order(requested))
        cascade_triggers = list(cascade_plan.get("trigger") or requested)

    outputs: dict[str, dict] = _hydrate_all_existing_outputs(deal)
    if cascade_plan is not None:
        # Prefer hydrated upstream over re-running promoted missing deps.
        valid = {"completed", "empty_vdr"}
        promoted = set(cascade_plan.get("missing_upstream") or [])
        order = [
            slug
            for slug in order
            if slug not in promoted or outputs.get(slug, {}).get("status") not in valid
        ]
        cascade_plan["missing_upstream"] = [
            slug for slug in (cascade_plan.get("missing_upstream") or []) if slug in order
        ]
        cascade_plan["agent_keys"] = order
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
    yield {
        "type": "log",
        "message": f"Synthesizing {company} verdict from Foundation + Deep Dive stores…",
        "level": "INFO",
    }

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
            "phase_id": "final_verdict",
            "stage_title": STAGE_TITLE.get(role.stage, role.stage_key),
            "stage_key": role.stage_key,
            "fv_code": role.code,
        }

        payload = _build_agent_output(
            deal,
            role=role,
            index=index,
            foundation=foundation,
            findings=findings,
            prior=outputs,
        )
        if role.slug in rerun_slugs and cascade_triggers:
            reason = (
                "missing_upstream"
                if role.slug in (cascade_plan or {}).get("missing_upstream", [])
                else ("trigger" if role.slug == cascade_trigger else "blast_radius")
            )
            payload = _apply_cascade_tags(
                payload,
                trigger=cascade_trigger,
                reason=reason,
            )
        outputs[role.slug] = payload
        completed_event: dict[str, Any] = {
            "type": "agent_completed" if payload.get("status") != "failed" else "agent_failed",
            "agent_key": role.slug,
            "agent": role.name,
            "agent_name": role.name,
            "status": payload.get("status"),
            "message": payload.get("error") or payload.get("summary"),
            "phase_id": "final_verdict",
            "stage_key": role.stage_key,
            "fv_code": role.code,
            "output": payload,
        }
        diagnostics = payload.get("diagnostics")
        if isinstance(diagnostics, dict) and diagnostics:
            completed_event["diagnostics"] = diagnostics
        cascade_meta = payload.get("cascade")
        if isinstance(cascade_meta, dict) and cascade_meta:
            completed_event["cascade"] = cascade_meta
        yield completed_event

    store = _write_store(deal, outputs=outputs, full_phase=full_phase)
    present = len(store.get("completeness", {}).get("present_agents") or [])
    yield {
        "type": "log",
        "message": f"Verdict Store written ({present}/7)",
        "level": "INFO",
    }

    if lifecycle:
        completed = sum(
            1 for p in outputs.values() if p.get("status") in {"completed", "empty_vdr"}
        )
        yield {
            "type": "phase_completed",
            "phase_id": "final_verdict",
            "completedAgents": completed,
            "totalAgents": len(PHASE4_AGENT_KEYS),
        }
        yield {
            "type": "pipeline_completed",
            "success": True,
            "phase_id": "final_verdict",
            "agent_keys": list(outputs.keys()),
        }
        yield {"type": "done", "success": True}

    yield {"type": "result", "result": outputs}


def run_final_verdict(
    db: Session,
    *,
    deal: Deal,
    agent_keys: list[str] | None = None,
    on_event: EventCb | None = None,
) -> dict[str, dict]:
    """Run Final Verdict agents in stage/DAG order; write outputs + Verdict Store."""
    outputs: dict[str, dict] = {}
    for event in iter_final_verdict_progress(db, deal=deal, agent_keys=agent_keys):
        if event.get("type") == "result":
            result = event.get("result")
            outputs = result if isinstance(result, dict) else {}
            continue
        _emit(on_event, event)
    return outputs


def iter_final_verdict_events(
    db: Session,
    *,
    deal: Deal,
    agent_keys: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield DIQ-shaped SSE events (lifecycle + per-agent progress)."""
    yield from iter_final_verdict_progress(
        db,
        deal=deal,
        agent_keys=agent_keys,
        lifecycle=True,
    )
