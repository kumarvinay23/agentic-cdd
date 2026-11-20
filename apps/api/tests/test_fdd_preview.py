"""FDD preview must come from SlideSpec (same source as PPTX), not CDD scrape."""

from __future__ import annotations

from agetic_cdd_api.fdd_schemas import (
    KpiTile,
    SlideSpec,
    SlideTable,
)
from agetic_cdd_api.report_preview import preview_fdd_from_slides


def test_preview_fdd_from_slides_preserves_chrome_fields() -> None:
    slides = [
        SlideSpec(
            slide_id="cover",
            layout="cover",
            deal_name="Project Compost Crew",
            engagement="Financial due diligence",
            basis_line="Unaudited monthly management accounts",
            page_no=1,
        ),
        SlideSpec(
            slide_id="ch_es_kpi",
            layout="kpi_strip",
            chapter="es",
            banner="EXECUTIVE SUMMARY",
            headline="Diligence EBITDA is $561k — earnings quality needs scrutiny",
            kpis=[
                KpiTile(label="Diligence EBITDA, FY25", value="$561k", detail="Margin 4.2%"),
            ],
            table=SlideTable(
                title="Key figures ($k)",
                headers=["Metric", "FY25"],
                rows=[["Revenue", "13,412"]],
                basis="Unaudited monthly management accounts",
            ),
            observations=["Revenue grew 13.0% into FY25."],
            source="CC_Investor_Workbook_EXTERNAL.xlsx",
            evidence_tier="B",
            page_no=4,
            completeness_state="complete",
        ),
        SlideSpec(
            slide_id="ch_bs_leases",
            layout="section_table_obs",
            chapter="bs",
            banner="BALANCE SHEET, DEBT AND LEASES",
            headline="FY25 rent of $406k has limited lease-file backing",
            table=SlideTable(
                title="Lease and commitment evidence",
                headers=["Item", "Amount", "Source"],
                rows=[
                    [
                        "Lease files in data room",
                        "PARTIAL — rent not readable from lease PDF (open request)",
                        "Lease PDF / OCR — status PARTIAL",
                    ]
                ],
            ),
            observations=[
                "Leases and commitments is held — evidence incomplete for this run.",
                "R05: Schedule of all leases and site agreements",
            ],
            source="Diligence analysis; lease PDF if present",
            evidence_tier="A/C",
            completeness_state="held",
            page_no=24,
        ),
    ]

    payload = preview_fdd_from_slides(
        slides,
        chrome={
            "project_label": "Project Compost Crew",
            "basis_short": "Draft for discussion - Unaudited monthly management accounts",
            "display_scale": "k",
        },
    )

    assert payload["preview_mode"] == "fdd_slidespec"
    assert payload["chrome"]["family"] == "fdd"
    assert payload["slide_count"] == 3

    cover, es, lease = payload["slides"]
    assert cover["kind"] == "cover"
    assert cover["chrome"] == "fdd"
    assert "Compost Crew" in cover["title"]

    assert es["banner"] == "EXECUTIVE SUMMARY"
    assert "561k" in es["title"]
    assert es["table_title"] == "Key figures ($k)"
    assert es["table"][0] == ["Metric", "FY25"]
    assert es["kpis"][0]["value"] == "$561k"
    assert es["bullets"][0].startswith("Revenue grew")
    assert es["source"].startswith("CC_Investor")
    assert es["evidence_tier"] == "B"
    assert es["page"] == "04"
    assert "Project Compost Crew" in (es["subtitle"] or "")

    assert "HELD" in lease["banner"]
    assert "PARTIAL" in " ".join(lease["table"][1])
    assert any("R05" in b for b in lease["bullets"])
    assert "Narrative bind:" not in " ".join(lease["bullets"])
