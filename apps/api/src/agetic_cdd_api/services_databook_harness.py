"""Phase 7 — databook ship harness (H-1…H-7, AC-3…AC-6).

Runs golden databooks, curated trap regressions, contamination scans, and
bit-identical re-runs. The ship gate exits non-zero on any failure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_databook_blocks import annotate_and_detect_blocks, reconcile_blocks
from agetic_cdd_api.services_databook_classify import (
    allows_history_extract,
    classify_entry,
    is_forecast_period_header,
)
from agetic_cdd_api.services_databook_extract import (
    _parse_number,
    is_implausible_money_magnitude,
    is_year_as_value,
    notes_from_prose,
    rows_from_table,
)
from agetic_cdd_api.services_databook_map import (
    caption_plainness,
    map_caption,
    same_family_allowed,
)
from agetic_cdd_api.services_databook_models import (
    DealDatabookParams,
    ExtractedRow,
    MetricFamily,
    PromotedMetric,
    ReleaseCellStatus,
    ReleasedCell,
    RowStatus,
    SourceBasis,
    TrapRecord,
)
from agetic_cdd_api.services_databook_prove import run_prove_pipeline
from agetic_cdd_api.services_databook_resolve import (
    apply_scale_step_guard,
    apply_series_drops,
    apply_statuses_and_promote,
    detect_conflicts,
)
from agetic_cdd_api.services_databook_utils import canonicalize_metric_key

logger = logging.getLogger(__name__)

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "databook"
)
_FLOAT_TOL = 1e-6
_STOP_TOKENS = frozenset(
    {"the", "and", "ltd", "limited", "inc", "plc", "corp", "company", "deal"}
)


def fixture_root() -> Path:
    return _FIXTURE_ROOT


def goldens_dir() -> Path:
    return fixture_root() / "goldens"


def traps_path() -> Path:
    return fixture_root() / "traps.jsonl"


def _floats_close(a: float, b: float, *, tol: float = _FLOAT_TOL) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)


def _float_in(target: float, collection: set[float] | list[float], *, tol: float = _FLOAT_TOL) -> bool:
    """Membership for floats without binary-representation false negatives."""
    t = float(target)
    return any(_floats_close(t, x, tol=tol) for x in collection)


def _truncate(msg: str, limit: int = 240) -> str:
    text = str(msg).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# Pipeline (library-free — documents in memory)
# ---------------------------------------------------------------------------


def _deal_tokens_from_golden(golden: dict[str, Any]) -> set[str]:
    """Mirror classify.deal_identity_tokens without requiring a Deal ORM row."""
    tokens: set[str] = set()
    for raw in (
        golden.get("company"),
        golden.get("deal_name"),
        golden.get("deal_slug"),
    ):
        if not raw:
            continue
        for part in re.findall(r"[a-zA-Z]{3,}", str(raw).lower()):
            if part not in _STOP_TOKENS:
                tokens.add(part)
    return tokens


def _coverage_years_from_golden(golden: dict[str, Any]) -> set[int]:
    """Prefer explicit coverage_years, else years cited in expected_cells."""
    years: set[int] = set()
    for y in golden.get("coverage_years") or []:
        try:
            years.add(int(y))
        except (TypeError, ValueError):
            continue
    for exp in golden.get("expected_cells") or []:
        if not isinstance(exp, dict) or exp.get("fiscal_year") is None:
            continue
        try:
            years.add(int(exp["fiscal_year"]))
        except (TypeError, ValueError):
            continue
    return years


def count_golden_figures(golden: dict[str, Any]) -> int:
    """Count numeric cells in history documents (H-1 figure budget; excludes forbid_sources)."""
    forbid = {str(x) for x in (golden.get("forbid_sources") or [])}
    n = 0
    for doc in golden.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        if str(doc.get("filename") or "") in forbid:
            continue
        for table in doc.get("tables") or []:
            if not isinstance(table, dict):
                continue
            rows = table.get("rows") or []
            if not isinstance(rows, list) or len(rows) < 2:
                continue
            for row in rows[1:]:
                if not isinstance(row, list) or len(row) < 2:
                    continue
                for cell in row[1:]:
                    if _parse_number(str(cell)) is not None:
                        n += 1
    return n


# Default H-1 size targets when golden omits expected_min_figures.
_DEFAULT_MIN_FIGURES: dict[str, int] = {
    "deal_a": 195,
    "deal_b": 252,
}

def _filter_history_docs(
    documents: list[dict[str, Any]],
    *,
    deal_tokens: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split documents into history-extractable vs set-aside/forecast."""
    history: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        if doc.get("set_aside") or doc.get("forbid_history"):
            blocked.append(doc)
            continue
        entry = classify_entry(
            {
                "filename": str(doc.get("filename") or ""),
                "library_stem": str(doc.get("library_stem") or doc.get("filename") or ""),
                "excerpt": str(doc.get("excerpt") or ""),
                "cdl_category": str(doc.get("cdl_category") or ""),
            },
            deal_tokens=deal_tokens,
        )
        stamped = {**doc, "_register": entry}
        if allows_history_extract(entry):
            history.append(stamped)
        else:
            blocked.append(stamped)
    return history, blocked


