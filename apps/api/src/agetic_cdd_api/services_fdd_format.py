"""Fix 3 — single number-rendering service for FDD slides.

Formatting is driven by unit type, currency and scale on the fact/cell —
never by ad-hoc format strings in chapter/slide modules.

Slide builders should call ``format_display`` / ``format_fact`` / ``format_cell``.
``services_fdd_chapters._fmt_num`` is a thin compatibility wrapper only.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal

from agetic_cdd_api.services_fdd_tokens import (
    format_fdd_number,
    format_pptx_money,
    _cell_is_money,
    _cell_is_percent,
    _infer_money_store_scale,
    display_unit_for_cell,
)

UnitType = Literal[
    "CURRENCY",
    "PERCENT",
    "PP",
    "MULTIPLE",
    "RATIO",
    "COUNT",
    "DAYS",
    "NUMBER",
]

_PERCENT_FRACTION_CAP = 1.5  # |v|≤1.5 treated as ontology fraction (0.304 → 30.4%)


def infer_unit_type(
    *,
    unit_type: str | None = None,
    unit: str | None = None,
    scale: str | None = None,
    currency: str | None = None,
    metric_key: str | None = None,
    pct: bool = False,
    money: bool = False,
) -> str:
    """Resolve a canonical unit type from flags or fact metadata."""
    if unit_type:
        return str(unit_type).strip().upper()
    if pct:
        return "PERCENT"
    if money:
        return "CURRENCY"
    scale_l = (scale or "").strip().lower()
    unit_l = (unit or "").strip().lower()
    mk = (metric_key or "").strip().lower()
    if scale_l in {"%", "pct", "percent"} or unit_l in {"%", "pct", "percent"}:
        return "PERCENT"
    if scale_l in {"pp"} or unit_l in {"pp"}:
        return "PP"
    if scale_l in {"x", "multiple"} or unit_l in {"x", "multiple"}:
        return "MULTIPLE"
    if scale_l in {"ratio"} or unit_l in {"ratio"}:
        return "RATIO"
    if scale_l in {"count", "fte", "#"} or unit_l in {"count", "fte", "#"}:
        return "COUNT"
    if scale_l in {"days", "day"} or unit_l in {"days", "day"} or mk.endswith("_days"):
        return "DAYS"
    if currency or scale_l in {
        "m",
        "k",
        "$m",
        "$k",
        "mm",
        "000",
        "thousands",
        "millions",
        "1",
        "u",
        "unit",
        "units",
        "usd",
    }:
        return "CURRENCY"
    if mk.endswith("_margin") or mk.endswith("_pct") or mk.endswith("_rate") or mk.endswith("_yoy"):
        return "PERCENT"
    if "multiple" in mk or mk.endswith("_x"):
        return "MULTIPLE"
    return "NUMBER"


def format_percent(
    value: float | None,
    *,
    already_points: bool | None = None,
    decimals: int = 1,
    glue_unit: bool = True,
) -> str:
    """Render a percent for slides — never a raw fraction like ``0.01798 %``."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if already_points is True:
        pts = num
    elif already_points is False:
        pts = num * 100.0
    else:
        pts = num * 100.0 if abs(num) <= _PERCENT_FRACTION_CAP else num
    try:
        d = Decimal(str(pts))
    except (InvalidOperation, ValueError, TypeError):
        return f"{pts}%" if glue_unit else str(pts)
    if decimals <= 0:
        body = f"{d.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}"
    else:
        q = Decimal(10) ** -decimals
        body = f"{d.quantize(q, rounding=ROUND_HALF_UP):,.{decimals}f}"
    return f"{body}%" if glue_unit else body


def format_pp(
    value: float | None,
    *,
    decimals: int = 1,
) -> str:
    """Percentage-point delta (already in points)."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    try:
        d = Decimal(str(num))
    except (InvalidOperation, ValueError, TypeError):
        return f"{num}pp"
    q = Decimal("0.1") if decimals == 1 else Decimal("0.01")
    body = f"{d.quantize(q, rounding=ROUND_HALF_UP):,.{decimals}f}"
    return f"{body}pp"


def format_multiple(value: float | None, *, decimals: int = 2) -> str:
    """Coverage / valuation multiple, e.g. ``1.25x``."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    try:
        d = Decimal(str(num))
    except (InvalidOperation, ValueError, TypeError):
        return f"{num}x"
    q = Decimal("0.01") if decimals == 2 else Decimal("0.1")
    body = f"{d.quantize(q, rounding=ROUND_HALF_UP):,.{decimals}f}"
    return f"{body}x"


