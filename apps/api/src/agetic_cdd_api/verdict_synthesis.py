"""Slice 3 — Stage C Final Verdict extractors (IC Synthesis + Recommendation)."""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.verdict_risks import prepare_verdict_risk_text

STAGE_C_SLUGS: frozenset[str] = frozenset({"ic_synthesis", "recommendation"})

_OVERALL_RATING_RE = re.compile(
    r"(?i)OVERALL\s+([\d.]+)\s*/\s*5\s+([A-Za-z][A-Za-z\s—\-]+?)(?:\s+Disclaimer|\s*$)"
)
_RATING_SECTION_RE = re.compile(
    r"(?i)Overall Investment Rating(.+?)(?:\bOVERALL\b|Disclaimer|$)",
    re.DOTALL,
)
_KNOWN_DIMENSIONS: tuple[str, ...] = (
    "Financial Health",
    "Market Opportunity",
    "Competitive Position",
    "Operational Maturity",
    "Technology & IP",
    "ESG Profile",
    "Management Quality",
)
_KNOWN_DIMENSION_ALT = "|".join(re.escape(name) for name in _KNOWN_DIMENSIONS)
_DIMENSION_LINE_RE = re.compile(
    rf"(?i)\b({_KNOWN_DIMENSION_ALT}|"
    r"[A-Z][a-z]+(?:\s+(?:&|[A-Z][a-z]+)){{1,4}})\s+"
    r"([\d.]+)\s*/\s*5\s+"
    rf"(.+?)(?=\s+(?:{_KNOWN_DIMENSION_ALT}|OVERALL)\b|Disclaimer|$)",
    re.DOTALL,
)
_PILLAR_SECTION_RE = re.compile(
    r"(?i)Investment Pillars\s+(.+?)(?=Financial Value Creation|Investment Risks|"
    r"Overall Investment Rating|Verdict\b|Key Monitoring|$)",
    re.DOTALL,
)
_KNOWN_PILLARS: tuple[str, ...] = (
    "Technology-First Positioning",
    "Vertical Integration Strategy",
    "Scale Advantage",
    "Brand Equity Among Youth",
    "Ecosystem Monetization",
    "Cloud Platform Expansion",
    "Partner Channel Scale",
)
_PILLAR_ENTRY_RE = re.compile(
    r"((?-i:[A-Z][A-Za-z0-9\-]+(?:\s+(?:&|(?-i:[A-Z][A-Za-z0-9\-]+))){1,5}))\s+"
    r"((?-i:[A-Z])[^\n]{15,220}?)"
    r"(?=\s+(?-i:[A-Z][A-Za-z0-9\-]+(?:\s+(?:&|[A-Z][A-Za-z0-9\-]+)){1,4})\s+(?-i:[A-Z])"
    r"|\s*Financial Value|\s*Investment Risks|\s*Overall Investment|$)",
    re.DOTALL,
)
_PILLAR_NAME_REJECT = re.compile(
    r"(?i)^(Metric|Executive|Organizational|Supply\s+Chain|Commentary|Financial|"
    r"Overall|Dimension|Diligence|Review|Section|Integration|Equity)|FY20|\bYoY\b"
)
_MONITOR_SECTION_RE = re.compile(
    r"(?i)Key Monitoring Metrics(?:\s+for Investors)?(.+?)(?:Disclaimer|$)",
    re.DOTALL,
)
_MONITOR_METRIC_RE = re.compile(
    r"(?i)\b("
    r"NRR|GRR|Logo Churn|Gross Margin|EBITDA Margin(?:\s*\([^)]+\))?|"
    r"Monthly Production(?:\s*\([^)]+\))?|Service Satisfaction Score|"
    r"Battery Incident Rate(?:\s*\([^)]+\))?|FAME-II Recovery Outcome(?:\s*\([^)]+\))?|"
    r"Net Dollar Retention|Gross Logo Churn|"
    r"(?-i:[A-Z][A-Za-z0-9]+(?:\s+(?-i:[A-Z][A-Za-z0-9]+)){0,4})"
    r"(?:\s*\([^)]{0,30}\))?)\s+"
    r"(INR\s+[\d.]+\s+Cr(?:\s+at\s+risk)?|[\d,]+(?:\.\d+)?%?(?:\s+target)?)\s+"
    r"([<>]=?\s*[\d,.]+%?|Full\s+[A-Za-z]+(?:\s+[A-Za-z]+){0,3})\s+"
    r"([<>]=?\s*[\d,.]+%?|Full\s+[A-Za-z]+(?:\s+[A-Za-z]/?){0,4})"
)
_MONITOR_HEADER_TOKENS = frozenset(
    {
        "metric",
        "current",
        "trigger for concern",
        "trigger for confidence",
        "commentary",
        "key monitoring metrics",
        "for investors",
        "confidence",
        "concern",
    }
)
_RISK_SECTION_RE = re.compile(
    r"(?i)Investment Risks\s+(.+?)(?=\s+Verdict\b|\s+Key Monitoring|"
    r"\s+Overall Investment|\s*$)",
    re.DOTALL,
)
_KNOWN_RISKS: tuple[str, ...] = (
    "Subsidy reduction / FAME-III delay",
    "OEM counter-attack (TVS, Bajaj)",
    "Battery cost plateau",
    "Execution failure at scale",
    "Capital market downturn",
    "China supply chain disruption",
    "Customer trust erosion",
)
_RISK_ROW_RE = re.compile(
    r"((?-i:[A-Z])[A-Za-z0-9 /&\-\(\),]{3,90}?)\s+"
    r"(High|Medium|Low)\s+(High|Medium|Low)\s+"
    r"((?:[A-Za-z0-9][A-Za-z0-9&+\-/]*(?:\s+[A-Za-z0-9&+\-/]+){0,5}?))"
    r"(?=\s+(?-i:[A-Z])[A-Za-z0-9 /&\-\(\),]{3,60}?\s+(?:High|Medium|Low)\s+(?:High|Medium|Low)"
    r"|\s+Verdict\b|\s*$)",
    re.IGNORECASE,
)
_RISK_HEADER_REJECT = re.compile(
    r"(?i)^(Risk Factor|Probability|Impact|Mitigation|Insight|Key risk|factors|IPO cash)"
)
_RISK_AFTER_NAME_RE = re.compile(
    r"(?i)^(High|Medium|Low)\s+(High|Medium|Low)\s+(.+)$"
)
_VERDICT_RE = re.compile(r"(?i)Verdict\s+(.+?)(?=\s+Disclaimer|\s+D2\.|\s*$)")
_POSITIVE_BULLET_RE = re.compile(
    r"(?i)(?:Key Positive Indicators)[\s\S]{0,40}?(?:[\x7f•\-]\s*)?"
    r"((?-i:[A-Z])[^.]{20,160}\.)"
)
_CONCERN_BULLET_RE = re.compile(
    r"(?i)(?:Key Risks?\s*&\s*Concerns)[\s\S]{0,40}?(?:[\x7f•\-]\s*)?"
    r"((?-i:[A-Z])[^.]{20,160}\.)"
)
_IRR_RE = re.compile(r"(?i)\bIRR\b[^\d]{0,20}([\d.]+)\s*%")
_MOIC_RE = re.compile(r"(?i)\bMOIC\b[^\d]{0,20}([\d.]+)\s*x")
_STRUCTURE_RE = re.compile(
    r"(?i)(staged investment[^.]*|earnout[^.]*|cash\s*/\s*stock[^.]*|"
    r"performance milestones[^.]*|recommended deal structure[^.]*)"
)


