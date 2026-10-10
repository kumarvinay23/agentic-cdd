"""FDD Phase 0 dual-render stubs from one ``report_spec`` + exhibit store."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FddRunManifest,
    ReportSpec,
    ReportSpecNode,
    StubRenderPage,
    StubRenderResult,
)
from agetic_cdd_api.services_databook_consume import MATERIAL_METRIC_KEYS
from agetic_cdd_api.services_fdd_deps import rebuild_and_persist
from agetic_cdd_api.services_fdd_exhibit import (
    cell_ref,
    index_cells,
    load_or_empty,
    persist_store,
    seed_phase0_hand_built_exhibit,
)
from agetic_cdd_api.services_fdd_store import (
    create_run,
    get_current_run_id,
    load_current_manifest,
    load_exhibit_store,
    load_manifest,
    load_report_spec,
    save_report_spec,
)
from agetic_cdd_api.services_fdd_tokens import (
    client_facing_text,
    find_tokens,
    format_cell_display,
    make_token,
    resolve_text,
)

# Cap line items shown per exhibit page/slide (full store still holds all cells).
_MAX_CELLS_PER_EXHIBIT = 28


def _content_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _exhibit_sort_key(ex: Exhibit) -> tuple[str, str]:
    return (ex.section_id or "ZZZ", ex.title or ex.exhibit_id)


def _pick_cells(ex: Exhibit) -> tuple[list[ExhibitCell], int]:
    """Prefer material metrics, then fiscal year desc; return (cells, omitted)."""
    cells = list(ex.cells)
    if not cells:
        return [], 0

    def rank(c: ExhibitCell) -> tuple[int, int, str]:
        mat = 0 if (c.metric_key or "") in MATERIAL_METRIC_KEYS else 1
        year = -(c.fiscal_year or 0)
        return (mat, year, c.label or c.cell_id)

    ordered = sorted(cells, key=rank)
    shown = ordered[:_MAX_CELLS_PER_EXHIBIT]
    return shown, max(0, len(ordered) - len(shown))


def _strip_fy_from_label(label: str, fiscal_year: int | None) -> str:
    """Avoid ``FY2025 Cost of sales FY2025`` — year shown once in the suffix."""
    import re

    text = (label or "").strip()
    if not text:
        return text
    # Keep YTD / plan stamps intact (year is part of the period label).
    if re.search(r"\bYTD\b|\(plan\)", text, flags=re.IGNORECASE):
        return text
    # Drop any FY / calendar-year tokens already embedded in the caption.
    text = re.sub(
        r"\bFY\s*20\d{2}A?\b|\bFY\s*\d{2}A?\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if fiscal_year is not None:
        text = re.sub(rf"\b{int(fiscal_year)}\b", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -·,/|")
    return text or (label or "").strip()


def _exhibit_body(ex: Exhibit) -> tuple[str, list[str]]:
    """Markdown-ish body with tokens + cell_refs used."""
    import re

    shown, omitted = _pick_cells(ex)
    refs: list[str] = []
    lines: list[str] = []
    if ex.scale_header:
        lines.append(f"Scale: {ex.scale_header}")
    if not shown:
        lines.append("No cells in this exhibit.")
        return "\n".join(lines), refs

    lines.append("")
    for cell in shown:
        ref = cell_ref(ex.exhibit_id, cell.cell_id)
        refs.append(ref)
        token = make_token(ex.exhibit_id, cell.cell_id)
        raw_label = cell.label or cell.cell_id
        period_stamped = bool(
            re.search(r"\bYTD\b|\(plan\)", raw_label or "", flags=re.IGNORECASE)
        )
        fy = "" if period_stamped else (f"FY{cell.fiscal_year}" if cell.fiscal_year else "")
        from agetic_cdd_api.services_fdd_tokens import display_unit_for_cell

        unit = display_unit_for_cell(cell)
        status = cell.status.value if cell.status else ""
        # Year once (suffix) — strip duplicates already in the caption.
        clean = _strip_fy_from_label(raw_label, cell.fiscal_year)
        bits = [b for b in (fy, unit, status) if b]
        suffix = f" ({', '.join(bits)})" if bits else ""
        lines.append(f"• {clean}{suffix}: {token}")
    if omitted:
        lines.append(f"… and {omitted} more figure(s) in the exhibit store.")
    for note in (ex.footnotes or [])[:3]:
        lines.append(f"Note: {note}")
    return "\n".join(lines), refs


def build_phase0_report_spec(
    *,
    run_id: str,
    deal_slug: str,
    store: ExhibitStoreDoc,
    company: str | None = None,
) -> ReportSpec:
    """Shared spec: cover + one section/slide per exhibit (identical figures)."""
    idx = index_cells(store)
    name = company or deal_slug
    exhibits = sorted(
        (ex for ex in store.exhibits if ex.cells),
        key=_exhibit_sort_key,
    )
    n_cells = len(idx)
    n_ex = len(exhibits)

    nodes: list[ReportSpecNode] = [
        ReportSpecNode(
            node_id="sec_cover",
            kind="section",
            title="Cover",
            body=(
                f"Financial Due Diligence — {name}\n"
                f"Exhibits: {n_ex} · Figures: {n_cells}\n"
                "One report_spec drives both the PDF report and IC deck."
            ),
        ),
        ReportSpecNode(
            node_id="slide_title",
            kind="slide",
            title=f"FDD — {name}",
            body=(
                f"{n_ex} exhibit(s) · {n_cells} figure(s)\n"
                "Shared figures with the PDF report (R5)."
            ),
            slide_index=0,
        ),
    ]

    if not exhibits:
        nodes.append(
            ReportSpecNode(
                node_id="sec_empty",
                kind="section",
                title="Exhibits",
                body="No exhibit cells available.",
            )
        )
        nodes.append(
            ReportSpecNode(
                node_id="slide_empty",
                kind="slide",
                title="Exhibits",
                body="No exhibit cells available.",
                slide_index=1,
            )
        )
    else:
        for i, ex in enumerate(exhibits, start=1):
            body, refs = _exhibit_body(ex)
            nodes.append(
                ReportSpecNode(
                    node_id=f"sec_{ex.exhibit_id}",
                    kind="section",
                    title=ex.title or ex.exhibit_id,
                    body=body,
                    exhibit_id=ex.exhibit_id,
                    cell_refs=refs,
                )
            )
            nodes.append(
                ReportSpecNode(
                    node_id=f"slide_{ex.exhibit_id}",
                    kind="slide",
                    title=ex.title or ex.exhibit_id,
                    body=body,
                    exhibit_id=ex.exhibit_id,
                    cell_refs=refs,
                    slide_index=i,
                )
            )

    all_refs = sorted(idx.keys())
    nodes.append(
        ReportSpecNode(
            node_id="msg_close",
            kind="message",
            title="Assembly note",
            body=(
                "Phase 0/1 stub assembly — full A–K sections land in later phases. "
                "Every figure above resolves from the exhibit store via number tokens."
            ),
            cell_refs=all_refs[:1],
        )
    )

    figures = {ref: cell.value for ref, cell in idx.items()}
    return ReportSpec(
        spec_id=f"spec_{run_id}",
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at="",
        title=f"FDD Report — {name}",
        nodes=nodes,
        content_hash=_content_hash(
            {
                "figures": figures,
                "nodes": [n.model_dump(mode="json") for n in nodes],
            }
        ),
    )


def _shared_figures(
    spec: ReportSpec, store: ExhibitStoreDoc
) -> tuple[dict[str, float | None], dict[str, str]]:
    """Union of every cell_ref / token in the spec — identical for report and deck (R5)."""
    idx = index_cells(store)
    refs: set[str] = set()
    for node in spec.nodes:
        refs.update(node.cell_refs or [])
        for _raw, eid, cid in find_tokens(node.body or ""):
            refs.add(cell_ref(eid, cid))
    figures: dict[str, float | None] = {}
    displays: dict[str, str] = {}
    for ref in sorted(refs):
        cell = idx.get(ref)
        if cell is None:
            continue
        figures[ref] = cell.value
        displays[ref] = format_cell_display(cell)
    return figures, displays


def render_stub(
    *,
    kind: str,
    spec: ReportSpec,
    store: ExhibitStoreDoc,
) -> StubRenderResult:
    """Resolve tokens for report pages or deck slides from the same spec.

    Figure maps are identical across report/deck (R5) — taken from the full
    spec's cell_refs and tokens, not only the subset visible on each page.
    """
    if kind not in {"report", "deck"}:
        raise ValueError(f"kind must be report|deck, got {kind!r}")

    if kind == "report":
        # Cover + sections + closing message (exclude slides).
        nodes = [n for n in spec.nodes if n.kind in {"section", "message"}]
    else:
        # Title + exhibit slides + closing message (exclude report-only sections).
        nodes = [n for n in spec.nodes if n.kind in {"slide", "message"}]

    figures, displays = _shared_figures(spec, store)

    parts: list[str] = []
    pages: list[StubRenderPage] = []
    for node in nodes:
        resolved_body = resolve_text(node.body, store)
        resolved_title = resolve_text(node.title or "", store)
        # Client PDF/deck: no [F/A/M/Q] tags or req_* ids
        body_text = client_facing_text(resolved_body.text)
        title_text = client_facing_text(resolved_title.text) or (node.title or "")
        page_kind = node.kind
        if node.node_id == "sec_cover":
            page_kind = "cover"
        pages.append(
            StubRenderPage(
                title=title_text,
                body=body_text,
                kind=page_kind,  # type: ignore[arg-type]
                exhibit_id=node.exhibit_id,
            )
        )
        header = f"# {title_text}" if kind == "report" else f"## Slide: {title_text}"
        parts.append(f"{header}\n{body_text}")

    body = "\n\n".join(parts)
    return StubRenderResult(
        kind=kind,  # type: ignore[arg-type]
        run_id=spec.run_id,
        figures=figures,
        displays=displays,
        body=body,
        pages=pages,
        content_hash=_content_hash(
            {
                "kind": kind,
                "figures": figures,
                "pages": [p.model_dump(mode="json") for p in pages],
            }
        ),
    )


def ensure_phase0_run(
    deal_slug: str,
    *,
    databook_release_id: str | None = None,
    databook_release_version: int | None = None,
    company: str | None = None,
    revenue_fy24: float = 3140.0,
    force_new: bool = False,
    allow_pinned_release: bool = False,
    bridge_databook: bool = True,
    prefer_current_release: bool = False,
) -> tuple[FddRunManifest, ExhibitStoreDoc, ReportSpec]:
    """Get-or-create current run; Phase 1 bridges release facts when available.

    When ``prefer_current_release`` is True (report builders), a stale pin is
    advanced to the current databook release instead of raising ReleasePinError.
    Governed API paths keep the default refuse-on-stale-pin behaviour.
    """
    from agetic_cdd_api.services_fdd_bridge import (
        bridge_release_into_run,
        check_release_pin,
        resolve_release_for_deal,
    )

    if prefer_current_release and databook_release_id is None:
        current_pref = resolve_release_for_deal(deal_slug, bootstrap=True)
        if current_pref is not None:
            databook_release_id = current_pref.release_id
            databook_release_version = current_pref.version

    manifest: FddRunManifest | None = None
    if not force_new:
        manifest = load_current_manifest(deal_slug)
    if manifest is None:
        manifest = create_run(
            deal_slug,
            databook_release_id=databook_release_id,
            databook_release_version=databook_release_version,
            draft_mode=True,
            allow_pinned_release=allow_pinned_release,
            note="FDD foundations run",
        )

    store = load_or_empty(deal_slug, manifest.run_id)

    if bridge_databook:
        want_id = databook_release_id or manifest.databook_release_id
        want_version = (
            databook_release_version
            if databook_release_version is not None
            else manifest.databook_release_version
        )
        current = resolve_release_for_deal(deal_slug, bootstrap=False)
        # Report path: advance stale pin to current rather than refusing.
        if (
            prefer_current_release
            and current is not None
            and want_id
            and (
                want_id != current.release_id
                or (
                    want_version is not None
                    and int(want_version) != int(current.version)
                )
            )
        ):
            want_id = current.release_id
            want_version = current.version
        if want_id and not prefer_current_release:
            check_release_pin(
                manifest.model_copy(
                    update={
                        "databook_release_id": want_id,
                        "databook_release_version": want_version,
                        "allow_pinned_release": allow_pinned_release
                        or manifest.allow_pinned_release,
                    }
                ),
                current=current,
            )
        release = resolve_release_for_deal(
            deal_slug, release_id=want_id, bootstrap=True
        )
        if release is not None:
            manifest, _facts, store, _assessment = bridge_release_into_run(
                deal_slug,
                manifest.run_id,
                release=release,
                allow_pinned_release=allow_pinned_release
                or manifest.allow_pinned_release,
                company=company,
            )

    if not store.exhibits:
        store = seed_phase0_hand_built_exhibit(
            store,
            revenue_fy24=revenue_fy24,
            databook_release_id=manifest.databook_release_id,
            databook_release_version=manifest.databook_release_version,
        )
        store = persist_store(deal_slug, manifest.run_id, store)

    # Phase 2 — scope seed + G0 readiness scan (idempotent).
    try:
        from agetic_cdd_api.services_fdd_scope import ensure_phase2_artefacts

        ensure_phase2_artefacts(
            deal_slug,
            manifest.run_id,
            company=company,
        )
        refreshed = load_manifest(deal_slug, manifest.run_id)
        if refreshed is not None:
            manifest = refreshed
    except (OSError, ValueError, TypeError):
        # Readiness is best-effort on ensure; API scan endpoint is authoritative.
        pass

    # Phase 3 — claims ledger (best-effort; POST …/claims/build is authoritative).
    try:
        from agetic_cdd_api.services_fdd_claims import build_claims_ledger

        build_claims_ledger(deal_slug, manifest.run_id, update_manifest=True)
        refreshed = load_manifest(deal_slug, manifest.run_id)
        if refreshed is not None:
            manifest = refreshed
    except (OSError, ValueError, TypeError):
        pass

    # Phase 5a/5b — QoE (M4/SEC-E) + BS/NWC/net debt exhibits (M8/M5/M6).
    try:
        from agetic_cdd_api.services_fdd_models import ensure_phase5b_models

        store, _summary = ensure_phase5b_models(
            deal_slug,
            manifest.run_id,
            store=store,
            company=company,
            build_qoe=True,
        )
        refreshed = load_manifest(deal_slug, manifest.run_id)
        if refreshed is not None:
            manifest = refreshed
    except (OSError, ValueError, TypeError, ImportError):
        pass

    # Phase 6 + 7 — commentary (best-effort) then assemble full report_spec.
    try:
        from agetic_cdd_api.services_fdd_assemble import ensure_commentary_and_assemble

        _commentary, spec = ensure_commentary_and_assemble(
            deal_slug,
            manifest.run_id,
            store=store,
            company=company,
        )
        # Reload store — QoE / Phase 5b exhibits may have been added.
        store = load_exhibit_store(deal_slug, manifest.run_id) or store
        refreshed = load_manifest(deal_slug, manifest.run_id)
        if refreshed is not None:
            manifest = refreshed
    except (OSError, ValueError, TypeError, ImportError):
        spec = build_phase0_report_spec(
            run_id=manifest.run_id,
            deal_slug=deal_slug,
            store=store,
            company=company,
        )
        spec = save_report_spec(spec)
        rebuild_and_persist(deal_slug, run_id=manifest.run_id, store=store, spec=spec)
    return manifest, store, spec


# Alias — Phase 1 entrypoint name.
ensure_fdd_run = ensure_phase0_run


def load_run_bundle(
    deal_slug: str, run_id: str | None = None
) -> tuple[FddRunManifest, ExhibitStoreDoc, ReportSpec]:
    explicit = run_id is not None and bool(str(run_id).strip())
    rid = str(run_id).strip() if explicit else get_current_run_id(deal_slug)
    if not rid:
        raise FileNotFoundError(
            f"No current FDD run set for deal {deal_slug}"
            if not explicit
            else f"Requested FDD run not found for deal {deal_slug}: {run_id!r}"
        )
    manifest = load_manifest(deal_slug, rid)
    if manifest is None:
        raise FileNotFoundError(
            f"Requested FDD run not found for deal {deal_slug}: {rid}"
            if explicit
            else f"Current FDD run pointer is stale for deal {deal_slug}: {rid}"
        )
    store = load_exhibit_store(deal_slug, rid)
    if store is None:
        raise FileNotFoundError(f"Missing FDD exhibits for deal {deal_slug} run {rid}")
    spec = load_report_spec(deal_slug, rid)
    if spec is None:
        raise FileNotFoundError(f"Missing FDD report_spec for deal {deal_slug} run {rid}")
    return manifest, store, spec


def refresh_spec_after_cell_change(
    deal_slug: str,
    run_id: str,
    store: ExhibitStoreDoc,
    *,
    company: str | None = None,
) -> ReportSpec:
    """Rebuild report spec from *store* (+ commentary if present) and persist.

    Builds the spec in memory before writing exhibits.json so a spec build
    failure does not leave a partially updated run on disk.
    """
    store = persist_store(deal_slug, run_id, store)
    try:
        from agetic_cdd_api.services_fdd_assemble import assemble_and_persist

        return assemble_and_persist(
            deal_slug,
            run_id,
            store=store,
            company=company,
            update_manifest=False,
        )
    except (OSError, ValueError, TypeError, ImportError):
        spec = build_phase0_report_spec(
            run_id=run_id, deal_slug=deal_slug, store=store, company=company
        )
        spec = save_report_spec(spec)
        rebuild_and_persist(deal_slug, run_id=run_id, store=store, spec=spec)
        return spec
