"""Build live-style Decision Chain payloads from workflow agent outputs.

Mirrors DiligenceIQ Sources → Decision chain (Σ Chain / Sources / Gaps):
plain-English narrative, inputs+source, calculations with formula/trace/result,
verbatim reads, and information gaps — grounded in agent ``spec`` / ``metrics``.
"""

from __future__ import annotations

import re
from typing import Any

_NOISE_SOURCE_RE = re.compile(r"(?i)(wildfly|\.log$|/tmp/|untitled)")
_SKIP_SPEC_KEYS = {
    "sources",
    "empty",
    "extractor",
    "coverage",
    "document",
    "slug",
    "track",
    "dd_code",
    "fv_code",
    "stage",
    "extract_source",
    "vdr_backed",
    "llm_refined",
    "metrics",
    "consumes_trading_comps",
    "consumes_precedent_transactions",
    "consumes_historical_performance",
    "consumes_capital_structure",
    "consumes_ic_synthesis",
    "consumes_execution_risk",
    "consumes_compensation_alignment",
    "consumes_valuation_modeling",
    "consumes_market_definition",
    "consumes_f05",
    "consumes_ceiling",
}


def _clean_sources(files: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for f in files:
        if not isinstance(f, str) or not f.strip():
            continue
        if _NOISE_SOURCE_RE.search(f):
            continue
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if abs(value) >= 100 or value == int(value):
            return str(int(value)) if value == int(value) else f"{value:.2f}".rstrip("0").rstrip(".")
        return f"{value:.4g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_fmt(v) for v in value[:8])
    if isinstance(value, dict):
        if "value" in value and ("unit" in value or "scale" in value or "label" in value):
            label = value.get("label") or ""
            unit = value.get("unit") or ""
            scale = value.get("scale") or ""
            raw = value.get("raw")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
            bits = [str(value.get("value"))]
            if unit:
                bits.append(str(unit))
            if scale:
                bits.append(str(scale))
            prefix = f"{label} " if label else ""
            return prefix + " ".join(bits)
        parts = []
        for k, v in list(value.items())[:6]:
            parts.append(f"{k}={_fmt(v)}")
        return "; ".join(parts)
    text = str(value).strip()
    return text if len(text) <= 160 else text[:157] + "…"


def _primary_source(files: list[str], idx: int = 0) -> str:
    return files[idx] if files else "—"


def _market_size_block(spec: dict[str, Any], files: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    inputs: list[dict[str, Any]] = []
    calcs: list[dict[str, Any]] = []
    reads: list[dict[str, Any]] = []
    for key, label in (("tam", "TAM"), ("sam", "SAM"), ("som", "SOM")):
        block = spec.get(key)
        if isinstance(block, dict) and block.get("value") is not None:
            inputs.append({
                "label": label,
                "key": key,
                "value": _fmt(block),
                "source": _primary_source(files),
            })
            reads.append({
                "label": f"{label} (verbatim)",
                "value": _fmt(block.get("raw") or block),
                "source": _primary_source(files),
            })
    tam = spec.get("tam") if isinstance(spec.get("tam"), dict) else {}
    sam = spec.get("sam") if isinstance(spec.get("sam"), dict) else {}
    som = spec.get("som") if isinstance(spec.get("som"), dict) else {}
    tam_v, sam_v, som_v = tam.get("value"), sam.get("value"), som.get("value")

    if isinstance(tam_v, (int, float)) and not isinstance(tam_v, bool) and tam_v != 0:
        if isinstance(sam_v, (int, float)) and not isinstance(sam_v, bool):
            ratio = float(sam_v) / float(tam_v)
            calcs.append({
                "label": "SAM / TAM share",
                "key": "sam_tam_share",
                "formula": "SAM ÷ TAM",
                "trace": f"{sam_v} ÷ {tam_v}",
                "result": f"{ratio:.1%}",
            })

    if isinstance(sam_v, (int, float)) and not isinstance(sam_v, bool) and sam_v != 0:
        if isinstance(som_v, (int, float)) and not isinstance(som_v, bool):
            ratio = float(som_v) / float(sam_v)
            calcs.append({
                "label": "SOM / SAM capture",
                "key": "som_sam_share",
                "formula": "SOM ÷ SAM",
                "trace": f"{som_v} ÷ {sam_v}",
                "result": f"{ratio:.1%}",
            })

    cagr = spec.get("cagr_pct")
    if isinstance(cagr, list) and cagr:
        calcs.append({
            "label": "CAGR observations",
            "key": "cagr_pct",
            "formula": "read from market volume notes / financials",
            "trace": f"n={len(cagr)} · values={_fmt(cagr)}",
            "result": _fmt(cagr),
        })
    elif isinstance(cagr, (int, float)) and not isinstance(cagr, bool):
        calcs.append({
            "label": "CAGR %",
            "key": "cagr_pct",
            "formula": "read from market volume notes / financials",
            "trace": str(cagr),
            "result": f"{cagr}%",
        })
    return inputs, calcs, reads


def _build_chain_from_spec(
    *,
    agent_key: str,
    agent_name: str,
    spec: dict[str, Any],
    files: list[str],
    findings: list[str],
) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    calcs: list[dict[str, Any]] = []
    reads: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    clean_files = _clean_sources(files)

    # --- typed extractors ---
    if any(k in spec for k in ("tam", "sam", "som")):
        i, c, r = _market_size_block(spec, clean_files)
        inputs.extend(i)
        calcs.extend(c)
        reads.extend(r)

    risk_items = spec.get("market_risk_items")
    if isinstance(risk_items, list):
        for it in risk_items[:8]:
            if not isinstance(it, dict):
                continue
            inputs.append({
                "label": str(it.get("risk") or "Risk item"),
                "key": "market_risk_item",
                "value": f"P={it.get('probability', '—')} · I={it.get('impact', '—')}",
                "source": _primary_source(clean_files),
            })

    regs = spec.get("regulatory_items")
    if isinstance(regs, list):
        for it in regs[:6]:
            if isinstance(it, dict):
                reads.append({
                    "label": str(it.get("area") or "Regulatory item"),
                    "value": f"{it.get('status', '—')} · {it.get('risk_level', '—')}",
                    "source": _primary_source(clean_files),
                })

    for lit in spec.get("litigation_exposures") or []:
        if isinstance(lit, str) and lit.strip():
            reads.append({"label": "Litigation exposure", "value": lit.strip()[:160], "source": _primary_source(clean_files)})

    segments = spec.get("segments")
    if isinstance(segments, list):
        for seg in segments[:6]:
            if isinstance(seg, dict):
                inputs.append({
                    "label": str(seg.get("name") or "Segment"),
                    "key": "segment_share_pct",
                    "value": f"share {seg.get('share_pct', '—')}%" + (f" · age {seg.get('avg_age')}" if seg.get("avg_age") else ""),
                    "source": _primary_source(clean_files),
                })

    buying = spec.get("buying_metrics")
    if isinstance(buying, dict):
        for k, v in buying.items():
            if v is None:
                continue
            calcs.append({
                "label": k.replace("_", " ").title(),
                "key": k,
                "formula": "extracted buying metric from commercial diligence",
                "trace": _fmt(v),
                "result": _fmt(v),
            })
    if spec.get("segment_hhi") is not None:
        calcs.append({
            "label": "Segment HHI",
            "key": "segment_hhi",
            "formula": "Σ share_i² × 10,000 (concentration index)",
            "trace": f"HHI={spec.get('segment_hhi')}",
            "result": _fmt(spec.get("segment_hhi")),
        })

    leverage = spec.get("leverage_ratios")
    if isinstance(leverage, dict):
        for k, v in leverage.items():
            calcs.append({
                "label": k.replace("_", " ").title(),
                "key": k,
                "formula": "capital structure ratio from financial diligence",
                "trace": _fmt(v),
                "result": _fmt(v),
            })
    dcf_m = spec.get("dcf_metrics") if isinstance(spec.get("dcf_metrics"), dict) else {}
    dcf = spec.get("dcf") if isinstance(spec.get("dcf"), dict) else dcf_m
    if isinstance(dcf, dict) and dcf:
        for k, label in (
            ("wacc_pct", "WACC %"),
            ("implied_share_price_inr", "Implied share price (INR)"),
            ("enterprise_value_usd_b", "Enterprise value (USD B)"),
            ("enterprise_value_inr_cr", "Enterprise value (INR Cr)"),
            ("equity_value_usd_b", "Equity value (USD B)"),
            ("equity_value_inr_cr", "Equity value (INR Cr)"),
        ):
            if dcf.get(k) is not None:
                calcs.append({
                    "label": label,
                    "key": k,
                    "formula": "DCF / capital model output",
                    "trace": _fmt(dcf.get(k)),
                    "result": _fmt(dcf.get(k)),
                })

    ff = spec.get("football_field")
    if isinstance(ff, list) and ff:
        shares = [r.get("equity_value_per_share_inr") for r in ff if isinstance(r, dict) and r.get("equity_value_per_share_inr") is not None]
        evs = [r.get("enterprise_value_usd_b") for r in ff if isinstance(r, dict) and r.get("enterprise_value_usd_b") is not None]
        if shares:
            calcs.append({
                "label": "Equity/share band (football field)",
                "key": "equity_share_band_inr",
                "formula": "min/max across football-field methods",
                "trace": f"min={min(shares)} · max={max(shares)} · n={len(shares)}",
                "result": f"INR {min(shares)} – {max(shares)}",
            })
        if evs:
            calcs.append({
                "label": "EV band (football field)",
                "key": "ev_band_usd_b",
                "formula": "min/max enterprise value across methods",
                "trace": f"min={min(evs)} · max={max(evs)} · n={len(evs)}",
                "result": f"${min(evs)}B – ${max(evs)}B",
            })

    returns = spec.get("returns_by_scenario")
    if isinstance(returns, list):
        for sc in returns[:5]:
            if isinstance(sc, dict):
                calcs.append({
                    "label": f"Returns — {sc.get('scenario') or 'scenario'}",
                    "key": "returns_by_scenario",
                    "formula": "IRR / MOIC from recommendation model",
                    "trace": f"IRR={sc.get('irr_pct')}% · MOIC={sc.get('moic_x')}x",
                    "result": f"{sc.get('irr_pct')}% / {sc.get('moic_x')}x",
                })

    monitors = spec.get("monitoring_metrics")
    if isinstance(monitors, list):
        for m in monitors[:6]:
            if isinstance(m, dict):
                inputs.append({
                    "label": str(m.get("metric") or "Monitor"),
                    "key": "monitoring_metric",
                    "value": f"current {m.get('current', '—')} · concern {m.get('concern_trigger', '—')}",
                    "source": _primary_source(clean_files),
                })

    dims = spec.get("dimensions")
    if isinstance(dims, list):
        for d in dims[:8]:
            if isinstance(d, dict):
                calcs.append({
                    "label": str(d.get("dimension") or "Dimension"),
                    "key": "scorecard_dimension",
                    "formula": "IC synthesis score 1–5",
                    "trace": _fmt(d.get("commentary") or ""),
                    "result": f"{d.get('score_1_5', '—')}/5",
                })

    # Generic metrics / leftover numeric fields
    metrics = spec.get("metrics") if isinstance(spec.get("metrics"), dict) else {}
    for k, v in metrics.items():
        if any(c.get("key") == k for c in calcs):
            continue
        if (isinstance(v, (int, float)) and not isinstance(v, bool)) or (isinstance(v, str) and v.strip()):
            calcs.append({
                "label": k.replace("_", " ").title(),
                "key": k,
                "formula": "agent metrics tally",
                "trace": _fmt(v),
                "result": _fmt(v),
            })

    handled_keys = {
        "tam", "sam", "som", "market_risk_items", "regulatory_items", "litigation_exposures",
        "segments", "buying_metrics", "leverage_ratios", "dcf", "dcf_metrics", "football_field",
        "returns_by_scenario", "monitoring_metrics", "dimensions", "cagr_pct", "segment_hhi",
    }

    for key, value in spec.items():
        if key in _SKIP_SPEC_KEYS or key in handled_keys:
            continue
        if isinstance(value, list) and value and all(isinstance(x, str) for x in value[:3]):
            for item in value[:5]:
                reads.append({
                    "label": key.replace("_", " ").title(),
                    "value": item.strip()[:160],
                    "source": _primary_source(clean_files),
                })
        elif (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and not any(c.get("key") == key for c in calcs)
        ):
            calcs.append({
                "label": key.replace("_", " ").title(),
                "key": key,
                "formula": "structured field from agent spec",
                "trace": _fmt(value),
                "result": _fmt(value),
            })

    # Gaps
    if not clean_files:
        gaps.append({"label": "Source documents", "detail": "No VDR citations on this agent output."})
    if not inputs and not calcs and not reads:
        gaps.append({"label": "Structured chain", "detail": "Agent has no numeric/list fields to expand into a calculation chain."})
    if not findings and not reads:
        gaps.append({"label": "Findings", "detail": "No findings text available for narrative grounding."})
    expected_numeric = ("tam", "sam", "wacc_pct", "go_no_go", "aligned_go_no_go")
    for exp in expected_numeric:
        if exp in ("tam", "sam") and agent_key in {"market_volume_and_growth", "demand_drivers"}:
            block = spec.get(exp)
            if not (isinstance(block, dict) and block.get("value") is not None):
                gaps.append({"label": exp.upper(), "detail": f"Expected {exp} not populated in agent spec."})

    # Plain English
    name = agent_name or agent_key.replace("_", " ").title()
    src_phrase = ", ".join(clean_files[:3]) if clean_files else "available workflow outputs"
    bits = [
        f"Starting from {name} workflow output grounded in {src_phrase}.",
    ]
    if findings:
        bits.append(f"Key finding: {findings[0].strip()[:180]}")
    if calcs:
        bits.append(
            f"Re-computed / tallied {len(calcs)} figure(s) from structured spec fields"
            + (f" (e.g. {calcs[0]['label']} → {calcs[0]['result']})." if calcs else ".")
        )
    if reads:
        bits.append(f"{len(reads)} item(s) read straight from source without re-derivation.")
    if gaps:
        bits.append(f"{len(gaps)} information gap(s) flagged.")
    bits.append("Every listed figure is traceable to this deal's agent output — not re-estimated in the report UI.")

    source_entries = [
        {"file": f, "role": "cited", "used_by": name}
        for f in clean_files
    ]

    return {
        "plain_english": " ".join(bits),
        "inputs": inputs[:20],
        "calculations": calcs[:24],
        "reads": reads[:20],
        "gaps": gaps[:12],
        "source_entries": source_entries[:24],
        "counts": {
            "chain": len(calcs) + len(inputs),
            "sources": len(clean_files),
            "gaps": len(gaps),
            "reads": len(reads),
        },
    }


def build_agent_decision_chain(
    *,
    agent_key: str,
    resolved_key: str,
    agent: dict[str, Any],
    source_files: list[str] | None = None,
) -> dict[str, Any]:
    """Return provenance + live-style chain block for one storyline agent."""
    spec = agent.get("spec") if isinstance(agent.get("spec"), dict) else {}
    files = _clean_sources(list(source_files or []) or list(agent.get("sources") or []) or list(spec.get("sources") or []))
    findings_raw = agent.get("findings") or []
    findings: list[str] = []
    for item in findings_raw:
        if isinstance(item, str) and item.strip():
            findings.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("finding") or item.get("note") or item.get("name")
            if text:
                findings.append(str(text).strip())
        if len(findings) >= 6:
            break

    available = bool(agent)
    chain = _build_chain_from_spec(
        agent_key=agent_key,
        agent_name=str(agent.get("agentName") or agent_key.replace("_", " ").title()),
        spec=spec if available else {},
        files=files,
        findings=findings,
    )
    if not available:
        chain = {
            "plain_english": f"No local output for {agent_key} (missing or not yet run).",
            "inputs": [],
            "calculations": [],
            "reads": [],
            "gaps": [{"label": "Agent output", "detail": f"{agent_key} not found in deal outputs."}],
            "source_entries": [],
            "counts": {"chain": 0, "sources": 0, "gaps": 1, "reads": 0},
        }

    return {
        "agent": agent_key,
        "resolved": resolved_key,
        "available": available,
        "status": agent.get("status") or ("missing" if not available else "completed"),
        "coverage": spec.get("coverage") or agent.get("source_coverage") or "-",
        "extract_source": agent.get("extract_source") or spec.get("extract_source") or "-",
        "sources": files[:8],
        "chain": chain,
    }
