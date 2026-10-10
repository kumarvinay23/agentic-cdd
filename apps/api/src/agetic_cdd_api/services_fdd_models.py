"""FDD Phase 5b — specialist models M1 / M2 / M3 / M7 / M8 / M5 / M6 (+ QoE for M4).

Builds section-mapped exhibits from the databook fact table so commentary and
assembly can stop holding back trading, margin, costs, cash conversion, QoE,
BS, NWC and debt.

Formulas (Appendix B lite):
- M1 Historical trading: multi-year IS lines + YoY / margin calcs (SEC-B)
- M2 Revenue & margin: mix/margin walk from M1 inputs — GM/EM levels + Δpp (SEC-C)
- M3 Costs and people: COGS / SG&A / labour + cost ratios vs revenue (SEC-D)
- M7 Cash conversion: OCF, capex, FCF = OCF − |capex|; conversion = OCF÷EBITDA (SEC-I)
- M8 Balance sheet: material BS lines as reported
- M5 NWC: (AR + inventory + other WC assets) − (AP + deferred + other WC liab.)
- M6 Net debt: gross interest-bearing debt (+ debt-like) − freely available cash;
  lease liabilities disclosed beside, not folded into headline net debt
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Iterable

from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CellStatus,
    EvidenceTier,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FddFact,
    FigureType,
    RunStage,
)
from agetic_cdd_api.services_fdd_exhibit import (
    load_or_empty,
    persist_store,
)
from agetic_cdd_api.services_fdd_store import (
    load_fact_table,
    load_manifest,
    load_qoe_workbook,
    load_scope_profile,
    save_manifest,
)
from agetic_cdd_api.services_fdd_tokens import metric_cell_id

logger = logging.getLogger(__name__)

MODELS_VERSION = "0.5.8"

TRADING_EXHIBIT_ID = "ex_m1_trading"
MARGIN_EXHIBIT_ID = "ex_m2_margin"
COSTS_EXHIBIT_ID = "ex_m3_costs"
CASH_CONV_EXHIBIT_ID = "ex_m7_cash"
BS_EXHIBIT_ID = "ex_m8_bs"
NWC_EXHIBIT_ID = "ex_m5_nwc"
NET_DEBT_EXHIBIT_ID = "ex_m6_net_debt"

# How many closed fiscal years to keep on the M1 trading workbook.
_TRADING_MAX_YEARS = 3

# Lower = worse (for aggregating bucket status).
_STATUS_PRIORITY: dict[CellStatus, int] = {
    CellStatus.MISSING: 0,
    CellStatus.DRAFT: 1,
    CellStatus.DOUBTFUL: 2,
    CellStatus.PROVEN: 3,
}

# Metric-key / label token buckets (underscore-normalised matching).
_CASH = frozenset(
    {
        "cash",
        "cash_and_cash_equivalents",
        "cash_and_equivalents",
        "cash_equivalents",
        "bank",
        "bank_balance",
        "bank_accounts",
        "total_bank_accounts",
        "checking",
        "checking_account",
        "undeposited_funds",
        "freely_available_cash",
        "unrestricted_cash",
    }
)
_RESTRICTED_CASH = frozenset(
    {"restricted_cash", "escrow_cash", "trapped_cash", "minimum_cash"}
)
# Printed interest-bearing facilities (sum these — do NOT also add LT-liability totals).
_LOAN_FACILITIES = frozenset(
    {
        "term_loan",
        "term_loans",
        "sba_loan",
        "sba_loans",
        "ppp_loan",
        "revolver",
        "revolving_credit",
        "bank_debt",
        "notes_payable",
        "notes_payable_long_term",
        "bonds",
        "senior_debt",
        "mezzanine",
        "borrowings",
    }
)
# Printed gross-debt totals (exclusive — prefer over summing facilities when present).
_GROSS_DEBT_PRINTED = frozenset(
    {
        "gross_debt",
        "total_debt",
        "interest_bearing_debt",
        "debt",
    }
)
# LT liability totals — fallback only when no facilities / printed gross debt.
_LT_LIABILITY_TOTALS = frozenset(
    {
        "long_term_liabilities",
        "long_term_debt",
        "non_current_liabilities",
    }
)
# Legacy union kept for BS line inclusion / matching helpers.
_GROSS_DEBT = _LOAN_FACILITIES | _GROSS_DEBT_PRINTED | _LT_LIABILITY_TOTALS | frozenset(
    {"loans", "loan", "facility"}
)
_DEBT_LIKE = frozenset(
    {
        "debt_like",
        "debt_like_items",
        "deferred_consideration",
        "earn_out",
        "earnout",
        "vendor_loan",
        "shareholder_loan",
        "preferred_equity_debt_like",
    }
)
_LEASE = frozenset(
    {
        "lease",
        "leases",
        "lease_liability",
        "lease_liabilities",
        "ifrs16",
        "right_of_use_liability",
        "rou_liability",
    }
)
_AR = frozenset(
    {
        "ar",
        "accounts_receivable",
        "trade_receivables",
        "trade_receivable",
        "receivables",
        "debtors",
    }
)
_AP = frozenset(
    {
        "ap",
        "accounts_payable",
        "trade_payables",
        "trade_payable",
        "payables",
        "creditors",
    }
)
_INVENTORY = frozenset({"inventory", "inventories", "stock", "stock_on_hand"})
_OTHER_WC_ASSET = frozenset(
    {
        "other_current_assets",
        "prepaid",
        "prepayments",
        "prepaid_expenses",
        "accrued_income",
    }
)
_OTHER_WC_LIAB = frozenset(
    {
        "other_current_liabilities",
        "accruals",
        "accrued_expenses",
        "deferred_revenue",
        "deferred_income",
        "contract_liabilities",
        "customer_deposits",
    }
)
# Fallback when AP / other WC liabilities are absent (monthly BS often prints this total).
_CURRENT_LIABILITIES = frozenset(
    {
        "current_liabilities",
        "total_current_liabilities",
        "short_term_liabilities",
    }
)
_BS_LINES = frozenset(
    {
        "total_assets",
        "total_liabilities",
        "total_equity",
        "equity",
        "net_assets",
        "nav",
        "net_asset_value",
        "current_assets",
        "current_liabilities",
        "non_current_assets",
        "non_current_liabilities",
        "long_term_liabilities",
        "long_term_debt",
        "ppe",
        "property_plant_equipment",
        "fixed_assets",
        "intangibles",
        "goodwill",
    }
)

# M1 income-statement / trading metric buckets (canonical output keys).
_REVENUE = frozenset(
    {"revenue", "net_revenue", "sales", "turnover", "total_revenue"}
)
_GROSS_PROFIT = frozenset({"gross_profit", "gross_income"})
_GROSS_MARGIN = frozenset({"gross_margin", "gross_margin_pct", "gm"})
_EBITDA = frozenset({"ebitda"})  # reported only — adjusted lives on QoE
_EBITDA_MARGIN = frozenset({"ebitda_margin", "ebitda_margin_pct"})
_OP_PROFIT = frozenset(
    {"operating_profit", "ebit", "operating_income", "operating_earnings"}
)
_NET_INCOME = frozenset(
    {
        "net_income",
        "net_profit",
        "profit_after_tax",
        "pat",
        "profit_for_the_year",
        "profit_for_year",
    }
)
# Ordered (bucket, canonical_metric_key, label) for reported IS lines.
_TRADING_REPORTED: tuple[tuple[frozenset[str], str, str], ...] = (
    (_REVENUE, "revenue", "Revenue"),
    (_GROSS_PROFIT, "gross_profit", "Gross profit"),
    (_GROSS_MARGIN, "gross_margin", "Gross margin %"),
    (_EBITDA, "ebitda", "EBITDA"),
    (_EBITDA_MARGIN, "ebitda_margin", "EBITDA margin %"),
    (_OP_PROFIT, "operating_profit", "Operating profit"),
    (_NET_INCOME, "net_income", "Net income"),
)

# M7 cash-flow / conversion buckets.
_OCF = frozenset(
    {
        "operating_cash_flow",
        "cash_from_operations",
        "cash_from_operating_activities",
        "net_cash_from_operating_activities",
        "net_cash_provided_by_operating_activities",
        "net_cash_used_in_operating_activities",
        "cash_generated_from_operations",
        "cash_provided_by_operating_activities",
        "cfo",
        "ocf",
    }
)
_CAPEX = frozenset(
    {
        "capex",
        "capital_expenditure",
        "capital_expenditures",
        "purchase_of_ppe",
        "purchases_of_ppe",
        "purchases_of_property_and_equipment",
        "purchases_of_property_plant_and_equipment",
        "additions_to_ppe",
        "ppe_additions",
        "investing_capex",
    }
)
_COGS = frozenset(
    {
        "cogs",
        "cost_of_goods_sold",
        "cost_of_sales",
        "cost_of_revenue",
        "direct_costs",
        "cost_of_operations",
        "total_cost_of_operations",
    }
)
_SGA = frozenset(
    {
        "sga",
        "sg_and_a",
        "selling_general_administrative",
        "opex",
        "operating_expenses",
        "operating_costs",
        "total_operating_expenses",
        "total_operating_costs",
        "overhead",
    }
)
_LABOR = frozenset(
    {
        "labor_cost",
        "labour_cost",
        "total_labor",
        "total_labour",
        "personnel_cost",
        "personnel_costs",
        "wages",
        "salaries",
        "salaries_and_wages",
        "wages_and_salaries",
        "payroll",
        "payroll_expenses",
        "staff_costs",
        "employee_costs",
    }
)
_HEADCOUNT = frozenset(
    {
        "headcount",
        "employees",
        "fte",
        "ftes",
        "average_fte",
        "average_headcount",
        "period_end_headcount",
    }
)
# Optional concentration / mix keys when present in the fact table.
_MIX_CONCENTRATION = frozenset(
    {
        "top_customer_pct",
        "top_10_customers_pct",
        "customer_concentration",
        "largest_customer_share",
        "revenue_concentration",
    }
)


def _norm(key: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (key or "").lower()).strip("_")


def _closed_year_cutoff() -> int:
    return date.today().year - 1


def _fmt(value: float | None) -> str:
    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    return format_fdd_number(value)


def _matches(norm_key: str, bucket: frozenset[str]) -> bool:
    """Exact key or multi-token subset match — never raw substring ``in``.

    Single-token aliases (``ar``, ``bank``, ``loan``) only match the full key
    so short tokens cannot hitch onto unrelated compounds (``bank_charge``,
    ``market``, ``warranty_reserve``). Multi-token aliases match when every
    token appears as a whole part of the key.
    """
    if not norm_key:
        return False
    if norm_key in bucket:
        return True
    parts = set(p for p in norm_key.split("_") if p)
    if not parts:
        return False
    for b in bucket:
        b_parts = set(p for p in b.split("_") if p)
        # Require ≥2 tokens so bare aliases stay exact-only
        if len(b_parts) >= 2 and b_parts.issubset(parts):
            return True
    return False


def _worst_status(statuses: Iterable[CellStatus]) -> CellStatus:
    items = list(statuses)
    if not items:
        return CellStatus.DRAFT
    return min(items, key=lambda s: _STATUS_PRIORITY.get(s, 0))


def _model_component_fact_id(model: str, component: str, year: int) -> str:
    """Stable fact_id for calculated M5/M6 component cells (always synthetic)."""
    return f"{model.lower()}:component:{_norm(component)}:{int(year)}"


class _Line:
    __slots__ = (
        "metric_key",
        "fiscal_year",
        "value",
        "fact_id",
        "currency",
        "scale",
        "status",
        "label",
        "sources",
    )

    def __init__(
        self,
        *,
        metric_key: str,
        fiscal_year: int,
        value: float,
        fact_id: str,
        currency: str | None,
        scale: str | None,
        status: CellStatus,
        label: str | None = None,
        sources: list[str] | None = None,
    ) -> None:
        self.metric_key = metric_key
        self.fiscal_year = fiscal_year
        self.value = float(value)
        self.fact_id = fact_id
        self.currency = currency
        self.scale = scale
        self.status = status
        self.label = label or metric_key.replace("_", " ").title()
        self.sources = list(sources or [])


def _source_pref(ln: _Line) -> int:
    """Prefer investor workbook over ledger/management when values tie."""
    from agetic_cdd_api.services_fdd_sources import classify_source

    if not ln.sources:
        return -1  # empty-source peers lose to any named source
    kind = classify_source(ln.sources, ln.label, ln.fact_id)
    if kind == "workbook":
        return 2
    if kind == "ledger":
        return 1
    if kind == "management":
        return 1
    return 0


def _lines_from_facts(facts: Iterable[FddFact]) -> list[_Line]:
    out: list[_Line] = []
    for f in facts:
        if f.value is None:
            continue
        src = list(f.sources or [])
        if f.labels and f.labels.source:
            src.append(f.labels.source)
        out.append(
            _Line(
                metric_key=f.metric_key,
                fiscal_year=int(f.fiscal_year),
                value=float(f.value),
                fact_id=f.fact_id,
                currency=f.currency,
                scale=f.scale,
                status=f.status,
                label=(f.labels.line if f.labels else None) or f.metric_key,
                sources=src,
            )
        )
        # Expand alternatives so workbook>ledger collapse still works when the
        # fact primary was not yet re-based at bridge time.
        for alt in f.alternatives or []:
            if not isinstance(alt, dict):
                continue
            try:
                alt_v = float(alt["value"]) if alt.get("value") is not None else None
            except (TypeError, ValueError):
                alt_v = None
            if alt_v is None:
                continue
            asrc = [str(s) for s in (alt.get("sources") or []) if str(s).strip()]
            if not asrc:
                # Empty-source peers cannot participate in same-basis alignment.
                continue
            out.append(
                _Line(
                    metric_key=f.metric_key,
                    fiscal_year=int(f.fiscal_year),
                    value=float(alt_v),
                    fact_id=f"{f.fact_id}:alt",
                    currency=f.currency,
                    scale=f.scale,
                    status=f.status,
                    label=(f.labels.line if f.labels else None) or f.metric_key,
                    sources=asrc,
                )
            )
    return out


# Phase-0 demo stubs must never feed M1–M8 (they invent 3140 / 420 figures).
_STORE_LINE_SKIP_EXHIBITS = frozenset({"ex_hist_pl", "ex_hist_bs"})


def _lines_from_store(store: ExhibitStoreDoc) -> list[_Line]:
    out: list[_Line] = []
    for ex in store.exhibits:
        if ex.exhibit_id in _STORE_LINE_SKIP_EXHIBITS:
            continue
        for c in ex.cells or []:
            if c.value is None or not c.metric_key:
                continue
            # Skip any model / calculated outputs to avoid feedback loops (M1…Mn)
            if c.model_id or c.figure_type == FigureType.CALCULATED:
                continue
            # Skip stub / hand-seeded cells without a databook fact_id
            fid = str(c.fact_id or "")
            if not fid or fid.startswith(("stub:", "hand:")):
                continue
            year = int(c.fiscal_year or 0)
            if year <= 0:
                logger.warning(
                    "Skipping store cell %s.%s — missing fiscal_year",
                    c.exhibit_id,
                    c.cell_id,
                )
                continue
            out.append(
                _Line(
                    metric_key=c.metric_key,
                    fiscal_year=year,
                    value=float(c.value),
                    fact_id=c.fact_id,
                    currency=c.currency,
                    scale=c.scale,
                    status=c.status,
                    label=c.label,
                )
            )
    return out


def _pick_year(lines: list[_Line], *, prefer_closed: bool = True) -> int | None:
    years = _pick_years(lines, max_years=1, prefer_closed=prefer_closed)
    return years[0] if years else None


def _pick_years(
    lines: list[_Line],
    *,
    max_years: int = _TRADING_MAX_YEARS,
    prefer_closed: bool = True,
) -> list[int]:
    """Newest-first fiscal years (closed preferred for historical trading)."""
    years = sorted({ln.fiscal_year for ln in lines if ln.fiscal_year}, reverse=True)
    if not years:
        return []
    if prefer_closed:
        cutoff = _closed_year_cutoff()
        closed = [y for y in years if y <= cutoff]
        if closed:
            return closed[:max_years]
    return years[:max_years]


def _yoy_pct(curr: float, prior: float) -> float | None:
    """YoY %; undefined when prior is zero or negative (loss → n/m)."""
    if prior == 0 or float(prior) < 0:
        return None
    return (float(curr) - float(prior)) / abs(float(prior)) * 100.0


def _margin_pct(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator) * 100.0


def _as_percent_points(value: float) -> float:
    """Normalise ratio margins (0.30) to percent points (30) for walks / display."""
    v = float(value)
    if abs(v) <= 1.5:
        return v * 100.0
    return v


def _scale_key(scale: str | None) -> str:
    return (scale or "").strip().lower()


def _currency_key(currency: str | None) -> str:
    return (currency or "").strip().upper()


def _status_rank(status: CellStatus) -> int:
    """Higher is better for model inputs — prefer confirmed/proven over doubtful."""
    return {
        CellStatus.PROVEN: 4,
        CellStatus.DRAFT: 2,
        CellStatus.DOUBTFUL: 1,
        CellStatus.MISSING: 0,
    }.get(status, 0)


def _collapse_lines(lines: list[_Line]) -> list[_Line]:
    """Collapse duplicate values per metric×year; keep material source peers.

    Same-basis ratios (pack COGS ÷ pack revenue, OCF ÷ pack EBITDA) need both
    workbook and management figures when they disagree. Proven/workbook still
    wins among identical values.
    """
    groups: dict[tuple[str, int], dict[float, _Line]] = {}
    for ln in lines:
        key = (_norm(ln.metric_key), int(ln.fiscal_year))
        bucket = groups.setdefault(key, {})
        vk = round(float(ln.value), 6)
        prev = bucket.get(vk)
        if prev is None:
            bucket[vk] = ln
            continue
        rank = (_status_rank(ln.status), _source_pref(ln))
        prev_rank = (_status_rank(prev.status), _source_pref(prev))
        if rank > prev_rank:
            bucket[vk] = ln
    out: list[_Line] = []
    for bucket in groups.values():
        out.extend(bucket.values())
    return out


_ASSET_SCHEDULE_LOAN_LABEL_RE = re.compile(
    r"(?i)\b(?:vehicle|term|bank)\s+loans?\s*:\s*\d+"
)


def _is_asset_schedule_loan_line(ln: _Line) -> bool:
    """True for depreciation-register captions where the ID is not the balance."""
    return bool(_ASSET_SCHEDULE_LOAN_LABEL_RE.search(ln.label or ""))


def _source_overlap(a: list[str], b: list[str]) -> bool:
    sa = {s.strip().lower() for s in a if s and str(s).strip()}
    sb = {s.strip().lower() for s in b if s and str(s).strip()}
    return bool(sa & sb)


def _bucket_sum(
    lines: list[_Line],
    bucket: frozenset[str],
    year: int,
    *,
    additive: bool = True,
    align_sources: list[str] | None = None,
) -> tuple[float | None, list[_Line]]:
    """Aggregate lines in *bucket* for *year*.

    Prefer proven/confirmed over doubtful (aligns with databook consume). Exclusive
    metrics (``additive=False``) pick one best line — never sum duplicates.
    When *align_sources* is set, prefer lines that share a source filename so
    ratios (COGS÷revenue, OCF÷EBITDA) stay on one basis.
    """
    hit = [
        ln
        for ln in lines
        if ln.fiscal_year == year
        and _matches(_norm(ln.metric_key), bucket)
        and not _is_asset_schedule_loan_line(ln)
    ]
    if not hit:
        return None, []

    # Prefer the strongest status tier present (proven beats doubtful).
    best_rank = max(_status_rank(ln.status) for ln in hit)
    hit = [ln for ln in hit if _status_rank(ln.status) == best_rank]

    # Dominant (currency, scale) — warn and exclude mismatches
    from collections import Counter

    pairs = Counter(
        (_currency_key(ln.currency), _scale_key(ln.scale)) for ln in hit
    )
    # Prefer non-blank currency/scale when counts tie
    (dom_cur, dom_scl), _count = sorted(
        pairs.items(),
        key=lambda kv: (
            0 if kv[0][0] else 1,
            0 if kv[0][1] else 1,
            -kv[1],
        ),
    )[0]
    kept: list[_Line] = []
    for ln in hit:
        cur, scl = _currency_key(ln.currency), _scale_key(ln.scale)
        # Allow blanks to inherit the dominant pair
        if (cur and cur != dom_cur) or (scl and scl != dom_scl):
            logger.warning(
                "Skipping %s FY%s in bucket sum — currency/scale %s/%s "
                "≠ dominant %s/%s",
                ln.metric_key,
                year,
                cur or "—",
                scl or "—",
                dom_cur or "—",
                dom_scl or "—",
            )
            continue
        kept.append(ln)
    if not kept:
        return None, []
    if align_sources:
        from agetic_cdd_api.services_fdd_sources import classify_source, source_blob

        align_kind = classify_source(align_sources)
        # Prefer peers whose sources are the same kind as the numerator
        # (management pack ÷ pack revenue — never pack COGS ÷ workbook revenue).
        kind_match = [
            ln
            for ln in kept
            if classify_source(ln.sources, ln.label) == align_kind
            and (
                align_kind != "management"
                or "investor" not in source_blob(ln.sources)
            )
        ]
        overlap = [ln for ln in kept if _source_overlap(ln.sources, align_sources)]
        if kind_match:
            kept = kind_match
        elif overlap:
            kept = overlap
    if not additive:
        # Prefer same-basis source when aligning; otherwise workbook over ledger.
        kept.sort(
            key=lambda ln: (
                (
                    -1
                    if align_sources
                    and _source_overlap(ln.sources, align_sources)
                    else 0
                ),
                -_source_pref(ln) if not align_sources else 0,
                0 if _norm(ln.metric_key) in bucket else 1,
                len(_norm(ln.metric_key)),
                _norm(ln.metric_key),
            )
        )
        return kept[0].value, [kept[0]]
    return sum(ln.value for ln in kept), kept


def _cell(
    *,
    exhibit_id: str,
    cell_id: str,
    label: str,
    value: float,
    fact_id: str,
    currency: str | None,
    scale: str | None,
    fiscal_year: int | None,
    metric_key: str,
    status: CellStatus,
    model_id: str,
    figure_type: FigureType = FigureType.CALCULATED,
    basis_label: str | None = None,
) -> ExhibitCell:
    # Keep unit empty when it would duplicate scale (render joins currency+scale).
    unit = None if scale in {"%", "pp", "M", "B", "K", "Cr"} else scale
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=label,
        value=float(value),
        display=_fmt(value),
        unit=unit,
        currency=currency,
        scale=scale,
        fiscal_year=fiscal_year,
        metric_key=metric_key,
        fact_id=fact_id,
        figure_type=figure_type,
        evidence_tier=EvidenceTier.B,
        status=status,
        basis_label=basis_label or f"{model_id} · {MODELS_VERSION}",
        model_id=model_id,
        model_version=MODELS_VERSION,
    )


def build_trading_exhibit(
    lines: list[_Line],
    *,
    years: list[int] | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> tuple[list[ExhibitCell], list[str]]:
    """M1 — multi-year historical trading workbook (reported IS + YoY / margins)."""
    notes: list[str] = []
    ys = years or _pick_years(lines, max_years=_TRADING_MAX_YEARS, prefer_closed=True)
    if not ys:
        return [], ["no_trading_facts"]

    cells: list[ExhibitCell] = []
    # canonical_metric → year → (value, hit lines)
    series: dict[str, dict[int, tuple[float, list[_Line]]]] = {
        key: {} for _, key, _ in _TRADING_REPORTED
    }
    cur = currency
    scl = scale

    for y in ys:
        for bucket, canon, label in _TRADING_REPORTED:
            total, hit = _bucket_sum(lines, bucket, y, additive=False)
            if total is None:
                continue
            for ln in hit:
                cur = cur or ln.currency
                scl = scl or ln.scale
            # Reported margins may arrive as ratios (0.30) — normalise to %.
            if "margin" in canon:
                total = _as_percent_points(total)
            series[canon][y] = (total, hit)
            cells.append(
                _cell(
                    exhibit_id=TRADING_EXHIBIT_ID,
                    cell_id=metric_cell_id(canon, y),
                    label=f"{label} FY{y}",
                    value=total,
                    fact_id=_model_component_fact_id("m1", canon, y)
                    if len(hit) != 1
                    else hit[0].fact_id,
                    currency=None if "margin" in canon else cur,
                    scale="%" if "margin" in canon else scl,
                    fiscal_year=y,
                    metric_key=canon,
                    status=_worst_status(ln.status for ln in hit),
                    model_id="M1",
                    figure_type=FigureType.REPORTED,
                    basis_label=f"M1 historical trading · FY{y}",
                )
            )

    # Derived margins when components exist and margin not already reported
    for y in ys:
        rev = series["revenue"].get(y)
        if rev is None:
            continue
        rev_v, rev_hit = rev
        if y not in series["gross_margin"]:
            gp = series["gross_profit"].get(y)
            if gp is not None:
                m = _margin_pct(gp[0], rev_v)
                if m is not None:
                    cells.append(
                        _cell(
                            exhibit_id=TRADING_EXHIBIT_ID,
                            cell_id=metric_cell_id("gross_margin", y),
                            label=f"Gross margin % FY{y}",
                            value=round(m, 4),
                            fact_id=_model_component_fact_id("m1", "gross_margin", y),
                            currency=cur,
                            scale="%",
                            fiscal_year=y,
                            metric_key="gross_margin",
                            status=_worst_status(
                                [*(ln.status for ln in rev_hit), *(ln.status for ln in gp[1])]
                            ),
                            model_id="M1",
                            figure_type=FigureType.CALCULATED,
                            basis_label=f"M1 gross profit ÷ revenue · FY{y}",
                        )
                    )
                    series["gross_margin"][y] = (m, rev_hit + gp[1])
        if y not in series["ebitda_margin"]:
            eb = series["ebitda"].get(y)
            if eb is not None:
                m = _margin_pct(eb[0], rev_v)
                if m is not None:
                    cells.append(
                        _cell(
                            exhibit_id=TRADING_EXHIBIT_ID,
                            cell_id=metric_cell_id("ebitda_margin", y),
                            label=f"EBITDA margin % FY{y}",
                            value=round(m, 4),
                            fact_id=_model_component_fact_id("m1", "ebitda_margin", y),
                            currency=cur,
                            scale="%",
                            fiscal_year=y,
                            metric_key="ebitda_margin",
                            status=_worst_status(
                                [*(ln.status for ln in rev_hit), *(ln.status for ln in eb[1])]
                            ),
                            model_id="M1",
                            figure_type=FigureType.CALCULATED,
                            basis_label=f"M1 EBITDA ÷ revenue · FY{y}",
                        )
                    )
                    series["ebitda_margin"][y] = (m, rev_hit + eb[1])

    # YoY on consecutive years present in the workbook (newest year gets the calc)
    sorted_asc = sorted(ys)
    for prior, curr in zip(sorted_asc, sorted_asc[1:]):
        for canon, label in (("revenue", "Revenue YoY %"), ("ebitda", "EBITDA YoY %")):
            if prior not in series[canon] or curr not in series[canon]:
                continue
            curr_v, curr_hit = series[canon][curr]
            prior_v, prior_hit = series[canon][prior]
            yoy = _yoy_pct(curr_v, prior_v)
            if yoy is None:
                if float(prior_v) < 0:
                    notes.append(f"{canon}_yoy_nm_fy{curr}_prior_loss")
                else:
                    notes.append(f"{canon}_yoy_undefined_fy{curr}_div0")
                continue
            yoy_key = f"{canon}_yoy"
            cells.append(
                _cell(
                    exhibit_id=TRADING_EXHIBIT_ID,
                    cell_id=metric_cell_id(yoy_key, curr),
                    label=f"{label} FY{curr}",
                    value=round(yoy, 4),
                    fact_id=_model_component_fact_id("m1", yoy_key, curr),
                    currency=None,
                    scale="%",
                    fiscal_year=curr,
                    metric_key=yoy_key,
                    status=_worst_status(
                        [*(ln.status for ln in curr_hit), *(ln.status for ln in prior_hit)]
                    ),
                    model_id="M1",
                    figure_type=FigureType.CALCULATED,
                    basis_label=f"M1 ({canon} FY{curr} − FY{prior}) ÷ |FY{prior}|",
                )
            )

    if not cells:
        notes.append(f"no_trading_lines_for_years_{ys}")
    else:
        notes.append(f"m1_years:{','.join(str(y) for y in ys)}")
        notes.append("Basis: investor workbook revenue (closed years)")
    return cells, notes


def build_balance_sheet_exhibit(
    lines: list[_Line],
    *,
    year: int | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> tuple[list[ExhibitCell], list[str]]:
    """M8 — material BS lines for the chosen year."""
    notes: list[str] = []
    y = year or _pick_year(lines)
    if y is None:
        return [], ["no_bs_facts"]
    cells: list[ExhibitCell] = []
    # One cell per metric — prefer pack totals over zeroed asset-register lines.
    buckets: list[tuple[frozenset[str], str]] = [
        (_CASH, "Cash"),
        (_RESTRICTED_CASH, "Restricted cash"),
        (_AR, "Accounts receivable"),
        (_INVENTORY, "Inventory"),
        (_AP, "Accounts payable"),
        (_GROSS_DEBT_PRINTED, "Gross debt"),
        (_LOAN_FACILITIES, "Term / facility loans"),
        (_LEASE, "Lease liabilities"),
        (_BS_LINES, "Balance sheet"),
    ]
    seen_keys: set[str] = set()
    for bucket, _label in buckets:
        # Collect distinct metric keys in this bucket for the year.
        keys = sorted(
            {
                _norm(ln.metric_key)
                for ln in lines
                if ln.fiscal_year == y and _matches(_norm(ln.metric_key), bucket)
            }
        )
        for key in keys:
            if key in seen_keys:
                continue
            total, hit = _bucket_sum(lines, frozenset({key}), y, additive=False)
            if total is None or not hit:
                continue
            # Skip zero inventory/cash from depreciation registers when a
            # non-zero peer exists (handled by _bucket_sum status/source pref).
            ln = hit[0]
            # Prefer non-zero when the exclusive pick is a zero stub.
            if float(total) == 0.0:
                alt_total, alt_hit = _bucket_sum(
                    [x for x in lines if abs(float(x.value)) > 1e-12],
                    frozenset({key}),
                    y,
                    additive=False,
                )
                if alt_total is not None and alt_hit:
                    total, hit, ln = alt_total, alt_hit, alt_hit[0]
            seen_keys.add(key)
            cells.append(
                _cell(
                    exhibit_id=BS_EXHIBIT_ID,
                    cell_id=metric_cell_id(ln.metric_key, y),
                    label=f"{ln.label} FY{y}",
                    value=float(total),
                    fact_id=ln.fact_id,
                    currency=ln.currency or currency,
                    scale=ln.scale or scale,
                    fiscal_year=y,
                    metric_key=ln.metric_key,
                    status=ln.status,
                    model_id="M8",
                    figure_type=FigureType.REPORTED,
                    basis_label=f"M8 balance sheet · FY{y}",
                )
            )
    if not cells:
        notes.append(f"no_bs_lines_for_fy{y}")
    return cells, notes


def build_nwc_exhibit(
    lines: list[_Line],
    *,
    year: int | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> tuple[list[ExhibitCell], list[str]]:
    """M5 — NWC bridge components + total for the chosen year."""
    notes: list[str] = []
    y = year or _pick_year(lines)
    if y is None:
        return [], ["no_nwc_facts"]

    cells: list[ExhibitCell] = []
    asset_total = 0.0
    liab_total = 0.0
    have_asset = False
    have_liab = False
    cur = currency
    scl = scale
    statuses: list[CellStatus] = []

    for bucket, label, is_asset in (
        (_AR, "Accounts receivable", True),
        (_INVENTORY, "Inventory", True),
        (_OTHER_WC_ASSET, "Other NWC assets", True),
        (_AP, "Accounts payable", False),
        (_OTHER_WC_LIAB, "Other NWC liabilities", False),
    ):
        total, hit = _bucket_sum(lines, bucket, y)
        if total is None:
            continue
        if is_asset:
            asset_total += total
            have_asset = True
        else:
            liab_total += total
            have_liab = True
        for ln in hit:
            cur = cur or ln.currency
            scl = scl or ln.scale
            statuses.append(ln.status)
        component_key = _norm(label)
        cells.append(
            _cell(
                exhibit_id=NWC_EXHIBIT_ID,
                cell_id=metric_cell_id(component_key, y),
                label=f"{label} FY{y}",
                value=total,
                fact_id=_model_component_fact_id("m5", component_key, y),
                currency=cur,
                scale=scl,
                fiscal_year=y,
                metric_key=component_key,
                status=_worst_status(ln.status for ln in hit),
                model_id="M5",
                basis_label=f"M5 NWC component · FY{y}",
            )
        )

    # Fallback: printed current-liabilities total when AP/other WC liab absent.
    if have_asset and not have_liab:
        cl_tot, cl_hit = _bucket_sum(lines, _CURRENT_LIABILITIES, y, additive=False)
        if cl_tot is not None:
            liab_total = float(cl_tot)
            have_liab = True
            for ln in cl_hit:
                cur = cur or ln.currency
                scl = scl or ln.scale
                statuses.append(ln.status)
            cells.append(
                _cell(
                    exhibit_id=NWC_EXHIBIT_ID,
                    cell_id=metric_cell_id("current_liabilities", y),
                    label=f"Current liabilities FY{y}",
                    value=cl_tot,
                    fact_id=_model_component_fact_id("m5", "current_liabilities", y),
                    currency=cur,
                    scale=scl,
                    fiscal_year=y,
                    metric_key="current_liabilities",
                    status=_worst_status(ln.status for ln in cl_hit),
                    model_id="M5",
                    basis_label=(
                        f"M5 NWC liability fallback (current liabilities) · FY{y}"
                    ),
                )
            )
            notes.append("nwc_liabilities_from_current_liabilities")

    if have_asset or have_liab:
        nwc = asset_total - liab_total
        cells.append(
            _cell(
                exhibit_id=NWC_EXHIBIT_ID,
                cell_id=f"nwc_fy{y}",
                label=f"Net working capital (AR+Inv−AP) FY{y}",
                value=nwc,
                fact_id=f"m5:nwc:{y}",
                currency=cur,
                scale=scl,
                fiscal_year=y,
                metric_key="nwc",
                status=(
                    _worst_status(statuses)
                    if (have_asset and have_liab)
                    else CellStatus.DRAFT
                ),
                model_id="M5",
                basis_label=(
                    f"M5 NWC (narrow) = AR + inventory − AP · FY{y}"
                    "; other current assets/liabilities not included"
                ),
            )
        )
        notes.append("nwc_basis:narrow_ar_inv_ap")
    else:
        notes.append(f"no_nwc_components_for_fy{y}")
    if have_asset and not have_liab:
        notes.append("nwc_liabilities_missing")
    if have_liab and not have_asset:
        notes.append("nwc_assets_missing")
    return cells, notes


def build_net_debt_exhibit(
    lines: list[_Line],
    *,
    year: int | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> tuple[list[ExhibitCell], list[str]]:
    """M6 — net debt bridge; leases disclosed beside the headline."""
    notes: list[str] = []
    y = year or _pick_year(lines)
    if y is None:
        return [], ["no_net_debt_facts"]

    cells: list[ExhibitCell] = []
    cur = currency
    scl = scale
    statuses: list[CellStatus] = []

    cash, cash_hit = _bucket_sum(lines, _CASH, y)
    # Prefer printed gross debt; else sum loan facilities; else LT-liability total.
    # Never add LT totals on top of SBA/term loans (double-counts State & Fed).
    debt, debt_hit = _bucket_sum(lines, _GROSS_DEBT_PRINTED, y, additive=False)
    debt_basis = "printed gross debt"
    if debt is None:
        debt, debt_hit = _bucket_sum(lines, _LOAN_FACILITIES, y, additive=True)
        debt_basis = "sum of interest-bearing facilities"
    if debt is None:
        debt, debt_hit = _bucket_sum(lines, _LT_LIABILITY_TOTALS, y, additive=False)
        debt_basis = "long-term liabilities total"
    debt_like, dl_hit = _bucket_sum(lines, _DEBT_LIKE, y)
    leases, lease_hit = _bucket_sum(lines, _LEASE, y)
    restricted, rest_hit = _bucket_sum(lines, _RESTRICTED_CASH, y)

    def _add_component(
        cell_id: str,
        label: str,
        total: float | None,
        hit: list[_Line],
        metric_key: str,
    ) -> None:
        nonlocal cur, scl
        if total is None:
            return
        for ln in hit:
            cur = cur or ln.currency
            scl = scl or ln.scale
            statuses.append(ln.status)
        cells.append(
            _cell(
                exhibit_id=NET_DEBT_EXHIBIT_ID,
                cell_id=cell_id,
                label=label,
                value=total,
                fact_id=_model_component_fact_id("m6", metric_key, y),
                currency=cur,
                scale=scl,
                fiscal_year=y,
                metric_key=metric_key,
                status=_worst_status(ln.status for ln in hit),
                model_id="M6",
                basis_label=f"M6 net debt component · FY{y}",
            )
        )

    _add_component(f"gross_debt_fy{y}", f"Gross interest-bearing debt FY{y}", debt, debt_hit, "gross_debt")
    _add_component(f"debt_like_fy{y}", f"Debt-like items FY{y}", debt_like, dl_hit, "debt_like")
    _add_component(f"cash_fy{y}", f"Freely available cash FY{y}", cash, cash_hit, "cash")
    _add_component(
        f"restricted_cash_fy{y}",
        f"Restricted / trapped cash FY{y}",
        restricted,
        rest_hit,
        "restricted_cash",
    )
    # Leases beside — not in headline net debt
    _add_component(
        f"lease_liabilities_fy{y}",
        f"Lease liabilities (beside net debt) FY{y}",
        leases,
        lease_hit,
        "lease_liabilities",
    )

    if debt is None and debt_like is None and cash is None:
        notes.append(f"no_net_debt_components_for_fy{y}")
        return cells, notes

    gross = (debt or 0.0) + (debt_like or 0.0)
    cash_for_net = cash or 0.0
    net = gross - cash_for_net
    status = _worst_status(statuses) if statuses else CellStatus.DRAFT
    if debt is None and debt_like is None:
        status = CellStatus.DRAFT
        notes.append("gross_debt_missing")
    if cash is None:
        status = CellStatus.DRAFT
        notes.append("cash_missing")
    notes.append(f"gross_debt_basis:{debt_basis}")

    cells.append(
        _cell(
            exhibit_id=NET_DEBT_EXHIBIT_ID,
            cell_id=f"net_debt_fy{y}",
            label=f"Net debt FY{y}",
            value=net,
            fact_id=f"m6:net_debt:{y}",
            currency=cur,
            scale=scl,
            fiscal_year=y,
            metric_key="net_debt",
            status=status,
            model_id="M6",
            basis_label=(
                f"M6 net debt = gross debt ({debt_basis}) (+ debt-like) − cash · FY{y}"
                + ("; leases disclosed beside" if leases is not None else "")
            ),
        )
    )
    return cells, notes


def build_margin_exhibit(
    lines: list[_Line],
    *,
    years: list[int] | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> tuple[list[ExhibitCell], list[str]]:
    """M2 — revenue / margin walk from M1 inputs (levels + YoY + Δpp).

    Emits closed-year revenue, COGS/GP, GM%, EBITDA/EM%, YoY revenue, and
    year-on-year margin moves in percentage points. Optional concentration
    metrics are included when present in the fact table.
    """
    notes: list[str] = []
    ys = years or _pick_years(lines, max_years=2, prefer_closed=True)
    if not ys:
        return [], ["no_margin_facts"]

    cells: list[ExhibitCell] = []
    cur = currency
    scl = scale
    # year → (value, hits) for walk math
    rev: dict[int, tuple[float, list[_Line]]] = {}
    gp: dict[int, tuple[float, list[_Line]]] = {}
    gm: dict[int, tuple[float, list[_Line]]] = {}
    eb: dict[int, tuple[float, list[_Line]]] = {}
    em: dict[int, tuple[float, list[_Line]]] = {}

    def _add(
        *,
        y: int,
        metric_key: str,
        label: str,
        value: float,
        hit: list[_Line],
        figure_type: FigureType,
        basis: str,
        unit_scale: str | None = None,
    ) -> None:
        nonlocal cur, scl
        for ln in hit:
            cur = cur or ln.currency
            scl = scl or ln.scale
        cells.append(
            _cell(
                exhibit_id=MARGIN_EXHIBIT_ID,
                cell_id=metric_cell_id(metric_key, y),
                label=label,
                value=value,
                fact_id=_model_component_fact_id("m2", metric_key, y),
                currency=None if unit_scale in {"%", "pp"} else cur,
                scale=unit_scale if unit_scale is not None else scl,
                fiscal_year=y,
                metric_key=metric_key,
                status=_worst_status(ln.status for ln in hit) if hit else CellStatus.DRAFT,
                model_id="M2",
                figure_type=figure_type,
                basis_label=basis,
            )
        )

    for y in ys:
        r_tot, r_hit = _bucket_sum(lines, _REVENUE, y, additive=False)
        g_tot, g_hit = _bucket_sum(lines, _GROSS_PROFIT, y, additive=False)
        gm_tot, gm_hit = _bucket_sum(lines, _GROSS_MARGIN, y, additive=False)
        e_tot, e_hit = _bucket_sum(lines, _EBITDA, y, additive=False)
        em_tot, em_hit = _bucket_sum(lines, _EBITDA_MARGIN, y, additive=False)
        cogs_tot, cogs_hit = _bucket_sum(lines, _COGS, y, additive=False)

        if r_tot is not None:
            rev[y] = (r_tot, r_hit)
            _add(
                y=y,
                metric_key="revenue",
                label=f"Revenue FY{y}",
                value=r_tot,
                hit=r_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M2 revenue · FY{y}",
            )
        if g_tot is not None:
            gp[y] = (g_tot, g_hit)
            _add(
                y=y,
                metric_key="gross_profit",
                label=f"Gross profit FY{y}",
                value=g_tot,
                hit=g_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M2 gross profit · FY{y}",
            )
        elif r_tot is not None and cogs_tot is not None:
            # Derive GP = revenue − COGS when GP not reported
            derived = float(r_tot) - float(cogs_tot)
            hit = [*r_hit, *cogs_hit]
            gp[y] = (derived, hit)
            _add(
                y=y,
                metric_key="gross_profit",
                label=f"Gross profit FY{y}",
                value=derived,
                hit=hit,
                figure_type=FigureType.CALCULATED,
                basis=f"M2 revenue − COGS · FY{y}",
            )
        if cogs_tot is not None:
            _add(
                y=y,
                metric_key="cogs",
                label=f"Cost of sales FY{y}",
                value=abs(float(cogs_tot)),
                hit=cogs_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M2 COGS · FY{y}",
            )
        elif r_tot is not None and y in gp:
            derived_cogs = float(r_tot) - float(gp[y][0])
            hit = [*r_hit, *gp[y][1]]
            _add(
                y=y,
                metric_key="cogs",
                label=f"Cost of sales FY{y}",
                value=derived_cogs,
                hit=hit,
                figure_type=FigureType.CALCULATED,
                basis=f"M2 revenue − gross profit · FY{y}",
            )

        # Gross margin %
        gm_val: float | None = gm_tot
        gm_hits = gm_hit
        gm_fig = FigureType.REPORTED
        if gm_val is not None:
            gm_val = _as_percent_points(gm_val)
        if gm_val is None and r_tot is not None and y in gp:
            gm_val = _margin_pct(gp[y][0], r_tot)
            gm_hits = [*r_hit, *gp[y][1]]
            gm_fig = FigureType.CALCULATED
        if gm_val is not None:
            gm[y] = (gm_val, gm_hits)
            _add(
                y=y,
                metric_key="gross_margin",
                label=f"Gross margin % FY{y}",
                value=round(gm_val, 4),
                hit=gm_hits,
                figure_type=gm_fig,
                basis=(
                    f"M2 gross margin · FY{y}"
                    if gm_fig == FigureType.REPORTED
                    else f"M2 GP ÷ revenue · FY{y}"
                ),
                unit_scale="%",
            )

        if e_tot is not None:
            eb[y] = (e_tot, e_hit)
            _add(
                y=y,
                metric_key="ebitda",
                label=f"EBITDA FY{y}",
                value=e_tot,
                hit=e_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M2 EBITDA · FY{y}",
            )
        em_val: float | None = em_tot
        em_hits = em_hit
        em_fig = FigureType.REPORTED
        if em_val is not None:
            em_val = _as_percent_points(em_val)
        if em_val is None and r_tot is not None and e_tot is not None:
            em_val = _margin_pct(e_tot, r_tot)
            em_hits = [*r_hit, *e_hit]
            em_fig = FigureType.CALCULATED
        if em_val is not None:
            em[y] = (em_val, em_hits)
            _add(
                y=y,
                metric_key="ebitda_margin",
                label=f"EBITDA margin % FY{y}",
                value=round(em_val, 4),
                hit=em_hits,
                figure_type=em_fig,
                basis=(
                    f"M2 EBITDA margin · FY{y}"
                    if em_fig == FigureType.REPORTED
                    else f"M2 EBITDA ÷ revenue · FY{y}"
                ),
                unit_scale="%",
            )

        # Optional concentration / mix
        mix_tot, mix_hit = _bucket_sum(lines, _MIX_CONCENTRATION, y, additive=False)
        if mix_tot is not None:
            _add(
                y=y,
                metric_key="top_customer_pct",
                label=f"Top-customer concentration % FY{y}",
                value=mix_tot,
                hit=mix_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M2 concentration · FY{y}",
                unit_scale="%",
            )

    # Walk calcs on newest year vs prior
    sorted_asc = sorted(ys)
    if len(sorted_asc) >= 2:
        prior, curr = sorted_asc[-2], sorted_asc[-1]
        if prior in rev and curr in rev:
            yoy = _yoy_pct(rev[curr][0], rev[prior][0])
            if yoy is not None:
                _add(
                    y=curr,
                    metric_key="revenue_yoy",
                    label=f"Revenue YoY % FY{curr}",
                    value=round(yoy, 4),
                    hit=[*rev[curr][1], *rev[prior][1]],
                    figure_type=FigureType.CALCULATED,
                    basis=f"M2 (rev FY{curr} − FY{prior}) ÷ |FY{prior}|",
                    unit_scale="%",
                )
        if prior in gm and curr in gm:
            delta = float(gm[curr][0]) - float(gm[prior][0])
            _add(
                y=curr,
                metric_key="gross_margin_delta_pp",
                label=f"Gross margin Δpp FY{curr}",
                value=round(delta, 4),
                hit=[*gm[curr][1], *gm[prior][1]],
                figure_type=FigureType.CALCULATED,
                basis=f"M2 GM% FY{curr} − FY{prior}",
                unit_scale="pp",
            )
            notes.append(f"gm_walk:FY{prior}->{curr}:{delta:+.2f}pp")
        if prior in em and curr in em:
            delta = float(em[curr][0]) - float(em[prior][0])
            _add(
                y=curr,
                metric_key="ebitda_margin_delta_pp",
                label=f"EBITDA margin Δpp FY{curr}",
                value=round(delta, 4),
                hit=[*em[curr][1], *em[prior][1]],
                figure_type=FigureType.CALCULATED,
                basis=f"M2 EM% FY{curr} − FY{prior}",
                unit_scale="pp",
            )
            notes.append(f"em_walk:FY{prior}->{curr}:{delta:+.2f}pp")
    else:
        notes.append("margin_walk_needs_two_years")

    if not cells:
        notes.append(f"no_margin_lines_for_years_{ys}")
    else:
        notes.append(f"m2_years:{','.join(str(y) for y in ys)}")
        notes.append("Basis: investor workbook revenue (closed years)")
    return cells, notes


def build_costs_exhibit(
    lines: list[_Line],
    *,
    years: list[int] | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> tuple[list[ExhibitCell], list[str]]:
    """M3 — costs and people workbook (COGS / SG&A / labour + ratios vs revenue).

    Emits closed-year cost lines, cost-as-%-of-revenue, optional headcount /
    revenue-per-head, and YoY on cost lines when two years are present.
    Labour is disclosed beside SG&A (often a subset) — never summed into opex.
    """
    notes: list[str] = []
    ys = years or _pick_years(lines, max_years=2, prefer_closed=True)
    if not ys:
        return [], ["no_costs_facts"]

    cells: list[ExhibitCell] = []
    cur = currency
    scl = scale
    rev: dict[int, tuple[float, list[_Line]]] = {}
    cogs: dict[int, tuple[float, list[_Line]]] = {}
    sga: dict[int, tuple[float, list[_Line]]] = {}
    labor: dict[int, tuple[float, list[_Line]]] = {}
    headcount: dict[int, tuple[float, list[_Line]]] = {}

    def _add(
        *,
        y: int,
        metric_key: str,
        label: str,
        value: float,
        hit: list[_Line],
        figure_type: FigureType,
        basis: str,
        unit_scale: str | None = None,
    ) -> None:
        nonlocal cur, scl
        for ln in hit:
            cur = cur or ln.currency
            scl = scl or ln.scale
        cells.append(
            _cell(
                exhibit_id=COSTS_EXHIBIT_ID,
                cell_id=metric_cell_id(metric_key, y),
                label=label,
                value=value,
                fact_id=_model_component_fact_id("m3", metric_key, y),
                currency=None if unit_scale in {"%", "pp", "FTE"} else cur,
                scale=unit_scale if unit_scale is not None else scl,
                fiscal_year=y,
                metric_key=metric_key,
                status=_worst_status(ln.status for ln in hit) if hit else CellStatus.DRAFT,
                model_id="M3",
                figure_type=figure_type,
                basis_label=basis,
            )
        )

    for y in ys:
        c_tot, c_hit = _bucket_sum(lines, _COGS, y, additive=False)
        s_tot, s_hit = _bucket_sum(lines, _SGA, y, additive=False)
        l_tot, l_hit = _bucket_sum(lines, _LABOR, y, additive=False)
        h_tot, h_hit = _bucket_sum(lines, _HEADCOUNT, y, additive=False)
        # Align revenue to the cost-pack source when costs are from the monthly
        # pack — avoids pack COGS ÷ workbook revenue.
        cost_sources: list[str] = []
        for hit in (c_hit, s_hit, l_hit):
            for ln in hit:
                cost_sources.extend(ln.sources)
        r_tot, r_hit = _bucket_sum(
            lines,
            _REVENUE,
            y,
            additive=False,
            align_sources=cost_sources or None,
        )

        if r_tot is not None:
            rev[y] = (r_tot, r_hit)
            _add(
                y=y,
                metric_key="revenue",
                label=f"Revenue FY{y}",
                value=r_tot,
                hit=r_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M3 revenue · FY{y}",
            )

        if c_tot is not None:
            c_abs = abs(float(c_tot))
            cogs[y] = (c_abs, c_hit)
            _add(
                y=y,
                metric_key="cogs",
                label=f"Cost of sales FY{y}",
                value=c_abs,
                hit=c_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M3 COGS · FY{y}",
            )
        elif r_tot is not None:
            # Derive COGS from revenue − GP when GP is on the fact table
            g_tot, g_hit = _bucket_sum(
                lines,
                _GROSS_PROFIT,
                y,
                additive=False,
                align_sources=list(r_hit[0].sources) if r_hit else None,
            )
            if g_tot is not None:
                derived = abs(float(r_tot) - float(g_tot))
                hit = [*r_hit, *g_hit]
                cogs[y] = (derived, hit)
                _add(
                    y=y,
                    metric_key="cogs",
                    label=f"Cost of sales FY{y}",
                    value=derived,
                    hit=hit,
                    figure_type=FigureType.CALCULATED,
                    basis=f"M3 revenue − gross profit · FY{y}",
                )

        if s_tot is not None:
            s_abs = abs(float(s_tot))
            sga[y] = (s_abs, s_hit)
            _add(
                y=y,
                metric_key="sga",
                label=f"SG&A FY{y}",
                value=s_abs,
                hit=s_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M3 SG&A · FY{y}",
            )

        if l_tot is not None:
            l_abs = abs(float(l_tot))
            labor[y] = (l_abs, l_hit)
            _add(
                y=y,
                metric_key="labor_cost",
                label=f"Labour cost FY{y}",
                value=l_abs,
                hit=l_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M3 labour · FY{y}",
            )

        if h_tot is not None:
            headcount[y] = (float(h_tot), h_hit)
            _add(
                y=y,
                metric_key="headcount",
                label=f"Headcount FY{y}",
                value=float(h_tot),
                hit=h_hit,
                figure_type=FigureType.REPORTED,
                basis=f"M3 headcount · FY{y}",
                unit_scale="FTE",
            )

        # Cost ratios vs same-basis revenue
        if y in rev:
            r_v, r_h = rev[y]
            for series, key, label, basis in (
                (cogs, "cogs_pct_revenue", "COGS % of revenue", "M3 COGS ÷ same-basis revenue"),
                (sga, "sga_pct_revenue", "SG&A % of revenue", "M3 SG&A ÷ same-basis revenue"),
                (
                    labor,
                    "labor_pct_revenue",
                    "Labour % of revenue",
                    "M3 labour ÷ same-basis revenue",
                ),
            ):
                if y not in series:
                    continue
                pct = _margin_pct(series[y][0], r_v)
                if pct is None:
                    continue
                hit = [*r_h, *series[y][1]]
                _add(
                    y=y,
                    metric_key=key,
                    label=f"{label} FY{y}",
                    value=round(pct, 4),
                    hit=hit,
                    figure_type=FigureType.CALCULATED,
                    basis=f"{basis} · FY{y}",
                    unit_scale="%",
                )

            if y in headcount and float(headcount[y][0]) != 0:
                rph = float(r_v) / float(headcount[y][0])
                hit = [*r_h, *headcount[y][1]]
                _add(
                    y=y,
                    metric_key="revenue_per_head",
                    label=f"Revenue per head FY{y}",
                    value=round(rph, 4),
                    hit=hit,
                    figure_type=FigureType.CALCULATED,
                    basis=f"M3 revenue ÷ headcount · FY{y}",
                )

    # YoY on cost lines (newest vs prior)
    sorted_asc = sorted(ys)
    if len(sorted_asc) >= 2:
        prior, curr = sorted_asc[-2], sorted_asc[-1]
        for series, key, label in (
            (cogs, "cogs_yoy", "COGS YoY %"),
            (sga, "sga_yoy", "SG&A YoY %"),
            (labor, "labor_yoy", "Labour YoY %"),
            (headcount, "headcount_yoy", "Headcount YoY %"),
        ):
            if prior not in series or curr not in series:
                continue
            yoy = _yoy_pct(series[curr][0], series[prior][0])
            if yoy is None:
                notes.append(f"{key}_undefined_fy{curr}")
                continue
            _add(
                y=curr,
                metric_key=key,
                label=f"{label} FY{curr}",
                value=round(yoy, 4),
                hit=[*series[curr][1], *series[prior][1]],
                figure_type=FigureType.CALCULATED,
                basis=f"M3 ({key.replace('_yoy', '')} FY{curr} − FY{prior}) ÷ |FY{prior}|",
                unit_scale="%",
            )
            notes.append(f"{key}:FY{prior}->{curr}:{yoy:+.2f}%")
    else:
        notes.append("costs_yoy_needs_two_years")

    # Require at least one cost / people line (revenue alone is not enough)
    cost_keys = {
        "cogs",
        "sga",
        "labor_cost",
        "headcount",
        "cogs_pct_revenue",
        "sga_pct_revenue",
        "labor_pct_revenue",
    }
    if not any(c.metric_key in cost_keys for c in cells):
        notes.append(f"no_cost_lines_for_years_{ys}")
        return [], notes

    notes.append(f"m3_years:{','.join(str(y) for y in ys)}")
    notes.append("Basis: monthly pack revenue (same-basis cost ratios)")
    return cells, notes


def build_cash_conversion_exhibit(
    lines: list[_Line],
    *,
    year: int | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> tuple[list[ExhibitCell], list[str]]:
    """M7 — OCF, capex, FCF and cash conversion vs EBITDA for one closed year."""
    notes: list[str] = []
    y = year or _pick_year(lines)
    if y is None:
        return [], ["no_cash_conversion_facts"]

    cells: list[ExhibitCell] = []
    cur = currency
    scl = scale
    statuses: list[CellStatus] = []

    ocf, ocf_hit = _bucket_sum(lines, _OCF, y, additive=False)
    capex_raw, capex_hit = _bucket_sum(
        lines,
        _CAPEX,
        y,
        additive=False,
        align_sources=[s for ln in ocf_hit for s in ln.sources] or None,
    )
    ebitda, ebitda_hit = _bucket_sum(
        lines,
        _EBITDA,
        y,
        additive=False,
        align_sources=[s for ln in ocf_hit for s in ln.sources] or None,
    )

    def _add(
        *,
        cell_id: str,
        label: str,
        value: float,
        hit: list[_Line],
        metric_key: str,
        figure_type: FigureType,
        basis: str,
        unit_scale: str | None = None,
    ) -> None:
        nonlocal cur, scl
        for ln in hit:
            cur = cur or ln.currency
            scl = scl or ln.scale
            statuses.append(ln.status)
        cells.append(
            _cell(
                exhibit_id=CASH_CONV_EXHIBIT_ID,
                cell_id=cell_id,
                label=label,
                value=value,
                fact_id=_model_component_fact_id("m7", metric_key, y),
                currency=None if unit_scale in {"%", "pp"} else cur,
                scale=unit_scale if unit_scale is not None else scl,
                fiscal_year=y,
                metric_key=metric_key,
                status=_worst_status(ln.status for ln in hit) if hit else CellStatus.DRAFT,
                model_id="M7",
                figure_type=figure_type,
                basis_label=basis,
            )
        )

    if ocf is not None:
        _add(
            cell_id=metric_cell_id("operating_cash_flow", y),
            label=f"Operating cash flow FY{y}",
            value=ocf,
            hit=ocf_hit,
            metric_key="operating_cash_flow",
            figure_type=FigureType.REPORTED,
            basis=f"M7 operating cash flow · FY{y}",
        )
    else:
        notes.append(f"ocf_missing_fy{y}")

    # Capex is a spend; CF extracts may be signed negative — normalise to |capex|
    capex_spend: float | None = None
    if capex_raw is not None:
        capex_spend = abs(float(capex_raw))
        _add(
            cell_id=metric_cell_id("capex", y),
            label=f"Capital expenditure FY{y}",
            value=capex_spend,
            hit=capex_hit,
            metric_key="capex",
            figure_type=FigureType.REPORTED,
            basis=f"M7 capex (absolute spend) · FY{y}",
        )
    else:
        notes.append(f"capex_missing_fy{y}")

    if ebitda is not None:
        _add(
            cell_id=metric_cell_id("ebitda", y),
            label=f"EBITDA (for conversion) FY{y}",
            value=ebitda,
            hit=ebitda_hit,
            metric_key="ebitda",
            figure_type=FigureType.REPORTED,
            basis=f"M7 EBITDA reference · FY{y}",
        )

    if ocf is not None and capex_spend is not None:
        fcf = float(ocf) - float(capex_spend)
        _add(
            cell_id=metric_cell_id("free_cash_flow", y),
            label=f"Free cash flow FY{y}",
            value=fcf,
            hit=[*ocf_hit, *capex_hit],
            metric_key="free_cash_flow",
            figure_type=FigureType.CALCULATED,
            basis=f"M7 FCF = OCF − |capex| · FY{y}",
        )
    elif ocf is not None and capex_spend is None:
        notes.append("fcf_held_capex_missing")

    if ocf is not None and ebitda is not None and float(ebitda) != 0.0:
        conv = float(ocf) / float(ebitda) * 100.0
        _add(
            cell_id=metric_cell_id("cash_conversion", y),
            label=f"Cash conversion % FY{y}",
            value=round(conv, 4),
            hit=[*ocf_hit, *ebitda_hit],
            metric_key="cash_conversion",
            figure_type=FigureType.CALCULATED,
            basis=f"M7 OCF ÷ EBITDA · FY{y}",
            unit_scale="%",
        )
    elif ocf is not None and ebitda is None:
        notes.append("cash_conversion_held_ebitda_missing")

    if (
        ocf is not None
        and capex_spend is not None
        and ebitda is not None
        and float(ebitda) != 0.0
    ):
        fcf = float(ocf) - float(capex_spend)
        fcf_conv = fcf / float(ebitda) * 100.0
        _add(
            cell_id=metric_cell_id("fcf_conversion", y),
            label=f"FCF conversion % FY{y}",
            value=round(fcf_conv, 4),
            hit=[*ocf_hit, *capex_hit, *ebitda_hit],
            metric_key="fcf_conversion",
            figure_type=FigureType.CALCULATED,
            basis=f"M7 FCF ÷ EBITDA · FY{y}",
            unit_scale="%",
        )

    # EBITDA alone is not a cash conversion workbook — drop it if OCF missing.
    if ocf is None:
        cells = [c for c in cells if c.metric_key != "ebitda"]
        if not cells:
            notes.append(f"cash_conversion_held_ocf_missing_fy{y}")
    if not cells:
        notes.append(f"no_cash_conversion_lines_for_fy{y}")
    return cells, notes


def apply_model_exhibits(
    store: ExhibitStoreDoc,
    *,
    trading_cells: list[ExhibitCell] | None = None,
    margin_cells: list[ExhibitCell] | None = None,
    costs_cells: list[ExhibitCell] | None = None,
    cash_cells: list[ExhibitCell] | None = None,
    bs_cells: list[ExhibitCell],
    nwc_cells: list[ExhibitCell],
    net_debt_cells: list[ExhibitCell],
    notes_by_exhibit: dict[str, list[str]] | None = None,
) -> ExhibitStoreDoc:
    """Replace M1/M2/M3/M5/M6/M7/M8 exhibits (full cell replace — no stale merge)."""
    notes_by_exhibit = notes_by_exhibit or {}
    batches: list[tuple[str, str, str, list[ExhibitCell]]] = [
        (TRADING_EXHIBIT_ID, "Historical trading (M1)", "SEC-B", trading_cells or []),
        (MARGIN_EXHIBIT_ID, "Revenue and margin (M2)", "SEC-C", margin_cells or []),
        (COSTS_EXHIBIT_ID, "Costs and people (M3)", "SEC-D", costs_cells or []),
        (CASH_CONV_EXHIBIT_ID, "Cash conversion and capex (M7)", "SEC-I", cash_cells or []),
        (BS_EXHIBIT_ID, "Balance sheet (M8)", "SEC-F", bs_cells or []),
        (NWC_EXHIBIT_ID, "Net working capital (M5)", "SEC-G", nwc_cells or []),
        (NET_DEBT_EXHIBIT_ID, "Net debt and debt-like (M6)", "SEC-H", net_debt_cells or []),
    ]
    model_ids = {eid for eid, _, _, _ in batches}
    # Drop prior model exhibits entirely, then rewrite from this build.
    exhibits = [ex for ex in store.exhibits if ex.exhibit_id not in model_ids]
    for eid, title, sec, cells in batches:
        foot = list(dict.fromkeys(notes_by_exhibit.get(eid) or []))[:8]
        if not cells:
            # Omit empty model exhibits entirely — avoids "figures pending" on a
            # section that has a shell but no cells (and keeps exhibit counts honest).
            continue
        exhibits.append(
            Exhibit(
                exhibit_id=eid,
                title=title,
                section_id=sec,
                status=ArtefactStatus.CHECKED,
                cells=sorted(cells, key=lambda c: c.cell_id),
                footnotes=foot,
            )
        )
    exhibits.sort(key=lambda e: e.exhibit_id)
    return store.model_copy(update={"exhibits": exhibits})


def build_phase5b_exhibits(
    deal_slug: str,
    run_id: str,
    *,
    store: ExhibitStoreDoc | None = None,
    persist: bool = True,
) -> tuple[ExhibitStoreDoc, dict[str, Any]]:
    """Build M1/M2/M3/M7/M8/M5/M6 exhibits from facts (+ existing non-model store cells)."""
    store = store or load_or_empty(deal_slug, run_id)
    facts_doc = load_fact_table(deal_slug, run_id)
    scope = load_scope_profile(deal_slug, run_id)
    currency = scope.currency if scope else None
    scale = scope.scale if scope else None

    lines = _collapse_lines(_lines_from_facts(facts_doc.facts if facts_doc else []))
    # Prefer fact-table rows; store supplements only novel metric×year keys
    # (bridged REPORTED cells otherwise double-count the same figures).
    seen = {(_norm(ln.metric_key), int(ln.fiscal_year)) for ln in lines}
    for ln in _lines_from_store(store):
        key = (_norm(ln.metric_key), int(ln.fiscal_year))
        if key in seen:
            # Fact-table rows are authoritative after workbook>ledger prefer —
            # never let a stronger-status ledger store cell flip the basis.
            continue
        lines.append(ln)
        seen.add(key)
    lines = _collapse_lines(lines)

    years = _pick_years(lines, max_years=_TRADING_MAX_YEARS, prefer_closed=True)
    year = years[0] if years else _pick_year(lines, prefer_closed=True)
    trading_cells, trading_notes = build_trading_exhibit(
        lines, years=years or None, currency=currency, scale=scale
    )
    margin_cells, margin_notes = build_margin_exhibit(
        lines, years=years[:2] if years else None, currency=currency, scale=scale
    )
    costs_cells, costs_notes = build_costs_exhibit(
        lines, years=years[:2] if years else None, currency=currency, scale=scale
    )
    cash_cells, cash_notes = build_cash_conversion_exhibit(
        lines, year=year, currency=currency, scale=scale
    )
    bs_cells, bs_notes = build_balance_sheet_exhibit(
        lines, year=year, currency=currency, scale=scale
    )
    nwc_cells, nwc_notes = build_nwc_exhibit(
        lines, year=year, currency=currency, scale=scale
    )
    nd_cells, nd_notes = build_net_debt_exhibit(
        lines, year=year, currency=currency, scale=scale
    )
    notes_by_exhibit = {
        TRADING_EXHIBIT_ID: trading_notes,
        MARGIN_EXHIBIT_ID: margin_notes,
        COSTS_EXHIBIT_ID: costs_notes,
        CASH_CONV_EXHIBIT_ID: cash_notes,
        BS_EXHIBIT_ID: bs_notes,
        NWC_EXHIBIT_ID: nwc_notes,
        NET_DEBT_EXHIBIT_ID: nd_notes,
    }
    notes = [n for group in notes_by_exhibit.values() for n in group]
    store = apply_model_exhibits(
        store,
        trading_cells=trading_cells,
        margin_cells=margin_cells,
        costs_cells=costs_cells,
        cash_cells=cash_cells,
        bs_cells=bs_cells,
        nwc_cells=nwc_cells,
        net_debt_cells=nd_cells,
        notes_by_exhibit=notes_by_exhibit,
    )

    # G3 — automatic model check packs gate exhibit status before commentary.
    from agetic_cdd_api.services_fdd_checks import run_and_apply_g3

    store, g3_doc = run_and_apply_g3(
        deal_slug, run_id, store=store, persist=persist
    )
    if persist:
        store = persist_store(deal_slug, run_id, store)

    held = set(g3_doc.held_back_exhibits or [])
    summary = {
        "version": MODELS_VERSION,
        "year": year,
        "years": years,
        "trading_cells": len(trading_cells),
        "margin_cells": len(margin_cells),
        "costs_cells": len(costs_cells),
        "cash_cells": len(cash_cells),
        "bs_cells": len(bs_cells),
        "nwc_cells": len(nwc_cells),
        "net_debt_cells": len(nd_cells),
        "notes": notes,
        "g3_passed": g3_doc.g3_passed,
        "g3_held_exhibits": list(held),
        "sections": {
            "SEC-B": bool(trading_cells) and TRADING_EXHIBIT_ID not in held,
            "SEC-C": bool(margin_cells) and MARGIN_EXHIBIT_ID not in held,
            "SEC-D": bool(costs_cells) and COSTS_EXHIBIT_ID not in held,
            # Cash conversion requires OCF (EBITDA-only is not enough).
            "SEC-I": any(
                c.metric_key
                in {"operating_cash_flow", "free_cash_flow", "cash_conversion"}
                for c in cash_cells
            )
            and CASH_CONV_EXHIBIT_ID not in held,
            "SEC-F": bool(bs_cells) and BS_EXHIBIT_ID not in held,
            "SEC-G": bool(nwc_cells)
            and not any(n == "nwc_liabilities_missing" for n in nwc_notes)
            and NWC_EXHIBIT_ID not in held,
            "SEC-H": bool(nd_cells) and NET_DEBT_EXHIBIT_ID not in held,
        },
    }
    return store, summary


def ensure_phase5b_models(
    deal_slug: str,
    run_id: str,
    *,
    store: ExhibitStoreDoc | None = None,
    company: str | None = None,
    build_qoe: bool = True,
) -> tuple[ExhibitStoreDoc, dict[str, Any]]:
    """Ensure QoE (M4/SEC-E) + M1/M2/M3/M7/M8/M5/M6 exhibits exist for commentary.

    *company* reserved for future scope seeding; unused for now.
    """
    _ = company
    store = store or load_or_empty(deal_slug, run_id)
    summary: dict[str, Any] = {"qoe": False, "models": {}}

    if build_qoe:
        try:
            from agetic_cdd_api.services_fdd_commentary import sync_qoe_exhibit
            from agetic_cdd_api.services_fdd_qoe import build_qoe_workbook

            existing = load_qoe_workbook(deal_slug, run_id)
            # Rebuild seed QoE whenever the register is empty so EBITDA tracks
            # the same workbook-preferred fact table as M1 (no 0.57 vs 0.56 split).
            if (
                existing is None
                or existing.adjusted_ebitda_diligence is None
                or not (existing.register_rows or [])
            ):
                build_qoe_workbook(deal_slug, run_id, update_manifest=True)
            store = sync_qoe_exhibit(deal_slug, run_id, store=store)
            summary["qoe"] = True
        except Exception as err:
            logger.warning(
                "Phase 5b QoE ensure failed for %s/%s: %s",
                deal_slug,
                run_id,
                err,
                exc_info=True,
            )
            summary["qoe_error"] = str(err)

    store, model_summary = build_phase5b_exhibits(
        deal_slug, run_id, store=store, persist=True
    )
    summary["models"] = model_summary
    summary["g3_passed"] = bool(model_summary.get("g3_passed"))

    manifest = load_manifest(deal_slug, run_id)
    if manifest is not None:
        stage = manifest.stage
        if stage in {
            RunStage.P0,
            RunStage.P1,
            RunStage.P2,
            RunStage.P3,
            RunStage.P4,
        }:
            stage = RunStage.P5
        save_manifest(
            manifest.model_copy(
                update={
                    "stage": stage,
                    "models_built": True,
                    "g3_passed": bool(model_summary.get("g3_passed")),
                    "model_versions": {
                        **(manifest.model_versions or {}),
                        "fdd_models_5b": MODELS_VERSION,
                    },
                }
            )
        )
    return store, summary
