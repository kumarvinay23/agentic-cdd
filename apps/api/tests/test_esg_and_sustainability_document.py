"""ESG & Sustainability — DiligenceIQ prompt-book material ESG with consequence."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_esg_and_sustainability import (
    _heuristic_esg_and_sustainability_spec,
    _regime_threshold_applies,
    build_esg_and_sustainability_spec,
    render_esg_and_sustainability_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-esg-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _esg_corpus() -> str:
    return (
        "Environmental Clearance (Factory) MoEFCC Obtained Low. "
        "Labor Law Compliance (Factories Act) State Labour Dept. Generally Compliant Low. "
        "AIS 156 Battery Safety Standard BIS / AIS Compliant (Gen 2+) Low. "
        "FAME-II Subsidy Claims MHI / DHI Under Review Medium. "
        "SEBI LODR (Post-IPO) SEBI Compliant Low. "
        "Data Protection (DPDPA 2023) MeitY Implementation Ongoing Medium. "
        "CCPA Consumer Complaints CCPA Active Proceedings High. "
        "Electric two-wheeler zero-emission mobility displacing ICE petrol vehicles. "
        "Operating footprint: factory energy use and battery recycling obligations. "
        "Workforce Metrics. Metric FY2022 FY2023 FY2024E "
        "Total Headcount (FTE) 3,200 8,500 9,800 "
        "Attrition Rate (%) 18% 28% 24% "
        "Female Employees (%) 16% 19% 22% "
        "Employee Engagement Score 58 / 100 Benchmark 72 / 100 "
        "Below average — post-layoff impact "
        "eNPS (Employee NPS) 18 35 Dissatisfaction signals "
        "Attrition — Technology 31% 20% Talent retention risk "
        "Attrition — Manufacturing 19% 14% Elevated but stabilizing. "
        "CSRD mentioned in a peer slide only — company threshold not met. "
        "Do not infer emissions from revenue or site count."
    )


def _legacy() -> dict:
    return {
        "role_code": "F-ESG",
        "themes": [
            "SEBI LODR (Post-IPO) — Compliant (Low risk)",
            "Data Protection (DPDPA 2023) — Implementation Ongoing (Medium risk)",
            "CCPA Consumer Complaints — Active Proceedings (High risk)",
        ],
        "labour_flags": [
            "Labor Law Compliance (Factories Act) — Generally Compliant (Low risk)",
        ],
        "environment_flags": [
            "Environmental Clearance (Factory) — Obtained (Low risk)",
            "FAME-II Subsidy Claims — Under Review (Medium risk)",
        ],
    }


def test_esg_prompt_book_listed() -> None:
    system = compose_system("esg_and_sustainability", sector="EV", geography="India")
    assert "esg_and_sustainability" in listed_agents()
    assert "material" in system.lower()
    body = agent_prompt("esg_and_sustainability")
    assert "Ola" not in body and "SoftBank" not in body
    assert "threshold" in body.lower()
    assert "footprint" in body.lower()
    assert "invest" in body.lower() or "pass" in body.lower()


def test_esg_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_esg_and_sustainability.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_material_topics_have_why() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=_esg_corpus(),
        sources=["06_Legal_Due_Diligence.pdf", "10_HR_Organizational_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    topics = [
        t for t in (heur.get("material_topics") or [])
        if isinstance(t, dict) and not str(t.get("topic") or "").startswith("Information")
    ]
    assert topics
    for t in topics:
        assert t.get("pillar") in {"E", "S", "G"}
        assert t.get("why_material")
        assert not str(t.get("why_material")).startswith("N/A")


def test_product_separated_from_footprint() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=_esg_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    rows = [
        r for r in (heur.get("product_vs_footprint") or [])
        if isinstance(r, dict)
    ]
    lenses = " ".join(str(r.get("lens") or "") for r in rows).lower()
    assert "product" in lenses
    assert "footprint" in lenses or "operat" in lenses
    findings = " ".join(str(r.get("finding") or "") for r in rows).lower()
    assert "zero-emission" in findings or "electric" in findings or "ice" in findings


def test_measured_metrics_separate_targets() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=_esg_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    metrics = [
        m for m in (heur.get("measured_metrics") or [])
        if isinstance(m, dict)
        and not str(m.get("metric") or "").startswith("Information")
        and not str(m.get("measured_result") or "").startswith("Information")
        and not str(m.get("measured_result") or "").startswith("N/A")
    ]
    assert metrics
    attrition = next(
        (m for m in metrics if "attrition rate" in str(m.get("metric") or "").lower()),
        None,
    )
    assert attrition is not None
    assert attrition.get("boundary")
    assert attrition.get("method")
    assert attrition.get("baseline_year")
    assert attrition.get("denominator")
    # Targets must be a separate field from measured results
    assert "management_target" in attrition
    assert "18" in str(attrition.get("measured_result") or "") or "28" in str(
        attrition.get("measured_result") or ""
    )


def test_workforce_safety_cost_continuity() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=_esg_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    wf = [
        w for w in (heur.get("workforce_safety") or [])
        if isinstance(w, dict) and not str(w.get("factor") or "").startswith("Information")
    ]
    assert wf
    blob = " ".join(
        f"{w.get('factor')} {w.get('record')} {w.get('cost_or_continuity')}" for w in wf
    ).lower()
    assert "attrition" in blob or "turnover" in blob or "engagement" in blob
    assert any(
        w.get("cost_or_continuity")
        and not str(w.get("cost_or_continuity")).startswith("Information")
        for w in wf
    )


def test_regime_threshold_not_applied_blindly() -> None:
    applies, rationale = _regime_threshold_applies(
        "CSRD",
        "Peer deck mentions CSRD. Company threshold not evidenced.",
        "India",
    )
    assert applies is False
    assert "not applied" in rationale.lower() or "not evidenced" in rationale.lower()


def test_no_env_inference_from_revenue_or_sites() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=(
            "Revenue INR 5,000 crore across 12 manufacturing sites implies strong "
            "environmental performance. GHG emissions inferred from revenue. "
            "Site count implies low energy intensity."
        ),
        sources=["05_Financial_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec={},
    )
    metrics = [
        m for m in (heur.get("measured_metrics") or [])
        if isinstance(m, dict)
        and not str(m.get("measured_result") or "").startswith("Information")
        and not str(m.get("measured_result") or "").startswith("N/A")
    ]
    for m in metrics:
        blob = f"{m.get('metric')} {m.get('measured_result')} {m.get('method')}".lower()
        assert "inferred from revenue" not in blob
        assert "site count implies" not in blob


def test_consequences_or_none() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=_esg_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    cons = [
        c for c in (heur.get("consequences") or [])
        if isinstance(c, dict) and not str(c.get("topic") or "").startswith("Information")
    ]
    assert cons
    types = " ".join(str(c.get("consequence_type") or "") for c in cons).lower()
    assert any(
        k in types
        for k in ("cost", "permit", "customer", "reporting", "none", "regulatory", "continuity")
    )


def test_legacy_dual_write() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=_esg_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    assert heur.get("themes") is not None
    assert heur.get("labour_flags") is not None
    assert heur.get("environment_flags") is not None
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert heur.get("dd_code") == "F-ESG" or heur.get("role_code") == "F-ESG"


def test_render_no_invest() -> None:
    heur = _heuristic_esg_and_sustainability_spec(
        company="Test3",
        corpus=_esg_corpus() + " We recommend invest.",
        sources=["06_Legal_Due_Diligence.pdf", "10_HR_Organizational_Due_Diligence.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    md = render_esg_and_sustainability_markdown("ESG & Sustainability", heur)
    assert "## 1. Material Topics" in md
    assert "## 2. Product Impact vs Operating Footprint" in md
    assert "## 3. Measured Metrics" in md
    assert "## 4. Workforce" in md or "Workforce & Safety" in md
    assert "## 5. Consequences" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "Management target" in md or "management target" in md.lower()


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "esg_and_sustainability",
        "agentName": "ESG & Sustainability",
        "target_company": "Test3",
        "summary": "ESG & Sustainability for Test3",
        "sources": ["06_Legal_Due_Diligence.pdf"],
        "spec": _heuristic_esg_and_sustainability_spec(
            company="Test3",
            corpus=_esg_corpus(),
            sources=["06_Legal_Due_Diligence.pdf"],
            sector="Electric Two-Wheelers",
            geography="India",
            legacy_spec=_legacy(),
        ),
    }
    md = render_agent_document("esg_and_sustainability", output)
    assert "## 6. Quality & Reliance" in md
    assert "Material" in md


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_esg_and_sustainability_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_esg_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        prefer_heuristic=True,
        legacy_spec=_legacy(),
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("role_code") == "F-ESG" or spec.get("dd_code") == "F-ESG"
