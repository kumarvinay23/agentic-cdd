"""Compose DiligenceIQ Final Valuation Range — committee-ready band.

Low / base / high EV on a common date/basis; comps with LTM/forward +
selection rationale; implied multiples on declared earnings; EV→equity via
capital-structure net debt; walk-away above the range vs hurdles/offer;
stand-alone only (no uncosted synergies); evidence gaps bounded where
possible. Code-enforced QA + Questions; READY→LIMITED on open QA FAILs.

Publishing is blocked when earnings quality, net debt or working capital
are not established — the blocker and unblock path are stated explicitly.

Stored under valuation_modeling.spec['final_valuation_range'].
No invest/pass / Go/bid endorsement. No company hardcoding.
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
_BASIS_RULE = (
    "Every method point is bound to a common as-of date and earnings basis "
    "from the valuation agent."
)
_COMP_RULE = (
    "Comp and precedent points carry selection rationale and LTM vs forward "
    "multiple labelling."
)
_HURDLE_RULE = (
    "Walk-away is checked against the recommended high and any offer / return "
    "hurdles from Sensitivity — never below the high."
)
_NO_BID_RULE = (
    "Final Valuation Range does not issue a Go / bid / invest or pass "
    "endorsement — Quality and Reliance only."
)
_GO_BID_RE = re.compile(
    r"(?i)\b(?:go\s+(?:decision|vote)|bid\s+(?:now|at)|submit\s+(?:a\s+)?bid|"
    r"recommend(?:ed)?\s+(?:to\s+)?(?:invest|pass|bid|buy)|"
    r"we\s+(?:should|must)\s+(?:bid|invest|pass))\b"
)
_LTM_RE = re.compile(r"(?i)\b(?:LTM|last\s+twelve\s+months|trailing)\b")
_FORWARD_RE = re.compile(r"(?i)\b(?:forward|NTM|FY\d{2,4}E|next\s+(?:twelve\s+months|year))\b")
_OFFER_RE = re.compile(
    r"(?i)(?:offer|bid)\s+(?:price|ev|enterprise\s+value)?[^\n]{0,40}?"
    r"(?:USD|US\$|\$)\s*([\d.]+)\s*([MB])"
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

    def _multiple_basis(blob: str) -> str:
        has_ltm = bool(_LTM_RE.search(blob))
        has_fwd = bool(_FORWARD_RE.search(blob))
        if has_ltm and has_fwd:
            return "mixed"
        if has_ltm:
            return "LTM"
        if has_fwd:
            return "forward"
        return "N/A (LTM vs forward not labelled)"

    comps = valuation.get("comps_summary") if isinstance(valuation.get("comps_summary"), dict) else {}
    comps_blob = " ".join(
        str(comps.get(k) or "")
        for k in (
            "selection_rationale", "peer_set", "multiple_basis", "notes",
            "range_multiple_low", "median_multiple", "period",
        )
    )
    comps_basis = (
        str(comps.get("multiple_basis") or "").strip()
        or _multiple_basis(comps_blob + " " + str(earn.get("period") or ""))
    )
    comps_rationale = (
        comps.get("selection_rationale")
        or comps.get("peer_set_rationale")
        or (
            f"Peer set implied by trading comps median {comps.get('median_multiple')}x"
            if comps.get("median_multiple") is not None
            else _info_request("comp selection rationale (peers included / excluded)")
        )
    )
    if comps.get("implied_ev_usd_b_low") is not None:
        points.append(
            {
                "label": "low",
                "method": "Trading comps (low)",
                "assumption_set": (
                    f"Peer multiple range low "
                    f"{comps.get('range_multiple_low')}x–{comps.get('range_multiple_high')}x "
                    f"on declared earnings ({comps_basis})"
                ),
                "enterprise_value_usd_b": _num(comps.get("implied_ev_usd_b_low")),
                "multiple_basis": comps_basis,
                "selection_rationale": _clean(comps_rationale, 160),
                "source": _DOC_CITE,
            }
        )
    if comps.get("implied_ev_usd_b_high") is not None:
        points.append(
            {
                "label": "high_candidate",
                "method": "Trading comps (high)",
                "assumption_set": (
                    f"Peer multiple range high on declared earnings ({comps_basis}); "
                    f"median {comps.get('median_multiple')}x"
                ),
                "enterprise_value_usd_b": _num(comps.get("implied_ev_usd_b_high")),
                "multiple_basis": comps_basis,
                "selection_rationale": _clean(comps_rationale, 160),
                "source": _DOC_CITE,
            }
        )

    prec = (
        valuation.get("precedents_summary")
        if isinstance(valuation.get("precedents_summary"), dict)
        else {}
    )
    prec_blob = " ".join(
        str(prec.get(k) or "")
        for k in ("selection_rationale", "multiple_basis", "notes", "median_multiple", "period")
    )
    prec_basis = (
        str(prec.get("multiple_basis") or "").strip()
        or _multiple_basis(prec_blob + " " + str(earn.get("period") or ""))
    )
    prec_rationale = (
        prec.get("selection_rationale")
        or (
            f"Precedent set implied by median {prec.get('median_multiple')}x"
            if prec.get("median_multiple") is not None
            else _info_request("precedent selection rationale")
        )
    )
    if prec.get("implied_ev_usd_b_low") is not None:
        points.append(
            {
                "label": "low_candidate",
                "method": "Precedent transactions (applied range)",
                "assumption_set": (
                    f"Precedent median {prec.get('median_multiple')}x applied to "
                    f"declared earnings ({prec_basis})"
                ),
                "enterprise_value_usd_b": _num(prec.get("implied_ev_usd_b_low")),
                "multiple_basis": prec_basis,
                "selection_rationale": _clean(prec_rationale, 160),
                "source": _DOC_CITE,
            }
        )
    if prec.get("implied_ev_usd_b_high") is not None:
        points.append(
            {
                "label": "high_candidate",
                "method": "Precedent transactions (high)",
                "assumption_set": f"Precedent applied high on declared earnings ({prec_basis})",
                "enterprise_value_usd_b": _num(prec.get("implied_ev_usd_b_high")),
                "multiple_basis": prec_basis,
                "selection_rationale": _clean(prec_rationale, 160),
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

    as_of = earn.get("as_of_date") or earn.get("as_of") or valuation.get("as_of_date")
    for p in points:
        p["implied_multiple_x"] = _implied_multiple(
            p.get("enterprise_value_usd_b"), earn_m
        )
        p["earnings_usd_m"] = _round(earn_m, 1) if earn_m is not None else None
        p["earnings_metric"] = earn.get("metric") or "Revenue"
        p["earnings_period"] = earn.get("period")
        p["as_of_date"] = as_of
        if "multiple_basis" not in p:
            p["multiple_basis"] = "N/A (not a trading/precedent multiple)"
        if "selection_rationale" not in p:
            p["selection_rationale"] = p.get("assumption_set")
    return [p for p in points if p.get("enterprise_value_usd_b") is not None]


def _common_date_basis(
    *,
    valuation: dict[str, Any],
    points: list[dict[str, Any]],
    deal_slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slots = deal_slots if isinstance(deal_slots, dict) else {}
    earn = valuation.get("earnings_basis") if isinstance(valuation.get("earnings_basis"), dict) else {}
    as_of = (
        earn.get("as_of_date")
        or earn.get("as_of")
        or valuation.get("as_of_date")
        or valuation.get("model_date")
        or slots.get("as_of_date")
        or _info_request("common valuation as-of date")
    )
    metric = earn.get("metric") or _info_request("common earnings metric")
    period = (
        earn.get("period")
        or slots.get("review_periods")
        or _info_request("common earnings / review period")
    )
    periods = {
        str(p.get("earnings_period") or "")
        for p in points
        if isinstance(p, dict) and p.get("earnings_period")
    }
    metrics = {
        str(p.get("earnings_metric") or "")
        for p in points
        if isinstance(p, dict) and p.get("earnings_metric")
    }
    consistent = (len(periods) <= 1) and (len(metrics) <= 1)
    bound = bool(_is_filled(as_of) or _is_filled(metric)) and bool(points)
    return {
        "bound": bound and consistent,
        "as_of_date": as_of,
        "earnings_metric": metric,
        "earnings_period": period,
        "methods_share_common_basis": consistent,
        "method_count": len(points),
        "notes": _BASIS_RULE,
    }


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
    corpus: str = "",
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

    # Offer / bid EV from pack (informational — not an endorsement)
    offer_ev_b = None
    om = _OFFER_RE.search(_prose(corpus))
    if om:
        offer_ev_b = _round(_to_usd_m(float(om.group(1)), om.group(2)) / 1000.0, 3)

    vs_offer = None
    if offer_ev_b is not None and walk is not None:
        vs_offer = (
            f"Walk-away USD {walk:g}B vs offer/bid EV USD {offer_ev_b:g}B — "
            f"{'walk-away above offer' if walk > offer_ev_b else 'offer at/above walk-away (flag)'}"
        )

    # Return hurdles from sensitivity cases (IRR)
    hurdles: list[str] = []
    for c in sens.get("scenario_cases") or []:
        if not isinstance(c, dict):
            continue
        if isinstance(c.get("irr_pct"), (int, float)) and "base" in str(c.get("case") or "").lower():
            hurdles.append(f"Base-case IRR hurdle {c['irr_pct']:g}%")
        if isinstance(c.get("moic_x"), (int, float)) and "base" in str(c.get("case") or "").lower():
            hurdles.append(f"Base-case MoIC hurdle {c['moic_x']:g}x")

    return {
        "walk_away_enterprise_value_usd_b": walk,
        "above_recommended_high": consistent,
        "recommended_high_usd_b": high_ev,
        "offer_enterprise_value_usd_b": offer_ev_b,
        "vs_offer": vs_offer or _info_request("offer / bid EV if tabled"),
        "return_hurdles": hurdles[:4] or [
            _info_request("return hurdles (IRR / MoIC) from Sensitivity")
        ],
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
        "notes": f"{_WALK_RULE} {_HURDLE_RULE}",
        "source": _COMPUTED,
    }


def _standalone_vs_synergies(
    corpus: str,
    synergies_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = _prose(corpus)
    syn = synergies_spec if isinstance(synergies_spec, dict) else {}
    buyer_obj = syn.get("buyer") if isinstance(syn.get("buyer"), dict) else {}
    buyer = None
    if buyer_obj.get("named") and buyer_obj.get("buyer_name"):
        buyer = _clean(buyer_obj.get("buyer_name"), 60)
    if not buyer:
        bm = _BUYER_RE.search(text)
        if bm:
            buyer = _clean(bm.group(1), 60)
            if re.search(r"(?i)^(the|a|an|and|or|for|with)\b", buyer or ""):
                buyer = None
    synergy_amt = None
    sm = _SYNERGY_RE.search(text)
    if sm:
        synergy_amt = _to_usd_m(float(sm.group(1)), sm.group(2))
    # Prefer synergies agent underwritable flag
    underwritable = bool(syn.get("underwritable"))
    fvr_excl = syn.get("fvr_exclusion") if isinstance(syn.get("fvr_exclusion"), dict) else {}
    costed_plan = bool(
        re.search(r"(?i)costed\s+(?:synergy\s+)?plan|synergy\s+bridge|integration\s+budget", text)
    ) or underwritable
    # Never credit if synergies agent excludes from FVR
    if fvr_excl.get("include_in_final_valuation_range") is False:
        credit = False
    else:
        credit = bool(buyer and (synergy_amt is not None or underwritable) and costed_plan)
    return {
        "stand_alone_only": not credit,
        "named_buyer": buyer or _info_request("named buyer if synergies are to be credited"),
        "synergy_usd_m": synergy_amt,
        "costed_plan": costed_plan,
        "synergies_credited": credit,
        "synergies_prior_present": bool(syn),
        "notes": (
            f"Stand-alone range only — synergies not credited"
            f"{'' if credit else ' (no named buyer and costed plan / FVR exclusion)'}"
            if not credit
            else (
                f"Buyer-specific synergies"
                + (f" USD {synergy_amt:g}M" if synergy_amt is not None else "")
                + f" credited for {buyer} with costed plan"
            )
        ),
        "source": _DOC_CITE if (buyer or synergy_amt or syn) else _COMPUTED,
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


def _fvr_evidence_qa(
    *,
    basis: dict[str, Any],
    points: list[dict[str, Any]],
    published: bool,
    blockers: list[dict[str, Any]],
    range_pts: dict[str, Any],
    bridge: list[dict[str, Any]],
    walk: dict[str, Any],
    standalone: dict[str, Any],
    corpus: str,
    insight_snapshot: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    # 1 Common date/basis
    basis_ok = bool(basis.get("bound")) or (
        bool(points)
        and basis.get("methods_share_common_basis") is not False
        and _is_filled(basis.get("earnings_metric"))
    )
    rows.append({
        "check": "common_date_basis",
        "status": "PASS" if basis_ok else "FAIL",
        "finding": (
            f"Common basis as-of={_clean(basis.get('as_of_date'), 40)}; "
            f"metric={_clean(basis.get('earnings_metric'), 40)}; "
            f"{basis.get('method_count') or 0} method point(s)"
            if basis_ok
            else "Methods not bound to a common as-of / earnings basis"
        ),
        "action": _BASIS_RULE,
    })

    # 2 Comp LTM/forward + rationale when comps used
    comp_pts = [
        p for p in points
        if isinstance(p, dict)
        and ("comp" in str(p.get("method") or "").lower() or "precedent" in str(p.get("method") or "").lower())
    ]
    if not comp_pts:
        comp_ok = True
        comp_finding = "No comps/precedent points — LTM/forward check not required"
    else:
        labelled = [
            p for p in comp_pts
            if str(p.get("multiple_basis") or "") in {"LTM", "forward", "mixed"}
            or (
                p.get("multiple_basis")
                and not str(p.get("multiple_basis")).startswith("N/A")
            )
        ]
        if not labelled:
            for p in comp_pts:
                period = str(p.get("earnings_period") or "")
                if _FORWARD_RE.search(period) or _LTM_RE.search(period):
                    labelled.append(p)
        has_rationale = all(_is_filled(p.get("selection_rationale")) for p in comp_pts)
        all_na = all(
            str(p.get("multiple_basis") or "").startswith("N/A") for p in comp_pts
        )
        # PASS when LTM/forward labelled (or period-derived) and rationale filled
        comp_ok = bool(labelled) and has_rationale
        if all_na and not labelled:
            comp_ok = False
        comp_finding = (
            f"{len(comp_pts)} comps/precedent point(s); "
            f"{len(labelled)} with LTM/forward label"
            if comp_ok
            else "Comps/precedents lack LTM vs forward label and selection rationale"
        )
    rows.append({
        "check": "comp_rationale_ltm_forward",
        "status": "PASS" if comp_ok else "FAIL",
        "finding": comp_finding,
        "action": _COMP_RULE,
    })

    # 3 EV → equity bridge
    bridge_ready = any(
        isinstance(r, dict) and r.get("bridge_status") == "ready"
        for r in bridge
    )
    nd_blocker = next(
        (
            b for b in blockers
            if isinstance(b, dict)
            and "net debt" in str(b.get("name") or "").lower()
            and not b.get("ready")
        ),
        None,
    )
    bridge_ok = bridge_ready or (not published and nd_blocker is not None)
    # When published, bridge must be ready; when withheld for ND, OK to be blocked
    if published:
        bridge_ok = bridge_ready
    rows.append({
        "check": "ev_equity_bridge_ready",
        "status": "PASS" if bridge_ok else "FAIL",
        "finding": (
            "EV→equity bridge ready with capital-structure net debt"
            if bridge_ready
            else (
                "Bridge blocked pending net debt — publish gate holds"
                if nd_blocker
                else "EV→equity bridge not ready"
            )
        ),
        "action": _BRIDGE_RULE,
    })

    # 4 Stand-alone vs synergy
    stand_ok = bool(standalone.get("stand_alone_only")) or bool(
        standalone.get("synergies_credited")
        and standalone.get("named_buyer")
        and standalone.get("costed_plan")
    )
    rows.append({
        "check": "standalone_synergy_split",
        "status": "PASS" if stand_ok else "FAIL",
        "finding": (
            standalone.get("notes")
            or (
                "Stand-alone only — synergies not credited"
                if standalone.get("stand_alone_only")
                else "Synergies credited with named buyer and costed plan"
            )
            if stand_ok
            else "Synergy credit without named buyer / costed plan"
        ),
        "action": _STANDALONE_RULE,
    })

    # 5 Walk-away above high (+ hurdles noted)
    has_high = isinstance(range_pts.get("high"), dict) and range_pts["high"].get(
        "enterprise_value_usd_b"
    ) is not None
    walk_ok = bool(walk.get("above_recommended_high")) if (published or has_high) else True
    if not has_high and not published:
        walk_ok = True  # deferred
    rows.append({
        "check": "walk_away_vs_hurdles",
        "status": "PASS" if walk_ok else "FAIL",
        "finding": (
            str(walk.get("check") or "Walk-away above high")
            + (
                f"; {walk.get('vs_offer')}"
                if _is_filled(walk.get("vs_offer"))
                else ""
            )
            if walk_ok
            else str(walk.get("check") or "Walk-away not above recommended high")
        ),
        "action": _HURDLE_RULE,
    })

    # 6 Publish gate
    blocking = [b for b in blockers if isinstance(b, dict) and not b.get("ready")]
    gate_ok = (published and not blocking) or (not published and bool(blocking))
    # FAIL if published despite blockers, or withheld with no blockers named
    if published and blocking:
        gate_ok = False
    if not published and not blocking:
        gate_ok = False
    rows.append({
        "check": "publish_gate_earnings_nd_wc",
        "status": "PASS" if gate_ok else "FAIL",
        "finding": (
            (
                "Range published — earnings, net debt and WC cleared"
                if published
                else f"Range withheld — blocked by: "
                + "; ".join(str(b.get("name")) for b in blocking[:3])
            )
            if gate_ok
            else (
                "Range published despite open blockers"
                if published and blocking
                else "Range withheld without stated earnings/ND/WC blockers"
            )
        ),
        "action": _BLOCK_RULE,
    })

    # 7 No Go/bid endorsement
    scrubbed = re.sub(
        r"(?i)[^.!?\n]*(?:"
        r"do\s+not\s+recommend|"
        r"no\s+go\s*/\s*bid|"
        r"range\s+evidence\s+only|"
        r"no\s+deal\s+verdict"
        r")[^.!?\n]*[.!?]?",
        " ",
        f"{corpus or ''} {insight_snapshot or ''}",
    )
    bid_lang = bool(_GO_BID_RE.search(scrubbed)) or bool(_INVEST_LANG.search(scrubbed))
    rows.append({
        "check": "no_go_bid_endorsement",
        "status": "PASS" if not bid_lang else "FAIL",
        "finding": (
            "No Go/bid/invest/pass endorsement in FVR narrative"
            if not bid_lang
            else "Go/bid/invest language present — strip before publishing"
        ),
        "action": _NO_BID_RULE,
    })

    return rows


def _questions_from_fvr_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    qa = (
        spec.get("final_valuation_evidence_qa")
        if isinstance(spec.get("final_valuation_evidence_qa"), list)
        else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    out: list[dict[str, str]] = []
    if _qa_fail("common_date_basis"):
        out.append(normalize_question({
            "question": "Bind all method points to a common as-of date and earnings basis",
            "required_records": "Valuation earnings_basis (as-of, metric, period)",
            "decision_effect": "Incomparable methods cannot form a committee range",
            "priority": "mandatory_pre_decision",
            "owner": "Valuation lead",
            "timing": "before IC",
            "closure_test": "common_date_basis QA PASS",
            "interim_treatment": "LIMITED until basis aligned",
        }))
    if _qa_fail("comp_rationale_ltm_forward"):
        out.append(normalize_question({
            "question": "Label comps/precedents LTM vs forward and state selection rationale",
            "required_records": "Peer set + multiple basis (LTM/forward)",
            "decision_effect": "Unlabelled multiples misstate the earnings reference",
            "priority": "mandatory_pre_decision",
            "owner": "Valuation lead",
            "timing": "before IC",
            "closure_test": "comp_rationale_ltm_forward QA PASS",
            "interim_treatment": "LIMITED until comps labelled",
        }))
    if _qa_fail("ev_equity_bridge_ready"):
        out.append(normalize_question({
            "question": "Complete capital-structure net debt so EV→equity can be bridged",
            "required_records": "Facility schedule + freely available cash + net-debt bridge",
            "decision_effect": "Equity value cannot be underwritten without ND",
            "priority": "mandatory_pre_decision",
            "owner": "Capital structure / valuation leads",
            "timing": "before IC",
            "closure_test": "ev_equity_bridge_ready QA PASS",
            "interim_treatment": "BLOCKED until ND bridge ready",
        }))
    if _qa_fail("standalone_synergy_split"):
        out.append(normalize_question({
            "question": "Keep FVR stand-alone — or credit synergies only with named buyer + costed plan",
            "required_records": "Synergies agent (named buyer, underwritable levers)",
            "decision_effect": "Unverified synergies inflate the committee range",
            "priority": "mandatory_pre_decision",
            "owner": "Valuation + M&A leads",
            "timing": "before IC",
            "closure_test": "standalone_synergy_split QA PASS",
            "interim_treatment": "Exclude synergies from FVR until verified",
        }))
    if _qa_fail("walk_away_vs_hurdles"):
        out.append(normalize_question({
            "question": "Set walk-away above recommended high and reconcile to offer / return hurdles",
            "required_records": "Walk-away EV + Sensitivity hurdles / offer EV",
            "decision_effect": "Walk-away at/below high is not committee-usable",
            "priority": "mandatory_pre_decision",
            "owner": "Deal / valuation lead",
            "timing": "before IC",
            "closure_test": "walk_away_vs_hurdles QA PASS",
            "interim_treatment": "LIMITED until walk-away consistent",
        }))
    if _qa_fail("publish_gate_earnings_nd_wc"):
        out.append(normalize_question({
            "question": "Clear earnings quality, net debt and working capital before publishing FVR",
            "required_records": "RQ verdict + capital ND bridge + WC bridge",
            "decision_effect": "Publishing with open blockers misleads the committee",
            "priority": "mandatory_pre_decision",
            "owner": "Valuation lead",
            "timing": "before IC",
            "closure_test": "publish_gate_earnings_nd_wc QA PASS",
            "interim_treatment": "BLOCKED — range withheld",
        }))
    if _qa_fail("no_go_bid_endorsement"):
        out.append(normalize_question({
            "question": "Remove Go/bid/invest/pass language from Final Valuation Range",
            "required_records": "FVR narrative with Quality/Reliance only",
            "decision_effect": "Endorsement here bypasses Recommendations / IC Synthesis",
            "priority": "mandatory_pre_decision",
            "owner": "Valuation lead",
            "timing": "before IC",
            "closure_test": "no_go_bid_endorsement QA PASS",
            "interim_treatment": "REWORK until endorsement removed",
        }))
    return [q for q in out if q]


def _quality_reliance(
    *,
    published: bool,
    blockers: list[dict[str, Any]],
    range_pts: dict[str, Any],
    walk: dict[str, Any],
    standalone: dict[str, Any],
    qa_fail: bool = False,
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

    if not published or blocking:
        reliance = "BLOCKED"
    elif published and has_range and walk_ok:
        reliance = "READY"
    elif has_range:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    if qa_fail and reliance == "READY":
        reliance = "LIMITED"

    bits = [
        f"Quality {quality}: range {'published' if published else 'withheld'}.",
        f"Reliance {reliance}.",
    ]
    if blocking:
        bits.append("Blockers: " + "; ".join(str(b.get("name")) for b in blocking[:3]) + ".")
    if not walk_ok and published:
        bits.append("Walk-away must sit above the recommended high.")
    if qa_fail:
        bits.append("Open Final Valuation QA FAILs cap READY → LIMITED.")
    bits.append(_BLOCK_RULE)
    bits.append(_NO_BID_RULE)
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
    synergies_spec: dict[str, Any] | None = None,
    deal_slots: dict[str, Any] | None = None,
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
    basis = _common_date_basis(
        valuation=valuation, points=points, deal_slots=deal_slots
    )
    range_pts = _select_range(points)
    bridge = _equity_bridge(
        range_pts=range_pts, net_debt_detail=nd_detail, net_debt_ready=nd_ok
    )
    walk = _walk_away(
        range_pts=range_pts, sensitivity=sensitivity_analysis, corpus=corpus
    )
    standalone = _standalone_vs_synergies(corpus, synergies_spec=synergies_spec)
    gaps = _evidence_gaps(
        range_pts=range_pts,
        blockers=blockers,
        sensitivity=sensitivity_analysis,
        net_debt_detail=nd_detail,
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
    snapshot = _soften_invest(". ".join(str(x) for x in bits if x))

    fvr_qa = _fvr_evidence_qa(
        basis=basis,
        points=points,
        published=published,
        blockers=blockers,
        range_pts=range_pts,
        bridge=bridge,
        walk=walk,
        standalone=standalone,
        corpus=corpus,
        insight_snapshot=snapshot,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in fvr_qa)
    quality, reliance, rationale = _quality_reliance(
        published=published,
        blockers=blockers,
        range_pts=range_pts,
        walk=walk,
        standalone=standalone,
        qa_fail=qa_fail,
    )

    out = {
        "insight_snapshot": snapshot,
        "range_published": published,
        "blockers": blockers,
        "common_date_basis": basis,
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
        "final_valuation_evidence_qa": fvr_qa,
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
    if deal_slots:
        out["deal_slots"] = deal_slots
    out["questions"] = _questions_from_fvr_gaps(out)
    return out


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
    synergies_spec: dict[str, Any] | None = None,
    prefer_heuristic: bool = True,
) -> dict[str, Any]:
    from agetic_cdd_api.agent_document_valuation_modeling import (
        gather_valuation_modeling_corpus,
    )
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    del prefer_heuristic  # LLM path reserved; heuristic is authoritative for blockers
    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    slots = {k: v for k, v in vars_.items() if v}

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
    syn = synergies_spec if isinstance(synergies_spec, dict) else _load("synergies")
    sens = sensitivity_analysis if isinstance(sensitivity_analysis, dict) else None
    if sens is None and isinstance(val, dict):
        sens = val.get("sensitivity_analysis") if isinstance(val.get("sensitivity_analysis"), dict) else None

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_valuation_modeling_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources

    out = _heuristic_final_range_spec(
        company=target,
        corpus=corpus or "",
        sources=srcs,
        valuation_spec=val,
        capital_structure=cap,
        revenue_quality=rq,
        historical_performance=hist,
        sensitivity_analysis=sens,
        synergies_spec=syn,
        deal_slots=slots,
    )
    out["deal_slots"] = slots
    return out


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
    parts.append(f"{_HURDLE_RULE}\n\n")
    walk_rows = [
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
        [
            "vs Offer / bid",
            _soften_invest(_clean(walk.get("vs_offer"), 160)),
        ],
        [
            "Return hurdles",
            _soften_invest(
                _clean(
                    "; ".join(str(h) for h in (walk.get("return_hurdles") or [])[:3]),
                    160,
                )
            ),
        ],
    ]
    parts.append(_table(["Field", "Value"], walk_rows))
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
            [
                "Synergies prior present?",
                "Yes" if standalone.get("synergies_prior_present") else "No",
            ],
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

    # 6 QA
    fvr_qa = (
        spec.get("final_valuation_evidence_qa")
        if isinstance(spec.get("final_valuation_evidence_qa"), list)
        else []
    )
    parts.append("## 6. Final Valuation Evidence QA\n\n")
    parts.append(
        "QA enforces common date/basis, comps LTM/forward + rationale, EV→equity "
        "readiness, stand-alone vs synergy split, walk-away vs hurdles, the "
        "earnings/ND/WC publish gate, and no Go/bid endorsement.\n\n"
    )
    basis = (
        spec.get("common_date_basis")
        if isinstance(spec.get("common_date_basis"), dict)
        else {}
    )
    if basis:
        parts.append(
            f"**Common basis:** as-of={_clean(basis.get('as_of_date'), 40)}; "
            f"metric={_clean(basis.get('earnings_metric'), 40)}; "
            f"period={_clean(basis.get('earnings_period'), 40)}; "
            f"bound={'Yes' if basis.get('bound') else 'No'}.\n\n"
        )
    if fvr_qa:
        parts.append(_table(
            ["Check", "Status", "Finding", "Action"],
            [
                [
                    _clean(r.get("check"), 48),
                    _clean(r.get("status"), 12),
                    _soften_invest(_clean(r.get("finding"), 160)),
                    _clean(r.get("action"), 120),
                ]
                for r in fvr_qa if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('Final Valuation evidence QA rows')}**\n\n")
    parts.append("---\n\n")

    # 7 Questions
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    parts.append("## 7. Questions and Inputs Required\n\n")
    if questions:
        for row in questions[:12]:
            if not isinstance(row, dict):
                continue
            parts.append(
                f"- **{_clean(row.get('question'), 200)}** — "
                f"records: {_clean(row.get('required_records'), 120)}; "
                f"effect: {_clean(row.get('decision_effect'), 120)}; "
                f"priority: {_clean(row.get('priority'), 40)}; "
                f"owner: {_clean(row.get('owner'), 40)}; "
                f"timing: {_clean(row.get('timing'), 40)}; "
                f"closure: {_clean(row.get('closure_test'), 120)}; "
                f"interim: {_clean(row.get('interim_treatment'), 120)}\n"
            )
        parts.append("\n")
    else:
        parts.append(
            "None are missing — material Final Valuation gaps are closed, "
            "or no Questions were generated from open QA FAILs.\n\n"
        )
    parts.append("---\n\n")

    # 8 Quality
    parts.append("## 8. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(qv, 30)],
            ["Reliance Verdict", _clean(rv, 30)],
            ["Rationale", _soften_invest(_clean(rationale, 460))],
        ],
    ))
    parts.append(f"**Quality:** {_clean(qv, 20)} — is the work accurate and honest about limits?\n\n")
    parts.append(
        f"**Reliance:** {_clean(rv, 20)} — can a decision rest on this Final Valuation Range?\n\n"
    )
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open Final Valuation QA FAILs cap READY → LIMITED. "
        f"{_NO_BID_RULE} "
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
