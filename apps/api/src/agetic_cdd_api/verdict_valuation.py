"""Slice 2 — Stage B Final Verdict extractors (Trading Comps + Precedents + DCF)."""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.verdict_risks import prepare_verdict_risk_text

STAGE_B_SLUGS: frozenset[str] = frozenset(
    {"trading_comps", "precedent_transactions", "valuation_modeling"}
)

_SUBJECT_PEER_RE = re.compile(
    r"(?i)Ola Electric\s*\(Subject\)\s+\S+\s+([\d.]+)\s+"
    r"(?:N/M|N/A|\d+(?:\.\d+)?x)\s+"
    r"(?:\(neg\.\s*EBITDA\)\s+)?"
    r"([\d.]+)x\s+"
    r"([+\-]?\d+(?:\.\d+)?)%\s+"
    r"([\d.]+)%"
)
_MEDIAN_COMPS_RE = re.compile(
    r"(?i)Median\s*\(Ex-Subject,\s*Ex-N/M\)\s+[^\d]*"
    r"([\d.]+)x\s+([\d.]+)x\s+([+\-]?\d+(?:\.\d+)?)%\s+([\d.]+)%"
)
_IPO_EV_RE = re.compile(r"(?i)IPO Implied EV(?:\s*\([^)]+\))?\s+[^\d~]*~?\s*([\d.]+)\s*B")
_COMP_EV_RANGE_RE = re.compile(
    r"(?i)EV\s*/\s*Revenue\s+USD\s+~590M\s+Revenue\s+"
    r"([\d.]+)x\s+([\d.]+)x\s+([\d.]+)B\s+([\d.]+)B"
)
_PRECEDENT_MEDIAN_RE = re.compile(r"(?i)Median\s+([\d.]+)x\s+\+?\d+%")
_PRECEDENT_APPLIED_RE = re.compile(
    r"(?i)Applied Range\s*\(Ola Electric\)\s+([\d.]+)x\s*[–-]\s*([\d.]+)x"
)
_PRECEDENT_EV_RANGE_RE = re.compile(
    r"(?i)Implied EV Range\s*\(FY2024E Rev\)\s+USD\s+([\d.]+)B\s*[–-]\s*USD\s+([\d.]+)B"
)
_PRECEDENT_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_PRECEDENT_DEAL_RE = re.compile(
    rf"(?i)\b{_PRECEDENT_MONTH}\s+\d{{4}}\s+"
    r"([A-Z][A-Za-z0-9][A-Za-z0-9\s&\.\-]{0,50}?(?:\([^)]{0,40}\))?)\s+"
    r"(?:Strategic|PE|Hero|Greaves|SPAC|Private|Investors|Logistics|OEMs|Honda|Yamaha)"
    r"[^\n]{0,100}?"
    r"~?\s*USD\s+([\d.]+)\s*([MB])\s+"
    r"~?\s*([\d.]+)x\s+Rev"
)
_PRECEDENT_TARGET_REJECT = re.compile(
    r"(?i)^(date|target|acquirer|geography|deal|transaction|implied|fy\d|jan|feb|mar)"
)
_DCF_WACC_RE = re.compile(r"(?i)WACC\s*\(Base\)\s+([\d.]+)%")
_DCF_EV_RE = re.compile(r"(?i)Enterprise Value\s*\(DCF\)\s+([\d,]+)\s+([\d.]+)B")
_DCF_EQUITY_RE = re.compile(r"(?i)Equity Value\s*\(DCF\)\s+([\d,]+)\s+([\d.]+)B")
_DCF_SHARE_RE = re.compile(
    r"(?i)Implied Share Price\s*\(DCF Base\)\s+INR\s+([\d.]+)"
)
_SCENARIO_RE = re.compile(
    r"(?i)(Bear Case|Base Case|Bull Case|IPO Market Price)\s*"
    r"\([^)]*\)\s+([\d,]+)\s+([\d.]+)B\s+INR\s+([\d.]+)\s+([+\-]?\d+(?:\.\d+)?)%"
)


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


