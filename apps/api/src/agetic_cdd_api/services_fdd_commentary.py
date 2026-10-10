"""FDD Phase 6 — section exhibits & tagged commentary (P6).

Implements PDF §6 / P6:
- Section drafts A–K + ES with sentence tags F/A/M/Q
- Numbers only as ``{{ex:…}}`` tokens (typed-figure ban)
- Fixed confidence vocabulary; no invest advice / superlatives
- Limitations for open items above materiality
"""

from __future__ import annotations

import re
from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CellStatus,
    CommentaryCheckResult,
    CommentaryDoc,
    CommentaryLimitation,
    CommentarySentence,
    DEFAULT_SECTIONS_IN_SCOPE,
    EvidenceTier,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    INVEST_ADVICE_FORBIDDEN,
    OPTIONAL_SECTIONS,
    QoeBridgePeriod,
    QoeWorkbookDoc,
    RunStage,
    SectionDraft,
    SUPERLATIVES_FORBIDDEN,
)
from agetic_cdd_api.services_fdd_exhibit import (
    cell_ref,
    index_cells,
    load_or_empty,
    persist_store,
    upsert_cells,
)
from agetic_cdd_api.services_fdd_store import (
    load_commentary,
    load_manifest,
    load_qoe_workbook,
    load_request_list,
    load_scope_profile,
    save_commentary,
    save_manifest,
)
from agetic_cdd_api.services_fdd_tokens import (
    assert_no_raw_numeric_literals,
    find_tokens,
    make_token,
    resolve_text,
)

COMMENTARY_VERSION = "0.2.3"  # QoE single reported line; SEC-K held-section digest

# Section blueprint: id → (title, diligence question, commentary focus)
SECTION_BLUEPRINT: dict[str, tuple[str, str, str]] = {
    "SEC-A": (
        "Scope, perimeter and basis",
        "What can the reader rely on?",
        "Scope table; basis of preparation; evidence tier; access limits",
    ),
    "SEC-B": (
        "Historical trading",
        "How has the business traded?",
        "Revenue and EBITDA trajectory from the databook",
    ),
    "SEC-C": (
        "Revenue and margin",
        "Where does margin come from?",
        "Mix, concentration and margin walks",
    ),
    "SEC-D": (
        "Costs and people",
        "What drives the cost base?",
        "Cost ratios and people metrics",
    ),
    "SEC-E": (
        "Quality of earnings",
        "What is sustainable earnings power?",
        "Bridge, walk, sensitivities and pro forma beside adjusted EBITDA",
    ),
    "SEC-F": (
        "Balance sheet and net assets",
        "What does the balance sheet show?",
        "NAV and material BS lines",
    ),
    "SEC-G": (
        "Net working capital",
        "What is a normal working-capital level?",
        "NWC components and peg candidates",
    ),
    "SEC-H": (
        "Net debt and debt-like items",
        "What is the debt-like claim on value?",
        "Net debt bridge and debt-like schedule",
    ),
    "SEC-I": (
        "Cash flow and capex",
        "How much cash does earnings convert to?",
        "Cash conversion and capex",
    ),
    "SEC-J": (
        "Forecast review",
        "Is the plan consistent with history?",
        "Bridge from last actual to plan (in-scope only)",
    ),
    "SEC-K": (
        "Key findings and completion",
        "What must be completed before release?",
        "Findings register and open items",
    ),
    "SEC-ES": (
        "Executive summary",
        "What must the IC know?",
        "Key financials and material open items — no new facts",
    ),
}

_TAG_LINE_RE = re.compile(r"^\[([FAMQ])\]\s*(.+)$")
# Causal phrasing is only allowed under Analysis (A) or Judgement (M) tags.
_BECAUSE_RE = re.compile(
    r"\b("
    r"because|driven by|attributable to|due to|as a result of|"
    r"owing to|on account of|stemming from|resulting from"
    r")\b",
    re.IGNORECASE,
)
QOE_EXHIBIT_ID = "ex_qoe_bridge"
# Keep in sync with services_fdd_models.* (avoid import cycle at module load).
TRADING_EXHIBIT_ID = "ex_m1_trading"
MARGIN_EXHIBIT_ID = "ex_m2_margin"
COSTS_EXHIBIT_ID = "ex_m3_costs"
CASH_CONV_EXHIBIT_ID = "ex_m7_cash"
BS_EXHIBIT_ID = "ex_m8_bs"
NWC_EXHIBIT_ID = "ex_m5_nwc"
_STUB_EXHIBIT_IDS = frozenset({"ex_hist_pl", "ex_hist_bs"})


class CommentaryValidationError(ValueError):
    """Invalid commentary payload or failed narrative checks."""


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _fmt(value: float | None) -> str:
    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    return format_fdd_number(value)


