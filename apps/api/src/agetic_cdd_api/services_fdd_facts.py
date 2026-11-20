"""Fix 1 — resolve FDD P&L figures from published databook facts only.

Report builders must not take revenue/EBITDA from agent claims. Prefer:

1. Ontology view (``v_databook_fact`` via ``build_databook_view``)
2. Current databook release cells (file-backed publish path)

Both paths yield a ``fact_id`` and a human source cite. Agent-prefixed fact ids
are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agetic_cdd_api.services_fdd_claims import AgentExhibitFigureError, assert_fact_id_not_agent_sourced


@dataclass(frozen=True)
class PublishedPlCell:
    """One closed-year P&L figure backed by a published fact id."""

    value: float
    fact_id: str
    source: str
    metric_key: str
    fiscal_year: int
    basis: str | None = None


def resolve_pl_series(
    deal_slug: str,
    *,
    metrics: tuple[str, ...] = ("revenue", "ebitda"),
    years: tuple[int, ...] = (2024, 2025),
) -> dict[str, dict[int, PublishedPlCell]]:
    """Return ``{metric: {year: PublishedPlCell}}`` for published facts only."""
    slug = str(deal_slug or "").strip()
    want_metrics = {m.lower() for m in metrics if m}
    want_years = {int(y) for y in years}
    out: dict[str, dict[int, PublishedPlCell]] = {m: {} for m in want_metrics}
    if not slug or not want_metrics or not want_years:
        return out

    _fill_from_ontology_view(slug, out, want_metrics, want_years)
    _fill_from_release(slug, out, want_metrics, want_years)
    return out


def source_line_from_cells(cells: Iterable[PublishedPlCell], *, fallback: str) -> str:
    """Join distinct source cites for a slide chrome line."""
    cites: list[str] = []
    seen: set[str] = set()
    for cell in cells:
        cite = (cell.source or "").strip() or cell.fact_id
        if not cite or cite in seen:
            continue
        seen.add(cite)
        cites.append(cite)
        if len(cites) >= 4:
            break
    if not cites:
        return fallback
    return "; ".join(cites) + "; Diligence analysis"


def _plausible_money(value: float | None) -> bool:
    if value is None:
        return False
    try:
        x = abs(float(value))
    except (TypeError, ValueError):
        return False
    # Reject sticky dust and raw-unit leftovers; SME packs sit under $1bn store-M.
    return 0.05 <= x < 1000.0


def _accept_fact_id(fact_id: str | None) -> str | None:
    if not fact_id:
        return None
    try:
        assert_fact_id_not_agent_sourced(fact_id)
    except AgentExhibitFigureError:
        return None
    return str(fact_id)


def _put(
    out: dict[str, dict[int, PublishedPlCell]],
    *,
    metric: str,
    year: int,
    value: float,
    fact_id: str,
    source: str,
    basis: str | None = None,
) -> None:
    if metric not in out or year in out[metric]:
        return
    if not _plausible_money(value):
        return
    fid = _accept_fact_id(fact_id)
    if fid is None:
        return
    out[metric][year] = PublishedPlCell(
        value=float(value),
        fact_id=fid,
        source=(source or "").strip() or fid,
        metric_key=metric,
        fiscal_year=year,
        basis=basis,
    )


def _fill_from_ontology_view(
    slug: str,
    out: dict[str, dict[int, PublishedPlCell]],
    want_metrics: set[str],
    want_years: set[int],
) -> None:
    try:
        from agetic_cdd_api.services_databook_view import build_databook_view
        from agetic_cdd_api.services_published_pages import _deal_id
        from agetic_cdd_api.settings import settings

        if not settings.databook_database_url.strip():
            return
        view = build_databook_view(_deal_id(slug))
    except Exception:
        return
    if getattr(view, "status", None) != "ready":
        return
    series = getattr(view, "series", None) or {}
    for metric in want_metrics:
        by_year = series.get(metric) or {}
        for year_s, cell in by_year.items():
            try:
                year = int(year_s)
            except (TypeError, ValueError):
                continue
            if year not in want_years:
                continue
            value = getattr(cell, "value", None)
            if value is None:
                continue
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            fact_id = getattr(cell, "fact_id", None)
            source = getattr(cell, "source", None) or getattr(cell, "raw", None) or ""
            _put(
                out,
                metric=metric,
                year=year,
                value=num,
                fact_id=str(fact_id) if fact_id else "",
                source=str(source),
                basis="published databook",
            )


def _fill_from_release(
    slug: str,
    out: dict[str, dict[int, PublishedPlCell]],
    want_metrics: set[str],
    want_years: set[int],
) -> None:
    try:
        from agetic_cdd_api.services_databook_consume import (
            load_current_release_metrics_for_slug,
        )
        from agetic_cdd_api.services_fdd_bridge import (
            fact_id_for_cell,
            released_cell_to_fact,
        )
    except Exception:
        return
    try:
        release = load_current_release_metrics_for_slug(slug)
    except Exception:
        release = None
    if release is None:
        return
    for cell in list(getattr(release, "cells", None) or []):
        metric = str(getattr(cell, "metric_key", "") or "").lower()
        if metric not in want_metrics:
            continue
        try:
            year = int(getattr(cell, "fiscal_year"))
        except (TypeError, ValueError):
            continue
        if year not in want_years:
            continue
        try:
            fact = released_cell_to_fact(cell, release, draft_mode=False)
        except Exception:
            continue
        value = getattr(fact, "value", None)
        if value is None:
            continue
        sources = list(getattr(fact, "sources", None) or getattr(cell, "sources", None) or [])
        source = "; ".join(str(s) for s in sources[:3] if s) or (
            f"Databook release {getattr(release, 'release_id', '')}"
        )
        try:
            fid = fact_id_for_cell(cell, release)
        except Exception:
            fid = getattr(fact, "fact_id", None)
        _put(
            out,
            metric=metric,
            year=year,
            value=float(value),
            fact_id=str(fid or getattr(fact, "fact_id", "") or ""),
            source=source,
            basis=str(getattr(getattr(cell, "source_basis", None), "value", None) or "release"),
        )