def _parse_trading_comps(text: str) -> dict[str, Any]:
    blob = prepare_verdict_risk_text(text or "")
    subject = _SUBJECT_PEER_RE.search(blob)
    median = _MEDIAN_COMPS_RE.search(blob)
    ipo = _IPO_EV_RE.search(blob)
    ev_range = _COMP_EV_RANGE_RE.search(blob)

    peers: list[dict[str, Any]] = []
    if subject:
        peers.append(
            {
                "name": "Ola Electric (Subject)",
                "market_cap_usd_b": _safe_float(subject.group(1)),
                "ev_revenue_x": _safe_float(subject.group(2)),
                "revenue_growth_pct": _safe_float(subject.group(3)),
                "gross_margin_pct": _safe_float(subject.group(4)),
                "is_subject": True,
            }
        )

    implied_low = _safe_float(ev_range.group(3)) if ev_range else None
    implied_high = _safe_float(ev_range.group(4)) if ev_range else None

    return {
        "subject": peers[0] if peers else None,
        "peer_median_ev_ebitda_x": _safe_float(median.group(1)) if median else None,
        "peer_median_ev_revenue_x": _safe_float(median.group(2)) if median else None,
        "peer_median_revenue_growth_pct": _safe_float(median.group(3)) if median else None,
        "peer_median_gross_margin_pct": _safe_float(median.group(4)) if median else None,
        "ipo_implied_ev_usd_b": _safe_float(ipo.group(1)) if ipo else None,
        "implied_ev_low_usd_b": implied_low,
        "implied_ev_high_usd_b": implied_high,
        "ev_revenue_low_x": _safe_float(ev_range.group(1)) if ev_range else None,
        "ev_revenue_high_x": _safe_float(ev_range.group(2)) if ev_range else None,
    }


def _parse_precedent_transactions(text: str) -> dict[str, Any]:
    blob = prepare_verdict_risk_text(text or "")
    deals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _PRECEDENT_DEAL_RE.finditer(blob):
        name = re.sub(r"\s+", " ", match.group(1)).strip(" ,;:")
        # Normalize em-dash variants inside parenthetical geography.
        name = name.replace("—", "–").replace("–", "-")
        name = re.sub(r"\s+", " ", name).strip()
        key = name.lower()
        if not name or key in seen or len(name) < 4:
            continue
        if _PRECEDENT_TARGET_REJECT.search(name):
            continue
        if name.endswith("(") or "(" in name and ")" not in name:
            continue
        raw_value = _safe_float(match.group(2))
        unit = (match.group(3) or "M").upper()
        value_usd_m = None
        if raw_value is not None:
            value_usd_m = raw_value * 1000.0 if unit == "B" else raw_value
        seen.add(key)
        deals.append(
            {
                "target": name,
                "value_usd_m": value_usd_m,
                "ev_revenue_x": _safe_float(match.group(4)),
            }
        )

    median = _PRECEDENT_MEDIAN_RE.search(blob)
    applied = _PRECEDENT_APPLIED_RE.search(blob)
    ev_range = _PRECEDENT_EV_RANGE_RE.search(blob)

    return {
        "transactions": deals[:8],
        "median_ev_revenue_x": _safe_float(median.group(1)) if median else None,
        "applied_ev_revenue_low_x": _safe_float(applied.group(1)) if applied else None,
        "applied_ev_revenue_high_x": _safe_float(applied.group(2)) if applied else None,
        "implied_ev_low_usd_b": _safe_float(ev_range.group(1)) if ev_range else None,
        "implied_ev_high_usd_b": _safe_float(ev_range.group(2)) if ev_range else None,
    }


