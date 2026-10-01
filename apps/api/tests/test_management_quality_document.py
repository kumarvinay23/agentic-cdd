"""Management Quality — DiligenceIQ prompt-book team assessment."""

from __future__ import annotations

from agetic_cdd_api.agent_document_management_quality import (
    _heuristic_management_quality_spec,
    build_management_quality_spec,
    render_management_quality_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import compose_system, listed_agents


class _FakeDeal:
    id = "deal-mq-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _hr_corpus() -> str:
    return (
        "10 HR Organizational Due Diligence. Leadership Team Succession Risk. "
        "Bhavish Aggarwal CEO & Founder 8 years Prior Experience Ola Cabs High Risk. "
        "Harish Abichandani CFO 3 years Prior Experience listed-corp CFO Medium Risk. "
        "Suvonil Chatterjee CTO 4 years Prior Experience EV software Medium Risk. "
        "Key-man dependency on Bhavish Aggarwal — no clear succession plan documented. "
        "Technology attrition at 31% creates IP and continuity risk. "
        "ESOP Pool (Diluted) 5.1% Employee. Notice period 3 months for CXOs. "
        "Board of Directors Name Role Independence "
        "Bhavish Aggarwal Chairman & Managing Director Executive "
        "Harish Abichandani Chief Financial Officer Executive "
        "Ramesh Natarajan Independent Director Independent "
        "Aisha Kapoor Independent Director Independent. "
        "CEO Bhavish Aggarwal CFO Harish Abichandani CTO Suvonil Chatterjee."
    )


def test_management_quality_prompt_book_listed() -> None:
    system = compose_system("management_quality", sector="EV", geography="India")
    assert "management_quality" in listed_agents()
    assert "Never infer a vacancy" in system
    assert system.count("WHERE TO LOOK, IN THIS ORDER") == 1


def test_management_quality_markdown_follows_prompt_book() -> None:
    f06 = {
        "c_suite": [
            {"role": "CEO", "name": "Bhavish Aggarwal", "criticality": 5, "replaceability": 1},
            {"role": "CFO", "name": "Harish Abichandani", "criticality": 4, "replaceability": 2},
            {"role": "CTO", "name": "Suvonil Chatterjee", "criticality": 4, "replaceability": 2},
        ],
        "succession_gaps": [
            "Key-man dependency on Bhavish Aggarwal — no clear succession plan documented.",
            "Technology attrition at 31% creates IP and continuity risk.",
        ],
        "org_risk_score": 8,
    }
    heur = _heuristic_management_quality_spec(
        company="Test3",
        corpus=_hr_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf", "02_Corporate_Overview.pdf"],
        inaccessible=[],
        f06_spec=f06,
    )
    md = render_management_quality_markdown("Management Quality", heur)

    assert "## 1. Source Resolution" in md
    assert "## 2. Executive & Senior Operating Roster" in md
    assert "## 3. Key-Person Dependencies" in md
    assert "## 4. Second-Line Depth, Succession & Board" in md
    assert "## 5. Vacancies, Capability Gaps & Information Gaps" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "does not recommend invest or pass" in md.lower()
    assert "Bhavish" in md
    assert "information gap" in md.lower()
    assert "Confirmed Vacancies" in md
    # Missing bio fields are info gaps, not vacancies forced from absence
    assert any(
        "information gap" in str(g.get("hiring_cost_eligible", "")).lower()
        for g in heur["information_gaps"]
    )
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_render_agent_document_management_quality() -> None:
    output = {
        "agentName": "Management Quality",
        "target_company": "Test3",
        "sources": ["10_HR_Organizational_Due_Diligence.pdf"],
        "document": (
            "# Management Quality\n\n"
            "## 2. Executive & Senior Operating Roster\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("management_quality", output)
    assert "## 2. Executive" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_management_quality_from_f06_only() -> None:
    spec = build_management_quality_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "10_HR_Organizational_Due_Diligence.pdf",
                    "cdl_category": "company_management",
                    "excerpt": _hr_corpus(),
                }
            ],
            "category_counts": {"company_management": 1},
        },
        company="Test3",
        f06_spec={
            "c_suite": [
                {"role": "CEO", "name": "Bhavish Aggarwal", "criticality": 5, "replaceability": 1},
            ],
            "succession_gaps": ["Key-man dependency flagged."],
        },
        corpus=_hr_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        inaccessible=[],
    )
    md = render_management_quality_markdown("Management Quality", spec)
    assert "## 1. Source Resolution" in md
    assert "Preliminary Investment" not in md
