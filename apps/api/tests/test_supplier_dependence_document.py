"""Supplier Dependence — DiligenceIQ prompt-book vendor criticality & contracts."""

from __future__ import annotations

from agetic_cdd_api.agent_document_supplier_dependence import (
    _heuristic_supplier_dependence_spec,
    _normalise_llm_spec,
    build_supplier_dependence_spec,
    render_supplier_dependence_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import (
    agent_prompt,
    compose_system,
    listed_agents,
    questions_complete,
)


class _FakeDeal:
    id = "deal-sup-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _sup_corpus() -> str:
    return (
        "Vendor Concentration. CATL Li-ion Cells China ~180 High No. "
        "Samsung SDI Battery Modules Korea ~95 Medium Partial. "
        "Motherson Sumi Wiring Harness India ~42 Low Yes. "
        "Total supplier spend FY2024 450 Cr. "
        "CATL is critical — production stops if cell supply stops. No alternate qualified. "
        "Executed MSA with CATL: 3-year term, auto-renewal, fixed pricing with annual escalator, "
        "SLA OTIF 95%, termination for convenience with 180 days notice, assignment restricted, "
        "change-of-control consent required, exclusivity for India EV cells. "
        "Switching from CATL would take 18 months to qualify and cost INR 80 Cr. "
        "Samsung SDI alternate Partial in Korea geography. "
        "China concentration risk on cells. Supply chain resilience localization noted."
    )


def _thin_corpus() -> str:
    return "Management asserts heavy supplier dependence. No payables ledger opened."


def test_supplier_dependence_prompt_book_listed() -> None:
    system = compose_system("supplier_dependence", sector="EV", geography="India")
    assert "supplier_dependence" in listed_agents()
    assert "payables" in system.lower() or "supplier" in system.lower()
    assert "questions" in system.lower()
    assert "[DEAL_PERIMETER]" in system or "Deal perimeter" in system
    body = agent_prompt("supplier_dependence")
    assert "Ola" not in body and "SoftBank" not in body
    assert "criticality" in body.lower()
    assert "sole source" in body.lower() or "sole-source" in body.lower()
    assert "disruption" in body.lower() or "resilien" in body.lower()


def test_supplier_dependence_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_supplier_dependence.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("supplier_dependence")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_unread_contracts_not_stated() -> None:
    heur = _heuristic_supplier_dependence_spec(
        company="Test3",
        corpus="CATL Li-ion Cells China ~180 High No. No contract pack opened.",
        sources=["a.pdf"],
    )
    contracts = heur.get("contract_terms") or []
    assert contracts
    row = contracts[0]
    assert str(row.get("contract_read") or "").startswith("No")
    for field in ("duration", "termination_rights", "exclusivity"):
        val = str(row.get(field) or "")
        assert (
            val.startswith("Information request")
            or val == "N/A (data room did not provide it)"
        ), field


def test_supplier_dependence_markdown_follows_prompt_book() -> None:
    heur = _heuristic_supplier_dependence_spec(
        company="Test3",
        corpus=_sup_corpus(),
        sources=["07_Operational_Due_Diligence.pdf"],
        legacy_spec={
            "vendors": [
                {
                    "name": "CATL",
                    "component": "Li-ion Cells",
                    "country": "China",
                    "annual_value_inr_cr": 180.0,
                    "risk_level": "High",
                    "alternate_available": "No",
                }
            ],
            "concentration_flags": ["Legacy China concentration"],
            "dependency_notes": ["Legacy dependency note"],
        },
    )
    md = render_supplier_dependence_markdown("Supplier Dependence", heur)

    assert "## 1. Supplier" in md
    assert "## 2. Operational" in md
    assert "## 3. Contract" in md
    assert "## 4. Substitut" in md or "## 4." in md
    assert "## 5. Change" in md or "## 5." in md
    assert "## 6. Supplier Evidence QA" in md
    assert "## 7. Questions and Inputs Required" in md
    assert "## 8. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert heur.get("supplier_roles")
    assert heur.get("disruption_priority")
    assert heur.get("scr_reconcile")
    qa = heur.get("supplier_evidence_qa") or []
    assert any(
        isinstance(r, dict)
        and r.get("check") == "contract_clauses_read"
        and r.get("status") == "PASS"
        for r in qa
    )
    assert heur.get("questions")
    assert questions_complete(heur["questions"])
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_thin_supplier_qa_and_questions() -> None:
    heur = _heuristic_supplier_dependence_spec(
        company="Test3",
        corpus=_thin_corpus(),
        sources=["a.pdf"],
    )
    qa = heur.get("supplier_evidence_qa") or []
    assert any(isinstance(r, dict) and r.get("status") == "FAIL" for r in qa)
    assert heur.get("questions")
    assert questions_complete(heur["questions"])
    assert heur.get("reliance_verdict") in {"LIMITED", "BLOCKED"}
    md = render_supplier_dependence_markdown("Supplier Dependence", heur)
    assert "## 6. Supplier Evidence QA" in md
    assert "FAIL" in md


def test_named_supplier_not_automatically_sole_source() -> None:
    heur = _heuristic_supplier_dependence_spec(
        company="Test3",
        corpus="Acme Widgets is a named supplier with partial alternates available.",
        sources=["a.pdf"],
    )
    subst = heur.get("substitutability") or []
    for row in subst:
        if not isinstance(row, dict):
            continue
        status = str(row.get("sole_source_status") or "").lower()
        assert ("not" in status and "automatically" in status) or "sole source" in status


def test_normalise_strips_recommendation_and_unread_terms() -> None:
    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Suppliers are fine — invest",
            "spend_by_supplier": [],
            "operational_criticality": [],
            "contract_terms": [
                {
                    "supplier": "CATL",
                    "contract_read": "No",
                    "duration": "3 years",
                    "exclusivity": "Yes",
                }
            ],
            "substitutability": [],
            "change_of_control": {},
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        sources=["a.pdf"],
        legacy_spec=None,
        corpus="CATL Li-ion Cells China ~180 High No.",
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()
    contracts = llm.get("contract_terms") or []
    if contracts:
        row = contracts[0]
        assert "Information request" in str(row.get("duration") or "") or str(
            row.get("contract_read") or ""
        ).startswith("No")
    assert llm.get("supplier_evidence_qa")
    assert llm.get("questions")
    assert questions_complete(llm["questions"])


def test_render_agent_document_supplier_dependence() -> None:
    output = {
        "agentName": "Supplier Dependence",
        "target_company": "Test3",
        "sources": ["07_Operational_Due_Diligence.pdf"],
        "document": (
            "# Supplier Dependence\n\n"
            "## 1. Supplier Spend (Payables Ledger)\n\n"
            "Seeded.\n\n"
            "## 8. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("supplier_dependence", output)
    assert "## 1. Supplier" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_supplier_dependence_from_corpus() -> None:
    spec = build_supplier_dependence_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "07_Operational_Due_Diligence.pdf",
                    "cdl_category": "operations",
                    "excerpt": _sup_corpus(),
                }
            ],
            "category_counts": {"operations": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_supplier_dependence_markdown("Supplier Dependence", spec)
    assert "## 2. Operational" in md
    assert "## 6. Supplier Evidence QA" in md
    assert "## 7. Questions" in md
    assert "## 8. Quality & Reliance" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("questions")
    assert questions_complete(spec["questions"])
    assert spec.get("deal_slots")
    assert spec.get("supplier_evidence_qa")
    assert spec.get("disruption_priority")
    assert spec.get("scr_reconcile")
