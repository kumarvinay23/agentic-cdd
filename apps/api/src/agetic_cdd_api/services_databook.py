"""Databook orchestration: rescan, summary, data-quality projection, reread."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_blocks import reconcile_blocks
from agetic_cdd_api.services_databook_decisions import apply_decision_overlays
from agetic_cdd_api.services_databook_extract import extract_from_library
from agetic_cdd_api.services_databook_models import (
    DatabookMeta,
    DatabookSummary,
    DataQualityResponse,
    DataQualitySummary,
    DealDatabookParams,
    RowStatus,
)
from agetic_cdd_api.services_databook_resolve import (
    apply_series_drops,
    apply_statuses_and_promote,
    assumption_issues_from_rows,
    build_data_quality_items,
    detect_conflicts,
)
from agetic_cdd_api.services_databook_store import (
    load_blocks,
    load_issues,
    load_meta,
    load_promoted,
    load_rows,
    save_blocks,
    save_issues,
    save_meta,
    save_promoted,
    save_rows,
)
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_library import load_library_index


def _params_from_env(base: DealDatabookParams | None = None) -> DealDatabookParams:
    params = base or DealDatabookParams()
    llm = os.environ.get("DATABOOK_LLM_MAP", "").strip() in {"1", "true", "TRUE", "yes"}
    return params.model_copy(update={"llm_map_enabled": llm})


def _summary_from_store(deal: Deal) -> DatabookSummary:
    from agetic_cdd_api.services_databook_excel import databook_freshness

    meta = load_meta(deal)
    rows = load_rows(deal)
    items = load_issues(deal)
    promoted = load_promoted(deal)
    blocks = load_blocks(deal)
    flags = {
        "dropped": sum(1 for i in items if i.get("kind") == "dropped"),
        "conflict": sum(1 for i in items if i.get("kind") == "conflict"),
        "failed_check": sum(1 for i in items if i.get("kind") == "failed_check"),
        "held_out": meta.held_out_count,
        "promoted": meta.promoted_count or len(promoted),
        "assumption": sum(1 for r in rows if r.assumption and r.status.value not in {"dropped"}),
        "vouched": sum(1 for r in rows if r.status == RowStatus.VOUCHED),
        "checks_passed": sum(1 for b in blocks if b.outcome == "pass"),
        "checks_failed": sum(1 for b in blocks if b.outcome == "fail"),
        "no_table": sum(1 for b in blocks if b.outcome == "no_table"),
    }
    return DatabookSummary(
        deal_id=deal.id,
        meta=meta,
        flags=flags,
        promoted_preview=promoted[:20],
        freshness=databook_freshness(deal),
    )


def rescan_databook(deal: Deal) -> DatabookSummary:
    """Re-extract from CDL cache, remap, block-check, series/conflicts, replay HITL decisions."""
    meta = load_meta(deal)
    params = _params_from_env(meta.params)

    rows, raw_blocks = extract_from_library(deal, params=params)
    blocks, block_fail_ids, failed_check_issues = reconcile_blocks(raw_blocks, params=params)

    rows, dropped_issues = apply_series_drops(rows, params=params)
    conflict_issues, hold_ids = detect_conflicts(rows)
    rows, auto_promoted = apply_statuses_and_promote(
        rows,
        hold_ids=hold_ids,
        block_fail_ids=block_fail_ids,
    )

    # Replay reviewer decisions on top of auto pipeline
    rows, decision_promoted = apply_decision_overlays(deal, rows)

    # Merge promoted: decision overrides auto for same metric+year
    promoted_by_key: dict[tuple[str, int], Any] = {
        (p.metric_key, p.fiscal_year): p for p in auto_promoted
    }
    for p in decision_promoted:
        promoted_by_key[(p.metric_key, p.fiscal_year)] = p
    promoted = list(promoted_by_key.values())

    # Drop conflicts for keys that are promoted
    resolved = {(p.metric_key, p.fiscal_year) for p in promoted}
    filtered_conflicts: list[dict[str, Any]] = []
    for item in conflict_issues:
        fy = item.get("fiscal_year")
        if fy is None:
            filtered_conflicts.append(item)
            continue
        row_ids: set[str] = set()
        for cand in item.get("candidates") or []:
            row_ids.update(cand.get("row_ids") or [])
        keys = {r.metric_key for r in rows if r.row_id in row_ids and r.metric_key}
        if any((k, int(fy)) in resolved for k in keys):
            continue
        if any(
            r.row_id in row_ids and r.status in {RowStatus.PROMOTED, RowStatus.VOUCHED, RowStatus.DROPPED}
            for r in rows
        ) and not any(
            r.row_id in row_ids and r.status in {RowStatus.HELD_OUT, RowStatus.CANDIDATE} for r in rows
        ):
            continue
        filtered_conflicts.append(item)

    filtered_fails: list[dict[str, Any]] = []
    for item in failed_check_issues:
        row_ids = set(item.get("row_ids") or [])
        if not row_ids:
            filtered_fails.append(item)
            continue
        if any(
            r.row_id in row_ids and r.status in {RowStatus.HELD_OUT, RowStatus.CANDIDATE} for r in rows
        ):
            filtered_fails.append(item)

    items = build_data_quality_items(
        dropped=dropped_issues,
        conflicts=filtered_conflicts,
        failed_checks=filtered_fails,
        assumed=assumption_issues_from_rows(rows),
    )

    save_rows(deal, rows)
    save_blocks(deal, blocks)
    save_issues(deal, items)
    save_promoted(deal, promoted)

    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.status.value] = by_status.get(row.status.value, 0) + 1

    meta = DatabookMeta(
        version=meta.version,
        last_rescan_at=utc_now_iso(),
        last_deep_at=meta.last_deep_at,
        params=params,
        row_count=len(rows),
        promoted_count=len(promoted),
        held_out_count=by_status.get("held_out", 0),
        issue_count=len(items),
    )
    save_meta(deal, meta)
    return _summary_from_store(deal)


def get_databook_summary(deal: Deal, *, ensure: bool = False) -> DatabookSummary:
    meta = load_meta(deal)
    rows = load_rows(deal)
    if ensure and meta.last_rescan_at is None and not rows:
        return rescan_databook(deal)
    return _summary_from_store(deal)


def get_data_quality(deal: Deal, *, ensure: bool = True) -> DataQualityResponse:
    items = load_issues(deal)
    meta = load_meta(deal)
    if ensure and meta.last_rescan_at is None and not items and not load_rows(deal):
        rescan_databook(deal)
        items = load_issues(deal)
    # Enrich legacy issue stores that pre-date ``assumed`` kind.
    if not any(str(i.get("kind")) == "assumed" for i in items):
        assumed = assumption_issues_from_rows(load_rows(deal))
        if assumed:
            items = [*items, *assumed]
    by_kind: dict[str, int] = {}
    for item in items:
        kind = str(item.get("kind") or "other")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    summary = DataQualitySummary(
        total=len(items),
        by_kind=by_kind,
        needs_review=len(items),
    )
    return DataQualityResponse(items=items, summary=summary)


def list_databook_rows(
    deal: Deal,
    *,
    status: str | None = None,
    metric: str | None = None,
    material_only: bool = False,
    min_abs: float | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    from agetic_cdd_api.services_databook_consume import filter_material_rows

    rows = load_rows(deal)
    out: list[dict[str, Any]] = []
    for row in rows:
        if status and row.status.value != status:
            continue
        if metric and row.metric_key != metric and (row.caption or "").lower().find(metric.lower()) < 0:
            continue
        out.append(row.model_dump(mode="json"))
    out = filter_material_rows(out, material_only=material_only, min_abs=min_abs)
    return out[:limit]


_TRIAGE_RANK = {
    "assumption": 0,
    "failed_check": 0,
    "sources_disagree": 1,
    "unread": 2,
    "not_landed": 3,
}


def list_databook_findings(deal: Deal) -> list[dict[str, Any]]:
    """Per-file trust ledger: check pass/fail counts, held-out, triage flags."""
    rows = load_rows(deal)
    items = load_issues(deal)
    blocks = load_blocks(deal)
    index = load_library_index(deal) or {}
    entries = index.get("documents") if isinstance(index, dict) else []
    if not isinstance(entries, list):
        entries = []

    by_doc: dict[str, dict[str, Any]] = {}

    def _slot(source_name: str, doc_id: str | None = None) -> dict[str, Any]:
        return by_doc.setdefault(
            source_name,
            {
                "source_name": source_name,
                "doc_id": doc_id or source_name,
                "row_count": 0,
                "held_out": 0,
                "promoted": 0,
                "dropped": 0,
                "vouched": 0,
                "conflicts": 0,
                "assumptions": 0,
                "unmapped": 0,
                "checks_passed": 0,
                "checks_failed": 0,
                "checks_total": 0,
                "no_table": False,
                "flags": [],
                "triage": None,
                "note": "",
            },
        )

    for entry in entries:
        if isinstance(entry, dict) and entry.get("filename"):
            _slot(str(entry["filename"]), str(entry.get("library_stem") or entry["filename"]))

    for row in rows:
        slot = _slot(row.source_name, row.doc_id)
        slot["row_count"] += 1
        if row.status.value == "held_out":
            slot["held_out"] += 1
        elif row.status.value == "promoted":
            slot["promoted"] += 1
        elif row.status.value == "dropped":
            slot["dropped"] += 1
        elif row.status.value == "vouched":
            slot["vouched"] += 1
        if row.assumption and row.status.value not in {"dropped"}:
            slot["assumptions"] += 1
        if row.metric_key is None and row.status.value not in {"dropped"}:
            slot["unmapped"] += 1

    for block in blocks:
        slot = _slot(block.source_name, block.doc_id)
        if block.outcome == "no_table":
            slot["no_table"] = True
            continue
        if block.outcome in {"pass", "fail"}:
            slot["checks_total"] += 1
            if block.outcome == "pass":
                slot["checks_passed"] += 1
            else:
                slot["checks_failed"] += 1

    for item in items:
        if item.get("kind") != "conflict":
            continue
        for cand in item.get("candidates") or []:
            for src in cand.get("sources") or []:
                if src in by_doc:
                    by_doc[src]["conflicts"] += 1

    for slot in by_doc.values():
        flags: list[str] = []
        if slot["assumptions"]:
            flags.append("assumption")
        if slot["conflicts"]:
            flags.append("sources_disagree")
        if slot["checks_failed"]:
            flags.append("failed_check")
        if slot["no_table"] or (slot["checks_total"] == 0 and slot["row_count"] == 0):
            flags.append("unread")
        elif slot["row_count"] and slot["promoted"] == 0 and slot["vouched"] == 0 and (
            slot["unmapped"] or slot["held_out"]
        ):
            flags.append("not_landed")

        triage = None
        for key in ("assumption", "failed_check", "sources_disagree", "unread", "not_landed"):
            if key in flags:
                triage = key
                break
        slot["flags"] = flags
        slot["triage"] = triage

        passed = slot["checks_passed"]
        failed = slot["checks_failed"]
        total = slot["checks_total"]
        if total:
            slot["note"] = f"{failed}/{total} checks failed · {slot['held_out']} rows held out"
        elif slot["no_table"]:
            slot["note"] = "No financial table found — silence is not a pass."
        elif slot["row_count"] and total == 0:
            slot["note"] = (
                f"{slot['row_count']} rows · no statement-block checks "
                f"(silence is not a pass) · {slot['held_out']} held out"
            )
        else:
            slot["note"] = "No extracted rows yet."

        slot["checks_passed"] = passed if total else None
        slot["checks_failed"] = failed if total else None
        slot["checks_total"] = total

    def sort_key(d: dict[str, Any]) -> tuple:
        triage = d.get("triage")
        rank = _TRIAGE_RANK.get(str(triage), 9) if triage else 9
        return (
            rank,
            -(d.get("checks_failed") or 0),
            -d["held_out"],
            -d["conflicts"],
            d["source_name"],
        )

    return sorted(by_doc.values(), key=sort_key)

def _reingest_vdr_file(db: Session, deal: Deal, filename: str, *, rebuild_search: bool = True) -> str:
    """Discard cached library text for one VDR file and re-extract from the original."""
    from collections import Counter

    from agetic_cdd_api.foundation_roles import foundation_binds, primary_role_codes_for_kind
    from agetic_cdd_api.services_extract import extract_file
    from agetic_cdd_api.services_library import (
        CDL_CATEGORIES,
        CDL_LABELS,
        _filename_type,
        _safe_stem,
        classify_cdl,
        load_library_index,
        route_agents,
        ui_category_for_cdl,
    )
    from agetic_cdd_api.services_library_chunks import build_document_chunks
    from agetic_cdd_api.services_library_search import rebuild_search_index
    from agetic_cdd_api.services_vdr import library_dir, list_vdr_docs, resolved_document_path, save_docs

    name = str(filename or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="filename required")

    path = resolved_document_path(deal, name)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found in VDR")

    docs = list_vdr_docs(deal)
    extracted = extract_file(path)
    text = str(extracted.get("text") or "")
    tables = list(extracted.get("tables") or [])
    cdl_primary, cdl_secondary, confidence = classify_cdl(filename=name, text=text)
    ui_category = ui_category_for_cdl(cdl_primary, filename=name, text=text)
    agents = route_agents(filename=name, cdl_category=cdl_primary)
    named = _filename_type(name)
    doc_kind = named[1] if named else cdl_primary
    parse_error = extracted.get("error")
    parser = extracted.get("parser")
    doc_status = "error" if parser in {"missing", "unsupported"} and not text else "ready"
    chunks = build_document_chunks(text, tables=tables) if doc_status == "ready" else []
    now = utc_now_iso()
    stem = _safe_stem(name)

    record = {
        "filename": name,
        "library_stem": stem,
        "format": path.suffix.lstrip(".").lower() or None,
        "status": doc_status,
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
    doc_dir = library_dir(deal) / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / f"{stem}.json").write_text(
        json.dumps({**record, "text": text, "tables": tables, "chunks": chunks}, indent=2),
        encoding="utf-8",
    )

    index = load_library_index(deal) or {
        "deal_id": deal.id,
        "documents": [],
        "status": "ready",
        "document_count": 0,
    }
    entries = [e for e in (index.get("documents") or []) if isinstance(e, dict) and e.get("filename") != name]
    entries.append(record)
    counts = Counter(str(e.get("cdl_category")) for e in entries)
    index = {
        **index,
        "deal_id": deal.id,
        "company": deal.company or deal.name,
        "generated_at": now,
        "status": "ready" if entries else "empty",
        "document_count": len(entries),
        "ready_count": sum(1 for e in entries if e.get("status") == "ready"),
        "category_counts": {key: int(counts.get(key, 0)) for key in CDL_CATEGORIES},
        "documents": entries,
        "foundation_binds": foundation_binds({"documents": entries}),
    }
    lib = library_dir(deal)
    (lib / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    if rebuild_search:
        rebuild_search_index(deal, index=index)

    updated_docs = []
    for d in docs:
        if str(d.get("filename") or d.get("name") or "") == name:
            updated_docs.append(
                {
                    **d,
                    "status": doc_status,
                    "category": ui_category,
                    "classified_at": now,
                    "routed_agents": agents,
                    "cdl_category": cdl_primary,
                }
            )
        else:
            updated_docs.append(d)
    save_docs(db, deal, updated_docs)
    return name


def reread_databook_document(db: Session, deal: Deal, filename: str) -> DatabookSummary:
    """Deep re-extract one VDR file into the library, then Rescan databook (decision replay)."""
    _reingest_vdr_file(db, deal, filename, rebuild_search=True)
    meta = load_meta(deal)
    meta = meta.model_copy(update={"last_deep_at": utc_now_iso()})
    save_meta(deal, meta)
    return rescan_databook(deal)


def deep_databook(db: Session, deal: Deal) -> DatabookSummary:
    """Discard stored library text for all VDR originals, re-extract, then Rescan."""
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_library_search import rebuild_search_index
    from agetic_cdd_api.services_vdr import list_vdr_docs

    docs = list_vdr_docs(deal)
    names: list[str] = []
    for d in docs:
        name = str(d.get("filename") or d.get("name") or "").strip()
        if name:
            names.append(name)
    # Also include library index filenames not present in docs.json
    index = load_library_index(deal) or {}
    for entry in index.get("documents") or []:
        if isinstance(entry, dict) and entry.get("filename"):
            fname = str(entry["filename"]).strip()
            if fname and fname not in names:
                names.append(fname)

    for name in names:
        try:
            _reingest_vdr_file(db, deal, name, rebuild_search=False)
        except HTTPException:
            continue

    index = load_library_index(deal)
    if index:
        rebuild_search_index(deal, index=index)

    meta = load_meta(deal)
    meta = meta.model_copy(update={"last_deep_at": utc_now_iso()})
    save_meta(deal, meta)
    return rescan_databook(deal)
