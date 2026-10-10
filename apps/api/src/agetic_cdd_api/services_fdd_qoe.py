"""FDD Phase 5a — Quality of Earnings model (M4).

Implements PDF §5 / Appendix B4:
- register with treatments (accept / partial / reject / sensitivity / pro_forma)
- consumption ledger (anti double-count)
- bridge + management↔diligence walk
- sensitivities & pro forma *beside* adjusted EBITDA
- G4 approval (lead for material judgements; partner for conclusion)
- PDF §5 worked example reproducible from fact IDs
"""

from __future__ import annotations

import uuid
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    AdjustmentRow,
    Approval,
    ArtefactStatus,
    DEFAULT_MATERIALITY_PCT,
    FddRunManifest,
    GateId,
    MATERIALITY_REVENUE_BAND,
    QoeBaselinePeriod,
    QoeBridgePeriod,
    QoeBridgeStep,
    QoeCheckResult,
    QoeConsumeRef,
    QoeProFormaItem,
    QoeSensitivityItem,
    QoeWalkStep,
    QoeWorkbookDoc,
    RunStage,
    TRIVIAL_FRACTION_OF_M,
)
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_scope import trivial_threshold as scope_trivial
from agetic_cdd_api.services_fdd_store import (
    load_approval,
    load_fact_table,
    load_manifest,
    load_qoe_workbook,
    load_scope_profile,
    save_approval,
    save_manifest,
    save_qoe_workbook,
)

QOE_MODEL_VERSION = "0.1.0"

# Treatments that contribute to adjusted EBITDA (bridge).
_BRIDGE_TREATMENTS = frozenset({"accept", "partial"})
# Treatments that must never enter the bridge.
_BESIDE_TREATMENTS = frozenset({"sensitivity", "pro_forma", "reject", "pending"})


class QoeValidationError(ValueError):
    """Invalid QoE register / treatment payload."""


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def compute_materiality_m(
    *,
    adj_ebitda: float,
    revenue: float,
    materiality_pct: float = DEFAULT_MATERIALITY_PCT,
) -> float:
    """Appendix B4: M = min(max(pct×AdjEBITDA, 0.5% Rev), 1% Rev)."""
    floor_rev, ceil_rev = MATERIALITY_REVENUE_BAND
    from_ebitda = float(materiality_pct) * float(adj_ebitda)
    from_rev_floor = float(floor_rev) * float(revenue)
    from_rev_ceil = float(ceil_rev) * float(revenue)
    return min(max(from_ebitda, from_rev_floor), from_rev_ceil)


def materiality_band_for(amount: float | None, *, m: float, trivial: float) -> str:
    if amount is None:
        return "trivial"
    abs_amt = abs(float(amount))
    if abs_amt >= float(m):
        return "above_m"
    if abs_amt >= float(trivial):
        return "above_trivial"
    return "trivial"


def merge_candidates_by_event_key(
    candidates: list[AdjustmentRow],
) -> list[AdjustmentRow]:
    """Event key is unique per period — merge duplicates before assessment."""
    merged: dict[tuple[str, str], AdjustmentRow] = {}
    for row in candidates:
        key = (row.event_key, row.period)
        if key not in merged:
            merged[key] = row
            continue
        prior = merged[key]
        origins = list(dict.fromkeys([*(prior.origin or []), *(row.origin or [])]))
        facts = list(dict.fromkeys([*prior.source_fact_ids, *row.source_fact_ids]))
        consumes = list(prior.consumes) + [
            c
            for c in row.consumes
            if not any(p.fact_id == c.fact_id for p in prior.consumes)
        ]
        mgmt = (
            row.management_amount
            if row.management_amount is not None
            else prior.management_amount
        )
        dil = (
            row.diligence_amount
            if row.diligence_amount is not None
            else prior.diligence_amount
        )
        merged[key] = prior.model_copy(
            update={
                "origin": origins,
                "source_fact_ids": facts,
                "consumes": consumes,
                "management_amount": mgmt,
                "diligence_amount": dil,
                "amount": dil if dil is not None else mgmt,
                "label": prior.label or row.label,
            }
        )
    return list(merged.values())


def _diligence_amount(row: AdjustmentRow) -> float:
    if row.diligence_amount is not None:
        return float(row.diligence_amount)
    if row.amount is not None:
        return float(row.amount)
    return 0.0


def _management_amount(row: AdjustmentRow) -> float:
    if row.management_amount is not None:
        return float(row.management_amount)
    return 0.0


