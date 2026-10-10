"""Phase 6 — post-run validation pack (OL-1, OL-2, OL-4).

Builds review cards from the current released databook: all doubtful / missing /
conflict cells, plus a calibration sample of proven cells. G4 renders page crops
onto cards when ``source_ref.page`` is known (AC-5 / S1-8 / OL-2).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Literal

from agetic_cdd_api.services_databook_crops import ensure_crop
from agetic_cdd_api.services_databook_models import (
    DealLike,
    ReleaseCellStatus,
    ReleasedCell,
    ValidationCard,
    ValidationCardKind,
    ValidationPack,
)
from agetic_cdd_api.services_databook_store import (
    load_current_release,
    load_page_register,
    update_meta,
)
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

_DEFAULT_CALIBRATION = 5
_MAX_CALIBRATION = 12


def _deal_slug(deal: DealLike) -> str:
    return str(getattr(deal, "slug", None) or getattr(deal, "id", "") or "")


def _card_id(kind: str, metric_key: str, fiscal_year: int, row_id: str | None) -> str:
    raw = f"{kind}|{metric_key}|{fiscal_year}|{row_id or ''}"
    return "vc_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _dependents(
    cell: ReleasedCell,
    by_year: dict[int, list[ReleasedCell]],
) -> list[str]:
    """Other material metrics in the same fiscal year (simple dependents graph)."""
    peers = by_year.get(cell.fiscal_year) or []
    out: list[str] = []
    for peer in peers:
        if peer.metric_key == cell.metric_key:
            continue
        if peer.metric_key not in out:
            out.append(peer.metric_key)
        if len(out) >= 6:
            break
    return out


def _kind_for_cell(cell: ReleasedCell) -> ValidationCardKind:
    if cell.status == ReleaseCellStatus.MISSING:
        return ValidationCardKind.MISSING
    if cell.alternatives:
        return ValidationCardKind.CONFLICT
    if cell.status == ReleaseCellStatus.DOUBTFUL:
        return ValidationCardKind.DOUBTFUL
    return ValidationCardKind.CALIBRATION


def _cell_to_card(
    cell: ReleasedCell,
    *,
    kind: ValidationCardKind,
    release_id: str | None,
    release_version: int | None,
    dependents: list[str],
    deal: DealLike | None = None,
    page_register: Any | None = None,
    render_crops: bool = True,
) -> ValidationCard:
    crop_status: Literal["available", "unavailable", "pending"] = "unavailable"
    crop_ref: str | None = None
    crop_reason: str | None = None
    source_ref = cell.source_ref

    if render_crops and deal is not None and source_ref is not None and source_ref.page is not None:
        caption = (cell.captions or [None])[0]
        result = ensure_crop(
            deal,
            source_ref,
            page_register=page_register,
            caption=caption,
            value=cell.value,
        )
        crop_ref = result.crop_ref
        crop_status = result.crop_status
        crop_reason = result.reason
        if result.source_ref is not None:
            source_ref = result.source_ref
    elif source_ref is not None and source_ref.page is not None:
        crop_status = "pending"
    elif cell.status == ReleaseCellStatus.MISSING:
        crop_status = "unavailable"
        crop_reason = "missing cell — no source page"

    return ValidationCard(
        card_id=_card_id(kind.value, cell.metric_key, cell.fiscal_year, cell.row_id),
        kind=kind,
        metric_key=cell.metric_key,
        fiscal_year=cell.fiscal_year,
        status=cell.status,
        value=cell.value,
        unit=cell.unit,
        currency=cell.currency,
        scale=cell.scale,
        row_id=cell.row_id,
        sources=list(cell.sources or []),
        captions=list(cell.captions or []),
        reason=cell.reason,
        alternatives=list(cell.alternatives or []),
        scope=cell.scope,
        statement=cell.statement,
        period_end=cell.period_end,
        period_length=cell.period_length,
        source_basis=cell.source_basis,
        source_ref=source_ref,
        proof_level=cell.proof_level,
        proof_checks=list(cell.proof_checks or []),
        dependents=dependents,
        release_id=release_id,
        release_version=release_version,
        crop_ref=crop_ref,
        crop_status=crop_status,
        crop_reason=crop_reason,
        request_id=cell.request_id,
        document_request=cell.document_request,
    )


def select_calibration_sample(
    proven: list[ReleasedCell],
    *,
    limit: int = _DEFAULT_CALIBRATION,
) -> list[ReleasedCell]:
    """Deterministic sample of proven cells for calibration (OL-4).

    Prefers diversity across metric keys, then higher fiscal years.
    """
    if not proven or limit <= 0:
        return []
    limit = min(limit, _MAX_CALIBRATION, len(proven))
    # Sort: unique metrics first by walking sorted keys
    by_metric: dict[str, list[ReleasedCell]] = {}
    for cell in proven:
        by_metric.setdefault(cell.metric_key, []).append(cell)
    for cells in by_metric.values():
        cells.sort(key=lambda c: c.fiscal_year, reverse=True)

    picked: list[ReleasedCell] = []
    # Round-robin across metrics for diversity
    metric_keys = sorted(by_metric.keys())
    idx = {k: 0 for k in metric_keys}
    while len(picked) < limit:
        progressed = False
        for key in metric_keys:
            cells = by_metric[key]
            i = idx[key]
            if i >= len(cells):
                continue
            picked.append(cells[i])
            idx[key] = i + 1
            progressed = True
            if len(picked) >= limit:
                break
        if not progressed:
            break
    return picked


def build_validation_pack(
    deal: DealLike,
    *,
    calibration_limit: int = _DEFAULT_CALIBRATION,
    persist_timestamp: bool = True,
    render_crops: bool = True,
) -> ValidationPack:
    """Assemble the post-run validation pack from the current release."""
    slug = _deal_slug(deal)
    release = load_current_release(deal)
    now = utc_now_iso()
    if release is None:
        return ValidationPack(
            deal_slug=slug,
            generated_at=now,
            cards=[],
            counts={"doubtful": 0, "conflict": 0, "missing": 0, "calibration": 0, "total": 0},
            ready_for_review=False,
        )

    page_register = None
    if render_crops:
        try:
            page_register = load_page_register(deal)
        except Exception:  # noqa: BLE001
            page_register = None

    cells = list(release.cells or [])
    by_year: dict[int, list[ReleasedCell]] = {}
    for cell in cells:
        by_year.setdefault(cell.fiscal_year, []).append(cell)

    review_cells = [
        c
        for c in cells
        if c.status in {ReleaseCellStatus.DOUBTFUL, ReleaseCellStatus.MISSING}
        or (c.status == ReleaseCellStatus.PROVEN and c.alternatives)
    ]
    proven = [c for c in cells if c.status == ReleaseCellStatus.PROVEN and not c.alternatives]
    calibration = select_calibration_sample(proven, limit=calibration_limit)

    cards: list[ValidationCard] = []
    for cell in review_cells:
        kind = _kind_for_cell(cell)
        cards.append(
            _cell_to_card(
                cell,
                kind=kind,
                release_id=release.release_id,
                release_version=release.version,
                dependents=_dependents(cell, by_year),
                deal=deal,
                page_register=page_register,
                render_crops=render_crops,
            )
        )
    for cell in calibration:
        cards.append(
            _cell_to_card(
                cell,
                kind=ValidationCardKind.CALIBRATION,
                release_id=release.release_id,
                release_version=release.version,
                dependents=_dependents(cell, by_year),
                deal=deal,
                page_register=page_register,
                render_crops=render_crops,
            )
        )

    # Stable order: conflict → doubtful → missing → calibration, then metric, year
    kind_rank = {
        ValidationCardKind.CONFLICT: 0,
        ValidationCardKind.DOUBTFUL: 1,
        ValidationCardKind.MISSING: 2,
        ValidationCardKind.CALIBRATION: 3,
    }
    cards.sort(
        key=lambda c: (kind_rank.get(c.kind, 9), c.metric_key, c.fiscal_year, c.card_id)
    )

    counts = {
        "doubtful": sum(1 for c in cards if c.kind == ValidationCardKind.DOUBTFUL),
        "conflict": sum(1 for c in cards if c.kind == ValidationCardKind.CONFLICT),
        "missing": sum(1 for c in cards if c.kind == ValidationCardKind.MISSING),
        "calibration": sum(1 for c in cards if c.kind == ValidationCardKind.CALIBRATION),
        "total": len(cards),
        "crops_available": sum(1 for c in cards if c.crop_status == "available"),
        "crops_pending": sum(1 for c in cards if c.crop_status == "pending"),
        "crops_unavailable": sum(1 for c in cards if c.crop_status == "unavailable"),
    }
    pack = ValidationPack(
        deal_slug=slug,
        release_id=release.release_id,
        release_version=release.version,
        generated_at=now,
        cards=cards,
        counts=counts,
        ready_for_review=True,
    )
    if persist_timestamp:
        try:
            update_meta(
                deal,
                lambda meta: meta.model_copy(update={"last_validation_pack_at": now}),
            )
        except Exception as exc:  # noqa: BLE001 — pack build must not fail on meta
            logger.warning("Failed to stamp validation pack time for %s: %s", slug, exc)
    return pack


def validation_pack_summary(deal: DealLike) -> dict[str, Any]:
    """Lightweight counts for databook summary header."""
    pack = build_validation_pack(deal, persist_timestamp=False, render_crops=False)
    return {
        "ready_for_review": pack.ready_for_review,
        "release_id": pack.release_id,
        "release_version": pack.release_version,
        "counts": pack.counts,
        "generated_at": pack.generated_at,
    }
