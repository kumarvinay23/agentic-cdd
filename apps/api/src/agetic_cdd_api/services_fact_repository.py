"""The only writer of the databook fact table.

A row is checked with the reference contract and the databook schema
before it is stored. Other services ask this module for a fact id.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agetic_cdd_api.services_ontology import stamp
from agetic_cdd_api.settings import settings

_SCHEMA_PATH = Path(__file__).resolve().parent / "databook_sql" / "DiligenceIQ_Databook_Data_Model_v1.schema.json"
_FACT_SCHEMA = json.loads(_SCHEMA_PATH.read_text())["$defs"]["fact"]
_MEMORY: dict[str, dict[str, Any]] = {}
_SEQUENCE = 0

dkey = lambda d: tuple(sorted(d.items()))


@dataclass
class Fact:
    concept_id: str; value: Optional[float]; unit_type: str; period_type: str; period_start: Optional[str]; period_end: Optional[str]
    months_covered: Optional[int]; basis: str; dimensions: dict; doc_id: Optional[str]; evidence_tier: str
    source_location_ids: list; status: str = "CANDIDATE"; currency: Optional[str] = None; scale_applied: int = 1
    reason_code: Optional[str] = None; reason_detail: Optional[str] = None; derived_from: list = field(default_factory=list)
    formula: Optional[str] = None; entity_id: str = "CONSOLIDATED"; fact_id: str = field(default_factory=lambda: "f-" + uuid.uuid4().hex[:12])
    mapping: dict = field(default_factory=dict)
    def key(self): return (self.entity_id, self.concept_id, self.period_type, self.period_end, self.basis, dkey(self.dimensions))


def check_fact_contract(f):
    errs = []
    if f.period_type == "FY" and f.months_covered != 12: errs.append("R-PER-02: FY with months_covered != 12")
    if f.period_type == "YTD" and not (f.months_covered and 1 <= f.months_covered <= 11): errs.append("YTD months_covered out of range")
    if f.unit_type == "CURRENCY" and not f.currency and f.value is not None: errs.append("currency missing")
    if f.status in ("HELD", "REJECTED", "COMPARATIVE") and not f.reason_code: errs.append("reason_code missing")
    if not f.source_location_ids and not f.derived_from: errs.append("lineage missing")
    return errs


def release_document(deal_id: str, doc_id: str) -> None:
    """Drop stored figures that came from one document so that file can be reread."""
    stale = [
        fact_id
        for fact_id, row in _MEMORY.items()
        if str(row.get("deal_id")) == deal_id and str(row.get("doc_id") or "") == doc_id
    ]
    for fact_id in stale:
        _MEMORY.pop(fact_id, None)
    url = settings.databook_database_url.strip()
    if not url or not deal_id or not doc_id:
        return
    from agetic_cdd_api.services_databook_migrate import psql

    quoted_deal = "'" + deal_id.replace("'", "''") + "'"
    quoted_doc = "'" + doc_id.replace("'", "''") + "'"
    result = psql(
        url,
        f"DELETE FROM fact WHERE deal_id = {quoted_deal} AND doc_id = {quoted_doc}; "
        f"DELETE FROM source_location WHERE doc_id = {quoted_doc};",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "document fact release failed")


def release_deal(deal_id: str) -> None:
    """Drop stored figures for one deal so a fresh room read can replace them."""
    stale = [fact_id for fact_id, row in _MEMORY.items() if str(row.get("deal_id")) == deal_id]
    for fact_id in stale:
        _MEMORY.pop(fact_id, None)
    url = settings.databook_database_url.strip()
    if not url or not deal_id:
        return
    from agetic_cdd_api.services_databook_migrate import psql

    quoted = "'" + deal_id.replace("'", "''") + "'"
    result = psql(
        url,
        f"DELETE FROM reconciliation WHERE deal_id = {quoted}; "
        f"DELETE FROM flag WHERE deal_id = {quoted}; "
        f"DELETE FROM record WHERE deal_id = {quoted}; "
        f"DELETE FROM mapping_decision WHERE deal_id = {quoted}; "
        f"DELETE FROM source_location WHERE doc_id IN (SELECT doc_id FROM document WHERE deal_id = {quoted}); "
        f"DELETE FROM fact WHERE deal_id = {quoted};",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "fact release failed")


def save_fact(row: dict[str, Any]) -> str:
    """Validate, stamp the ontology version, and store one fact."""
    prepared = _prepare(row)
    errors = check_fact_contract(_as_fact(prepared)) + schema_errors(prepared)
    if errors:
        raise ValueError("; ".join(errors))
    _reject_duplicate(prepared)
    _persist(prepared)
    _MEMORY[prepared["fact_id"]] = prepared
    return prepared["fact_id"]


def update_fact(fact_id: str, changes: dict[str, Any]) -> str:
    """Replace fields on a stored fact and check the contract again."""
    current = get_fact(fact_id)
    if current is None:
        raise ValueError(f"unknown fact {fact_id}")
    merged = dict(current)
    merged.update(changes)
    merged["fact_id"] = fact_id
    prepared = _prepare(merged)
    prepared["fact_id"] = fact_id
    errors = check_fact_contract(_as_fact(prepared)) + schema_errors(prepared)
    if errors:
        raise ValueError("; ".join(errors))
    _reject_duplicate(prepared)
    _persist(prepared, updating=True)
    _MEMORY[fact_id] = prepared
    return fact_id


def facts_for(deal_id: str) -> list[dict[str, Any]]:
    """Facts stored for one deal."""
    return [dict(row) for row in _MEMORY.values() if row.get("deal_id") == deal_id]


def get_fact(fact_id: str) -> dict[str, Any] | None:
    row = _MEMORY.get(fact_id)
    return dict(row) if row else None


def hold_number(*, name: str, value: Any, source: str, calc_id: str | None = None) -> str:
    """Keep an agent number in the repository when it is not an ontology fact."""
    fact_id = _next_id()
    _MEMORY[fact_id] = {"fact_id": fact_id, "name": name, "value": value, "source": source, "calc_id": calc_id}
    return fact_id


def record_selection(chosen: dict[str, Any], conflicts: list[dict[str, Any]]) -> str:
    """Store the authority choice and the sources that disagreed."""
    fact_id = _next_id()
    _MEMORY[fact_id] = {
        "fact_id": fact_id,
        "value": chosen.get("value"),
        "status": "SELECTED",
        "doc_type": chosen.get("doc_type"),
        "conflicts": list(conflicts),
    }
    return fact_id


def cited_facts(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Facts named by id in a rendered report."""
    found: list[dict[str, Any]] = []
    for fact_id in _fact_ids(report):
        row = get_fact(fact_id)
        if row and row.get("value") is not None:
            found.append(row)
    return found