def run_extract_pipeline(
    documents: list[dict[str, Any]],
    *,
    params: DealDatabookParams | None = None,
    deal_tokens: set[str] | None = None,
) -> dict[str, Any]:
    """Extract → block → series → scale → conflict → prove → promote.

    Returns rows, promoted, issues, blocked docs, and synthesised release cells.
    """
    params = params or DealDatabookParams()
    tokens = deal_tokens or set()
    history, blocked = _filter_history_docs(documents, deal_tokens=tokens)

    rows: list[ExtractedRow] = []
    raw_blocks = []
    seen: set[str] = set()
    for doc in history:
        filename = str(doc.get("filename") or "doc.pdf")
        doc_id = str(doc.get("library_stem") or filename)
        reg = doc.get("_register")
        for table in doc.get("tables") or []:
            if not isinstance(table, dict):
                continue
            table_rows, table_blocks = annotate_and_detect_blocks(
                source_name=filename,
                doc_id=doc_id,
                table=table,
                params=params,
            )
            for row in table_rows:
                if row.row_id in seen:
                    continue
                seen.add(row.row_id)
                if reg is not None:
                    row = row.model_copy(
                        update={
                            "source_basis": getattr(reg, "basis", None),
                            "ladder_score": getattr(reg, "ladder_score", None),
                            "actual_forecast": getattr(reg, "actual_forecast", None),
                        }
                    )
                rows.append(row)
            raw_blocks.extend(table_blocks)

    blocks, block_fail_ids, failed_check_issues = reconcile_blocks(raw_blocks, params=params)
    rows, dropped_issues = apply_series_drops(rows, params=params)
    rows, scale_hold_ids, scale_step_issues = apply_scale_step_guard(rows, params=params)
    conflict_issues, hold_ids = detect_conflicts(rows)
    hold_ids = set(hold_ids) | set(scale_hold_ids)

    rows, prove_holds, prove_issues = run_prove_pipeline(
        rows,
        blocks=blocks,
        block_fail_ids=block_fail_ids,
        hold_ids=hold_ids,
        params=params,
    )
    hold_ids = set(hold_ids) | set(prove_holds)

    rows, promoted = apply_statuses_and_promote(
        rows,
        hold_ids=hold_ids,
        block_fail_ids=block_fail_ids,
        params=params,
    )

    issues = (
        list(dropped_issues)
        + list(scale_step_issues)
        + list(conflict_issues)
        + list(failed_check_issues)
        + list(prove_issues)
    )
    cells = synthesize_release_cells(
        rows,
        promoted,
        conflict_issues,
        coverage_keys=None,
        sector_pack=(params.sector_pack or "generic"),
    )
    return {
        "rows": rows,
        "promoted": promoted,
        "blocks": blocks,
        "issues": issues,
        "conflict_issues": conflict_issues,
        "blocked_docs": blocked,
        "cells": cells,
    }


def _alt_dedupe_key(alt: dict[str, Any]) -> str:
    row_id = alt.get("row_id")
    if row_id:
        return f"row:{row_id}"
    sources = tuple(sorted(str(s) for s in (alt.get("sources") or [])))
    return f"v:{alt.get('value')}|{sources}"