def build_bridge(
    *,
    period: str,
    reported_ebitda: float,
    register: list[AdjustmentRow],
) -> QoeBridgePeriod:
    """Adjusted EBITDA = Reported + Σ accepted/partial diligence amounts."""
    steps: list[QoeBridgeStep] = [
        QoeBridgeStep(
            step_id="base",
            label="Reported EBITDA",
            amount=float(reported_ebitda),
            running_total=float(reported_ebitda),
        )
    ]
    running = float(reported_ebitda)
    adj_total = 0.0
    for row in register:
        if row.treatment not in _BRIDGE_TREATMENTS:
            continue
        amt = _diligence_amount(row)
        running += amt
        adj_total += amt
        steps.append(
            QoeBridgeStep(
                step_id=row.adjustment_id,
                label=row.label,
                amount=amt,
                running_total=round(running, 10),
                adjustment_id=row.adjustment_id,
            )
        )
    return QoeBridgePeriod(
        period=period,
        reported_ebitda=float(reported_ebitda),
        adjustments_total=round(adj_total, 10),
        adjusted_ebitda=round(running, 10),
        steps=steps,
    )


def build_management_to_diligence_walk(
    *,
    management_adj: float,
    diligence_adj: float,
    management_reported: float,
    diligence_reported: float,
    register: list[AdjustmentRow],
) -> list[QoeWalkStep]:
    """Walk re-adds: start at management adj EBITDA → diligence adj EBITDA.

    Steps: basis change (draft→audited), then diligence−management per
    accepted/partial row (PDF §5 worked example).
    """
    steps: list[QoeWalkStep] = [
        QoeWalkStep(
            step_id="mgmt_adj",
            label="Management's adjusted EBITDA",
            amount=float(management_adj),
            running_total=float(management_adj),
        )
    ]
    running = float(management_adj)
    basis_delta = float(diligence_reported) - float(management_reported)
    if abs(basis_delta) > 1e-9:
        running += basis_delta
        steps.append(
            QoeWalkStep(
                step_id="basis",
                label="Move from draft to audited accounts",
                amount=basis_delta,
                running_total=round(running, 10),
            )
        )
    for row in register:
        if row.treatment not in _BRIDGE_TREATMENTS:
            continue
        delta = _diligence_amount(row) - _management_amount(row)
        if abs(delta) <= 1e-9:
            continue
        running += delta
        steps.append(
            QoeWalkStep(
                step_id=f"walk_{row.adjustment_id}",
                label=row.difference_reason or row.label,
                amount=delta,
                running_total=round(running, 10),
                adjustment_id=row.adjustment_id,
            )
        )
    steps.append(
        QoeWalkStep(
            step_id="dil_adj",
            label="Diligence adjusted EBITDA",
            amount=round(float(diligence_adj) - running, 10),
            running_total=float(diligence_adj),
        )
    )
    return steps


def validate_consumption(
    register: list[AdjustmentRow],
    *,
    fact_ceilings: dict[str, float] | None = None,
) -> list[QoeCheckResult]:
    """PDF B4: for every fact f, Σ|consumed| ≤ |value of f|.

    Split consumption across bridge rows is allowed when the total stays within
    the fact ceiling (e.g. $4 + $6 of a $10 fact). Over-consumption is blocking.
    Without a ceiling, multi-row use is recorded as a non-blocking advisory.
    """
    checks: list[QoeCheckResult] = []
    ceilings = {k: abs(float(v)) for k, v in (fact_ceilings or {}).items()}
    by_fact: dict[str, float] = {}
    for row in register:
        if row.treatment in {"reject", "pending"}:
            continue
        for ref in row.consumes:
            by_fact[ref.fact_id] = by_fact.get(ref.fact_id, 0.0) + abs(float(ref.amount))

    for fact_id, total in sorted(by_fact.items()):
        rows_for = [
            r
            for r in register
            if any(c.fact_id == fact_id for c in r.consumes)
            and r.treatment in _BRIDGE_TREATMENTS | {"sensitivity", "pro_forma"}
        ]
        bridge_rows = [r for r in rows_for if r.treatment in _BRIDGE_TREATMENTS]
        ceiling = ceilings.get(fact_id)
        if ceiling is not None and total > ceiling + 1e-6:
            checks.append(
                QoeCheckResult(
                    check_id=f"consume_double:{fact_id}",
                    passed=False,
                    message=(
                        f"Fact {fact_id} over-consumed "
                        f"({total:.4g} > ceiling {ceiling:.4g})"
                        + (
                            ": " + ", ".join(r.adjustment_id for r in bridge_rows)
                            if bridge_rows
                            else ""
                        )
                    ),
                    blocking=True,
                )
            )
            continue
        if ceiling is None and len(bridge_rows) > 1:
            checks.append(
                QoeCheckResult(
                    check_id=f"consume_shared:{fact_id}",
                    passed=True,
                    message=(
                        f"Fact {fact_id} shared by bridge rows without ceiling "
                        f"({total:.4g}): "
                        + ", ".join(r.adjustment_id for r in bridge_rows)
                    ),
                    blocking=False,
                )
            )
            continue
        checks.append(
            QoeCheckResult(
                check_id=f"consume_ok:{fact_id}",
                passed=True,
                message=(
                    f"Fact {fact_id} consumption {total:.4g}"
                    + (f" ≤ {ceiling:.4g}" if ceiling is not None else " recorded")
                ),
                blocking=False,
            )
        )

    # Event key uniqueness per period
    seen: set[tuple[str, str]] = set()
    for row in register:
        key = (row.event_key, row.period)
        if key in seen:
            checks.append(
                QoeCheckResult(
                    check_id=f"event_dup:{row.event_key}:{row.period}",
                    passed=False,
                    message=f"Duplicate event_key {row.event_key} in {row.period}",
                    blocking=True,
                )
            )
        seen.add(key)
    return checks


