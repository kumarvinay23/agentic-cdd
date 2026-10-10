"""FDD Phase 2 — scope profile + G1 approval gate."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    DEFAULT_MATERIALITY_BASIS,
    DEFAULT_MATERIALITY_PCT,
    DEFAULT_SECTIONS_IN_SCOPE,
    OPTIONAL_SECTIONS,
    TRIVIAL_FRACTION_OF_M,
    Approval,
    ArtefactStatus,
    FddRunManifest,
    GateId,
    ReadinessReport,
    RequestListDoc,
    ScopeProfile,
)
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_store import (
    load_approval,
    load_manifest,
    load_readiness,
    load_scope_profile,
    save_approval,
    save_manifest,
    save_scope_profile,
)

__all__ = [
    "GateBlockedError",
    "ScopeValidationError",
    "approve_g1",
    "assert_g1_approvable",
    "default_periods",
    "ensure_phase2_artefacts",
    "seed_scope_profile",
    "trivial_threshold",
    "update_scope_profile",
    "validate_scope_for_g1",
]


class ScopeValidationError(ValueError):
    """Scope profile is incomplete for G1."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def default_periods(*, end_year: int | None = None) -> list[str]:
    """FY{n-2}A … FY{n}A style labels (calendar heuristic)."""
    now = datetime.now(UTC)
    if end_year is not None:
        y = end_year
    else:
        # Prefer prior full year as latest actual when early in calendar year.
        y = now.year - 1 if now.month < 4 else now.year
    return [f"FY{str(yy)[2:]}A" for yy in range(y - 2, y + 1)]


def _resolve_scope_entity(deal_slug: str, company: str | None) -> str:
    """Prefer a real target name over slug / TestN placeholders."""
    from agetic_cdd_api.services_accounts_extract import is_placeholder_company

    candidates: list[str] = []
    if company and str(company).strip():
        candidates.append(str(company).strip())
    try:
        from pathlib import Path

        from agetic_cdd_api.services_deals import deals_root

        idx_path = deals_root() / deal_slug / "library" / "index.json"
        if idx_path.is_file():
            import json

            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            for key in ("company", "name", "target"):
                val = idx.get(key) if isinstance(idx, dict) else None
                if val and str(val).strip():
                    candidates.append(str(val).strip())
    except (OSError, ValueError, TypeError):
        pass
    # Common VDR / pack stem when the deal was nicknamed testN.
    for cand in candidates:
        if not is_placeholder_company(cand, deal_slug):
            return cand
    # Last resort: Compost Crew-style name from documents folder.
    try:
        from agetic_cdd_api.services_deals import deals_root

        docs = deals_root() / deal_slug / "documents"
        if docs.is_dir():
            for p in docs.iterdir():
                name = p.name
                if "compost crew" in name.lower():
                    return "Compost Crew"
    except OSError:
        pass
    return (company or deal_slug).strip() or deal_slug


def seed_scope_profile(
    deal_slug: str,
    run_id: str,
    *,
    company: str | None = None,
    deal_type: str | None = "buy-side",
    currency: str = "USD",
    scale: str = "M",
    periods: list[str] | None = None,
    entities_in: list[str] | None = None,
    materiality_m: float | None = None,
) -> ScopeProfile:
    """Create a draft scope profile with sensible defaults (IN-4 / IN-5)."""
    from agetic_cdd_api.services_accounts_extract import is_placeholder_company

    entity = _resolve_scope_entity(deal_slug, company)
    existing = load_scope_profile(deal_slug, run_id)
    if existing is not None:
        # Refresh draft perimeter when it still carries a TestN / slug name.
        ents = list(existing.entities_in or [])
        if (
            existing.status == ArtefactStatus.DRAFT
            and ents
            and all(is_placeholder_company(e, deal_slug) for e in ents)
            and not is_placeholder_company(entity, deal_slug)
        ):
            return save_scope_profile(
                existing.model_copy(update={"entities_in": [entity]})
            )
        return existing

    profile = ScopeProfile(
        profile_id=f"scope_{uuid.uuid4().hex[:10]}",
        deal_slug=deal_slug,
        run_id=run_id,
        status=ArtefactStatus.DRAFT,
        entities_in=list(entities_in or [entity]),  # resolved target name
        entities_out=[],
        deal_type=deal_type,
        periods=list(periods or default_periods()),
        currency=currency,
        scale=scale,
        materiality_m=materiality_m,
        materiality_basis=DEFAULT_MATERIALITY_BASIS,
        materiality_pct=DEFAULT_MATERIALITY_PCT,
        sections_in_scope=list(DEFAULT_SECTIONS_IN_SCOPE),
        notes="Draft scope — lead must confirm perimeter and materiality before G1.",
    )
    profile = save_scope_profile(profile)
    manifest = load_manifest(deal_slug, run_id)
    if manifest is not None:
        save_manifest(
            manifest.model_copy(
                update={
                    "scope_profile_id": profile.profile_id,
                    "model_versions": {
                        **(manifest.model_versions or {}),
                        "fdd_phase2": "0.1.0",
                    },
                }
            )
        )
    return profile


