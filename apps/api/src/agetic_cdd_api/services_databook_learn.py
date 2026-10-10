"""Phase 6 — learning from HITL decisions (OL-5 lineage, OL-6 traps, OL-7 memory).

Every decision can:
  * record release lineage (decision_id → release version)
  * seed a trap regression case for P7
  * upsert mapping memory so remaps survive rescans
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_databook_coa import alias_key, normalize_caption
from agetic_cdd_api.services_databook_models import (
    DealLike,
    DecisionLineage,
    MappingMemoryEntry,
    TrapRecord,
)
from agetic_cdd_api.services_databook_store import (
    _exclusive_lock,
    _read_json,
    _write_json,
    databook_dir,
    update_meta,
)
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)


def _deal_slug(deal: DealLike) -> str:
    return str(getattr(deal, "slug", None) or getattr(deal, "id", "") or "")


def _memory_path(deal: DealLike) -> Path:
    return databook_dir(deal) / "mapping_memory.json"


def _traps_path(deal: DealLike) -> Path:
    return databook_dir(deal) / "traps.jsonl"


def _lineage_path(deal: DealLike) -> Path:
    return databook_dir(deal) / "decision_lineage.jsonl"


def caption_memory_key(caption: str) -> str:
    return alias_key(normalize_caption(caption or ""))


def load_mapping_memory(deal: DealLike) -> list[MappingMemoryEntry]:
    raw = _read_json(_memory_path(deal), {"entries": []})
    entries = raw.get("entries") if isinstance(raw, dict) else []
    out: list[MappingMemoryEntry] = []
    if not isinstance(entries, list):
        return out
    for item in entries:
        if not isinstance(item, dict):
            continue
        try:
            out.append(MappingMemoryEntry.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping bad mapping memory entry: %s", exc)
    return out


def save_mapping_memory(deal: DealLike, entries: list[MappingMemoryEntry]) -> None:
    _write_json(
        _memory_path(deal),
        {
            "entries": [e.model_dump(mode="json") for e in entries],
            "updated_at": utc_now_iso(),
            "count": len(entries),
        },
    )
    try:
        count = len(entries)
        update_meta(
            deal,
            lambda meta: meta.model_copy(update={"mapping_memory_count": count}),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to update mapping_memory_count: %s", exc)


def lookup_mapping_memory(
    deal: DealLike | None,
    caption: str,
    *,
    sector_pack: str = "generic",
    statement: str | None = None,
) -> MappingMemoryEntry | None:
    """Return the best learned remap for a caption, if any."""
    if deal is None:
        return None
    key = caption_memory_key(caption)
    if not key:
        return None
    candidates = [
        e
        for e in load_mapping_memory(deal)
        if e.caption_key == key
        and (e.sector_pack in {sector_pack, "generic", "*"} or not e.sector_pack)
    ]
    if not candidates:
        return None
    if statement:
        scoped = [e for e in candidates if not e.statement or e.statement == statement]
        if scoped:
            candidates = scoped
    candidates.sort(key=lambda e: (-e.hit_count, e.updated_at), reverse=False)
    candidates.sort(key=lambda e: e.hit_count, reverse=True)
    return candidates[0]


def upsert_mapping_memory(
    deal: DealLike,
    *,
    caption: str,
    metric_key: str,
    family: str | None = None,
    statement: str | None = None,
    sector_pack: str = "generic",
    decision_id: str | None = None,
) -> MappingMemoryEntry:
    key = caption_memory_key(caption)
    now = utc_now_iso()
    entries = load_mapping_memory(deal)
    for i, existing in enumerate(entries):
        if (
            existing.caption_key == key
            and existing.metric_key == metric_key
            and (existing.statement or None) == (statement or None)
            and existing.sector_pack == sector_pack
        ):
            updated = existing.model_copy(
                update={
                    "hit_count": existing.hit_count + 1,
                    "updated_at": now,
                    "source_decision_id": decision_id or existing.source_decision_id,
                    "family": family or existing.family,
                }
            )
            entries[i] = updated
            save_mapping_memory(deal, entries)
            return updated
    entry = MappingMemoryEntry(
        memory_id="mm_" + uuid.uuid4().hex[:12],
        caption_key=key,
        metric_key=metric_key,
        family=family,
        statement=statement,
        sector_pack=sector_pack,
        source_decision_id=decision_id,
        deal_slug=_deal_slug(deal),
        hit_count=1,
        created_at=now,
        updated_at=now,
    )
    entries.append(entry)
    save_mapping_memory(deal, entries)
    return entry


def append_trap(deal: DealLike, trap: TrapRecord) -> None:
    path = _traps_path(deal)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(trap.model_dump(mode="json"), default=str) + "\n"
    with _exclusive_lock(path):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
    try:
        update_meta(
            deal,
            lambda meta: meta.model_copy(
                update={"trap_count": int(meta.trap_count or 0) + 1}
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to bump trap_count: %s", exc)


def load_traps(deal: DealLike) -> list[TrapRecord]:
    path = _traps_path(deal)
    if not path.is_file():
        return []
    out: list[TrapRecord] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                try:
                    out.append(TrapRecord.model_validate(raw))
                except Exception:  # noqa: BLE001
                    continue
    except OSError as exc:
        logger.warning("Failed to read traps for %s: %s", _deal_slug(deal), exc)
    return out


def append_lineage(deal: DealLike, lineage: DecisionLineage) -> None:
    path = _lineage_path(deal)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(lineage.model_dump(mode="json"), default=str) + "\n"
    with _exclusive_lock(path):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())


def load_lineage(deal: DealLike) -> list[DecisionLineage]:
    path = _lineage_path(deal)
    if not path.is_file():
        return []
    out: list[DecisionLineage] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                try:
                    out.append(DecisionLineage.model_validate(raw))
                except Exception:  # noqa: BLE001
                    continue
    except OSError:
        return out
    return out


def _trap_kind_for_action(action: str, *, remapped: bool, value_changed: bool) -> str:
    if action in {"drop", "exclude"}:
        return "exclude_row"
    if action in {"vouch", "confirm"}:
        return "confirm_proven"
    if action == "accept":
        return "pick_alternative"
    if remapped:
        return "wrong_metric"
    if value_changed:
        return "wrong_value"
    return "wrong_metric"


def learn_from_decision(
    deal: DealLike,
    *,
    decision: dict[str, Any],
    release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply OL-5/6/7 side effects for one HITL decision. Safe to call best-effort."""
    action = str(decision.get("action") or "")
    decision_id = str(decision.get("decision_id") or "")
    match = decision.get("match") if isinstance(decision.get("match"), dict) else {}
    patch = decision.get("patch") if isinstance(decision.get("patch"), dict) else {}
    caption = str(match.get("caption") or patch.get("caption") or "") or None
    metric_key = str(
        patch.get("metric_key") or match.get("metric_key") or decision.get("metric_key") or ""
    ) or None
    fiscal_year = match.get("fiscal_year")
    if fiscal_year is None:
        fiscal_year = decision.get("fiscal_year")
    try:
        fy_int = int(fiscal_year) if fiscal_year is not None else None
    except (TypeError, ValueError):
        fy_int = None

    prior_metric = str(match.get("metric_key") or "") or None
    remapped = bool(
        metric_key
        and prior_metric
        and metric_key != prior_metric
    ) or (action in {"correct", "remap"} and patch.get("metric_key"))
    value_changed = "value" in patch and patch.get("value") is not None

    # OL-5 lineage
    lineage = DecisionLineage(
        decision_id=decision_id or ("dec_" + uuid.uuid4().hex[:10]),
        action=action,
        at=str(decision.get("at") or utc_now_iso()),
        actor=str(decision.get("actor") or "") or None,
        row_id=str(decision.get("row_id") or "") or None,
        release_id=(release or {}).get("release_id") if release else None,
        release_version=(release or {}).get("version") if release else None,
        match=dict(match),
    )
    try:
        append_lineage(deal, lineage)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to append decision lineage: %s", exc)

    # OL-7 mapping memory on remap / correct with new metric
    memory_entry = None
    if caption and metric_key and (remapped or action in {"correct", "remap", "vouch", "confirm"}):
        try:
            from agetic_cdd_api.services_databook_coa import coa_node_for_metric
            from agetic_cdd_api.services_databook_store import load_params

            try:
                params = load_params(deal)
                sector = str(getattr(params, "sector_pack", None) or "generic")
            except Exception:  # noqa: BLE001
                sector = "generic"
            fam = None
            try:
                node = coa_node_for_metric(metric_key, sector)
                if node is not None:
                    fam = getattr(node.family, "value", None) or str(node.family)
            except Exception:  # noqa: BLE001
                fam = None
            memory_entry = upsert_mapping_memory(
                deal,
                caption=caption,
                metric_key=metric_key,
                family=fam,
                sector_pack=sector,
                decision_id=decision_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to upsert mapping memory: %s", exc)

    # OL-6 trap
    trap = None
    try:
        bad_value = match.get("value") if isinstance(match.get("value"), (int, float)) else None
        good_value = patch.get("value") if isinstance(patch.get("value"), (int, float)) else None
        if good_value is None and isinstance(decision.get("value"), (int, float)):
            good_value = float(decision["value"])
        trap = TrapRecord(
            trap_id="tr_" + hashlib.sha1(
                f"{decision_id}|{action}|{caption}|{metric_key}".encode()
            ).hexdigest()[:12],
            kind=_trap_kind_for_action(action, remapped=bool(remapped), value_changed=value_changed),  # type: ignore[arg-type]
            caption=caption,
            metric_key=metric_key or prior_metric,
            fiscal_year=fy_int,
            bad_value=float(bad_value) if bad_value is not None else None,
            good_value=float(good_value) if good_value is not None else None,
            source_name=str(match.get("source_name") or "") or None,
            source_decision_id=decision_id or None,
            deal_slug=_deal_slug(deal),
            note=str(decision.get("reason") or "") or None,
            created_at=utc_now_iso(),
        )
        append_trap(deal, trap)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to seed trap from decision: %s", exc)
        trap = None

    return {
        "lineage": lineage.model_dump(mode="json"),
        "mapping_memory": memory_entry.model_dump(mode="json") if memory_entry else None,
        "trap": trap.model_dump(mode="json") if trap else None,
    }