def _walk_readd_eps(scale: str | None) -> float:
    """Scale-aware absolute epsilon for walk re-add checks."""
    if (scale or "").lower() in {"m", "cr", "mn", "million"}:
        return 1e-4
    if (scale or "").lower() in {"b", "bn", "billion"}:
        return 1e-6
    return 1.0


def recompute_qoe(doc: QoeWorkbookDoc) -> QoeWorkbookDoc:
    """Recompute bridge, walks, sensitivities, materiality, and checks."""
    register = merge_candidates_by_event_key(list(doc.register_rows))
    # Stamp differences + amount aliases
    stamped: list[AdjustmentRow] = []
    for row in register:
        mgmt = row.management_amount
        dil = row.diligence_amount
        diff = None
        if mgmt is not None and dil is not None:
            diff = float(dil) - float(mgmt)
        stamped.append(
            row.model_copy(
                update={
                    "difference": diff if diff is not None else row.difference,
                    "amount": dil if dil is not None else row.amount,
                }
            )
        )
    register = stamped

    baseline = doc.baseline[0] if doc.baseline else None
    period = doc.period
    mgmt_reported = (
        float(baseline.management_reported_ebitda)
        if baseline and baseline.management_reported_ebitda is not None
        else 0.0
    )
    dil_reported = (
        float(baseline.diligence_reported_ebitda)
        if baseline and baseline.diligence_reported_ebitda is not None
        else mgmt_reported
    )
    revenue = (
        float(baseline.revenue)
        if baseline and baseline.revenue is not None
        else 0.0
    )

    # Management bridge view (uses management amounts where present)
    mgmt_adj = mgmt_reported
    for row in register:
        if row.treatment in _BRIDGE_TREATMENTS:
            mgmt_adj += _management_amount(row)

    bridge = build_bridge(
        period=period, reported_ebitda=dil_reported, register=register
    )
    dil_adj = bridge.adjusted_ebitda

    walk = build_management_to_diligence_walk(
        management_adj=round(mgmt_adj, 10),
        diligence_adj=dil_adj,
        management_reported=mgmt_reported,
        diligence_reported=dil_reported,
        register=register,
    )

    # Derive sensitivities / pro forma deterministically from the register
    # (avoids stale or duplicate manual lists drifting from treatments).
    sens: list[QoeSensitivityItem] = []
    for row in register:
        if row.treatment != "sensitivity":
            continue
        amt = _diligence_amount(row)
        sens.append(
            QoeSensitivityItem(
                sensitivity_id=row.adjustment_id,
                label=row.label,
                amount=amt,
                direction="upside" if amt >= 0 else "downside",
                evidence_status=row.evidence_status,  # type: ignore[arg-type]
                rationale=row.rationale,
            )
        )

    pf: list[QoeProFormaItem] = []
    for row in register:
        if row.treatment != "pro_forma":
            continue
        pf.append(
            QoeProFormaItem(
                pro_forma_id=row.adjustment_id,
                label=row.label,
                amount=_diligence_amount(row),
                evidence_status=row.evidence_status,  # type: ignore[arg-type]
                rationale=row.rationale,
            )
        )

    upside = sum(s.amount for s in sens if s.direction == "upside")
    downside = sum(s.amount for s in sens if s.direction == "downside")
    sens_low = round(dil_adj + downside, 10)
    sens_high = round(dil_adj + upside, 10)
    pf_total = round(dil_adj + sum(p.amount for p in pf), 10)
    # "partly evidenced" — anything not fully verified
    partly_verified_gap = sum(
        p.amount for p in pf if p.evidence_status != "verified"
    )
    pf_share = (
        round(partly_verified_gap / pf_total, 6) if abs(pf_total) > 1e-9 else None
    )

    m = compute_materiality_m(adj_ebitda=dil_adj, revenue=revenue) if revenue else None
    trivial = scope_trivial(m) if m is not None else None

    stamped_mat: list[AdjustmentRow] = []
    for row in register:
        band = None
        if m is not None and trivial is not None:
            band = materiality_band_for(
                _diligence_amount(row), m=m, trivial=trivial
            )
        stamped_mat.append(
            row.model_copy(update={"materiality_band": band})  # type: ignore[arg-type]
        )
    register = stamped_mat

    checks = validate_consumption(register, fact_ceilings=doc.fact_ceilings)
    # Bridge re-add check
    checks.append(
        QoeCheckResult(
            check_id="bridge_readd",
            passed=abs(
                bridge.reported_ebitda
                + bridge.adjustments_total
                - bridge.adjusted_ebitda
            )
            < 1e-6,
            message="Bridge reported + adjustments = adjusted EBITDA",
            blocking=True,
        )
    )
    # Sensitivities / pro forma must not appear as bridge steps
    bridge_ids = {s.adjustment_id for s in bridge.steps if s.adjustment_id}
    sens_ids = {r.adjustment_id for r in register if r.treatment == "sensitivity"}
    pf_ids = {r.adjustment_id for r in register if r.treatment == "pro_forma"}
    checks.append(
        QoeCheckResult(
            check_id="sens_beside",
            passed=not (bridge_ids & sens_ids),
            message="Sensitivities remain beside adjusted EBITDA",
            blocking=True,
        )
    )
    checks.append(
        QoeCheckResult(
            check_id="pf_beside",
            passed=not (bridge_ids & pf_ids),
            message="Pro forma items remain below adjusted EBITDA",
            blocking=True,
        )
    )
    # Walk terminal — scale-aware epsilon ($m / Cr vs raw units)
    if walk:
        eps = _walk_readd_eps(doc.scale)
        checks.append(
            QoeCheckResult(
                check_id="walk_readd",
                passed=abs(walk[-1].running_total - dil_adj) < eps,
                message=(
                    f"Walk ends at diligence adj EBITDA "
                    f"({walk[-1].running_total} vs {dil_adj})"
                ),
                blocking=True,
            )
        )

    # G4 readiness: every above-trivial item needs a reviewer decision
    blockers: list[str] = []
    for row in register:
        if row.treatment in {"pending"}:
            blockers.append(f"{row.adjustment_id}:treatment_pending")
            continue
        if trivial is not None and abs(_diligence_amount(row)) >= trivial:
            if row.reviewer_decision == "pending":
                blockers.append(f"{row.adjustment_id}:decision_pending")
        if row.evidence_status == "pending" and row.treatment in _BRIDGE_TREATMENTS:
            blockers.append(f"{row.adjustment_id}:evidence_pending")
    # Partner items: pro forma on non-verified base
    for p in pf:
        if p.evidence_status != "verified":
            blockers.append(f"{p.pro_forma_id}:partner_pro_forma_evidence")

    blocking_failed = [c for c in checks if c.blocking and not c.passed]
    checks_passed = not blocking_failed

    return doc.model_copy(
        update={
            "register_rows": register,
            "candidates": list(doc.candidates) or register,
            "bridge": [bridge],
            "management_to_diligence_walk": walk,
            "sensitivities": sens,
            "pro_forma": pf,
            "adjusted_ebitda_management": round(mgmt_adj, 10),
            "adjusted_ebitda_diligence": dil_adj,
            "sensitivity_low": sens_low,
            "sensitivity_high": sens_high,
            "pro_forma_ebitda": pf_total,
            "pro_forma_partly_evidenced_share": pf_share,
            "materiality_m": round(m, 10) if m is not None else None,
            "trivial_threshold": round(trivial, 10) if trivial is not None else None,
            "checks": checks,
            "checks_passed": checks_passed,
            "g4_ready": checks_passed and not blockers,
            "g4_blockers": blockers,
            "updated_at": _now(),
        }
    )


