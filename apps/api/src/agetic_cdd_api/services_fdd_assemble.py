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
from typing import Any  # noqa: TC003 — used in assemble signatures

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

ASSEMBLY_VERSION = "0.5.0"  # Phase D exhibit-backed chapter content depth
_MAX_DECK_BULLETS = 6
_MAX_DECK_FINDING_SLIDES = 5  # include business findings (e.g. cost growth) with claim gaps
_TAG_LINE_RE = re.compile(r"^\[([FAMQ])\]\s*(.+)$")
_DECK_COMMENT_SECTIONS = (
    "SEC-ES",
    "SEC-B",
    "SEC-C",
    "SEC-D",
    "SEC-E",
    "SEC-F",
    "SEC-G",
    "SEC-H",
    "SEC-I",
    "SEC-K",
)
_BRIDGE_EXHIBIT_IDS = frozenset({"ex_qoe_bridge", "ex_m5_nwc", "ex_m6_net_debt"})
_ABBREVIATIONS = (
    "EBITDA — Earnings before interest, tax, depreciation and amortisation.",
    "QoE — Quality of Earnings; normalisation of reported earnings.",
    "NWC — Net working capital (operating CA less operating CL).",
    "Net debt — Interest-bearing debt less freely available cash.",
    "GRR / NRR — Gross / net revenue retention.",
    "Proven / doubtful — Databook release status on the cited figure.",
)
_SECTION_TITLES = {
    "SEC-A": "Scope & perimeter",
    "SEC-B": "Historical trading",
    "SEC-C": "Revenue & margin",
    "SEC-D": "Costs & people",
    "SEC-E": "Quality of earnings",
    "SEC-F": "Balance sheet / NAV",
    "SEC-G": "Net working capital",
    "SEC-H": "Net debt",
    "SEC-I": "Cash flow / capex",
    "SEC-J": "Forecast",
    "SEC-K": "Key findings",
    "SEC-ES": "Executive summary",
}


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


def _is_gap_bullet(text: str) -> bool:
    t = (text or "").lower()
    return (
        "(contradicted)" in t
        or "(unverifiable)" in t
        or " gap " in t
        or " — gap " in t
        or " vs " in t
    )


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

    # Key findings: prefer gap lines and surface an overflow note so the deck
    # does not hide seven of eight pack contradictions behind a single bullet.
    if draft.section_id == "SEC-K":
        gap_lines = [ln for ln in lines if _is_gap_bullet(ln)]
        other_lines = [ln for ln in lines if not _is_gap_bullet(ln)]
        # Keep action title (first other line when it matches action_title) then gaps.
        lead: list[str] = []
        if other_lines and draft.action_title and other_lines[0] == _humanize_sec_codes(
            draft.action_title, fallback_title=human
        ):
            lead = [other_lines[0]]
            other_lines = other_lines[1:]
        reserved_overflow = 1 if len(gap_lines) > 1 else 0
        room = max(0, max_bullets - len(lead) - reserved_overflow)
        shown_gaps = gap_lines[:room]
        omitted = len(gap_lines) - len(shown_gaps)
        lines = lead + shown_gaps
        if omitted > 0:
            lines.append(f"…and {omitted} more gap line(s) in the report")
        # Fill remaining slots with non-gap prose if any room left.
        remaining = max_bullets - len(lines)
        if remaining > 0 and other_lines:
            lines.extend(other_lines[:remaining])
        lines = lines[:max_bullets]
    else:
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
        "Sources: every figure is taken from the approved databook exhibits.",
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


