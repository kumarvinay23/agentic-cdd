"""FDD run / exhibit API — Phase 0–8 surfaces (… commentary, QA G5–G7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agetic_cdd_api.db import get_db
from agetic_cdd_api.deps import AuthContext, get_current_auth
from agetic_cdd_api.services_databook_store import load_current_release, load_release
from agetic_cdd_api.services_deals import get_deal, resolve_deal_storage_key
from agetic_cdd_api.services_fdd_bridge import (
    GateBlockedError,
    ReleasePinError,
    assert_g6_allowed,
    assess_databook_contract,
    bridge_release_into_run,
    check_release_pin,
    g6_allowed,
    resolve_release_for_deal,
)
from agetic_cdd_api.services_fdd_deps import dependents_of
from agetic_cdd_api.services_fdd_exhibit import cell_ref, update_cell_value
from agetic_cdd_api.fdd_schemas import AdjustmentRow, FddRunManifest
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_fdd_claims import (
    acknowledge_g2,
    build_claims_ledger,
    evaluate_g2,
)
from agetic_cdd_api.services_fdd_evidence import (
    EvidenceValidationError,
    list_claim_gaps,
    patch_request_status,
    run_p3_evidence_pass,
    suggest_filenames,
)
from agetic_cdd_api.services_fdd_commentary import (
    CommentaryValidationError,
    build_commentary,
    get_section,
    validate_section_draft,
)
from agetic_cdd_api.services_fdd_qa import (
    QaValidationError,
    add_challenge,
    approve_g5,
    approve_g6,
    build_qa_pack,
    freeze_snapshot,
    reset_gates_on_material_change,
    resolve_issue,
    respond_challenge,
    verify_g7,
)
from agetic_cdd_api.services_fdd_models import ensure_phase5b_models
from agetic_cdd_api.services_fdd_qoe import (
    QoeValidationError,
    approve_g4,
    build_qoe_workbook,
    update_qoe_register,
)
from agetic_cdd_api.services_fdd_render import (
    ensure_phase0_run,
    load_run_bundle,
    refresh_spec_after_cell_change,
    render_stub,
)
from agetic_cdd_api.services_fdd_scope import (
    ScopeValidationError,
    approve_g1,
    ensure_phase2_artefacts,
    seed_scope_profile,
    update_scope_profile,
    validate_scope_for_g1,
)
from agetic_cdd_api.services_fdd_store import (
    create_run,
    list_approvals,
    list_runs,
    load_approval,
    load_claims_ledger,
    load_commentary,
    load_dependency_graph,
    load_evidence_pass,
    load_exhibit_store,
    load_fact_table,
    load_manifest,
    load_model_checks,
    load_qa_pack,
    load_qoe_workbook,
    load_readiness,
    load_report_spec,
    load_request_list,
    load_scope_profile,
    load_snapshot,
)

router = APIRouter(tags=["fdd"])


class CreateFddRunBody(BaseModel):
    databook_release_id: str | None = None
    databook_release_version: int | None = None
    note: str | None = None
    seed_stub_exhibit: bool = True
    bridge_databook: bool = True
    allow_pinned_release: bool = False
    revenue_fy24: float | None = None


class UpdateFddCellBody(BaseModel):
    value: float
    display: str | None = None


class UpdateScopeBody(BaseModel):
    entities_in: list[str] | None = None
    entities_out: list[str] | None = None
    deal_type: str | None = None
    periods: list[str] | None = None
    currency: str | None = None
    scale: str | None = None
    materiality_m: float | None = None
    materiality_basis: str | None = None
    materiality_pct: float | None = None
    sections_in_scope: list[str] | None = None
    notes: str | None = None
    allow_edit_approved: bool = False


class ApproveG1Body(BaseModel):
    note: str | None = None
    require_g0: bool = True


class AcknowledgeG2Body(BaseModel):
    note: str | None = None
    allow_unreliable: bool = True


class BuildClaimsBody(BaseModel):
    open_requests: bool = True
    agent_keys: list[str] | None = None


class EvidenceRetrieveBody(BaseModel):
    """Phase 4 / P3 — targeted databook rescan from claim gaps."""

    mode: str = "rescan"  # rescan | reread | deep | rebridge
    filenames: list[str] | None = None
    rebridge: bool = True
    rebuild_claims: bool = True
    dry_run: bool = False
    open_requests: bool = True


class PatchRequestBody(BaseModel):
    status: str  # pending | requested | received | waived


class BuildQoeBody(BaseModel):
    worked_example: bool = False


class UpdateQoeRegisterBody(BaseModel):
    """Typed register rows — validated at the FastAPI edge (no raw dict dump)."""

    rows: list[AdjustmentRow]
    replace: bool = False


class ApproveG4Body(BaseModel):
    note: str | None = None
    approve_adjustment_ids: list[str] | None = None
    partner_conclusion: bool = False


class BuildCommentaryBody(BaseModel):
    section_ids: list[str] | None = None
    update_report_spec: bool = True


class ResolveIssueBody(BaseModel):
    status: str = "resolved"  # resolved | waived | accepted | open
    note: str | None = None


class ChallengeBody(BaseModel):
    title: str
    detail: str | None = None
    linked_issue_ids: list[str] | None = None


class RespondChallengeBody(BaseModel):
    status: str  # addressed | accepted | withdrawn | open
    response: str | None = None


class ApproveGateBody(BaseModel):
    note: str | None = None


class FreezeSnapshotBody(BaseModel):
    note: str | None = None


# Scope fields that may be patched via PUT …/scope (exclude control flags).
_SCOPE_PATCH_KEYS = frozenset(
    {
        "entities_in",
        "entities_out",
        "deal_type",
        "periods",
        "currency",
        "scale",
        "materiality_m",
        "materiality_basis",
        "materiality_pct",
        "sections_in_scope",
        "notes",
    }
)

_RUN_INCLUDE_ALL = frozenset(
    {
        "exhibits",
        "facts",
        "report_spec",
        "scope",
        "readiness",
        "claims",
        "qoe",
        "commentary",
        "qa",
        "snapshot",
    }
)


def _http_qoe_error(exc: QoeValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _http_qa_error(exc: QaValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _http_not_found(detail: str, exc: Exception | None = None) -> HTTPException:
    """404 without leaking filesystem paths from FileNotFoundError."""
    return HTTPException(status_code=404, detail=detail)


def _http_gate_blocked(exc: GateBlockedError, *, gate: str) -> HTTPException:
    """409 Conflict for governance / state-machine blocks with actionable context."""
    return HTTPException(
        status_code=409,
        detail={
            "gate": gate,
            "message": str(exc),
            "hint": "Resolve the blocking condition for this gate, then retry.",
        },
    )


def _deal_or_404(db: Session, deal_id: str, auth: AuthContext) -> Deal:
    """Resolve deal within the caller's org (API tenancy gate)."""
    return get_deal(db, deal_id=deal_id, org_id=auth.organization.id)


