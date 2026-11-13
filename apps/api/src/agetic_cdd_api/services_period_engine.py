"""Calculation and period engine.

`run_calculations`, `derive_periods`, and `compare_with_source` are copied
from the reference implementation. Totals, ratios, FY, YTD, and LTM come from
stored lines. The period type comes from the months covered and the confirmed
fiscal year end. A source total that differs from the derived total is stored
on reconciliation with a reason.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import defaultdict
from typing import Any

from agetic_cdd_api.services_fact_repository import Fact, dkey, get_fact, save_fact
from agetic_cdd_api.services_ontology import Ontology, load_ontology
from agetic_cdd_api.services_statement_reader import fiscal_year

TERM = re.compile(r"(policy:\w+\s+)?([a-z]+(?:\.[a-z0-9_]+)+)(\[[^\]]+\])?(\?)?")

def _sel(sel):
    return {} if not sel else dict(kv.split("=") for kv in sel.strip("[]").split(","))

def run_calculations(facts, onto: Ontology, policy, period_types):
    """Executes the ontology's calculation linkbase per period. Returns DERIVED facts."""
    stored = [f for f in facts if f.status in ("SELECTED", "DERIVED") and f.value is not None and f.period_type in period_types]
    by_p = defaultdict(list)
    for f in stored: by_p[(f.period_type, f.period_end)].append(f)
    out = []
    for (pt, pe), fs in by_p.items():
        have = {(f.concept_id, dkey(f.dimensions)): f for f in fs}
        lines = [f for f in fs if f.status == "SELECTED"]
        def emit(cid, dims, val, src, formula, calc_id):
            c = onto.concepts[cid]; s0 = src[0] if src else None
            tier = max((x.evidence_tier for x in src), default="B")       # a derived fact is only as strong as its weakest input
            f = Fact(cid, val, c["unit_type"], pt, s0.period_start if s0 else None, pe, s0.months_covered if s0 else None, "ACTUAL", dims, None, tier, [], status="DERIVED",
                     currency=next((x.currency for x in src if x.currency), None) if c["unit_type"] == "CURRENCY" else None, derived_from=[x.fact_id for x in src],
                     formula=f"{calc_id}: {formula}", mapping=dict(calculation=calc_id))
            have[(cid, dkey(dims))] = f; out.append(f); return f
        for k in onto.calcs:
            if pt not in k["period_types"]: continue
            expr, target = k["expr"], k["target"]
            if expr == "ROLLUP(*)":
                grp = defaultdict(list)
                for f in fs:
                    dim = onto.concepts[f.concept_id].get("split_dimension", "line")
                    if dim in f.dimensions or "line" in f.dimensions:
                        rest = {a: b for a, b in f.dimensions.items() if a not in (dim, "line")}
                        grp[(f.concept_id, dkey(rest))].append(f)
                for (cid, rest), mem in grp.items():
                    if (cid, rest) not in have:
                        emit(cid, dict(rest), sum(m.value for m in mem), mem, f"sum of {len(mem)} split-dimension members", k["id"])
                continue
            tcid, tsel = re.fullmatch(r"([a-z0-9_.]+)(\[[^\]]+\])?", target).groups()
            views = [None]
            if tsel and "=*" in tsel:
                num = TERM.search(expr).group(2)
                views = sorted({dict(d).get("view") for (cid, d) in have if cid == num and dict(d).get("view")})
            for v in views:
                tdims = {a: (v if b == "*" else b) for a, b in _sel(tsel).items()}
                if (tcid, dkey(tdims)) in have: continue
                m = re.fullmatch(r"(CLASSIFIED|CHILDREN)\(([\w.]+)\)", expr)
                if m and m.group(1) == "CLASSIFIED":
                    src = [f for f in lines if f.mapping.get("classification") == m.group(2) and f.concept_id != tcid]
                    if not src: continue
                    sgn = lambda f: (-1 if onto.concepts[f.concept_id].get("contra_of") else 1) * \
                                    (onto.concepts[f.concept_id].get("weight", 1) if not onto.concepts[f.concept_id].get("signed") else 1)
                    emit(tcid, tdims, sum(sgn(f) * f.value for f in src), src, f"signed sum of lines classified {m.group(2)} by the source", k["id"]); continue
                if m and m.group(1) == "CHILDREN":
                    src = [have[(ch, ())] for ch in onto.children.get(m.group(2), []) if (ch, ()) in have]
                    if not src: continue
                    emit(tcid, tdims, sum(onto.concepts[f.concept_id].get("weight", 1) * f.value for f in src), src, f"sum of child concepts of {m.group(2)}", k["id"]); continue
                if "/" in expr:
                    a, b = [x.strip() for x in expr.split("/")]
                    na, nb = TERM.fullmatch(a), TERM.fullmatch(b)
                    fa = have.get((na.group(2), dkey({x: (v if y == "*" else y) for x, y in _sel(na.group(3)).items()})))
                    fb = have.get((nb.group(2), ()))
                    if fa and fb and fb.value:
                        emit(tcid, tdims, fa.value / fb.value, [fa, fb], expr.replace("*", v or ""), k["id"])
                    continue
                total, src, ok, sign = 0.0, [], True, 1
                for tok in re.findall(r"[+-]|(?:policy:\w+\s+)?[a-z]+(?:\.[a-z0-9_]+)+(?:\[[^\]]+\])?\??", expr):
                    if tok in "+-": sign = 1 if tok == "+" else -1; continue
                    t = TERM.fullmatch(tok)
                    if t.group(1) and not policy.get(t.group(1).split(":")[1].strip()): continue
                    f = have.get((t.group(2), dkey(_sel(t.group(3)))))
                    if f is None:
                        if t.group(4): continue
                        ok = False; break
                    total += sign * f.value; src.append(f)
                if ok and src: emit(tcid, tdims, total, src, expr, k["id"])
    return out

