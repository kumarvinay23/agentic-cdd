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

FINDINGS_VERSION = "1.0.0"
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
    from datetime import date

    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    ledger = load_claims_ledger(deal_slug, run_id)
    if ledger is None:
        return []
    out: list[Finding] = []
    closed_cutoff = date.today().year - 1
    unreliable = {
        m.source_agent
        for m in (ledger.modules or [])
        if getattr(m, "unreliable", False)
    }
    for claim in ledger.claims or []:
        if not getattr(claim, "failed", False) and claim.test_result not in {
            "contradicted",
            "unverifiable",
        }:
            continue
        # Plan / open years are not diligence contradictions (pack YTD ≠ plan).
        if claim.fiscal_year is not None and int(claim.fiscal_year) > closed_cutoff:
            continue
        if claim.test_result != "contradicted":
            # Unverifiable without a contradiction is an open request, not a finding.
            continue
        mk = (claim.metric_key or "").lower()
        section = _SECTION_FOR_METRIC.get(mk, "SEC-K")
        result = claim.test_result or "unverifiable"
        if result == "contradicted" and mk in {"revenue", "ebitda", "gross_profit"}:
            # HIGH only at/above absolute materiality (0.03 M); smaller gaps stay
            # MODERATE so FY2023/24 EBITDA ~0.02 M are not false alarms.
            severity = FindingSeverity.MODERATE
            if (
                claim.claimed_value is not None
                and claim.databook_value is not None
            ):
                gap = abs(float(claim.claimed_value) - float(claim.databook_value))
                if gap + 1e-12 >= _CLAIM_HIGH_ABS:
                    severity = FindingSeverity.HIGH
                elif (
                    abs(float(claim.databook_value)) > 1e-9
                    and gap / abs(float(claim.databook_value)) >= max(_LARGE_GAP_REL, 0.05)
                ):
                    # Large relative miss on a small base still warrants HIGH.
                    severity = FindingSeverity.HIGH
        elif result == "contradicted":
            severity = FindingSeverity.MODERATE
        elif mk.startswith("grr") or mk.startswith("nrr"):
            severity = FindingSeverity.LOW
        else:
            severity = FindingSeverity.LOW
        if claim.source_agent and claim.source_agent in unreliable:
            if severity == FindingSeverity.LOW:
                severity = FindingSeverity.MODERATE
        year_lab = f"FY{claim.fiscal_year}" if claim.fiscal_year else "open period"
        metric_lab = (mk or "item").replace("_", " ")
        obs = (claim.text or "").strip()
        if (
            claim.claimed_value is not None
            and claim.databook_value is not None
            and result == "contradicted"
        ):
            obs = (
                f"{metric_lab} {year_lab}: claimed "
                f"{format_fdd_number(float(claim.claimed_value))} "
                f"vs databook {format_fdd_number(float(claim.databook_value))}."
            )
            title = (
                f"{metric_lab.title()} {year_lab}: claimed vs accounts "
                f"({result})"
            )
        elif result == "unverifiable":
            title = f"{metric_lab.title()} {year_lab} unverifiable vs accounts"
            if not obs:
                obs = title
        else:
            title = f"{metric_lab.title()} {year_lab} ({result})"
            if not obs:
                obs = title
        out.append(
            Finding(
                finding_id=_fid("claim", claim.claim_id),
                section_id=section,
                severity=severity,
                title=title[:160],
                observation=obs[:400],
                implication=(
                    "Reconcile sources before IC relies on this figure."
                    if result == "contradicted"
                    else "Obtain supporting evidence or retire the claim."
                ),
                ask_management=(
                    f"Please provide the schedule that supports {mk or 'this claim'} "
                    f"for FY{claim.fiscal_year}."
                    if claim.fiscal_year
                    else "Please provide supporting schedules for this claim."
                ),
                evidence_refs=[claim.claim_id]
                + ([claim.databook_fact_id] if claim.databook_fact_id else []),
                source=FindingSource.CLAIM
                if "gap" not in obs.lower()
                else FindingSource.SOURCE_BASIS_GAP,
            )
        )
        if len(out) >= _MAX_CLAIM_FINDINGS:
            break
    return out


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
    from datetime import date

    from agetic_cdd_api.services_fdd_commentary import (
        _request_title_is_open_year,
        _request_title_is_readiness_scaffold,
    )

    doc = load_request_list(deal_slug, run_id)
    if doc is None:
        return []
    items = list(getattr(doc, "items", None) or getattr(doc, "requests", None) or [])
    out: list[Finding] = []
    closed_cutoff = date.today().year - 1
    covered = covered_claim_keys or set()
    for item in items[:8]:
        item_id = getattr(item, "request_id", None) or ""
        title = getattr(item, "title", None) or str(item_id)
        detail = getattr(item, "detail", None) or title
        status = str(getattr(item, "status", "") or "").lower()
        if status in {"received", "waived"}:
            continue
        if _request_title_is_open_year(str(title), closed_cutoff):
            continue
        if _request_title_is_readiness_scaffold(str(title)):
            continue
        # Skip INFO duplicates of claim findings already raised at higher severity.
        title_l = str(title).lower()
        if any(key and key in title_l for key in covered):
            continue
        out.append(
            Finding(
                finding_id=_fid("req", str(item_id) or title),
                section_id="SEC-A",
                severity=FindingSeverity.INFO,
                title=f"Open information request — {title}"[:160],
                observation=str(detail)[:400],
                implication="Information gap remains on the diligence perimeter.",
                ask_management=str(detail)[:240],
                evidence_refs=[str(item_id)] if item_id else [],
                source=FindingSource.HELD_SECTION,
            )
        )
    return out