def _deal_storage_key(deal: Deal) -> str:
    """Org-scoped disk key; falls back to legacy slug-only workspace when present."""
    return resolve_deal_storage_key(deal)


def _get_deal_and_manifest(
    db: Session, deal_id: str, run_id: str, auth: AuthContext
) -> tuple[Deal, FddRunManifest]:
    """Org-scoped deal + existing FDD run, or 404."""
    deal = _deal_or_404(db, deal_id, auth)
    storage_key = _deal_storage_key(deal)
    manifest = load_manifest(storage_key, run_id)
    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail=f"FDD run '{run_id}' not found for deal '{deal_id}'",
        )
    return deal, manifest


def _deal_brief_fields(deal: Deal) -> dict[str, str | None]:
    return {
        "company": deal.company or deal.name or None,
        "description": deal.description or None,
        "sector": deal.sector or None,
    }


def _actor_id(auth: AuthContext) -> str:
    """Strong audit actor for G1/G4/G6 — requires user or member identity."""
    user = auth.user
    for attr in ("email", "id"):
        value = getattr(user, attr, None) if user is not None else None
        if value:
            return str(value)
    member_id = getattr(auth.member, "id", None) if auth.member is not None else None
    if member_id:
        return f"member:{member_id}"
    raise HTTPException(
        status_code=403,
        detail="Authenticated user identity required for governance gate approval",
    )


def _http_scope_error(exc: ScopeValidationError) -> HTTPException:
    """Invalid / incomplete scope payload → 422 (not a gate state conflict)."""
    return HTTPException(status_code=422, detail=str(exc))


def _parse_include(include: str | None) -> set[str]:
    """Parse ``?include=``; unknown keys → 422. Empty / ``*`` / omitted → all."""
    if include is None or not str(include).strip() or str(include).strip() == "*":
        return set(_RUN_INCLUDE_ALL)
    parts = {p.strip().lower() for p in str(include).split(",") if p.strip()}
    if not parts:
        return set(_RUN_INCLUDE_ALL)
    unknown = parts - _RUN_INCLUDE_ALL
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Unknown include field(s): {', '.join(sorted(unknown))}",
                "allowed": sorted(_RUN_INCLUDE_ALL),
            },
        )
    return parts


def _resolve_run_release_pin(
    deal: Deal,
    storage_key: str,
    *,
    release_id: str | None,
    release_version: int | None,
) -> tuple[str | None, int | None]:
    """Fill release id/version from current or named release when either side is omitted."""
    if release_id is None:
        release = load_current_release(deal)
        if release is None:
            release = resolve_release_for_deal(storage_key, bootstrap=True)
        if release is not None:
            return release.release_id, release.version
        return None, release_version

    if release_version is not None:
        return release_id, release_version

    # Explicit id without version — load the named release so pin checks can compare.
    pinned = load_release(deal, release_id)
    if pinned is None:
        pinned = resolve_release_for_deal(
            storage_key, release_id=release_id, bootstrap=False
        )
    if pinned is not None:
        return release_id, pinned.version
    return release_id, None