def derive_periods(facts, onto: Ontology, latest_actual: dt.date, fye_month: int = 12):
    fm = defaultdict(dict)
    for f in facts:
        if f.period_type == "FM" and f.status in ("SELECTED", "DERIVED") and f.value is not None and onto.concepts[f.concept_id].get("aggregation", "sum") in ("sum", "first", "last"):
            fm[(f.concept_id, dkey(f.dimensions), f.unit_type, f.currency)][f.period_end] = f
    out, la = [], latest_actual.isoformat()
    for (cid, dims, unit, cur), by_end in fm.items():
        ends = sorted(by_end)
        agg = onto.concepts[cid].get("aggregation", "sum")
        def mk(ptype, sel, pstart):
            fs = [by_end[e] for e in sel]
            v = sum(f.value for f in fs) if agg == "sum" else (fs[0].value if agg == "first" else fs[-1].value)
            out.append(Fact(cid, v, unit, ptype, pstart, sel[-1], len(sel), "ACTUAL", dict(dims), None, max(f.evidence_tier for f in fs), [], status="DERIVED", currency=cur,
                            derived_from=[f.fact_id for f in fs], formula=(f"sum of {len(sel)} monthly facts" if agg == "sum" else f"{agg} of {len(sel)} monthly facts")))
        fy = lambda e: fiscal_year(dt.date.fromisoformat(e), fye_month)
        ytd_n = (latest_actual.month - fye_month - 1) % 12 + 1          # months from fiscal-year start to the latest actual month
        for y in sorted({fy(e) for e in ends}):
            sel = [e for e in ends if fy(e) == y and e <= la]
            if len(sel) == 12: mk("FY", sel, sel[0][:8] + "01")
            elif sel and sel[-1] == la and len(sel) == ytd_n: mk("YTD", sel, sel[0][:8] + "01")
        prior = [e for e in ends if fy(e) == fiscal_year(latest_actual, fye_month) - 1][:ytd_n]
        if ytd_n < 12 and len(prior) == ytd_n: mk("YTD", prior, prior[0][:8] + "01")
        last12 = [e for e in ends if e <= la][-12:]
        if len(last12) == 12 and last12[-1] == la: mk("LTM", last12, last12[0][:8] + "01")
    return out

def index_of(facts, statuses=("SELECTED", "DERIVED")):
    return {(f.concept_id, f.period_type, f.period_end, dkey(f.dimensions)): f for f in facts if f.status in statuses and f.value is not None}

def compare_with_source(facts, items_by_stmt):
    """R-SRC-02 (subtotals and ratios at FM / AS_AT) and R-SRC-03 (annual columns at FY / YTD)."""
    der = index_of(facts, ("DERIVED", "SELECTED")); res = []
    for f in facts:
        if f.status != "COMPARATIVE" or f.value is None: continue
        d = der.get((f.concept_id, f.period_type, f.period_end, dkey(f.dimensions)))
        rule = "R-SRC-03" if f.reason_code == "DUPLICATE" else "R-SRC-02"
        if not d: res.append(dict(rule=rule, concept=f.concept_id, dims=f.dimensions, period_type=f.period_type, period_end=f.period_end, source=f.value, derived=None, passed=None, note="no derived fact")); continue
        tol = 0.0005 if f.unit_type == "PERCENT" else max(1.0, 0.0001 * abs(f.value))
        diff = f.value - d.value
        r = dict(rule=rule, concept=f.concept_id, dims=f.dimensions, period_type=f.period_type, period_end=f.period_end, source=round(f.value, 4), derived=round(d.value, 4),
                 diff=round(diff, 4), passed=abs(diff) <= tol, explained_by=None)
        if not r["passed"] and f.mapping.get("row") is not None:
            it = items_by_stmt.get(f.mapping["row"], {})
            outside = it.get("composition_outside") or []
            ex = sum(x["facts"][f.period_end].value * (-1 if x.get("contra") else 1) for x in outside if f.period_end in x.get("facts", {}))
            if outside and abs(diff - ex) <= tol:
                r["explained_by"] = "composition: the source subtotal also holds " + ", ".join(sorted({x["cid"] for x in outside}))
        res.append(r)
    return res


_RECON: dict[str, list[dict[str, Any]]] = {}


