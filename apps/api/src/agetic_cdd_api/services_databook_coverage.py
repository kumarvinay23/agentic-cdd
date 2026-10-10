"""G2 coverage honesty: expected keys×years → missing cells + document requests.

Shared by production ``build_release_cells`` / ``create_release`` and the P7 harness
so ship-gate coverage cannot diverge from live releases.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Literal

from agetic_cdd_api.services_databook_models import (
    CoverageSpec,
    DealDatabookParams,
    DocumentRequest,
    ExpectedDocsAssessment,
    ExpectedDocPresence,
    ReleaseCellStatus,
    ReleasedCell,
)

# Align with consume.MATERIAL_METRIC_KEYS + common P&L companions.
_GENERIC_COVERAGE_KEYS: tuple[str, ...] = (
    "revenue",
    "ebitda",
    "gross_profit",
    "gross_margin",
    "ebitda_margin",
    "yoy_growth",
)
_SAAS_EXTRA_KEYS: tuple[str, ...] = ("nrr", "grr")

# Stable fallback when no years in params, coverage_years, or cells — avoids calendar drift.
_DEFAULT_FALLBACK_COVERAGE_YEAR = 2024

_METRIC_DOC_KIND: dict[str, str] = {
    "revenue": "audited_financials",
    "ebitda": "audited_financials",
    "gross_profit": "audited_financials",
    "gross_margin": "audited_financials",
    "ebitda_margin": "audited_financials",
    "yoy_growth": "audited_financials",
    "nrr": "cohort_retention",
    "grr": "cohort_retention",
}

_DOC_KIND_LABELS: dict[str, str] = {
    "audited_financials": "Audited financial statements",
    "management_accounts": "Management accounts / board packs",
    "qoe_report": "Quality of earnings (QoE) report",
    "cohort_retention": "Cohort / retention schedule (NRR/GRR)",
    "supporting_schedule": "Supporting schedule / statement extract",
}


def default_coverage_keys(sector_pack: str = "generic") -> list[str]:
    pack = (sector_pack or "generic").strip().lower()
    keys = list(_GENERIC_COVERAGE_KEYS)
    if pack in {"saas"}:
        keys.extend(_SAAS_EXTRA_KEYS)
    return keys


def resolve_coverage_spec(
    *,
    params: DealDatabookParams | None = None,
    coverage_keys: list[str] | None = None,
    coverage_years: Iterable[int] | None = None,
    cell_years: Iterable[int] | None = None,
    source: Literal["params", "expected_docs", "material_default", "golden"] | None = None,
) -> CoverageSpec:
    """Resolve keys+years for missing synthesis.

    Precedence for keys: explicit coverage_keys → params.coverage_keys → sector default.
    Years: explicit → params → union of cell years → calendar fallback.
    """
    cfg = params or DealDatabookParams()
    keys = list(coverage_keys or cfg.coverage_keys or default_coverage_keys(cfg.sector_pack))
    # Drop SaaS-only metrics on non-SaaS packs (do not invent missing NRR).
    keys = [k for k in keys if k and not cfg.blocks_saas_metric(k)]
    keys = list(dict.fromkeys(keys))

    if coverage_years is not None:
        years = sorted({int(y) for y in coverage_years})
    elif cfg.coverage_years:
        years = sorted({int(y) for y in cfg.coverage_years})
    else:
        years = sorted({int(y) for y in (cell_years or ())})
    if not years:
        years = [_DEFAULT_FALLBACK_COVERAGE_YEAR]

    if source is not None:
        resolved_source = source
    elif coverage_keys is not None:
        resolved_source = "golden"
    elif cfg.coverage_keys:
        resolved_source = "params"
    else:
        resolved_source = "material_default"

    return CoverageSpec(keys=keys, years=years, source=resolved_source)


def _request_id(doc_kind: str, *parts: Any) -> str:
    raw = "|".join([doc_kind, *[str(p) for p in parts]])
    return "req_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _label_for_doc_kind(doc_kind: str) -> str:
    return _DOC_KIND_LABELS.get(doc_kind, doc_kind.replace("_", " ").title())


def _pick_doc_kind_for_metric(
    metric_key: str,
    assessment: ExpectedDocsAssessment | None,
) -> tuple[str, str, list[str]]:
    """Return (doc_kind, label, matched_filenames) for a missing metric."""
    preferred = _METRIC_DOC_KIND.get(metric_key, "supporting_schedule")
    if assessment is not None:
        # Prefer an absent required doc that covers this metric.
        for doc in assessment.docs:
            if metric_key in (doc.covers_metrics or []) and not doc.present and doc.required:
                return doc.doc_kind, doc.label, list(doc.matched_filenames)
        for doc in assessment.docs:
            if doc.doc_kind == preferred:
                if not doc.present:
                    return doc.doc_kind, doc.label, list(doc.matched_filenames)
                # Present but figure still missing → supporting schedule for that year.
                break
    return preferred, _label_for_doc_kind(preferred), []


def _merge_request(
    bucket: dict[str, DocumentRequest],
    *,
    doc_kind: str,
    label: str,
    reason: str,
    metric_key: str,
    fiscal_year: int,
    priority: str = "required",
    matched_filenames: list[str] | None = None,
) -> DocumentRequest:
    existing = bucket.get(doc_kind)
    if existing is None:
        req = DocumentRequest(
            request_id=_request_id(doc_kind, "open"),
            doc_kind=doc_kind,
            label=label,
            reason=reason,
            metric_keys=[metric_key],
            fiscal_years=[fiscal_year],
            priority=priority,  # type: ignore[arg-type]
            status="open",
            matched_filenames=list(matched_filenames or []),
        )
        bucket[doc_kind] = req
        return req
    if metric_key not in existing.metric_keys:
        existing.metric_keys.append(metric_key)
    if fiscal_year not in existing.fiscal_years:
        existing.fiscal_years.append(fiscal_year)
        existing.fiscal_years.sort()
    existing.matched_filenames = list(
        dict.fromkeys([*existing.matched_filenames, *(matched_filenames or [])])
    )
    # Broaden reason when multiple figures share a request.
    if reason and reason not in existing.reason:
        if existing.reason:
            existing.reason = f"{existing.reason}; {reason}"
        else:
            existing.reason = reason
    return existing


def requests_for_absent_docs(assessment: ExpectedDocsAssessment | None) -> list[DocumentRequest]:
    """Open requests for required expected docs that are absent from the VDR."""
    if assessment is None:
        return []
    out: list[DocumentRequest] = []
    for doc in assessment.docs:
        if doc.present or not doc.required:
            continue
        out.append(
            DocumentRequest(
                request_id=_request_id(doc.doc_kind, "absent"),
                doc_kind=doc.doc_kind,
                label=doc.label,
                reason=f"Expected document absent from VDR: {doc.label}",
                metric_keys=list(doc.covers_metrics or []),
                fiscal_years=[],
                priority="required",
                status="open",
                matched_filenames=[],
            )
        )
    return out


def _stamp_final_requests_on_missing_cells(
    by_key: dict[tuple[str, int], ReleasedCell],
    request_bucket: dict[str, DocumentRequest],
    assessment: ExpectedDocsAssessment | None,
) -> None:
    """Re-bind every MISSING cell to the final merged DocumentRequest for its doc_kind."""
    for key, cell in list(by_key.items()):
        if cell.status != ReleaseCellStatus.MISSING:
            continue
        doc_kind, _, _ = _pick_doc_kind_for_metric(cell.metric_key, assessment)
        final_req = request_bucket.get(doc_kind)
        if final_req is None:
            continue
        by_key[key] = cell.model_copy(
            update={
                "request_id": final_req.request_id,
                "document_request": final_req,
            }
        )


def fill_missing_coverage_cells(
    cells: list[ReleasedCell],
    *,
    coverage: CoverageSpec,
    assessment: ExpectedDocsAssessment | None = None,
    attach_absent_doc_requests: bool = True,
) -> tuple[list[ReleasedCell], list[DocumentRequest]]:
    """Ensure every coverage key×year is proven|doubtful|missing+request.

    Existing missing cells without a request get one attached. Absent key×year
    pairs are synthesized as MISSING with ``reason='expected figure absent'``.
    """
    by_key: dict[tuple[str, int], ReleasedCell] = {
        (c.metric_key, int(c.fiscal_year)): c for c in cells
    }
    request_bucket: dict[str, DocumentRequest] = {}

    # Seed bucket with absent-doc requests (first-class AR-5).
    if attach_absent_doc_requests:
        for req in requests_for_absent_docs(assessment):
            request_bucket[req.doc_kind] = req

    years = list(coverage.years) or sorted({c.fiscal_year for c in cells}) or [_DEFAULT_FALLBACK_COVERAGE_YEAR]
    for mk in coverage.keys:
        for fy in years:
            key = (mk, int(fy))
            cell = by_key.get(key)
            if cell is not None and cell.status != ReleaseCellStatus.MISSING:
                continue
            doc_kind, label, matched = _pick_doc_kind_for_metric(mk, assessment)
            reason = (
                cell.reason
                if cell is not None and cell.reason
                else "expected figure absent"
            )
            _merge_request(
                request_bucket,
                doc_kind=doc_kind,
                label=label,
                reason=reason if reason != "expected figure absent" else f"No evidence for {mk} FY{fy}",
                metric_key=mk,
                fiscal_year=int(fy),
                matched_filenames=matched,
            )
            if cell is None:
                by_key[key] = ReleasedCell(
                    metric_key=mk,
                    fiscal_year=int(fy),
                    status=ReleaseCellStatus.MISSING,
                    value=None,
                    reason="expected figure absent",
                    auto=True,
                )

    # Also register pre-existing missing cells outside coverage (dropped-only material etc.).
    for key, cell in list(by_key.items()):
        if cell.status != ReleaseCellStatus.MISSING:
            continue
        mk, fy = key
        doc_kind, label, matched = _pick_doc_kind_for_metric(mk, assessment)
        _merge_request(
            request_bucket,
            doc_kind=doc_kind,
            label=label,
            reason=cell.reason or f"No evidence for {mk} FY{fy}",
            metric_key=mk,
            fiscal_year=fy,
            matched_filenames=matched,
        )

    # Final pass: every MISSING cell gets the fully merged request snapshot.
    _stamp_final_requests_on_missing_cells(by_key, request_bucket, assessment)

    request_list = sorted(request_bucket.values(), key=lambda r: (r.priority != "required", r.doc_kind))
    ordered = sorted(by_key.values(), key=lambda c: (c.metric_key, c.fiscal_year))
    return ordered, request_list


def assessment_from_presence(
    *,
    deal_slug: str,
    profile: str,
    generated_at: str,
    docs: list[ExpectedDocPresence],
) -> ExpectedDocsAssessment:
    missing = [d.doc_kind for d in docs if d.required and not d.present]
    return ExpectedDocsAssessment(
        deal_slug=deal_slug,
        profile=profile,
        generated_at=generated_at,
        docs=docs,
        missing_required=missing,
        counts={
            "expected": len(docs),
            "present": sum(1 for d in docs if d.present),
            "missing_required": len(missing),
        },
    )
