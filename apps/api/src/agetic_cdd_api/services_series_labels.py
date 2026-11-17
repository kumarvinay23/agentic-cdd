"""Gate 4 / Gate 6 — stamp eight labels on Financial history series winners.

Postgres series facts (Gates 2–3) do not feed the FDD release path by default.
This module maps SELECTED/DERIVED series winners into labelled
``PromotedMetric`` rows, publishes a release, and clears FDD draft_mode when
the databook contract is complete.

Gate 4 covered contract-critical ``revenue`` / ``ebitda``. Gate 6 expands the
sync to the full Financial history series set (P&L companions + key BS lines).
Gate 7 derives ``gross_margin``, ``ebitda_margin``, and ``yoy_growth`` from
those winners so material coverage is not mostly MISSING.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.services_databook_consume import (
    _display_unit_parts,
    humanize_metric_key,
)
from agetic_cdd_api.services_databook_models import (
    PromotedMetric,
    ProofLevel,
    SourceBasis,
    SourceRef,
)

# Gate 6: all Financial history UI metrics that statement ingest can populate.
# Keep in sync with ``services_databook_view._SERIES_CONCEPTS`` values.
_SERIES_SYNC_METRICS = frozenset(
    {
        "revenue",
        "cogs",
        "gross_profit",
        "ebitda",
        "ebit",
        "net_income",
        "cash",
        "total_assets",
        "equity",
    }
)
# Backward-compatible alias (Gate 4 name).
_SERIES_MATERIAL = _SERIES_SYNC_METRICS
# Contract-critical subset — still required for draft_mode to clear.
_CONTRACT_SERIES_METRICS = frozenset({"revenue", "ebitda"})
# Gate 7: headline ratios derived from synced series winners.
_DERIVED_HEADLINE_METRICS = frozenset({"gross_margin", "ebitda_margin", "yoy_growth"})
_CHOSEN = frozenset({"SELECTED", "DERIVED"})
_SCALE_MAP = {
    1: None,
    1000: "K",
    1_000_000: "M",
    1_000_000_000: "B",
    10_000_000: "Cr",
}
_GATE_AUTO_RULES = frozenset(
    {
        "gate4_series_labels",
        "gate6_series_labels",
        "gate7_derived",
        None,
    }
)


def sync_material_series_labels(deal: Any) -> dict[str, Any]:
    """Promote labelled material series winners and refresh the databook release."""
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
    slug = str(getattr(deal, "slug", None) or deal_id).strip()
    if not deal_id:
        return {
            "deal_id": "",
            "synced": 0,
            "release_id": None,
            "contract_complete": False,
            "reasons": ["no_deal"],
        }

    from agetic_cdd_api.services_databook_release import SlugDeal, create_release
    from agetic_cdd_api.services_databook_store import load_promoted, save_promoted
    from agetic_cdd_api.services_fact_repository import facts_for
    from agetic_cdd_api.services_fdd_bridge import assess_databook_contract

    deal_like = SlugDeal(id=deal_id, slug=slug)
    promoted_new = [
        promoted_from_series_fact(row)
        for row in facts_for(deal_id)
        if _is_series_sync_winner(row)
    ]
    promoted_new = [m for m in promoted_new if m is not None]
    if not promoted_new:
        return {
            "deal_id": deal_id,
            "synced": 0,
            "metrics": [],
            "derived": [],
            "release_id": None,
            "contract_complete": False,
            "reasons": ["no_material_series_winners"],
        }

    existing = load_promoted(deal_like)
    by_key: dict[tuple[str, int], PromotedMetric] = {
        (m.metric_key, int(m.fiscal_year)): m for m in existing
    }
    for metric in promoted_new:
        key = (metric.metric_key, int(metric.fiscal_year))
        prior = by_key.get(key)
        # Preserve explicit HITL decisions; ontology auto rows may refresh.
        if prior is not None and not prior.auto and prior.decision_id:
            continue
        by_key[key] = metric

    # Gate 7: derive margins / YoY from the merged series winners.
    derived = derive_headline_metrics(list(by_key.values()))
    for metric in derived:
        key = (metric.metric_key, int(metric.fiscal_year))
        prior = by_key.get(key)
        if prior is not None and not prior.auto and prior.decision_id:
            continue
        if prior is not None and not _is_gate_auto(prior):
            continue
        by_key[key] = metric

    save_promoted(deal_like, list(by_key.values()))
    synced_metrics = sorted(
        {
            m.metric_key
            for m in by_key.values()
            if m.metric_key in _SERIES_SYNC_METRICS or m.metric_key in _DERIVED_HEADLINE_METRICS
        }
    )
    derived_metrics = sorted(
        {m.metric_key for m in derived if (m.metric_key, int(m.fiscal_year)) in by_key}
    )

    release = create_release(
        deal_like,
        source="bootstrap",
        note="Gate 6/7 — series labels + derived headline margins",
    )
    assessment = assess_databook_contract(release, deal_slug=slug)
    _sync_fdd_manifest_contract(slug, assessment)

    return {
        "deal_id": deal_id,
        "synced": len(promoted_new),
        "metrics": synced_metrics,
        "derived": derived_metrics,
        "contract_metrics_present": sorted(
            set(synced_metrics) & _CONTRACT_SERIES_METRICS
        ),
        "release_id": release.release_id,
        "contract_complete": bool(assessment.complete),
        "draft_mode": bool(assessment.draft_mode),
        "labels_incomplete": int(assessment.labels_incomplete or 0),
        "reasons": list(assessment.reasons or []),
    }


def promoted_from_series_fact(row: dict[str, Any]) -> PromotedMetric | None:
    """Build a labelled PromotedMetric from a Gate 3 series winner fact."""
    from agetic_cdd_api.services_databook_view import _fiscal_year, _metric_for_concept

    concept = str(row.get("concept_id") or "")
    metric = _metric_for_concept(concept)
    if metric not in _SERIES_SYNC_METRICS:
        return None
    year = _fiscal_year(row)
    if year is None or row.get("value") is None:
        return None

    labels = eight_labels_from_series_fact(row, metric_key=metric)
    if labels.missing_fields():
        # Still promote — assess will surface gaps — but try to fill defaults.
        pass

    file_name = _file_name(row)
    mapping = row.get("mapping") if isinstance(row.get("mapping"), dict) else {}
    sheet = str(mapping.get("sheet_or_page") or "") or None
    cell = str(mapping.get("cell_range") or "") or None
    row_idx, col_idx = _cell_rc(cell)
    caption = labels.line or humanize_metric_key(metric)
    currency = str(row.get("currency") or "") or None
    scale = _scale_label(row.get("scale_applied"))
    unit = labels.unit or _display_unit_parts(currency, scale, None) or currency
    source_basis = _source_basis(row)
    proof = _proof_level(row, source_basis)

    return PromotedMetric(
        metric_key=metric,
        fiscal_year=int(year),
        value=float(row["value"]),
        unit=unit,
        currency=currency,
        scale=scale,
        row_id=str(row.get("fact_id") or f"series:{metric}:{year}"),
        sources=[file_name] if file_name else [],
        captions=[caption],
        auto=True,
        scope=labels.scope,
        statement=labels.statement,
        period_end=labels.period_end,
        period_length=labels.period_length,
        source_basis=source_basis,
        source_ref=SourceRef(
            doc=file_name or "series_fact",
            table=sheet,
            row=row_idx,
            col=col_idx,
            rule="gate6_series_labels",
        ),
        proof_level=proof,
        proof_checks=["gate3_series_canonical", "gate6_eight_labels"],
    )


def derive_headline_metrics(metrics: list[PromotedMetric]) -> list[PromotedMetric]:
    """Gate 7 — derive gross_margin, ebitda_margin, yoy_growth from series winners.

    Margins are percent points (gross_profit / revenue × 100). YoY growth uses
    consecutive fiscal-year revenue winners.
    """
    by_year: dict[int, dict[str, PromotedMetric]] = {}
    for metric in metrics:
        year = int(metric.fiscal_year)
        by_year.setdefault(year, {})[metric.metric_key] = metric

    derived: list[PromotedMetric] = []
    for year in sorted(by_year):
        bucket = by_year[year]
        revenue = bucket.get("revenue")
        gross_profit = bucket.get("gross_profit")
        ebitda = bucket.get("ebitda")
        if revenue is not None and gross_profit is not None:
            margin = _safe_ratio_pct(gross_profit.value, revenue.value)
            if margin is not None:
                derived.append(
                    _derived_headline(
                        "gross_margin",
                        year,
                        margin,
                        primary=revenue,
                        secondary=gross_profit,
                        caption="Gross margin",
                    )
                )
        if revenue is not None and ebitda is not None:
            margin = _safe_ratio_pct(ebitda.value, revenue.value)
            if margin is not None:
                derived.append(
                    _derived_headline(
                        "ebitda_margin",
                        year,
                        margin,
                        primary=revenue,
                        secondary=ebitda,
                        caption="EBITDA margin",
                    )
                )
        prior_rev = by_year.get(year - 1, {}).get("revenue")
        if revenue is not None and prior_rev is not None:
            growth = _safe_ratio_pct(
                float(revenue.value) - float(prior_rev.value),
                prior_rev.value,
            )
            if growth is not None:
                derived.append(
                    _derived_headline(
                        "yoy_growth",
                        year,
                        growth,
                        primary=revenue,
                        secondary=prior_rev,
                        caption="YoY growth",
                    )
                )
    return derived


def _derived_headline(
    metric_key: str,
    fiscal_year: int,
    value: float,
    *,
    primary: PromotedMetric,
    secondary: PromotedMetric,
    caption: str,
) -> PromotedMetric:
    sources = list(
        dict.fromkeys([*(primary.sources or []), *(secondary.sources or [])])
    )
    proof = _min_proof(primary.proof_level, secondary.proof_level) or ProofLevel.L2
    basis = primary.source_basis or secondary.source_basis or SourceBasis.MANAGEMENT
    return PromotedMetric(
        metric_key=metric_key,
        fiscal_year=int(fiscal_year),
        value=round(float(value), 6),
        unit="%",
        currency=None,
        scale=None,
        row_id=f"derived:{metric_key}:{fiscal_year}",
        sources=sources,
        captions=[caption],
        auto=True,
        scope=primary.scope or secondary.scope or "consolidated",
        statement=primary.statement or secondary.statement or "IS",
        period_end=primary.period_end or secondary.period_end,
        period_length=primary.period_length or secondary.period_length or "FY",
        source_basis=basis,
        source_ref=SourceRef(
            doc=(sources[0] if sources else "series_derived"),
            table=f"derived:{primary.metric_key}+{secondary.metric_key}",
            rule="gate7_derived",
        ),
        proof_level=proof,
        proof_checks=[
            "gate7_derived_headline",
            f"from:{primary.metric_key}",
            f"from:{secondary.metric_key}",
        ],
    )


def _safe_ratio_pct(numerator: Any, denominator: Any) -> float | None:
    try:
        denom = float(denominator)
        if denom == 0:
            return None
        return (float(numerator) / denom) * 100.0
    except (TypeError, ValueError):
        return None


def _min_proof(left: ProofLevel | None, right: ProofLevel | None) -> ProofLevel | None:
    from agetic_cdd_api.services_databook_models import PROOF_LEVEL_RANK

    if left is None:
        return right
    if right is None:
        return left
    return left if PROOF_LEVEL_RANK.get(left, 0) <= PROOF_LEVEL_RANK.get(right, 0) else right


def _is_gate_auto(metric: PromotedMetric) -> bool:
    if not metric.auto:
        return False
    ref = metric.source_ref
    rule = getattr(ref, "rule", None) if ref is not None else None
    return rule in _GATE_AUTO_RULES


def eight_labels_from_series_fact(
    row: dict[str, Any],
    *,
    metric_key: str | None = None,
) -> Any:
    """Derive EightLabels from an ontology series fact row."""
    from agetic_cdd_api.fdd_schemas import EightLabels
    from agetic_cdd_api.services_databook_view import _metric_for_concept

    metric = metric_key or _metric_for_concept(str(row.get("concept_id") or ""))
    mapping = row.get("mapping") if isinstance(row.get("mapping"), dict) else {}
    line = (
        str(mapping.get("row_label_as_read") or "").strip()
        or str(mapping.get("concept_label") or "").strip()
        or humanize_metric_key(metric or "metric")
    )
    period_end = str(row.get("period_end") or "") or None
    period_length = str(row.get("period_type") or "") or None
    if period_length:
        period_length = period_length.upper()
    currency = str(row.get("currency") or "") or None
    scale = _scale_label(row.get("scale_applied"))
    unit = _display_unit_parts(currency, scale, None) or currency
    source_basis = _source_basis(row)
    file_name = _file_name(row)
    sheet = str(mapping.get("sheet_or_page") or "").strip()
    source = file_name
    if source and sheet:
        source = f"{source} / {sheet}"
    scope = str(row.get("entity_id") or "CONSOLIDATED").strip()
    if scope.upper() == "CONSOLIDATED":
        scope = "consolidated"
    statement = _statement_for_concept(str(row.get("concept_id") or ""))

    return EightLabels(
        scope=scope or None,
        statement=statement,
        line=line or None,
        period_end=period_end,
        period_length=period_length,
        basis=source_basis.value if source_basis else None,
        unit=unit or None,
        source=source or None,
    )


def assess_series_label_gate(deal: Any) -> dict[str, Any]:
    """Gate 4/6 assessor — synced series winners must carry complete eight labels."""
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
    from agetic_cdd_api.services_fact_repository import facts_for

    gaps: list[str] = []
    winners = 0
    for row in facts_for(deal_id):
        if not _is_series_sync_winner(row):
            continue
        winners += 1
        labels = eight_labels_from_series_fact(row)
        missing = labels.missing_fields()
        if missing:
            from agetic_cdd_api.services_databook_view import _fiscal_year, _metric_for_concept

            metric = _metric_for_concept(str(row.get("concept_id") or ""))
            year = _fiscal_year(row)
            gaps.append(
                f"labels_incomplete:{metric}:FY{year}:{','.join(missing)}"
            )
    ok = winners == 0 or not gaps
    return {
        "ok": ok,
        "winners": winners,
        "gaps": gaps,
        "summary": (
            "series labels complete"
            if ok
            else f"SERIES LABELS INCOMPLETE: {'; '.join(gaps[:5])}"
        ),
    }


def _is_series_sync_winner(row: dict[str, Any]) -> bool:
    """True when this fact should be promoted into the labelled release (Gate 6)."""
    from agetic_cdd_api.services_databook_view import _metric_for_concept

    if str(row.get("status") or "") not in _CHOSEN:
        return False
    if row.get("value") is None:
        return False
    metric = _metric_for_concept(str(row.get("concept_id") or ""))
    if metric not in _SERIES_SYNC_METRICS:
        return False
    basis = str(row.get("basis") or "ACTUAL").upper()
    return basis == "ACTUAL"


def _is_material_series_winner(row: dict[str, Any]) -> bool:
    """Backward-compatible alias for :func:`_is_series_sync_winner`."""
    return _is_series_sync_winner(row)


def _file_name(row: dict[str, Any]) -> str:
    name = str(row.get("file_name") or "").strip()
    if name:
        return name
    mapping = row.get("mapping") if isinstance(row.get("mapping"), dict) else {}
    return str(mapping.get("file_name") or "").strip()


def _source_basis(row: dict[str, Any]) -> SourceBasis:
    from agetic_cdd_api.services_databook_classify import infer_basis

    doc_type = str(row.get("doc_type") or "")
    if "AUDITED" in doc_type.upper():
        return SourceBasis.AUDITED
    if doc_type.startswith("FIN_QOE") or "ADVISER" in doc_type.upper():
        return SourceBasis.ADVISER
    if doc_type.startswith("FIN_"):
        return SourceBasis.MANAGEMENT
    inferred = infer_basis(_file_name(row), cdl_category=doc_type)
    if inferred != SourceBasis.UNKNOWN:
        return inferred
    return SourceBasis.MANAGEMENT


def _proof_level(row: dict[str, Any], basis: SourceBasis) -> ProofLevel:
    tier = str(row.get("evidence_tier") or "").upper()
    if basis == SourceBasis.AUDITED or tier == "A":
        return ProofLevel.L2
    if basis in {SourceBasis.MANAGEMENT, SourceBasis.ADVISER}:
        return ProofLevel.L2
    return ProofLevel.L2


def _statement_for_concept(concept_id: str) -> str | None:
    if concept_id.startswith("fin.pl."):
        return "IS"
    if concept_id.startswith("fin.bs."):
        return "BS"
    if concept_id.startswith("fin.cf."):
        return "CF"
    return "IS"


def _scale_label(raw: Any) -> str | None:
    try:
        number = int(float(raw))
    except (TypeError, ValueError):
        return None
    return _SCALE_MAP.get(number)


def _cell_rc(cell_range: str | None) -> tuple[int | None, int | None]:
    text = str(cell_range or "").strip().upper()
    match = re.match(r"^([A-Z]+)(\d+)", text)
    if not match:
        return None, None
    col_letters, row_s = match.group(1), match.group(2)
    col = 0
    for ch in col_letters:
        col = col * 26 + (ord(ch) - 64)
    return int(row_s), col


def _sync_fdd_manifest_contract(deal_slug: str, assessment: Any) -> None:
    """Keep an open FDD run aligned with the refreshed databook contract."""
    try:
        from agetic_cdd_api.services_fdd_store import load_current_manifest, save_manifest
    except Exception:
        return
    manifest = load_current_manifest(deal_slug)
    if manifest is None:
        return
    save_manifest(
        manifest.model_copy(
            update={
                "draft_mode": bool(assessment.draft_mode),
                "contract_complete": bool(assessment.complete),
                "g6_blocked": not bool(assessment.g6_allowed),
                "contract_reasons": list(assessment.reasons or []),
                "databook_release_id": getattr(assessment, "release_id", None)
                or manifest.databook_release_id,
                "databook_release_version": getattr(assessment, "release_version", None)
                or manifest.databook_release_version,
            }
        )
    )