def build_worked_example_qoe(
    *,
    deal_slug: str = "worked-example",
    run_id: str = "run_worked_example",
) -> QoeWorkbookDoc:
    """PDF §5 illustrative multi-site retail group ($m, FY25A)."""
    period = "FY25A"
    revenue = 1450.0
    mgmt_reported = 124.0
    dil_reported = 120.0

    facts = {
        "FY25.revenue": revenue,
        "FY25.ebitda.audited": dil_reported,
        "FY25.ebitda.draft": mgmt_reported,
        "FY25.opex.professional_fees": 4.0,
        "FY25.gain.property_sale": 30.0,
        "FY25.rent.non_cash": 6.0,
        "FY25.opex.pre_opening": 5.0,
        "FY25.income.other_non_op": 1.2,
        "FY25.opex.owner_salary_above_mkt": 0.8,
        "FY25.cos.bad_debt_one_off": 2.8,
        "FY25.rent.cash_measurement_delta": 2.0,
        "FY25.sites.run_rate_eight": 7.5,
    }

    def cref(fid: str, amount: float) -> QoeConsumeRef:
        return QoeConsumeRef(fact_id=fid, amount=amount)

    register = [
        AdjustmentRow(
            adjustment_id="A-01",
            event_key="gain:property-sale:FY25",
            period=period,
            label="Gain on sale of property",
            category="non_operating",
            proposed_by="management",
            management_amount=-30.0,
            diligence_amount=-30.0,
            amount=-30.0,
            treatment="accept",
            evidence_status="verified",
            evidence_documents=["sale_agreement.pdf", "ledger_extract.pdf"],
            source_fact_ids=["FY25.gain.property_sale"],
            consumes=[cref("FY25.gain.property_sale", 30.0)],
            rationale="Non-operating disposal gain",
            recurring_status="non_recurring",
            cash_impact="cash",
            origin=["management", "library"],
            reviewer_decision="approved",
            reviewer_by="deal_lead",
            reviewer_at="2026-01-15T00:00:00Z",
        ),
        AdjustmentRow(
            adjustment_id="A-02",
            event_key="fees:sale-process:FY25",
            period=period,
            label="Transaction and advisory fees",
            category="non_recurring",
            proposed_by="management",
            management_amount=4.0,
            diligence_amount=2.5,
            amount=2.5,
            difference=-1.5,
            difference_reason="Fees: the retainer continues (A-02)",
            treatment="partial",
            evidence_status="verified",
            evidence_documents=[
                "ledger_extract.pdf",
                "invoices.pdf",
                "engagement_letters.pdf",
            ],
            source_fact_ids=["FY25.opex.professional_fees"],
            consumes=[cref("FY25.opex.professional_fees", 2.5)],
            rationale="Fees tied to the sale process; 1.5 retainer continues",
            recurring_status="non_recurring",
            cash_impact="cash",
            origin=["management"],
            reviewer_decision="pending",
        ),
        AdjustmentRow(
            adjustment_id="A-03",
            event_key="rent:non-cash:FY25",
            period=period,
            label="Non-cash rent",
            category="non_cash",
            proposed_by="management",
            management_amount=6.0,
            diligence_amount=6.0,
            amount=6.0,
            treatment="accept",
            evidence_status="supported",
            evidence_documents=["lease_register.pdf"],
            source_fact_ids=["FY25.rent.non_cash"],
            consumes=[cref("FY25.rent.non_cash", 6.0)],
            rationale="Non-cash rent add-back; measurement sensitivity S-02",
            recurring_status="uncertain",
            cash_impact="non_cash",
            origin=["management"],
            reviewer_decision="approved",
            reviewer_by="deal_lead",
            reviewer_at="2026-01-15T00:00:00Z",
        ),
        AdjustmentRow(
            adjustment_id="A-04",
            event_key="costs:pre-opening:FY25",
            period=period,
            label="Pre-opening costs",
            category="non_recurring",
            proposed_by="management",
            management_amount=5.0,
            diligence_amount=3.5,
            amount=3.5,
            difference=-1.5,
            difference_reason="Pre-opening: part treated as ongoing (A-04)",
            treatment="partial",
            evidence_status="supported",
            evidence_documents=["site_pl.pdf"],
            source_fact_ids=["FY25.opex.pre_opening"],
            consumes=[cref("FY25.opex.pre_opening", 3.5)],
            rationale="Partial: 1.5 treated as ongoing for a multi-site opener",
            recurring_status="uncertain",
            cash_impact="cash",
            origin=["management"],
            reviewer_decision="pending",
        ),
        AdjustmentRow(
            adjustment_id="A-05",
            event_key="income:other-non-op:FY25",
            period=period,
            label="Other non-operating income",
            category="non_operating",
            proposed_by="diligence",
            management_amount=0.0,
            diligence_amount=-1.2,
            amount=-1.2,
            difference=-1.2,
            difference_reason="Other non-operating income removed (A-05)",
            treatment="accept",
            evidence_status="verified",
            evidence_documents=["notes_to_accounts.pdf"],
            source_fact_ids=["FY25.income.other_non_op"],
            consumes=[cref("FY25.income.other_non_op", 1.2)],
            rationale="Found by the library scan",
            recurring_status="non_recurring",
            cash_impact="cash",
            origin=["library"],
            reviewer_decision="approved",
            reviewer_by="deal_lead",
            reviewer_at="2026-01-15T00:00:00Z",
        ),
        AdjustmentRow(
            adjustment_id="A-06",
            event_key="normalisation:owner-salary:FY25",
            period=period,
            label="Owner's salary above market",
            category="normalisation",
            proposed_by="management",
            management_amount=0.8,
            diligence_amount=0.5,
            amount=0.5,
            difference=-0.3,
            difference_reason="Owner's salary set at the benchmark (A-06)",
            treatment="partial",
            evidence_status="supported",
            evidence_documents=["salary_benchmark.pdf"],
            source_fact_ids=["FY25.opex.owner_salary_above_mkt"],
            consumes=[cref("FY25.opex.owner_salary_above_mkt", 0.5)],
            rationale="Partial normalisation to market salary",
            recurring_status="recurring",
            cash_impact="cash",
            origin=["management"],
            reviewer_decision="pending",
        ),
        AdjustmentRow(
            adjustment_id="S-01",
            event_key="sensitivity:bad-debt:FY25",
            period=period,
            label="One-off bad-debt charge in cost of sales",
            category="sensitivity",
            proposed_by="diligence",
            management_amount=None,
            diligence_amount=2.8,
            amount=2.8,
            treatment="sensitivity",
            evidence_status="verified",
            source_fact_ids=["FY25.cos.bad_debt_one_off"],
            consumes=[cref("FY25.cos.bad_debt_one_off", 2.8)],
            rationale="Amount verified; recurrence unknown",
            recurring_status="uncertain",
            cash_impact="cash",
            origin=["diligence"],
            reviewer_decision="pending",
        ),
        AdjustmentRow(
            adjustment_id="S-02",
            event_key="sensitivity:rent-measurement:FY25",
            period=period,
            label="Non-cash rent measured from the full cash flow",
            category="sensitivity",
            proposed_by="diligence",
            management_amount=None,
            diligence_amount=-2.0,
            amount=-2.0,
            treatment="sensitivity",
            evidence_status="supported",
            source_fact_ids=["FY25.rent.cash_measurement_delta"],
            consumes=[cref("FY25.rent.cash_measurement_delta", 2.0)],
            rationale="Measurement uncertain",
            recurring_status="uncertain",
            cash_impact="non_cash",
            origin=["diligence"],
            reviewer_decision="pending",
        ),
        AdjustmentRow(
            adjustment_id="P-01",
            event_key="proforma:run-rate-eight-sites:FY25",
            period=period,
            label="Run-rate of eight sites opened in the year",
            category="pro_forma",
            proposed_by="diligence",
            management_amount=None,
            diligence_amount=7.5,
            amount=7.5,
            treatment="pro_forma",
            evidence_status="supported",
            source_fact_ids=["FY25.sites.run_rate_eight"],
            consumes=[cref("FY25.sites.run_rate_eight", 7.5)],
            rationale="Below the line; base partly evidenced",
            recurring_status="uncertain",
            cash_impact="cash",
            origin=["diligence"],
            reviewer_decision="pending",
        ),
    ]

    doc = QoeWorkbookDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        version=QOE_MODEL_VERSION,
        currency="USD",
        scale="m",
        period=period,
        worked_example=True,
        baseline=[
            QoeBaselinePeriod(
                period=period,
                management_reported_ebitda=mgmt_reported,
                diligence_reported_ebitda=dil_reported,
                revenue=revenue,
                revenue_fact_id="FY25.revenue",
                ebitda_fact_id="FY25.ebitda.audited",
                basis_note="Draft accounts 124.0 → audited 120.0",
            )
        ],
        candidates=list(register),
        register_rows=register,
        fact_ceilings={k: abs(float(v)) for k, v in facts.items()},
        notes=[
            f"Worked example fact ids: {', '.join(sorted(facts))}",
            "Illustrative multi-site retail group — not from any transaction",
        ],
    )
    return recompute_qoe(doc)


