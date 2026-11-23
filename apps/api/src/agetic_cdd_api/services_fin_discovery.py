"""Gate-2-miss financial file discovery.

Miss → shortlist → LLM/heuristic ranks FIN_* → promote → reread parsers → re-gate.
Parsers still own revenue/EBITDA numbers; the LLM only proposes which file/type.

Harden: after promote, keep only improves that add non-zero series (or recover Gate 2);
zero-only / no-improvement promotes are reverted so they cannot poison claims.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_series_ingest import (
    StatementSeriesIngestGate,
    is_expected_statement_source,
)
from agetic_cdd_api.services_statement_reader import (
    _STATEMENT_XLSX_NAME,
    is_non_statement_document,
    is_non_statement_sheet,
)

logger = logging.getLogger(__name__)

# Cap shortlist for inspectability / LLM context.
DEFAULT_CANDIDATE_LIMIT = 20
_SHEET_CAP = 24
_FTS_QUERY = (
    "revenue EBITDA balance sheet profit loss management accounts "
    "trial balance P&L financials income statement"
)
# Underscore-friendly: \b treats "_" as a word char, so CIM_Pack would miss.
_CIM_RE = re.compile(
    r"(?i)(?<![a-z0-9])(cim|confidential\s+information\s+memorandum|"
    r"info(?:rmation)?\s*memo)(?![a-z0-9])"
)
_SPREADSHEET_SUFFIX = (".xlsx", ".xlsm", ".xls")
_STATEMENT_PAGE_CLASSES = frozenset(
    {
        "income_statement",
        "balance_sheet",
        "cash_flow",
        "equity",
        "ebitda_bridge",
        "kpi",
        "note",
    }
)
# Ontology FIN_* ids the ranker may propose (promote path uses these later).
FIN_DOC_TYPES = frozenset(
    {
        "FIN_AUDITED_FS",
        "FIN_REVIEWED_FS",
        "FIN_MGMT_ACCOUNTS",
        "FIN_TRIAL_BALANCE",
        "FIN_GENERAL_LEDGER",
        "FIN_TAX_RETURN",
        "FIN_BUDGET",
        "FIN_MGMT_MODEL",
        "FIN_INVESTOR_WORKBOOK",
        "FIN_QOE_REPORT",
        "FIN_FDD_REPORT",
        "FIN_FIXED_ASSET_REGISTER",
    }
)
_HISTORY_PREFERRED_TYPES = frozenset(
    {
        "FIN_AUDITED_FS",
        "FIN_REVIEWED_FS",
        "FIN_MGMT_ACCOUNTS",
        "FIN_TRIAL_BALANCE",
        "FIN_GENERAL_LEDGER",
        "FIN_INVESTOR_WORKBOOK",
        "FIN_QOE_REPORT",
        "FIN_FDD_REPORT",
    }
)
_ALLOWED_LLM_RISK = frozenset({"cim_like", "forecast_like", "none"})
AUTO_PROMOTE_MIN_CONFIDENCE = 0.75
AUTO_PROMOTE_MAX_ATTEMPTS = 2
_AUTO_BLOCK_RISKS = frozenset({"cim_like", "forecast_like"})

_RANK_SYSTEM = """You rank deal-room spreadsheets that might contain historical financial statements.
Return ONLY a JSON object with key "ranked": an array of objects.
Each object keys:
- "filename": exact filename from the candidate list
- "sheet": best sheet name from that file, or null
- "suggested_doc_type": one FIN_* id from the allowed list
- "confidence": number from 0 to 1
- "why": short reason (no numbers, no revenue/EBITDA figures)
- "risk_flags": array of zero or more of: cim_like, forecast_like, none

