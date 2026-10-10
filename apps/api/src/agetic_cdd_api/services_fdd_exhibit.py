"""FDD exhibit store — versioned cells with fact IDs (Phase 0)."""

from __future__ import annotations

from typing import Iterable

from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CellStatus,
    EvidenceTier,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
)
from agetic_cdd_api.services_fdd_store import (
    load_exhibit_store,
    save_exhibit_store,
)


def cell_ref(exhibit_id: str, cell_id: str) -> str:
    return f"{exhibit_id}.{cell_id}"


def parse_cell_ref(ref: str) -> tuple[str, str]:
    if "." not in ref:
        raise ValueError(f"Invalid cell ref (want exhibit_id.cell_id): {ref!r}")
    exhibit_id, cell_id = ref.split(".", 1)
    if not exhibit_id or not cell_id:
        raise ValueError(f"Invalid cell ref: {ref!r}")
    return exhibit_id, cell_id


def index_cells(store: ExhibitStoreDoc) -> dict[str, ExhibitCell]:
    """Build ``exhibit_id.cell_id`` → cell map for O(1) bulk lookups."""
    return {
        cell_ref(ex.exhibit_id, cell.cell_id): cell
        for ex in store.exhibits
        for cell in ex.cells
    }


def index_exhibits(store: ExhibitStoreDoc) -> dict[str, Exhibit]:
    """Build ``exhibit_id`` → exhibit map (last wins on duplicate ids)."""
    return {ex.exhibit_id: ex for ex in store.exhibits}


def get_cell(store: ExhibitStoreDoc, exhibit_id: str, cell_id: str) -> ExhibitCell | None:
    """Find a cell by exhibit_id and cell_id (stops after matching exhibit)."""
    for ex in store.exhibits:
        if ex.exhibit_id != exhibit_id:
            continue
        for cell in ex.cells:
            if cell.cell_id == cell_id:
                return cell
        break
    return None


def get_cell_indexed(
    cells: dict[str, ExhibitCell], exhibit_id: str, cell_id: str
) -> ExhibitCell | None:
    """O(1) cell lookup against a pre-built ``index_cells`` map."""
    return cells.get(cell_ref(exhibit_id, cell_id))


def upsert_exhibit(store: ExhibitStoreDoc, exhibit: Exhibit) -> ExhibitStoreDoc:
    exhibits = [e for e in store.exhibits if e.exhibit_id != exhibit.exhibit_id]
    exhibits.append(exhibit)
    exhibits.sort(key=lambda e: e.exhibit_id)
    return store.model_copy(update={"exhibits": exhibits})


def _default_shell_title(exhibit_id: str) -> str:
    return exhibit_id.replace("_", " ").title()


def upsert_cell(
    store: ExhibitStoreDoc,
    cell: ExhibitCell,
    *,
    exhibit_title: str | None = None,
    section_id: str | None = None,
) -> ExhibitStoreDoc:
    """Insert or replace a cell; creates a shell exhibit if missing.

    When synthesizing a shell, pass ``exhibit_title`` / ``section_id`` to avoid
    awkward auto-titles from abbreviations (e.g. ebitda_bridge_fy24).
    """
    # R2 — agents never seed exhibit figures (Phase 3 enforcement).
    from agetic_cdd_api.services_fdd_claims import assert_fact_id_not_agent_sourced

    assert_fact_id_not_agent_sourced(cell.fact_id)

    exhibits = list(store.exhibits)
    found_ex = False
    for i, ex in enumerate(exhibits):
        if ex.exhibit_id != cell.exhibit_id:
            continue
        found_ex = True
        cells = [c for c in ex.cells if c.cell_id != cell.cell_id]
        cells.append(cell)
        cells.sort(key=lambda c: c.cell_id)
        exhibits[i] = ex.model_copy(update={"cells": cells})
        break
    if not found_ex:
        exhibits.append(
            Exhibit(
                exhibit_id=cell.exhibit_id,
                title=exhibit_title or _default_shell_title(cell.exhibit_id),
                section_id=section_id,
                cells=[cell],
            )
        )
        exhibits.sort(key=lambda e: e.exhibit_id)
    return store.model_copy(update={"exhibits": exhibits})


def upsert_cells(
    store: ExhibitStoreDoc,
    cells: Iterable[ExhibitCell],
    *,
    exhibit_titles: dict[str, str] | None = None,
    section_ids: dict[str, str] | None = None,
) -> ExhibitStoreDoc:
    """Batch upsert cells in one pass over exhibits (avoids O(updates·E·C)).

    Groups incoming cells by exhibit_id, then rewrites each affected exhibit once.
    """
    by_exhibit: dict[str, dict[str, ExhibitCell]] = {}
    for cell in cells:
        by_exhibit.setdefault(cell.exhibit_id, {})[cell.cell_id] = cell
    if not by_exhibit:
        return store

    titles = exhibit_titles or {}
    sections = section_ids or {}
    existing = index_exhibits(store)
    exhibits = [ex for ex in store.exhibits if ex.exhibit_id not in by_exhibit]

    for exhibit_id, incoming in sorted(by_exhibit.items()):
        prior = existing.get(exhibit_id)
        if prior is None:
            merged = sorted(incoming.values(), key=lambda c: c.cell_id)
            exhibits.append(
                Exhibit(
                    exhibit_id=exhibit_id,
                    title=titles.get(exhibit_id) or _default_shell_title(exhibit_id),
                    section_id=sections.get(exhibit_id),
                    cells=merged,
                )
            )
            continue
        kept = {c.cell_id: c for c in prior.cells}
        kept.update(incoming)
        exhibits.append(
            prior.model_copy(
                update={"cells": sorted(kept.values(), key=lambda c: c.cell_id)}
            )
        )

    exhibits.sort(key=lambda e: e.exhibit_id)
    return store.model_copy(update={"exhibits": exhibits})