def run_period_engine(facts, *, deal_id: str, policy: dict, latest_actual: dt.date, fye_month: int, items_by_stmt=None) -> dict[str, Any]:
    """Derive totals and periods, then keep each source difference on reconciliation."""
    working = _dated(list(facts))
    working += run_calculations(working, load_ontology(), policy, {"FM", "AS_AT"})
    working += derive_periods(working, load_ontology(), latest_actual, fye_month)
    working += run_calculations(working, load_ontology(), policy, {"FY", "YTD", "LTM"})
    comparisons = compare_with_source(working, items_by_stmt or {})
    stored = [_save(fact, deal_id) for fact in working]
    reconciliations = _reconcile(comparisons, working, deal_id)
    return {"facts": [row for row in stored if row], "comparisons": comparisons, "reconciliations": reconciliations}


def reconciliations_for(deal_id: str) -> list[dict[str, Any]]:
    """Differences stored for a deal."""
    return list(_RECON.get(deal_id, []))


def _dated(facts):
    for fact in facts:
        fact.period_end = _day(fact.period_end)
        fact.period_start = _day(fact.period_start)
    return facts


def _day(value):
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return value


def _save(fact, deal_id: str):
    if get_fact(fact.fact_id):
        return get_fact(fact.fact_id)
    try:
        from agetic_cdd_api.services_resolver import resolve_fact

        save_fact(resolve_fact(_fact_row(fact, deal_id)))
    except ValueError as exc:
        if "fact_key_selected" not in str(exc):
            raise
    return get_fact(fact.fact_id)


def _fact_row(fact, deal_id: str) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "deal_id": deal_id,
        "entity_id": fact.entity_id,
        "concept_id": fact.concept_id,
        "value": fact.value,
        "unit_type": fact.unit_type,
        "currency": fact.currency,
        "scale_applied": fact.scale_applied or 1,
        "period_type": fact.period_type,
        "period_start": fact.period_start,
        "period_end": fact.period_end,
        "months_covered": fact.months_covered,
        "basis": fact.basis,
        "dimensions": dict(fact.dimensions or {}),
        "doc_id": fact.doc_id,
        "evidence_tier": fact.evidence_tier,
        "source_location_ids": list(fact.source_location_ids or []),
        "status": fact.status,
        "reason_code": fact.reason_code,
        "reason_detail": fact.reason_detail,
        "derived_from": list(fact.derived_from or []),
        "formula": fact.formula,
    }


def _reconcile(comparisons, facts, deal_id: str) -> list[dict[str, Any]]:
    rows = []
    for result in comparisons:
        if result.get("passed") is not False:
            continue
        chosen = _match(facts, result, ("DERIVED", "SELECTED"))
        source = _match(facts, result, ("COMPARATIVE",))
        if chosen is None or source is None:
            continue
        rows.append(_recon_row(deal_id, chosen, source, result))
    _RECON[deal_id] = rows
    _persist(deal_id, rows)
    return rows


def _match(facts, result, statuses):
    wanted = dkey(result.get("dims") or {})
    period_end = _day(result.get("period_end"))
    for fact in facts:
        if fact.status not in statuses or fact.concept_id != result.get("concept"):
            continue
        if fact.period_type != result.get("period_type") or _day(fact.period_end) != period_end:
            continue
        if dkey(fact.dimensions) == wanted:
            return fact
    return None


def _recon_row(deal_id: str, chosen, source, result) -> dict[str, Any]:
    variance = float(result["diff"])
    derived = result.get("derived")
    reason = result.get("explained_by") or "source total differs from the derived total"
    return {
        "deal_id": deal_id,
        "selected_fact_id": chosen.fact_id,
        "comparative_fact_id": source.fact_id,
        "variance": variance,
        "variance_pct": None if not derived else variance / float(derived),
        "explanation": reason,
        "status": "EXPLAINED" if result.get("explained_by") else "OPEN",
    }


def _persist(deal_id: str, rows: list[dict[str, Any]]) -> None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not _deal_exists(url, deal_id):
        return
    from agetic_cdd_api.services_databook_migrate import psql

    script = f"DELETE FROM reconciliation WHERE deal_id = {_sql(deal_id)}; "
    script += " ".join(_insert(row) for row in rows)
    result = psql(url, script)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "reconciliation write failed")


def _deal_exists(url: str, deal_id: str) -> bool:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(url, f"SELECT deal_id FROM deal WHERE deal_id = {_sql(deal_id)}")
    return result.returncode == 0 and deal_id in result.stdout


def _insert(row: dict[str, Any]) -> str:
    pct = "NULL" if row["variance_pct"] is None else str(float(row["variance_pct"]))
    return (
        "INSERT INTO reconciliation ("
        "deal_id, selected_fact_id, comparative_fact_id, variance, variance_pct, explanation, status"
        ") VALUES ("
        f"{_sql(row['deal_id'])}, {_sql(row['selected_fact_id'])}, {_sql(row['comparative_fact_id'])}, "
        f"{float(row['variance'])}, {pct}, {_sql(row['explanation'])}, {_sql(row['status'])});"
    )


def _sql(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