Rules:
- Rank most likely historical P&L / BS / CF / management accounts sources first.
- Prefer FIN_MGMT_ACCOUNTS, FIN_AUDITED_FS, FIN_TRIAL_BALANCE, FIN_INVESTOR_WORKBOOK for history.
- Demote CIM / teaser / marketing packs (cim_like) and pure budget/forecast models (forecast_like).
- Use ONLY filenames and sheet names from the provided candidates.
- Do NOT invent or extract any financial figures, years, or amounts.
- Do NOT propose non-FIN_* types."""


def should_run_fin_discovery(gate: StatementSeriesIngestGate, *, flag_on: bool) -> bool:
    """True only on Gate 2 miss when the feature flag is enabled."""
    return bool(flag_on) and bool(gate.expected) and (not gate.ok)


def run_fin_discovery_recovery(
    deal: Any,
    gate: StatementSeriesIngestGate,
    *,
    room_result: dict[str, Any] | None = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    db: Any | None = None,
    auto_promote: bool = True,
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE,
    max_promote_attempts: int = AUTO_PROMOTE_MAX_ATTEMPTS,
) -> dict[str, Any]:
    """Miss-hook recovery: shortlist → rank → promote top safe file(s) → reread → re-gate."""
    deal_id = str(
        getattr(deal, "id", None) or getattr(deal, "slug", None) or gate.deal_id or ""
    ).strip()
    candidates = build_fin_discovery_candidates(
        deal,
        gate,
        room_result=room_result,
        limit=candidate_limit,
    )
    ranked, ranker = rank_fin_candidates(
        candidates,
        deal=deal,
        gate=gate,
    )
    logger.info(
        "fin discovery rank for deal %s — Gate 2 miss: %s; %s candidates; ranker=%s",
        deal_id,
        gate.summary(),
        len(ranked),
        ranker.get("status"),
    )
    for item in ranked[:8]:
        logger.info(
            "fin discovery ranked rank=%s conf=%s type=%s file=%s flags=%s",
            item.get("rank"),
            item.get("confidence"),
            item.get("suggested_doc_type"),
            item.get("filename"),
            item.get("risk_flags"),
        )

    promoted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    post_gate: StatementSeriesIngestGate | None = None
    recovered = False

    if auto_promote and ranked:
        promoted, skipped, post_gate, recovered = promote_and_reread_candidates(
            deal,
            ranked,
            db=db,
            min_confidence=min_confidence,
            max_attempts=max_promote_attempts,
            pre_gate=gate,
        )

    post_gate_dict = post_gate.as_dict() if post_gate is not None else None
    status = "noop"
    if recovered:
        status = "recovered"
    elif promoted:
        status = "promoted_still_miss"
    elif ranked:
        status = "ranked"

    gate_before = {
        "ok": gate.ok,
        "expected": gate.expected,
        "summary": gate.summary(),
        "blockers": list(gate.blockers),
        "expected_files": list(gate.expected_files),
        "reasons": list(gate.reasons),
        "series_fact_count": gate.series_fact_count,
        "series_metric_count": gate.series_metric_count,
    }
    payload = {
        "status": status,
        "phase": "promote_reread",
        "triggered": True,
        "llm_invoked": bool(ranker.get("llm_invoked")),
        "recovered": recovered,
        "promoted": promoted,
        "promote_skipped": skipped,
        "deal_id": deal_id,
        "gate_ok": bool(post_gate.ok) if post_gate is not None else gate.ok,
        "gate_expected": (
            bool(post_gate.expected) if post_gate is not None else gate.expected
        ),
        "gate_summary": post_gate.summary() if post_gate is not None else gate.summary(),
        "expected_files": list(
            post_gate.expected_files if post_gate is not None else gate.expected_files
        ),
        "reasons": list(post_gate.reasons if post_gate is not None else gate.reasons),
        "blockers": list(post_gate.blockers if post_gate is not None else gate.blockers),
        "candidate_count": len(ranked),
        "candidates": ranked,
        "ranker": ranker,
        "post_gate": post_gate_dict,
        "gate_before": gate_before,
    }
    try:
        from agetic_cdd_api.services_fin_discovery_hitl import persist_fin_discovery_hitl

        hitl = persist_fin_discovery_hitl(deal, payload)
        payload["hitl_pending"] = sum(
            1
            for c in (hitl.get("candidates") or [])
            if str(c.get("status") or "") == "pending"
        )
    except Exception:
        logger.exception("fin discovery HITL persist failed for deal %s", deal_id)
        payload["hitl_pending"] = 0
    try:
        from agetic_cdd_api.services_fin_discovery_audit import record_discovery_run

        audit_run = record_discovery_run(
            deal, payload, gate_before=gate_before
        )
        payload["audit_run_id"] = audit_run.get("run_id")
        # Keep HITL queue linked to this run for Accept/Reject audit trails.
        try:
            from agetic_cdd_api.services_fin_discovery_hitl import (
                load_fin_discovery_hitl,
                save_fin_discovery_hitl,
            )

            hitl_payload = load_fin_discovery_hitl(deal)
            hitl_payload["latest_run_id"] = audit_run.get("run_id")
            save_fin_discovery_hitl(deal, hitl_payload)
        except Exception:
            logger.debug("fin discovery HITL run_id link skipped", exc_info=True)
    except Exception:
        logger.exception("fin discovery audit persist failed for deal %s", deal_id)
        payload["audit_run_id"] = None
    return payload


def auto_promote_block_reason(
    candidate: dict[str, Any],
    *,
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE,
) -> str | None:
    """Return primary why a ranked candidate must not auto-promote, else None.

    Risk flags (cim/forecast) take priority over confidence / non-history type so
    audit and HITL always surface ``risk:*`` when those traps are present.
    """
    details = auto_promote_block_details(candidate, min_confidence=min_confidence)
    return None if details is None else str(details["reason"])


def auto_promote_block_details(
    candidate: dict[str, Any],
    *,
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE,
) -> dict[str, Any] | None:
    """Return skip details ``{reason, reasons, risk_flags}`` or None if eligible."""
    filename = str(candidate.get("filename") or "").strip()
    if not filename:
        return {
            "reason": "missing_filename",
            "reasons": ["missing_filename"],
            "risk_flags": [],
        }

    doc_type = str(candidate.get("suggested_doc_type") or "").strip()
    risks = _effective_risk_flags(candidate)
    blocked_risks = sorted(set(risks) & _AUTO_BLOCK_RISKS)
    reasons: list[str] = []

    # Risk flags first — strongest audit signal for CIM / forecast traps.
    if blocked_risks:
        reasons.append("risk:" + ",".join(blocked_risks))

    if doc_type not in FIN_DOC_TYPES:
        reasons.append("invalid_doc_type")

    if doc_type in FIN_DOC_TYPES and doc_type not in _HISTORY_PREFERRED_TYPES:
        reasons.append(f"non_history_type:{doc_type}")

    try:
        confidence = float(candidate.get("confidence"))
    except (TypeError, ValueError):
        reasons.append("missing_confidence")
        confidence = None
    if confidence is not None and confidence < float(min_confidence):
        reasons.append(f"confidence_below_{min_confidence}")

    if not reasons:
        return None
    return {
        "reason": reasons[0],
        "reasons": reasons,
        "risk_flags": blocked_risks or list(risks),
    }


def _effective_risk_flags(candidate: dict[str, Any]) -> list[str]:
    """Normalize candidate risk flags; re-derive from name/type when missing."""
    raw = [str(flag) for flag in (candidate.get("risk_flags") or []) if flag]
    flags = [f for f in raw if f and f != "none"]
    if flags:
        return list(dict.fromkeys(flags))
    # Re-derive so skips still audit risk when an older ranked row omitted flags.
    return _risk_flags(
        str(candidate.get("filename") or ""),
        doc_type=str(candidate.get("suggested_doc_type") or candidate.get("doc_type") or "")
        or None,
        sheet_names=[
            str(s)
            for s in (
                candidate.get("sheet_names")
                or candidate.get("statement_sheets")
                or []
            )
            if s
        ],
    )


def _skip_record(
    candidate: dict[str, Any],
    *,
    reason: str,
    reasons: list[str] | None = None,
    risk_flags: list[str] | None = None,
) -> dict[str, Any]:
    flags = list(risk_flags) if risk_flags is not None else _effective_risk_flags(candidate)
    return {
        "filename": candidate.get("filename"),
        "suggested_doc_type": candidate.get("suggested_doc_type"),
        "confidence": candidate.get("confidence"),
        "reason": reason,
        "reasons": list(reasons or [reason]),
        "risk_flags": flags,
    }


def promote_and_reread_candidates(
    deal: Any,
    ranked: list[dict[str, Any]],
    *,
    db: Any | None = None,
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE,
    max_attempts: int = AUTO_PROMOTE_MAX_ATTEMPTS,
    pre_gate: StatementSeriesIngestGate | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    StatementSeriesIngestGate | None,
    bool,
]:
    """Promote eligible top candidates, reread parsers, re-assess Gate 2.

    Stops early when Gate 2 flips to ok with a quality-accepted promote. Returns
    ``(promoted, skipped, post_gate, recovered)``.
    """
    promoted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    post_gate: StatementSeriesIngestGate | None = None
    attempts = 0
    baseline = pre_gate

    for candidate in ranked:
        details = auto_promote_block_details(
            candidate, min_confidence=min_confidence
        )
        if details is not None:
            skipped.append(
                _skip_record(
                    candidate,
                    reason=str(details["reason"]),
                    reasons=list(details.get("reasons") or []),
                    risk_flags=list(details.get("risk_flags") or []),
                )
            )
            continue
        if attempts >= max(1, int(max_attempts)):
            skipped.append(
                _skip_record(
                    candidate,
                    reason="max_promote_attempts",
                    reasons=["max_promote_attempts"],
                )
            )
            continue

        attempts += 1
        try:
            result = promote_and_reread_one(
                deal,
                filename=str(candidate["filename"]),
                doc_type=str(candidate["suggested_doc_type"]),
                confidence=float(candidate.get("confidence") or 0),
                db=db,
                candidate=candidate,
            )
        except Exception as exc:
            logger.exception(
                "fin discovery promote/reread failed for %s",
                candidate.get("filename"),
            )
            promoted.append(
                {
                    "filename": candidate.get("filename"),
                    "to_doc_type": candidate.get("suggested_doc_type"),
                    "confidence": candidate.get("confidence"),
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue

        quality_reason = evaluate_promote_quality(
            pre_gate=baseline,
            post_gate=result.get("post_gate_obj"),
            reread_meta=result.get("reread") or {},
            room=result.get("post_room") or {},
            filename=str(result.get("filename") or candidate.get("filename") or ""),
        )
        post_gate = result.get("post_gate_obj")
        # Drop non-JSON gate / room objects from audit row.
        result.pop("post_gate_obj", None)
        result.pop("post_room", None)

        if quality_reason:
            logger.info(
                "fin discovery quality-reject %s (%s) — reverting promote",
                result.get("filename"),
                quality_reason,
            )
            reverted_gate = revert_promote_after_quality_reject(
                deal,
                filename=str(result.get("filename") or ""),
                previous_doc_type=result.get("from_doc_type"),
                db=db,
                preferred_sheets=result.get("preferred_sheets"),
            )
            if reverted_gate is not None:
                post_gate = reverted_gate
            skipped.append(
                _skip_record(
                    candidate,
                    reason=quality_reason,
                    reasons=[quality_reason],
                )
            )
            result["ok"] = False
            result["quality_rejected"] = True
            result["quality_reason"] = quality_reason
            result["post_gate_ok"] = bool(post_gate.ok) if post_gate else False
            if post_gate is not None:
                result["post_gate"] = post_gate.as_dict()
            promoted.append(result)
            continue

        result["quality_rejected"] = False
        promoted.append(result)
        if post_gate is not None and post_gate.ok:
            logger.info(
                "fin discovery recovered Gate 2 via %s → %s",
                result.get("filename"),
                result.get("to_doc_type"),
            )
            return promoted, skipped, post_gate, True
        # Partial improve: raise baseline so the next attempt must improve further.
        if post_gate is not None:
            baseline = post_gate

    return promoted, skipped, post_gate, False


def preferred_sheets_for_candidate(candidate: dict[str, Any] | None) -> list[str] | None:
    """Build workbook sheet preference: suggested sheet first, then statement sheets."""
    if not candidate:
        return None
    sheets: list[str] = []
    suggested = str(candidate.get("suggested_sheet") or "").strip()
    if suggested:
        sheets.append(suggested)
    for name in candidate.get("statement_sheets") or []:
        text = str(name or "").strip()
        if text and text not in sheets:
            sheets.append(text)
    return sheets or None


_ZERO_EPS = 1e-12


def evaluate_promote_quality(
    *,
    pre_gate: StatementSeriesIngestGate | None,
    post_gate: StatementSeriesIngestGate | None,
    reread_meta: dict[str, Any],
    room: dict[str, Any],
    filename: str,
) -> str | None:
    """Return a ``quality:*`` reject reason, or None when the promote should stand.

    Keeps promotes that recover Gate 2 with non-zero series from the file, or that
    strictly improve non-zero series coverage vs the pre-promote baseline.
    """
    if reread_meta.get("ok") is False:
        return "quality:reread_failed"

    file_facts = _series_facts_for_file(room, filename)
    nonzero_file = sum(1 for fact in file_facts if _fact_value_abs(fact) > _ZERO_EPS)

    if file_facts and nonzero_file == 0:
        return "quality:zero_only_series"

    reread_fact_count = _reread_fact_count(reread_meta)

    if post_gate is not None and post_gate.ok:
        # Recovered only counts when this file contributed real history, or the
        # room already has non-zero series (promote was confirmatory).
        if nonzero_file > 0:
            return None
        room_nonzero = sum(
            1
            for fact in _series_facts_from_room(room)
            if _fact_value_abs(fact) > _ZERO_EPS
        )
        if room_nonzero > 0:
            return None
        # Room may omit file_name attribution in tests / partial loads — trust a
        # successful reread fact count when Gate 2 recovered.
        if reread_fact_count > 0:
            return None
        return "quality:zero_only_series"

    # Still a Gate 2 miss — require this file to add non-zero series and improve
    # counts vs the baseline so we do not leave a worse typing in place.
    if nonzero_file == 0 and reread_fact_count <= 0:
        return "quality:no_series_improvement"

    pre_facts = int(getattr(pre_gate, "series_fact_count", 0) or 0) if pre_gate else 0
    pre_metrics = int(getattr(pre_gate, "series_metric_count", 0) or 0) if pre_gate else 0
    post_facts = int(getattr(post_gate, "series_fact_count", 0) or 0) if post_gate else 0
    post_metrics = (
        int(getattr(post_gate, "series_metric_count", 0) or 0) if post_gate else 0
    )
    if post_facts > pre_facts or post_metrics > pre_metrics:
        return None
    return "quality:no_series_improvement"


def revert_promote_after_quality_reject(
    deal: Any,
    *,
    filename: str,
    previous_doc_type: str | None,
    db: Any | None = None,
    preferred_sheets: list[str] | None = None,
) -> StatementSeriesIngestGate | None:
    """Undo a bad FIN_* promote, reread, canonicalize, and re-assess Gate 2."""
    from agetic_cdd_api.services_document_register import update_document_type
    from agetic_cdd_api.services_series_ingest import assess_statement_series_ingest

    name = str(filename or "").strip()
    if not name:
        return None
    restore_type = str(previous_doc_type or "").strip() or "CORPORATE_DOCS"
    try:
        update_document_type(
            deal,
            name,
            restore_type,
            confidence=0.2,
            source="fin_discovery_quality_revert",
            preferred_sheets=None,
            suggested_sheet=None,
        )
    except Exception:
        logger.exception("fin discovery quality revert type update failed for %s", name)
        return None

    _reread_after_promote(deal, name, db=db, preferred_sheets=preferred_sheets)
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
    if deal_id:
        try:
            from agetic_cdd_api.services_series_canonical import (
                canonicalize_financial_history,
            )

            canonicalize_financial_history(deal_id)
        except Exception:
            logger.debug(
                "fin discovery quality revert canonicalize skipped for %s",
                name,
                exc_info=True,
            )
    post_room = _room_after_reread(deal)
    return assess_statement_series_ingest(deal, post_room)


def _series_facts_from_room(room: dict[str, Any]) -> list[Any]:
    from agetic_cdd_api.services_series_ingest import _is_series_fact

    return [fact for fact in (room.get("facts") or []) if _is_series_fact(fact)]


def _series_facts_for_file(room: dict[str, Any], filename: str) -> list[Any]:
    name = str(filename or "").strip()
    if not name:
        return []
    out: list[Any] = []
    for fact in _series_facts_from_room(room):
        if _fact_file_name(fact) == name:
            out.append(fact)
    return out


def _fact_file_name(fact: Any) -> str:
    if isinstance(fact, dict):
        direct = str(fact.get("file_name") or "").strip()
        if direct:
            return direct
        mapping = fact.get("mapping") or {}
        if isinstance(mapping, dict):
            return str(mapping.get("file_name") or "").strip()
        return ""
    direct = str(getattr(fact, "file_name", "") or "").strip()
    if direct:
        return direct
    mapping = getattr(fact, "mapping", None) or {}
    if isinstance(mapping, dict):
        return str(mapping.get("file_name") or "").strip()
    return ""


def _fact_value_abs(fact: Any) -> float:
    if isinstance(fact, dict):
        value = fact.get("value")
    else:
        value = getattr(fact, "value", None)
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0.0


def _reread_fact_count(reread_meta: dict[str, Any]) -> int:
    raw = reread_meta.get("facts")
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def promote_and_reread_one(
    deal: Any,
    *,
    filename: str,
    doc_type: str,
    confidence: float,
    db: Any | None = None,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promote one file to FIN_*, reread parsers, re-assess Gate 2."""
    from agetic_cdd_api.services_document_register import update_document_type
    from agetic_cdd_api.services_series_ingest import assess_statement_series_ingest

    preferred_sheets = preferred_sheets_for_candidate(candidate)
    row = update_document_type(
        deal,
        filename,
        doc_type,
        confidence=confidence,
        source="fin_discovery",
        preferred_sheets=preferred_sheets,
        suggested_sheet=(preferred_sheets[0] if preferred_sheets else None),
    )
    if row is None:
        raise RuntimeError(f"file not in document register: {filename}")

    reread_meta = _reread_after_promote(
        deal, filename, db=db, preferred_sheets=preferred_sheets
    )
    # Gate 3 must run after single-file reread (full read_room does this; databook
    # reread may not). Without it, monthly cells for the same FY trip Gate 2.
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
    if deal_id:
        try:
            from agetic_cdd_api.services_series_canonical import (
                canonicalize_financial_history,
            )

            canon = canonicalize_financial_history(deal_id)
            reread_meta = dict(reread_meta or {})
            reread_meta["series_canonical"] = {
                "groups": canon.get("groups"),
                "demoted": len(canon.get("demoted") or []),
                "conflicts": len(canon.get("conflicts") or []),
            }
        except Exception as exc:
            logger.warning(
                "fin discovery canonicalize after promote failed for %s: %s",
                filename,
                exc,
            )
    post_room = _room_after_reread(deal)
    post_gate = assess_statement_series_ingest(deal, post_room)
    return {
        "filename": filename,
        "from_doc_type": row.get("doc_type_previous"),
        "to_doc_type": doc_type,
        "confidence": confidence,
        "suggested_sheet": (candidate or {}).get("suggested_sheet")
        or (preferred_sheets[0] if preferred_sheets else None),
        "preferred_sheets": preferred_sheets,
        "rank_source": (candidate or {}).get("rank_source"),
        "reread": reread_meta,
        "post_gate_ok": post_gate.ok,
        "post_gate": post_gate.as_dict(),
        "post_gate_obj": post_gate,
        "post_room": post_room,
        "ok": True,
    }


