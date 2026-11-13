"""Run one workbook through the databook and write the regression report.

The reference pipeline test reads example_run.json. This runner builds that
file from the statement reader, the period engine, and the rule checker, and
loads the chosen facts when a databook URL is set.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_fact_repository import check_fact_contract
from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_publisher import tab_completeness
from agetic_cdd_api.services_period_engine import compare_with_source, derive_periods, run_calculations
from agetic_cdd_api.services_rule_checker import (
    cash_tie,
    check_rules,
    debt_tie,
    ebitda_bridge,
    run_identities,
    schedule_vs_book,
)
from agetic_cdd_api.services_statement_reader import read_statement_grid

_RULES = [
    "R-PL-02", "R-PL-03", "R-PL-05", "R-PL-06", "R-PL-07", "R-PL-08",
    "R-BS-01", "R-BS-02", "R-BS-03", "R-BS-04", "R-BS-05",
    "R-CF-01", "R-CF-02", "R-CF-03", "R-CF-05", "R-CF-06",
]
_POLICY = {"include_other_operating_income": False, "rent_basis": "GAAP", "bad_debt_in_ebitda": True}


def run_case(
    workbook: str,
    *,
    deal_id: str,
    currency: str,
    fye: str,
    out_dir: str,
    latest_actual: str = "",
    database_url: str = "",
) -> dict[str, Any]:
    """Read a workbook, write example_run.json, and publish when a URL is set.

    latest_actual, when set, dates the profile and the period derivation.
    When it is empty, the latest selected monthly period in the workbook is used.
    A databook load deletes rows for this deal_id only.
    """
    onto = load_ontology()
    doc_id = _doc_id(deal_id)
    read = _read(workbook, onto, currency, int(fye[:2]), doc_id)
    example = _example(read, onto, currency, fye, deal_id=deal_id, latest_actual=latest_actual)
    if database_url:
        _load(
            database_url,
            read,
            deal_id=deal_id,
            doc_id=doc_id,
            currency=currency,
            fye=fye,
            latest=example["profile"]["latest_actual_month"],
            file_name=Path(workbook).name,
        )
    checked = check_rules(read["stored"], deal_id)
    example["publish_set"] = checked["publish_set"]
    example["blocked_tabs"] = checked["blocked_tabs"]
    example["completeness"] = tab_completeness(
        _tabs(read["stored"], read["locs"], set(checked["blocked_tabs"]), onto),
        onto,
    )
    example["agent_chosen"] = _agent_chosen(read["stored"], read["locs"])
    if database_url:
        from agetic_cdd_api.services_publisher import publish

        published = publish(deal_id)
        example["completeness"] = published["completeness"]
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "example_run.json").write_text(json.dumps(example, indent=1, default=str))
    return example


def published_pages(
    workbook: str,
    *,
    deal_id: str,
    currency: str,
    fye: str,
    latest_actual: str = "",
) -> list[dict[str, Any]]:
    """Schedule pages for a workbook. This does not change the example file."""
    onto = load_ontology()
    read = _read(workbook, onto, currency, int(fye[:2]), _doc_id(deal_id))
    _example(read, onto, currency, fye, deal_id=deal_id, latest_actual=latest_actual)
    checked = check_rules(read["stored"], deal_id)
    return _published_pages(read, set(checked["blocked_tabs"]), onto)


def _doc_id(deal_id: str) -> str:
    return "d-" + deal_id


def _read(workbook: str, onto, currency: str, fye_month: int, doc_id: str) -> dict[str, Any]:
    import openpyxl

    values = openpyxl.load_workbook(workbook, data_only=True)
    formulas = openpyxl.load_workbook(workbook, data_only=False)
    facts: list[Any] = []
    checks: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    items: dict[tuple, dict] = {}
    found: dict[str, dict[str, Any]] = {}
    locs: dict[str, Any] = {}
    try:
        for sheet in values.worksheets:
            statement, sheet_facts, log, sheet_checks, sheet_items = read_statement_grid(
                sheet, formulas[sheet.title], doc_id, onto, currency, None, locs, fye_month=fye_month,
            )
            if not statement:
                continue
            found[statement] = {"facts": len(sheet_facts), "rows": len(log)}
            facts.extend(sheet_facts)
            checks.extend(sheet_checks)
            logs.extend(log)
            items.update({(statement, item["rn"]): item for item in sheet_items})
    finally:
        values.close()
        formulas.close()
    return {"facts": facts, "checks": checks, "logs": logs, "items": items, "found": found, "locs": locs}


def _example(
    read: dict[str, Any],
    onto,
    currency: str,
    fye: str,
    *,
    deal_id: str,
    latest_actual: str,
) -> dict[str, Any]:
    facts = list(read["facts"])
    latest = _latest(facts, latest_actual)
    facts += run_calculations(facts, onto, _POLICY, {"FM", "AS_AT"})
    facts += derive_periods(facts, onto, latest, int(fye[:2]))
    facts += run_calculations(facts, onto, _POLICY, {"FY", "YTD", "LTM"})
    rules = run_identities(facts, onto, [rule for rule in _RULES if rule in onto.rules])
    contract = Counter(err for fact in facts for err in check_fact_contract(fact))
    read["stored"] = facts
    return {
        "profile": {
            "deal_id": deal_id,
            "reporting_currency": currency,
            "fiscal_year_end": fye,
            "latest_actual_month": latest.isoformat(),
        },
        "statements": read["found"],
        "source_subtotal_checks": read["checks"],
        "derived_vs_source": _derived(facts, read),
        "rules": rules,
        "ebitda_bridge": ebitda_bridge(facts, onto),
        "cash_tie": cash_tie(rules),
        "debt_tie": debt_tie(facts),
        "schedule_vs_book": schedule_vs_book(facts),
        "contract": dict(contract),
        "review_queue": [row for row in read["logs"] if row.get("concept_id") and (row.get("confidence", 1) < 0.7 or row.get("alternative"))],
        "review_queue_ratio": _queue_ratio(read["logs"]),
        "unmapped": [row for row in read["logs"] if not row.get("concept_id") and row.get("row_kind") in ("LINE", "SUM", "ARITH", "RATIO")],
    }


def _queue_ratio(logs: list[dict[str, Any]]) -> float:
    lines = [row for row in logs if row.get("row_kind") == "LINE"]
    if not lines:
        return 0.0
    queued = [
        row for row in lines
        if row.get("concept_id") and (float(row.get("confidence") or 1) < 0.7 or row.get("alternative"))
    ]
    return round(len(queued) / len(lines), 4)


def _published_pages(read: dict[str, Any], blocked: set[str], onto) -> list[dict[str, Any]]:
    """Schedule pages for this run. The example file stays the reference shape."""
    from agetic_cdd_api.services_published_pages import pages_from_tabs

    return pages_from_tabs(_figure_tabs(read["stored"], read["locs"], blocked, onto))


def _figure_tabs(facts, locs: dict[str, Any], blocked: set[str], onto) -> dict[str, list]:
    tabs: dict[str, list] = {}
    for fact in facts:
        if fact.status not in ("SELECTED", "DERIVED") or not fact.fact_id:
            continue
        cell_range = next(
            (locs[item].cell_range for item in fact.source_location_ids if item in locs and locs[item].cell_range),
            "",
        )
        if not cell_range or fact.value is None:
            continue
        cell = {
            "fact_id": fact.fact_id,
            "concept_id": fact.concept_id,
            "value": float(fact.value),
            "period_end": str(fact.period_end or ""),
            "cell_range": cell_range,
            "dimensions": dict(fact.dimensions or {}),
        }
        for schedule in onto.concepts.get(fact.concept_id, {}).get("schedules") or []:
            if schedule in blocked or schedule == "GOV-05":
                continue
            tabs.setdefault(schedule, []).append(cell)
    return tabs


def _tabs(facts, locs: dict[str, Any], blocked: set[str], onto) -> dict[str, list]:
    tabs: dict[str, list] = {}
    for fact in facts:
        if fact.status not in ("SELECTED", "DERIVED") or not fact.fact_id:
            continue
        cell_range = next(
            (locs[item].cell_range for item in fact.source_location_ids if item in locs and locs[item].cell_range),
            "",
        )
        if not cell_range:
            continue
        cell = {"fact_id": fact.fact_id, "concept_id": fact.concept_id, "cell_range": cell_range}
        for schedule in onto.concepts.get(fact.concept_id, {}).get("schedules") or []:
            if schedule in blocked or schedule == "GOV-05":
                continue
            tabs.setdefault(schedule, []).append(cell)
    tabs.setdefault("GOV-05", [])
    return tabs


def _agent_chosen(facts, locs: dict[str, Any]) -> list[str]:
    """Chosen facts whose source cell was read by an agent, or whose document is agent output."""
    chosen = []
    for fact in facts:
        if fact.status not in ("SELECTED", "DERIVED"):
            continue
        for item in fact.source_location_ids or []:
            loc = locs.get(item)
            method = str(getattr(loc, "extraction_method", "") or "").upper()
            if method.startswith("AGENT"):
                chosen.append(fact.fact_id)
                break
    return chosen


def _derived(facts, read: dict[str, Any]) -> list[dict[str, Any]]:
    statement_of = {}
    for fact in facts:
        mapping = fact.mapping or {}
        if fact.status == "COMPARATIVE" and mapping.get("row") is not None:
            statement_of[fact.fact_id] = _statement(fact.concept_id)
    compared = []
    chosen = [fact for fact in facts if fact.status in ("DERIVED", "SELECTED")]
    for statement in read["found"]:
        rows = {number: item for (name, number), item in read["items"].items() if name == statement}
        subset = [fact for fact in facts if statement_of.get(fact.fact_id) == statement]
        if subset:
            compared.extend(compare_with_source(subset + chosen, rows))
    groups: dict[tuple, dict[str, int]] = defaultdict(lambda: {"failed": 0})
    for row in compared:
        if not row.get("concept"):
            continue
        bucket = groups[(row["rule"], row["concept"], json.dumps(row["dims"]), row["period_type"])]
        if row.get("passed") is False and not row.get("explained_by"):
            bucket["failed"] += 1
    return [{"failed": bucket["failed"]} for bucket in groups.values()]


def _statement(concept: str) -> str:
    if concept.startswith(("fin.pl.", "drv.")):
        return "PL"
    if concept.startswith("fin.bs."):
        return "BS"
    return "CF"


def _latest(facts, latest_actual: str) -> dt.date:
    chosen = (latest_actual or "").strip()
    if not chosen:
        monthly = [
            fact.period_end
            for fact in facts
            if fact.period_type == "FM" and fact.status == "SELECTED" and fact.period_end
        ]
        if not monthly:
            raise ValueError("no monthly actual to date the case")
        chosen = max(monthly)
    return dt.date.fromisoformat(str(chosen)[:10])


def _load(
    database_url: str,
    read: dict[str, Any],
    *,
    deal_id: str,
    doc_id: str,
    currency: str,
    fye: str,
    latest: str,
    file_name: str,
) -> None:
    import os
    import subprocess
    import tempfile

    from agetic_cdd_api.services_databook_migrate import psql
    from agetic_cdd_api.services_ontology import insert_deal

    psql(database_url, _clear(deal_id))
    insert_deal(database_url, {
        "deal_id": deal_id,
        "reporting_currency": currency,
        "fiscal_year_end": fye,
        "latest_actual_month": latest,
    })
    chosen = _chosen(read.get("stored") or read["facts"])
    version = load_ontology().version
    script = _document(version, deal_id, doc_id, file_name) + "".join(
        _location(loc) for loc in _locations(chosen, read["locs"])
    )
    script += "".join(_fact(fact, version, deal_id) for fact in chosen)
    handle, name = tempfile.mkstemp(suffix=".sql")
    os.close(handle)
    Path(name).write_text(script)
    result = subprocess.run(
        ["psql", database_url, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-f", name],
        check=False, capture_output=True, text=True,
    )
    Path(name).unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "databook case load failed")


def _clear(deal_id: str) -> str:
    quoted = _q(deal_id)
    return (
        f"DELETE FROM record WHERE deal_id = {quoted}; "
        f"DELETE FROM flag WHERE deal_id = {quoted}; "
        f"DELETE FROM reconciliation WHERE deal_id = {quoted}; "
        f"DELETE FROM mapping_decision WHERE deal_id = {quoted}; "
        f"DELETE FROM source_location WHERE doc_id IN (SELECT doc_id FROM document WHERE deal_id = {quoted}); "
        f"DELETE FROM fact WHERE deal_id = {quoted}; "
        f"DELETE FROM document WHERE deal_id = {quoted}; "
        f"DELETE FROM deal WHERE deal_id = {quoted};"
    )


def _chosen(facts) -> list[Any]:
    seen: set[tuple] = set()
    chosen = []
    for fact in facts:
        if fact.status not in ("SELECTED", "DERIVED") or fact.value is None:
            continue
        key = fact.key()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(fact)
    return chosen


def _locations(facts, locs: dict[str, Any]) -> list[Any]:
    wanted = {location_id for fact in facts for location_id in fact.source_location_ids}
    return [locs[location_id] for location_id in wanted if location_id in locs]


def _document(version: str, deal_id: str, doc_id: str, file_name: str) -> str:
    return (
        "INSERT INTO document (doc_id, deal_id, ontology_version, file_name, format, doc_type, status, evidence_tier) "
        f"VALUES ({_q(doc_id)}, {_q(deal_id)}, {_q(version)}, {_q(file_name)}, 'xlsx', 'FIN_MGMT_ACCOUNTS', 'READ', 'B');"
    )


def _location(loc) -> str:
    return (
        "INSERT INTO source_location (location_id, doc_id, sheet_or_page, cell_range, row_label_as_read, column_label_as_read, value_as_read, extraction_method, transform_steps) "
        f"VALUES ({_q(loc.location_id)}, {_q(loc.doc_id)}, {_q(loc.sheet_or_page)}, {_q(loc.cell_range)}, {_q(loc.row_label_as_read)}, "
        f"{_q(loc.column_label_as_read)}, {_q(loc.value_as_read)}, {_q(loc.extraction_method)}, ARRAY[]::text[]);"
    )


def _fact(fact, version: str, deal_id: str) -> str:
    start = _date(fact.period_start)
    end = _date(fact.period_end)
    derived = _array(fact.derived_from)
    sources = _array(fact.source_location_ids)
    return (
        "INSERT INTO fact (fact_id, deal_id, entity_id, ontology_version, concept_id, value, unit_type, currency, "
        "period_type, period_start, period_end, months_covered, basis, dimensions, status, evidence_tier, source_location_ids, derived_from, formula) "
        f"VALUES ({_q(fact.fact_id)}, {_q(deal_id)}, {_q(fact.entity_id)}, {_q(version)}, {_q(fact.concept_id)}, {fact.value}, "
        f"{_q(fact.unit_type)}, {_q(fact.currency) if fact.currency else 'NULL'}, {_q(fact.period_type)}, {start}, {end}, "
        f"{fact.months_covered if fact.months_covered is not None else 'NULL'}, {_q(fact.basis)}, {_q(json.dumps(fact.dimensions or {}))}::jsonb, "
        f"{_q(fact.status)}, {_q(fact.evidence_tier)}, {sources}, {derived}, {_q(fact.formula) if fact.formula else 'NULL'});"
    )


def _date(value) -> str:
    if not value:
        return "NULL"
    return f"DATE {_q(str(value)[:10])}"


def _array(values) -> str:
    if not values:
        return "ARRAY[]::text[]"
    return "ARRAY[" + ",".join(_q(item) for item in values) + "]::text[]"


def _q(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
