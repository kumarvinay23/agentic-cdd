"""HITL queue for Gate-2-miss fin discovery candidates that auto-promote skipped.

Pending items appear on Databook Files. Accept promotes + sheet-aware reread;
Reject records an operator decision without promoting.
"""

from __future__ import annotations

import logging
from typing import Any

from agetic_cdd_api.services_databook_store import databook_dir
from agetic_cdd_api.services_fin_discovery import (
    FIN_DOC_TYPES,
    evaluate_promote_quality,
    preferred_sheets_for_candidate,
    promote_and_reread_one,
    revert_promote_after_quality_reject,
)
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

_HITL_FILENAME = "fin_discovery_hitl.json"
_HISTORY_LIMIT = 40


def hitl_path(deal: Any):
    return databook_dir(deal) / _HITL_FILENAME


def load_fin_discovery_hitl(deal: Any) -> dict[str, Any]:
    path = hitl_path(deal)
    if not path.is_file():
        return {"deal_id": _deal_id(deal), "candidates": [], "updated_at": None}
    try:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("fin discovery HITL load failed: %s", exc)
        return {"deal_id": _deal_id(deal), "candidates": [], "updated_at": None}
    if not isinstance(raw, dict):
        return {"deal_id": _deal_id(deal), "candidates": [], "updated_at": None}
    raw.setdefault("deal_id", _deal_id(deal))
    raw.setdefault("candidates", [])
    return raw


def save_fin_discovery_hitl(deal: Any, payload: dict[str, Any]) -> dict[str, Any]:
    import json

    path = hitl_path(deal)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload)
    out["deal_id"] = _deal_id(deal)
    out["updated_at"] = utc_now_iso()
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


def list_fin_discovery_hitl(
    deal: Any,
    *,
    status: str | None = "pending",
) -> dict[str, Any]:
    """Return HITL queue; default only open (pending) suggestions."""
    payload = load_fin_discovery_hitl(deal)
    candidates = list(payload.get("candidates") or [])
    if status:
        wanted = str(status).strip().lower()
        candidates = [
            c for c in candidates if str(c.get("status") or "").lower() == wanted
        ]
    return {
        "deal_id": payload.get("deal_id") or _deal_id(deal),
        "updated_at": payload.get("updated_at"),
        "gate_summary": payload.get("gate_summary"),
        "ranker": payload.get("ranker"),
        "recovered": payload.get("recovered"),
        "count": len(candidates),
        "candidates": candidates,
    }


def persist_fin_discovery_hitl(
    deal: Any,
    recovery: dict[str, Any],
) -> dict[str, Any]:
    """Refresh pending HITL items from a discovery recovery payload."""
    previous = load_fin_discovery_hitl(deal)
    history = [
        c
        for c in (previous.get("candidates") or [])
        if str(c.get("status") or "") in {"accepted", "rejected"}
    ][-_HISTORY_LIMIT:]

    ranked = {
        str(c.get("filename") or ""): c
        for c in (recovery.get("candidates") or [])
        if isinstance(c, dict) and c.get("filename")
    }
    fresh: list[dict[str, Any]] = []

    for promo in recovery.get("promoted") or []:
        if not isinstance(promo, dict):
            continue
        name = str(promo.get("filename") or "").strip()
        if not name:
            continue
        base = dict(ranked.get(name) or {})
        fresh.append(
            _candidate_item(
                base,
                filename=name,
                status="auto_promoted",
                skip_reason=None,
                suggested_doc_type=str(
                    promo.get("to_doc_type") or base.get("suggested_doc_type") or ""
                )
                or None,
                preferred_sheets=promo.get("preferred_sheets")
                or preferred_sheets_for_candidate(base),
            )
        )

    for skip in recovery.get("promote_skipped") or []:
        if not isinstance(skip, dict):
            continue
        name = str(skip.get("filename") or "").strip()
        if not name:
            continue
        base = dict(ranked.get(name) or {})
        if skip.get("risk_flags"):
            base["risk_flags"] = list(skip.get("risk_flags") or [])
        fresh.append(
            _candidate_item(
                base,
                filename=name,
                status="pending",
                skip_reason=str(skip.get("reason") or "") or None,
                skip_reasons=list(skip.get("reasons") or []),
                suggested_doc_type=str(
                    skip.get("suggested_doc_type")
                    or base.get("suggested_doc_type")
                    or ""
                )
                or None,
                confidence=skip.get("confidence", base.get("confidence")),
                preferred_sheets=preferred_sheets_for_candidate(base),
            )
        )

    # Ranked rows never attempted (e.g. stopped after recovery) stay available for HITL.
    seen = {str(c.get("filename") or "") for c in fresh}
    for name, base in ranked.items():
        if not name or name in seen:
            continue
        fresh.append(
            _candidate_item(
                base,
                filename=name,
                status="pending",
                skip_reason="not_auto_attempted",
                preferred_sheets=preferred_sheets_for_candidate(base),
            )
        )

    payload = {
        "deal_id": _deal_id(deal),
        "gate_summary": recovery.get("gate_summary"),
        "ranker": recovery.get("ranker"),
        "recovered": bool(recovery.get("recovered")),
        "status": recovery.get("status"),
        "candidates": fresh + history,
    }
    return save_fin_discovery_hitl(deal, payload)


