"""Phase G — FDD Report PPTX structural parity checks (CI guards).

Validates chapter storyline / banners / chrome against
``tests/fixtures/fdd/pptx_parity_contract.json`` (frozen from Project_Crew_FDD_1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pptx import Presentation

from agetic_cdd_api.fdd_schemas import SlideSpec
from agetic_cdd_api.services_fdd_chapters import (
    DEFAULT_CHAPTER_ORDER,
    chapter_sequence,
    expected_chapter_ids,
)
from agetic_cdd_api.services_fdd_pptx import SLIDE_H, SLIDE_W, slide_chrome_inventory

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "fdd" / "pptx_parity_contract.json"
)


def parity_contract_path() -> Path:
    return _CONTRACT_PATH


def load_pptx_parity_contract(path: Path | None = None) -> dict[str, Any]:
    p = path or parity_contract_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"parity contract must be an object: {p}")
    return raw


def _banner_blob(slide: SlideSpec) -> str:
    return " ".join(
        x
        for x in (
            slide.banner or "",
            slide.headline or "",
            slide.deal_name or "",
            "CONTENTS" if slide.layout == "toc" else "",
            (slide.deal_name or "FDD") if slide.layout == "cover" else "",
        )
        if x
    )


def check_slide_spec_parity(
    slides: list[SlideSpec],
    *,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Return human-readable failure strings (empty = pass)."""
    c = contract or load_pptx_parity_contract()
    failures: list[str] = []

    if len(slides) < int(c.get("min_slides") or 12):
        failures.append(f"slide_count {len(slides)} < min_slides {c['min_slides']}")

    # Cover + TOC first.
    if not slides or slides[0].layout != "cover":
        failures.append("first slide must be cover")
    if len(slides) < 2 or slides[1].layout != "toc":
        failures.append("second slide must be toc")

    chapters = {str(s.chapter or "") for s in slides}
    for ch in c.get("required_chapters") or []:
        if ch == "cover":
            if slides[0].layout != "cover":
                failures.append("missing chapter cover")
            continue
        if ch == "contents":
            if not any(s.layout == "toc" for s in slides):
                failures.append("missing chapter contents/toc")
            continue
        if ch not in chapters:
            failures.append(f"missing chapter {ch}")

    # Storyline order for body chapters.
    seq = chapter_sequence(slides)
    expected = list(c.get("chapter_order") or expected_chapter_ids())
    if seq != expected:
        failures.append(f"chapter_order {seq} != {expected}")

    # Contract order must stay aligned with planner defaults.
    planner = [ch for _n, ch, _b, _t in DEFAULT_CHAPTER_ORDER]
    if expected != planner:
        failures.append(f"contract chapter_order {expected} != planner {planner}")

    layouts = {str(s.layout) for s in slides}
    for layout in c.get("required_layouts") or []:
        if layout not in layouts:
            failures.append(f"missing layout {layout}")

    banners_present = " | ".join(_banner_blob(s).upper() for s in slides)
    for banner in c.get("required_banners") or []:
        if banner.upper() not in banners_present:
            failures.append(f"missing banner {banner}")

    # At least one table-bearing slide per core chapter.
    for ch in c.get("core_chapters_require_table") or []:
        ch_slides = [s for s in slides if s.chapter == ch]
        if not ch_slides:
            failures.append(f"core chapter {ch} missing")
            continue
        has_table = any(
            (s.table and (s.table.headers or s.table.rows))
            or (s.layout == "kpi_strip" and s.kpis)
            or (s.layout == "findings_rank" and (s.findings or (s.table and s.table.rows)))
            for s in ch_slides
        )
        if not has_table:
            failures.append(f"core chapter {ch} has no table/KPI content")

    chrome = c.get("chrome") or {}
    content = [s for s in slides if s.layout not in {"cover", "toc"}]
    if chrome.get("content_slides_require_source"):
        if not any(s.source for s in content):
            failures.append("no content slide has Source")
    if chrome.get("content_slides_require_evidence"):
        if not any(s.evidence_tier for s in content):
            failures.append("no content slide has Evidence tier")
    if chrome.get("content_slides_require_page_no"):
        if not all(s.page_no is not None for s in content):
            failures.append("content slides missing page_no")
    min_obs = int(chrome.get("min_content_slides_with_observations") or 0)
    if min_obs and sum(1 for s in content if s.observations) < min_obs:
        failures.append(f"fewer than {min_obs} content slides with Observations")
    min_tables = int(chrome.get("min_content_slides_with_tables") or 0)
    table_n = sum(
        1
        for s in content
        if (s.table and (s.table.headers or s.table.rows)) or (s.layout == "kpi_strip" and s.table)
    )
    if min_tables and table_n < min_tables:
        failures.append(f"fewer than {min_tables} content slides with tables (got {table_n})")

    return failures


