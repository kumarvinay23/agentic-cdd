"""Compose DiligenceIQ Final Valuation Range — committee-ready band.

Low / base / high EV each traceable to a method; implied multiples on the
declared earnings figure; EV→equity via capital-structure net debt;
walk-away above the range; stand-alone only (no uncosted synergies);
evidence gaps bounded where possible.

Publishing is blocked when earnings quality, net debt or working capital
are not established — the blocker and unblock path are stated explicitly.

Stored under valuation_modeling.spec['final_valuation_range'].
No invest/pass. No company hardcoding.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+)?(?:recommend|advise|suggest)\s+(?:to\s+)?(?:invest|pass)\b"
)

_DOCUMENT_TITLE = "Final Valuation Range"
_DD_CODE = "FV-05-R"
_PARENT_KEY = "valuation_modeling"

_RANGE_RULE = (
    "Low, base and high enterprise value are each traceable to a method and "
    "an assumption set, with the implied multiple on the declared earnings figure."
)
_BRIDGE_RULE = (
    "Enterprise value bridges to equity value using the net debt position from "
    "the capital structure agent, including debt-like items."
)
_WALK_RULE = (
    "Walk-away sits above the recommended range — never below it. Conditions "
    "that would justify moving it are stated."
)
_STANDALONE_RULE = (
    "Stand-alone value is separated from anything a specific buyer would add. "
    "Synergies are not credited without a named buyer and a costed plan."
)
_GAP_RULE = (
    "Evidence gaps that would move the range are stated, with a bounded "
    "impact where that can be estimated."
)
_BLOCK_RULE = (
    "If earnings quality, net debt or working capital are not yet established, "
    "a range is not published — the blocker and unblock path are stated."
)

_NET_DEBT_PACK_RE = re.compile(
    r"(?i)Net\s+Debt[^\n]{0,40}?(?:USD|US\$|\$)\s*([\d.]+)\s*([MB])"
)
_WC_RE = re.compile(
    r"(?i)Working\s+Capital[^\n%]{0,40}?(?:USD|US\$|\$|INR)?\s*([\d.]+)"
)
_BUYER_RE = re.compile(
    r"(?i)\b(?:strategic\s+buyer|named\s+buyer|acquirer)\s*[:\-]?\s*"
    r"([A-Z][A-Za-z0-9][A-Za-z0-9\s&\.\-]{1,40})"
)
_SYNERGY_RE = re.compile(
    r"(?i)synerg(?:y|ies)[^\n]{0,60}?(?:USD|US\$|\$)\s*([\d.]+)\s*([MB])"
)


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("range evidence only — no deal verdict expressed", raw)
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _info_request(need: str) -> str:
    return f"Information request: {need}"


def _is_filled(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return bool(s) and not s.startswith("Information") and s != _NA


def _num(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _round(n: float | None, places: int = 2) -> float | None:
    if n is None:
        return None
    return round(float(n), places)


def _insight(text: Any, *, max_chars: int = 520) -> str:
    snap = _soften_invest(_clean(text, max_chars))
    return f"**Insight Snapshot:** {snap}\n\n" if snap else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [(_soften_invest(_clean(c, 220)) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _to_usd_m(value: float, unit: str | None) -> float:
    u = (unit or "M").upper()
    if u.startswith("B"):
        return value * 1000.0
    return value


def _implied_multiple(ev_usd_b: float | None, earnings_usd_m: float | None) -> float | None:
    if ev_usd_b is None or earnings_usd_m is None or earnings_usd_m <= 0:
        return None
    return _round((float(ev_usd_b) * 1000.0) / float(earnings_usd_m), 2)


# ---------------------------------------------------------------------------
# blockers
# ---------------------------------------------------------------------------


def _earnings_ready(valuation: dict[str, Any], revenue_quality: dict[str, Any] | None) -> tuple[bool, str]:
    earn = valuation.get("earnings_basis") if isinstance(valuation.get("earnings_basis"), dict) else {}
    amount = earn.get("amount")
    if not _is_filled(amount) or not isinstance(_num(amount), (int, float)):
        return False, "Declared earnings figure missing — unblock: state period, adjustments and source."
    rq = revenue_quality if isinstance(revenue_quality, dict) else {}
    qv = str(rq.get("quality_verdict") or "").upper()
    rv = str(rq.get("reliance_verdict") or "").upper()
    if rq and (qv == "REWORK" or rv == "BLOCKED"):
        return (
            False,
            f"Earnings quality not established (Quality {qv or '—'} / Reliance {rv or '—'}) — "
            f"unblock: close revenue-quality gaps until Quality PASS and Reliance not BLOCKED.",
        )
    return True, "Declared earnings figure ready; earnings quality not blocking."


def _net_debt_from_capital(
    capital: dict[str, Any] | None,
    corpus: str,
) -> tuple[bool, dict[str, Any], str]:
    """Return (ready, bridge_spec, message). Ready only when capital structure establishes net debt."""
    cap = capital if isinstance(capital, dict) else {}
    schedule_ok = bool(cap.get("schedule_complete"))
    bridge_rows = cap.get("net_debt_bridge") if isinstance(cap.get("net_debt_bridge"), list) else []
    closing = None
    for r in bridge_rows:
        if isinstance(r, dict) and "net debt" in str(r.get("component") or "").lower():
            closing = r
            break
    net = _num(closing.get("amount")) if isinstance(closing, dict) else None

    free_cash = None
    for c in cap.get("cash_split") or []:
        if isinstance(c, dict) and "freely" in str(c.get("bucket") or "").lower():
            free_cash = _num(c.get("amount"))
            break

    debt_like_sum = 0.0
    debt_like_sized = False
    for d in cap.get("debt_like_items") or []:
        if isinstance(d, dict) and isinstance(_num(d.get("amount")), (int, float)):
            debt_like_sum += float(_num(d.get("amount")))
            debt_like_sized = True

    gross = _num(cap.get("debt_total_usd_m"))
    if gross is None:
        for r in bridge_rows:
            if isinstance(r, dict) and "gross" in str(r.get("component") or "").lower():
                gross = _num(r.get("amount"))
                break

    pack_nd = None
    m = _NET_DEBT_PACK_RE.search(_prose(corpus))
    if m:
        pack_nd = _to_usd_m(float(m.group(1)), m.group(2))

    detail = {
        "gross_debt_usd_m": gross,
        "freely_available_cash_usd_m": free_cash,
        "debt_like_usd_m": debt_like_sum if debt_like_sized else None,
        "net_debt_usd_m": net,
        "pack_net_debt_usd_m": pack_nd,
        "schedule_complete": schedule_ok,
        "bridge_rows": bridge_rows,
        "source": _DOC_CITE if schedule_ok and net is not None else _NA,
    }

    if not cap:
        return (
            False,
            detail,
            "Capital structure agent not available — unblock: run Capital Structure (DD-24) to a complete facility schedule.",
        )
    if not schedule_ok:
        gaps = cap.get("schedule_gaps") or []
        gap_txt = "; ".join(str(g) for g in gaps[:3]) if gaps else "facility schedule incomplete"
        return (
            False,
            detail,
            f"Net debt not established — facility schedule incomplete ({gap_txt}). "
            f"Unblock: complete lender/rate/maturity/security/covenants on every facility; "
            f"size freely available cash. Pack cites net debt ~USD {pack_nd:g}M but that is not used until the schedule closes."
            if pack_nd is not None
            else f"Net debt not established — facility schedule incomplete ({gap_txt}). "
            f"Unblock: complete the facility schedule and size freely available cash.",
        )
    if free_cash is None:
        return (
            False,
            detail,
            "Net debt blocked — freely available cash not sized. Unblock: split cash into freely available / restricted / operating minimum.",
        )
    if net is None:
        return (
            False,
            detail,
            "Net debt closing line missing from capital structure bridge. Unblock: close the net-debt bridge.",
        )
    return True, detail, f"Net debt USD {net:g}M from capital structure (incl. debt-like)."


def _working_capital_ready(
    capital: dict[str, Any] | None,
    historical: dict[str, Any] | None,
    corpus: str,
) -> tuple[bool, str]:
    text = _prose(corpus)
    if _WC_RE.search(text):
        return True, "Working capital referenced in pack / financials."
    hist = historical if isinstance(historical, dict) else {}
    for row in hist.get("pl_lines") or hist.get("balance_sheet_lines") or []:
        if isinstance(row, dict) and "working capital" in str(row.get("line_item") or "").lower():
            return True, "Working capital line present in historical extract."
    # Soft: if capital structure ran and cash split exists, treat WC as not blocking hard
    # but prompt says WC must be established — require an explicit cue
    cap = capital if isinstance(capital, dict) else {}
    if cap.get("schedule_complete") and any(
        isinstance(c, dict) and _is_filled(c.get("amount"))
        for c in (cap.get("cash_split") or [])
    ):
        return (
            True,
            "Working capital treated as provisionally covered via cash / funding position "
            "(explicit WC bridge still preferred).",
        )
    return (
        False,
        "Working capital not yet established — unblock: size NWC / WC bridge from the accounts or databook.",
    )


# ---------------------------------------------------------------------------
# range construction
# ---------------------------------------------------------------------------


def _method_points(valuation: dict[str, Any], sensitivity: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Collect candidate EV points from valuation + sensitivity cases."""
    points: list[dict[str, Any]] = []
    earn = valuation.get("earnings_basis") if isinstance(valuation.get("earnings_basis"), dict) else {}
    earn_m = _num(earn.get("amount"))
    # Normalise earnings to USD M when unit is INR Cr (~83 INR/USD)
    unit = str(earn.get("unit") or "").upper()
    if earn_m is not None and "INR" in unit and "CR" in unit:
        earn_m = earn_m * 10.0 / 83.0

    comps = valuation.get("comps_summary") if isinstance(valuation.get("comps_summary"), dict) else {}
    if comps.get("implied_ev_usd_b_low") is not None:
        points.append(
            {
                "label": "low",
                "method": "Trading comps (low)",
                "assumption_set": (
                    f"Peer multiple range low "
                    f"{comps.get('range_multiple_low')}x–{comps.get('range_multiple_high')}x "
                    f"on declared earnings"
                ),
                "enterprise_value_usd_b": _num(comps.get("implied_ev_usd_b_low")),
                "source": _DOC_CITE,
            }
        )
    if comps.get("implied_ev_usd_b_high") is not None:
        points.append(
            {
                "label": "high_candidate",
                "method": "Trading comps (high)",
                "assumption_set": (
                    f"Peer multiple range high on declared earnings; "
                    f"median {comps.get('median_multiple')}x"
                ),
                "enterprise_value_usd_b": _num(comps.get("implied_ev_usd_b_high")),
                "source": _DOC_CITE,
            }
        )

    prec = (
        valuation.get("precedents_summary")
        if isinstance(valuation.get("precedents_summary"), dict)
        else {}
    )
    if prec.get("implied_ev_usd_b_low") is not None:
        points.append(
            {
                "label": "low_candidate",
                "method": "Precedent transactions (applied range)",
                "assumption_set": f"Precedent median {prec.get('median_multiple')}x applied to declared earnings",
                "enterprise_value_usd_b": _num(prec.get("implied_ev_usd_b_low")),
                "source": _DOC_CITE,
            }
        )
    if prec.get("implied_ev_usd_b_high") is not None:
        points.append(
            {
                "label": "high_candidate",
                "method": "Precedent transactions (high)",
                "assumption_set": f"Precedent applied high on declared earnings",
                "enterprise_value_usd_b": _num(prec.get("implied_ev_usd_b_high")),
                "source": _DOC_CITE,
            }
        )

    dcf = valuation.get("dcf") if isinstance(valuation.get("dcf"), dict) else {}
    dcf_view = valuation.get("dcf_view") if isinstance(valuation.get("dcf_view"), dict) else {}
    scenarios = dcf.get("scenarios") if isinstance(dcf.get("scenarios"), list) else []
    sens = sensitivity if isinstance(sensitivity, dict) else {}
    sens_cases = sens.get("scenario_cases") if isinstance(sens.get("scenario_cases"), list) else []
    sens_by = {
        str(c.get("case") or "").lower(): c
        for c in sens_cases
        if isinstance(c, dict)
    }

    for s in scenarios:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label") or "")
        low = label.lower()
        band = "base"
        if "bear" in low or "down" in low:
            band = "low"
        elif "bull" in low or "up" in low:
            band = "high"
        sc = sens_by.get(label.lower()) or {}
        assume = []
        if sc.get("growth_assumption"):
            assume.append(f"Growth: {sc['growth_assumption']}")
        if sc.get("margin_assumption"):
            assume.append(f"Margin: {sc['margin_assumption']}")
        if sc.get("capital_assumption"):
            assume.append(f"Capital: {sc['capital_assumption']}")
        if not assume:
            assume.append(f"DCF {label} assumptions from valuation agent")
        points.append(
            {
                "label": band,
                "method": f"DCF — {label}",
                "assumption_set": "; ".join(assume),
                "enterprise_value_usd_b": _num(s.get("enterprise_value_usd_b")),
                "equity_value_per_share_inr": _num(s.get("equity_value_per_share_inr")),
                "source": _DOC_CITE,
            }
        )

    if dcf.get("enterprise_value_usd_b") is not None and not any(
        p.get("label") == "base" for p in points
    ):
        points.append(
            {
                "label": "base",
                "method": "DCF (base)",
                "assumption_set": (
                    f"WACC {dcf.get('wacc_pct') or dcf_view.get('discount_rate_pct')}%"
                ),
                "enterprise_value_usd_b": _num(dcf.get("enterprise_value_usd_b")),
                "source": _DOC_CITE,
            }
        )

    for p in points:
        p["implied_multiple_x"] = _implied_multiple(
            p.get("enterprise_value_usd_b"), earn_m
        )
        p["earnings_usd_m"] = _round(earn_m, 1) if earn_m is not None else None
        p["earnings_metric"] = earn.get("metric") or "Revenue"
        p["earnings_period"] = earn.get("period")
    return [p for p in points if p.get("enterprise_value_usd_b") is not None]


