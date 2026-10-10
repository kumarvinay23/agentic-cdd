"""FDD Phase 7 — assemble one report_spec from commentary + exhibits (P7).

Produces paired section/slide nodes so PDF and IC deck share identical figures
(R5 / AS-5), with presentation-standard closing notes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CommentaryDoc,
    DEFAULT_SECTIONS_IN_SCOPE,
    Exhibit,
    ExhibitStoreDoc,
    ReportSpec,
    ReportSpecNode,
    RunStage,
    SectionDraft,
)
from agetic_cdd_api.services_fdd_deps import rebuild_and_persist
from agetic_cdd_api.services_fdd_exhibit import cell_ref, index_cells
from agetic_cdd_api.services_fdd_render import (
    _exhibit_body,
    _exhibit_sort_key,
)
from agetic_cdd_api.services_fdd_store import (
    load_commentary,
    load_manifest,
    load_qoe_workbook,
    load_scope_profile,
    save_manifest,
    save_report_spec,
)
from agetic_cdd_api.services_fdd_tokens import (
    apply_currency_to_prose,
    effective_currency_scale,
    find_tokens,
)

logger = logging.getLogger(__name__)

ASSEMBLY_VERSION = "0.2.1"  # chart year labels A/E; exhibit label FY de-dupe
_MAX_DECK_BULLETS = 6
_TAG_LINE_RE = re.compile(r"^\[([FAMQ])\]\s*(.+)$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _content_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _section_order(doc: CommentaryDoc | None) -> list[str]:
    """ES first, then default A–K, then any remaining drafts."""
    present = {s.section_id for s in (doc.sections if doc else [])}
    ordered: list[str] = []
    if "SEC-ES" in present:
        ordered.append("SEC-ES")
    for sid in DEFAULT_SECTIONS_IN_SCOPE:
        if sid == "SEC-ES":
            continue
        if sid in present:
            ordered.append(sid)
    for sid in sorted(present):
        if sid not in ordered:
            ordered.append(sid)
    return ordered


def _draft_by_id(doc: CommentaryDoc) -> dict[str, SectionDraft]:
    return {s.section_id: s for s in doc.sections}


_SEC_CODE_RE = re.compile(r"\bSEC-[A-Z]+\b")


def _humanize_sec_codes(text: str, *, fallback_title: str) -> str:
    """Replace leftover SEC-* codes with the section's human title."""
    if not text:
        return text
    title = (fallback_title or "").strip() or "this section"
    out = text
    if title:
        out = _SEC_CODE_RE.sub(title, out)
    return out


def _deck_body_from_draft(draft: SectionDraft) -> str:
    """Condense tagged prose into ≤6 bullets for IC slides (no [F/A/M/Q] tags)."""
    lines: list[str] = []
    human = draft.title or draft.section_id
    if draft.action_title and not draft.held_back:
        lines.append(_humanize_sec_codes(draft.action_title, fallback_title=human))
    for s in draft.sentences:
        text = (s.text or "").strip()
        if text:
            lines.append(_humanize_sec_codes(text, fallback_title=human))
    if not lines and draft.body:
        for raw in (draft.body or "").split("\n"):
            raw = raw.strip()
            if not raw:
                continue
            m = _TAG_LINE_RE.match(raw)
            lines.append(
                _humanize_sec_codes(m.group(2) if m else raw, fallback_title=human)
            )

    # Reserve a slot for the held-back notice so we never exceed ≤6 bullets
    max_bullets = _MAX_DECK_BULLETS - (1 if draft.held_back else 0)
    lines = lines[:max_bullets]
    if draft.held_back:
        reason = _humanize_sec_codes(
            draft.held_back_reason or "pending coverage",
            fallback_title=human,
        )
        lines.append(f"Held back: {reason}")
    return "\n".join(lines) if lines else human


