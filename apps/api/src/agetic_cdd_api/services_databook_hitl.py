"""Reviewer decisions written onto ontology facts.

Accept, remap, drop, vouch, and reread update `fact` / `mapping_decision`.
The file-backed store stays in place; callers dual-write while both paths exist.
A decision refreshes open flags and, when the profile is confirmed, republishes.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agetic_cdd_api.services_databook_view import _SERIES_PRIORITY
from agetic_cdd_api.services_fact_repository import (
    facts_for,
    get_fact,
    release_document,
    update_fact,
)
from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_published_pages import comparisons_from_pages, pages_from_tabs

_CHOSEN = {"SELECTED", "DERIVED"}
_OPEN = {"SELECTED", "DERIVED", "CANDIDATE", "COMPARATIVE"}


def accept_conflict(
    deal_id: str,
    *,
    fact_id: str | None = None,
    metric_key: str | None = None,
    fiscal_year: int | None = None,
    value: float | None = None,
    reason: str,
    actor: str,
) -> dict[str, Any] | None:
    """Choose one fact as SELECTED and demote the other values for that figure."""
    winner = _match_fact(
        deal_id,
        fact_id=fact_id,
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        value=value,
    )
    if winner is None:
        return None
    detail = f"reviewer {actor} accepted this value: {reason.strip()}"
    _demote_peers(winner, reason_detail=detail)
    mapping = dict(winner.get("mapping") or {})
    mapping["reviewer"] = actor
    mapping["reviewer_status"] = "accepted"
    mapping["method"] = mapping.get("method") or "USER"
    update_fact(
        str(winner["fact_id"]),
        {
            "status": "SELECTED",
            "reason_code": None,
            "reason_detail": None,
            "mapping": mapping,
            "reviewed_by": actor,
        },
    )
    return _after(deal_id, "accept", str(winner["fact_id"]))


def remap_fact(
    deal_id: str,
    fact_id: str,
    *,
    metric_key: str,
    reason: str,
    actor: str,
) -> dict[str, Any] | None:
    """Point a fact at another ontology concept and record a USER mapping decision."""
    fact = _owned(deal_id, fact_id)
    if fact is None:
        return None
    concept_id = concept_for_metric(metric_key)
    if not concept_id:
        return None
    onto = load_ontology()
    concept = onto.concepts[concept_id]
    moved = dict(fact)
    moved["concept_id"] = concept_id
    moved["unit_type"] = concept.get("unit_type") or fact.get("unit_type")
    _demote_peers(moved, reason_detail=f"reviewer {actor} remapped onto this concept: {reason.strip()}")
    mapping = dict(fact.get("mapping") or {})
    mapping.update(
        {
            "method": "USER",
            "reviewer": actor,
            "reviewer_status": "remapped",
            "confidence": 1.0,
            "prior_concept_id": fact.get("concept_id"),
        }
    )
    update_fact(
        fact_id,
        {
            "concept_id": concept_id,
            "unit_type": concept.get("unit_type") or fact.get("unit_type"),
            "status": "SELECTED" if fact.get("value") is not None else fact.get("status"),
            "reason_code": None if fact.get("value") is not None else fact.get("reason_code"),
            "reason_detail": None if fact.get("value") is not None else fact.get("reason_detail"),
            "mapping": mapping,
            "reviewed_by": actor,
        },
    )
    from agetic_cdd_api.services_mapper import record_mappings

    record_mappings(
        [
            {
                "row_kind": "LINE",
                "concept_id": concept_id,
                "method": "USER",
                "confidence": 1.0,
                "label_as_read": (fact.get("mapping") or {}).get("label") or metric_key,
                "label_path": [],
                "dimensions": dict(fact.get("dimensions") or {}),
                "sheet": None,
                "row": None,
            }
        ],
        deal_id,
        str(fact.get("doc_id") or ""),
    )
    return _after(deal_id, "remap", fact_id)


def drop_fact(
    deal_id: str,
    fact_id: str,
    *,
    reason: str,
    actor: str,
    action: str = "drop",
) -> dict[str, Any] | None:
    """Take a fact out of the publish set. The reviewer reason is stored."""
    fact = _owned(deal_id, fact_id)
    if fact is None:
        return None
    mapping = dict(fact.get("mapping") or {})
    mapping["reviewer"] = actor
    mapping["reviewer_status"] = action
    update_fact(
        fact_id,
        {
            "status": "REJECTED",
            "reason_code": "USER_EXCLUDED",
            "reason_detail": f"reviewer {actor}: {reason.strip()}",
            "mapping": mapping,
            "reviewed_by": actor,
        },
    )
    return _after(deal_id, action, fact_id)


def vouch_fact(
    deal_id: str,
    fact_id: str,
    *,
    reason: str,
    actor: str,
    action: str = "vouch",
) -> dict[str, Any] | None:
    """Confirm a figure, including an inherited currency. Does not invent an ISO code."""
    fact = _owned(deal_id, fact_id)
    if fact is None:
        return None
    if str(fact.get("unit_type") or "") == "CURRENCY" and not fact.get("currency"):
        raise ValueError("cannot vouch a currency amount that has no ISO code")
    mapping = dict(fact.get("mapping") or {})
    mapping["reviewer"] = actor
    mapping["reviewer_status"] = "confirmed"
    if mapping.get("currency_source") == "assumed":
        mapping["currency_source"] = "confirmed"
    _demote_peers(
        fact,
        reason_detail=f"reviewer {actor} confirmed another value for this figure: {reason.strip()}",
    )
    update_fact(
        fact_id,
        {
            "status": "SELECTED",
            "reason_code": None,
            "reason_detail": None,
            "mapping": mapping,
            "reviewed_by": actor,
        },
    )
    return _after(deal_id, action, fact_id)


def reread_document(deal: Any, filename: str) -> dict[str, Any] | None:
    """Rerun the statement reader for one registered file. Other documents stay."""
    from agetic_cdd_api.services_document_register import register_room
    from agetic_cdd_api.services_statement_reader import _file_facts, store_lines
    from agetic_cdd_api.services_vdr import documents_dir

    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "")
    name = str(filename or "").strip()
    if not deal_id or not name:
        return None
    row = next((item for item in register_room(deal) if item.get("file_name") == name), None)
    if row is None:
        return None
    release_document(deal_id, str(row["doc_id"]))
    from agetic_cdd_api.services_ontology import load_ontology as _load
    from agetic_cdd_api.services_deal_profile import published_databook

    published = published_databook(deal_id) or {}
    currency = str(published.get("reporting_currency") or "USD")
    year_end = str(published.get("fiscal_year_end") or "12-31")
    found, locs, _items = _file_facts(
        documents_dir(deal) / name,
        row,
        _load(),
        currency,
        1,
        int(year_end.split("-")[0]),
        deal_id,
    )
    stored = store_lines(found or [], locs, deal_id, doc_type=row.get("doc_type")) if found else []
    refreshed = _refresh(deal_id)
    return {
        "action": "reread",
        "doc_id": row["doc_id"],
        "file_name": name,
        "facts": len(stored),
        "flags": refreshed.get("flags") or [],
    }


def concept_for_metric(metric_key: str) -> str | None:
    """Series key or concept id → ontology concept. Unknown captions return None."""
    text = str(metric_key or "").strip()
    if not text:
        return None
    onto = load_ontology()
    if text in onto.concepts:
        return text
    matches = [concept_id for concept_id, metric in _metric_pairs() if metric == text]
    if not matches:
        return None
    order = _SERIES_PRIORITY.get(text) or ()
    for concept_id in order:
        if concept_id in matches:
            return concept_id
    return matches[0]


def schedule_pages(deal_id: str) -> list[dict[str, Any]]:
    """Published-style pages from in-memory SELECTED/DERIVED facts (the view filter)."""
    onto = load_ontology()
    tabs: dict[str, list[dict[str, Any]]] = {}
    for row in facts_for(deal_id):
        if row.get("status") not in _CHOSEN or row.get("value") is None:
            continue
        concept = onto.concepts.get(str(row.get("concept_id") or "")) or {}
        mapping = row.get("mapping") if isinstance(row.get("mapping"), dict) else {}
        cell_range = str(mapping.get("cell_range") or "")
        if not cell_range:
            ids = row.get("source_location_ids") or []
            cell_range = str(ids[0]) if ids else ""
        if not cell_range:
            continue
        cell = {
            "fact_id": row.get("fact_id"),
            "concept_id": row.get("concept_id"),
            "value": row.get("value"),
            "period_end": row.get("period_end"),
            "cell_range": cell_range,
            "dimensions": row.get("dimensions") or {},
        }
        for schedule in concept.get("schedules") or []:
            tabs.setdefault(str(schedule), []).append(cell)
    return pages_from_tabs(tabs)


def yoy_citations(deal_id: str) -> list[dict[str, Any]]:
    """CDD year-over-year rows citing the selected fact ids."""
    return comparisons_from_pages(schedule_pages(deal_id))


def _match_fact(
    deal_id: str,
    *,
    fact_id: str | None,
    metric_key: str | None,
    fiscal_year: int | None,
    value: float | None,
) -> dict[str, Any] | None:
    if fact_id:
        owned = _owned(deal_id, fact_id)
        if owned is not None and str(owned.get("status") or "") != "REJECTED":
            return owned
    concepts = _concepts_for(metric_key)
    if not concepts or fiscal_year is None or value is None:
        return None
    target = round(float(value), 6)
    for row in facts_for(deal_id):
        if str(row.get("status") or "") not in _OPEN:
            continue
        if str(row.get("concept_id") or "") not in concepts:
            continue
        if _year(row) != int(fiscal_year):
            continue
        if row.get("value") is None or round(float(row["value"]), 6) != target:
            continue
        return row
    return None


def _concepts_for(metric_key: str | None) -> set[str]:
    text = str(metric_key or "").strip()
    if not text:
        return set()
    onto = load_ontology()
    if text in onto.concepts:
        return {text}
    return {concept_id for concept_id, metric in _metric_pairs() if metric == text}


def _metric_pairs() -> list[tuple[str, str]]:
    from agetic_cdd_api.services_databook_view import _SERIES_CONCEPTS

    return list(_SERIES_CONCEPTS.items())


def _owned(deal_id: str, fact_id: str) -> dict[str, Any] | None:
    row = get_fact(fact_id)
    if row is None or str(row.get("deal_id") or "") != deal_id:
        return None
    return row


def _demote_peers(winner: dict[str, Any], *, reason_detail: str) -> None:
    key = _figure(winner)
    for row in facts_for(str(winner.get("deal_id") or "")):
        if row.get("fact_id") == winner.get("fact_id"):
            continue
        if _figure(row) != key or str(row.get("status") or "") not in _OPEN:
            continue
        same = row.get("value") == winner.get("value")
        update_fact(
            str(row["fact_id"]),
            {
                "status": "COMPARATIVE",
                "reason_code": "DUPLICATE" if same else "LOWER_AUTHORITY",
                "reason_detail": "the same value is already selected" if same else reason_detail,
            },
        )


def _figure(row: dict[str, Any]) -> tuple:
    dimensions = tuple(
        sorted((str(key), str(value)) for key, value in (row.get("dimensions") or {}).items())
    )
    return (
        row.get("deal_id"),
        row.get("entity_id") or "CONSOLIDATED",
        row.get("concept_id"),
        row.get("period_type"),
        str(row.get("period_end") or ""),
        row.get("basis"),
        dimensions,
    )


def _year(row: dict[str, Any]) -> int | None:
    if row.get("fiscal_year") is not None:
        try:
            return int(row["fiscal_year"])
        except (TypeError, ValueError):
            return None
    end = str(row.get("period_end") or "")
    if len(end) >= 4 and end[:4].isdigit():
        return int(end[:4])
    return None


def _after(deal_id: str, action: str, fact_id: str) -> dict[str, Any]:
    refreshed = _refresh(deal_id)
    published = _republish(deal_id)
    return {
        "action": action,
        "fact_id": fact_id,
        "status": (get_fact(fact_id) or {}).get("status"),
        "flags": refreshed.get("flags") or [],
        "published": published,
    }


def _refresh(deal_id: str) -> dict[str, Any]:
    from agetic_cdd_api.services_rule_checker import check_rules

    facts = []
    for row in facts_for(deal_id):
        facts.append(
            SimpleNamespace(
                concept_id=row.get("concept_id"),
                value=row.get("value"),
                unit_type=row.get("unit_type"),
                period_type=row.get("period_type"),
                period_end=row.get("period_end"),
                period_start=row.get("period_start"),
                months_covered=row.get("months_covered"),
                basis=row.get("basis"),
                dimensions=dict(row.get("dimensions") or {}),
                status=row.get("status"),
                reason_code=row.get("reason_code"),
                mapping=dict(row.get("mapping") or {}),
                fact_id=row.get("fact_id"),
                currency=row.get("currency"),
            )
        )
    try:
        return check_rules(facts, deal_id)
    except Exception:
        return {"flags": [], "publish_set": [], "blocked_tabs": []}


def _republish(deal_id: str) -> bool:
    try:
        from agetic_cdd_api.services_deal_profile import published_databook
        from agetic_cdd_api.services_publisher import publish

        if not published_databook(deal_id):
            return False
        publish(deal_id)
        return True
    except Exception:
        return False