def _reread_after_promote(
    deal: Any,
    filename: str,
    *,
    db: Any | None,
    preferred_sheets: list[str] | None = None,
) -> dict[str, Any]:
    """Prefer full databook reread when a DB session exists; else ontology file reread."""
    if db is not None:
        try:
            from agetic_cdd_api.services_databook import reread_databook_document

            summary = reread_databook_document(
                db, deal, filename, preferred_sheets=preferred_sheets
            )
            return {
                "mode": "reread_databook_document",
                "ok": True,
                "summary_type": type(summary).__name__,
                "preferred_sheets": preferred_sheets,
            }
        except Exception as exc:
            logger.warning(
                "reread_databook_document failed for %s (%s); falling back to reread_document",
                filename,
                exc,
            )
    try:
        from agetic_cdd_api.services_databook_hitl import reread_document

        result = reread_document(deal, filename, preferred_sheets=preferred_sheets)
        return {
            "mode": "reread_document",
            "ok": result is not None,
            "facts": (result or {}).get("facts"),
            "flags": (result or {}).get("flags") or [],
            "preferred_sheets": (result or {}).get("preferred_sheets") or preferred_sheets,
        }
    except Exception as exc:
        logger.exception("reread_document failed for %s", filename)
        return {
            "mode": "reread_document",
            "ok": False,
            "error": str(exc),
            "preferred_sheets": preferred_sheets,
        }


