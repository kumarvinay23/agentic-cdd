"""Ontology-backed Databook read model: `/view` series grid and `/lines` inventory.

Builds DiligenceIQ-shaped JSON from Postgres (`v_databook_fact`, `fact`, `document`,
`v_open_flags`) when `AGETIC_CDD_DATABOOK_DATABASE_URL` is set. Never falls back to
the file-backed promote path.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Iterable

from agetic_cdd_api.services_databook_view_models import (
    DatabookDqIssue,
    DatabookFileEntry,
    DatabookLineRow,
    DatabookLinesResponse,
    DatabookSeriesCell,
    DatabookTotals,
    DatabookViewResponse,
)
from agetic_cdd_api.services_deal_profile import published_databook
from agetic_cdd_api.settings import settings

# UI series keys (remote Financial history) ← ontology concept_id.
# Prefer totals when both a parent and a detail line map to the same key.
_SERIES_CONCEPTS: dict[str, str] = {
    "fin.pl.revenue": "revenue",
    "fin.pl.cost_of_sales": "cogs",
    "fin.pl.cos.goods": "cogs",  # "COGS" / "cost of goods sold" captions land here
    "fin.pl.gross_profit": "gross_profit",
    "fin.pl.ebitda": "ebitda",
    "fin.pl.operating_income": "ebit",
    "fin.pl.net_income": "net_income",
    "fin.bs.cash": "cash",
    "fin.bs.total_assets": "total_assets",
    "fin.bs.equity": "equity",
}

_CONCEPT_TO_METRIC = dict(_SERIES_CONCEPTS)
_SERIES_PRIORITY: dict[str, tuple[str, ...]] = {
    "cogs": ("fin.pl.cost_of_sales", "fin.pl.cos.goods"),
}

_STATEMENT_LABEL = {
    "PL": "schedule",
    "BS": "schedule",
    "CF": "schedule",
    "EQ": "schedule",
}

_DQ_LABEL = {
    "conflict": "Sources disagree",
    "assumed": "Assumption made",
    "untyped": "Untyped",
}


def build_databook_view(deal_id: str) -> DatabookViewResponse:
    """Financial history + file register + shared DQ chips."""
    deal_id = str(deal_id or "").strip()
    url = settings.databook_database_url.strip()
    if not deal_id:
        return _empty_view("unpublished")
    if not url:
        return _empty_view("unpublished")
    deal_row = _deal_row(url, deal_id)
    if not deal_row:
        # No ontology row is not a job in progress.
        return _empty_view("unpublished")

    published = published_databook(deal_id) or {}
    reporting_currency = str(
        published.get("reporting_currency")
        or deal_row.get("reporting_currency")
        or ""
    )
    actual_through = _actual_through_year(
        published.get("latest_actual_month") or deal_row.get("latest_actual_month")
    )

    files = _load_files(url, deal_id)
    view_rows = _load_view_facts(url, deal_id)
    all_facts = _load_line_facts(url, deal_id)
    open_flag_rows = _load_open_flags(url, deal_id)

    issue_index = _build_issue_index(all_facts, open_flag_rows)
    series, dq_cells = _build_series(view_rows, all_facts, issue_index, reporting_currency)
    line_rows = _facts_to_lines(all_facts, issue_index, actual_through)
    mapped = sum(1 for row in line_rows if row.metric)
    totals = DatabookTotals(
        rows=len(line_rows),
        mapped_rows=mapped,
        metrics=len(series),
        documents_parsed=sum(1 for f in files if not f.empty),
        candidates=sum(1 for f in all_facts if str(f.get("status") or "") == "CANDIDATE"),
        building=0,
        suspect_rows=sum(1 for row in line_rows if row.suspect),
    )
    return DatabookViewResponse(
        files=files,
        series=series,
        model=None,
        totals=totals,
        reporting_currency=reporting_currency,
        actual_through=actual_through,
        dq_cells=dq_cells,
        status="ready",
    )


def build_databook_lines(
    deal_id: str,
    *,
    q: str = "",
    unmapped: bool = False,
    issue: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> DatabookLinesResponse:
    """Full extraction inventory as `{ rows: Line[] }`."""
    deal_id = str(deal_id or "").strip()
    url = settings.databook_database_url.strip()
    if not deal_id or not url or not _deal_row(url, deal_id):
        return DatabookLinesResponse(rows=[])

    deal_row = _deal_row(url, deal_id) or {}
    published = published_databook(deal_id) or {}
    actual_through = _actual_through_year(
        published.get("latest_actual_month") or deal_row.get("latest_actual_month")
    )
    all_facts = _load_line_facts(url, deal_id)
    open_flag_rows = _load_open_flags(url, deal_id)
    issue_index = _build_issue_index(all_facts, open_flag_rows)
    rows = _facts_to_lines(all_facts, issue_index, actual_through)
    rows = filter_line_rows(rows, q=q, unmapped=unmapped, issue=issue)
    if offset:
        rows = rows[offset:]
    if limit is not None and limit >= 0:
        rows = rows[:limit]
    return DatabookLinesResponse(rows=rows)


def filter_line_rows(
    rows: Iterable[DatabookLineRow],
    *,
    q: str = "",
    unmapped: bool = False,
    issue: str | None = None,
) -> list[DatabookLineRow]:
    """Case-insensitive `q` on caption/file (and raw/sheet); optional unmapped / issue filters."""
    needle = (q or "").strip().lower()
    issue_key = (issue or "").strip().lower()
    out: list[DatabookLineRow] = []
    for row in rows:
        if unmapped and row.metric:
            continue
        if needle and not _row_matches_q(row, needle):
            continue
        if issue_key and not _row_matches_issue(row, issue_key):
            continue
        out.append(row)
    return out


def _row_matches_q(row: DatabookLineRow, needle: str) -> bool:
    hay = " ".join(
        [
            row.line_item or "",
            row.source or "",
            row.raw or "",
            row.sheet or "",
        ]
    ).lower()
    return needle in hay


def _row_matches_issue(row: DatabookLineRow, issue_key: str) -> bool:
    if not row.dq:
        return False
    if issue_key in {"any", "*"}:
        return True
    return any(item.kind == issue_key for item in row.dq)


def _empty_view(status: str) -> DatabookViewResponse:
    building = 1 if status == "building" else 0
    return DatabookViewResponse(
        files=[],
        series={},
        model=None,
        totals=DatabookTotals(building=building),
        reporting_currency="",
        actual_through=None,
        dq_cells={},
        status=status,  # type: ignore[arg-type]
    )


def _actual_through_year(latest_actual_month: Any) -> int | None:
    text = str(latest_actual_month or "").strip()
    if not text:
        return None
    match = re.match(r"^(\d{4})", text)
    return int(match.group(1)) if match else None


def _metric_for_concept(concept_id: str) -> str:
    return _CONCEPT_TO_METRIC.get(concept_id, "")


def _fiscal_year(row: dict[str, Any]) -> int | None:
    fy = row.get("fiscal_year")
    if fy is not None:
        try:
            return int(fy)
        except (TypeError, ValueError):
            pass
    period_end = str(row.get("period_end") or "")
    match = re.match(r"^(\d{4})", period_end)
    return int(match.group(1)) if match else None


def _statement_class(statement: str | None, sheet: str | None) -> str:
    if statement and statement in _STATEMENT_LABEL:
        return _STATEMENT_LABEL[statement]
    if statement:
        return str(statement).lower()
    if sheet:
        return "schedule"
    return ""


def _kind_and_unit(unit_type: str | None) -> tuple[str, str]:
    ut = str(unit_type or "").upper()
    if ut == "PERCENT":
        return "percent", "%"
    if ut in {"RATIO", "MULTIPLE"}:
        return "percent", ""
    return "money", ""


_SERIES_STATUS_RANK = {"SELECTED": 0, "DERIVED": 1, "COMPARATIVE": 2}


def _display_amount(value: float | None, source_currency: str, reporting_currency: str) -> tuple[float | None, str, bool]:
    """Series display in the confirmed currency. The fact row is not written.

    The number stays the stored amount. No exchange rate is applied. When the
    source code differs from the confirmed code, the cell is marked foreign.
    """
    source = (source_currency or "").strip()
    reporting = (reporting_currency or "").strip()
    if not reporting or source == reporting:
        return value, source or reporting, False
    return value, reporting, True


def _build_series(
    view_rows: list[dict[str, Any]],
    all_facts: list[dict[str, Any]],
    issue_index: dict[str, list[DatabookDqIssue]],
    reporting_currency: str = "",
) -> tuple[dict[str, dict[str, DatabookSeriesCell]], dict[str, list[DatabookDqIssue]]]:
    """Prefer published SELECTED/DERIVED; fill gaps from COMPARATIVE source totals for series concepts."""
    series: dict[str, dict[str, DatabookSeriesCell]] = {}
    dq_cells: dict[str, list[DatabookDqIssue]] = {}
    winners: dict[tuple[str, int], tuple[str, int, str]] = {}
    # (metric, year) → (concept_id, status_rank, fact_id)
    candidates = list(view_rows) + [
        f for f in all_facts if str(f.get("status") or "") == "COMPARATIVE"
    ]
    for row in candidates:
        concept_id = str(row.get("concept_id") or "")
        metric = _metric_for_concept(concept_id)
        year = _fiscal_year(row)
        if not metric or year is None or row.get("value") is None:
            continue
        status = str(row.get("status") or "SELECTED")
        status_rank = _SERIES_STATUS_RANK.get(status, 9)
        key = (metric, year)
        prior = winners.get(key)
        if prior is not None:
            prior_concept, prior_rank, _prior_fid = prior
            if status_rank > prior_rank:
                continue
            if status_rank == prior_rank and not _preferred_concept(metric, concept_id, prior_concept):
                continue
        winners[key] = (concept_id, status_rank, str(row.get("fact_id") or ""))
        sheet = str(row.get("sheet_or_page") or "")
        line_item = str(row.get("concept_label") or row.get("row_label_as_read") or metric)
        statement = _statement_class(row.get("statement"), sheet)
        raw = f"{sheet} · {line_item}" if sheet else line_item
        source = str(row.get("file_name") or "")
        stored_value = _as_float(row.get("value"))
        stored_currency = str(row.get("currency") or "")
        display_value, display_currency, foreign = _display_amount(
            stored_value, stored_currency, reporting_currency,
        )
        cell = DatabookSeriesCell(
            value=display_value,
            currency=display_currency,
            foreign=foreign,
            source=source,
            line_item=line_item,
            statement=statement,
            raw=raw,
            suspect=False,
            fact_id=str(row.get("fact_id") or "") or None,
        )
        series.setdefault(metric, {})[str(year)] = cell
        flags = list(issue_index.get(str(row.get("fact_id") or ""), []))
        figure_key = f"{metric}|{year}"
        flags.extend(issue_index.get(figure_key, []))
        mapping = row.get("mapping") if isinstance(row.get("mapping"), dict) else {}
        if str(mapping.get("currency_source") or "") == "assumed":
            flags.append(
                _issue_for_key(
                    f"assumed-currency:{row.get('fact_id') or figure_key}",
                    "assumed",
                    "Reporting currency inherited; source grid omitted ISO code",
                )
            )
        deduped = _dedupe_issues(flags)
        if deduped:
            dq_cells[figure_key] = deduped
    return series, dq_cells


def _preferred_concept(metric: str, candidate: str, incumbent: str) -> bool:
    """True when candidate should replace the incumbent series cell for this metric."""
    order = _SERIES_PRIORITY.get(metric)
    if not order:
        return True
    if candidate in order and incumbent in order:
        return order.index(candidate) < order.index(incumbent)
    if candidate in order:
        return True
    if incumbent in order:
        return False
    return True


def _facts_to_lines(
    facts: list[dict[str, Any]],
    issue_index: dict[str, list[DatabookDqIssue]],
    actual_through: int | None,
) -> list[DatabookLineRow]:
    rows: list[DatabookLineRow] = []
    for fact in facts:
        year = _fiscal_year(fact)
        if year is None:
            continue
        concept_id = str(fact.get("concept_id") or "")
        metric = _metric_for_concept(concept_id)
        sheet = str(fact.get("sheet_or_page") or "")
        line_item = str(
            fact.get("row_label_as_read")
            or fact.get("concept_label")
            or concept_id
            or "line"
        )
        statement = _statement_class(fact.get("statement"), sheet)
        source = str(fact.get("file_name") or fact.get("path") or "")
        raw = f"{sheet} · {line_item}" if sheet else line_item
        value = _as_float(fact.get("value"))
        printed_raw = str(fact.get("value_as_read") or "")
        printed = _as_float(fact.get("value_as_read"))
        if printed is None:
            printed = value
        scale_num = fact.get("scale_applied")
        try:
            scale = float(scale_num) if scale_num is not None else 1.0
        except (TypeError, ValueError):
            scale = 1.0
        scale_applied_bool = scale_num is not None
        kind, unit = _kind_and_unit(fact.get("unit_type"))
        currency = str(fact.get("currency") or "")
        basis = str(fact.get("basis") or "").upper()
        forecast: bool | None = None
        if basis in {"FORECAST", "BUDGET", "MGMT_CASE"} or (
            actual_through is not None and year > actual_through
        ):
            forecast = True
        mapping = fact.get("mapping") if isinstance(fact.get("mapping"), dict) else {}
        scale_source = str(mapping.get("scale_source") or mapping.get("classification") or "")
        if not scale_source and scale_applied_bool:
            scale_source = "sheet"
        scale_confidence = str(mapping.get("confidence") or "")
        if not scale_confidence and scale_applied_bool:
            scale_confidence = "high"
        fact_id = str(fact.get("fact_id") or "")
        token = str(fact.get("cell_range") or "")
        # Same caption × year can appear from multiple cells; keep React keys unique.
        key = fact_id or f"{source}|{statement}|{sheet}|{line_item}|{year}|{token}|{basis}"
        flags = list(issue_index.get(fact_id, []))
        figure_key = f"{metric}|{year}" if metric else ""
        if figure_key:
            flags.extend(issue_index.get(figure_key, []))
        currency_source = str(mapping.get("currency_source") or "")
        if currency_source == "assumed" or (
            not currency and kind == "money" and value is not None
        ):
            flags.append(
                _issue_for_key(
                    f"assumed-currency:{fact_id or key}",
                    "assumed",
                    "Reporting currency inherited; source grid omitted ISO code"
                    if currency_source == "assumed"
                    else "Currency not stated on the source line",
                )
            )
        rows.append(
            DatabookLineRow(
                key=key,
                statement=statement,
                sheet=sheet,
                line_item=line_item,
                period=year,
                value=value,
                value_base=value,
                printed=printed,
                printed_number=printed,
                printed_raw=printed_raw,
                scale=scale,
                scale_declared=scale,
                scale_source=scale_source,
                scale_confidence=scale_confidence,
                scale_applied=scale_applied_bool,
                kind=kind,
                unit=unit,
                currency=currency,
                metric=metric,
                subtotal=str(fact.get("status") or "") == "COMPARATIVE",
                note="",
                suspect=str(fact.get("status") or "") == "HELD",
                forecast=forecast,
                source=source,
                raw=raw,
                token=str(fact.get("cell_range") or ""),
                block=sheet,
                dq=_dedupe_issues(flags),
                fact_id=fact_id or None,
            )
        )
    rows.sort(key=lambda r: (r.source, r.sheet, r.line_item, r.period))
    return rows


def _build_issue_index(
    facts: list[dict[str, Any]],
    open_flag_rows: list[dict[str, Any]],
) -> dict[str, list[DatabookDqIssue]]:
    """Map fact_id and metric|year → shared DQ issues with stable `n`."""
    index: dict[str, list[DatabookDqIssue]] = defaultdict(list)

    # Conflicts: more than one live value for the same figure key.
    # Once a reviewer (or the resolver) has a SELECTED/DERIVED row, comparative
    # leftovers are the recorded reason, not an open disagreement.
    by_figure: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        status = str(fact.get("status") or "")
        if status in {"REJECTED", "HELD"}:
            continue
        metric = _metric_for_concept(str(fact.get("concept_id") or ""))
        year = _fiscal_year(fact)
        if not metric or year is None:
            continue
        by_figure[(metric, year)].append(fact)

    for (metric, year), group in by_figure.items():
        chosen = [f for f in group if str(f.get("status") or "") in {"SELECTED", "DERIVED"}]
        # Candidates still disagree with the chosen value. Comparative rows are the
        # recorded reason after a reviewer or the resolver has picked one.
        open_rows = [
            f
            for f in group
            if str(f.get("status") or "") in {"SELECTED", "DERIVED", "CANDIDATE"}
        ]
        pool = open_rows if chosen else group
        values = {
            round(float(f["value"]), 6)
            for f in pool
            if f.get("value") is not None
        }
        if len(values) < 2:
            continue
        detail_bits = []
        for f in pool:
            if f.get("value") is None:
                continue
            detail_bits.append(
                f"{f.get('value')} as '{f.get('row_label_as_read') or f.get('concept_label')}' "
                f"in {f.get('file_name') or 'document'}"
            )
        issue = _issue_for_key(
            f"conflict:{metric}|{year}",
            "conflict",
            "Stated across documents: " + "; ".join(detail_bits[:6]),
        )
        figure_key = f"{metric}|{year}"
        index[figure_key].append(issue)
        for f in pool:
            fid = str(f.get("fact_id") or "")
            if fid:
                index[fid].append(issue)

    for flag in open_flag_rows:
        kind = _flag_kind(flag)
        issue = _issue_for_key(
            str(flag.get("flag_id") or flag.get("code") or flag.get("message") or "flag"),
            kind,
            str(flag.get("message") or flag.get("rule") or flag.get("code") or ""),
        )
        for fact_id in flag.get("fact_ids") or []:
            index[str(fact_id)].append(issue)

    for fact in facts:
        status = str(fact.get("status") or "")
        fid = str(fact.get("fact_id") or "")
        if status == "HELD" and fid:
            index[fid].append(
                _issue_for_key(
                    f"held:{fid}",
                    "untyped",
                    str(fact.get("reason_detail") or fact.get("reason_code") or "Held for review"),
                )
            )
    return index


def _flag_kind(flag: dict[str, Any]) -> str:
    code = str(flag.get("code") or "").upper()
    message = str(flag.get("message") or "").lower()
    if "currency" in message or "scale" in message or "assum" in message:
        return "assumed"
    if "disagree" in message or "conflict" in message or code.startswith("R-"):
        return "conflict"
    return "untyped"


def _issue_for_key(stable_key: str, kind: str, detail: str) -> DatabookDqIssue:
    n = _stable_n(stable_key)
    return DatabookDqIssue(
        n=n,
        kind=kind,  # type: ignore[arg-type]
        label=_DQ_LABEL.get(kind, kind),
        detail=detail,
    )


def _stable_n(key: str) -> int:
    """Positive int in a UI-friendly range, stable across rebuilds for the same key."""
    # FNV-1a 32-bit
    h = 2166136261
    for ch in key.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % 9000) + 1000


def _dedupe_issues(issues: list[DatabookDqIssue]) -> list[DatabookDqIssue]:
    seen: set[int] = set()
    out: list[DatabookDqIssue] = []
    for item in issues:
        if item.n in seen:
            continue
        seen.add(item.n)
        out.append(item)
    out.sort(key=lambda i: i.n)
    return out


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        cleaned = re.sub(r"[^0-9eE.+-]", "", str(value))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None


# --- Postgres loaders ---------------------------------------------------------


def _sql(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _json_list(stdout: str) -> list[dict[str, Any]]:
    start, end = stdout.find("["), stdout.rfind("]")
    if start < 0 or end < start:
        return []
    payload = json.loads(stdout[start : end + 1])
    return payload if isinstance(payload, list) else []


def _json_object(stdout: str) -> dict[str, Any] | None:
    start, end = stdout.find("{"), stdout.rfind("}")
    if start < 0 or end < start:
        return None
    payload = json.loads(stdout[start : end + 1])
    return payload if isinstance(payload, dict) else None


def _deal_row(url: str, deal_id: str) -> dict[str, Any] | None:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT row_to_json(d)::text FROM deal d "
        f"WHERE d.deal_id = {_sql(deal_id)};",
    )
    if result.returncode != 0:
        return None
    return _json_object(result.stdout)


def _load_files(url: str, deal_id: str) -> list[DatabookFileEntry]:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT coalesce(json_agg(row_to_json(d) ORDER BY d.file_name), '[]'::json)::text "
        "FROM document d "
        f"WHERE d.deal_id = {_sql(deal_id)};",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "databook document read failed")
    files: list[DatabookFileEntry] = []
    for row in _json_list(result.stdout):
        status = str(row.get("status") or "")
        empty = status in {"SKIPPED", "EMPTY"} or bool(row.get("status_reason"))
        files.append(
            DatabookFileEntry(
                file=str(row.get("file_name") or ""),
                path=str(row.get("path") or row.get("file_name") or ""),
                doc_id=str(row.get("doc_id") or "") or None,
                status=status,
                status_reason=row.get("status_reason"),
                doc_type=row.get("doc_type"),
                evidence_tier=row.get("evidence_tier"),
                extraction={"method": "structural"},
                empty=empty,
                doc_facts=int(row.get("facts_count") or 0),
            )
        )
    return files


def _load_view_facts(url: str, deal_id: str) -> list[dict[str, Any]]:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT coalesce(json_agg(row_to_json(v)), '[]'::json)::text "
        f"FROM v_databook_fact v WHERE v.deal_id = {_sql(deal_id)};",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "databook view read failed")
    return _json_list(result.stdout)


def _load_line_facts(url: str, deal_id: str) -> list[dict[str, Any]]:
    """All non-rejected facts with source/document labels for the inventory."""
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT coalesce(json_agg(row_to_json(x)), '[]'::json)::text FROM ("
        "SELECT f.fact_id, f.deal_id, f.concept_id, c.label AS concept_label, c.statement, "
        "f.value, f.unit_type, f.currency, f.scale_applied, f.period_type, f.period_end, "
        "f.fiscal_year, f.basis, f.status, f.reason_code, f.reason_detail, f.mapping, "
        "d.file_name, d.path, sl.sheet_or_page, sl.cell_range, sl.value_as_read, "
        "sl.row_label_as_read "
        "FROM fact f "
        "JOIN onto_concept c ON c.version = f.ontology_version AND c.concept_id = f.concept_id "
        "LEFT JOIN source_location sl ON sl.location_id = f.source_location_ids[1] "
        "LEFT JOIN document d ON d.doc_id = COALESCE(sl.doc_id, f.doc_id) "
        f"WHERE f.deal_id = {_sql(deal_id)} AND f.status <> 'REJECTED'"
        ") x;",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "databook lines read failed")
    return _json_list(result.stdout)


def _load_open_flags(url: str, deal_id: str) -> list[dict[str, Any]]:
    from agetic_cdd_api.services_databook_migrate import psql
    from agetic_cdd_api.services_rule_checker import open_flags

    memory = open_flags(deal_id)
    result = psql(
        url,
        "SELECT coalesce(json_agg(row_to_json(v)), '[]'::json)::text "
        f"FROM v_open_flags v WHERE v.deal_id = {_sql(deal_id)};",
    )
    sql_rows: list[dict[str, Any]] = []
    if result.returncode == 0:
        sql_rows = _json_list(result.stdout)
        for row in sql_rows:
            # Align with in-memory flag shape.
            row.setdefault("flag_id", f"fl-{deal_id}-{row.get('code')}")
            row.setdefault("fact_ids", row.get("fact_ids") or [])
    # Prefer memory when present (same process as check_rules); else SQL.
    return memory or sql_rows
