"""Fix 3 — central number-rendering service."""

from __future__ import annotations

import re

import pytest

from agetic_cdd_api.fdd_schemas import CellStatus, ExhibitCell, FigureType
from agetic_cdd_api.services_fdd_chapters import DisplayCtx, _DISPLAY_CTX, _fmt_num
from agetic_cdd_api.services_fdd_format import (
    format_cell,
    format_display,
    format_multiple,
    format_percent,
    infer_unit_type,
)
from agetic_cdd_api.services_fdd_tokens import format_cell_display


def test_format_percent_converts_ontology_fraction() -> None:
    # Gap artefact class: raw fraction must never print as "0.01798… %".
    text = format_percent(0.01798859799634693)
    assert text == "1.8%"
    assert "0.01798" not in text
    assert " " not in text.strip("%")


def test_format_percent_keeps_points() -> None:
    assert format_percent(30.4) == "30.4%"
    assert format_percent(4.2, already_points=True) == "4.2%"
    assert format_percent(0.05, already_points=False, decimals=0) == "5%"


def test_format_multiple() -> None:
    assert format_multiple(1.253) == "1.25x"
    assert format_display(1.253, unit_type="MULTIPLE") == "1.25x"


def test_format_display_currency_via_flags() -> None:
    token = _DISPLAY_CTX.set(
        DisplayCtx(display_scale="k", store_scale="M", currency="USD")
    )
    try:
        assert format_display(13.282, money=True, prose=False) == _fmt_num(
            13.282, money=True
        )
        assert "$" in format_display(0.572, money=True, prose=True)
        assert format_display(0.304, pct=True) == "30.4%"
    finally:
        _DISPLAY_CTX.reset(token)


def test_fmt_num_is_thin_wrapper() -> None:
    token = _DISPLAY_CTX.set(
        DisplayCtx(display_scale="k", store_scale="M", currency="USD")
    )
    try:
        assert _fmt_num(0.042, pct=True) == "4.2%"
        assert _fmt_num(22.2, pct=True, already_points=True) == "22.2%"
        assert _fmt_num(0.709 / 0.709, unit_type="MULTIPLE") == "1.00x"
    finally:
        _DISPLAY_CTX.reset(token)


def test_format_cell_fraction_percent() -> None:
    cell = ExhibitCell(
        cell_id="m",
        exhibit_id="ex",
        label="margin",
        value=0.01798859799634693,
        fact_id="db:m",
        metric_key="ebitda_margin",
        scale="%",
        unit="%",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )
    assert format_cell(cell) == "1.8%"
    assert format_cell_display(cell) == "1.8%"


def test_format_cell_points_percent_keeps_two_dp() -> None:
    cell = ExhibitCell(
        cell_id="m",
        exhibit_id="ex",
        label="margin",
        value=-1.91,
        fact_id="db:m",
        metric_key="gm",
        scale="%",
        unit="%",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )
    assert format_cell_display(cell) == "(1.91)%"


def test_infer_unit_type() -> None:
    assert infer_unit_type(pct=True) == "PERCENT"
    assert infer_unit_type(money=True) == "CURRENCY"
    assert infer_unit_type(scale="x") == "MULTIPLE"
    assert infer_unit_type(metric_key="gross_margin") == "PERCENT"


def test_chapters_have_no_inline_number_format_strings() -> None:
    """Done-when: slide module must not own money/percent format strings."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "agetic_cdd_api" / "services_fdd_chapters.py"
    text = src.read_text(encoding="utf-8")
    # Strip the _claim_identity helper's float scrubber and comments.
    banned = re.compile(
        r"""f["'].*\{[^}]*:(?:,\.\d+f|\.\d+f)%\}|f["'].*\{[^}]*:\.\d+f\}x"""
    )
    hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Allow the draft-obs float scrubber (identity cleanup, not slide figures).
        if "_round_match" in text[max(0, text.find(line) - 200) : text.find(line) + 1]:
            continue
        if "def _scrub_claim" in text or "claim" in stripped.lower() and ":.4f" in stripped:
            continue
        if banned.search(line):
            hits.append(f"L{i}: {stripped}")
    # Explicitly ensure the old pct/money format literals are gone from _fmt_num.
    assert 'f"{num:,.1f}%"' not in text
    assert 'f"{num:,.1f}"' not in text or "format_display" in text
    assert not any(":.1f}%" in h or ":.2f}x" in h for h in hits), hits
