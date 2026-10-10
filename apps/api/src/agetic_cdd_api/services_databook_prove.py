"""Prove checks + L0–L4 proof levels (Phase 5 / S5 / AC-8).

Checks act: failed arithmetic / forecast contamination / BS imbalance / roll-forwards
hold rows. Auto-promote and proven release require ``min_proof_level`` (default L2).

G5 adds equity roll, cash/CF roll, NI cross-statement, notes-vs-statements, and
draft→final bridge (S5-03…07) with FailureClass tagging (S5-13).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from agetic_cdd_api.services_databook_models import (
    PROOF_LEVEL_RANK,
    ActualForecast,
    DealDatabookParams,
    ExtractedRow,
    FailureClass,
    NoteFact,
    ProofLevel,
    RowStatus,
    SourceBasis,
    StatementBlock,
)

_NI_KEYS = frozenset(
    {
        "net_income",
        "profit_for_period",
        "profit_after_tax",
        "net_profit",
    }
)
_FINAL_BASES = frozenset({SourceBasis.AUDITED, SourceBasis.MANAGEMENT})
_DRAFT_BASES = frozenset({SourceBasis.DRAFT})


def parse_min_proof_level(raw: str | ProofLevel | None) -> ProofLevel:
    if isinstance(raw, ProofLevel):
        return raw
    text = (raw or "L2").strip().upper()
    try:
        return ProofLevel(text)
    except ValueError:
        return ProofLevel.L2


def meets_min_proof(level: ProofLevel | None, minimum: ProofLevel) -> bool:
    if level is None:
        return False
    return PROOF_LEVEL_RANK[level] >= PROOF_LEVEL_RANK[minimum]


def _ties(a: float, b: float, *, rel_tol: float) -> bool:
    delta = abs(a - b)
    if delta <= 1.0 + 1e-9:
        return True
    return (delta / max(abs(b), 1e-9)) <= rel_tol


def _material(rows: Iterable[ExtractedRow]) -> list[ExtractedRow]:
    return [
        r
        for r in rows
        if r.status != RowStatus.DROPPED and r.metric_key and r.fiscal_year is not None
    ]


def _ladder(row: ExtractedRow) -> int:
    if row.ladder_score is not None:
        return int(row.ladder_score)
    if row.source_basis is not None:
        from agetic_cdd_api.services_databook_models import SOURCE_LADDER_SCORE

        return int(SOURCE_LADDER_SCORE.get(row.source_basis, 50))
    return 50


def _pick_best(candidates: list[ExtractedRow]) -> ExtractedRow | None:
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda r: (_ladder(r), abs(float(r.value)), r.row_id),
    )


def _index_by_metric_year(
    rows: list[ExtractedRow],
) -> dict[tuple[str, int], list[ExtractedRow]]:
    out: dict[tuple[str, int], list[ExtractedRow]] = defaultdict(list)
    for row in _material(rows):
        out[(str(row.metric_key), int(row.fiscal_year))].append(row)
    return out


def _best_metric(
    index: dict[tuple[str, int], list[ExtractedRow]],
    metric: str,
    fy: int,
) -> ExtractedRow | None:
    return _pick_best(index.get((metric, fy)) or [])


def _best_ni(
    index: dict[tuple[str, int], list[ExtractedRow]],
    fy: int,
) -> ExtractedRow | None:
    cands: list[ExtractedRow] = []
    for key in _NI_KEYS:
        cands.extend(index.get((key, fy)) or [])
    return _pick_best(cands)


def check_balance_sheet(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[dict[str, Any]], set[str]]:
    """S5-02 — when total assets / liabilities / equity exist for a FY, they must balance."""
    by_fy: dict[int, dict[str, ExtractedRow]] = defaultdict(dict)
    for row in rows:
        if row.status == RowStatus.DROPPED or row.fiscal_year is None or not row.metric_key:
            continue
        if row.metric_key not in {"total_assets", "total_liabilities", "total_equity"}:
            continue
        if row.coa_section and row.coa_section != "balance_sheet":
            if row.statement and row.statement != "balance_sheet":
                continue
        by_fy[int(row.fiscal_year)][row.metric_key] = row

    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()
    rel_tol = max(float(params.block_tie_rel_tol), 0.0)

    for fy, parts in sorted(by_fy.items()):
        if not {"total_assets", "total_liabilities", "total_equity"} <= set(parts):
            continue
        assets = parts["total_assets"]
        liab = parts["total_liabilities"]
        equity = parts["total_equity"]
        rhs = liab.value + equity.value
        ok = _ties(assets.value, rhs, rel_tol=rel_tol)
        if ok:
            continue
        for r in (assets, liab, equity):
            hold_ids.add(r.row_id)
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "bs_balance",
                "failure_class": FailureClass.SOURCE.value,
                "fiscal_year": fy,
                "metric": "total_assets",
                "value": assets.value,
                "expected": rhs,
                "sources": [assets.source_name, liab.source_name, equity.source_name],
                "row_ids": [assets.row_id, liab.row_id, equity.row_id],
                "reason": "Balance sheet does not balance (assets ≠ liabilities + equity)",
            }
        )
    return issues, hold_ids


def check_equity_roll_forward(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[dict[str, Any]], set[str]]:
    """S5-03 — equity_end ≈ equity_begin + NI − dividends (when components present)."""
    index = _index_by_metric_year(rows)
    years = sorted({fy for (_mk, fy) in index})
    rel_tol = max(float(params.block_tie_rel_tol), 0.0)
    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()

    for fy in years:
        end = _best_metric(index, "total_equity", fy)
        begin = _best_metric(index, "total_equity", fy - 1)
        ni = _best_ni(index, fy)
        if end is None or begin is None or ni is None:
            continue
        div = _best_metric(index, "dividends", fy)
        div_val = float(div.value) if div is not None else 0.0
        expected = float(begin.value) + float(ni.value) - div_val
        if _ties(float(end.value), expected, rel_tol=rel_tol):
            continue
        involved = [begin, end, ni] + ([div] if div is not None else [])
        for r in involved:
            hold_ids.add(r.row_id)
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "equity_roll",
                "failure_class": FailureClass.SOURCE.value,
                "fiscal_year": fy,
                "metric": "total_equity",
                "value": end.value,
                "expected": expected,
                "components": {
                    "equity_begin": begin.value,
                    "net_income": ni.value,
                    "dividends": div_val,
                },
                "sources": [r.source_name for r in involved],
                "row_ids": [r.row_id for r in involved],
                "reason": (
                    "Equity roll-forward failed "
                    f"(end {end.value} ≠ begin {begin.value} + NI {ni.value}"
                    f"{f' − div {div_val}' if div is not None else ''})"
                ),
            }
        )
    return issues, hold_ids


def check_cash_roll(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[dict[str, Any]], set[str]]:
    """S5-04 — cash_end ≈ cash_begin + net_change_in_cash when all three exist."""
    index = _index_by_metric_year(rows)
    years = sorted({fy for (_mk, fy) in index})
    rel_tol = max(float(params.block_tie_rel_tol), 0.0)
    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()

    for fy in years:
        end = _best_metric(index, "cash", fy)
        begin = _best_metric(index, "cash", fy - 1)
        change = _best_metric(index, "net_change_in_cash", fy)
        if end is None or begin is None or change is None:
            continue
        expected = float(begin.value) + float(change.value)
        if _ties(float(end.value), expected, rel_tol=rel_tol):
            continue
        for r in (begin, end, change):
            hold_ids.add(r.row_id)
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "cash_roll",
                "failure_class": FailureClass.SOURCE.value,
                "fiscal_year": fy,
                "metric": "cash",
                "value": end.value,
                "expected": expected,
                "components": {
                    "cash_begin": begin.value,
                    "net_change_in_cash": change.value,
                },
                "sources": [begin.source_name, end.source_name, change.source_name],
                "row_ids": [begin.row_id, end.row_id, change.row_id],
                "reason": (
                    "Cash / CF roll failed "
                    f"(cash {end.value} ≠ prior {begin.value} + change {change.value})"
                ),
            }
        )
    return issues, hold_ids


def check_ni_cross_statement(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[dict[str, Any]], set[str]]:
    """S5-05 — NI / profit figures for the same FY must agree across statements."""
    by_fy: dict[int, list[ExtractedRow]] = defaultdict(list)
    for row in _material(rows):
        if row.metric_key in _NI_KEYS:
            by_fy[int(row.fiscal_year)].append(row)

    rel_tol = max(float(params.block_tie_rel_tol), 0.0)
    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()

    for fy, cands in sorted(by_fy.items()):
        best = _pick_best(cands)
        if best is None or len(cands) < 2:
            continue
        values = {round(float(r.value), 6) for r in cands}
        if len(values) < 2:
            continue
        disagree = [
            r for r in cands if not _ties(float(r.value), float(best.value), rel_tol=rel_tol)
        ]
        if not disagree:
            continue
        for r in cands:
            hold_ids.add(r.row_id)
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "ni_cross",
                "failure_class": FailureClass.SOURCE.value,
                "fiscal_year": fy,
                "metric": "net_income",
                "value": best.value,
                "values": sorted(float(v) for v in values),
                "sources": [r.source_name for r in cands],
                "row_ids": [r.row_id for r in cands],
                "reason": "Net income / profit disagrees across statements for the same FY",
            }
        )
    return issues, hold_ids


def check_notes_vs_statements(
    rows: list[ExtractedRow],
    notes: list[NoteFact] | None,
    *,
    params: DealDatabookParams,
) -> tuple[list[dict[str, Any]], set[str]]:
    """S5-06 lite — note figures that map to a statement metric must agree."""
    if not notes:
        return [], set()
    index = _index_by_metric_year(rows)
    rel_tol = max(float(params.block_tie_rel_tol), 0.0)
    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()

    for note in notes:
        if not note.metric_key or note.fiscal_year is None:
            continue
        mk = str(note.metric_key)
        fy = int(note.fiscal_year)
        peers = list(index.get((mk, fy)) or [])
        if mk in _NI_KEYS:
            for alt in _NI_KEYS:
                if alt == mk:
                    continue
                peers.extend(index.get((alt, fy)) or [])
        if not peers:
            continue
        best = _pick_best(peers)
        if best is None:
            continue
        if _ties(float(note.value), float(best.value), rel_tol=rel_tol):
            continue
        for r in peers:
            hold_ids.add(r.row_id)
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "notes_vs_statements",
                "failure_class": FailureClass.SOURCE.value,
                "fiscal_year": fy,
                "metric": mk,
                "value": best.value,
                "expected": note.value,
                "note_id": note.note_id,
                "note_source": note.source_name,
                "sources": [best.source_name, note.source_name],
                "row_ids": [r.row_id for r in peers],
                "reason": (
                    f"Note figure {note.value} disagrees with statement {best.value} "
                    f"for {mk} FY{fy}"
                ),
            }
        )
    return issues, hold_ids


def check_draft_to_final(
    rows: list[ExtractedRow],
    *,
    params: DealDatabookParams,
) -> tuple[list[dict[str, Any]], set[str]]:
    """S5-07 — draft vs audited/management final for the same metric×year must bridge.

    On disagreement, hold the **draft** rows so they cannot silent-promote over final.
    """
    rel_tol = max(float(params.block_tie_rel_tol), 0.0)
    buckets: dict[tuple[str, int], list[ExtractedRow]] = defaultdict(list)
    for row in _material(rows):
        buckets[(str(row.metric_key), int(row.fiscal_year))].append(row)

    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()

    for (mk, fy), cands in sorted(buckets.items()):
        drafts = [r for r in cands if r.source_basis in _DRAFT_BASES]
        finals = [r for r in cands if r.source_basis in _FINAL_BASES]
        if not drafts or not finals:
            continue
        final = _pick_best(finals)
        if final is None:
            continue
        mismatched = [
            d
            for d in drafts
            if not _ties(float(d.value), float(final.value), rel_tol=rel_tol)
        ]
        if not mismatched:
            continue
        for d in mismatched:
            hold_ids.add(d.row_id)
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "draft_to_final",
                "failure_class": FailureClass.DEFINITION.value,
                "fiscal_year": fy,
                "metric": mk,
                "value": mismatched[0].value,
                "expected": final.value,
                "sources": [*(d.source_name for d in mismatched), final.source_name],
                "row_ids": [*(d.row_id for d in mismatched), final.row_id],
                "reason": (
                    f"Draft→final bridge: draft {mismatched[0].value} ≠ "
                    f"{final.source_basis.value if final.source_basis else 'final'} "
                    f"{final.value} for {mk} FY{fy}"
                ),
            }
        )
    return issues, hold_ids


def check_forecast_isolation(
    rows: list[ExtractedRow],
) -> tuple[list[dict[str, Any]], set[str]]:
    """S5-09 — forecast-tagged rows must not enter history promote path."""
    issues: list[dict[str, Any]] = []
    hold_ids: set[str] = set()
    for row in rows:
        if row.status == RowStatus.DROPPED:
            continue
        if row.actual_forecast != ActualForecast.FORECAST:
            continue
        if not row.metric_key:
            continue
        hold_ids.add(row.row_id)
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "forecast_isolation",
                "failure_class": FailureClass.DEFINITION.value,
                "fiscal_year": row.fiscal_year,
                "metric": row.metric_key,
                "value": row.value,
                "source": row.source_name,
                "row_id": row.row_id,
                "reason": "Forecast-tagged evidence held out of history",
            }
        )
    return issues, hold_ids


def check_sign_sense(
    rows: list[ExtractedRow],
) -> list[dict[str, Any]]:
    """S5-10 lite — unusual signs (e.g. large negative cash) flagged, not held."""
    issues: list[dict[str, Any]] = []
    for row in rows:
        if row.status == RowStatus.DROPPED or not row.metric_key:
            continue
        if row.metric_key == "cash" and row.value < 0:
            issues.append(
                {
                    "kind": "prove_check",
                    "check_id": "sign_sense",
                    "failure_class": FailureClass.DEFINITION.value,
                    "fiscal_year": row.fiscal_year,
                    "metric": row.metric_key,
                    "value": row.value,
                    "source": row.source_name,
                    "row_id": row.row_id,
                    "reason": "Cash is negative — unusual sign for BS cash line",
                }
            )
    return issues


def _multi_source_peers(rows: list[ExtractedRow]) -> dict[str, int]:
    """row_id → count of distinct sources agreeing on same metric+year+value."""
    buckets: dict[tuple[str, int, float], set[str]] = defaultdict(set)
    members: dict[tuple[str, int, float], list[str]] = defaultdict(list)
    for row in rows:
        if row.status == RowStatus.DROPPED or not row.metric_key or row.fiscal_year is None:
            continue
        key = (row.metric_key, int(row.fiscal_year), round(row.value, 6))
        buckets[key].add(row.source_name)
        members[key].append(row.row_id)

    out: dict[str, int] = {}
    for key, sources in buckets.items():
        n = len(sources)
        for rid in members[key]:
            out[rid] = max(out.get(rid, 0), n)
    return out


def assign_proof_levels(
    rows: list[ExtractedRow],
    *,
    block_fail_ids: set[str],
    hold_ids: set[str],
    blocks: list[StatementBlock] | None = None,
) -> list[ExtractedRow]:
    """Stamp ``proof_level`` + ``proof_checks`` on each row (AC-8)."""
    peers = _multi_source_peers(rows)
    passed_block_ids = {
        b.block_id for b in (blocks or []) if b.outcome == "pass"
    }
    out: list[ExtractedRow] = []
    for row in rows:
        checks: list[str] = []
        if row.status == RowStatus.DROPPED:
            level = ProofLevel.L0
        elif row.metric_key is None:
            level = ProofLevel.L0
        elif row.actual_forecast == ActualForecast.FORECAST:
            level = ProofLevel.L0
        elif row.row_id in block_fail_ids or row.row_id in hold_ids:
            level = ProofLevel.L1
        elif row.assumption or row.dual_agree is False or row.read_dual_agree is False:
            level = ProofLevel.L1
            if row.read_dual_agree is False:
                checks.append("read_dual_disagree")
        elif row.derived:
            level = ProofLevel.L1
            checks.append("mapped_derived")
        else:
            checks.append("mapped")
            if row.dual_agree:
                checks.append("dual_agree")
            if row.read_dual_agree:
                checks.append("read_dual_agree")
            if not row.assumption:
                checks.append("no_assumption")
            if row.block_id and row.block_id in passed_block_ids:
                checks.append("subtotal_tie")
            checks.append("unique_or_clear")
            level = ProofLevel.L2
            if peers.get(row.row_id, 1) >= 2:
                checks.append("cross_document")
                level = ProofLevel.L3
            if row.status == RowStatus.VOUCHED:
                checks.append("hitl_vouch")
                level = ProofLevel.L4
        out.append(
            row.model_copy(
                update={
                    "proof_level": level,
                    "proof_checks": checks,
                }
            )
        )
    return out


def run_prove_pipeline(
    rows: list[ExtractedRow],
    *,
    blocks: list[StatementBlock],
    block_fail_ids: set[str],
    hold_ids: set[str],
    params: DealDatabookParams,
    notes: list[NoteFact] | None = None,
) -> tuple[list[ExtractedRow], set[str], list[dict[str, Any]]]:
    """Run prove checks, merge holds, assign proof levels.

    Returns (annotated_rows, extra_hold_ids, prove_issues).
    """
    issues: list[dict[str, Any]] = []
    extra_holds: set[str] = set()

    for runner in (
        lambda: check_balance_sheet(rows, params=params),
        lambda: check_equity_roll_forward(rows, params=params),
        lambda: check_cash_roll(rows, params=params),
        lambda: check_ni_cross_statement(rows, params=params),
        lambda: check_notes_vs_statements(rows, notes, params=params),
        lambda: check_draft_to_final(rows, params=params),
        lambda: check_forecast_isolation(rows),
    ):
        check_issues, check_holds = runner()
        issues.extend(check_issues)
        extra_holds |= check_holds

    issues.extend(check_sign_sense(rows))

    for block in blocks:
        if block.outcome != "fail":
            continue
        issues.append(
            {
                "kind": "prove_check",
                "check_id": "subtotal_tie",
                "failure_class": FailureClass.SOURCE.value,
                "fiscal_year": block.fiscal_year,
                "block_id": block.block_id,
                "printed_subtotal": block.printed_subtotal,
                "computed_sum": block.computed_sum,
                "row_ids": list(block.line_row_ids),
                "source": block.source_name,
                "reason": "Statement block does not tie to the printed subtotal",
            }
        )

    combined_holds = set(hold_ids) | set(block_fail_ids) | extra_holds
    annotated = assign_proof_levels(
        rows,
        block_fail_ids=block_fail_ids,
        hold_ids=combined_holds,
        blocks=blocks,
    )
    return annotated, extra_holds, issues