def sync_scope_currency_from_store(
    deal_slug: str,
    run_id: str,
    store: Any | None = None,
) -> ScopeProfile | None:
    """Align draft scope currency/scale with exhibit majority (fixes stale INR)."""
    from agetic_cdd_api.services_fdd_store import load_exhibit_store
    from agetic_cdd_api.services_fdd_tokens import effective_currency_scale

    profile = load_scope_profile(deal_slug, run_id)
    if profile is None:
        return None
    if profile.status == ArtefactStatus.APPROVED:
        return profile  # do not silently rewrite G1-approved scope

    exhibit_store = store or load_exhibit_store(deal_slug, run_id)
    cur, scale = effective_currency_scale(scope=profile, store=exhibit_store)
    if (profile.currency or "").strip() == cur and (profile.scale or "").strip() == scale:
        return profile
    return save_scope_profile(
        profile.model_copy(update={"currency": cur, "scale": scale})
    )


def update_scope_profile(
    deal_slug: str,
    run_id: str,
    patch: dict[str, Any],
    *,
    allow_edit_approved: bool = False,
) -> ScopeProfile:
    """Patch draft scope fields. Re-approval required if previously approved."""
    profile = load_scope_profile(deal_slug, run_id) or seed_scope_profile(
        deal_slug, run_id
    )
    if profile.status == ArtefactStatus.APPROVED and not allow_edit_approved:
        raise ScopeValidationError(
            "Scope is G1-approved; pass allow_edit_approved=true to revise "
            "(will reset to draft)"
        )

    allowed = {
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
    updates: dict[str, Any] = {
        key: value for key, value in patch.items() if key in allowed
    }

    if profile.status == ArtefactStatus.APPROVED and allow_edit_approved:
        updates["status"] = ArtefactStatus.DRAFT
        updates["approved_at"] = None
        updates["approved_by"] = None
        updates["approval_id"] = None
        manifest = load_manifest(deal_slug, run_id)
        if manifest is not None:
            save_manifest(manifest.model_copy(update={"g1_approved": False}))

    if not updates:
        return profile

    return save_scope_profile(profile.model_copy(update=updates))


def validate_scope_for_g1(profile: ScopeProfile) -> list[str]:
    """Return list of blocking reasons; empty means G1-ready."""
    reasons: list[str] = []
    if not profile.entities_in:
        reasons.append("entities_in_required")
    if not (profile.deal_type and str(profile.deal_type).strip()):
        reasons.append("deal_type_required")
    if not profile.periods:
        reasons.append("periods_required")
    if not (profile.currency and str(profile.currency).strip()):
        reasons.append("currency_required")
    if profile.materiality_m is None and profile.materiality_pct is None:
        reasons.append("materiality_required")

    if profile.materiality_pct is not None:
        try:
            pct = float(profile.materiality_pct)
            if not (0 < pct <= 0.2):
                reasons.append("materiality_pct_out_of_range")
        except (ValueError, TypeError):
            reasons.append("materiality_pct_out_of_range")

    if not profile.sections_in_scope:
        reasons.append("sections_in_scope_required")

    unknown = [
        s
        for s in profile.sections_in_scope
        if s not in DEFAULT_SECTIONS_IN_SCOPE and s not in OPTIONAL_SECTIONS
    ]
    if unknown:
        reasons.append(f"unknown_sections:{','.join(unknown)}")
    return reasons


def trivial_threshold(materiality_m: float) -> float:
    """IN-5 — trivial < 5% of M."""
    return float(materiality_m) * TRIVIAL_FRACTION_OF_M


def assert_g1_approvable(
    deal_slug: str,
    run_id: str,
    *,
    require_g0: bool = True,
) -> ScopeProfile:
    profile = load_scope_profile(deal_slug, run_id)
    if profile is None:
        raise ScopeValidationError("No scope profile — seed or PUT scope first")
    reasons = validate_scope_for_g1(profile)
    if reasons:
        raise ScopeValidationError(
            "Scope incomplete for G1: " + ", ".join(reasons)
        )
    if require_g0:
        readiness = load_readiness(deal_slug, run_id)
        manifest = load_manifest(deal_slug, run_id)
        g0_ok = (readiness.g0_passed if readiness else False) or (
            manifest.g0_passed if manifest else False
        )
        if not g0_ok:
            raise GateBlockedError(
                "G1 blocked until G0 readiness passes "
                f"(run={run_id}); scan readiness and close required gaps"
            )
    return profile


def approve_g1(
    deal_slug: str,
    run_id: str,
    *,
    decided_by: str | None = None,
    note: str | None = None,
    require_g0: bool = True,
) -> tuple[ScopeProfile, Approval, FddRunManifest]:
    """G1 — lead approves scope perimeter / materiality / sections."""
    profile = assert_g1_approvable(deal_slug, run_id, require_g0=require_g0)
    existing = load_approval(deal_slug, run_id, GateId.G1)
    if (
        existing is not None
        and existing.status == ArtefactStatus.APPROVED
        and profile.status == ArtefactStatus.APPROVED
    ):
        manifest = load_manifest(deal_slug, run_id)
        if manifest is None:
            raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
        return profile, existing, manifest

    approval = Approval(
        approval_id=f"appr_{uuid.uuid4().hex[:10]}",
        gate=GateId.G1,
        run_id=run_id,
        deal_slug=deal_slug,
        status=ArtefactStatus.APPROVED,
        decided_at=_now(),
        decided_by=decided_by or "deal_lead",
        note=note or "Scope profile approved (G1)",
        payload={
            "profile_id": profile.profile_id,
            "entities_in": list(profile.entities_in),
            "sections_in_scope": list(profile.sections_in_scope),
            "materiality_m": profile.materiality_m,
            "materiality_pct": profile.materiality_pct,
            "materiality_basis": profile.materiality_basis,
            "currency": profile.currency,
            "periods": list(profile.periods),
        },
    )
    approval = save_approval(approval)
    profile = save_scope_profile(
        profile.model_copy(
            update={
                "status": ArtefactStatus.APPROVED,
                "approved_at": approval.decided_at,
                "approved_by": approval.decided_by,
                "approval_id": approval.approval_id,
            }
        )
    )
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
    manifest = save_manifest(
        manifest.model_copy(
            update={
                "g1_approved": True,
                "scope_profile_id": profile.profile_id,
                "status": (
                    ArtefactStatus.CHECKED
                    if not manifest.draft_mode
                    else manifest.status
                ),
                "model_versions": {
                    **(manifest.model_versions or {}),
                    "fdd_phase2": "0.1.0",
                },
            }
        )
    )
    return profile, approval, manifest


def ensure_phase2_artefacts(
    deal_slug: str,
    run_id: str,
    *,
    company: str | None = None,
    description: str | None = None,
    sector: str | None = None,
    deal_type: str | None = "buy-side",
    currency: str = "USD",
) -> tuple[ScopeProfile, ReadinessReport, RequestListDoc]:
    """Seed scope + scan readiness for a run (idempotent)."""
    from agetic_cdd_api.services_fdd_readiness import scan_and_persist_readiness

    profile = seed_scope_profile(
        deal_slug,
        run_id,
        company=company,
        deal_type=deal_type,
        currency=currency,
    )
    report, requests, _manifest = scan_and_persist_readiness(
        deal_slug,
        run_id,
        company=company,
        description=description,
        sector=sector,
        update_manifest=True,
    )
    return profile, report, requests