def format_count(value: float | None) -> str:
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return format_fdd_number(num)


def format_display(
    value: float | None,
    *,
    unit_type: str | None = None,
    currency: str | None = None,
    scale: str | None = None,
    unit: str | None = None,
    metric_key: str | None = None,
    display_scale: str | None = None,
    store_scale: str | None = None,
    prose: bool = False,
    already_points: bool | None = None,
    pct: bool = False,
    money: bool = False,
) -> str:
    """Canonical slide number renderer — unit metadata wins over call-site flags."""
    if value is None:
        return "—"
    ut = infer_unit_type(
        unit_type=unit_type,
        unit=unit,
        scale=scale,
        currency=currency,
        metric_key=metric_key,
        pct=pct,
        money=money,
    )
    if ut == "PERCENT":
        return format_percent(value, already_points=already_points)
    if ut == "PP":
        return format_pp(value)
    if ut == "CURRENCY":
        return format_pptx_money(
            value,
            store_scale=store_scale or scale or "M",
            display_scale=display_scale or "k",
            prose=prose,
        )
    if ut == "MULTIPLE":
        return format_multiple(value)
    if ut == "RATIO":
        return format_multiple(value)  # display as x until a dedicated ratio style exists
    if ut in {"COUNT", "DAYS"}:
        return format_count(value)
    # NUMBER — shared rounding, no unit suffix.
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num) >= 100:
        try:
            d = Decimal(str(num))
            body = f"{d.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,.1f}"
            return body
        except (InvalidOperation, ValueError, TypeError):
            return format_fdd_number(num)
    return format_fdd_number(num)


def format_fact(
    fact: Any,
    *,
    display_scale: str | None = None,
    store_scale: str | None = None,
    prose: bool = False,
) -> str:
    """Format from an FddFact / PublishedPlCell / duck-typed fact object."""
    if fact is None:
        return "—"
    display = getattr(fact, "display", None)
    if display:
        return str(display)
    value = getattr(fact, "value", None)
    return format_display(
        value,
        unit_type=getattr(fact, "unit_type", None),
        currency=getattr(fact, "currency", None),
        scale=getattr(fact, "scale", None),
        unit=getattr(fact, "unit", None),
        metric_key=getattr(fact, "metric_key", None),
        display_scale=display_scale,
        store_scale=store_scale or getattr(fact, "scale", None),
        prose=prose,
        money=True if getattr(fact, "metric_key", None) in {
            "revenue", "ebitda", "cash", "net_debt", "nwc", "gross_profit", "net_income"
        } and not getattr(fact, "unit_type", None) else False,
    )


def format_cell(
    cell: Any,
    *,
    store_scale: str = "M",
    display_scale: str = "k",
    prose: bool = False,
) -> str:
    """Format an ExhibitCell using its own unit/currency/scale."""
    if cell is None:
        return "—"
    # Percent/pp always re-render so fraction artefacts never ship — even if
    # ``display`` was pre-baked as a raw float string.
    if _cell_is_percent(cell):
        unit = display_unit_for_cell(cell)
        if unit == "pp":
            return format_pp(getattr(cell, "value", None))
        try:
            mag = abs(float(cell.value)) if cell.value is not None else 0.0
        except (TypeError, ValueError):
            mag = 0.0
        if mag <= _PERCENT_FRACTION_CAP:
            return format_percent(getattr(cell, "value", None))
        # Already in percent points — keep 2-dp accounting style "(1.91)%".
        num = format_fdd_number(getattr(cell, "value", None))
        return f"{num}%" if num not in {"—", ""} else num
    display = getattr(cell, "display", None)
    if display and not _cell_is_money(cell):
        return str(display)
    if _cell_is_money(cell):
        cell_store = _infer_money_store_scale(
            getattr(cell, "value", None),
            cell_scale=getattr(cell, "scale", None),
            fallback=store_scale or "M",
        )
        if str(cell_store).lower() in {"%", "pp", "pct", "percent"}:
            return format_percent(getattr(cell, "value", None))
        return format_pptx_money(
            getattr(cell, "value", None),
            store_scale=cell_store,
            display_scale=display_scale,
            prose=prose,
        )
    return format_display(
        getattr(cell, "value", None),
        unit=getattr(cell, "unit", None),
        scale=getattr(cell, "scale", None),
        currency=getattr(cell, "currency", None),
        metric_key=getattr(cell, "metric_key", None),
        display_scale=display_scale,
        store_scale=store_scale,
        prose=prose,
    )