def _front_matter_nodes(
    *,
    name: str,
    commentary: CommentaryDoc | None,
    store: ExhibitStoreDoc,
    databook_release_id: str | None,
    currency: str | None,
    scale: str | None,
    scope: Any | None,
    manifest: Any | None,
    findings_counts: dict[str, int],
) -> tuple[list[ReportSpecNode], list[ReportSpecNode]]:
    """Return (report_only_nodes, deck_slide_nodes_without_index)."""
    from agetic_cdd_api.services_fdd_findings import severity_dashboard_line

    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    ents = ", ".join((scope.entities_in if scope else [])[:6]) or name
    periods = ", ".join((scope.periods if scope else [])[:10]) or "as per exhibits"
    mat = None
    _basis_labels = {
        "adj_ebitda": "adjusted EBITDA",
        "adjusted_ebitda": "adjusted EBITDA",
        "ebitda": "EBITDA",
        "revenue": "revenue",
    }
    if scope is not None:
        basis_key = (scope.materiality_basis or "").strip().lower()
        basis_human = _basis_labels.get(basis_key, (scope.materiality_basis or "").replace("_", " "))
        if scope.materiality_m is not None:
            mat = f"{format_fdd_number(float(scope.materiality_m))} {scale or 'M'} ({basis_human})"
        elif scope.materiality_pct is not None:
            mat = f"{float(scope.materiality_pct) * 100:.1f}% of {basis_human}"
    basis_lines = [
        f"Entities in scope: {ents}",
        f"Periods: {periods}",
        f"Currency / scale: {currency or 'USD'} · {scale or 'M'}",
        f"Materiality: {mat or 'per scope profile'}",
        f"Databook release: {databook_release_id or 'unpinned'}",
        "Figures are taken from the approved databook exhibits for this run.",
    ]
    caveats: list[str] = []
    if manifest is not None:
        if getattr(manifest, "draft_mode", False):
            caveats.append("Draft mode — databook contract incomplete; partner gate blocked.")
        if not getattr(manifest, "contract_complete", True):
            reasons = list(getattr(manifest, "contract_reasons", None) or [])[:4]
            caveats.append(
                "Contract gaps: " + (", ".join(reasons) if reasons else "see readiness")
            )
        if not getattr(manifest, "g3_passed", True):
            caveats.append("G3 model checks have open failures — some sections may be held.")
        if not getattr(manifest, "g4_approved", False):
            caveats.append("QoE judgements not G4-approved — earnings may be unadjusted.")
    doubtful = 0
    for ex in store.exhibits or []:
        for cell in ex.cells or []:
            if cell.status and cell.status.value == "doubtful":
                doubtful += 1
    if doubtful:
        caveats.append(f"{doubtful} doubtful figure(s) remain in exhibits.")
    if findings_counts.get("total"):
        caveats.append(severity_dashboard_line(findings_counts))
    if not caveats:
        caveats.append("No material integrity caveats flagged for this run.")

    toc_lines: list[str] = []
    if commentary and commentary.sections:
        for sid in _section_order(commentary):
            draft = _draft_by_id(commentary).get(sid)
            label = (draft.title if draft else None) or _SECTION_TITLES.get(sid, sid)
            flag = " (held)" if draft and draft.held_back else ""
            toc_lines.append(f"• {label}{flag}")
    toc_lines.append("• Exhibits appendix")
    toc_lines.append("• Not evidenced / open items")
    toc_lines.append("• Presentation standards")

    agenda_lines = [
        "• Executive summary dashboard",
        "• Trading, margin, costs",
        "• QoE and bridges",
        "• Balance sheet, NWC, net debt, cash",
        "• Key findings",
        "• Open items",
    ]

    report_nodes = [
        ReportSpecNode(
            node_id="sec_basis",
            kind="section",
            title="Basis of preparation",
            body="\n".join(basis_lines),
        ),
        ReportSpecNode(
            node_id="sec_integrity",
            kind="section",
            title="Data integrity and caveats",
            body="\n".join(f"• {c}" for c in caveats),
        ),
        ReportSpecNode(
            node_id="sec_toc",
            kind="section",
            title="Contents",
            body="\n".join(toc_lines),
        ),
        ReportSpecNode(
            node_id="sec_abbreviations",
            kind="section",
            title="Abbreviations & key terms",
            body="\n".join(f"• {a}" for a in _ABBREVIATIONS),
        ),
    ]
    deck_nodes = [
        ReportSpecNode(
            node_id="slide_agenda",
            kind="slide",
            title="Agenda",
            body="\n".join(
                agenda_lines
                + [f"• {c}" for c in caveats[:2]]
                + basis_lines[:2]
            ),
        ),
    ]
    return report_nodes, deck_nodes


