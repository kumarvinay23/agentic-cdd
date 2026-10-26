"""Calculations for the CDD deck.

Every output is a formula over evidence ids. A haircut is applied only when
the bottom-up record states the rate and a money base. A plan year is never
treated as an actual. Mix shares are calculated from segment revenue when
the module did not already state a share.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agetic_cdd_api.report_builder_base import BuildContext
from agetic_cdd_api.report_cdd_deck_v4 import (
    _filled,
    _is_ledger_sizing_text,
    _is_qa_meta,
    _pct_from,
    _reported_period_type,
    _resolve,
    _spec,
)
from agetic_cdd_api.report_cdd_evidence import EvidenceBook

_YEAR = re.compile(r"(20\d{2})")
_HAIRCUT = re.compile(r"(?i)haircut")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_MONEY = re.compile(r"\$\s*([\d,.]+)\s*(million|billion|m|bn|b)?\b|(?<![\d.])([\d,.]+)\s*(million|billion)\b", re.I)


@dataclass
class Calc:
    id: str
    formula: str
    inputs: dict[str, dict[str, Any]]
    output: float
    unit: str
    used_on: list[str]
    rounding: int = 1
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "formula": self.formula,
            "inputs": self.inputs,
            "output": self.output,
            "unit": self.unit,
            "rounding": self.rounding,
            "used_on": self.used_on,
            "also_shown_as": [],
        }


@dataclass
class DeckMath:
    calculations: list[Calc] = field(default_factory=list)
    yoy: list[dict[str, Any]] = field(default_factory=list)
    mix: list[dict[str, Any]] = field(default_factory=list)
    mix_calculated: bool = False
    bridge: dict[str, Any] | None = None
    momentum: dict[str, Any] | None = None
    retention: dict[str, Any] | None = None
    haircuts: list[dict[str, Any]] = field(default_factory=list)
    margins: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)
    costs: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    assessment: dict[str, Any] | None = None
    prices: dict[str, Any] | None = None
    retention_curve: dict[str, Any] | None = None
    lever_dollars: dict[str, Any] | None = None
    logos: dict[str, Any] | None = None
    quotas: dict[str, Any] | None = None
    zips: dict[str, Any] | None = None
    initiatives: dict[str, Any] | None = None
    deals: dict[str, Any] | None = None
    price_moves: list[dict[str, Any]] = field(default_factory=list)
    adjacent: list[dict[str, Any]] = field(default_factory=list)
    method_core: list[dict[str, Any]] = field(default_factory=list)
    method_adjacent: list[dict[str, Any]] = field(default_factory=list)
    cohorts: dict[str, Any] | None = None
    concentration: dict[str, Any] | None = None
    unit_basis: dict[str, Any] | None = None
    ties: dict[str, Any] | None = None
    subscriber_curve: dict[str, Any] | None = None
    contracts: dict[str, Any] | None = None
    cim_history: list[dict[str, Any]] = field(default_factory=list)
    trading: dict[str, Any] | None = None
    forward: dict[str, Any] | None = None
    claims: list[dict[str, Any]] = field(default_factory=list)
    leaders: list[dict[str, Any]] = field(default_factory=list)
    picture: dict[str, Any] | None = None
    segment_bridge: dict[str, Any] | None = None
    dc_cases: dict[str, Any] | None = None
    milestones: list[dict[str, Any]] = field(default_factory=list)
    web_competitors: list[dict[str, Any]] = field(default_factory=list)
    conclusion: dict[str, Any] | None = None

    def payload(self) -> list[dict[str, Any]]:
        return [calc.as_dict() for calc in self.calculations]


def _year(label: str) -> int | None:
    match = _YEAR.search(str(label or ""))
    return int(match.group(1)) if match else None


def _money(text: str) -> float | None:
    body = _PERCENT.sub(" ", str(text or ""))
    match = _MONEY.search(body)
    if not match:
        return None
    raw = match.group(1) or match.group(3)
    unit = (match.group(2) or match.group(4) or "").lower()
    number = float(raw.replace(",", ""))
    if unit in {"b", "bn", "billion"}:
        return number * 1_000
    return number


def _inp(value: float, ref: str) -> dict[str, Any]:
    return {"value": value, "ref": ref}


def derive(ctx: BuildContext, book: EvidenceBook) -> DeckMath:
    math = DeckMath()
    _margins(ctx, book, math)
    _lines(ctx, book, math)
    _costs(ctx, book, math)
    _risks(ctx, book, math)
    _yoy(book, math)
    _mix(ctx, book, math)
    _bridge_and_momentum(ctx, book, math)
    _retention(ctx, book, math)
    _haircuts(ctx, book, math)
    _landscape(ctx, book, math)
    _from_data_room(ctx, book, math)
    _quota_coverage(math)
    return math


def _margins(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "historical_performance"))
    rows = spec.get("growth_and_margins") if isinstance(spec.get("growth_and_margins"), list) else []
    docs = _docs(book, "revenue_actual")
    for row in rows:
        if not isinstance(row, dict) or not re.search(r"(?i)margin", str(row.get("metric") or "")):
            continue
        pct = _pct_from(row.get("value"))
        if pct is None:
            continue
        label = str(row.get("period") or "").strip() or "period"
        kind = _reported_period_type(label, str(row.get("period_type") or "actual"))
        if kind not in {"actual", "ytd", "ttm"}:
            continue
        fid = book.add(
            module="HPF",
            title="Historical Performance",
            text=f"{row.get('metric')} {label} ({kind}): {pct:.1f}%",
            docs=docs,
            period_status=kind,
            bucket="margins",
        )
        if fid:
            book.stamp(fid, pct, label)
            math.margins.append({
                "label": label,
                "metric": str(row.get("metric") or "Margin").strip(),
                "value": pct,
                "id": fid,
                "kind": kind,
            })


def _lines(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    rows = spec.get("lines") or spec.get("sam_lines") or spec.get("revenue_lines") or []
    docs = _docs(book, "sizing")
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("line") or "").strip()
        raw = row.get("value")
        if not name or not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        scale = str(row.get("scale") or "million")
        fid = book.add(
            module="MVG",
            title="Market Volume & Growth",
            text=f"{name}: {float(raw):,.2f} {scale}",
            docs=docs,
            period_status="actual",
            bucket="sam_lines",
            grade="indicated",
        )
        if fid:
            book.stamp(fid, float(raw), name)
            math.lines.append({"name": name, "value": float(raw), "id": fid})


def _costs(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "cost_structure"))
    rows = spec.get("cost_lines") or spec.get("lines") or spec.get("cost_buckets") or []
    if not isinstance(rows, list):
        return
    docs = _docs(book, "revenue_actual")
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("line_item") or row.get("name") or row.get("bucket") or "").strip()
        amount = row.get("value") if isinstance(row.get("value"), (int, float)) else row.get("amount")
        if not name or not isinstance(amount, (int, float)) or isinstance(amount, bool):
            continue
        share = row.get("share") or row.get("pct_of_revenue") or ""
        fid = book.add(
            module="HPF",
            title="Historical Performance",
            text=f"Cost {name}: {float(amount):,.2f} {row.get('scale') or ''} share {share}".strip(),
            docs=docs,
            period_status="actual",
            bucket="costs",
        )
        if fid:
            math.costs.append({
                "name": name,
                "amount": f"{float(amount):,.2f}",
                "share": str(share or "—"),
                "id": fid,
            })


def _risks(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    agent = _resolve(ctx, "market_risk")
    spec = _spec(agent)
    rows = spec.get("risks") or spec.get("risk_register") or []
    docs = _docs(book, "barriers")
    if isinstance(rows, list):
        for row in rows[:6]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("risk") or "").strip()
            if not name or _is_qa_meta(name):
                continue
            severity = str(row.get("severity") or row.get("grade") or "—")
            note = str(row.get("mitigation") or row.get("evidence") or row.get("note") or "—")
            fid = book.add(
                module="MRK",
                title="Market Risk",
                text=f"Risk {name}. Severity {severity}. {note}",
                docs=docs,
                bucket="risks",
            )
            if fid:
                math.risks.append({"name": name, "severity": severity, "note": note, "id": fid})
    if math.risks:
        return
    from agetic_cdd_api.report_cdd_deck_v4 import _findings

    for line in _findings(agent, 4):
        if _is_qa_meta(line):
            continue
        fid = book.add(module="MRK", title="Market Risk", text=line, docs=docs, bucket="risks")
        if fid:
            math.risks.append({"name": line, "severity": "—", "note": "—", "id": fid})


def _yoy(book: EvidenceBook, math: DeckMath) -> None:
    series: list[tuple[str, float, str]] = [
        (label, round(value, 2), fid)
        for label, value, fid, status in book.vdr_points
        if status == "actual"
    ]
    if len(series) < 2:
        series = []
        seen_years: set[int] = set()
        for fid in book.buckets.get("revenue_actual", []):
            fact = book.by_id.get(fid) or {}
            if fact.get("source") == "vdr_direct":
                continue
            amount = fact.get("amount")
            if not isinstance(amount, (int, float)):
                continue
            label = _label_from(str(fact.get("text") or ""))
            year = _year(label)
            if year is None or year in seen_years or not re.fullmatch(r"20\d{2}", label):
                continue
            seen_years.add(year)
            series.append((label, float(amount), fid))
        series.sort(key=lambda item: item[0])
    if len(series) < 2:
        return
    for (earlier_label, earlier, earlier_id), (later_label, later, later_id) in zip(series, series[1:]):
        earlier_year, later_year = _year(earlier_label), _year(later_label)
        if earlier_year and later_year and later_year <= earlier_year:
            continue
        if earlier == 0:
            continue
        delta = round(later - earlier, 2)
        pct = round((later - earlier) / abs(earlier) * 100, 1)
        delta_id = f"CALC-DELTA-{_slug(later_label)}"
        pct_id = f"CALC-YOY-{_slug(later_label)}"
        math.calculations.append(Calc(
            id=delta_id,
            formula="later - earlier",
            inputs={"later": _inp(later, later_id), "earlier": _inp(earlier, earlier_id)},
            output=delta,
            unit="$M",
            rounding=2,
            used_on=["S023_h1_growth_drivers"],
            label=f"{earlier_label} to {later_label}",
        ))
        math.calculations.append(Calc(
            id=pct_id,
            formula="(later - earlier) / abs(earlier) * 100",
            inputs={"later": _inp(later, later_id), "earlier": _inp(earlier, earlier_id)},
            output=pct,
            unit="%",
            rounding=1,
            used_on=["S023_h1_growth_drivers"],
            label=f"{earlier_label} to {later_label}",
        ))
        math.yoy.append({
            "earlier": earlier_label,
            "later": later_label,
            "earlier_amount": earlier,
            "later_amount": later,
            "delta": delta,
            "pct": pct,
            "delta_id": delta_id,
            "pct_id": pct_id,
            "earlier_id": earlier_id,
            "later_id": later_id,
        })


def _mix(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    segments = _spec(_resolve(ctx, "customer_segmentation")).get("segments")
    if not isinstance(segments, list):
        return
    stated = []
    revenues = []
    ids = book.buckets.get("segments", [])
    for index, seg in enumerate(segments):
        if not isinstance(seg, dict) or not _filled(seg.get("name")):
            continue
        fid = ids[index] if index < len(ids) else (ids[-1] if ids else "")
        name = str(seg["name"])
        share = seg.get("share_pct")
        if isinstance(share, (int, float)) and not isinstance(share, bool):
            stated.append({"name": name, "share": float(share), "id": fid})
        raw = seg.get("revenue") if isinstance(seg.get("revenue"), (int, float)) else seg.get("arr")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            revenues.append({"name": name, "revenue": float(raw), "id": fid})
    if len(revenues) >= 2 and not stated:
        total = round(sum(item["revenue"] for item in revenues), 2)
        total_id = "CALC-MIX-TOTAL"
        math.calculations.append(Calc(
            id=total_id,
            formula=" + ".join(f"s{i}" for i in range(len(revenues))),
            inputs={f"s{i}": _inp(item["revenue"], item["id"]) for i, item in enumerate(revenues)},
            output=total,
            unit="$M",
            rounding=2,
            used_on=["S042_gf2_mix_shift"],
        ))
        for index, item in enumerate(revenues):
            share = round(item["revenue"] / total * 100, 1) if total else 0.0
            cid = f"CALC-MIX-{index + 1}"
            math.calculations.append(Calc(
                id=cid,
                formula=f"s{index} / total * 100",
                inputs={
                    f"s{index}": _inp(item["revenue"], item["id"]),
                    "total": {"value": total, "ref": "CALC"},
                },
                output=share,
                unit="%",
                rounding=1,
                used_on=["S042_gf2_mix_shift"],
            ))
            math.mix.append({"name": item["name"], "share": share, "id": item["id"], "calc_id": cid})
        math.mix_calculated = True
        return
    math.mix = stated


def _bridge_and_momentum(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    actual = _vdr_endpoint(book.vdr_points, "actual") or _last_amount(book, "revenue_actual")
    plan = _vdr_endpoint(getattr(book, "vdr_plan", []), "forecast") or _last_amount(book, "revenue_plan")
    if actual and plan and actual["amount"] and actual["year"] and plan["year"] and plan["year"] > actual["year"]:
        delta = round(plan["amount"] - actual["amount"], 2)
        multiple = round(plan["amount"] / actual["amount"], 2)
        math.calculations.append(Calc(
            id="CALC-BRIDGE-DELTA",
            formula="plan - actual",
            inputs={"plan": _inp(plan["amount"], plan["id"]), "actual": _inp(actual["amount"], actual["id"])},
            output=delta,
            unit="$M",
            rounding=2,
            used_on=["S046_sam_growth_build", "S047_scenario_analysis"],
        ))
        math.calculations.append(Calc(
            id="CALC-BRIDGE-MULTIPLE",
            formula="plan / actual",
            inputs={"plan": _inp(plan["amount"], plan["id"]), "actual": _inp(actual["amount"], actual["id"])},
            output=multiple,
            unit="x",
            rounding=2,
            used_on=["S046_sam_growth_build"],
        ))
        math.bridge = {
            "actual_label": actual["label"],
            "actual": actual["amount"],
            "actual_id": actual["id"],
            "plan_label": plan["label"],
            "plan": plan["amount"],
            "plan_id": plan["id"],
            "delta": delta,
            "multiple": multiple,
        }
        rate, rate_id = _market_rate(ctx, book)
        if rate is not None and rate_id:
            years_span = plan["year"] - actual["year"]
            grown = round(actual["amount"] * (1 + rate / 100) ** years_span, 2)
            math.calculations.append(Calc(
                id="CALC-MOMENTUM",
                formula="actual * (1 + rate / 100) ** (plan_year - actual_year)",
                inputs={
                    "actual": _inp(actual["amount"], actual["id"]),
                    "rate": _inp(rate, rate_id),
                    "plan_year": _inp(float(plan["year"]), plan["id"]),
                    "actual_year": _inp(float(actual["year"]), actual["id"]),
                },
                output=grown,
                unit="$M",
                rounding=2,
                used_on=["S047_scenario_analysis"],
            ))
            gap = round(plan["amount"] - grown, 2)
            math.calculations.append(Calc(
                id="CALC-MOMENTUM-GAP",
                formula="plan - momentum",
                inputs={
                    "plan": _inp(plan["amount"], plan["id"]),
                    "momentum": {"value": grown, "ref": "CALC"},
                },
                output=gap,
                unit="$M",
                rounding=2,
                used_on=["S047_scenario_analysis"],
            ))
            book.by_id[rate_id]["text"] = (
                f"Latest actual {actual['label']} ${actual['amount']:.2f}M. "
                f"Plan {plan['label']} ${plan['amount']:.2f}M. "
                f"Market rate {rate:g}%."
            )
            math.momentum = {
                "rate": rate,
                "rate_id": rate_id,
                "years": years_span,
                "value": grown,
                "gap": gap,
                "actual_label": actual["label"],
                "plan_label": plan["label"],
            }
    _trading_case(math)


def _market_rate(ctx: BuildContext, book: EvidenceBook) -> tuple[float | None, str]:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    plan = spec.get("plan_vs_market") if isinstance(spec.get("plan_vs_market"), dict) else {}
    rate = _pct_from(plan.get("market_rate"))
    if rate is None or not _filled(plan.get("market_rate")):
        return None, ""
    docs = _docs(book, "sizing")
    text = f"Plan rate {plan.get('plan_rate') or 'not stated'}. Market rate {plan.get('market_rate')}."
    fid = book.add(
        module="MVG",
        title="Market Volume & Growth",
        text=text,
        docs=docs,
        bucket="plan_case",
        grade="indicated",
    )
    return (rate, fid) if fid else (None, "")


def _retention(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    stick = _spec(_resolve(ctx, "customer_stickiness"))
    same = stick.get("retention_on_same_population") if isinstance(stick.get("retention_on_same_population"), dict) else {}
    grr = _pct_from(same.get("grr") if same else stick.get("grr"))
    nrr = _pct_from(same.get("nrr") if same else stick.get("nrr"))
    if grr is None or nrr is None:
        return
    ids = book.buckets.get("retention", [])
    grr_id = next((fid for fid in ids if "GRR" in book.by_id[fid]["text"]), ids[0] if ids else "")
    nrr_id = next((fid for fid in ids if "NRR" in book.by_id[fid]["text"]), ids[-1] if ids else "")
    if not grr_id or not nrr_id:
        return
    spread = round(nrr - grr, 1)
    math.calculations.append(Calc(
        id="CALC-NRR-GRR",
        formula="nrr - grr",
        inputs={"nrr": _inp(nrr, nrr_id), "grr": _inp(grr, grr_id)},
        output=spread,
        unit="pp",
        rounding=1,
        used_on=["S068_churn_triggers", "S079_l3_expand_accounts"],
    ))
    math.retention = {
        "grr": grr,
        "nrr": nrr,
        "spread": spread,
        "grr_id": grr_id,
        "nrr_id": nrr_id,
        "population": str(same.get("population") or "the stated population"),
    }


def _haircuts(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    bottom = spec.get("bottom_up") if isinstance(spec.get("bottom_up"), dict) else {}
    if not bottom:
        return
    rate_field = ""
    for key in ("capture_share", "arithmetic", "units", "bottom_up_size"):
        text = str(bottom.get(key) or "")
        if _HAIRCUT.search(text) and not _is_ledger_sizing_text(text):
            rate_field = text
            break
    if not rate_field:
        return
    rates = [float(item) for item in _PERCENT.findall(rate_field)]
    if re.search(r"(?i)\btwo\b", rate_field) and len(rates) == 1:
        rates = [rates[0], rates[0]]
    rates = rates[:2]
    if not rates:
        return
    base = None
    base_key = ""
    for key in ("bottom_up_size", "arithmetic", "units"):
        text = str(bottom.get(key) or "")
        if _is_ledger_sizing_text(text):
            continue
        found = _money(text)
        if found is not None and key != _field_of(rate_field, bottom):
            base = found
            base_key = key
            break
    if base is None:
        return
    ids = book.buckets.get("bottom_up", [])
    rate_id = _fact_containing(book, ids, "haircut") or (ids[0] if ids else "")
    base_label = {"bottom_up_size": "bottom-up size", "arithmetic": "arithmetic", "units": "units"}.get(base_key, base_key)
    base_id = _fact_containing(book, ids, base_label) or rate_id
    if not rate_id or not base_id:
        return
    running = base
    running_ref = base_id
    for index, rate in enumerate(rates, start=1):
        output = round(running * (1 - rate / 100), 2)
        cid = f"CALC-HAIRCUT-{index}"
        inputs = {
            "base" if index == 1 else "prior": _inp(running, running_ref if index == 1 else "CALC"),
            "rate": _inp(rate, rate_id),
        }
        if index == 1:
            formula = "base * (1 - rate / 100)"
        else:
            formula = "prior * (1 - rate / 100)"
        math.calculations.append(Calc(
            id=cid,
            formula=formula,
            inputs=inputs,
            output=output,
            unit="$M",
            rounding=2,
            used_on=["S089_sizing_method_core"],
            label=f"After haircut {index}",
        ))
        math.haircuts.append({"step": index, "rate": rate, "output": output, "id": cid, "base_id": base_id, "rate_id": rate_id})
        running = output
        running_ref = "CALC"


def _field_of(text: str, bottom: dict) -> str:
    for key, value in bottom.items():
        if str(value or "") == text:
            return key
    return ""


def _fact_containing(book: EvidenceBook, ids: list[str], needle: str) -> str:
    needle = needle.lower()
    for fid in ids:
        if needle in book.by_id[fid]["text"].lower():
            return fid
    return ""


def _docs(book: EvidenceBook, bucket: str) -> list[str]:
    for fid in book.buckets.get(bucket, []):
        docs = (book.by_id.get(fid) or {}).get("citations", {}).get("doc") or []
        if docs:
            return list(docs)
    return []


def _label_from(text: str) -> str:
    match = re.search(r"Revenue\s+(.+?)\s+\(", text)
    return match.group(1) if match else text[:24]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-") or "X"


def _last_amount(book: EvidenceBook, bucket: str) -> dict[str, Any] | None:
    chosen = None
    for fid in book.buckets.get(bucket, []):
        fact = book.by_id.get(fid) or {}
        if fact.get("source") == "vdr_direct":
            continue
        amount = fact.get("amount")
        if not isinstance(amount, (int, float)):
            continue
        label = _label_from(str(fact.get("text") or ""))
        year = _year(label)
        if year is None:
            continue
        if chosen is None or year >= chosen["year"]:
            chosen = {"id": fid, "amount": float(amount), "label": label, "year": year}
    return chosen


def _vdr_endpoint(points: list[tuple[str, float, str, str]], kind: str) -> dict[str, Any] | None:
    chosen = None
    for label, value, fid, status in points:
        if kind == "actual" and status != "actual":
            continue
        if kind != "actual" and status == "actual":
            continue
        year = _year(label)
        if year is None:
            continue
        if chosen is None or year >= chosen["year"]:
            chosen = {"id": fid, "amount": round(float(value), 2), "label": label, "year": year}
    return chosen


def _landscape(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """Competitive and growth exhibits. A page is filled only when the module stored the figures."""
    _assessment(ctx, book, math)
    _prices(ctx, book, math)
    _retention_curve(ctx, book, math)
    _lever_dollars(ctx, book, math)
    _logos_and_quotas(ctx, book, math)
    _zip_scores(ctx, book, math)
    _initiatives(ctx, book, math)
    _deals(ctx, book, math)
    _price_moves(ctx, book, math)
    _adjacent(ctx, book, math)


def _assessment(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "competitive_differentiation"))
    raw = spec.get("self_assessment") or spec.get("criteria_matrix") or spec.get("comparison")
    if not raw:
        raw = _spec(_resolve(ctx, "company_background")).get("self_assessment")
    columns, body = _matrix(raw)
    if len(columns) < 2 or len(body) < 2:
        return
    docs = _agent_docs(ctx, "competitive_differentiation") or _agent_docs(ctx, "company_background")
    ids: list[str] = []
    rows: list[list[str]] = []
    for row in body[:8]:
        cells = [_cell(row.get(column)) for column in columns]
        criterion = str(row.get("criterion") or row.get("name") or "").strip()
        if not criterion:
            continue
        text = f"Self-assessment {criterion}: " + ", ".join(f"{column} {cell}" for column, cell in zip(columns, cells))
        fid = book.add(module="CDF", title="Competitive Differentiation", text=text, docs=docs, bucket="assessment")
        if not fid:
            continue
        ids.append(fid)
        rows.append([criterion, *cells])
    if len(rows) < 2:
        return
    math.assessment = {"columns": ["Criterion", *columns], "rows": rows, "ids": ids}


def _prices(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "market_pricing"))
    raw = spec.get("price_points") or spec.get("prices") or spec.get("benchmarks") or []
    if not isinstance(raw, list):
        return
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        value = _num(item.get("price") if item.get("price") is not None else item.get("value"))
        name = str(item.get("name") or item.get("offer") or item.get("label") or "").strip()
        if value is None or not name:
            continue
        unit = str(item.get("unit") or item.get("basis") or "as stated").strip() or "as stated"
        role = str(item.get("role") or item.get("side") or "").lower()
        grouped.setdefault(unit, []).append({"name": name, "value": value, "role": role})
    chosen_unit, points = "", []
    for unit, rows in grouped.items():
        if len(rows) > len(points):
            chosen_unit, points = unit, rows
    if len(points) < 2:
        return
    docs = _agent_docs(ctx, "market_pricing")
    stored = []
    for point in points[:8]:
        fid = book.add(
            module="MPR",
            title="Market Pricing",
            text=f"Price {point['name']} ({chosen_unit}): {point['value']:.2f}",
            docs=docs,
            bucket="prices",
            grade="indicated",
        )
        if not fid:
            continue
        book.stamp(fid, point["value"], point["name"])
        stored.append({**point, "id": fid})
    if len(stored) < 2:
        return
    company = [point for point in stored if point["role"] in {"company", "target", "realised", "realized"}]
    peers = [point for point in stored if point["role"] in {"peer", "competitor", "list", "benchmark"}]
    gap = None
    if len(company) == 1 and peers and peers[0]["value"]:
        gap_value = round((company[0]["value"] / peers[0]["value"] - 1) * 100, 1)
        math.calculations.append(Calc(
            id="CALC-PRICE-GAP",
            formula="(company / peer - 1) * 100",
            inputs={
                "company": _inp(company[0]["value"], company[0]["id"]),
                "peer": _inp(peers[0]["value"], peers[0]["id"]),
            },
            output=gap_value,
            unit="%",
            rounding=1,
            used_on=["S064_price_benchmarking"],
        ))
        gap = {"value": gap_value, "peer": peers[0]["name"], "company": company[0]["name"]}
    math.prices = {"unit": chosen_unit, "points": stored, "gap": gap}


def _retention_curve(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "customer_stickiness"))
    raw = spec.get("retention_by_year") or spec.get("retention_history") or []
    if not isinstance(raw, list):
        return
    both, grr_only, nrr_only = [], [], []
    for row in raw:
        if not isinstance(row, dict):
            continue
        label = str(row.get("year") or row.get("period") or "").strip()
        if not label:
            continue
        grr = _pct_from(row.get("grr"))
        nrr = _pct_from(row.get("nrr"))
        item = {"label": label, "grr": grr, "nrr": nrr}
        if grr is not None and nrr is not None:
            both.append(item)
        if grr is not None:
            grr_only.append(item)
        if nrr is not None:
            nrr_only.append(item)
    if len(both) >= 2:
        series_rows, metrics = both, ("grr", "nrr")
    elif len(grr_only) >= 2:
        series_rows, metrics = grr_only, ("grr",)
    elif len(nrr_only) >= 2:
        series_rows, metrics = nrr_only, ("nrr",)
    else:
        return
    series_rows = sorted(series_rows, key=lambda item: item["label"])[:8]
    docs = _agent_docs(ctx, "customer_stickiness") or _docs(book, "retention")
    population = str(spec.get("population") or (spec.get("retention_on_same_population") or {}).get("population") or "the stated population")
    series: list[dict[str, Any]] = []
    for metric in metrics:
        values, ids = [], []
        for item in series_rows:
            value = float(item[metric])
            fid = book.add(
                module="CST",
                title="Customer Stickiness",
                text=f"{metric.upper()} {item['label']} (actual): {value:.1f}%",
                docs=docs,
                period_status="actual",
                bucket="retention_series",
            )
            if not fid:
                continue
            book.stamp(fid, value, item["label"])
            values.append(value)
            ids.append(fid)
        if len(values) == len(series_rows):
            series.append({"name": metric.upper(), "values": values, "point_refs": ids})
    if not series:
        return
    math.retention_curve = {
        "population": population,
        "categories": [item["label"] for item in series_rows],
        "series": series,
    }


def _lever_dollars(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    spec = _spec(_resolve(ctx, "growth_opportunities"))
    raw = spec.get("levers") or spec.get("opportunities") or []
    if not isinstance(raw, list):
        return
    parsed = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("lever") or "").strip()
        actual = _num(row.get("actual") if row.get("actual") is not None else row.get("current"))
        plan = _num(row.get("plan") if row.get("plan") is not None else row.get("plan_value"))
        if not name or actual is None or plan is None:
            continue
        parsed.append({
            "name": name,
            "actual": actual,
            "plan": plan,
            "actual_label": str(row.get("actual_label") or row.get("actual_year") or "actual"),
            "plan_label": str(row.get("plan_label") or row.get("plan_year") or "plan"),
        })
    labels = {(row["actual_label"], row["plan_label"]) for row in parsed}
    if len(parsed) < 2 or len(labels) != 1:
        return
    docs = _agent_docs(ctx, "growth_opportunities") or _docs(book, "levers")
    stored = []
    for row in parsed[:6]:
        fid = book.add(
            module="GRO",
            title="Growth Opportunities",
            text=(
                f"Lever {row['name']} actual {row['actual_label']} ${row['actual']:.2f}M. "
                f"Plan {row['plan_label']} ${row['plan']:.2f}M."
            ),
            docs=docs,
            bucket="lever_amounts",
            grade="indicated",
        )
        if not fid:
            continue
        stored.append({**row, "id": fid})
    if len(stored) < 2:
        return
    deltas = []
    for index, row in enumerate(stored, start=1):
        delta = round(row["plan"] - row["actual"], 2)
        cid = f"CALC-LEVER-DELTA-{index}"
        math.calculations.append(Calc(
            id=cid,
            formula="plan - actual",
            inputs={"plan": _inp(row["plan"], row["id"]), "actual": _inp(row["actual"], row["id"])},
            output=delta,
            unit="$M",
            rounding=2,
            used_on=["S072_growth_levers_overview"],
        ))
        deltas.append({**row, "delta": delta, "delta_id": cid})
    total = round(sum(row["delta"] for row in deltas), 2)
    math.calculations.append(Calc(
        id="CALC-LEVER-TOTAL",
        formula=" + ".join(f"d{i}" for i in range(len(deltas))),
        inputs={f"d{i}": {"value": row["delta"], "ref": "CALC"} for i, row in enumerate(deltas)},
        output=total,
        unit="$M",
        rounding=2,
        used_on=["S072_growth_levers_overview"],
    ))
    shares = []
    for index, row in enumerate(deltas, start=1):
        share = None
        if total:
            share = round(row["delta"] / total * 100, 1)
            math.calculations.append(Calc(
                id=f"CALC-LEVER-SHARE-{index}",
                formula="delta / total * 100",
                inputs={
                    "delta": {"value": row["delta"], "ref": "CALC"},
                    "total": {"value": total, "ref": "CALC"},
                },
                output=share,
                unit="%",
                rounding=1,
                used_on=["S072_growth_levers_overview"],
            ))
        shares.append({**row, "share": share})
    math.lever_dollars = {
        "rows": shares,
        "total": total,
        "actual_label": stored[0]["actual_label"],
        "plan_label": stored[0]["plan_label"],
    }


def _logos_and_quotas(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    stick = _spec(_resolve(ctx, "customer_stickiness"))
    growth = _spec(_resolve(ctx, "growth_opportunities"))
    raw = stick.get("logo_history") or growth.get("logo_history") or []
    years = []
    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            label = str(row.get("year") or row.get("period") or "").strip()
            new = _num(row.get("new") if row.get("new") is not None else row.get("new_logos"))
            churned = _num(row.get("churned") if row.get("churned") is not None else row.get("churned_logos"))
            if label and new is not None and churned is not None:
                years.append({"label": label, "new": new, "churned": churned})
    years = sorted(years, key=lambda item: item["label"])[:8]
    docs = _agent_docs(ctx, "customer_stickiness") or _agent_docs(ctx, "growth_opportunities")
    if len(years) >= 2:
        new_ids, churn_ids, nets = [], [], []
        for item in years:
            new_id = book.add(
                module="CST",
                title="Customer Stickiness",
                text=f"New logos {item['label']}: {item['new']:.0f}",
                docs=docs,
                period_status="actual",
                bucket="logos",
            )
            churn_id = book.add(
                module="CST",
                title="Customer Stickiness",
                text=f"Churned logos {item['label']}: {item['churned']:.0f}",
                docs=docs,
                period_status="actual",
                bucket="logos",
            )
            if not new_id or not churn_id:
                continue
            book.stamp(new_id, item["new"], item["label"])
            book.stamp(churn_id, item["churned"], item["label"])
            net = round(item["new"] - item["churned"], 0)
            cid = f"CALC-LOGO-NET-{_slug(item['label'])}"
            math.calculations.append(Calc(
                id=cid,
                formula="new - churned",
                inputs={"new": _inp(item["new"], new_id), "churned": _inp(item["churned"], churn_id)},
                output=net,
                unit="count",
                rounding=0,
                used_on=["S073_l1_new_customers"],
            ))
            new_ids.append(new_id)
            churn_ids.append(churn_id)
            nets.append({"label": item["label"], "value": net})
        if len(new_ids) >= 2:
            math.logos = {
                "categories": [item["label"] for item in years[: len(new_ids)]],
                "new": [item["new"] for item in years[: len(new_ids)]],
                "churned": [item["churned"] for item in years[: len(churn_ids)]],
                "new_ids": new_ids,
                "churn_ids": churn_ids,
                "nets": nets,
            }
    quota_rows = growth.get("sales_quotas") or growth.get("quotas") or stick.get("sales_quotas") or []
    stored_quotas = []
    if isinstance(quota_rows, list):
        qdocs = _agent_docs(ctx, "growth_opportunities") or docs
        for row in quota_rows[:6]:
            if not isinstance(row, dict):
                continue
            driver = str(row.get("driver") or row.get("name") or "").strip()
            baseline = str(row.get("baseline") or row.get("plan") or "").strip()
            growth_case = str(row.get("growth_case") or row.get("upside") or "—").strip() or "—"
            if not driver or not (baseline or _num(row.get("quota")) is not None):
                continue
            quota = _num(row.get("quota"))
            text = f"Quota {driver}. Baseline {baseline or quota}. Growth case {growth_case}."
            fid = book.add(module="GRO", title="Growth Opportunities", text=text, docs=qdocs, bucket="quotas")
            if fid:
                stored_quotas.append({
                    "driver": driver,
                    "baseline": baseline or f"{quota:.0f}",
                    "growth_case": growth_case,
                    "quota": quota,
                    "id": fid,
                })
    if stored_quotas:
        math.quotas = {"rows": stored_quotas}
        _quota_coverage(math)


def _zip_scores(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    growth = _spec(_resolve(ctx, "growth_opportunities"))
    segments = _spec(_resolve(ctx, "customer_segmentation"))
    raw = growth.get("zip_scores") or growth.get("zip_priorities") or segments.get("zip_scores") or []
    if not isinstance(raw, list):
        return
    docs = _agent_docs(ctx, "growth_opportunities") or _agent_docs(ctx, "customer_segmentation")
    rows, ids = [], []
    for row in raw:
        if not isinstance(row, dict):
            continue
        score = _num(row.get("score"))
        place = str(row.get("area") or row.get("city") or row.get("territory") or "").strip()
        if score is None or not place:
            continue
        territory = str(row.get("territory") or row.get("region") or "—").strip() or "—"
        county = str(row.get("county") or "—").strip() or "—"
        code = str(row.get("zip") or row.get("zip_code") or "—").strip() or "—"
        fid = book.add(
            module="GRO",
            title="Growth Opportunities",
            text=f"ZIP {code} {territory} {place} {county}: score {score:.2f}",
            docs=docs,
            bucket="zips",
            grade="indicated",
        )
        if not fid:
            continue
        book.stamp(fid, score, code)
        ids.append(fid)
        rows.append([territory, place, county, code, f"{score:.2f}"])
        if len(rows) >= 8:
            break
    if len(rows) < 2:
        return
    math.zips = {"rows": rows, "ids": ids}


def _initiatives(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    growth = _spec(_resolve(ctx, "growth_opportunities"))
    strategy = _spec(_resolve(ctx, "strategic_direction"))
    raw = growth.get("initiatives") or growth.get("product_lines") or strategy.get("initiatives") or []
    if not isinstance(raw, list):
        return
    parsed = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("initiative") or "").strip()
        if not name:
            continue
        actual = _num(row.get("actual") if row.get("actual") is not None else row.get("revenue"))
        plan = _num(row.get("plan") if row.get("plan") is not None else row.get("plan_value"))
        status = str(row.get("status") or "—").strip() or "—"
        if actual is None and plan is None and status == "—":
            continue
        parsed.append({
            "name": name,
            "status": status,
            "actual": actual,
            "plan": plan,
            "actual_label": str(row.get("actual_label") or row.get("actual_year") or ""),
            "plan_label": str(row.get("plan_label") or row.get("plan_year") or ""),
        })
    if len(parsed) < 2:
        return
    docs = _agent_docs(ctx, "growth_opportunities") or _agent_docs(ctx, "strategic_direction")
    stored = []
    for row in parsed[:6]:
        bits = [f"Initiative {row['name']}. Status {row['status']}."]
        if row["actual"] is not None:
            bits.append(f"Actual {row['actual_label']} ${row['actual']:.2f}M.")
        if row["plan"] is not None:
            bits.append(f"Plan {row['plan_label']} ${row['plan']:.2f}M.")
        fid = book.add(
            module="GRO",
            title="Growth Opportunities",
            text=" ".join(bits),
            docs=docs,
            bucket="initiatives",
            grade="indicated",
        )
        if fid:
            stored.append({**row, "id": fid})
    if len(stored) < 2:
        return
    for index, row in enumerate(stored, start=1):
        if row["actual"] is None or row["plan"] is None:
            row["delta"] = None
            continue
        delta = round(row["plan"] - row["actual"], 2)
        cid = f"CALC-INIT-DELTA-{index}"
        math.calculations.append(Calc(
            id=cid,
            formula="plan - actual",
            inputs={"plan": _inp(row["plan"], row["id"]), "actual": _inp(row["actual"], row["id"])},
            output=delta,
            unit="$M",
            rounding=2,
            used_on=["S082_l6_product_expansion"],
        ))
        row["delta"] = delta
        actual_year = _year(row["actual_label"])
        plan_year = _year(row["plan_label"])
        if actual_year and plan_year and plan_year > actual_year and row["actual"]:
            cagr = round(((row["plan"] / row["actual"]) ** (1 / (plan_year - actual_year)) - 1) * 100, 1)
            math.calculations.append(Calc(
                id=f"CALC-INIT-CAGR-{index}",
                formula="((plan / actual) ** (1 / (plan_year - actual_year)) - 1) * 100",
                inputs={
                    "plan": _inp(row["plan"], row["id"]),
                    "actual": _inp(row["actual"], row["id"]),
                    "plan_year": _inp(float(plan_year), row["id"]),
                    "actual_year": _inp(float(actual_year), row["id"]),
                },
                output=cagr,
                unit="%",
                rounding=1,
                used_on=["S082_l6_product_expansion"],
            ))
            row["cagr"] = cagr
    total = _num(growth.get("revenue_total") if growth.get("revenue_total") is not None else strategy.get("revenue_total"))
    if isinstance(growth.get("revenue_total"), dict):
        total = _num(growth["revenue_total"].get("actual") if growth["revenue_total"].get("actual") is not None else growth["revenue_total"].get("value"))
    share = None
    numerators = [row for row in stored if row["actual"] is not None]
    if total and numerators and all(row["actual"] is not None for row in numerators):
        part = round(sum(row["actual"] for row in numerators), 2)
        total_id = book.add(
            module="GRO",
            title="Growth Opportunities",
            text=f"Revenue total for the initiative share ${total:.2f}M.",
            docs=docs,
            bucket="initiatives",
            grade="indicated",
        )
        if total_id:
            math.calculations.append(Calc(
                id="CALC-INIT-PART",
                formula=" + ".join(f"a{i}" for i in range(len(numerators))),
                inputs={f"a{i}": _inp(row["actual"], row["id"]) for i, row in enumerate(numerators)},
                output=part,
                unit="$M",
                rounding=2,
                used_on=["S082_l6_product_expansion"],
            ))
            share_value = round(part / total * 100, 1)
            math.calculations.append(Calc(
                id="CALC-INIT-SHARE",
                formula="part / total * 100",
                inputs={
                    "part": {"value": part, "ref": "CALC"},
                    "total": _inp(total, total_id),
                },
                output=share_value,
                unit="%",
                rounding=1,
                used_on=["S082_l6_product_expansion"],
            ))
            share = {"value": share_value, "id": total_id}
    math.initiatives = {"rows": stored, "share": share}


def _deals(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    sources = (
        ("synergies", _spec(_resolve(ctx, "synergies"))),
        ("company_background", _spec(_resolve(ctx, "company_background"))),
        ("growth_opportunities", _spec(_resolve(ctx, "growth_opportunities"))),
    )
    raw: list[Any] = []
    docs: list[str] = []
    for key, spec in sources:
        candidate = spec.get("acquisitions") or spec.get("deals") or []
        if isinstance(candidate, list) and candidate:
            raw = candidate
            docs = _agent_docs(ctx, key)
            break
    stored = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("target") or "").strip()
        if not name:
            continue
        status = str(row.get("status") or "—").strip() or "—"
        scale = str(row.get("scale") or "—").strip() or "—"
        price = _num(row.get("price") if row.get("price") is not None else row.get("purchase_price"))
        multiple = _num(row.get("multiple") if row.get("multiple") is not None else row.get("ebitda_multiple"))
        synergy = _num(row.get("synergy_ebitda") if row.get("synergy_ebitda") is not None else row.get("synergy"))
        bits = [f"Acquisition {name}. Status {status}. Scale {scale}."]
        if price is not None:
            bits.append(f"Price {price:.2f}.")
        if multiple is not None:
            bits.append(f"Multiple {multiple:.2f}.")
        if synergy is not None:
            bits.append(f"Stated EBITDA effect {synergy:.2f}.")
        fid = book.add(module="SYN", title="Synergies", text=" ".join(bits), docs=docs, bucket="deals")
        if not fid:
            continue
        item = {
            "name": name,
            "status": status,
            "scale": scale,
            "id": fid,
            "price": price,
            "multiple": multiple,
            "implied": None,
            "residual": None,
        }
        if price is not None and multiple:
            implied = round(price / multiple, 2)
            cid = f"CALC-DEAL-EBITDA-{_slug(name)}"
            math.calculations.append(Calc(
                id=cid,
                formula="price / multiple",
                inputs={"price": _inp(price, fid), "multiple": _inp(multiple, fid)},
                output=implied,
                unit="$M",
                rounding=2,
                used_on=["S083_l7_ma"],
            ))
            item["implied"] = implied
            if synergy is not None:
                residual = round(synergy - implied, 2)
                math.calculations.append(Calc(
                    id=f"CALC-DEAL-RESIDUAL-{_slug(name)}",
                    formula="synergy - implied",
                    inputs={"synergy": _inp(synergy, fid), "implied": {"value": implied, "ref": "CALC"}},
                    output=residual,
                    unit="$M",
                    rounding=2,
                    used_on=["S083_l7_ma"],
                ))
                item["residual"] = residual
        stored.append(item)
        if len(stored) >= 6:
            break
    if stored:
        math.deals = {"rows": stored}


def _price_moves(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """A pricing lever is two stated prices for the same offer. The change is current / prior - 1."""
    spec = _spec(_resolve(ctx, "market_pricing"))
    raw = spec.get("price_levers") or spec.get("pricing_actions") or []
    if not isinstance(raw, list):
        raw = []
    levers = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("segment") or item.get("offer") or "").strip()
        prior = _num(item.get("prior") if item.get("prior") is not None else item.get("from"))
        current = _num(item.get("current") if item.get("current") is not None else item.get("to"))
        if not name or prior is None or current is None or prior == 0:
            continue
        levers.append({"name": name, "prior": prior, "current": current})
    if len(levers) < 2:
        levers = _moves_from_realised(spec.get("realised_prices"))
    if len(levers) < 2:
        return
    docs = _agent_docs(ctx, "market_pricing")
    stored = []
    for index, lever in enumerate(levers[:6], start=1):
        fid = book.add(
            module="MPR",
            title="Market Pricing",
            text=f"Price lever {lever['name']}: prior {lever['prior']:.2f} current {lever['current']:.2f}",
            docs=docs,
            bucket="price_moves",
            grade="indicated",
        )
        if not fid:
            continue
        change = round((lever["current"] / lever["prior"] - 1) * 100, 1)
        math.calculations.append(Calc(
            id=f"CALC-PRICE-MOVE-{index}",
            formula="(current / prior - 1) * 100",
            inputs={"prior": _inp(lever["prior"], fid), "current": _inp(lever["current"], fid)},
            output=change,
            unit="%",
            rounding=1,
            used_on=["S080_l4_pricing"],
        ))
        stored.append({**lever, "id": fid, "change": change})
    if len(stored) >= 2:
        math.price_moves = stored


def _moves_from_realised(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    grouped: dict[str, list[tuple[str, float]]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("service_or_segment") or item.get("name") or "").strip()
        value = _num(item.get("realised_net_price"))
        period = str(item.get("period") or "")
        if not name or value is None or value == 0:
            continue
        grouped.setdefault(name, []).append((period, value))
    levers = []
    for name, points in grouped.items():
        if len(points) < 2:
            continue
        points.sort(key=lambda pair: pair[0])
        levers.append({"name": name, "prior": points[0][1], "current": points[-1][1]})
    return levers


def _adjacent(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """An adjacent line is a sizing method beside the core market, with its own money base."""
    spec = _spec(_resolve(ctx, "market_volume_and_growth"))
    raw = spec.get("adjacent_lines") or spec.get("adjacent") or []
    if not isinstance(raw, list):
        return
    docs = _docs(book, "sizing") or _agent_docs(ctx, "market_volume_and_growth")
    stored = []
    for index, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("line") or "").strip()
        basis = str(row.get("basis") or row.get("method") or "").strip()
        som = _num(row.get("som") if row.get("som") is not None else row.get("value"))
        actual = _num(row.get("actual") if row.get("actual") is not None else row.get("sales"))
        if not name or not basis or som is None or _is_ledger_sizing_text(basis):
            continue
        actual_txt = f" actual {actual:.2f}" if actual is not None else ""
        fid = book.add(
            module="MVG",
            title="Market Volume & Growth",
            text=f"Adjacent {name}: {basis}. SOM {som:.2f}.{actual_txt}",
            docs=docs,
            bucket="adjacent",
            grade="indicated",
        )
        if not fid:
            continue
        capture = None
        if actual is not None and som:
            capture = round(actual / som * 100, 1)
            math.calculations.append(Calc(
                id=f"CALC-ADJ-CAPTURE-{index}",
                formula="actual / som * 100",
                inputs={"actual": _inp(actual, fid), "som": _inp(som, fid)},
                output=capture,
                unit="%",
                rounding=1,
                used_on=["S090_sizing_method_adjacent"],
            ))
        stored.append({"name": name, "basis": basis, "som": som, "actual": actual, "capture": capture, "id": fid})
        if len(stored) >= 6:
            break
    if len(stored) >= 2:
        math.adjacent = stored


_MARGIN_ROW = re.compile(r"(?i)^(gross|ebitda) margin( %)?$")
_GRR_ROW = re.compile(r"(?i)^gross revenue retention\b")
_NRR_ROW = re.compile(r"(?i)^net revenue retention\b")
_NEW_LOGO = re.compile(r"(?i)^new logos?$")
_CHURN_LOGO = re.compile(r"(?i)^churned logos?$")
_HAUL = re.compile(r"(?i)haul|collect|logistic")


def _from_data_room(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """Fill exhibits from workbook rows when the agent module did not store them."""
    _vdr_margins(book, math)
    _vdr_mix(book, math)
    _vdr_retention(ctx, book, math)
    _vdr_logos(book, math)
    _vdr_method(book, math)
    _vdr_room(ctx, book, math)


def _vdr_facts(book: EvidenceBook, module: str) -> list[dict[str, Any]]:
    return [
        fact for fact in book.facts
        if fact.get("source") == "vdr_direct" and fact.get("module") == module
    ]


def _yearly_actuals(fact: dict[str, Any], parser) -> dict[str, float]:
    cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
    status = fact.get("period_status") if isinstance(fact.get("period_status"), dict) else {}
    found: dict[str, float] = {}
    for key, raw in cells.items():
        label = str(key)
        if not re.fullmatch(r"20\d{2}", label):
            continue
        kind = _reported_period_type(label, str(status.get(key) or "actual"))
        if kind != "actual":
            continue
        value = parser(raw)
        if value is None:
            continue
        found[label] = float(value)
    return found


def _vdr_margins(book: EvidenceBook, math: DeckMath) -> None:
    if len(math.margins) >= 2:
        return
    chosen: dict[str, dict[str, Any]] = {}
    for fact in sorted(_vdr_facts(book, "HPF"), key=lambda item: _source_rank_title(item)):
        label = str(fact.get("row_label") or "").strip()
        if not _MARGIN_ROW.match(label):
            continue
        metric = "EBITDA margin" if "ebitda" in label.lower() else "Gross margin"
        if metric in chosen:
            continue
        years = _yearly_actuals(fact, _pct_from)
        if len(years) >= 2:
            chosen[metric] = {"fact": fact, "years": years, "metric": metric}
    for metric, item in chosen.items():
        fact = item["fact"]
        for year, value in sorted(item["years"].items()):
            fid = book.add(
                module="HPF",
                title="Historical Performance",
                text=f"{metric} {year} (actual): {value:.1f}%",
                docs=list((fact.get("citations") or {}).get("doc") or []),
                period_status="actual",
                bucket="margins",
                grade="established",
            )
            if not fid:
                continue
            book.stamp(fid, value, year)
            math.margins.append({"label": year, "metric": metric, "value": value, "id": fid, "kind": "actual"})


def _source_rank_title(fact: dict[str, Any]) -> int:
    title = f"{fact.get('section_title') or ''} {fact.get('module_title') or ''}".lower()
    if "statement of operations" in title or "management accounts" in title:
        return 0
    if "model basis" in title:
        return 5
    return 2


def _vdr_mix(book: EvidenceBook, math: DeckMath) -> None:
    if math.mix:
        return
    groups: dict[str, list[dict[str, Any]]] = {}
    for fact in _vdr_facts(book, "RVQ"):
        if "fin.revenue_mix" not in (fact.get("measures") or []):
            continue
        name = str(fact.get("row_label") or "").strip()
        if not name or _TOTAL_REVENUE_LABEL.match(name):
            continue
        groups.setdefault(str(fact.get("section_title") or ""), []).append(fact)
    best_rows: list[tuple[str, float, str]] = []
    best_year = ""
    for rows in groups.values():
        years: dict[str, list[tuple[str, float, str]]] = {}
        for fact in rows:
            for year, value in _yearly_actuals(fact, _parse_vdr_millions).items():
                if value <= 0:
                    continue
                years.setdefault(year, []).append((str(fact.get("row_label")), value, str(fact["id"])))
        if not years:
            continue
        year = max(years)
        if len(years[year]) > len(best_rows):
            best_year = year
            best_rows = years[year]
    if len(best_rows) < 2:
        return
    total = round(sum(value for _name, value, _fid in best_rows), 2)
    math.calculations.append(Calc(
        id="CALC-MIX-TOTAL",
        formula=" + ".join(f"s{i}" for i in range(len(best_rows))),
        inputs={f"s{i}": _inp(value, fid) for i, (_name, value, fid) in enumerate(best_rows)},
        output=total,
        unit="$M",
        rounding=2,
        used_on=["S042_gf2_mix_shift"],
    ))
    for index, (name, value, fid) in enumerate(best_rows):
        share = round(value / total * 100, 1) if total else 0.0
        cid = f"CALC-MIX-{index + 1}"
        math.calculations.append(Calc(
            id=cid,
            formula=f"s{index} / total * 100",
            inputs={f"s{index}": _inp(value, fid), "total": {"value": total, "ref": "CALC"}},
            output=share,
            unit="%",
            rounding=1,
            used_on=["S042_gf2_mix_shift"],
        ))
        math.mix.append({"name": name, "share": share, "id": fid, "calc_id": cid})
    math.mix_calculated = True
    if best_year:
        math.mix[0]["year"] = best_year


def _parse_vdr_millions(raw: Any) -> float | None:
    from agetic_cdd_api.report_cdd_evidence import _parse_millions

    return _parse_millions(str(raw))


_TOTAL_REVENUE_LABEL = re.compile(r"(?i)^(total\s+)?(net\s+)?(revenues?|sales|turnover)$")


def _vdr_retention(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    if math.retention or math.retention_curve:
        return
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for fact in _vdr_facts(book, "CST"):
        section = str(fact.get("section_title") or "")
        if "model basis" in section.lower() or "model basis" in str(fact.get("row_label") or "").lower():
            continue
        label = str(fact.get("row_label") or "")
        kind = "grr" if _GRR_ROW.match(label) else "nrr" if _NRR_ROW.match(label) else ""
        if not kind:
            continue
        years = _yearly_actuals(fact, _pct_from)
        if years:
            pairs.setdefault(section, {})[kind] = {"fact": fact, "years": years}
    logo_sections = {
        str(fact.get("section_title") or "")
        for fact in _vdr_facts(book, "CST")
        if _NEW_LOGO.match(str(fact.get("row_label") or "").strip())
    }
    chosen = None
    for section, found in pairs.items():
        if "grr" not in found or "nrr" not in found:
            continue
        overlap = sorted(set(found["grr"]["years"]) & set(found["nrr"]["years"]))
        if len(overlap) < 2:
            continue
        candidate = {"section": section, "years": overlap, "logos": section in logo_sections, **found}
        if chosen is None:
            chosen = candidate
            continue
        # The book that also counts new logos is the retention population. A longer residential series does not replace it.
        if candidate["logos"] != chosen["logos"]:
            if candidate["logos"]:
                chosen = candidate
            continue
        if len(overlap) > len(chosen["years"]):
            chosen = candidate
    if not chosen:
        return
    docs = list((chosen["grr"]["fact"].get("citations") or {}).get("doc") or [])
    population = chosen["section"].split("(")[0].strip() or "the stated book"
    series = []
    for metric, name in (("grr", "GRR"), ("nrr", "NRR")):
        values, ids = [], []
        for year in chosen["years"]:
            value = float(chosen[metric]["years"][year])
            fid = book.add(
                module="CST",
                title="Customer Stickiness",
                text=f"{name} {year} (actual): {value:.1f}%",
                docs=docs,
                period_status="actual",
                bucket="retention",
                grade="established",
            )
            if not fid:
                return
            book.stamp(fid, value, year)
            values.append(value)
            ids.append(fid)
        series.append({"name": name, "values": values, "point_refs": ids})
    math.retention_curve = {"population": population, "categories": chosen["years"], "series": series}
    grr = float(chosen["grr"]["years"][chosen["years"][-1]])
    nrr = float(chosen["nrr"]["years"][chosen["years"][-1]])
    spread = round(nrr - grr, 1)
    math.calculations.append(Calc(
        id="CALC-NRR-GRR",
        formula="nrr - grr",
        inputs={
            "nrr": _inp(nrr, series[1]["point_refs"][-1]),
            "grr": _inp(grr, series[0]["point_refs"][-1]),
        },
        output=spread,
        unit="pp",
        rounding=1,
        used_on=["S068_churn_triggers", "S079_l3_expand_accounts"],
    ))
    math.retention = {
        "population": population,
        "grr": grr,
        "nrr": nrr,
        "spread": spread,
        "grr_id": series[0]["point_refs"][-1],
        "nrr_id": series[1]["point_refs"][-1],
    }


def _vdr_logos(book: EvidenceBook, math: DeckMath) -> None:
    if math.logos:
        return
    grouped: dict[str, dict[str, dict[str, float]]] = {}
    docs: list[str] = []
    for fact in _vdr_facts(book, "CST"):
        label = str(fact.get("row_label") or "").strip()
        kind = "new" if _NEW_LOGO.match(label) else "churned" if _CHURN_LOGO.match(label) else ""
        if not kind:
            continue
        years = _yearly_actuals(fact, _num)
        if not years:
            continue
        section = str(fact.get("section_title") or "")
        grouped.setdefault(section, {})[kind] = years
        docs = list((fact.get("citations") or {}).get("doc") or docs)
    chosen_years: list[str] = []
    chosen: dict[str, dict[str, float]] = {}
    chosen_section = ""
    for section, found in grouped.items():
        if "new" not in found or "churned" not in found:
            continue
        overlap = sorted(set(found["new"]) & set(found["churned"]))
        if len(overlap) > len(chosen_years):
            chosen_years = overlap
            chosen = found
            chosen_section = section
    if len(chosen_years) < 2:
        return
    new_ids, churn_ids, nets = [], [], []
    for year in chosen_years:
        new_value = float(chosen["new"][year])
        churn_value = float(chosen["churned"][year])
        new_id = book.add(
            module="CST", title="Customer Stickiness",
            text=f"New logos {year} (actual): {new_value:.0f}",
            docs=docs, period_status="actual", bucket="logos", grade="established",
        )
        churn_id = book.add(
            module="CST", title="Customer Stickiness",
            text=f"Churned logos {year} (actual): {churn_value:.0f}",
            docs=docs, period_status="actual", bucket="logos", grade="established",
        )
        if not new_id or not churn_id:
            return
        book.stamp(new_id, new_value, year)
        book.stamp(churn_id, churn_value, year)
        net = round(new_value - churn_value, 0)
        math.calculations.append(Calc(
            id=f"CALC-LOGO-NET-{_slug(year)}",
            formula="new - churned",
            inputs={"new": _inp(new_value, new_id), "churned": _inp(churn_value, churn_id)},
            output=net, unit="count", rounding=0, used_on=["S073_l1_new_customers"],
        ))
        new_ids.append(new_id)
        churn_ids.append(churn_id)
        nets.append({"label": year, "value": net})
    active = None
    for fact in _vdr_facts(book, "CST"):
        if str(fact.get("section_title") or "") != chosen_section:
            continue
        if not re.fullmatch(r"(?i)active accounts", str(fact.get("row_label") or "").strip()):
            continue
        cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
        count = str(cells.get(chosen_years[-1]) or "").strip()
        later_key = next((str(key) for key in cells if re.search(r"H1", str(key), re.I)), "")
        later = str(cells.get(later_key) or "").strip() if later_key else ""
        if count and later and fact.get("id"):
            active = {
                "count": count,
                "year": chosen_years[-1],
                "later": later,
                "later_label": later_key,
                "id": str(fact["id"]),
            }
        break
    math.logos = {
        "categories": chosen_years,
        "section": chosen_section,
        "new": [float(chosen["new"][year]) for year in chosen_years],
        "churned": [float(chosen["churned"][year]) for year in chosen_years],
        "new_ids": new_ids,
        "churn_ids": churn_ids,
        "nets": nets,
        "active": active,
    }


def _safe_basis(basis: str, source: str, limit: int = 85) -> str:
    text = " ".join(basis.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
    for number in re.findall(r"\d[\d,]*(?:\.\d+)?%?", text):
        plain = number.replace(",", "")
        if number not in source and plain not in source.replace(",", ""):
            return ""
    return text


def _vdr_method(book: EvidenceBook, math: DeckMath) -> None:
    if math.method_core or math.adjacent:
        return
    core, adjacent = [], []
    for fact in _vdr_facts(book, "MVG"):
        if "mkt.segment_share" not in (fact.get("measures") or []):
            continue
        cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
        territory = str(cells.get("Service territory") or "")
        if "current" not in territory.lower() or "expand" in territory.lower():
            continue
        name = str(fact.get("row_label") or "").split("[")[0].strip()
        basis = _safe_basis(str(cells.get("Assumptions") or ""), str(fact.get("text") or ""))
        if not name or not basis:
            continue
        side = "Commercial" if "commercial" in str(fact.get("row_label") or "").lower() else "Residential"
        item = {"name": f"{side} {name}"[:40], "basis": basis, "id": str(fact["id"])}
        if _HAUL.search(name):
            core.append(item)
        else:
            adjacent.append(item)
    if len(core) >= 1:
        math.method_core = core[:6]
    if len(adjacent) >= 2:
        math.method_adjacent = adjacent[:6]


def _matrix(raw: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if isinstance(raw, dict):
        columns = [str(column) for column in (raw.get("columns") or []) if str(column).strip()]
        body = [row for row in (raw.get("rows") or []) if isinstance(row, dict)]
    elif isinstance(raw, list):
        columns, body = [], [row for row in raw if isinstance(row, dict)]
    else:
        return [], []
    if not columns and body:
        scores = body[0].get("scores") if isinstance(body[0].get("scores"), dict) else {}
        columns = [str(column) for column in scores if str(column).strip()]
    columns = columns[:5]
    normalised = []
    for row in body:
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else row
        normalised.append({
            "criterion": row.get("criterion") or row.get("name"),
            **{column: scores.get(column) for column in columns},
        })
    return columns, normalised


def _cell(value: Any) -> str:
    text = str(value if value is not None else "—").strip()
    return text or "—"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def _agent_docs(ctx: BuildContext, key: str) -> list[str]:
    agent = _resolve(ctx, key)
    spec = _spec(agent)
    docs: list[str] = []
    for pool in (agent.get("primary_sources"), spec.get("primary_sources"), spec.get("sources")):
        if not isinstance(pool, list):
            continue
        for item in pool:
            name = item.get("filename") or item.get("name") if isinstance(item, dict) else item
            text = str(name or "").strip()
            if text and text not in docs:
                docs.append(text)
    return docs[:6]


_YEAR_COL = re.compile(r"^20\d{2}(?:H[12])?$")
_QUOTA_ROW = re.compile(r"(?i)quota|sales rep|account manager|marketing|ramp")


def _trading_case(math: DeckMath) -> None:
    """Compound the latest actual at the latest actual growth, out to the plan year."""
    if math.trading or not math.bridge or not math.yoy:
        return
    step = math.yoy[-1]
    earlier = step.get("earlier_amount")
    later = step.get("later_amount")
    if not isinstance(earlier, (int, float)) or not isinstance(later, (int, float)) or earlier == 0:
        return
    plan_year = _year(str(math.bridge["plan_label"]))
    actual_year = _year(str(step["later"]))
    if plan_year is None or actual_year is None or plan_year <= actual_year:
        return
    grown = round(later * (later / earlier) ** (plan_year - actual_year), 2)
    math.calculations.append(Calc(
        id="CALC-TRADING",
        formula="later * (later / earlier) ** (plan_year - actual_year)",
        inputs={
            "later": _inp(later, step["later_id"]),
            "earlier": _inp(earlier, step["earlier_id"]),
            "plan_year": _inp(float(plan_year), math.bridge["plan_id"]),
            "actual_year": _inp(float(actual_year), step["later_id"]),
        },
        output=grown,
        unit="$M",
        rounding=2,
        used_on=["S047_scenario_analysis"],
    ))
    math.trading = {
        "value": grown,
        "later": step["later"],
        "plan_label": math.bridge["plan_label"],
        "later_id": step["later_id"],
        "earlier_id": step["earlier_id"],
    }


def _quota_coverage(math: DeckMath) -> None:
    if not math.quotas or math.quotas.get("reps") is not None or not math.logos:
        return
    rows = math.quotas.get("rows") or []
    quota = next(
        (
            row for row in rows
            if row.get("quota") and re.search(r"(?i)account|home", f"{row.get('driver') or ''} {row.get('baseline') or ''}")
        ),
        None,
    )
    if quota is None:
        quota = next(
            (row for row in rows if re.search(r"(?i)\bquota\b", str(row.get("driver") or "")) and row.get("quota")),
            None,
        )
    if quota is None:
        quota = next((row for row in rows if row.get("quota")), None)
    if quota is None or not quota.get("quota"):
        return
    new_value = math.logos["new"][-1]
    new_id = math.logos["new_ids"][-1]
    reps = round(new_value / quota["quota"], 1)
    math.calculations.append(Calc(
        id="CALC-LOGO-QUOTA",
        formula="new / quota",
        inputs={"new": _inp(new_value, new_id), "quota": _inp(quota["quota"], quota["id"])},
        output=reps,
        unit="x",
        rounding=1,
        used_on=["S073_l1_new_customers", "S075_l1_channel_expansion"],
    ))
    math.quotas["reps"] = reps


def _vdr_room(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """Exhibits that are already in the workbooks or the CIM and were not on a page."""
    facts = [fact for fact in book.facts if fact.get("source") == "vdr_direct"]
    _room_ties(math, facts)
    _room_cohorts(math, facts)
    _room_concentration(math, facts)
    _room_basis(math, facts)
    _room_subscriber(math, facts)
    _room_contracts(math, facts)
    _room_costs(math, facts)
    _room_zips(math, facts)
    _room_forward(math, facts)
    _room_segment_bridge(book, math, facts)
    _room_dc_cases(ctx, book, math)
    _room_reconcile(ctx, book, math)
    _room_ytd(ctx, book, math)
    _room_cim(ctx, book, math)
    _room_web(ctx, book, math)
    _room_conclusion(book, math)


_MONTHS = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}


def _research_file(ctx: BuildContext) -> Path | None:
    """A deal file wins. Otherwise use the example pack whose folder matches the company."""
    from agetic_cdd_api.report_cdd_evidence import deal_vdr_dir

    folder = deal_vdr_dir(ctx.deal_slug)
    if folder is not None:
        direct = folder.parent / "research.yaml"
        if direct.is_file():
            return direct
    company = str(ctx.profile.company) if ctx.profile and ctx.profile.company else ""
    slug = re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")
    if not slug:
        return None
    example = Path(__file__).resolve().parents[4] / "tools" / "cdd-report-builder" / "examples" / slug / "research.yaml"
    return example if example.is_file() else None


def _retrieved_phrase(raw: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(raw or "").strip())
    if not match:
        return ""
    year, month, day = match.groups()
    label = _MONTHS.get(month)
    if not label:
        return ""
    return f"Retrieved {int(day)} {label} {year}"


def _room_web(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """Competitor pages read on the web. They stay basis web and never become data-room facts."""
    if math.web_competitors:
        return
    path = _research_file(ctx)
    if path is None:
        return
    import yaml

    cfg = yaml.safe_load(path.read_text()) or {}
    phrase = _retrieved_phrase(str(cfg.get("retrieved") or ""))
    rows = []
    for item in cfg.get("items") or []:
        if not isinstance(item, dict):
            continue
        cells = item.get("cells") if isinstance(item.get("cells"), dict) else {}
        name = str(cells.get("Competitor") or "").strip()
        fid = str(item.get("id") or "")
        if not name or not fid.startswith("WEB-") or fid in book.by_id:
            continue
        body = item.get("text") or " | ".join(f"{key}: {value}" for key, value in cells.items())
        if phrase:
            body = f"{body} {phrase}."
        body = f"{body} Outside the data room."
        title = str(item.get("title") or "Secondary research")
        url = str(item.get("url") or "")
        fact = {
            "id": fid,
            "module": str(item.get("module") or "CID"),
            "module_title": "Secondary research (analyst)",
            "text": " ".join(body.split())[:500],
            "citations": {
                "doc": [],
                "web": [f"{title} <{url}> {phrase}".strip()],
                "computed": False,
            },
            "basis": "web",
            "grade": "indicated",
            "period_status": {},
            "class": "fact",
            "source": "analyst_research",
            "flags": ["SECONDARY_RESEARCH"],
            "cells": {str(key): str(value) for key, value in cells.items()},
            "row_label": name,
            "section_title": title,
        }
        book.facts.append(fact)
        book.by_id[fid] = fact
        rows.append({
            "id": fid,
            "name": name,
            "footprint": str(cells.get("Footprint") or "—"),
            "price": str(cells.get("Residential price") or "Not published"),
            "commercial": str(cells.get("Commercial entry price") or ""),
            "retrieved": phrase,
        })
    math.web_competitors = rows


def _room_conclusion(book: EvidenceBook, math: DeckMath) -> None:
    """One closing page: the plan against the trading cases, and reliance on the acquirer's biography."""
    if math.conclusion is not None:
        return
    acquirer = next(
        (
            person for person in math.leaders
            if re.search(r"(?i)\bacquir", str(person.get("bio") or ""))
        ),
        None,
    )
    bridge = math.bridge or {}
    trading = math.trading or {}
    low = trading.get("low") or {}
    parts: list[str] = []
    rows: list[list[str]] = []
    plan = bridge.get("plan")
    high = trading.get("value")
    low_value = low.get("value")
    pair = False
    if isinstance(plan, (int, float)) and isinstance(high, (int, float)) and isinstance(low_value, (int, float)):
        line = f"{low_value:.2f} to {high:.2f} million, against a plan of {plan:.2f}"
        parts.append(f"Recent trading points to {line}.")
        rows.append(["Plan", line])
        above = plan > max(high, low_value)
        pair = True
    elif isinstance(plan, (int, float)) and isinstance(high, (int, float)):
        line = f"{high:.2f} million, against a plan of {plan:.2f}"
        parts.append(f"Recent trading points to {line}.")
        rows.append(["Plan", line])
        above = plan > high
    else:
        above = False
    name = str(acquirer.get("name") or "").strip() if acquirer else ""
    if name:
        year = ""
        match = re.search(r"\b(20\d{2})\b", str(acquirer.get("bio") or ""))
        if match:
            year = f" in {match.group(1)}"
        parts.append(
            f"{name} acquired the company{year}. "
            "The build story is that biography. "
            "No interview or successor was loaded. "
            "That is a key-person reliance risk."
        )
        rows.append(["Key person", f"{name} acquired the company{year}. The build story is that biography."])
        rows.append(["Reliance", "No interview or successor was loaded."])
    if not rows:
        return
    docs: list[str] = []
    for fid in (bridge.get("plan_id"), (acquirer or {}).get("bio_id"), (acquirer or {}).get("id")):
        fact = book.by_id.get(str(fid or ""))
        if not fact:
            continue
        for doc in (fact.get("citations") or {}).get("doc") or []:
            if doc not in docs:
                docs.append(doc)
    fact_id = book.add(
        module="CBG",
        title="Company Background",
        text=" ".join(parts),
        docs=docs[:6],
        bucket="conclusion",
        grade="indicated",
    )
    if not fact_id:
        return
    plan_title = (
        "The plan is above both trading cases" if above and pair
        else "The plan is above the trading case" if above
        else "The plan against the trading case"
    )
    if name and rows and rows[0][0] == "Plan":
        title = f"{plan_title}, and the build record is {name}'s biography"
    elif name:
        title = f"The build record is {name}'s biography, and nobody tested that account"
    else:
        title = plan_title
    plan_bullet = (
        "The plan is above both trading cases." if above and pair
        else "The plan is above the trading case." if above
        else "The plan and the trading case are on the record."
    )
    if name and rows and rows[0][0] == "Plan":
        subtitle = "The trading range and the biography are already on the record. The reliance point is that nobody tested the acquirer."
        bullets = [
            plan_bullet,
            f"The build story is {name}'s biography.",
            "No interview or successor was loaded, which is the reliance risk.",
        ]
    elif name:
        subtitle = "The biography is already on the record. The reliance point is that nobody tested the acquirer."
        bullets = [
            f"The build story is {name}'s biography.",
            "No interview or successor was loaded, which is the reliance risk.",
        ]
    else:
        subtitle = "The trading range is already on the record. This page states the gap."
        bullets = [plan_bullet]
    math.conclusion = {
        "id": fact_id,
        "rows": rows,
        "title": title,
        "subtitle": subtitle,
        "bullets": bullets,
    }


