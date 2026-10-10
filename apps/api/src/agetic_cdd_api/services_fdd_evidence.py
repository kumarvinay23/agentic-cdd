"""FDD Phase 4 — evidence retrieval (run stage P3).

Gap list from failed financial claims → targeted databook rescan / VDR reread
→ new release only → bridge → rebuild claims (re-enter P2). Never patch
exhibits from VDR directly (R3 / D4).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from agetic_cdd_api.fdd_schemas import (
    ClaimGap,
    ClaimsLedgerDoc,
    EvidencePassDoc,
    RequestListDoc,
    RequestListItem,
    RunStage,
)
from agetic_cdd_api.services_databook import (
    deep_databook,
    rescan_databook,
    reread_databook_document,
)
from agetic_cdd_api.services_databook_store import load_current_release
from agetic_cdd_api.services_fdd_bridge import bridge_release_into_run
from agetic_cdd_api.services_fdd_claims import (
    _filenames_from_claim,
    build_claims_ledger,
    ensure_phase3_claims,
)
from agetic_cdd_api.services_fdd_store import (
    load_claims_ledger,
    load_manifest,
    load_request_list,
    save_evidence_pass,
    save_manifest,
    save_request_list,
)
from agetic_cdd_api.services_databook_release import SlugDeal

logger = logging.getLogger(__name__)

EVIDENCE_VERSION = "0.1.0"
EvidenceMode = Literal["rescan", "reread", "deep", "rebridge"]
_FAILED_FINANCIAL = frozenset({"contradicted", "unverifiable"})


class EvidenceValidationError(ValueError):
    """Invalid evidence-pass request."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _norm_metric(key: str | None) -> str:
    """Normalize metric keys for reconcile matching (case / spacing)."""
    return " ".join((key or "").strip().lower().replace("-", "_").split())


def list_claim_gaps(
    deal_slug: str,
    run_id: str,
    *,
    ledger: ClaimsLedgerDoc | None = None,
    ensure_claims: bool = True,
) -> list[ClaimGap]:
    """Failed financial claims that need VDR / databook evidence."""
    doc = ledger
    if doc is None:
        if ensure_claims:
            doc = ensure_phase3_claims(deal_slug, run_id)
        else:
            doc = load_claims_ledger(deal_slug, run_id)
    if doc is None:
        return []

    requests = load_request_list(deal_slug, run_id)
    # Index only items that can attach to a claim id (avoid full-scan per gap).
    req_by_claim = {
        i.claim_id: i
        for i in (requests.items if requests else [])
        if i.claim_id
    }

    gaps: list[ClaimGap] = []
    for claim in doc.claims:
        if claim.kind != "financial" or claim.test_result not in _FAILED_FINANCIAL:
            continue
        suggested = _filenames_from_claim(claim)
        req = req_by_claim.get(claim.claim_id)
        if req and req.suggested_filenames:
            seen = {n.lower() for n in suggested}
            for name in req.suggested_filenames:
                if name.lower() not in seen:
                    suggested.append(name)
                    seen.add(name.lower())
        gaps.append(
            ClaimGap(
                claim_id=claim.claim_id,
                source_agent=claim.source_agent,
                metric_key=claim.metric_key,
                fiscal_year=claim.fiscal_year,
                claimed_value=claim.claimed_value,
                databook_value=claim.databook_value,
                test_result=claim.test_result,  # type: ignore[arg-type]
                text=claim.text or "",
                suggested_filenames=suggested,
                request_id=req.request_id if req else None,
            )
        )
    return gaps


def suggest_filenames(gaps: list[ClaimGap]) -> list[str]:
    """Deduped VDR filenames hinted by gap citations."""
    out: list[str] = []
    seen: set[str] = set()
    for gap in gaps:
        for name in gap.suggested_filenames:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
    return out


def reconcile_requests_after_claims(
    deal_slug: str,
    run_id: str,
    *,
    ledger: ClaimsLedgerDoc | None = None,
) -> list[str]:
    """Mark pending claim-gap requests ``received`` when the claim now agrees."""
    doc = ledger or load_claims_ledger(deal_slug, run_id)
    req = load_request_list(deal_slug, run_id)
    if doc is None or req is None:
        return []

    agrees = {
        c.claim_id
        for c in doc.claims
        if c.kind == "financial" and c.test_result == "agrees" and c.claim_id
    }
    # Also match by normalized metric×year when claim_id was not stamped.
    agrees_keys = {
        (_norm_metric(c.metric_key), int(c.fiscal_year))
        for c in doc.claims
        if c.kind == "financial"
        and c.test_result == "agrees"
        and c.metric_key
        and c.fiscal_year is not None
    }

    received: list[str] = []
    updated: list[RequestListItem] = []
    changed = False
    for item in req.items:
        if item.status in {"received", "waived"}:
            updated.append(item)
            continue
        hit = False
        if item.claim_id and item.claim_id in agrees:
            hit = True
        elif item.metric_key and item.fiscal_year is not None:
            key = (_norm_metric(item.metric_key), int(item.fiscal_year))
            if key in agrees_keys:
                hit = True
        if hit:
            updated.append(item.model_copy(update={"status": "received"}))
            received.append(item.request_id)
            changed = True
        else:
            updated.append(item)

    if changed:
        save_request_list(
            RequestListDoc(
                run_id=run_id,
                deal_slug=deal_slug,
                updated_at=_now(),
                items=updated,
            )
        )
    return received


