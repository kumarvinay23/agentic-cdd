"""Publish schedule tabs from the databook view.

A cell is written only when it carries a fact id and a source cell. A required
concept with no such cell is a GOV-05 gap. The file-backed databook is left
in place.
"""

from __future__ import annotations

import json
from typing import Any

from agetic_cdd_api.services_ontology import load_ontology, stamp
from agetic_cdd_api.services_rule_checker import open_flags

_GAP = "GOV-05"


def publish(deal_id: str) -> dict[str, Any]:
    """Build one tab per schedule that has a sourced fact. Record the gaps."""
    onto = load_ontology()
    blocked = _blocked(deal_id)
    tabs: dict[str, list[dict[str, Any]]] = {}
    covered: set[tuple[str, str]] = set()
    for row in _view_rows(deal_id):
        cell = _cell(row)
        if not _sourced(cell):
            continue
        for schedule in _schedules(row):
            if schedule in blocked or schedule == _GAP:
                continue
            write_cell(cell)
            tabs.setdefault(schedule, []).append(cell)
            covered.add((schedule, str(row.get("concept_id") or "")))
    gaps = _gaps(deal_id, onto, tabs, covered)
    _store_gaps(deal_id, gaps)
    tabs[_GAP] = gaps
    return {"tabs": tabs, "gaps": gaps, "completeness": tab_completeness(tabs, onto)}


def tab_completeness(tabs: dict[str, list], onto) -> dict[str, float]:
    """Sourced required concepts over required concepts. An empty requirement scores 1."""
    by_id = {schedule["id"]: schedule for schedule in onto.b.get("schedules") or [] if schedule.get("id")}
    scores: dict[str, float] = {}
    for schedule_id, cells in tabs.items():
        required = [concept for concept in (by_id.get(schedule_id) or {}).get("required_concepts") or [] if concept]
        if schedule_id == _GAP or not required:
            scores[schedule_id] = 1.0
            continue
        sourced = {str(cell.get("concept_id") or "") for cell in cells if _sourced(cell)}
        scores[schedule_id] = round(len([concept for concept in required if concept in sourced]) / len(required), 4)
    scores.setdefault(_GAP, 1.0)
    return scores


def write_cell(cell: dict[str, Any]) -> dict[str, Any]:
    """Refuse a published cell that has no fact id or no source cell."""
    if not str(cell.get("fact_id") or "").strip() or not str(cell.get("cell_range") or "").strip():
        raise ValueError("a published cell needs a fact id and a source cell")
    return cell


def _blocked(deal_id: str) -> set[str]:
    return {
        str(flag["schedule_id"])
        for flag in open_flags(deal_id)
        if flag.get("severity") == "block" and flag.get("schedule_id")
    }


def _sourced(cell: dict[str, Any]) -> bool:
    return bool(str(cell.get("fact_id") or "").strip() and str(cell.get("cell_range") or "").strip())


def _cell(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_id": row.get("fact_id"),
        "concept_id": row.get("concept_id"),
        "value": row.get("value"),
        "period_type": row.get("period_type"),
        "period_end": row.get("period_end"),
        "cell_range": row.get("cell_range"),
        "sheet_or_page": row.get("sheet_or_page"),
        "dimensions": row.get("dimensions") or {},
    }


def _schedules(row: dict[str, Any]) -> list[str]:
    schedules = row.get("schedules") or []
    if isinstance(schedules, str):
        return [item.strip() for item in schedules.strip("{}").split(",") if item.strip()]
    return [str(item) for item in schedules if item]


def _gaps(deal_id: str, onto, tabs: dict[str, list], covered: set[tuple[str, str]]) -> list[dict[str, Any]]:
    by_id = {schedule["id"]: schedule for schedule in onto.b.get("schedules") or [] if schedule.get("id")}
    gaps = []
    for schedule_id in tabs:
        schedule = by_id.get(schedule_id) or {}
        for concept in schedule.get("required_concepts") or []:
            if (schedule_id, concept) in covered:
                continue
            gaps.append(_gap(deal_id, schedule_id, concept))
    return gaps


def _gap(deal_id: str, schedule_id: str, concept: str) -> dict[str, Any]:
    return stamp({
        "record_id": f"gap-{deal_id}-{schedule_id}-{concept}",
        "record_class": "data_gap",
        "schedule_id": _GAP,
        "fields": {
            "severity": "gap",
            "rule": _GAP,
            "issue": f"{concept} is required on {schedule_id} and has no source cell",
            "affected_exhibits": [schedule_id],
            "treatment": "held",
            "request_ref": None,
        },
    })


def agent_chosen_in_view(deal_id: str) -> list[str]:
    """Selected or derived fact ids in the view whose source is an agent."""
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not str(deal_id or "").strip():
        return []
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT coalesce(json_agg(DISTINCT v.fact_id), '[]'::json)::text "
        "FROM v_databook_fact v "
        "JOIN fact f ON f.fact_id = v.fact_id "
        "LEFT JOIN source_location sl ON sl.location_id = ANY(f.source_location_ids) "
        "LEFT JOIN document d ON d.doc_id = sl.doc_id "
        f"WHERE v.deal_id = {_sql(deal_id)} "
        "AND (upper(coalesce(sl.extraction_method, '')) LIKE 'AGENT%' OR d.doc_type = 'AGENT_OUTPUT');",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "agent fact read failed")
    return [str(item) for item in _json_list(result.stdout)]


def _view_rows(deal_id: str) -> list[dict[str, Any]]:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url:
        return []
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT coalesce(json_agg(row_to_json(v)), '[]'::json)::text "
        f"FROM v_databook_fact v WHERE v.deal_id = {_sql(deal_id)};",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "databook view read failed")
    return _json_list(result.stdout)


def _store_gaps(deal_id: str, gaps: list[dict[str, Any]]) -> None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not gaps:
        return
    from agetic_cdd_api.services_databook_migrate import psql

    script = f"DELETE FROM record WHERE deal_id = {_sql(deal_id)} AND record_class = 'data_gap'; "
    script += " ".join(_insert_gap(deal_id, gap) for gap in gaps)
    result = psql(url, script)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gap write failed")


def _insert_gap(deal_id: str, gap: dict[str, Any]) -> str:
    return (
        "INSERT INTO record (record_id, deal_id, ontology_version, record_class, fields, source_location_ids, evidence_tier, status) "
        "VALUES ("
        f"{_sql(gap['record_id'])}, {_sql(deal_id)}, {_sql(gap['ontology_version'])}, 'data_gap', "
        f"{_sql(json.dumps(gap['fields']))}::jsonb, ARRAY[]::text[], 'C', 'CANDIDATE');"
    )


def _json_list(stdout: str) -> list[dict[str, Any]]:
    start, end = stdout.find("["), stdout.rfind("]")
    if start < 0 or end < start:
        return []
    payload = json.loads(stdout[start:end + 1])
    return payload if isinstance(payload, list) else []


def _sql(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