def _parse_dcf_fields(text: str) -> dict[str, Any]:
    blob = prepare_verdict_risk_text(text or "")
    wacc = _DCF_WACC_RE.search(blob)
    ev = _DCF_EV_RE.search(blob)
    equity = _DCF_EQUITY_RE.search(blob)
    share = _DCF_SHARE_RE.search(blob)

    scenarios: list[dict[str, Any]] = []
    for match in _SCENARIO_RE.finditer(blob):
        scenarios.append(
            {
                "label": match.group(1).strip(),
                "enterprise_value_inr_cr": _safe_float(match.group(2).replace(",", "")),
                "enterprise_value_usd_b": _safe_float(match.group(3)),
                "equity_value_per_share_inr": _safe_float(match.group(4)),
                "premium_discount_vs_ipo_pct": _safe_float(match.group(5)),
            }
        )

    return {
        "wacc_pct": _safe_float(wacc.group(1)) if wacc else None,
        "enterprise_value_inr_cr": _safe_float(ev.group(1).replace(",", "")) if ev else None,
        "enterprise_value_usd_b": _safe_float(ev.group(2)) if ev else None,
        "equity_value_inr_cr": _safe_float(equity.group(1).replace(",", "")) if equity else None,
        "equity_value_usd_b": _safe_float(equity.group(2)) if equity else None,
        "implied_share_price_inr": _safe_float(share.group(1)) if share else None,
        "scenarios": scenarios[:4],
    }


def _build_trading_comps_spec(
    fields: dict[str, Any],
    *,
    sources: list[str],
    coverage: str,
    market_definition: dict | None,
    historical_performance: dict | None,
) -> dict[str, Any]:
    subject = fields.get("subject") if isinstance(fields.get("subject"), dict) else {}
    flags: list[str] = []
    if subject.get("ev_revenue_x") is not None and fields.get("peer_median_ev_revenue_x") is not None:
        if subject["ev_revenue_x"] < fields["peer_median_ev_revenue_x"]:
            flags.append(
                f"Subject EV/Revenue {subject['ev_revenue_x']:.2f}x below peer median "
                f"{fields['peer_median_ev_revenue_x']:.2f}x"
            )
    if fields.get("ipo_implied_ev_usd_b") and fields.get("implied_ev_high_usd_b"):
        if fields["ipo_implied_ev_usd_b"] > fields["implied_ev_high_usd_b"]:
            flags.append(
                f"IPO-implied EV USD {fields['ipo_implied_ev_usd_b']:.2f}B above comp-implied high "
                f"USD {fields['implied_ev_high_usd_b']:.2f}B"
            )

    empty = not (subject or fields.get("peer_median_ev_revenue_x") or fields.get("ipo_implied_ev_usd_b"))
    return {
        "empty": empty,
        "extractor": "heuristic_v1",
        "fv_code": "FV-03",
        "stage": "B",
        "document": "Valuation Benchmark Analysis",
        "sources": sources,
        "coverage": coverage,
        "subject_peer": subject,
        "peer_medians": {
            "ev_ebitda_x": fields.get("peer_median_ev_ebitda_x"),
            "ev_revenue_x": fields.get("peer_median_ev_revenue_x"),
            "revenue_growth_pct": fields.get("peer_median_revenue_growth_pct"),
            "gross_margin_pct": fields.get("peer_median_gross_margin_pct"),
        },
        "ipo_implied_ev_usd_b": fields.get("ipo_implied_ev_usd_b"),
        "implied_ev_range_usd_b": {
            "low": fields.get("implied_ev_low_usd_b"),
            "high": fields.get("implied_ev_high_usd_b"),
        },
        "valuation_flags": flags[:6],
        "consumes_market_definition": bool(market_definition),
        "consumes_historical_performance": bool(historical_performance),
        "metrics": {
            "subject_ev_revenue_x": subject.get("ev_revenue_x"),
            "median_ev_revenue_x": fields.get("peer_median_ev_revenue_x"),
            "ipo_ev_usd_b": fields.get("ipo_implied_ev_usd_b"),
        },
    }


