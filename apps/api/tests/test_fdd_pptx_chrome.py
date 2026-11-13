"""Phase B — FDD PPTX chrome layout contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation

from agetic_cdd_api.fdd_schemas import (
    KpiTile,
    PptxChrome,
    SlideSpec,
    SlideTable,
    StubRenderPage,
    TocEntry,
)
from agetic_cdd_api.services_fdd_pptx import (
    SLIDE_H,
    SLIDE_W,
    build_phase_b_fixture_slides,
    slide_chrome_inventory,
    stub_pages_to_slides,
    write_fdd_presentation,
)


@pytest.fixture()
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agetic_cdd_api import services_deals as deals_mod

    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_phase_b_fixture_has_chrome_layouts(tmp_path: Path) -> None:
    slides = build_phase_b_fixture_slides()
    assert len(slides) >= 8
    layouts = {s.layout for s in slides}
    for required in (
        "cover",
        "toc",
        "kpi_strip",
        "section_table_obs",
        "section_chart_obs",
        "findings_rank",
        "adj_detail",
        "request_table",
        "ledger_table",
        "glossary",
    ):
        assert required in layouts

    path = tmp_path / "fixture.pptx"
    write_fdd_presentation(path, slides)
    prs = Presentation(str(path))
    assert abs(prs.slide_width - SLIDE_W) < 1000
    assert abs(prs.slide_height - SLIDE_H) < 1000
    assert len(prs.slides) == len(slides)

    inv = slide_chrome_inventory(path)
    # Cover + TOC: no Observations / Evidence required
    # Fixture still names the chrome project; production chrome comes from the deal entity.
    assert inv[0]["texts"][0] in {"Project Crew", "FDD"}
    assert "CONTENTS" in inv[1]["texts"][0]

    content = [row for row in inv if row["page"] >= 3]
    assert any(row["has_observations"] for row in content)
    assert any(row["has_source"] for row in content)
    assert any(row["has_evidence"] for row in content)
    assert any(row["tables"] >= 1 for row in content)

    # KPI strip slide (page 3 in fixture) carries banner + evidence
    kpi = inv[2]
    assert "EXECUTIVE SUMMARY" in kpi["texts"][0]
    assert kpi["has_source"] and kpi["has_evidence"] and kpi["tables"] >= 1


def test_each_layout_renders(tmp_path: Path) -> None:
    chrome = PptxChrome()
    cases = [
        SlideSpec(slide_id="c", layout="cover", deal_name="Project Crew", page_no=1),
        SlideSpec(
            slide_id="t",
            layout="toc",
            banner="CONTENTS",
            headline="Contents",
            toc_entries=[TocEntry(number="01", title="Introduction", page="3")],
            page_no=2,
        ),
        SlideSpec(
            slide_id="k",
            layout="kpi_strip",
            banner="EXECUTIVE SUMMARY",
            headline="Headline",
            kpis=[KpiTile(label="Revenue", value="$1m", detail="YoY up")],
            observations=["Obs one"],
            source="Diligence analysis",
            evidence_tier="B",
            page_no=3,
        ),
        SlideSpec(
            slide_id="st",
            layout="section_table_obs",
            banner="TRADING",
            headline="Headline",
            table=SlideTable(title="Trading ($k)", headers=["Metric", "FY25"], rows=[["Revenue", "13,282"]]),
            observations=["Margin held"],
            source="Monthly P&L",
            evidence_tier="B",
            page_no=4,
        ),
        SlideSpec(
            slide_id="sc",
            layout="section_chart_obs",
            banner="TRADING",
            headline="Headline",
            chart_title="Revenue by stream",
            observations=["Municipal led growth"],
            source="Diligence analysis",
            evidence_tier="B/C",
            page_no=5,
        ),
        SlideSpec(
            slide_id="fr",
            layout="findings_rank",
            banner="EXECUTIVE SUMMARY",
            headline="Findings",
            table=SlideTable(headers=["#", "Finding"], rows=[["1", "EBITDA halved"]]),
            source="Diligence analysis",
            evidence_tier="A/B",
            page_no=6,
        ),
        SlideSpec(
            slide_id="ad",
            layout="adj_detail",
            banner="QUALITY OF EARNINGS",
            headline="ADJ-01",
            adj_id="ADJ-01",
            adj_body="Bad debt stays in costs.",
            observations=["Tier B"],
            source="Diligence analysis",
            evidence_tier="B",
            page_no=7,
        ),
        SlideSpec(
            slide_id="rq",
            layout="request_table",
            banner="DEAL CONSIDERATIONS",
            headline="Requests",
            table=SlideTable(headers=["ID", "Request"], rows=[["R01", "Audited accounts"]]),
            source="Diligence analysis",
            page_no=8,
        ),
        SlideSpec(
            slide_id="ld",
            layout="ledger_table",
            banner="APPENDICES",
            headline="Claims ledger",
            table=SlideTable(headers=["Claim", "Result"], rows=[["cl_1", "agrees"]]),
            source="Diligence analysis",
            page_no=9,
        ),
        SlideSpec(
            slide_id="gl",
            layout="glossary",
            banner="APPENDICES",
            headline="Glossary",
            table=SlideTable(headers=["Term", "Definition"], rows=[["QoE", "Quality of earnings"]]),
            source="Diligence analysis",
            page_no=10,
        ),
    ]
    path = tmp_path / "layouts.pptx"
    write_fdd_presentation(path, cases, chrome=chrome)
    inv = slide_chrome_inventory(path)
    assert len(inv) == 10
    assert inv[2]["has_observations"]
    assert inv[3]["tables"] == 1
    assert inv[3]["has_source"] and inv[3]["has_evidence"]


def test_stub_pages_adapter_applies_chrome(tmp_path: Path) -> None:
    pages = [
        StubRenderPage(title="FDD — Acme", body="Financial due diligence", kind="cover"),
        StubRenderPage(title="Agenda", body="• Executive summary\n• Trading", kind="slide"),
        StubRenderPage(
            title="Historical trading",
            body="FY2025 revenue 13.28\nInvestor workbook basis",
            kind="slide",
        ),
    ]
    slides = stub_pages_to_slides(pages, company="Acme")
    assert slides[0].layout == "cover"
    assert slides[1].layout == "toc"
    assert slides[2].layout == "section_table_obs"
    assert slides[2].banner.startswith("HISTORICAL")
    path = tmp_path / "adapted.pptx"
    write_fdd_presentation(path, slides)
    inv = slide_chrome_inventory(path)
    assert inv[2]["has_source"] and inv[2]["has_evidence"]


def test_fdd_report_builder_uses_chrome(deal_root: Path) -> None:
    from agetic_cdd_api.report_fdd import FddReportBuilder
    from agetic_cdd_api.services_fdd_render import ensure_phase0_run

    slug = "chrome-deal"
    (deal_root / slug).mkdir(parents=True)
    ensure_phase0_run(slug, company="Acme", revenue_fy24=100.0)
    events = list(FddReportBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in events)
    out = list((deal_root / slug / "reports" / "fdd_report").glob("*_FDD_Report.pptx"))
    assert out
    inv = slide_chrome_inventory(out[0])
    assert len(inv) >= 3
    # At least one content slide carries Source + Evidence chrome
    assert any(row["has_source"] and row["has_evidence"] for row in inv)
