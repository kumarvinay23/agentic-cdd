"""Ontology rule checker.

`run_identities` and `ebitda_bridge` are copied from the reference
implementation. A block failure is an open flag, and its databook tab stays
out of the publish set. Management EBITDA is the company's own line. Reported
EBITDA is the figure computed from the confirmed policy. Costs and cash
outflows stay positive; the ontology weight carries the sign, and the reader
records a sign flip.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from agetic_cdd_api.services_ontology import Ontology, load_ontology
from agetic_cdd_api.services_period_engine import TERM, _sel, index_of
from agetic_cdd_api.services_fact_repository import dkey

def run_identities(facts, onto: Ontology, rule_ids):
    idx = index_of(facts); res = []
    groups = sorted({(k[1], k[2]) for k in idx})
    def val(tok, pt, pe):
        t = TERM.fullmatch(tok.strip())
        if not t: return None
        cid, d = t.group(2), dkey(_sel(t.group(3)))
        f = idx.get((cid, pt, pe, d))
        if f is None and pt == "FM" and onto.concepts[cid]["period_nature"] == "instant": f = idx.get((cid, "AS_AT", pe, d))
        return None if f is None else f.value
    for rid in rule_ids:
        r = onto.rules[rid]
        for pt, pe in groups:
            lhs_instant = onto.concepts[TERM.fullmatch(r["lhs"].strip()).group(2)]["period_nature"] == "instant"
            if (pt == "AS_AT") != lhs_instant: continue             # balance rules at balance dates, flow rules at flow periods
            lhs = val(r["lhs"], pt, pe)
            if lhs is None: continue
            total, sign, ok = 0.0, 1, True
            for tok in re.findall(r"[+-]|\d+\*[a-z.0-9_]+|[a-z]+(?:\.[a-z0-9_]+)+(?:\[[^\]]+\])?", r["rhs"]):
                if tok in "+-": sign = 1 if tok == "+" else -1; continue
                v = val(tok, pt, pe)
                if v is None: ok = False; break
                total += sign * v
            if not ok: continue
            tol = max(r.get("abs_tol", 1.0), r.get("rel_tol", 0.001) * abs(lhs))
            res.append(dict(rule=rid, period_type=pt, period_end=pe, lhs=round(lhs, 2), rhs=round(total, 2), diff=round(lhs - total, 2), passed=abs(lhs - total) <= tol, severity=r["severity"]))
    return res

def ebitda_bridge(facts, onto: Ontology):
    """R-QOE-01: MANAGEMENT EBITDA must bridge to REPORTED EBITDA through recorded adjustments (qoe.adjustment_amount).
    With no adjustments recorded, every difference is flagged, and P&L lines whose value equals the difference are proposed."""
    idx = index_of(facts); out = []
    adj = defaultdict(float)
    for (cid, pt, pe, d), f in idx.items():
        if cid == "qoe.adjustment_amount" and dict(d).get("view") == "MANAGEMENT": adj[(pt, pe)] += f.value
    for (cid, pt, pe, d), f in idx.items():
        if cid != "fin.pl.ebitda" or dict(d).get("view") != "MANAGEMENT": continue
        rep = idx.get((cid, pt, pe, (("view", "REPORTED"),)))
        if not rep: continue
        gap = f.value - rep.value - adj[(pt, pe)]
        if abs(gap) <= 1.0: out.append(dict(rule="R-QOE-01", period_type=pt, period_end=pe, management=round(f.value, 2), reported=round(rep.value, 2), unbridged=0.0, passed=True)); continue
        match = sorted({x.concept_id + (f"[{list(x.dimensions.values())[0]}]" if x.dimensions else "") for (c2, p2, e2, d2), x in idx.items()
                        if p2 == pt and e2 == pe and c2.startswith("fin.pl.") and x.status in ("SELECTED", "DERIVED") and abs(abs(x.value) - abs(gap)) <= 1.0})
        out.append(dict(rule="R-QOE-01", period_type=pt, period_end=pe, management=round(f.value, 2), reported=round(rep.value, 2), unbridged=round(gap, 2), passed=False,
                        lines_equal_to_gap=match))
    return out


_FLAGS: dict[str, list[dict[str, Any]]] = {}


def cash_tie(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Months where cash-flow cash and balance-sheet cash were both present."""
    return [row for row in rules if row.get("rule") == "R-CF-03"]


