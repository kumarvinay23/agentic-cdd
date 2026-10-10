"""FDD Phase 1 — databook contract bridge (release → fact table → exhibits)."""

from __future__ import annotations

import re
from typing import Final

from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CellStatus,
    DatabookContractAssessment,
    EightLabels,
    EvidenceTier,
    ExhibitCell,
    ExhibitStoreDoc,
    FactTableDoc,
    FddFact,
    FddRunManifest,
    FigureType,
    LabelGap,
    RunStage,
)
from agetic_cdd_api.services_databook_consume import (
    MATERIAL_METRIC_KEYS,
    humanize_metric_key,
)
from agetic_cdd_api.services_databook_models import (
    DatabookRelease,
    PROOF_LEVEL_RANK,
    ProofLevel,
    ReleaseCellStatus,
    ReleasedCell,
    SourceBasis,
)
from agetic_cdd_api.services_databook_release import (
    SlugDeal,
    ensure_current_release_for_slug,
)
from agetic_cdd_api.services_databook_store import load_release, load_release_for_slug
from agetic_cdd_api.services_fdd_exhibit import persist_store, upsert_cells
from agetic_cdd_api.services_fdd_store import (
    load_exhibit_store,
    load_manifest,
    save_fact_table,
    save_manifest,
)
from agetic_cdd_api.services_fdd_sources import prefer_workbook_among
from agetic_cdd_api.services_fdd_tokens import format_fdd_number, metric_cell_id

BRIDGE_VERSION = "0.1.4"

# SaaS retention keys are optional for non-SaaS FDD packs — incomplete eight
# labels on NRR/GRR must not force draft_mode across every figure.
_CONTRACT_OPTIONAL_METRICS: Final[frozenset[str]] = frozenset({"nrr", "grr"})

# Money BS / P&L metrics that must never inherit a spurious "%" unit from
# captions like "Shareholders' Equity".
_MONEY_METRIC_KEYS: Final[frozenset[str]] = frozenset(
    {
        "revenue",
        "ebitda",
        "gross_profit",
        "cogs",
        "sga",
        "labor_cost",
        "net_income",
        "cash",
        "inventory",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "accounts_receivable",
        "accounts_payable",
        "operating_cash_flow",
        "capex",
        "free_cash_flow",
        "term_loan",
        "gross_debt",
        "net_debt",
        "nwc",
    }
)

# Whole-token BS / debt / WC routers (no raw substring ``in``).
_DEBT_TOKENS: Final[frozenset[str]] = frozenset(
    {"debt", "loan", "borrow", "revolver", "facility", "lease", "cash"}
)
_NWC_TOKENS: Final[frozenset[str]] = frozenset(
    {"receivable", "payable", "inventory", "accrual", "prepay", "prepaid"}
)
_BS_TOKENS: Final[frozenset[str]] = frozenset(
    {"assets", "liabilities", "equity", "nav", "ppe", "goodwill"}
)
_CF_TOKENS: Final[frozenset[str]] = frozenset(
    {"capex", "ocf", "cfo", "fcf"}
)
# Multi-token aliases checked via subset (frozenset of parts).
_NWC_MULTI: Final[tuple[frozenset[str], ...]] = (
    frozenset({"deferred", "revenue"}),
)
_BS_MULTI: Final[tuple[frozenset[str], ...]] = (
    frozenset({"net", "assets"}),
)
_CF_MULTI: Final[tuple[frozenset[str], ...]] = (
    frozenset({"operating", "cash"}),
    frozenset({"cash", "flow"}),
    frozenset({"free", "cash"}),
    frozenset({"net", "change", "cash"}),
    frozenset({"capital", "expenditure"}),
)
# P&L-ish tokens that block debt/cash false positives (lease_expense, cash_register).
# Do not include flow/flows — those belong on the cash-flow statement.
_PL_NOISE: Final[frozenset[str]] = frozenset(
    {
        "expense",
        "expenses",
        "cost",
        "costs",
        "charge",
        "charges",
        "maintenance",
        "register",
        "fee",
        "fees",
    }
)


