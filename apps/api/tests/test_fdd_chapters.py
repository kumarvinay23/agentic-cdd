"""Phase C — expected 01–09 chapter storyline assemble tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.fdd_schemas import ExhibitStoreDoc
from agetic_cdd_api.services_fdd_chapters import (
    chapter_sequence,
    expected_chapter_ids,
    plan_chapter_slides,
)
from agetic_cdd_api.services_fdd_pptx import slide_chrome_inventory, write_fdd_presentation


@pytest.fixture()
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agetic_cdd_api import services_deals as deals_mod

    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_plan_chapter_slides_matches_expected_toc() -> None:
    store = ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="", exhibits=[])
    slides = plan_chapter_slides(company="Acme", store=store)
    assert slides[0].layout == "cover"
    assert slides[1].layout == "toc"
    assert chapter_sequence(slides) == expected_chapter_ids()
    # Two-pass TOC page numbers filled for every chapter
    assert len(slides[1].toc_entries) == 9
    assert all(e.page for e in slides[1].toc_entries)
    # Transaction chapter always present (mix may be pending / open ask)
    tx = [s for s in slides if s.chapter == "transaction"]
    assert tx
    assert any(
        "open" in (s.headline or "").lower()
        or "held" in (s.headline or "").lower()
        or "mix" in (s.headline or "").lower()
        for s in tx
    )


def test_assemble_persists_chapter_slides(deal_root: Path) -> None:
    from agetic_cdd_api.services_fdd_assemble import assemble_and_persist
    from agetic_cdd_api.services_fdd_render import ensure_phase0_run
    from agetic_cdd_api.services_fdd_store import load_report_spec

    slug = "ch-assemble"
    (deal_root / slug).mkdir(parents=True)
    manifest, store, _ = ensure_phase0_run(
        slug, company="Acme", revenue_fy24=100.0, prefer_current_release=True
    )
    spec = assemble_and_persist(
        slug, manifest.run_id, store=store, company="Acme", update_manifest=True
    )
    assert chapter_sequence(list(spec.slides)) == expected_chapter_ids()
    persisted = load_report_spec(slug, manifest.run_id)
    assert persisted is not None
    assert chapter_sequence(list(persisted.slides)) == expected_chapter_ids()
    assert any(n.node_id.startswith("slide_ch_") for n in persisted.nodes)


def test_fdd_report_pptx_follows_chapter_order(deal_root: Path) -> None:
    from agetic_cdd_api.report_fdd import FddReportBuilder
    from agetic_cdd_api.services_fdd_render import ensure_phase0_run

    slug = "ch-pptx"
    (deal_root / slug).mkdir(parents=True)
    ensure_phase0_run(slug, company="Acme", revenue_fy24=100.0)
    events = list(FddReportBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in events)
    out = list((deal_root / slug / "reports" / "fdd_report").glob("*_FDD_Report.pptx"))
    assert out
    inv = slide_chrome_inventory(out[0])
    texts = [" | ".join(row["texts"][:2]) for row in inv]
    # Cover / Contents / Introduction / Executive summary appear in order
    joined = "\n".join(texts)
    assert "CONTENTS" in joined
    assert "INTRODUCTION" in joined
    assert "EXECUTIVE SUMMARY" in joined
    assert "QUALITY OF EARNINGS" in joined
    assert "TRADING" in joined
    assert "DEAL CONSIDERATIONS" in joined
    assert "APPENDICES" in joined
    # Banner order: INTRODUCTION before TRANSACTION before QoE
    intro_i = next(i for i, t in enumerate(texts) if "INTRODUCTION" in t)
    tx_i = next(i for i, t in enumerate(texts) if "TRANSACTION AND BUSINESS" in t)
    qoe_i = next(i for i, t in enumerate(texts) if "QUALITY OF EARNINGS" in t)
    assert intro_i < tx_i < qoe_i


def test_write_chapter_slides_chrome(tmp_path: Path) -> None:
    store = ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="", exhibits=[])
    slides = plan_chapter_slides(company="Acme", store=store)
    path = tmp_path / "chapters.pptx"
    write_fdd_presentation(path, slides)
    inv = slide_chrome_inventory(path)
    assert len(inv) == len(slides)
    content = [r for r in inv if r["page"] >= 3]
    assert any(r["has_source"] for r in content)
    assert any(r["has_evidence"] for r in content)
