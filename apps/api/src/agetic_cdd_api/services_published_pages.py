"""Report pages from the published databook tabs.

One page exists for each schedule that has a sourced fact. A lease schedule
renders rent, a statement of operations renders revenue and costs, and a debt
schedule renders debt. Comparisons use fact ids. An agent output is not a
chosen value.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.services_findings import compare

_RENT = "lease.rent"
_DEBT = ("debt.", "borrowings")
_REVENUE = {"fin.pl.revenue", "fin.pl.revenue_gross"}
_COST = "fin.pl.cost"
_YEAR = re.compile(r"^(20\d{2})(?:-\d{2}-\d{2})?$")


def _year_label(period: Any) -> str | None:
    text = str(period or "").strip()
    match = _YEAR.match(text)
    return match.group(1) if match else None


def _millions(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # Same convention as CDD deck: raw USD → millions for display math.
    if abs(number) >= 100_000:
        return number / 1_000_000
    return number


def pages_for_deal(deal_key: str) -> list[dict[str, Any]]:
    """Published schedule pages for a deal. Empty when the databook URL is unset.

    Report builders pass the deal slug. Facts are stored under the deal id.
    Resolve the slug before reading the view.
    """
    from agetic_cdd_api.settings import settings

    if not str(deal_key or "").strip() or not settings.databook_database_url.strip():
        return []
    from agetic_cdd_api.services_publisher import publish

    return pages_from_tabs(publish(_deal_id(deal_key))["tabs"])


def _deal_id(deal_key: str) -> str:
    """Map a report slug to the databook deal id when they differ."""
    key = str(deal_key or "").strip()
    if not key:
        return key
    try:
        from sqlalchemy import select

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Deal

        with SessionLocal() as db:
            row = db.scalar(select(Deal.id).where(Deal.slug == key).limit(1))
            if row:
                return str(row)
            row = db.scalar(select(Deal.id).where(Deal.id == key).limit(1))
            if row:
                return str(row)
    except Exception:
        return key
    return key


def pages_from_tabs(tabs: dict[str, list]) -> list[dict[str, Any]]:
    """One page per schedule that holds at least one sourced fact."""
    pages = []
    for schedule_id, cells in tabs.items():
        if schedule_id == "GOV-05":
            continue
        figures = [_figure(cell) for cell in cells if _sourced(cell)]
        if not figures:
            continue
        pages.append(_page(str(schedule_id), figures))
    return pages


def comparisons_from_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Revenue comparisons the CDD page plan already draws, taken from fact ids.

    One point per calendar year, amounts in millions — period-end stamps and raw
    USD must not become ``+160216 million`` on the growth page.
    """
    by_year: dict[str, dict[str, Any]] = {}
    for page in pages:
        if page.get("renders") != "revenue_and_costs":
            continue
        for figure in page["figures"]:
            if figure["concept_id"] != "fin.pl.revenue" or figure.get("dimensions"):
                continue
            year = _year_label(figure.get("period_end"))
            amount = _millions(figure.get("value"))
            if not year or amount is None:
                continue
            prior = by_year.get(year)
            # Keep the latest period_end within the year when several stamps exist.
            if prior is None or str(figure.get("period_end") or "") >= str(prior.get("period_end") or ""):
                by_year[year] = {**figure, "value": amount, "year": year}
    series = [by_year[year] for year in sorted(by_year)]
    rows = []
    for earlier, later in zip(series, series[1:]):
        earlier_amt = float(earlier["value"])
        later_amt = float(later["value"])
        if not earlier_amt or earlier["year"] == later["year"]:
            continue
        delta = round(later_amt - earlier_amt, 2)
        rows.append({
            "earlier": earlier["year"],
            "later": later["year"],
            "earlier_amount": earlier_amt,
            "later_amount": later_amt,
            "delta": delta,
            "pct": round(delta / abs(earlier_amt) * 100, 1),
            "delta_id": later["fact_id"],
            "pct_id": later["fact_id"],
            "earlier_id": earlier["fact_id"],
            "later_id": later["fact_id"],
        })
    return rows


def _page(schedule_id: str, figures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schedule_id": schedule_id,
        "renders": _renders(figures),
        "figures": figures,
        "comparison": _comparison(figures),
    }


def _figure(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_id": cell.get("fact_id"),
        "concept_id": cell.get("concept_id"),
        "value": cell.get("value"),
        "period_end": cell.get("period_end"),
        "cell_range": cell.get("cell_range"),
        "dimensions": cell.get("dimensions") or {},
    }


def _sourced(cell: dict[str, Any]) -> bool:
    return isinstance(cell, dict) and bool(str(cell.get("fact_id") or "").strip() and str(cell.get("cell_range") or "").strip())


def _renders(figures: list[dict[str, Any]]) -> str:
    concepts = {str(figure.get("concept_id") or "") for figure in figures}
    if any(concept.startswith(_RENT) for concept in concepts):
        return "rent"
    if any(concept.startswith(_DEBT[0]) or _DEBT[1] in concept for concept in concepts):
        return "debt"
    if any(concept in _REVENUE or concept.startswith(_COST) for concept in concepts):
        return "revenue_and_costs"
    return "figures"


def _comparison(figures: list[dict[str, Any]]) -> dict[str, Any] | None:
    if _segmented(figures):
        return {"recipe": "mix", "chart": "grouped_bar", "fact_ids": [figure["fact_id"] for figure in figures]}
    series = _series(figures)
    if len(series) == 2 and _total(series[0]["concept_id"]):
        result = compare("bridge", {"start": float(series[0]["value"]), "end": float(series[1]["value"])})
        result["fact_ids"] = [series[0]["fact_id"], series[1]["fact_id"]]
        return result
    if len(series) >= 2:
        peak = max(series, key=lambda figure: float(figure["value"]))
        result = compare("period_change", {
            "latest": float(series[-1]["value"]),
            "prior": float(series[-2]["value"]),
            "peak": float(peak["value"]),
        })
        result["fact_ids"] = [figure["fact_id"] for figure in series]
        return result
    return None


def _series(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plain = [figure for figure in figures if not figure.get("dimensions")]
    if not plain:
        return []
    concept = plain[0]["concept_id"]
    rows = [figure for figure in plain if figure["concept_id"] == concept]
    return sorted(rows, key=lambda figure: str(figure.get("period_end") or ""))


def _segmented(figures: list[dict[str, Any]]) -> bool:
    members = {tuple(sorted((figure.get("dimensions") or {}).items())) for figure in figures}
    periods = {figure.get("period_end") for figure in figures}
    return any(figure.get("dimensions") for figure in figures) and len(members) > 1 and len(periods) > 1


def _total(concept: str) -> bool:
    return concept in _REVENUE or concept.startswith(_RENT) or concept.startswith("debt.") or "borrowings" in concept
