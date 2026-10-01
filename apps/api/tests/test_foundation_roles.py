"""S0/S1 Foundation role mapping and VDR source binding."""

from __future__ import annotations

from agetic_cdd_api.foundation_roles import (
    bind_for_role,
    needed_role_codes,
    role_by_code,
    role_by_slug,
)
from agetic_cdd_api.services_library import classify_cdl


def test_s0_slug_contract() -> None:
    assert role_by_slug("strategic_direction").code == "F-01"
    assert role_by_slug("company_background").code == "F-05"
    assert role_by_slug("management_quality").code == "F-06"
    assert role_by_slug("regulatory_compliance").code == "F-04"
    assert role_by_code("F-02").slug is None
    assert role_by_code("F-03").slug is None
    assert role_by_slug("ip_and_technology").code == "F-IP"
    assert role_by_slug("esg_and_sustainability").code == "F-ESG"


def test_s1_filename_kinds() -> None:
    cases = [
        ("CyberGuard_CIM_Final.pdf", "deal_strategy", "cim"),
        ("01_Executive_Summary.pdf", "deal_strategy", "strategy"),
        ("03_Investment_Thesis.pdf", "deal_strategy", "strategy"),
        ("Project_Cyber_Teaser_v2.pdf", "deal_strategy", "teaser"),
        ("Process_Letter_Phase_1.pdf", "deal_strategy", "process"),
        ("Standard_NDA_CyberGuard.docx", "legal_esg", "nda"),
        ("Articles_of_Incorporation.pdf", "company_management", "articles"),
        ("Org_Chart_Oct2024.pptx", "company_management", "org_chart"),
        ("02_Corporate_Overview.pdf", "company_management", "company"),
        ("06_Legal_Due_Diligence.pdf", "legal_esg", "legal"),
        ("08_Technical_Due_Diligence.pdf", "operations", "technical"),
    ]
    for filename, category, kind in cases:
        got_cat, _secondary, conf = classify_cdl(filename=filename, text="revenue ebitda")
        assert got_cat == category, filename
        assert conf >= 0.9
        from agetic_cdd_api.services_library import _filename_type

        assert _filename_type(filename) == (category, kind), filename


def test_s2_role_order() -> None:
    assert needed_role_codes(None, full_phase=True) == [
        "F-01",
        "F-02",
        "F-03",
        "F-04",
        "F-IP",
        "F-ESG",
        "F-05",
        "F-06",
    ]
    assert needed_role_codes(["management_quality"], full_phase=False) == ["F-05", "F-06"]
    assert needed_role_codes(["ip_and_technology"], full_phase=False) == ["F-IP"]
    assert needed_role_codes(["strategic_direction"], full_phase=False) == ["F-01"]


def test_s1_bind_coverage() -> None:
    index = {
        "documents": [
            {"filename": "CIM.pdf", "doc_kind": "cim"},
            {"filename": "Teaser.pdf", "doc_kind": "teaser"},
            {"filename": "Overview.pdf", "doc_kind": "company"},
            {"filename": "Legal_DD.pdf", "doc_kind": "legal"},
        ]
    }
    f01 = bind_for_role(index, role_by_code("F-01"))
    assert f01["coverage"] == "full"
    assert f01["primary"] == ["CIM.pdf"]
    assert f01["secondary"] == ["Teaser.pdf"]

    f03 = bind_for_role(index, role_by_code("F-03"))
    assert f03["coverage"] == "missing"
    assert f03["primary"] == []

    f05 = bind_for_role(index, role_by_code("F-05"))
    assert f05["coverage"] == "partial"
    assert f05["secondary"] == ["Overview.pdf"]

    f04 = bind_for_role(index, role_by_code("F-04"))
    assert f04["coverage"] == "partial"
    assert f04["secondary"] == ["Legal_DD.pdf"]