def patch_request_status(
    deal_slug: str,
    run_id: str,
    request_id: str,
    *,
    status: Literal["pending", "requested", "received", "waived"],
) -> RequestListItem:
    """Update one open-item status (owner workflow)."""
    req = load_request_list(deal_slug, run_id)
    if req is None:
        raise EvidenceValidationError("Request list not found")
    found: RequestListItem | None = None
    items: list[RequestListItem] = []
    for item in req.items:
        if item.request_id == request_id:
            found = item.model_copy(update={"status": status})
            items.append(found)
        else:
            items.append(item)
    if found is None:
        raise EvidenceValidationError(f"Request {request_id!r} not found")
    save_request_list(
        RequestListDoc(
            run_id=run_id,
            deal_slug=deal_slug,
            updated_at=_now(),
            items=items,
        )
    )
    return found


def _stamp_stage_p3(deal_slug: str, run_id: str) -> None:
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise EvidenceValidationError(f"Missing FDD manifest {deal_slug}/{run_id}")
    save_manifest(
        manifest.model_copy(
            update={
                "stage": RunStage.P3,
                "model_versions": {
                    **dict(manifest.model_versions or {}),
                    "fdd_phase4": EVIDENCE_VERSION,
                },
            }
        )
    )


def _run_databook_job(
    *,
    deal: Any,
    db: Any | None,
    mode: EvidenceMode,
    filenames: list[str],
) -> Any | None:
    """Invoke existing databook rescan / reread / deep entry points.

    Reread mode continues past per-file failures and returns the last successful
    summary (or a list of successes when more than one file lands).
    """
    if mode == "rebridge":
        return None
    if mode == "deep":
        if db is None:
            raise EvidenceValidationError("deep mode requires a DB session")
        return deep_databook(db, deal)
    if mode == "reread":
        if not filenames:
            raise EvidenceValidationError(
                "reread mode requires filenames (or use rescan)"
            )
        if db is None:
            raise EvidenceValidationError("reread mode requires a DB session")
        summaries: list[Any] = []
        errors: list[str] = []
        for name in filenames:
            try:
                summaries.append(reread_databook_document(db, deal, name))
            except Exception as err:
                logger.error(
                    "Failed to reread document %s: %s", name, err, exc_info=True
                )
                errors.append(f"{name}:{err}")
        if not summaries:
            raise EvidenceValidationError(
                "reread failed for all filenames: " + "; ".join(errors[:5])
            )
        if errors:
            # Attach partial-failure signal for callers via attribute when possible.
            last = summaries[-1]
            try:
                setattr(last, "_reread_errors", errors)
            except Exception:
                pass
            logger.warning(
                "Partial reread: %s ok, %s failed", len(summaries), len(errors)
            )
        return summaries[-1] if len(summaries) == 1 else summaries
    # default: library rescan (+ auto-release)
    return rescan_databook(deal)


