"""Phase F — UI/API/catalog cleanup: FDD is PPTX-only."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.report_store import REPORT_TYPES, is_fdd_pptx_only, list_reports
from agetic_cdd_api.routers_reports import _resolve_download_artifact


@pytest.fixture()
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_fdd_report_catalog_is_pptx_only() -> None:
    assert REPORT_TYPES["fdd_report"]["export"] == "pptx"
    assert REPORT_TYPES["fdd_report"]["formats"] == ["pptx"]
    assert "docx" not in REPORT_TYPES["fdd_report"]["formats"]
    assert "pdf" not in REPORT_TYPES["fdd_report"]["formats"]
    assert REPORT_TYPES["fdd_deck"]["deprecated"] is True
    assert REPORT_TYPES["fdd_deck"]["formats"] == ["pptx"]
    assert is_fdd_pptx_only("fdd_report")
    assert is_fdd_pptx_only("fdd_deck")
    assert not is_fdd_pptx_only("cdd_deck")


def test_download_rejects_pdf_for_fdd(deal_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agetic_cdd_api.routers_reports as reports_mod

    monkeypatch.setattr(reports_mod, "_deals_root", lambda: deal_root)
    slug = "fdd-dl"
    pptx = deal_root / slug / "reports" / "fdd_report" / "Acme_FDD_Report.pptx"
    pptx.parent.mkdir(parents=True)
    pptx.write_bytes(b"pptx-bytes")
    # Stale twin path must still be refused.
    meta = {
        "report_type": "fdd_report",
        "status": "ready",
        "artifact_path": str(pptx.relative_to(deal_root / slug)),
        "pdf_artifact_path": "reports/fdd_report/Acme_FDD_Report.pdf",
    }
    with pytest.raises(HTTPException) as exc:
        _resolve_download_artifact(slug, meta, format="pdf")
    assert exc.value.status_code == 400
    assert "PowerPoint only" in str(exc.value.detail)

    path, fmt = _resolve_download_artifact(slug, meta, format=None)
    assert fmt == "pptx"
    assert path.resolve() == pptx.resolve()


def test_fdd_deck_alias_writes_chapter_pptx(deal_root: Path) -> None:
    from agetic_cdd_api.report_fdd import FddDeckBuilder, FddReportBuilder
    from agetic_cdd_api.services_fdd_render import ensure_phase0_run

    slug = "fdd-alias"
    (deal_root / slug).mkdir(parents=True)
    ensure_phase0_run(slug, company="Acme", revenue_fy24=100.0)

    events = list(FddReportBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in events)
    report_out = list((deal_root / slug / "reports" / "fdd_report").glob("*_FDD_Report.pptx"))
    assert report_out
    assert not list((deal_root / slug / "reports" / "fdd_report").glob("*.pdf"))
    assert not list((deal_root / slug / "reports" / "fdd_report").glob("*.docx"))

    events_deck = list(FddDeckBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in events_deck)
    deck_out = list((deal_root / slug / "reports" / "fdd_deck").glob("*_FDD_Deck.pptx"))
    assert deck_out
    assert not list((deal_root / slug / "reports" / "fdd_deck").glob("*.pdf"))
    assert not list((deal_root / slug / "reports" / "fdd_deck").glob("*.docx"))

    catalog = {r["report_type"]: r for r in list_reports(slug)}
    assert catalog["fdd_report"]["pdf_available"] is False
    assert catalog["fdd_deck"]["pdf_available"] is False
    assert catalog["fdd_deck"]["deprecated"] is True