def prose_safe_label(text: str) -> str:
    """Strip digit runs that would trip the typed-figure ban (keep period/request labels).

    Used when injecting request titles / blocker strings into draft prose. Structured
    ``CommentaryLimitation.text`` may still hold the original title for UI display.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    cleaned = raw
    # Remove only the digit spans the typed-figure checker would flag (allowlist-aware).
    for fault in assert_no_raw_numeric_literals(cleaned):
        cleaned = cleaned.replace(fault, "", 1)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -–,;:")
    return cleaned or "open item"


def _primary_bridge_period(qoe: QoeWorkbookDoc) -> QoeBridgePeriod | None:
    """Headline bridge row: prefer the workbook period, else first bridge period.

    ``qoe.bridge`` is an ordered list of ``QoeBridgePeriod``; index 0 is the
    primary/headline row when no period match is found (single-period workbooks).
    """
    if not qoe.bridge:
        return None
    period = (qoe.period or "").strip()
    if period:
        for row in qoe.bridge:
            if (row.period or "").strip() == period:
                return row
    return qoe.bridge[0]


def sync_qoe_exhibit(
    deal_slug: str,
    run_id: str,
    store: ExhibitStoreDoc | None = None,
) -> ExhibitStoreDoc:
    """Bind QoE bridge figures into the exhibit store so commentary can tokenise them."""
    qoe = load_qoe_workbook(deal_slug, run_id)
    store = store or load_or_empty(deal_slug, run_id)
    if qoe is None or qoe.adjusted_ebitda_diligence is None:
        return store

    period = qoe.period or "FY25A"
    qoe_real = _qoe_has_real_adjustments(qoe)
    bridge_row = _primary_bridge_period(qoe)
    reported = (
        float(bridge_row.reported_ebitda)
        if bridge_row is not None and bridge_row.reported_ebitda is not None
        else float(qoe.adjusted_ebitda_diligence)
    )
    cells: list[ExhibitCell] = []
    if not qoe_real:
        # Empty register — one visible Reported EBITDA line only (no triple clone).
        specs: list[tuple[str, str, float | None]] = [
            ("reported_ebitda", "Reported EBITDA", reported),
        ]
    else:
        specs = [
            ("reported_ebitda", "Reported EBITDA (diligence)", reported),
            (
                "adj_ebitda_mgmt",
                "Adjusted EBITDA (management)",
                qoe.adjusted_ebitda_management,
            ),
            (
                "adj_ebitda_dil",
                "Adjusted EBITDA (diligence)",
                qoe.adjusted_ebitda_diligence,
            ),
            ("sens_low", "Sensitivity low", qoe.sensitivity_low),
            ("sens_high", "Sensitivity high", qoe.sensitivity_high),
            ("pro_forma_ebitda", "Pro forma EBITDA", qoe.pro_forma_ebitda),
            ("materiality_m", "Materiality M", qoe.materiality_m),
        ]

    for cell_id, label, value in specs:
        if value is None:
            continue
        cells.append(
            ExhibitCell(
                cell_id=cell_id,
                exhibit_id=QOE_EXHIBIT_ID,
                label=label,
                value=float(value),
                display=_fmt(value),
                unit=qoe.scale,
                currency=qoe.currency,
                scale=qoe.scale,
                metric_key=cell_id,
                fact_id=f"qoe:{run_id}:{cell_id}",
                figure_type=FigureType.CALCULATED,
                evidence_tier=EvidenceTier.B,
                status=CellStatus.PROVEN if qoe.g4_approved else CellStatus.DRAFT,
                basis_label=f"QoE {qoe.version} · {period}",
                model_id="M4",
                model_version=qoe.version,
            )
        )
    if not cells:
        return store

    store = upsert_cells(
        store,
        cells,
        exhibit_titles={
            QOE_EXHIBIT_ID: (
                f"Reported EBITDA ({period})"
                if not qoe_real
                else f"QoE bridge ({period})"
            )
        },
        section_ids={QOE_EXHIBIT_ID: "SEC-E"},
    )
    # upsert merges — drop stale Adjusted / Pro forma shells when register empty.
    if not qoe_real:
        keep_ids = {c.cell_id for c in cells}
        revised: list = []
        for ex in store.exhibits:
            if ex.exhibit_id != QOE_EXHIBIT_ID:
                revised.append(ex)
                continue
            revised.append(
                ex.model_copy(
                    update={
                        "cells": [c for c in (ex.cells or []) if c.cell_id in keep_ids]
                    }
                )
            )
        store = store.model_copy(update={"exhibits": revised})
    return persist_store(deal_slug, run_id, store)


def _sentence(tag: str, text: str, citation: str | None = None) -> CommentarySentence:
    """Build a tagged sentence. F/A/M require a non-empty citation (P6 audit rule)."""
    if tag in {"F", "A", "M"} and not (citation or "").strip():
        raise CommentaryValidationError(
            f"Tag {tag} sentence requires a citation (exhibit / document / request id)"
        )
    return CommentarySentence(tag=tag, text=text, citation=citation)  # type: ignore[arg-type]


def _join_body(sentences: list[CommentarySentence]) -> str:
    return "\n".join(f"[{s.tag}] {s.text}" for s in sentences)


def _exhibits_for_section(store: ExhibitStoreDoc, section_id: str) -> list[str]:
    return [
        ex.exhibit_id
        for ex in store.exhibits
        if (ex.section_id or "") == section_id or section_id == "SEC-ES"
    ]


# Prefer earnings / trading anchors for headlines; deprioritize SaaS retention KPIs.
_HEADLINE_METRIC_PREF = (
    "adj_ebitda_dil",
    "adj_ebitda_mgmt",
    "adj_ebitda",
    "adjusted_ebitda",
    "ebitda",
    "operating_profit",
    "revenue",
    "gross_profit",
)
# SEC-B historical trading leads with revenue trajectory, then earnings.
_TRADING_METRIC_PREF = (
    "revenue",
    "ebitda",
    "operating_profit",
    "gross_profit",
    "net_income",
    "revenue_yoy",
    "ebitda_yoy",
)
# SEC-I cash conversion leads with conversion %, then FCF / OCF.
_CASH_METRIC_PREF = (
    "cash_conversion",
    "free_cash_flow",
    "operating_cash_flow",
    "fcf_conversion",
    "capex",
)
# SEC-C revenue & margin walk — GM% / Δpp, then revenue / EBITDA margin.
_MARGIN_METRIC_PREF = (
    "gross_margin",
    "gross_margin_delta_pp",
    "ebitda_margin",
    "ebitda_margin_delta_pp",
    "revenue",
    "revenue_yoy",
    "gross_profit",
    "top_customer_pct",
)
# SEC-D costs and people — SG&A / ratios, then COGS / labour / headcount.
_COSTS_METRIC_PREF = (
    "sga",
    "sga_pct_revenue",
    "cogs",
    "cogs_pct_revenue",
    "labor_cost",
    "labor_pct_revenue",
    "headcount",
    "revenue_per_head",
    "sga_yoy",
    "cogs_yoy",
)
_HEADLINE_METRIC_AVOID = (
    "grr",
    "nrr",
    "retention",
    "churn",
    "logo_retention",
    "gross_revenue_retention",
    "net_revenue_retention",
)
_FORECAST_MARKERS = (
    "forecast",
    "plan",
    "budget",
    "projection",
    "projected",
    "outlook",
    "target",
)
_ADJUSTED_METRIC_KEYS = frozenset(
    {
        "adj_ebitda_dil",
        "adj_ebitda_mgmt",
        "adj_ebitda",
        "adjusted_ebitda",
    }
)


def _headline_year_cutoff() -> int:
    """Latest fiscal year treated as *closed* historical for IC headlines.

    Always prior calendar year. In-year figures (e.g. FY2026 while the report
    date is Oct 2026 with YTD ledgers only) are management plan / stub, not
    closed actuals — even when the databook tags them proven.
    """
    from datetime import date

    return date.today().year - 1


def _period_tier(cell: ExhibitCell) -> int:
    """0 = closed historical, 1 = unknown year, 2 = in-year or outer plan/forecast."""
    blob = " ".join(
        str(x or "")
        for x in (
            cell.metric_key,
            cell.cell_id,
            cell.label,
            cell.basis_label,
            getattr(cell.labels, "basis", None) if cell.labels else None,
        )
    ).lower()
    if any(m in blob.replace(" ", "_") for m in _FORECAST_MARKERS):
        return 2
    year = int(cell.fiscal_year or 0)
    if year <= 0:
        return 1
    cutoff = _headline_year_cutoff()
    if year > cutoff:
        # Current calendar FY and later = not closed (plan / stub / forecast)
        return 2
    return 0  # year <= cutoff → closed historical


def _metric_pref_index(cell: ExhibitCell) -> int | None:
    blob = f"{cell.metric_key or ''} {cell.cell_id or ''}".lower().replace(" ", "_")
    mk = (cell.metric_key or "").lower().replace(" ", "_")
    cid = (cell.cell_id or "").lower()
    if any(a in blob for a in _HEADLINE_METRIC_AVOID):
        return None
    for i, pref in enumerate(_HEADLINE_METRIC_PREF):
        if mk == pref or cid == pref or cid.startswith(f"{pref}_"):
            return i
        if pref not in {"revenue", "gross_profit"} and pref in blob:
            return i
        if pref == "revenue" and (
            mk == "revenue"
            or cid.startswith("revenue_")
            or re.search(r"(^|_)revenue(_|$)", blob)
        ):
            return i
    return None


def _headline_metric_rank(cell: ExhibitCell) -> tuple[int, int, int, int, str]:
    """Rank: avoid → period (hist≺forecast) → metric pref → latest year within tier."""
    year = int(cell.fiscal_year or 0)
    year_key = -year  # within the same period tier, prefer the latest actual
    pref_i = _metric_pref_index(cell)
    if pref_i is None and any(
        a in f"{cell.metric_key or ''} {cell.cell_id or ''}".lower().replace(" ", "_")
        for a in _HEADLINE_METRIC_AVOID
    ):
        return (2, 99, 99, year_key, cell.cell_id)
    if pref_i is None:
        return (1, _period_tier(cell), 50, year_key, cell.cell_id)
    return (0, _period_tier(cell), pref_i, year_key, cell.cell_id)


def _qoe_has_real_adjustments(qoe: QoeWorkbookDoc | None) -> bool:
    """True only when the register moves adjusted EBITDA off reported."""
    if qoe is None:
        return False
    register = qoe.register_rows or []
    if not register:
        return False
    bridge = _primary_bridge_period(qoe)
    reported = bridge.reported_ebitda if bridge else None
    adj = qoe.adjusted_ebitda_diligence
    if reported is None or adj is None:
        return bool(register)
    try:
        return abs(float(adj) - float(reported)) > 1e-6
    except (TypeError, ValueError):
        return bool(register)


def _ebitda_basis_sentence(
    deal_slug: str,
    run_id: str,
    store: ExhibitStoreDoc,
) -> CommentarySentence | None:
    """One-line note: report uses investor-workbook EBITDA (via exhibit token)."""
    from agetic_cdd_api.services_fdd_sources import classify_source, display_source_name
    from agetic_cdd_api.services_fdd_store import load_fact_table

    tok, ref, cell = _first_cell_token(
        store,
        [TRADING_EXHIBIT_ID, "ex_db_is", QOE_EXHIBIT_ID],
        prefer=_prefer_metric_ref(
            store, [TRADING_EXHIBIT_ID, "ex_db_is"], "ebitda", historical_only=True
        ),
        historical_only=True,
    )
    if tok is None or cell is None:
        return None
    src = "investor workbook"
    facts = load_fact_table(deal_slug, run_id)
    if facts:
        year = int(cell.fiscal_year or 0)
        for f in facts.facts:
            if (
                f.metric_key == "ebitda"
                and f.value is not None
                and int(f.fiscal_year or 0) == year
            ):
                kind = classify_source(
                    f.sources, f.labels.source if f.labels else None
                )
                src = display_source_name(kind, f.sources)
                break
    # Use the exhibit token only — never type raw decimals into prose (P6 ban).
    return _sentence(
        "A",
        f"EBITDA basis is the {src}; closed-year figure is {tok}.",
        citation=ref or cell_ref(cell.exhibit_id, cell.cell_id),
    )


def _is_adjusted_earnings_cell(cell: ExhibitCell | None) -> bool:
    if cell is None:
        return False
    mk = (cell.metric_key or "").lower().replace(" ", "_")
    cid = (cell.cell_id or "").lower()
    if mk in _ADJUSTED_METRIC_KEYS or cid in _ADJUSTED_METRIC_KEYS:
        return True
    return cell.exhibit_id == QOE_EXHIBIT_ID and "adj_ebitda" in cid


def _period_unit_label(cell: ExhibitCell | None) -> tuple[str, str]:
    if cell is None:
        return ("", "")
    from agetic_cdd_api.services_fdd_tokens import display_unit_for_cell

    period = f"FY{cell.fiscal_year}" if cell.fiscal_year else ""
    return period, display_unit_for_cell(cell)


def _headline_metric_name(cell: ExhibitCell | None) -> str:
    """Short metric label for action titles — never re-state FY (period is separate)."""
    if cell is None:
        return "figure"
    mk = (cell.metric_key or cell.cell_id or "figure").lower().replace(" ", "_")
    if mk == "gross_margin_delta_pp" or (
        mk.endswith("_delta_pp") and "gross_margin" in mk
    ):
        return "gross margin change"
    if mk == "ebitda_margin_delta_pp" or (
        mk.endswith("_delta_pp") and "ebitda_margin" in mk
    ):
        return "EBITDA margin change"
    if mk.endswith("_delta_pp"):
        return "margin change"
    if mk == "gross_margin" or mk.startswith("gross_margin_"):
        return "gross margin"
    if mk == "ebitda_margin" or mk.startswith("ebitda_margin_"):
        return "EBITDA margin"
    if mk in {"cash_conversion", "fcf_conversion"}:
        return "cash conversion"
    if mk in {"free_cash_flow", "fcf"}:
        return "free cash flow"
    if mk in {"operating_cash_flow", "ocf", "cfo"}:
        return "operating cash flow"
    if mk == "capex":
        return "capex"
    if mk == "nwc" or mk.startswith("nwc_"):
        return "net working capital"
    if mk in {"cogs", "cost_of_sales"}:
        return "cost of sales"
    if mk in {"sga", "operating_costs", "operating_expenses"}:
        return "SG&A"
    if mk in {"labor_cost", "labour_cost"}:
        return "labour"
    if mk in {"cogs_pct_revenue", "sga_pct_revenue", "labor_pct_revenue"}:
        return (cell.label or mk).split(" FY")[0].strip() or mk
    if mk == "revenue" or mk.startswith("revenue_"):
        return "revenue"
    if "ebitda" in mk or "operating_profit" in mk:
        return "EBITDA"
    if mk in {"total_assets", "net_assets", "nav", "total_equity", "cash"}:
        label = (cell.label or mk).strip()
        # Strip trailing "FY2025" so period is not doubled in the phrase.
        label = re.sub(r"\s*FY20\d{2}\s*$", "", label, flags=re.I).strip()
        return label or mk
    label = (cell.label or cell.metric_key or "figure").strip()
    label = re.sub(r"\s*FY20\d{2}\s*$", "", label, flags=re.I).strip()
    return label or "figure"


def _headline_figure_phrase(
    token: str,
    cell: ExhibitCell | None,
    *,
    qoe_pending: bool,
    treat_as_adjusted: bool | None = None,
) -> str:
    """Labelled figure: 'FY2025 EBITDA 0.57 (USD M), unadjusted — QoE pending'."""
    period, unit = _period_unit_label(cell)
    mk = (cell.metric_key or cell.cell_id or "figure").lower().replace(" ", "_") if cell else "figure"
    metric = _headline_metric_name(cell)
    bits = [b for b in (period, metric, token) if b]
    core = " ".join(bits)
    if unit:
        core = f"{core} ({unit})"
    is_adj = (
        treat_as_adjusted
        if treat_as_adjusted is not None
        else _is_adjusted_earnings_cell(cell)
    )
    if is_adj and not qoe_pending:
        return f"adjusted {core}"
    if qoe_pending and ("ebitda" in mk or is_adj):
        return f"{core}, unadjusted — QoE pending"
    return core


def _prefer_metric_ref(
    store: ExhibitStoreDoc,
    exhibit_ids: list[str],
    metric_key: str,
    *,
    historical_only: bool = True,
) -> str | None:
    """Latest matching cell_ref for *metric_key* within *exhibit_ids*."""
    idx = index_cells(store)
    allowed = set(exhibit_ids)
    want = metric_key.lower().replace(" ", "_")
    candidates: list[tuple[int, str]] = []
    for ref, cell in idx.items():
        if cell.exhibit_id not in allowed or cell.value is None:
            continue
        if historical_only and _period_tier(cell) >= 2:
            continue
        mk = (cell.metric_key or "").lower().replace(" ", "_")
        cid = (cell.cell_id or "").lower()
        if mk != want and not cid.startswith(f"{want}_") and cid != want:
            continue
        year = int(cell.fiscal_year or 0)
        candidates.append((-year, ref))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _prefer_trading_anchor(
    store: ExhibitStoreDoc, exhibit_ids: list[str]
) -> str | None:
    """Best cell_ref for SEC-B — closed-year revenue, else EBITDA, from M1/IS."""
    for pref in _TRADING_METRIC_PREF:
        hit = _prefer_metric_ref(store, exhibit_ids, pref, historical_only=True)
        if hit:
            return hit
    return None


def _prefer_cash_anchor(
    store: ExhibitStoreDoc, exhibit_ids: list[str]
) -> str | None:
    """Best cell_ref for SEC-I — conversion %, FCF, or OCF from M7/CF."""
    for pref in _CASH_METRIC_PREF:
        hit = _prefer_metric_ref(store, exhibit_ids, pref, historical_only=True)
        if hit:
            return hit
    return None


def _prefer_margin_anchor(
    store: ExhibitStoreDoc, exhibit_ids: list[str]
) -> str | None:
    """Best cell_ref for SEC-C — GM% / Δpp from M2 (falls back to M1)."""
    for pref in _MARGIN_METRIC_PREF:
        hit = _prefer_metric_ref(store, exhibit_ids, pref, historical_only=True)
        if hit:
            return hit
    return None


def _prefer_costs_anchor(
    store: ExhibitStoreDoc, exhibit_ids: list[str]
) -> str | None:
    """Best cell_ref for SEC-D — SG&A / cost ratios from M3 (falls back to db)."""
    for pref in _COSTS_METRIC_PREF:
        hit = _prefer_metric_ref(store, exhibit_ids, pref, historical_only=True)
        if hit:
            return hit
    return None


_BS_METRIC_PREF = (
    "total_assets",
    "net_assets",
    "nav",
    "total_equity",
    "cash",
    "total_liabilities",
    "current_assets",
    "current_liabilities",
)


def _prefer_bs_anchor(
    store: ExhibitStoreDoc, exhibit_ids: list[str]
) -> str | None:
    """Best cell_ref for SEC-F — real BS lines, never P&L margins or phase-0 stubs."""
    real_ids = [e for e in exhibit_ids if e not in _STUB_EXHIBIT_IDS]
    if not real_ids:
        return None
    for pref in _BS_METRIC_PREF:
        hit = _prefer_metric_ref(store, real_ids, pref, historical_only=True)
        if hit:
            return hit
    return None


def _first_cell_token(
    store: ExhibitStoreDoc,
    exhibit_ids: list[str],
    *,
    prefer: str | None = None,
    historical_only: bool = False,
) -> tuple[str | None, str | None, ExhibitCell | None]:
    """Return ``({{ex:…}}, cell_ref, cell)`` from *exhibit_ids only*.

    Prefers historical earnings/revenue over retention KPIs and outer-year forecasts.
    """
    idx = index_cells(store)
    allowed = set(exhibit_ids)
    if not allowed:
        return None, None, None
    if prefer and prefer in idx:
        cell = idx[prefer]
        if cell.exhibit_id in allowed and cell.value is not None:
            if not historical_only or _period_tier(cell) < 2:
                return make_token(cell.exhibit_id, cell.cell_id), prefer, cell

    candidates: list[tuple[tuple, str, ExhibitCell]] = []
    for eid in exhibit_ids:
        for ref, cell in idx.items():
            if cell.exhibit_id != eid or cell.value is None:
                continue
            if historical_only and _period_tier(cell) >= 2:
                continue
            candidates.append((_headline_metric_rank(cell), ref, cell))
    if not candidates and historical_only:
        # Fall back to all periods if no historical cells exist
        return _first_cell_token(
            store, exhibit_ids, prefer=prefer, historical_only=False
        )
    if not candidates:
        return None, None, None
    candidates.sort(key=lambda t: (t[0], t[1]))
    _rank, ref, cell = candidates[0]
    return make_token(cell.exhibit_id, cell.cell_id), ref, cell


_GAP_SECTIONS_FULL = frozenset({"SEC-K"})
_GAP_SECTIONS_POINTER = frozenset({"SEC-B", "SEC-C", "SEC-E", "SEC-ES"})
_GAP_POINTER_ID = "gap:reconciliation:sec-k"


def _collect_source_gaps(
    deal_slug: str,
    run_id: str,
) -> list[CommentaryLimitation]:
    """Canonical cross-source gaps (workbook figure first, one line per metric×year).

    Skips incomplete / current fiscal years — YTD pack months must not be
    compared to full-year workbook plans.
    """
    from datetime import date

    from agetic_cdd_api.services_fdd_sources import (
        classify_source,
        display_source_name,
    )
    from agetic_cdd_api.services_fdd_store import load_claims_ledger, load_fact_table

    facts = load_fact_table(deal_slug, run_id)
    out: list[CommentaryLimitation] = []
    seen: set[str] = set()
    closed_cutoff = date.today().year - 1

    def _emit_pair(
        *,
        metric_key: str,
        fiscal_year: int,
        left_v: float,
        left_src: str,
        right_v: float,
        right_src: str,
    ) -> None:
        if int(fiscal_year) > closed_cutoff:
            return
        gap = abs(left_v - right_v)
        if gap < 0.001:
            return
        key = f"gap:{metric_key}:{fiscal_year}"
        if key in seen:
            return
        seen.add(key)
        # Prefer workbook-first, then monthly pack, then ledger.
        left_l, right_l = left_src.lower(), right_src.lower()
        if "workbook" in right_l and "workbook" not in left_l:
            left_v, right_v = right_v, left_v
            left_src, right_src = right_src, left_src
        out.append(
            CommentaryLimitation(
                item_id=key,
                text=(
                    f"FY{fiscal_year} {metric_key.replace('_', ' ')}: "
                    f"{left_src} {left_v:.3f} vs {right_src} {right_v:.3f} "
                    f"— gap {gap:.3f}"
                ),
                above_materiality=True,
            )
        )

    if facts:
        for f in facts.facts:
            if f.metric_key not in {"revenue", "ebitda", "gross_profit"}:
                continue
            if f.value is None or not (f.alternatives or []):
                continue
            if int(f.fiscal_year) > closed_cutoff:
                continue
            # Skip YTD / stub periods stamped on the fact.
            plen = (f.period_length or "").upper() if hasattr(f, "period_length") else ""
            if not plen and f.labels is not None:
                plen = str(getattr(f.labels, "period_length", "") or "").upper()
            if plen == "YTD":
                continue
            primary_kind = classify_source(
                f.sources, f.labels.source if f.labels else None
            )
            primary_src = display_source_name(primary_kind, f.sources)
            best: tuple[float, float, str] | None = None
            for alt in f.alternatives:
                if not isinstance(alt, dict):
                    continue
                try:
                    alt_v = (
                        float(alt["value"]) if alt.get("value") is not None else None
                    )
                except (TypeError, ValueError):
                    alt_v = None
                if alt_v is None:
                    continue
                gap = abs(alt_v - float(f.value))
                if gap < 0.001:
                    continue
                raw_kind = str(alt.get("source_kind") or "").lower()
                alt_kind = (
                    raw_kind
                    if raw_kind in {"workbook", "ledger", "management", "unknown"}
                    else classify_source(alt.get("sources"), alt.get("captions"))
                )
                alt_src = display_source_name(alt_kind, alt.get("sources"))
                if best is None or gap > best[0]:
                    best = (gap, alt_v, alt_src)
            if best is None:
                continue
            _gap, alt_v, alt_src = best
            _emit_pair(
                metric_key=f.metric_key,
                fiscal_year=int(f.fiscal_year),
                left_v=float(f.value),
                left_src=primary_src,
                right_v=alt_v,
                right_src=alt_src,
            )

    claims = load_claims_ledger(deal_slug, run_id)
    if claims:
        from agetic_cdd_api.services_fdd_claims import _claim_source_label

        for claim in claims.claims:
            if claim.kind != "financial" or claim.test_result != "contradicted":
                continue
            if claim.metric_key not in {"revenue", "ebitda", "gross_profit"}:
                continue
            if (
                claim.claimed_value is None
                or claim.databook_value is None
                or claim.fiscal_year is None
            ):
                continue
            if int(claim.fiscal_year) > closed_cutoff:
                continue
            db_src = display_source_name(
                classify_source(getattr(claim, "databook_sources", None)),
                getattr(claim, "databook_sources", None),
            )
            # Fall back: databook side is usually the release/workbook figure.
            if db_src == "alternate source":
                db_src = "investor workbook"
            _emit_pair(
                metric_key=claim.metric_key,
                fiscal_year=int(claim.fiscal_year),
                left_v=float(claim.databook_value),
                left_src=db_src,
                right_v=float(claim.claimed_value),
                right_src=_claim_source_label(claim),
            )

    out.sort(key=lambda lim: lim.item_id)
    return out


def _source_gap_limitations(
    deal_slug: str,
    run_id: str,
    *,
    section_id: str,
) -> list[CommentaryLimitation]:
    """Full reconciliation only on SEC-K; other pages get a one-line pointer."""
    if section_id not in _GAP_SECTIONS_FULL | _GAP_SECTIONS_POINTER:
        return []
    gaps = _collect_source_gaps(deal_slug, run_id)
    if not gaps:
        return []
    if section_id in _GAP_SECTIONS_FULL:
        return gaps
    return [
        CommentaryLimitation(
            item_id=_GAP_POINTER_ID,
            text=(
                f"Investor workbook vs QBO ledger: {len(gaps)} figure gap(s) — "
                f"full reconciliation under Key findings (SEC-K)."
            ),
            above_materiality=True,
        )
    ]


def _claim_title_duplicates_gap(title: str, gap_keys: set[str]) -> bool:
    """True when a request-list title restates an already-listed gap:metric:year."""
    title_l = (title or "").lower().replace("_", " ")
    if " vs " not in title_l and "gap " not in title_l:
        return False
    for gk in gap_keys:
        parts = gk.split(":")
        if len(parts) != 3:
            continue
        metric = parts[1].replace("_", " ")
        year = parts[2]
        if metric in title_l and year in title_l:
            return True
    return False


def _request_title_is_open_year(title: str, closed_cutoff: int) -> bool:
    """True for claim/gap titles that cite a fiscal year after the last closed year."""
    import re

    title_l = (title or "").lower()
    if "ytd" in title_l:
        return True
    if " vs " not in title_l and "(contradicted)" not in title_l:
        return False
    for match in re.finditer(r"\bfy\s*(20\d{2})\b", title_l):
        if int(match.group(1)) > closed_cutoff:
            return True
    return False


def _request_title_is_readiness_scaffold(title: str) -> bool:
    """True for IN-1 scaffolding (not a diligence finding the reader can act on)."""
    title_l = (title or "").lower().strip()
    scaffolds = (
        "approved databook release",
        "specialist models m1",
        "agent leads",
        "house template",
        "engagement brief",
        "vdr / data room",
        "management answers",
    )
    if any(s in title_l for s in scaffolds):
        return True
    if title_l.startswith("improve ") or title_l.startswith("provide "):
        # Readiness verbs + input labels — not figure gaps.
        return any(s in title_l for s in scaffolds) or "databook" in title_l
    return False


def _material_limitations(
    deal_slug: str,
    run_id: str,
    *,
    section_id: str,
) -> list[CommentaryLimitation]:
    """Open items above materiality (request list + QoE blockers + source gaps)."""
    out: list[CommentaryLimitation] = []
    all_gaps = _collect_source_gaps(deal_slug, run_id)
    all_gap_keys = {
        lim.item_id for lim in all_gaps if (lim.item_id or "").startswith("gap:")
    }
    if section_id in _GAP_SECTIONS_FULL:
        out.extend(all_gaps)
    elif section_id in _GAP_SECTIONS_POINTER and all_gaps:
        out.extend(
            [
                CommentaryLimitation(
                    item_id=_GAP_POINTER_ID,
                    text=(
                        f"Investor workbook vs QBO ledger: {len(all_gaps)} figure "
                        f"gap(s) — full reconciliation under Key findings (SEC-K)."
                    ),
                    above_materiality=True,
                )
            ]
        )
    from datetime import date

    closed_cutoff = date.today().year - 1
    req = load_request_list(deal_slug, run_id)
    qoe = load_qoe_workbook(deal_slug, run_id)
    m = qoe.materiality_m if qoe else None
    if req:
        for item in req.items:
            if item.status in {"received", "waived"}:
                continue
            title = item.title or ""
            # Skip YTD / open-year claim restatements (pack months ≠ full-year plan).
            if _request_title_is_open_year(title, closed_cutoff):
                continue
            # Skip readiness IN-1 scaffolding ("Improve Approved databook release").
            if _request_title_is_readiness_scaffold(title):
                continue
            # Never restate workbook↔ledger gaps outside SEC-K (pointer covers them).
            if _claim_title_duplicates_gap(title, all_gap_keys):
                if section_id not in _GAP_SECTIONS_FULL:
                    continue
                # On SEC-K the canonical gap: lines already cover these.
                continue
            blocking = set(item.blocking_sections or [])
            relevant = (
                not blocking
                or section_id in blocking
                or section_id in {"SEC-A", "SEC-ES", "SEC-K"}
            )
            if not relevant:
                continue
            out.append(
                CommentaryLimitation(
                    item_id=item.request_id,
                    text=title,
                    above_materiality=m is not None or bool(blocking),
                )
            )
    if qoe and section_id in {"SEC-E", "SEC-ES", "SEC-K"}:
        for b in qoe.g4_blockers:
            out.append(
                CommentaryLimitation(
                    item_id=f"qoe:{b}",
                    text=f"QoE open judgement: {b}",
                    above_materiality=True,
                )
            )
    return out


def _limitation_sentence_text(lim: CommentaryLimitation) -> str:
    """Prose form for a limitation — no raw request ids in client-facing text."""
    text = (lim.text or "").strip()
    if (lim.item_id or "").startswith("gap:") or "gap " in text.lower():
        return text if text.endswith(".") else f"{text}."
    # Claim / contradiction titles already carry size — quote them directly.
    if " vs " in text.lower() or "(contradicted)" in text.lower() or "(unverifiable)" in text.lower():
        return text if text.endswith(".") else f"{text}."
    label = prose_safe_label(text)
    if label and label.lower() not in {lim.item_id.lower(), "open item"}:
        return f"Open diligence item remains: {label}."
    return "An open diligence item remains pending coverage."


def draft_section(
    section_id: str,
    *,
    deal_slug: str,
    run_id: str,
    store: ExhibitStoreDoc,
    company: str | None = None,
) -> SectionDraft:
    """Deterministic template writer for one section (LLM-ready structure)."""
    meta = SECTION_BLUEPRINT.get(section_id)
    if meta is None:
        return SectionDraft(
            section_id=section_id,
            title=section_id,
            held_back=True,
            held_back_reason="Unknown section id",
            checks_passed=False,
            checks=[
                CommentaryCheckResult(
                    check_id="unknown_section",
                    passed=False,
                    message=f"No blueprint for {section_id}",
                    blocking=True,
                )
            ],
        )

    title, question, focus = meta
    exhibit_ids = _exhibits_for_section(store, section_id)
    # Executive summary may pull from any exhibit
    if section_id == "SEC-ES":
        exhibit_ids = [ex.exhibit_id for ex in store.exhibits]
    have_ids = {ex.exhibit_id for ex in store.exhibits}

    def _g3_block_for(eid: str) -> str | None:
        from agetic_cdd_api.services_fdd_checks import G3_HELD_PREFIX, g3_hold_reason

        ex = next((e for e in store.exhibits if e.exhibit_id == eid), None)
        if ex is None:
            return None
        reason = g3_hold_reason(ex)
        if reason:
            return reason
        # Also treat DRAFT model exhibits with any g3 footnote remnant.
        for fn in ex.footnotes or []:
            if str(fn).startswith(G3_HELD_PREFIX):
                return str(fn)[len(G3_HELD_PREFIX) :] or "model checks failed"
        return None
    # Historical trading: prefer the M1 workbook when present
    if section_id == "SEC-B":
        if TRADING_EXHIBIT_ID in have_ids:
            exhibit_ids = [TRADING_EXHIBIT_ID] + [
                e for e in exhibit_ids if e != TRADING_EXHIBIT_ID
            ]
        elif "ex_db_is" in have_ids and "ex_db_is" not in exhibit_ids:
            exhibit_ids = ["ex_db_is", *exhibit_ids]
    # Revenue & margin: prefer M2 workbook when present
    if section_id == "SEC-C":
        if MARGIN_EXHIBIT_ID in have_ids:
            exhibit_ids = [MARGIN_EXHIBIT_ID] + [
                e for e in exhibit_ids if e != MARGIN_EXHIBIT_ID
            ]
        elif TRADING_EXHIBIT_ID in have_ids and TRADING_EXHIBIT_ID not in exhibit_ids:
            exhibit_ids = [TRADING_EXHIBIT_ID, *exhibit_ids]
    # Cash conversion: prefer M7 workbook when present
    if section_id == "SEC-I":
        if CASH_CONV_EXHIBIT_ID in have_ids:
            exhibit_ids = [CASH_CONV_EXHIBIT_ID] + [
                e for e in exhibit_ids if e != CASH_CONV_EXHIBIT_ID
            ]
        elif "ex_db_cf" in have_ids and "ex_db_cf" not in exhibit_ids:
            exhibit_ids = ["ex_db_cf", *exhibit_ids]
    if section_id == "SEC-F":
        if BS_EXHIBIT_ID in have_ids:
            exhibit_ids = [BS_EXHIBIT_ID] + [
                e for e in exhibit_ids if e != BS_EXHIBIT_ID
            ]
        elif "ex_db_bs" in have_ids and "ex_db_bs" not in exhibit_ids:
            exhibit_ids = ["ex_db_bs", *exhibit_ids]
    if section_id == "SEC-G":
        if NWC_EXHIBIT_ID in have_ids:
            exhibit_ids = [NWC_EXHIBIT_ID] + [
                e for e in exhibit_ids if e != NWC_EXHIBIT_ID
            ]
    if section_id == "SEC-D":
        if COSTS_EXHIBIT_ID in have_ids:
            exhibit_ids = [COSTS_EXHIBIT_ID] + [
                e for e in exhibit_ids if e != COSTS_EXHIBIT_ID
            ]
        elif "ex_db_costs" in have_ids and "ex_db_costs" not in exhibit_ids:
            exhibit_ids = ["ex_db_costs", *exhibit_ids]

    # G3 — if the preferred model exhibit failed check packs, hold the section.
    _MODEL_SEC_PREF = {
        "SEC-B": TRADING_EXHIBIT_ID,
        "SEC-C": MARGIN_EXHIBIT_ID,
        "SEC-D": COSTS_EXHIBIT_ID,
        "SEC-F": BS_EXHIBIT_ID,
        "SEC-G": NWC_EXHIBIT_ID,
        "SEC-H": "ex_m6_net_debt",
        "SEC-I": CASH_CONV_EXHIBIT_ID,
    }
    g3_pref = _MODEL_SEC_PREF.get(section_id)
    g3_reason = _g3_block_for(g3_pref) if g3_pref else None

    limitations = _material_limitations(deal_slug, run_id, section_id=section_id)
    scope = load_scope_profile(deal_slug, run_id)
    qoe = load_qoe_workbook(deal_slug, run_id)
    name = company or deal_slug
    qoe_real = _qoe_has_real_adjustments(qoe)
    # Seed-only QoE (empty register, adj == reported) stays "pending".
    qoe_pending = qoe is None or not getattr(qoe, "g4_approved", False) or not qoe_real

    sentences: list[CommentarySentence] = []
    cell_refs: list[str] = []
    held_back = False
    held_reason: str | None = None

    if g3_reason:
        cite = g3_pref or (exhibit_ids[0] if exhibit_ids else section_id)
        g3_sentences = [
            _sentence(
                "Q",
                f"{title} is held back — model checks failed: {g3_reason}.",
                citation=cite,
            )
        ]
        return validate_section_draft(
            SectionDraft(
                section_id=section_id,
                title=title,
                diligence_question=question,
                action_title=f"{title} held (G3)",
                exhibit_ids=list(dict.fromkeys(exhibit_ids)),
                cell_refs=[],
                sentences=g3_sentences,
                body=_join_body(g3_sentences),
                tags_used=["Q"],
                held_back=True,
                held_back_reason=f"G3: {g3_reason}",
            ),
            store,
        )

    # Prefer QoE adjusted EBITDA for SEC-E / ES only when real adjustments exist.
    prefer_ref = None
    if (
        section_id in {"SEC-E", "SEC-ES"}
        and qoe_real
        and QOE_EXHIBIT_ID in {ex.exhibit_id for ex in store.exhibits}
    ):
        prefer_ref = cell_ref(QOE_EXHIBIT_ID, "adj_ebitda_dil")
    elif section_id in {"SEC-E", "SEC-ES"} and not qoe_real:
        # Fall back to reported / trading EBITDA until adjustments exist.
        prefer_ref = (
            cell_ref(QOE_EXHIBIT_ID, "reported_ebitda")
            if QOE_EXHIBIT_ID in {ex.exhibit_id for ex in store.exhibits}
            else _prefer_trading_anchor(
                store,
                [TRADING_EXHIBIT_ID, "ex_db_is", *exhibit_ids],
            )
        )
        # Prefer EBITDA over revenue for the ES/QoE headline when pending.
        ebitda_pref = _prefer_metric_ref(
            store,
            [TRADING_EXHIBIT_ID, "ex_db_is", *exhibit_ids],
            "ebitda",
            historical_only=True,
        )
        if ebitda_pref:
            prefer_ref = ebitda_pref
    elif section_id == "SEC-B":
        # Prefer closed-year revenue from M1 / IS exhibits
        prefer_ref = _prefer_trading_anchor(store, exhibit_ids)
    elif section_id == "SEC-C":
        prefer_ref = _prefer_margin_anchor(store, exhibit_ids)
    elif section_id == "SEC-D":
        prefer_ref = _prefer_costs_anchor(
            store,
            [COSTS_EXHIBIT_ID, "ex_db_costs", "ex_db_is", *exhibit_ids],
        )
    elif section_id == "SEC-I":
        prefer_ref = _prefer_cash_anchor(store, exhibit_ids)
    elif section_id == "SEC-F":
        prefer_ref = _prefer_bs_anchor(store, exhibit_ids)
    elif section_id == "SEC-G":
        prefer_ref = _prefer_metric_ref(store, exhibit_ids, "nwc", historical_only=True)

    # Historical trading / ES / cash: prefer closed actuals over outer-year plan.
    historical_only = section_id in {
        "SEC-B",
        "SEC-ES",
        "SEC-C",
        "SEC-D",
        "SEC-I",
        "SEC-F",
        "SEC-G",
    }
    token, ref, anchor_cell = _first_cell_token(
        store,
        exhibit_ids if section_id not in {"SEC-ES"} else (
            [TRADING_EXHIBIT_ID, "ex_db_is", QOE_EXHIBIT_ID, *exhibit_ids]
        ),
        prefer=prefer_ref,
        historical_only=historical_only,
    )
    if ref:
        cell_refs.append(ref)

    if section_id == "SEC-A":
        ents = ", ".join((scope.entities_in if scope else [])[:5]) or name
        from agetic_cdd_api.services_fdd_tokens import effective_currency_scale

        currency, _scale = effective_currency_scale(scope=scope, store=store, qoe=qoe)
        sentences = [
            _sentence(
                "F",
                f"The diligence perimeter covers {ents} on a {currency} basis.",
                citation="scope.json",
            ),
            _sentence(
                "A",
                "Basis of preparation follows the locked scope profile for this run.",
                citation="scope.json",
            ),
        ]
        if limitations:
            sentences.append(
                _sentence(
                    "Q",
                    "Open information requests remain against the perimeter.",
                    citation=limitations[0].item_id,
                )
            )
        action = f"Scope locked for {name}"
    elif section_id == "SEC-E":
        if token is None:
            held_back = True
            held_reason = "QoE exhibit figures not available — build QoE first"
            sentences = [
                _sentence(
                    "Q",
                    "Quality of earnings is held back pending the QoE bridge exhibit.",
                    citation="qoe",
                )
            ]
            action = "QoE held back"
        elif not qoe_real:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=True, treat_as_adjusted=False
            )
            sentences = [
                _sentence(
                    "F",
                    f"Reported earnings on the closed-year basis are {phrase}.",
                    citation=ref or QOE_EXHIBIT_ID,
                ),
                _sentence(
                    "A",
                    "No material QoE adjustments have been booked — the register is empty, so figures remain unadjusted pending the walk.",
                    citation=QOE_EXHIBIT_ID,
                ),
            ]
            basis = _ebitda_basis_sentence(deal_slug, run_id, store)
            if basis is not None:
                sentences.append(basis)
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material QoE judgements remain open.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"Unadjusted earnings: {phrase}"
        else:
            mgmt_tok, mgmt_ref, _mgmt_cell = _first_cell_token(
                store,
                [QOE_EXHIBIT_ID],
                prefer=cell_ref(QOE_EXHIBIT_ID, "adj_ebitda_mgmt"),
            )
            if mgmt_ref:
                cell_refs.append(mgmt_ref)
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False, treat_as_adjusted=True
            )
            sentences = [
                _sentence(
                    "F",
                    f"On the diligence basis, {phrase}.",
                    citation=QOE_EXHIBIT_ID,
                ),
            ]
            if mgmt_tok:
                sentences.append(
                    _sentence(
                        "A",
                        f"The move from management's bridge ({mgmt_tok}) to the diligence view is explained in the QoE walk.",
                        citation=QOE_EXHIBIT_ID,
                    )
                )
            sens_tok, sens_ref, _sens_cell = _first_cell_token(
                store,
                [QOE_EXHIBIT_ID],
                prefer=cell_ref(QOE_EXHIBIT_ID, "sens_low"),
            )
            if sens_tok and sens_ref:
                cell_refs.append(sens_ref)
                sentences.append(
                    _sentence(
                        "A",
                        f"Sensitivities remain beside adjusted EBITDA; the downside case is {sens_tok}.",
                        citation=QOE_EXHIBIT_ID,
                    )
                )
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material QoE judgements remain open.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"Diligence {phrase}"
    elif section_id == "SEC-ES":
        if token is None:
            held_back = True
            held_reason = "No exhibit figures available for executive summary"
            sentences = [
                _sentence(
                    "Q",
                    "Executive summary held back — no exhibit cells to cite.",
                    citation="exhibits",
                )
            ]
            action = "ES held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=qoe_pending
            )
            sentences = [
                _sentence(
                    "F",
                    f"Key financials for {name} are taken from approved exhibits; IC headline is {phrase}.",
                    citation=ref or "exhibits",
                ),
                _sentence(
                    "A",
                    "No new facts are introduced in the executive summary.",
                    citation="executive_summary",
                ),
            ]
            basis = _ebitda_basis_sentence(deal_slug, run_id, store)
            if basis is not None:
                sentences.append(basis)
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material open diligence items remain.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"IC headline: {phrase}"
    elif section_id == "SEC-B":
        cite = (
            TRADING_EXHIBIT_ID
            if TRADING_EXHIBIT_ID in exhibit_ids
            else (exhibit_ids[0] if exhibit_ids else section_id)
        )
        if token is None:
            held_back = True
            held_reason = "Historical trading figures not available — build M1 / bridge IS"
            sentences = [
                _sentence(
                    "Q",
                    "Historical trading is held back pending the M1 trading workbook.",
                    citation=cite,
                )
            ]
            action = "Historical trading held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=qoe_pending
            )
            sentences = [
                _sentence(
                    "F",
                    f"Historical trading: primary closed-year figure is {phrase}.",
                    citation=cite,
                ),
                _sentence(
                    "A",
                    "Revenue and earnings on this page use the investor workbook basis.",
                    citation=cite,
                ),
            ]
            # Secondary: EBITDA and/or YoY from the same trading workbook
            ebitda_tok, ebitda_ref, ebitda_cell = _first_cell_token(
                store,
                exhibit_ids,
                prefer=_prefer_metric_ref(store, exhibit_ids, "ebitda"),
                historical_only=True,
            )
            if (
                ebitda_tok
                and ebitda_ref
                and ebitda_ref != ref
                and ebitda_cell is not None
            ):
                cell_refs.append(ebitda_ref)
                ebitda_phrase = _headline_figure_phrase(
                    ebitda_tok, ebitda_cell, qoe_pending=qoe_pending
                )
                sentences.append(
                    _sentence(
                        "A",
                        f"Reported earnings on the same basis are {ebitda_phrase}.",
                        citation=cite,
                    )
                )
                basis = _ebitda_basis_sentence(deal_slug, run_id, store)
                if basis is not None:
                    sentences.append(basis)
            yoy_tok, yoy_ref, yoy_cell = _first_cell_token(
                store,
                exhibit_ids,
                prefer=_prefer_metric_ref(store, exhibit_ids, "revenue_yoy"),
                historical_only=True,
            )
            if yoy_tok and yoy_ref and yoy_cell is not None:
                cell_refs.append(yoy_ref)
                sentences.append(
                    _sentence(
                        "A",
                        f"Year-on-year revenue change is {yoy_tok}"
                        + (
                            f" ({yoy_cell.scale})"
                            if yoy_cell.scale
                            else ""
                        )
                        + ".",
                        citation=cite,
                    )
                )
            else:
                sentences.append(
                    _sentence(
                        "A",
                        f"Commentary focus — {focus}.",
                        citation=section_id,
                    )
                )
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material trading information requests remain open.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"Historical trading: {phrase}"
    elif section_id == "SEC-C":
        cite = (
            MARGIN_EXHIBIT_ID
            if MARGIN_EXHIBIT_ID in exhibit_ids
            else (exhibit_ids[0] if exhibit_ids else section_id)
        )
        if token is None:
            held_back = True
            held_reason = (
                "Revenue and margin figures not available — build M2 / bridge IS"
            )
            sentences = [
                _sentence(
                    "Q",
                    "Revenue and margin are held back pending the M2 margin workbook.",
                    citation=cite,
                )
            ]
            action = "Revenue and margin held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False
            )
            sentences = [
                _sentence(
                    "F",
                    f"Revenue and margin: primary closed-year figure is {phrase}.",
                    citation=cite,
                ),
                _sentence(
                    "A",
                    "Figures on this page use the investor workbook basis.",
                    citation=cite,
                ),
            ]
            delta_tok, delta_ref, delta_cell = _first_cell_token(
                store,
                exhibit_ids,
                prefer=_prefer_metric_ref(
                    store, exhibit_ids, "gross_margin_delta_pp"
                ),
                historical_only=True,
            )
            if (
                delta_tok
                and delta_ref
                and delta_ref != ref
                and delta_cell is not None
            ):
                cell_refs.append(delta_ref)
                sentences.append(
                    _sentence(
                        "A",
                        f"The gross-margin walk moves {delta_tok} pp year on year.",
                        citation=cite,
                    )
                )
            else:
                sentences.append(
                    _sentence(
                        "A",
                        f"Commentary focus — {focus}.",
                        citation=section_id,
                    )
                )
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material revenue or margin information requests remain open.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"Revenue and margin: {phrase}"
    elif section_id == "SEC-D":
        cite = (
            COSTS_EXHIBIT_ID
            if COSTS_EXHIBIT_ID in exhibit_ids
            else (exhibit_ids[0] if exhibit_ids else section_id)
        )
        costs_mk = (
            (anchor_cell.metric_key or "").lower().replace(" ", "_")
            if anchor_cell
            else ""
        )
        has_cost_figure = costs_mk in {
            "sga",
            "sga_pct_revenue",
            "cogs",
            "cogs_pct_revenue",
            "labor_cost",
            "labor_pct_revenue",
            "headcount",
            "revenue_per_head",
            "sga_yoy",
            "cogs_yoy",
            "labor_yoy",
            "headcount_yoy",
            "opex",
            "operating_expenses",
        }
        if token is None or not has_cost_figure:
            held_back = True
            held_reason = (
                "Cost and people figures not available — build M3 / bridge SG&A"
            )
            sentences = [
                _sentence(
                    "Q",
                    "Costs and people are held back pending the M3 costs workbook (SG&A, COGS, or labour).",
                    citation=cite,
                )
            ]
            action = "Costs and people held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False
            )
            sentences = [
                _sentence(
                    "F",
                    f"Costs and people: primary closed-year figure is {phrase}.",
                    citation=cite,
                ),
                _sentence(
                    "A",
                    "Cost ratios on this page use monthly pack revenue (same basis as pack costs).",
                    citation=cite,
                ),
            ]
            ratio_tok, ratio_ref, ratio_cell = _first_cell_token(
                store,
                exhibit_ids,
                prefer=_prefer_metric_ref(
                    store, exhibit_ids, "sga_pct_revenue"
                )
                or _prefer_metric_ref(store, exhibit_ids, "cogs_pct_revenue"),
                historical_only=True,
            )
            if (
                ratio_tok
                and ratio_ref
                and ratio_ref != ref
                and ratio_cell is not None
            ):
                cell_refs.append(ratio_ref)
                ratio_phrase = _headline_figure_phrase(
                    ratio_tok, ratio_cell, qoe_pending=False
                )
                sentences.append(
                    _sentence(
                        "A",
                        f"Cost intensity on the same basis is {ratio_phrase}.",
                        citation=cite,
                    )
                )
            else:
                sentences.append(
                    _sentence(
                        "A",
                        f"Commentary focus — {focus}.",
                        citation=section_id,
                    )
                )
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material cost or people information requests remain open.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"Costs and people: {phrase}"
    elif section_id == "SEC-I":
        cite = (
            CASH_CONV_EXHIBIT_ID
            if CASH_CONV_EXHIBIT_ID in exhibit_ids
            else (exhibit_ids[0] if exhibit_ids else section_id)
        )
        cash_mk = (
            (anchor_cell.metric_key or "").lower().replace(" ", "_")
            if anchor_cell
            else ""
        )
        has_cash_figure = cash_mk in {
            "operating_cash_flow",
            "free_cash_flow",
            "cash_conversion",
            "fcf_conversion",
            "capex",
            "ocf",
            "cfo",
            "fcf",
        }
        if token is None or not has_cash_figure:
            held_back = True
            held_reason = (
                "Cash conversion figures not available — need OCF/capex from CF"
            )
            sentences = [
                _sentence(
                    "Q",
                    "Cash flow and capex are held back pending operating cash flow and capex from the databook cash-flow statement.",
                    citation=cite,
                )
            ]
            action = "Cash conversion held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False
            )
            sentences = [
                _sentence(
                    "F",
                    f"Cash conversion: primary closed-year figure is {phrase}.",
                    citation=cite,
                ),
            ]
            fcf_tok, fcf_ref, fcf_cell = _first_cell_token(
                store,
                exhibit_ids,
                prefer=_prefer_metric_ref(store, exhibit_ids, "free_cash_flow"),
                historical_only=True,
            )
            if fcf_tok and fcf_ref and fcf_ref != ref and fcf_cell is not None:
                cell_refs.append(fcf_ref)
                fcf_phrase = _headline_figure_phrase(
                    fcf_tok, fcf_cell, qoe_pending=False
                )
                sentences.append(
                    _sentence(
                        "A",
                        f"Free cash flow on the same basis is {fcf_phrase}.",
                        citation=cite,
                    )
                )
            else:
                sentences.append(
                    _sentence(
                        "A",
                        f"Commentary focus — {focus}.",
                        citation=section_id,
                    )
                )
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material cash-flow information requests remain open.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"Cash conversion: {phrase}"
    elif section_id == "SEC-F":
        cite = (
            BS_EXHIBIT_ID
            if BS_EXHIBIT_ID in exhibit_ids
            else (exhibit_ids[0] if exhibit_ids else section_id)
        )
        bs_ref = _prefer_bs_anchor(store, exhibit_ids)
        if token is None or bs_ref is None:
            held_back = True
            held_reason = (
                "Balance sheet figures not available — bridge BS lines from VDR"
            )
            sentences = [
                _sentence(
                    "Q",
                    "Balance sheet and net assets are held back pending BS lines (assets, equity, cash) from the databook.",
                    citation=cite,
                )
            ]
            action = "Balance sheet held back"
        else:
            if bs_ref != ref:
                token, ref, anchor_cell = _first_cell_token(
                    store, exhibit_ids, prefer=bs_ref, historical_only=True
                )
                if ref:
                    cell_refs.append(ref)
            phrase = _headline_figure_phrase(
                token or "", anchor_cell, qoe_pending=False
            )
            sentences = [
                _sentence(
                    "F",
                    f"Balance sheet: primary closed-year figure is {phrase}.",
                    citation=cite,
                ),
                _sentence(
                    "A",
                    f"Commentary focus — {focus}.",
                    citation=section_id,
                ),
            ]
            if limitations:
                sentences.append(
                    _sentence(
                        "Q",
                        "Material balance-sheet information requests remain open.",
                        citation=limitations[0].item_id,
                    )
                )
            action = f"Balance sheet: {phrase}"
    elif section_id == "SEC-G":
        cite = (
            NWC_EXHIBIT_ID
            if NWC_EXHIBIT_ID in exhibit_ids
            else (exhibit_ids[0] if exhibit_ids else section_id)
        )
        nwc_ex = next(
            (ex for ex in store.exhibits if ex.exhibit_id == NWC_EXHIBIT_ID),
            None,
        )
        liab_missing = bool(
            nwc_ex
            and any(
                "nwc_liabilities_missing" in (n or "")
                for n in (nwc_ex.footnotes or [])
            )
        )
        if token is None or liab_missing:
            held_back = True
            held_reason = (
                "NWC incomplete — need WC liabilities (AP / current liabilities)"
            )
            sentences = [
                _sentence(
                    "Q",
                    "Net working capital is held back until accounts payable or current liabilities are bridged from the balance sheet.",
                    citation=cite,
                )
            ]
            action = "NWC held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False
            )
            sentences = [
                _sentence(
                    "F",
                    f"Net working capital on the closed-year basis is {phrase}.",
                    citation=cite,
                ),
                _sentence(
                    "A",
                    f"Commentary focus — {focus}.",
                    citation=section_id,
                ),
            ]
            action = f"NWC: {phrase}"
    elif section_id == "SEC-H":
        cite = (
            "ex_m6_net_debt"
            if "ex_m6_net_debt" in exhibit_ids
            else (exhibit_ids[0] if exhibit_ids else section_id)
        )
        if token is None:
            held_back = True
            held_reason = (
                "Net debt figures not available — bridge cash + debt / long-term liabilities"
            )
            sentences = [
                _sentence(
                    "Q",
                    "Net debt is held back pending cash and interest-bearing debt (or long-term liabilities / loan schedules) from the databook.",
                    citation=cite,
                )
            ]
            action = "Net debt held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False
            )
            sentences = [
                _sentence(
                    "F",
                    f"Net debt on the closed-year basis is {phrase}.",
                    citation=cite,
                ),
                _sentence(
                    "A",
                    f"Commentary focus — {focus}.",
                    citation=section_id,
                ),
            ]
            action = f"Net debt: {phrase}"
    elif section_id == "SEC-K":
        # Key findings hosts the workbook↔ledger reconciliation even without a
        # dedicated exhibit — never hard-hold solely for missing cells.
        # Held-section digest is injected later in build_commentary (needs peers).
        sentences = [
            _sentence(
                "A",
                f"Key findings for {name} — open figure gaps, held sections, and completion items.",
                citation="SEC-K",
            ),
        ]
        if token is not None:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False
            )
            sentences.insert(
                0,
                _sentence(
                    "F",
                    f"Primary closed-year figure is {phrase}.",
                    citation=exhibit_ids[0] if exhibit_ids else (ref or section_id),
                ),
            )
            action = f"Key findings: {phrase}"
        else:
            action = "Key findings"
        other_lims = [
            lim
            for lim in limitations
            if not (lim.item_id or "").startswith("gap:")
        ]
        for lim in other_lims[:4]:
            sentences.append(
                _sentence(
                    "Q",
                    lim.text,
                    citation=lim.item_id or "SEC-K",
                )
            )
        gap_only = [
            lim
            for lim in limitations
            if (lim.item_id or "").startswith("gap:")
        ]
        if not gap_only and not other_lims:
            sentences.append(
                _sentence(
                    "A",
                    "No material workbook-versus-ledger gaps are open on this run.",
                    citation="SEC-K",
                )
            )
    else:
        # Generic template for D (and other soft sections)
        if token is None and section_id not in OPTIONAL_SECTIONS:
            # Soft hold — still draft Q sentences if optional missing figures
            if not exhibit_ids:
                held_back = True
                held_reason = f"No exhibits mapped to {title}"
                sentences = [
                    _sentence(
                        "Q",
                        f"{title} is held back pending exhibit coverage.",
                        citation=section_id,
                    )
                ]
                action = f"{title} held back"
            else:
                sentences = [
                    _sentence(
                        "Q",
                        f"{title}: exhibits are present but no numeric cells are bound yet.",
                        citation=exhibit_ids[0],
                    )
                ]
                action = f"{title}: figures pending"
        elif token is None:
            held_back = True
            held_reason = f"{title} has no figures"
            sentences = [
                _sentence(
                    "Q",
                    f"{title} is out of figure coverage for this run.",
                    citation=section_id,
                )
            ]
            action = f"{title} held back"
        else:
            phrase = _headline_figure_phrase(
                token, anchor_cell, qoe_pending=False
            )
            fact_line = f"{title}: the primary figure is {phrase}."
            sentences = [
                _sentence(
                    "F",
                    fact_line,
                    citation=exhibit_ids[0] if exhibit_ids else (ref or section_id),
                ),
                _sentence(
                    "A",
                    f"Commentary focus — {focus}.",
                    citation=section_id,
                ),
            ]
            action = f"{title}: {phrase}"

    # Append source-gap / contradiction limitations (size + sources) first, then others.
    def _is_gap_lim(lim: CommentaryLimitation) -> bool:
        t = lim.text or ""
        return (
            (lim.item_id or "").startswith("gap:")
            or "gap " in t.lower()
            or "(contradicted)" in t.lower()
        )

    gap_lims = [lim for lim in limitations if _is_gap_lim(lim)]
    other_lims = [lim for lim in limitations if not _is_gap_lim(lim)]
    cited = {s.citation for s in sentences if s.citation}
    gap_n = 0
    other_n = 0
    for lim in [*gap_lims, *other_lims]:
        if lim.item_id in cited:
            continue
        is_gap = _is_gap_lim(lim)
        if is_gap and gap_n >= 12:
            continue
        if not is_gap and other_n >= 2:
            continue
        sentences.append(
            _sentence(
                "Q",
                _limitation_sentence_text(lim),
                citation=lim.item_id,
            )
        )
        cited.add(lim.item_id)
        if is_gap:
            gap_n += 1
        else:
            other_n += 1

    body = _join_body(sentences)
    draft = SectionDraft(
        section_id=section_id,
        title=title,
        diligence_question=question,
        status=ArtefactStatus.DRAFT,
        held_back=held_back,
        held_back_reason=held_reason,
        action_title=action,
        sentences=sentences,
        body=body,
        tags_used=sorted({s.tag for s in sentences}),
        exhibit_ids=list(dict.fromkeys(exhibit_ids)),
        cell_refs=list(dict.fromkeys(cell_refs)),
        limitations=limitations,
    )
    return validate_section_draft(draft, store)


def validate_section_draft(
    draft: SectionDraft, store: ExhibitStoreDoc
) -> SectionDraft:
    """Run P6 narrative checks; stamp checks_passed."""
    checks: list[CommentaryCheckResult] = []
    text_blob = "\n".join(
        [draft.action_title, draft.body] + [s.text for s in draft.sentences]
    )

    # 1) Typed figures
    faults = assert_no_raw_numeric_literals(text_blob)
    checks.append(
        CommentaryCheckResult(
            check_id="typed_figures",
            passed=not faults,
            message=(
                "No typed figures outside tokens"
                if not faults
                else f"Typed figures: {', '.join(faults[:8])}"
            ),
            blocking=True,
            severity="S1",
        )
    )

    # 2) Tokens resolve
    resolved = resolve_text(text_blob, store)
    checks.append(
        CommentaryCheckResult(
            check_id="tokens_resolve",
            passed=not resolved.unresolved,
            message=(
                "All tokens resolve"
                if not resolved.unresolved
                else f"Unresolved: {', '.join(resolved.unresolved[:8])}"
            ),
            blocking=True,
            severity="S1",
        )
    )

    # 3) Action title ≤ 1 token
    title_tokens = find_tokens(draft.action_title)
    checks.append(
        CommentaryCheckResult(
            check_id="action_title_tokens",
            passed=len(title_tokens) <= 1,
            message=f"Action title has {len(title_tokens)} token(s) (max 1)",
            blocking=True,
            severity="S2",
        )
    )

    # 4) Every sentence tagged; F/A/M have citations
    for i, s in enumerate(draft.sentences):
        if s.tag in {"F", "A", "M"} and not (s.citation or "").strip():
            checks.append(
                CommentaryCheckResult(
                    check_id=f"citation_{i}",
                    passed=False,
                    message=f"Sentence {i} tag {s.tag} missing citation",
                    blocking=True,
                    severity="S1",
                )
            )
        if s.tag == "Q" and not (s.citation or "").strip():
            checks.append(
                CommentaryCheckResult(
                    check_id=f"q_link_{i}",
                    passed=False,
                    message=f"Q sentence {i} missing open-item / request link",
                    blocking=False,
                    severity="S2",
                )
            )

    # 5) Invest advice / superlatives
    # Word-boundary match so "investor workbook" does not trip bare "invest".
    low = text_blob.lower()
    for phrase in INVEST_ADVICE_FORBIDDEN:
        if re.search(rf"\b{re.escape(phrase)}\b", low):
            checks.append(
                CommentaryCheckResult(
                    check_id="invest_advice",
                    passed=False,
                    message=f"Forbidden invest language: {phrase!r}",
                    blocking=True,
                    severity="S1",
                )
            )
            break
    else:
        checks.append(
            CommentaryCheckResult(
                check_id="invest_advice",
                passed=True,
                message="No invest advice",
                blocking=True,
                severity="S1",
            )
        )

    for phrase in SUPERLATIVES_FORBIDDEN:
        if phrase in low:
            checks.append(
                CommentaryCheckResult(
                    check_id="superlatives",
                    passed=False,
                    message=f"Forbidden superlative / overconfidence: {phrase!r}",
                    blocking=True,
                    severity="S1",
                )
            )
            break
    else:
        checks.append(
            CommentaryCheckResult(
                check_id="superlatives",
                passed=True,
                message="No forbidden superlatives",
                blocking=True,
                severity="S1",
            )
        )

    # 6) Because / driven by only in A or M
    for i, s in enumerate(draft.sentences):
        if _BECAUSE_RE.search(s.text) and s.tag not in {"A", "M"}:
            checks.append(
                CommentaryCheckResult(
                    check_id=f"causal_{i}",
                    passed=False,
                    message=f"Causal wording in tag {s.tag} (sentence {i})",
                    blocking=True,
                    severity="S1",
                )
            )

    # 7) Held-back must have reason
    if draft.held_back and not draft.held_back_reason:
        checks.append(
            CommentaryCheckResult(
                check_id="held_back_reason",
                passed=False,
                message="Held-back section missing reason",
                blocking=True,
                severity="S2",
            )
        )

    blocking_failed = [c for c in checks if c.blocking and not c.passed]
    return draft.model_copy(
        update={
            "checks": checks,
            "checks_passed": not blocking_failed,
            "tags_used": sorted({s.tag for s in draft.sentences}),
            "body": draft.body or _join_body(draft.sentences),
        }
    )


def _sections_in_scope(deal_slug: str, run_id: str) -> list[str]:
    scope = load_scope_profile(deal_slug, run_id)
    if scope and scope.sections_in_scope:
        return list(scope.sections_in_scope)
    return list(DEFAULT_SECTIONS_IN_SCOPE)


def _enrich_key_findings_with_held(
    drafts: list[SectionDraft],
) -> list[SectionDraft]:
    """Append held-section digest to SEC-K so Key findings is not gaps-only."""
    held = [
        d
        for d in drafts
        if d.held_back and d.section_id not in {"SEC-K", "SEC-ES", "SEC-A"}
    ]
    if not held:
        return drafts
    bits = []
    for d in held[:6]:
        reason = (d.held_back_reason or "figures pending").strip()
        title = (d.title or d.section_id).strip()
        bits.append(f"{title}: {reason}")
    digest = _sentence(
        "Q",
        "Held-back analysis sections — " + "; ".join(bits) + ".",
        citation="SEC-K",
    )
    out: list[SectionDraft] = []
    for d in drafts:
        if d.section_id != "SEC-K":
            out.append(d)
            continue
        sentences = list(d.sentences or [])
        # Drop the generic "no gaps" line when holds exist.
        sentences = [
            s
            for s in sentences
            if "No material workbook-versus-ledger gaps" not in (s.text or "")
        ]
        sentences.append(digest)
        out.append(
            d.model_copy(
                update={
                    "sentences": sentences,
                    "body": _join_body(sentences),
                    "tags_used": sorted({s.tag for s in sentences}),
                }
            )
        )
    return out


def build_commentary(
    deal_slug: str,
    run_id: str,
    *,
    company: str | None = None,
    section_ids: list[str] | None = None,
    update_manifest: bool = True,
    update_report_spec: bool = True,
) -> CommentaryDoc:
    """Build tagged commentary for in-scope sections; persist commentary.json."""
    store = sync_qoe_exhibit(deal_slug, run_id)
    wanted = section_ids or _sections_in_scope(deal_slug, run_id)
    drafts: list[SectionDraft] = []
    for sid in wanted:
        drafts.append(
            draft_section(
                sid,
                deal_slug=deal_slug,
                run_id=run_id,
                store=store,
                company=company,
            )
        )

    # Enrich SEC-K with a held-section digest (needs peer drafts).
    drafts = _enrich_key_findings_with_held(drafts)

    typed_faults: list[str] = []
    unresolved: list[str] = []
    for d in drafts:
        for c in d.checks:
            if c.check_id == "typed_figures" and not c.passed:
                typed_faults.append(f"{d.section_id}: {c.message}")
            if c.check_id == "tokens_resolve" and not c.passed:
                unresolved.append(f"{d.section_id}: {c.message}")

    held = [d.section_id for d in drafts if d.held_back]
    all_pass = all(d.checks_passed for d in drafts)

    doc = CommentaryDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        version=COMMENTARY_VERSION,
        status=ArtefactStatus.CHECKED if all_pass else ArtefactStatus.DRAFT,
        sections=drafts,
        held_back_sections=held,
        checks_passed=all_pass,
        typed_figure_faults=typed_faults,
        unresolved_tokens=unresolved,
        notes=[
            "Phase 6 deterministic section writers — LLM prompts can replace draft_section later",
            f"Sections: {len(drafts)}; held back: {len(held)}",
        ],
    )
    doc = save_commentary(doc)

    if update_report_spec:
        _bind_commentary_to_report_spec(
            deal_slug, run_id, doc, store=store, company=company
        )

    if update_manifest:
        manifest = load_manifest(deal_slug, run_id)
        if manifest is not None:
            stage = manifest.stage
            if stage in {
                RunStage.P0,
                RunStage.P1,
                RunStage.P2,
                RunStage.P3,
                RunStage.P4,
                RunStage.P5,
            }:
                stage = RunStage.P6
            save_manifest(
                manifest.model_copy(
                    update={
                        "commentary_built": True,
                        "stage": stage,
                        "model_versions": {
                            **(manifest.model_versions or {}),
                            "fdd_commentary": COMMENTARY_VERSION,
                        },
                    }
                )
            )
    return doc


def _bind_commentary_to_report_spec(
    deal_slug: str,
    run_id: str,
    doc: CommentaryDoc,
    *,
    store: ExhibitStoreDoc,
    company: str | None = None,
) -> None:
    """Refresh report_spec via Phase 7 assembly (commentary + exhibits + slides)."""
    from agetic_cdd_api.services_fdd_assemble import assemble_and_persist

    assemble_and_persist(
        deal_slug,
        run_id,
        store=store,
        company=company,
        commentary=doc,
        update_manifest=True,
    )


def get_section(deal_slug: str, run_id: str, section_id: str) -> SectionDraft | None:
    doc = load_commentary(deal_slug, run_id)
    if doc is None:
        return None
    for s in doc.sections:
        if s.section_id == section_id:
            return s
    return None


def inject_faulty_typed_figure(text: str, figure: str = "101.3") -> str:
    """Test helper — insert a raw figure for trap cases."""
    return f"{text} The figure is {figure} without a token."
