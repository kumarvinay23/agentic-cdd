"""Fix 2 — slide exhibit contracts: resolve rows, assert footing, refuse mismatch.

Each contracted slide declares additive row concepts (or dimension members),
periods, an optional dimension, and a total. The planner/renderer asserts
``sum(rows) == total`` per period and will not produce a matrix that fails.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from agetic_cdd_api.fdd_schemas import (
    ExhibitContract,
    ExhibitContractRow,
    SlideSpec,
    SlideTable,
)


class ExhibitFootingError(ValueError):
    """Raised when a contracted exhibit does not foot."""


@dataclass(frozen=True)
class ExhibitFootingResult:
    ok: bool
    period: str
    total: float | None
    row_sum: float | None
    delta: float | None
    message: str


def period_key(year: int) -> str:
    return str(int(year))


def _period_aliases(period: str) -> set[str]:
    raw = str(period or "").strip()
    if not raw:
        return set()
    out = {raw, raw.upper(), raw.lower()}
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 4:
        out.add(digits)
        out.add(f"FY{digits}")
        out.add(f"FY{digits[-2:]}")
        out.add(f"fy{digits}")
    elif len(digits) == 2:
        out.add(digits)
        out.add(f"FY{digits}")
        try:
            century = 2000 + int(digits)
            out.add(str(century))
            out.add(f"FY{century}")
        except ValueError:
            pass
    return out


def _lookup(values: dict[str, float], period: str) -> float | None:
    if not values:
        return None
    aliases = _period_aliases(period)
    for key, val in values.items():
        if str(key) in aliases or str(key).upper() in {a.upper() for a in aliases}:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
    return None


def _approx(
    a: float | None,
    b: float | None,
    *,
    abs_tol: float,
    rel_tol: float,
) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)


def check_exhibit_footing(contract: ExhibitContract) -> list[ExhibitFootingResult]:
    """Return one footing result per declared period (empty → skipped)."""
    periods = list(contract.periods or [])
    if not periods:
        # Infer from total / row keys.
        keys: set[str] = set(contract.total_values or {})
        for row in contract.rows or []:
            keys.update((row.values or {}).keys())
        periods = sorted(keys)
    if not periods:
        return [
            ExhibitFootingResult(
                ok=True,
                period="",
                total=None,
                row_sum=None,
                delta=None,
                message="No periods to foot — skipped",
            )
        ]

    results: list[ExhibitFootingResult] = []
    for period in periods:
        total = _lookup(contract.total_values or {}, period)
        row_vals: list[float] = []
        missing_rows = 0
        for row in contract.rows or []:
            val = _lookup(row.values or {}, period)
            if val is None:
                missing_rows += 1
                continue
            row_vals.append(float(val))
        concept = str(contract.total_concept or "total").replace("_", " ")
        period_lab = _client_period_label(period)
        if contract.require_all_rows and missing_rows:
            results.append(
                ExhibitFootingResult(
                    ok=False,
                    period=str(period),
                    total=total,
                    row_sum=None,
                    delta=None,
                    message=(
                        f"{period_lab} missing {missing_rows} row value(s) "
                        f"for {concept}"
                    ),
                )
            )
            continue
        if not row_vals and total is None:
            results.append(
                ExhibitFootingResult(
                    ok=True,
                    period=str(period),
                    total=None,
                    row_sum=None,
                    delta=None,
                    message=f"{period_lab} empty — skipped",
                )
            )
            continue
        if total is None:
            results.append(
                ExhibitFootingResult(
                    ok=False,
                    period=str(period),
                    total=None,
                    row_sum=sum(row_vals) if row_vals else None,
                    delta=None,
                    message=(
                        f"{period_lab} has row values but no {concept} total"
                    ),
                )
            )
            continue
        if not row_vals:
            results.append(
                ExhibitFootingResult(
                    ok=False,
                    period=str(period),
                    total=total,
                    row_sum=None,
                    delta=None,
                    message=(
                        f"{period_lab} has a {concept} total but no additive rows"
                    ),
                )
            )
            continue
        row_sum = float(sum(row_vals))
        ok = _approx(
            row_sum,
            total,
            abs_tol=float(contract.abs_tol),
            rel_tol=float(contract.rel_tol),
        )
        delta = row_sum - float(total)
        results.append(
            ExhibitFootingResult(
                ok=ok,
                period=str(period),
                total=float(total),
                row_sum=row_sum,
                delta=delta,
                message=(
                    f"{period_lab} {concept} foots"
                    if ok
                    else (
                        f"{period_lab} {concept} does not foot — "
                        f"rows vs total (Δ {delta:+.3f})"
                    )
                ),
            )
        )
    return results


def _client_period_label(period: object) -> str:
    raw = str(period or "").strip()
    if re.fullmatch(r"20\d{2}", raw):
        return f"FY{raw}"
    if raw.upper().startswith("FY"):
        return raw.upper()
    return raw or "Period"


def assert_exhibit_foots(contract: ExhibitContract) -> list[ExhibitFootingResult]:
    """Assert every period foots; raise ``ExhibitFootingError`` on the first failure."""
    results = check_exhibit_footing(contract)
    failed = [r for r in results if not r.ok]
    if failed:
        raise ExhibitFootingError(failed[0].message)
    return results


def stamp_footing_status(contract: ExhibitContract) -> ExhibitContract:
    """Return a copy with ``footing_status`` / ``footing_detail`` filled."""
    results = check_exhibit_footing(contract)
    failed = [r for r in results if not r.ok]
    if not results:
        return contract.model_copy(
            update={"footing_status": "skipped", "footing_detail": "No footing checks"}
        )
    if failed:
        return contract.model_copy(
            update={
                "footing_status": "failed",
                "footing_detail": failed[0].message,
            }
        )
    detail = "; ".join(r.message for r in results if r.message)[:400]
    return contract.model_copy(
        update={"footing_status": "ok", "footing_detail": detail}
    )


def _client_footing_detail(detail: str) -> str:
    """Strip internal contract ids (ex_*) from client-facing footing copy."""
    text = str(detail or "").strip()
    text = re.sub(r"\bex_[a-z0-9_]+\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" —;")
    return text or "Row sum does not equal total"


def held_table_for_failed_contract(
    contract: ExhibitContract,
    *,
    title: str = "Exhibit held",
) -> SlideTable:
    detail = _client_footing_detail(
        contract.footing_detail or "Row sum does not equal total"
    )
    return SlideTable(
        title=title,
        headers=["Item", "Status"],
        rows=[
            ["Exhibit", "Held — totals do not foot"],
            ["Detail", detail[:180] or "—"],
        ],
        basis="",
        source="Exhibit footing gate",
        evidence_tier="C",
    )


def apply_contract_or_hold(
    slide: SlideSpec,
    contract: ExhibitContract,
    *,
    mode: str | None = None,
) -> SlideSpec | None:
    """Attach a stamped contract.

    ``hard`` (default): replace the matrix with a held stub on footing failure.
    ``soft``: keep the matrix visible, mark completeness held, and footnote the
    delta so diligence content is not wiped for a stream-mix mismatch.
    """
    hold_mode = (mode or getattr(contract, "hold_mode", None) or "hard").strip().lower()
    if hold_mode not in {"hard", "soft"}:
        hold_mode = "hard"
    stamped = stamp_footing_status(contract)
    stamped = stamped.model_copy(update={"hold_mode": hold_mode})
    if stamped.footing_status != "failed":
        return slide.model_copy(update={"exhibit_contract": stamped})

    detail = (
        stamped.footing_detail
        or "Contracted exhibit rows do not sum to the declared total."
    )
    if hold_mode == "soft":
        # Soft hold keeps the matrix visible — do not paint · HELD on the banner.
        # Keep a short client note; contract_id stays on the stamped contract only.
        client_detail = _client_footing_detail(detail)
        footnotes = list(slide.footnotes or [])
        note = "Note: stream mix does not foot to reported revenue."
        if note not in footnotes:
            footnotes = [*footnotes, note][:5]
        return slide.model_copy(
            update={
                "exhibit_contract": stamped,
                "completeness_state": "complete",
                "completeness_detail": client_detail[:240],
                "footnotes": footnotes,
                "observations": [
                    "Do not price from stream totals until they foot to reported revenue.",
                    *(slide.observations or [])[:4],
                ][:6],
                "evidence_tier": slide.evidence_tier or "C",
            }
        )

    title = slide.table.title if slide.table is not None else "Exhibit held"
    return slide.model_copy(
        update={
            "headline": "Exhibit held — totals do not foot",
            "table": held_table_for_failed_contract(stamped, title=title),
            "kpis": [],
            "observations": [detail, *(slide.observations or [])[:3]][:6],
            "exhibit_contract": stamped,
            "evidence_tier": "C",
            "completeness_state": "held",
            "completeness_detail": detail[:240],
        }
    )


def enforce_exhibit_contracts(
    slides: Iterable[SlideSpec],
    *,
    drop_failed: bool = False,
) -> list[SlideSpec]:
    """Safety net: stamp/hold any slide that still carries an unchecked contract."""
    out: list[SlideSpec] = []
    for slide in slides:
        contract = getattr(slide, "exhibit_contract", None)
        if contract is None:
            out.append(slide)
            continue
        status = getattr(contract, "footing_status", "pending")
        hold_mode = str(getattr(contract, "hold_mode", "hard") or "hard").lower()
        if status in {"ok", "skipped", "failed"}:
            if drop_failed and status == "failed":
                continue
            # Hard-failed matrices must not stay numeric; soft-failed may.
            if status == "failed" and hold_mode != "soft" and slide.table is not None:
                rows = list(slide.table.rows or [])
                looks_held = any(
                    "do not foot" in str(c).lower()
                    for r in rows
                    for c in r
                )
                if not looks_held:
                    slide = slide.model_copy(
                        update={
                            "headline": "Exhibit held — totals do not foot",
                            "table": held_table_for_failed_contract(
                                contract,
                                title=slide.table.title or "Exhibit held",
                            ),
                            "kpis": [],
                            "completeness_state": "held",
                        }
                    )
            out.append(slide)
            continue
        held = apply_contract_or_hold(slide, contract)
        if held is None or (
            drop_failed
            and held.exhibit_contract
            and held.exhibit_contract.footing_status == "failed"
            and str(getattr(held.exhibit_contract, "hold_mode", "hard")) != "soft"
        ):
            if drop_failed:
                continue
            if held is not None:
                out.append(held)
            continue
        out.append(held)
    return out


def revenue_stream_contract_from_values(
    *,
    contract_id: str,
    years: Iterable[int],
    stream_fy: dict[str, dict[int, float | None]],
    total_fy: dict[int, float | None],
    total_concept: str = "revenue",
    dimension: str = "service_line",
    total_fact_ids: dict[str, str] | None = None,
    abs_tol: float = 0.02,
    rel_tol: float = 0.005,
) -> ExhibitContract:
    """Build a revenue-by-stream exhibit contract from numeric FY maps."""
    rows: list[ExhibitContractRow] = []
    for label, by_year in stream_fy.items():
        values: dict[str, float] = {}
        for y in years:
            val = by_year.get(int(y)) if by_year else None
            if val is None:
                continue
            try:
                values[period_key(int(y))] = float(val)
            except (TypeError, ValueError):
                continue
        if not values:
            continue
        rows.append(
            ExhibitContractRow(
                concept=str(label),
                label=str(label),
                values=values,
            )
        )
    totals: dict[str, float] = {}
    for y in years:
        val = total_fy.get(int(y))
        if val is None:
            continue
        try:
            totals[period_key(int(y))] = float(val)
        except (TypeError, ValueError):
            continue
    # Only declare periods that have a total or at least one row value.
    active: list[str] = []
    for y in years:
        key = period_key(int(y))
        if key in totals or any(key in (r.values or {}) for r in rows):
            active.append(key)
    return ExhibitContract(
        contract_id=contract_id,
        total_concept=total_concept,
        periods=active,
        dimension=dimension,
        rows=rows,
        total_values=totals,
        total_fact_ids=dict(total_fact_ids or {}),
        abs_tol=abs_tol,
        rel_tol=rel_tol,
        require_all_rows=False,
    )


def revenue_stream_contract_from_pack(
    pack: object,
    *,
    contract_id: str = "ex_revenue_by_stream",
    years: Iterable[int] | None = None,
    total_fy_override: dict[int, float] | None = None,
    total_fact_ids: dict[str, str] | None = None,
) -> ExhibitContract | None:
    """Derive a stream footing contract from a ``TradingPack``-like object."""
    stream_labels = list(getattr(pack, "stream_labels", None) or [])
    pack_years = list(years) if years is not None else list(getattr(pack, "years", ()) or ())
    if not stream_labels or not pack_years:
        return None
    fy_map = getattr(pack, "fy", None) or {}
    stream_fy: dict[str, dict[int, float | None]] = {}
    for label in stream_labels:
        by_year = fy_map.get(label) or {}
        stream_fy[str(label)] = {
            int(y): by_year.get(int(y)) for y in pack_years
        }
    total_fy: dict[int, float | None] = {}
    revenue_fy = getattr(pack, "revenue_fy", None) or {}
    revenue_line = fy_map.get("Revenue") or fy_map.get("Total Revenues") or {}
    for y in pack_years:
        if total_fy_override and int(y) in total_fy_override:
            total_fy[int(y)] = total_fy_override[int(y)]
            continue
        val = revenue_fy.get(int(y))
        if val is None:
            val = revenue_line.get(int(y))
        total_fy[int(y)] = val
    if not any(v is not None for v in total_fy.values()):
        return None
    if not any(
        any(v is not None for v in by.values()) for by in stream_fy.values()
    ):
        return None
    return revenue_stream_contract_from_values(
        contract_id=contract_id,
        years=pack_years,
        stream_fy=stream_fy,
        total_fy=total_fy,
        total_concept="revenue",
        dimension="service_line",
        total_fact_ids=total_fact_ids,
    )


def slide_may_draw_matrix(slide: SlideSpec) -> bool:
    """Renderer guard — hard-failed contracts must not paint their numeric matrix.

    Soft-held contracts keep the matrix so trading/transaction content survives a
    stream-mix footing gap, with held chrome instead of a blank stub.
    """
    contract = getattr(slide, "exhibit_contract", None)
    if contract is None:
        return True
    if getattr(contract, "footing_status", "ok") != "failed":
        return True
    return str(getattr(contract, "hold_mode", "hard") or "hard").lower() == "soft"
