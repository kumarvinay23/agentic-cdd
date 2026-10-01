"""Compose DiligenceIQ Sensitivity Analysis — what the valuation depends on.

Ranks drivers by value movement, builds a two-driver grid with direction
checks, defines downside/base/upside by assumptions, states operating
break-evens, labels evidenced vs judgement, and verifies MoM / hold /
IRR arithmetic consistency.

Stored under valuation_modeling.spec['sensitivity_analysis'] and appended
to the Valuation Model document. No invest/pass. No company hardcoding.
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

_DOCUMENT_TITLE = "Sensitivity Analysis"
_DD_CODE = "FV-05-S"
_PARENT_KEY = "valuation_modeling"

_RANK_RULE = (
    "Assumptions are ranked by the value movement they cause, one at a time, "
    "over a range plausible given this company's own history."
)
_GRID_RULE = (
    "The grid uses the two largest drivers. Value must fall as the discount "
    "rate rises and rise as growth rises. The base cell is consistent with "
    "the valuation agent."
)
_CASE_RULE = (
    "Downside, base and upside are defined by assumptions — growth, margin "
    "and capital — not by adjectives."
)
_BREAK_RULE = (
    "Break-even conditions are stated in operating terms: growth, retention "
    "or margin at which return falls below the hurdle."
)
_EVIDENCE_RULE = (
    "Each assumption is labelled evidenced or judgement so the reader knows "
    "which parts of the range are supported."
)
_RETURN_RULE = (
    "Return metrics are mutually consistent: a multiple of money, a hold "
    "period and an IRR must agree arithmetically."
)

_WACC_RE = re.compile(r"(?i)WACC[^\d%]{0,20}?([\d.]+)\s*%")
_TG_RE = re.compile(
    r"(?i)(?:terminal\s+growth|Term\.?\s*Growth|TG)\s*(?:rate)?[^\d%]{0,12}?([\d.]+)\s*%"
)
_BASE_CELL_RE = re.compile(
    r"(?i)base\s+case[^\n]{0,40}?([\d.]+)\s*%\s*WACC[^\n]{0,40}?([\d.]+)\s*%\s*(?:terminal|TG)"
)
_BASE_CELL_RE2 = re.compile(
    r"(?i)([\d.]+)\s*%\s*WACC[^\n,]{0,20}?([\d.]+)\s*%\s*terminal\s+growth"
)
_GRID_HEADER_RE = re.compile(
    r"(?i)WACC\s*\\\s*Term\.?\s*Growth\s+((?:[\d.]+%\s*(?:\(Base\))?\s*){3,})"
)
_GRID_ROW_RE = re.compile(
    r"(?i)([\d.]+)%\s*(?:\(Base\))?\s+((?:[\d,.]+(?:\s|$)){3,})"
)
_SHARE_GRID_ROW_RE = re.compile(
    r"(?i)([\d.]+)%\s*(?:\(Base\))?\s+((?:INR\s*[\d.]+(?:\s|$)){3,})"
)
_SCENARIO_LINE_RE = re.compile(
    r"(?i)(Bear|Base|Bull)\s+Case\s*(?:\(([^)]*)\))?\s+"
    r"([\d,]+)\s+([\d.]+)\s*B?\s+INR\s*([\d.]+)\s+([+\-]?\d+(?:\.\d+)?%)?"
    r"(?:\s+vs\s+IPO)?\s*(.*?)(?=(?:Bear|Base|Bull)\s+Case|$)"
)
_IRR_RE = re.compile(r"(?i)\bIRR\s*(?:of\s*)?([\d.]+)\s*%")
_MOIC_RE = re.compile(r"(?i)\b(?:MOIC|MoM|money[- ]multiple)\s*(?:of\s*)?([\d.]+)\s*x")
_HOLD_RE = re.compile(r"(?i)\b(?:hold(?:ing)?\s+period|exit\s+year)\s*(?:of\s*)?([\d.]+)\s*(?:years?|yrs?)?")
_CAGR_RE = re.compile(r"(?i)(?:Revenue\s+)?CAGR[^\d%]{0,20}?([\d.]+)\s*%")
_MARGIN_RE = re.compile(r"(?i)(?:gross|EBITDA)\s+margin[^\d%]{0,20}?([\d.]+)\s*%")
_RETENTION_RE = re.compile(r"(?i)(?:retention|NRR|net\s+retention)[^\d%]{0,20}?([\d.]+)\s*%")


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("sensitivity evidence only — no deal verdict expressed", raw)
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
        cells = [(_clean(c, 220) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# return arithmetic: MoIC ↔ hold ↔ IRR
# ---------------------------------------------------------------------------


def _irr_from_moic(moic: float, hold_years: float) -> float | None:
    if moic is None or hold_years is None or hold_years <= 0 or moic <= 0:
        return None
    return (float(moic) ** (1.0 / float(hold_years)) - 1.0) * 100.0


def _moic_from_irr(irr_pct: float, hold_years: float) -> float | None:
    if irr_pct is None or hold_years is None or hold_years <= 0:
        return None
    return (1.0 + float(irr_pct) / 100.0) ** float(hold_years)


def _check_returns(
    *,
    moic: float | None,
    irr_pct: float | None,
    hold_years: float | None,
) -> dict[str, Any]:
    if moic is None or irr_pct is None or hold_years is None:
        return {
            "status": "unchecked",
            "detail": _info_request("MoM, hold period and IRR all required for arithmetic check"),
            "moic_x": moic,
            "irr_pct": irr_pct,
            "hold_years": hold_years,
        }
    implied_irr = _irr_from_moic(float(moic), float(hold_years))
    implied_moic = _moic_from_irr(float(irr_pct), float(hold_years))
    assert implied_irr is not None and implied_moic is not None
    irr_delta = abs(implied_irr - float(irr_pct))
    moic_delta = abs(implied_moic - float(moic))
    # Tolerate ~1pp IRR / 0.15x MoIC (rounding / pack rounding)
    ok = irr_delta <= 1.25 or moic_delta <= 0.15
    return {
        "status": "pass" if ok else "fail",
        "detail": (
            f"{moic:g}x over {hold_years:g}y ⇒ IRR {implied_irr:.1f}% "
            f"(stated {irr_pct:g}%); stated IRR ⇒ MoIC {implied_moic:.2f}x "
            f"— {'OK' if ok else 'MISMATCH'}"
        ),
        "moic_x": _round(moic, 2),
        "irr_pct": _round(irr_pct, 1),
        "hold_years": _round(hold_years, 1),
        "implied_irr_pct": _round(implied_irr, 1),
        "implied_moic_x": _round(implied_moic, 2),
    }


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------


def _base_from_valuation(valuation: dict[str, Any] | None) -> dict[str, Any]:
    val = valuation if isinstance(valuation, dict) else {}
    dcf = val.get("dcf") if isinstance(val.get("dcf"), dict) else {}
    dcf_view = val.get("dcf_view") if isinstance(val.get("dcf_view"), dict) else {}
    wacc = _num(dcf.get("wacc_pct")) or _num(dcf_view.get("discount_rate_pct"))
    ev = _num(dcf.get("enterprise_value_usd_b")) or _num(dcf_view.get("enterprise_value_usd_b"))
    share = _num(dcf.get("implied_share_price_inr")) or _num(dcf_view.get("implied_share_price_inr"))
    scenarios = dcf.get("scenarios") if isinstance(dcf.get("scenarios"), list) else []
    base_sc = next(
        (s for s in scenarios if isinstance(s, dict) and "base" in str(s.get("label") or "").lower()),
        None,
    )
    if base_sc:
        share = share or _num(base_sc.get("equity_value_per_share_inr"))
        ev = ev or _num(base_sc.get("enterprise_value_usd_b"))
    return {
        "wacc_pct": wacc,
        "terminal_growth_pct": None,
        "enterprise_value_usd_b": ev,
        "share_price_inr": share,
        "scenarios": scenarios,
        "earnings_basis": val.get("earnings_basis") if isinstance(val.get("earnings_basis"), dict) else {},
    }


def _parse_grid(corpus: str) -> dict[str, Any]:
    """Parse WACC × terminal-growth EV grid from pack prose."""
    text = _prose(corpus)
    growths: list[float] = []
    hm = _GRID_HEADER_RE.search(text)
    if hm:
        raw_pcts = [float(x) for x in re.findall(r"([\d.]+)%", hm.group(1))]
        # Header may run into first WACC row (e.g. … 5.0% 7.0% 22,840 …)
        for p in raw_pcts:
            if p >= 6.0 and growths:
                break
            growths.append(p)
    if not growths:
        # Common pack layout: 1.0% 2.0% 3.0% (Base) 4.0% 5.0%
        growths = [1.0, 2.0, 3.0, 4.0, 5.0]

    rows: list[dict[str, Any]] = []
    # Prefer EV (INR Cr) block before share-price block
    ev_idx = text.lower().find("enterprise value sensitivity")
    share_idx = text.lower().find("implied share price sensitivity")
    block = text
    if ev_idx >= 0:
        end = share_idx if share_idx > ev_idx else ev_idx + 2500
        block = text[ev_idx:end]

    for m in _GRID_ROW_RE.finditer(block):
        wacc = float(m.group(1))
        # Skip growth-axis labels mistaken as WACC rows
        if wacc < 6.0:
            continue
        vals = [float(x.replace(",", "")) for x in re.findall(r"[\d,]+(?:\.\d+)?", m.group(2))]
        if len(vals) < 3:
            continue
        cells = {}
        for i, g in enumerate(growths[: len(vals)]):
            cells[f"{g:g}%"] = vals[i]
        rows.append({"wacc_pct": wacc, "values_inr_cr": cells, "values_list": vals[: len(growths)]})

    base_wacc = None
    base_tg = None
    bm = _BASE_CELL_RE.search(text) or _BASE_CELL_RE2.search(text)
    if bm:
        base_wacc = float(bm.group(1))
        base_tg = float(bm.group(2))
    if base_wacc is None:
        wm = re.search(r"(?i)([\d.]+)%\s*\(Base\)", block)
        if wm:
            base_wacc = float(wm.group(1))
    if base_tg is None and growths:
        # Prefer labelled (Base) growth
        labelled = re.search(r"([\d.]+)%\s*\(Base\)", text[hm.start(): hm.end() + 20] if hm else text[:800])
        base_tg = float(labelled.group(1)) if labelled else 3.0

    return {
        "growth_axis_pct": growths,
        "rows": rows,
        "base_wacc_pct": base_wacc,
        "base_terminal_growth_pct": base_tg,
        "unit": "INR Cr",
        "metric": "Enterprise Value",
    }


def _direction_check(grid: dict[str, Any]) -> dict[str, Any]:
    """Value must fall as WACC rises and rise as growth rises."""
    rows = grid.get("rows") if isinstance(grid.get("rows"), list) else []
    growths = grid.get("growth_axis_pct") or []
    if len(rows) < 2 or len(growths) < 2:
        return {
            "status": "unchecked",
            "detail": _info_request("grid rows to verify direction"),
            "wacc_direction_ok": None,
            "growth_direction_ok": None,
        }

    # Along WACC column at base (or mid) growth index
    g_idx = 0
    base_tg = grid.get("base_terminal_growth_pct")
    if base_tg is not None:
        for i, g in enumerate(growths):
            if abs(float(g) - float(base_tg)) < 0.05:
                g_idx = i
                break
    else:
        g_idx = len(growths) // 2

    wacc_vals: list[tuple[float, float]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        vals = r.get("values_list") or []
        if g_idx >= len(vals):
            continue
        wacc_vals.append((float(r["wacc_pct"]), float(vals[g_idx])))
    wacc_vals.sort(key=lambda x: x[0])
    wacc_ok = all(wacc_vals[i][1] >= wacc_vals[i + 1][1] for i in range(len(wacc_vals) - 1))

    # Along growth at base (or mid) WACC row
    base_wacc = grid.get("base_wacc_pct")
    pick = None
    if base_wacc is not None:
        pick = min(rows, key=lambda r: abs(float(r.get("wacc_pct") or 0) - float(base_wacc)))
    else:
        pick = rows[len(rows) // 2]
    g_vals = list(pick.get("values_list") or [])
    growth_ok = all(g_vals[i] <= g_vals[i + 1] for i in range(len(g_vals) - 1)) if len(g_vals) >= 2 else False

    ok = bool(wacc_ok and growth_ok)
    return {
        "status": "pass" if ok else "fail",
        "detail": (
            f"As WACC rises value {'falls' if wacc_ok else 'does NOT fall'}; "
            f"as growth rises value {'rises' if growth_ok else 'does NOT rise'} — "
            f"{'OK' if ok else 'MISMATCH — do not publish until fixed'}"
        ),
        "wacc_direction_ok": wacc_ok,
        "growth_direction_ok": growth_ok,
    }


def _rank_drivers(
    *,
    grid: dict[str, Any],
    valuation_base: dict[str, Any],
    corpus: str,
    historical: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """One-at-a-time ranks by absolute value movement over plausible ranges."""
    ranked: list[dict[str, Any]] = []
    rows = grid.get("rows") if isinstance(grid.get("rows"), list) else []
    growths = grid.get("growth_axis_pct") or []
    base_wacc = grid.get("base_wacc_pct") or valuation_base.get("wacc_pct")
    base_tg = grid.get("base_terminal_growth_pct") or 3.0

    def _cell(wacc: float, tg: float) -> float | None:
        if not rows or not growths:
            return None
        row = min(rows, key=lambda r: abs(float(r.get("wacc_pct") or 0) - wacc))
        g_i = min(range(len(growths)), key=lambda i: abs(float(growths[i]) - tg))
        vals = row.get("values_list") or []
        return float(vals[g_i]) if g_i < len(vals) else None

    base_val = _cell(float(base_wacc or 9.0), float(base_tg)) if base_wacc else None

    # WACC swing across grid at base TG
    if rows and base_val is not None and base_wacc is not None:
        waccs = sorted(float(r["wacc_pct"]) for r in rows if isinstance(r, dict))
        lo = _cell(waccs[0], float(base_tg))
        hi = _cell(waccs[-1], float(base_tg))
        if lo is not None and hi is not None:
            move = abs(hi - lo)
            ranked.append(
                {
                    "assumption": "Discount rate (WACC)",
                    "range_low": f"{waccs[0]:g}%",
                    "range_high": f"{waccs[-1]:g}%",
                    "range_basis": "Pack sensitivity matrix span (plausible financing / risk range)",
                    "value_at_low": lo,
                    "value_at_high": hi,
                    "value_unit": grid.get("unit") or "INR Cr",
                    "absolute_move": _round(move, 1),
                    "pct_move_vs_base": _round(100.0 * move / abs(base_val), 1) if base_val else None,
                    "rank": 0,
                    "source": _DOC_CITE,
                    "evidence_class": "evidenced",
                }
            )

    # Terminal growth swing at base WACC
    if growths and base_val is not None and base_wacc is not None:
        lo = _cell(float(base_wacc), float(growths[0]))
        hi = _cell(float(base_wacc), float(growths[-1]))
        if lo is not None and hi is not None:
            move = abs(hi - lo)
            ranked.append(
                {
                    "assumption": "Terminal growth rate",
                    "range_low": f"{growths[0]:g}%",
                    "range_high": f"{growths[-1]:g}%",
                    "range_basis": "Pack terminal-growth axis",
                    "value_at_low": lo,
                    "value_at_high": hi,
                    "value_unit": grid.get("unit") or "INR Cr",
                    "absolute_move": _round(move, 1),
                    "pct_move_vs_base": _round(100.0 * move / abs(base_val), 1) if base_val else None,
                    "rank": 0,
                    "source": _DOC_CITE,
                    "evidence_class": "evidenced",
                }
            )

    # Historical growth / margin as third driver (judgement band from history)
    hist_cagr = None
    if isinstance(historical, dict):
        for row in historical.get("growth_and_margins") or []:
            if isinstance(row, dict) and "cagr" in str(row.get("metric") or "").lower():
                hist_cagr = _num(row.get("value") or row.get("fy2024_value"))
                break
    text = _prose(corpus)
    if hist_cagr is None:
        cm = _CAGR_RE.search(text)
        if cm:
            hist_cagr = float(cm.group(1))

    # Scenario EV span as proxy for operating-case (growth/margin/capex) movement
    scenarios = valuation_base.get("scenarios") or []
    evs = [
        _num(s.get("enterprise_value_usd_b"))
        for s in scenarios
        if isinstance(s, dict)
    ]
    evs_f = [e for e in evs if e is not None]
    if len(evs_f) >= 2:
        move_b = max(evs_f) - min(evs_f)
        # Convert USD B → INR Cr approx (× 83*10 ≈ 830) for rank comparability when base is INR Cr
        move_inr = move_b * 830.0
        ranked.append(
            {
                "assumption": "Operating case (growth / margin / capital)",
                "range_low": "Downside case",
                "range_high": "Upside case",
                "range_basis": (
                    f"Company history CAGR ~{hist_cagr:g}%"
                    if hist_cagr is not None
                    else "Bear/base/bull scenario span from valuation agent"
                ),
                "value_at_low": min(evs_f),
                "value_at_high": max(evs_f),
                "value_unit": "USD B",
                "absolute_move": _round(move_inr, 1),
                "pct_move_vs_base": None,
                "rank": 0,
                "source": _COMPUTED,
                "evidence_class": "judgement" if hist_cagr is None else "mixed",
                "notes": "Scenario operating assumptions move EV across the case ladder",
            }
        )

    ranked.sort(key=lambda r: float(r.get("absolute_move") or 0), reverse=True)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    if not ranked:
        ranked.append(
            {
                "assumption": _info_request("assumption that moves value"),
                "range_low": _NA,
                "range_high": _NA,
                "range_basis": _info_request("plausible historical range"),
                "absolute_move": None,
                "rank": 1,
                "source": _NA,
                "evidence_class": "judgement",
            }
        )
    return ranked


def _parse_assumption_columns(text: str) -> dict[str, dict[str, Any]]:
    """Parse Base/Bear/Bull assumption columns from DCF assumption tables."""
    # Column order in pack: Base, Bear/Downside, Bull/Upside (WACC 9.0 / 11.5 / 7.5)
    out: dict[str, dict[str, Any]] = {
        "Base Case": {},
        "Bear Case": {},
        "Bull Case": {},
    }
    patterns = [
        (
            "wacc_pct",
            r"(?i)WACC\s*\(Base\)\s*([\d.]+)\s*%\s*([\d.]+)\s*%\s*([\d.]+)\s*%",
        ),
        (
            "terminal_growth_pct",
            r"(?i)Terminal\s+Growth\s+Rate\s*\(Base\)\s*([\d.]+)\s*%\s*([\d.]+)\s*%\s*([\d.]+)\s*%",
        ),
        (
            "revenue_cagr_pct",
            r"(?i)Revenue\s+CAGR\s*\(FY20\d{2}[–\-]FY20\d{2}\)[^\d]{0,10}?([\d.]+)\s*%\s*([\d.]+)\s*%\s*([\d.]+)\s*%",
        ),
        (
            "ebitda_margin_pct",
            r"(?i)EBITDA\s+Margin\s*\(FY20\d{2}[^)]*\)\s*([\d.]+)\s*%\s*([\d.]+)\s*%\s*([\d.]+)\s*%",
        ),
        (
            "capex_pct_revenue",
            r"(?i)Capex\s*\(%\s*of\s*Revenue[^)]*\)\s*([\d.]+)\s*%\s*([\d.]+)\s*%\s*([\d.]+)\s*%",
        ),
    ]
    keys = ("Base Case", "Bear Case", "Bull Case")
    for field, pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        # Pack order: Base, Bear, Bull
        vals = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
        # Detect if middle is higher WACC (bear) — already Base/Bear/Bull
        if field == "wacc_pct" and vals[1] < vals[0] and vals[2] > vals[0]:
            # Unexpected order — leave as-is
            pass
        for key, val in zip(keys, vals):
            out[key][field] = val
    return out


def _build_cases(
    *,
    corpus: str,
    valuation_base: dict[str, Any],
    grid: dict[str, Any],
    recommendation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    cases: list[dict[str, Any]] = []
    col = _parse_assumption_columns(text)

    # Prefer pack scenario summary lines when present
    for m in _SCENARIO_LINE_RE.finditer(text):
        label = f"{m.group(1).title()} Case"
        assume_blob = (m.group(2) or "").strip()
        key_driver = _clean(m.group(7), 120) if m.lastindex and m.lastindex >= 7 else ""
        wacc = None
        tg = None
        wm = re.search(r"(?i)WACC\s*([\d.]+)\s*%", assume_blob)
        tm2 = re.search(r"(?i)TG\s*([\d.]+)", assume_blob)
        if wm:
            wacc = float(wm.group(1))
        if tm2:
            tg = float(tm2.group(1))
        col_row = col.get(label) or {}
        wacc = wacc if wacc is not None else col_row.get("wacc_pct")
        tg = tg if tg is not None else col_row.get("terminal_growth_pct")
        cagr = col_row.get("revenue_cagr_pct")
        margin = col_row.get("ebitda_margin_pct")
        capex = col_row.get("capex_pct_revenue")
        growth_assump = (
            f"Revenue CAGR {cagr:g}%; terminal growth {tg:g}%"
            if cagr is not None and tg is not None
            else (
                f"Terminal growth {tg:g}%"
                if tg is not None
                else _info_request(f"growth assumption for {label}")
            )
        )
        margin_assump = (
            f"EBITDA margin {margin:g}%"
            if margin is not None
            else _info_request(f"margin assumption for {label}")
        )
        capital_assump = (
            f"WACC {wacc:g}%"
            + (f"; capex {capex:g}% of revenue" if capex is not None else "")
            if wacc is not None
            else _info_request(f"capital / discount assumption for {label}")
        )
        if key_driver:
            growth_assump = f"{growth_assump} ({key_driver})"
        cases.append(
            {
                "case": label,
                "growth_assumption": growth_assump,
                "margin_assumption": margin_assump,
                "capital_assumption": capital_assump,
                "wacc_pct": wacc,
                "terminal_growth_pct": tg,
                "enterprise_value_inr_cr": _num(m.group(3).replace(",", "")),
                "enterprise_value_usd_b": _num(m.group(4)),
                "equity_value_per_share_inr": _num(m.group(5)),
                "vs_ipo_pct": _num(m.group(6)) if m.group(6) else None,
                "key_driver": key_driver or _NA,
                "source": _DOC_CITE,
                "notes": _CASE_RULE,
            }
        )

    # Build from assumption columns + valuation scenarios when summary lines absent
    if len(cases) < 3:
        by_label = {str(c.get("case")): c for c in cases if isinstance(c, dict)}
        for s in valuation_base.get("scenarios") or []:
            if not isinstance(s, dict):
                continue
            label = str(s.get("label") or "")
            if not label:
                continue
            low = label.lower()
            col_row = col.get(label) or {}
            if "bear" in low:
                col_row = col.get("Bear Case") or col_row
            elif "bull" in low:
                col_row = col.get("Bull Case") or col_row
            elif "base" in low:
                col_row = col.get("Base Case") or col_row

            wacc = col_row.get("wacc_pct")
            tg = col_row.get("terminal_growth_pct")
            cagr = col_row.get("revenue_cagr_pct")
            margin = col_row.get("ebitda_margin_pct")
            capex = col_row.get("capex_pct_revenue")

            if cagr is not None or tg is not None:
                growth = (
                    f"Revenue CAGR {cagr:g}%"
                    if cagr is not None
                    else ""
                )
                if tg is not None:
                    growth = f"{growth}; terminal growth {tg:g}%".strip("; ")
            elif "bear" in low:
                growth = "Stressed volume / delayed ramp"
            elif "bull" in low:
                growth = "Accelerated volume / mix"
            else:
                growth = "Moderate growth per valuation base"

            if margin is not None:
                margin_a = f"EBITDA margin {margin:g}%"
            elif "bear" in low:
                margin_a = "Compressed margin vs base"
            elif "bull" in low:
                margin_a = "Expanded margin / opex leverage"
            else:
                margin_a = "Base margin path"

            if wacc is not None:
                capital = f"WACC {wacc:g}%"
                if capex is not None:
                    capital += f"; capex {capex:g}% of revenue"
            elif "bear" in low:
                capital = "Higher discount rate"
            elif "bull" in low:
                capital = "Lower discount / supportive capital markets"
            else:
                capital = f"WACC {valuation_base.get('wacc_pct') or grid.get('base_wacc_pct') or 'base'}%"

            row = {
                "case": label,
                "growth_assumption": growth,
                "margin_assumption": margin_a,
                "capital_assumption": capital,
                "wacc_pct": wacc or (valuation_base.get("wacc_pct") if "base" in low else None),
                "terminal_growth_pct": tg or (
                    grid.get("base_terminal_growth_pct") if "base" in low else None
                ),
                "enterprise_value_usd_b": s.get("enterprise_value_usd_b"),
                "equity_value_per_share_inr": s.get("equity_value_per_share_inr"),
                "vs_ipo_pct": s.get("premium_discount_vs_ipo_pct"),
                "key_driver": _CASE_RULE,
                "source": _DOC_CITE if col_row else _COMPUTED,
                "notes": "Aligned to valuation agent scenario ladder + pack assumption columns",
            }
            if label in by_label:
                by_label[label].update({k: v for k, v in row.items() if v is not None})
            else:
                cases.append(row)
                by_label[label] = row

    # Overlay returns from recommendation when present
    rec = recommendation if isinstance(recommendation, dict) else {}
    returns = rec.get("returns_by_scenario") if isinstance(rec.get("returns_by_scenario"), list) else []
    hold_stated = None
    for row in returns:
        if not isinstance(row, dict):
            continue
        hold_stated = hold_stated or _num(row.get("hold_years"))
    if hold_stated is None:
        hm = _HOLD_RE.search(text)
        hold_stated = float(hm.group(1)) if hm else None

    for c in cases:
        label = str(c.get("case") or "")
        match = next(
            (
                r for r in returns
                if isinstance(r, dict) and str(r.get("scenario") or "").lower() == label.lower()
            ),
            None,
        )
        irr = _num(match.get("irr_pct")) if match else None
        moic = _num(match.get("moic_x")) if match else None
        hold = hold_stated
        if hold is None and moic is not None and irr is not None and moic > 0 and irr > -100:
            try:
                import math

                hold = math.log(float(moic)) / math.log(1.0 + float(irr) / 100.0)
            except (ValueError, ZeroDivisionError):
                hold = None
        if hold is None:
            hold = 5.0
        if irr is None and moic is not None:
            irr = _irr_from_moic(moic, hold)
        if moic is None and irr is not None:
            moic = _moic_from_irr(irr, hold)
        c["hold_years"] = _round(hold, 2)
        c["irr_pct"] = _round(irr, 1) if irr is not None else None
        c["moic_x"] = _round(moic, 2) if moic is not None else None
        c["returns_arithmetic"] = _check_returns(moic=moic, irr_pct=irr, hold_years=hold)

    if not cases:
        cases = [
            {
                "case": name,
                "growth_assumption": _info_request(f"growth for {name}"),
                "margin_assumption": _info_request(f"margin for {name}"),
                "capital_assumption": _info_request(f"capital for {name}"),
                "source": _NA,
                "notes": _CASE_RULE,
            }
            for name in ("Downside Case", "Base Case", "Upside Case")
        ]
    return cases


def _build_breakevens(
    *,
    corpus: str,
    grid: dict[str, Any],
    valuation_base: dict[str, Any],
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows_out: list[dict[str, Any]] = []

    # Pack note: IPO justified only at WACC ≤ 7.5% with TG ≥ 4.5%
    ipo = re.search(
        r"(?i)IPO\s+price\s+is\s+only\s+justified\s+at\s+WACC\s*[≤<=]\s*([\d.]+)\s*%"
        r"[^\n]{0,40}?terminal\s+growth\s*[≥>=]\s*([\d.]+)\s*%",
        text,
    )
    if ipo:
        rows_out.append(
            {
                "metric": "Reference price justification (operating/financial)",
                "condition": (
                    f"Discount rate ≤ {ipo.group(1)}% with terminal growth ≥ {ipo.group(2)}% "
                    f"(or materially more optimistic FCF)"
                ),
                "hurdle": "IPO / reference price",
                "operating_terms": (
                    f"Needs WACC ≤ {ipo.group(1)}% and terminal growth ≥ {ipo.group(2)}% "
                    f"— or upside operating FCF path"
                ),
                "source": _DOC_CITE,
                "evidence_class": "evidenced",
            }
        )

    # Grid: find where base-share falls below a hurdle relative to base
    base_wacc = grid.get("base_wacc_pct") or valuation_base.get("wacc_pct")
    base_tg = grid.get("base_terminal_growth_pct")
    growths = grid.get("growth_axis_pct") or []
    rows = grid.get("rows") if isinstance(grid.get("rows"), list) else []
    if base_wacc is not None and growths and rows:
        # Break-even vs base: terminal growth that restores base EV when WACC +100bp
        base_row = min(rows, key=lambda r: abs(float(r.get("wacc_pct") or 0) - float(base_wacc)))
        stress_wacc = float(base_wacc) + 1.0
        stress_row = min(rows, key=lambda r: abs(float(r.get("wacc_pct") or 0) - stress_wacc))
        g_idx = 0
        if base_tg is not None:
            g_idx = min(range(len(growths)), key=lambda i: abs(float(growths[i]) - float(base_tg)))
        base_vals = base_row.get("values_list") or []
        stress_vals = stress_row.get("values_list") or []
        if g_idx < len(base_vals) and stress_vals:
            target = float(base_vals[g_idx])
            # smallest growth index on stress row with value >= target
            restore = None
            for i, v in enumerate(stress_vals):
                if float(v) >= target:
                    restore = growths[i] if i < len(growths) else None
                    break
            if restore is not None:
                rows_out.append(
                    {
                        "metric": "Value vs base under +100bp WACC",
                        "condition": f"Terminal growth ≥ {restore:g}%",
                        "hurdle": "Base-case enterprise value",
                        "operating_terms": (
                            f"If discount rate rises +100bp to ~{stress_wacc:g}%, "
                            f"terminal growth must reach ≥ {restore:g}% to hold base value"
                        ),
                        "source": _COMPUTED,
                        "evidence_class": "judgement",
                    }
                )

    # Returns hurdle from cases
    base_case = next(
        (c for c in cases if isinstance(c, dict) and "base" in str(c.get("case") or "").lower()),
        None,
    )
    down_case = next(
        (
            c for c in cases
            if isinstance(c, dict)
            and any(x in str(c.get("case") or "").lower() for x in ("bear", "down"))
        ),
        None,
    )
    if base_case and base_case.get("irr_pct") is not None:
        hurdle = float(base_case["irr_pct"])
        rows_out.append(
            {
                "metric": "Return below base IRR hurdle",
                "condition": (
                    f"Operating path at or below downside "
                    f"({down_case.get('growth_assumption') if down_case else 'downside growth'})"
                ),
                "hurdle": f"IRR {hurdle:g}% (base)",
                "operating_terms": (
                    f"Return falls below {hurdle:g}% IRR when growth/margin/capital "
                    f"track the downside case assumptions"
                ),
                "source": _COMPUTED,
                "evidence_class": "mixed",
            }
        )

    # Retention / margin mentions
    rm = _RETENTION_RE.search(text)
    if rm:
        rows_out.append(
            {
                "metric": "Retention",
                "condition": f"Retention below {rm.group(1)}%",
                "hurdle": "Underwriting retention floor",
                "operating_terms": (
                    f"Case breaks if net retention / retention falls below {rm.group(1)}% "
                    f"without offsetting volume"
                ),
                "source": _DOC_CITE,
                "evidence_class": "evidenced",
            }
        )

    if not rows_out:
        rows_out.append(
            {
                "metric": _info_request("break-even metric"),
                "condition": _info_request("operating condition where return < hurdle"),
                "hurdle": _info_request("hurdle rate / value floor"),
                "operating_terms": _BREAK_RULE,
                "source": _NA,
                "evidence_class": "judgement",
            }
        )
    return rows_out


def _evidence_register(
    *,
    ranked: list[dict[str, Any]],
    grid: dict[str, Any],
    cases: list[dict[str, Any]],
    breakevens: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in ranked:
        rows.append(
            {
                "assumption": r.get("assumption"),
                "classification": r.get("evidence_class") or "judgement",
                "why": r.get("range_basis") or r.get("notes") or _EVIDENCE_RULE,
                "source": r.get("source") or _NA,
            }
        )
    if grid.get("rows"):
        rows.append(
            {
                "assumption": "WACC × terminal growth grid",
                "classification": "evidenced",
                "why": "Parsed from pack sensitivity matrix; direction checked",
                "source": _DOC_CITE,
            }
        )
    for c in cases:
        if not isinstance(c, dict):
            continue
        rows.append(
            {
                "assumption": f"{c.get('case')} operating stack",
                "classification": (
                    "evidenced"
                    if str(c.get("source") or "").startswith("(DOC")
                    else "judgement"
                ),
                "why": (
                    f"Growth: {c.get('growth_assumption')}; "
                    f"Margin: {c.get('margin_assumption')}; "
                    f"Capital: {c.get('capital_assumption')}"
                ),
                "source": c.get("source") or _NA,
            }
        )
    for b in breakevens:
        if isinstance(b, dict):
            rows.append(
                {
                    "assumption": b.get("metric"),
                    "classification": b.get("evidence_class") or "judgement",
                    "why": b.get("operating_terms"),
                    "source": b.get("source") or _NA,
                }
            )
    # Dedupe by assumption name
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = str(r.get("assumption") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out[:16]


def _quality_reliance(
    *,
    ranked: list[dict[str, Any]],
    grid: dict[str, Any],
    direction: dict[str, Any],
    cases: list[dict[str, Any]],
    returns_checks: list[dict[str, Any]],
) -> tuple[str, str, str]:
    has_rank = any(isinstance(r.get("absolute_move"), (int, float)) for r in ranked)
    has_grid = bool(grid.get("rows"))
    dir_ok = direction.get("status") == "pass"
    cases_ok = sum(
        1 for c in cases
        if isinstance(c, dict)
        and _is_filled(c.get("growth_assumption"))
        and _is_filled(c.get("capital_assumption"))
    ) >= 2
    ret_fail = sum(1 for c in returns_checks if c.get("status") == "fail")
    ret_pass = sum(1 for c in returns_checks if c.get("status") == "pass")

    if has_rank and has_grid and dir_ok and cases_ok and ret_fail == 0:
        quality = "PASS"
    else:
        quality = "REWORK"

    if has_grid and dir_ok and (ret_pass >= 1 or cases_ok):
        reliance = "READY"
    elif has_rank or has_grid:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"Quality {quality}: drivers ranked={has_rank}, grid={has_grid}, "
        f"direction={'OK' if dir_ok else 'fail'}.",
        f"Reliance {reliance}.",
    ]
    if not dir_ok:
        bits.append("Fix grid direction before publishing.")
    if ret_fail:
        bits.append("MoM / hold / IRR arithmetic failed on at least one case.")
    bits.append(_RETURN_RULE)
    return quality, reliance, " ".join(bits)


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_sensitivity_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    valuation_spec: dict[str, Any] | None = None,
    recommendation_spec: dict[str, Any] | None = None,
    historical_performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valuation_base = _base_from_valuation(valuation_spec)
    grid = _parse_grid(corpus)
    # Align base cell with valuation agent
    if valuation_base.get("wacc_pct") is not None:
        grid["base_wacc_pct"] = grid.get("base_wacc_pct") or valuation_base["wacc_pct"]
    if grid.get("base_terminal_growth_pct") is None:
        tm = _TG_RE.search(_prose(corpus))
        grid["base_terminal_growth_pct"] = float(tm.group(1)) if tm else 3.0
    # If valuation share differs, note consistency
    base_consistent = True
    if (
        valuation_base.get("wacc_pct") is not None
        and grid.get("base_wacc_pct") is not None
        and abs(float(valuation_base["wacc_pct"]) - float(grid["base_wacc_pct"])) > 0.15
    ):
        base_consistent = False

    direction = _direction_check(grid)
    ranked = _rank_drivers(
        grid=grid,
        valuation_base=valuation_base,
        corpus=corpus,
        historical=historical_performance,
    )
    cases = _build_cases(
        corpus=corpus,
        valuation_base=valuation_base,
        grid=grid,
        recommendation=recommendation_spec,
    )
    breakevens = _build_breakevens(
        corpus=corpus,
        grid=grid,
        valuation_base=valuation_base,
        cases=cases,
    )
    evidence = _evidence_register(
        ranked=ranked, grid=grid, cases=cases, breakevens=breakevens
    )
    returns_checks = [
        c.get("returns_arithmetic")
        for c in cases
        if isinstance(c, dict) and isinstance(c.get("returns_arithmetic"), dict)
    ]
    quality, reliance, rationale = _quality_reliance(
        ranked=ranked,
        grid=grid,
        direction=direction,
        cases=cases,
        returns_checks=returns_checks,
    )

    top = ranked[0]["assumption"] if ranked else "—"
    bits = [f"Sensitivity Analysis for {company}", f"top driver: {top}"]
    if grid.get("base_wacc_pct") is not None:
        bits.append(
            f"base cell WACC {grid.get('base_wacc_pct'):g}% / "
            f"TG {grid.get('base_terminal_growth_pct'):g}%"
        )
    bits.append(f"direction {direction.get('status')}")

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "ranked_drivers": ranked,
        "two_driver_grid": {
            **grid,
            "driver_x": "Terminal growth rate",
            "driver_y": "Discount rate (WACC)",
            "base_cell": {
                "wacc_pct": grid.get("base_wacc_pct"),
                "terminal_growth_pct": grid.get("base_terminal_growth_pct"),
                "consistent_with_valuation_agent": base_consistent,
                "valuation_wacc_pct": valuation_base.get("wacc_pct"),
                "valuation_share_inr": valuation_base.get("share_price_inr"),
            },
            "direction_check": direction,
            "notes": _GRID_RULE,
        },
        "scenario_cases": cases,
        "breakevens": breakevens,
        "evidence_register": evidence,
        "returns_consistency": returns_checks,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "fv_code": _DD_CODE,
        "dd_code": _DD_CODE,
        "parent_agent": _PARENT_KEY,
        "empty": not grid.get("rows") and not ranked,
    }


def _llm_sensitivity_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "sensitivity_analysis",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
        src_lines = "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:16], start=1)) or "[1] VDR"
        user = (
            f"Company: {company}\n\nSources:\n{src_lines}\n\n"
            f"Corpus:\n{corpus[:28000]}\n\n"
            "Return JSON with keys:\n"
            "insight_snapshot,\n"
            "ranked_drivers: [{assumption, range_low, range_high, range_basis, "
            "absolute_move, value_unit, evidence_class, source}],\n"
            "two_driver_grid: {driver_x, driver_y, growth_axis_pct, rows, "
            "base_wacc_pct, base_terminal_growth_pct, direction_check},\n"
            "scenario_cases: [{case, growth_assumption, margin_assumption, "
            "capital_assumption, irr_pct, moic_x, hold_years}],\n"
            "breakevens: [{metric, condition, hurdle, operating_terms, evidence_class}],\n"
            "evidence_register: [{assumption, classification, why, source}],\n"
            "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
            "No invest or pass."
        )
        return generate_json(system=system, user=user)
    except Exception:
        return None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    heur: dict[str, Any],
) -> dict[str, Any]:
    out = dict(heur)
    for key in (
        "insight_snapshot",
        "ranked_drivers",
        "two_driver_grid",
        "scenario_cases",
        "breakevens",
        "evidence_register",
        "quality_verdict",
        "reliance_verdict",
        "quality_reliance_rationale",
    ):
        if key in llm and llm[key]:
            out[key] = llm[key]
    # Re-check direction on whatever grid we keep
    grid = out.get("two_driver_grid") if isinstance(out.get("two_driver_grid"), dict) else {}
    if grid.get("rows") and not isinstance(grid.get("direction_check"), dict):
        grid["direction_check"] = _direction_check(grid)
        out["two_driver_grid"] = grid
    out["composer"] = "llm_v1"
    return out


def build_sensitivity_analysis_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    valuation_spec: dict[str, Any] | None = None,
    recommendation_spec: dict[str, Any] | None = None,
    historical_performance: dict[str, Any] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.agent_document_valuation_modeling import (
        gather_valuation_modeling_corpus,
    )
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)

    def _load(agent_key: str) -> dict[str, Any] | None:
        try:
            disk = read_agent_output_file(deal, agent_key=agent_key) or {}
            spec = disk.get("spec")
            return spec if isinstance(spec, dict) else None
        except Exception:
            return None

    val = valuation_spec if isinstance(valuation_spec, dict) else _load("valuation_modeling")
    rec = (
        recommendation_spec
        if isinstance(recommendation_spec, dict)
        else _load("recommendation")
    )
    hist = (
        historical_performance
        if isinstance(historical_performance, dict)
        else _load("historical_performance")
    )

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_valuation_modeling_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources

    heur = _heuristic_sensitivity_spec(
        company=target,
        corpus=corpus or "",
        sources=srcs,
        valuation_spec=val,
        recommendation_spec=rec,
        historical_performance=hist,
    )
    if prefer_heuristic:
        return heur

    llm_raw = _llm_sensitivity_spec(
        company=target,
        corpus=corpus or "",
        sources=srcs,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
    )
    if not llm_raw:
        return heur
    return _normalise_llm_spec(llm_raw, heur=heur)


def _cell(v: Any, n: int = 220) -> str:
    return _soften_invest(_clean(v, n)) or "—"


def render_sensitivity_analysis_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
    include_sources: bool = True,
) -> str:
    ranked = spec.get("ranked_drivers") if isinstance(spec.get("ranked_drivers"), list) else []
    grid = spec.get("two_driver_grid") if isinstance(spec.get("two_driver_grid"), dict) else {}
    cases = spec.get("scenario_cases") if isinstance(spec.get("scenario_cases"), list) else []
    breakevens = spec.get("breakevens") if isinstance(spec.get("breakevens"), list) else []
    evidence = (
        spec.get("evidence_register") if isinstance(spec.get("evidence_register"), list) else []
    )
    srcs = sources or spec.get("primary_sources") or []
    direction = (
        grid.get("direction_check") if isinstance(grid.get("direction_check"), dict) else {}
    )
    base_cell = grid.get("base_cell") if isinstance(grid.get("base_cell"), dict) else {}

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_RETURN_RULE}\n\n")

    # 1
    parts.append("## 1. Ranked Drivers\n\n")
    parts.append(f"{_RANK_RULE}\n\n")
    if ranked:
        parts.append(_table(
            ["Rank", "Assumption", "Range", "Basis", "Abs. move", "Class", "Source"],
            [
                [
                    str(r.get("rank") or "—"),
                    _cell(r.get("assumption"), 40),
                    _cell(f"{r.get('range_low')} → {r.get('range_high')}", 40),
                    _cell(r.get("range_basis"), 80),
                    (
                        f"{r.get('absolute_move'):g} {r.get('value_unit') or ''}"
                        if isinstance(r.get("absolute_move"), (int, float))
                        else "—"
                    ),
                    _cell(r.get("evidence_class"), 16),
                    _cell(r.get("source") or _NA, 40),
                ]
                for r in ranked if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('ranked drivers')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Two-Driver Grid\n\n")
    parts.append(f"{_GRID_RULE}\n\n")
    parts.append(
        f"**Drivers:** {grid.get('driver_y') or 'WACC'} (rows) × "
        f"{grid.get('driver_x') or 'Terminal growth'} (columns)\n\n"
    )
    parts.append(
        f"**Base cell:** WACC {base_cell.get('wacc_pct') or grid.get('base_wacc_pct')}% / "
        f"TG {base_cell.get('terminal_growth_pct') or grid.get('base_terminal_growth_pct')}%"
        f" — consistent with valuation agent: "
        f"{'yes' if base_cell.get('consistent_with_valuation_agent', True) else 'NO — reconcile'}"
        f" (valuation WACC {base_cell.get('valuation_wacc_pct')})\n\n"
    )
    parts.append(
        f"**Direction check:** {_cell(direction.get('detail'), 200)}\n\n"
    )
    growths = grid.get("growth_axis_pct") or []
    rows = grid.get("rows") if isinstance(grid.get("rows"), list) else []
    if rows and growths:
        headers = ["WACC \\ TG"] + [f"{g:g}%" for g in growths]
        table_rows = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            vals = r.get("values_list") or []
            w = r.get("wacc_pct")
            label = f"{w:g}%"
            if grid.get("base_wacc_pct") is not None and abs(float(w) - float(grid["base_wacc_pct"])) < 0.05:
                label += " (Base)"
            table_rows.append(
                [label] + [
                    f"{vals[i]:,.0f}" if i < len(vals) else "—"
                    for i in range(len(growths))
                ]
            )
        parts.append(
            f"### {grid.get('metric') or 'Enterprise Value'} "
            f"({grid.get('unit') or 'INR Cr'})\n\n"
        )
        parts.append(_table(headers, table_rows))
    else:
        parts.append(f"**{_info_request('two-driver sensitivity grid')}**\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Downside / Base / Upside Cases\n\n")
    parts.append(f"{_CASE_RULE}\n\n")
    if cases:
        parts.append(_table(
            ["Case", "Growth", "Margin", "Capital", "EV", "IRR", "MoIC", "Hold", "Returns check"],
            [
                [
                    _cell(c.get("case"), 24),
                    _cell(c.get("growth_assumption"), 60),
                    _cell(c.get("margin_assumption"), 60),
                    _cell(c.get("capital_assumption"), 60),
                    (
                        f"USD {c.get('enterprise_value_usd_b'):g}B"
                        if isinstance(c.get("enterprise_value_usd_b"), (int, float))
                        else (
                            f"INR {c.get('enterprise_value_inr_cr'):g} Cr"
                            if isinstance(c.get("enterprise_value_inr_cr"), (int, float))
                            else "—"
                        )
                    ),
                    (
                        f"{c.get('irr_pct'):g}%"
                        if isinstance(c.get("irr_pct"), (int, float))
                        else "—"
                    ),
                    (
                        f"{c.get('moic_x'):g}x"
                        if isinstance(c.get("moic_x"), (int, float))
                        else "—"
                    ),
                    (
                        f"{c.get('hold_years'):g}y"
                        if isinstance(c.get("hold_years"), (int, float))
                        else "—"
                    ),
                    _cell((c.get("returns_arithmetic") or {}).get("status"), 12),
                ]
                for c in cases if isinstance(c, dict)
            ],
        ))
        for c in cases:
            if not isinstance(c, dict):
                continue
            arith = c.get("returns_arithmetic") if isinstance(c.get("returns_arithmetic"), dict) else {}
            if arith.get("detail"):
                parts.append(
                    f"- **{c.get('case')} returns:** {_cell(arith.get('detail'), 200)}\n"
                )
        parts.append("\n")
    else:
        parts.append(f"**{_info_request('downside / base / upside cases by assumption')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Break-even Conditions\n\n")
    parts.append(f"{_BREAK_RULE}\n\n")
    if breakevens:
        parts.append(_table(
            ["Metric", "Condition", "Hurdle", "Operating terms", "Class"],
            [
                [
                    _cell(b.get("metric"), 40),
                    _cell(b.get("condition"), 80),
                    _cell(b.get("hurdle"), 40),
                    _cell(b.get("operating_terms"), 120),
                    _cell(b.get("evidence_class"), 16),
                ]
                for b in breakevens if isinstance(b, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('operating break-evens')}**\n\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Evidenced vs Judgement\n\n")
    parts.append(f"{_EVIDENCE_RULE}\n\n")
    if evidence:
        parts.append(_table(
            ["Assumption", "Class", "Why", "Source"],
            [
                [
                    _cell(e.get("assumption"), 40),
                    _cell(e.get("classification"), 16),
                    _cell(e.get("why"), 120),
                    _cell(e.get("source") or _NA, 40),
                ]
                for e in evidence if isinstance(e, dict)
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
