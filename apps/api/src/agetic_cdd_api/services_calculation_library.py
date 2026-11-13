"""Recipes for the metrics the financial calculation library does not cover.

An agent asks for a calculation by id and receives the value, the formula,
the inputs and the sources. The model comments on that result. Percentage
recipes use a ratio (1 = 100%), which is the unit the metric checks use.
Pass scale="percent" when the caller needs percentage points.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Any

_RATIO = "ratio"
_CURRENCY = "currency"
_MULTIPLE = "multiple"


def ask_calculation(
    calc_id: str,
    *,
    inputs: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    sources: list[str] | None = None,
    scale: str = "ratio",
    rounding: int | None = None,
) -> dict[str, Any]:
    """Run one recipe. Records are customer, contract or cohort rows."""
    spec = _RECIPES.get(calc_id)
    if spec is None:
        raise ValueError(f"unknown calculation {calc_id}")
    target, unit, formula, recipe = spec
    used = _inputs_for(calc_id, inputs or {}, records or [])
    raw = recipe(used)
    used.pop("trading_value", None)
    places = _rounding(unit, scale, rounding)
    value = _present(raw, unit, scale, places)
    named = [str(item) for item in (sources or used.get("sources") or []) if str(item).strip()]
    stored = {key: value_ for key, value_ in used.items() if key != "sources"}
    published = {
        "calc_id": calc_id,
        "target": target,
        "value": value,
        "formula": formula,
        "inputs": stored,
        "sources": named,
        "unit": unit,
        "scale": "percent" if scale == "percent" and unit == _RATIO else "number",
        "rounding": places,
        "checks": _checks(calc_id, raw, stored),
    }
    fact_id = _store_result(published)
    if fact_id:
        published["fact_id"] = fact_id
    return published


def recompute(published: dict[str, Any]) -> dict[str, Any]:
    """Run the stored recipe again. CI uses this on every published number."""
    again = ask_calculation(
        str(published["calc_id"]),
        inputs=dict(published.get("inputs") or {}),
        sources=list(published.get("sources") or []),
        scale="percent" if published.get("scale") == "percent" else "ratio",
        rounding=int(published["rounding"]),
    )
    return {
        "calc_id": again["calc_id"],
        "match": again["value"] == published.get("value"),
        "published": published.get("value"),
        "recomputed": again["value"],
    }


def _store_result(published: dict[str, Any]) -> str | None:
    """Store an ontology concept through the fact repository."""
    from agetic_cdd_api.services_fact_repository import save_fact

    unit = str(published.get("unit") or "")
    scale = str(published.get("scale") or "")
    if scale == "percent" and unit == _RATIO:
        unit_type = "PERCENT"
    else:
        unit_type = {"ratio": "RATIO", "currency": "CURRENCY", "multiple": "MULTIPLE"}.get(unit, "OTHER")
    row = {
        "deal_id": published.get("deal_id") or "unassigned",
        "concept_id": published.get("target"),
        "value": published.get("value"),
        "unit_type": unit_type,
        "period_type": "POINT",
        "dimensions": {"run": uuid.uuid4().hex[:8]},
        "basis": "ACTUAL",
        "status": "DERIVED",
        "evidence_tier": "B",
        "derived_from": [str(published.get("calc_id") or "calculation")],
        "formula": published.get("formula"),
        "name": published.get("target"),
        "source": ", ".join(published.get("sources") or []) or str(published.get("formula") or ""),
        "calc_id": published.get("calc_id"),
    }
    if unit_type == "CURRENCY":
        row["currency"] = published.get("currency")
    try:
        return save_fact(row)
    except ValueError:
        return None


def _inputs_for(calc_id: str, inputs: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    if records and calc_id in _FROM_RECORDS:
        derived = _FROM_RECORDS[calc_id](records, inputs)
        return {**derived, **{key: value for key, value in inputs.items() if value is not None}}
    return dict(inputs)


def _movements(records: list[dict[str, Any]]) -> dict[str, float]:
    opening = expansion = contraction = churn = 0.0
    for row in records:
        prior = _num(row.get("opening_revenue", row.get("prior_revenue")), None)
        if prior is None:
            continue
        opening += prior
        if row.get("churned") is True or row.get("retained") is False:
            stated = _num(row.get("churn_revenue"), None)
            churn += prior if stated is None else stated
            continue
        if any(key in row for key in ("expansion", "contraction", "churn_revenue")):
            expansion += _num(row.get("expansion"), 0.0) or 0.0
            contraction += _num(row.get("contraction"), 0.0) or 0.0
            churn += _num(row.get("churn_revenue"), 0.0) or 0.0
            continue
        current = _num(row.get("revenue"), prior) or prior
        if current >= prior:
            expansion += current - prior
        else:
            contraction += prior - current
    return {
        "opening_revenue": opening,
        "expansion": expansion,
        "contraction": contraction,
        "churn": churn,
    }


def _logo_counts(records: list[dict[str, Any]]) -> dict[str, float]:
    opening = [row for row in records if row.get("opening") is True or "prior_revenue" in row or "opening_revenue" in row]
    retained = [
        row for row in opening
        if row.get("retained") is True or (row.get("churned") is not True and row.get("retained") is not False)
    ]
    return {"opening": float(len(opening)), "retained": float(len(retained))}


def _cohort_counts(records: list[dict[str, Any]], inputs: dict[str, Any]) -> dict[str, float]:
    cohort = inputs.get("cohort")
    chosen = [row for row in records if cohort is None or row.get("cohort") == cohort]
    if not chosen:
        raise ValueError("cohort retention needs cohort records")
    opening = _num(chosen[0].get("opening"), None)
    retained = _num(chosen[0].get("retained"), None)
    if opening is None or retained is None:
        raise ValueError("cohort retention needs opening and retained")
    return {"opening": opening, "retained": retained, "cohort": str(chosen[0].get("cohort") or cohort or "")}


def _revenues(records: list[dict[str, Any]], inputs: dict[str, Any]) -> dict[str, Any]:
    amounts = [_num(row.get("revenue"), None) for row in records]
    amounts = [amount for amount in amounts if amount is not None]
    if not amounts:
        raise ValueError("concentration needs customer revenue")
    return {"revenues": amounts, "top_n": int(inputs.get("top_n") or 1)}


def _customer_revenue(records: list[dict[str, Any]], inputs: dict[str, Any]) -> dict[str, float]:
    amounts = [_num(row.get("revenue"), None) for row in records]
    amounts = [amount for amount in amounts if amount is not None]
    customers = len({row.get("customer_id") or index for index, row in enumerate(records)}) or len(amounts)
    payload: dict[str, Any] = {"revenue": sum(amounts), "customers": float(customers)}
    if inputs.get("period_months") is not None:
        payload["period_months"] = inputs["period_months"]
    if inputs.get("market") is not None:
        payload["market"] = inputs["market"]
    return payload


_FROM_RECORDS = {
    "CALC-KPI-CONCENTRATION": _revenues,
    "CALC-KPI-LOGO-RETENTION": lambda records, _inputs: _logo_counts(records),
    "CALC-KPI-LOGO-CHURN": lambda records, _inputs: _logo_counts(records),
    "CALC-KPI-COHORT-RETENTION": _cohort_counts,
    "CALC-KPI-GRR": lambda records, _inputs: _movements(records),
    "CALC-KPI-NRR": lambda records, _inputs: _movements(records),
    "CALC-KPI-REVENUE-PER-CUSTOMER": _customer_revenue,
    "CALC-MKT-SHARE": _customer_revenue,
}


def _need(inputs: dict[str, Any], *names: str) -> float:
    for name in names:
        value = _num(inputs.get(name), None)
        if value is not None:
            return value
    raise ValueError("missing " + " or ".join(names))


def _div(numerator: float, denominator: float) -> Decimal:
    return Decimal(str(numerator)) / Decimal(str(denominator))


def _concentration(inputs: dict[str, Any]) -> Decimal:
    revenues = [Decimal(str(item)) for item in inputs.get("revenues") or []]
    total = sum(revenues, Decimal(0))
    if total == 0:
        raise ValueError("concentration needs revenue")
    top_n = int(inputs.get("top_n") or 1)
    return sum(sorted(revenues, reverse=True)[:top_n]) / total


def _logo_retention(inputs: dict[str, Any]) -> Decimal:
    if inputs.get("logo_churn") is not None:
        return Decimal(1) - Decimal(str(inputs["logo_churn"]))
    opening = _need(inputs, "opening")
    if opening == 0:
        raise ValueError("logo retention needs opening customers")
    return _div(_need(inputs, "retained"), opening)


def _logo_churn(inputs: dict[str, Any]) -> Decimal:
    if inputs.get("logo_retention") is not None:
        return Decimal(1) - Decimal(str(inputs["logo_retention"]))
    opening = _need(inputs, "opening")
    if opening == 0:
        raise ValueError("logo churn needs opening customers")
    retained = _num(inputs.get("retained"), None)
    churned = opening - retained if retained is not None else _need(inputs, "churned")
    return _div(churned, opening)


def _cohort_retention(inputs: dict[str, Any]) -> Decimal:
    opening = _need(inputs, "opening")
    if opening == 0:
        raise ValueError("cohort retention needs opening customers")
    return _div(_need(inputs, "retained"), opening)


def _grr(inputs: dict[str, Any]) -> Decimal:
    opening = _need(inputs, "opening_revenue")
    if opening == 0:
        raise ValueError("gross revenue retention needs opening revenue")
    lost = (_num(inputs.get("contraction"), 0.0) or 0.0) + (_num(inputs.get("churn"), 0.0) or 0.0)
    return _div(opening - lost, opening)


def _nrr(inputs: dict[str, Any]) -> Decimal:
    opening = _need(inputs, "opening_revenue")
    if opening == 0:
        raise ValueError("net revenue retention needs opening revenue")
    lost = (_num(inputs.get("contraction"), 0.0) or 0.0) + (_num(inputs.get("churn"), 0.0) or 0.0)
    return _div(opening - lost + (_num(inputs.get("expansion"), 0.0) or 0.0), opening)


def _revenue_per_customer(inputs: dict[str, Any]) -> float:
    customers = _need(inputs, "customers")
    if customers == 0:
        raise ValueError("revenue per customer needs customers")
    revenue = _need(inputs, "revenue")
    months = _num(inputs.get("period_months"), None)
    if months:
        return revenue / months / customers
    return revenue / customers


def _market_share(inputs: dict[str, Any]) -> Decimal:
    market = _need(inputs, "market")
    if market == 0:
        raise ValueError("market share needs a market size")
    return _div(_need(inputs, "revenue"), market)


def _trading(inputs: dict[str, Any]) -> float:
    plan = _need(inputs, "plan")
    if inputs.get("ytd") is not None and inputs.get("months") is not None:
        trading = float(inputs["ytd"]) / float(inputs["months"]) * 12.0
    elif inputs.get("trading") is not None:
        trading = float(inputs["trading"])
    else:
        earlier = _need(inputs, "earlier")
        later = _need(inputs, "later")
        years = _need(inputs, "plan_year") - _need(inputs, "later_year")
        if earlier == 0:
            raise ValueError("trading needs a non-zero base year")
        trading = later * (later / earlier) ** years
    inputs["trading_value"] = trading
    return plan - trading


def _multiple(numerator: str, denominator: str):
    def recipe(inputs: dict[str, Any]) -> float:
        base = _need(inputs, denominator)
        if base == 0:
            raise ValueError(f"{denominator} is zero")
        return _need(inputs, numerator) / base

    return recipe


def _median_multiple(inputs: dict[str, Any]) -> float:
    values = [float(item) for item in inputs.get("multiples") or []]
    if not values:
        raise ValueError("comps need at least one multiple")
    return float(median(values))


def _implied(inputs: dict[str, Any]) -> float:
    return _median_multiple(inputs) * _need(inputs, "metric")


def _synergy(inputs: dict[str, Any]) -> float:
    return _need(inputs, "gross") - _num(inputs.get("cost_to_achieve"), 0.0)


def _expansion(inputs: dict[str, Any]) -> Decimal:
    return Decimal(str(_need(inputs, "nrr"))) - Decimal(str(_need(inputs, "grr")))


def _annualise(inputs: dict[str, Any]) -> Decimal:
    return Decimal(str(_need(inputs, "monthly"))) ** 12


_RECIPES: dict[str, tuple[str, str, str, Any]] = {
    "CALC-KPI-CONCENTRATION": ("kpi.concentration_top_n_pct", _RATIO, "sum(top revenues) / sum(revenues)", _concentration),
    "CALC-KPI-LOGO-RETENTION": ("kpi.logo_retention_pct", _RATIO, "retained / opening", _logo_retention),
    "CALC-KPI-LOGO-CHURN": ("kpi.logo_churn_pct", _RATIO, "1 - logo retention", _logo_churn),
    "CALC-KPI-COHORT-RETENTION": ("kpi.cohort_retention_pct", _RATIO, "cohort retained / cohort opening", _cohort_retention),
    "CALC-KPI-GRR": ("kpi.grr_pct", _RATIO, "(opening - contraction - churn) / opening", _grr),
    "CALC-KPI-NRR": ("kpi.nrr_pct", _RATIO, "(opening - contraction - churn + expansion) / opening", _nrr),
    "CALC-KPI-REVENUE-PER-CUSTOMER": ("kpi.arpu", _CURRENCY, "revenue / customers", _revenue_per_customer),
    "CALC-KPI-ANNUALISE": ("kpi.cohort_retention_pct", _RATIO, "monthly ** 12", _annualise),
    "CALC-KPI-EXPANSION": ("kpi.nrr_pct", _RATIO, "nrr - grr", _expansion),
    "CALC-MKT-SHARE": ("mkt.market_share_pct", _RATIO, "revenue / market", _market_share),
    "CALC-PLAN-VS-TRADING": ("plan_vs_trading", _CURRENCY, "plan - trading run-rate", _trading),
    "CALC-VAL-EV-EBITDA": ("deal.ev_ebitda_multiple", _MULTIPLE, "enterprise value / ebitda", _multiple("enterprise_value", "ebitda")),
    "CALC-VAL-EV-REVENUE": ("deal.ev_revenue_multiple", _MULTIPLE, "enterprise value / revenue", _multiple("enterprise_value", "revenue")),
    "CALC-VAL-MOIC": ("deal.moic", _MULTIPLE, "exit value / invested", _multiple("exit_value", "invested")),
    "CALC-COMPS-MEDIAN": ("deal.trading_comp_multiple", _MULTIPLE, "median(trading multiples)", _median_multiple),
    "CALC-COMPS-IMPLIED": ("deal.ev_ebitda_multiple", _CURRENCY, "median trading multiple * metric", _implied),
    "CALC-PRECEDENT-MEDIAN": ("deal.precedent_multiple", _MULTIPLE, "median(precedent multiples)", _median_multiple),
    "CALC-PRECEDENT-IMPLIED": ("deal.ev_ebitda_multiple", _CURRENCY, "median precedent multiple * metric", _implied),
    "CALC-SYNERGY-NET": ("deal.synergy_net", _CURRENCY, "gross synergy - cost to achieve", _synergy),
}


def _checks(calc_id: str, value: Decimal | float, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    number = Decimal(value) if isinstance(value, Decimal) else Decimal(str(value))
    if calc_id == "CALC-KPI-GRR":
        nrr = inputs.get("nrr")
        within = number <= 1 and (nrr is None or number <= Decimal(str(nrr)))
        checks.append({"id": "R-KPI-03", "passed": bool(within)})
    if calc_id == "CALC-KPI-CONCENTRATION":
        checks.append({"id": "R-KPI-04", "passed": bool(Decimal(0) <= number <= 1)})
    if calc_id == "CALC-KPI-LOGO-CHURN" and inputs.get("logo_retention") is not None:
        expected = Decimal(1) - Decimal(str(inputs["logo_retention"]))
        checks.append({"id": "R-KPI-02", "passed": number == expected})
    return checks


def _present(value: Decimal | float, unit: str, scale: str, places: int) -> float:
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    if scale == "percent" and unit == _RATIO:
        number *= 100
    quant = Decimal("1").scaleb(-places)
    return float(number.quantize(quant, rounding=ROUND_HALF_UP))


def _rounding(unit: str, scale: str, rounding: int | None) -> int:
    if rounding is not None:
        return rounding
    if scale == "percent" and unit == _RATIO:
        return 2
    if unit == _RATIO:
        return 4
    return 2


def _num(value: Any, default: float | None) -> float | None:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return default