def _presentation_standards_body(
    *,
    store: ExhibitStoreDoc,
    company: str | None,
    release_id: str | None,
    scale: str | None,
    currency: str | None,
) -> str:
    # Currency/scale from scope/exhibits — not scale_header (which embeds release id)
    cur = currency or "USD"
    scl = scale or "M"
    bits = [
        f"Company: {company or store.deal_slug}",
        f"Currency / scale: {cur} · {scl} (one scale per exhibit)",
        "Rounding: compute unrounded; displays HALF_UP to 2 d.p.; negatives in brackets.",
        "Periods: fiscal labels as shown on exhibits (e.g. FY22A, FY23A, FY24A).",
        "Deck charts: category axis = Period; value axis = currency · scale.",
        "Sources: every figure resolves from the exhibit store via number tokens.",
    ]
    if release_id:
        bits.append(f"Databook release: {release_id}")
    # Same figure rule as the cover — unique cell refs (index), not raw rows.
    from agetic_cdd_api.services_fdd_exhibit import index_cells

    live = [ex for ex in store.exhibits if ex.cells]
    n_ex = len(live)
    n_cells = len(index_cells(store))
    bits.append(f"Exhibits: {n_ex} · Figures: {n_cells}")
    return "\n".join(bits)


def assemble_report_spec(
    *,
    run_id: str,
    deal_slug: str,
    store: ExhibitStoreDoc,
    commentary: CommentaryDoc | None = None,
    company: str | None = None,
    databook_release_id: str | None = None,
    currency: str | None = None,
    scale: str | None = None,
) -> ReportSpec:
    """Build the shared Phase 7 report_spec (commentary + exhibits + standards)."""
    idx = index_cells(store)
    name = company or deal_slug
    # Skip empty model shells (held sections) so the appendix never shows stale figures.
    exhibits = sorted(
        (ex for ex in store.exhibits if ex.cells),
        key=_exhibit_sort_key,
    )
    n_cells = len(idx)
    n_ex = len(exhibits)
    n_sections = len(commentary.sections) if commentary else 0

    nodes: list[ReportSpecNode] = [
        ReportSpecNode(
            node_id="sec_cover",
            kind="section",
            title="Cover",
            body=(
                f"Financial Due Diligence — {name}\n"
                f"Sections: {n_sections} · Exhibits: {n_ex} · Figures: {n_cells}\n"
                "One report_spec drives both the PDF report and IC deck (R5)."
            ),
        ),
        ReportSpecNode(
            node_id="slide_title",
            kind="slide",
            title=f"FDD — {name}",
            body=(
                f"{n_sections} section(s) · {n_ex} exhibit(s) · {n_cells} figure(s)\n"
                "Shared figures with the PDF report."
            ),
            slide_index=0,
        ),
    ]

    slide_i = 1
    if commentary and commentary.sections:
        by_id = _draft_by_id(commentary)
        for sid in _section_order(commentary):
            draft = by_id.get(sid)
            if draft is None:
                continue
            human = draft.title or sid
            # Report heading: human title when held back; else action_title (may
            # carry a figure token resolved at render time).
            if draft.held_back:
                title = human
            else:
                title = draft.action_title or human
            title = _humanize_sec_codes(title, fallback_title=human)
            exhibit_id = draft.exhibit_ids[0] if draft.exhibit_ids else None
            # Preserve order; dedupe draft refs + body tokens (same cell_ref format)
            refs = list(dict.fromkeys(draft.cell_refs or []))
            seen = set(refs)
            for _raw, eid, cid in find_tokens(
                f"{draft.body or ''}\n{draft.action_title or ''}"
            ):
                ref = cell_ref(eid, cid)
                if ref not in seen:
                    seen.add(ref)
                    refs.append(ref)
            body = draft.body or f"{draft.title}\n(No prose drafted.)"
            body = _humanize_sec_codes(body, fallback_title=human)
            # Stale commentary may still say INR while exhibits are USD
            body = apply_currency_to_prose(body, currency)
            title = apply_currency_to_prose(title, currency)
            deck_body = apply_currency_to_prose(
                _deck_body_from_draft(draft), currency
            )
            nodes.append(
                ReportSpecNode(
                    node_id=f"sec_comment_{sid}",
                    kind="section",
                    title=title,
                    body=body,
                    exhibit_id=exhibit_id,
                    cell_refs=refs,
                )
            )
            nodes.append(
                ReportSpecNode(
                    node_id=f"slide_comment_{sid}",
                    kind="slide",
                    title=draft.title or sid,
                    body=deck_body,
                    exhibit_id=exhibit_id,
                    cell_refs=refs,
                    slide_index=slide_i,
                )
            )
            slide_i += 1
    else:
        nodes.append(
            ReportSpecNode(
                node_id="sec_comment_pending",
                kind="section",
                title="Commentary",
                body=(
                    "Section commentary not built yet — "
                    "POST …/commentary/build, then re-assemble."
                ),
            )
        )
        nodes.append(
            ReportSpecNode(
                node_id="slide_comment_pending",
                kind="slide",
                title="Commentary pending",
                body="Build commentary to populate IC slides.",
                slide_index=slide_i,
            )
        )
        slide_i += 1

    # Exhibit appendix — shared figures for report + deck
    if not exhibits:
        nodes.append(
            ReportSpecNode(
                node_id="sec_exhibits_empty",
                kind="section",
                title="Exhibits",
                body="No exhibit cells available.",
            )
        )
        nodes.append(
            ReportSpecNode(
                node_id="slide_exhibits_empty",
                kind="slide",
                title="Exhibits",
                body="No exhibit cells available.",
                slide_index=slide_i,
            )
        )
        slide_i += 1
    else:
        for ex in exhibits:
            body, refs = _exhibit_body(ex)
            title = ex.title or ex.exhibit_id
            nodes.append(
                ReportSpecNode(
                    node_id=f"sec_ex_{ex.exhibit_id}",
                    kind="section",
                    title=f"Exhibit — {title}",
                    body=body,
                    exhibit_id=ex.exhibit_id,
                    cell_refs=refs,
                )
            )
            nodes.append(
                ReportSpecNode(
                    node_id=f"slide_ex_{ex.exhibit_id}",
                    kind="slide",
                    title=title,
                    body=_deck_exhibit_body(ex, body),
                    exhibit_id=ex.exhibit_id,
                    cell_refs=refs,
                    slide_index=slide_i,
                )
            )
            slide_i += 1

    standards = _presentation_standards_body(
        store=store,
        company=name,
        release_id=databook_release_id,
        scale=scale,
        currency=currency,
    )
    nodes.append(
        ReportSpecNode(
            node_id="msg_standards",
            kind="message",
            title="Presentation standards",
            body=standards,
            cell_refs=[],  # standards are presentation policy, not a figure
        )
    )

    figures = {ref: cell.value for ref, cell in idx.items()}
    return ReportSpec(
        spec_id=f"spec_{run_id}",
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        title=f"FDD Report — {name}",
        nodes=nodes,
        content_hash=_content_hash(
            {
                "assembly": ASSEMBLY_VERSION,
                "figures": figures,
                "nodes": [n.model_dump(mode="json") for n in nodes],
            }
        ),
    )