def check_pptx_file_parity(
    path: Path | str,
    *,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a rendered PPTX against size / banners / chrome inventory."""
    c = contract or load_pptx_parity_contract()
    path = Path(path)
    failures: list[str] = []
    if not path.is_file():
        return [f"missing pptx file: {path}"]

    prs = Presentation(str(path))
    size = c.get("slide_size") or {}
    tol = int(size.get("tolerance_emu") or 20000)
    want_w = int(size.get("width_emu") or int(SLIDE_W))
    want_h = int(size.get("height_emu") or int(SLIDE_H))
    if abs(int(prs.slide_width) - want_w) > tol:
        failures.append(f"slide_width {prs.slide_width} != {want_w} (±{tol})")
    if abs(int(prs.slide_height) - want_h) > tol:
        failures.append(f"slide_height {prs.slide_height} != {want_h} (±{tol})")

    n = len(prs.slides)
    if n < int(c.get("min_slides") or 12):
        failures.append(f"pptx slide_count {n} < min_slides {c['min_slides']}")

    inv = slide_chrome_inventory(path)
    blob = "\n".join(" | ".join(row.get("texts") or []) for row in inv).upper()
    for banner in c.get("required_banners") or []:
        if banner.upper() not in blob:
            failures.append(f"pptx missing banner {banner}")

    chrome = c.get("chrome") or {}
    content = [row for row in inv if int(row.get("page") or 0) >= 3]
    if chrome.get("content_slides_require_source") and not any(r.get("has_source") for r in content):
        failures.append("pptx content slides missing Source")
    if chrome.get("content_slides_require_evidence") and not any(
        r.get("has_evidence") for r in content
    ):
        failures.append("pptx content slides missing Evidence")
    min_obs = int(chrome.get("min_content_slides_with_observations") or 0)
    if min_obs and sum(1 for r in content if r.get("has_observations")) < min_obs:
        failures.append(f"pptx fewer than {min_obs} Observation panels")
    min_tables = int(chrome.get("min_content_slides_with_tables") or 0)
    if min_tables and sum(1 for r in content if int(r.get("tables") or 0) >= 1) < min_tables:
        failures.append(f"pptx fewer than {min_tables} table slides")

    return failures


def check_artifact_extensions(
    report_dir: Path | str,
    *,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Ensure fdd_report folder has PPTX only (no DOCX/PDF twins)."""
    c = contract or load_pptx_parity_contract()
    root = Path(report_dir)
    failures: list[str] = []
    if not root.is_dir():
        return [f"missing report dir: {root}"]
    art = c.get("artifact") or {}
    allowed = {e.lower() for e in (art.get("allowed_extensions") or [".pptx"])}
    forbidden = {e.lower() for e in (art.get("forbidden_extensions") or [".docx", ".pdf"])}
    files = [p for p in root.iterdir() if p.is_file()]
    pptx = [p for p in files if p.suffix.lower() in allowed]
    if not pptx:
        failures.append(f"no {sorted(allowed)} artifact in {root}")
    for p in files:
        if p.suffix.lower() in forbidden:
            # Side JSON / figures companions are fine; only block twin report formats.
            if p.name.endswith("_figures.json") or p.name.endswith("_side.json"):
                continue
            if any(tag in p.name.lower() for tag in ("fdd_report", "fdd_deck", "report", "deck")):
                failures.append(f"forbidden artifact {p.name}")
            elif p.suffix.lower() in {".docx", ".pdf"} and "fdd" in p.name.lower():
                failures.append(f"forbidden artifact {p.name}")
            elif p.suffix.lower() in {".docx", ".pdf"}:
                # Any Word/PDF under fdd_report/ is a twin.
                failures.append(f"forbidden twin artifact {p.name}")
    return failures


def assert_pptx_parity(
    *,
    slides: list[SlideSpec] | None = None,
    pptx_path: Path | str | None = None,
    report_dir: Path | str | None = None,
    contract: dict[str, Any] | None = None,
    visual_reference: Path | str | None = None,
    visual_out_dir: Path | str | None = None,
    include_visual: bool | None = None,
) -> None:
    """Raise AssertionError with joined failures if any check fails.

    Visual PNG diffs are optional (Phase G). They run only when
    ``include_visual=True`` or ``FDD_VISUAL_DIFF=1`` and render tools exist;
    skips never fail structural parity.
    """
    c = contract or load_pptx_parity_contract()
    failures: list[str] = []
    if slides is not None:
        failures.extend(check_slide_spec_parity(slides, contract=c))
    if pptx_path is not None:
        failures.extend(check_pptx_file_parity(pptx_path, contract=c))
    if report_dir is not None:
        failures.extend(check_artifact_extensions(report_dir, contract=c))

    run_visual = include_visual
    if run_visual is None:
        from agetic_cdd_api.services_fdd_visual_diff import visual_diff_enabled

        run_visual = visual_diff_enabled()
    if run_visual and pptx_path is not None:
        from agetic_cdd_api.services_fdd_visual_diff import compare_pptx_visual

        report = compare_pptx_visual(
            pptx_path,
            visual_reference,
            out_dir=visual_out_dir,
            contract=c,
            force=True,
        )
        if not report.skipped:
            failures.extend(report.failures)

    if failures:
        raise AssertionError("FDD PPTX parity failures:\n- " + "\n- ".join(failures))