def schema_errors(row: dict[str, Any]) -> list[str]:
    """Why this row does not match the fact schema."""
    errors: list[str] = []
    for name in _FACT_SCHEMA["required"]:
        if name not in row:
            errors.append(f"schema missing {name}")
    properties = _FACT_SCHEMA["properties"]
    for name, value in row.items():
        spec = properties.get(name)
        if spec is None or _fits(value, spec):
            continue
        errors.append(f"schema {name} is invalid")
    return errors


def _reject_duplicate(row: dict[str, Any]) -> None:
    if row.get("status") not in {"SELECTED", "DERIVED"}:
        return
    figure = _figure(row)
    for existing in _MEMORY.values():
        if existing.get("fact_id") == row.get("fact_id"):
            continue
        if existing.get("status") in {"SELECTED", "DERIVED"} and _figure(existing) == figure:
            raise ValueError("fact_key_selected")


def _figure(row: dict[str, Any]) -> tuple[Any, ...]:
    dimensions = tuple(sorted((str(key), str(value)) for key, value in (row.get("dimensions") or {}).items()))
    return (
        row.get("deal_id"),
        row.get("entity_id"),
        row.get("concept_id"),
        row.get("period_type"),
        row.get("period_end"),
        row.get("basis"),
        dimensions,
    )


