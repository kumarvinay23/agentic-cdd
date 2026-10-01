"""Report metadata store — JSON-file persistence per deal.

Each deal keeps ``{deal_folder}/reports/report_meta.json`` with an entry
per report type tracking status, job id, timestamps, and the active
storyline snapshot.  The file is the single source of truth for the
report catalog page and detail view until we move to a proper DB table.
"""

from __future__ import annotations

import json
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_deals import ensure_deal_folder

_lock = threading.Lock()

REPORT_TYPES: dict[str, dict[str, str]] = {
    "cdd_deck": {
        "label": "CDD Deck",
        "format": "deck",
        "export": "pptx",
        "description": "Full commercial due-diligence deck — provenance-tracked widescreen slides from the VDR + web research across market, competition, customers, operations, financials and IC decision.",
    },
    "ic_memo": {
        "label": "IC Memo",
        "format": "document",
        "export": "pdf",
        "description": "Investment Committee memorandum — valuation range, risk assessment, go/no-go recommendation.",
    },
    "market_deck": {
        "label": "Market Intel Deck",
        "format": "deck",
        "export": "pptx",
        "description": "Market intelligence deck — market definition, sizing, growth, pricing, positioning matrices, market maps and competitive battlecards.",
    },
    "strategy_report": {
        "label": "Strategy Report",
        "format": "document",
        "export": "docx",
        "description": "Consulting-grade strategic due-diligence report — deal framing, company & management, strategy, legal/IP/ESG, with thesis, risks and verdicts.",
    },
    "ops_dashboard": {
        "label": "Operations Dashboard",
        "format": "dashboard",
        "export": "xlsx",
        "description": "Operating KPI dashboard — executive scorecard, customer, operational & risk, and financial analysis with RAG status and trends.",
    },
}


def _meta_path(deal_slug: str) -> Path:
    return ensure_deal_folder(deal_slug) / "reports" / "report_meta.json"


def _read_all(deal_slug: str) -> dict[str, Any]:
    p = _meta_path(deal_slug)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_all(deal_slug: str, data: dict[str, Any]) -> None:
    p = _meta_path(deal_slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=p.parent, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tf:
        json.dump(data, tf, indent=2, default=str)
        tmp = Path(tf.name)
    tmp.replace(p)


def get_report(deal_slug: str, report_type: str) -> dict[str, Any] | None:
    all_meta = _read_all(deal_slug)
    return all_meta.get(report_type)


def list_reports(deal_slug: str) -> list[dict[str, Any]]:
    """Return catalog entries for all 5 report types (always, even if never generated)."""
    all_meta = _read_all(deal_slug)
    result = []
    for rt, info in REPORT_TYPES.items():
        entry = all_meta.get(rt, {})
        result.append({
            "report_type": rt,
            **info,
            "status": entry.get("status", "not_generated"),
            "job_id": entry.get("job_id"),
            "started_at": entry.get("started_at"),
            "ready_at": entry.get("ready_at"),
            "storyline_count": len(entry.get("storyline", [])),
        })
    return result


def start_report(deal_slug: str, report_type: str) -> dict[str, Any]:
    """Mark a report as running and return the job envelope."""
    with _lock:
        all_meta = _read_all(deal_slug)
        job_id = f"{deal_slug}:{report_type}:{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()
        entry = all_meta.get(report_type, {})
        entry.update({
            "report_type": report_type,
            "job_id": job_id,
            "status": "running",
            "started_at": now,
            "ready_at": None,
            "error": None,
        })
        if "storyline" not in entry:
            entry["storyline"] = []
        all_meta[report_type] = entry
        _write_all(deal_slug, all_meta)
    return {"job": job_id, "report_type": report_type, "status": "running"}


def finish_report(
    deal_slug: str,
    report_type: str,
    *,
    storyline: list[dict] | None = None,
    sources: dict | None = None,
    artifact_path: str | None = None,
    error: str | None = None,
) -> None:
    """Mark a report as ready (or failed)."""
    with _lock:
        all_meta = _read_all(deal_slug)
        entry = all_meta.get(report_type, {})
        now = datetime.now(UTC).isoformat()
        if error:
            entry["status"] = "failed"
            entry["error"] = error
        else:
            entry["status"] = "ready"
            entry["ready_at"] = now
            entry["error"] = None
        if storyline is not None:
            entry["storyline"] = storyline
        if sources is not None:
            entry["sources"] = sources
        if artifact_path is not None:
            entry["artifact_path"] = artifact_path
        all_meta[report_type] = entry
        _write_all(deal_slug, all_meta)


def update_storyline(deal_slug: str, report_type: str, storyline: list[dict]) -> None:
    with _lock:
        all_meta = _read_all(deal_slug)
        entry = all_meta.get(report_type, {})
        entry["storyline"] = storyline
        all_meta[report_type] = entry
        _write_all(deal_slug, all_meta)


def report_artifact_dir(deal_slug: str, report_type: str) -> Path:
    d = ensure_deal_folder(deal_slug) / "reports" / report_type
    d.mkdir(parents=True, exist_ok=True)
    return d