def _slide_spec_to_node(slide: Any, *, slide_index: int) -> ReportSpecNode:
    """Mirror a chapter SlideSpec into a legacy kind=slide node for render_stub."""
    lines: list[str] = []
    if getattr(slide, "headline", None):
        lines.append(str(slide.headline))
    for obs in list(getattr(slide, "observations", None) or [])[:8]:
        lines.append(f"• {obs}")
    title = (getattr(slide, "banner", None) or getattr(slide, "headline", None) or slide.slide_id)
    if getattr(slide, "layout", None) == "cover":
        title = getattr(slide, "deal_name", None) or title
    exhibit_id = None
    for fid in list(getattr(slide, "figure_ids", None) or []):
        if str(fid).startswith("ex_"):
            exhibit_id = str(fid)
            break
    return ReportSpecNode(
        node_id=f"slide_ch_{slide.slide_id}",
        kind="slide",
        title=str(title)[:120],
        body=apply_currency_to_prose("\n".join(lines), None),
        exhibit_id=exhibit_id,
        cell_refs=[],
        slide_index=slide_index,
    )


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
    findings: Any | None = None,
    scope: Any | None = None,
    manifest: Any | None = None,
    include_deck_exhibit_appendix: bool | None = None,
    qoe: Any | None = None,
    request_list: Any | None = None,
    claims: Any | None = None,
) -> ReportSpec:
    """Build the shared Phase 7 report_spec (commentary + exhibits + chapters).

    Section nodes keep SEC-* depth for legacy report render/tests. Widescreen
    PPTX uses ``spec.slides`` (expected chapters 01–09). Slide nodes mirror
    those chapters for ``render_stub(kind='deck')``.
    """
    from agetic_cdd_api.services_fdd_chapters import default_chrome, plan_chapter_slides
    from agetic_cdd_api.services_fdd_findings import (
        finding_page_title,
        format_finding_card,
        not_evidenced_body,
    )

    idx = index_cells(store)
    name = company or deal_slug
    exhibits = sorted(
        (ex for ex in store.exhibits if ex.cells),
        key=_exhibit_sort_key,
    )
    n_cells = len(idx)
    n_ex = len(exhibits)
    n_sections = len(commentary.sections) if commentary else 0
    findings_list = list(getattr(findings, "findings", None) or [])
    findings_counts = dict(getattr(findings, "counts", None) or {})
    if include_deck_exhibit_appendix is None:
        include_deck_exhibit_appendix = bool(
            getattr(scope, "deck_include_exhibit_appendix", False)
        )

    chapter_slides = plan_chapter_slides(
        company=name,
        store=store,
        commentary=commentary,
        scope=scope,
        findings=findings,
        qoe=qoe,
        request_list=request_list,
        claims=claims,
        chrome=default_chrome(company=name, scope=scope),
    )

    nodes: list[ReportSpecNode] = [
        ReportSpecNode(
            node_id="sec_cover",
            kind="section",
            title="Cover",
            body=(
                f"Financial & tax due diligence — findings report\n"
                f"Strictly Private and Confidential\n"
                f"Sections: {n_sections} · Exhibits: {n_ex} · Figures: {n_cells}\n"
                f"Chapters: {len(chapter_slides)} slide(s) (01–09 storyline)"
            ),
        ),
    ]

    report_fm, _deck_fm = _front_matter_nodes(
        name=name,
        commentary=commentary,
        store=store,
        databook_release_id=databook_release_id,
        currency=currency,
        scale=scale,
        scope=scope,
        manifest=manifest,
        findings_counts=findings_counts,
    )
    nodes.extend(report_fm)

    # Chaptered widescreen slides (Phase C) — primary PPTX storyline.
    for i, slide in enumerate(chapter_slides):
        nodes.append(_slide_spec_to_node(slide, slide_index=i))

    if commentary and commentary.sections:
        by_id = _draft_by_id(commentary)
        for sid in _section_order(commentary):
            draft = by_id.get(sid)
            if draft is None:
                continue
            human = draft.title or sid
            if sid == "SEC-ES":
                title = "Executive summary"
            elif draft.held_back:
                title = human
            else:
                title = draft.action_title or human
            title = _humanize_sec_codes(title, fallback_title=human)
            if sid == "SEC-ES":
                title = "Executive summary"
            exhibit_id = draft.exhibit_ids[0] if draft.exhibit_ids else None
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
            body = apply_currency_to_prose(body, currency)
            title = apply_currency_to_prose(title, currency)
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
            sec_findings = [f for f in findings_list if f.section_id == sid]
            for i, finding in enumerate(sec_findings[:4]):
                nodes.append(
                    ReportSpecNode(
                        node_id=f"sec_finding_{sid}_{i}",
                        kind="section",
                        title=finding_page_title(finding),
                        body=format_finding_card(finding),
                        exhibit_id=exhibit_id,
                        cell_refs=list(finding.evidence_refs or [])[:8],
                    )
                )
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

    gap_body = not_evidenced_body(findings=findings_list, commentary=commentary)
    nodes.append(
        ReportSpecNode(
            node_id="sec_not_evidenced",
            kind="section",
            title="Not evidenced / open items",
            body=gap_body,
        )
    )

    # Exhibit appendix — section nodes (legacy); PPTX chapters cover narrative.
    if not exhibits:
        nodes.append(
            ReportSpecNode(
                node_id="sec_exhibits_empty",
                kind="section",
                title="Exhibits",
                body="No exhibit cells available.",
            )
        )
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
            if include_deck_exhibit_appendix:
                # Optional appendix slides after chapter storyline.
                nodes.append(
                    ReportSpecNode(
                        node_id=f"slide_ex_{ex.exhibit_id}",
                        kind="slide",
                        title=title,
                        body=_deck_exhibit_body(ex, body),
                        exhibit_id=ex.exhibit_id,
                        cell_refs=refs,
                        slide_index=len(chapter_slides)
                        + sum(
                            1
                            for n in nodes
                            if n.kind == "slide" and n.slide_index is not None and n.slide_index >= len(chapter_slides)
                        ),
                    )
                )

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
            cell_refs=[],
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
        slides=list(chapter_slides),
        content_hash=_content_hash(
            {
                "assembly": ASSEMBLY_VERSION,
                "figures": figures,
                "nodes": [n.model_dump(mode="json") for n in nodes],
                "slides": [s.model_dump(mode="json") for s in chapter_slides],
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

    from agetic_cdd_api.services_fdd_findings import build_findings
    from agetic_cdd_api.services_fdd_store import (
        load_claims_ledger,
        load_findings,
        load_request_list,
    )

    try:
        findings = build_findings(
            deal_slug,
            run_id,
            store=store,
            commentary=commentary,
            update_manifest=True,
        )
    except Exception as err:
        logger.warning(
            "Findings build failed for %s/%s: %s", deal_slug, run_id, err, exc_info=True
        )
        findings = load_findings(deal_slug, run_id)

    request_list = load_request_list(deal_slug, run_id)
    claims = load_claims_ledger(deal_slug, run_id)

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
        findings=findings,
        scope=scope,
        manifest=manifest,
        qoe=qoe,
        request_list=request_list,
        claims=claims,
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

    # Seed findings before commentary so SEC-ES can cite severity counts.
    try:
        from agetic_cdd_api.services_fdd_findings import build_findings

        build_findings(
            deal_slug,
            run_id,
            store=store,
            commentary=load_commentary(deal_slug, run_id),
            update_manifest=True,
        )
    except Exception as err:
        logger.warning(
            "Pre-commentary findings build failed for %s/%s: %s",
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