class ReleasePinError(ValueError):
    """Manifest databook pin does not match the current release."""


class GateBlockedError(ValueError):
    """Requested gate is unavailable (e.g. G6 while draft_mode)."""


def _sanitize_money_unit(
    metric_key: str | None,
    *,
    unit: str | None,
    scale: str | None,
) -> str | None:
    """Drop spurious % units on money lines (e.g. Shareholders' Equity)."""
    unt = (unit or "").strip()
    scl = (scale or "").strip()
    mk = (metric_key or "").strip().lower()
    if unt in {"%", "pp", "pct", "percent"} and (
        mk in _MONEY_METRIC_KEYS or scl in {"M", "B", "K", "Cr", "m", "b", "k"}
    ):
        return None
    return unit


_STATEMENT_EXHIBIT: dict[str, tuple[str, str, str]] = {
    "is": ("ex_db_is", "Income statement (databook)", "SEC-B"),
    "income_statement": ("ex_db_is", "Income statement (databook)", "SEC-B"),
    "pl": ("ex_db_is", "Income statement (databook)", "SEC-B"),
    "p&l": ("ex_db_is", "Income statement (databook)", "SEC-B"),
    "bs": ("ex_db_bs", "Balance sheet (databook)", "SEC-F"),
    "balance_sheet": ("ex_db_bs", "Balance sheet (databook)", "SEC-F"),
    "cf": ("ex_db_cf", "Cash flow (databook)", "SEC-I"),
    "cash_flow": ("ex_db_cf", "Cash flow (databook)", "SEC-I"),
}


def _format_number(value: float | None) -> str:
    return format_fdd_number(value)


def _map_release_status(status: ReleaseCellStatus | str) -> CellStatus:
    raw = status.value if isinstance(status, ReleaseCellStatus) else str(status)
    if raw == CellStatus.PROVEN.value:
        return CellStatus.PROVEN
    if raw == CellStatus.DOUBTFUL.value:
        return CellStatus.DOUBTFUL
    if raw == CellStatus.MISSING.value:
        return CellStatus.MISSING
    return CellStatus.DRAFT


def eight_labels_from_cell(cell: ReleasedCell) -> EightLabels:
    line = (cell.captions[0] if cell.captions else None) or humanize_metric_key(
        cell.metric_key
    )
    from agetic_cdd_api.services_databook_consume import _display_unit_parts

    raw_unit = _sanitize_money_unit(
        cell.metric_key, unit=cell.unit, scale=cell.scale
    )
    unit = _display_unit_parts(cell.currency, cell.scale, raw_unit) or None
    if unit in {"%", "pp", "pct", "percent"} and (
        (cell.scale or "").strip() in {"M", "B", "K", "Cr", "m", "b", "k"}
        or (cell.metric_key or "").lower() in _MONEY_METRIC_KEYS
    ):
        unit = None
    basis = cell.source_basis.value if cell.source_basis else None
    source: str | None = None
    if cell.source_ref is not None:
        ref = cell.source_ref
        bits = [ref.doc]
        if ref.page is not None:
            bits.append(f"p{ref.page}")
        if ref.table:
            bits.append(str(ref.table))
        source = " / ".join(b for b in bits if b) or None
    if not source and cell.sources:
        source = str(cell.sources[0])
    return EightLabels(
        scope=cell.scope,
        statement=cell.statement,
        line=line,
        period_end=cell.period_end,
        period_length=cell.period_length,
        basis=basis,
        unit=unit,
        source=source,
    )


def fact_id_for_cell(cell: ReleasedCell, release: DatabookRelease) -> str:
    if cell.row_id:
        return f"db:{release.release_id}:{cell.row_id}"
    return f"db:{release.release_id}:{cell.metric_key}:{cell.fiscal_year}"