@router.post("/portfolios/{deal_id}/fdd/runs")
def create_fdd_run(
    deal_id: str,
    body: CreateFddRunBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal = _deal_or_404(db, deal_id, auth)
    storage_key = _deal_storage_key(deal)
    body = body or CreateFddRunBody()
    release_id, release_version = _resolve_run_release_pin(
        deal,
        storage_key,
        release_id=body.databook_release_id,
        release_version=body.databook_release_version,
    )

    phase0_kwargs: dict[str, Any] = {
        "databook_release_id": release_id,
        "databook_release_version": release_version,
        "company": deal.name or deal.slug,
        "force_new": True,
        "allow_pinned_release": body.allow_pinned_release,
        "bridge_databook": body.bridge_databook,
    }
    if body.revenue_fy24 is not None:
        phase0_kwargs["revenue_fy24"] = body.revenue_fy24

    try:
        if body.seed_stub_exhibit or body.bridge_databook:
            manifest, store, spec = ensure_phase0_run(storage_key, **phase0_kwargs)
        else:
            manifest = create_run(
                storage_key,
                databook_release_id=release_id,
                databook_release_version=release_version,
                note=body.note,
                draft_mode=True,
                allow_pinned_release=body.allow_pinned_release,
            )
            store = load_exhibit_store(storage_key, manifest.run_id)
            spec = None
    except ReleasePinError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    facts = load_fact_table(storage_key, manifest.run_id)
    scope = load_scope_profile(storage_key, manifest.run_id)
    readiness = load_readiness(storage_key, manifest.run_id)
    return {
        "success": True,
        "data": {
            "manifest": manifest.model_dump(mode="json"),
            "exhibit_count": len(store.exhibits) if store else 0,
            "fact_count": len(facts.facts) if facts else 0,
            "draft_mode": manifest.draft_mode,
            "contract_complete": manifest.contract_complete,
            "g6_blocked": manifest.g6_blocked,
            "g0_passed": manifest.g0_passed,
            "g1_approved": manifest.g1_approved,
            "claims_built": manifest.claims_built,
            "g2_passed": manifest.g2_passed,
            "qoe_built": manifest.qoe_built,
            "g4_approved": manifest.g4_approved,
            "unreliable_modules": list(manifest.unreliable_modules or []),
            "scope_profile_id": scope.profile_id if scope else None,
            "readiness_score": readiness.score if readiness else None,
            "spec_id": spec.spec_id if spec else None,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs")
def list_fdd_runs(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal = _deal_or_404(db, deal_id, auth)
    return {"success": True, "data": list_runs(_deal_storage_key(deal))}


@router.get("/portfolios/{deal_id}/fdd/contract")
def get_fdd_contract(
    deal_id: str,
    release_id: str | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Assess whether the current/pinned release meets FDD databook minimum."""
    deal = _deal_or_404(db, deal_id, auth)
    storage_key = _deal_storage_key(deal)
    release = resolve_release_for_deal(
        storage_key, release_id=release_id, bootstrap=True
    )
    assessment = assess_databook_contract(release, deal_slug=storage_key)
    return {"success": True, "data": assessment.model_dump(mode="json")}


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}")
def get_fdd_run(
    deal_id: str,
    run_id: str,
    include: str | None = Query(
        default=None,
        description=(
            "Comma-separated artefacts to include "
            "(exhibits,facts,report_spec,scope,readiness,claims,qoe,commentary,qa,snapshot). "
            "Default / * = all. Manifest always returned."
        ),
    ),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal = _deal_or_404(db, deal_id, auth)
    storage_key = _deal_storage_key(deal)
    want = _parse_include(include)
    need_bundle = bool(want & {"exhibits", "report_spec"})
    store = None
    spec = None
    try:
        if need_bundle:
            manifest, store, spec = load_run_bundle(storage_key, run_id)
        else:
            manifest = load_manifest(storage_key, run_id)
            if manifest is None:
                raise FileNotFoundError(run_id)
    except FileNotFoundError as exc:
        manifest = load_manifest(storage_key, run_id)
        if manifest is None:
            raise _http_not_found(
                f"FDD run '{run_id}' not found for deal '{deal_id}'", exc
            ) from exc
        if "exhibits" in want:
            store = load_exhibit_store(storage_key, run_id)
        if "report_spec" in want:
            spec = load_report_spec(storage_key, run_id)

    facts = load_fact_table(storage_key, run_id) if "facts" in want else None
    scope = load_scope_profile(storage_key, run_id) if "scope" in want else None
    readiness = load_readiness(storage_key, run_id) if "readiness" in want else None
    claims = load_claims_ledger(storage_key, run_id) if "claims" in want else None
    qoe = load_qoe_workbook(storage_key, run_id) if "qoe" in want else None
    commentary = (
        load_commentary(storage_key, run_id) if "commentary" in want else None
    )
    qa = load_qa_pack(storage_key, run_id) if "qa" in want else None
    snapshot = load_snapshot(storage_key, run_id) if "snapshot" in want else None
    return {
        "success": True,
        "data": {
            "manifest": manifest.model_dump(mode="json"),
            "exhibits": (
                store.model_dump(mode="json")
                if store is not None and "exhibits" in want
                else None
            ),
            "facts": facts.model_dump(mode="json") if facts else None,
            "report_spec": (
                spec.model_dump(mode="json")
                if spec is not None and "report_spec" in want
                else None
            ),
            "scope": scope.model_dump(mode="json") if scope else None,
            "readiness": readiness.model_dump(mode="json") if readiness else None,
            "claims": claims.model_dump(mode="json") if claims else None,
            "qoe": qoe.model_dump(mode="json") if qoe else None,
            "commentary": commentary.model_dump(mode="json") if commentary else None,
            "qa": qa.model_dump(mode="json") if qa else None,
            "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
            "g6_allowed": g6_allowed(manifest),
            "g0_passed": manifest.g0_passed,
            "g1_approved": manifest.g1_approved,
            "g4_approved": manifest.g4_approved,
            "g5_approved": manifest.g5_approved,
            "g6_approved": manifest.g6_approved,
            "g7_verified": manifest.g7_verified,
            "claims_built": manifest.claims_built,
            "qoe_built": manifest.qoe_built,
            "commentary_built": manifest.commentary_built,
            "qa_built": manifest.qa_built,
            "unreliable_modules": list(manifest.unreliable_modules or []),
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/bridge")
def post_fdd_bridge(
    deal_id: str,
    run_id: str,
    allow_pinned_release: bool = False,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Re-run Phase 1 bridge from pinned/current databook release."""
    deal, manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    try:
        check_release_pin(
            manifest.model_copy(
                update={"allow_pinned_release": allow_pinned_release
                        or manifest.allow_pinned_release}
            )
        )
        manifest, facts, store, assessment = bridge_release_into_run(
            storage_key,
            run_id,
            release_id=manifest.databook_release_id,
            allow_pinned_release=allow_pinned_release
            or manifest.allow_pinned_release,
            company=deal.name or deal.slug,
        )
    except ReleasePinError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G6") from exc
    except FileNotFoundError as exc:
        raise _http_not_found("Bridge release artefacts not found", exc) from exc
    return {
        "success": True,
        "data": {
            "manifest": manifest.model_dump(mode="json"),
            "assessment": assessment.model_dump(mode="json"),
            "fact_count": len(facts.facts),
            "exhibit_count": len(store.exhibits),
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/facts")
def get_fdd_facts(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    facts = load_fact_table(_deal_storage_key(deal), run_id)
    if facts is None:
        raise HTTPException(status_code=404, detail="Fact table not found")
    return {"success": True, "data": facts.model_dump(mode="json")}


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/exhibits")
def get_fdd_exhibits(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    store = load_exhibit_store(_deal_storage_key(deal), run_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Exhibit store not found")
    return {"success": True, "data": store.model_dump(mode="json")}


@router.put("/portfolios/{deal_id}/fdd/runs/{run_id}/exhibits/{exhibit_id}/cells/{cell_id}")
def put_fdd_cell(
    deal_id: str,
    run_id: str,
    exhibit_id: str,
    cell_id: str,
    body: UpdateFddCellBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    store = load_exhibit_store(storage_key, run_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Exhibit store not found")
    if load_report_spec(storage_key, run_id) is None:
        raise HTTPException(status_code=404, detail="Report spec not found for this run")
    try:
        updated_store = update_cell_value(
            store, exhibit_id, cell_id, body.value, display=body.display
        )
        spec = refresh_spec_after_cell_change(
            storage_key, run_id, updated_store, company=deal.name or deal.slug
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Cell '{cell_id}' not found in exhibit '{exhibit_id}'",
        ) from exc
    except FileNotFoundError as exc:
        raise _http_not_found("Report spec not found for this run", exc) from exc
    # Material figure change invalidates G5–G7 / frozen snapshot.
    try:
        reset_gates_on_material_change(
            storage_key, run_id, reason=f"cell edit {exhibit_id}.{cell_id}"
        )
    except FileNotFoundError:
        pass
    report = render_stub(kind="report", spec=spec, store=updated_store)
    deck = render_stub(kind="deck", spec=spec, store=updated_store)
    ref = cell_ref(exhibit_id, cell_id)
    return {
        "success": True,
        "data": {
            "cell_ref": ref,
            "value": body.value,
            "report_figures": report.figures,
            "deck_figures": deck.figures,
            "figures_match": report.figures == deck.figures,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/render-stub")
def get_fdd_render_stub(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    try:
        _m, store, spec = load_run_bundle(storage_key, run_id)
    except FileNotFoundError as exc:
        raise _http_not_found("Render bundle artefacts not found", exc) from exc
    report = render_stub(kind="report", spec=spec, store=store)
    deck = render_stub(kind="deck", spec=spec, store=store)
    return {
        "success": True,
        "data": {
            "report": report.model_dump(mode="json"),
            "deck": deck.model_dump(mode="json"),
            "figures_match": report.figures == deck.figures,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/deps")
def get_fdd_deps(
    deal_id: str,
    run_id: str,
    cell_ref_q: str | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    graph = load_dependency_graph(_deal_storage_key(deal), run_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Dependency graph not found")
    payload: dict[str, Any] = {"graph": graph.model_dump(mode="json")}
    if cell_ref_q:
        payload["dependents"] = dependents_of(graph, f"cell:{cell_ref_q}")
    return {"success": True, "data": payload}


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/readiness")
def get_fdd_readiness(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G0 readiness report (cached). POST …/readiness/scan to refresh."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    report = load_readiness(storage_key, run_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Readiness not scanned yet — POST …/readiness/scan",
        )
    requests = load_request_list(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "readiness": report.model_dump(mode="json"),
            "requests": requests.model_dump(mode="json") if requests else None,
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/readiness/scan")
def post_fdd_readiness_scan(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Rescan input inventory and recompute G0 (also seeds scope if missing)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    brief = _deal_brief_fields(deal)
    # Unified with phase2 bootstrap — one scan + scope seed path.
    profile, report, requests = ensure_phase2_artefacts(
        storage_key,
        run_id,
        company=brief["company"],
        description=brief["description"],
        sector=brief["sector"],
    )
    manifest = load_manifest(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "readiness": report.model_dump(mode="json"),
            "requests": requests.model_dump(mode="json"),
            "scope": profile.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/requests")
def get_fdd_requests(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = load_request_list(_deal_storage_key(deal), run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Request list not found")
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.patch("/portfolios/{deal_id}/fdd/runs/{run_id}/requests/{request_id}")
def patch_fdd_request(
    deal_id: str,
    run_id: str,
    request_id: str,
    body: PatchRequestBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update open-item status (pending / requested / received / waived)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    status = (body.status or "").strip().lower()
    if status not in {"pending", "requested", "received", "waived"}:
        raise HTTPException(
            status_code=400,
            detail="status must be pending|requested|received|waived",
        )
    try:
        item = patch_request_status(
            _deal_storage_key(deal),
            run_id,
            request_id,
            status=status,  # type: ignore[arg-type]
        )
    except EvidenceValidationError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"success": True, "data": item.model_dump(mode="json")}


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/evidence/gaps")
def get_fdd_evidence_gaps(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Claim gaps that need VDR / databook evidence (Phase 4 / P3)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    gaps = list_claim_gaps(storage_key, run_id, ensure_claims=True)
    return {
        "success": True,
        "data": {
            "gaps": [g.model_dump(mode="json") for g in gaps],
            "suggested_filenames": suggest_filenames(gaps),
            "count": len(gaps),
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/evidence")
def get_fdd_evidence_pass(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Latest evidence-pass audit record (if any)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = load_evidence_pass(_deal_storage_key(deal), run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Evidence pass not found")
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/evidence/retrieve")
def post_fdd_evidence_retrieve(
    deal_id: str,
    run_id: str,
    body: EvidenceRetrieveBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run P3 evidence pass: claim gaps → databook rescan → bridge → P2 claims."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    payload = body or EvidenceRetrieveBody()
    mode = (payload.mode or "rescan").strip().lower()
    if mode not in {"rescan", "reread", "deep", "rebridge"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be rescan|reread|deep|rebridge",
        )
    try:
        doc = run_p3_evidence_pass(
            storage_key,
            run_id,
            deal=deal,
            db=db,
            mode=mode,  # type: ignore[arg-type]
            filenames=payload.filenames,
            rebridge=payload.rebridge,
            rebuild_claims=payload.rebuild_claims,
            dry_run=payload.dry_run,
            open_requests=payload.open_requests,
        )
    except EvidenceValidationError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    manifest = load_manifest(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "evidence": doc.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
            "gaps_closed": max(
                0, len(doc.gaps_before) - len(doc.gaps_after)
            ),
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/scope")
def get_fdd_scope(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    brief = _deal_brief_fields(deal)
    profile = load_scope_profile(storage_key, run_id) or seed_scope_profile(
        storage_key, run_id, company=brief["company"]
    )
    blockers = validate_scope_for_g1(profile)
    return {
        "success": True,
        "data": {
            "scope": profile.model_dump(mode="json"),
            "g1_ready": not blockers,
            "g1_blockers": blockers,
        },
    }


@router.put("/portfolios/{deal_id}/fdd/runs/{run_id}/scope")
def put_fdd_scope(
    deal_id: str,
    run_id: str,
    body: UpdateScopeBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    raw = body.model_dump(exclude_unset=True)
    allow = bool(raw.pop("allow_edit_approved", False))
    patch = {k: v for k, v in raw.items() if k in _SCOPE_PATCH_KEYS}
    try:
        profile = update_scope_profile(
            storage_key, run_id, patch, allow_edit_approved=allow
        )
    except ScopeValidationError as exc:
        raise _http_scope_error(exc) from exc
    blockers = validate_scope_for_g1(profile)
    return {
        "success": True,
        "data": {
            "scope": profile.model_dump(mode="json"),
            "g1_ready": not blockers,
            "g1_blockers": blockers,
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/phase2")
def post_fdd_phase2(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Seed scope + scan readiness (idempotent Phase 2 bootstrap)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    brief = _deal_brief_fields(deal)
    profile, report, requests = ensure_phase2_artefacts(
        storage_key,
        run_id,
        company=brief["company"],
        description=brief["description"],
        sector=brief["sector"],
    )
    manifest = load_manifest(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "scope": profile.model_dump(mode="json"),
            "readiness": report.model_dump(mode="json"),
            "requests": requests.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/gates")
def get_fdd_gates(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    readiness = load_readiness(storage_key, run_id)
    scope = load_scope_profile(storage_key, run_id)
    approvals = list_approvals(storage_key, run_id)
    g1_appr = load_approval(storage_key, run_id, "G1")
    g4_appr = load_approval(storage_key, run_id, "G4")
    g5_appr = load_approval(storage_key, run_id, "G5")
    g6_appr = load_approval(storage_key, run_id, "G6")
    g7_appr = load_approval(storage_key, run_id, "G7")
    g1_blockers = validate_scope_for_g1(scope) if scope else ["no_scope"]
    qoe = load_qoe_workbook(storage_key, run_id)
    qa = load_qa_pack(storage_key, run_id)
    snapshot = load_snapshot(storage_key, run_id)
    model_checks = load_model_checks(storage_key, run_id)
    g3_held = list(model_checks.held_back_exhibits) if model_checks else []
    return {
        "success": True,
        "data": {
            "G0": {
                "passed": manifest.g0_passed,
                "score": manifest.g0_score,
                "blocked": not manifest.g0_passed,
                "threshold": readiness.threshold if readiness else 0.9,
            },
            "G1": {
                "approved": manifest.g1_approved,
                "ready": bool(scope) and not g1_blockers,
                "blockers": g1_blockers,
                "approval": (
                    g1_appr.model_dump(mode="json") if g1_appr else None
                ),
            },
            "G2": evaluate_g2(storage_key, run_id, manifest=manifest),
            "G3": {
                "passed": manifest.g3_passed,
                "models_built": manifest.models_built,
                "ready": bool(manifest.models_built),
                "blockers": g3_held if not manifest.g3_passed else [],
                "held_back_exhibits": g3_held,
                "packs": (
                    [p.model_dump(mode="json") for p in model_checks.packs]
                    if model_checks
                    else []
                ),
            },
            "G4": {
                "approved": manifest.g4_approved,
                "ready": bool(qoe.g4_ready) if qoe else False,
                "blockers": list(qoe.g4_blockers) if qoe else ["no_qoe"],
                "approval": (
                    g4_appr.model_dump(mode="json") if g4_appr else None
                ),
                "adjusted_ebitda": (
                    qoe.adjusted_ebitda_diligence if qoe else None
                ),
            },
            "G5": {
                "approved": manifest.g5_approved,
                "ready": bool(qa.g5_ready) if qa else False,
                "blockers": list(qa.g5_blockers) if qa else ["no_qa"],
                "open_s1": qa.open_s1_count if qa else None,
                "approval": (
                    g5_appr.model_dump(mode="json") if g5_appr else None
                ),
            },
            "G6": {
                "allowed": g6_allowed(manifest),
                "blocked": manifest.g6_blocked,
                "approved": manifest.g6_approved,
                "ready": bool(qa.g6_ready) if qa else False,
                "blockers": list(qa.g6_blockers) if qa else ["no_qa"],
                "approval": (
                    g6_appr.model_dump(mode="json") if g6_appr else None
                ),
            },
            "G7": {
                "verified": manifest.g7_verified,
                "snapshot_id": manifest.snapshot_id,
                "frozen": snapshot is not None,
                "approval": (
                    g7_appr.model_dump(mode="json") if g7_appr else None
                ),
            },
            "approvals": [a.model_dump(mode="json") for a in approvals],
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/gates/G1/approve")
def post_fdd_g1_approve(
    deal_id: str,
    run_id: str,
    body: ApproveG1Body | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G1 — lead approves scope profile."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    body = body or ApproveG1Body()
    try:
        profile, approval, manifest = approve_g1(
            storage_key,
            run_id,
            decided_by=_actor_id(auth),
            note=body.note,
            require_g0=body.require_g0,
        )
    except FileNotFoundError as exc:
        raise _http_not_found("Scope profile artefact missing", exc) from exc
    except ScopeValidationError as exc:
        raise _http_scope_error(exc) from exc
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G1") from exc
    return {
        "success": True,
        "data": {
            "scope": profile.model_dump(mode="json"),
            "approval": approval.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/gates/G2/acknowledge")
def post_fdd_g2_acknowledge(
    deal_id: str,
    run_id: str,
    body: AcknowledgeG2Body | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G2 — confirm claims reliability (or acknowledge unreliable modules)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    body = body or AcknowledgeG2Body()
    try:
        status, approval, manifest = acknowledge_g2(
            storage_key,
            run_id,
            decided_by=_actor_id(auth),
            note=body.note,
            allow_unreliable=body.allow_unreliable,
        )
    except FileNotFoundError as exc:
        raise _http_not_found("FDD run missing", exc) from exc
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G2") from exc
    return {
        "success": True,
        "data": {
            "g2": status,
            "approval": approval.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/claims")
def get_fdd_claims(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Claims ledger (cached). POST …/claims/build to (re)extract + test."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    ledger = load_claims_ledger(_deal_storage_key(deal), run_id)
    if ledger is None:
        raise HTTPException(
            status_code=404,
            detail="Claims ledger not built yet — POST …/claims/build",
        )
    return {"success": True, "data": ledger.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/claims/build")
def post_fdd_claims_build(
    deal_id: str,
    run_id: str,
    body: BuildClaimsBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Extract agent claims and test financial ones against the databook fact table."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    body = body or BuildClaimsBody()
    agents = tuple(body.agent_keys) if body.agent_keys else None
    ledger = build_claims_ledger(
        storage_key,
        run_id,
        agent_keys=agents,
        open_requests=body.open_requests,
        update_manifest=True,
    )
    manifest = load_manifest(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "claims": ledger.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/claims/reliability")
def get_fdd_claims_reliability(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    ledger = load_claims_ledger(_deal_storage_key(deal), run_id)
    if ledger is None:
        raise HTTPException(status_code=404, detail="Claims ledger not built yet")
    return {
        "success": True,
        "data": {
            "unreliable_modules": list(ledger.unreliable_modules),
            "modules": [m.model_dump(mode="json") for m in ledger.modules],
            "manifest_unreliable": list(manifest.unreliable_modules or []),
            "threshold": 0.5,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/qoe")
def get_fdd_qoe(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """QoE workbook (cached). POST …/qoe/build to (re)generate."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = load_qoe_workbook(_deal_storage_key(deal), run_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="QoE workbook not built yet — POST …/qoe/build",
        )
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/qoe/build")
def post_fdd_qoe_build(
    deal_id: str,
    run_id: str,
    body: BuildQoeBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Build QoE workbook from facts, or seed the PDF §5 worked example."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    body = body or BuildQoeBody()
    doc = build_qoe_workbook(
        storage_key,
        run_id,
        worked_example=body.worked_example,
        update_manifest=True,
    )
    manifest = load_manifest(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "qoe": doc.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/models/build")
def post_fdd_models_build(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Phase 5b — build QoE exhibit (M4) + BS/NWC/net debt exhibits (M8/M5/M6) + G3."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    store, summary = ensure_phase5b_models(
        storage_key,
        run_id,
        company=getattr(deal, "name", None) or deal_id,
        build_qoe=True,
    )
    manifest = load_manifest(storage_key, run_id)
    checks = load_model_checks(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "summary": summary,
            "exhibit_ids": [e.exhibit_id for e in store.exhibits],
            "g3_passed": bool(summary.get("g3_passed")),
            "checks": checks.model_dump(mode="json") if checks else None,
            "manifest": manifest.model_dump(mode="json") if manifest else None,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/models/checks")
def get_fdd_model_checks(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G3 model check packs (auto gate after P4 models)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = load_model_checks(_deal_storage_key(deal), run_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="Model checks not built yet — POST …/models/build",
        )
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.put("/portfolios/{deal_id}/fdd/runs/{run_id}/qoe/register")
def put_fdd_qoe_register(
    deal_id: str,
    run_id: str,
    body: UpdateQoeRegisterBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Upsert QoE register rows; recomputes bridge / walks / checks."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    try:
        doc = update_qoe_register(
            _deal_storage_key(deal),
            run_id,
            body.rows,
            replace=body.replace,
        )
    except QoeValidationError as exc:
        raise _http_qoe_error(exc) from exc
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/qoe/bridge")
def get_fdd_qoe_bridge(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = load_qoe_workbook(_deal_storage_key(deal), run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="QoE workbook not built yet")
    return {
        "success": True,
        "data": {
            "bridge": [b.model_dump(mode="json") for b in doc.bridge],
            "walk": [
                w.model_dump(mode="json") for w in doc.management_to_diligence_walk
            ],
            "adjusted_ebitda_diligence": doc.adjusted_ebitda_diligence,
            "adjusted_ebitda_management": doc.adjusted_ebitda_management,
            "sensitivity_low": doc.sensitivity_low,
            "sensitivity_high": doc.sensitivity_high,
            "pro_forma_ebitda": doc.pro_forma_ebitda,
            "materiality_m": doc.materiality_m,
            "trivial_threshold": doc.trivial_threshold,
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/gates/G4/approve")
def post_fdd_g4_approve(
    deal_id: str,
    run_id: str,
    body: ApproveG4Body | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G4 — lead (and optionally partner) approves QoE judgements."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    body = body or ApproveG4Body()
    try:
        doc, approval, manifest = approve_g4(
            storage_key,
            run_id,
            decided_by=_actor_id(auth),
            note=body.note,
            approve_adjustment_ids=body.approve_adjustment_ids,
            partner_conclusion=body.partner_conclusion,
        )
    except FileNotFoundError as exc:
        raise _http_not_found("QoE workbook artefact missing", exc) from exc
    except QoeValidationError as exc:
        raise _http_qoe_error(exc) from exc
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G4") from exc
    return {
        "success": True,
        "data": {
            "qoe": doc.model_dump(mode="json"),
            "approval": approval.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/commentary")
def get_fdd_commentary(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Section commentary pack (cached). POST …/commentary/build to generate."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = load_commentary(_deal_storage_key(deal), run_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="Commentary not built yet — POST …/commentary/build",
        )
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/commentary/build")
def post_fdd_commentary_build(
    deal_id: str,
    run_id: str,
    body: BuildCommentaryBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Build tagged F/A/M/Q commentary for in-scope sections (Phase 6)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    body = body or BuildCommentaryBody()
    try:
        doc = build_commentary(
            storage_key,
            run_id,
            company=deal.name or deal.slug,
            section_ids=body.section_ids,
            update_manifest=True,
            update_report_spec=body.update_report_spec,
        )
    except CommentaryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    manifest = load_manifest(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "commentary": doc.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/commentary/{section_id}")
def get_fdd_commentary_section(
    deal_id: str,
    run_id: str,
    section_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    draft = get_section(_deal_storage_key(deal), run_id, section_id)
    if draft is None:
        raise HTTPException(
            status_code=404,
            detail=f"Section '{section_id}' not found — build commentary first",
        )
    return {"success": True, "data": draft.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/commentary/validate")
def post_fdd_commentary_validate(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Re-run narrative checks on the persisted commentary pack."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    doc = load_commentary(storage_key, run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Commentary not built yet")
    store = load_exhibit_store(storage_key, run_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Exhibit store not found")
    sections = [validate_section_draft(s, store) for s in doc.sections]
    typed = [
        f"{s.section_id}: {c.message}"
        for s in sections
        for c in s.checks
        if c.check_id == "typed_figures" and not c.passed
    ]
    return {
        "success": True,
        "data": {
            "checks_passed": all(s.checks_passed for s in sections),
            "typed_figure_faults": typed,
            "sections": [s.model_dump(mode="json") for s in sections],
        },
    }


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/gates/G6/check")
def check_fdd_g6(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """IN-3 — G6 is blocked while the run is in draft mode."""
    _deal, manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    try:
        assert_g6_allowed(manifest)
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G6") from exc
    return {
        "success": True,
        "data": {"allowed": True, "run_id": run_id, "gate": "G6"},
    }


# ---------------------------------------------------------------------------
# Phase 8 — QA / G5–G7
# ---------------------------------------------------------------------------


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/qa")
def get_fdd_qa(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """QA pack (cached). POST …/qa/scan to (re)run the catalogue."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = load_qa_pack(_deal_storage_key(deal), run_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="QA pack not built yet — POST …/qa/scan",
        )
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/qa/scan")
def post_fdd_qa_scan(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run Phase 8 check catalogue → issue log; advance stage to P8."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    storage_key = _deal_storage_key(deal)
    doc = build_qa_pack(storage_key, run_id, update_manifest=True)
    manifest = load_manifest(storage_key, run_id)
    return {
        "success": True,
        "data": {
            "qa": doc.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/qa/issues/{issue_id}/resolve")
def post_fdd_qa_resolve_issue(
    deal_id: str,
    run_id: str,
    issue_id: str,
    body: ResolveIssueBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    body = body or ResolveIssueBody()
    try:
        doc = resolve_issue(
            _deal_storage_key(deal),
            run_id,
            issue_id,
            status=body.status,
            resolved_by=_actor_id(auth),
            note=body.note,
        )
    except QaValidationError as exc:
        raise _http_qa_error(exc) from exc
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/qa/challenges")
def post_fdd_qa_challenge(
    deal_id: str,
    run_id: str,
    body: ChallengeBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Raise a partner / reviewer challenge (P9)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    doc = add_challenge(
        _deal_storage_key(deal),
        run_id,
        title=body.title,
        detail=body.detail,
        raised_by=_actor_id(auth),
        linked_issue_ids=body.linked_issue_ids,
    )
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.post(
    "/portfolios/{deal_id}/fdd/runs/{run_id}/qa/challenges/{challenge_id}/respond"
)
def post_fdd_qa_respond_challenge(
    deal_id: str,
    run_id: str,
    challenge_id: str,
    body: RespondChallengeBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    try:
        doc = respond_challenge(
            _deal_storage_key(deal),
            run_id,
            challenge_id,
            status=body.status,
            response=body.response,
            responded_by=_actor_id(auth),
        )
    except QaValidationError as exc:
        raise _http_qa_error(exc) from exc
    return {"success": True, "data": doc.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/gates/G5/approve")
def post_fdd_g5_approve(
    deal_id: str,
    run_id: str,
    body: ApproveGateBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G5 — lead confirms QA catalogue is clear of S1 blockers."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    body = body or ApproveGateBody()
    try:
        doc, approval, manifest = approve_g5(
            _deal_storage_key(deal),
            run_id,
            decided_by=_actor_id(auth),
            note=body.note,
        )
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G5") from exc
    except FileNotFoundError as exc:
        raise _http_not_found("QA artefact missing", exc) from exc
    return {
        "success": True,
        "data": {
            "qa": doc.model_dump(mode="json"),
            "approval": approval.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/gates/G6/approve")
def post_fdd_g6_approve(
    deal_id: str,
    run_id: str,
    body: ApproveGateBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G6 — partner signs off after challenges are cleared (non-draft only)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    body = body or ApproveGateBody()
    try:
        doc, approval, manifest = approve_g6(
            _deal_storage_key(deal),
            run_id,
            decided_by=_actor_id(auth),
            note=body.note,
        )
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G6") from exc
    except FileNotFoundError as exc:
        raise _http_not_found("QA / manifest artefact missing", exc) from exc
    return {
        "success": True,
        "data": {
            "qa": doc.model_dump(mode="json"),
            "approval": approval.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
        },
    }


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/snapshot/freeze")
def post_fdd_snapshot_freeze(
    deal_id: str,
    run_id: str,
    body: FreezeSnapshotBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Freeze artefact hashes for G7 (requires G5)."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    body = body or FreezeSnapshotBody()
    try:
        snap = freeze_snapshot(
            _deal_storage_key(deal),
            run_id,
            frozen_by=_actor_id(auth),
            note=body.note,
        )
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G5") from exc
    except QaValidationError as exc:
        raise _http_qa_error(exc) from exc
    return {"success": True, "data": snap.model_dump(mode="json")}


@router.get("/portfolios/{deal_id}/fdd/runs/{run_id}/snapshot")
def get_fdd_snapshot(
    deal_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    snap = load_snapshot(_deal_storage_key(deal), run_id)
    if snap is None:
        raise HTTPException(
            status_code=404,
            detail="No frozen snapshot — POST …/snapshot/freeze",
        )
    return {"success": True, "data": snap.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/fdd/runs/{run_id}/gates/G7/verify")
def post_fdd_g7_verify(
    deal_id: str,
    run_id: str,
    body: ApproveGateBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """G7 — verify current artefact hashes match the frozen snapshot."""
    deal, _manifest = _get_deal_and_manifest(db, deal_id, run_id, auth)
    body = body or ApproveGateBody()
    try:
        snap, approval, manifest = verify_g7(
            _deal_storage_key(deal),
            run_id,
            decided_by=_actor_id(auth),
            note=body.note,
        )
    except GateBlockedError as exc:
        raise _http_gate_blocked(exc, gate="G7") from exc
    except FileNotFoundError as exc:
        raise _http_not_found("Snapshot / manifest missing", exc) from exc
    return {
        "success": True,
        "data": {
            "snapshot": snap.model_dump(mode="json"),
            "approval": approval.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
        },
    }
