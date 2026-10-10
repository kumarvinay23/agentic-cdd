"""Report metadata store — JSON-file persistence per deal.

Each deal keeps ``{deal_folder}/reports/report_meta.json`` with an entry
per report type tracking status, job id, timestamps, and the active
storyline snapshot.  The file is the single source of truth for the
report catalog page and detail view until we move to a proper DB table.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from agetic_cdd_api.services_deals import ensure_deal_folder

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
    "fdd_report": {
        "label": "FDD Report",
        "format": "document",
        "export": "docx",
        "description": "Financial due-diligence report — Word + PDF from one report_spec; figures from approved databook only.",
    },
    "fdd_deck": {
        "label": "FDD IC Deck",
        "format": "deck",
        "export": "pptx",
        "description": "FDD IC deck — same report_spec figures as the FDD report; labelled chart axes on multi-year exhibits.",
    },
}


def _meta_path(deal_slug: str) -> Path:
    return ensure_deal_folder(deal_slug) / "reports" / "report_meta.json"


def _lock_path(deal_slug: str) -> Path:
    return ensure_deal_folder(deal_slug) / "reports" / "report_meta.lock"


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    """Cross-process exclusive lock for brief read-modify-write on report meta."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path if path.name.endswith(".lock") else path.with_name(path.name + ".lock")
    if not lock_path.exists():
        try:
            lock_path.touch()
        except OSError:
            pass

    with open(lock_path, "r+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _meta_lock(deal_slug: str) -> Iterator[None]:
    with _exclusive_lock(_lock_path(deal_slug)):
        yield


def _read_body(deal_slug: str) -> dict[str, Any]:
    p = _meta_path(deal_slug)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_body(deal_slug: str, data: dict[str, Any]) -> None:
    p = _meta_path(deal_slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=p.parent)
    tmp = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, p)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _artifact_fingerprint(filepath: Path) -> tuple[str, int]:
    """Streamed SHA256 prefix + byte size — avoids loading large artifacts into RAM."""
    hasher = hashlib.sha256()
    with filepath.open("rb") as handle:
        while chunk := handle.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()[:16], filepath.stat().st_size


def get_report(deal_slug: str, report_type: str) -> dict[str, Any] | None:
    with _meta_lock(deal_slug):
        return _read_body(deal_slug).get(report_type)


def list_reports(deal_slug: str) -> list[dict[str, Any]]:
    """Return catalog entries for all report types (always, even if never generated)."""
    with _meta_lock(deal_slug):
        all_meta = _read_body(deal_slug)
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
                "stale_databook": bool(entry.get("stale_databook")),
                "stale_release_id": entry.get("stale_release_id"),
                "stale_reason": entry.get("stale_reason"),
            })
        return result


def start_report(deal_slug: str, report_type: str) -> dict[str, Any]:
    """Mark a report as running and return the job envelope."""
    with _meta_lock(deal_slug):
        all_meta = _read_body(deal_slug)
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
        _write_body(deal_slug, all_meta)
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
    with _meta_lock(deal_slug):
        all_meta = _read_body(deal_slug)
        entry = all_meta.get(report_type, {})
        now = datetime.now(UTC).isoformat()
        if error:
            entry["status"] = "failed"
            entry["error"] = error
        else:
            entry["status"] = "ready"
            entry["ready_at"] = now
            entry["error"] = None
            # Fresh build clears databook-stale markers (G1 / C-5).
            entry.pop("stale_databook", None)
            entry.pop("stale_at", None)
            entry.pop("stale_release_id", None)
            entry.pop("stale_release_version", None)
            entry.pop("stale_reason", None)
        if storyline is not None:
            entry["storyline"] = storyline
        if sources is not None:
            entry["sources"] = sources
        if artifact_path is not None:
            entry["artifact_path"] = artifact_path
            # Content fingerprint so clients can detect a regenerated-but-same-name file.
            try:
                deal_dir = ensure_deal_folder(deal_slug)
                p = Path(artifact_path)
                filepath = p if p.is_absolute() else (deal_dir / artifact_path)
                if filepath.is_file():
                    digest, nbytes = _artifact_fingerprint(filepath)
                    entry["content_sha256"] = digest
                    entry["artifact_bytes"] = nbytes
            except OSError:
                pass
        all_meta[report_type] = entry
        _write_body(deal_slug, all_meta)


def update_storyline(deal_slug: str, report_type: str, storyline: list[dict]) -> None:
    with _meta_lock(deal_slug):
        all_meta = _read_body(deal_slug)
        entry = all_meta.get(report_type, {})
        entry["storyline"] = storyline
        all_meta[report_type] = entry
        _write_body(deal_slug, all_meta)


def mark_reports_stale_for_databook_release(
    deal_slug: str,
    *,
    release_id: str,
    release_version: int | None = None,
) -> list[str]:
    """Flag previously ready reports as stale after a new databook release (G1 / C-5).

    Does not auto-rebuild (expensive); UI/API can show ``stale_databook`` and prompt
    regenerate. Returns report_types that were marked.
    """
    marked: list[str] = []
    with _meta_lock(deal_slug):
        all_meta = _read_body(deal_slug)
        now = datetime.now(UTC).isoformat()
        for report_type, entry in list(all_meta.items()):
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "")
            if status not in {"ready", "stale"}:
                continue
            entry["stale_databook"] = True
            entry["stale_at"] = now
            entry["stale_release_id"] = release_id
            if release_version is not None:
                entry["stale_release_version"] = release_version
            entry["stale_reason"] = (
                f"Databook release {release_id} published — regenerate to refresh figures."
            )
            # Keep artifact downloadable but surface staleness in catalog/status.
            if status == "ready":
                entry["status"] = "stale"
            all_meta[report_type] = entry
            marked.append(report_type)
        if marked:
            _write_body(deal_slug, all_meta)
    return marked


def report_artifact_dir(deal_slug: str, report_type: str) -> Path:
    d = ensure_deal_folder(deal_slug) / "reports" / report_type
    d.mkdir(parents=True, exist_ok=True)
    return d
