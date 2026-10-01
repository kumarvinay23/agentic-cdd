"""Slice 3 heuristic extractors for Customer Analysis Deep Dive agents (no LLM)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from agetic_cdd_api.deep_dive_extractors import (
    _hits,
    _is_noisy_sentence,
    _sentences,
)

CUSTOMER_SLUGS: frozenset[str] = frozenset(
    {
        "customer_segmentation",
        "customer_stickiness",
        "customer_satisfaction",
        "buying_behavior",
    }
)

_KNOWN_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("Urban Professional", r"Urban Professional"),
    ("Student / Young Adult", r"Student\s*/\s*Young Adult"),
    ("Gig Economy Worker", r"Gig Economy Worker"),
    ("Family User", r"Family User"),
    ("Fleet Operator", r"Fleet Operator"),
)

_SEGMENT_SHARE_RE_TMPL = r"(?i){name}\s+(\d+(?:\.\d+)?)%"

_RETENTION_METRICS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("grr_pct", re.compile(r"(?i)Gross Revenue Retention\s*\(GRR\)\s+(\d+(?:\.\d+)?)%")),
    ("nrr_pct", re.compile(r"(?i)Net Revenue Retention\s*\(NRR\)\s+(\d+(?:\.\d+)?)%")),
    ("logo_churn_pct", re.compile(r"(?i)Logo Churn\s*\(%\)\s+(\d+(?:\.\d+)?)%")),
    ("revenue_churn_pct", re.compile(r"(?i)Revenue Churn\s*\(%\)\s+(\d+(?:\.\d+)?)%")),
    (
        "retention_12m_pct",
        re.compile(
            r"(?i)(?:12[- ]Month Customer Retention Rate|Retention Rate\s*\(12M\))\s+"
            r"(\d+(?:\.\d+)?)%"
        ),
    ),
    (
        "repurchase_pct",
        re.compile(
            r"(?i)(?:Repurchase Rate(?:\s*\([^)]*\))?|Repeat\s*/\s*Referral Purchase\s*\(%\))"
            r"\s+(?:N/A\s+)?(?:\d+(?:\.\d+)?%\s+){0,2}(\d+(?:\.\d+)?)%"
        ),
    ),
)

_COHORT_RE = re.compile(
    r"(?i)(Q[1-4]\s+FY20\d{2}(?:\s*\([^)]{0,40}\))?)\s+"
    r"([\d,]+)\s+"
    r"(\d+(?:\.\d+)?)%\s+"
    r"(\d+(?:\.\d+)?)%"
    r"(?:\s+(?:N/A|(\d+(?:\.\d+)?)%))?"
)

_CHURN_DRIVER_RE = re.compile(
    r"(?i)"
    r"(Service Delay(?:\s*&\s*Unresolved Complaints)?|"
    r"Software Bugs\s*/\s*Feature Gaps(?:\s*\([^)]*\))?|"
    r"Battery Performance Below Expectations|"
    r"Competitive Product Launch(?:\s*\([^)]*\))?|"
    r"Spare Parts Unavailability|"
    r"Price Increase\s*/\s*Subsidy Reduction|"
    r"Lifestyle\s*/\s*Need Change)"
    r"\s+(\d+(?:\.\d+)?)%\s+(Critical|High|Medium|Low)\b"
)

_NPS_FOCAL_RE = re.compile(
    r"(?i)(?:Net Promoter Score\s*\(NPS\)|NPS Score)\s+(\d+(?:\.\d+)?)"
)
_NPS_ROW_RE = re.compile(
    r"(?i)NPS Score\s+((?:\d+(?:\.\d+)?\s+){2,})"
)
_SERVICE_SAT_RE = re.compile(
    r"(?i)Service Satisfaction\s*\(%\)\s+(\d+(?:\.\d+)?)%"
)
_CAC_RE = re.compile(
    r"(?i)(?:Customer Acquisition Cost\s*\(CAC\)|CAC\s*\(INR\))\s+"
    r"(?:INR\s*)?([\d,]+)"
)
_ONLINE_SHARE_RE = re.compile(
    r"(?i)online funnel captures\s*~?(\d+(?:\.\d+)?)%"
)
_ONLINE_ROW_RE = re.compile(
    r"(?i)Online Sales (?:Share|Mix)\s*\(%\)\s+((?:~?\d+(?:\.\d+)?%\s*){2,})"
)
_EMI_SHARE_RE = re.compile(
    r"(?i)~?(\d+(?:\.\d+)?)%\s+of customers purchase via EMI"
)
_TIME_TO_PURCHASE_RE = re.compile(
    r"(?i)Time to Purchase\s*\(Days\)\s+(\d+(?:\.\d+)?)"
)
_GEO_ROW_RE = re.compile(
    r"(?i)(South India|West India|North India|East India|Central India(?:\s*&\s*Others)?)"
    r"[^\d]{0,40}?(\d+(?:\.\d+)?)%"
)

_ICP_NEEDLES = (
    "urban professional",
    "urban millennial",
    "gen z",
    "18–35",
    "18-35",
    "buyer segment",
    "customer profile",
    "ideal customer",
    "aided recall",
)
_STICKINESS_NEEDLES = (
    "retention",
    "nrr",
    "grr",
    "logo churn",
    "repurchase",
    "emi customers",
    "software lock-in",
    "moveos app",
    "ecosystem",
)
_SATISFACTION_NEEDLES = (
    "nps",
    "service satisfaction",
    "service experience",
    "churn driver",
    "unresolved complaints",
    "service delay",
    "reputational",
)
_BUYING_NEEDLES = (
    "online",
    "digital-first",
    "experience center",
    "channel",
    "time to purchase",
    "repeat purchase",
    "cac",
    "emi",
    "fleet segment",
    "concentration",
)
_BAD_CUSTOMER = (
    "porter",
    "threat of",
    "bargaining power",
    "competitive rivalry",
    "glassdoor",
    "employee engagement",
    "enps",
    "attrition — technology",
)


class CustomerSegment(BaseModel):
    name: str
    share_pct: float | None = None
    avg_age: str | None = None
    use_case: str | None = None
    key_driver: str | None = None


class CohortRow(BaseModel):
    cohort: str
    size_units: float | None = None
    m6_retention_pct: float | None = None
    m12_retention_pct: float | None = None
    m36_retention_pct: float | None = None


class ChurnDriver(BaseModel):
    driver: str
    contribution_pct: float | None = None
    severity: str | None = None


class CustomerSegmentationSpec(BaseModel):
    """DD-08 — Ideal Customer Profile (ICP)."""

    document: str = "Ideal Customer Profile (ICP)"
    dd_code: str = "DD-08"
    segments: list[CustomerSegment] = Field(default_factory=list)
    icp_notes: list[str] = Field(default_factory=list)
    geo_mix: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class CustomerStickinessSpec(BaseModel):
    """DD-11 — Revenue Retention Table."""

    document: str = "Revenue Retention Table"
    dd_code: str = "DD-11"
    retention_metrics: dict[str, float] = Field(default_factory=dict)
    cohorts: list[CohortRow] = Field(default_factory=list)
    stickiness_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class CustomerSatisfactionSpec(BaseModel):
    """DD-12 — Onboarding Failure Analysis."""

    document: str = "Onboarding Failure Analysis"
    dd_code: str = "DD-12"
    nps: float | None = None
    peer_nps: list[str] = Field(default_factory=list)
    service_satisfaction_pct: float | None = None
    churn_drivers: list[ChurnDriver] = Field(default_factory=list)
    satisfaction_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class BuyingBehaviorSpec(BaseModel):
    """DD-09 — Concentration Risk Analysis."""

    document: str = "Concentration Risk Analysis"
    dd_code: str = "DD-09"
    concentration_flags: list[str] = Field(default_factory=list)
    channel_mix: list[str] = Field(default_factory=list)
    buying_metrics: dict[str, float] = Field(default_factory=dict)
    behavior_notes: list[str] = Field(default_factory=list)
    segment_hhi: float | None = None
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


def _clean(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "").strip()


def _dedupe(lines: list[str], *, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        cleaned = re.sub(r"\s+", " ", _clean(line)).strip()
        cleaned = re.sub(r"^[\W_]{1,4}", "", cleaned).strip()
        key = cleaned.lower()
        if len(cleaned) < 20 or key in seen:
            continue
        if any(bad in key for bad in _BAD_CUSTOMER):
            continue
        seen.add(key)
        out.append(cleaned[:280])
        if len(out) >= limit:
            break
    return out


def _parse_segments(text: str) -> list[CustomerSegment]:
    out: list[CustomerSegment] = []
    for label, name_pat in _KNOWN_SEGMENTS:
        match = re.search(_SEGMENT_SHARE_RE_TMPL.format(name=name_pat), text or "")
        if not match:
            continue
        share = float(match.group(1))
        # Optional age band immediately after share (e.g. 27–35 or N/A).
        tail = (text or "")[match.end() : match.end() + 80]
        age_m = re.match(r"\s*((?:\d{2}\s*[–\-]\s*\d{2})|N/A)\b", tail, re.I)
        age = re.sub(r"\s+", "", age_m.group(1)) if age_m else None
        out.append(CustomerSegment(name=label, share_pct=share, avg_age=age))
    return out


def _parse_geo_mix(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _GEO_ROW_RE.finditer(text or ""):
        region = re.sub(r"\s+", " ", match.group(1)).strip()
        key = region.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(f"{region}: {float(match.group(2)):g}% revenue share")
        if len(found) >= 5:
            break
    return found


def _parse_retention_metrics(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, pattern in _RETENTION_METRICS:
        match = pattern.search(text or "")
        if match:
            metrics[key] = float(match.group(1))
    # Soft fill repurchase from commercial "22% vs 35%" style if missing.
    if "repurchase_pct" not in metrics:
        m = re.search(
            r"(?i)Repeat purchase rate of\s+(\d+(?:\.\d+)?)%\s+vs\s+(\d+(?:\.\d+)?)%",
            text or "",
        )
        if m:
            metrics["repurchase_pct"] = float(m.group(1))
            metrics["repurchase_benchmark_pct"] = float(m.group(2))
    return metrics


def _parse_cohorts(text: str) -> list[CohortRow]:
    rows: list[CohortRow] = []
    for match in _COHORT_RE.finditer(text or ""):
        cohort = re.sub(r"\s+", " ", match.group(1)).strip()
        size = float(match.group(2).replace(",", ""))
        m6 = float(match.group(3))
        m12 = float(match.group(4))
        m36 = float(match.group(5)) if match.group(5) else None
        rows.append(
            CohortRow(
                cohort=cohort,
                size_units=size,
                m6_retention_pct=m6,
                m12_retention_pct=m12,
                m36_retention_pct=m36,
            )
        )
        if len(rows) >= 8:
            break
    return rows


def _parse_churn_drivers(text: str) -> list[ChurnDriver]:
    rows: list[ChurnDriver] = []
    for match in _CHURN_DRIVER_RE.finditer(text or ""):
        rows.append(
            ChurnDriver(
                driver=re.sub(r"\s+", " ", match.group(1)).strip(),
                contribution_pct=float(match.group(2)),
                severity=match.group(3).title(),
            )
        )
        if len(rows) >= 7:
            break
    return rows


def _focal_nps(text: str) -> float | None:
    # Prefer commercial peer row (first value = focal).
    row = _NPS_ROW_RE.search(text or "")
    if row:
        vals = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", row.group(1))]
        if vals:
            return vals[0]
    match = _NPS_FOCAL_RE.search(text or "")
    return float(match.group(1)) if match else None


def _peer_nps_lines(text: str, prior_spec: dict | None) -> list[str]:
    lines: list[str] = []
    if prior_spec:
        for row in prior_spec.get("competitors") or []:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            nps = row.get("nps")
            if name and nps is not None:
                lines.append(f"{name}: NPS {nps:g}")
    if lines:
        return lines[:6]
    # Fallback: commercial table headers after NPS Score.
    row = _NPS_ROW_RE.search(text or "")
    if not row:
        return []
    vals = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", row.group(1))]
    labels = ("Ola Electric", "Ather Energy", "TVS iQube", "Industry Avg")
    for label, val in zip(labels, vals):
        lines.append(f"{label}: NPS {val:g}")
    return lines[:6]


def _extract_segmentation(text: str, sentences: list[str]) -> CustomerSegmentationSpec:
    segments = _parse_segments(text)
    geo = _parse_geo_mix(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _ICP_NEEDLES, limit=6), limit=4)
    if not notes and segments:
        top = max(segments, key=lambda s: s.share_pct or 0.0)
        notes = [
            f"Largest segment is {top.name} at {top.share_pct:g}% of the customer mix."
        ]
    model = CustomerSegmentationSpec(
        segments=segments,
        icp_notes=notes,
        geo_mix=geo,
    )
    model.empty = not any([model.segments, model.icp_notes, model.geo_mix])
    return model


def _extract_stickiness(text: str, sentences: list[str]) -> CustomerStickinessSpec:
    metrics = _parse_retention_metrics(text)
    cohorts = _parse_cohorts(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _STICKINESS_NEEDLES, limit=8), limit=4)
    # Prefer structured metric deltas over table noise.
    preferred: list[str] = []
    if metrics.get("retention_12m_pct") is not None:
        preferred.append(
            f"12-month customer retention is {metrics['retention_12m_pct']:g}%."
        )
    if metrics.get("nrr_pct") is not None and metrics.get("grr_pct") is not None:
        preferred.append(
            f"GRR {metrics['grr_pct']:g}% / NRR {metrics['nrr_pct']:g}%."
        )
    if metrics.get("logo_churn_pct") is not None:
        preferred.append(f"Logo churn elevated at {metrics['logo_churn_pct']:g}%.")
    notes = _dedupe([*preferred, *notes], limit=4)
    model = CustomerStickinessSpec(
        retention_metrics=metrics,
        cohorts=cohorts,
        stickiness_notes=notes,
    )
    model.empty = not any(
        [model.retention_metrics, model.cohorts, model.stickiness_notes]
    )
    return model


def _extract_satisfaction(
    text: str,
    sentences: list[str],
    *,
    prior_spec: dict | None,
) -> CustomerSatisfactionSpec:
    nps = _focal_nps(text)
    peers = _peer_nps_lines(text, prior_spec)
    sat_m = _SERVICE_SAT_RE.search(text or "")
    service_sat = float(sat_m.group(1)) if sat_m else None
    drivers = _parse_churn_drivers(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _SATISFACTION_NEEDLES, limit=8), limit=4)
    preferred: list[str] = []
    if nps is not None:
        preferred.append(f"Focal NPS is {nps:g}.")
    if service_sat is not None:
        preferred.append(f"Service satisfaction is {service_sat:g}%.")
    if drivers:
        top = drivers[0]
        preferred.append(
            f"Top churn driver: {top.driver} ({top.contribution_pct:g}%, {top.severity})."
        )
    notes = _dedupe([*preferred, *notes], limit=4)
    model = CustomerSatisfactionSpec(
        nps=nps,
        peer_nps=peers,
        service_satisfaction_pct=service_sat,
        churn_drivers=drivers,
        satisfaction_notes=notes,
    )
    model.empty = not any(
        [
            model.nps is not None,
            model.peer_nps,
            model.service_satisfaction_pct is not None,
            model.churn_drivers,
            model.satisfaction_notes,
        ]
    )
    return model


def _extract_buying(
    text: str,
    sentences: list[str],
    *,
    prior_spec: dict | None,
) -> BuyingBehaviorSpec:
    segments = _parse_segments(text)
    flags: list[str] = []
    buying: dict[str, float] = {}

    if segments:
        ranked = sorted(segments, key=lambda s: s.share_pct or 0.0, reverse=True)
        top = ranked[0]
        if top.share_pct is not None:
            flags.append(f"Top segment concentration: {top.name} at {top.share_pct:g}%.")
            if top.share_pct >= 30:
                flags.append(
                    f"Single-segment concentration flag — {top.name} exceeds 30% of mix."
                )
        shares = [s.share_pct for s in segments if s.share_pct is not None]
        hhi = sum(s * s for s in shares) if shares else None
    else:
        hhi = None

    online = _ONLINE_SHARE_RE.search(text or "")
    if online:
        buying["online_sales_pct"] = float(online.group(1))
    else:
        online_row = _ONLINE_ROW_RE.search(text or "")
        if online_row:
            vals = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", online_row.group(1))]
            # FY series + industry avg: drop trailing industry if sharply lower.
            if len(vals) >= 3 and vals[-1] < vals[-2] * 0.7:
                buying["online_sales_pct"] = vals[-2]
            elif vals:
                buying["online_sales_pct"] = vals[-1]
    if "online_sales_pct" in buying:
        flags.append(f"Online sales mix {buying['online_sales_pct']:g}%.")

    emi = _EMI_SHARE_RE.search(text or "")
    if emi:
        buying["emi_purchase_pct"] = float(emi.group(1))

    cac = _CAC_RE.search(text or "")
    if cac:
        buying["cac_inr"] = float(cac.group(1).replace(",", ""))

    ttp = _TIME_TO_PURCHASE_RE.search(text or "")
    if ttp:
        buying["time_to_purchase_days"] = float(ttp.group(1))

    fleet = re.search(
        r"(?i)Fleet segment\s*\((\d+(?:\.\d+)?)%\s+of revenue\)",
        text or "",
    )
    if fleet:
        buying["fleet_revenue_pct"] = float(fleet.group(1))
        flags.append(f"Fleet / B2B is {buying['fleet_revenue_pct']:g}% of revenue.")

    channel = _dedupe(
        _hits(
            [s for s in sentences if not _is_noisy_sentence(s)],
            ("digital-first", "experience center", "online funnel", "channel model", "dealer"),
            limit=5,
        ),
        limit=3,
    )
    notes = _dedupe(
        _hits(
            [s for s in sentences if not _is_noisy_sentence(s)],
            _BUYING_NEEDLES,
            limit=6,
        ),
        limit=4,
    )
    if prior_spec:
        wins = prior_spec.get("wins") or []
        if wins and isinstance(wins[0], str):
            notes = _dedupe([f"Share context · {wins[0]}", *notes], limit=4)

    model = BuyingBehaviorSpec(
        concentration_flags=_dedupe(flags, limit=5),
        channel_mix=channel,
        buying_metrics=buying,
        behavior_notes=notes,
        segment_hhi=round(hhi, 1) if hhi is not None else None,
    )
    model.empty = not any(
        [
            model.concentration_flags,
            model.channel_mix,
            model.buying_metrics,
            model.behavior_notes,
            model.segment_hhi is not None,
        ]
    )
    return model


def extract_customer_spec(
    slug: str,
    text: str,
    *,
    sources: list[str] | None = None,
    coverage: str = "missing",
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    """Return typed Customer Analysis spec JSON. Heuristic first; optional LLM refine."""
    from agetic_cdd_api.deep_dive_llm import refine_customer_spec

    clipped = (text or "")[:50_000]
    sentences = _sentences(clipped)
    src = list(sources or [])

    if slug == "customer_segmentation":
        model = _extract_segmentation(clipped, sentences)
    elif slug == "customer_stickiness":
        model = _extract_stickiness(clipped, sentences)
    elif slug == "customer_satisfaction":
        model = _extract_satisfaction(clipped, sentences, prior_spec=prior_spec)
    elif slug == "buying_behavior":
        model = _extract_buying(clipped, sentences, prior_spec=prior_spec)
    else:
        return {"slug": slug, "empty": True, "extractor": "none", "track": "C"}

    if coverage == "missing" and not clipped.strip():
        model.empty = True

    payload = model.model_dump(mode="json")
    payload["slug"] = slug
    payload["track"] = "C"
    payload["sources"] = src
    payload["coverage"] = coverage
    payload["extractor"] = "heuristic_v1"
    payload["llm_refined"] = False
    payload["metrics"] = _customer_metrics(slug, payload)

    # Hybrid pilot: satisfaction + buying only (flag + Gemini key).
    if slug in {"customer_satisfaction", "buying_behavior"}:
        payload = refine_customer_spec(slug, payload, text=clipped)
        payload["metrics"] = _customer_metrics(slug, payload)
    return payload


def _customer_metrics(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "customer_segmentation":
        conc = payload.get("concentration") if isinstance(payload.get("concentration"), dict) else {}
        return {
            "segment_count": len(payload.get("segments") or []),
            "geo_count": len(payload.get("geo_mix") or []),
            "axis_count": len(payload.get("segments_by_axis") or []),
            "contract_count": len(payload.get("largest_contracts") or []),
            "concentration_calculable": bool(conc.get("calculable")),
        }
    if slug == "customer_stickiness":
        metrics = payload.get("retention_metrics") or {}
        deltas = payload.get("retention_delta") or []
        falling = sum(
            1 for d in deltas
            if isinstance(d, dict) and d.get("is_finding")
        )
        return {
            "metric_count": len(metrics) if isinstance(metrics, dict) else 0,
            "cohort_count": len(payload.get("cohorts") or []),
            "contract_count": len(payload.get("contract_protections") or []),
            "falling_retention_findings": falling,
        }
    if slug == "customer_satisfaction":
        return {
            "has_nps": payload.get("nps") is not None,
            "has_csat": payload.get("service_satisfaction_pct") is not None,
            "churn_driver_count": len(payload.get("churn_drivers") or []),
            "ops_signal_count": len(payload.get("operational_signals") or []),
            "association_comparable": bool(
                (payload.get("churn_association") or {}).get("comparable")
                if isinstance(payload.get("churn_association"), dict)
                else False
            ),
            "research_needed": bool(
                (payload.get("research_design") or {}).get("needed")
                if isinstance(payload.get("research_design"), dict)
                else False
            ),
        }
    if slug == "buying_behavior":
        switching = (
            payload.get("switching")
            if isinstance(payload.get("switching"), dict)
            else {}
        )
        seasonality = (
            payload.get("seasonality")
            if isinstance(payload.get("seasonality"), dict)
            else {}
        )
        return {
            "flag_count": len(payload.get("concentration_flags") or []),
            "metric_count": len(payload.get("buying_metrics") or {}),
            "has_hhi": payload.get("segment_hhi") is not None,
            "map_count": len(payload.get("purchase_maps") or []),
            "crm_cycle_count": sum(
                1 for c in (payload.get("sales_cycles") or [])
                if isinstance(c, dict) and c.get("crm_evidenced")
            ),
            "switching_evidenced": bool(switching.get("evidenced")),
            "seasonality_measured": bool(seasonality.get("measured")),
        }
    return {}


def findings_from_customer_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if slug == "customer_segmentation":
        conc = spec.get("concentration") if isinstance(spec.get("concentration"), dict) else {}
        if conc:
            if conc.get("calculable"):
                bits = ["Concentration (parents)"]
                for label, key in (
                    ("T1", "top_1_share_pct"),
                    ("T5", "top_5_share_pct"),
                    ("T10", "top_10_share_pct"),
                ):
                    if conc.get(key):
                        bits.append(f"{label} {conc[key]}")
                out.append(" · ".join(bits))
            else:
                out.append("Concentration unassessed — ledger requested; risk rating withheld")
        for row in (spec.get("largest_contracts") or [])[:2]:
            if isinstance(row, dict) and row.get("name"):
                if not str(row["name"]).startswith("Information"):
                    out.append(
                        f"Contract: {row['name']}"
                        + (f" ({row.get('share_pct')})" if row.get("share_pct") else "")
                    )
        if not out:
            for row in spec.get("segments") or []:
                if not isinstance(row, dict):
                    continue
                bits = [row.get("name") or "Segment"]
                if row.get("share_pct") is not None:
                    try:
                        bits.append(f"{float(row['share_pct']):g}%")
                    except (TypeError, ValueError):
                        bits.append(f"{row['share_pct']}%")
                if row.get("avg_age"):
                    bits.append(f"age {row['avg_age']}")
                out.append(" — ".join(bits))
            out.extend(spec.get("icp_notes") or [])
            out.extend(
                g if isinstance(g, str) else str(g)
                for g in (spec.get("geo_mix") or [])
            )
    elif slug == "customer_stickiness":
        for row in (spec.get("retention_delta") or [])[:2]:
            if isinstance(row, dict) and row.get("is_finding"):
                out.append(
                    f"Finding · {row.get('metric') or 'retention'} "
                    f"{row.get('direction') or 'down'}: {row.get('magnitude') or ''}".strip()
                )
        same = (
            spec.get("retention_on_same_population")
            if isinstance(spec.get("retention_on_same_population"), dict)
            else {}
        )
        if same.get("grr") or same.get("nrr"):
            bits = ["Same-pop retention"]
            if same.get("grr"):
                bits.append(f"GRR {same['grr']}")
            if same.get("nrr"):
                bits.append(f"NRR {same['nrr']}")
            if same.get("logo_retention"):
                bits.append(f"Logo {same['logo_retention']}")
            out.append(" · ".join(bits))
        metrics = spec.get("retention_metrics") or {}
        if isinstance(metrics, dict) and not same:
            for key in (
                "retention_12m_pct",
                "grr_pct",
                "nrr_pct",
                "logo_churn_pct",
                "logo_retention_pct",
                "repurchase_pct",
            ):
                if key in metrics and metrics[key] is not None:
                    try:
                        out.append(f"{key}: {float(metrics[key]):g}")
                    except (TypeError, ValueError):
                        out.append(f"{key}: {metrics[key]}")
        for row in (spec.get("cohorts") or [])[:3]:
            if isinstance(row, dict) and row.get("cohort"):
                m12 = row.get("m12_retention_pct")
                bit = f"Cohort {row['cohort']}"
                if m12 is not None:
                    try:
                        bit += f" · M12 {float(m12):g}%"
                    except (TypeError, ValueError):
                        bit += f" · M12 {m12}%"
                out.append(bit)
        cliff = spec.get("renewal_cliff") if isinstance(spec.get("renewal_cliff"), dict) else {}
        if cliff.get("material_share_pct") and not str(cliff["material_share_pct"]).startswith("Information"):
            out.append(f"Renewal cliff: {cliff.get('material_share_pct')} in {cliff.get('window') or 'window'}")
        if not out:
            out.extend(spec.get("stickiness_notes") or [])
    elif slug == "customer_satisfaction":
        if spec.get("nps") is not None:
            out.append(f"NPS {spec['nps']:g}")
        if spec.get("service_satisfaction_pct") is not None:
            out.append(f"Service satisfaction {spec['service_satisfaction_pct']:g}%")
        for row in spec.get("churn_drivers") or []:
            if not isinstance(row, dict):
                continue
            bits = [row.get("driver") or "Driver"]
            if row.get("contribution_pct") is not None:
                bits.append(f"{row['contribution_pct']:g}%")
            if row.get("severity"):
                bits.append(str(row["severity"]))
            out.append(" — ".join(bits))
        assoc = (
            spec.get("churn_association")
            if isinstance(spec.get("churn_association"), dict)
            else {}
        )
        if assoc.get("comparable"):
            out.append("Service↔churn association (not causation unless evidenced)")
        research = (
            spec.get("research_design")
            if isinstance(spec.get("research_design"), dict)
            else {}
        )
        if research.get("needed"):
            out.append("Research design proposed — sentiment evidence thin")
        if not out:
            out.extend(spec.get("satisfaction_notes") or [])
    elif slug == "buying_behavior":
        maps = spec.get("purchase_maps") or []
        if maps:
            out.append(f"{len(maps)} segment purchase map(s)")
        cycles = spec.get("sales_cycles") or []
        crm_n = sum(1 for c in cycles if isinstance(c, dict) and c.get("crm_evidenced"))
        if crm_n:
            out.append(f"{crm_n} segment cycle(s) CRM-evidenced")
        switching = (
            spec.get("switching")
            if isinstance(spec.get("switching"), dict)
            else {}
        )
        if switching.get("evidenced"):
            out.append("Switching triggers evidenced (say vs did)")
        seasonality = (
            spec.get("seasonality")
            if isinstance(spec.get("seasonality"), dict)
            else {}
        )
        if seasonality.get("measured"):
            out.append("Seasonality measured")
        elif maps or crm_n or switching.get("evidenced"):
            out.append("Seasonality not asserted — data thin")
        out.extend(spec.get("concentration_flags") or [])
        out.extend(spec.get("channel_mix") or [])
        metrics = spec.get("buying_metrics") or {}
        if isinstance(metrics, dict):
            for key, val in list(metrics.items())[:4]:
                try:
                    out.append(f"{key}: {float(val):g}")
                except (TypeError, ValueError):
                    out.append(f"{key}: {val}")
        if spec.get("segment_hhi") is not None:
            out.append(f"Segment HHI {spec['segment_hhi']:g}")
        if not out:
            out.extend(spec.get("behavior_notes") or [])

    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())
    return deduped
