"""Databook HITL decisions: Correct / Drop / Vouch / Accept proposal."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any, Literal

from fastapi import HTTPException, status

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_map import map_caption
from agetic_cdd_api.services_databook_models import (
    ExtractedRow,
    MetricFamily,
    PromotedMetric,
    RowStatus,
)
from agetic_cdd_api.services_databook_resolve import (
    apply_series_drops,
    assumption_issues_from_rows,
    build_data_quality_items,
    detect_conflicts,
)
from agetic_cdd_api.services_databook_store import (
    append_decision,
    load_blocks,
    load_meta,
    load_params,
    load_promoted,
    load_rows,
    save_issues,
    save_meta,
    save_promoted,
    save_rows,
)
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

DecisionAction = Literal["correct", "drop", "vouch", "accept"]

# Statuses that must not feed conflict detection (resolved or deliberately sidelined).
_CONFLICT_EXCLUDED = frozenset(
    {
        RowStatus.DROPPED,
        RowStatus.PROMOTED,
        RowStatus.VOUCHED,
        RowStatus.HELD_OUT,
    }
)


def _require_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if len(text) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required (at least 3 characters). Correcting ≠ vouching.",
        )
    return text


def _find_row(rows: list[ExtractedRow], row_id: str) -> ExtractedRow:
    for row in rows:
        if row.row_id == row_id:
            return row
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Row not found: {row_id}")


def _json_primitive(value: Any) -> Any:
    """Coerce enums and nested structures to JSON-serializable primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_primitive(v) for v in value]
    return value


def _upsert_promoted(
    promoted: list[PromotedMetric],
    *,
    row: ExtractedRow,
    decision_id: str,
    auto: bool = False,
    sources: list[str] | None = None,
    captions: list[str] | None = None,
) -> list[PromotedMetric]:
    if not row.metric_key or row.fiscal_year is None:
        return promoted
    out = [
        p
        for p in promoted
        if not (p.metric_key == row.metric_key and p.fiscal_year == row.fiscal_year)
    ]
    out.append(
        PromotedMetric(
            metric_key=row.metric_key,
            fiscal_year=row.fiscal_year,
            value=row.value,
            unit=row.unit,
            currency=row.currency,
            scale=row.scale,
            row_id=row.row_id,
            sources=sources if sources is not None else [row.source_name],
            captions=captions if captions is not None else [row.caption],
            decision_id=decision_id,
            auto=auto,
        )
    )
    return out


def _rebuild_issues_from_rows(deal: Deal, rows: list[ExtractedRow]) -> list[dict[str, Any]]:
    """Recompute dropped/conflict issues, skipping metric+years already promoted/vouched."""
    params = load_params(deal)
    promoted = load_promoted(deal)
    resolved: set[tuple[str, int]] = {(p.metric_key, p.fiscal_year) for p in promoted}

    # Series drops on non-decision rows
    probe = [r.model_copy(update={"status": RowStatus.CANDIDATE}) for r in rows if r.status != RowStatus.DROPPED]
    _, dropped_issues = apply_series_drops(probe, params=params)

    conflict_src = [
        r
        for r in rows
        if r.status not in _CONFLICT_EXCLUDED
        and not (
            r.metric_key
            and r.fiscal_year is not None
            and (r.metric_key, r.fiscal_year) in resolved
        )
    ]
    conflict_issues, _ = detect_conflicts(conflict_src)
    filtered: list[dict[str, Any]] = []
    for item in conflict_issues:
        fy = item.get("fiscal_year")
        if fy is None:
            filtered.append(item)
            continue
        row_ids: set[str] = set()
        for cand in item.get("candidates") or []:
            row_ids.update(cand.get("row_ids") or [])
        metric_keys = {
            r.metric_key for r in rows if r.row_id in row_ids and r.metric_key
        }
        if any((mk, int(fy)) in resolved for mk in metric_keys):
            continue
        filtered.append(item)

    failed_checks: list[dict[str, Any]] = []
    for block in load_blocks(deal):
        if block.outcome != "fail":
            continue
        if any(
            r.row_id in set(block.line_row_ids)
            and r.status in {RowStatus.HELD_OUT, RowStatus.CANDIDATE}
            for r in rows
        ):
            failed_checks.append(
                {
                    "kind": "failed_check",
                    "source": block.source_name,
                    "block_id": block.block_id,
                    "fiscal_year": block.fiscal_year,
                    "period": block.period,
                    "printed_subtotal": block.printed_subtotal,
                    "computed_sum": block.computed_sum,
                    "row_ids": list(block.line_row_ids),
                    "reason": "Statement block does not tie to the printed subtotal",
                }
            )

    kept_drops = []
    for item in dropped_issues:
        detail = item.get("detail") or {}
        val = detail.get("value")
        fy = detail.get("fiscal_year")
        still = any(
            r.status == RowStatus.DROPPED and r.fiscal_year == fy and r.value == val for r in rows
        )
        # Also keep if still present as candidate outlier (rescan path)
        if still or any(
            r.fiscal_year == fy and r.value == val and r.status == RowStatus.CANDIDATE for r in rows
        ):
            kept_drops.append(item)

    return build_data_quality_items(
        dropped=kept_drops,
        conflicts=filtered,
        failed_checks=failed_checks,
        assumed=assumption_issues_from_rows(rows),
    )