def _build_precedent_spec(
    fields: dict[str, Any],
    *,
    sources: list[str],
    coverage: str,
    foundation_f05: dict | None,
    compensation_alignment: dict | None,
) -> dict[str, Any]:
    flags: list[str] = []
    if fields.get("median_ev_revenue_x") is not None:
        flags.append(f"Precedent median EV/Revenue: {fields['median_ev_revenue_x']:.1f}x")
    if fields.get("implied_ev_low_usd_b") is not None and fields.get("implied_ev_high_usd_b") is not None:
        flags.append(
            f"Applied precedent EV range USD {fields['implied_ev_low_usd_b']:.2f}B–"
            f"{fields['implied_ev_high_usd_b']:.2f}B"
        )

    empty = not (
        fields.get("transactions")
        or fields.get("median_ev_revenue_x")
        or fields.get("applied_ev_revenue_low_x")
    )
    return {
        "empty": empty,
        "extractor": "heuristic_v1",
        "fv_code": "FV-04",
        "stage": "B",
        "document": "Precedent Transaction Analysis",
        "sources": sources,
        "coverage": coverage,
        "transactions": fields.get("transactions") or [],
        "median_ev_revenue_x": fields.get("median_ev_revenue_x"),
        "applied_ev_revenue_range_x": {
            "low": fields.get("applied_ev_revenue_low_x"),
            "high": fields.get("applied_ev_revenue_high_x"),
        },
        "implied_ev_range_usd_b": {
            "low": fields.get("implied_ev_low_usd_b"),
            "high": fields.get("implied_ev_high_usd_b"),
        },
        "valuation_flags": flags[:6],
        "consumes_f05": bool(foundation_f05),
        "consumes_compensation_alignment": bool(compensation_alignment),
        "metrics": {
            "precedent_count": len(fields.get("transactions") or []),
            "median_ev_revenue_x": fields.get("median_ev_revenue_x"),
        },
    }


def _build_valuation_modeling_spec(
    dcf: dict[str, Any],
    *,
    sources: list[str],
    coverage: str,
    trading_comps: dict | None,
    precedent_transactions: dict | None,
    historical_performance: dict | None,
    capital_structure: dict | None,
) -> dict[str, Any]:
    football: list[dict[str, Any]] = []

    for scenario in dcf.get("scenarios") or []:
        if isinstance(scenario, dict):
            football.append(
                {
                    "method": scenario.get("label"),
                    "equity_value_per_share_inr": scenario.get("equity_value_per_share_inr"),
                    "enterprise_value_usd_b": scenario.get("enterprise_value_usd_b"),
                    "premium_discount_vs_ipo_pct": scenario.get("premium_discount_vs_ipo_pct"),
                }
            )

    if isinstance(trading_comps, dict):
        comp_range = trading_comps.get("implied_ev_range_usd_b") or {}
        if comp_range.get("low") is not None or comp_range.get("high") is not None:
            football.append(
                {
                    "method": "Trading comps",
                    "enterprise_value_usd_b_low": comp_range.get("low"),
                    "enterprise_value_usd_b_high": comp_range.get("high"),
                }
            )
        if trading_comps.get("ipo_implied_ev_usd_b") is not None:
            football.append(
                {
                    "method": "IPO reference",
                    "enterprise_value_usd_b": trading_comps.get("ipo_implied_ev_usd_b"),
                }
            )

    if isinstance(precedent_transactions, dict):
        prec_range = precedent_transactions.get("implied_ev_range_usd_b") or {}
        if prec_range.get("low") is not None or prec_range.get("high") is not None:
            football.append(
                {
                    "method": "Precedent transactions",
                    "enterprise_value_usd_b_low": prec_range.get("low"),
                    "enterprise_value_usd_b_high": prec_range.get("high"),
                }
            )

    flags: list[str] = []
    if dcf.get("implied_share_price_inr") is not None:
        flags.append(f"DCF base implied share price INR {dcf['implied_share_price_inr']:.1f}")
    if dcf.get("wacc_pct") is not None:
        flags.append(f"Base WACC {dcf['wacc_pct']:.1f}%")

    empty = not (
        dcf.get("enterprise_value_usd_b")
        or dcf.get("implied_share_price_inr")
        or football
    )
    return {
        "empty": empty,
        "extractor": "heuristic_v1",
        "fv_code": "FV-05",
        "stage": "B",
        "document": "Valuation Range Overlap / Football Field",
        "sources": sources,
        "coverage": coverage,
        "dcf": dcf,
        "football_field": football[:8],
        "valuation_flags": flags[:6],
        "consumes_trading_comps": bool(trading_comps),
        "consumes_precedent_transactions": bool(precedent_transactions),
        "consumes_historical_performance": bool(historical_performance),
        "consumes_capital_structure": bool(capital_structure),
        "metrics": {
            "dcf_ev_usd_b": dcf.get("enterprise_value_usd_b"),
            "dcf_share_inr": dcf.get("implied_share_price_inr"),
            "scenarios": len(football),
        },
    }