def _from_doubtful_headlines(store: ExhibitStoreDoc) -> list[Finding]:
    """Doubtful closed-year revenue/EBITDA → moderate finding."""
    from datetime import date

    out: list[Finding] = []
    closed_cutoff = date.today().year - 1
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
            out.append(
                Finding(
                    finding_id=_fid("doubt", ex.exhibit_id, mk, str(cell.fiscal_year)),
                    section_id=_SECTION_FOR_METRIC.get(mk, "SEC-B"),
                    severity=FindingSeverity.MODERATE,
                    title=f"Doubtful {mk} FY{cell.fiscal_year}",
                    observation=(
                        f"{ex.title or ex.exhibit_id}: {mk} FY{cell.fiscal_year} "
                        f"is tagged {cell.status.value}."
                    ),
                    implication="Confirm source basis before using this figure in pricing.",
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
        score = 0
        if claim.databook_value is not None:
            try:
                if abs(cv - float(claim.databook_value)) > 0.001:
                    score = 2  # pack alternate vs workbook databook
            except (TypeError, ValueError):
                score = 1
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
    if sga_yoy is None and labor_yoy is None:
        return []

    # Revenue growth: prefer pack M3 revenue levels (same basis as labour/SG&A).
    rev_curr = _cell_by_metric(store, {"ex_m3_costs"}, "revenue", closed)
    rev_prior = _cell_by_metric(store, {"ex_m3_costs"}, "revenue", prior)
    rev_pct: float | None = None
    rev_refs: list[str] = []
    rev_basis = "monthly pack"
    if (
        rev_curr is not None
        and rev_prior is not None
        and rev_prior.value not in (None, 0)
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
        if rev_yoy is None:
            return []
        try:
            rev_pct = float(rev_yoy.value)
        except (TypeError, ValueError):
            return []
        rev_refs = [f"{rev_yoy.exhibit_id}.{rev_yoy.cell_id}"]
        rev_basis = "investor workbook"

    # EBITDA pair on one source — prefer pack (aligned with cost YoY), else workbook.
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

    if eb_prior_v is None and deal_slug and run_id:
        pack_eb = _pack_metric_from_claims(
            deal_slug, run_id, metric_key="ebitda", years={prior, closed}
        )
        if prior in pack_eb and closed in pack_eb and pack_eb[prior] not in (0, 0.0):
            eb_prior_v = pack_eb[prior]
            eb_curr_v = pack_eb[closed]
            eb_basis = "monthly pack"
            eb_refs = [f"claim:ebitda:FY{prior}", f"claim:ebitda:FY{closed}"]

    if eb_prior_v is None or eb_curr_v is None or eb_prior_v == 0:
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

    claim_findings = _from_claims(deal_slug, run_id)
    covered_keys: set[str] = set()
    for f in claim_findings:
        # "Resolve claim ebitda FY2023" → cover request titles with same metric×year.
        title_l = (f.title or "").lower()
        for token in title_l.replace("(", " ").replace(")", " ").split():
            if token.startswith("fy20") or token in {
                "revenue",
                "ebitda",
                "gross_profit",
                "gross_margin",
                "cogs",
                "sga",
            }:
                covered_keys.add(token)
        if f.evidence_refs:
            covered_keys.update(str(r).lower() for r in f.evidence_refs if r)
    findings = sort_findings(
        [
            *_from_g3(store),
            *_from_qoe(deal_slug, run_id),
            *_from_held_sections(commentary),
            *claim_findings,
            *_from_cost_pressure(store, deal_slug=deal_slug, run_id=run_id),
            *_from_doubtful_headlines(store),
            *_from_requests(deal_slug, run_id, covered_claim_keys=covered_keys),
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

    doc = FindingsDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        findings=findings,
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
