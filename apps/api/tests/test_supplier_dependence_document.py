"""Supplier Dependence — DiligenceIQ prompt-book vendor criticality & contracts."""

from __future__ import annotations

from agetic_cdd_api.agent_document_supplier_dependence import (
    _heuristic_supplier_dependence_spec,
    build_supplier_dependence_spec,
    render_supplier_dependence_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


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
        "China concentration risk on cells."
    )


def test_supplier_dependence_prompt_book_listed() -> None:
    system = compose_system("supplier_dependence", sector="EV", geography="India")
    assert "supplier_dependence" in listed_agents()
    assert "payables" in system.lower() or "supplier" in system.lower()
    body = agent_prompt("supplier_dependence")
    assert "Ola" not in body and "SoftBank" not in body
    assert "criticality" in body.lower()
    assert "sole source" in body.lower() or "sole-source" in body.lower()


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

    assert "## 1. Supplier Spend" in md
    assert "## 2. Operational Criticality" in md
    assert "## 3. Contract" in md
    assert "## 4. Substitutability" in md
    assert "## 5. Change-of-Control" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    vendors = heur.get("vendors") or []
    assert isinstance(vendors, list) and vendors
    assert any(
        isinstance(r, dict) and r.get("ledger_evidenced")
        for r in (heur.get("spend_by_supplier") or [])
    )
    crit = heur.get("operational_criticality") or []
    assert any(isinstance(r, dict) and "Critical" in str(r.get("criticality") or "") for r in crit)
    assert (heur.get("change_of_control") or {}).get("transaction_triggers_flagged") is True
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert "sole source" in md.lower() or "not automatically" in md.lower()


def test_named_supplier_not_automatically_sole_source() -> None:
    heur = _heuristic_supplier_dependence_spec(
        company="Test3",
        corpus="Acme Parts Widgets India ~10 Medium Yes. Alternate available Yes.",
        sources=["a.pdf"],
    )
    subst = heur.get("substitutability") or []
    md = render_supplier_dependence_markdown("Supplier Dependence", heur)
    assert "not automatically sole source" in md.lower() or any(
        "not automatically" in str(r.get("sole_source_status") or "").lower()
        for r in subst if isinstance(r, dict)
    )


def test_normalise_strips_recommendation_and_unread_terms() -> None:
    from agetic_cdd_api.agent_document_supplier_dependence import _normalise_llm_spec
    import inspect

    sig = inspect.signature(_normalise_llm_spec)
    kwargs: dict = {"sources": ["a.pdf"], "legacy_spec": None}
    if "corpus" in sig.parameters:
        kwargs["corpus"] = "CATL Li-ion Cells China ~180 High No."

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Suppliers are fine — invest",
            "spend_by_supplier": [{"supplier": "CATL", "spend": "180 Cr", "ledger_evidenced": True}],
            "operational_criticality": [{"supplier": "CATL", "criticality": "Critical"}],
            "contract_terms": [
                {
                    "supplier": "CATL",
                    "contract_read": "No",
                    "duration": "3-year term invented",
                    "termination_rights": "at will",
                }
            ],
            "substitutability": [{"supplier": "CATL", "alternatives": "None"}],
            "change_of_control": {"transaction_triggers_flagged": False},
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        **kwargs,
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()
    contracts = llm.get("contract_terms") or []
    assert contracts
    assert "3-year term invented" not in str(contracts[0].get("duration") or "")


def test_render_agent_document_supplier_dependence() -> None:
    output = {
        "agentName": "Supplier Dependence",
        "target_company": "Test3",
        "sources": ["07_Operational_Due_Diligence.pdf"],
        "document": (
            "# Supplier Dependence\n\n"
            "## 1. Supplier Spend (Payables Ledger)\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("supplier_dependence", output)
    assert "## 1. Supplier Spend" in rendered
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
    assert "## 2. Operational Criticality" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-22"
