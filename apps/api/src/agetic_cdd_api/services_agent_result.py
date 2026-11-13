"""One result per agent.

Tables, counts, charts and the verdict are fields of that result. Every
number in it is a fact id. The narrative is rendered from those facts. A
new fact is accepted by the fact store, and its checks, before it can be
cited. A table is built so its rows sum to the total, with an Other line
when the named rows do not cover the total. A count or a verdict that
contradicts its detail blocks the output.
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

RESULT_SCHEMA = "agent_result_v1"
RESULT_FIELDS = (
    "agent_key",
    "schema",
    "fact_store",
    "numbers",
    "counts",
    "details",
    "tables",
    "charts",
    "verdict",
    "narrative",
)
_LIST_FIELDS = ("cohorts", "competitors", "segments", "customers", "suppliers", "risks")
_ZERO_COHORTS = re.compile(r"\b0\s+cohorts?\b|\bno cohorts?\b", re.I)
_MONEY = Decimal("0.01")


def note_fact(
    store: dict[str, dict[str, Any]],
    *,
    name: str,
    source: str,
    value: Any = None,
    calc_id: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> str:
    """Accept a fact. A calculation is checked before the fact can be cited."""
    checked = value
    if calc_id:
        from agetic_cdd_api.services_calculation_library import ask_calculation

        computed = ask_calculation(calc_id, inputs=inputs or {})
        if value is not None and not _same(value, computed["value"]):
            raise ValueError(f"{name} does not match {calc_id}")
        checked = computed["value"]
        source = source or computed["formula"]
        fact_id = computed.get("fact_id")
    else:
        fact_id = None
    if checked is None:
        raise ValueError(f"{name} has no value")
    if not fact_id:
        from agetic_cdd_api.services_fact_repository import hold_number

        fact_id = hold_number(name=name, value=checked, source=source, calc_id=calc_id)
    store[fact_id] = {"name": name, "value": checked, "source": source, "calc_id": calc_id}
    return fact_id


def tie_table(
    lines: list[dict[str, Any]],
    total: float,
    *,
    source: str,
    store: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rows plus an Other line when one is needed. The rows then equal the total."""
    facts = store if store is not None else {}
    named = [_money_of(line.get("amount")) for line in lines]
    covered = sum(named, Decimal(0))
    target = _money_of(total)
    gap = target - covered
    rows: list[dict[str, str]] = []
    for line, amount in zip(lines, named, strict=True):
        fact_id = note_fact(facts, name=str(line.get("label") or "line"), source=source, value=_as_float(amount))
        rows.append({"label": str(line.get("label") or "line"), "amount": fact_id})
    if gap < 0:
        return {"rows": rows, "total": None, "ties": False, "gap": _as_float(gap), "fact_store": facts}
    if gap > 0:
        fact_id = note_fact(facts, name="Other", source=source, value=_as_float(gap))
        rows.append({"label": "Other", "amount": fact_id})
    total_id = note_fact(facts, name="total", source=source, value=_as_float(target))
    return {"rows": rows, "total": total_id, "ties": True, "fact_store": facts}


def build_agent_result(
    agent_key: str,
    *,
    facts: list[dict[str, Any]] | None = None,
    counts: dict[str, Any] | None = None,
    details: dict[str, list[Any]] | None = None,
    lines: list[dict[str, Any]] | None = None,
    total: float | None = None,
    charts: list[dict[str, Any]] | None = None,
    verdict: str | None = None,
    source: str = "data room",
) -> dict[str, Any]:
    """Assemble the one result for an agent. Numbers are fact ids."""
    store: dict[str, dict[str, Any]] = {}
    numbers: dict[str, str] = {}
    for item in facts or []:
        fact_id = note_fact(
            store,
            name=str(item["name"]),
            source=str(item.get("source") or source),
            value=item.get("value"),
            calc_id=item.get("calc_id"),
            inputs=item.get("inputs"),
        )
        numbers[str(item["name"])] = fact_id
    detail_map = {key: list(value) for key, value in (details or {}).items()}
    count_ids: dict[str, str] = {}
    for name, stated in (counts or {}).items():
        fact_id = note_fact(store, name=name, source=source, value=stated)
        count_ids[name] = fact_id
        numbers[name] = fact_id
    tables: list[dict[str, Any]] = []
    if lines is not None and total is not None:
        table = tie_table(lines, total, source=source, store=store)
        tables.append({key: value for key, value in table.items() if key != "fact_store"})
    chart_rows = []
    for chart in charts or []:
        series = []
        for point in chart.get("series") or []:
            fact_id = note_fact(
                store,
                name=str(point.get("label") or "point"),
                source=source,
                value=point.get("value"),
            )
            series.append({"label": str(point.get("label") or "point"), "amount": fact_id})
        chart_rows.append({"title": chart.get("title") or agent_key, "series": series})
    result = {
        "agent_key": agent_key,
        "schema": RESULT_SCHEMA,
        "fact_store": store,
        "numbers": numbers,
        "counts": count_ids,
        "details": detail_map,
        "tables": tables,
        "charts": chart_rows,
        "verdict": verdict,
        "narrative": "",
    }
    result["narrative"] = render_narrative(result)
    return result