def assess_databook_contract(
    release: DatabookRelease | None,
    *,
    deal_slug: str,
) -> DatabookContractAssessment:
    """IN-2 / IN-3 — draft mode unless material cells carry status + eight labels."""
    if release is None:
        return DatabookContractAssessment(
            deal_slug=deal_slug,
            complete=False,
            draft_mode=True,
            g6_allowed=False,
            reasons=["no_databook_release"],
        )

    cells = list(release.cells or [])
    reasons: list[str] = []
    if not cells:
        reasons.append("no_release_cells")

    material = [
        c
        for c in cells
        if c.metric_key in MATERIAL_METRIC_KEYS
        and c.metric_key not in _CONTRACT_OPTIONAL_METRICS
    ]
    if cells and not material:
        reasons.append("no_material_cells")

    labels_incomplete = 0
    label_gaps: list[LabelGap] = []
    min_l2_rank = PROOF_LEVEL_RANK.get(ProofLevel.L2, 2)
    for cell in material:
        labels = eight_labels_from_cell(cell)
        status = _map_release_status(cell.status)
        if status == CellStatus.MISSING:
            continue
        missing = labels.missing_fields()
        if missing:
            labels_incomplete += 1
            label_gaps.append(
                LabelGap(
                    metric_key=cell.metric_key,
                    fiscal_year=int(cell.fiscal_year),
                    missing_fields=list(missing),
                )
            )
            reasons.append(
                f"labels_incomplete:{cell.metric_key}:FY{cell.fiscal_year}:"
                + ",".join(missing)
            )
        if status == CellStatus.PROVEN:
            if cell.proof_level is None:
                reasons.append(
                    f"proof_level_missing:{cell.metric_key}:FY{cell.fiscal_year}"
                )
            else:
                rank = PROOF_LEVEL_RANK.get(cell.proof_level, 0)
                if rank < min_l2_rank:
                    reasons.append(
                        f"proof_below_l2:{cell.metric_key}:FY{cell.fiscal_year}:"
                        f"{cell.proof_level.value}"
                    )

    # Compact reasons for display (cap label incompletes at 5); full gaps in label_gaps.
    compact: list[str] = []
    seen: set[str] = set()
    label_inc_count = 0
    for r in reasons:
        if r.startswith("labels_incomplete:"):
            label_inc_count += 1
            if label_inc_count > 5:
                if "labels_incomplete:…" not in seen:
                    compact.append("labels_incomplete:…")
                    seen.add("labels_incomplete:…")
                continue
        if r not in seen:
            seen.add(r)
            compact.append(r)

    complete = not compact
    return DatabookContractAssessment(
        deal_slug=deal_slug,
        release_id=release.release_id,
        release_version=release.version,
        complete=complete,
        draft_mode=not complete,
        g6_allowed=complete,
        cell_count=len(cells),
        material_count=len(material),
        labels_incomplete=labels_incomplete,
        label_gaps=label_gaps,
        reasons=compact,
    )


def _prefer_workbook_value(
    cell: ReleasedCell,
) -> tuple[float | None, list[str], list[dict]]:
    """Prefer investor-workbook candidates over ledger when both disagree.

    Returns ``(value, sources, alternatives)`` with the non-chosen peer retained
    in alternatives so commentary can state the gap.
    """
    value, sources, alts, _note = prefer_workbook_among(
        cell.value,
        list(cell.sources or []),
        [dict(a) for a in (cell.alternatives or []) if isinstance(a, dict)],
    )
    return value, sources, alts