def accept_fin_discovery_candidate(
    deal: Any,
    *,
    filename: str,
    db: Any | None = None,
    actor: str | None = None,
    doc_type: str | None = None,
) -> dict[str, Any]:
    """Operator Accept → promote FIN_* + sheet-aware reread."""
    name = str(filename or "").strip()
    if not name:
        raise ValueError("filename is required")

    payload = load_fin_discovery_hitl(deal)
    item = _find_candidate(payload, name, statuses={"pending", "rejected"})
    if item is None:
        raise KeyError(f"no HITL candidate for {name}")

    chosen_type = str(doc_type or item.get("suggested_doc_type") or "").strip()
    if chosen_type not in FIN_DOC_TYPES:
        raise ValueError(f"invalid or missing FIN_* type: {chosen_type or '(empty)'}")

    candidate = {
        "filename": name,
        "suggested_doc_type": chosen_type,
        "suggested_sheet": item.get("suggested_sheet"),
        "statement_sheets": item.get("statement_sheets") or [],
        "preferred_sheets": item.get("preferred_sheets"),
        "rank_source": item.get("rank_source") or "hitl",
        "confidence": item.get("confidence"),
        "risk_flags": item.get("risk_flags") or [],
    }
    # Rebuild preferred sheets if only suggested_sheet is present.
    if not candidate.get("preferred_sheets"):
        candidate["preferred_sheets"] = preferred_sheets_for_candidate(candidate)

    result = promote_and_reread_one(
        deal,
        filename=name,
        doc_type=chosen_type,
        confidence=float(item.get("confidence") or 0.9),
        db=db,
        candidate=candidate,
    )
    quality_reason = evaluate_promote_quality(
        pre_gate=None,
        post_gate=result.get("post_gate_obj"),
        reread_meta=result.get("reread") or {},
        room=result.get("post_room") or {},
        filename=name,
    )
    # promote_and_reread_one may leave non-JSON objects; strip before persistence.
    result.pop("post_gate_obj", None)
    result.pop("post_room", None)

    if quality_reason:
        reverted = revert_promote_after_quality_reject(
            deal,
            filename=name,
            previous_doc_type=result.get("from_doc_type"),
            db=db,
            preferred_sheets=result.get("preferred_sheets"),
        )
        result["ok"] = False
        result["quality_rejected"] = True
        result["quality_reason"] = quality_reason
        result["post_gate_ok"] = bool(reverted.ok) if reverted is not None else False
        if reverted is not None:
            result["post_gate"] = reverted.as_dict()
        raise ValueError(
            f"promote quality rejected for {name}: {quality_reason}"
        )

    result["quality_rejected"] = False
    item["status"] = "accepted"
    item["suggested_doc_type"] = chosen_type
    item["reviewed_at"] = utc_now_iso()
    item["reviewed_by"] = actor
    item["accept_result"] = {
        "post_gate_ok": result.get("post_gate_ok"),
        "to_doc_type": result.get("to_doc_type"),
        "preferred_sheets": result.get("preferred_sheets"),
        "reread": result.get("reread"),
    }
    save_fin_discovery_hitl(deal, payload)
    try:
        from agetic_cdd_api.services_fin_discovery_audit import record_hitl_decision

        record_hitl_decision(
            deal,
            action="hitl_accept",
            filename=name,
            actor=actor,
            run_id=str(payload.get("latest_run_id") or "") or None,
            doc_type=chosen_type,
            post_gate_ok=bool(result.get("post_gate_ok")),
            preferred_sheets=result.get("preferred_sheets"),
            extra={"from_doc_type": result.get("from_doc_type")},
        )
    except Exception:
        logger.exception("fin discovery accept audit failed for %s", name)
    return {
        "candidate": item,
        "promote": result,
        "queue": list_fin_discovery_hitl(deal, status="pending"),
    }


