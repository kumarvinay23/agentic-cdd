"""Management Quality — DiligenceIQ prompt-book team assessment."""

from __future__ import annotations

import re
from pathlib import Path

from agetic_cdd_api.agent_document_management_quality import (
    _heuristic_management_quality_spec,
    build_management_quality_spec,
    render_management_quality_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-mq-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"
    metadata = {
        "deal_perimeter": "standalone ops",
        "transaction_type": "majority buyout",
        "as_of_date": "2024-12-31",
        "decision_stage": "IC",
    }


def _hr_corpus() -> str:
    return (
        "10 HR Organizational Due Diligence. Leadership Team Succession Risk. "
        "Bhavish Aggarwal CEO & Founder 8 years Prior Experience Ola Cabs High Risk. "
        "Harish Abichandani CFO 3 years Prior Experience listed-corp CFO Medium Risk. "
        "Suvonil Chatterjee CTO 4 years Prior Experience EV software Medium Risk. "
        "Key-man dependency on Bhavish Aggarwal — no clear succession plan documented. "
        "Technology attrition at 31% creates IP and continuity risk. "
        "ESOP Pool (Diluted) 5.1% Employee. Notice period 3 months for CXOs. "
        "Retention bonus for CTO tied to vesting schedule. "
        "Board of Directors Name Role Independence "
        "Bhavish Aggarwal Chairman & Managing Director Executive "
        "Harish Abichandani Chief Financial Officer Executive "
        "Ramesh Natarajan Independent Director Independent "
        "Aisha Kapoor Independent Director Independent. "
        "CEO Bhavish Aggarwal CFO Harish Abichandani CTO Suvonil Chatterjee. "
        "CFO delivered against budget in FY24; CTO missed product roadmap target."
    )


def _f06() -> dict:
    return {
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


def test_management_quality_prompt_book_listed() -> None:
    system = compose_system(
        "management_quality",
        sector="EV",
        geography="India",
        deal_perimeter="standalone ops",
        transaction_type="majority buyout",
        as_of_date="2024-12-31",
        decision_stage="IC",
    )
    assert "management_quality" in listed_agents()
    assert "Never infer a vacancy" in system
    assert system.count("WHERE TO LOOK, IN THIS ORDER") == 1
    body = agent_prompt("management_quality")
    assert "questions" in body.lower()
    assert "checklist" in body.lower() or "cv" in body.lower()
    assert "standalone ops" in system.lower() or "deal perimeter" in system.lower()


def test_management_quality_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_management_quality.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_management_quality_markdown_follows_prompt_book() -> None:
    heur = _heuristic_management_quality_spec(
        company="Test3",
        corpus=_hr_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf", "02_Corporate_Overview.pdf"],
        inaccessible=[],
        f06_spec=_f06(),
    )
    md = render_management_quality_markdown("Management Quality", heur)

    assert "## 1. Source Resolution" in md
    assert "## 2. Executive & Senior Operating Roster" in md
    assert "## 3. Key-Person Dependencies" in md
    assert "## 4. Second-Line Depth, Succession & Board" in md
    assert "## 5. Vacancies, Capability Gaps & Information Gaps" in md
    assert "## 6. Management Quality Evidence QA" in md
    assert "## 7. Questions and Inputs Required" in md
    assert "## 8. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "does not recommend invest or pass" in md.lower()
    assert "Bhavish" in md
    assert "information gap" in md.lower()
    assert "Confirmed Vacancies" in md
    assert any(
        "information gap" in str(g.get("hiring_cost_eligible", "")).lower()
        for g in heur["information_gaps"]
    )
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_roster_incentives_checklist_and_qa() -> None:
    heur = _heuristic_management_quality_spec(
        company="Test3",
        corpus=_hr_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        inaccessible=[],
        f06_spec=_f06(),
    )
    execs = heur.get("executives") or []
    assert len(execs) >= 3
    assert any(
        isinstance(e, dict)
        and e.get("tenure")
        and not str(e.get("tenure")).startswith("N/A")
        for e in execs
    )
    incentives = heur.get("incentive_clauses") or []
    assert any(
        isinstance(r, dict)
        and not str(r.get("extract") or "").startswith("Information")
        for r in incentives
    )
    checklist = heur.get("evidence_checklist") or []
    assert len(checklist) == 4
    assert any(r.get("status") == "CLOSED" for r in checklist if isinstance(r, dict))
    scores = heur.get("score_evidence") or []
    assert any(
        isinstance(r, dict) and "org_risk" in str(r.get("score") or "")
        for r in scores
    )
    qa = heur.get("mq_evidence_qa") or []
    checks = {r.get("check") for r in qa if isinstance(r, dict)}
    for need in (
        "role_roster_tenure_scale_plan_actual",
        "incentive_retention_clauses",
        "vacancy_capability_info_enum",
        "board_succession_tables",
        "score_evidence",
        "evidence_checklist_closure",
        "strategy_ic_esg_cross_check",
    ):
        assert need in checks
    # Vacancy enum must PASS — bios are info gaps not vacancies
    vac = next(r for r in qa if r.get("check") == "vacancy_capability_info_enum")
    assert vac.get("status") == "PASS"
    questions = heur.get("questions") or []
    assert questions
    # Without Strategy/IC/ESG priors, cross-check FAILs → READY capped
    assert heur.get("reliance_verdict") in {"LIMITED", "BLOCKED", "READY"}


def test_never_infer_vacancy_from_missing_bio() -> None:
    heur = _heuristic_management_quality_spec(
        company="Test3",
        corpus="CEO Jane Doe. CFO John Smith.",
        sources=["thin.pdf"],
        inaccessible=[],
        f06_spec={
            "c_suite": [
                {"role": "CEO", "name": "Jane Doe", "criticality": 5, "replaceability": 2},
            ],
            "succession_gaps": [],
        },
    )
    assert heur.get("confirmed_vacancies") == [] or all(
        "bio" not in str(v.get("evidence") or "").lower()
        for v in heur.get("confirmed_vacancies") or []
    )
    info = heur.get("information_gaps") or []
    assert any(
        isinstance(g, dict)
        and "no — information gap" in str(g.get("hiring_cost_eligible") or "").lower()
        for g in info
    )


def test_cross_check_with_strategy_prior() -> None:
    heur = _heuristic_management_quality_spec(
        company="Test3",
        corpus=_hr_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        inaccessible=[],
        f06_spec=_f06(),
        strategy_spec={
            "insight_snapshot": "Plan relies on Bhavish Aggarwal delivery.",
            "assessment_read": "CEO-led execution.",
        },
        ic_spec={"summary": "IC notes key-person on Bhavish."},
        esg_spec={"insight_snapshot": "Governance board independent majority."},
    )
    cross = heur.get("strategy_ic_esg_cross_check") or {}
    assert cross.get("strategic_direction_present")
    assert cross.get("ic_synthesis_present")
    assert cross.get("esg_present")
    assert cross.get("aligned")


def test_render_agent_document_management_quality() -> None:
    output = {
        "agentName": "Management Quality",
        "target_company": "Test3",
        "sources": ["10_HR_Organizational_Due_Diligence.pdf"],
        "document": (
            "# Management Quality\n\n"
            "## 2. Executive & Senior Operating Roster\n\n"
            "Seeded.\n\n"
            "## 8. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("management_quality", output)
    assert "## 2. Executive" in rendered
    assert "**Recommendation:**" not in rendered


def test_employee_yes_no_column_not_used_as_ceo_name() -> None:
    """Ledger 'Employee' Yes/No must never become the CEO / key-person name."""
    from agetic_cdd_api.agent_document_management_quality import (
        _executives_from_f06,
        _key_person_rows,
        _plausible_person_name,
    )

    assert not _plausible_person_name("No Employee")
    assert not _plausible_person_name("Yes Employee")
    corpus = (
        "Certificate Holder Job Title Employee Shares "
        "CS-01 Ben Parry CEO Yes 10,000,010 "
        "CS-03 Dan Israel Senior Vice President No 200,000 "
        "Ben Parry CEO No Employee 10,000,010"
    )
    execs = _executives_from_f06(None, corpus)
    names = [str(e.get("name") or "") for e in execs]
    assert any("Parry" in n for n in names)
    assert not any(re.search(r"(?i)^no\s+employee$", n) for n in names)
    assert not any("No Employee" in n for n in names)
    kps = _key_person_rows(execs, corpus, None)
    persons = " ".join(str(k.get("person") or "") for k in kps)
    assert "Parry" in persons
    assert "No Employee" not in persons


def test_controlling_shareholder_seeded_as_key_person() -> None:
    """CEO / majority owner must flag as key-person even without 'key-man' wording."""
    corpus = (
        "Cap Table Summary — Common Stock outstanding 10,294,861. "
        "Ben Parry 10,000,010 (97.14% of common); 61.27% of all outstanding; "
        "55.26% fully diluted. Ben Parry, CEO. "
        "Tiffany Williams (Commercial Driver) 2,070 shares."
    )
    heur = _heuristic_management_quality_spec(
        company="Compost Crew",
        corpus=corpus,
        sources=["securities_ledger.pdf"],
        inaccessible=[],
        f06_spec=None,
    )
    execs = heur.get("executives") or []
    assert any("Parry" in str(e.get("name") or "") for e in execs if isinstance(e, dict))
    kps = heur.get("key_persons") or []
    assert kps
    names = " ".join(str(k.get("person") or "") for k in kps if isinstance(k, dict))
    assert "Parry" in names
    assert "Commercial Driver" not in names
    insight = str(heur.get("insight_snapshot") or "")
    assert "0 named executives" not in insight
    assert "0 key-person" not in insight


def test_ceo_sentence_fragment_not_used_as_person_name() -> None:
    """'Compost Crew is led by a proven (CEO)' must not become the retention name."""
    from agetic_cdd_api.agent_document_management_quality import (
        _executives_from_f06,
        _plausible_person_name,
    )

    assert not _plausible_person_name("Compost Crew is led by a proven (CEO)")
    assert _plausible_person_name("Ben Parry (CEO)")
    corpus = (
        "Compost Crew is led by a proven operator. "
        "Ben Parry, CEO owns 97.14% of common."
    )
    execs = _executives_from_f06(None, corpus)
    names = [str(e.get("name") or "") for e in execs]
    assert any("Parry" in n for n in names)
    assert not any("led by" in n.lower() or "proven" in n.lower() for n in names)


def test_build_management_quality_from_f06_only() -> None:
    deal = _FakeDeal()
    spec = build_management_quality_spec(
        deal,  # type: ignore[arg-type]
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
        prefer_heuristic=True,
    )
    md = render_management_quality_markdown("Management Quality", spec)
    assert "## 1. Source Resolution" in md
    assert "## 8. Quality & Reliance" in md
    assert "Preliminary Investment" not in md
    slots = spec.get("deal_slots") or {}
    assert slots.get("deal_perimeter") == "standalone ops"
    assert spec.get("mq_evidence_qa")