def released_cell_to_fact(
    cell: ReleasedCell,
    release: DatabookRelease,
    *,
    draft_mode: bool,
) -> FddFact:
    labels = eight_labels_from_cell(cell)
    release_status = _map_release_status(cell.status)
    # Keep proven/doubtful from the release — draft_mode is a run banner, not a
    # blanket demotion of every pack actual to "draft".
    status = release_status
    value, sources, alternatives = _prefer_workbook_value(cell)
    unit = _sanitize_money_unit(cell.metric_key, unit=cell.unit, scale=cell.scale)
    if unit != cell.unit and labels.unit and "%" in (labels.unit or ""):
        labels = labels.model_copy(update={"unit": None})
    return FddFact(
        fact_id=fact_id_for_cell(cell, release),
        metric_key=cell.metric_key,
        fiscal_year=int(cell.fiscal_year),
        value=value,
        display=_format_number(value) if value is not None else "—",
        status=status,
        release_status=release_status,
        labels=labels,
        labels_complete=labels.complete,
        draft_flagged=draft_mode,
        currency=cell.currency,
        scale=cell.scale,
        unit=unit,
        row_id=cell.row_id,
        proof_level=cell.proof_level.value if cell.proof_level else None,
        databook_release_id=release.release_id,
        databook_release_version=release.version,
        source_ref=cell.source_ref.model_dump(mode="json") if cell.source_ref else None,
        request_id=cell.request_id,
        sources=sources,
        alternatives=alternatives,
    )


def facts_from_release(
    release: DatabookRelease,
    *,
    draft_mode: bool,
) -> list[FddFact]:
    return [
        released_cell_to_fact(c, release, draft_mode=draft_mode)
        for c in release.cells
    ]


def _exhibit_meta_for_statement(statement: str | None) -> tuple[str, str, str]:
    key = (statement or "").strip().lower().replace(" ", "_")
    if key in _STATEMENT_EXHIBIT:
        return _STATEMENT_EXHIBIT[key]
    return ("ex_db_metrics", "Databook metrics", "SEC-B")


def _exhibit_meta_for_metric(metric_key: str | None) -> tuple[str, str, str] | None:
    """Route BS / debt / WC / CF metrics when statement labels are missing.

    Uses whole-token intersection (not substring ``in``) so keys like
    ``board_member_lease_expense`` / ``cash_register_maintenance`` stay off SEC-F.
    """
    nk = re.sub(r"[^a-z0-9]+", "_", (metric_key or "").lower()).strip("_")
    if not nk:
        return None
    tokens = {p for p in nk.split("_") if p}
    if not tokens:
        return None
    # Cash-flow statement before BS — operating_cash_flow has a "cash" token.
    if any(alias <= tokens for alias in _CF_MULTI) or tokens & _CF_TOKENS:
        return ("ex_db_cf", "Cash flow (databook)", "SEC-I")
    # Multi-token WC / BS aliases first (deferred_revenue, net_assets)
    if any(alias <= tokens for alias in (*_NWC_MULTI, *_BS_MULTI)):
        return ("ex_db_bs", "Balance sheet (databook)", "SEC-F")
    # Skip P&L noise compounds before bare debt/cash tokens
    if tokens & _PL_NOISE:
        return None
    if tokens & _DEBT_TOKENS or tokens & _NWC_TOKENS or tokens & _BS_TOKENS:
        return ("ex_db_bs", "Balance sheet (databook)", "SEC-F")
    return None

def _basis_to_tier(basis: str | None) -> EvidenceTier:
    if basis == SourceBasis.AUDITED.value:
        return EvidenceTier.A
    if basis in {SourceBasis.MANAGEMENT.value, SourceBasis.DRAFT.value}:
        return EvidenceTier.B
    return EvidenceTier.C


_COST_METRICS = frozenset(
    {
        "sga",
        "opex",
        "operating_expenses",
        "labor_cost",
        "labour_cost",
        "personnel_cost",
        "personnel_costs",
        "headcount",
        "fte",
        "ftes",
        "average_fte",
        "average_headcount",
    }
)