def merge_verdict_valuation_spec(slug: str, base: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if not base:
        return dict(incoming)
    if incoming.get("empty"):
        return dict(base)
    if base.get("empty"):
        return dict(incoming)

    if slug == "trading_comps":
        merged = dict(base)
        if incoming.get("subject_peer") and not merged.get("subject_peer"):
            merged["subject_peer"] = incoming["subject_peer"]
        for key in ("peer_medians", "implied_ev_range_usd_b"):
            base_map = merged.get(key) if isinstance(merged.get(key), dict) else {}
            inc_map = incoming.get(key) if isinstance(incoming.get(key), dict) else {}
            combined = dict(base_map)
            for sub_key, value in inc_map.items():
                if value is not None:
                    combined[sub_key] = value
            merged[key] = combined
        for key in ("ipo_implied_ev_usd_b",):
            if incoming.get(key) is not None:
                merged[key] = incoming[key]
        merged["valuation_flags"] = _merge_str_lists(base.get("valuation_flags"), incoming.get("valuation_flags"))
        merged["sources"] = _merge_str_lists(base.get("sources"), incoming.get("sources"), limit=4)
        merged["empty"] = False
        return merged

    if slug == "precedent_transactions":
        merged = dict(base)
        tx_by_name = {
            str(row.get("target") or "").lower(): row
            for row in (merged.get("transactions") or [])
            if isinstance(row, dict) and row.get("target")
        }
        for row in incoming.get("transactions") or []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("target") or "").lower()
            if key:
                tx_by_name[key] = row
        merged["transactions"] = list(tx_by_name.values())[:8]
        for key in (
            "median_ev_revenue_x",
            "applied_ev_revenue_range_x",
            "implied_ev_range_usd_b",
        ):
            if incoming.get(key) is not None:
                merged[key] = incoming[key]
        merged["valuation_flags"] = _merge_str_lists(base.get("valuation_flags"), incoming.get("valuation_flags"))
        merged["sources"] = _merge_str_lists(base.get("sources"), incoming.get("sources"), limit=4)
        merged["empty"] = not merged.get("transactions") and not merged.get("median_ev_revenue_x")
        return merged

    if slug == "valuation_modeling":
        merged = dict(incoming if not incoming.get("empty") else base)
        ff_by_method: dict[str, dict] = {}
        for row in (base.get("football_field") or []) + (incoming.get("football_field") or []):
            if not isinstance(row, dict):
                continue
            key = str(row.get("method") or "").strip().lower()
            if key:
                ff_by_method[key] = row
        merged["football_field"] = list(ff_by_method.values())[:8]
        merged["valuation_flags"] = _merge_str_lists(base.get("valuation_flags"), incoming.get("valuation_flags"))
        merged["sources"] = _merge_str_lists(base.get("sources"), incoming.get("sources"), limit=4)
        if isinstance(incoming.get("dcf"), dict) and incoming["dcf"]:
            merged["dcf"] = incoming["dcf"]
        merged["empty"] = not (merged.get("dcf") or merged.get("football_field"))
        return merged

    return dict(incoming)