def debt_tie(facts) -> list[dict[str, Any]]:
    """R-DEBT-01, copied from the reference runner: book facility balances against balance-sheet borrowings."""
    from agetic_cdd_api.services_period_engine import index_of

    debt_facts = [
        fact for fact in facts
        if getattr(fact, "concept_id", None) == "debt.balance" and (fact.dimensions or {}).get("balance_source")
    ]
    indexed = index_of(facts)
    ties = []
    for balance_date in sorted({fact.period_end for fact in debt_facts}):
        book = [
            fact for fact in debt_facts
            if fact.period_end == balance_date and fact.dimensions.get("balance_source") == "BOOK"
        ]
        selected = [fact for fact in book if fact.status == "SELECTED"]
        held = [fact for fact in book if fact.status == "HELD"]
        borrowings = [
            indexed.get((concept, "AS_AT", balance_date, ()))
            for concept in ("fin.bs.borrowings_current", "fin.bs.borrowings_non_current")
        ]
        if not any(borrowings) or not book:
            continue
        sheet_total = sum(fact.value for fact in borrowings if fact)
        register_total = sum(fact.value for fact in selected)
        ties.append(dict(
            rule="R-DEBT-01",
            balance_date=balance_date,
            facilities_with_book_balance=len(selected),
            facilities_without=len(held),
            without=[fact.dimensions["facility"] + ": " + (fact.reason_detail or "")[:70] for fact in held],
            register_total=round(register_total, 2),
            balance_sheet_borrowings=round(sheet_total, 2),
            gap=round(register_total - sheet_total, 2),
            passed=abs(register_total - sheet_total) <= max(1.0, 0.01 * abs(sheet_total)),
        ))
    return ties


def schedule_vs_book(facts) -> list[dict[str, Any]]:
    """R-DEBT-02. A room with no facility schedule is unverifiable, not a silent pass."""
    debt = [
        fact for fact in facts
        if getattr(fact, "concept_id", None) == "debt.balance" and (fact.dimensions or {}).get("facility")
    ]
    if not any((fact.dimensions or {}).get("balance_source") == "SCHEDULE" for fact in debt):
        return [dict(rule="R-DEBT-02", status="UNVERIFIABLE", reason="no facility schedule")]
    grouped: dict[tuple, dict] = defaultdict(dict)
    for fact in debt:
        source = (fact.dimensions or {}).get("balance_source")
        if source:
            grouped[(fact.dimensions["facility"], fact.period_end)][source] = fact
    compared = []
    for (facility, balance_date), sources in sorted(grouped.items()):
        schedule, book = sources.get("SCHEDULE"), sources.get("BOOK")
        if not (schedule and book):
            continue
        if schedule.value is None:
            compared.append(dict(
                rule="R-DEBT-02", facility=facility, date=balance_date,
                status="UNVERIFIABLE", reason=schedule.reason_code, book=book.value,
            ))
            continue
        if book.value is None:
            continue
        gap = schedule.value - book.value
        compared.append(dict(
            rule="R-DEBT-02", facility=facility, date=balance_date,
            status="PASS" if abs(gap) <= max(1.0, 0.001 * abs(book.value)) else "FAIL",
            schedule=schedule.value, book=book.value, diff=round(gap, 2),
        ))
    return compared