def _prepare(row: dict[str, Any]) -> dict[str, Any]:
    prepared = stamp(dict(row))
    prepared.setdefault("fact_id", _next_id())
    prepared.setdefault("entity_id", "CONSOLIDATED")
    prepared.setdefault("dimensions", {})
    prepared.setdefault("status", "CANDIDATE")
    prepared.setdefault("evidence_tier", "B")
    prepared.setdefault("basis", "ACTUAL")
    prepared.setdefault("source_location_ids", [])
    prepared.setdefault("derived_from", [])
    prepared.setdefault("mapping", dict(row.get("mapping") or {}))
    if str(prepared.get("unit_type") or "") == "CURRENCY" and not prepared.get("currency"):
        from agetic_cdd_api.services_deal_profile import reporting_currency_for

        code = reporting_currency_for(str(prepared.get("deal_id") or ""))
        if code:
            prepared["currency"] = code
            mapping = dict(prepared.get("mapping") or {})
            if not mapping.get("currency_source"):
                mapping["currency_source"] = "assumed"
                mapping.setdefault("scale_source", "assumed")
            prepared["mapping"] = mapping
    return prepared


def _as_fact(row: dict[str, Any]) -> Fact:
    return Fact(
        concept_id=str(row.get("concept_id") or ""),
        value=None if row.get("value") is None else float(row["value"]),
        unit_type=str(row.get("unit_type") or ""),
        period_type=str(row.get("period_type") or ""),
        period_start=row.get("period_start"),
        period_end=row.get("period_end"),
        months_covered=row.get("months_covered"),
        basis=str(row.get("basis") or ""),
        dimensions=dict(row.get("dimensions") or {}),
        doc_id=row.get("doc_id"),
        evidence_tier=str(row.get("evidence_tier") or ""),
        source_location_ids=list(row.get("source_location_ids") or []),
        status=str(row.get("status") or "CANDIDATE"),
        currency=row.get("currency"),
        scale_applied=int(row["scale_applied"]) if row.get("scale_applied") else 1,
        reason_code=row.get("reason_code"),
        reason_detail=row.get("reason_detail"),
        derived_from=list(row.get("derived_from") or []),
        formula=row.get("formula"),
        entity_id=str(row.get("entity_id") or "CONSOLIDATED"),
        fact_id=str(row.get("fact_id") or ""),
    )


def _fits(value: Any, spec: dict[str, Any]) -> bool:
    allowed = spec.get("type")
    kinds = [allowed] if isinstance(allowed, str) else list(allowed or [])
    if value is None:
        return "null" in kinds or not kinds
    if "enum" in spec and value not in spec["enum"]:
        return False
    if "number" in kinds and isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if "integer" in kinds and isinstance(value, int) and not isinstance(value, bool):
        low, high = spec.get("minimum"), spec.get("maximum")
        return (low is None or value >= low) and (high is None or value <= high)
    if "string" in kinds and isinstance(value, str):
        pattern = spec.get("pattern")
        return pattern is None or re.fullmatch(pattern, value) is not None
    if "object" in kinds and isinstance(value, dict):
        return _object_fits(value, spec)
    if "array" in kinds and isinstance(value, list):
        item = spec.get("items") or {}
        return all(_fits(entry, item) for entry in value)
    return not kinds


def _object_fits(value: dict[str, Any], spec: dict[str, Any]) -> bool:
    extra = spec.get("additionalProperties")
    if not isinstance(extra, dict):
        return True
    return all(_fits(item, extra) for item in value.values())


