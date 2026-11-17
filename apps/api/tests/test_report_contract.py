"""Gate FDD/CDD export on databook contract reliability."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pptx import Presentation
from pptx.util import Inches

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.report_store import finish_report, get_report, list_reports
from agetic_cdd_api.services_fdd_store import create_run
from agetic_cdd_api.services_report_contract import (
    ReportContractBlockedError,
    apply_report_contract_gate,
    evaluate_report_contract,
    watermark_pptx_unreliable,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def _minimal_pptx(path: Path) -> Path:
    prs = Presentation()
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    box = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(8), Inches(1))
    box.text_frame.text = "Clean slide"
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path


def test_ungated_report_types_are_reliable(deal_root: Path) -> None:
    gate = evaluate_report_contract("any-deal", "ic_memo")
    assert gate.reliable is True
    assert gate.source == "ungated"


def test_fdd_draft_manifest_is_unreliable(deal_root: Path) -> None:
    slug = "gate-draft"
    (deal_root / slug).mkdir(parents=True)
    create_run(
        slug,
        draft_mode=True,
        contract_complete=False,
        g6_blocked=True,
        contract_reasons=["labels_incomplete:revenue:FY2024:proof_level"],
    )
    gate = evaluate_report_contract(slug, "fdd_report")
    assert gate.reliable is False
    assert gate.draft_mode is True
    assert gate.g6_blocked is True
    assert "draft_mode" in gate.blockers
    assert "g6_blocked" in gate.blockers
    assert "labels_incomplete" in gate.blockers
    assert "UNRELIABLE" in gate.summary()


def test_fdd_complete_manifest_is_reliable(deal_root: Path) -> None:
    slug = "gate-ok"
    (deal_root / slug).mkdir(parents=True)
    create_run(
        slug,
        draft_mode=False,
        contract_complete=True,
        g6_blocked=False,
        contract_reasons=[],
    )
    gate = evaluate_report_contract(slug, "fdd_report")
    assert gate.reliable is True
    assert gate.blockers == []


def test_cdd_uses_databook_release_assessment(deal_root: Path) -> None:
    slug = "gate-cdd"
    (deal_root / slug).mkdir(parents=True)
    assessment = MagicMock(
        complete=False,
        g6_allowed=False,
        draft_mode=True,
        reasons=["labels_incomplete:ebitda:FY2023:source_ref"],
        release_id="rel_1",
    )
    with (
        patch(
            "agetic_cdd_api.services_fdd_bridge.resolve_release_for_deal",
            return_value=None,
        ),
        patch(
            "agetic_cdd_api.services_fdd_bridge.assess_databook_contract",
            return_value=assessment,
        ),
    ):
        gate = evaluate_report_contract(slug, "cdd_deck")
    assert gate.reliable is False
    assert gate.draft_mode is True
    assert "labels_incomplete" in gate.blockers


def test_watermark_stamps_unreliable_banner(deal_root: Path) -> None:
    path = _minimal_pptx(deal_root / "wm" / "deck.pptx")
    watermark_pptx_unreliable(path)
    prs = Presentation(str(path))
    texts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
    joined = "\n".join(texts)
    assert "UNRELIABLE" in joined
    assert "databook contract incomplete" in joined


def test_apply_gate_watermarks_when_not_strict(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "gate-wm"
    (deal_root / slug).mkdir(parents=True)
    create_run(
        slug,
        draft_mode=True,
        contract_complete=False,
        g6_blocked=True,
        contract_reasons=["no_material_cells"],
    )
    pptx = _minimal_pptx(deal_root / slug / "reports" / "fdd_report" / "Deck.pptx")
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.report_contract_strict",
        False,
        raising=False,
    )
    gate = apply_report_contract_gate(
        slug, "fdd_report", str(pptx.relative_to(deal_root / slug))
    )
    assert gate.reliable is False
    prs = Presentation(str(pptx))
    assert any(
        "UNRELIABLE" in (shape.text_frame.text if shape.has_text_frame else "")
        for slide in prs.slides
        for shape in slide.shapes
    )


def test_apply_gate_raises_in_strict_mode(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "gate-strict"
    (deal_root / slug).mkdir(parents=True)
    create_run(
        slug,
        draft_mode=True,
        contract_complete=False,
        g6_blocked=True,
        contract_reasons=["draft"],
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.report_contract_strict",
        True,
        raising=False,
    )
    with pytest.raises(ReportContractBlockedError, match="UNRELIABLE"):
        apply_report_contract_gate(slug, "fdd_report", None)


def test_finish_report_persists_unreliable_and_catalog(
    deal_root: Path,
) -> None:
    slug = "gate-meta"
    pptx = _minimal_pptx(deal_root / slug / "reports" / "fdd_report" / "Deck.pptx")
    finish_report(
        slug,
        "fdd_report",
        artifact_path=str(pptx.relative_to(deal_root / slug)),
        status="unreliable",
        reliability={
            "reliable": False,
            "draft_mode": True,
            "g6_blocked": True,
            "contract_complete": False,
            "blockers": ["draft_mode", "g6_blocked"],
        },
    )
    meta = get_report(slug, "fdd_report")
    assert meta is not None
    assert meta["status"] == "unreliable"
    assert meta["reliability"]["draft_mode"] is True

    catalog = {r["report_type"]: r for r in list_reports(slug)}
    assert catalog["fdd_report"]["status"] == "unreliable"
    assert catalog["fdd_report"]["reliability"]["reliable"] is False
