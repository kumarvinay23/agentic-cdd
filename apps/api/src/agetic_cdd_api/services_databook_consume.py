"""Downstream readers for promoted Databook metrics (agents / reports / export)."""

from __future__ import annotations

import copy
import csv
import io
import json
from typing import Any, Iterable

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_models import PromotedMetric
from agetic_cdd_api.services_databook_store import load_promoted
from agetic_cdd_api.services_deals import deals_root

# Headline FY metrics reviewers typically care about first.
MATERIAL_METRIC_KEYS = frozenset(
    {
        "revenue",
        "ebitda",
        "gross_margin",
        "ebitda_margin",
        "nrr",
        "grr",
        "yoy_growth",
    }
)

_LABELS = {
    "revenue": "Revenue",
    "ebitda": "EBITDA",
    "gross_margin": "Gross Margin",
    "ebitda_margin": "EBITDA Margin",
    "nrr": "NRR",
    "grr": "GRR",
    "yoy_growth": "YoY Growth",
    "units_sold": "Units Sold",
    "revenue_share_pct": "Revenue Share",
}


def load_promoted_metrics(deal: Deal) -> list[PromotedMetric]:
    """Canonical reader for agents/reports — prefer over raw agent pl_lines."""
    return load_promoted(deal)


def load_promoted_metrics_for_slug(deal_slug: str) -> list[PromotedMetric]:
    """Load promoted.json by deal slug (report builders may lack a Deal ORM row)."""
    path = deals_root() / deal_slug / "databook" / "promoted.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[PromotedMetric] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(PromotedMetric.model_validate(item))
        except Exception:
            continue
    return out


def humanize_metric_key(metric_key: str) -> str:
    return _LABELS.get(metric_key, metric_key.replace("_", " ").title())


def filter_material_promoted(
    metrics: Iterable[PromotedMetric],
    *,
    material_only: bool = False,
    min_abs: float | None = None,
    metric_keys: frozenset[str] | None = None,
) -> list[PromotedMetric]:
    keys = metric_keys or MATERIAL_METRIC_KEYS
    out: list[PromotedMetric] = []
    for m in metrics:
        if material_only and m.metric_key not in keys:
            continue
        if min_abs is not None and abs(m.value) < min_abs:
            continue
        out.append(m)
    return out


def filter_material_rows(
    rows: list[dict[str, Any]],
    *,
    material_only: bool = False,
    min_abs: float | None = None,
    metric_keys: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    keys = metric_keys or MATERIAL_METRIC_KEYS
    out: list[dict[str, Any]] = []
    for row in rows:
        key = row.get("metric_key")
        if material_only and key not in keys:
            continue
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            value = None
        if min_abs is not None and (value is None or abs(value) < min_abs):
            continue
        out.append(row)
    return out


def promoted_to_pl_lines(metrics: list[PromotedMetric]) -> list[dict[str, Any]]:
    """Pivot promoted (metric, year, value) into historical_performance pl_lines shape.

    Year columns are always ``fy{YYYY}_value`` so any horizon (2022…2025+) works;
    report consumers already match that pattern via FY key regexes.
    """
    by_metric: dict[str, dict[str, Any]] = {}
    for m in metrics:
        line = by_metric.setdefault(
            m.metric_key,
            {
                "line_item": humanize_metric_key(m.metric_key),
                "unit": _display_unit(m),
                "databook": True,
                "sources": [],
            },
        )
        line[f"fy{m.fiscal_year}_value"] = m.value
        for src in m.sources:
            if src not in line["sources"]:
                line["sources"].append(src)
        display = _display_unit(m)
        if display:
            line["unit"] = display
    # Stable order: material keys first, then alpha
    order = {k: i for i, k in enumerate(sorted(MATERIAL_METRIC_KEYS))}
    return [
        by_metric[k]
        for k in sorted(by_metric.keys(), key=lambda x: (order.get(x, 99), x))
    ]


def prefer_promoted_pl_lines(
    deal_slug: str,
    existing: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Prefer databook promoted series; fall back to agent pl_lines when empty."""
    promoted = load_promoted_metrics_for_slug(deal_slug)
    if not promoted:
        return list(existing or [])
    return promoted_to_pl_lines(promoted)


def merge_promoted_into_historical_spec(deal: Deal, spec: dict[str, Any]) -> dict[str, Any]:
    """Overlay promoted metrics onto a historical_performance agent spec.

    Returns a deep copy so nested agent-spec structures are not shared with the
    caller's original dict.
    """
    promoted = load_promoted_metrics(deal)
    if not promoted:
        return copy.deepcopy(spec)
    out = copy.deepcopy(spec)
    pl = promoted_to_pl_lines(promoted)
    sources: list[str] = list(out.get("sources") or [])
    for p in promoted:
        for s in p.sources:
            if s not in sources:
                sources.append(s)
    notes = list(out.get("bridge_notes") or [])
    note = (
        f"Databook promoted {len(promoted)} metric-year(s) preferred over raw extract."
    )
    if note not in notes:
        notes.insert(0, note)
    perf = dict(out.get("performance_metrics") or {})
    for p in promoted:
        perf[f"{p.metric_key}_fy{p.fiscal_year}"] = p.value
    out["pl_lines"] = pl
    out["performance_metrics"] = perf
    out["bridge_notes"] = notes
    out["sources"] = sources
    out["databook_promoted"] = True
    out["empty"] = False
    return out


def promoted_resolved_keys(metrics: Iterable[PromotedMetric]) -> set[tuple[str, int]]:
    """(canonical family, fiscal_year) pairs resolved by databook — suppress agent WARNs."""
    return {(m.metric_key, m.fiscal_year) for m in metrics}


def promoted_as_metric_fact_dicts(metrics: list[PromotedMetric]) -> list[dict[str, Any]]:
    """Shape compatible with ops-dashboard MetricFact construction."""
    out: list[dict[str, Any]] = []
    for m in metrics:
        out.append(
            {
                "family": m.metric_key,
                "label": humanize_metric_key(m.metric_key),
                "value": m.value,
                "year": m.fiscal_year,
                "unit": _display_unit(m),
                "agent_key": "databook",
                "agent_name": "Databook",
                "sources": list(m.sources),
            }
        )
    return out


def promoted_csv(metrics: list[PromotedMetric]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "metric_key",
            "fiscal_year",
            "value",
            "unit",
            "currency",
            "scale",
            "row_id",
            "sources",
            "captions",
            "auto",
            "decision_id",
        ]
    )
    for m in sorted(metrics, key=lambda x: (x.metric_key, x.fiscal_year)):
        writer.writerow(
            [
                m.metric_key,
                m.fiscal_year,
                m.value,
                m.unit or "",
                m.currency or "",
                m.scale or "",
                m.row_id,
                ";".join(m.sources),
                ";".join(m.captions),
                "1" if m.auto else "0",
                m.decision_id or "",
            ]
        )
    return buf.getvalue()


def _display_unit(m: PromotedMetric) -> str:
    """Compose display unit without dropping scale when currency is absent (or vice versa)."""
    parts: list[str] = []
    if m.currency:
        parts.append(m.currency)
    if m.scale and m.scale not in parts:
        parts.append(m.scale)
    if m.unit and m.unit not in parts:
        parts.append(m.unit)
    return " ".join(parts) if parts else ""
