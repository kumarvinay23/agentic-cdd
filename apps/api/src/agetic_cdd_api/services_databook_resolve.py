"""Series sanity, conflict detection, and metric promotion rules."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from typing import Any, Literal

from agetic_cdd_api.services_databook_extract import (
    is_implausible_money_magnitude,
    is_year_as_value,
)
from agetic_cdd_api.services_databook_map import caption_plainness, display_metric_label, same_family_allowed
from agetic_cdd_api.services_databook_models import (
    DEFAULT_CONFLICT_RULE,
    PROOF_LEVEL_RANK,
    SCALE_STEP_REASON,
    SERIES_DROP_REASON,
    ConflictCandidate,
    DataQualityConflict,
    DataQualityDropped,
    DealDatabookParams,
    ExtractedRow,
    MetricFamily,
    PromotedMetric,
    ProofLevel,
    RowStatus,
)
from agetic_cdd_api.services_databook_prove import meets_min_proof, parse_min_proof_level


def _proof_rank(level: ProofLevel | None) -> int:
    if level is None:
        return -1
    return PROOF_LEVEL_RANK[level]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def _value_bucket(value: float) -> float:
    """Relative-precision bucket so large-unit currencies don't split on float noise."""
    if not math.isfinite(value) or value == 0.0:
        return 0.0
    # ~9 significant digits — stable for JPY/IDR-scale integers and typical money floats.
    return float(f"{value:.9g}")


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _dominant_sign(values: list[float]) -> int | None:
    """Majority sign among non-zero values; None when tied or empty."""
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return None


def apply_series_drops(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[ExtractedRow], list[dict[str, Any]]]:
    """Drop values orders of magnitude below the metric series centre.

    Centre is taken from the dominant-sign peer cluster only, and opposite-sign
    adjustments (e.g. a small reclass next to large positive revenue) are never
    series-dropped — they stay for conflict / mapping review.
    """
    by_metric: dict[str, list[ExtractedRow]] = defaultdict(list)
    for row in rows:
        if row.metric_key and row.fiscal_year is not None:
            by_metric[row.metric_key].append(row)

    dropped_issues: list[dict[str, Any]] = []
    drop_ids: set[str] = set()
    ratio = max(params.series_magnitude_ratio, 2.0)

    for metric_key, group in by_metric.items():
        signed = [r.value for r in group if r.value != 0]
        if len(signed) < 3:
            continue
        majority = _dominant_sign(signed)
        if majority is None:
            continue
        # Median of absolute magnitudes within the dominant-sign cluster.
        values = [abs(v) for v in signed if _sign(v) == majority]
        if len(values) < 3:
            continue
        centre = _median(values)
        if centre <= 0:
            continue
        for row in group:
            if _sign(row.value) != majority:
                continue
            magnitude = abs(row.value)
            if magnitude == 0:
                continue
            if centre / magnitude >= ratio:
                drop_ids.add(row.row_id)
                dropped_issues.append(
                    DataQualityDropped(
                        source="series",
                        reason=SERIES_DROP_REASON,
                        detail={
                            "metric": display_metric_label(metric_key, row.caption),
                            "fiscal_year": row.fiscal_year,
                            "value": row.value,
                        },
                    ).model_dump(mode="json")
                )

    out: list[ExtractedRow] = []
    for row in rows:
        if row.row_id in drop_ids:
            out.append(row.model_copy(update={"status": RowStatus.DROPPED}))
        else:
            out.append(row)
    return out, dropped_issues


def _clean_peer_centre(others: list[float], *, cluster_log_span: float = 0.5) -> float | None:
    """Geometric-stable centre from peers within ~cluster_log_span of the log-median.

    Rejects volatile leave-one-out sets like [1.0, 1_000_000.0] that would produce
    a meaningless arithmetic median for ×1000 detection.
    """
    if len(others) < 2:
        return None
    positive = [v for v in others if v > 0]
    if len(positive) < 2:
        return None
    peer_logs = [math.log10(v) for v in positive]
    log_med = float(statistics.median(peer_logs))
    clean = [
        v
        for v, lg in zip(positive, peer_logs)
        if abs(lg - log_med) <= cluster_log_span
    ]
    if len(clean) < 2:
        return None
    centre = _median(clean)
    if centre <= 0:
        return None
    return centre