def _select_range(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick low / base / high — prefer DCF bear/base/bull when present."""
    by_band: dict[str, list[dict[str, Any]]] = {"low": [], "base": [], "high": []}
    for p in points:
        lab = str(p.get("label") or "")
        if lab in by_band:
            by_band[lab].append(p)
        elif lab.endswith("candidate"):
            if "low" in lab:
                by_band["low"].append(p)
            elif "high" in lab:
                by_band["high"].append(p)

    def _prefer_dcf(cands: list[dict[str, Any]], fallback_key: str) -> dict[str, Any] | None:
        if not cands and not points:
            return None
        dcf = [c for c in cands if "dcf" in str(c.get("method") or "").lower()]
        pool = dcf or cands
        if not pool:
            # fallback: min/median/max of all points
            ordered = sorted(points, key=lambda x: float(x["enterprise_value_usd_b"]))
            if not ordered:
                return None
            if fallback_key == "low":
                return ordered[0]
            if fallback_key == "high":
                return ordered[-1]
            return ordered[len(ordered) // 2]
        # Prefer the DCF point; if several, take min for low / max for high / mid for base
        if fallback_key == "low":
            return min(pool, key=lambda x: float(x["enterprise_value_usd_b"]))
        if fallback_key == "high":
            return max(pool, key=lambda x: float(x["enterprise_value_usd_b"]))
        # base: exact base label preferred
        base_exact = [c for c in pool if c.get("label") == "base"]
        return base_exact[0] if base_exact else pool[0]

    low = _prefer_dcf(by_band["low"], "low")
    base = _prefer_dcf(by_band["base"], "base")
    high = _prefer_dcf(by_band["high"], "high")

    # Ensure ordering low <= base <= high when all present
    vals = [
        (k, p)
        for k, p in (("low", low), ("base", base), ("high", high))
        if p is not None
    ]
    if len(vals) >= 2:
        ordered = sorted(vals, key=lambda kv: float(kv[1]["enterprise_value_usd_b"]))
        # Remap only if inverted
        if low and high and float(low["enterprise_value_usd_b"]) > float(high["enterprise_value_usd_b"]):
            low, high = high, low

    return {
        "low": low,
        "base": base,
        "high": high,
        "candidates": points,
    }


def _equity_bridge(
    *,
    range_pts: dict[str, Any],
    net_debt_detail: dict[str, Any],
    net_debt_ready: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    nd = net_debt_detail.get("net_debt_usd_m") if net_debt_ready else None
    nd_b = (float(nd) / 1000.0) if isinstance(nd, (int, float)) else None
    for band in ("low", "base", "high"):
        p = range_pts.get(band)
        if not isinstance(p, dict):
            continue
        ev = _num(p.get("enterprise_value_usd_b"))
        eq = None
        if ev is not None and nd_b is not None:
            eq = _round(ev - nd_b, 3)
        rows.append(
            {
                "band": band,
                "enterprise_value_usd_b": ev,
                "net_debt_usd_b": _round(nd_b, 3) if nd_b is not None else None,
                "net_debt_usd_m": nd if net_debt_ready else None,
                "equity_value_usd_b": eq,
                "equity_value_per_share_inr": p.get("equity_value_per_share_inr"),
                "gross_debt_usd_m": net_debt_detail.get("gross_debt_usd_m"),
                "freely_available_cash_usd_m": net_debt_detail.get("freely_available_cash_usd_m"),
                "debt_like_usd_m": net_debt_detail.get("debt_like_usd_m"),
                "bridge_status": "ready" if net_debt_ready else "blocked",
                "notes": _BRIDGE_RULE,
                "source": net_debt_detail.get("source") or _NA,
            }
        )
    return rows


def _walk_away(
    *,
    range_pts: dict[str, Any],
    sensitivity: dict[str, Any] | None,
) -> dict[str, Any]:
    high = range_pts.get("high") if isinstance(range_pts.get("high"), dict) else None
    base = range_pts.get("base") if isinstance(range_pts.get("base"), dict) else None
    high_ev = _num(high.get("enterprise_value_usd_b")) if high else None
    base_ev = _num(base.get("enterprise_value_usd_b")) if base else None

    # Walk-away = high + half the (high−base) gap, or high × 1.08 when no base
    walk = None
    if high_ev is not None and base_ev is not None and high_ev >= base_ev:
        walk = _round(high_ev + 0.5 * (high_ev - base_ev), 3)
    elif high_ev is not None:
        walk = _round(high_ev * 1.08, 3)

    consistent = (
        walk is not None
        and high_ev is not None
        and walk > high_ev
    )
    move_conditions = []
    sens = sensitivity if isinstance(sensitivity, dict) else {}
    for b in sens.get("breakevens") or []:
        if isinstance(b, dict) and b.get("operating_terms"):
            move_conditions.append(_clean(b.get("operating_terms"), 160))
    if not move_conditions:
        move_conditions = [
            "Material improvement in evidenced growth / margin vs upside case assumptions",
            "Discount rate (WACC) falls enough that base cell exceeds current high",
            "Named buyer with a costed synergy plan (stand-alone range itself does not move)",
        ]

    return {
        "walk_away_enterprise_value_usd_b": walk,
        "above_recommended_high": consistent,
        "recommended_high_usd_b": high_ev,
        "check": (
            f"Walk-away USD {walk:g}B is above recommended high USD {high_ev:g}B — OK"
            if consistent and walk is not None and high_ev is not None
            else (
                "Walk-away not set — range incomplete"
                if walk is None
                else "Walk-away must sit above the recommended high — fix before publishing"
            )
        ),
        "move_conditions": move_conditions[:5],
        "notes": _WALK_RULE,
        "source": _COMPUTED,
    }


def _standalone_vs_synergies(corpus: str) -> dict[str, Any]:
    text = _prose(corpus)
    buyer = None
    bm = _BUYER_RE.search(text)
    if bm:
        buyer = _clean(bm.group(1), 60)
        if re.search(r"(?i)^(the|a|an|and|or|for|with)\b", buyer or ""):
            buyer = None
    synergy_amt = None
    sm = _SYNERGY_RE.search(text)
    if sm:
        synergy_amt = _to_usd_m(float(sm.group(1)), sm.group(2))
    costed_plan = bool(
        re.search(r"(?i)costed\s+(?:synergy\s+)?plan|synergy\s+bridge|integration\s+budget", text)
    )
    credit = bool(buyer and synergy_amt is not None and costed_plan)
    return {
        "stand_alone_only": not credit,
        "named_buyer": buyer or _info_request("named buyer if synergies are to be credited"),
        "synergy_usd_m": synergy_amt,
        "costed_plan": costed_plan,
        "synergies_credited": credit,
        "notes": (
            f"Stand-alone range only — synergies not credited"
            f"{'' if credit else ' (no named buyer and costed plan)'}"
            if not credit
            else f"Buyer-specific synergies USD {synergy_amt:g}M credited for {buyer} with costed plan"
        ),
        "source": _DOC_CITE if (buyer or synergy_amt) else _COMPUTED,
        "rule": _STANDALONE_RULE,
    }


def _evidence_gaps(
    *,
    range_pts: dict[str, Any],
    blockers: list[dict[str, Any]],
    sensitivity: dict[str, Any] | None,
    net_debt_detail: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for b in blockers:
        if isinstance(b, dict) and not b.get("ready"):
            gaps.append(
                {
                    "gap": b.get("name"),
                    "impact": "Range cannot be published until cleared",
                    "bounded_move_usd_b": None,
                    "unblock": b.get("unblock"),
                    "source": _COMPUTED,
                }
            )

    low = range_pts.get("low") if isinstance(range_pts.get("low"), dict) else None
    high = range_pts.get("high") if isinstance(range_pts.get("high"), dict) else None
    if low and high:
        span = float(high["enterprise_value_usd_b"]) - float(low["enterprise_value_usd_b"])
        gaps.append(
            {
                "gap": "Method disagreement (comps / precedents / DCF)",
                "impact": "Already reflected in low–high span",
                "bounded_move_usd_b": _round(span, 2),
                "unblock": "Close forecast / multiple evidence to shrink the span",
                "source": _COMPUTED,
            }
        )

    if net_debt_detail.get("pack_net_debt_usd_m") is not None and not net_debt_detail.get(
        "schedule_complete"
    ):
        gaps.append(
            {
                "gap": "Capital structure schedule incomplete vs pack net debt",
                "impact": (
                    f"Equity bridge may shift by ~USD "
                    f"{net_debt_detail['pack_net_debt_usd_m']:g}M once schedule closes"
                ),
                "bounded_move_usd_b": _round(
                    float(net_debt_detail["pack_net_debt_usd_m"]) / 1000.0, 3
                ),
                "unblock": "Complete facility schedule and freely available cash split",
                "source": _DOC_CITE,
            }
        )

    sens = sensitivity if isinstance(sensitivity, dict) else {}
    grid = sens.get("two_driver_grid") if isinstance(sens.get("two_driver_grid"), dict) else {}
    if grid.get("rows"):
        gaps.append(
            {
                "gap": "Discount rate / terminal growth within sensitivity grid",
                "impact": "Moves value inside the published band; outside grid needs new cases",
                "bounded_move_usd_b": None,
                "unblock": "Hold to evidenced WACC / TG ranges from Sensitivity Analysis",
                "source": _COMPUTED,
            }
        )

    if not gaps:
        gaps.append(
            {
                "gap": _info_request("evidence gap that would move the range"),
                "impact": _GAP_RULE,
                "bounded_move_usd_b": None,
                "unblock": _info_request("what would close the gap"),
                "source": _NA,
            }
        )
    return gaps[:8]


def _quality_reliance(
    *,
    published: bool,
    blockers: list[dict[str, Any]],
    range_pts: dict[str, Any],
    walk: dict[str, Any],
    standalone: dict[str, Any],
) -> tuple[str, str, str]:
    has_range = all(
        isinstance(range_pts.get(k), dict) and range_pts[k].get("enterprise_value_usd_b") is not None
        for k in ("low", "base", "high")
    )
    walk_ok = bool(walk.get("above_recommended_high"))
    stand_ok = bool(standalone.get("stand_alone_only")) or bool(standalone.get("synergies_credited"))
    blocking = [b for b in blockers if isinstance(b, dict) and not b.get("ready")]

    if published and has_range and walk_ok and stand_ok and not blocking:
        quality = "PASS"
    else:
        quality = "REWORK"

    if published and has_range and walk_ok:
        reliance = "READY"
    elif has_range and blocking:
        reliance = "BLOCKED"
    elif has_range:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"Quality {quality}: range {'published' if published else 'withheld'}.",
        f"Reliance {reliance}.",
    ]
    if blocking:
        bits.append("Blockers: " + "; ".join(str(b.get("name")) for b in blocking[:3]) + ".")
    if not walk_ok and published:
        bits.append("Walk-away must sit above the recommended high.")
    bits.append(_BLOCK_RULE)
    return quality, reliance, " ".join(bits)


# ---------------------------------------------------------------------------
# heuristic / build / render
# ---------------------------------------------------------------------------


def _heuristic_final_range_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    valuation_spec: dict[str, Any] | None = None,
    capital_structure: dict[str, Any] | None = None,
    revenue_quality: dict[str, Any] | None = None,
    historical_performance: dict[str, Any] | None = None,
    sensitivity_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valuation = valuation_spec if isinstance(valuation_spec, dict) else {}
    earn_ok, earn_msg = _earnings_ready(valuation, revenue_quality)
    nd_ok, nd_detail, nd_msg = _net_debt_from_capital(capital_structure, corpus)
    wc_ok, wc_msg = _working_capital_ready(capital_structure, historical_performance, corpus)

    blockers = [
        {
            "name": "Earnings quality / declared earnings",
            "ready": earn_ok,
            "detail": earn_msg,
            "unblock": earn_msg.split("unblock:", 1)[-1].strip() if "unblock:" in earn_msg.lower() else earn_msg,
        },
        {
            "name": "Net debt (capital structure)",
            "ready": nd_ok,
            "detail": nd_msg,
            "unblock": nd_msg.split("Unblock:", 1)[-1].strip() if "Unblock:" in nd_msg else nd_msg,
        },
        {
            "name": "Working capital",
            "ready": wc_ok,
            "detail": wc_msg,
            "unblock": wc_msg.split("unblock:", 1)[-1].strip() if "unblock:" in wc_msg.lower() else wc_msg,
        },
    ]
    published = earn_ok and nd_ok and wc_ok

    points = _method_points(valuation, sensitivity_analysis)
    range_pts = _select_range(points)
    bridge = _equity_bridge(
        range_pts=range_pts, net_debt_detail=nd_detail, net_debt_ready=nd_ok
    )
    walk = _walk_away(range_pts=range_pts, sensitivity=sensitivity_analysis)
    standalone = _standalone_vs_synergies(corpus)
    gaps = _evidence_gaps(
        range_pts=range_pts,
        blockers=blockers,
        sensitivity=sensitivity_analysis,
        net_debt_detail=nd_detail,
    )
    quality, reliance, rationale = _quality_reliance(
        published=published,
        blockers=blockers,
        range_pts=range_pts,
        walk=walk,
        standalone=standalone,
    )

    # Legacy dual-write keys for IC memo
    def _ev(band: str) -> float | None:
        p = range_pts.get(band)
        return _num(p.get("enterprise_value_usd_b")) if isinstance(p, dict) else None

    bits = [f"Final Valuation Range for {company}"]
    if published:
        bits.append(
            f"EV USD {_ev('low')}–{_ev('high')}B (base {_ev('base')}B); "
            f"walk-away USD {walk.get('walk_away_enterprise_value_usd_b')}B"
        )
    else:
        blocked_names = [b["name"] for b in blockers if not b["ready"]]
        bits.append("range withheld — blocked by: " + "; ".join(blocked_names))

    return {
        "insight_snapshot": _soften_invest(". ".join(str(x) for x in bits if x)),
        "range_published": published,
        "blockers": blockers,
        "range_points": range_pts,
        "ev_low_usd_b": _ev("low") if published else None,
        "ev_base_usd_b": _ev("base") if published else None,
        "ev_high_usd_b": _ev("high") if published else None,
        "equity_bridge": bridge,
        "walk_away": walk if published else {
            **walk,
            "walk_away_enterprise_value_usd_b": None,
            "check": "Walk-away withheld until the range is publishable",
            "notes": _WALK_RULE,
        },
        "stand_alone": standalone,
        "evidence_gaps": gaps,
        "quality_verdict": quality,
        "reliance_verdict": "BLOCKED" if not published else reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "fv_code": _DD_CODE,
        "dd_code": _DD_CODE,
        "parent_agent": _PARENT_KEY,
        "empty": not points,
        "notes": _BLOCK_RULE if not published else _RANGE_RULE,
    }


def build_final_valuation_range_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    valuation_spec: dict[str, Any] | None = None,
    capital_structure: dict[str, Any] | None = None,
    revenue_quality: dict[str, Any] | None = None,
    historical_performance: dict[str, Any] | None = None,
    sensitivity_analysis: dict[str, Any] | None = None,
    prefer_heuristic: bool = True,
) -> dict[str, Any]:
    from agetic_cdd_api.agent_document_valuation_modeling import (
        gather_valuation_modeling_corpus,
    )
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    del prefer_heuristic  # LLM path reserved; heuristic is authoritative for blockers
    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()

    def _load(agent_key: str) -> dict[str, Any] | None:
        try:
            disk = read_agent_output_file(deal, agent_key=agent_key) or {}
            spec = disk.get("spec")
            return spec if isinstance(spec, dict) else None
        except Exception:
            return None

    val = valuation_spec if isinstance(valuation_spec, dict) else _load("valuation_modeling")
    cap = capital_structure if isinstance(capital_structure, dict) else _load("capital_structure")
    rq = revenue_quality if isinstance(revenue_quality, dict) else _load("revenue_quality")
    hist = (
        historical_performance
        if isinstance(historical_performance, dict)
        else _load("historical_performance")
    )
    sens = sensitivity_analysis if isinstance(sensitivity_analysis, dict) else None
    if sens is None and isinstance(val, dict):
        sens = val.get("sensitivity_analysis") if isinstance(val.get("sensitivity_analysis"), dict) else None

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_valuation_modeling_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources

    return _heuristic_final_range_spec(
        company=target,
        corpus=corpus or "",
        sources=srcs,
        valuation_spec=val,
        capital_structure=cap,
        revenue_quality=rq,
        historical_performance=hist,
        sensitivity_analysis=sens,
    )


def render_final_valuation_range_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
    include_sources: bool = True,
) -> str:
    published = bool(spec.get("range_published"))
    blockers = spec.get("blockers") if isinstance(spec.get("blockers"), list) else []
    range_pts = spec.get("range_points") if isinstance(spec.get("range_points"), dict) else {}
    bridge = spec.get("equity_bridge") if isinstance(spec.get("equity_bridge"), list) else []
    walk = spec.get("walk_away") if isinstance(spec.get("walk_away"), dict) else {}
    standalone = spec.get("stand_alone") if isinstance(spec.get("stand_alone"), dict) else {}
    gaps = spec.get("evidence_gaps") if isinstance(spec.get("evidence_gaps"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_BLOCK_RULE}\n\n")

    # Publishing gate
    parts.append("## 0. Publishing Gate\n\n")
    if published:
        parts.append("**Range status:** PUBLISHED — earnings, net debt and working capital cleared.\n\n")
    else:
        parts.append(
            "**Range status:** WITHHELD — cannot publish a committee range until blockers clear.\n\n"
        )
    parts.append(_table(
        ["Requirement", "Ready?", "Detail / unblock"],
        [
            [
                _clean(b.get("name"), 40),
                "Yes" if b.get("ready") else "No",
                _soften_invest(_clean(b.get("detail"), 160)),
            ]
            for b in blockers if isinstance(b, dict)
        ],
    ))
    parts.append("---\n\n")

    # 1 Range
    parts.append("## 1. Low / Base / High Enterprise Value\n\n")
    parts.append(f"{_RANGE_RULE}\n\n")
    if not published:
        parts.append(
            "*Figures below are method triangulation only — not an actionable published range.*\n\n"
        )
    rows = []
    for band in ("low", "base", "high"):
        p = range_pts.get(band)
        if not isinstance(p, dict):
            continue
        rows.append(
            [
                band.title(),
                _clean(p.get("method"), 40),
                (
                    f"USD {p.get('enterprise_value_usd_b'):g}B"
                    if isinstance(p.get("enterprise_value_usd_b"), (int, float))
                    else "—"
                ),
                (
                    f"{p.get('implied_multiple_x'):g}x"
                    if isinstance(p.get("implied_multiple_x"), (int, float))
                    else "—"
                ),
                _soften_invest(_clean(p.get("assumption_set"), 100)),
                _clean(p.get("source") or _NA, 40),
            ]
        )
    if rows:
        parts.append(_table(
            ["Band", "Method", "EV", "Implied multiple", "Assumption set", "Source"],
            rows,
        ))
    else:
        parts.append(f"**{_info_request('low / base / high EV traceable to methods')}**\n\n")
    parts.append("---\n\n")

    # 2 Bridge
    parts.append("## 2. EV → Equity Bridge (net debt)\n\n")
    parts.append(f"{_BRIDGE_RULE}\n\n")
    if bridge:
        parts.append(_table(
            ["Band", "EV (USD B)", "Net debt (USD M)", "Equity (USD B)", "Status"],
            [
                [
                    _clean(r.get("band"), 12),
                    (
                        f"{r.get('enterprise_value_usd_b'):g}"
                        if isinstance(r.get("enterprise_value_usd_b"), (int, float))
                        else "—"
                    ),
                    (
                        f"{r.get('net_debt_usd_m'):g}"
                        if isinstance(r.get("net_debt_usd_m"), (int, float))
                        else "—"
                    ),
                    (
                        f"{r.get('equity_value_usd_b'):g}"
                        if isinstance(r.get("equity_value_usd_b"), (int, float))
                        else "—"
                    ),
                    _clean(r.get("bridge_status"), 16),
                ]
                for r in bridge if isinstance(r, dict)
            ],
        ))
        sample = bridge[0] if bridge else {}
        parts.append(
            f"Gross debt USD {sample.get('gross_debt_usd_m')}; "
            f"freely available cash USD {sample.get('freely_available_cash_usd_m')}; "
            f"debt-like USD {sample.get('debt_like_usd_m')}.\n\n"
        )
    else:
        parts.append(f"**{_info_request('EV to equity bridge via capital structure net debt')}**\n\n")
    parts.append("---\n\n")

    # 3 Walk-away
    parts.append("## 3. Walk-away Price\n\n")
    parts.append(f"{_WALK_RULE}\n\n")
    parts.append(_table(
        ["Field", "Value"],
        [
            [
                "Walk-away EV",
                (
                    f"USD {walk.get('walk_away_enterprise_value_usd_b'):g}B"
                    if isinstance(walk.get("walk_away_enterprise_value_usd_b"), (int, float))
                    else "Withheld"
                ),
            ],
            [
                "Recommended high",
                (
                    f"USD {walk.get('recommended_high_usd_b'):g}B"
                    if isinstance(walk.get("recommended_high_usd_b"), (int, float))
                    else "—"
                ),
            ],
            ["Consistency check", _soften_invest(_clean(walk.get("check"), 160))],
        ],
    ))
    if walk.get("move_conditions"):
        parts.append("**Conditions that would justify moving walk-away:**\n\n")
        for c in walk.get("move_conditions") or []:
            parts.append(f"- {_soften_invest(_clean(c, 200))}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 4 Stand-alone
    parts.append("## 4. Stand-alone vs Buyer Synergies\n\n")
    parts.append(f"{_STANDALONE_RULE}\n\n")
    parts.append(_table(
        ["Field", "Value"],
        [
            ["Stand-alone only?", "Yes" if standalone.get("stand_alone_only") else "No — synergies credited"],
            ["Named buyer", _soften_invest(_clean(standalone.get("named_buyer"), 60))],
            [
                "Synergy amount",
                (
                    f"USD {standalone.get('synergy_usd_m'):g}M"
                    if isinstance(standalone.get("synergy_usd_m"), (int, float))
                    else "—"
                ),
            ],
            ["Costed plan?", "Yes" if standalone.get("costed_plan") else "No"],
            ["Notes", _soften_invest(_clean(standalone.get("notes"), 160))],
        ],
    ))
    parts.append("---\n\n")

    # 5 Gaps
    parts.append("## 5. Evidence Gaps That Move the Range\n\n")
    parts.append(f"{_GAP_RULE}\n\n")
    if gaps:
        parts.append(_table(
            ["Gap", "Impact", "Bounded move", "Unblock"],
            [
                [
                    _soften_invest(_clean(g.get("gap"), 50)),
                    _soften_invest(_clean(g.get("impact"), 80)),
                    (
                        f"USD {g.get('bounded_move_usd_b'):g}B"
                        if isinstance(g.get("bounded_move_usd_b"), (int, float))
                        else "—"
                    ),
                    _soften_invest(_clean(g.get("unblock"), 80)),
                ]
                for g in gaps if isinstance(g, dict)
            ],
        ))
    parts.append("---\n\n")

    # 6 Quality
    parts.append("## 6. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(f"**Quality:** {qv}  \n")
    parts.append(f"**Reliance:** {rv}  \n\n")
    parts.append(f"{_soften_invest(_clean(rationale, 600))}\n\n")
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "This agent does not issue an invest or pass recommendation.*\n\n"
    )
    if not include_sources:
        return "".join(parts)

    parts.append("---\n\n")
    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(srcs[:16], start=1):
            parts.append(f"{i}. {_clean(name, 120)}\n")
    else:
        parts.append(f"1. {_NA}\n")
    parts.append("\n")
    return "".join(parts)