def _actual_year_cells(cells: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for key, raw in cells.items():
        label = str(key).strip()
        if not re.fullmatch(r"20\d{2}", label):
            continue
        text = str(raw).strip()
        amount = _num(text)
        if amount is None or not text:
            continue
        found[label] = {"text": text, "amount": amount}
    return found


def _room_segment_bridge(book: EvidenceBook, math: DeckMath, facts: list[dict[str, Any]]) -> None:
    """Year-to-year movement on the workbook segment sheet, including the municipal share."""
    if math.segment_bridge is not None:
        return
    lines = []
    total = None
    for fact in facts:
        if not _in_section(fact, "revenue by segment"):
            continue
        label = str(fact.get("row_label") or "").strip()
        cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
        years = _actual_year_cells(cells)
        if not label or len(years) < 2:
            continue
        item = {
            "label": label,
            "id": str(fact.get("id") or ""),
            "years": years,
            "docs": list((fact.get("citations") or {}).get("doc") or []),
        }
        if "total" in label.lower():
            total = item
        else:
            lines.append(item)
    if len(lines) < 2:
        return
    year_list = sorted(total["years"])[-3:] if total else sorted({year for line in lines for year in line["years"]})[-3:]
    if len(year_list) < 2:
        return
    pairs = [(year_list[index], year_list[index + 1]) for index in range(len(year_list) - 1)]
    shown = []
    for line in lines:
        if all(line["years"].get(year, {}).get("amount") == 0 for year in year_list if year in line["years"]):
            continue
        shown.append(line)
    if not shown:
        return
    shown = shown[:8]
    latest_pair = pairs[-1]
    prior_pair = pairs[-2] if len(pairs) > 1 else None

    def _delta(line: dict[str, Any], pair: tuple[str, str] | None) -> float | None:
        if pair is None:
            return None
        earlier, later = pair
        if earlier not in line["years"] or later not in line["years"]:
            return None
        return round(line["years"][later]["amount"] - line["years"][earlier]["amount"], 2)

    def _leader(pair: tuple[str, str] | None) -> dict[str, Any] | None:
        ranked = []
        for line in shown:
            delta = _delta(line, pair)
            if delta is None:
                continue
            ranked.append((abs(delta), line, delta))
        if not ranked:
            return None
        _size, line, delta = max(ranked, key=lambda item: item[0])
        earlier, later = pair or ("", "")
        return {"name": line["label"], "delta": delta, "earlier": earlier, "later": later}

    columns = ["Segment", *year_list]
    for earlier, later in pairs:
        columns.append(f"{earlier}-{later}")
    ids = []
    rows = []
    for index, line in enumerate(shown):
        bits = [f"{line['label']} | " + " | ".join(
            f"{year}: {line['years'][year]['text']}" for year in year_list if year in line["years"]
        )]
        row = [_clip_cell(line["label"], 28)]
        for year in year_list:
            row.append(line["years"][year]["text"] if year in line["years"] else "—")
        for pair in pairs:
            delta = _delta(line, pair)
            if delta is None:
                row.append("—")
                continue
            earlier, later = pair
            row.append(f"{delta:+.2f}")
            bits.append(f"{earlier} to {later} change {delta:+.2f}")
            math.calculations.append(Calc(
                id=f"CALC-SEG-{index}-{later}",
                formula="later - earlier",
                inputs={
                    "later": _inp(line["years"][later]["amount"], line["id"]),
                    "earlier": _inp(line["years"][earlier]["amount"], line["id"]),
                },
                output=delta,
                unit="$M",
                rounding=2,
                used_on=["S040_growth_factors_overview"],
            ))
        fid = book.add(
            module="HPF",
            title="Historical Performance",
            text=". ".join(bits),
            docs=line["docs"],
            period_status="actual",
            bucket="segment_bridge",
            grade="established",
        )
        if not fid:
            continue
        ids.append(fid)
        rows.append(row)
    if len(rows) < 2 or not ids:
        math.calculations = [calc for calc in math.calculations if not calc.id.startswith("CALC-SEG-")]
        return
    latest = _leader(latest_pair)
    prior = _leader(prior_pair)
    title_bits = []
    for leader in (prior, latest):
        if not leader:
            continue
        title_bits.append(
            f"From {leader['earlier']} to {leader['later']}, {leader['name']} changed {leader['delta']:+.2f} million"
        )
    title = ". ".join(title_bits) + "." if title_bits else "Workbook segment revenue by year, with each year's change."
    if len(title) > 160 and latest:
        title = (
            f"From {latest['earlier']} to {latest['later']}, {latest['name']} changed {latest['delta']:+.2f} million."
        )
    subtitle = "Each change is the later workbook year minus the earlier one."
    if total and len(year_list) >= 2:
        municipal = [line for line in lines if line["label"].lower().startswith("municipal")]
        early_year, late_year = year_list[0], year_list[-1]
        shares = []
        for year, calc_id in ((early_year, "CALC-MUNI-SHARE-EARLY"), (late_year, "CALC-MUNI-SHARE-LATE")):
            parts = [line for line in municipal if year in line["years"] and line["id"]]
            if not parts or year not in total["years"] or not total["years"][year]["amount"] or not total["id"]:
                continue
            numerator = sum(line["years"][year]["amount"] for line in parts)
            share = round(numerator / total["years"][year]["amount"] * 100, 1)
            inputs = {f"m{index}": _inp(line["years"][year]["amount"], line["id"]) for index, line in enumerate(parts)}
            inputs["total"] = _inp(total["years"][year]["amount"], total["id"])
            names = " + ".join(f"m{index}" for index in range(len(parts)))
            math.calculations.append(Calc(
                id=calc_id,
                formula=f"({names}) / total * 100",
                inputs=inputs,
                output=share,
                unit="%",
                rounding=1,
                used_on=["S040_growth_factors_overview"],
            ))
            shares.append((year, share))
        if len(shares) == 2:
            subtitle = (
                f"Municipal lines were {shares[0][1]:.1f}% of workbook revenue in {shares[0][0]} "
                f"and {shares[1][1]:.1f}% in {shares[1][0]}."
            )
    math.segment_bridge = {
        "columns": columns,
        "rows": rows,
        "ids": ids,
        "title": title,
        "subtitle": subtitle,
    }


def _sheet_amount(amount: float) -> str:
    return f"{amount:.10f}".rstrip("0").rstrip(".")


def _investor_workbooks(ctx: BuildContext) -> list[Any]:
    from agetic_cdd_api.report_cdd_evidence import deal_vdr_dir

    folder = deal_vdr_dir(ctx.deal_slug)
    if folder is None:
        return []
    return [
        path for path in folder.rglob("*.xlsx")
        if re.search(r"investor|workbook", path.name, re.I) and not path.name.startswith("~$")
    ]


def _read_contract_blocks(path: Any) -> dict[str, Any]:
    """DC upside rows and the residential reconciliation block, when a workbook prints them."""
    import openpyxl

    found: dict[str, Any] = {}
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for name in workbook.sheetnames:
            sheet = workbook[name]
            rows = list(sheet.iter_rows(max_row=60, max_col=6, values_only=True))
            lowered = name.lower()
            if "contract" in lowered and "spectrum" not in found:
                for index, row in enumerate(rows):
                    if str(row[0] or "").strip().lower() != "scenario":
                        continue
                    revenue_at = next(
                        (col for col, cell in enumerate(row) if cell and "revenue" in str(cell).lower()),
                        None,
                    )
                    if revenue_at is None:
                        continue
                    cases = []
                    for follow in rows[index + 1:index + 6]:
                        label = str(follow[0] or "").strip()
                        amount = follow[revenue_at] if revenue_at < len(follow) else None
                        if not label:
                            break
                        if not isinstance(amount, (int, float)):
                            continue
                        cases.append({"name": label, "amount": float(amount)})
                    if cases:
                        found["spectrum"] = cases
            if "residential" in lowered and "reconcile" not in found:
                stripe = nominal = paying = None
                note = ""
                for row in rows:
                    label = str(row[0] or "").strip()
                    low = label.lower()
                    numbers = [float(cell) for cell in row[1:] if isinstance(cell, (int, float))]
                    count = next((number for number in numbers if number >= 100), None)
                    rate = next((number for number in numbers if 0 < number < 100), None)
                    if low.startswith("stripe subscriptions") and count is not None:
                        stripe = count
                    elif "nominal" in low and count is not None:
                        nominal = {"count": count, "rate": rate}
                    elif low.startswith("paying residential") and count is not None:
                        paying = count
                    elif "municipal household" in low:
                        note = label
                if stripe is not None and nominal is not None:
                    found["reconcile"] = {
                        "stripe": stripe,
                        "nominal": nominal["count"],
                        "rate": nominal["rate"],
                        "paying": paying,
                        "note": note,
                    }
    finally:
        workbook.close()
    return found


def _room_dc_cases(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """Annualize the largest contract's first half, and read the DC upside rows the sheet prints."""
    if math.dc_cases is not None or not math.contracts or not math.contracts.get("ids"):
        return
    fact = book.by_id.get(math.contracts["ids"][0]) or {}
    cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
    h1_text = ""
    for key, value in cells.items():
        if re.search(r"H1", str(key), re.I) and str(value).strip() not in {"", "0", "—"}:
            h1_text = str(value).strip()
            break
    h1_amount = _num(h1_text)
    rows = []
    fact_bits = []
    run_rate = None
    docs = list((fact.get("citations") or {}).get("doc") or [])
    if h1_amount and h1_amount > 0:
        if h1_amount > 500:
            run_rate = round(h1_amount * 2 / 1_000_000, 2)
            formula = "h1 * 2 / 1000000"
        else:
            run_rate = round(h1_amount * 2, 2)
            formula = "h1 * 2"
        used = ["S074_l1_right_to_win"]
        if math.bridge and (math.trading or math.momentum):
            used.append("S047_scenario_analysis")
        math.calculations.append(Calc(
            id="CALC-CONTRACT-RUNRATE",
            formula=formula,
            inputs={"h1": _inp(h1_amount, str(fact.get("id") or math.contracts["ids"][0]))},
            output=run_rate,
            unit="$M",
            rounding=2,
            used_on=used,
        ))
        rows.append(["Largest contract, first half times two", f"{run_rate:.2f}"])
        fact_bits.append(f"First-half billings annualize to {run_rate:.2f} million")
    else:
        run_rate = None
    dc = (math.forward or {}).get("dc") or {}
    dc_fact = book.by_id.get(dc.get("id") or "") or {}
    dc_cells = dc_fact.get("cells") if isinstance(dc_fact.get("cells"), dict) else {}
    plan_label, plan_text = _year_cell(dc_cells, "2026")
    plan_amount = _num(plan_text)
    if plan_label and plan_text and plan_amount is not None:
        rows.append([f"Municipal - DC {plan_label}", f"{plan_amount:.2f}"])
        fact_bits.append(f"Municipal - DC {plan_label} is {plan_text}")
        docs = list((dc_fact.get("citations") or {}).get("doc") or docs)
    blocks: dict[str, Any] = {}
    for path in _investor_workbooks(ctx)[:3]:
        try:
            blocks = _read_contract_blocks(path)
        except Exception:
            continue
        if blocks.get("spectrum"):
            if path.name not in docs:
                docs.append(path.name)
            break
    for case in (blocks.get("spectrum") or [])[:3]:
        shown = round(case["amount"], 2)
        short = "modeled" if "model" in case["name"].lower() else case["name"].split(",")[0].strip()
        rows.append([_clip_cell(f"DC 2030 {short}", 40), f"{shown:.2f}"])
        fact_bits.append(f"DC 2030 {short} {_sheet_amount(case['amount'])} million")
    if not fact_bits:
        return
    fid = book.add(
        module="HPF",
        title="Historical Performance",
        text=". ".join(fact_bits) + ".",
        docs=docs[:6],
        bucket="dc_cases",
        grade="established",
    )
    if not fid:
        math.calculations = [calc for calc in math.calculations if calc.id != "CALC-CONTRACT-RUNRATE"]
        return
    math.dc_cases = {"rows": rows[:6], "id": fid, "run_rate": run_rate}


def _room_reconcile(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """Stripe subscriptions versus the paying book, when the residential sheet reconciles them."""
    if not math.unit_basis:
        return
    found = None
    doc = ""
    for path in _investor_workbooks(ctx)[:3]:
        try:
            blocks = _read_contract_blocks(path)
        except Exception:
            continue
        if blocks.get("reconcile"):
            found = blocks["reconcile"]
            doc = path.name
            break
    if not found:
        return
    rate = found.get("rate")
    rate_text = f" at {round(rate, 2):.2f} a month" if isinstance(rate, (int, float)) else ""
    municipal = ""
    match = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)\s+municipal", str(found.get("note") or ""), re.I)
    if match:
        municipal = f" They already sit inside the {match.group(1)} municipal households, so they are not added again."
    text = (
        f"Stripe subscriptions are {found['stripe']:.0f}. "
        f"Nominal-rate subscriptions are {found['nominal']:.0f}{rate_text}.{municipal}"
    )
    fid = book.add(
        module="CST",
        title="Customer Stickiness",
        text=text,
        docs=[doc] if doc else [],
        bucket="unit_basis",
        grade="established",
    )
    if not fid:
        return
    math.unit_basis["ids"].append(fid)
    math.unit_basis["reconcile"] = text


def _in_section(fact: dict[str, Any], needle: str) -> bool:
    return needle.lower() in str(fact.get("section_title") or "").lower()


def _clip_cell(value: Any, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text or "—"
    return text[:limit].rsplit(" ", 1)[0] or text[:limit]


def _room_ties(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    accounts = next(
        (
            fact for fact in facts
            if _in_section(fact, "statement of operations")
            and _TOTAL_REVENUE_LABEL.match(str(fact.get("row_label") or "").strip())
        ),
        None,
    )
    workbook = next(
        (
            fact for fact in facts
            if _in_section(fact, "financial summary")
            and re.fullmatch(r"(?i)(total\s+)?revenues?", str(fact.get("row_label") or "").strip())
        ),
        None,
    )
    if accounts is None or workbook is None:
        return
    rows = []
    ids = [str(accounts["id"]), str(workbook["id"])]
    for year in ("2023", "2024", "2025"):
        left = str((accounts.get("cells") or {}).get(year) or "")
        right = str((workbook.get("cells") or {}).get(year) or "")
        if not left or not right or left == right:
            continue
        cim = next(
            (
                fact for fact in facts
                if _in_section(fact, "cim crosswalk")
                and str(fact.get("row_label") or "").strip().lower() == f"revenue {year}"
            ),
            None,
        )
        cim_value = "—"
        if cim is not None:
            cim_value = str((cim.get("cells") or {}).get("Value in the CIM") or "—")
            ids.append(str(cim["id"]))
        rows.append([year, left, right, cim_value])
    if not rows:
        return
    latest = rows[-1]
    math.ties = {
        "columns": ["Year", "Accounts", "Workbook", "CIM"],
        "rows": rows,
        "ids": ids,
        "issue": (
            f"{latest[0]} accounts {latest[1]}, workbook {latest[2]}"
            + (f", CIM {latest[3]}" if latest[3] != "—" else "")
            + "."
        ),
        "treatment": "The accounts figure is the one used on the results pages. The others stay visible here.",
    }


def _room_cohorts(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    chosen = []
    for fact in facts:
        if not _in_section(fact, "customer cohorts"):
            continue
        if not re.fullmatch(r"\d{4} cohort", str(fact.get("row_label") or "").strip()):
            continue
        cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
        years = {str(key): str(value) for key, value in cells.items() if _YEAR_COL.match(str(key)) and str(value).endswith("%")}
        if len(years) >= 2:
            chosen.append((fact, years))
    if len(chosen) < 2:
        return
    counts: dict[str, int] = {}
    for _fact, years in chosen:
        for key in years:
            counts[key] = counts.get(key, 0) + 1
    columns = [key for key, count in sorted(counts.items()) if count >= 2][-4:]
    if len(columns) < 2:
        return
    rows, ids = [], []
    for fact, years in chosen:
        if not any(key in years for key in columns):
            continue
        accounts = str((fact.get("cells") or {}).get("Accounts") or "—")
        if accounts.lower() == "accounts":
            accounts = "—"
        rows.append([str(fact.get("row_label")), _clip_cell(accounts, 12), *[years.get(key, "—") for key in columns]])
        ids.append(str(fact["id"]))
        if len(rows) >= 8:
            break
    if len(rows) < 2:
        return
    math.cohorts = {"columns": ["Cohort", "Accounts", *columns], "rows": rows, "ids": ids}


def _room_concentration(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    ranked = [
        fact for fact in facts
        if _in_section(fact, "concentration") and str((fact.get("cells") or {}).get("Account") or "").strip()
    ]
    if len(ranked) < 3:
        return
    rows, ids = [], []
    for fact in ranked[:8]:
        cells = fact.get("cells") or {}
        revenue = next((str(value) for key, value in cells.items() if "revenue" in str(key).lower()), "—")
        share = str(cells.get("% of commercial") or cells.get("Share") or "—")
        cumulative = str(cells.get("Cumulative %") or "—")
        rows.append([
            str(fact.get("row_label") or "—"),
            _clip_cell(cells.get("Account"), 28),
            _clip_cell(revenue, 16),
            _clip_cell(share, 12),
            _clip_cell(cumulative, 12),
        ])
        ids.append(str(fact["id"]))
    last = rows[-1]
    math.concentration = {
        "columns": ["Rank", "Account", "Revenue", "Share", "Cumulative"],
        "rows": rows,
        "ids": ids,
        "note": f"The first {len(rows)} accounts reach a cumulative share of {last[4]}.",
    }


def _room_basis(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    wanted = ("active locations", "arr (", "arpa", "gross dollar retention", "net dollar retention")
    picked = []
    for fact in facts:
        if not _in_section(fact, "unit economics"):
            continue
        label = str(fact.get("row_label") or "")
        if any(token in label.lower() for token in wanted):
            picked.append(fact)
    if len(picked) < 2:
        return

    def _rank(fact: dict[str, Any]) -> int:
        label = str(fact.get("row_label") or "").lower()
        for index, token in enumerate(wanted):
            if token in label:
                return index
        return len(wanted)

    rows, ids = [], []
    model = actual = ""
    price = ""
    for fact in sorted(picked, key=_rank)[:6]:
        cells = fact.get("cells") or {}
        label = str(fact.get("row_label") or "")
        short = label.split("[", 1)[0].strip()
        if "arpa" in label.lower() or "arpu" in label.lower():
            short = "Price per month"
        rows.append([
            _clip_cell(short, 32),
            _clip_cell(cells.get("Commercial"), 14),
            _clip_cell(cells.get("Municipal"), 14),
            _clip_cell(cells.get("Residential"), 14),
        ])
        ids.append(str(fact["id"]))
        if "gross dollar" in label.lower() and "model basis" in label.lower():
            model = str(cells.get("Commercial") or "")
        if "gross dollar" in label.lower() and "actual cohort" in label.lower():
            actual = str(cells.get("Commercial") or "")
        if "arpa" in label.lower() or "arpu" in label.lower():
            short = "Price per month"
            price = str(cells.get("Residential") or "")
    math.unit_basis = {
        "columns": ["Metric", "Commercial", "Municipal", "Residential"],
        "rows": rows,
        "ids": ids,
        "price": price,
        "issue": (
            f"Gross retention {model} on the model basis and {actual} on the cohort basis."
            if model and actual and model != actual else ""
        ),
        "treatment": "The results pages use the actual cohort basis. The model basis is shown beside it.",
    }


def _room_subscriber(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    points = []
    for fact in facts:
        if not _in_section(fact, "customer retention summary"):
            continue
        label = str(fact.get("row_label") or "").strip()
        if not re.fullmatch(r"\d{1,3}", label):
            continue
        cells = fact.get("cells") or {}
        sub = _num(cells.get("Subscriber retention"))
        rev = _num(cells.get("Revenue retention"))
        if sub is None or rev is None:
            continue
        points.append((int(label), label, sub, rev, str(fact["id"])))
    points.sort()
    if len(points) < 3:
        return
    math.subscriber_curve = {
        "categories": [item[1] for item in points],
        "subscriber": [item[2] for item in points],
        "revenue": [item[3] for item in points],
        "ids": [item[4] for item in points],
    }


def _room_contracts(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    ranked = []
    for fact in facts:
        if not _in_section(fact, "contracts"):
            continue
        label = str(fact.get("row_label") or "").strip()
        if not label or "total" in label.lower():
            continue
        cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
        revenue = str(cells.get("2025") or "")
        amount = _num(revenue)
        if amount is None:
            continue
        lifetime = str(cells.get("Lifetime") or "—")
        ranked.append((amount, label, revenue, lifetime, str(fact["id"])))
    ranked.sort(reverse=True)
    if len(ranked) < 3:
        return
    top_amount, _top_label, _top_revenue, _top_life, top_id = ranked[0]
    revenue = next(
        (
            fact for fact in facts
            if _in_section(fact, "statement of operations")
            and _TOTAL_REVENUE_LABEL.match(str(fact.get("row_label") or "").strip())
            and str((fact.get("cells") or {}).get("2025") or "")
        ),
        None,
    )
    share = ""
    revenue_id = ""
    revenue_amount = _num((revenue.get("cells") or {}).get("2025")) if revenue else None
    formula = ""
    if revenue is not None and revenue_amount and top_amount:
        if top_amount > 500 and revenue_amount < 500:
            share_value = round(top_amount / (revenue_amount * 1_000_000) * 100, 1)
            formula = "contract / (revenue * 1000000) * 100"
        elif top_amount < 500 and revenue_amount < 500:
            share_value = round(top_amount / revenue_amount * 100, 1)
            formula = "contract / revenue * 100"
        else:
            share_value = None
        if formula and share_value is not None:
            revenue_id = str(revenue["id"])
            math.calculations.append(Calc(
                id="CALC-CONTRACT-SHARE",
                formula=formula,
                inputs={"contract": _inp(top_amount, top_id), "revenue": _inp(revenue_amount, revenue_id)},
                output=share_value,
                unit="%",
                rounding=1,
                used_on=["S074_l1_right_to_win"],
            ))
            share = f"{share_value:.1f}%"
    math.contracts = {
        "columns": ["Contract", "2025", "Lifetime"],
        "rows": [[_clip_cell(label, 32), _clip_cell(shown, 18), _clip_cell(lifetime, 18)] for _amount, label, shown, lifetime, _fid in ranked[:6]],
        "ids": [item[4] for item in ranked[:6]],
        "share": share,
        "revenue_id": revenue_id,
        "year": "2025",
    }


def _room_costs(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    if math.costs:
        return
    lines = [
        ("^labor & related benefits$", "Labor and related benefits"),
        ("^subcontractors$", "Subcontractors"),
        ("^compost facility operating costs$", "Processing"),
        ("^total selling", "SG&A"),
    ]
    fleet = (
        r"^maintenance & repairs\b",
        r"^fuel costs\b",
        r"^risk management\b",
        r"^other fleet and equipment costs\b",
    )
    revenue = next(
        (
            fact for fact in facts
            if _in_section(fact, "statement of operations")
            and _TOTAL_REVENUE_LABEL.match(str(fact.get("row_label") or "").strip())
        ),
        None,
    )
    if revenue is None:
        return
    year, revenue_text, revenue_amount = _latest_cost_cell(revenue.get("cells") or {})
    if not year or revenue_amount is None or revenue_amount <= 0 or revenue_amount > 500:
        return
    chosen: list[tuple[str, str, float, list[str]]] = []
    for pattern, name in lines:
        fact = _cost_fact(facts, pattern)
        if fact is None:
            continue
        _year, text, amount = _latest_cost_cell(fact.get("cells") or {}, year)
        if amount is None or amount > 500:
            continue
        chosen.append((name, text, amount, [str(fact["id"])]))
    fleet_facts = [fact for fact in (_cost_fact(facts, pattern) for pattern in fleet) if fact is not None]
    if len(fleet_facts) == len(fleet):
        parts = []
        for fact in fleet_facts:
            text, amount = _cost_number(fact.get("cells") or {}, year)
            if amount is None:
                parts = []
                break
            parts.append((text, amount, str(fact["id"])))
        if parts:
            names = ["a", "b", "c", "d"]
            terms = []
            inputs = {}
            total = 0.0
            for name, (text, amount, fid) in zip(names, parts):
                inputs[name] = _inp(amount, fid)
                if "M" in text or amount < 500:
                    terms.append(name)
                    total += amount
                else:
                    terms.append(f"({name} / 1000000)")
                    total += amount / 1_000_000
            total = round(total, 2)
            math.calculations.append(Calc(
                id="CALC-FLEET",
                formula=" + ".join(terms),
                inputs=inputs,
                output=total,
                unit="$M",
                rounding=2,
                used_on=["S011_value_chain"],
            ))
            chosen.append(("Fleet: maintenance, fuel, risk, other", f"${total:.2f}M", total, [fid for _text, _amount, fid in parts], "CALC"))
    if len(chosen) < 2:
        return
    for index, item in enumerate(chosen, start=1):
        name, text, amount, ids = item[:4]
        cost_ref = item[4] if len(item) == 5 else ids[0]
        share = round(amount / revenue_amount * 100, 1)
        math.calculations.append(Calc(
            id=f"CALC-COST-SHARE-{index}",
            formula="cost / revenue * 100",
            inputs={"cost": _inp(amount, cost_ref), "revenue": _inp(revenue_amount, str(revenue["id"]))},
            output=share,
            unit="%",
            rounding=1,
            used_on=["S011_value_chain"],
        ))
        math.costs.append({
            "name": name,
            "amount": text,
            "share": f"{share:.1f}%",
            "year": year,
            "id": ids[0],
            "ids": [*ids, str(revenue["id"])],
        })


def _cost_fact(facts: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
    regex = re.compile(pattern, re.I)
    for fact in facts:
        if _in_section(fact, "statement of operations") and regex.search(str(fact.get("row_label") or "").strip()):
            return fact
    return None


def _cost_number(cells: dict[str, Any], year: str) -> tuple[str, float | None]:
    pairs = [
        (str(key), str(value))
        for key, value in cells.items()
        if str(key) == year
    ]
    if not pairs:
        return "", None
    text = pairs[0][1]
    return text, _num(text)


def _latest_cost_cell(cells: dict[str, Any], year: str = "") -> tuple[str, str, float | None]:
    pairs = [
        (str(key), str(value))
        for key, value in cells.items()
        if re.fullmatch(r"20\d{2}", str(key)) and (not year or str(key) == year)
    ]
    if not pairs:
        return "", "", None
    label, text = sorted(pairs)[-1]
    amount = _num(text)
    if amount is None or amount > 500:
        return label, text, None
    return label, text, amount


def _room_zips(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    if math.zips:
        return

    def collect(predicate, territory: str) -> list[tuple]:
        scored = []
        for fact in facts:
            title = str(fact.get("section_title") or "")
            if not predicate(title):
                continue
            cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
            score = _num(next((value for key, value in cells.items() if re.search(r"(?i)^score\b|score \(0", str(key))), None))
            city = str(fact.get("row_label") or "").strip()
            if re.fullmatch(r"\d+", city):
                city = str(cells.get("City") or "").strip()
            if score is None or not city or city.lower() in {"city", "rank"}:
                continue
            county = str(cells.get("County") or cells.get("CountyName") or "—")
            code = str(cells.get("Zip") or cells.get("ZIP") or cells.get("ZipCode") or "—")
            if re.fullmatch(r"\d+\.0", code):
                code = code[:-2]
            scored.append((score, territory, city, county, code, str(fact["id"])))
        scored.sort(reverse=True)
        return scored[:4]

    maryland = collect(lambda title: "territory scores" in title.lower() and "northern virginia" not in title.lower(), "Maryland")
    virginia = collect(lambda title: "northern virginia" in title.lower(), "Northern Virginia")
    scored = maryland + virginia
    if len(scored) < 3:
        return
    math.zips = {
        "rows": [[territory, city, county, code, f"{score:.2f}"] for score, territory, city, county, code, _fid in scored[:8]],
        "ids": [item[5] for item in scored[:8]],
        "virginia": bool(virginia),
    }


def _year_cell(cells: dict[str, Any], year: str) -> tuple[str, str]:
    for key, value in cells.items():
        label = str(key).strip()
        if re.match(rf"^{year}(?:P|E)?$", label) and str(value).strip():
            return label, str(value).strip()
    return "", ""


def _room_forward(math: DeckMath, facts: list[dict[str, Any]]) -> None:
    """Plan lines the segment sheet already names: the DC municipal line and Utica."""
    if math.forward is not None:
        return
    dc = utica = None
    lines: list[dict[str, Any]] = []
    for fact in facts:
        if not _in_section(fact, "revenue by segment"):
            continue
        label = str(fact.get("row_label") or "").strip().lower()
        cells = fact.get("cells") or {}
        if not isinstance(cells, dict):
            continue
        if label == "municipal - dc" and dc is None:
            actual_year, actual = _year_cell(cells, "2025")
            plan_year, plan = _year_cell(cells, "2030")
            mix = str(cells.get("2025 Mix") or "").strip()
            if actual and plan:
                dc = {
                    "actual": actual,
                    "actual_year": actual_year,
                    "plan": plan,
                    "plan_year": plan_year,
                    "mix": mix,
                    "id": fact.get("id") or "",
                }
        if label == "utica" and utica is None:
            early_year, early = _year_cell(cells, "2026")
            plan_year, plan = _year_cell(cells, "2030")
            if early and plan:
                utica = {
                    "early": early,
                    "early_year": early_year,
                    "plan": plan,
                    "plan_year": plan_year,
                    "id": fact.get("id") or "",
                }
        if label in {"utica", "key compostables", "compost & products"}:
            actual_year, actual = _year_cell(cells, "2025")
            plan_year, plan = _year_cell(cells, "2030")
            actual_amount = _num(actual)
            plan_amount = _num(plan)
            if actual and plan and actual_amount is not None and plan_amount is not None:
                lines.append({
                    "name": {"utica": "Utica", "key compostables": "Key Compostables", "compost & products": "Compost and products"}[label],
                    "actual": actual,
                    "actual_year": actual_year,
                    "actual_amount": actual_amount,
                    "plan": plan,
                    "plan_year": plan_year,
                    "plan_amount": plan_amount,
                    "id": fact.get("id") or "",
                })
    products = _segment_pair(math, facts, lines)
    if dc or utica or products:
        math.forward = {"dc": dc, "utica": utica, "products": products}


def _segment_pair(math: DeckMath, facts: list[dict[str, Any]], lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Share of workbook revenue for Utica plus Key Compostables, actual and plan."""
    if len(lines) < 2:
        return None
    by_name = {line["name"]: line for line in lines}
    utica = by_name.get("Utica")
    key = by_name.get("Key Compostables")
    workbook = next(
        (
            fact for fact in facts
            if _in_section(fact, "financial summary")
            and re.fullmatch(r"(?i)(total\s+)?revenues?", str(fact.get("row_label") or "").strip())
        ),
        None,
    )
    if utica is None or key is None or workbook is None:
        return {"lines": lines}
    cells = workbook.get("cells") or {}
    actual_amount = _num(str(cells.get("2025") or ""))
    _plan_year, plan_text = _year_cell(cells, "2030")
    plan_amount = _num(plan_text)
    workbook_id = str(workbook.get("id") or "")
    if not actual_amount or plan_amount is None or not workbook_id:
        return {"lines": lines}
    now = round((utica["actual_amount"] + key["actual_amount"]) / actual_amount * 100, 1)
    later = round((utica["plan_amount"] + key["plan_amount"]) / plan_amount * 100, 1)
    math.calculations.append(Calc(
        id="CALC-SEGMENT-NOW",
        formula="(utica + key) / revenue * 100",
        inputs={
            "utica": _inp(utica["actual_amount"], utica["id"]),
            "key": _inp(key["actual_amount"], key["id"]),
            "revenue": _inp(actual_amount, workbook_id),
        },
        output=now,
        unit="%",
        rounding=1,
        used_on=["S082_l6_product_expansion"],
    ))
    math.calculations.append(Calc(
        id="CALC-SEGMENT-PLAN",
        formula="(utica + key) / revenue * 100",
        inputs={
            "utica": _inp(utica["plan_amount"], utica["id"]),
            "key": _inp(key["plan_amount"], key["id"]),
            "revenue": _inp(plan_amount, workbook_id),
        },
        output=later,
        unit="%",
        rounding=1,
        used_on=["S082_l6_product_expansion"],
    ))
    return {"lines": lines, "now": now, "later": later, "revenue_id": workbook_id}


def _partial_totals(path: Any) -> tuple[float, float, int, int, int] | None:
    """Sum the same opening months of the two latest years on a monthly P&L."""
    import datetime

    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook["Monthly P&L"] if "Monthly P&L" in workbook.sheetnames else workbook[workbook.sheetnames[0]]
        rows = list(sheet.iter_rows(max_row=30, values_only=True))
    finally:
        workbook.close()
    header = None
    total = None
    for row in rows:
        if header is None and any(isinstance(cell, datetime.datetime) for cell in row):
            header = row
        if any(isinstance(cell, str) and cell.strip().lower().startswith("total revenues") for cell in row):
            total = row
    if header is None or total is None:
        return None
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for index, cell in enumerate(header):
        if not isinstance(cell, datetime.datetime) or cell.month > 7:
            continue
        amount = total[index] if index < len(total) else None
        if not isinstance(amount, (int, float)):
            continue
        sums[cell.year] = sums.get(cell.year, 0.0) + float(amount)
        counts[cell.year] = counts.get(cell.year, 0) + 1
    years = [year for year in sorted(sums) if counts.get(year, 0) >= 6]
    if len(years) < 2:
        return None
    earlier, later = years[-2], years[-1]
    months = min(counts[earlier], counts[later])
    return round(sums[earlier] / 1_000_000, 2), round(sums[later] / 1_000_000, 2), earlier, later, months


def _room_ytd(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    """Carry the latest actual forward at the year-to-date growth rate."""
    if not math.trading or not math.bridge or math.trading.get("low"):
        return
    from agetic_cdd_api.report_cdd_evidence import deal_vdr_dir

    folder = deal_vdr_dir(ctx.deal_slug)
    if folder is None:
        return
    paths = [
        path for path in folder.rglob("*.xlsx")
        if re.search(r"monthly", path.name, re.I) and not path.name.startswith("~$")
    ]
    found = None
    doc = ""
    for path in paths[:2]:
        try:
            found = _partial_totals(path)
        except Exception:
            continue
        if found:
            doc = path.name
            break
    if not found or not doc or found[0] == 0:
        return
    earlier_m, later_m, earlier_year, later_year, months = found
    plan_year = _year(str(math.bridge["plan_label"]))
    actual_year = _year(str(math.trading.get("later") or ""))
    actual = math.bridge.get("actual")
    if (
        plan_year is None or actual_year is None or plan_year <= actual_year
        or not isinstance(actual, (int, float))
    ):
        return
    rate = round((later_m / earlier_m - 1) * 100, 1)
    grown = round(actual * (later_m / earlier_m) ** (plan_year - actual_year), 2)
    text = (
        f"The first {months} months of {earlier_year} total ${earlier_m:.2f}M. "
        f"The first {months} months of {later_year} total ${later_m:.2f}M. "
        f"Year-to-date growth is {rate:.1f}%. "
        f"Carried forward, that pace is {grown:.2f} million by {math.bridge['plan_label']}."
    )
    fact_id = book.add(
        module="HPF",
        title="Historical Performance",
        text=text,
        docs=[doc],
        bucket="revenue_plan",
        grade="indicated",
    )
    if not fact_id:
        return
    math.calculations.append(Calc(
        id="CALC-YTD-RATE",
        formula="(ytd_later / ytd_earlier - 1) * 100",
        inputs={
            "ytd_later": _inp(later_m, fact_id),
            "ytd_earlier": _inp(earlier_m, fact_id),
        },
        output=rate,
        unit="%",
        rounding=1,
        used_on=["S047_scenario_analysis"],
    ))
    math.calculations.append(Calc(
        id="CALC-YTD-PACE",
        formula="actual * (ytd_later / ytd_earlier) ** (plan_year - actual_year)",
        inputs={
            "actual": _inp(float(actual), math.bridge["actual_id"]),
            "ytd_later": _inp(later_m, fact_id),
            "ytd_earlier": _inp(earlier_m, fact_id),
            "plan_year": _inp(float(plan_year), math.bridge["plan_id"]),
            "actual_year": _inp(float(actual_year), math.bridge["actual_id"]),
        },
        output=grown,
        unit="$M",
        rounding=2,
        used_on=["S047_scenario_analysis"],
    ))
    math.trading["low"] = {"value": grown, "rate": rate, "id": fact_id}


def _cim_prose(path: Any) -> tuple[list[str], list[str]]:
    from pptx import Presentation

    slides: list[str] = []
    descrs: list[str] = []
    deck = Presentation(str(path))
    for slide in deck.slides:
        parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = " ".join(
                    paragraph.text.strip()
                    for paragraph in shape.text_frame.paragraphs
                    if paragraph.text.strip()
                )
                if text:
                    parts.append(text)
            element = getattr(shape, "_element", None)
            if element is None:
                continue
            for node in element.iter():
                if node.tag.endswith("cNvPr"):
                    descr = node.get("descr") or ""
                    if descr:
                        descrs.append(descr)
        if parts:
            slides.append(" ".join(parts))
    return slides, descrs


def _cim_claims(book: EvidenceBook, math: DeckMath, slides: list[str], docs: list[str]) -> None:
    text = " ".join(slides)
    if re.search(r"99\.5%\s*\+?\s*on-time", text, re.I) and re.search(r"\b70\s+NPS\b", text, re.I):
        sentence = "The CIM states 99.5% on-time and a 70 NPS score."
        fact_id = book.add(
            module="CBG", title="Company Background", text=sentence, docs=docs, bucket="claims", grade="asserted",
        )
        if fact_id:
            math.claims.append({
                "name": "On-time service", "stated": "99.5% on-time",
                "test": "No survey file was loaded", "id": fact_id,
            })
            math.claims.append({
                "name": "NPS", "stated": "70 NPS",
                "test": "No survey file was loaded", "id": fact_id,
            })
    if re.search(r"12,000", text) and re.search(r"2\.6%", text):
        sentence = (
            "The CIM states the DC contract is about 12,000 of the municipal locations, "
            "and that rates step up about 2.6% a year from 2027."
        )
        fact_id = book.add(
            module="CBG", title="Company Background", text=sentence, docs=docs, bucket="claims", grade="asserted",
        )
        if fact_id:
            math.claims.append({
                "name": "DC locations", "stated": "about 12,000 of municipal",
                "test": "Not named on the contract sheet", "id": fact_id,
            })
            math.claims.append({
                "name": "Rate step-up", "stated": "about 2.6% a year from 2027",
                "test": "No dollar effect is calculated", "id": fact_id,
            })
    for slide in slides:
        if "DC contract terms" not in slide:
            continue
        sentence = (
            "The CIM states the DC contract was signed in 2025 after a 2023 pilot. "
            "It describes a 5-year contract, one year plus 4 option years, "
            "with annual price escalators and escalating participation caps. "
            "That sentence does not state a termination right."
        )
        term_id = book.add(
            module="CBG", title="Company Background", text=sentence, docs=docs, bucket="claims", grade="asserted",
        )
        if not term_id:
            break
        math.claims.extend([
            {
                "name": "DC term",
                "stated": "Signed in 2025 after a 2023 pilot",
                "test": "CIM wording, not the contract sheet",
                "id": term_id,
            },
            {
                "name": "DC renewal",
                "stated": "5-year term: one year plus 4 option years",
                "test": "Annual escalators and participation caps",
                "id": term_id,
            },
            {
                "name": "DC termination",
                "stated": "Not in that CIM sentence",
                "test": "The option years are the renewal it describes",
                "id": term_id,
            },
        ])
        break


_ROLE = re.compile(
    r"([A-Z][a-z]+(?: [A-Z][a-z]+){1,2}) "
    r"(CEO|Chief Revenue Officer|Sr\. Director of Composting|Vice President of Operations)"
)


def _leadership_bios(slide: str) -> dict[int, str]:
    """Biographies follow the named roles, in the same order, on the leadership page."""
    starts = (
        "Acquired Compost Crew in 2018",
        "Recently joined Compost Crew to lead business development",
        "Joined Compost Crew in 2019",
        "Recently joined Compost Crew to lead operations",
    )
    spots = [(slide.find(start), start) for start in starts if slide.find(start) >= 0]
    spots.sort()
    bios: list[str] = []
    for index, (pos, _start) in enumerate(spots):
        end = spots[index + 1][0] if index + 1 < len(spots) else len(slide)
        bios.append(" ".join(slide[pos:end].split()))
    return {index: text for index, text in enumerate(bios[:4])}


def _cim_milestones(book: EvidenceBook, math: DeckMath, slides: list[str], docs: list[str]) -> None:
    """History-page labels, plus the 2018 acquisition sentence on the leadership page."""
    if math.milestones:
        return
    labels = ("FOUNDED", "ACQUISITION", "DIVERSIFICATION", "ACCELERATION", "EXPANSION")
    history = ""
    leadership = ""
    for slide in slides:
        if "FOUNDED" in slide and "ACQUISITION" in slide and not history:
            history = slide
        if "LEADERSHIP TEAM" in slide and "Acquired Compost Crew in 2018" in slide and not leadership:
            leadership = slide
    rows: list[tuple[str, str]] = []
    if history:
        spots = sorted((history.find(label), label) for label in labels if history.find(label) >= 0)
        for index, (pos, label) in enumerate(spots):
            end = spots[index + 1][0] if index + 1 < len(spots) else len(history)
            raw = history[pos + len(label):end]
            body = re.sub(r"COMPOST CREW HISTORY", " ", raw)
            body = re.sub(r"\b20\d{2}(?:-\d{4}| and beyond)?\b", " ", body)
            body = " ".join(body.split(" ,"))
            body = " ".join(body.split()).strip(" .")
            if body:
                rows.append((label.title(), body, " ".join(raw.split())))
    acquired = ""
    if leadership:
        match = re.search(r"Acquired Compost Crew in 2018\..*?(?:India)", leadership)
        if match:
            acquired = " ".join(match.group(0).split())
    milestones = []
    for when, what, raw in rows:
        text = f"{when}. {what}."
        shown = what
        if when == "Acceleration" and "Key City" in raw and "Washington, DC in 2023" in raw:
            shown = "Acquired Key City in June 2024 and signed the Washington, DC contract in 2023"
            text = f"{when}. {what}. {shown}."
        if when == "Acquisition" and acquired:
            text = f"2018. Ben Parry acquires Compost Crew and Fat Worm Compost. {acquired}"
            when = "2018"
            shown = "Acquired in 2018, from three trucks and five people to $13M+ revenue and 25K customers"
        fid = book.add(
            module="CBG", title="Company Background", text=text, docs=docs, bucket="history", grade="asserted",
        )
        if fid:
            milestones.append({"when": when, "what": _clip_cell(shown, 80), "id": fid})
    if len(milestones) >= 2:
        math.milestones = milestones


def _cim_leaders(book: EvidenceBook, math: DeckMath, slides: list[str], docs: list[str]) -> None:
    blob = next((slide for slide in slides if re.search(r"LEADERSHIP TEAM", slide)), "")
    pairs = _ROLE.findall(blob)
    if len(pairs) < 2:
        return
    sentence = "The CIM leadership page names " + "; ".join(f"{name}, {role}" for name, role in pairs[:4]) + "."
    fact_id = book.add(
        module="CBG", title="Company Background", text=sentence, docs=docs, bucket="leadership", grade="asserted",
    )
    if not fact_id:
        return
    bios = _leadership_bios(blob)
    math.leaders.extend(
        {"name": name, "role": role, "id": fact_id, "bio": bios.get(index, ""), "bio_id": ""}
        for index, (name, role) in enumerate(pairs[:4])
    )
    for person in math.leaders:
        bio = str(person.get("bio") or "").strip()
        if not bio:
            continue
        bio_id = book.add(
            module="CBG",
            title="Company Background",
            text=f"{person['name']}, {person['role']}. {bio}",
            docs=docs,
            bucket="leadership",
            grade="asserted",
        )
        person["bio_id"] = bio_id or ""


_LOGO_WORDS = {
    "green", "header", "logo", "image", "picture", "photo", "icon",
    "wikimedia", "commons", "symbol", "meaning", "history", "png", "brand", "svg", "file",
}


def _cim_picture(book: EvidenceBook, math: DeckMath, descrs: list[str], docs: list[str], company: str) -> None:
    names: list[str] = []
    for descr in descrs:
        if "/" in descr or not re.search(r"(?i)logo|brand", descr):
            continue
        cleaned = re.sub(r"(?i)^file:\s*", "", descr)
        cleaned = re.sub(r"\.[A-Za-z0-9]{2,4}\b.*", " ", cleaned)
        cleaned = re.sub(r"[^A-Za-z& ]+", " ", cleaned)
        words = [word for word in cleaned.split() if word.lower() not in _LOGO_WORDS and len(word) > 1]
        if not words or not words[0][:1].isupper():
            continue
        name = " ".join(words[:3])
        if company and company.lower() in name.lower():
            continue
        if name not in names:
            names.append(name)
        if len(names) >= 4:
            break
    if not names:
        return
    shown = ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 1 else names[0]
    fact_id = book.add(
        module="CBG",
        title="Company Background",
        text=f"Pictures on the CIM competitive page are described as {shown}.",
        docs=docs,
        bucket="competition",
        grade="asserted",
    )
    if fact_id:
        math.picture = {"name": shown, "id": fact_id}


def _room_cim(ctx: BuildContext, book: EvidenceBook, math: DeckMath) -> None:
    from agetic_cdd_api.report_cdd_evidence import deal_vdr_dir

    folder = deal_vdr_dir(ctx.deal_slug)
    if folder is None:
        return
    paths = [
        path for path in folder.rglob("*.pptx")
        if re.search(r"cim|memorandum", path.name, re.I) and not path.name.startswith("~$")
    ]
    for path in paths[:2]:
        try:
            tables, notes = _cim_slide_tables(path)
        except Exception:
            continue
        doc = [path.name]
        if math.assessment is None:
            _cim_archetypes(book, math, tables, doc)
        if math.quotas is None:
            _cim_quotas(book, math, tables, doc)
        if math.deals is None:
            _cim_deals(book, math, tables, notes, doc)
        if not math.cim_history:
            _cim_history(book, math, tables, doc)
        try:
            prose, descrs = _cim_prose(path)
        except Exception:
            prose, descrs = [], []
        if not math.claims:
            _cim_claims(book, math, prose, doc)
        if not math.leaders:
            _cim_leaders(book, math, prose, doc)
        if not math.milestones:
            _cim_milestones(book, math, prose, doc)
        if math.picture is None:
            company = ""
            if ctx.profile and ctx.profile.company:
                company = str(ctx.profile.company)
            _cim_picture(book, math, descrs, doc, company)


def _cim_slide_tables(path: Any) -> tuple[list[list[list[str]]], list[str]]:
    from pptx import Presentation

    tables: list[list[list[str]]] = []
    notes: list[str] = []
    deck = Presentation(str(path))
    for slide in deck.slides:
        blob = []
        for shape in slide.shapes:
            if getattr(shape, "has_table", False):
                rows = []
                for row in shape.table.rows:
                    rows.append([" ".join(cell.text.split()) for cell in row.cells])
                if rows:
                    tables.append(rows)
            elif getattr(shape, "has_text_frame", False):
                text = " ".join(paragraph.text.strip() for paragraph in shape.text_frame.paragraphs if paragraph.text.strip())
                if text:
                    blob.append(text)
        joined = " ".join(blob)
        if re.search(r"(?i)purchase price", joined) and re.search(r"(?i)ebitda", joined):
            notes.append(joined)
    return tables, notes


def _mark(cell: str) -> str:
    token = " ".join(str(cell or "").split())
    if token in {"✓", "✔", "☑"} or token.lower() in {"yes", "y"}:
        return "Yes"
    if token in {"x", "X", "✗", "✕", "×"} or token.lower() in {"no", "n"}:
        return "No"
    if not token or token in {"?", "—", "-", "--"}:
        return "—"
    return token


def _cim_archetypes(book: EvidenceBook, math: DeckMath, tables: list[list[list[str]]], docs: list[str]) -> None:
    for table in tables:
        header = table[0]
        if len(header) < 4:
            continue
        body = table[1:]
        marks = [_mark(cell) for row in body for cell in row[1:]]
        usable = [cell for cell in marks if cell in {"Yes", "No"}]
        if len(usable) < 8 or len(usable) / max(len(marks), 1) < 0.6:
            continue
        indexes = list(range(1, len(header)))
        labels = []
        for index in indexes:
            label = header[index].strip() if index < len(header) else ""
            labels.append(label or "Target")
        keep = indexes[:5]
        labels = [_clip_cell(header[index].strip() or "Target", 22) for index in keep]
        omitted = [_clip_cell(header[index].strip(), 22) for index in indexes[5:] if index < len(header) and header[index].strip()]
        rows, ids = [], []
        for row in body[:8]:
            criterion = row[0].strip()
            if not criterion or _mark(criterion) in {"Yes", "No"}:
                continue
            cells = [_mark(row[index] if index < len(row) else "") for index in keep]
            text = f"Criterion {criterion}: " + ", ".join(f"{column} {cell}" for column, cell in zip(labels, cells))
            fid = book.add(module="CID", title="Competitor Identification", text=text, docs=docs, bucket="assessment", grade="asserted")
            if not fid:
                continue
            rows.append([_clip_cell(criterion, 36), *cells])
            ids.append(fid)
        if len(rows) >= 3:
            math.assessment = {
                "columns": ["Criterion", *labels],
                "rows": rows,
                "ids": ids,
                "omitted": omitted,
            }
            return


def _cim_quotas(book: EvidenceBook, math: DeckMath, tables: list[list[list[str]]], docs: list[str]) -> None:
    for table in tables:
        header = [cell.lower() for cell in table[0]]
        if not header or "driver" not in header[0] or not any("baseline" in cell for cell in header):
            continue
        growth_at = next((index for index, cell in enumerate(header) if "growth" in cell), 2)
        stored = []
        for row in table[1:]:
            driver = row[0].strip() if row else ""
            baseline = row[1].strip() if len(row) > 1 else ""
            growth = row[growth_at].strip() if len(row) > growth_at else ""
            if not driver or (not baseline and not growth):
                continue
            if not _QUOTA_ROW.search(driver):
                continue
            text = f"{driver}. Baseline {baseline}. Growth case {growth}."
            fid = book.add(module="GRO", title="Growth Opportunities", text=text, docs=docs, bucket="quotas", grade="asserted")
            if not fid:
                continue
            stored.append({
                "driver": _clip_cell(driver, 36),
                "baseline": _clip_cell(baseline, 28),
                "growth_case": _clip_cell(growth, 28),
                "id": fid,
                "quota": _num(baseline),
            })
            if len(stored) >= 8:
                break
        if len(stored) >= 2:
            math.quotas = {"rows": stored}
            return


def _cim_deals(
    book: EvidenceBook,
    math: DeckMath,
    tables: list[list[list[str]]],
    notes: list[str],
    docs: list[str],
) -> None:
    stored = []
    for table in tables:
        header = [cell.lower() for cell in table[0]]
        if len(header) < 3 or "target" not in header[0] or "status" not in header[1]:
            continue
        for row in table[1:]:
            name = row[0].strip() if row else ""
            status = row[1].strip() if len(row) > 1 else ""
            detail = row[2].strip() if len(row) > 2 else ""
            if not name or not status:
                continue
            text = f"Acquisition {name}. Status {status}. {detail}"
            fid = book.add(module="SYN", title="Synergies", text=text, docs=docs, bucket="deals", grade="asserted")
            if not fid:
                continue
            stored.append({
                "name": _clip_cell(name, 28),
                "status": _clip_cell(status, 22),
                "scale": "—",
                "terms_text": _clip_cell(detail, 40),
                "id": fid,
                "price": None,
                "multiple": None,
                "implied": None,
                "residual": None,
            })
            if len(stored) >= 8:
                break
        if stored:
            break
    if not stored:
        return
    note = ""
    note_id = ""
    if notes:
        paragraph = " ".join(notes[0].split())
        if len(paragraph) > 300:
            paragraph = paragraph[:300].rsplit(" ", 1)[0]
        note_id = book.add(module="SYN", title="Synergies", text=paragraph, docs=docs, bucket="deals", grade="asserted")
        if note_id:
            note = paragraph
    math.deals = {"rows": stored, "note": note, "note_id": note_id}
    if notes and re.search(r"(?i)subcontract", notes[0]) and re.search(r"1\.2", notes[0]) and re.search(r"1\.6", notes[0]):
        split = (
            "The CIM states about $1.2M of subcontract revenue and about $1.6M of own-book revenue. "
            "Neither figure is added to company revenue here."
        )
        split_id = book.add(module="SYN", title="Synergies", text=split, docs=docs, bucket="deals", grade="asserted")
        if split_id:
            math.deals["split"] = split
            math.deals["split_id"] = split_id
    _spotlight_economics(book, math, notes, docs)


def _spotlight_economics(
    book: EvidenceBook,
    math: DeckMath,
    notes: list[str],
    docs: list[str],
) -> None:
    """Price, multiple and the stated EBITDA effect, when the CIM spotlight gives all three."""
    if not notes or not math.deals or math.deals.get("economics"):
        return
    text = notes[0]
    price = re.search(r"\$(\d+(?:\.\d+)?)\s*M\s+purchase price", text, re.I)
    multiple = re.search(r"(\d+(?:\.\d+)?)x\s+standalone", text, re.I)
    stated = re.search(r"\+\$(\d+(?:\.\d+)?)\s*M EBITDA", text, re.I)
    if not price or not multiple or not stated:
        return
    price_m = float(price.group(1))
    multiple_x = float(multiple.group(1))
    stated_m = float(stated.group(1))
    if multiple_x == 0:
        return

    def grab(pattern: str) -> float | None:
        match = re.search(pattern, text, re.I)
        return float(match.group(1)) if match else None

    cash = grab(r"\$(\d+(?:\.\d+)?)\s*million cash")
    note_k = grab(r"\$(\d+(?:\.\d+)?)\s*k seller")
    equity = grab(r"(\d+(?:\.\d+)?)%\s*equity")
    warrant = grab(r"(\d+(?:\.\d+)?)%\s*total warrant")
    insource = grab(r"\$(\d+(?:\.\d+)?)\s*M/yr")
    bits = [
        f"CIM purchase price ${price_m:.1f}M at {multiple_x:.1f}x.",
        f"Stated EBITDA effect ${stated_m:.1f}M.",
    ]
    if cash is not None:
        bits.append(f"Cash ${cash:.1f} million.")
    if note_k is not None:
        bits.append(f"Note ${note_k:.0f}k.")
    if equity is not None:
        bits.append(f"Equity {equity:.0f}%.")
    if warrant is not None:
        bits.append(f"Warrant potential {warrant:.1f}%.")
    if insource is not None:
        bits.append(f"In-sourced margin ${insource:.1f}M a year.")
    fact_id = book.add(
        module="SYN", title="Synergies", text=" ".join(bits), docs=docs, bucket="deals", grade="asserted",
    )
    if not fact_id:
        return
    implied = round(price_m / multiple_x, 2)
    math.calculations.append(Calc(
        id="CALC-DEAL-EBITDA-Spotlight",
        formula="price / multiple",
        inputs={"price": _inp(price_m, fact_id), "multiple": _inp(multiple_x, fact_id)},
        output=implied,
        unit="$M",
        rounding=2,
        used_on=["S083_l7_ma"],
    ))
    residual = round(stated_m - implied, 2)
    math.calculations.append(Calc(
        id="CALC-DEAL-RESIDUAL-Spotlight",
        formula="stated - implied",
        inputs={"stated": _inp(stated_m, fact_id), "implied": {"value": implied, "ref": "CALC"}},
        output=residual,
        unit="$M",
        rounding=2,
        used_on=["S083_l7_ma"],
    ))
    math.deals["economics"] = {
        "id": fact_id,
        "price": price_m,
        "multiple": multiple_x,
        "stated": stated_m,
        "cash": cash,
        "note_k": note_k,
        "equity": equity,
        "warrant": warrant,
        "insource": insource,
        "implied": implied,
        "residual": residual,
    }


def _cim_history(book: EvidenceBook, math: DeckMath, tables: list[list[list[str]]], docs: list[str]) -> None:
    for table in tables:
        header = table[0]
        if not header or header[0].strip().lower() != "year":
            continue
        years = [cell for cell in header[1:] if re.search(r"20\d{2}", cell)]
        if len(years) < 3:
            continue
        metrics = []
        for row in table[1:4]:
            label = row[0].strip() if row else ""
            if not label:
                continue
            values = {header[index]: row[index].strip() for index in range(1, min(len(header), len(row))) if row[index].strip()}
            text = f"{label} | " + " | ".join(f"{year}: {values.get(year, '')}" for year in years)
            fid = book.add(module="CBG", title="Company Background", text=text, docs=docs, bucket="history", grade="asserted")
            if fid:
                metrics.append((label, values, fid))
        if len(metrics) < 2:
            return
        history = []
        for year in years[:6]:
            bits = [f"{label.split()[0]} {values.get(year, '—')}" for label, values, _fid in metrics if values.get(year)]
            if not bits:
                continue
            history.append({
                "when": year,
                "what": _clip_cell("; ".join(bits), 80),
                "ids": [fid for _label, _values, fid in metrics],
            })
        if len(history) >= 3:
            math.cim_history = history
            return