def extract_verdict_valuation_spec(
    slug: str,
    text: str,
    *,
    sources: list[str],
    coverage: str,
    market_definition: dict | None = None,
    historical_performance: dict | None = None,
    foundation_f05: dict | None = None,
    capital_structure: dict | None = None,
    compensation_alignment: dict | None = None,
    trading_comps: dict | None = None,
    precedent_transactions: dict | None = None,
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    if prior_spec and not prior_spec.get("empty"):
        partial = extract_verdict_valuation_spec(
            slug,
            text,
            sources=sources,
            coverage=coverage,
            market_definition=market_definition,
            historical_performance=historical_performance,
            foundation_f05=foundation_f05,
            capital_structure=capital_structure,
            compensation_alignment=compensation_alignment,
            trading_comps=trading_comps,
            precedent_transactions=precedent_transactions,
            prior_spec=None,
        )
        return merge_verdict_valuation_spec(slug, prior_spec, partial)

    normalized = prepare_verdict_risk_text(text)
    if slug == "trading_comps":
        return _build_trading_comps_spec(
            _parse_trading_comps(normalized),
            sources=sources,
            coverage=coverage,
            market_definition=market_definition,
            historical_performance=historical_performance,
        )
    if slug == "precedent_transactions":
        return _build_precedent_spec(
            _parse_precedent_transactions(normalized),
            sources=sources,
            coverage=coverage,
            foundation_f05=foundation_f05,
            compensation_alignment=compensation_alignment,
        )
    if slug == "valuation_modeling":
        return _build_valuation_modeling_spec(
            _parse_dcf_fields(normalized),
            sources=sources,
            coverage=coverage,
            trading_comps=trading_comps,
            precedent_transactions=precedent_transactions,
            historical_performance=historical_performance,
            capital_structure=capital_structure,
        )
    return {"empty": True, "document": slug}


def extract_verdict_valuation_from_documents(
    slug: str,
    documents: list[tuple[str, str]],
    *,
    coverage: str,
    market_definition: dict | None = None,
    historical_performance: dict | None = None,
    foundation_f05: dict | None = None,
    capital_structure: dict | None = None,
    compensation_alignment: dict | None = None,
    trading_comps: dict | None = None,
    precedent_transactions: dict | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] | None = None
    sources: list[str] = []
    for filename, text in documents:
        chunk = (text or "").strip()
        if not chunk:
            continue
        sources.append(filename)
        partial = extract_verdict_valuation_spec(
            slug,
            chunk,
            sources=[filename],
            coverage=coverage,
            market_definition=None,
            historical_performance=None,
            foundation_f05=None,
            capital_structure=None,
            compensation_alignment=None,
            trading_comps=None,
            precedent_transactions=None,
        )
        merged = merge_verdict_valuation_spec(slug, merged, partial)

    if merged is None:
        merged = extract_verdict_valuation_spec(
            slug,
            "",
            sources=[],
            coverage=coverage,
        )
    else:
        merged["sources"] = sources[:4]
        merged["coverage"] = coverage

    if slug == "trading_comps":
        merged = _build_trading_comps_spec(
            _parse_trading_comps(
                "\n".join(text for _, text in documents if (text or "").strip())
            ),
            sources=list(merged.get("sources") or []),
            coverage=coverage,
            market_definition=market_definition,
            historical_performance=historical_performance,
        )
    elif slug == "precedent_transactions":
        merged = _build_precedent_spec(
            _parse_precedent_transactions(
                "\n".join(text for _, text in documents if (text or "").strip())
            ),
            sources=list(merged.get("sources") or []),
            coverage=coverage,
            foundation_f05=foundation_f05,
            compensation_alignment=compensation_alignment,
        )
    elif slug == "valuation_modeling":
        merged = _build_valuation_modeling_spec(
            _parse_dcf_fields("\n".join(text for _, text in documents if (text or "").strip())),
            sources=list(merged.get("sources") or []),
            coverage=coverage,
            trading_comps=trading_comps,
            precedent_transactions=precedent_transactions,
            historical_performance=historical_performance,
            capital_structure=capital_structure,
        )
    return merged


def findings_from_verdict_valuation_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    if spec.get("empty"):
        return []
    out: list[str] = []
    if slug == "trading_comps":
        subject = spec.get("subject_peer") if isinstance(spec.get("subject_peer"), dict) else {}
        if subject.get("ev_revenue_x") is not None:
            out.append(f"Subject EV/Revenue: {subject['ev_revenue_x']:.2f}x")
        medians = spec.get("peer_medians") if isinstance(spec.get("peer_medians"), dict) else {}
        if medians.get("ev_revenue_x") is not None:
            out.append(f"Peer median EV/Revenue: {medians['ev_revenue_x']:.2f}x")
        if spec.get("ipo_implied_ev_usd_b") is not None:
            out.append(f"IPO-implied EV: USD {spec['ipo_implied_ev_usd_b']:.2f}B")
        ev_range = spec.get("implied_ev_range_usd_b") if isinstance(spec.get("implied_ev_range_usd_b"), dict) else {}
        if ev_range.get("low") is not None and ev_range.get("high") is not None:
            out.append(
                f"Comp-implied EV range: USD {ev_range['low']:.2f}B–{ev_range['high']:.2f}B"
            )
    elif slug == "precedent_transactions":
        if spec.get("median_ev_revenue_x") is not None:
            out.append(f"Precedent median EV/Revenue: {spec['median_ev_revenue_x']:.1f}x")
        ev_range = spec.get("implied_ev_range_usd_b") if isinstance(spec.get("implied_ev_range_usd_b"), dict) else {}
        if ev_range.get("low") is not None and ev_range.get("high") is not None:
            out.append(
                f"Precedent-implied EV range: USD {ev_range['low']:.2f}B–{ev_range['high']:.2f}B"
            )
        for tx in spec.get("transactions") or []:
            if not isinstance(tx, dict):
                continue
            name = tx.get("target")
            mult = tx.get("ev_revenue_x")
            if name and mult is not None:
                out.append(f"{name}: ~{mult:.1f}x revenue")
            if len(out) >= 6:
                break
    elif slug == "valuation_modeling":
        dcf = spec.get("dcf") if isinstance(spec.get("dcf"), dict) else {}
        if dcf.get("implied_share_price_inr") is not None:
            out.append(f"DCF base share price: INR {dcf['implied_share_price_inr']:.1f}")
        if dcf.get("enterprise_value_usd_b") is not None:
            out.append(f"DCF enterprise value: USD {dcf['enterprise_value_usd_b']:.2f}B")
        for row in spec.get("football_field") or []:
            if not isinstance(row, dict):
                continue
            method = row.get("method") or "Method"
            if row.get("equity_value_per_share_inr") is not None:
                out.append(f"{method}: INR {row['equity_value_per_share_inr']:.1f}/share")
            elif row.get("enterprise_value_usd_b") is not None:
                out.append(f"{method}: USD {row['enterprise_value_usd_b']:.2f}B EV")
            elif row.get("enterprise_value_usd_b_low") is not None:
                out.append(
                    f"{method}: USD {row['enterprise_value_usd_b_low']:.2f}B–"
                    f"{row.get('enterprise_value_usd_b_high'):.2f}B EV"
                )
            if len(out) >= 8:
                break

    for flag in spec.get("valuation_flags") or []:
        if isinstance(flag, str) and flag.strip():
            out.append(flag.strip())
        if len(out) >= 8:
            break

    seen: set[str] = set()
    deduped: list[str] = []
    for line in out:
        key = line.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(_clip(line, 220))
    return deduped[:8]
