"""Choose one value per figure from the ontology authority order.

A lower-authority document stays on the fact with a reason. A normal load
therefore stores one chosen row per figure.
"""

from __future__ import annotations

from typing import Any

from agetic_cdd_api.services_fact_repository import facts_for, update_fact
from agetic_cdd_api.services_ontology import load_ontology

_CHOSEN = {"SELECTED", "DERIVED"}
_PLAN_BASIS = {"BUDGET", "FORECAST", "MGMT_CASE"}
_REASONS = {
    "LOWER_AUTHORITY": "a higher-authority source was selected",
    "EQUAL_AUTHORITY_CONFLICT": "two sources of equal authority disagree",
    "DUPLICATE": "the same value is already selected",
}


def resolve_fact(row: dict[str, Any]) -> dict[str, Any]:
    """Return the row to store. Demote the other chosen row for this figure."""
    prepared = dict(row)
    if prepared.get("status") not in _CHOSEN:
        return prepared
    prepared.setdefault("entity_id", "CONSOLIDATED")
    prepared.setdefault("dimensions", {})
    current = _peer(prepared)
    if current is None:
        return prepared
    winner_is_new, reason = _outcome(current, prepared)
    if winner_is_new:
        update_fact(str(current["fact_id"]), _demotion(reason))
        return prepared
    demoted = dict(prepared)
    demoted.update(_demotion(reason))
    return demoted


def _peer(row: dict[str, Any]) -> dict[str, Any] | None:
    key = _key(row)
    for fact in facts_for(str(row.get("deal_id") or "")):
        if fact.get("fact_id") == row.get("fact_id") or fact.get("status") not in _CHOSEN:
            continue
        if _key(fact) == key:
            return fact
    return None


def _outcome(current: dict[str, Any], incoming: dict[str, Any]) -> tuple[bool, str]:
    current_rank = _rank(current)
    incoming_rank = _rank(incoming)
    if incoming_rank < current_rank:
        return True, "LOWER_AUTHORITY"
    if incoming_rank > current_rank:
        return False, "LOWER_AUTHORITY"
    if incoming.get("value") != current.get("value"):
        return False, "EQUAL_AUTHORITY_CONFLICT"
    return False, "DUPLICATE"


def _rank(row: dict[str, Any]) -> int:
    onto = load_ontology()
    family = _family(row, onto.b["authority_family_by_namespace"])
    order = list(onto.b["authority_order"].get(family) or [])
    doc_type = _doc_type(row)
    if doc_type in order:
        return order.index(doc_type)
    return len(order) + 1


def _family(row: dict[str, Any], families: dict[str, str]) -> str:
    namespace = str(row.get("concept_id") or "").split(".", 1)[0]
    family = families.get(namespace, "KPI")
    if family == "FINANCIAL_ACTUAL" and row.get("basis") in _PLAN_BASIS:
        return "FINANCIAL_PLAN"
    if family == "FINANCIAL_ACTUAL" and row.get("period_type") == "FM":
        return "FINANCIAL_ACTUAL_MONTHLY"
    return family


def _doc_type(row: dict[str, Any]) -> str:
    if row.get("doc_type"):
        return str(row["doc_type"])
    if row.get("status") == "DERIVED":
        return "CALCULATED"
    from agetic_cdd_api.services_document_register import document_type

    return document_type(str(row.get("doc_id") or "")) or ""


def _key(row: dict[str, Any]) -> tuple:
    dimensions = tuple(sorted((str(key), str(value)) for key, value in (row.get("dimensions") or {}).items()))
    return (
        row.get("deal_id"),
        row.get("entity_id") or "CONSOLIDATED",
        row.get("concept_id"),
        row.get("period_type"),
        row.get("period_end"),
        row.get("basis"),
        dimensions,
    )


def _demotion(reason: str) -> dict[str, str]:
    return {"status": "COMPARATIVE", "reason_code": reason, "reason_detail": _REASONS[reason]}