def run_p3_evidence_pass(
    deal_slug: str,
    run_id: str,
    *,
    deal: Any | None = None,
    db: Any | None = None,
    mode: EvidenceMode = "rescan",
    filenames: list[str] | None = None,
    rebridge: bool = True,
    rebuild_claims: bool = True,
    dry_run: bool = False,
    open_requests: bool = True,
) -> EvidencePassDoc:
    """Gap list → databook job → new release → bridge → P2 claims refresh.

    *mode*:
    - ``rescan`` — re-extract from CDL library (auto-release)
    - ``reread`` — re-ingest listed VDR files then rescan
    - ``deep`` — re-ingest all VDR originals then rescan
    - ``rebridge`` — skip extract; pull current release into the run only

    Manifest stage is stamped to P3 only after a successful databook path
    (or intentional rebridge), never before a failing job.
    """
    if mode not in {"rescan", "reread", "deep", "rebridge"}:
        raise EvidenceValidationError(f"Unknown evidence mode: {mode!r}")

    gaps_before = list_claim_gaps(deal_slug, run_id, ensure_claims=True)
    suggested = suggest_filenames(gaps_before)
    names = list(filenames) if filenames else list(suggested)

    # Explicit filenames + rescan + db → targeted reread (VDR file then rescan).
    effective_mode: EvidenceMode = mode
    if mode == "rescan" and filenames and db is not None:
        effective_mode = "reread"
    if effective_mode == "reread" and not names and suggested:
        names = list(suggested)

    deal_obj = deal or SlugDeal(id=deal_slug, slug=deal_slug)
    release_before = load_current_release(deal_obj)
    release_id_before = release_before.release_id if release_before else None

    notes: list[str] = [
        f"gaps_before={len(gaps_before)}",
        f"suggested_files={len(suggested)}",
    ]
    if dry_run:
        doc = EvidencePassDoc(
            run_id=run_id,
            deal_slug=deal_slug,
            updated_at=_now(),
            version=EVIDENCE_VERSION,
            mode=effective_mode,
            dry_run=True,
            filenames=names,
            gaps_before=gaps_before,
            gaps_after=gaps_before,
            release_id_before=release_id_before,
            release_id_after=release_id_before,
            notes=[*notes, "dry_run — no databook mutation"],
        )
        return save_evidence_pass(doc)

    job_error: str | None = None
    summary: Any | None = None
    try:
        summary = _run_databook_job(
            deal=deal_obj,
            db=db,
            mode=effective_mode,
            filenames=names,
        )
        if effective_mode == "rebridge":
            notes.append("databook_job=rebridge")
        elif summary is not None:
            n_ok = len(summary) if isinstance(summary, list) else 1
            notes.append(f"databook_job={effective_mode} ok={n_ok}")
            probe = summary[-1] if isinstance(summary, list) else summary
            reread_errs = getattr(probe, "_reread_errors", None)
            if reread_errs:
                notes.append(f"reread_partial_errors={len(reread_errs)}")
    except Exception as err:
        logger.exception(
            "P3 databook job failed for %s/%s mode=%s",
            deal_slug,
            run_id,
            effective_mode,
        )
        job_error = str(err)
        notes.append(f"databook_job_error:{err}")
        summary = None

    release_after = load_current_release(deal_obj)
    release_id_after = release_after.release_id if release_after else None
    release_ver_after = release_after.version if release_after else None
    release_changed = bool(
        release_id_after and release_id_after != release_id_before
    )
    if release_changed:
        notes.append(f"new_release:{release_id_after}")
    elif effective_mode != "rebridge":
        notes.append("release_unchanged")

    # Failed extract + identical release → do not stamp P3 or re-bridge the
    # same dataset (avoids redundant passes and stuck P3 manifests).
    job_failed_stale = (
        effective_mode != "rebridge"
        and job_error is not None
        and not release_changed
    )

    claims_rebuilt = False
    gaps_after = list(gaps_before)
    received: list[str] = []
    do_bridge = rebridge
    do_claims = rebuild_claims

    if job_failed_stale:
        notes.append("short_circuit_stale_release — skip bridge/claims")
        do_bridge = False
        do_claims = False
    else:
        # Stamp P3 only after a usable databook outcome (or intentional rebridge).
        _stamp_stage_p3(deal_slug, run_id)

    if do_bridge:
        bridge_release_into_run(
            deal_slug,
            run_id,
            release=release_after,
            release_id=release_id_after,
            bootstrap=release_after is None,
            allow_pinned_release=True,
        )
        notes.append("bridged")

    if do_claims:
        ledger = build_claims_ledger(
            deal_slug, run_id, open_requests=open_requests
        )
        claims_rebuilt = True
        gaps_after = list_claim_gaps(
            deal_slug, run_id, ledger=ledger, ensure_claims=False
        )
        received = reconcile_requests_after_claims(
            deal_slug, run_id, ledger=ledger
        )
        notes.append(
            f"claims_rebuilt agrees={ledger.agrees} "
            f"contradicted={ledger.contradicted} unverifiable={ledger.unverifiable}"
        )
        if received:
            notes.append(f"requests_received={len(received)}")

    # Persist phase4 version even on short-circuit so operators can see the attempt.
    if job_failed_stale:
        manifest = load_manifest(deal_slug, run_id)
        if manifest is not None:
            save_manifest(
                manifest.model_copy(
                    update={
                        "model_versions": {
                            **dict(manifest.model_versions or {}),
                            "fdd_phase4": EVIDENCE_VERSION,
                        },
                    }
                )
            )

    doc = EvidencePassDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        version=EVIDENCE_VERSION,
        mode=effective_mode,
        dry_run=False,
        filenames=names,
        gaps_before=gaps_before,
        gaps_after=gaps_after,
        release_id_before=release_id_before,
        release_id_after=release_id_after,
        release_version_after=release_ver_after,
        requests_received=received,
        claims_rebuilt=claims_rebuilt,
        notes=notes,
    )
    return save_evidence_pass(doc)
