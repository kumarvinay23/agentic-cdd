"""Supply Chain Resilience — DiligenceIQ prompt-book SPOF / capacity / continuity."""

from __future__ import annotations

from agetic_cdd_api.agent_document_supply_chain_resilience import (
    _heuristic_supply_chain_resilience_spec,
    build_supply_chain_resilience_spec,
    render_supply_chain_resilience_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-scr-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _scr_corpus() -> str:
    return (
        "Critical path: input cells → assembly plant → warehouse → last-mile delivery. "
        "Single-source cell supplier CATL — no alternate qualified. "
        "Single plant at Hosur for final assembly. "
        "Capacity utilization 78%. Monthly production capacity 45,000 units. "
        "Plan ramp in FY2026 binds plant capacity when volumes exceed 55,000 units/month. "
        "Days Inventory Outstanding (DIO) 68 days. Days Payable Outstanding (DPO) 38 days. "
        "Order-to-delivery lead time 22 days. Parts stockout 11.2%. "
        "Disruption: cell shortage in Q2 2023 lasted 6 weeks with INR 42 Cr revenue impact; "
        "resolved via air-freight and temporary Samsung SDI allocation. "
        "Backup dual-source for modules was tested in a 2024 drill. "
        "Spare warehouse capacity at Chennai remains untested. "
        "Contractual priority with CATL never tested under force majeure. "
        "Localization FY2024 import content 48% target. Gigafactory phase 1 localization. "
        "If CATL fails, production halt ~60 days and INR 80 Cr cost."
    )


def test_supply_chain_resilience_prompt_book_listed() -> None:
    system = compose_system("supply_chain_resilience", sector="EV", geography="India")
    assert "supply_chain_resilience" in listed_agents()
    assert "single" in system.lower() or "resilience" in system.lower()
    body = agent_prompt("supply_chain_resilience")
    assert "Ola" not in body and "SoftBank" not in body
    assert "continuity" in body.lower()
    assert "supplier" in body.lower()


def test_supply_chain_resilience_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_supply_chain_resilience.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("supply_chain_resilience")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_spof_marks_single_supplier_on_input() -> None:
    heur = _heuristic_supply_chain_resilience_spec(
        company="Test3",
        corpus=_scr_corpus(),
        sources=["12_Manufacturing_Supply_Chain_Review.pdf"],
    )
    chain = heur.get("critical_path") or []
    assert any(
        isinstance(n, dict) and str(n.get("spof") or "").lower() == "yes"
        for n in chain
    )
    inputish = [
        n for n in chain
        if isinstance(n, dict)
        and ("input" in str(n.get("stage") or "").lower() or n.get("spof_type") == "single_supplier")
    ]
    assert inputish
    assert any(str(n.get("spof") or "").lower() == "yes" for n in inputish)


def test_supply_chain_resilience_markdown_follows_prompt_book() -> None:
    heur = _heuristic_supply_chain_resilience_spec(
        company="Test3",
        corpus=_scr_corpus(),
        sources=["12_Manufacturing_Supply_Chain_Review.pdf"],
        legacy_spec={
            "logistics_metrics": {"dio_days": 68.0},
            "localization_milestones": ["Legacy localization note"],
            "resilience_notes": ["Legacy resilience note"],
        },
    )
    md = render_supply_chain_resilience_markdown("Supply Chain Resilience", heur)

    assert "## 1. Critical Path" in md
    assert "## 2. Capacity & Headroom" in md
    assert "## 3. Disruption History" in md
    assert "## 4. Continuity" in md
    assert "## 5. Plausible Downside" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert heur.get("logistics_metrics", {}).get("dio_days") == 68.0
    hist = heur.get("disruption_history") or []
    assert any(
        isinstance(r, dict)
        and "shortage" in str(r.get("incident") or "").lower()
        for r in hist
    )
    cont = heur.get("continuity_arrangements") or []
    assert any(
        isinstance(r, dict)
        and "tested" in str(r.get("tested_or_used") or "").lower()
        and "untested" not in str(r.get("tested_or_used") or "").lower()
        for r in cont
    )
    assert any(
        isinstance(r, dict) and "untested" in str(r.get("tested_or_used") or "").lower()
        for r in cont
    )
    downs = heur.get("plausible_downsides") or []
    assert downs
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_supplier_reconcile_flags_alternate_conflict() -> None:
    heur = _heuristic_supply_chain_resilience_spec(
        company="Test3",
        corpus=_scr_corpus(),
        sources=["a.pdf"],
        supplier_spec={
            "vendors": [
                {
                    "name": "CATL",
                    "component": "Li-ion Cells",
                    "country": "China",
                    "annual_value_inr_cr": 180.0,
                    "risk_level": "High",
                    "alternate_available": "Yes",
                }
            ],
            "contract_terms": [
                {
                    "supplier": "CATL",
                    "contract_read": "Yes — MSA opened",
                    "duration": "3-year term",
                    "termination_rights": "180 days notice",
                }
            ],
        },
    )
    rec = heur.get("supplier_reconcile") or {}
    assert rec.get("supplier_agent_present") is True
    conflicts = rec.get("conflicts") or []
    assert any("CATL" in str(c) and "alternate" in str(c).lower() for c in conflicts)
    assert heur.get("quality_verdict") == "REWORK"


def test_normalise_strips_recommendation_and_forces_reconcile() -> None:
    from agetic_cdd_api.agent_document_supply_chain_resilience import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Chain is fine — invest",
            "critical_path": [
                {
                    "stage": "input / cells",
                    "description": "Single-source CATL",
                    "spof": "Yes",
                    "spof_type": "single_supplier",
                    "supplier_or_asset": "CATL",
                }
            ],
            "capacity_headroom": [{"stage": "plant", "current_capacity": "45k"}],
            "disruption_history": [{"incident": "shortage"}],
            "continuity_arrangements": [
                {"arrangement": "dual-source", "tested_or_used": ""}
            ],
            "plausible_downsides": [{"exposure": "CATL"}],
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "READY",
        },
        sources=["a.pdf"],
        legacy_spec=None,
        corpus=_scr_corpus(),
        supplier_spec={
            "vendors": [
                {"name": "CATL", "alternate_available": "Yes"},
            ],
        },
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()
    cont = llm.get("continuity_arrangements") or []
    assert cont and cont[0].get("tested_or_used")
    assert llm.get("quality_verdict") == "REWORK"
    assert (llm.get("supplier_reconcile") or {}).get("conflicts")


def test_render_agent_document_supply_chain_resilience() -> None:
    output = {
        "agentName": "Supply Chain Resilience",
        "target_company": "Test3",
        "sources": ["12_Manufacturing_Supply_Chain_Review.pdf"],
        "document": (
            "# Supply Chain Resilience\n\n"
            "## 1. Critical Path & Single Points of Failure\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("supply_chain_resilience", output)
    assert "## 1. Critical Path" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_supply_chain_resilience_from_corpus() -> None:
    spec = build_supply_chain_resilience_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "12_Manufacturing_Supply_Chain_Review.pdf",
                    "cdl_category": "operations",
                    "excerpt": _scr_corpus(),
                }
            ],
            "category_counts": {"operations": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_supply_chain_resilience_markdown("Supply Chain Resilience", spec)
    assert "## 2. Capacity & Headroom" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-14"