def _dedupe_dict_rows(
    left: list | None,
    right: list | None,
    *,
    key: str,
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in (left or []) + (right or []):
        if not isinstance(row, dict):
            continue
        token = str(row.get(key) or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(dict(row))
        if len(out) >= limit:
            break
    return out


def _parse_dimensions(blob: str) -> list[dict[str, Any]]:
    section = _RATING_SECTION_RE.search(blob)
    if not section:
        return []
    scope = section.group(1)
    dimensions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _DIMENSION_LINE_RE.finditer(scope):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        # Reject header bleed and lowercase-leading fragments ("nascent ESG Profile").
        if not name or not name[0].isupper():
            continue
        key = name.lower()
        if key in seen or key in {"overall", "dimension", "rating", "commentary"}:
            continue
        if name.lower().startswith(("commentary", "dimension", "rating")):
            continue
        score = _safe_float(match.group(2))
        if score is None or score > 5:
            continue
        seen.add(key)
        dimensions.append(
            {
                "dimension": name,
                "score_1_5": score,
                "commentary": _clip(match.group(3), 120),
            }
        )
    return dimensions[:8]


def _parse_pillars(blob: str) -> list[dict[str, str]]:
    section = _PILLAR_SECTION_RE.search(blob)
    if not section:
        return []
    body = re.sub(r"\s+", " ", section.group(1)).strip()
    hits: list[tuple[int, int, str]] = []
    for name in _KNOWN_PILLARS:
        for match in re.finditer(re.escape(name), body, flags=re.IGNORECASE):
            hits.append((match.start(), match.end(), body[match.start() : match.end()]))
    hits.sort(key=lambda item: item[0])
    pillars: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, (start, end, name) in enumerate(hits):
        key = name.lower()
        if key in seen:
            continue
        detail_end = hits[idx + 1][0] if idx + 1 < len(hits) else len(body)
        detail = body[end:detail_end].strip(" .;:")
        if len(detail) < 12:
            continue
        seen.add(key)
        pillars.append({"name": name, "detail": _clip(detail, 180)})
        if len(pillars) >= 6:
            return pillars

    if pillars:
        return pillars

    # Generic Title-Case fallback for non-Test2 packs.
    for match in _PILLAR_ENTRY_RE.finditer(body):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        key = name.lower()
        if not name or key in seen or len(name) < 6 or len(name.split()) < 2:
            continue
        if _PILLAR_NAME_REJECT.search(name):
            continue
        detail = _clip(match.group(2), 180)
        if detail.lower().startswith(("summary,", "diligence,", "health ")):
            continue
        seen.add(key)
        pillars.append({"name": name, "detail": detail})
        if len(pillars) >= 6:
            break
    return pillars


def _parse_monitoring_metrics(blob: str) -> list[dict[str, str]]:
    section = _MONITOR_SECTION_RE.search(blob)
    if not section:
        return []
    scope = section.group(1)
    scope = re.sub(
        r"(?i)^\s*Metric\s+Current\s+Trigger for Concern\s+Trigger for Confidence\s*",
        "",
        scope,
    )
    monitoring: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _MONITOR_METRIC_RE.finditer(scope):
        metric = re.sub(r"\s+", " ", match.group(1)).strip()
        key = metric.lower()
        if not metric or key in seen or key in _MONITOR_HEADER_TOKENS:
            continue
        if any(token in key for token in ("trigger", "confidence", "concern", "current", "metric")):
            continue
        if not re.search(r"[A-Za-z]", metric) or not re.search(r"\d", match.group(2)):
            continue
        if len(metric.split()) > 6:
            continue
        seen.add(key)
        monitoring.append(
            {
                "metric": metric,
                "current": match.group(2).strip(),
                "concern_trigger": match.group(3).strip(),
                "confidence_trigger": match.group(4).strip(),
            }
        )
        if len(monitoring) >= 8:
            break
    return monitoring


def _parse_primary_risks(blob: str) -> list[dict[str, str]]:
    section = _RISK_SECTION_RE.search(blob)
    if not section:
        return []
    body = section.group(1)
    body = re.sub(r"(?i)■?\s*Insight Snapshot:[^.]*\.", " ", body)
    body = re.sub(
        r"(?i)Risk Factor\s+Probability\s+Impact\s+Mitigation",
        " ",
        body,
    )
    body = re.sub(r"\s+", " ", body).strip()

    hits: list[tuple[int, int, str]] = []
    for name in _KNOWN_RISKS:
        for match in re.finditer(re.escape(name), body, flags=re.IGNORECASE):
            hits.append((match.start(), match.end(), body[match.start() : match.end()]))
    hits.sort(key=lambda item: item[0])

    risks: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, (_start, end, name) in enumerate(hits):
        key = name.lower()
        if key in seen:
            continue
        segment_end = hits[idx + 1][0] if idx + 1 < len(hits) else len(body)
        segment = body[end:segment_end].strip(" .;:")
        parsed = _RISK_AFTER_NAME_RE.match(segment)
        if not parsed:
            continue
        mitigation = re.sub(r"\s+", " ", parsed.group(3)).strip(" .;:")
        if len(mitigation) < 4:
            continue
        seen.add(key)
        risks.append(
            {
                "risk": name,
                "probability": parsed.group(1).title(),
                "impact": parsed.group(2).title(),
                "mitigation": _clip(mitigation, 100),
            }
        )
        if len(risks) >= 8:
            return risks

    if risks:
        return risks

    for match in _RISK_ROW_RE.finditer(body):
        name = re.sub(r"\s+", " ", match.group(1)).strip(" .;:")
        if len(name) < 4 or _RISK_HEADER_REJECT.search(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        mitigation = re.sub(r"\s+", " ", match.group(4)).strip(" .;:")
        if len(mitigation) < 4:
            continue
        seen.add(key)
        risks.append(
            {
                "risk": name,
                "probability": match.group(2).title(),
                "impact": match.group(3).title(),
                "mitigation": _clip(mitigation, 100),
            }
        )
        if len(risks) >= 8:
            break
    return risks


def _clip(text: str, limit: int = 220) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(value).strip())
    if not cleaned or cleaned in {".", "-", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _merge_str_lists(
    left: list[str] | None,
    right: list[str] | None,
    *,
    limit: int = 8,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in (left or []) + (right or []):
        if not isinstance(item, str):
            continue
        bit = item.strip()
        key = bit.lower()
        if bit and key not in seen:
            seen.add(key)
            out.append(bit)
        if len(out) >= limit:
            break
    return out


def _upstream_summary(spec: dict | None) -> str | None:
    if not isinstance(spec, dict) or spec.get("empty"):
        return None
    findings = spec.get("valuation_flags") or spec.get("retention_risk_flags") or []
    for flag in findings:
        if isinstance(flag, str) and flag.strip():
            return flag.strip()
    metrics = spec.get("metrics") if isinstance(spec.get("metrics"), dict) else {}
    if metrics:
        bits = [f"{k}={v}" for k, v in list(metrics.items())[:3] if v is not None]
        if bits:
            return ", ".join(bits)
    return None


def _parse_ic_fields(text: str) -> dict[str, Any]:
    blob = prepare_verdict_risk_text(text or "")
    overall = _OVERALL_RATING_RE.search(blob)

    risks = _parse_primary_risks(blob)

    verdict_match = _VERDICT_RE.search(blob)
    verdict_text = _clip(verdict_match.group(1), 360) if verdict_match else None

    positives = [_clip(m.group(1), 160) for m in _POSITIVE_BULLET_RE.finditer(blob)][:5]
    concerns = [
        _clip(m.group(1), 160)
        for m in _CONCERN_BULLET_RE.finditer(blob)
        if "insight snapshot" not in m.group(1).lower()
    ][:5]

    return {
        "overall_score_1_5": _safe_float(overall.group(1)) if overall else None,
        "overall_label": re.sub(r"\s+", " ", overall.group(2)).strip(" —-") if overall else None,
        "dimensions": _parse_dimensions(blob),
        "investment_pillars": _parse_pillars(blob),
        "primary_risks": risks[:8],
        "verdict_narrative": verdict_text,
        "strengths": positives,
        "concerns": concerns,
    }


def _merge_ic_fields(base: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if not base:
        return dict(incoming)
    merged = dict(base)
    for key in ("overall_score_1_5", "overall_label", "verdict_narrative"):
        if incoming.get(key) is not None:
            merged[key] = incoming[key]
    merged["dimensions"] = _dedupe_dict_rows(
        base.get("dimensions"), incoming.get("dimensions"), key="dimension", limit=8
    )
    merged["investment_pillars"] = _dedupe_dict_rows(
        base.get("investment_pillars"), incoming.get("investment_pillars"), key="name", limit=6
    )
    merged["primary_risks"] = _dedupe_dict_rows(
        base.get("primary_risks"), incoming.get("primary_risks"), key="risk", limit=8
    )
    merged["strengths"] = _merge_str_lists(base.get("strengths"), incoming.get("strengths"), limit=5)
    merged["concerns"] = _merge_str_lists(base.get("concerns"), incoming.get("concerns"), limit=5)
    return merged


def _parse_recommendation_fields(text: str) -> dict[str, Any]:
    blob = prepare_verdict_risk_text(text or "")
    irr = _IRR_RE.search(blob)
    moic = _MOIC_RE.search(blob)
    structure = _STRUCTURE_RE.search(blob)

    return {
        "irr_pct": _safe_float(irr.group(1)) if irr else None,
        "moic_x": _safe_float(moic.group(1)) if moic else None,
        "deal_structure": _clip(structure.group(1), 200) if structure else None,
        "monitoring_metrics": _parse_monitoring_metrics(blob),
    }


def _merge_recommendation_fields(
    base: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    if not base:
        return dict(incoming)
    merged = dict(base)
    for key in ("irr_pct", "moic_x", "deal_structure"):
        if incoming.get(key) is not None:
            merged[key] = incoming[key]
    merged["monitoring_metrics"] = _dedupe_dict_rows(
        base.get("monitoring_metrics"),
        incoming.get("monitoring_metrics"),
        key="metric",
        limit=8,
    )
    return merged


def _decide_go_no_go(
    fields: dict[str, Any],
    *,
    execution_risk: dict | None,
    valuation_modeling: dict | None,
) -> tuple[str, str, float | None]:
    label = (fields.get("overall_label") or "").lower()
    score = fields.get("overall_score_1_5")
    narrative = (fields.get("verdict_narrative") or "").lower()

    if "no-go" in label or "no go" in label or "pass" == label.strip():
        decision = "No-Go"
    elif "conditional" in label or "monitor" in label:
        decision = "Conditional Go"
    elif "positive" in label or "proceed" in label or "go" in label:
        decision = "Go"
    elif score is not None:
        if score >= 3.5:
            decision = "Go"
        elif score >= 2.5:
            decision = "Conditional Go"
        else:
            decision = "No-Go"
    elif "staged investment" in narrative or "high-risk, high-reward" in narrative:
        decision = "Conditional Go"
    else:
        decision = "Conditional Go"

    # Valuation overhang: large IPO premium vs DCF → keep Conditional when otherwise Go.
    if decision == "Go" and isinstance(valuation_modeling, dict):
        dcf = valuation_modeling.get("dcf") if isinstance(valuation_modeling.get("dcf"), dict) else {}
        for scenario in dcf.get("scenarios") or []:
            if not isinstance(scenario, dict):
                continue
            if scenario.get("label") == "Base Case":
                disc = scenario.get("premium_discount_vs_ipo_pct")
                if isinstance(disc, (int, float)) and disc <= -40:
                    decision = "Conditional Go"
                break

    if isinstance(execution_risk, dict) and not execution_risk.get("empty"):
        hc = execution_risk.get("overall_human_capital_risk_1_10")
        if isinstance(hc, (int, float)) and hc >= 8 and decision == "Go":
            decision = "Conditional Go"

    confidence = "medium"
    if score is not None:
        if score >= 4.0 or score <= 1.5:
            confidence = "high"
        elif 2.5 <= score <= 3.5:
            confidence = "medium"
        else:
            confidence = "medium-low"
    elif fields.get("verdict_narrative"):
        confidence = "medium"
    else:
        confidence = "low"

    return decision, confidence, score


def _enrich_from_upstream(
    fields: dict[str, Any],
    *,
    execution_risk: dict | None,
    compensation_alignment: dict | None,
    trading_comps: dict | None,
    precedent_transactions: dict | None,
    valuation_modeling: dict | None,
) -> dict[str, Any]:
    strengths = list(fields.get("strengths") or [])
    concerns = list(fields.get("concerns") or [])
    pillars = list(fields.get("investment_pillars") or [])
    risks = list(fields.get("primary_risks") or [])

    for slug, spec in (
        ("execution_risk", execution_risk),
        ("compensation_alignment", compensation_alignment),
        ("trading_comps", trading_comps),
        ("precedent_transactions", precedent_transactions),
        ("valuation_modeling", valuation_modeling),
    ):
        bit = _upstream_summary(spec)
        if not bit:
            continue
        # Upstream summaries are decision context — never promote into strengths.
        concerns.append(f"{slug}: {bit}")

    if isinstance(valuation_modeling, dict) and not valuation_modeling.get("empty"):
        dcf = valuation_modeling.get("dcf") if isinstance(valuation_modeling.get("dcf"), dict) else {}
        if dcf.get("implied_share_price_inr") is not None:
            concerns.append(
                f"DCF base share INR {dcf['implied_share_price_inr']:.1f} vs IPO reference"
            )
        for flag in valuation_modeling.get("valuation_flags") or []:
            if isinstance(flag, str) and flag not in concerns:
                concerns.append(flag)

    if isinstance(execution_risk, dict) and not execution_risk.get("empty"):
        for flag in execution_risk.get("retention_risk_flags") or []:
            if isinstance(flag, str):
                risks.append(
                    {
                        "risk": _clip(flag, 80),
                        "probability": "High",
                        "impact": "High",
                        "mitigation": "Succession / retention plan",
                    }
                )

    if isinstance(trading_comps, dict) and not trading_comps.get("empty"):
        for flag in trading_comps.get("valuation_flags") or []:
            if isinstance(flag, str) and flag not in concerns:
                concerns.append(flag)

    # Strengths stay VDR-derived positives only (already in `strengths`).
    fields["strengths"] = _merge_str_lists([], strengths, limit=6)
    fields["concerns"] = _merge_str_lists(
        [],
        [c for c in concerns if "insight snapshot" not in c.lower()],
        limit=6,
    )
    fields["investment_pillars"] = pillars[:6]
    # Dedupe risks by name
    seen: set[str] = set()
    deduped_risks: list[dict[str, str]] = []
    for row in risks:
        if not isinstance(row, dict):
            continue
        key = str(row.get("risk") or "").lower()
        if key and key not in seen:
            seen.add(key)
            deduped_risks.append(row)
        if len(deduped_risks) >= 8:
            break
    fields["primary_risks"] = deduped_risks
    return fields


def _build_ic_synthesis_spec(
    fields: dict[str, Any],
    *,
    sources: list[str],
    coverage: str,
    execution_risk: dict | None = None,
    compensation_alignment: dict | None = None,
    trading_comps: dict | None = None,
    precedent_transactions: dict | None = None,
    valuation_modeling: dict | None = None,
) -> dict[str, Any]:
    enriched = _enrich_from_upstream(
        dict(fields),
        execution_risk=execution_risk,
        compensation_alignment=compensation_alignment,
        trading_comps=trading_comps,
        precedent_transactions=precedent_transactions,
        valuation_modeling=valuation_modeling,
    )
    decision, confidence, score = _decide_go_no_go(
        enriched,
        execution_risk=execution_risk,
        valuation_modeling=valuation_modeling,
    )

    empty = not (
        enriched.get("overall_score_1_5")
        or enriched.get("investment_pillars")
        or enriched.get("verdict_narrative")
        or enriched.get("strengths")
        or enriched.get("primary_risks")
        or any(
            isinstance(s, dict) and not s.get("empty")
            for s in (
                execution_risk,
                compensation_alignment,
                trading_comps,
                precedent_transactions,
                valuation_modeling,
            )
        )
    )

    return {
        "empty": empty,
        "extractor": "heuristic_v1",
        "fv_code": "FV-06",
        "stage": "C",
        "document": "Final Investment Memo (Go/No-Go)",
        "sources": sources,
        "coverage": coverage,
        "overall_score_1_5": score,
        "overall_label": enriched.get("overall_label"),
        "go_no_go": decision,
        "confidence": confidence,
        "dimensions": enriched.get("dimensions") or [],
        "investment_pillars": enriched.get("investment_pillars") or [],
        "primary_risks": enriched.get("primary_risks") or [],
        "strengths": enriched.get("strengths") or [],
        "concerns": enriched.get("concerns") or [],
        "verdict_narrative": enriched.get("verdict_narrative"),
        "value_creation_thesis": enriched.get("verdict_narrative"),
        "consumes_execution_risk": bool(execution_risk),
        "consumes_compensation_alignment": bool(compensation_alignment),
        "consumes_trading_comps": bool(trading_comps),
        "consumes_precedent_transactions": bool(precedent_transactions),
        "consumes_valuation_modeling": bool(valuation_modeling),
        "metrics": {
            "overall_score_1_5": score,
            "go_no_go": decision,
            "confidence": confidence,
            "pillar_count": len(enriched.get("investment_pillars") or []),
            "risk_count": len(enriched.get("primary_risks") or []),
        },
    }


def _scenario_returns_from_valuation(valuation_modeling: dict | None) -> list[dict[str, Any]]:
    """Return VDR-evidenced IRR/MOIC only — never invent a Bear/Base/Bull ladder."""
    out: list[dict[str, Any]] = []
    if not isinstance(valuation_modeling, dict):
        return out

    # Explicit returns already on the valuation pack
    for row in valuation_modeling.get("returns_by_scenario") or []:
        if not isinstance(row, dict):
            continue
        if row.get("irr_pct") is None and row.get("moic_x") is None:
            continue
        out.append(
            {
                "scenario": str(row.get("scenario") or row.get("label") or "Scenario"),
                "irr_pct": row.get("irr_pct"),
                "moic_x": row.get("moic_x"),
                "equity_value_per_share_inr": row.get("equity_value_per_share_inr"),
                "premium_discount_vs_ipo_pct": row.get("premium_discount_vs_ipo_pct"),
            }
        )
    if out:
        return out[:4]

    dcf = valuation_modeling.get("dcf") if isinstance(valuation_modeling.get("dcf"), dict) else {}
    for scenario in dcf.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        irr = scenario.get("irr_pct")
        moic = scenario.get("moic_x")
        if irr is None and moic is None:
            continue
        label = str(scenario.get("label") or scenario.get("scenario") or "Scenario")
        out.append(
            {
                "scenario": label,
                "irr_pct": irr,
                "moic_x": moic,
                "equity_value_per_share_inr": scenario.get("equity_value_per_share_inr"),
                "premium_discount_vs_ipo_pct": scenario.get("premium_discount_vs_ipo_pct"),
            }
        )
    return out[:4]


def _build_recommendation_spec(
    fields: dict[str, Any],
    *,
    sources: list[str],
    coverage: str,
    ic_synthesis: dict | None = None,
    precedent_transactions: dict | None = None,
    valuation_modeling: dict | None = None,
) -> dict[str, Any]:
    returns = _scenario_returns_from_valuation(valuation_modeling)
    if fields.get("irr_pct") is not None or fields.get("moic_x") is not None:
        for row in returns:
            if row.get("scenario") == "Base Case":
                if fields.get("irr_pct") is not None:
                    row["irr_pct"] = fields["irr_pct"]
                if fields.get("moic_x") is not None:
                    row["moic_x"] = fields["moic_x"]

    structure = fields.get("deal_structure")
    if not structure and isinstance(ic_synthesis, dict):
        narrative = (ic_synthesis.get("verdict_narrative") or "").lower()
        if "staged" in narrative:
            structure = "Staged investment with performance milestones"
        elif ic_synthesis.get("go_no_go") == "No-Go":
            structure = "Do not proceed — no transaction structure proposed"
        else:
            structure = "Conditional entry with staged capital and milestone gates"
    if not structure:
        structure = "Staged investment with performance milestones"

    conditions: list[str] = []
    if isinstance(ic_synthesis, dict):
        for risk in ic_synthesis.get("primary_risks") or []:
            if not isinstance(risk, dict):
                continue
            name = (risk.get("risk") or "").strip()
            mit = (risk.get("mitigation") or "").strip()
            # Skip truncated / header-bleed mitigations.
            if not name or not mit or len(mit) < 8:
                continue
            if mit.endswith(("&", "+", "/", "—", "-")):
                continue
            conditions.append(f"CP: mitigate {name} via {mit}")
            if len(conditions) >= 4:
                break
        for concern in ic_synthesis.get("concerns") or []:
            if not isinstance(concern, str):
                continue
            low = concern.lower()
            if "insight snapshot" in low or low.startswith(
                (
                    "execution_risk:",
                    "trading_comps:",
                    "valuation_modeling:",
                    "precedent_transactions:",
                    "compensation_alignment:",
                    "dcf ",
                )
            ):
                continue
            if "vs ipo" in low or low.startswith("dcf"):
                continue
            conditions.append(f"CP: address {_clip(concern, 100)}")
            if len(conditions) >= 6:
                break
    if isinstance(precedent_transactions, dict) and not precedent_transactions.get("empty"):
        ev = precedent_transactions.get("implied_ev_range_usd_b") or {}
        if ev.get("low") is not None and ev.get("high") is not None:
            conditions.append(
                f"CP: bid within precedent EV band USD {ev['low']:.2f}B–{ev['high']:.2f}B"
            )

    day_100: list[str] = []
    for metric in fields.get("monitoring_metrics") or []:
        if not isinstance(metric, dict):
            continue
        name = metric.get("metric")
        target = metric.get("confidence_trigger")
        if name and target:
            day_100.append(f"Day 0–100: improve {name} toward {target}")
        if len(day_100) >= 5:
            break
    if not day_100 and isinstance(ic_synthesis, dict):
        for pillar in ic_synthesis.get("investment_pillars") or []:
            if isinstance(pillar, dict) and pillar.get("name"):
                day_100.append(f"Day 0–100: advance {pillar['name']} workstream")
            if len(day_100) >= 4:
                break
    if not day_100:
        day_100 = [
            "Day 0–30: confirm service recovery plan and key-person retention",
            "Day 31–60: lock battery localization milestones and subsidy exposure",
            "Day 61–100: rebaseline NRR / churn vs investment thesis gates",
        ]

    go = None
    if isinstance(ic_synthesis, dict):
        go = ic_synthesis.get("go_no_go")

    empty = not (
        structure
        or returns
        or conditions
        or day_100
        or (isinstance(ic_synthesis, dict) and not ic_synthesis.get("empty"))
    )

    base_return = next((r for r in returns if r.get("scenario") == "Base Case"), returns[0] if returns else {})
    return {
        "empty": empty,
        "extractor": "heuristic_v1",
        "fv_code": "FV-07",
        "stage": "C",
        "document": "Transaction Structure & Returns Summary",
        "sources": sources,
        "coverage": coverage,
        "deal_structure": structure,
        "returns_by_scenario": returns[:4],
        "conditions_precedent": conditions[:8],
        "hundred_day_plan": day_100[:6],
        "aligned_go_no_go": go,
        "monitoring_metrics": fields.get("monitoring_metrics") or [],
        "consumes_ic_synthesis": bool(ic_synthesis),
        "consumes_precedent_transactions": bool(precedent_transactions),
        "consumes_valuation_modeling": bool(valuation_modeling),
        "metrics": {
            "base_irr_pct": base_return.get("irr_pct"),
            "base_moic_x": base_return.get("moic_x"),
            "cp_count": len(conditions),
            "plan_items": len(day_100),
            "go_no_go": go,
        },
    }


def merge_verdict_synthesis_spec(slug: str, base: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if not base:
        return dict(incoming)
    if incoming.get("empty"):
        return dict(base)
    if base.get("empty"):
        return dict(incoming)

    if slug == "ic_synthesis":
        merged = dict(incoming)
        for key in ("overall_score_1_5", "overall_label", "go_no_go", "confidence", "verdict_narrative"):
            if base.get(key) is not None and merged.get(key) is None:
                merged[key] = base[key]
        merged["investment_pillars"] = (base.get("investment_pillars") or []) + [
            p for p in (incoming.get("investment_pillars") or []) if p not in (base.get("investment_pillars") or [])
        ]
        merged["investment_pillars"] = merged["investment_pillars"][:6]
        merged["primary_risks"] = (base.get("primary_risks") or [])[:4] + (incoming.get("primary_risks") or [])[:4]
        merged["strengths"] = _merge_str_lists(base.get("strengths"), incoming.get("strengths"))
        merged["concerns"] = _merge_str_lists(base.get("concerns"), incoming.get("concerns"))
        merged["sources"] = _merge_str_lists(base.get("sources"), incoming.get("sources"), limit=4)
        merged["empty"] = False
        return merged

    if slug == "recommendation":
        merged = dict(incoming)
        for key in ("deal_structure", "aligned_go_no_go"):
            if base.get(key) and not merged.get(key):
                merged[key] = base[key]
        merged["returns_by_scenario"] = incoming.get("returns_by_scenario") or base.get("returns_by_scenario") or []
        merged["conditions_precedent"] = _merge_str_lists(
            base.get("conditions_precedent"),
            incoming.get("conditions_precedent"),
        )
        merged["hundred_day_plan"] = _merge_str_lists(
            base.get("hundred_day_plan"),
            incoming.get("hundred_day_plan"),
            limit=6,
        )
        merged["sources"] = _merge_str_lists(base.get("sources"), incoming.get("sources"), limit=4)
        merged["empty"] = False
        return merged

    return dict(incoming)


def extract_verdict_synthesis_spec(
    slug: str,
    text: str,
    *,
    sources: list[str],
    coverage: str,
    execution_risk: dict | None = None,
    compensation_alignment: dict | None = None,
    trading_comps: dict | None = None,
    precedent_transactions: dict | None = None,
    valuation_modeling: dict | None = None,
    ic_synthesis: dict | None = None,
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    if prior_spec and not prior_spec.get("empty"):
        partial = extract_verdict_synthesis_spec(
            slug,
            text,
            sources=sources,
            coverage=coverage,
            execution_risk=execution_risk,
            compensation_alignment=compensation_alignment,
            trading_comps=trading_comps,
            precedent_transactions=precedent_transactions,
            valuation_modeling=valuation_modeling,
            ic_synthesis=ic_synthesis,
            prior_spec=None,
        )
        return merge_verdict_synthesis_spec(slug, prior_spec, partial)

    normalized = prepare_verdict_risk_text(text)
    if slug == "ic_synthesis":
        return _build_ic_synthesis_spec(
            _parse_ic_fields(normalized),
            sources=sources,
            coverage=coverage,
            execution_risk=execution_risk,
            compensation_alignment=compensation_alignment,
            trading_comps=trading_comps,
            precedent_transactions=precedent_transactions,
            valuation_modeling=valuation_modeling,
        )
    if slug == "recommendation":
        return _build_recommendation_spec(
            _parse_recommendation_fields(normalized),
            sources=sources,
            coverage=coverage,
            ic_synthesis=ic_synthesis,
            precedent_transactions=precedent_transactions,
            valuation_modeling=valuation_modeling,
        )
    return {"empty": True, "document": slug}


def extract_verdict_synthesis_from_documents(
    slug: str,
    documents: list[tuple[str, str]],
    *,
    coverage: str,
    execution_risk: dict | None = None,
    compensation_alignment: dict | None = None,
    trading_comps: dict | None = None,
    precedent_transactions: dict | None = None,
    valuation_modeling: dict | None = None,
    ic_synthesis: dict | None = None,
) -> dict[str, Any]:
    sources: list[str] = []
    fields: dict[str, Any] | None = None
    for filename, text in documents:
        chunk = (text or "").strip()
        if not chunk:
            continue
        sources.append(filename)
        if slug == "ic_synthesis":
            fields = _merge_ic_fields(fields, _parse_ic_fields(chunk))
        elif slug == "recommendation":
            fields = _merge_recommendation_fields(fields, _parse_recommendation_fields(chunk))

    parsed = fields or (
        _parse_ic_fields("") if slug == "ic_synthesis" else _parse_recommendation_fields("")
    )
    if slug == "ic_synthesis":
        return _build_ic_synthesis_spec(
            parsed,
            sources=sources[:4],
            coverage=coverage,
            execution_risk=execution_risk,
            compensation_alignment=compensation_alignment,
            trading_comps=trading_comps,
            precedent_transactions=precedent_transactions,
            valuation_modeling=valuation_modeling,
        )
    if slug == "recommendation":
        return _build_recommendation_spec(
            parsed,
            sources=sources[:4],
            coverage=coverage,
            ic_synthesis=ic_synthesis,
            precedent_transactions=precedent_transactions,
            valuation_modeling=valuation_modeling,
        )
    return {"empty": True, "document": slug, "coverage": coverage, "sources": sources[:4]}


def findings_from_verdict_synthesis_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    if spec.get("empty"):
        return []
    out: list[str] = []
    if slug == "ic_synthesis":
        rec = spec.get("recommendation") if isinstance(spec.get("recommendation"), dict) else {}
        if rec.get("stance"):
            out.append(f"Stance: {str(rec['stance'])[:160]}")
        elif spec.get("go_no_go"):
            out.append(f"Stance: {spec['go_no_go']}")
        for d in (spec.get("case_depends_on") or [])[:2]:
            if isinstance(d, dict) and d.get("pillar"):
                out.append(f"Depends: {d['pillar']}")
        if not any(x.startswith("Depends:") for x in out):
            for pillar in spec.get("investment_pillars") or []:
                if isinstance(pillar, dict) and pillar.get("name"):
                    out.append(f"Depends: {pillar['name']}")
                if len(out) >= 4:
                    break
        blocking = [
            b for b in (spec.get("blockers") or [])
            if isinstance(b, dict) and b.get("blocks_decision")
        ]
        if blocking:
            out.append(f"OPEN BLOCKER: {str(blocking[0].get('item') or '')[:120]}")
        else:
            for risk in spec.get("primary_risks") or []:
                if isinstance(risk, dict) and risk.get("risk"):
                    out.append(f"Risk: {risk['risk']}")
                if len(out) >= 6:
                    break
        fin = spec.get("financial_picture") if isinstance(spec.get("financial_picture"), dict) else {}
        if fin.get("earnings_fallen_or_negative"):
            out.append("Financial: earnings negative/troughing")
        qv, rv = spec.get("quality_verdict"), spec.get("reliance_verdict")
        if qv or rv:
            out.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
    elif slug == "recommendation":
        for row in (spec.get("price_actions") or [])[:1]:
            if isinstance(row, dict) and row.get("action"):
                out.append(f"Price: {str(row['action'])[:160]}")
        for row in (spec.get("conditions_precedent_structured") or [])[:2]:
            if isinstance(row, dict) and row.get("action"):
                out.append(f"CP: {str(row['action'])[:160]}")
            elif isinstance(row, str):
                out.append(row)
        if not out and spec.get("deal_structure"):
            out.append(f"Structure: {spec['deal_structure']}")
        base = next(
            (
                r for r in (spec.get("returns_by_scenario") or [])
                if isinstance(r, dict) and str(r.get("scenario") or "").lower().startswith("base")
            ),
            None,
        )
        if isinstance(base, dict):
            if base.get("irr_pct") is not None and base.get("moic_x") is not None:
                out.append(f"Base returns: IRR {base['irr_pct']:.1f}% / MOIC {base['moic_x']:.1f}x")
        for cp in spec.get("conditions_precedent") or []:
            if isinstance(cp, str) and not any(cp[:40] in x for x in out):
                out.append(cp)
            if len(out) >= 6:
                break
        for item in spec.get("hundred_day_plan") or []:
            if isinstance(item, str):
                out.append(item)
            if len(out) >= 8:
                break
        open_block = [
            o for o in (spec.get("open_items") or [])
            if isinstance(o, dict) and o.get("blocks_decision")
        ]
        if open_block:
            out.append(f"OPEN BLOCKER: {str(open_block[0].get('item') or '')[:120]}")
        qv, rv = spec.get("quality_verdict"), spec.get("reliance_verdict")
        if qv or rv:
            out.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")

    seen: set[str] = set()
    deduped: list[str] = []
    for line in out:
        key = line.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(_clip(line, 220))
    return deduped[:8]
