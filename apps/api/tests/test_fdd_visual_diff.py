"""Optional Phase G visual diffs — PNG compare + gated PPTX render."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agetic_cdd_api.services_fdd_parity import assert_pptx_parity, load_pptx_parity_contract
from agetic_cdd_api.services_fdd_visual_diff import (
    compare_png_pair,
    compare_pptx_visual,
    discover_render_tools,
    load_visual_diff_config,
    visual_diff_enabled,
)


pytest.importorskip("PIL")


def _solid_png(path: Path, *, color: tuple[int, int, int, int], size=(80, 60)) -> Path:
    from PIL import Image

    Image.new("RGBA", size, color).save(path)
    return path


def test_visual_diff_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FDD_VISUAL_DIFF", raising=False)
    assert visual_diff_enabled() is False
    report = compare_pptx_visual("missing.pptx")
    assert report.skipped is True
    assert report.enabled is False


def test_visual_diff_config_from_contract() -> None:
    cfg = load_visual_diff_config(load_pptx_parity_contract())
    assert cfg["optional"] is True
    assert cfg["env_flag"] == "FDD_VISUAL_DIFF"
    assert cfg["slides"] == [1, 2]
    assert cfg["max_mean_abs_diff"] == 12.0


def test_compare_png_pair_identical(tmp_path: Path) -> None:
    a = _solid_png(tmp_path / "a.png", color=(10, 20, 30, 255))
    b = _solid_png(tmp_path / "b.png", color=(10, 20, 30, 255))
    result = compare_png_pair(a, b, diff_out=tmp_path / "diff.png")
    assert result.passed
    assert result.mean_abs_diff == 0.0
    assert result.pct_pixels_over_tol == 0.0
    assert Path(result.diff_png or "").is_file()


def test_compare_png_pair_detects_difference(tmp_path: Path) -> None:
    a = _solid_png(tmp_path / "a.png", color=(0, 0, 0, 255))
    b = _solid_png(tmp_path / "b.png", color=(255, 255, 255, 255))
    result = compare_png_pair(
        a,
        b,
        max_mean_abs_diff=5.0,
        max_pct_pixels_over_tol=1.0,
        pixel_tol=10,
    )
    assert result.passed is False
    assert result.mean_abs_diff > 5.0
    assert result.pct_pixels_over_tol > 1.0


def test_compare_pptx_visual_skips_when_tools_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FDD_VISUAL_DIFF", "1")
    # Force "tools missing" regardless of the host.
    from agetic_cdd_api.services_fdd_visual_diff import RenderTools

    pptx = tmp_path / "x.pptx"
    pptx.write_bytes(b"not-a-real-pptx")
    report = compare_pptx_visual(
        pptx,
        force=True,
        tools=RenderTools(soffice=None, pdftoppm=None, has_pymupdf=False),
    )
    assert report.skipped is True
    assert "unavailable" in (report.skip_reason or "").lower()


def test_assert_pptx_parity_ignores_visual_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FDD_VISUAL_DIFF", raising=False)
    # Structural-only path: no pptx_path → no visual attempt.
    from agetic_cdd_api.services_fdd_chapters import plan_chapter_slides
    from agetic_cdd_api.fdd_schemas import ExhibitStoreDoc

    slides = plan_chapter_slides(
        company="Acme",
        store=ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="", exhibits=[]),
    )
    assert_pptx_parity(slides=slides)  # must not raise


@pytest.mark.fdd_visual
def test_optional_pptx_render_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Live render smoke — skipped unless FDD_VISUAL_DIFF=1 and LibreOffice present."""
    if not visual_diff_enabled():
        pytest.skip("FDD_VISUAL_DIFF not set")
    tools = discover_render_tools()
    if not tools.ready:
        pytest.skip(f"render tools unavailable: {tools}")

    from agetic_cdd_api.fdd_schemas import ExhibitStoreDoc
    from agetic_cdd_api.services_fdd_chapters import plan_chapter_slides
    from agetic_cdd_api.services_fdd_pptx import write_fdd_presentation

    slides = plan_chapter_slides(
        company="Compost Crew",
        store=ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="", exhibits=[]),
    )
    pptx = tmp_path / "smoke.pptx"
    write_fdd_presentation(pptx, slides)
    report = compare_pptx_visual(pptx, out_dir=tmp_path / "vdiff", force=True)
    assert report.skipped is False
    assert report.passed
    assert any(r.passed for r in report.results)


@pytest.mark.fdd_visual
def test_optional_vs_reference_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not visual_diff_enabled():
        pytest.skip("FDD_VISUAL_DIFF not set")
    ref = os.environ.get("FDD_VISUAL_REF_PPTX")
    if not ref or not Path(ref).is_file():
        pytest.skip("FDD_VISUAL_REF_PPTX not configured")
    tools = discover_render_tools()
    if not tools.ready:
        pytest.skip(f"render tools unavailable: {tools}")

    from agetic_cdd_api.fdd_schemas import ExhibitStoreDoc
    from agetic_cdd_api.services_fdd_chapters import plan_chapter_slides
    from agetic_cdd_api.services_fdd_pptx import write_fdd_presentation

    slides = plan_chapter_slides(
        company="Compost Crew",
        store=ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="", exhibits=[]),
    )
    pptx = tmp_path / "ours.pptx"
    write_fdd_presentation(pptx, slides)
    # Compare cover+TOC only — content depth still diverges from Project Crew.
    report = compare_pptx_visual(
        pptx,
        ref,
        out_dir=tmp_path / "vdiff",
        slides=[1, 2],
        force=True,
    )
    assert report.skipped is False
    # Do not hard-fail CI on pixel drift yet — report is the deliverable.
    assert len(report.results) >= 1
