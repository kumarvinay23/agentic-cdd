"""Build and publish versioned databook releases (P0).

Working store (extract / promoted / issues) remains mutable. A release is an
immutable snapshot of proven / doubtful / missing cells that reports consume.

Classification order (per metric×year):
  1. PROVEN — working promoted wins; unresolved conflict tickets do not demote it,
     but competing candidates are attached as ``alternatives`` for audit.
  2. DOUBTFUL — held-out / candidate rows or open conflicts without a promoted winner.
  3. MISSING — material keys whose only rows were dropped.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from agetic_cdd_api.services_databook_models import (
    CoverageSpec,
    DatabookRelease,
    DealDatabookParams,
    DealLike,
    ExpectedDocsAssessment,
    ExtractedRow,
    ProofLevel,
    ReleaseCellStatus,
    ReleasedCell,
    RowStatus,
)
from agetic_cdd_api.services_databook_prove import meets_min_proof, parse_min_proof_level
from agetic_cdd_api.services_databook_store import (
    list_release_summaries,
    load_current_release,
    load_issues,
    load_meta,
    load_promoted,
    load_release_for_slug,
    load_rows,
    next_release_version,
    release_write_lock,
    save_release,
)
from agetic_cdd_api.services_databook_extract import (
    is_implausible_money_magnitude,
    is_year_as_value,
)
from agetic_cdd_api.services_databook_map import caption_plainness, map_caption
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

ReleaseSource = Literal["manual", "rescan", "decision", "bootstrap", "import"]

# Align with consume.MATERIAL_METRIC_KEYS (kept local to avoid import cycles).
_MATERIAL_KEYS = frozenset(
    {
        "revenue",
        "ebitda",
        "gross_margin",
        "ebitda_margin",
        "nrr",
        "grr",
        "yoy_growth",
    }
)

# Row statuses that can still yield a release cell elsewhere in the pipeline.
_RELEASABLE_ROW_STATUSES = frozenset(
    {
        RowStatus.CANDIDATE,
        RowStatus.HELD_OUT,
        RowStatus.PROMOTED,
        RowStatus.VOUCHED,
    }
)


def _reject_reason(
    metric_key: str,
    fiscal_year: int,
    value: float,
    *,
    params: DealDatabookParams | None = None,
    sector_pack: str = "generic",
) -> str | None:
    base = params or DealDatabookParams()
    pack = (sector_pack or base.sector_pack or "generic").strip().lower()
    cfg = base.model_copy(update={"sector_pack": pack})
    if cfg.blocks_saas_metric(metric_key):
        return "Rejected SaaS retention metric on non-SaaS sector pack"
    if is_year_as_value(metric_key, fiscal_year, value):
        return "Rejected year-as-value (fiscal year leaked into metric cell)"
    if is_implausible_money_magnitude(metric_key, value):
        return "Rejected implausible magnitude (likely unscaled currency units)"
    return None


@dataclass(frozen=True, slots=True)
class SlugDeal:
    """Concrete DealLike for slug-only report/bootstrap paths."""

    id: str
    slug: str | None = None

    def __post_init__(self) -> None:
        if not (self.slug or self.id):
            raise ValueError("SlugDeal requires id or slug")


def _safe_float(
    raw: Any,
    *,
    context: str,
    metric_key: str | None = None,
    fiscal_year: int | None = None,
) -> float | None:
    """Parse a numeric candidate; log when raw data is present but unparseable."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Databook release: failed to parse %s as float (metric=%s fy=%s value=%r)",
            context,
            metric_key,
            fiscal_year,
            raw,
        )
        return None