def render_narrative(result: dict[str, Any]) -> str:
    """Write the narrative from the result. Every number is one of its facts."""
    store = result.get("fact_store") or {}
    parts: list[str] = []
    for name, fact_id in (result.get("counts") or {}).items():
        fact = store.get(fact_id) or {}
        parts.append(f"{name} {fact.get('value')} ({fact.get('source')})")
    for table in result.get("tables") or []:
        if not table.get("ties"):
            continue
        labels = ", ".join(str(row.get("label")) for row in table.get("rows") or [])
        total = store.get(table.get("total") or "", {})
        parts.append(f"table {labels} totals {total.get('value')}")
    if result.get("verdict"):
        parts.append(f"verdict {result['verdict']}")
    if not parts:
        return f"{result.get('agent_key')} has no counted detail."
    return ". ".join(parts) + "."


def consistency_gate(result: dict[str, Any]) -> str | None:
    """Why this result cannot be published, or None when it is consistent."""
    missing = [field for field in RESULT_FIELDS if field not in result]
    if missing:
        return "result schema missing " + ", ".join(missing)
    if result.get("schema") != RESULT_SCHEMA:
        return "result schema is not agent_result_v1"
    store = result.get("fact_store") or {}
    if _bare_numbers(result, store):
        return "result numbers must be fact ids"
    count_gap = _count_gap(result, store)
    if count_gap:
        return count_gap
    if _zero_cohort_claim(result):
        return "0 cohorts above cohort figures"
    for table in result.get("tables") or []:
        if table.get("ties") is not True or not _table_ties(table, store):
            return "table does not tie to its total"
    narrative = str(result.get("narrative") or "")
    if narrative != render_narrative(result):
        return "narrative was not written from the result"
    return None


def ensure_agent_result(agent_key: str, output: dict[str, Any]) -> str | None:
    """Attach the one result. A contradiction is returned and blocks publication."""
    existing = output.get("result")
    if isinstance(existing, dict) and existing.get("schema") == RESULT_SCHEMA:
        existing["narrative"] = render_narrative(existing)
        return consistency_gate(existing)
    result = _derive_result(agent_key, output)
    gap = consistency_gate(result)
    if gap:
        output["result"] = result
        return gap
    output["result"] = result
    return None


def _derive_result(agent_key: str, output: dict[str, Any]) -> dict[str, Any]:
    spec = output.get("spec") if isinstance(output.get("spec"), dict) else {}
    details: dict[str, list[Any]] = {}
    counts: dict[str, Any] = {}
    for name in _LIST_FIELDS:
        rows = _rows(output, spec, name)
        if rows is None:
            continue
        details[name] = rows
        stated = _stated_count(output, spec, name)
        counts[name] = len(rows) if stated is None else stated
    source = _source(output)
    verdict = _verdict(output, spec)
    return build_agent_result(
        agent_key,
        counts=counts,
        details=details,
        verdict=verdict,
        source=source,
    )


def _rows(output: dict[str, Any], spec: dict[str, Any], name: str) -> list[Any] | None:
    for pool in (spec, output):
        value = pool.get(name)
        if isinstance(value, list):
            return value
    return None


def _stated_count(output: dict[str, Any], spec: dict[str, Any], name: str) -> int | None:
    for pool in (spec, output):
        value = pool.get(f"{name}_count")
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _source(output: dict[str, Any]) -> str:
    sources = output.get("sources")
    if isinstance(sources, list) and sources:
        first = sources[0]
        if isinstance(first, dict):
            return str(first.get("filename") or first.get("name") or "data room")
        return str(first)
    return "data room"


def _verdict(output: dict[str, Any], spec: dict[str, Any]) -> str | None:
    for pool in (spec, output):
        for key in ("verdict", "quality_verdict", "reliance"):
            value = pool.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _count_gap(result: dict[str, Any], store: dict[str, dict[str, Any]]) -> str | None:
    for name, fact_id in (result.get("counts") or {}).items():
        fact = store.get(fact_id) or {}
        count = fact.get("value")
        detail = result.get("details", {}).get(name) or []
        if not isinstance(detail, list):
            continue
        if count == 0 and detail:
            return f"{name} is 0 above {len(detail)} rows"
        if detail and isinstance(count, (int, float)) and int(count) != len(detail):
            return f"{name} count {count} contradicts {len(detail)} rows"
    return None


def _zero_cohort_claim(result: dict[str, Any]) -> bool:
    cohorts = result.get("details", {}).get("cohorts") or []
    if not cohorts:
        return False
    verdict = str(result.get("verdict") or "")
    narrative = str(result.get("narrative") or "")
    return bool(_ZERO_COHORTS.search(verdict) or _ZERO_COHORTS.search(narrative))


def _bare_numbers(result: dict[str, Any], store: dict[str, dict[str, Any]]) -> bool:
    for fact_id in list((result.get("numbers") or {}).values()) + list((result.get("counts") or {}).values()):
        if not isinstance(fact_id, str) or fact_id not in store:
            return True
    return False


def _table_ties(table: dict[str, Any], store: dict[str, dict[str, Any]]) -> bool:
    total_id = table.get("total")
    total = (store.get(total_id) or {}).get("value")
    if total is None:
        return False
    covered = Decimal(0)
    for row in table.get("rows") or []:
        amount = (store.get(row.get("amount")) or {}).get("value")
        if amount is None:
            return False
        covered += _money_of(amount)
    return covered == _money_of(total)


def _money_of(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _as_float(value: Decimal) -> float:
    return float(value)


def _same(left: Any, right: Any) -> bool:
    return _money_of(left) == _money_of(right)
