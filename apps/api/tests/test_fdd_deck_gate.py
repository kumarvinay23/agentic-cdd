"""Fix 8 — deck release gate on open block flags."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agetic_cdd_api.fdd_schemas import PptxChrome, SlideSpec, SlideTable
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_deck_gate import (
    assert_deck_release_allowed,
    evaluate_deck_release_gate,
    name_block_flag,
    stamp_slide_completeness,
)
from agetic_cdd_api.services_fdd_pptx import write_fdd_presentation
from agetic_cdd_api import services_rule_checker as rule_mod


_DEAL = "fix8-deck-gate"


def _seed_flags(flags: list[dict]) -> None:
    rule_mod._FLAGS[_DEAL] = list(flags)


def _clear_flags() -> None:
    rule_mod._FLAGS.pop(_DEAL, None)


def test_name_block_flag() -> None:
    named = name_block_flag(
        {
            "code": "R-BS-03",
            "schedule_id": "FDD-12",
            "message": "The balance sheet balances.",
            "flag_id": "fl-1",
        }
    )
    assert named.display() == "R-BS-03 (FDD-12): The balance sheet balances."


def test_gate_allows_when_no_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_flags()
    monkeypatch.setattr(
        "agetic_cdd_api.services_published_pages._deal_id",
        lambda key: key,
    )
    gate = evaluate_deck_release_gate(_DEAL)
    assert gate.allowed
    assert gate.named_flags() == []
    assert_deck_release_allowed(_DEAL)


def test_gate_allows_warn_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_published_pages._deal_id",
        lambda key: key,
    )
    _seed_flags(
        [
            {
                "code": "R-WARN-01",
                "severity": "warn",
                "schedule_id": "FDD-12",
                "message": "Soft warning",
                "status": "OPEN",
            }
        ]
    )
    try:
        gate = evaluate_deck_release_gate(_DEAL)
        assert gate.allowed
    finally:
        _clear_flags()


def test_gate_refuses_and_names_open_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_published_pages._deal_id",
        lambda key: key,
    )
    _seed_flags(
        [
            {
                "code": "R-BS-03",
                "severity": "block",
                "schedule_id": "FDD-12",
                "message": "The balance sheet balances.",
                "status": "OPEN",
                "flag_id": "fl-bs",
            },
            {
                "code": "R-QOE-01",
                "severity": "block",
                "schedule_id": "FDD-03",
                "message": "EBITDA bridge incomplete.",
                "status": "OPEN",
                "flag_id": "fl-qoe",
            },
        ]
    )
    try:
        gate = evaluate_deck_release_gate(_DEAL)
        assert not gate.allowed
        names = gate.named_flags()
        assert any("R-BS-03" in n and "FDD-12" in n for n in names)
        assert any("R-QOE-01" in n and "FDD-03" in n for n in names)
        with pytest.raises(GateBlockedError) as exc:
            assert_deck_release_allowed(_DEAL)
        msg = str(exc.value)
        assert "R-BS-03" in msg
        assert "FDD-12" in msg
        assert "R-QOE-01" in msg
    finally:
        _clear_flags()


def test_export_chapter_pptx_refuses_on_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_published_pages._deal_id",
        lambda key: key,
    )
    _seed_flags(
        [
            {
                "code": "R-PL-02",
                "severity": "block",
                "schedule_id": "FDD-06",
                "message": "Gross profit foots.",
                "status": "OPEN",
            }
        ]
    )
    try:
        from agetic_cdd_api import report_fdd as report_mod

        monkeypatch.setattr(
            report_mod,
            "report_artifact_dir",
            lambda *_a, **_k: tmp_path,
        )
        ctx = SimpleNamespace(deal_slug=_DEAL, pdf_artifact_path=None)
        with pytest.raises(GateBlockedError) as exc:
            report_mod._export_chapter_pptx(
                ctx,
                report_type="fdd_report",
                filename="blocked.pptx",
                product_label="FDD Report",
            )
        assert "R-PL-02" in str(exc.value)
        assert "FDD-06" in str(exc.value)
        assert not (tmp_path / "blocked.pptx").exists()
    finally:
        _clear_flags()


def test_stamp_slide_completeness_blocks_chapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_published_pages._deal_id",
        lambda key: key,
    )
    _seed_flags(
        [
            {
                "code": "R-BS-03",
                "severity": "block",
                "schedule_id": "FDD-12",
                "message": "The balance sheet balances.",
                "status": "OPEN",
            }
        ]
    )
    try:
        slides = [
            SlideSpec(
                slide_id="ch_bs_1",
                layout="section_table_obs",
                chapter="bs",
                banner="BALANCE SHEET",
                headline="Working capital",
                table=SlideTable(
                    title="NWC",
                    headers=["Item", "FY25"],
                    rows=[["NWC", "954"]],
                ),
            ),
            SlideSpec(
                slide_id="ch_trading_1",
                layout="section_table_obs",
                chapter="trading",
                headline="Trading ok",
                table=SlideTable(
                    title="Revenue",
                    headers=["Item", "FY25"],
                    rows=[["Revenue", "13,412"]],
                ),
            ),
        ]
        stamped = stamp_slide_completeness(slides, deal_slug=_DEAL)
        bs = next(s for s in stamped if s.slide_id == "ch_bs_1")
        tr = next(s for s in stamped if s.slide_id == "ch_trading_1")
        assert bs.completeness_state == "blocked"
        assert "R-BS-03" in bs.completeness_detail
        assert bs.table is not None
        assert any("block" in str(c).lower() for r in bs.table.rows for c in r)
        assert "954" not in "".join(str(c) for r in bs.table.rows for c in r)
        assert tr.completeness_state == "complete"
        assert tr.table is not None
        assert any("13,412" in str(c) for r in tr.table.rows for c in r)
    finally:
        _clear_flags()


def test_stamp_replaces_silent_empty_table() -> None:
    slides = [
        SlideSpec(
            slide_id="ch_es_kpi",
            layout="section_table_obs",
            chapter="es",
            headline="Key figures",
            table=SlideTable(title="Key figures", headers=["Metric"], rows=[]),
        )
    ]
    stamped = stamp_slide_completeness(slides, gate=None)
    assert stamped[0].completeness_state == "empty"
    assert stamped[0].table is not None
    assert stamped[0].table.rows
    assert any("empty" in str(c).lower() or "completeness" in str(c).lower()
               for r in stamped[0].table.rows for c in r)


def test_renderer_shows_completeness_not_empty_grid(tmp_path: Path) -> None:
    slide = SlideSpec(
        slide_id="empty",
        layout="section_table_obs",
        chapter="trading",
        banner="TRADING",
        headline="Should not be blank",
        completeness_state="empty",
        completeness_detail="No published figures",
        table=SlideTable(title="Revenue", headers=["a"], rows=[]),
    )
    out = tmp_path / "empty.pptx"
    write_fdd_presentation(out, [slide], chrome=PptxChrome())
    from pptx import Presentation

    prs = Presentation(str(out))
    texts = []
    for s in prs.slides:
        for shape in s.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
    blob = "\n".join(texts).lower()
    assert "empty" in blob or "completeness" in blob
