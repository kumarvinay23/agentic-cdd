"""Durable audit log for Gate-2-miss fin discovery runs + HITL decisions.

Append-only JSONL under ``databook/fin_discovery_audit.jsonl`` (same pattern as
``decisions.jsonl``). Each discovery recovery writes a ``discovery_run`` event;
Accept/Reject append ``hitl_accept`` / ``hitl_reject`` linked by ``run_id``.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from agetic_cdd_api.services_databook_store import _exclusive_lock, databook_dir
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

_AUDIT_FILENAME = "fin_discovery_audit.jsonl"
_MAX_CANDIDATES_IN_RUN = 25


def audit_path(deal: Any):
    return databook_dir(deal) / _AUDIT_FILENAME


def record_discovery_run(
    deal: Any,
    recovery: dict[str, Any],
    *,
    gate_before: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one miss-hook recovery as an audit run. Returns the run record."""
    run_id = str(uuid.uuid4())
    deal_id = _deal_id(deal)
    event = {
        "event": "discovery_run",
        "run_id": run_id,
        "ts": utc_now_iso(),
        "deal_id": deal_id,
        "trigger": "gate2_miss",
        "status": recovery.get("status"),
        "recovered": bool(recovery.get("recovered")),
        "llm_invoked": bool(recovery.get("llm_invoked")),
        "ranker": _slim_ranker(recovery.get("ranker")),
        "gate_before": gate_before
        or {
            "ok": False,
            "expected": recovery.get("gate_expected"),
            "summary": recovery.get("gate_summary"),
            "blockers": recovery.get("blockers"),
            "expected_files": recovery.get("expected_files"),
            "reasons": recovery.get("reasons"),
        },
        "gate_after": recovery.get("post_gate"),
        "candidate_count": recovery.get("candidate_count"),
        "candidates": [
            _slim_candidate(c)
            for c in (recovery.get("candidates") or [])[:_MAX_CANDIDATES_IN_RUN]
            if isinstance(c, dict)
        ],
        "promoted": [
            _slim_promote(p)
            for p in (recovery.get("promoted") or [])
            if isinstance(p, dict)
        ],
        "promote_skipped": [
            {
                "filename": s.get("filename"),
                "reason": s.get("reason"),
                "reasons": list(s.get("reasons") or ([s.get("reason")] if s.get("reason") else [])),
                "risk_flags": list(s.get("risk_flags") or []),
                "suggested_doc_type": s.get("suggested_doc_type"),
                "confidence": s.get("confidence"),
            }
            for s in (recovery.get("promote_skipped") or [])
            if isinstance(s, dict)
        ],
        "hitl_pending": recovery.get("hitl_pending"),
    }
    _append_event(deal, event)
    return event


def record_hitl_decision(
    deal: Any,
    *,
    action: str,
    filename: str,
    actor: str | None = None,
    run_id: str | None = None,
    doc_type: str | None = None,
    reason: str | None = None,
    post_gate_ok: bool | None = None,
    preferred_sheets: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append an Accept/Reject audit event (optionally linked to a discovery run)."""
    kind = str(action or "").strip().lower()
    if kind not in {"hitl_accept", "hitl_reject", "accept", "reject"}:
        raise ValueError(f"unsupported HITL audit action: {action}")
    event_name = "hitl_accept" if kind in {"hitl_accept", "accept"} else "hitl_reject"
    event = {
        "event": event_name,
        "run_id": run_id or _latest_run_id(deal),
        "ts": utc_now_iso(),
        "deal_id": _deal_id(deal),
        "filename": str(filename or "").strip(),
        "actor": actor,
        "doc_type": doc_type,
        "reason": (reason or "").strip() or None,
        "post_gate_ok": post_gate_ok,
        "preferred_sheets": preferred_sheets,
    }
    if extra:
        event["extra"] = extra
    _append_event(deal, event)
    return event


def load_fin_discovery_audit(deal: Any) -> list[dict[str, Any]]:
    """Load all audit events (oldest → newest)."""
    path = audit_path(deal)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed fin discovery audit line %s in %s: %s",
                    line_no,
                    path,
                    exc,
                )
                continue
            if isinstance(item, dict):
                out.append(item)
    except OSError as exc:
        logger.warning("Failed to read fin discovery audit %s: %s", path, exc)
    return out


def list_fin_discovery_audit(
    deal: Any,
    *,
    limit: int = 50,
    event: str | None = None,
) -> dict[str, Any]:
    """Return newest audit events first (optionally filtered by event type)."""
    events = load_fin_discovery_audit(deal)
    if event:
        wanted = str(event).strip().lower()
        events = [e for e in events if str(e.get("event") or "").lower() == wanted]
    newest = list(reversed(events))
    capped = newest[: max(1, int(limit))]
    runs = [e for e in events if e.get("event") == "discovery_run"]
    hitl = [
        e
        for e in events
        if e.get("event") in {"hitl_accept", "hitl_reject"}
    ]
    return {
        "deal_id": _deal_id(deal),
        "count": len(capped),
        "total": len(events),
        "run_count": len(runs),
        "hitl_count": len(hitl),
        "recovered_runs": sum(1 for r in runs if r.get("recovered")),
        "events": capped,
    }


def _append_event(deal: Any, event: dict[str, Any]) -> None:
    path = audit_path(deal)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=True, default=str)
    with _exclusive_lock(path):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()


def _latest_run_id(deal: Any) -> str | None:
    for event in reversed(load_fin_discovery_audit(deal)):
        if event.get("event") == "discovery_run" and event.get("run_id"):
            return str(event["run_id"])
    return None


def _slim_ranker(ranker: Any) -> dict[str, Any] | None:
    if not isinstance(ranker, dict):
        return None
    return {
        "status": ranker.get("status"),
        "llm_invoked": ranker.get("llm_invoked"),
        "model": ranker.get("model"),
        "error": ranker.get("error"),
    }


def _slim_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": candidate.get("rank"),
        "filename": candidate.get("filename"),
        "suggested_doc_type": candidate.get("suggested_doc_type"),
        "confidence": candidate.get("confidence"),
        "suggested_sheet": candidate.get("suggested_sheet"),
        "risk_flags": list(candidate.get("risk_flags") or []),
        "rank_source": candidate.get("rank_source"),
        "score": candidate.get("score"),
        "why": candidate.get("llm_why") or candidate.get("why"),
    }


def _slim_promote(promo: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": promo.get("filename"),
        "from_doc_type": promo.get("from_doc_type"),
        "to_doc_type": promo.get("to_doc_type"),
        "confidence": promo.get("confidence"),
        "preferred_sheets": promo.get("preferred_sheets"),
        "post_gate_ok": promo.get("post_gate_ok"),
        "ok": promo.get("ok"),
        "error": promo.get("error"),
        "quality_rejected": promo.get("quality_rejected"),
        "quality_reason": promo.get("quality_reason"),
    }


def _deal_id(deal: Any) -> str:
    return str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