def apply_scale_step_guard(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[ExtractedRow], set[str], list[dict[str, Any]]]:
    """Hold out values ~×1000 / ÷1000 vs a clean peer centre (thousand-scale misread).

    Uses log10 distance vs leave-one-out peers that form a tight cluster, so a
    volatile pair like ``[1, 1e6]`` cannot invent a false baseline.
    """
    by_metric: dict[str, list[ExtractedRow]] = defaultdict(list)
    for row in rows:
        if row.status == RowStatus.DROPPED:
            continue
        if row.metric_key and row.fiscal_year is not None:
            by_metric[row.metric_key].append(row)

    hold_ids: set[str] = set()
    issues: list[dict[str, Any]] = []
    step = max(float(params.scale_step_ratio), 100.0)
    tol = min(max(float(params.scale_step_tol), 0.05), 0.5)
    lo = step * (1.0 - tol)
    hi = step * (1.0 + tol)
    log_lo = math.log10(lo)
    log_hi = math.log10(hi)

    for metric_key, group in by_metric.items():
        if len(group) < 3:
            continue
        for row in group:
            magnitude = abs(row.value)
            if magnitude == 0:
                continue
            others = [abs(r.value) for r in group if r.row_id != row.row_id and r.value != 0]
            centre = _clean_peer_centre(others)
            if centre is None or centre <= 0:
                continue
            log_diff = abs(math.log10(magnitude) - math.log10(centre))
            if log_lo <= log_diff <= log_hi:
                ratio = max(centre / magnitude, magnitude / centre)
                hold_ids.add(row.row_id)
                issues.append(
                    {
                        "kind": "scale_step",
                        "source": "series",
                        "reason": SCALE_STEP_REASON,
                        "metric": display_metric_label(metric_key, row.caption),
                        "metric_key": metric_key,
                        "fiscal_year": row.fiscal_year,
                        "value": row.value,
                        "series_centre": centre,
                        "ratio": round(ratio, 3),
                        "log10_diff": round(log_diff, 3),
                        "row_id": row.row_id,
                    }
                )

    return rows, hold_ids, issues


def _issue_metric_key(item: dict[str, Any]) -> Any:
    """Strict fallback order for issue identity across builders/merges."""
    return item.get("metric_key") or item.get("metric") or item.get("caption")


