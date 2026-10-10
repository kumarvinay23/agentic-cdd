"""FDD Phase 8 — QA & review (P8–P9, gates G5–G7).

Check catalogue → issue log (S1–S4) → G5 lead QA → partner challenge (G6)
→ snapshot freeze → G7 hash verify. Material artefact changes reset G5–G7.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    Approval,
    ArtefactStatus,
    ChallengeItem,
    ExhibitCell,
    ExhibitStoreDoc,
    FddRunManifest,
    GateId,
    Issue,
    IssueSeverity,
    QaCheckResult,
    QaPackDoc,
    ReportSpec,
    RunStage,
    SnapshotDoc,
)
from agetic_cdd_api.services_fdd_bridge import GateBlockedError, g6_allowed
from agetic_cdd_api.services_fdd_exhibit import cell_ref, index_cells
from agetic_cdd_api.services_fdd_render import render_stub
from agetic_cdd_api.services_fdd_store import (
    load_approval,
    load_claims_ledger,
    load_commentary,
    load_exhibit_store,
    load_manifest,
    load_qa_pack,
    load_qoe_workbook,
    load_report_spec,
    load_scope_profile,
    load_snapshot,
    save_approval,
    save_manifest,
    save_qa_pack,
    save_snapshot,
)
from agetic_cdd_api.services_fdd_tokens import assert_no_raw_numeric_literals, find_tokens

QA_VERSION = "0.1.0"

_BULLET_RE = re.compile(r"(?m)^\s*[•\-\*]\s+")
_SEVERITIES: frozenset[str] = frozenset({"S1", "S2", "S3", "S4"})
# Hashes compared to decide whether G5/G6 approvals survive a soft rescan.
_MATERIAL_HASH_KEYS = (
    "figures_hash",
    "exhibit_hash",
    "commentary_hash",
    "qoe_hash",
    "report_hash",
    "deck_hash",
)


class QaValidationError(ValueError):
    """Invalid QA payload or failed gate preconditions."""


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _coerce_severity(severity: str) -> IssueSeverity:
    if severity not in _SEVERITIES:
        raise QaValidationError(
            f"Invalid severity {severity!r}; expected one of {sorted(_SEVERITIES)}"
        )
    return severity  # type: ignore[return-value]


def _issue_id(check_id: str, suffix: str = "") -> str:
    """Deterministic id from immutable keys only (never from message prose)."""
    base = f"{check_id}:{suffix}" if suffix else check_id
    return f"iss_{hashlib.sha1(base.encode()).hexdigest()[:10]}"


def _new_check(
    check_id: str,
    *,
    passed: bool,
    message: str,
    severity: IssueSeverity | str = "S1",
    blocking: bool = True,
    origin_stage: RunStage | None = None,
    issue_ids: list[str] | None = None,
) -> QaCheckResult:
    sev = _coerce_severity(str(severity))
    return QaCheckResult(
        check_id=check_id,
        passed=passed,
        message=message,
        severity=sev,
        blocking=blocking,
        origin_stage=origin_stage,
        issue_ids=list(issue_ids or []),
    )


def _open_issue(
    *,
    check_id: str,
    severity: IssueSeverity | str,
    message: str,
    origin_stage: RunStage | None = None,
    cell_ref_s: str | None = None,
    section_id: str | None = None,
    suffix: str = "",
    blocking: bool | None = None,
) -> Issue:
    sev = _coerce_severity(str(severity))
    is_blocking = blocking if blocking is not None else sev == "S1"
    # Prefer caller suffix → cell_ref → section_id → check_id (stable across rescans).
    stable_key = (suffix or cell_ref_s or section_id or check_id).strip()
    return Issue(
        issue_id=_issue_id(check_id, stable_key),
        check_id=check_id,
        severity=sev,
        message=message,
        origin_stage=origin_stage,
        cell_ref=cell_ref_s,
        section_id=section_id,
        status="open",
        blocking=is_blocking,
        created_at=_now(),
    )


def _material_artefacts_changed(
    prior: QaPackDoc | None, hashes: dict[str, str | None]
) -> bool:
    """True when exhibit/render/commentary/QoE hashes differ from the last pack."""
    if prior is None:
        return False
    for key in _MATERIAL_HASH_KEYS:
        old = getattr(prior, key, None)
        new = hashes.get(key)
        # Only compare when both sides have a value — first-time fills are not a change.
        if old and new and old != new:
            return True
    return False


def compute_render_hashes(
    store: ExhibitStoreDoc, spec: ReportSpec
) -> tuple[str, str, str, dict[str, float | None], dict[str, float | None]]:
    """Return (report_hash, deck_hash, figures_hash, report_figs, deck_figs)."""
    report = render_stub(kind="report", spec=spec, store=store)
    deck = render_stub(kind="deck", spec=spec, store=store)
    report_hash = report.content_hash or _stable_hash(
        {"pages": [p.model_dump(mode="json") for p in report.pages], "figures": report.figures}
    )
    deck_hash = deck.content_hash or _stable_hash(
        {"pages": [p.model_dump(mode="json") for p in deck.pages], "figures": deck.figures}
    )
    figures_hash = _stable_hash({"report": report.figures, "deck": deck.figures})
    return report_hash, deck_hash, figures_hash, report.figures, deck.figures


def compute_artefact_hashes(
    deal_slug: str, run_id: str, *, store: ExhibitStoreDoc | None = None
) -> dict[str, str | None]:
    """Hashes used for snapshot freeze / G7 verify."""
    store = store or load_exhibit_store(deal_slug, run_id)
    spec = load_report_spec(deal_slug, run_id)
    manifest = load_manifest(deal_slug, run_id)
    commentary = load_commentary(deal_slug, run_id)
    qoe = load_qoe_workbook(deal_slug, run_id)

    report_hash = deck_hash = figures_hash = None
    if store is not None and spec is not None:
        report_hash, deck_hash, figures_hash, _, _ = compute_render_hashes(store, spec)

    return {
        "report_hash": report_hash,
        "deck_hash": deck_hash,
        "figures_hash": figures_hash,
        "exhibit_hash": _stable_hash(store.model_dump(mode="json")) if store else None,
        "commentary_hash": (
            _stable_hash(commentary.model_dump(mode="json")) if commentary else None
        ),
        "qoe_hash": _stable_hash(qoe.model_dump(mode="json")) if qoe else None,
        "manifest_hash": (
            _stable_hash(manifest.model_dump(mode="json")) if manifest else None
        ),
    }


# ---------------------------------------------------------------------------
# Check catalogue
# ---------------------------------------------------------------------------


def _check_recon(
    store: ExhibitStoreDoc | None, spec: ReportSpec | None
) -> tuple[QaCheckResult, list[Issue]]:
    if store is None or spec is None:
        return (
            _new_check(
                "recon_report_deck",
                passed=False,
                message="Missing exhibit store or report_spec for recon",
                origin_stage=RunStage.P7,
            ),
            [
                _open_issue(
                    check_id="recon_report_deck",
                    severity="S1",
                    message="Cannot reconcile report vs deck — missing artefacts",
                    origin_stage=RunStage.P7,
                    suffix="missing",
                )
            ],
        )
    _rh, _dh, _fh, report_figs, deck_figs = compute_render_hashes(store, spec)
    # Compare non-None figure keys present in either render
    keys = sorted(set(report_figs) | set(deck_figs))
    mismatches: list[str] = []
    for k in keys:
        rv = report_figs.get(k)
        dv = deck_figs.get(k)
        if rv is None and dv is None:
            continue
        if rv is None or dv is None or abs(float(rv) - float(dv)) > 1e-9:
            mismatches.append(k)
    if mismatches:
        iss = _open_issue(
            check_id="recon_report_deck",
            severity="S1",
            message=f"Report/deck figure mismatch: {', '.join(mismatches[:8])}",
            origin_stage=RunStage.P7,
            suffix="mismatch",
        )
        return (
            _new_check(
                "recon_report_deck",
                passed=False,
                message=iss.message,
                origin_stage=RunStage.P7,
                issue_ids=[iss.issue_id],
            ),
            [iss],
        )
    return (
        _new_check(
            "recon_report_deck",
            passed=True,
            message=f"Report and deck share {len(keys)} figure(s)",
            origin_stage=RunStage.P7,
        ),
        [],
    )


def _check_qoe_arithmetic(deal_slug: str, run_id: str) -> tuple[QaCheckResult, list[Issue]]:
    qoe = load_qoe_workbook(deal_slug, run_id)
    if qoe is None:
        return (
            _new_check(
                "arithmetic_qoe_bridge",
                passed=True,
                message="No QoE workbook — arithmetic check skipped",
                severity="S3",
                blocking=False,
                origin_stage=RunStage.P5,
            ),
            [],
        )
    issues: list[Issue] = []
    for i, bridge in enumerate(qoe.bridge):
        expected = round(bridge.reported_ebitda + bridge.adjustments_total, 10)
        if abs(expected - bridge.adjusted_ebitda) > 1e-6:
            iss = _open_issue(
                check_id="arithmetic_qoe_bridge",
                severity="S1",
                message=(
                    f"Bridge period {bridge.period}: reported+adj "
                    f"{expected} ≠ adjusted {bridge.adjusted_ebitda}"
                ),
                origin_stage=RunStage.P5,
                suffix=f"{i}:{bridge.period}",
            )
            issues.append(iss)
    failed_checks = [c for c in qoe.checks if c.blocking and not c.passed]
    for c in failed_checks:
        issues.append(
            _open_issue(
                check_id="arithmetic_qoe_bridge",
                severity="S1",
                message=f"QoE check failed: {c.check_id} — {c.message}",
                origin_stage=RunStage.P5,
                suffix=c.check_id,
            )
        )
    if issues:
        return (
            _new_check(
                "arithmetic_qoe_bridge",
                passed=False,
                message=f"{len(issues)} QoE arithmetic / check fault(s)",
                origin_stage=RunStage.P5,
                issue_ids=[i.issue_id for i in issues],
            ),
            issues,
        )
    return (
        _new_check(
            "arithmetic_qoe_bridge",
            passed=True,
            message="QoE bridge arithmetic OK",
            origin_stage=RunStage.P5,
        ),
        [],
    )


def _check_double_count(deal_slug: str, run_id: str) -> tuple[QaCheckResult, list[Issue]]:
    qoe = load_qoe_workbook(deal_slug, run_id)
    if qoe is None:
        return (
            _new_check(
                "double_count",
                passed=True,
                message="No QoE workbook — double-count check skipped",
                severity="S3",
                blocking=False,
                origin_stage=RunStage.P5,
            ),
            [],
        )
    issues: list[Issue] = []
    for c in qoe.checks:
        if c.check_id in {"consumption_ceiling", "no_double_count"} and not c.passed:
            issues.append(
                _open_issue(
                    check_id="double_count",
                    severity="S1",
                    message=c.message,
                    origin_stage=RunStage.P5,
                    suffix=c.check_id,
                )
            )
    # Heuristic: same fact_id consumed by multiple bridge treatments
    fact_owners: dict[str, list[str]] = {}
    for row in qoe.register_rows:
        if row.treatment not in {"accept", "partial"}:
            continue
        for cons in row.consumes:
            fid = cons.fact_id
            if fid:
                fact_owners.setdefault(str(fid), []).append(row.adjustment_id)
    for fid, owners in fact_owners.items():
        if len(set(owners)) > 1:
            issues.append(
                _open_issue(
                    check_id="double_count",
                    severity="S1",
                    message=f"Fact {fid} consumed by multiple bridge rows: {', '.join(owners)}",
                    origin_stage=RunStage.P5,
                    suffix=fid,
                )
            )
    if issues:
        return (
            _new_check(
                "double_count",
                passed=False,
                message=f"{len(issues)} double-count risk(s)",
                origin_stage=RunStage.P5,
                issue_ids=[i.issue_id for i in issues],
            ),
            issues,
        )
    return (
        _new_check(
            "double_count",
            passed=True,
            message="No double-count signals in QoE register",
            origin_stage=RunStage.P5,
        ),
        [],
    )


def _check_perimeter(deal_slug: str, run_id: str) -> tuple[QaCheckResult, list[Issue]]:
    scope = load_scope_profile(deal_slug, run_id)
    manifest = load_manifest(deal_slug, run_id)
    if scope is None:
        iss = _open_issue(
            check_id="perimeter_scope",
            severity="S2",
            message="No scope profile — perimeter not locked",
            origin_stage=RunStage.P2,
            suffix="missing",
            blocking=False,
        )
        return (
            _new_check(
                "perimeter_scope",
                passed=False,
                message=iss.message,
                severity="S2",
                blocking=False,
                origin_stage=RunStage.P2,
                issue_ids=[iss.issue_id],
            ),
            [iss],
        )
    issues: list[Issue] = []
    if not scope.entities_in:
        issues.append(
            _open_issue(
                check_id="perimeter_scope",
                severity="S1",
                message="Scope entities_in is empty — perimeter leak risk",
                origin_stage=RunStage.P2,
                suffix="empty_entities",
            )
        )
    if manifest and not manifest.g1_approved:
        issues.append(
            _open_issue(
                check_id="perimeter_scope",
                severity="S2",
                message="G1 scope not approved",
                origin_stage=RunStage.P2,
                suffix="g1",
                blocking=False,
            )
        )
    # Flag entities_out appearing in exhibit labels (lite perimeter leak)
    out_names = {e.strip().lower() for e in (scope.entities_out or []) if e.strip()}
    store = load_exhibit_store(deal_slug, run_id)
    if out_names and store is not None:
        for ex in store.exhibits:
            for cell in ex.cells:
                label = (cell.label or "").lower()
                for name in out_names:
                    if name and name in label:
                        issues.append(
                            _open_issue(
                                check_id="perimeter_scope",
                                severity="S1",
                                message=(
                                    f"Perimeter leak: out-of-scope entity "
                                    f"{name!r} in {cell_ref(ex.exhibit_id, cell.cell_id)}"
                                ),
                                origin_stage=RunStage.P2,
                                cell_ref_s=cell_ref(ex.exhibit_id, cell.cell_id),
                                suffix=f"{ex.exhibit_id}.{cell.cell_id}",
                            )
                        )
    blocking = [i for i in issues if i.blocking]
    passed = not blocking
    return (
        _new_check(
            "perimeter_scope",
            passed=passed,
            message=(
                "Perimeter OK"
                if passed and not issues
                else f"{len(issues)} perimeter finding(s)"
            ),
            severity="S1" if blocking else "S2",
            blocking=bool(blocking),
            origin_stage=RunStage.P2,
            issue_ids=[i.issue_id for i in issues],
        ),
        issues,
    )


def _check_evidence_cells(
    store: ExhibitStoreDoc | None,
) -> tuple[QaCheckResult, list[Issue]]:
    if store is None:
        return (
            _new_check(
                "evidence_cells",
                passed=False,
                message="No exhibit store",
                origin_stage=RunStage.P1,
            ),
            [
                _open_issue(
                    check_id="evidence_cells",
                    severity="S1",
                    message="Exhibit store missing",
                    origin_stage=RunStage.P1,
                    suffix="missing",
                )
            ],
        )
    issues: list[Issue] = []
    for ex in store.exhibits:
        for cell in ex.cells:
            if cell.value is None:
                continue
            fid = (cell.fact_id or "").strip()
            ref = cell_ref(ex.exhibit_id, cell.cell_id)
            if not fid:
                issues.append(
                    _open_issue(
                        check_id="evidence_cells",
                        severity="S1",
                        message=f"Cell {ref} has value but no fact_id",
                        origin_stage=RunStage.P1,
                        cell_ref_s=ref,
                        suffix=ref,
                    )
                )
            elif fid.lower().startswith("agent:"):
                issues.append(
                    _open_issue(
                        check_id="evidence_cells",
                        severity="S1",
                        message=f"Agent-seeded figure in exhibit: {ref} ({fid})",
                        origin_stage=RunStage.P3,
                        cell_ref_s=ref,
                        suffix=ref,
                    )
                )
    if issues:
        return (
            _new_check(
                "evidence_cells",
                passed=False,
                message=f"{len(issues)} evidence fault(s)",
                origin_stage=RunStage.P1,
                issue_ids=[i.issue_id for i in issues],
            ),
            issues,
        )
    return (
        _new_check(
            "evidence_cells",
            passed=True,
            message="All valued cells carry non-agent fact_ids",
            origin_stage=RunStage.P1,
        ),
        [],
    )


def _check_commentary(deal_slug: str, run_id: str) -> tuple[list[QaCheckResult], list[Issue]]:
    commentary = load_commentary(deal_slug, run_id)
    checks: list[QaCheckResult] = []
    issues: list[Issue] = []
    if commentary is None:
        checks.append(
            _new_check(
                "typed_figures",
                passed=True,
                message="No commentary — typed-figure check skipped",
                severity="S3",
                blocking=False,
                origin_stage=RunStage.P6,
            )
        )
        checks.append(
            _new_check(
                "consistency_tokens",
                passed=True,
                message="No commentary — token check skipped",
                severity="S3",
                blocking=False,
                origin_stage=RunStage.P6,
            )
        )
        return checks, issues

    # Typed figures
    typed: list[Issue] = []
    for sec in commentary.sections:
        blob = "\n".join([sec.action_title, sec.body] + [s.text for s in sec.sentences])
        faults = assert_no_raw_numeric_literals(blob)
        for f in faults:
            typed.append(
                _open_issue(
                    check_id="typed_figures",
                    severity="S1",
                    message=f"{sec.section_id}: typed figure {f!r}",
                    origin_stage=RunStage.P6,
                    section_id=sec.section_id,
                    suffix=f"{sec.section_id}:{f}",
                )
            )
    for fault in commentary.typed_figure_faults:
        typed.append(
            _open_issue(
                check_id="typed_figures",
                severity="S1",
                message=fault,
                origin_stage=RunStage.P6,
                suffix=fault[:40],
            )
        )
    # Dedupe by issue_id
    by_id = {i.issue_id: i for i in typed}
    typed = list(by_id.values())
    issues.extend(typed)
    checks.append(
        _new_check(
            "typed_figures",
            passed=not typed,
            message=(
                "No typed figures in commentary"
                if not typed
                else f"{len(typed)} typed-figure fault(s)"
            ),
            origin_stage=RunStage.P6,
            issue_ids=[i.issue_id for i in typed],
        )
    )

    # Unresolved tokens
    token_issues: list[Issue] = []
    for tok in commentary.unresolved_tokens:
        token_issues.append(
            _open_issue(
                check_id="consistency_tokens",
                severity="S1",
                message=tok,
                origin_stage=RunStage.P6,
                suffix=tok[:40],
            )
        )
    store = load_exhibit_store(deal_slug, run_id)
    idx = index_cells(store) if store else {}
    for sec in commentary.sections:
        for raw, eid, cid in find_tokens(sec.body):
            if cell_ref(eid, cid) not in idx:
                token_issues.append(
                    _open_issue(
                        check_id="consistency_tokens",
                        severity="S1",
                        message=f"{sec.section_id}: unresolved token {raw}",
                        origin_stage=RunStage.P6,
                        section_id=sec.section_id,
                        cell_ref_s=cell_ref(eid, cid),
                        suffix=f"{sec.section_id}:{raw}",
                    )
                )
    by_id = {i.issue_id: i for i in token_issues}
    token_issues = list(by_id.values())
    issues.extend(token_issues)
    checks.append(
        _new_check(
            "consistency_tokens",
            passed=not token_issues,
            message=(
                "All commentary tokens resolve"
                if not token_issues
                else f"{len(token_issues)} unresolved token(s)"
            ),
            origin_stage=RunStage.P6,
            issue_ids=[i.issue_id for i in token_issues],
        )
    )

    # Completeness — held-back in-scope sections
    held = [
        s
        for s in commentary.sections
        if s.held_back and s.section_id not in {"SEC-J"}
    ]
    held_issues = [
        _open_issue(
            check_id="completeness_sections",
            severity="S2",
            message=f"{s.section_id} held back: {s.held_back_reason or 'no reason'}",
            origin_stage=RunStage.P6,
            section_id=s.section_id,
            suffix=s.section_id,
            blocking=False,
        )
        for s in held
    ]
    issues.extend(held_issues)
    checks.append(
        _new_check(
            "completeness_sections",
            passed=not held_issues,
            message=(
                "No held-back core sections"
                if not held_issues
                else f"{len(held_issues)} section(s) held back"
            ),
            severity="S2",
            blocking=False,
            origin_stage=RunStage.P6,
            issue_ids=[i.issue_id for i in held_issues],
        )
    )
    return checks, issues


def _check_deck_quality(
    store: ExhibitStoreDoc | None, spec: ReportSpec | None
) -> tuple[QaCheckResult, list[Issue]]:
    if store is None or spec is None:
        return (
            _new_check(
                "deck_quality",
                passed=True,
                message="No deck artefacts — skipped",
                severity="S4",
                blocking=False,
                origin_stage=RunStage.P7,
            ),
            [],
        )
    deck = render_stub(kind="deck", spec=spec, store=store)
    issues: list[Issue] = []
    for i, page in enumerate(deck.pages):
        bullets = _BULLET_RE.findall(page.body or "")
        if len(bullets) > 6:
            issues.append(
                _open_issue(
                    check_id="deck_quality",
                    severity="S4",
                    message=f"Slide '{page.title}' has {len(bullets)} bullets (max 6)",
                    origin_stage=RunStage.P7,
                    suffix=f"slide{i}",
                    blocking=False,
                )
            )

    # AS-7 — multi-year exhibits should yield labelled chart series (Period / scale).
    chartable = 0
    try:
        from agetic_cdd_api.report_fdd import _chart_series_from_exhibit

        for ex in store.exhibits:
            if _chart_series_from_exhibit(ex) is not None:
                chartable += 1
    except Exception:
        chartable = 0
    msg = (
        "Deck quality OK"
        if not issues
        else f"{len(issues)} deck quality finding(s)"
    )
    if chartable:
        msg = f"{msg} · {chartable} exhibit(s) chartable with labelled axes"
    return (
        _new_check(
            "deck_quality",
            passed=not issues,
            message=msg,
            severity="S4",
            blocking=False,
            origin_stage=RunStage.P7,
            issue_ids=[i.issue_id for i in issues],
        ),
        issues,
    )


def _check_claims_agent_ban(deal_slug: str, run_id: str) -> tuple[QaCheckResult, list[Issue]]:
    claims = load_claims_ledger(deal_slug, run_id)
    if claims is None:
        return (
            _new_check(
                "claims_agent_figures",
                passed=True,
                message="No claims ledger — skipped",
                severity="S3",
                blocking=False,
                origin_stage=RunStage.P3,
            ),
            [],
        )
    issues: list[Issue] = []
    for c in claims.claims:
        if c.failed or c.test_result in {"contradicted", "unverifiable"}:
            issues.append(
                _open_issue(
                    check_id="claims_agent_figures",
                    severity="S2",
                    message=f"Failed claim {c.claim_id}: {c.text[:120]}",
                    origin_stage=RunStage.P3,
                    suffix=c.claim_id,
                    blocking=False,
                )
            )
    passed = len(issues) == 0
    return (
        _new_check(
            "claims_agent_figures",
            passed=passed,
            message=(
                "No failed claim findings"
                if passed
                else f"{len(issues)} failed claim(s) (S2)"
            ),
            severity="S2",
            blocking=False,  # S2 — does not block G5 alone
            origin_stage=RunStage.P3,
            issue_ids=[i.issue_id for i in issues],
        ),
        issues,
    )


def run_qa_catalogue(
    deal_slug: str, run_id: str
) -> tuple[list[QaCheckResult], list[Issue], dict[str, str | None]]:
    """Execute the Phase 8 check catalogue; return checks, issues, hashes."""
    store = load_exhibit_store(deal_slug, run_id)
    spec = load_report_spec(deal_slug, run_id)
    checks: list[QaCheckResult] = []
    issues: list[Issue] = []

    for fn in (
        lambda: _check_recon(store, spec),
        lambda: _check_qoe_arithmetic(deal_slug, run_id),
        lambda: _check_double_count(deal_slug, run_id),
        lambda: _check_perimeter(deal_slug, run_id),
        lambda: _check_evidence_cells(store),
        lambda: _check_deck_quality(store, spec),
        lambda: _check_claims_agent_ban(deal_slug, run_id),
    ):
        c, iss = fn()
        checks.append(c)
        issues.extend(iss)

    more_checks, more_issues = _check_commentary(deal_slug, run_id)
    checks.extend(more_checks)
    issues.extend(more_issues)

    hashes = compute_artefact_hashes(deal_slug, run_id, store=store)
    return checks, issues, hashes


def _readiness_from_issues(
    issues: list[Issue],
    *,
    challenges: list[ChallengeItem],
    manifest: FddRunManifest | None,
    g5_approved: bool,
) -> tuple[bool, list[str], bool, list[str], int, int]:
    open_issues = [i for i in issues if i.status == "open"]
    open_s1 = [i for i in open_issues if i.severity == "S1"]
    open_s2 = [i for i in open_issues if i.severity == "S2"]
    g5_blockers: list[str] = []
    if open_s1:
        g5_blockers.append(f"open_s1:{len(open_s1)}")
        g5_blockers.extend(i.issue_id for i in open_s1[:5])
    g5_ready = not open_s1

    g6_blockers: list[str] = []
    if not g5_approved and not g5_ready:
        g6_blockers.append("g5_not_ready")
    elif not g5_approved:
        g6_blockers.append("g5_not_approved")
    if manifest is not None and not g6_allowed(manifest):
        g6_blockers.append("draft_mode_or_contract")
    open_challenges = [c for c in challenges if c.status == "open"]
    if open_challenges:
        g6_blockers.append(f"open_challenges:{len(open_challenges)}")
    g6_ready = (
        g5_approved
        and not open_challenges
        and (manifest is None or g6_allowed(manifest))
    )
    return (
        g5_ready,
        g5_blockers,
        g6_ready,
        g6_blockers,
        len(open_s1),
        len(open_s2),
    )


def build_qa_pack(
    deal_slug: str,
    run_id: str,
    *,
    update_manifest: bool = True,
    preserve_challenges: bool = True,
) -> QaPackDoc:
    """Run catalogue, persist qa.json, update manifest stage → P8."""
    prior = load_qa_pack(deal_slug, run_id)
    challenges = list(prior.challenges) if prior and preserve_challenges else []
    # Preserve non-open resolutions by issue_id where possible
    prior_resolved = {
        i.issue_id: i
        for i in (prior.issues if prior else [])
        if i.status != "open"
    }

    checks, fresh_issues, hashes = run_qa_catalogue(deal_slug, run_id)
    merged: list[Issue] = []
    for iss in fresh_issues:
        old = prior_resolved.get(iss.issue_id)
        if old is not None:
            # Keep resolution; refresh message from latest scan for display.
            merged.append(old.model_copy(update={"message": iss.message}))
        else:
            merged.append(iss)

    manifest = load_manifest(deal_slug, run_id)
    material_changed = _material_artefacts_changed(prior, hashes)
    # Soft rescans preserve approvals; only material hash drift clears G5/G6.
    g5_approved = bool(prior.g5_approved) if prior else False
    g6_approved = bool(prior.g6_approved) if prior else False
    if material_changed:
        g5_approved = False
        g6_approved = False

    open_s1 = [i for i in merged if i.status == "open" and i.severity == "S1"]
    g5_ready, g5_blockers, g6_ready, g6_blockers, n_s1, n_s2 = _readiness_from_issues(
        merged,
        challenges=challenges,
        manifest=manifest,
        g5_approved=g5_approved,
    )
    # Approvals stay sticky across soft rescans; readiness still reflects open S1.
    if open_s1 and not g5_approved:
        g5_ready = False

    snap = load_snapshot(deal_slug, run_id)
    notes = [
        "Phase 8 QA catalogue — recon, arithmetic, perimeter, double-count, "
        "evidence, commentary, deck quality",
        f"Checks: {len(checks)}; open S1: {n_s1}; open S2: {n_s2}",
    ]
    if material_changed:
        notes.append("Material artefact hashes changed — G5/G6 approvals cleared")

    doc = QaPackDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        version=QA_VERSION,
        status=ArtefactStatus.CHECKED if g5_ready else ArtefactStatus.DRAFT,
        checks=checks,
        issues=merged,
        challenges=challenges,
        open_s1_count=n_s1,
        open_s2_count=n_s2,
        g5_ready=g5_ready,
        g5_approved=g5_approved,
        g5_blockers=g5_blockers,
        g6_ready=g6_ready,
        g6_approved=g6_approved and g6_ready,
        g6_blockers=g6_blockers,
        snapshot_frozen=snap is not None and snap.status == ArtefactStatus.APPROVED,
        snapshot_id=snap.snapshot_id if snap else None,
        g7_verified=bool(snap.g7_verified) if snap else False,
        report_hash=hashes.get("report_hash"),
        deck_hash=hashes.get("deck_hash"),
        figures_hash=hashes.get("figures_hash"),
        exhibit_hash=hashes.get("exhibit_hash"),
        commentary_hash=hashes.get("commentary_hash"),
        qoe_hash=hashes.get("qoe_hash"),
        notes=notes,
    )
    doc = save_qa_pack(doc)

    if update_manifest and manifest is not None:
        stage = manifest.stage
        if stage in {
            RunStage.P0,
            RunStage.P1,
            RunStage.P2,
            RunStage.P3,
            RunStage.P4,
            RunStage.P5,
            RunStage.P6,
            RunStage.P7,
        }:
            stage = RunStage.P8
        save_manifest(
            manifest.model_copy(
                update={
                    "qa_built": True,
                    "g5_approved": doc.g5_approved,
                    "g6_approved": doc.g6_approved,
                    "g7_verified": doc.g7_verified,
                    "snapshot_id": doc.snapshot_id,
                    "stage": stage,
                    "model_versions": {
                        **(manifest.model_versions or {}),
                        "fdd_qa": QA_VERSION,
                    },
                }
            )
        )
    return doc


def resolve_issue(
    deal_slug: str,
    run_id: str,
    issue_id: str,
    *,
    status: str = "resolved",
    resolved_by: str | None = None,
    note: str | None = None,
) -> QaPackDoc:
    doc = load_qa_pack(deal_slug, run_id)
    if doc is None:
        raise QaValidationError("No QA pack — POST …/qa/scan first")
    if status not in {"resolved", "waived", "accepted", "open"}:
        raise QaValidationError(f"Invalid issue status: {status}")
    found = False
    updated: list[Issue] = []
    for iss in doc.issues:
        if iss.issue_id == issue_id:
            found = True
            # S1 cannot be waived — must resolve with a fix + rescan
            if iss.severity == "S1" and status == "waived":
                raise QaValidationError("S1 blockers cannot be waived — fix and rescan")
            updated.append(
                iss.model_copy(
                    update={
                        "status": status,
                        "resolved_at": _now() if status != "open" else None,
                        "resolved_by": resolved_by,
                        "resolution_note": note,
                    }
                )
            )
        else:
            updated.append(iss)
    if not found:
        raise QaValidationError(f"Issue not found: {issue_id}")
    # Soft resolution does not clear gate approvals — only material hash drift does.
    save_qa_pack(doc.model_copy(update={"issues": updated}))
    return build_qa_pack(deal_slug, run_id, update_manifest=True)


def add_challenge(
    deal_slug: str,
    run_id: str,
    *,
    title: str,
    detail: str | None = None,
    raised_by: str | None = None,
    linked_issue_ids: list[str] | None = None,
) -> QaPackDoc:
    doc = load_qa_pack(deal_slug, run_id) or build_qa_pack(
        deal_slug, run_id, update_manifest=True
    )
    item = ChallengeItem(
        challenge_id=f"ch_{uuid.uuid4().hex[:10]}",
        title=title,
        detail=detail,
        raised_by=raised_by,
        raised_at=_now(),
        status="open",
        linked_issue_ids=list(linked_issue_ids or []),
    )
    challenges = list(doc.challenges) + [item]
    save_qa_pack(
        doc.model_copy(
            update={"challenges": challenges, "g6_approved": False, "g6_ready": False}
        )
    )
    return build_qa_pack(deal_slug, run_id, update_manifest=True)


def respond_challenge(
    deal_slug: str,
    run_id: str,
    challenge_id: str,
    *,
    status: str,
    response: str | None = None,
    responded_by: str | None = None,
) -> QaPackDoc:
    doc = load_qa_pack(deal_slug, run_id)
    if doc is None:
        raise QaValidationError("No QA pack — POST …/qa/scan first")
    if status not in {"addressed", "accepted", "withdrawn", "open"}:
        raise QaValidationError(f"Invalid challenge status: {status}")
    found = False
    updated: list[ChallengeItem] = []
    for ch in doc.challenges:
        if ch.challenge_id == challenge_id:
            found = True
            updated.append(
                ch.model_copy(
                    update={
                        "status": status,
                        "response": response,
                        "responded_at": _now(),
                        "responded_by": responded_by,
                    }
                )
            )
        else:
            updated.append(ch)
    if not found:
        raise QaValidationError(f"Challenge not found: {challenge_id}")
    save_qa_pack(doc.model_copy(update={"challenges": updated, "g6_approved": False}))
    return build_qa_pack(deal_slug, run_id, update_manifest=True)


def assert_g5_approvable(deal_slug: str, run_id: str) -> QaPackDoc:
    doc = load_qa_pack(deal_slug, run_id)
    if doc is None:
        doc = build_qa_pack(deal_slug, run_id, update_manifest=True)
    if not doc.g5_ready or doc.open_s1_count > 0:
        raise GateBlockedError(
            "G5 blocked by open S1 issues: "
            + ", ".join(doc.g5_blockers[:8])
        )
    return doc


def approve_g5(
    deal_slug: str,
    run_id: str,
    *,
    decided_by: str | None = None,
    note: str | None = None,
) -> tuple[QaPackDoc, Approval, FddRunManifest]:
    """G5 — lead confirms QA catalogue clean of S1 blockers."""
    doc = assert_g5_approvable(deal_slug, run_id)
    existing = load_approval(deal_slug, run_id, GateId.G5)
    if (
        existing is not None
        and existing.status == ArtefactStatus.APPROVED
        and doc.g5_approved
    ):
        manifest = load_manifest(deal_slug, run_id)
        if manifest is None:
            raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
        return doc, existing, manifest

    approval = Approval(
        approval_id=f"appr_{uuid.uuid4().hex[:10]}",
        gate=GateId.G5,
        run_id=run_id,
        deal_slug=deal_slug,
        status=ArtefactStatus.APPROVED,
        decided_at=_now(),
        decided_by=decided_by or "deal_lead",
        note=note or "QA catalogue clear of S1 (G5)",
        payload={
            "open_s1_count": doc.open_s1_count,
            "open_s2_count": doc.open_s2_count,
            "check_ids": [c.check_id for c in doc.checks if c.passed],
            "figures_hash": doc.figures_hash,
        },
    )
    approval = save_approval(approval)
    # Mark G5 approved on disk before rescan so readiness treats it as approved.
    save_qa_pack(
        doc.model_copy(
            update={
                "g5_approved": True,
                "g5_ready": True,
                "g5_blockers": [],
                "status": ArtefactStatus.APPROVED,
            }
        )
    )
    doc = build_qa_pack(deal_slug, run_id, update_manifest=False)
    # build_qa_pack preserves prior.g5_approved when no new S1 opens
    if not doc.g5_approved:
        doc = save_qa_pack(doc.model_copy(update={"g5_approved": True, "g5_ready": True}))

    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
    stage = RunStage.P8
    manifest = save_manifest(
        manifest.model_copy(
            update={
                "qa_built": True,
                "g5_approved": True,
                "stage": stage,
                "model_versions": {
                    **(manifest.model_versions or {}),
                    "fdd_qa": QA_VERSION,
                },
            }
        )
    )
    return doc, approval, manifest


def assert_g6_partner_approvable(deal_slug: str, run_id: str) -> QaPackDoc:
    """Partner challenge gate — requires G5 + non-draft contract + no open challenges."""
    from agetic_cdd_api.services_fdd_bridge import assert_g6_allowed

    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
    assert_g6_allowed(manifest)
    doc = load_qa_pack(deal_slug, run_id)
    if doc is None:
        raise GateBlockedError("G6 blocked — no QA pack; POST …/qa/scan first")
    if not doc.g5_approved:
        raise GateBlockedError("G6 blocked until G5 is approved")
    open_ch = [c for c in doc.challenges if c.status == "open"]
    if open_ch:
        raise GateBlockedError(
            f"G6 blocked by {len(open_ch)} open challenge(s): "
            + ", ".join(c.challenge_id for c in open_ch[:5])
        )
    return doc


def approve_g6(
    deal_slug: str,
    run_id: str,
    *,
    decided_by: str | None = None,
    note: str | None = None,
) -> tuple[QaPackDoc, Approval, FddRunManifest]:
    """G6 — partner signs off after challenge list is clear."""
    doc = assert_g6_partner_approvable(deal_slug, run_id)
    existing = load_approval(deal_slug, run_id, GateId.G6)
    if (
        existing is not None
        and existing.status == ArtefactStatus.APPROVED
        and doc.g6_approved
    ):
        manifest = load_manifest(deal_slug, run_id)
        if manifest is None:
            raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
        return doc, existing, manifest

    approval = Approval(
        approval_id=f"appr_{uuid.uuid4().hex[:10]}",
        gate=GateId.G6,
        run_id=run_id,
        deal_slug=deal_slug,
        status=ArtefactStatus.APPROVED,
        decided_at=_now(),
        decided_by=decided_by or "partner",
        note=note or "Partner challenge complete (G6)",
        payload={
            "challenges": len(doc.challenges),
            "figures_hash": doc.figures_hash,
            "g5_approval": True,
        },
    )
    approval = save_approval(approval)
    doc = save_qa_pack(
        doc.model_copy(
            update={
                "g6_approved": True,
                "g6_ready": True,
                "g6_blockers": [],
            }
        )
    )
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
    manifest = save_manifest(
        manifest.model_copy(
            update={
                "g6_approved": True,
                "stage": RunStage.P9,
                "g6_blocked": False,
            }
        )
    )
    return doc, approval, manifest


def freeze_snapshot(
    deal_slug: str,
    run_id: str,
    *,
    frozen_by: str | None = None,
    note: str | None = None,
) -> SnapshotDoc:
    """Freeze artefact hashes after G6 (or G5 for draft dry-runs with allow)."""
    doc = load_qa_pack(deal_slug, run_id)
    if doc is None:
        raise QaValidationError("No QA pack — POST …/qa/scan first")
    if not doc.g5_approved:
        raise GateBlockedError("Snapshot freeze requires G5 approval")
    hashes = compute_artefact_hashes(deal_slug, run_id)
    if not hashes.get("figures_hash"):
        raise QaValidationError("Cannot freeze — missing report/deck hashes")

    snap = SnapshotDoc(
        snapshot_id=f"snap_{uuid.uuid4().hex[:10]}",
        run_id=run_id,
        deal_slug=deal_slug,
        frozen_at=_now(),
        frozen_by=frozen_by or "deal_lead",
        report_hash=str(hashes["report_hash"]),
        deck_hash=str(hashes["deck_hash"]),
        figures_hash=str(hashes["figures_hash"]),
        exhibit_hash=str(hashes.get("exhibit_hash") or ""),
        commentary_hash=hashes.get("commentary_hash"),
        qoe_hash=hashes.get("qoe_hash"),
        manifest_hash=hashes.get("manifest_hash"),
        status=ArtefactStatus.APPROVED,
        note=note,
    )
    snap = save_snapshot(snap)
    save_qa_pack(
        doc.model_copy(
            update={
                "snapshot_frozen": True,
                "snapshot_id": snap.snapshot_id,
                "g7_verified": False,
                "report_hash": snap.report_hash,
                "deck_hash": snap.deck_hash,
                "figures_hash": snap.figures_hash,
            }
        )
    )
    manifest = load_manifest(deal_slug, run_id)
    if manifest is not None:
        save_manifest(
            manifest.model_copy(
                update={
                    "snapshot_id": snap.snapshot_id,
                    "g7_verified": False,
                    "stage": RunStage.P10
                    if manifest.g6_approved
                    else manifest.stage,
                }
            )
        )
    return snap


def verify_g7(
    deal_slug: str,
    run_id: str,
    *,
    decided_by: str | None = None,
    note: str | None = None,
) -> tuple[SnapshotDoc, Approval, FddRunManifest]:
    """G7 — current artefact hashes must match the frozen snapshot."""
    snap = load_snapshot(deal_slug, run_id)
    if snap is None:
        raise GateBlockedError("G7 blocked — no frozen snapshot; POST …/snapshot/freeze")
    current = compute_artefact_hashes(deal_slug, run_id)
    mismatch: list[str] = []
    for key in (
        "report_hash",
        "deck_hash",
        "figures_hash",
        "exhibit_hash",
        "commentary_hash",
        "qoe_hash",
    ):
        frozen = getattr(snap, key, None)
        now = current.get(key)
        if frozen and now and frozen != now:
            mismatch.append(f"{key}: frozen={frozen} current={now}")
    if mismatch:
        snap = save_snapshot(
            snap.model_copy(
                update={"g7_verified": False, "g7_mismatch": mismatch}
            )
        )
        raise GateBlockedError(
            "G7 hash mismatch — material change since freeze: "
            + "; ".join(mismatch[:4])
        )

    approval = Approval(
        approval_id=f"appr_{uuid.uuid4().hex[:10]}",
        gate=GateId.G7,
        run_id=run_id,
        deal_slug=deal_slug,
        status=ArtefactStatus.APPROVED,
        decided_at=_now(),
        decided_by=decided_by or "system",
        note=note or "Snapshot hashes verified (G7)",
        payload={
            "snapshot_id": snap.snapshot_id,
            "figures_hash": snap.figures_hash,
        },
    )
    approval = save_approval(approval)
    snap = save_snapshot(
        snap.model_copy(
            update={
                "g7_verified": True,
                "g7_verified_at": _now(),
                "g7_mismatch": [],
            }
        )
    )
    qa = load_qa_pack(deal_slug, run_id)
    if qa is not None:
        save_qa_pack(qa.model_copy(update={"g7_verified": True}))

    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
    manifest = save_manifest(
        manifest.model_copy(
            update={
                "g7_verified": True,
                "snapshot_id": snap.snapshot_id,
                "stage": RunStage.P10,
                "status": ArtefactStatus.APPROVED,
            }
        )
    )
    return snap, approval, manifest


def reset_gates_on_material_change(
    deal_slug: str,
    run_id: str,
    *,
    reason: str = "material artefact change",
) -> FddRunManifest:
    """Invalidate G5–G7 (and freeze) when exhibits / commentary / QoE change."""
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")

    qa = load_qa_pack(deal_slug, run_id)
    if qa is not None:
        save_qa_pack(
            qa.model_copy(
                update={
                    "g5_approved": False,
                    "g6_approved": False,
                    "g7_verified": False,
                    "snapshot_frozen": False,
                    "snapshot_id": None,
                    "status": ArtefactStatus.DRAFT,
                    "notes": list(qa.notes or [])
                    + [f"Gates reset: {reason}"],
                }
            )
        )

    # Supersede gate approvals G5–G7
    for gate in (GateId.G5, GateId.G6, GateId.G7):
        appr = load_approval(deal_slug, run_id, gate)
        if appr is not None and appr.status == ArtefactStatus.APPROVED:
            save_approval(
                appr.model_copy(
                    update={
                        "status": ArtefactStatus.SUPERSEDED,
                        "note": (appr.note or "") + f" · superseded: {reason}",
                    }
                )
            )

    snap = load_snapshot(deal_slug, run_id)
    if snap is not None:
        save_snapshot(
            snap.model_copy(
                update={
                    "status": ArtefactStatus.SUPERSEDED,
                    "g7_verified": False,
                    "note": (snap.note or "") + f" · superseded: {reason}",
                }
            )
        )

    return save_manifest(
        manifest.model_copy(
            update={
                "g5_approved": False,
                "g6_approved": False,
                "g7_verified": False,
                "snapshot_id": None,
                "note": (manifest.note or "") + f" · gates reset: {reason}",
            }
        )
    )


def seed_s1_agent_figure(
    deal_slug: str, run_id: str, *, exhibit_id: str | None = None
) -> ExhibitCell:
    """Test / trap helper — inject an agent-seeded figure (S1 evidence fault)."""
    from agetic_cdd_api.services_fdd_exhibit import (
        load_or_empty,
        persist_store,
        upsert_cells,
    )
    from agetic_cdd_api.fdd_schemas import CellStatus, EvidenceTier, FigureType

    store = load_or_empty(deal_slug, run_id)
    eid = exhibit_id or (store.exhibits[0].exhibit_id if store.exhibits else "ex_trap")
    cell = ExhibitCell(
        cell_id="agent_trap",
        exhibit_id=eid,
        label="Agent trap figure",
        value=42.0,
        display="42",
        fact_id="agent:trap:42",
        figure_type=FigureType.ESTIMATED,
        evidence_tier=EvidenceTier.C,
        status=CellStatus.DRAFT,
    )
    store = upsert_cells(
        store,
        [cell],
        exhibit_titles={eid: eid},
        section_ids={eid: "SEC-B"},
    )
    persist_store(deal_slug, run_id, store)
    reset_gates_on_material_change(deal_slug, run_id, reason="seeded S1 agent figure")
    return cell
