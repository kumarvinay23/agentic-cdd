"""Operational Risk — DiligenceIQ prompt-book evidence-derived register."""

from __future__ import annotations

from agetic_cdd_api.agent_document_operational_risk import (
    _heuristic_operational_risk_spec,
    build_operational_risk_spec,
    render_operational_risk_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-ops-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _ops_corpus() -> str:
    return (
        "Operational KPI Dashboard (FY2024E). "
        "Defect Rate (units per 1000) < 8 13.4 At Risk. "
        "Parts Stockout Rate (%) < 3% 11.2% Below Target. "
        "Capacity Utilization (%) 80% 71% -9 pp Monitor. "
        "Service Resolution Time 48 hours target, actual 72 hours At Risk. "
        "Operational risk rating: HIGH. "
        "Production bottlenecks High / High. Quality defects Medium / High. "
        "Stockouts High / Medium. "
        "Cell shortage incident in Q2 2023 occurred twice per year historically "
        "with INR 42 Cr revenue impact; if recurred would cut EBITDA by ~INR 18 Cr. "
        "QA inspection SOP is in place and was tested in the FY2024 audit drill. "
        "Spare capacity contingency plan remains untested. "
        "Staff attrition at service centers 28% annually — High / Medium. "
        "Plan ramp in FY2026 to new geography (Tier-2 cities) amplifies service resolution risk. "
        "Safety near-miss at Hosur plant in 2024; control training completed but never tested under load. "
        "Generic enterprise risk framework items are ignored — register from records only."
    )


def test_operational_risk_prompt_book_listed() -> None:
    system = compose_system("operational_risk", sector="EV", geography="India")
    assert "operational_risk" in listed_agents()
    assert "risk" in system.lower()
    body = agent_prompt("operational_risk")
    assert "Ola" not in body and "SoftBank" not in body
    assert "taxonomy" in body.lower() or "generic" in body.lower()
    assert "tested" in body.lower()


def test_operational_risk_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_operational_risk.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("operational_risk")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_register_from_records_not_taxonomy() -> None:
    heur = _heuristic_operational_risk_spec(
        company="Test3",
        corpus=_ops_corpus(),
        sources=["07_Operational_Due_Diligence.pdf"],
    )
    register = heur.get("risk_register") or []
    assert any(
        isinstance(r, dict)
        and not r.get("hypothesis")
        and (
            "defect" in str(r.get("risk") or "").lower()
            or "stockout" in str(r.get("risk") or "").lower()
            or "bottleneck" in str(r.get("risk") or "").lower()
        )
        for r in register
    )
    # Must not invent a bare generic taxonomy row as the only content
    assert not all(
        "generic" in str(r.get("risk") or "").lower()
        for r in register if isinstance(r, dict)
    )


def test_untested_control_not_mitigation() -> None:
    heur = _heuristic_operational_risk_spec(
        company="Test3",
        corpus=_ops_corpus(),
        sources=["a.pdf"],
    )
    controls = heur.get("controls") or []
    assert controls
    untested = [
        c for c in controls
        if isinstance(c, dict) and "untested" in str(c.get("tested") or "").lower()
    ]
    assert untested
    assert any(
        "not mitigation" in str(c.get("mitigation_status") or "").lower()
        for c in untested
    )
    tested = [
        c for c in controls
        if isinstance(c, dict) and str(c.get("tested") or "") == "Tested"
    ]
    assert tested


def test_operational_risk_markdown_follows_prompt_book() -> None:
    heur = _heuristic_operational_risk_spec(
        company="Test3",
        corpus=_ops_corpus(),
        sources=["07_Operational_Due_Diligence.pdf"],
        legacy_spec={
            "kpi_gaps": [{"kpi": "Defect Rate", "status": "At Risk"}],
            "risk_items": [
                {"risk": "Production bottlenecks", "likelihood": "High", "impact": "High"}
            ],
            "integrity_notes": ["Legacy HIGH operational risk rating."],
        },
    )
    md = render_operational_risk_markdown("Operational Risk", heur)

    assert "## 1. Evidence-Derived Risk Register" in md
    assert "## 2. Sized Risks" in md
    assert "## 3. Controls" in md
    assert "## 4. Historical vs Plan" in md
    assert "## 5. Price / Protection" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    sized = heur.get("sized_risks") or []
    assert any(
        isinstance(s, dict) and str(s.get("sized") or "") in {"Yes", "Partial"}
        for s in sized
    )
    hist = heur.get("historical_vs_plan") or []
    assert any(
        isinstance(h, dict)
        and (
            "plan" in str(h.get("bucket") or "").lower()
            or "historical" in str(h.get("bucket") or "").lower()
        )
        for h in hist
    )
    priced = heur.get("priced_vs_noise") or []
    assert any(
        isinstance(p, dict) and "hypothesis" in str(p.get("classification") or "").lower()
        for p in priced
    )
    assert heur.get("kpi_gaps")
    assert heur.get("risk_items")
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_normalise_strips_recommendation() -> None:
    from agetic_cdd_api.agent_document_operational_risk import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Ops look fine — invest",
            "risk_register": [
                {
                    "risk": "Defect Rate gap",
                    "evidence": "13.4 At Risk",
                    "hypothesis": False,
                }
            ],
            "sized_risks": [{"risk": "Defect Rate gap", "frequency": "ongoing", "sized": "Partial"}],
            "controls": [{"risk": "Defect Rate gap", "control": "QA SOP", "tested": ""}],
            "historical_vs_plan": [{"risk": "Defect Rate gap", "bucket": "In historical results"}],
            "priced_vs_noise": [{"risk": "Unknown cyber", "classification": "Hypothesis"}],
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        sources=["a.pdf"],
        legacy_spec=None,
        corpus=_ops_corpus(),
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()
    controls = llm.get("controls") or []
    assert controls and controls[0].get("tested")
    assert "not mitigation" in str(controls[0].get("mitigation_status") or "").lower()


def test_render_agent_document_operational_risk() -> None:
    output = {
        "agentName": "Operational Risk",
        "target_company": "Test3",
        "sources": ["07_Operational_Due_Diligence.pdf"],
        "document": (
            "# Operational Risk\n\n"
            "## 1. Evidence-Derived Risk Register\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("operational_risk", output)
    assert "## 1. Evidence-Derived Risk Register" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_operational_risk_from_corpus() -> None:
    spec = build_operational_risk_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "07_Operational_Due_Diligence.pdf",
                    "cdl_category": "operations",
                    "excerpt": _ops_corpus(),
                }
            ],
            "category_counts": {"operations": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_operational_risk_markdown("Operational Risk", spec)
    assert "## 2. Sized Risks" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-19"
