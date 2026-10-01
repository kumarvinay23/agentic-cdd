"""Dictionary-first caption → metric mapping with family gates."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agetic_cdd_api.services_databook_models import MetricFamily


@dataclass(frozen=True)
class MetricMapHit:
    metric_key: str
    family: MetricFamily
    unit: str | None = None
    plainness: float = 1.0  # 1.0 = caption plainly names the metric
    currency: str | None = None
    scale: str | None = None


# Longer / more specific patterns first.
_RULES: list[tuple[re.Pattern[str], MetricMapHit]] = [
    (re.compile(r"\bnet\s+revenue\s+retention\b|\bnrr\b", re.I), MetricMapHit("nrr", MetricFamily.RETENTION, "%", 1.0)),
    (re.compile(r"\bgross\s+revenue\s+retention\b|\bgrr\b", re.I), MetricMapHit("grr", MetricFamily.RETENTION, "%", 1.0)),
    (re.compile(r"\brevenue\s+churn\b", re.I), MetricMapHit("revenue_churn", MetricFamily.RETENTION, "%", 1.0)),
    (re.compile(r"\brevenue\s+share\b|\b%?\s*revenue\s+share", re.I), MetricMapHit("revenue_share_pct", MetricFamily.SHARE, "%", 1.0)),
    (re.compile(r"\bunits?\s+share\b", re.I), MetricMapHit("units_share_pct", MetricFamily.SHARE, "%", 1.0)),
    (re.compile(r"\byoy\s+growth\b|\byear[\s-]?over[\s-]?year\b", re.I), MetricMapHit("yoy_growth", MetricFamily.GROWTH, "%", 1.0)),
    (re.compile(r"\bunits?\s+sold\b", re.I), MetricMapHit("units_sold", MetricFamily.UNITS, "000s", 1.0)),
    (re.compile(r"\bgross\s+margin\b", re.I), MetricMapHit("gross_margin", MetricFamily.MARGIN, "%", 1.0)),
    (re.compile(r"\bebitda\s+margin\b", re.I), MetricMapHit("ebitda_margin", MetricFamily.MARGIN, "%", 1.0)),
    (re.compile(r"\btotal\s+revenues?\b", re.I), MetricMapHit("revenue", MetricFamily.REVENUE, None, 1.0)),
    (re.compile(r"\bgross\s+profit\b", re.I), MetricMapHit("gross_profit", MetricFamily.OTHER, None, 1.0)),
    (re.compile(r"\bebitda\b", re.I), MetricMapHit("ebitda", MetricFamily.OTHER, None, 1.0)),
    (re.compile(r"\bnet\s+revenue\b|\brevenue\b(?!\s*(?:share|churn|retention))", re.I), MetricMapHit("revenue", MetricFamily.REVENUE, None, 0.95)),
]


def normalize_caption(caption: str) -> str:
    return re.sub(r"\s+", " ", (caption or "").strip())


def map_caption(caption: str) -> MetricMapHit | None:
    text = normalize_caption(caption)
    if not text:
        return None
    # Never map CIM Crosswalk page provenance rows as financial metrics
    if re.search(r"(?i)cim\s*page|page\(s\)|crosswalk", text):
        return None
    for pattern, hit in _RULES:
        if pattern.search(text):
            # Prefer more specific retention/share over bare "revenue"
            return hit
    return None


def caption_plainness(caption: str, metric_key: str) -> float:
    """How plainly the caption names the metric (used in conflict ranking)."""
    hit = map_caption(caption)
    if hit and hit.metric_key == metric_key:
        # Exact family match with short caption scores higher
        words = normalize_caption(caption).lower().split()
        if metric_key.replace("_", " ") in normalize_caption(caption).lower():
            return 1.0
        if len(words) <= 3:
            return 0.95
        return hit.plainness
    # Caption maps to a different family → reject from competing as that metric
    return 0.0


def same_family_allowed(caption: str, metric_key: str) -> bool:
    """True if this caption is allowed to compete for metric_key."""
    hit = map_caption(caption)
    if hit is None:
        return False
    target = None
    for _, rule_hit in _RULES:
        if rule_hit.metric_key == metric_key:
            target = rule_hit
            break
    if target is None:
        return hit.metric_key == metric_key
    return hit.family == target.family and (
        hit.metric_key == metric_key
        or (metric_key == "revenue" and hit.metric_key == "revenue")
    )


def display_metric_label(metric_key: str, caption: str | None = None) -> str:
    if caption:
        hit = map_caption(caption)
        if hit and hit.metric_key == metric_key:
            return normalize_caption(caption)
    labels = {
        "revenue": "Revenue",
        "units_sold": "Units Sold (000s)",
        "revenue_share_pct": "Revenue Share (%)",
        "units_share_pct": "Units Share (%)",
        "yoy_growth": "YoY Growth",
        "nrr": "Net Revenue Retention (NRR)",
        "grr": "Gross Revenue Retention (GRR)",
        "revenue_churn": "Revenue Churn",
        "net_revenue_usd_m": "net_revenue_usd_m",
    }
    return labels.get(metric_key, metric_key)