def build_qoe_from_facts(
    deal_slug: str,
    run_id: str,
    *,
    period: str | None = None,
    fiscal_year: int | None = None,
) -> QoeWorkbookDoc:
    """Seed a QoE workbook from the run fact table (baseline only; empty register)."""
    facts = load_fact_table(deal_slug, run_id)
    manifest = load_manifest(deal_slug, run_id)
    scope = load_scope_profile(deal_slug, run_id)

    year = fiscal_year
    if year is None and facts and facts.facts:
        from datetime import date

        # Prefer latest *closed* year with EBITDA (not in-year / outer plan).
        cutoff = date.today().year - 1
        years = sorted({int(f.fiscal_year) for f in facts.facts}, reverse=True)
        closed = [y for y in years if y <= cutoff]
        ebitda_years = {
            int(f.fiscal_year)
            for f in facts.facts
            if f.metric_key in {"ebitda", "operating_profit"} and f.value is not None
        }
        for candidate in closed or years:
            if candidate in ebitda_years or not ebitda_years:
                year = candidate
                break
        if year is None:
            year = closed[0] if closed else (years[0] if years else 2024)
    if year is None:
        year = 2024
    per = period or f"FY{str(year)[-2:]}A"

    def _fact(metric: str) -> tuple[float | None, str | None]:
        if not facts:
            return None, None
        hits = [
            f
            for f in facts.facts
            if f.metric_key == metric and int(f.fiscal_year) == int(year) and f.value is not None
        ]
        if not hits:
            return None, None

        def _rank(f: Any) -> tuple[int, int]:
            from agetic_cdd_api.fdd_schemas import CellStatus

            status_rank = {
                CellStatus.PROVEN: 4,
                CellStatus.DRAFT: 2,
                CellStatus.DOUBTFUL: 1,
                CellStatus.MISSING: 0,
            }.get(f.status, 0)
            blob = " ".join(
                [*(f.sources or []), (f.labels.source if f.labels else "") or ""]
            ).lower()
            src = 2 if any(
                h in blob
                for h in ("workbook", "investor", "management", "model", "cim")
            ) else (1 if any(h in blob for h in ("qbo", "quickbooks", "ledger", "xero")) else 0)
            return (status_rank, src)

        best = max(hits, key=_rank)
        return best.value, best.fact_id

    revenue, rev_fid = _fact("revenue")
    ebitda, ebitda_fid = _fact("ebitda")
    if ebitda is None:
        ebitda, ebitda_fid = _fact("operating_profit")

    currency = (scope.currency if scope else None) or "USD"
    scale = (scope.scale if scope else None) or "M"

    doc = QoeWorkbookDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        version=QOE_MODEL_VERSION,
        databook_release_id=manifest.databook_release_id if manifest else None,
        databook_release_version=(
            manifest.databook_release_version if manifest else None
        ),
        currency=currency,
        scale=scale or "M",
        period=per,
        worked_example=False,
        baseline=[
            QoeBaselinePeriod(
                period=per,
                management_reported_ebitda=ebitda,
                diligence_reported_ebitda=ebitda,
                revenue=revenue,
                revenue_fact_id=rev_fid,
                ebitda_fact_id=ebitda_fid,
                basis_note="Seeded from databook fact table",
            )
        ],
        notes=["Register empty — add adjustments via PUT …/qoe/register"],
    )
    return recompute_qoe(doc)


