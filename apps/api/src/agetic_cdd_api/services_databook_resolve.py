"""Series sanity, conflict detection, and metric promotion rules."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Any

from agetic_cdd_api.services_databook_map import caption_plainness, display_metric_label, same_family_allowed
from agetic_cdd_api.services_databook_models import (
    DEFAULT_CONFLICT_RULE,
    SERIES_DROP_REASON,
    ConflictCandidate,
    DataQualityConflict,
    DataQualityDropped,
    DealDatabookParams,
    ExtractedRow,
    MetricFamily,
    PromotedMetric,
    RowStatus,
)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def apply_series_drops(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[ExtractedRow], list[dict[str, Any]]]:
    """Drop values orders of magnitude below the metric series centre."""
    by_metric: dict[str, list[ExtractedRow]] = defaultdict(list)
    for row in rows:
        if row.metric_key and row.fiscal_year is not None:
            by_metric[row.metric_key].append(row)

    dropped_issues: list[dict[str, Any]] = []
    drop_ids: set[str] = set()
    ratio = max(params.series_magnitude_ratio, 2.0)

    for metric_key, group in by_metric.items():
        values = [abs(r.value) for r in group if r.value != 0]
        if len(values) < 3:
            continue
        centre = abs(_median(values))
        if centre == 0:
            continue
        for row in group:
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
            row = row.model_copy(update={"status": RowStatus.DROPPED})
        out.append(row)
    return out, dropped_issues


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
                    round(float(c.get("value")), 6)
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
                item.get("row_id") or item.get("metric"),
                item.get("fiscal_year"),
                item.get("value"),
                item.get("reason"),
            )
        else:
            key = ("raw", json.dumps(item, sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def detect_conflicts(
    rows: list[ExtractedRow],
) -> tuple[list[dict[str, Any]], set[str]]:
    """
    Group by (metric_key, fiscal_year). Only same-family captions may compete.

    Auto-chosen is a proposal only — rows stay held_out when conflicted.
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
    for row in active:
        source_totals[row.source_name] += 1
        if row.metric_key:
            source_metric_facts[(row.source_name, row.metric_key)] += 1

    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()

    for (metric_key, year), group in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        value_buckets: dict[float, list[ExtractedRow]] = defaultdict(list)
        for row in group:
            value_buckets[round(row.value, 6)].append(row)

        if len(value_buckets) < 2:
            continue

        candidates: list[ConflictCandidate] = []
        for value, members in value_buckets.items():
            sources = sorted({m.source_name for m in members})
            captions = sorted({m.caption for m in members})
            best = max(
                members,
                key=lambda m: (
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
            return (
                c.stated_by,
                c.source_facts,
                c.source_total_facts,
                plain,
                -abs(c.value - centre),
                round(c.value, 6),
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
        scope = "across documents" if len(scopes) > 1 else "within one document"
        label = display_metric_label(metric_key, group[0].caption)
        issues.append(
            DataQualityConflict(
                metric=label,
                fiscal_year=year,
                chosen=winner.value,
                candidates=candidates,
                scope=scope,  # type: ignore[arg-type]
                rule=DEFAULT_CONFLICT_RULE,
            ).model_dump(mode="json")
        )
        for m in group:
            hold_ids.add(m.row_id)

    return _dedupe_issues(issues), hold_ids


def apply_statuses_and_promote(
    rows: list[ExtractedRow],
    *,
    hold_ids: set[str],
    block_fail_ids: set[str] | None = None,
) -> tuple[list[ExtractedRow], list[PromotedMetric]]:
    """
    Auto-promote only unique+mapped+no-assumption rows that are not held out or dropped.

    Rows in failed statement blocks are always held out (never silent-promote).
    Identical values from multiple sources promote together (merged sources).
    """
    fail_ids = block_fail_ids or set()
    combined_hold = set(hold_ids) | fail_ids

    groups: dict[tuple[str, int], set[float]] = defaultdict(set)
    for row in rows:
        if (
            row.status == RowStatus.DROPPED
            or row.row_id in fail_ids
            or not row.metric_key
            or row.fiscal_year is None
            or not same_family_allowed(row.caption, row.metric_key)
        ):
            continue
        groups[(row.metric_key, row.fiscal_year)].add(round(row.value, 6))

    # Collect promotable rows by metric+year
    promo_members: dict[tuple[str, int], list[ExtractedRow]] = defaultdict(list)
    for row in rows:
        if row.status == RowStatus.DROPPED or row.row_id in combined_hold:
            continue
        if (
            row.metric_key
            and row.fiscal_year is not None
            and not row.assumption
            and same_family_allowed(row.caption, row.metric_key)
            and len(groups.get((row.metric_key, row.fiscal_year), set())) == 1
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
                m.source_name,
                m.row_id,
            ),
            reverse=True,
        )
        sources = sorted({m.source_name for m in members})
        captions = sorted({m.caption for m in members})
        primary = members[0]
        promoted.append(
            PromotedMetric(
                metric_key=metric_key,
                fiscal_year=year,
                value=primary.value,
                unit=primary.unit,
                currency=primary.currency,
                scale=primary.scale,
                row_id=primary.row_id,
                sources=sources,
                captions=captions,
                auto=True,
            )
        )
        for m in members:
            promoted_row_ids.add(m.row_id)

    out: list[ExtractedRow] = []
    for row in rows:
        if row.status == RowStatus.DROPPED:
            out.append(row)
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


def assumption_issues_from_rows(rows: list[ExtractedRow]) -> list[dict[str, Any]]:
    """DiligenceIQ-compatible ``assumed`` items for Data Quality Review."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row.assumption or row.status == RowStatus.DROPPED:
            continue
        reason_parts: list[str] = []
        if row.currency is None and row.metric_family == MetricFamily.REVENUE:
            if row.scale:
                reason_parts.append(
                    f"scale inferred from unit '{row.scale}', not stated in the value"
                )
            else:
                reason_parts.append("no currency stated; not converted")
        elif row.currency is None:
            reason_parts.append("no currency stated; not converted")
        if row.unit is None and row.metric_family not in {MetricFamily.SHARE, MetricFamily.GROWTH, MetricFamily.RETENTION, MetricFamily.MARGIN}:
            if "currency" not in " ".join(reason_parts):
                reason_parts.append("unit/currency inferred or missing")
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