def _dedupe_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        kind = item.get("kind")
        if kind == "dropped":
            detail = item.get("detail") or {}
            key: tuple[Any, ...] = (
                "dropped",
                detail.get("metric"),
                detail.get("fiscal_year"),
                detail.get("value"),
            )
        elif kind == "conflict":
            cands = tuple(
                sorted(
                    _value_bucket(float(c.get("value")))
                    for c in (item.get("candidates") or [])
                    if c.get("value") is not None
                )
            )
            key = ("conflict", item.get("metric"), item.get("fiscal_year"), cands)
        elif kind == "failed_check":
            key = (
                "failed_check",
                item.get("block_id"),
                item.get("fiscal_year"),
                item.get("printed_subtotal"),
                item.get("computed_sum"),
            )
        elif kind == "assumed":
            key = (
                "assumed",
                str(_issue_metric_key(item) or "").strip().lower(),
                item.get("fiscal_year"),
                item.get("value"),
                item.get("reason"),
            )
        elif kind == "scale_step":
            # Fact identity — not row_id-first — so merges with/without row_id collide.
            key = (
                "scale_step",
                str(_issue_metric_key(item) or "").strip().lower(),
                item.get("fiscal_year"),
                item.get("value"),
            )
        elif kind == "unmapped":
            key = (
                "unmapped",
                str(_issue_metric_key(item) or "").strip().lower(),
                item.get("fiscal_year"),
                item.get("value"),
                item.get("row_id") or "",
            )
        else:
            key = ("raw", json.dumps(item, sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _row_ladder(row: ExtractedRow) -> int:
    from agetic_cdd_api.services_databook_models import SOURCE_LADDER_SCORE, SourceBasis

    if row.ladder_score is not None:
        return int(row.ladder_score)
    if row.source_basis is not None:
        return SOURCE_LADDER_SCORE.get(row.source_basis, SOURCE_LADDER_SCORE[SourceBasis.UNKNOWN])
    return SOURCE_LADDER_SCORE[SourceBasis.UNKNOWN]


# Metrics whose within-document component lines sum to the headline (no total row).
_ADDITIVE_WITHIN_DOC = frozenset({"labor_cost"})


def _prefer_total_rows(group: list[ExtractedRow]) -> list[ExtractedRow]:
    """When a Total line exists, drop component peers so they don't conflict."""
    from agetic_cdd_api.services_databook_blocks import is_total_caption

    totals = [r for r in group if is_total_caption(r.caption)]
    if not totals:
        return group
    # Prefer totals per source; keep non-totals only from sources without a total.
    sources_with_total = {r.source_name for r in totals}
    kept = [
        r
        for r in group
        if is_total_caption(r.caption) or r.source_name not in sources_with_total
    ]
    return kept or group


def detect_conflicts(
    rows: list[ExtractedRow],
) -> tuple[list[dict[str, Any]], set[str]]:
    """
    Group by (metric_key, fiscal_year). Only same-family captions may compete.

    Auto-chosen is a proposal only — rows stay held_out when conflicted.
    Phase 1: source ladder (audited ≫ … ≫ deal papers) ranks before stated_by.
    Within one document, Total captions displace components; additive metrics
    (labour) are allowed to carry multiple component values for later summing.
    """
    active = [
        r
        for r in rows
        if r.status != RowStatus.DROPPED
        and r.metric_key
        and r.fiscal_year is not None
        and same_family_allowed(r.caption, r.metric_key)
    ]

    groups: dict[tuple[str, int], list[ExtractedRow]] = defaultdict(list)
    for row in active:
        assert row.metric_key and row.fiscal_year is not None
        groups[(row.metric_key, row.fiscal_year)].append(row)

    source_totals: dict[str, int] = defaultdict(int)
    source_metric_facts: dict[tuple[str, str], int] = defaultdict(int)
    source_ladder: dict[str, int] = {}
    for row in active:
        source_totals[row.source_name] += 1
        if row.metric_key:
            source_metric_facts[(row.source_name, row.metric_key)] += 1
        # Keep the best ladder score seen for a source name.
        score = _row_ladder(row)
        prev = source_ladder.get(row.source_name)
        if prev is None or score > prev:
            source_ladder[row.source_name] = score

    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()

    for (metric_key, year), group in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        group = _prefer_total_rows(group)
        # Labour (and similar): COGS + SG&A payroll lines sum — not a conflict.
        if (
            metric_key in _ADDITIVE_WITHIN_DOC
            and len({r.source_name for r in group}) == 1
        ):
            continue

        value_buckets: dict[float, list[ExtractedRow]] = defaultdict(list)
        for row in group:
            value_buckets[_value_bucket(row.value)].append(row)

        if len(value_buckets) < 2:
            continue

        candidates: list[ConflictCandidate] = []
        for value, members in value_buckets.items():
            # Ladder-first, then name — primary_source tie-break must not be alpha-only.
            sources = sorted(
                {m.source_name for m in members},
                key=lambda s: (-source_ladder.get(s, 50), s),
            )
            captions = sorted({m.caption for m in members})
            best = max(
                members,
                key=lambda m: (
                    _row_ladder(m),
                    source_metric_facts[(m.source_name, metric_key)],
                    source_totals[m.source_name],
                    caption_plainness(m.caption, metric_key),
                    m.source_name,
                    m.row_id,
                ),
            )
            candidates.append(
                ConflictCandidate(
                    value=value,
                    sources=sources,
                    captions=captions,
                    chosen=False,
                    stated_by=len(sources),
                    source_facts=source_metric_facts[(best.source_name, metric_key)],
                    source_total_facts=source_totals[best.source_name],
                    row_ids=[m.row_id for m in members],
                )
            )

        centre = _median([c.value for c in candidates])

        def rank(c: ConflictCandidate) -> tuple:
            plain = max((caption_plainness(cap, metric_key) for cap in c.captions), default=0.0)
            primary_source = c.sources[0] if c.sources else ""
            ladder = max((source_ladder.get(s, 50) for s in c.sources), default=50)
            return (
                ladder,
                c.stated_by,
                c.source_facts,
                c.source_total_facts,
                plain,
                -abs(c.value - centre),
                _value_bucket(c.value),
                primary_source,
            )

        eligible = [
            c
            for c in candidates
            if max((caption_plainness(cap, metric_key) for cap in c.captions), default=0.0) > 0.0
        ]
        # Prefer plain captions for ranking, but always record conflicts even if plainness is 0.
        pool = eligible if eligible else candidates
        winner = max(pool, key=rank)

        for c in candidates:
            c.chosen = c is winner

        scopes = {m.source_name for m in group}
        scope: Literal["across documents", "within one document"] = (
            "across documents" if len(scopes) > 1 else "within one document"
        )
        label = display_metric_label(metric_key, group[0].caption)
        issue = DataQualityConflict(
            metric=label,
            fiscal_year=year,
            chosen=winner.value,
            candidates=candidates,
            scope=scope,
            rule=DEFAULT_CONFLICT_RULE,
        ).model_dump(mode="json")
        # Canonical key for release / FDD join — display label alone cannot match
        # metric_key cells (e.g. "Total Revenue" vs revenue).
        issue["metric_key"] = metric_key
        issue["ladder_scores"] = {
            s: source_ladder.get(s, 50) for s in sorted(scopes)
        }
        issues.append(issue)
        for m in group:
            hold_ids.add(m.row_id)

    return _dedupe_issues(issues), hold_ids


def apply_statuses_and_promote(
    rows: list[ExtractedRow],
    *,
    hold_ids: set[str],
    block_fail_ids: set[str] | None = None,
    params: DealDatabookParams | None = None,
) -> tuple[list[ExtractedRow], list[PromotedMetric]]:
    """
    Auto-promote only unique+mapped+no-assumption rows at min proof level (default L2).

    Rows in failed statement blocks are always held out (never silent-promote).
    Identical values from multiple sources promote together (merged sources).
    """
    fail_ids = block_fail_ids or set()
    combined_hold = set(hold_ids) | fail_ids
    params = params or DealDatabookParams()
    minimum = parse_min_proof_level(params.min_proof_level)

    # Collapse Total vs component peers before uniqueness / promote.
    eligible_by_key: dict[tuple[str, int], list[ExtractedRow]] = defaultdict(list)
    for row in rows:
        if (
            row.status == RowStatus.DROPPED
            or row.row_id in fail_ids
            or not row.metric_key
            or row.fiscal_year is None
            or not same_family_allowed(row.caption, row.metric_key)
            or is_year_as_value(row.metric_key, row.fiscal_year, row.value)
            or is_implausible_money_magnitude(row.metric_key, row.value)
        ):
            continue
        eligible_by_key[(row.metric_key, row.fiscal_year)].append(row)
    for key, members in list(eligible_by_key.items()):
        eligible_by_key[key] = _prefer_total_rows(members)

    groups: dict[tuple[str, int], set[float]] = defaultdict(set)
    for key, members in eligible_by_key.items():
        for row in members:
            groups[key].add(_value_bucket(row.value))

    # Collect promotable rows by metric+year
    promo_members: dict[tuple[str, int], list[ExtractedRow]] = defaultdict(list)
    eligible_ids = {r.row_id for members in eligible_by_key.values() for r in members}
    for row in rows:
        if row.status == RowStatus.DROPPED or row.row_id in combined_hold:
            continue
        if row.row_id not in eligible_ids:
            continue
        key = (row.metric_key or "", int(row.fiscal_year or 0))
        multi_ok = (
            row.metric_key in _ADDITIVE_WITHIN_DOC
            and len({m.source_name for m in eligible_by_key.get(key, [])}) <= 1
        )
        if (
            row.metric_key
            and row.fiscal_year is not None
            and not row.assumption
            and not row.derived  # S4-6: derived metrics are not auto-promoted as printed facts
            and meets_min_proof(row.proof_level, minimum)
            and same_family_allowed(row.caption, row.metric_key)
            and not is_year_as_value(row.metric_key, row.fiscal_year, row.value)
            and not is_implausible_money_magnitude(row.metric_key, row.value)
            and not params.blocks_saas_metric(row.metric_key)
            and (multi_ok or len(groups.get((row.metric_key, row.fiscal_year), set())) == 1)
        ):
            promo_members[(row.metric_key, row.fiscal_year)].append(row)

    promoted: list[PromotedMetric] = []
    promoted_row_ids: set[str] = set()
    for (metric_key, year), members in sorted(promo_members.items()):
        if not members:
            continue
        # Deterministic primary for unit/currency/scale when multi-source agree on value.
        members.sort(
            key=lambda m: (
                caption_plainness(m.caption, metric_key),
                bool(m.currency),
                bool(m.scale),
                bool(m.unit),
                _proof_rank(m.proof_level),
                m.source_name,
                m.row_id,
            ),
            reverse=True,
        )
        sources = sorted({m.source_name for m in members})
        captions = sorted({m.caption for m in members})
        primary = members[0]
        # Additive within-doc: sum distinct component captions (labour COGS + SG&A).
        if (
            metric_key in _ADDITIVE_WITHIN_DOC
            and len(sources) == 1
            and len({_value_bucket(m.value) for m in members}) > 1
        ):
            # One row per caption — avoid double-counting identical peers.
            by_cap: dict[str, ExtractedRow] = {}
            for m in members:
                by_cap.setdefault(m.caption, m)
            value = sum(float(m.value) for m in by_cap.values())
            checks_extra = ["additive_components"]
        else:
            value = primary.value
            checks_extra = []
        # Multi-source agree bumps to at least L3 on the promoted artifact.
        level = primary.proof_level or ProofLevel.L2
        if len(sources) >= 2 and _proof_rank(level) < _proof_rank(ProofLevel.L3):
            level = ProofLevel.L3
        checks = list(primary.proof_checks or [])
        if len(sources) >= 2 and "cross_document" not in checks:
            checks.append("cross_document")
        for c in checks_extra:
            if c not in checks:
                checks.append(c)
        promoted.append(
            PromotedMetric(
                metric_key=metric_key,
                fiscal_year=year,
                value=value,
                unit=primary.unit,
                currency=primary.currency,
                scale=primary.scale,
                row_id=primary.row_id,
                sources=sources,
                captions=captions,
                auto=True,
                scope=primary.scope,
                statement=primary.statement,
                period_end=primary.period_end,
                period_length=primary.period_length,
                source_basis=primary.source_basis,
                source_ref=primary.source_ref,
                proof_level=level,
                proof_checks=checks,
            )
        )
        for m in members:
            promoted_row_ids.add(m.row_id)

    out: list[ExtractedRow] = []
    for row in rows:
        # Always copy so callers never see shared mutable status objects.
        if row.status == RowStatus.DROPPED:
            out.append(row.model_copy(update={"status": RowStatus.DROPPED}))
            continue
        if row.row_id in fail_ids or row.row_id in hold_ids:
            out.append(row.model_copy(update={"status": RowStatus.HELD_OUT}))
            continue
        if row.row_id in promoted_row_ids:
            out.append(row.model_copy(update={"status": RowStatus.PROMOTED}))
            continue
        if row.metric_key is None:
            out.append(row.model_copy(update={"status": RowStatus.HELD_OUT}))
            continue
        out.append(row.model_copy(update={"status": RowStatus.CANDIDATE}))

    return out, promoted


def unmapped_issues_from_rows(rows: list[ExtractedRow]) -> list[dict[str, Any]]:
    """Surface statement lines that CoA dual-map could not assign (S4-9)."""
    from agetic_cdd_api.services_databook_blocks import is_total_caption

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if row.status == RowStatus.DROPPED or row.metric_key is not None:
            continue
        if is_total_caption(row.caption):
            continue
        key = row.row_id
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "kind": "unmapped",
                "metric": row.caption,
                "fiscal_year": row.fiscal_year,
                "value": row.value,
                "source": row.source_name,
                "caption": row.caption,
                "row_id": row.row_id,
                "statement": row.statement,
                "reason": "No CoA dual-agree map (section gate or caption mismatch)",
            }
        )
    return out