def build_qoe_workbook(
    deal_slug: str,
    run_id: str,
    *,
    worked_example: bool = False,
    update_manifest: bool = True,
) -> QoeWorkbookDoc:
    """Build (or rebuild) QoE workbook and persist."""
    if worked_example:
        doc = build_worked_example_qoe(deal_slug=deal_slug, run_id=run_id)
    else:
        existing = load_qoe_workbook(deal_slug, run_id)
        if existing is not None and existing.register_rows:
            doc = recompute_qoe(existing)
        else:
            doc = build_qoe_from_facts(deal_slug, run_id)
    doc = save_qoe_workbook(doc)

    if update_manifest:
        manifest = load_manifest(deal_slug, run_id)
        if manifest is not None:
            stage = manifest.stage
            # Advance toward P5 when QoE is built.
            if stage in {RunStage.P0, RunStage.P1, RunStage.P2, RunStage.P3, RunStage.P4}:
                stage = RunStage.P5
            save_manifest(
                manifest.model_copy(
                    update={
                        "qoe_built": True,
                        "qoe_version": doc.version,
                        "stage": stage,
                        "model_versions": {
                            **(manifest.model_versions or {}),
                            "fdd_qoe": QOE_MODEL_VERSION,
                        },
                    }
                )
            )
    return doc