def _merge_conflict_alternatives(
    existing: list[dict[str, Any]] | None,
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge non-chosen conflict candidates; dedupe by row_id or value+sources."""
    combined = list(existing or [])
    seen = {_alt_dedupe_key(a) for a in combined if isinstance(a, dict)}
    for alt in new:
        if not isinstance(alt, dict) or alt.get("chosen"):
            continue
        key = _alt_dedupe_key(alt)
        if key in seen:
            continue
        combined.append(alt)
        seen.add(key)
    return combined


def synthesize_release_cells(
    rows: list[ExtractedRow],
    promoted: list[PromotedMetric],
    conflict_issues: list[dict[str, Any]],
    *,
    coverage_keys: list[str] | None,
    coverage_years: set[int] | None = None,
    sector_pack: str = "generic",
) -> list[ReleasedCell]:
    """Build proven/doubtful/missing cells from a working pipeline result (H-1/AC-3)."""
    cells: dict[tuple[str, int], ReleasedCell] = {}

    for p in promoted:
        cells[(p.metric_key, p.fiscal_year)] = ReleasedCell(
            metric_key=p.metric_key,
            fiscal_year=p.fiscal_year,
            status=ReleaseCellStatus.PROVEN,
            value=p.value,
            unit=p.unit,
            currency=p.currency,
            scale=p.scale,
            row_id=p.row_id,
            sources=list(p.sources or []),
            captions=list(p.captions or []),
            scope=p.scope,
            statement=p.statement,
            period_end=p.period_end,
            period_length=p.period_length,
            source_basis=p.source_basis,
            proof_level=p.proof_level,
            proof_checks=list(p.proof_checks or []),
        )

    # Open conflicts without a promoted winner → doubtful with alternatives.
    # Never overwrite an existing cell (proven or already-captured doubtful).
    for issue in conflict_issues:
        metric = canonicalize_metric_key(issue.get("metric"))
        fy = issue.get("fiscal_year")
        if not metric or fy is None:
            continue
        key = (metric, int(fy))
        candidates = [c for c in (issue.get("candidates") or []) if isinstance(c, dict)]
        if key in cells:
            existing = cells[key]
            if existing.status == ReleaseCellStatus.PROVEN:
                new_alts = [c for c in candidates if not c.get("chosen")]
                merged = _merge_conflict_alternatives(existing.alternatives, new_alts)
                if merged != (existing.alternatives or []):
                    cells[key] = existing.model_copy(update={"alternatives": merged})
            continue
        chosen = next((c for c in candidates if c.get("chosen")), None)
        value = None
        if chosen is not None and chosen.get("value") is not None:
            try:
                value = float(chosen["value"])
            except (TypeError, ValueError):
                value = None
        cells[key] = ReleasedCell(
            metric_key=metric,
            fiscal_year=int(fy),
            status=ReleaseCellStatus.DOUBTFUL,
            value=value,
            sources=list((chosen or {}).get("sources") or []),
            captions=list((chosen or {}).get("captions") or []),
            reason="unresolved conflict",
            alternatives=candidates,
        )

    # Held-out / candidate material rows without promoted → doubtful
    for row in rows:
        if not row.metric_key or row.fiscal_year is None:
            continue
        if row.status == RowStatus.DROPPED:
            continue
        key = (row.metric_key, int(row.fiscal_year))
        if key in cells:
            continue
        if row.status in {RowStatus.HELD_OUT, RowStatus.CANDIDATE}:
            cells[key] = ReleasedCell(
                metric_key=row.metric_key,
                fiscal_year=int(row.fiscal_year),
                status=ReleaseCellStatus.DOUBTFUL,
                value=row.value,
                row_id=row.row_id,
                sources=[row.source_name],
                captions=[row.caption],
                reason="held out / unproven",
            )

    if coverage_keys:
        from agetic_cdd_api.services_databook_coverage import (
            fill_missing_coverage_cells,
            resolve_coverage_spec,
        )
        from agetic_cdd_api.services_databook_models import DealDatabookParams

        coverage = resolve_coverage_spec(
            params=DealDatabookParams(sector_pack=sector_pack or "generic"),
            coverage_keys=list(coverage_keys),
            coverage_years=coverage_years,
            cell_years={c.fiscal_year for c in cells.values()},
            source="golden",
        )
        filled, _requests = fill_missing_coverage_cells(
            list(cells.values()),
            coverage=coverage,
            assessment=None,
            attach_absent_doc_requests=False,
        )
        return filled

    return sorted(cells.values(), key=lambda c: (c.metric_key, c.fiscal_year))


def normalize_cells_for_compare(cells: list[ReleasedCell]) -> list[dict[str, Any]]:
    """Stable subset for bit-identical / golden compare (AC-6)."""
    out: list[dict[str, Any]] = []
    for c in cells:
        val: float | None = None
        if c.value is not None:
            val = round(float(c.value), 6)
            if val == 0.0:
                val = 0.0  # normalize -0.0 for cross-platform fingerprints
        out.append(
            {
                "metric_key": c.metric_key,
                "fiscal_year": c.fiscal_year,
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "value": val,
                "sources": sorted(c.sources or []),
                "captions": sorted(c.captions or []),
            }
        )
    out.sort(key=lambda x: (x["metric_key"], x["fiscal_year"], x["status"]))
    return out


def cells_fingerprint(cells: list[ReleasedCell]) -> str:
    payload = json.dumps(normalize_cells_for_compare(cells), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Golden runner (H-1, H-3, H-4, H-5, H-6)
# ---------------------------------------------------------------------------


@dataclass
class CheckFailure:
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoldenResult:
    golden_id: str
    ok: bool
    failures: list[CheckFailure] = field(default_factory=list)
    proven: int = 0
    doubtful: int = 0
    missing: int = 0
    fingerprint: str = ""
    figures: int = 0
    min_figures: int = 0


@lru_cache(maxsize=32)
def _load_golden_cached(path_str: str, mtime_ns: int, size_bytes: int) -> dict[str, Any]:
    path = Path(path_str)
    stat = path.stat()
    if stat.st_mtime_ns != mtime_ns or stat.st_size != size_bytes:
        _load_golden_cached.cache_clear()
        return _load_golden_cached(path_str, stat.st_mtime_ns, stat.st_size)
    return json.loads(path.read_text(encoding="utf-8"))


def load_golden(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    st = resolved.stat()
    return _load_golden_cached(str(resolved), st.st_mtime_ns, st.st_size)


def run_golden(golden: dict[str, Any] | Path) -> GoldenResult:
    """Execute one golden databook and assert ship-rule checks."""
    if isinstance(golden, Path):
        golden_path = golden
        golden = load_golden(golden_path)
        golden_id = str(golden.get("golden_id") or golden_path.stem)
    else:
        golden_id = str(golden.get("golden_id") or "golden")

    params = DealDatabookParams(
        sector_pack=str(golden.get("sector_pack") or "generic"),
        currency=str(golden.get("currency") or "INR"),
        scale=str(golden.get("scale") or "Cr"),
    )
    tokens = _deal_tokens_from_golden(golden)
    docs = list(golden.get("documents") or [])
    coverage = list(golden.get("coverage_keys") or [])
    coverage_years = _coverage_years_from_golden(golden)

    first = run_extract_pipeline(docs, params=params, deal_tokens=tokens)
    second = run_extract_pipeline(docs, params=params, deal_tokens=tokens)

    cells = synthesize_release_cells(
        first["rows"],
        first["promoted"],
        first["conflict_issues"],
        coverage_keys=coverage or None,
        coverage_years=coverage_years or None,
        sector_pack=params.sector_pack,
    )
    cells2 = synthesize_release_cells(
        second["rows"],
        second["promoted"],
        second["conflict_issues"],
        coverage_keys=coverage or None,
        coverage_years=coverage_years or None,
        sector_pack=params.sector_pack,
    )

    # G2 — expected-docs assessment + attach document requests on missing cells.
    from agetic_cdd_api.services_databook_classify import assess_expected_docs
    from agetic_cdd_api.services_databook_coverage import (
        fill_missing_coverage_cells,
        resolve_coverage_spec,
    )
    from agetic_cdd_api.services_databook_models import (
        FileRegister,
        FileRegisterEntry,
        FileRelevance,
        FileRole,
        SourceBasis,
    )

    entries: list[FileRegisterEntry] = []
    for doc in docs:
        if not isinstance(doc, dict) or not doc.get("filename"):
            continue
        name = str(doc["filename"])
        excerpt = str(doc.get("excerpt") or "")
        cdl = str(doc.get("cdl_category") or "")
        low = f"{name} {excerpt}".lower()
        basis = SourceBasis.UNKNOWN
        if "audit" in low or "financial statement" in low:
            basis = SourceBasis.AUDITED
        elif "management" in low:
            basis = SourceBasis.MANAGEMENT
        set_aside = name in set(golden.get("forbid_sources") or [])
        entries.append(
            FileRegisterEntry(
                filename=name,
                doc_id=name,
                relevance=FileRelevance.SET_ASIDE if set_aside else FileRelevance.IN_SCOPE,
                role=FileRole.SET_ASIDE if set_aside else FileRole.HISTORY_SOURCE,
                basis=basis,
                ladder_score=100 if basis == SourceBasis.AUDITED else 70,
                cdl_category=cdl or None,
                set_aside_reason="forbidden golden source" if set_aside else None,
            )
        )
    assessment = assess_expected_docs(
        FileRegister(
            deal_slug=str(golden.get("deal_slug") or golden_id),
            generated_at="1970-01-01T00:00:00Z",
            entries=entries,
        ),
        deal_slug=str(golden.get("deal_slug") or golden_id),
        profile=str(golden.get("sector_pack") or "generic"),
        generated_at="1970-01-01T00:00:00Z",
    )
    cov_spec = resolve_coverage_spec(
        params=params,
        coverage_keys=coverage or None,
        coverage_years=coverage_years or None,
        cell_years={c.fiscal_year for c in cells},
        source="golden",
    )
    cells, request_list = fill_missing_coverage_cells(
        cells, coverage=cov_spec, assessment=assessment
    )
    cells2, _ = fill_missing_coverage_cells(
        cells2, coverage=cov_spec, assessment=assessment
    )

    failures: list[CheckFailure] = []
    fp1 = cells_fingerprint(cells)
    fp2 = cells_fingerprint(cells2)
    if fp1 != fp2:
        failures.append(
            CheckFailure(
                code="H-6",
                message="bit-identical re-run failed",
                detail={"fp1": fp1, "fp2": fp2},
            )
        )

    # H-5 contamination: history rows must not come from forbidden sources
    forbid = set(golden.get("forbid_sources") or [])
    for row in first["rows"]:
        if row.status == RowStatus.DROPPED:
            continue
        if row.source_name in forbid:
            failures.append(
                CheckFailure(
                    code="H-5",
                    message=f"contamination: history row from {row.source_name}",
                    detail={"caption": row.caption, "metric_key": row.metric_key},
                )
            )

    blocked_names = {str(d.get("filename") or "") for d in first["blocked_docs"]}
    for name in forbid:
        if any(str(d.get("filename") or "") == name for d in docs) and name not in blocked_names:
            failures.append(
                CheckFailure(
                    code="H-5",
                    message=f"expected source gated from history: {name}",
                    detail={"blocked": sorted(blocked_names)},
                )
            )

    # H-1 / H-3 expected cells
    by_key = {(c.metric_key, c.fiscal_year): c for c in cells}
    for exp in golden.get("expected_cells") or []:
        mk = str(exp["metric_key"])
        fy = int(exp["fiscal_year"])
        got = by_key.get((mk, fy))
        if got is None:
            failures.append(
                CheckFailure(
                    code="H-1",
                    message=f"missing expected cell {mk} FY{fy}",
                )
            )
            continue
        want_status = str(exp.get("status") or "proven")
        got_status = got.status.value if hasattr(got.status, "value") else str(got.status)
        if got_status != want_status:
            failures.append(
                CheckFailure(
                    code="H-3",
                    message=f"status mismatch {mk} FY{fy}: got {got_status} want {want_status}",
                    detail={"got_value": got.value, "want_value": exp.get("value")},
                )
            )
        if "value" in exp and exp["value"] is not None and got.value is not None:
            if not _floats_close(float(got.value), float(exp["value"])):
                failures.append(
                    CheckFailure(
                        code="H-3",
                        message=f"value mismatch {mk} FY{fy}: got {got.value} want {exp['value']}",
                    )
                )

    # H-4 coverage: every coverage key×year (same matrix as fill_missing) must
    # be proven|doubtful|missing — do not expand to incidental cell years
    # outside the resolved coverage window (e.g. appendix/BS-only FYs).
    if cov_spec.keys:
        for mk in cov_spec.keys:
            for fy in cov_spec.years:
                cell = by_key.get((mk, fy))
                if cell is None:
                    failures.append(
                        CheckFailure(
                            code="H-4",
                            message=f"coverage gap: {mk} FY{fy} has no status",
                        )
                    )
                elif cell.status not in {
                    ReleaseCellStatus.PROVEN,
                    ReleaseCellStatus.DOUBTFUL,
                    ReleaseCellStatus.MISSING,
                }:
                    failures.append(
                        CheckFailure(
                            code="H-4",
                            message=f"coverage status invalid: {mk} FY{fy}={cell.status}",
                        )
                    )

    # G2 — every missing cell must carry a document request; open request_list non-empty when missing.
    req_ids = {r.request_id for r in request_list}
    for cell in cells:
        if cell.status != ReleaseCellStatus.MISSING:
            continue
        if not cell.request_id or cell.document_request is None:
            failures.append(
                CheckFailure(
                    code="G2-request",
                    message=(
                        f"missing cell {cell.metric_key} FY{cell.fiscal_year} "
                        "lacks document_request"
                    ),
                )
            )
        elif cell.request_id not in req_ids:
            failures.append(
                CheckFailure(
                    code="G2-request",
                    message=(
                        f"missing cell {cell.metric_key} FY{cell.fiscal_year} "
                        f"request_id {cell.request_id} not in request_list"
                    ),
                )
            )
    if any(c.status == ReleaseCellStatus.MISSING for c in cells) and not request_list:
        failures.append(
            CheckFailure(
                code="G2-request",
                message="missing cells present but request_list is empty",
            )
        )
    # Optional golden.expected_docs: required kinds that should be absent → open requests
    for kind in golden.get("expect_missing_docs") or []:
        kind_s = str(kind)
        if assessment is not None and kind_s not in (assessment.missing_required or []):
            failures.append(
                CheckFailure(
                    code="G2-docs",
                    message=f"expected absent doc kind not flagged: {kind_s}",
                    detail={"missing_required": list(assessment.missing_required or [])},
                )
            )
        if not any(r.doc_kind == kind_s and r.status == "open" for r in request_list):
            failures.append(
                CheckFailure(
                    code="G2-docs",
                    message=f"expected open request for doc kind: {kind_s}",
                )
            )

    # G3 — stable page classes + statement routing on golden tables.
    from agetic_cdd_api.services_databook_pages import classify_table_class

    for exp in golden.get("expected_page_classes") or []:
        if not isinstance(exp, dict):
            continue
        tname = str(exp.get("table_name") or "")
        want_class = str(exp.get("page_class") or "")
        if not tname or not want_class:
            continue
        hit = classify_table_class(table_name=tname)
        if hit.page_class.value != want_class:
            failures.append(
                CheckFailure(
                    code="G3-class",
                    message=(
                        f"table {tname!r} classify got {hit.page_class.value} "
                        f"want {want_class}"
                    ),
                )
            )
        row_matches = [
            r
            for r in first["rows"]
            if (r.table_name or "") == tname and r.status != RowStatus.DROPPED
        ]
        if not row_matches:
            failures.append(
                CheckFailure(
                    code="G3-class",
                    message=f"no extracted rows for table {tname!r}",
                )
            )
            continue
        row_classes = {
            r.page_class.value if r.page_class is not None else "unknown"
            for r in row_matches
        }
        if want_class not in row_classes:
            failures.append(
                CheckFailure(
                    code="G3-class",
                    message=(
                        f"rows on {tname!r} page_class {sorted(row_classes)} "
                        f"want {want_class}"
                    ),
                )
            )
        if want_class not in {"unknown", "other", "note"}:
            stmts = {r.statement for r in row_matches if r.statement}
            if want_class not in stmts:
                failures.append(
                    CheckFailure(
                        code="G3-route",
                        message=(
                            f"rows on {tname!r} statement {sorted(stmts)} "
                            f"want {want_class}"
                        ),
                    )
                )

    # G5 — prove checks that should be green on this golden (when inputs present).
    failed_prove = {
        str(i.get("check_id"))
        for i in (first.get("issues") or [])
        if isinstance(i, dict) and i.get("kind") == "prove_check" and i.get("check_id")
    }
    for check_id in golden.get("expect_prove_ok") or []:
        cid = str(check_id)
        if cid in failed_prove:
            failures.append(
                CheckFailure(
                    code="G5-prove",
                    message=f"prove check failed on golden: {cid}",
                    detail={"failed_prove": sorted(failed_prove)},
                )
            )

    proven = sum(1 for c in cells if c.status == ReleaseCellStatus.PROVEN)
    doubtful = sum(1 for c in cells if c.status == ReleaseCellStatus.DOUBTFUL)
    missing = sum(1 for c in cells if c.status == ReleaseCellStatus.MISSING)
    min_proven = int(golden.get("expected_min_proven") or 0)
    if proven < min_proven:
        failures.append(
            CheckFailure(
                code="H-3",
                message=f"proven count {proven} < expected_min_proven {min_proven}",
            )
        )

    # G6 / H-1 — full-size golden figure budget
    figures = count_golden_figures(golden)
    min_figures = int(
        golden.get("expected_min_figures")
        or _DEFAULT_MIN_FIGURES.get(golden_id, 0)
        or 0
    )
    if min_figures and figures < min_figures:
        failures.append(
            CheckFailure(
                code="H-1",
                message=f"figure count {figures} < expected_min_figures {min_figures}",
                detail={"figures": figures, "expected_min_figures": min_figures},
            )
        )

    return GoldenResult(
        golden_id=golden_id,
        ok=not failures,
        failures=failures,
        proven=proven,
        doubtful=doubtful,
        missing=missing,
        fingerprint=fp1,
        figures=figures,
        min_figures=min_figures,
    )


def run_all_goldens(directory: Path | None = None) -> list[GoldenResult]:
    root = directory or goldens_dir()
    results: list[GoldenResult] = []
    for path in sorted(root.glob("*.json")):
        results.append(run_golden(path))
    return results


# ---------------------------------------------------------------------------
# Trap runner (H-2)
# ---------------------------------------------------------------------------


@dataclass
class TrapResult:
    trap_id: str
    ok: bool
    message: str = ""
    kind: str = ""


def load_traps_fixture(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or traps_path()
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(json.loads(line))
    return out


def _rows_from_trap_spec(spec: dict[str, Any]) -> list[ExtractedRow]:
    rows: list[ExtractedRow] = []
    for i, item in enumerate(spec.get("rows") or []):
        rows.append(
            ExtractedRow(
                row_id=str(item.get("row_id") or f"t{i}"),
                doc_id=str(item.get("doc_id") or "d"),
                source_name=str(item.get("source_name") or "a.pdf"),
                caption=str(item.get("caption") or ""),
                metric_key=item.get("metric_key"),
                metric_family=MetricFamily(item["metric_family"])
                if item.get("metric_family")
                else MetricFamily.UNKNOWN,
                fiscal_year=item.get("fiscal_year"),
                value=float(item["value"]),
                status=RowStatus(item["status"]) if item.get("status") else RowStatus.CANDIDATE,
                ladder_score=item.get("ladder_score"),
                source_basis=SourceBasis(item["source_basis"])
                if item.get("source_basis")
                else None,
                dual_agree=item.get("dual_agree"),
                assumption=bool(item.get("assumption", False)),
                derived=bool(item.get("derived", False)),
                statement=item.get("statement"),
                coa_section=item.get("coa_section"),
            )
        )
    return rows


def run_trap(spec: dict[str, Any]) -> TrapResult:
    """Dispatch one curated trap check."""
    trap_id = str(spec.get("trap_id") or "?")
    kind = str(spec.get("kind") or "")
    check = str(spec.get("check") or "")
    try:
        if check == "map":
            hit = map_caption(
                str(spec["caption"]),
                statement=spec.get("statement"),
                sector_pack=str(spec.get("sector_pack") or "generic"),
            )
            expect = spec.get("expect_metric")
            forbid = spec.get("forbid_metric")
            got = hit.metric_key if hit else None
            if expect and got != expect:
                return TrapResult(trap_id, False, f"map got {got} want {expect}", kind)
            if forbid and got == forbid:
                return TrapResult(trap_id, False, f"map must not be {forbid}", kind)
            if spec.get("expect_unmapped") and hit is not None:
                return TrapResult(trap_id, False, "expected unmapped", kind)
            return TrapResult(trap_id, True, kind=kind)

        if check == "family":
            caption = str(spec["caption"])
            metric = str(spec["metric_key"])
            allowed = same_family_allowed(caption, metric)
            want = bool(spec.get("expect_allowed", True))
            if allowed != want:
                return TrapResult(
                    trap_id, False, f"family allowed={allowed} want={want}", kind
                )
            return TrapResult(trap_id, True, kind=kind)

        if check == "series_drop":
            rows = _rows_from_trap_spec(spec)
            out, _ = apply_series_drops(rows, params=DealDatabookParams())
            dropped = {r.value for r in out if r.status == RowStatus.DROPPED}
            for v in spec.get("expect_dropped") or []:
                if not _float_in(float(v), dropped):
                    return TrapResult(trap_id, False, f"expected drop {v}", kind)
            for v in spec.get("expect_kept") or []:
                if _float_in(float(v), dropped):
                    return TrapResult(trap_id, False, f"unexpected drop {v}", kind)
            return TrapResult(trap_id, True, kind=kind)

        if check == "scale_step":
            rows = _rows_from_trap_spec(spec)
            out, hold_ids, _ = apply_scale_step_guard(rows, params=DealDatabookParams())
            held_vals = {r.value for r in out if r.row_id in hold_ids}
            for v in spec.get("expect_held") or []:
                if not _float_in(float(v), held_vals):
                    return TrapResult(trap_id, False, f"expected hold {v}", kind)
            return TrapResult(trap_id, True, kind=kind)

        if check == "conflict":
            rows = _rows_from_trap_spec(spec)
            issues, _ = detect_conflicts(rows)
            metric = canonicalize_metric_key(spec.get("metric") or "revenue")
            fy = int(spec.get("fiscal_year") or 2024)
            found = [
                i
                for i in issues
                if canonicalize_metric_key(i.get("metric")) == metric
            ]
            found = [i for i in found if i.get("fiscal_year") == fy] or found
            if spec.get("expect_conflict") and not found:
                return TrapResult(trap_id, False, "expected conflict", kind)
            if found:
                values = {
                    float(c["value"])
                    for c in found[0].get("candidates") or []
                    if isinstance(c, dict) and c.get("value") is not None
                }
                for v in spec.get("forbid_values") or []:
                    if _float_in(float(v), values):
                        return TrapResult(
                            trap_id, False, f"forbidden candidate {v} in conflict", kind
                        )
                for v in spec.get("require_values") or []:
                    if not _float_in(float(v), values):
                        return TrapResult(
                            trap_id, False, f"missing candidate {v}", kind
                        )
            return TrapResult(trap_id, True, kind=kind)

        if check == "year_as_value":
            ok = is_year_as_value(
                spec.get("metric_key"),
                spec.get("fiscal_year"),
                float(spec["value"]),
            )
            want = bool(spec.get("expect_true", True))
            if ok != want:
                return TrapResult(trap_id, False, f"year_as_value={ok} want={want}", kind)
            return TrapResult(trap_id, True, kind=kind)

        if check == "raw_money":
            ok = is_implausible_money_magnitude(
                spec.get("metric_key"), float(spec["value"])
            )
            want = bool(spec.get("expect_true", True))
            if ok != want:
                return TrapResult(trap_id, False, f"raw_money={ok} want={want}", kind)
            return TrapResult(trap_id, True, kind=kind)

        if check == "parse":
            got = _parse_number(str(spec["cell"]))
            want = spec.get("expect")
            if want is None:
                if got is not None:
                    return TrapResult(trap_id, False, f"expected None got {got}", kind)
            elif got is None or not _floats_close(float(got), float(want)):
                return TrapResult(trap_id, False, f"parse got {got} want {want}", kind)
            return TrapResult(trap_id, True, kind=kind)

        if check == "set_aside":
            tokens = set(spec.get("deal_tokens") or ["acme"])
            entry = classify_entry(
                {
                    "filename": str(spec["filename"]),
                    "library_stem": "x",
                    "excerpt": str(spec.get("excerpt") or ""),
                },
                deal_tokens=tokens,
            )
            want_aside = bool(spec.get("expect_set_aside", True))
            is_aside = not allows_history_extract(entry)
            # forecast_only also blocks history
            if want_aside and not is_aside:
                return TrapResult(trap_id, False, "expected set-aside/forecast gate", kind)
            if not want_aside and is_aside:
                return TrapResult(trap_id, False, "unexpected gate", kind)
            if spec.get("expect_role") and entry.role.value != spec["expect_role"]:
                return TrapResult(
                    trap_id,
                    False,
                    f"role={entry.role.value} want={spec['expect_role']}",
                    kind,
                )
            return TrapResult(trap_id, True, kind=kind)

        if check == "forecast_header":
            cell = str(spec["cell"])
            got = is_forecast_period_header(cell)
            want = bool(spec.get("expect_true", True))
            if got != want:
                return TrapResult(
                    trap_id, False, f"forecast_header({cell})={got} want={want}", kind
                )
            return TrapResult(trap_id, True, kind=kind)

        if check == "plainness":
            score = caption_plainness(str(spec["caption"]), str(spec["metric_key"]))
            min_score = float(spec.get("min_score") or 0.0)
            if score < min_score:
                return TrapResult(
                    trap_id, False, f"plainness {score} < {min_score}", kind
                )
            return TrapResult(trap_id, True, kind=kind)

        if check == "extract":
            table = spec.get("table") or {}
            rows = rows_from_table(
                source_name=str(spec.get("source_name") or "a.pdf"),
                doc_id="d",
                table=table,
                sector_pack=str(spec.get("sector_pack") or "generic"),
            )
            if "expect_row_count" in spec and len(rows) != int(spec["expect_row_count"]):
                return TrapResult(
                    trap_id,
                    False,
                    f"row_count={len(rows)} want={spec['expect_row_count']}",
                    kind,
                )
            for exp in spec.get("expect_rows") or []:
                match = [
                    r
                    for r in rows
                    if r.metric_key == exp.get("metric_key")
                    and r.fiscal_year == exp.get("fiscal_year")
                ]
                if not match:
                    return TrapResult(
                        trap_id,
                        False,
                        f"missing extract {exp.get('metric_key')} FY{exp.get('fiscal_year')}",
                        kind,
                    )
                if "value" in exp and not _floats_close(match[0].value, float(exp["value"])):
                    return TrapResult(
                        trap_id,
                        False,
                        f"value {match[0].value} != {exp['value']}",
                        kind,
                    )
            for forbid in spec.get("forbid_values") or []:
                if any(_floats_close(r.value, float(forbid)) for r in rows):
                    return TrapResult(
                        trap_id, False, f"forbidden extract value {forbid}", kind
                    )
            return TrapResult(trap_id, True, kind=kind)

        if check == "prose_notes":
            notes = notes_from_prose(
                source_name="a.pdf",
                doc_id="d",
                text=str(spec.get("text") or ""),
            )
            min_notes = int(spec.get("min_notes") or 0)
            if len(notes) < min_notes:
                return TrapResult(
                    trap_id, False, f"notes={len(notes)} < {min_notes}", kind
                )
            # Statement extract from prose text alone must be empty tables
            return TrapResult(trap_id, True, kind=kind)

        if check == "promote_derived":
            rows = _rows_from_trap_spec(spec)
            # Ensure L2 proof via prove pipeline
            rows, holds, _ = run_prove_pipeline(
                rows, blocks=[], block_fail_ids=set(), hold_ids=set(), params=DealDatabookParams()
            )
            _, promoted = apply_statuses_and_promote(rows, hold_ids=holds, params=DealDatabookParams())
            derived_keys = {p.metric_key for p in promoted}
            for mk in spec.get("forbid_promoted") or []:
                if mk in derived_keys:
                    return TrapResult(
                        trap_id, False, f"derived {mk} must not auto-promote", kind
                    )
            for mk in spec.get("require_promoted") or []:
                if mk not in derived_keys:
                    return TrapResult(
                        trap_id, False, f"expected promote {mk}", kind
                    )
            return TrapResult(trap_id, True, kind=kind)

        if check == "prove":
            from agetic_cdd_api.services_databook_models import NoteFact
            from agetic_cdd_api.services_databook_prove import run_prove_pipeline as _prove

            rows = _rows_from_trap_spec(spec)
            notes_raw = spec.get("notes") or []
            notes = [
                NoteFact(
                    note_id=str(n.get("note_id") or f"n{i}"),
                    doc_id=str(n.get("doc_id") or "d"),
                    source_name=str(n.get("source_name") or "notes.pdf"),
                    caption=str(n.get("caption") or ""),
                    fiscal_year=n.get("fiscal_year"),
                    value=float(n["value"]),
                    metric_key=n.get("metric_key"),
                )
                for i, n in enumerate(notes_raw)
                if isinstance(n, dict) and n.get("value") is not None
            ]
            _, holds, issues = _prove(
                rows,
                blocks=[],
                block_fail_ids=set(),
                hold_ids=set(),
                params=DealDatabookParams(),
                notes=notes or None,
            )
            check_id = str(spec.get("check_id") or "")
            matched = [i for i in issues if i.get("check_id") == check_id] if check_id else issues
            expect_fail = bool(spec.get("expect_fail", True))
            if expect_fail and not matched:
                return TrapResult(
                    trap_id, False, f"expected prove fail {check_id or '*'}", kind
                )
            if not expect_fail and matched:
                return TrapResult(
                    trap_id, False, f"unexpected prove fail {check_id}", kind
                )
            if spec.get("expect_holds") and check_id:
                if not holds:
                    return TrapResult(
                        trap_id,
                        False,
                        f"expected holds for {check_id}; holds empty",
                        kind,
                    )
                issue_ids = {
                    rid
                    for i in matched
                    for rid in (
                        i.get("row_ids")
                        or ([i["row_id"]] if i.get("row_id") else [])
                    )
                }
                # Holds may be a subset of issue row_ids (e.g. draft-only on draft→final).
                if not set(holds).issubset(issue_ids):
                    return TrapResult(
                        trap_id,
                        False,
                        f"expected holds for {check_id}; holds={sorted(holds)}",
                        kind,
                    )
            if spec.get("expect_failure_class") and matched:
                want_fc = str(spec["expect_failure_class"])
                got_fc = matched[0].get("failure_class")
                if got_fc != want_fc:
                    return TrapResult(
                        trap_id,
                        False,
                        f"failure_class={got_fc} want={want_fc}",
                        kind,
                    )
            return TrapResult(trap_id, True, kind=kind)

        if check == "page_class":
            from agetic_cdd_api.services_databook_pages import classify_text_to_page_class

            hit = classify_text_to_page_class(str(spec.get("text") or ""))
            want = str(spec.get("expect_class") or "")
            if hit.page_class.value != want:
                return TrapResult(
                    trap_id,
                    False,
                    f"page_class got {hit.page_class.value} want {want}",
                    kind,
                )
            return TrapResult(trap_id, True, kind=kind)

        if check == "page_class_map":
            table = spec.get("table") or {}
            rows = rows_from_table(
                source_name=str(spec.get("source_name") or "a.pdf"),
                doc_id="d",
                table=table,
                sector_pack=str(spec.get("sector_pack") or "generic"),
            )
            want_stmt = spec.get("expect_statement")
            if want_stmt:
                for row in rows:
                    if row.statement != want_stmt:
                        return TrapResult(
                            trap_id,
                            False,
                            f"statement {row.statement!r} want {want_stmt!r}",
                            kind,
                        )
            caption = str(spec.get("caption") or "")
            if caption:
                matched = [r for r in rows if r.caption == caption]
                if not matched:
                    return TrapResult(trap_id, False, f"no row for caption {caption!r}", kind)
                if spec.get("expect_unmapped") and matched[0].metric_key is not None:
                    return TrapResult(
                        trap_id,
                        False,
                        f"misroute mapped to {matched[0].metric_key}",
                        kind,
                    )
            return TrapResult(trap_id, True, kind=kind)

        return TrapResult(trap_id, False, f"unknown check {check}", kind)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Trap %s crashed", trap_id)
        return TrapResult(trap_id, False, _truncate(f"exception: {exc}"), kind)


def run_all_traps(path: Path | None = None) -> list[TrapResult]:
    return [run_trap(spec) for spec in load_traps_fixture(path)]


# ---------------------------------------------------------------------------
# Ship gate (H-7)
# ---------------------------------------------------------------------------


@dataclass
class ShipGateReport:
    ok: bool
    goldens: list[GoldenResult] = field(default_factory=list)
    traps: list[TrapResult] = field(default_factory=list)
    trap_pass: int = 0
    trap_fail: int = 0
    golden_pass: int = 0
    golden_fail: int = 0
    required_trap_count: int = 32

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "goldens": {
                "pass": self.golden_pass,
                "fail": self.golden_fail,
                "total": len(self.goldens),
                "ids": [
                    {
                        "id": g.golden_id,
                        "ok": g.ok,
                        "proven": g.proven,
                        "doubtful": g.doubtful,
                        "missing": g.missing,
                        "figures": g.figures,
                        "min_figures": g.min_figures,
                        "fp": g.fingerprint,
                        "failures": [
                            {"code": f.code, "message": f.message} for f in g.failures
                        ],
                    }
                    for g in self.goldens
                ],
            },
            "traps": {
                "pass": self.trap_pass,
                "fail": self.trap_fail,
                "total": len(self.traps),
                "required": self.required_trap_count,
                "failures": [
                    {
                        "id": t.trap_id,
                        "kind": t.kind,
                        "message": _truncate(t.message),
                    }
                    for t in self.traps
                    if not t.ok
                ],
            },
        }


def run_ship_gate(
    *,
    goldens_directory: Path | None = None,
    traps_file: Path | None = None,
    required_trap_count: int = 32,
) -> ShipGateReport:
    """H-7 — full databook engine ship gate."""
    goldens = run_all_goldens(goldens_directory)
    traps = run_all_traps(traps_file)
    golden_pass = sum(1 for g in goldens if g.ok)
    golden_fail = len(goldens) - golden_pass
    trap_pass = sum(1 for t in traps if t.ok)
    trap_fail = len(traps) - trap_pass
    ok = (
        golden_fail == 0
        and trap_fail == 0
        and len(goldens) >= 1
        and len(traps) >= required_trap_count
        and all(
            (g.min_figures == 0 or g.figures >= g.min_figures) for g in goldens
        )
    )
    return ShipGateReport(
        ok=ok,
        goldens=goldens,
        traps=traps,
        trap_pass=trap_pass,
        trap_fail=trap_fail,
        golden_pass=golden_pass,
        golden_fail=golden_fail,
        required_trap_count=required_trap_count,
    )


def trap_record_from_spec(spec: dict[str, Any]) -> TrapRecord | None:
    """Optional helper — convert fixture row to TrapRecord shape for deals."""
    try:
        return TrapRecord(
            trap_id=str(spec["trap_id"]),
            kind=spec.get("kind") or "wrong_metric",  # type: ignore[arg-type]
            caption=spec.get("caption"),
            metric_key=spec.get("expect_metric") or spec.get("metric_key"),
            fiscal_year=spec.get("fiscal_year"),
            bad_value=spec.get("bad_value"),
            good_value=spec.get("good_value"),
            note=str(spec.get("note") or spec.get("check") or ""),
            created_at="fixture",
        )
    except Exception:  # noqa: BLE001
        return None
