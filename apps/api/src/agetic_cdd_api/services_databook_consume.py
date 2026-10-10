"""Downstream readers for released Databook metrics (agents / reports / export).

P0 hard rule: reports prefer the **current released** snapshot. Proven cells
supply numbers; doubtful cells are status-only (no provisional figures in
report tables); missing cells withhold agent material figures. Working
``promoted.json`` is not authoritative once a release exists; if none exists,
we bootstrap a release from the working store when possible.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import re
import warnings
from typing import Any, Iterable

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_models import (
    DatabookRelease,
    PromotedMetric,
    ReleaseCellStatus,
    ReleasedCell,
)
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

_FY_VALUE_RE = re.compile(r"^fy(\d{4})_value$", re.I)
_WORD_RE = re.compile(r"[a-z0-9]+", re.I)


def _normalize_metric_label(text: Any) -> str:
    """Collapse a line_item / metric_key into underscore form for exact compares.

    Coerces non-strings (None, int, bool) so callers can pass raw ``line.get(...)``.
    """
    words = _WORD_RE.findall(str(text or "").lower())
    return "_".join(words)


def _is_material_item(key: Any, item: Any) -> bool:
    """True only for exact material keys / labels — not substring containment.

    Avoids false positives like ``net_revenue_share`` matching ``revenue`` or
    ``gross_margin_bps`` matching ``gross_margin``.
    """
    key_norm = _normalize_metric_label(key)
    if key_norm in MATERIAL_METRIC_KEYS:
        return True
    item_norm = _normalize_metric_label(item)
    if item_norm in MATERIAL_METRIC_KEYS:
        return True
    # Token-subset match only when the item has *exactly* the material's words
    # (e.g. "Gross Margin" → gross_margin), not supersets with extra tokens.
    for mat in MATERIAL_METRIC_KEYS:
        mat_words = mat.split("_")
        item_words = item_norm.split("_") if item_norm else []
        if item_words == mat_words:
            return True
    return False


def load_promoted_metrics(deal: Deal) -> list[PromotedMetric]:
    """Working-store promoted metrics (HITL / export). Reports should use release APIs."""
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
    items: list[Any]
    if isinstance(raw, dict):
        items = raw.get("metrics") if isinstance(raw.get("metrics"), list) else []
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    out: list[PromotedMetric] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(PromotedMetric.model_validate(item))
        except Exception:
            continue
    return out


def load_current_release_metrics_for_slug(deal_slug: str) -> DatabookRelease | None:
    """Current release, bootstrapping from working store when missing."""
    from agetic_cdd_api.services_databook_release import ensure_current_release_for_slug

    return ensure_current_release_for_slug(deal_slug)


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


def _display_unit_parts(
    currency: str | None,
    scale: str | None,
    unit: str | None,
) -> str:
    """Join currency/scale/unit without doubles (\"USD M M\", \"USD % %\")."""
    cur = (currency or "").strip()
    scl = (scale or "").strip()
    unt = (unit or "").strip()
    if scl in {"%", "pp", "pct", "percent"} or unt in {"%", "pp", "pct", "percent"}:
        return unt or (scl if scl != "pct" else "%")
    # Prefer an already-composed unit string when it embeds currency/scale.
    if unt and (not cur or cur.upper() in unt.upper()) and (
        not scl or scl.upper() in unt.upper() or unt.upper().endswith(scl.upper())
    ):
        return unt
    parts: list[str] = []
    for p in (cur, scl, unt):
        if not p:
            continue
        if any(p.upper() == x.upper() for x in parts):
            continue
        if parts and p.upper() in " ".join(parts).upper():
            continue
        if parts and " ".join(parts).upper() in p.upper():
            parts = [p]
            continue
        parts.append(p)
    return " ".join(parts)


def _display_unit(m: PromotedMetric) -> str:
    return _display_unit_parts(m.currency, m.scale, m.unit)


def _display_unit_cell(c: ReleasedCell) -> str:
    return _display_unit_parts(c.currency, c.scale, c.unit)


def _collapse_line_status(statuses: list[str]) -> str:
    """Line-level status from year statuses.

    ``mixed`` means partial year coverage (e.g. proven + missing) — not a silent
    final. Downstream must treat it like incomplete coverage, never as proven.
    """
    if not statuses:
        return "missing"
    if all(s == "proven" for s in statuses):
        return "proven"
    if any(s == "doubtful" for s in statuses):
        # Doubtful dominates: any provisional year keeps the line flagged.
        return "doubtful"
    if all(s == "missing" for s in statuses):
        return "missing"
    return "mixed"


def _ordered_metric_keys(keys: Iterable[str], *, first_seen: list[str] | None = None) -> list[str]:
    """Material keys first (stable material order); custom keys keep first-seen order."""
    key_set = set(keys)
    order = {k: i for i, k in enumerate(sorted(MATERIAL_METRIC_KEYS))}
    material = sorted(
        (k for k in key_set if k in MATERIAL_METRIC_KEYS),
        key=lambda x: order.get(x, 99),
    )
    if first_seen is not None:
        custom = [k for k in first_seen if k not in MATERIAL_METRIC_KEYS and k in key_set]
        custom_set = set(custom)
        leftover = sorted(k for k in key_set if k not in MATERIAL_METRIC_KEYS and k not in custom_set)
        return [*material, *custom, *leftover]
    return sorted(key_set, key=lambda x: (order.get(x, 99), x))


def released_to_pl_lines(release: DatabookRelease) -> list[dict[str, Any]]:
    """Pivot released cells into historical_performance pl_lines shape.

    Proven cells supply ``fy*_value``. Doubtful cells are status-only (no
    provisional numbers in report tables). Missing cells omit values and set
    ``missing_years``. Line ``databook_status`` may be ``mixed`` when years
    combine proven+missing (partial coverage — not a silent final).
    """
    by_metric: dict[str, dict[str, Any]] = {}
    first_seen: list[str] = []
    for c in release.cells:
        if c.metric_key not in by_metric:
            first_seen.append(c.metric_key)
        line = by_metric.setdefault(
            c.metric_key,
            {
                "line_item": humanize_metric_key(c.metric_key),
                "metric_key": c.metric_key,
                "unit": "",
                "fy_units": {},
                "databook": True,
                "databook_release_id": release.release_id,
                "databook_release_version": release.version,
                "sources": [],
                "fy_status": {},
                "fy_reasons": {},
            },
        )
        line["fy_status"][str(c.fiscal_year)] = c.status.value
        if c.reason:
            line["fy_reasons"][str(c.fiscal_year)] = c.reason
        if c.status == ReleaseCellStatus.MISSING:
            line.setdefault("missing_years", []).append(c.fiscal_year)
        elif c.status == ReleaseCellStatus.DOUBTFUL:
            # Status only — do not ship provisional numbers into report tables
            # (avoids contradicting confirmed Full Metric Grid figures).
            line.setdefault("doubtful_years", []).append(c.fiscal_year)
            line["databook_provisional"] = True
        elif c.value is not None:
            line[f"fy{c.fiscal_year}_value"] = c.value
        if c.sources:
            line["sources"] = list(dict.fromkeys([*line["sources"], *c.sources]))
        display = _display_unit_cell(c)
        if display:
            line["fy_units"][str(c.fiscal_year)] = display

    # Line-level status + consolidated unit (common unit, else joined distinct).
    for line in by_metric.values():
        statuses = list((line.get("fy_status") or {}).values())
        line["databook_status"] = _collapse_line_status(statuses)

        fy_units: dict[str, str] = line.get("fy_units") or {}
        distinct = list(dict.fromkeys(u for u in fy_units.values() if u))
        if len(distinct) == 1:
            line["unit"] = distinct[0]
        elif distinct:
            line["unit"] = " | ".join(distinct)
        else:
            line["unit"] = ""

    return [by_metric[k] for k in _ordered_metric_keys(by_metric.keys(), first_seen=first_seen)]


def promoted_to_pl_lines(metrics: list[PromotedMetric]) -> list[dict[str, Any]]:
    """Legacy pivot from working promoted store (tests / export helpers)."""
    by_metric: dict[str, dict[str, Any]] = {}
    first_seen: list[str] = []
    for m in metrics:
        if m.metric_key not in by_metric:
            first_seen.append(m.metric_key)
        line = by_metric.setdefault(
            m.metric_key,
            {
                "line_item": humanize_metric_key(m.metric_key),
                "metric_key": m.metric_key,
                "unit": _display_unit(m),
                "databook": True,
                "databook_status": "proven",
                "sources": [],
            },
        )
        line[f"fy{m.fiscal_year}_value"] = m.value
        if m.sources:
            line["sources"] = list(dict.fromkeys([*line["sources"], *m.sources]))
        display = _display_unit(m)
        if display:
            line.setdefault("fy_units", {})[str(m.fiscal_year)] = display
            # Keep line-level unit as first-seen; do not silently clobber later years.
            if not line.get("unit"):
                line["unit"] = display
    for line in by_metric.values():
        fy_units: dict[str, str] = line.get("fy_units") or {}
        distinct = list(dict.fromkeys(u for u in fy_units.values() if u))
        if len(distinct) == 1:
            line["unit"] = distinct[0]
        elif distinct:
            line["unit"] = " | ".join(distinct)
    return [by_metric[k] for k in _ordered_metric_keys(by_metric.keys(), first_seen=first_seen)]


def _strip_material_agent_values(existing: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Hard rule when no release: do not silently ship agent material FY figures."""
    out: list[dict[str, Any]] = []
    for line in existing or []:
        if not isinstance(line, dict):
            continue
        item = str(line.get("line_item") or line.get("metric_key") or "").strip()
        key = str(line.get("metric_key") or "").strip()
        if not _is_material_item(key, item):
            out.append(dict(line))
            continue
        cleaned = dict(line)
        stripped_years: list[int] = []
        for k in list(cleaned.keys()):
            m = _FY_VALUE_RE.match(str(k))
            if m:
                stripped_years.append(int(m.group(1)))
                cleaned.pop(k)
        cleaned["databook"] = True
        cleaned["databook_status"] = "missing"
        cleaned["missing_years"] = stripped_years
        cleaned["databook_note"] = (
            "No released databook — material agent figures withheld (P0 hard consume)."
        )
        out.append(cleaned)
    return out


def prefer_released_pl_lines(
    deal_slug: str,
    existing: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Prefer current released databook; never fall back to agent material figures."""
    release = load_current_release_metrics_for_slug(deal_slug)
    if release is None or not release.cells:
        return _strip_material_agent_values(existing)
    return released_to_pl_lines(release)


def material_agent_fy_values_present(lines: list[dict[str, Any]] | None) -> bool:
    """True when material lines still carry fy*_value without a databook release stamp.

    G1 / AC-7 guard — reports must not treat these as silent finals.
    """
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        item = str(line.get("line_item") or line.get("metric_key") or "").strip()
        key = str(line.get("metric_key") or "").strip()
        if not _is_material_item(key, item):
            continue
        has_fy = any(_FY_VALUE_RE.match(str(k)) and line.get(k) is not None for k in line)
        if not has_fy:
            continue
        if line.get("databook") or line.get("databook_release_id"):
            # Released / overlay path — ok even when doubtful (flagged separately).
            continue
        return True
    return False


def released_pl_display_rows(
    deal_slug: str,
    existing: list[dict[str, Any]] | None = None,
    *,
    limit: int = 12,
) -> tuple[list[list[str]], list[dict[str, Any]], str | None]:
    """Table rows for report appendices: [Line, FY values, Unit, Status].

    Returns (rows, pl_lines, footnote). Footnote is set when any doubtful cells exist.
    """
    pl = prefer_released_pl_lines(deal_slug, existing)
    rows: list[list[str]] = []
    doubtful = False
    for line in pl[: max(limit, 0)]:
        if not isinstance(line, dict):
            continue
        status = str(line.get("databook_status") or "")
        label = str(line.get("line_item") or "—")
        if status == "doubtful" or line.get("databook_provisional"):
            label = f"{label} †"
            doubtful = True
        years: list[str] = []
        for k, v in sorted(line.items()):
            if str(k).startswith("fy") and str(k).endswith("_value") and v is not None:
                years.append(f"{str(k).replace('_value', '').upper()}={v}")
        if not years and status == "missing":
            years_txt = "missing"
        elif not years and status == "doubtful":
            years_txt = "doubtful (no final value)"
        elif not years and status == "mixed":
            years_txt = "partial coverage"
        else:
            years_txt = "; ".join(years) or "—"
        rows.append([label, years_txt, str(line.get("unit") or "—"), status or "proven"])
    footnote = None
    if doubtful:
        footnote = "† Doubtful — provisional released value, not final."
    if any(isinstance(l, dict) and l.get("databook_status") == "mixed" for l in pl):
        mixed_note = "mixed = partial year coverage (not a silent final)."
        footnote = f"{footnote} {mixed_note}".strip() if footnote else mixed_note
    return rows, pl, footnote


def prefer_promoted_pl_lines(
    deal_slug: str,
    existing: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Deprecated alias — prefer ``prefer_released_pl_lines``."""
    warnings.warn(
        "prefer_promoted_pl_lines is deprecated; use prefer_released_pl_lines instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return prefer_released_pl_lines(deal_slug, existing)


def merge_promoted_into_historical_spec(deal: Deal, spec: dict[str, Any]) -> dict[str, Any]:
    """Overlay released databook onto a historical_performance agent spec."""
    from agetic_cdd_api.services_databook_release import ensure_current_release

    release = ensure_current_release(deal, bootstrap=True)
    if release is None or not release.cells:
        out = copy.deepcopy(spec)
        out["pl_lines"] = _strip_material_agent_values(
            list(out.get("pl_lines") or []) if isinstance(out.get("pl_lines"), list) else []
        )
        out["databook_released"] = False
        out["databook_promoted"] = False
        return out

    out = copy.deepcopy(spec)
    pl = released_to_pl_lines(release)
    all_sources: list[str] = list(out.get("sources") or [])
    for c in release.cells:
        all_sources.extend(c.sources)
    sources = list(dict.fromkeys(all_sources))
    notes = list(out.get("bridge_notes") or [])
    proven_n = release.counts.get("proven", 0)
    doubt_n = release.counts.get("doubtful", 0)
    miss_n = release.counts.get("missing", 0)
    note = (
        f"Databook release {release.release_id}: {proven_n} proven, "
        f"{doubt_n} doubtful, {miss_n} missing — preferred over raw extract."
    )
    if note not in notes:
        notes.insert(0, note)
    if doubt_n:
        doubt_note = (
            "Doubtful figures are provisional (flagged) and must not be treated as final."
        )
        if doubt_note not in notes:
            notes.insert(1, doubt_note)
    # out is already deepcopy(spec) — mutate nested performance_metrics in place.
    if not isinstance(out.get("performance_metrics"), dict):
        out["performance_metrics"] = {}
    perf = out["performance_metrics"]
    for c in release.cells:
        if c.value is not None and c.status == ReleaseCellStatus.PROVEN:
            perf[f"{c.metric_key}_fy{c.fiscal_year}"] = c.value
        elif c.status == ReleaseCellStatus.DOUBTFUL:
            perf[f"{c.metric_key}_fy{c.fiscal_year}_status"] = "doubtful"
    out["pl_lines"] = pl
    out["bridge_notes"] = notes
    out["sources"] = sources
    out["databook_promoted"] = True  # legacy flag
    out["databook_released"] = True
    out["databook_release_id"] = release.release_id
    out["databook_release_version"] = release.version
    out["empty"] = False
    return out


def promoted_resolved_keys(metrics: Iterable[PromotedMetric]) -> set[tuple[str, int]]:
    """(canonical family, fiscal_year) pairs resolved by databook — suppress agent WARNs."""
    return {(m.metric_key, m.fiscal_year) for m in metrics}


def released_resolved_keys(release: DatabookRelease | None) -> set[tuple[str, int]]:
    if release is None:
        return set()
    return {
        (c.metric_key, c.fiscal_year)
        for c in release.cells
        if c.status in {ReleaseCellStatus.PROVEN, ReleaseCellStatus.DOUBTFUL}
    }


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
                "databook_status": "proven",
            }
        )
    return out


def released_as_metric_fact_dicts(release: DatabookRelease) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in release.cells:
        # Proven only — doubtful numbers must not enter KPI / Full Metric Grid.
        if c.status != ReleaseCellStatus.PROVEN or c.value is None:
            continue
        out.append(
            {
                "family": c.metric_key,
                "label": humanize_metric_key(c.metric_key),
                "value": c.value,
                "year": c.fiscal_year,
                "unit": _display_unit_cell(c),
                "agent_key": "databook",
                "agent_name": "Databook",
                "sources": list(c.sources),
                "databook_status": c.status.value,
                "databook_release_id": release.release_id,
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