def update_qoe_register(
    deal_slug: str,
    run_id: str,
    rows: list[dict[str, Any]] | list[AdjustmentRow],
    *,
    replace: bool = False,
) -> QoeWorkbookDoc:
    """Upsert register rows by adjustment_id; recompute derived tabs."""
    doc = load_qoe_workbook(deal_slug, run_id)
    if doc is None:
        doc = build_qoe_workbook(deal_slug, run_id, update_manifest=True)

    incoming: list[AdjustmentRow] = []
    for raw in rows:
        if isinstance(raw, AdjustmentRow):
            incoming.append(raw)
        else:
            incoming.append(AdjustmentRow.model_validate(raw))

    if replace:
        register = merge_candidates_by_event_key(incoming)
    else:
        by_id = {r.adjustment_id: r for r in doc.register_rows}
        for row in incoming:
            prior = by_id.get(row.adjustment_id)
            if prior is None:
                by_id[row.adjustment_id] = row
            else:
                patch = row.model_dump(exclude_unset=True)
                by_id[row.adjustment_id] = prior.model_copy(update=patch)
        register = merge_candidates_by_event_key(list(by_id.values()))

    # Changing facts under an approved decision → reset decision
    reset: list[AdjustmentRow] = []
    prior_by_id = {r.adjustment_id: r for r in doc.register_rows}
    for row in register:
        old = prior_by_id.get(row.adjustment_id)
        if (
            old is not None
            and old.reviewer_decision == "approved"
            and (
                old.diligence_amount != row.diligence_amount
                or old.treatment != row.treatment
                or [c.model_dump() for c in old.consumes]
                != [c.model_dump() for c in row.consumes]
            )
        ):
            reset.append(
                row.model_copy(
                    update={
                        "reviewer_decision": "pending",
                        "reviewer_by": None,
                        "reviewer_at": None,
                        "reviewer_note": "Reset — underlying facts/treatment changed",
                    }
                )
            )
        else:
            reset.append(row)

    doc = recompute_qoe(
        doc.model_copy(
            update={
                "register_rows": reset,
                "g4_approved": False,
                "approval_id": None,
                "status": ArtefactStatus.DRAFT,
            }
        )
    )
    return save_qoe_workbook(doc)