def _persist(row: dict[str, Any], *, updating: bool = False) -> None:
    url = settings.databook_database_url.strip()
    if not url or not _deal_exists(url, str(row["deal_id"])):
        return
    sql = _update_sql(row) if updating else _insert_sql(row)
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(url, sql)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "fact write failed")


def _deal_exists(url: str, deal_id: str) -> bool:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(url, f"SELECT deal_id FROM deal WHERE deal_id = {_text(deal_id)}")
    return result.returncode == 0 and deal_id in result.stdout


def _insert_sql(row: dict[str, Any]) -> str:
    mapping = json.dumps(row.get("mapping") or {})
    return (
        "INSERT INTO fact ("
        "fact_id, deal_id, entity_id, ontology_version, concept_id, value, unit_type, currency,"
        " scale_applied, period_type, period_start, period_end, months_covered, fiscal_year, basis, dimensions,"
        " status, reason_code, reason_detail, evidence_tier, source_location_ids, derived_from, formula, mapping"
        ") VALUES ("
        f"{_text(row['fact_id'])}, {_text(row['deal_id'])}, {_text(row['entity_id'])}, {_text(row['ontology_version'])}, "
        f"{_text(row['concept_id'])}, {_number(row.get('value'))}, {_text(row['unit_type'])}, {_nullable_text(row.get('currency'))}, "
        f"{_number(row.get('scale_applied') or 1)}, "
        f"{_text(row['period_type'])}, {_date(row.get('period_start'))}, {_date(row.get('period_end'))}, "
        f"{_number(row.get('months_covered'))}, {_number(row.get('fiscal_year'))}, {_text(row['basis'])}, "
        f"{_text(json.dumps(row.get('dimensions') or {}))}::jsonb, {_text(row['status'])}, "
        f"{_nullable_text(row.get('reason_code'))}, {_nullable_text(row.get('reason_detail'))}, "
        f"{_text(row['evidence_tier'])}, "
        f"{_array(row.get('source_location_ids') or [])}, {_array(row.get('derived_from') or [])}, "
        f"{_nullable_text(row.get('formula'))}, {_text(mapping)}::jsonb);"
    )


def _update_sql(row: dict[str, Any]) -> str:
    mapping = json.dumps(row.get("mapping") or {})
    return (
        "UPDATE fact SET "
        f"concept_id = {_text(row['concept_id'])}, "
        f"value = {_number(row.get('value'))}, status = {_text(row['status'])}, "
        f"currency = {_nullable_text(row.get('currency'))}, "
        f"reason_code = {_nullable_text(row.get('reason_code'))}, "
        f"reason_detail = {_nullable_text(row.get('reason_detail'))}, "
        f"mapping = {_text(mapping)}::jsonb, "
        f"reviewed_by = {_nullable_text(row.get('reviewed_by'))}, "
        f"ontology_version = {_text(row['ontology_version'])} "
        f"WHERE fact_id = {_text(row['fact_id'])};"
    )


def _fact_ids(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "fact_id" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_fact_ids(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_fact_ids(item))
    return found


def _next_id() -> str:
    global _SEQUENCE
    _SEQUENCE += 1
    fact_id = f"fact-{_SEQUENCE}"
    while fact_id in _MEMORY:
        _SEQUENCE += 1
        fact_id = f"fact-{_SEQUENCE}"
    return fact_id


def _array(values: list[Any]) -> str:
    if not values:
        return "ARRAY[]::text[]"
    return "ARRAY[" + ", ".join(_text(item) for item in values) + "]::text[]"


def _date(value: Any) -> str:
    if not value:
        return "NULL"
    return "DATE " + _text(value)


def _number(value: Any) -> str:
    if value is None:
        return "NULL"
    return str(float(value) if not isinstance(value, int) else int(value))


def _nullable_text(value: Any) -> str:
    if value is None:
        return "NULL"
    return _text(value)


def _text(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
