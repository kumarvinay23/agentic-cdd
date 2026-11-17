"""Gate 3 — one canonical Financial history series cell per metric × year.

After statement ingest, multiple SELECTED/DERIVED facts can still map to the
same UI metric (concept aliases, period shapes, competing files). This pass
keeps one winner and demotes the rest to COMPARATIVE so FDD/CDD cannot price
off mixed figures.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_CHOSEN = frozenset({"SELECTED", "DERIVED"})
_PERIOD_RANK = {
    "FY": 0,
    "YTD": 1,
    "LTM": 2,
    "TTM": 2,
    "FM": 3,
    "AS_AT": 4,
}
_TIER_RANK = {"A": 0, "B": 1, "C": 2}
_REASONS = {
    "LOWER_AUTHORITY": (
        "a higher-authority source was selected for this Financial history metric"
    ),
    "EQUAL_AUTHORITY_CONFLICT": (
        "two sources of equal authority disagree for this Financial history metric"
    ),
    "DUPLICATE": "the same value is already selected for this Financial history metric",
}


def canonicalize_financial_history(deal_id: str) -> dict[str, Any]:
    """Keep one SELECTED/DERIVED fact per metric × fiscal year; demote peers."""
    deal_id = str(deal_id or "").strip()
    if not deal_id:
        return {
            "deal_id": "",
            "groups": 0,
            "winners": [],
            "demoted": [],
            "conflicts": [],
        }

    from agetic_cdd_api.services_fact_repository import facts_for, update_fact

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in facts_for(deal_id):
        key = series_group_key(row)
        if key is None:
            continue
        if str(row.get("status") or "") not in _CHOSEN:
            continue
        if row.get("value") is None:
            continue
        groups[key].append(row)

    winners: list[str] = []
    demoted: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for key, pool in groups.items():
        ranked = sorted(pool, key=series_candidate_rank)
        winner = ranked[0]
        winner_id = str(winner.get("fact_id") or "")
        if winner_id:
            winners.append(winner_id)
        if len(ranked) == 1:
            continue

        winner_auth = _authority_rank(winner)
        for loser in ranked[1:]:
            loser_id = str(loser.get("fact_id") or "")
            if not loser_id or loser_id == winner_id:
                continue
            same = _same_value(loser.get("value"), winner.get("value"))
            if same:
                reason = "DUPLICATE"
            elif _authority_rank(loser) == winner_auth:
                reason = "EQUAL_AUTHORITY_CONFLICT"
                conflicts.append(
                    {
                        "metric": key[1],
                        "fiscal_year": key[2],
                        "winner_fact_id": winner_id,
                        "loser_fact_id": loser_id,
                        "winner_value": winner.get("value"),
                        "loser_value": loser.get("value"),
                    }
                )
            else:
                reason = "LOWER_AUTHORITY"
            update_fact(
                loser_id,
                {
                    "status": "COMPARATIVE",
                    "reason_code": reason,
                    "reason_detail": _REASONS[reason],
                },
            )
            demoted.append(
                {
                    "fact_id": loser_id,
                    "metric": key[1],
                    "fiscal_year": key[2],
                    "reason_code": reason,
                    "winner_fact_id": winner_id,
                }
            )

    return {
        "deal_id": deal_id,
        "groups": len(groups),
        "winners": winners,
        "demoted": demoted,
        "conflicts": conflicts,
    }


def series_group_key(row: dict[str, Any]) -> tuple[Any, ...] | None:
    """(entity, metric, fiscal_year, basis) for Financial history canonicalization."""
    from agetic_cdd_api.services_databook_view import _fiscal_year, _metric_for_concept

    concept = str(row.get("concept_id") or "")
    metric = _metric_for_concept(concept)
    year = _fiscal_year(row)
    if not metric or year is None:
        return None
    entity = str(row.get("entity_id") or "CONSOLIDATED")
    basis = str(row.get("basis") or "ACTUAL")
    return (entity, metric, int(year), basis)


def series_candidate_rank(row: dict[str, Any]) -> tuple[Any, ...]:
    """Lower tuple wins. Mirrors view preference + resolver authority."""
    from agetic_cdd_api.services_databook_view import (
        _SERIES_PRIORITY,
        _metric_for_concept,
    )

    status = str(row.get("status") or "")
    status_rank = 0 if status == "SELECTED" else 1
    period_rank = _PERIOD_RANK.get(str(row.get("period_type") or ""), 9)
    concept = str(row.get("concept_id") or "")
    metric = _metric_for_concept(concept)
    order = _SERIES_PRIORITY.get(metric) or ()
    concept_rank = order.index(concept) if concept in order else 99
    dims = row.get("dimensions") or {}
    dim_rank = 0 if not dims else 1
    auth = _authority_rank(row)
    tier = _TIER_RANK.get(str(row.get("evidence_tier") or "").upper(), 3)
    mapping = row.get("mapping") if isinstance(row.get("mapping"), dict) else {}
    kind = str(mapping.get("row_kind") or "").upper()
    kind_rank = 0 if kind == "LINE" else 1
    fact_id = str(row.get("fact_id") or "")
    return (
        status_rank,
        period_rank,
        concept_rank,
        dim_rank,
        auth,
        tier,
        kind_rank,
        fact_id,
    )


def duplicate_metric_years(
    facts: list[dict[str, Any]] | None = None,
    *,
    deal_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return metric×year groups that still have multiple SELECTED/DERIVED facts."""
    if facts is None:
        from agetic_cdd_api.services_fact_repository import facts_for

        facts = facts_for(str(deal_id or ""))
    groups: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for row in facts or []:
        if str(row.get("status") or "") not in _CHOSEN:
            continue
        key = series_group_key(row)
        if key is None or row.get("value") is None:
            continue
        fid = str(row.get("fact_id") or "")
        if fid:
            groups[key].append(fid)
    return [
        {
            "entity_id": key[0],
            "metric": key[1],
            "fiscal_year": key[2],
            "basis": key[3],
            "fact_ids": ids,
        }
        for key, ids in groups.items()
        if len(ids) > 1
    ]


def _authority_rank(row: dict[str, Any]) -> int:
    from agetic_cdd_api.services_resolver import _rank

    return int(_rank(row))


def _same_value(left: Any, right: Any) -> bool:
    try:
        return round(float(left), 6) == round(float(right), 6)
    except (TypeError, ValueError):
        return left == right