def _conflict_alternatives(conflict: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives: list[dict[str, Any]] = []
    for cand in conflict.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        alternatives.append(
            {
                "value": cand.get("value"),
                "sources": list(cand.get("sources") or []),
                "captions": list(cand.get("captions") or []),
                "chosen": bool(cand.get("chosen")),
                "stated_by": cand.get("stated_by"),
            }
        )
    return alternatives


def _chosen_from_conflict(
    conflict: dict[str, Any],
    *,
    metric_key: str,
    fiscal_year: int,
) -> float | None:
    """Return the conflict winner, skipping year-as-value leaks."""
    for cand in conflict.get("candidates") or []:
        if not isinstance(cand, dict) or not cand.get("chosen"):
            continue
        parsed = _safe_float(
            cand.get("value"),
            context="conflict.chosen",
            metric_key=metric_key,
            fiscal_year=fiscal_year,
        )
        if parsed is not None and not is_year_as_value(metric_key, fiscal_year, parsed):
            if not is_implausible_money_magnitude(metric_key, parsed):
                return parsed
    # Fall back to any non-year candidate (prefer highest stated_by).
    ranked: list[tuple[int, float, dict[str, Any]]] = []
    for cand in conflict.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        parsed = _safe_float(
            cand.get("value"),
            context="conflict.candidate",
            metric_key=metric_key,
            fiscal_year=fiscal_year,
        )
        if (
            parsed is None
            or is_year_as_value(metric_key, fiscal_year, parsed)
            or is_implausible_money_magnitude(metric_key, parsed)
        ):
            continue
        stated = int(cand.get("stated_by") or 0)
        ranked.append((stated, parsed, cand))
    if not ranked:
        return None
    # Higher ladder score first; on tie prefer the median (resists inflated outliers).
    ranked.sort(key=lambda x: (-x[0], -abs(x[1])))
    top_score = ranked[0][0]
    top = [r for r in ranked if r[0] == top_score]
    if len(top) > 1:
        import statistics

        median = float(statistics.median([v for _, v, _ in top]))
        top.sort(key=lambda x: (abs(x[1] - median), -abs(x[1])))
        logger.warning(
            "Databook release: conflict tie on stated_by=%s for %s fy=%s — "
            "using median-nearest value %s among %d candidates (median=%s)",
            top_score,
            metric_key,
            fiscal_year,
            top[0][1],
            len(top),
            median,
        )
        return top[0][1]
    return ranked[0][1]


def _best_held_row(group: list[ExtractedRow], metric_key: str, fy: int) -> ExtractedRow | None:
    """Pick the least-bad held-out row for a doubtful release cell."""
    eligible = [
        r
        for r in group
        if not is_year_as_value(metric_key, fy, r.value)
        and not is_implausible_money_magnitude(metric_key, r.value)
        and same_family_ok(r.caption, metric_key)
    ]
    if not eligible:
        eligible = [
            r
            for r in group
            if not is_year_as_value(metric_key, fy, r.value)
            and not is_implausible_money_magnitude(metric_key, r.value)
        ]
    if not eligible:
        return None

    def rank(r: ExtractedRow) -> tuple:
        return (
            1 if r.dual_agree else 0,
            caption_plainness(r.caption, metric_key),
            0 if r.assumption else 1,
            -abs(r.value) if abs(r.value) < 100_000 else -1e18,
            r.source_name,
            r.row_id,
        )

    return max(eligible, key=rank)


def same_family_ok(caption: str, metric_key: str) -> bool:
    from agetic_cdd_api.services_databook_map import same_family_allowed

    return same_family_allowed(caption, metric_key)


def build_release_cells(deal: DealLike) -> list[ReleasedCell]:
    """Map working store → proven / doubtful / missing cells.

    PROVEN requires proof_level ≥ min_proof_level (default L2). Promoted rows
    below the gate are released as doubtful (checks act — S5-14 / AR-3).
    Coverage missing+request is applied by ``finalize_release_coverage``.
    """
    promoted = load_promoted(deal)
    rows = load_rows(deal)
    issues = load_issues(deal)
    params = load_meta(deal).params
    minimum = parse_min_proof_level(params.min_proof_level)

    row_by_id = {r.row_id: r for r in rows}
    cells: dict[tuple[str, int], ReleasedCell] = {}

    for p in promoted:
        reject = _reject_reason(
            p.metric_key, p.fiscal_year, p.value, params=params
        )
        if reject:
            cells[(p.metric_key, p.fiscal_year)] = ReleasedCell(
                metric_key=p.metric_key,
                fiscal_year=p.fiscal_year,
                status=ReleaseCellStatus.MISSING,
                value=None,
                unit=p.unit,
                currency=p.currency,
                scale=p.scale,
                row_id=p.row_id,
                sources=list(p.sources),
                captions=list(p.captions),
                reason=reject,
                decision_id=p.decision_id,
                auto=p.auto,
                scope=p.scope,
                statement=p.statement,
                period_end=p.period_end,
                period_length=p.period_length,
                source_basis=p.source_basis,
                source_ref=p.source_ref,
                proof_level=p.proof_level,
                proof_checks=list(p.proof_checks or []),
            )
            continue

        level = p.proof_level
        if level is None:
            src = row_by_id.get(p.row_id)
            level = src.proof_level if src else None
        if level is None and not p.auto:
            # HITL decision without stamped level → treat as L4 vouch-equivalent.
            level = ProofLevel.L4
        checks = list(p.proof_checks or [])
        if not checks:
            src = row_by_id.get(p.row_id)
            if src:
                checks = list(src.proof_checks or [])

        if meets_min_proof(level, minimum):
            status = ReleaseCellStatus.PROVEN
            reason = f"Proven at {level.value if level else 'L2'}"
        else:
            status = ReleaseCellStatus.DOUBTFUL
            reason = (
                f"Promoted in working store but proof "
                f"{level.value if level else 'missing'} < {minimum.value}"
            )

        cells[(p.metric_key, p.fiscal_year)] = ReleasedCell(
            metric_key=p.metric_key,
            fiscal_year=p.fiscal_year,
            status=status,
            value=p.value,
            unit=p.unit,
            currency=p.currency,
            scale=p.scale,
            row_id=p.row_id,
            sources=list(p.sources),
            captions=list(p.captions),
            reason=reason,
            decision_id=p.decision_id,
            auto=p.auto,
            scope=p.scope,
            statement=p.statement,
            period_end=p.period_end,
            period_length=p.period_length,
            source_basis=p.source_basis,
            source_ref=p.source_ref,
            proof_level=level,
            proof_checks=checks,
        )

    conflicts_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for item in issues:
        if item.get("kind") != "conflict":
            continue
        fy = item.get("fiscal_year")
        if fy is None:
            continue
        try:
            fy_i = int(fy)
        except (TypeError, ValueError):
            logger.warning(
                "Databook release: skipping conflict with non-int fiscal_year=%r metric=%s",
                fy,
                item.get("metric"),
            )
            continue
        # Prefer canonical metric_key; map display labels ("Total Revenue" /
        # "EBITDA") onto metric_key so we never emit orphan cells keyed by the
        # display label alone (empty sources, duplicate facts).
        keys: list[str] = []
        mk = str(item.get("metric_key") or "").strip()
        if mk:
            keys.append(mk)
        label = str(item.get("metric") or "").strip()
        if label:
            hit = map_caption(label)
            if hit and hit.metric_key:
                if hit.metric_key not in keys:
                    keys.append(hit.metric_key)
            elif label not in keys:
                keys.append(label)
        for key_name in keys:
            conflicts_by_key[(key_name, fy_i)] = item

    # Intentional: promoted/PROVEN wins over open conflict tickets. Attach competing
    # candidates as alternatives so auditability is not lost when we skip demotion.
    for key, conflict in conflicts_by_key.items():
        cell = cells.get(key)
        if cell is None or cell.status != ReleaseCellStatus.PROVEN:
            continue
        alternatives = _conflict_alternatives(conflict)
        if not alternatives:
            continue
        reason = cell.reason or "Promoted in working databook"
        if "competing candidates retained" not in reason:
            reason = f"{reason}; competing candidates retained as alternatives"
        cells[key] = cell.model_copy(
            update={
                "alternatives": alternatives,
                "reason": reason,
            }
        )

    # Doubtful: held-out / candidate mapped rows not already proven.
    held_groups: dict[tuple[str, int], list[ExtractedRow]] = {}
    for row in rows:
        if row.status not in {RowStatus.HELD_OUT, RowStatus.CANDIDATE}:
            continue
        if not row.metric_key or row.fiscal_year is None:
            continue
        key = (row.metric_key, int(row.fiscal_year))
        if key in cells and cells[key].status == ReleaseCellStatus.PROVEN:
            continue
        held_groups.setdefault(key, []).append(row)

    for key, group in held_groups.items():
        metric_key, fy = key
        if params.blocks_saas_metric(metric_key):
            continue
        conflict = conflicts_by_key.get(key)
        alternatives: list[dict[str, Any]] = []
        best_value: float | None = None
        best_row = _best_held_row(group, metric_key, fy)
        reason = "Held out pending proof or review"
        if conflict:
            reason = "Sources disagree — released as doubtful"
            alternatives = _conflict_alternatives(conflict)
            best_value = _chosen_from_conflict(
                conflict, metric_key=metric_key, fiscal_year=fy
            )
        if best_row is None:
            # Only year-as-value / unusable held rows — do not ship a number.
            cells[key] = ReleasedCell(
                metric_key=metric_key,
                fiscal_year=fy,
                status=ReleaseCellStatus.MISSING,
                value=None,
                sources=list(dict.fromkeys(r.source_name for r in group if r.source_name)),
                captions=list(dict.fromkeys(r.caption for r in group if r.caption)),
                reason="No releasable evidence (year-as-value or unusable held rows)",
                auto=True,
            )
            continue
        if best_value is None:
            best_value = _safe_float(
                best_row.value,
                context="held_row.value",
                metric_key=metric_key,
                fiscal_year=fy,
            )
            if best_value is not None and (
                is_year_as_value(metric_key, fy, best_value)
                or is_implausible_money_magnitude(metric_key, best_value)
            ):
                best_value = None
        if best_value is None:
            cells[key] = ReleasedCell(
                metric_key=metric_key,
                fiscal_year=fy,
                status=ReleaseCellStatus.MISSING,
                value=None,
                row_id=best_row.row_id,
                sources=list(dict.fromkeys(r.source_name for r in group if r.source_name)),
                captions=list(dict.fromkeys(r.caption for r in group if r.caption)),
                reason="No releasable numeric evidence after year-as-value filter",
                auto=True,
            )
            continue
        if any(r.assumption for r in group):
            reason = f"{reason}; assumption on unit/scale"

        # Prefer the winning conflict candidate's sources so mixed workbook+pack
        # filenames do not collapse both bases onto one cell.
        sources = list(dict.fromkeys(r.source_name for r in group if r.source_name))
        captions = list(dict.fromkeys(r.caption for r in group if r.caption))
        if conflict and alternatives:
            for cand in alternatives:
                if not cand.get("chosen"):
                    continue
                cand_sources = [str(s) for s in (cand.get("sources") or []) if s]
                cand_caps = [str(c) for c in (cand.get("captions") or []) if c]
                if cand_sources:
                    sources = cand_sources
                if cand_caps:
                    captions = list(dict.fromkeys([*cand_caps, *captions]))
                break

        cells[key] = ReleasedCell(
            metric_key=metric_key,
            fiscal_year=fy,
            status=ReleaseCellStatus.DOUBTFUL,
            value=best_value,
            unit=best_row.unit,
            currency=best_row.currency,
            scale=best_row.scale,
            row_id=best_row.row_id,
            sources=sources,
            captions=captions,
            reason=reason,
            alternatives=alternatives,
            auto=True,
            scope=best_row.scope,
            statement=best_row.statement,
            period_end=best_row.period_end,
            period_length=best_row.period_length,
            source_basis=best_row.source_basis,
            source_ref=best_row.source_ref,
            proof_level=best_row.proof_level or ProofLevel.L1,
            proof_checks=list(best_row.proof_checks or []),
        )

    # Conflicts with no held rows still produce doubtful if not already classified.
    for key, conflict in conflicts_by_key.items():
        if key in cells:
            continue
        metric_key, fy = key
        value = _chosen_from_conflict(conflict, metric_key=metric_key, fiscal_year=fy)
        alternatives = _conflict_alternatives(conflict)
        if value is None and alternatives:
            logger.warning(
                "Databook release: doubtful cell %s fy=%s has alternatives but no parseable value",
                metric_key,
                fy,
            )
        cells[key] = ReleasedCell(
            metric_key=metric_key,
            fiscal_year=fy,
            status=ReleaseCellStatus.DOUBTFUL,
            value=value,
            sources=[],
            captions=[],
            reason="Sources disagree — released as doubtful",
            alternatives=alternatives,
            auto=True,
        )

    # Missing: material (metric, year) seen in extract but fully dropped / unusable.
    seen_material: dict[tuple[str, int], list[ExtractedRow]] = {}
    for row in rows:
        if not row.metric_key or row.fiscal_year is None:
            continue
        if row.metric_key not in _MATERIAL_KEYS:
            continue
        key = (row.metric_key, int(row.fiscal_year))
        seen_material.setdefault(key, []).append(row)

    for key, group in seen_material.items():
        if key in cells:
            continue
        if not any(r.status in _RELEASABLE_ROW_STATUSES for r in group):
            cells[key] = ReleasedCell(
                metric_key=key[0],
                fiscal_year=key[1],
                status=ReleaseCellStatus.MISSING,
                value=None,
                sources=list(dict.fromkeys(r.source_name for r in group if r.source_name)),
                captions=[],
                reason="No releasable evidence (all candidate rows dropped or rejected)",
                auto=True,
            )

    return sorted(cells.values(), key=lambda c: (c.metric_key, c.fiscal_year))


def _counts(cells: list[ReleasedCell], request_list: list | None = None) -> dict[str, int]:
    counts = Counter(c.status.value for c in cells)
    return {
        "proven": counts["proven"],
        "doubtful": counts["doubtful"],
        "missing": counts["missing"],
        "requests": len(request_list or []),
    }


def finalize_release_coverage(
    deal: DealLike,
    cells: list[ReleasedCell],
    *,
    coverage_keys: list[str] | None = None,
    coverage_years: list[int] | None = None,
) -> tuple[list[ReleasedCell], list, CoverageSpec, ExpectedDocsAssessment | None]:
    """G2 pass: fill coverage gaps as missing+request; assess expected docs."""
    from agetic_cdd_api.services_databook_classify import (
        assess_expected_docs,
        build_expected_docs_for_deal,
    )
    from agetic_cdd_api.services_databook_coverage import (
        fill_missing_coverage_cells,
        resolve_coverage_spec,
    )
    from agetic_cdd_api.services_databook_store import load_expected_docs, load_file_register, load_meta

    params = load_meta(deal).params
    cell_years = {c.fiscal_year for c in cells}
    coverage = resolve_coverage_spec(
        params=params,
        coverage_keys=coverage_keys,
        coverage_years=coverage_years,
        cell_years=cell_years,
    )

    assessment: ExpectedDocsAssessment | None = load_expected_docs(deal)
    if assessment is None:
        register = load_file_register(deal)
        slug = deal.slug or deal.id
        profile = params.expected_doc_profile or params.sector_pack or "generic"
        from agetic_cdd_api.models import Deal

        if isinstance(deal, Deal):
            try:
                assessment = build_expected_docs_for_deal(
                    deal,
                    register=register,
                    profile=profile,
                    persist=True,
                )
            except Exception:
                assessment = None
        if assessment is None:
            assessment = assess_expected_docs(
                register,
                deal_slug=str(slug),
                profile=str(profile),
            )

    filled, request_list = fill_missing_coverage_cells(
        cells, coverage=coverage, assessment=assessment
    )
    return filled, request_list, coverage, assessment


def create_release(
    deal: DealLike,
    *,
    source: ReleaseSource = "manual",
    note: str | None = None,
) -> DatabookRelease:
    """Publish a new immutable release from the working store and set it current.

    Version allocation and snapshot write share ``release_write_lock`` so two
    workers cannot publish the same ``vN`` (TOCTOU-safe).
    """
    # Build cells outside the lock — pure reads of working store.
    cells = build_release_cells(deal)
    cells, request_list, coverage, expected_docs = finalize_release_coverage(deal, cells)
    with release_write_lock(deal):
        version = next_release_version(deal)
        release_id = f"v{version}"
        release = DatabookRelease(
            release_id=release_id,
            version=version,
            created_at=utc_now_iso(),
            deal_slug=(deal.slug or deal.id),
            source=source,
            note=note,
            cells=cells,
            counts=_counts(cells, request_list),
            coverage=coverage,
            request_list=request_list,
            expected_docs=expected_docs,
        )
        save_release(deal, release, set_current=True, locked=True)
    logger.info(
        "Databook release %s for %s: %s",
        release.release_id,
        deal.slug or deal.id,
        release.counts,
    )
    # G1 / C-5 — mark ready reports stale so downstream rebuild is explicit.
    try:
        from agetic_cdd_api.report_store import mark_reports_stale_for_databook_release

        slug = (deal.slug or deal.id or "").strip()
        if slug:
            marked = mark_reports_stale_for_databook_release(
                slug,
                release_id=release.release_id,
                release_version=release.version,
            )
            if marked:
                logger.info(
                    "Marked reports stale after %s: %s",
                    release.release_id,
                    ", ".join(marked),
                )
    except Exception:
        logger.exception("Failed to mark reports stale after databook release")
    return release


def ensure_current_release(
    deal: DealLike,
    *,
    bootstrap: bool = True,
) -> DatabookRelease | None:
    """Return current release; optionally bootstrap from working store if none exists."""
    current = load_current_release(deal)
    if current is not None:
        return current
    if not bootstrap:
        return None
    promoted = load_promoted(deal)
    rows = load_rows(deal)
    if not promoted and not rows:
        return None
    return create_release(deal, source="bootstrap", note="Auto-bootstrap from working store")


def ensure_current_release_for_slug(deal_slug: str) -> DatabookRelease | None:
    """Slug-based ensure for report builders (bootstrap from disk if needed)."""
    release = load_release_for_slug(deal_slug)
    if release is not None:
        return release

    from agetic_cdd_api.services_deals import deals_root

    root = deals_root() / deal_slug / "databook"
    if not root.is_dir():
        return None

    deal: DealLike = SlugDeal(id=deal_slug, slug=deal_slug)
    meta = load_meta(deal)
    if meta.current_release_id:
        return load_release_for_slug(deal_slug, meta.current_release_id)
    promoted = load_promoted(deal)
    rows = load_rows(deal)
    if not promoted and not rows:
        return None
    return create_release(deal, source="bootstrap", note="Auto-bootstrap from working store")


def release_summary_dict(release: DatabookRelease | None) -> dict[str, Any] | None:
    if release is None:
        return None
    open_requests = [
        r for r in (release.request_list or []) if getattr(r, "status", "open") == "open"
    ]
    return {
        "release_id": release.release_id,
        "version": release.version,
        "created_at": release.created_at,
        "source": release.source,
        "note": release.note,
        "counts": release.counts,
        "request_count": len(open_requests),
        "coverage": release.coverage.model_dump(mode="json") if release.coverage else None,
        "missing_required_docs": list(
            (release.expected_docs.missing_required if release.expected_docs else []) or []
        ),
    }


def list_releases(deal: DealLike) -> list[dict[str, Any]]:
    return list_release_summaries(deal)