def assert_g4_approvable(deal_slug: str, run_id: str) -> QoeWorkbookDoc:
    doc = load_qoe_workbook(deal_slug, run_id)
    if doc is None:
        raise QoeValidationError("No QoE workbook — POST …/qoe/build first")
    doc = recompute_qoe(doc)
    if not doc.checks_passed:
        failed = [c.check_id for c in doc.checks if c.blocking and not c.passed]
        raise QoeValidationError(
            "QoE checks failed: " + ", ".join(failed) or "unknown"
        )
    # Allow G4 when pending decisions remain only if we batch-approve them
    # in approve_g4; blockers listed for readiness.
    return doc


def approve_g4(
    deal_slug: str,
    run_id: str,
    *,
    decided_by: str | None = None,
    note: str | None = None,
    approve_adjustment_ids: list[str] | None = None,
    partner_conclusion: bool = False,
) -> tuple[QoeWorkbookDoc, Approval, FddRunManifest]:
    """G4 — lead approves QoE judgements; partner flag for conclusion / pro forma."""
    doc = assert_g4_approvable(deal_slug, run_id)
    existing = load_approval(deal_slug, run_id, GateId.G4)
    if (
        existing is not None
        and existing.status == ArtefactStatus.APPROVED
        and doc.g4_approved
    ):
        manifest = load_manifest(deal_slug, run_id)
        if manifest is None:
            raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
        return doc, existing, manifest

    ids = set(approve_adjustment_ids or [r.adjustment_id for r in doc.register_rows])
    updated_rows: list[AdjustmentRow] = []
    now = _now()
    actor = decided_by or "deal_lead"
    for row in doc.register_rows:
        if row.adjustment_id in ids and row.reviewer_decision == "pending":
            # Partner required for pro forma on non-verified base
            if row.treatment == "pro_forma" and row.evidence_status != "verified":
                if not partner_conclusion:
                    raise GateBlockedError(
                        f"G4 partner conclusion required for pro forma "
                        f"{row.adjustment_id} (evidence={row.evidence_status})"
                    )
            updated_rows.append(
                row.model_copy(
                    update={
                        "reviewer_decision": "approved",
                        "reviewer_by": actor,
                        "reviewer_at": now,
                        "reviewer_note": note,
                    }
                )
            )
        else:
            updated_rows.append(row)

    doc = recompute_qoe(doc.model_copy(update={"register_rows": updated_rows}))
    # Still blocked if residual pending above trivial
    residual = [
        b for b in doc.g4_blockers if b.endswith(":decision_pending")
    ]
    if residual and not partner_conclusion:
        # Batch path: if caller approved all ids, recompute should clear;
        # otherwise refuse.
        still = [
            r.adjustment_id
            for r in doc.register_rows
            if r.reviewer_decision == "pending"
            and doc.trivial_threshold is not None
            and abs(_diligence_amount(r)) >= doc.trivial_threshold
        ]
        if still:
            raise QoeValidationError(
                "G4 incomplete — pending decisions: " + ", ".join(still)
            )

    # Partner conclusion clears pro_forma evidence blockers when flagged
    if partner_conclusion:
        doc = doc.model_copy(
            update={
                "g4_blockers": [
                    b
                    for b in doc.g4_blockers
                    if not b.endswith(":partner_pro_forma_evidence")
                ]
            }
        )

    approval = Approval(
        approval_id=f"appr_{uuid.uuid4().hex[:10]}",
        gate=GateId.G4,
        run_id=run_id,
        deal_slug=deal_slug,
        status=ArtefactStatus.APPROVED,
        decided_at=now,
        decided_by=actor,
        note=note
        or (
            "QoE register approved (G4)"
            + (" — partner conclusion" if partner_conclusion else "")
        ),
        payload={
            "qoe_version": doc.version,
            "adjusted_ebitda_diligence": doc.adjusted_ebitda_diligence,
            "adjusted_ebitda_management": doc.adjusted_ebitda_management,
            "sensitivity_low": doc.sensitivity_low,
            "sensitivity_high": doc.sensitivity_high,
            "pro_forma_ebitda": doc.pro_forma_ebitda,
            "materiality_m": doc.materiality_m,
            "partner_conclusion": partner_conclusion,
            "approved_ids": sorted(ids),
        },
    )
    approval = save_approval(approval)
    doc = save_qoe_workbook(
        doc.model_copy(
            update={
                "g4_approved": True,
                "g4_ready": True,
                "g4_blockers": [],
                "approval_id": approval.approval_id,
                "status": ArtefactStatus.APPROVED,
            }
        )
    )
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
    manifest = save_manifest(
        manifest.model_copy(
            update={
                "g4_approved": True,
                "qoe_built": True,
                "qoe_version": doc.version,
                "stage": RunStage.P5,
                "model_versions": {
                    **(manifest.model_versions or {}),
                    "fdd_qoe": QOE_MODEL_VERSION,
                },
            }
        )
    )
    return doc, approval, manifest
