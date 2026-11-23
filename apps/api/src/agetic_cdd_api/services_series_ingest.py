"""Gate 2 — fail loud when statement ingest yields no usable Financial history.

When the room contains statement-shaped (or FIN_*-typed) workbooks but Phase 1
stores no mapped series cells, data ingestion must not silently complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agetic_cdd_api.services_statement_reader import (
    SERIES_CONCEPT_IDS,
    _STATEMENT_XLSX_NAME,
    is_fin_typed_workbook,
    is_non_statement_document,
    xlsx_skip_reason,
)


class StatementIngestBlockedError(RuntimeError):
    """Statement-shaped sources present but Financial history series is empty."""


@dataclass
class StatementSeriesIngestGate:
    deal_id: str
    ok: bool
    expected: bool
    series_fact_count: int = 0
    series_metric_count: int = 0
    expected_files: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def blockers(self) -> list[str]:
        if self.ok:
            return []
        flags: list[str] = []
        for reason in self.reasons:
            key = str(reason).split(":", 1)[0]
            if key and key not in flags:
                flags.append(key)
        return flags or ["no_mapped_series"]

    def summary(self) -> str:
        if self.ok:
            if not self.expected:
                return "statement ingest: no statement-shaped workbooks expected"
            return (
                f"statement ingest ok — {self.series_fact_count} series facts, "
                f"{self.series_metric_count} Financial history metrics"
            )
        bits = ", ".join(self.blockers)
        sample = "; ".join(self.reasons[:5]) if self.reasons else "no mapped series"
        return f"STATEMENT INGEST FAILED ({bits}): {sample}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "expected": self.expected,
            "series_fact_count": self.series_fact_count,
            "series_metric_count": self.series_metric_count,
            "expected_files": list(self.expected_files),
            "reasons": list(self.reasons),
            "blockers": self.blockers,
            "source": self.source,
            "summary": self.summary(),
        }


def is_expected_statement_source(row: dict[str, Any]) -> bool:
    """True when this register row should contribute Financial history series."""
    name = str(row.get("file_name") or "")
    fmt = str(row.get("format") or "").lower()
    suffix_ok = name.lower().endswith((".xlsx", ".xlsm", ".xls"))
    if fmt not in {"xlsx", "xls", "xlsm"} and not suffix_ok:
        return False
    if is_non_statement_document(row.get("doc_type")):
        return False
    if _STATEMENT_XLSX_NAME.search(name):
        return True
    # Gate 5: typed financial packs must produce series even when the filename is opaque.
    return is_fin_typed_workbook(row)


def assess_statement_series_ingest(
    deal: Any,
    room_result: dict[str, Any] | None = None,
    *,
    error: BaseException | str | None = None,
) -> StatementSeriesIngestGate:
    """Assess whether statement ingest produced a usable mapped series."""
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "").strip()
    reasons: list[str] = []
    source = "room_result" if room_result is not None else "pre_read"

    if error is not None:
        reasons.append(f"read_failed:{error}")

    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url:
        reasons.append("databook_url_unset")

    room = room_result if isinstance(room_result, dict) else None
    if room_result is not None and room is None:
        reasons.append("statement_read_returned_invalid_payload")

    rows = list((room or {}).get("rows") or [])
    if not rows:
        try:
            from agetic_cdd_api.services_document_register import register_room

            rows = list(register_room(deal) or [])
            if source == "pre_read":
                source = "register_room"
        except Exception as exc:
            reasons.append(f"register_failed:{exc}")
            rows = []

    expected_rows = [row for row in rows if is_expected_statement_source(row)]
    expected_files = [str(row.get("file_name") or "") for row in expected_rows]
    expected = bool(expected_rows)

    facts = list((room or {}).get("facts") or [])
    series_facts = [fact for fact in facts if _is_series_fact(fact)]
    series_fact_count = len(series_facts)
    series_metric_count = _metric_count_from_facts(series_facts)

    # Trust an explicit room_result facts list. Only hit Postgres when the
    # caller did not supply facts (e.g. pre-read / register-only assessment).
    if (
        series_metric_count == 0
        and url
        and deal_id
        and room is not None
        and "facts" not in room
    ):
        try:
            from agetic_cdd_api.services_databook_view import build_databook_view

            view = build_databook_view(deal_id)
            series_metric_count = len(getattr(view, "series", None) or {})
            if series_metric_count:
                source = "databook_view"
        except Exception as exc:
            reasons.append(f"view_failed:{exc}")

    if expected:
        from pathlib import Path

        from agetic_cdd_api.services_vdr import documents_dir

        root = documents_dir(deal)
        for row in expected_rows:
            name = str(row.get("file_name") or "")
            path = root / name if name else None
            skip = None
            if path is not None and path.is_file():
                skip = xlsx_skip_reason(path, row)
            if skip:
                reasons.append(f"skipped:{name}:{skip}")

    # Zeros alone are not usable history — they flip Gate 2 green while poisoning
    # downstream claims/reconcile (FIN discovery harden).
    nonzero_series = sum(1 for fact in series_facts if _series_value_abs(fact) > 0.0)
    usable = series_fact_count > 0 or series_metric_count > 0
    if series_fact_count > 0 and nonzero_series == 0:
        reasons.append("zero_only_series_cells")
        usable = False
    if expected and not usable:
        if url:
            from agetic_cdd_api.services_deal_profile import published_databook

            if not published_databook(deal_id):
                reasons.append("profile_unpublished")
        if room is not None and not any(str(r).startswith("skipped:") for r in reasons):
            if "zero_only_series_cells" not in reasons:
                reasons.append("no_mapped_series_cells")
        if room is None and "databook_url_unset" not in reasons:
            if not any(str(r).startswith("read_failed:") for r in reasons):
                reasons.append("statement_read_returned_empty")

    # Gate 3: refuse multiple live SELECTED/DERIVED cells for one metric×year.
    from agetic_cdd_api.services_series_canonical import duplicate_metric_years

    if series_facts:
        dupes = duplicate_metric_years(series_facts)
    elif deal_id:
        dupes = duplicate_metric_years(deal_id=deal_id)
    else:
        dupes = []
    for dupe in dupes[:5]:
        reasons.append(
            f"multiple_canonical_series:{dupe['metric']}:FY{dupe['fiscal_year']}"
        )

    # Deduplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        text = str(reason)
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)

    ok = ((not expected) or usable) and not dupes
    return StatementSeriesIngestGate(
        deal_id=deal_id,
        ok=ok,
        expected=expected,
        series_fact_count=series_fact_count,
        series_metric_count=series_metric_count,
        expected_files=expected_files,
        reasons=deduped,
        source=source,
    )


def apply_statement_ingest_gate(
    deal: Any,
    room_result: dict[str, Any] | None = None,
    *,
    error: BaseException | str | None = None,
) -> StatementSeriesIngestGate:
    """Evaluate Gate 2; raise when statement sources expected but series empty."""
    gate = assess_statement_series_ingest(deal, room_result, error=error)
    if gate.ok:
        return gate
    raise StatementIngestBlockedError(gate.summary())


def _is_series_fact(fact: Any) -> bool:
    if isinstance(fact, dict):
        concept = str(fact.get("concept_id") or "")
        status = str(fact.get("status") or "")
        value = fact.get("value")
    else:
        concept = str(getattr(fact, "concept_id", "") or "")
        status = str(getattr(fact, "status", "") or "")
        value = getattr(fact, "value", None)
    if concept not in SERIES_CONCEPT_IDS:
        return False
    if status and status not in {"SELECTED", "HELD", "DERIVED", "COMPARATIVE"}:
        return False
    return value is not None


def _series_value_abs(fact: Any) -> float:
    """Absolute numeric magnitude for a series fact; non-numeric → 0."""
    if isinstance(fact, dict):
        value = fact.get("value")
    else:
        value = getattr(fact, "value", None)
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0.0


def _metric_count_from_facts(facts: list[Any]) -> int:
    metrics: set[str] = set()
    for fact in facts:
        if isinstance(fact, dict):
            concept = str(fact.get("concept_id") or "")
        else:
            concept = str(getattr(fact, "concept_id", "") or "")
        if concept in SERIES_CONCEPT_IDS:
            metrics.add(concept)
    return len(metrics)
