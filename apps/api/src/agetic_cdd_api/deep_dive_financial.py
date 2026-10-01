"""Slice 5 heuristic extractors for Financial Analysis Deep Dive agents (no LLM)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from agetic_cdd_api.deep_dive_extractors import (
    _hits,
    _is_noisy_sentence,
    _sentences,
)

FINANCIAL_SLUGS: frozenset[str] = frozenset(
    {
        "historical_performance",
        "revenue_quality",
        "cash_flow",
        "capital_structure",
    }
)

_PNL_ITEMS = (
    "Revenue|Cost of Goods Sold|Gross Profit|Gross Margin\\s*\\(%\\)|"
    "R&D Expenses|Sales & Marketing|G&A Expenses|EBITDA|EBITDA Margin\\s*\\(%\\)|"
    "Depreciation & Amortisation|EBIT|Finance Costs|Net Loss\\s*\\(PAT\\)"
)
_PNL_LINE_RE = re.compile(
    rf"(?i)({_PNL_ITEMS})\s+(.+?)(?=\s+(?:{_PNL_ITEMS})\s|\Z)"
)

_GRR_RE = re.compile(r"(?i)Gross Revenue Retention\s*\(GRR\)\s+(\d+(?:\.\d+)?)%")
_NRR_RE = re.compile(r"(?i)Net Revenue Retention\s*\(NRR\)\s+(\d+(?:\.\d+)?)%")
_LOGO_CHURN_RE = re.compile(r"(?i)Logo Churn\s*\(%\)\s+(\d+(?:\.\d+)?)%")
_REV_CHURN_RE = re.compile(r"(?i)Revenue Churn\s*\(%\)\s+(\d+(?:\.\d+)?)%")
_FLEET_REV_RE = re.compile(r"(?i)Fleet segment\s*\((\d+(?:\.\d+)?)%\s+of revenue\)")
_EMI_PCT_RE = re.compile(r"(?i)(~)?(\d+(?:\.\d+)?)%\s+of customers purchase via EMI")

_BURN_RE = re.compile(
    r"(?i)Cash Burn Rate\s*\(Monthly INR Cr\)\s+~?(\d+(?:\.\d+)?)"
)
_LIQUIDITY_RE = re.compile(
    r"(?i)Minimum Liquidity.*?Currently\s+~?INR\s+([\d,]+)\s+Crore"
)
_CAPEX_SPEND_RE = re.compile(
    r"(?i)FY2024 spend:\s+~?INR\s+([\d,]+)\s+Crore"
)
_UFCF_ROW_RE = re.compile(
    r"(?i)Unlevered Free Cash Flow\s*\(UFCF\)\s+"
    r"\(?[-\d,]+\)?\s+\(?[-\d,]+\)?\s+\(?[-\d,]+\)?\s+\(?[-\d,]+\)?\s+\(?[-\d,]+\)?\s+"
    r"\(?(\d+(?:\.\d+)?)\)?"
)
_UFCF_SIMPLE_RE = re.compile(
    r"(?i)Unlevered Free Cash Flow\s*\(UFCF\)\s+((?:\(?[-\d,]+\)?\s*){5})"
)

_TOTAL_DEBT_RE = re.compile(r"(?i)TOTAL DEBT\s+USD\s+(\d+(?:\.\d+)?)\s*M")
_DEBT_INSTRUMENT_RE = re.compile(
    r"(?i)(Senior Term Loan A|Senior Term Loan B|Mezzanine Notes|"
    r"Working Capital Revolver|Equipment Finance Lease|Debentures\s*\(Listed NCDs\))"
    r"\s+USD\s+(\d+(?:\.\d+)?)\s*M"
)
_RATIO_ROW_RE = re.compile(
    r"(?i)(Net Debt / Revenue|Interest Coverage\s*\(EBIT / Interest\)|"
    r"Debt / Equity Ratio|Current Ratio|Cash Burn Rate\s*\(Monthly INR Cr\))"
    r".{0,40}?([\d.]+\s*x|N/M|-\d+(?:\.\d+)?x|~?\d+(?:\.\d+)?)"
)

_WACC_RE = re.compile(
    r"(?i)WACC\s*\(Base(?: Case)?\)\s+~?(\d+(?:\.\d+)?)%"
)
_DCF_EQUITY_SHARE_RE = re.compile(
    r"(?i)Implied Share Price\s*\(DCF Base\)\s+INR\s+([\d.]+)"
)
_DCF_EQUITY_VALUE_RE = re.compile(
    r"(?i)Equity Value\s*\(DCF\)\s+([\d,]+)"
)
_HEALTH_RATING_RE = re.compile(
    r"(?i)Financing Health Rating:\s*([\d.]+)\s*/\s*5"
)
_DCF_EV_RE = re.compile(
    r"(?i)Enterprise Value\s*\(DCF\)\s+([\d,]+)"
)

_HIST_NEEDLES = (
    "revenue", "ebitda", "gross margin", "profit", "p&l", "historical", "loss",
)
_REV_QUALITY_NEEDLES = (
    "retention", "churn", "nrr", "grr", "recurring", "ltv", "cac", "revenue quality",
)
_CASH_NEEDLES = (
    "cash burn", "liquidity", "capex", "working capital", "free cash flow", "runway",
)
_CAPITAL_NEEDLES = (
    "debt", "equity", "wacc", "covenant", "refinancing", "leverage", "valuation", "dcf",
)
_BAD_FIN = (
    "porter", "market share", "nps score", "competitive rivalry", "threat of",
)


class PnlLine(BaseModel):
    line_item: str
    fy2024_value: float | None = None
    fy2023_value: float | None = None
    unit: str = "USD M"


class DebtInstrument(BaseModel):
    name: str
    amount_usd_m: float | None = None


class HistoricalPerformanceSpec(BaseModel):
    """DD-23 — Adjusted EBITDA Bridge."""

    document: str = "Adjusted EBITDA Bridge"
    dd_code: str = "DD-23"
    pl_lines: list[PnlLine] = Field(default_factory=list)
    performance_metrics: dict[str, float] = Field(default_factory=dict)
    bridge_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class RevenueQualitySpec(BaseModel):
    """DD-09b — Revenue Persistence Analysis."""

    document: str = "Revenue Persistence Analysis"
    dd_code: str = "DD-09b"
    retention_metrics: dict[str, float] = Field(default_factory=dict)
    revenue_mix: dict[str, float] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class CashFlowSpec(BaseModel):
    """DD-24a — Cash Flow Profile."""

    document: str = "Cash Flow Profile"
    dd_code: str = "DD-24a"
    cash_metrics: dict[str, float] = Field(default_factory=dict)
    liquidity_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class CapitalStructureSpec(BaseModel):
    """DD-24 — Intrinsic Value Statement (NPV)."""

    document: str = "Intrinsic Value Statement (NPV)"
    dd_code: str = "DD-24"
    debt_total_usd_m: float | None = None
    debt_instruments: list[DebtInstrument] = Field(default_factory=list)
    leverage_ratios: dict[str, float | str] = Field(default_factory=dict)
    dcf_metrics: dict[str, float] = Field(default_factory=dict)
    capital_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


def _clean(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "").strip()


def _dedupe(lines: list[str], *, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        cleaned = re.sub(r"\s+", " ", _clean(line)).strip()
        key = cleaned.lower()
        if len(cleaned) < 20 or key in seen:
            continue
        if any(bad in key for bad in _BAD_FIN):
            continue
        seen.add(key)
        out.append(cleaned[:280])
        if len(out) >= limit:
            break
    return out


def _format_number(val: Any) -> str:
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int | float):
        return f"{val:g}"
    return str(val)


def _parse_pnl_values(raw: str) -> list[float | None]:
    tokens = re.findall(r"N/M|\(?[-\d,.]+%?\)?", raw or "", flags=re.I)
    out: list[float | None] = []
    for token in tokens:
        if token.upper() == "N/M":
            out.append(None)
            continue
        neg = token.startswith("(") and token.endswith(")")
        num = re.sub(r"[^\d.]", "", token.replace("%", ""))
        if not num:
            continue
        val = float(num)
        if neg:
            val = -val
        out.append(val)
    return out


def _parse_pnl_table(text: str) -> list[PnlLine]:
    from agetic_cdd_api.services_accounts_extract import (
        detect_unit_from_corpus,
        is_cim_crosswalk_context,
        looks_like_cim_page_list,
    )

    rows: list[PnlLine] = []
    seen: set[str] = set()
    unit_default, _ = detect_unit_from_corpus(text or "")
    for match in _PNL_LINE_RE.finditer(text or ""):
        item = re.sub(r"\s+", " ", match.group(1)).strip()
        key = item.lower()
        if key in seen:
            continue
        if is_cim_crosswalk_context(text or "", match.start()):
            continue
        values = _parse_pnl_values(match.group(2))
        if looks_like_cim_page_list(values):
            continue
        seen.add(key)
        fy2024 = values[3] if len(values) > 3 else None
        fy2023 = values[2] if len(values) > 2 else None
        # Drop year-as-value artefacts
        if isinstance(fy2023, float) and 2000 <= fy2023 <= 2100 and float(fy2023).is_integer():
            fy2023 = None
        if isinstance(fy2024, float) and 2000 <= fy2024 <= 2100 and float(fy2024).is_integer():
            fy2024 = None
        unit = "%" if "margin" in key else unit_default
        rows.append(
            PnlLine(
                line_item=item,
                fy2024_value=fy2024,
                fy2023_value=fy2023,
                unit=unit,
            )
        )
        if len(rows) >= 10:
            break
    return rows


def _parse_debt_instruments(text: str) -> list[DebtInstrument]:
    rows: list[DebtInstrument] = []
    for match in _DEBT_INSTRUMENT_RE.finditer(text or ""):
        rows.append(
            DebtInstrument(
                name=re.sub(r"\s+", " ", match.group(1)).strip(),
                amount_usd_m=float(match.group(2)),
            )
        )
        if len(rows) >= 8:
            break
    return rows


def _parse_leverage_ratios(text: str) -> dict[str, float | str]:
    ratios: dict[str, float | str] = {}
    for match in _RATIO_ROW_RE.finditer(text or ""):
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        raw = match.group(2).strip()
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if raw.upper().startswith("N/M"):
            ratios[key] = "N/M"
            continue
        num = re.sub(r"[^\d.-]", "", raw)
        if num:
            try:
                ratios[key] = float(num)
            except ValueError:
                ratios[key] = raw
    return ratios


def _parse_ufcf_fy2025(text: str) -> float | None:
    block = _UFCF_SIMPLE_RE.search(text or "")
    if block:
        values = _parse_pnl_values(block.group(1))
        if len(values) >= 5 and values[0] is not None:
            return values[0]
    match = _UFCF_ROW_RE.search(text or "")
    if match:
        return -float(match.group(1)) if "(" in (match.group(0) or "") else float(match.group(1))
    return None


def _extract_historical_performance(text: str, sentences: list[str]) -> HistoricalPerformanceSpec:
    pl_lines = _parse_pnl_table(text)
    metrics: dict[str, float] = {}
    for row in pl_lines:
        key = re.sub(r"[^a-z0-9]+", "_", row.line_item.lower()).strip("_")
        unit = (row.unit or "").lower()
        if row.fy2024_value is not None and row.unit != "%":
            if "inr" in unit:
                metrics[f"{key}_fy2024_inr_cr"] = row.fy2024_value
            elif "usd" in unit:
                metrics[f"{key}_fy2024_usd_m"] = row.fy2024_value
            else:
                metrics[f"{key}_fy2024"] = row.fy2024_value
        if row.fy2024_value is not None and row.unit == "%":
            metrics[f"{key}_fy2024_pct"] = row.fy2024_value

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _HIST_NEEDLES, limit=6), limit=4)
    rev = next((r for r in pl_lines if r.line_item.lower().startswith("revenue")), None)
    ebitda = next((r for r in pl_lines if r.line_item.lower() == "ebitda"), None)
    unit_label = (rev.unit if rev else None) or (ebitda.unit if ebitda else None) or "USD M"
    if rev and rev.fy2024_value is not None and rev.fy2023_value is not None:
        growth = ((rev.fy2024_value - rev.fy2023_value) / abs(rev.fy2023_value)) * 100
        notes = _dedupe(
            [f"Revenue FY2024 {unit_label} {rev.fy2024_value:g} (~{growth:+.0f}% YoY).", *notes],
            limit=4,
        )
    if ebitda and ebitda.fy2024_value is not None:
        notes = _dedupe(
            [f"EBITDA FY2024 {unit_label} {ebitda.fy2024_value:g}.", *notes],
            limit=4,
        )

    model = HistoricalPerformanceSpec(
        pl_lines=pl_lines,
        performance_metrics=metrics,
        bridge_notes=notes,
    )
    model.empty = not any([model.pl_lines, model.performance_metrics, model.bridge_notes])
    return model


def _extract_revenue_quality(
    text: str,
    sentences: list[str],
    prior_spec: dict | None,
) -> RevenueQualitySpec:
    metrics: dict[str, float] = {}
    for regex, key in (
        (_GRR_RE, "grr_pct"),
        (_NRR_RE, "nrr_pct"),
        (_LOGO_CHURN_RE, "logo_churn_pct"),
        (_REV_CHURN_RE, "revenue_churn_pct"),
    ):
        match = regex.search(text or "")
        if match:
            metrics[key] = float(match.group(1))

    mix: dict[str, float] = {}
    fleet = _FLEET_REV_RE.search(text or "")
    if fleet:
        mix["fleet_revenue_pct"] = float(fleet.group(1))
    emi = _EMI_PCT_RE.search(text or "")
    if emi:
        mix["emi_customer_pct"] = float(emi.group(2))

    if prior_spec:
        buying = prior_spec.get("buying_metrics") if isinstance(prior_spec.get("buying_metrics"), dict) else {}
        if not buying:
            buying = prior_spec
        for src_key, dst_key in (
            ("online_sales_pct", "online_sales_pct"),
            ("fleet_revenue_pct", "fleet_revenue_pct"),
        ):
            if dst_key not in mix and buying.get(src_key) is not None:
                mix[dst_key] = float(buying[src_key])

    flags: list[str] = []
    if metrics.get("nrr_pct") is not None and metrics["nrr_pct"] < 90:
        flags.append(f"NRR {metrics['nrr_pct']:g}% below 90% durability threshold.")
    if metrics.get("logo_churn_pct") is not None and metrics["logo_churn_pct"] > 30:
        flags.append(f"Logo churn {metrics['logo_churn_pct']:g}% elevated vs typical SaaS/consumer benchmarks.")
    if metrics.get("grr_pct") is not None and metrics.get("nrr_pct") is not None:
        expansion = metrics["nrr_pct"] - metrics["grr_pct"]
        flags.append(f"Expansion uplift (NRR-GRR) ~{expansion:g} pp.")

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe([*flags, *_hits(clean, _REV_QUALITY_NEEDLES, limit=6)], limit=5)
    preferred = [
        s
        for s in clean
        if re.search(
            r"(?i)retention warning|revenue quality|logo churn|nrr|grr|recurring",
            s,
        )
    ]
    notes = _dedupe([*notes, *preferred], limit=5)

    model = RevenueQualitySpec(
        retention_metrics=metrics,
        revenue_mix=mix,
        quality_flags=_dedupe(flags, limit=4),
        quality_notes=notes,
    )
    model.empty = not any([model.retention_metrics, model.revenue_mix, model.quality_flags, model.quality_notes])
    return model


def _extract_cash_flow(
    text: str,
    sentences: list[str],
    prior_spec: dict | None,
) -> CashFlowSpec:
    metrics: dict[str, float] = {}
    burn = _BURN_RE.search(text or "")
    if burn:
        metrics["monthly_burn_inr_cr"] = float(burn.group(1))
    liq = _LIQUIDITY_RE.search(text or "")
    if liq:
        metrics["liquidity_inr_cr"] = float(liq.group(1).replace(",", ""))
    capex = _CAPEX_SPEND_RE.search(text or "")
    if capex:
        metrics["capex_fy2024_inr_cr"] = float(capex.group(1).replace(",", ""))
    ufcf = _parse_ufcf_fy2025(text)
    if ufcf is not None:
        metrics["ufcf_fy2025_inr_cr"] = ufcf

    if prior_spec:
        hist = prior_spec.get("performance_metrics") if isinstance(prior_spec, dict) else {}
        if isinstance(hist, dict):
            rev = hist.get("revenue_fy2024_inr_cr")
            if rev is not None:
                metrics["revenue_fy2024_inr_cr"] = float(rev)
        if prior_spec.get("logistics_metrics") and isinstance(prior_spec["logistics_metrics"], dict):
            dio = prior_spec["logistics_metrics"].get("dio_days")
            if dio is not None:
                metrics["dio_days"] = float(dio)

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _CASH_NEEDLES, limit=6), limit=4)
    preferred: list[str] = []
    if metrics.get("monthly_burn_inr_cr") is not None:
        preferred.append(
            f"Monthly cash burn ~INR {metrics['monthly_burn_inr_cr']:g} Cr (above sub-50 target)."
        )
    if metrics.get("liquidity_inr_cr") is not None:
        preferred.append(f"Reported liquidity ~INR {metrics['liquidity_inr_cr']:g} Cr.")
    runway = re.search(
        r"(?i)(\d+\s*[–-]\s*\d+)\s+month\s+liquidity\s+runway",
        text or "",
    )
    if runway:
        preferred.append(f"Liquidity runway: {runway.group(1)} months.")
    notes = _dedupe([*preferred, *notes], limit=5)

    model = CashFlowSpec(cash_metrics=metrics, liquidity_notes=notes)
    model.empty = not any([model.cash_metrics, model.liquidity_notes])
    return model


def _extract_capital_structure(text: str, sentences: list[str]) -> CapitalStructureSpec:
    debt_total = _TOTAL_DEBT_RE.search(text or "")
    instruments = _parse_debt_instruments(text)
    ratios = _parse_leverage_ratios(text)

    dcf: dict[str, float] = {}
    wacc = _WACC_RE.search(text or "")
    if wacc:
        dcf["wacc_pct"] = float(wacc.group(1))
    share = _DCF_EQUITY_SHARE_RE.search(text or "")
    if share:
        dcf["implied_share_price_inr"] = float(share.group(1))
    ev = _DCF_EV_RE.search(text or "")
    if ev:
        dcf["enterprise_value_inr_cr"] = float(ev.group(1).replace(",", ""))
    eq = _DCF_EQUITY_VALUE_RE.search(text or "")
    if eq:
        dcf["equity_value_inr_cr"] = float(eq.group(1).replace(",", ""))
    rating = _HEALTH_RATING_RE.search(text or "")
    health = float(rating.group(1)) if rating else None

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _CAPITAL_NEEDLES, limit=6), limit=4)
    if debt_total:
        notes = _dedupe(
            [f"Total debt USD {debt_total.group(1)}M.", *notes],
            limit=4,
        )
    if health is not None:
        notes = _dedupe([f"Financing health rating {health:g} / 5.", *notes], limit=4)
    if dcf.get("implied_share_price_inr") is not None:
        notes = _dedupe(
            [
                f"DCF base implied share price INR {dcf['implied_share_price_inr']:g}.",
                *notes,
            ],
            limit=4,
        )
    refinance = re.search(r"(?i)Refinancing risk:\s*(Medium|High|Low)", text or "")
    if refinance:
        notes = _dedupe([f"Refinancing risk: {refinance.group(1).title()}.", *notes], limit=4)

    model = CapitalStructureSpec(
        debt_total_usd_m=float(debt_total.group(1)) if debt_total else None,
        debt_instruments=instruments,
        leverage_ratios=ratios,
        dcf_metrics=dcf,
        capital_notes=notes,
    )
    model.empty = not any(
        [
            model.debt_total_usd_m,
            model.debt_instruments,
            model.leverage_ratios,
            model.dcf_metrics,
            model.capital_notes,
        ]
    )
    return model


def extract_financial_spec(
    slug: str,
    text: str,
    *,
    sources: list[str] | None = None,
    coverage: str = "missing",
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    """Return typed Financial Analysis spec JSON. Heuristic only."""
    clipped = (text or "")[:50_000]
    sentences = _sentences(clipped)
    src = list(sources or [])

    if slug == "historical_performance":
        model = _extract_historical_performance(clipped, sentences)
    elif slug == "revenue_quality":
        model = _extract_revenue_quality(clipped, sentences, prior_spec)
    elif slug == "cash_flow":
        model = _extract_cash_flow(clipped, sentences, prior_spec)
    elif slug == "capital_structure":
        model = _extract_capital_structure(clipped, sentences)
    else:
        return {"slug": slug, "empty": True, "extractor": "none", "track": "F"}

    if coverage == "missing" and not clipped.strip():
        model.empty = True

    payload = model.model_dump(mode="json")
    payload["slug"] = slug
    payload["track"] = "F"
    payload["sources"] = src
    payload["coverage"] = coverage
    payload["extractor"] = "heuristic_v1"
    payload["metrics"] = _financial_metrics(slug, payload)
    return payload


def _financial_metrics(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "historical_performance":
        return {
            "pl_line_count": len(payload.get("pl_lines") or []),
            "metric_count": len(payload.get("performance_metrics") or {}),
        }
    if slug == "revenue_quality":
        return {
            "retention_metric_count": len(payload.get("retention_metrics") or {}),
            "flag_count": len(payload.get("quality_flags") or []),
        }
    if slug == "cash_flow":
        return {"metric_count": len(payload.get("cash_metrics") or {})}
    if slug == "capital_structure":
        return {
            "debt_instrument_count": len(payload.get("debt_instruments") or []),
            "ratio_count": len(payload.get("leverage_ratios") or {}),
            "dcf_metric_count": len(payload.get("dcf_metrics") or {}),
        }
    return {}


def findings_from_financial_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if slug == "historical_performance":
        for row in spec.get("pl_lines") or []:
            if not isinstance(row, dict):
                continue
            if row.get("fy2024_value") is None:
                continue
            unit = row.get("unit") or "INR Cr"
            suffix = "%" if unit == "%" else f" {unit}"
            out.append(f"{row.get('line_item')}: {_format_number(row['fy2024_value'])}{suffix}")
        metrics = spec.get("performance_metrics") or {}
        if isinstance(metrics, dict):
            for key, val in list(metrics.items())[:3]:
                out.append(f"{key}: {_format_number(val)}")
        out.extend(spec.get("bridge_notes") or [])
    elif slug == "revenue_quality":
        metrics = spec.get("retention_metrics") or {}
        if isinstance(metrics, dict):
            for key, val in metrics.items():
                out.append(f"{key}: {_format_number(val)}")
        mix = spec.get("revenue_mix") or {}
        if isinstance(mix, dict):
            for key, val in list(mix.items())[:3]:
                out.append(f"{key}: {_format_number(val)}")
        out.extend(spec.get("quality_flags") or [])
        out.extend(spec.get("quality_notes") or [])
    elif slug == "cash_flow":
        metrics = spec.get("cash_metrics") or {}
        if isinstance(metrics, dict):
            for key, val in list(metrics.items())[:6]:
                out.append(f"{key}: {_format_number(val)}")
        out.extend(spec.get("liquidity_notes") or [])
    elif slug == "capital_structure":
        if spec.get("debt_total_usd_m") is not None:
            out.append(f"total_debt_usd_m: {_format_number(spec['debt_total_usd_m'])}")
        for row in spec.get("debt_instruments") or []:
            if isinstance(row, dict) and row.get("name"):
                bit = row["name"]
                if row.get("amount_usd_m") is not None:
                    bit += f" — USD {row['amount_usd_m']:g}M"
                out.append(bit)
        ratios = spec.get("leverage_ratios") or {}
        if isinstance(ratios, dict):
            for key, val in list(ratios.items())[:4]:
                out.append(f"{key}: {_format_number(val)}")
        dcf = spec.get("dcf_metrics") or {}
        if isinstance(dcf, dict):
            for key, val in list(dcf.items())[:4]:
                out.append(f"{key}: {_format_number(val)}")
        out.extend(spec.get("capital_notes") or [])

    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())
    return deduped
