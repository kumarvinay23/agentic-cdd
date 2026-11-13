from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.fdd_schemas import StubRenderPage
from agetic_cdd_api.services_fdd_report_pdf import (
    PAGE_H,
    PAGE_W,
    _page_role,
    _parse_finding,
    write_fdd_findings_pdf,
)


def test_parse_finding_card_body() -> None:
    page = StubRenderPage(
        title="B12AB · Margin concentration",
        body=(
            "[HIGH] Margin concentration in one SKU\n"
            "Observation: Top SKU is 71% of GP.\n"
            "Implication: Price risk is concentrated.\n"
            "Evidence: ex_m2.cell_1"
        ),
    )
    parsed = _parse_finding(page)
    assert parsed is not None
    assert parsed["severity"] == "high"
    assert "Margin concentration" in parsed["title"]
    assert _page_role(page) == "finding"


def test_write_landscape_findings_pdf(tmp_path: Path) -> None:
    pages = [
        StubRenderPage(
            title="Cover",
            body="Financial & tax due diligence — findings report",
            kind="cover",
        ),
        StubRenderPage(
            title="Executive summary",
            body="Findings: 1 high · 0 moderate · 0 low\n• Key point one",
        ),
        StubRenderPage(
            title="A1 · Test finding",
            body=(
                "[HIGH] Test finding\n"
                "Observation: Observed gap.\n"
                "Implication: Needs true-up.\n"
                "Evidence: claim_1"
            ),
        ),
    ]
    out = tmp_path / "fdd.pdf"
    write_fdd_findings_pdf(
        path=out,
        title="FDD Report — PackCo",
        company="PackCo",
        pages=pages,
    )
    assert out.exists() and out.stat().st_size > 500

    import fitz

    doc = fitz.open(str(out))
    assert len(doc) == 3
    rect = doc[0].rect
    assert abs(float(rect.width) - PAGE_W) < 1.0
    assert abs(float(rect.height) - PAGE_H) < 1.0
    cover = doc[0].get_text() or ""
    assert "PackCo" in cover
    assert "findings report" in cover.lower()
    finding = doc[2].get_text() or ""
    assert "KEY FINDING" in finding
    assert "OBSERVATIONS" in finding