def _period_tag_for_fact(fact: FddFact) -> str:
    """Human period stamp — YTD stubs and plan years must not read as closed FY."""
    from datetime import date

    from agetic_cdd_api.services_fdd_sources import classify_source

    year = int(fact.fiscal_year)
    closed = date.today().year - 1
    plen = ""
    pend = ""
    if fact.labels:
        plen = str(fact.labels.period_length or "").upper()
        pend = str(fact.labels.period_end or "")
    kind = classify_source(fact.sources, fact.labels.source if fact.labels else None)
    # Workbook / plan wins the label even when the release cell carried a YTD
    # stamp from the pack (prefer_workbook swaps the figure, not the labels).
    if year > closed and kind == "workbook":
        return f"FY{year}E (plan)"
    if plen == "YTD" or (year > closed and kind == "management"):
        month = 7
        if len(pend) >= 7 and pend[5:7].isdigit():
            month = max(1, min(12, int(pend[5:7])))
        # Bare FY stamped YTD often keeps period_end Dec-31 — use Jul when so.
        if month == 12 and (plen == "YTD" or kind == "management"):
            month = 7
        months = (
            "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        )
        return f"Jan–{months[month - 1]} {year} YTD"
    if year > closed:
        return f"FY{year}E (plan)"
    return f"FY{year}"


def facts_to_exhibit_cells(facts: list[FddFact]) -> list[ExhibitCell]:
    cells: list[ExhibitCell] = []
    for fact in facts:
        if fact.metric_key in _COST_METRICS:
            meta = ("ex_db_costs", "Costs and people (databook)", "SEC-D")
        else:
            meta = _exhibit_meta_for_statement(fact.labels.statement)
            # When statement is blank/unknown, route BS/debt/WC metrics off the P&L dump
            if meta[0] == "ex_db_metrics":
                by_metric = _exhibit_meta_for_metric(fact.metric_key)
                if by_metric is not None:
                    meta = by_metric
        exhibit_id, _title, _sec = meta
        # Slugify so tokens never embed spaces/parens from human metric labels
        cell_id = metric_cell_id(fact.metric_key, fact.fiscal_year)
        base_label = fact.labels.line or humanize_metric_key(fact.metric_key)
        period = _period_tag_for_fact(fact)
        label = f"{base_label} ({period})"
        figure_type = FigureType.REPORTED
        if "YTD" in period or "plan" in period:
            figure_type = (
                FigureType.ESTIMATED if "plan" in period else FigureType.REPORTED
            )
        from agetic_cdd_api.services_fdd_sources import (
            classify_source,
            display_source_name,
        )

        kind = classify_source(
            fact.sources, fact.labels.source if fact.labels else None
        )
        basis = display_source_name(kind, fact.sources)
        if "YTD" in period:
            basis = f"{basis} · YTD actuals"
        elif "plan" in period:
            basis = f"{basis} · full-year plan"
        cells.append(
            ExhibitCell(
                cell_id=cell_id,
                exhibit_id=exhibit_id,
                label=label,
                value=fact.value,
                display=fact.display,
                unit=fact.unit,
                currency=fact.currency,
                scale=fact.scale,
                fiscal_year=fact.fiscal_year,
                metric_key=fact.metric_key,
                fact_id=fact.fact_id,
                figure_type=figure_type,
                evidence_tier=_basis_to_tier(fact.labels.basis),
                status=fact.status,
                draft_flagged=fact.draft_flagged,
                basis_label=basis,
                labels=fact.labels,
                databook_release_id=fact.databook_release_id,
                databook_release_version=fact.databook_release_version,
                source_ref=fact.source_ref,
            )
        )
    return cells


def apply_facts_to_store(
    store: ExhibitStoreDoc,
    facts: list[FddFact],
) -> ExhibitStoreDoc:
    """Upsert databook-derived exhibit cells; preserve non-db exhibits."""
    cells = facts_to_exhibit_cells(facts)
    if not cells:
        return store
    titles: dict[str, str] = {}
    sections: dict[str, str] = {}
    for fact in facts:
        if fact.metric_key in _COST_METRICS:
            meta = ("ex_db_costs", "Costs and people (databook)", "SEC-D")
        else:
            meta = _exhibit_meta_for_statement(fact.labels.statement)
            if meta[0] == "ex_db_metrics":
                by_metric = _exhibit_meta_for_metric(fact.metric_key)
                if by_metric is not None:
                    meta = by_metric
        eid, title, sec = meta
        titles[eid] = title
        sections[eid] = sec
    return upsert_cells(store, cells, exhibit_titles=titles, section_ids=sections)


def resolve_release_for_deal(
    deal_slug: str,
    *,
    release_id: str | None = None,
    bootstrap: bool = True,
) -> DatabookRelease | None:
    """Load pinned or current release; optionally bootstrap from working store."""
    if release_id:
        deal = SlugDeal(id=deal_slug, slug=deal_slug)
        pinned = load_release(deal, release_id)
        if pinned is not None:
            return pinned
        # Fallback slug loader (path-based) if DealLike path differs
        return load_release_for_slug(deal_slug, release_id)
    if bootstrap:
        return ensure_current_release_for_slug(deal_slug)
    return load_release_for_slug(deal_slug)


def check_release_pin(
    manifest: FddRunManifest,
    *,
    current: DatabookRelease | None = None,
    allow_intentional_pin: bool | None = None,
) -> None:
    """Refuse stage start when pinned release ≠ current (unless intentional pin).

    ``allow_pinned_release`` permits a non-current release_id, but the declared
    version must still match the pinned artefact when that artefact is loadable.
    """
    allow = (
        manifest.allow_pinned_release
        if allow_intentional_pin is None
        else allow_intentional_pin
    )
    pin_id = manifest.databook_release_id
    if not pin_id:
        return
    pin_ver = manifest.databook_release_version
    cur = current if current is not None else load_release_for_slug(manifest.deal_slug)

    # Self-consistency: pin version ↔ pinned artefact (not just ↔ current).
    pinned = (
        cur
        if cur is not None and cur.release_id == pin_id
        else load_release_for_slug(manifest.deal_slug, pin_id)
    )
    if (
        pinned is not None
        and pin_ver is not None
        and int(pin_ver) != int(pinned.version)
    ):
        raise ReleasePinError(
            f"Pinned databook version {pin_ver} ≠ artefact {pinned.version} "
            f"for release {pin_id}"
        )

    if cur is None:
        return
    id_ok = pin_id == cur.release_id
    ver_ok = pin_ver is None or int(pin_ver) == int(cur.version)
    if id_ok and ver_ok:
        return
    if allow:
        return
    if not id_ok:
        raise ReleasePinError(
            f"Pinned databook release {pin_id} "
            f"≠ current {cur.release_id} (v{cur.version}); "
            "pass allow_pinned_release=true to intentionally pin"
        )
    raise ReleasePinError(
        f"Pinned databook version {pin_ver} ≠ current {cur.version} "
        f"for release {cur.release_id}"
    )


def assert_g6_allowed(manifest: FddRunManifest) -> None:
    if manifest.draft_mode or manifest.g6_blocked or not manifest.contract_complete:
        raise GateBlockedError(
            "G6 unavailable while FDD run is in draft mode "
            f"(run={manifest.run_id}, draft_mode={manifest.draft_mode}, "
            f"g6_blocked={manifest.g6_blocked}, "
            f"contract_complete={manifest.contract_complete}, "
            f"reasons={list(manifest.contract_reasons or [])[:5]})"
        )


def g6_allowed(manifest: FddRunManifest) -> bool:
    return (
        not manifest.draft_mode
        and not manifest.g6_blocked
        and bool(manifest.contract_complete)
    )


_PHASE0_STUB_EXHIBIT_IDS = frozenset({"ex_hist_pl", "ex_hist_bs"})


def _scale_header_from_facts(
    facts: list[FddFact], *, company: str | None = None
) -> str | None:
    """Currency/scale banner for exhibits — release id lives only on standards/manifest."""
    curs = sorted(
        {(f.currency or "").strip() for f in facts if (f.currency or "").strip()}
    )
    scales = sorted(
        {(f.scale or "").strip() for f in facts if (f.scale or "").strip()}
    )
    if len(curs) > 1 or len(scales) > 1:
        cur_part = " / ".join(curs) if curs else None
        scale_part = " / ".join(scales) if scales else None
        unit = " ".join(p for p in (cur_part, scale_part) if p)
        if unit:
            unit = f"{unit} (Mixed Units)"
    else:
        cur = curs[0] if curs else None
        scale = scales[0] if scales else None
        unit = " ".join(p for p in (cur, scale) if p) or None
    parts = [p for p in (company, unit) if p]
    return " · ".join(parts) if parts else None

def _phase0_stub_metrics_covered(store: ExhibitStoreDoc, facts: list[FddFact]) -> bool:
    """True when bridged facts cover the P&L stub's anchor metric (revenue).

    Extra hand-seed display cells (e.g. EBITDA) do not block eviction once
    revenue is present in the release — databook exhibits replace the stubs.
    """
    stub = next(
        (e for e in store.exhibits if e.exhibit_id == "ex_hist_pl"),
        None,
    )
    if stub is None:
        return bool(facts)
    have = {f.metric_key for f in facts}
    if "revenue" in {c.metric_key for c in stub.cells} and "revenue" in have:
        return True
    needed = {c.metric_key for c in stub.cells if c.metric_key}
    if not needed:
        return True
    return needed.issubset(have)


def bridge_release_into_run(
    deal_slug: str,
    run_id: str,
    *,
    release: DatabookRelease | None = None,
    release_id: str | None = None,
    bootstrap: bool = True,
    allow_pinned_release: bool = False,
    company: str | None = None,
) -> tuple[FddRunManifest, FactTableDoc, ExhibitStoreDoc, DatabookContractAssessment]:
    """Assess contract, write fact table, populate exhibits, update manifest."""
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")

    rel = release or resolve_release_for_deal(
        deal_slug, release_id=release_id or manifest.databook_release_id, bootstrap=bootstrap
    )
    assessment = assess_databook_contract(rel, deal_slug=deal_slug)
    facts = facts_from_release(rel, draft_mode=assessment.draft_mode) if rel else []

    fact_doc = FactTableDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at="",
        databook_release_id=assessment.release_id,
        databook_release_version=assessment.release_version,
        draft_mode=assessment.draft_mode,
        contract_complete=assessment.complete,
        g6_blocked=not assessment.g6_allowed,
        reasons=list(assessment.reasons),
        facts=facts,
    )
    fact_doc = save_fact_table(fact_doc)

    store = load_exhibit_store(deal_slug, run_id) or ExhibitStoreDoc(
        run_id=run_id, deal_slug=deal_slug, updated_at="", exhibits=[]
    )
    if facts:
        # Evict Phase-0 hand stubs only when databook facts cover P&L stub metrics.
        if _phase0_stub_metrics_covered(store, facts):
            kept = [
                e
                for e in store.exhibits
                if e.exhibit_id not in _PHASE0_STUB_EXHIBIT_IDS
            ]
            store = store.model_copy(update={"exhibits": kept})
        store = apply_facts_to_store(store, facts)
        header = _scale_header_from_facts(facts, company=company)
        if header:
            # Always refresh — sticky headers previously froze an old release id
            store = store.model_copy(
                update={
                    "exhibits": [
                        e.model_copy(update={"scale_header": header})
                        for e in store.exhibits
                    ]
                }
            )
    store = persist_store(deal_slug, run_id, store)

    manifest = manifest.model_copy(
        update={
            "stage": RunStage.P1,
            "draft_mode": assessment.draft_mode,
            "contract_complete": assessment.complete,
            "g6_blocked": not assessment.g6_allowed,
            "allow_pinned_release": allow_pinned_release
            or manifest.allow_pinned_release,
            "databook_release_id": assessment.release_id
            or manifest.databook_release_id,
            "databook_release_version": assessment.release_version
            if assessment.release_version is not None
            else manifest.databook_release_version,
            "contract_reasons": list(assessment.reasons),
            "model_versions": {
                **dict(manifest.model_versions or {}),
                "fdd_phase1": BRIDGE_VERSION,
            },
            "status": ArtefactStatus.DRAFT
            if assessment.draft_mode
            else ArtefactStatus.CHECKED,
        }
    )
    manifest = save_manifest(manifest)
    return manifest, fact_doc, store, assessment
