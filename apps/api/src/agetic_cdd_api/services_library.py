"""Central Data Library — parse VDR bytes, classify, index, and route."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from agetic_cdd_api.foundation_roles import BIND_FILENAME_TYPES, bind_for_slug, foundation_binds, primary_role_codes_for_kind
from agetic_cdd_api.models import Deal
from agetic_cdd_api.pipeline_catalog import PHASE1_AGENT_KEYS, get_agent_meta
from agetic_cdd_api.services_extract import extract_file
from agetic_cdd_api.services_ingestion import classify_filename, utc_now_iso
from agetic_cdd_api.services_library_chunks import build_document_chunks
from agetic_cdd_api.services_vdr import library_dir, list_vdr_docs, resolved_document_path, save_docs, sync_vdr_from_disk
from agetic_cdd_api.services_zip_expand import expand_all_zips_in_vdr

CDL_CATEGORIES = (
    "deal_strategy",
    "company_management",
    "market_competition",
    "customer",
    "operations",
    "legal_esg",
    "financial",
)

CDL_LABELS = {
    "deal_strategy": "Deal / Strategy",
    "company_management": "Company / Management",
    "market_competition": "Market / Competition",
    "customer": "Customer",
    "operations": "Operations",
    "legal_esg": "Legal / ESG",
    "financial": "Financial",
}

_CDL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "financial": (
        "revenue", "ebitda", "p&l", "profit", "valuation", "balance sheet", "cash flow",
        "income", "financial", "fdd", "working capital", "margin", "forecast",
    ),
    "legal_esg": (
        "legal", "nda", "contract", "litigation", "compliance", "regulatory", "esg",
        "articles of", "privacy", "gdpr",
    ),
    "market_competition": (
        "market", "tam", "sam", "competitor", "competition", "share", "cagr", "gartner",
    ),
    "customer": (
        "customer", "churn", "nps", "retention", "cohort", "crm", "pipeline",
    ),
    "operations": (
        "supply chain", "manufacturing", "operations", "supplier", "capacity", "headcount",
    ),
    "deal_strategy": (
        "investment thesis", "cim", "teaser", "process letter", "synergy", "strategic",
    ),
    "company_management": (
        "org chart", "management", "board", "biography", "corporate overview", "articles of inc",
    ),
}

_TECH_KEYWORDS = ("architecture", "software", "patent", "ip ", "technical", "technology", "source code")

# Filename document-type wins over body keywords (CIM text always mentions revenue).
# BIND_FILENAME_TYPES (process letter, NDA, articles, org chart, teaser, CIM) match first.
_FILENAME_TYPES: tuple[tuple[str, str, str], ...] = BIND_FILENAME_TYPES + (
    (r"executive\s*summary|investment\s*thesis|information\s*memorand", "deal_strategy", "strategy"),
    (r"corporate\s*overview|company\s*profile|\bhr\b|human\s*resource|organisational|organizational|management\s*team|leadership", "company_management", "company"),
    (r"market|competition|competitor|landscape", "market_competition", "market"),
    (r"financial|fdd|valuation|p\s*&\s*l|profit\s*loss", "financial", "financial"),
    (r"commercial|customer|\bnps\b|churn|customer\s*retention", "customer", "customer"),
    (r"legal|litigation|esg|compliance|contract", "legal_esg", "legal"),
    (r"operational|operations|manufacturing|supply\s*chain", "operations", "operations"),
    (r"technical|technology|product\s*dd|software|patent|\bip\b", "operations", "technical"),
)

CDL_ROUTES: dict[str, list[str]] = {
    "deal_strategy": ["deal_context_and_objectives", "scope_and_methodology", "strategic_direction"],
    "company_management": ["company_background", "management_quality"],
    "market_competition": [
        "market_definition",
        "competitor_identification",
        "competitive_differentiation",
        "market_share_strategy",
    ],
    "customer": [
        "customer_segmentation",
        "customer_stickiness",
        "customer_satisfaction",
        "buying_behavior",
    ],
    "operations": [
        "supplier_dependence",
        "cost_structure",
        "operational_risk",
        "supply_chain_resilience",
    ],
    "legal_esg": ["regulatory_compliance", "esg_and_sustainability"],
    "financial": [
        "historical_performance",
        "revenue_quality",
        "cash_flow",
        "capital_structure",
    ],
}

_TYPE_ROUTES: dict[str, list[str]] = {
    "technical": ["ip_and_technology"],
    "company": [
        "company_background",
        "management_quality",
        "execution_risk",
        "compensation_alignment",
    ],
}

_UI_FROM_FILENAME = {
    "Financial": "financial",
    "Legal": "legal_esg",
    "Technical": "operations",
    "General": "deal_strategy",
}

_COMPANY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&'.-]*(?:[\s,]+[A-Z][A-Za-z0-9&'.-]*){0,7}\s+"
    r"(?:Limited|Ltd\.?|Inc\.?|PLC|LLC|GmbH))\b"
)
# Skip advisor / vendor entities when inferring target company from excerpts.
_ADVISOR_NAME_MARKERS = (
    "deloitte", "pwc", "kpmg", "ernst", " ey ", "mckinsey", "goldman",
    "bain ", "bcg", "accenture", "grant thornton",
)


def _haystack(filename: str, text: str) -> str:
    return f"{filename} {text}".lower()


def _filename_type(filename: str) -> tuple[str, str] | None:
    name = Path(filename).stem.lower().replace("_", " ").replace("-", " ")
    for pattern, category, kind in _FILENAME_TYPES:
        if re.search(pattern, name):
            return category, kind
    return None


def classify_cdl(*, filename: str, text: str) -> tuple[str, str | None, float]:
    """Prefer VDR document type from the filename; use body keywords as secondary."""
    blob = _haystack(filename, text)
    scores = {
        category: sum(1 for kw in keywords if kw in blob)
        for category, keywords in _CDL_KEYWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    content_best, content_score = ranked[0]
    content_second, content_second_score = ranked[1]
    named = _filename_type(filename)
    if named:
        category, _kind = named
        secondary = content_best if content_score > 0 and content_best != category else None
        if secondary is None and content_second_score > 0 and content_second != category:
            secondary = content_second
        return category, secondary, 0.92
    if content_score == 0:
        fallback = _UI_FROM_FILENAME.get(classify_filename(filename), "deal_strategy")
        return fallback, None, 0.45
    secondary = content_second if content_second_score > 0 and content_second != content_best else None
    confidence = min(0.95, 0.55 + 0.08 * content_score)
    return content_best, secondary, round(confidence, 2)


def route_agents(*, filename: str, cdl_category: str) -> list[str]:
    named = _filename_type(filename)
    if named:
        _category, kind = named
        override = _TYPE_ROUTES.get(kind)
        if override:
            return list(override)
    return list(CDL_ROUTES.get(cdl_category, CDL_ROUTES["deal_strategy"]))


def ui_category_for_cdl(cdl_category: str, *, filename: str, text: str) -> str:
    named = _filename_type(filename)
    if named and named[1] == "technical":
        return "Technical"
    if cdl_category == "financial":
        return "Financial"
    if cdl_category == "legal_esg":
        return "Legal"
    blob = _haystack(filename, "")
    if any(kw in blob for kw in ("technical", "technology", "software", "patent")):
        return "Technical"
    return "General"


def library_index_path(deal: Deal) -> Path:
    return library_dir(deal) / "index.json"


def load_library_index(deal: Deal) -> dict | None:
    path = library_index_path(deal)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _legacy_stem(filename: str) -> str:
    """Pre-hash stem format — kept for backward-compatible document loads."""
    stem = Path(filename).stem
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", stem)[:80] or "document"


def _safe_stem(filename: str) -> str:
    """Sanitize filename stem and append a short hash to prevent payload overwrites."""
    path = Path(filename)
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", path.stem)[:60] or "document"
    file_hash = hashlib.md5(filename.encode("utf-8")).hexdigest()[:8]
    return f"{stem}_{file_hash}"


_AGENT_FALLBACK = {
    "company_background": ("company_management", None),
    "management_quality": ("company_management", None),
    "execution_risk": ("company_management", None),
    "compensation_alignment": ("company_management", None),
    "strategic_direction": ("deal_strategy", None),
    "regulatory_compliance": ("legal_esg", None),
    "esg_and_sustainability": ("legal_esg", None),
    "ip_and_technology": ("operations", "technical"),
}


def documents_for_agent(index: dict, agent_key: str) -> list[dict]:
    """Prefer F-role primary/secondary binds; else routed_agents / category fallback."""
    bound = bind_for_slug(index, agent_key)
    if bound is not None:
        return list(bound["documents"])
    docs = list(index.get("documents") or [])
    matched = [doc for doc in docs if agent_key in (doc.get("routed_agents") or [])]
    if matched:
        return matched
    fallback = _AGENT_FALLBACK.get(agent_key)
    if not fallback:
        return []
    category, kind = fallback
    return [
        doc
        for doc in docs
        if doc.get("cdl_category") == category and (kind is None or doc.get("doc_kind") == kind)
    ]


def load_library_document(deal: Deal, filename: str) -> dict | None:
    doc_dir = library_dir(deal) / "documents"
    for stem in (_safe_stem(filename), _legacy_stem(filename)):
        path = doc_dir / f"{stem}.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return payload if isinstance(payload, dict) else None
    return None


def ingest_vdr_to_library(db: Session, *, deal: Deal) -> dict:
    """Parse VDR files from disk, classify from content, persist the Central Data Library."""
    # Expand any lingering zip packs so library ingest sees extractable members.
    expand_all_zips_in_vdr(deal, remove_archives=True)
    deal = sync_vdr_from_disk(db, deal)

    docs = list_vdr_docs(deal)
    parsed_docs: list[dict] = []
    index_entries: list[dict] = []
    routing: list[dict] = []
    now = utc_now_iso()
    doc_dir = library_dir(deal) / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)

    for doc in docs:
        filename = str(doc.get("filename") or doc.get("name") or "")
        row = {**doc}
        if not filename:
            row["status"] = "error"
            parsed_docs.append(row)
            continue

        path = resolved_document_path(deal, filename)
        extracted = extract_file(path)
        text = str(extracted.get("text") or "")
        tables = list(extracted.get("tables") or [])
        cdl_primary, cdl_secondary, confidence = classify_cdl(filename=filename, text=text)
        ui_category = ui_category_for_cdl(cdl_primary, filename=filename, text=text)
        agents = route_agents(filename=filename, cdl_category=cdl_primary)
        named = _filename_type(filename)
        doc_kind = named[1] if named else cdl_primary
        parse_error = extracted.get("error")
        parser = extracted.get("parser")
        status = "error" if parser in {"missing", "unsupported"} and not text else "ready"
        chunks = build_document_chunks(text, tables=tables) if status == "ready" else []

        row.update(
            {
                "status": status,
                "category": ui_category,
                "classified_at": now,
                "routed_agents": agents,
                "cdl_category": cdl_primary,
                "cdl_secondary": cdl_secondary,
                "doc_kind": doc_kind,
                "confidence": confidence,
                "char_count": len(text),
                "table_count": len(tables),
                "chunk_count": len(chunks),
                "excerpt": text[:400],
                "parse_error": parse_error,
            }
        )
        parsed_docs.append(row)

        record = {
            "filename": filename,
            "library_stem": _safe_stem(filename),
            "format": row.get("format"),
            "status": status,
            "cdl_category": cdl_primary,
            "cdl_category_label": CDL_LABELS[cdl_primary],
            "cdl_secondary": cdl_secondary,
            "doc_kind": doc_kind,
            "ui_category": ui_category,
            "confidence": confidence,
            "char_count": len(text),
            "table_count": len(tables),
            "chunk_count": len(chunks),
            "page_count": extracted.get("page_count") or 0,
            "parser": parser,
            "parse_error": parse_error,
            "routed_agents": agents,
            "foundation_roles": primary_role_codes_for_kind(doc_kind),
            "excerpt": text[:800],
        }
        index_entries.append(record)
        routing.append(
            {
                "filename": filename,
                "cdl_category": cdl_primary,
                "doc_kind": doc_kind,
                "confidence": confidence,
                "routed_agents": agents,
            }
        )
        (doc_dir / f"{_safe_stem(filename)}.json").write_text(
            json.dumps({**record, "text": text, "tables": tables, "chunks": chunks}, indent=2),
            encoding="utf-8",
        )

    counts = Counter(entry["cdl_category"] for entry in index_entries)
    index = {
        "deal_id": deal.id,
        "company": deal.company or deal.name,
        "generated_at": now,
        "status": "ready" if index_entries else "empty",
        "document_count": len(index_entries),
        "ready_count": sum(1 for entry in index_entries if entry["status"] == "ready"),
        "category_counts": {key: int(counts.get(key, 0)) for key in CDL_CATEGORIES},
        "documents": index_entries,
        "foundation_binds": foundation_binds({"documents": index_entries}),
    }
    lib = library_dir(deal)
    (lib / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (lib / "routing.json").write_text(
        json.dumps({"deal_id": deal.id, "generated_at": now, "documents": routing}, indent=2),
        encoding="utf-8",
    )
    save_docs(db, deal, parsed_docs)
    from agetic_cdd_api.services_library_search import rebuild_search_index

    rebuild_search_index(deal, index=index)
    return index


def library_index_stats(deal: Deal) -> dict[str, Any]:
    """Summarize CDL index + FTS search.db for a deal."""
    from agetic_cdd_api.services_library_search import search_db_path, search_index_stats

    index = load_library_index(deal)
    if not index:
        return {
            "document_count": 0,
            "ready_count": 0,
            "chunk_count": 0,
            "indexed_chunks": 0,
            "fts_ready": False,
            "generated_at": None,
        }
    chunk_count = sum(
        int(doc.get("chunk_count") or 0)
        for doc in (index.get("documents") or [])
        if isinstance(doc, dict)
    )
    fts = search_index_stats(deal)
    return {
        "document_count": int(index.get("document_count") or 0),
        "ready_count": int(index.get("ready_count") or 0),
        "chunk_count": chunk_count,
        "indexed_chunks": int(fts.get("chunk_count") or 0),
        "fts_ready": bool(fts.get("fts_ready")) and search_db_path(deal).is_file(),
        "generated_at": index.get("generated_at"),
        "search_db": fts.get("search_db"),
    }


def reingest_deal_library(db: Session, *, deal: Deal) -> dict[str, Any]:
    """Rebuild Central Data Library + chunk store + FTS index from VDR on disk."""
    index = ingest_vdr_to_library(db, deal=deal)
    stats = library_index_stats(deal)
    return {
        "success": True,
        "deal_id": deal.id,
        "slug": deal.slug,
        "company": deal.company or deal.name,
        "library_status": index.get("status"),
        "category_counts": index.get("category_counts") or {},
        **stats,
    }


def _docs_in(index: dict, *categories: str) -> list[dict]:
    wanted = set(categories)
    return [doc for doc in index.get("documents") or [] if doc.get("cdl_category") in wanted]


def _lead_sentences(text: str, count: int = 2) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(part for part in parts[:count] if part)


def _guess_company(docs: list[dict], fallback: str) -> str:
    """Infer target company from excerpts — fallback only; skips advisor/vendor names."""
    for doc in docs:
        match = _COMPANY_RE.search(str(doc.get("excerpt") or ""))
        if not match:
            continue
        name = re.sub(r"\s+", " ", match.group(1)).strip(" ,")
        lowered = name.lower()
        if any(marker in lowered for marker in _ADVISOR_NAME_MARKERS):
            continue
        if 4 < len(name) < 90:
            return name
    return fallback


def _target_company(deal: Deal, docs: list[dict] | None = None) -> str:
    """Prefer explicit deal metadata; infer from VDR excerpts only when company is unset."""
    explicit = str(deal.company or "").strip()
    if explicit:
        return explicit
    fallback = str(deal.name or "the company").strip()
    if docs:
        return _guess_company(docs, fallback)
    return fallback


def phase1_agent_output(deal: Deal, *, agent_key: str, index: dict) -> dict:
    meta = get_agent_meta(agent_key) or {}
    agent = meta.get("agent") or {"agentName": agent_key, "description": ""}
    docs = list(index.get("documents") or [])
    counts = dict(index.get("category_counts") or {})
    gaps = [CDL_LABELS[key] for key in CDL_CATEGORIES if not counts.get(key)]
    sources = [str(doc["filename"]) for doc in docs]
    context_docs = _docs_in(index, "deal_strategy", "company_management")
    target = _target_company(deal, context_docs or docs)
    context_sources = [str(doc["filename"]) for doc in context_docs[:4]]
    lead = ""
    for doc in context_docs:
        lead = _lead_sentences(str(doc.get("excerpt") or ""), 2)
        if lead:
            break

    if agent_key == "deal_context_and_objectives":
        from agetic_cdd_api.agent_document_deal_context import (
            build_deal_context_spec,
            render_deal_context_markdown,
        )

        spec = build_deal_context_spec(deal, index=index, company=target)
        overview = spec.get("overview") if isinstance(spec.get("overview"), dict) else {}
        drivers = spec.get("drivers") if isinstance(spec.get("drivers"), list) else []
        document_md = render_deal_context_markdown(
            str(agent.get("agentName") or "Deal Context & Objectives"),
            spec,
            sources=sources,
        )
        summary = str(spec.get("insight_snapshot") or "").strip() or (
            f"{target}: parsed {index.get('document_count', 0)} VDR files into the Central Data Library. "
            + (lead if lead else "Deal context is taken from strategy and company documents.")
        )
        findings = [f"Target: {target}"]
        for driver in drivers[:3]:
            if isinstance(driver, dict) and driver.get("text"):
                fig = driver.get("figure")
                line = str(driver["text"])
                if fig and "N/A" not in str(fig):
                    line = f"{line} [{fig}]"
                findings.append(line)
            elif driver:
                findings.append(str(driver))
        ledger = spec.get("fact_ledger") if isinstance(spec.get("fact_ledger"), list) else []
        evidenced = sum(
            1
            for r in ledger
            if isinstance(r, dict) and not str(r.get("value", "")).startswith("N/A")
        )
        if evidenced:
            findings.append(f"Fact ledger: {evidenced} evidenced / {len(ledger)} rows")
        qv = spec.get("quality_verdict")
        rv = spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if lead and lead not in findings:
            findings.append(lead)
        findings.extend(
            f"{CDL_LABELS[key]}: {counts.get(key, 0)} file(s)"
            for key in CDL_CATEGORIES
            if counts.get(key, 0)
        )
        return {
            "stub": False,
            "agent_key": agent_key,
            "agentName": agent.get("agentName", agent_key),
            "description": agent.get("description", ""),
            "phase_id": "data_ingestion",
            "deal_id": deal.id,
            "deal_name": deal.name,
            "target_company": target,
            "context_sources": context_sources,
            "library": "library/index.json",
            "document_count": index.get("document_count", 0),
            "category_counts": counts,
            "sources": sources,
            "gaps": gaps,
            "summary": summary,
            "findings": findings[:12],
            "spec": {
                **spec,
                "industry": overview.get("industry"),
                "transaction_type": overview.get("transaction_type"),
                "deal_rationale": overview.get("deal_rationale"),
                "legal_entity": overview.get("legal_entity"),
            },
            "document": document_md,
            "generated_at": utc_now_iso(),
            "output_path": f"outputs/{agent_key}.json",
        }

    covered = [CDL_LABELS[key] for key in CDL_CATEGORIES if counts.get(key)]
    from agetic_cdd_api.agent_document_scope_methodology import (
        build_scope_methodology_spec,
        render_scope_methodology_markdown,
    )

    spec = build_scope_methodology_spec(
        deal,
        index=index,
        company=target,
        covered=covered,
        gaps=gaps,
    )
    document_md = render_scope_methodology_markdown(
        str(agent.get("agentName") or "Scope & Methodology"),
        spec,
        sources=sources,
    )
    summary = str(spec.get("insight_snapshot") or "").strip() or (
        f"Coverage for {target}: "
        f"{', '.join(covered) or 'no classified sources'}. "
        + (
            f"{len(gaps)} diligence categories have no source files."
            if gaps
            else "All seven diligence categories have at least one source file."
        )
    )
    findings = [f"Covered: {label}" for label in covered]
    findings.extend(f"Gap: {label}" for label in gaps)
    counts_cov = spec.get("coverage_counts") if isinstance(spec.get("coverage_counts"), dict) else {}
    if counts_cov:
        findings.append(
            f"Questions evidenced: {counts_cov.get('questions_evidenced', '—')}/"
            f"{counts_cov.get('questions_in_scope', '—')}"
        )
        findings.append(
            f"Documents read: {counts_cov.get('documents_read', '—')}/"
            f"{counts_cov.get('documents_available', '—')}"
        )
    qv = spec.get("quality_verdict")
    rv = spec.get("reliance_verdict")
    if qv or rv:
        findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
    unfinished = spec.get("unfinished") if isinstance(spec.get("unfinished"), list) else []
    must_close = sum(
        1 for u in unfinished if isinstance(u, dict) and str(u.get("gate") or "").startswith("must")
    )
    if must_close:
        findings.append(f"Must-close unfinished: {must_close}")
    if not findings:
        findings = ["No classified sources in the current data room."]

    return {
        "stub": False,
        "agent_key": agent_key,
        "agentName": agent.get("agentName", agent_key),
        "description": agent.get("description", ""),
        "phase_id": "data_ingestion",
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": target,
        "context_sources": context_sources,
        "library": "library/index.json",
        "document_count": index.get("document_count", 0),
        "category_counts": counts,
        "sources": sources,
        "gaps": gaps,
        "summary": summary,
        "findings": findings[:12],
        "spec": spec,
        "document": document_md,
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{agent_key}.json",
    }


def ingest_phase1(db: Session, *, deal: Deal) -> dict[str, dict]:
    """Build the library and return outputs for both Phase 1 agents."""
    index = ingest_vdr_to_library(db, deal=deal)
    return {key: phase1_agent_output(deal, agent_key=key, index=index) for key in PHASE1_AGENT_KEYS}