def _room_after_reread(deal: Any) -> dict[str, Any]:
    """Build a room payload for Gate 2 re-assessment after promote/reread."""
    from agetic_cdd_api.services_document_register import register_room

    rows = list(register_room(deal) or [])
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
    facts: list[Any] = []
    if deal_id:
        try:
            from agetic_cdd_api.services_fact_repository import facts_for

            facts = list(facts_for(deal_id) or [])
        except Exception:
            facts = []
    return {"rows": rows, "facts": facts}


def rank_fin_candidates(
    candidates: list[dict[str, Any]],
    *,
    deal: Any,
    gate: StatementSeriesIngestGate | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rank shortlist with Gemini JSON; fall back to heuristic order on failure.

    Never invents numbers. Does not promote or re-parse.
    """
    if not candidates:
        return [], {
            "status": "skipped_empty",
            "llm_invoked": False,
            "model": None,
            "error": None,
        }

    enriched = [_with_heuristic_suggestion(dict(item)) for item in candidates]
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json
    from agetic_cdd_api.services_llm import llm_model, llm_provider

    if not gemini_configured():
        ranked = _finalize_ranks(enriched)
        return ranked, {
            "status": "heuristic_fallback",
            "llm_invoked": False,
            "provider": llm_provider(),
            "model": None,
            "error": "llm_not_configured",
        }

    system = _RANK_SYSTEM + "\nAllowed FIN_* types: " + ", ".join(sorted(FIN_DOC_TYPES))
    user = _rank_user_prompt(deal=deal, gate=gate, candidates=enriched)
    parsed = generate_json(system=system, user=user, temperature=0.1)
    model = llm_model()
    provider = llm_provider()
    if not parsed:
        ranked = _finalize_ranks(enriched)
        return ranked, {
            "status": "heuristic_fallback",
            "llm_invoked": False,
            "provider": provider,
            "model": model,
            "error": "llm_empty_or_failed",
        }

    merged, error = _merge_llm_ranking(enriched, parsed)
    if error:
        ranked = _finalize_ranks(enriched)
        return ranked, {
            "status": "heuristic_fallback",
            "llm_invoked": True,
            "provider": provider,
            "model": model,
            "error": error,
        }

    ranked = _finalize_ranks(merged)
    from agetic_cdd_api.services_llm import llm_last_invocation

    return ranked, {
        "status": "llm",
        "llm_invoked": True,
        "provider": provider,
        "model": model,
        "invocation": llm_last_invocation(),
        "error": None,
    }


def _rank_user_prompt(
    *,
    deal: Any,
    gate: StatementSeriesIngestGate | None,
    candidates: list[dict[str, Any]],
) -> str:
    company = (
        getattr(deal, "company", None)
        or getattr(deal, "name", None)
        or getattr(deal, "slug", None)
        or "unknown"
    )
    gate_bits = ""
    if gate is not None:
        gate_bits = (
            f"Gate 2 summary: {gate.summary()}\n"
            f"Already-tried expected files: {list(gate.expected_files)}\n"
        )
    slim = [
        {
            "filename": c.get("filename"),
            "doc_type": c.get("doc_type"),
            "cdl_category": c.get("cdl_category"),
            "sheet_names": list(c.get("sheet_names") or [])[:12],
            "statement_sheets": list(c.get("statement_sheets") or [])[:8],
            "risk_flags": list(c.get("risk_flags") or []),
            "heuristic_score": c.get("score"),
            "why": c.get("why"),
        }
        for c in candidates
    ]
    return (
        f"Deal / company: {company}\n"
        f"{gate_bits}"
        "Candidates (JSON). Rank which files should be typed as historical FIN_* sources:\n"
        f"{json.dumps(slim, ensure_ascii=True)}\n"
    )


def _merge_llm_ranking(
    candidates: list[dict[str, Any]],
    parsed: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    raw = parsed.get("ranked")
    if not isinstance(raw, list) or not raw:
        return None, "missing_ranked_array"

    by_name = {str(c.get("filename") or ""): c for c in candidates if c.get("filename")}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in raw:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "").strip()
        if not filename or filename in seen or filename not in by_name:
            continue
        doc_type = str(entry.get("suggested_doc_type") or "").strip()
        if doc_type not in FIN_DOC_TYPES:
            continue
        try:
            confidence = float(entry.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        sheet = entry.get("sheet")
        sheet_name = str(sheet).strip() if sheet not in (None, "") else None
        allowed_sheets = {
            str(s) for s in (by_name[filename].get("sheet_names") or []) if s
        }
        if sheet_name and allowed_sheets and sheet_name not in allowed_sheets:
            sheet_name = None

        risk_flags = _normalize_llm_risk_flags(
            entry.get("risk_flags"),
            fallback=list(by_name[filename].get("risk_flags") or []),
        )
        why = str(entry.get("why") or "").strip() or by_name[filename].get("why")

        merged = dict(by_name[filename])
        merged.update(
            {
                "suggested_doc_type": doc_type,
                "confidence": round(confidence, 3),
                "suggested_sheet": sheet_name,
                "llm_why": why,
                "risk_flags": risk_flags,
                "rank_source": "llm",
            }
        )
        # Soft demote risky types for later promote gate (still ranked, just lower).
        if "cim_like" in risk_flags:
            merged["confidence"] = round(min(float(merged["confidence"]), 0.4), 3)
        if "forecast_like" in risk_flags and doc_type in _HISTORY_PREFERRED_TYPES:
            merged["confidence"] = round(min(float(merged["confidence"]), 0.55), 3)

        ordered.append(merged)
        seen.add(filename)

    if not ordered:
        return None, "no_valid_ranked_entries"

    for cand in candidates:
        name = str(cand.get("filename") or "")
        if name and name not in seen:
            ordered.append(dict(cand))
    return ordered, None


def _normalize_llm_risk_flags(raw: Any, *, fallback: list[str]) -> list[str]:
    flags: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            key = str(item or "").strip().lower()
            if key in _ALLOWED_LLM_RISK and key != "none" and key not in flags:
                flags.append(key)
    if not flags:
        for key in fallback:
            if key in _ALLOWED_LLM_RISK and key != "none" and key not in flags:
                flags.append(key)
    return flags


def _with_heuristic_suggestion(candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("suggested_doc_type") in FIN_DOC_TYPES:
        return candidate
    doc_type = _heuristic_doc_type(candidate)
    out = dict(candidate)
    out["suggested_doc_type"] = doc_type
    out["confidence"] = round(_heuristic_confidence(candidate, doc_type), 3)
    out["suggested_sheet"] = (list(candidate.get("statement_sheets") or []) or [None])[0]
    out["rank_source"] = "heuristic"
    return out


def _heuristic_doc_type(candidate: dict[str, Any]) -> str:
    flags = set(candidate.get("risk_flags") or [])
    name = str(candidate.get("filename") or "")
    blob = " ".join(
        [
            name,
            " ".join(str(s) for s in (candidate.get("sheet_names") or [])),
        ]
    )
    if "forecast_like" in flags or re.search(r"(?i)\b(budget|forecast|projection)\b", blob):
        if re.search(r"(?i)\bbudget\b", blob):
            return "FIN_BUDGET"
        return "FIN_MGMT_MODEL"
    if re.search(r"(?i)trial\s*balance|tb\b", blob):
        return "FIN_TRIAL_BALANCE"
    if re.search(r"(?i)audited|10[\s_-]?k|annual\s*report", blob):
        return "FIN_AUDITED_FS"
    if re.search(r"(?i)qoe|quality\s*of\s*earnings", blob):
        return "FIN_QOE_REPORT"
    if re.search(r"(?i)databook|data\s*book|investor", blob):
        return "FIN_INVESTOR_WORKBOOK"
    if candidate.get("statement_sheets") or candidate.get("name_statement_shaped"):
        return "FIN_MGMT_ACCOUNTS"
    return "FIN_INVESTOR_WORKBOOK"


def _heuristic_confidence(candidate: dict[str, Any], doc_type: str) -> float:
    score = float(candidate.get("score") or 0.0)
    conf = 0.35 + min(0.45, max(0.0, score) / 12.0)
    flags = set(candidate.get("risk_flags") or [])
    if "cim_like" in flags:
        conf = min(conf, 0.35)
    if "forecast_like" in flags and doc_type in _HISTORY_PREFERRED_TYPES:
        conf = min(conf, 0.45)
    if doc_type in _HISTORY_PREFERRED_TYPES and candidate.get("statement_sheets"):
        conf = max(conf, 0.55)
    return max(0.0, min(0.95, conf))


def _finalize_ranks(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [dict(item) for item in candidates]
    for idx, item in enumerate(out, start=1):
        item["rank"] = idx
        if item.get("suggested_doc_type") not in FIN_DOC_TYPES:
            item["suggested_doc_type"] = _heuristic_doc_type(item)
        if item.get("confidence") is None:
            item["confidence"] = round(
                _heuristic_confidence(item, str(item["suggested_doc_type"])), 3
            )
        if "rank_source" not in item:
            item["rank_source"] = "heuristic"
    return out


def build_fin_discovery_candidates(
    deal: Any,
    gate: StatementSeriesIngestGate | None = None,
    *,
    room_result: dict[str, Any] | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[dict[str, Any]]:
    """Heuristic shortlist of spreadsheets that might deserve FIN_* promotion.

    Includes register xlsx that are **not** already expected statement sources,
    boosted by FTS financial hits and statement-like sheet names.
    """
    rows = _register_rows(deal, room_result)
    expected_names = {
        str(name)
        for name in (list(gate.expected_files) if gate is not None else [])
        if name
    }
    lib_meta = _library_meta(deal)
    fts_by_file = _fts_filename_scores(deal)
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        if not _is_spreadsheet_row(row):
            continue
        filename = str(row.get("file_name") or "").strip()
        if not filename or filename in seen:
            continue
        # Already tried as statement sources — discovery looks for alternatives.
        if is_expected_statement_source(row) or filename in expected_names:
            continue
        if is_non_statement_document(row.get("doc_type")):
            continue
        seen.add(filename)
        pool.append(
            _candidate_from_row(
                deal,
                row,
                lib_meta=lib_meta.get(filename) or {},
                fts_score=fts_by_file.get(filename, 0.0),
            )
        )

    # FTS may surface files missing from a thin room_result; pull register/path meta.
    for filename, fts_score in fts_by_file.items():
        if filename in seen:
            continue
        if not filename.lower().endswith(_SPREADSHEET_SUFFIX):
            continue
        if filename in expected_names:
            continue
        row = _row_for_filename(rows, filename)
        if row is not None and is_expected_statement_source(row):
            continue
        if row is not None and is_non_statement_document(row.get("doc_type")):
            continue
        seen.add(filename)
        pool.append(
            _candidate_from_row(
                deal,
                row
                or {
                    "file_name": filename,
                    "format": _format_from_name(filename),
                    "doc_type": (lib_meta.get(filename) or {}).get("doc_kind"),
                },
                lib_meta=lib_meta.get(filename) or {},
                fts_score=fts_score,
            )
        )

    pool.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("filename") or "")))
    capped = pool[: max(1, int(limit))]
    for idx, item in enumerate(capped, start=1):
        item["rank"] = idx
    return capped


def _register_rows(
    deal: Any, room_result: dict[str, Any] | None
) -> list[dict[str, Any]]:
    rows = list((room_result or {}).get("rows") or [])
    if rows:
        return rows
    try:
        from agetic_cdd_api.services_document_register import register_room

        return list(register_room(deal) or [])
    except Exception as exc:
        logger.warning("fin discovery register_room failed: %s", exc)
        return []


def _library_meta(deal: Any) -> dict[str, dict[str, Any]]:
    try:
        from agetic_cdd_api.services_library import load_library_index

        index = load_library_index(deal) or {}
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in index.get("documents") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("filename") or "").strip()
        if name:
            out[name] = entry
    return out


def _fts_filename_scores(deal: Any) -> dict[str, float]:
    """Best (lowest BM25 → highest boost) score per filename from financial FTS."""
    try:
        from agetic_cdd_api.services_library_search import search_library_chunks

        hits = search_library_chunks(
            deal,
            query=_FTS_QUERY,
            categories={"financial"},
            limit=40,
        )
    except Exception as exc:
        logger.debug("fin discovery FTS unavailable: %s", exc)
        return {}

    scores: dict[str, float] = {}
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        filename = str(hit.get("filename") or "").strip()
        if not filename:
            continue
        # sqlite bm25: lower is better; convert to a positive boost in ~0..6
        raw = float(hit.get("rank") or 0.0)
        boost = max(0.0, min(6.0, 4.0 - raw))
        prev = scores.get(filename)
        if prev is None or boost > prev:
            scores[filename] = boost
    return scores


def _is_spreadsheet_row(row: dict[str, Any]) -> bool:
    name = str(row.get("file_name") or "")
    fmt = str(row.get("format") or "").lower()
    if fmt in {"xlsx", "xls", "xlsm"}:
        return True
    return name.lower().endswith(_SPREADSHEET_SUFFIX)


def _format_from_name(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".xlsm"):
        return "xlsm"
    if lower.endswith(".xls"):
        return "xls"
    return "xlsx"


def _row_for_filename(
    rows: list[dict[str, Any]], filename: str
) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("file_name") or "") == filename:
            return row
    return None


def _candidate_from_row(
    deal: Any,
    row: dict[str, Any],
    *,
    lib_meta: dict[str, Any],
    fts_score: float,
) -> dict[str, Any]:
    filename = str(row.get("file_name") or "").strip()
    doc_type = str(row.get("doc_type") or lib_meta.get("doc_kind") or "").strip() or None
    cdl = str(lib_meta.get("cdl_category") or "").strip() or None
    path = _resolve_path(deal, filename)
    sheet_names, statement_sheets, sheet_classes = _sheet_features(path)

    risk_flags = _risk_flags(filename, doc_type=doc_type, sheet_names=sheet_names)
    name_hit = _name_statement_shaped(filename)
    score = _heuristic_score(
        name_hit=name_hit,
        cdl=cdl,
        fts_score=fts_score,
        statement_sheet_count=len(statement_sheets),
        risk_flags=risk_flags,
    )
    size_bytes = None
    if path is not None and path.is_file():
        try:
            size_bytes = int(path.stat().st_size)
        except OSError:
            size_bytes = None

    return {
        "filename": filename,
        "doc_type": doc_type,
        "format": str(row.get("format") or _format_from_name(filename)).lower(),
        "cdl_category": cdl,
        "size_bytes": size_bytes,
        "sheet_names": sheet_names,
        "statement_sheets": statement_sheets,
        "sheet_classes": sheet_classes,
        "fts_score": round(float(fts_score), 3),
        "name_statement_shaped": name_hit,
        "risk_flags": risk_flags,
        "score": round(float(score), 3),
        "why": _why(
            name_hit=name_hit,
            cdl=cdl,
            fts_score=fts_score,
            statement_sheets=statement_sheets,
            risk_flags=risk_flags,
        ),
    }


def _resolve_path(deal: Any, filename: str) -> Path | None:
    if not filename:
        return None
    try:
        from agetic_cdd_api.services_vdr import documents_dir

        path = documents_dir(deal) / filename
        return path if path.is_file() else None
    except Exception:
        return None


def _sheet_features(
    path: Path | None,
) -> tuple[list[str], list[str], dict[str, str]]:
    if path is None or not path.is_file():
        return [], [], {}
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            names = [str(name) for name in (wb.sheetnames or [])][:_SHEET_CAP]
        finally:
            wb.close()
    except Exception as exc:
        logger.debug("fin discovery sheet read failed for %s: %s", path.name, exc)
        return [], [], {}

    statement_sheets: list[str] = []
    sheet_classes: dict[str, str] = {}
    try:
        from agetic_cdd_api.services_databook_pages import classify_sheet_name
    except Exception:
        classify_sheet_name = None  # type: ignore[assignment]

    for name in names:
        if is_non_statement_sheet(name):
            sheet_classes[name] = "non_statement"
            continue
        page_class = None
        if classify_sheet_name is not None:
            try:
                hit = classify_sheet_name(name)
                if hit is not None and getattr(hit, "page_class", None) is not None:
                    page_class = str(hit.page_class.value if hasattr(hit.page_class, "value") else hit.page_class)
            except Exception:
                page_class = None
        if page_class:
            sheet_classes[name] = page_class
        key = (page_class or "").lower()
        if key in _STATEMENT_PAGE_CLASSES or _name_statement_shaped(name):
            statement_sheets.append(name)
            if name not in sheet_classes:
                sheet_classes[name] = key or "statement_shaped"
    return names, statement_sheets, sheet_classes


def _name_statement_shaped(text: str) -> bool:
    """True when filename/sheet looks statement-like (underscores ≈ spaces)."""
    raw = str(text or "").strip()
    if not raw:
        return False
    if _STATEMENT_XLSX_NAME.search(raw):
        return True
    normalized = re.sub(r"[_\-.]+", " ", raw)
    return bool(_STATEMENT_XLSX_NAME.search(normalized))


def _risk_flags(
    filename: str, *, doc_type: str | None, sheet_names: list[str]
) -> list[str]:
    flags: list[str] = []
    blob = f"{filename}\n" + "\n".join(sheet_names)
    if _CIM_RE.search(blob):
        flags.append("cim_like")
    try:
        from agetic_cdd_api.services_databook_classify import (
            ActualForecast,
            infer_actual_forecast,
        )

        if infer_actual_forecast(filename, " ".join(sheet_names)) == ActualForecast.FORECAST:
            flags.append("forecast_like")
    except Exception:
        if re.search(r"(?i)\b(budget|forecast|projection)\b", blob):
            flags.append("forecast_like")
    if doc_type in {"FIN_MGMT_MODEL", "FIN_BUDGET", "DEAL_MODEL"}:
        if "forecast_like" not in flags:
            flags.append("forecast_like")
    if is_non_statement_document(doc_type):
        flags.append("non_statement_doc_type")
    return flags


def _heuristic_score(
    *,
    name_hit: bool,
    cdl: str | None,
    fts_score: float,
    statement_sheet_count: int,
    risk_flags: list[str],
) -> float:
    score = 0.0
    if name_hit:
        score += 3.0
    if (cdl or "") == "financial":
        score += 2.0
    score += min(6.0, float(fts_score))
    score += min(3.0, float(statement_sheet_count))
    if "cim_like" in risk_flags:
        score -= 4.0
    if "forecast_like" in risk_flags:
        score -= 2.5
    if "non_statement_doc_type" in risk_flags:
        score -= 5.0
    return score


def _why(
    *,
    name_hit: bool,
    cdl: str | None,
    fts_score: float,
    statement_sheets: list[str],
    risk_flags: list[str],
) -> str:
    bits: list[str] = []
    if name_hit:
        bits.append("statement-shaped filename")
    if cdl == "financial":
        bits.append("library category=financial")
    if fts_score > 0:
        bits.append(f"FTS financial hit ({fts_score:.1f})")
    if statement_sheets:
        bits.append("statement-like sheets: " + ", ".join(statement_sheets[:4]))
    if risk_flags:
        bits.append("risk=" + ",".join(risk_flags))
    return "; ".join(bits) if bits else "spreadsheet not yet expected as statement source"