def _deck_exhibit_body(ex: Exhibit, full_body: str) -> str:
    """Keep exhibit slides scannable — scale header + first lines."""
    lines = [ln for ln in (full_body or "").split("\n") if ln.strip()]
    head: list[str] = []
    if ex.scale_header:
        head.append(f"Scale: {ex.scale_header}")
    for ln in lines:
        if ln.startswith("Scale:") or ln.startswith("Section:"):
            if ln not in head:
                head.append(ln)
            continue
        head.append(ln)
        if len(head) >= _MAX_DECK_BULLETS:
            break
    return "\n".join(head) if head else (ex.title or ex.exhibit_id)


def assemble_and_persist(
    deal_slug: str,
    run_id: str,
    *,
    store: ExhibitStoreDoc,
    company: str | None = None,
    commentary: CommentaryDoc | None = None,
    update_manifest: bool = True,
) -> ReportSpec:
    """Assemble Phase 7 spec, persist, rebuild deps; optionally set stage P7."""
    commentary = commentary if commentary is not None else load_commentary(deal_slug, run_id)
    manifest = load_manifest(deal_slug, run_id)
    scope = load_scope_profile(deal_slug, run_id)
    qoe = load_qoe_workbook(deal_slug, run_id)
    currency, scale = effective_currency_scale(scope=scope, store=store, qoe=qoe)

    spec = assemble_report_spec(
        run_id=run_id,
        deal_slug=deal_slug,
        store=store,
        commentary=commentary,
        company=company,
        databook_release_id=(
            manifest.databook_release_id if manifest else None
        ),
        currency=currency,
        scale=scale,
    )
    spec = save_report_spec(spec)
    rebuild_and_persist(deal_slug, run_id=run_id, store=store, spec=spec)

    if update_manifest and manifest is not None:
        stage = manifest.stage
        # Advance toward P7 once assembly runs (don't regress past P8+)
        if stage in {
            RunStage.P0,
            RunStage.P1,
            RunStage.P2,
            RunStage.P3,
            RunStage.P4,
            RunStage.P5,
            RunStage.P6,
        }:
            stage = RunStage.P7
        save_manifest(
            manifest.model_copy(
                update={
                    "stage": stage,
                    "model_versions": {
                        **(manifest.model_versions or {}),
                        "fdd_assembly": ASSEMBLY_VERSION,
                    },
                    "status": (
                        ArtefactStatus.CHECKED
                        if commentary and commentary.checks_passed
                        else manifest.status
                    ),
                }
            )
        )
    return spec