def check_rules(facts, deal_id: str) -> dict[str, Any]:
    """Run the identity rules and the EBITDA bridge. Block failures leave the publish set."""
    onto = load_ontology()
    identities = run_identities(facts, onto, _identity_ids(onto))
    bridge = ebitda_bridge(facts, onto)
    failed = [result for result in identities + bridge + debt_tie(facts) if result.get("passed") is False]
    failed += [
        dict(row, passed=False, period_end=row.get("date"))
        for row in schedule_vs_book(facts)
        if row.get("status") == "FAIL"
    ]
    flags = [_flag(deal_id, result, onto, facts) for result in failed]
    _FLAGS[deal_id] = flags
    _persist(deal_id, flags)
    schedules = _schedules(facts, onto)
    blocked = {flag["schedule_id"] for flag in flags if flag["severity"] == "block" and flag.get("schedule_id")}
    return {"flags": flags, "publish_set": sorted(schedules - blocked), "blocked_tabs": sorted(blocked)}


def open_flags(deal_id: str) -> list[dict[str, Any]]:
    """Open flags recorded for a deal."""
    return list(_FLAGS.get(deal_id, []))


def _identity_ids(onto: Ontology) -> list[str]:
    return [rule["id"] for rule in onto.b["rules"] if rule.get("lhs") and rule.get("rhs")]


def _flag(deal_id: str, result: dict[str, Any], onto: Ontology, facts) -> dict[str, Any]:
    code = str(result["rule"])
    rule = onto.rules.get(code, {})
    concept = _concept(rule.get("lhs") or rule.get("concept") or "")
    schedules = list((onto.concepts.get(concept) or {}).get("schedules") or [])
    return {
        "flag_id": (
            f"fl-{deal_id}-{code}-{result.get('period_end') or result.get('balance_date') or result.get('date') or 'na'}"
        ).replace(" ", ""),
        "deal_id": deal_id,
        "code": code,
        "severity": str(result.get("severity") or rule.get("severity") or "warn"),
        "schedule_id": schedules[0] if schedules else None,
        "fact_ids": _fact_ids(facts, result),
        "message": rule.get("description") or code,
        "status": "OPEN",
    }


def _concept(token: str) -> str:
    match = TERM.fullmatch(str(token).strip())
    return match.group(2) if match else ""


def _schedules(facts, onto: Ontology) -> set[str]:
    found: set[str] = set()
    for fact in facts:
        if getattr(fact, "status", None) not in {"SELECTED", "DERIVED"}:
            continue
        found.update(onto.concepts.get(fact.concept_id, {}).get("schedules") or [])
    return found


def _fact_ids(facts, result: dict[str, Any]) -> list[str]:
    period_end = result.get("period_end")
    return [
        fact.fact_id
        for fact in facts
        if getattr(fact, "period_end", None) == period_end and getattr(fact, "fact_id", None)
    ]


def _persist(deal_id: str, flags: list[dict[str, Any]]) -> None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not _deal_exists(url, deal_id):
        return
    from agetic_cdd_api.services_databook_migrate import psql

    script = f"DELETE FROM flag WHERE deal_id = {_sql(deal_id)}; "
    script += " ".join(_insert(flag) for flag in flags)
    result = psql(url, script)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "flag write failed")


def _deal_exists(url: str, deal_id: str) -> bool:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(url, f"SELECT deal_id FROM deal WHERE deal_id = {_sql(deal_id)}")
    return result.returncode == 0 and deal_id in result.stdout


def _insert(flag: dict[str, Any]) -> str:
    schedule = "NULL" if not flag.get("schedule_id") else _sql(flag["schedule_id"])
    ids = "ARRAY[]::text[]" if not flag["fact_ids"] else "ARRAY[" + ", ".join(_sql(item) for item in flag["fact_ids"]) + "]::text[]"
    return (
        "INSERT INTO flag (flag_id, deal_id, code, severity, schedule_id, fact_ids, message, status) VALUES ("
        f"{_sql(flag['flag_id'])}, {_sql(flag['deal_id'])}, {_sql(flag['code'])}, {_sql(flag['severity'])}, "
        f"{schedule}, {ids}, {_sql(flag['message'])}, {_sql(flag['status'])});"
    )


def _sql(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
