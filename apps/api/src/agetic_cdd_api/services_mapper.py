"""Save the statement reader's mapping choices.

The concept, the section class, and the class twin come from `read_statement_grid`.
A line with confidence under 0.7, or a line whose section changed the concept, is a
guess and stays on the review queue. A line with no concept stays on that queue too.
"""

from __future__ import annotations

import json
from typing import Any

from agetic_cdd_api.services_ontology import stamp

_KINDS = {"LINE", "SUM", "ARITH", "RATIO"}
_GUESS_BELOW = 0.7
_SAVED: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}


def record_mappings(log: list[dict[str, Any]], deal_id: str, doc_id: str) -> dict[str, list[dict[str, Any]]]:
    """Store one mapping decision per matched line, and queue every guess."""
    decisions = [stamp(_decision(entry, deal_id, doc_id)) for entry in log if _matched(entry)]
    queue = [_review_row(entry, deal_id, doc_id) for entry in log if _queued(entry)]
    result = {"decisions": decisions, "review_queue": queue}
    _SAVED[(deal_id, doc_id)] = result
    _persist(deal_id, doc_id, decisions)
    return result


def mappings_for(deal_id: str) -> dict[str, list[dict[str, Any]]]:
    """Decisions and review rows recorded for a deal."""
    decisions: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    for (saved_deal, _doc), result in _SAVED.items():
        if saved_deal != deal_id:
            continue
        decisions.extend(result["decisions"])
        queue.extend(result["review_queue"])
    return {"decisions": decisions, "review_queue": queue}


def _matched(entry: dict[str, Any]) -> bool:
    return entry.get("row_kind") in _KINDS and bool(entry.get("concept_id")) and bool(entry.get("method"))


def _queued(entry: dict[str, Any]) -> bool:
    if entry.get("row_kind") not in _KINDS:
        return False
    if not entry.get("concept_id"):
        return True
    return _guess(entry)


def _guess(entry: dict[str, Any]) -> bool:
    confidence = float(entry.get("confidence") or 0)
    return confidence < _GUESS_BELOW or bool(entry.get("alternative"))


def _decision(entry: dict[str, Any], deal_id: str, doc_id: str) -> dict[str, Any]:
    row = _review_row(entry, deal_id, doc_id)
    row["validated_by_rules"] = []
    row["reviewer"] = None
    return row


def _review_row(entry: dict[str, Any], deal_id: str, doc_id: str) -> dict[str, Any]:
    return {
        "deal_id": deal_id,
        "doc_id": doc_id,
        "label_as_read": entry.get("label_as_read") or "",
        "label_path": list(entry.get("label_path") or []),
        "concept_id": entry.get("concept_id"),
        "dimensions": dict(entry.get("dimensions") or {}),
        "method": entry.get("method"),
        "confidence": entry.get("confidence"),
        "alternative": entry.get("alternative"),
        "row_kind": entry.get("row_kind"),
        "sheet": entry.get("sheet"),
        "row": entry.get("row"),
    }


def _persist(deal_id: str, doc_id: str, decisions: list[dict[str, Any]]) -> None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not str(doc_id or "").strip() or not _document_exists(url, deal_id, doc_id):
        return
    from agetic_cdd_api.services_databook_migrate import psql

    script = f"DELETE FROM mapping_decision WHERE deal_id = {_sql(deal_id)} AND doc_id = {_sql(doc_id)}; "
    script += " ".join(_insert(row) for row in decisions)
    result = psql(url, script)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "mapping decision write failed")


def _document_exists(url: str, deal_id: str, doc_id: str) -> bool:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT doc_id FROM document WHERE "
        f"deal_id = {_sql(deal_id)} AND doc_id = {_sql(doc_id)}",
    )
    return result.returncode == 0 and doc_id in result.stdout


def _insert(row: dict[str, Any]) -> str:
    path = "ARRAY[]::text[]" if not row["label_path"] else "ARRAY[" + ", ".join(_sql(item) for item in row["label_path"]) + "]::text[]"
    confidence = "NULL" if row.get("confidence") is None else str(float(row["confidence"]))
    return (
        "INSERT INTO mapping_decision ("
        "deal_id, doc_id, ontology_version, label_as_read, label_path, concept_id, dimensions, method, confidence"
        ") VALUES ("
        f"{_sql(row['deal_id'])}, {_sql(row['doc_id'])}, {_sql(row['ontology_version'])}, {_sql(row['label_as_read'])}, "
        f"{path}, {_sql(row['concept_id'])}, {_sql(json.dumps(row['dimensions']))}::jsonb, {_sql(row['method'])}, {confidence});"
    )


def _sql(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
