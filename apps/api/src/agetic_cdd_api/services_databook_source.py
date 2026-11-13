"""Choose the Databook series source: ontology, file, or dual.

Ontology mode never calls the file-backed summary. Dual prefers ontology
when that read has series or rows, and otherwise uses the file store.
The file-backed modules stay on disk until the ontology Close passes.
"""

from __future__ import annotations

from typing import Any

from agetic_cdd_api.services_databook_view import (
    build_databook_lines,
    build_databook_view,
    filter_line_rows,
)
from agetic_cdd_api.services_databook_view_models import (
    DatabookLineRow,
    DatabookLinesResponse,
    DatabookSeriesCell,
    DatabookTotals,
    DatabookViewResponse,
)
from agetic_cdd_api.settings import settings

_NO_SOURCED_FACT = "No sourced fact for this figure and year."


def no_sourced_fact_message() -> str:
    """Empty Financial history cells use this explanation."""
    return _NO_SOURCED_FACT


def view_for_deal(deal: Any) -> DatabookViewResponse:
    """Financial history for the UI source flag.

    Ontology mode returns facts only. It does not read or promote the file store.
    """
    mode = settings.databook_source
    if mode == "ontology":
        return build_databook_view(_deal_id(deal))
    if mode == "file":
        return _file_view(deal)
    ontology = build_databook_view(_deal_id(deal))
    if _ontology_has_series(ontology):
        return ontology
    return _file_view(deal)


def lines_for_deal(
    deal: Any,
    *,
    q: str = "",
    unmapped: bool = False,
    issue: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> DatabookLinesResponse:
    """All line items for the same source flag as the series grid.

    Ontology mode returns facts only. It does not read or promote the file store.
    """
    mode = settings.databook_source
    if mode == "ontology":
        return build_databook_lines(
            _deal_id(deal),
            q=q,
            unmapped=unmapped,
            issue=issue,
            limit=limit,
            offset=offset,
        )
    if mode == "file":
        return _file_lines(deal, q=q, unmapped=unmapped, issue=issue, limit=limit, offset=offset)
    ontology = build_databook_lines(
        _deal_id(deal),
        q=q,
        unmapped=unmapped,
        issue=issue,
        limit=limit,
        offset=offset,
    )
    if ontology.rows:
        return ontology
    return _file_lines(deal, q=q, unmapped=unmapped, issue=issue, limit=limit, offset=offset)


def tinted_cells_resolve(view: DatabookViewResponse) -> bool:
    """Every tinted series cell has a data-quality id `n`."""
    for issues in view.dq_cells.values():
        if not issues:
            continue
        if any(not isinstance(issue.n, int) for issue in issues):
            return False
    return True


def _ontology_has_series(view: DatabookViewResponse) -> bool:
    return view.status == "ready" and bool(view.series or view.totals.rows)


def _file_view(deal: Any) -> DatabookViewResponse:
    from agetic_cdd_api.services_databook import get_databook_summary

    summary = get_databook_summary(deal, ensure=False)
    series: dict[str, dict[str, DatabookSeriesCell]] = {}
    for metric in summary.promoted_preview:
        series.setdefault(metric.metric_key, {})[str(metric.fiscal_year)] = DatabookSeriesCell(
            value=metric.value,
            currency="" if metric.unit == "%" else (metric.currency or ""),
            unit=metric.unit,
            source=(metric.sources or [""])[0],
            line_item=(metric.captions or [metric.metric_key])[0],
            statement=metric.statement or "",
            fact_id=None,
        )
    return DatabookViewResponse(
        series=series,
        totals=DatabookTotals(metrics=len(series), mapped_rows=len(summary.promoted_preview)),
        status="ready" if series else "building",
        source="file",
    )


def _file_lines(
    deal: Any,
    *,
    q: str,
    unmapped: bool,
    issue: str | None,
    limit: int | None,
    offset: int,
) -> DatabookLinesResponse:
    from agetic_cdd_api.services_databook import list_databook_rows

    rows: list[DatabookLineRow] = []
    for raw in list_databook_rows(deal, limit=10000):
        year = raw.get("fiscal_year")
        if year is None:
            continue
        metric = str(raw.get("metric_key") or "")
        rows.append(
            DatabookLineRow(
                key=str(raw.get("row_id") or ""),
                line_item=str(raw.get("caption") or metric or "line"),
                period=int(year),
                value=raw.get("value"),
                metric=metric,
                currency=str(raw.get("currency") or ""),
                source=str(raw.get("source_name") or ""),
                scale_applied=bool(raw.get("scale")),
                statement=str(raw.get("statement") or ""),
                fact_id=None,
            )
        )
    rows = filter_line_rows(rows, q=q, unmapped=unmapped, issue=issue)
    if offset:
        rows = rows[offset:]
    if limit is not None and limit >= 0:
        rows = rows[:limit]
    return DatabookLinesResponse(rows=rows)


def _deal_id(deal: Any) -> str:
    return str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "")
