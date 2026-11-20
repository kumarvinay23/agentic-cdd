"""FDD findings ledger — structured cards from claims, G3, QoE, and held sections."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    CommentaryDoc,
    ExhibitCell,
    ExhibitStoreDoc,
    Finding,
    FindingSeverity,
    FindingSource,
    FindingsDoc,
)
from agetic_cdd_api.services_fdd_checks import G3_HELD_PREFIX, g3_hold_reason
from agetic_cdd_api.services_fdd_store import (
    load_claims_ledger,
    load_commentary,
    load_exhibit_store,
    load_manifest,
    load_qoe_workbook,
    load_request_list,
    save_manifest,
)

FINDINGS_VERSION = "1.1.0"  # Fix 5 — register records; claims/RFIs are not findings
_MAX_CLAIM_FINDINGS = 12
# Absolute USD-M gap for core P&L claim contradictions. Below this → MODERATE.
_CLAIM_HIGH_ABS = 0.03
_LARGE_GAP_REL = 0.02  # kept for tests / relative upgrade path
_SECTION_FOR_METRIC = {
    "revenue": "SEC-B",
    "ebitda": "SEC-B",
    "gross_margin": "SEC-C",
    "gross_profit": "SEC-C",
    "cogs": "SEC-D",
    "sga": "SEC-D",
    "grr": "SEC-K",
    "nrr": "SEC-K",
    "grr_residential": "SEC-K",
    "grr_commercial": "SEC-K",
    "nrr_residential": "SEC-K",
    "nrr_commercial": "SEC-K",
}

_SEVERITY_RANK = {
    FindingSeverity.HIGH: 0,
    FindingSeverity.MODERATE: 1,
    FindingSeverity.LOW: 2,
    FindingSeverity.INFO: 3,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fid(*parts: str) -> str:
    raw = "|".join(parts)
    return "fnd_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _counts(findings: list[Finding]) -> dict[str, int]:
    out = {s.value: 0 for s in FindingSeverity}
    for f in findings:
        out[f.severity.value] = out.get(f.severity.value, 0) + 1
    out["total"] = len(findings)
    return out


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_RANK.get(f.severity, 9), f.section_id or "", f.title),
    )


def top_findings(findings: list[Finding], *, limit: int = 5) -> list[Finding]:
    """Surface IC-priority findings first: severity, then business MODEL over claims."""

    def _rank(f: Finding) -> tuple:
        src = f.source
        # Prefer model / QoE business findings over source-reconciliation claims.
        src_rank = 0 if src == FindingSource.MODEL else (
            1 if src == FindingSource.QOE else (
                2 if src == FindingSource.G3 else 3
            )
        )
        return (
            _SEVERITY_RANK.get(f.severity, 9),
            src_rank,
            f.section_id or "",
            f.title,
        )

    return sorted(findings, key=_rank)[: max(0, limit)]


def format_finding_card(finding: Finding) -> str:
    """Plain-text card body for report_spec nodes (PDF parses KEY FINDING layout)."""
    lines = [
        f"[{finding.severity.value.upper()}] {finding.title}",
        f"Observation: {finding.observation}" if finding.observation else "",
        f"Implication: {finding.implication}" if finding.implication else "",
        f"Ask management: {finding.ask_management}" if finding.ask_management else "",
    ]
    if finding.evidence_refs:
        lines.append("Evidence: " + "; ".join(finding.evidence_refs[:6]))
    return "\n".join(ln for ln in lines if ln)


def finding_page_title(finding: Finding) -> str:
    """Report page title — short id · headline (Compost Crew Latest style)."""
    short = (finding.finding_id or "fnd")[-4:].upper()
    section = (finding.section_id or "").replace("SEC-", "")
    prefix = f"{section}{short}" if section else short
    return f"{prefix} · {finding.title}"[:120]


def _from_claims(deal_slug: str, run_id: str) -> list[Finding]:
    """Fix 5 — claim contradictions are NOT findings.

    Failed agent claims stay on the claims ledger and open information
    requests / gaps. Rule and claim bookkeeping must not crowd the IC findings
    register.
    """
    _ = (deal_slug, run_id, load_claims_ledger, _MAX_CLAIM_FINDINGS, _CLAIM_HIGH_ABS)
    return []


def _from_g3(store: ExhibitStoreDoc) -> list[Finding]:
    out: list[Finding] = []
    for ex in store.exhibits or []:
        reason = g3_hold_reason(ex)
        if not reason:
            for fn in ex.footnotes or []:
                text = str(fn)
                if text.startswith(G3_HELD_PREFIX):
                    reason = text[len(G3_HELD_PREFIX) :] or "model checks failed"
                    break
        if not reason:
            continue
        section = ex.section_id or "SEC-K"
        core = section in {"SEC-B", "SEC-C", "SEC-E"}
        out.append(
            Finding(
                finding_id=_fid("g3", ex.exhibit_id),
                section_id=section,
                severity=FindingSeverity.HIGH if core else FindingSeverity.MODERATE,
                title=f"Model check hold — {ex.title or ex.exhibit_id}",
                observation=reason[:400],
                implication="Section commentary is held until the model check pack passes.",
                ask_management="Confirm which source basis should drive this exhibit.",
                evidence_refs=[ex.exhibit_id],
                source=FindingSource.G3,
            )
        )
    return out


def _from_qoe(deal_slug: str, run_id: str) -> list[Finding]:
    qoe = load_qoe_workbook(deal_slug, run_id)
    if qoe is None:
        return [
            Finding(
                finding_id=_fid("qoe", run_id, "missing"),
                section_id="SEC-E",
                severity=FindingSeverity.MODERATE,
                title="QoE workbook not built",
                observation="Quality of earnings adjustments have not been built for this run.",
                implication="IC headline remains on unadjusted earnings until QoE is complete.",
                ask_management="Provide a normalisation bridge for the closed year.",
                evidence_refs=[],
                source=FindingSource.QOE,
            )
        ]
    out: list[Finding] = []
    register = list(getattr(qoe, "register_rows", None) or [])
    if not register and not getattr(qoe, "g4_approved", False):
        out.append(
            Finding(
                finding_id=_fid("qoe", run_id, "pending"),
                section_id="SEC-E",
                severity=FindingSeverity.MODERATE,
                title="QoE adjustments pending",
                observation="Reported EBITDA is shown unadjusted; no material QoE items registered.",
                implication="Sustainable earnings may differ once normalisations are agreed.",
                ask_management="Confirm one-off / non-recurring items for the closed year.",
                evidence_refs=["ex_qoe_bridge"],
                source=FindingSource.QOE,
            )
        )
    return out


def _from_held_sections(commentary: CommentaryDoc | None) -> list[Finding]:
    if commentary is None:
        return []
    out: list[Finding] = []
    for draft in commentary.sections or []:
        if not draft.held_back:
            continue
        severity = (
            FindingSeverity.INFO
            if draft.section_id == "SEC-J"
            else FindingSeverity.MODERATE
        )
        out.append(
            Finding(
                finding_id=_fid("held", draft.section_id or "x"),
                section_id=draft.section_id,
                severity=severity,
                title=f"{draft.title or draft.section_id} held back",
                observation=draft.held_back_reason or "Section pending figure coverage.",
                implication="Do not treat this section as complete for IC purposes.",
                ask_management="Supply the missing schedules or confirm the section is out of scope.",
                evidence_refs=[draft.section_id] if draft.section_id else [],
                source=FindingSource.HELD_SECTION,
            )
        )
    return out


def _from_requests(
    deal_slug: str,
    run_id: str,
    *,
    covered_claim_keys: set[str] | None = None,
) -> list[Finding]:
    """Fix 5 — open RFIs are requests, not findings (GOV-03 info_request)."""
    _ = (deal_slug, run_id, covered_claim_keys, load_request_list)
    return []


def _mechanism_for(finding: Finding) -> str:
    sev = finding.severity
    if sev == FindingSeverity.HIGH:
        return "condition"
    if sev == FindingSeverity.MODERATE:
        return "covenant"
    return "information"


def _tier_for(finding: Finding) -> str:
    refs = list(finding.evidence_refs or [])
    for ref in refs:
        t = str(ref).strip().upper()
        if t in {"A", "B", "C"}:
            return t
    src = finding.source
    if src in {FindingSource.MODEL, FindingSource.QOE}:
        return "B"
    if src == FindingSource.G3:
        return "B"
    return "C" if src == FindingSource.HELD_SECTION else "B"


def _enrich_finding_record(finding: Finding, *, display_id: str) -> Finding:
    """Fill Fix 5 register fields from existing prose when unset."""
    quant = (finding.quantified_effect or "").strip()
    if not quant:
        for blob in (finding.implication, finding.observation):
            if blob:
                quant = " ".join(str(blob).split())[:72]
                break
        if not quant:
            quant = "Size / effect pending"
    protection = (finding.protection or "").strip()
    if not protection:
        protection = (
            " ".join(str(finding.ask_management).split())[:70]
            if finding.ask_management
            else "Confirm with management / counsel"
        )
    mechanism = finding.mechanism or _mechanism_for(finding)
    tier = (finding.tier_or_grade or "").strip() or _tier_for(finding)
    area = (finding.area or "").strip() or (finding.section_id or "").replace("SEC-", "")
    fact_ids = list(finding.fact_ids or [])
    if not fact_ids:
        fact_ids = [
            r
            for r in (finding.evidence_refs or [])
            if r and not str(r).lower().startswith(("req_", "fnd_", "claim"))
        ]
    return finding.model_copy(
        update={
            "display_id": display_id,
            "area": area[:40],
            "quantified_effect": quant[:120],
            "tier_or_grade": tier,
            "protection": protection[:120],
            "mechanism": mechanism,
            "fact_ids": fact_ids[:8],
            "slide_ref": finding.slide_ref or "ch_es_findings",
        }
    )


def assign_findings_register(
    findings: list[Finding],
    *,
    population_limit: int = 12,
) -> tuple[list[Finding], list[str]]:
    """Assign stable F01… display_ids; declare the IC population."""
    ranked = top_findings(findings, limit=max(population_limit, len(findings)))
    # Population = diligence items that may appear on ES / protections (high/mod first).
    population_src = [
        f
        for f in ranked
        if f.severity in {FindingSeverity.HIGH, FindingSeverity.MODERATE}
    ] or ranked[:population_limit]
    population_src = population_src[:population_limit]
    id_by_finding: dict[str, str] = {}
    for i, f in enumerate(population_src, start=1):
        id_by_finding[f.finding_id] = f"F{i:02d}"
    # Remaining findings get F-numbers after the population for stable refs.
    next_i = len(population_src) + 1
    enriched: list[Finding] = []
    for f in sort_findings(findings):
        did = id_by_finding.get(f.finding_id)
        if not did:
            did = f"F{next_i:02d}"
            next_i += 1
        enriched.append(_enrich_finding_record(f, display_id=did))
    population = [id_by_finding[f.finding_id] for f in population_src]
    return enriched, population


def materialize_findings_register(
    findings_doc: FindingsDoc | None,
    *,
    limit: int = 12,
) -> list[Finding]:
    """Return population findings in display_id order for ES / protections."""
    if findings_doc is None:
        return []
    by_id = {
        f.display_id: f
        for f in (findings_doc.findings or [])
        if getattr(f, "display_id", None)
    }
    pop = list(findings_doc.population or [])
    if pop:
        return [by_id[d] for d in pop if d in by_id][:limit]
    # Fallback for older docs without population.
    return top_findings(list(findings_doc.findings or []), limit=limit)


def _from_doubtful_headlines(store: ExhibitStoreDoc) -> list[Finding]:
    """Doubtful closed-year revenue/EBITDA → moderate finding.

    When the CDD accounts extract already supplies usable revenue for that year,
    skip the revenue nag — ES/trading price the CDD spine instead.
    """
    from datetime import date

    from agetic_cdd_api.services_fdd_chapters import _cdd_evidence_revenue_by_year

    out: list[Finding] = []
    closed_cutoff = date.today().year - 1
    deal_slug = str(getattr(store, "deal_slug", None) or "").strip()
    cdd_rev = _cdd_evidence_revenue_by_year(deal_slug) if deal_slug else {}
    for ex in store.exhibits or []:
        if ex.exhibit_id not in {"ex_m1_trading", "ex_m2_margin", "ex_db_is"}:
            continue
        for cell in ex.cells or []:
            if cell.fiscal_year is not None and int(cell.fiscal_year) > closed_cutoff:
                continue
            mk = (cell.metric_key or "").lower()
            if mk not in {"revenue", "ebitda"}:
                continue
            if cell.status not in {CellStatus.DOUBTFUL, CellStatus.DRAFT}:
                continue
            if cell.fiscal_year is None:
                continue
            year = int(cell.fiscal_year)
            if mk == "revenue" and year in cdd_rev:
                continue
            # Years without a CDD spine stay informational — do not block pricing noise.
            severity = FindingSeverity.MODERATE
            implication = "Confirm source basis before using this figure in pricing."
            if mk == "revenue" and year not in cdd_rev:
                severity = FindingSeverity.INFO
                implication = (
                    "FY column stays blank on ES/trading; CDD spine has no usable "
                    f"{year} revenue — confirm basis only if that year is needed."
                )
            out.append(
                Finding(
                    finding_id=_fid("doubt", ex.exhibit_id, mk, str(cell.fiscal_year)),
                    section_id=_SECTION_FOR_METRIC.get(mk, "SEC-B"),
                    severity=severity,
                    title=f"Doubtful {mk} FY{cell.fiscal_year}",
                    observation=(
                        f"{ex.title or ex.exhibit_id}: {mk} FY{cell.fiscal_year} "
                        f"is tagged {cell.status.value}."
                    ),
                    implication=implication,
                    ask_management=f"Confirm the preferred basis for {mk} FY{cell.fiscal_year}.",
                    evidence_refs=[f"{ex.exhibit_id}.{cell.cell_id}"],
                    source=FindingSource.SOURCE_BASIS_GAP,
                )
            )
    # Deduplicate by title
    seen: set[str] = set()
    uniq: list[Finding] = []
    for f in out:
        if f.title in seen:
            continue
        seen.add(f.title)
        uniq.append(f)
    return uniq[:6]


def _cell_by_metric(
    store: ExhibitStoreDoc,
    exhibit_ids: set[str],
    metric_key: str,
    year: int,
) -> ExhibitCell | None:
    want = metric_key.lower()
    for ex in store.exhibits or []:
        if ex.exhibit_id not in exhibit_ids:
            continue
        for cell in ex.cells or []:
            if (
                (cell.metric_key or "").lower() == want
                and cell.fiscal_year == year
                and cell.value is not None
            ):
                return cell
    return None


def _cell_source_kind(cell: ExhibitCell | None) -> str:
    from agetic_cdd_api.services_fdd_sources import classify_source

    if cell is None:
        return "unknown"
    blob = " ".join(
        str(x or "")
        for x in (
            cell.basis_label,
            cell.label,
            cell.model_id,
            " ".join(str(s) for s in (getattr(cell, "sources", None) or [])[:3]),
        )
    )
    kind = classify_source(blob)
    if kind != "unknown":
        return kind
    low = blob.lower()
    if "monthly pack" in low or "management" in low:
        return "management"
    if "workbook" in low or (cell.model_id or "").upper() in {"M1", "M2", "M8"}:
        return "workbook"
    return "unknown"


def _pack_metric_from_claims(
    deal_slug: str,
    run_id: str,
    *,
    metric_key: str,
    years: set[int],
) -> dict[int, float]:
    """Prefer claimed pack figures when they diverge from the workbook databook."""
    ledger = load_claims_ledger(deal_slug, run_id)
    if ledger is None:
        return {}
    best: dict[int, tuple[int, float]] = {}
    want = metric_key.lower()
    for claim in ledger.claims or []:
        if (claim.metric_key or "").lower() != want:
            continue
        if claim.fiscal_year is None or int(claim.fiscal_year) not in years:
            continue
        if claim.claimed_value is None:
            continue
        try:
            cv = float(claim.claimed_value)
        except (TypeError, ValueError):
            continue
        # Sticky raw grain (98097 / 9436) must never win over SME-scale pack figures.
        if abs(cv) >= 1000.0:
            continue
        if 1e-6 < abs(cv) < 0.05:
            continue
        score = 0
        if claim.databook_value is not None:
            try:
                if abs(cv - float(claim.databook_value)) > 0.001:
                    score = 2  # pack alternate vs workbook databook
            except (TypeError, ValueError):
                score = 1
        # Prefer SME-plausible millions when scores tie.
        if abs(cv) < 1000.0:
            score += 1
        prev = best.get(int(claim.fiscal_year))
        if prev is None or score > prev[0]:
            best[int(claim.fiscal_year)] = (score, cv)
    return {y: val for y, (_score, val) in best.items()}


def _from_cost_pressure(
    store: ExhibitStoreDoc,
    *,
    deal_slug: str | None = None,
    run_id: str | None = None,
) -> list[Finding]:
    """Business finding: opex outgrew revenue while EBITDA fell (one basis)."""
    from datetime import date

    from agetic_cdd_api.services_fdd_sources import display_source_name
    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    closed = date.today().year - 1
    prior = closed - 1
    sga_yoy = _cell_by_metric(store, {"ex_m3_costs"}, "sga_yoy", closed)
    labor_yoy = _cell_by_metric(store, {"ex_m3_costs"}, "labor_yoy", closed)

    def _yoy_from_levels(metric: str) -> ExhibitCell | None:
        """Fallback when M3 YoY cells are missing after a sticky-scale rebuild."""
        curr = _cell_by_metric(
            store, {"ex_m3_costs", "ex_db_is", "ex_m1_trading"}, metric, closed
        )
        prev = _cell_by_metric(
            store, {"ex_m3_costs", "ex_db_is", "ex_m1_trading"}, metric, prior
        )
        if curr is None or prev is None or prev.value in (None, 0):
            return None
        try:
            pct = (float(curr.value) - float(prev.value)) / abs(float(prev.value)) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            return None
        return curr.model_copy(
            update={
                "metric_key": f"{metric}_yoy",
                "value": pct,
                "cell_id": f"{metric}_yoy_fy{closed}",
                "label": f"{metric} YoY % FY{closed}",
            }
        )

    if sga_yoy is None:
        sga_yoy = _yoy_from_levels("sga")
    if labor_yoy is None:
        labor_yoy = _yoy_from_levels("labor") or _yoy_from_levels("payroll")

    # Trading-pack fallback — same inputs as the FY24→FY25 cost bridge slide.
    pack_rev_pct: float | None = None
    pack_labor_pct: float | None = None
    pack_sga_pct: float | None = None
    pack_eb_prior: float | None = None
    pack_eb_curr: float | None = None
    if deal_slug:
        try:
            from agetic_cdd_api.services_fdd_trading import (
                _sga_ex_dep,
                _total_labour,
                build_trading_pack,
            )

            pack = build_trading_pack(deal_slug)
        except Exception:
            pack = None
        if pack is not None:
            rev_p = (pack.fy.get("Revenue") or pack.revenue_fy or {}).get(prior)
            rev_c = (pack.fy.get("Revenue") or pack.revenue_fy or {}).get(closed)
            if rev_p not in (None, 0) and rev_c is not None:
                try:
                    pack_rev_pct = (float(rev_c) - float(rev_p)) / abs(float(rev_p)) * 100.0
                except (TypeError, ValueError, ZeroDivisionError):
                    pack_rev_pct = None
            labor_p = _total_labour(pack, prior)
            labor_c = _total_labour(pack, closed)
            if labor_p not in (None, 0) and labor_c is not None:
                try:
                    pack_labor_pct = (
                        (float(labor_c) - float(labor_p)) / abs(float(labor_p)) * 100.0
                    )
                except (TypeError, ValueError, ZeroDivisionError):
                    pack_labor_pct = None
            sga_p = _sga_ex_dep(pack, prior)
            sga_c = _sga_ex_dep(pack, closed)
            if sga_p not in (None, 0) and sga_c is not None:
                try:
                    pack_sga_pct = (float(sga_c) - float(sga_p)) / abs(float(sga_p)) * 100.0
                except (TypeError, ValueError, ZeroDivisionError):
                    pack_sga_pct = None
            # Prefer management EBITDA for the cost-pressure story when present.
            eb_series = pack.fy.get("EBITDA (management)") or pack.fy.get("EBITDA") or {}
            pack_eb_prior = eb_series.get(prior)
            pack_eb_curr = eb_series.get(closed)
            if labor_yoy is None and pack_labor_pct is not None:
                labor_yoy = ExhibitCell(
                    cell_id=f"labor_yoy_fy{closed}",
                    exhibit_id="ex_m3_costs",
                    label=f"Labour YoY % FY{closed}",
                    value=float(pack_labor_pct),
                    metric_key="labor_yoy",
                    fiscal_year=closed,
                    fact_id=f"pack:labor_yoy:{closed}",
                    status=CellStatus.PROVEN,
                )
            if sga_yoy is None and pack_sga_pct is not None:
                sga_yoy = ExhibitCell(
                    cell_id=f"sga_yoy_fy{closed}",
                    exhibit_id="ex_m3_costs",
                    label=f"SG&A YoY % FY{closed}",
                    value=float(pack_sga_pct),
                    metric_key="sga_yoy",
                    fiscal_year=closed,
                    fact_id=f"pack:sga_yoy:{closed}",
                    status=CellStatus.PROVEN,
                )

    if sga_yoy is None and labor_yoy is None:
        return []

    def _plausible_money(v: float | None) -> bool:
        if v is None:
            return False
        try:
            x = abs(float(v))
        except (TypeError, ValueError):
            return False
        return x >= 0.05 and x < 1000.0

    # Revenue growth: prefer coherent M3 levels; skip sticky dust (0.039).
    rev_curr = _cell_by_metric(store, {"ex_m3_costs"}, "revenue", closed)
    rev_prior = _cell_by_metric(store, {"ex_m3_costs"}, "revenue", prior)
    rev_pct: float | None = None
    rev_refs: list[str] = []
    rev_basis = "monthly pack"
    if (
        rev_curr is not None
        and rev_prior is not None
        and _plausible_money(rev_prior.value)
        and _plausible_money(rev_curr.value)
    ):
        try:
            rev_pct = (
                (float(rev_curr.value) - float(rev_prior.value))
                / abs(float(rev_prior.value))
                * 100.0
            )
            rev_refs = [
                f"ex_m3_costs.{rev_prior.cell_id}",
                f"ex_m3_costs.{rev_curr.cell_id}",
            ]
        except (TypeError, ValueError, ZeroDivisionError):
            rev_pct = None
    if rev_pct is None:
        rev_yoy = _cell_by_metric(
            store, {"ex_m1_trading", "ex_m2_margin"}, "revenue_yoy", closed
        )
        if rev_yoy is not None:
            try:
                cand = float(rev_yoy.value)
                # Ignore absurd YoY artefacts from sticky rebuilds.
                if abs(cand) <= 200.0:
                    rev_pct = cand
                    rev_refs = [f"{rev_yoy.exhibit_id}.{rev_yoy.cell_id}"]
                    rev_basis = "investor workbook"
            except (TypeError, ValueError):
                rev_pct = None
    if rev_pct is None and pack_rev_pct is not None:
        rev_pct = pack_rev_pct
        rev_basis = "monthly pack"
        rev_refs = [f"pack:revenue:FY{prior}", f"pack:revenue:FY{closed}"]
    if rev_pct is None:
        return []

    # EBITDA pair: store (same basis) → trading pack → SME-plausible claims.
    # Pack before claims so sticky claim leftovers (98097) cannot block the story.
    ebitda_by_kind: dict[str, dict[int, ExhibitCell]] = {}
    for ex in store.exhibits or []:
        if ex.exhibit_id not in {
            "ex_m1_trading",
            "ex_m2_margin",
            "ex_db_is",
            "ex_db_metrics",
            "ex_m7_cash",
        }:
            continue
        for cell in ex.cells or []:
            if (cell.metric_key or "").lower() != "ebitda":
                continue
            if cell.fiscal_year not in {prior, closed} or cell.value is None:
                continue
            if not _plausible_money(cell.value):
                continue
            kind = _cell_source_kind(cell)
            ebitda_by_kind.setdefault(kind, {})[int(cell.fiscal_year)] = cell

    eb_prior_v: float | None = None
    eb_curr_v: float | None = None
    eb_basis = "investor workbook"
    eb_refs: list[str] = []
    for kind in ("management", "workbook"):
        pair = ebitda_by_kind.get(kind) or {}
        if prior in pair and closed in pair and pair[prior].value not in (None, 0):
            try:
                eb_prior_v = float(pair[prior].value)
                eb_curr_v = float(pair[closed].value)
            except (TypeError, ValueError):
                continue
            eb_basis = display_source_name(kind)
            eb_refs = [
                f"{pair[prior].exhibit_id}.{pair[prior].cell_id}",
                f"{pair[closed].exhibit_id}.{pair[closed].cell_id}",
            ]
            break

    if eb_prior_v is None and pack_eb_prior not in (None, 0) and pack_eb_curr is not None:
        if _plausible_money(pack_eb_prior) and _plausible_money(pack_eb_curr):
            eb_prior_v = float(pack_eb_prior)
            eb_curr_v = float(pack_eb_curr)
            eb_basis = "monthly pack"
            eb_refs = [f"pack:ebitda:FY{prior}", f"pack:ebitda:FY{closed}"]

    if eb_prior_v is None and deal_slug and run_id:
        pack_eb = _pack_metric_from_claims(
            deal_slug, run_id, metric_key="ebitda", years={prior, closed}
        )
        if (
            prior in pack_eb
            and closed in pack_eb
            and _plausible_money(pack_eb[prior])
            and _plausible_money(pack_eb[closed])
        ):
            eb_prior_v = pack_eb[prior]
            eb_curr_v = pack_eb[closed]
            eb_basis = "monthly pack"
            eb_refs = [f"claim:ebitda:FY{prior}", f"claim:ebitda:FY{closed}"]

    if eb_prior_v is None or eb_curr_v is None or eb_prior_v == 0 or rev_pct is None:
        return []
    eb_change = (eb_curr_v - eb_prior_v) / abs(eb_prior_v)
    if eb_change >= 0:
        return []

    cost_bits: list[str] = []
    refs: list[str] = []
    pressure = False
    if labor_yoy is not None:
        try:
            labor_pct = float(labor_yoy.value)
        except (TypeError, ValueError):
            labor_pct = None
        if labor_pct is not None and labor_pct > rev_pct + 0.5:
            pressure = True
            cost_bits.append(
                f"labour grew {format_fdd_number(labor_pct)}% "
                f"while revenue grew {format_fdd_number(rev_pct)}% "
                f"({rev_basis})"
            )
            refs.append(f"ex_m3_costs.{labor_yoy.cell_id}")
    if sga_yoy is not None:
        try:
            sga_pct = float(sga_yoy.value)
        except (TypeError, ValueError):
            sga_pct = None
        if sga_pct is not None and sga_pct > rev_pct + 0.5:
            pressure = True
            cost_bits.append(f"SG&A grew {format_fdd_number(sga_pct)}%")
            refs.append(f"ex_m3_costs.{sga_yoy.cell_id}")
    if not pressure or not cost_bits:
        return []
    refs.extend(rev_refs)
    refs.extend(eb_refs)
    eb_pct = abs(eb_change) * 100.0
    obs = (
        f"EBITDA fell about {format_fdd_number(eb_pct)}% into FY{closed} "
        f"({format_fdd_number(eb_prior_v)} → {format_fdd_number(eb_curr_v)}, "
        f"{eb_basis}) as "
        + " and ".join(cost_bits)
        + "."
    )
    return [
        Finding(
            finding_id=_fid("cost_pressure", str(closed)),
            section_id="SEC-D",
            severity=FindingSeverity.HIGH,
            title=f"Cost growth outpaced revenue into FY{closed}",
            observation=obs[:420],
            implication=(
                "Earnings compression is driven by opex intensity, not revenue "
                "decline — diligence should test whether labour and SG&A growth "
                "is structural or one-off."
            ),
            ask_management=(
                f"Please explain the FY{closed} labour and SG&A step-up versus "
                f"revenue growth, and which costs are expected to persist."
            ),
            evidence_refs=refs[:8],
            source=FindingSource.MODEL,
        )
    ]


def _ic_money(val: float | None) -> str:
    """Prose money for IC quantified_effect / observation (store units = $m)."""
    from agetic_cdd_api.services_fdd_format import format_display

    return format_display(
        val,
        money=True,
        prose=True,
        store_scale="M",
        display_scale="k",
    )


def _from_ic_diligence(
    store: ExhibitStoreDoc,
    *,
    deal_slug: str | None = None,
) -> list[Finding]:
    """IC-style diligence findings (concentration, leases, dividends, funding, rights).

    Complements cost-pressure / QoE so the ES register can surface a Crew-like
    set without promoting claims or RFIs into findings (Fix 5).
    """
    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    slug = (deal_slug or str(getattr(store, "deal_slug", "") or "")).strip()
    out: list[Finding] = []

    # Shared cash/BS pack for dividend / lease / funding fallbacks.
    try:
        from agetic_cdd_api.services_fdd_chapter_depth import build_cash_bs_pack

        bsp = build_cash_bs_pack(slug) if slug else None
    except Exception:
        bsp = None

    # --- Concentration ---
    try:
        from agetic_cdd_api.services_fdd_trading import (
            build_trading_pack,
            concentration_rows,
        )

        pack = build_trading_pack(slug) if slug else None
    except Exception:
        pack = None
    if pack is not None:
        conc = concentration_rows(pack, year=2025) or []
        top_share = next(
            (
                float(v)
                for lab, v, _k in conc
                if v is not None
                and "share of total revenue" in str(lab).lower()
                and "municipal share" not in str(lab).lower()
            ),
            None,
        )
        muni_share = next(
            (
                float(v)
                for lab, v, _k in conc
                if v is not None and "municipal share" in str(lab).lower()
            ),
            None,
        )
        share = top_share if top_share is not None else muni_share
        if share is not None and share >= 0.15:
            pct = format_fdd_number(share * 100.0 if share <= 1.5 else share)
            out.append(
                Finding(
                    finding_id=_fid("ic", "concentration", slug or "deal"),
                    section_id="SEC-C",
                    severity=FindingSeverity.HIGH if share >= 0.20 else FindingSeverity.MODERATE,
                    title="Customer / channel concentration is material",
                    observation=(
                        f"Largest evidenced share is {pct}% of FY25 revenue; "
                        "contract term and renewal evidence remain open."
                    ),
                    implication="Earnings and retention risk concentrate in one relationship.",
                    ask_management="Provide the customer agreement, options, and renewal history.",
                    evidence_refs=["B", "ex_m1_trading"],
                    source=FindingSource.MODEL,
                    area="Trading",
                    quantified_effect=f"{pct}% of FY25 revenue",
                    protection="Obtain agreement and option evidence before pricing concentration risk",
                    mechanism="condition",
                    tier_or_grade="B",
                )
            )

    # --- Dividend arrears / debt-like ---
    div = _cell_by_metric(
        store, {"ex_m6_net_debt", "ex_m8_bs", "ex_db_bs"}, "dividends_payable", 2025
    )
    if div is None:
        div = _cell_by_metric(
            store, {"ex_m6_net_debt", "ex_m8_bs", "ex_db_bs"}, "dividend_payable", 2025
        )
    if div is None:
        div = _cell_by_metric(
            store, {"ex_m6_net_debt", "ex_m8_bs", "ex_db_bs"}, "dividends", 2025
        )
    div_val: float | None = None
    div_fact: str | None = None
    if div is not None and isinstance(div.value, (int, float)):
        div_val = abs(float(div.value))
        div_fact = str(div.fact_id) if div.fact_id else None
    # Prefer Jul-26 accrued (matches ES KPI) then FY25 from cash/BS pack.
    if bsp is not None:
        pack_div = bsp.dividends_payable.get("Jul-26")
        if pack_div is None:
            pack_div = bsp.dividends_payable.get(2025)
        if pack_div is not None and abs(float(pack_div)) >= 0.05:
            if div_val is None or abs(float(pack_div)) >= div_val:
                div_val = abs(float(pack_div))
    if div_val is not None and div_val >= 0.05:
        amt = _ic_money(div_val)
        out.append(
            Finding(
                finding_id=_fid("ic", "dividends", slug or "deal", f"{div_val:.3f}"),
                section_id="SEC-G",
                severity=FindingSeverity.HIGH,
                title="Accrued dividends are debt-like for value",
                observation=(
                    f"Dividends payable of about {amt} remain outstanding; "
                    "treat as debt-like until settled or waived."
                ),
                implication="Equity value and net debt shift once arrears are recognised as debt-like.",
                ask_management="Confirm Series preferred dividend policy, arrears, and settlement path.",
                evidence_refs=["B", div_fact or "ex_m6_net_debt"],
                source=FindingSource.MODEL,
                area="Balance sheet",
                quantified_effect=f"Dividends payable ~{amt}",
                protection="SPA / price for dividend arrears as debt-like",
                mechanism="price",
                tier_or_grade="B",
                fact_ids=[div_fact] if div_fact else [],
            )
        )

    # --- Lease / commitment evidence ---
    rent = _cell_by_metric(store, {"ex_m3_costs", "ex_db_is", "ex_m1_trading"}, "rent", 2025)
    lease_missing = True
    rent_val: float | None = None
    if bsp is not None and getattr(bsp, "evidenced_lease_rent_m", None) is not None:
        lease_missing = False
    if rent is not None and rent.value is not None:
        rent_val = float(rent.value)
    elif bsp is not None and getattr(bsp, "rent_fy25", None) is not None:
        rent_val = float(bsp.rent_fy25)
    if lease_missing:
        quant = f"FY25 rent ~{_ic_money(rent_val)}" if rent_val is not None else "Lease schedule missing"
        out.append(
            Finding(
                finding_id=_fid("ic", "leases", slug or "deal"),
                section_id="SEC-G",
                severity=FindingSeverity.MODERATE,
                title="Lease commitments are largely unevidenced",
                observation=(
                    "Rent expense is in the accounts but lease files / ASC 842 schedules "
                    "are incomplete or PARTIAL — commitments cannot be sized."
                ),
                implication="Off-balance commitments and ROU liabilities may be understated.",
                ask_management="Provide the full lease schedule (term, rent, termination) for all sites.",
                evidence_refs=["C", "LEASE_AGREEMENT"],
                source=FindingSource.MODEL,
                area="Leases",
                quantified_effect=quant,
                protection="Condition / RFI for lease schedule before IC reliance",
                mechanism="condition",
                tier_or_grade="C",
            )
        )

    # --- Funding / grant match ---
    if bsp is not None and (
        getattr(bsp, "usda_match_m", None) is not None
        or getattr(bsp, "usda_grant_m", None) is not None
    ):
        match_m = getattr(bsp, "usda_match_m", None)
        grant_m = getattr(bsp, "usda_grant_m", None)
        out.append(
            Finding(
                finding_id=_fid("ic", "funding", slug or "deal"),
                section_id="SEC-H",
                severity=FindingSeverity.HIGH,
                title="Funding / grant match requirement is open",
                observation=(
                    f"Grant evidence shows USDA {_ic_money(grant_m)}"
                    if grant_m is not None
                    else "Grant / FPEP funding is referenced in the room"
                )
                + (
                    f" with matching requirement {_ic_money(match_m)} still to evidence."
                    if match_m is not None
                    else "; matching cash requirement is not fully evidenced."
                ),
                implication="Sources & uses and runway for the round remain incomplete.",
                ask_management="Provide sources & uses and evidence of matching funds / draw conditions.",
                evidence_refs=["C", "FPEP"],
                source=FindingSource.MODEL,
                area="Funding",
                quantified_effect=(
                    f"Match ~{_ic_money(match_m)}"
                    if match_m is not None
                    else "Match requirement open"
                ),
                protection="IC condition — confirm funding plan before relying on grant cash",
                mechanism="condition",
                tier_or_grade="C",
            )
        )

    # --- Preferred / transaction rights ---
    try:
        from agetic_cdd_api.services_fdd_chapter_depth import parse_transaction_terms

        terms = parse_transaction_terms(slug) if slug else None
    except Exception:
        terms = None
    if terms is not None:
        round_size = getattr(terms, "primary_m", None)
        has_pref = bool(
            getattr(terms, "existing_preferred", None)
            or getattr(terms, "round_label", None)
            or round_size
        )
        if has_pref:
            pref_note = str(getattr(terms, "existing_preferred", None) or "").strip()
            out.append(
                Finding(
                    finding_id=_fid("ic", "preferred", slug or "deal"),
                    section_id="SEC-A",
                    severity=FindingSeverity.MODERATE,
                    title="Preferred rights and round terms need confirmation",
                    observation=(
                        pref_note
                        or "Series preferred carries cumulative dividends / participation rights; "
                        "executed terms and cap table must be confirmed against the CIM."
                    ),
                    implication="Economic rights can reorder proceeds at exit and affect pricing.",
                    ask_management="Provide executed preferred charter, side letters, and current cap table.",
                    evidence_refs=["B", "CIM"],
                    source=FindingSource.MODEL,
                    area="Transaction",
                    quantified_effect=(
                        f"Round ~{_ic_money(float(round_size))}"
                        if round_size is not None
                        else "Preferred terms open"
                    ),
                    protection="Counsel review of preferred rights before IC",
                    mechanism="condition",
                    tier_or_grade="B",
                )
            )

    # --- Core trading decline (residential + commercial), masked by growth streams ---
    if pack is not None:
        ytd_year = 2026
        core_labels = ("Residential", "Commercial")
        prior = sum(
            float((pack.ytd.get(lab) or {}).get(ytd_year - 1) or 0.0)
            for lab in core_labels
        )
        curr = sum(
            float((pack.ytd.get(lab) or {}).get(ytd_year) or 0.0)
            for lab in core_labels
        )
        if prior >= 0.5 and curr > 0 and curr < prior * 0.97:
            pct_num = (curr / prior - 1.0) * 100.0
            pct = f"{pct_num:.1f}"
            res_p = (pack.ytd.get("Residential") or {}).get(ytd_year - 1)
            res_c = (pack.ytd.get("Residential") or {}).get(ytd_year)
            com_p = (pack.ytd.get("Commercial") or {}).get(ytd_year - 1)
            com_c = (pack.ytd.get("Commercial") or {}).get(ytd_year)

            def _chg(a: object, b: object) -> str | None:
                if a is None or b is None or float(a) == 0:
                    return None
                return f"{(float(b) / float(a) - 1.0) * 100.0:.1f}"

            res_pct = _chg(res_p, res_c)
            com_pct = _chg(com_p, com_c)
            detail_bits = []
            if res_pct is not None:
                detail_bits.append(f"residential {res_pct}%")
            if com_pct is not None:
                detail_bits.append(f"commercial {com_pct}%")
            detail = (", ".join(detail_bits) + "; ") if detail_bits else ""
            out.append(
                Finding(
                    finding_id=_fid("ic", "core_decline", slug or "deal"),
                    section_id="SEC-C",
                    severity=FindingSeverity.HIGH,
                    title="Core residential and commercial revenue is declining",
                    observation=(
                        f"YTD core (residential + commercial) is down {abs(pct_num):.1f}% "
                        f"({_ic_money(prior)} → {_ic_money(curr)}); {detail}"
                        "municipal and Key Compostables lift headline revenue."
                    ),
                    implication=(
                        "Headline growth masks softness in the core book; "
                        "pricing and retention risk sit in the larger channels."
                    ),
                    ask_management=(
                        "Explain residential and commercial volume/price drivers "
                        "and the outlook for the rest of FY26."
                    ),
                    evidence_refs=["B", "ex_m1_trading"],
                    source=FindingSource.MODEL,
                    area="Trading",
                    quantified_effect=(
                        f"Core YTD {pct}% ({_ic_money(curr)} vs {_ic_money(prior)})"
                    ),
                    protection="Diligence deep-dive on core channel retention before IC",
                    mechanism="condition",
                    tier_or_grade="B",
                )
            )

    # --- Receivables build / DSO ---
    ar_end = None
    ar_start = None
    if bsp is not None:
        ar_end = (bsp.ar or {}).get("Jul-26")
        ar_start = (bsp.ar or {}).get(2025)
        if ar_start is None:
            ar_start = (bsp.ar or {}).get(2024)
    if ar_end is None:
        ar_cell = _cell_by_metric(
            store, {"ex_m5_nwc", "ex_m8_bs", "ex_db_bs"}, "accounts_receivable", 2025
        )
        if ar_cell is not None and isinstance(ar_cell.value, (int, float)):
            ar_end = float(ar_cell.value)
    if (
        ar_end is not None
        and ar_start is not None
        and float(ar_start) > 0
        and float(ar_end) >= float(ar_start) * 1.15
    ):
        growth_pct = (float(ar_end) / float(ar_start) - 1.0) * 100.0
        growth = f"{growth_pct:.1f}"
        # Days of revenue: prefer LTM when available, else FY25 revenue / 365.
        rev_base = None
        if pack is not None:
            rev_base = getattr(pack, "ltm_revenue", None) or (pack.revenue_fy or {}).get(
                2025
            )
        if rev_base is None and bsp is not None:
            rev_base = getattr(bsp, "ltm_revenue", None)
        if rev_base is None:
            rev_cell = _cell_by_metric(
                store, {"ex_m1_trading", "ex_db_is"}, "revenue", 2025
            )
            if rev_cell is not None and isinstance(rev_cell.value, (int, float)):
                rev_base = float(rev_cell.value)
        days = None
        if rev_base and float(rev_base) > 0:
            days = float(ar_end) / (float(rev_base) / 365.0)
        days_txt = f", ~{days:.0f} days of revenue" if days else ""
        sev = (
            FindingSeverity.HIGH
            if growth_pct >= 25.0 or (days is not None and days >= 40.0)
            else FindingSeverity.MODERATE
        )
        out.append(
            Finding(
                finding_id=_fid("ic", "receivables", slug or "deal"),
                section_id="SEC-G",
                severity=sev,
                title="Receivables have built ahead of revenue",
                observation=(
                    f"Trade receivables rose {growth}% "
                    f"({_ic_money(float(ar_start))} → {_ic_money(float(ar_end))})"
                    f"{days_txt}; bad-debt provision remains thin versus the build."
                ),
                implication="Working capital and earnings quality risk if collections slip.",
                ask_management=(
                    "Provide an aged AR schedule, top-balance detail, and collection outlook."
                ),
                evidence_refs=["B", "ex_m5_nwc"],
                source=FindingSource.MODEL,
                area="Balance sheet",
                quantified_effect=(
                    f"AR {_ic_money(float(ar_end))}"
                    + (f" (~{days:.0f} days)" if days else "")
                ),
                protection="NWC / AR diligence condition before pegging working capital",
                mechanism="condition",
                tier_or_grade="B",
            )
        )

    # --- Cash dividends paid while loss-making ---
    paid = None
    ni = None
    if bsp is not None:
        paid_ytd = (bsp.dividend_paid or {}).get("Jul-26")
        paid_fy = (bsp.dividend_paid or {}).get(2025)
        # Prefer the larger evidenced cash leakage (FY closed vs YTD).
        cands = [abs(float(x)) for x in (paid_ytd, paid_fy) if x is not None]
        paid = max(cands) if cands else None
        ni = (bsp.net_income or {}).get("Jul-26")
        if ni is None:
            ni = (bsp.net_income or {}).get(2025)
    if paid is not None and float(paid) >= 0.05 and (
        ni is None or float(ni) <= 0
    ):
        out.append(
            Finding(
                finding_id=_fid("ic", "dividend_cash", slug or "deal"),
                section_id="SEC-G",
                severity=FindingSeverity.HIGH,
                title="Cash dividends paid while the business is loss-making",
                observation=(
                    f"About {_ic_money(float(paid))} of cash dividends have been paid "
                    "while earnings remain negative — cash leakage ahead of the round."
                ),
                implication="New money can be diverted to legacy preferred / arrears without a hard stop.",
                ask_management="Confirm dividend policy, cash paid since Jan-25, and waiver path.",
                evidence_refs=["B", "ex_db_cf"],
                source=FindingSource.MODEL,
                area="Cash flow",
                quantified_effect=f"Cash dividends ~{_ic_money(float(paid))}",
                protection="No-leakage covenant to closing; bar on using proceeds for arrears",
                mechanism="covenant",
                tier_or_grade="B",
            )
        )

    # --- Loan schedule / asset register integrity ---
    loan_gap = False
    loan_note = ""
    try:
        from agetic_cdd_api.services_fdd_chapter_depth import list_data_room_files

        docs = list_data_room_files(slug) if slug else []
    except Exception:
        docs = []
    loan_docs = [
        d
        for d in docs
        if re.search(
            r"(?i)loan|asset.?register|fixed.?asset|ppe",
            str(d.get("document") or ""),
        )
    ]
    # Compare vehicle + SBA components to financial debt (do not also add loans_payable).
    if bsp is not None:
        gross = (bsp.financial_debt or {}).get(2025)
        veh = (bsp.vehicle_loans or {}).get(2025)
        sba = (bsp.sba_loans or {}).get(2025)
        if gross is not None and (veh is not None or sba is not None):
            part_sum = float(veh or 0.0) + float(sba or 0.0)
            if part_sum > 0 and abs(float(gross) - part_sum) >= 0.05:
                loan_gap = True
                loan_note = (
                    f"Vehicle + SBA loans {_ic_money(part_sum)} vs "
                    f"financial debt {_ic_money(float(gross))}."
                )
    if loan_docs and not loan_gap:
        # Room has a loan/asset file but schedule integrity is not proven.
        loan_gap = True
        loan_note = (
            "Loan / asset-register files are in the room but schedule integrity "
            "(#REF / unexplained PPE) is not closed."
        )
    if loan_gap:
        out.append(
            Finding(
                finding_id=_fid("ic", "loan_register", slug or "deal"),
                section_id="SEC-G",
                severity=FindingSeverity.HIGH if loan_docs else FindingSeverity.MODERATE,
                title="Loan schedule and asset register need a clean tie-out",
                observation=(
                    loan_note
                    or "Debt and fixed-asset schedules are incomplete or inconsistent."
                ),
                implication="Gross debt and PPE can be misstated until schedules foot to the books.",
                ask_management=(
                    "Provide a clean loan schedule and fixed-asset register that tie to the BS."
                ),
                evidence_refs=["C", "ex_m6_net_debt"],
                source=FindingSource.MODEL,
                area="Balance sheet",
                quantified_effect=loan_note[:80] if loan_note else "Schedule open",
                protection="Condition — loan and asset register tie-out before IC reliance",
                mechanism="condition",
                tier_or_grade="C",
            )
        )

    # --- Interest / other income netting with dividend accrual ---
    interest = _cell_by_metric(
        store, {"ex_db_is", "ex_m1_trading", "ex_m3_costs"}, "interest_income", 2025
    )
    other_inc = _cell_by_metric(
        store, {"ex_db_is", "ex_m1_trading"}, "other_income", 2025
    )
    if other_inc is None:
        other_inc = _cell_by_metric(
            store, {"ex_db_is", "ex_m1_trading"}, "other_revenue", 2025
        )
    other_val = (
        float(other_inc.value)
        if other_inc is not None and isinstance(other_inc.value, (int, float))
        else None
    )
    interest_val = (
        float(interest.value)
        if interest is not None and isinstance(interest.value, (int, float))
        else None
    )
    # Fallback: monthly extract "Other income (expense)" often holds the net line.
    if other_val is None and slug:
        try:
            from agetic_cdd_api.services_fdd_chapter_depth import _load_extract

            for row in _load_extract(slug) or []:
                if getattr(row, "fiscal_year", None) != 2025:
                    continue
                cap = str(getattr(row, "caption", None) or "")
                if not re.search(r"(?i)^other income", cap):
                    continue
                raw = getattr(row, "value", None)
                if raw is None:
                    continue
                fv = float(raw)
                # Absolute dollars → $m when clearly not already in millions.
                other_val = fv / 1_000_000.0 if abs(fv) >= 1000.0 else fv
                break
        except Exception:
            pass
    div_acc = None
    if bsp is not None:
        div_acc = (bsp.dividend_accrual or {}).get(2025)
    if (
        div_acc is not None
        and abs(float(div_acc)) >= 0.01
        and (other_val is not None or interest_val is not None)
    ):
        net_bits: list[str] = []
        net_val = 0.0
        if interest_val is not None:
            net_bits.append(f"interest {_ic_money(interest_val)}")
            net_val += interest_val
        if other_val is not None:
            net_bits.append(f"other income {_ic_money(other_val)}")
            net_val += other_val
        net_bits.append(f"dividend accrual {_ic_money(float(div_acc))}")
        # Other income (expense) often already includes the accrual; show residual.
        residual = net_val  # keep reported other-income line as the net signal
        out.append(
            Finding(
                finding_id=_fid("ic", "interest_netting", slug or "deal"),
                section_id="SEC-B",
                severity=FindingSeverity.MODERATE,
                title="Interest and other income are netted with dividend accrual",
                observation=(
                    "Below-EBITDA items mix interest / other income with preferred "
                    f"dividend accrual ({'; '.join(net_bits)}). Nature of other income "
                    "and any acquisition accounting remains open."
                ),
                implication=(
                    "Earnings quality and cash conversion can be overstated if netting hides cost."
                ),
                ask_management=(
                    "Provide a bridge of interest, other income, and dividend accrual for FY25."
                ),
                evidence_refs=["B", "ex_db_is"],
                source=FindingSource.MODEL,
                area="QoE",
                quantified_effect=f"Other income (expense) ~{_ic_money(residual)}",
                protection="QoE bridge — separate interest, other income, and dividend accrual",
                mechanism="information",
                tier_or_grade="B",
            )
        )

    # --- Earnings quality / records ---
    out.append(
        Finding(
            finding_id=_fid("ic", "records", slug or "deal"),
            section_id="SEC-B",
            severity=FindingSeverity.MODERATE,
            title="Earnings quality depends on unaudited records",
            observation=(
                "Diligence EBITDA rests on unaudited monthly management accounts; "
                "ledger detail behind other income / adjustments remains open."
            ),
            implication="IC should not treat diligence EBITDA as audited until tie-outs close.",
            ask_management="Provide ledger detail for other income and QoE adjustments.",
            evidence_refs=["B"],
            source=FindingSource.MODEL,
            area="QoE",
            quantified_effect="Unaudited basis",
            protection="Information rights / closing condition for audit tie-out",
            mechanism="information",
            tier_or_grade="B",
        )
    )
    return out


def build_findings(
    deal_slug: str,
    run_id: str,
    *,
    store: ExhibitStoreDoc | None = None,
    commentary: CommentaryDoc | None = None,
    update_manifest: bool = True,
) -> FindingsDoc:
    """Build and persist the findings ledger for a run."""
    from agetic_cdd_api.services_fdd_store import save_findings

    store = store or load_exhibit_store(deal_slug, run_id)
    if store is None:
        store = ExhibitStoreDoc(
            deal_slug=deal_slug, run_id=run_id, updated_at=_now(), exhibits=[]
        )
    commentary = commentary if commentary is not None else load_commentary(deal_slug, run_id)

    # Fix 5 — claims and RFIs are not findings (ledger / request list only).
    _ = _from_claims(deal_slug, run_id)
    _ = _from_requests(deal_slug, run_id)
    findings = sort_findings(
        [
            *_from_g3(store),
            *_from_qoe(deal_slug, run_id),
            *_from_held_sections(commentary),
            *_from_cost_pressure(store, deal_slug=deal_slug, run_id=run_id),
            *_from_doubtful_headlines(store),
            *_from_ic_diligence(store, deal_slug=deal_slug),
        ]
    )
    # De-dupe by finding_id, then by metric×year stem (keep higher severity).
    by_id: dict[str, Finding] = {}
    for f in findings:
        by_id.setdefault(f.finding_id, f)
    findings = sort_findings(list(by_id.values()))
    by_stem: dict[str, Finding] = {}
    for f in findings:
        stem = re.sub(
            r"^(resolve claim|open information request —)\s*",
            "",
            (f.title or "").lower(),
        )
        stem = re.sub(r"\s*\([^)]*\)\s*$", "", stem).strip()
        prev = by_stem.get(stem)
        if prev is None or _SEVERITY_RANK.get(f.severity, 9) < _SEVERITY_RANK.get(
            prev.severity, 9
        ):
            by_stem[stem] = f
    findings = sort_findings(list(by_stem.values()))
    findings, population = assign_findings_register(findings, population_limit=12)

    doc = FindingsDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        findings=findings,
        population=population,
        counts=_counts(findings),
        version=FINDINGS_VERSION,
    )
    save_findings(doc)

    if update_manifest:
        manifest = load_manifest(deal_slug, run_id)
        if manifest is not None:
            save_manifest(
                manifest.model_copy(
                    update={
                        "findings_built": True,
                        "model_versions": {
                            **(manifest.model_versions or {}),
                            "fdd_findings": FINDINGS_VERSION,
                        },
                    }
                )
            )
    return doc


def not_evidenced_body(
    *,
    findings: list[Finding],
    commentary: CommentaryDoc | None,
) -> str:
    """Appendix text for gaps / held / open requests."""
    lines = [
        "Items below are not fully evidenced for this run. "
        "Each should be closed with a schedule or an explicit out-of-scope note.",
        "",
    ]
    held = [f for f in findings if f.source == FindingSource.HELD_SECTION]
    claims = [f for f in findings if f.source in {FindingSource.CLAIM, FindingSource.SOURCE_BASIS_GAP}]
    other = [
        f
        for f in findings
        if f.source not in {FindingSource.HELD_SECTION, FindingSource.CLAIM, FindingSource.SOURCE_BASIS_GAP}
    ]
    if commentary:
        for d in commentary.sections or []:
            if d.held_back:
                lines.append(
                    f"• Held section — {d.title or d.section_id}: "
                    f"{d.held_back_reason or 'pending figures'}"
                )
    for f in held + claims + other:
        lines.append(f"• [{f.severity.value}] {f.title}")
        if f.ask_management:
            lines.append(f"  Information request: {f.ask_management}")
    if len(lines) <= 2:
        lines.append("• No open gaps recorded.")
    return "\n".join(lines)


def severity_dashboard_line(counts: dict[str, int]) -> str:
    return (
        f"Findings: {counts.get('high', 0)} high · "
        f"{counts.get('moderate', 0)} moderate · "
        f"{counts.get('low', 0)} low · "
        f"{counts.get('info', 0)} info "
        f"(total {counts.get('total', 0)})"
    )
