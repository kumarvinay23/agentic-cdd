"""Compose DiligenceIQ Cash Flow — EBITDA→cash bridge + liquidity (prompt book).

Reconciles opening→closing cash, bridges EBITDA to OCF and FCF, separates
maintenance vs growth capex, sizes working-capital movements, and assesses
liquidity / runway. Dual-writes legacy Cash Flow Profile fields
(cash_metrics / liquidity_notes).

No invest/pass. Missing cash data cannot prove distress.
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

_DOCUMENT_TITLE = "Cash Flow Profile"
_DD_CODE = "DD-24a"

_BRIDGE_RULE = (
    "Opening cash reconciles to closing cash; EBITDA bridges to operating cash "
    "flow and free cash flow with interest/tax treatment, non-cash items, "
    "working-capital movements, maintenance versus growth capex, financing and "
    "one-offs stated."
)
_DAYS_RULE = (
    "DSO, DPO and inventory days are calculated only with matching denominators "
    "and populations; otherwise they are omitted with a reason."
)
_LIQUIDITY_RULE = (
    "Liquidity, minimum cash and downside runway are assessed from evidenced "
    "balances and burn. Missing cash data cannot prove distress."
)

_OPEN_CASH_RE = re.compile(
    r"(?i)(?:opening|beginning)\s+cash"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_CLOSE_CASH_RE = re.compile(
    r"(?i)(?:closing|ending|cash\s+at\s+(?:bank|period\s+end)|period[- ]end\s+cash)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_OCF_RE = re.compile(
    r"(?i)(?:operating\s+cash\s+flow|cash\s+from\s+operations|CFO)\b"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_FCF_RE = re.compile(
    r"(?i)(?:free\s+cash\s+flow|FCF|UFCF|unlevered\s+free\s+cash\s+flow)\b"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_EBITDA_RE = re.compile(
    r"(?i)\bEBITDA\b[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*"
    r"\(?([-]?[\d,]+(?:\.\d+)?)\)?\s*(M|Cr|mn|m)?"
)
_CAPEX_RE = re.compile(
    r"(?i)(?:capex|capital\s+expenditure|ppe\s+additions)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_MAINT_CAPEX_RE = re.compile(
    r"(?i)(?:maintenance\s+capex|maint(?:enance)?\.?\s+capex)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_GROWTH_CAPEX_RE = re.compile(
    r"(?i)(?:growth\s+capex|expansion\s+capex)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_BURN_RE = re.compile(
    r"(?i)(?:monthly\s+(?:cash\s+)?burn|cash\s+burn(?:\s+rate)?)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn|m)?"
)
_RUNWAY_RE = re.compile(
    r"(?i)(?:liquidity\s+)?runway\s*(?:of|=|:)?\s*"
    r"(\d+(?:\.\d+)?)\s*[–-]?\s*(\d+(?:\.\d+)?)?\s*months?"
)
_DSO_RE = re.compile(r"(?i)\bDSO\b[^\d]{0,20}(\d+(?:\.\d+)?)\s*days?")
_DPO_RE = re.compile(r"(?i)\bDPO\b[^\d]{0,20}(\d+(?:\.\d+)?)\s*days?")
_DIO_RE = re.compile(
    r"(?i)\b(?:DIO|inventory\s+days|days\s+inventory)\b[^\d]{0,20}"
    r"(\d+(?:\.\d+)?)\s*days?"
)
_WC_DELTA_RE = re.compile(
    r"(?i)(?:change\s+in\s+working\s+capital|Δ\s*NWC|working\s+capital\s+(?:inflow|outflow|movement))"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹|GBP|£)?\s*\(?([-]?[\d,]+(?:\.\d+)?)\)?\s*(M|Cr|mn|m)?"
)
_ONE_OFF_RE = re.compile(
    r"(?i)\b(one[- ]off|non[- ]recurring|exceptional)\b.{0,80}?"
    r"(?:cash|capex|cost|item)",
    re.DOTALL,
)
_FINANCING_RE = re.compile(
    r"(?i)\b(debt\s+(?:draw|drawdown|repay|repayment)|equity\s+(?:inject|raise)|"
    r"financing\s+(?:inflow|outflow)|interest\s+paid|tax\s+paid)\b"
)


def _info_request(what: str) -> str:
    return f"Information request: {what}"


def _is_filled(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text != _NA and not text.startswith("Information request")


def _num(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    neg = text.startswith("(") and text.endswith(")")
    text = text.replace(",", "").replace("£", "").replace("$", "").replace("₹", "")
    text = re.sub(r"[^\d.\-]", "", text)
    if not text or text in {".", "-", "-."}:
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    return -abs(val) if neg else val


def _soften_invest(text: Any) -> str:
    raw = str(text or "")
    raw = re.sub(
        r"(?i)\b(recommend(?:ation)?\s+(?:to\s+)?(?:invest|pass)|invest\s*/\s*pass)\b",
        "diligence finding",
        raw,
    )
    raw = re.sub(r"(?i)\s*[—\-]\s*\b(invest|pass)\b\.?\s*$", "", raw)
    return _clean(raw, 600)


def _insight(text: Any, *, max_chars: int = 520) -> str:
    body = _soften_invest(_clean(text, max_chars))
    return f"**Insight Snapshot:** {body}\n\n" if body else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for i in range(len(headers)):
            val = row[i] if i < len(row) else "—"
            cells.append(str(val or "—").replace("|", "\\|").replace("\n", " ").strip())
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _unit_from_match(m: re.Match[str] | None, default: str = "") -> str:
    if not m or m.lastindex is None or m.lastindex < 2:
        return default
    u = (m.group(2) or "").strip()
    if not u:
        return default
    low = u.lower()
    if low in {"cr"}:
        return "INR Cr"
    if low in {"m", "mn"}:
        return "USD M"
    return u


def _amt(m: re.Match[str] | None) -> tuple[float | None, str]:
    if not m:
        return None, ""
    val = _num(m.group(1))
    return val, _unit_from_match(m)


def gather_cash_flow_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "financial": 0,
        "deal_strategy": 1,
        "operations": 2,
        "customer": 3,
        "company_management": 4,
    }
    needles = (
        "cash", "cf", "socf", "liquidity", "burn", "capex", "working capital",
        "dso", "dpo", "inventory", "bank", "treasury", "fcf", "ocf",
    )
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple[int, int, str]:
        name = str(d.get("filename") or "").lower()
        needle_hit = 0 if any(n in name for n in needles) else 1
        return (
            prefer.get(str(d.get("cdl_category") or ""), 9),
            needle_hit,
            str(d.get("filename") or ""),
        )

    ranked = sorted(docs, key=_rank)
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:12]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        loaded: dict[str, Any] = {}
        try:
            raw_loaded = load_library_document(deal, filename)
            if isinstance(raw_loaded, dict):
                loaded = raw_loaded
        except Exception:
            loaded = {}
        text = str(loaded.get("text") or doc.get("excerpt") or "")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:12_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 48_000:
            break
    return "\n\n".join(blobs), sources


def _legacy_metrics(legacy: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    raw = legacy.get("cash_metrics") if isinstance(legacy.get("cash_metrics"), dict) else {}
    for k, v in raw.items():
        num = _num(v)
        if num is not None:
            metrics[str(k)] = num
    return metrics


def _ebitda_from_prior(prior: dict[str, Any] | None) -> tuple[float | None, str]:
    if not isinstance(prior, dict):
        return None, ""
    # Prefer Historical Performance shared fact register / performance metrics.
    for row in prior.get("shared_fact_register") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("metric") or "").lower() != "ebitda":
            continue
        if str(row.get("period_type") or "") not in {"", "actual", "forecast"}:
            continue
        val = _num(row.get("value"))
        if val is not None:
            period = str(row.get("period") or "")
            return val, period
    perf = prior.get("performance_metrics") if isinstance(prior.get("performance_metrics"), dict) else {}
    for key in ("ebitda_fy2024", "ebitda_fy2025", "ebitda_fy2023"):
        if key in perf and isinstance(perf[key], (int, float)):
            return float(perf[key]), key.replace("ebitda_", "").upper()
    return None, ""


def _cash_period_bridge(
    *,
    corpus: str,
    sources: list[str],
    metrics: dict[str, float],
) -> list[dict[str, Any]]:
    src0 = sources[0] if sources else "data room"
    open_v, open_u = _amt(_OPEN_CASH_RE.search(corpus))
    close_v, close_u = _amt(_CLOSE_CASH_RE.search(corpus))
    ocf_v, ocf_u = _amt(_OCF_RE.search(corpus))
    fcf_v, fcf_u = _amt(_FCF_RE.search(corpus))
    if open_v is None and "liquidity_inr_cr" in metrics:
        # Legacy extract sometimes only has a single liquidity figure.
        close_v = close_v if close_v is not None else metrics.get("liquidity_inr_cr")
        open_u = open_u or "INR Cr"
        close_u = close_u or "INR Cr"

    unit = open_u or close_u or ocf_u or fcf_u or "as stated"
    lines: list[dict[str, Any]] = []
    if open_v is not None:
        lines.append({
            "label": "Opening cash",
            "value": open_v,
            "sign": 1,
            "unit": unit,
            "source": f"{src0} · opening cash",
            "notes": _BRIDGE_RULE,
        })
    if ocf_v is not None:
        lines.append({
            "label": "Operating cash flow",
            "value": ocf_v,
            "sign": 1,
            "unit": unit or ocf_u,
            "source": f"{src0} · OCF",
            "notes": _BRIDGE_RULE,
        })
        metrics.setdefault("operating_cash_flow", ocf_v)
    if fcf_v is not None:
        metrics.setdefault("free_cash_flow", fcf_v)
    if close_v is not None:
        lines.append({
            "label": "Closing cash",
            "value": close_v,
            "sign": 1,
            "unit": unit or close_u,
            "source": f"{src0} · closing cash",
            "notes": _BRIDGE_RULE,
        })
        metrics.setdefault("closing_cash", close_v)
    return lines


def _ebitda_to_fcf_bridge(
    *,
    corpus: str,
    sources: list[str],
    metrics: dict[str, float],
    ebitda: float | None,
    ebitda_period: str,
) -> list[dict[str, Any]]:
    src0 = sources[0] if sources else "data room"
    ocf_v, _ = _amt(_OCF_RE.search(corpus))
    fcf_v, _ = _amt(_FCF_RE.search(corpus))
    capex_v, _ = _amt(_CAPEX_RE.search(corpus))
    maint_v, _ = _amt(_MAINT_CAPEX_RE.search(corpus))
    growth_v, _ = _amt(_GROWTH_CAPEX_RE.search(corpus))
    wc_v, _ = _amt(_WC_DELTA_RE.search(corpus))
    if capex_v is None and "capex_fy2024_inr_cr" in metrics:
        capex_v = metrics["capex_fy2024_inr_cr"]
    if fcf_v is None and "ufcf_fy2025_inr_cr" in metrics:
        fcf_v = metrics["ufcf_fy2025_inr_cr"]
    if ocf_v is None and "operating_cash_flow" in metrics:
        ocf_v = metrics["operating_cash_flow"]

    lines: list[dict[str, Any]] = []
    if ebitda is not None:
        lines.append({
            "label": f"EBITDA ({ebitda_period or 'period'})",
            "value": ebitda,
            "sign": 1,
            "unit": "as stated",
            "source": "historical_performance / accounts",
            "notes": "Starting point for cash conversion",
            "formula": "as stated",
        })
        metrics.setdefault("ebitda", ebitda)
    if wc_v is not None:
        # Convention: positive WC investment is cash outflow → sign -1 when labelled outflow
        sign = -1 if re.search(r"(?i)outflow|increase|investment", corpus[max(0, corpus.lower().find('working capital')-20):][:80] or "") else 1
        lines.append({
            "label": "Working capital movement",
            "value": abs(wc_v),
            "sign": sign if wc_v >= 0 else -1,
            "unit": "as stated",
            "source": f"{src0} · WC movement",
            "notes": _BRIDGE_RULE,
            "formula": "ΔNWC as stated in cash flow statement",
        })
        metrics.setdefault("wc_movement", wc_v)
    if maint_v is not None or growth_v is not None:
        if maint_v is not None:
            lines.append({
                "label": "Maintenance capex",
                "value": maint_v,
                "sign": -1,
                "unit": "as stated",
                "source": f"{src0} · maint capex",
                "notes": "Maintenance vs growth separated",
                "formula": "maintenance_capex (cash)",
            })
            metrics.setdefault("maintenance_capex", maint_v)
        if growth_v is not None:
            lines.append({
                "label": "Growth capex",
                "value": growth_v,
                "sign": -1,
                "unit": "as stated",
                "source": f"{src0} · growth capex",
                "notes": "Maintenance vs growth separated",
                "formula": "growth_capex (cash)",
            })
            metrics.setdefault("growth_capex", growth_v)
    elif capex_v is not None:
        lines.append({
            "label": "Capex (undifferentiated)",
            "value": capex_v,
            "sign": -1,
            "unit": "as stated",
            "source": f"{src0} · capex",
            "notes": _info_request("maintenance vs growth split"),
            "formula": "total_capex (cash)",
        })
        metrics.setdefault("capex", capex_v)

    if ocf_v is not None:
        lines.append({
            "label": "Operating cash flow",
            "value": ocf_v,
            "sign": 1,
            "unit": "as stated",
            "source": f"{src0} · OCF",
            "notes": _BRIDGE_RULE,
            "formula": "EBITDA ± non-cash ± ΔNWC − tax/interest (as defined)",
        })
    if fcf_v is not None:
        lines.append({
            "label": "Free cash flow",
            "value": fcf_v,
            "sign": 1,
            "unit": "as stated",
            "source": f"{src0} · FCF",
            "notes": _BRIDGE_RULE,
            "formula": "OCF − capex (treatment stated)",
        })

    # Conversion when both EBITDA and OCF exist and EBITDA ≠ 0
    if ebitda not in (None, 0) and ocf_v is not None:
        conv = (ocf_v / abs(ebitda)) * 100
        metrics["cash_conversion_pct"] = round(conv, 1)
        lines.append({
            "label": "Cash conversion (OCF / |EBITDA|)",
            "value": round(conv, 1),
            "sign": 1,
            "unit": "%",
            "source": _COMPUTED,
            "notes": "Explain near-zero/negative conversion when relevant",
            "formula": f"({ocf_v:g}/abs({ebitda:g}))*100",
        })
    return lines


def _capex_split(corpus: str, metrics: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    maint_v, _ = _amt(_MAINT_CAPEX_RE.search(corpus))
    growth_v, _ = _amt(_GROWTH_CAPEX_RE.search(corpus))
    total_v, _ = _amt(_CAPEX_RE.search(corpus))
    if total_v is None and "capex_fy2024_inr_cr" in metrics:
        total_v = metrics["capex_fy2024_inr_cr"]
    if maint_v is not None:
        rows.append({
            "category": "maintenance",
            "value": maint_v,
            "source": _DOC_CITE,
            "notes": "Maintenance capex evidenced",
        })
    if growth_v is not None:
        rows.append({
            "category": "growth",
            "value": growth_v,
            "source": _DOC_CITE,
            "notes": "Growth capex evidenced",
        })
    if not rows and total_v is not None:
        rows.append({
            "category": "undifferentiated",
            "value": total_v,
            "source": _DOC_CITE,
            "notes": _info_request("maintenance vs growth capex split"),
        })
    if not rows:
        rows.append({
            "category": "missing",
            "value": None,
            "source": _NA,
            "notes": _info_request("capex ledger with maint vs growth"),
        })
    return rows


def _wc_days(corpus: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, pattern, denom in (
        ("DSO", _DSO_RE, "revenue / AR population must match"),
        ("DPO", _DPO_RE, "purchases or COGS / AP population must match"),
        ("Inventory days", _DIO_RE, "COGS or purchases / inventory population must match"),
    ):
        m = pattern.search(corpus)
        if m:
            rows.append({
                "metric": label,
                "value_days": float(m.group(1)),
                "denominator": denom,
                "source": _DOC_CITE,
                "notes": _DAYS_RULE,
            })
        else:
            rows.append({
                "metric": label,
                "value_days": None,
                "denominator": denom,
                "source": _NA,
                "notes": _info_request(f"{label} with matching denominator"),
            })
    return rows


def _financing_and_one_offs(corpus: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for m in _FINANCING_RE.finditer(corpus):
        start = max(0, m.start() - 20)
        end = min(len(corpus), m.end() + 80)
        snippet = _clean(corpus[start:end], 160)
        rows.append({
            "item": _clean(m.group(0), 40),
            "kind": "financing",
            "evidence": snippet,
            "source": _DOC_CITE,
        })
        if len(rows) >= 4:
            break
    for m in _ONE_OFF_RE.finditer(corpus):
        rows.append({
            "item": _clean(m.group(0), 80),
            "kind": "one_off",
            "evidence": _clean(m.group(0), 120),
            "source": _DOC_CITE,
        })
        if len(rows) >= 6:
            break
    if not rows:
        rows.append({
            "item": _info_request("financing cash flows and one-off cash items"),
            "kind": "missing",
            "evidence": _NA,
            "source": _NA,
        })
    return rows


def _liquidity_assessment(
    *,
    corpus: str,
    metrics: dict[str, float],
) -> dict[str, Any]:
    burn_v, _ = _amt(_BURN_RE.search(corpus))
    if burn_v is None and "monthly_burn_inr_cr" in metrics:
        burn_v = metrics["monthly_burn_inr_cr"]
    cash_v = metrics.get("closing_cash") or metrics.get("liquidity_inr_cr")
    if cash_v is None:
        cash_v, _ = _amt(_CLOSE_CASH_RE.search(corpus))

    runway_m = _RUNWAY_RE.search(corpus)
    runway_stated: str | None = None
    if runway_m:
        lo = runway_m.group(1)
        hi = runway_m.group(2)
        runway_stated = f"{lo}–{hi} months" if hi else f"{lo} months"

    runway_computed: float | None = None
    runway_formula = ""
    if cash_v is not None and burn_v not in (None, 0):
        runway_computed = round(float(cash_v) / abs(float(burn_v)), 1)
        runway_formula = f"{cash_v:g}/abs({burn_v:g})"
        metrics["runway_months_computed"] = runway_computed
    if burn_v is not None:
        metrics["monthly_burn"] = burn_v
    if cash_v is not None:
        metrics.setdefault("closing_cash", cash_v)

    pressure = "unavailable"
    if cash_v is not None and burn_v is not None:
        if runway_computed is not None and runway_computed < 6:
            pressure = "verified_tight"
        elif runway_computed is not None:
            pressure = "verified_adequate"
        else:
            pressure = "verified_with_limits"
    elif cash_v is None and burn_v is None:
        pressure = "unavailable"

    notes: list[str] = []
    if cash_v is not None:
        notes.append(f"Closing / available cash ~{cash_v:g} {_DOC_CITE}.")
    if burn_v is not None:
        notes.append(f"Monthly cash burn ~{burn_v:g} {_DOC_CITE}.")
    if runway_stated:
        notes.append(f"Stated runway: {runway_stated} {_DOC_CITE}.")
    if runway_computed is not None:
        notes.append(
            f"Computed runway ~{runway_computed:g} months "
            f"(formula {runway_formula}) {_COMPUTED}."
        )
    if pressure == "unavailable":
        notes.append(
            "Liquidity pressure not established — cash/burn inputs unavailable "
            "(missing ≠ distress)."
        )
    notes.append(_LIQUIDITY_RULE)

    return {
        "closing_cash": cash_v,
        "monthly_burn": burn_v,
        "runway_stated": runway_stated or _info_request("stated liquidity runway"),
        "runway_months_computed": runway_computed,
        "runway_formula": runway_formula or _info_request("cash and monthly burn for runway"),
        "minimum_cash": _info_request("operating minimum cash"),
        "pressure": pressure,
        "notes": notes[:8],
    }


def _recalc_bridges(
    cash_bridge: list[dict[str, Any]],
    ebitda_bridge: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from agetic_cdd_api.prompt_book import recalculate_bridge

    checks: list[dict[str, Any]] = []
    if len(cash_bridge) >= 2:
        result = recalculate_bridge(cash_bridge)
        checks.append({
            "bridge": "opening_to_closing_cash",
            "ok": result.get("ok"),
            "stated_total": result.get("stated_total"),
            "computed_total": result.get("computed_total"),
            "residual": result.get("residual"),
            "error": result.get("error"),
        })
    # EBITDA→FCF is not a simple additive last-line total when OCF/FCF are
    # intermediate reported lines — only recalc when we have a clear closing FCF
    # and additive components without duplicate OCF/FCF totals.
    additive = [
        r for r in ebitda_bridge
        if isinstance(r, dict)
        and str(r.get("label") or "").lower() not in {
            "operating cash flow",
            "cash conversion (ocf / |ebitda|)",
        }
        and r.get("value") is not None
    ]
    if len(additive) >= 2 and any(
        "free cash flow" in str(r.get("label") or "").lower() for r in additive
    ):
        result = recalculate_bridge(additive)
        checks.append({
            "bridge": "ebitda_to_fcf",
            "ok": result.get("ok"),
            "stated_total": result.get("stated_total"),
            "computed_total": result.get("computed_total"),
            "residual": result.get("residual"),
            "error": result.get("error"),
        })
    return checks


def _quality_reliance(
    *,
    cash_bridge: list[dict],
    ebitda_bridge: list[dict],
    liquidity: dict[str, Any],
    recalc: list[dict],
) -> tuple[str, str, str]:
    has_open_close = any(
        "opening" in str(r.get("label") or "").lower() for r in cash_bridge
    ) and any(
        "closing" in str(r.get("label") or "").lower() for r in cash_bridge
    )
    has_ebitda = any(
        "ebitda" in str(r.get("label") or "").lower() for r in ebitda_bridge
    )
    has_ocf = any(
        "operating cash" in str(r.get("label") or "").lower() for r in ebitda_bridge
    )
    failed_recalc = [c for c in recalc if c.get("ok") is False]
    pressure = str(liquidity.get("pressure") or "unavailable")

    if has_ebitda and has_ocf and has_open_close and not failed_recalc:
        quality, reliance = "PASS", "READY"
    elif has_ebitda or has_ocf or has_open_close:
        quality, reliance = "PASS", "LIMITED"
    else:
        quality, reliance = "REWORK", "BLOCKED"

    if failed_recalc:
        quality = "REWORK"
        if reliance == "READY":
            reliance = "LIMITED"

    bits = [
        f"Cash bridge {'present' if has_open_close else 'incomplete'}; "
        f"EBITDA→cash {'present' if has_ebitda and has_ocf else 'incomplete'}.",
    ]
    if failed_recalc:
        bits.append(f"{len(failed_recalc)} bridge recalculation difference(s).")
    if pressure == "unavailable":
        bits.append("Liquidity pressure unavailable (missing ≠ distress).")
    elif pressure == "verified_tight":
        bits.append("Verified tight runway from cash/burn.")
    return quality, reliance, " ".join(bits)


def _questions_from_cf_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    cash_bridge = spec.get("cash_bridge") if isinstance(spec.get("cash_bridge"), list) else []
    ebitda_bridge = (
        spec.get("ebitda_to_cash_bridge")
        if isinstance(spec.get("ebitda_to_cash_bridge"), list)
        else []
    )
    has_open = any("opening" in str(r.get("label") or "").lower() for r in cash_bridge)
    has_close = any("closing" in str(r.get("label") or "").lower() for r in cash_bridge)
    if not (has_open and has_close):
        out.append(
            normalize_question(
                {
                    "question": "Provide monthly (or period) opening→closing cash reconciliation",
                    "required_records": "Bank reconciliation / treasury cash pack / SoCF",
                    "decision_effect": "Liquidity and FCF reliance for Valuation",
                    "priority": "mandatory_pre_decision",
                    "owner": "CFO",
                    "timing": "before IC",
                    "closure_test": "Opening + movements = closing within materiality",
                    "interim_treatment": "Liquidity conclusions BLOCKED",
                }
            )
        )

    has_ebitda = any("ebitda" in str(r.get("label") or "").lower() for r in ebitda_bridge)
    has_ocf = any("operating cash" in str(r.get("label") or "").lower() for r in ebitda_bridge)
    if not (has_ebitda and has_ocf):
        out.append(
            normalize_question(
                {
                    "question": "Provide EBITDA→OCF→FCF bridge with interest/tax and WC treatment defined",
                    "required_records": "Cash flow statement + WC roll-forward",
                    "decision_effect": "Cash conversion drives valuation and financing need",
                    "priority": "mandatory_pre_decision",
                    "owner": "CFO",
                    "timing": "before IC",
                    "closure_test": "Bridge recalculates; levered vs unlevered labelled",
                    "interim_treatment": "Do not use conversion ratios in READY reliance",
                }
            )
        )

    capex = spec.get("capex_split") if isinstance(spec.get("capex_split"), list) else []
    if not capex or any(
        isinstance(r, dict)
        and str(r.get("category") or "") in {"missing", "undifferentiated"}
        for r in capex
    ):
        out.append(
            normalize_question(
                {
                    "question": "Split capex into maintenance vs growth with ledger support",
                    "required_records": "Capex ledger / fixed-asset additions schedule",
                    "decision_effect": "Affects FCF and maintenance burden",
                    "priority": "signing_condition",
                    "owner": "CFO / ops",
                    "timing": "per deal timetable",
                    "closure_test": "Maint + growth = total capex for each period",
                    "interim_treatment": "Treat total capex as undifferentiated",
                }
            )
        )

    liq = spec.get("liquidity") if isinstance(spec.get("liquidity"), dict) else {}
    if str(liq.get("pressure") or "") == "unavailable":
        out.append(
            normalize_question(
                {
                    "question": "Provide closing cash, monthly burn and minimum cash for runway",
                    "required_records": "Treasury pack + 13-week cash forecast",
                    "decision_effect": "Downside funding need / structure conditions",
                    "priority": "mandatory_pre_decision",
                    "owner": "CFO",
                    "timing": "before IC",
                    "closure_test": "Runway = cash / |burn| with stated minimum cash",
                    "interim_treatment": "Do not infer distress from missing cash data",
                }
            )
        )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for q in out:
        key = q.get("question", "").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
    if not unique:
        # Framework: Questions section must exist; state explicitly when complete.
        unique.append(
            normalize_question(
                {
                    "question": "No material cash-flow inputs are missing for the evidenced periods",
                    "required_records": "N/A — current pack sufficient for stated bridges",
                    "decision_effect": "None — cash bridge publishable as shared basis",
                    "priority": "residual_uncertainty",
                    "owner": "CFO",
                    "timing": "n/a",
                    "closure_test": "Re-run if new periods or perimeter change",
                    "interim_treatment": "None",
                }
            )
        )
    return unique[:12]


def _heuristic_cash_flow_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    legacy_spec: dict[str, Any] | None = None,
    prior_historical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    metrics = _legacy_metrics(legacy)
    ebitda, ebitda_period = _ebitda_from_prior(prior_historical)
    if ebitda is None:
        m = _EBITDA_RE.search(corpus)
        if m:
            ebitda = _num(m.group(1))
            ebitda_period = "corpus"

    cash_bridge = _cash_period_bridge(corpus=corpus, sources=sources, metrics=metrics)
    ebitda_bridge = _ebitda_to_fcf_bridge(
        corpus=corpus,
        sources=sources,
        metrics=metrics,
        ebitda=ebitda,
        ebitda_period=ebitda_period,
    )
    capex_split = _capex_split(corpus, metrics)
    wc_days = _wc_days(corpus)
    financing = _financing_and_one_offs(corpus)
    liquidity = _liquidity_assessment(corpus=corpus, metrics=metrics)
    recalc = _recalc_bridges(cash_bridge, ebitda_bridge)
    quality, reliance, rationale = _quality_reliance(
        cash_bridge=cash_bridge,
        ebitda_bridge=ebitda_bridge,
        liquidity=liquidity,
        recalc=recalc,
    )

    conv = metrics.get("cash_conversion_pct")
    lead_bits = [f"Cash Flow for {company}"]
    if conv is not None:
        lead_bits.append(f"cash conversion {conv:g}%")
    if liquidity.get("runway_months_computed") is not None:
        lead_bits.append(f"runway ~{liquidity['runway_months_computed']:g} months")
    elif str(liquidity.get("pressure")) == "unavailable":
        lead_bits.append("liquidity inputs incomplete (missing ≠ distress)")

    notes = list(liquidity.get("notes") or [])
    for n in (legacy.get("liquidity_notes") or []):
        if isinstance(n, str) and n.strip() and n not in notes:
            notes.append(n.strip())

    out: dict[str, Any] = {
        "insight_snapshot": _soften_invest("; ".join(lead_bits)),
        "cash_bridge": cash_bridge,
        "ebitda_to_cash_bridge": ebitda_bridge,
        "capex_split": capex_split,
        "wc_days": wc_days,
        "financing_and_one_offs": financing,
        "liquidity": liquidity,
        "bridge_recalculations": recalc,
        "cash_metrics": metrics,
        "liquidity_notes": notes[:8],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": not cash_bridge and not ebitda_bridge and not metrics,
    }
    out["questions"] = _questions_from_cf_gaps(out)
    return out


def _llm_cash_flow_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "cash_flow",
            sector=sector,
            geography=geography,
            materiality=materiality,
            target_company=company,
            deal_perimeter=deal_perimeter,
            transaction_type=transaction_type,
            as_of_date=as_of_date,
            review_periods=review_periods,
            decision_stage=decision_stage,
        )
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "cash_bridge: [{label, value, sign, unit, source, notes}],\n"
        "ebitda_to_cash_bridge: [{label, value, sign, unit, source, notes, formula}],\n"
        "capex_split: [{category, value, source, notes}],\n"
        "wc_days: [{metric, value_days, denominator, source, notes}],\n"
        "financing_and_one_offs: [{item, kind, evidence, source}],\n"
        "liquidity: {closing_cash, monthly_burn, runway_stated, "
        "runway_months_computed, runway_formula, minimum_cash, pressure, notes},\n"
        "cash_metrics: {string: number},\n"
        "liquidity_notes: [string],\n"
        "questions: [{question, required_records, decision_effect, priority, "
        "owner, timing, closure_test, interim_treatment}],\n"
        "quality_verdict: PASS|REWORK,\n"
        "reliance_verdict: READY|LIMITED|BLOCKED,\n"
        "quality_reliance_rationale: string.\n"
        "Missing cash data cannot prove distress. No invest or pass."
    )
    try:
        parsed = generate_json(system=system, user=user, temperature=0.1)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    company: str,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str,
    prior_historical: dict[str, Any] | None,
) -> dict[str, Any]:
    heur = _heuristic_cash_flow_spec(
        company=company,
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy_spec,
        prior_historical=prior_historical,
    )
    for key in (
        "cash_bridge",
        "ebitda_to_cash_bridge",
        "capex_split",
        "wc_days",
        "financing_and_one_offs",
    ):
        raw = llm.get(key) if isinstance(llm.get(key), list) else []
        cleaned = [r for r in raw if isinstance(r, dict)]
        llm[key] = cleaned or heur.get(key) or []

    liq = llm.get("liquidity") if isinstance(llm.get("liquidity"), dict) else {}
    llm["liquidity"] = {**heur.get("liquidity", {}), **liq} if liq else heur.get("liquidity")

    metrics = llm.get("cash_metrics") if isinstance(llm.get("cash_metrics"), dict) else {}
    merged_metrics = dict(heur.get("cash_metrics") or {})
    for k, v in metrics.items():
        num = _num(v)
        if num is not None:
            merged_metrics[str(k)] = num
    llm["cash_metrics"] = merged_metrics

    notes = llm.get("liquidity_notes") if isinstance(llm.get("liquidity_notes"), list) else []
    notes = [_soften_invest(_clean(n, 220)) for n in notes if isinstance(n, str) and n.strip()]
    llm["liquidity_notes"] = (notes or heur.get("liquidity_notes") or [])[:8]

    llm["bridge_recalculations"] = _recalc_bridges(
        llm["cash_bridge"], llm["ebitda_to_cash_bridge"]
    )
    quality, reliance, rationale = _quality_reliance(
        cash_bridge=llm["cash_bridge"],
        ebitda_bridge=llm["ebitda_to_cash_bridge"],
        liquidity=llm["liquidity"] if isinstance(llm.get("liquidity"), dict) else {},
        recalc=llm["bridge_recalculations"],
    )
    from agetic_cdd_api.prompt_book import normalize_verdicts

    qv, rv = normalize_verdicts(
        quality=llm.get("quality_verdict") or quality,
        reliance=llm.get("reliance_verdict") or reliance,
        default_quality=quality,
        default_reliance=reliance,
    )
    llm["quality_verdict"] = qv
    llm["reliance_verdict"] = rv
    llm["quality_reliance_rationale"] = (
        _soften_invest(_clean(llm.get("quality_reliance_rationale"), 460))
        if str(llm.get("quality_reliance_rationale") or "").strip()
        else rationale
    )
    for dead in ("recommendation", "confidence", "investment_verdict", "verdict"):
        llm.pop(dead, None)

    snap = _soften_invest(llm.get("insight_snapshot") or "")
    llm["insight_snapshot"] = snap or heur.get("insight_snapshot")
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = (legacy_spec or {}).get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = (legacy_spec or {}).get("dd_code") or _DD_CODE
    llm["empty"] = not llm["cash_bridge"] and not llm["ebitda_to_cash_bridge"] and not llm["cash_metrics"]

    if not llm.get("questions"):
        llm["questions"] = _questions_from_cf_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled: list[dict[str, str]] = []
        for raw in llm.get("questions") or []:
            if not isinstance(raw, dict):
                continue
            q = normalize_question(raw)
            if not q.get("closure_test"):
                q["closure_test"] = "Cash bridge ties to balances within materiality"
            filled.append(q)
        llm["questions"] = filled or _questions_from_cf_gaps(llm)
    return llm


def build_cash_flow_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    prior_historical: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)

    if corpus is None:
        gathered_corpus, gathered_sources = gather_cash_flow_corpus(deal, idx)
        corpus = gathered_corpus
        if not sources:
            sources = gathered_sources
    sources = list(sources or [])
    if not corpus:
        bits: list[str] = []
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                name = str(doc.get("filename") or "source")
                if name not in sources:
                    sources.append(name)
        corpus = "\n".join(bits)

    if not prefer_heuristic:
        llm = _llm_cash_flow_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=vars_.get("geography"),
            materiality=vars_.get("materiality"),
            deal_perimeter=vars_.get("deal_perimeter"),
            transaction_type=vars_.get("transaction_type"),
            as_of_date=vars_.get("as_of_date"),
            review_periods=vars_.get("review_periods"),
            decision_stage=vars_.get("decision_stage"),
        )
        if llm:
            spec = _normalise_llm_spec(
                llm,
                company=target,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
                prior_historical=prior_historical,
            )
            spec["deal_slots"] = {k: v for k, v in vars_.items() if v}
            return spec

    spec = _heuristic_cash_flow_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy_spec,
        prior_historical=prior_historical,
    )
    spec["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return spec


def render_cash_flow_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    cash_bridge = spec.get("cash_bridge") if isinstance(spec.get("cash_bridge"), list) else []
    ebitda_bridge = (
        spec.get("ebitda_to_cash_bridge")
        if isinstance(spec.get("ebitda_to_cash_bridge"), list)
        else []
    )
    capex = spec.get("capex_split") if isinstance(spec.get("capex_split"), list) else []
    wc_days = spec.get("wc_days") if isinstance(spec.get("wc_days"), list) else []
    financing = (
        spec.get("financing_and_one_offs")
        if isinstance(spec.get("financing_and_one_offs"), list)
        else []
    )
    liquidity = spec.get("liquidity") if isinstance(spec.get("liquidity"), dict) else {}
    recalc = (
        spec.get("bridge_recalculations")
        if isinstance(spec.get("bridge_recalculations"), list)
        else []
    )
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Opening → Closing Cash\n\n")
    parts.append(f"{_BRIDGE_RULE}\n\n")
    if cash_bridge:
        parts.append(_table(
            ["Line", "Value", "Sign", "Unit", "Source"],
            [
                [
                    _clean(r.get("label"), 40),
                    (
                        f"{float(r['value']):g}"
                        if isinstance(r.get("value"), (int, float))
                        else _clean(r.get("value"), 20)
                    ),
                    str(r.get("sign") or 1),
                    _clean(r.get("unit"), 12),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in cash_bridge if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('monthly opening→closing cash bridge')}**\n\n")
    parts.append("---\n\n")

    parts.append("## 2. EBITDA → OCF → FCF\n\n")
    parts.append(f"{_BRIDGE_RULE}\n\n")
    if ebitda_bridge:
        parts.append(_table(
            ["Line", "Value", "Sign", "Unit", "Formula", "Source"],
            [
                [
                    _clean(r.get("label"), 40),
                    (
                        f"{float(r['value']):g}"
                        if isinstance(r.get("value"), (int, float))
                        else _clean(r.get("value"), 20)
                    ),
                    str(r.get("sign") or 1),
                    _clean(r.get("unit"), 12),
                    _clean(r.get("formula"), 48),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in ebitda_bridge if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('EBITDA to OCF/FCF bridge')}**\n\n")
    if recalc:
        parts.append("### Bridge recalculation\n\n")
        parts.append(_table(
            ["Bridge", "OK", "Stated", "Computed", "Residual", "Error"],
            [
                [
                    _clean(r.get("bridge"), 40),
                    str(r.get("ok")),
                    _clean(r.get("stated_total"), 20),
                    _clean(r.get("computed_total"), 20),
                    _clean(r.get("residual"), 20),
                    _clean(r.get("error"), 40),
                ]
                for r in recalc if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 3. Capex Split & Working-Capital Days\n\n")
    parts.append(f"{_DAYS_RULE}\n\n")
    if capex:
        parts.append("### Capex\n\n")
        parts.append(_table(
            ["Category", "Value", "Source", "Notes"],
            [
                [
                    _clean(r.get("category"), 24),
                    (
                        f"{float(r['value']):g}"
                        if isinstance(r.get("value"), (int, float))
                        else "—"
                    ),
                    _clean(r.get("source") or _NA, 40),
                    _clean(r.get("notes"), 80),
                ]
                for r in capex if isinstance(r, dict)
            ],
        ))
    if wc_days:
        parts.append("### WC days\n\n")
        parts.append(_table(
            ["Metric", "Days", "Denominator rule", "Source"],
            [
                [
                    _clean(r.get("metric"), 24),
                    (
                        f"{float(r['value_days']):g}"
                        if isinstance(r.get("value_days"), (int, float))
                        else "—"
                    ),
                    _clean(r.get("denominator"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in wc_days if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 4. Financing & One-offs\n\n")
    if financing:
        parts.append(_table(
            ["Item", "Kind", "Evidence", "Source"],
            [
                [
                    _clean(r.get("item"), 60),
                    _clean(r.get("kind"), 16),
                    _clean(r.get("evidence"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in financing if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('financing and one-off cash items')}**\n\n")
    parts.append("---\n\n")

    parts.append("## 5. Liquidity & Runway\n\n")
    parts.append(f"{_LIQUIDITY_RULE}\n\n")
    parts.append(_table(
        ["Measure", "Value"],
        [
            ["Closing cash", _clean(liquidity.get("closing_cash"), 40)],
            ["Monthly burn", _clean(liquidity.get("monthly_burn"), 40)],
            ["Runway (stated)", _clean(liquidity.get("runway_stated"), 40)],
            [
                "Runway (computed months)",
                _clean(liquidity.get("runway_months_computed"), 40),
            ],
            ["Runway formula", _clean(liquidity.get("runway_formula"), 60)],
            ["Minimum cash", _clean(liquidity.get("minimum_cash"), 60)],
            ["Pressure assessment", _clean(liquidity.get("pressure"), 40)],
        ],
    ))
    for note in (liquidity.get("notes") or [])[:6]:
        if isinstance(note, str) and note.strip():
            parts.append(f"- {_clean(note, 240)}\n")
    parts.append("\n---\n\n")

    if questions:
        parts.append("## 6. Questions and Inputs Required\n\n")
        parts.append(_table(
            [
                "Priority",
                "Question",
                "Decision Effect",
                "Required Records",
                "Owner",
                "Closure Test",
                "Interim",
            ],
            [
                [
                    _clean(r.get("priority"), 36),
                    _clean(r.get("question"), 100),
                    _clean(r.get("decision_effect"), 70),
                    _clean(r.get("required_records"), 70),
                    _clean(r.get("owner"), 36),
                    _clean(r.get("closure_test"), 70),
                    _clean(r.get("interim_treatment"), 70),
                ]
                for r in questions[:12] if isinstance(r, dict)
            ],
        ))
        parts.append("---\n\n")

    parts.append("## 7. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'REWORK', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'BLOCKED', 20)} — "
        f"can diligence rest on this cash bridge?\n\n"
    )
    if spec.get("quality_reliance_rationale"):
        parts.append(f"**Rationale:** {_soften_invest(spec.get('quality_reliance_rationale'))}\n\n")
    parts.append(
        "*This document publishes the cash and liquidity facts. It does not "
        "recommend invest or pass. Missing cash data cannot prove distress.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    for i, src in enumerate(srcs[:40], start=1):
        if isinstance(src, str) and src.strip():
            parts.append(f"**[{i}]** {src.strip()}\n")
    parts.append("\n")
    return "".join(parts)