def ensure_commentary_and_assemble(
    deal_slug: str,
    run_id: str,
    *,
    store: ExhibitStoreDoc,
    company: str | None = None,
    rebuild_commentary: bool = True,
) -> tuple[CommentaryDoc | None, ReportSpec]:
    """Build/refresh commentary, then assemble Phase 7 report_spec.

    Default *rebuild_commentary=True* so report/deck generate picks up draft
    fixes (headline metric, currency, held-back titles) instead of reusing a
    stale commentary.json from an earlier run.
    """
    from agetic_cdd_api.services_fdd_commentary import (
        COMMENTARY_VERSION,
        build_commentary,
        sync_qoe_exhibit,
    )

    # Sync exhibits + draft scope currency *before* drafting commentary
    try:
        store = sync_qoe_exhibit(deal_slug, run_id, store=store)
    except Exception as err:
        logger.warning(
            "Failed to sync QoE exhibit for %s/%s during assemble: %s",
            deal_slug,
            run_id,
            err,
            exc_info=True,
        )
    try:
        from agetic_cdd_api.services_fdd_scope import sync_scope_currency_from_store

        sync_scope_currency_from_store(deal_slug, run_id, store=store)
    except Exception as err:
        logger.warning(
            "Failed to sync scope currency for %s/%s: %s",
            deal_slug,
            run_id,
            err,
            exc_info=True,
        )

    commentary = load_commentary(deal_slug, run_id)
    stale = commentary is not None and commentary.version != COMMENTARY_VERSION
    if commentary is None or rebuild_commentary or stale:
        try:
            commentary = build_commentary(
                deal_slug,
                run_id,
                company=company,
                update_manifest=True,
                update_report_spec=False,  # assemble owns the spec
            )
        except Exception as err:
            logger.warning(
                "Failed to build commentary for %s/%s, falling back to store: %s",
                deal_slug,
                run_id,
                err,
                exc_info=True,
            )
            commentary = load_commentary(deal_slug, run_id)

    spec = assemble_and_persist(
        deal_slug,
        run_id,
        store=store,
        company=company,
        commentary=commentary,
        update_manifest=True,
    )
    return commentary, spec