def update_cell_value(
    store: ExhibitStoreDoc,
    exhibit_id: str,
    cell_id: str,
    value: float,
    *,
    display: str | None = None,
) -> ExhibitStoreDoc:
    cell = get_cell(store, exhibit_id, cell_id)
    if cell is None:
        raise KeyError(f"Unknown cell {cell_ref(exhibit_id, cell_id)}")
    updated = cell.model_copy(
        update={
            "value": float(value),
            "display": display if display is not None else _format_number(value),
        }
    )
    return upsert_cell(store, updated)


def update_cell_values(
    store: ExhibitStoreDoc,
    updates: dict[str, float],
    *,
    displays: dict[str, str] | None = None,
) -> ExhibitStoreDoc:
    """Bulk value updates keyed by ``exhibit_id.cell_id`` (indexed lookup)."""
    idx = index_cells(store)
    display_map = displays or {}
    revised: list[ExhibitCell] = []
    for ref, value in updates.items():
        cell = idx.get(ref)
        if cell is None:
            raise KeyError(f"Unknown cell {ref}")
        revised.append(
            cell.model_copy(
                update={
                    "value": float(value),
                    "display": display_map.get(ref, _format_number(value)),
                }
            )
        )
    return upsert_cells(store, revised)


def _format_number(value: float | None) -> str:
    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    return format_fdd_number(value)


DEFAULT_STUB_REVENUE_FY24 = 3140.0


def seed_phase0_hand_built_exhibit(
    store: ExhibitStoreDoc,
    *,
    revenue_fy24: float = DEFAULT_STUB_REVENUE_FY24,
    databook_release_id: str | None = None,
    databook_release_version: int | None = None,
) -> ExhibitStoreDoc:
    """Minimal hand-built exhibit for Phase 0 dual-render stub.

    ``fact_id`` is an explicit hand-seed id until Phase 1 binds real release facts.
    """
    common = dict(
        exhibit_id="ex_hist_pl",
        unit="USD",
        currency="USD",
        scale="M",
        figure_type=FigureType.REPORTED,
        evidence_tier=EvidenceTier.C,
        status=CellStatus.DRAFT,
        basis_label="Phase 0 hand-built seed",
        databook_release_id=databook_release_id,
        databook_release_version=databook_release_version,
    )
    ebitda = round(float(revenue_fy24) * 0.22, 2)
    exhibit = Exhibit(
        exhibit_id="ex_hist_pl",
        title="Historical P&L (stub)",
        section_id="SEC-B",
        status=ArtefactStatus.DRAFT,
        scale_header="USD M",
        cells=[
            ExhibitCell(
                cell_id="revenue_fy24",
                label="Revenue FY2024",
                value=float(revenue_fy24),
                display=_format_number(revenue_fy24),
                fiscal_year=2024,
                metric_key="revenue",
                fact_id="hand:revenue:2024",
                **common,
            ),
            ExhibitCell(
                cell_id="ebitda_fy24",
                label="EBITDA FY2024",
                value=float(ebitda),
                display=_format_number(ebitda),
                fiscal_year=2024,
                metric_key="ebitda",
                fact_id="hand:ebitda:2024",
                **common,
            ),
        ],
        footnotes=["Phase 0 stub — figures are hand-seeded pending databook bridge."],
    )
    store = upsert_exhibit(store, exhibit)
    # Second exhibit so the stub PDF/deck always has multiple pages/slides.
    bs = Exhibit(
        exhibit_id="ex_hist_bs",
        title="Balance sheet highlights (stub)",
        section_id="SEC-F",
        status=ArtefactStatus.DRAFT,
        scale_header="USD M",
        cells=[
            ExhibitCell(
                cell_id="cash_fy24",
                exhibit_id="ex_hist_bs",
                label="Cash FY2024",
                value=420.0,
                display=_format_number(420.0),
                unit="USD",
                currency="USD",
                scale="M",
                fiscal_year=2024,
                metric_key="cash",
                fact_id="hand:cash:2024",
                figure_type=FigureType.REPORTED,
                evidence_tier=EvidenceTier.C,
                status=CellStatus.DRAFT,
                basis_label="Phase 0 hand-built seed",
                databook_release_id=databook_release_id,
                databook_release_version=databook_release_version,
            )
        ],
        footnotes=["Phase 0 stub balance sheet highlight."],
    )
    return upsert_exhibit(store, bs)


def persist_store(deal_slug: str, run_id: str, store: ExhibitStoreDoc) -> ExhibitStoreDoc:
    return save_exhibit_store(
        store.model_copy(update={"deal_slug": deal_slug, "run_id": run_id})
    )


def load_or_empty(deal_slug: str, run_id: str) -> ExhibitStoreDoc:
    existing = load_exhibit_store(deal_slug, run_id)
    if existing is not None:
        return existing
    return ExhibitStoreDoc(run_id=run_id, deal_slug=deal_slug, updated_at="", exhibits=[])


def cells_matching(
    store: ExhibitStoreDoc, refs: Iterable[str]
) -> dict[str, ExhibitCell]:
    idx = index_cells(store)
    return {r: idx[r] for r in refs if r in idx}