def reject_fin_discovery_candidate(
    deal: Any,
    *,
    filename: str,
    actor: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Operator Reject → leave file untyped; remove from pending queue."""
    name = str(filename or "").strip()
    if not name:
        raise ValueError("filename is required")

    payload = load_fin_discovery_hitl(deal)
    item = _find_candidate(payload, name, statuses={"pending"})
    if item is None:
        raise KeyError(f"no pending HITL candidate for {name}")

    item["status"] = "rejected"
    item["reviewed_at"] = utc_now_iso()
    item["reviewed_by"] = actor
    item["reject_reason"] = (reason or "").strip() or None
    save_fin_discovery_hitl(deal, payload)
    try:
        from agetic_cdd_api.services_fin_discovery_audit import record_hitl_decision

        record_hitl_decision(
            deal,
            action="hitl_reject",
            filename=name,
            actor=actor,
            run_id=str(payload.get("latest_run_id") or "") or None,
            doc_type=str(item.get("suggested_doc_type") or "") or None,
            reason=item.get("reject_reason"),
        )
    except Exception:
        logger.exception("fin discovery reject audit failed for %s", name)
    return {
        "candidate": item,
        "queue": list_fin_discovery_hitl(deal, status="pending"),
    }


def _candidate_item(
    base: dict[str, Any],
    *,
    filename: str,
    status: str,
    skip_reason: str | None,
    skip_reasons: list[str] | None = None,
    suggested_doc_type: str | None = None,
    confidence: Any = None,
    preferred_sheets: list[str] | None = None,
) -> dict[str, Any]:
    sheets = preferred_sheets or preferred_sheets_for_candidate(base)
    reasons = list(skip_reasons or [])
    if skip_reason and skip_reason not in reasons:
        reasons = [skip_reason, *reasons]
    return {
        "id": filename,
        "filename": filename,
        "status": status,
        "skip_reason": skip_reason,
        "skip_reasons": reasons,
        "suggested_doc_type": suggested_doc_type or base.get("suggested_doc_type"),
        "confidence": confidence if confidence is not None else base.get("confidence"),
        "suggested_sheet": base.get("suggested_sheet"),
        "statement_sheets": list(base.get("statement_sheets") or []),
        "preferred_sheets": sheets,
        "risk_flags": list(base.get("risk_flags") or []),
        "why": base.get("llm_why") or base.get("why"),
        "rank": base.get("rank"),
        "rank_source": base.get("rank_source"),
        "score": base.get("score"),
        "cdl_category": base.get("cdl_category"),
        "doc_type": base.get("doc_type"),
        "reviewed_at": None,
        "reviewed_by": None,
    }


def _find_candidate(
    payload: dict[str, Any],
    filename: str,
    *,
    statuses: set[str],
) -> dict[str, Any] | None:
    for item in payload.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("filename") or "") != filename:
            continue
        if str(item.get("status") or "") in statuses:
            return item
    return None


def _deal_id(deal: Any) -> str:
    return str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
