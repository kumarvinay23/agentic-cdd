"""Caption → metric mapping via CoA tree (Phase 4) with dual-agree + section gate."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agetic_cdd_api.services_databook_coa import (
    alias_key,
    coa_node_for_metric,
    display_label_for_metric,
    map_caption_coa,
    normalize_caption,
)
from agetic_cdd_api.services_databook_models import MetricFamily

_DISPLAY_LABELS: dict[str, str] = {
    "revenue": "Revenue",
    "units_sold": "Units Sold (000s)",
    "revenue_share_pct": "Revenue Share (%)",
    "units_share_pct": "Units Share (%)",
    "yoy_growth": "YoY Growth",
    "nrr": "Net Revenue Retention (NRR)",
    "grr": "Gross Revenue Retention (GRR)",
    "revenue_churn": "Revenue Churn",
    "arr": "ARR",
    "logo_churn": "Logo Churn",
    "gross_margin": "Gross Margin",
    "ebitda_margin": "EBITDA Margin",
    "ebitda": "EBITDA",
    "gross_profit": "Gross Profit",
    "cash": "Cash",
    "net_debt": "Net Debt",
}


@dataclass(frozen=True)
class MetricMapHit:
    metric_key: str
    family: MetricFamily
    unit: str | None = None
    plainness: float = 1.0
    currency: str | None = None
    scale: str | None = None
    # Phase 4 CoA provenance
    coa_id: str | None = None
    section: str | None = None
    derived: bool = False
    dual_agree: bool = True
    sign: int = 1


def map_caption(
    caption: str,
    *,
    statement: str | None = None,
    sector_pack: str = "generic",
    deal: Any | None = None,
) -> MetricMapHit | None:
    """Map a line caption through the CoA dual-agree path.

    ``statement`` enables the section gate (IS / BS / CF / KPI).
    ``sector_pack`` selects generic or saas (etc.).
    Optional ``deal`` enables Phase 6 mapping-memory overrides (OL-7).
    """
    # OL-7: HITL remaps win over static CoA when present
    if deal is not None:
        try:
            from agetic_cdd_api.services_databook_learn import lookup_mapping_memory

            mem = lookup_mapping_memory(
                deal, caption, sector_pack=sector_pack, statement=statement
            )
            if mem is not None:
                node = coa_node_for_metric(mem.metric_key, sector_pack)
                family = (
                    node.family
                    if node is not None
                    else MetricFamily.UNKNOWN
                )
                return MetricMapHit(
                    metric_key=mem.metric_key,
                    family=family if isinstance(family, MetricFamily) else MetricFamily.UNKNOWN,
                    unit=node.unit if node is not None else None,
                    plainness=1.0,
                    currency=None,
                    scale=None,
                    coa_id=node.id if node is not None else None,
                    section=str(node.section) if node is not None else None,
                    derived=False,
                    dual_agree=True,
                    sign=getattr(node, "sign", 1) if node is not None else 1,
                )
        except Exception:  # noqa: BLE001 — memory must never break extract
            pass

    hit = map_caption_coa(caption, statement=statement, sector_pack=sector_pack)
    if hit is None:
        return None
    return MetricMapHit(
        metric_key=hit.metric_key,
        family=hit.family,
        unit=hit.unit,
        plainness=hit.plainness,
        currency=hit.currency,
        scale=hit.scale,
        coa_id=hit.coa_id,
        section=hit.section,
        derived=hit.derived,
        dual_agree=hit.dual_agree,
        sign=hit.sign,
    )


def _metric_phrase(metric_key: str) -> str:
    """Human phrase for word-boundary plainness checks (drop trailing _pct)."""
    return re.sub(r"_pct$", "", metric_key).replace("_", " ").strip()


def caption_plainness(
    caption: str,
    metric_key: str,
    *,
    statement: str | None = None,
    sector_pack: str = "generic",
) -> float:
    """How plainly the caption names the metric (used in conflict ranking)."""
    hit = map_caption(caption, statement=statement, sector_pack=sector_pack)
    if not (hit and hit.metric_key == metric_key):
        return 0.0

    text = normalize_caption(caption)
    key = alias_key(caption)
    node = coa_node_for_metric(metric_key, sector_pack)
    if node:
        for cap in node.captions:
            if alias_key(cap) == key:
                return 1.0

    phrase = _metric_phrase(metric_key)
    if phrase and re.search(rf"\b{re.escape(phrase)}\b", text, re.I):
        return 1.0

    words = text.lower().split()
    if len(words) <= 3:
        return 0.95
    return hit.plainness


def same_family_allowed(
    caption: str,
    metric_key: str,
    *,
    statement: str | None = None,
    sector_pack: str = "generic",
) -> bool:
    """True if this caption is allowed to compete for metric_key."""
    hit = map_caption(caption, statement=statement, sector_pack=sector_pack)
    if hit is None:
        return False
    target = coa_node_for_metric(metric_key, sector_pack)
    if target is None:
        return hit.metric_key == metric_key
    return hit.family == target.family and hit.metric_key == metric_key


def display_metric_label(
    metric_key: str,
    caption: str | None = None,
    *,
    sector_pack: str = "generic",
) -> str:
    if caption:
        hit = map_caption(caption, sector_pack=sector_pack)
        if hit and hit.metric_key == metric_key:
            return normalize_caption(caption)
    if metric_key in _DISPLAY_LABELS:
        return _DISPLAY_LABELS[metric_key]
    label = display_label_for_metric(metric_key, sector_pack)
    return label if label else metric_key