def assumption_issues_from_rows(rows: list[ExtractedRow]) -> list[dict[str, Any]]:
    """DiligenceIQ-compatible ``assumed`` items for Data Quality Review."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row.assumption or row.status == RowStatus.DROPPED:
            continue
        reason_parts: list[str] = []
        # Structured reason flags — never gate on serialized prose substrings.
        flags: set[str] = set()
        if row.currency_source in {"caption", "map"} and row.currency:
            reason_parts.append(
                f"currency '{row.currency}' from {row.currency_source}, not table header"
            )
            flags.add("currency_inferred")
        if row.scale_source in {"caption", "map"} and row.scale:
            reason_parts.append(
                f"scale '{row.scale}' from {row.scale_source}, not table header"
            )
            flags.add("scale_inferred")
        if row.currency is None and row.metric_family == MetricFamily.REVENUE:
            if row.scale and not reason_parts:
                reason_parts.append(
                    f"scale inferred from unit '{row.scale}', not stated in the value"
                )
                flags.add("scale_inferred")
            elif row.currency is None:
                reason_parts.append("no currency stated; not converted")
                flags.add("currency_missing")
        elif row.currency is None and not reason_parts:
            reason_parts.append("no currency stated; not converted")
            flags.add("currency_missing")
        if row.unit is None and row.metric_family not in {
            MetricFamily.SHARE,
            MetricFamily.GROWTH,
            MetricFamily.RETENTION,
            MetricFamily.MARGIN,
        }:
            # "currency_missing" must not suppress a unit gap; only inferred unit/currency
            # or scale already explained should skip the combined fallback.
            if not flags.intersection({"currency_inferred", "scale_inferred", "unit_fallback"}):
                reason_parts.append("unit/currency inferred or missing")
                flags.add("unit_fallback")
        reason = "; ".join(reason_parts) if reason_parts else "assumption made during extract or mapping"
        out.append(
            {
                "kind": "assumed",
                "metric": row.metric_key or row.caption,
                "fiscal_year": row.fiscal_year,
                "value": row.value,
                "source": row.source_name,
                "caption": row.caption,
                "row_id": row.row_id,
                "unit": row.unit,
                "currency": row.currency,
                "scale": row.scale,
                "reason": reason,
            }
        )
    return out


def build_data_quality_items(
    *,
    dropped: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    failed_checks: list[dict[str, Any]] | None = None,
    assumed: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return _dedupe_issues(
        [*dropped, *conflicts, *(failed_checks or []), *(assumed or [])]
    )