def _refresh_meta(deal: Deal, rows: list[ExtractedRow], issues: list[dict[str, Any]], promoted: list[PromotedMetric]) -> None:
    meta = load_meta(deal)
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.status.value] = by_status.get(row.status.value, 0) + 1
    meta = meta.model_copy(
        update={
            "row_count": len(rows),
            "promoted_count": len(promoted),
            "held_out_count": by_status.get("held_out", 0),
            "issue_count": len(issues),
        }
    )
    save_meta(deal, meta)


def _write_decision(
    deal: Deal,
    *,
    action: DecisionAction,
    row: ExtractedRow | None,
    reason: str,
    actor: str,
    patch: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    decision_id = uuid.uuid4().hex[:12]
    payload: dict[str, Any] = {
        "decision_id": decision_id,
        "action": action,
        "reason": reason,
        "actor": actor,
        "at": utc_now_iso(),
        "row_id": row.row_id if row else None,
        "match": {
            "source_name": row.source_name if row else None,
            "caption": row.caption if row else None,
            "fiscal_year": row.fiscal_year if row else None,
            "metric_key": row.metric_key if row else None,
        }
        if row
        else None,
        "patch": _json_primitive(patch or {}),
    }
    if extra:
        payload.update(_json_primitive(extra))
    append_decision(deal, payload)
    return decision_id


def correct_row(
    deal: Deal,
    row_id: str,
    *,
    reason: str,
    actor: str,
    value: float | None = None,
    metric_key: str | None = None,
    unit: str | None = None,
    currency: str | None = None,
    scale: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Machine misread — patch fields and promote when metric+year present."""
    reason = _require_reason(reason)
    rows = load_rows(deal)
    row = _find_row(rows, row_id)
    updates: dict[str, Any] = {"assumption": False}
    if value is not None:
        updates["value"] = float(value)
    if caption is not None:
        updates["caption"] = caption.strip()
        hit = map_caption(caption)
        if hit and metric_key is None:
            updates["metric_key"] = hit.metric_key
            updates["metric_family"] = hit.family
    if metric_key is not None:
        updates["metric_key"] = metric_key
        hit = map_caption(metric_key.replace("_", " "))
        updates["metric_family"] = hit.family if hit else MetricFamily.OTHER
    if unit is not None:
        updates["unit"] = unit
    if currency is not None:
        updates["currency"] = currency
    if scale is not None:
        updates["scale"] = scale

    decision_id = _write_decision(
        deal,
        action="correct",
        row=row,
        reason=reason,
        actor=actor,
        patch=updates,
    )
    updated = row.model_copy(update=updates)
    if updated.metric_key and updated.fiscal_year is not None:
        updated = updated.model_copy(update={"status": RowStatus.PROMOTED})
    else:
        updated = updated.model_copy(update={"status": RowStatus.CANDIDATE})

    new_rows = [updated if r.row_id == row_id else r for r in rows]
    # Drop other conflicting candidates for same metric+year (reviewer chose this correction)
    if updated.metric_key and updated.fiscal_year is not None:
        fixed: list[ExtractedRow] = []
        for r in new_rows:
            if (
                r.row_id != row_id
                and r.metric_key == updated.metric_key
                and r.fiscal_year == updated.fiscal_year
                and r.status != RowStatus.DROPPED
            ):
                fixed.append(r.model_copy(update={"status": RowStatus.DROPPED}))
            else:
                fixed.append(r)
        new_rows = fixed

    promoted = load_promoted(deal)
    if updated.status == RowStatus.PROMOTED:
        promoted = _upsert_promoted(promoted, row=updated, decision_id=decision_id, auto=False)
    save_rows(deal, new_rows)
    save_promoted(deal, promoted)
    issues = _rebuild_issues_from_rows(deal, new_rows)
    save_issues(deal, issues)
    _refresh_meta(deal, new_rows, issues, promoted)
    return {
        "decision_id": decision_id,
        "action": "correct",
        "row": updated.model_dump(mode="json"),
    }


def drop_row(deal: Deal, row_id: str, *, reason: str, actor: str) -> dict[str, Any]:
    """Not a figure — remove from candidates."""
    reason = _require_reason(reason)
    rows = load_rows(deal)
    row = _find_row(rows, row_id)
    decision_id = _write_decision(deal, action="drop", row=row, reason=reason, actor=actor)
    updated = row.model_copy(update={"status": RowStatus.DROPPED})
    new_rows = [updated if r.row_id == row_id else r for r in rows]
    promoted = [p for p in load_promoted(deal) if p.row_id != row_id]
    save_rows(deal, new_rows)
    save_promoted(deal, promoted)
    issues = _rebuild_issues_from_rows(deal, new_rows)
    save_issues(deal, issues)
    _refresh_meta(deal, new_rows, issues, promoted)
    return {
        "decision_id": decision_id,
        "action": "drop",
        "row": updated.model_dump(mode="json"),
    }


def vouch_row(deal: Deal, row_id: str, *, reason: str, actor: str) -> dict[str, Any]:
    """Read was correct; release on reviewer authority (must not be used just to clear a list)."""
    reason = _require_reason(reason)
    rows = load_rows(deal)
    row = _find_row(rows, row_id)
    if not row.metric_key or row.fiscal_year is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot vouch a row without metric_key and fiscal_year — correct/map it first.",
        )
    decision_id = _write_decision(deal, action="vouch", row=row, reason=reason, actor=actor)
    updated = row.model_copy(update={"status": RowStatus.VOUCHED, "assumption": False})
    new_rows = [updated if r.row_id == row_id else r for r in rows]
    # Hold siblings for same metric+year (governing source chosen)
    fixed: list[ExtractedRow] = []
    for r in new_rows:
        if (
            r.row_id != row_id
            and r.metric_key == updated.metric_key
            and r.fiscal_year == updated.fiscal_year
            and r.status not in {RowStatus.DROPPED}
        ):
            fixed.append(r.model_copy(update={"status": RowStatus.HELD_OUT}))
        else:
            fixed.append(r)
    new_rows = fixed
    promoted = _upsert_promoted(load_promoted(deal), row=updated, decision_id=decision_id, auto=False)
    save_rows(deal, new_rows)
    save_promoted(deal, promoted)
    issues = _rebuild_issues_from_rows(deal, new_rows)
    save_issues(deal, issues)
    _refresh_meta(deal, new_rows, issues, promoted)
    return {
        "decision_id": decision_id,
        "action": "vouch",
        "row": updated.model_dump(mode="json"),
    }


def accept_conflict(
    deal: Deal,
    *,
    metric_key: str,
    fiscal_year: int,
    value: float,
    reason: str,
    actor: str,
    row_id: str | None = None,
) -> dict[str, Any]:
    """Accept a conflict candidate (proposal or alternate) as governing value."""
    reason = _require_reason(reason)
    hit = map_caption(metric_key)
    resolved_key = hit.metric_key if hit else metric_key.strip()
    rows = load_rows(deal)
    target_rows = [
        r
        for r in rows
        if r.metric_key == resolved_key
        and r.fiscal_year == fiscal_year
        and round(r.value, 6) == round(float(value), 6)
        and r.status != RowStatus.DROPPED
    ]
    if row_id:
        target_rows = [r for r in target_rows if r.row_id == row_id] or [
            r for r in rows if r.row_id == row_id
        ]
    if not target_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching candidate rows for that metric/year/value",
        )
    primary = target_rows[0]
    decision_id = _write_decision(
        deal,
        action="accept",
        row=primary,
        reason=reason,
        actor=actor,
        patch={"value": float(value), "metric_key": resolved_key, "fiscal_year": fiscal_year},
        extra={"accepted_value": float(value), "metric_key": resolved_key, "fiscal_year": fiscal_year},
    )
    win_ids = {r.row_id for r in target_rows}
    win_sources = sorted({r.source_name for r in target_rows})
    win_captions = sorted({r.caption for r in target_rows})
    new_rows: list[ExtractedRow] = []
    for r in rows:
        if r.row_id in win_ids:
            new_rows.append(
                r.model_copy(update={"status": RowStatus.PROMOTED, "assumption": False, "value": float(value)})
            )
        elif r.metric_key == resolved_key and r.fiscal_year == fiscal_year and r.status != RowStatus.DROPPED:
            new_rows.append(r.model_copy(update={"status": RowStatus.DROPPED}))
        else:
            new_rows.append(r)
    promoted = _upsert_promoted(
        load_promoted(deal),
        row=primary.model_copy(update={"value": float(value), "status": RowStatus.PROMOTED, "metric_key": resolved_key}),
        decision_id=decision_id,
        auto=False,
        sources=win_sources,
        captions=win_captions,
    )
    save_rows(deal, new_rows)
    save_promoted(deal, promoted)
    issues = _rebuild_issues_from_rows(deal, new_rows)
    save_issues(deal, issues)
    _refresh_meta(deal, new_rows, issues, promoted)
    return {
        "decision_id": decision_id,
        "action": "accept",
        "metric_key": resolved_key,
        "fiscal_year": fiscal_year,
        "value": float(value),
        "sources": win_sources,
    }


def load_decisions(deal: Deal) -> list[dict[str, Any]]:
    import json

    from agetic_cdd_api.services_databook_store import databook_dir

    path = databook_dir(deal) / "decisions.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed decision line %s in %s: %s",
                    line_no,
                    path,
                    exc,
                )
                continue
            if isinstance(item, dict):
                out.append(item)
            else:
                logger.warning(
                    "Skipping non-object decision line %s in %s (got %s)",
                    line_no,
                    path,
                    type(item).__name__,
                )
    except OSError as exc:
        logger.warning("Failed to read decisions from %s: %s", path, exc)
        return []
    return out


def _find_overlay_index(
    working: list[ExtractedRow],
    by_id: dict[str, int],
    *,
    row_id: Any,
    match: dict[str, Any],
) -> int | None:
    if row_id:
        idx = by_id.get(str(row_id))
        if idx is not None:
            return idx
    for i, r in enumerate(working):
        if (
            r.source_name == match.get("source_name")
            and r.caption == match.get("caption")
            and r.fiscal_year == match.get("fiscal_year")
        ):
            return i
    return None


def apply_decision_overlays(deal: Deal, rows: list[ExtractedRow]) -> tuple[list[ExtractedRow], list[PromotedMetric]]:
    """Replay decisions.jsonl onto freshly extracted rows (latest decision wins per match)."""
    decisions = load_decisions(deal)
    if not decisions:
        return rows, []

    # Indices stay stable: overlays only mutate status/fields in place, never reorder/remove rows.
    working = list(rows)
    by_id = {r.row_id: i for i, r in enumerate(working)}
    promoted: list[PromotedMetric] = []

    for dec in decisions:
        action = dec.get("action")
        match = dec.get("match") or {}
        patch = dict(dec.get("patch") or {})
        decision_id = str(dec.get("decision_id") or "")
        row_id = dec.get("row_id")

        if action == "accept":
            metric_key = dec.get("metric_key") or patch.get("metric_key") or match.get("metric_key")
            fy = dec.get("fiscal_year") if dec.get("fiscal_year") is not None else patch.get("fiscal_year")
            if fy is None:
                fy = match.get("fiscal_year")
            value = dec.get("accepted_value")
            if value is None:
                value = patch.get("value")
            if metric_key and fy is not None and value is not None:
                win_rows = [
                    r
                    for r in working
                    if r.metric_key == metric_key
                    and r.fiscal_year == int(fy)
                    and round(r.value, 6) == round(float(value), 6)
                ]
                win_ids = {r.row_id for r in win_rows}
                win_sources = sorted({r.source_name for r in win_rows})
                win_captions = sorted({r.caption for r in win_rows})
                primary = None
                for i, r in enumerate(working):
                    if r.row_id in win_ids:
                        u = r.model_copy(
                            update={
                                "status": RowStatus.PROMOTED,
                                "assumption": False,
                                "value": float(value),
                            }
                        )
                        primary = primary or u
                        working[i] = u
                    elif r.metric_key == metric_key and r.fiscal_year == int(fy):
                        working[i] = r.model_copy(update={"status": RowStatus.DROPPED})
                if primary:
                    promoted = _upsert_promoted(
                        promoted,
                        row=primary,
                        decision_id=decision_id,
                        auto=False,
                        sources=win_sources,
                        captions=win_captions,
                    )
            continue

        idx = _find_overlay_index(working, by_id, row_id=row_id, match=match)
        if idx is None:
            continue
        row = working[idx]
        if action == "drop":
            working[idx] = row.model_copy(update={"status": RowStatus.DROPPED})
            promoted = [p for p in promoted if p.row_id != row.row_id]
        elif action == "correct":
            updates = {
                k: v
                for k, v in patch.items()
                if k
                in {
                    "value",
                    "metric_key",
                    "metric_family",
                    "unit",
                    "currency",
                    "scale",
                    "caption",
                    "assumption",
                }
            }
            if "metric_family" in updates and isinstance(updates["metric_family"], str):
                try:
                    updates["metric_family"] = MetricFamily(updates["metric_family"])
                except ValueError:
                    updates["metric_family"] = MetricFamily.OTHER
            updated = row.model_copy(update=updates)
            if updated.metric_key and updated.fiscal_year is not None:
                updated = updated.model_copy(update={"status": RowStatus.PROMOTED})
            working[idx] = updated
            if updated.metric_key and updated.fiscal_year is not None:
                for i, r in enumerate(working):
                    if (
                        r.row_id != updated.row_id
                        and r.metric_key == updated.metric_key
                        and r.fiscal_year == updated.fiscal_year
                        and r.status != RowStatus.DROPPED
                    ):
                        working[i] = r.model_copy(update={"status": RowStatus.DROPPED})
            if updated.status == RowStatus.PROMOTED:
                promoted = _upsert_promoted(promoted, row=updated, decision_id=decision_id, auto=False)
        elif action == "vouch":
            if row.metric_key and row.fiscal_year is not None:
                updated = row.model_copy(update={"status": RowStatus.VOUCHED, "assumption": False})
                working[idx] = updated
                for i, r in enumerate(working):
                    if (
                        r.row_id != updated.row_id
                        and r.metric_key == updated.metric_key
                        and r.fiscal_year == updated.fiscal_year
                        and r.status != RowStatus.DROPPED
                    ):
                        working[i] = r.model_copy(update={"status": RowStatus.HELD_OUT})
                promoted = _upsert_promoted(promoted, row=updated, decision_id=decision_id, auto=False)

    return working, promoted
