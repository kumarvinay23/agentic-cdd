"""FDD Phase 7 — assemble commentary + exhibits into one report_spec / dual render."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.report_fdd import FddDeckBuilder, FddReportBuilder
from agetic_cdd_api.services_fdd_assemble import (
    assemble_report_spec,
    ensure_commentary_and_assemble,
)
from agetic_cdd_api.services_fdd_commentary import build_commentary
from agetic_cdd_api.services_fdd_qoe import build_qoe_workbook
from agetic_cdd_api.services_fdd_render import ensure_phase0_run, render_stub
from agetic_cdd_api.services_fdd_scope import seed_scope_profile
from agetic_cdd_api.services_fdd_store import (
    load_exhibit_store,
    load_manifest,
    load_report_spec,
    load_scope_profile,
    save_scope_profile,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _prep(slug: str, deal_root: Path):
    (deal_root / slug).mkdir(parents=True)
    manifest, store, _spec = ensure_phase0_run(
        slug, company="RetailCo", revenue_fy24=100.0, prefer_current_release=True
    )
    build_qoe_workbook(slug, manifest.run_id, worked_example=True)
    seed_scope_profile(slug, manifest.run_id, company="RetailCo")
    profile = load_scope_profile(slug, manifest.run_id)
    assert profile is not None
    save_scope_profile(profile.model_copy(update={"entities_in": ["RetailCo Ltd"]}))
    return manifest, store


def test_assemble_includes_commentary_and_exhibits(deal_root: Path) -> None:
    slug = "p7-assemble"
    manifest, store = _prep(slug, deal_root)
    # Force commentary then assemble (ensure_phase0 may already have done this)
    build_commentary(slug, manifest.run_id, company="RetailCo", update_report_spec=True)
    spec = load_report_spec(slug, manifest.run_id)
    assert spec is not None
    store = load_exhibit_store(slug, manifest.run_id) or store

    comment_secs = [n for n in spec.nodes if n.node_id.startswith("sec_comment_")]
    comment_slides = [n for n in spec.nodes if n.node_id.startswith("slide_comment_")]
    exhibit_secs = [n for n in spec.nodes if n.node_id.startswith("sec_ex_")]
    assert len(comment_secs) >= 5  # in-scope sections
    assert len(comment_slides) == len(comment_secs)
    assert len(exhibit_secs) >= 1
    assert any(n.node_id == "msg_standards" for n in spec.nodes)
    assert any(n.node_id == "sec_cover" for n in spec.nodes)

    report = render_stub(kind="report", spec=spec, store=store)
    deck = render_stub(kind="deck", spec=spec, store=store)
    # Cover + commentary sections + exhibits + standards
    assert len(report.pages) >= 8
    assert len(deck.pages) >= 8
    assert report.figures == deck.figures

    man = load_manifest(slug, manifest.run_id)
    assert man is not None
    assert man.model_versions.get("fdd_assembly")


def test_generate_produces_multi_section_pdf_and_deck(deal_root: Path) -> None:
    slug = "p7-generate"
    _prep(slug, deal_root)

    report_events = list(FddReportBuilder(slug).generate())
    deck_events = list(FddDeckBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in report_events)
    assert any(e.get("stage") == "done" for e in deck_events)

    # Section events should mention commentary
    assert any(
        "commentary" in str(e.get("message", "")).lower()
        or e.get("commentary_sections")
        for e in report_events
        if e.get("stage") == "section"
    )

    report_dir = deal_root / slug / "reports" / "fdd_report"
    deck_dir = deal_root / slug / "reports" / "fdd_deck"
    report_figs = json.loads(list(report_dir.glob("*_figures.json"))[0].read_text())
    deck_figs = json.loads(list(deck_dir.glob("*_figures.json"))[0].read_text())
    assert report_figs["page_count"] >= 8
    assert deck_figs["page_count"] >= 8
    assert report_figs["figures"] == deck_figs["figures"]

    from pypdf import PdfReader

    pdf = list(report_dir.glob("*.pdf"))[0]
    assert len(PdfReader(str(pdf)).pages) >= 8


def test_ensure_commentary_and_assemble_idempotent(deal_root: Path) -> None:
    slug = "p7-idem"
    manifest, store = _prep(slug, deal_root)
    c1, s1 = ensure_commentary_and_assemble(
        slug, manifest.run_id, store=store, company="RetailCo"
    )
    c2, s2 = ensure_commentary_and_assemble(
        slug, manifest.run_id, store=store, company="RetailCo"
    )
    assert c1 is not None and c2 is not None
    assert len(s1.nodes) == len(s2.nodes)
    assert s1.content_hash == s2.content_hash


def test_ensure_rebuilds_stale_commentary_version(deal_root: Path) -> None:
    """Regenerate must not keep a pre-fix commentary.json (INR / GRR headlines)."""
    from agetic_cdd_api.services_fdd_commentary import COMMENTARY_VERSION
    from agetic_cdd_api.services_fdd_store import load_commentary, save_commentary

    slug = "p7-stale-comment"
    manifest, store = _prep(slug, deal_root)
    ensure_commentary_and_assemble(
        slug, manifest.run_id, store=store, company="RetailCo"
    )
    doc = load_commentary(slug, manifest.run_id)
    assert doc is not None
    # Simulate an older on-disk draft that would keep wrong headlines
    save_commentary(doc.model_copy(update={"version": "0.0.1"}))
    c2, _spec = ensure_commentary_and_assemble(
        slug, manifest.run_id, store=store, company="RetailCo"
    )
    assert c2 is not None
    assert c2.version == COMMENTARY_VERSION
    # Scope / ES prose should not hard-code INR when exhibits are USD
    scope_sec = next((s for s in c2.sections if s.section_id == "SEC-A"), None)
    if scope_sec is not None:
        assert "on a INR basis" not in (scope_sec.body or "")


def test_assemble_without_commentary_still_has_exhibits(deal_root: Path) -> None:
    slug = "p7-no-comment"
    (deal_root / slug).mkdir(parents=True)
    manifest, store, _ = ensure_phase0_run(
        slug, company="X", revenue_fy24=50.0, prefer_current_release=True
    )
    # Assemble with explicit None commentary (bypass auto-build)
    spec = assemble_report_spec(
        run_id=manifest.run_id,
        deal_slug=slug,
        store=store,
        commentary=None,
        company="X",
    )
    assert any(n.node_id == "sec_comment_pending" for n in spec.nodes)
    assert any(n.node_id.startswith("sec_ex_") for n in spec.nodes) or any(
        n.node_id == "sec_exhibits_empty" for n in spec.nodes
    )
    standards = next(n for n in spec.nodes if n.node_id == "msg_standards")
    assert standards.cell_refs == []


def test_render_resolves_tokens_in_titles(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import ReportSpec, ReportSpecNode
    from agetic_cdd_api.services_fdd_render import render_stub
    from agetic_cdd_api.services_fdd_tokens import make_token

    slug = "p7-titles"
    manifest, store = _prep(slug, deal_root)
    ex = next(e for e in store.exhibits if e.cells)
    cell = ex.cells[0]
    token = make_token(ex.exhibit_id, cell.cell_id)
    spec = ReportSpec(
        spec_id="s1",
        run_id=manifest.run_id,
        deal_slug=slug,
        updated_at="t",
        title="T",
        nodes=[
            ReportSpecNode(
                node_id="sec_x",
                kind="section",
                title=f"IC headline: adjusted earnings {token}",
                body=f"Body uses {token}.",
                cell_refs=[f"{ex.exhibit_id}.{cell.cell_id}"],
            )
        ],
    )
    report = render_stub(kind="report", spec=spec, store=store)
    assert "{{ex:" not in report.pages[0].title
    assert "{{ex:" not in report.pages[0].body


def test_safe_name_caps_length() -> None:
    from agetic_cdd_api.report_fdd import _safe_name

    long = "A" * 200
    assert len(_safe_name(long, "slug")) <= 100
    assert _safe_name("Acme!! Corp", "slug") == "Acme_Corp"


def test_slide_body_preserves_structural_blank() -> None:
    from agetic_cdd_api.report_fdd import _slide_body_lines

    lines = _slide_body_lines("First\n\nSecond\n\n\nThird")
    assert lines == ["First", "", "Second", "", "Third"]
    capped = _slide_body_lines("\n".join(f"L{i}" for i in range(12)), max_content=8)
    assert len([ln for ln in capped if ln]) == 8


def test_deck_body_respects_six_bullet_cap_with_held_back() -> None:
    from agetic_cdd_api.fdd_schemas import CommentarySentence, SectionDraft
    from agetic_cdd_api.services_fdd_assemble import _deck_body_from_draft

    draft = SectionDraft(
        section_id="SEC-E",
        title="QoE",
        action_title="Adj. EBITDA summary",
        held_back=True,
        held_back_reason="missing bridge",
        sentences=[
            CommentarySentence(tag="F", text=f"Fact line {i}") for i in range(8)
        ],
    )
    lines = _deck_body_from_draft(draft).split("\n")
    assert len(lines) <= 6
    assert lines[-1].startswith("Held back:")


def test_refs_dedupe_tokens_from_body(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import (
        ArtefactStatus,
        CommentaryDoc,
        CommentarySentence,
        SectionDraft,
    )

    slug = "p7-refs"
    manifest, store = _prep(slug, deal_root)
    # Pick a real cell from the store if present
    ex = store.exhibits[0]
    cid = ex.cells[0].cell_id
    ref = f"{ex.exhibit_id}.{cid}"
    token = f"{{{{ex:{ex.exhibit_id}.{cid}}}}}"
    commentary = CommentaryDoc(
        run_id=manifest.run_id,
        deal_slug=slug,
        updated_at="2026-10-08T00:00:00+00:00",
        status=ArtefactStatus.DRAFT,
        sections=[
            SectionDraft(
                section_id="SEC-A",
                title="Perimeter",
                body=f"[F] Revenue is {token}.",
                sentences=[
                    CommentarySentence(tag="F", text=f"Revenue is {token}.")
                ],
                cell_refs=[ref, ref],  # intentional duplicate
                exhibit_ids=[ex.exhibit_id],
                checks_passed=True,
            )
        ],
        checks_passed=True,
    )
    spec = assemble_report_spec(
        run_id=manifest.run_id,
        deal_slug=slug,
        store=store,
        commentary=commentary,
        company="RetailCo",
    )
    sec = next(n for n in spec.nodes if n.node_id == "sec_comment_SEC-A")
    assert sec.cell_refs.count(ref) == 1
